"""Trusted, explicit cash-only interruption after native write authority expires."""
import json
import os
from pathlib import Path
import unittest
from uuid import uuid4

from tests.postgres import harness, forward_fixture as fixture
from tests.postgres import test_paper_service as paper_fixture
from vonneumann.market.feed import MarketFeedError

SOURCE = Path(__file__).resolve().parents[4] / 'supabase/operations/2026-10-08-reconcile-expired-cash-only-paper-run.sql'


@unittest.skipUnless(os.environ.get(harness.OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class ExpiredPaperMaintenanceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = fixture.start(cls)

    setUp = paper_fixture.PaperFlowSqlTests.setUp
    asyncTearDown = paper_fixture.PaperFlowSqlTests.asyncTearDown
    wait = paper_fixture.PaperFlowSqlTests.wait

    def snapshot(self):
        query = """SELECT jsonb_build_object('revision',revision,'fence',fence,
          'reserve',reserve::text,'checkpoint_sha256',encode(sha256(convert_to(engine_state::text,'UTF8')),'hex'),
          'accounts_sha256',encode(sha256(convert_to((SELECT jsonb_agg(to_jsonb(a) ORDER BY id)::text
            FROM vn_durability.accounts a WHERE a.run_id=r.id),'UTF8')),'hex'),
          'positions_sha256',encode(sha256(convert_to(coalesce((SELECT jsonb_agg(to_jsonb(p) ORDER BY id)::text
            FROM vn_durability.positions p WHERE p.run_id=r.id),'[]'),'UTF8')),'hex'))
          FROM vn_durability.runs r WHERE id='""" + self.run + "';"
        return json.loads(self.db.scalar(query, role=fixture.ADMIN))

    async def failed_run(self, revoke=True):
        async def failure(_assets):
            raise MarketFeedError('price_stale')
        self.feed.get_price_captures = failure
        self.service.start(self.ids['owner'], self.start)
        await self.wait()
        self.assertEqual(self.service._phase, 'failed')
        await self.service.close()
        self.db.sql("UPDATE vn_durability.runs SET lease_until='1970-01-01' WHERE id='" + self.run + "';", role=fixture.ADMIN)
        if revoke:
            pair = self.transport.pair
            self.db.sql(self.db.revoke_source(pair, self.db.oids(pair)))
        self.input = {**self.snapshot(), 'owner': self.ids['owner'], 'run': self.run, 'command': str(uuid4())}

    def operation(self, value=None, rollback=False, suffix='', role='postgres'):
        body = json.dumps(self.input if value is None else value, sort_keys=True).replace("'", "''")
        sql = SOURCE.read_text().replace('__INPUT_JSON__', body)
        sql = sql.removesuffix('COMMIT;\n') + suffix + ('ROLLBACK;\n' if rollback else 'COMMIT;\n')
        if role != 'postgres':
            sql = 'SET ROLE ' + role + ';\n' + sql
            role = fixture.ADMIN
        return self.db.sql(sql, role=role, check=False)

    def journal_count(self):
        return self.db.scalar("SELECT count(*) FROM vn_durability.commands WHERE run_id='" + self.run + "' AND id='" + self.input['command'] + "';", role=fixture.ADMIN)

    def delivery_snapshot(self):
        query = "SELECT jsonb_build_object(" + ','.join(
            "'" + table + "',(SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]'::jsonb) FROM "
            + schema + '.' + table + " t WHERE run_id='" + self.run + "')"
            for schema, table in (('vn_durability', 'outbox_events'),
                                  ('vn_durability', 'outbox_progress'),
                                  ('vn_projection', 'relay_events'))
        ) + ');'
        return json.loads(self.db.scalar(query, role=fixture.ADMIN))

    async def test_actual_rollback_then_one_original_atomic_interruption_preserves_cash_and_checkpoint(self):
        await self.failed_run()
        before = self.snapshot()
        delivery_before = self.delivery_snapshot()
        result = self.operation(rollback=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.journal_count(), '0')
        result = self.operation()
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.snapshot()
        self.assertEqual((after.pop('revision'), after.pop('fence')), (before['revision'] + 1, before['fence'] + 1))
        self.assertEqual(after, {k:v for k,v in before.items() if k not in ('revision', 'fence')})
        self.assertEqual(self.journal_count(), '1')
        state = json.loads(self.db.scalar("SELECT jsonb_build_object('status',status,'reconciliation',requires_reconciliation) FROM vn_durability.runs WHERE id='"+self.run+"';", role=fixture.ADMIN))
        self.assertEqual(state, {'status':'failed','reconciliation':True})
        projection = json.loads(self.db.scalar("SELECT data FROM vn_projection.runs WHERE run_id='" + self.run
            + "' AND revision=" + str(before['revision'] + 1) + ';', role=fixture.ADMIN))
        self.assertEqual((projection['status'], projection['requires_reconciliation']), ('failed', True))
        self.assertEqual(projection['total_probe_count'], 8)
        self.assertIsNone(projection['reference_equity'])
        self.assertEqual(projection['equity_availability'], 'unavailable')
        self.assertEqual(self.delivery_snapshot(), delivery_before)
        self.db.sql((fixture.HERE/'verify.sql').read_text())
        repeat = self.operation()
        self.assertNotEqual(repeat.returncode, 0)
        self.assertEqual(self.journal_count(), '1')

    async def test_live_native_pair_and_unexpired_run_are_denied(self):
        await self.failed_run(revoke=False)
        before = self.snapshot()
        self.assertNotEqual(self.operation().returncode, 0)
        self.assertEqual(self.snapshot(), before)
        pair=self.transport.pair; self.db.sql(self.db.revoke_source(pair,self.db.oids(pair)))
        self.db.sql("UPDATE vn_durability.runs SET lease_until=clock_timestamp()+interval '60s' WHERE id='"+self.run+"';", role=fixture.ADMIN)
        self.assertNotEqual(self.operation().returncode, 0)
        self.assertEqual(self.journal_count(), '0')

    async def test_other_owner_changed_checkpoint_and_revision_are_denied(self):
        await self.failed_run()
        before = self.snapshot()
        for change in ({'owner':self.ids['other']}, {'checkpoint_sha256':'0'*64},
                       {'revision':before['revision']+1}, {'revision':None}, {'fence':None}):
            with self.subTest(change=tuple(change)):
                self.assertNotEqual(self.operation({**self.input,**change}).returncode, 0)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.journal_count(), '0')

    async def test_api_and_capability_roles_have_no_maintenance_authority(self):
        await self.failed_run()
        for role in ('anon','authenticated','service_role','vn_economic','vn_relay'):
            with self.subTest(role=role):
                result = self.operation(role=role)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('maintenance_input_denied', result.stderr)
        self.assertEqual(self.journal_count(), '0')

    async def test_open_position_is_denied_even_with_matching_original_hash(self):
        await self.failed_run()
        self.db.sql("INSERT INTO vn_durability.positions(run_id,user_id,id,account_id,asset,quantity,notional,entry_fee) "
                    "SELECT run_id,user_id,'" + str(uuid4()) + "',id,'SOL/USDC',1,1,0 "
                    "FROM vn_durability.accounts WHERE run_id='" + self.run + "' ORDER BY id LIMIT 1;", role=fixture.ADMIN)
        before = self.snapshot()
        self.input.update(before)
        result = self.operation()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('original_expired_cash_only_run_required', result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.journal_count(), '0')

    async def test_late_failure_rolls_back_terminal_journal_and_projection(self):
        await self.failed_run()
        before = self.snapshot()
        result = self.operation(suffix="DO $$ BEGIN RAISE EXCEPTION 'late_fixture_failure'; END $$;\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.journal_count(), '0')
