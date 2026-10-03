"""Acknowledged installation and serial outbox delivery for the bounded rehearsal.

Own this coordinator and its repository exclusively on one event loop. It can
start only from an acknowledged fresh v3/v4 creation; it is not a checkpoint
decoder, an adapter for the live controller, or a cross-process restorer.
An injected publisher accepts one stable event identity and must deduplicate
repeated delivery. Its success is relay acceptance, not every browser's receipt.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
import json
from typing import Awaitable, Callable

from ..core.exact_rehearsal import ExactCandidate, ExactState
from .command_protocol import PreparedCommand, canonical_json, bounded_integer
from .command_repository import (CommandRepository, CommandReceipt, CommandTransport,
                                 CommandAdmissionError, CommandBusy, UncertainCommand)


class PublicationError(RuntimeError):
    """Retained delivery needs retry using the same event identity."""


class TransitionCoordinator:
    def __init__(self, repository: CommandRepository, outbox_transport: CommandTransport):
        receipt = repository.last_receipt
        if (repository.busy or repository.pending is not None or receipt is None
                or receipt.command.kind != 'create' or repository.revision != 1
                or repository.status != 'starting' or repository.command_version not in (3, 4)
                or receipt.revision != 1 or receipt.fence != repository.fence):
            raise CommandAdmissionError('coordinator requires an acknowledged fresh v3/v4 run')
        self._repository = repository
        self._transport = outbox_transport
        self._creation = receipt.command
        self._initial_fence = receipt.fence
        self._state: ExactState | None = None
        self._candidate: ExactCandidate | None = None
        self._command: PreparedCommand | None = None
        self._receipt: CommandReceipt | None = None
        self._events: tuple[bytes, ...] = ()
        self._next = 0
        self._awaiting_ack = False
        self._installed = False
        self._admission_baseline = None
        self._open = True
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def installed_state(self):
        return self._state

    @property
    def pending_candidate(self):
        return self._candidate

    @property
    def pending_command(self):
        return self._command

    @property
    def pending_receipt(self):
        return self._receipt

    @property
    def next_event_index(self):
        return self._next

    @property
    def busy(self):
        return self._task is not None or self._repository.busy

    @property
    def accepting(self):
        return (self._open and not self.busy and self._candidate is None
                and self._repository.accepting and self._current())

    def _current(self):
        revision = 1 if self._state is None else self._state.revision
        return (self._repository.revision == revision
                and self._repository.fence == self._initial_fence
                and self._repository.status == ('starting' if self._state is None
                                                 else self._state.to_dict()['status']))

    def close_admission(self):
        """Permanent economic drain; owned work, readback and delivery may settle."""
        self._open = False
        self._repository.close_admission()

    def _idle(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise CommandAdmissionError('coordinator belongs to another event loop')
        if self.busy:
            raise CommandBusy('an owned transition or delivery is still running')

    async def _owned(self, operation, *, unsubmitted=False):
        # The readiness barrier also protects ownership under eager task factories.
        ready = asyncio.get_running_loop().create_future()

        async def run():
            try:
                await ready
                return await operation()
            finally:
                self._task = None

        coroutine = run()
        try:
            task = asyncio.create_task(coroutine)
        except Exception:
            coroutine.close()
            if unsubmitted:
                # The readiness barrier never opened, so no repository call
                # could start. This proves local rejection, not DB rollback.
                self._clear()
            raise CommandAdmissionError('transition task could not be scheduled') from None
        self._task = task

        def completed(done):
            if self._task is done:
                self._task = None
            if not done.cancelled():
                done.exception()

        task.add_done_callback(completed)
        ready.set_result(None)
        return await asyncio.shield(task)

    async def submit(self, candidate: ExactCandidate, *, command_id: str) -> CommandReceipt:
        self._idle()
        if not self.accepting:
            raise CommandAdmissionError('transition admission is closed or work remains retained')
        if type(candidate) is not ExactCandidate:
            raise CommandAdmissionError('an exact owned candidate is required')
        # Revalidate the paired evidence rather than accepting a mutable projection.
        candidate.__post_init__()
        transition = candidate.transition
        before = None if self._state is None else self._state.to_dict()
        if canonical_json(transition['before']) != canonical_json(before):
            raise CommandAdmissionError('candidate does not extend the installed state')
        configuration = self._creation.expected_request['config']
        if (canonical_json(transition['after']['engine']['config'])
                != canonical_json(configuration['rehearsal'])
                or Decimal(configuration['rehearsal']['initial_cash'])
                != Decimal(self._creation.expected_request['initial_cash'])):
            raise CommandAdmissionError('candidate differs from acknowledged run configuration')
        command = PreparedCommand.batch(self._repository.owner_id, self._repository.run_id,
            self._repository.worker_id, self._repository.fence, self._repository.revision,
            candidate.operations, command_id=command_id, version=self._repository.command_version, transition=transition)
        # No suspension between admission and retaining the exact candidate/ID.
        self._candidate, self._command = candidate, command
        self._receipt = None
        self._events = tuple(canonical_json(event) for event in transition['events'])
        self._next, self._awaiting_ack, self._installed = 0, False, False
        self._admission_baseline = self._repository_snapshot()
        return await self._owned(self._submit, unsubmitted=True)

    def _repository_snapshot(self):
        repo = self._repository
        return (repo.last_receipt, repo.revision, repo.fence, repo.status, repo.command_version)

    async def _submit(self):
        try:
            receipt = await self._repository.submit(self._command)
        except CommandAdmissionError:
            baseline, current = self._admission_baseline, self._repository_snapshot()
            if (baseline is not None and baseline[0] is current[0] and baseline[1:] == current[1:]
                    and self._repository.pending is None and not self._repository.busy
                    and self._receipt is None and not self._installed):
                # Repository records pending before any RPC and wraps every
                # post-admission transport failure as UncertainCommand. Only
                # this unchanged baseline proves the request was never sent.
                self._clear()
            raise
        self._receipt = receipt
        self._finish_install()
        return receipt

    def _validate_receipt(self):
        command, receipt, candidate = self._command, self._receipt, self._candidate
        if (command is None or receipt is None or candidate is None
                or type(receipt) is not CommandReceipt
                or receipt.command != command
                or receipt.command.request != command.request):
            raise UncertainCommand('retained command and receipt do not match')
        after = candidate.state.to_dict()
        response = receipt.response
        if (type(response) is not dict or set(response) != {'run_id', 'revision', 'fence', 'status', 'reserve'}
                or response['run_id'] != command.run_id
                or type(response['revision']) is not int or response['revision'] != after['revision']
                or type(response['fence']) is not int or response['fence'] != command.fence
                or response['status'] != after['status'] or type(response['reserve']) is not str
                or Decimal(response['reserve']) != Decimal(after['reserve'])
                or self._repository.revision != receipt.revision
                or self._repository.fence != receipt.fence or self._repository.status != receipt.status
                or self._repository.pending is not None):
            raise UncertainCommand('acknowledgment does not establish the retained exact state')
        if (canonical_json(command.expected_request['payload']) != canonical_json({
                'version': self._repository.command_version, 'operations': candidate.operations, 'transition': candidate.transition})):
            raise UncertainCommand('acknowledged payload differs from retained candidate')

    def _install(self):
        """No callbacks or awaits: validate first, then one state-pointer assignment."""
        self._validate_receipt()
        before = None if self._state is None else self._state.to_dict()
        if canonical_json(before) != canonical_json(self._candidate.transition['before']):
            raise UncertainCommand('installed state changed before acknowledgment installation')
        self._state = self._candidate.state

    def _finish_install(self):
        self._validate_receipt()
        if not self._installed:
            self._install()
            self._installed = True
        if not self._events:
            self._clear()

    def _clear(self):
        self._candidate = self._command = self._receipt = None
        self._events = ()
        self._next, self._awaiting_ack, self._installed = 0, False, False
        self._admission_baseline = None

    async def reconcile(self) -> CommandReceipt | None:
        self._idle()
        if self._candidate is None:
            return None
        return await self._owned(self._reconcile)

    async def _reconcile(self):
        if self._receipt is None:
            if self._repository.pending is not None:
                if self._repository.pending != self._command:
                    raise UncertainCommand('repository retained a different command')
                receipt = await self._repository.resolve_pending()
                if receipt is None:
                    return None
            else:
                # A canceled outer task can leave a successful late repository
                # acknowledgment after repository.pending was already cleared.
                receipt = self._repository.last_receipt
                if receipt is None or receipt.command != self._command:
                    raise UncertainCommand('no matching retained acknowledgment is available')
            self._receipt = receipt
        receipt = self._receipt
        self._finish_install()
        return receipt

    async def heartbeat(self, lease_seconds: int = 30):
        self._idle()
        if not self._open:
            raise CommandAdmissionError('transition admission is permanently closed')
        if (self._candidate is not None and not self._installed) or not self._current():
            raise CommandAdmissionError('install the retained transition before lease renewal')
        return await self._owned(lambda: self._repository.heartbeat(lease_seconds))

    def _event(self, index):
        command = self._command
        return {'event_id': f'{command.run_id}:{command.command_id}:{index}',
                'owner_id': command.owner_id, 'run_id': command.run_id,
                'command_id': command.command_id,
                'revision': command.expected_result_revision, 'event_index': index,
                'event': json.loads(self._events[index])}

    def _page(self, response, count, max_bytes):
        expected = {'version', 'owner_id', 'run_id', 'through_revision', 'events', 'has_more'}
        encoded = canonical_json(response)
        size = len(json.dumps(json.loads(encoded), ensure_ascii=False, sort_keys=True,
                              separators=(', ', ': ')).encode('utf-8'))
        if (type(response) is not dict or set(response) != expected or size > max_bytes
                or type(response['version']) is not int or response['version'] != 1
                or response['owner_id'] != self._command.owner_id
                or response['run_id'] != self._command.run_id
                or type(response['through_revision']) is not int
                or response['through_revision'] != self._state.revision
                or type(response['events']) is not list or not 1 <= len(response['events']) <= count
                or self._next + len(response['events']) > len(self._events)
                or type(response['has_more']) is not bool
                or response['has_more'] != (self._next + len(response['events']) < len(self._events))):
            raise PublicationError('outbox page does not match the retained installed transition')
        rows = response['events']
        for offset, row in enumerate(rows):
            if canonical_json(row) != canonical_json(self._event(self._next + offset)):
                raise PublicationError('outbox event identity, order or content differs')
        return rows

    async def _acknowledge(self):
        event = self._event(self._next)
        result = await self._transport.rpc('acknowledge_event', {
            'owner_id': self._command.owner_id, 'run': self._command.run_id,
            'command_id': self._command.command_id, 'event_index': self._next})
        expected = {key: value for key, value in event.items() if key != 'event'}
        expected.update(version=1, owner_id=self._command.owner_id,
                        run_id=self._command.run_id, acknowledged=True)
        if canonical_json(result) != canonical_json(expected):
            raise PublicationError('outbox acknowledgment does not match the original event')
        self._next += 1
        self._awaiting_ack = False

    async def publish_pending(self, publisher: Callable[[dict], Awaitable[None]], *,
                              max_events: int = 50, max_bytes: int = 65536) -> int:
        self._idle()
        bounded_integer(max_events, 'event limit', maximum=100)
        bounded_integer(max_bytes, 'page bytes', minimum=512, maximum=65536)
        if not callable(publisher):
            raise CommandAdmissionError('a stable idempotent publisher is required')
        if self._candidate is None:
            return 0
        if not self._installed or self._receipt is None:
            raise CommandAdmissionError('install the acknowledged candidate before publishing')
        self._validate_receipt()
        return await self._owned(lambda: self._publish(publisher, max_events, max_bytes))

    async def _publish(self, publisher, max_events, max_bytes):
        delivered = 0
        try:
            while delivered < max_events and self._next < len(self._events):
                if self._awaiting_ack:
                    await self._acknowledge()
                    delivered += 1
                    continue
                response = await self._transport.rpc('read_outbox', {
                    'owner_id': self._command.owner_id, 'run': self._command.run_id,
                    'through_revision': self._state.revision,
                    'max_events': max_events - delivered, 'max_bytes': max_bytes})
                rows = self._page(response, max_events - delivered, max_bytes)
                for row in rows:
                    # Detach from validation and retained evidence before entering
                    # caller code. Success and pending-ack ownership are atomic.
                    result = await publisher(json.loads(canonical_json(row)))
                    if result is not None:
                        raise PublicationError('publisher must confirm relay acceptance with None')
                    self._awaiting_ack = True
                    await self._acknowledge()
                    delivered += 1
            if self._next == len(self._events):
                self._clear()
            return delivered
        except asyncio.CancelledError:
            raise
        except Exception:
            raise PublicationError('delivery remains retained; retry the original event identity') from None
