"""Deterministic synthetic market frames with an explicit modeled clock.

Drift and volatility describe one modeled step, not elapsed wall time or
calibrated market returns. The default step is one simulated minute; playback
delays do not change the path. This feed does not aggregate timeframe candles.
"""

from __future__ import annotations

import hashlib
import math
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from ..core.market_validation import (
    MarketValueError,
    finite_number,
    nonnegative_value,
    positive_price,
)
from .feed import MarketFeed, MarketTick

# Baseline prices for simulation assets
BASE_PRICES: dict[str, float] = {
    "SOL/USDC": 150.0,
    "JUP/USDC": 0.85,
    "BONK/USDC": 0.000025,
    "WIF/USDC": 2.10,
    "JTO/USDC": 3.50,
    "PYTH/USDC": 0.42,
    "ORCA/USDC": 3.80,
    "RAY/USDC": 2.20,
}

BASE_VOLUMES: dict[str, float] = {
    "SOL/USDC": 1_000_000,
    "JUP/USDC": 500_000,
    "BONK/USDC": 2_000_000,
    "WIF/USDC": 300_000,
    "JTO/USDC": 200_000,
    "PYTH/USDC": 150_000,
    "ORCA/USDC": 100_000,
    "RAY/USDC": 180_000,
}


@dataclass
class AssetState:
    """Internal state tracking for a single simulated asset."""

    current_price: float
    base_volume: float
    drift: float = 0.0001
    volatility: float = 0.02  # Log-return standard deviation per modeled step.
    tick_count: int = 0


