"""Read-only reconciliation of an original Stop after a worker restart."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, Literal

from ..market import provider_acquisition_v3 as wire
from .native_stop_dispatch import NATIVE_POLICY_SHA256, StopIntentPins

_LIMITS = dict.fromkeys((
    'provider_attested', 'calibrated_clock', 'hosted_authority',
    'running_authority', 'live_trading_authority', 'model_native_join',
), False)
_HEAD_KEYS = {'native_sequence', 'native_head_sha256', 'previous_seal_sha256'}


@dataclass(frozen=True, slots=True)
class StopReconciliationResult:
    resolution: Literal['observed_committed_exact', 'unknown']
    receipt_sha256: str | None = None
    stop_head_sha256: str | None = None


def _format(record: str) -> str:
    return f'ga-jupiter-b2-{record}-research-v3-v1'


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _clock(value: dict) -> int:
    wire.fields(value, {'observed_at_us', 'wall_lower_us', 'wall_upper_us'})
    observed = wire.counter(value['observed_at_us'])
    wire.require(value['wall_lower_us'] == value['wall_upper_us'] == value['observed_at_us'])
    return observed


def _pins(dependencies: list, limit: int) -> dict:
    wire.require(type(dependencies) is list and 0 < len(dependencies) <= limit)
    pins = {}
    for pin in dependencies:
        wire.fields(pin, {'semantic_kind', 'original_id', 'original_wire', 'wire_sha256', 'wire_bytes'})
        key = (pin['semantic_kind'], wire.uuid(pin['original_id']), wire.digest(pin['wire_sha256']))
        raw = pin['original_wire'].encode('utf-8')
        wire.require(type(key[0]) is str and key not in pins
                     and pin['wire_bytes'] == str(len(raw)) and _sha(raw) == key[2])
        pins[key] = raw
    wire.require(list(pins) == sorted(pins))
    return pins


class StopReconciliation:
    """The callback reads the held native getter through an independent reader.

    An unknown result supplies no dispatch permission. This adapter has no
    write callback. The database getter validates the exact stored Stop chain,
    including when a later archival Capture is the current head.
    """

    def __init__(self, command_wire: bytes, pins: StopIntentPins):
        wire.require(type(pins) is StopIntentPins)
        scope = wire.fields(wire.read_json(pins.scope_wire, 512, exact=True),
                            {'owner_id', 'run_id', 'market_epoch'})
        for identity in scope.values():
            wire.uuid(identity)
        stop_id = wire.uuid(pins.reserved_stop_id)
        command = wire.fields(wire.read_json(command_wire, 4096, exact=True), {
            'format', 'native_policy_sha256', 'scope', 'action_id', 'action_kind',
            'expected_head', 'expected_fence_id', 'expected_fence_revision', 'body',
        })
        wire.require(command['format'] == _format('allocation-command')
                     and command['native_policy_sha256'] == NATIVE_POLICY_SHA256
                     and command['scope'] == scope and command['action_id'] == stop_id
                     and command['action_kind'] == 'source_stop'
                     and command['expected_fence_id'] is None
                     and command['expected_fence_revision'] is None)
        head = wire.fields(command['expected_head'], _HEAD_KEYS)
        self._sequence = wire.counter(head['native_sequence'], minimum=3, maximum=15) + 1
        self._previous_head = wire.digest(head['native_head_sha256'])
        wire.require(head['previous_seal_sha256'] is None)
        body = wire.fields(command['body'], {'expected_control_sha256', 'expected_mode'})
        wire.require(body['expected_mode'] == 'open')
        self._control_sha256 = wire.digest(body['expected_control_sha256'])
        self._package_sha256 = wire.digest(pins.native_package_sha256)
        self._catalog_sha256 = wire.digest(pins.effective_catalog_sha256)
        self._command = command_wire.decode('utf-8')
        self._common = dict(native_policy_sha256=NATIVE_POLICY_SHA256, scope=scope, limits=_LIMITS)
        self._target = dict(target_id=stop_id, target_kind='source_stop')
        self._action = dict(action_id=stop_id, action_kind='source_stop', original_command_sha256=_sha(command_wire))
        self._query = wire.canonical(dict(format=_format('original-query'),
            native_policy_sha256=NATIVE_POLICY_SHA256, scope=scope, **self._target,
            expected_original_command_sha256=self._action['original_command_sha256'],
            correlation={'kind': 'original_action_id', 'id': stop_id}))

    def read(self, independent_get_original: Callable[[bytes], bytes]) -> StopReconciliationResult:
        try:
            raw = independent_get_original(self._query)
        except Exception:
            return StopReconciliationResult('unknown')
        try:
            reply = wire.read_json(raw, 8 * 1024 * 1024, exact=True)
            if type(reply) is not dict or reply.get('format') != _format('original-reply'):
                return StopReconciliationResult('unknown')
            return self._verify_committed(reply)
        except (wire.AcquisitionError, AttributeError, KeyError, TypeError, UnicodeError, ValueError):
            return StopReconciliationResult('unknown')

    def _verify_committed(self, reply: dict) -> StopReconciliationResult:
        expected = dict(format=_format('original-reply'), **self._common, **self._target,
                        original_command_wire=self._command)
        wire.fields(reply, {*expected, 'original_result_wire', 'original_receipt_wire',
                            'dependencies', 'observed_head'})
        wire.require(all(reply[key] == value for key, value in expected.items()))
        complete = _pins(reply['dependencies'], 70)

        result_wire = reply['original_result_wire'].encode('utf-8')
        result = wire.read_json(result_wire, 131072, exact=True)
        expected_result = dict(format=_format('allocation-result'), **self._common, **self._action,
                               native_sequence=str(self._sequence))
        wire.fields(result, {*expected_result, 'dependencies', 'result_body'})
        wire.require(all(result[key] == value for key, value in expected_result.items()))
        direct = _pins(result['dependencies'], 7)
        wire.require(direct.items() <= complete.items())
        fence_pins = [(key, raw) for key, raw in direct.items() if key[0] == 'native_fence_record']
        wire.require(len(fence_pins) == 1)
        fence_key, fence_wire = fence_pins[0]
        fence = wire.read_json(fence_wire, 16384, exact=True)
        wire.require(fence['scope'] == self._common['scope'] and fence['fence_id'] == fence_key[1])
        revision = wire.counter(fence['revision'], minimum=1, maximum=14)
        control_pins = [(key, raw) for key, raw in direct.items()
                        if key[0] == 'native_command' and key[2] == self._control_sha256]
        wire.require(len(control_pins) == 1)
        control_key, control_wire = control_pins[0]
        control = wire.read_json(control_wire, 16384, exact=True)
        wire.require(control['scope'] == self._common['scope'] and control['action_id'] == control_key[1]
                     and control['native_policy_sha256'] == NATIVE_POLICY_SHA256
                     and control['action_kind'] == 'source_resume')
        wire.require(result['result_body'] == dict(previous_mode='open', resulting_mode='stopped',
            previous_control_sha256=self._control_sha256, resulting_fence_revision=str(revision + 1)))
        result_sha = _sha(result_wire)

        receipt_wire = reply['original_receipt_wire'].encode('utf-8')
        receipt = wire.read_json(receipt_wire, 4096, exact=True)
        expected_receipt = dict(format=_format('allocation-receipt'), **self._common, **self._action,
            native_sequence=str(self._sequence), result_sha256=result_sha,
            previous_native_head_sha256=self._previous_head, admission_observation=None,
            native_package_sha256=self._package_sha256, catalog_manifest_sha256=self._catalog_sha256)
        wire.fields(receipt, {*expected_receipt, 'final_function_observation', 'commit_processing_observation'})
        wire.require(all(receipt[key] == value for key, value in expected_receipt.items()))
        wire.require(_clock(receipt['final_function_observation']) <= _clock(receipt['commit_processing_observation']))

        receipt_sha = _sha(receipt_wire)
        journal = dict(native_sequence=str(self._sequence), **self._action,
            original_result_sha256=result_sha, original_receipt_sha256=receipt_sha,
            previous_native_head_sha256=self._previous_head)
        stop_head = _sha(wire.canonical(journal))
        observed = wire.fields(reply['observed_head'], _HEAD_KEYS)
        observed_sequence = wire.counter(observed['native_sequence'], minimum=self._sequence, maximum=16)
        observed_hash = wire.digest(observed['native_head_sha256'])
        wire.require(observed['previous_seal_sha256'] is None
                     and (observed_hash == stop_head) == (observed_sequence == self._sequence))
        return StopReconciliationResult('observed_committed_exact', receipt_sha, stop_head)
