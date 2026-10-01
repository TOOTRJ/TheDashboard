"""Real Jupiter/Birdeye adapter behavior with fake HTTP and no provider access."""

from __future__ import annotations

import asyncio
import time
import traceback
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    import aiohttp
    from vonneumann.market import jupiter_feed as module
    from vonneumann.market.feed import MarketTick, QuoteEvidence
    from vonneumann.market.solana_time import MAINNET_GENESIS_HASH


SOL, JUP = "SOL/USDC", "JUP/USDC"
SECRET = "fake-provider-secret-do-not-display"
RPC_URL = "https://rpc.example.test/?api-key=" + SECRET


def prices(**values):
    return {module.TOKEN_MINTS[asset]: {"usdPrice": value, "blockId": 123456} for asset, value in values.items()}


class Response:
    def __init__(self, body=None, status=200, error=None):
        self.body, self.status, self.error = body, status, error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        if self.error:
            raise self.error
        return self.body


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.rpc_calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected provider request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    def post(self, url, **kwargs):
        self.rpc_calls.append((url, kwargs))
        payload = kwargs["json"]
        result = MAINNET_GENESIS_HASH if payload["method"] == "getGenesisHash" else int(time.time())
        return Response({"jsonrpc": "2.0", "id": payload["id"], "result": result})

    async def close(self):
        self.closed = True


class FeedReliabilityTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def make_feed(self, *responses):
        feed = module.JupiterFeed(api_key=SECRET, rpc_url=RPC_URL)
        feed._session = Session(*responses)
        return feed

    def stale_cache(self, feed):
        stamp = time.monotonic() - 30
        wall = time.time() - 30
        feed._cache[SOL] = (stamp, MarketTick(
            SOL, 100, 4, wall, QuoteEvidence(123455, wall, stamp)))
        return dict(feed._cache)

    async def assert_safe_failure(self, operation):
        with self.assertRaises(module.MarketFeedError) as caught:
            await operation
        self.assertNotIn(SECRET, str(caught.exception))
        formatted = "".join(traceback.format_exception(caught.exception))
        self.assertNotIn(SECRET, formatted)
        return caught.exception

    async def test_valid_requested_batch_has_one_request_and_fresh_cache_reuse(self):
        feed = self.make_feed(Response(prices(**{SOL: 123.5, JUP: 1.0})))
        ticks = await feed.get_ticks([SOL, JUP, SOL])
        self.assertEqual(set(ticks), {SOL, JUP})
        self.assertEqual(ticks[SOL].price, 123.5)
        self.assertIs(await feed.get_tick(SOL), ticks[SOL])
        self.assertEqual(feed.api_call_count, 1)
        url, options = feed._session.calls[0]
        self.assertEqual(url, "https://api.jup.ag/price/v3")
        self.assertEqual(options["params"]["ids"], ",".join([module.TOKEN_MINTS[SOL], module.TOKEN_MINTS[JUP]]))
        self.assertFalse(options["allow_redirects"])

    async def test_rate_limits_errors_and_redirects_never_return_expired_prices(self):
        for status in (401, 403, 429, 500, 503, 301, 302, 307):
            with self.subTest(status=status):
                feed = self.make_feed(Response(status=status))
                old = self.stale_cache(feed)
                error = await self.assert_safe_failure(feed.get_ticks([SOL]))
                self.assertEqual(error.code, "price_rate_limited" if status == 429 else "price_unavailable")
                self.assertEqual(feed._cache, old)

    async def test_transport_timeout_and_json_errors_are_safe_and_no_stale_fallback(self):
        for response in (aiohttp.ClientConnectionError(SECRET), asyncio.TimeoutError(SECRET),
                         Response(error=ValueError(SECRET))):
            with self.subTest(kind=type(response).__name__):
                feed = self.make_feed(response)
                old = self.stale_cache(feed)
                await self.assert_safe_failure(feed.get_tick(SOL))
                self.assertEqual(feed._cache, old)

    async def test_missing_requested_price_never_becomes_zero_or_partial_result(self):
        for body in ({}, prices(**{JUP: 1}), {module.TOKEN_MINTS[SOL]: None}):
            for multi in (False, True):
                with self.subTest(body=body, multi=multi):
                    feed = self.make_feed(Response(body))
                    operation = feed.get_ticks([SOL]) if multi else feed.get_tick(SOL)
                    await self.assert_safe_failure(operation)

    async def test_malformed_shapes_and_nonfinite_nonpositive_prices_fail_closed(self):
        bodies = [None, [], "invalid", {module.TOKEN_MINTS[SOL]: []}]
        bodies += [prices(**{SOL: value}) for value in
                   (None, False, True, "123", 0, -1, float("nan"), float("inf"), -float("inf"))]
        for body in bodies:
            with self.subTest(body_type=type(body).__name__):
                await self.assert_safe_failure(self.make_feed(Response(body)).get_tick(SOL))

    async def test_partial_invalid_price_batch_does_not_commit_earlier_valid_asset(self):
        feed = self.make_feed(Response(prices(**{SOL: 120, JUP: float("nan")})))
        old = self.stale_cache(feed)
        await self.assert_safe_failure(feed.get_ticks([SOL, JUP]))
        self.assertEqual(feed._cache, old)

    async def test_successful_retry_replaces_old_cache_after_previous_failure(self):
        feed = self.make_feed(Response(status=503), Response(prices(**{SOL: 121})))
        self.stale_cache(feed)
        await self.assert_safe_failure(feed.get_tick(SOL))
        self.assertEqual((await feed.get_tick(SOL)).price, 121)
        self.assertEqual(feed.api_call_count, 2)

    async def test_empty_or_unknown_asset_requests_do_not_call_provider(self):
        feed = self.make_feed()
        self.assertEqual(await feed.get_ticks([]), {})
        await self.assert_safe_failure(feed.get_tick("unknown-private-value"))
        self.assertEqual(feed._session.calls, [])

    async def test_session_creation_is_bounded_and_does_not_use_proxy_environment(self):
        feed = module.JupiterFeed(api_key=SECRET, rpc_url=RPC_URL)
        fake = Session(Response(prices(**{SOL: 99})))
        with patch.object(module.aiohttp, "ClientSession", return_value=fake) as factory:
            await feed.get_tick(SOL)
        self.assertFalse(factory.call_args.kwargs["trust_env"])
        self.assertEqual(factory.call_args.kwargs["timeout"].total, 5)
        await feed.close()
        self.assertTrue(fake.closed)

    async def test_price_cancellation_propagates_without_cache_commit(self):
        feed = self.make_feed(asyncio.CancelledError())
        old = self.stale_cache(feed)
        with self.assertRaises(asyncio.CancelledError):
            await feed.get_tick(SOL)
        self.assertEqual(feed._cache, old)

    async def test_price_quotes_have_no_invented_or_repeated_candle_volume(self):
        feed = self.make_feed(Response(prices(**{SOL: 120})))
        tick = await feed.get_tick(SOL)
        self.assertEqual(tick.volume, 0)
        self.assertFalse(hasattr(feed, "refresh_volumes"))
        self.assertFalse(hasattr(feed, "_volume_cache"))
        self.assertFalse(hasattr(feed, "backfill_probe"))

    async def test_candle_access_delegates_without_using_jupiter_http_session_or_counter(self):
        feed = self.make_feed()
        candles = [object()]
        feed._candles.get_candles = AsyncMock(return_value=candles)
        self.assertIs(await feed.get_candles([SOL], warmup=True), candles)
        feed._candles.get_candles.assert_awaited_once_with([SOL], warmup=True)
        self.assertEqual(feed._session.calls, [])
        self.assertEqual(feed.api_call_count, 0)

    async def test_missing_birdeye_configuration_fails_on_candle_access_only(self):
        feed = module.JupiterFeed(api_key=SECRET, rpc_url=RPC_URL, birdeye_api_key="")
        feed._session = Session(Response(prices(**{SOL: 120})))
        self.assertEqual((await feed.get_tick(SOL)).price, 120)
        error = await self.assert_safe_failure(feed.get_candles([SOL], warmup=True))
        self.assertEqual(error.code, "candles_configuration")
        self.assertIsNone(feed._candles._session)

    async def test_birdeye_key_override_and_close_both_sessions(self):
        feed = module.JupiterFeed(api_key=SECRET, rpc_url=RPC_URL, birdeye_api_key="explicit-candle-key")
        self.assertEqual(feed._candles._api_key, "explicit-candle-key")
        self.assertEqual(feed._candles._token_mints, module.TOKEN_MINTS)
        feed._session = Session()
        candle_session = Session()
        feed._candles._session = candle_session
        await feed.close()
        self.assertTrue(feed._session.closed)
        self.assertTrue(candle_session.closed)

    async def test_close_candle_session_even_if_quote_session_close_fails(self):
        feed = self.make_feed()
        feed._session.close = AsyncMock(side_effect=RuntimeError("test close failure"))
        feed._candles.close = AsyncMock()
        with self.assertRaises(RuntimeError):
            await feed.close()
        feed._candles.close.assert_awaited_once()

    async def test_optional_swap_quote_errors_do_not_echo_provider_exception(self):
        feed = self.make_feed(RuntimeError(SECRET))
        with self.assertRaises(module.SwapQuoteError) as captured:
            await feed.get_swap_quote(module.TOKEN_MINTS[SOL], module.USDC_MINT, 100)
        self.assertEqual(captured.exception.code, "swap_quote_unavailable")
        self.assertNotIn(SECRET, "".join(traceback.format_exception(captured.exception)))
        self.assertTrue(all(options["allow_redirects"] is False for _, options in feed._session.calls))
