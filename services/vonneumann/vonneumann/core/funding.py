"""Safe failures and bounded roundoff handling for candidate funding."""

import math


class FundingError(RuntimeError):
    """A mandatory population change cannot be applied safely."""

    def __init__(self, code: str = "funding_invalid_plan"):
        self.code = code
        super().__init__(code)


def valid_cash(value: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def funding_tolerance(available: float, required: float) -> float:
    return min(1e-9, 8 * max(math.ulp(available), math.ulp(required)))


def sum_cashflows(values) -> float:
    try:
        result = math.fsum(values)
    except (OverflowError, ValueError):
        raise FundingError() from None
    if not math.isfinite(result):
        raise FundingError()
    return result


def can_fund(available: float, required: float) -> bool:
    if not valid_cash(available) or not valid_cash(required):
        return False
    # Permit only floating-point noise, never a dollar-scale relative tolerance.
    tolerance = funding_tolerance(available, required)
    return available >= required or required - available <= tolerance