class SimulationFeed(MarketFeed):
    """
    Seeded geometric price paths independent of requested asset order/subsets.

    Every nonempty batch advances every supported asset once and returns the
    requested subset at the same timestamp. The default seed deliberately gives
    all colonies the same market path; optimizer randomness cannot alter it.
    The first frame is at start_timestamp + step_seconds.
    """

    def __init__(
        self,
        drift: float = 0.0001,
        volatility: float = 0.02,
        volume_noise: float = 0.5,
        *,
        seed: int = 0,
        start_timestamp: float = 1704067200.0,
        step_seconds: float = 60.0,
    ):
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**64:
            raise MarketValueError()
        self._seed = seed
        self._drift = finite_number(drift)
        self._volatility = nonnegative_value(volatility)
        self._volume_noise = nonnegative_value(volume_noise)
        # Reject unrepresentable variance before any market path is created.
        finite_number(self._volatility * self._volatility)
        self._start_timestamp = self._validate_timestamp(start_timestamp)
        self._step_seconds = positive_price(step_seconds)
        self._current_timestamp = self._start_timestamp
        self._frame_number = 0
        self._next_timestamp()  # A configured step must advance the float clock.
        self._assets: dict[str, AssetState] = {}
        self._rngs: dict[str, random.Random] = {}

        for asset, price in BASE_PRICES.items():
            self._assets[asset] = AssetState(
                current_price=positive_price(price),
                base_volume=nonnegative_value(BASE_VOLUMES[asset]),
                drift=self._drift,
                volatility=self._volatility,
            )
            # Python's built-in hash varies across processes. A versioned digest
            # makes each asset's private stream stable and independent instead.
            digest = hashlib.sha256(f"vonneumann-sim-v1:{seed}:{asset}".encode()).digest()
            self._rngs[asset] = random.Random(int.from_bytes(digest, "big"))

    @property
    def current_timestamp(self) -> float:
        """Last committed frame time, or the start time before the first frame."""
        return self._current_timestamp

    @property
    def simulation_spec(self) -> dict:
        """A copied, JSON-safe description sufficient to reproduce the feed.

        Seeds are decimal strings so the full unsigned 64-bit range survives
        JavaScript and JSON consumers without integer precision loss.
        """
        return {
            "model_version": "gbm-discrete-v1",
            "seed": str(self._seed),
            "start_timestamp": self._start_timestamp,
            "step_seconds": self._step_seconds,
            "drift": self._drift,
            "volatility": self._volatility,
            "volume_noise": self._volume_noise,
        }

    @staticmethod
    def _validate_timestamp(value) -> float:
        timestamp = nonnegative_value(value)
        try:
            datetime.fromtimestamp(timestamp, timezone.utc)
        except (OverflowError, OSError, ValueError):
            raise MarketValueError() from None
        return timestamp

    def _next_timestamp(self) -> float:
        try:
            timestamp = self._validate_timestamp(
                self._start_timestamp + (self._frame_number + 1) * self._step_seconds
            )
        except OverflowError:
            raise MarketValueError() from None
        if (timestamp <= self._current_timestamp or
                datetime.fromtimestamp(timestamp, timezone.utc) <=
                datetime.fromtimestamp(self._current_timestamp, timezone.utc)):
            raise MarketValueError()
        return timestamp

    @staticmethod
    def _advance_price(price: float, log_return: float) -> float:
        """Apply an exponential return without requiring its factor to fit.

        The ordinary path preserves an exact zero return. The fallback handles
        an overflowing/underflowing factor when the final price can still fit.
        Subnormal factors also use the fallback to avoid magnifying their lost
        relative precision when multiplied by a large, normal price.
        A final zero, infinity, or NaN is an error, never a price clamp.
        """
        try:
            factor = math.exp(log_return)
            result = price * factor
        except OverflowError:
            factor = math.inf
            result = math.inf
        if factor >= sys.float_info.min and math.isfinite(result) and result > 0:
            return result
        try:
            return positive_price(math.exp(math.fsum((math.log(price), log_return))))
        except OverflowError:
            raise MarketValueError() from None

    def _step(self, state: AssetState, rng: random.Random) -> tuple[AssetState, float]:
        """Compute a candidate state using only a staged private RNG."""
        price = positive_price(state.current_price)
        base_volume = nonnegative_value(state.base_volume)
        drift = finite_number(state.drift)
        volatility = nonnegative_value(state.volatility)
        variance = finite_number(volatility * volatility)
        try:
            log_return = finite_number(math.fsum((
                drift, -0.5 * variance, finite_number(volatility * rng.gauss(0, 1)),
            )))
        except OverflowError:
            raise MarketValueError() from None
        next_price = self._advance_price(price, log_return)
        # This bounded linear volume multiplier is synthetic, not a model of
        # executable liquidity. Validate before clamping so NaN/inf cannot hide.
        volume_multiplier = max(0.1, finite_number(
            1.0 + rng.gauss(0, self._volume_noise)
        ))
        volume = nonnegative_value(base_volume * volume_multiplier)
        return AssetState(next_price, base_volume, drift, volatility, state.tick_count + 1), volume

    async def get_tick(self, asset: str) -> MarketTick:
        return (await self.get_ticks([asset]))[asset]

    async def get_ticks(self, assets: list[str]) -> dict[str, MarketTick]:
        if not isinstance(assets, (list, tuple)):
            raise MarketValueError()
        requested = {}
        for asset in assets:
            if not isinstance(asset, str) or asset not in self._assets:
                raise MarketValueError()
            requested[asset] = None
        if not requested:
            return {}

        timestamp = self._next_timestamp()
        next_assets = {}
        next_rngs = {}
        ticks = {}
        for asset, state in self._assets.items():
            rng = random.Random(0)
            rng.setstate(self._rngs[asset].getstate())
            next_state, volume = self._step(state, rng)
            next_assets[asset] = next_state
            next_rngs[asset] = rng
            ticks[asset] = MarketTick(asset, next_state.current_price, volume, timestamp)

        # No await or mutation precedes this commit. A bad asset, clock, or draw
        # leaves every price, RNG (including its Gaussian cache), and time intact.
        self._assets = next_assets
        self._rngs = next_rngs
        self._current_timestamp = timestamp
        self._frame_number += 1
        return {asset: ticks[asset] for asset in requested}

    def get_current_price(self, asset: str) -> float:
        """Read the last modeled price without advancing the market clock."""
        if not isinstance(asset, str) or asset not in self._assets:
            raise MarketValueError()
        return positive_price(self._assets[asset].current_price)
