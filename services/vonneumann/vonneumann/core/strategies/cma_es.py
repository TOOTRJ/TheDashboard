"""
CMA-ES strategy — Covariance Matrix Adaptation Evolution Strategy.

Uses the `cmaes` pip package (ask-and-tell interface). Each evolution step
tells the optimizer the fitness of the current population, then asks for
new candidate solutions. The entire population is replaced each step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

try:
    import cmaes as cmaes_lib
except ImportError:
    cmaes_lib = None  # type: ignore[assignment]

from ..gene_registry import GENE_REGISTRY
from ..genome import Genome
from .base import EvolutionResult, EvolutionStrategy

if TYPE_CHECKING:
    from ..colony_config import ColonyConfig
    from ..probe import Probe

NUMERIC_GENES = GENE_REGISTRY.numeric_gene_names()


class CMAEvolutionStrategy(EvolutionStrategy):
    name = "cma_es"
    label = "CMA-ES"
    description = (
        "Covariance Matrix Adaptation Evolution Strategy. "
        "Best for continuous optimization in <100 dimensions."
    )

    def __init__(self) -> None:
        self._optimizer = None
        self._gene_names: list[str] = []
        self._first_generation: bool = True

    def initialize(self, probes: list[Probe], colony_config: ColonyConfig) -> None:
        if cmaes_lib is None:
            raise ImportError(
                "cmaes package is required for CMA-ES strategy. "
                "Install with: pip install cmaes"
            )
        self._gene_names = [
            g for g in NUMERIC_GENES if colony_config.is_gene_evolvable(g)
        ]
        if not self._gene_names or not probes:
            return

        genomes = [p.genome for p in probes]

        mean = np.array(
            [np.mean([getattr(g, name) for g in genomes]) for name in self._gene_names]
        )
        bounds = np.array(
            [
                list(colony_config.get_effective_range(name)[:2])
                for name in self._gene_names
            ]
        )
        sigma = float(np.mean(bounds[:, 1] - bounds[:, 0]) * 0.3)

        self._optimizer = cmaes_lib.CMA(
            mean=mean,
            sigma=sigma,
            bounds=bounds,
            population_size=len(genomes),
        )

    def evolve(
        self,
        probes: list[Probe],
        dead_probes: list[Probe],
        colony_config: ColonyConfig,
    ) -> EvolutionResult:
        if self._optimizer is None:
            return EvolutionResult(offspring=[], retire_ids=[])

        # Tell: feed fitness to CMA-ES (skip first call — no prior ask() to match)
        if not self._first_generation:
            solutions = []
            for probe in probes:
                params = np.array(
                    [getattr(probe.genome, name) for name in self._gene_names]
                )
                solutions.append((params, -probe.fitness))  # CMA-ES minimizes
            self._optimizer.tell(solutions)
        self._first_generation = False

        # Ask: sample new candidate solutions
        offspring: list[Genome] = []
        best = max(probes, key=lambda p: p.fitness)
        for _ in range(len(probes)):
            params = self._optimizer.ask()
            genome_dict: dict = {}
            for i, name in enumerate(self._gene_names):
                genome_dict[name] = float(params[i])
            # Fill non-evolvable genes from the best current probe
            for name in NUMERIC_GENES:
                if name not in genome_dict:
                    genome_dict[name] = getattr(best.genome, name)
            genome_dict["generation"] = best.genome.generation + 1
            new_genome = Genome.from_dict(genome_dict)
            new_genome.assets = list(best.genome.assets)
            new_genome.validate(colony_config)
            offspring.append(new_genome)

        retire_ids = [p.probe_id for p in probes]

        return EvolutionResult(
            offspring=offspring,
            retire_ids=retire_ids,
            metadata={
                "cma_generation": self._optimizer.generation
                if hasattr(self._optimizer, "generation")
                else 0
            },
        )
