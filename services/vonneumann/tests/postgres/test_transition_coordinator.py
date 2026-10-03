"""Retained candidate installation and event delivery against isolated PostgreSQL.

No application settings, provider clients, real credentials or configured
database endpoints are read. The injected transport reaches only this test
class's owned local PostgreSQL fixture.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import unittest
from uuid import UUID
from unittest.mock import patch

from tests.postgres.harness import PostgresContractTestCase
from tests.postgres.test_command_adapter import FixtureRpcTransport, identity, literal
from tests.postgres.test_decimal_lineage_contract import document
from vonneumann.core.decision_inputs import DecisionInputs
from vonneumann.core.exact_rehearsal import ExactRehearsalConfig, bootstrap
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandAdmissionError, CommandBusy, CommandRepository, UncertainCommand
from vonneumann.db.transition_coordinator import PublicationError, TransitionCoordinator


class OutboxFixture:
    def setUp(self):
        self.owner, self.other_owner, self.run, self.worker = (identity() for _ in range(4))
        self.db.sql(f"INSERT INTO auth.users(id) VALUES ({literal(self.owner)}),({literal(self.other_owner)});")
        self.config = ExactRehearsalConfig('genetic_algorithm', self.owner, self.run)
        self.transport = FixtureRpcTransport(self.db)
        self.repository = CommandRepository(self.transport, self.owner, self.run, self.worker)

    def candidate(self):
        inputs = DecisionInputs(datetime.fromtimestamp(0, timezone.utc),
            datetime(2026, 10, 2, tzinfo=timezone.utc), 0.0,
            tuple(str(UUID(int=index)) for index in range(1000, 1032)),
            tuple((0, f'Outbox-{index}') for index in range(8)))
        return bootstrap(self.config, inputs)

    async def create(self):
        await self.repository.submit(PreparedCommand.create(self.owner, self.run, self.worker,
            self.config.run_configuration(), self.config.initial_cash, lease_seconds=120))
        await self.repository.heartbeat(120)

    def prepared(self, candidate, command_id=None):
        return PreparedCommand.batch(self.owner, self.run, self.worker, 1, 1,
            candidate.operations, command_id=command_id or identity(), version=3,
            transition=candidate.transition)

    async def commit_bootstrap(self):
        await self.create()
        candidate = self.candidate()
        command = self.prepared(candidate)
        await self.repository.submit(command)
        return candidate, command

    def read_args(self, *, through=2, count=50, size=65536):
        return {'owner_id': self.owner, 'run': self.run, 'through_revision': through,
                'max_events': count, 'max_bytes': size}

    async def read(self, **kwargs):
        return await self.transport.rpc('read_outbox', self.read_args(**kwargs))

    def ack_args(self, command, index):
        return {'owner_id': self.owner, 'run': self.run, 'command_id': command, 'event_index': index}

    async def ack(self, command, index):
        return await self.transport.rpc('acknowledge_event', self.ack_args(command, index))

    def read_sql(self, *, owner=None, run=None, through=2, count=50, size=65536):
        return 'SELECT vn_durability.read_outbox(' + ','.join(map(literal,
            (owner or self.owner, run or self.run, through, count, size))) + ');'

    def ack_sql(self, command, index, *, owner=None, run=None):
        return 'SELECT vn_durability.acknowledge_event(' + ','.join(map(literal,
            (owner or self.owner, run or self.run, command, index))) + ');'

    def raw_command(self, payload, command=None):
        return 'SELECT vn_durability.commit_command(' + ','.join((literal(self.owner),literal(self.run),
            literal(self.worker),'1','1',literal(command or identity()),document(payload))) + ');'

    def snapshot(self, tables=('runs', 'commands', 'accounts', 'positions', 'outbox_events', 'outbox_progress')):
        parts = []
        for table in tables:
            column = 'id' if table == 'runs' else 'run_id'
            parts.extend((literal(table), "(SELECT coalesce(jsonb_agg(digest ORDER BY digest),'[]'::jsonb) FROM "
                "(SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') digest "
                f"FROM vn_durability.{table} t WHERE {column}={literal(self.run)}) rows)"))
        return self.db.scalar('SELECT jsonb_build_object(' + ','.join(parts) + ');')

    def reject(self, sql, *, role='service_role', error=None):
        before = self.snapshot()
        result = self.db.sql(sql, role=role, check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        if error:
            self.assertIn(error, result.stderr)
        self.assertEqual(self.snapshot(), before)


class OutboxContractTests(OutboxFixture, PostgresContractTestCase, unittest.IsolatedAsyncioTestCase):
    async def test_events_commit_once_with_checkpoint_and_late_failure_rolls_back_every_row(self):
        await self.create()
        candidate = self.candidate()
        command = self.prepared(candidate)
        broken = deepcopy(command.expected_request['payload'])
        broken['transition']['after']['reserve'] = '201'
        self.reject(self.raw_command(broken), error='invalid_transition_projection')
        self.assertEqual((await self.read(through=1))['events'], [])
        await self.repository.submit(command)
        page = await self.read()
        self.assertEqual([row['event'] for row in page['events']], candidate.transition['events'])
        self.assertEqual([row['event_id'] for row in page['events']],
                         [f'{self.run}:{command.command_id}:{index}' for index in range(9)])
        before = self.snapshot()
        await self.transport.rpc(command.rpc_name, command.rpc_args)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(await self.read(), page)

    async def test_count_and_total_byte_bounded_pages_resume_after_each_contiguous_ack(self):
        candidate, command = await self.commit_bootstrap()
        self.assertEqual((await self.read(through=1))['events'], [], 'Uninstalled revisions must stay gated')
        count_page = await self.read(count=2)
        self.assertEqual(len(count_page['events']), 2)
        self.assertTrue(count_page['has_more'])
        one = await self.read(count=1)
        one['has_more'] = False  # SQL conservatively budgets the longer spelling.
        byte_limit = len(json.dumps(one, ensure_ascii=False, separators=(', ', ': ')).encode('utf-8'))
        self.assertGreaterEqual(byte_limit, 512)
        bounded = await self.read(count=100, size=byte_limit)
        self.assertEqual(len(bounded['events']), 1)
        raw = self.db.scalar(self.read_sql(count=100, size=byte_limit), role='service_role')
        self.assertLessEqual(len(raw.encode('utf-8')), byte_limit)
        self.reject(self.read_sql(size=byte_limit-1), error='outbox_event_exceeds_page')
        delivered = []
        while True:
            page = await self.read(count=2)
            if not page['events']:
                self.assertFalse(page['has_more'])
                break
            for record in page['events']:
                delivered.append(record)
                response = await self.ack(record['command_id'], record['event_index'])
                self.assertEqual(response, {'version': 1, 'owner_id': self.owner, 'run_id': self.run,
                    'command_id': command.command_id, 'event_id': record['event_id'],
                    'event_index': record['event_index'], 'revision': 2, 'acknowledged': True})
        self.assertEqual([row['event'] for row in delivered], candidate.transition['events'])
        self.assertEqual(len({row['event_id'] for row in delivered}), 9)
        before = self.snapshot()
        self.assertEqual((await self.ack(command.command_id, 0))['event_id'], f'{self.run}:{command.command_id}:0')
        self.assertEqual(self.snapshot(), before, 'An old ack cannot rewind delivery progress')

    async def test_concurrent_duplicate_and_lost_ack_are_idempotent_without_economic_lease(self):
        _, command = await self.commit_bootstrap()
        self.db.sql(f"UPDATE vn_durability.runs SET lease_until=clock_timestamp()-interval '1 second' WHERE id={literal(self.run)};")
        economic = self.snapshot(('runs', 'commands', 'accounts', 'positions', 'outbox_events'))
        self.reject(self.ack_sql(command.command_id, 1), error='outbox_acknowledgement_out_of_order')
        replies = await asyncio.gather(self.ack(command.command_id, 0), self.ack(command.command_id, 0))
        self.assertEqual(replies[0], replies[1])
        self.transport.drop_reply_once = 'acknowledge_event'
        with self.assertRaises(ConnectionError):
            await self.ack(command.command_id, 1)
        self.assertEqual((await self.read(count=1))['events'][0]['event_index'], 2)
        self.assertEqual((await self.ack(command.command_id, 1))['event_index'], 1)
        self.assertEqual(self.snapshot(('runs', 'commands', 'accounts', 'positions', 'outbox_events')), economic)

    async def test_foreign_identity_invalid_bounds_and_client_mutation_cannot_change_outbox(self):
        _, command = await self.commit_bootstrap()
        for sql in (self.read_sql(owner=self.other_owner), self.read_sql(run=identity()),
                    self.read_sql(through=3), self.ack_sql(command.command_id, 0, owner=self.other_owner),
                    self.ack_sql(command.command_id, 0, run=identity()), self.ack_sql(identity(), 0),
                    self.ack_sql(command.command_id, 1025), self.ack_sql(command.command_id, -1),
                    self.ack_sql(command.command_id, None)):
            with self.subTest(sql=sql):
                self.reject(sql)
        for kwargs in ({'count': 0}, {'count': 101}, {'count': None}, {'size': 511},
                       {'size': 65537}, {'size': None}, {'through': 0}, {'through': None}):
            with self.subTest(bounds=kwargs):
                self.reject(self.read_sql(**kwargs), error='invalid_outbox_request')
        for role in ('anon', 'authenticated', 'service_role'):
            for table in ('outbox_events', 'outbox_progress'):
                with self.subTest(role=role, table=table):
                    self.reject(f'DELETE FROM vn_durability.{table};', role=role, error='permission denied')
            if role != 'service_role':
                self.reject(self.read_sql(), role=role, error='permission denied')
                self.reject(self.ack_sql(command.command_id, 0), role=role, error='permission denied')
        for table, own_count in (('outbox_events', '9'), ('outbox_progress', '1')):
            query = f'SELECT count(*) FROM vn_durability.{table} WHERE run_id={literal(self.run)};'
            self.assertEqual(self.db.scalar(f'SET request.jwt.claim.sub={literal(self.owner)};' + query,
                                           role='authenticated'), own_count)
            self.assertEqual(self.db.scalar(f'SET request.jwt.claim.sub={literal(self.other_owner)};' + query,
                                           role='authenticated'), '0')

    async def test_two_runs_reusing_command_uuid_have_distinct_routable_event_identities(self):
        _, first = await self.commit_bootstrap()
        original_run = self.run
        original = await self.read()
        self.run = identity()
        self.config = ExactRehearsalConfig('genetic_algorithm', self.owner, self.run)
        self.repository = CommandRepository(self.transport, self.owner, self.run, self.worker)
        await self.create()
        await self.repository.submit(self.prepared(self.candidate(), command_id=first.command_id))
        second = await self.read()
        self.assertEqual([row['command_id'] for row in original['events']],
                         [row['command_id'] for row in second['events']])
        self.assertFalse({row['event_id'] for row in original['events']} &
                         {row['event_id'] for row in second['events']})
        self.assertEqual({row['run_id'] for row in original['events']}, {original_run})
        self.assertEqual({row['run_id'] for row in second['events']}, {self.run})
        self.assertEqual({row['owner_id'] for row in second['events']}, {self.owner})


class LateCommitReplyTransport(FixtureRpcTransport):
    """Expose a real commit while holding only its reply, never its transaction."""
    def __init__(self, database):
        super().__init__(database)
        self.committed = asyncio.Event()
        self.release = asyncio.Event()

    async def rpc(self, name, args):
        result = await super().rpc(name, args)
        if name == 'commit_command':
            self.committed.set()
            await self.release.wait()
        return result


class TransitionCoordinatorTests(OutboxFixture, PostgresContractTestCase, unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_caller_late_database_ack_installs_once_and_preserves_permanent_drain(self):
        self.transport = LateCommitReplyTransport(self.db)
        self.repository = CommandRepository(self.transport, self.owner, self.run, self.worker)
        await self.create()
        coordinator = TransitionCoordinator(self.repository, self.transport)
        candidate, command_id = self.candidate(), identity()
        caller = asyncio.create_task(coordinator.submit(candidate, command_id=command_id))
        await asyncio.wait_for(self.transport.committed.wait(), 5)
        self.assertEqual(self.db.scalar(f'SELECT count(*) FROM vn_durability.outbox_events WHERE run_id={literal(self.run)};'), '9')
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        coordinator.close_admission()
        self.assertIsNone(coordinator.installed_state)
        self.assertIs(coordinator.pending_candidate, candidate)
        self.assertTrue(coordinator.busy)
        with self.assertRaises(CommandBusy):
            await coordinator.heartbeat()
        self.transport.release.set()

        async def settled():
            while coordinator.busy:
                await asyncio.sleep(0.001)
        await asyncio.wait_for(settled(), 5)
        self.assertIs(coordinator.installed_state, candidate.state)
        self.assertEqual(coordinator.pending_receipt.command.command_id, command_id)
        self.assertFalse(coordinator.accepting)
        emitted = []

        async def publish(event):
            self.assertIs(coordinator.installed_state, candidate.state)
            emitted.append(event)
        self.assertEqual(await coordinator.publish_pending(publish), 9)
        self.assertEqual(len({row['event_id'] for row in emitted}), 9)
        self.assertIsNone(coordinator.pending_candidate)
        self.assertFalse(coordinator.accepting)
        self.assertEqual([name for name, _ in self.transport.calls].count('commit_command'), 1)
        with self.assertRaises(CommandAdmissionError):
            await coordinator.heartbeat()

    async def test_install_failure_retains_committed_candidate_and_receipt_without_resubmission(self):
        await self.create()
        coordinator = TransitionCoordinator(self.repository, self.transport)
        candidate, command_id = self.candidate(), identity()
        with patch.object(coordinator, '_install', side_effect=RuntimeError('fixture install failure')):
            with self.assertRaises(RuntimeError):
                await coordinator.submit(candidate, command_id=command_id)
        self.assertIsNone(coordinator.installed_state)
        self.assertIs(coordinator.pending_candidate, candidate)
        self.assertEqual(coordinator.pending_receipt.command.command_id, command_id)
        self.assertFalse(coordinator.accepting)
        writes = [item for item in self.transport.calls if item[0] == 'commit_command']
        self.assertEqual(len(writes), 1)
        published = []

        async def publish(event):
            published.append(event)
        with self.assertRaises(CommandAdmissionError):
            await coordinator.publish_pending(publish)
        self.assertEqual(published, [])
        coordinator.close_admission()
        retained = coordinator.pending_receipt
        self.assertIs(await coordinator.reconcile(), retained)
        self.assertIs(coordinator.installed_state, candidate.state)
        await coordinator.publish_pending(publish)
        self.assertEqual(len(published), 9)
        self.assertEqual([item for item in self.transport.calls if item[0] == 'commit_command'], writes)
        self.assertFalse(coordinator.accepting)

    async def test_partial_delivery_and_lost_ack_retry_only_the_original_stable_event(self):
        await self.create()
        coordinator = TransitionCoordinator(self.repository, self.transport)
        candidate, command_id = self.candidate(), identity()
        await coordinator.submit(candidate, command_id=command_id)
        accepted, attempts = set(), []
        fail_index = 2

        async def publish(event):
            nonlocal fail_index
            self.assertIs(coordinator.installed_state, candidate.state)
            attempts.append(event['event_id'])
            accepted.add(event['event_id'])  # The relay deduplicates effects.
            if event['event_index'] == fail_index:
                fail_index = None
                raise ConnectionError('Fixture relay accepted but its reply was lost')
        self.transport.drop_reply_once = 'acknowledge_event'
        with self.assertRaises(PublicationError):
            await coordinator.publish_pending(publish, max_events=4)
        self.assertEqual(coordinator.next_event_index, 0)
        self.assertEqual(attempts, [f'{self.run}:{command_id}:0'])
        self.assertEqual((await self.read(count=1))['events'][0]['event_index'], 1)
        with self.assertRaises(PublicationError):
            await coordinator.publish_pending(publish, max_events=4)
        self.assertEqual(coordinator.next_event_index, 2)
        self.assertEqual(attempts.count(f'{self.run}:{command_id}:0'), 1,
                         'An uncertain database ack retries only the ack, not relay delivery')
        coordinator.close_admission()
        while coordinator.pending_candidate is not None:
            await coordinator.publish_pending(publish, max_events=2)
        self.assertEqual(len(accepted), 9)
        self.assertEqual(attempts.count(f'{self.run}:{command_id}:2'), 2)
        self.assertEqual(len(attempts), 10, 'At-least-once delivery needs an idempotent relay')
        self.assertEqual((await self.read())['events'], [])
        self.assertEqual([name for name, _ in self.transport.calls].count('commit_command'), 1)
        self.assertFalse(coordinator.accepting)

    async def test_real_cma_replacement_lost_reply_resolves_original_candidate_after_lease_loss(self):
        from tests import test_exact_rehearsal as fixtures
        with patch.object(fixtures, 'OWNER', self.owner), patch.object(fixtures, 'RUN', self.run):
            config, _, candidates, _ = fixtures.roundtrip_windows('cma_es', collect_all=True)
        self.config = config
        await self.create()
        coordinator = TransitionCoordinator(self.repository, self.transport)
        target_index = next(index for index, candidate in enumerate(candidates)
                            if candidate.state.to_dict()['engine']['generation'] == 1)
        emitted = set()

        async def publish(event):
            self.assertIsNotNone(coordinator.installed_state)
            self.assertGreaterEqual(coordinator.installed_state.revision, event['revision'])
            emitted.add(event['event_id'])
        for candidate in candidates[:target_index]:
            await coordinator.submit(candidate, command_id=identity())
            while coordinator.pending_candidate is not None:
                await coordinator.publish_pending(publish)
        source = coordinator.installed_state
        target, command_id = candidates[target_index], identity()
        before_bytes = source.to_dict()
        self.transport.drop_reply_once = 'commit_command'
        with self.assertRaises(UncertainCommand):
            await coordinator.submit(target, command_id=command_id)
        self.assertIs(coordinator.installed_state, source)
        self.assertEqual(source.to_dict(), before_bytes)
        self.assertIs(coordinator.pending_candidate, target)
        self.assertIsNone(coordinator.pending_receipt)
        self.assertFalse(coordinator.accepting)
        self.db.sql(f"UPDATE vn_durability.runs SET lease_until=clock_timestamp()-interval '1 second' WHERE id={literal(self.run)};")
        committed = self.snapshot()
        commands = [args for name, args in self.transport.calls if name == 'commit_command']
        retained = coordinator.pending_command
        receipt = await coordinator.reconcile()
        self.assertIs(receipt.command, retained)
        self.assertEqual(receipt.command.command_id, command_id)
        self.assertIs(coordinator.installed_state, target.state)
        self.assertEqual(coordinator.installed_state.to_dict()['engine']['generation'], 1)
        self.assertEqual(self.snapshot(), committed)
        self.assertFalse(self.repository.lease_valid)
        self.assertEqual([args for name, args in self.transport.calls if name == 'commit_command'], commands)
        self.assertEqual(self.transport.calls[-1][0], 'get_command')
        while coordinator.pending_candidate is not None:
            await coordinator.publish_pending(publish, max_events=3)
        event_rows = int(self.db.scalar(f'SELECT count(*) FROM vn_durability.outbox_events WHERE run_id={literal(self.run)};'))
        self.assertEqual(len(emitted), event_rows)
        self.assertFalse(coordinator.accepting, 'Readback and delivery cannot renew the economic lease')
