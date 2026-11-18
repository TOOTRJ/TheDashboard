"""Owned native tests for incomplete Capture and archival retention after Stop or expiry."""
from __future__ import annotations

import copy
import os
import unittest
from uuid import UUID

from tests.postgres.allocation_control_v3_fixture import (
    AllocationFixture, BEGIN, LATE_CAPTURE_POLICY_SHA256, N, SETTINGS, canonical, literal, sha,
)
from tests.postgres.harness import OPT_IN
from tests.postgres.test_allocation_capture_join_v3 import (
    AllocationCaptureJoinNativeCase, RAW_BODIES, WIRE_FIELDS, as_wire, decode_wire, synthetic_capture,
)
from tests.postgres.test_allocation_control_v3 import submit_handoff_original
from vonneumann.market import provider_acquisition_v3 as acquisition, source_admission_v3 as source
from vonneumann.research.native_stop_reconciliation import StopReconciliation


_DISPOSITION = {
    'not_received': (0, 0, 'request_unavailable'),
    'partial_discarded': (1, 1, 'response_overflow'),
    'withheld': (2, 2, 'credential_echo_withheld'),
    'captured_original': (2, 3, 'cleanup_incomplete'),
}
_DIAGNOSTIC_PIN_FIELDS = (
    'record_id', 'provider_family', 'endpoint_binding_id', 'request_sha256',
    'request_started_wall_us', 'request_started_monotonic_us', 'received_wall_us',
    'received_monotonic_us', 'http_status',
)


def incomplete_capture(reservation, prepared, disposition):
    index, prefix_count, failure_code = _DISPOSITION[disposition]
    original = synthetic_capture(reservation, prepared).to_dict()
    original_capsules = original['capsule_wires']
    request_pin = decode_wire(original_capsules[index].encode())
    diagnostic = {field: request_pin[field] for field in _DIAGNOSTIC_PIN_FIELDS}
    diagnostic.update(body_state=disposition, incomplete=True, failure_code=failure_code)
    if disposition in ('not_received', 'partial_discarded'):
        diagnostic.update(received_wall_us=None, received_monotonic_us=None)
    if disposition == 'not_received':
        diagnostic['http_status'] = None
    original.update(capsule_wires=original_capsules[:prefix_count], diagnostics=[diagnostic],
                    collection_completed=False, failure_code=failure_code)
    return source.validate_capture(reservation, source.envelope('Capture', original))


