"""One local collection attempt after an exact native Reservation commits."""
from __future__ import annotations

from threading import Lock

from ..market import provider_acquisition_v3 as codec
from ..market import source_admission_v3 as source
from ..market.provider_recorded_transport_v3 import PreparedPacket

_KIND = 'packet_reservation'
_B2_CONTROL_POLICY_SHA256 = 'e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0'
_A1_IDS = (
    'reservation_id', 'capture_id', 'admission_id', 'observation_id',
    'price_record_id', 'genesis_record_id', 'block_time_record_id',
)
_NATIVE_IDS = ('read_observation_id', 'availability_id', 'closure_id', 'reconcile_id')
_LIMITS = dict.fromkeys((
    'provider_attested', 'calibrated_clock', 'hosted_authority',
    'running_authority', 'live_trading_authority', 'model_native_join',
), False)
_HEAD_KEYS = {'native_sequence', 'native_head_sha256', 'previous_seal_sha256'}
_COMMAND_KEYS = {
    'format', 'native_policy_sha256', 'scope', 'action_id', 'action_kind',
    'expected_head', 'expected_fence_id', 'expected_fence_revision', 'body',
}
_REPLY_KEYS = {
    'format', 'native_policy_sha256', 'scope', 'target_id', 'target_kind',
    'original_command_wire', 'original_result_wire', 'original_receipt_wire',
    'dependencies', 'observed_head', 'limits',
}


class NativeCaptureDispatchError(ValueError):
    """The original reservation cannot authorize provider collection."""

    def __init__(self):
        super().__init__('Native collection refused or unresolved')


def _format(record):
    return f'ga-jupiter-b2-{record}-research-v3-v1'


def _utc(value):
    codec.fields(value, {'observed_at_us', 'wall_lower_us', 'wall_upper_us'})
    lower, observed, upper = (codec.counter(value[key], minimum=1)
        for key in ('wall_lower_us', 'observed_at_us', 'wall_upper_us'))
    codec.require(lower <= observed <= upper)
    return observed


