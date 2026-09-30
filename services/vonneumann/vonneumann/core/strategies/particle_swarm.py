"""
Particle Swarm Optimization strategy.

Each particle (probe) updates its genome based on personal best,
global best, and its velocity vector. Every evolution step retires
all probes and spawns new ones at updated positions.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..evolution import mutate_assets
from ..gene_registry import GENE_REGISTRY
from ..genome import Genome
from .base import EvolutionResult, EvolutionStrategy

if TYPE_CHECKING:
    from ..colony_config import ColonyConfig
    from ..probe import Probe

NUMERIC_GENES = GENE_REGISTRY.numeric_gene_names()


class ParticleSwarmStrategy(EvolutionStrategy):
    supports_cohorts = True
    name = "particle_swarm"
    label = "Particle Swarm Optimization"
    description = "PSO with inertia weight, cognitive and social components."

    def __init__(self) -> None:
        self.w = 0.7  # Inertia weight
        self.c1 = 1.5  # Cognitive coefficient (personal best attraction)
        self.c2 = 1.5  # Social coefficient (global best attraction)
        self._velocities: dict[str, dict[str, float]] = {}
        self._personal_best: dict[str, tuple[dict, float]] = {}
        self._global_best: tuple[dict, float] | None = None

    def initialize(self, probes: list[Probe], colony_config: ColonyConfig) -> None:
        """Initialize velocities and personal bests keyed by real probe IDs."""
        self.abort_cohort()
        for probe in probes:
            self._velocities[probe.probe_id] = {name: 0.0 for name in NUMERIC_GENES}
            self._personal_best[probe.probe_id] = (
                probe.genome.to_dict(),
                probe.fitness,
            )

    def abort_cohort(self) -> None:
        self._velocities.clear()
        self._personal_best.clear()
        self._global_best = None

    def bind_candidates(self, probes: list[Probe]) -> None:
        members = {probe.probe_id for probe in probes}
        self._velocities = {pid: value for pid, value in self._velocities.items() if pid in members}
        self._personal_best = {pid: value for pid, value in self._personal_best.items() if pid in members}

    def evolve(
        self,
        probes: list[Probe],
        dead_probes: list[Probe],
        colony_config: ColonyConfig,
    ) -> EvolutionResult:
        # Update personal and global bests
        for p in probes:
            pid = p.probe_id
            if pid not in self._personal_best or p.fitness > self._personal_best[pid][1]:
                self._personal_best[pid] = (p.genome.to_dict(), p.fitness)
            if self._global_best is None or p.fitness > self._global_best[1]:
                self._global_best = (p.genome.to_dict(), p.fitness)

        offspring: list[Genome] = []
        retire_ids: list[str] = []
        parent_map: dict[str, list[str]] = {}

        for probe in probes:
            pid = probe.probe_id
            if pid not in self._velocities:
                self._velocities[pid] = {name: 0.0 for name in NUMERIC_GENES}

            velocity = self._velocities[pid]
            pb = self._personal_best[pid][0]
            gb = self._global_best[0]
            current = probe.genome.to_dict()

            new_genes: dict[str, float] = {}
            new_velocity: dict[str, float] = {}
            for gene in NUMERIC_GENES:
                if not colony_config.is_gene_evolvable(gene):
                    new_genes[gene] = current[gene]
                    new_velocity[gene] = 0.0
                    continue
                r1, r2 = random.random(), random.random()
                v = (
                    self.w * velocity[gene]
                    + self.c1 * r1 * (pb[gene] - current[gene])
                    + self.c2 * r2 * (gb[gene] - current[gene])
                )
                new_velocity[gene] = v
                new_genes[gene] = current[gene] + v

            new_genome = Genome.from_dict(
                {**new_genes, "generation": probe.genome.generation + 1}
            )
            new_genome.assets = mutate_assets(
                probe.genome.assets, colony_config, swap_rate=0.10
            )
            new_genome.validate(colony_config)

            # Store velocity under same key — genesis calls remap_probe_id after spawning
            self._velocities[pid] = new_velocity

            idx = str(len(offspring))
            parent_map[idx] = [pid]
            offspring.append(new_genome)
            retire_ids.append(pid)

        return EvolutionResult(
            offspring=offspring,
            retire_ids=retire_ids,
            parent_map=parent_map,
            metadata={
                "global_best_fitness": self._global_best[1]
                if self._global_best
                else 0
            },
        )

    def remap_probe_id(self, old_id: str, new_id: str) -> None:
        """Transfer velocity and personal-best state from old probe to new."""
        if old_id in self._velocities:
            self._velocities[new_id] = self._velocities.pop(old_id)
        if old_id in self._personal_best:
            self._personal_best[new_id] = self._personal_best.pop(old_id)
