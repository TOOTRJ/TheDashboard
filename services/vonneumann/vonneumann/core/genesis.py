"""
Genesis Controller — the top-level orchestrator.

Responsibilities:
  - Spawn and fund Gen-0 probes (respecting ColonyConfig)
  - Delegate evolution to a pluggable EvolutionStrategy
  - Handle death events (reclaim capital, strategy-aware auto-spawn)
  - Enforce population cap, capital limits, max lifespan
  - Run circuit breakers and diversity injection
  - Drive the tick loop and broadcast events
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Optional, Callable, Awaitable

from .clock import timestamp_datetime, utc_now
from .colony_config import ColonyConfig
from .evolution import FITNESS_POLICY, NUMERIC_GENES, mutate, population_diversity
from .equity_metrics import EQUITY_METRICS_POLICY
from .genome import Genome, random_genome
from .execution import ExecutionConfig
from .gene_registry import GENE_REGISTRY
from .search_random import SearchRandomStreams
from .funding import FundingError, can_fund, funding_tolerance, sum_cashflows, valid_cash
from .names import generate_probe_name
from .market_validation import MarketValueError, nonnegative_value, positive_price
from .probe import Probe, ProbeStepError
from .risk_control import RiskRecoveryError
from .evaluation import EvaluationCohort, EVALUATION_POLICY
from .strategies.base import EvolutionResult, EvolutionStrategy
from .types import EventType, ProbeEvent, ProbeState, FitnessSnapshot
from ..market.feed import MarketFeed, MarketFeedError, MarketTick, QuoteEvidence
from ..market.candles import CandleHistory, CANDLE_POLICY
from ..market.quote_freshness import MAX_SOURCE_AGE_SECONDS, QUOTE_POLICY, quote_source_age, validate_quote

logger = logging.getLogger(__name__)

DEAD_PROBE_RETENTION = 500
GENERATION_HISTORY_RETENTION = 100
LIFECYCLE_POLICY = {
    "version": "acknowledged-terminal-sealed-generations-v1",
    "terminal_event": "probe_dead",
    "generation_completion": "sealed_births_all_terminal_acknowledged",
    "generation_semantics": "birth_epoch_not_ancestry_depth",
    "generation_diversity": "rms_pairwise_global_normalized_numeric_v1",
    "generation_diversity_assets": "excluded",
    "reproduced_count": "distinct_sources_with_acknowledged_offspring_before_completion",
    "closed_trade_retention": 256,
    "dead_probe_retention": DEAD_PROBE_RETENTION,
    "generation_history_retention": GENERATION_HISTORY_RETENTION,
}


@dataclass
class _GenerationAggregate:
    """Constant-size lifetime statistics; never retain old probe objects.

    Numeric diversity uses Welford moments: mean pairwise squared distance is
    2 * sum(M2) / (n - 1). This is exact online algebra, not a retained sample.
    It intentionally differs from live population mean distance with assets.
    """

    started_at: datetime
    count: int = 0
    unacknowledged_births: int = 0
    terminal_count: int = 0
    reproduced: int = 0
    sealed: bool = False
    means: list[float] = field(default_factory=lambda: [0.0] * len(NUMERIC_GENES))
    m2: list[float] = field(default_factory=lambda: [0.0] * len(NUMERIC_GENES))
    fitness_sum: float = 0.0
    best_fitness: float = -math.inf
    worst_fitness: float = math.inf
    roi_sum: float = 0.0
    best_roi: float = -math.inf
    capital_sum: float = 0.0
    trade_count: int = 0
    win_rate_sum: float = 0.0
    traded_candidates: int = 0

    def born(self, probe: Probe) -> None:
        values = []
        for name in NUMERIC_GENES:
            definition = GENE_REGISTRY.get(name)
            value = (getattr(probe.genome, name) - definition.min) / (definition.max - definition.min or 1.0)
            if not math.isfinite(value):
                raise ValueError("Generation genes must be finite")
            values.append(value)
        self.started_at = min(self.started_at, probe.born_at)
        self.count += 1
        self.unacknowledged_births += 1
        for index, value in enumerate(values):
            delta = value - self.means[index]
            self.means[index] += delta / self.count
            self.m2[index] += delta * (value - self.means[index])

    def terminal(self, probe: Probe) -> None:
        fitness, roi, capital = probe.fitness, probe.roi, probe.capital
        self.terminal_count += 1
        self.fitness_sum = math.fsum((self.fitness_sum, fitness))
        self.best_fitness = max(self.best_fitness, fitness)
        self.worst_fitness = min(self.worst_fitness, fitness)
        self.roi_sum = math.fsum((self.roi_sum, roi))
        self.best_roi = max(self.best_roi, roi)
        self.capital_sum = math.fsum((self.capital_sum, capital))
        self.trade_count += probe.num_trades
        if probe.num_trades:
            self.traded_candidates += 1
            self.win_rate_sum = math.fsum((self.win_rate_sum, probe.win_rate))

    def summary(self, generation: int, ended_at: datetime) -> dict:
        n = self.count
        diversity = math.sqrt(max(0.0, 2.0 * math.fsum(self.m2) / (n - 1))) if n > 1 else 0.0
        return {
            "generation": generation, "started_at": self.started_at.isoformat(),
            "ended_at": ended_at.isoformat(), "total_probes": n,
            "alive_probes": 0, "dead_probes": self.terminal_count,
            "reproduced_count": self.reproduced,
            "best_fitness": round(self.best_fitness, 4),
            "avg_fitness": round(self.fitness_sum / n, 4),
            "worst_fitness": round(self.worst_fitness, 4),
            "total_capital": round(self.capital_sum, 2),
            "avg_capital": round(self.capital_sum / n, 2),
            "total_trades": self.trade_count,
            "avg_win_rate": round(self.win_rate_sum / self.traded_candidates, 4) if self.traded_candidates else 0.0,
            "best_roi": round(self.best_roi, 4), "avg_roi": round(self.roi_sum / n, 4),
            "genome_diversity": round(diversity, 4),
        }


class GenesisController:
    """Orchestrates the entire Von Neumann probe colony."""

    def __init__(
        self,
        market_feed: MarketFeed,
        strategy: EvolutionStrategy,
        colony_id: str,
        user_id: str,
        mode: str = "simulation",
        max_probes: int = 50,
        max_capital: float = 10_000.0,
        seed_capital: float = 100.0,
        gen0_count: int = 10,
        tick_interval_ms: int = 1000,
        mutation_rate: float = 0.20,
        child_count: int = 2,
        capital_split: float = 0.45,
        diversity_threshold: float = 0.10,
        circuit_breaker_drop_pct: float = 0.30,
        colony_config: Optional[ColonyConfig] = None,
        on_event: Optional[Callable[[ProbeEvent], Awaitable[None]]] = None,
        persist_risk_status: Optional[Callable[[dict], Awaitable[None]]] = None,
        search_seed: str = "0",
        execution_config: Optional[ExecutionConfig] = None,
    ):
        if getattr(market_feed, "simulation_only", False) and mode != "simulation":
            raise ValueError("This offline fixture feed supports simulation mode only")
        self.market_feed = market_feed
        self.strategy = strategy
        self._search_streams = SearchRandomStreams(search_seed, strategy.name)
        self._search_epoch = 0
        self._mutation_event = 0
        self.strategy.configure_search(self._search_streams, self._search_epoch)
        self._uses_cohorts = bool(getattr(strategy, "supports_cohorts", False))
        self.user_id = user_id
        self.mode = mode
        self.execution_config = execution_config or ExecutionConfig()

        # Population config
        self.max_probes = max_probes
        self.gen0_count = gen0_count
        self.seed_capital = seed_capital

        # Capital management
        self.max_capital = max_capital
        self.reserve_capital = max_capital
        self.total_deployed = 0.0

        # Evolution config
        self.mutation_rate = mutation_rate
        self.child_count = child_count
        # Kept for caller compatibility; evaluation budgets no longer shrink
        # with the parent's proceeds. Every new candidate gets seed_capital.
        self.capital_split = capital_split
        self.diversity_threshold = diversity_threshold

        # Colony config (gene overrides, enabled genes, etc.)
        self.colony_config = colony_config or ColonyConfig()

        # Wall-clock pacing is separate from the simulation's modeled time.
        # Production SimulationFeed supplies current_timestamp. External/custom
        # feeds without that capability retain real event time, never an inferred
        # source-price timestamp.
        self.tick_interval_ms = tick_interval_ms
        self._uses_simulation_clock = mode == "simulation" and hasattr(market_feed, "current_timestamp")
        self._market_started_at = self._event_time() if self._uses_simulation_clock else None
        self._wall_started_monotonic: Optional[float] = None

        # Safety
        threshold = nonnegative_value(circuit_breaker_drop_pct)
        if not 0 < threshold <= 1:
            raise ValueError("Circuit-breaker loss fraction must be above zero and at most one")
        self.circuit_breaker_drop_pct = threshold
        self.circuit_breaker_active = False
        self._persist_risk_status = persist_risk_status
        self._risk_control = {
            "policy": "initial-account-loss-v1", "threshold_fraction": threshold,
            "baseline_equity": None, "observed_equity": None,
            "observed_loss_fraction": None, "observed_at": None,
            "trip_id": None, "tripped_at": None, "trip_equity": None,
            "trip_loss_fraction": None, "last_recovered_at": None, "recovery_count": 0,
        }

        # State
        self.colony_id = colony_id
        self.run_id = colony_id  # Alias for backward compatibility
        self.probes: dict[str, Probe] = {}
        self.dead_probes: list[Probe] = []
        self._archived_probe_count = 0
        self.current_generation = 0
        self.tick_count = 0
        self._running = False
        self._paused = False
        self._lifecycle_status = "starting"
        self.failure_code: Optional[str] = None
        self.failure_message: Optional[str] = None
        self.state_persisted = False
        self._feed_closed = False
        self._tick_lock = asyncio.Lock()
        self.started_at: Optional[datetime] = None

        # Event callback
        self._on_event = on_event

        # Capital tracking
        self._initial_total_capital = 0.0

        # Latest prices (updated each tick for use during probe retirement)
        self._latest_prices: dict[str, float] = {}
        self._latest_ticks: dict[str, MarketTick] = {}
        self._source_slots: dict[str, int] = {}
        self._source_quotes: dict[str, MarketTick] = {}
        self._market_ready = False

        # Every candidate reads the same run-anchored series, including assets
        # first selected by a later generation. Quotes never seed indicators.
        self._candle_assets = sorted(self.colony_config.get_effective_assets())
        self.candle_history = CandleHistory(self._candle_assets)

        # Generation tracking
        self._generation_probe_counts: dict[int, int] = {}
        self._generation_dead_counts: dict[int, int] = {}
        self._generation_reproduced: dict[int, int] = {}
        self._emitted_generation_stats: set[int] = set()
        self._generation_aggregates: dict[int, _GenerationAggregate] = {}
        self._birth_generation_floor = 0
        self._cohort_parent_generations: dict[str, tuple[int, bool]] = {}

        # Snapshot interval
        self.snapshot_interval = 25
        self._cohort: Optional[EvaluationCohort] = None
        self._cohort_seeds: list[Genome] = []
        self._evaluation_iteration = 0
        self._last_evaluation: Optional[dict] = None

        # Reproduction interval (from colony config or default 100)
        self.reproduction_interval = self.colony_config.reproduction_interval

        logger.info(
            f"[Genesis] Init. mode={mode} strategy={strategy.name} "
            f"max_probes={max_probes} max_capital=${max_capital} gen0={gen0_count} "
            f"repro_interval={self.reproduction_interval}"
        )

    def _event_time(self) -> datetime:
        if self._uses_simulation_clock:
            return timestamp_datetime(self.market_feed.current_timestamp)
        return utc_now()

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def live_probes(self) -> list[Probe]:
        return [p for p in self.probes.values() if p.state != ProbeState.DEAD]

    @property
    def active_capital(self) -> float:
        """Value still owned by registered probes, including partial failures.

        A DEAD probe awaiting a failed persistence acknowledgement still owns
        its cash until the controller has actually reclaimed and removed it.
        """
        return math.fsum(p.total_value for p in self.probes.values())

    def status(self) -> dict:
        live = self.live_probes
        open_positions = sum(len(probe.open_positions) for probe in self.probes.values())
        # Failure reporting must survive the same malformed ledger that stopped
        # execution. Unknown valuation is not zero, principal, or stale equity.
        reserve = active = total = None
        try:
            reserve = nonnegative_value(self.reserve_capital)
        except MarketValueError:
            pass
        try:
            values = []
            for probe in self.probes.values():
                values.append(nonnegative_value(probe.capital))
                for asset, trade in probe.open_positions.items():
                    price = self._mark_price(asset)
                    values.append(trade.marked_value(price))
            active = nonnegative_value(math.fsum(values))
            if reserve is not None:
                total = nonnegative_value(reserve + active)
        except (MarketValueError, MarketFeedError, OverflowError):
            active = total = None
        try:
            diversity = nonnegative_value(
                population_diversity([p.genome for p in live]) if len(live) >= 2 else 1.0)
        except (ValueError, TypeError, OverflowError, AttributeError):
            diversity = None
        return {
            "status": self._lifecycle_status,
            "failure_code": self.failure_code,
            "failure_message": self.failure_message,
            "state_persisted": self.state_persisted,
            "open_positions": open_positions,
            "requires_reconciliation": (open_positions > 0 and self._lifecycle_status == "stopped") or
                                       (bool(self.probes) and self._lifecycle_status == "failed"),
            "run_id": self.run_id,
            "colony_id": self.colony_id,
            "strategy": self.strategy.name,
            "search_spec": {**self._search_streams.spec(self._search_epoch),
                "simulation_spec": (self.market_feed.simulation_spec
                    if self._uses_simulation_clock and hasattr(self.market_feed, "simulation_spec") else None),
                "dataset_spec": (self.market_feed.dataset_spec
                    if self._uses_simulation_clock and hasattr(self.market_feed, "dataset_spec") else None)},
            "mode": self.mode,
            "execution_policy": self.execution_config.policy(),
            "generation": self.current_generation,
            "tick": self.tick_count,
            "live_probes": len(live),
            "dead_probes": self._archived_probe_count,
            "total_probes": len(self.probes) + self._archived_probe_count,
            "reserve_capital": round(reserve, 2) if reserve is not None else None,
            "active_capital": round(active, 2) if active is not None else None,
            "total_capital": round(total, 2) if total is not None else None,
            "valuation_available": total is not None,
            "evaluation_policy": dict(EVALUATION_POLICY) if self._uses_cohorts else None,
            "cohort": self._cohort.to_dict() if self._cohort else None,
            "last_evaluation": deepcopy(self._last_evaluation),
            "circuit_breaker": self.circuit_breaker_active,
            "risk_control": deepcopy(self._risk_control),
            "diversity": round(diversity, 4) if diversity is not None else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "uptime_secs": (
                max(0.0, time.monotonic() - self._wall_started_monotonic)
                if self._wall_started_monotonic is not None else 0
            ),
            "clock_basis": "synthetic_market" if self._uses_simulation_clock else "wall",
            "quote_policy": dict(QUOTE_POLICY) if self.mode == "paper" else None,
            "candle_policy": deepcopy(CANDLE_POLICY),
            "metrics_policy": dict(EQUITY_METRICS_POLICY),
            "fitness_policy": dict(FITNESS_POLICY),
            "lifecycle_policy": dict(LIFECYCLE_POLICY),
            "market_time": self._event_time().isoformat() if self._uses_simulation_clock else None,
            "market_elapsed_secs": (
                (self._event_time() - self._market_started_at).total_seconds()
                if self._market_started_at is not None else None
            ),
            "simulation_spec": (
                self.market_feed.simulation_spec
                if self._uses_simulation_clock and hasattr(self.market_feed, "simulation_spec") else None
            ),
            "jup_api_calls": (
                self.market_feed.api_call_count
                if hasattr(self.market_feed, "api_call_count") else 0
            ),
        }

    # ── Startup ──────────────────────────────────────────────────────────

    @property
    def lifecycle_status(self) -> str:
        return self._lifecycle_status

    def set_lifecycle(self, status: str) -> None:
        if status in {"paused", "risk_halted", "stopped", "failed"}:
            self._abort_evaluation(status)
        self._lifecycle_status = status
        self._running = status in {"running", "paused", "risk_halted"}
        self._paused = status == "paused"

    async def prepare(self) -> None:
        """Seed and persist the population before a supervised loop may start."""
        self.started_at = utc_now()
        self._wall_started_monotonic = time.monotonic()
        logger.info(f"[Genesis] Starting in {self.mode} mode. Seeding {self.gen0_count} Gen-0 probes.")

        genomes = [random_genome(generation=0, colony_config=self.colony_config,
                   rng=self._search_streams.rng('gen0', self._search_epoch, index))
                   for index in range(self.gen0_count)]
        await self._apply_replacement(EvolutionResult(genomes, []))
        if len(self.live_probes) != self.gen0_count:
            raise RuntimeError("Initial population is incomplete")

        # Paper history is independent of the quote clock and warmed once for
        # the whole configured universe. The subsequent quote is current.
        if self.mode == "paper":
            await self._refresh_candles(warmup=True)

        # After history warmup, require a current quote for every selected asset.
        assets = sorted({asset for probe in self.live_probes for asset in probe.genome.assets})
        ticks = await self.market_feed.get_ticks(assets)
        valid_ticks, errors = self._validate_ticks(assets, ticks)
        if not assets or errors:
            raise errors[0] if errors else MarketValueError()
        self._latest_ticks = valid_ticks
        self._latest_prices = {asset: tick.price for asset, tick in valid_ticks.items()}
        self._market_ready = True
        if self.mode == "simulation":
            # Preserve the first atomic synthetic frame without a second step.
            await self._refresh_candles(warmup=True)
        for probe in self.live_probes:
            probe.attach_candle_history(self.candle_history)
            for asset in probe.genome.assets:
                probe.on_quote(valid_ticks[asset])
        self._require_current_quotes()

        # Initialize the strategy with live probes
        self.strategy.initialize(list(self.probes.values()), self.colony_config)
        if self._uses_cohorts:
            self._bind_evaluation()

        self._initial_total_capital = self.active_capital + self.reserve_capital
        self._observe_account_risk()

    async def run(self) -> None:
        """Run only after the manager has durably marked preparation complete."""
        await self._tick_loop()

    async def _refresh_candles(self, *, warmup: bool = False) -> None:
        if not hasattr(self.market_feed, "get_candles"):
            raise MarketFeedError("candles_unavailable")
        candles = await self.market_feed.get_candles(self._candle_assets, warmup=warmup)
        self.candle_history.ingest(candles, available_at=self._event_time().timestamp())

    async def stop(self) -> None:
        self._running = False
        self._paused = False
        await self.cleanup()
        # Positions stay attached for reconciliation; stopping cannot fabricate a fill.
        logger.info("[Genesis] Stopped; retained position records for reconciliation.")

    async def cleanup(self) -> None:
        """Release feed resources without erasing probe/position state."""
        self._abort_evaluation("worker_stopped")
        self._running = False
        if not self._feed_closed and hasattr(self.market_feed, "close"):
            await self.market_feed.close()
            self._feed_closed = True

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    async def wait_for_tick(self) -> None:
        """Allow a tick already in progress to finish before persisting a pause."""
        async with self._tick_lock:
            pass

    async def quiesce(self) -> None:
        self._paused = True
        await self.wait_for_tick()

    # ── Probe spawning ───────────────────────────────────────────────────

    async def _spawn_probe(self, genome: Genome, capital: float, *,
                           _planned_reserve: Optional[float] = None) -> Optional[Probe]:
        if self.circuit_breaker_active:
            return None
        if genome.generation < self._birth_generation_floor:
            raise FundingError("generation_sealed")
        if not valid_cash(capital) or not valid_cash(self.reserve_capital):
            raise FundingError()
        if len(self.probes) >= self.max_probes:
            return None
        if capital < 1.0 or not can_fund(self.reserve_capital, capital):
            return None

        reserve_after = max(0.0, sum_cashflows((self.reserve_capital, -capital)))
        if _planned_reserve is not None:
            # The batch uses the full cashflow sum to avoid cumulative rounding.
            # Only the validated controller plan may supply this adjustment.
            if not valid_cash(_planned_reserve):
                raise FundingError()
            reserve_after = _planned_reserve

        probe = Probe(
            genome=genome,
            initial_capital=capital,
            mode=self.mode,
            probe_name=generate_probe_name(genome.generation),
            clock=self._event_time,
            candle_history=self.candle_history,
            execution_config=self.execution_config,
        )
        for asset in genome.assets:
            if asset in self._latest_ticks:
                probe.on_quote(self._latest_ticks[asset])
        probe.birth_tick = self.tick_count
        probe.set_funded()
        probe.set_observing()

        self.probes[probe.probe_id] = probe
        self.reserve_capital = reserve_after
        self.total_deployed += capital

        gen = genome.generation
        self._generation_probe_counts[gen] = self._generation_probe_counts.get(gen, 0) + 1
        aggregate = self._generation_aggregates.setdefault(gen, _GenerationAggregate(probe.born_at))
        aggregate.born(probe)
        if gen > self.current_generation:
            self.current_generation = gen

        logger.info(
            f"[Genesis] Spawned {probe.probe_name} Gen={gen} "
            f"Capital=${capital:.2f} ({len(self.probes)} live)"
        )

        await self._emit(ProbeEvent(
            timestamp=probe.born_at,
            event_type=EventType.PROBE_BORN,
            probe_id=probe.probe_id,
            data=probe.summary(),
        ))
        aggregate.unacknowledged_births -= 1
        return probe

    # ── Probe retirement (strategy-driven) ───────────────────────────────

    def _liquidation_plan(self, probe: Probe) -> tuple[float, dict[str, float]]:
        """Project exactly the arithmetic/prices used by Probe._close_position."""
        if self.mode == "paper":
            self._require_fresh_assets(probe.open_positions)
        prices = {asset: self._latest_prices.get(asset) for asset in probe.open_positions}
        try:
            return probe.validate_liquidation(prices), prices
        except MarketValueError:
            raise FundingError() from None

    def _preflight_replacement(self, result: EvolutionResult, *, self_reproducing: bool = False
                               ) -> tuple[list[Genome], dict[str, tuple[Probe, dict[str, float]]], list[float]]:
        """Validate the entire mandatory batch before any close/retire/birth.

        The tick lock serializes controller changes while this plan is applied.
        A strategy may already have advanced optimizer state; rejection is a
        terminal failure, never an implicit retry of that optimizer step.
        """
        if (not isinstance(result, EvolutionResult) or
                not isinstance(result.retire_ids, list) or
                not isinstance(result.offspring, list) or
                not isinstance(result.parent_map, dict) or
                not all(isinstance(pid, str) for pid in result.retire_ids) or
                len(set(result.retire_ids)) != len(result.retire_ids) or
                (result.retire_ids and not result.offspring) or
                not valid_cash(self.reserve_capital) or
                not valid_cash(self.seed_capital) or self.seed_capital < 1):
            raise FundingError()
        allowed_states = ({ProbeState.REPRODUCING} if self_reproducing else
                          {ProbeState.OBSERVING, ProbeState.TRADING})
        retired = {}
        proceeds = []
        for pid in result.retire_ids:
            probe = self.probes.get(pid)
            if (probe is None or probe.state not in allowed_states or
                    (self_reproducing and probe.open_positions)):
                raise FundingError()
            projected, prices = self._liquidation_plan(probe)
            retired[pid] = (probe, prices)
            proceeds.append(projected)

        if len(self.probes) - len(retired) + len(result.offspring) > self.max_probes:
            raise FundingError("funding_capacity")
        required = sum_cashflows(self.seed_capital for _ in result.offspring)
        flows = [self.reserve_capital, *proceeds]
        available = sum_cashflows(flows)
        if not can_fund(available, required):
            raise FundingError("funding_insufficient")
        # Validate every debit before retiring anyone. Comparing two rounded
        # totals alone can conceal a shortage revealed by the final cashflow sum.
        balances = []
        for _ in result.offspring:
            if not can_fund(available, self.seed_capital):
                raise FundingError("funding_insufficient")
            flows.append(-self.seed_capital)
            balance = sum_cashflows(flows)
            if balance < -funding_tolerance(available, self.seed_capital):
                raise FundingError("funding_insufficient")
            available = max(0.0, balance)
            balances.append(available)

        # Copy strategy output so assigning lineage cannot mutate a parent's
        # genome or another child's genome through an aliased object.
        children = []
        allowed_assets = set(self.colony_config.get_effective_assets())
        known_parents = (set(self.probes) | {p.probe_id for p in self.dead_probes}
                         | set(self._cohort_parent_generations))
        if any(key not in {str(i) for i in range(len(result.offspring))}
               for key in result.parent_map):
            raise FundingError()
        for i, genome in enumerate(result.offspring):
            if (not isinstance(genome, Genome) or
                    any(not valid_cash(getattr(genome, gene)) for gene in NUMERIC_GENES) or
                    not isinstance(genome.generation, int) or isinstance(genome.generation, bool) or
                    genome.generation < self._birth_generation_floor or not isinstance(genome.assets, list) or
                    not genome.assets or not all(isinstance(a, str) for a in genome.assets) or
                    len(set(genome.assets)) != len(genome.assets) or
                    not set(genome.assets).issubset(allowed_assets)):
                raise FundingError()
            parents = result.parent_map.get(str(i), genome.parent_ids)
            if (not isinstance(parents, list) or
                    not all(isinstance(pid, str) and pid in known_parents for pid in parents) or
                    len(set(parents)) != len(parents)):
                raise FundingError()
            child = deepcopy(genome)
            child.parent_ids = list(parents)
            children.append(child)
        return children, retired, balances

    async def _apply_replacement(self, result: EvolutionResult, *, self_reproducing: bool = False) -> None:
        if self.circuit_breaker_active:
            return
        self._require_current_quotes()
        children, retired, balances = self._preflight_replacement(result, self_reproducing=self_reproducing)
        selected_ids = {pid for genome in children for pid in genome.parent_ids}
        parent_refs = {probe.probe_id: probe for probe in [*self.dead_probes, *self.probes.values()]}
        reclaimed_flows = [self.reserve_capital]
        for probe, prices in retired.values():
            reason = "evolution_selected" if probe.probe_id in selected_ids else "evolution_culled"
            reclaimed_flows.append(await self._retire_probe(probe, reason=reason, prices=prices))
            self.reserve_capital = sum_cashflows(reclaimed_flows)
        if self._check_circuit_breaker():
            await self._save_risk_status(self.status())
            await self._publish_risk_change("tripped")
            return
        for genome, balance in zip(children, balances):
            self._require_current_quotes()
            new_probe = await self._spawn_probe(genome, self.seed_capital, _planned_reserve=balance)
            if new_probe is None:
                raise FundingError()
            # Count actual acknowledged births, not intended reproduction. A
            # partial failed batch keeps its lineage but cannot seal generations.
            for parent_id in genome.parent_ids:
                parent = parent_refs.get(parent_id)
                pinned = self._cohort_parent_generations.get(parent_id)
                generation = parent.genome.generation if parent else pinned[0] if pinned else None
                recorded = getattr(parent, "_has_persisted_offspring", False) if parent else pinned[1] if pinned else True
                aggregate = self._generation_aggregates.get(generation)
                if aggregate is not None and not recorded:
                    aggregate.reproduced += 1
                    self._generation_reproduced[generation] = aggregate.reproduced
                    if parent is not None:
                        parent._has_persisted_offspring = True
                    if pinned is not None:
                        self._cohort_parent_generations[parent_id] = (generation, True)
            if genome.parent_ids and hasattr(self.strategy, "remap_probe_id"):
                self.strategy.remap_probe_id(genome.parent_ids[0], new_probe.probe_id)
        if children:
            self._birth_generation_floor = max(self._birth_generation_floor, max(g.generation for g in children))
        for generation, aggregate in list(self._generation_aggregates.items()):
            if generation < self._birth_generation_floor:
                aggregate.sealed = True
            await self._maybe_emit_generation_stats(generation)

    async def _retire_probe(self, probe: Probe, reason: str = "evolution", *,
                            prices: Optional[dict[str, float]] = None) -> float:
        """Close positions, transition to DEAD, archive. Returns reclaimed capital.
        Handles both TRADING and OBSERVING probes correctly."""
        if self.probes.get(probe.probe_id) is not probe:
            return 0.0
        if not valid_cash(self.reserve_capital):
            raise FundingError()
        self._require_current_quotes()
        if self.mode == "paper":
            self._require_fresh_assets(probe.open_positions)
        if prices is None:
            _, prices = self._liquidation_plan(probe)
        elif self.mode == "paper" and any(
                prices.get(asset) != self._mark_price(asset) for asset in probe.open_positions):
            raise MarketFeedError("source_time_invalid")
        # Prices were validated for every retiring parent before any mutation.
        for evt in probe.close_all_positions(prices, "EVOLUTION"):
            await self._emit(evt)

        # Selection is a reason for retirement, not proof that a child birth
        # already succeeded. Culls never emit a reproduction intent.
        selected = reason == "evolution_selected"
        if probe.state == ProbeState.TRADING and selected:
            probe._transition(ProbeState.REPRODUCING)
            await self._emit(ProbeEvent(EventType.PROBE_REPRODUCING, probe.probe_id,
                                       probe.summary(), timestamp=self._event_time()))
        elif probe.state in {ProbeState.TRADING, ProbeState.OBSERVING}:
            probe._transition(ProbeState.DYING)
            await self._emit(ProbeEvent(EventType.PROBE_DYING, probe.probe_id,
                                       {"reason": reason, **probe.summary()}, timestamp=self._event_time()))
        if probe.state not in {ProbeState.REPRODUCING, ProbeState.DYING}:
            raise FundingError()
        probe._transition(ProbeState.DEAD)
        probe.died_at = self._event_time()
        probe.death_reason = reason
        await self._emit(ProbeEvent(EventType.PROBE_DEAD, probe.probe_id,
                                   probe.summary(), timestamp=probe.died_at))
        # Ownership is retained in self.probes until the explicit terminal write
        # has been acknowledged. Failures cannot reclaim or archive this cash.
        reclaimed = probe.capital
        if not valid_cash(reclaimed):
            raise FundingError()
        self._archive_probe(probe)
        return reclaimed

    def _archive_probe(self, probe: Probe) -> None:
        if self.probes.get(probe.probe_id) is not probe:
            return
        generation = probe.genome.generation
        aggregate = self._generation_aggregates.get(generation)
        if aggregate is None:
            raise FundingError("generation_missing")
        # Stage every fallible calculation before either ledger owns reclaimed
        # cash. Bad aggregate arithmetic must not double-credit the account.
        staged = deepcopy(aggregate)
        staged.terminal(probe)
        if any(isinstance(value, (int, float)) and not math.isfinite(value)
               for value in vars(staged).values()):
            raise FundingError("generation_metrics_invalid")
        reserve = sum_cashflows((self.reserve_capital, probe.capital))
        if not valid_cash(reserve):
            raise FundingError()
        self._generation_aggregates[generation] = staged
        self.reserve_capital = reserve
        self._generation_dead_counts[generation] = staged.terminal_count
        self._archived_probe_count += 1
        self.dead_probes.append(probe)
        if len(self.dead_probes) > DEAD_PROBE_RETENTION:
            del self.dead_probes[:-DEAD_PROBE_RETENTION]
        del self.probes[probe.probe_id]

    # ── Lifecycle: Reproduction (strategy-delegated) ─────────────────────

    def _bind_evaluation(self) -> None:
        members = list(self.live_probes)
        self._cohort_parent_generations = {p.probe_id: (p.genome.generation, False) for p in members}
        self.strategy.bind_candidates(members)
        self._evaluation_iteration += 1
        self._cohort = EvaluationCohort(
            f"{self.run_id}:{self._evaluation_iteration}", members,
            float(self.reproduction_interval * 60))
        self._cohort_seeds = [deepcopy(p.genome) for p in members]

    def _abort_evaluation(self, reason: str) -> None:
        cohort = getattr(self, "_cohort", None)
        if cohort is not None and cohort.phase not in {"aborted", "completed"}:
            cohort.abort(reason, self._event_time().timestamp())
            self.strategy.abort_cohort()
            self._last_evaluation = cohort.to_dict()

    async def _publish_evaluation(self) -> None:
        await self._save_risk_status(self.status())
        await self._emit(ProbeEvent(event_type=EventType.SIMULATION_STATUS,
                                   probe_id="genesis", timestamp=self._event_time(), data=self.status()))

    async def _restart_evaluation(self) -> None:
        # Interrupted fitness/holdings cannot become a new comparable window.
        # Fully preflight fresh candidate accounts before closing any survivor.
        genomes = deepcopy(self._cohort_seeds)
        for genome in genomes:
            genome.generation = self.current_generation + 1
            genome.parent_ids = []
        await self._apply_replacement(EvolutionResult(genomes, list(self.probes)))
        if self.circuit_breaker_active:
            return
        self._search_epoch += 1
        self._mutation_event = 0
        self.strategy.configure_search(self._search_streams, self._search_epoch)
        self.strategy.initialize(list(self.live_probes), self.colony_config)
        self._bind_evaluation()
        await self._publish_evaluation()

    async def _advance_evaluation(self) -> bool:
        """Return whether ordinary decisions may execute in this market frame."""
        if not self._uses_cohorts:
            return True
        if self.circuit_breaker_active or self._cohort is None:
            return False
        if self._cohort.phase == "aborted":
            await self._restart_evaluation()
            return False
        now = self._event_time().timestamp()
        if self._cohort.phase == "warming":
            if all(p.evaluation_ready(now) for p in self.live_probes):
                self._cohort.start(now)
                for probe in self.live_probes:
                    probe.reset_signal_boundary(now)
                await self._publish_evaluation()
            return False
        if self._cohort.due(now):
            await self._evaluate_reproduction()
            return False
        return self._cohort.phase == "evaluating"

    async def _evaluate_reproduction(self) -> None:
        """Delegate evolution to the strategy. Called every reproduction_interval ticks."""
        if self.circuit_breaker_active:
            return
        self._require_current_quotes()
        if self._uses_cohorts:
            cohort = self._cohort
            now = self._event_time().timestamp()
            if cohort is None or not cohort.due(now):
                return
            # A completed window must rank net liquidation results, including
            # the same exit costs that retirement will actually pay. Validate
            # every candidate first; a bad sibling cannot cause a partial batch.
            closures = []
            for probe in self.live_probes:
                prices = {asset: self._mark_price(asset) for asset in probe.open_positions}
                probe.validate_liquidation(prices)
                closures.append((probe, prices))
            for probe, prices in closures:
                self._require_fresh_assets(probe.open_positions)
                for event in probe.close_all_positions(prices, "EVOLUTION"):
                    await self._emit(event)
            if self._check_circuit_breaker():
                await self._save_risk_status(self.status())
                await self._publish_risk_change("tripped")
                return
            evaluated = cohort.complete(list(self.live_probes), now)
            self._last_evaluation = cohort.to_dict()
            await self._publish_evaluation()
            self._require_current_quotes()
            result = self.strategy.evolve(list(evaluated), [], self.colony_config)
            if not set(result.retire_ids).issubset(cohort.member_ids):
                raise ValueError("Optimizer returned unknown candidate IDs")
            # Never truncate or invent candidates: the optimizer must bind the
            # exact complete proposal that will be evaluated on the next window.
            size = len(cohort.member_ids)
            children = list(result.offspring)
            if len(children) != size:
                raise ValueError("Optimizer returned an incomplete or oversized cohort")
            parents = {str(i): result.parent_map.get(str(i), children[i].parent_ids)
                       for i in range(len(children))}
            self._last_evaluation["selection"] = deepcopy(result.metadata)
            await self._publish_evaluation()
            await self._apply_replacement(EvolutionResult(children, list(self.probes), parents, result.metadata))
            if self.circuit_breaker_active:
                return
            self._bind_evaluation()
            await self._publish_evaluation()
            return
        live = [p for p in self.probes.values()
                if p.state in (ProbeState.OBSERVING, ProbeState.TRADING)]
        if len(live) < 2:
            return
        result = self.strategy.evolve(live, self.dead_probes, self.colony_config)
        await self._apply_replacement(result)
        await self._check_diversity()

    # ── Lifecycle: Death ─────────────────────────────────────────────────

    def _available_births(self, requested: int) -> int:
        if not valid_cash(self.reserve_capital) or not valid_cash(self.seed_capital) or self.seed_capital < 1:
            raise FundingError()
        count = min(requested, max(0, self.max_probes - len(self.probes)))
        while count and not can_fund(self.reserve_capital, math.fsum(self.seed_capital for _ in range(count))):
            count -= 1
        return count

    async def _inject_candidates(self, requested: int) -> None:
        if self.circuit_breaker_active or self._uses_cohorts:
            return
        count = self._available_births(requested)
        if not count:
            return
        new_genomes = self.strategy.inject_diversity(
            [p.genome for p in self.live_probes], self.dead_probes, self.colony_config,
            current_generation=self.current_generation, count=count,
            rng=self._search_streams.rng('mutation', self._search_epoch,
                                         'diversity', self._mutation_event),
        )
        self._mutation_event += 1
        if not isinstance(new_genomes, list) or len(new_genomes) > count:
            raise FundingError()
        await self._apply_replacement(EvolutionResult(new_genomes, []))

    async def _handle_die(self, probe: Probe) -> None:
        # Repeated event delivery must not credit the same account twice.
        if self.probes.get(probe.probe_id) is not probe:
            return
        self._require_current_quotes()
        if (probe.state != ProbeState.DEAD or probe.open_positions or
                not valid_cash(probe.capital) or not valid_cash(self.reserve_capital)):
            raise FundingError()
        if self._cohort is not None and self._cohort.phase == "evaluating":
            self._cohort.record_terminal(probe, probe.death_reason or "death", self._event_time().timestamp())
        probe_gen = probe.genome.generation
        self._archive_probe(probe)

        await self._maybe_emit_generation_stats(probe_gen)
        if not self._uses_cohorts and len(self.live_probes) < max(1, self.gen0_count // 2):
            await self._inject_candidates(1)
        # Other DEAD probes in this tick's batch may still own recoverable cash.
        if not self.probes and not self.circuit_breaker_active and not self._uses_cohorts:
            raise FundingError("population_extinct")

    async def _handle_self_reproduce(self, probe: Probe) -> None:
        """Fund a complete set of clones before reclaiming the parent's cash.

        Probe has already closed positions and persisted reproduction intent.
        On refusal retain that REPRODUCING parent for reconciliation.
        """
        if (self.circuit_breaker_active or self._uses_cohorts or self.probes.get(probe.probe_id) is not probe
                or probe.state != ProbeState.REPRODUCING):
            return
        self._require_current_quotes()
        children = []
        for child_index in range(self.child_count):
            child = Genome(
                **{g: getattr(probe.genome, g) for g in NUMERIC_GENES},
                assets=list(probe.genome.assets),
                generation=max(probe.genome.generation + 1, self._birth_generation_floor),
                parent_ids=[probe.probe_id],
            )
            children.append(mutate(child, mutation_rate=self.mutation_rate, colony_config=self.colony_config,
                rng=self._search_streams.rng('mutation', self._search_epoch,
                                             'self-reproduction', self._mutation_event, child_index)))
        self._mutation_event += 1
        await self._apply_replacement(
            EvolutionResult(children, [probe.probe_id]), self_reproducing=True,
        )

    # ── Tick loop ────────────────────────────────────────────────────────

    async def _tick_loop(self) -> None:
        interval = self.tick_interval_ms / 1000.0
        while self._running:
            if self._paused:
                await asyncio.sleep(0.1)
                continue
            async with self._tick_lock:
                if not self._paused and self._running:
                    await self._tick_all()
            await asyncio.sleep(interval)

        logger.info("[Genesis] Tick loop stopped.")

    def _mark_price(self, asset: str) -> float:
        if self.mode == "paper":
            tick = self._latest_ticks.get(asset)
            if tick is None:
                raise MarketFeedError("source_time_unavailable")
            validate_quote(tick, previous_slot=self._source_slots.get(asset))
        return positive_price(self._latest_prices.get(asset))

    def _require_fresh_assets(self, assets) -> None:
        if self.mode == "paper":
            for asset in assets:
                self._mark_price(asset)

    def _require_current_quotes(self) -> None:
        if self.mode == "paper" and self._market_ready:
            if not self._latest_ticks:
                raise MarketFeedError("source_time_unavailable")
            self._require_fresh_assets(self._latest_ticks)

    def _validate_ticks(self, assets: list[str], ticks) -> tuple[dict[str, MarketTick], list[Exception]]:
        """Normalize requested observations without ever reusing a missing mark.

        Paper quotes require source-time evidence independently of the adapter.
        Synthetic modeled timestamps retain their separate clock semantics.
        """
        valid = {}
        errors = []
        if not isinstance(ticks, dict):
            return valid, [MarketValueError()]
        for asset in assets:
            tick = ticks.get(asset)
            try:
                if not isinstance(tick, MarketTick) or tick.asset != asset:
                    raise MarketValueError()
                normalized = MarketTick(
                    asset, positive_price(tick.price), nonnegative_value(tick.volume),
                    nonnegative_value(tick.timestamp), tick.evidence)
                if self.mode == "paper":
                    previous = self._source_quotes.get(asset)
                    if previous is not None and isinstance(normalized.evidence, QuoteEvidence):
                        if (previous.evidence.source_slot == normalized.evidence.source_slot and
                                previous.timestamp != normalized.timestamp):
                            raise MarketFeedError("source_time_invalid")
                        # A provider refresh cannot reset monotonic source age.
                        # Carry the anchor across changed slots as well: estimated
                        # block time may be identical in adjacent slots.
                        prior_age = quote_source_age(previous,
                            wall_now=normalized.evidence.received_at,
                            monotonic_now=normalized.evidence.received_monotonic)
                        floor = max(0.0, prior_age - (normalized.timestamp - previous.timestamp))
                        normalized = replace(normalized, evidence=replace(normalized.evidence,
                            source_age_at_receipt=max(floor, quote_source_age(normalized,
                                wall_now=normalized.evidence.received_at,
                                monotonic_now=normalized.evidence.received_monotonic))))
                    validate_quote(normalized, previous_slot=self._source_slots.get(asset))
                    self._source_slots[asset] = normalized.evidence.source_slot
                    self._source_quotes[asset] = normalized
                valid[asset] = normalized
            except (MarketValueError, MarketFeedError) as error:
                errors.append(error)
        return valid, errors

    async def _tick_all(self) -> None:
        live = [p for p in self.probes.values()
                if p.state in (ProbeState.OBSERVING, ProbeState.TRADING)]
        if not live and (self.circuit_breaker_active or not self._uses_cohorts):
            if self.circuit_breaker_active:
                # All positions may have closed and capital returned to reserve.
                # Retain the explicit halt; never silently refill this population.
                self._observe_account_risk()
                await self._emit(ProbeEvent(event_type=EventType.SIMULATION_STATUS,
                                            probe_id="genesis", data=self.status(),
                                            timestamp=self._event_time()))
                return
            raise FundingError("population_extinct")

        self.tick_count += 1

        # Fetch prices and push to all probes
        all_assets = sorted({a for p in live for a in [*p.genome.assets, *p.open_positions]})
        if self._uses_cohorts:
            all_assets = sorted(set(all_assets) | set(self._candle_assets))
        # On a failed refresh, status must not present the previous batch as a
        # current valuation or use it to close/recycle a missing asset.
        self._latest_prices = {}
        self._latest_ticks = {}
        feed_failure = None
        try:
            ticks = await self.market_feed.get_ticks(all_assets)
        except MarketFeedError as error:
            # Keep only the newly validated partial batch for a final risk pass.
            # Never combine it with the previous refresh's marks.
            feed_failure = error
            ticks = error.valid_ticks
        ticks, failures = self._validate_ticks(all_assets, ticks)
        if feed_failure is not None:
            failures.insert(0, feed_failure)
        self._latest_ticks = ticks
        self._latest_prices = {asset: tick.price for asset, tick in ticks.items()}

        risk_assets: dict[str, set[str]] = {}
        for probe in live:
            eligible = risk_assets[probe.probe_id] = set()
            for asset in dict.fromkeys([*probe.genome.assets, *probe.open_positions]):
                tick = ticks.get(asset)
                if tick is None:
                    continue
                try:
                    probe.on_quote(tick)
                    eligible.add(asset)
                except Exception as error:
                    failures.append(error)

        # All probes get a bounded risk pass before any signal, reproduction,
        # reporting, or persistence failure can interrupt the decision phase.
        risk_events = []
        for probe in live:
            eligible = set()
            for asset in risk_assets[probe.probe_id]:
                try:
                    self._require_fresh_assets([asset])
                    eligible.add(asset)
                except MarketFeedError as error:
                    failures.append(error)
            # Freeze the entire valued portfolio before closes/entries change
            # its holdings. A partial quote batch can still reduce individual
            # risks, but cannot contribute a full portfolio return observation.
            try:
                if set(probe.open_positions).issubset(eligible):
                    observed_at = self._event_time().timestamp()
                    remaining_age = MAX_SOURCE_AGE_SECONDS
                    if self.mode == "paper":
                        for asset in probe.open_positions:
                            try:
                                asset_remaining = MAX_SOURCE_AGE_SECONDS - quote_source_age(ticks[asset])
                                if asset_remaining < 0:
                                    raise MarketFeedError("price_stale")
                                remaining_age = min(remaining_age, asset_remaining)
                            except MarketFeedError as error:
                                # Eligibility can expire between its first check
                                # and this valuation. Preserve fresh sibling risk
                                # checks without knowingly closing an expired mark.
                                eligible.discard(asset)
                                failures.append(error)
                    if set(probe.open_positions).issubset(eligible):
                        probe.observe_equity(assets=eligible, observed_at=observed_at,
                                             valid_until=observed_at + remaining_age)
            except Exception as error:
                # Metric errors must not interrupt the all-probe risk pass.
                failures.append(error)
            try:
                risk_events.extend(probe.risk_tick(assets=eligible))
            except ProbeStepError as error:
                risk_events.extend(error.events)
                failures.append(error.cause)
            except Exception as error:
                failures.append(error)
        # Latch from a complete fresh valuation before any awaited write can
        # fail, and before any queued entry or population allocation can run.
        tripped = False
        if not failures:
            try:
                tripped = self._check_circuit_breaker()
            except Exception as error:
                # A held quote can expire during this final valuation. Keep
                # every protective close already applied in the risk pass,
                # then stop before decisions or any population allocation.
                failures.append(error)
        for event in risk_events:
            # Persistence failures are never swallowed or retried as probe bugs.
            await self._emit(event)
        if failures:
            raise failures[0]
        if tripped:
            await self._save_risk_status(self.status())
            await self._publish_risk_change("tripped")

        # A candle outage/revision stops decisions only after fresh quote risk
        # checks have completed. Revalidate quotes after this awaited request.
        if not self.circuit_breaker_active:
            await self._refresh_candles()

        decisions_allowed = await self._advance_evaluation()
        # Replacement invalidates the earlier list of owned candidates.
        live = list(self.live_probes)

        # Broadcast prices every 5 ticks
        if self.tick_count % 5 == 0:
            price_data = {
                asset: {"price": t.price, "volume": t.volume,
                        "timestamp": t.timestamp, "account_currency": "USD",
                        "mode": self.mode}
                for asset, t in ticks.items() if t.price > 0
            }
            if price_data:
                await self._emit(ProbeEvent(
                    timestamp=self._event_time(),
                    event_type=EventType.PRICE_UPDATE,
                    probe_id="genesis",
                    data={"prices": price_data, "tick": self.tick_count},
                ))

        # Tick each probe — collect death and self-reproduce events
        dying: list[Probe] = []
        self_reproducing: list[Probe] = []

        for probe in live:
            # Event writes and broadcasts above may have aged every quote.
            self._require_current_quotes()
            was_halted = self.circuit_breaker_active
            try:
                max_life = self.colony_config.max_lifespan_ticks
                age = self.tick_count - probe.birth_tick
                if self._uses_cohorts:
                    started = self._cohort.started_at if self._cohort else None
                    age = None if started is None else (self._event_time().timestamp() - started) / 60
                if max_life and age is not None and age >= max_life and not probe._should_die():
                    # A profitable candidate cannot breed or fill a pending
                    # entry on the same tick its hard lifespan limit expires.
                    events = probe._trigger_die("max_lifespan")
                else:
                    events = probe.tick(check_risk=False,
                                        allow_new_risk=not self.circuit_breaker_active and decisions_allowed,
                                        allow_reproduction=not self._uses_cohorts,
                                        risk_check=lambda: self._check_circuit_breaker() or self.circuit_breaker_active)
            except ProbeStepError as error:
                for event in error.events:
                    await self._emit(event)
                # Accounts and positions remain owned for reconciliation. Do
                # not breed/reclaim capital after an incomplete decision phase.
                raise error.cause
            # Forced closes can also incur costs. Latch before awaited writes
            # or the next candidate decision, preserving all close events.
            cost_risk_error = None
            try:
                self._check_circuit_breaker()
            except Exception as error:
                cost_risk_error = error
            for evt in events:
                await self._emit(evt)
                if evt.event_type == EventType.PROBE_DEAD:
                    dying.append(probe)
                elif evt.event_type == EventType.PROBE_REPRODUCING:
                    self_reproducing.append(probe)

            if cost_risk_error is not None:
                raise cost_risk_error
            if self.circuit_breaker_active and not was_halted:
                await self._save_risk_status(self.status())
                await self._publish_risk_change("tripped")

        # Process death events
        for probe in dying:
            await self._handle_die(probe)

        # Process self-triggered reproduction events (probe hit ROI/dollar target)
        for probe in self_reproducing:
            await self._handle_self_reproduce(probe)

        # Strategy-driven reproduction at intervals
        if (not self._uses_cohorts and not self.circuit_breaker_active and
                self.tick_count % self.reproduction_interval == 0):
            await self._evaluate_reproduction()

        if (not self._uses_cohorts and not self.circuit_breaker_active and
                not any(p.state in (ProbeState.OBSERVING, ProbeState.TRADING) for p in self.probes.values())):
            raise FundingError("population_extinct")

        # Batched probe updates every 10 ticks, system status every 5
        if self.tick_count % 5 == 0:
            await self._emit(ProbeEvent(
                timestamp=self._event_time(),
                event_type=EventType.SIMULATION_STATUS,
                probe_id="genesis",
                data=self.status(),
            ))
        if self.tick_count % 10 == 0:
            for p in self.live_probes:
                await self._emit(ProbeEvent(
                    timestamp=self._event_time(),
                    event_type=EventType.PROBE_UPDATE,
                    probe_id=p.probe_id,
                    data=p.summary(),
                ))

        # Fitness snapshots
        if self.tick_count % self.snapshot_interval == 0:
            await self._capture_fitness_snapshots()

        # Log status
        if self.tick_count % 50 == 0:
            self._log_status()

    # ── Circuit breaker ──────────────────────────────────────────────────

    def _account_equity(self) -> float:
        """Reserve plus every still-owned account, with fresh held-asset marks.

        Cumulative recycled funding (`total_deployed`) is never a loss baseline.
        Cash does not need a quote; every open holding does.
        """
        values = [nonnegative_value(self.reserve_capital)]
        for probe in self.probes.values():
            values.append(nonnegative_value(probe.capital))
            for asset, trade in probe.open_positions.items():
                price = self._mark_price(asset)
                # The exact accepted controller mark must also be the probe's
                # mark used by protective exits and subsequent decisions.
                if probe._marks.get(asset) != price:
                    raise MarketValueError()
                values.append(trade.marked_value(price))
        return nonnegative_value(math.fsum(values))

    def _observe_account_risk(self) -> Optional[tuple[float, float]]:
        if self._initial_total_capital <= 0:
            return None
        baseline = positive_price(self._initial_total_capital)
        total = self._account_equity()
        loss = max(0.0, 1.0 - total / baseline)
        self._risk_control.update(baseline_equity=baseline, observed_equity=total,
                                  observed_loss_fraction=loss,
                                  observed_at=self._event_time().isoformat())
        return total, loss

    def _check_circuit_breaker(self) -> bool:
        observation = self._observe_account_risk()
        if observation is None or self.circuit_breaker_active:
            return False
        total, loss = observation
        # Compare equity against the boundary directly: subtracting two nearly
        # equal normalized floats can put an exact threshold on the wrong side.
        if total > self._initial_total_capital * (1.0 - self.circuit_breaker_drop_pct):
            return False
        self.circuit_breaker_active = True
        self.set_lifecycle("risk_halted")
        self.state_persisted = False
        self._risk_control.update(trip_id=str(uuid.uuid4()), tripped_at=self._event_time().isoformat(),
                                  trip_equity=total, trip_loss_fraction=loss)
        for probe in self.probes.values():
            probe.discard_entry_intents()
        logger.warning("[Genesis] Account-loss circuit breaker halted new risk")
        return True

    async def _save_risk_status(self, status: dict) -> None:
        self.state_persisted = False
        if self._persist_risk_status is not None:
            await self._persist_risk_status({**status, "state_persisted": False})
            self.state_persisted = True

    async def _publish_risk_change(self, action: str) -> None:
        await self._emit(ProbeEvent(event_type=EventType.CIRCUIT_BREAKER,
                                   probe_id="genesis", timestamp=self._event_time(),
                                   data={"action": action, "circuit_breaker": self.circuit_breaker_active,
                                         "risk_control": deepcopy(self._risk_control)}))
        await self._emit(ProbeEvent(event_type=EventType.SIMULATION_STATUS,
                                   probe_id="genesis", timestamp=self._event_time(), data=self.status()))

    def _validate_risk_recovery(self) -> None:
        if not self.live_probes:
            raise RiskRecoveryError("risk_no_candidates")
        try:
            # Recovery also requires all candidate quotes, since ordinary
            # decisions resume on the next independently validated quote batch.
            self._require_current_quotes()
            if self.mode == "paper":
                self._require_fresh_assets({asset for p in self.live_probes
                                            for asset in [*p.genome.assets, *p.open_positions]})
            observation = self._observe_account_risk()
        except (MarketFeedError, MarketValueError, OverflowError):
            raise RiskRecoveryError("risk_quotes_unavailable") from None
        if observation is None or observation[0] <= self._initial_total_capital * (1.0 - self.circuit_breaker_drop_pct):
            raise RiskRecoveryError("risk_loss_unrecovered")

    async def recover_circuit_breaker(self, trip_id: str) -> None:
        """Explicit acknowledgement, never a loss-baseline reset or retry loop."""
        async with self._tick_lock:
            if not self.circuit_breaker_active or self.lifecycle_status != "risk_halted":
                raise RiskRecoveryError("risk_not_halted")
            if trip_id != self._risk_control["trip_id"]:
                raise RiskRecoveryError("risk_trip_changed")
            self._validate_risk_recovery()
            # Bring decisions up to date while entries remain latched. A data
            # problem here rejects recovery, preserving protective monitoring.
            try:
                await self._refresh_candles(warmup=True)
            except MarketFeedError:
                raise RiskRecoveryError("risk_history_unavailable") from None
            self._validate_risk_recovery()
            recovered_at = self._event_time()
            proposal = {**self._risk_control,
                        "recovery_count": self._risk_control["recovery_count"] + 1,
                        "last_recovered_at": recovered_at.isoformat()}
            await self._save_risk_status({**self.status(), "status": "running",
                                         "circuit_breaker": False, "risk_control": proposal})
            try:
                self._validate_risk_recovery()
            except RiskRecoveryError:
                # A slow acknowledged write may outlive the quotes. Compensate
                # its prospective status without ever releasing the live latch.
                await self._save_risk_status(self.status())
                raise
            for probe in self.probes.values():
                probe.reset_signal_boundary(self._event_time().timestamp())
            self._risk_control = {**proposal,
                                  **{key: self._risk_control[key] for key in
                                     ("observed_equity", "observed_loss_fraction", "observed_at")}}
            self.circuit_breaker_active = False
            self.set_lifecycle("running")
            try:
                await self._publish_risk_change("recovered")
            except BaseException:
                # The manager awaits this operation in a bounded child task.
                # Stop its queued tick before releasing our lock on failure or
                # cancellation; supervision will persist the terminal failure.
                # Preserve the recovery that storage already acknowledged.
                self._running = False
                self._paused = True
                raise

    # ── Diversity ────────────────────────────────────────────────────────

    async def _check_diversity(self) -> None:
        genomes = [p.genome for p in self.live_probes]
        if len(genomes) < 2:
            return
        diversity = self.strategy.compute_diversity(genomes)
        if diversity < self.diversity_threshold:
            await self._inject_candidates(2)

    # ── Fitness snapshots ────────────────────────────────────────────────

    async def _capture_fitness_snapshots(self) -> None:
        for probe in self.live_probes:
            self._require_current_quotes()
            snapshot = FitnessSnapshot(
                probe_id=probe.probe_id,
                generation=probe.genome.generation,
                tick=self.tick_count,
                fitness_score=probe.fitness,
                roi=probe.roi,
                sharpe_ratio=probe.sharpe,
                max_drawdown=probe.max_drawdown,
                win_rate=probe.win_rate,
                trade_count=probe.num_trades,
                current_capital=probe.capital,
                metrics=probe.metrics(),
                captured_at=self._event_time(),
            )
            await self._emit(ProbeEvent(
                timestamp=snapshot.captured_at,
                event_type=EventType.FITNESS_SNAPSHOT,
                probe_id=probe.probe_id,
                data={
                    "generation": snapshot.generation,
                    "tick": snapshot.tick,
                    "fitness_score": snapshot.fitness_score,
                    "roi": snapshot.roi,
                    "sharpe_ratio": snapshot.sharpe_ratio,
                    "max_drawdown": snapshot.max_drawdown,
                    "win_rate": snapshot.win_rate,
                    "trade_count": snapshot.trade_count,
                    "current_capital": snapshot.current_capital,
                    "metrics": snapshot.metrics,
                },
            ))

    # ── Generation stats ─────────────────────────────────────────────────

    async def _maybe_emit_generation_stats(self, generation: int) -> None:
        aggregate = self._generation_aggregates.get(generation)
        if (aggregate is None or not aggregate.sealed or aggregate.unacknowledged_births or
                not aggregate.count or aggregate.terminal_count != aggregate.count):
            return
        ended_at = self._event_time()
        stats = aggregate.summary(generation, ended_at)
        await self._emit(ProbeEvent(EventType.GENERATION_COMPLETE, "genesis", stats, timestamp=ended_at))
        # A failed write leaves the sealed aggregate available for reconciliation
        # and an explicit retry; completion is never acknowledged in advance.
        del self._generation_aggregates[generation]
        self._generation_probe_counts.pop(generation, None)
        self._generation_dead_counts.pop(generation, None)
        self._generation_reproduced.pop(generation, None)
        self._emitted_generation_stats.add(generation)
        if len(self._emitted_generation_stats) > GENERATION_HISTORY_RETENTION:
            self._emitted_generation_stats.remove(min(self._emitted_generation_stats))
        logger.info(f"[Genesis] Generation {generation} complete: {aggregate.count} probes")

    # ── Event emission ───────────────────────────────────────────────────

    async def _emit(self, event: ProbeEvent) -> None:
        if self._on_event:
            # In-memory mutations cannot continue after their durable write failed.
            await self._on_event(event)

    # ── Reporting ────────────────────────────────────────────────────────

    def _log_status(self) -> None:
        live = self.live_probes
        if not live:
            return
        avg_roi = sum(p.roi for p in live) / len(live)
        avg_fitness = sum(p.fitness for p in live) / len(live)
        logger.info(
            f"[Genesis] Tick={self.tick_count} | {len(live)} live | "
            f"Avg ROI={avg_roi*100:.1f}% | Avg Fitness={avg_fitness:.3f} | "
            f"Dead={self._archived_probe_count} | Reserve=${self.reserve_capital:.0f}"
        )
