"""Real-controller regressions for paper quote age at mutation boundaries."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.genome import Genome
    from vonneumann.core.strategies.base import EvolutionResult, EvolutionStrategy
    from vonneumann.core.types import EventType, ProbeState
    from vonneumann.market.feed import MarketFeedError, MarketTick, QuoteEvidence
    from vonneumann.market.candles import MinuteCandle


ASSET = "SOL/USDC"
OTHER_ASSET = "JUP/USDC"


class ControlledClock:
    def __init__(self):
        self.wall = 1_700_000_000.0
        self.mono = 500.0

    def time(self):
        return self.wall

    def monotonic(self):
        return self.mono

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds


class FixedStrategy(EvolutionStrategy):
    name = "source_time_test"
    label = "Offline source-time strategy"

    def initialize(self, probes, colony_config):
        pass

    def evolve(self, probes, dead_probes, colony_config):
        return EvolutionResult([], [])


class MutableSourceFeed:
    def __init__(self, clock):
        self.clock = clock
        self.failure = None
        self.response = self.prices()

    def prices(self, price=100.0, *, age=0.0, slot=100):
        return {asset: MarketTick(asset, price, 1_000.0, self.clock.wall - age,
                                 QuoteEvidence(slot, self.clock.wall, self.clock.mono))
                for asset in (ASSET, OTHER_ASSET)}

    async def get_candles(self, assets, *, warmup=False):
        return []  # This quote/accounting fixture deliberately has no signal history.

    async def get_ticks(self, assets):
        if self.failure is not None:
            raise self.failure
        return self.response


class SourceTimeControllerTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.clock = ControlledClock()
        self.offline_stack.enter_context(patch("vonneumann.market.quote_freshness.time", self.clock))
        self.events = []
        self.offline_stack.enter_context(patch("vonneumann.core.probe.time", self.clock))

    @staticmethod
    def genome(**kwargs):
        return Genome(
            assets=[ASSET, OTHER_ASSET], num_assets=2.0,
            position_size_pct=0.5, max_open_positions=2.0,
            stop_loss_pct=0.1, take_profit_pct=0.2,
            timeframe_minutes=1.0, rsi_period=5.0,
            benchmark_target_pct=100.0, reproduce_target_dollars=1_000.0,
            death_drawdown_pct=0.99,
        )

    async def controller(self):
        feed = MutableSourceFeed(self.clock)

        async def persist(event):
            self.events.append(event)

        controller = GenesisController(
            feed, FixedStrategy(), A1, USER_A, mode="paper", gen0_count=2,
            max_probes=6, max_capital=400.0, seed_capital=100.0,
            diversity_threshold=0.0,
            colony_config=ColonyConfig(available_assets=[ASSET, OTHER_ASSET]),
            on_event=persist,
        )
        with patch("vonneumann.core.genesis.random_genome", side_effect=self.genome):
            await controller.prepare()
        for probe in controller.live_probes:
            probe._clock = lambda: datetime.fromtimestamp(self.clock.wall, timezone.utc)
            for asset in probe.genome.assets:
                probe.on_price_update(asset, 100.0, 1_000.0)
        self.events.clear()
        return controller, feed, list(controller.live_probes)

    def open_position(self, probe, asset=ASSET):
        if probe.state == ProbeState.OBSERVING:
            probe._transition(ProbeState.TRADING)
        self.assertIsNotNone(probe._open_position(asset, 100.0, {}))
        return probe.open_positions[asset]

    def expire_after(self, controller, event_type):
        async def persist(event):
            self.events.append(event)
            if event.event_type == event_type:
                self.clock.advance(31)
        controller._on_event = persist

    def assert_no_new_exposure_or_evolution(self, original_ids, controller):
        self.assertEqual(set(controller.probes), original_ids)
        self.assertEqual(controller.dead_probes, [])
        self.assertFalse(any(event.event_type in {
            EventType.TRADE_OPENED, EventType.PROBE_BORN, EventType.PROBE_REPRODUCING,
        } for event in self.events))

    async def test_stale_asset_does_not_prevent_fresh_siblings_final_stop(self):
        controller, feed, (stale, healthy) = await self.controller()
        stale_trade = self.open_position(stale, OTHER_ASSET)
        healthy_trade = self.open_position(healthy)
        original_ids = set(controller.probes)
        old_buffer = stale._marks.get(OTHER_ASSET)
        feed.response = feed.prices(80)
        feed.response[OTHER_ASSET] = feed.prices(80, age=31)[OTHER_ASSET]
        controller.reproduction_interval = 1
        with patch.object(controller.strategy, "evolve", wraps=controller.strategy.evolve) as evolve:
            with self.assertRaises(MarketFeedError):
                await controller._tick_all()
            evolve.assert_not_called()
        self.assertEqual(stale.open_positions, {OTHER_ASSET: stale_trade})
        self.assertEqual(stale._marks.get(OTHER_ASSET), old_buffer)
        self.assertEqual(healthy.closed_trades, [healthy_trade])
        self.assertEqual(healthy.capital, 90)
        self.assertNotIn(OTHER_ASSET, controller._latest_prices)
        self.assert_no_new_exposure_or_evolution(original_ids, controller)

    async def test_adapter_partial_failure_preserves_only_fresh_risk_observations(self):
        controller, feed, (stale, healthy) = await self.controller()
        stale_trade = self.open_position(stale, OTHER_ASSET)
        healthy_trade = self.open_position(healthy)
        fresh = feed.prices(80)[ASSET]
        # Controller validates adapter evidence again, including erroneous entries
        # in valid_ticks; the exception is never authority to trust an old mark.
        old = feed.prices(80, age=31)[OTHER_ASSET]
        failure = MarketFeedError("price_stale", valid_ticks={ASSET: fresh, OTHER_ASSET: old})
        feed.failure = failure
        with self.assertRaises(MarketFeedError):
            await controller._tick_all()
        self.assertEqual(stale.open_positions, {OTHER_ASSET: stale_trade})
        self.assertEqual(healthy.closed_trades, [healthy_trade])
        self.assert_no_new_exposure_or_evolution({stale.probe_id, healthy.probe_id}, controller)

    async def test_paper_ticks_without_source_evidence_cannot_trade(self):
        controller, feed, probes = await self.controller()
        feed.response = {asset: replace(tick, evidence=None)
                         for asset, tick in feed.response.items()}
        with patch.object(probes[0], "tick", wraps=probes[0].tick) as decision:
            with self.assertRaises(MarketFeedError):
                await controller._tick_all()
            decision.assert_not_called()
        self.assertEqual(controller._latest_prices, {})
        self.assert_no_new_exposure_or_evolution(set(controller.probes), controller)

    async def test_source_slot_regression_is_blocked_but_same_slot_price_change_is_usable(self):
        controller, feed, probes = await self.controller()
        feed.response = feed.prices(101, slot=100)
        await controller._tick_all()
        self.assertEqual(controller._latest_prices[ASSET], 101)
        buffers = [probe._marks.get(ASSET) for probe in probes]
        feed.response = feed.prices(80, slot=99)
        with self.assertRaises(MarketFeedError):
            await controller._tick_all()
        self.assertEqual(controller._latest_prices, {})
        self.assertEqual([probe._marks.get(ASSET) for probe in probes], buffers)

    async def test_paused_status_loses_valuation_when_the_mark_ages_out(self):
        controller, _feed, (probe, _) = await self.controller()
        trade = self.open_position(probe)
        controller.set_lifecycle("paused")
        self.assertTrue(controller.status()["valuation_available"])
        cash, reserve = probe.capital, controller.reserve_capital
        self.clock.advance(31)
        status = controller.status()
        self.assertEqual(status["status"], "paused")
        self.assertFalse(status["valuation_available"])
        self.assertIsNone(status["total_capital"])
        self.assertEqual(probe.open_positions, {ASSET: trade})
        self.assertEqual((probe.capital, controller.reserve_capital), (cash, reserve))

    async def test_risk_event_persistence_delay_blocks_all_later_decisions(self):
        controller, feed, (stopping, other) = await self.controller()
        trade = self.open_position(stopping)
        feed.response = feed.prices(80)
        self.expire_after(controller, EventType.TRADE_CLOSED)
        with patch.object(other, "tick", wraps=other.tick) as decision, \
             patch.object(controller.strategy, "evolve", wraps=controller.strategy.evolve) as evolve:
            with self.assertRaises(MarketFeedError):
                await controller._tick_all()
            decision.assert_not_called()
            evolve.assert_not_called()
        self.assertEqual(stopping.closed_trades, [trade])
        self.assertEqual(other.open_positions, {})
        self.assertEqual([e.data["trade_id"] for e in self.events
                          if e.event_type == EventType.TRADE_CLOSED], [trade.trade_id])

    async def test_price_broadcast_delay_blocks_entry_and_lifespan_liquidation(self):
        controller, _feed, (first, later) = await self.controller()
        trade = self.open_position(later)
        controller.tick_count = 4  # This frame broadcasts before decisions.
        controller.colony_config.max_lifespan_ticks = 5
        self.expire_after(controller, EventType.PRICE_UPDATE)
        with patch.object(first, "tick", wraps=first.tick) as decision:
            with self.assertRaises(MarketFeedError):
                await controller._tick_all()
            decision.assert_not_called()
        self.assertEqual(later.open_positions, {ASSET: trade})
        self.assertIsNone(trade.exit_price)
        self.assertEqual(controller.dead_probes, [])

    async def test_completed_entry_is_retained_but_delay_blocks_next_probe_and_evolution(self):
        controller, feed, (first, later) = await self.controller()
        end = int(self.clock.wall) // 60 * 60
        controller.candle_history.ingest([
            MinuteCandle(asset, end - 60, 100, 100, 100, 100, 1000, "test")
            for asset in (ASSET, OTHER_ASSET)
        ], available_at=self.clock.wall)
        for tick in feed.response.values():
            first.on_quote(tick)
        with patch.object(first, "_has_entry_signal", return_value=(True, {})):
            self.assertEqual(first.tick(), [])
        self.clock.advance(1)
        feed.response = feed.prices(slot=101)
        controller.reproduction_interval = 1
        self.expire_after(controller, EventType.TRADE_OPENED)
        with patch.object(first, "_has_entry_signal", return_value=(True, {})), \
             patch.object(later, "tick", wraps=later.tick) as decision, \
             patch.object(controller.strategy, "evolve", wraps=controller.strategy.evolve) as evolve:
            with self.assertRaises(MarketFeedError):
                await controller._tick_all()
            decision.assert_not_called()
            evolve.assert_not_called()
        self.assertTrue(first.open_positions)
        self.assertEqual(later.open_positions, {})
        opened = [e for e in self.events if e.event_type == EventType.TRADE_OPENED]
        self.assertEqual({e.data["trade_id"] for e in opened},
                         {trade.trade_id for trade in first.open_positions.values()})
        self.assertEqual(len(controller.probes), 2)

    async def test_retirement_persistence_delay_preserves_next_parent_and_prevents_births(self):
        controller, _feed, (first, later) = await self.controller()
        first_trade = self.open_position(first)
        held = self.open_position(later)
        plan = EvolutionResult([self.genome(), self.genome()], list(controller.probes))
        self.expire_after(controller, EventType.TRADE_CLOSED)
        with self.assertRaises(MarketFeedError):
            await controller._apply_replacement(plan)
        self.assertEqual(first.closed_trades, [first_trade])
        self.assertEqual(later.open_positions, {ASSET: held})
        self.assertIsNone(held.exit_price)
        self.assertIn(later.probe_id, controller.probes)
        self.assertFalse(any(e.event_type == EventType.PROBE_BORN for e in self.events))

    async def test_birth_persistence_delay_blocks_next_reserve_debit(self):
        controller, _feed, originals = await self.controller()
        reserve = controller.reserve_capital
        self.expire_after(controller, EventType.PROBE_BORN)
        with self.assertRaises(MarketFeedError):
            await controller._apply_replacement(EvolutionResult([self.genome(), self.genome()], []))
        births = [e for e in self.events if e.event_type == EventType.PROBE_BORN]
        self.assertEqual(len(births), 1)
        self.assertEqual(len(controller.probes), len(originals) + 1)
        self.assertEqual(controller.reserve_capital, reserve - controller.seed_capital)

    async def test_refresh_cannot_reset_source_age_after_wall_clock_rollback(self):
        for changed_slot in (False, True):
            with self.subTest(changed_slot=changed_slot):
                self.clock.wall, self.clock.mono = 1_700_000_000.0, 500.0
                controller, feed, probes = await self.controller()
                original = dict(feed.response)
                # Twenty real seconds pass, but the wall clock only shows five.
                self.clock.mono += 20
                self.clock.wall += 5
                feed.response = {
                    asset: replace(tick, evidence=QuoteEvidence(
                        101 if changed_slot else 100, self.clock.wall, self.clock.mono))
                    for asset, tick in original.items()
                }
                await controller._tick_all()
                self.assertEqual(controller._latest_prices[ASSET], 100)
                previous_buffers = [probe._marks.get(ASSET) for probe in probes]
                # A second refresh offers the same source time with new receipt
                # metadata. Even another higher slot cannot erase its true age.
                self.clock.mono += 11
                self.clock.wall += 3
                feed.response = {
                    asset: replace(tick, price=101, evidence=QuoteEvidence(
                        102 if changed_slot else 100, self.clock.wall, self.clock.mono))
                    for asset, tick in original.items()
                }
                with self.assertRaises(MarketFeedError) as raised:
                    await controller._tick_all()
                self.assertEqual(raised.exception.code, "price_stale")
                self.assertEqual(controller._latest_prices, {})
                self.assertEqual([probe._marks.get(ASSET) for probe in probes], previous_buffers)
                self.assertFalse(any(e.event_type == EventType.TRADE_OPENED for e in self.events))

    async def test_new_source_replaces_expired_anchor_without_inheriting_old_age(self):
        controller, feed, (probe, _) = await self.controller()
        held = self.open_position(probe)
        self.clock.advance(35)
        self.assertFalse(controller.status()["valuation_available"])
        # New block time advances by the full elapsed time; the old quote is
        # expired, but it must not permanently prevent recovery with fresh data.
        feed.response = feed.prices(101, slot=101)
        await controller._tick_all()
        self.assertTrue(controller.status()["valuation_available"])
        self.assertEqual(controller._latest_prices[ASSET], 101)
        self.assertEqual(probe.open_positions, {ASSET: held})
        self.assertIsNone(held.exit_price)

    async def test_same_slot_cannot_change_source_timestamp_to_claim_freshness(self):
        controller, feed, probes = await self.controller()
        previous_buffers = [probe._marks.get(ASSET) for probe in probes]
        self.clock.advance(1)
        feed.response = feed.prices(101, slot=100)
        with self.assertRaises(MarketFeedError) as raised:
            await controller._tick_all()
        self.assertEqual(raised.exception.code, "source_time_invalid")
        self.assertEqual(controller._latest_prices, {})
        self.assertEqual([probe._marks.get(ASSET) for probe in probes], previous_buffers)
