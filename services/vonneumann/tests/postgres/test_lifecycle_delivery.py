"""Real v4 lifecycle receipts and outbox recovery in the owned offline database."""
from __future__ import annotations

import unittest

from tests.lifecycle_fixtures import lifecycle_trace
from tests.postgres.harness import PostgresContractTestCase
from tests.postgres.test_command_adapter import FixtureRpcTransport, identity, literal
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandRepository, UncertainCommand
from vonneumann.db.transition_coordinator import TransitionCoordinator, PublicationError


class LifecycleDeliveryTests(PostgresContractTestCase, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.owner,self.run,self.worker = identity(),identity(),identity()
        self.db.sql(f'INSERT INTO auth.users(id) VALUES ({literal(self.owner)});')
        self.transport = FixtureRpcTransport(self.db)
        self.repository = CommandRepository(self.transport,self.owner,self.run,self.worker)
        self.delivered = []

    async def publish(self,event):
        self.assertIsNotNone(self.coordinator.installed_state)
        self.assertGreaterEqual(self.coordinator.installed_state.revision,event['revision'])
        self.delivered.append(event['event_id'])

    async def setup_trace(self,kind):
        config,candidates = lifecycle_trace(kind,strategy='cma_es',owner_id=self.owner,run_id=self.run)
        await self.repository.submit(PreparedCommand.create(self.owner,self.run,self.worker,
            config.run_configuration(),config.initial_cash,lease_seconds=120))
        self.coordinator = TransitionCoordinator(self.repository,self.transport)
        await self.coordinator.heartbeat(120)
        return candidates

    async def install(self,candidate):
        await self.coordinator.submit(candidate,command_id=identity())
        while self.coordinator.pending_candidate is not None:
            await self.coordinator.publish_pending(self.publish)

    def commit_calls(self):
        return [args for name,args in self.transport.calls if name == 'commit_command']

    def economic_snapshot(self):
        pairs = []
        for table in ('runs','accounts','positions','commands','account_lineage','lineage_sources','outbox_events'):
            column = 'id' if table == 'runs' else 'run_id'
            pairs.extend((literal(table),"(SELECT coalesce(jsonb_agg(digest ORDER BY digest),'[]'::jsonb) FROM "
                "(SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') digest "
                f'FROM vn_durability.{table} t WHERE {column}={literal(self.run)}) q)'))
        return self.db.scalar('SELECT jsonb_build_object('+','.join(pairs)+');')

    async def test_recovery_lost_reply_readback_after_lease_expiry_installs_only_original_candidate(self):
        candidates = await self.setup_trace('recover')
        target_index = next(i for i,c in enumerate(candidates)
            if c.transition['evidence']['control'] is not None and
               c.transition['evidence']['control']['action'] == 'recover')
        for candidate in candidates[:target_index]: await self.install(candidate)
        source,target,command_id = self.coordinator.installed_state,candidates[target_index],identity()
        self.transport.drop_reply_once = 'commit_command'
        with self.assertRaises(UncertainCommand):
            await self.coordinator.submit(target,command_id=command_id)
        self.assertIs(self.coordinator.installed_state,source)
        self.assertTrue(source.to_dict()['engine']['lifecycle']['risk']['active'])
        self.db.sql("UPDATE vn_durability.runs SET lease_until=clock_timestamp()-interval '1 second' "
                    f'WHERE id={literal(self.run)};')
        snapshot,calls = self.economic_snapshot(),self.commit_calls()
        receipt = await self.coordinator.reconcile()
        self.assertEqual(receipt.command.command_id,command_id)
        self.assertIs(self.coordinator.installed_state,target.state)
        self.assertEqual(self.commit_calls(),calls)
        self.assertEqual(self.economic_snapshot(),snapshot)
        self.assertFalse(self.coordinator.accepting)
        while self.coordinator.pending_candidate is not None:
            await self.coordinator.publish_pending(self.publish,max_events=1)
        self.assertEqual(self.economic_snapshot(),snapshot)
        self.assertFalse(self.coordinator.accepting)
        state = target.state.to_dict()
        self.assertFalse(state['engine']['lifecycle']['risk']['active'])
        self.assertTrue(state['engine']['lifecycle']['restart_required'])
        self.assertEqual(sum(not p['closed'] for p in state['positions']),8)
        self.assertEqual(len(self.delivered),len(set(self.delivered)))

    async def test_stop_retains_positions_and_lost_delivery_ack_never_repeats_stop_or_publication(self):
        candidates = await self.setup_trace('pause_stop')
        for candidate in candidates[:-1]: await self.install(candidate)
        source,target,command_id = self.coordinator.installed_state,candidates[-1],identity()
        await self.coordinator.submit(target,command_id=command_id)
        self.coordinator.close_admission()
        self.assertEqual(target.state.to_dict()['status'],'stopped')
        self.assertEqual(target.state.to_dict()['positions'],source.to_dict()['positions'])
        self.assertEqual(sum(not p['closed'] for p in target.state.to_dict()['positions']),8)
        self.transport.drop_reply_once = 'acknowledge_event'
        calls = self.commit_calls()
        snapshot = self.economic_snapshot()
        with self.assertRaises(PublicationError): await self.coordinator.publish_pending(self.publish)
        attempts = len(self.delivered)
        await self.coordinator.publish_pending(self.publish)
        self.assertEqual(len(self.delivered),attempts)
        self.assertEqual(self.commit_calls(),calls)
        self.assertEqual(self.economic_snapshot(),snapshot)
        self.assertFalse(self.coordinator.accepting)
        self.assertIsNone(self.coordinator.pending_candidate)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_durability.positions WHERE '
            f'run_id={literal(self.run)} AND NOT closed;'),'8')
