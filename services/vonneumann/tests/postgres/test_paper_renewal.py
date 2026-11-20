"""Isolated PostgreSQL finite-renewal guards and real catalog-change races."""
from datetime import datetime,timedelta,timezone
import importlib.util,os
from pathlib import Path
import unittest
from uuid import uuid4
from tests.postgres import harness
ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('paper_renewal_native',ROOT/'scripts/dashboard_paper_renewal.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class RenewalNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get(harness.OPT_IN)!='1':raise unittest.SkipTest('Explicit isolated PostgreSQL opt-in required')
        cls.db=harness.IsolatedPostgres();cls.addClassCleanup(cls.db.close);cls.db.start()
        for name in ('20261117010000_vonneumann_paper_v6.sql','20261118010000_vonneumann_paper_v6_search_path.sql'):
            cls.db.sql((ROOT/'supabase/migrations'/name).read_text())
    def setUp(self):
        now=datetime.now(timezone.utc);self.old=(now+timedelta(hours=2)).isoformat();self.new=(now+timedelta(hours=3)).isoformat()
        self.owner,self.run,self.login=str(uuid4()),str(uuid4()),'vn_paper_'+uuid4().hex
        self.db.sql(f"INSERT INTO auth.users VALUES('{self.owner}'); CREATE ROLE {self.login} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD 'synthetic-renewal-fixture' VALID UNTIL '{self.old}'; GRANT USAGE ON SCHEMA vn_paper_v6 TO {self.login}; GRANT EXECUTE ON FUNCTION vn_paper_v6.rpc(text,jsonb) TO {self.login}; INSERT INTO vn_paper_v6.bindings VALUES('{self.login}','{self.owner}','{self.run}','{self.old}');")
        self.oid=int(self.db.scalar(f"SELECT oid FROM pg_roles WHERE rolname='{self.login}';"))
        self.record={'owner_id':self.owner,'run_id':self.run,'db_login':self.login,'role_oid':self.oid,
            'previous_deadline':self.old,'new_deadline':self.new}
    def unchanged(self):
        self.assertEqual(self.db.scalar(f"SELECT rolvaliduntil='{self.old}'::timestamptz FROM pg_roles WHERE oid={self.oid};"),'t')
        self.assertEqual(self.db.scalar(f"SELECT expires_at='{self.old}'::timestamptz FROM vn_paper_v6.bindings WHERE login='{self.login}';"),'t')
    def test_atomic_extension_changes_neither_password_nor_permissions(self):
        password=self.db.scalar(f"SELECT rolpassword FROM pg_authid WHERE oid={self.oid};")
        self.db.sql(r.renew_sql(self.record))
        self.assertEqual(self.db.scalar(f"SELECT rolvaliduntil='{self.new}'::timestamptz AND NOT rolinherit AND rolconnlimit=2 FROM pg_roles WHERE oid={self.oid};"),'t')
        self.assertEqual(self.db.scalar(f"SELECT expires_at='{self.new}'::timestamptz FROM vn_paper_v6.bindings WHERE login='{self.login}';"),'t')
        self.assertEqual(self.db.scalar(f"SELECT rolpassword FROM pg_authid WHERE oid={self.oid};"),password)
        spec=importlib.util.spec_from_file_location('renewal_close_fixture',ROOT/'scripts/dashboard-paper-v6.py')
        operator=importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)
        effective={**self.record,'valid_until':self.new}
        self.db.sql(operator.credential_close_sql(effective))
        self.assertEqual(self.db.scalar(f"SELECT NOT rolcanlogin FROM pg_roles WHERE oid={self.oid};"),'t')
    def test_wrong_oid_refuses_without_extending_either_deadline(self):
        changed={**self.record,'role_oid':self.oid+10000}
        self.assertNotEqual(self.db.sql(r.renew_sql(changed),check=False).returncode,0);self.unchanged()
    def test_silent_binding_update_failure_rolls_back_already_altered_role(self):
        function='renewal_fixture_'+uuid4().hex
        self.db.sql(f"CREATE FUNCTION public.{function}() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NULL; END$$; CREATE TRIGGER {function} BEFORE UPDATE ON vn_paper_v6.bindings FOR EACH ROW WHEN(OLD.login='{self.login}'::name) EXECUTE FUNCTION public.{function}();")
        self.assertNotEqual(self.db.sql(r.renew_sql(self.record),check=False).returncode,0);self.unchanged()

    def test_existing_table_acl_or_missing_rpc_refuses_without_deadline_change(self):
        for drift,restore in (
            (f"GRANT SELECT ON vn_paper_v6.entries TO {self.login};",f"REVOKE SELECT ON vn_paper_v6.entries FROM {self.login};"),
            (f"REVOKE EXECUTE ON FUNCTION vn_paper_v6.rpc(text,jsonb) FROM {self.login};",f"GRANT EXECUTE ON FUNCTION vn_paper_v6.rpc(text,jsonb) TO {self.login};")):
            self.db.sql(drift)
            self.assertNotEqual(self.db.sql(r.renew_sql(self.record),check=False).returncode,0)
            self.unchanged();self.db.sql(restore)

    def race_before_alter(self,drift):
        key=100000+uuid4().int%1000000000;tag=uuid4().hex
        gate_name='renewal_gate_'+tag;renew_name='renewal_race_'+tag
        gate=self.db.begin_sql(f"SET application_name='{gate_name}'; SELECT pg_advisory_lock({key}); SELECT pg_sleep(30);",timeout=15)
        self.db.wait_until(f"SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid={key} AND granted);",timeout=5)
        sql=r.renew_sql(self.record).replace("lock_timeout='1s'","lock_timeout='5s'")
        anchor="EXECUTE format('ALTER ROLE %I VALID UNTIL %L'"
        self.assertIn(anchor,sql)
        # This test-only barrier opens the precise precheck/ALTER window. The
        # actual postcondition and transaction are the production SQL.
        sql=sql.replace(anchor,f"PERFORM pg_advisory_xact_lock({key}); "+anchor,1)
        renewal=self.db.begin_sql(f"SET application_name='{renew_name}'; "+sql,timeout=15)
        try:
            self.db.wait_until(f"SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='{renew_name}' AND wait_event='advisory');",timeout=5)
            self.db.sql(drift)
        finally:
            self.db.sql(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='{gate_name}';")
            gate.wait(5,check=False)
        result=renewal.wait(8,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('finite_renewal_original_changed',result.stderr)
        self.unchanged()

    def test_concurrent_role_attribute_change_is_detected_after_alter_and_rolled_back(self):
        self.race_before_alter(f"ALTER ROLE {self.login} INHERIT;")
        self.assertEqual(self.db.scalar(f"SELECT rolinherit FROM pg_roles WHERE oid={self.oid};"),'t')

    def test_concurrent_private_table_grant_is_detected_and_deadlines_are_unchanged(self):
        self.race_before_alter(f"GRANT SELECT ON vn_paper_v6.entries TO {self.login};")
        self.assertEqual(self.db.scalar(f"SELECT has_table_privilege('{self.login}','vn_paper_v6.entries','SELECT');"),'t')

    def test_table_grant_after_binding_update_is_detected_before_commit(self):
        key=100000+uuid4().int%1000000000;tag=uuid4().hex
        gate_name='renewal_final_gate_'+tag;renew_name='renewal_final_race_'+tag
        gate=self.db.begin_sql(f"SET application_name='{gate_name}'; SELECT pg_advisory_lock({key}); SELECT pg_sleep(30);",timeout=15)
        self.db.wait_until(f"SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid={key} AND granted);",timeout=5)
        sql=r.renew_sql(self.record).replace("lock_timeout='1s'","lock_timeout='5s'")
        index=sql.rfind('IF NOT EXISTS(SELECT 1 FROM pg_roles r')
        self.assertGreater(index,sql.index('UPDATE vn_paper_v6.bindings'))
        sql=sql[:index]+f"PERFORM pg_advisory_xact_lock({key}); "+sql[index:]
        renewal=self.db.begin_sql(f"SET application_name='{renew_name}'; "+sql,timeout=15)
        try:
            self.db.wait_until(f"SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='{renew_name}' AND wait_event='advisory');",timeout=5)
            grant=self.db.sql(f"SET lock_timeout='500ms'; GRANT SELECT ON vn_paper_v6.entries TO {self.login};",check=False)
        finally:
            self.db.sql(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='{gate_name}';")
            gate.wait(5,check=False)
        result=renewal.wait(8,check=False)
        self.assertEqual(grant.returncode,0,grant.stderr)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('finite_renewal_permission_postcondition',result.stderr)
        self.unchanged()


if __name__=='__main__':unittest.main()
