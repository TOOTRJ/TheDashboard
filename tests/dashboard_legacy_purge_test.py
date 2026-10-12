import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dashboard_purge_fixture', ROOT/'scripts/tests/operator_fixture.py')
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
module = fixture.load('purge_operator_test', 'scripts/dashboard-legacy-purge.py')


class LegacyPurgeTests(unittest.TestCase):
    def setUp(self):
        scope = fixture.scope(); scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)

    def record(self):
        return {'state': 'prepared', 'digests': {table: {'count': 1, 'md5': 'a'*32}
                for table in module.TABLES}}

    def test_submitted_original_cannot_be_applied_again(self):
        with patch.object(module, 'reviewed_source') as source:
            with self.assertRaises(module.Refused):
                module.apply(object(), {**self.record(), 'state': 'submitted_or_uncertain'})
            source.assert_not_called()

    def test_changed_original_content_prevents_any_submission(self):
        with patch.object(module, 'reviewed_source', return_value='reviewed'), \
                patch.object(module, 'current', return_value={}), patch.object(module, 'save') as save:
            with self.assertRaises(module.Refused):
                module.apply(object(), self.record())
            save.assert_not_called()

    def test_original_intent_is_saved_before_unknown_reply_and_not_retried(self):
        record = self.record()
        saved = []
        class Client:
            def query(self, source, **options):
                self_test.assertEqual(saved, ['submitted_or_uncertain'])
                raise module.management.Refused('unknown reply')
        self_test = self
        with patch.object(module, 'reviewed_source', return_value='reviewed'), \
                patch.object(module, 'current', return_value=record['digests']), \
                patch.object(module, 'save', side_effect=lambda r: saved.append(r['state'])):
            with self.assertRaises(module.management.Refused):
                module.apply(Client(), record)
        self.assertEqual(record['state'], 'submitted_or_uncertain')
        with self.assertRaises(module.Refused):
            module.apply(Client(), record)

    def test_original_rows_or_partial_purge_never_report_success(self):
        record = self.record()
        zero = {'count': 0, 'md5': 'd751713988987e9331980363e24189ce'}
        for result in (record['digests'], {**record['digests'], module.TABLES[0]: zero}):
            with patch.object(module, 'current', return_value=result), \
                    patch.object(module, 'save') as save:
                with self.assertRaises(module.Refused):
                    module.reconcile(object(), record)
                save.assert_not_called()

    def test_empty_read_still_requires_full_catalog_and_history_verification(self):
        record = self.record()
        empty = {table: {'count': 0, 'md5': 'd751713988987e9331980363e24189ce'} for table in module.TABLES}
        with patch.object(module, 'current', return_value=empty), \
                patch.object(module.cutover, 'artifacts', return_value=(1, 2, 3)), \
                patch.object(module.cutover, 'reconcile', side_effect=module.cutover.Refused('catalog changed')), \
                patch.object(module, 'save') as save:
            with self.assertRaises(module.cutover.Refused):
                module.reconcile(object(), record)
            save.assert_not_called()
        self.assertEqual(record['state'], 'prepared')

    def test_private_snapshot_refuses_symlinks_or_loose_modes(self):
        with tempfile.TemporaryDirectory(prefix='dashboard-purge-test-') as directory:
            path = Path(directory)/'snapshot.json'
            path.write_text('{}')
            os.chmod(path, 0o644)
            with self.assertRaises(module.Refused):
                module.private_bytes(path)
            os.chmod(path, 0o600)
            self.assertEqual(module.private_bytes(path), b'{}')
            link = Path(directory)/'link.json'
            link.symlink_to(path)
            with self.assertRaises(OSError):
                module.private_bytes(link)


if __name__ == '__main__':
    unittest.main()
