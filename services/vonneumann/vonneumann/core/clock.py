"""Clock boundaries for modeled market time and real service time."""

from datetime import datetime, timezone

from .market_validation import MarketValueError, nonnegative_value


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_datetime(value: float) -> datetime:
    """Reject invalid/unrepresentable Unix time instead of silently using now."""
    seconds = nonnegative_value(value)
    try:
        return datetime.fromtimestamp(seconds, timezone.utc)
    except (ValueError, OverflowError, OSError):
        raise MarketValueError() from None


def clock_datetime(value: datetime) -> datetime:
    """Only timezone-aware instants can become ledger or event timestamps."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MarketValueError()
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise MarketValueError() from None
