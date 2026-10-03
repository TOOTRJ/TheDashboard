"""One operational owner for the fresh, bounded synthetic v4 rehearsal.

Receipt expiry is a process-local scheduling budget, NOT provider source age.
Synthetic event clocks remain independent. No provider capture, persisted clock,
historical state or arbitrary prepared candidate can enter this API. Exclusive
ownership of the repository/transport on one event loop is required.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import math
import time
from typing import Callable

from ..core import exact_lifecycle as lifecycle
from ..core.decision_inputs import DecisionInputs
from ..core.exact_rehearsal import ExactObservation
from .command_protocol import canonical_json, canonical_uuid
from .command_repository import CommandAdmissionError, CommandBusy, UncertainCommand
from .transition_coordinator import TransitionCoordinator


class OperationalAdmissionError(CommandAdmissionError):
    """This owner cannot admit another economic decision."""


MAX_OWNED_COMMANDS = 4096


@dataclass(frozen=True, slots=True, init=False)
class RehearsalQuote:
    """An owner-issued exact synthetic quote with an immutable receipt window."""

    observation: ExactObservation
    received_at: float
    received_monotonic: float
    _owner: object = field(repr=False, compare=False)

    def __init__(self, *args, **kwargs):
        raise OperationalAdmissionError('quotes must be captured by their operational owner')


class RehearsalAdmissionOwner:
    """Own prepare → dispatch → install → publish, including caller cancellation.

    Any planning/capacity/clock/window failure irreversibly closes admission.
    Already owned work may still install and publish or reconcile its original
    command. There is no restart, reopen, provider binding or live-controller
    authority. A caller must not also use the repository/coordinator directly.
    """

    def __init__(self, repository, outbox_transport,
                 config: lifecycle.ExactLifecycleConfig, *,
                 wall_clock: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic,
                 max_wait_seconds: float = 5.0):
        if (type(config) is not lifecycle.ExactLifecycleConfig
                or not callable(wall_clock) or not callable(monotonic)
                or type(max_wait_seconds) not in (int, float)
                or not math.isfinite(max_wait_seconds) or not 0 < max_wait_seconds <= 60):
            raise OperationalAdmissionError('a bounded synthetic lifecycle owner is required')
        receipt = repository.last_receipt
        if (receipt is None or repository.command_version != 4
                or canonical_json(receipt.command.expected_request.get('config'))
                != canonical_json(config.run_configuration())
                or receipt.command.owner_id != config.owner_id
                or receipt.command.run_id != config.run_id):
            raise OperationalAdmissionError('owner requires its acknowledged fresh v4 configuration')
        self._config = config
        self._wall_clock, self._monotonic = wall_clock, monotonic
        self._budget = float(max_wait_seconds)
        self._epoch = object()
        self._last_wall = self._last_monotonic = None
        self._closed_reason: str | None = None
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._window: RehearsalQuote | None = None
        self._accepted_quote: RehearsalQuote | None = None
        self._inflight_candidate = None
        self._inflight_quote: RehearsalQuote | None = None
        self._inflight_kind: str | None = None
        self._used_command_ids: set[str] = {receipt.command.command_id}
        self._coordinator = TransitionCoordinator(repository, outbox_transport,
                                                  admission_guard=self._guard)

    @property
    def installed_state(self):
        return self._coordinator.installed_state

    @property
    def pending_candidate(self):
        return self._coordinator.pending_candidate

    @property
    def pending_command(self):
        return self._coordinator.pending_command

    @property
    def pending_receipt(self):
        return self._coordinator.pending_receipt

    @property
    def next_event_index(self):
        return self._coordinator.next_event_index

    @property
    def busy(self):
        return self._task is not None or self._coordinator.busy

    @property
    def accepting(self):
        if self._closed_reason is not None or self.busy:
            return False
        try:
            # Sample owner clocks first: repository lease validation can also
            # reject clock rollback, but merely losing a lease is not our latch.
            self._guard()
            return self._coordinator.accepting
        except (Exception, asyncio.CancelledError):
            self._close(self._closed_reason or 'repository_admission_invalid')
            return False

    @property
    def closed_reason(self):
        return self._closed_reason

    def _close(self, reason):
        if self._closed_reason is None:
            self._closed_reason = reason
        self._coordinator.close_admission()

    def close_admission(self):
        self._close('draining')

    def _reject(self, reason):
        self._close(reason)
        raise OperationalAdmissionError(reason)

    def _clocks(self):
        try:
            wall, mono = self._wall_clock(), self._monotonic()
            if (any(type(value) not in (int, float) or not math.isfinite(value)
                    or value < 0 for value in (wall, mono))
                    or self._last_wall is not None and wall < self._last_wall
                    or self._last_monotonic is not None and mono < self._last_monotonic):
                raise ValueError()
        except (Exception, asyncio.CancelledError):
            self._reject('clock_invalid')
        self._last_wall, self._last_monotonic = wall, mono
        return float(wall), float(mono)

    def _guard(self):
        if self._closed_reason is not None:
            raise OperationalAdmissionError(self._closed_reason)
        wall, mono = self._clocks()
        if self._window is not None and max(wall - self._window.received_at,
                mono - self._window.received_monotonic) >= self._budget:
            self._reject('observation_expired')

    def _idle(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise OperationalAdmissionError('owner belongs to another event loop')
        if self.busy:
            raise CommandBusy('an operational request is still owned')

    def _admit(self):
        self._idle()
        if not self.accepting:
            raise OperationalAdmissionError('operational admission is closed or work remains retained')

    def capture_quote(self, timestamp: int, price: str) -> RehearsalQuote:
        """Capture a synthetic quote; this cannot refresh an accepted quote's window."""
        self._admit()
        try:
            observation = ExactObservation(timestamp, price)
            wall, mono = self._clocks()
        except Exception:
            self._close('quote_invalid')
            raise OperationalAdmissionError(self._closed_reason) from None
        quote = object.__new__(RehearsalQuote)
        for key, value in (('observation', observation), ('received_at', wall),
                           ('received_monotonic', mono), ('_owner', self._epoch)):
            object.__setattr__(quote, key, value)
        return quote

    def _use_quote(self, quote, *, accepted=False):
        if (type(quote) is not RehearsalQuote or quote._owner is not self._epoch
                or accepted and quote is not self._accepted_quote):
            self._reject('quote_binding_invalid')
        self._window = quote
        self._guard()

    def _synchronize(self):
        candidate = self._inflight_candidate
        if candidate is not None and self.installed_state is candidate.state:
            self._accepted_quote = (self._inflight_quote
                                    if self._inflight_kind == 'protective' else None)
        if self.pending_candidate is None and not self._coordinator.busy:
            self._inflight_candidate = self._inflight_quote = self._inflight_kind = None
            self._window = None

    def _after_boundary(self):
        # A failed clock/window must never discard an acknowledged candidate or
        # prevent delivery. Coordinator performs the same check inside its tasks.
        try:
            self._guard()
        except (Exception, asyncio.CancelledError):
            self._close(self._closed_reason or 'admission_check_failed')
        self._synchronize()

    async def _owned(self, operation):
        ready = asyncio.get_running_loop().create_future()

        async def run():
            try:
                await ready
                return await operation()
            except asyncio.CancelledError:
                # Caller cancellation is shielded. Cancellation of this owned
                # task itself is an interruption, never permission to continue.
                self._close('operation_interrupted')
                raise
            finally:
                try:
                    self._after_boundary()
                finally:
                    self._task = None

        coroutine = run()
        try:
            task = asyncio.create_task(coroutine)
        except (Exception, asyncio.CancelledError):
            coroutine.close()
            self._close('scheduling_failed')
            raise OperationalAdmissionError('operational request could not be scheduled') from None
        self._task = task

        def completed(done):
            if self._task is done:
                if done.cancelled():
                    self._close('operation_interrupted')
                self._after_boundary()
                self._task = None
            if not done.cancelled():
                done.exception()

        task.add_done_callback(completed)
        ready.set_result(None)
        return await asyncio.shield(task)

    async def _plan_submit(self, planner, kind, command_id, quote=None):
        try:
            self._guard()
            canonical_uuid(command_id, 'command id')
            if command_id in self._used_command_ids:
                self._reject('command_identity_reused')
            if len(self._used_command_ids) >= MAX_OWNED_COMMANDS:
                self._reject('command_capacity_exhausted')
            candidate = planner()
            self._guard()
            self._inflight_candidate = candidate
            self._inflight_quote, self._inflight_kind = quote, kind
            self._used_command_ids.add(command_id)
        except (Exception, asyncio.CancelledError):
            self._close(self._closed_reason or 'preparation_failed')
            raise OperationalAdmissionError(self._closed_reason) from None
        try:
            return await self._coordinator.submit(candidate, command_id=command_id)
        except UncertainCommand:
            # Original candidate/command remain owned; never replan or resubmit.
            raise
        except Exception:
            self._close(self._closed_reason or 'submission_rejected')
            raise

    async def bootstrap(self, inputs: DecisionInputs, *, command_id: str):
        self._admit()
        return await self._owned(lambda: self._plan_submit(
            lambda: lifecycle.bootstrap(self._config, inputs), 'bootstrap', command_id))

    async def protect(self, quote: RehearsalQuote, inputs: DecisionInputs, *, command_id: str):
        self._admit()
        self._use_quote(quote)
        return await self._owned(lambda: self._plan_submit(
            lambda: lifecycle.prepare_protective(self.installed_state, quote.observation, inputs),
            'protective', command_id, quote))

    async def decide(self, quote: RehearsalQuote, inputs: DecisionInputs, *, command_id: str,
                     candle_end=None, candle_close=None):
        self._admit()
        self._use_quote(quote, accepted=True)
        return await self._owned(lambda: self._plan_submit(
            lambda: lifecycle.prepare_decision(self.installed_state,
                ExactObservation(quote.observation.timestamp, quote.observation.price,
                                 candle_end, candle_close), inputs), 'decision', command_id, quote))

    async def control(self, action: str, inputs: DecisionInputs, *, command_id: str,
                      quote=None, candle_end=None, candle_close=None, trip_id=None):
        self._admit()
        if action == 'recover':
            self._use_quote(quote, accepted=True)
        elif quote is not None or candle_end is not None or candle_close is not None:
            self._reject('control_observation_invalid')
        return await self._owned(lambda: self._plan_submit(
            lambda: lifecycle.prepare_control(self.installed_state, action, inputs,
                None if quote is None else ExactObservation(quote.observation.timestamp,
                    quote.observation.price, candle_end, candle_close), trip_id),
            'control', command_id, quote))

    async def heartbeat(self, lease_seconds: int = 30):
        self._idle()
        self._guard()
        return await self._owned(lambda: self._coordinator.heartbeat(lease_seconds))

    async def reconcile(self):
        self._idle()
        return await self._owned(self._coordinator.reconcile)

    async def publish_pending(self, publisher, *, max_events=50, max_bytes=65536):
        self._idle()
        return await self._owned(lambda: self._coordinator.publish_pending(
            publisher, max_events=max_events, max_bytes=max_bytes))
