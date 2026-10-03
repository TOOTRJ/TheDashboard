"""Independent ownership, installation and durable-outbox race acceptance.

The fake server commits before returning a reply, allowing deterministic lost
ACKs without assuming that transport failure means rollback. Real bounded
engine candidates, including all four solver replacements, cross the boundary.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from contextlib import ExitStack
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import deny_network
from tests.test_exact_rehearsal import ALGORITHMS, OWNER, RUN, WORKER, advance, initial, inputs
from vonneumann.core.exact_rehearsal import ExactRehearsalConfig, bootstrap
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import (
    CommandAdmissionError, CommandBusy, CommandRepository, UncertainCommand,
)
from vonneumann.db.transition_coordinator import TransitionCoordinator


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class Gate:
    """Pause after the fake server has committed, before delivering its reply."""
    def __init__(self, error=None):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.error = error
        self.cancelled = False

    async def __call__(self, result, _arguments):
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self.error is not None:
            raise self.error
        return deepcopy(result)


class CommittingTransport:
    """Small ledger/outbox fake with explicit per-RPC reply fault injection."""
    def __init__(self):
        self.calls = []
        self.effects = defaultdict(deque)
        self.revision = 0
        self.status = None
        self.ledger = {}
        self.events = []
        self.acknowledged = set()

    def fault(self, name, effect):
        self.effects[name].append(effect)

    def count(self, name):
        return sum(call[0] == name for call in self.calls)

    async def rpc(self, name, arguments):
        args = deepcopy(arguments)
        self.calls.append((name, args))
        if name == 'create_run':
            self.revision, self.status = 1, 'starting'
            result = dict(run_id=args['run'], revision=1, fence=1, status='starting')
        elif name == 'heartbeat':
            result = dict(run_id=args['run'], revision=self.revision, fence=1)
        elif name == 'commit_command':
            key = args['command_id']
            if key in self.ledger:
                result = deepcopy(self.ledger[key]['response'])
            else:
                if args['expected_revision'] != self.revision:
                    raise AssertionError('Fake server rejects a stale economic command')
                self.revision += 1
                after = args['payload']['transition']['after']
                self.status = after['status']
                result = dict(run_id=args['run'], revision=self.revision, fence=1,
                              status=self.status, reserve=after['reserve'])
                self.ledger[key] = dict(request={
                    'kind': 'batch', 'owner_id': args['owner_id'], 'run_id': args['run'],
                    'worker': args['worker'], 'command_id': key, 'fence': args['token'],
                    'expected_revision': args['expected_revision'], 'payload': args['payload'],
                }, response=deepcopy(result), request_hash='ab' * 32)
                for index, event in enumerate(args['payload']['transition']['events']):
                    self.events.append(dict(event_id=f"{args['run']}:{key}:{index}",
                        owner_id=args['owner_id'], run_id=args['run'], command_id=key,
                        revision=self.revision, event_index=index, event=deepcopy(event)))
        elif name == 'get_command':
            result = deepcopy(self.ledger.get(args['command_id']))
        elif name == 'read_outbox':
            remaining = [row for row in self.events if row['revision'] <= args['through_revision']
                         and row['event_id'] not in self.acknowledged]
            page = []
            for row in remaining[:args['max_events']]:
                trial = page + [row]
                # Match the SQL JSONB textual spacing when enforcing page bytes.
                body = dict(version=1, owner_id=args['owner_id'], run_id=args['run'],
                    through_revision=args['through_revision'], events=trial,
                    has_more=len(trial) < len(remaining))
                size = len(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                      separators=(', ', ': ')).encode())
                if size > args['max_bytes']:
                    break
                page = trial
            result = dict(version=1, owner_id=args['owner_id'], run_id=args['run'],
                through_revision=args['through_revision'], events=deepcopy(page),
                has_more=len(page) < len(remaining))
        elif name == 'acknowledge_event':
            event_id = f"{args['run']}:{args['command_id']}:{args['event_index']}"
            row = next(row for row in self.events if row['event_id'] == event_id)
            unread = next((item for item in self.events
                           if item['event_id'] not in self.acknowledged), None)
            if event_id not in self.acknowledged and unread['event_id'] != event_id:
                raise AssertionError('Fake outbox rejects skipped delivery acknowledgments')
            self.acknowledged.add(event_id)
            result = dict(version=1, owner_id=args['owner_id'], run_id=args['run'],
                command_id=args['command_id'], event_id=event_id,
                event_index=args['event_index'], revision=row['revision'], acknowledged=True)
        else:
            raise AssertionError(f'Unexpected RPC {name}')
        if self.effects[name]:
            effect = self.effects[name].popleft()
            if isinstance(effect, BaseException):
                raise effect
            if callable(effect):
                return await effect(deepcopy(result), args)
            return deepcopy(effect)
        return deepcopy(result)


class TransitionCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        guard = deny_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)
        self.clock = Clock()
        self.transport = CommittingTransport()
        self.repo = CommandRepository(self.transport, OWNER, RUN, WORKER, monotonic=self.clock)
        self.coordinator = None
        self.tasks, self.gates = [], []
        self.identities = 8000000

    async def asyncTearDown(self):
        for gate in self.gates:
            gate.release.set()
        if self.tasks:
            await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), 2)
        await self.settled()

    def identity(self):
        self.identities += 1
        return str(UUID(int=self.identities))

    def spawn(self, awaitable):
        task = asyncio.create_task(awaitable)
        self.tasks.append(task)
        return task

    def gate(self, rpc, *, error=None):
        gate = Gate(error)
        self.gates.append(gate)
        self.transport.fault(rpc, gate)
        return gate

    async def entered(self, gate):
        await asyncio.wait_for(gate.entered.wait(), 2)

    async def settled(self):
        for _ in range(100):
            if not self.repo.busy and (self.coordinator is None or not self.coordinator.busy):
                return
            await asyncio.sleep(0)
        self.fail('Owned fake operation did not settle')

    async def ready(self, algorithm='genetic_algorithm'):
        config, candidate = initial(algorithm)
        command = PreparedCommand.create(OWNER, RUN, WORKER, config.run_configuration(),
                                         config.initial_cash, command_id=self.identity())
        await self.repo.submit(command)
        self.coordinator = TransitionCoordinator(self.repo, self.transport)
        await self.coordinator.heartbeat()
        return candidate

    async def sink(self, event):
        return None

    async def install_bootstrap(self):
        candidate = await self.ready()
        await self.coordinator.submit(candidate, command_id=self.identity())
        await self.coordinator.publish_pending(self.sink)
        return candidate

    async def test_constructor_requires_exact_acknowledged_version_three_creation(self):
        with self.assertRaises((ValueError, RuntimeError)):
            TransitionCoordinator(self.repo, self.transport)
        config, _ = initial()
        command = PreparedCommand.create(OWNER, RUN, WORKER,
            {'durability_contract_version': 1}, config.initial_cash)
        await self.repo.submit(command)
        with self.assertRaises((ValueError, RuntimeError)):
            TransitionCoordinator(self.repo, self.transport)

    async def test_submission_retains_before_first_await_and_installs_only_after_ack(self):
        candidate = await self.ready()
        identity = self.identity()
        gate = self.gate('commit_command')
        task = self.spawn(self.coordinator.submit(candidate, command_id=identity))
        await self.entered(gate)
        self.assertIsNone(self.coordinator.installed_state)
        self.assertIs(self.coordinator.pending_candidate, candidate)
        self.assertEqual(self.coordinator.pending_command.command_id, identity)
        self.assertFalse(self.coordinator.accepting)
        self.assertEqual(self.transport.count('read_outbox'), 0)
        gate.release.set()
        receipt = await task
        self.assertEqual(receipt.command.command_id, identity)
        self.assertIs(self.coordinator.installed_state, candidate.state)
        self.assertFalse(self.coordinator.accepting)  # durable outbox still pending
        self.assertEqual(self.transport.count('commit_command'), 1)

    async def test_caller_cancel_then_late_ack_installs_once_without_resubmission(self):
        candidate = await self.ready()
        gate = self.gate('commit_command')
        with patch.object(self.coordinator, '_install', wraps=self.coordinator._install) as install:
            task = self.spawn(self.coordinator.submit(candidate, command_id=self.identity()))
            await self.entered(gate)
            retained = self.coordinator.pending_command
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertFalse(gate.cancelled)
            self.assertIsNone(self.coordinator.installed_state)
            gate.release.set()
            await self.settled()
            self.assertIs(self.coordinator.installed_state, candidate.state)
            self.assertEqual(install.call_count, 1)
            await self.coordinator.reconcile()
            self.assertEqual(install.call_count, 1)
            self.assertIs(self.coordinator.pending_command, retained)
            self.assertEqual(self.transport.count('get_command'), 0)
            self.assertEqual(self.transport.count('commit_command'), 1)

    async def test_owner_task_shutdown_recovers_late_repository_receipt(self):
        candidate = await self.ready()
        gate = self.gate('commit_command')
        task = self.spawn(self.coordinator.submit(candidate, command_id=self.identity()))
        await self.entered(gate)
        owned = self.coordinator._task
        self.assertIsNotNone(owned)
        owned.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(gate.cancelled)
        gate.release.set()
        await self.settled()
        self.assertIsNone(self.repo.pending)
        self.assertIsNone(self.coordinator.installed_state)
        receipt = await self.coordinator.reconcile()
        self.assertEqual(receipt.command.command_id, self.repo.last_receipt.command.command_id)
        self.assertIs(self.coordinator.installed_state, candidate.state)
        self.assertEqual(self.transport.count('get_command'), 0)
        self.assertEqual(self.transport.count('commit_command'), 1)

    async def test_lost_reply_missing_readback_retains_original_until_exact_resolution(self):
        candidate = await self.ready()
        self.transport.fault('commit_command', OSError('reply lost after commit'))
        with self.assertRaises(UncertainCommand):
            await self.coordinator.submit(candidate, command_id=self.identity())
        command = self.coordinator.pending_command
        self.transport.fault('get_command', None)
        self.assertIsNone(await self.coordinator.reconcile())
        self.assertIs(self.coordinator.pending_command, command)
        self.assertIs(self.coordinator.pending_candidate, candidate)
        self.assertIsNone(self.coordinator.installed_state)
        self.assertFalse(self.coordinator.accepting)
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.submit(candidate, command_id=self.identity())
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.heartbeat()
        receipt = await self.coordinator.reconcile()
        self.assertEqual(receipt.command.request, command.request)
        self.assertIs(self.coordinator.installed_state, candidate.state)
        self.assertEqual(self.transport.count('commit_command'), 1)
        self.assertEqual({args['command_id'] for name, args in self.transport.calls
                          if name == 'get_command'}, {command.command_id})
        self.assertFalse(self.repo.lease_valid)  # journal reads are not lease renewals

    async def test_invalid_readback_does_not_install_or_publish(self):
        candidate = await self.ready()
        self.transport.fault('commit_command', OSError('lost ACK'))
        with self.assertRaises(UncertainCommand):
            await self.coordinator.submit(candidate, command_id=self.identity())
        command = self.coordinator.pending_command
        for field, value in [('command_id', self.identity()), ('expected_revision', True)]:
            bad = deepcopy(self.transport.ledger[command.command_id])
            bad['request'][field] = value
            self.transport.fault('get_command', bad)
            with self.assertRaises(UncertainCommand):
                await self.coordinator.reconcile()
            self.assertIsNone(self.coordinator.installed_state)
            self.assertIs(self.coordinator.pending_command, command)
        bad = deepcopy(self.transport.ledger[command.command_id])
        bad['response']['reserve'] = '201'
        self.transport.fault('get_command', bad)
        with self.assertRaises(UncertainCommand):
            await self.coordinator.reconcile()
        self.assertEqual(self.transport.count('read_outbox'), 0)
        await self.coordinator.reconcile()
        self.assertIs(self.coordinator.installed_state, candidate.state)

    async def test_wrong_exact_reserve_retains_uncertainty_but_trailing_zero_ack_is_valid(self):
        candidate = await self.ready()

        async def wrong(result, _args):
            result['reserve'] = '200.000000000000000000000000000000000001'
            return result

        self.transport.fault('commit_command', wrong)
        with self.assertRaises(UncertainCommand):
            await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertEqual(self.repo.revision, 1)
        self.assertIsNone(self.coordinator.installed_state)
        original = self.coordinator.pending_command
        self.transport.ledger[original.command_id]['response']['reserve'] = '200.0000'
        await self.coordinator.reconcile()
        self.assertIs(self.coordinator.installed_state, candidate.state)

    async def test_failed_install_retains_acknowledged_candidate_and_retry_uses_no_rpc(self):
        candidate = await self.ready()
        with patch.object(self.coordinator, '_install', side_effect=RuntimeError('install failed')):
            with self.assertRaises(RuntimeError):
                await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertEqual(self.repo.revision, 2)
        self.assertIsNone(self.coordinator.installed_state)
        self.assertIs(self.coordinator.pending_candidate, candidate)
        self.assertIsNotNone(self.coordinator.pending_receipt)
        self.assertFalse(self.coordinator.accepting)
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.heartbeat()
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.publish_pending(self.sink)
        calls = len(self.transport.calls)
        await self.coordinator.reconcile()
        self.assertEqual(len(self.transport.calls), calls)
        self.assertIs(self.coordinator.installed_state, candidate.state)

    async def test_pending_publication_is_ordered_bounded_and_detached(self):
        candidate = await self.ready()
        identity = self.identity()
        await self.coordinator.submit(candidate, command_id=identity)
        delivered = []

        async def publish(row):
            self.assertIs(self.coordinator.installed_state, candidate.state)
            delivered.append(deepcopy(row))
            row['event']['kind'] = 'external mutation'
            row['event_id'] = 'external mutation'

        self.assertEqual(await self.coordinator.publish_pending(publish, max_events=2), 2)
        self.assertEqual([row['event_id'] for row in delivered], [f'{RUN}:{identity}:0', f'{RUN}:{identity}:1'])
        self.assertEqual(self.coordinator.next_event_index, 2)
        self.assertFalse(self.coordinator.accepting)
        self.assertEqual(await self.coordinator.publish_pending(publish, max_events=50), 7)
        self.assertEqual([row['event'] for row in delivered], candidate.transition['events'])
        self.assertEqual([row['event_index'] for row in delivered], list(range(9)))
        self.assertEqual(len(self.transport.acknowledged), 9)
        self.assertTrue(self.coordinator.accepting)
        self.assertIsNone(self.coordinator.pending_candidate)
        self.assertEqual(await self.coordinator.publish_pending(publish), 0)

    async def test_partial_callback_failure_redelivers_only_same_unacknowledged_identity(self):
        candidate = await self.ready()
        identity = self.identity()
        await self.coordinator.submit(candidate, command_id=identity)
        attempts, observed = [], set()

        async def fails_after_external_effect(row):
            attempts.append(row['event_id'])
            observed.add(row['event_id'])  # an idempotent external sink
            if row['event_index'] == 1:
                raise OSError('external effect happened; reply disappeared')

        with self.assertRaises((RuntimeError, OSError)):
            await self.coordinator.publish_pending(fails_after_external_effect)
        self.assertEqual(self.coordinator.next_event_index, 1)
        self.assertEqual(self.transport.acknowledged, {f'{RUN}:{identity}:0'})

        async def succeeds(row):
            attempts.append(row['event_id'])
            observed.add(row['event_id'])

        self.assertEqual(await self.coordinator.publish_pending(succeeds), 8)
        self.assertEqual(attempts[:3], [f'{RUN}:{identity}:0', f'{RUN}:{identity}:1', f'{RUN}:{identity}:1'])
        self.assertEqual(len(observed), 9)
        self.assertEqual(self.transport.count('commit_command'), 1)

    async def test_successful_callback_lost_durable_ack_retries_ack_without_republishing(self):
        candidate = await self.ready()
        identity = self.identity()
        await self.coordinator.submit(candidate, command_id=identity)
        self.transport.fault('acknowledge_event', OSError('ack reply lost'))
        delivered = []

        async def publish(row):
            delivered.append(row['event_id'])

        with self.assertRaises((RuntimeError, OSError)):
            await self.coordinator.publish_pending(publish)
        self.assertEqual(delivered, [f'{RUN}:{identity}:0'])
        self.assertEqual(self.transport.acknowledged, {f'{RUN}:{identity}:0'})
        self.assertEqual(await self.coordinator.publish_pending(publish, max_events=2), 2)
        self.assertEqual(delivered, [f'{RUN}:{identity}:0', f'{RUN}:{identity}:1'])
        acknowledgments = [args for name, args in self.transport.calls if name == 'acknowledge_event']
        self.assertEqual([args['event_index'] for args in acknowledgments], [0, 0, 1])
        self.assertEqual(self.coordinator.next_event_index, 2)

    async def test_cancelled_publication_caller_does_not_duplicate_inflight_delivery(self):
        candidate = await self.ready()
        identity = self.identity()
        await self.coordinator.submit(candidate, command_id=identity)
        gate = Gate()
        self.gates.append(gate)
        delivered = []

        async def publish(row):
            delivered.append(row['event_id'])
            await gate(None, {})

        task = self.spawn(self.coordinator.publish_pending(publish, max_events=1))
        await self.entered(gate)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        with self.assertRaises(CommandBusy):
            await self.coordinator.publish_pending(self.sink)
        gate.release.set()
        await self.settled()
        self.assertFalse(gate.cancelled)
        self.assertEqual(delivered, [f'{RUN}:{identity}:0'])
        self.assertEqual(self.coordinator.next_event_index, 1)
        self.assertEqual(self.transport.acknowledged, {f'{RUN}:{identity}:0'})

    async def test_invalid_pages_are_rejected_before_any_callback_or_ack(self):
        candidate = await self.ready()
        identity = self.identity()
        await self.coordinator.submit(candidate, command_id=identity)
        calls = []

        async def publish(row):
            calls.append(row)

        def mutations(page):
            altered = deepcopy(page)
            altered['events'][0]['event_id'] = f'{RUN}:{identity}:1'
            yield altered
            altered = deepcopy(page)
            altered['events'][0]['event']['kind'] = 'retire'
            yield altered
            altered = deepcopy(page)
            altered['events'][0]['revision'] = 3
            yield altered
            altered = deepcopy(page)
            altered['events'].reverse()
            yield altered
            altered = deepcopy(page)
            altered['events'] = []
            altered['has_more'] = False
            yield altered
            altered = deepcopy(page)
            altered['has_more'] = 1
            yield altered
            altered = deepcopy(page)
            altered['events'][0]['event_index'] = False
            yield altered

        page = dict(version=1, owner_id=OWNER, run_id=RUN, through_revision=2,
                    events=deepcopy(self.transport.events), has_more=False)
        for bad in mutations(page):
            self.transport.fault('read_outbox', bad)
            with self.assertRaises((ValueError, RuntimeError)):
                await self.coordinator.publish_pending(publish)
            self.assertEqual(calls, [])
            self.assertEqual(self.transport.count('acknowledge_event'), 0)
            self.assertEqual(self.coordinator.next_event_index, 0)

    async def test_invalid_ack_keeps_delivered_event_for_same_id_ack_retry(self):
        candidate = await self.ready()
        identity = self.identity()
        await self.coordinator.submit(candidate, command_id=identity)

        async def wrong(result, _args):
            result['event_index'] = True
            return result

        self.transport.fault('acknowledge_event', wrong)
        delivered = []

        async def publish(row):
            delivered.append(row['event_id'])

        with self.assertRaises((ValueError, RuntimeError)):
            await self.coordinator.publish_pending(publish)
        await self.coordinator.publish_pending(publish, max_events=1)
        self.assertEqual(delivered, [f'{RUN}:{identity}:0'])
        self.assertEqual(self.coordinator.next_event_index, 1)

    async def test_drain_during_submit_does_not_prevent_install_but_never_reopens(self):
        candidate = await self.ready()
        gate = self.gate('commit_command')
        task = self.spawn(self.coordinator.submit(candidate, command_id=self.identity()))
        await self.entered(gate)
        self.coordinator.close_admission()
        gate.release.set()
        await task
        self.assertIs(self.coordinator.installed_state, candidate.state)
        self.assertFalse(self.coordinator.accepting)
        await self.coordinator.publish_pending(self.sink)
        self.assertFalse(self.coordinator.accepting)
        self.assertFalse(self.repo.lease_valid)
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.heartbeat()

    async def test_drain_during_resolution_and_publication_remains_permanent(self):
        candidate = await self.ready()
        self.transport.fault('commit_command', OSError('lost'))
        with self.assertRaises(UncertainCommand):
            await self.coordinator.submit(candidate, command_id=self.identity())
        gate = self.gate('get_command')
        task = self.spawn(self.coordinator.reconcile())
        await self.entered(gate)
        self.coordinator.close_admission()
        gate.release.set()
        await task
        delivery = Gate()
        self.gates.append(delivery)

        async def publish(row):
            await delivery(None, row)

        task = self.spawn(self.coordinator.publish_pending(publish))
        await self.entered(delivery)
        self.coordinator.close_admission()
        delivery.release.set()
        await task
        self.assertFalse(self.coordinator.accepting)
        self.assertIs(self.coordinator.installed_state, candidate.state)

    async def test_late_heartbeat_after_drain_cannot_reopen_admission(self):
        await self.install_bootstrap()
        gate = self.gate('heartbeat')
        task = self.spawn(self.coordinator.heartbeat())
        await self.entered(gate)
        self.coordinator.close_admission()
        gate.release.set()
        await task
        self.assertFalse(self.repo.lease_valid)
        self.assertFalse(self.coordinator.accepting)

    async def test_installed_outbox_backlog_can_renew_lease_without_admitting_economics(self):
        candidate = await self.ready()
        await self.coordinator.submit(candidate, command_id=self.identity())
        self.clock.value += 30
        self.assertFalse(self.repo.lease_valid)
        await self.coordinator.heartbeat()
        self.assertTrue(self.repo.lease_valid)
        self.assertFalse(self.coordinator.accepting)
        self.assertIs(self.coordinator.pending_candidate, candidate)
        self.assertEqual(self.transport.count('commit_command'), 1)
        await self.coordinator.publish_pending(self.sink)
        self.assertTrue(self.coordinator.accepting)

    async def test_busy_operations_fail_without_queueing_or_starting_another_rpc(self):
        candidate = await self.ready()
        gate = self.gate('commit_command')
        task = self.spawn(self.coordinator.submit(candidate, command_id=self.identity()))
        await self.entered(gate)
        calls = len(self.transport.calls)
        for operation in (lambda: self.coordinator.heartbeat(), self.coordinator.reconcile,
                          lambda: self.coordinator.publish_pending(self.sink),
                          lambda: self.coordinator.submit(candidate, command_id=self.identity())):
            with self.assertRaises(CommandBusy):
                await operation()
        self.assertEqual(len(self.transport.calls), calls)
        gate.release.set()
        await task

    async def test_heartbeat_race_blocks_submit_and_expired_lease_stops_new_candidate(self):
        candidate = await self.ready()
        gate = self.gate('heartbeat')
        task = self.spawn(self.coordinator.heartbeat())
        await self.entered(gate)
        with self.assertRaises(CommandBusy):
            await self.coordinator.submit(candidate, command_id=self.identity())
        gate.release.set()
        await task
        self.clock.value += 30
        self.assertFalse(self.coordinator.accepting)
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertIsNone(self.coordinator.pending_candidate)
        self.assertEqual(self.transport.count('commit_command'), 0)

    async def test_bootstrap_configuration_mismatch_fails_before_post(self):
        await self.ready('genetic_algorithm')
        _, wrong = initial('particle_swarm')
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.submit(wrong, command_id=self.identity())
        self.assertIsNone(self.coordinator.pending_candidate)
        self.assertEqual(self.transport.count('commit_command'), 0)

    async def test_candidate_must_extend_full_installed_state_and_empty_event_transition_clears(self):
        boot = await self.install_bootstrap()
        protective, decision = advance(boot.state, 900, end=900, close='100')
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.submit(decision, command_id=self.identity())
        calls = self.transport.count('read_outbox')
        await self.coordinator.submit(protective, command_id=self.identity())
        self.assertIs(self.coordinator.installed_state, protective.state)
        self.assertIsNone(self.coordinator.pending_candidate)
        self.assertTrue(self.coordinator.accepting)
        self.assertEqual(self.transport.count('read_outbox'), calls)
        await self.coordinator.submit(decision, command_id=self.identity())
        self.assertIs(self.coordinator.installed_state, decision.state)

    async def test_matching_revision_with_different_prior_state_is_not_admitted(self):
        boot = await self.install_bootstrap()
        protected, _ = advance(boot.state, 900, price='100', end=900, close='100')
        other, wrong_decision = advance(boot.state, 900, price='101', end=900, close='100')
        self.assertEqual(protected.state.revision, other.state.revision)
        await self.coordinator.submit(protected, command_id=self.identity())
        calls = self.transport.count('commit_command')
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.submit(wrong_decision, command_id=self.identity())
        self.assertIs(self.coordinator.installed_state, protected.state)
        self.assertIsNone(self.coordinator.pending_candidate)
        self.assertEqual(self.transport.count('commit_command'), calls)

    async def test_two_runs_reusing_command_id_cannot_collide_in_shared_idempotent_sink(self):
        identity = self.identity()
        delivered = {}

        async def shared_sink(row):
            delivered.setdefault(row['event_id'], deepcopy(row))

        for run in (RUN, str(UUID(int=777))):
            config = ExactRehearsalConfig('genetic_algorithm', OWNER, run)
            candidate = bootstrap(config, inputs(0))
            transport = CommittingTransport()
            repository = CommandRepository(transport, OWNER, run, WORKER, monotonic=self.clock)
            await repository.submit(PreparedCommand.create(OWNER, run, WORKER,
                config.run_configuration(), config.initial_cash, command_id=self.identity()))
            coordinator = TransitionCoordinator(repository, transport)
            await coordinator.heartbeat()
            await coordinator.submit(candidate, command_id=identity)
            await coordinator.publish_pending(shared_sink)
        self.assertEqual(len(delivered), 18)
        self.assertEqual({row['run_id'] for row in delivered.values()}, {RUN, str(UUID(int=777))})
        self.assertEqual({row['command_id'] for row in delivered.values()}, {identity})
        self.assertTrue(all(row['event_id'] == f"{row['run_id']}:{identity}:{row['event_index']}"
                            for row in delivered.values()))

    async def test_eager_task_factory_preserves_exclusive_ownership(self):
        candidate = await self.ready()
        loop = asyncio.get_running_loop()
        original_factory = loop.get_task_factory()
        try:
            loop.set_task_factory(asyncio.eager_task_factory)
            receipt = await self.coordinator.submit(candidate, command_id=self.identity())
            self.assertEqual(receipt.revision, 2)
            self.assertIs(self.coordinator.installed_state, candidate.state)
            self.assertFalse(self.coordinator.busy)
            self.assertEqual(await self.coordinator.publish_pending(self.sink), 9)
            self.assertFalse(self.coordinator.busy)
        finally:
            loop.set_task_factory(original_factory)

    async def test_outer_scheduling_failure_proves_no_rpc_and_releases_unsubmitted_candidate(self):
        candidate = await self.ready()
        with patch('vonneumann.db.transition_coordinator.asyncio.create_task',
                   side_effect=RuntimeError('cannot schedule')):
            with self.assertRaises(CommandAdmissionError):
                await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertFalse(self.coordinator.busy)
        self.assertIsNone(self.coordinator.installed_state)
        self.assertIsNone(self.coordinator.pending_candidate)
        self.assertIsNone(self.repo.pending)
        self.assertEqual(self.transport.count('commit_command'), 0)
        await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertIs(self.coordinator.installed_state, candidate.state)

    async def test_inner_repository_scheduling_failure_keeps_original_command_uncertain(self):
        candidate = await self.ready()
        actual_create_task = asyncio.create_task
        calls = 0

        def first_only(awaitable):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('repository scheduling failed after retention')
            return actual_create_task(awaitable)

        with patch('vonneumann.db.transition_coordinator.asyncio.create_task', first_only):
            with self.assertRaises(CommandAdmissionError):
                await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertIs(self.coordinator.pending_candidate, candidate)
        self.assertIs(self.coordinator.pending_command, self.repo.pending)
        self.assertTrue(self.repo.uncertain)
        self.assertFalse(self.coordinator.accepting)
        self.assertEqual(self.transport.count('commit_command'), 0)
        self.assertIsNone(await self.coordinator.reconcile())
        self.assertIs(self.coordinator.pending_candidate, candidate)

    async def test_lease_expires_between_coordinator_and_repository_admission_without_post(self):
        candidate = await self.ready()
        # Entry observes a valid lease; the owned submit starts after the clock
        # advances. No RPC was admitted, so the local candidate can be released.
        task = self.spawn(self.coordinator.submit(candidate, command_id=self.identity()))
        for _ in range(10):
            if self.coordinator.pending_candidate is not None:
                break
            await asyncio.sleep(0)
        self.assertIs(self.coordinator.pending_candidate, candidate)
        self.clock.value += 30
        with self.assertRaises(CommandAdmissionError):
            await task
        self.assertIsNone(self.repo.pending)
        self.assertIsNone(self.coordinator.pending_candidate)
        self.assertIsNone(self.coordinator.installed_state)
        self.assertEqual(self.transport.count('commit_command'), 0)
        await self.coordinator.heartbeat()
        await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertIs(self.coordinator.installed_state, candidate.state)

    async def test_owned_publisher_cancel_during_ack_retries_ack_without_duplicate_callback(self):
        candidate = await self.ready()
        identity = self.identity()
        await self.coordinator.submit(candidate, command_id=identity)
        gate = self.gate('acknowledge_event')
        delivered = []

        async def publish(row):
            delivered.append(row['event_id'])

        task = self.spawn(self.coordinator.publish_pending(publish, max_events=1))
        await self.entered(gate)
        self.coordinator._task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(gate.cancelled)
        self.assertEqual(delivered, [f'{RUN}:{identity}:0'])
        await self.coordinator.publish_pending(publish, max_events=1)
        self.assertEqual(delivered, [f'{RUN}:{identity}:0'])
        self.assertEqual(self.coordinator.next_event_index, 1)
        self.assertEqual(self.transport.count('commit_command'), 1)

    async def test_oversized_page_rejection_never_calls_publisher(self):
        candidate = await self.ready()
        await self.coordinator.submit(candidate, command_id=self.identity())
        page = dict(version=1, owner_id=OWNER, run_id=RUN, through_revision=2,
                    events=deepcopy(self.transport.events), has_more=False)
        self.transport.fault('read_outbox', page)  # hostile server ignores the requested byte bound
        delivered = []

        async def publish(row):
            delivered.append(row)

        with self.assertRaises((ValueError, RuntimeError)):
            await self.coordinator.publish_pending(publish, max_bytes=512)
        self.assertEqual(delivered, [])
        self.assertEqual(self.transport.acknowledged, set())
        self.assertEqual(self.coordinator.next_event_index, 0)

    async def test_invalid_publication_budgets_and_callback_result_keep_delivery_unacked(self):
        candidate = await self.ready()
        await self.coordinator.submit(candidate, command_id=self.identity())
        calls = len(self.transport.calls)
        for options in ({'max_events': True}, {'max_events': 0}, {'max_events': 101},
                        {'max_bytes': True}, {'max_bytes': 0}, {'max_bytes': 65537}):
            with self.assertRaises((ValueError, RuntimeError)):
                await self.coordinator.publish_pending(self.sink, **options)
        self.assertEqual(len(self.transport.calls), calls)

        async def invalid_result(_row):
            return True

        with self.assertRaises((ValueError, RuntimeError)):
            await self.coordinator.publish_pending(invalid_result)
        self.assertEqual(self.transport.acknowledged, set())
        self.assertEqual(self.coordinator.next_event_index, 0)

    async def test_all_four_real_replacements_install_original_optimizer_state_without_replanning(self):
        from cmaes import CMA
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                self.transport = CommittingTransport()
                self.repo = CommandRepository(self.transport, OWNER, RUN, WORKER,
                                              monotonic=self.clock)
                candidate = await self.ready(algorithm)
                await self.coordinator.submit(candidate, command_id=self.identity())
                await self.coordinator.publish_pending(self.sink)
                replaced = False
                for bar in range(1, 66):
                    close = '100' if bar < 61 else '80' if bar != 62 else '120'
                    protected, decision = advance(candidate.state, bar * 900,
                                                  end=bar * 900, close=close)
                    for next_candidate in (protected, decision):
                        is_replacement = any(event['kind'] == 'evaluation'
                            for event in next_candidate.transition['events'])
                        previous = self.coordinator.installed_state
                        before = previous.to_dict()
                        if is_replacement:
                            strategy_type = type(next_candidate.state._fork()[1])
                            gate = self.gate('commit_command')
                            with ExitStack() as stack:
                                stack.enter_context(patch.object(strategy_type, 'evolve',
                                    side_effect=AssertionError('optimizer must not run during installation')))
                                stack.enter_context(patch.object(CMA, 'ask',
                                    side_effect=AssertionError('CMA ask must not repeat')))
                                stack.enter_context(patch.object(CMA, 'tell',
                                    side_effect=AssertionError('CMA tell must not repeat')))
                                task = self.spawn(self.coordinator.submit(next_candidate,
                                                     command_id=self.identity()))
                                await self.entered(gate)
                                retained = self.coordinator.pending_command.request
                                self.assertIs(self.coordinator.installed_state, previous)
                                self.assertEqual(previous.to_dict(), before)
                                task.cancel()
                                with self.assertRaises(asyncio.CancelledError):
                                    await task
                                gate.release.set()
                                await self.settled()
                                await self.coordinator.reconcile()
                                self.assertEqual(self.coordinator.pending_command.request, retained)
                                await self.coordinator.publish_pending(self.sink)
                            self.assertIs(self.coordinator.installed_state, next_candidate.state)
                            self.assertEqual(self.coordinator.installed_state.to_dict()['engine']['optimizer'],
                                             next_candidate.state.to_dict()['engine']['optimizer'])
                            self.assertEqual(previous.to_dict(), before)
                            replaced = True
                        else:
                            await self.coordinator.submit(next_candidate, command_id=self.identity())
                            await self.coordinator.publish_pending(self.sink)
                        candidate = next_candidate
                    if replaced:
                        break
                    # Execute the bar-62 entry and bar-63 signal exit causally.
                    if bar in (62, 63):
                        protected, decision = advance(candidate.state, bar * 900 + 1,
                                                      price='99' if bar == 63 else '100')
                        for candidate in (protected, decision):
                            await self.coordinator.submit(candidate, command_id=self.identity())
                            await self.coordinator.publish_pending(self.sink)
                self.assertTrue(replaced)
                self.assertEqual(self.coordinator.installed_state.to_dict()['engine']['generation'], 1)
                self.assertTrue(self.coordinator.accepting)


if __name__ == '__main__':
    unittest.main()
