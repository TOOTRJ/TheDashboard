"""Real controller/probe/persister timing with an offline synthetic market."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import random
import unittest
from unittest.mock import patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_repository_security import RecordingDB

with deny_network():
    from vonneumann.core.clock import clock_datetime, timestamp_datetime
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.genome import Genome
    from vonneumann.core.market_validation import MarketValueError
    from vonneumann.core.probe import Probe
    from vonneumann.core.strategies.base import EvolutionResult, EvolutionStrategy
    from vonneumann.core.types import EventType, ProbeState
    from vonneumann.db.repository import EventPersister, VonNeumannRepository
    from vonneumann.market.sim_feed import SimulationFeed


ASSET = "SOL/USDC"
START = 1704067200.0


class FixedStrategy(EvolutionStrategy):
    name = "clock_test"
    label = "Offline clock fixture"

    def initialize(self, probes, colony_config):
        pass

    def evolve(self, probes, dead_probes, colony_config):
        return EvolutionResult([], [])


def genome(**overrides):
    return Genome(**{
        "assets": [ASSET], "num_assets": 1.0, "timeframe_minutes": 5.0,
        "position_size_pct": 0.2, "stop_loss_pct": 0.1, "take_profit_pct": 0.03,
        "benchmark_target_pct": 100.0, "reproduce_target_dollars": 1_000_000.0,
        "death_drawdown_pct": 0.99, **overrides,
    })


class EngineClockTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        original_rng = random.getstate()
        self.addCleanup(random.setstate, original_rng)

    async def replay(self, interval_ms, rng_noise):
        db = RecordingDB()
        with patch("vonneumann.db.repository.get_supabase", return_value=db):
            persister = EventPersister(VonNeumannRepository(USER_A, A1))
        events = []

        async def on_event(event):
            await persister.handle(event)
            events.append(event)

        feed = SimulationFeed(seed=42, start_timestamp=START, drift=0.01,
                              volatility=0, volume_noise=0)
        controller = GenesisController(
            feed, FixedStrategy(), A1, USER_A, gen0_count=2, max_probes=4,
            max_capital=400, seed_capital=100, tick_interval_ms=interval_ms,
            diversity_threshold=0, on_event=on_event,
            colony_config=ColonyConfig(available_assets=[ASSET], reproduction_interval=100),
        )
        with patch("vonneumann.core.genesis.random_genome", side_effect=lambda **_: genome()):
            await controller.prepare()
        controller.snapshot_interval = 3
        controller.set_lifecycle("running")
        actual_tick = controller._tick_all
        prices = []

        async def tick_and_stop():
            # Stand in for a different optimizer's unrelated global RNG usage.
            for _ in range(rng_noise):
                random.random()
                random.gauss(0, 1)
            await actual_tick()
            prices.append(dict(controller._latest_prices))
            if controller.tick_count == 20:
                controller._running = False

        sleeps = []

        async def record_pacing(seconds):
            sleeps.append(seconds)

        # Force a known signal policy so this test isolates clock/plumbing from
        # indicator thresholds; actual candle boundaries and delayed fills remain real.
        with patch.object(controller, "_tick_all", side_effect=tick_and_stop), \
             patch("vonneumann.core.genesis.asyncio.sleep", side_effect=record_pacing), \
             patch.object(Probe, "_has_entry_signal", return_value=(True, {})), \
             patch.object(Probe, "_has_exit_signal", return_value=False):
            await controller._tick_loop()

        # IDs and cosmetic names remain deliberately nondeterministic. Compare
        # semantic ledger fields, not a false claim of a byte-identical run.
        rows = []
        for call in db.calls:
            if call["table"] == "vn_trades":
                fields = {k: v for k, v in call["fields"].items()
                          if k not in {"id", "probe_id"}}
                rows.append(fields)
        trace = [(e.event_type.value, e.timestamp.isoformat(),
                  {k: v for k, v in e.data.items() if k != "trade_id"})
                 for e in events if e.event_type in {EventType.TRADE_OPENED, EventType.TRADE_CLOSED}]
        return controller, events, rows, trace, prices, sleeps

    async def test_playback_intervals_and_optimizer_rng_do_not_change_market_or_trade_clock(self):
        fast = await self.replay(100, 0)
        slow = await self.replay(5_000, 50)
        self.assertTrue(fast[2], "Fixture must exercise real trade persistence")
        self.assertEqual(fast[2:5], slow[2:5])
        self.assertEqual(fast[5], [0.1] * 20)
        self.assertEqual(slow[5], [5.0] * 20)
        for controller, events, *_ in (fast, slow):
            self.assertEqual(controller.status()["market_elapsed_secs"], 21 * 60)
            births = [e for e in events if e.event_type == EventType.PROBE_BORN]
            self.assertEqual(len(births), 2)
            self.assertTrue(all(e.timestamp == timestamp_datetime(START) for e in births))
            self.assertTrue(all(e.data["born_at"] == e.timestamp.isoformat() for e in births))
            snapshots = [e for e in events if e.event_type == EventType.FITNESS_SNAPSHOT]
            self.assertTrue(snapshots)
            self.assertTrue(all(e.timestamp == timestamp_datetime(START + (e.data["tick"] + 1) * 60)
                                for e in snapshots))
            for probe in controller.live_probes:
                self.assertTrue(probe.closed_trades)
                self.assertTrue(all(t.closed_at > t.opened_at for t in probe.closed_trades))

    async def test_service_uptime_and_pause_do_not_advance_synthetic_time(self):
        controller, *_ = await self.replay(100, 0)
        clock_before = controller.market_feed.current_timestamp
        controller.pause()
        baseline = controller._wall_started_monotonic
        with patch("vonneumann.core.genesis.time.monotonic", return_value=baseline + 12):
            first = controller.status()
        with patch("vonneumann.core.genesis.time.monotonic", return_value=baseline + 50_000):
            second = controller.status()
        self.assertEqual((first["uptime_secs"], second["uptime_secs"]), (12, 50_000))
        for key in ("market_time", "market_elapsed_secs", "simulation_spec"):
            self.assertEqual(first[key], second[key])
        self.assertEqual(controller.market_feed.current_timestamp, clock_before)
        self.assertEqual(first["clock_basis"], "synthetic_market")
        self.assertEqual(first["simulation_spec"]["seed"], "42")
        controller.resume()
        self.assertEqual(controller.market_feed.current_timestamp, clock_before)

    async def test_retirement_children_and_generation_timestamps_use_current_market_time(self):
        controller, events, *_ = await self.replay(100, 0)
        parents = list(controller.live_probes)
        children = [genome(generation=1, parent_ids=[p.probe_id]) for p in parents]
        now = timestamp_datetime(controller.market_feed.current_timestamp)
        await controller._apply_replacement(EvolutionResult(children, [p.probe_id for p in parents]))
        self.assertTrue(all(p.born_at == now for p in controller.live_probes))
        stats = [e for e in events if e.event_type == EventType.GENERATION_COMPLETE]
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0].timestamp, now)
        self.assertEqual(stats[0].data["started_at"], timestamp_datetime(START).isoformat())
        self.assertEqual(stats[0].data["ended_at"], now.isoformat())
        retirement = [e for e in events if e.event_type == EventType.PROBE_REPRODUCING]
        self.assertTrue(retirement)
        self.assertTrue(all(e.timestamp == now for e in retirement))

    async def test_paper_feed_without_simulation_clock_keeps_real_event_time(self):
        feed = object()
        controller = GenesisController(feed, FixedStrategy(), A1, USER_A, mode="paper")
        before, now, after = datetime.now(timezone.utc), controller._event_time(), datetime.now(timezone.utc)
        self.assertLessEqual(before, now)
        self.assertLessEqual(now, after)
        self.assertEqual(controller.status()["clock_basis"], "wall")
        self.assertIsNone(controller.status()["market_time"])


class ProbeClockTests(OfflineTestMixin, unittest.TestCase):
    def test_probe_birth_open_close_and_death_follow_injected_clock(self):
        current = [datetime(2001, 1, 1, tzinfo=timezone.utc)]
        probe = Probe(genome(), 100, clock=lambda: current[0])
        self.assertEqual(probe.born_at, current[0])
        probe.set_funded()
        probe.set_observing()
        probe._transition(ProbeState.TRADING)
        current[0] += timedelta(minutes=5)
        opened = probe._open_position(ASSET, 100, {})
        trade = probe.open_positions[ASSET]
        self.assertEqual(opened.timestamp, current[0])
        self.assertEqual(trade.opened_at, current[0])
        current[0] += timedelta(minutes=2)
        closed = probe._close_position(ASSET, 105, "TAKE_PROFIT")
        self.assertEqual(closed.timestamp, current[0])
        self.assertEqual(trade.closed_at, current[0])
        current[0] += timedelta(minutes=1)
        dying = probe._trigger_die("test_clock")[-1]
        self.assertEqual(dying.timestamp, current[0])
        self.assertEqual(probe.died_at, current[0])
        self.assertEqual(dying.data["died_at"], current[0].isoformat())

    def test_invalid_clock_cannot_mutate_a_trade_or_cash_balance(self):
        current = [datetime(2001, 1, 1, tzinfo=timezone.utc)]
        probe = Probe(genome(), 100, clock=lambda: current[0])
        probe._open_position(ASSET, 100, {})
        before = deepcopy((probe.open_positions, probe.capital, probe.closed_trades))
        current[0] = datetime(2001, 1, 1)  # No implicit local-time conversion.
        with self.assertRaises(MarketValueError):
            probe._close_position(ASSET, 105, "TAKE_PROFIT")
        self.assertEqual((probe.open_positions, probe.capital, probe.closed_trades), before)

    def test_clock_boundaries_reject_unrepresentable_unix_and_naive_time(self):
        for value in (-1, False, float("nan"), float("inf"), 1e100, "100"):
            with self.subTest(value=value), self.assertRaises(MarketValueError):
                timestamp_datetime(value)
        self.assertEqual(timestamp_datetime(0), datetime(1970, 1, 1, tzinfo=timezone.utc))
        with self.assertRaises(MarketValueError):
            clock_datetime(datetime(2001, 1, 1))
        with self.assertRaises(MarketValueError):
            clock_datetime(datetime.min.replace(tzinfo=timezone(timedelta(hours=1))))
