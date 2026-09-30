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

from ..search_random import SearchRandomStreams

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

    supports_cohorts = False

    def __init__(self) -> None:
        self.configure_search(SearchRandomStreams('0', self.name))

    def configure_search(self, streams: SearchRandomStreams, epoch: int = 0) -> None:
        """Called before initialization; ownership never depends on UUIDs/time."""
        if streams.algorithm != self.name:
            raise ValueError('Search stream algorithm does not match strategy')
        self._search_streams, self._search_epoch = streams, epoch
        self._rng = streams.rng('strategy', epoch)
        self._mutation_event = 0

    def mutation_rng(self, candidate_index: int = 0):
        return self._search_streams.rng('mutation', self._search_epoch,
                                        'generation', self._mutation_event, candidate_index)

    def cma_seed(self) -> int:
        return self._search_streams.derive('strategy', self._search_epoch, 'cma') % 2**32

    def bind_candidates(self, probes: list[Probe]) -> None:
        """Bind newly spawned accounts to the preceding ordered ask batch."""

    def abort_cohort(self) -> None:
        """Discard an interrupted batch without admitting partial evaluations."""

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
        *, rng=None,
    ) -> list[Genome]:
        """Create diversity-injection genomes. Default: mutated best-of-dead."""
        from ..evolution import inject_diversity_genomes

        return inject_diversity_genomes(
            genomes, current_generation, dead_probes, colony_config, count,
            rng=rng if rng is not None else self.mutation_rng()
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
        }
