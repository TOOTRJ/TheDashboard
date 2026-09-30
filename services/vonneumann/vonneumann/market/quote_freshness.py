"""Conservative, local source-age policy; this does not prove price finality."""

from __future__ import annotations

import math
import time

from .feed import MarketFeedError, MarketTick, QuoteEvidence

MAX_SOURCE_AGE_SECONDS = 30.0
FUTURE_TOLERANCE_SECONDS = 2.0
QUOTE_POLICY = {
    "version": "jupiter-source-age-v1",
    "provider": "jupiter-price-v3",
    "quote_currency": "USD",
    "source_time": "solana-estimated-block-time",
    "max_source_age_seconds": MAX_SOURCE_AGE_SECONDS,
    "future_tolerance_seconds": FUTURE_TOLERANCE_SECONDS,
}


def source_slot(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**64:
        raise MarketFeedError("source_time_invalid")
    return value


def _time_value(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MarketFeedError("source_time_invalid")
    try:
        value = float(value)
    except OverflowError:
        raise MarketFeedError("source_time_invalid") from None
    if not math.isfinite(value) or value < 0:
        raise MarketFeedError("source_time_invalid")
    return value


def quote_source_age(tick: MarketTick, *, wall_now: float | None = None,
                     monotonic_now: float | None = None) -> float:
    """Compute conservative age, including expired evidence used as an anchor."""
    evidence = tick.evidence
    if not isinstance(evidence, QuoteEvidence):
        raise MarketFeedError("source_time_unavailable")
    source_slot(evidence.source_slot)
    if evidence.provider != "jupiter-price-v3" or evidence.quote_currency != "USD":
        raise MarketFeedError("source_time_invalid")
    stamp = _time_value(tick.timestamp)
    received = _time_value(evidence.received_at)
    received_mono = _time_value(evidence.received_monotonic)
    now = _time_value(time.time() if wall_now is None else wall_now)
    mono = _time_value(time.monotonic() if monotonic_now is None else monotonic_now)
    elapsed = mono - received_mono
    initial_age, wall_age = received - stamp, now - stamp
    if elapsed < 0 or initial_age < -FUTURE_TOLERANCE_SECONDS or wall_age < -FUTURE_TOLERANCE_SECONDS:
        raise MarketFeedError("source_time_invalid")
    floor = 0.0 if evidence.source_age_at_receipt is None else _time_value(evidence.source_age_at_receipt)
    return max(wall_age, max(0.0, initial_age, floor) + elapsed)


def validate_quote(tick: MarketTick, *, previous_slot: int | None = None,
                   wall_now: float | None = None, monotonic_now: float | None = None) -> None:
    """Require known age at every consumption boundary, including cache hits.

    Monotonic elapsed time prevents a wall-clock rollback from extending quote
    validity. Current wall age is also considered, so forward jumps fail safely.
    Same-slot price changes are permitted; lower source slots are not.
    """
    age = quote_source_age(tick, wall_now=wall_now, monotonic_now=monotonic_now)
    if age > MAX_SOURCE_AGE_SECONDS:
        raise MarketFeedError("price_stale")
    if previous_slot is not None and tick.evidence.source_slot < source_slot(previous_slot):
        raise MarketFeedError("source_slot_regressed")
