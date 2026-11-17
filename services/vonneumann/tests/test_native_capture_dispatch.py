"""Offline worker collection gate checks using a held synthetic packet."""
import copy
import json
from pathlib import Path
import unittest
from uuid import UUID

from vonneumann.market.provider_acquisition_v3 import canonical
from vonneumann.market.provider_recorded_transport_v3 import PreparedPacket
from vonneumann.market.source_admission_v3 import issuer, sha, wire
from vonneumann.research.native_capture_dispatch import NativeCaptureDispatchError, ReservationCollection

_B2_POLICY = 'e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0'
_PACKET_POLICY = 'f' * 64
_PACKAGE = 'a' * 64
_CATALOG = 'b' * 64
_FIXTURE = Path(__file__).with_name('postgres') / 'durable_acquisition_fixture_v3.json'


def _id(number):
    return str(UUID(int=number))


def _format(name):
    return f'ga-jupiter-b2-{name}-research-v3-v1'


def _pin(kind, identity, value):
    raw = canonical(value)
    return dict(semantic_kind=kind, original_id=identity, original_wire=raw.decode(),
                wire_sha256=sha(raw), wire_bytes=str(len(raw)))


class NativeCaptureDispatchTests(unittest.TestCase):
    def setUp(self):
        row = json.loads(_FIXTURE.read_bytes())[0]
        self.reservation = wire(row['reservation_wire'], 'Reservation')
        reservation = self.reservation.to_dict()
        self.capture = wire(row['capture_wire'], 'Capture')
        self.prepared = PreparedPacket(issuer(reservation['issuer']), reservation['price_record_id'],
            reservation['genesis_record_id'], reservation['block_time_record_id'], reservation['observation_id'],
            int(reservation['genesis_rpc_id']), int(reservation['block_time_rpc_id']))
        self.scope = reservation['scope']
        self.action_id = reservation['reservation_id']
        extra_ids = dict(read_observation_id=_id(701), availability_id=_id(702),
                         closure_id=_id(703), reconcile_id=_id(704))
        self.command = dict(format=_format('allocation-command'), native_policy_sha256=_PACKET_POLICY,
            scope=self.scope, action_id=self.action_id, action_kind='packet_reservation',
            expected_head=dict(native_sequence='4', native_head_sha256='a' * 64, previous_seal_sha256=None),
            expected_fence_id=_id(705), expected_fence_revision='2',
            body=dict(reservation_wire=row['reservation_wire'], prepared_packet_wire=self.prepared.wire.decode(), **extra_ids))
        self.command_wire = canonical(self.command)
        self.common = dict(native_policy_sha256=_PACKET_POLICY, scope=self.scope, limits={
            'provider_attested': False, 'calibrated_clock': False, 'hosted_authority': False,
            'running_authority': False, 'live_trading_authority': False, 'model_native_join': False,
        })
        self.action = dict(action_id=self.action_id, action_kind='packet_reservation',
                           original_command_sha256=sha(self.command_wire))
        self.provisional = canonical(dict(format=_format('provisional'), **self.common, **self.action,
                                          pending_commit=True))
        renew = dict(scope=self.scope, action_id=_id(706), action_kind='fence_renew', native_policy_sha256=_B2_POLICY)
        fence = dict(scope=self.scope, fence_id=_id(705), revision='2',
            holder_principal_binding_id=reservation['issuer_principal_binding_id'],
            acquisition_epoch=self.prepared.binding.acquisition_epoch, issued_at_us='10', expires_at_us='70')
        pins = [_pin('native_command', renew['action_id'], renew), _pin('native_fence_record', fence['fence_id'], fence)]
        packet_ids = {key: reservation[key] for key in (
            'reservation_id', 'capture_id', 'admission_id', 'observation_id',
            'price_record_id', 'genesis_record_id', 'block_time_record_id',
        )}
        packet_ids.update(extra_ids)
        body = dict(packet_ids=packet_ids, original_a1_reservation_sha256=self.reservation.sha256,
                    prepared_packet_sha256=sha(self.prepared.wire), capture_status='unresolved')
        self.result = dict(format=_format('allocation-result'), **self.common, **self.action,
                           native_sequence='5', result_body=body, dependencies=pins)
        self.receipt = dict(format=_format('allocation-receipt'), **self.common, **self.action,
            native_sequence='5', result_sha256=sha(canonical(self.result)),
            previous_native_head_sha256=self.command['expected_head']['native_head_sha256'],
            admission_observation=None, final_function_observation=dict(observed_at_us='20', wall_lower_us='20', wall_upper_us='20'),
            commit_processing_observation=dict(observed_at_us='21', wall_lower_us='21', wall_upper_us='21'),
            native_package_sha256=_PACKAGE, catalog_manifest_sha256=_CATALOG)
        journal = dict(native_sequence='5', **self.action, original_result_sha256=sha(canonical(self.result)),
            original_receipt_sha256=sha(canonical(self.receipt)), previous_native_head_sha256=self.receipt['previous_native_head_sha256'])
        self.reply = dict(format=_format('original-reply'), **self.common, target_id=self.action_id,
            target_kind='packet_reservation', original_command_wire=self.command_wire.decode(),
            original_result_wire=canonical(self.result).decode(), original_receipt_wire=canonical(self.receipt).decode(),
            dependencies=pins, observed_head=dict(native_sequence='5', native_head_sha256=sha(canonical(journal)),
                                                 previous_seal_sha256=None))
        self.calls = []

    def gate(self, command=None):
        return ReservationCollection(self.command_wire if command is None else command, self.prepared,
            expected_policy_sha256=_PACKET_POLICY, expected_native_package_sha256=_PACKAGE,
            expected_catalog_manifest_sha256=_CATALOG)

    def submit(self, raw):
        self.assertEqual(raw, self.command_wire)
        self.calls.append('submit')
        return self.provisional

    def read(self, query):
        value = json.loads(query)
        self.assertEqual(value, dict(format=_format('original-query'), native_policy_sha256=_PACKET_POLICY,
            scope=self.scope, target_id=self.action_id, target_kind='packet_reservation',
            expected_original_command_sha256=sha(self.command_wire), correlation=dict(kind='original_action_id', id=self.action_id)))
        self.assertEqual(query, canonical(value))
        self.calls.append('read')
        return canonical(self.reply)

    def collect(self, prepared):
        self.assertIs(prepared, self.prepared)
        self.calls.append('collect')
        return self.capture

    def test_ack_then_exact_current_read_allows_one_attempt(self):
        gate = self.gate()
        self.assertEqual(gate.collect(self.submit, self.read, self.collect).wire, self.capture.wire)
        with self.assertRaises(NativeCaptureDispatchError):
            gate.collect(self.submit, self.read, self.collect)
        self.assertEqual(self.calls, ['submit', 'read', 'collect'])

    def test_lost_ack_and_existing_replay_never_call_reader_or_provider(self):
        def lose_ack(_):
            raise TimeoutError('synthetic acknowledgement loss')
        for submit in (lose_ack, lambda _: canonical(self.reply), lambda _: self.provisional + b'\n'):
            with self.subTest(submit=submit), self.assertRaises(NativeCaptureDispatchError):
                self.gate().collect(submit, self.read, self.collect)
        self.assertEqual(self.calls, [])

    def test_absent_changed_or_stale_readback_denies_collection(self):
        stale = copy.deepcopy(self.reply)
        stale['observed_head']['native_sequence'] = '6'
        bad_receipt = copy.deepcopy(self.reply)
        bad_receipt['original_receipt_wire'] = canonical(dict(self.receipt, catalog_manifest_sha256='c' * 64)).decode()
        bad_pins = dict(self.reply, dependencies=self.reply['dependencies'][:1])
        for reply in ({'resolution': 'observed_absent_unknown'}, stale, bad_receipt, bad_pins):
            with self.subTest(keys=sorted(reply)), self.assertRaises(NativeCaptureDispatchError):
                self.gate().collect(self.submit, lambda _: canonical(reply), self.collect)
        self.assertEqual(self.calls, ['submit'] * 4)

    def test_bound_plan_and_eleven_unique_ids_before_submit(self):
        for field, altered in (('read_observation_id', self.action_id), ('prepared_packet_wire', '{}')):
            command = copy.deepcopy(self.command)
            command['body'][field] = altered
            with self.subTest(field=field), self.assertRaises(NativeCaptureDispatchError):
                self.gate(canonical(command))
        self.assertEqual(self.calls, [])

    def test_failed_collection_cannot_restart_on_same_gate(self):
        gate = self.gate()
        with self.assertRaises(NativeCaptureDispatchError):
            gate.collect(self.submit, self.read, lambda _: None)
        with self.assertRaises(NativeCaptureDispatchError):
            gate.collect(self.submit, self.read, self.collect)
        self.assertEqual(self.calls, ['submit', 'read'])
