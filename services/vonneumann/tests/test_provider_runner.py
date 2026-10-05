"""Bounded explicit scheduling over the real offline provider controller."""
from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
import time
from unittest.mock import patch
import unittest

from tests import test_provider_controller as fixture
from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.provider_runner import ProviderPilotRunner, RunnerReport
    from vonneumann.core.provider_pilot import ProviderPilotLimits
    from vonneumann.db.command_repository import CommandAdmissionError, CommandBusy, UncertainCommand
    from vonneumann.db.transition_coordinator import PublicationError


class ProviderRunnerTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    # Reuse fixture helpers without inheriting and executing its 29 tests twice.
    identity = fixture.ProviderControllerTests.identity
    age = fixture.ProviderControllerTests.age
    allocation = fixture.ProviderControllerTests.allocation
    publisher = fixture.ProviderControllerTests.publisher
    ready = fixture.ProviderControllerTests.ready
    price = fixture.ProviderControllerTests.price
    spawn = fixture.ProviderControllerTests.spawn
    gate = fixture.ProviderControllerTests.gate
    entered = fixture.ProviderControllerTests.entered
    advance_to = fixture.ProviderControllerTests.advance_to
    history_values = fixture.ProviderControllerTests.history_values
    assert_unique_commands = fixture.ProviderControllerTests.assert_unique_commands

    def setUp(self):
        super().setUp()
        self.wall, self.mono = fixture.Clock(), fixture.Clock()
        self.wall.value, self.mono.value = fixture.END + 10.0, 1000.0
        clocks = SimpleNamespace(time=self.wall, monotonic=self.mono)
        self.enterContext(patch.object(fixture.jupiter_feed, 'time', clocks))
        self.enterContext(patch.object(fixture.birdeye_candles, 'time', clocks))
        self.enterContext(patch.object(fixture.solana_time, 'time', clocks))
        self.enterContext(patch.object(fixture.birdeye_candles, 'REQUEST_SPACING_SECONDS', 0))
        self.transport = fixture.CommittingTransport()
        self.repo = fixture.CommandRepository(self.transport, fixture.OWNER, fixture.RUN,
                                              fixture.WORKER, monotonic=self.mono)
        self.owner = self.controller = self.feed = self.runner = None
        self.serial = 61_000_000
        self.stop_id = self.identity()
        self.allocations, self.delivered, self.tasks, self.gates = [], [], [], []
        self.lookup_elapsed, self.delivery_hook = 1.0, None
        self.source_seconds = {}

    async def asyncTearDown(self):
        for gate in self.gates:
            gate.release.set()
        if self.runner is not None:
            self.runner.close_admission()
            try:
                await asyncio.wait_for(self.runner.settle(), 5)
            except (CommandAdmissionError, UncertainCommand, PublicationError, asyncio.CancelledError):
                pass
        await fixture.ProviderControllerTests.asyncTearDown(self)

    async def configured(self, *, ticks=2, interval=.01, monotonic=time.monotonic, **options):
        await self.ready(**options)
        for index in range(ticks):
            self.price(slot=fixture.SLOT + index)
        self.runner = ProviderPilotRunner(self.controller, interval_seconds=interval,
                                         max_ticks=ticks, monotonic=monotonic)
        return self.runner

    async def wait_stage(self, stage):
        for _ in range(2000):
            if self.runner.pending_stage == stage:
                return
            await asyncio.sleep(0)
        self.fail(f'Runner did not enter {stage}')

    async def test_explicit_finite_run_is_sequential_and_does_not_automatically_stop(self):
        await self.configured(ticks=3)
        report = await self.runner.run()
        self.assertIs(type(report), RunnerReport)
        self.assertEqual((report.status, report.ticks_completed), ('complete', 3))
        self.assertEqual([row.kind for row in report.reports], ['bootstrap', 'tick', 'tick', 'tick'])
        self.assertEqual([row.quote_sequence for row in report.reports], [0, 1, 2, 3])
        self.assertFalse(report.stop_requested)
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'running')
        self.assertNotIn(self.stop_id, self.transport.ledger)
        self.assertEqual(self.feed.api_call_count, 3)
        self.assertFalse(self.runner.busy)
        self.assertIs(self.runner.last_report, report)
        self.assert_unique_commands()
        with self.assertRaises(CommandAdmissionError):
            await self.runner.run()

    async def test_constructor_requires_explicit_finite_interval_and_bounded_integer_ticks(self):
        await self.ready(limits=ProviderPilotLimits(max_quotes=2))
        for interval in (True, 0, -1, float('nan'), float('inf'), '1', 120, 3601):
            with self.subTest(interval=repr(interval)), self.assertRaises(CommandAdmissionError):
                ProviderPilotRunner(self.controller, interval_seconds=interval, max_ticks=1)
        for ticks in (True, 0, -1, 1.0, 3):
            with self.subTest(ticks=ticks), self.assertRaises(CommandAdmissionError):
                ProviderPilotRunner(self.controller, interval_seconds=.01, max_ticks=ticks)
        await self.controller.bootstrap()
        with self.assertRaises(CommandAdmissionError):
            ProviderPilotRunner(self.controller, interval_seconds=.01, max_ticks=1)

    async def test_interval_must_remain_below_an_explicit_short_controller_lease(self):
        await self.ready()
        self.controller = fixture.module.ProviderPilotController(self.owner, self.feed,
            self.publisher, self.allocation, lease_seconds=2,
            wall_clock=self.wall, monotonic=self.mono)
        for interval in (2, 3):
            with self.assertRaises(CommandAdmissionError):
                ProviderPilotRunner(self.controller, interval_seconds=interval, max_ticks=1)
        self.runner = ProviderPilotRunner(self.controller, interval_seconds=.01, max_ticks=1)

    async def test_cancel_during_long_wait_wakes_and_drains_without_another_price_request(self):
        await self.configured(ticks=2, interval=60)
        task = self.spawn(self.runner.run()); await self.wait_stage('wait')
        count = self.feed.api_call_count
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.controller.accepting)
        report = await asyncio.wait_for(self.runner.settle(), 2)
        self.assertEqual((report.status, report.ticks_completed), ('drained', 1))
        self.assertEqual(self.feed.api_call_count, count)
        self.assertNotIn(self.stop_id, self.transport.ledger)

    async def test_cancel_during_price_read_finishes_original_capture_but_admits_no_protection(self):
        await self.configured(ticks=2)
        gate = fixture.ReadGate(fixture.price_body({fixture.SOL: '101'}, slot=fixture.SLOT))
        self.gates.append(gate); self.feed._session.responses[0] = gate
        task = self.spawn(self.runner.run()); await self.entered(gate)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(gate.cancelled)
        self.assertTrue(self.runner.busy)
        with self.assertRaises(CommandBusy):
            await self.runner.run()
        gate.release.set()
        report = await self.runner.settle()
        self.assertEqual(report.status, 'drained')
        self.assertEqual(self.owner.installed_state.to_dict()['source']['quote_sequence'], 0)
        self.assertEqual(self.transport.count('commit_command'), 1)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertNotIn(self.stop_id, self.transport.ledger)

    async def test_cancel_during_bootstrap_history_never_admits_bootstrap_or_first_tick(self):
        gate = fixture.ReadGate(fixture.response_bytes()); self.gates.append(gate)
        await self.configured(ticks=2, candle_response=gate)
        task = self.spawn(self.runner.run()); await self.entered(gate)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        gate.release.set()
        report = await self.runner.settle()
        self.assertEqual(report.status, 'drained')
        self.assertEqual(report.ticks_completed, 0)
        self.assertIsNone(self.owner.installed_state)
        self.assertEqual(self.transport.count('commit_command'), 0)
        self.assertEqual(self.feed.api_call_count, 0)
        self.assertEqual(self.allocations, [])

    async def test_cancel_during_committed_bootstrap_retains_publication_without_first_tick(self):
        await self.configured(ticks=2)
        gate = self.gate('commit_command')
        task = self.spawn(self.runner.run()); await self.entered(gate)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(gate.cancelled)
        gate.release.set()
        report = await self.runner.settle()
        self.assertEqual(report.status, 'drained')
        self.assertEqual(report.ticks_completed, 0)
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'running')
        self.assertEqual(len(self.delivered), 9)
        self.assertEqual(self.feed.api_call_count, 0)

    async def test_cancelled_caller_completed_result_remains_owned_until_settle(self):
        await self.configured(ticks=2, interval=60)
        task = self.spawn(self.runner.run()); await self.wait_stage('wait')
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        for _ in range(1000):
            if self.runner.last_report is not None:
                break
            await asyncio.sleep(0)
        self.assertTrue(self.runner.busy)
        with self.assertRaises(CommandBusy):
            await self.runner.run()
        expected = self.runner.last_report
        self.assertIs(await self.runner.settle(), expected)
        self.assertFalse(self.runner.busy)

    async def test_request_stop_before_run_does_not_create_or_stop_unsubmitted_state(self):
        await self.configured(ticks=2)
        self.runner.request_stop()
        report = await self.runner.run()
        self.assertEqual(report.status, 'drained')
        self.assertTrue(report.stop_requested)
        self.assertEqual(report.reports, ())
        self.assertIsNone(self.owner.installed_state)
        self.assertEqual(self.transport.count('commit_command'), 0)
        self.assertEqual(self.allocations, [])

    async def test_request_stop_during_wait_wakes_and_uses_reserved_identity_once(self):
        await self.configured(ticks=2, interval=60)
        task = self.spawn(self.runner.run()); await self.wait_stage('wait')
        before = self.owner.installed_state.to_dict()
        allocations = len(self.allocations)
        self.runner.request_stop()
        report = await asyncio.wait_for(task, 2)
        self.assertEqual(report.status, 'stopped')
        self.assertEqual(report.ticks_completed, 1)
        self.assertTrue(report.stop_requested)
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')
        for field in ('positions', 'accounts', 'reserve'):
            self.assertEqual(self.owner.installed_state.to_dict()[field], before[field])
        self.assertEqual(len(self.allocations), allocations)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertIn(self.stop_id, self.transport.ledger)
        count = self.transport.count('commit_command')
        self.runner.request_stop()
        self.assertIs(await self.runner.settle(), report)
        self.assertEqual(self.transport.count('commit_command'), count)

    async def test_request_stop_during_committed_tick_settles_original_before_terminal_command(self):
        await self.configured(ticks=2)
        async def unchanged(result, _args):
            return result
        self.transport.fault('commit_command', unchanged)  # bootstrap
        gate = self.gate('commit_command')  # first protection
        task = self.spawn(self.runner.run()); await self.entered(gate)
        self.runner.request_stop()
        with self.assertRaises(CommandBusy):
            await self.runner.run()
        gate.release.set()
        report = await task
        self.assertEqual(report.status, 'stopped')
        self.assertEqual(report.ticks_completed, 1)
        self.assertFalse(report.reports[1].decision_committed)
        self.assertEqual([row.kind for row in report.reports], ['bootstrap', 'tick', 'stop'])
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertEqual(self.transport.count('commit_command'), 3)
        self.assert_unique_commands()

    async def test_lost_ack_returns_visible_fault_and_explicit_settle_attempts_original_once(self):
        await self.configured(ticks=1)
        self.transport.fault('commit_command', OSError('bootstrap commit reply lost'))
        with self.assertRaises(UncertainCommand):
            await self.runner.run()
        original = self.owner.pending_command
        self.assertEqual(self.feed.api_call_count, 0)
        self.assertEqual(self.transport.count('get_command'), 0)
        self.transport.fault('get_command', None)
        pending = await self.runner.settle()
        self.assertEqual(pending.status, 'pending')
        self.assertEqual(pending.ticks_completed, 0)
        self.assertIs(self.owner.pending_command, original)
        self.assertEqual(self.transport.count('get_command'), 1)
        self.assertEqual(self.feed.api_call_count, 0)
        report = await self.runner.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(report.ticks_completed, 1)
        self.assertEqual(len(report.reports), 2)
        ids = [args['command_id'] for name, args in self.transport.calls if name == 'commit_command']
        self.assertEqual(ids.count(original.command_id), 1)
        self.assert_unique_commands()

    async def test_publication_fault_never_retries_until_explicit_settle(self):
        await self.configured(ticks=1)
        self.transport.fault('acknowledge_event', OSError('delivery ack lost'))
        with self.assertRaises(PublicationError):
            await self.runner.run()
        event_id = self.delivered[0]['event_id']
        self.assertEqual(self.feed.api_call_count, 0)
        count = self.transport.count('acknowledge_event')
        await asyncio.sleep(.03)
        self.assertEqual(self.transport.count('acknowledge_event'), count)
        report = await self.runner.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual([row['event_id'] for row in self.delivered].count(event_id), 1)
        self.assertEqual(report.ticks_completed, 1)

    async def test_stop_intent_survives_unknown_commit_without_new_command_or_refetch(self):
        await self.configured(ticks=2)
        self.transport.fault('commit_command', OSError('bootstrap reply lost'))
        with self.assertRaises(UncertainCommand):
            await self.runner.run()
        self.runner.request_stop()
        self.transport.fault('get_command', None)
        pending = await self.runner.settle()
        self.assertEqual(pending.status, 'pending')
        self.assertTrue(pending.stop_requested)
        self.assertEqual(self.feed.api_call_count, 0)
        report = await self.runner.settle()
        self.assertEqual(report.status, 'stopped')
        self.assertEqual(self.transport.count('commit_command'), 2)
        self.assertEqual(self.feed.api_call_count, 0)
        self.assert_unique_commands()

    async def test_pacing_clock_failure_cannot_block_original_commit_or_reserved_stop(self):
        clock = fixture.Clock()
        await self.configured(ticks=2, monotonic=clock)
        self.transport.fault('commit_command', OSError('bootstrap reply lost'))
        with self.assertRaises(UncertainCommand):
            await self.runner.run()
        clock.value -= 1
        self.runner.request_stop()
        report = await self.runner.settle()
        self.assertEqual(report.status, 'stopped')
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')
        self.assertEqual(len(self.transport.acknowledged), len(self.transport.events))
        self.assertEqual(len(self.delivered), len(self.transport.events))
        self.assertEqual(self.feed.api_call_count, 0)

    async def test_backward_pacing_clock_during_wait_closes_future_ticks(self):
        clock = fixture.Clock()
        await self.configured(ticks=2, interval=.03, monotonic=clock)
        task = self.spawn(self.runner.run()); await self.wait_stage('wait')
        clock.value -= 1
        with self.assertRaises(CommandAdmissionError):
            await task
        report = await self.runner.settle()
        self.assertEqual(report.status, 'drained')
        self.assertEqual(report.ticks_completed, 1)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertNotIn(self.stop_id, self.transport.ledger)

    async def test_delayed_tick_schedules_next_interval_from_completion_without_catchup(self):
        await self.configured(ticks=3, interval=.04)
        starts, finishes = [], []
        original = self.controller.tick
        async def measured():
            starts.append(asyncio.get_running_loop().time())
            result = await original()
            if len(starts) == 1:
                await asyncio.sleep(.09)
            finishes.append(asyncio.get_running_loop().time())
            return result
        with patch.object(self.controller, 'tick', measured):
            report = await self.runner.run()
        self.assertEqual(report.ticks_completed, 3)
        self.assertGreaterEqual(starts[1] - finishes[0], .03)
        self.assertGreaterEqual(starts[2] - finishes[1], .03)
        self.assert_unique_commands()

    async def test_cross_loop_settlement_never_consumes_original_runner_task(self):
        await self.configured(ticks=2)
        gate = fixture.ReadGate(fixture.price_body({fixture.SOL: '101'}, slot=fixture.SLOT))
        self.gates.append(gate); self.feed._session.responses[0] = gate
        task = self.spawn(self.runner.run()); await self.entered(gate)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        retained = self.runner._task
        with self.assertRaises(CommandAdmissionError):
            await asyncio.to_thread(lambda: asyncio.run(self.runner.settle()))
        self.assertIs(self.runner._task, retained)
        self.assertFalse(retained.done())
        gate.release.set()
        report = await self.runner.settle()
        self.assertEqual(report.status, 'drained')
        self.assertEqual(self.feed.api_call_count, 1)

    async def test_creation_failure_and_early_owned_cancel_leave_no_bootstrap_to_replay(self):
        await self.configured(ticks=1)
        with patch.object(asyncio, 'create_task', side_effect=RuntimeError('scheduler unavailable')):
            with self.assertRaises(CommandAdmissionError):
                await self.runner.run()
        report = await self.runner.settle()
        self.assertEqual(report.status, 'drained')
        self.assertEqual(self.transport.count('commit_command'), 0)
        self.assertEqual(self.allocations, [])

    async def test_owned_task_cancel_before_first_instruction_settles_without_provider_requests(self):
        await self.configured(ticks=1)
        create = asyncio.create_task
        def cancelled(coroutine, *args, **kwargs):
            task = create(coroutine, *args, **kwargs)
            task.cancel()
            return task
        with patch.object(asyncio, 'create_task', cancelled):
            with self.assertRaises(asyncio.CancelledError):
                await self.runner.run()
        report = await self.runner.settle()
        self.assertEqual(report.status, 'drained')
        self.assertEqual(self.transport.count('commit_command'), 0)
        self.assertEqual(self.feed.api_call_count, 0)
        self.assertEqual(self.allocations, [])

    async def test_owned_runner_interruption_still_settles_busy_original_controller(self):
        await self.configured(ticks=2)
        gate = fixture.ReadGate(fixture.price_body({fixture.SOL: '101'}, slot=fixture.SLOT))
        self.gates.append(gate); self.feed._session.responses[0] = gate
        task = self.spawn(self.runner.run()); await self.entered(gate)
        self.runner._task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(gate.cancelled)
        self.assertTrue(self.runner.busy)
        settlement = self.spawn(self.runner.settle())
        await asyncio.sleep(0)
        self.assertFalse(settlement.done())
        gate.release.set()
        report = await settlement
        self.assertEqual(report.status, 'drained')
        self.assertEqual(self.transport.count('commit_command'), 1)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertFalse(self.runner.busy)

    async def test_pre_admission_failure_cannot_count_previous_same_kind_report_twice(self):
        await self.configured(ticks=2)
        original = self.controller.tick
        calls = 0
        async def rejection():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise CommandAdmissionError('rejected before controller operation admission')
            return await original()
        with patch.object(self.controller, 'tick', rejection):
            with self.assertRaises(CommandAdmissionError):
                await self.runner.run()
        count = self.transport.count('commit_command')
        report = await self.runner.settle()
        self.assertEqual(report.status, 'closed')
        self.assertEqual(report.ticks_completed, 1)
        self.assertEqual([row.kind for row in report.reports], ['bootstrap', 'tick'])
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(self.feed.api_call_count, 1)

    async def test_explicit_stop_after_finite_completion_is_separate_and_report_is_frozen(self):
        await self.configured(ticks=1)
        report = await self.runner.run()
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            report.status = 'forged'
        self.runner.request_stop()
        stopped = await self.runner.settle()
        self.assertEqual(stopped.status, 'stopped')
        self.assertEqual([row.kind for row in stopped.reports], ['bootstrap', 'tick', 'stop'])
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')
        self.assert_unique_commands()
