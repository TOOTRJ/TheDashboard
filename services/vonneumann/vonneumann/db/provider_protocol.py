"""Independent v5 source validation around the unchanged v4 economic model.

Only local copies are projected for model validation. The caller retains the
original v5 source envelope for journaling. Document manifests do not prove raw
response derivation or authenticity; the worker's exact parser is trusted.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from . import lifecycle_protocol as model
from .command_protocol import CommandValidationError, canonical_json, _keys
from ..market.provider_contract import (
    ASSET, ProviderSourceError, source_policy, clock_us, validate_source_state,
    validate_frame, check_frame, validate_history, MAX_HISTORY_BARS,
)

_EMPTY_EMA = {"count": 0, "last_end": None, "closes": [], "values": {}, "previous": {}}
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _require(condition):
    if not condition:
        raise CommandValidationError("Provider transition validation failed")


def _safe(function):
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, KeyError, OverflowError, AttributeError, RecursionError):
            raise CommandValidationError("Provider transition validation failed") from None
    return wrapped


def _same(one, two):
    return canonical_json(one) == canonical_json(two)


def _datetime_us(value):
    _require(type(value) is str and len(value) <= 64)
    parsed = datetime.fromisoformat(value)
    _require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0
             and parsed.isoformat() == value)
    delta = parsed - _EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


@_safe
def validate_configuration(config, owner_id, run_id, initial_cash):
    _keys(config, {"durability_contract_version", "execution", "rehearsal", "source_policy"})
    _require(type(config["durability_contract_version"]) is int and config["durability_contract_version"] == 5)
    policy = config["source_policy"]
    _require(type(policy) is dict and "epoch" in policy and _same(policy, source_policy(policy["epoch"])))
    _require(config["rehearsal"]["asset"] == ASSET)
    projected = {key: deepcopy(config[key]) for key in ("execution", "rehearsal")}
    projected["durability_contract_version"] = 4
    model.validate_configuration(projected, owner_id, run_id, initial_cash)


def _seed_ema(bars):
    from ..core.exact_rehearsal import _append_candle, ExactObservation
    _require(len(bars) == 61)
    engine = {"ema": deepcopy(_EMPTY_EMA)}
    for end, close, _ in bars:
        _append_candle(engine, ExactObservation(end, close, end, close))
    return engine["ema"]


def _state_source(state):
    _keys(state, {"version", "owner_id", "run_id", "revision", "status", "reserve",
                  "accounts", "positions", "engine", "source"})
    source = state["source"]
    validate_source_state(source)
    engine = state["engine"]
    _require(engine["config"]["asset"] == ASSET)
    frame = source["last_quote"]
    quote = None if frame is None else {"timestamp": frame["decision_second"], "price": frame["quote"]["price"]}
    _require(_same(engine["last_quote"], quote))
    bars = source["bars"]
    ema = engine["ema"]
    _require(type(ema) is dict and type(ema.get("count")) is int and ema["count"] >= 61
             and ema["last_end"] == bars[-1][0]
             and _same(ema["closes"], [row[1] for row in bars]))
    if frame is None:
        _require(source["quote_sequence"] == 0 and _same(ema, _seed_ema(bars))
                 and engine["decision_timestamp"] is None
                 and all(row["cursor"] is None and row["pending"] is None for row in engine["members"]))
    return source


@_safe
def model_transition(transition):
    """Detach and remove only v5 additions and the prequote seed projection.

    V4 requires a quote whenever its EMA is nonempty. Until the first accepted
    protection, v5 separately recomputes its complete seed and verifies no
    seed change; the local model projection uses the original empty EMA on
    both sides. Once a quote exists, the actual EMA continuation is validated.
    """
    projected = deepcopy(transition)
    projected["evidence"].pop("source")
    before = projected["before"]
    prequote = before is None or before["engine"]["last_quote"] is None
    for key in ("before", "after"):
        state = projected[key]
        if state is not None:
            state.pop("source")
            if prequote:
                state["engine"]["ema"] = deepcopy(_EMPTY_EMA)
    return projected


@_safe
def validate_transition(transition, operations, owner_id, run_id, base_revision):
    _keys(transition, {"version", "before", "after", "evidence", "events"})
    # Bound the direct validator too; normal command preparation applies the
    # stricter whole PostgreSQL-spacing payload limit independently.
    _require(len(canonical_json(transition)) <= 262144)
    before, after, evidence = (transition[key] for key in ("before", "after", "evidence"))
    _keys(evidence, {"kind", "inputs", "observation", "actions", "control", "source"})
    envelope = evidence["source"]
    _keys(envelope, {"version", "phase", "frame", "history", "wall_us", "monotonic_us"})
    _require(type(envelope["version"]) is int and envelope["version"] == 1
             and envelope["phase"] == evidence["kind"])
    wall, mono = envelope["wall_us"], envelope["monotonic_us"]
    _require(type(wall) is int and type(mono) is int and 0 <= wall <= 10**16 and 0 <= mono <= 10**16)
    inputs = evidence["inputs"]
    _require(_datetime_us(inputs["wall_at"]) == wall)
    _require(type(inputs["monotonic_at"]) is str and len(inputs["monotonic_at"]) <= 64)
    _require(clock_us(float.fromhex(inputs["monotonic_at"]), upper=True) == mono)
    event_us = _datetime_us(inputs["event_at"])
    _require(event_us % 1_000_000 == 0)
    event_second = event_us // 1_000_000
    following = _state_source(after)
    prior = None if before is None else _state_source(before)
    if prior is not None:
        _require(following["epoch"] == prior["epoch"])
        if prior["last_quote"] is not None:
            _require(wall >= prior["last_quote"]["decision_wall_us"]
                     and mono >= prior["last_quote"]["decision_monotonic_us"])
    frame, history = envelope["frame"], envelope["history"]
    kind = evidence["kind"]
    control = evidence["control"]
    recovering = kind == "control" and type(control) is dict and control.get("action") == "recover"
    quoted = kind in {"protective", "decision"} or recovering
    _require(kind in {"bootstrap", "protective", "decision", "control"})
    _require((kind == "bootstrap") == (before is None))
    observation = evidence["observation"]
    if quoted:
        _require(frame is not None)
        check_frame(frame, wall_us=wall, monotonic_us=mono)
        _require(event_second == frame["decision_second"])
        _keys(observation, {"timestamp", "price", "candle_end", "candle_close"})
        _require(observation["timestamp"] == frame["decision_second"]
                 and type(observation["timestamp"]) is int
                 and observation["price"] == frame["quote"]["price"])
    else:
        _require(frame is None and observation is None
                 and event_us <= wall <= event_us + 1_000_000)
    if kind == "bootstrap":
        _require(history is not None and following["last_quote"] is None
                 and following["quote_sequence"] == 0)
        bars = validate_history(history, prior_bars=[], seed=True, wall_us=wall, monotonic_us=mono)
        _require(_same(following["bars"], bars) and _same(after["engine"]["ema"], _seed_ema(bars)))
    elif kind == "protective":
        _require(history is None)
        validate_frame(frame, prior_source=prior, epoch=prior["epoch"])
        expected = deepcopy(prior)
        expected.update(quote_sequence=frame["sequence"], last_quote=deepcopy(frame))
        _require(_same(following, expected)
                 and observation["candle_end"] is None and observation["candle_close"] is None)
    elif kind == "decision" or recovering:
        _require(prior["last_quote"] is not None and _same(frame, prior["last_quote"]))
        expected = deepcopy(prior)
        halted = before["engine"]["lifecycle"]["risk"]["active"]
        if kind == "decision" and halted:
            _require(history is None)
        if history is not None:
            added = validate_history(history, prior_bars=prior["bars"], seed=False, wall_us=wall, monotonic_us=mono)
            expected["bars"] = (prior["bars"] + added)[-MAX_HISTORY_BARS:]
        _require(_same(following, expected))
        candle = following["bars"][-1] if recovering or history is not None else None
        _require(observation["candle_end"] == (None if candle is None else candle[0])
                 and observation["candle_close"] == (None if candle is None else candle[1]))
        if kind == "decision" and not halted:
            _require(following["bars"][-1][0] == (wall - 5_000_000) // 900_000_000 * 900)
        if recovering:
            _require(candle[0] * 1_000_000 + 5_000_000 <= wall
                     and candle[0] == (wall - 5_000_000) // 900_000_000 * 900)
    else:
        _require(history is None and _same(following, prior))
    if before is not None and before["engine"]["last_quote"] is None:
        _require(kind in {"protective", "control"} and not recovering
                 and _same(after["engine"]["ema"], before["engine"]["ema"]))
    model.validate_transition(model_transition(transition), operations, owner_id, run_id, base_revision)
