"""
Genesis Controller — the top-level orchestrator.

Responsibilities:
  - Spawn and fund Gen-0 probes (respecting ColonyConfig)
  - Evaluate fitness-ranked reproduction at intervals (not per-tick)
  - Handle death events (reclaim capital, best-of-dead auto-spawn)
  - Enforce population cap, capital limits, max lifespan
  - Run circuit breakers and diversity injection
  - Drive the tick loop and broadcast events
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

from .colony_config import ColonyConfig
from .evolution import (
    inject_diversity,
    population_diversity,
    reproduce,
    select_parents_by_fitness,
    tournament_select,
)
from .genome import Genome, random_genome
from .names import generate_probe_name
from .probe import Probe
from .types import EventType, ProbeEvent, ProbeState, FitnessSnapshot
from ..market.feed import MarketFeed

logger = logging.getLogger(__name__)


class GenesisController:
    """Orchestrates the entire Von Neumann probe colony."""

    def __init__(
        self,
        market_feed: MarketFeed,
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
        self.capital_split = capital_split
        self.diversity_threshold = diversity_threshold

        # Colony config (gene overrides, enabled genes, etc.)
        self.colony_config = colony_config or ColonyConfig()

        # Timing
        self.tick_interval_ms = tick_interval_ms

        # Safety
        self.circuit_breaker_drop_pct = circuit_breaker_drop_pct
        self.circuit_breaker_active = False

        # State
        self.run_id = str(uuid.uuid4())
        self.probes: dict[str, Probe] = {}
        self.dead_probes: list[Probe] = []
        self.current_generation = 0
        self.tick_count = 0
        self._running = False
        self._paused = False
        self.started_at: Optional[datetime] = None

        # Event callback
        self._on_event = on_event

        # Capital tracking
        self._initial_total_capital = 0.0

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
            f"[Genesis] Init. mode={mode} max_probes={max_probes} "
            f"max_capital=${max_capital} gen0={gen0_count} "
            f"repro_interval={self.reproduction_interval}"
        )

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def live_probes(self) -> list[Probe]:
        return [p for p in self.probes.values() if p.state != ProbeState.DEAD]

    @property
    def active_capital(self) -> float:
        return sum(p.capital for p in self.live_probes)

    def status(self) -> dict:
        live = self.live_probes
        return {
            "status": "running" if self._running and not self._paused else
                      "paused" if self._paused else "stopped",
            "run_id": self.run_id,
            "mode": self.mode,
            "generation": self.current_generation,
            "tick": self.tick_count,
            "live_probes": len(live),
            "dead_probes": len(self.dead_probes),
            "total_probes": len(live) + len(self.dead_probes),
            "reserve_capital": round(self.reserve_capital, 2),
            "active_capital": round(self.active_capital, 2),
            "total_capital": round(self.reserve_capital + self.active_capital, 2),
            "circuit_breaker": self.circuit_breaker_active,
            "diversity": round(
                population_diversity([p.genome for p in live]) if len(live) >= 2 else 1.0,
                4,
            ),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "uptime_secs": (
                (datetime.now(timezone.utc) - self.started_at).total_seconds()
                if self.started_at else 0
            ),
            "jup_api_calls": (
                self.market_feed.api_call_count
                if hasattr(self.market_feed, "api_call_count") else 0
            ),
        }

    # ── Startup ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        self.started_at = datetime.now(timezone.utc)
        self._running = True
        self._paused = False
        logger.info(f"[Genesis] Starting in {self.mode} mode. Seeding {self.gen0_count} Gen-0 probes.")

        for _ in range(self.gen0_count):
            genome = random_genome(generation=0, colony_config=self.colony_config)
            await self._spawn_probe(genome, self.seed_capital)

        # Backfill price history for paper mode
        if self.mode == "paper":
            await self._backfill_probes()

        self._initial_total_capital = self.active_capital + self.reserve_capital

        await self._emit(ProbeEvent(
            event_type=EventType.SIMULATION_STATUS,
            probe_id="genesis",
            data=self.status(),
        ))

        await self._tick_loop()

    async def _backfill_probes(self) -> None:
        if not hasattr(self.market_feed, 'backfill_probe'):
            return
        all_assets = list({a for p in self.live_probes for a in p.genome.assets})
        logger.info(f"[Genesis] Backfilling {len(all_assets)} assets...")
        history = await self.market_feed.backfill_probe(all_assets, timeframe_minutes=15, limit=100)
        for probe in self.live_probes:
            for asset in probe.genome.assets:
                for candle in history.get(asset, []):
                    probe.on_price_update(asset, candle["price"], candle["volume"])

    async def stop(self) -> None:
        self._running = False
        logger.info("[Genesis] Stopping.")
        await self._emit(ProbeEvent(
            event_type=EventType.SIMULATION_STATUS,
            probe_id="genesis",
            data={**self.status(), "status": "stopped"},
        ))

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    # ── Probe spawning ───────────────────────────────────────────────────

    async def _spawn_probe(self, genome: Genome, capital: float) -> Optional[Probe]:
        live_count = len(self.live_probes)
        if live_count >= self.max_probes:
            return None
        if capital < 1.0 or self.reserve_capital < capital:
            return None

        probe = Probe(
            genome=genome,
            initial_capital=capital,
            mode=self.mode,
            probe_name=generate_probe_name(genome.generation),
        )
        probe.birth_tick = self.tick_count
        probe.set_funded()
        probe.set_observing()

        self.probes[probe.probe_id] = probe
        self.reserve_capital -= capital
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
            event_type=EventType.PROBE_BORN,
            probe_id=probe.probe_id,
            data=probe.summary(),
        ))
        return probe

    # ── Lifecycle: Reproduction ──────────────────────────────────────────

    async def _evaluate_reproduction(self) -> None:
        """
        Fitness-ranked reproduction. Called every reproduction_interval ticks.
        Top 30% by fitness reproduce (if they meet the benchmark floor).
        """
        live = [p for p in self.probes.values()
                if p.state in (ProbeState.OBSERVING, ProbeState.TRADING)]
        if len(live) < 2:
            return

        parents = select_parents_by_fitness(
            live, top_pct=0.30, min_trades=3, min_roi=0.0
        )

        for parent in parents:
            # Floor check: ROI must meet minimum benchmark
            if parent.roi < parent.genome.benchmark_target_pct:
                continue
            await self._handle_reproduce(parent)

    async def _handle_reproduce(self, parent: Probe) -> None:
        logger.info(
            f"[Genesis] {parent.probe_name} reproducing. "
            f"Fitness={parent.fitness:.3f} ROI={parent.roi*100:.1f}%"
        )

        # Close all open positions
        events = parent._trigger_reproduce()
        for evt in events:
            await self._emit(evt)

        live_genomes = [p.genome for p in self.live_probes if p is not parent]

        # Use tournament selection for mate
        live_list = [p for p in self.live_probes if p is not parent]
        mate = tournament_select(live_list, k=3)
        mate_genomes = live_genomes if mate is None else [g for g in live_genomes]

        child_genomes = reproduce(
            parent=parent.genome,
            population=mate_genomes,
            num_children=self.child_count,
            mutation_rate=self.mutation_rate,
            colony_config=self.colony_config,
        )

        child_capital = parent.capital * self.capital_split
        remaining = parent.capital - (child_capital * len(child_genomes))
        self.reserve_capital += max(0, remaining)

        for child_genome in child_genomes:
            child_genome.parent_ids = [parent.probe_id]
            if mate:
                child_genome.parent_ids.append(mate.probe_id)
            await self._spawn_probe(child_genome, child_capital)

        # Archive parent
        parent_gen = parent.genome.generation
        self._generation_reproduced[parent_gen] = self._generation_reproduced.get(parent_gen, 0) + 1
        self.dead_probes.append(parent)
        parent.state = ProbeState.DEAD
        if parent.probe_id in self.probes:
            del self.probes[parent.probe_id]

        await self._check_diversity()
        await self._maybe_emit_generation_stats(parent_gen)

    # ── Lifecycle: Death ─────────────────────────────────────────────────

    async def _handle_die(self, probe: Probe) -> None:
        reclaimed = probe.capital
        self.reserve_capital += reclaimed

        probe_gen = probe.genome.generation
        self._generation_dead_counts[probe_gen] = self._generation_dead_counts.get(probe_gen, 0) + 1
        self.dead_probes.append(probe)
        if probe.probe_id in self.probes:
            del self.probes[probe.probe_id]

        await self._maybe_emit_generation_stats(probe_gen)

        # Auto-spawn: best-of-dead instead of random
        live_count = len(self.live_probes)
        if live_count < self.gen0_count // 2 and self.reserve_capital >= self.seed_capital:
            logger.info("[Genesis] Population low — spawning from best-of-dead")
            if self.dead_probes:
                recent_dead = self.dead_probes[-50:]
                best = max(recent_dead, key=lambda p: p.fitness)
                from .evolution import mutate
                child_genome = Genome(
                    **{g: getattr(best.genome, g) for g in Genome.__dataclass_fields__ if hasattr(best.genome, g) and g not in ('assets', 'generation', 'parent_ids')},
                    assets=list(best.genome.assets),
                    generation=self.current_generation,
                    parent_ids=[best.probe_id],
                )
                child_genome = mutate(child_genome, mutation_rate=0.30, colony_config=self.colony_config)
                await self._spawn_probe(child_genome, self.seed_capital)
            else:
                genome = random_genome(generation=self.current_generation, colony_config=self.colony_config)
                await self._spawn_probe(genome, self.seed_capital)

    # ── Tick loop ────────────────────────────────────────────────────────

    async def _tick_loop(self) -> None:
        interval = self.tick_interval_ms / 1000.0
        while self._running:
            if self._paused:
                await asyncio.sleep(0.1)
                continue
            try:
                await self._tick_all()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Genesis] Tick error: {e}", exc_info=True)
                await asyncio.sleep(1)

        logger.info("[Genesis] Tick loop stopped.")

    async def _tick_all(self) -> None:
        if self.circuit_breaker_active:
            return

        live = [p for p in self.probes.values()
                if p.state in (ProbeState.OBSERVING, ProbeState.TRADING)]
        if not live:
            return

        self.tick_count += 1

        # Fetch prices and push to all probes
        all_assets = list({a for p in live for a in p.genome.assets})
        ticks = await self.market_feed.get_ticks(all_assets)

        for probe in live:
            for asset in probe.genome.assets:
                if asset in ticks:
                    tick = ticks[asset]
                    probe.on_price_update(asset, tick.price, tick.volume)

        # Broadcast prices every 5 ticks
        if self.tick_count % 5 == 0:
            price_data = {
                asset: {"price": round(t.price, 6), "volume": round(t.volume, 2)}
                for asset, t in ticks.items() if t.price > 0
            }
            if price_data:
                await self._emit(ProbeEvent(
                    event_type=EventType.PRICE_UPDATE,
                    probe_id="genesis",
                    data={"prices": price_data, "tick": self.tick_count},
                ))

        # Tick each probe — collect only death events (reproduction is interval-based now)
        dying: list[Probe] = []

        for probe in live:
            events = probe.tick()
            for evt in events:
                await self._emit(evt)
                if evt.event_type == EventType.PROBE_DYING:
                    dying.append(probe)
                # NOTE: PROBE_REPRODUCING from probe.tick() is now ignored here.
                # Reproduction is handled by _evaluate_reproduction() at intervals.

        # Process death events
        for probe in dying:
            await self._handle_die(probe)

        # Max lifespan enforcement
        max_life = self.colony_config.max_lifespan_ticks
        if max_life:
            for probe in list(self.probes.values()):
                if probe.state in (ProbeState.OBSERVING, ProbeState.TRADING):
                    age = self.tick_count - probe.birth_tick
                    if age >= max_life:
                        events = probe._trigger_die("max_lifespan")
                        for evt in events:
                            await self._emit(evt)
                        await self._handle_die(probe)

        # Fitness-ranked reproduction at intervals
        if self.tick_count % self.reproduction_interval == 0:
            await self._evaluate_reproduction()

        # Batched probe updates every 10 ticks, system status every 5
        if self.tick_count % 5 == 0:
            await self._emit(ProbeEvent(
                event_type=EventType.SIMULATION_STATUS,
                probe_id="genesis",
                data=self.status(),
            ))
        if self.tick_count % 10 == 0:
            for p in self.live_probes:
                await self._emit(ProbeEvent(
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
        total = self.active_capital + self.reserve_capital
        if self._initial_total_capital <= 0:
            return
        drop = (self._initial_total_capital - total) / self._initial_total_capital
        if drop >= self.circuit_breaker_drop_pct and not self.circuit_breaker_active:
            logger.critical(f"[Genesis] CIRCUIT BREAKER! Capital dropped {drop*100:.1f}%")
            self.circuit_breaker_active = True

    # ── Diversity ────────────────────────────────────────────────────────

    async def _check_diversity(self) -> None:
        live_genomes = [p.genome for p in self.live_probes]
        new_genomes = inject_diversity(
            live_genomes,
            self.current_generation,
            self.diversity_threshold,
            dead_probes=self.dead_probes if self.dead_probes else None,
            colony_config=self.colony_config,
        )
        for genome in new_genomes:
            if self.reserve_capital >= self.seed_capital:
                await self._spawn_probe(genome, self.seed_capital)

    # ── Fitness snapshots ────────────────────────────────────────────────

    async def _capture_fitness_snapshots(self) -> None:
        for probe in self.live_probes:
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
            )
            await self._emit(ProbeEvent(
                event_type=EventType.FITNESS_SNAPSHOT,
                probe_id=probe.probe_id,
                data={
                    "generation": snapshot.generation,
                    "tick": snapshot.tick,
                    "fitness_score": round(snapshot.fitness_score, 4),
                    "roi": round(snapshot.roi, 4),
                    "sharpe_ratio": round(snapshot.sharpe_ratio, 4),
                    "max_drawdown": round(snapshot.max_drawdown, 4),
                    "win_rate": round(snapshot.win_rate, 4),
                    "trade_count": snapshot.trade_count,
                    "current_capital": round(snapshot.current_capital, 4),
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
            event_type=EventType.GENERATION_COMPLETE,
            probe_id="genesis",
            data=stats,
        ))

    # ── Event emission ───────────────────────────────────────────────────

    async def _emit(self, event: ProbeEvent) -> None:
        if self._on_event:
            try:
                await self._on_event(event)
            except Exception as e:
                logger.error(f"[Genesis] Event handler error: {e}")

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
