"""Offline checks for risk-first execution and preservation of completed events."""

from __future__ import annotations

import time
import unittest
import json
import math
from unittest.mock import patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.funding import FundingError
    from vonneumann.core.genome import Genome
    from vonneumann.core.market_validation import MarketValueError
    from vonneumann.core.probe import ProbeStepError
    from vonneumann.core.strategies.base import EvolutionResult, EvolutionStrategy
    from vonneumann.core.types import EventType, ProbeState, TradeRecord
    from vonneumann.db.repository import PersistenceError
    from vonneumann.market.feed import MarketTick
    from vonneumann.market.candles import MinuteCandle


ASSET = "SOL/USDC"
OTHER_ASSET = "JUP/USDC"


class FixedStrategy(EvolutionStrategy):
    name = "market_test_strategy"
    label = "Offline market strategy"

    def initialize(self, probes, colony_config):
        pass

    def evolve(self, probes, dead_probes, colony_config):
        return EvolutionResult([], [])


class MutableFeed:
    def __init__(self):
        self.response = self.prices()

    @staticmethod
    def prices(price=100.0):
        return {asset: MarketTick(asset, price, 1_000.0, time.time())
                for asset in (ASSET, OTHER_ASSET)}

    async def get_candles(self, assets, *, warmup=False):
        return []  # This quote/accounting fixture deliberately has no signal history.

    async def get_ticks(self, assets):
        return self.response


class MarketFailureIsolationTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    async def controller(self):
        self.events = []
        feed = MutableFeed()

        async def persist(event):
            self.events.append(event)

        def genome(**kwargs):
            return Genome(
                assets=[ASSET, OTHER_ASSET], num_assets=2.0,
                position_size_pct=0.5, max_open_positions=2.0,
                stop_loss_pct=0.1, take_profit_pct=0.2,
                timeframe_minutes=1.0, rsi_period=5.0,
                benchmark_target_pct=100.0, reproduce_target_dollars=1_000.0,
                death_drawdown_pct=0.99,
            )

        controller = GenesisController(
            feed, FixedStrategy(), A1, USER_A, gen0_count=2, max_probes=6,
            max_capital=400.0, seed_capital=100.0, diversity_threshold=0.0,
            colony_config=ColonyConfig(available_assets=[ASSET, OTHER_ASSET]),
            on_event=persist,
        )
        with patch("vonneumann.core.genesis.random_genome", side_effect=genome):
            await controller.prepare()
        for probe in controller.live_probes:
            for asset in probe.genome.assets:
                probe.on_price_update(asset, 100.0, 1_000.0)
        self.events.clear()
        return controller, feed, list(controller.live_probes)

    def open_position(self, probe, asset=ASSET):
        if probe.state == ProbeState.OBSERVING:
            probe._transition(ProbeState.TRADING)
        self.assertIsNotNone(probe._open_position(asset, 100.0, {}))
        return probe.open_positions[asset]

    def closed_events(self):
        return [event for event in self.events if event.event_type == EventType.TRADE_CLOSED]

    async def test_healthy_sibling_stop_runs_before_another_probes_signal_failure(self):
        controller, feed, (bad, healthy) = await self.controller()
        trade = self.open_position(healthy)
        feed.response = feed.prices(80.0)
        end = int(time.time()) // 60 * 60
        controller.candle_history.ingest([
            MinuteCandle(asset, end - 60, 100, 100, 100, 100, 1000, "test")
            for asset in (ASSET, OTHER_ASSET)
        ], available_at=time.time())
        failure = RuntimeError("simulated signal calculation failure")
        with patch.object(bad, "_has_entry_signal", side_effect=failure), \
             patch.object(healthy, "tick", wraps=healthy.tick) as healthy_decisions:
            with self.assertRaises(RuntimeError) as raised:
                await controller._tick_all()
            self.assertIs(raised.exception, failure)
            healthy_decisions.assert_not_called()
        self.assertEqual(healthy.open_positions, {})
        self.assertEqual(healthy.closed_trades, [trade])
        self.assertEqual(healthy.capital, 90.0)
        self.assertEqual(bad.capital, 100.0)
        self.assertEqual(len(controller.probes), 2)
        self.assertEqual(controller.dead_probes, [])
        self.assertEqual([(event.probe_id, event.data["trade_id"])
                          for event in self.closed_events()], [(healthy.probe_id, trade.trade_id)])

    async def test_later_asset_risk_error_preserves_earlier_close_and_sibling_stop(self):
        controller, feed, (bad, healthy) = await self.controller()
        earlier = self.open_position(bad)
        malformed = self.open_position(bad, OTHER_ASSET)
        malformed.entry_price = 0.0
        sibling = self.open_position(healthy)
        feed.response = feed.prices(80.0)
        with patch.object(bad, "tick", wraps=bad.tick) as bad_decisions, \
             patch.object(healthy, "tick", wraps=healthy.tick) as healthy_decisions:
            with self.assertRaises(MarketValueError):
                await controller._tick_all()
            bad_decisions.assert_not_called()
            healthy_decisions.assert_not_called()
        self.assertEqual(bad.closed_trades, [earlier])
        self.assertEqual(bad.open_positions, {OTHER_ASSET: malformed})
        self.assertEqual(bad.capital, 65.0)
        self.assertEqual(healthy.closed_trades, [sibling])
        self.assertEqual(healthy.capital, 90.0)
        self.assertEqual({event.data["trade_id"] for event in self.closed_events()},
                         {earlier.trade_id, sibling.trade_id})

    async def test_probe_step_error_carries_successful_close_before_later_asset_failure(self):
        _controller, _feed, (probe, _) = await self.controller()
        earlier = self.open_position(probe)
        malformed = self.open_position(probe, OTHER_ASSET)
        malformed.entry_price = 0.0
        probe.on_price_update(ASSET, 80.0, 1_000.0)
        probe.on_price_update(OTHER_ASSET, 80.0, 1_000.0)
        with self.assertRaises(ProbeStepError) as raised:
            probe.risk_tick(assets={ASSET, OTHER_ASSET})
        self.assertIsInstance(raised.exception.cause, MarketValueError)
        self.assertIsInstance(raised.exception.events, tuple)
        self.assertEqual([event.data["trade_id"] for event in raised.exception.events],
                         [earlier.trade_id])
        self.assertEqual(probe.closed_trades, [earlier])
        self.assertEqual(probe.open_positions, {OTHER_ASSET: malformed})

    async def test_missing_quote_never_executes_from_a_cached_old_stop_price(self):
        controller, feed, (missing, healthy) = await self.controller()
        unpriced_trade = self.open_position(missing, OTHER_ASSET)
        priced_trade = self.open_position(healthy)
        missing.on_price_update(OTHER_ASSET, 80.0, 1_000.0)
        controller._latest_prices[OTHER_ASSET] = 80.0
        old_buffer = missing._marks.get(OTHER_ASSET)
        feed.response = {ASSET: MarketTick(ASSET, 80.0, 1_000.0, time.time())}
        with patch.object(missing, "tick", wraps=missing.tick) as decisions:
            with self.assertRaises(MarketValueError):
                await controller._tick_all()
            decisions.assert_not_called()
        self.assertEqual(missing.open_positions, {OTHER_ASSET: unpriced_trade})
        self.assertEqual(missing.closed_trades, [])
        self.assertEqual(missing.capital, 50.0)
        self.assertEqual(missing._marks.get(OTHER_ASSET), old_buffer)
        self.assertEqual(healthy.closed_trades, [priced_trade])
        self.assertEqual([event.data["trade_id"] for event in self.closed_events()],
                         [priced_trade.trade_id])

    async def test_bad_market_ticks_cannot_poison_buffers_or_controller_cache(self):
        bad_ticks = (
            None,
            MarketTick(OTHER_ASSET, 80.0, 1_000.0, time.time()),
            MarketTick(ASSET, 0.0, 1_000.0, time.time()),
            MarketTick(ASSET, float("nan"), 1_000.0, time.time()),
            MarketTick(ASSET, float("inf"), 1_000.0, time.time()),
            MarketTick(ASSET, False, 1_000.0, time.time()),
            MarketTick(ASSET, 80.0, -1.0, time.time()),
            MarketTick(ASSET, 80.0, float("nan"), time.time()),
            MarketTick(ASSET, 80.0, True, time.time()),
            MarketTick(ASSET, 80.0, 1_000.0, None),
            MarketTick(ASSET, 80.0, 1_000.0, -1.0),
            MarketTick(ASSET, 80.0, 1_000.0, float("nan")),
            MarketTick(ASSET, 80.0, 1_000.0, float("inf")),
            MarketTick(ASSET, 80.0, 1_000.0, False),
        )
        for bad_tick in bad_ticks:
            with self.subTest(bad_tick=bad_tick):
                controller, feed, probes = await self.controller()
                feed.response = feed.prices(80.0)
                feed.response[ASSET] = bad_tick
                buffers = [probe._marks.get(ASSET) for probe in probes]
                histories = [controller.candle_history.latest(ASSET, 1) for probe in probes]
                with self.assertRaises(MarketValueError):
                    await controller._tick_all()
                self.assertEqual([probe._marks.get(ASSET) for probe in probes], buffers)
                self.assertEqual([controller.candle_history.latest(ASSET, 1) for probe in probes], histories)
                self.assertNotIn(ASSET, controller._latest_prices)
                self.assertEqual(controller._latest_prices[OTHER_ASSET], 80.0)
                self.assertFalse(any(event.event_type == EventType.TRADE_OPENED
                                     for event in self.events))

    async def test_feed_exception_clears_cached_marks_without_executing_stale_stops(self):
        controller, feed, (first, second) = await self.controller()
        first_trade = self.open_position(first)
        second_trade = self.open_position(second)
        for probe in (first, second):
            probe.on_price_update(ASSET, 80.0, 1_000.0)
        controller._latest_prices[ASSET] = 80.0
        failure = RuntimeError("simulated feed failure")
        with patch.object(feed, "get_ticks", side_effect=failure), \
             patch.object(first, "risk_tick", wraps=first.risk_tick) as first_risk, \
             patch.object(second, "risk_tick", wraps=second.risk_tick) as second_risk:
            with self.assertRaises(RuntimeError) as raised:
                await controller._tick_all()
            self.assertIs(raised.exception, failure)
            first_risk.assert_not_called()
            second_risk.assert_not_called()
        self.assertEqual(controller._latest_prices, {})
        self.assertEqual(first.open_positions, {ASSET: first_trade})
        self.assertEqual(second.open_positions, {ASSET: second_trade})
        self.assertEqual(first.capital, 50.0)
        self.assertEqual(second.capital, 50.0)
        self.assertEqual(first.closed_trades, [])
        self.assertEqual(second.closed_trades, [])
        self.assertEqual(self.closed_events(), [])

    async def test_risk_event_persistence_failure_propagates_without_reclassification(self):
        controller, feed, (first, second) = await self.controller()
        first_trade = self.open_position(first)
        second_trade = self.open_position(second)
        feed.response = feed.prices(80.0)
        failure = PersistenceError("insert_trade")
        attempted = []

        async def persist(event):
            attempted.append(event)
            if event.event_type == EventType.TRADE_CLOSED:
                raise failure

        controller._on_event = persist
        with patch.object(first, "tick", wraps=first.tick) as first_decisions, \
             patch.object(second, "tick", wraps=second.tick) as second_decisions:
            with self.assertRaises(PersistenceError) as raised:
                await controller._tick_all()
            self.assertIs(raised.exception, failure)
            first_decisions.assert_not_called()
            second_decisions.assert_not_called()
        self.assertEqual(first.closed_trades, [first_trade])
        self.assertEqual(second.closed_trades, [second_trade])
        self.assertEqual(first.capital, 90.0)
        self.assertEqual(second.capital, 90.0)
        self.assertEqual(len([e for e in attempted if e.event_type == EventType.TRADE_CLOSED]), 1)

    async def test_completed_decision_event_is_persisted_before_later_asset_failure(self):
        controller, feed, (bad, healthy) = await self.controller()
        feed.response = feed.prices(100.0)
        failure = MarketValueError()

        end = int(time.time()) // 60 * 60
        controller.candle_history.ingest([
            MinuteCandle(asset, end - 60, 100, 100, 100, 100, 1000, "test")
            for asset in (ASSET, OTHER_ASSET)
        ], available_at=time.time())
        for tick in feed.response.values():
            bad.on_quote(tick)
        with patch.object(bad, "_has_entry_signal", return_value=(True, {})):
            self.assertEqual(bad.tick(), [])  # Both signals queue without filling.
        original_open = bad._open_position
        def open_or_fail(asset, price, signals):
            if asset == OTHER_ASSET:
                raise failure
            return original_open(asset, price, signals)
        stamp = time.time() + 0.1  # A later modeled quote, without sleeping.
        feed.response = {asset: MarketTick(asset, 100, 1000, stamp)
                         for asset in (ASSET, OTHER_ASSET)}
        with patch.object(bad, "_open_position", side_effect=open_or_fail), \
             patch.object(healthy, "tick", wraps=healthy.tick) as healthy_decisions:
            with self.assertRaises(MarketValueError) as raised:
                await controller._tick_all()
            self.assertIs(raised.exception, failure)
            healthy_decisions.assert_not_called()
        self.assertEqual(bad.capital, 50.0)
        self.assertEqual(set(bad.open_positions), {ASSET})
        opened = [event for event in self.events if event.event_type == EventType.TRADE_OPENED]
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].data["trade_id"], bad.open_positions[ASSET].trade_id)
        self.assertEqual(healthy.capital, 100.0)
        self.assertEqual(healthy.open_positions, {})

    async def test_simulation_timestamp_zero_is_valid_and_does_not_imply_stale_feed(self):
        controller, feed, probes = await self.controller()
        feed.response = {asset: MarketTick(asset, 100.0, 0.0, 0.0)
                         for asset in (ASSET, OTHER_ASSET)}
        await controller._tick_all()
        self.assertEqual(controller.tick_count, 1)
        self.assertTrue(all(probe._marks[ASSET] == 100.0 for probe in probes))
        self.assertIsNone(controller.candle_history.latest(ASSET, 1))

    async def test_failure_status_remains_json_safe_when_portfolio_valuation_is_invalid(self):
        for corruption in ("entry", "cash", "mark", "reserve"):
            with self.subTest(corruption=corruption):
                controller, _feed, (probe, _) = await self.controller()
                trade = self.open_position(probe)
                if corruption == "entry":
                    trade.entry_price = 0.0
                elif corruption == "cash":
                    probe.capital = float("nan")
                elif corruption == "mark":
                    controller._latest_prices[ASSET] = float("nan")
                else:
                    controller.reserve_capital = float("nan")
                controller.set_lifecycle("failed")
                controller.failure_code = "invalid_market_value"
                status = controller.status()
                encoded = json.dumps(status, allow_nan=False)
                self.assertIsInstance(encoded, str)
                self.assertEqual(status["status"], "failed")
                self.assertFalse(status["valuation_available"])
                self.assertIsNone(status["total_capital"])
                self.assertTrue(status["requires_reconciliation"])
                self.assertIn(probe.probe_id, controller.probes)

    async def test_failure_status_does_not_emit_nan_diversity_from_invalid_gene(self):
        controller, _feed, (probe, _) = await self.controller()
        probe.genome.rsi_period = float("nan")
        controller.set_lifecycle("failed")
        status = controller.status()
        json.dumps(status, allow_nan=False)
        self.assertIsNone(status["diversity"])
        self.assertEqual(len(controller.probes), 2)

    async def test_replacement_rejects_invalid_trade_history_before_any_liquidation(self):
        controller, _feed, (first, bad) = await self.controller()
        earlier = self.open_position(first)
        held = self.open_position(bad)
        bad.closed_trades.append(TradeRecord(
            trade_id="malformed-historical-trade", probe_id=bad.probe_id,
            pair=ASSET, side="BUY", entry_price=100.0, amount=1.0, exit_price=None,
        ))
        plan = EvolutionResult(
            offspring=[Genome.from_dict(probe.genome.to_dict()) for probe in controller.live_probes],
            retire_ids=list(controller.probes),
        )
        before_cash, before_reserve = bad.capital, controller.reserve_capital
        before_ids = set(controller.probes)
        with patch.object(controller.strategy, "evolve", return_value=plan):
            with self.assertRaises(FundingError) as raised:
                await controller._evaluate_reproduction()
        self.assertEqual(raised.exception.code, "funding_invalid_plan")
        self.assertEqual(controller.reserve_capital, before_reserve)
        self.assertEqual(bad.capital, before_cash)
        self.assertEqual(set(controller.probes), before_ids)
        self.assertEqual(controller.dead_probes, [])
        self.assertEqual(first.capital, 50.0)
        self.assertEqual(first.open_positions, {ASSET: earlier})
        self.assertIsNone(earlier.exit_price)
        self.assertEqual(bad.open_positions, {ASSET: held})
        self.assertIsNone(held.exit_price)
        self.assertEqual(len(bad.closed_trades), 1)
        self.assertEqual(self.events, [])

    async def test_historical_trade_return_cannot_overflow_portfolio_fitness(self):
        controller, _feed, (first, later) = await self.controller()
        first_position = self.open_position(first)
        later_position = self.open_position(later)
        later.closed_trades.append(TradeRecord(
            trade_id="large-finite-historical-return", probe_id=later.probe_id,
            pair=ASSET, side="BUY", entry_price=1e-200, exit_price=1.0,
            amount=1e-200, pnl=1.0, pnl_pct=1e200,
        ))
        # Closed-trade percentages are no longer portfolio-return samples.
        # A large historical percentage cannot block a valid liquidation.
        self.assertTrue(math.isfinite(later.closed_trades[0].return_pct()))
        self.assertTrue(math.isfinite(later.fitness))
        plan = EvolutionResult(
            offspring=[Genome.from_dict(probe.genome.to_dict()) for probe in controller.live_probes],
            retire_ids=list(controller.probes),
        )
        with patch.object(controller.strategy, "evolve", return_value=plan):
            await controller._evaluate_reproduction()
        self.assertIn(first, controller.dead_probes)
        self.assertIn(later, controller.dead_probes)
        for probe, position in ((first, first_position), (later, later_position)):
            self.assertEqual(probe.open_positions, {})
            self.assertEqual(position.exit_price, 100.0)
            self.assertIsNone(probe.sharpe)
            self.assertEqual(probe.fitness, 0.0)



if __name__ == "__main__":
    unittest.main()
