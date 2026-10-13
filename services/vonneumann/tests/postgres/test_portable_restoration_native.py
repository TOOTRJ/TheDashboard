"""Joined guarded native-v2 readback/restoration; disposable local DB only.

Requires the separately reviewed native fixture package. No source fixture is
relabelled as real-provider data; no hosted/restoration authority is returned.
"""
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import os
import unittest
from uuid import UUID

from tests.postgres.harness import OPT_IN
from tests.measure_provider_ga_research import literal
from tests.test_provider_contract import OWNER, RUN, WORKER, EPOCH, MONO, raw_capture, source_inputs
from tests.test_portable_restoration import inputs_of, prepare_restored_next
from vonneumann.research import provider_portable_ga_model as ga, portable_partitioned_checkpoint as cp, numeric_wire as numbers
from vonneumann.research import portable_restoration as restore, portable_restoration_wire as wire


def json_wire(value): return json.dumps(value, ensure_ascii=False).encode('utf-8')


@unittest.skipUnless(os.environ.get(OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class PortableRestorationNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import inside the opt-in fixture, so ordinary discovery does not
        # duplicate the independent native TestCase or install its package.
        from tests.postgres.test_portable_native import PortableNativeSqlTests, ACTOR, OTHER, OTHER_RUN
        cls._native = PortableNativeSqlTests
        cls.actor, cls.other, cls.other_run = ACTOR, OTHER, OTHER_RUN
        cls._native.setUpClass()
        cls.db = cls._native.db

    @classmethod
    def tearDownClass(cls): cls._native.tearDownClass()

    def setUp(self):
        self.fixture = self._native(methodName='runTest')
        self.fixture.setUp()

    def operator_expected(self, row):
        """Independent fixture installer view of accepted head + actual catalog.

        This is a laboratory operator capability, not a production application
        credential. It never trusts the receipt or seeds an accepted head.
        """
        command = numbers.decode(row[2])
        query = '''SELECT jsonb_build_object(
          'owner_id',c.owner_id::text,'run_id',c.run_id::text,'revision',c.revision::text,
          'command_id',c.command_id::text,'command_sha256',c.command_sha256,
          'manifest_sha256',c.manifest_sha256,'semantic_validator_sha256',c.validator_sha256,
          'native_package_sha256',c.package_sha256)
          FROM vn_portable_native_research.commands c
          JOIN vn_portable_native_research.runs r USING(owner_id,run_id)
          JOIN vn_portable_semantic_research.accepted_heads h USING(owner_id,run_id)
          JOIN vn_portable_native_research.package_manifest p ON p.singleton
          WHERE c.owner_id=''' + literal(OWNER) + ' AND c.run_id=' + literal(RUN) + '''
          AND c.revision=r.revision AND h.revision=c.revision
          AND h.command_sha256=c.command_sha256 AND h.manifest_sha256=c.manifest_sha256
          AND h.validator_sha256=c.validator_sha256
          AND c.validator_sha256=vn_portable_semantic_research.validator_contract()
          AND c.package_sha256=p.sha256 AND p.sha256=vn_portable_native_research.catalog_fingerprint();'''
        accepted = json.loads(self.db.scalar(query))
        self.assertEqual(accepted['command_id'], command['command_id'])
        self.assertEqual(accepted['command_sha256'], hashlib.sha256(row[2]).hexdigest())
        self.assertEqual(accepted['manifest_sha256'], hashlib.sha256(numbers.encode(row[1].to_dict())).hexdigest())
        return wire.ExpectedHead(accepted['owner_id'], accepted['run_id'], int(accepted['revision']),
            accepted['manifest_sha256'], accepted['command_id'], accepted['command_sha256'],
            accepted['semantic_validator_sha256'], accepted['native_package_sha256'])

    def load(self, row, *, prove_read_only=True):
        expected = self.operator_expected(row)
        response = self.fixture.checkpoint(row)
        before = self.fixture.snapshot() if prove_read_only else None
        restored = restore.restore_readback(json_wire(response), expected)
        if prove_read_only:
            self.assertEqual(self.fixture.snapshot(), before, 'Loading must not write or install a lease')
        self.assertEqual(restored.state.to_dict(), row[0].state.to_dict())
        self.assertEqual(restored.checkpoint.component_wires, tuple(block._wire for block in row[1].components))
        self.assertFalse(restored.restoration_authority); self.assertFalse(restored.hosted_authority)
        self.assertFalse(restored.lease_restored); self.assertFalse(restored.identity_ledger_restored)
        return restored

    def identities(self, row, expected, ids):
        response = self.db.scalar(self.fixture.lookup(row, list(ids)), role=self.actor)
        return restore.decode_identity_lookup(response.encode(), expected, ids)

    def assert_next(self, previous, following):
        source_critical = following[0].transition['evidence']['kind'] in {'protective', 'decision'}
        # Whole-table snapshots establish read-only behavior in the independent
        # control case; do not repeatedly copy the complete journal while the
        # original five-second laboratory source guard is running.
        restored = self.load(previous, prove_read_only=not source_critical)
        inputs = inputs_of(following[0])
        checked = self.identities(previous, restored.checkpoint.expected, inputs.ids)
        before = self.fixture.snapshot() if not source_critical else None
        prepared = prepare_restored_next(restored, following[0], inputs, checked)
        self.assertEqual(prepared._wire, following[0]._wire)
        self.assertEqual(restore.prepare_restored_transport(restored, prepared,
            command_id=numbers.decode(following[2])['command_id']), following[2])
        if not source_critical:
            self.assertEqual(self.fixture.snapshot(), before, 'Preparation must not submit or acquire a lease')
        pending = self.fixture.commit(following[2])
        self.assertFalse(pending['record_observed']); self.assertTrue(pending['pending_until_commit'])
        if source_critical:
            # The subsequent independently scoped checkpoint load binds the
            # committed head. Original getter reconciliation is separately
            # exercised for controls and the dedicated uncertain-reply case.
            return
        observed = self.fixture.read(following)
        resolution = restore.reconcile_original_request(restore.PendingOriginalRequest.capture(following[2]),
            json_wire(observed), self.operator_expected(following))
        self.assertEqual(resolution.outcome, 'observed_original_commit')
        self.assertFalse(resolution.retry_authority)

    def test_actual_scoped_committed_readback_next_controls_and_historical_refusal(self):
        self.fixture.create(); row = self.fixture.bootstrap()
        self.fixture.commit(row[2]); initial = row
        for serial, action in enumerate(('pause', 'resume', 'stop'), 50):
            following = self.fixture.control(row, action, serial=serial)
            self.assert_next(row, following); row = following
        restored = self.load(row)
        self.assertEqual(restored.state.to_dict()['status'], 'stopped')
        old_response = self.fixture.checkpoint(initial)
        old_expected = replace(restored.checkpoint.expected,
            command_id=numbers.decode(initial[2])['command_id'], command_sha256=hashlib.sha256(initial[2]).hexdigest(),
            revision=initial[0].state.revision, manifest_sha256=self.fixture.manifest_sha(initial))
        with self.assertRaises(wire.RestorationError): wire.decode_readback(json_wire(old_response), old_expected)
        inspection = wire.decode_readback(json_wire(old_response), replace(old_expected, allow_historical=True))
        self.assertFalse(inspection.is_current)
        with self.assertRaises(wire.RestorationError): restore.reconstruct_checkpoint(inspection)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_portable_native_research.dependency_pins;'), '52')

    def test_original_absence_pending_reply_and_foreign_getter_never_grant_retry(self):
        self.fixture.create(); row = self.fixture.bootstrap(); pending = restore.PendingOriginalRequest.capture(row[2])
        absent = self.fixture.read(row)
        self.assertFalse(absent['found'])
        provisional = self.fixture.commit(row[2]); expected = self.operator_expected(row)
        unresolved = restore.reconcile_original_request(pending, json_wire(absent), expected)
        self.assertEqual(unresolved.outcome, 'not_observed_uncertain'); self.assertFalse(unresolved.retry_authority)
        uncommitted_reply = {'format': restore.COMMAND_READBACK_FORMAT, 'found': True,
            'receipt': provisional, 'original_command_wire': row[2].decode()}
        with self.assertRaises(wire.RestorationError): restore.reconcile_original_request(pending, json_wire(uncommitted_reply), expected)
        wrong_actor = self.db.scalar('SELECT vn_portable_native_research.get_command(' + ','.join((
            literal(WORKER), literal(self.other_run), literal(pending.command_id), literal(pending.command_sha256))) + ');', role=self.other)
        self.assertEqual(json.loads(wrong_actor), absent)
        self.load(row)
        observed = self.fixture.read(row)
        result = restore.reconcile_original_request(pending, json_wire(observed), expected)
        self.assertEqual(result.original.wire, row[2]); self.assertEqual(result.original.command_id, pending.command_id)
        self.assertFalse(result.retry_authority); self.assertFalse(result.hosted_authority)

    def test_native_current_head_oracle_retains_retired_ids_after_original_restart(self):
        self.fixture.create(); original = self.fixture.bootstrap(); self.fixture.commit(original[2])
        row = original
        for serial, action in enumerate(('pause', 'resume'), 60):
            following = self.fixture.control(row, action, serial=serial)
            self.assert_next(row, following); row = following
        # A literal synthetic quote at the actual laboratory clock. No clock
        # GUC, semantic seed, source relabeling or real provider request is used.
        state = row[3].accept(row[0]); data = state.to_dict()
        at = max(int(self.db.scalar('SELECT floor(extract(epoch FROM clock_timestamp()));')),
                 data['engine']['lifecycle']['last_control_at'] + 1)
        initial_at = int(datetime.fromisoformat(original[0].transition['evidence']['inputs']['event_at']).timestamp())
        mono = MONO + at - initial_at
        frame = ga.source.make_frame(raw_capture(price='100', block=900,
            source_second=at - 2, wall=at - 1, mono=mono - 1), prior_source=data['source'],
            epoch=EPOCH, wall_now=at, monotonic_now=mono)
        protective = ga.prepare_protective(state, frame, source_inputs(at, mono=mono, serial=70), ledger=row[3])
        capture = cp.capture_owned_candidate(protective)
        following = (protective, capture, cp.prepare_transport(protective, capture, previous=row[1],
            command_id=str(UUID(int=97000000 + protective.state.revision))), row[3])
        self.assert_next(row, following); row = following
        state = row[3].accept(row[0])
        decision = ga.prepare_decision(state, frame, None, source_inputs(at, mono=mono, generation=1, serial=71), ledger=row[3])
        capture = cp.capture_owned_candidate(decision)
        following = (decision, capture, cp.prepare_transport(decision, capture, previous=row[1],
            command_id=str(UUID(int=97000000 + decision.state.revision))), row[3])
        self.assert_next(row, following); row = following
        restored = self.load(row)
        old_id = original[0].state.to_dict()['accounts'][0]['id']
        self.assertNotIn(old_id, {account['id'] for account in restored.state.to_dict()['accounts']})
        oracle = self.identities(row, restored.checkpoint.expected, (old_id,))
        self.assertTrue(oracle.used(old_id))
        stale = self.db.sql(self.fixture.lookup(original, [old_id]), role=self.actor, check=False)
        self.assertNotEqual(stale.returncode, 0); self.assertIn('portable_native_lookup_head_mismatch', stale.stderr)
        # Independent current preparation also refuses a reused retired UUID.
        paused = self.fixture.control(row, 'pause', serial=72); self.assert_next(row, paused); row = paused
        resumed = self.fixture.control(row, 'resume', serial=73); self.assert_next(row, resumed); row = resumed
        state = row[3].accept(row[0]); data = state.to_dict()
        at = max(int(self.db.scalar('SELECT floor(extract(epoch FROM clock_timestamp()));')),
                 data['engine']['lifecycle']['last_control_at'] + 1)
        # Keep the actual server observation within the reviewed laboratory
        # source interval. This bounded owned-fixture wait changes no clock GUC.
        self.db.sql('SELECT pg_sleep(least(8,greatest(0,' + str(at) + '-extract(epoch FROM clock_timestamp())-1)));')
        mono = MONO + at - initial_at
        frame = ga.source.make_frame(raw_capture(price='100', block=901,
            source_second=at - 2, wall=at - 1, mono=mono - 1), prior_source=data['source'],
            epoch=EPOCH, wall_now=at, monotonic_now=mono)
        protective = ga.prepare_protective(state, frame, source_inputs(at, mono=mono, serial=74), ledger=row[3])
        capture = cp.capture_owned_candidate(protective)
        following = (protective, capture, cp.prepare_transport(protective, capture, previous=row[1],
            command_id=str(UUID(int=98000000 + protective.state.revision))), row[3])
        self.assert_next(row, following); row = following
        state = row[3].accept(row[0]); restored = self.load(row)
        original_inputs = source_inputs(at, mono=mono, generation=2, serial=75)
        reused_inputs = replace(original_inputs, ids=(old_id,) + original_inputs.ids[1:])
        checked = self.identities(row, restored.checkpoint.expected, reused_inputs.ids)
        self.assertTrue(checked.used(old_id))
        before = self.fixture.snapshot()
        with self.assertRaises(ga.ExactRehearsalError):
            ga.prepare_decision(state, frame, None, reused_inputs, ledger=row[3])
        with self.assertRaises(ga.ExactRehearsalError):
            restore.prepare_restored_candidate(restored, reused_inputs, checked, phase='decision', frame=frame)
        self.assertEqual(self.fixture.snapshot(), before)


if __name__ == '__main__': unittest.main()
