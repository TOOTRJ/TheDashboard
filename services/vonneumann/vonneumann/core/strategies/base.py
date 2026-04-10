"""
Strategy base class for evolutionary algorithms.

To add a new strategy:
  1. Create a file in core/strategies/
  2. Subclass EvolutionStrategy
  3. Implement name, label, initialize, evolve
  4. Done. Auto-discovery handles the rest.
"""

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

    offspring: list[Genome]
    retire_ids: list[str]
    parent_map: dict[str, list[str]] = field(default_factory=dict)
    """Maps str(offspring_index) -> [parent_probe_ids] for genealogy tracking."""
    metadata: dict = field(default_factory=dict)


class EvolutionStrategy(ABC):
    """Base class for all evolutionary algorithm strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique snake_case identifier (e.g. 'genetic_algorithm')."""

    @property
    @abstractmethod
    def label(self) -> str:
        """Human-readable display name (e.g. 'Genetic Algorithm')."""

    @property
    def description(self) -> str:
        """One-line description shown in the frontend strategy picker."""
        return ""

    @abstractmethod
    def initialize(self, probes: list[Probe], colony_config: ColonyConfig) -> None:
        """Called once after Gen-0 probes are spawned, before the tick loop.
        Receives Probe objects so strategies can store probe_ids for state tracking."""

    @abstractmethod
    def evolve(
        self,
        probes: list[Probe],
        dead_probes: list[Probe],
        colony_config: ColonyConfig,
    ) -> EvolutionResult:
        """Called every reproduction_interval ticks.
        Returns genomes to spawn and probe IDs to retire.
        Must NOT mutate probe state directly."""

    def compute_diversity(self, genomes: list[Genome]) -> float:
        """Population diversity (0.0-1.0). Default: avg pairwise distance."""
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
        """Create diversity-injection genomes. Default: mutated best-of-dead."""
        from ..evolution import inject_diversity_genomes

        return inject_diversity_genomes(
            genomes, current_generation, dead_probes, colony_config, count
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
        }
