"""Actual-controller replay and quote-age boundaries with owned input sources.

These are offline runtime tests, not an exact-money transition planner or a
claim that a frozen planning clock authorizes a later database commit.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import random
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network

with deny_network():
    import numpy as np
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.decision_inputs import DecisionInputError, DecisionInputs
    from vonneumann.core.engine_state import capture_engine_state
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.genome import Genome
    from vonneumann.core.strategies import get_strategy
    from vonneumann.core.types import EventType, ProbeState
    from vonneumann.market.feed import MarketFeedError, QuoteEvidence
    from vonneumann.market.sim_feed import SimulationFeed
    from tests.test_search_replay import ALGORITHMS, make_controller
    from tests.test_ema_baseline import baseline_config
    from tests.test_source_time_controller import ASSET, OTHER_ASSET, FixedStrategy, MutableSourceFeed


class OwnedSources:
    def __init__(self):
        self.wall = 1_800_000_000.0
        self.mono = 500.0
        self.identities = 0
        self.names = []

    def wall_time(self):
        return datetime.fromtimestamp(self.wall, timezone.utc)

    def monotonic(self):
        return self.mono

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds

    def next_id(self):
        self.identities += 1
        return str(UUID(int=self.identities))

    def name(self, generation):
        self.names.append(generation)
        return f"Replay generation {generation}, birth {len(self.names)}"


def no_global_decision_sources():
    """Raise on fallback draws; never seed or replace another run's state."""
    stack = ExitStack()
    for target in ("uuid.uuid4", "vonneumann.core.genesis.generate_probe_name",
                   "vonneumann.core.names.generate_probe_name", "numpy.random.seed"):
        stack.enter_context(patch(target, side_effect=AssertionError(f"Global source used: {target}")))
    for name in ("seed", "random", "uniform", "randint", "randrange", "sample", "choice", "gauss"):
        stack.enter_context(patch(f"random.{name}", side_effect=AssertionError(f"Global random.{name} used")))
    return stack


async def controller_trace(algorithm, *, yield_events):
    sources = OwnedSources()
    feed = SimulationFeed(seed=729)
    events = []

    async def persist(event):
        events.append(deepcopy(event.to_ws_message()))
        if yield_events:
            await asyncio.sleep(0)

    experiment = baseline_config()
    experiment.reproduction_interval = 50
    controller = GenesisController(feed, get_strategy(algorithm), A1, USER_A,
        gen0_count=8, max_probes=8, max_capital=10000, seed_capital=100,
        colony_config=experiment, on_event=persist, circuit_breaker_drop_pct=1.,
        event_clock=lambda: datetime.fromtimestamp(feed.current_timestamp, timezone.utc),
        wall_clock=sources.wall_time, monotonic_clock=sources.monotonic,
        id_factory=sources.next_id, name_factory=sources.name)
    await controller.prepare()
    controller.set_lifecycle("running")
    populations = [list(controller.probes)]
    for _ in range(500):
        iteration = controller._evaluation_iteration
        sources.advance(.25)
        await controller._tick_all()
        if controller._evaluation_iteration != iteration:
            populations.append(list(controller.probes))
        if len(populations) == 4:
            break
    else:
        raise AssertionError("Controller did not complete three actual replacement windows")

    natural_events = len(events)
    # Exercise the same injected identity source for a loss latch after replay.
    # The earlier trace contains ordinary signal-driven entries and exits.
    for probe in controller.live_probes:
        asset = probe.genome.assets[0]
        if probe.state == ProbeState.OBSERVING:
            probe._transition(ProbeState.TRADING)
        event = probe._open_position(asset, controller._latest_prices[asset], {})
        if event is not None:
            await controller._emit(event)
        for held in probe.open_positions:
            controller._latest_prices[held] = .000000001
            probe.on_price_update(held, .000000001, 1000.)
    controller.circuit_breaker_drop_pct = .000001
    if not controller._check_circuit_breaker():
        raise AssertionError("Controlled account loss did not latch")
    await controller._publish_risk_change("tripped")
    return {
        "events": events, "natural_events": natural_events, "populations": populations,
        "status": controller.status(), "names": sources.names,
        "live": [probe.summary() for probe in controller.live_probes],
        "dead": [probe.summary() for probe in controller.dead_probes],
        "trades": [asdict(trade) for probe in [*controller.probes.values(), *controller.dead_probes]
                   for trade in [*probe.closed_trades, *probe.open_positions.values()]],
    }


class ControllerDecisionSourceTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    async def test_all_four_real_solvers_replay_unmodified_ids_names_events_and_trades(self):
        random_before = random.getstate()
        numpy_before = np.random.get_state()
        with no_global_decision_sources():
            for algorithm in ALGORITHMS:
                with self.subTest(algorithm=algorithm):
                    first = await controller_trace(algorithm, yield_events=False)
                    second = await controller_trace(algorithm, yield_events=True)
                    # No UUID/name/timestamp normalization hides a source leak.
                    self.assertEqual(first, second)
                    ordinary = first["events"][:first["natural_events"]]
                    kinds = [event["type"] for event in ordinary]
                    self.assertIn(EventType.TRADE_OPENED.value, kinds)
                    self.assertIn(EventType.TRADE_CLOSED.value, kinds)
                    self.assertGreater(kinds.count(EventType.PROBE_BORN.value), 8)
                    self.assertEqual(len(first["populations"]), 4)
                    self.assertGreater(len(set(first["names"])), 1)
                    self.assertTrue(first["status"]["circuit_breaker"])
                    trip = first["status"]["risk_control"]
                    self.assertIsNotNone(trip["trip_id"])
                    self.assertIsNotNone(trip["tripped_at"])
                    self.assertEqual(first["status"]["clock_basis"], "explicit_decision")
        self.assertEqual(random.getstate(), random_before)
        numpy_after = np.random.get_state()
        self.assertEqual(numpy_after[0], numpy_before[0])
        np.testing.assert_array_equal(numpy_after[1], numpy_before[1])
        self.assertEqual(numpy_after[2:], numpy_before[2:])

    async def test_fresh_input_cursors_reproduce_real_births_and_fills_without_exhaustion_fallback(self):
        # prepare() consumes the feed's first one-minute frame before ingesting
        # its candle; fixed decision time must cover that completed observation.
        event_at = datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc)
        wall_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ids = tuple(str(UUID(int=value)) for value in range(1, 4))
        inputs = DecisionInputs(event_at, wall_at, 500.0, ids=ids,
                                names=((0, "First"), (0, "Second"), (0, "Unfunded")))
        runs = []
        with no_global_decision_sources():
            for _ in range(2):
                cursor = inputs.new_cursor()
                events = []

                async def persist(event):
                    events.append(deepcopy(event.to_ws_message()))

                controller = GenesisController(SimulationFeed(seed=729),
                    get_strategy("genetic_algorithm"), A1, USER_A, gen0_count=2,
                    max_probes=4, max_capital=400., seed_capital=100.,
                    colony_config=baseline_config(), on_event=persist,
                    event_clock=cursor.event_time, wall_clock=cursor.wall_time,
                    monotonic_clock=cursor.monotonic_time, id_factory=cursor.next_id,
                    name_factory=cursor.probe_name)
                await controller.prepare()
                first, second = controller.live_probes
                self.assertEqual([first.probe_id, second.probe_id], list(ids[:2]))
                self.assertEqual([first.probe_name, second.probe_name], ["First", "Second"])
                self.assertEqual(first.born_at, event_at)
                self.assertEqual(controller.started_at, wall_at)
                first._transition(ProbeState.TRADING)
                await controller._emit(first._open_position(ASSET, 100., {}))
                trade = first.open_positions[ASSET]
                self.assertEqual(trade.trade_id, ids[2])
                self.assertEqual(trade.opened_at, event_at)
                await controller._emit(first._close_position(ASSET, 110., "SIGNAL_EXIT"))
                self.assertEqual(trade.closed_at, event_at)
                before = (controller.reserve_capital, controller.total_deployed,
                          list(controller.probes), deepcopy(events))
                with self.assertRaises(DecisionInputError):
                    await controller._spawn_probe(deepcopy(first.genome), 100.)
                self.assertEqual((controller.reserve_capital, controller.total_deployed,
                                  list(controller.probes), events), before)
                # The same exhausted identity source also fails before another
                # fill can debit an already-owned account.
                cash = second.capital
                with self.assertRaises(DecisionInputError):
                    second._open_position(ASSET, 100., {})
                self.assertEqual(second.capital, cash)
                self.assertEqual(second.open_positions, {})
                runs.append((events, asdict(trade), controller.status()))
        self.assertEqual(runs[0], runs[1])

    async def test_engine_snapshot_omits_operational_sources_without_calling_them(self):
        controller = await make_controller("genetic_algorithm")

        def forbidden(*_):
            raise AssertionError("Snapshot evaluated an operational source")

        controller_fields = {"_event_clock", "_wall_clock", "_monotonic_clock",
                             "_id_factory", "_name_factory"}
        probe_fields = {"_id_factory", "_monotonic_clock"}
        for field in controller_fields:
            setattr(controller, field, forbidden)
        for probe in controller.probes.values():
            for field in probe_fields:
                setattr(probe, field, forbidden)
        snapshot = await capture_engine_state(controller)
        first, second = snapshot.fork(), snapshot.fork()
        self.assertFalse(controller_fields.intersection(first.attributes))
        self.assertEqual(list(first.probes), list(controller.probes))
        for data in first.probes.values():
            self.assertFalse(probe_fields.intersection(data.attributes))
        self.assertIsNot(first.strategy, controller.strategy)
        self.assertIsNot(first.strategy, second.strategy)
        first.attributes["reserve_capital"] = 0.
        self.assertEqual(second.attributes["reserve_capital"], controller.reserve_capital)

    @staticmethod
    def genome(**_):
        return Genome(assets=[ASSET, OTHER_ASSET], num_assets=2., position_size_pct=.5,
            max_open_positions=2., stop_loss_pct=.1, take_profit_pct=.2,
            timeframe_minutes=1., rsi_period=5., benchmark_target_pct=100.,
            reproduce_target_dollars=1000., death_drawdown_pct=.99)

    async def paper_controller(self):
        sources = OwnedSources()
        feed = MutableSourceFeed(sources)
        events = []

        async def persist(event):
            events.append(deepcopy(event.to_ws_message()))

        controller = GenesisController(feed, FixedStrategy(), A1, USER_A, mode="paper",
            gen0_count=2, max_probes=6, max_capital=400., seed_capital=100.,
            diversity_threshold=0., colony_config=ColonyConfig(available_assets=[ASSET, OTHER_ASSET]),
            on_event=persist, event_clock=sources.wall_time, wall_clock=sources.wall_time,
            monotonic_clock=sources.monotonic, id_factory=sources.next_id,
            name_factory=sources.name)
        with patch("vonneumann.core.genesis.random_genome", side_effect=self.genome):
            await controller.prepare()
        controller.set_lifecycle("running")
        events.clear()
        return controller, feed, sources, events

    def open_position(self, probe):
        probe._transition(ProbeState.TRADING)
        self.assertIsNotNone(probe._open_position(ASSET, 100., {}))
        return probe.open_positions[ASSET]

    async def test_injected_clocks_are_resampled_after_protective_event_await(self):
        controller, feed, sources, events = await self.paper_controller()
        stopping, later = controller.live_probes
        trade = self.open_position(stopping)
        feed.response = feed.prices(80.)

        async def delayed_persistence(event):
            events.append(event.to_ws_message())
            if event.event_type == EventType.TRADE_CLOSED:
                await asyncio.sleep(0)
                sources.advance(31.)

        controller._on_event = delayed_persistence
        with patch.object(later, "tick", wraps=later.tick) as decision, \
             patch.object(controller.strategy, "evolve", wraps=controller.strategy.evolve) as evolution:
            with self.assertRaises(MarketFeedError) as raised:
                await controller._tick_all()
            self.assertEqual(raised.exception.code, "price_stale")
            decision.assert_not_called()
            evolution.assert_not_called()
        self.assertEqual(stopping.closed_trades, [trade])
        self.assertEqual(stopping.capital, 90.)
        self.assertEqual(later.open_positions, {})
        self.assertEqual([event["data"]["trade_id"] for event in events
                          if event["type"] == "trade_closed"], [trade.trade_id])
        with self.assertRaises(MarketFeedError):
            controller._mark_price(ASSET)

    async def test_injected_clocks_are_resampled_after_price_publication_await(self):
        controller, _, sources, events = await self.paper_controller()
        first, later = controller.live_probes
        trade = self.open_position(later)
        controller.tick_count = 4
        controller.colony_config.max_lifespan_ticks = 5

        async def delayed_persistence(event):
            events.append(event.to_ws_message())
            if event.event_type == EventType.PRICE_UPDATE:
                await asyncio.sleep(0)
                sources.advance(31.)

        controller._on_event = delayed_persistence
        with patch.object(first, "tick", wraps=first.tick) as decision:
            with self.assertRaises(MarketFeedError) as raised:
                await controller._tick_all()
            self.assertEqual(raised.exception.code, "price_stale")
            decision.assert_not_called()
        self.assertEqual(later.open_positions, {ASSET: trade})
        self.assertIsNone(trade.exit_price)
        self.assertEqual(controller.dead_probes, [])

    async def test_explicit_monotonic_age_survives_wall_clock_rollback_and_receipt_refresh(self):
        controller, feed, sources, _ = await self.paper_controller()
        original = dict(feed.response)
        sources.mono += 20.
        sources.wall += 5.
        feed.response = {asset: replace(tick, evidence=QuoteEvidence(101, sources.wall, sources.mono))
                         for asset, tick in original.items()}
        await controller._tick_all()
        sources.mono += 11.
        sources.wall -= 2.
        feed.response = {asset: replace(tick, evidence=QuoteEvidence(102, sources.wall, sources.mono))
                         for asset, tick in original.items()}
        with self.assertRaises(MarketFeedError) as raised:
            await controller._tick_all()
        self.assertEqual(raised.exception.code, "price_stale")
        self.assertEqual(controller._latest_prices, {})

    async def test_bad_or_duplicate_birth_sources_do_not_debit_reserve(self):
        controller, _, sources, events = await self.paper_controller()
        existing = next(iter(controller.probes))
        cases = (("_name_factory", lambda _: ""),
                 ("_name_factory", lambda _: "bad\nname"),
                 ("_name_factory", lambda _: "x" * 129),
                 ("_id_factory", lambda: "{" + existing + "}"),
                 ("_id_factory", lambda: existing))
        before = (controller.reserve_capital, controller.total_deployed,
                  dict(controller._generation_probe_counts), list(controller.probes), deepcopy(events))
        for field, factory in cases:
            with self.subTest(field=field):
                with patch.object(controller, field, factory):
                    with self.assertRaises(ValueError):
                        await controller._spawn_probe(self.genome(), 100.)
                self.assertEqual((controller.reserve_capital, controller.total_deployed,
                                  dict(controller._generation_probe_counts), list(controller.probes), events),
                                 before)
        self.assertGreaterEqual(sources.identities, 2)

    async def test_failed_risk_identity_keeps_halt_and_prevents_new_allocation(self):
        controller, feed, _, _ = await self.paper_controller()
        probe = controller.live_probes[0]
        trade = self.open_position(probe)
        feed.response = feed.prices(1.)
        ticks, errors = controller._validate_ticks([ASSET, OTHER_ASSET], feed.response)
        self.assertEqual(errors, [])
        controller._latest_ticks = ticks
        controller._latest_prices = {asset: tick.price for asset, tick in ticks.items()}
        for candidate in controller.live_probes:
            for tick in ticks.values():
                candidate.on_quote(tick)
        controller.circuit_breaker_drop_pct = .01
        reserve = controller.reserve_capital
        with patch.object(controller, "_id_factory", side_effect=ValueError("input allocation exhausted")):
            with self.assertRaises(ValueError):
                controller._check_circuit_breaker()
        self.assertTrue(controller.circuit_breaker_active)
        self.assertEqual(controller.lifecycle_status, "risk_halted")
        self.assertFalse(controller.state_persisted)
        self.assertIsNone(await controller._spawn_probe(self.genome(), 100.))
        self.assertEqual(controller.reserve_capital, reserve)
        self.assertEqual(probe.open_positions, {ASSET: trade})


if __name__ == "__main__":
    unittest.main()
