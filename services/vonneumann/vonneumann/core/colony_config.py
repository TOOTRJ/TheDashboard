"""
Colony Configuration — controls how a simulation run is initialized and evolved.

gene_overrides:  Bound genes throughout their lifetime or fix them to values
enabled_genes:   Only these genes evolve; others use defaults (None = all)
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
        if not isinstance(d, dict) or set(d) - {"min", "max", "default", "fixed"}:
            raise ValueError("Invalid gene override")
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

    def resolve_gene_domains(self):
        """The same validated active domains are used by every factory/operator."""
        if not isinstance(self.gene_overrides, dict) or any(
                not isinstance(value, GeneOverride) for value in self.gene_overrides.values()):
            raise ValueError("Invalid gene overrides")
        return GENE_REGISTRY.resolve_domains(
            {name: override.to_dict() for name, override in self.gene_overrides.items()},
            self.enabled_genes, len(self.get_effective_assets()))

    def is_gene_evolvable(self, gene_name: str) -> bool:
        return self.resolve_gene_domains()[gene_name].evolvable

    def get_effective_range(self, gene_name: str) -> tuple[float, float, float]:
        """Configured domain, including fixed/disabled values and asset capacity."""
        domain = self.resolve_gene_domains()[gene_name]
        return domain.minimum, domain.maximum, domain.default

    def get_effective_assets(self) -> list[str]:
        if self.available_assets is None:
            return list(AVAILABLE_ASSETS)
        assets = self.available_assets
        if (not isinstance(assets, list) or not assets or
                any(not isinstance(asset, str) or asset not in AVAILABLE_ASSETS for asset in assets) or
                len(assets) != len(set(assets))):
            raise ValueError("Assets must be unique supported assets")
        return list(assets)

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
        if not isinstance(d, dict) or not isinstance(d.get("gene_overrides", {}), dict):
            raise ValueError("Invalid colony gene configuration")
        overrides = {name: GeneOverride.from_dict(value) for name, value in d.get("gene_overrides", {}).items()}
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
