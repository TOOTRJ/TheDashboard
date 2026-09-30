"""Validated completed-minute history and shared, run-anchored indicators.

Quotes never enter this store. A source must supply explicit completed minute
candles, including honest synthetic provenance when the market is simulated.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable, Mapping

from .feed import MarketFeedError


MINUTE_RETENTION = 4096
CANDLE_POLICY = {
    "version": "completed-minutes-v1",
    "base_interval_seconds": 60,
    "timeframe_minutes": [1, 60],
    "bucket_anchor": "unix_epoch_utc",
    "gaps": "reject_without_padding",
    "completed_revisions": "reject",
    "leading_partial_bucket": "ignore",
    "ema": "sma_seed_then_recursive",
    "ema_periods": [2, 60],
    "ema_origin": "first_complete_bucket_in_run_history",
    "minute_overlap_retention": MINUTE_RETENTION,
    "close_retention": 64,
    "volume_retention": 21,
}


def _number(value, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MarketFeedError("candle_invalid")
    try:
        result = float(value)
    except OverflowError:
        raise MarketFeedError("candle_invalid") from None
    if not math.isfinite(result) or (result <= 0 if positive else result < 0):
        raise MarketFeedError("candle_invalid")
    return result


def _label(value) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise MarketFeedError("candle_invalid")
    return value


@dataclass(frozen=True)
class MinuteCandle:
    asset: str
    start: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
    quote_currency: str = "USD"
    volume_unit: str = "base_token"

    def __post_init__(self) -> None:
        for name in ("asset", "source", "quote_currency", "volume_unit"):
            _label(getattr(self, name))
        _number(self.start)
        if self.start != int(self.start) or int(self.start) % 60:
            raise MarketFeedError("candle_invalid")
        object.__setattr__(self, "start", int(self.start))
        for name in ("open", "high", "low", "close"):
            object.__setattr__(self, name, _number(getattr(self, name), positive=True))
        object.__setattr__(self, "volume", _number(self.volume))
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise MarketFeedError("candle_invalid")

    @property
    def end(self) -> int:
        return self.start + 60


@dataclass(frozen=True)
class CandleSnapshot:
    asset: str
    timeframe_minutes: int
    start: int
    end: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    closes: tuple[float, ...]
    volumes: tuple[float, ...]
    emas: Mapping[int, float]
    completed_count: int
    source: str
    quote_currency: str
    volume_unit: str

    def __post_init__(self) -> None:
        # Copy as well as freeze: a caller retaining the original dict cannot
        # alter a published snapshot or another probe's indicator values.
        object.__setattr__(self, "closes", tuple(self.closes))
        object.__setattr__(self, "volumes", tuple(self.volumes))
        object.__setattr__(self, "emas", MappingProxyType(dict(self.emas)))


@dataclass
class _Series:
    timeframe: int
    pending: list[MinuteCandle] = field(default_factory=list)
    closes: list[float] = field(default_factory=list)
    volumes: list[float] = field(default_factory=list)
    emas: dict[int, float] = field(default_factory=dict)
    completed_count: int = 0
    snapshot: CandleSnapshot | None = None

    def clone(self) -> _Series:
        return _Series(self.timeframe, list(self.pending), list(self.closes),
                       list(self.volumes), dict(self.emas), self.completed_count, self.snapshot)

    def append(self, candle: MinuteCandle) -> None:
        # A run starting inside a bucket cannot reconstruct its missing prefix.
        if not self.pending and candle.start % (self.timeframe * 60):
            return
        self.pending.append(candle)
        if len(self.pending) < self.timeframe:
            return
        first, last = self.pending[0], self.pending[-1]
        try:
            volume = _number(math.fsum(item.volume for item in self.pending))
        except OverflowError:
            raise MarketFeedError("candle_invalid") from None
        self.completed_count += 1
        self.closes.append(last.close)
        self.volumes.append(volume)
        del self.closes[:-64]
        del self.volumes[:-21]
        for period in range(2, 61):
            if self.completed_count == period:
                # Scaling prevents overflow of a representable mean and avoids
                # dividing tiny samples before summation (which can underflow).
                window = self.closes[-period:]
                scale = max(window)
                ema = scale * (math.fsum(value / scale for value in window) / period)
                self.emas[period] = _number(ema, positive=True)
            elif self.completed_count > period:
                previous = self.emas[period]
                self.emas[period] = _number(
                    previous + (last.close - previous) * (2.0 / (period + 1)), positive=True)
        self.snapshot = CandleSnapshot(
            asset=first.asset, timeframe_minutes=self.timeframe,
            start=first.start, end=last.end, open=first.open,
            high=max(item.high for item in self.pending),
            low=min(item.low for item in self.pending), close=last.close, volume=volume,
            closes=tuple(self.closes), volumes=tuple(self.volumes), emas=self.emas,
            completed_count=self.completed_count, source=first.source,
            quote_currency=first.quote_currency, volume_unit=first.volume_unit,
        )
        self.pending.clear()


@dataclass
class _Asset:
    minutes: OrderedDict[int, MinuteCandle] = field(default_factory=OrderedDict)
    series: dict[int, _Series] = field(default_factory=lambda: {t: _Series(t) for t in range(1, 61)})
    identity: tuple[str, str, str] | None = None

    def clone(self) -> _Asset:
        return _Asset(OrderedDict(self.minutes), {t: s.clone() for t, s in self.series.items()}, self.identity)

    def append(self, candle: MinuteCandle) -> None:
        identity = (candle.source, candle.quote_currency, candle.volume_unit)
        if self.identity is not None and identity != self.identity:
            raise MarketFeedError("candle_source_changed")
        if self.minutes:
            first, last = next(iter(self.minutes)), next(reversed(self.minutes))
            if candle.start < first:
                raise MarketFeedError("candle_history_expired")
            if candle.start <= last:
                if self.minutes.get(candle.start) != candle:
                    raise MarketFeedError("candle_revision")
                return
            if candle.start != last + 60:
                raise MarketFeedError("candle_gap")
        self.identity = identity
        for series in self.series.values():
            series.append(candle)
        self.minutes[candle.start] = candle
        if len(self.minutes) > MINUTE_RETENTION:
            self.minutes.popitem(last=False)


class CandleHistory:
    """Atomically ingest completed minutes; all probes share the same EMA origin.

    History is deliberately append-only. Retained overlap can be replayed
    identically, but neither revisions nor older-than-retention backfill can
    silently change an already used indicator trajectory.
    """

    def __init__(self, assets: Iterable[str]):
        if isinstance(assets, (str, bytes)):
            raise MarketFeedError("candle_invalid")
        try:
            selected = list(assets)
        except TypeError:
            raise MarketFeedError("candle_invalid") from None
        if not selected:
            raise MarketFeedError("candle_invalid")
        for asset in selected:
            _label(asset)
        if len(set(selected)) != len(selected):
            raise MarketFeedError("candle_invalid")
        self._assets = {asset: _Asset() for asset in selected}

    def ingest(self, candles: Iterable[MinuteCandle], *, available_at: float) -> None:
        available = _number(available_at)
        try:
            batch = list(candles)
        except TypeError:
            raise MarketFeedError("candle_invalid") from None
        normalized = []
        for item in batch:
            if not isinstance(item, MinuteCandle):
                raise MarketFeedError("candle_invalid")
            # Revalidate at the store boundary, including objects supplied by
            # adapters, before sorting or altering any staging state.
            candle = MinuteCandle(item.asset, item.start, item.open, item.high,
                                  item.low, item.close, item.volume, item.source,
                                  item.quote_currency, item.volume_unit)
            if candle.asset not in self._assets:
                raise MarketFeedError("candle_invalid")
            if candle.end > available:
                raise MarketFeedError("candle_incomplete")
            normalized.append(candle)
        staged = {asset: self._assets[asset].clone() for asset in {c.asset for c in normalized}}
        for candle in sorted(normalized, key=lambda c: (c.asset, c.start)):
            staged[candle.asset].append(candle)
        # No await or mutation of the live store occurs before this commit.
        self._assets.update(staged)

    def latest(self, asset: str, timeframe: int) -> CandleSnapshot | None:
        if (not isinstance(asset, str) or asset not in self._assets
                or isinstance(timeframe, bool) or not isinstance(timeframe, int)
                or not 1 <= timeframe <= 60):
            raise MarketFeedError("candle_invalid")
        return self._assets[asset].series[timeframe].snapshot

    def last_start(self, asset: str) -> int | None:
        if not isinstance(asset, str) or asset not in self._assets:
            raise MarketFeedError("candle_invalid")
        minutes = self._assets[asset].minutes
        return next(reversed(minutes)) if minutes else None
