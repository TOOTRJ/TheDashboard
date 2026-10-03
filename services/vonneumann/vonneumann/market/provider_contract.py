"""Exact, bounded provider evidence for the v5 rehearsal contract.

Manifests bind worker-parsed records to retained document identities. They do
not authenticate providers or let a database prove derivation from raw bytes.
Receipt clocks belong to one process epoch; they grant no restart authority.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
from uuid import UUID

from ..core.decimal_execution import PRICE_SCALE, _text, _units
from .provider_evidence import (ProviderDocument, PARSER_POLICY, MAX_DOCUMENT_BYTES,
                                _request, _canonical)
from .exact_records import ExactCandleRecord, parse_candle_records, parse_price_record

MINT = "So11111111111111111111111111111111111111112"
ASSET = "SOL/USD"
MAX_CLOCK_US = 10**16
MAX_SOURCE_SECOND = 10_000_000_000
MAX_RECEIPT_AGE_US = 5_000_000
MAX_SOURCE_AGE_US = 30_000_000
FUTURE_TOLERANCE_US = 2_000_000
CANDLE_SECONDS = 900
CANDLE_COMPLETION_US = 5_000_000
SEED_BARS = 61
MAX_HISTORY_BARS = 64
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class ProviderSourceError(ValueError):
    def __init__(self, *_ignored):
        super().__init__("Provider source validation failed.")


class ProviderDeferred(ProviderSourceError):
    """An unchanged quote or real same-second observation is not a new frame."""


def _fail():
    raise ProviderSourceError()


def _safe(function):
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ProviderSourceError:
            raise
        except (ValueError, TypeError, KeyError, OverflowError, AttributeError, RecursionError):
            raise ProviderSourceError() from None
    return wrapped


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        _fail()


def _integer(value, maximum=MAX_CLOCK_US, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _epoch(value):
    if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
        _fail()
    return value


def _price(value):
    if _text(_units(value, PRICE_SCALE, positive=True), PRICE_SCALE) != value:
        _fail()
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


@_safe
def source_policy(epoch):
    return {"version": "jupiter-birdeye-sol-usd-v1", "epoch": _epoch(epoch),
        "asset": ASSET, "mint": MINT, "chain": "solana", "denomination": "USD",
        "valuation": "reference_mark", "source_time_policy": "jupiter-block-id-as-slot-estimated-time-v1",
        "clock_policy": "conservative-integer-microseconds-v1", "max_source_age_us": MAX_SOURCE_AGE_US,
        "future_tolerance_us": FUTURE_TOLERANCE_US, "max_receipt_age_us": MAX_RECEIPT_AGE_US,
        "candle_seconds": CANDLE_SECONDS, "candle_completion_us": CANDLE_COMPLETION_US,
        "seed_bars": SEED_BARS, "max_history_bars": MAX_HISTORY_BARS,
        "source_order": "strict-block-ref-nondecreasing-estimate-v1",
        "evidence_trust": "worker-parsed-records-and-manifests-v1",
        "outlier_policy": "provider-default-omitted"}


@_safe
def clock_us(value, upper=False):
    """Floor receipts and ceil current samples using the original exact ratio."""
    if type(upper) is not bool or type(value) not in (int, float):
        _fail()
    if type(value) is float:
        if not math.isfinite(value) or value < 0:
            _fail()
        numerator, denominator = value.as_integer_ratio()
    else:
        if value < 0:
            _fail()
        numerator, denominator = value, 1
    scaled = numerator * 1_000_000
    result = (scaled + denominator - 1) // denominator if upper else scaled // denominator
    return _integer(result)


def _document_wire(value, provider=None):
    _keys(value, {"provider", "parser_policy", "request", "request_sha256", "response_sha256",
                  "response_bytes", "received_wall_us", "received_monotonic_us"})
    actual = value["provider"]
    if type(actual) is not str or actual not in MAX_DOCUMENT_BYTES or provider not in (None, actual):
        _fail()
    if value["parser_policy"] != PARSER_POLICY or type(value["parser_policy"]) is not str:
        _fail()
    _integer(value["response_bytes"], MAX_DOCUMENT_BYTES[actual], 1)
    for key in ("request_sha256", "response_sha256"):
        if type(value[key]) is not str or not _HASH.fullmatch(value[key]):
            _fail()
    for key in ("received_wall_us", "received_monotonic_us"):
        _integer(value[key])
    request = value["request"]
    _keys(request, {"method", "endpoint", "chain", "parameters"})
    expected = _request(actual, request["parameters"])
    if _json(request) != _canonical(expected):
        _fail()
    if hashlib.sha256(_canonical(expected)).hexdigest() != value["request_sha256"]:
        _fail()
    parameters = request["parameters"]
    if actual == "jupiter-price-v3":
        if MINT not in parameters["ids"].split(","):
            _fail()
    elif parameters["address"] != MINT:
        _fail()


@_safe
def document_wire(document):
    if type(document) is not ProviderDocument:
        _fail()
    manifest = document.manifest()
    manifest["received_wall_us"] = clock_us(manifest.pop("received_at"))
    manifest["received_monotonic_us"] = clock_us(manifest.pop("received_monotonic"))
    _document_wire(manifest)
    return manifest


@_safe
def validate_quote_wire(quote):
    _keys(quote, {"price", "block_ref", "estimated_source_second", "source_age_floor_us", "document"})
    _price(quote["price"])
    _integer(quote["block_ref"], 2**64 - 1)
    _integer(quote["estimated_source_second"], MAX_SOURCE_SECOND)
    _integer(quote["source_age_floor_us"])
    _document_wire(quote["document"], "jupiter-price-v3")


@_safe
def quote_wire(capture):
    # Import locally: the feed imports neither this contract nor its validators.
    from .jupiter_feed import PriceCapture
    if type(capture) is not PriceCapture:
        _fail()
    record = capture.record
    if record.mint != MINT or type(record.decimals) is not int or record.decimals != 9:
        _fail()
    reparsed = parse_price_record(record.document, asset=record.asset, mint=MINT)
    if reparsed != record:
        _fail()
    evidence = capture.evidence
    if (evidence.provider != "jupiter-price-v3" or evidence.quote_currency != "USD"
            or evidence.source_slot != record.block_id
            or evidence.received_at != record.document.received_at
            or evidence.received_monotonic != record.document.received_monotonic):
        _fail()
    result = {"price": record.price, "block_ref": record.block_id,
        "estimated_source_second": capture.source_timestamp,
        "source_age_floor_us": clock_us(0 if evidence.source_age_at_receipt is None
                                        else evidence.source_age_at_receipt, upper=True),
        "document": document_wire(record.document)}
    validate_quote_wire(result)
    return result


def _receipt(document, wall_us, monotonic_us):
    wall_delta = wall_us - document["received_wall_us"]
    mono_delta = monotonic_us - document["received_monotonic_us"]
    if min(wall_delta, mono_delta) < 0 or max(wall_delta, mono_delta) >= MAX_RECEIPT_AGE_US:
        _fail()


def _frame_shape(frame):
    _keys(frame, {"sequence", "decision_second", "decision_wall_us", "decision_monotonic_us", "quote"})
    _integer(frame["sequence"], 4096, 1)
    second = _integer(frame["decision_second"], MAX_SOURCE_SECOND)
    wall = _integer(frame["decision_wall_us"])
    _integer(frame["decision_monotonic_us"])
    if not second * 1_000_000 <= wall <= (second + 1) * 1_000_000:
        _fail()
    validate_quote_wire(frame["quote"])
    receipt = frame["quote"]["document"]["received_wall_us"]
    if second < (receipt + 999_999) // 1_000_000:
        _fail()


@_safe
def check_frame(frame, *, wall_us, monotonic_us):
    _frame_shape(frame)
    _integer(wall_us); _integer(monotonic_us)
    if wall_us < frame["decision_wall_us"] or monotonic_us < frame["decision_monotonic_us"]:
        _fail()
    _check_quote(frame["quote"], wall_us, monotonic_us)


def _check_quote(quote, wall_us, monotonic_us):
    doc = quote["document"]
    _receipt(doc, wall_us, monotonic_us)
    source_us = quote["estimated_source_second"] * 1_000_000
    if source_us - wall_us > FUTURE_TOLERANCE_US or source_us - doc["received_wall_us"] > FUTURE_TOLERANCE_US:
        _fail()
    initial_age = max(0, doc["received_wall_us"] - source_us, quote["source_age_floor_us"])
    age = max(wall_us - source_us, initial_age + monotonic_us - doc["received_monotonic_us"])
    if age > MAX_SOURCE_AGE_US:
        _fail()


@_safe
def validate_bars(bars, *, allow_empty=False):
    if type(allow_empty) is not bool or type(bars) is not list or not (0 if allow_empty else 61) <= len(bars) <= 64:
        _fail()
    previous = None
    for row in bars:
        if type(row) is not list or len(row) != 3:
            _fail()
        end = _integer(row[0], MAX_SOURCE_SECOND, 900)
        if end % 900 or previous is not None and end != previous + 900:
            _fail()
        _price(row[1])
        if type(row[2]) is not str or not _HASH.fullmatch(row[2]):
            _fail()
        previous = end


@_safe
def validate_source_state(value, *, epoch=None):
    _keys(value, {"version", "epoch", "quote_sequence", "last_quote", "bars"})
    if type(value["version"]) is not int or value["version"] != 1:
        _fail()
    _epoch(value["epoch"])
    if epoch is not None and value["epoch"] != _epoch(epoch):
        _fail()
    sequence = _integer(value["quote_sequence"], 4096)
    if value["last_quote"] is None:
        if sequence != 0:
            _fail()
    else:
        _frame_shape(value["last_quote"])
        check_frame(value["last_quote"], wall_us=value["last_quote"]["decision_wall_us"],
                    monotonic_us=value["last_quote"]["decision_monotonic_us"])
        if sequence != value["last_quote"]["sequence"]:
            _fail()
    validate_bars(value["bars"])


def _carried_floor(quote, oldquote):
    doc, olddoc = quote["document"], oldquote["document"]
    oldsource = oldquote["estimated_source_second"] * 1_000_000
    oldage = max(0, olddoc["received_wall_us"] - oldsource, oldquote["source_age_floor_us"])
    carried = max(doc["received_wall_us"] - oldsource,
                  oldage + doc["received_monotonic_us"] - olddoc["received_monotonic_us"])
    return max(0, carried - (quote["estimated_source_second"] - oldquote["estimated_source_second"]) * 1_000_000)


@_safe
def validate_frame(frame, *, prior_source=None, epoch=None):
    _frame_shape(frame)
    check_frame(frame, wall_us=frame["decision_wall_us"], monotonic_us=frame["decision_monotonic_us"])
    if epoch is not None:
        _epoch(epoch)
    if prior_source is None:
        if frame["sequence"] != 1:
            _fail()
        return
    validate_source_state(prior_source, epoch=epoch)
    if frame["sequence"] != prior_source["quote_sequence"] + 1:
        _fail()
    prior = prior_source["last_quote"]
    if prior is None:
        return
    quote, oldquote = frame["quote"], prior["quote"]
    doc, olddoc = quote["document"], oldquote["document"]
    if (frame["decision_second"] <= prior["decision_second"]
            or frame["decision_wall_us"] < prior["decision_wall_us"]
            or frame["decision_monotonic_us"] < prior["decision_monotonic_us"]
            or quote["block_ref"] <= oldquote["block_ref"]
            or quote["estimated_source_second"] < oldquote["estimated_source_second"]
            or doc["received_wall_us"] < olddoc["received_wall_us"]
            or doc["received_monotonic_us"] <= olddoc["received_monotonic_us"]
            or quote["source_age_floor_us"] < _carried_floor(quote, oldquote)):
        _fail()


@_safe
def make_frame(capture, *, prior_source, epoch, wall_now, monotonic_now):
    _epoch(epoch)
    if prior_source is not None:
        validate_source_state(prior_source, epoch=epoch)
    quote = quote_wire(capture)
    wall_us, mono_us = clock_us(wall_now, upper=True), clock_us(monotonic_now, upper=True)
    second = int(wall_now)
    prior = None if prior_source is None else prior_source["last_quote"]
    if prior is not None:
        old = prior["quote"]
        doc, olddoc = quote["document"], old["document"]
        if (wall_us < prior["decision_wall_us"] or mono_us < prior["decision_monotonic_us"]
                or doc["received_wall_us"] < olddoc["received_wall_us"]
                or doc["received_monotonic_us"] < olddoc["received_monotonic_us"]):
            _fail()
        quote["source_age_floor_us"] = max(quote["source_age_floor_us"], _carried_floor(quote, old))
    _check_quote(quote, wall_us, mono_us)
    if prior is not None:
        old = prior["quote"]
        if quote["block_ref"] < old["block_ref"] or quote["estimated_source_second"] < old["estimated_source_second"]:
            _fail()
        if quote["block_ref"] == old["block_ref"]:
            if quote["price"] == old["price"] and quote["estimated_source_second"] == old["estimated_source_second"]:
                check_frame(prior, wall_us=wall_us, monotonic_us=mono_us)
                raise ProviderDeferred()
            _fail()
        if second <= prior["decision_second"]:
            raise ProviderDeferred()
    if second < (quote["document"]["received_wall_us"] + 999_999) // 1_000_000:
        raise ProviderDeferred()
    result = {"sequence": 1 if prior_source is None else prior_source["quote_sequence"] + 1,
        "decision_second": second, "decision_wall_us": wall_us,
        "decision_monotonic_us": mono_us, "quote": quote}
    validate_frame(result, prior_source=prior_source, epoch=epoch)
    return result


def _doc_sort(document):
    return tuple(document[key] for key in ("response_sha256", "request_sha256", "received_wall_us", "received_monotonic_us"))


def _history_shape(bundle):
    _keys(bundle, {"documents", "minutes", "unscaled"})
    if bundle["unscaled"] is not True:
        _fail()
    docs, minutes = bundle["documents"], bundle["minutes"]
    if type(docs) is not list or not 1 <= len(docs) <= 4 or type(minutes) is not list or len(minutes) not in (15, 915):
        _fail()
    for doc in docs:
        _document_wire(doc, "birdeye-ohlcv-v3")
    ordering = [_doc_sort(doc) for doc in docs]
    if ordering != sorted(set(ordering)):
        _fail()
    used, previous = set(), None
    for row in minutes:
        if type(row) is not list or len(row) != 3:
            _fail()
        start = _integer(row[0], MAX_SOURCE_SECOND - 60, 60)
        index = _integer(row[2], len(docs) - 1)
        _price(row[1])
        if start % 60 or previous is not None and start != previous + 60:
            _fail()
        params = docs[index]["request"]["parameters"]
        if not params["time_from"] <= start or start + 60 > params["time_to"]:
            _fail()
        used.add(index); previous = start
    if used != set(range(len(docs))) or (minutes[-1][0] + 60) % 900:
        _fail()


@_safe
def derive_bars(bundle):
    _history_shape(bundle)
    minutes = bundle["minutes"]
    result = []
    for offset in range(0, len(minutes), 15):
        batch = minutes[offset:offset + 15]
        pairs = [[row[0], row[1]] for row in batch]
        result.append([batch[-1][0] + 60, batch[-1][1], hashlib.sha256(_json(pairs)).hexdigest()])
    return result


@_safe
def validate_history(bundle, *, prior_bars, seed, wall_us, monotonic_us):
    _integer(wall_us); _integer(monotonic_us)
    if type(seed) is not bool:
        _fail()
    validate_bars(prior_bars, allow_empty=True)
    if (seed and prior_bars) or (not seed and len(prior_bars) < 61):
        _fail()
    _history_shape(bundle)
    rows = bundle["minutes"]
    if len(rows) != (915 if seed else 15):
        _fail()
    latest = (wall_us - CANDLE_COMPLETION_US) // (900 * 1_000_000) * 900
    bars = derive_bars(bundle)
    if bars[-1][0] != latest or (not seed and bars[0][0] != prior_bars[-1][0] + 900):
        _fail()
    for document in bundle["documents"]:
        _receipt(document, wall_us, monotonic_us)
    for offset in range(0, len(rows), 15):
        batch = rows[offset:offset + 15]
        completed = (batch[-1][0] + 60) * 1_000_000 + CANDLE_COMPLETION_US
        if completed > wall_us or any(completed > bundle["documents"][row[2]]["received_wall_us"] for row in batch):
            _fail()
    return bars


@_safe
def build_history(records, *, prior_bars, seed, wall_us, monotonic_us):
    _integer(wall_us); _integer(monotonic_us)
    if type(records) not in (tuple, list) or len(records) > 20_000 or type(seed) is not bool:
        _fail()
    validate_bars(prior_bars, allow_empty=True)
    if (seed and prior_bars) or (not seed and len(prior_bars) < 61):
        _fail()
    documents, parsed, by_start = {}, {}, {}
    for record in records:
        if type(record) is not ExactCandleRecord or record.mint != MINT or record.is_scaled_ui_token is not False or record.multiplier not in (None, "1"):
            _fail()
        identity = id(record.document)
        if identity not in parsed:
            if len(parsed) >= 4:
                _fail()
            parsed[identity] = {row.start: row for row in parse_candle_records(record.document, asset=record.asset, mint=MINT)}
            documents[identity] = document_wire(record.document)
        if record != parsed[identity].get(record.start) or record.start in by_start:
            _fail()
        by_start[record.start] = record
    # Compare every supplied retained minute, even if this retrieval yields no
    # next candle. Partial overlap cannot prove a fingerprint; reject it.
    for end, close, fingerprint in prior_bars:
        starts = range(end - 900, end, 60)
        present = [start in by_start for start in starts]
        if any(present):
            if not all(present):
                _fail()
            pairs = [[start, by_start[start].close] for start in starts]
            for _, value in pairs:
                _price(value)
            if pairs[-1][1] != close or hashlib.sha256(_json(pairs)).hexdigest() != fingerprint:
                _fail()
    latest = (wall_us - CANDLE_COMPLETION_US) // (900 * 1_000_000) * 900
    if not seed:
        if latest < prior_bars[-1][0]:
            _fail()
        if latest == prior_bars[-1][0]:
            return None
        if latest != prior_bars[-1][0] + 900:
            _fail()
    count = 915 if seed else 15
    selected = []
    for start in range(latest - count * 60, latest, 60):
        if start not in by_start:
            _fail()
        record = by_start[start]
        _price(record.close)
        selected.append(record)
    selected_docs = {_json(documents[id(row.document)]): documents[id(row.document)] for row in selected}
    docs = sorted(selected_docs.values(), key=_doc_sort)
    indices = {_json(doc): index for index, doc in enumerate(docs)}
    bundle = {"documents": docs, "minutes": [[row.start, row.close, indices[_json(documents[id(row.document)])]] for row in selected], "unscaled": True}
    validate_history(bundle, prior_bars=prior_bars, seed=seed, wall_us=wall_us, monotonic_us=monotonic_us)
    return bundle


@_safe
def source_state(epoch, frame, bars):
    result = {"version": 1, "epoch": _epoch(epoch), "quote_sequence": 0 if frame is None else frame["sequence"],
              "last_quote": deepcopy(frame), "bars": deepcopy(bars)}
    validate_source_state(result)
    return result
