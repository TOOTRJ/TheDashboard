"""Configured phenotypes in unit coordinates shared by numerical optimizers.

Integer/coupled repairs belong to Genome.validate. Assets deliberately use
deterministic inheritance/resize, not an unreported continuous coordinate or
independent random mutation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import numpy as np

from .gene_registry import finite_gene
from .genome import Genome, NUMERIC_GENES

if TYPE_CHECKING:
    from .colony_config import ColonyConfig


PARAMETER_POLICY = {
    "version": "effective-unit-domain-v1",
    "coordinates": "unit_interval",
    "integer_rounding": "genome_nearest_half_up",
    "assets": "inherit_and_resize",
    "repairs": "configured_phenotype",
}


class ParameterCodec:
    """One immutable effective geometry for an optimizer epoch."""

    def __init__(self, colony_config: ColonyConfig):
        self._config = deepcopy(colony_config)
        self.domains = self._config.resolve_gene_domains()
        self.names = tuple(name for name, domain in self.domains.items() if domain.evolvable)
        self._assets = self._config.get_effective_assets()

    @property
    def dimensions(self) -> int:
        return len(self.names)

    @property
    def bounds(self) -> np.ndarray:
        return np.tile([0.0, 1.0], (self.dimensions, 1))

    def check_configuration(self, colony_config: ColonyConfig) -> None:
        if (colony_config.resolve_gene_domains() != self.domains
                or colony_config.get_effective_assets() != self._assets):
            raise ValueError("Optimizer geometry cannot change during an evaluation epoch")

    def vector(self, values, *, clip: bool = False) -> np.ndarray:
        # Preserve booleans/types until finite validation; mixed float arrays
        # must not silently coerce True into a valid numeric coordinate.
        array = np.asarray(values, dtype=object)
        if array.ndim != 1 or len(array) != self.dimensions:
            raise ValueError("Optimizer vector has the wrong number of dimensions")
        unit = np.array([finite_gene(value) for value in array.tolist()], dtype=float)
        if clip:
            return np.clip(unit, 0.0, 1.0)
        if np.any(unit < 0.0) or np.any(unit > 1.0):
            raise ValueError("Optimizer coordinates must stay in the unit interval")
        return unit

    def encode(self, genome: Genome) -> np.ndarray:
        # Encoding never silently repairs a scored phenotype or fixed control.
        validated = deepcopy(genome).validate(self._config)
        if (any(getattr(validated, name) != getattr(genome, name) for name in NUMERIC_GENES)
                or validated.assets != genome.assets):
            raise ValueError("Optimizer requires an already validated configured phenotype")
        return self.vector([
            (getattr(genome, name) - self.domains[name].minimum)
            / (self.domains[name].maximum - self.domains[name].minimum)
            for name in self.names
        ])

    def decode(self, values, template: Genome, *, clip: bool = False) -> Genome:
        unit = self.vector(values, clip=clip)
        genome = deepcopy(template)
        for name, coordinate in zip(self.names, unit):
            domain = self.domains[name]
            setattr(genome, name, domain.minimum + float(coordinate) * (domain.maximum - domain.minimum))
        genome.validate(self._config)
        self.encode(genome)
        return genome
