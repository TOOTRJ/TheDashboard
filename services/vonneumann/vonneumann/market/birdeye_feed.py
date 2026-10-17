"""
Live market feed using the Birdeye API.

Fetches real Solana token prices for paper trading mode.
Uses the /defi/price endpoint for spot prices and /defi/ohlcv for history backfill.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

from ..http_tls import require_no_keylog, verified_http_context

require_no_keylog()
import aiohttp

from .feed import MarketFeed, MarketTick

logger = logging.getLogger(__name__)

BIRDEYE_API_URL = "https://public-api.birdeye.so"
BIRDEYE_API_KEY = os.environ.get("BIRDEYE_API_KEY", "")

# Token mint addresses on Solana mainnet
TOKEN_ADDRESSES: dict[str, str] = {
    "SOL/USDC": "So11111111111111111111111111111111111111112",
    "JUP/USDC": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "JTO/USDC": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
    "PYTH/USDC": "HZ1JovNiVvGrGaNiWp8WnpF89F3PqkqnhHHgFTbXSqoD",
    "ORCA/USDC": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "RAY/USDC": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
}

# Rate limit: Birdeye free tier is strict, keep ~1 req/sec to be safe
REQUEST_DELAY = 0.75  # seconds between requests


class BirdeyeFeed(MarketFeed):
    """
    Live market feed fetching real prices from Birdeye API.
    Each get_tick() call makes an HTTP request. Prices are cached briefly
    to avoid hammering the API when multiple probes track the same asset.
    """

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or BIRDEYE_API_KEY
        if not self._api_key:
            raise ValueError("BIRDEYE_API_KEY is required for paper trading mode")

        self._headers = {
            "X-API-KEY": self._api_key,
            "x-chain": "solana",
            "User-Agent": "VonNeumann/1.0",
            "Accept": "application/json",
        }

        # Price cache: asset -> (timestamp, MarketTick)
        self._cache: dict[str, tuple[float, MarketTick]] = {}
        self._cache_ttl = 2.0  # seconds

        # Session reuse
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=10),
                trust_env=False,
                connector=aiohttp.TCPConnector(ssl=verified_http_context()),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_address(self, asset: str) -> str:
        addr = TOKEN_ADDRESSES.get(asset)
        if not addr:
            raise ValueError(f"Unknown asset: {asset}. Known: {list(TOKEN_ADDRESSES.keys())}")
        return addr

    async def get_tick(self, asset: str) -> MarketTick:
        """Fetch latest price for an asset. Uses brief cache to avoid duplicate calls."""
        now = time.time()

        # Check cache
        if asset in self._cache:
            cached_time, cached_tick = self._cache[asset]
            if now - cached_time < self._cache_ttl:
                return cached_tick

        address = self._get_address(asset)
        session = await self._get_session()

        try:
            async with session.get(
                f"{BIRDEYE_API_URL}/defi/price",
                params={"address": address},
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[Birdeye] Price fetch failed for {asset}: HTTP {resp.status}")
                    # Return cached value if available, else error
                    if asset in self._cache:
                        return self._cache[asset][1]
                    return MarketTick(asset=asset, price=0, volume=0, timestamp=now)

                data = await resp.json()
                price_data = data.get("data", {})
                price = float(price_data.get("value", 0))

                tick = MarketTick(
                    asset=asset,
                    price=price,
                    volume=0,  # Price endpoint doesn't include volume
                    timestamp=now,
                )
                self._cache[asset] = (now, tick)
                return tick

        except Exception as e:
            logger.error(f"[Birdeye] Price fetch error for {asset}: {e}")
            if asset in self._cache:
                return self._cache[asset][1]
            return MarketTick(asset=asset, price=0, volume=0, timestamp=now)

    async def get_ticks(self, assets: list[str]) -> dict[str, MarketTick]:
        """Fetch latest prices for multiple assets with rate limiting."""
        result: dict[str, MarketTick] = {}
        for asset in assets:
            result[asset] = await self.get_tick(asset)
            await asyncio.sleep(REQUEST_DELAY)
        return result

    async def backfill(
        self,
        asset: str,
        timeframe_minutes: int = 15,
        limit: int = 100,
    ) -> list[dict]:
        """
        Fetch OHLCV candle history for signal warmup.
        Returns list of {price, volume} dicts (close prices).
        Used to pre-fill a probe's price buffer so RSI/EMA can compute from tick 1.
        """
        address = self._get_address(asset)
        session = await self._get_session()

        interval_map = {1: "1m", 3: "3m", 5: "5m", 15: "15m", 30: "30m", 60: "1H"}
        interval = interval_map.get(timeframe_minutes, "15m")

        now = int(time.time())
        time_from = now - (limit * timeframe_minutes * 60)

        try:
            async with session.get(
                f"{BIRDEYE_API_URL}/defi/ohlcv",
                params={
                    "address": address,
                    "type": interval,
                    "time_from": time_from,
                    "time_to": now,
                },
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[Birdeye] OHLCV fetch failed for {asset}: HTTP {resp.status}")
                    return []

                data = await resp.json()
                items = data.get("data", {}).get("items", [])

                candles = []
                for c in items:
                    candles.append({
                        "price": float(c["c"]),   # close price
                        "volume": float(c["v"]),
                        "open": float(c["o"]),
                        "high": float(c["h"]),
                        "low": float(c["l"]),
                        "timestamp": c.get("unixTime", 0),
                    })

                logger.info(f"[Birdeye] Backfilled {len(candles)} candles for {asset} ({interval})")
                return candles

        except Exception as e:
            logger.error(f"[Birdeye] OHLCV fetch error for {asset}: {e}")
            return []

    async def backfill_probe(
        self,
        assets: list[str],
        timeframe_minutes: int = 15,
        limit: int = 100,
    ) -> dict[str, list[dict]]:
        """Backfill multiple assets. Returns {asset: [candles]}."""
        result: dict[str, list[dict]] = {}
        for asset in assets:
            result[asset] = await self.backfill(asset, timeframe_minutes, limit)
            await asyncio.sleep(REQUEST_DELAY)
        return result
