"""Atomic curated history and durable relay/archive in the offline SQL fixture."""
from __future__ import annotations
from decimal import Decimal, localcontext
import json
from pathlib import Path

from tests.lifecycle_fixtures import lifecycle_trace
from tests.postgres.test_command_adapter import identity, literal
from tests.postgres import test_lifecycle_contract as lifecycle_tests

PROJECTIONS = Path(__file__).resolve().parents[2] / 'db-contract' / '002_read_projections.sql'


class ReadProjectionTests(lifecycle_tests.LifecycleContractTests):
    # Also rerun the inherited real traces for all four optimizers through the
    # projection trigger, including replacement, terminal, recovery and controls.
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.db.sql("SET dashboard.contract_rehearsal='db03a1-isolated';\n" + PROJECTIONS.read_text(), timeout=30)

    def setUp(self):
        self.db.sql("TRUNCATE TABLE vn_durability.runs CASCADE;")
        super().setUp()
        context = localcontext()
        context.__enter__().prec = 100
        self.addCleanup(context.__exit__, None, None, None)

    def apply_trace(self, kind, strategy='genetic_algorithm'):
        # One complete trace per owned 256 MiB tmpfs. This is fixture-only
        # cleanup, never a journal retention policy or application operation.
        self.db.sql("TRUNCATE TABLE vn_durability.runs CASCADE;")
        return super().apply_trace(kind, strategy)

    def as_owner(self, sql, owner=None):
        return json.loads(self.db.scalar(
            f"SET request.jwt.claim.sub={literal(owner or self.owner)};\n" + sql,
            role='authenticated'))

    def page(self, kind, *, through=None, after=(0, ''), rows=100, size=65536):
        args = (literal(self.run), literal(kind), 'NULL' if through is None else str(through),
                str(after[0]), literal(after[1]), str(rows), str(size))
        return self.as_owner('SELECT vn_read.page(' + ','.join(args) + ');')

    def latest(self, table):
        return json.loads(self.db.scalar(f"SELECT coalesce(jsonb_agg(data),'[]') FROM "
            f"(SELECT DISTINCT ON (entity_key) data FROM vn_projection.{table} "
            f"WHERE run_id={literal(self.run)} ORDER BY entity_key,revision DESC) p;"))

    def bootstrap(self):
        config, candidates = lifecycle_trace('pause_stop', owner_id=self.owner, run_id=self.run)
        self.db.sql(self.create_sql(config), role='service_role')
        command = identity()
        self.db.sql(self.sql(self.payload(candidates[0]), command), role='service_role', timeout=30)
        return candidates, command

    def test_frozen_cash_and_old_evaluations_survive_replacement_without_double_counting(self):
        for kind in ('replacement', 'terminal'):
            _, candidates = self.apply_trace(kind)
            before = candidates[-1].transition['before']
            operations = candidates[-1].operations
            final = candidates[-1].state.to_dict()
            latest = {p['id']: p for p in self.latest('probes')}
            old_ids = {m['id'] for m in before['engine']['members']}
            expected = {a['id']: Decimal(a['cash']) for a in before['accounts']}
            position_owner = {p['id']: p['account_id'] for p in final['positions']}
            frozen = {}
            for op in operations:
                if op['kind'] == 'close':
                    expected[position_owner[op['id']]] += Decimal(op['proceeds']) - Decimal(op['fee'])
                elif op['kind'] == 'open':
                    expected[op['account_id']] -= Decimal(op['notional']) + Decimal(op['fee'])
                elif op['kind'] == 'retire':
                    frozen[op['id']] = expected[op['id']]
                    expected[op['id']] = Decimal(0)
            for probe_id in old_ids:
                row = latest[probe_id]
                self.assertTrue(row['retired'])
                self.assertEqual(Decimal(row['economic_cash']), 0)
                self.assertIsNone(row['equity'])
                self.assertGreater(Decimal(row['terminal_cash']), 0)
                if probe_id in frozen:
                    self.assertEqual(Decimal(row['terminal_cash']), frozen[probe_id])
                self.assertEqual(row['metrics_basis'], 'last_observed_before_replacement')
            self.assertEqual(len(latest), 16)
            evaluation = self.latest('evaluations')[0]
            self.assertEqual(set(evaluation['cohort']['member_ids']), old_ids)
            self.assertEqual(len(evaluation['terminal_accounts']), 8)
            run = self.latest('runs')[0]
            expected_equity = Decimal(final['reserve']) + sum(Decimal(a['cash']) for a in final['accounts'])
            mark = Decimal(final['engine']['last_quote']['price'])
            expected_equity += sum(Decimal(p['entry']['quantity']) * mark for p in final['positions'] if not p['closed'])
            self.assertEqual(Decimal(run['reference_equity']), expected_equity)
            self.assertEqual(run['account_currency'], 'USD')
            self.assertNotIn('optimizer', json.dumps(evaluation))

    def test_owner_revision_pagination_is_bounded_and_stable_after_later_commands(self):
        candidates, _ = self.bootstrap()
        first = self.page('probes', rows=1, size=4096)
        self.assertTrue(first['has_more'])
        self.assertLessEqual(len(json.dumps(first, ensure_ascii=False).encode()), 4096)
        self.db.sql(self.sql(self.payload(candidates[1])), role='service_role')
        collected = first['records'][:]
        page = first
        while page['has_more']:
            cursor = page['next_cursor']
            page = self.page('probes', through=first['through_revision'],
                             after=(cursor['revision'], cursor['key']), rows=1, size=4096)
            collected.extend(page['records'])
        self.assertEqual(len(collected), 8)
        self.assertEqual({r['revision'] for r in collected}, {2})
        self.assertEqual(len({r['key'] for r in collected}), 8)
        for row in collected:
            self.assertIsNone(row['data']['fitness'])
            self.assertNotIn('optimizer', row['data'])
        foreign = identity()
        self.db.sql(f'INSERT INTO auth.users VALUES({literal(foreign)});')
        denied = self.db.sql(f"SET request.jwt.claim.sub={literal(foreign)}; SELECT vn_read.page({literal(self.run)},'runs');", role='authenticated', check=False)
        self.assertIn('run_unavailable', denied.stderr)
        for kind in ('events', 'runs; DROP SCHEMA public CASCADE'):
            denied = self.db.sql(f"SET request.jwt.claim.sub={literal(self.owner)}; SELECT vn_read.page({literal(self.run)},{literal(kind)});", role='authenticated', check=False)
            self.assertIn('invalid_read_kind', denied.stderr)
        denied = self.db.sql(f"SET request.jwt.claim.sub={literal(self.owner)}; SELECT vn_read.page({literal(self.run)},'probes',NULL,0,'',100,512);", role='authenticated', check=False)
        self.assertIn('read_record_exceeds_page', denied.stderr)

    def test_projection_failure_rolls_back_economics_checkpoint_journal_and_outbox(self):
        config, candidates = lifecycle_trace('pause_stop', owner_id=self.owner, run_id=self.run)
        self.db.sql(self.create_sql(config), role='service_role')
        command = identity()
        def counts():
            return self.db.scalar(f"SELECT jsonb_build_object('revision',(SELECT revision FROM vn_durability.runs WHERE id={literal(self.run)}),"
                f"'checkpoint',(SELECT engine_state FROM vn_durability.runs WHERE id={literal(self.run)}),"
                "'accounts',(SELECT count(*) FROM vn_durability.accounts),"
                "'commands',(SELECT count(*) FROM vn_durability.commands),"
                "'outbox',(SELECT count(*) FROM vn_durability.outbox_events),"
                "'probes',(SELECT count(*) FROM vn_projection.probes),"
                "'runs',(SELECT count(*) FROM vn_projection.runs));")
        before = counts()
        self.db.sql(f"ALTER TABLE vn_projection.runs ADD CONSTRAINT injected_failure CHECK(run_id<>{literal(self.run)}) NOT VALID;")
        try:
            failed = self.db.sql(self.sql(self.payload(candidates[0]), command), role='service_role', check=False)
            self.assertIn('injected_failure', failed.stderr)
            self.assertEqual(counts(), before)
        finally:
            self.db.sql('ALTER TABLE vn_projection.runs DROP CONSTRAINT injected_failure;')
        first = self.db.scalar(self.sql(self.payload(candidates[0]), command), role='service_role')
        acknowledged = counts()
        self.assertEqual(self.db.scalar(self.sql(self.payload(candidates[0]), command), role='service_role'), first)
        self.assertEqual(counts(), acknowledged)

    def event_call(self, name, command, index):
        return 'SELECT ' + name + '(' + ','.join((literal(self.owner), literal(self.run), literal(command), str(index))) + ');'

    def events(self, through=None, after=0, rows=100):
        return self.as_owner('SELECT vn_read.events(' + ','.join((literal(self.run),
            'NULL' if through is None else str(through), str(after), str(rows))) + ');')

    def test_durable_acceptance_precedes_ack_and_late_events_do_not_move_replay_cutoff(self):
        _, command = self.bootstrap()
        ack = self.event_call('vn_durability.acknowledge_event', command, 0)
        failed = self.db.sql(ack, role='service_role', check=False)
        self.assertIn('durable_relay_acceptance_required', failed.stderr)
        first = json.loads(self.db.scalar(self.event_call('vn_read.accept_event', command, 0), role='service_role'))
        self.assertEqual(first['sequence'], 1)
        self.assertEqual(json.loads(self.db.scalar(self.event_call('vn_read.accept_event', command, 0), role='service_role')), first)
        page = self.events(rows=1)
        self.assertEqual(page['through_sequence'], 1)
        # Lost acceptance/ACK replies replay the original stable identity.
        self.db.sql(ack, role='service_role')
        self.db.sql(ack, role='service_role')
        # Accept out of order deliberately; sequence tracks acceptance, not
        # lexical event IDs or command revisions. Core ACK remains contiguous.
        self.db.sql(self.event_call('vn_read.accept_event', command, 8), role='service_role')
        self.db.sql(self.event_call('vn_read.accept_event', command, 1), role='service_role')
        self.assertEqual(self.events(through=1, after=1)['records'], [])
        next_page = self.events(after=1)
        self.assertEqual([r['sequence'] for r in next_page['records']], [2, 3])
        self.assertEqual([r['data']['event_index'] for r in next_page['records']], [8, 1])
        failed = self.db.sql(self.event_call('vn_durability.acknowledge_event', command, 8), role='service_role', check=False)
        self.assertIn('outbox_acknowledgement_out_of_order', failed.stderr)
        self.db.sql(self.event_call('vn_durability.acknowledge_event', command, 1), role='service_role')
        self.assertEqual(len(self.events()['records']), 3)

    def test_concurrent_acceptance_serializes_sequences_under_run_lock(self):
        _, command = self.bootstrap()
        first = self.db.begin_sql('BEGIN; ' + self.event_call('vn_read.accept_event', command, 0) +
            ' SELECT pg_sleep(.4); COMMIT;', role='service_role', timeout=5)
        second = self.db.begin_sql(self.event_call('vn_read.accept_event', command, 1), role='service_role', timeout=5)
        first.wait(); second.wait()
        rows = self.events()['records']
        self.assertEqual([r['sequence'] for r in rows], [1, 2])
        self.assertEqual({r['data']['event_index'] for r in rows}, {0, 1})
        for index in (0, 1):
            self.db.sql(self.event_call('vn_read.accept_event', command, index), role='service_role')
        self.assertEqual(len(self.events()['records']), 2)

    def test_archive_is_owner_run_specific_idempotent_and_retains_open_exposure(self):
        _, candidates = self.apply_trace('pause_stop')
        final = candidates[-1].state.to_dict()
        request = identity()
        sql = 'SELECT vn_read.archive_run(' + ','.join((literal(self.run), str(final['revision']), literal(request))) + ');'
        before = self.db.scalar(f"SELECT count(*) FROM vn_durability.positions WHERE run_id={literal(self.run)};")
        receipt = self.as_owner(sql)
        self.assertTrue(receipt['archived'])
        self.assertEqual(receipt['retained_open_positions'], 8)
        self.assertTrue(receipt['retained_exposure'])
        self.assertTrue(receipt['requires_reconciliation'])
        self.assertEqual(receipt['classification'], 'known_terminal_checkpoint')
        self.assertEqual(self.as_owner(sql), receipt)
        self.assertEqual(self.db.scalar(f"SELECT count(*) FROM vn_durability.positions WHERE run_id={literal(self.run)};"), before)
        failed = self.db.sql(f"SET request.jwt.claim.sub={literal(self.owner)}; SELECT vn_read.archive_run({literal(self.run)},{final['revision']},{literal(identity())});", role='authenticated', check=False)
        self.assertIn('archive_request_conflict', failed.stderr)
        self.run, self.worker = identity(), identity()
        self.bootstrap()
        failed = self.db.sql(f"SET request.jwt.claim.sub={literal(self.owner)}; SELECT vn_read.archive_run({literal(self.run)},2,{literal(identity())});", role='authenticated', check=False)
        self.assertIn('archive_unavailable', failed.stderr)

    def test_curated_rpc_grants_do_not_expose_core_projection_or_private_helpers(self):
        self.bootstrap()
        for role in ('anon', 'authenticated', 'service_role'):
            for sql in ('SELECT * FROM vn_projection.probes;', 'SELECT * FROM vn_durability.commands;',
                        'SELECT vn_projection.project_command();'):
                with self.subTest(role=role, sql=sql):
                    denied = self.db.sql(sql, role=role, check=False)
                    self.assertNotEqual(denied.returncode, 0)
                    self.assertIn('permission denied', denied.stderr)
        for role in ('anon', 'service_role'):
            denied = self.db.sql(f"SELECT vn_read.page({literal(self.run)},'runs');", role=role, check=False)
            self.assertIn('permission denied', denied.stderr)
        denied = self.db.sql(self.event_call('vn_read.accept_event', identity(), 0), role='authenticated', check=False)
        self.assertIn('permission denied', denied.stderr)
