# Von Neumann: Multi-Strategy & Multi-Colony Refactor

## Overview

This document describes a refactor of the Von Neumann evolutionary trading probe system to support:

1. **Multiple EA strategies** (GA, DE, PSO, CMA-ES) via a Strategy Pattern with auto-discovery
2. **Multiple simultaneous colonies**, each with independent strategy, config, market feed, and lifecycle
3. **Easy extensibility** -- adding a new algorithm = one new file, zero registration boilerplate

---

## 1. File Structure

```
vonneumann/core/
    strategies/                        # NEW directory
        __init__.py                    # Auto-discovery registry
        base.py                        # EvolutionStrategy ABC + EvolutionResult
        genetic_algorithm.py           # GA operators extracted from evolution.py
        differential_evolution.py      # DE strategy
        particle_swarm.py              # PSO strategy
        cma_es.py                      # CMA-ES strategy (uses `cmaes` pip package)
    colony_manager.py                  # NEW: manages multiple concurrent colonies
    evolution.py                       # MODIFIED: keep fitness/diversity/mutate utilities,
                                       #   remove GA selection/crossover/reproduce operators
    genesis.py                         # MODIFIED: accept strategy, delegate evolution,
                                       #   add _retire_probe(), _latest_prices, price buffer transfer
    types.py                           # MODIFIED: add colony_id to ProbeEvent.to_ws_message()
    colony_config.py                   # MODIFIED: add mutation_rate field
    gene_registry.py                   # UNCHANGED
    genome.py                          # UNCHANGED
    names.py                           # UNCHANGED
    probe.py                           # UNCHANGED

vonneumann/server/
    app.py                             # MODIFIED: replace _genesis singleton with ColonyManager,
                                       #   add /colonies/ endpoints, keep backward-compat shims,
                                       #   update WS handler for multi-colony commands,
                                       #   fix reproduction_interval preset override bug
    websocket.py                       # UNCHANGED (broadcast is colony-agnostic)

vonneumann/db/
    repository.py                      # MODIFIED: add colony metadata persistence
    connection.py                      # UNCHANGED

vonneumann/market/
    feed.py                            # UNCHANGED
    sim_feed.py                        # UNCHANGED

requirements.txt                       # MODIFIED: add `cmaes>=0.11.0`

src/lib/probes/
    types.ts                           # MODIFIED: add colony_id, strategy fields, ColonyInfo type
    colony-config.ts                   # MODIFIED: add strategy to StartConfig
    websocket.ts                       # UNCHANGED
    constants.ts                       # MODIFIED: add STRATEGY_LABELS, STRATEGY_DESCRIPTIONS
    probes-supabase.ts                 # MODIFIED: add fetchColonies(), rewrite fetchColonyRuns()

src/components/probes/
    ColonyConfigDialog.tsx             # MODIFIED: add strategy selector dropdown
    SimulationControls.tsx             # MODIFIED: show strategy badge, support multi-colony
    ColonySelector.tsx                 # MODIFIED: show live colonies alongside historical runs
    ProbesDashboard.tsx                # MODIFIED: pass strategy + activeColonies props through

src/app/(dashboard)/probes/page.tsx    # MODIFIED: multi-colony state, colony_id WS filtering,
                                       #   send strategy in handleStart POST body
```

**Summary:** 5 new files, 14 modified files, 0 deleted files.

---

## 2. Strategy Interface

### `core/strategies/base.py`

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..colony_config import ColonyConfig
    from ..genome import Genome
    from ..probe import Probe


@dataclass
class EvolutionResult:
    """Outcome of one evolution step."""
    offspring: list[Genome]          # New genomes to spawn as probes
    retire_ids: list[str]            # Probe IDs to archive (parents consumed by reproduction)
    parent_map: dict[str, list[str]] = field(default_factory=dict)
        # Maps offspring index -> [parent_probe_ids] for genealogy tracking.
        # Key is str(index) into offspring list. Genesis uses this to set
        # genome.parent_ids on each child before spawning.
    metadata: dict = field(default_factory=dict)  # Strategy-specific stats for logging


class EvolutionStrategy(ABC):
    """
    Base class for evolutionary algorithm strategies.

    To add a new strategy:
      1. Create a file in core/strategies/
      2. Subclass EvolutionStrategy
      3. Implement name, label, initialize, evolve
      4. Done. Auto-discovery handles the rest.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique snake_case identifier (e.g. 'genetic_algorithm').
        Used as the strategy key in API payloads and DB records."""

    @property
    @abstractmethod
    def label(self) -> str:
        """Human-readable display name (e.g. 'Genetic Algorithm')."""

    @property
    def description(self) -> str:
        """Optional one-line description shown in the frontend strategy picker."""
        return ""

    @abstractmethod
    def initialize(
        self,
        probes: list[Probe],
        colony_config: ColonyConfig,
    ) -> None:
        """Called once after Gen-0 probes are spawned and before the tick loop starts.
        Receives actual Probe objects (not just genomes) so strategies can store
        probe_ids for internal state tracking (e.g. PSO velocities keyed by probe_id).
        """

    @abstractmethod
    def evolve(
        self,
        probes: list[Probe],
        dead_probes: list[Probe],
        colony_config: ColonyConfig,
    ) -> EvolutionResult:
        """Called every reproduction_interval ticks by GenesisController.
        Given the live population and graveyard, decide:
          - Which probes to retire (their capital returns to reserve)
          - What new genomes to create (spawned with allocated capital)
        The strategy MUST NOT mutate probe state directly."""

    def compute_diversity(self, genomes: list[Genome]) -> float:
        """Population diversity metric (0.0 = identical, 1.0 = maximally diverse).
        Default: average pairwise normalized Euclidean distance in gene space.
        Override if the strategy has a more meaningful diversity measure."""
        from ..evolution import population_diversity
        return population_diversity(genomes)

    def inject_diversity(
        self,
        genomes: list[Genome],
        dead_probes: list[Probe],
        colony_config: ColonyConfig,
        current_generation: int,
        count: int = 2,
    ) -> list[Genome]:
        """Create genomes for diversity injection when diversity drops below threshold.
        Default: strongly-mutated copies of the best dead probe, or random Gen-0.
        Override for strategy-specific diversity mechanisms."""
        from ..evolution import inject_diversity_genomes
        return inject_diversity_genomes(
            genomes, current_generation, dead_probes, colony_config, count
        )

    def to_dict(self) -> dict:
        """Serializable representation for the /strategies API."""
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
        }
```

### Key design decisions

- **`initialize()` receives `list[Probe]`, not `list[Genome]`.** PSO needs probe_ids to key velocity vectors. Passing probes avoids the placeholder-ID problem where initialize stores state under fake keys that never match real probe IDs.
- **`EvolutionResult.parent_map` tracks genealogy.** Strategies know which parents produced which offspring. Genesis reads this to set `genome.parent_ids` before spawning, preserving the frontend genealogy tree.
- **`inject_diversity()` takes `current_generation`.** Without it, injected genomes default to generation=0, corrupting generation tracking.
- **`evolve()` is the single integration point.** Genesis calls it once per reproduction interval. The strategy returns a declarative result (retire these probes, spawn these genomes). Genesis handles all capital management, position closing, event emission, and probe lifecycle transitions.
- **`compute_diversity()` and `inject_diversity()` have defaults.** A minimal strategy only needs `name`, `label`, `initialize`, and `evolve`. Four things to implement, zero boilerplate.
- **Strategy is stateful.** PSO needs velocity vectors, CMA-ES needs distribution params. The strategy instance lives for the lifetime of its colony.
- **Strategy never touches capital or probe state.** Capital allocation and lifecycle transitions are colony-level concerns.

---

## 3. Auto-Discovery Registry

### `core/strategies/__init__.py`

```python
import importlib
import inspect
import logging
import pkgutil
from pathlib import Path

