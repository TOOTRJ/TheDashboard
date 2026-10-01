"""Explicit in-process forks for staged optimizer/evaluation work.

These copies are private process state, not durable checkpoints or serialized
artifacts. They do not copy a controller, market feed, wallet, database client,
callback or task. The caller must exclusively own the source while forking and
must install a successful branch only at its separate commit boundary.

In cmaes 0.13.1, CMA's serialization hooks omit its RandomState and recreate an
unseeded generator. Even ordinary deepcopy(CMA) therefore changes the next ask.
This narrow copier bypasses those hooks and preserves the complete local state
and RNG caches. Unknown classes/fields/package versions fail closed so a future
solver change requires an explicit review rather than a silently partial fork.
"""

from __future__ import annotations

import random
import math
from typing import TypeVar

import numpy as np

from .colony_config import ColonyConfig, GeneOverride
from .evaluation import EvaluatedCandidate, EvaluationCohort
from .gene_registry import GeneDomain
from .genome import Genome
from .parameter_codec import ParameterCodec
from .search_random import SearchRandomStreams
from .strategies.base import EvolutionStrategy
from .strategies.cma_es import CMAEvolutionStrategy, cmaes_lib
from .strategies.cohort_contract import SelectionCohort
from .strategies.differential_evolution import DifferentialEvolutionStrategy
from .strategies.genetic_algorithm import GeneticAlgorithmStrategy
from .strategies.particle_swarm import ParticleSwarmStrategy


CMA_FORK_VERSION = "0.13.1"
_COMMON = {"_search_streams", "_search_epoch", "_rng", "_mutation_event"}
_STRATEGY_FIELDS = {
    GeneticAlgorithmStrategy: _COMMON | {"mutation_rate", "mutation_strength", "_cohort"},
    DifferentialEvolutionStrategy: _COMMON | {"F", "CR", "min_pop", "_cohort", "_phase", "_pairs"},
    ParticleSwarmStrategy: _COMMON | {"w", "c2", "_cohort", "_codec", "_velocities", "_personal_best", "_global_best"},
    CMAEvolutionStrategy: _COMMON | {"_optimizer", "_codec", "_gene_names", "_first_generation",
        "_pending_vectors", "_pending_genomes", "_bound_ids", "_bound_genomes", "_awaiting_bind"},
}
_STATE_FIELDS = {
    **_STRATEGY_FIELDS,
    SearchRandomStreams: {"seed", "algorithm"},
    SelectionCohort: {"population_size", "bound_ids", "_signatures", "_pending", "_previous_ids",
                      "_previous_context", "_bootstrap"},
    ParameterCodec: {"_config", "domains", "names", "_assets"},
    ColonyConfig: {"gene_overrides", "enabled_genes", "available_assets", "max_lifespan_ticks",
                   "reproduction_interval", "mutation_rate", "strategy_profile"},
    GeneOverride: {"min", "max", "default", "fixed"},
    GeneDomain: {"minimum", "maximum", "default", "integer"},
    Genome: {"rsi_period", "rsi_oversold", "rsi_overbought", "ema_fast", "ema_slow", "volume_threshold",
             "position_size_pct", "stop_loss_pct", "take_profit_pct", "max_open_positions",
             "timeframe_minutes", "benchmark_target_pct", "reproduce_target_dollars", "death_drawdown_pct",
             "num_assets", "assets", "generation", "parent_ids"},
    EvaluatedCandidate: {"probe_id", "evaluation_id", "iteration_id", "_genome", "fitness", "roi", "num_trades",
                         "reason", "status", "window_started_at", "window_ends_at", "terminated_at", "cohort_complete"},
    EvaluationCohort: {"horizon_seconds", "iteration_id", "member_ids", "_genomes", "_evaluation_ids", "_evaluations",
                       "phase", "started_at", "ends_at", "completed_at", "abort_reason"},
}
_CMA_FIELDS = {
    "_n_dim", "_popsize", "_mu", "_mu_eff", "_cc", "_c1", "_cmu", "_c_sigma", "_d_sigma", "_cm", "_chi_n",
    "_weights", "_p_sigma", "_pc", "_mean", "_C", "_sigma", "_D", "_B", "_bounds", "_n_max_resampling",
    "_g", "_rng", "_lr_adapt", "_alpha", "_beta_mean", "_beta_Sigma", "_gamma", "_Emean", "_ESigma",
    "_Vmean", "_VSigma", "_eta_mean", "_eta_Sigma", "_tolx", "_tolxup", "_tolfun", "_tolconditioncov",
    "_funhist_term", "_funhist_values",
}
StrategyT = TypeVar("StrategyT", bound=EvolutionStrategy)


