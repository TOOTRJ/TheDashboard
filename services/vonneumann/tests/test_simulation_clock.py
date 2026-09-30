"""Offline regression tests for deterministic, atomic synthetic market frames."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import math
import random
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.market_validation import MarketValueError
    from vonneumann.market.sim_feed import BASE_PRICES, BASE_VOLUMES, SimulationFeed


ASSETS = list(BASE_PRICES)
START = 1704067200.0


class SimulationClockTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def snapshot(self, feed):
        return {
            "clock": feed.current_timestamp,
            "frame": feed._frame_number,
            "assets": {asset: asdict(state) for asset, state in feed._assets.items()},
            "rngs": {asset: rng.getstate() for asset, rng in feed._rngs.items()},
        }

    async def test_default_clock_advances_once_per_batch_for_all_assets(self):
        feed = SimulationFeed()
        self.assertEqual(feed.current_timestamp, START)
        ticks = await feed.get_ticks([ASSETS[0], ASSETS[1], ASSETS[0]])
        self.assertEqual(list(ticks), ASSETS[:2])
        self.assertEqual({tick.timestamp for tick in ticks.values()}, {START + 60.0})
        self.assertEqual(feed.current_timestamp, START + 60.0)
        self.assertTrue(all(state.tick_count == 1 for state in feed._assets.values()))
        next_ticks = await feed.get_ticks(ASSETS)
        self.assertEqual({tick.timestamp for tick in next_ticks.values()}, {START + 120.0})

    async def test_seeded_path_ignores_order_duplicates_subsets_and_late_requests(self):
        reference = SimulationFeed(seed=123)
        selective = SimulationFeed(seed=123)
        for frame in range(60):
            expected = await reference.get_ticks(ASSETS)
            requested = ([ASSETS[0], ASSETS[0]] if frame < 30 else
                         list(reversed(ASSETS[frame % len(ASSETS):] + ASSETS[:frame % len(ASSETS)])))
            actual = await selective.get_ticks(requested)
            self.assertEqual(actual, {asset: expected[asset] for asset in requested})
            self.assertEqual(self.snapshot(selective), self.snapshot(reference))

    async def test_different_seeds_produce_different_paths_at_the_same_clock(self):
        first = await SimulationFeed(seed=1).get_ticks(ASSETS)
        second = await SimulationFeed(seed=2).get_ticks(ASSETS)
        self.assertTrue(all(first[asset].price != second[asset].price for asset in ASSETS))
        self.assertEqual({tick.timestamp for tick in first.values()},
                         {tick.timestamp for tick in second.values()})

    async def test_global_rng_optimizer_calls_wall_clock_and_yields_do_not_change_paths(self):
        saved_random_state = random.getstate()
        try:
            reference = SimulationFeed(seed=99)
            delayed = SimulationFeed(seed=99)
            for frame in range(30):
                with patch("time.time", return_value=100.0 + frame):
                    expected = await reference.get_ticks(ASSETS)
                random.seed(frame)
                for _ in range(frame + 1):
                    random.random()
                    random.gauss(0, 1)
                state_before_feed = random.getstate()
                with patch("time.time", return_value=9_000_000_000.0 + frame * 1000):
                    await asyncio.sleep(0)
                    actual = await delayed.get_ticks(ASSETS)
                self.assertEqual(actual, expected)
                self.assertEqual(random.getstate(), state_before_feed)
        finally:
            random.setstate(saved_random_state)

    async def test_private_asset_seed_uses_stable_versioned_digest(self):
        seed = 2**64 - 1
        feed = SimulationFeed(seed=seed)
        ticks = await feed.get_ticks(ASSETS)
        for asset in ASSETS:
            digest = hashlib.sha256(f"vonneumann-sim-v1:{seed}:{asset}".encode()).digest()
            stream = random.Random(int.from_bytes(digest, "big"))
            log_return = math.fsum((0.0001, -0.5 * 0.02**2, 0.02 * stream.gauss(0, 1)))
            expected_price = BASE_PRICES[asset] * math.exp(log_return)
            expected_volume = BASE_VOLUMES[asset] * max(0.1, 1 + stream.gauss(0, 0.5))
            self.assertEqual(ticks[asset].price, expected_price)
            self.assertEqual(ticks[asset].volume, expected_volume)

    async def test_empty_batches_do_not_advance_prices_clock_or_rngs(self):
        feed = SimulationFeed(seed=12)
        for _ in range(3):
            before = self.snapshot(feed)
            self.assertEqual(await feed.get_ticks([]), {})
            self.assertEqual(self.snapshot(feed), before)
        self.assertEqual(await feed.get_ticks(ASSETS), await SimulationFeed(seed=12).get_ticks(ASSETS))

    async def test_invalid_batches_reject_atomically_before_any_asset_draw(self):
        feed = SimulationFeed(seed=12)
        for request in ([ASSETS[0], "unknown"], [ASSETS[0], None], [ASSETS[0], []],
                        [True], None, ASSETS[0]):
            with self.subTest(request=request):
                before = self.snapshot(feed)
                with self.assertRaises(MarketValueError):
                    await feed.get_ticks(request)
                self.assertEqual(self.snapshot(feed), before)
        self.assertEqual(await feed.get_ticks(ASSETS), await SimulationFeed(seed=12).get_ticks(ASSETS))

    async def test_single_asset_api_advances_the_same_complete_market_frame(self):
        single = SimulationFeed(seed=18)
        batch = SimulationFeed(seed=18)
        for frame in range(12):
            asset = ASSETS[frame % len(ASSETS)]
            expected = await batch.get_ticks(ASSETS)
            self.assertEqual(await single.get_tick(asset), expected[asset])
            self.assertEqual(self.snapshot(single), self.snapshot(batch))

    async def test_current_price_read_does_not_advance_and_unknown_read_is_rejected(self):
        feed = SimulationFeed()
        before = self.snapshot(feed)
        self.assertEqual(feed.get_current_price(ASSETS[0]), BASE_PRICES[ASSETS[0]])
        with self.assertRaises(MarketValueError):
            feed.get_current_price("unknown")
        self.assertEqual(self.snapshot(feed), before)

    async def test_simulation_spec_is_json_safe_copied_and_preserves_full_seed(self):
        seed = 2**64 - 1
        feed = SimulationFeed(seed=seed, start_timestamp=0, step_seconds=0.25,
                              drift=0.01, volatility=0.03, volume_noise=0.1)
        expected_spec = {
            "model_version": "gbm-discrete-v1", "seed": str(seed),
            "start_timestamp": 0.0, "step_seconds": 0.25,
            "drift": 0.01, "volatility": 0.03, "volume_noise": 0.1,
            "candle_model": "minute-endpoints-v1", "volume_unit": "synthetic_base_token",
        }
        self.assertEqual(json.loads(json.dumps(feed.simulation_spec, allow_nan=False)), expected_spec)
        changed = feed.simulation_spec
        changed.update(seed="42", step_seconds=1000, volatility=10)
        self.assertEqual(feed.simulation_spec, expected_spec)
        fresh = SimulationFeed(seed=seed, start_timestamp=0, step_seconds=0.25,
                               drift=0.01, volatility=0.03, volume_noise=0.1)
        self.assertEqual(await feed.get_ticks(ASSETS), await fresh.get_ticks(ASSETS))
        self.assertEqual(feed.current_timestamp, 0.25)

    async def test_invalid_seed_and_numeric_parameters_are_rejected(self):
        bad_values = [None, True, "0", math.nan, math.inf, -math.inf, 10**400]
        invalid = {
            "seed": [None, True, -1, 2**64, 1.0, "1"],
            "drift": bad_values,
            "volatility": bad_values + [-0.1, 1e200],
            "volume_noise": bad_values + [-0.1],
            "start_timestamp": bad_values + [-1, 253402300800.0],
            "step_seconds": bad_values + [-1, 0, 5e-324],
        }
        for name, values in invalid.items():
            for value in values:
                with self.subTest(parameter=name, value=value):
                    with self.assertRaises(MarketValueError):
                        SimulationFeed(**{name: value})

    async def test_clock_uses_start_plus_frame_number_without_cumulative_drift(self):
        feed = SimulationFeed(start_timestamp=0, step_seconds=0.1)
        for frame in range(1, 101):
            ticks = await feed.get_ticks([ASSETS[0]])
            self.assertEqual(feed.current_timestamp, frame * 0.1)
            self.assertEqual(ticks[ASSETS[0]].timestamp, frame * 0.1)

    async def test_clock_requires_an_advance_representable_in_utc_event_datetimes(self):
        for step in (1e-50, 1e-7, 0.49e-6):
            with self.subTest(step=step):
                with self.assertRaises(MarketValueError):
                    SimulationFeed(start_timestamp=0, step_seconds=step)
        feed = SimulationFeed(start_timestamp=0, step_seconds=1e-6)
        previous = datetime.fromtimestamp(feed.current_timestamp, timezone.utc)
        for _ in range(10):
            await feed.get_ticks([ASSETS[0]])
            current = datetime.fromtimestamp(feed.current_timestamp, timezone.utc)
            self.assertGreater(current, previous)
            previous = current

    async def test_datetime_limit_failure_does_not_commit_prices_rng_or_clock(self):
        start = datetime(9999, 12, 31, 23, 59, 58, tzinfo=timezone.utc).timestamp()
        feed = SimulationFeed(start_timestamp=start, step_seconds=1)
        await feed.get_ticks(ASSETS)
        before = self.snapshot(feed)
        with self.assertRaises(MarketValueError):
            await feed.get_ticks(ASSETS)
        self.assertEqual(self.snapshot(feed), before)

    async def test_zero_drift_volatility_and_noise_keep_exact_initial_values(self):
        feed = SimulationFeed(drift=0, volatility=0, volume_noise=0)
        for _ in range(10):
            ticks = await feed.get_ticks(ASSETS)
            self.assertEqual({asset: tick.price for asset, tick in ticks.items()}, BASE_PRICES)
            self.assertEqual({asset: tick.volume for asset, tick in ticks.items()}, BASE_VOLUMES)

    async def test_large_negative_return_stays_positive_without_a_clamp(self):
        feed = SimulationFeed(drift=-2, volatility=0, volume_noise=0)
        for frame in range(1, 4):
            ticks = await feed.get_ticks(ASSETS)
            for asset, tick in ticks.items():
                self.assertGreater(tick.price, 0)
                self.assertAlmostEqual(tick.price / BASE_PRICES[asset], math.exp(-2 * frame))

    async def test_geometric_step_includes_variance_correction(self):
        feed = SimulationFeed(drift=0.05, volatility=0.8, volume_noise=0)
        with patch.object(random.Random, "gauss", return_value=0):
            ticks = await feed.get_ticks(ASSETS)
        for asset, tick in ticks.items():
            self.assertEqual(tick.price, BASE_PRICES[asset] * math.exp(0.05 - 0.5 * 0.8**2))

    async def test_extreme_representable_moves_survive_unrepresentable_exp_factor(self):
        for price, drift in ((1e-300, 750.0), (1e300, -750.0)):
            with self.subTest(price=price, drift=drift):
                feed = SimulationFeed(drift=drift, volatility=0, volume_noise=0)
                for state in feed._assets.values():
                    state.current_price = price
                ticks = await feed.get_ticks(ASSETS)
                expected = math.exp(math.log(price) + drift)
                for tick in ticks.values():
                    self.assertTrue(math.isfinite(tick.price))
                    self.assertGreater(tick.price, 0)
                    self.assertAlmostEqual(tick.price / expected, 1.0)

    async def test_subnormal_exp_factor_preserves_normal_final_price_precision(self):
        price = 1e300
        for drift in (-744.0, -745.0):
            with self.subTest(drift=drift):
                feed = SimulationFeed(drift=drift, volatility=0, volume_noise=0)
                for state in feed._assets.values():
                    state.current_price = price
                # Independent high-precision arithmetic avoids the binary-float
                # factor rounding that formerly caused 29% and 75% price errors.
                with localcontext() as context:
                    context.prec = 80
                    expected = float((Decimal.from_float(price).ln()
                                      + Decimal.from_float(drift)).exp())
                ticks = await feed.get_ticks(ASSETS)
                for tick in ticks.values():
                    self.assertTrue(math.isclose(tick.price, expected, rel_tol=1e-12, abs_tol=0),
                                    (tick.price, expected))

    async def test_unrepresentable_price_rejects_complete_frame_without_advancement(self):
        for drift in (1000.0, -1000.0):
            with self.subTest(drift=drift):
                feed = SimulationFeed(drift=drift, volatility=0)
                before = self.snapshot(feed)
                with self.assertRaises(MarketValueError):
                    await feed.get_ticks(ASSETS)
                self.assertEqual(self.snapshot(feed), before)

    async def test_late_unrequested_asset_failure_rolls_back_entire_frame_and_rngs(self):
        feed = SimulationFeed(seed=9)
        reference = SimulationFeed(seed=9)
        await feed.get_ticks(ASSETS)
        await reference.get_ticks(ASSETS)
        last = ASSETS[-1]
        saved_drift = feed._assets[last].drift
        feed._assets[last].drift = 1000.0
        before = self.snapshot(feed)
        with self.assertRaises(MarketValueError):
            await feed.get_ticks([ASSETS[0]])
        self.assertEqual(self.snapshot(feed), before)
        feed._assets[last].drift = saved_drift
        self.assertEqual(await feed.get_ticks(ASSETS), await reference.get_ticks(ASSETS))

    async def test_nonfinite_draw_or_volume_cannot_be_hidden_by_volume_floor(self):
        for draws in ((math.nan, 0), (0, -math.inf), (0, math.inf)):
            with self.subTest(draws=draws):
                feed = SimulationFeed()
                before = self.snapshot(feed)
                with patch.object(random.Random, "gauss", side_effect=draws):
                    with self.assertRaises(MarketValueError):
                        await feed.get_ticks(ASSETS)
                self.assertEqual(self.snapshot(feed), before)

    async def test_late_volume_overflow_keeps_all_assets_clock_and_rngs_unchanged(self):
        feed = SimulationFeed(volume_noise=0)
        feed._assets[ASSETS[-1]].base_volume = 1e308
        before = self.snapshot(feed)
        # Price draw then volume draw for every asset; the last volume overflows.
        with patch.object(random.Random, "gauss", side_effect=[0, 1] * len(ASSETS)):
            with self.assertRaises(MarketValueError):
                await feed.get_ticks(ASSETS)
        self.assertEqual(self.snapshot(feed), before)


if __name__ == "__main__":
    unittest.main()
