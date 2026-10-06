"""Real NOSUPERUSER installation, Auth dependency preservation and rollback."""
from __future__ import annotations

import hashlib
import json
import os
import time
import unittest
from uuid import uuid4

from tests.postgres import harness
from tests.postgres import installer_fixture as fixture
from tests.postgres.legacy_fixture import literal


@unittest.skipUnless(os.environ.get(harness.OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class InstallerBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = harness.IsolatedPostgres()
        cls.addClassCleanup(cls.db.close)
        cls.db.start()
        cls.db.sql('CREATE ROLE vn_test_admin LOGIN SUPERUSER;')
        cls.db.sql(fixture.HOSTED_BOOTSTRAP, role=fixture.ADMIN)
        cls.db.sql("""
CREATE TABLE public.installer_unrelated (id integer PRIMARY KEY, value text);
INSERT INTO public.installer_unrelated VALUES(1,'preserve');
CREATE TABLE public.installer_gate (released boolean NOT NULL);
INSERT INTO public.installer_gate VALUES(false);
GRANT SELECT,UPDATE ON public.installer_unrelated TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
 GRANT ALL ON TABLES TO anon,authenticated,service_role;
""")

    def admin(self, sql, *, check=True):
        return self.db.sql(sql, role=fixture.ADMIN, check=check)

    def setUp(self):
        self.admin("""
DROP SCHEMA IF EXISTS vn_read,vn_projection,vn_durability,vn_identity CASCADE;
UPDATE public.installer_gate SET released=false;
DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='vn_contract_owner') THEN
 EXECUTE 'DROP OWNED BY vn_contract_owner'; EXECUTE 'DROP ROLE vn_contract_owner';
END IF; END $$;
ALTER ROLE postgres NOSUPERUSER CREATEDB CREATEROLE INHERIT NOREPLICATION BYPASSRLS;
REVOKE ALL ON SCHEMA auth FROM postgres;
REVOKE ALL ON FUNCTION auth.uid() FROM postgres;
REVOKE ALL(id) ON auth.users FROM postgres;
GRANT USAGE ON SCHEMA auth TO postgres;
GRANT EXECUTE ON FUNCTION auth.uid() TO postgres;
GRANT REFERENCES(id) ON auth.users TO postgres;
""")
        self.before = self.unchanged_catalog()

    def unchanged_catalog(self):
        return self.db.scalar("""
SELECT jsonb_build_object(
 'auth_schema',(SELECT jsonb_build_object('owner',nspowner,'acl',nspacl)
   FROM pg_namespace WHERE nspname='auth'),
 'auth_table',(SELECT jsonb_build_object('owner',relowner,'acl',relacl)
   FROM pg_class WHERE oid='auth.users'::regclass),
 'auth_columns',(SELECT jsonb_agg(jsonb_build_object('name',attname,'acl',attacl) ORDER BY attnum)
   FROM pg_attribute WHERE attrelid='auth.users'::regclass AND attnum>0),
 'auth_uid',(SELECT jsonb_build_object('owner',proowner,'acl',proacl,'body',prosrc)
   FROM pg_proc WHERE oid='auth.uid()'::regprocedure),
 'defaults',(SELECT coalesce(jsonb_agg(to_jsonb(d) ORDER BY oid),'[]'::jsonb)
   FROM pg_default_acl d WHERE defaclrole='postgres'::regrole),
 'api_roles',(SELECT jsonb_agg(to_jsonb(r) ORDER BY oid) FROM pg_roles r
   WHERE rolname IN ('anon','authenticated','service_role','authenticator')),
 'api_memberships',(SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY m.oid),'[]'::jsonb)
   FROM pg_auth_members m WHERE member IN
   (SELECT oid FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role','authenticator'))),
 'unrelated',(SELECT jsonb_build_object('owner',relowner,'acl',relacl)
   FROM pg_class WHERE oid='public.installer_unrelated'::regclass),
 'unrelated_rows',(SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM public.installer_unrelated t)
);
""", role=fixture.ADMIN)

    def install(self, *, suffix='', check=True):
        return self.db.sql(fixture.rehearsal_sql(suffix=suffix), check=check, timeout=30)

    def assert_uninstalled(self):
        self.assertEqual(self.db.scalar("SELECT NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname IN "
            "('vn_identity','vn_durability','vn_projection','vn_read')) AND "
            "NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='vn_contract_owner');"), 't')

    def owner_sql(self, sql):
        return self.db.sql('SET ROLE vn_contract_owner;\n' + sql)

    def bootstrap_v5(self, strategy='genetic_algorithm'):
        from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
        from vonneumann.core import provider_lifecycle as core
        from tests.postgres import test_provider_contract as provider
        owner, run, worker, command = (str(uuid4()) for _ in range(4))
        self.admin('INSERT INTO auth.users VALUES(' + literal(owner) + ');')
        config = core.ProviderLifecycleConfig(ExactLifecycleConfig(strategy, owner, run, asset='SOL/USD'), str(uuid4()))
        args = [literal(owner), literal(run), literal(worker), literal(command),
                literal(json.dumps(config.run_configuration())) + '::jsonb', literal(config.initial_cash), '120']
        self.db.sql('SELECT vn_durability.create_run(' + ','.join(args) + ');', role='service_role')
        now, mono = time.time(), time.monotonic()
        candidate = core.bootstrap(config, provider.seed_history(now, mono), provider.decision_inputs(now, mono))
        payload = {'version': 5, 'operations': candidate.operations, 'transition': candidate.transition}
        args = [literal(owner), literal(run), literal(worker), '1', '1', literal(str(uuid4())),
                literal(json.dumps(payload)) + '::jsonb']
        self.db.sql('SELECT vn_durability.commit_command(' + ','.join(args) + ');', role='service_role', timeout=30)
        actual = json.loads(self.db.scalar('SELECT engine_state FROM vn_durability.runs WHERE id=' + literal(run) + ';',
                                          role=fixture.ADMIN))
        self.assertEqual(actual, candidate.state.to_dict())
        page = json.loads(self.db.scalar('SET request.jwt.claim.sub=' + literal(owner) + '; SELECT vn_read.page(' +
            literal(run) + ",'probes');", role='authenticated'))
        self.assertEqual(len(page['records']), 8)
        return owner, run

    def test_original_fixture_installation_fails_without_auth_dependency_grants(self):
        self.db.sql('CREATE ROLE vn_contract_owner NOLOGIN NOSUPERUSER NOCREATEROLE NOBYPASSRLS; '
                    'GRANT vn_contract_owner TO postgres WITH INHERIT FALSE, SET TRUE;')
        result = self.db.sql(fixture.MARKER + harness.CONTRACT.read_text(), check=False, timeout=30)
        self.assertIn('42501', result.stderr)
        self.assertIn('auth', result.stderr)
        self.assertEqual(self.db.scalar("SELECT to_regnamespace('vn_durability') IS NULL;"), 't')
        self.assertEqual(self.unchanged_catalog(), self.before)

    def test_full_laboratory_installs_as_actual_non_superuser_postgres(self):
        self.assertEqual(self.db.scalar("SELECT current_user='postgres' AND session_user='postgres' AND "
            "NOT rolsuper AND rolcreaterole AND rolbypassrls FROM pg_roles WHERE rolname=current_user;"), 't')
        self.install()
        self.assertEqual(self.unchanged_catalog(), self.before)
        self.assertEqual(self.db.scalar("SELECT relowner='vn_contract_owner'::regrole FROM pg_class "
                                       "WHERE oid='vn_durability.runs'::regclass;", role=fixture.ADMIN), 't')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_constraint WHERE conrelid='vn_durability.runs'::regclass "
                                       "AND confrelid='auth.users'::regclass AND contype='f' AND convalidated;", role=fixture.ADMIN), '1')
        self.assertEqual(self.db.scalar("SELECT NOT rolsuper AND NOT rolcanlogin AND NOT rolcreaterole AND "
            "NOT rolcreatedb AND NOT rolbypassrls AND NOT rolinherit AND NOT rolreplication "
            "FROM pg_roles WHERE rolname='vn_contract_owner';"), 't')

    def test_private_owner_needs_no_auth_grants_or_managed_role_membership(self):
        self.install()
        self.assertEqual(self.db.scalar("SELECT NOT has_schema_privilege('vn_contract_owner','auth','USAGE') AND "
            "NOT has_function_privilege('vn_contract_owner','auth.uid()','EXECUTE') AND "
            "NOT has_column_privilege('vn_contract_owner','auth.users','id','REFERENCES') AND "
            "NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member='vn_contract_owner'::regrole);"), 't')
        self.assertEqual(self.db.scalar("SELECT NOT pg_has_role('vn_contract_owner','postgres','SET') AND "
            "NOT has_schema_privilege('vn_contract_owner','vn_identity','CREATE') AND "
            "NOT has_schema_privilege('postgres','vn_durability','CREATE');"), 't')
    def test_identity_bridge_preserves_auth_uid_null_and_both_claim_forms(self):
        self.install()
        self.assertEqual(self.owner_sql('SELECT vn_identity.owner_id() IS NULL;').stdout.strip(), 't')
        for claims in ("SET request.jwt.claim.sub='" + str(uuid4()) + "';",
                       "SET request.jwt.claims='" + json.dumps({'sub': str(uuid4())}) + "';",
                       "SET request.jwt.claim.sub='" + str(uuid4()) + "'; SET request.jwt.claims='" +
                       json.dumps({'sub': str(uuid4())}) + "';"):
            expected = self.db.scalar(claims + ' SELECT auth.uid();')
            actual = self.owner_sql(claims + ' SELECT vn_identity.owner_id();').stdout.strip()
            self.assertEqual(actual, expected)
        denied = self.db.sql("SET ROLE vn_contract_owner; SELECT auth.uid();", check=False)
        self.assertIn('42501', denied.stderr)
        malformed = self.db.sql("SET ROLE vn_contract_owner; SET request.jwt.claim.sub='bad-uuid'; "
                               "SELECT vn_identity.owner_id();", check=False)
        self.assertIn('22P02', malformed.stderr)

    def test_bridge_is_fixed_installer_owned_and_private_owner_cannot_replace_it(self):
        self.install()
        self.assertEqual(self.db.scalar("SELECT proowner='postgres'::regrole AND prosecdef AND provolatile='s' "
            "AND pronargs=0 AND proconfig=ARRAY['search_path=pg_catalog, pg_temp'] "
            "FROM pg_proc WHERE oid='vn_identity.owner_id()'::regprocedure;"), 't')
        for sql in ("CREATE OR REPLACE FUNCTION vn_identity.owner_id() RETURNS uuid LANGUAGE sql AS $$ SELECT NULL::uuid $$;",
                    'ALTER FUNCTION vn_identity.owner_id() OWNER TO vn_contract_owner;',
                    'DROP FUNCTION vn_identity.owner_id();', 'GRANT EXECUTE ON FUNCTION vn_identity.owner_id() TO authenticated;'):
            result = self.db.sql('SET ROLE vn_contract_owner; ' + sql, check=False)
            # GRANT may succeed with a warning while granting nothing; check effect too.
            self.assertTrue(result.returncode or 'no privileges were granted' in result.stderr)
            self.assertEqual(self.db.scalar("SELECT has_function_privilege('authenticated','vn_identity.owner_id()','EXECUTE');"), 'f')

    def test_api_roles_cannot_use_bridge_assume_owner_or_direct_write_core(self):
        self.install()
        for role in ('anon', 'authenticated', 'service_role', 'authenticator'):
            for sql in ('SELECT vn_identity.owner_id();', 'SET ROLE vn_contract_owner;',
                        'DELETE FROM vn_durability.runs;', 'SELECT * FROM vn_projection.runs;'):
                with self.subTest(role=role, sql=sql):
                    denied = self.db.sql(sql, role=role, check=False)
                    self.assertIn('42501', denied.stderr)

    def test_all_four_v5_bootstraps_curated_two_owner_reads_and_fk_remain_valid(self):
        self.install()
        runs = [self.bootstrap_v5(strategy) for strategy in
                ('genetic_algorithm', 'differential_evolution', 'particle_swarm', 'cma_es')]
        owner, run = runs[0]
        for claims in ('', 'SET request.jwt.claim.sub=' + literal(runs[1][0]) + '; '):
            denied = self.db.sql(claims + 'SELECT vn_read.page(' + literal(run) + ",'probes');",
                                 role='authenticated', check=False)
            self.assertNotEqual(denied.returncode, 0, denied.stdout)
            self.assertIn('run_unavailable' if claims else 'invalid_read_page', denied.stderr)
        # Already-created FK still enforces existence without new Auth grants.
        nonexistent = str(uuid4())
        denied = self.admin('UPDATE vn_durability.runs SET user_id=' + literal(nonexistent) +
                            ' WHERE id=' + literal(run) + ';', check=False)
        self.assertIn('23503', denied.stderr)
        self.assertEqual(self.unchanged_catalog(), self.before)

    def test_atomic_late_failure_removes_roles_schemas_and_membership(self):
        result = self.install(suffix='SELECT 1/0;', check=False)
        self.assertIn('22012', result.stderr)
        self.assert_uninstalled()
        self.assertEqual(self.unchanged_catalog(), self.before)

    def test_opt_in_and_superuser_installation_are_rejected_before_mutation(self):
        sources = fixture.verified_sources()
        result = self.db.sql(sources['004_installer_boundary.sql'], check=False)
        self.assertIn('isolated_installer_rehearsal_required', result.stderr)
        self.admin('ALTER ROLE postgres SUPERUSER;')
        result = self.install(check=False)
        self.assertIn('hosted_like_installer_required', result.stderr)
        self.assert_uninstalled()

    def test_auth_grant_options_and_missing_dependency_are_rejected(self):
        variants = (
            'GRANT USAGE ON SCHEMA auth TO postgres WITH GRANT OPTION;',
            'GRANT EXECUTE ON FUNCTION auth.uid() TO postgres WITH GRANT OPTION;',
            'GRANT REFERENCES(id) ON auth.users TO postgres WITH GRANT OPTION;',
            'REVOKE EXECUTE ON FUNCTION auth.uid() FROM postgres;',
        )
        for sql in variants:
            self.setUp()
            self.admin(sql)
            before = self.unchanged_catalog()
            result = self.install(check=False)
            self.assertIn('measured_auth_dependency_permissions_required', result.stderr)
            self.assert_uninstalled()
            self.assertEqual(self.unchanged_catalog(), before)

    def test_existing_owner_and_schema_fail_closed_without_repurposing(self):
        self.db.sql('CREATE ROLE vn_contract_owner NOLOGIN;')
        result = self.install(check=False)
        self.assertIn('fresh_installer_rehearsal_required', result.stderr)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_auth_members WHERE roleid='vn_contract_owner'::regrole;"), '1')
        self.setUp()
        self.db.sql('CREATE SCHEMA vn_identity; CREATE TABLE vn_identity.preserve(id integer); '
                    'INSERT INTO vn_identity.preserve VALUES(42);')
        result = self.install(check=False)
        self.assertIn('fresh_installer_rehearsal_required', result.stderr)
        self.assertEqual(self.db.scalar('SELECT id FROM vn_identity.preserve;'), '42')

    def test_api_administrative_membership_is_rejected_and_preserved(self):
        self.admin('CREATE ROLE vn_test_indirect NOLOGIN; GRANT vn_test_indirect TO authenticated WITH ADMIN TRUE;')
        self.addCleanup(self.admin, 'DROP ROLE vn_test_indirect;')
        before = self.unchanged_catalog()
        result = self.install(check=False)
        self.assertIn('api_role_authority_requires_review', result.stderr)
        self.assert_uninstalled()
        self.assertEqual(self.unchanged_catalog(), before)

    def test_fixture_manifest_pins_sources_and_denies_production_packaging(self):
        sources = fixture.verified_sources()
        manifest = json.loads(fixture.MANIFEST.read_text())
        self.assertFalse(manifest['production_application_available'])
        for name, value in sources.items():
            self.assertEqual(hashlib.sha256(value.encode()).hexdigest(), manifest['sources_sha256'][name])
        with self.assertRaisesRegex(ValueError, 'anchor changed'):
            fixture.replace_once('duplicated duplicated', 'duplicated', 'replacement')

    def test_inherited_creator_setting_is_locally_neutralized_and_restored(self):
        result = self.db.sql("SET createrole_self_grant='inherit,set';\n" + fixture.rehearsal_sql() +
                             '\nSHOW createrole_self_grant;', timeout=30)
        self.assertEqual(result.stdout.strip(), 'inherit,set')
        memberships = json.loads(self.db.scalar("SELECT jsonb_agg(jsonb_build_object('member',pg_get_userbyid(member),"
            "'admin',admin_option,'set',set_option,'inherit',inherit_option) ORDER BY admin_option DESC) "
            "FROM pg_auth_members WHERE roleid='vn_contract_owner'::regrole;"))
        self.assertEqual(memberships, [
            {'member': 'postgres', 'admin': True, 'set': False, 'inherit': False},
            {'member': 'postgres', 'admin': False, 'set': True, 'inherit': False},
        ])
        self.assertEqual(self.unchanged_catalog(), self.before)

    def test_auth_fk_lock_timeout_rolls_back_entire_installation(self):
        held = self.db.begin_sql("BEGIN; LOCK auth.users IN ACCESS EXCLUSIVE MODE; "
            "SELECT pg_advisory_lock(7320661); DO $$ BEGIN LOOP "
            "EXIT WHEN (SELECT released FROM public.installer_gate); PERFORM pg_sleep(.025); "
            "END LOOP; END $$; COMMIT;", role=fixture.ADMIN, timeout=12)
        try:
            self.db.wait_until("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' "
                               "AND objid=7320661 AND granted);")
            result = self.install(check=False)
            self.assertIn('55P03', result.stderr)
            self.assert_uninstalled()
            self.assertEqual(self.unchanged_catalog(), self.before)
        finally:
            self.admin('UPDATE public.installer_gate SET released=true;')
            held.wait(timeout=12)

    def test_unexpected_global_function_default_fails_without_changing_defaults(self):
        self.admin('CREATE ROLE vn_test_extra_execute NOLOGIN; ALTER DEFAULT PRIVILEGES FOR ROLE postgres '
                   'GRANT EXECUTE ON FUNCTIONS TO vn_test_extra_execute;')
        self.addCleanup(self.admin, 'ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE EXECUTE ON FUNCTIONS '
                        'FROM vn_test_extra_execute; DROP ROLE vn_test_extra_execute;')
        before = self.unchanged_catalog()
        result = self.install(check=False)
        self.assertIn('installer_boundary_postcondition_failed', result.stderr)
        self.assert_uninstalled()
        self.assertEqual(self.unchanged_catalog(), before)

    def test_caller_search_path_cannot_replace_managed_identity_dependency(self):
        self.install()
        expected, spoofed = str(uuid4()), str(uuid4())
        result = self.db.sql("SET ROLE vn_contract_owner; CREATE TEMP TABLE uid_shadow(id uuid); "
            "CREATE FUNCTION pg_temp.uid() RETURNS uuid LANGUAGE sql AS $$ SELECT '" + spoofed +
            "'::uuid $$; SET search_path=pg_temp,public; SET request.jwt.claim.sub='" + expected +
            "'; SELECT vn_identity.owner_id();")
        self.assertEqual(result.stdout.strip(), expected)
