"""Owned PostgreSQL handoff, reservation, capture and Stop composition proofs."""
from __future__ import annotations

import copy
import json
import os
import unittest
from contextlib import closing
from uuid import UUID

from tests.postgres.allocation_control_v3_fixture import (
    AllocationFixture, AllocationJoinedPostgres, BEGIN, N, SETTINGS, canonical, literal, sha,
)
from tests.postgres.harness import OPT_IN
from tests.postgres.test_allocation_control_v3 import (
    issue_handoff, prepare_handoff, submit_handoff_original,
)
from vonneumann.market import provider_acquisition_v3 as acquisition, source_admission_v3 as source
from vonneumann.market.provider_recorded_transport_v3 import PreparedPacket
from vonneumann.research.native_capture_dispatch import NativeCaptureDispatchError, ReservationCollection
from vonneumann.research.native_stop_dispatch import StopDispatch, StopIntentPins

A1_IDS = (
    'reservation_id', 'admission_id', 'capture_id', 'observation_id',
    'price_record_id', 'genesis_record_id', 'block_time_record_id',
)
NATIVE_IDS = ('read_observation_id', 'availability_id', 'closure_id', 'reconcile_id')
RAW_BODIES = (
    b'{"So11111111111111111111111111111111111111112":{"usdPrice":100.123456789012345678,"blockId":42,"decimals":9,"priceChange24h":null}}',
    b'{"id":1,"jsonrpc":"2.0","result":"5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"}',
    b'{"id":2,"jsonrpc":"2.0","result":1799999998}',
)
WIRE_FIELDS = ('original_command_wire', 'original_result_wire', 'original_receipt_wire')
SLEEP = 'SELECT pg_catalog.pg_sleep(8)'


def as_wire(value):
    return canonical(value).encode()


def decode_wire(raw):
    value = json.loads(raw)
    if as_wire(value) != raw:
        raise AssertionError('noncanonical database response')
    return value


def source_envelope(kind, scope, **fields):
    return source.envelope(kind, dict(
        format=source.FORMATS[kind], scope=scope, authority=dict(source.AUTHORITY),
        policy_sha256=source.POLICY_SHA256, **fields,
    ))


def joined_packet(scope, successor_binding, seed):
    genesis = scope['genesis']['initial_acquisition_spec']
    policy = scope['package']['policies']
    issuer = dict(
        **scope['scope'], acquisition_epoch=genesis['acquisition_epoch'],
        issuer_binding_id=genesis['issuer_binding_id'],
        endpoint_bindings=genesis['endpoint_bindings'],
        parser_policy_sha256=policy['acquisition_sha256'],
    )
    packet_ids = {name: str(UUID(int=seed + offset))
                  for offset, name in enumerate(A1_IDS + NATIVE_IDS)}
    reservation = source_envelope(
        'Reservation', scope['scope'], issuer=issuer, issuer_principal_binding_id=successor_binding,
        policies={key: policy[key] for key in source.FIELDS['Policies']},
        genesis_rpc_id='1', block_time_rpc_id='2',
        **{key: packet_ids[key] for key in A1_IDS},
    )
    prepared = PreparedPacket(
        source.issuer(issuer), **{key: packet_ids[key] for key in A1_IDS[3:]},
        genesis_rpc_id=1, block_time_rpc_id=2,
    )
    return reservation, prepared, packet_ids


def synthetic_capture(reservation, prepared):
    families = ('jupiter-price-v3', 'solana-rpc', 'solana-rpc')
    requests = (
        acquisition.public_request(families[0]),
        acquisition.public_request(families[1], rpc_method='getGenesisHash', rpc_id=1),
        acquisition.public_request(families[2], rpc_method='getBlockTime', rpc_id=2, slot=42),
    )
    ids = (prepared.price_record_id, prepared.genesis_record_id, prepared.block_time_record_id)
    capsules = [
        acquisition.capture_capsule(
            prepared.binding, record_id=record_id, provider_family=family, request=request,
            raw_body=raw, http_status=200, started_wall_us=1_800_000_000_000_000,
            received_wall_us=1_800_000_000_100_000, started_monotonic_us=9_800_000,
            received_monotonic_us=9_900_000,
        ).wire.decode()
        for family, request, raw, record_id in zip(families, requests, RAW_BODIES, ids, strict=True)
    ]
    held = reservation.to_dict()
    capture = source_envelope(
        'Capture', held['scope'], capture_id=held['capture_id'], observation_id=held['observation_id'],
        reservation_sha256=reservation.sha256, capsule_wires=capsules, diagnostics=[],
        collection_completed=True, eligibility=False, failure_code=None,
    )
    return source.validate_capture(reservation, capture)