class StrategyForkError(ValueError):
    """The source cannot be copied under the reviewed local-state schema."""


class _Fork:
    def __init__(self, memo: dict[int, object] | None = None) -> None:
        if memo is not None and type(memo) is not dict:
            raise StrategyForkError("Fork memo must be an internal plain dictionary")
        self.memo: dict[int, object] = {} if memo is None else memo
        self.owned: set[int] = set()
        self.active: set[int] = set()
        self.arrays: list[np.ndarray] = []

    def copy(self, value: object, depth: int = 0):
        if depth > 64:
            raise StrategyForkError("Optimizer state nesting exceeds the reviewed bound")
        kind = type(value)
        if value is None or kind in (str, bool, int, float, np.float64):
            return value
        identity = id(value)
        if identity in self.active:
            raise StrategyForkError("Cyclic optimizer state is unsupported")
        if identity in self.memo:
            if identity not in self.owned:
                for array in _validate_memo(value, self.memo[identity]):
                    self._remember_array(array)
                self.owned.add(identity)
            return self.memo[identity]
        self.active.add(identity)
        try:
            result = self._copy(value, kind, depth)
            self.memo[identity] = result
            self.owned.add(identity)
            return result
        finally:
            self.active.remove(identity)

    def _copy(self, value, kind, depth):
        copy = lambda item: self.copy(item, depth + 1)
        if kind is tuple:
            return tuple(copy(item) for item in value)
        if kind is list:
            return [copy(item) for item in value]
        if kind is dict:
            # All reviewed maps use string keys; rejecting arbitrary objects
            # also avoids invoking user-defined hashing/copy behavior.
            if any(type(key) is not str for key in value):
                raise StrategyForkError("Optimizer state maps require plain string keys")
            return {key: copy(item) for key, item in value.items()}
        if kind is np.ndarray:
            if value.dtype.hasobject or value.dtype.kind not in "biuf" or value.dtype.metadata is not None:
                raise StrategyForkError("Optimizer arrays must contain only numeric values")
            # Repeated references to the *same* array use the memo. Distinct
            # overlapping views are absent from the reviewed solver schema;
            # reject instead of silently changing their shared-storage meaning.
            self._remember_array(value)
            result = value.copy(order="K")
            result.setflags(write=value.flags.writeable)
            return result
        if kind is random.Random:
            rng_state = _python_rng_state(value)
            result = random.Random(0)
            # Python's state is only immutable tuples/ints/optional float;
            # NumPy's get_state returns a detached array which set_state copies.
            # Never place these temporary state objects in the assembly memo.
            result.setstate(rng_state)
            return result
        if kind is np.random.RandomState:
            result = np.random.RandomState(0)
            result.set_state(value.get_state())
            return result
        _check_fields(value)
        result = object.__new__(kind)
        # No __init__, __getstate__, __setstate__, __reduce__, configure_search,
        # initialize, bind or solver ask/tell is executed while copying state.
        result.__dict__.update(copy(value.__dict__))
        return result

    def _remember_array(self, value: np.ndarray) -> None:
        for seen in self.arrays:
            if seen is value:
                return
            if np.shares_memory(value, seen):
                raise StrategyForkError("Distinct overlapping optimizer array views are unsupported")
        self.arrays.append(value)


def _check_cma_version() -> None:
    if cmaes_lib is None or getattr(cmaes_lib, "__version__", None) != CMA_FORK_VERSION:
        raise StrategyForkError("CMA local-state fork requires reviewed cmaes 0.13.1")


def _python_rng_state(value: random.Random) -> tuple:
    if (set(value.__dict__) != {"gauss_next"} or
            (value.gauss_next is not None and
             (type(value.gauss_next) is not float or not math.isfinite(value.gauss_next)))):
        raise StrategyForkError("Unexpected Python RNG fields or mutable/nonfinite Gaussian cache")
    # Exact random.Random owns the C MT state; its only Python-managed state is
    # gauss_next, and setstate would otherwise retain an arbitrary object there.
    return value.getstate()


def _check_fields(value) -> None:
    kind = type(value)
    cma_type = cmaes_lib.CMA if cmaes_lib is not None else None
    if kind is cma_type:
        _check_cma_version()
        fields = _CMA_FIELDS
    else:
        fields = _STATE_FIELDS.get(kind)
    if fields is None or type(value.__dict__) is not dict or set(value.__dict__) != fields:
        raise StrategyForkError("Unknown optimizer state class or fields")
    if kind is cma_type and type(value._rng) is not np.random.RandomState:
        raise StrategyForkError("CMA requires its reviewed private RandomState")


