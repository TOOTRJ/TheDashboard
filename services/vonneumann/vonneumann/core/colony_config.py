"""
Colony Configuration — controls how a simulation run is initialized and evolved.

gene_overrides:  Narrow starting ranges or fix genes to specific values
enabled_genes:   Only these genes participate in mutation/crossover (None = all)
available_assets: Restrict the asset pool (None = all AVAILABLE_ASSETS)
max_lifespan_ticks: Maximum candidate market minutes after warmup (None = no limit)
reproduction_interval: Common evaluation window in market minutes after all candidates warm
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any

from .gene_registry import GENE_REGISTRY
from .genome import AVAILABLE_ASSETS


@dataclass
class GeneOverride:
    """Override for a single gene. All fields optional."""
    min: Optional[float] = None
    max: Optional[float] = None
    default: Optional[float] = None
    fixed: Optional[float] = None  # If set, gene does not evolve

    def to_dict(self) -> dict:
        d: dict[str, Any] = {}
        if self.min is not None: d["min"] = self.min
        if self.max is not None: d["max"] = self.max
        if self.default is not None: d["default"] = self.default
        if self.fixed is not None: d["fixed"] = self.fixed
        return d

    @classmethod
    def from_dict(cls, d: dict) -> GeneOverride:
        return cls(
            min=d.get("min"),
            max=d.get("max"),
            default=d.get("default"),
            fixed=d.get("fixed"),
        )


@dataclass
class ColonyConfig:
    """Full configuration for a simulation run."""
    gene_overrides: dict[str, GeneOverride] = field(default_factory=dict)
    enabled_genes: Optional[list[str]] = None  # None = all genes evolve
    available_assets: Optional[list[str]] = None  # None = all assets
    max_lifespan_ticks: Optional[int] = None
    reproduction_interval: int = 100  # Common evaluation window in market minutes after all candidates warm
    mutation_rate: Optional[float] = None  # None = use strategy default

    def is_gene_evolvable(self, gene_name: str) -> bool:
        """Returns False if gene is fixed or not in enabled_genes."""
        override = self.gene_overrides.get(gene_name)
        if override and override.fixed is not None:
            return False
        if self.enabled_genes is not None and gene_name not in self.enabled_genes:
            return False
        return True

    def get_effective_range(self, gene_name: str) -> tuple[float, float, float]:
        """
        Get (min, max, default) for a gene, respecting overrides.
        Overrides are clamped within hard registry bounds.
        """
        gene_def = GENE_REGISTRY.get(gene_name)
        override = self.gene_overrides.get(gene_name)

        if override and override.fixed is not None:
            val = max(gene_def.min, min(gene_def.max, override.fixed))
            return (val, val, val)

        lo = gene_def.min
        hi = gene_def.max
        default = gene_def.default

        if override:
            if override.min is not None:
                lo = max(gene_def.min, override.min)
            if override.max is not None:
                hi = min(gene_def.max, override.max)
            if override.default is not None:
                default = max(lo, min(hi, override.default))

        # Ensure lo <= hi
        if lo > hi:
            lo, hi = hi, lo

        return (lo, hi, max(lo, min(hi, default)))

    def get_effective_assets(self) -> list[str]:
        if self.available_assets:
            return [a for a in self.available_assets if a in AVAILABLE_ASSETS]
        return list(AVAILABLE_ASSETS)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "gene_overrides": {k: v.to_dict() for k, v in self.gene_overrides.items()},
            "enabled_genes": self.enabled_genes,
            "available_assets": self.available_assets,
            "max_lifespan_ticks": self.max_lifespan_ticks,
            "reproduction_interval": self.reproduction_interval,
        }
        if self.mutation_rate is not None:
            d["mutation_rate"] = self.mutation_rate
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ColonyConfig:
        overrides = {}
        for k, v in d.get("gene_overrides", {}).items():
            if isinstance(v, dict):
                overrides[k] = GeneOverride.from_dict(v)
        return cls(
            gene_overrides=overrides,
            enabled_genes=d.get("enabled_genes"),
            available_assets=d.get("available_assets"),
            max_lifespan_ticks=d.get("max_lifespan_ticks"),
            reproduction_interval=d.get("reproduction_interval", 100),
            mutation_rate=d.get("mutation_rate"),
        )


# ══════════════════════════════════════════════════════════════════════════════
# PRESETS
# ══════════════════════════════════════════════════════════════════════════════

PRESET_CONFIGS: dict[str, ColonyConfig] = {
    "default": ColonyConfig(),

    "rsi_focus": ColonyConfig(
        enabled_genes=[
            "rsi_period", "rsi_oversold", "rsi_overbought",
            "stop_loss_pct", "take_profit_pct", "position_size_pct",
            "benchmark_target_pct", "reproduce_target_dollars", "death_drawdown_pct",
        ],
        gene_overrides={
            "volume_threshold": GeneOverride(fixed=1.5),
            "ema_fast": GeneOverride(fixed=9.0),
            "ema_slow": GeneOverride(fixed=21.0),
        },
    ),

    "conservative_risk": ColonyConfig(
        gene_overrides={
            "position_size_pct": GeneOverride(min=0.05, max=0.15),
            "stop_loss_pct": GeneOverride(min=0.01, max=0.05),
            "take_profit_pct": GeneOverride(min=0.03, max=0.10),
            "max_open_positions": GeneOverride(fixed=1.0),
        },
    ),

    "wide_exploration": ColonyConfig(
        gene_overrides={
            "benchmark_target_pct": GeneOverride(min=0.03, max=0.08),
            "reproduce_target_dollars": GeneOverride(min=2.0, max=8.0),
        },
        reproduction_interval=50,
    ),

    "high_risk": ColonyConfig(
        gene_overrides={
            "position_size_pct": GeneOverride(min=0.70, max=0.90),
            "stop_loss_pct": GeneOverride(min=0.05, max=0.10),
            "take_profit_pct": GeneOverride(min=0.10, max=0.20),
            "max_open_positions": GeneOverride(fixed=4.0),
            "benchmark_target_pct": GeneOverride(min=0.03, max=0.06),
            "reproduce_target_dollars": GeneOverride(min=2.0, max=5.0),
            "death_drawdown_pct": GeneOverride(min=0.25, max=0.35),
        },
        reproduction_interval=75,
    ),

    "fast_evolution": ColonyConfig(
        gene_overrides={
            "benchmark_target_pct": GeneOverride(min=0.03, max=0.05),
            "reproduce_target_dollars": GeneOverride(min=2.0, max=5.0),
            "timeframe_minutes": GeneOverride(min=5, max=15),
        },
        reproduction_interval=25,
        max_lifespan_ticks=200,
        mutation_rate=0.35,
    ),

    "slow_evolution": ColonyConfig(
        gene_overrides={
            "benchmark_target_pct": GeneOverride(min=0.08, max=0.15),
            "reproduce_target_dollars": GeneOverride(min=15.0, max=50.0),
            "timeframe_minutes": GeneOverride(min=30, max=60),
        },
        reproduction_interval=200,
        mutation_rate=0.10,
    ),

    "scalper": ColonyConfig(
        gene_overrides={
            "position_size_pct": GeneOverride(min=0.10, max=0.25),
            "stop_loss_pct": GeneOverride(min=0.01, max=0.03),
            "take_profit_pct": GeneOverride(min=0.03, max=0.06),
            "timeframe_minutes": GeneOverride(fixed=5.0),
            "max_open_positions": GeneOverride(min=2, max=4),
        },
        reproduction_interval=50,
    ),
}
