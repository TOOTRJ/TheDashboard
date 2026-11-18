"""Original operation retention and bounded exact-target production installer."""
import base64
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('dashboard_paper_operator_tests', ROOT / 'scripts/dashboard-paper-v6.py')
operator = importlib.util.module_from_spec(spec); spec.loader.exec_module(operator)


class PaperOperatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        for name, value in (('ROOT', ROOT), ('MIGRATION', ROOT/'supabase/migrations/20261117010000_vonneumann_paper_v6.sql'),
                            ('HARDENING', ROOT/'supabase/migrations/20261118010000_vonneumann_paper_v6_search_path.sql'),
                            ('HARDENING_STATE', self.folder/'search-path-hardening-original.json'),
                            ('DIRECTORY', self.folder), ('SCHEMA_STATE', self.folder/'schema-original.json'),
                            ('CREDENTIAL_STATE', self.folder/'credentials-original.json')):
            replacement = patch.object(operator, name, value); replacement.start()
            self.addCleanup(replacement.stop)
        # Only git's ignore lookup is mocked; private ownership/mode/no-follow
        # and exclusive-create checks execute against real temporary files.
        ignore = patch.object(operator.subprocess, 'run', return_value=type('Ignored', (), {'returncode': 0})())
        ignore.start(); self.addCleanup(ignore.stop)

    def test_prepared_source_is_private_original_and_cannot_be_replaced(self):
        first = operator.prepare()
        self.assertEqual(stat.S_IMODE(operator.SCHEMA_STATE.stat().st_mode), 0o600)
        with self.assertRaises(FileExistsError):
            operator.prepare()
        self.assertEqual(operator._read(operator.SCHEMA_STATE), first)

    def test_install_records_original_source_inside_same_transaction_and_bound(self):
        source, digest = operator._source()
        sql = operator.schema_install_sql(source)
        self.assertEqual(sql.count('\nCOMMIT;'), 1)
        self.assertIn(base64.b64encode(source.encode()).decode(), sql)
        self.assertIn("VALUES('20261117010000','vonneumann_paper_v6'", sql)
        forward, forward_digest = operator._hardening_source()
        self.assertIn(base64.b64encode(forward.encode()).decode(), sql)
        self.assertIn("VALUES('20261118010000','vonneumann_paper_v6_search_path'", sql)
        self.assertIn('SET search_path = pg_catalog, pg_temp;', sql)
        self.assertEqual(digest, operator.BASE_SHA256)
        body = {'query': sql, 'parameters': [], 'read_only': False}
        self.assertLessEqual(len(json.dumps(body).encode()), operator.MAX_BODY)

    def test_hardening_unknown_reply_reconciles_once_and_preserves_original_base_and_credentials(self):
        operator.prepare()
        operator._write(operator.CREDENTIAL_STATE, {'synthetic': 'original credential record untouched'})
        before_base = operator.SCHEMA_STATE.read_bytes()
        before_credentials = operator.CREDENTIAL_STATE.read_bytes()
        prepared = operator.prepare_hardening()
        class Client:
            writes = 0
            def verify(self): pass
            def query(self, sql, parameters, *, read_only):
                self.writes += 1
                raise TimeoutError()
        client = Client()
        receipt = {'version': prepared['version'], 'sha256': prepared['sha256']}
        with patch.object(operator, 'preflight_hardening'), patch.object(operator, 'verify_hardening', return_value=receipt) as readback:
            self.assertEqual(operator.apply_hardening(client), receipt)
            readback.assert_called_once()
        self.assertEqual(client.writes, 1)
        self.assertEqual(operator._read(operator.HARDENING_STATE)['state'], 'installed_verified')
        self.assertEqual(operator.SCHEMA_STATE.read_bytes(), before_base)
        self.assertEqual(operator.CREDENTIAL_STATE.read_bytes(), before_credentials)
        with self.assertRaises(operator.Refused): operator.apply_hardening(client)
        self.assertEqual(client.writes, 1)

    def test_missing_hardening_receipt_leaves_original_uncertain_and_never_retries(self):
        operator.prepare_hardening()
        class Client:
            writes = 0
            def verify(self): pass
            def query(self, *args, **kwargs):
                self.writes += 1
                raise TimeoutError()
        client = Client()
        with patch.object(operator, 'preflight_hardening'), patch.object(operator, 'verify_hardening', side_effect=operator.Refused('not observed')):
            with self.assertRaises(operator.Refused): operator.apply_hardening(client)
        self.assertEqual(operator._read(operator.HARDENING_STATE)['state'], 'submitted_or_uncertain')
        with self.assertRaises(operator.Refused): operator.apply_hardening(client)
        self.assertEqual(client.writes, 1)

    def test_secure_schema_requires_exact_forward_history_receipt(self):
        base = {'name': operator.NAME, 'one_source': True, 'sha256': operator.BASE_SHA256}
        checks = {'tables': operator.TABLES, 'owned_rls': True, 'client_restricted': True,
            'rpc_exact': True, 'client_rpc': True, 'no_client_tables': True,
            'no_api_access': True, 'no_public_schema': True, 'no_public_rpc': True}
        client = type('Client', (), {'verify': lambda self: None,
            'postgrest': lambda self: {'db_schema': 'public,graphql_public'}})()
        with patch.object(operator, '_one', side_effect=[base, checks, {'name': 'wrong'}]) as query:
            with self.assertRaises(operator.Refused):
                operator.verify_schema(client, {'sha256': operator.BASE_SHA256})
            self.assertIn("p.proconfig=ARRAY['search_path=pg_catalog, pg_temp']", query.call_args_list[1].args[1])
            self.assertNotIn("OR p.proconfig=ARRAY['search_path=pg_catalog']", query.call_args_list[1].args[1])

    def test_uncertain_schema_reply_uses_original_readback_without_write_retry(self):
        operator.prepare()
        class Client:
            writes, verified = 0, 0
            def verify(self): self.verified += 1
            def query(self, sql, parameters, *, read_only):
                self.writes += 1
                if read_only: raise AssertionError('Expected one installation attempt only')
                raise TimeoutError()
        client = Client()
        with patch.object(operator, 'preflight'), patch.object(operator, 'verify_schema', return_value={'verified': True}) as readback:
            self.assertEqual(operator.apply_schema(client), {'verified': True})
            self.assertEqual(client.writes, 1)
            self.assertEqual(client.verified, 1)
            readback.assert_called_once()
        self.assertEqual(operator._read(operator.SCHEMA_STATE)['state'], 'installed_verified')
        with self.assertRaises(operator.Refused):
            operator.apply_schema(client)
        self.assertEqual(client.writes, 1)

    def test_unobserved_schema_outcome_stays_uncertain_and_blocks_retry(self):
        operator.prepare()
        class Client:
            def verify(self): pass
            def query(self, *args, **kwargs): raise TimeoutError()
        with patch.object(operator, 'preflight'), patch.object(operator, 'verify_schema', side_effect=operator.Refused('not observed')):
            with self.assertRaises(operator.Refused): operator.apply_schema(Client())
        self.assertEqual(operator._read(operator.SCHEMA_STATE)['state'], 'submitted_or_uncertain')
        with self.assertRaises(operator.Refused): operator.apply_schema(Client())

    def test_credential_prepare_and_sql_keep_plaintext_local_and_exact_finite_scope(self):
        digest = operator._source()[1]
        with patch.object(operator, 'verify_schema', return_value={'sha256': digest}), patch.object(operator, 'verify_owner'):
            record = operator.prepare_credentials(object())
        loaded = operator._credentials()
        self.assertEqual(loaded, record)
        self.assertEqual(stat.S_IMODE(operator.CREDENTIAL_STATE.stat().st_mode), 0o600)
        sql = operator.credential_install_sql(record)
        self.assertNotIn(record['db_password'], sql)
        self.assertIn(record['scram_verifier'], sql)
        self.assertIn(record['db_login'], sql)
        self.assertIn('NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE', sql)
        self.assertIn(record['valid_until'], sql)
        self.assertNotIn('DROP ', sql)
        with patch.object(operator, 'verify_schema', return_value={'sha256': digest}), patch.object(operator, 'verify_owner'):
            with self.assertRaises(FileExistsError): operator.prepare_credentials(object())

    def test_unrelated_existing_role_oid_cannot_be_accepted(self):
        record = {'db_login': 'vn_paper_'+uuid4().hex, 'run_id': str(uuid4()),
            'valid_until': '2026-11-24T00:00:00+00:00', 'role_oid': 10001}
        row = {'role_oid': 10002, 'binding_exact': True, 'restricted': True, 'role_deadline': True,
            'no_memberships': True, 'direct_rpc': True, 'no_table_access': True,
            'can_login': True, 'binding_deadline': True, 'binding_active': True}
        client = type('Client', (), {'verify': lambda self: None})()
        with patch.object(operator, '_one', return_value=row):
            with self.assertRaises(operator.Refused): operator.verify_credentials(client, record)

    def test_expired_exact_original_can_pass_closing_preflight_but_not_active_verification(self):
        record = {'db_login': 'vn_paper_'+uuid4().hex, 'run_id': str(uuid4()),
            'valid_until': '2000-01-01T00:00:00+00:00', 'role_oid': 10001}
        row = {'role_oid': 10001, 'binding_exact': True, 'restricted': True, 'role_deadline': True,
            'no_memberships': True, 'direct_rpc': True, 'no_table_access': True,
            'can_login': True, 'binding_deadline': True, 'binding_active': False}
        client = type('Client', (), {'verify': lambda self: None})()
        with patch.object(operator, '_one', return_value=row), patch.object(operator, '_write'):
            with self.assertRaises(operator.Refused): operator.verify_credentials(client, record)
            result = operator.verify_credentials(client, record, allow_expired=True)
        self.assertEqual(result['state'], 'issued_verified')
        sql = operator.credential_close_sql(record)
        before_alter = sql.split("EXECUTE format('ALTER ROLE", 1)[0]
        self.assertIn('r.oid=10001::oid', before_alter)
        self.assertIn("r.rolvaliduntil='2000-01-01T00:00:00+00:00'::timestamptz", before_alter)
        self.assertIn('FOR UPDATE', before_alter)
        self.assertIn(record['run_id'], before_alter)
        self.assertEqual(sql.count('r.oid=10001::oid'), 2)


if __name__ == '__main__':
    unittest.main()
