"""Real offline PG17 locking/replay proof; never a production v6 installer."""
import json
import os
from pathlib import Path
import time
import unittest

from tests.postgres import canonical_fixture as canonical, harness, installer_fixture
from tests.postgres.test_provider_contract import (
    ProviderContractTests as _ProviderTests, decision_inputs, quote_frame,
)
from tests.postgres.test_command_adapter import identity, literal
from tests.postgres.test_decimal_lineage_contract import document
from vonneumann.core import provider_lifecycle as core
from vonneumann.research.checkpoint_reference import CheckpointReference, encode_owned_candidate

SQL = Path(__file__).resolve().parents[2] / 'db-contract' / 'research' / 'checkpoint_reference.sql'


def load_tests(loader, tests, pattern):
    # Do not rediscover inherited v5 behavioral tests in this research suite.
    return unittest.TestSuite(CheckpointReferenceSqlTests(name)
        for name in sorted(CheckpointReferenceSqlTests.__dict__) if name.startswith('test_'))


@unittest.skipUnless(os.environ.get(harness.OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class CheckpointReferenceSqlTests(_ProviderTests):
    @classmethod
    def setUpClass(cls):
        cls.db = canonical.start(cls)
        rejected = cls.db.sql(SQL.read_text(), check=False)
        if rejected.returncode == 0 or 'offline_checkpoint_fixture_required' not in rejected.stderr:
            raise AssertionError('Research artifact installed without its offline marker')
        cls.db.sql("SET dashboard.checkpoint_reference_fixture='offline-v1'; BEGIN;" + SQL.read_text() + 'COMMIT;')
        # No grants ship in the artifact. Grant only synthetic fixture clients.
        cls.db.sql('''GRANT USAGE ON SCHEMA vn_checkpoint_research TO vn_economic;
GRANT EXECUTE ON FUNCTION vn_checkpoint_research.reference(uuid,uuid),
 vn_checkpoint_research.commit_reference(uuid,uuid,uuid,bigint,bigint,uuid,jsonb),
 vn_checkpoint_research.get_reference_command(uuid,uuid,uuid) TO vn_economic;''')

    def reference(self):
        return CheckpointReference.from_dict(json.loads(self.db.scalar(
            f'SELECT vn_checkpoint_research.reference({literal(self.owner)},{literal(self.run)});',
            role='vn_economic')))

    def prepare(self):
        config, boot = self.prepare_bootstrap()
        ref = self.reference()
        return config, boot, encode_owned_candidate(boot, ref)

    def compact_sql(self, payload, command_id, *, owner=None, revision=None, worker=None, token=1):
        ref = payload['before_reference']
        return 'SELECT vn_checkpoint_research.commit_reference(' + ','.join((
            literal(self.owner if owner is None else owner), literal(self.run),
            literal(self.worker if worker is None else worker), str(token),
            str(ref['revision'] if revision is None else revision), literal(command_id), document(payload))) + ');'

    def compact_commit(self, encoded, command_id=None):
        command_id = identity() if command_id is None else command_id
        result = self.db.scalar(self.compact_sql(encoded.to_dict(), command_id), role='vn_economic')
        return command_id, json.loads(result)

    def all_effects(self):
        return self.snapshot() + self.db.scalar(f"SELECT md5(coalesce(string_agg(to_jsonb(r)::text,',' ORDER BY command_id),'')) "
            f'FROM vn_checkpoint_research.requests r WHERE run_id={literal(self.run)};') + self.db.scalar(
            'SELECT jsonb_build_array(' + ','.join("(SELECT md5(coalesce(string_agg(to_jsonb(t)::text,',' ORDER BY to_jsonb(t)::text),'')) "
                f'FROM vn_projection.{table} t WHERE run_id={literal(self.run)})'
                for table in ('runs', 'probes', 'trades', 'evaluations')) + ');')

    def protected(self, state):
        now, mono = time.time(), time.monotonic()
        frame = quote_frame(state, now, mono)
        return core.prepare_protective(state, frame, decision_inputs(now, mono))

    def test_bootstrap_protective_stop_keep_original_wire_and_v5_model_effects(self):
        _, boot, encoded = self.prepare()
        command, receipt = self.compact_commit(encoded)
        self.assertEqual(receipt['revision'], 2)
        protected = self.protected(boot.state)
        ref = self.reference()
        compact = encode_owned_candidate(protected, ref)
        self.assertLess(compact.payload_bytes, protected.payload_bytes)
        self.assertEqual(int(self.db.scalar('SELECT octet_length(' + document(compact.to_dict()) + '::text);')),
                         compact.payload_bytes)
        self.compact_commit(compact)
        stopped = core.prepare_control(protected.state, 'stop', decision_inputs())
        self.compact_commit(encode_owned_candidate(stopped, self.reference()))
        self.assertEqual(self.db.scalar(f'SELECT engine_state FROM vn_durability.runs WHERE id={literal(self.run)};'),
                         self.db.scalar('SELECT ' + document(stopped.state.to_dict()) + ';'))
        read = json.loads(self.db.scalar('SELECT vn_checkpoint_research.get_reference_command(' +
            ','.join((literal(self.owner), literal(self.run), literal(command))) + ');', role='vn_economic'))
        self.assertEqual(read['request']['payload'], encoded.to_dict())
        self.assertEqual(read['response'], receipt)
        self.assertEqual(read['request']['command_id'], command)

    def test_lost_reply_replay_after_advance_does_not_resolve_a_new_checkpoint(self):
        _, boot, encoded = self.prepare()
        command, first = self.compact_commit(encoded)
        protected = self.protected(boot.state)
        self.compact_commit(encode_owned_candidate(protected, self.reference()))
        before = self.all_effects()
        _, replay = self.compact_commit(encoded, command)
        self.assertEqual(replay, first)
        self.assertEqual(self.all_effects(), before)
        changed = encoded.to_dict(); changed['before_reference']['sha256'] = '0' * 64
        denied = self.db.sql(self.compact_sql(changed, command), role='vn_economic', check=False)
        self.assertIn('reference_command_conflict', denied.stderr)
        self.assertEqual(self.all_effects(), before)

    def test_changed_owner_run_revision_hash_and_shape_are_denied_without_effects(self):
        _, boot, encoded = self.prepare()
        before = self.all_effects()
        for field, value in (('owner_id', identity()), ('run_id', identity()), ('revision', 99),
                             ('revision', 1.0), ('sha256', '0' * 64), ('hash_policy', 'client-json')):
            changed = encoded.to_dict(); changed['before_reference'][field] = value
            denied = self.db.sql(self.compact_sql(changed, identity(), revision=1), role='vn_economic', check=False)
            self.assertIn('reference_checkpoint_mismatch', denied.stderr)
            self.assertEqual(self.all_effects(), before)
        changed = encoded.to_dict(); changed['transition']['before'] = None
        denied = self.db.sql(self.compact_sql(changed, identity()), role='vn_economic', check=False)
        self.assertNotEqual(denied.returncode, 0)
        self.assertEqual(self.all_effects(), before)
        denied = self.db.sql(self.compact_sql(encoded.to_dict(), identity(), owner=identity()), role='vn_economic', check=False)
        self.assertIn('run_unavailable', denied.stderr)

    def test_wrong_fence_worker_and_expired_authority_deny_even_original_replay(self):
        _, boot, encoded = self.prepare()
        command, _ = self.compact_commit(encoded)
        before = self.all_effects()
        for args in ({'worker': identity()}, {'token': 2}):
            denied = self.db.sql(self.compact_sql(encoded.to_dict(), command, **args), role='vn_economic', check=False)
            self.assertIn('reference_lease_or_contract_lost', denied.stderr)
            self.assertEqual(self.all_effects(), before)
        self.db.sql(f"UPDATE vn_durability.runs SET lease_until=clock_timestamp()-interval '1 second' WHERE id={literal(self.run)};")
        before = self.all_effects()
        denied = self.db.sql(self.compact_sql(encoded.to_dict(), command), role='vn_economic', check=False)
        self.assertIn('reference_lease_or_contract_lost', denied.stderr)
        self.assertEqual(self.all_effects(), before)
        # Readback, not a new identity or mutation, still resolves after expiry.
        resolved = self.db.scalar('SELECT vn_checkpoint_research.get_reference_command(' +
            ','.join((literal(self.owner), literal(self.run), literal(command))) + ');', role='vn_economic')
        self.assertIsNotNone(json.loads(resolved)['response'])

    def test_late_journal_failure_rolls_back_all_v5_effects_then_original_retry_once(self):
        _, boot, encoded = self.prepare()
        command = identity()
        before = self.all_effects()
        self.db.sql(f'ALTER TABLE vn_checkpoint_research.requests ADD CONSTRAINT injected_checkpoint_failure CHECK(run_id<>{literal(self.run)}) NOT VALID;')
        try:
            failed = self.db.sql(self.compact_sql(encoded.to_dict(), command), role='vn_economic', check=False)
            self.assertIn('injected_checkpoint_failure', failed.stderr)
            self.assertEqual(self.all_effects(), before)
        finally:
            self.db.sql('ALTER TABLE vn_checkpoint_research.requests DROP CONSTRAINT injected_checkpoint_failure;')
        self.compact_commit(encoded, command)
        self.assertEqual(self.db.scalar(f'SELECT count(*) FROM vn_checkpoint_research.requests WHERE run_id={literal(self.run)};'), '1')
        self.assertEqual(self.db.scalar(f'SELECT count(*) FROM vn_durability.accounts WHERE run_id={literal(self.run)};'), '8')

    def test_corrupt_economics_and_future_source_fail_the_unchanged_inner_model(self):
        _, boot, encoded = self.prepare()
        before = self.all_effects()
        changed = encoded.to_dict()
        changed['transition']['after']['reserve'] = '0'
        denied = self.db.sql(self.compact_sql(changed, identity()), role='vn_economic', check=False)
        self.assertNotEqual(denied.returncode, 0)
        self.assertEqual(self.all_effects(), before)
        changed = encoded.to_dict()
        changed['transition']['evidence']['source']['wall_us'] += 60_000_000
        denied = self.db.sql(self.compact_sql(changed, identity()), role='vn_economic', check=False)
        self.assertNotEqual(denied.returncode, 0)
        self.assertEqual(self.all_effects(), before)

    def test_wire_and_expanded_capacity_are_independently_enforced(self):
        _, boot, encoded = self.prepare()
        huge = encoded.to_dict(); huge['padding'] = 'x' * 262144
        before = self.all_effects()
        rejected = self.db.sql(self.compact_sql(huge, identity()), role='vn_economic', check=False)
        self.assertIn('reference_wire_capacity_or_identity', rejected.stderr)
        self.assertEqual(self.all_effects(), before)
        self.compact_commit(encoded)
        protected = self.protected(boot.state)
        self.db.sql(f"UPDATE vn_durability.runs SET engine_state=engine_state||jsonb_build_object('padding',repeat('x',262144)) WHERE id={literal(self.run)};")
        payload = encode_owned_candidate(protected, self.reference()).to_dict()
        before = self.all_effects()
        rejected = self.db.sql(self.compact_sql(payload, identity()), role='vn_economic', check=False)
        self.assertIn('reference_expanded_capacity', rejected.stderr)
        self.assertEqual(self.all_effects(), before)

    def test_reference_and_lease_are_rechecked_after_waiting_for_the_run_lock(self):
        for change, expected in (("lease_until=clock_timestamp()-interval '1 second'", 'reference_lease_or_contract_lost'),
                                 ("engine_state='{}'::jsonb", 'reference_checkpoint_mismatch')):
            with self.subTest(change=change):
                self.run, self.worker = identity(), identity()
                _, boot, encoded = self.prepare()
                holder = self.db.real.begin_sql(f"BEGIN; SET application_name='checkpoint-lock-holder'; "
                    f"SELECT id FROM vn_durability.runs WHERE id={literal(self.run)} FOR UPDATE; SELECT pg_sleep(2); "
                    f"UPDATE vn_durability.runs SET {change} WHERE id={literal(self.run)}; COMMIT;", role=installer_fixture.ADMIN)
                deadline = time.monotonic() + 4
                while self.db.scalar("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='checkpoint-lock-holder' AND wait_event='PgSleep');") != 't':
                    if time.monotonic() >= deadline: raise AssertionError('Owned lock holder did not reach its barrier')
                    time.sleep(.02)
                waiting = self.db.real.begin_sql('SET ROLE vn_economic; ' + self.compact_sql(encoded.to_dict(), identity()),
                    role='vn_test_economic_client')
                holder.wait()
                denied = waiting.wait(check=False)
                self.assertIn(expected, denied.stderr)
                self.assertEqual(self.db.scalar(f'SELECT revision FROM vn_durability.runs WHERE id={literal(self.run)};'), '1')
                self.assertEqual(self.db.scalar(f'SELECT count(*) FROM vn_checkpoint_research.requests WHERE run_id={literal(self.run)};'), '0')

    def test_lease_expiry_during_additional_journaling_rolls_back_every_effect(self):
        _, boot, encoded = self.prepare()
        self.db.sql(f"UPDATE vn_durability.runs SET lease_until=clock_timestamp()+interval '2 seconds' WHERE id={literal(self.run)};")
        self.db.sql("CREATE FUNCTION vn_checkpoint_research.delay_journal() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(2.2); RETURN NEW; END $$; "
                    "CREATE TRIGGER research_delay BEFORE INSERT ON vn_checkpoint_research.requests FOR EACH ROW EXECUTE FUNCTION vn_checkpoint_research.delay_journal();")
        before = self.all_effects()
        try:
            denied = self.db.sql(self.compact_sql(encoded.to_dict(), identity()), role='vn_economic', check=False)
            self.assertIn('reference_lease_lost_at_end', denied.stderr)
            self.assertEqual(self.all_effects(), before)
        finally:
            self.db.sql('DROP TRIGGER research_delay ON vn_checkpoint_research.requests; DROP FUNCTION vn_checkpoint_research.delay_journal();')

    def test_source_expiry_during_additional_journaling_rolls_back_every_effect(self):
        _, boot, encoded = self.prepare()
        self.db.sql("CREATE FUNCTION vn_checkpoint_research.delay_journal() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(5.1); RETURN NEW; END $$; "
                    "CREATE TRIGGER research_delay BEFORE INSERT ON vn_checkpoint_research.requests FOR EACH ROW EXECUTE FUNCTION vn_checkpoint_research.delay_journal();")
        before = self.all_effects()
        try:
            denied = self.db.sql(self.compact_sql(encoded.to_dict(), identity()), role='vn_economic', check=False)
            self.assertIn('provider_receipt_expired', denied.stderr)
            self.assertEqual(self.all_effects(), before)
        finally:
            self.db.sql('DROP TRIGGER research_delay ON vn_checkpoint_research.requests; DROP FUNCTION vn_checkpoint_research.delay_journal();')

    def test_anonymous_browser_service_relay_and_other_owner_cannot_read_research_records(self):
        _, boot, encoded = self.prepare()
        command, _ = self.compact_commit(encoded)
        for role in ('anon', 'authenticated', 'service_role', 'vn_relay'):
            denied = self.db.sql(f'SELECT vn_checkpoint_research.reference({literal(self.owner)},{literal(self.run)});',
                                 role=role, check=False)
            self.assertNotEqual(denied.returncode, 0)
            denied = self.db.sql('SELECT * FROM vn_checkpoint_research.requests;', role=role, check=False)
            self.assertNotEqual(denied.returncode, 0)
        denied = self.db.sql('SELECT vn_checkpoint_research.get_reference_command(' +
            ','.join((literal(identity()), literal(self.run), literal(command))) + ');', role='vn_economic', check=False)
        self.assertIn('run_unavailable', denied.stderr)
        self.assertEqual(self.db.scalar("SELECT NOT EXISTS(SELECT 1 FROM pg_proc p, LATERAL "
            "aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE "
            "p.pronamespace='vn_checkpoint_research'::regnamespace AND a.grantee=0 AND a.privilege_type='EXECUTE');"), 't')
