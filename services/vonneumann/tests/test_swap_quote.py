"""Real Swap V2 quote adapter, fake HTTP only; no provider/wallet access."""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError, asdict
import hashlib
import json
import traceback
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    import aiohttp
    from vonneumann.market import jupiter_feed as module
    from vonneumann.market import swap_quote as contract

SOL = module.TOKEN_MINTS["SOL/USDC"]
USDC = module.USDC_MINT
SECRET = "test-only-key-and-private-provider-message"
RPC_URL = "https://rpc.example.test/"


def quote_body(**changes):
    return {"inputMint": SOL, "outputMint": USDC, "inAmount": "1000000000",
            "outAmount": "150000000", "otherAmountThreshold": "148500000",
            "swapMode": "ExactIn", "slippageBps": 100, "router": "metis",
            "mode": "ultra", "transaction": None, "taker": None, **changes}


class Content:
    def __init__(self, raw, *, error=None, delay=0):
        self.raw, self.error, self.delay = raw, error, delay
        self.reads = 0

    async def iter_chunked(self, size):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        for start in range(0, len(self.raw), size):
            self.reads += 1
            yield self.raw[start:start + size]


class Response:
    def __init__(self, body=None, *, raw=None, status=200, length=None, error=None, delay=0):
        self.raw = json.dumps(quote_body() if body is None else body).encode() if raw is None else raw
        self.status = status
        self.content_length = length
        self.content = Content(self.raw, error=error, delay=delay)
        self.exited = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.exited = True
        return False


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    def post(self, *args, **kwargs):
        raise AssertionError("Quote adapter must never execute, sign or call RPC")


class SwapQuoteTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def feed(self, response):
        feed = module.JupiterFeed(api_key=SECRET, rpc_url=RPC_URL, birdeye_api_key="")
        feed._session = Session(response)
        return feed

    async def request(self, feed, *, amount=1000000000, slippage=None):
        return await feed.get_swap_quote(SOL, USDC, amount, slippage)

    async def assert_error(self, feed, code, **kwargs):
        try:
            await self.request(feed, **kwargs)
        except contract.SwapQuoteError as error:
            self.assertEqual(error.code, code)
            self.assertNotIn(SECRET, str(error))
            self.assertNotIn(SECRET, "".join(traceback.format_exception(error)))
            return
        self.fail("Expected explicit safe swap quote failure")

    async def test_managed_quote_uses_v2_private_auth_without_wallet_or_execution_options(self):
        response = Response(quote_body(requestId=SECRET, routePlan=[{"private": SECRET}],
                                       feeMint=USDC, feeBps=2, totalInputAmount=SECRET))
        feed = self.feed(response)
        result = await self.request(feed)
        self.assertEqual(len(feed._session.calls), 1)
        url, options = feed._session.calls[0]
        self.assertEqual(url, "https://api.jup.ag/swap/v2/order")
        self.assertEqual(options["params"], {"inputMint": SOL, "outputMint": USDC, "amount": "1000000000"})
        self.assertEqual(options["headers"]["x-api-key"], SECRET)
        self.assertIs(options["allow_redirects"], False)
        self.assertEqual(options["timeout"].total, 5)
        self.assertEqual(result.input_amount_atomic, 1000000000)
        self.assertEqual(result.output_amount_atomic, 150000000)
        self.assertEqual(result.minimum_output_amount_atomic, 148500000)
        self.assertIsNone(result.requested_slippage_bps)
        self.assertEqual(result.slippage_bps, 100)
        self.assertEqual(result.response_sha256, hashlib.sha256(response.raw).hexdigest())
        self.assertEqual(result.provider, "jupiter-swap-v2-order")
        self.assertEqual(result.semantics, "indicative-exact-in-quote-only-v1")
        self.assertGreater(result.received_at, 0)
        self.assertGreater(result.received_monotonic, 0)
        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn("transaction", asdict(result))
        self.assertNotIn("source_time", asdict(result))
        with self.assertRaises(FrozenInstanceError):
            result.output_amount_atomic = 1
        self.assertTrue(response.exited)
        self.assertEqual(feed.api_call_count, 1)
        self.assertEqual(feed._cache, {})
        self.assertEqual(feed._source_slots, {})

    async def test_explicit_zero_and_maximum_slippage_are_distinct_from_managed(self):
        for slippage in (0, 100, 10000):
            response = Response(quote_body(slippageBps=slippage, mode="manual",
                                          otherAmountThreshold="0" if slippage == 10000 else "150000000"))
            feed = self.feed(response)
            result = await self.request(feed, slippage=slippage)
            self.assertEqual(result.requested_slippage_bps, slippage)
            self.assertEqual(feed._session.calls[0][1]["params"]["slippageBps"], str(slippage))

    async def test_atomic_values_above_float_precision_and_uint64_max_remain_exact(self):
        for amount in (1, 2**53 + 1, contract.UINT64_MAX):
            feed = self.feed(Response(quote_body(inAmount=str(amount), outAmount=str(amount),
                                                 otherAmountThreshold=str(amount))))
            result = await self.request(feed, amount=amount)
            self.assertEqual(result.input_amount_atomic, amount)
            self.assertEqual(result.output_amount_atomic, amount)
            self.assertEqual(feed._session.calls[0][1]["params"]["amount"], str(amount))

    async def test_invalid_requests_fail_before_session_or_network_access(self):
        feed = self.feed(Response())
        feed._get_session = AsyncMock(side_effect=AssertionError("Must not create a session"))
        for amount in (True, False, 1.0, "1", 0, -1, 2**64, None, float("nan"), float("inf")):
            with self.subTest(amount=amount):
                await self.assert_error(feed, "swap_quote_invalid_request", amount=amount)
        for slippage in (True, False, 1.0, "100", -1, 10001, [], float("nan")):
            with self.subTest(slippage=slippage):
                await self.assert_error(feed, "swap_quote_invalid_request", slippage=slippage)
        for invalid in (None, [], "fake-input", "0" * 44, "1" * 31, "1" * 33,
                        "z" * 44, " " + SOL, SOL + "\n", "1" + SOL, "é" * 32):
            for args in ((invalid, USDC), (SOL, invalid)):
                with self.subTest(mints=args), self.assertRaises(contract.SwapQuoteError) as caught:
                    await feed.get_swap_quote(*args, 1)
                self.assertEqual(caught.exception.code, "swap_quote_invalid_request")
        with self.assertRaises(contract.SwapQuoteError):
            await feed.get_swap_quote(SOL, SOL, 1)
        feed._get_session.assert_not_awaited()
        self.assertEqual(feed.api_call_count, 0)

    async def test_mints_require_canonical_base58_32_bytes_without_token_safety_claim(self):
        # Public key encoding only; the all-zero system address is not asserted
        # to be an SPL mint. No on-chain token/decimal lookup occurs here.
        self.assertTrue(contract._valid_mint("1" * 32))
        for mint in (*module.TOKEN_MINTS.values(), USDC):
            self.assertTrue(contract._valid_mint(mint))

    async def test_http_statuses_are_explicit_and_never_read_private_error_bodies_or_retry(self):
        for status, code in ((400, "swap_quote_provider_rejected"), (401, "swap_quote_auth_failed"),
                             (403, "swap_quote_auth_failed"), (429, "swap_quote_rate_limited"),
                             (301, "swap_quote_redirect_rejected"), (307, "swap_quote_redirect_rejected"),
                             (500, "swap_quote_unavailable"), (503, "swap_quote_unavailable")):
            response = Response(raw=SECRET.encode(), status=status)
            feed = self.feed(response)
            await self.assert_error(feed, code)
            self.assertEqual(response.content.reads, 0)
            self.assertEqual(len(feed._session.calls), 1)
            self.assertTrue(response.exited)

    async def test_transport_errors_are_redacted_without_retry(self):
        for response in (RuntimeError(SECRET), Response(error=RuntimeError(SECRET))):
            feed = self.feed(response)
            await self.assert_error(feed, "swap_quote_unavailable")
            self.assertEqual(len(feed._session.calls), 1)

    async def test_real_aiohttp_internal_disconnect_retry_cannot_send_a_second_attempt(self):
        async with aiohttp.ClientSession(trust_env=False) as session:
            feed = self.feed(Response())
            feed._session = session
            # Invoke the actual client retry loop with only its connector mocked.
            # No socket is created and no request reaches a provider.
            with patch.object(session.connector, "connect", new_callable=AsyncMock,
                              side_effect=aiohttp.ServerDisconnectedError(SECRET)) as connect:
                await self.assert_error(feed, "swap_quote_unavailable")
            connect.assert_awaited_once()
            self.assertEqual(feed.api_call_count, 1)

    async def test_timeout_bounds_session_acquisition_and_entire_body_read(self):
        with patch.object(module, "QUOTE_TIMEOUT_SECONDS", .01):
            feed = self.feed(Response(delay=.1))
            await self.assert_error(feed, "swap_quote_timeout")
            self.assertEqual(len(feed._session.calls), 1)
            feed = self.feed(Response())
            async def slow_session():
                await asyncio.sleep(.1)
                return feed._session
            feed._get_session = slow_session
            await self.assert_error(feed, "swap_quote_timeout")
            self.assertEqual(feed.api_call_count, 0)

    async def test_cancellation_propagates_without_conversion_or_retry(self):
        feed = self.feed(Response(error=asyncio.CancelledError()))
        with self.assertRaises(asyncio.CancelledError):
            await self.request(feed)
        self.assertEqual(len(feed._session.calls), 1)

    async def test_response_bytes_bounded_with_missing_or_false_content_length(self):
        for length in (None, 1, contract.MAX_QUOTE_BYTES + 1):
            response = Response(raw=b" " * (contract.MAX_QUOTE_BYTES + 1), length=length)
            feed = self.feed(response)
            await self.assert_error(feed, "swap_quote_too_large")
            self.assertTrue(response.exited)
            if length == contract.MAX_QUOTE_BYTES + 1:
                self.assertEqual(response.content.reads, 0)

    async def test_invalid_json_and_ambiguous_keys_never_produce_quote(self):
        for raw in (b"", b"<html>private</html>", b"null", b"[]", b"true", b"{}", b"\xff",
                    b'{"transaction":null,"transaction":null}', b'{"private":NaN}',
                    b"[" * 2000 + b"]" * 2000):
            await self.assert_error(self.feed(Response(raw=raw)), "swap_quote_invalid")

    async def test_no_transaction_or_wallet_context_can_escape(self):
        for changes in ({"transaction": SECRET}, {"transaction": ""}, {"transaction": {}},
                        {"taker": SOL}, {"taker": ""}):
            await self.assert_error(self.feed(Response(quote_body(**changes))), "swap_quote_not_read_only")
        value = quote_body()
        del value["transaction"]
        await self.assert_error(self.feed(Response(value)), "swap_quote_invalid")

    async def test_provider_error_fields_are_rejected_without_reflecting_messages(self):
        for changes in ({"error": SECRET}, {"errorMessage": SECRET}, {"errorCode": 1}, {"errorCode": 0}):
            await self.assert_error(self.feed(Response(quote_body(**changes))), "swap_quote_provider_rejected")

    async def test_requested_identity_amount_slippage_and_response_enum_must_match(self):
        for changes in ({"inputMint": USDC}, {"outputMint": SOL}, {"inAmount": "999"},
                        {"swapMode": "ExactOut"}, {"swapMode": None}, {"router": SECRET},
                        {"mode": "future"}, {"slippageBps": True}, {"slippageBps": 1.5},
                        {"slippageBps": -1}, {"slippageBps": 10001}, {"slippageBps": "100"},
                        {"slippageBps": 10**1000},
                        {"otherAmountThreshold": "150000001"}):
            await self.assert_error(self.feed(Response(quote_body(**changes))), "swap_quote_invalid")
        await self.assert_error(self.feed(Response()), "swap_quote_invalid", slippage=50)
        for router in ("metis", "jupiterz", "dflow", "okx"):
            result = await self.request(self.feed(Response(quote_body(router=router))))
            self.assertEqual(result.router, router)

    async def test_response_atomic_strings_are_canonical_positive_uint64_except_zero_threshold(self):
        for field in ("inAmount", "outAmount", "otherAmountThreshold"):
            for invalid in (1, 1.0, True, None, "", "-1", "+1", "01", "1.0", "1e9", "１", "1\n", " 1", str(2**64), "1" * 1000):
                with self.subTest(field=field, invalid=invalid):
                    await self.assert_error(self.feed(Response(quote_body(**{field: invalid}))), "swap_quote_invalid")
        for field in ("inAmount", "outAmount"):
            await self.assert_error(self.feed(Response(quote_body(**{field: "0"}))), "swap_quote_invalid")
        result = await self.request(self.feed(Response(quote_body(otherAmountThreshold="0"))))
        self.assertEqual(result.minimum_output_amount_atomic, 0)


if __name__ == "__main__":
    unittest.main()
