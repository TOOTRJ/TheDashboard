"""Bounded mainnet block-time evidence; no claim of price or block finality."""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from urllib.parse import urlsplit

from .feed import MarketFeedError
from .quote_freshness import source_slot

MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
MAX_RPC_RESPONSE_BYTES = 65536


def _unique(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError()


def validate_rpc_url(value: str) -> str:
    """Keep credentials private; an explicit HTTPS RPC endpoint is required."""
    try:
        if (not isinstance(value, str) or not value or "\\" in value
                or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError()
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.fragment or "#" in value
                or parsed.port == 0):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise MarketFeedError("rpc_configuration") from None


class SolanaTimeResolver:
    """Resolve at most eight unique slots, with four requests in flight.

    The caller bounds the complete Jupiter + RPC operation with one deadline.
    The small monotonic cache is evidence reuse, never a freshness override.
    """

    CACHE_LIMIT = 256
    CACHE_TTL = 30.0

    def __init__(self, rpc_url: str):
        self._rpc_url = validate_rpc_url(rpc_url)
        self._verified_session = None
        self._request_id = 0
        self._cache: OrderedDict[int, tuple[float, int]] = OrderedDict()
        self.api_call_count = 0

    async def _rpc(self, session, method: str, params: list):
        self._request_id += 1
        request_id = self._request_id
        try:
            self.api_call_count += 1
            async with session.post(
                self._rpc_url,
                json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise MarketFeedError("rpc_rate_limited" if response.status == 429 else "rpc_unavailable")
                raw = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    if len(raw) + len(chunk) > MAX_RPC_RESPONSE_BYTES:
                        raise MarketFeedError("rpc_invalid")
                    raw.extend(chunk)
                body = json.loads(raw.decode('utf-8', errors='strict'),
                                  object_pairs_hook=_unique, parse_constant=_invalid_constant)
                if (not isinstance(body, dict) or body.get("jsonrpc") != "2.0"
                        or type(body.get("id")) is not int or body["id"] != request_id
                        or "error" in body or "result" not in body):
                    raise MarketFeedError("rpc_invalid")
                return body["result"]
        except MarketFeedError:
            raise
        except (ValueError, TypeError, OverflowError):
            raise MarketFeedError("rpc_invalid") from None
        except Exception:
            raise MarketFeedError("rpc_unavailable") from None

    async def resolve(self, session, slots: list[int], *, deadline: float | None = None
                      ) -> tuple[dict[int, int], dict[int, MarketFeedError]]:
        unique = list(dict.fromkeys(source_slot(slot) for slot in slots))
        if len(unique) > 8:
            raise MarketFeedError("source_time_invalid")
        if not unique:
            return {}, {}
        if self._verified_session is not session:
            genesis = await self._rpc(session, "getGenesisHash", [])
            if genesis != MAINNET_GENESIS_HASH:
                raise MarketFeedError("rpc_wrong_network")
            self._verified_session = session
            # Never carry block evidence across a replaced client/network check.
            self._cache.clear()

        now = time.monotonic()
        for slot, (cached_at, _) in list(self._cache.items()):
            if not 0 <= now - cached_at < self.CACHE_TTL:
                del self._cache[slot]
        resolved = {}
        pending = []
        for slot in unique:
            if slot in self._cache:
                resolved[slot] = self._cache[slot][1]
                self._cache.move_to_end(slot)
            else:
                pending.append(slot)

        semaphore = asyncio.Semaphore(4)

        async def fetch(slot):
            async with semaphore:
                try:
                    stamp = await self._rpc(session, "getBlockTime", [slot])
                    if stamp is None:
                        raise MarketFeedError("source_time_unavailable")
                    if type(stamp) is not int or not 0 <= stamp < 2**63:
                        raise MarketFeedError("source_time_invalid")
                    return slot, stamp, None
                except MarketFeedError as error:
                    return slot, None, error

        # Leave a short part of the caller's deadline for cancellation and final
        # quote validation. A slow slot must not discard a completed sibling
        # needed for the controller's last risk pass. External cancellation
        # still propagates without committing any part of this lookup group.
        tasks = {asyncio.create_task(fetch(slot)): slot for slot in pending}
        results = []
        if tasks:
            loop = asyncio.get_running_loop()
            end = loop.time() + 5 if deadline is None else deadline
            try:
                done, unfinished = await asyncio.wait(tasks, timeout=max(0.0, end - loop.time() - 0.05))
                for task in unfinished:
                    task.cancel()
                if unfinished:
                    await asyncio.gather(*unfinished, return_exceptions=True)
                # Iterate request order for deterministic error selection.
                for task, slot in tasks.items():
                    results.append(task.result() if task in done else
                                   (slot, None, MarketFeedError("rpc_unavailable")))
            except BaseException:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
        errors = {}
        cached_at = time.monotonic()
        for slot, stamp, error in results:
            if error is not None:
                errors[slot] = error
            else:
                resolved[slot] = stamp
                self._cache[slot] = (cached_at, stamp)
                self._cache.move_to_end(slot)
        while len(self._cache) > self.CACHE_LIMIT:
            self._cache.popitem(last=False)
        return resolved, errors
