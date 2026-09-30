"""
Genetic Algorithm strategy — tournament selection, uniform crossover, Gaussian mutation.

Extracted from the original monolithic evolution.py.
"""

from __future__ import annotations

import random
from typing import Optional, TYPE_CHECKING

from ..evolution import NUMERIC_GENES, mutate
from ..gene_registry import GENE_REGISTRY
from ..genome import AVAILABLE_ASSETS, Genome
from .base import EvolutionResult, EvolutionStrategy

if TYPE_CHECKING:
    from ..colony_config import ColonyConfig
    from ..probe import Probe


class GeneticAlgorithmStrategy(EvolutionStrategy):
    supports_cohorts = True
    name = "genetic_algorithm"
    label = "Genetic Algorithm"
    description = (
        "Classic GA with tournament selection, uniform crossover, and Gaussian mutation."
    )

    def __init__(self) -> None:
        self.mutation_rate = 0.20
        self.mutation_strength = 0.15
        self.top_pct = 0.30
        self.child_count = 2
        self.min_trades = 3
        self.min_roi = 0.0

    def initialize(self, probes: list[Probe], colony_config: ColonyConfig) -> None:
        if colony_config.mutation_rate is not None:
            self.mutation_rate = colony_config.mutation_rate

    def evolve(
        self,
        probes: list[Probe],
        dead_probes: list[Probe],
        colony_config: ColonyConfig,
    ) -> EvolutionResult:
        parents = select_parents_by_fitness(
            probes, self.top_pct, self.min_trades, self.min_roi
        )
        if len(parents) < 2:
            return EvolutionResult(offspring=[], retire_ids=[])

        offspring: list[Genome] = []
        retire_ids: list[str] = []
        parent_map: dict[str, list[str]] = {}

        for parent in parents:
            mate_pool = [p for p in probes if p.probe_id != parent.probe_id]
            mate = tournament_select(mate_pool, k=3)

            children = reproduce(
                parent.genome,
                mate.genome if mate else None,
                self.child_count,
                self.mutation_rate,
                colony_config,
            )

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


# ══════════════════════════════════════════════════════════════════════════════
# GA OPERATORS (extracted from evolution.py)
# ══════════════════════════════════════════════════════════════════════════════


def select_parents_by_fitness(
    probes: list[Probe],
    top_pct: float = 0.30,
    min_trades: int = 3,
    min_roi: float = 0.0,
) -> list[Probe]:
    """Select top probes by fitness for reproduction."""
    eligible = [p for p in probes if p.num_trades >= min_trades and p.roi >= min_roi]
    if not eligible:
        return []
    ranked = sorted(eligible, key=lambda p: p.fitness, reverse=True)
    n = max(1, int(len(ranked) * top_pct))
    return ranked[:n]


def tournament_select(probes: list[Probe], k: int = 3) -> Optional[Probe]:
    """Tournament selection: pick k random probes, return the fittest."""
    if not probes:
        return None
    tournament = random.sample(probes, min(k, len(probes)))
    return max(tournament, key=lambda p: p.fitness)


def crossover(
    parent_a: Genome,
    parent_b: Genome,
    generation: int,
    colony_config: Optional[ColonyConfig] = None,
) -> tuple[Genome, Genome]:
    """Uniform crossover with asset merging."""
    child_a_genes: dict[str, float] = {}
    child_b_genes: dict[str, float] = {}

    for gene in NUMERIC_GENES:
        a_val = getattr(parent_a, gene)
        b_val = getattr(parent_b, gene)
        evolvable = colony_config.is_gene_evolvable(gene) if colony_config else True

        if evolvable and random.random() > 0.5:
            child_a_genes[gene] = a_val
            child_b_genes[gene] = b_val
        else:
            child_a_genes[gene] = a_val if not evolvable else b_val
            child_b_genes[gene] = a_val if not evolvable else a_val

    effective_assets = (
        colony_config.get_effective_assets() if colony_config else AVAILABLE_ASSETS
    )
    parent_assets = list(set(parent_a.assets + parent_b.assets))
    parent_assets = [a for a in parent_assets if a in effective_assets]
    if not parent_assets:
        parent_assets = effective_assets

    def pick_assets(n_gene: float) -> list[str]:
        n = max(1, min(len(parent_assets), int(round(n_gene))))
        return random.sample(parent_assets, min(n, len(parent_assets)))

    child_a = Genome(
        **child_a_genes,
        assets=pick_assets(child_a_genes["num_assets"]),
        generation=generation,
        parent_ids=[],
    )
    child_b = Genome(
        **child_b_genes,
        assets=pick_assets(child_b_genes["num_assets"]),
        generation=generation,
        parent_ids=[],
    )

    return child_a.validate(colony_config), child_b.validate(colony_config)


def reproduce(
    parent: Genome,
    mate: Optional[Genome],
    num_children: int = 2,
    mutation_rate: float = 0.20,
    colony_config: Optional[ColonyConfig] = None,
) -> list[Genome]:
    """Produce children via sexual (crossover+mutate) or asexual (clone+mutate).

    Uses the caller-provided mate (already selected via tournament) so that
    the genealogy recorded by the caller matches who actually bred. When no
    mate is available, falls back to asexual cloning.

    Both children from each crossover are kept and mutated independently to
    avoid wasting work.
    """
    generation = parent.generation + 1
    children: list[Genome] = []

    while len(children) < num_children:
        if mate is not None and random.random() > 0.3:
            child_a, child_b = crossover(parent, mate, generation, colony_config)
            child_a = mutate(child_a, mutation_rate, colony_config=colony_config)
            children.append(child_a)
            if len(children) < num_children:
                child_b = mutate(child_b, mutation_rate, colony_config=colony_config)
                children.append(child_b)
        else:
            child = Genome(
                **{g: getattr(parent, g) for g in NUMERIC_GENES},
                assets=list(parent.assets),
                generation=generation,
                parent_ids=[],
            )
            child = mutate(child, mutation_rate * 1.5, colony_config=colony_config)
            children.append(child)

    return children[:num_children]