from .base import EvolutionStrategy, EvolutionResult

_registry: dict[str, type[EvolutionStrategy]] = {}
_metadata_cache: dict[str, dict] = {}  # Cached to_dict() results to avoid repeat instantiation
_discovered = False

def _discover() -> None:
    """Scan this package for EvolutionStrategy subclasses. Called once on first access."""
    global _discovered
    if _discovered:
        return
    _discovered = True

    package_dir = Path(__file__).parent
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name == "base":
            continue
        try:
            module = importlib.import_module(f".{module_info.name}", __package__)
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, EvolutionStrategy)
                    and obj is not EvolutionStrategy
                    and not inspect.isabstract(obj)
                ):
                    instance = obj()
                    _registry[instance.name] = obj
                    _metadata_cache[instance.name] = instance.to_dict()
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to load strategy module: %s", module_info.name
            )

def get_strategy(name: str) -> EvolutionStrategy:
    """Instantiate a strategy by name. Raises KeyError if not found."""
    _discover()
    if name not in _registry:
        raise KeyError(
            f"Unknown strategy '{name}'. Available: {list(_registry.keys())}"
        )
    return _registry[name]()

def list_strategies() -> list[dict]:
    """Return metadata for all discovered strategies (cached, no extra instantiation)."""
    _discover()
    return list(_metadata_cache.values())
```

Strategy metadata is cached during `_discover()` so `list_strategies()` doesn't re-instantiate classes. CMA-ES imports `cmaes` at class-import time, so avoiding extra instantiation saves startup cost.

**Adding a new strategy:** Drop a file in `core/strategies/`, subclass `EvolutionStrategy`, implement the four required methods. `_discover()` picks it up automatically via `pkgutil.iter_modules`. No imports, no registration calls, no touching any other file.

---

## 4. Strategy Implementations

### 4a. Genetic Algorithm (`strategies/genetic_algorithm.py`)

Extracted from the current `evolution.py`. These GA-specific operators move here:
- `select_parents_by_fitness()`
- `tournament_select()`
- `crossover()`
- `reproduce()`

Note: `mutate()` stays in `evolution.py` because it is also used by `inject_diversity_genomes()` and genesis auto-spawn logic.

```python
from ..evolution import mutate  # mutate is a shared utility, stays in evolution.py

class GeneticAlgorithmStrategy(EvolutionStrategy):
    name = "genetic_algorithm"
    label = "Genetic Algorithm"
    description = "Classic GA with tournament selection, uniform crossover, and Gaussian mutation."

    def __init__(self):
        self.mutation_rate = 0.20      # Overridden by ColonyConfig.mutation_rate if set
        self.mutation_strength = 0.15
        self.top_pct = 0.30
        self.child_count = 2
        self.min_trades = 3
        self.min_roi = 0.0

    def initialize(self, probes, colony_config):
        # Read mutation_rate from colony config if provided
        if colony_config.mutation_rate is not None:
            self.mutation_rate = colony_config.mutation_rate

    def evolve(self, probes, dead_probes, colony_config):
        parents = select_parents_by_fitness(
            probes, self.top_pct, self.min_trades, self.min_roi
        )
        if len(parents) < 2:
            return EvolutionResult(offspring=[], retire_ids=[])

        offspring = []
        retire_ids = []
        parent_map = {}

        for parent in parents:
            if parent.roi < parent.genome.benchmark_target_pct:
                continue

            # Exclude parent from mate pool (current code does this)
            mate_pool = [p for p in probes if p.probe_id != parent.probe_id]
            mate = tournament_select(mate_pool, k=3)
            mate_genomes = [p.genome for p in mate_pool]

            children = reproduce(
                parent.genome, mate_genomes,
                self.child_count, self.mutation_rate, colony_config
            )

            # Track parent lineage for each child
            for child in children:
                idx = str(len(offspring))
                parent_ids = [parent.probe_id]
                if mate:
                    parent_ids.append(mate.probe_id)
                parent_map[idx] = parent_ids
                offspring.append(child)

            retire_ids.append(parent.probe_id)

        return EvolutionResult(
            offspring=offspring,
            retire_ids=retire_ids,
            parent_map=parent_map,
            metadata={"parents_selected": len(retire_ids)},
        )
```

### 4b. Differential Evolution (`strategies/differential_evolution.py`)

```python
import random
from ..gene_registry import GENE_REGISTRY
from ..genome import Genome

