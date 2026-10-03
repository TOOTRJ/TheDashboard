"""Completed, unpadded Birdeye V3 minutes for paper-mode indicators.

Completion, continuity and retry bounds below are local safety policies, not
provider guarantees. Historical observations never substitute for live quotes.
"""

from __future__ import annotations

import asyncio
import math
import hashlib
import json
import time
from collections.abc import Mapping

import aiohttp

from .candles import MINUTE_RETENTION, MinuteCandle
from .feed import MarketFeedError
from .provider_evidence import ProviderDocument, bounded_response_body
from .exact_records import ExactCandleRecord, ExactRecordError, parse_candle_records

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
        self._exact_cache: dict[str, tuple[ExactCandleRecord, ...]] = {}
        # Keep only compact exact fingerprints across request-window changes.
        # Retaining every old response document would grow without bound.
        self._accepted_fingerprints: dict[str, dict[int, str]] = {}
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
        return await self._get_candles(assets, warmup=warmup, exact=False)

    async def get_exact_candles(self, assets: list[str], *, warmup: bool = False):
        """Immutable raw-unit source records; no implicit execution-grid rounding."""
        return await self._get_candles(assets, warmup=warmup, exact=True)

    async def _get_candles(self, assets: list[str], *, warmup: bool, exact: bool):
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
                    views = await self._fetch_locked(requested, cutoff=cutoff, warmup=warmup)
                    return ([row for asset in requested for row in self._exact_cache[asset]]
                            if exact else views)
        except MarketFeedError:
            raise
        except (ValueError, TypeError, OverflowError):
            raise MarketFeedError("candles_invalid") from None
        except Exception:
            # Provider exceptions can contain the authenticated URL or headers.
            raise MarketFeedError("candles_unavailable") from None

    async def _fetch_locked(self, assets: list[str], *, cutoff: int, warmup: bool) -> list[MinuteCandle]:
        pending: dict[str, tuple[MinuteCandle, ...]] = {}
        exact_pending: dict[str, tuple[ExactCandleRecord, ...]] = {}
        fingerprint_pending: dict[str, dict[int, str]] = {}
        request_count = 0
        for asset in assets:
            previous = self._cutoffs.get(asset)
            if previous is not None and cutoff < previous:
                raise MarketFeedError("candles_clock_invalid")
            covered_warmup = (previous == cutoff and self._exact_cache[asset][0].document.parameters[
                "time_from"] <= cutoff - WARMUP_MINUTES * 60)
            if previous == cutoff and (not warmup or covered_warmup):
                pending[asset] = self._cache[asset]
                exact_pending[asset] = self._exact_cache[asset]
                fingerprint_pending[asset] = self._accepted_fingerprints[asset]
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
            parameters = {
                "address": self._token_mints[asset], "type": "1m", "mode": "range",
                "time_from": start, "time_to": cutoff, "currency": "usd",
                "chart_type": "price", "ui_amount_mode": "raw", "padding": "false",
            }
            async with session.get(
                BIRDEYE_CANDLES_URL,
                params=parameters,
                headers={"X-API-KEY": self._api_key, "x-chain": "solana", "Accept": "application/json"},
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    code = "candles_rate_limited" if response.status == 429 else "candles_unavailable"
                    raise MarketFeedError(code)
                raw = await bounded_response_body(response, provider=CANDLE_SOURCE)
                received_at, received_mono = time.time(), time.monotonic()
                if received_at < cutoff + COMPLETION_MARGIN_SECONDS:
                    raise MarketFeedError("candles_clock_invalid")
                document = ProviderDocument.capture(CANDLE_SOURCE, parameters, raw,
                                                    received_at, received_mono)
            rows = self._parse(document, asset=asset, start=start, cutoff=cutoff, initial=initial)
            # Compare exact accepted history before float views can hide a
            # revision, including explicit warmup after narrower refreshes.
            fingerprints = dict(self._accepted_fingerprints.get(asset, {}))
            fields = ("open", "high", "low", "close", "volume", "volume_usd",
                      "is_scaled_ui_token", "multiplier")
            for row in rows:
                identity = [getattr(row, key) for key in fields]
                fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=True,
                    separators=(",", ":"), allow_nan=False).encode("ascii")).hexdigest()
                old = fingerprints.get(row.start)
                if old is not None and old != fingerprint:
                    raise MarketFeedError("candles_revision")
                fingerprints[row.start] = fingerprint
            fingerprint_pending[asset] = {stamp: fingerprints[stamp]
                for stamp in sorted(fingerprints)[-MINUTE_RETENTION:]}
            exact_pending[asset] = rows
            pending[asset] = tuple(MinuteCandle(
                asset=row.asset, start=row.start, open=float(row.open), high=float(row.high),
                low=float(row.low), close=float(row.close), volume=float(row.volume),
                source=CANDLE_SOURCE, quote_currency="USD", volume_unit="base_token") for row in rows)
        self._accepted_fingerprints.update(fingerprint_pending)
        self._exact_cache.update(exact_pending)
        self._cache.update(pending)
        self._cutoffs.update({asset: cutoff for asset in assets})
        self._first_starts.update({asset: min(self._first_starts.get(asset, rows[0].start), rows[0].start)
                                   for asset, rows in pending.items()})
        return [candle for asset in assets for candle in pending[asset]]

    def _parse(self, document: ProviderDocument, *, asset: str, start: int, cutoff: int,
               initial: bool) -> tuple[ExactCandleRecord, ...]:
        try:
            candles = parse_candle_records(document, asset=asset, mint=self._token_mints[asset])
        except ExactRecordError as error:
            raise MarketFeedError(error.code) from None
        if not candles:
            raise MarketFeedError("candles_missing")
        if ((not initial and candles[0].start != start) or candles[-1].end != cutoff
                or any(right.start != left.start + 60 for left, right in zip(candles, candles[1:]))):
            raise MarketFeedError("candles_gap")
        return candles
