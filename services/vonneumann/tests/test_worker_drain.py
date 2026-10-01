"""Offline races for worker startup ownership, admission and bounded draining."""

from __future__ import annotations

import asyncio
import importlib
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import A1, A2, USER_A, OfflineTestMixin, deny_network
from tests.test_lifecycle import FakeFeed

with deny_network():
    from fastapi import HTTPException
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.colony_manager import ColonyAdmissionError, ColonyLifecycleError, ColonyManager
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.types import TradeRecord
    from vonneumann.server.auth import VerifiedUser
    from vonneumann.server.models import StartRequest
    manager_module = importlib.import_module('vonneumann.core.colony_manager')
    app_module = importlib.import_module('vonneumann.server.app')


class WorkerDrainTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.managers, self.callers, self.release_gates = [], [], []
        self.manager = self.new_manager()
        self.feed = FakeFeed()
        self.events, self.persisted = [], []
        self.strategy = SimpleNamespace(name='genetic_algorithm', initialize=lambda *_: None,
                                        configure_search=lambda *_: None)
        self.offline_stack.enter_context(patch('vonneumann.core.strategies.get_strategy', return_value=self.strategy))
        self.offline_stack.enter_context(patch.object(GenesisController, '_tick_all', new=AsyncMock()))

    async def asyncTearDown(self):
        for gate in self.release_gates:
            gate.set()
        for task in self.callers:
            if not task.done():
                task.cancel()
        if self.callers:
            await asyncio.wait_for(asyncio.gather(*self.callers, return_exceptions=True), 2)
        for manager in self.managers:
            with patch.object(manager_module, 'SHUTDOWN_TIMEOUT_SECONDS', .2):
                await manager.shutdown()
        await super().asyncTearDown()

    def new_manager(self, **kwargs):
        manager = ColonyManager(**kwargs)
        self.managers.append(manager)
        return manager

    def release_gate(self):
        gate = asyncio.Event()
        self.release_gates.append(gate)
        return gate

    def spawn(self, awaitable):
        task = asyncio.create_task(awaitable)
        self.callers.append(task)
        return task

    async def wait(self, event):
        await asyncio.wait_for(event.wait(), 1)

    async def event(self, event):
        self.events.append(event)

    async def persist(self, status):
        self.persisted.append(dict(status))

    async def create(self, *, manager=None, colony_id=A1, **kwargs):
        manager = manager or self.manager
        args = dict(colony_id=colony_id, user_id=USER_A, mode='simulation',
                    strategy_name='genetic_algorithm', colony_config=ColonyConfig(),
                    on_event=self.event, gen0_count=2, seed_capital=10, max_capital=100,
                    tick_interval_ms=100, persist_status=self.persist)
        args.update(kwargs)
        with patch.object(manager, '_create_feed', return_value=self.feed):
            return await manager.create_colony(**args)

    def fake_app(self, repo, *, factory=None):
        self.offline_stack.enter_context(patch.object(app_module, 'colony_manager', self.manager))
        constructor = self.offline_stack.enter_context(patch.object(
            app_module, 'VonNeumannRepository', side_effect=factory, return_value=repo))
        self.offline_stack.enter_context(patch.object(app_module.ws_manager, 'broadcast_to_user', new=AsyncMock()))
        feed = self.offline_stack.enter_context(patch.object(self.manager, '_create_feed', return_value=self.feed))
        return constructor, feed

    def user(self):
        return VerifiedUser(USER_A, int(time.time()) + 3600)

    def test_retained_capacity_is_a_strict_bounded_integer(self):
        for value in (None, True, False, 0, -1, 129, 1.0, '32'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ColonyManager(max_retained_colonies=value)
        self.new_manager(max_retained_colonies=1)
        self.new_manager(max_retained_colonies=128)

    async def test_reservation_owns_operation_before_side_effects_and_rejects_duplicate(self):
        manager = self.new_manager(max_retained_colonies=1)
        entered, release = asyncio.Event(), self.release_gate()
        owners = []

        async def operation():
            owners.append(asyncio.current_task())
            self.assertIs(manager._start_tasks[A1], asyncio.current_task())
            entered.set()
            await release.wait()
            return {'accepted': A1}

        caller = self.spawn(manager.run_start(A1, operation))
        await self.wait(entered)
        self.assertIsNot(owners[0], caller)
        reserved = manager._start_tasks[A1]
        rejected = AsyncMock()
        with self.assertRaises(ColonyLifecycleError) as duplicate:
            await manager.run_start(A1, rejected)
        self.assertEqual(duplicate.exception.code, 'colony_exists')
        self.assertTrue(duplicate.exception.conflict)
        with self.assertRaises(ColonyAdmissionError) as capacity:
            await manager.run_start(A2, rejected)
        self.assertEqual(capacity.exception.code, 'worker_capacity')
        rejected.assert_not_called()
        self.assertIs(manager._start_tasks[A1], reserved)
        release.set()
        self.assertEqual(await caller, {'accepted': A1})
        self.assertNotIn(A1, manager._start_tasks)
        self.assertEqual(await manager.run_start(A2, AsyncMock(return_value='next')), 'next')

    async def test_concurrent_last_slot_admits_exactly_one_operation(self):
        manager = self.new_manager(max_retained_colonies=1)
        entered, release, calls = asyncio.Event(), self.release_gate(), []

        async def operation(ident):
            calls.append(ident)
            entered.set()
            await release.wait()
            return ident

        one = self.spawn(manager.run_start(A1, lambda: operation(A1)))
        two = self.spawn(manager.run_start(A2, lambda: operation(A2)))
        await self.wait(entered)
        await asyncio.sleep(0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(manager._start_tasks), 1)
        release.set()
        results = await asyncio.gather(one, two, return_exceptions=True)
        errors = [value for value in results if isinstance(value, ColonyAdmissionError)]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].code, 'worker_capacity')
        self.assertEqual([value for value in results if isinstance(value, str)], calls)

    async def test_create_inside_owner_uses_reserved_slot_and_duplicate_never_replaces_state(self):
        manager = self.new_manager(max_retained_colonies=1)
        result = await manager.run_start(A1, lambda: self.create(manager=manager))
        self.assertEqual(result, A1)
        colony, lock, task = manager.get_colony(A1), manager._locks[A1], manager._tasks[A1]
        with self.assertRaises(ColonyLifecycleError) as duplicate:
            await self.create(manager=manager)
        self.assertEqual(duplicate.exception.code, 'colony_exists')
        self.assertIs(manager.get_colony(A1), colony)
        self.assertIs(manager._locks[A1], lock)
        self.assertIs(manager._tasks[A1], task)
        self.assertEqual(self.feed.closed, 0)

    async def test_child_task_cannot_impersonate_the_start_reservation_owner(self):
        async def operation():
            child = self.spawn(self.create())
            with self.assertRaises(ColonyLifecycleError) as duplicate:
                await child
            self.assertEqual(duplicate.exception.code, 'colony_exists')

        await self.manager.run_start(A1, operation)
        self.assertEqual(self.feed.reads, 0)
        self.assertEqual(self.manager._colonies, {})

    async def test_stopped_and_failed_colonies_still_consume_retained_capacity(self):
        for failed in (False, True):
            manager = self.new_manager(max_retained_colonies=1)
            if failed:
                with patch.object(GenesisController, 'prepare', new=AsyncMock(side_effect=ValueError('fixture'))):
                    with self.assertRaises(ColonyLifecycleError):
                        await self.create(manager=manager)
                self.assertEqual(manager.get_colony(A1).lifecycle_status, 'failed')
            else:
                await self.create(manager=manager)
                await manager.stop_colony(A1)
                self.assertEqual(manager.get_colony(A1).lifecycle_status, 'stopped')
            with self.subTest(failed=failed), self.assertRaises(ColonyAdmissionError) as error:
                await self.create(manager=manager, colony_id=A2)
            self.assertEqual(error.exception.code, 'worker_capacity')
            self.assertEqual(set(manager._colonies), {A1})

    async def test_repeated_request_cancellation_cancels_owner_once_and_waits_for_compensation(self):
        entered, cleaning, release = asyncio.Event(), asyncio.Event(), self.release_gate()
        cancellations, finished = [], []

        async def operation():
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellations.append('cancel')
                cleaning.set()
                await release.wait()
                finished.append('compensated')
                raise

        caller = self.spawn(self.manager.run_start(A1, operation))
        await self.wait(entered)
        owned = self.manager._start_tasks[A1]
        caller.cancel()
        await self.wait(cleaning)
        for _ in range(3):
            caller.cancel()
            await asyncio.sleep(0)
        self.assertFalse(caller.done())
        self.assertFalse(owned.done())
        self.assertEqual(owned.cancelling(), 1)
        self.assertIs(self.manager._start_tasks[A1], owned)
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertEqual(cancellations, ['cancel'])
        self.assertEqual(finished, ['compensated'])
        self.assertNotIn(A1, self.manager._start_tasks)

    async def test_shutdown_deadline_retains_owned_work_and_reuses_one_drain_task(self):
        entered, cleaning, release = asyncio.Event(), asyncio.Event(), self.release_gate()

        async def operation():
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cleaning.set()
                await release.wait()
                raise

        caller = self.spawn(self.manager.run_start(A1, operation))
        await self.wait(entered)
        owner = self.manager._start_tasks[A1]
        with patch.object(manager_module, 'SHUTDOWN_TIMEOUT_SECONDS', .01):
            result = await asyncio.wait_for(self.manager.shutdown(), .5)
            self.assertEqual(result['status'], 'incomplete')
            self.assertGreater(result['pending_operations'], 0)
            await self.wait(cleaning)
            drain = self.manager._shutdown_task
            self.assertFalse(drain.done())
            again = await asyncio.wait_for(self.manager.shutdown(), .5)
            self.assertEqual(again['status'], 'incomplete')
            self.assertIs(self.manager._shutdown_task, drain)
            self.assertIs(self.manager._start_tasks[A1], owner)
            self.assertEqual(owner.cancelling(), 1)
            denied = AsyncMock()
            with self.assertRaises(ColonyAdmissionError) as error:
                await self.manager.run_start(A2, denied)
            self.assertEqual(error.exception.code, 'worker_draining')
            denied.assert_not_called()
            release.set()
            with self.assertRaises(ColonyLifecycleError) as interrupted:
                await caller
            self.assertEqual(interrupted.exception.code, 'worker_draining')
            await asyncio.wait_for(asyncio.shield(drain), 1)
            complete = await self.manager.shutdown()
        self.assertEqual(complete, {'status': 'complete', 'pending_operations': 0})
        self.assertIs(self.manager._shutdown_task, drain)

    async def test_shutdown_cancels_blocked_prepare_before_a_running_loop_can_appear(self):
        preparing, cancelled = asyncio.Event(), asyncio.Event()

        async def prepare(_controller):
            preparing.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with patch.object(GenesisController, 'prepare', new=prepare):
            caller = self.spawn(self.create())
            await self.wait(preparing)
            result = await self.manager.shutdown()
            with self.assertRaises(ColonyLifecycleError) as interrupted:
                await caller
            self.assertEqual(interrupted.exception.code, 'worker_draining')
        self.assertEqual(result, {'status': 'complete', 'pending_operations': 0})
        self.assertTrue(cancelled.is_set())
        self.assertEqual(self.manager.get_colony(A1).lifecycle_status, 'failed')
        self.assertEqual(self.manager.get_colony(A1).failure_code, 'startup_cancelled')
        self.assertEqual(self.manager._tasks, {})
        self.assertEqual(self.feed.closed, 1)

    async def test_cancellation_resistant_prepare_remains_owned_until_acknowledged(self):
        preparing, cancellation_seen = asyncio.Event(), asyncio.Event()
        release = self.release_gate()

        async def prepare(_controller):
            preparing.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellation_seen.set()
                await release.wait()
                # A provider suppressing cancellation cannot enable execution.

        with patch.object(GenesisController, 'prepare', new=prepare), \
                patch.object(GenesisController, 'run', new=AsyncMock()) as run, \
                patch.object(manager_module, 'SHUTDOWN_TIMEOUT_SECONDS', .01):
            caller = self.spawn(self.create())
            await self.wait(preparing)
            owner = self.manager._start_tasks[A1]
            controller = self.manager.get_colony(A1)
            result = await asyncio.wait_for(self.manager.shutdown(), .5)
            self.assertEqual(result['status'], 'incomplete')
            await self.wait(cancellation_seen)
            self.assertIs(self.manager._start_tasks[A1], owner)
            self.assertIs(self.manager.get_colony(A1), controller)
            self.assertTrue(controller._worker_draining)
            self.assertTrue(controller._paused)
            run.assert_not_awaited()
            self.assertEqual(self.feed.closed, 0)
            release.set()
            with self.assertRaises(ColonyLifecycleError) as error:
                await caller
            self.assertEqual(error.exception.code, 'worker_draining')
            await asyncio.wait_for(asyncio.shield(self.manager._shutdown_task), 1)
            self.assertEqual(await self.manager.shutdown(), {'status': 'complete', 'pending_operations': 0})
        run.assert_not_awaited()
        self.assertEqual(controller.lifecycle_status, 'failed')
        self.assertEqual(self.feed.closed, 1)

    async def test_startup_running_ack_during_drain_is_followed_by_failure_without_execution(self):
        acknowledging, release, writes = asyncio.Event(), self.release_gate(), []

        async def persist(status):
            if status['status'] == 'running':
                async def ack():
                    acknowledging.set()
                    await release.wait()
                    writes.append('running')
                await manager_module.complete_operation(ack())
            else:
                writes.append(status['status'])

        publish = AsyncMock()
        with patch.object(GenesisController, 'run', new=AsyncMock()) as run, \
                patch.object(manager_module, 'SHUTDOWN_TIMEOUT_SECONDS', .01):
            caller = self.spawn(self.create(persist_status=persist, on_status=publish))
            await self.wait(acknowledging)
            controller = self.manager.get_colony(A1)
            self.assertEqual(controller.lifecycle_status, 'running')
            first = await self.manager.shutdown()
            self.assertEqual(first['status'], 'incomplete')
            self.assertTrue(controller._worker_draining)
            self.assertTrue(controller._paused)
            self.assertEqual(writes, [])
            run.assert_not_awaited()
            release.set()
            with self.assertRaises(ColonyLifecycleError) as error:
                await caller
            self.assertEqual(error.exception.code, 'worker_draining')
            await asyncio.wait_for(asyncio.shield(self.manager._shutdown_task), 1)
            self.assertEqual(await self.manager.shutdown(), {'status': 'complete', 'pending_operations': 0})
        self.assertEqual(writes, ['running', 'failed'])
        self.assertEqual([call.args[0]['status'] for call in publish.await_args_list], ['failed'])
        self.assertEqual(controller.lifecycle_status, 'failed')
        self.assertFalse(controller._running)
        run.assert_not_awaited()

    async def test_failed_resource_close_is_retained_as_incomplete_after_tasks_finish(self):
        await self.create()
        controller = self.manager.get_colony(A1)
        with patch.object(self.feed, 'close', new=AsyncMock(side_effect=RuntimeError('private close failure'))) as close:
            result = await self.manager.shutdown()
            again = await self.manager.shutdown()
        self.assertEqual(result, {'status': 'incomplete', 'pending_operations': 0})
        self.assertEqual(again, result)
        self.assertTrue(self.manager._shutdown_task.done())
        self.assertIs(self.manager.get_colony(A1), controller)
        self.assertEqual(controller.lifecycle_status, 'failed')
        self.assertEqual(controller.failure_code, 'cleanup_failed')
        self.assertTrue(controller.state_persisted)
        self.assertNotIn('private close failure', str(controller.status()))
        close.assert_awaited_once()

    async def test_drain_during_initial_insert_waits_for_ack_then_terminal_compensation(self):
        inserting, compensating = asyncio.Event(), asyncio.Event()
        insert_release, failure_release = self.release_gate(), self.release_gate()
        writes = []

        async def execute(name, *args, **kwargs):
            if name == 'insert_colony':
                inserting.set()
                await insert_release.wait()
            elif name == 'update_colony_status':
                compensating.set()
                await failure_release.wait()
            writes.append((name, args, kwargs))

        _constructor, feed = self.fake_app(SimpleNamespace(execute_async=AsyncMock(side_effect=execute)))
        caller = self.spawn(app_module._start_colony(StartRequest(gen0_count=2), self.user()))
        await self.wait(inserting)
        self.assertEqual(len(self.manager._start_tasks), 1)
        self.assertEqual(self.manager._colonies, {})
        owned = next(iter(self.manager._start_tasks.values()))
        with patch.object(manager_module, 'SHUTDOWN_TIMEOUT_SECONDS', .01):
            first = await self.manager.shutdown()
            self.assertEqual(first['status'], 'incomplete')
            self.assertEqual(writes, [])
            insert_release.set()
            await self.wait(compensating)
            self.assertEqual([write[0] for write in writes], ['insert_colony'])
            caller.cancel()
            await asyncio.sleep(0)
            caller.cancel()
            second = await self.manager.shutdown()
            self.assertEqual(second['status'], 'incomplete')
            self.assertEqual(owned.cancelling(), 1)
            self.assertIn(owned, self.manager._start_tasks.values())
            feed.assert_not_called()
            failure_release.set()
            with self.assertRaises(asyncio.CancelledError):
                await caller
            self.assertEqual(await self.manager.shutdown(), {'status': 'complete', 'pending_operations': 0})
        self.assertEqual([write[0] for write in writes], ['insert_colony', 'update_colony_status'])
        ident = writes[0][1][0]
        self.assertEqual(writes[-1][1][:2], (ident, 'failed'))
        self.assertTrue(self.manager.get_colony(ident).state_persisted)
        self.assertEqual(self.manager._tasks, {})

    async def test_draining_http_start_touches_no_repository_or_feed_and_health_remains_live(self):
        repository = SimpleNamespace(execute_async=AsyncMock())
        constructor, feed = self.fake_app(repository)
        await self.manager.shutdown()
        with self.assertRaises(HTTPException) as caught:
            await app_module._start_colony(StartRequest(gen0_count=2), self.user())
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail['code'], 'worker_draining')
        constructor.assert_not_called()
        repository.execute_async.assert_not_called()
        feed.assert_not_called()
        self.assertEqual(await app_module.health(), {'status': 'ok'})

    async def test_slow_resource_close_obeys_global_deadline_without_losing_controller(self):
        await self.create()
        controller = self.manager.get_colony(A1)
        closing, release = asyncio.Event(), self.release_gate()
        close_calls = []

        async def close():
            close_calls.append('started')
            closing.set()
            await release.wait()
            close_calls.append('closed')

        with patch.object(self.feed, 'close', new=close), \
                patch.object(manager_module, 'SHUTDOWN_TIMEOUT_SECONDS', .01):
            result = await asyncio.wait_for(self.manager.shutdown(), .5)
            self.assertEqual(result['status'], 'incomplete')
            self.assertGreater(result['pending_operations'], 0)
            await self.wait(closing)
            self.assertIs(self.manager.get_colony(A1), controller)
            drain = self.manager._shutdown_task
            self.assertFalse(drain.done())
            release.set()
            await asyncio.wait_for(asyncio.shield(drain), 1)
            result = await self.manager.shutdown()
        self.assertEqual(result, {'status': 'complete', 'pending_operations': 0})
        self.assertIs(self.manager._shutdown_task, drain)
        self.assertEqual(close_calls, ['started', 'closed'])
        self.assertEqual(controller.lifecycle_status, 'stopped')
        self.assertTrue(controller.state_persisted)

    async def test_normal_shutdown_preserves_positions_and_durable_reconciliation_evidence(self):
        await self.create()
        controller = self.manager.get_colony(A1)
        probe = controller.live_probes[0]
        trade = TradeRecord(trade_id='drain-trade', probe_id=probe.probe_id, pair='SOL/USDC',
                            side='BUY', entry_price=100, amount=1)
        probe.open_positions['SOL/USDC'] = trade
        capital = probe.capital
        result = await self.manager.shutdown()
        self.assertEqual(result, {'status': 'complete', 'pending_operations': 0})
        self.assertEqual(controller.lifecycle_status, 'stopped')
        self.assertIs(probe.open_positions['SOL/USDC'], trade)
        self.assertEqual(probe.capital, capital)
        self.assertEqual(self.feed.closed, 1)
        self.assertFalse(self.persisted[-1]['state_persisted'])
        self.assertTrue(controller.state_persisted)
        self.assertEqual(self.persisted[-1]['open_positions'], 1)
        self.assertTrue(self.persisted[-1]['requires_reconciliation'])
        self.assertEqual(self.manager._tasks, {})


if __name__ == '__main__':
    unittest.main()
