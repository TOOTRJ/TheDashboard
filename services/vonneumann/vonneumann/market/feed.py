"""Abstract market feed interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class QuoteEvidence:
    """Source provenance for a paper quote; never a candle or execution promise."""

    source_slot: int
    received_at: float
    received_monotonic: float
    provider: str = "jupiter-price-v3"
    quote_currency: str = "USD"
    source_age_at_receipt: float | None = None  # Monotonic age floor carried across refreshes.


@dataclass
class MarketTick:
    """A single price/volume tick for an asset."""

    asset: str
    price: float
    volume: float
    timestamp: float  # Modeled simulation time, or estimated source block time for paper quotes.
    evidence: QuoteEvidence | None = None


class MarketFeedError(RuntimeError):
    """Safe error with current valid observations available for a final risk pass."""

    def __init__(self, code: str, *, valid_ticks: dict[str, MarketTick] | None = None):
        self.code = code
        self.valid_ticks = dict(valid_ticks or {})
        super().__init__("Market data refresh failed. Execution requires valid provider data.")


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

    async def get_candles(self, assets: list[str], *, warmup: bool = False) -> list:
        """Return completed canonical minutes without advancing the quote clock.

        Feeds must implement this explicitly; price polls cannot stand in for
        completed candles or their volume.
        """
        raise MarketFeedError("candles_unavailable")
