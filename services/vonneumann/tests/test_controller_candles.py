"""Candle history through the real controller, without network or persistence."""

import unittest
import random
from unittest.mock import AsyncMock, patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_engine_clock import FixedStrategy, genome

with deny_network():
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.types import EventType, ProbeState
    from vonneumann.market.feed import MarketFeedError
    from vonneumann.market.sim_feed import SimulationFeed


ASSET = "SOL/USDC"
SECOND = "JUP/USDC"


class ControllerCandleTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    async def controller(self):
        self.events = []

        async def event(value):
            self.events.append(value)

        feed = SimulationFeed(seed=42, drift=0, volatility=0, volume_noise=0)
        controller = GenesisController(
            feed, FixedStrategy(), A1, USER_A, gen0_count=1, max_probes=4,
            max_capital=400, seed_capital=100, diversity_threshold=0,
            colony_config=ColonyConfig(available_assets=[ASSET, SECOND]), on_event=event,
        )
        with patch("vonneumann.core.genesis.random_genome", side_effect=lambda **_: genome()):
            await controller.prepare()
        self.events.clear()
        return controller, feed, controller.live_probes[0]

    async def test_initial_frame_and_unselected_assets_enter_shared_history_once(self):
        controller, feed, _ = await self.controller()
        stamp = feed.current_timestamp
        for asset in (ASSET, SECOND):
            self.assertEqual(controller.candle_history.latest(asset, 1).completed_count, 1)
        before = controller.candle_history.latest(SECOND, 1)
        await controller._refresh_candles()
        self.assertEqual(controller.candle_history.latest(SECOND, 1), before)
        self.assertEqual(feed.current_timestamp, stamp)
        await controller._tick_all()
        self.assertEqual(controller.candle_history.latest(SECOND, 1).completed_count, 2)
        self.assertEqual(feed.current_timestamp, stamp + 60)

    async def test_stop_is_persisted_before_history_outage_interrupts_decisions(self):
        controller, feed, probe = await self.controller()
        price = feed.get_current_price(ASSET)
        probe._open_position(ASSET, price, {})
        probe._transition(ProbeState.TRADING)
        trade = probe.open_positions[ASSET]
        feed._assets[ASSET].current_price = price * 0.8
        with patch.object(feed, "get_candles", new=AsyncMock(side_effect=MarketFeedError("candles_unavailable"))), \
             patch.object(probe, "tick", wraps=probe.tick) as decision:
            with self.assertRaises(MarketFeedError):
                await controller._tick_all()
            decision.assert_not_called()
        self.assertEqual(probe.closed_trades, [trade])
        self.assertEqual(trade.exit_reason, "STOP_LOSS")
        self.assertTrue(any(e.event_type == EventType.TRADE_CLOSED for e in self.events))

    async def test_child_uses_own_timeframe_and_same_run_history_without_parent_copy(self):
        controller, _, parent = await self.controller()
        for _ in range(69):
            await controller._tick_all()
        child = await controller._spawn_probe(genome(assets=[SECOND], timeframe_minutes=7.0), 100)
        self.assertIsNotNone(child)
        self.assertEqual(controller.candle_history.latest(SECOND, 1).completed_count, 70)
        self.assertGreaterEqual(controller.candle_history.latest(SECOND, 7).completed_count, 9)
        with patch.object(child, "_has_entry_signal", return_value=(True, {})) as signal:
            child.tick()
            signal.assert_not_called()  # A newborn never replays the existing close.
        self.assertEqual(child.open_positions, {})
        self.assertFalse(hasattr(parent, "_price_buffer"))

    async def test_simulation_rejects_nonminute_candle_configuration(self):
        for feed in (SimulationFeed(step_seconds=30), SimulationFeed(start_timestamp=1704067201)):
            await feed.get_ticks([ASSET])
            with self.assertRaises(MarketFeedError) as error:
                await feed.get_candles([ASSET])
            self.assertEqual(error.exception.code, "candle_clock_configuration")

    async def test_candle_high_low_and_volume_describe_exactly_one_synthetic_frame(self):
        feed = SimulationFeed(drift=0.01, volatility=0, volume_noise=0)
        before = feed.get_current_price(ASSET)
        tick = await feed.get_tick(ASSET)
        first = (await feed.get_candles([ASSET]))[0]
        self.assertEqual((first.open, first.close), (before, tick.price))
        self.assertEqual((first.low, first.high), (before, tick.price))
        self.assertEqual(first.volume, tick.volume)
        self.assertEqual(first.end, tick.timestamp)
        self.assertEqual(await feed.get_candles([ASSET]), [first])
        self.assertEqual(first.volume_unit, "synthetic_base_token")

    async def test_real_indicators_decisions_and_fills_replay_identically(self):
        original_rng = random.getstate()
        self.addCleanup(random.setstate, original_rng)

        async def replay(interval, noise):
            events = []
            async def event(value):
                if value.event_type in (EventType.TRADE_OPENED, EventType.TRADE_CLOSED):
                    events.append((value.event_type.value, value.timestamp.isoformat(),
                                   {k: v for k, v in value.data.items() if k != "trade_id"}))
            feed = SimulationFeed(seed=32, drift=0, volatility=0.02, volume_noise=0.5)
            controller = GenesisController(
                feed, FixedStrategy(), A1, USER_A, gen0_count=1, max_probes=2,
                max_capital=200, seed_capital=100, diversity_threshold=0,
                tick_interval_ms=interval,
                colony_config=ColonyConfig(available_assets=[ASSET]), on_event=event,
            )
            settings = genome(timeframe_minutes=5, rsi_period=5, ema_fast=3,
                              ema_slow=12, rsi_oversold=45, volume_threshold=1.0)
            with patch("vonneumann.core.genesis.random_genome", return_value=settings):
                await controller.prepare()
            controller.set_lifecycle("running")
            actual_tick = controller._tick_all
            async def tick_and_stop():
                for _ in range(noise):
                    random.random()
                await actual_tick()
                if controller.tick_count == 500:
                    controller._running = False
            sleep = AsyncMock()
            with patch.object(controller, "_tick_all", side_effect=tick_and_stop), \
                 patch("vonneumann.core.genesis.asyncio.sleep", new=sleep):
                await controller._tick_loop()
            self.assertEqual(sleep.await_count, 500)
            self.assertTrue(all(call.args == (interval / 1000,) for call in sleep.await_args_list))
            return events, controller.candle_history.latest(ASSET, 5)

        fast, fast_history = await replay(100, 0)
        slow, slow_history = await replay(5000, 75)
        self.assertTrue(any(e[0] == EventType.TRADE_OPENED.value for e in fast))
        self.assertTrue(any(e[0] == EventType.TRADE_CLOSED.value for e in fast))
        self.assertEqual(fast, slow)
        self.assertEqual(fast_history, slow_history)
