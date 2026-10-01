"""Exact, pure USD-reference plans for the next durable accounting policy.

This is a new research policy, not an implicit conversion of the existing
binary64 execution model and not Solana token-atomic settlement. Cash uses 36
decimal places, prices/quantities 18, and basis-point settings 6. All arithmetic
uses integers; ambient Decimal precision, rounding and traps cannot affect it.
The live engine continues to use execution.py until the complete state cutover.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re


DECIMAL_EXECUTION_VERSION = "usd-reference-decimal-v2"
CASH_SCALE = 36
PRICE_SCALE = 18
QUANTITY_SCALE = 18
BPS_SCALE = 6
MAX_VALUE = 10**36
RATE_DENOMINATOR = 10_000 * 10**BPS_SCALE
_PLAIN_DECIMAL = re.compile(r"(0|[1-9][0-9]*)(?:\.([0-9]+))?\Z", re.ASCII)


class DecimalExecutionError(ValueError):
    """A plan cannot satisfy this version's exact units and bounds."""


def _units(value: str, scale: int, *, positive: bool = False) -> int:
    if type(value) is not str or len(value) > 75:
        raise DecimalExecutionError("a bounded plain decimal string is required")
    match = _PLAIN_DECIMAL.fullmatch(value)
    if match is None or len(match[2] or "") > scale:
        raise DecimalExecutionError("amount does not fit the declared decimal grid")
    units = int(match[1]) * 10**scale + int((match[2] or "").ljust(scale, "0") or "0")
    if units > MAX_VALUE * 10**scale or (positive and units == 0):
        raise DecimalExecutionError("amount is outside the declared range")
    return units


def _text(units: int, scale: int) -> str:
    sign = "-" if units < 0 else ""
    whole, fraction = divmod(abs(units), 10**scale)
    tail = str(fraction).rjust(scale, "0").rstrip("0")
    return sign + str(whole) + ("." + tail if tail else "")


def _bounded(units: int, scale: int, *, positive: bool = False) -> int:
    if units < 0 or units > MAX_VALUE * 10**scale or (positive and units == 0):
        raise DecimalExecutionError("calculation is outside the declared range")
    return units


def _ceil_ratio(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def _exact_record(actual: object, expected: object) -> bool:
    # Avoid bool/int equality and serialization coercion of unsupported types.
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return (actual.keys() == expected.keys()
                and all(_exact_record(actual[key], item) for key, item in expected.items()))
    return actual == expected


@dataclass(frozen=True, slots=True)
class DecimalExecutionConfig:
    fee_bps: str = "0"
    half_spread_bps: str = "0"
    slippage_bps: str = "0"
    _fee_units: int = field(init=False, repr=False)
    _impact_units: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        values = [_units(getattr(self, name), BPS_SCALE)
                  for name in ("fee_bps", "half_spread_bps", "slippage_bps")]
        if values[0] >= RATE_DENOMINATOR or values[1] + values[2] >= RATE_DENOMINATOR:
            raise DecimalExecutionError("fee and total adverse impact must be below 10000 bps")
        for name, value in zip(("fee_bps", "half_spread_bps", "slippage_bps"), values):
            object.__setattr__(self, name, _text(value, BPS_SCALE))
        object.__setattr__(self, "_fee_units", values[0])
        object.__setattr__(self, "_impact_units", values[1] + values[2])

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in ("fee_bps", "half_spread_bps", "slippage_bps")}

    @classmethod
    def from_dict(cls, value: object) -> DecimalExecutionConfig:
        if type(value) is not dict or value.keys() != {"fee_bps", "half_spread_bps", "slippage_bps"}:
            raise DecimalExecutionError("invalid exact execution configuration")
        return cls(**value)

    def policy(self) -> dict:
        return {"version": DECIMAL_EXECUTION_VERSION, "account_currency": "USD",
                "cost_assumptions": "uncalibrated_scenario", "valuation": "reference_mark",
                "cash_scale": CASH_SCALE, "quantity_scale": QUANTITY_SCALE,
                "price_scale": PRICE_SCALE, "bps_scale": BPS_SCALE,
                "rounding": {"buy_price": "up", "sell_price": "down",
                             "quantity": "down", "fee": "up", "residual": "retain_cash"},
                "config": self.to_dict()}


def _config(value: DecimalExecutionConfig) -> None:
    if type(value) is not DecimalExecutionConfig or DecimalExecutionConfig.from_dict(value.to_dict()) != value:
        raise DecimalExecutionError("invalid exact execution configuration")


