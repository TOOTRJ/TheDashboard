"""
Evolution utilities — fitness scoring, mutation, and diversity measurement.

GA-specific operators (selection, crossover, reproduce) live in
strategies/genetic_algorithm.py. This module contains shared utilities
used by probe.py, genesis.py, and all strategy implementations.
"""

from __future__ import annotations

import math
import random
from typing import Optional, TYPE_CHECKING

from .gene_registry import GENE_REGISTRY
from .genome import Genome, AVAILABLE_ASSETS, random_genome

if TYPE_CHECKING:
    from .colony_config import ColonyConfig
    from .probe import Probe

NUMERIC_GENES = GENE_REGISTRY.numeric_gene_names()


# ══════════════════════════════════════════════════════════════════════════════
# FITNESS SCORING
# ══════════════════════════════════════════════════════════════════════════════


def compute_fitness(
    roi: float,
    sharpe: float,
    max_drawdown: float,
    num_trades: int,
    win_rate: float,
) -> float:
    """
    Composite fitness: ROI + (Sharpe*0.3) - (DD*2.0) - activity_penalty + win_bonus.
    This is now used for SELECTION, not just reporting.
    """
    if num_trades < 3:
        return roi - 0.5

    roi_score = roi
    sharpe_score = sharpe * 0.3
    drawdown_penalty = max_drawdown * 2.0
    activity_penalty = max(0, (10 - num_trades) * 0.01)
    win_bonus = (win_rate - 0.5) * 0.1

    return round(
        roi_score + sharpe_score - drawdown_penalty - activity_penalty + win_bonus, 6
    )


def compute_sharpe(returns: list[float], risk_free: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance) if variance > 0 else 1e-9
    return (mean - risk_free) / std


# ══════════════════════════════════════════════════════════════════════════════
# MUTATION (shared utility — used by GA strategy, diversity injection, auto-spawn)
# ══════════════════════════════════════════════════════════════════════════════


def mutate(
    genome: Genome,
    mutation_rate: float = 0.20,
    mutation_strength: float = 0.15,
    colony_config: Optional[ColonyConfig] = None,
) -> Genome:
    """
    Gaussian mutation. Only mutates evolvable genes.
    Fixed/disabled genes are untouched.
    """
    for gene_name in NUMERIC_GENES:
        evolvable = colony_config.is_gene_evolvable(gene_name) if colony_config else True
        if not evolvable:
            continue

        if random.random() < mutation_rate:
            gene_def = GENE_REGISTRY.get(gene_name)
            gene_range = gene_def.max - gene_def.min
            noise = random.gauss(0, mutation_strength * gene_range)
            current = getattr(genome, gene_name)
            setattr(genome, gene_name, current + noise)

    # Asset mutation (in-place swap, ~30% rate)
    genome.assets = mutate_assets(genome.assets, colony_config, swap_rate=0.30)

    return genome.validate(colony_config)


def mutate_assets(
    assets: list[str],
    colony_config: Optional[ColonyConfig] = None,
    swap_rate: float = 0.15,
) -> list[str]:
    """Return a copy of `assets` with a small chance of swapping one entry.

    Lightweight helper used by strategies that don't go through the full
    `mutate()` pipeline (DE, PSO, CMA-ES) but still want their offspring to
    explore the asset space.
    """
    if not assets or random.random() >= swap_rate:
        return list(assets)
    effective_assets = (
        colony_config.get_effective_assets() if colony_config else AVAILABLE_ASSETS
    )
    candidates = [a for a in effective_assets if a not in assets]
    if not candidates:
        return list(assets)
    result = list(assets)
    result[random.randrange(len(result))] = random.choice(candidates)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# DIVERSITY
# ══════════════════════════════════════════════════════════════════════════════


def genome_distance(a: Genome, b: Genome) -> float:
    """Euclidean distance in normalized gene space."""
    total = 0.0
    for gene_name in NUMERIC_GENES:
        gene_def = GENE_REGISTRY.get(gene_name)
        gene_range = gene_def.max - gene_def.min or 1.0
        a_norm = (getattr(a, gene_name) - gene_def.min) / gene_range
        b_norm = (getattr(b, gene_name) - gene_def.min) / gene_range
        total += (a_norm - b_norm) ** 2

    # Asset distance (Jaccard)
    a_set, b_set = set(a.assets), set(b.assets)
    union = a_set | b_set
    if union:
        asset_dist = 1 - len(a_set & b_set) / len(union)
        total += asset_dist ** 2

    return math.sqrt(total)


def population_diversity(genomes: list[Genome]) -> float:
    if len(genomes) < 2:
        return 1.0
    distances = []
    for i, a in enumerate(genomes):
        for b in genomes[i + 1 :]:
            distances.append(genome_distance(a, b))
    return sum(distances) / len(distances)


def inject_diversity_genomes(
    genomes: list[Genome],
    current_generation: int,
    dead_probes: Optional[list] = None,
    colony_config: Optional[ColonyConfig] = None,
    count: int = 2,
) -> list[Genome]:
    """
    Create `count` diversity-injection genomes.
    Prefers strongly-mutated copies of the best dead probe.
    Falls back to random Gen-0 genomes.
    """
    injected: list[Genome] = []
    for _ in range(count):
        if dead_probes:
            best_dead = max(dead_probes[-50:], key=lambda p: p.fitness)
            child = Genome(
                **{g: getattr(best_dead.genome, g) for g in NUMERIC_GENES},
                assets=list(best_dead.genome.assets),
                generation=current_generation,
                parent_ids=[best_dead.probe_id],
            )
            child = mutate(
                child,
                mutation_rate=0.30,
                mutation_strength=0.25,
                colony_config=colony_config,
            )
            injected.append(child)
        else:
            injected.append(
                random_genome(
                    generation=current_generation, colony_config=colony_config
                )
            )
    return injected


def inject_diversity(
    population: list[Genome],
    current_generation: int,
    diversity_threshold: float = 0.10,
    inject_count: int = 2,
    dead_probes: Optional[list] = None,
    colony_config: Optional[ColonyConfig] = None,
) -> list[Genome]:
    """Deprecated: use inject_diversity_genomes() instead.
    Kept for backward compatibility during transition."""
    diversity = population_diversity(population)
    if diversity >= diversity_threshold:
        return []
    return inject_diversity_genomes(
        population, current_generation, dead_probes, colony_config, inject_count
    )
