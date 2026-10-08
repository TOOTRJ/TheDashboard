"""Offline refusal and original-outcome handling for the scoped DB operator."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'dashboard-db-cutover.py'
SPEC = importlib.util.spec_from_file_location('dashboard_db_operator_tests', PATH)
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


class ClosedMigrationOperatorTests(unittest.TestCase):
    def test_artifacts_reproduce_and_preserve_closed_admission(self):
        builder, source, manifest = operator.artifacts()
        self.assertEqual(manifest['installed_admission'], 'closed')
        self.assertFalse(manifest['credentials_provisioned'])
        self.assertFalse(manifest['api_exposed'])
        self.assertIn("SET LOCAL transaction_timeout='25s'", source)
        self.assertEqual(source.count('\nCOMMIT;\n'), 1)
        self.assertNotIn('tests.postgres', source)

    def test_history_is_inserted_before_the_only_commit(self):
        source = "BEGIN; SELECT 'literal''quote';\nCOMMIT;\n"
        wrapped = operator.history_wrapper(source, '20261007010000', 'vonneumann_closed_v5')
        self.assertTrue(wrapped.endswith('COMMIT;\n'))
        self.assertIn('schema_migrations(version,name,statements)', wrapped)
        self.assertIn("SELECT ''literal''''quote''", wrapped)
        self.assertLess(wrapped.index('INSERT INTO'), wrapped.rindex('COMMIT;'))

    def test_unreviewed_grammar_cannot_become_an_application(self):
        for source, version, name in (
            ('SELECT 1;', '20261007010000', 'good'),
            ('BEGIN;\nCOMMIT;\nCOMMIT;\n', '20261007010000', 'good'),
            ('BEGIN;\nCOMMIT;\n', 'bad', 'good'),
            ('BEGIN;\nCOMMIT;\n', '20261007010000', "bad'); DROP"),
        ):
            with self.subTest(source=source, version=version, name=name), self.assertRaises(operator.Refused):
                operator.history_wrapper(source, version, name)

    def test_private_files_refuse_replacement_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'original.json'
            operator.private_write(path, '{}')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                operator.private_write(path, 'replacement')
            link = Path(directory) / 'alias.json'
            link.symlink_to(path)
            with self.assertRaises(operator.Refused):
                operator.private_write(link, 'replacement')
            self.assertEqual(path.read_text(), '{}')

    def test_uncertain_reply_reconciles_once_without_second_application(self):
        builder, source, manifest = operator.artifacts()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'outcome.json'
            with patch.object(operator, 'STATE', state), patch.object(operator, 'preflight', return_value={}), \
                patch.object(operator, 'sql_file', side_effect=operator.Refused('timeout')) as submit, \
                patch.object(operator, 'reconcile', return_value={'admission': 'closed'}) as recover:
                result = operator.apply(builder, source, manifest)
                self.assertEqual(result['admission'], 'closed')
                submit.assert_called_once()
                recover.assert_called_once()
                retained = json.loads(state.read_text())
                self.assertEqual(retained['status'], 'committed_and_verified_closed')
                with self.assertRaises(FileExistsError):
                    operator.apply(builder, source, manifest)
                submit.assert_called_once()

    def test_failed_reconciliation_retains_original_unknown_outcome(self):
        builder, source, manifest = operator.artifacts()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'outcome.json'
            with patch.object(operator, 'STATE', state), patch.object(operator, 'preflight', return_value={}), \
                patch.object(operator, 'sql_file', return_value=[]), \
                patch.object(operator, 'reconcile', side_effect=operator.Refused('unavailable')):
                with self.assertRaises(operator.Refused):
                    operator.apply(builder, source, manifest)
                retained = json.loads(state.read_text())
                self.assertEqual(retained['status'], 'outcome_unknown_until_fresh_postflight')
                self.assertEqual(retained['migration_sha256'], manifest['migration_sha256'])
                self.assertTrue(state.with_name('original-closed-install.sql').is_file())


if __name__ == '__main__':
    unittest.main()
