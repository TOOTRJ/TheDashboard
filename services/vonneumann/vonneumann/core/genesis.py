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
from dataclasses import replace
from datetime import datetime
from typing import Optional, Callable, Awaitable

from .clock import timestamp_datetime, utc_now
from .colony_config import ColonyConfig
from .evolution import FITNESS_POLICY, NUMERIC_GENES, mutate, population_diversity
from .equity_metrics import EQUITY_METRICS_POLICY
from .genome import Genome, random_genome
from .funding import FundingError, can_fund, funding_tolerance, sum_cashflows, valid_cash
from .names import generate_probe_name
from .market_validation import MarketValueError, nonnegative_value, positive_price, position_value
from .probe import Probe, ProbeStepError
from .strategies.base import EvolutionResult, EvolutionStrategy
from .types import EventType, ProbeEvent, ProbeState, FitnessSnapshot
from ..market.feed import MarketFeed, MarketFeedError, MarketTick, QuoteEvidence
from ..market.candles import CandleHistory, CANDLE_POLICY
from ..market.quote_freshness import MAX_SOURCE_AGE_SECONDS, QUOTE_POLICY, quote_source_age, validate_quote

logger = logging.getLogger(__name__)


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
    ):
        self.market_feed = market_feed
        self.strategy = strategy
        self.user_id = user_id
        self.mode = mode

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
        self.circuit_breaker_drop_pct = circuit_breaker_drop_pct
        self.circuit_breaker_active = False

        # State
        self.colony_id = colony_id
        self.run_id = colony_id  # Alias for backward compatibility
        self.probes: dict[str, Probe] = {}
        self.dead_probes: list[Probe] = []
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

        # Snapshot interval
        self.snapshot_interval = 25

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
                    entry = positive_price(trade.entry_price)
                    amount = nonnegative_value(trade.amount)
                    values.append(position_value(amount, entry, price))
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
            "mode": self.mode,
            "generation": self.current_generation,
            "tick": self.tick_count,
            "live_probes": len(live),
            "dead_probes": len(self.dead_probes),
            "total_probes": len(self.probes) + len(self.dead_probes),
            "reserve_capital": round(reserve, 2) if reserve is not None else None,
            "active_capital": round(active, 2) if active is not None else None,
            "total_capital": round(total, 2) if total is not None else None,
            "valuation_available": total is not None,
            "circuit_breaker": self.circuit_breaker_active,
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
        self._lifecycle_status = status
        self._running = status in {"running", "paused"}
        self._paused = status == "paused"

    async def prepare(self) -> None:
        """Seed and persist the population before a supervised loop may start."""
        self.started_at = utc_now()
        self._wall_started_monotonic = time.monotonic()
        logger.info(f"[Genesis] Starting in {self.mode} mode. Seeding {self.gen0_count} Gen-0 probes.")

        genomes = [random_genome(generation=0, colony_config=self.colony_config)
                   for _ in range(self.gen0_count)]
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

        self._initial_total_capital = self.active_capital + self.reserve_capital

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
        known_parents = set(self.probes) | {p.probe_id for p in self.dead_probes}
        if any(key not in {str(i) for i in range(len(result.offspring))}
               for key in result.parent_map):
            raise FundingError()
        for i, genome in enumerate(result.offspring):
            if (not isinstance(genome, Genome) or
                    any(not valid_cash(getattr(genome, gene)) for gene in NUMERIC_GENES) or
                    not isinstance(genome.generation, int) or isinstance(genome.generation, bool) or
                    genome.generation < 0 or not isinstance(genome.assets, list) or
                    not genome.assets or not all(isinstance(a, str) for a in genome.assets) or
                    len(set(genome.assets)) != len(genome.assets) or
                    not set(genome.assets).issubset(allowed_assets)):
                raise FundingError()
            parents = result.parent_map.get(str(i), genome.parent_ids)
            if (not isinstance(parents, list) or
                    not all(isinstance(pid, str) and pid in known_parents for pid in parents)):
                raise FundingError()
            child = deepcopy(genome)
            child.parent_ids = list(parents)
            children.append(child)
        return children, retired, balances

    async def _apply_replacement(self, result: EvolutionResult, *, self_reproducing: bool = False) -> None:
        self._require_current_quotes()
        children, retired, balances = self._preflight_replacement(result, self_reproducing=self_reproducing)
        reclaimed_flows = [self.reserve_capital]
        for probe, prices in retired.values():
            reclaimed_flows.append(await self._retire_probe(probe, prices=prices))
            self.reserve_capital = sum_cashflows(reclaimed_flows)
        for genome, balance in zip(children, balances):
            # Retirement/birth persistence can take longer than a quote's life.
            self._require_current_quotes()
            new_probe = await self._spawn_probe(genome, self.seed_capital, _planned_reserve=balance)
            if new_probe is None:
                # A validated, serialized batch must never silently lose births.
                # Do not roll back uncertain persistence or redistribute cash.
                raise FundingError()
            if genome.parent_ids and genome.parent_ids[0] in retired:
                parent = retired[genome.parent_ids[0]][0]
                if hasattr(self.strategy, "remap_probe_id"):
                    self.strategy.remap_probe_id(parent.probe_id, new_probe.probe_id)
        for probe, _ in retired.values():
            await self._maybe_emit_generation_stats(probe.genome.generation)

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

        # State transition depends on current state
        if probe.state == ProbeState.TRADING:
            probe._transition(ProbeState.REPRODUCING)
            await self._emit(ProbeEvent(
                timestamp=self._event_time(),
                event_type=EventType.PROBE_REPRODUCING,
                probe_id=probe.probe_id,
                data=probe.summary(),
            ))
            probe._transition(ProbeState.DEAD)
        elif probe.state == ProbeState.OBSERVING:
            probe._transition(ProbeState.DYING)
            probe.died_at = self._event_time()
            probe.death_reason = reason
            await self._emit(ProbeEvent(
                timestamp=probe.died_at,
                event_type=EventType.PROBE_DYING,
                probe_id=probe.probe_id,
                data={"reason": reason, **probe.summary()},
            ))
            probe._transition(ProbeState.DEAD)
        else:
            probe.state = ProbeState.DEAD

        reclaimed = probe.capital
        if not valid_cash(reclaimed):
            raise FundingError()
        self.reserve_capital = sum_cashflows((self.reserve_capital, reclaimed))

        gen = probe.genome.generation
        self._generation_reproduced[gen] = self._generation_reproduced.get(gen, 0) + 1
        self.dead_probes.append(probe)
        if probe.probe_id in self.probes:
            del self.probes[probe.probe_id]

        return reclaimed

    # ── Lifecycle: Reproduction (strategy-delegated) ─────────────────────

    async def _evaluate_reproduction(self) -> None:
        """Delegate evolution to the strategy. Called every reproduction_interval ticks."""
        self._require_current_quotes()
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
        count = self._available_births(requested)
        if not count:
            return
        new_genomes = self.strategy.inject_diversity(
            [p.genome for p in self.live_probes], self.dead_probes, self.colony_config,
            current_generation=self.current_generation, count=count,
        )
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
        self.reserve_capital = sum_cashflows((self.reserve_capital, probe.capital))

        probe_gen = probe.genome.generation
        self._generation_dead_counts[probe_gen] = self._generation_dead_counts.get(probe_gen, 0) + 1
        self.dead_probes.append(probe)
        del self.probes[probe.probe_id]

        await self._maybe_emit_generation_stats(probe_gen)
        if len(self.live_probes) < max(1, self.gen0_count // 2):
            await self._inject_candidates(1)
        # Other DEAD probes in this tick's batch may still own recoverable cash.
        if not self.probes:
            raise FundingError("population_extinct")

    async def _handle_self_reproduce(self, probe: Probe) -> None:
        """Fund a complete set of clones before reclaiming the parent's cash.

        Probe has already closed positions and persisted reproduction intent.
        On refusal retain that REPRODUCING parent for reconciliation.
        """
        if self.probes.get(probe.probe_id) is not probe or probe.state != ProbeState.REPRODUCING:
            return
        self._require_current_quotes()
        children = []
        for _ in range(self.child_count):
            child = Genome(
                **{g: getattr(probe.genome, g) for g in NUMERIC_GENES},
                assets=list(probe.genome.assets),
                generation=probe.genome.generation + 1,
                parent_ids=[probe.probe_id],
            )
            children.append(mutate(child, mutation_rate=self.mutation_rate, colony_config=self.colony_config))
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
        if self.circuit_breaker_active:
            raise RuntimeError("Circuit breaker stopped execution")

        live = [p for p in self.probes.values()
                if p.state in (ProbeState.OBSERVING, ProbeState.TRADING)]
        if not live:
            raise FundingError("population_extinct")

        self.tick_count += 1

        # Fetch prices and push to all probes
        all_assets = sorted({a for p in live for a in [*p.genome.assets, *p.open_positions]})
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
        for event in risk_events:
            # Persistence failures are never swallowed or retried as probe bugs.
            await self._emit(event)
        if failures:
            raise failures[0]

        # A candle outage/revision stops decisions only after fresh quote risk
        # checks have completed. Revalidate quotes after this awaited request.
        await self._refresh_candles()

        # Broadcast prices every 5 ticks
        if self.tick_count % 5 == 0:
            price_data = {
                asset: {"price": round(t.price, 6), "volume": round(t.volume, 2)}
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
            try:
                events = probe.tick(check_risk=False)
            except ProbeStepError as error:
                for event in error.events:
                    await self._emit(event)
                # Accounts and positions remain owned for reconciliation. Do
                # not breed/reclaim capital after an incomplete decision phase.
                raise error.cause
            for evt in events:
                await self._emit(evt)
                if evt.event_type == EventType.PROBE_DYING:
                    dying.append(probe)
                elif evt.event_type == EventType.PROBE_REPRODUCING:
                    self_reproducing.append(probe)

        # Process death events
        for probe in dying:
            await self._handle_die(probe)

        # Process self-triggered reproduction events (probe hit ROI/dollar target)
        for probe in self_reproducing:
            await self._handle_self_reproduce(probe)

        # Max lifespan enforcement
        max_life = self.colony_config.max_lifespan_ticks
        if max_life:
            for probe in list(self.probes.values()):
                if probe.state in (ProbeState.OBSERVING, ProbeState.TRADING):
                    age = self.tick_count - probe.birth_tick
                    if age >= max_life:
                        self._require_current_quotes()
                        events = probe._trigger_die("max_lifespan")
                        for evt in events:
                            await self._emit(evt)
                        await self._handle_die(probe)

        # Strategy-driven reproduction at intervals
        if self.tick_count % self.reproduction_interval == 0:
            await self._evaluate_reproduction()

        if not any(p.state in (ProbeState.OBSERVING, ProbeState.TRADING) for p in self.probes.values()):
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

        # Circuit breaker
        self._check_circuit_breaker()

        # Log status
        if self.tick_count % 50 == 0:
            self._log_status()

    # ── Circuit breaker ──────────────────────────────────────────────────

    def _check_circuit_breaker(self) -> None:
        self._require_current_quotes()
        total = self.active_capital + self.reserve_capital
        if self._initial_total_capital <= 0:
            return
        drop = (self._initial_total_capital - total) / self._initial_total_capital
        if drop >= self.circuit_breaker_drop_pct and not self.circuit_breaker_active:
            logger.critical(f"[Genesis] CIRCUIT BREAKER! Capital dropped {drop*100:.1f}%")
            self.circuit_breaker_active = True

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
        if generation in self._emitted_generation_stats:
            return
        live_at_gen = [
            p for p in self.probes.values()
            if p.genome.generation == generation and p.state != ProbeState.DEAD
        ]
        if live_at_gen:
            return

        all_gen_probes = [
            p for p in list(self.probes.values()) + self.dead_probes
            if p.genome.generation == generation
        ]
        if not all_gen_probes:
            return

        total = len(all_gen_probes)
        alive = sum(1 for p in all_gen_probes if p.state != ProbeState.DEAD)
        dead = total - alive
        reproduced = self._generation_reproduced.get(generation, 0)

        fitness_scores = [p.fitness for p in all_gen_probes]
        rois = [p.roi for p in all_gen_probes]
        capitals = [p.capital for p in all_gen_probes]
        win_rates = [p.win_rate for p in all_gen_probes if p.num_trades > 0]
        diversity = population_diversity([p.genome for p in all_gen_probes]) if len(all_gen_probes) >= 2 else 1.0

        stats = {
            "generation": generation,
            "started_at": min(p.born_at for p in all_gen_probes).isoformat(),
            "ended_at": self._event_time().isoformat(),
            "total_probes": total,
            "alive_probes": alive,
            "dead_probes": dead,
            "reproduced_count": reproduced,
            "best_fitness": round(max(fitness_scores), 4) if fitness_scores else 0,
            "avg_fitness": round(sum(fitness_scores) / len(fitness_scores), 4) if fitness_scores else 0,
            "worst_fitness": round(min(fitness_scores), 4) if fitness_scores else 0,
            "total_capital": round(sum(capitals), 2),
            "avg_capital": round(sum(capitals) / len(capitals), 2) if capitals else 0,
            "total_trades": sum(p.num_trades for p in all_gen_probes),
            "avg_win_rate": round(sum(win_rates) / len(win_rates), 4) if win_rates else 0,
            "best_roi": round(max(rois), 4) if rois else 0,
            "avg_roi": round(sum(rois) / len(rois), 4) if rois else 0,
            "genome_diversity": round(diversity, 4),
        }

        self._emitted_generation_stats.add(generation)
        logger.info(f"[Genesis] Generation {generation} complete: {total} probes, best={stats['best_fitness']}")

        await self._emit(ProbeEvent(
            timestamp=self._event_time(),
            event_type=EventType.GENERATION_COMPLETE,
            probe_id="genesis",
            data=stats,
        ))

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
            f"Dead={len(self.dead_probes)} | Reserve=${self.reserve_capital:.0f}"
        )
