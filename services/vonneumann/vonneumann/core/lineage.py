"""Immutable ancestry plans for the offline exact DB-03A command boundary.

Sources describe algorithm inputs, not equal genetic contribution or CMA
weights. A normalized CMA distribution records its complete ordered evaluation
membership once; children separately identify their asset template. Iteration
IDs are bounded engine text, not UUIDs or database proof of cohort membership.
The current engine, Genome JSON and dashboard remain on their existing lineage
path until the complete persistence cutover. Lineage version 2 adds only an
explicit unscored restart clone; command versions before v4 must reject it.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from uuid import UUID

from .evaluation import EvaluatedCandidate
from .genome import Genome
from .strategies.base import EvolutionResult


STRATEGIES = frozenset({"genetic_algorithm", "differential_evolution", "particle_swarm", "cma_es"})
_ROLES = frozenset({"genetic_parent", "target", "base", "difference_positive",
                    "difference_negative", "particle", "social", "asset_template", "clone_source"})
_CLONES = frozenset({"clone_mutation", "no_active_clone", "fixed_repair_clone"})


class LineageValidationError(ValueError):
    """An ancestry claim is missing, contradictory or not representable."""


def _uuid(value: object) -> str:
    if type(value) is not str:
        raise LineageValidationError("Lineage identities require canonical UUID strings")
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise LineageValidationError("Lineage identities require canonical UUID strings") from None
    return value


def _text(value: object, *, maximum: int = 256) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum or "\x00" in value:
        raise LineageValidationError("Lineage text is missing or outside its bound")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise LineageValidationError("Lineage text must be valid Unicode") from None
    return value


def _integer(value: object, *, minimum: int = 0, maximum: int = 99) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise LineageValidationError("Lineage integer is outside its bound")
    return value


def _keys(value: object, keys: set[str]) -> None:
    if type(value) is not dict or value.keys() != keys:
        raise LineageValidationError("Lineage fields do not match the versioned contract")


def _ids(value: object, *, minimum: int = 1, maximum: int = 100) -> tuple[str, ...]:
    if type(value) not in (list, tuple) or not minimum <= len(value) <= maximum:
        raise LineageValidationError("Lineage membership is incomplete or oversized")
    ids = tuple(_uuid(item) for item in value)
    if len(set(ids)) != len(ids):
        raise LineageValidationError("Lineage membership must contain unique identities")
    return ids


@dataclass(frozen=True, slots=True)
class SourceBinding:
    role: str
    source_id: str
    ordinal: int = 0

    def __post_init__(self) -> None:
        if type(self.role) is not str or self.role not in _ROLES:
            raise LineageValidationError("Unknown ancestry role")
        _uuid(self.source_id)
        _integer(self.ordinal)

    def to_dict(self) -> dict:
        return {"role": self.role, "source_id": self.source_id, "ordinal": self.ordinal}

    @classmethod
    def from_dict(cls, value: object) -> "SourceBinding":
        _keys(value, {"role", "source_id", "ordinal"})
        return cls(**value)


@dataclass(frozen=True, slots=True)
class BirthLineage:
    child_id: str
    strategy: str
    operation: str
    source_iteration_id: str | None
    offspring_index: int | None
    sources: tuple[SourceBinding, ...]
    distribution_id: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        _uuid(self.child_id)
        if type(self.version) is not int or self.version not in (1, 2):
            raise LineageValidationError("Unsupported lineage version")
        if type(self.strategy) is not str or self.strategy not in STRATEGIES:
            raise LineageValidationError("Unknown lineage strategy")
        if type(self.operation) is not str or type(self.sources) is not tuple:
            raise LineageValidationError("Lineage operation and immutable sources are required")
        if any(type(source) is not SourceBinding for source in self.sources):
            raise LineageValidationError("Lineage sources must be typed immutable bindings")
        if any(source.source_id == self.child_id for source in self.sources):
            raise LineageValidationError("A child cannot name itself as an ancestry source")
        if self.version == 2:
            _text(self.source_iteration_id)
            _integer(self.offspring_index)
            if (self.operation != "restart_clone" or self.distribution_id is not None
                    or [(s.role, s.ordinal) for s in self.sources] != [("clone_source", 0), ("asset_template", 0)]
                    or self.sources[0].source_id != self.sources[1].source_id):
                raise LineageValidationError("Restart lineage requires one ordered interrupted phenotype source")
            return
        if self.operation == "founder":
            if self.source_iteration_id is not None or self.offspring_index is not None or self.sources or self.distribution_id is not None:
                raise LineageValidationError("A founder cannot claim evaluated ancestry")
            return
        _text(self.source_iteration_id)
        _integer(self.offspring_index)
        if self.distribution_id is not None:
            _uuid(self.distribution_id)

        pattern: list[tuple[str, int]]
        if self.strategy == "genetic_algorithm":
            if self.operation == "crossover_mutation":
                pattern = [("genetic_parent", 0), ("genetic_parent", 1)]
            elif self.operation in _CLONES:
                pattern = [("genetic_parent", 0)]
            else:
                raise LineageValidationError("Unsupported genetic ancestry operation")
        elif self.strategy == "differential_evolution":
            if self.operation == "de_rand1bin":
                pattern = [(role, 0) for role in ("target", "base", "difference_positive", "difference_negative", "asset_template")]
            elif self.operation in {"target_clone", "no_active_clone", "fixed_repair_clone"}:
                pattern = [("target", 0), ("asset_template", 0)]
            else:
                raise LineageValidationError("Unsupported differential ancestry operation")
        elif self.strategy == "particle_swarm":
            if self.operation not in {"swarm_update", "no_active_clone"}:
                raise LineageValidationError("Unsupported swarm ancestry operation")
            pattern = [("particle", 0)]
            if len(self.sources) == 3 and self.operation == "swarm_update":
                pattern.append(("social", 0))
            pattern.append(("asset_template", 0))
        elif self.operation == "distribution_sample":
            pattern = [("asset_template", 0)]
            if self.distribution_id is None:
                raise LineageValidationError("A CMA sample requires a normalized distribution")
        elif self.operation == "no_active_clone":
            pattern = [("clone_source", 0), ("asset_template", 0)]
        else:
            raise LineageValidationError("Unsupported CMA ancestry operation")
        if [(source.role, source.ordinal) for source in self.sources] != pattern:
            raise LineageValidationError("Ancestry roles, order or cardinality do not match the operation")
        if not (self.strategy == "cma_es" and self.operation == "distribution_sample") and self.distribution_id is not None:
            raise LineageValidationError("Only a CMA sample may reference a distribution")
        ids = [source.source_id for source in self.sources]
        if self.strategy == "genetic_algorithm":
            if len(set(ids)) != len(ids):
                raise LineageValidationError("Genetic parents must be distinct")
        elif len(ids) > 1:
            if ids[-1] != ids[0] or len(set(ids[:-1])) != len(ids[:-1]):
                raise LineageValidationError("Template/source bindings are inconsistent")

    @classmethod
    def founder(cls, child_id: str, strategy: str = "genetic_algorithm") -> "BirthLineage":
        return cls(child_id, strategy, "founder", None, None, ())

    def to_dict(self) -> dict:
        return {"version": self.version, "child_id": self.child_id, "strategy": self.strategy,
                "operation": self.operation, "source_iteration_id": self.source_iteration_id,
                "offspring_index": self.offspring_index, "sources": [source.to_dict() for source in self.sources],
                "distribution_id": self.distribution_id}

    @classmethod
    def from_dict(cls, value: object) -> "BirthLineage":
        _keys(value, {"version", "child_id", "strategy", "operation", "source_iteration_id",
                      "offspring_index", "sources", "distribution_id"})
        if type(value["version"]) is not int or value["version"] not in (1, 2) or type(value["sources"]) is not list or len(value["sources"]) > 5:
            raise LineageValidationError("Unsupported or oversized lineage record")
        return cls(value["child_id"], value["strategy"], value["operation"], value["source_iteration_id"],
                   value["offspring_index"], tuple(SourceBinding.from_dict(source) for source in value["sources"]),
                   value["distribution_id"], value["version"])


@dataclass(frozen=True, slots=True)
class DistributionLineage:
    id: str
    stage: str
    source_iteration_id: str
    previous_distribution_id: str | None
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _uuid(self.id)
        _text(self.source_iteration_id)
        if type(self.source_ids) is not tuple:
            raise LineageValidationError("Distribution membership must be immutable")
        _ids(self.source_ids, minimum=2)
        if self.stage == "bootstrap":
            if self.previous_distribution_id is not None:
                raise LineageValidationError("A bootstrap cannot claim an earlier distribution")
        elif self.stage == "update":
            _uuid(self.previous_distribution_id)
            if self.previous_distribution_id == self.id:
                raise LineageValidationError("Distribution ancestry cannot reference itself")
        else:
            raise LineageValidationError("Unknown distribution stage")

    def to_operation(self) -> dict:
        return {"kind": "distribution", "id": self.id, "stage": self.stage,
                "source_iteration_id": self.source_iteration_id,
                "previous_distribution_id": self.previous_distribution_id,
                "source_ids": list(self.source_ids)}

    @classmethod
    def from_operation(cls, value: object) -> "DistributionLineage":
        _keys(value, {"kind", "id", "stage", "source_iteration_id", "previous_distribution_id", "source_ids"})
        if value["kind"] != "distribution" or type(value["source_ids"]) is not list:
            raise LineageValidationError("Invalid distribution operation")
        return cls(value["id"], value["stage"], value["source_iteration_id"],
                   value["previous_distribution_id"], tuple(value["source_ids"]))


@dataclass(frozen=True, slots=True)
class LineagePlan:
    distribution: DistributionLineage | None
    birth_lineages: tuple[BirthLineage, ...]

    def __post_init__(self) -> None:
        if type(self.birth_lineages) is not tuple or not 1 <= len(self.birth_lineages) <= 100:
            raise LineageValidationError("A plan requires a complete immutable bounded child batch")
        if any(type(child) is not BirthLineage for child in self.birth_lineages):
            raise LineageValidationError("A plan requires typed birth lineage")
        _ids(tuple(child.child_id for child in self.birth_lineages))
        if len({(child.strategy, child.source_iteration_id) for child in self.birth_lineages}) != 1:
            raise LineageValidationError("A replacement must use one strategy and one evaluation iteration")
        if [child.offspring_index for child in self.birth_lineages] != list(range(len(self.birth_lineages))):
            raise LineageValidationError("Child bindings must preserve the complete offspring order")
        if self.distribution is not None:
            if type(self.distribution) is not DistributionLineage:
                raise LineageValidationError("Invalid distribution plan")
            if set(child.child_id for child in self.birth_lineages).intersection(self.distribution.source_ids):
                raise LineageValidationError("Distribution sources cannot be replacement child identities")
            for child in self.birth_lineages:
                if (child.distribution_id != self.distribution.id
                        or child.source_iteration_id != self.distribution.source_iteration_id
                        or child.sources[0].source_id not in self.distribution.source_ids):
                    raise LineageValidationError("Child is not bound to this distribution and template membership")
        elif any(child.distribution_id is not None for child in self.birth_lineages):
            raise LineageValidationError("CMA proposal is missing its distribution operation")

    @property
    def distribution_operation(self) -> dict | None:
        return self.distribution.to_operation() if self.distribution is not None else None


def _finite(value: object) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _completed(evaluated: object, cohort_member_ids: object) -> tuple[list[EvaluatedCandidate], str, tuple]:
    ids = _ids(cohort_member_ids)
    if type(evaluated) not in (list, tuple) or len(evaluated) != len(ids) or any(type(member) is not EvaluatedCandidate for member in evaluated):
        raise LineageValidationError("A complete typed evaluation cohort is required")
    for member in evaluated:
        _uuid(member.probe_id)
    by_id = {member.probe_id: member for member in evaluated}
    if len(by_id) != len(ids) or set(by_id) != set(ids):
        raise LineageValidationError("Evaluations do not match the ordered cohort membership")
    contexts, evaluations = set(), set()
    for member in evaluated:
        _uuid(member.probe_id)
        _text(member.iteration_id)
        _text(member.evaluation_id, maximum=512)
        if (member.status != "completed" or member.cohort_complete is not True
                or not _finite(member.fitness) or not _finite(member.roi)
                or type(member.num_trades) is not int or member.num_trades < 0
                or type(member.reason) is not str or not member.reason
                or not _finite(member.window_started_at) or member.window_started_at < 0
                or not _finite(member.window_ends_at) or member.window_ends_at <= member.window_started_at
                or not _finite(member.terminated_at) or member.terminated_at < member.window_started_at
                or type(member.genome) is not Genome):
            raise LineageValidationError("Completed cohort evidence is invalid")
        contexts.add((member.iteration_id, member.window_started_at, member.window_ends_at))
        evaluations.add(member.evaluation_id)
    if len(contexts) != 1 or len(evaluations) != len(ids):
        raise LineageValidationError("Evaluations mix iterations, windows or evaluation identities")
    context = next(iter(contexts))
    # EvaluationCohort's current identity policy binds each evaluation to its
    # original ordered member slot, even when callbacks arrive in another order.
    if any(by_id[source].evaluation_id != f"{context[0]}:{index}" for index, source in enumerate(ids)):
        raise LineageValidationError("Evaluation identity does not match its ordered cohort member")
    return [by_id[source] for source in ids], context[0], context[1:]


def lineage_plan_from_evolution(
    strategy: str, result: EvolutionResult, evaluated: list[EvaluatedCandidate] | tuple[EvaluatedCandidate, ...],
    child_ids: list[str] | tuple[str, ...], *, cohort_member_ids: list[str] | tuple[str, ...],
    distribution_id: str | None = None, previous_distribution_id: str | None = None,
) -> LineagePlan:
    """Bind every proposed child using complete role metadata and cohort evidence.

    This validates the supplied evidence; it does not create a checkpoint,
    certify an optimizer's numerical weights, mutate a result, or persist data.
    A CMA update requires the caller's explicit preceding distribution identity.
    That identity is asserted provenance, not proof that persisted optimizer
    state produced this update; a future checkpoint boundary must establish it.
    """
    if type(strategy) is not str or strategy not in STRATEGIES or type(result) is not EvolutionResult:
        raise LineageValidationError("Known strategy and typed evolution result required")
    ordered, iteration, window = _completed(evaluated, cohort_member_ids)
    ids = tuple(member.probe_id for member in ordered)
    children = _ids(child_ids)
    if (len(children) != len(ids) or set(children).intersection(ids)
            or type(result.offspring) is not list or len(result.offspring) != len(children)
            or any(type(genome) is not Genome for genome in result.offspring)
            or type(result.retire_ids) is not list or result.retire_ids != list(ids)
            or type(result.parent_map) is not dict or set(result.parent_map) != {str(i) for i in range(len(children))}
            or type(result.metadata) is not dict):
        raise LineageValidationError("Evolution result is incomplete or not bound to this ordered cohort")
    for parents in result.parent_map.values():
        if type(parents) is not list or not set(_ids(parents)).issubset(ids):
            raise LineageValidationError("Evolution ancestry names an unknown or duplicated source")
    metadata = result.metadata
    plans: list[BirthLineage] = []
    distribution = None

    def birth(index: int, operation: str, bindings: list[SourceBinding], parent_ids: list[str], dist: str | None = None):
        if result.parent_map[str(index)] != parent_ids:
            raise LineageValidationError("Flat source list contradicts the typed optimizer roles")
        plans.append(BirthLineage(children[index], strategy, operation, iteration, index, tuple(bindings), dist))

    if strategy == "genetic_algorithm":
        if (metadata.get("selection_policy") != "completed-window-generational-ga-v1"
                or metadata.get("iteration_id") != iteration
                or type(metadata.get("evaluation_accounts")) is not int or metadata["evaluation_accounts"] != len(ids)
                or type(metadata.get("offspring")) is not list or len(metadata["offspring"]) != len(children)):
            raise LineageValidationError("Missing genetic operation evidence")
        for index, item in enumerate(metadata["offspring"]):
            _keys(item, {"offspring_index", "operation", "parent_ids"})
            if type(item["offspring_index"]) is not int or item["offspring_index"] != index or type(item["parent_ids"]) is not list:
                raise LineageValidationError("Genetic offspring order is inconsistent")
            parents = list(_ids(item["parent_ids"], maximum=2))
            birth(index, item["operation"], [SourceBinding("genetic_parent", source, ordinal)
                                             for ordinal, source in enumerate(parents)], parents)
    elif strategy == "differential_evolution":
        size, half = len(ids), len(ids) // 2
        if (size < 8 or size % 2 or metadata.get("selection_policy") != "paired-common-window-de-rand1bin-v1"
                or metadata.get("iteration_id") != iteration
                or type(metadata.get("phase")) is not str
                or metadata.get("phase") not in {"bootstrap", "paired"}
                or type(metadata.get("evaluation_accounts")) is not int or metadata["evaluation_accounts"] != size
                or type(metadata.get("incumbent_slots")) is not int or metadata["incumbent_slots"] != half
                or not _finite(metadata.get("window_started_at")) or not _finite(metadata.get("window_ends_at"))
                or (metadata["window_started_at"], metadata["window_ends_at"]) != window
                or type(metadata.get("next_pairs")) is not list or len(metadata["next_pairs"]) != half):
            raise LineageValidationError("Missing paired differential evolution evidence")
        selected = _ids(metadata.get("selected_ids"), minimum=half, maximum=half)
        if not set(selected).issubset(ids):
            raise LineageValidationError("DE selected sources must be evaluated members")
        decisions = metadata.get("pair_selections")
        if metadata["phase"] == "bootstrap":
            if decisions != [] or selected != tuple(member.probe_id for member in sorted(ordered, key=lambda member: member.fitness, reverse=True)[:half]):
                raise LineageValidationError("DE bootstrap sources contradict its evaluated ranking")
        else:
            if type(decisions) is not list or len(decisions) != half:
                raise LineageValidationError("DE pairwise selection evidence is incomplete")
            by_id = {member.probe_id: member for member in ordered}
            compared = []
            for slot, decision in enumerate(decisions):
                _keys(decision, {"slot", "target_id", "trial_id", "target_fitness", "trial_fitness", "accepted_trial", "winner_id"})
                target, trial = decision["target_id"], decision["trial_id"]
                if (target != ids[slot] or trial != ids[slot + half]
                        or type(decision["slot"]) is not int or decision["slot"] != slot):
                    raise LineageValidationError("DE pair identity is inconsistent")
                accepted = by_id[trial].fitness > by_id[target].fitness
                if (decision["accepted_trial"] is not accepted or decision["winner_id"] != selected[slot]
                        or selected[slot] != (trial if accepted else target)
                        or not _finite(decision["target_fitness"]) or not _finite(decision["trial_fitness"])
                        or decision["target_fitness"] != by_id[target].fitness or decision["trial_fitness"] != by_id[trial].fitness):
                    raise LineageValidationError("DE pairwise result contradicts evaluation evidence")
                compared.extend((target, trial))
            if len(set(compared)) != size or set(compared) != set(ids):
                raise LineageValidationError("DE pair decisions must cover the complete evaluated batch")
        targets, trials = [], []
        for slot, item in enumerate(metadata["next_pairs"]):
            _keys(item, {"slot", "target_index", "trial_index", "target_source_id", "operation", "proposed_donors", "trial_contributors"})
            if (any(type(item[name]) is not int for name in ("slot", "target_index", "trial_index"))
                    or (item["slot"], item["target_index"], item["trial_index"]) != (slot, slot, slot + half)
                    or item["target_source_id"] != selected[slot]):
                raise LineageValidationError("DE next-pair order is inconsistent")
            donors = item["proposed_donors"]
            roles = ("target", "base", "difference_positive", "difference_negative")
            _keys(donors, set(roles))
            donor_ids = _ids([donors[role] for role in roles], minimum=4, maximum=4)
            if donors["target"] != selected[slot] or not set(donor_ids).issubset(selected):
                raise LineageValidationError("DE donors do not match the selected source pool")
            operation = item["operation"]
            if type(operation) is not str or operation not in {"de_rand1bin", "no_active_clone", "fixed_repair_clone"}:
                raise LineageValidationError("Unknown DE trial operation")
            actual = donors if operation == "de_rand1bin" else {"target": selected[slot]}
            if type(item["trial_contributors"]) is not dict or item["trial_contributors"] != actual:
                raise LineageValidationError("Proposed donors are not evidence of actual DE contribution")
            target_sources = [SourceBinding("target", selected[slot]), SourceBinding("asset_template", selected[slot])]
            actual_roles = roles if operation == "de_rand1bin" else ("target",)
            trial_sources = [SourceBinding(role, actual[role]) for role in actual_roles] + [SourceBinding("asset_template", selected[slot])]
            targets.append((slot, "target_clone", target_sources, [selected[slot]]))
            trials.append((slot + half, operation, trial_sources, [actual[role] for role in actual_roles]))
        for arguments in targets + trials:
            birth(*arguments)
    elif strategy == "particle_swarm":
        roles = metadata.get("parent_roles")
        dimensions = _integer(metadata.get("active_dimensions"), maximum=64)
        best = max(ordered, key=lambda member: member.fitness)
        if (metadata.get("lineage_policy") != "numeric_particle_and_social_sources"
                or metadata.get("best_score_iteration_id") != iteration
                or not _finite(metadata.get("global_best_fitness")) or metadata["global_best_fitness"] != best.fitness
                or type(roles) is not dict or set(roles) != {str(i) for i in range(len(children))}):
            raise LineageValidationError("Missing swarm role evidence")
        for index, particle in enumerate(ids):
            item = roles[str(index)]
            _keys(item, {"particle_source_id", "social_source_id"})
            social = item["social_source_id"]
            if item["particle_source_id"] != particle or (social is not None and (social != best.probe_id or social == particle or dimensions == 0)):
                raise LineageValidationError("Swarm source roles contradict the bound cohort")
            parents = [particle] + ([social] if social is not None else [])
            bindings = [SourceBinding("particle", particle)] + ([SourceBinding("social", social)] if social is not None else [])
            bindings.append(SourceBinding("asset_template", particle))
            birth(index, "swarm_update" if dimensions else "no_active_clone", bindings, parents)
    else:
        dimensions = _integer(metadata.get("active_dimensions"), maximum=64)
        if dimensions == 0:
            for index, source in enumerate(ids):
                birth(index, "no_active_clone", [SourceBinding("clone_source", source), SourceBinding("asset_template", source)], [source])
        else:
            if (metadata.get("lineage_policy") != "numeric_distribution_and_asset_template"
                    or type(metadata.get("distribution_source_ids")) is not list or metadata["distribution_source_ids"] != list(ids)):
                raise LineageValidationError("CMA distribution membership must preserve the complete bound order")
            template = _uuid(metadata.get("asset_template_source_id"))
            if template != max(ordered, key=lambda member: member.fitness).probe_id:
                raise LineageValidationError("CMA asset template contradicts evaluated selection")
            generation = _integer(metadata.get("cma_generation"), maximum=2**63 - 1)
            distribution = DistributionLineage(distribution_id, "bootstrap" if generation == 0 else "update",
                                               iteration, previous_distribution_id, ids)
            for index in range(len(children)):
                birth(index, "distribution_sample", [SourceBinding("asset_template", template)], list(ids), distribution.id)
    if distribution is None and (distribution_id is not None or previous_distribution_id is not None):
        raise LineageValidationError("This proposal cannot claim a distribution transition")
    return LineagePlan(distribution, tuple(plans))
