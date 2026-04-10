"""
Evolution engine — crossover, mutation, fitness scoring, selection, and diversity.

All functions accept an optional ColonyConfig to respect:
  - enabled_genes: only evolvable genes participate in crossover/mutation
  - gene_overrides: fixed genes are preserved unchanged
  - available_assets: asset crossover respects the restricted pool
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
# SELECTION (NEW — fitness-ranked)
# ══════════════════════════════════════════════════════════════════════════════


def select_parents_by_fitness(
    probes: list[Probe],
    top_pct: float = 0.30,
    min_trades: int = 3,
    min_roi: float = 0.0,
) -> list[Probe]:
    """
    Select top probes by fitness for reproduction.
    Filters: must have >= min_trades and roi >= min_roi (floor).
    Returns the top top_pct% sorted by fitness descending.
    """
    eligible = [
        p for p in probes
        if p.num_trades >= min_trades and p.roi >= min_roi
    ]
    if not eligible:
        return []

    ranked = sorted(eligible, key=lambda p: p.fitness, reverse=True)
    n = max(1, int(len(ranked) * top_pct))
    return ranked[:n]


def tournament_select(probes: list[Probe], k: int = 3) -> Optional[Probe]:
    """Tournament selection: pick k random probes, return the fittest."""
    if not probes:
        return None
    tournament = random.sample(probes, min(k, len(probes)))
    return max(tournament, key=lambda p: p.fitness)


# ══════════════════════════════════════════════════════════════════════════════
# CROSSOVER
# ══════════════════════════════════════════════════════════════════════════════


def crossover(
    parent_a: Genome,
    parent_b: Genome,
    generation: int,
    colony_config: Optional[ColonyConfig] = None,
) -> tuple[Genome, Genome]:
    """
    Uniform crossover. For evolvable genes: 50/50 from either parent.
    For fixed/disabled genes: both children get parent_a's value.
    Asset crossover prefers parental assets.
    """
    child_a_genes: dict[str, float] = {}
    child_b_genes: dict[str, float] = {}

    for gene in NUMERIC_GENES:
        a_val = getattr(parent_a, gene)
        b_val = getattr(parent_b, gene)

        evolvable = colony_config.is_gene_evolvable(gene) if colony_config else True

        if evolvable and random.random() > 0.5:
            child_a_genes[gene] = a_val
            child_b_genes[gene] = b_val
        else:
            child_a_genes[gene] = a_val if not evolvable else b_val
            child_b_genes[gene] = a_val if not evolvable else a_val

    # Asset crossover: prefer parental assets
    effective_assets = (
        colony_config.get_effective_assets() if colony_config else AVAILABLE_ASSETS
    )
    parent_assets = list(set(parent_a.assets + parent_b.assets))
    # Filter to effective assets
    parent_assets = [a for a in parent_assets if a in effective_assets]
    if not parent_assets:
        parent_assets = effective_assets

    def pick_assets(n_gene: float) -> list[str]:
        n = max(1, min(len(parent_assets), int(round(n_gene))))
        return random.sample(parent_assets, min(n, len(parent_assets)))

    child_a = Genome(
        **child_a_genes,
        assets=pick_assets(child_a_genes["num_assets"]),
        generation=generation,
        parent_ids=[],
    )
    child_b = Genome(
        **child_b_genes,
        assets=pick_assets(child_b_genes["num_assets"]),
        generation=generation,
        parent_ids=[],
    )

    return child_a.validate(colony_config), child_b.validate(colony_config)


# ══════════════════════════════════════════════════════════════════════════════
# MUTATION
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

    # Asset mutation: 30% chance to swap one asset
    effective_assets = (
        colony_config.get_effective_assets() if colony_config else AVAILABLE_ASSETS
    )
    if random.random() < 0.30 and genome.assets:
        idx = random.randrange(len(genome.assets))
        candidates = [a for a in effective_assets if a not in genome.assets]
        if candidates:
            genome.assets[idx] = random.choice(candidates)

    return genome.validate(colony_config)


# ══════════════════════════════════════════════════════════════════════════════
# REPRODUCTION
# ══════════════════════════════════════════════════════════════════════════════


def reproduce(
    parent: Genome,
    population: list[Genome],
    num_children: int = 2,
    mutation_rate: float = 0.20,
    colony_config: Optional[ColonyConfig] = None,
) -> list[Genome]:
    """
    Produce children. Sexual (crossover+mutate) or asexual (clone+mutate).
    """
    generation = parent.generation + 1
    children = []
    mates = [g for g in population if g is not parent]

    for _ in range(num_children):
        if mates and random.random() > 0.3:
            mate = random.choice(mates)
            child, _ = crossover(parent, mate, generation, colony_config)
            child = mutate(child, mutation_rate, colony_config=colony_config)
        else:
            child = Genome(
                **{g: getattr(parent, g) for g in NUMERIC_GENES},
                assets=list(parent.assets),
                generation=generation,
                parent_ids=[],
            )
            child = mutate(child, mutation_rate * 1.5, colony_config=colony_config)

        children.append(child)

    return children


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
        for b in genomes[i + 1:]:
            distances.append(genome_distance(a, b))
    return sum(distances) / len(distances)


def inject_diversity(
    population: list[Genome],
    current_generation: int,
    diversity_threshold: float = 0.10,
    inject_count: int = 2,
    dead_probes: Optional[list] = None,
    colony_config: Optional[ColonyConfig] = None,
) -> list[Genome]:
    """
    If diversity is low, inject genomes. Prefers mutated copies of
    best dead probes over random Gen-0.
    """
    diversity = population_diversity(population)
    if diversity >= diversity_threshold:
        return []

    injected: list[Genome] = []
    for _ in range(inject_count):
        if dead_probes:
            # Pick best dead probe and mutate strongly
            best_dead = max(dead_probes, key=lambda p: p.fitness)
            child = Genome(
                **{g: getattr(best_dead.genome, g) for g in NUMERIC_GENES},
                assets=list(best_dead.genome.assets),
                generation=current_generation,
                parent_ids=[best_dead.probe_id],
            )
            child = mutate(child, mutation_rate=0.30, mutation_strength=0.25, colony_config=colony_config)
            injected.append(child)
        else:
            injected.append(random_genome(generation=current_generation, colony_config=colony_config))

    return injected
