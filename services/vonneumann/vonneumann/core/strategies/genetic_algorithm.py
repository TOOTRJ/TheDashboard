"""
Genetic Algorithm strategy — tournament selection, uniform crossover, Gaussian mutation.

Extracted from the original monolithic evolution.py.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Optional, TYPE_CHECKING

from ..evolution import NUMERIC_GENES, mutate
from ..genome import AVAILABLE_ASSETS, Genome
from ..search_random import private_rng
from .base import EvolutionResult, EvolutionStrategy
from .cohort_contract import SelectionCohort, preserve_fixed_controls

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
        super().__init__()
        self.mutation_rate = 0.20
        self.mutation_strength = 0.15
        self._cohort = SelectionCohort()

    def initialize(self, probes: list[Probe], colony_config: ColonyConfig) -> None:
        if len(probes) < 2:
            raise ValueError("Genetic Algorithm requires at least two evaluation accounts")
        self._cohort.initialize(probes)
        self.mutation_rate = (.20 if colony_config.mutation_rate is None
                              else colony_config.mutation_rate)

    def bind_candidates(self, probes: list[Probe]) -> None:
        self._cohort.bind(probes)

    def abort_cohort(self) -> None:
        self._cohort.abort()

    def evolve(
        self,
        probes: list[Probe],
        dead_probes: list[Probe],
        colony_config: ColonyConfig,
        *, period_operator: str | None = None,
    ) -> EvolutionResult:
        portable = None
        if period_operator is not None:
            if type(period_operator) is not str:
                raise ValueError('Explicit period operator must be a plain version string')
            from .. import integer_period_mutation as portable
            if period_operator != portable.VERSION:
                raise ValueError('Unknown explicit period mutation operator')
            portable.validate_context(self, colony_config)
        eligible = self._cohort.results(probes)
        if portable is not None and len(eligible) != 8:
            raise ValueError('Portable model requires the complete eight-member cohort')
        offspring: list[Genome] = []
        parent_map: dict[str, list[str]] = {}
        operations = []

        # A complete no-trade or losing window is still valid evidence. Select
        # only from this exact completed cohort and keep a bounded population.
        while len(offspring) < len(eligible):
            parent = tournament_select(eligible, k=3, rng=self._rng)
            mate_pool = [p for p in eligible if p.probe_id != parent.probe_id]
            mate = tournament_select(mate_pool, k=3, rng=self._rng)
            sexual = mate is not None and self._rng.random() > 0.3

            child_operations = []
            if portable is not None:
                children = portable.reproduce(parent.genome, mate.genome if sexual else None,
                    min(2, len(eligible) - len(offspring)), colony_config, rng=self._rng,
                    seed=self._search_streams.seed, epoch=self._search_epoch,
                    event=self._mutation_event, child_start=len(offspring),
                    operations=child_operations)
            else:
                children = reproduce(
                    parent.genome,
                    mate.genome if sexual else None,
                    min(2, len(eligible) - len(offspring)),
                    self.mutation_rate,
                    colony_config,
                    operations=child_operations,
                    rng=self._rng,
                    mutation_rngs=[self.mutation_rng(i) for i in range(len(offspring),
                        min(len(offspring) + 2, len(eligible)))],
                )

            for child, operation in zip(children, child_operations):
                idx = str(len(offspring))
                parent_ids = [parent.probe_id]
                if operation == "crossover_mutation":
                    parent_ids.append(mate.probe_id)
                parent_map[idx] = parent_ids
                offspring.append(child)
                operations.append({"offspring_index": int(idx),
                                   "operation": operation,
                                   "parent_ids": list(parent_ids)})

        self._cohort.propose(offspring, eligible)
        self._mutation_event += 1
        metadata = {"selection_policy": "completed-window-generational-ga-v1",
                    "iteration_id": eligible[0].iteration_id,
                    "evaluation_accounts": len(eligible), "offspring": operations}
        if portable is not None:
            metadata['mutation_operator'] = portable.VERSION
        return EvolutionResult(
            offspring=offspring,
            retire_ids=[p.probe_id for p in eligible],
            parent_map=parent_map,
            metadata=metadata,
        )


# ══════════════════════════════════════════════════════════════════════════════
# GA OPERATORS (extracted from evolution.py)
# ══════════════════════════════════════════════════════════════════════════════


def tournament_select(probes: list[Probe], k: int = 3, *, rng=None) -> Optional[Probe]:
    """Tournament selection: pick k random probes, return the fittest."""
    if not probes:
        return None
    tournament = private_rng(rng).sample(probes, min(k, len(probes)))
    return max(tournament, key=lambda p: p.fitness)


def crossover(
    parent_a: Genome,
    parent_b: Genome,
    generation: int,
    colony_config: Optional[ColonyConfig] = None,
    *, repair_flags: Optional[list[bool]] = None, rng=None,
) -> tuple[Genome, Genome]:
    """Uniform crossover with asset merging."""
    rng = private_rng(rng)
    child_a_genes: dict[str, float] = {}
    child_b_genes: dict[str, float] = {}

    for gene in NUMERIC_GENES:
        a_val = getattr(parent_a, gene)
        b_val = getattr(parent_b, gene)
        evolvable = colony_config.is_gene_evolvable(gene) if colony_config else True

        if evolvable and rng.random() > 0.5:
            child_a_genes[gene] = a_val
            child_b_genes[gene] = b_val
        else:
            child_a_genes[gene] = a_val if not evolvable else b_val
            child_b_genes[gene] = a_val if not evolvable else a_val

    effective_assets = (
        colony_config.get_effective_assets() if colony_config else AVAILABLE_ASSETS
    )
    # Stable ordered union: hash randomization must not change sampled assets.
    parent_assets = list(dict.fromkeys(parent_a.assets + parent_b.assets))
    parent_assets = [a for a in parent_assets if a in effective_assets]
    if not parent_assets:
        parent_assets = effective_assets

    def pick_assets(n_gene: float) -> list[str]:
        n = max(1, min(len(parent_assets), int(round(n_gene))))
        return rng.sample(parent_assets, min(n, len(parent_assets)))

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

    children = []
    for child in (child_a, child_b):
        child.validate(colony_config)
        repaired = preserve_fixed_controls(child, parent_a, colony_config)
        children.append(repaired)
        if repair_flags is not None:
            repair_flags.append(repaired is not child)
    return tuple(children)


def reproduce(
    parent: Genome,
    mate: Optional[Genome],
    num_children: int = 2,
    mutation_rate: float = 0.20,
    colony_config: Optional[ColonyConfig] = None,
    *, operations: Optional[list[str]] = None, rng=None, mutation_rngs=None,
) -> list[Genome]:
    """Produce children via sexual (crossover+mutate) or asexual (clone+mutate).

    The caller chooses whether this is sexual and supplies a mate only for
    actual crossover. This makes recorded genealogy match the operation.

    Both children from each crossover are kept and mutated independently to
    avoid wasting work.
    """
    generation = max(parent.generation, mate.generation if mate else parent.generation) + 1
    rng = private_rng(rng)
    children: list[Genome] = []

    if colony_config is not None and not any(colony_config.is_gene_evolvable(g) for g in NUMERIC_GENES):
        for _ in range(num_children):
            child = deepcopy(parent)
            child.generation, child.parent_ids = generation, []
            children.append(child)
            if operations is not None:
                operations.append("no_active_clone")
        return children

    def finish(child, rate, crossed=False, reverted=False):
        mutation_rng = mutation_rngs[len(children)] if mutation_rngs is not None else rng
        mutated = mutate(child, rate, colony_config=colony_config, rng=mutation_rng)
        result = preserve_fixed_controls(mutated, parent, colony_config)
        repaired = reverted or result is not mutated
        if operations is not None:
            operations.append("fixed_repair_clone" if repaired else
                              "crossover_mutation" if crossed else "clone_mutation")
        return result

    while len(children) < num_children:
        if mate is not None:
            repair_flags = []
            child_a, child_b = crossover(parent, mate, generation, colony_config,
                                         repair_flags=repair_flags, rng=rng)
            children.append(finish(child_a, mutation_rate, crossed=True, reverted=repair_flags[0]))
            if len(children) < num_children:
                children.append(finish(child_b, mutation_rate, crossed=True, reverted=repair_flags[1]))
        else:
            child = Genome(
                **{g: getattr(parent, g) for g in NUMERIC_GENES},
                assets=list(parent.assets),
                generation=generation,
                parent_ids=[],
            )
            children.append(finish(child, mutation_rate * 1.5))

    return children[:num_children]
