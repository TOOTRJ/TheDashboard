"""Abstract market feed interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MarketTick:
    """A single price/volume tick for an asset."""

    asset: str
    price: float
    volume: float
    timestamp: float  # Unix seconds


class MarketFeed(ABC):
    """Protocol for all market data sources."""

    @abstractmethod
    async def get_tick(self, asset: str) -> MarketTick:
        """Return the latest price tick for the given asset."""
        ...

    @abstractmethod
    async def get_ticks(self, assets: list[str]) -> dict[str, MarketTick]:
        """Return latest ticks for multiple assets at once."""
        ...
