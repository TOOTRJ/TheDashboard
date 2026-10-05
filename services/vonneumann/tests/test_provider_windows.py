"""Offline complete-window acquisition against the real exact source contract."""
from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
import hashlib
import math
import time as real_time
import traceback
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from tests.security_support import OfflineTestMixin, deny_network
from tests.test_birdeye_candles import Response, Session, MINTS, row, body
from tests.test_exact_provider_feeds import Number, wire

with deny_network():
    from vonneumann.market import birdeye_candles as module
    from vonneumann.market import jupiter_feed as jupiter
    from vonneumann.market import provider_contract as source
    from vonneumann.market.feed import MarketFeedError
    from vonneumann.core import exact_lifecycle as kernel
    from vonneumann.core.provider_lifecycle import ProviderLifecycleConfig
    from vonneumann.db.provider_owner import ProviderAdmissionOwner
    from vonneumann.db.command_protocol import PreparedCommand
    from vonneumann.db.command_repository import CommandRepository

from tests.test_exact_rehearsal import OWNER, RUN, WORKER
from tests.test_provider_contract import EPOCH, raw_capture
from tests.test_transition_coordinator import CommittingTransport


END = 1_790_755_200
SECRET = "fake-provider-window-secret-must-not-leak"


def response_bytes(end=END, *, count=915, changes=None, extra=(), scaled=False, multiplier=None):
    items = [row(stamp, c=Number("101.000000000000000001"))
             for stamp in range(end - count * 60, end, 60)]
    for index, values in (changes or {}).items():
        items[index].update(values)
    payload = body(*items, *extra)
    payload["data"]["is_scaled_ui_token"] = scaled
    if multiplier is not None:
        payload["data"]["multiplier"] = Number(multiplier)
    return wire(payload).encode()


class ProviderWindowTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.wall, self.mono = END + 10.0, 1000.0
        self.enterContext(patch.object(module, "time", SimpleNamespace(
            time=lambda: self.wall, monotonic=lambda: self.mono)))

    def adapter(self, *responses, key=SECRET, mints=MINTS):
        adapter = module.BirdeyeCandles(key, mints)
        adapter._session = Session(*responses)
        self.addAsyncCleanup(adapter.close)
        return adapter

    def age(self, amount):
        self.wall += amount
        self.mono += amount

    async def failure(self, awaitable, code):
        with self.assertRaises(MarketFeedError) as caught:
            await awaitable
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn(SECRET, "".join(traceback.format_exception(caught.exception)))
        return caught.exception

    def build(self, rows, *, bars=(), seed=True):
        return source.build_history(rows, prior_bars=list(bars), seed=seed,
            wall_us=source.clock_us(self.wall, upper=True),
            monotonic_us=source.clock_us(self.mono, upper=True))

    def assert_legacy_empty(self, adapter):
        self.assertEqual(adapter._cutoffs, {})
        self.assertEqual(adapter._first_starts, {})
        self.assertEqual(adapter._cache, {})
        self.assertEqual(adapter._exact_cache, {})
        self.assertEqual(adapter._accepted_fingerprints, {})

    async def test_seed_is_one_fresh_exact_document_accepted_by_v5_contract(self):
        raw = response_bytes()
        adapter = self.adapter(Response(raw))
        rows = await adapter.get_provider_history()
        self.assertIs(type(rows), tuple)
        self.assertEqual(len(rows), 915)
        self.assertEqual((rows[0].start, rows[-1].end), (END - 915 * 60, END))
        self.assertEqual({row.asset for row in rows}, {"SOL/USD"})
        self.assertEqual({row.mint for row in rows}, {source.MINT})
        self.assertTrue(all(row.document is rows[0].document for row in rows))
        document = rows[0].document
        self.assertEqual(document.raw_body, raw)
        self.assertEqual(document.response_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual((document.received_at, document.received_monotonic), (self.wall, self.mono))
        self.assertEqual(rows[0].close, "101.000000000000000001")
        self.assertNotIn(SECRET, repr(rows))
        with self.assertRaises(FrozenInstanceError):
            rows[0].close = "999"
        self.assertEqual(len(source.derive_bars(self.build(rows))), 61)
        url, options = adapter._session.calls[0]
        self.assertEqual(url, module.BIRDEYE_CANDLES_URL)
        self.assertEqual(options["params"], {
            "address": source.MINT, "type": "1m", "mode": "range",
            "time_from": END - 915 * 60, "time_to": END, "currency": "usd",
            "chart_type": "price", "ui_amount_mode": "raw", "padding": "false",
        })
        self.assertEqual(options["headers"]["x-chain"], "solana")
        self.assertFalse(options["allow_redirects"])
        self.assertEqual(options["timeout"].total, 5)
        self.assertEqual(adapter.api_call_count, 1)
        self.assert_legacy_empty(adapter)

    async def test_increment_owns_full_previous_bar_overlap_and_exactly_one_new_bar(self):
        adapter = self.adapter(Response(response_bytes()), Response(response_bytes(END + 900, count=30)))
        seed = await adapter.get_provider_history()
        bars = source.derive_bars(self.build(seed))
        self.age(900)
        rows = await adapter.get_provider_history(previous_end=END)
        self.assertEqual(len(rows), 30)
        self.assertEqual((rows[0].start, rows[-1].end), (END - 900, END + 900))
        bundle = self.build(rows, bars=bars, seed=False)
        self.assertEqual(len(bundle["minutes"]), 15)
        self.assertEqual(len(bundle["documents"]), 1)
        self.assertEqual(source.derive_bars(bundle)[0][0], END + 900)
        self.assert_legacy_empty(adapter)

    async def test_actual_owner_bootstrap_and_decision_accept_fresh_feed_windows(self):
        sequence = 90_000_000
        def identity():
            nonlocal sequence
            sequence += 1
            return str(UUID(int=sequence))
        def allocations(generation):
            return {"ids":tuple(identity() for _ in range(9)),
                    "names":tuple((generation, f"Window-{generation}-{i}") for i in range(8)),
                    "command_id":identity()}
        transport = CommittingTransport()
        repository = CommandRepository(transport, OWNER, RUN, WORKER, monotonic=lambda:self.mono)
        config = ProviderLifecycleConfig(kernel.ExactLifecycleConfig(
            "genetic_algorithm", OWNER, RUN, asset="SOL/USD"), EPOCH)
        await repository.submit(PreparedCommand.create(OWNER, RUN, WORKER,
            config.run_configuration(), config.initial_cash, command_id=identity()))
        owner = ProviderAdmissionOwner(repository, transport, config,
            wall_clock=lambda:self.wall, monotonic=lambda:self.mono)
        await owner.heartbeat()
        events = []
        async def publish(event):
            events.append(event)
        adapter = self.adapter(Response(response_bytes()), Response(response_bytes(END+900, count=30)))
        await owner.bootstrap(await adapter.get_provider_history(), **allocations(0))
        await owner.publish_pending(publish)
        self.assertEqual(owner.installed_state.to_dict()["engine"]["ema"]["count"], 61)
        for _ in range(45):
            self.age(20)
            await owner.heartbeat()
        capture = raw_capture(block=345_678_901, price="101", source_second=int(self.wall)-2,
                              wall=self.wall-1, mono=self.mono-1)
        ticket = owner.capture_quote(capture)
        await owner.protect(ticket, command_id=identity())
        await owner.publish_pending(publish)
        cursor = owner.installed_state.to_dict()["source"]["bars"][-1][0]
        rows = await adapter.get_provider_history(previous_end=cursor)
        await owner.decide(ticket, rows, **allocations(1))
        await owner.publish_pending(publish)
        state = owner.installed_state.to_dict()
        self.assertEqual(state["source"]["bars"][-1][0], END+900)
        self.assertEqual(state["engine"]["ema"]["count"], 62)
        self.assertEqual(state["engine"]["cohort"]["phase"], "evaluating")
        self.assertEqual(state["positions"], [])
        self.assertTrue(owner.accepting)
        self.assertEqual(len({event["event_id"] for event in events}), len(events))

    async def test_retained_overlap_revision_remains_visible_to_owner_contract(self):
        adapter = self.adapter(Response(response_bytes()), Response(response_bytes(
            END + 900, count=30, changes={0:{"c": Number("101.000000000000000002")}})))
        bars = source.derive_bars(self.build(await adapter.get_provider_history()))
        self.age(900)
        rows = await adapter.get_provider_history(previous_end=END)
        with self.assertRaises(source.ProviderSourceError):
            self.build(rows, bars=bars, seed=False)
        self.assertEqual(rows[0].close, "101.000000000000000002")

    async def test_same_cursor_between_boundaries_returns_empty_without_http(self):
        adapter = self.adapter()
        self.assertEqual(await adapter.get_provider_history(previous_end=END), ())
        self.age(880)
        self.assertEqual(await adapter.get_provider_history(previous_end=END), ())
        self.assertEqual(adapter._session.calls, [])
        self.assertEqual(adapter.api_call_count, 0)

    async def test_repeated_seed_requests_are_fresh_without_legacy_cache_reuse(self):
        raw = response_bytes()
        adapter = self.adapter(Response(raw), Response(raw))
        first = await adapter.get_provider_history()
        self.age(.2)
        second = await adapter.get_provider_history()
        self.assertIsNot(first[0].document, second[0].document)
        self.assertEqual(first[0].document.received_at, END + 10)
        self.assertEqual(second[0].document.received_at, self.wall)
        self.assertEqual(len(adapter._session.calls), 2)

    async def test_exact_five_second_completion_boundary_does_not_round_up(self):
        adapter = self.adapter(Response(response_bytes(END + 900, count=30)))
        self.wall = math.nextafter(float(END + 905), -math.inf)
        self.assertEqual(await adapter.get_provider_history(previous_end=END), ())
        self.wall = float(END + 905)
        rows = await adapter.get_provider_history(previous_end=END)
        self.assertEqual(rows[-1].end, END + 900)
        self.assertEqual(len(adapter._session.calls), 1)

    async def test_invalid_cursor_rejects_before_request(self):
        for cursor in (True, False, "1790755200", float(END), 0, -900, END + 1, 10_000_000_800):
            with self.subTest(cursor=cursor):
                adapter = self.adapter()
                await self.failure(adapter.get_provider_history(previous_end=cursor), "candles_cursor_invalid")
                self.assertEqual(adapter._session.calls, [])

    async def test_future_cursor_and_multi_bar_backlog_reject_without_io(self):
        for cursor, code in ((END + 900, "candles_clock_invalid"),
                             (END - 1800, "candles_backlog")):
            with self.subTest(cursor=cursor):
                adapter = self.adapter()
                await self.failure(adapter.get_provider_history(previous_end=cursor), code)
                self.assertEqual(adapter._session.calls, [])

    async def test_key_and_pinned_mint_are_required_before_request(self):
        for options in ({"key": ""}, {"key":"  "}, {"mints":{}},
                        {"mints":{"SOL/USDC":MINTS["JUP/USDC"]}}):
            with self.subTest(options=options):
                adapter = self.adapter(**options)
                await self.failure(adapter.get_provider_history(), "candles_configuration")
                self.assertEqual(adapter._session.calls, [])

    async def test_usd_registry_identity_is_supported(self):
        adapter = self.adapter(Response(response_bytes()), mints={"SOL/USD":source.MINT})
        self.assertEqual((await adapter.get_provider_history())[0].asset, "SOL/USD")

    async def test_lock_wait_crossing_boundary_rejects_before_request(self):
        adapter = self.adapter()
        await adapter._lock.acquire()
        task = asyncio.create_task(adapter.get_provider_history())
        await asyncio.sleep(0)
        self.age(900)
        adapter._lock.release()
        await self.failure(task, "candles_window_changed")
        self.assertEqual(adapter._session.calls, [])

    async def test_response_crossing_boundary_does_not_relabel_old_request(self):
        async def advance():
            self.age(900)
        adapter = self.adapter(Response(response_bytes(), before_json=advance))
        await self.failure(adapter.get_provider_history(), "candles_window_changed")
        self.assertEqual(adapter._session.calls[0][1]["params"]["time_to"], END)
        self.assert_legacy_empty(adapter)

    async def test_parse_crossing_boundary_rejects_before_return(self):
        original = module.parse_candle_records
        def slow_parse(*args, **kwargs):
            parsed = original(*args, **kwargs)
            self.age(900)
            return parsed
        adapter = self.adapter(Response(response_bytes()))
        with patch.object(module, "parse_candle_records", side_effect=slow_parse):
            await self.failure(adapter.get_provider_history(), "candles_window_changed")

    async def test_parse_consuming_receipt_budget_rejects_before_return(self):
        original = module.parse_candle_records
        def slow_parse(*args, **kwargs):
            parsed = original(*args, **kwargs)
            self.age(5)
            return parsed
        adapter = self.adapter(Response(response_bytes()))
        with patch.object(module, "parse_candle_records", side_effect=slow_parse):
            await self.failure(adapter.get_provider_history(), "candles_stale")

    async def test_response_clock_rollback_rejects_both_clock_types(self):
        for clock in ("wall", "mono"):
            with self.subTest(clock=clock):
                self.wall, self.mono = END + 10.0, 1000.0
                async def rollback():
                    setattr(self, clock, getattr(self, clock) - 1)
                adapter = self.adapter(Response(response_bytes(), before_json=rollback))
                await self.failure(adapter.get_provider_history(), "candles_clock_invalid")

    async def test_invalid_clocks_reject_without_http(self):
        for value in (True, float("nan"), float("inf"), -1, "bad", 10**17):
            with self.subTest(value=value):
                self.wall, self.mono = value, 1000
                adapter = self.adapter()
                await self.failure(adapter.get_provider_history(), "candles_clock_invalid")
                self.assertEqual(adapter._session.calls, [])

    async def test_close_latches_new_api_and_does_not_reopen_session(self):
        adapter = self.adapter()
        await adapter.close()
        with patch.object(adapter, "_get_session", new=AsyncMock()) as get_session:
            await self.failure(adapter.get_provider_history(), "candles_closed")
            await self.failure(adapter.get_provider_history(previous_end=END), "candles_closed")
        get_session.assert_not_awaited()

    async def test_close_during_response_rejects_retained_data(self):
        adapter = None
        async def close():
            await adapter.close()
        adapter = self.adapter(Response(response_bytes(), before_json=close))
        await self.failure(adapter.get_provider_history(), "candles_closed")
        self.assert_legacy_empty(adapter)

    async def test_cancellation_during_body_preserves_no_cursor_and_retry_is_fresh(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def block():
            entered.set()
            await release.wait()
        adapter = self.adapter(Response(response_bytes(), before_json=block), Response(response_bytes()))
        task = asyncio.create_task(adapter.get_provider_history())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assert_legacy_empty(adapter)
        rows = await adapter.get_provider_history()
        self.assertEqual(len(rows), 915)
        self.assertEqual(len(adapter._session.calls), 2)

    async def test_total_timeout_includes_shared_lock_wait(self):
        adapter = self.adapter()
        await adapter._lock.acquire()
        try:
            with patch.object(module, "REQUEST_TIMEOUT_SECONDS", .01):
                await self.failure(adapter.get_provider_history(), "candles_unavailable")
        finally:
            adapter._lock.release()
        self.assertEqual(adapter._session.calls, [])

    async def test_body_suppressing_deadline_cancellation_cannot_return_fresh_rows(self):
        suppressed = []
        async def suppress_cancellation():
            try:
                await asyncio.sleep(.1)
            except asyncio.CancelledError:
                suppressed.append(True)
        adapter = self.adapter(Response(response_bytes(), before_json=suppress_cancellation))
        with patch.object(module, "REQUEST_TIMEOUT_SECONDS", .01):
            await self.failure(adapter.get_provider_history(), "candles_unavailable")
        self.assertEqual(suppressed, [True])
        self.assert_legacy_empty(adapter)
        self.assertEqual(adapter.api_call_count, 1)

    async def test_synchronous_parse_overrunning_deadline_rejects_despite_frozen_receipt_clock(self):
        original = module.parse_candle_records
        parsed = []
        def slow_parse(*args, **kwargs):
            rows = original(*args, **kwargs)
            parsed.append(True)
            real_time.sleep(.3)
            return rows
        adapter = self.adapter(Response(response_bytes(END, count=30)))
        with (patch.object(module, "REQUEST_TIMEOUT_SECONDS", .2),
              patch.object(module, "parse_candle_records", side_effect=slow_parse)):
            await self.failure(adapter.get_provider_history(previous_end=END-900), "candles_unavailable")
        self.assertEqual(parsed, [True])
        self.assert_legacy_empty(adapter)

    async def test_request_middleware_rejects_second_transport_attempt(self):
        adapter = self.adapter(Response(response_bytes()))
        await adapter.get_provider_history()
        middleware = adapter._session.calls[0][1]["middlewares"][0]
        handler = AsyncMock(return_value=object())
        await middleware(object(), handler)
        await self.failure(middleware(object(), handler), "candles_unavailable")
        self.assertEqual(handler.await_count, 1)

    async def test_http_errors_and_secret_exception_are_sanitized_without_cache_fallback(self):
        for response, code in ((Response(status=429), "candles_rate_limited"),
                               (Response(status=500), "candles_unavailable"),
                               (Response(status=302), "candles_unavailable"),
                               (Response(error=RuntimeError(SECRET)), "candles_invalid")):
            with self.subTest(code=code):
                adapter = self.adapter(response)
                await self.failure(adapter.get_provider_history(), code)
                self.assert_legacy_empty(adapter)

    async def test_short_seed_and_partial_increment_are_rejected_without_stitching(self):
        for raw, cursor in ((response_bytes(count=914), None),
                            (response_bytes(count=15), END - 900)):
            with self.subTest(cursor=cursor):
                adapter = self.adapter(Response(raw))
                await self.failure(adapter.get_provider_history(previous_end=cursor), "candles_gap")
                self.assert_legacy_empty(adapter)

    async def test_missing_interior_minute_and_invalid_forming_row_reject(self):
        items = [row(stamp) for stamp in range(END - 915 * 60, END, 60)]
        del items[50]
        adapter = self.adapter(Response(body(*items)))
        await self.failure(adapter.get_provider_history(), "candles_gap")
        adapter = self.adapter(Response(response_bytes(extra=(row(END, c=-1),))))
        await self.failure(adapter.get_provider_history(), "candles_invalid")

    async def test_valid_inclusive_boundary_is_validated_and_excluded_future_row_rejects(self):
        adapter = self.adapter(Response(response_bytes(extra=(row(END),))))
        rows = await adapter.get_provider_history()
        self.assertEqual(len(rows), 915)
        self.assertEqual(rows[-1].end, END)
        adapter = self.adapter(Response(response_bytes(extra=(row(END+60),))))
        await self.failure(adapter.get_provider_history(), "candles_invalid")

    async def test_scaled_multiplier_and_wrong_mint_are_rejected(self):
        for raw in (response_bytes(scaled=True), response_bytes(multiplier="2"),
                    response_bytes(changes={0:{"address":MINTS["JUP/USDC"]}})):
            with self.subTest(response_hash=hashlib.sha256(raw).hexdigest()):
                await self.failure(self.adapter(Response(raw)).get_provider_history(), "candles_invalid")

    async def test_legacy_caches_and_cutoffs_are_preserved_on_provider_read(self):
        adapter = self.adapter(Response(response_bytes(count=2)), Response(response_bytes()))
        legacy = await adapter.get_exact_candles(["SOL/USDC"])
        snapshot = (dict(adapter._cutoffs), dict(adapter._first_starts), dict(adapter._cache),
                    dict(adapter._exact_cache), dict(adapter._accepted_fingerprints))
        rows = await adapter.get_provider_history()
        self.assertEqual(len(rows), 915)
        self.assertEqual(snapshot, (adapter._cutoffs, adapter._first_starts, adapter._cache,
                                    adapter._exact_cache, adapter._accepted_fingerprints))
        self.assertIs((await adapter.get_exact_candles(["SOL/USDC"]))[0], legacy[0])

    async def test_jupiter_delegation_passes_authoritative_cursor_without_price_request(self):
        feed = jupiter.JupiterFeed(api_key=SECRET, rpc_url="https://rpc.example.test")
        self.addAsyncCleanup(feed.close)
        sentinel = (object(),)
        feed._candles.get_provider_history = AsyncMock(return_value=sentinel)
        with patch.object(feed, "_get_session", new=AsyncMock()) as price_session:
            self.assertIs(await feed.get_provider_history(previous_end=END), sentinel)
        feed._candles.get_provider_history.assert_awaited_once_with(previous_end=END)
        price_session.assert_not_awaited()
        self.assertEqual(feed.api_call_count, 0)
