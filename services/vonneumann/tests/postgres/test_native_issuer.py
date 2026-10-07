"""Real limited-issuer atomicity, grants, collisions and bounded pair revocation."""
from __future__ import annotations

from dataclasses import replace
import json
import os
import time
import unittest
from uuid import uuid4

from tests.postgres import harness, installer_fixture, native_issuer_fixture as fixture
from tests.postgres.test_session_auth import NativeSessionAuthTests as _SessionTests
from tests.postgres.test_command_adapter import literal
from tests.postgres.test_decimal_lineage_contract import document
from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
from vonneumann.core.provider_lifecycle import ProviderLifecycleConfig


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for cls in (LimitedIssuerBoundaryTests, LimitedIssuedRpcTests):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    return suite


@unittest.skipUnless(os.environ.get(harness.OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class LimitedIssuedRpcTests(_SessionTests):
    @classmethod
    def setUpClass(cls):
        cls.db = fixture.start(cls)


@unittest.skipUnless(os.environ.get(harness.OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class LimitedIssuerBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = fixture.start(cls)
        cls.db.sql('''CREATE TABLE public.issuer_unrelated(id integer PRIMARY KEY);
INSERT INTO public.issuer_unrelated VALUES(42);
GRANT SELECT,UPDATE ON public.issuer_unrelated TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon,authenticated,service_role;
''')

    def setUp(self):
        self.owner, self.other, self.run = (str(uuid4()) for _ in range(3))
        self.admin(f"INSERT INTO auth.users VALUES('{self.owner}'),('{self.other}');")
        self.pair = fixture.Pair.new(self.owner, self.run)
        self.before = self.unchanged()

    def tearDown(self):
        self.assertEqual(self.unchanged(), self.before)

    def admin(self, source, **options):
        return self.db.sql(source, role=installer_fixture.ADMIN, **options)

    def unchanged(self):
        return self.admin('''SELECT jsonb_build_object(
 'auth_schema',(SELECT to_jsonb(n) FROM pg_namespace n WHERE nspname='auth'),
 'auth_table',(SELECT jsonb_build_object('owner',relowner,'acl',relacl) FROM pg_class WHERE oid='auth.users'::regclass),
 'auth_columns',(SELECT jsonb_agg(jsonb_build_array(attnum,attacl) ORDER BY attnum) FROM pg_attribute WHERE attrelid='auth.users'::regclass AND attnum>0),
 'auth_uid',(SELECT jsonb_build_object('owner',proowner,'acl',proacl,'body',prosrc) FROM pg_proc WHERE oid='auth.uid()'::regprocedure),
 'api_roles',(SELECT jsonb_agg(to_jsonb(r)-'rolpassword' ORDER BY oid) FROM pg_roles r WHERE rolname IN ('anon','authenticated','service_role','authenticator')),
 'api_members',(SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY oid),'[]') FROM pg_auth_members m WHERE member IN
   (SELECT oid FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role','authenticator'))),
 'private_members',(SELECT jsonb_agg(to_jsonb(m) ORDER BY oid) FROM pg_auth_members m WHERE roleid='vn_contract_owner'::regrole),
 'defaults',(SELECT coalesce(jsonb_agg(to_jsonb(d) ORDER BY oid),'[]') FROM pg_default_acl d),
 'role_settings',(SELECT coalesce(jsonb_agg(to_jsonb(d) ORDER BY setdatabase,setrole),'[]') FROM pg_db_role_setting d),
 'unrelated_acl',(SELECT relacl::text FROM pg_class WHERE oid='public.issuer_unrelated'::regclass),
 'unrelated_rows',(SELECT jsonb_agg(to_jsonb(t)) FROM public.issuer_unrelated t),
 'function_bodies',(SELECT md5(string_agg(oid::text||prosrc||coalesce(proacl::text,''),',' ORDER BY oid)) FROM pg_proc WHERE pronamespace IN
   ('vn_access'::regnamespace,'vn_durability'::regnamespace,'vn_read'::regnamespace)));''').stdout.strip()

    def bind_count(self, pair):
        ids = ','.join(literal(value) for value in pair.issuances)
        return int(self.admin(f'SELECT count(*) FROM vn_access.bindings WHERE issuance_id IN ({ids});').stdout)

    def assert_absent(self, pair, *, existing=()):
        for name in pair.names:
            count = self.admin(f"SELECT count(*) FROM pg_roles WHERE rolname='{name}';").stdout.strip()
            self.assertEqual(count, '1' if name in existing else '0')
        self.assertEqual(self.bind_count(pair), 0)

    def status(self, pair):
        ids = ','.join(literal(value) for value in pair.issuances)
        return json.loads(self.admin(f"SELECT jsonb_agg(jsonb_build_object('name',b.principal_name,'oid',b.principal_oid,"
            "'revoked',b.revoked_at,'login',r.rolcanlogin) ORDER BY b.capability) FROM vn_access.bindings b "
            f'JOIN pg_roles r ON r.oid=b.principal_oid WHERE b.issuance_id IN ({ids});').stdout)

    def revoke(self, pair, *, check=True, source=None, oids=None):
        result = self.db.private_sql(source or self.db.revoke_source(pair, oids or self.db.oids(pair)))
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def denied(self, result, message):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        for value in self.db.sensitive_values:
            self.assertNotIn(value, result.stdout + result.stderr)

    def barrier(self, marker):
        # Independent fixture observer only; limited postgres cannot see other
        # sessions' redacted activity. Do not broaden issuer statistics grants.
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            if self.admin(f"SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='{marker}' AND wait_event='PgSleep');").stdout.strip()=='t':
                return
            time.sleep(.03)
        self.fail('Owned limited-issuer concurrency barrier did not appear')

    def create(self, pair):
        worker, command = str(uuid4()), str(uuid4())
        config = ProviderLifecycleConfig(ExactLifecycleConfig('genetic_algorithm',pair.owner,pair.run,asset='SOL/USD'),str(uuid4()))
        source = 'SELECT vn_durability.create_run(' + ','.join((literal(pair.owner),literal(pair.run),literal(worker),
                  literal(command),document(config.run_configuration()),literal(config.initial_cash),'120')) + ');'
        response = json.loads(self.db.native(pair.names[0],'economic',source).stdout)
        return command, response

    def test_actual_limited_issuer_creates_independent_scram_bound_pair(self):
        self.db.issue_pair(self.pair)
        self.assertEqual(self.bind_count(self.pair), 2)
        for index, capability in enumerate(('economic','relay')):
            name = self.pair.names[index]
            self.assertEqual(self.db.native(name,capability,'SELECT session_user,system_user,current_user;').stdout.strip(),
                             f'{name}|scram-sha-256:{name}|vn_{capability}')
            self.assertEqual(self.admin(f"SELECT rolpassword LIKE 'SCRAM-SHA-256$4096:%' FROM pg_authid WHERE rolname='{name}';").stdout.strip(),'t')
            result = json.loads(self.admin(f"SELECT jsonb_agg(jsonb_build_array(pg_get_userbyid(roleid),admin_option,inherit_option,set_option)) "
                f"FROM pg_auth_members WHERE member='{name}'::regrole;").stdout)
            self.assertEqual(result, [[f'vn_{capability}',False,False,True]])
        self.assertEqual(self.db.scalar("SELECT session_user='postgres' AND NOT rolsuper AND rolcreaterole FROM pg_roles WHERE rolname=session_user;"),'t')
        self.assertEqual(self.admin(f"SELECT bool_and(recovery_until-issued_at=interval '600 seconds' AND "
            f"expires_at-issued_at=interval '300 seconds') FROM vn_access.bindings WHERE run_id='{self.run}';").stdout.strip(),'t')

    def test_creator_and_password_settings_are_local_and_restored(self):
        source = "SET createrole_self_grant='inherit,set'; SET password_encryption='md5';\n" + self.db.issue_source(self.pair)
        source += '\nSHOW createrole_self_grant; SHOW password_encryption;'
        self.assertEqual(self.db.issue_pair(self.pair, source=source).stdout.strip(),'inherit,set\nmd5')
        for name in self.pair.names:
            self.assertEqual(self.admin(f"SELECT count(*) FROM pg_auth_members WHERE roleid='{name}'::regrole AND "
                "member='postgres'::regrole AND grantor=10 AND admin_option AND NOT set_option AND NOT inherit_option;").stdout.strip(),'1')
        self.db.native(self.pair.names[0],'economic','SELECT 1;')

    def test_existing_second_name_is_never_repurposed(self):
        existing = self.pair.names[1]
        self.admin(f'CREATE ROLE {existing} NOLOGIN;')
        before = self.admin(f"SELECT to_jsonb(r)-'rolpassword' FROM pg_roles r WHERE rolname='{existing}';").stdout
        self.denied(self.db.issue_pair(self.pair,check=False),'native_issuer_fresh_names_required')
        self.assert_absent(self.pair, existing=(existing,))
        self.assertEqual(self.admin(f"SELECT to_jsonb(r)-'rolpassword' FROM pg_roles r WHERE rolname='{existing}';").stdout,before)

    def test_existing_issuance_identity_rolls_back_new_pair(self):
        self.db.issue_pair(self.pair)
        other = replace(fixture.Pair.new(self.owner,self.run), issuances=(self.pair.issuances[0],str(uuid4())))
        before = self.status(self.pair)
        self.denied(self.db.issue_pair(other,check=False),'native_issuer_fresh_bindings_required')
        for name in other.names:
            self.assertEqual(self.admin(f"SELECT count(*) FROM pg_roles WHERE rolname='{name}';").stdout.strip(),'0')
        self.assertEqual(self.status(self.pair),before)

    def test_missing_auth_owner_rolls_back_both_roles_members_and_bindings(self):
        missing = replace(self.pair,owner=str(uuid4()))
        self.denied(self.db.issue_pair(missing,check=False),'23503')
        self.assert_absent(missing)

    def test_late_issue_failure_rolls_back_complete_pair(self):
        source = self.db.issue_source(self.pair).replace('-- AFTER_ISSUANCE','SELECT 1/0;')
        self.denied(self.db.issue_pair(self.pair,source=source,check=False),'22012')
        self.assert_absent(self.pair)

    def test_pair_is_unpublished_before_commit_and_concurrent_collision_is_bounded(self):
        marker = 'issuer-publish-' + uuid4().hex
        source = f"SET application_name='{marker}';\n" + self.db.issue_source(self.pair).replace('-- AFTER_ISSUANCE','SELECT pg_sleep(2);')
        held = self.db.begin_sql(source,timeout=6)
        self.barrier(marker)
        self.assert_absent(self.pair)
        started = time.monotonic()
        self.denied(self.db.issue_pair(self.pair,check=False),'55P03')
        self.assertLess(time.monotonic()-started,1.5)
        held.wait()
        self.assertEqual(self.bind_count(self.pair),2)
        for name,password in zip(self.pair.names,self.pair.passwords):
            self.db.write_private(name+'.pgpass',f'*:5432:postgres:{name}:{password}\n')
        self.db.native(self.pair.names[0],'economic','SELECT 1;')

    def test_superuser_and_api_issuers_are_denied_without_mutation(self):
        source = self.db.issue_source(self.pair)
        for role in (installer_fixture.ADMIN,'anon','authenticated','service_role','authenticator'):
            self.denied(self.db.private_sql(source,role=role),'limited_native_issuer_required')
            self.assert_absent(self.pair)

    def test_missing_rehearsal_marker_is_denied(self):
        source = self.db.issue_source(self.pair).removeprefix(fixture.MARKER)
        self.denied(self.db.issue_pair(self.pair,source=source,check=False),'isolated_native_issuer_required')
        self.assert_absent(self.pair)

    def test_unexpected_registry_column_grant_is_rejected_and_preserved(self):
        self.admin('GRANT SELECT(principal_name) ON vn_access.bindings TO authenticated;')
        try:
            self.denied(self.db.issue_pair(self.pair,check=False),'native_issuer_catalog_requires_review')
            self.assert_absent(self.pair)
            self.assertEqual(self.admin("SELECT has_column_privilege('authenticated','vn_access.bindings','principal_name','SELECT');").stdout.strip(),'t')
        finally:
            self.admin('REVOKE SELECT(principal_name) ON vn_access.bindings FROM authenticated;')

    def test_pair_revocation_denies_existing_session_and_new_logins(self):
        self.db.issue_pair(self.pair)
        marker = 'issuer-open-' + uuid4().hex
        source = f"SET application_name='{marker}'; SELECT pg_sleep(2); SELECT vn_durability.get_command('{self.owner}','{self.run}','{uuid4()}');"
        open_session = self.db.begin_native(self.pair.names[0],'economic',source,timeout=6)
        self.barrier(marker)
        self.revoke(self.pair)
        self.denied(open_session.wait(check=False),'principal_denied')
        for index,capability in enumerate(('economic','relay')):
            self.assertNotEqual(self.db.native(self.pair.names[index],capability,'SELECT 1;',check=False).returncode,0)
        self.assertTrue(all(item['revoked'] and not item['login'] for item in self.status(self.pair)))

    def test_repeated_revocation_preserves_first_timestamp_and_binding(self):
        self.db.issue_pair(self.pair)
        scope = fixture.Scope(self.pair.owner,self.pair.run,self.pair.names,self.pair.issuances)
        self.revoke(scope,oids=self.db.oids(self.pair))
        before = self.status(self.pair)
        self.revoke(self.pair)
        self.assertEqual(self.status(self.pair),before)
        self.assertEqual(self.bind_count(self.pair),2)

    def test_revocation_refuses_wrong_owner_run_oid_or_missing_pair_atomically(self):
        self.db.issue_pair(self.pair)
        before = self.status(self.pair)
        oids = self.db.oids(self.pair)
        for pair,ids,message in ((replace(self.pair,owner=self.other),oids,'native_revocation_binding_changed'),
                                (replace(self.pair,run=str(uuid4())),oids,'native_revocation_binding_changed'),
                                (self.pair,tuple(reversed(oids)),'native_revocation_identity_changed'),
                                (replace(self.pair,issuances=(self.pair.issuances[0],str(uuid4()))),oids,'native_revocation_pair_missing')):
            self.denied(self.revoke(pair,oids=ids,check=False),message)
            self.assertEqual(self.status(self.pair),before)

    def test_revocation_lock_timeout_is_failure_without_partial_revocation(self):
        self.pair = replace(self.pair,names=('vn_native_2'+uuid4().hex[1:],'vn_native_1'+uuid4().hex[1:]))
        self.db.issue_pair(self.pair)
        command,_ = self.create(self.pair)
        marker = 'issuer-held-' + uuid4().hex
        source = (f"SET application_name='{marker}'; BEGIN; SELECT vn_durability.get_command('{self.owner}','{self.run}','{command}'); "
                  'SELECT pg_sleep(2); COMMIT;')
        held = self.db.begin_native(self.pair.names[0],'economic',source,timeout=6)
        self.barrier(marker)
        before = self.status(self.pair)
        started = time.monotonic()
        self.denied(self.revoke(self.pair,check=False),'55P03')
        self.assertLess(time.monotonic()-started,1.5)
        self.assertEqual(self.status(self.pair),before)
        held.wait()
        self.revoke(self.pair)
        self.assertTrue(all(item['revoked'] and not item['login'] for item in self.status(self.pair)))

    def test_late_revoke_failure_restores_active_pair(self):
        self.db.issue_pair(self.pair)
        before = self.status(self.pair)
        source = self.db.revoke_source(self.pair,self.db.oids(self.pair)).replace('-- AFTER_REVOCATION','SELECT 1/0;')
        self.denied(self.revoke(self.pair,source=source,check=False),'22012')
        self.assertEqual(self.status(self.pair),before)
        self.db.native(self.pair.names[0],'economic','SELECT 1;')

    def test_rotation_retains_original_command_and_never_repeats_economics(self):
        self.db.issue_pair(self.pair)
        command, original = self.create(self.pair)
        replacement = fixture.Pair.new(self.owner,self.run)
        self.db.issue_pair(replacement)
        self.revoke(self.pair)
        evidence = json.loads(self.db.native(replacement.names[0],'economic',
            f"SELECT vn_durability.get_command('{self.owner}','{self.run}','{command}');").stdout)
        self.assertEqual(evidence['response'],original)
        self.assertEqual(self.admin(f"SELECT count(*) FROM vn_durability.commands WHERE run_id='{self.run}';").stdout.strip(),'1')

    def test_dropped_and_recreated_name_cannot_be_revoked_as_old_oid(self):
        self.db.issue_pair(self.pair)
        oids = self.db.oids(self.pair)
        name = self.pair.names[0]
        self.admin(f'DROP OWNED BY {name}; DROP ROLE {name}; CREATE ROLE {name} LOGIN NOINHERIT CONNECTION LIMIT 2;')
        fresh = self.admin(f"SELECT oid FROM pg_roles WHERE rolname='{name}';").stdout.strip()
        self.assertNotEqual(int(fresh),oids[0])
        self.denied(self.revoke(self.pair,oids=oids,check=False),'native_revocation_identity_changed')
        self.assertEqual(self.admin(f"SELECT rolcanlogin FROM pg_roles WHERE oid={fresh};").stdout.strip(),'t')
        self.assertEqual(self.admin(f"SELECT count(*) FROM vn_access.bindings WHERE run_id='{self.run}' AND revoked_at IS NOT NULL;").stdout.strip(),'0')

    def test_role_replacement_during_revocation_gap_rolls_back_wrong_target(self):
        self.db.issue_pair(self.pair)
        oids = self.db.oids(self.pair)
        marker = 'issuer-role-gap-' + uuid4().hex
        source = f"SET application_name='{marker}';\n" + self.db.revoke_source(self.pair,oids).replace(
            '-- BEFORE_ROLE_DISABLE','PERFORM pg_sleep(2);')
        held = self.db.begin_sql(source,timeout=6)
        self.barrier(marker)
        name = self.pair.names[0]
        self.admin(f'DROP OWNED BY {name}; DROP ROLE {name};')
        # Actual limited postgres creates this distinct, independently committed
        # role and can administer it. The in-flight old-OID revocation must not
        # commit NOLOGIN on it even though its name matches the requested name.
        self.db.sql(f'CREATE ROLE {name} LOGIN NOINHERIT CONNECTION LIMIT 2;')
        fresh = self.db.scalar(f"SELECT oid FROM pg_roles WHERE rolname='{name}';")
        self.assertNotEqual(int(fresh),oids[0])
        self.denied(held.wait(check=False),'native_revocation_identity_changed')
        self.assertEqual(self.db.scalar(f"SELECT rolcanlogin FROM pg_roles WHERE oid={fresh};"),'t')
        self.assertEqual(self.admin(f"SELECT count(*) FROM vn_access.bindings WHERE run_id='{self.run}' AND revoked_at IS NOT NULL;").stdout.strip(),'0')
        self.assertEqual(self.db.scalar(f"SELECT rolcanlogin FROM pg_roles WHERE rolname='{self.pair.names[1]}';"),'t')

    def test_role_ddl_lock_prevents_replacement_after_final_check(self):
        self.db.issue_pair(self.pair)
        marker = 'issuer-role-lock-' + uuid4().hex
        source = f"SET application_name='{marker}';\n" + self.db.revoke_source(self.pair,self.db.oids(self.pair)).replace(
            '-- AFTER_REVOCATION','SELECT pg_sleep(2);')
        held = self.db.begin_sql(source,timeout=6)
        self.barrier(marker)
        name = self.pair.names[0]
        result = self.db.private_sql(f'BEGIN; SET LOCAL lock_timeout=\'250ms\'; DROP ROLE {name}; COMMIT;')
        self.denied(result,'55P03')
        held.wait()
        self.assertEqual(self.bind_count(self.pair),2)
        self.assertTrue(all(item['revoked'] and not item['login'] for item in self.status(self.pair)))

    def test_lost_issuance_reply_retains_exact_pair_and_refuses_new_submission(self):
        marker = 'issuer-lost-reply-' + uuid4().hex
        source = f"SET application_name='{marker}';\n" + self.db.issue_source(self.pair) + '\nSELECT pg_sleep(2);'
        held = self.db.begin_sql(source,timeout=6)
        self.barrier(marker)  # The explicit COMMIT precedes this observed sleep.
        self.assertEqual(self.bind_count(self.pair),2)
        before = self.status(self.pair)
        held.close()  # Only this owned client loses its reply; no compensating DDL.
        self.denied(self.db.issue_pair(self.pair,check=False),'native_issuer_fresh_names_required')
        self.assertEqual(self.status(self.pair),before)
        self.assertEqual(self.bind_count(self.pair),2)
