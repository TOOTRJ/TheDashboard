"""Offline whole-operation ownership through real literal provider adapters.

Only HTTP and the command ledger/outbox are fakes. The controller composes the
actual Jupiter/Birdeye adapters, immutable provider records, strict paper pilot
owner, exact lifecycle candidates and command/receipt validation.
"""
from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
import time as real_time
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from uuid import UUID

from tests.security_support import OfflineTestMixin, deny_network
from tests.test_birdeye_candles import Response as CandleResponse, Session as CandleSession
from tests.test_exact_provider_feeds import price_body
from tests.test_feed_reliability import Response as PriceResponse, Session as PriceSession
from tests.test_provider_windows import END, response_bytes
from tests.test_provider_contract import EPOCH
from tests.test_exact_rehearsal import OWNER, RUN, WORKER
from tests.test_transition_coordinator import Clock, CommittingTransport, Gate

with deny_network():
    from vonneumann.core import exact_lifecycle as kernel
    from vonneumann.core import provider_lifecycle as life
    from vonneumann.core import provider_controller as module
    from vonneumann.core import provider_acquisition
    from vonneumann.core.provider_pilot import ProviderPilotLimits
    from vonneumann.db.command_protocol import PreparedCommand
    from vonneumann.db.command_repository import (
        CommandAdmissionError, CommandBusy, CommandRepository, UncertainCommand,
    )
    from vonneumann.db.provider_pilot_owner import ProviderPilotOwner, PilotAdmissionRefused
    from vonneumann.db.transition_coordinator import PublicationError
    from vonneumann.db.rehearsal_owner import OperationalAdmissionError
    from vonneumann.market import birdeye_candles, jupiter_feed, solana_time


SOL = 'SOL/USDC'
SECRET = 'offline-controller-secret-must-not-leak'
SLOT = 345_678_901


class ReadGate(PriceResponse):
    """Hold a real provider body before its parser receives the first byte."""
    def __init__(self, raw):
        super().__init__(raw)
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.cancelled = False

    async def iter_chunked(self, size):
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        async for chunk in super().iter_chunked(size):
            yield chunk


class ControllerSession(PriceSession):
    """Return strict mainnet JSON-RPC responses through the actual resolver."""
    def __init__(self, fixture):
        super().__init__()
        self.fixture = fixture

    def post(self, url, **kwargs):
        self.rpc_calls.append((url, kwargs))
        payload = kwargs['json']
        if payload['method'] == 'getGenesisHash':
            result = solana_time.MAINNET_GENESIS_HASH
        elif payload['method'] == 'getBlockTime':
            slot, = payload['params']
            result = self.fixture.source_seconds.setdefault(slot, int(self.fixture.wall.value) - 2)
            self.fixture.age(self.fixture.lookup_elapsed)
        else:
            raise AssertionError('Controller requested an unexpected Solana RPC method')
        return PriceResponse({'jsonrpc': '2.0', 'id': payload['id'], 'result': result})


class ProviderControllerTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.wall, self.mono = Clock(), Clock()
        self.wall.value, self.mono.value = END + 10.0, 1000.0
        clocks = SimpleNamespace(time=self.wall, monotonic=self.mono)
        self.enterContext(patch.object(jupiter_feed, 'time', clocks))
        self.enterContext(patch.object(birdeye_candles, 'time', clocks))
        self.enterContext(patch.object(solana_time, 'time', clocks))
        self.enterContext(patch.object(birdeye_candles, 'REQUEST_SPACING_SECONDS', 0))
        self.transport = CommittingTransport()
        self.repo = CommandRepository(self.transport, OWNER, RUN, WORKER, monotonic=self.mono)
        self.owner = self.controller = self.feed = None
        self.serial = 51_000_000
        self.stop_id = self.identity()
        self.allocations, self.delivered, self.tasks, self.gates = [], [], [], []
        self.lookup_elapsed = 1.0
        self.delivery_hook = None
        self.source_seconds = {}

    async def asyncTearDown(self):
        for gate in self.gates:
            gate.release.set()
        if self.tasks:
            await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), 5)
        if self.controller is not None:
            try:
                await asyncio.wait_for(self.controller.settle(), 5)
            except (CommandAdmissionError, UncertainCommand, PublicationError):
                pass
        if self.feed is not None:
            await self.feed.close()

    def identity(self):
        self.serial += 1
        return str(UUID(int=self.serial))

    def age(self, amount):
        self.wall.value += amount
        self.mono.value += amount

    def allocation(self, kind, generation):
        if kind == 'bootstrap':
            ids = tuple(self.identity() for _ in range(9))
            names = tuple((generation, f'Controller-{generation}-{index}') for index in range(8))
        elif kind in ('protect', 'protective', 'decision', 'decide'):
            ids = tuple(self.identity() for _ in range(9))
            names = tuple((generation, f'Controller-{generation}-{index}') for index in range(8))
        else:
            ids, names = (), ()
        result = module.CommandAllocation(self.identity(), ids, names)
        self.allocations.append((kind, generation, result))
        return result

    async def publisher(self, row):
        self.delivered.append(row)
        if self.delivery_hook is not None:
            await self.delivery_hook(row)

    async def ready(self, *, lookup_elapsed=1, limits=None, publisher=None, candle_response=None):
        config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig(
            'genetic_algorithm', OWNER, RUN, asset='SOL/USD'), EPOCH)
        await self.repo.submit(PreparedCommand.create(OWNER, RUN, WORKER,
            config.run_configuration(), config.initial_cash, command_id=self.identity()))
        options = {} if limits is None else {'limits': limits}
        self.owner = ProviderPilotOwner(self.repo, self.transport, config,
            stop_command_id=self.stop_id, wall_clock=self.wall, monotonic=self.mono, **options)
        self.feed = jupiter_feed.JupiterFeed(api_key=SECRET, birdeye_api_key=SECRET,
            rpc_url='https://rpc.example.test/?key=' + SECRET)
        self.feed._session = ControllerSession(self)
        self.feed._candles._session = CandleSession(
            CandleResponse(response_bytes()) if candle_response is None else candle_response)
        self.lookup_elapsed = lookup_elapsed

        self.controller = module.ProviderPilotController(self.owner, self.feed,
            self.publisher if publisher is None else publisher, self.allocation,
            wall_clock=self.wall, monotonic=self.mono)
        return self.controller

    async def bootstrapped(self, **options):
        await self.ready(**options)
        report = await self.controller.bootstrap()
        self.assertEqual(report.status, 'complete')
        return report

    def price(self, *, slot=SLOT, value='101.000000000000000001', response=None):
        response = PriceResponse(price_body({SOL: value}, slot=slot)) if response is None else response
        self.feed._session.responses.append(response)
        return response

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
        await asyncio.wait_for(gate.entered.wait(), 5)

    def assert_no_legacy_history(self):
        adapter = self.feed._candles
        self.assertEqual(adapter._cutoffs, {})
        self.assertEqual(adapter._first_starts, {})
        self.assertEqual(adapter._cache, {})
        self.assertEqual(adapter._exact_cache, {})
        self.assertEqual(adapter._accepted_fingerprints, {})

    def assert_unique_commands(self):
        ids = [args['command_id'] for name, args in self.transport.calls if name == 'commit_command']
        self.assertEqual(len(ids), len(set(ids)))

    async def advance_to(self, wall):
        while self.wall.value < wall:
            self.age(min(20, wall - self.wall.value))
            await self.controller.heartbeat()

    def history_values(self, *, end=END, seed=False):
        count = 915 if seed else 30
        values = ['100'] * 900 + ['80'] * 15 if seed else ['80'] * 15 + ['150'] * 15
        changes = {index: {field: value for field in ('o', 'h', 'l', 'c')}
                   for index, value in enumerate(values)}
        # response_bytes serializes strings as strings; provide numeric tokens
        # explicitly so these are exact provider numbers throughout parsing.
        from tests.test_exact_provider_feeds import Number
        changes = {index: {field: Number(value) for field, value in fields.items()}
                   for index, fields in changes.items()}
        return response_bytes(end, count=count, changes=changes)

    async def positions_open(self):
        await self.bootstrapped(candle_response=CandleResponse(self.history_values(seed=True)))
        self.price(value='80'); await self.controller.tick()
        await self.advance_to(END + 910)
        self.feed._candles._session.responses.append(CandleResponse(
            self.history_values(end=END + 900)))
        self.price(slot=SLOT + 1, value='150')
        report = await self.controller.tick()
        self.assertTrue(report.decision_committed)
        data = self.owner.installed_state.to_dict()
        self.assertEqual(data['source']['bars'][-1][0], END + 900)
        self.assertTrue(any(member['pending'] is not None for member in data['engine']['members']))
        self.age(1); self.price(slot=SLOT + 2, value='150')
        self.assertTrue((await self.controller.tick()).decision_committed)
        self.assertTrue(any(not position['closed']
                            for position in self.owner.installed_state.to_dict()['positions']))

    async def test_literal_adapters_bootstrap_and_first_tick_install_complete_exact_state(self):
        report = await self.bootstrapped()
        self.assertEqual((report.kind, report.revision, report.quote_sequence), ('bootstrap', 2, 0))
        state = self.owner.installed_state.to_dict()
        self.assertEqual(state['engine']['ema']['count'], 61)
        self.assertEqual(len(state['accounts']), 8)
        self.assertEqual(len(self.feed._candles._session.calls), 1)
        self.assertEqual(len(self.delivered), 9)
        self.price()
        report = await self.controller.tick()
        state = self.owner.installed_state.to_dict()
        self.assertEqual(report.kind, 'tick')
        self.assertEqual(report.status, 'complete')
        self.assertTrue(report.decision_committed)
        self.assertEqual((report.revision, report.quote_sequence), (4, 1))
        self.assertEqual(state['source']['last_quote']['quote']['price'], '101.000000000000000001')
        self.assertEqual(state['engine']['cohort']['phase'], 'evaluating')
        self.assertEqual(self.transport.count('commit_command'), 3)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertEqual([options['json']['method'] for _, options in self.feed._session.rpc_calls],
                         ['getGenesisHash', 'getBlockTime'])
        self.assertEqual(self.feed._candles.api_call_count, 1)
        self.assertIsNone(self.controller.pending_stage)
        self.assertFalse(self.controller.busy)
        self.assertTrue(self.controller.accepting)
        self.assert_no_legacy_history()
        self.assert_unique_commands()

    async def test_ordinary_quote_runs_protection_without_empty_decision_allocation_or_history(self):
        await self.bootstrapped(); self.price(); await self.controller.tick()
        self.age(1); self.price(slot=SLOT + 1)
        allocation_count = len(self.allocations)
        command_count = self.transport.count('commit_command')
        history_count = self.feed._candles.api_call_count
        report = await self.controller.tick()
        self.assertEqual(report.status, 'complete')
        self.assertFalse(report.decision_committed)
        self.assertEqual(report.quote_sequence, 2)
        self.assertEqual(len(self.allocations), allocation_count + 1)
        self.assertEqual(self.transport.count('commit_command'), command_count + 1)
        self.assertEqual(self.feed._candles.api_call_count, history_count)
        self.assert_no_legacy_history()

    async def test_literal_increment_signal_fill_and_controls_preserve_real_open_positions(self):
        await self.positions_open()
        before = self.owner.installed_state.to_dict()
        self.assertEqual(before['engine']['ema']['count'], 62)
        self.assertEqual(self.feed._candles.api_call_count, 2)
        request = self.feed._candles._session.calls[-1][1]['params']
        self.assertEqual((request['time_from'], request['time_to']), (END - 900, END + 900))
        paused = await self.controller.control('pause')
        self.assertEqual(paused.status, 'complete')
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'paused')
        for field in ('positions', 'accounts', 'reserve'):
            self.assertEqual(self.owner.installed_state.to_dict()[field], before[field])
        await self.controller.stop()
        for field in ('positions', 'accounts', 'reserve'):
            self.assertEqual(self.owner.installed_state.to_dict()[field], before[field])
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')
        self.assert_no_legacy_history()
        self.assert_unique_commands()

    async def test_protective_delivery_lost_ack_retains_same_tick_and_never_refetches(self):
        await self.positions_open(); self.age(1); self.price(slot=SLOT + 3, value='180')
        self.transport.fault('acknowledge_event', OSError('protective delivery ack lost'))
        delivery_count = len(self.delivered)
        with self.assertRaises(PublicationError):
            await self.controller.tick()
        original = self.delivered[-1]['event_id']
        command_count, allocation_count = self.transport.count('commit_command'), len(self.allocations)
        price_count, history_count = self.feed.api_call_count, self.feed._candles.api_call_count
        self.assertIsNotNone(self.controller.pending_stage)
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual([row['event_id'] for row in self.delivered[delivery_count:]].count(original), 1)
        self.assertTrue(all(position['closed']
                            for position in self.owner.installed_state.to_dict()['positions']))
        self.assertEqual(self.transport.count('commit_command'), command_count)
        self.assertEqual(len(self.allocations), allocation_count)
        self.assertEqual((self.feed.api_call_count, self.feed._candles.api_call_count),
                         (price_count, history_count))

    async def test_slow_protective_publication_expires_source_without_rewriting_committed_closes(self):
        await self.positions_open()
        delayed = False
        async def slow(row):
            nonlocal delayed
            if not delayed:
                delayed = True
                self.age(5)
        self.delivery_hook = slow
        self.age(1); self.price(slot=SLOT + 3, value='180')
        count = self.transport.count('commit_command')
        report = await self.controller.tick()
        self.assertEqual(report.status, 'closed')
        self.assertFalse(report.decision_committed)
        self.assertEqual(self.transport.count('commit_command'), count + 1)
        self.assertTrue(all(position['closed']
                            for position in self.owner.installed_state.to_dict()['positions']))
        self.assertFalse(self.controller.accepting)
        self.assertTrue(delayed)

    async def test_same_second_capture_waits_inside_tick_without_refetch_or_reanchoring(self):
        await self.bootstrapped(lookup_elapsed=0)
        self.age(.25); self.price()
        waits = []
        async def boundary(seconds):
            waits.append(seconds)
            self.age(seconds)
        with patch.object(module.asyncio, 'sleep', side_effect=boundary):
            report = await self.controller.tick()
        capture = self.feed._captures[SOL]
        self.assertEqual(waits, [.75])
        self.assertEqual(report.status, 'complete')
        self.assertEqual(report.quote_sequence, 1)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertIs(self.feed._captures[SOL], capture)
        frame = self.owner.installed_state.to_dict()['source']['last_quote']
        self.assertEqual(frame['quote']['document']['response_sha256'], capture.record.document.response_sha256)
        self.assertEqual(frame['quote']['document']['received_wall_us'], int((END + 10.25) * 1_000_000))

    async def test_early_timer_wakeup_waits_for_actual_boundary_with_same_receipt(self):
        await self.bootstrapped(lookup_elapsed=0)
        self.age(.25); self.price()
        waits = []
        async def early_boundary(seconds):
            waits.append(seconds)
            self.age(seconds - .00025 if len(waits) == 1 else seconds)
        with patch.object(module.asyncio, 'sleep', side_effect=early_boundary):
            report = await self.controller.tick()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(report.quote_sequence, 1)
        self.assertEqual(len(waits), 2)
        self.assertGreaterEqual(waits[1], .001)
        self.assertEqual(self.feed.api_call_count, 1)
        capture = self.feed._captures[SOL]
        frame = self.owner.installed_state.to_dict()['source']['last_quote']
        self.assertEqual(frame['quote']['document']['response_sha256'],
                         capture.record.document.response_sha256)
        self.assertEqual(frame['quote']['document']['received_wall_us'],
                         int((END + 10.25) * 1_000_000))
        self.assertGreaterEqual(frame['decision_second'], END + 11)
        self.assertIsNone(self.controller.last_failure)

    async def test_shutdown_after_early_wakeup_does_not_wait_again_or_submit_protection(self):
        await self.bootstrapped(lookup_elapsed=0)
        self.age(.25); self.price()
        count = self.transport.count('commit_command')
        waits = []
        async def early_stop(seconds):
            waits.append(seconds); self.age(seconds - .00025)
            self.controller.close_admission()
        with patch.object(module.asyncio, 'sleep', side_effect=early_stop):
            report = await self.controller.tick()
        self.assertEqual(report.status, 'drained')
        self.assertEqual(len(waits), 1)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertEqual(self.transport.count('commit_command'), count)

    async def test_repeated_early_wakeups_have_finite_budget_without_refetch_or_submission(self):
        await self.bootstrapped(lookup_elapsed=0)
        self.age(.25); self.price()
        count = self.transport.count('commit_command')
        waits = []
        async def tiny_progress(seconds):
            waits.append(seconds)
            self.age(seconds - .00025 if len(waits) == 1 else .000001)
        with patch.object(module.asyncio, 'sleep', side_effect=tiny_progress):
            with self.assertRaises(OperationalAdmissionError):
                await self.controller.tick()
        self.assertEqual(len(waits), module.MAX_RECEIPT_BOUNDARY_WAKEUPS)
        self.assertEqual(self.controller.last_failure['admission_code'], 'receipt_wait_budget')
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertFalse(self.controller.accepting)

    async def test_suspended_receipt_wait_rejects_expired_original_without_refetch(self):
        await self.bootstrapped(lookup_elapsed=0)
        self.age(.25); self.price()
        count = self.transport.count('commit_command')
        async def oversleep(_seconds): self.age(5)
        with patch.object(module.asyncio, 'sleep', side_effect=oversleep):
            with self.assertRaises(CommandAdmissionError): await self.controller.tick()
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertFalse(self.controller.accepting)

    async def test_shutdown_during_receipt_wait_prevents_protective_submission(self):
        await self.bootstrapped(lookup_elapsed=0)
        self.age(.25); self.price()
        count = self.transport.count('commit_command')
        async def drain(seconds):
            self.controller.close_admission()
            self.age(seconds)
        with patch.object(module.asyncio, 'sleep', side_effect=drain):
            report = await self.controller.tick()
        self.assertEqual(report.status, 'drained')
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(self.feed.api_call_count, 1)

    async def test_stalled_actual_clock_does_not_admit_or_reanchor_fractional_receipt(self):
        await self.bootstrapped(lookup_elapsed=0)
        self.age(.25); self.price()
        count = self.transport.count('commit_command')
        async def stalled(_seconds): pass
        with patch.object(module.asyncio, 'sleep', side_effect=stalled):
            with self.assertRaises(OperationalAdmissionError): await self.controller.tick()
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertFalse(self.controller.accepting)
        self.assertEqual(self.controller.last_failure['admission_code'],
                         'receipt_clock_not_advanced')
        self.assertEqual(self.controller.last_failure['stage'], 'capture')
        self.assertIsNone(self.controller.last_failure['acquisition'])

    async def test_unchanged_snapshot_is_deferred_without_refreshing_installed_age_anchor(self):
        await self.bootstrapped(); self.price(); await self.controller.tick()
        before = self.owner.installed_state.to_dict()['source']
        # A new HTTP receipt of the same block retains the resolver's original
        # source second. It cannot renew the owner's accepted age anchor.
        self.age(.25); self.price()
        count, allocations = self.transport.count('commit_command'), len(self.allocations)
        report = await self.controller.tick()
        self.assertEqual(report.status, 'deferred')
        self.assertEqual(self.owner.installed_state.to_dict()['source'], before)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(len(self.allocations), allocations)
        self.assertEqual(self.feed.api_call_count, 2)

    async def test_repeated_snapshot_after_normal_wait_does_not_reuse_consumed_ticket(self):
        await self.bootstrapped(); self.price(); await self.controller.tick()
        before = self.owner.installed_state.to_dict()['source']
        self.age(7); self.price()
        count = self.transport.count('commit_command')
        report = await self.controller.tick()
        self.assertEqual(report.status, 'deferred')
        self.assertEqual(self.owner.installed_state.to_dict()['source'], before)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertTrue(self.controller.accepting)

    async def test_cancelled_caller_during_price_read_retains_whole_tick_and_rejects_overlap(self):
        await self.bootstrapped()
        gate = ReadGate(price_body({SOL: '101'}, slot=SLOT))
        self.gates.append(gate); self.price(response=gate)
        task = self.spawn(self.controller.tick())
        await self.entered(gate)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(gate.cancelled)
        self.assertTrue(self.controller.busy)
        for operation in (self.controller.tick, lambda: self.controller.control('pause'), self.controller.heartbeat):
            with self.assertRaises(CommandBusy):
                await operation()
        gate.release.set()
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(report.quote_sequence, 1)
        self.assertTrue(report.decision_committed)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertIs(self.controller.last_report, report)
        self.assert_unique_commands()

    async def test_cancelled_caller_during_committed_reply_keeps_same_tick_until_settlement(self):
        await self.bootstrapped(); self.price()
        gate = self.gate('commit_command')
        task = self.spawn(self.controller.tick())
        await self.entered(gate)
        retained = self.owner.pending_command
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(gate.cancelled)
        self.assertTrue(self.controller.busy)
        with self.assertRaises(CommandBusy):
            await self.controller.tick()
        gate.release.set()
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(report.quote_sequence, 1)
        self.assertTrue(report.decision_committed)
        self.assertIn(retained.command_id, self.transport.ledger)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assert_unique_commands()

    async def test_completed_result_after_cancel_must_be_consumed_before_a_new_tick(self):
        await self.bootstrapped(); self.price()
        gate = self.gate('commit_command')
        task = self.spawn(self.controller.tick()); await self.entered(gate)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        gate.release.set()
        for _ in range(1000):
            if self.owner.installed_state.to_dict()['engine']['cohort']['phase'] == 'evaluating':
                break
            await asyncio.sleep(0)
        self.assertEqual(self.owner.installed_state.to_dict()['engine']['cohort']['phase'], 'evaluating')
        self.assertTrue(self.controller.busy)
        count = self.transport.count('commit_command')
        with self.assertRaises(CommandBusy):
            await self.controller.tick()
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertFalse(self.controller.busy)

    async def test_protection_lost_reply_reconciles_original_before_same_tick_decision(self):
        await self.bootstrapped(); self.price()
        self.transport.fault('commit_command', OSError('commit reply lost'))
        with self.assertRaises(UncertainCommand):
            await self.controller.tick()
        retained = self.owner.pending_command
        self.assertIsNotNone(self.controller.pending_stage)
        self.assertFalse(self.controller.accepting)
        self.assertEqual(self.feed.api_call_count, 1)
        self.transport.fault('get_command', None)
        pending = await self.controller.settle()
        self.assertEqual(pending.status, 'pending')
        self.assertIs(self.owner.pending_command, retained)
        self.assertEqual(self.feed.api_call_count, 1)
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertTrue(report.decision_committed)
        self.assertEqual(report.quote_sequence, 1)
        calls = [args['command_id'] for name, args in self.transport.calls if name == 'commit_command']
        self.assertEqual(calls.count(retained.command_id), 1)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertTrue(self.repo.lease_valid)
        self.assert_unique_commands()

    async def test_decision_lost_reply_never_replans_or_refetches_during_readback(self):
        await self.bootstrapped(); self.price()
        # The first fault preserves protection; the second loses the decision.
        async def unchanged(result, _arguments):
            return result
        self.transport.fault('commit_command', unchanged)
        self.transport.fault('commit_command', OSError('decision reply lost'))
        with self.assertRaises(UncertainCommand):
            await self.controller.tick()
        retained = self.owner.pending_command
        allocation_count, command_count = len(self.allocations), self.transport.count('commit_command')
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertTrue(report.decision_committed)
        self.assertEqual(self.owner.installed_state.to_dict()['engine']['cohort']['phase'], 'evaluating')
        self.assertEqual(len(self.allocations), allocation_count)
        self.assertEqual(self.transport.count('commit_command'), command_count)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertIn(retained.command_id, self.transport.ledger)

    async def test_slow_bootstrap_publication_keeps_controller_busy_through_last_ack(self):
        entered, release = asyncio.Event(), asyncio.Event()
        self.gates.append(SimpleNamespace(release=release))
        async def publish(row):
            self.delivered.append(row)
            if len(self.delivered) == 1:
                entered.set()
                await release.wait()
        await self.ready(publisher=publish)
        task = self.spawn(self.controller.bootstrap())
        await asyncio.wait_for(entered.wait(), 5)
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'running')
        self.assertTrue(self.controller.busy)
        count, allocations = self.transport.count('commit_command'), len(self.allocations)
        for operation in (self.controller.tick, self.controller.bootstrap,
                          lambda: self.controller.control('pause'), self.controller.heartbeat):
            with self.assertRaises(CommandBusy):
                await operation()
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(len(self.allocations), allocations)
        release.set()
        self.assertEqual((await task).status, 'complete')
        self.assertEqual(len(self.delivered), 9)
        self.assertEqual(len(self.transport.acknowledged), 9)
        self.assertFalse(self.controller.busy)

    async def test_lost_first_replacement_reply_completes_terminal_pilot_without_normal_readmission(self):
        from tests.test_exact_provider_feeds import Number
        def history(end, first=False):
            if first: return self.history_values(end=end)
            return response_bytes(end, count=30, changes={i: {f: Number('150')
                for f in ('o','h','l','c')} for i in range(30)})
        await self.bootstrapped(candle_response=CandleResponse(self.history_values(seed=True)))
        self.price(value='80'); await self.controller.tick()
        for index, offset in enumerate((900, 1800, 2700), 1):
            await self.advance_to(END + offset + 15)
            self.feed._candles._session.responses.append(CandleResponse(history(END+offset, first=index==1)))
            self.price(slot=SLOT+index, value='150'); await self.controller.tick()
        await self.advance_to(END+3615)
        self.feed._candles._session.responses.append(CandleResponse(history(END+3600)))
        self.price(slot=SLOT+4, value='150')
        async def unchanged(result, _arguments): return result
        self.transport.fault('commit_command', unchanged)  # acknowledged protection
        self.transport.fault('commit_command', OSError('replacement committed; reply lost'))
        with self.assertRaises(UncertainCommand): await self.controller.tick()
        original = self.owner.pending_command
        delayed = False
        async def slow_committed_replacement(_event):
            nonlocal delayed
            if not delayed and self.owner.installed_state.to_dict()['engine']['generation'] == 1:
                delayed = True
                self.age(6)
        self.delivery_hook = slow_committed_replacement
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertTrue(report.decision_committed)
        self.assertTrue(self.controller.pilot_completed)
        self.assertFalse(self.repo.lease_valid)  # readback itself is not renewal
        self.assertEqual(self.owner.installed_state.to_dict()['engine']['generation'], 1)
        self.assertTrue(delayed)
        commands = [a['command_id'] for n,a in self.transport.calls if n=='commit_command']
        self.assertEqual(commands.count(original.command_id), 1)
        self.assertEqual(self.feed.api_call_count, 5)
        # Explicit reserved stop renews its own terminal path, without another
        # price, normal-admission attempt or evolutionary command.
        self.assertEqual((await self.controller.stop()).status, 'complete')
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')
        self.assertEqual(self.feed.api_call_count, 5)

    async def test_callback_failure_retains_same_event_and_bootstrap_stage_without_recommit(self):
        failures = 1
        async def publish(row):
            nonlocal failures
            self.delivered.append(row)
            if row['event_index'] == 1 and failures:
                failures -= 1
                raise OSError('sink effect happened, response lost')
        await self.ready(publisher=publish)
        with self.assertRaises(PublicationError):
            await self.controller.bootstrap()
        allocation_count, command_count = len(self.allocations), self.transport.count('commit_command')
        self.assertIsNotNone(self.controller.pending_stage)
        with self.assertRaises(CommandBusy):
            await self.controller.tick()
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        event_ids = [row['event_id'] for row in self.delivered]
        self.assertEqual(event_ids[1], event_ids[2])
        self.assertEqual(len(set(event_ids)), 9)
        self.assertEqual(len(self.transport.acknowledged), 9)
        self.assertEqual(self.transport.count('commit_command'), command_count)
        self.assertEqual(len(self.allocations), allocation_count)
        self.assertEqual(self.feed._candles.api_call_count, 1)

    async def test_lost_delivery_ack_retries_only_ack_then_finishes_same_bootstrap(self):
        await self.ready()
        self.transport.fault('acknowledge_event', OSError('ack committed, reply lost'))
        with self.assertRaises(PublicationError):
            await self.controller.bootstrap()
        first = self.delivered[0]['event_id']
        count = self.transport.count('commit_command')
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual([row['event_id'] for row in self.delivered].count(first), 1)
        self.assertEqual(len(self.delivered), 9)
        self.assertEqual(len(self.transport.acknowledged), 9)
        acknowledgments = [args for name, args in self.transport.calls if name == 'acknowledge_event']
        self.assertEqual([args['event_index'] for args in acknowledgments[:2]], [0, 0])
        self.assertEqual(self.transport.count('commit_command'), count)

    async def test_cancelled_bootstrap_publication_finishes_under_whole_operation_shield(self):
        gate = self.gate('acknowledge_event')
        await self.ready()
        task = self.spawn(self.controller.bootstrap()); await self.entered(gate)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(gate.cancelled)
        with self.assertRaises(CommandBusy):
            await self.controller.tick()
        gate.release.set()
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(len(self.delivered), 9)
        self.assertEqual(len({row['event_id'] for row in self.delivered}), 9)
        self.assert_unique_commands()

    async def test_stop_busy_latches_drain_and_never_starts_remaining_decision(self):
        await self.bootstrapped(); self.price()
        gate = self.gate('commit_command')
        task = self.spawn(self.controller.tick()); await self.entered(gate)
        count, allocations = self.transport.count('commit_command'), len(self.allocations)
        with self.assertRaises(CommandBusy):
            await self.controller.stop()
        self.assertFalse(self.controller.accepting)
        gate.release.set()
        report = await task
        self.assertEqual(report.status, 'drained')
        self.assertFalse(report.decision_committed)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(len(self.allocations), allocations)
        stopped = await self.controller.stop()
        self.assertEqual(stopped.status, 'complete')
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')
        self.assertIn(self.stop_id, self.transport.ledger)
        self.assertEqual(len(self.allocations), allocations)
        self.assert_unique_commands()

    async def test_explicit_drain_during_committed_reply_keeps_install_but_no_new_decision(self):
        await self.bootstrapped(); self.price()
        gate = self.gate('commit_command')
        task = self.spawn(self.controller.tick()); await self.entered(gate)
        self.controller.close_admission()
        gate.release.set()
        report = await task
        self.assertEqual(report.status, 'drained')
        self.assertEqual(report.quote_sequence, 1)
        self.assertFalse(report.decision_committed)
        self.assertEqual(self.owner.installed_state.to_dict()['engine']['cohort']['phase'], 'warming')
        self.assertFalse(self.controller.accepting)
        count = self.transport.count('commit_command')
        with self.assertRaises(CommandAdmissionError):
            await self.controller.tick()
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertTrue(self.owner.stop_available)
        await self.controller.stop()
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')

    async def test_drain_during_bootstrap_history_does_not_admit_bootstrap_after_receipt(self):
        gate = ReadGate(response_bytes()); self.gates.append(gate)
        await self.ready(candle_response=gate)
        task = self.spawn(self.controller.bootstrap()); await self.entered(gate)
        self.controller.close_admission(); gate.release.set()
        report = await task
        self.assertEqual(report.status, 'drained')
        self.assertEqual(self.transport.count('commit_command'), 0)
        self.assertEqual(self.allocations, [])
        self.assertIsNone(self.owner.installed_state)
        self.assertIsNone(self.controller.pending_stage)

    async def test_drain_during_price_receipt_does_not_admit_protection_after_capture(self):
        await self.bootstrapped()
        gate = ReadGate(price_body({SOL: '101'}, slot=SLOT)); self.gates.append(gate)
        self.price(response=gate)
        before = self.owner.installed_state
        count, allocations = self.transport.count('commit_command'), len(self.allocations)
        task = self.spawn(self.controller.tick()); await self.entered(gate)
        self.controller.close_admission(); gate.release.set()
        report = await task
        self.assertEqual(report.status, 'drained')
        self.assertIs(self.owner.installed_state, before)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(len(self.allocations), allocations)
        self.age(6)
        await self.controller.stop()
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')

    async def test_drain_during_decision_history_releases_idle_window_for_delayed_stop(self):
        await self.bootstrapped(); self.price(); await self.controller.tick()
        await self.advance_to(END + 910)
        gate = ReadGate(response_bytes(END + 900, count=30)); self.gates.append(gate)
        self.feed._candles._session.responses.append(gate)
        self.price(slot=SLOT + 1)
        task = self.spawn(self.controller.tick()); await self.entered(gate)
        count, allocations = self.transport.count('commit_command'), len(self.allocations)
        before = self.owner.installed_state
        self.controller.close_admission(); gate.release.set()
        report = await task
        self.assertEqual(report.status, 'drained')
        self.assertFalse(report.decision_committed)
        self.assertIs(self.owner.installed_state, before)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(len(self.allocations), allocations)
        self.age(6)
        self.assertTrue(self.owner.stop_available)
        await self.controller.stop()
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')

    async def test_history_cpu_overrun_is_rejected_before_allocation_or_dispatch(self):
        await self.ready()
        parser = birdeye_candles.parse_candle_records
        def slow_parser(*args, **kwargs):
            result = parser(*args, **kwargs)
            real_time.sleep(.03)
            return result
        with patch.object(module, 'HISTORY_TIMEOUT_SECONDS', .01), \
                patch.object(birdeye_candles, 'parse_candle_records', slow_parser):
            with self.assertRaises(CommandAdmissionError):
                await self.controller.bootstrap()
        self.assertEqual(self.transport.count('commit_command'), 0)
        self.assertEqual(self.allocations, [])
        self.assertIsNone(self.owner.installed_state)
        self.assertFalse(self.controller.accepting)

    async def test_price_cpu_overrun_is_rejected_before_protection_allocation_or_dispatch(self):
        await self.bootstrapped(); self.price()
        parser = jupiter_feed.parse_price_record
        def slow_parser(*args, **kwargs):
            result = parser(*args, **kwargs)
            real_time.sleep(.03)
            return result
        before = self.owner.installed_state
        count, allocations = self.transport.count('commit_command'), len(self.allocations)
        with patch.object(provider_acquisition, 'ACQUISITION_TIMEOUT_SECONDS', .01), \
                patch.object(jupiter_feed, 'parse_price_record', slow_parser):
            with self.assertRaises(CommandAdmissionError):
                await self.controller.tick()
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(len(self.allocations), allocations)
        self.assertIs(self.owner.installed_state, before)
        self.assertFalse(self.controller.accepting)

    async def test_pause_then_reserved_stop_preserves_all_economic_values(self):
        await self.bootstrapped(); self.price(); await self.controller.tick()
        before = self.owner.installed_state.to_dict()
        paused = await self.controller.control('pause')
        self.assertEqual(paused.status, 'complete')
        after_pause = self.owner.installed_state.to_dict()
        self.assertEqual(after_pause['status'], 'paused')
        for field in ('positions', 'accounts', 'reserve'):
            self.assertEqual(after_pause[field], before[field])
        allocation_count = len(self.allocations)
        stopped = await self.controller.stop()
        self.assertEqual(stopped.status, 'complete')
        after_stop = self.owner.installed_state.to_dict()
        self.assertEqual(after_stop['status'], 'stopped')
        for field in ('positions', 'accounts', 'reserve'):
            self.assertEqual(after_stop[field], before[field])
        self.assertEqual(len(self.allocations), allocation_count)
        self.assertEqual(self.transport.ledger[self.stop_id]['request']['payload']
                         ['transition']['evidence']['control']['action'], 'stop')
        self.assertFalse(self.controller.accepting)
        count = self.transport.count('commit_command')
        self.assertEqual((await self.controller.stop()).status, 'complete')
        self.assertEqual(self.transport.count('commit_command'), count)

    async def test_reserved_stop_lost_reply_reconciles_without_second_stop_or_allocations(self):
        await self.bootstrapped()
        self.transport.fault('commit_command', OSError('stop reply lost after commit'))
        count, allocations = self.transport.count('commit_command'), len(self.allocations)
        with self.assertRaises(UncertainCommand):
            await self.controller.stop()
        self.assertEqual(self.owner.pending_command.command_id, self.stop_id)
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')
        self.assertEqual(self.transport.count('commit_command'), count + 1)
        self.assertEqual(len(self.allocations), allocations)
        self.assert_unique_commands()

    async def test_soft_quote_budget_refusal_retains_reserved_stop_channel(self):
        await self.bootstrapped(limits=ProviderPilotLimits(max_quotes=1))
        self.price(); await self.controller.tick(); self.age(1); self.price(slot=SLOT + 1)
        count = self.transport.count('commit_command')
        with self.assertRaises(PilotAdmissionRefused):
            await self.controller.tick()
        self.assertEqual(self.controller.last_report.status, 'drained')
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(self.owner.refusal_reason, 'pilot_quote_budget')
        self.assertIsNone(self.owner.closed_reason)
        self.assertTrue(self.owner.stop_available)
        await self.controller.stop()
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')

    async def test_source_expiry_after_protection_readback_does_not_refetch_or_post_decision(self):
        await self.bootstrapped(); self.price()
        self.transport.fault('commit_command', OSError('reply lost after protection'))
        with self.assertRaises(UncertainCommand):
            await self.controller.tick()
        retained = self.owner.pending_candidate
        count, allocations = self.transport.count('commit_command'), len(self.allocations)
        self.age(5)
        report = await self.controller.settle()
        self.assertEqual(report.status, 'closed')
        self.assertIs(self.owner.installed_state, retained.state)
        self.assertFalse(report.decision_committed)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(len(self.allocations), allocations)
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertFalse(self.controller.accepting)

    async def test_clock_rollback_closes_before_fetch_or_new_command(self):
        await self.bootstrapped()
        self.wall.value -= 1
        count = self.transport.count('commit_command')
        with self.assertRaises(CommandAdmissionError):
            await self.controller.tick()
        self.assertFalse(self.controller.accepting)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(self.feed.api_call_count, 0)

    async def test_failed_provider_stage_survives_finished_work_without_secret_text(self):
        import json
        from vonneumann.market.feed import MarketFeedError
        await self.bootstrapped()
        count = self.transport.count('commit_command')
        async def failed_capture(_assets):
            raise MarketFeedError('rpc_unavailable')
        self.feed.get_price_captures = failed_capture
        with self.assertRaises(CommandAdmissionError):
            await self.controller.tick()
        self.assertIsNone(self.controller.pending_stage)
        self.assertEqual(self.controller.last_failure, {
            'stage': 'capture', 'category': 'operational_admission_failed',
            'provider_code': None, 'acquisition': {
                'stage': 'provider_capture', 'category': 'market_feed_error',
                'provider_code': 'rpc_unavailable'}})
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertFalse(self.controller.accepting)
        self.assertNotIn(SECRET, json.dumps(self.controller.last_failure))
        self.controller.last_failure['acquisition']['provider_code'] = 'changed'
        self.assertEqual(self.controller.last_failure['acquisition']['provider_code'], 'rpc_unavailable')

    async def test_cross_loop_settle_preserves_cancelled_callers_original_task(self):
        await self.bootstrapped()
        gate = ReadGate(price_body({SOL: '101'}, slot=SLOT)); self.gates.append(gate)
        self.price(response=gate)
        task = self.spawn(self.controller.tick()); await self.entered(gate)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        original = self.controller._task
        with self.assertRaises(CommandAdmissionError):
            await asyncio.to_thread(lambda: asyncio.run(self.controller.settle()))
        self.assertIs(self.controller._task, original)
        self.assertFalse(original.done())
        gate.release.set()
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(self.feed.api_call_count, 1)
        self.assert_unique_commands()

    async def test_owned_task_interruption_waits_original_acquisition_before_closing(self):
        await self.bootstrapped()
        gate = ReadGate(price_body({SOL: '101'}, slot=SLOT)); self.gates.append(gate)
        self.price(response=gate)
        count = self.transport.count('commit_command')
        task = self.spawn(self.controller.tick()); await self.entered(gate)
        self.controller._task.cancel()
        with self.assertRaises((asyncio.CancelledError, CommandAdmissionError)):
            await task
        self.assertFalse(gate.cancelled)
        self.assertTrue(self.controller.busy)
        settlement = self.spawn(self.controller.settle())
        await asyncio.sleep(0)
        self.assertFalse(settlement.done())
        self.assertTrue(self.controller.busy)
        gate.release.set()
        report = await settlement
        self.assertEqual(report.status, 'closed')
        self.assertEqual(self.feed.api_call_count, 1)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertFalse(self.controller.busy)
        self.assertIsNone(self.controller.pending_stage)

    async def test_pause_retry_settles_original_control_without_second_allocation_or_command(self):
        await self.bootstrapped()
        self.transport.fault('commit_command', OSError('pause reply lost'))
        with self.assertRaises(UncertainCommand):
            await self.controller.control('pause')
        original = self.owner.pending_command
        count, allocations = self.transport.count('commit_command'), len(self.allocations)
        report = await self.controller.control('pause')
        self.assertEqual(report.status, 'complete')
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'paused')
        self.assertIsNone(self.owner.closed_reason)
        # Readback proves identity and installation, without renewing a lease.
        # The explicit stop operation renews before using this byte reservation.
        self.assertGreater(self.owner.reserved_stop_bytes, 0)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(len(self.allocations), allocations)
        ids = [args['command_id'] for name, args in self.transport.calls if name == 'commit_command']
        self.assertEqual(ids.count(original.command_id), 1)
        await self.controller.stop()
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')

    async def test_stop_retry_settles_original_reserved_control_without_second_transition(self):
        await self.bootstrapped()
        self.transport.fault('commit_command', OSError('stop reply lost'))
        with self.assertRaises(UncertainCommand):
            await self.controller.stop()
        count, allocations = self.transport.count('commit_command'), len(self.allocations)
        report = await self.controller.stop()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')
        self.assertIsNone(self.owner.closed_reason)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertEqual(len(self.allocations), allocations)
        self.assert_unique_commands()

    async def test_confirmed_controls_are_idempotent_without_new_leases_or_allocations(self):
        await self.bootstrapped()
        await self.controller.control('pause')
        counts = (self.transport.count('commit_command'), self.transport.count('heartbeat'), len(self.allocations))
        self.assertEqual((await self.controller.control('pause')).status, 'complete')
        self.assertEqual((self.transport.count('commit_command'), self.transport.count('heartbeat'), len(self.allocations)), counts)
        await self.controller.stop()
        counts = (self.transport.count('commit_command'), self.transport.count('heartbeat'), len(self.allocations))
        self.assertEqual((await self.controller.stop()).status, 'complete')
        self.assertEqual((self.transport.count('commit_command'), self.transport.count('heartbeat'), len(self.allocations)), counts)
        self.assertIsNone(self.owner.closed_reason)

    async def test_completion_boundary_changed_during_allocation_fails_before_decision_dispatch(self):
        await self.bootstrapped(candle_response=CandleResponse(self.history_values(seed=True)))
        self.price(value='80'); await self.controller.tick()
        await self.advance_to(END + 910)
        self.feed._candles._session.responses.append(CandleResponse(self.history_values(end=END + 900)))
        self.price(slot=SLOT + 1, value='150'); await self.controller.tick()
        self.assertTrue(any(member['pending'] is not None
                            for member in self.owner.installed_state.to_dict()['engine']['members']))
        await self.advance_to(END + 1803.9)
        count, history_count = self.transport.count('commit_command'), self.feed._candles.api_call_count
        def boundary(kind, generation):
            if kind == 'decide':
                self.age(.2)
            return self.allocation(kind, generation)
        self.controller._allocate = boundary
        self.price(slot=SLOT + 2, value='150')
        with self.assertRaises(CommandAdmissionError):
            await self.controller.tick()
        self.assertEqual(self.transport.count('commit_command'), count + 1)
        self.assertEqual(self.feed._candles.api_call_count, history_count)
        self.assertEqual(self.owner.installed_state.to_dict()['source']['bars'][-1][0], END + 900)
        self.assertIsNotNone(self.controller.closed_reason)
        self.assertIsNone(self.controller.pending_stage)

    async def test_reports_and_allocations_are_frozen_detached_values(self):
        report = await self.bootstrapped()
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            report.status = 'forged'
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            self.allocations[0][2].command_id = self.identity()
        self.assertGreaterEqual(report.elapsed_seconds, 0)
        self.assertIs(self.controller.last_report, report)
        self.assertIsNone(self.controller.pending_stage)
