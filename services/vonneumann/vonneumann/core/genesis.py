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
import uuid
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

from .colony_config import ColonyConfig
from .evolution import NUMERIC_GENES, mutate, population_diversity
from .genome import Genome, random_genome
from .names import generate_probe_name
from .probe import Probe
from .strategies.base import EvolutionStrategy
from .types import EventType, ProbeEvent, ProbeState, FitnessSnapshot
from ..market.feed import MarketFeed

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

        # Optional background volume-refresh task (for paper/live modes where
        # the feed supports periodic OHLCV volume refresh from a secondary source).
        self._volume_task: Optional[asyncio.Task] = None

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

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def live_probes(self) -> list[Probe]:
        return [p for p in self.probes.values() if p.state != ProbeState.DEAD]

    @property
    def active_capital(self) -> float:
        """Total portfolio value across all live probes (USDC + open positions)."""
        return sum(p.total_value for p in self.live_probes)

    def status(self) -> dict:
        live = self.live_probes
        open_positions = sum(len(probe.open_positions) for probe in self.probes.values())
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

    def set_lifecycle(self, status: str) -> None:
        self._lifecycle_status = status
        self._running = status in {"running", "paused"}
        self._paused = status == "paused"

    async def prepare(self) -> None:
        """Seed and persist the population before a supervised loop may start."""
        self.started_at = datetime.now(timezone.utc)
        logger.info(f"[Genesis] Starting in {self.mode} mode. Seeding {self.gen0_count} Gen-0 probes.")

        for _ in range(self.gen0_count):
            genome = random_genome(generation=0, colony_config=self.colony_config)
            if await self._spawn_probe(genome, self.seed_capital) is None:
                raise RuntimeError("Initial population could not be fully funded")
        if len(self.live_probes) != self.gen0_count:
            raise RuntimeError("Initial population is incomplete")

        # Backfill price history for paper mode
        if self.mode == "paper":
            await self._backfill_probes()

        # A successful start must have a usable feed for every selected asset.
        # History availability/freshness policy is a separate data-quality gate.
        assets = sorted({asset for probe in self.live_probes for asset in probe.genome.assets})
        ticks = await self.market_feed.get_ticks(assets)
        if not assets or any(asset not in ticks or not math.isfinite(ticks[asset].price)
                             or ticks[asset].price <= 0 for asset in assets):
            raise RuntimeError("Initial market prices unavailable")
        self._latest_prices = {asset: ticks[asset].price for asset in assets}

        # Initialize the strategy with live probes
        self.strategy.initialize(list(self.probes.values()), self.colony_config)

        self._initial_total_capital = self.active_capital + self.reserve_capital

    async def run(self) -> None:
        """Run only after the manager has durably marked preparation complete."""
        # Start background volume refresher if the feed supports it.
        if hasattr(self.market_feed, "refresh_volumes"):
            self._volume_task = asyncio.create_task(self._volume_refresh_loop())

        await self._tick_loop()

    async def _volume_refresh_loop(self) -> None:
        """Background task: periodically refresh volume data from secondary source."""
        while self._running:
            assets = sorted({asset for probe in self.live_probes for asset in probe.genome.assets})
            await self.market_feed.refresh_volumes(assets)
            await asyncio.sleep(30)

    async def _backfill_probes(self) -> None:
        if not hasattr(self.market_feed, 'backfill_probe'):
            return
        # Group probes by timeframe to minimize API calls
        timeframe_groups: dict[int, list[str]] = {}
        for probe in self.live_probes:
            tf = probe.genome.int_genes()["timeframe_minutes"]
            for asset in probe.genome.assets:
                timeframe_groups.setdefault(tf, [])
                if asset not in timeframe_groups[tf]:
                    timeframe_groups[tf].append(asset)

        all_history: dict[int, dict] = {}
        for tf, assets in timeframe_groups.items():
            logger.info(f"[Genesis] Backfilling {len(assets)} assets at {tf}m timeframe...")
            all_history[tf] = await self.market_feed.backfill_probe(assets, timeframe_minutes=tf, limit=100)

        for probe in self.live_probes:
            tf = probe.genome.int_genes()["timeframe_minutes"]
            history = all_history.get(tf, {})
            for asset in probe.genome.assets:
                for candle in history.get(asset, []):
                    probe.on_price_update(asset, candle["price"], candle["volume"])

    async def stop(self) -> None:
        self._running = False
        self._paused = False
        await self.cleanup()
        # Positions stay attached for reconciliation; stopping cannot fabricate a fill.
        logger.info("[Genesis] Stopped; retained position records for reconciliation.")

    async def cleanup(self) -> None:
        """Release feed resources without erasing probe/position state."""
        self._running = False
        if self._volume_task:
            if not self._volume_task.done():
                self._volume_task.cancel()
            try:
                await self._volume_task
            except (asyncio.CancelledError, Exception):
                pass
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
            self._check_volume_task()

    def _check_volume_task(self) -> None:
        if self._volume_task and self._volume_task.done():
            if self._volume_task.cancelled():
                raise RuntimeError("Volume refresh stopped unexpectedly")
            self._volume_task.result()

    async def quiesce(self) -> None:
        self._paused = True
        await self.wait_for_tick()

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

    # ── Probe retirement (strategy-driven) ───────────────────────────────

    async def _retire_probe(self, probe: Probe, reason: str = "evolution") -> float:
        """Close positions, transition to DEAD, archive. Returns reclaimed capital.
        Handles both TRADING and OBSERVING probes correctly."""
        # Close all open positions
        for asset in list(probe.open_positions.keys()):
            price = self._latest_prices.get(asset, 0)
            if price <= 0:
                buf = probe._price_buffer.get(asset, [])
                price = buf[-1] if buf else 0
            evt = probe._close_position(asset, price, "EVOLUTION")
            if evt:
                await self._emit(evt)

        # State transition depends on current state
        if probe.state == ProbeState.TRADING:
            probe._transition(ProbeState.REPRODUCING)
            await self._emit(ProbeEvent(
                event_type=EventType.PROBE_REPRODUCING,
                probe_id=probe.probe_id,
                data=probe.summary(),
            ))
            probe._transition(ProbeState.DEAD)
        elif probe.state == ProbeState.OBSERVING:
            probe._transition(ProbeState.DYING)
            probe.died_at = datetime.now(timezone.utc)
            probe.death_reason = reason
            await self._emit(ProbeEvent(
                event_type=EventType.PROBE_DYING,
                probe_id=probe.probe_id,
                data={"reason": reason, **probe.summary()},
            ))
            probe._transition(ProbeState.DEAD)
        else:
            probe.state = ProbeState.DEAD

        reclaimed = probe.capital
        self.reserve_capital += reclaimed

        gen = probe.genome.generation
        self._generation_reproduced[gen] = self._generation_reproduced.get(gen, 0) + 1
        self.dead_probes.append(probe)
        if probe.probe_id in self.probes:
            del self.probes[probe.probe_id]

        return reclaimed

    @staticmethod
    def _transfer_price_buffers(source: Probe, target: Probe) -> None:
        """Copy price/volume buffers from a retired probe to its offspring."""
        for asset in source.genome.assets:
            if asset in source._price_buffer:
                target._price_buffer[asset] = list(source._price_buffer[asset])
            if asset in source._volume_buffer:
                target._volume_buffer[asset] = list(source._volume_buffer[asset])

    # ── Lifecycle: Reproduction (strategy-delegated) ─────────────────────

    async def _evaluate_reproduction(self) -> None:
        """Delegate evolution to the strategy. Called every reproduction_interval ticks."""
        live = [p for p in self.probes.values()
                if p.state in (ProbeState.OBSERVING, ProbeState.TRADING)]
        if len(live) < 2:
            return

        result = self.strategy.evolve(live, self.dead_probes, self.colony_config)

        # 1. Retire probes: close positions, reclaim capital, archive
        total_reclaimed = 0.0
        retired_probes: dict[str, Probe] = {}
        for probe_id in result.retire_ids:
            probe = self.probes.get(probe_id)
            if not probe or probe.state == ProbeState.DEAD:
                continue
            retired_probes[probe_id] = probe
            reclaimed = await self._retire_probe(probe)
            total_reclaimed += reclaimed

        # 2. Spawn offspring with capital from retired probes
        if result.offspring:
            if result.retire_ids and total_reclaimed > 0:
                per_child = (total_reclaimed * self.capital_split) / len(result.offspring)
            else:
                per_child = self.seed_capital
            for i, genome in enumerate(result.offspring):
                # Set parent_ids from strategy's parent_map
                idx = str(i)
                if idx in result.parent_map:
                    genome.parent_ids = result.parent_map[idx]

                spawn_capital = min(per_child, self.reserve_capital)
                if spawn_capital < 1.0:
                    continue
                new_probe = await self._spawn_probe(genome, spawn_capital)

                # Transfer price buffers from retired parent to offspring
                if new_probe and genome.parent_ids:
                    parent_id = genome.parent_ids[0]
                    parent = retired_probes.get(parent_id)
                    if parent:
                        self._transfer_price_buffers(parent, new_probe)
                        if hasattr(self.strategy, 'remap_probe_id'):
                            self.strategy.remap_probe_id(parent_id, new_probe.probe_id)

        # 3. Check diversity
        await self._check_diversity()
        # 4. Generation stats
        for probe_id in result.retire_ids:
            probe = retired_probes.get(probe_id)
            if probe:
                await self._maybe_emit_generation_stats(probe.genome.generation)

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

        # Auto-spawn: use strategy's diversity injection
        live_count = len(self.live_probes)
        if live_count < self.gen0_count // 2 and self.reserve_capital >= self.seed_capital:
            logger.info("[Genesis] Population low -- spawning via strategy diversity injection")
            genomes = [p.genome for p in self.live_probes]
            new_genomes = self.strategy.inject_diversity(
                genomes, self.dead_probes, self.colony_config,
                current_generation=self.current_generation, count=1,
            )
            for g in new_genomes:
                await self._spawn_probe(g, self.seed_capital)

    async def _handle_self_reproduce(self, probe: Probe) -> None:
        """A probe hit its own reproduction target (ROI/$ threshold).

        Probe has already transitioned to REPRODUCING and closed its positions.
        We finalize the transition to DEAD, reclaim its capital, and spawn
        `child_count` mutated asexual clones so the lineage propagates.
        """
        if probe.state != ProbeState.REPRODUCING:
            return

        reclaimed = probe.capital
        probe._transition(ProbeState.DEAD)
        self.reserve_capital += reclaimed

        probe_gen = probe.genome.generation
        self._generation_reproduced[probe_gen] = self._generation_reproduced.get(probe_gen, 0) + 1
        self.dead_probes.append(probe)
        if probe.probe_id in self.probes:
            del self.probes[probe.probe_id]

        # Spawn mutated asexual children that inherit this probe's successful genome.
        if self.child_count > 0:
            per_child = (reclaimed * self.capital_split) / self.child_count
            if per_child < 1.0:
                per_child = min(self.seed_capital, self.reserve_capital)
            logger.info(
                f"[Genesis] Self-reproduce: {probe.probe_name} spawning "
                f"{self.child_count} children at ${per_child:.2f} each"
            )
            for _ in range(self.child_count):
                spawn_capital = min(per_child, self.reserve_capital)
                if spawn_capital < 1.0:
                    break
                child = Genome(
                    **{g: getattr(probe.genome, g) for g in NUMERIC_GENES},
                    assets=list(probe.genome.assets),
                    generation=probe.genome.generation + 1,
                    parent_ids=[probe.probe_id],
                )
                child = mutate(
                    child,
                    mutation_rate=self.mutation_rate,
                    colony_config=self.colony_config,
                )
                new_probe = await self._spawn_probe(child, spawn_capital)
                if new_probe:
                    self._transfer_price_buffers(probe, new_probe)
                    if hasattr(self.strategy, "remap_probe_id"):
                        self.strategy.remap_probe_id(probe.probe_id, new_probe.probe_id)

        await self._maybe_emit_generation_stats(probe_gen)

    # ── Tick loop ────────────────────────────────────────────────────────

    async def _tick_loop(self) -> None:
        interval = self.tick_interval_ms / 1000.0
        while self._running:
            # Background failures must reach the same terminal supervisor.
            self._check_volume_task()
            if self._paused:
                await asyncio.sleep(0.1)
                continue
            async with self._tick_lock:
                if not self._paused and self._running:
                    await self._tick_all()
            await asyncio.sleep(interval)

        logger.info("[Genesis] Tick loop stopped.")

    async def _tick_all(self) -> None:
        if self.circuit_breaker_active:
            raise RuntimeError("Circuit breaker stopped execution")

        live = [p for p in self.probes.values()
                if p.state in (ProbeState.OBSERVING, ProbeState.TRADING)]
        if not live:
            raise RuntimeError("No active probes remain")

        self.tick_count += 1

        # Fetch prices and push to all probes
        all_assets = list({a for p in live for a in p.genome.assets})
        ticks = await self.market_feed.get_ticks(all_assets)

        # Store latest prices for use during probe retirement
        for asset, tick in ticks.items():
            self._latest_prices[asset] = tick.price

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

        # Tick each probe — collect death and self-reproduce events
        dying: list[Probe] = []
        self_reproducing: list[Probe] = []

        for probe in live:
            events = probe.tick()
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
                        events = probe._trigger_die("max_lifespan")
                        for evt in events:
                            await self._emit(evt)
                        await self._handle_die(probe)

        # Strategy-driven reproduction at intervals
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
        genomes = [p.genome for p in self.live_probes]
        if len(genomes) < 2:
            return
        diversity = self.strategy.compute_diversity(genomes)
        if diversity < self.diversity_threshold:
            new_genomes = self.strategy.inject_diversity(
                genomes, self.dead_probes, self.colony_config,
                current_generation=self.current_generation, count=2,
            )
            for g in new_genomes:
                if self.reserve_capital >= self.seed_capital:
                    await self._spawn_probe(g, self.seed_capital)

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