class DifferentialEvolutionStrategy(EvolutionStrategy):
    name = "differential_evolution"
    label = "Differential Evolution"
    description = "DE/rand/1/bin -- differential mutation with binomial crossover."

    def __init__(self):
        self.F = 0.8           # Differential weight (scaling factor)
        self.CR = 0.9          # Crossover probability
        self.min_pop = 4       # Minimum population for DE to operate

    def initialize(self, probes, colony_config):
        pass

    def evolve(self, probes, dead_probes, colony_config):
        if len(probes) < self.min_pop:
            return EvolutionResult(offspring=[], retire_ids=[])

        offspring = []
        retire_ids = []
        parent_map = {}
        sorted_probes = sorted(probes, key=lambda p: p.fitness)

        # Attempt trial vectors for the worst half of the population
        candidates = sorted_probes[: len(sorted_probes) // 2]
        for target in candidates:
            pool = [p for p in probes if p.probe_id != target.probe_id]
            if len(pool) < 3:
                continue
            a, b, c = random.sample(pool, 3)
            trial = _de_trial(
                target.genome, a.genome, b.genome, c.genome,
                self.F, self.CR, colony_config,
            )
            idx = str(len(offspring))
            parent_map[idx] = [target.probe_id, a.probe_id]
            offspring.append(trial)
            retire_ids.append(target.probe_id)

        return EvolutionResult(
            offspring=offspring,
            retire_ids=retire_ids,
            parent_map=parent_map,
            metadata={"trials_generated": len(offspring)},
        )


def _de_trial(
    target: Genome, a: Genome, b: Genome, c: Genome,
    F: float, CR: float, colony_config,
) -> Genome:
    """DE/rand/1/bin: mutant = a + F*(b - c), binomial crossover with target."""
    gene_names = GENE_REGISTRY.numeric_gene_names()
    j_rand = random.randint(0, len(gene_names) - 1)
    new_genes = {}
    for i, name in enumerate(gene_names):
        if not colony_config.is_gene_evolvable(name):
            new_genes[name] = getattr(target, name)
            continue
        if random.random() < CR or i == j_rand:
            mutant = getattr(a, name) + F * (getattr(b, name) - getattr(c, name))
            new_genes[name] = mutant
        else:
            new_genes[name] = getattr(target, name)
    new_genes["generation"] = target.generation + 1
    genome = Genome.from_dict(new_genes)
    genome.validate(colony_config)
    return genome
```

### 4c. Particle Swarm Optimization (`strategies/particle_swarm.py`)

```python
import random
from ..gene_registry import GENE_REGISTRY
from ..genome import Genome

class ParticleSwarmStrategy(EvolutionStrategy):
    name = "particle_swarm"
    label = "Particle Swarm Optimization"
    description = "PSO with inertia weight, cognitive and social components."

    def __init__(self):
        self.w = 0.7           # Inertia weight
        self.c1 = 1.5          # Cognitive coefficient (personal best attraction)
        self.c2 = 1.5          # Social coefficient (global best attraction)
        # Strategy-internal state
        self._velocities: dict[str, dict[str, float]] = {}   # probe_id -> {gene: velocity}
        self._personal_best: dict[str, tuple[dict, float]] = {}  # probe_id -> (genome_dict, fitness)
        self._global_best: tuple[dict, float] | None = None

    def initialize(self, probes, colony_config):
        """Initialize zero velocities keyed by actual probe IDs."""
        gene_names = GENE_REGISTRY.numeric_gene_names()
        for probe in probes:
            self._velocities[probe.probe_id] = {name: 0.0 for name in gene_names}
            # Set initial personal best to current genome
            self._personal_best[probe.probe_id] = (probe.genome.to_dict(), probe.fitness)

    def evolve(self, probes, dead_probes, colony_config):
        # Update personal and global bests
        for p in probes:
            pid = p.probe_id
            if pid not in self._personal_best or p.fitness > self._personal_best[pid][1]:
                self._personal_best[pid] = (p.genome.to_dict(), p.fitness)
            if self._global_best is None or p.fitness > self._global_best[1]:
                self._global_best = (p.genome.to_dict(), p.fitness)

        # Update velocities and positions for all particles
        offspring = []
        retire_ids = []
        parent_map = {}
        gene_names = GENE_REGISTRY.numeric_gene_names()

        for probe in probes:
            pid = probe.probe_id
            if pid not in self._velocities:
                self._velocities[pid] = {name: 0.0 for name in gene_names}

            velocity = self._velocities[pid]
            pb = self._personal_best[pid][0]
            gb = self._global_best[0]
            current = probe.genome.to_dict()

            new_genes = {}
            new_velocity = {}
            for gene in gene_names:
                if not colony_config.is_gene_evolvable(gene):
                    new_genes[gene] = current[gene]
                    new_velocity[gene] = 0.0
                    continue
                r1, r2 = random.random(), random.random()
                v = (self.w * velocity[gene]
                     + self.c1 * r1 * (pb[gene] - current[gene])
                     + self.c2 * r2 * (gb[gene] - current[gene]))
                new_velocity[gene] = v
                new_genes[gene] = current[gene] + v

            new_genome = Genome.from_dict({**new_genes, "generation": probe.genome.generation + 1})
            new_genome.validate(colony_config)

            # Store velocity under SAME key — genesis will transfer it to the new probe
            # via _transfer_velocity_key() callback after spawning
            self._velocities[pid] = new_velocity

            idx = str(len(offspring))
            parent_map[idx] = [pid]
            offspring.append(new_genome)
            retire_ids.append(pid)

        return EvolutionResult(
            offspring=offspring,
            retire_ids=retire_ids,
            parent_map=parent_map,
            metadata={"global_best_fitness": self._global_best[1] if self._global_best else 0},
        )

    def remap_probe_id(self, old_id: str, new_id: str) -> None:
        """Called by genesis after spawning an offspring that replaces a retired probe.
        Transfers velocity and personal-best state from the old probe ID to the new one."""
        if old_id in self._velocities:
            self._velocities[new_id] = self._velocities.pop(old_id)
        if old_id in self._personal_best:
            self._personal_best[new_id] = self._personal_best.pop(old_id)
```

PSO "moves" every particle to a new position each evolution step. This maps to retire-old-probe + spawn-new-probe-at-updated-position. The `remap_probe_id()` method lets genesis inform the strategy of the old→new probe ID mapping so velocity state carries over.

### 4d. CMA-ES (`strategies/cma_es.py`)

Uses the `cmaes` pip package (ask-and-tell interface), which fits perfectly because GenesisController already owns the evaluation loop.

```python
import numpy as np
import cmaes as cmaes_lib

from ..gene_registry import GENE_REGISTRY
from ..genome import Genome

class CMAEvolutionStrategy(EvolutionStrategy):
    name = "cma_es"
    label = "CMA-ES"
    description = "Covariance Matrix Adaptation Evolution Strategy. Best for continuous optimization in <100 dimensions."

    def __init__(self):
        self._optimizer: cmaes_lib.CMA | None = None
        self._gene_names: list[str] = []
        self._first_generation: bool = True  # Skip tell() on first evolve() call

    def initialize(self, probes, colony_config):
        self._gene_names = [
            g for g in GENE_REGISTRY.numeric_gene_names()
            if colony_config.is_gene_evolvable(g)
        ]
        if not self._gene_names or not probes:
            return

        genomes = [p.genome for p in probes]

        # Compute initial mean from the population centroid
        mean = np.array([
            np.mean([getattr(g, name) for g in genomes])
            for name in self._gene_names
        ])
        bounds = np.array([
            list(colony_config.get_effective_range(name)[:2])
            for name in self._gene_names
        ])
        sigma = float(np.mean(bounds[:, 1] - bounds[:, 0]) * 0.3)

        self._optimizer = cmaes_lib.CMA(
            mean=mean,
            sigma=sigma,
            bounds=bounds,
            population_size=len(genomes),
        )

    def evolve(self, probes, dead_probes, colony_config):
        if self._optimizer is None:
            return EvolutionResult(offspring=[], retire_ids=[])

        # Tell: feed fitness of current population to CMA-ES
        # Skip on first call — optimizer hasn't ask()'d yet, so there are no
        # solutions to tell() about. Gen-0 probes were random, not from ask().
        if not self._first_generation:
            solutions = []
            for probe in probes:
                params = np.array([
                    getattr(probe.genome, name) for name in self._gene_names
                ])
                solutions.append((params, -probe.fitness))  # CMA-ES minimizes; negate
            self._optimizer.tell(solutions)  # Single call with full list
        self._first_generation = False

        # Ask: sample new candidate solutions
        offspring = []
        best = max(probes, key=lambda p: p.fitness)
        for _ in range(len(probes)):
            params = self._optimizer.ask()
            genome_dict = {}
            for i, name in enumerate(self._gene_names):
                genome_dict[name] = float(params[i])
            # Fill non-evolvable genes from the best current probe
            for name in GENE_REGISTRY.numeric_gene_names():
                if name not in genome_dict:
                    genome_dict[name] = getattr(best.genome, name)
            genome_dict["generation"] = best.genome.generation + 1
            new_genome = Genome.from_dict(genome_dict)
            new_genome.validate(colony_config)
            offspring.append(new_genome)

        retire_ids = [p.probe_id for p in probes]

        return EvolutionResult(
            offspring=offspring,
            retire_ids=retire_ids,
            metadata={"cma_generation": self._optimizer.generation},
        )
```

CMA-ES replaces the entire population each step. The `_first_generation` flag ensures `tell()` is skipped on the first call (Gen-0 probes were not produced by `ask()`, so the optimizer has no matching solutions to receive feedback for). On subsequent calls, `tell()` is called once with the full solutions list, then `ask()` samples the next generation.

---

## 5. Changes to `evolution.py`

`evolution.py` is **not deleted**. It becomes a shared utility module.

**Keep (unchanged):**
- `compute_fitness()` -- imported by `probe.py`
- `compute_sharpe()` -- imported by `probe.py`
- `genome_distance()` -- used by diversity calculations
- `population_diversity()` -- used by default `compute_diversity()` in base strategy
- `mutate()` -- **stays here** (shared by GA strategy, `inject_diversity_genomes()`, and genesis auto-spawn)

**Move to `strategies/genetic_algorithm.py`:**
- `select_parents_by_fitness()`
- `tournament_select()`
- `crossover()`
- `reproduce()`

**Refactor `inject_diversity()` into `inject_diversity_genomes()`:**
Extract the genome-creation logic. Add `current_generation` parameter so injected genomes get the correct generation number. The diversity-threshold check moves to the caller (genesis).

```python
# evolution.py -- after refactor

def compute_fitness(roi, sharpe, max_drawdown, num_trades, win_rate) -> float: ...  # unchanged
def compute_sharpe(returns, risk_free=0.0) -> float: ...                           # unchanged
def genome_distance(a: Genome, b: Genome) -> float: ...                            # unchanged
def population_diversity(genomes: list[Genome]) -> float: ...                      # unchanged
def mutate(genome, mutation_rate=0.20, mutation_strength=0.15, colony_config=None) -> Genome: ...  # unchanged

def inject_diversity_genomes(
    genomes: list[Genome],
    current_generation: int,
    dead_probes: Optional[list] = None,
    colony_config: Optional[ColonyConfig] = None,
    count: int = 2,
) -> list[Genome]:
    """Create `count` diversity-injection genomes.
    Prefers strongly-mutated copies of the best dead probe.
    Falls back to random Gen-0 genomes.
    Sets generation to current_generation on all produced genomes."""
    results = []
    for _ in range(count):
        if dead_probes:
            recent = dead_probes[-50:]
            best = max(recent, key=lambda p: p.fitness)
            genome = _clone_genome(best.genome, current_generation)
            genome = mutate(genome, mutation_rate=0.30, colony_config=colony_config)
        else:
            genome = random_genome(generation=current_generation, colony_config=colony_config)
        results.append(genome)
    return results
```

---

## 6. Changes to `ColonyConfig`

### Add `mutation_rate` field

The user's `mutation_rate` setting needs to reach strategies. Add it to `ColonyConfig` so strategies can read it during `initialize()`.

```python
@dataclass
class ColonyConfig:
    # ... existing fields ...
    mutation_rate: Optional[float] = None  # NEW -- None means "use strategy default"
```

This avoids a separate configuration channel. The strategy reads `colony_config.mutation_rate` in `initialize()` and falls back to its own default if `None`.

---

## 7. Changes to `GenesisController`

### Constructor

```python
class GenesisController:
    def __init__(
        self,
        market_feed: MarketFeed,
        strategy: EvolutionStrategy,    # NEW required parameter
        colony_id: str,                 # NEW -- replaces internally-generated run_id
        user_id: str,
        mode: str = "simulation",
        # ... existing params unchanged ...
        colony_config: ColonyConfig | None = None,
        on_event: Callable[[ProbeEvent], Awaitable[None]] | None = None,
    ):
        self.strategy = strategy
        self.colony_id = colony_id      # Used as run_id throughout
        self.run_id = colony_id         # Alias for backward compatibility
        self._latest_prices: dict[str, float] = {}  # NEW -- updated each tick
        # ... rest unchanged ...
```

### `start()`

After spawning Gen-0 probes, initialize the strategy with actual Probe objects:

```python
async def start(self):
    # ... spawn gen0 probes (unchanged) ...
    self.strategy.initialize(list(self.probes.values()), self.colony_config)
    # ... rest of start unchanged ...
```

### Price tracking in `_tick_all()`

Store latest prices each tick so `_retire_probe()` can access them:

```python
async def _tick_all(self):
    # ... existing code to fetch ticks ...
    ticks = await self.market_feed.get_ticks(all_assets)

    # NEW: store latest prices for use during retirement
    for asset, tick in ticks.items():
        self._latest_prices[asset] = tick.price

    # ... rest of _tick_all unchanged ...
```

### `_retire_probe()` -- New helper method

Replaces inline probe retirement logic. Handles the state-transition difference between TRADING and OBSERVING probes.

```python
async def _retire_probe(self, probe: Probe, reason: str = "evolution") -> float:
    """Close positions, transition to DEAD, archive. Returns reclaimed capital.
    Handles both TRADING and OBSERVING probes correctly."""
    reclaimed = 0.0

    # Close all open positions
    for asset in list(probe.open_positions.keys()):
        price = self._latest_prices.get(asset, 0)
        if price <= 0:
            # Fallback to probe's own price buffer
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
        # OBSERVING -> DYING -> DEAD (OBSERVING -> REPRODUCING is not valid)
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
        # Already DEAD or in an unexpected state -- just mark dead
        probe.state = ProbeState.DEAD

    reclaimed = probe.capital
    self.reserve_capital += reclaimed

    gen = probe.genome.generation
    self._generation_reproduced[gen] = self._generation_reproduced.get(gen, 0) + 1
    self.dead_probes.append(probe)
    if probe.probe_id in self.probes:
        del self.probes[probe.probe_id]

    return reclaimed
```

### `_evaluate_reproduction()` -- Delegate to strategy

Replace the current inline GA logic:

```python
async def _evaluate_reproduction(self) -> None:
    live = [p for p in self.probes.values()
            if p.state in (ProbeState.OBSERVING, ProbeState.TRADING)]
    if len(live) < 2:
        return

    result = self.strategy.evolve(live, self.dead_probes, self.colony_config)

    # 1. Retire probes: close positions, reclaim capital, archive
    total_reclaimed = 0.0
    retired_probes: dict[str, Probe] = {}  # old_id -> probe (for price buffer transfer)
    for probe_id in result.retire_ids:
        probe = self.probes.get(probe_id)
        if not probe or probe.state == ProbeState.DEAD:
            continue
        # Snapshot price buffers before retirement for transfer to offspring
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
                    # PSO: remap velocity state from old to new probe ID
                    if hasattr(self.strategy, 'remap_probe_id'):
                        self.strategy.remap_probe_id(parent_id, new_probe.probe_id)

    # 3. Check diversity
    await self._check_diversity()
    # 4. Generation stats
    for probe_id in result.retire_ids:
        probe = retired_probes.get(probe_id)
        if probe:
            await self._maybe_emit_generation_stats(probe.genome.generation)
```

### Price buffer transfer -- New helper

Solves the PSO/CMA-ES warmup problem. Offspring inherit their parent's price observation history so signal computation works immediately.

```python
def _transfer_price_buffers(self, source: Probe, target: Probe) -> None:
    """Copy price and volume buffers from a retired probe to its offspring.
    This avoids the warmup cost when strategies replace the entire population."""
    for asset in source.genome.assets:
        if asset in source._price_buffer:
            target._price_buffer[asset] = list(source._price_buffer[asset])
        if asset in source._volume_buffer:
            target._volume_buffer[asset] = list(source._volume_buffer[asset])
```

### `_check_diversity()` -- Delegate to strategy

```python
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
```

### `_handle_die()` -- Strategy-aware auto-spawn

Replace the inline `from .evolution import mutate` auto-spawn with strategy delegation:

```python
async def _handle_die(self, probe: Probe) -> None:
    reclaimed = probe.capital
    self.reserve_capital += reclaimed

    # ... existing generation tracking, archive logic unchanged ...

    # Auto-spawn: use strategy's inject_diversity instead of hardcoded mutate
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
```

### `status()` -- Add strategy name

```python
def status(self) -> dict:
    return {
        # ... existing fields ...
        "colony_id": self.colony_id,
        "strategy": self.strategy.name,
    }
```

---

## 8. ColonyManager

### `core/colony_manager.py`

```python
import asyncio
import logging
import uuid
from typing import Callable, Awaitable, Optional

from .colony_config import ColonyConfig
from .genesis import GenesisController
from .types import ProbeEvent
from ..market.feed import MarketFeed

logger = logging.getLogger(__name__)


class ColonyManager:
    """Manages multiple concurrent GenesisController instances."""

    def __init__(self):
        self._colonies: dict[str, GenesisController] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def create_colony(
        self,
        colony_id: str,
        user_id: str,
        mode: str,
        strategy_name: str,
        colony_config: ColonyConfig,
        on_event: Callable[[ProbeEvent], Awaitable[None]],
        *,
        max_probes: int = 50,
        gen0_count: int = 10,
        seed_capital: float = 100,
        max_capital: float = 10_000,
        tick_interval_ms: int = 1000,
        mutation_rate: float = 0.20,
    ) -> str:
        """Create and start a new colony. Returns colony_id."""
        from .strategies import get_strategy

        strategy = get_strategy(strategy_name)
        market_feed = self._create_feed(mode)

        # Store mutation_rate in colony_config so strategies can read it
        colony_config.mutation_rate = mutation_rate

        genesis = GenesisController(
            market_feed=market_feed,
            strategy=strategy,
            colony_id=colony_id,
            user_id=user_id,
            mode=mode,
            max_probes=max_probes,
            gen0_count=gen0_count,
            seed_capital=seed_capital,
            max_capital=max_capital,
            tick_interval_ms=tick_interval_ms,
            mutation_rate=mutation_rate,
            colony_config=colony_config,
            on_event=on_event,
        )

        self._colonies[colony_id] = genesis
        task = asyncio.create_task(genesis.start())
        self._tasks[colony_id] = task
        return colony_id

    async def stop_colony(self, colony_id: str) -> None:
        genesis = self._colonies.get(colony_id)
        if genesis:
            await genesis.stop()  # Use public API, not private _running
        task = self._tasks.pop(colony_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._colonies.pop(colony_id, None)

    async def pause_colony(self, colony_id: str) -> None:
        genesis = self._colonies.get(colony_id)
        if genesis:
            genesis.pause()  # Use public API

    async def resume_colony(self, colony_id: str) -> None:
        genesis = self._colonies.get(colony_id)
        if genesis:
            genesis.resume()  # Use public API

    def get_colony(self, colony_id: str) -> Optional[GenesisController]:
        return self._colonies.get(colony_id)

    def list_colonies(self) -> list[dict]:
        """Return status of all active colonies."""
        return [
            {**genesis.status(), "colony_id": cid}
            for cid, genesis in self._colonies.items()
        ]

    def latest_colony_id(self) -> Optional[str]:
        """Return the most recently created colony's ID, or None."""
        if self._colonies:
            return list(self._colonies.keys())[-1]
        return None

    def active_count(self) -> int:
        return len(self._colonies)

    async def shutdown(self) -> None:
        """Stop all colonies. Called on server shutdown."""
        for colony_id in list(self._colonies.keys()):
            await self.stop_colony(colony_id)

    def _create_feed(self, mode: str) -> MarketFeed:
        if mode == "simulation":
            from ..market.sim_feed import SimulationFeed
            return SimulationFeed()
        else:
            from ..market.jupiter_feed import JupiterFeed
            return JupiterFeed()
```

Each colony gets its own `SimulationFeed` instance (independent price paths), its own `GenesisController`, and runs as its own `asyncio.Task`. This is fully concurrent under the event loop -- no threads, no multiprocessing.

Key changes from v1:
- `stop_colony()` uses `await genesis.stop()` instead of directly setting `genesis._running = False`
- `pause_colony()` / `resume_colony()` use public `pause()` / `resume()` methods
- No separate `_metadata` dict -- genesis.status() already contains strategy/mode/user_id
- `latest_colony_id()` helper for backward-compat shims

---

## 9. API Endpoint Changes

### New Endpoints

```
GET    /api/v1/strategies                    # List available strategies
POST   /api/v1/colonies/                     # Create and start a colony
GET    /api/v1/colonies/                      # List all active colonies
GET    /api/v1/colonies/{colony_id}           # Get colony status
POST   /api/v1/colonies/{colony_id}/pause     # Pause colony
POST   /api/v1/colonies/{colony_id}/resume    # Resume colony
POST   /api/v1/colonies/{colony_id}/stop      # Stop colony
```

### Backward-Compatible Shims

These continue to work, targeting the most recently created colony:

```python
@app.post("/api/v1/simulation/start")
async def start_simulation(req: StartRequest, ...):
    colony_id = str(uuid.uuid4())
    colony_config = _build_colony_config(req)
    # Wire up dual handler (DB persistence + WS broadcast)
    repo = VonNeumannRepository(req.user_id, run_id=colony_id)
    persister = EventPersister(repo, mode=req.mode)
    async def dual_handler(event: ProbeEvent):
        await persister.handle(event)
        msg = event.to_ws_message()
        msg["colony_id"] = colony_id
        await ws_manager.broadcast(msg)
    await colony_manager.create_colony(
        colony_id=colony_id, strategy_name=req.strategy, on_event=dual_handler, ...
    )
    # Insert colony record for Supabase queries
    repo.insert_colony(colony_id, req.strategy, req.model_dump(), req.mode)
    return {"status": "started", "run_id": colony_id, "colony_id": colony_id, ...}

@app.post("/api/v1/simulation/stop")
async def stop_simulation(...):
    cid = colony_manager.latest_colony_id()
    if not cid:
        raise HTTPException(404, "No simulation running")
    await colony_manager.stop_colony(cid)
    return {"status": "stopped"}

# pause/resume — same pattern using latest_colony_id()
# GET /api/v1/status — returns latest colony's status
```

### Updated Request Model

```python
class StartRequest(BaseModel):
    user_id: str
    mode: str = "simulation"
    strategy: str = "genetic_algorithm"    # NEW
    preset: str | None = None
    colony_config: ColonyConfigModel | None = None
    max_probes: int = 50
    max_capital: float = 10_000
    seed_capital: float = 100
    gen0_count: int = 10
    tick_interval_ms: int = 1000
    mutation_rate: float = 0.20
```

### Fix: `_build_colony_config` reproduction_interval override bug

```python
def _build_colony_config(req: StartRequest) -> ColonyConfig:
    if req.preset and req.preset in PRESET_CONFIGS:
        config = ColonyConfig.from_dict(PRESET_CONFIGS[req.preset].to_dict())
    else:
        config = ColonyConfig()

    if req.colony_config:
        # ... existing overlay logic ...
        # FIX: only override reproduction_interval if explicitly provided
        if req.colony_config.reproduction_interval is not None:
            config.reproduction_interval = req.colony_config.reproduction_interval
    return config
```

The Pydantic model changes `reproduction_interval` from `int = 100` to `Optional[int] = None`:

```python
class ColonyConfigModel(BaseModel):
    # ... existing fields ...
    reproduction_interval: Optional[int] = None  # FIX: None means "keep preset default"
```

### Updated WebSocket Handler (multi-colony routing)

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "command":
                    action = msg.get("data", {}).get("action")
                    colony_id = msg.get("data", {}).get("colony_id")
                    # If no colony_id, target the latest colony
                    target = colony_id or colony_manager.latest_colony_id()
                    if not target:
                        continue
                    if action == "stop":
                        await colony_manager.stop_colony(target)
                    elif action == "pause":
                        await colony_manager.pause_colony(target)
                    elif action == "resume":
                        await colony_manager.resume_colony(target)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
```

### Server Module-Level Changes

```python
# app.py -- replace globals
# BEFORE:
_genesis: Optional[GenesisController] = None
_genesis_task: Optional[asyncio.Task] = None

# AFTER:
from ..core.colony_manager import ColonyManager
colony_manager = ColonyManager()
```

Lifespan shutdown calls `await colony_manager.shutdown()` instead of stopping a single genesis.

---

## 10. WebSocket Message Format Changes

### Current Format

```json
{
    "type": "probe_born",
    "timestamp": "2026-04-09T12:00:00Z",
    "data": { "probe_id": "abc-123", ... }
}
```

### New Format

```json
{
    "type": "probe_born",
    "timestamp": "2026-04-09T12:00:00Z",
    "colony_id": "col-789",
    "data": { "probe_id": "abc-123", ... }
}
```

The `colony_id` is injected by the event handler closure in `app.py` (not by `ProbeEvent.to_ws_message()`). This keeps `types.py` changes minimal:

```python
# types.py -- to_ws_message stays unchanged.
# colony_id is added by the event handler wrapper in app.py.
def to_ws_message(self) -> dict:
    return {
        "type": self.event_type.value,
        "timestamp": self.timestamp.isoformat(),
        "data": {"probe_id": self.probe_id, **self.data},
    }
```

The event handler in `app.py` injects it:
```python
def _make_dual_handler(colony_id, persister):
    async def handler(event: ProbeEvent):
        await persister.handle(event)
        msg = event.to_ws_message()
        msg["colony_id"] = colony_id
        await ws_manager.broadcast(msg)
    return handler
```

### WebSocket Command Extensions

```json
{
    "type": "command",
    "data": { "action": "pause", "colony_id": "col-789" }
}
```

If `colony_id` is omitted, the command applies to the most recently created colony.

---

## 11. Database Changes

### New Migration: `vn_colonies` Table

```sql
CREATE TABLE vn_colonies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    strategy TEXT NOT NULL DEFAULT 'genetic_algorithm',
    config JSONB NOT NULL DEFAULT '{}',
    mode TEXT NOT NULL DEFAULT 'simulation',
    status TEXT NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    stopped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_vn_colonies_user_id ON vn_colonies(user_id);
CREATE INDEX idx_vn_colonies_status ON vn_colonies(status);

ALTER TABLE vn_colonies ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own colonies" ON vn_colonies FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own colonies" ON vn_colonies FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own colonies" ON vn_colonies FOR UPDATE USING (auth.uid() = user_id);
```

The `vn_colonies.id` serves as the `run_id` across `vn_probes`, `vn_trades`, `vn_fitness_snapshots`, and `vn_generation_stats`. Existing `run_id` columns and indexes remain unchanged.

**Note:** No FK constraint is added from existing `run_id` columns to `vn_colonies.id`. Existing rows have `run_id` values from before this migration that have no matching colony record. Adding a FK would require either backfilling `vn_colonies` rows for all historical runs or accepting that old data would violate the constraint. We accept the soft reference and rely on application-level consistency.

### Repository Changes

Add to `VonNeumannRepository`:

```python
def insert_colony(self, colony_id: str, strategy: str, config: dict, mode: str) -> None:
    self.db.table("vn_colonies").insert({
        "id": colony_id,
        "user_id": self.user_id,
        "strategy": strategy,
        "config": config,
        "mode": mode,
    }).execute()

def update_colony_status(self, colony_id: str, status: str) -> None:
    fields = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if status == "stopped":
        fields["stopped_at"] = datetime.now(timezone.utc).isoformat()
    self.db.table("vn_colonies").update(fields).eq("id", colony_id).execute()
```

### `EventPersister` Changes

On `SIMULATION_STATUS` events with `status == "stopped"`, call `update_colony_status()`.

### Known Limitation: Synchronous DB Client

`VonNeumannRepository` uses the synchronous `supabase-py` client. Each DB write in `EventPersister.handle()` blocks the asyncio event loop briefly. With multiple colonies producing events concurrently, this may become a bottleneck. Mitigation options for a future iteration: (a) wrap DB calls in `asyncio.to_thread()`, (b) batch writes, or (c) switch to an async Supabase client.

---

## 12. Frontend Changes

### `types.ts` -- New/Modified Types

```typescript
// Add to WsMessage:
export interface WsMessage {
    type: string;
    timestamp: string;
    colony_id?: string;        // NEW
    data: Record<string, any>;
}

// Add to SystemStatus:
export interface SystemStatus {
    // ... existing fields ...
    colony_id?: string;         // NEW
    strategy?: string;          // NEW
}

// New type for active colonies (live, not just historical):
export interface ColonyInfo {
    colony_id: string;
    strategy: string;
    mode: string;
    status: SimulationStatus;
    generation: number;
    tick: number;
    live_probes: number;
    dead_probes: number;
    total_capital: number;
    diversity: number;
    started_at: string;
    uptime_secs: number;
}

// New type for strategy metadata:
export interface StrategyInfo {
    name: string;
    label: string;
    description: string;
}

// Add strategy to ColonyRun:
export interface ColonyRun {
    run_id: string;
    mode: string;
    strategy?: string;          // NEW
    started_at: string;
    ended_at: string | null;
    probe_count: number;
    best_fitness: number;
}
```

### `colony-config.ts` -- Add Strategy

```typescript
export interface StartConfig {
    mode: "simulation" | "paper";
    strategy: string;              // NEW -- default "genetic_algorithm"
    preset?: string;
    colony_config: ColonyConfig;
    gen0_count: number;
    max_capital: number;
    seed_capital: number;
    tick_interval_ms: number;
    mutation_rate: number;
    max_probes: number;
}

export function buildDefaultStartConfig(): StartConfig {
    return {
        mode: "simulation",
        strategy: "genetic_algorithm",     // NEW
        // ... rest unchanged ...
    };
}
```

### `constants.ts` -- Strategy Labels

```typescript
// These serve as fallbacks. The canonical list comes from GET /api/v1/strategies.
export const STRATEGY_LABELS: Record<string, string> = {
    genetic_algorithm: "Genetic Algorithm",
    differential_evolution: "Differential Evolution",
    particle_swarm: "Particle Swarm Optimization",
    cma_es: "CMA-ES",
};

export const STRATEGY_DESCRIPTIONS: Record<string, string> = {
    genetic_algorithm: "Classic GA with tournament selection, uniform crossover, and Gaussian mutation.",
    differential_evolution: "DE/rand/1/bin -- differential mutation with binomial crossover.",
    particle_swarm: "PSO with inertia weight, cognitive and social components.",
    cma_es: "Covariance Matrix Adaptation Evolution Strategy.",
};
```

### `probes-supabase.ts` -- Colony Queries

Rewrite `fetchColonyRuns()` to query `vn_colonies` directly (avoids the N+1 problem of the old approach that grouped probes client-side):

```typescript
export async function fetchColonyRuns(): Promise<ColonyRun[]> {
    // Single query against the new vn_colonies table
    const { data } = await supabase()
        .from("vn_colonies")
        .select("id, strategy, mode, status, started_at, stopped_at")
        .order("created_at", { ascending: false });

    if (!data) return [];

    // Batch-fetch probe counts and best fitness for all colonies at once
    const colonyIds = data.map((c: any) => c.id);
    const { data: probeStats } = await supabase()
        .from("vn_probes")
        .select("run_id, fitness_score")
        .in("run_id", colonyIds);

    // Aggregate client-side (2 queries total, not N+1)
    const statsMap = new Map<string, { count: number; best: number }>();
    for (const row of probeStats ?? []) {
        const existing = statsMap.get(row.run_id) ?? { count: 0, best: 0 };
        existing.count++;
        existing.best = Math.max(existing.best, row.fitness_score ?? 0);
        statsMap.set(row.run_id, existing);
    }

    return data.map((col: any) => {
        const stats = statsMap.get(col.id) ?? { count: 0, best: 0 };
        return {
            run_id: col.id,
            mode: col.mode,
            strategy: col.strategy,
            started_at: col.started_at,
            ended_at: col.stopped_at,
            probe_count: stats.count,
            best_fitness: stats.best,
        };
    });
}

export async function fetchActiveColonies(): Promise<ColonyInfo[]> {
    // Active colonies come from the REST API, not Supabase,
    // since they reflect in-memory state of the running service.
    // This is called via apiCall() in the page, not here.
    // This function exists for type completeness but the actual
    // data source is GET /api/v1/colonies/.
    return [];
}
```

### `ColonyConfigDialog.tsx` -- Strategy Selector

Add a strategy dropdown at the top of the dialog, before the mode selector:

```tsx
// New state:
const [strategies, setStrategies] = useState<StrategyInfo[]>([]);

// Fetch strategies on mount:
useEffect(() => {
    fetch(`${VN_API_URL}/api/v1/strategies`, { headers: { "x-api-key": VN_API_KEY } })
        .then(r => r.json())
        .then(setStrategies)
        .catch(() => {
            // Fallback to hardcoded labels if backend unreachable
            setStrategies(Object.entries(STRATEGY_LABELS).map(([name, label]) => ({
                name, label, description: STRATEGY_DESCRIPTIONS[name] ?? "",
            })));
        });
}, []);

// Render (before mode selector):
<div>
    <Label>Evolution Strategy</Label>
    <Select
        value={config.strategy}
        onValueChange={(v) => setConfig(c => ({ ...c, strategy: v }))}
    >
        {strategies.map(s => (
            <SelectItem key={s.name} value={s.name}>
                {s.label}
            </SelectItem>
        ))}
    </Select>
    <p className="text-xs text-muted-foreground mt-1">
        {strategies.find(s => s.name === config.strategy)?.description}
    </p>
</div>
```

### `SimulationControls.tsx` -- Strategy Badge

Add strategy display to the control bar:

```tsx
interface Props {
    // ... existing ...
    strategy?: string;                  // NEW
    activeColonies?: ColonyInfo[];      // NEW
}

// Render -- show strategy badge alongside mode badge:
{strategy && (
    <Badge variant="outline" className="ml-2 text-xs">
        {STRATEGY_LABELS[strategy] ?? strategy}
    </Badge>
)}

{activeColonies && activeColonies.length > 1 && (
    <Badge variant="secondary" className="ml-2">
        {activeColonies.length} colonies
    </Badge>
)}
```

### `ColonySelector.tsx` -- Live Colonies

```tsx
interface Props {
    runs: ColonyRun[];
    activeColonies: ColonyInfo[];       // NEW
    activeRunId: string | null;
    onSelectRun: (runId: string) => void;
}
```

Two sections: "Active Colonies" (live, with strategy badge and stats) and "History" (existing). Show the trigger whenever there are active colonies OR > 1 historical run.

### `ProbesDashboard.tsx` -- Pass-through props

Add `strategy` and `activeColonies` to the ProbesDashboard props interface so they flow from the page through to `SimulationControls` and `ColonySelector`:

```tsx
interface Props {
    // ... existing 16 props ...
    strategy?: string;              // NEW
    activeColonies: ColonyInfo[];   // NEW
}
```

### `page.tsx` -- Multi-Colony State

```tsx
// New state:
const [activeColonies, setActiveColonies] = useState<ColonyInfo[]>([]);
const [selectedColonyId, setSelectedColonyId] = useState<string | null>(null);

// WebSocket handler -- filter by colony:
const handleWsMessage = React.useCallback((msg: WsMessage) => {
    const colonyId = msg.colony_id;

    // Update activeColonies list from simulation_status events
    if (msg.type === "simulation_status") {
        setActiveColonies(prev => {
            const updated = prev.filter(c => c.colony_id !== colonyId);
            if (msg.data.status !== "stopped") {
                updated.push({
                    colony_id: colonyId!,
                    strategy: msg.data.strategy,
                    ...msg.data,
                } as ColonyInfo);
            }
            return updated;
        });
    }

    // Only process events for the currently selected colony
    if (selectedColonyId && colonyId && colonyId !== selectedColonyId) return;

    // ... existing message handling (probe_born, probe_update, etc.) unchanged ...
}, [selectedColonyId]);

// handleStart -- include strategy in POST body:
const handleStart = async (startConfig: StartConfig) => {
    // ...
    const result = await apiCall("/api/v1/simulation/start", "POST", {
        user_id: user.id,
        mode: startConfig.mode,
        strategy: startConfig.strategy,       // NEW -- was missing
        preset: startConfig.preset,
        colony_config: startConfig.colony_config,
        gen0_count: startConfig.gen0_count,
        max_capital: startConfig.max_capital,
        seed_capital: startConfig.seed_capital,
        tick_interval_ms: startConfig.tick_interval_ms,
        mutation_rate: startConfig.mutation_rate,
        max_probes: startConfig.max_probes,
    });
    const newRunId = result.run_id as string;
    setSelectedColonyId(newRunId);
    // ... rest unchanged ...
};

// Fetch active colonies periodically from REST API:
React.useEffect(() => {
    const fetchActive = async () => {
        try {
            const data = await apiCall("/api/v1/colonies/", "GET");
            setActiveColonies(data);
        } catch { /* backend offline */ }
    };
    fetchActive();
    const interval = setInterval(fetchActive, 10_000);
    return () => clearInterval(interval);
}, []);

// Colony switching:
const handleSelectColony = (colonyId: string) => {
    setSelectedColonyId(colonyId);
    setProbes([]);
    setPrices({});
    prevPrices.current = {};
    refreshFromSupabase(colonyId);
};

// Pass new props to ProbesDashboard:
<ProbesDashboard
    // ... existing props ...
    strategy={systemStatus?.strategy}
    activeColonies={activeColonies}
/>
```

---

## 13. Dependency Changes

### `requirements.txt`

```diff
+ cmaes>=0.11.0
```

**Why `cmaes` and not DEAP/PyGAD:**
- DEAP and PyGAD want to own the population loop (`algorithms.eaSimple`, `pygad.GA.run()`). GenesisController already owns the tick loop. Forcing an external EA library to run inside our loop would require fighting their API.
- The `cmaes` package uses an ask-and-tell interface: call `ask()` to get candidate solutions, evaluate them yourself, call `tell()` to feed back results. This fits perfectly -- genesis runs probes for N ticks, then asks the CMA-ES strategy for new candidates.
- GA, DE, and PSO are straightforward enough to implement with `random` and `math` (matching the existing hand-rolled style). CMA-ES requires covariance matrix math that's not worth reimplementing.

`numpy` is already in requirements.

---

## 14. Migration Path

### Phase 1: Backend Strategy + Multi-Colony
1. Add `cmaes` to `requirements.txt`
2. Add `mutation_rate` field to `ColonyConfig`
3. Create `core/strategies/` with base, GA, DE, PSO, CMA-ES
4. Refactor `evolution.py`: keep `compute_fitness`, `compute_sharpe`, `genome_distance`, `population_diversity`, `mutate`; move GA operators to `strategies/genetic_algorithm.py`; extract `inject_diversity_genomes()` from `inject_diversity()`
5. Modify `genesis.py`: add `strategy` + `colony_id` params, add `_retire_probe()`, `_transfer_price_buffers()`, `_latest_prices`; refactor `_evaluate_reproduction()`, `_check_diversity()`, `_handle_die()`
6. Create `colony_manager.py`
7. Add DB migration for `vn_colonies`
8. Update `repository.py` for colony persistence
9. Modify `app.py`: replace singleton with ColonyManager, add new endpoints, fix `_build_colony_config`, update WS handler

### Phase 2: Frontend Multi-Colony
1. Update `types.ts` with new types
2. Update `colony-config.ts` with strategy field
3. Update `constants.ts` with strategy labels
4. Rewrite `probes-supabase.ts` `fetchColonyRuns()` to use `vn_colonies`
5. Update `ColonyConfigDialog.tsx` with strategy selector
6. Update `SimulationControls.tsx` with strategy badge
7. Update `ColonySelector.tsx` for live colonies
8. Update `ProbesDashboard.tsx` props interface
9. Update `page.tsx` for multi-colony state, colony_id filtering, strategy in POST body

### Phase 3: Testing & Polish
1. Unit tests for all strategies
2. Integration tests for ColonyManager
3. API backward-compatibility tests
4. Frontend E2E tests

---

## 15. Testing Checklist

### Strategy Layer
- [ ] `EvolutionStrategy` ABC cannot be instantiated directly
- [ ] Auto-discovery finds all four built-in strategies
- [ ] `get_strategy("genetic_algorithm")` returns a `GeneticAlgorithmStrategy`
- [ ] `get_strategy("nonexistent")` raises `KeyError`
- [ ] `list_strategies()` returns cached metadata for all strategies (no double-instantiation)
- [ ] Adding a new `.py` file to `strategies/` with a valid subclass makes it discoverable
- [ ] A `.py` file with a broken import logs an error but doesn't crash discovery

### Genetic Algorithm Strategy
- [ ] `evolve()` returns offspring and retire_ids when population has qualifying parents
- [ ] `evolve()` returns empty result when population is too small or no parents qualify
- [ ] Offspring genomes pass `GENE_REGISTRY.validate_genome()`
- [ ] Fixed genes (via `ColonyConfig`) are not mutated or crossed over
- [ ] `parent_map` correctly maps offspring indices to parent probe IDs
- [ ] Tournament selection excludes the current parent from the mate pool
- [ ] `mutation_rate` from `ColonyConfig` overrides the strategy default
- [ ] End-to-end: GA strategy produces the same behavior as the pre-refactor code path

### Differential Evolution Strategy
- [ ] `evolve()` generates trial vectors via DE/rand/1/bin
- [ ] Trial vector genes respect effective bounds from `ColonyConfig`
- [ ] Minimum population guard (< 4 probes returns empty)
- [ ] Each trial excludes its target from the donor pool
- [ ] `parent_map` tracks target and primary donor for each trial

### Particle Swarm Strategy
- [ ] `initialize()` sets up zero velocities keyed by real probe IDs
- [ ] `evolve()` updates velocities using personal and global bests
- [ ] Gene values after position update are clamped to bounds via `validate()`
- [ ] Fixed genes have zero velocity and don't change
- [ ] Personal best and global best tracking works correctly
- [ ] `remap_probe_id()` correctly transfers velocity state from old to new probe ID

### CMA-ES Strategy
- [ ] `initialize()` creates CMA optimizer with correct mean, sigma, and bounds
- [ ] First `evolve()` call skips `tell()` and only `ask()`s
- [ ] Subsequent `evolve()` calls `tell(solutions)` with full list then `ask()`
- [ ] Sampled solutions respect gene bounds after `validate()`
- [ ] Non-evolvable genes are inherited from the best probe
- [ ] Missing `import numpy as np` is present

### GenesisController Changes
- [ ] Constructor accepts `strategy` and `colony_id` parameters
- [ ] `start()` calls `strategy.initialize()` with Probe objects (not genomes)
- [ ] `_retire_probe()` handles TRADING probes (REPRODUCING path)
- [ ] `_retire_probe()` handles OBSERVING probes (DYING path)
- [ ] `_retire_probe()` uses `_latest_prices` with fallback to probe price buffer
- [ ] `_evaluate_reproduction()` calls `strategy.evolve()` and handles results
- [ ] `_evaluate_reproduction()` sets `parent_ids` from `result.parent_map`
- [ ] `_evaluate_reproduction()` transfers price buffers from parent to offspring
- [ ] `_evaluate_reproduction()` calls `remap_probe_id()` for PSO strategy
- [ ] `_evaluate_reproduction()` skips already-DEAD probes in retire_ids
- [ ] `_check_diversity()` passes `current_generation` to `inject_diversity()`
- [ ] `_handle_die()` auto-spawn uses `strategy.inject_diversity()` instead of inline mutate
- [ ] Capital accounting: retired probe capital → reserve → offspring allocation (no double-counting)
- [ ] `status()` includes `colony_id` and `strategy`
- [ ] `_latest_prices` updated every tick

### ColonyManager
- [ ] `create_colony()` returns a valid colony_id and starts the colony
- [ ] Multiple colonies can run simultaneously (test with 3 colonies)
- [ ] `stop_colony()` calls `genesis.stop()` then cancels task cleanly
- [ ] `pause_colony()` / `resume_colony()` use public `pause()` / `resume()` methods
- [ ] `list_colonies()` returns status of all active colonies
- [ ] `latest_colony_id()` returns the most recent colony's ID
- [ ] `shutdown()` stops all colonies cleanly
- [ ] Each colony gets its own independent `SimulationFeed`
- [ ] Each colony gets its own `EventPersister` writing to the correct `run_id`

### API Endpoints
- [ ] `GET /api/v1/strategies` returns all discovered strategies
- [ ] `POST /api/v1/colonies/` creates and starts a colony with correct strategy
- [ ] `GET /api/v1/colonies/` lists active colonies
- [ ] `GET /api/v1/colonies/{id}` returns colony status
- [ ] `POST /api/v1/colonies/{id}/stop` stops colony
- [ ] `POST /api/v1/simulation/start` still works (backward compat), returns `colony_id`
- [ ] `POST /api/v1/simulation/stop` stops the latest colony
- [ ] `strategy` field defaults to `"genetic_algorithm"` when omitted
- [ ] `_build_colony_config` does NOT clobber preset's `reproduction_interval`
- [ ] 404 for unknown colony_id
- [ ] API key validation applies to all new endpoints

### WebSocket
- [ ] All broadcast messages include `colony_id`
- [ ] Messages from different colonies have different `colony_id` values
- [ ] Command messages with `colony_id` target the correct colony
- [ ] Command messages without `colony_id` target the latest colony
- [ ] WS handler routes through `colony_manager`, not a global singleton

### Database
- [ ] `vn_colonies` migration creates table with correct schema and RLS
- [ ] `insert_colony()` writes strategy and config
- [ ] `update_colony_status()` sets status and stopped_at
- [ ] Existing data (run_ids with no matching colony row) is unaffected
- [ ] `fetchColonyRuns()` queries `vn_colonies` with 2 total queries (not N+1)

### Frontend
- [ ] `ColonyConfigDialog` fetches strategies from API and renders dropdown
- [ ] Strategy fallback works when API is unreachable (hardcoded labels)
- [ ] Selecting a strategy updates the `StartConfig.strategy` field
- [ ] `handleStart` sends `strategy` in the POST body
- [ ] `SimulationControls` shows strategy badge for active colony
- [ ] `ColonySelector` shows active colonies with strategy labels
- [ ] `ProbesDashboard` receives and passes through `strategy` and `activeColonies` props
- [ ] Page filters WebSocket events by `selectedColonyId`
- [ ] Switching between active colonies clears and reloads probes
- [ ] Starting a second colony while one is running works
- [ ] Stopping one colony doesn't affect other running colonies

### Integration / End-to-End
- [ ] Start a GA colony, let it run for 200 ticks, verify probes evolve correctly
- [ ] Start a DE colony, verify trial vectors are generated and worst-half replaced
- [ ] Start a PSO colony, verify particles update positions and velocities carry over
- [ ] Start a CMA-ES colony, verify first evolve skips tell, subsequent calls work
- [ ] Run two colonies simultaneously with different strategies, verify independent operation
- [ ] Stop one colony, verify the other continues running
- [ ] Historical data from both colonies is queryable in Supabase via `vn_colonies`
- [ ] Frontend shows both colonies and can switch between them
- [ ] Price buffers transfer from parent to offspring (no warmup gaps)
- [ ] Genealogy tree renders correctly with parent_ids from strategy's parent_map
