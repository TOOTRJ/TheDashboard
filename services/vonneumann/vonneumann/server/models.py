"""Validated, bounded input for paper and simulation colonies."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.colony_config import ColonyConfig, GeneOverride, PRESET_CONFIGS
from ..core.gene_registry import GENE_REGISTRY
from ..core.genome import AVAILABLE_ASSETS
from ..core.strategies import list_strategies


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class RecoverRequest(StrictModel):
    trip_id: str = Field(min_length=36, max_length=36,
                         pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

    @field_validator("trip_id")
    @classmethod
    def canonical_trip_id(cls, value: str) -> str:
        return value.lower()


class GeneOverrideModel(StrictModel):
    min: Optional[float] = None
    max: Optional[float] = None
    default: Optional[float] = None
    fixed: Optional[float] = None


class ColonyConfigModel(StrictModel):
    gene_overrides: Optional[dict[str, GeneOverrideModel]] = Field(default=None, max_length=15)
    enabled_genes: Optional[list[str]] = Field(default=None, max_length=15)
    available_assets: Optional[list[str]] = Field(default=None, min_length=1, max_length=8)
    max_lifespan_ticks: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    reproduction_interval: Optional[int] = Field(default=None, ge=1, le=1_000_000)

    @field_validator("enabled_genes")
    @classmethod
    def known_genes(cls, value):
        if value is not None and (len(value) != len(set(value)) or
                                  any(not GENE_REGISTRY.has(name) for name in value)):
            raise ValueError("Enabled genes must be unique registered genes")
        return value

    @field_validator("available_assets")
    @classmethod
    def known_assets(cls, value):
        if value is not None and (len(value) != len(set(value)) or
                                  any(name not in AVAILABLE_ASSETS for name in value)):
            raise ValueError("Assets must be unique supported assets")
        return value

    @field_validator("gene_overrides")
    @classmethod
    def registered_overrides(cls, value):
        if value is not None and any(not GENE_REGISTRY.has(name) for name in value):
            raise ValueError("Overrides must use registered genes")
        return value


class StartRequest(StrictModel):
    mode: Literal["simulation", "paper"] = "simulation"
    strategy: str = Field(default="genetic_algorithm", min_length=1, max_length=64)
    preset: Optional[str] = Field(default=None, max_length=64)
    colony_config: Optional[ColonyConfigModel] = None
    max_probes: int = Field(default=50, ge=2, le=100)
    max_capital: float = Field(default=10_000.0, ge=10, le=1_000_000_000)
    seed_capital: float = Field(default=100.0, ge=10, le=1_000_000_000)
    gen0_count: int = Field(default=10, ge=2, le=50)
    tick_interval_ms: int = Field(default=1000, ge=100, le=60_000)
    mutation_rate: Optional[float] = Field(default=None, ge=0, le=0.5)

    @field_validator("strategy")
    @classmethod
    def known_strategy(cls, value):
        if value not in {strategy["name"] for strategy in list_strategies()}:
            raise ValueError("Strategy is not available")
        return value

    @field_validator("preset")
    @classmethod
    def known_preset(cls, value):
        if value is not None and value not in PRESET_CONFIGS:
            raise ValueError("Preset is not available")
        return value

    @model_validator(mode="after")
    def compatible_configuration(self):
        if self.gen0_count > self.max_probes:
            raise ValueError("Initial population must not exceed the population limit")
        if self.gen0_count * self.seed_capital > self.max_capital:
            raise ValueError("Capital must fund every initial probe")
        if self.strategy == "differential_evolution" and (self.gen0_count < 8 or self.gen0_count % 2):
            raise ValueError("Differential evolution requires an even number of at least eight funded target/trial accounts")
        validate_colony_config(build_colony_config(self))
        return self


def build_colony_config(req: StartRequest) -> ColonyConfig:
    """Copy presets; explicit zero and null overrides retain their meaning."""
    config = (ColonyConfig.from_dict(PRESET_CONFIGS[req.preset].to_dict())
              if req.preset is not None else ColonyConfig())
    custom = req.colony_config
    if custom is not None:
        if custom.gene_overrides is not None:
            for name, override in custom.gene_overrides.items():
                config.gene_overrides[name] = GeneOverride(**override.model_dump())
        for name in ("enabled_genes", "available_assets", "max_lifespan_ticks"):
            if name in custom.model_fields_set:
                setattr(config, name, getattr(custom, name))
        if custom.reproduction_interval is not None:
            config.reproduction_interval = custom.reproduction_interval
    config.mutation_rate = (req.mutation_rate if req.mutation_rate is not None else
                            config.mutation_rate if config.mutation_rate is not None else 0.20)
    return config


def validate_colony_config(config: ColonyConfig) -> None:
    """Use the same domain feasibility checks as construction and all operators."""
    config.resolve_gene_domains()