class AllocationCaptureRetentionNativeCase(AllocationCaptureJoinNativeCase):
    def _create_fixture(self):
        return AllocationFixture(self.db, creator_edges=True, joined=True, late_capture=True)

    def collect_provider(self, prepared):
        self.provider_calls.append(prepared)
        self.assertIs(prepared, self.prepared)
        return incomplete_capture(self.reservation, prepared, self.disposition)

    def capture_command(self, capture):
        command = self.fixture.command(self.scope, 'capture_retention', action_id=self.packet_ids['capture_id'])
        self.assertEqual(command['native_policy_sha256'], LATE_CAPTURE_POLICY_SHA256)
        self.assertIsNone(command['expected_fence_id'])
        self.assertIsNone(command['expected_fence_revision'])
        command['body'] = dict(reservation_action_id=self.packet_ids['reservation_id'], capture_wire=capture.wire.decode())
        return command

    def query_without_capture(self, capture_id):
        query = super().query_without_capture(capture_id)
        query['native_policy_sha256'] = LATE_CAPTURE_POLICY_SHA256
        return query

    def assert_retained(self, command, capture, sequence, *, previous_head_sha256=None):
        reply = self.read_capture(self.packet_ids['capture_id'])
        self.assertEqual(reply, self.read_original(command))
        self.assertEqual(self.assert_original(reply, command, sequence, previous_head_sha256=previous_head_sha256), dict(
            reservation_action_id=self.reserve['action_id'], original_a1_reservation_sha256=self.reservation.sha256,
            original_a1_capture_sha256=capture.sha256, collection_completed=False, eligibility=False, terminal=False,
        ))
        returned_command = decode_wire(reply['original_command_wire'].encode())
        retained = source.wire(returned_command['body']['capture_wire'], 'Capture')
        self.assertEqual(retained.wire, capture.wire)
        source.validate_capture(self.reservation, retained)
        capsule_wires = retained.to_dict()['capsule_wires']
        self.assertEqual(tuple(acquisition.decode_capsule(raw.encode(), self.prepared.binding).raw_body
                               for raw in capsule_wires), RAW_BODIES[:_DISPOSITION[self.disposition][1]])
        self.assertEqual(retained.to_dict()['diagnostics'][0]['body_state'], self.disposition)
        before_replay = self.fixture.snapshot()
        replay = decode_wire(self.submit_bytes(as_wire(command)))
        self.assertEqual([replay[key] for key in WIRE_FIELDS], [reply[key] for key in WIRE_FIELDS])
        self.assertEqual(self.fixture.snapshot(), before_replay)
        self.assert_no_recollection(1)
        self.assert_reserved_ids()
        return reply

    def assert_original_wires(self, before, after):
        self.assertEqual([before[key] for key in WIRE_FIELDS], [after[key] for key in WIRE_FIELDS])

    def assert_same_source_state(self, before, after):
        changed = {key for key in before if before[key] != after[key]}
        self.assertEqual(changed, {'native_sequence', 'native_head_sha256'})

    def wait_for_fence_expiry(self):
        renew = self.read_original(self.plan['renew'])
        fence = decode_wire(renew['original_result_wire'].encode())['result_body']['original_fence_record']
        expires_us = int(fence['expires_at_us'])
        clock = 'SELECT floor(extract(epoch FROM clock_timestamp())*1000000)::bigint;'
        before = int(self.db.scalar(clock))
        self.assertLess(before, expires_us)
        self.assertLessEqual(expires_us - before, 60_000_000)
        # Bound each server statement while waiting on the actual database clock.
        for _ in range(3):
            observed = int(self.db.scalar(clock))
            if observed >= expires_us:
                break
            target = min(expires_us + 100_000, observed + 30_000_000)
            self.db.scalar(f'SELECT pg_sleep_until(to_timestamp({target}::numeric/1000000));', timeout=34)
        self.assertGreaterEqual(int(self.db.scalar(clock)), expires_us)
        return expires_us

    def assert_diagnostic_refused(self, command, **altered_fields):
        bad = copy.deepcopy(command)
        capture = decode_wire(bad['body']['capture_wire'].encode())
        capture['diagnostics'][0].update(altered_fields)
        bad['body']['capture_wire'] = canonical(capture)
        before = self.fixture.snapshot()
        self.assert_refused(bad, self.recorder, 'b3_diagnostic_conflict')
        self.assertEqual(self.fixture.snapshot(), before)
        self.assert_capture_unknown(5)


