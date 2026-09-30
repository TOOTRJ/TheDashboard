"""Normalized social swarm with best scores reset at every market window.

Each candidate has one observation in a common evaluation window. Therefore
its within-window personal best is its current phenotype and the cognitive
term is zero. Inertia and current-window social attraction move the swarm;
old market-regime scores are diagnostics, never current selection evidence.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import numpy as np

from ..genome import Genome
from ..parameter_codec import ParameterCodec, PARAMETER_POLICY
from .base import EvolutionResult, EvolutionStrategy
from .cohort_contract import SelectionCohort

if TYPE_CHECKING:
    from ..colony_config import ColonyConfig
    from ..probe import Probe


SWARM_POLICY = {
    "version": "window-reset-social-v1",
    "best_scores": "current_common_window_only",
    "cognitive_attraction": "zero_with_one_observation_per_window",
    "initial_velocity": "uniform_unit_minus_0_1_plus_0_1",
    "velocity": "repaired_normalized_displacement",
}


class ParticleSwarmStrategy(EvolutionStrategy):
    supports_cohorts = True
    name = "particle_swarm"
    label = "Window-reset Swarm (PSO variant)"
    description = "Normalized window-reset social swarm with inertia and current-window scores."

    def __init__(self) -> None:
        super().__init__()
        self.w = 0.7
        self.c2 = 1.5
        if not hasattr(self, "_rng"):
            self._rng = random.Random()
        self._cohort = SelectionCohort()
        self._codec: ParameterCodec | None = None
        self._velocities: dict[str, dict[str, float]] = {}
        self._personal_best: dict[str, tuple[dict, float | None]] = {}
        self._global_best: tuple[dict, float] | None = None

    def initialize(self, probes: list[Probe], colony_config: ColonyConfig) -> None:
        self.abort_cohort()
        codec = ParameterCodec(colony_config)
        for probe in probes:
            codec.encode(probe.genome)
        self._cohort.initialize(probes)
        self._codec = codec
        for probe in probes:
            self._velocities[probe.probe_id] = {
                name: self._rng.uniform(-0.1, 0.1) for name in codec.names
            }
            # A fresh account has no completed-window score yet.
            self._personal_best[probe.probe_id] = (probe.genome.to_dict(), None)

    def abort_cohort(self) -> None:
        self._cohort.abort()
        self._codec = None
        self._velocities.clear()
        self._personal_best.clear()
        self._global_best = None

    def bind_candidates(self, probes: list[Probe]) -> None:
        members = {probe.probe_id for probe in probes}
        if members != set(self._velocities):
            raise ValueError("Swarm velocities must map exactly to the new candidate accounts")
        self._cohort.bind(probes)
        self._personal_best = {probe.probe_id: (probe.genome.to_dict(), None) for probe in probes}
        self._global_best = None

    def evolve(
        self,
        probes: list[Probe],
        dead_probes: list[Probe],
        colony_config: ColonyConfig,
    ) -> EvolutionResult:
        if self._codec is None:
            raise ValueError("Swarm requires an initialized parameter codec")
        self._codec.check_configuration(colony_config)
        ordered = self._cohort.results(probes)
        # Validate every phenotype before consuming randomness or updating state.
        positions = {probe.probe_id: self._codec.encode(probe.genome) for probe in ordered}
        best = max(ordered, key=lambda probe: probe.fitness)
        global_position = positions[best.probe_id]
        next_velocities: dict[str, dict[str, float]] = {}
        offspring: list[Genome] = []
        parent_map: dict[str, list[str]] = {}
        parent_roles: dict[str, dict] = {}
        for probe in ordered:
            pid = probe.probe_id
            current = positions[pid]
            velocity = np.array([self._velocities[pid][name] for name in self._codec.names])
            random_social = np.array([self._rng.random() for _ in self._codec.names])
            social = self.c2 * random_social * (global_position - current)
            proposal = current + self.w * velocity + social
            child = self._codec.decode(proposal, probe.genome, clip=True)
            social_source = best if best.probe_id != pid and np.any(social != 0) else None
            sources = [probe, social_source] if social_source is not None else [probe]
            child.generation = max(source.genome.generation for source in sources) + 1
            parent_map[str(len(offspring))] = [source.probe_id for source in sources]
            parent_roles[str(len(offspring))] = {
                "particle_source_id": pid,
                "social_source_id": social_source.probe_id if social_source is not None else None,
            }
            child.parent_ids = []
            realized = self._codec.encode(child) - current
            next_velocities[pid] = {name: float(value) for name, value in zip(self._codec.names, realized)}
            offspring.append(child)

        self._cohort.propose(offspring, ordered)
        self._velocities = next_velocities
        self._personal_best = {probe.probe_id: (probe.genome.to_dict(), probe.fitness) for probe in ordered}
        self._global_best = (best.genome.to_dict(), best.fitness)
        return EvolutionResult(
            offspring=offspring,
            retire_ids=[probe.probe_id for probe in ordered],
            parent_map=parent_map,
            metadata={
                "lineage_policy": "numeric_particle_and_social_sources",
                "parent_roles": parent_roles,
                "global_best_fitness": best.fitness,
                "best_score_iteration_id": best.iteration_id,
                "parameter_policy": dict(PARAMETER_POLICY),
                "swarm_policy": dict(SWARM_POLICY),
                "active_dimensions": self._codec.dimensions,
            },
        )

    def remap_probe_id(self, old_id: str, new_id: str) -> None:
        """Transfer particle momentum to its fresh evaluation account."""
        if old_id not in self._velocities or new_id in self._velocities:
            raise ValueError("Swarm particle remapping must be one-to-one")
        self._velocities[new_id] = self._velocities.pop(old_id)
        self._personal_best[new_id] = self._personal_best.pop(old_id)
