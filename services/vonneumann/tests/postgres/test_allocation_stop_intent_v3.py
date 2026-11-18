"""One owned native fixture per actual successor-versus-Stop race."""
import copy
import json
import os
import unittest
from contextlib import ExitStack, closing
from uuid import UUID

from tests.postgres.allocation_control_v3_fixture import (
    AllocationFixture, AllocationHandoffPostgres, A, ANCHOR_OWNER, BEGIN, N, SETTINGS, canonical, literal, sha,
)
from tests.postgres.harness import OPT_IN
from tests.postgres.test_allocation_control_v3 import issue_handoff, prepare_handoff


@unittest.skipUnless(os.environ.get(OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class AllocationStopIntentNativeTests(unittest.TestCase):
    def setUp(self):
        self.db = AllocationHandoffPostgres().start()
        self.addCleanup(self.db.close)
        self.fixture = AllocationFixture(self.db, creator_edges=True)

    def ready(self):
        plan = prepare_handoff(self.fixture)
        issue_handoff(self.fixture, plan)
        scope = plan['scope']
        reader = scope['actors']['reader']
        control = scope['actors']['control']
        successor = plan['successor']
        for actor in (reader, control, successor):
            self.assertEqual(
                self.db.scalar(
                    'SELECT session_user,system_user,ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid();',
                    role=actor,
                ),
                f'{actor}|scram-sha-256:{actor}|t',
            )
        self.assertEqual(self.fixture.head(scope)['native_sequence'], '3')
        self.assertEqual(self.fixture.head(scope)['source_mode'], 'open')
        return plan, scope, reader, control, successor

    def intent_query(self, entry, value):
        self.assertIn(entry, ('record_stop_intent', 'get_stop_intent'))
        return f'SELECT {N}.{entry}({literal(canonical(value))});\n'

    def record_query(self, stop):
        return self.intent_query('record_stop_intent', stop)

    def get_query(self, stop):
        return self.intent_query('get_stop_intent', self.fixture.query(stop))

    def inspect_intent(self, stop, reader):
        result = self.db.sql(SETTINGS + self.get_query(stop), role=reader)
        value = json.loads(result.stdout)
        self.assertEqual(canonical(value) + '\n', result.stdout)
        self.assertEqual(value['format'], 'ga-jupiter-b2-stop-intent-observation-research-v3-v1')
        self.assertEqual(value['action_id'], stop['action_id'])
        self.assertEqual(value['scope'], stop['scope'])
        return value

    def assert_absent(self, stop, reader):
        observed = self.inspect_intent(stop, reader)
        self.assertEqual(observed['resolution'], 'observed_absent_unknown')
        self.assertIsNone(observed['intent_wire'])
        self.assertEqual(self.intent_rows(stop['scope']), [])

    def intent_rows(self, scope):
        return json.loads(self.db.scalar(f"""SELECT coalesce(jsonb_agg(jsonb_build_object(
          'scope_wire',scope_wire,'action_id',action_id,'intent_wire',intent_wire,
          'registering_xid',registering_xid::text,'xmin',xmin::text,'ctid',ctid::text)),'[]')
          FROM {N}.stop_intents WHERE scope_wire={literal(canonical(scope))};"""))

    def assert_committed_intent(self, stop, scope, reader):
        observed = self.inspect_intent(stop, reader)
        self.assertEqual(observed['resolution'], 'observed_committed_exact')
        intent_wire = observed['intent_wire']
        intent = json.loads(intent_wire)
        self.assertEqual(canonical(intent), intent_wire)
        self.assertEqual(intent['format'], 'ga-jupiter-b2-stop-intent-research-v3-v1')
        self.assertEqual(intent['installation_id'], scope['installation_id'])
        self.assertEqual(intent['native_package_sha256'], scope['package']['native_package_sha256'])
        self.assertEqual(intent['control_binding_id'], scope['bindings']['control'])
        self.assertEqual(intent['original_command_wire'], canonical(stop))
        self.assertEqual(intent['original_command_sha256'], sha(canonical(stop)))
        marker_wire = self.db.scalar(
            f'SELECT handoff_wire FROM {A}.credential_handoff WHERE scope_wire={literal(canonical(stop["scope"]))};'
        )
        self.assertEqual(intent['effective_catalog_sha256'], json.loads(marker_wire)['catalog_sha256'])
        self.assertNotEqual(intent['effective_catalog_sha256'], scope['package']['catalog_manifest_sha256'])
        self.assertEqual(intent['handoff_sha256'], sha(marker_wire))
        [row] = self.intent_rows(stop['scope'])
        self.assertEqual(row['intent_wire'], intent_wire)
        self.assertEqual(row['action_id'], stop['action_id'])
        self.assertRegex(row['registering_xid'], r'^[1-9][0-9]{0,19}$')
        # Compare actual retained values and both logical declared keys against
        # the separate admin reserve. No physical/WAL limit is inferred.
        metadata = dict(scope=stop['scope'], action_id=row['action_id'],
                        registering_xid=row['registering_xid'],
                        intent_wire_bytes=str(len(intent_wire.encode())))
        charged = len(intent_wire.encode()) + len(canonical(metadata).encode())
        charged += sum(len(canonical(key).encode()) for key in ([stop['scope']], [row['action_id']]))
        self.assertLessEqual(charged, 32768)
        return intent_wire

    def observe_provisional_intent(self, writer, stop):
        writer.send(self.record_query(stop))
        value = json.loads(writer.line())
        self.assertEqual(value, dict(
            format='ga-jupiter-b2-stop-intent-provisional-research-v3-v1',
            scope=stop['scope'], action_id=stop['action_id'],
            original_command_sha256=sha(canonical(stop)), pending_commit=True,
        ))

    def observe_provisional_operation(self, writer, command, actor):
        writer.send(self.fixture.call('submit', command, actor))
        value = json.loads(writer.line())
        self.assertTrue(value['pending_commit'])
        self.assertEqual(value['original_command_sha256'], sha(canonical(command)))

    def wait_for_operation(self, waiter, winner, query):
        waiter.send("SET LOCAL lock_timeout='4000ms';\n")
        waiter_pid = waiter.backend_pid()
        winner_pid = winner.backend_pid()
        waiter.send(query)
        self.fixture.wait_for_blocker(waiter_pid, winner_pid)
        # A psql session can await input after its backend exits. Close this
        # exact child's stdin before checking its expected SQL failure.
        waiter._process.stdin.close()

    def assert_waiter_refused(self, writer, sqlstate, reason):
        error = writer.failure_stderr()
        self.assertNotEqual(writer._process.returncode, 0)
        self.assertEqual(writer._process.stdout.read(), b'')
        self.assertRegex(error, rf'(?m)^ERROR:\s+{sqlstate}: {reason}\s*$')

    def refuse(self, actor, sql, sqlstate, reason=None):
        result = self.db.sql(BEGIN + SETTINGS + sql + 'COMMIT;\n', role=actor, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        if reason is None:
            self.assertRegex(result.stderr, rf'(?m)^ERROR:\s+{sqlstate}:')
        else:
            self.assertRegex(result.stderr, rf'(?m)^ERROR:\s+{sqlstate}: {reason}\s*$')

    def originals(self, commands, reader):
        def immutable(reply):
            return {key: reply[key] for key in (
                'original_command_wire', 'original_result_wire', 'original_receipt_wire', 'dependencies',
            )}
        return [immutable(self.fixture.get(command, reader)) for command in commands]

    def assert_stop(self, stop, scope, reader, control, position, before):
        expected_intent = self.assert_committed_intent(stop, scope, reader)
        intent_before = self.intent_rows(scope['scope'])
        self.assertEqual(before, self.accounting(scope))
        self.assertFalse(before['Stop_reserve_consumed'])
        with closing(self.fixture.writer(control)) as writer:
            self.observe_provisional_operation(writer, stop, control)
            writer.finish()
        reply = self.fixture.get(stop, reader)
        self.assertEqual(reply['original_command_wire'], canonical(stop))
        receipt = json.loads(reply['original_receipt_wire'])
        self.assertEqual(receipt['original_command_sha256'], sha(canonical(stop)))
        self.assertEqual(receipt['native_sequence'], str(position))
        self.assertEqual(reply['observed_head']['native_sequence'], str(position))
        self.assertEqual(self.fixture.head(scope)['source_mode'], 'stopped')
        self.assertTrue(self.accounting(scope)['Stop_reserve_consumed'])
        self.assertEqual(self.intent_rows(scope['scope']), intent_before)
        self.assertEqual(self.assert_committed_intent(stop, scope, reader), expected_intent)
        return reply

    def lifecycle_snapshot(self):
        return [entry for entry in self.fixture.snapshot() if entry[1] != "stop_intents"]

    def accounting(self, scope):
        return json.loads(self.db.scalar(
            f"SELECT accounting_wire FROM {N}.scope_state WHERE scope_wire={literal(canonical(scope['scope']))};"
        ))

    def test_committed_stop_intent_prevents_actual_successor_renew(self):
        plan, scope, reader, control, successor = self.ready()
        f = self.fixture
        stop, renew = plan['stop'], plan['renew']
        originals = self.originals((plan['install'], plan['acquire'], plan['resume']), reader)
        before = self.lifecycle_snapshot()
        accounting = self.accounting(scope)

        self.assert_absent(stop, reader)
        self.refuse(control, f.call('submit', stop, control), '42501', 'b2_stop_intent_required')
        self.refuse(reader, self.record_query(stop), '42501')
        self.refuse(control, self.get_query(stop), '42501')
        self.refuse(successor, f'SELECT count(*) FROM {N}.stop_intents;\n', '42501')
        self.assertEqual(self.lifecycle_snapshot(), before)

        # Both early constraint forcing and combining record+dispatch in the
        # registering transaction must roll back the only staged intent row.
        for statement, sqlstate, reason in (
            ('SET CONSTRAINTS ALL IMMEDIATE;', 'P0001', 'b2_stop_intent_commit_form_refused'),
            (f.call('submit', stop, control), '42501', 'b2_stop_intent_uncommitted'),
        ):
            with closing(f.writer(control)) as trial:
                self.observe_provisional_intent(trial, stop)
                trial.send(statement + '\n')
                trial._process.stdin.close()
                self.assert_waiter_refused(trial, sqlstate, reason)
            self.assert_absent(stop, reader)
            self.assertEqual(self.lifecycle_snapshot(), before)

        with ExitStack() as stack:
            intent_writer = stack.enter_context(closing(f.writer(control)))
            renew_writer = stack.enter_context(closing(f.writer(successor)))
            self.observe_provisional_intent(intent_writer, stop)
            self.assert_absent(stop, reader)
            self.wait_for_operation(renew_writer, intent_writer, f.call('submit', renew, successor))
            # The provisional reply cannot authorize dispatch. The separately
            # authenticated reader resolves the exact record after literal COMMIT.
            intent_writer.finish()
            self.assert_waiter_refused(renew_writer, '42501', 'b2_stop_intent_pending')

        self.assertEqual(self.lifecycle_snapshot(), before)
        self.assertEqual(f.head(scope)['native_sequence'], '3')
        self.assertEqual(self.originals((plan['install'], plan['acquire'], plan['resume']), reader), originals)
        exact_intent = self.assert_committed_intent(stop, scope, reader)
        changed = copy.deepcopy(stop)
        changed['body']['expected_control_sha256'] = 'f' * 64
        self.refuse(control, self.record_query(changed), '42501', 'b2_stop_intent_conflict')
        self.refuse(control, f.call('submit', changed, control), '42501', 'b2_stop_intent_conflict')
        self.refuse(reader, self.get_query(changed), '42501', 'b2_stop_intent_conflict')
        # Alter only a trusted control binding wire. Reader authority and K2
        # survive, but this positive reconciliation must require exact binding.
        held_control = next(
            value for value in scope['manifest']['bindings']
            if value['principal_binding_id'] == scope['bindings']['control']
        )
        drifted_control = dict(held_control, issuance_id=str(UUID(int=994199)))
        def arrange_binding(value):
            self.db.sql(
                f"BEGIN; SET LOCAL ROLE {ANCHOR_OWNER}; UPDATE {A}.actor_bindings "
                f"SET binding_wire={literal(canonical(value))} "
                f"WHERE scope_wire={literal(canonical(stop['scope']))} "
                f"AND binding_id={literal(scope['bindings']['control'])}; COMMIT;"
            )
        arrange_binding(drifted_control)
        drifted_snapshot = self.lifecycle_snapshot()
        drifted_intent_rows = self.intent_rows(stop['scope'])
        self.refuse(reader, self.get_query(stop), '42501', 'b2_stop_intent_pin_refused')
        self.assertEqual(self.lifecycle_snapshot(), drifted_snapshot)
        self.assertEqual(self.intent_rows(stop['scope']), drifted_intent_rows)
        arrange_binding(held_control)
        self.assertEqual(self.assert_committed_intent(stop, scope, reader), exact_intent)

        self.assert_stop(stop, scope, reader, control, 4, accounting)
        recorded = self.db.sql(BEGIN + SETTINGS + self.record_query(stop) + 'COMMIT;\n', role=control)
        self.assertEqual(recorded.stdout, exact_intent + '\n')
        self.assertEqual(self.originals((plan['install'], plan['acquire'], plan['resume']), reader), originals)

    def test_actual_successor_renew_prevents_stale_intent_before_dispatch(self):
        plan, scope, reader, control, successor = self.ready()
        f = self.fixture
        stop, renew = plan['stop'], plan['renew']
        originals = self.originals((plan['install'], plan['acquire'], plan['resume']), reader)
        self.assert_absent(stop, reader)
        with ExitStack() as stack:
            renew_writer = stack.enter_context(closing(f.writer(successor)))
            intent_writer = stack.enter_context(closing(f.writer(control)))
            self.observe_provisional_operation(renew_writer, renew, successor)
            self.assertEqual(f.get(renew, reader)['resolution'], 'observed_absent_unknown')
            self.wait_for_operation(intent_writer, renew_writer, self.record_query(stop))
            renew_writer.finish()
            self.assert_waiter_refused(intent_writer, 'P0001', 'b2_stale_head')

        self.assert_absent(stop, reader)
        self.assertEqual(f.get(stop, reader)['resolution'], 'observed_absent_unknown')
        self.assertEqual(f.head(scope)['native_sequence'], '4')
        renew_reply = f.get(renew, reader)
        self.assertEqual(renew_reply['original_command_wire'], canonical(renew))
        self.assertEqual(json.loads(renew_reply['original_receipt_wire'])['original_command_sha256'],
                         sha(canonical(renew)))
        self.assertEqual(self.originals((plan['install'], plan['acquire'], plan['resume']), reader), originals)

        # The stale bytes were never dispatched. The first Stop dispatch keeps
        # the one allocated ID and uses the newly observed committed position.
        new_stop = f.command(scope, 'source_stop')
        new_stop['body'] = copy.deepcopy(stop['body'])
        self.assertEqual(new_stop['action_id'], stop['action_id'])
        self.assertEqual(new_stop['expected_head']['native_sequence'], '4')
        self.assertNotEqual(canonical(new_stop), canonical(stop))
        before = self.accounting(scope)
        with closing(f.writer(control)) as writer:
            # Deliberately discard the SQL response and the client's exit
            # status. Only the independent reader resolves what committed.
            writer.send(self.record_query(new_stop))
            writer.finish(check=False)
        self.assert_stop(new_stop, scope, reader, control, 5, before)
        self.assertEqual(self.originals((plan['install'], plan['acquire'], plan['resume']), reader), originals)
        self.assertEqual(f.get(renew, reader)['original_receipt_wire'], renew_reply['original_receipt_wire'])
