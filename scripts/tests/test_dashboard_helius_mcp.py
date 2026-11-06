"""Offline artifact/credential boundary tests; no real key or provider requests."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    'dashboard_helius_mcp', Path(__file__).resolve().parents[1] / 'dashboard-helius-mcp.py',
)
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)
FAKE_KEY = '00000000-0000-4000-8000-000000000000'


class DashboardHeliusMcpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='dashboard-helius-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / 'scripts').mkdir(mode=0o700)
        (self.root / 'scripts/dashboard-helius-no-telemetry.mjs').write_text('// fake preload')
        self.ssl = self.root / 'ssl'
        self.ssl.mkdir(mode=0o700)
        self.key = self.ssl / 'helius-mcp.env'
        self.key.write_text('HELIUS_API_KEY=' + FAKE_KEY + '\n')
        self.key.chmod(0o600)
        self.execute = patch.object(dashboard.os, 'execve', side_effect=AssertionError('Unexpected real execution'))
        self.execute.start()
        self.addCleanup(self.execute.stop)

    def runtime_fixture(self):
        runtime = self.ssl / 'helius-mcp-runtime'
        runtime.mkdir(mode=0o700)
        for name in ('bin', 'home', 'tmp', 'npm-cache'):
            (runtime / name).mkdir(mode=0o700)
        node = runtime / 'bin/node'
        node.write_bytes(b'fake-reviewed-node')
        node.chmod(0o700)
        lock = runtime / 'package-lock.json'
        lock.write_text('{"lockfileVersion":3}\n')
        entry = runtime / 'node_modules/helius-mcp/dist/index.js'
        entry.parent.mkdir(parents=True, mode=0o700)
        entry.write_text('// fake stdio entrypoint; never executed\n')
        files, links = dashboard.module_inventory(runtime)
        node_hash = hashlib.sha256(node.read_bytes()).hexdigest()
        lock_hash = hashlib.sha256(lock.read_bytes()).hexdigest()
        manifest = {
            'package': 'helius-mcp', 'version': dashboard.VERSION, 'node_version': '24.19.0',
            'node_sha256': node_hash, 'package_lock_sha256': lock_hash,
            'files': files, 'symlinks': links,
        }
        metadata = runtime / 'runtime-integrity.json'
        metadata.write_text(json.dumps(manifest))
        metadata.chmod(0o600)
        overrides = patch.multiple(
            dashboard, NODE_SHA256=node_hash, LOCK_SHA256=lock_hash,
            MANIFEST_SHA256=hashlib.sha256(metadata.read_bytes()).hexdigest(),
        )
        overrides.start()
        self.addCleanup(overrides.stop)
        return runtime

    def test_reads_only_single_assignment_without_shell_interpretation(self):
        self.assertEqual(dashboard.read_key(self.root), FAKE_KEY)
        for text in (
            '', 'HELIUS_API_KEY=\n', FAKE_KEY, 'export HELIUS_API_KEY=' + FAKE_KEY,
            'HELIUS_API_KEY="' + FAKE_KEY + '"',
            'HELIUS_API_KEY=' + FAKE_KEY + '\nOTHER_TOKEN=private',
            'HELIUS_API_KEY=' + FAKE_KEY + '\nHELIUS_API_KEY=' + FAKE_KEY,
            'HELIUS_API_KEY=$(cat /some/secret)', 'HELIUS_API_KEY=`anything`',
            'HELIUS_API_KEY=' + '\u00e9' * 36,
        ):
            with self.subTest(case=text[:15]):
                self.key.write_text(text)
                with self.assertRaises(dashboard.Refused) as refused:
                    dashboard.read_key(self.root)
                self.assertNotIn(FAKE_KEY, str(refused.exception))

    def test_comments_and_blank_lines_allow_exactly_one_key_assignment(self):
        self.key.write_text('# Dashboard-only API key\n\nHELIUS_API_KEY=' + FAKE_KEY + '\n\n  # End\n')
        self.assertEqual(dashboard.read_key(self.root), FAKE_KEY)
        self.key.write_text('# Comment\nHELIUS_API_KEY=' + FAKE_KEY + '\nANOTHER_KEY=not-allowed\n')
        with self.assertRaises(dashboard.Refused):
            dashboard.read_key(self.root)

    def test_key_requires_owned_exact_0600_regular_bounded_file(self):
        for mode in (0o400, 0o640, 0o644, 0o666, 0o700):
            with self.subTest(mode=mode):
                self.key.chmod(mode)
                with self.assertRaises(dashboard.Refused):
                    dashboard.read_key(self.root)
        self.key.chmod(0o600)
        self.key.write_bytes(b'X' * 4097)
        with self.assertRaises(dashboard.Refused):
            dashboard.read_key(self.root)

    def test_foreign_file_owner_refused(self):
        with patch.object(dashboard.os, 'getuid', return_value=os.getuid() + 1):
            with self.assertRaises(dashboard.Refused):
                dashboard.read_owned(self.key, maximum=4096, mode=0o600)

    def test_key_symlink_and_hardlink_refused(self):
        target = self.ssl / 'fake-other-key'
        self.key.rename(target)
        self.key.symlink_to(target)
        with self.assertRaises(dashboard.Refused):
            dashboard.read_key(self.root)
        self.key.unlink()
        os.link(target, self.key)
        with self.assertRaises(dashboard.Refused):
            dashboard.read_key(self.root)

    def test_fifo_refused_without_waiting_for_writer(self):
        self.key.unlink()
        os.mkfifo(self.key, 0o600)
        with self.assertRaises(dashboard.Refused):
            dashboard.read_key(self.root)

    def test_symlinked_or_writable_parent_refused(self):
        self.ssl.chmod(0o777)
        with self.assertRaises(dashboard.Refused):
            dashboard.read_key(self.root)
        self.ssl.chmod(0o700)
        moved = self.root / 'private-data'
        self.ssl.rename(moved)
        self.ssl.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(dashboard.Refused):
            dashboard.read_key(self.root)

    def test_environment_is_an_allowlist_without_inherited_credentials_or_options(self):
        inherited = {
            'HOME': '/some/shared/home', 'PATH': '/shared/tools', 'GITHUB_TOKEN': 'shared',
            'HELIUS_API_KEY': 'other-key', 'NODE_OPTIONS': '--import=/shared/module.mjs',
            'HTTP_PROXY': 'https://shared-proxy.invalid', 'VERCEL_TOKEN': 'shared',
            'DATABASE_URL': 'shared', 'DYLD_INSERT_LIBRARIES': '/shared/library',
        }
        with patch.dict(os.environ, inherited):
            result = dashboard.child_environment(FAKE_KEY, self.root)
        self.assertEqual(set(result), {'PATH', 'HOME', 'TMPDIR', 'LANG', 'NO_COLOR',
            'HELIUS_API_KEY', 'HELIUS_NETWORK', 'HELIUS_MCP_SHARED_CREDENTIAL'})
        self.assertEqual(result['HOME'], str(self.ssl / 'helius-mcp-runtime/home'))
        self.assertEqual(result['HELIUS_API_KEY'], FAKE_KEY)
        self.assertEqual(result['HELIUS_MCP_SHARED_CREDENTIAL'], '1')
        self.assertEqual(result['HELIUS_NETWORK'], 'mainnet-beta')
        self.assertNotIn('shared', '\n'.join(result.values()))

    def test_verified_tree_never_reads_credential(self):
        self.runtime_fixture()
        with patch.object(dashboard, 'read_key', side_effect=AssertionError('Unexpected credential read')):
            result = dashboard.verify_runtime(self.root)
        self.assertFalse(result['credential_read'])
        self.assertEqual(result['provider_requests'], 0)
        self.assertEqual(result['verified_files'], 1)
        self.assertNotIn(FAKE_KEY, json.dumps(result))

    def test_modified_dependency_refused(self):
        runtime = self.runtime_fixture()
        (runtime / 'node_modules/helius-mcp/dist/index.js').write_text('// changed')
        with self.assertRaisesRegex(dashboard.Refused, 'dependency tree'):
            dashboard.verify_runtime(self.root)

    def test_added_dependency_file_refused(self):
        runtime = self.runtime_fixture()
        (runtime / 'node_modules/unreviewed.js').write_text('// new')
        with self.assertRaisesRegex(dashboard.Refused, 'dependency tree'):
            dashboard.verify_runtime(self.root)

    def test_changed_lock_node_and_manifest_refused_before_key(self):
        runtime = self.runtime_fixture()
        for name in ('package-lock.json', 'bin/node', 'runtime-integrity.json'):
            path = runtime / name
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            with self.subTest(path=name), patch.object(dashboard, 'read_key', side_effect=AssertionError('Unexpected credential read')):
                with self.assertRaises(dashboard.Refused):
                    dashboard.launch(self.root)
            path.write_bytes(original)

    def test_symlink_cannot_escape_modules(self):
        runtime = self.runtime_fixture()
        (runtime / 'node_modules/escape').symlink_to(self.key)
        with self.assertRaisesRegex(dashboard.Refused, 'link escaped'):
            dashboard.verify_runtime(self.root)

    def test_launch_passes_key_only_in_child_environment_and_exact_entry(self):
        runtime = self.runtime_fixture()
        with patch.object(dashboard.os, 'execve') as execute, patch.object(dashboard.os, 'chdir') as change:
            dashboard.launch(self.root)
        node, arguments, environment = execute.call_args.args
        self.assertEqual(node, str(runtime / 'bin/node'))
        self.assertEqual(arguments, [node, '--import', str(self.root / 'scripts/dashboard-helius-no-telemetry.mjs'),
            str(runtime / 'node_modules/helius-mcp/dist/index.js')])
        self.assertNotIn(FAKE_KEY, ' '.join(arguments))
        self.assertEqual(environment['HELIUS_API_KEY'], FAKE_KEY)
        change.assert_called_once_with(self.root)

    def test_cli_default_is_stdio_and_errors_suppress_underlying_process_text(self):
        with patch.object(dashboard, 'launch') as launch:
            self.assertEqual(dashboard.main([]), 0)
            launch.assert_called_once_with()
        error = io.StringIO()
        with patch.object(dashboard, 'launch', side_effect=OSError('never print ' + FAKE_KEY)), contextlib.redirect_stderr(error):
            self.assertEqual(dashboard.main(['stdio']), 1)
        self.assertNotIn(FAKE_KEY, error.getvalue())
        self.assertNotIn('never print', error.getvalue())

    def test_mutating_domain_tools_are_excluded_from_recommendation(self):
        self.assertEqual(len(dashboard.ENABLED_TOOLS), 6)
        self.assertFalse({'heliusAccount', 'heliusWrite', 'heliusStreaming', 'heliusKnowledge'} & set(dashboard.ENABLED_TOOLS))


if __name__ == '__main__':
    unittest.main()
