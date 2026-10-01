"""Immutable fixture playback through the actual indicator and decision engine."""

from __future__ import annotations

import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_engine_clock import FixedStrategy, genome
from tests.test_repository_security import RecordingDB
from tests.test_search_replay import ALGORITHMS, config, snapshot

with deny_network():
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.types import EventType
    from vonneumann.core.strategies import get_strategy
    from vonneumann.db.repository import VonNeumannRepository
    from vonneumann.market.dataset import DatasetError, MAINNET_GENESIS_HASH, TOKEN_MINTS, write_dataset
    from vonneumann.market.dataset_cli import generate_synthetic_dataset
    from vonneumann.market.feed import MarketFeedError
    from vonneumann.market.replay_feed import ReplayFeed
    from vonneumann.market.sim_feed import SimulationFeed


SOL, JUP = "SOL/USDC", "JUP/USDC"


class DatasetReplayTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        state = random.getstate()
        self.addCleanup(random.setstate, state)

    async def fixture(self, name="fixture", frames=4, seed="32", assets=(SOL, JUP)):
        path = self.root / name
        await generate_synthetic_dataset(path, frames=frames, assets=list(assets), seed=seed)
        return path

    def records(self, path):
        manifest = json.loads((path / "manifest.json").read_text())
        frames = [json.loads(line) for line in (path / "frames.jsonl").read_text().splitlines()]
        return manifest["metadata"], frames

    async def test_requests_advance_whole_frames_with_isolated_cursors_and_no_rng_dependency(self):
        path = await self.fixture()
        one, other = ReplayFeed(path), ReplayFeed(path)
        origin = one.current_timestamp
        self.assertEqual(await one.get_ticks([]), {})
        self.assertEqual(await one.get_candles([SOL, JUP], warmup=True), [])
        self.assertEqual(one.current_timestamp, origin)
        for bad in ([SOL, "unsupported"], "SOL/USDC", [True], [None]):
            with self.assertRaises(MarketFeedError):
                await one.get_ticks(bad)
            with self.assertRaises(MarketFeedError):
                await one.get_candles(bad)
            self.assertEqual(one.current_timestamp, origin)
        first = await one.get_ticks([JUP, SOL, JUP])
        self.assertEqual(list(first), [JUP, SOL])
        self.assertEqual(first, await other.get_ticks([SOL, JUP]))
        first[SOL].price = 1
        random.seed(929)
        for _ in range(50):
            random.gauss(0, 1)
        second = await one.get_tick(JUP)
        self.assertEqual(second, (await other.get_ticks([SOL, JUP]))[JUP])
        self.assertEqual(one.current_timestamp, origin + 120)
        self.assertNotEqual((await ReplayFeed(path).get_tick(SOL)).price, 1)
        # Metadata is copied and contains no local file location.
        spec = one.dataset_spec
        spec["dataset_id"] = "changed"
        self.assertNotEqual(one.dataset_spec["dataset_id"], "changed")
        self.assertNotIn(str(self.root), json.dumps(one.dataset_spec))

    async def test_candles_are_delivered_once_per_asset_after_frame_and_survive_skipped_reads(self):
        path = await self.fixture()
        feed = ReplayFeed(path)
        for _ in range(3):
            await feed.get_tick(SOL)
        stamp = feed.current_timestamp
        candles = await feed.get_candles([JUP])
        self.assertEqual(len(candles), 3)
        self.assertTrue(all(bar.asset == JUP and bar.end <= stamp for bar in candles))
        self.assertEqual(await feed.get_candles([JUP]), [])
        self.assertEqual(len(await feed.get_candles([SOL])), 3)
        self.assertEqual(feed.current_timestamp, stamp)
        await feed.get_tick(SOL)
        self.assertEqual(len(await feed.get_candles([SOL, JUP])), 2)

    async def test_delayed_bar_cannot_be_read_before_its_delivery_frame(self):
        source = await self.fixture(frames=3, assets=(SOL,))
        metadata, frames = self.records(source)
        delayed = frames[0]["candles"].pop()
        delayed["available_at"] = frames[1]["observed_at"]
        frames[1]["candles"].insert(0, delayed)
        path = self.root / "delayed"
        write_dataset(path, metadata, frames)
        feed = ReplayFeed(path)
        await feed.get_tick(SOL)
        self.assertEqual(await feed.get_candles([SOL], warmup=True), [])
        await feed.get_tick(SOL)
        bars = await feed.get_candles([SOL])
        self.assertEqual([bar.start for bar in bars], [delayed["start"], delayed["start"] + 60])

    async def test_eof_never_repeats_last_quote_or_advances_clock(self):
        path = await self.fixture(frames=1)
        feed = ReplayFeed(path)
        await feed.get_ticks([SOL, JUP])
        await feed.get_candles([SOL, JUP])
        stamp = feed.current_timestamp
        for _ in range(2):
            with self.assertRaises(MarketFeedError) as error:
                await feed.get_tick(SOL)
            self.assertEqual(error.exception.code, "dataset_exhausted")
            self.assertEqual(error.exception.valid_ticks, {})
            self.assertEqual(feed.current_timestamp, stamp)
            self.assertEqual(await feed.get_candles([SOL, JUP]), [])

    async def test_duplicate_candles_are_not_redelivered_as_new_history(self):
        source = await self.fixture(frames=3, assets=(SOL,))
        metadata, frames = self.records(source)
        frames[2]["candles"].insert(0, frames[0]["candles"][0])
        path = self.root / "duplicate"
        write_dataset(path, metadata, frames)
        feed = ReplayFeed(path)
        for _ in range(3):
            await feed.get_tick(SOL)
            self.assertEqual(len(await feed.get_candles([SOL])), 1)

    async def test_provider_playback_paper_mode_and_unimplemented_windows_are_refused(self):
        path = await self.fixture()
        feed = ReplayFeed(path)
        strategy = MagicMock()
        with self.assertRaisesRegex(ValueError, "simulation mode only"):
            GenesisController(feed, strategy, A1, USER_A, mode="paper")
        strategy.configure_search.assert_not_called()
        metadata, frames = self.records(path)
        metadata["evaluation_start_at"] += 60
        destination = self.root / "window"
        write_dataset(destination, metadata, frames)
        with self.assertRaises(DatasetError) as error:
            ReplayFeed(destination)
        self.assertEqual(error.exception.code, "replay_window_unsupported")
        # This is generated test data with a provider-shaped schema, not an
        # acquisition or rights assertion about any actual provider response.
        metadata.update({
            "source_kind": "provider_observations", "network": "solana-mainnet",
            "genesis_hash": MAINNET_GENESIS_HASH,
            "assets": [{"asset": item["asset"], "mint": TOKEN_MINTS[item["asset"]]}
                       for item in metadata["assets"]],
            "quote_provider": "jupiter-price-v3", "candle_provider": "birdeye-ohlcv-v3",
            "volume_unit": "base_token", "quote_volume_semantics": "unavailable_zero_placeholder",
            "source_time_semantics": "estimated_block_time", "availability_semantics": "recorded_receipt",
            "rights_basis": "provider_archive_permission_reviewed", "simulation_spec": None,
        })
        for frame in frames:
            for quote in frame["quotes"]:
                quote.update(source_slot=frame["seq"] + 10, volume=0, volume_unit="base_token")
            for candle in frame["candles"]:
                candle.update(source="birdeye-ohlcv-v3", volume_unit="base_token")
        provider_path = self.root / "provider-shaped-fixture"
        write_dataset(provider_path, metadata, frames)
        with self.assertRaises(DatasetError) as error:
            ReplayFeed(provider_path)
        self.assertEqual(error.exception.code, "provider_replay_unsupported")

    async def test_real_decisions_trades_and_indicators_match_original_and_changed_pacing(self):
        path = await self.fixture(frames=501, assets=(SOL,))

        async def run(feed, interval, noise):
            events = []
            async def event(value):
                if value.event_type in (EventType.TRADE_OPENED, EventType.TRADE_CLOSED):
                    events.append((value.event_type.value, value.timestamp.isoformat(),
                                   {k: v for k, v in value.data.items() if k != "trade_id"}))
            controller = GenesisController(
                feed, FixedStrategy(), A1, USER_A, gen0_count=1, max_probes=2,
                max_capital=200, seed_capital=100, diversity_threshold=0,
                tick_interval_ms=interval,
                colony_config=ColonyConfig(available_assets=[SOL]), on_event=event,
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
            return events, controller.candle_history.latest(SOL, 5), controller

        original = await run(SimulationFeed(seed=32), 100, 0)
        replay = await run(ReplayFeed(path), 5000, 30)
        self.assertTrue(any(e[0] == EventType.TRADE_OPENED.value for e in original[0]))
        self.assertTrue(any(e[0] == EventType.TRADE_CLOSED.value for e in original[0]))
        self.assertEqual(original[:2], replay[:2])
        self.assertEqual(original[2].status()["total_capital"], replay[2].status()["total_capital"])
        identity = replay[2].status()["search_spec"]["dataset_spec"]
        self.assertEqual(identity["dataset_id"], ReplayFeed(path).dataset_spec["dataset_id"])
        self.assertEqual(identity["quote_currency"], "USD")
        db = RecordingDB()
        with patch("vonneumann.db.repository.get_supabase", return_value=db):
            repository = VonNeumannRepository(USER_A, A1)
        repository.update_colony_status(A1, "stopped", {
            "search_spec": replay[2].status()["search_spec"],
        })
        saved = json.loads(json.dumps(db.calls[-1]["fields"], allow_nan=False))
        self.assertEqual(saved["config"]["runtime"]["search_spec"]["dataset_spec"], identity)
        # Exhaustion clears current marks; the final observation cannot be used
        # again as if a new source refresh had succeeded.
        with self.assertRaises(MarketFeedError) as error:
            await replay[2]._tick_all()
        self.assertEqual(error.exception.code, "dataset_exhausted")
        self.assertEqual(replay[2]._latest_prices, {})

    async def test_all_four_optimizers_preserve_common_window_results_and_offspring(self):
        path = await self.fixture(frames=501, seed="729")
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                controllers = []
                for feed, pacing in ((SimulationFeed(seed=729), 100), (ReplayFeed(path), 5000)):
                    controller = GenesisController(
                        feed, get_strategy(algorithm), A1, USER_A,
                        gen0_count=8, max_probes=8, max_capital=10000, seed_capital=100,
                        tick_interval_ms=pacing, colony_config=config(),
                        circuit_breaker_drop_pct=1., search_seed="19",
                    )
                    await controller.prepare()
                    controller.set_lifecycle("running")
                    controllers.append(controller)
                identities = ({}, {})
                for controller, ids in zip(controllers, identities):
                    snapshot(controller, ids)
                generations = 0
                for _ in range(500):
                    iteration = controllers[0]._evaluation_iteration
                    for controller in controllers:
                        await controller._tick_all()
                    self.assertEqual(controllers[0]._latest_prices, controllers[1]._latest_prices)
                    if controllers[0]._evaluation_iteration != iteration:
                        actual = []
                        for controller, ids in zip(controllers, identities):
                            data = snapshot(controller, ids)
                            # Input provenance differs by design; compare the
                            # actual genomes, ancestry, account and clock data.
                            data["search_spec"].pop("dataset_spec")
                            actual.append(data)
                        self.assertEqual(actual[0], actual[1])
                        generations += 1
                        if generations == 4:
                            break
                self.assertEqual(generations, 4)
