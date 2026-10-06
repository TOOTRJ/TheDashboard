"""Real TLS/SCRAM identities, owner/run isolation and credential lifecycle."""
from __future__ import annotations
import json
import os
import time
import unittest
from uuid import uuid4

from tests.postgres import harness, installer_fixture, session_auth_fixture as fixture
from tests.postgres.test_command_adapter import literal
from tests.postgres.test_decimal_lineage_contract import document
from tests.postgres.test_provider_contract import seed_history, decision_inputs
from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
from vonneumann.core import provider_lifecycle as core


@unittest.skipUnless(os.environ.get(harness.OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class NativeSessionAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=fixture.start(cls)

    def setUp(self):
        self.owner,self.other,self.run,self.worker,self.command=(str(uuid4()) for _ in range(5))
        self.admin(f"INSERT INTO auth.users VALUES ('{self.owner}'),('{self.other}');")
        self.economic=self.db.issue(self.owner,self.run,'economic')
        self.relay=self.db.issue(self.owner,self.run,'relay')
        self.config=core.ProviderLifecycleConfig(ExactLifecycleConfig('genetic_algorithm',self.owner,self.run,asset='SOL/USD'),str(uuid4()))

    def admin(self,sql,**options):
        return self.db.sql(sql,role=installer_fixture.ADMIN,**options)

    def call(self,sql,*,role=None,capability='economic',**options):
        return self.db.native(role or self.economic,capability,sql,**options)

    def create_sql(self,owner=None,run=None):
        return 'SELECT vn_durability.create_run('+','.join((literal(owner or self.owner),literal(run or self.run),
            literal(self.worker),literal(self.command),document(self.config.run_configuration()),literal(self.config.initial_cash),'120'))+');'

    def get_sql(self,owner=None,run=None,command=None):
        return 'SELECT vn_durability.get_command('+','.join(map(literal,(owner or self.owner,run or self.run,command or self.command)))+');'

    def heartbeat_sql(self):
        return f"SELECT vn_durability.heartbeat('{self.owner}','{self.run}','{self.worker}',1,120);"

    def denied(self,sql,**options):
        result=self.call(sql,check=False,**options)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('42501',result.stderr)
        return result

    def snapshot(self):
        return self.admin("SELECT jsonb_build_array("+','.join(
            "(SELECT md5(coalesce(string_agg(to_jsonb(t)::text,',' ORDER BY to_jsonb(t)::text),'')) FROM "+table+
            " t WHERE "+key+"='"+self.run+"')" for table,key in (
                ('vn_durability.runs','id'),('vn_durability.commands','run_id'),('vn_durability.accounts','run_id'),
                ('vn_durability.outbox_events','run_id'),('vn_projection.runs','run_id'),
                ('vn_projection.relay_events','run_id')))+');').stdout.strip()

    def revoke(self,role):
        return self.db.sql(f"SET ROLE vn_contract_owner; UPDATE vn_access.bindings SET revoked_at=clock_timestamp() "
            f"WHERE principal_name='{role}';")

    def barrier(self,sql):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if self.admin(sql).stdout.strip()=='t':
                return
            time.sleep(.03)
        self.fail('Owned native SQL concurrency barrier did not appear')

    def test_actual_scram_tls_identity_survives_set_role_and_definer(self):
        result=self.call('SELECT session_user,system_user,current_user; RESET ROLE; SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid();')
        self.assertEqual(result.stdout.strip(),f'{self.economic}|scram-sha-256:{self.economic}|vn_economic\nt')
        self.call(self.create_sql())
        result=json.loads(self.call(self.get_sql()).stdout)
        self.assertEqual(result['response']['revision'],1)
        self.assertEqual(result['request']['owner_id'],self.owner)

    def test_bad_password_hostname_and_plaintext_are_rejected_before_sql(self):
        self.db.write_private('wrong.pgpass',f'*:5432:postgres:{self.economic}:incorrect-fixture-password\n')
        for options,expected in (({'password_file':'wrong.pgpass'},'password authentication failed'),
                                 ({'host':'wrong.example'},'does not match host name'),
                                 ({'root':'wrong-root.crt'},'certificate verify failed'),
                                 ({'sslmode':'disable'},'rejects connection')):
            with self.subTest(options=options):
                result=self.call(self.create_sql(),check=False,**options)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(expected,result.stderr)
        self.assertEqual(self.admin(f"SELECT count(*) FROM vn_durability.runs WHERE id='{self.run}';").stdout.strip(),'0')

    def test_owner_and_run_cannot_be_spoofed_even_with_forged_jwt_claims(self):
        self.call(self.create_sql())
        before=self.snapshot()
        self.denied(self.get_sql(owner=self.other))
        self.denied(self.get_sql(run=str(uuid4())))
        self.denied(f"SET request.jwt.claim.sub='{self.other}'; SET request.jwt.claims='{{\"sub\":\"{self.other}\",\"role\":\"service_role\"}}'; "+self.create_sql(owner=self.other))
        self.assertEqual(self.snapshot(),before)

    def test_all_eight_entrypoints_reject_unbound_run_before_payload(self):
        owner,run=literal(self.owner),literal(str(uuid4()))
        economic=[f"create_run({owner},{run},NULL,NULL,'{{}}','100',30)",
            f'heartbeat({owner},{run},NULL,1,30)',f"commit_command({owner},{run},NULL,1,1,NULL,'{{}}')",
            f'get_command({owner},{run},NULL)',f'interrupt_expired({owner},{run},1,NULL)']
        relay=[('vn_durability',f'read_outbox({owner},{run},1,1,1024)'),
               ('vn_durability',f'acknowledge_event({owner},{run},NULL,0)'),('vn_read',f'accept_event({owner},{run},NULL,0)')]
        for call in economic:
            self.denied('SELECT vn_durability.'+call+';')
        for namespace,call in relay:
            self.denied('SELECT '+namespace+'.'+call+';',role=self.relay,capability='relay')

    def test_capabilities_raw_binding_and_session_impersonation_are_denied(self):
        for sql in ('SET ROLE vn_contract_owner;', 'SET ROLE vn_relay;', 'SET ROLE authenticated;',
            f'SET SESSION AUTHORIZATION {self.relay};', 'SELECT * FROM vn_access.bindings;',
            "SELECT vn_access.require_actor(NULL,NULL,'economic','create_run');",
            'SELECT * FROM vn_durability.runs;', 'DELETE FROM vn_access.bindings;',
            'SELECT vn_read.accept_event(NULL,NULL,NULL,0);'):
            with self.subTest(sql=sql): self.denied(sql)
        self.denied(self.create_sql(),role=self.relay,capability='relay')

    def test_api_service_and_trust_socket_cannot_imitate_authenticated_worker(self):
        for role in ('anon','authenticated','service_role','authenticator'):
            result=self.db.sql(self.create_sql(),role=role,check=False)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('42501',result.stderr)
        result=self.db.sql('SET ROLE vn_economic; '+self.create_sql(),role=self.economic,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('principal_denied',result.stderr)

    def test_not_before_and_role_attribute_or_membership_drift_fail_closed(self):
        future=self.db.issue(self.owner,self.run,'economic',delay=20)
        self.denied(self.create_sql(),role=future)
        for mutation,restore in ((f'ALTER ROLE {self.economic} INHERIT;',f'ALTER ROLE {self.economic} NOINHERIT;'),
            (f'ALTER ROLE {self.economic} CONNECTION LIMIT -1;',f'ALTER ROLE {self.economic} CONNECTION LIMIT 2;'),
            (f'GRANT vn_relay TO {self.economic} WITH ADMIN FALSE,INHERIT FALSE,SET TRUE;',f'REVOKE vn_relay FROM {self.economic};')):
            self.admin(mutation)
            self.denied(self.create_sql())
            self.admin(restore)
        self.call(self.create_sql())

    def test_expired_write_ticket_keeps_bounded_original_command_readback_only(self):
        role=self.db.issue(self.owner,self.run,'economic',expires=.8,recovery=60)
        self.call(self.create_sql(),role=role)
        self.admin('SELECT pg_sleep(1);')
        self.denied(self.create_sql(),role=role) # Replay is not fresh authority.
        self.denied(self.heartbeat_sql(),role=role)
        evidence=json.loads(self.call(self.get_sql(),role=role).stdout)
        self.assertEqual(evidence['response']['revision'],1)

    def test_existing_connection_checks_password_and_binding_deadlines(self):
        role=self.db.issue(self.owner,self.run,'economic',expires=.5,recovery=1.5)
        session=self.db.begin_native(role,'economic','SELECT pg_sleep(2); '+self.create_sql(),timeout=6)
        result=session.wait(check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('principal_denied',result.stderr)
        self.assertNotEqual(self.call(self.get_sql(),role=role,check=False).returncode,0)

    def test_revocation_is_observed_by_already_open_connection(self):
        marker='native-revoke-'+uuid4().hex
        session=self.db.begin_native(self.economic,'economic',f"SET application_name='{marker}'; SELECT pg_sleep(2); "+self.create_sql(),timeout=6)
        self.barrier(f"SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='{marker}' AND wait_event='PgSleep');")
        self.revoke(self.economic)
        result=session.wait(check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('principal_denied',result.stderr)

    def test_revocation_serializes_after_admitted_transaction_then_blocks_next(self):
        self.call(self.create_sql())
        marker='native-lock-'+uuid4().hex
        session=self.db.begin_native(self.economic,'economic',f"SET application_name='{marker}'; BEGIN; "+self.get_sql()+' SELECT pg_sleep(2); COMMIT;',timeout=6)
        self.barrier(f"SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='{marker}' AND wait_event='PgSleep');")
        revoke=self.db.begin_sql(f"SET ROLE vn_contract_owner; UPDATE vn_access.bindings SET revoked_at=clock_timestamp() WHERE principal_name='{self.economic}';",timeout=6)
        self.barrier("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE 'UPDATE vn_access.bindings%');")
        session.wait(); revoke.wait()
        self.denied(self.get_sql())

    def test_rotation_uses_new_principal_and_resolves_same_original_command(self):
        original=json.loads(self.call(self.create_sql()).stdout)
        replacement=self.db.issue(self.owner,self.run,'economic')
        self.revoke(self.economic)
        self.denied(self.create_sql())
        self.assertEqual(json.loads(self.call(self.get_sql(),role=replacement).stdout)['response'],original)
        self.assertEqual(json.loads(self.call(self.create_sql(),role=replacement).stdout),original)
        self.assertEqual(self.admin(f"SELECT count(*) FROM vn_durability.commands WHERE run_id='{self.run}';").stdout.strip(),'1')

    def test_drop_and_recreate_same_role_name_cannot_reuse_binding_oid(self):
        old_oid=self.admin(f"SELECT oid FROM pg_roles WHERE rolname='{self.economic}';").stdout.strip()
        self.admin(f"DROP OWNED BY {self.economic}; DROP ROLE {self.economic};")
        # Reuse the fixture password file without retrieving its contents.
        password='fresh-synthetic-password'
        self.admin(f"CREATE ROLE {self.economic} LOGIN NOINHERIT CONNECTION LIMIT 2 PASSWORD '{password}' VALID UNTIL '2099-01-01'; "
                   f'GRANT vn_economic TO {self.economic} WITH ADMIN FALSE,INHERIT FALSE,SET TRUE;')
        self.db.write_private(self.economic+'.pgpass',f'*:5432:postgres:{self.economic}:{password}\n')
        self.assertNotEqual(self.admin(f"SELECT oid FROM pg_roles WHERE rolname='{self.economic}';").stdout.strip(),old_oid)
        self.denied(self.create_sql())

    def test_scope_immutable_and_revocation_one_way(self):
        for change in (f"owner_id='{self.other}'", "expires_at=expires_at+interval '1 second'", "revoked_at=clock_timestamp()+interval '1 hour'"):
            result=self.db.sql(f"SET ROLE vn_contract_owner; UPDATE vn_access.bindings SET {change} WHERE principal_name='{self.economic}';",check=False)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('binding_immutable',result.stderr)
        self.revoke(self.economic)
        result=self.db.sql(f"SET ROLE vn_contract_owner; UPDATE vn_access.bindings SET revoked_at=NULL WHERE principal_name='{self.economic}';",check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('binding_immutable',result.stderr)

    def test_repeatable_read_cannot_keep_a_pre_revocation_authority_snapshot(self):
        self.call(self.create_sql())
        marker='native-snapshot-'+uuid4().hex
        session=self.db.begin_native(self.economic,'economic',f"SET application_name='{marker}'; BEGIN ISOLATION LEVEL REPEATABLE READ; "
            'SELECT count(*) FROM pg_roles; SELECT pg_sleep(2); '+self.get_sql()+' COMMIT;',timeout=6)
        self.barrier(f"SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='{marker}' AND wait_event='PgSleep');")
        self.revoke(self.economic)
        result=session.wait(check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertTrue('40001' in result.stderr or 'principal_denied' in result.stderr)

    def test_expiry_after_batch_projection_rolls_back_economics_and_history(self):
        self.call(self.create_sql())
        role=self.db.issue(self.owner,self.run,'economic',expires=1.5,recovery=60)
        now,mono=time.time(),time.monotonic()
        candidate=core.bootstrap(self.config,seed_history(now,mono),decision_inputs(now,mono))
        sql='SELECT vn_durability.commit_command('+','.join((literal(self.owner),literal(self.run),literal(self.worker),
            '1','1',literal(str(uuid4())),document({'version':5,'operations':candidate.operations,'transition':candidate.transition})))+');'
        self.admin("CREATE FUNCTION public.native_delay_batch() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(2); RETURN NEW; END $$; "
            'CREATE TRIGGER zz_native_delay AFTER INSERT ON vn_durability.commands FOR EACH ROW EXECUTE FUNCTION public.native_delay_batch();')
        try:
            before=self.snapshot()
            session=self.db.begin_native(role,'economic',sql,timeout=6)
            self.barrier(f"SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename='{role}' AND wait_event='PgSleep');")
            result=session.wait(check=False)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('principal_denied',result.stderr)
            self.assertEqual(self.snapshot(),before)
        finally:
            self.admin('DROP TRIGGER zz_native_delay ON vn_durability.commands; DROP FUNCTION public.native_delay_batch();')

    def test_expiry_after_create_effects_rolls_back_entire_command(self):
        role=self.db.issue(self.owner,self.run,'economic',expires=1.5,recovery=60)
        self.admin("CREATE FUNCTION public.native_delay() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(2); RETURN NEW; END $$; "
            'CREATE TRIGGER native_delay AFTER INSERT ON vn_durability.commands FOR EACH ROW EXECUTE FUNCTION public.native_delay();')
        try:
            before=self.snapshot()
            session=self.db.begin_native(role,'economic',self.create_sql(),timeout=6)
            self.barrier(f"SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename='{role}' AND wait_event='PgSleep');")
            result=session.wait(check=False)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('principal_denied',result.stderr)
            self.assertEqual(self.snapshot(),before)
        finally:
            self.admin('DROP TRIGGER native_delay ON vn_durability.commands; DROP FUNCTION public.native_delay();')

    def test_native_v5_bootstrap_relay_accept_ack_and_owner_page(self):
        self.call(self.create_sql())
        now,mono=time.time(),time.monotonic()
        candidate=core.bootstrap(self.config,seed_history(now,mono),decision_inputs(now,mono))
        command=str(uuid4())
        sql='SELECT vn_durability.commit_command('+','.join((literal(self.owner),literal(self.run),literal(self.worker),
            '1','1',literal(command),document({'version':5,'operations':candidate.operations,'transition':candidate.transition})))+');'
        self.call(sql)
        stored=json.loads(self.admin(f"SELECT engine_state FROM vn_durability.runs WHERE id='{self.run}';").stdout)
        self.assertEqual(stored,candidate.state.to_dict())
        page=json.loads(self.call(f"SELECT vn_durability.read_outbox('{self.owner}','{self.run}',2,50,65536);",role=self.relay,capability='relay').stdout)
        self.assertEqual(len(page['events']),9)
        for index in range(9):
            args=f"'{self.owner}','{self.run}','{command}',{index}"
            self.call('SELECT vn_read.accept_event('+args+');',role=self.relay,capability='relay')
            self.call('SELECT vn_durability.acknowledge_event('+args+');',role=self.relay,capability='relay')
        page=self.db.sql(f"SET request.jwt.claim.sub='{self.owner}'; SELECT vn_read.page('{self.run}','probes',2,0,'',50,65536);",role='authenticated')
        self.assertEqual(len(json.loads(page.stdout)['records']),8)
        self.assertEqual(self.admin(f"SELECT count(*) FROM vn_projection.relay_events WHERE run_id='{self.run}';").stdout.strip(),'9')


@unittest.skipUnless(os.environ.get(harness.OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class NativeInstallationTests(unittest.TestCase):
    def setUp(self):
        self.db=fixture.NativePostgres()
        self.addCleanup(self.db.close)
        self.db.start()
        self.db.sql('CREATE ROLE vn_test_admin LOGIN SUPERUSER;')
        self.db.sql(installer_fixture.HOSTED_BOOTSTRAP,role=installer_fixture.ADMIN)
        self.db.sql('CREATE TABLE public.native_unrelated(id int PRIMARY KEY); INSERT INTO public.native_unrelated VALUES(42); '
            'GRANT SELECT ON public.native_unrelated TO authenticated; '
            'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT ON TABLES TO authenticated;')

    def metadata(self):
        return self.db.scalar("SELECT jsonb_build_object('auth_schema',(SELECT to_jsonb(n) FROM pg_namespace n WHERE nspname='auth'),"
            "'auth_uid',(SELECT jsonb_build_object('owner',proowner,'acl',proacl,'body',prosrc) FROM pg_proc WHERE oid='auth.uid()'::regprocedure),"
            "'auth_table',(SELECT jsonb_build_object('owner',relowner,'acl',relacl) FROM pg_class WHERE oid='auth.users'::regclass),"
            "'defaults',(SELECT jsonb_agg(to_jsonb(d) ORDER BY oid) FROM pg_default_acl d WHERE defaclrole='postgres'::regrole),"
            "'api_memberships',(SELECT jsonb_agg(to_jsonb(m) ORDER BY oid) FROM pg_auth_members m WHERE member IN "
            "(SELECT oid FROM pg_roles WHERE rolname IN('anon','authenticated','service_role','authenticator'))),"
            "'unrelated',(SELECT jsonb_build_object('acl',relacl,'owner',relowner) FROM pg_class WHERE oid='public.native_unrelated'::regclass),"
            "'rows',(SELECT jsonb_agg(to_jsonb(t)) FROM public.native_unrelated t));",role=installer_fixture.ADMIN)

    def test_late_failure_is_atomic_and_success_preserves_auth_api_defaults_unrelated(self):
        before=self.metadata()
        failed=fixture.package().rsplit('COMMIT;',1)[0]+"DO $$ BEGIN RAISE EXCEPTION 'native_injected_late_failure'; END $$;\nCOMMIT;\n"
        result=self.db.sql(failed,check=False,timeout=30)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('native_injected_late_failure',result.stderr)
        self.assertEqual(self.metadata(),before)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'vn_%';"),'0')
        self.db.sql(fixture.package(),timeout=30)
        self.assertEqual(self.metadata(),before)
        self.assertEqual(self.db.scalar("SET ROLE vn_contract_owner; SELECT count(*) FROM vn_access.bindings;"),'0')

    def test_preexisting_access_namespace_is_preserved_and_entire_install_refused(self):
        self.db.sql('CREATE SCHEMA vn_access; CREATE TABLE vn_access.unrelated(id int); INSERT INTO vn_access.unrelated VALUES(42);')
        before=self.metadata()
        result=self.db.sql(fixture.package(),check=False,timeout=30)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.db.scalar('SELECT id FROM vn_access.unrelated;'),'42')
        self.assertEqual(self.metadata(),before)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_roles WHERE rolname IN('vn_contract_owner','vn_economic','vn_relay');"),'0')
