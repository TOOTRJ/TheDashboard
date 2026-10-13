"""Joined guarded native-v2 readback/restoration; disposable local DB only.

Requires the separately reviewed native fixture package. No source fixture is
relabelled as real-provider data; no hosted/restoration authority is returned.
"""
from dataclasses import replace
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import time
import unittest
from uuid import UUID
from unittest.mock import patch

from tests.postgres.harness import OPT_IN, SqlFailure
from tests.measure_provider_ga_research import literal
from tests.test_provider_contract import OWNER, RUN, WORKER, EPOCH, MONO, raw_capture, source_inputs
from tests.test_portable_restoration import inputs_of, prepare_restored_next
from vonneumann.research import provider_portable_ga_model as ga, portable_partitioned_checkpoint as cp, numeric_wire as numbers
from vonneumann.research import portable_restoration as restore, portable_restoration_wire as wire


def json_wire(value): return json.dumps(value, ensure_ascii=False).encode('utf-8')


def utc_microseconds(value):
    elapsed = datetime.fromisoformat(value) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (elapsed.days * 86400 + elapsed.seconds) * 1000000 + elapsed.microseconds


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
        self.source_phase_seconds = {}

    def timed_source_phase(self, label, operation):
        """Fixed laboratory phases, measured by this process; no native clock."""
        started = time.monotonic()
        try:
            return operation()
        finally:
            self.source_phase_seconds[label] = time.monotonic() - started

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

    def capture_context_before_source(self, row, *, serial, generation=0):
        """Observe the committed head and ID oracle before an original capture.

        The allocation tuple does not depend on the later event/source clock.
        No prospective checkpoint or provisional receipt becomes authority.
        """
        ids = source_inputs(0, generation=generation, serial=serial).ids
        return self.capture_context(row, ids)

    def capture_context(self, row, ids):
        """Capture original readback/oracle while this head is actually current."""
        expected = self.operator_expected(row)
        response = json.loads(self.db.scalar(self.context_query(row, ids), role=self.actor))
        return expected, json_wire(response['checkpoint']), json_wire(response['identities']), ids

    def context_query(self, row, ids):
        """Full scoped native getters; no fixture/operator SELECT capability."""
        digest = self.fixture.manifest_sha(row)
        checkpoint = 'vn_portable_native_research.read_checkpoint(' + ','.join((
            literal(OWNER), literal(RUN), str(row[0].state.revision), literal(digest))) + ')'
        lookup = self.fixture.lookup(row, list(ids), digest=digest).removeprefix('SELECT ').removesuffix(';')
        return "SELECT jsonb_build_object('checkpoint'," + checkpoint + ",'identities'," + lookup + ');'

    def commit_protective_and_capture_once(self, previous, following, ids):
        """One ACTOR connection, explicit COMMIT, then a new read transaction.

        The scoped getters still audit their actor/package/current head and
        reject same-transaction provisional readback. A separate fresh operator
        connection subsequently supplies the actual accepted head/catalog. No
        provisional or partial output authorizes the original decision.
        """
        self.assertEqual(following[0].transition['evidence']['kind'], 'protective')
        self.assertEqual(following[0].transition['before'], previous[0].state.to_dict())
        source = 'BEGIN;' + self.fixture.sql(following[2]) + 'COMMIT;' + self.context_query(following, ids)
        try:
            result = self.timed_source_phase('protective_submission_and_native_readback',
                lambda: self.db.sql(source, role=self.actor, timeout=30))
            # JSONB output is LF-delimited; do not interpret other Unicode
            # separators as successful complete protocol records.
            records = result.stdout.strip().split('\n')
            self.assertEqual(len(records), 2, 'Require both complete original pending and committed-readback records')
            pending, response = (json.loads(record) for record in records)
            self.assertIs(pending['record_observed'], False); self.assertIs(pending['pending_until_commit'], True)
            self.assertEqual(set(response), {'checkpoint', 'identities'})
            self.assertIs(response['checkpoint']['receipt']['record_observed'], True)
            self.assertIs(response['checkpoint']['receipt']['pending_until_commit'], False)
            expected = self.timed_source_phase('fresh_operator_head_and_catalog', lambda: self.operator_expected(following))
        except Exception:
            # The error may be in the SELECT after COMMIT. It cannot imply that
            # the original protection rolled back. Stop; reconcile only its ID.
            try:
                observed = self.fixture.read(following)
                print(json.dumps({'combined_original_protective_outcome': 'uncertain-until-fresh-getter',
                    'original_command_id': numbers.decode(following[2])['command_id'],
                    'original_command_sha256': hashlib.sha256(following[2]).hexdigest(),
                    'fresh_original_command_found': observed['found'],
                    'laboratory_host_phase_seconds': dict(self.source_phase_seconds),
                    'failed_guard_instant_observed': False,
                    'retry_performed': False, 'decision_submitted': False}, sort_keys=True))
            except Exception:
                pass
            raise
        return expected, json_wire(response['checkpoint']), json_wire(response['identities']), ids

    def restore_captured_context(self, row, context):
        """Reconstruct a recorded current-at-capture snapshot, with no submission.

        These saved bytes do not prove that their head is current at decode time.
        The delayed comparison path below never submits from the saved snapshot.
        """
        expected, checkpoint, identities, ids = context
        restored = restore.restore_readback(checkpoint, expected)
        checked = restore.decode_identity_lookup(identities, expected, ids)
        self.assertEqual(restored.state.to_dict(), row[0].state.to_dict())
        self.assertEqual(restored.checkpoint.component_wires, tuple(block._wire for block in row[1].components))
        self.assertFalse(restored.restoration_authority); self.assertFalse(restored.hosted_authority)
        self.assertFalse(restored.lease_restored); self.assertFalse(restored.identity_ledger_restored)
        return restored, checked

    def current_source_clock(self, state, *, pace_integral_action=False):
        """Sample the real fixture clock after any bounded control-order wait."""
        previous_control = state.to_dict()['engine']['lifecycle']['last_control_at']
        target = 0 if previous_control is None else previous_control + 1
        query = 'SELECT floor(extract(epoch FROM clock_timestamp())*1000000);'
        now_us = int(self.db.scalar(query))
        if now_us < target * 1000000:
            self.assertLessEqual(target * 1000000 - now_us, 8000000, 'Control-order wait must stay bounded')
            now_us = int(self.db.scalar('SELECT pg_sleep(greatest(0,' + str(target)
                + '-extract(epoch FROM clock_timestamp())));'
                + query))
        self.assertGreaterEqual(now_us, target * 1000000)
        if pace_integral_action:
            # Schedule this positive v2 fixture BEFORE its first receipt. V2's
            # integral action otherwise spends almost one second when acquisition
            # lands just after a whole second. Sample one genuine clock to pace
            # once, then preserve the actual observed receipt after that wait.
            # Scheduler overshoot is not adjusted, retried or re-paced.
            phase_query = '''WITH sampled AS MATERIALIZED
              (SELECT extract(epoch FROM clock_timestamp()) AS at)
              SELECT pg_sleep(greatest(0,floor(at)+0.95-at)) FROM sampled;'''
            now_us = int(self.timed_source_phase('pre_acquisition_clock_pacing',
                lambda: self.db.scalar(phase_query + query)))
            self.assertGreaterEqual(now_us, target * 1000000)
        # Preserve the original observed receipt, not a rounded-down label that
        # spends up to a second of the unchanged five-second native allowance.
        received_at = now_us / 1000000
        # Original v2 forbids an integral action second before the ceiling of a
        # fractional receipt. Wait on the genuine clock; never label the first
        # request with a prospective/future decision time or refresh its receipt.
        action_second = (now_us + 999999) // 1000000
        decision_us = int(self.db.scalar('SELECT pg_sleep(greatest(0,' + str(action_second)
            + '-extract(epoch FROM clock_timestamp())));' + query))
        self.assertGreaterEqual(decision_us, action_second * 1000000)
        # V2 frame clocks ceil binary64 but DecisionInputs rounds through
        # datetime. Use the observed integral action second for both, avoiding
        # a one-microsecond representation mismatch without future adjustment.
        observed_second = decision_us // 1000000
        return observed_second, received_at, observed_second

    def assert_equivalent(self, previous, following, context):
        restored, checked = context
        inputs = inputs_of(following[0])
        self.assertEqual(restored.checkpoint.expected.manifest_sha256, self.fixture.manifest_sha(previous))
        self.assertEqual(checked.requested, inputs.ids)
        prepared = prepare_restored_next(restored, following[0], inputs, checked)
        self.assertEqual(prepared._wire, following[0]._wire)
        self.assertEqual(restore.prepare_restored_transport(restored, prepared,
            command_id=numbers.decode(following[2])['command_id']), following[2])

    def report_source_failure_after_rollback(self, following):
        """Observe fixed fixture fields later; do not infer the failed guard instant.

        The original request is inspected only after refusal. The failed row has
        rolled back, so its deadline is derived from that immutable request, not
        represented as a persisted guard observation. This read cannot retry it.
        """
        try:
            original = numbers.decode(following[2])
            quote = original['evidence']['inputs']['provider']['frame']['quote']
            received_us = quote['document']['received_wall_us']
            source_us = quote['estimated_source_second'] * 1000000
            deadline_us = min(received_us,
                received_us + 25000000 - quote['source_age_floor_us'], source_us + 25000000)
            history = original['evidence']['inputs']['provider'].get('history')
            if history is not None:
                deadline_us = min(deadline_us, *(document['received_wall_us'] for document in history['documents']))
            deadline_us += 5000000
            observation = json.loads(self.db.scalar('''WITH observed AS MATERIALIZED
              (SELECT clock_timestamp() AS at)
              SELECT jsonb_build_object(
              'observed_at_us',floor(extract(epoch FROM o.at)*1000000)::text,
              'lease_until_us',floor(extract(epoch FROM r.lease_until)*1000000)::text,
              'accepted_revision',r.revision::text,'accepted_command_id',c.command_id::text,
              'accepted_manifest_sha256',c.manifest_sha256,
              'accepted_guard_observed_at',c.guard_observed_at)
              FROM observed o CROSS JOIN vn_portable_native_research.runs r
              LEFT JOIN vn_portable_native_research.commands c
              ON c.owner_id=r.owner_id AND c.run_id=r.run_id AND c.revision=r.revision
              WHERE r.owner_id=''' + literal(OWNER) + ' AND r.run_id=' + literal(RUN) + ';'))
            observed_us = int(observation['observed_at_us'])
            original_readback = self.fixture.read(following)
            diagnostic = {'native_source_failure_observation': 'after-original-refusal-and-rollback',
                'failed_guard_instant_observed': False, 'failed_branch_attribution_authority': False,
                'original_command_id': original['command_id'],
                'original_command_sha256': hashlib.sha256(following[2]).hexdigest(),
                'original_command_found_after_failure': original_readback['found'],
                'original_received_wall_us': received_us,
                'derived_original_source_deadline_us': deadline_us,
                'source_deadline_elapsed_at_later_observation': deadline_us <= observed_us,
                'lease_expired_at_later_observation': int(observation['lease_until_us']) <= observed_us,
                'receipt_age_seconds_at_later_observation': (observed_us - received_us) / 1000000,
                'estimated_source_age_seconds_at_later_observation': (observed_us - source_us) / 1000000,
                'laboratory_host_phase_seconds': dict(self.source_phase_seconds),
                'retry_performed': False, **observation}
        except Exception as error:
            # A diagnostic failure must not replace or conceal the SQL refusal.
            diagnostic = {'native_source_failure_observation': 'unavailable-after-original-refusal',
                'diagnostic_error_type': type(error).__name__, 'retry_performed': False,
                'failed_guard_instant_observed': False, 'failed_branch_attribution_authority': False}
        print(json.dumps(diagnostic, sort_keys=True))

    def commit_source_once(self, previous, following):
        """Submit one original; leave all duplicate reconstruction off admission."""
        kind = following[0].transition['evidence']['kind']
        self.assertIn(kind, {'protective', 'decision'})
        if kind == 'decision':
            self.assertEqual(following[0].transition['evidence']['inputs']['provider']['frame'],
                previous[0].transition['evidence']['inputs']['provider']['frame'])
        try:
            pending = self.timed_source_phase(kind + '_native_submission', lambda: self.fixture.commit(following[2]))
        except SqlFailure:
            try:
                self.report_source_failure_after_rollback(following)
            except Exception:
                # Even output failure must preserve the original SQL exception.
                pass
            raise
        committed_at = time.monotonic()
        self.assertFalse(pending['record_observed']); self.assertTrue(pending['pending_until_commit'])
        return committed_at

    def assert_next(self, previous, following):
        """Prove restored controls before their separate data-free submission."""
        self.assertEqual(following[0].transition['evidence']['kind'], 'control')
        inputs = inputs_of(following[0])
        restored = self.load(previous)
        checked = self.identities(previous, restored.checkpoint.expected, inputs.ids)
        before = self.fixture.snapshot()
        self.assert_equivalent(previous, following, (restored, checked))
        self.assertEqual(self.fixture.snapshot(), before, 'Preparation must not submit or acquire a lease')
        pending = self.fixture.commit(following[2])
        self.assertFalse(pending['record_observed']); self.assertTrue(pending['pending_until_commit'])
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

    def test_captured_current_head_equivalence_retains_retired_ids_after_original_pair(self):
        self.fixture.create(); original = self.fixture.bootstrap(); self.fixture.commit(original[2])
        row = original
        for serial, action in enumerate(('pause', 'resume'), 60):
            following = self.fixture.control(row, action, serial=serial)
            self.assert_next(row, following); row = following
        # A literal synthetic quote at the actual laboratory clock. No clock
        # GUC, semantic seed, source relabeling or real provider request is used.
        before_protective = row
        protective_context = self.capture_context_before_source(row, serial=70)
        state = row[3].accept(row[0]); data = state.to_dict()
        at, received_at, decision_at = self.current_source_clock(state, pace_integral_action=True)
        captured_started = time.monotonic()
        initial_at = int(datetime.fromisoformat(original[0].transition['evidence']['inputs']['event_at']).timestamp())
        received_mono = MONO + received_at - initial_at
        mono = MONO + decision_at - initial_at
        frame = ga.source.make_frame(raw_capture(price='100', block=900,
            source_second=int(received_at) - 2, wall=received_at, mono=received_mono), prior_source=data['source'],
            epoch=EPOCH, wall_now=decision_at, monotonic_now=mono)
        protective = self.timed_source_phase('protective_model', lambda:
            ga.prepare_protective(state, frame, source_inputs(at, wall=decision_at, mono=mono, serial=70), ledger=row[3]))
        capture = self.timed_source_phase('protective_checkpoint', lambda: cp.capture_owned_candidate(protective))
        protective_wire = self.timed_source_phase('protective_transport', lambda:
            cp.prepare_transport(protective, capture, previous=row[1], command_id=str(UUID(int=97000000 + protective.state.revision))))
        following = (protective, capture, protective_wire, row[3])
        snapshot_started = time.monotonic()
        decision_context = self.commit_protective_and_capture_once(row, following,
            source_inputs(at, wall=decision_at, mono=mono, generation=1, serial=71).ids)
        protective_readback_at = time.monotonic(); row = following
        protective_row = row
        # Both original snapshots are bound while their heads are current. Keep
        # the independent protective head/catalog/oracle read before decision,
        # but postpone ALL duplicate cold graph/next-wire work until the pair
        # has been submitted once with the unchanged original source frame.
        snapshot_seconds = protective_readback_at - snapshot_started
        state = self.timed_source_phase('protective_ledger_acceptance', lambda: row[3].accept(row[0]))
        decision = self.timed_source_phase('decision_model', lambda:
            ga.prepare_decision(state, frame, None, source_inputs(at, wall=decision_at, mono=mono, generation=1, serial=71), ledger=row[3]))
        capture = self.timed_source_phase('decision_checkpoint', lambda: cp.capture_owned_candidate(decision))
        decision_wire = self.timed_source_phase('decision_transport', lambda:
            cp.prepare_transport(decision, capture, previous=row[1], command_id=str(UUID(int=97000000 + decision.state.revision))))
        following = (decision, capture, decision_wire, row[3])
        decision_committed_at = self.commit_source_once(row, following); row = following
        # Saved snapshots cannot grant current-at-decode continuation authority.
        # These complete math comparisons do not submit, replay or renew a lease.
        self.assert_equivalent(before_protective, protective_row,
            self.restore_captured_context(before_protective, protective_context))
        self.assert_equivalent(protective_row, row,
            self.restore_captured_context(protective_row, decision_context))
        compared_at = time.monotonic()
        restored = self.load(row)
        receipt_us = frame['quote']['document']['received_wall_us']
        protective_guard = json.loads(decision_context[1])['receipt']['guard_observed_at']
        print(json.dumps({'restoration_native_source_sequence': 'same-original-frame-once',
            'positive_v2_pre_acquisition_pacing': True,
            'pre_acquisition_target_fraction_us': 950000,
            'original_observed_receipt_fraction_us': receipt_us % 1000000,
            'original_receipt_to_action_wall_seconds': round(decision_at - received_at, 6),
            'protective_submit_and_current_readback_host_seconds_from_action_sample': round(protective_readback_at - captured_started, 6),
            'protective_submit_current_readback_and_independent_oracle_host_seconds': round(snapshot_seconds, 6),
            'decision_commit_host_seconds_from_action_sample': round(decision_committed_at - captured_started, 6),
            'pair_and_both_delayed_equivalences_host_seconds_from_action_sample': round(compared_at - captured_started, 6),
            'laboratory_host_phase_seconds': dict(self.source_phase_seconds),
            'protective_guard_seconds_from_original_receipt': (utc_microseconds(protective_guard) - receipt_us) / 1000000,
            'decision_guard_seconds_from_original_receipt': (utc_microseconds(restored.checkpoint.guard_observed_at) - receipt_us) / 1000000}, sort_keys=True))
        old_id = original[0].state.to_dict()['accounts'][0]['id']
        self.assertNotIn(old_id, {account['id'] for account in restored.state.to_dict()['accounts']})
        oracle = self.identities(row, restored.checkpoint.expected, (old_id,))
        self.assertTrue(oracle.used(old_id))
        stale = self.db.sql(self.fixture.lookup(original, [old_id]), role=self.actor, check=False)
        self.assertNotEqual(stale.returncode, 0); self.assertIn('portable_native_lookup_head_mismatch', stale.stderr)
        # Independent current preparation also refuses a reused retired UUID.
        paused = self.fixture.control(row, 'pause', serial=72); self.assert_next(row, paused); row = paused
        resumed = self.fixture.control(row, 'resume', serial=73); self.assert_next(row, resumed); row = resumed
        before_protective = row
        context = self.capture_context_before_source(row, serial=74)
        state = row[3].accept(row[0]); data = state.to_dict()
        at, received_at, decision_at = self.current_source_clock(state)
        received_mono = MONO + received_at - initial_at
        mono = MONO + decision_at - initial_at
        frame = ga.source.make_frame(raw_capture(price='100', block=901,
            source_second=int(received_at) - 2, wall=received_at, mono=received_mono), prior_source=data['source'],
            epoch=EPOCH, wall_now=decision_at, monotonic_now=mono)
        protective = ga.prepare_protective(state, frame, source_inputs(at, wall=decision_at, mono=mono, serial=74), ledger=row[3])
        capture = cp.capture_owned_candidate(protective)
        following = (protective, capture, cp.prepare_transport(protective, capture, previous=row[1],
            command_id=str(UUID(int=98000000 + protective.state.revision))), row[3])
        self.commit_source_once(row, following); row = following
        self.assert_equivalent(before_protective, row, self.restore_captured_context(before_protective, context))
        state = row[3].accept(row[0]); restored = self.load(row)
        original_inputs = source_inputs(at, wall=decision_at, mono=mono, generation=2, serial=75)
        reused_inputs = replace(original_inputs, ids=(old_id,) + original_inputs.ids[1:])
        checked = self.identities(row, restored.checkpoint.expected, reused_inputs.ids)
        self.assertTrue(checked.used(old_id))
        before = self.fixture.snapshot()
        with self.assertRaises(ga.ExactRehearsalError):
            ga.prepare_decision(state, frame, None, reused_inputs, ledger=row[3])
        with self.assertRaises(ga.ExactRehearsalError):
            restore.prepare_restored_candidate(restored, reused_inputs, checked, phase='decision', frame=frame)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_expired_original_source_reports_later_rollback_state_without_retry(self):
        self.fixture.create(lease=60); original = self.fixture.bootstrap(); self.fixture.commit(original[2])
        before = self.fixture.snapshot()
        state = original[3].accept(original[0]); data = state.to_dict()
        at, received_at, decision_at = self.current_source_clock(state)
        initial_at = int(datetime.fromisoformat(original[0].transition['evidence']['inputs']['event_at']).timestamp())
        received_mono = MONO + received_at - initial_at
        mono = MONO + decision_at - initial_at
        frame = ga.source.make_frame(raw_capture(price='100', block=900,
            source_second=int(received_at) - 2, wall=received_at, mono=received_mono), prior_source=data['source'],
            epoch=EPOCH, wall_now=decision_at, monotonic_now=mono)
        protective = ga.prepare_protective(state, frame,
            source_inputs(at, wall=decision_at, mono=mono, serial=80), ledger=original[3])
        capture = cp.capture_owned_candidate(protective)
        following = (protective, capture, cp.prepare_transport(protective, capture, previous=original[1],
            command_id=str(UUID(int=99000000 + protective.state.revision))), original[3])
        # Expire this already prepared original on genuine elapsed DB time. No
        # timestamp/quote substitution, heartbeat, rebasing or second attempt.
        observed = json.loads(self.db.scalar('SELECT pg_sleep(6);SELECT jsonb_build_object('
            + "'observed_at_us',floor(extract(epoch FROM clock_timestamp())*1000000)::text,"
            + "'lease_until_us',floor(extract(epoch FROM lease_until)*1000000)::text)"
            + ' FROM vn_portable_native_research.runs WHERE owner_id=' + literal(OWNER)
            + ' AND run_id=' + literal(RUN) + ';'))
        self.assertGreater(int(observed['observed_at_us']), frame['quote']['document']['received_wall_us'] + 5000000)
        self.assertLess(int(observed['observed_at_us']), int(observed['lease_until_us']))
        output = io.StringIO()
        with patch.object(self.fixture, 'commit', wraps=self.fixture.commit) as one_original, redirect_stdout(output):
            with self.assertRaises(SqlFailure) as failure:
                self.commit_source_once(original, following)
        self.assertIn('portable_native_source_expired', str(failure.exception))
        one_original.assert_called_once_with(following[2])
        diagnostic = json.loads(output.getvalue())
        self.assertEqual(diagnostic['native_source_failure_observation'], 'after-original-refusal-and-rollback')
        self.assertFalse(diagnostic['failed_guard_instant_observed'])
        self.assertFalse(diagnostic['failed_branch_attribution_authority'])
        self.assertFalse(diagnostic['retry_performed'])
        self.assertTrue(diagnostic['source_deadline_elapsed_at_later_observation'])
        self.assertFalse(diagnostic['lease_expired_at_later_observation'])
        self.assertFalse(diagnostic['original_command_found_after_failure'])
        self.assertEqual(diagnostic['original_command_id'], numbers.decode(following[2])['command_id'])
        self.assertEqual(diagnostic['original_command_sha256'], hashlib.sha256(following[2]).hexdigest())
        self.assertEqual(int(diagnostic['accepted_revision']), original[0].state.revision)
        self.assertEqual(diagnostic['accepted_command_id'], numbers.decode(original[2])['command_id'])
        self.assertEqual(diagnostic['accepted_manifest_sha256'], self.fixture.manifest_sha(original))
        # Pure exception-preservation subproof only: no second SQL submission or
        # diagnostic DB read. A reporter/output exception cannot mask the very
        # same original SqlFailure instance observed above.
        with patch.object(self.fixture, 'commit', side_effect=failure.exception) as no_database_retry, \
             patch.object(self, 'report_source_failure_after_rollback', side_effect=BrokenPipeError('test-only-output-error')), \
             patch.object(self.db, 'sql', side_effect=AssertionError('pure-error-proof-must-not-call-db')):
            with self.assertRaises(SqlFailure) as preserved:
                self.commit_source_once(original, following)
        self.assertIs(preserved.exception, failure.exception)
        no_database_retry.assert_called_once_with(following[2])
        self.assertEqual(self.fixture.read(following), {'format': restore.COMMAND_READBACK_FORMAT, 'found': False})
        self.assertEqual(self.fixture.snapshot(), before)
        print(json.dumps(diagnostic, sort_keys=True))

    def test_combined_readback_error_after_commit_reconciles_original_without_decision(self):
        self.fixture.create(lease=60); original = self.fixture.bootstrap(); self.fixture.commit(original[2])
        state = original[3].accept(original[0]); data = state.to_dict()
        at, received_at, decision_at = self.current_source_clock(state)
        initial_at = int(datetime.fromisoformat(original[0].transition['evidence']['inputs']['event_at']).timestamp())
        received_mono = MONO + received_at - initial_at
        mono = MONO + decision_at - initial_at
        frame = ga.source.make_frame(raw_capture(price='100', block=900,
            source_second=int(received_at) - 2, wall=received_at, mono=received_mono), prior_source=data['source'],
            epoch=EPOCH, wall_now=decision_at, monotonic_now=mono)
        protective = ga.prepare_protective(state, frame,
            source_inputs(at, wall=decision_at, mono=mono, serial=85), ledger=original[3])
        capture = cp.capture_owned_candidate(protective)
        following = (protective, capture, cp.prepare_transport(protective, capture, previous=original[1],
            command_id=str(UUID(int=100000000 + protective.state.revision))), original[3])
        ids = source_inputs(at, generation=1, serial=86).ids
        original_query = self.context_query
        output = io.StringIO()
        with patch.object(self, 'context_query', side_effect=lambda row, asked:
                original_query(row, asked) + 'SELECT 1/0;'), \
                patch.object(self.db, 'sql', wraps=self.db.sql) as submissions, redirect_stdout(output):
            with self.assertRaises(SqlFailure) as failure:
                self.commit_protective_and_capture_once(original, following, ids)
        self.assertIn('division by zero', str(failure.exception))
        source_submissions = [call for call in submissions.call_args_list
            if self.fixture.sql(following[2]) in call.args[0]]
        self.assertEqual(len(source_submissions), 1)
        diagnostic = json.loads(output.getvalue())
        self.assertEqual(diagnostic['combined_original_protective_outcome'], 'uncertain-until-fresh-getter')
        self.assertTrue(diagnostic['fresh_original_command_found'])
        self.assertFalse(diagnostic['retry_performed']); self.assertFalse(diagnostic['decision_submitted'])
        self.assertEqual(diagnostic['original_command_id'], numbers.decode(following[2])['command_id'])
        self.assertEqual(diagnostic['original_command_sha256'], hashlib.sha256(following[2]).hexdigest())
        before = self.fixture.snapshot()
        observed = self.fixture.read(following)
        self.assertEqual(observed['original_command_wire'].encode(), following[2])
        self.assertTrue(observed['receipt']['record_observed'])
        self.assertEqual(self.load(following).state.to_dict(), protective.state.to_dict())
        self.assertEqual(self.fixture.snapshot(), before)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_portable_native_research.commands;'), '2')
        print(json.dumps(diagnostic, sort_keys=True))


if __name__ == '__main__': unittest.main()
