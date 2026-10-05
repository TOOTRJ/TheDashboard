"""Opt-in, single-window v5 paper pilot with reserved terminal capacity.

This owner is intentionally absent from production service selection. Policy
refusal stops new economics without reopening the existing hard-failure latch.
It reserves byte/identity capacity, not a lease, network delivery or liquidation.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time

from ..core import provider_lifecycle as lifecycle
from ..core.decision_inputs import DecisionInputs
from ..core.exact_rehearsal import ExactCandidate, ExactCapacityError, MAX_PAYLOAD_BYTES
from ..core.provider_pilot import (
    ProviderPilotLimits, PilotCapacityError, decision_required, stop_capacity_bytes,
)
from .command_protocol import canonical_uuid
from .command_repository import UncertainCommand
from .provider_owner import ProviderAdmissionOwner
from .rehearsal_owner import MAX_OWNED_COMMANDS, OperationalAdmissionError


class PilotAdmissionRefused(OperationalAdmissionError):
    """The pilot has ended ordinary admission; a reserved stop may remain."""


class ProviderPilotOwner(ProviderAdmissionOwner):
    def __init__(self, repository, outbox_transport, config, *, stop_command_id,
                 limits=ProviderPilotLimits(), wall_clock=time.time,
                 monotonic=time.monotonic):
        if type(limits) is not ProviderPilotLimits:
            raise OperationalAdmissionError('a bounded pilot policy is required')
        limits.__post_init__()
        canonical_uuid(stop_command_id, 'reserved stop command id')
        receipt = repository.last_receipt
        if receipt is None or stop_command_id == receipt.command.command_id:
            raise OperationalAdmissionError('stop requires a distinct unused command id')
        self._limits = ProviderPilotLimits(limits.max_quotes, limits.max_commands)
        self._reserved_stop_id = stop_command_id
        self._pilot_refusal = None
        self._first_quote_second = None
        self._verified_stop_state = None
        self._verified_stop_bytes = None
        self._planned_stop_bytes = None
        super().__init__(repository, outbox_transport, config,
                         wall_clock=wall_clock, monotonic=monotonic)

    @property
    def refusal_reason(self):
        return self._pilot_refusal

    @property
    def limits(self):
        """Immutable local policy for an exclusive scheduling owner."""
        return self._limits

    @property
    def owned_command_count(self):
        return len(self._used_command_ids)

    @property
    def reserved_stop_bytes(self):
        return (self._verified_stop_bytes
                if self.installed_state is self._verified_stop_state else None)

    @property
    def accepting(self):
        return self._pilot_refusal is None and super().accepting

    @property
    def stop_available(self):
        # A retained command/event prefix must settle before another command.
        if (self._closed_reason is not None or self.busy
                or self.installed_state is None
                or self.installed_state is not self._verified_stop_state
                or self.installed_state.to_dict()['status'] == 'stopped'
                or self._reserved_stop_id in self._used_command_ids):
            return False
        try:
            self._guard()
            return self._coordinator.accepting
        except (Exception, asyncio.CancelledError):
            self._close(self._closed_reason or 'repository_admission_invalid')
            return False

    def _refuse(self, reason):
        if self._pilot_refusal is None:
            self._pilot_refusal = reason
        # A refused plan never owns evidence for a future command. Retaining
        # an idle ticket here would later expire the independent stop channel.
        # Never clear evidence still bound to reconciliation or publication.
        if self.pending_candidate is None and not self._coordinator.busy:
            self._window = None
            self._history = None
        raise PilotAdmissionRefused(self._pilot_refusal)

    def _admit(self):
        self._idle()
        if self._pilot_refusal is not None:
            raise PilotAdmissionRefused(self._pilot_refusal)
        self._limits.__post_init__()
        super()._admit()

    def _allocations(self, ids, names):
        # Freeze membership and validate scalar contents before any await.
        try:
            origin = datetime(1970, 1, 1, tzinfo=timezone.utc)
            DecisionInputs(origin, origin, 0.0, ids, names)
        except (Exception, asyncio.CancelledError):
            self._reject('pilot_allocations_invalid')
        if (len(ids) > self._limits.MAX_IDS or len(names) > self._limits.MAX_NAMES):
            self._refuse('pilot_allocation_budget')
        if self._reserved_stop_id in ids:
            self._refuse('pilot_reserved_identity')

    def _quote_policy(self, frame):
        if frame['sequence'] > self._limits.max_quotes:
            self._refuse('pilot_quote_budget')
        if (self._first_quote_second is not None and frame['decision_second']
                > self._first_quote_second + self._limits.MAX_ELAPSED_QUOTE_SECONDS):
            self._refuse('pilot_duration')

    def discard_unsubmitted_evidence(self):
        """Abandon an idle scheduling window without touching retained work.

        An exclusive controller uses this when draining between protection and
        decision. The accepted ticket is invalidated; another decision requires
        a new acknowledged protection. Hard admission latches are unchanged.
        """
        self._idle()
        if self.pending_candidate is not None:
            raise OperationalAdmissionError('retained evidence must settle before abandonment')
        self._window = self._history = self._accepted_quote = None

    def capture_quote(self, capture):
        self._admit()
        if (self.installed_state is not None and self.installed_state.to_dict()
                ['source']['quote_sequence'] >= self._limits.max_quotes):
            self._refuse('pilot_quote_budget')
        ticket = super().capture_quote(capture)
        self._quote_policy(ticket.frame)
        return ticket

    def _synchronize(self):
        candidate = self._inflight_candidate
        if candidate is not None and self.installed_state is candidate.state:
            data = candidate.state.to_dict()
            if data['status'] != 'stopped':
                self._verified_stop_state = candidate.state
                self._verified_stop_bytes = self._planned_stop_bytes
            quote = data['source']['last_quote']
            if self._first_quote_second is None and quote is not None:
                self._first_quote_second = quote['decision_second']
            if data['engine']['generation'] >= self._limits.MAX_GENERATION:
                self._pilot_refusal = self._pilot_refusal or 'pilot_completed'
        super()._synchronize()

    async def _plan_submit(self, planner, kind, command_id, quote=None):
        terminal = kind == 'pilot_stop'
        try:
            self._guard()
            canonical_uuid(command_id, 'command id')
            if command_id in self._used_command_ids:
                self._reject('command_identity_reused')
            if terminal:
                if command_id != self._reserved_stop_id:
                    self._reject('stop_identity_invalid')
                if len(self._used_command_ids) >= MAX_OWNED_COMMANDS:
                    self._reject('command_capacity_exhausted')
            else:
                if command_id == self._reserved_stop_id:
                    self._refuse('pilot_reserved_identity')
                # Includes creation and reserves one slot for the stop itself.
                if len(self._used_command_ids) >= self._limits.max_commands - 1:
                    self._refuse('pilot_command_budget')
                if quote is not None:
                    self._quote_policy(quote.frame)
            candidate = planner()
            if type(candidate) is not ExactCandidate:
                self._reject('pilot_candidate_invalid')
            if terminal:
                if (candidate.transition['evidence']['control']['action'] != 'stop'
                        or self.installed_state is not self._verified_stop_state
                        or candidate.payload_bytes > self._verified_stop_bytes):
                    self._reject('stop_capacity_invariant_failed')
                self._planned_stop_bytes = None
            else:
                data = candidate.state.to_dict()
                if (data['engine']['generation'] > self._limits.MAX_GENERATION
                        or data['engine']['lifecycle']['search_epoch']
                        > self._limits.MAX_SEARCH_EPOCH):
                    self._refuse('pilot_generation_budget')
                try:
                    self._planned_stop_bytes = stop_capacity_bytes(candidate.state)
                except PilotCapacityError:
                    self._refuse('pilot_stop_capacity')
                if (type(self._planned_stop_bytes) is not int
                        or self._planned_stop_bytes <= 0):
                    self._reject('pilot_stop_witness_invalid')
                if self._planned_stop_bytes > MAX_PAYLOAD_BYTES:
                    self._refuse('pilot_stop_capacity')
            self._guard()
            self._inflight_candidate = candidate
            self._inflight_quote, self._inflight_kind = quote, kind
            self._used_command_ids.add(command_id)
        except PilotAdmissionRefused:
            raise
        except ExactCapacityError:
            if terminal:
                self._close('stop_capacity_invariant_failed')
                raise OperationalAdmissionError(self._closed_reason) from None
            self._refuse('pilot_payload_capacity')
        except (Exception, asyncio.CancelledError):
            self._close(self._closed_reason or 'preparation_failed')
            raise OperationalAdmissionError(self._closed_reason) from None
        try:
            return await self._coordinator.submit(candidate, command_id=command_id)
        except UncertainCommand:
            raise
        except Exception:
            self._close(self._closed_reason or 'submission_rejected')
            raise

    async def bootstrap(self, records, *, ids=(), names=(), command_id):
        self._admit()
        self._allocations(ids, names)
        return await super().bootstrap(records, ids=ids, names=names, command_id=command_id)

    async def protect(self, ticket, *, ids=(), names=(), command_id):
        self._admit()
        self._allocations(ids, names)
        return await super().protect(ticket, ids=ids, names=names, command_id=command_id)

    def decision_due(self, ticket):
        self._admit()
        self._use_quote(ticket, accepted=True)
        required = decision_required(self.installed_state, ticket.frame['decision_second'])
        if not required:
            self._window = None
        return required

    async def decide(self, ticket, records=(), *, ids=(), names=(), command_id):
        self._admit()
        self._allocations(ids, names)
        self._use_quote(ticket, accepted=True)
        records = self._records(records)
        try:
            canonical_uuid(command_id, 'command id')
        except Exception:
            self._reject('command_identity_invalid')
        if command_id == self._reserved_stop_id:
            self._refuse('pilot_reserved_identity')
        if command_id in self._used_command_ids:
            self._reject('command_identity_reused')
        if not decision_required(self.installed_state, ticket.frame['decision_second']):
            if records:
                self._reject('unexpected_pilot_history')
            # Do not reserve or consume a command identity for an empty decision.
            # Release only this scheduling window; keep the accepted ticket.
            self._window = None
            return None
        return await super().decide(ticket, records, ids=ids, names=names,
                                    command_id=command_id)

    async def control(self, action, *, ids=(), names=(), command_id=None, ticket=None,
                      records=(), trip_id=None):
        if action == 'stop':
            if (command_id not in (None, self._reserved_stop_id) or ids or names
                    or ticket is not None or records or trip_id is not None):
                self._reject('stop_inputs_invalid')
            return await self.stop()
        self._admit()
        if action != 'pause':
            self._refuse('pilot_control_unsupported')
        self._allocations(ids, names)
        return await super().control(action, ids=ids, names=names, command_id=command_id,
                                     ticket=ticket, records=records, trip_id=trip_id)

    async def stop(self):
        self._idle()
        if not self.stop_available:
            raise OperationalAdmissionError('reserved stop is unavailable or work remains retained')
        return await self._owned(lambda: self._plan_submit(
            lambda: lifecycle.prepare_control(self.installed_state, 'stop', self._inputs((), ())),
            'pilot_stop', self._reserved_stop_id))
