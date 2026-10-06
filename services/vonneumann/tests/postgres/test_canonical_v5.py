"""Canonical v5 admission, exact manifest, actual-role permission and rollback."""
from __future__ import annotations
from copy import deepcopy
import json
import os
import time
import unittest
from uuid import uuid4

from tests.postgres import canonical_fixture as canonical
from tests.postgres import harness, installer_fixture
from tests.postgres.test_command_adapter import literal
from tests.postgres.test_provider_contract import ProviderContractTests as _ProviderTests
from tests.postgres.test_provider_controller import ProviderControllerSqlTests as _ControllerTests

# Imports are aliases, and loader below excludes the reference classes so normal
# discovery doesn't inadvertently run their laboratory suites again.

def load_tests(loader, tests, pattern):
    result = unittest.TestSuite()
    for cls in (CanonicalProviderTests, CanonicalControllerTests, CanonicalBoundaryTests):
        result.addTests(loader.loadTestsFromTestCase(cls))
    return result


@unittest.skipUnless(os.environ.get(harness.OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class CanonicalProviderTests(_ProviderTests):
    @classmethod
    def setUpClass(cls):
        cls.db = canonical.start(cls)


@unittest.skipUnless(os.environ.get(harness.OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class CanonicalControllerTests(_ControllerTests):
    @classmethod
    def setUpClass(cls):
        cls.db = canonical.start(cls)

    async def publish(self, event):
        await super().publish(event)
        self.db.scalar('SELECT vn_read.accept_event('+','.join((literal(event['owner_id']),
            literal(event['run_id']),literal(event['command_id']),str(event['event_index'])))+');',role='vn_relay')


@unittest.skipUnless(os.environ.get(harness.OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class CanonicalBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = harness.IsolatedPostgres()
        cls.addClassCleanup(cls.db.close)
        cls.db.start()
        cls.db.sql('CREATE ROLE vn_test_admin LOGIN SUPERUSER;')
        cls.db.sql(installer_fixture.HOSTED_BOOTSTRAP,role=installer_fixture.ADMIN)
        cls.db.sql('''CREATE ROLE vn_test_economic_client LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
CREATE ROLE vn_test_relay_client LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;''',role=installer_fixture.ADMIN)
        cls.db.sql('''CREATE TABLE public.canonical_unrelated(id int PRIMARY KEY);
INSERT INTO public.canonical_unrelated VALUES(42);
GRANT SELECT,UPDATE ON public.canonical_unrelated TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon,authenticated,service_role;
''')

    def read(self, source, *, role=installer_fixture.ADMIN, **options):
        return self.db.scalar(source,role=role,**options)

    def admin(self, source, **options):
        return self.db.sql(source,role=installer_fixture.ADMIN,**options)

    def setUp(self):
        self.admin('''DROP SCHEMA IF EXISTS vn_read,vn_projection,vn_durability,vn_identity CASCADE;
DO $$ DECLARE r text; BEGIN FOREACH r IN ARRAY ARRAY['vn_contract_owner','vn_economic','vn_relay'] LOOP
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN EXECUTE format('DROP OWNED BY %I',r); EXECUTE format('DROP ROLE %I',r); END IF;
END LOOP; END $$;''')
        self.before = self.unchanged()

    def unchanged(self):
        return self.read('''SELECT jsonb_build_object(
 'auth_schema',(SELECT to_jsonb(n) FROM pg_namespace n WHERE nspname='auth'),
 'auth_table',(SELECT jsonb_build_object('owner',relowner,'acl',relacl) FROM pg_class WHERE oid='auth.users'::regclass),
 'auth_uid',(SELECT jsonb_build_object('owner',proowner,'acl',proacl,'body',prosrc) FROM pg_proc WHERE oid='auth.uid()'::regprocedure),
 'defaults',(SELECT coalesce(jsonb_agg(to_jsonb(d) ORDER BY oid),'[]') FROM pg_default_acl d WHERE defaclrole='postgres'::regrole),
 'memberships',(SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY oid),'[]') FROM pg_auth_members m WHERE member IN
  (SELECT oid FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role','authenticator'))),
 'unrelated_acl',(SELECT relacl::text FROM pg_class WHERE oid='public.canonical_unrelated'::regclass),
 'unrelated_rows',(SELECT jsonb_agg(to_jsonb(t)) FROM public.canonical_unrelated t));''',role=installer_fixture.ADMIN)

    def install(self, *, suffix='', check=True):
        source=canonical.package()
        if suffix:
            source=source.rsplit('COMMIT;',1)[0]+suffix+'\nCOMMIT;\n'
        return self.db.sql(source,check=check,timeout=30)

    def as_role(self, role, source, *, check=True):
        if role in ('vn_economic','vn_relay'):
            client='vn_test_economic_client' if role=='vn_economic' else 'vn_test_relay_client'
            self.admin('GRANT '+role+' TO '+client+' WITH ADMIN FALSE,INHERIT FALSE,SET TRUE;')
            return self.db.sql('SET ROLE '+role+';\n'+source,role=client,check=check)
        return self.db.sql(source,role=role,check=check)

    def assert_uninstalled(self):
        self.assertEqual(self.read("SELECT NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname IN "
            "('vn_identity','vn_durability','vn_projection','vn_read')) AND NOT EXISTS(SELECT 1 FROM pg_roles "
            "WHERE rolname IN ('vn_contract_owner','vn_economic','vn_relay'));"),'t')

    def bootstrap(self, *, install=True):
        from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
        from vonneumann.core import provider_lifecycle as core
        from tests.postgres import test_provider_contract as provider
        if install: self.install()
        owner,run,worker,command=(str(uuid4()) for _ in range(4))
        self.admin('INSERT INTO auth.users VALUES('+literal(owner)+');')
        config=core.ProviderLifecycleConfig(ExactLifecycleConfig('genetic_algorithm',owner,run,asset='SOL/USD'),str(uuid4()))
        def create(configuration):
            return 'SELECT vn_durability.create_run('+','.join((literal(owner),literal(run),literal(worker),literal(command),
                literal(json.dumps(configuration))+'::jsonb',literal(config.initial_cash),'120'))+');'
        self.as_role('vn_economic',create(config.run_configuration()))
        now,mono=time.time(),time.monotonic()
        candidate=core.bootstrap(config,provider.seed_history(now,mono),provider.decision_inputs(now,mono))
        payload={'version':5,'operations':candidate.operations,'transition':candidate.transition}
        commit_id=str(uuid4())
        def batch(value):
            return 'SELECT vn_durability.commit_command('+','.join((literal(owner),literal(run),literal(worker),'1','1',literal(commit_id),literal(json.dumps(value))+'::jsonb'))+');'
        self.as_role('vn_economic',batch(payload))
        self.candidate,self.worker=candidate,worker
        return owner,run,create,batch,payload,commit_id

    def test_installer_is_non_super_and_auth_unrelated_defaults_preserved(self):
        self.install()
        self.assertEqual(self.read('SELECT current_user=session_user AND NOT rolsuper FROM pg_roles WHERE rolname=current_user;',role='postgres'),'t')
        self.assertEqual(self.unchanged(),self.before)
        self.assertEqual(self.read("SELECT count(*) FROM pg_roles WHERE rolname IN ('vn_economic','vn_relay') AND NOT rolcanlogin AND NOT rolinherit AND NOT rolbypassrls;"),'2')

    def test_exact_function_body_signature_and_capability_manifest_matches_catalog(self):
        self.install()
        manifest=json.loads((canonical.DIRECTORY/'manifest.json').read_text())
        actual=json.loads(self.read('''SELECT jsonb_agg(jsonb_build_object('signature',n.nspname||'.'||p.proname||'('||
 replace(oidvectortypes(p.proargtypes),', ', ',')||')','body_sha256',encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),
 'security_definer',p.prosecdef) ORDER BY n.nspname,p.proname) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname IN ('vn_identity','vn_durability','vn_projection','vn_read');'''))
        expected=sorted([{k:m[k] for k in ('signature','body_sha256','security_definer')} for m in manifest['functions']],key=lambda m:m['signature'])
        self.assertEqual(actual,expected)
        for m in manifest['functions']:
            for role in ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay'):
                observed=self.read('SELECT has_function_privilege('+literal(role)+','+literal(m['signature'])+",'EXECUTE');")
                self.assertEqual(observed,'t' if role==m['execute_role'] else 'f')
        for kind,query in (('tables',"SELECT n.nspname||'.'||c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('vn_durability','vn_projection') AND c.relkind='r' ORDER BY 1;"),
                           ('indexes',"SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('vn_durability','vn_projection') AND c.relkind='i' AND NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conindid=c.oid) ORDER BY 1;"),
                           ('triggers',"SELECT tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('vn_durability','vn_projection') AND NOT t.tgisinternal ORDER BY 1;")):
            self.assertEqual(self.read(query).splitlines(),manifest[kind])

    def test_v1_through_v4_missing_string_and_null_versions_rejected_without_effects(self):
        owner,run,create,batch,payload,_=self.bootstrap()
        baseline=self.read('SELECT revision FROM vn_durability.runs WHERE id='+literal(run)+';')
        for version in (None,1,2,3,4,'5',True):
            altered=deepcopy(payload);altered['version']=version
            self.assertIn('invalid_payload',self.as_role('vn_economic',batch(altered),check=False).stderr)
            configuration=json.loads(self.read('SELECT config FROM vn_durability.runs WHERE id='+literal(run)+';',role=installer_fixture.ADMIN))
            configuration['durability_contract_version']=version
            self.assertIn('invalid_provider_config',self.as_role('vn_economic',create(configuration),check=False).stderr)
        self.assertEqual(self.read('SELECT revision FROM vn_durability.runs WHERE id='+literal(run)+';'),baseline)
        rejected=self.admin('UPDATE vn_durability.runs SET command_version=4 WHERE id='+literal(run)+';',check=False)
        self.assertIn('23514',rejected.stderr)

    def test_economic_relay_and_service_cannot_cross_capabilities_or_write_raw_tables(self):
        self.install()
        manifest=json.loads((canonical.DIRECTORY/'manifest.json').read_text())
        for role in ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay'):
            for table in manifest['tables']:
                for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN'):
                    self.assertEqual(self.read('SELECT has_table_privilege('+literal(role)+','+literal(table)+','+literal(privilege)+');'),'f')
            for statement in ('SET ROLE vn_contract_owner;', 'SELECT * FROM vn_durability.runs;',
                              'CREATE TABLE vn_read.unauthorized(id int);','SELECT vn_durability.money(\'"1"\'::jsonb);'):
                self.assertNotEqual(self.as_role(role,statement,check=False).returncode,0)
        self.assertNotEqual(self.as_role('vn_economic','SELECT vn_read.accept_event(NULL,NULL,NULL,0);',check=False).returncode,0)
        self.assertNotEqual(self.as_role('vn_relay',"SELECT vn_durability.create_run(NULL,NULL,NULL,NULL,'{}','100',30);",check=False).returncode,0)

    def test_owner_reads_relay_dedup_ack_prefix_and_archive_idempotence(self):
        from vonneumann.core import provider_lifecycle as core
        from tests.postgres.test_provider_contract import decision_inputs
        owner,run,_,_,_,command=self.bootstrap()
        page='SELECT vn_read.page('+literal(run)+",'probes');"
        self.assertEqual(len(json.loads(self.read('SET request.jwt.claim.sub='+literal(owner)+';'+page,role='authenticated'))['records']),8)
        for foreign in (str(uuid4()),None):
            denied=self.db.sql('SET request.jwt.claim.sub='+literal(foreign or '')+';'+page,role='authenticated',check=False)
            self.assertNotEqual(denied.returncode,0)
        event_args=','.join((literal(owner),literal(run),literal(command),'0'))
        ack='SELECT vn_durability.acknowledge_event('+event_args+');'
        self.assertIn('durable_relay_acceptance_required',self.as_role('vn_relay',ack,check=False).stderr)
        accept='SELECT vn_read.accept_event('+event_args+');'
        first=self.as_role('vn_relay',accept).stdout
        self.assertEqual(self.as_role('vn_relay',accept).stdout,first)
        self.as_role('vn_relay',ack)
        stopped=core.prepare_control(self.candidate.state,'stop',decision_inputs())
        stop_payload={'version':5,'operations':stopped.operations,'transition':stopped.transition}
        self.as_role('vn_economic','SELECT vn_durability.commit_command('+','.join((literal(owner),literal(run),literal(self.worker),'1','2',literal(str(uuid4())),literal(json.dumps(stop_payload))+'::jsonb'))+');')
        archive='SELECT vn_read.archive_run('+','.join((literal(run),'3',literal(str(uuid4()))))+');'
        first=self.read('SET request.jwt.claim.sub='+literal(owner)+';'+archive,role='authenticated')
        receipt=json.loads(first)
        self.assertTrue(receipt['archived'])
        self.assertTrue(receipt['requires_reconciliation'])
        self.assertEqual(self.read('SET request.jwt.claim.sub='+literal(owner)+';'+archive,role='authenticated'),first)
        self.assertEqual(self.read('SELECT count(*) FROM vn_durability.commands WHERE run_id='+literal(run)+';'),'3')

    def test_late_failure_rolls_back_all_schemas_and_roles(self):
        failed=self.install(suffix='SELECT 1/0;',check=False)
        self.assertIn('22012',failed.stderr)
        self.assert_uninstalled()
        self.assertEqual(self.unchanged(),self.before)

    def test_existing_capability_role_refused_without_modification(self):
        self.db.sql('CREATE ROLE vn_relay NOLOGIN;')
        before=self.read("SELECT row_to_json(r) FROM pg_roles r WHERE rolname='vn_relay';")
        failed=self.install(check=False)
        self.assertIn('fresh_installer_rehearsal_required',failed.stderr)
        self.assertEqual(self.read("SELECT row_to_json(r) FROM pg_roles r WHERE rolname='vn_relay';"),before)
        self.assertEqual(self.unchanged(),self.before)

    def test_extra_global_table_default_grant_is_rejected_atomically(self):
        self.admin('CREATE ROLE vn_test_default_recipient NOLOGIN;')
        self.db.sql('ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO vn_test_default_recipient;')
        try:
            failed=self.install(check=False)
            self.assertIn('canonical_table_postcondition_failed',failed.stderr)
            self.assert_uninstalled()
        finally:
            self.db.sql('ALTER DEFAULT PRIVILEGES REVOKE SELECT ON TABLES FROM vn_test_default_recipient;')
            self.admin('DROP ROLE vn_test_default_recipient;')
        self.assertEqual(self.unchanged(),self.before)

    def test_auth_fk_lock_timeout_rolls_back_installation(self):
        holder=self.db.begin_sql('BEGIN; LOCK auth.users IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep(2); ROLLBACK;',role=installer_fixture.ADMIN,timeout=5)
        self.db.wait_until("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE relation='auth.users'::regclass AND mode='AccessExclusiveLock' AND granted);")
        failed=self.install(check=False)
        self.assertIn('55P03',failed.stderr)
        holder.wait()
        self.assert_uninstalled()
        self.assertEqual(self.unchanged(),self.before)

    def test_late_projection_failure_preserves_entire_original_command(self):
        self.install()
        self.admin("CREATE FUNCTION public.canonical_projection_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'canonical_late_failure'; END $$; "
                   'CREATE TRIGGER canonical_late_failure AFTER INSERT ON vn_projection.probes FOR EACH ROW EXECUTE FUNCTION public.canonical_projection_failure();')
        try:
            with self.assertRaises(harness.SqlFailure) as failure:
                self.bootstrap(install=False)
            self.assertIn('canonical_late_failure',str(failure.exception))
            self.assertEqual(self.read('SELECT count(*) FROM vn_durability.commands;'),'1')
            self.assertEqual(self.read('SELECT count(*) FROM vn_durability.accounts;'),'0')
            self.assertEqual(self.read('SELECT count(*) FROM vn_durability.outbox_events;'),'0')
            self.assertEqual(self.read('SELECT count(*) FROM vn_projection.probes;'),'0')
            self.assertEqual(self.read('SELECT engine_state IS NULL AND revision=1 FROM vn_durability.runs;'),'t')
        finally:
            self.admin('DROP TRIGGER canonical_late_failure ON vn_projection.probes; DROP FUNCTION public.canonical_projection_failure();')
