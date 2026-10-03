"""Raw-byte exact numeric capture and credential-free request provenance."""
from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, Inexact, Rounded, localcontext
import hashlib
import json
import unittest

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.market.provider_evidence import (
        MAX_DOCUMENT_BYTES, MAX_NODES, PARSER_POLICY, ProviderDocument,
        ProviderEvidenceError, bounded_response_body, decimal_text,
    )

SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JUPITER = "jupiter-price-v3"
BIRDEYE = "birdeye-ohlcv-v3"
SECRET = "private-provider-body-or-authentication-detail"


def parameters():
    return {"address": SOL, "type": "1m", "mode": "range", "time_from": 60,
            "time_to": 180, "currency": "usd", "chart_type": "price",
            "ui_amount_mode": "raw", "padding": "false"}


def capture(raw=b'{"price":1.2300}', *, provider=JUPITER, params=None, **clocks):
    params = ({"ids": SOL} if provider == JUPITER else parameters()) if params is None else params
    return ProviderDocument.capture(provider, params, raw, clocks.get("received_at", 100.25),
                                    clocks.get("received_monotonic", 20.5))


class ProviderEvidenceTests(OfflineTestMixin, unittest.TestCase):
    def reject(self, operation):
        with self.assertRaises(ProviderEvidenceError) as caught:
            operation()
        self.assertEqual(str(caught.exception), "Provider evidence validation failed.")

    def test_original_bytes_and_exact_numeric_tokens_survive_independent_decode(self):
        raw = b'{ "integer":9007199254740993,"float":1.2300,"exponent":12.3e-2,"items":[true,null] }'
        document = capture(raw)
        self.assertIs(document.raw_body, raw)
        self.assertEqual(document.response_sha256, hashlib.sha256(raw).hexdigest())
        tree = document.decode()
        self.assertIs(type(tree["integer"]), int)
        self.assertEqual(tree["integer"], 9007199254740993)
        self.assertIs(type(tree["float"]), Decimal)
        self.assertEqual(tree["float"].as_tuple(), Decimal("1.2300").as_tuple())
        self.assertEqual(decimal_text(tree["exponent"]), "0.123")
        tree["items"].append(SECRET)
        self.assertEqual(document.decode()["items"], [True, None])

    def test_distinct_decimals_that_share_binary64_remain_distinct(self):
        values = capture(b'[1.00000000000000001,1.00000000000000002]').decode()
        self.assertEqual(float(values[0]), float(values[1]))
        self.assertNotEqual(values[0], values[1])
        self.assertEqual([decimal_text(v) for v in values], ["1.00000000000000001", "1.00000000000000002"])

    def test_request_and_manifest_are_canonical_detached_and_safe(self):
        params = parameters()
        document = capture(provider=BIRDEYE, params=params)
        params["address"] = SECRET
        manifest = document.manifest()
        self.assertEqual(manifest["request"], {"method": "GET", "endpoint": "https://public-api.birdeye.so/defi/v3/ohlcv", "chain": "solana", "parameters": parameters()})
        self.assertEqual(manifest["parser_policy"], PARSER_POLICY)
        expected = json.dumps(manifest["request"], sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
        self.assertEqual(document.request, expected)
        self.assertEqual(manifest["request_sha256"], hashlib.sha256(expected).hexdigest())
        self.assertNotIn("raw_body", manifest)
        self.assertNotIn("headers", manifest)
        manifest["request"]["parameters"]["address"] = SECRET
        document.parameters["address"] = SECRET
        self.assertEqual(document.parameters["address"], SOL)

    def test_frozen_document_repr_does_not_disclose_raw_body(self):
        document = capture(json.dumps({"private": SECRET}).encode())
        with self.assertRaises(FrozenInstanceError):
            document.raw_body = b"null"
        self.assertNotIn(SECRET, repr(document))
        for raw in (bytearray(b"null"), memoryview(b"null"), "null"):
            self.reject(lambda: capture(raw))

    def test_direct_constructor_revalidates_metadata_body_and_policy(self):
        document = capture()
        for changes in ({"parser_policy": "unreviewed"}, {"provider": "other"},
                        {"request": b'{"headers":{"Authorization":"secret"}}'},
                        {"request": document.request + b" "}, {"raw_body": b'{"a":1,"a":2}'},
                        {"received_at": True}, {"received_monotonic": float("nan")}):
            with self.subTest(fields=list(changes)):
                self.reject(lambda: replace(document, **changes))
        wrong = json.loads(document.request)
        wrong["endpoint"] = "https://private.invalid/secret"
        self.reject(lambda: replace(document, request=json.dumps(wrong).encode()))
        wrong = json.loads(document.request)
        wrong["chain"] = "ethereum"
        self.reject(lambda: replace(document, request=json.dumps(wrong, sort_keys=True, separators=(",", ":")).encode()))

    def test_request_hash_binds_parameter_order_and_interval(self):
        self.assertNotEqual(capture(params={"ids": SOL + "," + USDC}).request_sha256,
                            capture(params={"ids": USDC + "," + SOL}).request_sha256)
        base = capture(provider=BIRDEYE)
        changed = capture(provider=BIRDEYE, params={**parameters(), "time_to": 240})
        self.assertNotEqual(base.request_sha256, changed.request_sha256)
        self.assertEqual(base.response_sha256, changed.response_sha256)

    def test_jupiter_allowlist_rejects_secrets_bad_mints_and_duplicate_ids(self):
        variants = ({}, {"ids": [SOL]}, {"ids": SOL, "api_key": SECRET},
                    {"ids": SOL + "," + SOL}, {"ids": " " + SOL}, {"ids": "0" * 44},
                    {"ids": "2" * 32}, {"ids": "https://private.invalid/" + SECRET},
                    {"ids": SOL + ","}, {"ids": SOL * 51})
        for params in variants:
            with self.subTest(keys=list(params)):
                self.reject(lambda: capture(params=params))
        self.assertEqual(capture(params={"ids": "1" * 32}).parameters["ids"], "1" * 32)

    def test_birdeye_allowlist_binds_exact_request_policy_and_bounded_interval(self):
        changes = (("type", "15m"), ("currency", "usdc"), ("chart_type", "marketcap"),
                   ("mode", "count"), ("padding", False), ("ui_amount_mode", "scaled"),
                   ("time_from", 61), ("time_from", True), ("time_from", -60),
                   ("time_from", 180), ("time_to", 60 + 5000 * 60), ("time_to", 180.0),
                   ("time_to", 10_000_000_020), ("address", "not-a-mint"), ("headers", SECRET))
        for key, value in changes:
            with self.subTest(key=key, value=value):
                self.reject(lambda: capture(provider=BIRDEYE, params={**parameters(), key: value}))
        self.reject(lambda: capture(provider=BIRDEYE, params={k: v for k, v in parameters().items() if k != "mode"}))

    def test_unknown_provider_and_invalid_clocks_fail_safely(self):
        self.reject(lambda: capture(provider=SECRET))
        for key in ("received_at", "received_monotonic"):
            for value in (True, "1", Decimal("1"), -1, float("nan"), float("inf"), 10**400):
                with self.subTest(key=key, value_type=type(value)):
                    self.reject(lambda: capture(**{key: value}))
        self.assertEqual(capture(received_at=0, received_monotonic=0).received_at, 0)

    def test_duplicates_nonfinite_and_invalid_json_fail_closed(self):
        samples = (b'{"price":1,"price":2}', b'{"p":{"a":1,"a":2}}',
                   b'{"p":NaN}', b'{"p":Infinity}', b'{"p":-Infinity}',
                   b'{"p":01}', b'{"p":+1}', b'{"p":1.}', b'{"p":.1}',
                   b'{"p":-0}', b'{"p":1} null', b'{"p":', b'', b' ')
        for raw in samples:
            with self.subTest(raw=raw):
                self.reject(lambda: capture(raw))

    def test_invalid_utf8_bom_unpaired_surrogate_are_rejected(self):
        for raw in (b'"\xff"', b'\xef\xbb\xbf{}', b'{"p":"\\ud800"}', b'{"\\udfff":1}'):
            self.reject(lambda: capture(raw))
        self.assertEqual(capture(b'"\\ud83d\\ude00"').decode(), "\U0001f600")

    def test_container_depth_checked_before_decode_ignores_braces_in_strings(self):
        self.assertEqual(capture(b'"' + b"[" * 100 + b'"').decode(), "[" * 100)
        self.assertEqual(capture(b'"escaped\\\"["').decode(), 'escaped"[')
        capture(b"[" * 32 + b"0" + b"]" * 32)
        for depth in (33, 2000):
            self.reject(lambda: capture(b"[" * depth + b"0" + b"]" * depth))

    def test_total_nodes_include_mapping_keys_and_enforce_declared_bound(self):
        accepted = b"[" + b",".join([b"0"] * (MAX_NODES - 1)) + b"]"
        self.assertEqual(len(capture(accepted, provider=BIRDEYE).decode()), MAX_NODES - 1)
        rejected = b"[" + b",".join([b"0"] * MAX_NODES) + b"]"
        self.reject(lambda: capture(rejected, provider=BIRDEYE))
        keys = json.dumps({str(i): 0 for i in range(MAX_NODES // 2)}).encode()
        self.reject(lambda: capture(keys, provider=BIRDEYE))

    def test_full_birdeye_record_budget_fits_node_bound(self):
        row = {"address": SOL, "type": "1m", "currency": "usd", "unix_time": 60,
               "o": 1, "h": 2, "l": 1, "c": 2, "v": 3, "v_usd": 6, "multiplier": 1}
        raw = json.dumps({"success": True, "data": {"items": [row] * 5000, "is_scaled_ui_token": False}}).encode()
        self.assertEqual(len(capture(raw, provider=BIRDEYE).decode()["data"]["items"]), 5000)

    def test_provider_specific_body_caps(self):
        for provider, cap in MAX_DOCUMENT_BYTES.items():
            with self.subTest(provider=provider):
                raw = b'"' + b"a" * (cap - 2) + b'"'
                self.assertEqual(len(capture(raw, provider=provider).raw_body), cap)
                self.reject(lambda: capture(raw + b" ", provider=provider))

    def test_numeric_lexeme_coefficient_and_exponent_limits(self):
        values = capture(b"[" + b"9" * 80 + b",1e80,1e-80]").decode()
        self.assertEqual(values, [10**80 - 1, Decimal("1e80"), Decimal("1e-80")])
        for token in ("9" * 81, "0." + "1" * 80, "1e81", "1e-81",
                      "1e" + "0" * 127, "1e99999999999999999999999"):
            self.reject(lambda: capture(('[' + token + ']').encode()))

    def test_numeric_decode_and_decimal_text_ignore_decimal_context_rounding(self):
        with localcontext() as context:
            context.prec, context.Emax, context.Emin = 2, 9, -9
            context.traps[Inexact] = context.traps[Rounded] = True
            # localcontext copies sticky flags set by earlier arithmetic/tests.
            # Observe only flags raised by this exact-decoding operation.
            context.clear_flags()
            values = capture(b'[12345678901234567890.123456789012345678,1e-80,1e79]').decode()
            self.assertEqual(decimal_text(values[0]), "12345678901234567890.123456789012345678")
            self.assertEqual(decimal_text(values[1]), "0." + "0" * 79 + "1")
            self.assertEqual(decimal_text(values[2]), "1" + "0" * 79)
            self.assertFalse(context.flags[Inexact])
            self.assertFalse(context.flags[Rounded])

    def test_canonical_decimal_zero_integer_fraction_and_exponent(self):
        for value, expected in ((0, "0"), (12, "12"), (Decimal("0.000"), "0"),
                                (Decimal("1.2300"), "1.23"), (Decimal("1e3"), "1000"),
                                (Decimal("0.0000100"), "0.00001"), (Decimal("100.000"), "100")):
            self.assertEqual(decimal_text(value), expected)

    def test_decimal_text_rejects_floats_strings_bool_signs_nonfinite(self):
        for value in (1.0, "1", True, None, -1, Decimal("-0"), Decimal("-0.0"),
                      Decimal("-1"), Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity")):
            self.reject(lambda: decimal_text(value))
        for zero in (0, Decimal("0.0")):
            self.reject(lambda: decimal_text(zero, positive=True))
        self.assertEqual(decimal_text(1, positive=True), "1")
        self.reject(lambda: decimal_text(1, positive=1))

    def test_expanded_digit_limits_reject_values_without_rounding(self):
        self.assertEqual(decimal_text(10**80 - 1), "9" * 80)
        self.assertEqual(decimal_text(Decimal("1e-80")), "0." + "0" * 79 + "1")
        for value in (10**80, Decimal("1e80"), Decimal("1e-81"),
                      Decimal("1.1e-80"), Decimal("0." + "1" * 81)):
            self.reject(lambda: decimal_text(value))


class Content:
    def __init__(self, raw, error=None):
        self.raw, self.error, self.requested_sizes, self.reads = raw, error, [], 0

    async def iter_chunked(self, size):
        self.requested_sizes.append(size)
        if self.error is not None:
            raise self.error
        for index in range(0, len(self.raw), size):
            self.reads += 1
            yield self.raw[index:index + size]


class Response:
    def __init__(self, raw, length=None, error=None, content_type=None):
        self.content_length, self.content_type = length, content_type
        self.content = Content(raw, error=error)

    async def json(self):
        raise AssertionError("Exact capture cannot use response.json()")


class ProviderBodyTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    async def test_missing_or_false_content_length_cannot_evade_actual_cap(self):
        maximum = MAX_DOCUMENT_BYTES[JUPITER]
        for length in (None, 0, 1, maximum):
            response = Response(b"x" * maximum, length)
            self.assertEqual(await bounded_response_body(response, provider=JUPITER), b"x" * maximum)
            self.assertEqual(response.content.requested_sizes, [16 * 1024])
            with self.assertRaises(ProviderEvidenceError):
                await bounded_response_body(Response(b"x" * (maximum + 1), length), provider=JUPITER)

    async def test_declared_oversize_rejected_without_reading(self):
        response = Response(b"{}", MAX_DOCUMENT_BYTES[JUPITER] + 1)
        with self.assertRaises(ProviderEvidenceError):
            await bounded_response_body(response, provider=JUPITER)
        self.assertEqual(response.content.reads, 0)
        self.assertEqual(response.content.requested_sizes, [])

    async def test_invalid_provider_length_empty_body_and_nonbytes_fail(self):
        for length in (-1, True, "2"):
            with self.assertRaises(ProviderEvidenceError):
                await bounded_response_body(Response(b"{}", length), provider=JUPITER)
        for response, provider in ((Response(b""), JUPITER), (Response("{}"), JUPITER), (Response(b"{}"), SECRET)):
            with self.assertRaises(ProviderEvidenceError):
                await bounded_response_body(response, provider=provider)

    async def test_error_redaction_and_cancellation_semantics(self):
        with self.assertRaises(ProviderEvidenceError) as caught:
            await bounded_response_body(Response(b"{}", error=RuntimeError(SECRET)), provider=JUPITER)
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)
        with self.assertRaises(asyncio.CancelledError):
            await bounded_response_body(Response(b"{}", error=asyncio.CancelledError()), provider=JUPITER)

    async def test_birdeye_uses_separate_larger_cap(self):
        raw = b"a" * (MAX_DOCUMENT_BYTES[JUPITER] + 1)
        self.assertEqual(await bounded_response_body(Response(raw), provider=BIRDEYE), raw)
        with self.assertRaises(ProviderEvidenceError):
            await bounded_response_body(Response(raw), provider=JUPITER)

    async def test_mime_type_requires_json_and_never_falls_back_to_json_method(self):
        for mime in (None, "application/json", "application/problem+json", "APPLICATION/JSON", "application/json; charset=utf-8"):
            self.assertEqual(await bounded_response_body(Response(b"{}", content_type=mime), provider=JUPITER), b"{}")
        for mime in ("text/html", "text/json", "application/notjson", "", 42):
            response = Response(b"{}", content_type=mime)
            with self.assertRaises(ProviderEvidenceError):
                await bounded_response_body(response, provider=JUPITER)
            self.assertEqual(response.content.reads, 0)