@unittest.skipUnless(os.environ.get(OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class AllocationCaptureRetentionNativeTests(AllocationCaptureRetentionNativeCase):
    def test_committed_stop_preserves_exact_late_withheld_capture(self):
        self.disposition = 'withheld'
        reserved, capture = self.reserve_and_collect()
        command = self.capture_command(capture)
        command_wire = as_wire(command)
        stop = self.stop_command()
        self.db.sql(BEGIN + SETTINGS + self.sql_call('record_stop_intent', as_wire(stop)) + 'COMMIT;\n',
                    role=self.control)
        self.assert_refused(command, self.recorder, 'b2_stop_intent_pending')
        self.assert_capture_unknown(5)
        self.stop_with_dispatch_gate(stop, 6, already_registered=True)
        self.assert_capture_unknown(6)
        stopped = self.assert_head(6, 'stopped')
        stop_reply = self.read_original(stop)
        self.assertIsNone(stopped['active_fence_id'])

        incorrect_ancestor = copy.deepcopy(command)
        incorrect_ancestor['expected_head']['native_head_sha256'] = 'f' * 64
        self.assert_refused(incorrect_ancestor, self.recorder, 'b3_capture_ancestor_refused')
        rebased = self.capture_command(capture)
        self.assertEqual(rebased['expected_head']['native_sequence'], '6')
        self.assert_refused(rebased, self.recorder, 'b3_capture_ancestor_refused')
        foreign = copy.deepcopy(command)
        foreign['scope']['run_id'] = str(UUID(int=994401))
        self.assert_refused(foreign, self.recorder, 'b2_actor_scope_refused')
        wrong_id = dict(command, action_id=str(UUID(int=994402)))
        self.assert_refused(wrong_id, self.recorder, 'b3_capture_shape')
        wrong_reservation = copy.deepcopy(command)
        wrong_reservation['body']['reservation_action_id'] = str(UUID(int=994404))
        self.assert_refused(wrong_reservation, self.recorder, 'b3_capture_refused')
        self.assert_capture_unknown(6)
        self.assert_journal([self.reserve, stop])

        self.assertEqual(as_wire(command), command_wire)
        submit_handoff_original(self.fixture, command, self.recorder)
        self.assert_retained(command, capture, 7, previous_head_sha256=stopped['native_head_sha256'])
        self.assert_same_source_state(stopped, self.assert_head(7, 'stopped'))
        self.assert_original_wires(stop_reply, self.read_original(stop))
        reconciliation = StopReconciliation(as_wire(stop), self.stop_pins()).read(self.get_original_bytes)
        self.assertEqual(reconciliation.resolution, 'observed_committed_exact')
        self.assertEqual(reconciliation.receipt_sha256, sha(stop_reply['original_receipt_wire']))
        self.assertEqual(reconciliation.stop_head_sha256, stopped['native_head_sha256'])
        self.assert_original_wires(reserved, self.read_original(self.reserve))
        scope_wire = literal(canonical(self.scope['scope']))
        self.assertEqual(self.db.scalar(f"SELECT accounting_wire::jsonb->>'Stop_reserve_consumed' FROM {N}.scope_state "
                                        f"WHERE scope_wire={scope_wire};"), 'true')
        self.assert_journal([self.reserve, stop, command])

    def test_elapsed_fence_retains_exact_original_with_captured_diagnostic(self):
        self.disposition = 'captured_original'
        reserved, capture = self.reserve_and_collect()
        command = self.capture_command(capture)
        before = self.assert_head(5, 'open')
        self.assert_diagnostic_refused(command, request_started_monotonic_us='0')
        authorization_query = dict(
            format='ga-jupiter-b3-collection-authorization-query-v2', scope=self.scope['scope'],
            reservation_id=self.reserve['action_id'], reservation_command_sha256=sha(as_wire(self.reserve)),
            head_sha256=before['native_head_sha256'], record_id=self.prepared.price_record_id,
            provider_family='jupiter-price-v3', request_sha256=sha(acquisition.public_request('jupiter-price-v3')),
        )
        authorize = SETTINGS + self.sql_call('get_original', as_wire(authorization_query))
        authorization = decode_wire(self.db.scalar(authorize, role=self.recorder).encode())
        self.assertEqual(authorization['query_sha256'], sha(as_wire(authorization_query)))
        expires_us = self.wait_for_fence_expiry()
        self.assertLess(int(authorization['observed_at_us']), expires_us)
        self.assert_sql_refused(authorize, self.recorder, 'b3_collection_fence_refused')
        self.assertEqual(self.fixture.head(self.scope), before)
        submit_handoff_original(self.fixture, command, self.recorder)
        retained = self.assert_retained(command, capture, 6)
        receipt = decode_wire(retained['original_receipt_wire'].encode())
        self.assertGreaterEqual(int(receipt['commit_processing_observation']['observed_at_us']), expires_us)
        self.assert_same_source_state(before, self.assert_head(6, 'open'))
        self.assert_original_wires(reserved, self.read_original(self.reserve))
        self.assert_journal([self.reserve, command])

    def test_not_received_diagnostic_retains_no_capsule(self):
        self.disposition = 'not_received'
        _, capture = self.reserve_and_collect()
        command = self.capture_command(capture)
        self.assert_diagnostic_refused(command, received_wall_us='1800000000100000', received_monotonic_us='9900000')
        submit_handoff_original(self.fixture, command, self.recorder)
        self.assert_retained(command, capture, 6)
        self.assert_head(6, 'open')
        self.assert_journal([self.reserve, command])

    def test_partial_discarded_diagnostic_preserves_prefix_and_refuses_claimed_payload(self):
        self.disposition = 'partial_discarded'
        _, capture = self.reserve_and_collect()
        command = self.capture_command(capture)
        self.assert_diagnostic_refused(command, response_base64='ZmFicmljYXRlZA==')
        self.assert_diagnostic_refused(command, endpoint_binding_id=str(UUID(int=994403)))
        self.assert_diagnostic_refused(command, request_sha256='f' * 64)
        submit_handoff_original(self.fixture, command, self.recorder)
        self.assert_retained(command, capture, 6)
        self.assert_head(6, 'open')
        self.assert_journal([self.reserve, command])
