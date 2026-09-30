"""
CMA-ES strategy — Covariance Matrix Adaptation Evolution Strategy.

Uses the `cmaes` pip package (ask-and-tell interface). Each evolution step
tells the optimizer the fitness of the current population, then asks for
new candidate solutions. The entire population is replaced each step.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import TYPE_CHECKING

import numpy as np

try:
    import cmaes as cmaes_lib
except ImportError:
    cmaes_lib = None  # type: ignore[assignment]

from ..evolution import mutate_assets
from ..gene_registry import GENE_REGISTRY
from ..genome import Genome
from ..evaluation import EvaluatedCandidate
from .base import EvolutionResult, EvolutionStrategy

if TYPE_CHECKING:
    from ..colony_config import ColonyConfig
    from ..probe import Probe

NUMERIC_GENES = GENE_REGISTRY.numeric_gene_names()


class CMAEvolutionStrategy(EvolutionStrategy):
    supports_cohorts = True
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
        self._pending_vectors: list[np.ndarray] | None = None
        self._pending_genomes: list[Genome] | None = None
        self._bound_ids: tuple[str, ...] = ()
        self._bound_genomes: dict[str, dict] = {}
        self._awaiting_bind = False

    @staticmethod
    def _phenotype(genome: Genome) -> dict:
        return {**{name: getattr(genome, name) for name in NUMERIC_GENES},
                "assets": list(genome.assets)}

    def abort_cohort(self) -> None:
        """A partial market window cannot update the search distribution."""
        self._optimizer = None
        self._gene_names = []
        self._first_generation = True
        self._pending_vectors = self._pending_genomes = None
        self._bound_ids = ()
        self._bound_genomes = {}
        self._awaiting_bind = False

    def bind_candidates(self, probes: list[Probe]) -> None:
        ids = tuple(probe.probe_id for probe in probes)
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("CMA candidates must have unique identities")
        phenotypes = {probe.probe_id: self._phenotype(probe.genome) for probe in probes}
        if self._optimizer is not None and len(ids) != self._optimizer.population_size:
            raise ValueError("CMA binding must contain the complete population")
        if self._awaiting_bind and self._pending_vectors is None:
            raise ValueError("CMA has no valid next ask batch to bind")
        if self._pending_vectors is not None:
            if not self._awaiting_bind:
                raise ValueError("CMA ask batch has already been bound")
            if (self._pending_genomes is None or len(probes) != len(self._pending_vectors) or
                    any(self._phenotype(probe.genome) != self._phenotype(genome)
                        for probe, genome in zip(probes, self._pending_genomes))):
                raise ValueError("CMA candidates do not match their ordered ask batch")
        elif self._optimizer is not None and self._bound_ids and (
                ids != self._bound_ids or phenotypes != self._bound_genomes):
            raise ValueError("CMA bootstrap membership cannot be replaced before evaluation")
        self._bound_ids, self._bound_genomes = ids, phenotypes
        self._awaiting_bind = False

    def _validate_results(self, probes: list[Probe]) -> dict:
        if self._awaiting_bind or not self._bound_ids:
            raise ValueError("CMA results require a bound candidate batch")
        by_id = {probe.probe_id: probe for probe in probes}
        if len(by_id) != len(probes) or set(by_id) != set(self._bound_ids):
            raise ValueError("CMA results must cover every bound candidate exactly once")
        iterations = set()
        evaluations = set()
        windows = set()
        for probe in probes:
            if (not isinstance(probe, EvaluatedCandidate) or probe.status != "completed" or
                    not probe.cohort_complete):
                raise ValueError("CMA accepts only completed cohort evaluations")
            if (self._phenotype(probe.genome) != self._bound_genomes[probe.probe_id] or
                    isinstance(probe.fitness, bool) or not isinstance(probe.fitness, (int, float)) or
                    not math.isfinite(probe.fitness)):
                raise ValueError("CMA result phenotype or score is invalid")
            iterations.add(probe.iteration_id)
            evaluations.add(probe.evaluation_id)
            if (any(isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or
                    not math.isfinite(stamp) or stamp < 0 for stamp in
                    (probe.window_started_at, probe.window_ends_at, probe.terminated_at)) or
                    probe.window_ends_at <= probe.window_started_at):
                raise ValueError("CMA results require a valid common evaluation window")
            windows.add((probe.window_started_at, probe.window_ends_at))
        if len(iterations) != 1 or len(evaluations) != len(probes) or len(windows) != 1:
            raise ValueError("CMA results mix cohorts or duplicate evaluation identities")
        return by_id

    def initialize(self, probes: list[Probe], colony_config: ColonyConfig) -> None:
        self.abort_cohort()
        if cmaes_lib is None:
            raise ImportError(
                "cmaes package is required for CMA-ES strategy. "
                "Install with: pip install cmaes"
            )
        self._gene_names = [
            g for g in NUMERIC_GENES if colony_config.is_gene_evolvable(g)
        ]
        if not probes:
            return
        if not self._gene_names:
            self.bind_candidates(probes)
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
        self.bind_candidates(probes)

    def evolve(
        self,
        probes: list[Probe],
        dead_probes: list[Probe],
        colony_config: ColonyConfig,
    ) -> EvolutionResult:
        by_id = self._validate_results(probes)
        if self._optimizer is None:
            return EvolutionResult(offspring=[], retire_ids=[])

        # Consume the bound batch before changing optimizer state. If an ask or
        # tell fails the controller fails closed rather than repeating a tell.
        ids = self._bound_ids
        pending_vectors = self._pending_vectors
        self._bound_ids = ()
        self._pending_vectors = self._pending_genomes = None
        self._awaiting_bind = True
        # The initial random cohort bootstraps the mean; it was never asked.
        # Subsequent updates retain EXACT ask vectors, not rounded/repaired genes.
        if pending_vectors is not None:
            solutions = [(params.copy(), -by_id[pid].fitness)
                         for pid, params in zip(ids, pending_vectors)]
            self._optimizer.tell(solutions)
        self._first_generation = False

        # Ask: sample new candidate solutions
        offspring: list[Genome] = []
        vectors: list[np.ndarray] = []
        best = max(probes, key=lambda p: p.fitness)
        for _ in range(self._optimizer.population_size):
            params = self._optimizer.ask().copy()
            vectors.append(params)
            genome_dict: dict = {}
            for i, name in enumerate(self._gene_names):
                genome_dict[name] = float(params[i])
            # Fill non-evolvable genes from the best current probe
            for name in NUMERIC_GENES:
                if name not in genome_dict:
                    genome_dict[name] = getattr(best.genome, name)
            genome_dict["generation"] = best.genome.generation + 1
            new_genome = Genome.from_dict(genome_dict)
            new_genome.assets = mutate_assets(
                best.genome.assets, colony_config, swap_rate=0.10
            )
            new_genome.validate(colony_config)
            offspring.append(new_genome)

        self._pending_vectors = vectors
        self._pending_genomes = deepcopy(offspring)

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
