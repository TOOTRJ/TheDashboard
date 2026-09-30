"""Strict ordered bindings for selection over completed common-window cohorts."""

from __future__ import annotations

import math
from copy import deepcopy

from ..evaluation import EvaluatedCandidate
from ..gene_registry import GENE_REGISTRY


def candidate_signature(genome) -> dict:
    """Economic phenotype and generation; controller-assigned ancestry is separate."""
    return {**{name: getattr(genome, name) for name in GENE_REGISTRY.numeric_gene_names()},
            "assets": list(genome.assets), "generation": genome.generation}


def _finite(value) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def preserve_fixed_controls(candidate, parent, colony_config):
    """Reject repairs that move a fixed coordinate until the joint codec lands."""
    if colony_config is not None and any(
            not colony_config.is_gene_evolvable(name)
            and getattr(candidate, name) != getattr(parent, name)
            for name in GENE_REGISTRY.numeric_gene_names()):
        # Restoring a fixed value into an invalid coupled phenotype is unsafe.
        clone = deepcopy(parent)
        clone.generation = candidate.generation
        clone.parent_ids = []
        return clone
    return candidate


class SelectionCohort:
    """A proposal consumes one batch and binds exactly one fresh ordered batch."""

    def __init__(self):
        self.abort()

    def abort(self):
        self.population_size = 0
        self.bound_ids = ()
        self._signatures = {}
        self._pending = None
        self._previous_ids = ()
        self._previous_context = None
        self._bootstrap = False

    @property
    def awaiting_bind(self):
        return self._pending is not None

    def initialize(self, probes):
        if self.population_size:
            raise ValueError("Selection strategy already has an initialized cohort")
        members = list(probes)
        ids, signatures = self._identities(members)
        self.population_size = len(members)
        self.bound_ids, self._signatures = ids, dict(zip(ids, signatures))
        self._bootstrap = True

    @staticmethod
    def _identities(probes):
        ids = tuple(p.probe_id for p in probes)
        if (not ids or any(not isinstance(pid, str) or not pid for pid in ids)
                or len(ids) != len(set(ids))):
            raise ValueError("Selection candidates need unique nonempty identities")
        signatures = [candidate_signature(p.genome) for p in probes]
        return ids, signatures

    def bind(self, probes):
        members = list(probes)
        ids, signatures = self._identities(members)
        if len(ids) != self.population_size:
            raise ValueError("Selection binding must preserve the evaluation population")
        if self.awaiting_bind:
            if set(ids).intersection(self._previous_ids):
                raise ValueError("A new evaluation requires fresh candidate accounts")
            if signatures != self._pending:
                raise ValueError("Selection candidates do not match their ordered proposal")
        elif not self._bootstrap:
            raise ValueError("A selection proposal can only be bound once")
        elif ids != self.bound_ids or dict(zip(ids, signatures)) != self._signatures:
            raise ValueError("Bound candidates cannot be replaced before evaluation")
        if self.awaiting_bind:
            self._bootstrap = False
        self.bound_ids, self._signatures = ids, dict(zip(ids, signatures))
        self._pending = None

    def results(self, probes):
        members = list(probes)
        if self.awaiting_bind or not self.bound_ids:
            raise ValueError("Selection results require a bound candidate batch")
        if any(not isinstance(p, EvaluatedCandidate) for p in members):
            raise ValueError("Selection accepts only completed cohort evaluations")
        by_id = {p.probe_id: p for p in members}
        if len(by_id) != len(members) or set(by_id) != set(self.bound_ids):
            raise ValueError("Selection results must cover every bound candidate exactly once")
        contexts, evaluation_ids = set(), set()
        for p in members:
            if (p.status != "completed" or p.cohort_complete is not True
                    or not _finite(p.fitness) or not _finite(p.roi)
                    or isinstance(p.num_trades, bool) or not isinstance(p.num_trades, int)
                    or p.num_trades < 0 or not isinstance(p.reason, str) or not p.reason
                    or not isinstance(p.iteration_id, str) or not p.iteration_id
                    or not isinstance(p.evaluation_id, str) or not p.evaluation_id
                    or not _finite(p.window_started_at) or p.window_started_at < 0
                    or not _finite(p.window_ends_at) or p.window_ends_at <= p.window_started_at
                    or not _finite(p.terminated_at) or p.terminated_at < p.window_started_at
                    or candidate_signature(p.genome) != self._signatures[p.probe_id]):
                raise ValueError("Selection result has invalid evidence or a changed candidate")
            contexts.add((p.iteration_id, p.window_started_at, p.window_ends_at))
            evaluation_ids.add(p.evaluation_id)
        if len(contexts) != 1 or len(evaluation_ids) != len(members):
            raise ValueError("Selection results mix market windows or evaluation identities")
        context = next(iter(contexts))
        if self._previous_context is not None and (
                context[0] == self._previous_context[0] or context[1] < self._previous_context[2]):
            raise ValueError("Selection cannot reuse or overlap the preceding evaluation context")
        return [by_id[pid] for pid in self.bound_ids]

    def propose(self, genomes, evaluated):
        ordered = self.results(evaluated)
        if len(genomes) != self.population_size:
            raise ValueError("Selection proposal must preserve the evaluation population")
        pending = [candidate_signature(g) for g in genomes]
        context = (ordered[0].iteration_id, ordered[0].window_started_at, ordered[0].window_ends_at)
        self._pending = deepcopy(pending)
        self._previous_ids, self._previous_context = self.bound_ids, context
        self.bound_ids, self._signatures = (), {}