class ReservationCollection:
    """The submit callback returns only after COMMIT acknowledgment.

    The reader callback uses a separate authenticated reader connection and
    executes the supplied original query once. Callback identity and database
    target verification belong to the enclosing worker adapter.
    """

    def __init__(self, command_wire: bytes, prepared: PreparedPacket, *,
                 expected_policy_sha256: str, expected_native_package_sha256: str,
                 expected_catalog_manifest_sha256: str):
        try:
            self._package = codec.digest(expected_native_package_sha256)
            self._catalog = codec.digest(expected_catalog_manifest_sha256)
            policy = codec.digest(expected_policy_sha256)
            command = codec.read_json(command_wire, 16384, exact=True)
            codec.fields(command, _COMMAND_KEYS)
            codec.require(command['format'] == _format('allocation-command')
                          and command['action_kind'] == _KIND
                          and command['native_policy_sha256'] == policy)
            source.scope(command['scope'])
            codec.uuid(command['action_id'])
            self._fence_id = codec.uuid(command['expected_fence_id'])
            self._fence_revision = command['expected_fence_revision']
            codec.counter(self._fence_revision, maximum=16, minimum=1)
            head = command['expected_head']
            codec.fields(head, _HEAD_KEYS)
            codec.digest(head['native_head_sha256'])
            codec.require(head['previous_seal_sha256'] is None)
            self._sequence = str(codec.counter(head['native_sequence'], maximum=14, minimum=1) + 1)
            self._previous_head = head['native_head_sha256']

            body = command['body']
            codec.fields(body, {'reservation_wire', 'prepared_packet_wire', *_NATIVE_IDS})
            self._reservation = source.wire(body['reservation_wire'], 'Reservation')
            reservation = self._reservation.to_dict()
            codec.require(reservation['scope'] == command['scope']
                          and reservation['reservation_id'] == command['action_id'])
            codec.require(type(prepared) is PreparedPacket and prepared.binding == source.issuer(reservation['issuer']))
            for key in ('observation_id', 'price_record_id', 'genesis_record_id', 'block_time_record_id'):
                codec.require(getattr(prepared, key) == reservation[key])
            for key in ('genesis_rpc_id', 'block_time_rpc_id'):
                codec.require(str(getattr(prepared, key)) == reservation[key])
            prepared_wire = prepared.wire
            codec.require(body['prepared_packet_wire'] == prepared_wire.decode('utf-8'))
            packet_ids = {key: reservation[key] for key in _A1_IDS}
            packet_ids.update((key, codec.uuid(body[key])) for key in _NATIVE_IDS)
            codec.require(len(set(packet_ids.values())) == len(packet_ids))
            self._fence_holder = reservation['issuer_principal_binding_id']
            self._result_body = dict(packet_ids=packet_ids,
                original_a1_reservation_sha256=self._reservation.sha256,
                prepared_packet_sha256=source.sha(prepared_wire), capture_status='unresolved')
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            raise NativeCaptureDispatchError() from None

        self._prepared = prepared
        self._command_wire = command_wire
        self._command_text = command_wire.decode('utf-8')
        self._common = dict(native_policy_sha256=policy, scope=command['scope'], limits=_LIMITS)
        self._target = dict(target_id=command['action_id'], target_kind=_KIND)
        self._action = dict(action_id=command['action_id'], action_kind=_KIND,
                            original_command_sha256=source.sha(command_wire))
        self._query = codec.canonical(dict(format=_format('original-query'),
            native_policy_sha256=policy, scope=command['scope'], **self._target,
            expected_original_command_sha256=self._action['original_command_sha256'],
            correlation={'kind': 'original_action_id', 'id': command['action_id']}))
        self._attempt_lock = Lock()
        self._attempted = False

    def collect(self, submit_recorder, independent_reader, collector):
        with self._attempt_lock:
            if self._attempted:
                raise NativeCaptureDispatchError()
            self._attempted = True
        try:
            submitted = submit_recorder(self._command_wire)
            expected = dict(format=_format('provisional'), **self._common,
                            **self._action, pending_commit=True)
            codec.require(type(submitted) is bytes and submitted == codec.canonical(expected))
            self._verify_committed(independent_reader(self._query))
            capture = collector(self._prepared)
            return source.validate_capture(self._reservation, capture)
        except Exception:
            # The original remains unresolved after a failed or lost reply.
            raise NativeCaptureDispatchError() from None

    def _verify_committed(self, wire):
        reply = codec.read_json(wire, 8 * 1024 * 1024, exact=True)
        codec.fields(reply, _REPLY_KEYS)
        expected = dict(format=_format('original-reply'), **self._common,
                        **self._target, original_command_wire=self._command_text)
        codec.require(all(reply[key] == value for key, value in expected.items()))
        codec.require(type(reply['dependencies']) is list and 0 < len(reply['dependencies']) <= 70)

        result_wire = reply['original_result_wire'].encode('utf-8')
        result = codec.read_json(result_wire, 16384, exact=True)
        expected_result = dict(format=_format('allocation-result'), **self._common,
            **self._action, native_sequence=self._sequence, result_body=self._result_body)
        codec.fields(result, {*expected_result, 'dependencies'})
        codec.require(all(result[key] == value for key, value in expected_result.items()))
        fence = self._verify_reservation_pins(result['dependencies'], reply['dependencies'])
        result_sha = source.sha(result_wire)

        receipt_wire = reply['original_receipt_wire'].encode('utf-8')
        receipt = codec.read_json(receipt_wire, 4096, exact=True)
        expected_receipt = dict(format=_format('allocation-receipt'), **self._common,
            **self._action, native_sequence=self._sequence, result_sha256=result_sha,
            previous_native_head_sha256=self._previous_head, admission_observation=None,
            native_package_sha256=self._package, catalog_manifest_sha256=self._catalog)
        codec.fields(receipt, {*expected_receipt, 'final_function_observation', 'commit_processing_observation'})
        codec.require(all(receipt[key] == value for key, value in expected_receipt.items()))
        final = _utc(receipt['final_function_observation'])
        committed = _utc(receipt['commit_processing_observation'])
        codec.require(codec.counter(fence['issued_at_us']) <= final <= committed < codec.counter(fence['expires_at_us']))

        journal = dict(native_sequence=self._sequence, **self._action,
            original_result_sha256=result_sha, original_receipt_sha256=source.sha(receipt_wire),
            previous_native_head_sha256=self._previous_head)
        codec.require(reply['observed_head'] == dict(native_sequence=self._sequence,
            native_head_sha256=source.sha(codec.canonical(journal)), previous_seal_sha256=None))

    def _verify_reservation_pins(self, direct, complete):
        codec.require(type(direct) is list and len(direct) == 2)
        verified = {}
        for pin in direct:
            codec.fields(pin, {'semantic_kind', 'original_id', 'original_wire', 'wire_sha256', 'wire_bytes'})
            kind = pin['semantic_kind']
            codec.require(kind in ('native_command', 'native_fence_record') and kind not in verified)
            codec.require(pin in complete)
            codec.uuid(pin['original_id'])
            body = pin['original_wire'].encode('utf-8')
            codec.require(pin['wire_bytes'] == str(len(body)) and pin['wire_sha256'] == source.sha(body))
            value = codec.read_json(body, 16384, exact=True)
            codec.require(value['scope'] == self._common['scope'])
            if kind == 'native_command':
                codec.require(value['action_id'] == pin['original_id'] and value['action_kind'] == 'fence_renew'
                              and value['native_policy_sha256'] == _B2_CONTROL_POLICY_SHA256)
            else:
                codec.require(value['fence_id'] == pin['original_id'] == self._fence_id
                              and value['revision'] == self._fence_revision
                              and value['holder_principal_binding_id'] == self._fence_holder
                              and value['acquisition_epoch'] == self._prepared.binding.acquisition_epoch)
            verified[kind] = value
        return verified['native_fence_record']
