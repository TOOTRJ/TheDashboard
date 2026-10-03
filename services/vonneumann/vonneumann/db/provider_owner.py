"""Process-local owner for provider evidence and version-five paper decisions.

The owner controls clocks, command reconciliation and publication. It cannot
fetch providers, restore checkpoints or submit live-wallet transactions.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import time

from ..core import provider_lifecycle as lifecycle
from ..core.decision_inputs import DecisionInputs
from ..market import provider_contract as source
from .command_protocol import canonical_json
from .rehearsal_owner import RehearsalAdmissionOwner, OperationalAdmissionError


@dataclass(frozen=True, slots=True, init=False)
class ProviderQuote:
    """Owner-issued immutable frame with detached JSON views."""
    _wire: bytes = field(repr=False)
    _owner: object = field(repr=False, compare=False)

    def __init__(self, *args, **kwargs):
        raise OperationalAdmissionError('provider quotes must be captured by their owner')

    @property
    def frame(self):
        return json.loads(self._wire)


class ProviderAdmissionOwner(RehearsalAdmissionOwner):
    def __init__(self, repository, outbox_transport, config: lifecycle.ProviderLifecycleConfig,
                 *, wall_clock=time.time, monotonic=time.monotonic):
        if (type(config) is not lifecycle.ProviderLifecycleConfig
                or not callable(wall_clock) or not callable(monotonic)):
            raise OperationalAdmissionError('a bounded provider lifecycle owner is required')
        receipt = repository.last_receipt
        if (receipt is None or repository.command_version != 5
                or canonical_json(receipt.command.expected_request.get('config'))
                != canonical_json(config.run_configuration())
                or receipt.command.owner_id != config.owner_id
                or receipt.command.run_id != config.run_id):
            raise OperationalAdmissionError('owner requires its acknowledged fresh v5 configuration')
        self._history = None
        self._initialize(repository, outbox_transport, config, wall_clock, monotonic, 5.0)

    def _guard(self):
        if self._closed_reason is not None:
            raise OperationalAdmissionError(self._closed_reason)
        wall, mono = self._clocks()
        try:
            wall_us = source.clock_us(wall, upper=True)
            mono_us = source.clock_us(mono, upper=True)
            if self._window is not None:
                source.check_frame(self._window.frame, wall_us=wall_us, monotonic_us=mono_us)
            if self._history is not None:
                for document in self._history['documents']:
                    elapsed = (wall_us - document['received_wall_us'],
                               mono_us - document['received_monotonic_us'])
                    if min(elapsed) < 0 or max(elapsed) >= 5_000_000:
                        raise source.ProviderSourceError()
        except (Exception, asyncio.CancelledError):
            self._reject('provider_evidence_expired_or_invalid')

    def _synchronize(self):
        super()._synchronize()
        if self.pending_candidate is None and not self._coordinator.busy:
            self._history = None

    def capture_quote(self, capture) -> ProviderQuote:
        self._admit()
        try:
            if self.installed_state is None:
                raise source.ProviderSourceError()
            wall, mono = self._clocks()
            frame = source.make_frame(capture,
                prior_source=self.installed_state.to_dict()['source'], epoch=self._config.epoch,
                wall_now=wall, monotonic_now=mono)
        except source.ProviderDeferred:
            # Normal repeated snapshot/subsecond deferral never refreshes anchors.
            raise
        except (Exception, asyncio.CancelledError):
            self._reject('provider_quote_invalid')
        quote = object.__new__(ProviderQuote)
        object.__setattr__(quote, '_wire', canonical_json(frame))
        object.__setattr__(quote, '_owner', self._epoch)
        return quote

    def _use_quote(self, quote, *, accepted=False):
        if (type(quote) is not ProviderQuote or quote._owner is not self._epoch
                or accepted and quote is not self._accepted_quote):
            self._reject('quote_binding_invalid')
        self._window = quote
        self._guard()

    def _inputs(self, ids, names, quote=None):
        wall, mono = self._clocks()
        wall_us = source.clock_us(wall, upper=True)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        second = int(wall) if quote is None else quote.frame['decision_second']
        return DecisionInputs(epoch + timedelta(seconds=second),
                              epoch + timedelta(microseconds=wall_us), mono, ids, names)

    def _records(self, records):
        # Own membership before scheduling; immutable records alone do not own
        # a caller's mutable container. Never consume arbitrary iterators here.
        if type(records) not in (tuple, list) or len(records) > 20_000:
            self._reject('provider_records_invalid')
        return tuple(records)

    def _build_history(self, records, inputs, *, seed=False):
        wall_us, mono_us = lifecycle.evidence_clocks(inputs)
        bars = [] if seed else self.installed_state.to_dict()['source']['bars']
        bundle = source.build_history(records, prior_bars=bars, seed=seed,
                                      wall_us=wall_us, monotonic_us=mono_us)
        self._history = bundle
        return bundle

    async def bootstrap(self, records, *, ids=(), names=(), command_id):
        self._admit()
        records = self._records(records)
        def plan():
            inputs = self._inputs(ids, names)
            history = self._build_history(records, inputs, seed=True)
            return lifecycle.bootstrap(self._config, history, inputs)
        return await self._owned(lambda: self._plan_submit(plan, 'bootstrap', command_id))

    async def protect(self, ticket, *, ids=(), names=(), command_id):
        self._admit()
        self._use_quote(ticket)
        return await self._owned(lambda: self._plan_submit(
            lambda: lifecycle.prepare_protective(self.installed_state, ticket.frame,
                                                self._inputs(ids, names, ticket)),
            'protective', command_id, ticket))

    async def decide(self, ticket, records=(), *, ids=(), names=(), command_id):
        self._admit()
        records = self._records(records)
        self._use_quote(ticket, accepted=True)
        def plan():
            inputs = self._inputs(ids, names, ticket)
            if self.installed_state.to_dict()['engine']['lifecycle']['risk']['active']:
                if records:
                    raise source.ProviderSourceError()
                history = None
            else:
                history = self._build_history(records, inputs)
            return lifecycle.prepare_decision(self.installed_state, ticket.frame, history, inputs)
        return await self._owned(lambda: self._plan_submit(plan, 'decision', command_id, ticket))

    async def control(self, action, *, ids=(), names=(), command_id, ticket=None,
                      records=(), trip_id=None):
        self._admit()
        records = self._records(records)
        if action == 'recover':
            self._use_quote(ticket, accepted=True)
        elif ticket is not None or records:
            self._reject('control_observation_invalid')
        def plan():
            inputs = self._inputs(ids, names, ticket)
            history = self._build_history(records, inputs) if action == 'recover' else None
            return lifecycle.prepare_control(self.installed_state, action, inputs,
                frame=None if ticket is None else ticket.frame, history=history, trip_id=trip_id)
        return await self._owned(lambda: self._plan_submit(plan, 'control', command_id, ticket))
