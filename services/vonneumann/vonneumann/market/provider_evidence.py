"""Bounded raw provider documents with exact JSON numbers and safe provenance.

This layer records bytes and request identity; it does not authenticate a
provider, prove market freshness, or grant archive rights. Monetary consumers
must apply their own declared decimal grid and provider field semantics.
Credentials, headers and caller-selected endpoints are deliberately absent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import json
import math
import re
from types import MappingProxyType


PARSER_POLICY = "provider-json-exact-v1"
MAX_DOCUMENT_BYTES = MappingProxyType({
    "jupiter-price-v3": 128 * 1024,
    "birdeye-ohlcv-v3": 4 * 1024 * 1024,
})
_ENDPOINTS = {"jupiter-price-v3": "https://api.jup.ag/price/v3",
              "birdeye-ohlcv-v3": "https://public-api.birdeye.so/defi/v3/ohlcv"}
MAX_NESTING = 32
MAX_NODES = 200_000
MAX_NUMERIC_TOKEN = 128
MAX_COEFFICIENT_DIGITS = 80
MAX_EXPONENT = 80
READ_CHUNK_BYTES = 16 * 1024
_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE]([+-]?[0-9]+))?\Z", re.ASCII)


class ProviderEvidenceError(ValueError):
    """Safe public failure: no provider body, path or secret enters the message."""

    def __init__(self):
        super().__init__("Provider evidence validation failed.")


def _fail():
    raise ProviderEvidenceError()


def _provider(provider):
    if type(provider) is not str or provider not in MAX_DOCUMENT_BYTES:
        _fail()
    return provider


def _clock(value):
    if type(value) not in (int, float):
        _fail()
    try:
        result = float(value)
    except (OverflowError, ValueError):
        _fail()
    if not math.isfinite(result) or result < 0:
        _fail()
    return result


def _mint(value):
    if (type(value) is not str or not 32 <= len(value) <= 44
            or any(char not in _BASE58 for char in value)):
        _fail()
    number = 0
    for char in value:
        number = number * 58 + _BASE58.index(char)
    leading = len(value) - len(value.lstrip("1"))
    if leading + (number.bit_length() + 7) // 8 != 32:
        _fail()
    return value


def _parameters(provider, parameters):
    if type(parameters) is not dict:
        _fail()
    if provider == "jupiter-price-v3":
        if set(parameters) != {"ids"} or type(parameters["ids"]) is not str:
            _fail()
        # Bound before splitting and do not canonicalize the requested order.
        value = parameters["ids"]
        if len(value) > 50 * 45:
            _fail()
        mints = value.split(",")
        if not 1 <= len(mints) <= 50 or len(set(mints)) != len(mints):
            _fail()
        for mint in mints:
            _mint(mint)
    else:
        fixed = {"type": "1m", "mode": "range", "currency": "usd",
                 "chart_type": "price", "ui_amount_mode": "raw", "padding": "false"}
        if (set(parameters) != set(fixed) | {"address", "time_from", "time_to"}
                or any(type(parameters[key]) is not str or parameters[key] != value
                       for key, value in fixed.items())):
            _fail()
        _mint(parameters["address"])
        for key in ("time_from", "time_to"):
            value = parameters[key]
            if type(value) is not int or not 0 <= value <= 10_000_000_000 or value % 60:
                _fail()
        if (parameters["time_from"] >= parameters["time_to"]
                or (parameters["time_to"] - parameters["time_from"]) // 60 + 1 > 5000):
            _fail()
    return dict(parameters)


def _request(provider, parameters):
    return {"method": "GET", "endpoint": _ENDPOINTS[provider], "chain": "solana",
            "parameters": _parameters(provider, parameters)}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _numeric(token, *, integer):
    if len(token) > MAX_NUMERIC_TOKEN:
        _fail()
    match = _NUMBER.fullmatch(token)
    if match is None:
        _fail()
    exponent = match[1]
    if exponent is not None:
        # A 128-character token is already bounded, but compare only its small
        # exact integer exponent before constructing a Decimal.
        if not -MAX_EXPONENT <= int(exponent) <= MAX_EXPONENT:
            _fail()
    coefficient = re.split("[eE]", token, maxsplit=1)[0]
    digits = sum("0" <= char <= "9" for char in coefficient)
    if digits > MAX_COEFFICIENT_DIGITS:
        _fail()
    if integer:
        # int('-0') would erase its sign before monetary field validation.
        if token == "-0":
            _fail()
        return int(token)
    value = Decimal(token)
    if not value.is_finite():
        _fail()
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _preflight(text):
    """Bound container depth before JSON's recursive decoder sees the text."""
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_NESTING:
                _fail()
        elif char in "]}":
            depth -= 1
            if depth < 0:
                _fail()


def _tree(value):
    # Count values and mapping keys; no recursion or approximate numeric casts.
    pending = [value]
    nodes = 0
    while pending:
        item = pending.pop()
        nodes += 1
        if nodes > MAX_NODES:
            _fail()
        if type(item) is dict:
            pending.extend(item.keys())
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
        elif type(item) is str:
            # json.loads accepts escaped unpaired surrogates even though they
            # cannot represent valid UTF-8 source text after unescaping.
            if any(0xD800 <= ord(char) <= 0xDFFF for char in item):
                _fail()
        elif item is not None and type(item) not in (bool, int, Decimal):
            _fail()


