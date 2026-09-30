"""Completed, unpadded Birdeye V3 minutes for paper-mode indicators.

Completion, continuity and retry bounds below are local safety policies, not
provider guarantees. Historical observations never substitute for live quotes.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Mapping

import aiohttp

from .candles import MinuteCandle
from .feed import MarketFeedError

BIRDEYE_CANDLES_URL = "https://public-api.birdeye.so/defi/v3/ohlcv"
CANDLE_SOURCE = "birdeye-ohlcv-v3"
COMPLETION_MARGIN_SECONDS = 5
WARMUP_MINUTES = 3660
OVERLAP_MINUTES = 2
MAX_PROVIDER_RECORDS = 5000
MAX_ASSETS = 8
BATCH_TIMEOUT_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 5
# This process-local pacing does not account for other clients sharing a key.
REQUEST_SPACING_SECONDS = 1


def _number(value: object, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MarketFeedError("candles_invalid")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise MarketFeedError("candles_invalid") from None
    if not math.isfinite(number) or (number <= 0 if positive else number < 0):
        raise MarketFeedError("candles_invalid")
    return number


class BirdeyeCandles:
    """One bounded shared history request per asset and completed-minute cutoff.

The first request (or explicit warmup) covers 3660 minutes. Later requests
overlap the previous successful cutoff by two minutes. No partial batch advances
the request watermarks; a retry must still cover the unavailable interval.
"""

    def __init__(self, api_key: str, token_mints: Mapping[str, str]):
        self._api_key = api_key
        self._token_mints = dict(token_mints)
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self._cutoffs: dict[str, int] = {}
        self._first_starts: dict[str, int] = {}
        self._cache: dict[str, tuple[MinuteCandle, ...]] = {}
        self.api_call_count = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
                trust_env=False,
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def get_candles(self, assets: list[str], *, warmup: bool = False) -> list[MinuteCandle]:
        """Return validated completed minutes, or fail without stale fallback."""
        requested = list(dict.fromkeys(assets))
        if any(asset not in self._token_mints for asset in requested):
            raise MarketFeedError("unsupported_asset")
        if len(requested) > MAX_ASSETS:
            raise MarketFeedError("candles_batch_limit")
        if not requested:
            return []
        if not isinstance(self._api_key, str) or not self._api_key.strip():
            raise MarketFeedError("candles_configuration")
        try:
            now = _number(time.time(), positive=True)
            cutoff = math.floor((now - COMPLETION_MARGIN_SECONDS) / 60) * 60
            if cutoff < WARMUP_MINUTES * 60:
                raise MarketFeedError("candles_clock_invalid")
            async with asyncio.timeout(BATCH_TIMEOUT_SECONDS):
                async with self._lock:
                    return await self._fetch_locked(requested, cutoff=cutoff, warmup=warmup)
        except MarketFeedError:
            raise
        except (ValueError, TypeError, OverflowError):
            raise MarketFeedError("candles_invalid") from None
        except Exception:
            # Provider exceptions can contain the authenticated URL or headers.
            raise MarketFeedError("candles_unavailable") from None

    async def _fetch_locked(self, assets: list[str], *, cutoff: int, warmup: bool) -> list[MinuteCandle]:
        pending: dict[str, tuple[MinuteCandle, ...]] = {}
        request_count = 0
        for asset in assets:
            previous = self._cutoffs.get(asset)
            if previous is not None and cutoff < previous:
                raise MarketFeedError("candles_clock_invalid")
            if previous == cutoff:
                pending[asset] = self._cache[asset]
                continue
            initial = previous is None or warmup
            start = (cutoff - WARMUP_MINUTES * 60 if initial else
                     max(previous - OVERLAP_MINUTES * 60, self._first_starts[asset]))
            # Leave room for a provider's inclusive end-boundary candle.
            if (cutoff - start) // 60 + 1 > MAX_PROVIDER_RECORDS:
                raise MarketFeedError("candles_backlog")
            if request_count:
                await asyncio.sleep(REQUEST_SPACING_SECONDS)
            session = await self._get_session()
            self.api_call_count += 1
            request_count += 1
            async with session.get(
                BIRDEYE_CANDLES_URL,
                params={
                    "address": self._token_mints[asset], "type": "1m", "mode": "range",
                    "time_from": start, "time_to": cutoff, "currency": "usd",
                    "chart_type": "price", "ui_amount_mode": "raw", "padding": "false",
                },
                headers={"X-API-KEY": self._api_key, "x-chain": "solana", "Accept": "application/json"},
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    code = "candles_rate_limited" if response.status == 429 else "candles_unavailable"
                    raise MarketFeedError(code)
                payload = await response.json()
            pending[asset] = self._parse(payload, asset=asset, start=start, cutoff=cutoff, initial=initial)
        self._cache.update(pending)
        self._cutoffs.update({asset: cutoff for asset in assets})
        self._first_starts.update({asset: min(self._first_starts.get(asset, rows[0].start), rows[0].start)
                                   for asset, rows in pending.items()})
        return [candle for asset in assets for candle in pending[asset]]

    def _parse(self, payload: object, *, asset: str, start: int, cutoff: int,
               initial: bool) -> tuple[MinuteCandle, ...]:
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise MarketFeedError("candles_invalid")
        body = payload.get("data")
        if not isinstance(body, dict) or not isinstance(body.get("is_scaled_ui_token"), bool):
            raise MarketFeedError("candles_invalid")
        items = body.get("items")
        if not isinstance(items, list) or len(items) > MAX_PROVIDER_RECORDS:
            raise MarketFeedError("candles_invalid")
        by_start: dict[int, MinuteCandle] = {}
        for row in items:
            if not isinstance(row, dict):
                raise MarketFeedError("candles_invalid")
            stamp = row.get("unix_time")
            if (isinstance(stamp, bool) or not isinstance(stamp, int)
                    or stamp <= 0 or stamp % 60 != 0 or stamp > cutoff):
                raise MarketFeedError("candles_invalid")
            if (row.get("address") != self._token_mints[asset]
                    or row.get("type") != "1m" or row.get("currency") != "usd"):
                raise MarketFeedError("candles_invalid")
            values = {key: _number(row.get(key), positive=True) for key in ("o", "h", "l", "c")}
            volume = _number(row.get("v"), positive=False)
            _number(row.get("v_usd"), positive=False)
            if not values["l"] <= min(values["o"], values["c"]) <= max(values["o"], values["c"]) <= values["h"]:
                raise MarketFeedError("candles_invalid")
            # Validate even an excluded end-boundary row before discarding it.
            if stamp < start or stamp + 60 > cutoff:
                continue
            candle = MinuteCandle(
                asset=asset, start=stamp, open=values["o"], high=values["h"],
                low=values["l"], close=values["c"], volume=volume,
                source=CANDLE_SOURCE, quote_currency="USD", volume_unit="base_token",
            )
            if stamp in by_start and by_start[stamp] != candle:
                raise MarketFeedError("candles_revision")
            by_start[stamp] = candle
        if not by_start:
            raise MarketFeedError("candles_missing")
        candles = tuple(by_start[stamp] for stamp in sorted(by_start))
        if ((not initial and candles[0].start != start) or candles[-1].start + 60 != cutoff
                or any(right.start != left.start + 60 for left, right in zip(candles, candles[1:]))):
            raise MarketFeedError("candles_gap")
        return candles