def _validate_memo(source, target) -> list[np.ndarray]:
    """Validate a root assembler's pre-copied graph before reusing its alias."""
    def describe(root):
        mutable: set[int] = set()
        arrays: list[np.ndarray] = []
        active: set[int] = set()
        seen: dict[int, int] = {}
        retained: list[object] = []

        def visit(value, depth=0):
            if depth > 64:
                raise StrategyForkError("Fork memo state nesting exceeds the reviewed bound")
            kind = type(value)
            if value is None or kind in (str, bool, int):
                return kind, value
            if kind is float:
                return kind, value.hex()
            if kind is np.float64:
                return kind, value.tobytes()
            if id(value) in active:
                raise StrategyForkError("Cyclic fork memo state is unsupported")
            if id(value) in seen:
                return "alias", seen[id(value)]
            seen[id(value)] = len(seen)
            retained.append(value)
            active.add(id(value))
            try:
                if kind is not tuple:
                    mutable.add(id(value))
                if kind in (list, tuple):
                    return kind, tuple(visit(item, depth + 1) for item in value)
                if kind is dict:
                    if any(type(key) is not str for key in value):
                        raise StrategyForkError("Fork memo maps require plain string keys")
                    return kind, tuple((key, visit(item, depth + 1)) for key, item in value.items())
                if kind is np.ndarray:
                    if value.dtype.hasobject or value.dtype.kind not in "biuf" or value.dtype.metadata is not None:
                        raise StrategyForkError("Fork memo arrays must be numeric")
                    if any(np.shares_memory(value, other) for other in arrays):
                        raise StrategyForkError("Distinct overlapping fork memo array views are unsupported")
                    arrays.append(value)
                    return kind, value.dtype.str, value.shape, value.flags.writeable, value.tobytes()
                if kind is random.Random:
                    rng_state = _python_rng_state(value)
                    return kind, rng_state[0], rng_state[1], None if rng_state[2] is None else rng_state[2].hex()
                if kind is np.random.RandomState:
                    # The state array returned here is already detached from
                    # the generator; compare it without retaining its identity.
                    state = value.get_state()
                    return kind, state[0], state[1].tobytes(), state[2:]
                _check_fields(value)
                return kind, visit(value.__dict__, depth + 1)
            finally:
                active.remove(id(value))

        signature = visit(root)
        return signature, mutable, arrays

    left, source_ids, source_arrays = describe(source)
    right, target_ids, target_arrays = describe(target)
    if (left != right or source_ids.intersection(target_ids)
            or any(np.shares_memory(a, b) for a in source_arrays for b in target_arrays)):
        raise StrategyForkError("Fork memo does not contain an equivalent isolated state copy")
    return source_arrays


def fork_strategy(strategy: StrategyT, *, memo: dict[int, object] | None = None) -> StrategyT:
    """Copy one supported optimizer without advancing the source or its RNG.

    This accepts bootstrap, bound, pending-bind and aborted strategy state. It
    validates the reviewed state shape, not arbitrary fabricated state semantics.
    References shared within the source remain shared within the fork, while
    mutable state never crosses branches. Concurrent source mutation is outside
    this synchronous ownership contract.

    An optional shared memo is only for the internal snapshot assembler, never
    persisted/untrusted inputs. Pre-copied aliases are validated before reuse.
    """
    if type(strategy) not in _STRATEGY_FIELDS:
        raise StrategyForkError("Only the four reviewed optimizer classes may be forked")
    _check_fields(strategy)
    if (type(strategy._rng) is not random.Random or type(strategy._search_streams) is not SearchRandomStreams
            or any(type(value) is not int or value < 0 for value in (strategy._search_epoch, strategy._mutation_event))):
        raise StrategyForkError("Invalid optimizer search-stream ownership")
    if type(strategy) is CMAEvolutionStrategy:
        _check_cma_version()
    return _Fork(memo).copy(strategy)


def fork_evaluation(cohort: EvaluationCohort, *, memo: dict[int, object] | None = None) -> EvaluationCohort:
    """Copy the entire warming/evaluating/completed/aborted cohort in process.

    Frozen EvaluatedCandidate records still contain a mutable private Genome;
    those genomes, partial terminal results and membership bindings are copied.
    The constructor is never called and no evaluation is completed or aborted.
    Optional memo follows the same internal-assembly rules as fork_strategy.
    """
    if type(cohort) is not EvaluationCohort:
        raise StrategyForkError("Only a reviewed EvaluationCohort may be forked")
    return _Fork(memo).copy(cohort)
