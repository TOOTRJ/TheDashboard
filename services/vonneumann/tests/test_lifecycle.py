"""Offline lifecycle regressions using real controllers and fake I/O."""
from __future__ import annotations
import asyncio
import importlib
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from tests.security_support import A1, A2, USER_A, USER_B, OfflineTestMixin, deny_network
from tests.test_repository_security import RecordingDB, RecordingQuery
with deny_network():
    from fastapi import HTTPException
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.colony_manager import ColonyManager, ColonyLifecycleError
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.funding import FundingError
    from vonneumann.core.market_validation import MarketValueError
    from vonneumann.core.risk_control import RiskRecoveryError, RISK_RECOVERY_MESSAGES
    from vonneumann.core.types import EventType, ProbeEvent, TradeRecord
    from vonneumann.db.repository import PersistenceError, VonNeumannRepository
    from vonneumann.market.feed import MarketFeedError, MarketTick, QuoteEvidence
    from vonneumann.server.auth import VerifiedUser
    from vonneumann.server.models import StartRequest
    manager_module = importlib.import_module('vonneumann.core.colony_manager')
    app_module = importlib.import_module('vonneumann.server.app')

class FakeFeed:
    def __init__(self):
        self.closed = self.reads = self.history_reads = 0
        self.gate = None
    async def get_ticks(self, assets):
        self.reads += 1
        if self.gate is not None:
            await self.gate.wait()
        stamp, monotonic = time.time(), time.monotonic()
        return {a: MarketTick(a, 100 + self.reads * .01, 10, stamp,
                             QuoteEvidence(self.reads, stamp, monotonic)) for a in assets}
    async def get_candles(self, assets, **kwargs):
        self.history_reads += 1
        return []
    async def close(self):
        self.closed += 1

class LifecycleTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.manager, self.feed = ColonyManager(), FakeFeed()
        self.events, self.persisted, self.published = [], [], []
        self.strategy = SimpleNamespace(name='genetic_algorithm', initialize=lambda *_: None,
                                        configure_search=lambda *_: None)
        self.offline_stack.enter_context(patch.object(self.manager, '_create_feed', return_value=self.feed))
        self.offline_stack.enter_context(patch('vonneumann.core.strategies.get_strategy', return_value=self.strategy))
        self.tick = self.offline_stack.enter_context(patch.object(GenesisController, '_tick_all', new=AsyncMock()))
    async def asyncTearDown(self):
        await self.manager.shutdown()
        await asyncio.sleep(0)
        await super().asyncTearDown()
    async def event(self, value): self.events.append(value)
    async def persist(self, value): self.persisted.append(dict(value))
    async def publish(self, value): self.published.append(dict(value))
    async def create(self, **overrides):
        args = dict(colony_id=A1, user_id=USER_A, mode='simulation', strategy_name='genetic_algorithm',
                    colony_config=ColonyConfig(), on_event=self.event, gen0_count=2,
                    seed_capital=10, max_capital=100, tick_interval_ms=100,
                    persist_status=self.persist, on_status=self.publish)
        args.update(overrides)
        return await self.manager.create_colony(**args)
    async def failed(self):
        task = self.manager._tasks.get(A1)
        if task: await asyncio.wait_for(asyncio.shield(task), 1)
        status = self.manager.get_colony(A1).status()
        self.assertEqual(status['status'], 'failed')
        self.assertEqual(self.manager.active_count(), 0)
        self.assertNotIn(A1, self.manager._tasks)
        self.assertEqual(self.feed.closed, 1)
        return status
    async def test_preparation_waits_for_prices_history_and_initial_persistence(self):
        self.feed.gate = asyncio.Event()
        task = asyncio.create_task(self.create(mode='paper'))
        while not self.feed.reads: await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.assertEqual(self.manager.get_colony(A1).status()['status'], 'starting')
        self.assertNotIn(A1, self.manager._tasks)
        self.assertEqual(len(self.events), 2)
        self.assertTrue(all(e.event_type == EventType.PROBE_BORN for e in self.events))
        self.assertGreater(self.feed.history_reads, 0)
        self.feed.gate.set()
        await task
        self.assertEqual(self.manager.get_colony(A1).status()['status'], 'running')
        self.assertFalse(self.persisted[0]['state_persisted'])
        self.assertTrue(self.published[0]['state_persisted'])
    async def test_initial_probe_write_failure_is_retained_and_owner_visible(self):
        async def fail(_): raise PersistenceError('insert_probe')
        with self.assertRaises(ColonyLifecycleError) as error: await self.create(on_event=fail)
        self.assertEqual(error.exception.code, 'persistence_failed')
        status = await self.failed()
        self.assertTrue(status['state_persisted'])
        self.assertTrue(status['requires_reconciliation'])
        self.assertEqual(len(self.manager.list_colonies(USER_A)), 1)
        self.assertEqual(self.manager.list_colonies(USER_B), [])
    async def test_strategy_failure_is_sanitized_and_never_fake_running(self):
        def fail(*_): raise ValueError('PRIVATE_DETAIL')
        self.strategy.initialize = fail
        with self.assertRaises(ColonyLifecycleError): await self.create()
        status = await self.failed()
        self.assertNotIn('PRIVATE_DETAIL', str(status))
        self.assertEqual(status['failure_code'], 'startup_failed')
    async def test_controller_constructor_failure_closes_created_feed(self):
        with patch.object(manager_module, 'GenesisController', side_effect=RuntimeError('private')):
            with self.assertRaises(ColonyLifecycleError): await self.create()
        await self.failed()
    async def test_startup_timeout_cancels_warmup_and_starts_no_loop(self):
        self.feed.gate = asyncio.Event()
        with patch.object(manager_module, 'STARTUP_TIMEOUT_SECONDS', .01):
            with self.assertRaises(ColonyLifecycleError) as error: await self.create()
        self.assertEqual(error.exception.code, 'startup_timeout')
        await self.failed()
        self.tick.assert_not_awaited()
    async def test_missing_initial_prices_fail_preparation(self):
        with patch.object(self.feed, 'get_ticks', new=AsyncMock(return_value={})):
            with self.assertRaises(ColonyLifecycleError): await self.create()
        await self.failed()
    async def test_incomplete_initial_population_never_reports_ready(self):
        with patch.object(GenesisController, '_spawn_probe', new=AsyncMock(return_value=None)):
            with self.assertRaises(ColonyLifecycleError): await self.create()
        await self.failed()
        self.assertEqual(self.feed.reads, 0)
    async def test_feed_failure_has_safe_specific_terminal_code(self):
        with patch.object(self.feed, 'get_ticks', new=AsyncMock(side_effect=MarketFeedError('price_rate_limited'))):
            with self.assertRaises(ColonyLifecycleError) as error: await self.create()
        self.assertEqual(error.exception.code, 'feed_unavailable')
        self.assertEqual((await self.failed())['failure_code'], 'feed_unavailable')
    async def test_stale_paper_source_has_specific_persisted_failure_and_does_not_start(self):
        with patch.object(self.feed, 'get_ticks', new=AsyncMock(side_effect=MarketFeedError('price_stale'))):
            with self.assertRaises(ColonyLifecycleError) as error: await self.create(mode='paper')
        self.assertEqual(error.exception.code, 'feed_stale')
        status = await self.failed()
        self.assertEqual(status['failure_code'], 'feed_stale')
        self.assertEqual(self.persisted[-1]['failure_code'], 'feed_stale')
        self.assertEqual(status['quote_policy']['max_source_age_seconds'], 30)
        self.tick.assert_not_awaited()
    async def test_wrong_rpc_network_fails_before_any_probe_is_created(self):
        with patch.object(self.manager, '_create_feed', side_effect=MarketFeedError('rpc_wrong_network')):
            with self.assertRaises(ColonyLifecycleError) as error: await self.create(mode='paper')
        self.assertEqual(error.exception.code, 'feed_configuration')
        self.assertEqual(self.manager.get_colony(A1).status()['status'], 'failed')
        self.assertEqual(self.persisted[-1]['failure_code'], 'feed_configuration')
        self.assertEqual(self.events, [])
        self.tick.assert_not_awaited()
    async def test_candle_failure_is_supervised_for_configured_assets_only(self):
        refresh = AsyncMock(side_effect=MarketFeedError('candles_unavailable'))
        self.feed.get_candles = refresh
        with self.assertRaises(ColonyLifecycleError):
            await self.create(colony_config=ColonyConfig(available_assets=['SOL/USDC']))
        self.assertEqual((await self.failed())['failure_code'], 'feed_unavailable')
        refresh.assert_awaited_once_with(['SOL/USDC'], warmup=True)
    async def test_unavailable_status_storage_is_truthfully_reported(self):
        async def fail(_): raise PersistenceError('update_colony_status')
        with self.assertRaises(ColonyLifecycleError): await self.create(persist_status=fail)
        status = await self.failed()
        self.assertFalse(status['state_persisted'])
        self.assertFalse(self.published[-1]['state_persisted'])
        self.tick.assert_not_awaited()
    async def test_tick_failure_stops_once_without_retry_or_private_errors(self):
        self.tick.side_effect = ZeroDivisionError('PRIVATE_DETAIL')
        await self.create()
        status = await self.failed()
        self.assertEqual(self.tick.await_count, 1)
        self.assertEqual(status['failure_code'], 'execution_failed')
        self.assertNotIn('PRIVATE_DETAIL', str(status))
    async def test_replacement_failure_is_terminal_preserves_owned_funds_and_is_not_retried(self):
        self.tick.side_effect = FundingError('funding_insufficient')
        await self.create()
        status = await self.failed()
        self.assertEqual(self.tick.await_count, 1)
        self.assertEqual(status['failure_code'], 'funding_insufficient')
        self.assertTrue(status['state_persisted'])
        self.assertTrue(status['requires_reconciliation'])
        self.assertEqual(status['live_probes'], 2)
        self.assertEqual(status['total_capital'], 100)
        self.assertEqual(self.persisted[-1]['failure_code'], 'funding_insufficient')
        self.assertEqual(self.published[-1]['failure_code'], 'funding_insufficient')
    async def test_unrecognized_funding_error_is_sanitized(self):
        self.tick.side_effect = FundingError('PRIVATE_DETAIL')
        await self.create()
        status = await self.failed()
        self.assertEqual(status['failure_code'], 'funding_invalid_plan')
        self.assertNotIn('PRIVATE_DETAIL', str(status))
    async def test_genesis_emit_propagates_persistence_failure(self):
        await self.create()
        controller = self.manager.get_colony(A1)
        controller._on_event = AsyncMock(side_effect=PersistenceError('insert_trade'))
        with self.assertRaises(PersistenceError):
            await controller._emit(ProbeEvent(event_type=EventType.TRADE_OPENED, probe_id='p', data={}))
    async def test_pause_resume_stop_persist_and_terminal_controls_conflict(self):
        await self.create()
        await self.manager.pause_colony(A1)
        await self.manager.resume_colony(A1)
        await self.manager.stop_colony(A1)
        self.assertEqual([s['status'] for s in self.persisted], ['running', 'paused', 'running', 'stopped'])
        for control in (self.manager.pause_colony, self.manager.resume_colony):
            with self.assertRaises(ColonyLifecycleError) as error: await control(A1)
            self.assertTrue(error.exception.conflict)
        self.assertIsNotNone(self.manager.get_owned_colony(A1, USER_A))

    async def test_halted_colony_is_active_and_can_stop_but_not_pause_or_resume(self):
        await self.create()
        colony = self.manager.get_colony(A1)
        colony.circuit_breaker_active = True
        colony.set_lifecycle('risk_halted')
        self.assertEqual(self.manager.active_count(), 1)
        for control in (self.manager.pause_colony, self.manager.resume_colony):
            with self.assertRaises(ColonyLifecycleError) as error:
                await control(A1)
            self.assertTrue(error.exception.conflict)
        self.assertEqual(self.feed.closed, 0)
        self.assertTrue(colony.circuit_breaker_active)
        await self.manager.stop_colony(A1)
        self.assertEqual(colony.lifecycle_status, 'stopped')
        self.assertTrue(colony.circuit_breaker_active)
        self.assertEqual(self.feed.closed, 1)
        self.assertEqual(self.manager.active_count(), 0)

    async def test_pause_racing_trip_keeps_halt_monitored_and_does_not_fail(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def tick():
            entered.set()
            await release.wait()
            colony = self.manager.get_colony(A1)
            colony.circuit_breaker_active = True
            colony.set_lifecycle('risk_halted')
            await self.persist(colony.status())
        self.tick.side_effect = tick
        await self.create()
        await entered.wait()
        task = asyncio.create_task(self.manager.pause_colony(A1))
        colony = self.manager.get_colony(A1)
        while not colony._paused:
            await asyncio.sleep(0)
        release.set()
        with self.assertRaises(ColonyLifecycleError) as error:
            await task
        self.assertTrue(error.exception.conflict)
        self.assertEqual(colony.lifecycle_status, 'risk_halted')
        self.assertFalse(colony._paused)
        self.assertTrue(colony._running)
        self.assertEqual(self.feed.closed, 0)
        self.assertEqual([s['status'] for s in self.persisted], ['running', 'risk_halted'])

    async def test_stop_racing_trip_stops_after_halt_without_deadlock(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def tick():
            entered.set()
            await release.wait()
            colony = self.manager.get_colony(A1)
            colony.circuit_breaker_active = True
            colony.set_lifecycle('risk_halted')
            await self.persist(colony.status())
        self.tick.side_effect = tick
        await self.create()
        await entered.wait()
        task = asyncio.create_task(self.manager.stop_colony(A1))
        while not self.manager._locks[A1].locked():
            await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(task, 1)
        self.assertEqual(self.manager.get_colony(A1).lifecycle_status, 'stopped')
        self.assertEqual([s['status'] for s in self.persisted], ['running', 'risk_halted', 'stopped'])
        self.assertEqual(self.feed.closed, 1)

    async def test_recovery_conflicts_keep_halt_and_feed_running(self):
        await self.create()
        colony = self.manager.get_colony(A1)
        colony.circuit_breaker_active = True
        colony.set_lifecycle('risk_halted')
        for code in RISK_RECOVERY_MESSAGES:
            with self.subTest(code=code), patch.object(
                    colony, 'recover_circuit_breaker', new=AsyncMock(side_effect=RiskRecoveryError(code))):
                with self.assertRaises(ColonyLifecycleError) as error:
                    await self.manager.recover_colony(A1, A1)
                self.assertEqual(error.exception.code, code)
                self.assertTrue(error.exception.conflict)
                self.assertEqual(colony.lifecycle_status, 'risk_halted')
                self.assertTrue(colony.circuit_breaker_active)
                self.assertEqual(self.feed.closed, 0)
        self.assertEqual(len(self.persisted), 1)

    async def test_recovery_of_running_colony_conflicts_before_engine(self):
        await self.create()
        colony = self.manager.get_colony(A1)
        with patch.object(colony, 'recover_circuit_breaker', new=AsyncMock()) as recover:
            with self.assertRaises(ColonyLifecycleError) as error:
                await self.manager.recover_colony(A1, A1)
            self.assertEqual(error.exception.code, 'risk_not_halted')
            self.assertTrue(error.exception.conflict)
            recover.assert_not_awaited()

    async def test_recovery_persistence_failure_fails_closed_with_latch_retained(self):
        await self.create()
        colony = self.manager.get_colony(A1)
        colony.circuit_breaker_active = True
        colony.set_lifecycle('risk_halted')
        with patch.object(colony, 'recover_circuit_breaker',
                          new=AsyncMock(side_effect=PersistenceError('update_colony_status'))):
            with self.assertRaises(ColonyLifecycleError) as error:
                await self.manager.recover_colony(A1, A1)
            self.assertEqual(error.exception.code, 'persistence_failed')
            self.assertFalse(error.exception.conflict)
        status = await self.failed()
        self.assertTrue(status['circuit_breaker'])
        self.assertTrue(self.persisted[-1]['circuit_breaker'])

    async def test_recovery_timeout_fails_closed_without_abandoning_owned_positions(self):
        await self.create()
        colony = self.manager.get_colony(A1)
        colony.circuit_breaker_active = True
        colony.set_lifecycle('risk_halted')
        cancelled = asyncio.Event()
        async def blocked(_):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        with patch.object(colony, 'recover_circuit_breaker', new=blocked), \
                patch.object(manager_module, 'QUIESCE_TIMEOUT_SECONDS', .01):
            with self.assertRaises(ColonyLifecycleError) as error:
                await self.manager.recover_colony(A1, A1)
        self.assertEqual(error.exception.code, 'execution_failed')
        self.assertTrue(cancelled.is_set())
        status = await self.failed()
        self.assertTrue(status['circuit_breaker'])
        self.assertTrue(status['requires_reconciliation'])

    async def test_cancelled_recovery_finishes_and_serializes_with_stop(self):
        await self.create()
        colony = self.manager.get_colony(A1)
        colony.circuit_breaker_active = True
        colony.set_lifecycle('risk_halted')
        entered, release = asyncio.Event(), asyncio.Event()
        async def recover(trip_id):
            self.assertEqual(trip_id, A2)
            entered.set()
            await release.wait()
            colony.circuit_breaker_active = False
            colony.set_lifecycle('running')
            await self.persist(colony.status())
        with patch.object(colony, 'recover_circuit_breaker', new=AsyncMock(side_effect=recover)):
            task = asyncio.create_task(self.manager.recover_colony(A1, A2))
            await entered.wait()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            stopped = asyncio.create_task(self.manager.stop_colony(A1))
            await asyncio.sleep(0)
            self.assertFalse(stopped.done())
            self.assertEqual(self.feed.closed, 0)
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(stopped, 1)
        self.assertEqual(colony.lifecycle_status, 'stopped')
        self.assertEqual([s['status'] for s in self.persisted], ['running', 'running', 'stopped'])

    async def test_halted_loop_unexpected_exit_is_supervised(self):
        async def exit_loop(colony):
            colony.set_lifecycle('risk_halted')
        with patch.object(GenesisController, 'run', new=exit_loop):
            await self.create()
            self.assertEqual((await self.failed())['failure_code'], 'execution_failed')

    async def test_shutdown_stops_halted_colony(self):
        await self.create()
        self.manager.get_colony(A1).set_lifecycle('risk_halted')
        await self.manager.shutdown()
        self.assertEqual(self.manager.get_colony(A1).lifecycle_status, 'stopped')
        self.assertEqual(self.feed.closed, 1)

    async def test_resume_acknowledgement_during_drain_cannot_reopen_execution(self):
        await self.create()
        await self.manager.pause_colony(A1)
        colony = self.manager.get_colony(A1)
        entered, release = asyncio.Event(), asyncio.Event()

        async def persist(status):
            if status['status'] == 'running':
                entered.set()
                await release.wait()
            await self.persist(status)

        self.manager._persist[A1] = persist
        resume = asyncio.create_task(self.manager.resume_colony(A1))
        await entered.wait()
        shutdown = asyncio.create_task(self.manager.shutdown())
        try:
            await asyncio.sleep(0)
            self.assertTrue(colony._worker_draining)
            ticks = self.tick.await_count
            release.set()
            with self.assertRaises(ColonyLifecycleError) as error:
                await resume
            self.assertEqual(error.exception.code, 'worker_draining')
            self.assertEqual((await shutdown)['status'], 'complete')
            self.assertEqual(self.tick.await_count, ticks)
            self.assertEqual(colony.lifecycle_status, 'failed')
            self.assertTrue(colony._paused)
        finally:
            release.set()
            await asyncio.gather(resume, shutdown, return_exceptions=True)

    async def test_real_risk_recovery_ack_and_publication_during_drain_cannot_tick(self):
        await self.create()
        colony = self.manager.get_colony(A1)
        colony.circuit_breaker_active = True
        colony._risk_control['trip_id'] = A2
        colony.set_lifecycle('risk_halted')
        entered, release = asyncio.Event(), asyncio.Event()
        publishing, published = asyncio.Event(), asyncio.Event()

        async def persist(status):
            if status['status'] == 'running':
                entered.set()
                await release.wait()
            await self.persist(status)

        async def publish(_action):
            publishing.set()
            await published.wait()

        colony._persist_risk_status = persist
        with patch.object(colony, '_publish_risk_change', new=publish):
            recovery = asyncio.create_task(self.manager.recover_colony(A1, A2))
            await asyncio.wait_for(entered.wait(), 1)
            shutdown = asyncio.create_task(self.manager.shutdown())
            try:
                await asyncio.sleep(0)
                ticks = self.tick.await_count
                release.set()
                await asyncio.wait_for(publishing.wait(), 1)
                # Recovery acknowledged running, but the permanent drain latch
                # keeps queued tick-loop decisions disabled during publication.
                self.assertEqual(colony.lifecycle_status, 'running')
                self.assertTrue(colony._paused)
                colony.resume()
                colony.set_lifecycle('running')
                self.assertTrue(colony._paused)
                await asyncio.sleep(.11)
                self.assertEqual(self.tick.await_count, ticks)
                published.set()
                with self.assertRaises(ColonyLifecycleError) as error:
                    await recovery
                self.assertEqual(error.exception.code, 'worker_draining')
                self.assertEqual((await shutdown)['status'], 'complete')
                self.assertEqual(colony.lifecycle_status, 'failed')
                self.assertFalse(colony.circuit_breaker_active)  # ACK evidence is preserved.
            finally:
                release.set()
                published.set()
                await asyncio.gather(recovery, shutdown, return_exceptions=True)

    async def test_drain_rejects_new_controls_before_controller_mutation(self):
        await self.create()
        await self.manager.shutdown()
        colony = self.manager.get_colony(A1)
        before = list(self.persisted)
        for action, args in ((self.manager.pause_colony, (A1,)),
                             (self.manager.resume_colony, (A1,)),
                             (self.manager.recover_colony, (A1, A2)),
                             (self.manager.stop_colony, (A1,))):
            with self.assertRaises(ColonyLifecycleError) as error:
                await action(*args)
            self.assertEqual(error.exception.code, 'worker_draining')
        self.assertEqual(self.persisted, before)
        self.assertEqual(colony.lifecycle_status, 'stopped')

    async def test_failed_resource_close_is_retained_and_never_reported_as_complete(self):
        await self.create()
        with patch.object(self.feed, 'close', new=AsyncMock(side_effect=RuntimeError('private-close'))) as close:
            first = await self.manager.shutdown()
            second = await self.manager.shutdown()
        self.assertEqual(first, {'status': 'incomplete', 'pending_operations': 0})
        self.assertEqual(second, first)
        self.assertEqual(close.await_count, 1)
        self.assertEqual(self.manager.get_colony(A1).lifecycle_status, 'failed')
        self.assertTrue(self.manager._cleanup_failures)
        self.assertNotIn('private-close', str(self.persisted))
    async def test_stop_preserves_open_positions_and_closes_feed(self):
        await self.create()
        controller = self.manager.get_colony(A1)
        probe = controller.live_probes[0]
        trade = TradeRecord(trade_id='trade', probe_id=probe.probe_id, pair='SOL/USDC', side='BUY', entry_price=100, amount=.01)
        probe.open_positions['SOL/USDC'] = trade
        await self.manager.stop_colony(A1)
        status = controller.status()
        self.assertEqual(status['status'], 'stopped')
        self.assertEqual(status['open_positions'], 1)
        self.assertTrue(status['requires_reconciliation'])
        self.assertIs(probe.open_positions['SOL/USDC'], trade)
        self.assertEqual(self.feed.closed, 1)
        self.assertNotIn(A1, self.manager._tasks)
    async def test_stop_finishes_current_event_batch(self):
        entered, release, writes = asyncio.Event(), asyncio.Event(), []
        async def tick():
            entered.set()
            await release.wait()
            writes.extend(['one', 'two'])
        self.tick.side_effect = tick
        await self.create()
        await entered.wait()
        task = asyncio.create_task(self.manager.stop_colony(A1))
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.assertEqual(self.feed.closed, 0)
        release.set()
        await task
        self.assertEqual(writes, ['one', 'two'])
    async def test_tick_failure_racing_stop_remains_failed(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def tick():
            entered.set()
            await release.wait()
            raise PersistenceError('insert_trade')
        self.tick.side_effect = tick
        await self.create()
        await entered.wait()
        task = asyncio.create_task(self.manager.stop_colony(A1))
        while not self.manager._locks[A1].locked(): await asyncio.sleep(0)
        release.set()
        with self.assertRaises(ColonyLifecycleError) as error: await task
        self.assertEqual(error.exception.code, 'persistence_failed')
        status = await self.failed()
        self.assertEqual(status['failure_code'], 'persistence_failed')
        self.assertNotIn('stopped', [s['status'] for s in self.persisted])
    async def test_repeated_cancelled_control_waiter_does_not_abandon_transition(self):
        await self.create()
        for name, target in (('pause', 'paused'), ('resume', 'running'), ('stop', 'stopped')):
            entered, release = asyncio.Event(), asyncio.Event()
            async def persist(status):
                if status['status'] == target:
                    entered.set()
                    await release.wait()
                self.persisted.append(dict(status))
            self.manager._persist[A1] = persist
            task = asyncio.create_task(getattr(self.manager, name + '_colony')(A1))
            await entered.wait()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError): await task
            status = self.manager.get_colony(A1).status()
            self.assertEqual(status['status'], target)
            self.assertTrue(status['state_persisted'])
    async def test_startup_cancellation_cleans_resources_and_records_failure(self):
        self.feed.gate = asyncio.Event()
        task = asyncio.create_task(self.create())
        while not self.feed.reads: await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual((await self.failed())['failure_code'], 'startup_cancelled')
    def mock_app(self, repo):
        self.offline_stack.enter_context(patch.object(app_module, 'colony_manager', self.manager))
        self.offline_stack.enter_context(patch.object(app_module, 'VonNeumannRepository', return_value=repo))
        self.offline_stack.enter_context(patch.object(app_module.ws_manager, 'broadcast_to_user', new=AsyncMock()))
    async def test_http_start_persists_parent_before_constructing_feed(self):
        order = []
        async def operation(name, *args, **kwargs): order.append(name)
        self.mock_app(SimpleNamespace(execute_async=AsyncMock(side_effect=operation)))
        def feed(mode):
            self.assertEqual(order, ['insert_colony'])
            return self.feed
        with patch.object(self.manager, '_create_feed', side_effect=feed):
            result = await app_module._start_colony(StartRequest(gen0_count=2), VerifiedUser(USER_A, int(time.time()) + 3600))
        self.assertEqual(result['status'], 'started')
        self.assertEqual(order, ['insert_colony', 'insert_probe', 'insert_probe', 'update_colony_status'])

    async def test_http_lifecycle_callback_persists_risk_evidence_without_unknown_fields(self):
        repo = SimpleNamespace(execute_async=AsyncMock())
        self.mock_app(repo)
        with patch.object(self.manager, 'create_colony', new=AsyncMock()) as create:
            await app_module._start_colony(StartRequest(), VerifiedUser(USER_A, int(time.time()) + 3600))
        risk = {'policy': 'initial-account-loss-v1', 'trip_id': A1, 'baseline_equity': 100.0}
        callback = create.await_args.kwargs['persist_status']
        await callback({'status': 'risk_halted', 'circuit_breaker': True,
                        'risk_control': risk, 'private_extra': 'not-persisted'})
        call = repo.execute_async.await_args
        self.assertEqual(call.args[0], 'update_colony_status')
        self.assertEqual(call.args[2], 'risk_halted')
        self.assertEqual(call.kwargs['details']['risk_control'], risk)
        self.assertTrue(call.kwargs['details']['circuit_breaker'])
        self.assertNotIn('private_extra', call.kwargs['details'])
    async def test_http_initial_write_failure_starts_nothing(self):
        self.mock_app(SimpleNamespace(execute_async=AsyncMock(side_effect=PersistenceError('insert_colony'))))
        with self.assertRaises(HTTPException) as error:
            await app_module._start_colony(StartRequest(), VerifiedUser(USER_A, int(time.time()) + 3600))
        self.assertEqual(error.exception.status_code, 503)
        self.assertFalse(error.exception.detail['state_persisted'])
        self.assertEqual(self.feed.reads, 0)
        # An unacknowledged insert may have committed. Keep its identity visible
        # without claiming a saved failure or discarding the reserved history.
        cid = error.exception.detail['colony_id']
        status = self.manager.get_colony(cid).status()
        self.assertEqual(status['status'], 'failed')
        self.assertEqual(status['failure_code'], 'persistence_failed')
        self.assertFalse(status['state_persisted'])
        self.assertTrue(status['requires_reconciliation'])
        self.assertEqual(self.manager.list_colonies(USER_B), [])
    async def test_cancelled_initial_insert_marks_committed_start_failed(self):
        entered, release, writes = asyncio.Event(), asyncio.Event(), []
        async def operation(name, *args, **kwargs):
            if name == 'insert_colony':
                entered.set()
                await release.wait()
            writes.append((name, args, kwargs))
        self.mock_app(SimpleNamespace(execute_async=AsyncMock(side_effect=operation)))
        task = asyncio.create_task(app_module._start_colony(StartRequest(), VerifiedUser(USER_A, int(time.time()) + 3600)))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        release.set()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual([w[0] for w in writes], ['insert_colony', 'update_colony_status'])
        cid = writes[0][1][0]
        self.assertEqual(writes[-1][1][1], 'failed')
        self.assertEqual(self.manager.get_colony(cid).status()['status'], 'failed')
        self.assertEqual(self.feed.reads, 0)

    async def test_lost_insert_ack_compensates_without_erasing_committed_configuration(self):
        db, committed = RecordingDB(), {}

        def execute(query):
            db.calls.append(query.call)
            if query.call['operation'] == 'insert':
                committed.update(query.call['fields'])
                raise RuntimeError('private-lost-reply-after-commit')
            # A real update patches these fields, retaining the original config.
            committed.update(query.call['fields'])
            return SimpleNamespace(data=[committed])

        with patch('vonneumann.db.repository.get_supabase', return_value=db):
            repo = VonNeumannRepository(USER_A, A1)
        self.mock_app(repo)
        with patch.object(app_module.uuid, 'uuid4', return_value=A1), \
                patch.object(RecordingQuery, 'execute', new=execute):
            with self.assertRaises(HTTPException) as error:
                await app_module._start_colony(StartRequest(), VerifiedUser(USER_A, int(time.time()) + 3600))
        self.assertEqual([c['operation'] for c in db.calls], ['insert', 'update'])
        self.assertNotIn('config', db.calls[1]['fields'])
        self.assertEqual(repo._colony_config, {})
        self.assertEqual(committed['config'], db.calls[0]['fields']['config'])
        self.assertEqual(committed['config']['search_seed'], '0')
        self.assertEqual(committed['status'], 'failed')
        self.assertEqual(error.exception.status_code, 503)
        self.assertTrue(error.exception.detail['state_persisted'])
        self.assertNotIn('accepted', error.exception.detail)
        self.assertEqual(self.feed.reads, 0)
        self.assertTrue(self.manager.get_colony(A1).state_persisted)

    async def test_market_failure_with_corrupt_valuation_still_persists_safe_terminal_state(self):
        async def fail_after_corruption():
            colony = self.manager.get_colony(A1)
            probe = colony.live_probes[0]
            asset = probe.genome.assets[0]
            probe.open_positions[asset] = TradeRecord(
                trade_id='corrupt-mark-trade', probe_id=probe.probe_id,
                pair=asset, side='BUY', entry_price=100.0, amount=5.0,
            )
            colony._latest_prices[asset] = float('nan')
            raise MarketValueError()

        self.tick.side_effect = fail_after_corruption
        await self.create()
        status = await self.failed()
        self.assertEqual(status['failure_code'], 'invalid_market_value')
        self.assertTrue(status['state_persisted'])
        self.assertFalse(status['valuation_available'])
        self.assertIsNone(status['active_capital'])
        self.assertIsNone(status['total_capital'])
        self.assertTrue(status['requires_reconciliation'])
        self.assertEqual(status['open_positions'], 1)
        self.assertEqual(self.persisted[-1]['status'], 'failed')
        self.assertEqual(self.persisted[-1]['failure_code'], 'invalid_market_value')
        self.assertEqual(self.published[-1]['failure_code'], 'invalid_market_value')
        json.dumps(status, allow_nan=False)
        json.dumps(self.persisted[-1], allow_nan=False)
        self.assertEqual(len(self.manager.list_colonies(USER_A)), 1)

if __name__ == '__main__': unittest.main()
