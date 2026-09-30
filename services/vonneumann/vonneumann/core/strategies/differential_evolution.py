"""DE/rand/1/bin with paired target/trial accounts on each common market window.

The configured population is the actual funded evaluation-account count, 2*N.
The first completed batch seeds N incumbents. Subsequent batches evaluate N
incumbent clones and N trials concurrently before selecting paired winners.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from ..evolution import mutate_assets
from ..gene_registry import GENE_REGISTRY
from ..genome import Genome
from ..search_random import private_rng
from .base import EvolutionResult, EvolutionStrategy
from .cohort_contract import SelectionCohort, preserve_fixed_controls

if TYPE_CHECKING:
    from ..colony_config import ColonyConfig
    from ..probe import Probe

NUMERIC_GENES = GENE_REGISTRY.numeric_gene_names()


class DifferentialEvolutionStrategy(EvolutionStrategy):
    supports_cohorts = True
    name = "differential_evolution"
    label = "Differential Evolution"
    description = "DE/rand/1/bin with paired target/trial evaluation on common market windows."

    def __init__(self) -> None:
        super().__init__()
        self.F = 0.8
        self.CR = 0.9
        self.min_pop = 4  # Incumbent slots; each requires two funded accounts.
        self._cohort = SelectionCohort()
        self._phase = "uninitialized"
        self._pairs: tuple[tuple[str, str], ...] = ()

    def initialize(self, probes: list[Probe], colony_config: ColonyConfig) -> None:
        if len(probes) < 2 * self.min_pop or len(probes) % 2:
            raise ValueError("Differential Evolution needs an even population of at least eight evaluation accounts")
        self._cohort.initialize(probes)
        self._phase = "bootstrap"
        self._pairs = ()

    def bind_candidates(self, probes: list[Probe]) -> None:
        pending = self._cohort.awaiting_bind
        self._cohort.bind(probes)
        if pending:
            half = len(probes) // 2
            self._pairs = tuple((probes[i].probe_id, probes[i + half].probe_id)
                                for i in range(half))
            self._phase = "paired"

    def abort_cohort(self) -> None:
        self._cohort.abort()
        self._phase = "uninitialized"
        self._pairs = ()

    def evolve(self, probes: list[Probe], dead_probes: list[Probe],
               colony_config: ColonyConfig) -> EvolutionResult:
        evaluated = self._cohort.results(probes)
        half = len(evaluated) // 2
        selections = []
        if self._phase == "bootstrap":
            # Stable ties preserve original bound order, never callback order.
            winners = sorted(evaluated, key=lambda p: p.fitness, reverse=True)[:half]
        elif self._phase == "paired":
            by_id = {p.probe_id: p for p in evaluated}
            if len(self._pairs) != half:
                raise ValueError("DE lost its complete target/trial pairing")
            winners = []
            for slot, (target_id, trial_id) in enumerate(self._pairs):
                target, trial = by_id[target_id], by_id[trial_id]
                accepted = trial.fitness > target.fitness
                winner = trial if accepted else target
                winners.append(winner)
                selections.append({"slot": slot, "target_id": target_id,
                    "trial_id": trial_id, "target_fitness": target.fitness,
                    "trial_fitness": trial.fitness, "accepted_trial": accepted,
                    "winner_id": winner.probe_id})
        else:
            raise ValueError("DE requires an initialized comparison batch")

        # Complete every pairwise decision before proposing any next vector.
        # These winners supply all donors; losing trials cannot influence them.
        frozen = [(p.probe_id, p.genome) for p in winners]
        generation = max(p.genome.generation for p in evaluated) + 1
        targets, trials = [], []
        parent_map, roles = {}, []
        for slot, (target_id, target_genome) in enumerate(frozen):
            target_clone = deepcopy(target_genome)
            target_clone.generation, target_clone.parent_ids = generation, []
            targets.append(target_clone)
            parent_map[str(slot)] = [target_id]
            donors = self._rng.sample([p for p in frozen if p[0] != target_id], 3)
            (a_id, a), (b_id, b), (c_id, c) = donors
            trial_operations = []
            trial = _de_trial(target_genome, a, b, c, self.F, self.CR, colony_config,
                              operations=trial_operations, rng=self._rng,
                              mutation_rng=self.mutation_rng(slot))
            trial.generation = generation
            trials.append(trial)
            trial_index = slot + half
            contributed = trial_operations[0] == "de_rand1bin"
            parent_map[str(trial_index)] = [target_id, a_id, b_id, c_id] if contributed else [target_id]
            donor_roles = {"target": target_id, "base": a_id,
                           "difference_positive": b_id, "difference_negative": c_id}
            roles.append({"slot": slot, "target_index": slot, "trial_index": trial_index,
                "target_source_id": target_id,
                "operation": trial_operations[0], "proposed_donors": donor_roles,
                "trial_contributors": donor_roles if contributed else {"target": target_id}})

        offspring = targets + trials
        metadata = {"selection_policy": "paired-common-window-de-rand1bin-v1",
                    "phase": self._phase, "iteration_id": evaluated[0].iteration_id,
                    "window_started_at": evaluated[0].window_started_at,
                    "window_ends_at": evaluated[0].window_ends_at,
                    "evaluation_accounts": len(evaluated), "incumbent_slots": half,
                    "selected_ids": [p.probe_id for p in winners],
                    "pair_selections": selections, "next_pairs": roles,
                    "fixed_repair_policy": "revert_to_target_if_fixed_control_changes"}
        self._cohort.propose(offspring, evaluated)
        self._mutation_event += 1
        return EvolutionResult(offspring, [p.probe_id for p in evaluated], parent_map, metadata)


def _de_trial(target: Genome, a: Genome, b: Genome, c: Genome,
              F: float, CR: float, colony_config: ColonyConfig, *, operations=None,
              rng=None, mutation_rng=None) -> Genome:
    """Mutate/cross only active dimensions, always forcing one active donor."""
    rng = private_rng(rng)
    active = [name for name in NUMERIC_GENES if colony_config.is_gene_evolvable(name)]
    if not active:
        clone = deepcopy(target)
        clone.generation += 1
        clone.parent_ids = []
        if operations is not None:
            operations.append("no_active_clone")
        return clone
    mandatory = rng.choice(active)
    new_genes = {}
    for name in NUMERIC_GENES:
        if name in active and (name == mandatory or rng.random() < CR):
            new_genes[name] = getattr(a, name) + F * (getattr(b, name) - getattr(c, name))
        else:
            new_genes[name] = getattr(target, name)
    genome = Genome.from_dict({**new_genes, "generation": target.generation + 1})
    genome.assets = mutate_assets(target.assets, colony_config, swap_rate=0.15,
                                  rng=mutation_rng if mutation_rng is not None else rng)
    validated = genome.validate(colony_config)
    repaired = preserve_fixed_controls(validated, target, colony_config)
    if operations is not None:
        operations.append("fixed_repair_clone" if repaired is not validated else "de_rand1bin")
    return repaired
