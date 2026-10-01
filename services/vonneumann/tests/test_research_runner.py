"""Independent accounting, causality and selection checks for offline EMA research."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network
from tests.test_dataset import metadata, frames, provider_bundle

with deny_network():
    from vonneumann.core.execution import ExecutionConfig
    from vonneumann.market.dataset import load_dataset, write_dataset
    from vonneumann.research.runner import ResearchConfig, ResearchError, run_experiment
    from vonneumann.research.runner import _EmaAccount


ASSET = 'SOL/USDC'
WARMUP_MINUTES = 305  # 61 complete five-minute bars, independent of chosen EMA.
GRID_IDS = [f'ema-{fast:02d}-{slow:02d}' for fast in (3, 5, 8, 12)
            for slow in (15, 20, 30, 45, 60)]
CONTROL_IDS = ['fixed-ema-09-21', 'cash', 'buy-hold-25', 'buy-hold-100']


class ResearchRunnerTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix='research-runner-tests-', dir='/private/tmp')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture_count = 0
        state = random.getstate()
        self.addCleanup(random.setstate, state)

    def config(self, **changes):
        return ResearchConfig(timeframe_minutes=5, train_minutes=20, holdout_minutes=20,
                              **changes)

    def fixture(self, *, config=None, quote_prices=None, candle_prices=None, count=None):
        config = config or self.config()
        count = count if count is not None else WARMUP_MINUTES + config.train_minutes + config.holdout_minutes
        rows = frames(count=count)
        quotes = quote_prices if quote_prices is not None else [100.0] * count
        candles = candle_prices if candle_prices is not None else quotes
        self.assertEqual(len(quotes), count)
        self.assertEqual(len(candles), count)
        for index, row in enumerate(rows):
            row['quotes'][0].update(price=quotes[index], volume=0)
            row['candles'][0].update(open=candles[index], high=candles[index],
                                     low=candles[index], close=candles[index], volume=0)
        self.fixture_count += 1
        destination = self.root / f'fixture-{self.fixture_count}'
        write_dataset(destination, metadata(frames=count), rows)
        return destination, rows

    @staticmethod
    def evaluations(result, partition):
        return {item['candidate_id']: item for item in result['evaluations'][partition]}

    async def test_identical_runs_ignore_global_random_noise_and_leave_global_rng_untouched(self):
        path, _ = self.fixture()
        config = self.config(random_seed='18446744073709551615', random_budget=7)
        first = await run_experiment(path, config)
        random.seed(49283)
        for _ in range(1000):
            random.gauss(0, 1)
        before = random.getstate()
        with patch('random.random', side_effect=AssertionError('Global search RNG forbidden')), \
             patch('random.shuffle', side_effect=AssertionError('Global search RNG forbidden')), \
             patch('random.sample', side_effect=AssertionError('Global search RNG forbidden')):
            second = await run_experiment(path, config)
        self.assertEqual(random.getstate(), before)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(json.dumps(first, allow_nan=False)), first)
        self.assertEqual(first['schema_version'], 'ema-research-v1')
        self.assertNotIn(str(self.root), json.dumps(first))

    async def test_exhaustive_grid_and_random_prefix_have_stable_tie_selection(self):
        path, _ = self.fixture()
        one = await run_experiment(path, self.config(random_seed='31', random_budget=1))
        full = await run_experiment(path, self.config(random_seed='31', random_budget=20))
        other = await run_experiment(path, self.config(random_seed='32', random_budget=1))
        self.assertEqual(set(self.evaluations(full, 'train')), set(GRID_IDS + CONTROL_IDS))
        self.assertEqual(len(full['candidates']), 24)
        self.assertEqual(full['selection']['grid_winner'], 'ema-03-15')
        order = full['selection']['random']['order']
        self.assertEqual(len(order), 20)
        self.assertEqual(set(order), set(GRID_IDS))
        self.assertEqual(one['selection']['random']['order'], order)
        self.assertNotEqual(other['selection']['random']['order'], order)
        self.assertEqual(one['selection']['random']['trial_ids'], order[:1])
        self.assertEqual(one['selection']['random']['winner'], order[0])
        self.assertEqual(full['selection']['random']['winner'], 'ema-03-15')
        expected_holdout = {full['selection']['grid_winner'], full['selection']['random']['winner'], *CONTROL_IDS}
        self.assertEqual(set(self.evaluations(full, 'holdout')), expected_holdout)
        self.assertEqual(len(full['evaluations']['holdout']), len(expected_holdout))
        for row in full['evaluations']['train']:
            self.assertAlmostEqual(row['summary']['cash'], 1000)
            self.assertEqual(row['summary']['roi'], 0)

    async def test_holdout_changes_cannot_change_training_ledgers_or_selections(self):
        config = self.config(random_seed='79', random_budget=6)
        count = WARMUP_MINUTES + 40
        training_end = WARMUP_MINUTES - 1 + 20
        prices = [100.0] * count
        # A completed bullish candle followed by a different executable quote.
        prices[309] = 105.0
        prices[310] = 102.0
        first_path, _ = self.fixture(config=config, quote_prices=prices)
        altered = list(prices)
        for index in range(training_end + 1, count):
            altered[index] = 1000.0 if index % 2 else 1.0
        second_path, _ = self.fixture(config=config, quote_prices=altered)
        one = await run_experiment(first_path, config)
        two = await run_experiment(second_path, config)
        self.assertEqual(one['selection'], two['selection'])
        self.assertEqual(one['evaluations']['train'], two['evaluations']['train'])
        self.assertNotEqual(one['dataset']['dataset_id'], two['dataset']['dataset_id'])
        self.assertNotEqual(one['evaluations']['holdout'], two['evaluations']['holdout'])

    async def test_buy_hold_fee_spread_slippage_and_exact_boundary_prices_match_decimal_oracle(self):
        execution = ExecutionConfig(fee_bps=35, half_spread_bps=20, slippage_bps=15)
        config = self.config(execution=execution)
        prices = [100.0] * (WARMUP_MINUTES + 40)
        # Boundaries are cash-only; the first later quote is deliberately unlike it.
        prices[304], prices[305], prices[324] = 900.0, 80.0, 120.0
        prices[325], prices[344] = 110.0, 90.0
        path, _ = self.fixture(config=config, quote_prices=prices)
        result = await run_experiment(path, config)
        for partition, initial_price, final_price, first_frame, last_frame in (
                ('train', 80, 120, 305, 324), ('holdout', 110, 90, 325, 344)):
            for fraction in (25, 100):
                row = self.evaluations(result, partition)[f'buy-hold-{fraction}']
                with localcontext() as ctx:
                    ctx.prec = 60
                    cash = Decimal(1000)
                    budget = cash * Decimal(fraction) / 100
                    fee = Decimal(35) / 10000
                    impact = Decimal(35) / 10000
                    quantity = budget / (1 + fee) / (Decimal(initial_price) * (1 + impact))
                    proceeds = quantity * Decimal(final_price) * (1 - impact) * (1 - fee)
                    expected_cash = cash - budget + proceeds
                self.assertAlmostEqual(row['summary']['cash'], float(expected_cash), places=10)
                self.assertAlmostEqual(row['summary']['net_pnl'], float(expected_cash - cash), places=10)
                self.assertEqual(row['summary']['num_trades'], 1)
                events = [(item['frame'], event) for item in row['ledger'] for event in item['events']]
                opened = [(frame, event) for frame, event in events if event['kind'] == 'trade_opened']
                closed = [(frame, event) for frame, event in events if event['kind'] == 'trade_closed']
                self.assertEqual(len(opened), 1)
                self.assertEqual(len(closed), 1)
                self.assertEqual(opened[0][0], first_frame)
                self.assertEqual(closed[0][0], last_frame)
                self.assertEqual(opened[0][1]['execution']['entry']['reference_price'], initial_price)
                self.assertEqual(closed[0][1]['execution']['exit']['reference_price'], final_price)
                self.assertFalse(row['ledger'][0]['events'])
                self.assertEqual(row['ledger'][0]['cash'], 1000)
                self.assertEqual(row['ledger'][-1]['position_value'], 0)

    async def test_every_frame_reconciles_cash_holdings_costs_and_terminal_net_pnl_from_events(self):
        config = self.config(execution=ExecutionConfig(15, 10, 5))
        prices = [100.0] * (WARMUP_MINUTES + 40)
        prices[309], prices[310], prices[314], prices[315] = 105, 101, 95, 99
        prices[329], prices[330], prices[334], prices[335] = 103, 100, 95, 98
        path, source = self.fixture(config=config, quote_prices=prices)
        result = await run_experiment(path, config)
        for partition in ('train', 'holdout'):
            for evaluation in result['evaluations'][partition]:
                with self.subTest(partition=partition, candidate=evaluation['candidate_id']):
                    cash, net_pnl, costs = Decimal(1000), Decimal(0), Decimal(0)
                    peak, worst_drawdown = Decimal(1000), Decimal(0)
                    positions, completed = {}, 0
                    for row in evaluation['ledger']:
                        samples = [Decimal(str(row['pre_equity']))]
                        for event in row['events']:
                            if event['kind'] == 'trade_opened':
                                entry = event['execution']['entry']
                                self.assertNotIn(event['trade_id'], positions)
                                positions[event['trade_id']] = entry
                                cash -= Decimal(str(entry['cash_debit']))
                                costs += sum(Decimal(str(entry[name])) for name in ('fee', 'spread_cost', 'slippage_cost'))
                            elif event['kind'] == 'trade_closed':
                                self.assertIn(event['trade_id'], positions)
                                entry = positions.pop(event['trade_id'])
                                exit_fill = event['execution']['exit']
                                cash += Decimal(str(exit_fill['cash_credit']))
                                net_pnl += Decimal(str(exit_fill['cash_credit'])) - Decimal(str(entry['cash_debit']))
                                costs += sum(Decimal(str(exit_fill[name])) for name in ('fee', 'spread_cost', 'slippage_cost'))
                                completed += 1
                            samples.append(Decimal(str(event['equity_after'])))
                        mark = Decimal(str(source[row['frame']]['quotes'][0]['price']))
                        holdings = sum(Decimal(str(entry['quantity'])) * mark for entry in positions.values())
                        self.assertAlmostEqual(row['cash'], float(cash), places=9)
                        self.assertAlmostEqual(row['position_value'], float(holdings), places=9)
                        self.assertAlmostEqual(row['equity'], float(cash + holdings), places=9)
                        samples.append(cash + holdings)
                        for equity in samples:
                            peak = max(peak, equity)
                            worst_drawdown = max(worst_drawdown, (peak - equity) / peak)
                        self.assertAlmostEqual(row['max_drawdown'], float(worst_drawdown), places=12)
                    self.assertFalse(positions)
                    summary = evaluation['summary']
                    self.assertAlmostEqual(summary['cash'], float(cash), places=9)
                    self.assertAlmostEqual(summary['net_pnl'], float(net_pnl), places=9)
                    self.assertAlmostEqual(summary['trade_net_pnl'], float(net_pnl), places=9)
                    self.assertAlmostEqual(summary['total_costs'], float(costs), places=9)
                    self.assertAlmostEqual(summary['roi'], float((cash - 1000) / 1000), places=12)
                    self.assertAlmostEqual(summary['max_drawdown'], float(worst_drawdown), places=12)
                    self.assertAlmostEqual(summary['fitness'],
                        float((cash - 1000) / 1000 - 2 * worst_drawdown), places=12)
                    self.assertEqual(summary['num_trades'], completed)
        scores = {row['candidate_id']: row['summary']['fitness'] for row in result['evaluations']['train']}
        self.assertEqual(result['selection']['grid_winner'], min(GRID_IDS, key=lambda ident: (-scores[ident], ident)))

    async def test_ema_entry_uses_quote_after_cross_and_never_consumes_holdout_for_training_fill(self):
        count = WARMUP_MINUTES + 40
        quotes = [100.0] * count
        candles = [100.0] * count
        candles[309] = 105
        quotes[310] = 102
        candles[319] = 90  # Exit signal well before the partition end.
        candles[324] = 200  # Another bullish cross exactly on terminal training frame.
        quotes[325] = 1000  # Would expose a pending-intent partition leak.
        path, _ = self.fixture(quote_prices=quotes, candle_prices=candles)
        result = await run_experiment(path, self.config())
        train = self.evaluations(result, 'train')['fixed-ema-09-21']
        opened = [(row, event) for row in train['ledger'] for event in row['events']
                  if event['kind'] == 'trade_opened']
        self.assertTrue(opened, 'Fixture must exercise a real EMA crossing and fill')
        self.assertEqual(opened[0][0]['frame'], 310)
        self.assertEqual(opened[0][1]['execution']['entry']['reference_price'], 102)
        self.assertEqual(train['ledger'][0]['frame'], 304)
        self.assertEqual(train['ledger'][0]['candle']['completed_bars'], 61)
        self.assertEqual(train['ledger'][-1]['frame'], 324)
        self.assertTrue(train['ledger'][-1]['candle']['bullish'],
                        'The terminal fixture must contain an otherwise actionable crossing')
        self.assertFalse(train['ledger'][-1]['intents_after'])
        self.assertFalse(any(event['kind'] == 'trade_opened' for event in train['ledger'][-1]['events']))
        for partition in ('train', 'holdout'):
            window = result['windows'][partition]
            for evaluation in result['evaluations'][partition]:
                self.assertEqual(evaluation['ledger'][0]['frame'], window['boundary_frame'])
                self.assertEqual(evaluation['ledger'][-1]['frame'], window['end_frame'])
                self.assertEqual(len(evaluation['ledger']), window['end_frame'] - window['boundary_frame'] + 1)
                self.assertEqual(evaluation['ledger'][0]['cash'], 1000)
                self.assertEqual(evaluation['ledger'][0]['position_value'], 0)
                self.assertFalse(evaluation['ledger'][0]['intents_before'])
                self.assertFalse(evaluation['ledger'][0]['events'])
        holdout = self.evaluations(result, 'holdout')['fixed-ema-09-21']
        self.assertFalse(any(event['kind'] == 'trade_opened' for event in holdout['ledger'][1]['events']))

    async def test_protective_death_keeps_real_remaining_cash_without_restart_or_refund(self):
        prices = [100.0] * (WARMUP_MINUTES + 40)
        prices[309], prices[310], prices[311] = 105, 100, 10
        path, _ = self.fixture(quote_prices=prices)
        result = await run_experiment(path, self.config())
        fixed = self.evaluations(result, 'train')['fixed-ema-09-21']
        self.assertAlmostEqual(fixed['summary']['cash'], 775)
        self.assertAlmostEqual(fixed['summary']['net_pnl'], -225)
        died = next(row for row in fixed['ledger'] if any(event['kind'] == 'probe_dead' for event in row['events']))
        self.assertEqual(died['frame'], 311)
        for row in fixed['ledger']:
            if row['frame'] > 311:
                self.assertAlmostEqual(row['cash'], 775)
                self.assertEqual(row['position_value'], 0)
                self.assertFalse(row['events'])
        holdout = self.evaluations(result, 'holdout')['fixed-ema-09-21']
        self.assertEqual(holdout['ledger'][0]['cash'], 1000)

    async def test_terminal_frame_checks_drawdown_retirement_before_liquidation(self):
        quotes = [100.0] * (WARMUP_MINUTES + 40)
        candles = list(quotes)
        candles[309] = 105
        quotes[324] = 99.8  # Below the account drawdown limit, but not the 3% stop.
        path, _ = self.fixture(quote_prices=quotes, candle_prices=candles)
        original_advance = _EmaAccount.advance

        def advance_with_prior_peak(account, tick, frame, **options):
            if (account.definition['id'] == 'fixed-ema-09-21' and frame == 324
                    and options.get('terminal')):
                # Isolate terminal lifecycle handling from how an earlier peak
                # arose. Prior value 1000 is above 80% of 1249.5 (999.6);
                # the terminal 25% holding mark is 999.5, just below it.
                self.assertTrue(account.probe.open_positions)
                self.assertAlmostEqual(account.probe.total_value, 1000)
                account.probe.peak_capital = 1249.5
            return original_advance(account, tick, frame, **options)

        with patch.object(_EmaAccount, 'advance', advance_with_prior_peak):
            result = await run_experiment(path, self.config())
        fixed = self.evaluations(result, 'train')['fixed-ema-09-21']
        terminal = fixed['ledger'][-1]
        self.assertEqual(terminal['state'], 'DEAD')
        self.assertAlmostEqual(terminal['cash'], 999.5)
        self.assertEqual(terminal['position_value'], 0)
        self.assertFalse(terminal['intents_after'])
        kinds = [event['kind'] for event in terminal['events']]
        self.assertEqual(kinds.count('probe_dying'), 1)
        self.assertEqual(kinds.count('probe_dead'), 1)
        self.assertEqual(kinds.count('trade_closed'), 1)
        self.assertNotIn('trade_opened', kinds)
        deaths = [event for event in terminal['events'] if event['kind'] in ('probe_dying', 'probe_dead')]
        self.assertTrue(all(event['reason'] == 'drawdown' for event in deaths))
        self.assertAlmostEqual(fixed['summary']['net_pnl'], -.5)
        self.assertAlmostEqual(fixed['summary']['max_drawdown'], (1249.5 - 999.5) / 1249.5)

    async def test_missing_dataset_asset_is_rejected_before_playback(self):
        path, _ = self.fixture()
        with patch('vonneumann.research.runner.ReplayFeed.get_ticks',
                   side_effect=AssertionError('Missing asset reached playback')):
            with self.assertRaises(ResearchError) as caught:
                await run_experiment(path, self.config(asset='JUP/USDC'))
        self.assertEqual(caught.exception.code, 'research_coverage')

    async def test_cooperative_cancellation_propagates_without_a_partial_result(self):
        path, _ = self.fixture()
        before = {item.relative_to(self.root): item.read_bytes()
                  for item in self.root.rglob('*') if item.is_file()}
        task = asyncio.create_task(run_experiment(path, self.config()))
        # A real event-loop turn lets dataset validation finish and enters the
        # frame loop. Cancellation must then win before a result is produced.
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(task.cancelled())
        self.assertEqual(before, {item.relative_to(self.root): item.read_bytes()
                                  for item in self.root.rglob('*') if item.is_file()})

    async def test_insufficient_warmup_or_window_and_provider_archives_are_rejected(self):
        for count in (304, 305, 344):
            path, _ = self.fixture(count=count)
            with self.subTest(count=count), self.assertRaises(ResearchError):
                await run_experiment(path, self.config())
        meta, rows = provider_bundle()
        destination = self.root / 'provider-shaped-synthetic-test'
        write_dataset(destination, meta, rows)
        with self.assertRaises(ResearchError):
            await run_experiment(destination, self.config())

    async def test_full_frame_count_does_not_substitute_for_candles_available_at_warmup_boundary(self):
        config = self.config()
        count = WARMUP_MINUTES + config.train_minutes + config.holdout_minutes
        rows = frames(count=count)
        delayed = [row['candles'].pop() for row in rows[:WARMUP_MINUTES]]
        rows[WARMUP_MINUTES]['candles'] = delayed + rows[WARMUP_MINUTES]['candles']
        path = self.root / 'late-warmup'
        write_dataset(path, metadata(frames=count), rows)
        with self.assertRaises(ResearchError):
            await run_experiment(path, config)

    async def test_complete_quotes_cannot_hide_missing_trailing_holdout_candles(self):
        config = self.config()
        count = WARMUP_MINUTES + config.train_minutes + config.holdout_minutes
        for missing in (1, 5):
            rows = frames(count=count)
            for row in rows[-missing:]:
                row['candles'] = []
            path = self.root / f'missing-tail-{missing}'
            write_dataset(path, metadata(frames=count), rows)
            with self.subTest(missing=missing), self.assertRaises(ResearchError):
                await run_experiment(path, config)

    async def test_configuration_rejects_malformed_values_before_any_dataset_io(self):
        invalid = [('asset', 'not-supported'), ('asset', True), ('timeframe_minutes', True),
                   ('timeframe_minutes', 4), ('timeframe_minutes', 61), ('timeframe_minutes', 5.5),
                   ('train_minutes', 0), ('train_minutes', True), ('holdout_minutes', -1),
                   ('holdout_minutes', 1.5), ('initial_capital', True), ('initial_capital', 0),
                   ('initial_capital', float('nan')), ('initial_capital', float('inf')),
                   ('random_seed', 1), ('random_seed', '01'), ('random_seed', '-1'),
                   ('random_seed', '18446744073709551616'), ('random_budget', True),
                   ('random_budget', 0), ('random_budget', 21), ('execution', {})]
        with patch('vonneumann.research.runner.ReplayFeed',
                   side_effect=AssertionError('Malformed research config reached dataset I/O')):
            for name, value in invalid:
                with self.subTest(name=name, value=value), self.assertRaises((ResearchError, ValueError)):
                    config = replace(self.config(), **{name: value})
                    await run_experiment(self.root / 'missing-private-dataset', config)
        config = self.config()
        with self.assertRaises(FrozenInstanceError):
            config.random_budget = 2

    async def test_result_identifies_exact_dataset_and_reviewed_engine_source_without_local_paths(self):
        path, _ = self.fixture()
        result = await run_experiment(path, self.config())
        self.assertEqual(result['dataset']['dataset_id'], load_dataset(path).dataset_id)
        files = result['engine']['source_sha256']
        required = {'services/vonneumann/vonneumann/core/probe.py',
                    'services/vonneumann/vonneumann/core/execution.py',
                    'services/vonneumann/vonneumann/market/candles.py',
                    'services/vonneumann/vonneumann/research/runner.py'}
        self.assertTrue(required.issubset(files))
        repository = Path(__file__).resolve().parents[3]
        for relative, expected in files.items():
            self.assertFalse(Path(relative).is_absolute())
            self.assertNotIn('..', Path(relative).parts)
            self.assertEqual(hashlib.sha256((repository / relative).read_bytes()).hexdigest(), expected)
        self.assertNotIn(str(path), json.dumps(result))


if __name__ == '__main__':
    unittest.main()
