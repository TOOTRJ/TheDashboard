"""Detached in-process state for the first DB-03A2C staging prerequisite.

Capture raw state under the controller's tick lock without running reports,
constructors, feed calls or optimizer operations. A snapshot exposes only fresh
data forks. It cannot execute a tick, install state, renew ownership or restore
a process. Current float accounting and original clocks remain unchanged.

The private graph deliberately is not a serialized checkpoint. In particular,
saved quote receipt times cannot confer freshness in another process. A future
transition coordinator must provide immutable decision evidence, exact economic
plans and stable identities, then install only the matching acknowledged state.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, fields
from datetime import datetime, timezone

from .colony_config import ColonyConfig, GeneOverride
from .evaluation import EvaluationCohort
from .execution import ExecutionConfig
from .genesis import GenesisController, _GenerationAggregate
from .genome import Genome
from .probe import Probe
from .search_random import SearchRandomStreams
from .state_components import ProbeData, capture_probe_data, fork_probe_data, fork_candle_history
from .strategy_fork import fork_strategy, fork_evaluation
from .strategies.base import EvolutionStrategy
from ..market.candles import CandleHistory
from ..market.feed import MarketTick, QuoteEvidence


ENGINE_FORK_VERSION = "engine-fork-v1"

# Explicit classification makes newly introduced controller fields fail closed.
# Operational latches, locks and acknowledgement flags may never be overwritten
# by installing an old candidate. They do not belong to the economic state.
OPERATIONAL_FIELDS = frozenset({
    "market_feed", "_on_event", "_persist_risk_status", "_tick_lock",
    "_running", "_paused", "_worker_draining", "_feed_closed",
    "_wall_started_monotonic", "state_persisted",
})
COMPONENT_FIELDS = frozenset({"strategy", "probes", "dead_probes", "candle_history", "_cohort"})
DATA_FIELDS = frozenset({
    "_search_streams", "_search_epoch", "_mutation_event", "_uses_cohorts",
    "user_id", "mode", "execution_config", "max_probes", "gen0_count",
    "seed_capital", "max_capital", "reserve_capital", "total_deployed",
    "mutation_rate", "child_count", "capital_split", "diversity_threshold",
    "colony_config", "tick_interval_ms", "_uses_simulation_clock",
    "_market_started_at", "circuit_breaker_drop_pct", "circuit_breaker_active",
    "_risk_control", "colony_id", "run_id", "_archived_probe_count",
    "current_generation", "tick_count", "_lifecycle_status", "failure_code",
    "failure_message", "started_at", "_initial_total_capital", "_latest_prices",
    "_latest_ticks", "_source_slots", "_source_quotes", "_market_ready",
    "_candle_assets", "_generation_probe_counts", "_generation_dead_counts",
    "_generation_reproduced", "_emitted_generation_stats", "_generation_aggregates",
    "_birth_generation_floor", "_cohort_parent_generations", "snapshot_interval",
    "_cohort_seeds", "_evaluation_iteration", "_last_evaluation", "reproduction_interval",
})
_DATA_CLASSES = frozenset({ColonyConfig, GeneOverride, ExecutionConfig, Genome,
                          _GenerationAggregate, MarketTick, QuoteEvidence})


class EngineStateError(ValueError):
    """The current graph cannot be captured by this explicitly supported version."""


def _copy_data(value, memo: dict, active: set[int] | None = None, depth: int = 0):
    """Copy only known data, bypassing arbitrary deepcopy/serialization hooks.

    Numeric sentinels such as aggregate best=-inf are preserved. This function
    validates graph ownership/type, not economic or future wire admissibility.
    """
    kind = type(value)
    if kind in (type(None), bool, int, float, str):
        return value
    if kind is datetime:
        if value.tzinfo is not None and type(value.tzinfo) is not timezone:
            raise EngineStateError("unsupported state timezone")
        return value
    if depth > 64:
        raise EngineStateError("state nesting exceeds the supported bound")
    active = set() if active is None else active
    identity = id(value)
    if identity in active:
        raise EngineStateError("cyclic state is unsupported")
    if kind not in (dict, list, tuple, set, frozenset, SearchRandomStreams) and kind not in _DATA_CLASSES:
        raise EngineStateError("state contains an unsupported object")
    if kind in _DATA_CLASSES:
        names = {field.name for field in fields(kind)}
        if any(type(key) is not str for key in vars(value)) or vars(value).keys() != names:
            raise EngineStateError("state model has unclassified fields")
    elif kind is SearchRandomStreams:
        if any(type(key) is not str for key in vars(value)) or vars(value).keys() != {"seed", "algorithm"}:
            raise EngineStateError("search streams have unclassified fields")
    if identity in memo:
        return memo[identity]
    active.add(identity)
    try:
        def clone(item):
            return _copy_data(item, memo, active, depth + 1)
        if kind is dict:
            result = {}
            for key, item in value.items():
                if type(key) not in (str, int):
                    raise EngineStateError("unsupported state mapping key")
                result[key] = clone(item)
        elif kind in (list, tuple, set, frozenset):
            result = kind(clone(item) for item in value)
        else:
            result = object.__new__(kind)
            for key, item in vars(value).items():
                object.__setattr__(result, key, clone(item))
        memo[identity] = result
        return result
    finally:
        active.remove(identity)


@dataclass(slots=True)
class EngineDraft:
    """Owned mutable data for inspection and future planning, not a controller.

    ProbeData records only whether a probe used the single shared history. It
    contains neither history references nor a runnable clock-bound Probe.
    """

    attributes: dict
    probes: dict[str, ProbeData]
    dead_probes: list[ProbeData]
    strategy: EvolutionStrategy
    candle_history: CandleHistory
    cohort: EvaluationCohort | None


def _validate_attributes(attributes: dict) -> None:
    if (type(attributes) is not dict or any(type(key) is not str for key in attributes)
            or attributes.keys() != DATA_FIELDS):
        raise EngineStateError("controller data fields do not match the fork contract")
    if (type(attributes["run_id"]) is not str or not attributes["run_id"]
            or type(attributes["colony_id"]) is not str
            or attributes["colony_id"] != attributes["run_id"]
            or type(attributes["user_id"]) is not str or not attributes["user_id"]
            or type(attributes["mode"]) is not str
            or attributes["mode"] not in ("simulation", "paper")
            or type(attributes["_lifecycle_status"]) is not str
            or attributes["_lifecycle_status"] not in
                ("starting", "running", "paused", "risk_halted", "stopped", "failed")):
        raise EngineStateError("controller identity is inconsistent")


def _validate_members(probes: dict, dead_probes: list) -> None:
    if type(probes) is not dict or type(dead_probes) is not list:
        raise EngineStateError("probe collections have unsupported types")
    ids = []
    for key, probe in probes.items():
        if type(probe) is not ProbeData or type(key) is not str or key != probe.attributes.get("probe_id"):
            raise EngineStateError("probe mapping identity is inconsistent")
        ids.append(key)
    for probe in dead_probes:
        if type(probe) is not ProbeData:
            raise EngineStateError("retained probe data is invalid")
        ids.append(probe.attributes.get("probe_id"))
    if any(type(identity) is not str or not identity for identity in ids) or len(set(ids)) != len(ids):
        raise EngineStateError("probe ownership identities overlap")


def _fork_draft(data: EngineDraft) -> EngineDraft:
    if type(data) is not EngineDraft:
        raise EngineStateError("typed engine data required")
    _validate_attributes(data.attributes)
    _validate_members(data.probes, data.dead_probes)
    memo = {}
    attributes = _copy_data(data.attributes, memo)
    return EngineDraft(
        attributes,
        {identity: fork_probe_data(probe, memo=memo) for identity, probe in data.probes.items()},
        [fork_probe_data(probe, memo=memo) for probe in data.dead_probes],
        fork_strategy(data.strategy, memo=memo),
        fork_candle_history(data.candle_history, memo=memo),
        None if data.cohort is None else fork_evaluation(data.cohort, memo=memo),
    )


class EngineSnapshot:
    """Sealed private state; every public data read is a fresh detached fork."""

    __slots__ = ("__data",)

    def __init__(self):
        raise TypeError("use capture_engine_state")

    def __setattr__(self, name, value):
        raise AttributeError("engine snapshots are sealed")

    def __reduce_ex__(self, protocol):
        raise TypeError("an in-process engine snapshot is not a durable checkpoint")

    @property
    def run_id(self) -> str:
        return self.__data.attributes["run_id"]

    @property
    def owner_id(self) -> str:
        return self.__data.attributes["user_id"]

    @property
    def mode(self) -> str:
        return self.__data.attributes["mode"]

    def fork(self) -> EngineDraft:
        return _fork_draft(self.__data)


async def capture_engine_state(controller: GenesisController) -> EngineSnapshot:
    """Capture at the worker's serialized tick/recovery boundary.

    Call from the controller's owning event loop, without already holding its
    lock. Cancellation while waiting has no effect on controller state. Startup
    preparation predates the tick lock and is deliberately unsupported until it
    reaches a non-starting lifecycle. No awaits occur while reading/copying.
    """
    if type(controller) is not GenesisController or type(vars(controller).get("_tick_lock")) is not asyncio.Lock:
        raise EngineStateError("an exact controller and its tick lock are required")
    async with controller._tick_lock:
        if (any(type(key) is not str for key in vars(controller))
                or vars(controller).keys() != DATA_FIELDS | COMPONENT_FIELDS | OPERATIONAL_FIELDS):
            raise EngineStateError("controller has unclassified fields")
        source_attributes = {name: value for name, value in vars(controller).items() if name in DATA_FIELDS}
        _validate_attributes(source_attributes)
        if controller._lifecycle_status == "starting" and controller.started_at is not None:
            raise EngineStateError("startup preparation is not a stable capture boundary")
        if type(controller.probes) is not dict or type(controller.dead_probes) is not list:
            raise EngineStateError("probe collections have unsupported types")
        memo = {}
        # Keep this assembly-only wrapper alive until all components are copied;
        # an id-keyed memo must never refer to a freed temporary source object.
        attributes = _copy_data(source_attributes, memo)
        def probe_data(probe):
            if type(probe) is not Probe:
                raise EngineStateError("an exact probe is required")
            captured = capture_probe_data(probe, memo=memo)
            if probe._candle_history is not None and probe._candle_history is not controller.candle_history:
                raise EngineStateError("probe refers to a different candle history")
            return captured
        probes = {identity: probe_data(probe) for identity, probe in controller.probes.items()}
        dead_probes = [probe_data(probe) for probe in controller.dead_probes]
        _validate_members(probes, dead_probes)
        data = EngineDraft(attributes, probes, dead_probes,
                           fork_strategy(controller.strategy, memo=memo),
                           fork_candle_history(controller.candle_history, memo=memo),
                           None if controller._cohort is None else fork_evaluation(controller._cohort, memo=memo))
        snapshot = object.__new__(EngineSnapshot)
        object.__setattr__(snapshot, "_EngineSnapshot__data", data)
        return snapshot
