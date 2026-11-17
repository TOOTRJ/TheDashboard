"""Replayable two-EMA paper transitions with an explicit durable journal boundary.

The mathematical kernel remains a pure calculation.  This controller advances
its owned model only after reading the exact original journal entry back.  The
caller supplies authenticated storage and immutable source-artifact readers;
this module never acquires credentials or treats a digest as authentication.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import hashlib
from typing import Callable, Iterable, Protocol

from ..market import provider_acquisition_v3 as acquisition
from ..market import prospective_source_v3 as source
from ..research import numeric_wire
from ..research import prospective_ga_v3_model as model
from ..research.prospective_ga_v3_policy import V3Config, V3Inputs, SourceBinding

FORMAT = 'dashboard-prospective-paper-journal-v1'
MAX_ENTRY_BYTES = 512 * 1024


class RuntimeRefused(RuntimeError):
    """Fixed diagnostics only; provider and database exception text stays private."""


class RuntimePending(RuntimeRefused):
    """The original append may have committed; reconcile its original identity."""


class JournalRejected(RuntimeRefused):
    """Authenticated immutable native rejection of this exact original entry.

    A negative lookup or ordinary SQL/network exception cannot construct this
    outcome in the transport. The original rejected wire is required so the
    controller can prove which retained candidate is permanently barred.
    """
    def __init__(self, wire: bytes, reason='stop_committed'):
        if type(wire) is not bytes or reason != 'stop_committed':
            raise RuntimeRefused('invalid_original_rejection')
        self.wire, self.reason = wire, reason
        super().__init__('original_transition_rejected_stop_committed')


def _require(condition):
    if not condition:
        raise RuntimeRefused('invalid_prospective_journal')


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _encoded(value):
    return acquisition.read_json(numeric_wire.encode(value), numeric_wire.MAX_BYTES, exact=True)


def _decoded(value):
    return numeric_wire.decode(acquisition.canonical(value))


def _inputs(value):
    row = _decoded(value)
    _require(type(row) is dict and set(row) == {'event_us', 'clock', 'ids', 'names'})
    return V3Inputs(acquisition.ClockBound(**row['clock']), row['event_us'],
        tuple(row['ids']), tuple(tuple(pair) for pair in row['names']))


@dataclass(frozen=True, slots=True)
class JournalEntry:
    wire: bytes

    def __post_init__(self):
        row = acquisition.read_json(self.wire, MAX_ENTRY_BYTES, exact=True)
        _require(type(row) is dict and set(row) == {'format', 'owner_id', 'run_id',
            'command_id', 'sequence', 'previous_sha256', 'witness', 'candidate_sha256',
            'candidate_wire'})
        _require(row['format'] == FORMAT)
        for field in ('owner_id', 'run_id', 'command_id'):
            acquisition.uuid(row[field])
        acquisition.counter(row['sequence'], minimum=1)
        if row['previous_sha256'] is not None:
            acquisition.digest(row['previous_sha256'])
        acquisition.digest(row['candidate_sha256'])
        candidate = row['candidate_wire'].encode('utf-8')
        _require(_digest(candidate) == row['candidate_sha256'])
        # The existing bounded numeric decoder independently validates the
        # original model command, including exact integer/binary64 encodings.
        numeric_wire.decode(candidate)
        _require(type(row['witness']) is dict)

    @property
    def sha256(self):
        return _digest(self.wire)

    def to_dict(self):
        return acquisition.read_json(self.wire, MAX_ENTRY_BYTES, exact=True)


class TransitionJournal(Protocol):
    async def append(self, entry: JournalEntry, *, expected_sequence: int,
                     expected_sha256: str | None) -> JournalEntry: ...
    async def get(self, command_id: str) -> JournalEntry | None: ...


class SourceArtifacts(Protocol):
    """Resolve by original durable scope and digest, never from request DTOs."""
    def __call__(self, kind: str, sha256: str): ...


def _source(artifacts, kind, sha256):
    acquisition.digest(sha256)
    artifact = artifacts(kind, sha256)
    expected = {'mark': source.SourceMark, 'history': source.SampledHistory,
                'series': source.SampledCloseSeries}[kind]
    _require(type(artifact) is expected and artifact.sha256 == sha256)
    return artifact


def _witness(candidate):
    original = candidate._witness
    kind = original['kind']
    row = {'kind': kind, 'inputs': _encoded(original['inputs'].to_dict())}
    if kind == 'bootstrap':
        row['config'] = _encoded(original['config'].to_dict())
    elif kind == 'epoch_rollover':
        row['successor_binding'] = original['successor_binding'].to_dict()
    elif kind == 'control':
        row.update(action=original['action'], trip_id=original['trip_id'])
    if kind != 'epoch_rollover':
        for role in ('mark', 'history', 'series'):
            artifact = original.get(role)
            row[role + '_sha256'] = None if artifact is None else artifact.sha256
        _require(original.get('expected_mark_sha256') == row['mark_sha256']
            and original.get('expected_history_sha256') == row['history_sha256'])
    return row


def _replay(row, state, ledger, artifacts):
    witness = row['witness']
    kind, inputs = witness['kind'], _inputs(witness['inputs'])
    common = {'kind', 'inputs'}
    if kind == 'epoch_rollover':
        _require(set(witness) == common | {'successor_binding'})
        return model.prepare_epoch_rollover(state,
            SourceBinding(**witness['successor_binding']), inputs, ledger=ledger)
    _require(kind in {'bootstrap', 'protective', 'decision', 'control'})
    allowed = common | {'mark_sha256', 'history_sha256', 'series_sha256'}
    allowed |= {'config'} if kind == 'bootstrap' else {'action', 'trip_id'} if kind == 'control' else set()
    _require(set(witness) == allowed)
    resolved = {role: None if witness[role + '_sha256'] is None else
        _source(artifacts, role, witness[role + '_sha256'])
        for role in ('mark', 'history', 'series')}
    if kind == 'bootstrap':
        _require(state is None and resolved['mark'] is None)
        return model.bootstrap(V3Config.from_dict(_decoded(witness['config'])),
            resolved['history'], resolved['series'],
            expected_history_sha256=witness['history_sha256'], inputs=inputs, ledger=ledger)
    arguments = dict(expected_mark_sha256=witness['mark_sha256'], inputs=inputs, ledger=ledger)
    if kind == 'protective':
        _require(resolved['history'] is None and resolved['series'] is None)
        return model.prepare_protective(state, resolved['mark'], **arguments)
    arguments.update(history=resolved['history'], series=resolved['series'],
        expected_history_sha256=witness['history_sha256'])
    if kind == 'decision':
        return model.prepare_decision(state, resolved['mark'], **arguments)
    return model.prepare_control(state, witness['action'], mark=resolved['mark'],
        trip_id=witness['trip_id'], **arguments)


class ProspectiveRuntime:
    """One owner/run and one retained append; restart uses independent replay.

    The journal must enforce compare-and-swap, owner scope, immutable command
    identity, transactional history retention and fencing.  A network failure or
    absent readback never authorizes a fresh command or assumed rollback.
    """
    def __init__(self, owner_id, run_id, journal: TransitionJournal,
                 artifacts: SourceArtifacts):
        acquisition.uuid(owner_id); acquisition.uuid(run_id)
        self.owner_id, self.run_id = owner_id, run_id
        self._journal, self._artifacts = journal, artifacts
        self._ledger = model.OfflineLedger(owner_id, run_id)
        self._state = None
        self._sequence, self._head_sha256 = 0, None
        self._pending = None
        self._busy = False
        self._restoring = False

    @property
    def state(self):
        return self._state

    @property
    def sequence(self):
        return self._sequence

    @property
    def head_sha256(self):
        return self._head_sha256

    @property
    def pending(self):
        return self._pending is not None

    @property
    def history(self):
        return self._ledger.history

    def _idle(self):
        if self._pending is not None or self._busy:
            raise RuntimePending('original_transition_unresolved')

    def restore(self, entries: Iterable[JournalEntry]):
        """Replay a complete ordered original prefix before new work is allowed.

        A failed restore leaves this instance unusable; construct a fresh
        instance and re-read the exact durable prefix after correcting storage.
        """
        self.begin_restore()
        try:
            self.restore_page(entries)
        except BaseException:
            # Do not allow continuation from a partially inspected prefix.
            raise RuntimeRefused('restore_failed') from None
        else:
            self.finish_restore()
        return self._state

    def begin_restore(self):
        self._idle()
        _require(self._sequence == 0 and self._state is None)
        self._busy = self._restoring = True

    def restore_page(self, entries: Iterable[JournalEntry]):
        _require(self._restoring and self._busy)
        for entry in entries:
            self._accept(entry)

    def finish_restore(self):
        _require(self._restoring and self._busy)
        self._busy = self._restoring = False
        return self._state

    def _accept(self, entry):
        _require(type(entry) is JournalEntry)
        row = entry.to_dict()
        _require((row['owner_id'], row['run_id']) == (self.owner_id, self.run_id)
            and acquisition.counter(row['sequence']) == self._sequence + 1
            and row['previous_sha256'] == self._head_sha256)
        candidate = _replay(row, self._state, self._ledger, self._artifacts)
        _require(candidate._wire == row['candidate_wire'].encode('utf-8'))
        self._state = self._ledger.accept(candidate)
        # Native command identity/readback provides replay idempotency. Retain
        # only the current kernel memo, not every prior full sealed state. Used
        # identities, acquisition epochs and original assessment history remain.
        # The exact owned OfflineLedger type is required by the pinned kernel;
        # this is cache release, never a state import or economic modification.
        self._ledger._accepted = {candidate._wire: self._state}
        if hasattr(self._artifacts, 'retain'):
            current = self._state.to_dict()['source']
            self._artifacts.retain({(kind, digest) for kind, digest in (
                ('history', current['history_sha256']), ('series', current['close_series_sha256']),
                ('mark', current['last_mark_sha256'])) if digest is not None})
        self._sequence += 1
        self._head_sha256 = entry.sha256
        return self._state

    def prepare_bootstrap(self, config, history, series, *, inputs):
        self._idle()
        _require((config.owner_id, config.run_id) == (self.owner_id, self.run_id))
        return model.bootstrap(config, history, series,
            expected_history_sha256=history.sha256, inputs=inputs, ledger=self._ledger)

    def prepare_protective(self, mark, *, inputs):
        self._idle()
        return model.prepare_protective(self._state, mark,
            expected_mark_sha256=mark.sha256, inputs=inputs, ledger=self._ledger)

    def prepare_decision(self, mark, *, inputs, history=None, series=None):
        self._idle()
        return model.prepare_decision(self._state, mark, expected_mark_sha256=mark.sha256,
            inputs=inputs, ledger=self._ledger, history=history, series=series,
            expected_history_sha256=None if history is None else history.sha256)

    def prepare_observation(self, mark, *, inputs, history=None, series=None):
        """Prepare both paper phases at one genuine pre-I/O decision instant.

        A private shadow validates protection before computing the decision.
        The owned ledger is untouched until each original is durably accepted.
        The caller may discard the decision when Stop intervenes after the first
        append.  Database commit time remains separate from decision time; these
        are simulated reference-mark fills, never executable quotes.
        """
        self._idle()
        protective = self.prepare_protective(mark, inputs=inputs)
        shadow = deepcopy(self._ledger)
        protected = shadow.accept(protective)
        if protected.to_dict()['status'] == 'risk_halted':
            return protective, None
        decision = model.prepare_decision(protected, mark,
            expected_mark_sha256=mark.sha256, inputs=inputs, ledger=shadow,
            history=history, series=series,
            expected_history_sha256=None if history is None else history.sha256)
        return protective, decision

    def prepare_control(self, action, inputs, **arguments):
        self._idle()
        return model.prepare_control(self._state, action, inputs, ledger=self._ledger, **arguments)

    def prepare_epoch_rollover(self, binding, inputs):
        self._idle()
        return model.prepare_epoch_rollover(self._state, binding, inputs, ledger=self._ledger)

    async def submit(self, candidate, *, command_id):
        self._idle()
        acquisition.uuid(command_id)
        _require(type(candidate) is model.V3Candidate)
        candidate.__post_init__()
        after = candidate.state.to_dict()
        _require((after['owner_id'], after['run_id']) == (self.owner_id, self.run_id))
        self._ledger.check(candidate.transition['before'], self.owner_id, self.run_id)
        row = {'format': FORMAT, 'owner_id': self.owner_id, 'run_id': self.run_id,
            'command_id': command_id, 'sequence': str(self._sequence + 1),
            'previous_sha256': self._head_sha256, 'witness': _witness(candidate),
            'candidate_sha256': _digest(candidate._wire),
            'candidate_wire': candidate._wire.decode('utf-8')}
        entry = JournalEntry(acquisition.canonical(row))
        # Prove that the independent original artifact reader can reproduce the
        # candidate before handing an immutable operation to storage.
        replay = _replay(row, self._state, self._ledger, self._artifacts)
        _require(replay._wire == candidate._wire)
        self._pending, self._busy = entry, True
        try:
            original = await self._journal.append(entry, expected_sequence=self._sequence,
                expected_sha256=self._head_sha256)
            return self._finish(original)
        except JournalRejected as error:
            self._reject(error)
        except BaseException:
            # Preserve cancellation as well as unknown database acknowledgments.
            # The caller must reconcile this original command before continuing.
            raise RuntimePending('original_transition_unresolved') from None
        finally:
            self._busy = False

    def _finish(self, original):
        _require(type(original) is JournalEntry and original.wire == self._pending.wire)
        state = self._accept(original)
        self._pending = None
        return state

    def _reject(self, error):
        if (self._pending is None or error.wire != self._pending.wire
            or error.reason != 'stop_committed'):
            raise RuntimePending('original_rejection_mismatch') from None
        self._pending = None
        raise error

    async def reconcile(self):
        if self._busy:
            raise RuntimePending('original_transition_busy')
        _require(self._pending is not None)
        self._busy = True
        try:
            original = await self._journal.get(self._pending.to_dict()['command_id'])
            if original is None:
                raise RuntimePending('original_transition_not_observed')
            return self._finish(original)
        except JournalRejected as error:
            self._reject(error)
        except BaseException:
            raise RuntimePending('original_transition_unresolved') from None
        finally:
            self._busy = False
