"""Offline acceptance tests for the local source-age safety policy."""

from __future__ import annotations

from dataclasses import replace
import unittest

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.market.feed import MarketFeedError, MarketTick, QuoteEvidence
    from vonneumann.market.quote_freshness import quote_source_age, source_slot, validate_quote


class QuoteFreshnessTests(OfflineTestMixin, unittest.TestCase):
    def tick(self, *, timestamp=1_700_000_000.0, slot=100, received=None,
             monotonic=500.0, price=100.0):
        return MarketTick(
            "SOL/USDC", price, 1000.0, timestamp,
            QuoteEvidence(slot, timestamp if received is None else received, monotonic),
        )

    def assert_rejected(self, tick, code, *, wall_now=1_700_000_000.0,
                        monotonic_now=500.0, previous_slot=None):
        with self.assertRaises(MarketFeedError) as raised:
            validate_quote(tick, wall_now=wall_now, monotonic_now=monotonic_now,
                           previous_slot=previous_slot)
        self.assertEqual(raised.exception.code, code)

    def test_thirty_second_age_boundary_is_inclusive(self):
        tick = self.tick()
        validate_quote(tick, wall_now=tick.timestamp + 30, monotonic_now=530)
        self.assert_rejected(tick, "price_stale", wall_now=tick.timestamp + 30.0001,
                             monotonic_now=530.0001)

    def test_future_tolerance_checks_both_receipt_and_consumption(self):
        tick = self.tick(timestamp=1_700_000_002.0, received=1_700_000_000.0)
        validate_quote(tick, wall_now=1_700_000_000.0, monotonic_now=500)
        self.assert_rejected(replace(tick, timestamp=tick.timestamp + 0.0001),
                             "source_time_invalid")
        self.assert_rejected(tick, "source_time_invalid", wall_now=1_699_999_999.999)

    def test_time_spent_resolving_source_and_in_cache_counts_toward_age(self):
        tick = self.tick(received=1_700_000_028.0)
        validate_quote(tick, wall_now=1_700_000_030.0, monotonic_now=502)
        self.assert_rejected(tick, "price_stale", wall_now=1_700_000_030.01,
                             monotonic_now=502.01)

    def test_wall_clock_rollback_cannot_rejuvenate_cached_quote(self):
        tick = self.tick(received=1_700_000_020.0)
        self.assert_rejected(tick, "price_stale", wall_now=1_700_000_005.0,
                             monotonic_now=511)

    def test_forward_wall_clock_jump_expires_quote_without_monotonic_jump(self):
        self.assert_rejected(self.tick(), "price_stale", wall_now=1_700_000_031.0)

    def test_backwards_monotonic_time_is_invalid(self):
        self.assert_rejected(self.tick(), "source_time_invalid", monotonic_now=499.999)

    def test_missing_or_wrong_evidence_never_becomes_receipt_time_fallback(self):
        for evidence in (None, {}, {"source_slot": 100}, "known"):
            with self.subTest(evidence=evidence):
                self.assert_rejected(replace(self.tick(), evidence=evidence),
                                     "source_time_unavailable")

    def test_source_slot_requires_u64_integer_without_boolean_coercion(self):
        self.assertEqual(source_slot(0), 0)
        self.assertEqual(source_slot(2**64 - 1), 2**64 - 1)
        for value in (None, True, False, -1, 2**64, 100.0, "100", float("nan")):
            with self.subTest(value=value):
                self.assert_rejected(self.tick(slot=value), "source_time_invalid")

    def test_all_clock_metadata_rejects_nonfinite_negative_and_coerced_values(self):
        for value in (None, True, False, -1, float("nan"), float("inf"), "500", 10**400):
            for field in ("timestamp", "received_at", "received_monotonic", "wall_now", "monotonic_now"):
                with self.subTest(field=field, value=value):
                    tick = self.tick()
                    kwargs = {"wall_now": 1_700_000_000.0, "monotonic_now": 500.0}
                    if field == "timestamp":
                        tick = replace(tick, timestamp=value)
                    elif field in {"received_at", "received_monotonic"}:
                        tick = replace(tick, evidence=replace(tick.evidence, **{field: value}))
                    elif value is None:
                        # None intentionally means use the injected/default clock.
                        continue
                    else:
                        kwargs[field] = value
                    self.assert_rejected(tick, "source_time_invalid", **kwargs)

    def test_provider_and_currency_must_match_the_supported_evidence_contract(self):
        for evidence in (replace(self.tick().evidence, provider="unknown"),
                         replace(self.tick().evidence, quote_currency="USDC")):
            self.assert_rejected(replace(self.tick(), evidence=evidence), "source_time_invalid")

    def test_slot_regression_is_rejected_even_when_its_timestamp_is_recent(self):
        self.assert_rejected(self.tick(slot=99), "source_slot_regressed", previous_slot=100)

    def test_same_slot_price_changes_and_identical_repeats_keep_original_age(self):
        for tick in (self.tick(), self.tick(price=101.0)):
            with self.subTest(price=tick.price):
                validate_quote(tick, previous_slot=100, wall_now=1_700_000_001.0,
                               monotonic_now=501)
                self.assert_rejected(tick, "price_stale", previous_slot=100,
                                     wall_now=1_700_000_031.0, monotonic_now=531)

    def test_carried_age_floor_preserves_expiry_after_receipt_clock_rollback(self):
        tick = self.tick(received=1_700_000_005.0, monotonic=520.0)
        tick = replace(tick, evidence=replace(tick.evidence, source_age_at_receipt=28.0))
        validate_quote(tick, wall_now=1_700_000_007.0, monotonic_now=522.0)
        self.assertEqual(quote_source_age(tick, wall_now=1_700_000_007.0,
                                         monotonic_now=522.0), 30.0)
        self.assert_rejected(tick, "price_stale", wall_now=1_700_000_007.01,
                             monotonic_now=522.01)

    def test_invalid_carried_age_floor_cannot_bypass_timestamp_validation(self):
        for floor in (-1, float("nan"), float("inf"), True, False, "20", 10**400):
            with self.subTest(floor=floor):
                tick = self.tick()
                tick = replace(tick, evidence=replace(tick.evidence, source_age_at_receipt=floor))
                self.assert_rejected(tick, "source_time_invalid")

    def test_expired_evidence_remains_usable_as_an_age_anchor_only(self):
        tick = self.tick()
        self.assertEqual(quote_source_age(tick, wall_now=1_700_000_005.0,
                                         monotonic_now=535), 35.0)
        self.assert_rejected(tick, "price_stale", wall_now=1_700_000_005.0,
                             monotonic_now=535)