class AllocationCaptureJoinNativeCase(unittest.TestCase):
    def _create_fixture(self):
        return AllocationFixture(self.db, creator_edges=True)

    def setUp(self):
        self.db = AllocationJoinedPostgres().start()
        self.addCleanup(self.db.close)
        self.fixture = self._create_fixture()
        self.plan = prepare_handoff(self.fixture)
        self.marker = issue_handoff(self.fixture, self.plan)
        self.scope = self.plan['scope']
        self.reader = self.scope['actors']['reader']
        self.control = self.scope['actors']['control']
        self.recorder = self.plan['successor']
        self.provider_calls = []
        for role in (self.reader, self.control, self.recorder):
            self.assertEqual(self.db.scalar(
                'SELECT session_user,system_user,ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid();',
                role=role,
            ), f'{role}|scram-sha-256:{role}|t')
        submit_handoff_original(self.fixture, self.plan['renew'], self.recorder)
        self.assert_head(4, 'open')
        self.reservation, self.prepared, self.packet_ids = joined_packet(
            self.scope, self.plan['permit']['new_binding_id'], 994200,
        )
        self.reserve = self.reserve_command(self.reservation, self.prepared, self.packet_ids)

    def assert_head(self, position, mode):
        head = self.fixture.head(self.scope)
        self.assertEqual(head['native_sequence'], str(position))
        self.assertEqual(head['source_mode'], mode)
        self.assertEqual(head['last_ingest_sequence'], '0')
        self.assertIsNone(head['last_admission_sha256'])
        self.assertIsNone(head['last_availability_sha256'])
        if mode == 'open':
            self.assertEqual(head['active_fence_id'], self.plan['renew']['expected_fence_id'])
            self.assertEqual(head['fence_revision'], '2')
        return head

    def fenced_command(self, kind, action_id, body):
        value = self.fixture.command(self.scope, kind, action_id=action_id)
        head = self.fixture.head(self.scope)
        value.update(expected_fence_id=head['active_fence_id'], expected_fence_revision=head['fence_revision'], body=body)
        return value

    def reserve_command(self, reservation, prepared, packet_ids):
        return self.fenced_command('packet_reservation', packet_ids['reservation_id'], dict(
            reservation_wire=reservation.wire.decode(), prepared_packet_wire=prepared.wire.decode(),
            **{key: packet_ids[key] for key in NATIVE_IDS},
        ))

    def capture_command(self, capture):
        return self.fenced_command('capture_retention', self.packet_ids['capture_id'], dict(
            reservation_action_id=self.packet_ids['reservation_id'], capture_wire=capture.wire.decode(),
        ))

    def query_without_capture(self, capture_id):
        # The fresh reader receives only the reserved ID and scope. No command,
        # result, body, receipt or capture digest survives in its request.
        return dict(
            format='ga-jupiter-b2-original-query-research-v3-v1',
            native_policy_sha256=self.reserve['native_policy_sha256'], scope=self.scope['scope'],
            target_kind='capture_retention', target_id=capture_id, expected_original_command_sha256=None,
            correlation=dict(kind='original_action_id', id=capture_id),
        )

    def sql_call(self, entry, raw):
        self.assertIn(entry, ('submit', 'get_original', 'record_stop_intent', 'get_stop_intent'))
        decode_wire(raw)
        return f'SELECT {N}.{entry}({literal(raw.decode())});\n'

    def query_bytes(self, entry, raw):
        result = self.db.sql(SETTINGS + self.sql_call(entry, raw), role=self.reader)
        self.assertTrue(result.stdout.endswith('\n'))
        self.assertEqual(result.stdout.count('\n'), 1)
        return result.stdout[:-1].encode()

    def read_original(self, command):
        return decode_wire(self.query_bytes('get_original', as_wire(self.fixture.query(command))))

    def read_capture(self, capture_id):
        return decode_wire(self.query_bytes('get_original', as_wire(self.query_without_capture(capture_id))))

    def submit_bytes(self, raw):
        with closing(self.fixture.writer(self.recorder)) as writer:
            writer.send(self.sql_call('submit', raw))
            provisional_or_original = writer.line().encode()
            writer.finish()  # The callback returns only after literal COMMIT succeeds.
            return provisional_or_original

    def collection(self):
        return ReservationCollection(
            as_wire(self.reserve), self.prepared,
            expected_policy_sha256=self.reserve['native_policy_sha256'],
            expected_native_package_sha256=self.scope['package']['native_package_sha256'],
            expected_catalog_manifest_sha256=self.marker['catalog_sha256'],
        )

    def collect_provider(self, prepared):
        self.provider_calls.append(prepared)
        self.assertIs(prepared, self.prepared)
        return synthetic_capture(self.reservation, prepared)

    def get_original_bytes(self, raw):
        return self.query_bytes('get_original', raw)

    def assert_no_recollection(self, count):
        with self.assertRaises(NativeCaptureDispatchError):
            self.collection().collect(self.submit_bytes, self.get_original_bytes, self.collect_provider)
        self.assertEqual(self.provider_calls, [self.prepared] * count)

    def assert_original(self, reply, command, sequence, *, previous_head_sha256=None):
        self.assertEqual(reply['format'], 'ga-jupiter-b2-original-reply-research-v3-v1')
        self.assertEqual(reply['scope'], self.scope['scope'])
        self.assertEqual(reply['target_id'], command['action_id'])
        self.assertEqual(reply['target_kind'], command['action_kind'])
        self.assertEqual(reply['original_command_wire'], canonical(command))
        result = decode_wire(reply['original_result_wire'].encode())
        receipt = decode_wire(reply['original_receipt_wire'].encode())
        for item in (result, receipt):
            self.assertEqual(item['scope'], command['scope'])
            self.assertEqual(item['action_kind'], command['action_kind'])
            self.assertEqual(item['action_id'], command['action_id'])
            self.assertEqual(item['native_sequence'], str(sequence))
            self.assertEqual(item['original_command_sha256'], sha(canonical(command)))
        self.assertEqual(receipt['result_sha256'], sha(reply['original_result_wire']))
        previous_head = previous_head_sha256 or command['expected_head']['native_head_sha256']
        self.assertEqual(receipt['previous_native_head_sha256'], previous_head)
        self.assertEqual(receipt['native_package_sha256'], self.scope['package']['native_package_sha256'])
        self.assertEqual(receipt['catalog_manifest_sha256'], self.marker['catalog_sha256'])
        return result['result_body']

    def assert_reserved_ids(self):
        ids = ','.join(map(literal, self.packet_ids.values()))
        scope = literal(canonical(self.scope['scope']))
        rows = json.loads(self.db.scalar(f'''SELECT coalesce(jsonb_object_agg(original_id,record_wire::jsonb),'{{}}')
            FROM {N}.identities WHERE scope_wire={scope} AND original_id IN({ids});'''))
        self.assertEqual(set(rows), set(self.packet_ids.values()))
        for role, original_id in self.packet_ids.items():
            self.assertEqual(rows[original_id]['identity_role'], role)
            self.assertEqual(rows[original_id]['first_native_sequence'], '5')
            self.assertEqual(rows[original_id]['association']['packet_reservation_id'], self.packet_ids['reservation_id'])

    def assert_journal(self, expected):
        rows = json.loads(self.db.scalar(f'''SELECT jsonb_agg(jsonb_build_array(o.native_sequence::text,
            o.action_kind,o.action_id,o.finalized,j.journal_sha256) ORDER BY o.native_sequence)
            FROM {N}.original_operations o JOIN {N}.journal_entries j
            USING(scope_wire,native_sequence,action_id);'''))
        prefix = [self.plan[key] for key in ('install', 'acquire', 'resume', 'renew')]
        self.assertEqual([row[:4] for row in rows], [
            [str(index), command['action_kind'], command['action_id'], True]
            for index, command in enumerate(prefix + list(expected), start=1)
        ])
        self.assertEqual(rows[-1][-1], self.fixture.head(self.scope)['native_head_sha256'])

    def assert_sql_refused(self, statement, role, reason):
        result = self.db.sql(statement, role=role, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertIn(reason, result.stderr)

    def assert_refused(self, command, role, reason):
        statement = BEGIN + SETTINGS + self.sql_call('submit', as_wire(command)) + 'COMMIT;\n'
        self.assert_sql_refused(statement, role, reason)

    def assert_capture_unknown(self, position):
        observed = self.read_capture(self.packet_ids['capture_id'])
        self.assertEqual(observed['resolution'], 'observed_absent_unknown')
        self.assertIsNone(observed['original_operation_pin'])
        self.assertNotIn('original_command_wire', observed)
        self.assertEqual(observed['observed_head']['native_sequence'], str(position))

    def parked_backend(self, name, *, pid=None):
        guard = (f"datname=current_database() AND usename={literal(self.recorder)} AND backend_type='client backend' "
                 f"AND pid<>pg_backend_pid() AND application_name={literal(name)} AND wait_event='PgSleep' "
                 f"AND rtrim(btrim(query,E' \\t\\r\\n'),';')={literal(SLEEP)}")
        if pid is not None:
            self.assertIs(type(pid), int)
            guard += f' AND pid={pid}'
        self.db.wait_until(f'SELECT count(*)=1 FROM pg_stat_activity WHERE {guard};', timeout=3)
        found_pid, started = json.loads(self.db.scalar(
            f'SELECT jsonb_build_array(pid,backend_start::text) FROM pg_stat_activity WHERE {guard};'
        ))
        self.assertIs(type(found_pid), int)
        self.assertGreater(found_pid, 0)
        exact = f"{guard} AND pid={found_pid} AND backend_start={literal(started)}::timestamptz"
        return found_pid, started, exact

    def terminate_parked(self, identity):
        pid, started, exact = identity
        self.assertEqual('t', self.db.scalar(f'''SELECT coalesce((SELECT pg_terminate_backend(pid,2000)
            FROM pg_stat_activity WHERE {exact}),false);''', timeout=4))
        self.assertEqual('t', self.db.scalar(f'''SELECT NOT EXISTS(SELECT 1 FROM pg_stat_activity
            WHERE pid={pid} AND backend_start={literal(started)}::timestamptz AND usename={literal(self.recorder)});'''))

    def commit_and_park(self, command, name):
        sql = (f'SET application_name={literal(name)};\n' + BEGIN + SETTINGS
               + self.sql_call('submit', as_wire(command)) + f'COMMIT;\n{SLEEP};\n')
        session = self.db.begin_sql(sql, role=self.recorder, timeout=12)
        return session, self.parked_backend(name)

    def stop_command(self):
        stop = self.fixture.command(self.scope, 'source_stop')
        stop['body'] = dict(expected_control_sha256=sha(canonical(self.plan['resume'])), expected_mode='open')
        return stop

    def stop_pins(self):
        return StopIntentPins(
            scope_wire=as_wire(self.scope['scope']), reserved_stop_id=self.scope['stop_id'],
            installation_id=self.scope['installation_id'],
            native_package_sha256=self.scope['package']['native_package_sha256'],
            effective_catalog_sha256=self.marker['catalog_sha256'], handoff_sha256=sha(canonical(self.marker)),
            control_binding_id=self.scope['bindings']['control'],
        )

    def stop_with_dispatch_gate(self, stop, position, *, already_registered=False):
        if not already_registered:
            self.db.sql(BEGIN + SETTINGS + self.sql_call('record_stop_intent', as_wire(stop)) + 'COMMIT;\n',
                        role=self.control)
        gate = StopDispatch(as_wire(stop), self.stop_pins())
        events = []

        def read_intent(query_wire):
            events.append('independent-reader')
            return self.query_bytes('get_stop_intent', query_wire)

        def submit_stop(command_wire):
            events.append('control-dispatch')
            self.assertEqual(command_wire, as_wire(stop))
            submit_handoff_original(self.fixture, decode_wire(command_wire), self.control)

        gate.dispatch(read_intent, submit_stop)
        self.assertEqual(events, ['independent-reader', 'control-dispatch'])
        reply = self.read_original(stop)
        self.assert_original(reply, stop, position)
        self.assert_head(position, 'stopped')
        self.assertEqual(stop['action_id'], self.scope['stop_id'])

    def reserve_and_collect(self):
        gate = self.collection()
        capture = gate.collect(self.submit_bytes, self.get_original_bytes, self.collect_provider)
        with self.assertRaises(NativeCaptureDispatchError):
            gate.collect(self.submit_bytes, self.get_original_bytes, self.collect_provider)
        self.assertEqual(self.provider_calls, [self.prepared])
        reserved = self.read_original(self.reserve)
        self.assertEqual(self.assert_original(reserved, self.reserve, 5), dict(
            packet_ids=self.packet_ids, original_a1_reservation_sha256=self.reservation.sha256,
            prepared_packet_sha256=sha(self.prepared.wire.decode()), capture_status='unresolved',
        ))
        self.assert_reserved_ids()
        self.assert_head(5, 'open')
        alternative = joined_packet(self.scope, self.plan['permit']['new_binding_id'], 994300)
        self.assert_refused(self.reserve_command(*alternative), self.recorder, 'b3_packet_head_refused')
        self.assert_journal([self.reserve])
        return reserved, capture



@unittest.skipUnless(os.environ.get(OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class AllocationCaptureJoinNativeTests(AllocationCaptureJoinNativeCase):
    def test_committed_capture_after_recorder_loss_keeps_exact_originals_through_stop(self):
        reserved, capture = self.reserve_and_collect()
        command = self.capture_command(capture)
        wrong_fence = copy.deepcopy(command)
        wrong_fence['expected_fence_revision'] = '1'
        self.assert_refused(wrong_fence, self.recorder, 'b2_stale_head')
        wrong_raw = capture.to_dict()
        capsule = json.loads(wrong_raw['capsule_wires'][0]); capsule['response_sha256'] = '0' * 64
        wrong_raw['capsule_wires'][0] = canonical(capsule)
        malformed = self.capture_command(source.envelope('Capture', wrong_raw))
        self.assert_refused(malformed, self.recorder, 'b3_raw_conflict')
        for key, numeric in (('id', 1.0), ('jsonrpc', 2.0)):
            with self.subTest(noncanonical_rpc_field=key):
                altered = capture.to_dict()
                genesis = json.loads(altered['capsule_wires'][1])
                request = json.loads(genesis['canonical_public_request_wire'])
                body = json.loads(request['body_wire'])
                body[key] = numeric
                request['body_wire'] = canonical(body)
                genesis['canonical_public_request_wire'] = canonical(request)
                genesis['request_sha256'] = sha(genesis['canonical_public_request_wire'])
                altered['capsule_wires'][1] = canonical(genesis)
                malformed_rpc = self.capture_command(source.envelope('Capture', altered))
                self.assert_refused(malformed_rpc, self.recorder, 'b3_capsule_conflict')
        self.assert_refused(command, self.reader, '42501')
        self.assert_capture_unknown(5)
        self.assert_journal([self.reserve])

        session, identity = self.commit_and_park(command, 'dashboard_joined_capture_committed')
        # A separate native read witnesses COMMIT before the fault. No capture
        # writer response or digest is given to either independent read.
        committed = self.read_capture(self.packet_ids['capture_id'])
        self.terminate_parked(identity)
        self.assertNotEqual(session.wait(timeout=5, check=False).returncode, 0)
        recovered = self.read_capture(self.packet_ids['capture_id'])
        self.assertEqual(recovered, committed)
        self.assertEqual(recovered, self.read_original(command))
        opaque_query = self.sql_call('get_original', as_wire(self.query_without_capture(self.packet_ids['capture_id'])))
        self.assert_sql_refused(SETTINGS + opaque_query, self.recorder, 'b3_capture_reader_refused')
        wrong_digest = dict(self.fixture.query(command), expected_original_command_sha256='0' * 64)
        self.assert_sql_refused(SETTINGS + self.sql_call('get_original', as_wire(wrong_digest)),
                                self.reader, 'b2_original_refused')
        self.assertEqual(self.assert_original(recovered, command, 6), dict(
            reservation_action_id=self.reserve['action_id'], original_a1_reservation_sha256=self.reservation.sha256,
            original_a1_capture_sha256=capture.sha256, collection_completed=True, eligibility=False, terminal=False,
        ))
        original = source.wire(json.loads(recovered['original_command_wire'])['body']['capture_wire'], 'Capture')
        self.assertEqual(original.wire, capture.wire)
        source.validate_capture(self.reservation, original)
        self.assertEqual(tuple(acquisition.decode_capsule(raw.encode(), self.prepared.binding).raw_body
                               for raw in original.to_dict()['capsule_wires']), RAW_BODIES)
        self.assert_no_recollection(1)
        self.assert_head(6, 'open')

        stop = self.stop_command()
        self.stop_with_dispatch_gate(stop, 7)
        self.assert_journal([self.reserve, command, stop])
        self.assert_reserved_ids()
        for before, after in ((reserved, self.read_original(self.reserve)),
                              (recovered, self.read_capture(self.packet_ids['capture_id']))):
            self.assertEqual([before[key] for key in WIRE_FIELDS], [after[key] for key in WIRE_FIELDS])

    def test_provisional_capture_loss_unblocks_stop_without_recollection_or_late_capture(self):
        reserved, capture = self.reserve_and_collect()
        command = self.capture_command(capture)
        stop = self.stop_command()
        application = 'dashboard_joined_capture_provisional'
        with closing(self.fixture.writer(self.recorder)) as writer, closing(self.fixture.writer(self.control)) as waiter:
            writer.send(f'SET application_name={literal(application)};\n')
            writer_pid = writer.backend_pid()
            writer.send(self.sql_call('submit', as_wire(command)))
            provisional = decode_wire(writer.line().encode())
            self.assertTrue(provisional['pending_commit'])
            self.assertEqual(provisional['original_command_sha256'], sha(canonical(command)))
            writer.send(f'{SLEEP};\n')
            identity = self.parked_backend(application, pid=writer_pid)
            self.assert_capture_unknown(5)
            waiter.send("SET LOCAL lock_timeout='4000ms';\n")
            waiter_pid = waiter.backend_pid()
            waiter.send(self.sql_call('record_stop_intent', as_wire(stop)))
            self.fixture.wait_for_blocker(waiter_pid, writer_pid)
            self.terminate_parked(identity)
            writer._process.stdin.close()
            self.assertIn('57P01', writer.failure_stderr())
            self.assertNotEqual(writer._process.returncode, 0)
            intent = decode_wire(waiter.line().encode())
            self.assertTrue(intent['pending_commit'])
            self.assertEqual(intent['original_command_sha256'], sha(canonical(stop)))
            waiter.finish()

        self.assert_capture_unknown(5)
        self.assert_no_recollection(1)
        self.assert_journal([self.reserve])
        self.stop_with_dispatch_gate(stop, 6, already_registered=True)
        self.assert_capture_unknown(6)
        self.assert_refused(command, self.recorder, 'b2_stop_intent_pending')
        self.assert_refused(self.capture_command(capture), self.recorder, 'b2_stop_intent_pending')
        self.assert_journal([self.reserve, stop])
        self.assert_reserved_ids()
        self.assertEqual([reserved[key] for key in WIRE_FIELDS],
                         [self.read_original(self.reserve)[key] for key in WIRE_FIELDS])

    def test_lost_reservation_ack_keeps_committed_ids_without_provider_io(self):
        acknowledged_outside_gate = []
        gate_read_requests = []

        def submit_then_lose_reply(raw):
            self.assertEqual(raw, as_wire(self.reserve))
            session, identity = self.commit_and_park(self.reserve, 'dashboard_joined_reservation_ack_lost')
            self.assert_original(self.read_original(self.reserve), self.reserve, 5)
            self.terminate_parked(identity)
            self.assertNotEqual(session.wait(timeout=5, check=False).returncode, 0)
            acknowledged_outside_gate.append(True)
            raise TimeoutError('owned reservation writer lost before acknowledgment')

        def gate_reader_unexpected(raw):
            gate_read_requests.append(raw)
            return self.get_original_bytes(raw)

        with self.assertRaises(NativeCaptureDispatchError):
            self.collection().collect(submit_then_lose_reply, gate_reader_unexpected, self.collect_provider)
        self.assertEqual(acknowledged_outside_gate, [True])
        self.assertEqual(gate_read_requests, [])
        self.assert_no_recollection(0)
        self.assert_capture_unknown(5)
        self.assert_reserved_ids()
        self.assert_journal([self.reserve])
        stop = self.stop_command()
        self.stop_with_dispatch_gate(stop, 6)
        self.assert_capture_unknown(6)
        self.assert_journal([self.reserve, stop])
