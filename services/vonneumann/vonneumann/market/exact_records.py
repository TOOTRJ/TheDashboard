"""Immutable source records derived from bounded provider response bytes.

These records preserve the provider's decimal values without asserting that a
reference mark is executable, that a candle was available at its close, or that
the values fit a later execution grid. Float compatibility belongs at an
explicit caller boundary, never in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .provider_evidence import ProviderDocument, ProviderEvidenceError, decimal_text


EXACT_RECORD_VERSION = "provider-exact-record-v1"
MAX_CANDLE_ROWS = 5000
MAX_PROVIDER_TIMESTAMP = 10_000_000_000


class ExactRecordError(ProviderEvidenceError):
    """Safe adapter-facing failure code without provider payload content."""

    def __init__(self, code: str):
        if code not in {"price_invalid", "candles_invalid", "candles_revision"}:
            code = "candles_invalid"
        self.code = code
        super().__init__()


def _invalid() -> ProviderEvidenceError:
    # Do not echo provider payloads, URLs, or caller-supplied identity strings.
    return ProviderEvidenceError()


def _identity(asset: object, mint: object) -> None:
    for value, maximum in ((asset, 128), (mint, 128)):
        if (type(value) is not str or not value or len(value) > maximum
                or value != value.strip()
                or any(ord(character) < 32 or ord(character) == 127 for character in value)):
            raise _invalid()


def _document(document: object, provider: str) -> ProviderDocument:
    if type(document) is not ProviderDocument or document.provider != provider:
        raise _invalid()
    return document


def _integer(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _invalid()
    return value


def _new(record_type: type, **values):
    """Internal construction after derivation; public field substitution fails."""
    record = object.__new__(record_type)
    for name, value in values.items():
        object.__setattr__(record, name, value)
    return record


@dataclass(frozen=True, slots=True, init=False)
class ExactPriceRecord:
    asset: str
    mint: str
    price: str
    block_id: int
    decimals: int | None
    document: ProviderDocument = field(repr=False)

    def __init__(self, *args, **kwargs):
        raise ProviderEvidenceError()

    def to_dict(self) -> dict:
        return {
            "version": EXACT_RECORD_VERSION, "asset": self.asset, "mint": self.mint,
            "price": self.price, "block_id": self.block_id, "decimals": self.decimals,
            "quote_currency": "USD", "valuation": "reference_mark",
            "document": self.document.manifest(),
        }


@dataclass(frozen=True, slots=True, init=False)
class ExactCandleRecord:
    asset: str
    mint: str
    start: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    volume_usd: str
    is_scaled_ui_token: bool
    multiplier: str | None
    document: ProviderDocument = field(repr=False)

    def __init__(self, *args, **kwargs):
        raise ProviderEvidenceError()

    @property
    def end(self) -> int:
        return self.start + 60

    def require_unscaled(self) -> ExactCandleRecord:
        if self.is_scaled_ui_token:
            raise ProviderEvidenceError()
        return self

    def to_dict(self) -> dict:
        return {
            "version": EXACT_RECORD_VERSION, "asset": self.asset, "mint": self.mint,
            "start": self.start, "end": self.end, "open": self.open, "high": self.high,
            "low": self.low, "close": self.close, "volume": self.volume,
            "volume_usd": self.volume_usd, "quote_currency": "USD",
            "volume_unit": "base_token", "ui_amount_mode": "raw",
            "is_scaled_ui_token": self.is_scaled_ui_token, "multiplier": self.multiplier,
            "document": self.document.manifest(),
        }


def parse_price_record(document: ProviderDocument, *, asset: str, mint: str) -> ExactPriceRecord:
    """Derive one requested mint's reference price and original block reference.

    ``asset`` is the caller's configured display identity; this function binds
    the mint to the actual request, not a symbol-to-mint discovery service.
    Token decimals are metadata and never determine USD price precision.
    """
    try:
        return _parse_price_record(document, asset=asset, mint=mint)
    except ProviderEvidenceError:
        raise ExactRecordError("price_invalid") from None


def _parse_price_record(document: ProviderDocument, *, asset: str, mint: str) -> ExactPriceRecord:
    _identity(asset, mint)
    _document(document, "jupiter-price-v3")
    parameters = document.parameters
    ids = parameters.get("ids")
    if type(ids) is not str or mint not in ids.split(","):
        raise _invalid()
    payload = document.decode()
    if type(payload) is not dict or type(payload.get(mint)) is not dict:
        raise _invalid()
    info = payload[mint]
    price = decimal_text(info.get("usdPrice"), positive=True)
    block_id = _integer(info.get("blockId"), minimum=0, maximum=2**64 - 1)
    decimals = info.get("decimals")
    if decimals is not None:
        decimals = _integer(decimals, minimum=0, maximum=255)
    return _new(ExactPriceRecord, asset=asset, mint=mint, price=price,
                block_id=block_id, decimals=decimals, document=document)


def parse_candle_records(document: ProviderDocument, *, asset: str,
                         mint: str) -> tuple[ExactCandleRecord, ...]:
    """Derive ordered, complete requested minutes, retaining exact source units.

    This layer validates every returned row, including excluded older/forming
    rows. It does not fill missing intervals or claim request-window coverage.
    Duplicate rows must agree on all consumed source values before exclusion.
    """
    try:
        return _parse_candle_records(document, asset=asset, mint=mint)
    except ExactRecordError:
        raise
    except ProviderEvidenceError:
        raise ExactRecordError("candles_invalid") from None


def _parse_candle_records(document: ProviderDocument, *, asset: str,
                          mint: str) -> tuple[ExactCandleRecord, ...]:
    _identity(asset, mint)
    _document(document, "birdeye-ohlcv-v3")
    parameters = document.parameters
    expected = {"address": mint, "type": "1m", "currency": "usd",
                "chart_type": "price", "ui_amount_mode": "raw", "mode": "range"}
    if any(type(parameters.get(name)) is not str or parameters[name] != value
           for name, value in expected.items()):
        raise _invalid()
    padding = parameters.get("padding")
    if not (padding is False or type(padding) is str and padding == "false"):
        raise _invalid()
    start = _integer(parameters.get("time_from"), minimum=0, maximum=MAX_PROVIDER_TIMESTAMP)
    cutoff = _integer(parameters.get("time_to"), minimum=0, maximum=MAX_PROVIDER_TIMESTAMP)
    if start >= cutoff or start % 60 or cutoff % 60:
        raise _invalid()
    payload = document.decode()
    if type(payload) is not dict or payload.get("success") is not True:
        raise _invalid()
    body = payload.get("data")
    if type(body) is not dict or type(body.get("is_scaled_ui_token")) is not bool:
        raise _invalid()
    scaled = body["is_scaled_ui_token"]
    multiplier = None
    if "multiplier" in body:
        multiplier = decimal_text(body["multiplier"], positive=True)
    rows = body.get("items")
    if type(rows) is not list or len(rows) > MAX_CANDLE_ROWS:
        raise _invalid()
    by_start: dict[int, ExactCandleRecord] = {}
    for row in rows:
        if type(row) is not dict:
            raise _invalid()
        stamp = _integer(row.get("unix_time"), minimum=1, maximum=MAX_PROVIDER_TIMESTAMP)
        if stamp % 60 or stamp > cutoff:
            raise _invalid()
        if (row.get("address") != mint or row.get("type") != "1m"
                or row.get("currency") != "usd"):
            raise _invalid()
        prices = {name: decimal_text(row.get(name), positive=True) for name in ("o", "h", "l", "c")}
        volume = decimal_text(row.get("v"))
        volume_usd = decimal_text(row.get("v_usd"))
        opening, high, low, close = (Decimal(prices[name]) for name in ("o", "h", "l", "c"))
        if not low <= min(opening, close) <= max(opening, close) <= high:
            raise _invalid()
        record = _new(ExactCandleRecord, asset=asset, mint=mint, start=stamp,
                      open=prices["o"], high=prices["h"], low=prices["l"], close=prices["c"],
                      volume=volume, volume_usd=volume_usd, is_scaled_ui_token=scaled,
                      multiplier=multiplier, document=document)
        previous = by_start.get(stamp)
        if previous is not None and record != previous:
            raise ExactRecordError("candles_revision")
        by_start[stamp] = record
    return tuple(by_start[stamp] for stamp in sorted(by_start) if start <= stamp and stamp + 60 <= cutoff)
