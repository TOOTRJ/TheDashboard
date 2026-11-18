"""Real transaction guards for closing one original paper login, including expiry."""
import importlib.util
import os
from pathlib import Path
import unittest
from uuid import uuid4

from tests.postgres import harness

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('dashboard_paper_native_operator', ROOT/'scripts/dashboard-paper-v6.py')
operator = importlib.util.module_from_spec(spec); spec.loader.exec_module(operator)


class PaperV6OperatorSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get(harness.OPT_IN) != '1':
            raise unittest.SkipTest('Explicit isolated PostgreSQL opt-in required')
        cls.db = harness.IsolatedPostgres(); cls.addClassCleanup(cls.db.close); cls.db.start()
        cls.db.sql((ROOT/'supabase/migrations/20261117010000_vonneumann_paper_v6.sql').read_text())
        cls.db.sql((ROOT/'supabase/migrations/20261118010000_vonneumann_paper_v6_search_path.sql').read_text())
        cls.db.sql(f"INSERT INTO auth.users VALUES('{operator.OWNER}');")

    def make_original(self, *, expired=False, owner=None):
        owner = operator.OWNER if owner is None else owner
        self.db.sql(f"INSERT INTO auth.users VALUES('{owner}') ON CONFLICT DO NOTHING;")
        login, run = 'vn_paper_'+uuid4().hex, str(uuid4())
        expiry = '2000-01-01T00:00:00+00:00' if expired else '2099-01-01T00:00:00+00:00'
        self.db.sql(f"CREATE ROLE {login} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD 'synthetic-operator-fixture' VALID UNTIL '{expiry}'; "
            f"GRANT USAGE ON SCHEMA vn_paper_v6 TO {login}; GRANT EXECUTE ON FUNCTION vn_paper_v6.rpc(text,jsonb) TO {login}; "
            f"INSERT INTO vn_paper_v6.bindings VALUES('{login}','{owner}','{run}','{expiry}');")
        oid = int(self.db.scalar(f"SELECT oid FROM pg_roles WHERE rolname='{login}';"))
        return {'owner_id': owner, 'db_login': login, 'run_id': run, 'valid_until': expiry, 'role_oid': oid}

    def test_explicit_app_owner_closure_preserves_legacy_owner_login(self):
        legacy = self.make_original()
        selected = self.make_original(owner='10000000-0000-4000-8000-000000000099')
        self.db.sql(operator.credential_close_sql(selected))
        self.assertEqual(self.db.scalar(f"SELECT NOT rolcanlogin AND rolpassword IS NULL FROM pg_authid WHERE oid={selected['role_oid']};"), 't')
        self.assertEqual(self.db.scalar(f"SELECT rolcanlogin AND rolpassword IS NOT NULL FROM pg_authid WHERE oid={legacy['role_oid']};"), 't')
        self.assertEqual(self.db.scalar(f"SELECT owner_id='{legacy['owner_id']}'::uuid AND run_id='{legacy['run_id']}'::uuid AND expires_at='{legacy['valid_until']}'::timestamptz FROM vn_paper_v6.bindings WHERE login='{legacy['db_login']}';"), 't')

    def test_wrong_record_owner_cannot_close_another_owner_login(self):
        original = self.make_original(owner='10000000-0000-4000-8000-000000000098')
        changed = {**original, 'owner_id': operator.OWNER}
        result = self.db.sql(operator.credential_close_sql(changed), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.db.scalar(f"SELECT rolcanlogin AND rolpassword IS NOT NULL FROM pg_authid WHERE oid={original['role_oid']};"), 't')
        self.assertEqual(self.db.scalar(f"SELECT owner_id='{original['owner_id']}'::uuid AND expires_at='{original['valid_until']}'::timestamptz FROM vn_paper_v6.bindings WHERE login='{original['db_login']}';"), 't')

    def test_expired_owned_role_is_closed_with_password_removed(self):
        record = self.make_original(expired=True)
        self.db.sql(operator.credential_close_sql(record))
        self.assertEqual(self.db.scalar(f"SELECT NOT rolcanlogin AND rolpassword IS NULL FROM pg_authid WHERE oid={record['role_oid']};"), 't')
        self.assertEqual(self.db.scalar(f"SELECT expires_at<=clock_timestamp() FROM vn_paper_v6.bindings WHERE login='{record['db_login']}';"), 't')

    def test_recreated_same_name_oid_refuses_in_transaction_and_preserves_replacement(self):
        record = self.make_original()
        login = record['db_login']
        self.db.sql(f"DROP OWNED BY {login}; DROP ROLE {login}; CREATE ROLE {login} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD 'replacement-synthetic-fixture' VALID UNTIL '{record['valid_until']}';")
        replacement = int(self.db.scalar(f"SELECT oid FROM pg_roles WHERE rolname='{login}';"))
        self.assertNotEqual(replacement, record['role_oid'])
        result = self.db.sql(operator.credential_close_sql(record), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.db.scalar(f"SELECT rolcanlogin AND rolpassword IS NOT NULL FROM pg_authid WHERE oid={replacement};"), 't')
        self.assertEqual(self.db.scalar(f"SELECT expires_at='{record['valid_until']}'::timestamptz FROM vn_paper_v6.bindings WHERE login='{login}';"), 't')

    def test_changed_binding_scope_refuses_before_altering_original_login(self):
        record = self.make_original()
        changed_run = str(uuid4())
        self.db.sql(f"UPDATE vn_paper_v6.bindings SET run_id='{changed_run}' WHERE login='{record['db_login']}';")
        result = self.db.sql(operator.credential_close_sql(record), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.db.scalar(f"SELECT rolcanlogin AND rolpassword IS NOT NULL FROM pg_authid WHERE oid={record['role_oid']};"), 't')
        self.assertEqual(self.db.scalar(f"SELECT run_id='{changed_run}'::uuid AND expires_at='{record['valid_until']}'::timestamptz FROM vn_paper_v6.bindings WHERE login='{record['db_login']}';"), 't')


if __name__ == '__main__':
    unittest.main()
