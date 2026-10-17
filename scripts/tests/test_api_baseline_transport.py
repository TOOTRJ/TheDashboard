"""Pure fixed-operation transport tests: no Keychain, network or SQL execution."""
from contextlib import ExitStack
import importlib.util
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('api_transport_fixture', ROOT / 'scripts/tests/operator_fixture.py')
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)
management = fixture.load('api_baseline_transport_management', 'scripts/dashboard-supabase-management.py')


class ApiBaselineTransportTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(fixture.scope())
        self.keychain = self.stack.enter_context(patch.object(management, 'credential', side_effect=AssertionError('No Keychain access')))
        self.client = management.Management.__new__(management.Management)
        self.client._verified = True
        self.request = self.stack.enter_context(patch.object(self.client, '_request', return_value={'synthetic': 'result'}))

    def tearDown(self):
        self.keychain.assert_not_called()

    def test_actual_reviewed_emission_uses_permissions_only_and_fixed_request(self):
        module = types.ModuleType('independent_expected_permissions_emitter')
        path = ROOT / 'scripts/dashboard_api_baseline.py'
        module.__file__ = str(path)
        exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
        expected = module.baseline_sql(apply_acl=True)
        self.assertGreater(len(expected.encode('utf-8')), 65536)
        self.assertLessEqual(len(expected.encode('utf-8')), 196608)
        self.assertNotEqual(expected, module.baseline_sql(apply_acl=False))
        self.assertEqual(self.client.api_baseline_permissions(), {'synthetic': 'result'})
        self.request.assert_called_once_with('/database/query', {
            'query': expected, 'parameters': [], 'read_only': False,
        })

    def test_unverified_refuses_before_source_loading_or_request(self):
        with patch.object(management, '_api_baseline_permissions_sql') as source:
            for state in (False, None, 0, 1, 'true'):
                self.client._verified = state
                with self.subTest(state=state), self.assertRaises(management.Refused):
                    self.client.api_baseline_permissions()
            source.assert_not_called()
        self.request.assert_not_called()

    def test_wrong_project_verification_does_not_enable_operation(self):
        self.client._verified = False
        self.request.return_value = {'id': management.REF, 'name': management.NAME, 'organization_id': 'another-owner'}
        with self.assertRaises(management.Refused):
            self.client.verify()
        self.assertFalse(self.client._verified)
        with patch.object(management, '_api_baseline_permissions_sql') as source:
            with self.assertRaises(management.Refused):
                self.client.api_baseline_permissions()
            source.assert_not_called()
        self.assertEqual(self.request.call_args.args, ('',))
        self.assertEqual(self.request.call_count, 1)

    def test_no_caller_sql_hash_path_or_parameters_are_accepted(self):
        with patch.object(management, '_api_baseline_permissions_sql') as source:
            for args, kwargs in ((('SELECT 1;',), {}), ((), {'source': 'SELECT 1;'}),
                                 ((), {'path': '/tmp/source.py'}), ((), {'sha256': '0' * 64}),
                                 ((), {'parameters': []})):
                with self.subTest(args=args, kwargs=kwargs), self.assertRaises(TypeError):
                    self.client.api_baseline_permissions(*args, **kwargs)
            source.assert_not_called()
        self.request.assert_not_called()

    def test_failed_refresh_retires_previously_verified_identity(self):
        self.client._verified = True
        self.request.return_value = {'id': 'wrong-project', 'name': management.NAME,
                                     'organization_id': management.ORG}
        with self.assertRaises(management.Refused):
            self.client.verify()
        self.assertFalse(self.client._verified)
        with patch.object(management, '_api_baseline_permissions_sql') as source:
            with self.assertRaises(management.Refused):
                self.client.api_baseline_permissions()
            source.assert_not_called()
        self.assertEqual(self.request.call_count, 1)

    def test_utf8_query_byte_cap_and_container_types_refuse_before_request(self):
        for value in ('x' * 196609, '\N{LATIN SMALL LETTER E WITH ACUTE}' * 98305, '', None, b'SELECT 1;', True):
            with self.subTest(kind=type(value).__name__), patch.object(management, '_api_baseline_permissions_sql', return_value=value):
                with self.assertRaises(management.Refused):
                    self.client.api_baseline_permissions()
        self.request.assert_not_called()

    def test_exact_dedicated_byte_cap_is_accepted_only_at_fixed_path(self):
        value = 'x' * 196608
        with patch.object(management, '_api_baseline_permissions_sql', return_value=value):
            self.client.api_baseline_permissions()
        self.request.assert_called_once_with('/database/query', {'query': value, 'parameters': [], 'read_only': False})

    def test_generic_query_cap_is_still_65536(self):
        with self.assertRaises(management.Refused):
            self.client.query('x' * 65537)
        self.request.assert_not_called()
        self.client.query('x' * 65536)
        self.request.assert_called_once_with('/database/query', {'query': 'x' * 65536, 'parameters': [], 'read_only': True})

    def test_missing_source_refuses_without_request(self):
        with patch.object(management.os, 'open', side_effect=OSError('controlled missing source')):
            with self.assertRaisesRegex(management.Refused, '^Reviewed API baseline permissions source unavailable$'):
                self.client.api_baseline_permissions()
        self.request.assert_not_called()

    def test_unreviewed_or_oversize_source_is_not_compiled(self):
        with tempfile.TemporaryDirectory(prefix='dashboard-api-transport-test-') as directory:
            root = Path(directory).resolve()
            (root / 'scripts').mkdir()
            path = root / 'scripts/dashboard_api_baseline.py'
            for value in (b'raise AssertionError("unreviewed sentinel")\n', b'x' * 65537):
                path.write_bytes(value)
                with self.subTest(size=len(value)), patch.object(management, 'ROOT', root), patch.object(management, 'compile', create=True) as compiler:
                    with self.assertRaises(management.Refused):
                        self.client.api_baseline_permissions()
                    compiler.assert_not_called()
        self.request.assert_not_called()

    def test_symlink_source_is_refused_before_compilation(self):
        with tempfile.TemporaryDirectory(prefix='dashboard-api-transport-test-') as directory:
            root = Path(directory).resolve()
            (root / 'scripts').mkdir()
            target = root / 'sentinel.py'
            target.write_text('raise AssertionError("unused sentinel")\n')
            (root / 'scripts/dashboard_api_baseline.py').symlink_to(target)
            with patch.object(management, 'ROOT', root), patch.object(management, 'compile', create=True) as compiler:
                with self.assertRaises(management.Refused):
                    self.client.api_baseline_permissions()
                compiler.assert_not_called()
        self.request.assert_not_called()

    def test_nonregular_source_is_opened_nonblocking_and_never_compiled(self):
        with tempfile.TemporaryDirectory(prefix='dashboard-api-transport-test-') as directory:
            root = Path(directory).resolve()
            (root / 'scripts').mkdir()
            os.mkfifo(root / 'scripts/dashboard_api_baseline.py')
            original_open = management.os.open
            flags_seen = []
            def bounded_open(path, flags, *args, **kwargs):
                flags_seen.append(flags)
                if not flags & os.O_NONBLOCK:
                    raise AssertionError('Refuse to perform a potentially blocking fixture open')
                return original_open(path, flags, *args, **kwargs)
            with patch.object(management, 'ROOT', root), patch.object(management.os, 'open', side_effect=bounded_open), patch.object(management, 'compile', create=True) as compiler:
                with self.assertRaises(management.Refused):
                    self.client.api_baseline_permissions()
                compiler.assert_not_called()
            self.assertEqual(len(flags_seen), 1)
            self.assertTrue(flags_seen[0] & os.O_NONBLOCK)
        self.request.assert_not_called()

    def test_source_loading_failure_is_safe_and_never_a_request(self):
        with patch.object(management, '_api_baseline_permissions_sql', side_effect=management.Refused('fixed controlled source refusal')):
            with self.assertRaisesRegex(management.Refused, '^fixed controlled source refusal$'):
                self.client.api_baseline_permissions()
        self.request.assert_not_called()

    def test_transport_failure_is_not_retried_or_relabelled(self):
        error = management.Refused('original uncertain request')
        self.request.side_effect = error
        with patch.object(management, '_api_baseline_permissions_sql', return_value='fixed reviewed SQL') as source:
            with self.assertRaises(management.Refused) as caught:
                self.client.api_baseline_permissions()
            self.assertIs(caught.exception, error)
            source.assert_called_once_with()
        self.request.assert_called_once()


if __name__ == '__main__':
    unittest.main()
