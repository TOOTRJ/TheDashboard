"""One held B2 Stop dispatch gated by an independently authenticated reader."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from threading import Lock
from typing import Callable

from ..market import provider_acquisition_v3 as wire


NATIVE_POLICY_SHA256 = 'e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0'


class StopDispatchError(RuntimeError):
    """Fixed error text keeps credential and database response details private."""


@dataclass(frozen=True, slots=True)
class StopIntentPins:
    """Trusted pins from the selected scope, installation and K2 handoff."""

    scope_wire: bytes
    reserved_stop_id: str
    installation_id: str
    native_package_sha256: str
    effective_catalog_sha256: str
    handoff_sha256: str
    control_binding_id: str


class StopDispatch:
    """Hold one exact Stop. Dispatch once only after committed intent readback.

    The caller supplies an independent scoped reader and a separate control
    submit transport. The native getter authenticates the reader. This guard
    validates the returned bytes against already trusted scope and handoff
    pins. The original-operation getter remains responsible for the Stop
    outcome. A lost submit response requires reconciliation of the same
    original. Creating another guard cannot establish permission to retry it.
    """

    def __init__(self, command_wire: bytes, pins: StopIntentPins):
        try:
            if type(pins) is not StopIntentPins:
                raise wire.AcquisitionError()
            scope = wire.fields(wire.read_json(pins.scope_wire, 512, exact=True),
                                {'owner_id', 'run_id', 'market_epoch'})
            for identity in scope.values():
                wire.uuid(identity)
            stop_id = wire.uuid(pins.reserved_stop_id)
            command = wire.fields(wire.read_json(command_wire, 4096, exact=True), {
                'format', 'native_policy_sha256', 'scope', 'action_id', 'action_kind',
                'expected_head', 'expected_fence_id', 'expected_fence_revision', 'body',
            })
            wire.require(
                command['format'] == 'ga-jupiter-b2-allocation-command-research-v3-v1'
                and command['native_policy_sha256'] == NATIVE_POLICY_SHA256
                and command['scope'] == scope and command['action_id'] == stop_id
                and command['action_kind'] == 'source_stop'
                and command['expected_fence_id'] is None
                and command['expected_fence_revision'] is None
            )
            head = wire.fields(command['expected_head'], {
                'native_sequence', 'native_head_sha256', 'previous_seal_sha256',
            })
            wire.counter(head['native_sequence'], minimum=3, maximum=15)
            wire.digest(head['native_head_sha256'])
            wire.require(head['previous_seal_sha256'] is None)
            body = wire.fields(command['body'], {'expected_control_sha256', 'expected_mode'})
            wire.digest(body['expected_control_sha256'])
            wire.require(body['expected_mode'] == 'open')

            command_sha256 = hashlib.sha256(command_wire).hexdigest()
            intent = wire.canonical({
                'format': 'ga-jupiter-b2-stop-intent-research-v3-v1',
                'installation_id': wire.uuid(pins.installation_id),
                'native_package_sha256': wire.digest(pins.native_package_sha256),
                'effective_catalog_sha256': wire.digest(pins.effective_catalog_sha256),
                'handoff_sha256': wire.digest(pins.handoff_sha256),
                'control_binding_id': wire.uuid(pins.control_binding_id),
                'original_command_wire': command_wire.decode('utf-8'),
                'original_command_sha256': command_sha256,
            })
            wire.require(len(intent) <= 4096)
            query = wire.canonical({
                'format': 'ga-jupiter-b2-original-query-research-v3-v1',
                'native_policy_sha256': NATIVE_POLICY_SHA256,
                'scope': scope,
                'target_kind': 'source_stop',
                'target_id': stop_id,
                'expected_original_command_sha256': command_sha256,
                'correlation': {'kind': 'original_action_id', 'id': stop_id},
            })
            observation = wire.canonical({
                'format': 'ga-jupiter-b2-stop-intent-observation-research-v3-v1',
                'scope': scope,
                'action_id': stop_id,
                'resolution': 'observed_committed_exact',
                'intent_wire': intent.decode('utf-8'),
            })
        except wire.AcquisitionError:
            raise StopDispatchError('Original Stop or its trusted pins are invalid') from None
        self._command_wire = command_wire
        self._query_wire = query
        self._committed_observation = observation
        self._attempt_lock = Lock()
        self._attempted = False

    def dispatch(self, read_intent: Callable[[bytes], bytes],
                 submit_stop: Callable[[bytes], None]) -> None:
        with self._attempt_lock:
            if self._attempted:
                raise StopDispatchError('Original Stop dispatch attempt was already used')
            self._attempted = True
        try:
            observed = read_intent(self._query_wire)
        except Exception:
            raise StopDispatchError('Committed original Stop intent could not be read') from None
        # The entire positive observation is deterministic. Byte equality also
        # refuses noncanonical encodings, provisional or absent replies and
        # mismatches in any nested command or trusted intent pin.
        if type(observed) is not bytes or observed != self._committed_observation:
            raise StopDispatchError('Committed original Stop intent could not be verified')
        try:
            submit_stop(self._command_wire)
        except Exception:
            raise StopDispatchError('Original Stop submit outcome requires independent reconciliation') from None
