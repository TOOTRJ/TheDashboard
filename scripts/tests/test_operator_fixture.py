"""The portable source fixture never changes operational helpers or credentials."""
import builtins
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import urllib.request
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('operator_fixture_boundary_test', Path(__file__).with_name('operator_fixture.py'))
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)


class OperatorFixtureTests(unittest.TestCase):
    def test_different_checkout_root_supports_nested_imports_and_pure_artifacts(self):
        # Simulate an Ubuntu checkout without creating /Users or copying private inputs.
        public_inputs = fixture.SOURCES | {
            'services/vonneumann/db-contract/forward/manifest.json',
            'services/vonneumann/db-contract/forward/package.sql',
            'services/vonneumann/db-contract/forward/review.sql',
            'services/vonneumann/db-contract/legacy_catalog.sql',
            'supabase/audits/2026-10-07-forward-install-review.json',
            'supabase/audits/2026-10-07-forward-install-manifest.json',
            'supabase/migrations/20261007010000_vonneumann_closed_v5.sql',
        }
        with tempfile.TemporaryDirectory(prefix='dashboard-source-fixture-') as directory:
            checkout = Path(directory).resolve() / 'checkout'; checkout.mkdir()
            for name in public_inputs:
                target = checkout / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(fixture.ROOT / name, target)
            with patch.object(fixture, 'ROOT', checkout), fixture.scope():
                module = fixture.load('different_checkout_native_fixture', 'scripts/dashboard-native-credentials.py')
                self.assertEqual(module.ROOT, checkout)
                self.assertEqual(module.cutover.ROOT, checkout)
                builder, source, manifest = module.cutover.artifacts()
                self.assertEqual(builder.ROOT, checkout)
                self.assertEqual(manifest['installed_admission'], 'closed')
                self.assertIn('COMMIT;', source)
            self.assertFalse((checkout / 'ssl').exists())
            self.assertFalse((checkout / '.env').exists())

    def test_only_the_exact_pinned_source_assignment_is_relocated(self):
        source = fixture.ROOT_ASSIGNMENT + "\nREF = 'fxpxsciltakyypunglzr'\n"
        changed = fixture.relocated_source('scripts/dashboard-db-cutover.py', source)
        self.assertEqual(changed, f"ROOT = Path({str(fixture.ROOT)!r})\nREF = 'fxpxsciltakyypunglzr'\n")
        for invalid in (source.replace(str(fixture.PINNED_ROOT), '/other/project'), source + fixture.ROOT_ASSIGNMENT + '\n'):
            with self.assertRaises(AssertionError): fixture.relocated_source('scripts/dashboard-db-cutover.py', invalid)
        commented = '# ' + fixture.ROOT_ASSIGNMENT + '\n' + source
        with patch.object(fixture, 'ROOT', Path('/fixture-only-checkout')):
            changed = fixture.relocated_source('scripts/dashboard-db-cutover.py', commented)
        self.assertEqual(changed, '# ' + fixture.ROOT_ASSIGNMENT + "\nROOT = Path('/fixture-only-checkout')\nREF = 'fxpxsciltakyypunglzr'\n")

    def test_sources_are_regular_reviewed_paths_not_private_or_traversed_files(self):
        for name in ('ssl/token.py', '.env', 'scripts/../ssl/token.py', 'scripts/unreviewed.py'):
            with self.subTest(name=name), self.assertRaises(AssertionError):
                fixture.reviewed_path(fixture.PINNED_ROOT / name)

    def test_scope_denies_real_process_network_and_private_reads_then_restores(self):
        before = (subprocess.run, urllib.request.build_opener, builtins.open, importlib.util.spec_from_file_location)
        with fixture.scope():
            with self.assertRaises(AssertionError): subprocess.run(['must-not-execute'])
            with self.assertRaises(AssertionError): urllib.request.build_opener()
            for name in ('ssl/never-read', '.env', '.vercel/project.json'):
                with self.subTest(name=name), self.assertRaises(AssertionError):
                    (fixture.ROOT / name).read_bytes()
        self.assertEqual(before, (subprocess.run, urllib.request.build_opener, builtins.open, importlib.util.spec_from_file_location))

    def test_nested_operator_sources_load_without_changing_production_files(self):
        before = {name: (fixture.ROOT / name).read_bytes() for name in fixture.SOURCES}
        module = fixture.load('fixture_nested_native_test', 'scripts/dashboard-native-credentials.py')
        self.assertEqual(module.ROOT, fixture.ROOT)
        self.assertEqual(module.cutover.REF, 'fxpxsciltakyypunglzr')
        self.assertEqual(module.management.ORG, 'cqfnnaunmupdyobkyqfo')
        self.assertEqual(before, {name: (fixture.ROOT / name).read_bytes() for name in fixture.SOURCES})

    def test_owned_synthetic_private_file_still_exercises_real_file_mode_checks(self):
        module = fixture.load('fixture_private_purge_test', 'scripts/dashboard-legacy-purge.py')
        with tempfile.TemporaryDirectory(prefix='dashboard-fixture-private-') as directory:
            path = Path(directory) / 'snapshot.json'; path.write_bytes(b'{}'); path.chmod(0o600)
            with fixture.scope(): self.assertEqual(module.private_bytes(path), b'{}')
            path.chmod(0o644)
            with fixture.scope(), self.assertRaises(module.Refused): module.private_bytes(path)


if __name__ == '__main__': unittest.main()
