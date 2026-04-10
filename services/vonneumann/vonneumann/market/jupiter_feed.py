"""
Live market feed using the Jupiter API.

Uses Jupiter Price API v3 for real-time Solana token prices.
Key advantage: fetches ALL token prices in a single API call (up to 50 mints).
This makes 1-second tick intervals feasible even with many assets.

Jupiter is also the swap provider for live trading (Phase 6), so using it
for prices keeps the entire pipeline on one provider.

Backfill uses Birdeye OHLCV since Jupiter doesn't have a candle history endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

import aiohttp

from .feed import MarketFeed, MarketTick

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


class JupiterFeed(MarketFeed):
    """
    Live market feed using Jupiter Price API v3.
    Fetches all token prices in ONE request per tick.
    Developer plan: 10 RPS — supports 1-second ticks easily.
    """

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or JUP_API_KEY
        if not self._api_key:
            raise ValueError("JUP_API_KEY is required for paper trading mode")

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

        # Cache: asset -> (timestamp, MarketTick)
        self._cache: dict[str, tuple[float, MarketTick]] = {}
        self._cache_ttl = 0.8  # seconds — slightly under 1s tick

        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Price API ────────────────────────────────────────────────────────

    async def _fetch_all_prices(self) -> dict[str, MarketTick]:
        """Fetch all token prices in a single Jupiter API call."""
        now = time.time()

        # Check if entire cache is still fresh
        if self._cache:
            oldest = min(t for t, _ in self._cache.values())
            if now - oldest < self._cache_ttl:
                return {asset: tick for asset, (_, tick) in self._cache.items()}

        mints = ",".join(TOKEN_MINTS.values())
        session = await self._get_session()
        self.api_call_count += 1

        try:
            async with session.get(
                f"{JUPITER_API_URL}/price/v3",
                params={"ids": mints},
                headers=self._jup_headers,
            ) as resp:
                if resp.status == 429:
                    logger.warning("[Jupiter] Rate limited — using cached prices")
                    return {a: t for a, (_, t) in self._cache.items()}

                if resp.status != 200:
                    logger.warning(f"[Jupiter] Price API HTTP {resp.status}")
                    return {a: t for a, (_, t) in self._cache.items()}

                data = await resp.json()

                result: dict[str, MarketTick] = {}
                for mint_addr, price_info in data.items():
                    asset = MINT_TO_ASSET.get(mint_addr)
                    if not asset or price_info is None:
                        continue

                    price = float(price_info.get("usdPrice", 0))
                    if price <= 0:
                        continue

                    tick = MarketTick(
                        asset=asset,
                        price=price,
                        volume=0,  # Jupiter price API doesn't include volume
                        timestamp=now,
                    )
                    result[asset] = tick
                    self._cache[asset] = (now, tick)

                return result

        except Exception as e:
            logger.error(f"[Jupiter] Price fetch error: {e}")
            return {a: t for a, (_, t) in self._cache.items()}

    async def get_tick(self, asset: str) -> MarketTick:
        """Get price for a single asset (fetches all, returns one)."""
        now = time.time()
        if asset in self._cache:
            cached_time, cached_tick = self._cache[asset]
            if now - cached_time < self._cache_ttl:
                return cached_tick

        all_prices = await self._fetch_all_prices()
        if asset in all_prices:
            return all_prices[asset]

        # Fallback
        return MarketTick(asset=asset, price=0, volume=0, timestamp=now)

    async def get_ticks(self, assets: list[str]) -> dict[str, MarketTick]:
        """Get prices for multiple assets — single API call."""
        all_prices = await self._fetch_all_prices()
        return {a: all_prices[a] for a in assets if a in all_prices}

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

        except Exception as e:
            logger.error(f"[Jupiter] Backfill error for {asset}: {e}")
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
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[Jupiter] Quote API HTTP {resp.status}")
                    return None
                return await resp.json()

        except Exception as e:
            logger.error(f"[Jupiter] Quote error: {e}")
            return None
