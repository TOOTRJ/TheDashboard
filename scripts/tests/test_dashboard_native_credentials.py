"""Original-scope retention and project isolation for the native operator."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


operator = load('native_credential_operator_test', ROOT / 'scripts/dashboard-native-credentials.py')
management = load('management_isolation_test', ROOT / 'scripts/dashboard-supabase-management.py')


class NativeCredentialOperatorTests(unittest.TestCase):
    def test_prepared_original_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            owner = {'legacy_owner_count': 1, 'legacy_owner_auth_match': True, 'legacy_owner_ids': [str(uuid4())]}
            operator.cutover.private_write(folder / 'bot-owner-scope.json', json.dumps(owner))
            with patch.object(operator, 'DIRECTORY', folder), patch.object(operator, 'STATE', folder / 'original.json'):
                first = operator.prepare()
                self.assertEqual(first['state'], 'prepared')
                self.assertNotEqual(first['passwords'][0], first['passwords'][1])
                self.assertTrue(all(p not in operator.builder.install() for p in first['passwords'] + first['verifiers']))
                with self.assertRaises(operator.cutover.Refused): operator.prepare()
                self.assertEqual(operator.private_read(operator.STATE), first)

    def test_reconciliation_uses_original_scope_and_never_submits_verifiers(self):
        record = {'owner': str(uuid4()), 'run': str(uuid4()), 'issuances': [str(uuid4()), str(uuid4())],
                  'names': ['vn_native_' + uuid4().hex, 'vn_native_' + uuid4().hex],
                  'passwords': ['a' * 64, 'b' * 64], 'verifiers': ['private-verifier-a', 'private-verifier-b']}
        rows = [{'owner': record['owner'], 'run': record['run'], 'issuance': record['issuances'][i],
                 'name': record['names'][i], 'oid': 30001 + i, 'capability': ('economic', 'relay')[i],
                 'restricted': True, 'deadline_matches': True, 'revoked': None, 'login': True} for i in range(2)]
        class Client:
            def query(self, sql):
                for secret in record['passwords'] + record['verifiers']:
                    if secret in sql: raise AssertionError('Private material in readback SQL')
                return [{'receipt': rows}]
        with patch.object(operator, 'save'):
            self.assertEqual(operator.reconcile(Client(), record)['state'], 'issued_verified')
            rows[0]['oid'] = 40000
            with self.assertRaises(operator.cutover.Refused): operator.reconcile(Client(), record)

    def test_nonprivate_files_are_not_credential_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'; path.write_text('{}'); path.chmod(0o644)
            with self.assertRaises(operator.cutover.Refused): operator.private_read(path)
            path.chmod(0o600); alias = path.with_name('alias'); alias.symlink_to(path)
            with self.assertRaises(operator.cutover.Refused): operator.private_read(alias)

    def test_management_path_requires_verified_exact_project(self):
        value = management.Management.__new__(management.Management)
        value._verified = False; value._credential = 'synthetic'
        for path in ('/database/query', '/../other/database/query', 'https://other.example'):
            with self.assertRaises(management.Refused): value._request(path)
        with patch.object(value, '_request', return_value={'id': management.REF, 'name': 'Other', 'organization_id': management.ORG}):
            with self.assertRaises(management.Refused): value.verify()
        self.assertFalse(value._verified)


if __name__ == '__main__': unittest.main()
