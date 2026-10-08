"""Executable, exclusively owned provider paper pilot; no service cutover.

One task owns each complete provider-to-outbox operation. A retained stage is
the continuation of that original operation, never permission to repeat its
economic command. The feed, owner, transport and publisher must have no other
callers. This component cannot restore checkpoints or trade a wallet.
"""
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import time

from .decision_inputs import DecisionInputs
from .provider_acquisition import ACQUISITION_TIMEOUT_SECONDS, ProviderPriceAcquisition
from .operation_diagnostics import failure_labels
from ..db.command_protocol import bounded_integer, canonical_uuid
from ..db.command_repository import CommandBusy, UncertainCommand
from ..db.provider_pilot_owner import ProviderPilotOwner, PilotAdmissionRefused
from ..db.rehearsal_owner import OperationalAdmissionError
from ..db.transition_coordinator import PublicationError
from ..market.provider_contract import CANDLE_COMPLETION_US, clock_us

HISTORY_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class CommandAllocation:
    command_id: str
    ids: tuple[str, ...] = ()
    names: tuple[tuple[int, str], ...] = ()

    def __post_init__(self):
        canonical_uuid(self.command_id, 'controller command id')
        origin = datetime(1970, 1, 1, tzinfo=timezone.utc)
        DecisionInputs(origin, origin, 0.0, self.ids, self.names)
        if len(self.ids) > 9 or len(self.names) > 8:
            raise OperationalAdmissionError('controller allocations exceed pilot bounds')


@dataclass(frozen=True, slots=True)
class TickReport:
    kind: str
    status: str
    revision: int
    quote_sequence: int
    decision_committed: bool
    elapsed_seconds: float | None
    phase_seconds: tuple[tuple[str, float], ...]


@dataclass(slots=True)
class _Work:
    kind: str
    stage: str
    started: float
    ticket: object = None
    records: tuple = ()
    allocation: CommandAllocation | None = None
    next_stage: str | None = None
    decision_committed: bool = False
    renewed_after_readback: bool = False
    expected_revision: int | None = None
    phases: dict[str, float] = field(default_factory=dict)


