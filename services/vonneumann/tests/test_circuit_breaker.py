"""Offline account-risk limits exercised through real controllers and probes."""

from copy import deepcopy
from datetime import datetime, timezone
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_source_time_controller import ControlledClock, FixedStrategy, MutableSourceFeed, ASSET, OTHER_ASSET
from tests.test_probe_candles import History

with deny_network():
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.colony_manager import ColonyManager, ColonyLifecycleError
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.genome import Genome
    from vonneumann.core.probe import _SignalIntent
    from vonneumann.core.risk_control import RiskRecoveryError
    from vonneumann.core.types import EventType, ProbeState
    from vonneumann.db.repository import PersistenceError
    from vonneumann.market.feed import MarketFeedError


class CircuitBreakerTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    async def recovery_publication_failure(self, *, timeout):
        await self.controller()
        self.invest()
        await self.tick(60)
        await self.tick(80)
        baseline = self.c.status()["risk_control"]["baseline_equity"]
        owned = list(self.c.probes)
        manager = ColonyManager()
        manager._colonies[A1] = self.c
        manager._locks[A1] = asyncio.Lock()
        manager._persist[A1] = self.c._persist_risk_status
        entered, release = asyncio.Event(), asyncio.Event()
        async def failed_publish(_action):
            entered.set()
            await release.wait()
            raise RuntimeError("Injected notification failure")
        self.c._publish_risk_change = failed_publish
        self.c._tick_all = AsyncMock()
        with patch("vonneumann.core.colony_manager.QUIESCE_TIMEOUT_SECONDS", .05 if timeout else 1):
            recovery = asyncio.create_task(manager.recover_colony(
                A1, self.c.status()["risk_control"]["trip_id"]))
            await entered.wait()
            # The real loop queues on the recovery lock before its failing
            # child task can wake the manager. This exposed an extra-tick race.
            loop = asyncio.create_task(self.c.run())
            manager._tasks[A1] = loop
            await asyncio.sleep(0)
            if not timeout:
                release.set()
            with self.assertRaises(ColonyLifecycleError) as raised:
                await recovery
        self.assertFalse(raised.exception.conflict)
        self.c._tick_all.assert_not_awaited()
        self.assertEqual(self.c.lifecycle_status, "failed")
        self.assertEqual(list(self.c.probes), owned)
        self.assertTrue(self.c.status()["requires_reconciliation"])
        self.assertEqual(self.saved[-1]["status"], "failed")
        self.assertEqual(self.saved[-1]["risk_control"]["baseline_equity"], baseline)
        self.assertEqual(self.saved[-1]["risk_control"]["recovery_count"], 1)
        self.assertIsNotNone(self.saved[-1]["risk_control"]["last_recovered_at"])
        self.assertTrue(loop.done())

    async def test_failed_recovery_publication_cannot_release_waiting_tick(self):
        await self.recovery_publication_failure(timeout=False)

    async def test_cancelled_recovery_publication_cannot_release_waiting_tick(self):
        await self.recovery_publication_failure(timeout=True)

    async def test_account_valuation_failure_preserves_completed_protective_closes(self):
        await self.controller()
        self.invest()
        self.c._account_equity = lambda: (_ for _ in ()).throw(MarketFeedError("price_stale"))
        with self.assertRaises(MarketFeedError):
            await self.tick(49)
        closes = [event for event in self.events if event.event_type == EventType.TRADE_CLOSED]
        self.assertEqual(len(closes), 2)
        self.assertTrue(all(not probe.open_positions for probe in self.probes))
        self.assertFalse(any(event.event_type == EventType.CIRCUIT_BREAKER for event in self.events))

    def setUp(self):
        super().setUp()
        self.clock = ControlledClock()
        self.offline_stack.enter_context(patch("vonneumann.market.quote_freshness.time", self.clock))
        self.offline_stack.enter_context(patch("vonneumann.core.probe.time", self.clock))
        self.events, self.saved = [], []

    async def controller(self, *, threshold=.2, capital=200):
        self.feed = MutableSourceFeed(self.clock)
        async def event(value):
            self.events.append(value)
        async def save(value):
            self.saved.append(deepcopy(value))
        self.c = GenesisController(self.feed, FixedStrategy(), A1, USER_A,
            mode="paper", gen0_count=2, seed_capital=100, max_capital=capital,
            max_probes=6, diversity_threshold=0, circuit_breaker_drop_pct=threshold,
            colony_config=ColonyConfig(available_assets=[ASSET, OTHER_ASSET]),
            on_event=event, persist_risk_status=save)
        self.c._event_time = lambda: datetime.fromtimestamp(self.clock.wall, timezone.utc)
        def genome(**_):
            return Genome(assets=[ASSET, OTHER_ASSET], num_assets=2, timeframe_minutes=1,
                position_size_pct=.5, max_open_positions=2, stop_loss_pct=.5,
                take_profit_pct=.5, death_drawdown_pct=.9,
                benchmark_target_pct=100, reproduce_target_dollars=1000)
        with patch("vonneumann.core.genesis.random_genome", side_effect=genome):
            await self.c.prepare()
        self.c.set_lifecycle("running")
        self.probes = list(self.c.live_probes)
        self.events.clear()
        return self.c

    def invest(self):
        for probe in self.probes:
            self.assertIsNotNone(probe._open_position(ASSET, 100, {}))
            probe._transition(ProbeState.TRADING)

    async def tick(self, price=100):
        self.clock.advance(1)
        self.feed.response = self.feed.prices(price, slot=100 + self.c.tick_count + 1)
        await self.c._tick_all()

    def trip_events(self):
        return [e for e in self.events if e.event_type == EventType.CIRCUIT_BREAKER
                and e.data["action"] == "tripped"]

    async def test_exact_account_boundary_cancels_pending_entries_before_execution(self):
        await self.controller()
        self.invest()
        for probe in self.probes:
            probe._pending_intents[OTHER_ASSET] = _SignalIntent(
                self.clock.wall - 1, self.clock.mono - 1, "entry", None, {})
        self.c.reproduction_interval = 1
        with patch.object(self.c.strategy, "evolve", wraps=self.c.strategy.evolve) as evolve:
            await self.tick(60)  # 100 cash + 60 marked exposure = 160 / 200.
            evolve.assert_not_called()
        self.assertEqual(self.c.lifecycle_status, "risk_halted")
        self.assertTrue(self.c.circuit_breaker_active)
        self.assertEqual(self.c.status()["total_capital"], 160)
        self.assertTrue(all(set(p.open_positions) == {ASSET} for p in self.probes))
        self.assertTrue(all(not p._pending_intents for p in self.probes))
        self.assertEqual(len(self.trip_events()), 1)
        self.assertEqual(self.saved[-1]["status"], "risk_halted")
        self.assertEqual(self.saved[-1]["risk_control"]["trip_equity"], 160)

    async def test_below_boundary_continues_normal_decisions(self):
        await self.controller()
        self.invest()
        self.c.reproduction_interval = 1
        with patch.object(self.c.strategy, "evolve", wraps=self.c.strategy.evolve) as evolve:
            await self.tick(61)
            evolve.assert_called_once()
        self.assertFalse(self.c.circuit_breaker_active)
        self.assertEqual(self.trip_events(), [])

    async def test_halted_ticks_manage_positions_without_candle_dependency_or_repeat_trip(self):
        await self.controller()
        self.invest()
        await self.tick(60)
        self.feed.get_candles = AsyncMock(side_effect=MarketFeedError("candles_unavailable"))
        await self.tick(49)  # Both valid stop losses must still close.
        self.feed.get_candles.assert_not_awaited()
        self.assertTrue(all(not p.open_positions for p in self.probes))
        self.assertEqual(sum(len(p.closed_trades) for p in self.probes), 2)
        self.assertEqual(self.c.status()["total_capital"], 149)
        self.assertEqual(len(self.trip_events()), 1)
        self.assertEqual(self.c.lifecycle_status, "risk_halted")

    async def test_take_profit_and_terminal_drawdown_remain_available_while_halted(self):
        await self.controller()
        self.invest()
        await self.tick(60)
        await self.tick(160)
        self.assertTrue(all(not p.open_positions for p in self.probes))
        self.assertEqual({t.exit_reason for p in self.probes for t in p.closed_trades}, {"TAKE_PROFIT"})
        self.assertTrue(self.c.circuit_breaker_active)  # No automatic reset on rebound.

    async def test_dead_halted_population_reclaims_once_and_never_refills(self):
        await self.controller()
        self.invest()
        for probe in self.probes:
            probe.genome.death_drawdown_pct = .15
        await self.tick(60)
        self.assertEqual(self.c.probes, {})
        self.assertEqual(len(self.c.dead_probes), 2)
        self.assertEqual(self.c.reserve_capital, 160)
        await self.c._handle_die(self.probes[0])
        await self.tick(60)
        self.assertEqual(self.c.reserve_capital, 160)
        self.assertEqual(self.c.lifecycle_status, "risk_halted")
        self.assertFalse(any(e.event_type == EventType.PROBE_BORN for e in self.events))
        with self.assertRaises(RiskRecoveryError) as raised:
            await self.c.recover_circuit_breaker(self.c.status()["risk_control"]["trip_id"])
        self.assertEqual(raised.exception.code, "risk_no_candidates")

    async def test_profitable_sibling_cannot_reproduce_after_account_breach(self):
        await self.controller(threshold=.3)
        self.probes[0].capital = 20
        self.probes[1].capital = 120
        self.probes[1].genome.benchmark_target_pct = .1
        self.probes[1]._transition(ProbeState.TRADING)
        await self.tick()
        self.assertTrue(self.c.circuit_breaker_active)
        self.assertFalse(any(e.event_type == EventType.PROBE_REPRODUCING for e in self.events))
        self.assertEqual(len(self.c.probes), 2)

    async def test_account_reserve_and_recycled_allocations_do_not_change_denominator(self):
        await self.controller(threshold=.3, capital=10000)
        self.probes[0].capital = 50
        self.c.total_deployed = 1e12
        await self.tick()
        self.assertFalse(self.c.circuit_breaker_active)
        risk = self.c.status()["risk_control"]
        self.assertEqual(risk["baseline_equity"], 10000)
        self.assertAlmostEqual(risk["observed_loss_fraction"], .005)
        self.c.reserve_capital = 0
        await self.tick()
        self.assertTrue(self.c.circuit_breaker_active)
        self.assertEqual(self.c.status()["risk_control"]["baseline_equity"], 10000)

    async def test_recovery_rejects_boundary_wrong_trip_and_stale_quotes_without_clearing(self):
        await self.controller()
        self.invest()
        await self.tick(60)
        trip = self.c.status()["risk_control"]["trip_id"]
        for supplied, expected in (("wrong", "risk_trip_changed"), (trip, "risk_loss_unrecovered")):
            with self.assertRaises(RiskRecoveryError) as raised:
                await self.c.recover_circuit_breaker(supplied)
            self.assertEqual(raised.exception.code, expected)
        await self.tick(80)
        self.clock.advance(31)
        with self.assertRaises(RiskRecoveryError) as raised:
            await self.c.recover_circuit_breaker(trip)
        self.assertEqual(raised.exception.code, "risk_quotes_unavailable")
        self.assertTrue(self.c.circuit_breaker_active)
        self.assertEqual(self.c.lifecycle_status, "risk_halted")

    async def test_valid_recovery_is_acknowledged_before_clearing_and_preserves_baseline(self):
        await self.controller()
        self.invest()
        await self.tick(60)
        trip = self.c.status()["risk_control"]["trip_id"]
        await self.tick(80)
        async def save(status):
            self.assertTrue(self.c.circuit_breaker_active)
            self.assertEqual(self.c.lifecycle_status, "risk_halted")
            self.saved.append(deepcopy(status))
        self.c._persist_risk_status = save
        await self.c.recover_circuit_breaker(trip)
        risk = self.c.status()["risk_control"]
        self.assertEqual(self.saved[-1]["status"], "running")
        self.assertFalse(self.c.circuit_breaker_active)
        self.assertEqual(self.c.lifecycle_status, "running")
        self.assertEqual((risk["baseline_equity"], risk["trip_equity"], risk["recovery_count"]), (200, 160, 1))
        self.assertTrue(all(p._signals_after == self.clock.wall for p in self.probes))
        await self.tick(60)
        self.assertNotEqual(self.c.status()["risk_control"]["trip_id"], trip)

    async def test_slow_recovery_ack_compensates_to_halt_before_any_new_risk(self):
        await self.controller()
        self.invest()
        await self.tick(60)
        await self.tick(80)
        async def save(status):
            self.saved.append(deepcopy(status))
            if status["status"] == "running":
                self.clock.advance(31)
        self.c._persist_risk_status = save
        with self.assertRaises(RiskRecoveryError):
            await self.c.recover_circuit_breaker(self.c.status()["risk_control"]["trip_id"])
        self.assertEqual([x["status"] for x in self.saved[-2:]], ["running", "risk_halted"])
        self.assertTrue(self.c.circuit_breaker_active)
        self.assertEqual(self.c.status()["risk_control"]["recovery_count"], 0)

    async def test_recovery_history_or_persistence_failure_retains_halt(self):
        await self.controller()
        self.invest()
        await self.tick(60)
        await self.tick(80)
        trip = self.c.status()["risk_control"]["trip_id"]
        with patch.object(self.feed, "get_candles", new=AsyncMock(side_effect=MarketFeedError("candles_unavailable"))):
            with self.assertRaises(RiskRecoveryError) as raised:
                await self.c.recover_circuit_breaker(trip)
            self.assertEqual(raised.exception.code, "risk_history_unavailable")
        self.c._persist_risk_status = AsyncMock(side_effect=PersistenceError("update_colony_status"))
        with self.assertRaises(PersistenceError):
            await self.c.recover_circuit_breaker(trip)
        self.assertTrue(self.c.circuit_breaker_active)
        self.assertFalse(self.c.state_persisted)
        self.assertEqual(self.c.status()["risk_control"]["recovery_count"], 0)

    async def test_trip_write_failure_keeps_positions_and_latch_without_new_entries(self):
        await self.controller()
        self.invest()
        self.c._persist_risk_status = AsyncMock(side_effect=PersistenceError("update_colony_status"))
        with self.assertRaises(PersistenceError):
            await self.tick(60)
        self.assertTrue(self.c.circuit_breaker_active)
        self.assertTrue(all(p.open_positions for p in self.probes))
        self.assertFalse(self.c.state_persisted)
        self.assertEqual(self.trip_events(), [])

    async def test_hard_lifespan_precedes_profit_reproduction_and_pending_entry(self):
        await self.controller()
        self.c.colony_config.max_lifespan_ticks = 1
        probe = self.probes[0]
        probe.capital = 120
        probe.genome.benchmark_target_pct = .1
        probe._transition(ProbeState.TRADING)
        probe._pending_intents[ASSET] = _SignalIntent(self.clock.wall - 1, self.clock.mono - 1, "entry", None, {})
        await self.tick()
        self.assertEqual(probe.death_reason, "max_lifespan")
        own = [e.event_type for e in self.events if e.probe_id == probe.probe_id]
        self.assertNotIn(EventType.TRADE_OPENED, own)
        self.assertNotIn(EventType.PROBE_REPRODUCING, own)

    async def test_recovery_signal_boundary_discards_old_candles_but_allows_new_signals(self):
        await self.controller()
        probe = self.probes[0]
        history = History()
        probe.genome.ema_fast, probe.genome.ema_slow = 2, 3
        probe.genome.rsi_period = 5
        probe.genome.rsi_oversold = 30
        probe.genome.volume_threshold = 1.5
        probe.attach_candle_history(history)
        probe.reset_signal_boundary(self.clock.wall)
        history.put(end=int(self.clock.wall))
        probe._discover_candle_signals()
        self.assertEqual(probe._pending_intents, {})
        self.clock.advance(60)
        history.put(end=int(self.clock.wall))
        probe.on_quote(self.feed.prices(slot=101)[ASSET])
        probe._discover_candle_signals()
        self.assertIn(ASSET, probe._pending_intents)
