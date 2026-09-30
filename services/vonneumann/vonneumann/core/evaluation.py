"""Ordered, immutable candidate results for one common market-time window.

An early protective death leaves the candidate in its original cohort. Its
terminal cash is conceptually held until the common deadline, never replaced
with a new candidate or omitted from an optimizer batch. Interrupted windows
are unscored and must not be sent to an optimizer.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Iterable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .genome import Genome
    from .probe import Probe


EVALUATION_POLICY = {
    "version": "common-market-window-v1",
    "horizon_unit": "market_minutes",
    "warmup": "all_candidates_ready",
    "early_terminal": "freeze_cash_and_score_until_common_deadline",
    "interruptions": "abort_without_tell",
    "deadline_mark": "first_valid_observation_at_or_after_deadline",
}


def _time(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Evaluation time must be finite and nonnegative")
    return float(value)


def _score(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Candidate scores must be finite")
    return float(value)


@dataclass(frozen=True)
class EvaluatedCandidate:
    """Read-only strategy input, independent of retained mutable probe records."""

    probe_id: str
    evaluation_id: str
    iteration_id: str
    _genome: Genome
    fitness: Optional[float]
    roi: Optional[float]
    num_trades: int
    reason: str
    status: str
    window_started_at: Optional[float]
    window_ends_at: Optional[float]
    terminated_at: float
    cohort_complete: bool = False

    @property
    def genome(self) -> Genome:
        # Genome remains mutable elsewhere; never expose the cohort's copy.
        return deepcopy(self._genome)

    def to_dict(self) -> dict:
        return {"probe_id": self.probe_id, "evaluation_id": self.evaluation_id,
                "iteration_id": self.iteration_id, "fitness": self.fitness,
                "roi": self.roi, "num_trades": self.num_trades,
                "reason": self.reason, "status": self.status,
                "cohort_complete": self.cohort_complete,
                "window_started_at": self.window_started_at,
                "window_ends_at": self.window_ends_at, "terminated_at": self.terminated_at}


class EvaluationCohort:
    """Exactly one terminal result per original member, in original order."""

    def __init__(self, iteration_id: str, probes: Iterable[Probe], horizon_seconds: float):
        members = list(probes)
        ids = [p.probe_id for p in members]
        if (not isinstance(iteration_id, str) or not iteration_id or not members or
                any(not isinstance(pid, str) or not pid for pid in ids) or len(ids) != len(set(ids))):
            raise ValueError("A cohort needs a unique, nonempty ordered membership")
        self.horizon_seconds = _time(horizon_seconds)
        if self.horizon_seconds <= 0:
            raise ValueError("Evaluation horizon must be positive")
        self.iteration_id = iteration_id
        self.member_ids = tuple(ids)
        self._genomes = {p.probe_id: deepcopy(p.genome) for p in members}
        self._evaluation_ids = {pid: f"{iteration_id}:{index}" for index, pid in enumerate(ids)}
        self._evaluations: dict[str, EvaluatedCandidate] = {}
        self.phase = "warming"
        self.started_at: Optional[float] = None
        self.ends_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.abort_reason: Optional[str] = None

    @property
    def evaluations(self) -> tuple[EvaluatedCandidate, ...]:
        return tuple(self._evaluations[pid] for pid in self.member_ids if pid in self._evaluations)

    def start(self, at: float) -> None:
        if self.phase != "warming":
            raise ValueError("Evaluation window has already started or terminated")
        started_at = _time(at)
        ends_at = _time(started_at + self.horizon_seconds)
        if ends_at <= started_at:
            raise ValueError("Evaluation horizon is not representable at this time")
        self.started_at, self.ends_at = started_at, ends_at
        self.phase = "evaluating"

    def due(self, at: float) -> bool:
        stamp = _time(at)
        return self.phase == "evaluating" and self.ends_at is not None and stamp >= self.ends_at

    def _snapshot(self, probe: Probe, reason: str, at: float) -> EvaluatedCandidate:
        pid = probe.probe_id
        if pid not in self._genomes:
            raise ValueError("Candidate is not a member of this cohort")
        if self.phase != "evaluating" or self.started_at is None or at < self.started_at:
            raise ValueError("Candidate cannot complete outside an active evaluation window")
        if probe.genome.to_dict() != self._genomes[pid].to_dict():
            raise ValueError("Candidate phenotype changed during its evaluation")
        if not isinstance(reason, str) or not reason:
            raise ValueError("Candidate completion requires a reason")
        count = probe.num_trades
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("Candidate trade count is invalid")
        return EvaluatedCandidate(
            pid, self._evaluation_ids[pid], self.iteration_id, deepcopy(self._genomes[pid]),
            _score(probe.fitness), _score(probe.roi), count, reason, "completed",
            self.started_at, self.ends_at, at)

    def record_terminal(self, probe: Probe, reason: str, at: float) -> EvaluatedCandidate:
        stamp = _time(at)
        if probe.probe_id in self._evaluations:
            raise ValueError("Candidate already has a terminal evaluation")
        result = self._snapshot(probe, reason, stamp)
        self._evaluations[probe.probe_id] = result
        return result

    def complete(self, probes: Iterable[Probe], at: float) -> tuple[EvaluatedCandidate, ...]:
        stamp = _time(at)
        if not self.due(stamp):
            raise ValueError("Cohort is not due for completion")
        members = list(probes)
        by_id = {p.probe_id: p for p in members}
        if len(by_id) != len(members) or not set(by_id).issubset(self._genomes):
            raise ValueError("Completion contains duplicate or foreign candidates")
        missing = set(self.member_ids) - self._evaluations.keys()
        if not missing.issubset(by_id):
            raise ValueError("Completion must account for every original candidate")
        # Validate the entire remaining batch before recording any new result.
        additions = {pid: self._snapshot(by_id[pid], "window_complete", stamp)
                     for pid in self.member_ids if pid in missing}
        completed = {**self._evaluations, **additions}
        # Individually terminal members are not a completed optimizer batch.
        # Grant completion only after every member and the common deadline pass.
        self._evaluations = {pid: replace(result, cohort_complete=True)
                             for pid, result in completed.items()}
        self.completed_at = stamp
        self.phase = "completed"
        return self.evaluations

    def abort(self, reason: str, at: float) -> None:
        stamp = _time(at)
        if self.phase in {"completed", "aborted"}:
            raise ValueError("Cohort has already terminated")
        if not isinstance(reason, str) or not reason:
            raise ValueError("Aborted evaluation requires a reason")
        if self.started_at is not None and stamp < self.started_at:
            raise ValueError("Abort cannot predate the evaluation window")
        for pid in self.member_ids:
            if pid not in self._evaluations:
                self._evaluations[pid] = EvaluatedCandidate(
                    pid, self._evaluation_ids[pid], self.iteration_id, deepcopy(self._genomes[pid]),
                    None, None, 0, reason, "aborted", self.started_at, self.ends_at, stamp)
        self.phase, self.abort_reason, self.completed_at = "aborted", reason, stamp

    def to_dict(self) -> dict:
        return {"policy": dict(EVALUATION_POLICY), "iteration_id": self.iteration_id,
                "phase": self.phase, "member_ids": list(self.member_ids),
                "member_count": len(self.member_ids),
                "completed_count": sum(result.status == "completed" for result in self.evaluations),
                "horizon_seconds": self.horizon_seconds, "started_at": self.started_at,
                "ends_at": self.ends_at, "completed_at": self.completed_at,
                "abort_reason": self.abort_reason,
                "evaluations": [result.to_dict() for result in self.evaluations]}
