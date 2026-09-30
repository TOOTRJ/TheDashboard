"""Validation shared by market observations and simulated trade arithmetic."""

from __future__ import annotations

import math


class MarketValueError(ValueError):
    """An observation or monetary calculation cannot be used safely."""

    code = "invalid_market_value"

    def __init__(self):
        # Values may come from a provider; do not include them in public errors.
        super().__init__(self.code)


class ProbeStepError(RuntimeError):
    """A failed step together with the events its completed actions produced."""

    def __init__(self, events, cause: Exception):
        self.events = tuple(events)
        self.cause = cause
        super().__init__("Probe step failed")


def finite_number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MarketValueError()
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise MarketValueError() from None
    if not math.isfinite(result):
        raise MarketValueError()
    return result


def nonnegative_value(value) -> float:
    result = finite_number(value)
    if result < 0:
        raise MarketValueError()
    return result


def positive_price(value) -> float:
    result = finite_number(value)
    if result <= 0:
        raise MarketValueError()
    return result


def trade_return(entry_price, exit_price) -> float:
    """A recorded zero terminal value is a loss; a missing exit is invalid."""
    entry = positive_price(entry_price)
    exit_value = nonnegative_value(exit_price)
    return finite_number((exit_value - entry) / entry)


def position_value(amount, entry_price, exit_price) -> float:
    """Value a position without cancelling principal or underflowing a ratio.

    Separating mantissas/exponents keeps amount * exit / entry representable
    when the intermediate exit / entry would overflow or underflow. If the
    final positive value itself is unrepresentable, fail instead of inventing
    a zero terminal value.
    """
    cost = nonnegative_value(amount)
    entry = positive_price(entry_price)
    exit_value = nonnegative_value(exit_price)
    if cost == 0 or exit_value == 0:
        return 0.0
    cost_mantissa, cost_exponent = math.frexp(cost)
    entry_mantissa, entry_exponent = math.frexp(entry)
    exit_mantissa, exit_exponent = math.frexp(exit_value)
    mantissa = cost_mantissa * (exit_mantissa / entry_mantissa)
    try:
        result = math.ldexp(mantissa, cost_exponent + exit_exponent - entry_exponent)
    except OverflowError:
        raise MarketValueError() from None
    return positive_price(result)
