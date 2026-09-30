"""
Probe genome — the evolvable parameters that define trading behavior.

Gene definitions live in gene_registry.py. This module provides:
  - Genome dataclass (stores gene values)
  - random_genome() (creates Gen-0 genomes, optionally with ColonyConfig)
  - validate() (projects the actual phenotype into configured domains)

Backward-compat exports: GENE_BOUNDS, NUMERIC_GENES, AVAILABLE_ASSETS
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, TYPE_CHECKING

from .gene_registry import GENE_REGISTRY, GeneType, finite_gene

if TYPE_CHECKING:
    from .colony_config import ColonyConfig

# Tradeable assets on Solana DEXs
AVAILABLE_ASSETS = [
    "SOL/USDC",
    "JUP/USDC",
    "BONK/USDC",
    "WIF/USDC",
    "JTO/USDC",
    "PYTH/USDC",
    "ORCA/USDC",
    "RAY/USDC",
]

# Backward-compatible exports (derived from registry)
GENE_BOUNDS: dict[str, tuple[float, float]] = GENE_REGISTRY.gene_bounds()
NUMERIC_GENES: list[str] = GENE_REGISTRY.numeric_gene_names()


@dataclass
class Genome:
    """Full genetic blueprint of a probe. All numeric genes are floats."""

    # Signal genes
    rsi_period: float = 14.0
    rsi_oversold: float = 32.0
    rsi_overbought: float = 70.0
    ema_fast: float = 9.0
    ema_slow: float = 21.0
    volume_threshold: float = 1.4

    # Risk genes
    position_size_pct: float = 0.75
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.07
    max_open_positions: float = 1.0

    # Lifecycle genes
    timeframe_minutes: float = 15.0
    benchmark_target_pct: float = 0.08
    reproduce_target_dollars: float = 10.0
    death_drawdown_pct: float = 0.20
    num_assets: float = 2.0

    # Asset selection (not numeric, handled separately)
    assets: list[str] = field(default_factory=lambda: ["SOL/USDC", "JUP/USDC"])

    # Lineage metadata (not evolved)
    generation: int = 0
    parent_ids: list[str] = field(default_factory=list)

    def int_genes(self) -> dict[str, int]:
        """Read the integer phenotype; validated genomes need no hidden rounding."""
        result = {}
        for gene in GENE_REGISTRY.all_genes():
            if gene.gene_type != GeneType.INT:
                continue
            value = finite_gene(getattr(self, gene.name))
            if not value.is_integer():
                raise ValueError("Integer phenotype must be validated before trading")
            result[gene.name] = int(value)
        if result["ema_fast"] >= result["ema_slow"]:
            raise ValueError("EMA fast must be below EMA slow in the integer phenotype")
        return result

    def validate(self, colony_config: Optional[ColonyConfig] = None) -> Genome:
        """Apply configured controls and relationships without consuming randomness."""
        effective_assets = colony_config.get_effective_assets() if colony_config else list(AVAILABLE_ASSETS)
        domains = (colony_config.resolve_gene_domains() if colony_config else
                   GENE_REGISTRY.resolve_domains(asset_count=len(effective_assets)))
        corrected = GENE_REGISTRY.validate_genome(
            {name: getattr(self, name) for name in NUMERIC_GENES}, domains)
        if not isinstance(self.assets, list) or any(not isinstance(asset, str) for asset in self.assets):
            raise ValueError("Genome assets must be a list of trading pairs")
        n = int(corrected["num_assets"])
        # Preserve valid preferences, removing duplicates and deterministic filling.
        assets = list(dict.fromkeys(asset for asset in self.assets if asset in effective_assets))[:n]
        assets.extend(asset for asset in effective_assets if asset not in assets)
        assets = assets[:n]
        if len(assets) != n:
            raise ValueError("Genome asset count is not feasible")
        # Commit only after every gene and asset constraint has validated.
        for name, value in corrected.items():
            setattr(self, name, value)
        self.assets = assets
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Genome:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


def random_genome(
    generation: int = 0,
    parent_ids: list[str] | None = None,
    colony_config: Optional[ColonyConfig] = None,
) -> Genome:
    """
    Generate a random genome for Gen-0 probes.
    If colony_config is provided, respects gene overrides and available assets.
    """
    effective_assets = colony_config.get_effective_assets() if colony_config else list(AVAILABLE_ASSETS)
    domains = (colony_config.resolve_gene_domains() if colony_config else
               GENE_REGISTRY.resolve_domains(asset_count=len(effective_assets)))
    gene_values: dict[str, float] = {}
    for name, domain in domains.items():
        if not domain.evolvable:
            gene_values[name] = float(domain.default)
        elif domain.integer:
            gene_values[name] = float(random.randint(int(domain.minimum), int(domain.maximum)))
        else:
            gene_values[name] = random.uniform(domain.minimum, domain.maximum)
    assets = random.sample(effective_assets, int(gene_values["num_assets"]))
    return Genome(**gene_values, assets=assets, generation=generation,
                  parent_ids=list(parent_ids) if parent_ids else []).validate(colony_config)
