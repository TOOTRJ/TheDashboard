"""Offline playback of a validated, immutable synthetic fixture.

This is deliberately not a paper feed. Recorded provider observations require
a separate replay clock/freshness contract before they can drive decisions.
Every nonempty quote request advances one whole frame; candle reads expose
only previously delivered frames and never advance modeled time.
"""

from __future__ import annotations

from os import PathLike

from .candles import MinuteCandle
from .dataset import DatasetError, load_dataset
from .feed import MarketFeed, MarketFeedError, MarketTick


class ReplayFeed(MarketFeed):
    """A fresh cursor over one locally validated synthetic dataset directory."""

    simulation_only = True

    def __init__(self, path: str | PathLike[str]):
        self._dataset = load_dataset(path)
        metadata = self._dataset.manifest["metadata"]
        if metadata["source_kind"] != "synthetic_fixture":
            raise DatasetError("provider_replay_unsupported")
        if (metadata["warmup_minutes"] != 0 or
                metadata["evaluation_start_at"] != metadata["simulation_spec"]["start_timestamp"] or
                metadata["evaluation_end_at"] != self._dataset.frames[-1]["observed_at"]):
            raise DatasetError("replay_window_unsupported")
        self._assets = tuple(item["asset"] for item in metadata["assets"])
        self._frame_index = -1
        self._current_timestamp = metadata["simulation_spec"]["start_timestamp"]
        self._candle_cursors = {asset: 0 for asset in self._assets}
        self._candles = {asset: [] for asset in self._assets}
        seen = {asset: set() for asset in self._assets}
        for index, frame in enumerate(self._dataset.frames):
            for row in frame["candles"]:
                asset = row["asset"]
                # The codec has already rejected conflicting duplicate values
                # or availability times. Deliver each canonical minute once.
                if row["start"] not in seen[asset]:
                    seen[asset].add(row["start"])
                    candle = MinuteCandle(**{
                        key: value for key, value in row.items() if key != "available_at"
                    })
                    self._candles[asset].append((index, candle))

    @property
    def current_timestamp(self) -> float:
        return self._current_timestamp

    @property
    def simulation_spec(self) -> dict:
        return dict(self._dataset.manifest["metadata"]["simulation_spec"])

    @property
    def dataset_spec(self) -> dict:
        """JSON-safe identity for run ledgers; no local path or raw records."""
        metadata = self._dataset.manifest["metadata"]
        return {
            "dataset_id": self._dataset.dataset_id,
            "schema_version": self._dataset.manifest["schema_version"],
            "frames_sha256": self._dataset.manifest["frames"]["sha256"],
            "frame_count": len(self._dataset.frames),
            "source_kind": metadata["source_kind"],
            "quote_currency": metadata["quote_currency"],
            "volume_unit": metadata["volume_unit"],
            "availability_semantics": metadata["availability_semantics"],
            "valuation_policy": metadata["valuation_policy"],
            "playback_policy": "synthetic-whole-frame-once-v1",
        }

    def _requested(self, assets: list[str]) -> tuple[str, ...]:
        if not isinstance(assets, (list, tuple)) or any(
            not isinstance(asset, str) or asset not in self._assets for asset in assets
        ):
            raise MarketFeedError("unsupported_asset")
        return tuple(dict.fromkeys(assets))

    async def get_tick(self, asset: str) -> MarketTick:
        return (await self.get_ticks([asset]))[asset]

    async def get_ticks(self, assets: list[str]) -> dict[str, MarketTick]:
        requested = self._requested(assets)
        if not requested:
            return {}
        index = self._frame_index + 1
        if index >= len(self._dataset.frames):
            raise MarketFeedError("dataset_exhausted")
        frame = self._dataset.frames[index]
        result = {
            row["asset"]: MarketTick(row["asset"], row["price"], row["volume"], row["source_time"])
            for row in frame["quotes"] if row["asset"] in requested
        }
        requested_ticks = {asset: result[asset] for asset in requested}
        self._frame_index = index
        self._current_timestamp = frame["observed_at"]
        # Reconstruct mutable ticks for each call; callers cannot alter the
        # validated immutable dataset or another playback cursor's result.
        return requested_ticks

    async def get_candles(self, assets: list[str], *, warmup: bool = False) -> list[MinuteCandle]:
        requested = self._requested(assets)
        result = []
        for asset in requested:
            rows = self._candles[asset]
            cursor = self._candle_cursors[asset]
            while cursor < len(rows) and rows[cursor][0] <= self._frame_index:
                result.append(rows[cursor][1])
                cursor += 1
            self._candle_cursors[asset] = cursor
        return result