class ProviderPilotController:
    def __init__(self, owner, feed, publisher, allocate, *, lease_seconds=120,
                 wall_clock=time.time, monotonic=time.monotonic,
                 max_events=50, max_bytes=65536):
        if (type(owner) is not ProviderPilotOwner or owner.busy
                or owner.installed_state is not None or owner.pending_candidate is not None
                or not all(callable(value) for value in
                           (publisher, allocate, wall_clock, monotonic))
                or not callable(getattr(feed, 'get_provider_history', None))):
            raise OperationalAdmissionError('controller requires exclusive fresh pilot resources')
        bounded_integer(lease_seconds, 'lease seconds', maximum=120)
        bounded_integer(max_events, 'event limit', maximum=100)
        bounded_integer(max_bytes, 'page bytes', minimum=512, maximum=65536)
        self._owner, self._feed = owner, feed
        self._publisher, self._allocate = publisher, allocate
        self._acquisition = ProviderPriceAcquisition(feed, owner)
        self._lease_seconds = lease_seconds
        self._max_events, self._max_bytes = max_events, max_bytes
        self._wall, self._monotonic = wall_clock, monotonic
        self._last_wall = self._last_mono = None
        self._loop = None
        self._task = None
        self._waiter = False
        self._work: _Work | None = None
        self._draining = False
        self._closed_reason = None
        self._last_report = None
        self._last_failure = None

    @property
    def last_failure(self):
        if self._last_failure is None:
            return None
        return {**self._last_failure.to_dict(),
                'acquisition': self._acquisition.last_failure}

    @property
    def busy(self):
        # Includes an original completed result retained by a cancelled caller.
        return self._task is not None or self._owner.busy or self._acquisition.busy

    @property
    def pending_stage(self):
        return None if self._work is None else self._work.stage

    @property
    def last_report(self):
        return self._last_report

    @property
    def pilot_limits(self):
        return self._owner.limits

    @property
    def pilot_completed(self):
        return self._owner.refusal_reason == 'pilot_completed'

    @property
    def lease_seconds(self):
        return self._lease_seconds

    @property
    def lease_remaining_seconds(self):
        self._clocks()
        return self._owner.lease_remaining_seconds

    @property
    def closed_reason(self):
        return self._closed_reason or self._owner.closed_reason

    @property
    def accepting(self):
        if self.busy or self._work is not None or self._draining:
            return False
        try:
            self._clocks()
        except OperationalAdmissionError:
            return False
        state = self._owner.installed_state
        return (self.closed_reason is None and self._owner.refusal_reason is None
                and (state is None or state.to_dict()['status'] in ('running', 'risk_halted')))

    def close_admission(self):
        """Stop new stages while preserving settlement and reserved stop."""
        self._draining = True
        self._acquisition.close_admission()

    def _fail(self, reason):
        self._closed_reason = self._closed_reason or reason
        self.close_admission()
        self._owner.close_admission()

    def _clocks(self):
        try:
            wall, mono = self._wall(), self._monotonic()
            if (any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
                    for value in (wall, mono))
                    or self._last_wall is not None and wall < self._last_wall
                    or self._last_mono is not None and mono < self._last_mono):
                raise ValueError()
        except (Exception, asyncio.CancelledError):
            self._fail('controller_clock_invalid')
            raise OperationalAdmissionError(self._closed_reason) from None
        self._last_wall, self._last_mono = float(wall), float(mono)
        return self._last_wall, self._last_mono

    def _bind_loop(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise OperationalAdmissionError('controller belongs to another event loop')

    def _idle(self):
        self._bind_loop()
        if self.busy:
            raise CommandBusy('the original controller operation must settle first')

    def _normal(self):
        self._clocks()
        if (self._draining or self.closed_reason is not None
                or self._owner.refusal_reason is not None):
            raise OperationalAdmissionError('controller ordinary admission is closed')

    async def _timed(self, label, operation, *, settlement=False):
        work = self._work
        try:
            _, start = self._clocks()
        except OperationalAdmissionError:
            if not settlement:
                if inspect.iscoroutine(operation):
                    operation.close()
                raise
            start = None
        try:
            return await operation
        finally:
            try:
                _, end = self._clocks()
            except OperationalAdmissionError:
                end = None
            if work is not None and start is not None and end is not None:
                work.phases[label] = work.phases.get(label, 0.0) + end - start

    def _report(self, status, *, finish=False):
        work = self._work
        state = self._owner.installed_state
        data = None if state is None else state.to_dict()
        try:
            _, now = self._clocks()
            elapsed = now - work.started
        except OperationalAdmissionError:
            elapsed = None
        report = TickReport(work.kind, status, 1 if data is None else data['revision'],
            0 if data is None else data['source']['quote_sequence'], work.decision_committed,
            elapsed, tuple(sorted(work.phases.items())))
        self._last_report = report
        if finish:
            self._work = None
        return report

    def _allocation(self, kind):
        work = self._work
        data = None if self._owner.installed_state is None else self._owner.installed_state.to_dict()
        generation = 0 if data is None else data['engine']['generation'] + 1
        allocation = self._allocate(kind, generation)
        if type(allocation) is not CommandAllocation:
            if inspect.iscoroutine(allocation):
                allocation.close()
            raise OperationalAdmissionError('allocation factory must return immutable CommandAllocation')
        allocation.__post_init__()
        work.allocation = CommandAllocation(allocation.command_id, allocation.ids, allocation.names)
        return dict(command_id=allocation.command_id, ids=allocation.ids, names=allocation.names)

    async def _history(self, previous_end):
        async with asyncio.timeout(HISTORY_TIMEOUT_SECONDS) as deadline:
            records = await self._timed('history_acquisition',
                self._feed.get_provider_history(previous_end=previous_end))
            if (deadline.expired() or asyncio.get_running_loop().time() >= deadline.when()
                    or type(records) not in (tuple, list) or len(records) > 20000):
                raise OperationalAdmissionError('controller history acquisition failed')
            return tuple(records)

    async def _capture(self):
        # A fractional receipt cannot be used until the next actual UTC second.
        # Keep this subsecond wait inside the original acquisition budget:
        # handing it to the five-second runner cadence expires the receipt.
        # This admits the same document, without another provider request.
        async with asyncio.timeout(ACQUISITION_TIMEOUT_SECONDS) as deadline:
            ticket = await self._acquisition.capture_quote()
            target = self._acquisition.deferred_until_second
            if ticket is None and target is not None:
                wall, _ = self._clocks()
                delay = target - wall
                if delay > 1:
                    raise OperationalAdmissionError('controller_receipt_boundary_invalid')
                if delay > 0:
                    await asyncio.sleep(delay)
                wall, _ = self._clocks()
                if deadline.expired() or asyncio.get_running_loop().time() >= deadline.when():
                    raise OperationalAdmissionError('controller_price_acquisition_expired')
                if self._draining or self.closed_reason:
                    return None
                if wall < target:
                    raise OperationalAdmissionError('controller_receipt_clock_did_not_advance')
                ticket = await self._acquisition.capture_quote()
                if ticket is None and self._acquisition.has_deferred_capture:
                    raise OperationalAdmissionError('controller_original_receipt_not_admitted')
            if deadline.expired() or asyncio.get_running_loop().time() >= deadline.when():
                raise OperationalAdmissionError('controller_price_acquisition_expired')
            return ticket

    async def _publish(self):
        while self._owner.pending_candidate is not None:
            delivered = await self._timed('publication', self._owner.publish_pending(
                self._publisher, max_events=self._max_events, max_bytes=self._max_bytes),
                settlement=True)
            if delivered == 0 and self._owner.pending_candidate is not None:
                raise PublicationError('retained publication made no progress')

    async def _submit(self, phase, operation, next_stage):
        work = self._work
        # The continuation is owned before the submission boundary. Recovery
        # resolves this command; it must never call its planner/allocator again.
        work.stage, work.next_stage = phase + '_settle', next_stage
        state = self._owner.installed_state
        work.expected_revision = 2 if state is None else state.revision + 1
        await self._timed('owner_submission', operation)
        work.stage = next_stage

    async def _renew(self):
        await self._timed('lease_renewal', self._owner.heartbeat(self._lease_seconds))

    def _barrier(self):
        """After an await, drain before the next unsubmitted action."""
        if self._draining or self.closed_reason:
            self._owner.discard_unsubmitted_evidence()
            return self._report('closed' if self.closed_reason else 'drained', finish=True)
        return None

    async def _advance(self, *, settlement_only=False):
        work = self._work
        try:
            while True:
                stage = work.stage
                if stage.endswith('_settle'):
                    if self._owner.busy:
                        return self._report('pending')
                    receipt = await self._timed('reconciliation', self._owner.reconcile(), settlement=True)
                    if receipt is None and self._owner.pending_candidate is not None:
                        return self._report('pending')
                    state = self._owner.installed_state
                    if state is None or state.revision != work.expected_revision:
                        self._fail('controller_original_command_uninstalled')
                        return self._report('closed', finish=True)
                    if stage == 'decide_settle':
                        work.decision_committed = True
                    work.renewed_after_readback = True
                    work.stage = work.next_stage
                    continue
                if stage.endswith('_publish'):
                    await self._publish()
                    work.allocation = None
                    work.records = ()
                    work.stage = 'decision_select' if stage == 'protect_publish' else 'done'
                    continue
                if stage == 'done':
                    # A journal readback proves the original commit, not a
                    # renewed lease. Publication must finish first, but normal
                    # execution may return to the runner only with a fresh
                    # acknowledged heartbeat. Draining settles without renewal.
                    if (work.renewed_after_readback and not settlement_only
                            and not self._draining and not self.closed_reason
                            and not self.pilot_completed):
                        self._normal()
                        await self._renew()
                        work.renewed_after_readback = False
                        report = self._barrier()
                        if report is not None:
                            return report
                    status = 'closed' if self.closed_reason else 'complete'
                    return self._report(status, finish=True)
                if settlement_only or self._draining or self.closed_reason:
                    self._owner.discard_unsubmitted_evidence()
                    return self._report('closed' if self.closed_reason else 'drained', finish=True)
                self._normal()
                if work.renewed_after_readback:
                    await self._renew()
                    work.renewed_after_readback = False
                    report = self._barrier()
                    if report is not None:
                        return report
                if stage == 'bootstrap_history':
                    await self._renew()
                    report = self._barrier()
                    if report is not None:
                        return report
                    work.records = await self._history(None)
                    report = self._barrier()
                    if report is not None:
                        return report
                    allocation = self._allocation('bootstrap')
                    await self._submit('bootstrap', self._owner.bootstrap(work.records, **allocation),
                                       'bootstrap_publish')
                elif stage == 'capture':
                    await self._renew()
                    report = self._barrier()
                    if report is not None:
                        return report
                    work.ticket = await self._timed('price_acquisition', self._capture())
                    report = self._barrier()
                    if report is not None:
                        return report
                    if work.ticket is None:
                        return self._report('deferred', finish=True)
                    allocation = self._allocation('protect')
                    await self._submit('protect', self._owner.protect(work.ticket, **allocation),
                                       'protect_publish')
                elif stage == 'decision_select':
                    if not self._owner.decision_due(work.ticket):
                        work.stage = 'done'
                        continue
                    data = self._owner.installed_state.to_dict()
                    if not data['engine']['lifecycle']['risk']['active']:
                        previous_end = data['source']['bars'][-1][0]
                        wall, _ = self._clocks()
                        latest = (clock_us(wall) - CANDLE_COMPLETION_US) // 900_000_000 * 900
                        if latest > previous_end:
                            work.records = await self._history(previous_end)
                    report = self._barrier()
                    if report is not None:
                        return report
                    allocation = self._allocation('decide')
                    await self._submit('decide', self._owner.decide(work.ticket, work.records, **allocation),
                                       'decide_publish')
                    work.decision_committed = True
                elif stage == 'pause_submit':
                    await self._renew()
                    report = self._barrier()
                    if report is not None:
                        return report
                    allocation = self._allocation('pause')
                    await self._submit('pause', self._owner.control('pause', **allocation), 'pause_publish')
                elif stage == 'stop_submit':
                    # Drain prevents new economics, but explicitly authorized
                    # terminal control is allowed through the reserved path.
                    raise AssertionError('stop has a separate terminal branch')
                elif stage == 'heartbeat':
                    await self._renew()
                    work.stage = 'done'
                else:
                    raise OperationalAdmissionError('invalid retained controller stage')
        except (UncertainCommand, PublicationError):
            raise
        except PilotAdmissionRefused:
            self.close_admission()
            self._report('drained', finish=True)
            raise
        except (Exception, asyncio.CancelledError) as error:
            if self._last_failure is None:
                self._last_failure = failure_labels(work.stage, error)
            self._fail('controller_operation_failed')
            if (self._owner.pending_candidate is None and not self._owner.busy
                    and not self._acquisition.busy):
                self._report('closed', finish=True)
            raise

    async def _consume(self, task):
        self._bind_loop()
        if self._waiter:
            raise CommandBusy('an original controller waiter is still active')
        self._waiter = True
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                self._task = None
                self._fail('controller_operation_interrupted')
                raise OperationalAdmissionError(self._closed_reason) from None
            raise  # Original whole task/result remains owned.
        except Exception:
            if task.done() and self._task is task:
                self._task = None
            raise
        else:
            self._task = None
            return result
        finally:
            self._waiter = False

    async def _owned(self, operation):
        ready = asyncio.get_running_loop().create_future()
        async def run():
            await ready
            try:
                return await operation()
            except asyncio.CancelledError:
                self._fail('controller_operation_interrupted')
                raise
        coroutine = run()
        try:
            task = asyncio.create_task(coroutine)
        except (Exception, asyncio.CancelledError):
            coroutine.close()
            self._fail('controller_scheduling_failed')
            raise OperationalAdmissionError(self._closed_reason) from None
        self._task = task
        def completed(done):
            if done.cancelled():
                self._fail('controller_operation_interrupted')
            else:
                done.exception()
        task.add_done_callback(completed)
        ready.set_result(None)
        return await self._consume(task)

    def _new(self, kind, stage):
        _, mono = self._clocks()
        self._work = _Work(kind, stage, mono)

    async def bootstrap(self):
        self._idle()
        self._normal()
        if self._work is not None or self._owner.installed_state is not None:
            raise OperationalAdmissionError('fresh bootstrap only; settle original work first')
        self._new('bootstrap', 'bootstrap_history')
        return await self._owned(self._advance)

    async def tick(self):
        self._idle()
        self._normal()
        if self._work is not None:
            raise CommandBusy('settle the original controller stage first')
        state = self._owner.installed_state
        if state is None or state.to_dict()['status'] not in ('running', 'risk_halted'):
            raise OperationalAdmissionError('tick requires a running bootstrapped pilot')
        self._new('tick', 'capture')
        return await self._owned(self._advance)

    async def settle(self):
        self._bind_loop()
        if self._task is not None:
            return await self._consume(self._task)
        if self._acquisition.busy:
            # Explicit interruption of the owned controller task can leave its
            # shielded acquisition alive. Cleanup consumes that original result
            # before reporting idle; it never starts another provider request.
            return await self._owned(self._settle_acquisition)
        self._idle()
        if self._work is None:
            return self._last_report
        return await self._owned(lambda: self._advance(settlement_only=self._draining or bool(self.closed_reason)))

    async def _settle_acquisition(self):
        try:
            await self._timed('acquisition_cleanup', self._acquisition.settle(), settlement=True)
        except Exception:
            # A failed original task still owns a completed exception until
            # capture_quote consumes it below. No new capture is authorized.
            pass
        try:
            await self._timed('acquisition_cleanup', self._acquisition.capture_quote(), settlement=True)
        except Exception:
            if self._acquisition.busy:
                raise
            # The original capture may reject the now hard-closed owner. Its
            # result is nevertheless consumed and no request remains owned.
        if self._work is not None:
            return await self._advance(settlement_only=True)
        return self._last_report

    async def _control(self, action):
        if self._work is not None:
            report = await self._advance(settlement_only=True)
            if self._work is not None:
                return report  # No queued control or new identity.
        # Retrying an uncertain control first resolves its original identity.
        # Once installed, the requested status is already authoritative; a
        # second pause/stop would be an invalid new lifecycle transition.
        state = self._owner.installed_state
        if state is not None:
            data = state.to_dict()
            if data['status'] == {'pause': 'paused', 'stop': 'stopped'}[action]:
                report = self._last_report
                if report is None or report.kind != action or report.revision != data['revision']:
                    report = TickReport(action, 'closed' if self.closed_reason else 'complete',
                        data['revision'], data['source']['quote_sequence'], False, 0.0, ())
                    self._last_report = report
                return report
        self._new(action, action + '_submit')
        if action == 'stop':
            try:
                await self._renew()
                await self._submit('stop', self._owner.stop(), 'stop_publish')
                return await self._advance(settlement_only=True)
            except (UncertainCommand, PublicationError):
                raise
            except (Exception, asyncio.CancelledError):
                self._fail('controller_operation_failed')
                raise
        return await self._advance()

    async def control(self, action):
        if action == 'stop':
            return await self.stop()
        self._idle()
        self._normal()
        if action != 'pause':
            raise OperationalAdmissionError('pilot controller supports pause and stop only')
        return await self._owned(lambda: self._control(action))

    async def stop(self):
        self._bind_loop()
        self.close_admission()
        self._idle()
        return await self._owned(lambda: self._control('stop'))

    async def heartbeat(self):
        self._idle()
        if self._work is not None:
            raise OperationalAdmissionError('settle original work before heartbeat')
        self._new('heartbeat', 'heartbeat')
        return await self._owned(self._advance)
