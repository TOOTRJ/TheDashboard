"""Finite inert artifact checks; behavioral acceptance lives in PostgreSQL."""
import hashlib
import json
from pathlib import Path
import unittest
from tests.postgres import legacy_evidence_fixture as fixture


class LegacyEvidencePackageTests(unittest.TestCase):
    def test_package_and_manifest_are_deterministic_and_digest_pinned(self):
        sql,manifest=fixture.builder.build()
        self.assertEqual(sql,(fixture.HERE/'package.sql').read_text())
        self.assertEqual(manifest,json.loads((fixture.HERE/'manifest.json').read_text()))
        self.assertEqual(hashlib.sha256(sql.encode()).hexdigest(),manifest['package_sha256'])
        self.assertEqual(manifest['mode'],'isolated_legacy_evidence_rehearsal_only')
        self.assertFalse(manifest['production_application_available'])

    def test_no_runtime_import_or_migration_installs_this_component(self):
        worker=Path(__file__).resolve().parents[1]
        for directory in (worker/'vonneumann',worker.parents[1]/'supabase/migrations'):
            self.assertTrue(directory.is_dir())
            for path in directory.rglob('*'):
                if path.suffix in ('.py','.sql'):
                    self.assertNotIn('legacy_evidence_fixture',path.read_text())
                    self.assertNotIn('db-contract/legacy-evidence',path.read_text())

    def test_component_inventory_is_finite_and_no_economic_credential_is_added(self):
        _,manifest=fixture.builder.build()
        self.assertEqual(len(manifest['tables']),5)
        self.assertEqual(len(manifest['functions']),19)
        self.assertEqual(len(manifest['authenticated']),3)
        self.assertEqual(len(manifest['attestor']),3)
        self.assertFalse(manifest['private_tables_exposed'])
