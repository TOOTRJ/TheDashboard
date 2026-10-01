"""Deterministic USD-reference accounting for uncalibrated cost scenarios.

This is a research execution assumption, not a Solana quote/fill, USDC account,
or calibrated liquidity model. Fractions of a base token are hypothetical; token
decimals, fixed/network fees, capacity, delay, and rejection are not modeled.
All arithmetic is staged and finite; display rounding never enters the ledger.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import math
from typing import Mapping

from .market_validation import (
    MarketValueError, finite_number, nonnegative_value, positive_price,
    position_value, trade_return,
)

EXECUTION_VERSION = "usd-reference-percentage-cost-v1"
EXECUTION_POLICY = {
    "version": EXECUTION_VERSION,
    "account_currency": "USD",
    "valuation": "reference_mark",
    "cost_assumptions": "uncalibrated_scenario",
}


def _strict_record(value, names):
    if not isinstance(value, Mapping) or set(value) != set(names):
        raise MarketValueError()


@dataclass(frozen=True)
class ExecutionConfig:
    fee_bps: float = 0.0
    half_spread_bps: float = 0.0
    slippage_bps: float = 0.0

    def __post_init__(self):
        for name in ("fee_bps", "half_spread_bps", "slippage_bps"):
            object.__setattr__(self, name, nonnegative_value(getattr(self, name)))
        if self.fee_bps >= 10_000 or self.half_spread_bps + self.slippage_bps >= 10_000:
            raise MarketValueError()

    @classmethod
    def from_dict(cls, value) -> ExecutionConfig:
        _strict_record(value, ("fee_bps", "half_spread_bps", "slippage_bps"))
        return cls(**value)

    def to_dict(self) -> dict:
        return asdict(self)

    def policy(self) -> dict:
        return {"version": EXECUTION_VERSION, "account_currency": "USD",
                "valuation": "reference_mark", "cost_assumptions": "uncalibrated_scenario",
                "config": self.to_dict()}


@dataclass(frozen=True)
class EntryFill:
    reference_price: float
    fill_price: float
    quantity: float
    notional: float
    fee: float
    cash_debit: float
    spread_cost: float
    slippage_cost: float

    def __post_init__(self):
        for field in fields(self):
            validator = nonnegative_value if field.name in ("fee", "spread_cost", "slippage_cost") else positive_price
            object.__setattr__(self, field.name, validator(getattr(self, field.name)))

    @classmethod
    def from_dict(cls, value) -> EntryFill:
        _strict_record(value, (field.name for field in fields(cls)))
        return cls(**value)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExitFill:
    kind: str
    reference_price: float
    fill_price: float
    quantity: float
    notional: float
    fee: float
    cash_credit: float
    spread_cost: float
    slippage_cost: float
    gross_pnl: float
    net_pnl: float
    net_return: float

    def __post_init__(self):
        if self.kind not in ("fill", "writeoff"):
            raise MarketValueError()
        for field in fields(self):
            if field.name == "kind":
                continue
            validator = finite_number if field.name in ("gross_pnl", "net_pnl", "net_return") else nonnegative_value
            object.__setattr__(self, field.name, validator(getattr(self, field.name)))
        positive_price(self.quantity)
        if self.kind == "fill":
            for value in (self.reference_price, self.fill_price, self.notional, self.cash_credit):
                positive_price(value)
        elif any(getattr(self, name) != 0 for name in (
                "reference_price", "fill_price", "notional", "fee", "cash_credit", "spread_cost", "slippage_cost")):
            raise MarketValueError()

    @classmethod
    def from_dict(cls, value) -> ExitFill:
        _strict_record(value, (field.name for field in fields(cls)))
        return cls(**value)

    def to_dict(self) -> dict:
        return asdict(self)


def _config(config):
    if not isinstance(config, ExecutionConfig):
        raise MarketValueError()
    # Also detects bypassed/mutated frozen objects before any accounting work.
    if ExecutionConfig.from_dict(config.to_dict()) != config:
        raise MarketValueError()


def _product(left, right):
    """Preserve representable products; positive underflow is an error."""
    return position_value(nonnegative_value(left), 1.0, nonnegative_value(right))


def _cost(quantity, reference_price, bps):
    if bps == 0:
        return 0.0
    # Neither qty*reference nor reference*bps/10000 must fit individually.
    # Keep exponents separate until the final positive cost is constructed.
    mantissa, exponent = 1.0, 0
    for value in (quantity, reference_price, bps):
        part, power = math.frexp(positive_price(value))
        mantissa *= part
        exponent += power
    divisor, power = math.frexp(10_000.0)
    try:
        return positive_price(math.ldexp(mantissa / divisor, exponent - power))
    except OverflowError:
        raise MarketValueError() from None


def buy_fill(budget: float, reference_price: float, config: ExecutionConfig) -> EntryFill:
    """All-in cash debit is the requested budget; fees reduce invested notional."""
    _config(config)
    budget, reference = positive_price(budget), positive_price(reference_price)
    impact_bps = config.half_spread_bps + config.slippage_bps
    fill_price = positive_price(position_value(reference, 10_000.0, 10_000.0 + impact_bps))
    if impact_bps > 0 and fill_price <= reference:
        raise MarketValueError()
    notional = positive_price(position_value(budget, 10_000.0 + config.fee_bps, 10_000.0))
    fee = position_value(notional, 10_000.0, config.fee_bps)
    if config.fee_bps > 0 and (fee <= 0 or notional >= budget):
        raise MarketValueError()
    quantity = positive_price(position_value(notional, fill_price, 1.0))
    return EntryFill(reference, fill_price, quantity, notional, fee, budget,
                     _cost(quantity, reference, config.half_spread_bps),
                     _cost(quantity, reference, config.slippage_bps))


def validate_entry(entry: EntryFill, config: ExecutionConfig) -> None:
    if not isinstance(entry, EntryFill) or entry != buy_fill(entry.cash_debit, entry.reference_price, config):
        raise MarketValueError()


def mark_value(entry: EntryFill, mark: float) -> float:
    """Reference mark of explicit quantity, excluding hypothetical future fees."""
    if not isinstance(entry, EntryFill):
        raise MarketValueError()
    # Entry config is checked at construction/load; valuation charges no costs.
    positive_price(entry.notional)
    positive_price(entry.cash_debit)
    return positive_price(_product(positive_price(entry.quantity), positive_price(mark)))


def sell_fill(entry: EntryFill, reference_price: float, config: ExecutionConfig) -> ExitFill:
    validate_entry(entry, config)
    reference = positive_price(reference_price)
    impact_bps = config.half_spread_bps + config.slippage_bps
    fill_price = positive_price(position_value(reference, 10_000.0, 10_000.0 - impact_bps))
    if impact_bps > 0 and fill_price >= reference:
        raise MarketValueError()
    notional = positive_price(_product(entry.quantity, fill_price))
    fee = position_value(notional, 10_000.0, config.fee_bps)
    # Compute proceeds directly instead of notional - fee, retaining an ordinary
    # small positive balance when the fee approaches the configured upper bound.
    credit = positive_price(position_value(notional, 10_000.0, 10_000.0 - config.fee_bps))
    if config.fee_bps > 0 and (fee <= 0 or credit >= notional):
        raise MarketValueError()
    gross = finite_number(notional - entry.notional)
    net = finite_number(credit - entry.cash_debit)
    return ExitFill("fill", reference, fill_price, entry.quantity, notional, fee, credit,
                    _cost(entry.quantity, reference, config.half_spread_bps),
                    _cost(entry.quantity, reference, config.slippage_bps),
                    gross, net, trade_return(entry.cash_debit, credit))


def writeoff_fill(entry: EntryFill) -> ExitFill:
    """Explicit terminal loss is a write-off, not a zero-price market fill."""
    if not isinstance(entry, EntryFill):
        raise MarketValueError()
    EntryFill.from_dict(entry.to_dict())
    return ExitFill("writeoff", 0.0, 0.0, entry.quantity, 0.0, 0.0, 0.0, 0.0, 0.0,
                    -entry.notional, -entry.cash_debit, -1.0)


def execution_record(config: ExecutionConfig, entry: EntryFill,
                     exit: ExitFill | None = None) -> dict:
    validate_entry(entry, config)
    if exit is not None:
        if not isinstance(exit, ExitFill):
            raise MarketValueError()
        expected = writeoff_fill(entry) if exit.kind == "writeoff" else sell_fill(entry, exit.reference_price, config)
        if exit != expected:
            raise MarketValueError()
    return {"version": EXECUTION_VERSION, "account_currency": "USD", "config": config.to_dict(),
            "entry": entry.to_dict(), "exit": None if exit is None else exit.to_dict()}


def parse_execution(record: Mapping) -> tuple[ExecutionConfig, EntryFill, ExitFill | None]:
    """Strictly recompute persisted evidence, rejecting changed or unknown policy."""
    _strict_record(record, ("version", "account_currency", "config", "entry", "exit"))
    if record["version"] != EXECUTION_VERSION or record["account_currency"] != "USD":
        raise MarketValueError()
    config = ExecutionConfig.from_dict(record["config"])
    entry = EntryFill.from_dict(record["entry"])
    exit = None if record["exit"] is None else ExitFill.from_dict(record["exit"])
    execution_record(config, entry, exit)
    return config, entry, exit
