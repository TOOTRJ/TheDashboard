"""
Simulation market feed -- geometric Brownian motion price generator.

Produces realistic-looking price series with configurable drift and volatility.
Maintains price/volume history for each asset. No external dependencies.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

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
    drift: float = 0.0001  # slight upward bias
    volatility: float = 0.02  # 2% per tick std dev
    tick_count: int = 0


class SimulationFeed(MarketFeed):
    """
    Geometric Brownian motion market feed for simulation mode.
    Each call to get_tick advances the price by one step.
    """

    def __init__(
        self,
        drift: float = 0.0001,
        volatility: float = 0.02,
        volume_noise: float = 0.5,
    ):
        self._assets: dict[str, AssetState] = {}
        self._drift = drift
        self._volatility = volatility
        self._volume_noise = volume_noise

        # Initialize all assets
        for asset, price in BASE_PRICES.items():
            self._assets[asset] = AssetState(
                current_price=price,
                base_volume=BASE_VOLUMES.get(asset, 100_000),
                drift=drift,
                volatility=volatility,
            )

    def _step(self, state: AssetState) -> tuple[float, float]:
        """Advance price by one GBM step. Returns (price, volume)."""
        # GBM: dS = S * (mu*dt + sigma*dW)
        dw = random.gauss(0, 1)
        returns = state.drift + state.volatility * dw
        state.current_price *= 1 + returns
        state.current_price = max(state.current_price * 0.001, state.current_price)
        state.tick_count += 1

        # Volume: base * random multiplier (log-normal-ish)
        vol_mult = max(0.1, 1.0 + random.gauss(0, self._volume_noise))
        volume = state.base_volume * vol_mult

        return state.current_price, volume

    async def get_tick(self, asset: str) -> MarketTick:
        if asset not in self._assets:
            raise ValueError(f"Unknown asset: {asset}")
        state = self._assets[asset]
        price, volume = self._step(state)
        return MarketTick(
            asset=asset,
            price=price,
            volume=volume,
            timestamp=time.time(),
        )

    async def get_ticks(self, assets: list[str]) -> dict[str, MarketTick]:
        result = {}
        for asset in assets:
            result[asset] = await self.get_tick(asset)
        return result

    def get_current_price(self, asset: str) -> float:
        """Synchronous price read without advancing. Used for SL/TP checks."""
        if asset in self._assets:
            return self._assets[asset].current_price
        return 0.0
