"""Offline wire-precision, identity, unit and immutable-source regressions."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import localcontext
import json
import unittest

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.market.provider_evidence import ProviderDocument, ProviderEvidenceError
    from vonneumann.market.exact_records import (
        ExactCandleRecord, ExactPriceRecord, ExactRecordError,
        parse_candle_records, parse_price_record,
    )


ASSET = "SOL/USDC"
MINT = "So11111111111111111111111111111111111111112"
START = 1_790_756_100
_ABSENT = object()


def price_document(*, price="100", block="348004023", decimals="9", parameters=None,
                   payload=None):
    raw = ("{" + json.dumps(MINT) + ":{\"usdPrice\":" + price
           + ",\"blockId\":" + block
           + ("" if decimals is None else ",\"decimals\":" + decimals) + "}}")
    return ProviderDocument.capture(
        provider="jupiter-price-v3", parameters={"ids": MINT} if parameters is None else parameters,
        raw_body=raw.encode() if payload is None else payload,
        received_at=START + 1000, received_monotonic=1000,
    )


def row(stamp=START, *, overrides=None):
    fields = {"unix_time": str(stamp), "address": json.dumps(MINT), "type": '"1m"',
              "currency": '"usd"', "o": "100", "h": "102", "l": "99",
              "c": "101", "v": "3", "v_usd": "301"}
    fields.update(overrides or {})
    return "{" + ",".join(json.dumps(key) + ":" + value for key, value in fields.items()) + "}"


def candle_document(*rows, parameters=None, scaled="false", multiplier=_ABSENT, payload=None):
    raw = ('{"success":true,"data":{"is_scaled_ui_token":' + scaled
           + ("" if multiplier is _ABSENT else ',"multiplier":' + multiplier)
           + ',"items":[' + ",".join(rows) + "]}}")
    request = {"address": MINT, "type": "1m", "currency": "usd", "chart_type": "price",
               "ui_amount_mode": "raw", "padding": "false", "mode": "range",
               "time_from": START, "time_to": START + 180}
    request.update(parameters or {})
    return ProviderDocument.capture(
        provider="birdeye-ohlcv-v3", parameters=request,
        raw_body=raw.encode() if payload is None else payload,
        received_at=START + 1000, received_monotonic=1000,
    )


def price(record=None, **changes):
    return parse_price_record(price_document(**changes) if record is None else record,
                              asset=ASSET, mint=MINT)


def candles(document):
    return parse_candle_records(document, asset=ASSET, mint=MINT)


class ExactPriceRecordTests(OfflineTestMixin, unittest.TestCase):
    def test_exact_lexemes_are_canonical_without_a_price_decimal_rounding_policy(self):
        record = price(price="1.234567890123456789012345678900e-7", decimals="9")
        self.assertEqual(record.price, "0.00000012345678901234567890123456789")
        self.assertEqual(record.decimals, 9)
        self.assertEqual(record.block_id, 348004023)

    def test_integer_above_binary64_exact_range_and_sub_binary64_difference_survive(self):
        self.assertEqual(price(price="9007199254740993").price, "9007199254740993")
        left = price(price="1.000000000000000001")
        right = price(price="1.000000000000000002")
        self.assertNotEqual(left.price, right.price)
        self.assertNotEqual(left.document.response_sha256, right.document.response_sha256)

    def test_context_precision_cannot_round_source_values(self):
        with localcontext() as context:
            context.prec = 3
            record = price(price="123456789.01234567890123456789")
        self.assertEqual(record.price, "123456789.01234567890123456789")

    def test_optional_decimals_are_metadata_and_invalid_values_are_rejected(self):
        for value in (None, "null"):
            with self.subTest(value=value):
                self.assertIsNone(price(decimals=value).decimals)
        for value in ("true", "-1", "256", "1.0", '"9"'):
            with self.subTest(value=value), self.assertRaises(ExactRecordError) as caught:
                price(decimals=value)
            self.assertEqual(caught.exception.code, "price_invalid")

    def test_block_reference_is_an_exact_bounded_integer(self):
        self.assertEqual(price(block="0").block_id, 0)
        self.assertEqual(price(block=str(2**64 - 1)).block_id, 2**64 - 1)
        for value in ("null", "true", "-1", str(2**64), "1.0", "1e2", '"123"'):
            with self.subTest(value=value), self.assertRaises(ExactRecordError) as caught:
                price(block=value)
            self.assertEqual(caught.exception.code, "price_invalid")

    def test_price_must_be_a_positive_numeric_token(self):
        for value in ("null", "true", "0", "-1", '"100"', "[]", "{}"):
            with self.subTest(value=value), self.assertRaises(ExactRecordError):
                price(price=value)

    def test_requested_mint_must_match_and_missing_or_null_rows_fail(self):
        for payload in (b"{}", ("{" + json.dumps(MINT) + ":null}").encode()):
            with self.subTest(payload=payload), self.assertRaises(ExactRecordError):
                price(payload=payload)
        with self.assertRaises(ExactRecordError):
            price(parameters={"ids": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"})
        with self.assertRaises(ExactRecordError):
            parse_price_record(price_document(), asset=ASSET, mint=MINT + "x")

    def test_invalid_display_identity_and_wrong_provider_fail(self):
        for asset in ("", " SOL/USDC", "SOL\nUSDC", True, "a" * 129):
            with self.subTest(asset=asset), self.assertRaises(ExactRecordError):
                parse_price_record(price_document(), asset=asset, mint=MINT)
        with self.assertRaises(ExactRecordError):
            parse_price_record(candle_document(row()), asset=ASSET, mint=MINT)

    def test_values_cannot_be_constructed_or_replaced_separately_from_document(self):
        record = price()
        with self.assertRaises(ProviderEvidenceError):
            ExactPriceRecord(asset=ASSET, mint=MINT, price="999", block_id=1,
                             decimals=9, document=record.document)
        with self.assertRaises(ProviderEvidenceError):
            replace(record, price="999")
        with self.assertRaises(FrozenInstanceError):
            record.price = "999"
        decoded = record.document.decode()
        decoded[MINT]["usdPrice"] = 999
        self.assertEqual(record.price, "100")
        self.assertEqual(price(record.document).price, "100")

    def test_serialized_evidence_is_detached_and_contains_manifest_without_body(self):
        record = price()
        emitted = record.to_dict()
        self.assertEqual((emitted["quote_currency"], emitted["valuation"]), ("USD", "reference_mark"))
        self.assertEqual(emitted["document"], record.document.manifest())
        self.assertNotIn("usdPrice", json.dumps(emitted))
        emitted["document"]["request"]["parameters"]["ids"] = "changed"
        self.assertEqual(record.document.parameters["ids"], MINT)


class ExactCandleRecordTests(OfflineTestMixin, unittest.TestCase):
    def test_preserves_all_exact_prices_and_distinct_volume_units(self):
        document = candle_document(row(overrides={"o": "1.000000000000000001",
            "h": "1.000000000000000003", "l": "1", "c": "1.000000000000000002",
            "v": "9007199254740993", "v_usd": "9007199254740993.000000000000000001"}))
        record, = candles(document)
        self.assertEqual((record.open, record.close), ("1.000000000000000001", "1.000000000000000002"))
        self.assertEqual(record.volume, "9007199254740993")
        self.assertEqual(record.volume_usd, "9007199254740993.000000000000000001")
        self.assertEqual((record.start, record.end), (START, START + 60))
        self.assertIs(record.document, document)
        self.assertIs(record.require_unscaled(), record)

    def test_sorts_complete_rows_and_validates_excluded_rows_before_filtering(self):
        document = candle_document(row(START + 180), row(START + 120), row(START - 60), row(START))
        result = candles(document)
        self.assertEqual([item.start for item in result], [START, START + 120])
        self.assertTrue(all(item.document is document for item in result))
        for stamp in (START - 60, START + 180):
            with self.subTest(stamp=stamp), self.assertRaises(ExactRecordError):
                candles(candle_document(row(), row(stamp, overrides={"v_usd": '"bad"'})))

    def test_empty_and_gapped_records_leave_coverage_policy_to_adapter(self):
        self.assertEqual(candles(candle_document()), ())
        result = candles(candle_document(row(), row(START + 120)))
        self.assertEqual(len(result), 2)

    def test_numerically_identical_duplicate_forms_are_deduplicated(self):
        result = candles(candle_document(row(), row(overrides={"o": "1e2", "c": "101.000"})))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].open, "100")

    def test_exact_difference_below_binary64_resolution_rejects_duplicate(self):
        for field in ("o", "c", "v", "v_usd"):
            baseline = {"o": "100", "c": "101", "v": "3", "v_usd": "301"}[field]
            with self.subTest(field=field), self.assertRaises(ExactRecordError) as caught:
                candles(candle_document(row(), row(overrides={field: baseline + ".000000000000000001"})))
            self.assertEqual(caught.exception.code, "candles_revision")

    def test_conflicting_excluded_duplicate_is_also_rejected(self):
        with self.assertRaises(ExactRecordError) as caught:
            candles(candle_document(row(START + 180), row(START + 180, overrides={"v": "4"})))
        self.assertEqual(caught.exception.code, "candles_revision")

    def test_exact_ohlc_order_is_validated_without_rounding(self):
        with self.assertRaises(ExactRecordError):
            candles(candle_document(row(overrides={"l": "100.000000000000000001"})))
        with localcontext() as context:
            context.prec = 2
            record, = candles(candle_document(row(overrides={"o": "100.000000000000000001"})))
        self.assertEqual(record.open, "100.000000000000000001")

    def test_row_identity_currency_and_interval_are_checked(self):
        for field, value in (("address", '"other-mint"'), ("type", '"5m"'),
                             ("currency", '"native"'), ("currency", "null")):
            with self.subTest(field=field), self.assertRaises(ExactRecordError):
                candles(candle_document(row(overrides={field: value})))

    def test_request_must_explicitly_pin_raw_usd_price_minutes(self):
        for parameters in ({"address": "other"}, {"type": "5m"}, {"currency": "native"},
                           {"chart_type": "mcap"}, {"ui_amount_mode": "scaled"},
                           {"mode": "count"}, {"padding": "true"}):
            with self.subTest(parameters=parameters), self.assertRaises(ProviderEvidenceError):
                candles(candle_document(row(), parameters=parameters))

    def test_window_and_row_timestamps_are_integer_aligned_and_bounded(self):
        for value in ("true", "1.0", "0", str(START + 1), "-60", "10000000020", str(START + 240)):
            with self.subTest(value=value), self.assertRaises(ExactRecordError):
                candles(candle_document(row(overrides={"unix_time": value})))
        for parameters in ({"time_from": START + 1}, {"time_to": START},
                           {"time_from": -60}, {"time_to": 10_000_000_020}):
            with self.subTest(parameters=parameters), self.assertRaises(ProviderEvidenceError):
                candles(candle_document(row(), parameters=parameters))

    def test_positive_prices_and_nonnegative_token_and_usd_volume(self):
        for field in ("o", "h", "l", "c", "v", "v_usd"):
            for value in ("-1", "null", "true", '"3"'):
                with self.subTest(field=field, value=value), self.assertRaises(ExactRecordError):
                    candles(candle_document(row(overrides={field: value})))
        record, = candles(candle_document(row(overrides={"v": "0", "v_usd": "0e3"})))
        self.assertEqual((record.volume, record.volume_usd), ("0", "0"))

    def test_scaled_metadata_is_retained_but_explicit_profile_guard_rejects(self):
        for multiplier in (_ABSENT, "null", "2.500000000000000001"):
            with self.subTest(multiplier=multiplier):
                record, = candles(candle_document(row(), scaled="true", multiplier=multiplier))
                self.assertTrue(record.is_scaled_ui_token)
                self.assertEqual(record.multiplier, None if multiplier is _ABSENT or multiplier == "null" else multiplier)
                with self.assertRaises(ProviderEvidenceError):
                    record.require_unscaled()
                self.assertEqual(record.open, "100")

    def test_invalid_scaling_marker_and_multiplier_fail(self):
        for scaled in ("null", "1", '"false"'):
            with self.subTest(scaled=scaled), self.assertRaises(ExactRecordError):
                candles(candle_document(row(), scaled=scaled))
        for multiplier in ("0", "-1", '"2"', "true"):
            with self.subTest(multiplier=multiplier), self.assertRaises(ExactRecordError):
                candles(candle_document(row(), multiplier=multiplier))

    def test_real_unscaled_null_multiplier_preserves_exact_raw_evidence(self):
        document = candle_document(row(), multiplier="null")
        record, = candles(document)
        self.assertIsNone(record.multiplier)
        self.assertFalse(record.is_scaled_ui_token)
        self.assertIs(record.require_unscaled(), record)
        self.assertEqual(record.open, "100")
        self.assertIs(record.document, document)
        self.assertIn(b'"multiplier":null', document.raw_body)

    def test_invalid_envelope_and_record_count_fail(self):
        for payload in (b"{}", b'{"success":false,"data":{}}',
                        b'{"success":true,"data":{"is_scaled_ui_token":false,"items":null}}'):
            with self.subTest(payload=payload), self.assertRaises(ExactRecordError):
                candles(candle_document(payload=payload))
        with self.assertRaises(ProviderEvidenceError):
            candles(candle_document(*(row() for _ in range(5001))))

    def test_candle_cannot_be_forged_and_serialization_remains_detached(self):
        record, = candles(candle_document(row()))
        with self.assertRaises(ProviderEvidenceError):
            ExactCandleRecord()
        with self.assertRaises(ProviderEvidenceError):
            replace(record, close="999")
        with self.assertRaises(FrozenInstanceError):
            record.close = "999"
        emitted = record.to_dict()
        self.assertEqual((emitted["quote_currency"], emitted["volume_unit"], emitted["ui_amount_mode"]),
                         ("USD", "base_token", "raw"))
        self.assertNotIn("raw_body", emitted["document"])
        emitted["close"] = "999"
        self.assertEqual(record.close, "101")


if __name__ == "__main__":
    unittest.main()
