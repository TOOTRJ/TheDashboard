"""Immutable, observed portfolio-equity diagnostics on nominal UTC minutes.

An endpoint is an as-of valuation: it may use a previously observed frozen
portfolio, but never a future price or current holdings at a historical time.
The resulting Sharpe statistic is descriptive, unannualized, and has no role
in validating a strategy or determining whether its sample is sufficient.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
import statistics
from types import MappingProxyType
from typing import Iterable

from .market_validation import MarketValueError, finite_number, nonnegative_value


INTERVAL_SECONDS = 60
MAX_OBSERVATION_CARRY_SECONDS = 30
MAX_RETURN_WINDOW = 1440
EQUITY_METRICS_POLICY = MappingProxyType({
    "version": "equity-asof-minute-v1",
    "interval_seconds": INTERVAL_SECONDS,
    "endpoint_anchor": "unix_epoch_utc",
    "endpoint_valuation": "latest_observation_at_or_before_endpoint",
    "exact_endpoint": "current_observation_preferred_without_revision",
    "max_observation_carry_seconds": MAX_OBSERVATION_CARRY_SECONDS,
    "max_contiguous_returns": MAX_RETURN_WINDOW,
    "gaps": "reset_contiguous_segment_without_interpolation",
    "missing_periods_definition": "missing_nominal_endpoints_after_first_observation",
    "zero_denominator": "reset_contiguous_segment",
    "benchmark_return_per_period": 0.0,
    "benchmark_assumption": "zero_return_cash_not_a_claim_of_risk_free_usdc",
    "standard_deviation": "sample_n_minus_one",
    "annualized": False,
    "minimum_computable_returns": 2,
    "statistical_significance": "not_established",
})


def return_statistics(returns: Iterable[float], risk_free_per_period: float = 0.0) -> dict:
    """Describe same-period returns, without epsilon denominators or capping.

Malformed inputs raise a safe validation error. Finite inputs whose derived
arithmetic cannot be represented produce an unavailable diagnostic instead.
The benchmark's units must equal the supplied return period.
"""
    values = tuple(finite_number(value) for value in returns)
    benchmark = finite_number(risk_free_per_period)
    result = {"status": "insufficient_samples", "sharpe_ratio": None,
              "return_count": len(values), "mean_excess_return": None,
              "sample_standard_deviation": None}
    if not values:
        return result
    try:
        excess = tuple(finite_number(value - benchmark) for value in values)
        result["mean_excess_return"] = finite_number(statistics.mean(excess))
        if len(excess) < 2:
            return result
        deviation = nonnegative_value(statistics.stdev(excess))
        result["sample_standard_deviation"] = deviation
        if deviation == 0:
            result["status"] = "zero_variance"
            return result
        result["sharpe_ratio"] = finite_number(result["mean_excess_return"] / deviation)
        result["status"] = "available"
    except (MarketValueError, ArithmeticError, statistics.StatisticsError):
        result["status"] = "invalid_arithmetic"
        result["sharpe_ratio"] = None
    return result


def calculate_sharpe(returns: Iterable[float], risk_free_per_period: float = 0.0) -> float | None:
    """Compatibility helper; use return_statistics when validity metadata matters."""
    return return_statistics(returns, risk_free_per_period)["sharpe_ratio"]


@dataclass(frozen=True)
class EquityObservation:
    equity: float
    observed_at: float
    valid_until: float

    def __post_init__(self) -> None:
        equity = nonnegative_value(self.equity)
        observed_at = nonnegative_value(self.observed_at)
        valid_until = nonnegative_value(self.valid_until)
        if valid_until < observed_at:
            raise MarketValueError()
        object.__setattr__(self, "equity", equity)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "valid_until", min(
            valid_until, observed_at + MAX_OBSERVATION_CARRY_SECONDS))

    def covers(self, endpoint: int) -> bool:
        return (self.observed_at <= endpoint <= self.valid_until
                and endpoint - self.observed_at <= MAX_OBSERVATION_CARRY_SECONDS)


@dataclass(frozen=True)
class EquitySample:
    endpoint: int
    equity: float
    observed_at: float
    valid_until: float


@dataclass(frozen=True)
class EquityHistory:
    """Most recent contiguous endpoint-return segment plus lifetime gap counts.

Caller-supplied observations must already represent a complete portfolio with
admissible marks. `valid_until` must incorporate the oldest required quote's
remaining freshness; cash-only observations are still limited to 30 seconds.
No mutation occurs when observation validation fails.
"""

    capacity: int = MAX_RETURN_WINDOW
    returns: tuple[float, ...] = ()
    last_observation: EquityObservation | None = None
    last_sample: EquitySample | None = None
    missing_periods: int = 0
    invalid_intervals: int = 0
    window_start_endpoint: int | None = None
    _processed_endpoint: int | None = None
    _invalid_arithmetic: bool = False
    _statistics_returns: tuple[float, ...] | None = field(default=None, repr=False, compare=False)
    _statistics: tuple[tuple[str, object], ...] = field(default=(), repr=False, compare=False)

    def __post_init__(self) -> None:
        if (isinstance(self.capacity, bool) or not isinstance(self.capacity, int)
                or not 2 <= self.capacity <= MAX_RETURN_WINDOW):
            raise MarketValueError()
        object.__setattr__(self, "returns", tuple(self.returns))
        if len(self.returns) > self.capacity:
            raise MarketValueError()
        # Immutable tuple identity survives same-period dataclass.replace().
        # Only a new return segment/window requires the exact-ratio arithmetic.
        if self._statistics_returns is not self.returns:
            object.__setattr__(self, "_statistics", tuple(return_statistics(self.returns).items()))
            object.__setattr__(self, "_statistics_returns", self.returns)

    def observe(self, equity: float, observed_at: float, valid_until: float) -> EquityHistory:
        """Return a new state, consuming at most two covered endpoint samples.

