"""Offline regressions for actual V3 schema and completed source-minute fetching."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import traceback
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    import aiohttp
    from vonneumann.market import birdeye_candles as module
    from vonneumann.market.feed import MarketFeedError

SOL, JUP = "SOL/USDC", "JUP/USDC"
MINTS = {SOL: "So11111111111111111111111111111111111111112", JUP: "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"}
SECRET = "fake-birdeye-secret-never-display"
CUTOFF = 1_790_756_100


def row(stamp, *, asset=SOL, **changes):
    value = {"unix_time": stamp, "address": MINTS[asset], "o": 100, "h": 102,
             "l": 99, "c": 101, "v": 3, "v_usd": 301, "type": "1m", "currency": "usd"}
    value.update(changes)
    return value


def body(*items):
    return {"success": True, "data": {"is_scaled_ui_token": False, "items": list(items)}}


def recent(cutoff=CUTOFF, count=2, *, asset=SOL):
    return body(*(row(stamp, asset=asset) for stamp in range(cutoff - count * 60, cutoff, 60)))


class Response:
    def __init__(self, payload=None, *, status=200, error=None, before_json=None):
        self.payload, self.status, self.error = payload, status, error
        self.before_json = before_json
        self.content = self

    async def iter_chunked(self, size):
        if self.before_json:
            await self.before_json()
        if self.error is not None:
            raise self.error
        raw = self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()
        for offset in range(0, len(raw), size):
            yield raw[offset:offset + size]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        if self.before_json:
            await self.before_json()
        if self.error is not None:
            raise self.error
        return self.payload


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected HTTP request in candle test")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def close(self):
        self.closed = True


class BirdeyeCandlesTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.now = CUTOFF + module.COMPLETION_MARGIN_SECONDS
        self.enterContext(patch.object(module, "time", SimpleNamespace(time=lambda: self.now, monotonic=time.monotonic)))
        self.enterContext(patch.object(module, "REQUEST_SPACING_SECONDS", 0))

    def make_adapter(self, *responses, key=SECRET):
        adapter = module.BirdeyeCandles(key, MINTS)
        adapter._session = Session(*responses)
        return adapter

    async def failure(self, operation, code=None):
        with self.assertRaises(MarketFeedError) as caught:
            await operation
        if code:
            self.assertEqual(caught.exception.code, code)
        self.assertNotIn(SECRET, "".join(traceback.format_exception(caught.exception)))
        return caught.exception

    async def test_real_provider_fixture_parses_snake_case_and_excludes_forming_minute(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "birdeye-v3-candles-20260930.json").read_text())
        self.now = fixture["retrieved_at"]
        adapter = self.make_adapter(Response(fixture["response"]))
        candles = await adapter.get_candles([SOL], warmup=True)
        cutoff = int((self.now - 5) // 60) * 60
        self.assertEqual(len(candles), 10)
        self.assertEqual(candles[-1].start + 60, cutoff)
        self.assertLess(candles[-1].start, fixture["response"]["data"]["items"][-1]["unix_time"])
        self.assertEqual(candles[0].volume, fixture["response"]["data"]["items"][0]["v"])
        self.assertNotEqual(candles[0].volume, fixture["response"]["data"]["items"][0]["v_usd"])
        self.assertEqual((candles[0].source, candles[0].quote_currency, candles[0].volume_unit),
                         ("birdeye-ohlcv-v3", "USD", "base_token"))

    async def test_warmup_fetches_3660_minutes_once_with_pinned_safe_parameters(self):
        adapter = self.make_adapter(Response(recent(count=3660)))
        candles = await adapter.get_candles([SOL, SOL], warmup=True)
        self.assertEqual(len(candles), 3660)
        self.assertEqual(candles[0].start, CUTOFF - 3660 * 60)
        url, options = adapter._session.calls[0]
        self.assertEqual(url, module.BIRDEYE_CANDLES_URL)
        self.assertEqual(options["params"], {
            "address": MINTS[SOL], "type": "1m", "mode": "range", "time_from": CUTOFF - 3660 * 60,
            "time_to": CUTOFF, "currency": "usd", "chart_type": "price",
            "ui_amount_mode": "raw", "padding": "false",
        })
        self.assertEqual(options["headers"]["x-chain"], "solana")
        self.assertFalse(options["allow_redirects"])
        self.assertEqual(await adapter.get_candles([SOL]), candles)
        self.assertEqual(adapter.api_call_count, 1)

    async def test_completion_margin_boundary_and_cached_cutoff(self):
        self.now = CUTOFF + 4.999
        adapter = self.make_adapter(Response(recent(CUTOFF - 60)), Response(recent(CUTOFF, count=3)))
        old = await adapter.get_candles([SOL])
        self.assertEqual(old[-1].start + 60, CUTOFF - 60)
        self.now = CUTOFF + 5
        new = await adapter.get_candles([SOL])
        self.assertEqual(new[-1].start + 60, CUTOFF)
        self.now = CUTOFF + 64.999
        self.assertEqual(await adapter.get_candles([SOL]), new)
        self.assertEqual(adapter.api_call_count, 2)

    async def test_incremental_request_covers_elapsed_time_and_two_minute_overlap(self):
        adapter = self.make_adapter(Response(recent()), Response(recent(CUTOFF + 180, count=5)))
        await adapter.get_candles([SOL])
        self.now += 180
        candles = await adapter.get_candles([SOL])
        params = adapter._session.calls[-1][1]["params"]
        self.assertEqual((params["time_from"], params["time_to"]), (CUTOFF - 120, CUTOFF + 180))
        self.assertEqual(len(candles), 5)

    async def test_initial_short_history_can_warm_but_missing_incremental_prefix_fails(self):
        adapter = self.make_adapter(Response(recent(count=1)), Response(recent(CUTOFF + 60, count=1)))
        self.assertEqual(len(await adapter.get_candles([SOL], warmup=True)), 1)
        self.now += 60
        await self.failure(adapter.get_candles([SOL]), "candles_gap")
        self.assertEqual(adapter._cutoffs, {SOL: CUTOFF})

    async def test_new_token_overlap_never_demands_minutes_before_accepted_history_began(self):
        adapter = self.make_adapter(Response(recent(count=1)), Response(recent(CUTOFF + 60, count=2)))
        await adapter.get_candles([SOL], warmup=True)
        self.now += 60
        candles = await adapter.get_candles([SOL])
        self.assertEqual(len(candles), 2)
        self.assertEqual(adapter._session.calls[-1][1]["params"]["time_from"], CUTOFF - 60)

    async def test_empty_interior_and_trailing_gaps_are_explicit_without_padding(self):
        cases = [(body(), "candles_missing"),
                 (body(row(CUTOFF - 180), row(CUTOFF - 60)), "candles_gap"),
                 (body(row(CUTOFF - 120)), "candles_gap")]
        for payload, code in cases:
            with self.subTest(code=code):
                adapter = self.make_adapter(Response(payload))
                await self.failure(adapter.get_candles([SOL]), code)
                self.assertEqual(adapter._cutoffs, {})
                self.assertEqual(adapter._cache, {})

    async def test_unsorted_rows_and_identical_duplicates_normalize_without_volume_multiplication(self):
        adapter = self.make_adapter(Response(body(row(CUTOFF - 60), row(CUTOFF - 120), row(CUTOFF - 60))))
        candles = await adapter.get_candles([SOL])
        self.assertEqual([c.start for c in candles], [CUTOFF - 120, CUTOFF - 60])
        self.assertEqual(sum(c.volume for c in candles), 6)

    async def test_conflicting_duplicate_candles_are_rejected(self):
        payload = body(row(CUTOFF - 60), row(CUTOFF - 60, v=4))
        await self.failure(self.make_adapter(Response(payload)).get_candles([SOL]), "candles_revision")

    async def test_malformed_shapes_success_markers_and_missing_metadata_fail_closed(self):
        cases = [None, [], "bad", {}, {"success": 1, "data": {}}, {"success": False, "message": SECRET},
                 {"success": True, "data": []}, {"success": True, "data": {"items": []}}]
        for replacement in (None, 0, "false"):
            payload = recent()
            payload["data"]["is_scaled_ui_token"] = replacement
            cases.append(payload)
        for replacement in (None, {}, "bad", [None], [False], [[]]):
            payload = recent()
            payload["data"]["items"] = replacement
            cases.append(payload)
        for field in row(CUTOFF - 60):
            incomplete = row(CUTOFF - 60)
            del incomplete[field]
            cases.append(body(incomplete))
        for payload in cases:
            with self.subTest(payload_type=type(payload).__name__):
                await self.failure(self.make_adapter(Response(payload)).get_candles([SOL]), "candles_invalid")

    async def test_numeric_type_finiteness_and_ohlc_bounds_are_strict(self):
        for field in ("o", "h", "l", "c", "v", "v_usd"):
            values = (None, False, True, "100", float("nan"), float("inf"), -1)
            if field in ("o", "h", "l", "c"):
                values += (0,)
            for value in values:
                with self.subTest(field=field, kind=type(value).__name__):
                    await self.failure(self.make_adapter(Response(body(row(CUTOFF - 60, **{field: value})))).get_candles([SOL]),
                                       "candles_invalid")
        for changes in ({"h": 100}, {"l": 101}, {"o": 103}, {"c": 98}):
            await self.failure(self.make_adapter(Response(body(row(CUTOFF - 60, **changes)))).get_candles([SOL]),
                               "candles_invalid")
        candles = await self.make_adapter(Response(body(row(CUTOFF - 60, v=0, v_usd=0)))).get_candles([SOL])
        self.assertEqual(candles[0].volume, 0)

    async def test_timestamp_and_source_identity_mismatches_fail_closed(self):
        changes = [{"unix_time": stamp} for stamp in (True, None, 0, -60, float(CUTOFF - 60),
                                                      CUTOFF - 59, CUTOFF + 60)]
        changes += [{"address": MINTS[JUP]}, {"type": "15m"}, {"currency": "native"},
                    {"unixTime": CUTOFF - 60, "unix_time": None}]
        for change in changes:
            await self.failure(self.make_adapter(Response(body(row(CUTOFF - 60, **change)))).get_candles([SOL]),
                               "candles_invalid")

    async def test_forming_boundary_candle_is_validated_before_it_is_ignored(self):
        valid = recent()["data"]["items"]
        adapter = self.make_adapter(Response(body(*valid, row(CUTOFF))))
        self.assertEqual(len(await adapter.get_candles([SOL])), 2)
        await self.failure(self.make_adapter(Response(body(*valid, row(CUTOFF, v=False)))).get_candles([SOL]),
                           "candles_invalid")

    async def test_http_failures_redirects_transport_and_json_errors_do_not_leak_or_fallback(self):
        cases = [Response(status=status) for status in (401, 403, 429, 500, 503, 301, 302, 307)]
        cases += [aiohttp.ClientConnectionError(SECRET), asyncio.TimeoutError(SECRET),
                  Response(error=ValueError(SECRET))]
        for response in cases:
            adapter = self.make_adapter(Response(recent()), response)
            await adapter.get_candles([SOL])
            previous_cache = deepcopy(adapter._cache)
            self.now += 60
            await self.failure(adapter.get_candles([SOL]))
            self.assertEqual(adapter._cache, previous_cache)
            self.assertEqual(adapter._cutoffs, {SOL: CUTOFF})
            self.now = CUTOFF + 5

    async def test_rate_limit_has_specific_safe_code(self):
        await self.failure(self.make_adapter(Response(status=429)).get_candles([SOL]), "candles_rate_limited")

    async def test_partial_asset_failure_commits_no_watermarks_or_partial_cache(self):
        adapter = self.make_adapter(Response(recent()), Response(status=503),
                                    Response(recent()), Response(recent(asset=JUP)))
        await self.failure(adapter.get_candles([SOL, JUP]))
        self.assertEqual((adapter._cutoffs, adapter._cache), ({}, {}))
        candles = await adapter.get_candles([SOL, JUP])
        self.assertEqual({c.asset for c in candles}, {SOL, JUP})
        self.assertEqual(adapter.api_call_count, 4)
        self.assertEqual(adapter._cutoffs, {SOL: CUTOFF, JUP: CUTOFF})

    async def test_clock_rollback_and_excessive_backlog_never_return_cached_history(self):
        adapter = self.make_adapter(Response(recent()))
        await adapter.get_candles([SOL])
        self.now -= 60
        await self.failure(adapter.get_candles([SOL]), "candles_clock_invalid")
        self.now = CUTOFF + 5000 * 60 + 5
        await self.failure(adapter.get_candles([SOL]), "candles_backlog")
        self.assertEqual(adapter.api_call_count, 1)

    async def test_batch_uses_entry_cutoff_even_if_clock_advances_while_awaiting_provider(self):
        async def advance():
            self.now += 120
        adapter = self.make_adapter(Response(recent(), before_json=advance), Response(recent(asset=JUP)))
        candles = await adapter.get_candles([SOL, JUP])
        self.assertEqual(max(c.start + 60 for c in candles), CUTOFF)
        self.assertTrue(all(call[1]["params"]["time_to"] == CUTOFF for call in adapter._session.calls))

    async def test_empty_unknown_missing_config_and_oversize_batches_do_not_contact_provider(self):
        adapter = self.make_adapter(key="")
        self.assertEqual(await adapter.get_candles([]), [])
        await self.failure(adapter.get_candles([SOL]), "candles_configuration")
        await self.failure(adapter.get_candles([SECRET]), "unsupported_asset")
        self.assertEqual(adapter._session.calls, [])
        adapter = module.BirdeyeCandles(SECRET, {str(i): str(i) for i in range(9)})
        await self.failure(adapter.get_candles(list(adapter._token_mints)), "candles_batch_limit")
        self.assertIsNone(adapter._session)

    async def test_session_configuration_is_bounded_and_separate_without_proxy_inheritance(self):
        adapter = module.BirdeyeCandles(SECRET, MINTS)
        session = Session(Response(recent()))
        with patch.object(module.aiohttp, "ClientSession", return_value=session) as factory:
            await adapter.get_candles([SOL])
        self.assertEqual(factory.call_args.kwargs["timeout"].total, 5)
        self.assertFalse(factory.call_args.kwargs["trust_env"])
        await adapter.close()
        self.assertTrue(session.closed)

    async def test_whole_batch_timeout_is_bounded_and_does_not_commit(self):
        async def hang():
            await asyncio.Event().wait()
        adapter = self.make_adapter(Response(recent(), before_json=hang))
        with patch.object(module, "BATCH_TIMEOUT_SECONDS", 0.01):
            await self.failure(adapter.get_candles([SOL]), "candles_unavailable")
        self.assertEqual((adapter._cutoffs, adapter._cache), ({}, {}))

    async def test_cancellation_propagates_without_committing(self):
        adapter = self.make_adapter(asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await adapter.get_candles([SOL])
        self.assertEqual((adapter._cutoffs, adapter._cache), ({}, {}))

    async def test_provider_record_cap_and_scaled_marker_are_validated(self):
        too_many = body(*[row(CUTOFF - 60)] * 5001)
        await self.failure(self.make_adapter(Response(too_many)).get_candles([SOL]), "candles_invalid")
        payload = recent()
        payload["data"]["is_scaled_ui_token"] = True
        self.assertEqual(len(await self.make_adapter(Response(payload)).get_candles([SOL])), 2)
