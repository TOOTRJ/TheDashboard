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
    from vonneumann.market.feed import MarketTick


SOL, JUP = "SOL/USDC", "JUP/USDC"
SECRET = "fake-provider-secret-do-not-display"


def prices(**values):
    return {module.TOKEN_MINTS[asset]: {"usdPrice": value} for asset, value in values.items()}


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
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected provider request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def close(self):
        self.closed = True


class FeedReliabilityTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def make_feed(self, *responses, volume=False):
        feed = module.JupiterFeed(api_key=SECRET)
        feed._session = Session(*responses)
        if volume:
            feed._birdeye_key = SECRET
            feed._birdeye_headers = {"X-API-KEY": SECRET}
        return feed

    def stale_cache(self, feed):
        stamp = time.time() - 30
        feed._cache[SOL] = (stamp, MarketTick(SOL, 100, 4, stamp))
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
        feed = module.JupiterFeed(api_key=SECRET)
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

    async def test_configured_volume_http_transport_and_payload_failures_surface(self):
        cases = [Response(status=code) for code in (401, 429, 500, 302)]
        cases += [aiohttp.ClientConnectionError(SECRET), asyncio.TimeoutError(SECRET),
                  Response(error=ValueError(SECRET)), Response([]),
                  Response({"success": False, "message": SECRET}),
                  Response({"data": {"items": "invalid"}})]
        for response in cases:
            with self.subTest(kind=type(response).__name__):
                feed = self.make_feed(response, volume=True)
                feed._volume_cache[SOL] = 7
                await self.assert_safe_failure(feed.refresh_volumes([SOL]))
                self.assertEqual(feed._volume_cache, {SOL: 7})
                self.assertEqual(feed._last_volume_refresh, 0)

    async def test_volume_requires_finite_nonnegative_numeric_value(self):
        for value in (None, False, "7", -1, float("nan"), float("inf")):
            with self.subTest(value_type=type(value).__name__):
                body = {"data": {"items": [{"v": value}]}}
                await self.assert_safe_failure(self.make_feed(Response(body), volume=True).refresh_volumes([SOL]))

    async def test_volume_batch_commits_atomically_and_throttles_only_after_success(self):
        body = {"data": {"items": [{"v": 0}]}}
        feed = self.make_feed(Response(body), Response(status=503), Response(body), volume=True)
        feed._volume_cache[SOL] = 5
        with patch.object(module.asyncio, "sleep", new=AsyncMock()):
            await self.assert_safe_failure(feed.refresh_volumes([SOL, JUP]))
            self.assertEqual(feed._volume_cache, {SOL: 5})
            await feed.refresh_volumes([SOL])
            self.assertEqual(feed._volume_cache, {SOL: 0})
            self.assertGreater(feed._last_volume_refresh, 0)
            await feed.refresh_volumes([SOL])
        self.assertEqual(len(feed._session.calls), 3)
        self.assertTrue(all(options["allow_redirects"] is False for _, options in feed._session.calls))

    async def test_missing_optional_volume_key_and_empty_history_policy_are_preserved(self):
        feed = self.make_feed()
        await feed.refresh_volumes([SOL])
        self.assertEqual(await feed.backfill(SOL), [])
        self.assertEqual(feed._session.calls, [])
        feed = self.make_feed(Response({"data": {"items": []}}), volume=True)
        with patch.object(module.asyncio, "sleep", new=AsyncMock()):
            await feed.refresh_volumes([SOL])
        self.assertEqual(feed._volume_cache, {})

    async def test_optional_history_and_quote_logs_do_not_echo_provider_exception(self):
        feed = self.make_feed(Response(error=ValueError(SECRET)), Response(error=ValueError(SECRET)), volume=True)
        with self.assertLogs(module.logger, level="WARNING") as captured:
            self.assertEqual(await feed.backfill(SOL), [])
            self.assertIsNone(await feed.get_swap_quote("fake-input", "fake-output", 100))
        self.assertNotIn(SECRET, " ".join(captured.output))
        self.assertTrue(all(options["allow_redirects"] is False for _, options in feed._session.calls))