@dataclass(frozen=True, slots=True)
class EntryPlan:
    budget: str
    reference_price: str
    config: DecimalExecutionConfig = field(default_factory=DecimalExecutionConfig)
    fill_price: str = field(init=False)
    quantity: str = field(init=False)
    notional: str = field(init=False)
    fee: str = field(init=False)
    cash_debit: str = field(init=False)
    residual_budget: str = field(init=False)

    def __post_init__(self) -> None:
        _config(self.config)
        budget = _units(self.budget, CASH_SCALE, positive=True)
        reference = _units(self.reference_price, PRICE_SCALE, positive=True)
        price = _bounded(_ceil_ratio(reference * (RATE_DENOMINATOR + self.config._impact_units),
                                     RATE_DENOMINATOR), PRICE_SCALE, positive=True)
        notional_cap = budget * RATE_DENOMINATOR // (RATE_DENOMINATOR + self.config._fee_units)
        quantity = _bounded(notional_cap // price, QUANTITY_SCALE, positive=True)
        # price18 * quantity18 is exactly cash36: no product rounding.
        notional = _bounded(quantity * price, CASH_SCALE, positive=True)
        fee = _ceil_ratio(notional * self.config._fee_units, RATE_DENOMINATOR)
        debit = _bounded(notional + fee, CASH_SCALE, positive=True)
        if debit > budget:
            raise DecimalExecutionError("entry exceeds its budget")
        values = {"budget": (budget, CASH_SCALE), "reference_price": (reference, PRICE_SCALE),
                  "fill_price": (price, PRICE_SCALE), "quantity": (quantity, QUANTITY_SCALE),
                  "notional": (notional, CASH_SCALE), "fee": (fee, CASH_SCALE),
                  "cash_debit": (debit, CASH_SCALE), "residual_budget": (budget - debit, CASH_SCALE)}
        for name, (value, scale) in values.items():
            object.__setattr__(self, name, _text(value, scale))

    def to_dict(self) -> dict:
        return {"version": DECIMAL_EXECUTION_VERSION, "config": self.config.to_dict(),
                **{name: getattr(self, name) for name in
                   ("budget", "reference_price", "fill_price", "quantity", "notional",
                    "fee", "cash_debit", "residual_budget")}}

    @classmethod
    def from_dict(cls, value: object) -> EntryPlan:
        if type(value) is not dict or not {"budget", "reference_price", "config"} <= value.keys():
            raise DecimalExecutionError("invalid entry evidence")
        result = cls(value["budget"], value["reference_price"], DecimalExecutionConfig.from_dict(value["config"]))
        if not _exact_record(value, result.to_dict()):
            raise DecimalExecutionError("entry evidence does not match the declared policy")
        return result


def _entry(entry: EntryPlan) -> None:
    if type(entry) is not EntryPlan or EntryPlan.from_dict(entry.to_dict()) != entry:
        raise DecimalExecutionError("invalid exact entry plan")


@dataclass(frozen=True, slots=True)
class ExitPlan:
    entry: EntryPlan
    reference_price: str | None
    kind: str = field(init=False)
    fill_price: str = field(init=False)
    quantity: str = field(init=False)
    notional: str = field(init=False)
    fee: str = field(init=False)
    cash_credit: str = field(init=False)
    gross_pnl: str = field(init=False)
    net_pnl: str = field(init=False)

    def __post_init__(self) -> None:
        _entry(self.entry)
        quantity = _units(self.entry.quantity, QUANTITY_SCALE, positive=True)
        if self.reference_price is None:
            kind, price, notional, fee = "writeoff", 0, 0, 0
        else:
            reference = _units(self.reference_price, PRICE_SCALE, positive=True)
            price = _bounded(reference * (RATE_DENOMINATOR - self.entry.config._impact_units)
                             // RATE_DENOMINATOR, PRICE_SCALE, positive=True)
            notional = _bounded(quantity * price, CASH_SCALE, positive=True)
            fee = _ceil_ratio(notional * self.entry.config._fee_units, RATE_DENOMINATOR)
            object.__setattr__(self, "reference_price", _text(reference, PRICE_SCALE))
            kind = "fill"
        credit = _bounded(notional - fee, CASH_SCALE)
        values = {"fill_price": _text(price, PRICE_SCALE), "quantity": self.entry.quantity,
                  "notional": _text(notional, CASH_SCALE), "fee": _text(fee, CASH_SCALE),
                  "cash_credit": _text(credit, CASH_SCALE),
                  "gross_pnl": _text(notional - _units(self.entry.notional, CASH_SCALE), CASH_SCALE),
                  "net_pnl": _text(credit - _units(self.entry.cash_debit, CASH_SCALE), CASH_SCALE)}
        object.__setattr__(self, "kind", kind)
        for name, value in values.items():
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict:
        return {"version": DECIMAL_EXECUTION_VERSION, "entry": self.entry.to_dict(),
                **{name: getattr(self, name) for name in
                   ("kind", "reference_price", "fill_price", "quantity", "notional", "fee",
                    "cash_credit", "gross_pnl", "net_pnl")}}

    @classmethod
    def from_dict(cls, value: object) -> ExitPlan:
        if type(value) is not dict or not {"entry", "reference_price"} <= value.keys():
            raise DecimalExecutionError("invalid exit evidence")
        result = cls(EntryPlan.from_dict(value["entry"]), value["reference_price"])
        if not _exact_record(value, result.to_dict()):
            raise DecimalExecutionError("exit evidence does not match the declared policy")
        return result


def debit_cash(cash: str, debit: str) -> str:
    return _text(_bounded(_units(cash, CASH_SCALE) - _units(debit, CASH_SCALE), CASH_SCALE), CASH_SCALE)


def credit_cash(cash: str, credit: str) -> str:
    return _text(_bounded(_units(cash, CASH_SCALE) + _units(credit, CASH_SCALE), CASH_SCALE), CASH_SCALE)


def transfer_cash(source: str, destination: str, amount: str) -> tuple[str, str]:
    """Plan both sides before a caller installs either balance."""
    return debit_cash(source, amount), credit_cash(destination, amount)


def mark_value(entry: EntryPlan, reference_price: str) -> str:
    _entry(entry)
    return _text(_bounded(_units(entry.quantity, QUANTITY_SCALE, positive=True)
                          * _units(reference_price, PRICE_SCALE, positive=True), CASH_SCALE), CASH_SCALE)
