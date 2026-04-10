"""
Differential Evolution strategy — DE/rand/1/bin.

Each evolution step replaces the worst half of the population with
trial vectors generated via differential mutation + binomial crossover.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..gene_registry import GENE_REGISTRY
from ..genome import Genome
from .base import EvolutionResult, EvolutionStrategy

if TYPE_CHECKING:
    from ..colony_config import ColonyConfig
    from ..probe import Probe

NUMERIC_GENES = GENE_REGISTRY.numeric_gene_names()


class DifferentialEvolutionStrategy(EvolutionStrategy):
    name = "differential_evolution"
    label = "Differential Evolution"
    description = "DE/rand/1/bin -- differential mutation with binomial crossover."

    def __init__(self) -> None:
        self.F = 0.8  # Differential weight (scaling factor)
        self.CR = 0.9  # Crossover probability
        self.min_pop = 4  # Minimum population for DE to operate

    def initialize(self, probes: list[Probe], colony_config: ColonyConfig) -> None:
        pass

    def evolve(
        self,
        probes: list[Probe],
        dead_probes: list[Probe],
        colony_config: ColonyConfig,
    ) -> EvolutionResult:
        if len(probes) < self.min_pop:
            return EvolutionResult(offspring=[], retire_ids=[])

        offspring: list[Genome] = []
        retire_ids: list[str] = []
        parent_map: dict[str, list[str]] = {}
        sorted_probes = sorted(probes, key=lambda p: p.fitness)

        # Replace the worst half with trial vectors
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
    target: Genome,
    a: Genome,
    b: Genome,
    c: Genome,
    F: float,
    CR: float,
    colony_config: ColonyConfig,
) -> Genome:
    """DE/rand/1/bin: mutant = a + F*(b - c), binomial crossover with target."""
    j_rand = random.randint(0, len(NUMERIC_GENES) - 1)
    new_genes: dict[str, float] = {}
    for i, name in enumerate(NUMERIC_GENES):
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
    genome.assets = list(target.assets)
    genome.validate(colony_config)
    return genome
