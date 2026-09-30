"""
Probe genome — the evolvable parameters that define trading behavior.

Gene definitions live in gene_registry.py. This module provides:
  - Genome dataclass (stores gene values)
  - random_genome() (creates Gen-0 genomes, optionally with ColonyConfig)
  - validate() (clamps bounds + runs constraints via registry)

Backward-compat exports: GENE_BOUNDS, NUMERIC_GENES, AVAILABLE_ASSETS
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, TYPE_CHECKING

from .gene_registry import GENE_REGISTRY

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
        """Return genes that should be integers during trading."""
        return {
            "rsi_period": max(2, int(round(self.rsi_period))),
            "ema_fast": max(2, int(round(self.ema_fast))),
            "ema_slow": max(3, int(round(self.ema_slow))),
            "max_open_positions": max(1, int(round(self.max_open_positions))),
            "timeframe_minutes": max(1, int(round(self.timeframe_minutes))),
            "num_assets": max(1, min(len(AVAILABLE_ASSETS), int(round(self.num_assets)))),
        }

    def validate(self, colony_config: Optional[ColonyConfig] = None) -> Genome:
        """Clamp all genes to bounds and run registry constraints. Returns self."""
        # Build a dict snapshot of numeric genes
        genome_dict = {name: getattr(self, name) for name in NUMERIC_GENES}

        # Run registry validation (clamp + constraints)
        corrected = GENE_REGISTRY.validate_genome(genome_dict)

        # Apply corrected values back
        for name, val in corrected.items():
            setattr(self, name, val)

        # Sync asset list to num_assets gene
        effective_assets = AVAILABLE_ASSETS
        if colony_config:
            effective_assets = colony_config.get_effective_assets()

        n = self.int_genes()["num_assets"]
        n = min(n, len(effective_assets))
        if len(self.assets) != n or not all(a in effective_assets for a in self.assets):
            self.assets = random.sample(effective_assets, n)

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
    effective_assets = AVAILABLE_ASSETS
    if colony_config:
        effective_assets = colony_config.get_effective_assets()

    n_assets = random.randint(1, min(3, len(effective_assets)))
    assets = random.sample(effective_assets, n_assets)

    gene_values: dict[str, float] = {}
    for gene_def in GENE_REGISTRY.all_genes():
        if colony_config:
            lo, hi, default = colony_config.get_effective_range(gene_def.name)
            # Check if gene is fixed
            override = colony_config.gene_overrides.get(gene_def.name)
            if override and override.fixed is not None:
                gene_values[gene_def.name] = max(gene_def.min, min(gene_def.max, override.fixed))
                continue
        else:
            lo, hi = gene_def.min, gene_def.max

        # Special handling for timeframe
        if gene_def.name == "timeframe_minutes":
            choices = [v for v in [5.0, 15.0, 30.0, 60.0] if lo <= v <= hi]
            gene_values[gene_def.name] = random.choice(choices) if choices else lo
        else:
            gene_values[gene_def.name] = random.uniform(lo, hi)

    # Override num_assets to match actual asset count
    gene_values["num_assets"] = float(n_assets)

    g = Genome(
        **gene_values,
        assets=assets,
        generation=generation,
        parent_ids=parent_ids or [],
    )
    return g.validate(colony_config)
