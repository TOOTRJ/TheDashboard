"""Frozen protocol, honest pairing and complete replay over actual synthetic accounts."""
import asyncio
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network
from tests.test_dataset import metadata, frames, provider_bundle
with deny_network():
    from vonneumann.core.execution import ExecutionConfig
    from vonneumann.market.dataset import DatasetError, write_dataset
    from vonneumann.research.artifacts import canonical_bytes, load_result, write_result, ResearchArtifactError
    from vonneumann.research.runner import ResearchConfig
    from vonneumann.research.protocol import PairedProtocol, PairedResearchError, run_protocol, verify_result, write_plan, load_plan, _source


class PairedProtocolTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix='dashboard-paired-test-', dir=Path(tempfile.gettempdir()).resolve())
        self.addCleanup(temporary.cleanup); self.root = Path(temporary.name)
        self.config = ResearchConfig(timeframe_minutes=5, train_minutes=40, holdout_minutes=40,
            execution=ExecutionConfig(2, 3, 5))
        rows = frames(count=self.config.required_frames)
        for index, row in enumerate(rows):
            price = 100 + 8 * math.sin(index / 17)
            row['quotes'][0]['price'] = price
            row['candles'][0].update(open=price, high=price, low=price, close=price)
        self.dataset = self.root / 'dataset'; self.rows = rows
        write_dataset(self.dataset, metadata(frames=len(rows)), rows)

    def protocol(self, seeds=('0', '1'), budgets=(4, 8)):
        return PairedProtocol.freeze(self.dataset, self.config, seeds=seeds, budgets=budgets)

    async def test_actual_two_seed_two_budget_complete_accounts_and_paired_metrics_reproduce(self):
        protocol = self.protocol(); write_plan(self.root / 'plan', protocol)
        self.assertEqual(load_plan(self.root / 'plan'), protocol)
        before = random.getstate()
        first = await run_protocol(self.dataset, protocol)
        self.assertEqual(random.getstate(), before)
        self.assertEqual([(c['seed'], c['budget']) for c in first['children']], [('0',4),('0',8),('1',4),('1',8)])
        self.assertEqual(len(first['paired_rows']), 4)
        self.assertTrue(all(value is False for value in first['claims'].values()))
        for child, paired in zip(first['children'], first['paired_rows']):
            payload = child['payload']; encoded = canonical_bytes(payload)
            self.assertEqual(child['manifest']['payload']['bytes'], len(encoded))
            self.assertEqual(child['manifest']['payload']['sha256'], hashlib.sha256(encoded).hexdigest())
            self.assertEqual(child['result_id'], hashlib.sha256(canonical_bytes(child['manifest'])).hexdigest())
            self.assertEqual(len(payload['evaluations']['train']), 24)
            summaries = {r['candidate_id']: r['summary'] for r in payload['evaluations']['holdout']}
            ga = summaries[payload['selection']['ga']['winner']]
            other = summaries[payload['selection']['random']['winner']]
            for metric in ('fitness', 'roi', 'max_drawdown', 'net_pnl', 'total_costs', 'num_trades'):
                self.assertEqual(paired['ga_minus_random'][metric], ga[metric] - other[metric])
            for name in ('cash', 'fixed-ema-09-21', 'buy-hold-25', 'buy-hold-100'):
                self.assertEqual(paired['ga_minus_controls'][name]['roi'], ga['roi'] - summaries[name]['roi'])
            for algorithm in ('ga','random'):
                trace = payload['selection'][algorithm]
                self.assertEqual(len(trace['trials']), child['budget'])
                self.assertEqual(trace['budget'], paired['requests'][algorithm]['budget'])
                self.assertEqual(trace['additional_computed_evaluations'], 0)
            self.assertEqual(payload['selection']['ga']['trial_ids'][:4], payload['selection']['random']['trial_ids'][:4])
            self.assertEqual(paired['exhaustive_training_accounts_charged'], 24)
        written = write_result(self.root / 'result', first)
        reproduced = await verify_result(self.dataset, self.root / 'result')
        self.assertEqual(written.result_id, reproduced.result_id)
        self.assertNotIn(str(self.root), json.dumps(first))

    async def test_coordinated_rehash_of_complete_child_and_summary_cannot_bypass_full_replay(self):
        value = await run_protocol(self.dataset, self.protocol(seeds=('0',), budgets=(8,)))
        value['children'][0]['payload']['evaluations']['holdout'][0]['ledger'][1]['cash'] += 1
        child = value['children'][0]; wire = canonical_bytes(child['payload'])
        child['manifest']['payload'].update(bytes=len(wire), sha256=hashlib.sha256(wire).hexdigest())
        child['result_id'] = hashlib.sha256(canonical_bytes(child['manifest'])).hexdigest()
        value['paired_rows'][0]['ga_minus_random']['roi'] = 999
        write_result(self.root / 'rehashed', value)
        load_result(self.root / 'rehashed')  # Integrity succeeds; semantic replay must still refuse.
        with self.assertRaises(PairedResearchError) as caught:
            await verify_result(self.dataset, self.root / 'rehashed')
        self.assertEqual(caught.exception.code, 'paired_integrity')

    def test_exact_plan_types_policy_bounds_and_nested_immutability(self):
        protocol = self.protocol(); value = protocol.to_dict()
        with self.assertRaises(FrozenInstanceError): protocol._wire = b'{}'
        value['base_config']['execution']['fee_bps'] = 999
        self.assertEqual(protocol.to_dict()['base_config']['execution']['fee_bps'], 2)
        for field, bad in (('seeds',['01']), ('seeds',['0','0']), ('seeds',[False]),
                           ('budgets',[True]), ('budgets',[8,4]), ('budgets',[4,4]),
                           ('budgets',[21]), ('python','3.12.15'), ('scope','historical_backtest')):
            changed = protocol.to_dict(); changed[field] = bad
            with self.assertRaises(PairedResearchError): PairedProtocol.from_dict(changed)
        changed = protocol.to_dict(); changed['baseline_policy']['selection'] = 'holdout_best'
        with self.assertRaises(PairedResearchError): PairedProtocol.from_dict(changed)
        changed = protocol.to_dict(); changed['base_config']['timeframe_minutes'] = True
        with self.assertRaises(PairedResearchError): PairedProtocol.from_dict(changed)
        changed = protocol.to_dict(); changed['extra'] = '/private/secret'
        with self.assertRaises(PairedResearchError) as caught: PairedProtocol.from_dict(changed)
        self.assertNotIn('/private/secret', str(caught.exception))
        with self.assertRaises(PairedResearchError): self.protocol(seeds=tuple(map(str, range(8))), budgets=(1,4,8))

    async def test_source_or_dataset_change_refuses_before_evaluation(self):
        protocol = self.protocol()
        changed = _source(); first = next(iter(changed)); changed[first] = '0'*64
        with patch('vonneumann.research.protocol._source', return_value=changed), \
             patch('vonneumann.research.protocol.run_experiment', side_effect=AssertionError('Child must not start')):
            with self.assertRaises(PairedResearchError) as caught: await run_protocol(self.dataset, protocol)
            self.assertEqual(caught.exception.code, 'paired_context')
        rows = deepcopy(self.rows); rows[-1]['quotes'][0]['price'] += 1
        path = self.root / 'changed'; write_dataset(path, metadata(frames=len(rows)), rows)
        with patch('vonneumann.research.protocol.run_experiment', side_effect=AssertionError('Child must not start')):
            with self.assertRaises(PairedResearchError) as caught: await run_protocol(path, protocol)
            self.assertEqual(caught.exception.code, 'paired_context')

    def test_provider_observations_cannot_be_relabelled_or_used_for_plan(self):
        meta, rows = provider_bundle(); path = self.root / 'provider'
        write_dataset(path, meta, rows)
        with self.assertRaises(DatasetError) as caught:
            PairedProtocol.freeze(path, self.config, seeds=('0',), budgets=(4,))
        self.assertEqual(caught.exception.code, 'provider_replay_unsupported')
        with self.assertRaises(PairedResearchError): PairedProtocol.freeze(self.dataset,
            ResearchConfig(asset='JUP/USDC', timeframe_minutes=5, train_minutes=40, holdout_minutes=40), seeds=('0',), budgets=(4,))

    async def test_cancellation_publishes_no_partial_and_preserves_frozen_plan(self):
        protocol = self.protocol()
        with patch('vonneumann.research.protocol.run_experiment', side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError): await run_protocol(self.dataset, protocol)
        self.assertFalse((self.root / 'result').exists())
        self.assertEqual(protocol, PairedProtocol.from_dict(protocol.to_dict()))

    def test_canonical_bytes_duplicate_fields_and_existing_plan_are_refused(self):
        protocol = self.protocol(); write_plan(self.root / 'plan', protocol)
        with self.assertRaises(ResearchArtifactError): write_plan(self.root / 'plan', protocol)
        with self.assertRaises(PairedResearchError): PairedProtocol(protocol._wire + b' ')
        with self.assertRaises(PairedResearchError): PairedProtocol(b'{"version":1,"version":1}\n')
        with self.assertRaises(PairedResearchError): PairedProtocol(b'x'*65537)