At most one future endpoint can be covered by the previous observation's
30-second lifetime. Any intervening missing endpoints are counted in O(1),
even after years of downtime. An exact current endpoint can also be sampled.
"""
        current = EquityObservation(equity, observed_at, valid_until)
        previous = self.last_observation
        if previous is not None and current.observed_at < previous.observed_at:
            raise MarketValueError()
        endpoint = math.floor(current.observed_at / INTERVAL_SECONDS) * INTERVAL_SECONDS
        exact = current.observed_at == endpoint
        if self._processed_endpoint is None:
            state = self._sample(current, endpoint) if exact else self
            return replace(state, last_observation=current, _processed_endpoint=endpoint)
        if endpoint <= self._processed_endpoint:
            # Same-period updates change only the next endpoint's candidate.
            # Even an exact duplicate cannot revise a published return.
            return replace(self, last_observation=current)

        first_endpoint = self._processed_endpoint + INTERVAL_SECONDS
        endpoint_count = (endpoint - first_endpoint) // INTERVAL_SECONDS + 1
        state = self
        sampled_first = False
        if previous is not None and previous.covers(first_endpoint) and not (exact and first_endpoint == endpoint):
            state = state._sample(previous, first_endpoint)
            sampled_first = True

        missing = endpoint_count - int(sampled_first) - int(exact)
        if missing:
            # This gap follows any previous-observation sample and precedes
            # any exact-current sample. Never bridge it with a longer return.
            state = replace(state, returns=(), missing_periods=state.missing_periods + missing,
                            window_start_endpoint=None, _invalid_arithmetic=False)
        if exact:
            # The exact endpoint is the latest valid observation, preferred to
            # a still-valid older observation for that same endpoint.
            state = state._sample(current, endpoint, force_baseline=bool(missing))
        return replace(state, last_observation=current, _processed_endpoint=endpoint)

    def _sample(self, observation: EquityObservation, endpoint: int, *,
                force_baseline: bool = False) -> EquityHistory:
        sample = EquitySample(endpoint, observation.equity, observation.observed_at, observation.valid_until)
        previous = self.last_sample
        if force_baseline or previous is None or previous.endpoint + INTERVAL_SECONDS != endpoint:
            return replace(self, returns=(), last_sample=sample,
                           window_start_endpoint=endpoint, _invalid_arithmetic=False)
        try:
            if previous.equity <= 0:
                raise MarketValueError()
            value = finite_number((sample.equity - previous.equity) / previous.equity)
        except (MarketValueError, ArithmeticError):
            # A terminal -100% return is valid. Returns *from* zero, or an
            # unrepresentable ratio, cannot extend a meaningful segment.
            return replace(self, returns=(), last_sample=sample, window_start_endpoint=endpoint,
                           invalid_intervals=self.invalid_intervals + 1, _invalid_arithmetic=True)
        returns = (*self.returns, value)[-self.capacity:]
        return replace(self, returns=returns, last_sample=sample, _invalid_arithmetic=False,
                       window_start_endpoint=endpoint - len(returns) * INTERVAL_SECONDS)

    def diagnostic(self) -> dict:
        """JSON-compatible diagnostic with observation and coverage provenance."""
        result = dict(self._statistics)
        if self._invalid_arithmetic:
            result.update(status="invalid_arithmetic", sharpe_ratio=None)
        sample, observation = self.last_sample, self.last_observation
        result.update({
            "policy_version": EQUITY_METRICS_POLICY["version"],
            "interval_seconds": INTERVAL_SECONDS,
            "annualized": False,
            "risk_free_per_period": 0.0,
            "capacity": self.capacity,
            "missing_periods": self.missing_periods,
            "invalid_intervals": self.invalid_intervals,
            "window_start_endpoint": self.window_start_endpoint,
            "last_sample_endpoint": sample.endpoint if sample else None,
            "last_sample_observed_at": sample.observed_at if sample else None,
            "last_sample_valid_until": sample.valid_until if sample else None,
            "last_sample_observation_age_seconds": sample.endpoint - sample.observed_at if sample else None,
            "last_observed_at": observation.observed_at if observation else None,
            "last_observation_valid_until": observation.valid_until if observation else None,
            "last_processed_endpoint": self._processed_endpoint,
        })
        return result
