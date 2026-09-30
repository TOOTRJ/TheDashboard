"""
Centralized Gene Registry — single source of truth for all gene definitions.

Adding a new gene:
  1. Call GENE_REGISTRY.register(GeneDefinition(...)) at the bottom of this file
  2. Add the field to the Genome dataclass in genome.py
  3. That's it — evolution, validation, config UI, radar chart all auto-discover it

Each gene has a type, hard bounds and default. Resolved domains combine these
with colony controls before deterministic phenotype projection. Coupled
relationships can only adjust active genes inside their configured domains.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
import math


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


GENOME_POLICY = {"version": "configured-phenotype-v1", "integer_rounding": "nearest_half_up",
                 "disabled": "configured_default", "validation": "deterministic_no_rng"}
RELATIONSHIPS = (("ema_fast", "ema_slow"), ("stop_loss_pct", "take_profit_pct"))


def finite_gene(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Gene values must be finite numbers")
    try:
        value = float(value)
    except (OverflowError, ValueError):
        raise ValueError("Gene values must be finite numbers") from None
    if not math.isfinite(value):
        raise ValueError("Gene values must be finite numbers")
    return value


@dataclass(frozen=True)
class GeneDomain:
    minimum: float
    maximum: float
    default: float
    integer: bool

    @property
    def evolvable(self) -> bool:
        return self.minimum < self.maximum


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

    def resolve_domains(self, overrides: dict | None = None,
                        enabled_genes: list[str] | None = None,
                        asset_count: int = 8) -> dict[str, GeneDomain]:
        """Resolve one feasible domain for construction, projection and operators."""
        overrides = {} if overrides is None else overrides
        if (not isinstance(overrides, dict) or any(name not in self._genes for name in overrides) or
                isinstance(asset_count, bool) or not isinstance(asset_count, int) or asset_count < 1):
            raise ValueError("Invalid gene configuration")
        if enabled_genes is not None and (not isinstance(enabled_genes, list) or
                any(not isinstance(name, str) or name not in self._genes for name in enabled_genes) or
                len(enabled_genes) != len(set(enabled_genes))):
            raise ValueError("Enabled genes must be unique registered genes")
        domains = {}
        for gene in self.all_genes():
            override = overrides.get(gene.name, {})
            if not isinstance(override, dict) or set(override) - {"min", "max", "default", "fixed"}:
                raise ValueError("Invalid gene override")
            values = {key: finite_gene(value) for key, value in override.items() if value is not None}
            if any(value < gene.min or value > gene.max for value in values.values()):
                raise ValueError("Gene overrides must stay within registry bounds")
            integer = gene.gene_type == GeneType.INT
            if integer and any(not value.is_integer() for value in values.values()):
                raise ValueError("Integer gene overrides must be whole numbers")
            lo, hi = values.get("min", gene.min), values.get("max", gene.max)
            if lo > hi:
                raise ValueError("Gene minimum must not exceed its maximum")
            if any(not lo <= values[key] <= hi for key in ("fixed", "default") if key in values):
                raise ValueError("Gene fixed and default values must fit the configured range")
            if gene.name == "num_assets":
                hi = min(hi, asset_count)
                if lo > hi or any(values[key] > hi for key in ("fixed", "default") if key in values):
                    raise ValueError("Asset count must fit the available asset pool")
            default = values.get("default", min(hi, max(lo, gene.default)))
            if "fixed" in values:
                lo = hi = default = values["fixed"]
            elif enabled_genes is not None and gene.name not in enabled_genes:
                lo = hi = default
            domains[gene.name] = GeneDomain(lo, hi, default, integer)
        for lower, upper in RELATIONSHIPS:
            if lower in domains and upper in domains and domains[lower].minimum >= domains[upper].maximum:
                raise ValueError("Fixed, disabled and active gene values must permit their required relationships")
        return domains

    def validate_genome(self, genome_dict: dict[str, float],
                        domains: dict[str, GeneDomain] | None = None) -> dict[str, float]:
        """Deterministically project finite values into a feasible phenotype.

        Integer conversion precedes coupled constraints. A zero-width domain is
        immutable, including disabled defaults, explicit fixed and equal bounds.
        """
        if set(genome_dict) != set(self._genes):
            raise ValueError("A genome must contain every registered numeric gene")
        domains = self.resolve_domains() if domains is None else domains
        result = {}
        for gene in self.all_genes():
            value = finite_gene(genome_dict[gene.name])
            domain = domains[gene.name]
            value = min(domain.maximum, max(domain.minimum, value))
            if domain.integer:
                value = float(math.floor(value + 0.5))
            result[gene.name] = value
        for lower, upper in RELATIONSHIPS:
            if lower not in result or upper not in result or result[lower] < result[upper]:
                continue
            lower_domain, upper_domain = domains[lower], domains[upper]
            before = lambda value: value - 1 if lower_domain.integer else math.nextafter(value, -math.inf)
            after = lambda value: value + 1 if upper_domain.integer else math.nextafter(value, math.inf)
            if lower_domain.evolvable:
                result[lower] = max(lower_domain.minimum, min(result[lower], before(result[upper])))
            if result[lower] >= result[upper] and upper_domain.evolvable:
                result[upper] = min(upper_domain.maximum, max(result[upper], after(result[lower])))
            if result[lower] >= result[upper]:
                raise ValueError("Configured gene relationship cannot be preserved")
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
    min=0.05, max=0.90, default=0.75,
    description="Fraction of capital allocated per trade.",
))

GENE_REGISTRY.register(GeneDefinition(
    name="stop_loss_pct",
    label="Stop Loss %",
    group=GeneGroup.RISK,
    min=0.01, max=0.10, default=0.03,
    description="Maximum loss percentage before a position is automatically closed.",
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
    min=1, max=4, default=1.0,
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
    name="reproduce_target_dollars",
    label="Reproduce At $",
    group=GeneGroup.LIFECYCLE,
    min=2.0, max=50.0, default=10.0,
    description="Dollar profit target for reproduction eligibility (OR'd with ROI %).",
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
