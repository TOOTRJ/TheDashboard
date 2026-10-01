"""Explicit data forks for a quiescent legacy engine, without runnable probes.

This C1 boundary preserves binary64 v1 values; it is neither a decimal ledger
adapter nor a restart/checkpoint format. Capture never calls a Probe constructor,
reporting property, clock, feed, or history-attachment method. The owner must
hold its transition lock and separately verify shared candle-history ownership.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from types import MappingProxyType

from .equity_metrics import EquityHistory, EquityObservation, EquitySample
from .execution import ExecutionConfig
from .genome import Genome
from .probe import Probe, _SignalIntent
from .types import ProbeState, TradeRecord
from ..market.candles import CandleHistory, CandleSnapshot, MinuteCandle, _Asset, _Series


class StateComponentError(ValueError):
    """State does not match this explicitly supported data-only boundary."""


@dataclass(frozen=True, slots=True)
class ProbeData:
    """Detached, privately owned data, never a Probe with fallback resources.

    Nested containers are deliberately mutable for a subsequent data fork.
    A publishing owner must seal this DTO behind a defensive-copy interface.
    ``uses_candle_history`` records a relationship, not the history itself.
    """

    attributes: dict
    uses_candle_history: bool


_PROBE_FIELDS = frozenset({
    "strategy_profile", "probe_id", "probe_name", "genome", "mode", "execution_config",
    "initial_capital", "capital", "peak_capital", "_max_drawdown", "_equity_history",
    "_valuation_assets", "state", "born_at", "died_at", "death_reason", "birth_tick",
    "_tick_count", "open_positions", "closed_trades", "_evicted_trade_count",
    "_evicted_winning_trades", "_evicted_trade_pnl", "_marks", "_quote_observations",
    "_candle_cursors", "_pending_intents", "_signals_after",
})
_PROBE_OPTIONAL = frozenset({"_has_persisted_offspring"})
_PROBE_RESOURCES = frozenset({"_clock", "_candle_history", "_id_factory", "_monotonic_clock"})
_GENES = frozenset({"rsi_period", "rsi_oversold", "rsi_overbought", "ema_fast", "ema_slow",
    "volume_threshold", "position_size_pct", "stop_loss_pct", "take_profit_pct",
    "max_open_positions", "timeframe_minutes", "benchmark_target_pct",
    "reproduce_target_dollars", "death_drawdown_pct", "num_assets"})
_TRADE_NUMBERS = frozenset({"entry_price", "amount"})
_TRADE_OPTIONAL_NUMBERS = frozenset({"exit_price", "pnl", "pnl_pct", "signal_rsi",
    "signal_ema_fast", "signal_ema_slow", "signal_volume_ratio", "stop_loss_price", "take_profit_price"})
_CANDLE_NUMBERS = frozenset({"open", "high", "low", "close", "volume"})
_CANDLE_TEXT = frozenset({"asset", "source", "quote_currency", "volume_unit"})
_SHAPES = {
    Genome: _GENES | {"assets", "generation", "parent_ids"},
    ExecutionConfig: {"fee_bps", "half_spread_bps", "slippage_bps"},
    TradeRecord: _TRADE_NUMBERS | _TRADE_OPTIONAL_NUMBERS | {"trade_id", "probe_id", "pair", "side",
        "exit_reason", "opened_at", "closed_at", "execution"},
    _SignalIntent: {"candle_end", "receipt_boundary", "action", "trade_id", "signals"},
    EquityObservation: {"equity", "observed_at", "valid_until"},
    EquitySample: {"endpoint", "equity", "observed_at", "valid_until"},
    EquityHistory: {"capacity", "returns", "last_observation", "last_sample", "missing_periods",
        "invalid_intervals", "window_start_endpoint", "_processed_endpoint", "_invalid_arithmetic",
        "_statistics_returns", "_statistics"},
    MinuteCandle: _CANDLE_NUMBERS | _CANDLE_TEXT | {"start"},
    CandleSnapshot: _CANDLE_NUMBERS | _CANDLE_TEXT | {"timeframe_minutes", "start", "end", "closes",
        "volumes", "emas", "completed_count", "previous_emas", "previous_end"},
    _Series: {"timeframe", "pending", "closes", "volumes", "emas", "completed_count", "snapshot"},
    _Asset: {"minutes", "series", "identity"},
    CandleHistory: {"_assets"},
}


def _require(condition: bool) -> None:
    if not condition:
        raise StateComponentError("unsupported or malformed state component")


def _number(value, *, nonnegative=False) -> bool:
    try:
        return (type(value) in (int, float) and math.isfinite(value)
                and (not nonnegative or value >= 0))
    except OverflowError:
        return False


def _integer(value, *, minimum=0) -> bool:
    return type(value) is int and value >= minimum


def _stamp(value) -> bool:
    # Current ledger clocks normalize to timezone.utc. Do not retain a custom
    # tzinfo object that could hide operational state or execute conversion code.
    return type(value) is datetime and value.tzinfo is timezone.utc


def _sequence(value, container, item_type) -> bool:
    return type(value) is container and all(type(item) is item_type for item in value)


def _mapping(value, key_type, value_type) -> bool:
    return type(value) is dict and all(type(key) is key_type and type(item) is value_type
                                      for key, item in value.items())


def _number_map(value) -> bool:
    return type(value) is dict and all(type(key) is str and _number(item, nonnegative=True)
                                      for key, item in value.items())


def _plain_data(value, active=None, depth=0) -> None:
    """Execution/signals are plain data, not a place for other typed objects."""
    _require(depth <= 64)
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        _require(math.isfinite(value))
        return
    _require(type(value) in (dict, list))
    active = set() if active is None else active
    _require(id(value) not in active)
    active.add(id(value))
    if type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str)
            _plain_data(item, active, depth + 1)
    else:
        for item in value:
            _plain_data(item, active, depth + 1)
    active.remove(id(value))


def _validate_probe_attributes(values) -> None:
    _require(type(values) is dict and _PROBE_FIELDS <= values.keys()
             and not values.keys() - (_PROBE_FIELDS | _PROBE_OPTIONAL))
    for name in ("strategy_profile", "probe_id", "probe_name", "mode"):
        _require(type(values[name]) is str)
    _require(type(values["genome"]) is Genome and type(values["execution_config"]) is ExecutionConfig)
    for name in ("initial_capital", "capital", "peak_capital", "_max_drawdown", "_signals_after"):
        _require(_number(values[name], nonnegative=True))
    _require(_number(values["_evicted_trade_pnl"]))
    for name in ("birth_tick", "_tick_count", "_evicted_trade_count", "_evicted_winning_trades"):
        _require(_integer(values[name]))
    _require(type(values["_equity_history"]) is EquityHistory and values["_valuation_assets"] is None)
    _require(type(values["state"]) is ProbeState and _stamp(values["born_at"]))
    _require(values["died_at"] is None or _stamp(values["died_at"]))
    _require(values["death_reason"] is None or type(values["death_reason"]) is str)
    _require(_mapping(values["open_positions"], str, TradeRecord)
             and _sequence(values["closed_trades"], list, TradeRecord))
    _require(_number_map(values["_marks"]) and _number_map(values["_candle_cursors"]))
    observations = values["_quote_observations"]
    _require(type(observations) is dict and all(type(asset) is str and type(pair) is tuple
             and len(pair) == 2 and all(_number(item, nonnegative=True) for item in pair)
             for asset, pair in observations.items()))
    _require(_mapping(values["_pending_intents"], str, _SignalIntent))
    if "_has_persisted_offspring" in values:
        _require(type(values["_has_persisted_offspring"]) is bool)


def _validate_object(value) -> None:
    kind, fields = type(value), vars(value)
    _require(fields.keys() == _SHAPES[kind])
    if kind is Genome:
        _require(all(_number(fields[name]) for name in _GENES)
                 and _integer(value.generation) and _sequence(value.assets, list, str)
                 and _sequence(value.parent_ids, list, str))
    elif kind is ExecutionConfig:
        _require(all(_number(item, nonnegative=True) for item in fields.values())
                 and value.fee_bps < 10000 and value.half_spread_bps + value.slippage_bps < 10000)
    elif kind is TradeRecord:
        _require(all(type(fields[name]) is str for name in ("trade_id", "probe_id", "pair", "side")))
        _require(all(_number(fields[name]) for name in _TRADE_NUMBERS))
        _require(all(fields[name] is None or _number(fields[name]) for name in _TRADE_OPTIONAL_NUMBERS))
        _require((value.exit_reason is None or type(value.exit_reason) is str) and _stamp(value.opened_at)
                 and (value.closed_at is None or _stamp(value.closed_at))
                 and (value.execution is None or type(value.execution) is dict))
        _plain_data(value.execution)
    elif kind is _SignalIntent:
        _require(_number(value.candle_end, nonnegative=True) and _number(value.receipt_boundary, nonnegative=True)
                 and type(value.action) is str and value.action in ("entry", "exit")
                 and (value.trade_id is None or type(value.trade_id) is str) and type(value.signals) is dict)
        _plain_data(value.signals)
    elif kind in (EquityObservation, EquitySample):
        _require(all(_number(fields[name], nonnegative=True) for name in ("equity", "observed_at", "valid_until")))
        if kind is EquitySample:
            _require(_integer(value.endpoint))
    elif kind is EquityHistory:
        _require(_integer(value.capacity, minimum=2) and type(value.returns) is tuple
                 and all(_number(item) for item in value.returns)
                 and (value.last_observation is None or type(value.last_observation) is EquityObservation)
                 and (value.last_sample is None or type(value.last_sample) is EquitySample)
                 and _integer(value.missing_periods) and _integer(value.invalid_intervals)
                 and all(fields[name] is None or _integer(fields[name]) for name in ("window_start_endpoint", "_processed_endpoint"))
                 and type(value._invalid_arithmetic) is bool
                 and (value._statistics_returns is None or (type(value._statistics_returns) is tuple
                      and all(_number(item) for item in value._statistics_returns)))
                 and type(value._statistics) is tuple
                 and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str
                         and (item[1] is None or type(item[1]) in (str, bool, int, float))
                         for item in value._statistics))
    elif kind in (MinuteCandle, CandleSnapshot):
        _require(all(type(fields[name]) is str for name in _CANDLE_TEXT)
                 and all(_number(fields[name], nonnegative=True) for name in _CANDLE_NUMBERS)
                 and _integer(value.start))
        if kind is CandleSnapshot:
            _require(_integer(value.end) and _integer(value.timeframe_minutes, minimum=1)
                     and _integer(value.completed_count) and type(value.closes) is tuple
                     and type(value.volumes) is tuple
                     and all(_number(item) for item in (*value.closes, *value.volumes))
                     and (value.previous_end is None or _integer(value.previous_end)))
            for mapping in (value.emas, value.previous_emas):
                _require(type(mapping) is MappingProxyType and all(type(key) is int and _number(item)
                                                                  for key, item in mapping.items()))
    elif kind is _Series:
        _require(_integer(value.timeframe, minimum=1) and _sequence(value.pending, list, MinuteCandle)
                 and type(value.closes) is list and type(value.volumes) is list
                 and all(_number(item) for item in (*value.closes, *value.volumes))
                 and type(value.emas) is dict and all(type(key) is int and _number(item) for key, item in value.emas.items())
                 and _integer(value.completed_count) and (value.snapshot is None or type(value.snapshot) is CandleSnapshot))
    elif kind is _Asset:
        _require(type(value.minutes) is OrderedDict and all(type(key) is int and type(item) is MinuteCandle
                     and key == item.start for key, item in value.minutes.items()))
        _require(type(value.series) is dict and value.series.keys() == set(range(1, 61))
                 and all(type(key) is int and type(item) is _Series and key == item.timeframe
                         for key, item in value.series.items()))
        _require(value.identity is None or (_sequence(value.identity, tuple, str) and len(value.identity) == 3))
    elif kind is CandleHistory:
        _require(bool(value._assets) and _mapping(value._assets, str, _Asset))


def _validate_graph(value, active=None, visited=None) -> None:
    active, visited = set() if active is None else active, set() if visited is None else visited
    kind = type(value)
    if value is None or kind in (str, bool, int, ProbeState):
        return
    if kind is float:
        _require(math.isfinite(value))
        return
    if kind is datetime:
        _require(_stamp(value))
        return
    _require(kind in (dict, list, tuple, OrderedDict, MappingProxyType) or kind in _SHAPES)
    _require(id(value) not in active)
    if id(value) in visited:
        return
    active.add(id(value))
    if kind in (dict, OrderedDict, MappingProxyType):
        for key, item in value.items():
            _require(type(key) in (str, int))
            _validate_graph(item, active, visited)
    elif kind in (list, tuple):
        for item in value:
            _validate_graph(item, active, visited)
    else:
        _validate_object(value)
        for item in vars(value).values():
            _validate_graph(item, active, visited)
    active.remove(id(value))
    visited.add(id(value))


def _copy_graph(value, memo):
    kind = type(value)
    if value is None or kind in (str, bool, int, float, datetime, ProbeState):
        return value
    if id(value) in memo:
        return memo[id(value)]
    if kind in (dict, OrderedDict):
        result = {} if kind is dict else OrderedDict()
        memo[id(value)] = result
        result.update((key, _copy_graph(item, memo)) for key, item in value.items())
    elif kind is list:
        result = []
        memo[id(value)] = result
        result.extend(_copy_graph(item, memo) for item in value)
    elif kind is tuple:
        result = tuple(_copy_graph(item, memo) for item in value)
        memo[id(value)] = result
    elif kind is MappingProxyType:
        result = MappingProxyType({key: _copy_graph(item, memo) for key, item in value.items()})
        memo[id(value)] = result
    else:
        result = object.__new__(kind)
        memo[id(value)] = result
        for name, item in vars(value).items():
            object.__setattr__(result, name, _copy_graph(item, memo))
    return result


def capture_probe_data(probe: Probe, *, memo=None) -> ProbeData:
    """Capture raw quiescent data; the owner supplies a fresh capture-wide memo."""
    _require(type(probe) is Probe)
    fields = vars(probe)
    _require((_PROBE_FIELDS | _PROBE_RESOURCES) <= fields.keys()
             and not fields.keys() - (_PROBE_FIELDS | _PROBE_OPTIONAL | _PROBE_RESOURCES))
    _require(all(callable(fields[name]) for name in ("_clock", "_id_factory", "_monotonic_clock"))
             and (fields["_candle_history"] is None
             or type(fields["_candle_history"]) is CandleHistory))
    values = {name: item for name, item in fields.items() if name not in _PROBE_RESOURCES}
    _validate_probe_attributes(values)
    _validate_graph(values)
    # This wrapper is ephemeral. Memoizing its id across captures could reuse
    # a freed dict address and substitute another probe's entire attributes.
    # The real source values remain owned by the quiescent controller graph.
    memo = {} if memo is None else memo
    return ProbeData({name: _copy_graph(item, memo) for name, item in values.items()},
                     fields["_candle_history"] is not None)


def fork_probe_data(data: ProbeData, *, memo=None) -> ProbeData:
    """Copy a DTO without acquiring a clock or becoming an executable Probe."""
    _require(type(data) is ProbeData and type(data.uses_candle_history) is bool)
    _validate_probe_attributes(data.attributes)
    _validate_graph(data.attributes)
    return ProbeData(_copy_graph(data.attributes, {} if memo is None else memo), data.uses_candle_history)


def fork_candle_history(history: CandleHistory, *, memo=None) -> CandleHistory:
    """Copy every EMA accumulator and pending bucket, without replay or I/O."""
    _require(type(history) is CandleHistory)
    _validate_graph(history)
    return _copy_graph(history, {} if memo is None else memo)
