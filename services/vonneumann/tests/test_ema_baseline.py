"""EMA-only experiment behavior through canonical history, real probes and solvers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import importlib
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_repository_security import RecordingDB

with deny_network():
    from pydantic import ValidationError
    from vonneumann.core.colony_config import ColonyConfig, GeneOverride, PRESET_CONFIGS
    from vonneumann.core.funding import FundingError
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.genome import Genome, NUMERIC_GENES
    from vonneumann.core.probe import Probe
    from vonneumann.core.signal_profile import EMA_BASELINE_PROFILE, LEGACY_PROFILE
    from vonneumann.core.strategies import get_strategy
    from vonneumann.core.strategies.base import EvolutionResult
    from vonneumann.core.types import EventType, ProbeState
    from vonneumann.market.candles import CandleHistory, MinuteCandle
    from vonneumann.market.feed import MarketTick, QuoteEvidence
    from vonneumann.market.sim_feed import SimulationFeed
    from vonneumann.server.auth import VerifiedUser
    from vonneumann.server.models import StartRequest, build_colony_config
    app_module = importlib.import_module('vonneumann.server.app')


ASSET = 'SOL/USDC'
ORIGIN = 1_704_067_200  # UTC midnight, aligned to every tested five-minute bar.
SOLVERS = ('genetic_algorithm', 'differential_evolution', 'cma_es', 'particle_swarm')


def baseline_config():
    return build_colony_config(StartRequest(preset=EMA_BASELINE_PROFILE,
        colony_config={'reproduction_interval': 3,
                       'gene_overrides': {'timeframe_minutes': {'fixed': 5.0}}}))


def decimal_ema(prices, period):
    """Independent high-precision SMA seed and weighted recurrence oracle."""
    with localcontext() as context:
        context.prec = 70
        values = [Decimal(str(value)) for value in prices]
        average = sum(values[:period]) / Decimal(period)
        weight = Decimal(2) / Decimal(period + 1)
        for value in values[period:]:
            average = weight * value + (1 - weight) * average
        return float(average)


class BaselineConfigurationTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.offline_stack.enter_context(patch.dict(PRESET_CONFIGS, {
            EMA_BASELINE_PROFILE: deepcopy(PRESET_CONFIGS[EMA_BASELINE_PROFILE])}))

    def test_omitted_profile_preserves_legacy_semantics_and_old_config_roundtrips(self):
        self.assertEqual(build_colony_config(StartRequest()).strategy_profile, LEGACY_PROFILE)
        self.assertEqual(ColonyConfig.from_dict({}).strategy_profile, LEGACY_PROFILE)
        self.assertEqual(Probe(Genome(), 100).strategy_profile, LEGACY_PROFILE)
        old = {'enabled_genes': ['rsi_oversold'], 'available_assets': [ASSET]}
        restored = ColonyConfig.from_dict(old)
        self.assertEqual(restored.strategy_profile, LEGACY_PROFILE)
        self.assertEqual(ColonyConfig.from_dict(restored.to_dict()).to_dict(), restored.to_dict())

    def test_preset_has_two_integer_search_dimensions_and_fixed_experiment_controls(self):
        config = build_colony_config(StartRequest(preset=EMA_BASELINE_PROFILE))
        domains = config.resolve_gene_domains()
        self.assertEqual({name for name, domain in domains.items() if domain.evolvable},
                         {'ema_fast', 'ema_slow'})
        self.assertTrue(domains['ema_fast'].integer and domains['ema_slow'].integer)
        self.assertEqual(config.available_assets, [ASSET])
        self.assertEqual(domains['num_assets'].default, 1)
        self.assertEqual(domains['max_open_positions'].default, 1)
        self.assertEqual(domains['timeframe_minutes'].default, 15)
        self.assertIsNone(config.max_lifespan_ticks)
        self.assertEqual(config.reproduction_interval, 1440)

    def test_conflicting_or_ambiguous_baseline_requests_are_rejected(self):
        changes = [
            {'strategy_profile': LEGACY_PROFILE}, {'strategy_profile': 'ema'},
            {'strategy_profile': None}, {'strategy_profile': True},
            {'enabled_genes': None}, {'enabled_genes': []},
            {'enabled_genes': ['ema_fast']},
            {'enabled_genes': ['ema_fast', 'ema_slow', 'rsi_period']},
            {'enabled_genes': ['ema_fast', 'ema_fast']},
            {'available_assets': None}, {'available_assets': [ASSET, 'JUP/USDC']},
            {'max_lifespan_ticks': 0}, {'max_lifespan_ticks': 100},
            {'reproduction_interval': True}, {'reproduction_interval': 0},
            {'gene_overrides': {'max_open_positions': {'fixed': 2.0}}},
        ]
        for custom in changes:
            with self.subTest(custom=custom), self.assertRaises(ValidationError):
                StartRequest(preset=EMA_BASELINE_PROFILE, colony_config=custom)

    def test_narrowed_and_fixed_ema_controls_keep_profile_and_do_not_mutate_preset(self):
        before = deepcopy(PRESET_CONFIGS[EMA_BASELINE_PROFILE].to_dict())
        request = StartRequest(preset=EMA_BASELINE_PROFILE, colony_config={
            'gene_overrides': {'ema_fast': {'fixed': 5.0},
                               'ema_slow': {'min': 15.0, 'max': 20.0, 'default': 17.0}}})
        config = build_colony_config(request)
        restored = ColonyConfig.from_dict(json.loads(json.dumps(config.to_dict())))
        self.assertEqual(restored.to_dict(), config.to_dict())
        self.assertEqual(restored.resolve_gene_domains()['ema_fast'].default, 5)
        self.assertFalse(restored.is_gene_evolvable('ema_fast'))
        self.assertTrue(restored.is_gene_evolvable('ema_slow'))
        config.available_assets[0] = 'JUP/USDC'
        config.gene_overrides['ema_slow'].max = 19
        self.assertEqual(PRESET_CONFIGS[EMA_BASELINE_PROFILE].to_dict(), before)

    def test_internal_configuration_also_rejects_invalid_profile_and_age_policy(self):
        for profile in ('invalid', True, None):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                ColonyConfig(strategy_profile=profile).resolve_gene_domains()
        config = baseline_config()
        for horizon in (True, 0, 1.5, 1_000_001):
            with self.subTest(horizon=horizon), self.assertRaises(ValueError):
                replace(config, reproduction_interval=horizon).resolve_gene_domains()

    def test_serialized_profile_lists_are_detached_in_both_directions(self):
        config = baseline_config()
        encoded = config.to_dict()
        restored = ColonyConfig.from_dict(encoded)
        encoded['available_assets'][0] = 'JUP/USDC'
        encoded['enabled_genes'].append('rsi_period')
        for candidate in (config, restored):
            self.assertEqual(candidate.available_assets, [ASSET])
            self.assertEqual(candidate.enabled_genes, ['ema_fast', 'ema_slow'])


class BaselineProbeTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.history = CandleHistory([ASSET])
        self.now = float(ORIGIN)
        self.bar_count = 0

    def bars(self, closes):
        candles = []
        for price in closes:
            for minute in range(5):
                start = ORIGIN + self.bar_count * 300 + minute * 60
                candles.append(MinuteCandle(ASSET, start, price, price, price, price,
                                           0, 'offline-ema-baseline'))
            self.bar_count += 1
        self.now = float(ORIGIN + self.bar_count * 300)
        self.history.ingest(candles, available_at=self.now)
        return self.history.latest(ASSET, 5)

    def probe(self, *, fast=3, slow=10, mode='simulation'):
        genome = Genome(assets=[ASSET], num_assets=1, timeframe_minutes=5,
                        ema_fast=fast, ema_slow=slow, position_size_pct=.25,
                        stop_loss_pct=.03, take_profit_pct=.07, max_open_positions=1,
                        benchmark_target_pct=.15, reproduce_target_dollars=50)
        probe = Probe(genome, 100, mode=mode, strategy_profile=EMA_BASELINE_PROFILE,
                      clock=lambda: datetime.fromtimestamp(self.now, timezone.utc),
                      candle_history=self.history)
        probe.set_funded()
        probe.set_observing()
        return probe

    def quote(self, probe, price=100, *, stamp=None, receipt=None):
        evidence = QuoteEvidence(1, self.now, receipt) if receipt is not None else None
        probe.on_quote(MarketTick(ASSET, price, 0,
                                 self.now if stamp is None else stamp, evidence))

    def test_zero_volume_real_cross_opens_and_closes_without_any_rsi_computation(self):
        self.bars([100] * 60)
        probe = self.probe()
        with patch.object(probe, '_compute_rsi', side_effect=AssertionError('RSI feature is disabled')):
            self.bars([101])
            self.quote(probe, 100)
            self.assertTrue(probe.evaluation_ready(self.now))
            self.assertEqual(probe.tick(), [])
            self.assertEqual(probe._pending_intents[ASSET].action, 'entry')
            self.now += 1
            self.quote(probe, 102)
            events = probe.tick()
            self.assertEqual([e.event_type for e in events], [EventType.TRADE_OPENED])
            trade = probe.open_positions[ASSET]
            self.assertEqual(trade.entry_price, 102)
            self.assertIsNone(trade.signal_rsi)
            self.assertIsNone(trade.signal_volume_ratio)
            self.bars([99])
            self.quote(probe, 102)
            self.assertEqual(probe.tick(), [])
            self.assertEqual(probe._pending_intents[ASSET].action, 'exit')
            self.now += 1
            self.quote(probe, 103)
            events = probe.tick()
            self.assertEqual([e.data.get('exit_reason') for e in events], ['SIGNAL_EXIT'])
            self.assertEqual(trade.exit_price, 103)

    def test_equality_and_sustained_above_are_not_new_crossings(self):
        self.bars([100] * 60)
        probe = self.probe()
        self.bars([100])
        self.assertFalse(probe._has_entry_signal(ASSET)[0])
        self.assertFalse(probe._has_exit_signal(ASSET))
        self.bars([101])
        self.assertTrue(probe._has_entry_signal(ASSET)[0])
        self.assertFalse(probe._has_exit_signal(ASSET))
        self.bars([102])
        self.assertFalse(probe._has_entry_signal(ASSET)[0])
        self.quote(probe)
        self.assertEqual(probe.tick(), [])
        self.assertFalse(probe._pending_intents)

    def test_bearish_cross_can_leave_previous_equality(self):
        self.bars([100] * 60)
        probe = self.probe()
        self.bars([99])
        self.assertTrue(probe._has_exit_signal(ASSET))
        self.assertFalse(probe._has_entry_signal(ASSET)[0])

    def test_tiny_price_ema_signal_and_trade_provenance_keep_full_precision(self):
        self.bars([1e-12] * 60)
        probe = self.probe()
        self.bars([1.01e-12])
        self.quote(probe, 1e-12)
        probe.tick()
        self.now += 1
        self.quote(probe, 1.02e-12)
        self.assertEqual(len(probe.tick()), 1)
        trade = probe.open_positions[ASSET]
        self.assertGreater(trade.signal_ema_fast, trade.signal_ema_slow)
        self.assertGreater(trade.signal_ema_slow, 0)
        self.assertAlmostEqual(trade.signal_ema_fast / 1e-12, 1.005, places=13)
        self.assertAlmostEqual(trade.signal_ema_slow / 1e-12, 1 + .01 * 2 / 11, places=13)

    def test_exact_61_bar_warmup_is_independent_of_sampled_slow_period(self):
        self.bars([100] * 60)
        probes = [self.probe(slow=slow) for slow in (10, 15, 60)]
        for probe in probes:
            self.assertFalse(probe.evaluation_ready(self.now))
            self.assertFalse(probe._has_entry_signal(ASSET)[0])
        self.bars([101])
        for probe in probes:
            self.assertTrue(probe.evaluation_ready(self.now))
            self.assertTrue(probe._has_entry_signal(ASSET)[0])
            self.assertFalse(probe.evaluation_ready(self.now + 301))

    def test_recursive_current_and_previous_ema_share_full_origin_and_are_immutable(self):
        prices = [500 + (i % 11) for i in range(80)] + [100 + (i % 7) for i in range(140)]
        snapshot = self.bars(prices)
        self.assertEqual(snapshot.completed_count, 220)
        self.assertEqual(len(snapshot.closes), 64)
        self.assertEqual(snapshot.previous_end, snapshot.end - 300)
        for period in (3, 10, 21, 60):
            self.assertAlmostEqual(snapshot.emas[period], decimal_ema(prices, period), places=11)
            self.assertAlmostEqual(snapshot.previous_emas[period], decimal_ema(prices[:-1], period), places=11)
        self.assertGreater(abs(snapshot.emas[60] - decimal_ema(prices[-64:], 60)), 1)
        previous = dict(snapshot.previous_emas)
        with self.assertRaises(TypeError):
            snapshot.previous_emas[3] = 999
        external = dict(previous)
        copied = replace(snapshot, previous_emas=external)
        external[3] = 999
        self.assertEqual(dict(copied.previous_emas), previous)
        self.bars([90, 110])
        self.assertEqual(dict(snapshot.previous_emas), previous)

    def test_paper_cross_waits_for_quote_source_and_receipt_after_signal_availability(self):
        self.bars([100] * 60)
        probe = self.probe(mode='paper')
        self.bars([101])
        end = self.now
        self.quote(probe, stamp=end + 1, receipt=10)
        with patch('vonneumann.core.probe.time.monotonic', return_value=20):
            self.assertEqual(probe.tick(), [])
        self.now += 2
        for stamp, receipt in ((end + 2, 15), (end, 21)):
            self.quote(probe, stamp=stamp, receipt=receipt)
            self.assertEqual(probe.tick(), [])
            self.assertFalse(probe.open_positions)
        self.quote(probe, 101, stamp=end + 2, receipt=21)
        self.assertEqual([e.event_type for e in probe.tick()], [EventType.TRADE_OPENED])

    def test_birth_and_catchup_skip_old_crosses_but_next_contiguous_cross_is_eligible(self):
        self.bars([100] * 60)
        parent = self.probe()
        self.bars([101, 102])
        self.quote(parent)
        self.assertEqual(parent.tick(), [])
        self.assertFalse(parent._pending_intents)
        child = self.probe()
        self.quote(child)
        child.tick()
        self.assertFalse(child._pending_intents)
        for price in (90, 110):
            self.bars([price])
            for probe in (parent, child):
                self.quote(probe)
                probe.tick()
        for probe in (parent, child):
            self.assertEqual(probe._pending_intents[ASSET].action, 'entry')
            self.assertFalse(probe.open_positions)

    def test_child_born_on_crossing_bar_cannot_replay_that_entry(self):
        self.bars([100] * 60 + [101])
        child = self.probe()
        self.assertTrue(child._has_entry_signal(ASSET)[0], 'The birth bar really contains a cross')
        self.quote(child)
        self.assertEqual(child.tick(), [])
        self.now += 1
        self.quote(child, 101)
        self.assertEqual(child.tick(), [])
        self.assertFalse(child._pending_intents)
        self.assertFalse(child.open_positions)

    def test_quote_risk_exits_still_work_without_any_indicator_warmup(self):
        for price, reason in ((96, 'STOP_LOSS'), (108, 'TAKE_PROFIT')):
            with self.subTest(reason=reason):
                probe = self.probe()
                self.quote(probe)
                probe._open_position(ASSET, 100, {})
                probe._transition(ProbeState.TRADING)
                self.assertFalse(probe.evaluation_ready(self.now))
                self.now += 1
                self.quote(probe, price)
                with patch.object(probe, '_compute_rsi', side_effect=AssertionError('RSI disabled')):
                    events = probe.tick(allow_reproduction=False)
                self.assertEqual([e.data.get('exit_reason') for e in events], [reason])
                self.assertFalse(probe.open_positions)


class BaselineControllerTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.offline_stack.enter_context(patch.dict(PRESET_CONFIGS, {
            EMA_BASELINE_PROFILE: deepcopy(PRESET_CONFIGS[EMA_BASELINE_PROFILE])}))

    async def controller(self, algorithm='genetic_algorithm', *, config=None):
        async def ignore(_):
            pass
        controller = GenesisController(SimulationFeed(seed=729), get_strategy(algorithm), A1, USER_A,
            gen0_count=8, max_probes=8, max_capital=10000, seed_capital=100,
            tick_interval_ms=100, colony_config=config or baseline_config(), on_event=ignore,
            circuit_breaker_drop_pct=1., search_seed='19')
        await controller.prepare()
        controller.set_lifecycle('running')
        return controller

    async def test_all_four_real_solvers_keep_only_two_ema_parameters_variable_across_generations(self):
        for algorithm in SOLVERS:
            with self.subTest(algorithm=algorithm):
                controller = await self.controller(algorithm)
                first = next(iter(controller.probes.values())).genome
                fixed = {name: getattr(first, name) for name in NUMERIC_GENES
                         if name not in {'ema_fast', 'ema_slow'}}
                observed_pairs = set()
                generation_pairs = []
                previous = -1
                generations = []
                for _ in range(500):
                    if controller._evaluation_iteration != previous:
                        previous = controller._evaluation_iteration
                        generations.append(previous)
                        generation_pairs.append(tuple((probe.genome.ema_fast, probe.genome.ema_slow)
                                                      for probe in controller.probes.values()))
                        self.assertEqual(len(controller.probes), 8)
                        for probe in controller.probes.values():
                            self.assertEqual(probe.strategy_profile, EMA_BASELINE_PROFILE)
                            self.assertEqual(probe.genome.assets, [ASSET])
                            self.assertEqual({name: getattr(probe.genome, name) for name in fixed}, fixed)
                            fast, slow = probe.genome.ema_fast, probe.genome.ema_slow
                            self.assertEqual(fast, int(fast))
                            self.assertEqual(slow, int(slow))
                            self.assertTrue(3 <= fast <= 12 < 15 <= slow <= 60)
                            observed_pairs.add((fast, slow))
                    if len(generations) == 4:
                        break
                    await controller._tick_all()
                self.assertEqual(len(generations), 4, 'Real cohort windows must complete')
                self.assertGreater(len(observed_pairs), 1)
                self.assertTrue(any(pairs != generation_pairs[0] for pairs in generation_pairs[1:]),
                                'Completed optimizer steps must actually propose new EMA candidates')
                status = controller.status()
                self.assertEqual(status['strategy_profile'], EMA_BASELINE_PROFILE)
                self.assertFalse(status['signal_policy']['rsi_enabled'])
                self.assertFalse(status['signal_policy']['volume_enabled'])
                self.assertEqual(status['signal_policy']['warmup_completed_bars'], 61)

    async def test_malformed_replacement_cannot_retire_accounts_or_liquidate_positions(self):
        controller = await self.controller()
        parent = next(iter(controller.probes.values()))
        parent._open_position(ASSET, controller._latest_prices[ASSET], {})
        parent._transition(ProbeState.TRADING)
        before_ids = set(controller.probes)
        before_reserve, before_cash = controller.reserve_capital, parent.capital
        before_trade = parent.open_positions[ASSET]
        for field, value in (('position_size_pct', .9), ('timeframe_minutes', 10),
                             ('rsi_oversold', 35), ('ema_fast', 12.5)):
            with self.subTest(field=field):
                child = deepcopy(parent.genome)
                child.generation += 1
                setattr(child, field, value)
                result = EvolutionResult([child], [parent.probe_id], {'0': [parent.probe_id]})
                with self.assertRaises(FundingError):
                    await controller._apply_replacement(result)
                self.assertEqual(set(controller.probes), before_ids)
                self.assertEqual(controller.reserve_capital, before_reserve)
                self.assertEqual(parent.capital, before_cash)
                self.assertIs(parent.open_positions[ASSET], before_trade)
                self.assertIsNone(before_trade.closed_at)
                self.assertEqual(parent.state, ProbeState.TRADING)
                self.assertFalse(controller.dead_probes)

    async def test_controller_detaches_baseline_config_from_later_caller_edits(self):
        config = baseline_config()
        controller = await self.controller(config=config)
        config.strategy_profile = LEGACY_PROFILE
        config.available_assets[0] = 'JUP/USDC'
        config.gene_overrides['position_size_pct'].fixed = .9
        self.assertEqual(controller.colony_config.strategy_profile, EMA_BASELINE_PROFILE)
        self.assertEqual(controller.colony_config.available_assets, [ASSET])
        self.assertEqual(controller.colony_config.gene_overrides['position_size_pct'].fixed, .25)

    async def test_real_api_persists_profile_in_resolved_config_and_runtime(self):
        db = RecordingDB()
        async def create(**kwargs):
            self.persisted_controller = GenesisController(
                SimulationFeed(seed=4), get_strategy(kwargs['strategy_name']),
                kwargs['colony_id'], kwargs['user_id'], mode=kwargs['mode'],
                gen0_count=kwargs['gen0_count'], max_probes=kwargs['max_probes'],
                colony_config=kwargs['colony_config'], search_seed=kwargs['search_seed'],
                on_event=kwargs['on_event'], persist_risk_status=kwargs['persist_status'])
            await self.persisted_controller.prepare()
            self.persisted_controller.set_lifecycle('running')
        request = StartRequest(preset=EMA_BASELINE_PROFILE, gen0_count=2, max_probes=2)
        with patch('vonneumann.db.repository.get_supabase', return_value=db), \
             patch.object(app_module, 'uuid', SimpleNamespace(uuid4=lambda: A1)), \
             patch.object(app_module.ws_manager, 'broadcast_to_user', new=AsyncMock()), \
             patch.object(app_module.colony_manager, 'create_colony', new=AsyncMock(side_effect=create)):
            response = await app_module._start_colony(request, VerifiedUser(USER_A, int(time.time()) + 3600))
            await self.persisted_controller._publish_evaluation()
        self.assertEqual(response['config']['colony_config']['strategy_profile'], EMA_BASELINE_PROFILE)
        rows = [call for call in db.calls if call['table'] == 'vn_colonies']
        inserted = next(call['fields']['config'] for call in rows if call['operation'] == 'insert')
        self.assertEqual(inserted['colony_config']['strategy_profile'], EMA_BASELINE_PROFILE)
        saved = [call['fields']['config'] for call in rows if call['operation'] == 'update'][-1]
        runtime = json.loads(json.dumps(saved, allow_nan=False))['runtime']
        self.assertEqual(runtime['strategy_profile'], EMA_BASELINE_PROFILE)
        self.assertEqual(runtime['signal_policy'], inserted['signal_policy'])
        self.assertFalse(runtime['signal_policy']['rsi_enabled'])
        self.assertFalse(runtime['signal_policy']['volume_enabled'])
        restored = ColonyConfig.from_dict(saved['colony_config'])
        self.assertEqual(restored.strategy_profile, EMA_BASELINE_PROFILE)
        self.assertEqual(set(restored.enabled_genes), {'ema_fast', 'ema_slow'})


if __name__ == '__main__':
    unittest.main()
