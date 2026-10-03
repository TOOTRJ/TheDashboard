"""Real ownership boundaries: pre-dispatch rejection versus committed expiry."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import OfflineTestMixin
from tests.test_exact_rehearsal import OWNER, RUN, WORKER, initial, advance
from tests.test_transition_coordinator import Clock, CommittingTransport, Gate
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandRepository, CommandAdmissionError, UncertainCommand
from vonneumann.db.transition_coordinator import TransitionCoordinator, PublicationError


class DispatchAdmissionTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.clock = Clock()
        self.transport = CommittingTransport()
        self.repository = CommandRepository(self.transport, OWNER, RUN, WORKER, monotonic=self.clock)
        self.coordinator = None
        self.next_identity = 9600000
        self.checks = 0
        self.delivered = []
        self.tasks, self.gates = [], []

    async def asyncTearDown(self):
        for gate in self.gates:
            gate.release.set()
        if self.tasks:
            await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), 2)
        await self.settle()

    def identity(self):
        self.next_identity += 1
        return str(UUID(int=self.next_identity))

    def guard(self):
        self.checks += 1
        if self.clock.value >= 110:
            raise ValueError('private-source-expiry-detail')

    async def ready(self, *, guarded=True):
        config, candidate = initial()
        await self.repository.submit(PreparedCommand.create(OWNER, RUN, WORKER,
            config.run_configuration(), config.initial_cash, command_id=self.identity()))
        self.coordinator = TransitionCoordinator(self.repository, self.transport,
            admission_guard=self.guard if guarded else None)
        await self.coordinator.heartbeat()
        return candidate

    def command(self, candidate):
        return PreparedCommand.batch(OWNER, RUN, WORKER, self.repository.fence,
            self.repository.revision, candidate.operations, command_id=self.identity(),
            version=3, transition=candidate.transition)

    async def sink(self, event):
        self.delivered.append(event)

    async def expire(self, result, arguments):
        self.clock.value = 111
        return result

    async def expire_error(self, result, arguments):
        self.clock.value = 111
        raise OSError('private-transport-detail')

    async def settle(self):
        for _ in range(100):
            if not self.repository.busy and (self.coordinator is None or not self.coordinator.busy):
                return
            await asyncio.sleep(0)
        self.fail('Owned fake operation did not settle')

    def assert_unsent(self):
        self.assertEqual(self.transport.count('commit_command'), 0)
        self.assertIsNone(self.repository.pending)
        self.assertFalse(self.repository.uncertain)
        self.assertEqual(self.repository.revision, 1)
        if self.coordinator is not None:
            self.assertIsNone(self.coordinator.pending_candidate)
            self.assertIsNone(self.coordinator.installed_state)

    async def test_constructor_and_repository_reject_noncallable_guard_before_admission(self):
        candidate = await self.ready()
        with self.assertRaises(CommandAdmissionError):
            TransitionCoordinator(self.repository, self.transport, admission_guard=1)
        with self.assertRaises(CommandAdmissionError):
            await self.repository.submit(self.command(candidate), before_dispatch=1)
        self.assert_unsent()
        self.assertTrue(self.repository.accepting)

    async def test_repository_clock_exceptions_and_overflow_are_sanitized_and_invalidate_lease(self):
        await self.ready(guarded=False)
        def failing():
            raise RuntimeError('private-clock-detail')
        def cancelled():
            raise asyncio.CancelledError()
        for clock in (failing, cancelled, lambda: 10**400):
            self.repository._clock = clock
            with self.assertRaises(CommandAdmissionError) as caught:
                _ = self.repository.accepting
            self.assertNotIn('private', str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)
            self.assertTrue(caught.exception.__suppress_context__)
            self.repository._clock = self.clock
            self.assertFalse(self.repository.lease_valid)
            self.assertFalse(self.repository.accepting)
            await self.repository.heartbeat()
            self.assertTrue(self.repository.accepting)

    async def test_cancelled_coordinator_scheduling_closes_and_clears_unsent_candidate(self):
        candidate = await self.ready()
        with patch('vonneumann.db.transition_coordinator.asyncio.create_task', side_effect=asyncio.CancelledError):
            with self.assertRaises(CommandAdmissionError):
                await self.coordinator.submit(candidate, command_id=self.identity())
        self.assert_unsent()
        self.assertFalse(self.coordinator.busy)
        self.assertFalse(self.coordinator.accepting)

    async def test_cancelled_repository_scheduling_preserves_existing_uncertain_retention(self):
        candidate = await self.ready(guarded=False)
        command = self.command(candidate)
        with patch('vonneumann.db.command_repository.asyncio.create_task', side_effect=asyncio.CancelledError):
            with self.assertRaises(CommandAdmissionError):
                await self.repository.submit(command)
        self.assertEqual(self.transport.count('commit_command'), 0)
        self.assertIs(self.repository.pending, command)
        self.assertTrue(self.repository.uncertain)
        self.assertFalse(self.repository.busy)
        self.assertFalse(self.repository.accepting)

    async def test_guard_failure_is_provably_unsent_and_not_uncertain(self):
        candidate = await self.ready()
        self.clock.value = 111
        with self.assertRaises(CommandAdmissionError) as caught:
            await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertNotIn('private', str(caught.exception))
        self.assert_unsent()
        self.assertFalse(self.coordinator.accepting)
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.heartbeat()

    async def test_scheduler_gap_before_repository_dispatch_rechecks_guard(self):
        candidate = await self.ready()
        create_task = asyncio.create_task
        scheduled = 0
        def delayed(coroutine):
            nonlocal scheduled
            scheduled += 1
            task = create_task(coroutine)
            if scheduled == 2:
                # Coordinator admission already passed; repository work is queued.
                self.clock.value = 111
            return task
        with patch('vonneumann.db.command_repository.asyncio.create_task', side_effect=delayed):
            with self.assertRaises(CommandAdmissionError):
                await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertEqual(scheduled, 2)
        self.assert_unsent()

    async def test_scheduler_gap_rechecks_lease_even_without_guard(self):
        candidate = await self.ready(guarded=False)
        create_task = asyncio.create_task
        def delayed(coroutine):
            task = create_task(coroutine)
            self.clock.value = 130
            return task
        with patch('vonneumann.db.command_repository.asyncio.create_task', side_effect=delayed):
            with self.assertRaises(CommandAdmissionError):
                await self.repository.submit(self.command(candidate))
        self.assert_unsent()
        self.assertFalse(self.repository.lease_valid)
        await self.repository.heartbeat()
        self.assertTrue(self.repository.accepting)

    async def test_request_decode_cost_precedes_last_guard_and_lease_sample(self):
        candidate = await self.ready(guarded=False)
        command = self.command(candidate)
        getter = PreparedCommand.rpc_args.fget
        def decode_then_expire(value):
            arguments = getter(value)
            self.clock.value = 130
            return arguments
        with patch.object(PreparedCommand, 'rpc_args', property(decode_then_expire)):
            with self.assertRaises(CommandAdmissionError):
                await self.repository.submit(command, before_dispatch=self.guard)
        self.assert_unsent()

    async def test_unsent_request_materialization_failure_is_not_transport_uncertainty(self):
        candidate = await self.ready(guarded=False)
        command = self.command(candidate)
        def broken(value):
            raise ValueError('private-request-decoding-detail')
        with patch.object(PreparedCommand, 'rpc_args', property(broken)):
            with self.assertRaises(CommandAdmissionError) as caught:
                await self.repository.submit(command)
        self.assertNotIn('private', str(caught.exception))
        self.assert_unsent()

    async def test_scheduler_gap_rechecks_permanent_close_before_dispatch(self):
        candidate = await self.ready(guarded=False)
        create_task = asyncio.create_task
        def delayed(coroutine):
            task = create_task(coroutine)
            self.repository.close_admission()
            return task
        with patch('vonneumann.db.command_repository.asyncio.create_task', side_effect=delayed):
            with self.assertRaises(CommandAdmissionError):
                await self.repository.submit(self.command(candidate))
        self.assert_unsent()
        with self.assertRaises(CommandAdmissionError):
            await self.repository.heartbeat()

    async def test_guard_cannot_silently_close_admission_or_consume_lease_before_send(self):
        for mode in ('close', 'consume_lease'):
            with self.subTest(mode=mode):
                # Each iteration gets a new independent run owner.
                self.repository = CommandRepository(self.transport, OWNER, RUN, WORKER, monotonic=self.clock)
                candidate = await self.ready(guarded=False)
                def guard():
                    if mode == 'close':
                        self.repository.close_admission()
                    else:
                        self.clock.value += 30
                before = self.transport.count('commit_command')
                with self.assertRaises(CommandAdmissionError):
                    await self.repository.submit(self.command(candidate), before_dispatch=guard)
                self.assertEqual(self.transport.count('commit_command'), before)
                self.assertIsNone(self.repository.pending)
                self.assertFalse(self.repository.uncertain)

    async def test_async_guard_is_closed_without_await_or_rpc(self):
        candidate = await self.ready(guarded=False)
        retained = []
        async def forbidden():
            raise AssertionError('An admission guard must not be awaited')
        def guard():
            coroutine = forbidden()
            retained.append(coroutine)
            return coroutine
        with self.assertRaises(CommandAdmissionError):
            await self.repository.submit(self.command(candidate), before_dispatch=guard)
        self.assertIsNone(retained[0].cr_frame)
        self.assert_unsent()

    async def test_future_guard_is_not_awaited_or_cancelled(self):
        candidate = await self.ready(guarded=False)
        future = asyncio.get_running_loop().create_future()
        with self.assertRaises(CommandAdmissionError):
            await self.repository.submit(self.command(candidate), before_dispatch=lambda: future)
        self.assertFalse(future.done())
        future.set_result(None)
        self.assert_unsent()

    async def test_guard_cancellation_before_rpc_is_sanitized_unsent_rejection(self):
        candidate = await self.ready(guarded=False)
        def guard():
            raise asyncio.CancelledError()
        with self.assertRaises(CommandAdmissionError):
            await self.repository.submit(self.command(candidate), before_dispatch=guard)
        self.assert_unsent()

    async def test_expired_ack_still_installs_and_delivers_entire_committed_candidate(self):
        candidate = await self.ready()
        self.transport.fault('commit_command', self.expire)
        receipt = await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertEqual(receipt.revision, candidate.state.revision)
        self.assertIs(self.coordinator.installed_state, candidate.state)
        self.assertFalse(self.coordinator.accepting)
        self.assertEqual(self.transport.count('commit_command'), 1)
        delivered = await self.coordinator.publish_pending(self.sink)
        self.assertEqual(delivered, len(candidate.transition['events']))
        self.assertEqual(len(self.delivered), delivered)
        self.assertFalse(self.coordinator.accepting)
        self.assertIsNone(self.coordinator.pending_candidate)

    async def test_post_rpc_error_remains_uncertain_despite_guard_failure(self):
        candidate = await self.ready()
        self.transport.fault('commit_command', self.expire_error)
        with self.assertRaises(UncertainCommand):
            await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertIsNotNone(self.repository.pending)
        self.assertIs(self.coordinator.pending_candidate, candidate)
        self.assertTrue(self.repository.uncertain)
        self.assertIsNone(self.coordinator.installed_state)
        # Expiry may not block read-only resolution or acknowledged installation.
        receipt = await self.coordinator.reconcile()
        self.assertEqual(receipt.revision, candidate.state.revision)
        self.assertIs(self.coordinator.installed_state, candidate.state)
        await self.coordinator.publish_pending(self.sink)
        self.assertEqual(self.transport.count('commit_command'), 1)
        self.assertFalse(self.coordinator.accepting)

    async def test_readback_expiry_checks_after_resolution_and_still_installs(self):
        candidate = await self.ready()
        self.transport.fault('commit_command', OSError('lost reply'))
        with self.assertRaises(UncertainCommand):
            await self.coordinator.submit(candidate, command_id=self.identity())
        self.transport.fault('get_command', self.expire)
        receipt = await self.coordinator.reconcile()
        self.assertEqual(receipt.revision, candidate.state.revision)
        self.assertIs(self.coordinator.installed_state, candidate.state)
        self.assertFalse(self.repository.accepting)
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.heartbeat()

    async def test_retained_receipt_reconciliation_without_rpc_checks_expiry(self):
        candidate = await self.ready()
        with patch.object(self.coordinator, '_install', side_effect=RuntimeError('installation retry')):
            with self.assertRaises(RuntimeError):
                await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertIsNotNone(self.coordinator.pending_receipt)
        self.clock.value = 111
        receipt = await self.coordinator.reconcile()
        self.assertEqual(receipt.revision, candidate.state.revision)
        self.assertIs(self.coordinator.installed_state, candidate.state)
        self.assertEqual(self.transport.count('get_command'), 0)
        self.assertFalse(self.coordinator.accepting)

    async def test_eventless_ack_clears_candidate_but_does_not_erase_expiry_latch(self):
        candidate = await self.ready()
        await self.coordinator.submit(candidate, command_id=self.identity())
        await self.coordinator.publish_pending(self.sink)
        protected, _ = advance(candidate.state, 900)
        self.assertEqual(protected.transition['events'], [])
        self.transport.fault('commit_command', self.expire)
        await self.coordinator.submit(protected, command_id=self.identity())
        self.assertIs(self.coordinator.installed_state, protected.state)
        self.assertIsNone(self.coordinator.pending_candidate)
        self.assertFalse(self.coordinator.accepting)

    async def test_missing_or_failed_readback_remains_original_outcome_and_closes(self):
        candidate = await self.ready()
        self.transport.fault('commit_command', OSError('lost reply'))
        with self.assertRaises(UncertainCommand):
            await self.coordinator.submit(candidate, command_id=self.identity())
        self.transport.fault('get_command', self.expire_error)
        with self.assertRaises(UncertainCommand):
            await self.coordinator.reconcile()
        self.assertTrue(self.repository.uncertain)
        self.assertIs(self.coordinator.pending_candidate, candidate)
        self.transport.fault('get_command', None)
        self.assertIsNone(await self.coordinator.reconcile())
        self.assertFalse(self.coordinator.accepting)

    async def test_heartbeat_reply_cannot_reopen_admission_when_guard_expires(self):
        await self.ready()
        self.transport.fault('heartbeat', self.expire)
        await self.coordinator.heartbeat()
        self.assertFalse(self.repository.lease_valid)
        self.assertFalse(self.coordinator.accepting)
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.heartbeat()

    async def test_outbox_read_expiry_does_not_discard_or_stop_committed_delivery(self):
        candidate = await self.ready()
        await self.coordinator.submit(candidate, command_id=self.identity())
        self.transport.fault('read_outbox', self.expire)
        count = await self.coordinator.publish_pending(self.sink)
        self.assertEqual(count, len(candidate.transition['events']))
        self.assertEqual(len(self.delivered), count)
        self.assertFalse(self.coordinator.accepting)

    async def test_publisher_expiry_keeps_success_and_original_event_acknowledgment(self):
        candidate = await self.ready()
        await self.coordinator.submit(candidate, command_id=self.identity())
        async def publisher(event):
            self.delivered.append(event)
            self.clock.value = 111
        count = await self.coordinator.publish_pending(publisher)
        self.assertEqual(count, len(candidate.transition['events']))
        self.assertEqual(self.transport.count('acknowledge_event'), count)
        self.assertFalse(self.coordinator.accepting)

    async def test_acknowledge_expiry_keeps_ack_and_continues_ordered_delivery(self):
        candidate = await self.ready()
        await self.coordinator.submit(candidate, command_id=self.identity())
        self.transport.fault('acknowledge_event', self.expire)
        count = await self.coordinator.publish_pending(self.sink)
        self.assertEqual(count, len(candidate.transition['events']))
        self.assertEqual(len(self.transport.acknowledged), count)
        self.assertFalse(self.coordinator.accepting)

    async def test_outbox_errors_preserve_publication_error_and_ack_only_retry(self):
        candidate = await self.ready()
        await self.coordinator.submit(candidate, command_id=self.identity())
        self.transport.fault('acknowledge_event', self.expire_error)
        with self.assertRaises(PublicationError):
            await self.coordinator.publish_pending(self.sink)
        self.assertEqual(len(self.delivered), 1)
        self.assertEqual(self.coordinator.next_event_index, 0)
        await self.coordinator.publish_pending(self.sink)
        self.assertEqual(len(self.delivered), len(candidate.transition['events']))
        self.assertFalse(self.coordinator.accepting)

    async def test_cancelled_publisher_still_checks_expiry_and_retains_original_event(self):
        candidate = await self.ready()
        await self.coordinator.submit(candidate, command_id=self.identity())
        async def publisher(event):
            self.clock.value = 111
            raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.coordinator.publish_pending(publisher)
        self.assertEqual(self.coordinator.next_event_index, 0)
        self.assertIs(self.coordinator.pending_candidate, candidate)
        self.assertFalse(self.coordinator.accepting)
        await self.coordinator.publish_pending(self.sink)
        self.assertEqual(len(self.delivered), len(candidate.transition['events']))

    async def test_caller_cancellation_does_not_skip_late_ack_guard_or_installation(self):
        candidate = await self.ready()
        gate = Gate()
        self.gates.append(gate)
        self.transport.fault('commit_command', gate)
        task = asyncio.create_task(self.coordinator.submit(candidate, command_id=self.identity()))
        self.tasks.append(task)
        await asyncio.wait_for(gate.entered.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.clock.value = 111
        gate.release.set()
        await self.settle()
        self.assertIs(self.coordinator.installed_state, candidate.state)
        self.assertFalse(self.coordinator.accepting)
        await self.coordinator.publish_pending(self.sink)
        self.assertEqual(self.transport.count('commit_command'), 1)

    async def test_post_await_async_guard_result_is_closed_without_masking_commit(self):
        candidate = await self.ready(guarded=False)
        retained = []
        async def forbidden():
            raise AssertionError('Post-await guard must be synchronous')
        def guard():
            if self.transport.count('commit_command'):
                coroutine = forbidden()
                retained.append(coroutine)
                return coroutine
        self.coordinator = TransitionCoordinator(self.repository, self.transport, admission_guard=guard)
        receipt = await self.coordinator.submit(candidate, command_id=self.identity())
        self.assertEqual(receipt.revision, candidate.state.revision)
        self.assertIsNone(retained[0].cr_frame)
        self.assertIs(self.coordinator.installed_state, candidate.state)
        self.assertFalse(self.coordinator.accepting)
