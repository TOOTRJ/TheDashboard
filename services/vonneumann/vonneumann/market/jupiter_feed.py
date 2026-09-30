"""
Live market feed using the Jupiter API.

Uses Jupiter Price API v3 for Solana token prices, batching requested assets.
Provider failures stop execution; only source-validated complete batches are cached.

Jupiter is also the swap provider for live trading (Phase 6), so using it
for prices keeps the entire pipeline on one provider.

Backfill uses Birdeye OHLCV since Jupiter doesn't have a candle history endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from typing import Optional

import aiohttp

from .feed import MarketFeed, MarketFeedError, MarketTick, QuoteEvidence
from .quote_freshness import quote_source_age, source_slot, validate_quote
from .solana_time import SolanaTimeResolver

logger = logging.getLogger(__name__)

JUPITER_API_URL = "https://api.jup.ag"
JUP_API_KEY = os.environ.get("JUP_API_KEY", "")
BIRDEYE_API_KEY = os.environ.get("BIRDEYE_API_KEY", "")

# Token mint addresses on Solana mainnet
TOKEN_MINTS: dict[str, str] = {
    "SOL/USDC": "So11111111111111111111111111111111111111112",
    "JUP/USDC": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "BONK/USDC": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "WIF/USDC": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "JTO/USDC": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
    "PYTH/USDC": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "ORCA/USDC": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "RAY/USDC": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
}

# Reverse lookup: mint address -> asset pair
MINT_TO_ASSET: dict[str, str] = {v: k for k, v in TOKEN_MINTS.items()}

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def _number(value, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Invalid market value")
    value = float(value)
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise ValueError("Invalid market value")
    return value


class JupiterFeed(MarketFeed):
    """
    Live market feed using Jupiter Price API v3.
    Fetches requested token prices in one request per tick.
    Tick rates must respect the configured provider account's actual quota.
    """

    def __init__(self, api_key: str = "", *, rpc_url: str | None = None):
        self._api_key = api_key or JUP_API_KEY
        if not self._api_key:
            raise ValueError("JUP_API_KEY is required for paper trading mode")

        self._source_time = SolanaTimeResolver(
            os.environ.get("VN_SOLANA_RPC_URL", "") if rpc_url is None else rpc_url
        )
        self._source_slots: dict[str, int] = {}
        self._price_lock = asyncio.Lock()

        self._jup_headers = {
            "x-api-key": self._api_key,
            "Accept": "application/json",
        }

        # API call counter (exposed to Genesis for tracking)
        self.api_call_count: int = 0

        # Birdeye headers for OHLCV backfill
        self._birdeye_key = BIRDEYE_API_KEY
        self._birdeye_headers = {
            "X-API-KEY": self._birdeye_key,
            "x-chain": "solana",
            "User-Agent": "VonNeumann/1.0",
            "Accept": "application/json",
        } if self._birdeye_key else {}

        # Cache: asset -> (monotonic receipt time, source-validated MarketTick)
        self._cache: dict[str, tuple[float, MarketTick]] = {}
        self._cache_ttl = 0.8  # seconds — slightly under 1s tick

        # Volume cache — Jupiter price API doesn't include volume, so we
        # refresh from Birdeye OHLCV on a slow schedule and merge the last
        # known volume into each tick. Without this, the `volume_threshold`
        # signal gene is silently neutralized after ~20 live ticks.
        self._volume_cache: dict[str, float] = {}
        self._last_volume_refresh: float = 0.0
        self._volume_refresh_interval: float = 60.0  # seconds

        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5),
                trust_env=False,
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Price API ────────────────────────────────────────────────────────

    async def _fetch_all_prices(self, assets: Optional[list[str]] = None) -> dict[str, MarketTick]:
        """Bound the complete price/source lookup; never refresh a source timestamp.

        A failed batch carries only currently validated siblings for a final risk
        pass. Neither its quote cache nor its slot watermarks are committed.
        """
        requested = list(dict.fromkeys(TOKEN_MINTS if assets is None else assets))
        if any(asset not in TOKEN_MINTS for asset in requested):
            raise MarketFeedError("unsupported_asset")
        if not requested:
            return {}
        try:
            async with asyncio.timeout(5) as deadline:
                async with self._price_lock:
                    return await self._fetch_prices_locked(requested, deadline=deadline.when())
        except MarketFeedError:
            raise
        except (ValueError, TypeError, OverflowError):
            raise MarketFeedError("price_invalid") from None
        except Exception:
            raise MarketFeedError("price_unavailable") from None

    async def _fetch_prices_locked(self, requested: list[str], *, deadline: float) -> dict[str, MarketTick]:
        mono, wall = time.monotonic(), time.time()
        cached = {}
        for asset in requested:
            entry = self._cache.get(asset)
            if entry is None or not 0 <= mono - entry[0] < self._cache_ttl:
                break
            try:
                validate_quote(entry[1], previous_slot=self._source_slots.get(asset),
                               wall_now=wall, monotonic_now=mono)
            except MarketFeedError:
                break
            cached[asset] = entry[1]
        if len(cached) == len(requested):
            return cached

        session = await self._get_session()
        self.api_call_count += 1
        async with session.get(
            f"{JUPITER_API_URL}/price/v3",
            params={"ids": ",".join(TOKEN_MINTS[asset] for asset in requested)},
            headers=self._jup_headers,
            allow_redirects=False,
        ) as resp:
            if resp.status != 200:
                raise MarketFeedError("price_rate_limited" if resp.status == 429 else "price_unavailable")
            data = await resp.json()
            # Record receipt before RPC work. RPC latency consumes freshness.
            received_at, received_mono = time.time(), time.monotonic()
            if not isinstance(data, dict):
                raise MarketFeedError("price_invalid")

        candidates, errors = {}, {}
        for asset in requested:
            info = data.get(TOKEN_MINTS[asset])
            if not isinstance(info, dict):
                errors[asset] = MarketFeedError("price_missing")
                continue
            try:
                price = _number(info.get("usdPrice"), positive=True)
                slot = source_slot(info.get("blockId"))
                candidates[asset] = (price, slot)
            except MarketFeedError as error:
                errors[asset] = error
            except (ValueError, TypeError, OverflowError):
                errors[asset] = MarketFeedError("price_invalid")

        times, time_errors = await self._source_time.resolve(
            session, [slot for _, slot in candidates.values()], deadline=deadline)
        result = {}
        # One final shared time boundary prevents earlier-resolved slots from
        # appearing fresh after a slow sibling lookup.
        wall, mono = time.time(), time.monotonic()
        for asset, (price, slot) in candidates.items():
            if slot in time_errors:
                errors[asset] = time_errors[slot]
                continue
            try:
                stamp = times[slot]
                age_floor = max(0.0, received_at - stamp)
                previous = self._cache.get(asset)
                if previous is not None:
                    previous_tick = previous[1]
                    if (previous_tick.evidence.source_slot == slot
                            and previous_tick.timestamp != stamp):
                        raise MarketFeedError("source_time_invalid")
                    previous_age = quote_source_age(
                        previous_tick, wall_now=received_at, monotonic_now=received_mono)
                    age_floor = max(age_floor, previous_age - (stamp - previous_tick.timestamp))
                tick = MarketTick(
                    asset=asset, price=price,
                    volume=_number(self._volume_cache.get(asset, 0.0), positive=False), timestamp=stamp,
                    evidence=QuoteEvidence(slot, received_at, received_mono,
                                           source_age_at_receipt=age_floor),
                )
                validate_quote(tick, previous_slot=self._source_slots.get(asset),
                               wall_now=wall, monotonic_now=mono)
                result[asset] = tick
            except MarketFeedError as error:
                errors[asset] = error
            except (ValueError, TypeError, OverflowError):
                errors[asset] = MarketFeedError("price_invalid")
        if errors:
            first = next(errors[asset] for asset in requested if asset in errors)
            raise MarketFeedError(first.code, valid_ticks=result)
        self._cache.update({asset: (received_mono, tick) for asset, tick in result.items()})
        self._source_slots.update({asset: tick.evidence.source_slot for asset, tick in result.items()})
        return result

    async def get_tick(self, asset: str) -> MarketTick:
        """Get a validated price or an explicit provider failure, never a zero fallback."""
        return (await self._fetch_all_prices([asset]))[asset]

    async def get_ticks(self, assets: list[str]) -> dict[str, MarketTick]:
        """Get prices for multiple assets — single API call."""
        return await self._fetch_all_prices(assets)

    # ── Volume refresh (via Birdeye) ─────────────────────────────────────
    # Jupiter's price API doesn't return volume. We keep a small per-asset
    # cache that we refresh from Birdeye 1-minute OHLCV on a slow schedule
    # so the `volume_threshold` signal gene has real data to work with.

    async def refresh_volumes(self, assets: Optional[list[str]] = None) -> None:
        """Refresh cached volumes from Birdeye. Rate-limited internally — safe to call every tick."""
        if not self._birdeye_key:
            return

        now = time.time()
        if now - self._last_volume_refresh < self._volume_refresh_interval:
            return
        target_assets = list(dict.fromkeys(TOKEN_MINTS if assets is None else assets))
        if any(asset not in TOKEN_MINTS for asset in target_assets):
            raise MarketFeedError("unsupported_asset")
        pending = {}
        try:
            session = await self._get_session()
            for asset in target_assets:
                async with session.get(
                    "https://public-api.birdeye.so/defi/ohlcv",
                    params={
                        "address": TOKEN_MINTS[asset],
                        "type": "1m",
                        "time_from": int(now) - 180,
                        "time_to": int(now),
                    },
                    headers=self._birdeye_headers,
                    allow_redirects=False,
                ) as resp:
                    if resp.status != 200:
                        raise MarketFeedError("volume_unavailable")
                    data = await resp.json()
                    if not isinstance(data, dict) or data.get("success") is False:
                        raise MarketFeedError("volume_invalid")
                    body = data.get("data")
                    items = body.get("items") if isinstance(body, dict) else None
                    if not isinstance(items, list):
                        raise MarketFeedError("volume_invalid")
                    if items:
                        if not isinstance(items[-1], dict):
                            raise MarketFeedError("volume_invalid")
                        pending[asset] = _number(items[-1].get("v"), positive=False)
                    # Empty history remains optional; candle freshness policy is separate.
                await asyncio.sleep(0.75)  # Birdeye rate limit
            self._volume_cache.update(pending)
            self._last_volume_refresh = now
        except MarketFeedError:
            raise
        except (ValueError, TypeError, OverflowError):
            raise MarketFeedError("volume_invalid") from None
        except Exception:
            raise MarketFeedError("volume_unavailable") from None

    # ── OHLCV Backfill (via Birdeye) ─────────────────────────────────────
    # Jupiter doesn't have a candle history endpoint, so we use Birdeye
    # for the initial backfill to warm up probe RSI/EMA buffers.

    async def backfill(
        self,
        asset: str,
        timeframe_minutes: int = 15,
        limit: int = 100,
    ) -> list[dict]:
        """Fetch OHLCV history from Birdeye for signal warmup."""
        if not self._birdeye_key:
            logger.warning("[Jupiter] No BIRDEYE_API_KEY — skipping backfill")
            return []

        mint = TOKEN_MINTS.get(asset)
        if not mint:
            return []

        session = await self._get_session()
        interval_map = {1: "1m", 3: "3m", 5: "5m", 15: "15m", 30: "30m", 60: "1H"}
        interval = interval_map.get(timeframe_minutes, "15m")

        now = int(time.time())
        time_from = now - (limit * timeframe_minutes * 60)

        try:
            async with session.get(
                "https://public-api.birdeye.so/defi/ohlcv",
                params={
                    "address": mint,
                    "type": interval,
                    "time_from": time_from,
                    "time_to": now,
                },
                headers=self._birdeye_headers,
                allow_redirects=False,
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[Jupiter] Birdeye OHLCV HTTP {resp.status} for {asset}")
                    return []

                data = await resp.json()
                items = data.get("data", {}).get("items", [])

                candles = [
                    {
                        "price": float(c["c"]),
                        "volume": float(c["v"]),
                        "timestamp": c.get("unixTime", 0),
                    }
                    for c in items
                ]
                logger.info(f"[Jupiter] Backfilled {len(candles)} candles for {asset}")
                return candles

        except Exception:
            logger.warning("[Jupiter] Optional history unavailable")
            return []

    async def backfill_probe(
        self,
        assets: list[str],
        timeframe_minutes: int = 15,
        limit: int = 100,
    ) -> dict[str, list[dict]]:
        """Backfill multiple assets with rate-limited Birdeye calls."""
        result: dict[str, list[dict]] = {}
        for asset in assets:
            result[asset] = await self.backfill(asset, timeframe_minutes, limit)
            await asyncio.sleep(0.75)  # Birdeye rate limit
        return result

    # ── Swap Quoting (for future live trading) ───────────────────────────

    async def get_swap_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_lamports: int,
        slippage_bps: int = 100,
    ) -> Optional[dict]:
        """
        Get a swap quote from Jupiter. Used for live trading (Phase 6).
        Returns the full quote response needed to execute a swap.
        """
        session = await self._get_session()
        self.api_call_count += 1
        try:
            async with session.get(
                f"{JUPITER_API_URL}/swap/v1/quote",
                params={
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "amount": str(amount_lamports),
                    "slippageBps": str(slippage_bps),
                },
                headers=self._jup_headers,
                allow_redirects=False,
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[Jupiter] Quote API HTTP {resp.status}")
                    return None
                return await resp.json()

        except Exception:
            logger.warning("[Jupiter] Quote unavailable")
            return None
