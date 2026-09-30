"""Offline cohort scheduling through real controllers, probes, and candle history."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_source_time_controller import ControlledClock

with deny_network():
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.funding import FundingError
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.genome import Genome
    from vonneumann.core.probe import Probe
    from vonneumann.core.strategies.base import EvolutionResult, EvolutionStrategy
    from vonneumann.core.strategies.cma_es import CMAEvolutionStrategy
    from vonneumann.core.types import EventType, ProbeState
    from vonneumann.market.candles import MinuteCandle
    from vonneumann.market.feed import MarketFeedError, MarketTick, QuoteEvidence


ASSET = "SOL/USDC"
START = 1_704_067_200.0


class CohortRecordingStrategy(EvolutionStrategy):
    supports_cohorts = True
    name = "cohort_recording_test"
    label = "Offline cohort strategy"

    def __init__(self):
        self.received = []
        self.aborts = 0
        self.initializations = 0

    def initialize(self, probes, colony_config):
        self.initializations += 1

    def abort_cohort(self):
        self.aborts += 1

    def evolve(self, probes, dead_probes, colony_config):
        self.received.append(tuple(probes))
        children = []
        for probe in probes:
            child = probe.genome
            child.generation += 1
            children.append(child)
        return EvolutionResult(children, [probe.probe_id for probe in probes],
                               {str(i): [p.probe_id] for i, p in enumerate(probes)})


class CandleQuoteFeed:
    """Fresh explicit paper quotes plus real completed, contiguous minute candles."""

    def __init__(self, clock, *, ready=True):
        self.clock = clock
        self.ready = ready
        self.price = 100.0
        self.failure = None
        self.slot = 100
        self.candle_start = int(START) - 120 * 60

    async def get_ticks(self, assets):
        if self.failure is not None:
            raise self.failure
        self.slot += 1
        return {asset: MarketTick(asset, self.price, 1_000.0, self.clock.wall,
                    QuoteEvidence(self.slot, self.clock.wall, self.clock.mono))
                for asset in assets}

    async def get_candles(self, assets, *, warmup=False):
        if not self.ready:
            return []
        end = int(self.clock.wall // 60) * 60
        return [MinuteCandle(asset, start, 100, 100, 100, 100, 10, "offline-cohort")
                for asset in assets for start in range(self.candle_start, end, 60)]


class ControllerCohortTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.clock = ControlledClock()
        self.clock.wall = START
        self.offline_stack.enter_context(patch("vonneumann.market.quote_freshness.time", self.clock))
        self.offline_stack.enter_context(patch("vonneumann.core.probe.time", self.clock))
        self.events = []

    @staticmethod
    def genome(**_):
        return Genome(assets=[ASSET], num_assets=1, timeframe_minutes=5,
                      rsi_period=5, ema_fast=3, ema_slow=10,
                      position_size_pct=.5, stop_loss_pct=.1, take_profit_pct=.2,
                      death_drawdown_pct=.5, benchmark_target_pct=.15,
                      reproduce_target_dollars=50)

    async def controller(self, *, strategy=None, population=2, capital=400,
                         ready=True, horizon=2, lifespan=None, pacing=1000, threshold=1):
        self.feed = CandleQuoteFeed(self.clock, ready=ready)
        strategy = strategy or CohortRecordingStrategy()
        async def event(value):
            self.events.append(value)
        c = GenesisController(self.feed, strategy, A1, USER_A, mode="paper",
            gen0_count=population, max_probes=population, seed_capital=100,
            max_capital=capital, tick_interval_ms=pacing, diversity_threshold=0,
            circuit_breaker_drop_pct=threshold,
            colony_config=ColonyConfig(available_assets=[ASSET],
                enabled_genes=["rsi_oversold", "volume_threshold"],
                reproduction_interval=horizon, max_lifespan_ticks=lifespan),
            on_event=event)
        c._event_time = lambda: datetime.fromtimestamp(self.clock.wall, timezone.utc)
        with patch("vonneumann.core.genesis.random_genome", side_effect=self.genome):
            await c.prepare()
        c.set_lifecycle("running")
        if isinstance(strategy, CMAEvolutionStrategy):
            strategy._optimizer.reseed_rng(1907)
        self.events.clear()
        return c

    async def tick(self, c, seconds=1, *, price=None):
        self.clock.advance(seconds)
        if price is not None:
            self.feed.price = price
        await c._tick_all()

    async def start(self, c):
        await self.tick(c)
        self.assertEqual(c._cohort.phase, "evaluating")
        return c._cohort

    async def complete(self, c, *, extra_delay=0):
        self.assertIsNotNone(c._cohort.ends_at)
        await self.tick(c, c._cohort.ends_at - self.clock.wall + extra_delay)

    async def asked_cma(self, *, threshold=1):
        c = await self.controller(strategy=CMAEvolutionStrategy(), population=4, capital=800,
                                  threshold=threshold)
        await self.start(c)
        await self.complete(c)  # Bootstrap creates the first actual ask batch.
        self.assertIsNotNone(c.strategy._pending_vectors)
        await self.start(c)
        return c

    async def test_warmup_blocks_entries_reproduction_and_lifespan(self):
        c = await self.controller(ready=False, horizon=1, lifespan=1)
        ids = set(c.probes)
        with patch.object(Probe, "_has_entry_signal", return_value=(True, {})), \
             patch.object(Probe, "_should_reproduce", return_value=True):
            for _ in range(5):
                await self.tick(c, 120)
        self.assertEqual(c._cohort.phase, "warming")
        self.assertIsNone(c._cohort.started_at)
        self.assertEqual(set(c.probes), ids)
        self.assertEqual(c.strategy.received, [])
        self.assertTrue(all(not p.open_positions and not p.closed_trades
                            and not p._pending_intents for p in c.live_probes))
        self.assertFalse(any(e.event_type in {EventType.TRADE_OPENED, EventType.PROBE_BORN,
                                             EventType.PROBE_DYING, EventType.PROBE_REPRODUCING}
                             for e in self.events))
        self.feed.ready = True
        await self.start(c)
        self.assertEqual(c._cohort.started_at, self.clock.wall)
        self.assertEqual(set(c.probes), ids)

    async def test_deadline_uses_common_market_time_and_ignores_poll_count(self):
        observations = []
        for pacing, polls in ((100, 120), (5000, 2)):
            self.clock.wall, self.clock.mono = START, 500
            c = await self.controller(pacing=pacing)
            cohort = await self.start(c)
            initial_ids = set(c.probes)
            for _ in range(polls - 1):
                await self.tick(c, 120 / polls)
                self.assertEqual(set(c.probes), initial_ids)
            await self.tick(c, 120 / polls)
            self.assertEqual(len(c.strategy.received), 1)
            results = c.strategy.received[0]
            self.assertEqual(cohort.phase, "completed")
            self.assertTrue(initial_ids.isdisjoint(c.probes))
            observations.append([(r.window_started_at, r.window_ends_at, r.terminated_at,
                                  r.fitness, r.num_trades) for r in results])
        self.assertEqual(observations[0], observations[1])

    async def test_start_boundary_discards_warmup_signal_before_any_entry(self):
        c = await self.controller()
        with patch.object(Probe, "_has_entry_signal", return_value=(True, {})):
            await self.start(c)
        self.assertTrue(all(not p._pending_intents and not p.open_positions
                            and p._signals_after == self.clock.wall for p in c.live_probes))

    async def test_self_reproduction_is_disabled_inside_the_common_window(self):
        c = await self.controller()
        await self.start(c)
        ids = set(c.probes)
        with patch.object(Probe, "_should_reproduce", return_value=True):
            await self.tick(c)
        self.assertEqual(set(c.probes), ids)
        self.assertTrue(all(p.state == ProbeState.OBSERVING for p in c.live_probes))
        self.assertFalse(any(e.event_type == EventType.PROBE_REPRODUCING for e in self.events))

    async def test_lifespan_begins_after_warmup_and_all_dead_cohort_still_finishes(self):
        c = await self.controller(ready=False, lifespan=1)
        await self.tick(c, 600)
        self.feed.ready = True
        cohort = await self.start(c)
        ids = tuple(c.probes)
        await self.tick(c, 59)
        self.assertEqual(tuple(c.probes), ids)
        await self.tick(c, 1)
        self.assertEqual(c.probes, {})
        self.assertEqual(len(cohort.evaluations), 2)
        self.assertEqual(c.strategy.received, [])
        self.assertEqual({r.reason for r in cohort.evaluations}, {"max_lifespan"})
        await self.complete(c)
        self.assertEqual(len(c.strategy.received), 1)
        self.assertEqual(tuple(r.probe_id for r in c.strategy.received[0]), ids)
        self.assertEqual(len(c.live_probes), 2)
        self.assertAlmostEqual(c.active_capital + c.reserve_capital, 400)

    async def test_real_cma_tell_keeps_early_dead_and_all_dead_members(self):
        for dead_count in (1, 4):
            with self.subTest(dead_count=dead_count):
                self.clock.wall, self.clock.mono = START, 500
                c = await self.asked_cma()
                cohort = c._cohort
                original_ids = tuple(c.probes)
                expected = [v.copy() for v in c.strategy._pending_vectors]
                optimizer = c.strategy._optimizer
                for probe in list(c.live_probes)[:dead_count]:
                    probe._trigger_die("fixture_protective_death")
                    await c._handle_die(probe)
                self.assertEqual(len(cohort.evaluations), dead_count)
                with patch.object(optimizer, "tell", wraps=optimizer.tell) as tell:
                    await self.complete(c)
                tell.assert_called_once()
                told = tell.call_args.args[0]
                self.assertEqual(len(told), 4)
                # tell sorts its argument; all scores here tie, preserving order.
                self.assertEqual([v.tolist() for v, _ in told], [v.tolist() for v in expected])
                self.assertEqual(tuple(r.probe_id for r in cohort.evaluations), original_ids)
                self.assertEqual(len(c.live_probes), 4)
                self.assertAlmostEqual(c.active_capital + c.reserve_capital, 800)

    async def test_lifecycle_interruptions_abort_cma_without_telling_partial_results(self):
        for status in ("paused", "risk_halted", "failed", "stopped"):
            with self.subTest(status=status):
                self.clock.wall, self.clock.mono = START, 500
                c = await self.asked_cma()
                cohort, optimizer = c._cohort, c.strategy._optimizer
                with patch.object(optimizer, "tell", wraps=optimizer.tell) as tell:
                    c.set_lifecycle(status)
                tell.assert_not_called()
                self.assertEqual(cohort.phase, "aborted")
                self.assertEqual(cohort.abort_reason, status)
                self.assertEqual(len(cohort.evaluations), 4)
                self.assertTrue(all(r.status == "aborted" and r.fitness is None
                                    for r in cohort.evaluations))
                self.assertIsNone(c.strategy._optimizer)

    async def test_cleanup_aborts_pending_window_without_optimizer_update(self):
        c = await self.asked_cma()
        optimizer = c.strategy._optimizer
        with patch.object(optimizer, "tell", wraps=optimizer.tell) as tell:
            await c.cleanup()
        tell.assert_not_called()
        self.assertEqual(c._cohort.phase, "aborted")
        self.assertEqual(c._cohort.abort_reason, "worker_stopped")

    async def test_real_account_risk_trip_aborts_before_cma_can_tell(self):
        c = await self.asked_cma(threshold=.04)
        cohort, optimizer = c._cohort, c.strategy._optimizer
        for probe in c.live_probes:
            probe._open_position(ASSET, 100, {})
            probe._transition(ProbeState.TRADING)
        with patch.object(optimizer, "tell", wraps=optimizer.tell) as tell:
            await self.tick(c, price=80)
        tell.assert_not_called()
        self.assertTrue(c.circuit_breaker_active)
        self.assertEqual(c.lifecycle_status, "risk_halted")
        self.assertEqual(cohort.phase, "aborted")
        self.assertEqual(cohort.abort_reason, "risk_halted")
        self.assertTrue(all(r.fitness is None for r in cohort.evaluations))
        self.assertAlmostEqual(c.active_capital + c.reserve_capital, 760)

    async def test_resume_replaces_interrupted_accounts_and_preserves_equity(self):
        c = await self.controller()
        cohort = await self.start(c)
        parents = list(c.live_probes)
        probe = parents[0]
        probe._open_position(ASSET, 100, {})
        probe._transition(ProbeState.TRADING)
        await self.tick(c, price=110)
        c.set_lifecycle("paused")
        total = c.active_capital + c.reserve_capital
        old_ids = set(c.probes)
        c.set_lifecycle("running")
        await self.tick(c, price=110)
        self.assertEqual(cohort.phase, "aborted")
        self.assertTrue(old_ids.isdisjoint(c.probes))
        self.assertEqual(c._cohort.phase, "warming")
        self.assertEqual(c.strategy.received, [])
        self.assertEqual(len(probe.closed_trades), 1)
        self.assertAlmostEqual(c.active_capital + c.reserve_capital, total)
        for child in c.live_probes:
            self.assertEqual(child.capital, 100)
            self.assertEqual(child.roi, 0)
            self.assertFalse(child.open_positions or child.closed_trades or child._pending_intents)
            self.assertEqual(child._marks[ASSET], 110)
        await self.start(c)
        self.assertGreater(c._cohort.started_at, cohort.started_at)

    async def test_deadline_uses_first_valid_late_mark_and_new_accounts_receive_it(self):
        c = await self.controller()
        cohort = await self.start(c)
        probe = c.live_probes[0]
        probe._open_position(ASSET, 100, {})
        probe._transition(ProbeState.TRADING)
        nominal_end = cohort.ends_at
        self.feed.price = 110
        await self.complete(c, extra_delay=17)
        result = next(r for r in cohort.evaluations if r.probe_id == probe.probe_id)
        self.assertEqual(result.window_ends_at, nominal_end)
        self.assertEqual(result.terminated_at, nominal_end + 17)
        self.assertAlmostEqual(result.roi, .05)
        self.assertAlmostEqual(result.fitness, .05)
        self.assertEqual(probe.closed_trades[-1].exit_price, 110)
        self.assertTrue(all(p._marks[ASSET] == 110 and not p.open_positions
                            for p in c.live_probes))

    async def test_failed_feed_after_deadline_does_not_score_a_stale_mark(self):
        c = await self.controller()
        cohort = await self.start(c)
        self.feed.failure = MarketFeedError("price_stale")
        with self.assertRaises(MarketFeedError):
            await self.complete(c, extra_delay=5)
        self.assertEqual(cohort.phase, "evaluating")
        self.assertEqual(cohort.evaluations, ())
        self.assertEqual(c.strategy.received, [])
        c.set_lifecycle("failed")
        self.assertEqual(cohort.phase, "aborted")
        self.assertTrue(all(r.fitness is None for r in cohort.evaluations))

    async def test_phenotype_edit_fails_before_any_candidate_is_submitted(self):
        c = await self.controller()
        cohort = await self.start(c)
        ids = tuple(c.probes)
        c.live_probes[-1].genome.rsi_oversold += 1
        with self.assertRaisesRegex(ValueError, "phenotype changed"):
            await self.complete(c)
        self.assertEqual(tuple(c.probes), ids)
        self.assertEqual(cohort.evaluations, ())
        self.assertEqual(c.strategy.received, [])
        self.assertEqual(cohort.phase, "evaluating")

    async def test_completed_candidate_genomes_and_scores_do_not_follow_mutable_parents(self):
        c = await self.controller()
        cohort = await self.start(c)
        parents = list(c.live_probes)
        original = deepcopy(parents[0].genome.to_dict())
        await self.complete(c)
        result = cohort.evaluations[0]
        parents[0].capital = 999
        parents[0].genome.rsi_oversold = 1
        returned = result.genome
        returned.assets.clear()
        returned.rsi_oversold = 0
        self.assertEqual(result.genome.to_dict(), original)
        self.assertEqual(result.fitness, 0)
        self.assertEqual(result.roi, 0)

    async def test_rejected_terminal_identity_cannot_credit_still_owned_dead_cash(self):
        c = await self.controller()
        cohort = await self.start(c)
        probe = c.live_probes[0]
        probe.genome.rsi_oversold += 1
        probe._trigger_die("fixture_protective_death")
        before_reserve = c.reserve_capital
        before_total = c.active_capital + c.reserve_capital
        with self.assertRaisesRegex(ValueError, "phenotype changed"):
            await c._handle_die(probe)
        self.assertIs(c.probes[probe.probe_id], probe)
        self.assertEqual(c.reserve_capital, before_reserve)
        self.assertEqual(c.active_capital + c.reserve_capital, before_total)
        self.assertEqual(cohort.evaluations, ())
        self.assertEqual(c.dead_probes, [])

    async def test_insufficient_replacement_funding_preserves_original_accounts(self):
        c = await self.controller(capital=200)
        cohort = await self.start(c)
        # A valid realized loss leaves insufficient cash for two fresh $100 accounts.
        c.live_probes[0].capital = 90
        ids = tuple(c.probes)
        balances = [p.capital for p in c.live_probes]
        with patch.object(c, "_retire_probe", wraps=c._retire_probe) as retire:
            with self.assertRaises(FundingError) as raised:
                await self.complete(c)
            retire.assert_not_called()
        self.assertEqual(raised.exception.code, "funding_insufficient")
        self.assertEqual(tuple(c.probes), ids)
        self.assertEqual([p.capital for p in c.live_probes], balances)
        self.assertEqual(c.reserve_capital, 0)
        self.assertEqual(len(c.strategy.received), 1)
        c.set_lifecycle("failed")
        self.assertEqual(c.lifecycle_status, "failed")
        self.assertTrue(c.status()["requires_reconciliation"])
        self.assertEqual(cohort.phase, "completed")
        self.assertFalse(any(e.event_type == EventType.PROBE_BORN for e in self.events))


if __name__ == "__main__":
    unittest.main()
