"""
Live market feed using the Jupiter API.

Uses Jupiter Price API v3 for Solana token prices, batching requested assets.
Provider failures stop execution; only source-validated complete batches are cached.

The separate Swap V2 helper supplies indicative token quotes only. It does not
participate in paper USD valuation and cannot build, sign, or execute a swap.

Completed indicator candles use the separate Birdeye V3 history adapter.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp

from .birdeye_candles import BirdeyeCandles
from .candles import MinuteCandle
from .feed import MarketFeed, MarketFeedError, MarketTick, QuoteEvidence
from .quote_freshness import quote_source_age, source_slot, validate_quote
from .solana_time import SolanaTimeResolver
from .provider_evidence import ProviderDocument, ProviderEvidenceError, bounded_response_body
from .exact_records import ExactPriceRecord, parse_price_record
from .swap_quote import (
    QUOTE_TIMEOUT_SECONDS, SWAP_ORDER_URL, SwapQuote, SwapQuoteError,
    bounded_quote_body, parse_swap_quote, quote_parameters,
)

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


@dataclass(frozen=True, slots=True)
class PriceCapture:
    """Exact provider price paired with the existing local block-time policy.

    RPC response bytes are not archived by this capture. Estimated source time
    is a local resolver result, not provider publication time or finality.
    """
    record: ExactPriceRecord
    source_timestamp: int
    evidence: QuoteEvidence

    def __post_init__(self):
        if (type(self.record) is not ExactPriceRecord or type(self.evidence) is not QuoteEvidence
                or type(self.source_timestamp) is not int or not 0 <= self.source_timestamp < 2**63
                or self.evidence.provider != self.record.document.provider
                or self.evidence.quote_currency != "USD"
                or self.evidence.source_slot != self.record.block_id
                or self.evidence.received_at != self.record.document.received_at
                or self.evidence.received_monotonic != self.record.document.received_monotonic):
            raise ProviderEvidenceError()
        quote_source_age(self.as_tick(), wall_now=self.evidence.received_at,
                         monotonic_now=self.evidence.received_monotonic)

    def as_tick(self) -> MarketTick:
        return MarketTick(self.record.asset, float(self.record.price), 0.0,
                          self.source_timestamp, self.evidence)

    def validate(self, *, previous_slot=None, wall_now=None, monotonic_now=None):
        validate_quote(self.as_tick(), previous_slot=previous_slot,
                       wall_now=wall_now, monotonic_now=monotonic_now)

    def to_dict(self):
        return {"record": self.record.to_dict(),
                "source_timestamp": self.source_timestamp,
                "source_time_policy": "jupiter-block-id-as-slot-estimated-time-v1",
                "source_age_at_receipt": self.evidence.source_age_at_receipt}


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
        self._captures: dict[str, PriceCapture] = {}
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

    async def _fetch_all_prices(self, assets: Optional[list[str]] = None, *, exact: bool = False):
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
                    ticks = await self._fetch_prices_locked(requested, deadline=deadline.when())
                    return ({asset: self._captures[asset] for asset in requested} if exact else ticks)
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
            capture = self._captures.get(asset)
            if capture is None:
                break
            try:
                capture.validate(previous_slot=self._source_slots.get(asset),
                                 wall_now=wall, monotonic_now=mono)
            except MarketFeedError:
                break
            # Legacy ticks are mutable. Never let a caller rewrite the retained
            # exact price or source-age anchor through a cached display view.
            view = capture.as_tick()
            cached[asset] = entry[1] if entry[1] == view else view
        if len(cached) == len(requested):
            return cached

        session = await self._get_session()
        self.api_call_count += 1
        parameters = {"ids": ",".join(TOKEN_MINTS[asset] for asset in requested)}
        async with session.get(
            f"{JUPITER_API_URL}/price/v3",
            params=parameters,
            headers=self._jup_headers,
            allow_redirects=False,
        ) as resp:
            if resp.status != 200:
                raise MarketFeedError("price_rate_limited" if resp.status == 429 else "price_unavailable")
            raw = await bounded_response_body(resp, provider="jupiter-price-v3")
            # Capture receipt before parsing/RPC. Both consume freshness.
            received_at, received_mono = time.time(), time.monotonic()
            document = ProviderDocument.capture("jupiter-price-v3", parameters, raw,
                                               received_at, received_mono)
            data = document.decode()
            if not isinstance(data, dict):
                raise MarketFeedError("price_invalid")

        candidates, errors = {}, {}
        for asset in requested:
            info = data.get(TOKEN_MINTS[asset])
            if not isinstance(info, dict):
                errors[asset] = MarketFeedError("price_missing")
                continue
            try:
                slot = source_slot(info.get("blockId"))
                record = parse_price_record(document, asset=asset, mint=TOKEN_MINTS[asset])
                candidates[asset] = (record, slot)
            except MarketFeedError as error:
                errors[asset] = error
            except (ValueError, TypeError, OverflowError):
                errors[asset] = MarketFeedError("price_invalid")

        times, time_errors = await self._source_time.resolve(
            session, [slot for _, slot in candidates.values()], deadline=deadline)
        result, captures = {}, {}
        # One final shared time boundary prevents earlier-resolved slots from
        # appearing fresh after a slow sibling lookup.
        wall, mono = time.time(), time.monotonic()
        for asset, (record, slot) in candidates.items():
            if slot in time_errors:
                errors[asset] = time_errors[slot]
                continue
            try:
                stamp = times[slot]
                age_floor = max(0.0, received_at - stamp)
                previous = self._captures.get(asset)
                if previous is not None:
                    previous_tick = previous.as_tick()
                    if (previous_tick.evidence.source_slot == slot
                            and previous_tick.timestamp != stamp):
                        raise MarketFeedError("source_time_invalid")
                    previous_age = quote_source_age(
                        previous_tick, wall_now=received_at, monotonic_now=received_mono)
                    age_floor = max(age_floor, previous_age - (stamp - previous_tick.timestamp))
                capture = PriceCapture(record, stamp, QuoteEvidence(
                    slot, received_at, received_mono, source_age_at_receipt=age_floor))
                tick = capture.as_tick()
                validate_quote(tick, previous_slot=self._source_slots.get(asset),
                               wall_now=wall, monotonic_now=mono)
                result[asset] = tick
                captures[asset] = capture
            except MarketFeedError as error:
                errors[asset] = error
            except (ValueError, TypeError, OverflowError):
                errors[asset] = MarketFeedError("price_invalid")
        if errors:
            first = next(errors[asset] for asset in requested if asset in errors)
            raise MarketFeedError(first.code, valid_ticks=result)
        self._captures.update(captures)
        self._cache.update({asset: (received_mono, tick) for asset, tick in result.items()})
        self._source_slots.update({asset: tick.evidence.source_slot for asset, tick in result.items()})
        return result

    async def get_tick(self, asset: str) -> MarketTick:
        """Get a validated price or an explicit provider failure, never a zero fallback."""
        return (await self._fetch_all_prices([asset]))[asset]

    async def get_ticks(self, assets: list[str]) -> dict[str, MarketTick]:
        """Get prices for multiple assets — single API call."""
        return await self._fetch_all_prices(assets)

    async def get_price_captures(self, assets: list[str]) -> dict[str, PriceCapture]:
        """Fresh immutable exact captures; not an executable engine checkpoint."""
        return await self._fetch_all_prices(assets, exact=True)

    async def get_exact_candles(self, assets: list[str], *, warmup: bool = False):
        """Retain provider decimals independently of legacy indicator views."""
        return await self._candles.get_exact_candles(assets, warmup=warmup)

    async def get_provider_history(self, *, previous_end: int | None = None):
        """Fresh bounded SOL/USD windows; the v5 owner retains the bar cursor."""
        return await self._candles.get_provider_history(previous_end=previous_end)

    async def get_candles(self, assets: list[str], *, warmup: bool = False) -> list[MinuteCandle]:
        """Fetch completed source minutes for the shared indicator history."""
        return await self._candles.get_candles(assets, warmup=warmup)

    # ── Indicative Swap V2 quotes (not used for paper USD valuation) ─────

    async def get_swap_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        slippage_bps: int | None = None,
    ) -> SwapQuote:
        """One bounded quote-only request, with explicit safe failure codes.

        Omits taker and all wallet/execution options. Default slippage is managed
        by Jupiter; an explicit integer override may affect routing. Returned
        amounts are atomic token estimates, not USD marks or net wallet fills.
        No provider error body, transaction, request ID, or raw response escapes.
        """
        params = quote_parameters(input_mint, output_mint, amount_atomic, slippage_bps)
        attempted = False

        async def one_attempt(request, handler):
            # aiohttp retries some idempotent GET disconnects internally. Its
            # public per-request middleware runs on each attempt, so block the
            # second before transport work without mutating our shared session.
            nonlocal attempted
            if attempted:
                raise SwapQuoteError("swap_quote_unavailable") from None
            attempted = True
            return await handler(request)

        try:
            async with asyncio.timeout(QUOTE_TIMEOUT_SECONDS):
                session = await self._get_session()
                self.api_call_count += 1
                async with session.get(
                    SWAP_ORDER_URL, params=params, headers=self._jup_headers,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=QUOTE_TIMEOUT_SECONDS),
                    middlewares=(one_attempt,),
                ) as resp:
                    if resp.status != 200:
                        code = ("swap_quote_auth_failed" if resp.status in (401, 403)
                                else "swap_quote_rate_limited" if resp.status == 429
                                else "swap_quote_redirect_rejected" if 300 <= resp.status < 400
                                else "swap_quote_provider_rejected" if 400 <= resp.status < 500
                                else "swap_quote_unavailable")
                        raise SwapQuoteError(code)
                    body = await bounded_quote_body(resp)
                    received_at, received_mono = time.time(), time.monotonic()
                return parse_swap_quote(
                    body, input_mint=input_mint, output_mint=output_mint,
                    amount_atomic=amount_atomic, slippage_bps=slippage_bps,
                    received_at=received_at, received_monotonic=received_mono,
                )
        except SwapQuoteError:
            raise
        except TimeoutError:
            raise SwapQuoteError("swap_quote_timeout") from None
        except Exception:
            raise SwapQuoteError("swap_quote_unavailable") from None