def _decode(provider, raw_body):
    if (type(raw_body) is not bytes or not raw_body
            or len(raw_body) > MAX_DOCUMENT_BYTES[provider]):
        _fail()
    try:
        text = raw_body.decode("utf-8")
        if text.startswith("\ufeff"):
            _fail()
        _preflight(text)
        value = json.loads(text, object_pairs_hook=_pairs,
            parse_int=lambda token: _numeric(token, integer=True),
            parse_float=lambda token: _numeric(token, integer=False),
            parse_constant=lambda _: _fail())
        _tree(value)
        return value
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        raise ProviderEvidenceError() from None


def decimal_text(value, *, positive=False):
    """Expand an exact JSON number without Decimal-context arithmetic/rounding.

    The returned plain spelling is canonical. No float, string or boolean can
    enter accidentally; negative zero is rejected before its sign is erased.
    This generic 80-digit bound does not replace the economic price/cash grid.
    """
    if type(positive) is not bool or type(value) not in (int, Decimal):
        _fail()
    if type(value) is int:
        if value < 0 or (positive and value == 0) or value >= 10**80:
            _fail()
        return str(value)
    if not value.is_finite() or value.is_signed():
        _fail()
    sign, digits, exponent = value.as_tuple()
    if len(digits) > MAX_COEFFICIENT_DIGITS or not -MAX_EXPONENT <= exponent <= MAX_EXPONENT:
        _fail()
    text = "".join(str(digit) for digit in digits)
    if not any(digits):
        if positive:
            _fail()
        return "0"
    point = len(text) + exponent
    if point <= 0:
        whole, tail = "0", "0" * -point + text
    elif point >= len(text):
        whole, tail = text + "0" * (point - len(text)), ""
    else:
        whole, tail = text[:point], text[point:]
    whole = whole.lstrip("0") or "0"
    tail = tail.rstrip("0")
    if len(whole) > 80 or len(tail) > 80:
        _fail()
    return whole + ("." + tail if tail else "")


@dataclass(frozen=True, slots=True)
class ProviderDocument:
    """Immutable response identity; receipt clocks authorize no cross-process use."""
    provider: str
    request: bytes = field(repr=False)
    raw_body: bytes = field(repr=False)
    received_at: float
    received_monotonic: float
    parser_policy: str = PARSER_POLICY

    def __post_init__(self):
        self._metadata()
        _decode(self.provider, self.raw_body)

    def _metadata(self):
        _provider(self.provider)
        if self.parser_policy != PARSER_POLICY or type(self.parser_policy) is not str:
            _fail()
        _clock(self.received_at)
        _clock(self.received_monotonic)
        if type(self.request) is not bytes or len(self.request) > 4096:
            _fail()
        try:
            request = json.loads(self.request.decode("ascii"), object_pairs_hook=_pairs)
            if (type(request) is not dict or set(request) != {"method", "endpoint", "chain", "parameters"}
                    or _canonical(_request(self.provider, request["parameters"])) != self.request):
                _fail()
        except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
            raise ProviderEvidenceError() from None
        return request

    @classmethod
    def capture(cls, provider, parameters, raw_body, received_at, received_monotonic):
        _provider(provider)
        request = _canonical(_request(provider, parameters))
        return cls(provider, request, raw_body, _clock(received_at), _clock(received_monotonic))

    @property
    def parameters(self):
        return self._metadata()["parameters"]

    @property
    def response_sha256(self):
        return hashlib.sha256(self.raw_body).hexdigest()

    @property
    def request_sha256(self):
        return hashlib.sha256(self.request).hexdigest()

    def decode(self):
        self._metadata()
        return _decode(self.provider, self.raw_body)

    def manifest(self):
        request = self._metadata()
        return {"provider": self.provider, "parser_policy": self.parser_policy,
                "request": request, "request_sha256": self.request_sha256,
                "response_sha256": self.response_sha256, "response_bytes": len(self.raw_body),
                "received_at": self.received_at, "received_monotonic": self.received_monotonic}


async def bounded_response_body(response, *, provider):
    """Read bounded decoded bytes, including when Content-Length is absent/false."""
    _provider(provider)
    maximum = MAX_DOCUMENT_BYTES[provider]
    try:
        content_type = getattr(response, "content_type", None)
        if content_type is not None:
            if type(content_type) is not str:
                _fail()
            mime = content_type.lower().split(";", 1)[0].strip()
            if (mime != "application/json" and
                    not re.fullmatch(r"application/[a-z0-9!#$&^_.+-]+\+json", mime, re.ASCII)):
                _fail()
        length = getattr(response, "content_length", None)
        if length is not None and (type(length) is not int or length < 0 or length > maximum):
            _fail()
        pieces, size = [], 0
        async for chunk in response.content.iter_chunked(READ_CHUNK_BYTES):
            if type(chunk) is not bytes:
                _fail()
            size += len(chunk)
            if size > maximum:
                _fail()
            pieces.append(chunk)
        if not size:
            _fail()
        return b"".join(pieces)
    except Exception:
        # Response errors can include request headers/URLs. Preserve cancellation
        # (a BaseException) but expose none of those transport details.
        raise ProviderEvidenceError() from None
