"""Fresh-process offline CLI, semantic replay, and artifact publication checks."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.security_support import deny_network
from tests.test_dataset import frames, metadata

with deny_network():
    from vonneumann.market.dataset import MAINNET_GENESIS_HASH, TOKEN_MINTS, load_dataset, write_dataset
    from vonneumann.research.artifacts import load_result, plain_data, write_result


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ASSET = 'SOL/USDC'
FRAME_COUNT = 305 + 20 + 20

# Invoke the actual __main__ in a new interpreter, installing the fail-closed
# import/network guards before importing application code. No environment from
# the parent process (and therefore no inherited account keys) reaches the child.
CHILD_BOOTSTRAP = r'''
import importlib.abc
import os
import runpy
import socket
import sys

assert set(os.environ) <= {'PATH', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE',
                           'PYTHON_DOTENV_DISABLED', 'PYTHONHASHSEED', 'LC_CTYPE',
                           '__CF_USER_TEXT_ENCODING'}
blocked = ('supabase', 'dotenv', 'aiohttp', 'httpx', 'requests', 'pydantic_settings',
           'vonneumann.config', 'vonneumann.db', 'vonneumann.server',
           'vonneumann.core.genesis', 'vonneumann.core.colony_manager',
           'vonneumann.market.jupiter_feed', 'vonneumann.market.birdeye_feed')
class NoLiveImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == item or fullname.startswith(item + '.') for item in blocked):
            raise AssertionError('Offline research imported a live adapter or configuration')
sys.meta_path.insert(0, NoLiveImports())
def no_network(*args, **kwargs):
    raise AssertionError('Offline research attempted network access')
socket.getaddrinfo = socket.create_connection = no_network
socket.socket.connect = socket.socket.connect_ex = socket.socket.sendto = no_network
sys.argv = ['vonneumann.research.cli', *sys.argv[1:]]
try:
    runpy.run_module('vonneumann.research.cli', run_name='__main__')
finally:
    assert not any(name == item or name.startswith(item + '.')
                   for name in sys.modules for item in blocked)
'''


class ResearchCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temporary = tempfile.TemporaryDirectory(prefix='research-cli-', dir='/private/tmp')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        rows = frames(count=FRAME_COUNT)
        for index, frame in enumerate(rows):
            # Actual bullish crossings, later fills, then protective exits in
            # each partition. Keep all ordinary fixture observations explicit.
            price = {309: 105.0, 310: 101.0, 314: 95.0,
                     329: 105.0, 330: 101.0, 334: 95.0}.get(index, 100.0)
            frame['quotes'][0].update(price=price, volume=0)
            frame['candles'][0].update(open=price, high=price, low=price, close=price, volume=0)
        cls.dataset = cls.root / 'dataset'
        with deny_network():
            write_dataset(cls.dataset, metadata(frames=FRAME_COUNT), rows)
        cls.result = cls.root / 'original-result'
        process = cls.child(cls.run_arguments(cls.result))
        if process.returncode != 0:
            raise AssertionError(f'Offline CLI fixture failed: {process.stderr}')
        cls.report = json.loads(process.stdout)
        cls.original = load_result(cls.result)

    def setUp(self):
        super().setUp()
        self.network = deny_network()
        self.network.__enter__()
        self.addCleanup(self.network.__exit__, None, None, None)
        self.directory = self.root / self._testMethodName
        self.directory.mkdir()

    @classmethod
    def child(cls, arguments, *, hash_seed='0'):
        environment = {'PATH': os.defpath, 'PYTHONPATH': str(PACKAGE_ROOT),
                       'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1',
                       'PYTHONHASHSEED': hash_seed}
        return subprocess.run([sys.executable, '-s', '-c', CHILD_BOOTSTRAP, *map(str, arguments)],
                              env=environment, cwd=cls.root, capture_output=True,
                              text=True, timeout=30, check=False)

    @classmethod
    def run_arguments(cls, output, *, dataset=None, extras=()):
        return ['run', '--dataset', dataset or cls.dataset, '--output', output,
                '--timeframe-minutes', '5', '--train-minutes', '20', '--holdout-minutes', '20',
                '--random-seed', '18446744073709551615', '--random-budget', '7',
                '--fee-bps', '25', '--half-spread-bps', '10', '--slippage-bps', '15', *extras]

    def verify(self, result=None, *, dataset=None):
        return self.child(['verify', '--dataset', dataset or self.dataset, '--result', result or self.result])

    def assert_safe_failure(self, process, *, code=None):
        self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
        self.assertEqual(process.stdout, '')
        error = json.loads(process.stderr)
        self.assertEqual(set(error), {'error'})
        if code:
            self.assertEqual(error['error'], code)
        self.assertNotIn(str(self.root), process.stderr)
        self.assertNotIn('private-sentinel', process.stderr)
        self.assertNotIn('Traceback', process.stderr)

    def tampered(self, edit):
        changed = plain_data(self.original.payload)
        edit(changed)
        path = self.directory / f'tampered-{len(list(self.directory.iterdir()))}'
        artifact = write_result(path, changed)
        # The codec intentionally accepts integrity-valid JSON. This establishes
        # that verify must compare replay semantics, not merely file checksums.
        self.assertEqual(load_result(path).result_id, artifact.result_id)
        self.assertNotEqual(artifact.result_id, self.original.result_id)
        return path

    def test_run_publishes_readable_full_ledger_and_verify_reproduces_it(self):
        self.assertEqual(self.report['result_id'], self.original.result_id)
        self.assertEqual(self.report['dataset_id'], load_dataset(self.dataset).dataset_id)
        self.assertEqual(self.report['scope'], 'synthetic_mechanics_only')
        self.assertEqual(self.report['verification'], 'created')
        self.assertEqual(self.report['random_budget'], 7)
        self.assertEqual(self.original.payload['config']['random_seed'], '18446744073709551615')
        training = self.original.payload['evaluations']['train']
        self.assertEqual(len(training), 24)
        self.assertTrue(any(event['kind'] == 'trade_opened'
                            for candidate in training if candidate['candidate_id'].startswith('ema-')
                            for row in candidate['ledger'] for event in row['events']))
        verified = self.verify()
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(verified.stderr, '')
        report = json.loads(verified.stdout)
        self.assertEqual(report, {**self.report, 'verification': 'full_replay_equal'})
        self.assertNotIn(str(self.root), verified.stdout)

    def test_rehashed_numeric_ledger_tampering_fails_even_if_reported_summaries_are_unchanged(self):
        def edit(value):
            value['evaluations']['train'][0]['ledger'][1]['equity'] += 0.125
        path = self.tampered(edit)
        self.assertEqual(load_result(path).payload['evaluations']['train'][0]['summary'],
                         self.original.payload['evaluations']['train'][0]['summary'])
        self.assert_safe_failure(self.verify(path), code='research_integrity')

    def test_rehashed_wrong_dataset_identity_engine_version_and_source_fingerprint_fail(self):
        def fingerprint(value):
            key = sorted(value['engine']['source_sha256'])[0]
            value['engine']['source_sha256'][key] = '0' * 64
        changes = [lambda value: value['dataset'].update(dataset_id='0' * 64),
                   lambda value: value['engine'].update(version='private-sentinel-version'), fingerprint]
        for edit in changes:
            with self.subTest(edit=edit):
                self.assert_safe_failure(self.verify(self.tampered(edit)), code='research_integrity')

    def test_different_valid_bound_dataset_is_not_accepted_as_same_experiment(self):
        source = load_dataset(self.dataset)
        rows = plain_data(source.frames)
        rows[-1]['quotes'][0]['price'] += 2
        rows[-1]['candles'][0].update(open=102, high=102, low=102, close=102)
        other = self.directory / 'other-dataset'
        write_dataset(other, source.manifest['metadata'], rows)
        self.assert_safe_failure(self.verify(dataset=other), code='research_integrity')

    def test_invalid_run_config_and_insufficient_coverage_create_no_output(self):
        cases = [('--timeframe-minutes', '4'), ('--train-minutes', '0'),
                 ('--initial-capital', 'nan'), ('--initial-capital', 'inf'),
                 ('--random-seed', '01'), ('--random-budget', '21'),
                 ('--asset', 'private-sentinel-asset'), ('--fee-bps', '10000'),
                 ('--slippage-bps', '-1'), ('--train-minutes', '100')]
        for index, extra in enumerate(cases):
            output = self.directory / f'invalid-{index}'
            with self.subTest(extra=extra):
                self.assert_safe_failure(self.child(self.run_arguments(output, extras=extra)))
                self.assertFalse(output.exists())
        missing = self.directory / 'private-sentinel-missing'
        output = self.directory / 'missing-output'
        self.assert_safe_failure(self.child(self.run_arguments(output, dataset=missing)), code='research_dataset')
        self.assertFalse(output.exists())

    def test_provider_archive_is_rejected_without_importing_live_adapters_or_creating_output(self):
        source = load_dataset(self.dataset)
        meta, rows = plain_data(source.manifest['metadata']), plain_data(source.frames)
        meta.update(source_kind='provider_observations', network='solana-mainnet',
                    genesis_hash=MAINNET_GENESIS_HASH, quote_provider='jupiter-price-v3',
                    candle_provider='birdeye-ohlcv-v3', volume_unit='base_token',
                    quote_volume_semantics='unavailable_zero_placeholder',
                    source_time_semantics='estimated_block_time', availability_semantics='recorded_receipt',
                    rights_basis='provider_archive_permission_reviewed', simulation_spec=None,
                    evaluation_start_at=rows[0]['observed_at'])
        meta['assets'][0]['mint'] = TOKEN_MINTS[ASSET]
        for frame in rows:
            frame['quotes'][0].update(source_slot=frame['seq'] + 1, volume_unit='base_token')
            for candle in frame['candles']:
                candle.update(source='birdeye-ohlcv-v3', volume_unit='base_token')
        provider = self.directory / 'provider-shaped-fixture'
        write_dataset(provider, meta, rows)
        output = self.directory / 'rejected-output'
        self.assert_safe_failure(self.child(self.run_arguments(output, dataset=provider)), code='research_dataset')
        self.assertFalse(output.exists())

    def test_existing_results_are_not_overwritten_even_when_arguments_differ(self):
        before = {entry.name: entry.read_bytes() for entry in self.result.iterdir()}
        process = self.child(self.run_arguments(self.result, extras=['--random-seed', '1']))
        self.assert_safe_failure(process, code='research_exists')
        self.assertEqual({entry.name: entry.read_bytes() for entry in self.result.iterdir()}, before)

    def test_fresh_process_hash_seed_and_uuid_noise_cannot_change_result_bytes_or_ids(self):
        for seed in ('1', '41203'):
            output = self.directory / f'hashseed-{seed}'
            process = self.child(self.run_arguments(output), hash_seed=seed)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stderr, '')
            self.assertEqual(json.loads(process.stdout)['result_id'], self.original.result_id)
            for filename in ('manifest.json', 'result.json'):
                self.assertEqual((output / filename).read_bytes(), (self.result / filename).read_bytes())

    def test_malformed_result_configuration_and_corrupt_files_have_safe_errors(self):
        path = self.tampered(lambda value: value.update(config={'private-sentinel': True}))
        self.assert_safe_failure(self.verify(path), code='research_invalid')
        corrupt = self.directory / 'corrupt'
        corrupt.mkdir()
        (corrupt / 'manifest.json').write_text('private-sentinel')
        (corrupt / 'result.json').write_text('private-sentinel')
        self.assert_safe_failure(self.verify(corrupt), code='research_invalid')


if __name__ == '__main__':
    unittest.main()
