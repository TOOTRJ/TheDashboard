"""
Centralized Gene Registry — single source of truth for all gene definitions.

Adding a new gene:
  1. Call GENE_REGISTRY.register(GeneDefinition(...)) at the bottom of this file
  2. Add the field to the Genome dataclass in genome.py
  3. That's it — evolution, validation, config UI, radar chart all auto-discover it

Each gene has: name, label, group, bounds, default, type, description, constraints.
Constraints are functions that correct a gene value given the full genome snapshot,
ensuring structural invariants (e.g., ema_fast < ema_slow).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Any


class GeneType(str, Enum):
    FLOAT = "float"
    INT = "int"


class GeneGroup(str, Enum):
    SIGNAL = "signal"
    RISK = "risk"
    LIFECYCLE = "lifecycle"


@dataclass(frozen=True)
class GeneDefinition:
    name: str
    label: str
    group: GeneGroup
    min: float
    max: float
    default: float
    gene_type: GeneType = GeneType.FLOAT
    description: str = ""
    # Constraint function: (value, genome_dict) -> corrected value
    # Called AFTER bounds clamping, in registration order
    constraint: Optional[Callable[[float, dict], float]] = field(
        default=None, repr=False, compare=False
    )


class GeneRegistry:
    """Registry of all gene definitions. Iterated in registration order."""

    def __init__(self) -> None:
        self._genes: dict[str, GeneDefinition] = {}
        self._order: list[str] = []

    def register(self, gene: GeneDefinition) -> None:
        if gene.name in self._genes:
            raise ValueError(f"Gene '{gene.name}' already registered")
        self._genes[gene.name] = gene
        self._order.append(gene.name)

    def get(self, name: str) -> GeneDefinition:
        return self._genes[name]

    def has(self, name: str) -> bool:
        return name in self._genes

    def all_genes(self) -> list[GeneDefinition]:
        return [self._genes[n] for n in self._order]

    def numeric_gene_names(self) -> list[str]:
        return list(self._order)

    def gene_bounds(self) -> dict[str, tuple[float, float]]:
        """Backward-compatible dict matching the old GENE_BOUNDS format."""
        return {g.name: (g.min, g.max) for g in self.all_genes()}

    def gene_labels(self) -> dict[str, str]:
        return {g.name: g.label for g in self.all_genes()}

    def gene_defaults(self) -> dict[str, float]:
        return {g.name: g.default for g in self.all_genes()}

    def by_group(self, group: GeneGroup) -> list[GeneDefinition]:
        return [g for g in self.all_genes() if g.group == group]

    def validate_genome(self, genome_dict: dict[str, float]) -> dict[str, float]:
        """
        Validate a genome dict: clamp to bounds, then run constraints.
        Returns a corrected copy.
        """
        result = dict(genome_dict)

        # Phase 1: Clamp all values to hard bounds
        for gene in self.all_genes():
            if gene.name in result:
                result[gene.name] = max(gene.min, min(gene.max, result[gene.name]))

        # Phase 2: Run constraint functions in registration order
        for gene in self.all_genes():
            if gene.constraint and gene.name in result:
                corrected = gene.constraint(result[gene.name], result)
                # Re-clamp after constraint to guarantee bounds
                result[gene.name] = max(gene.min, min(gene.max, corrected))

        return result

    def to_json_schema(self) -> list[dict[str, Any]]:
        """Export full registry as JSON for the dashboard API endpoint."""
        return [
            {
                "name": g.name,
                "label": g.label,
                "group": g.group.value,
                "min": g.min,
                "max": g.max,
                "default": g.default,
                "type": g.gene_type.value,
                "description": g.description,
            }
            for g in self.all_genes()
        ]


# ══════════════════════════════════════════════════════════════════════════════
# CONSTRAINT FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════


def _ema_fast_constraint(val: float, genome: dict) -> float:
    """ema_fast must be < ema_slow."""
    ema_slow = genome.get("ema_slow", 21.0)
    if val >= ema_slow:
        return max(3.0, ema_slow * 0.5)
    return val


def _rsi_oversold_constraint(val: float, genome: dict) -> float:
    """rsi_oversold must be < rsi_overbought, with at least 10 gap."""
    overbought = genome.get("rsi_overbought", 70.0)
    if val >= overbought - 5:
        return max(20.0, overbought - 15)
    return val


def _stop_loss_constraint(val: float, genome: dict) -> float:
    """stop_loss_pct must be < take_profit_pct."""
    tp = genome.get("take_profit_pct", 0.07)
    if val >= tp:
        return max(0.01, tp * 0.4)
    return val


# ══════════════════════════════════════════════════════════════════════════════
# REGISTER ALL GENES
# ══════════════════════════════════════════════════════════════════════════════

GENE_REGISTRY = GeneRegistry()

# ── Signal genes ─────────────────────────────────────────────────────────────

GENE_REGISTRY.register(GeneDefinition(
    name="rsi_period",
    label="RSI Period",
    group=GeneGroup.SIGNAL,
    min=5, max=30, default=14.0,
    gene_type=GeneType.INT,
    description="Number of candles used to compute the Relative Strength Index.",
))

GENE_REGISTRY.register(GeneDefinition(
    name="rsi_oversold",
    label="RSI Oversold",
    group=GeneGroup.SIGNAL,
    min=20, max=45, default=32.0,
    description="RSI threshold below which an asset is considered oversold (buy signal).",
    constraint=_rsi_oversold_constraint,
))

GENE_REGISTRY.register(GeneDefinition(
    name="rsi_overbought",
    label="RSI Overbought",
    group=GeneGroup.SIGNAL,
    min=55, max=85, default=70.0,
    description="RSI threshold above which an asset is considered overbought (sell signal).",
))

GENE_REGISTRY.register(GeneDefinition(
    name="ema_fast",
    label="EMA Fast",
    group=GeneGroup.SIGNAL,
    min=3, max=20, default=9.0,
    gene_type=GeneType.INT,
    description="Period of the fast Exponential Moving Average. Must be less than EMA Slow.",
    constraint=_ema_fast_constraint,
))

GENE_REGISTRY.register(GeneDefinition(
    name="ema_slow",
    label="EMA Slow",
    group=GeneGroup.SIGNAL,
    min=10, max=60, default=21.0,
    gene_type=GeneType.INT,
    description="Period of the slow Exponential Moving Average.",
))

GENE_REGISTRY.register(GeneDefinition(
    name="volume_threshold",
    label="Volume Threshold",
    group=GeneGroup.SIGNAL,
    min=1.0, max=3.0, default=1.4,
    description="Multiplier of average volume required to confirm entry signal.",
))

# ── Risk genes ───────────────────────────────────────────────────────────────

GENE_REGISTRY.register(GeneDefinition(
    name="position_size_pct",
    label="Position Size %",
    group=GeneGroup.RISK,
    min=0.05, max=0.30, default=0.15,
    description="Fraction of capital allocated per trade.",
))

GENE_REGISTRY.register(GeneDefinition(
    name="stop_loss_pct",
    label="Stop Loss %",
    group=GeneGroup.RISK,
    min=0.01, max=0.10, default=0.03,
    description="Maximum loss percentage before a position is automatically closed.",
    constraint=_stop_loss_constraint,
))

GENE_REGISTRY.register(GeneDefinition(
    name="take_profit_pct",
    label="Take Profit %",
    group=GeneGroup.RISK,
    min=0.03, max=0.20, default=0.07,
    description="Target profit percentage to automatically close a winning position.",
))

GENE_REGISTRY.register(GeneDefinition(
    name="max_open_positions",
    label="Max Positions",
    group=GeneGroup.RISK,
    min=1, max=4, default=2.0,
    gene_type=GeneType.INT,
    description="Maximum number of simultaneous open positions.",
))

# ── Lifecycle genes ──────────────────────────────────────────────────────────

GENE_REGISTRY.register(GeneDefinition(
    name="timeframe_minutes",
    label="Timeframe (min)",
    group=GeneGroup.LIFECYCLE,
    min=5, max=60, default=15.0,
    gene_type=GeneType.INT,
    description="Candle timeframe in minutes for signal computation.",
))

GENE_REGISTRY.register(GeneDefinition(
    name="benchmark_target_pct",
    label="Reproduce At %",
    group=GeneGroup.LIFECYCLE,
    min=0.03, max=0.15, default=0.08,
    description="Minimum ROI percentage required for a probe to be eligible for reproduction.",
))

GENE_REGISTRY.register(GeneDefinition(
    name="death_drawdown_pct",
    label="Death Drawdown %",
    group=GeneGroup.LIFECYCLE,
    min=0.10, max=0.35, default=0.20,
    description="Maximum drawdown percentage before a probe dies.",
))

GENE_REGISTRY.register(GeneDefinition(
    name="num_assets",
    label="# Assets",
    group=GeneGroup.LIFECYCLE,
    min=1, max=3, default=2.0,
    gene_type=GeneType.INT,
    description="Number of trading pairs the probe monitors simultaneously.",
))
