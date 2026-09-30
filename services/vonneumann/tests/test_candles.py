"""Offline completed-minute aggregation and shared indicator contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
import math
import unittest

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.market.candles import CandleHistory, MinuteCandle, MINUTE_RETENTION
    from vonneumann.market.feed import MarketFeedError


A, B = "SOL/USDC", "JUP/USDC"


def candle(index, *, asset=A, price=None, volume=1.0, **overrides):
    close = float(index + 2 if price is None else price)
    values = dict(asset=asset, start=index * 60, open=close, high=close,
                  low=close, close=close, volume=volume, source="fixture-minutes-v1")
    values.update(overrides)
    return MinuteCandle(**values)


class CandleHistoryTests(OfflineTestMixin, unittest.TestCase):
    def reject(self, action, code="candle_invalid"):
        with self.assertRaises(MarketFeedError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception),
                         "Market data refresh failed. Execution requires valid provider data.")

    def capture(self, history):
        return tuple((asset, history.last_start(asset),
                      tuple(history.latest(asset, tf) for tf in range(1, 61)))
                     for asset in (A, B))

    def test_minute_is_immutable_and_normalizes_integral_start_and_numbers(self):
        bar = candle(1, start=60.0, price=3, volume=0)
        self.assertEqual(bar.end, 120)
        self.assertIs(type(bar.start), int)
        self.assertIs(type(bar.close), float)
        self.assertEqual(bar.quote_currency, "USD")
        self.assertEqual(bar.volume_unit, "base_token")
        with self.assertRaises(FrozenInstanceError):
            bar.close = 10

    def test_numeric_shapes_prices_volume_and_alignment_fail_strictly(self):
        for value in (True, False, None, "2", -1, float("nan"), float("inf"), 10**400):
            for field in ("start", "open", "high", "low", "close", "volume"):
                with self.subTest(field=field, kind=type(value).__name__):
                    self.reject(lambda: candle(0, **{field: value}))
        for field in ("open", "high", "low", "close"):
            self.reject(lambda: candle(0, **{field: 0}))
        for start in (1, 59, 60.5):
            self.reject(lambda: candle(0, start=start))
        for change in ({"high": 1}, {"low": 3}, {"open": 3}, {"close": 3}):
            self.reject(lambda: candle(0, **change))

    def test_metadata_and_api_selectors_are_strict(self):
        for field in ("asset", "source", "quote_currency", "volume_unit"):
            for value in (None, True, "", " bad "):
                self.reject(lambda: candle(0, **{field: value}))
        for assets in (None, A, [], [A, A], [A, None]):
            self.reject(lambda: CandleHistory(assets))
        history = CandleHistory([A])
        for tf in (0, 61, True, 5.0, "5"):
            self.reject(lambda: history.latest(A, tf))
        self.reject(lambda: history.latest(B, 5))
        self.reject(lambda: history.last_start(B))
        self.assertIsNone(history.latest(A, 1))
        self.assertIsNone(history.last_start(A))

    def test_forming_bar_is_rejected_and_exact_end_is_accepted(self):
        history = CandleHistory([A])
        self.reject(lambda: history.ingest([candle(0)], available_at=59.999), "candle_incomplete")
        self.assertIsNone(history.last_start(A))
        history.ingest([candle(0)], available_at=60)
        self.assertEqual(history.latest(A, 1).end, 60)

    def test_invalid_clock_or_malformed_batch_does_not_commit(self):
        history = CandleHistory([A, B])
        history.ingest([candle(0), candle(0, asset=B)], available_at=60)
        before = self.capture(history)
        for stamp in (None, True, "120", -1, float("nan"), float("inf"), 10**400):
            self.reject(lambda: history.ingest([candle(1)], available_at=stamp))
        for batch in (None, [candle(1), {}], [candle(1), candle(1, asset="unknown")]):
            self.reject(lambda: history.ingest(batch, available_at=120))
        self.assertEqual(self.capture(history), before)

    def test_seven_minute_ohlcv_uses_utc_epoch_bucket_across_hour_boundary(self):
        history = CandleHistory([A])
        bars = [candle(i, open=i + 1, high=i + 4, low=i + 0.5,
                       close=i + 2, volume=i + 1) for i in range(56, 63)]
        history.ingest(reversed(bars), available_at=63 * 60)
        snapshot = history.latest(A, 7)
        self.assertEqual((snapshot.start, snapshot.end), (56 * 60, 63 * 60))
        self.assertEqual((snapshot.open, snapshot.high, snapshot.low, snapshot.close),
                         (57, 66, 56.5, 64))
        self.assertEqual(snapshot.volume, sum(range(57, 64)))
        self.assertEqual(snapshot.closes, (64.0,))
        self.assertEqual(snapshot.completed_count, 1)

    def test_seven_minute_anchor_does_not_reset_at_day_boundary(self):
        history = CandleHistory([A])
        # 1435 is an epoch-aligned seven-minute bucket and straddles midnight.
        history.ingest([candle(i) for i in range(1435, 1442)], available_at=1442 * 60)
        snapshot = history.latest(A, 7)
        self.assertEqual((snapshot.start, snapshot.end), (1435 * 60, 1442 * 60))

    def test_partial_leading_and_current_buckets_never_seed_indicators(self):
        history = CandleHistory([A])
        history.ingest([candle(i) for i in range(2, 7)], available_at=7 * 60)
        self.assertIsNone(history.latest(A, 7))
        history.ingest([candle(i) for i in range(7, 13)], available_at=13 * 60)
        self.assertIsNone(history.latest(A, 7))
        history.ingest([candle(13)], available_at=14 * 60)
        self.assertEqual(history.latest(A, 7).start, 7 * 60)
        self.assertEqual(history.latest(A, 7).completed_count, 1)
        history.ingest([candle(14)], available_at=15 * 60)
        self.assertEqual(history.latest(A, 7).end, 14 * 60)

    def test_all_integer_timeframes_have_independent_complete_buckets(self):
        history = CandleHistory([A])
        history.ingest([candle(i) for i in range(121)], available_at=121 * 60)
        for tf in range(1, 61):
            with self.subTest(tf=tf):
                latest = history.latest(A, tf)
                self.assertEqual(latest.completed_count, 121 // tf)
                self.assertEqual(latest.end, (121 // tf) * tf * 60)
                self.assertEqual(latest.volume, tf)

    def test_sorted_history_and_incremental_ingestion_are_identical(self):
        bars = [candle(i, asset=asset, price=100 + (i % 17), volume=i % 5)
                for i in range(181) for asset in (A, B)]
        batched, incremental = CandleHistory([A, B]), CandleHistory([A, B])
        batched.ingest(reversed(bars), available_at=181 * 60)
        for offset in range(0, len(bars), 14):
            chunk = bars[offset:offset + 14]
            incremental.ingest(chunk, available_at=max(c.end for c in chunk))
        self.assertEqual(self.capture(batched), self.capture(incremental))

    def test_exact_duplicates_and_overlapping_batches_do_not_advance_state(self):
        history = CandleHistory([A, B])
        bars = [candle(i) for i in range(25)]
        history.ingest([*bars, *bars], available_at=25 * 60)
        before = self.capture(history)
        history.ingest(reversed(bars[5:]), available_at=25 * 60)
        self.assertEqual(self.capture(history), before)
        self.assertEqual(history.latest(A, 1).completed_count, 25)

    def test_revision_in_existing_or_same_batch_is_atomic_across_assets(self):
        history = CandleHistory([A, B])
        history.ingest([candle(0), candle(0, asset=B)], available_at=60)
        before = self.capture(history)
        self.reject(lambda: history.ingest(
            [candle(1), candle(0, asset=B, volume=2)], available_at=120), "candle_revision")
        self.assertEqual(self.capture(history), before)
        self.reject(lambda: history.ingest(
            [candle(1), candle(1, volume=2)], available_at=120), "candle_revision")
        self.assertEqual(self.capture(history), before)

    def test_gap_rejects_every_asset_staging_update_without_padding(self):
        history = CandleHistory([A, B])
        history.ingest([candle(0), candle(0, asset=B)], available_at=60)
        before = self.capture(history)
        self.reject(lambda: history.ingest(
            [candle(1), candle(2, asset=B)], available_at=180), "candle_gap")
        self.assertEqual(self.capture(history), before)
        empty = CandleHistory([A])
        self.reject(lambda: empty.ingest([candle(0), candle(2)], available_at=180), "candle_gap")
        self.assertIsNone(empty.last_start(A))

    def test_provider_currency_and_volume_unit_cannot_change_mid_series(self):
        history = CandleHistory([A, B])
        history.ingest([candle(0)], available_at=60)
        before = self.capture(history)
        for changed in ({"source": "different"}, {"quote_currency": "USDC"}, {"volume_unit": "USD"}):
            self.reject(lambda: history.ingest(
                [candle(0, asset=B), candle(1, **changed)], available_at=120), "candle_source_changed")
            self.assertEqual(self.capture(history), before)

    def test_sma_seed_then_recursive_ema_matches_hand_calculated_fixture(self):
        history = CandleHistory([A])
        history.ingest([candle(0, price=2), candle(1, price=4)], available_at=120)
        self.assertEqual(dict(history.latest(A, 1).emas), {2: 3.0})
        history.ingest([candle(2, price=8)], available_at=180)
        snapshot = history.latest(A, 1)
        self.assertAlmostEqual(snapshot.emas[2], 19 / 3)
        self.assertAlmostEqual(snapshot.emas[3], 14 / 3)
        history.ingest([candle(3, price=16)], available_at=240)
        snapshot = history.latest(A, 1)
        self.assertAlmostEqual(snapshot.emas[2], 115 / 9)
        self.assertAlmostEqual(snapshot.emas[3], 31 / 3)
        self.assertEqual(snapshot.emas[4], 7.5)
        self.assertNotIn(5, snapshot.emas)

    def test_snapshots_are_deeply_immutable_and_preserved_after_later_ingestion(self):
        history = CandleHistory([A])
        history.ingest([candle(i) for i in range(3)], available_at=180)
        first = history.latest(A, 1)
        with self.assertRaises(FrozenInstanceError):
            first.end = 0
        with self.assertRaises(TypeError):
            first.emas[2] = 0
        original = {2: 7.0}
        copied = replace(first, emas=original)
        original[2] = 99
        self.assertEqual(copied.emas[2], 7)
        history.ingest([candle(3)], available_at=240)
        self.assertEqual(first.end, 180)
        self.assertEqual(first.completed_count, 3)
        self.assertIsNot(first, history.latest(A, 1))

    def test_volume_overflow_fails_whole_batch_without_mutating_other_asset(self):
        history = CandleHistory([A, B])
        history.ingest([candle(0, volume=1e308)], available_at=60)
        before = self.capture(history)
        self.reject(lambda: history.ingest(
            [candle(0, asset=B), candle(1, volume=1e308)], available_at=120))
        self.assertEqual(self.capture(history), before)

    def test_ema_seed_supports_extreme_representable_prices(self):
        for price in (1e308, math.ulp(0.0)):
            with self.subTest(price=price):
                history = CandleHistory([A])
                history.ingest([candle(i, price=price) for i in range(61)], available_at=61 * 60)
                self.assertEqual(history.latest(A, 1).emas[60], price)

    def test_shared_ema_survives_retention_and_late_reader_matches_original_origin(self):
        history = CandleHistory([A])
        count = MINUTE_RETENTION + 8
        values = [100.0 + (i % 29) ** 2 / 10 for i in range(count)]
        history.ingest([candle(i, price=value) for i, value in enumerate(values)], available_at=count * 60)
        snapshot = history.latest(A, 1)
        self.assertEqual(snapshot.completed_count, count)
        self.assertEqual(len(snapshot.closes), 64)
        self.assertEqual(len(snapshot.volumes), 21)
        self.assertEqual(len(history._assets[A].minutes), MINUTE_RETENTION)
        with localcontext() as context:
            context.prec = 50
            expected = sum(Decimal(str(value)) for value in values[:60]) / Decimal(60)
            alpha = Decimal(2) / Decimal(61)
            for value in values[60:]:
                expected = (Decimal(1) - alpha) * expected + alpha * Decimal(str(value))
        self.assertAlmostEqual(snapshot.emas[60], float(expected), places=11)
        # A newborn is only a new reader; it cannot reset the shared seed.
        self.assertIs(history.latest(A, 1), snapshot)
        old = history.latest(A, 60)
        self.assertEqual(old.completed_count, count // 60)
        self.assertIn(60, old.emas)
        before = history.last_start(A), snapshot, old
        self.reject(lambda: history.ingest([candle(0, price=values[0])], available_at=count * 60),
                    "candle_history_expired")
        self.assertEqual((history.last_start(A), history.latest(A, 1), history.latest(A, 60)), before)
        oldest_kept = count - MINUTE_RETENTION
        history.ingest([candle(oldest_kept, price=values[oldest_kept])], available_at=count * 60)
        self.assertEqual(history.latest(A, 1), snapshot)
