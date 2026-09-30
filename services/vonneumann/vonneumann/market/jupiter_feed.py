"""
Live market feed using the Jupiter API.

Uses Jupiter Price API v3 for Solana token prices, batching requested assets.
Provider failures stop execution; only source-validated complete batches are cached.

Jupiter is also the swap provider for live trading (Phase 6), so using it
for prices keeps the entire pipeline on one provider.

Completed indicator candles use the separate Birdeye V3 history adapter.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from typing import Optional

import aiohttp

from .birdeye_candles import BirdeyeCandles
from .candles import MinuteCandle
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

    def __init__(self, api_key: str = "", *, rpc_url: str | None = None,
                 birdeye_api_key: str | None = None):
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

        # Configuration is enforced on candle access so quote-only callers can
        # still validate Jupiter/RPC independently. This owns a separate session.
        self._candles = BirdeyeCandles(
            BIRDEYE_API_KEY if birdeye_api_key is None else birdeye_api_key, TOKEN_MINTS)

        # Cache: asset -> (monotonic receipt time, source-validated MarketTick)
        self._cache: dict[str, tuple[float, MarketTick]] = {}
        self._cache_ttl = 0.8  # seconds — slightly under 1s tick

        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5),
                trust_env=False,
            )
        return self._session

    async def close(self) -> None:
        try:
            if self._session and not self._session.closed:
                await self._session.close()
        finally:
            await self._candles.close()

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
                    # Jupiter does not supply volume. Indicator volume comes only
                    # from completed source candles, never repeated quote polls.
                    volume=0.0, timestamp=stamp,
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

    async def get_candles(self, assets: list[str], *, warmup: bool = False) -> list[MinuteCandle]:
        """Fetch completed source minutes for the shared indicator history."""
        return await self._candles.get_candles(assets, warmup=warmup)

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
