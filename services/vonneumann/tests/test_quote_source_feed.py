"""Jupiter + Solana source-time contract with fake HTTP only."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
import traceback
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network
from tests.test_feed_reliability import Response, SECRET, RPC_URL, SOL, JUP

with deny_network():
    from vonneumann.market import jupiter_feed as jupiter
    from vonneumann.market import solana_time as solana
    from vonneumann.market.feed import MarketFeedError
    from vonneumann.market.quote_freshness import validate_quote


def price_body(values):
    return {jupiter.TOKEN_MINTS[asset]: {"usdPrice": price, "blockId": slot}
            for asset, (price, slot) in values.items()}


class Clock:
    def __init__(self):
        self.wall, self.mono = 2_000_000_000.0, 100.0

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds

    def time(self):
        return self.wall

    def monotonic(self):
        return self.mono


class FakeSession:
    closed = False

    def __init__(self, clock, bodies, *, times=None, genesis=solana.MAINNET_GENESIS_HASH):
        self.clock, self.bodies = clock, list(bodies)
        self.times = times or {}
        self.genesis = genesis
        self.calls = []
        self.active = self.peak_active = 0
        self.rpc_transform = None
        self.block_enter = None

    def get(self, url, **options):
        self.calls.append(("GET", url, options))
        if not self.bodies:
            raise AssertionError("Unexpected fake price request")
        body = self.bodies.pop(0)
        return body if isinstance(body, Response) else Response(body)

    def post(self, url, **options):
        self.calls.append(("POST", url, options))
        request = options["json"]
        method = request["method"]
        result = self.genesis if method == "getGenesisHash" else self.times.get(request["params"][0], int(self.clock.wall))
        response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        if self.rpc_transform:
            response = self.rpc_transform(request, response)
        if isinstance(response, Response):
            return response
        owner = self

        class RPCResponse(Response):
            async def __aenter__(self):
                if method == "getBlockTime":
                    owner.active += 1
                    owner.peak_active = max(owner.peak_active, owner.active)
                    if owner.block_enter:
                        await owner.block_enter(request)
                    await asyncio.sleep(0)
                return self

            async def __aexit__(self, *args):
                if method == "getBlockTime":
                    owner.active -= 1
                return False

        return RPCResponse(response)

    async def close(self):
        self.closed = True

    def method_calls(self, method):
        return [c for c in self.calls if c[0] == "POST" and c[2]["json"]["method"] == method]


class QuoteSourceFeedTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.clock = Clock()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(jupiter, "time", self.clock))
        self.stack.enter_context(patch.object(solana, "time", self.clock))

    def feed(self, *bodies, times=None, genesis=solana.MAINNET_GENESIS_HASH):
        feed = jupiter.JupiterFeed(api_key=SECRET, rpc_url=RPC_URL)
        feed._session = FakeSession(self.clock, bodies, times=times, genesis=genesis)
        return feed

    async def failure(self, awaitable, code=None):
        with self.assertRaises(MarketFeedError) as raised:
            await awaitable
        if code:
            self.assertEqual(raised.exception.code, code)
        formatted = "".join(traceback.format_exception(raised.exception))
        self.assertNotIn(SECRET, formatted)
        self.assertNotIn(RPC_URL, formatted)
        return raised.exception

    def test_rpc_configuration_is_explicit_private_and_https_only(self):
        invalid = ("", "http://rpc.example.test", "https://user:secret@rpc.example.test",
                   "https://rpc.example.test/#secret", "https://rpc.example.test/#", "https://",
                   "https://rpc.example.test:99999", "https://rpc.example.test:0",
                   "https://rpc.example.test/ bad", "https://rpc.example.test/\x00",
                   "https://rpc.example.test/\\bad", None, 42)
        with patch.dict(jupiter.os.environ, {"VN_SOLANA_RPC_URL": ""}):
            for url in invalid:
                with self.subTest(url_type=type(url).__name__):
                    with self.assertRaises(MarketFeedError) as raised:
                        jupiter.JupiterFeed(api_key=SECRET, rpc_url=url)
                    self.assertEqual(raised.exception.code, "rpc_configuration")
            with patch.dict(jupiter.os.environ, {"VN_SOLANA_RPC_URL": RPC_URL}):
                self.assertEqual(jupiter.JupiterFeed(api_key=SECRET)._source_time._rpc_url, RPC_URL)
            with patch.dict(jupiter.os.environ, {"VN_SOLANA_RPC_URL": "invalid"}):
                self.assertEqual(jupiter.JupiterFeed(api_key=SECRET, rpc_url=RPC_URL)._source_time._rpc_url, RPC_URL)

    async def test_shared_slot_deduplicates_rpc_and_separates_credentials(self):
        feed = self.feed(price_body({SOL: (100, 77), JUP: (1, 77)}))
        ticks = await feed.get_ticks([SOL, JUP, SOL])
        self.assertEqual(feed.api_call_count, 1)
        self.assertEqual(feed._source_time.api_call_count, 2)
        self.assertEqual(len(feed._session.method_calls("getGenesisHash")), 1)
        self.assertEqual(len(feed._session.method_calls("getBlockTime")), 1)
        tick = ticks[SOL]
        self.assertEqual(tick.timestamp, self.clock.wall)
        self.assertEqual(tick.evidence.source_slot, 77)
        self.assertEqual(tick.evidence.received_at, self.clock.wall)
        self.assertEqual(tick.evidence.received_monotonic, self.clock.mono)
        self.assertEqual(tick.evidence.quote_currency, "USD")
        for method, url, options in feed._session.calls:
            self.assertFalse(options["allow_redirects"])
            if method == "POST":
                self.assertEqual(url, RPC_URL)
                self.assertNotIn(SECRET, str(options))
                self.assertNotIn("x-api-key", options["headers"])
        self.assertIs(await feed.get_tick(SOL), tick)
        self.assertEqual(len(feed._session.calls), 3)

    async def test_rpc_stream_is_bounded_before_allocating_the_full_body(self):
        feed = self.feed(price_body({SOL: (100, 77)}))
        class OversizedResponse(Response):
            delivered = 0
            async def iter_chunked(self, size):
                for _ in range(100):
                    self.delivered += size
                    yield b' ' * size
            async def json(self):
                raise AssertionError('RPC must consume bounded bytes')
        response = OversizedResponse()
        feed._session.rpc_transform = lambda request, body: response
        await self.failure(feed.get_ticks([SOL]), 'rpc_invalid')
        self.assertEqual(response.delivered, solana.MAX_RPC_RESPONSE_BYTES + 8192)
        self.assertEqual(feed._source_time._cache, {})
        self.assertEqual(feed._captures, {})

    async def test_rpc_duplicate_keys_invalid_utf8_and_constants_reject(self):
        for raw in (b'{"jsonrpc":"2.0","id":1,"result":1,"result":2}',
                    b'{"jsonrpc":"2.0","id":1,"result":"\xff"}',
                    b'{"jsonrpc":"2.0","id":1,"result":NaN}'):
            with self.subTest(body_hash=__import__('hashlib').sha256(raw).hexdigest()):
                feed = self.feed(price_body({SOL: (100, 77)}))
                feed._session.rpc_transform = lambda request, body: Response(raw)
                await self.failure(feed.get_ticks([SOL]), 'rpc_invalid')
                self.assertEqual(feed._source_time._cache, {})

    async def test_receipt_precedes_rpc_and_final_validation_includes_lookup_latency(self):
        feed = self.feed(price_body({SOL: (100, 77)}), times={77: int(self.clock.wall) - 29})
        async def latency(_request):
            self.clock.advance(2)
        feed._session.block_enter = latency
        error = await self.failure(feed.get_tick(SOL), "price_stale")
        self.assertEqual(error.valid_ticks, {})
        self.assertEqual(feed._cache, {})
        self.assertEqual(feed._source_slots, {})

    async def test_stale_http_success_exposes_only_current_fresh_siblings(self):
        feed = self.feed(price_body({SOL: (80, 77), JUP: (1, 78)}),
                         times={77: int(self.clock.wall), 78: int(self.clock.wall) - 31})
        error = await self.failure(feed.get_ticks([SOL, JUP]), "price_stale")
        self.assertEqual(set(error.valid_ticks), {SOL})
        self.assertEqual(error.valid_ticks[SOL].price, 80)
        self.assertEqual(feed._cache, {})
        self.assertEqual(feed._source_slots, {})

    async def test_public_provider_fixture_rejects_stale_source_despite_successful_price_response(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" /
                              "jupiter-source-times-20260930.json").read_text())
        self.clock.wall = fixture["received_at"]
        records = fixture["records"]
        body = price_body({row["asset"]: (row["usd_price"], row["source_slot"])
                           for row in records})
        times = {row["source_slot"]: row["source_timestamp"] for row in records}
        feed = self.feed(body, times=times)
        assets = [row["asset"] for row in records]
        self.assertEqual(set(assets), set(jupiter.TOKEN_MINTS))
        error = await self.failure(feed.get_ticks(assets), "price_stale")
        self.assertEqual(set(error.valid_ticks), set(assets) - {"PYTH/USDC"})
        self.assertEqual(len(error.valid_ticks), 7)
        self.assertIn(SOL, error.valid_ticks)
        self.assertEqual(feed._cache, {})
        self.assertEqual(feed._source_slots, {})
        self.assertEqual(len(feed._session.method_calls("getBlockTime")), 6)
        stale = next(row for row in records if row["asset"] == "PYTH/USDC")
        self.assertAlmostEqual(self.clock.wall - stale["source_timestamp"], 112.507, places=3)

    async def test_invalid_price_missing_slot_and_missing_asset_keep_valid_sibling(self):
        for bad in (None, {}, {"usdPrice": "not-a-number", "blockId": 78},
                    {"usdPrice": 1}, {"usdPrice": 1, "blockId": True},
                    {"usdPrice": 1, "blockId": 2**64}, {"usdPrice": 1, "blockId": -1},
                    {"usdPrice": 1, "blockId": "78"}):
            with self.subTest(bad_type=type(bad).__name__):
                body = price_body({SOL: (80, 77)})
                if bad is not None:
                    body[jupiter.TOKEN_MINTS[JUP]] = bad
                feed = self.feed(body)
                error = await self.failure(feed.get_ticks([SOL, JUP]))
                self.assertEqual(set(error.valid_ticks), {SOL})
                self.assertEqual(feed._cache, {})
                self.assertEqual(feed._source_slots, {})

    async def test_unknown_invalid_future_and_rpc_error_time_are_never_receipt_fallbacks(self):
        for result in (None, False, -1, 2**63, "2000000000", 2_000_000_000.0, 2_000_000_003):
            with self.subTest(result=result):
                feed = self.feed(price_body({SOL: (100, 77), JUP: (1, 78)}), times={77: result})
                error = await self.failure(feed.get_ticks([SOL, JUP]))
                self.assertEqual(set(error.valid_ticks), {JUP})
                self.assertEqual(feed._cache, {})

    async def test_wrong_genesis_cannot_resolve_or_cache_any_source_time(self):
        for genesis in ("devnet-fake-hash", None, {}, True):
            with self.subTest(genesis_type=type(genesis).__name__):
                feed = self.feed(price_body({SOL: (100, 77)}), genesis=genesis)
                await self.failure(feed.get_tick(SOL), "rpc_wrong_network")
                self.assertEqual(feed._session.method_calls("getBlockTime"), [])
                self.assertIsNone(feed._source_time._verified_session)
                self.assertEqual(feed._cache, {})

    async def test_rpc_protocol_ids_jsonrpc_errors_status_and_body_fail_closed_safely(self):
        transforms = [
            lambda req, body: {**body, "id": body["id"] + 1},
            lambda req, body: {**body, "id": str(body["id"])},
            lambda req, body: {**body, "id": True},
            lambda req, body: {**body, "jsonrpc": "1.0"},
            lambda req, body: {**body, "error": {"message": SECRET}},
            lambda req, body: [],
            lambda req, body: Response(error=ValueError(SECRET)),
        ]
        transforms += [lambda req, body, status=status: Response(status=status)
                       for status in (301, 302, 307, 401, 429, 503)]
        for transform in transforms:
            with self.subTest(transform=transforms.index(transform)):
                feed = self.feed(price_body({SOL: (100, 77)}))
                feed._session.rpc_transform = transform
                error = await self.failure(feed.get_tick(SOL))
                self.assertEqual(error.valid_ticks, {})
                self.assertEqual(feed._cache, {})

    async def test_block_rpc_error_is_isolated_to_its_slot(self):
        feed = self.feed(price_body({SOL: (100, 77), JUP: (1, 78)}))
        def transform(request, body):
            if request["method"] == "getBlockTime" and request["params"] == [78]:
                return {"jsonrpc": "2.0", "id": request["id"], "error": {"message": SECRET}}
            return body
        feed._session.rpc_transform = transform
        error = await self.failure(feed.get_ticks([SOL, JUP]), "rpc_invalid")
        self.assertEqual(set(error.valid_ticks), {SOL})

    async def test_partial_refresh_preserves_existing_quote_cache_and_watermarks_then_recovers(self):
        feed = self.feed(price_body({SOL: (100, 77), JUP: (1, 77)}),
                         price_body({SOL: (80, 78), JUP: (1, 79)}),
                         price_body({SOL: (81, 80), JUP: (1, 80)}), times={79: None})
        await feed.get_ticks([SOL, JUP])
        cache, watermarks = dict(feed._cache), dict(feed._source_slots)
        self.clock.advance(1)
        error = await self.failure(feed.get_ticks([SOL, JUP]), "source_time_unavailable")
        self.assertEqual(error.valid_ticks[SOL].price, 80)
        self.assertEqual(feed._cache, cache)
        self.assertEqual(feed._source_slots, watermarks)
        recovered = await feed.get_ticks([SOL, JUP])
        self.assertEqual(recovered[SOL].price, 81)
        self.assertEqual(feed._source_slots, {SOL: 80, JUP: 80})

    async def test_missing_source_slot_never_uses_token_creation_timestamp(self):
        body = {jupiter.TOKEN_MINTS[SOL]: {"usdPrice": 100, "createdAt": int(self.clock.wall)}}
        feed = self.feed(body)
        await self.failure(feed.get_tick(SOL), "source_time_invalid")
        self.assertEqual(feed._session.method_calls("getBlockTime"), [])
        self.assertEqual(feed._session.method_calls("getGenesisHash"), [])

    async def test_source_age_is_rechecked_inside_local_cache_ttl(self):
        self.clock.wall += 0.8
        body = price_body({SOL: (100, 77)})
        feed = self.feed(body, body, times={77: 1_999_999_971})
        first = await feed.get_tick(SOL)
        self.clock.advance(0.4)
        await self.failure(feed.get_tick(SOL), "price_stale")
        self.assertEqual(feed.api_call_count, 2)
        self.assertIs(feed._cache[SOL][1], first)

    async def test_cache_uses_monotonic_time_and_does_not_extend_source_age(self):
        body = price_body({SOL: (100, 77)})
        feed = self.feed(body, body, times={77: 1_999_999_970})
        first = await feed.get_tick(SOL)
        self.clock.mono += 0.5
        self.clock.wall -= 0.5
        await self.failure(feed.get_tick(SOL), "price_stale")
        self.assertEqual(feed._cache[SOL][0], 100)
        self.assertEqual(first.evidence.received_at, 2_000_000_000)

    async def test_refresh_preserves_effective_source_age_for_later_consumers(self):
        body = price_body({SOL: (100, 77)})
        feed = self.feed(body, body, times={77: 1_999_999_971})
        await feed.get_tick(SOL)
        self.clock.mono += 0.9
        self.clock.wall -= 0.9
        refreshed = await feed.get_tick(SOL)
        self.assertEqual(refreshed.evidence.received_at, self.clock.wall)
        self.assertAlmostEqual(refreshed.evidence.source_age_at_receipt, 29.9)
        self.clock.advance(0.2)
        with self.assertRaises(MarketFeedError) as raised:
            validate_quote(refreshed, wall_now=self.clock.wall, monotonic_now=self.clock.mono)
        self.assertEqual(raised.exception.code, "price_stale")

    async def test_newer_slot_with_unchanged_timestamp_cannot_reset_age_after_wall_rollback(self):
        feed = self.feed(price_body({SOL: (100, 77)}), price_body({SOL: (101, 78)}),
                         times={77: 1_999_999_970, 78: 1_999_999_970})
        await feed.get_tick(SOL)
        self.clock.mono += 1
        self.clock.wall -= 1
        await self.failure(feed.get_tick(SOL), "price_stale")
        self.assertEqual(feed._source_slots[SOL], 77)

    async def test_newer_source_timestamp_can_replace_an_expired_previous_quote(self):
        feed = self.feed(price_body({SOL: (100, 77)}), price_body({SOL: (101, 78)}),
                         times={77: 1_999_999_970, 78: 2_000_000_001})
        await feed.get_tick(SOL)
        self.clock.advance(1)
        refreshed = await feed.get_tick(SOL)
        self.assertEqual(refreshed.price, 101)
        self.assertEqual(refreshed.evidence.source_age_at_receipt, 0)

    async def test_same_slot_source_timestamp_revision_is_rejected(self):
        feed = self.feed(price_body({SOL: (100, 77)}), price_body({SOL: (101, 77)}))
        await feed.get_tick(SOL)
        self.clock.advance(30)
        await self.failure(feed.get_tick(SOL), "source_time_invalid")
        self.assertEqual(feed._cache[SOL][1].price, 100)

    async def test_same_slot_new_price_is_allowed_lower_slot_does_not_commit(self):
        feed = self.feed(price_body({SOL: (100, 77)}), price_body({SOL: (101, 77)}),
                         price_body({SOL: (102, 76)}))
        await feed.get_tick(SOL)
        self.clock.advance(1)
        self.assertEqual((await feed.get_tick(SOL)).price, 101)
        self.assertEqual(len(feed._session.method_calls("getGenesisHash")), 1)
        self.assertEqual(len(feed._session.method_calls("getBlockTime")), 1)
        old = dict(feed._cache)
        self.clock.advance(1)
        await self.failure(feed.get_tick(SOL), "source_slot_regressed")
        self.assertEqual(feed._source_slots[SOL], 77)
        self.assertEqual(feed._cache, old)

    async def test_identity_is_rechecked_on_a_replaced_http_session(self):
        feed = self.feed(price_body({SOL: (100, 77)}))
        await feed.get_tick(SOL)
        self.clock.advance(1)
        feed._session = FakeSession(self.clock, [price_body({SOL: (100, 78)})], genesis="wrong-network")
        await self.failure(feed.get_tick(SOL), "rpc_wrong_network")
        self.assertEqual(feed._source_slots[SOL], 77)

    async def test_lookup_concurrency_and_total_deadline_are_bounded(self):
        body = price_body({asset: (100, slot) for slot, asset in enumerate(jupiter.TOKEN_MINTS)})
        feed = self.feed(body)
        await feed.get_ticks(list(jupiter.TOKEN_MINTS))
        self.assertEqual(len(feed._session.method_calls("getBlockTime")), 8)
        self.assertEqual(feed._session.peak_active, 4)
        hanging = self.feed(price_body({SOL: (100, 77)}))
        entered = asyncio.Event()
        async def hang(_request):
            entered.set()
            await asyncio.Event().wait()
        hanging._session.block_enter = hang
        real_timeout = asyncio.timeout
        with patch.object(jupiter.asyncio, "timeout", side_effect=lambda seconds: real_timeout(0.08)) as timeout:
            await self.failure(hanging.get_tick(SOL), "rpc_unavailable")
        timeout.assert_called_once_with(5)
        self.assertTrue(entered.is_set())
        self.assertEqual(hanging._cache, {})
        self.assertEqual(hanging._source_slots, {})
        self.assertEqual(hanging._source_time._cache, {})

    async def test_slow_slot_deadline_preserves_resolved_sibling_and_cancels_request(self):
        feed = self.feed(price_body({SOL: (80, 77), JUP: (1, 78)}))
        cancelled = asyncio.Event()
        async def slow(request):
            if request["params"] == [78]:
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
        feed._session.block_enter = slow
        real_timeout = asyncio.timeout
        with patch.object(jupiter.asyncio, "timeout", side_effect=lambda seconds: real_timeout(0.08)):
            error = await self.failure(feed.get_ticks([SOL, JUP]), "rpc_unavailable")
        self.assertTrue(cancelled.is_set())
        self.assertEqual(set(error.valid_ticks), {SOL})
        self.assertEqual(error.valid_ticks[SOL].price, 80)
        self.assertEqual(feed._cache, {})
        self.assertEqual(feed._source_slots, {})

    async def test_price_http_deadline_is_bounded_before_any_source_lookup(self):
        class HangingPrice(Response):
            async def iter_chunked(self, size):
                await asyncio.Event().wait()
                yield b""  # Make this an async byte-stream iterator.
        feed = self.feed(HangingPrice())
        real_timeout = asyncio.timeout
        with patch.object(jupiter.asyncio, "timeout", side_effect=lambda seconds: real_timeout(0.01)):
            error = await self.failure(feed.get_tick(SOL), "price_unavailable")
        self.assertEqual(error.valid_ticks, {})
        self.assertEqual(feed._session.method_calls("getGenesisHash"), [])

    async def test_cancellation_propagates_and_does_not_commit_partial_quotes(self):
        feed = self.feed(price_body({SOL: (100, 77), JUP: (1, 78)}))
        async def cancel(request):
            if request["params"] == [78]:
                raise asyncio.CancelledError()
        feed._session.block_enter = cancel
        with self.assertRaises(asyncio.CancelledError):
            await feed.get_ticks([SOL, JUP])
        self.assertEqual(feed._cache, {})
        self.assertEqual(feed._source_slots, {})
        self.assertEqual(feed._source_time._cache, {})

    async def test_external_cancellation_drains_pending_lookup_and_keeps_caches_uncommitted(self):
        feed = self.feed(price_body({SOL: (100, 77), JUP: (1, 78)}))
        entered, cancelled = asyncio.Event(), asyncio.Event()
        async def wait_for_cancel(request):
            if request["params"] == [78]:
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
        feed._session.block_enter = wait_for_cancel
        operation = asyncio.create_task(feed.get_ticks([SOL, JUP]))
        await entered.wait()
        await asyncio.sleep(0)
        operation.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await operation
        self.assertTrue(cancelled.is_set())
        self.assertEqual(feed._cache, {})
        self.assertEqual(feed._source_slots, {})
        self.assertEqual(feed._source_time._cache, {})

    async def test_slot_cache_is_bounded_and_expires_without_changing_quote_age(self):
        feed = self.feed()
        resolver, session = feed._source_time, feed._session
        for start in range(0, 272, 8):
            resolved, errors = await resolver.resolve(session, list(range(start, start + 8)))
            self.assertEqual(len(resolved), 8)
            self.assertEqual(errors, {})
        self.assertEqual(len(resolver._cache), 256)
        self.assertNotIn(0, resolver._cache)
        self.assertEqual(len(session.method_calls("getGenesisHash")), 1)
        self.clock.advance(30)
        await resolver.resolve(session, [271])
        self.assertEqual(len(resolver._cache), 1)
        self.assertEqual(len(session.method_calls("getBlockTime")), 273)
        await self.failure(resolver.resolve(session, list(range(9))), "source_time_invalid")
