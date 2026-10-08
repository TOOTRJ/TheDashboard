"""Bounded provider pilot admission, reserved stop and retained-work races.

The owner uses real sealed lifecycle candidates and command validation. Only
the RPC ledger/outbox is fake; network I/O remains denied throughout.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch
import unittest
from uuid import UUID

from tests.security_support import deny_network
from tests.test_exact_rehearsal import ALGORITHMS, OWNER, RUN, WORKER
from tests.test_provider_contract import EPOCH, END, WALL, MONO, raw_capture, raw_minutes
from tests.test_transition_coordinator import Clock, CommittingTransport, Gate
from vonneumann.core import exact_lifecycle as kernel
from vonneumann.core import provider_lifecycle as life
from vonneumann.core.exact_rehearsal import MAX_PAYLOAD_BYTES
from vonneumann.core.provider_pilot import ProviderPilotLimits
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import (
    CommandAdmissionError, CommandBusy, CommandRepository, UncertainCommand,
)
from vonneumann.db import provider_pilot_owner as module
from vonneumann.market.provider_contract import ProviderSourceError


class ProviderPilotOwnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        guard = deny_network(); guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)
        self.wall, self.mono = Clock(), Clock()
        self.wall.value, self.mono.value = float(WALL), MONO
        self.transport = CommittingTransport()
        self.repo = CommandRepository(self.transport, OWNER, RUN, WORKER, monotonic=self.mono)
        self.owner = None
        self.identities = 41_000_000
        self.tasks, self.gates, self.events = [], [], []
        self.stop_id = self.identity()

    async def asyncTearDown(self):
        for gate in self.gates:
            gate.release.set()
        if self.tasks:
            await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), 3)
        await self.settled()

    def identity(self):
        self.identities += 1
        return str(UUID(int=self.identities))

    def allocation(self, generation=1):
        return {'ids': tuple(self.identity() for _ in range(9)),
                'names': tuple((generation, f'Pilot-{generation}-{index}') for index in range(8)),
                'command_id': self.identity()}

    def age(self, delta):
        self.wall.value += delta
        self.mono.value += delta

    async def offset(self, value):
        self.wall.value, self.mono.value = float(WALL + value), MONO + value
        await self.owner.heartbeat()

    def spawn(self, awaitable):
        task = asyncio.create_task(awaitable)
        self.tasks.append(task)
        return task

    def gate(self, rpc, *, error=None):
        gate = Gate(error); self.gates.append(gate)
        self.transport.fault(rpc, gate)
        return gate

    async def entered(self, gate):
        await asyncio.wait_for(gate.entered.wait(), 3)

    async def settled(self):
        for _ in range(400):
            if not self.repo.busy and (self.owner is None or not self.owner.busy):
                return
            await asyncio.sleep(0)
        self.fail('Provider pilot work did not settle')

    async def sink(self, event):
        self.events.append(event)

    async def ready(self, algorithm='genetic_algorithm', *, limits=None):
        config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig(
            algorithm, OWNER, RUN, asset='SOL/USD'), EPOCH)
        await self.repo.submit(PreparedCommand.create(OWNER, RUN, WORKER,
            config.run_configuration(), config.initial_cash, command_id=self.identity()))
        options = {} if limits is None else {'limits': limits}
        self.owner = module.ProviderPilotOwner(self.repo, self.transport, config,
            stop_command_id=self.stop_id, wall_clock=self.wall, monotonic=self.mono, **options)
        await self.owner.heartbeat()
        return config

    async def bootstrapped(self, algorithm='genetic_algorithm', *, limits=None, low_seed=False):
        await self.ready(algorithm, limits=limits)
        records = raw_minutes(closes=['100'] * 900 + ['80'] * 15) if low_seed else raw_minutes()
        await self.owner.bootstrap(records, **self.allocation(0))
        await self.owner.publish_pending(self.sink)

    def ticket(self, *, block=100, source_second=None, price='100'):
        return self.owner.capture_quote(raw_capture(block=block, price=price,
            source_second=int(self.wall.value) - 2 if source_second is None else source_second,
            wall=self.wall.value - 1, mono=self.mono.value - 1))

    async def first_decision(self):
        self.age(1)
        ticket = self.ticket()
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        await self.owner.decide(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        return ticket

    def assert_refused(self, reason):
        self.assertEqual(self.owner.refusal_reason, reason)
        self.assertIsNone(self.owner.closed_reason)
        self.assertFalse(self.owner.accepting)

    async def assert_stop(self):
        before = self.owner.installed_state.to_dict()
        count = self.transport.count('commit_command')
        self.assertTrue(self.owner.stop_available)
        receipt = await self.owner.stop()
        self.assertEqual(receipt.command.command_id, self.stop_id)
        after = self.owner.installed_state.to_dict()
        self.assertEqual(after['status'], 'stopped')
        self.assertEqual(after['positions'], before['positions'])
        self.assertEqual(after['accounts'], before['accounts'])
        self.assertEqual(after['reserve'], before['reserve'])
        self.assertEqual(self.transport.count('commit_command'), count + 1)
        request = self.transport.ledger[self.stop_id]['request']['payload']
        self.assertEqual(request['version'], 5)
        self.assertEqual(request['transition']['evidence']['inputs']['ids'], [])
        self.assertEqual(request['transition']['evidence']['inputs']['names'], [])
        await self.owner.publish_pending(self.sink)
        self.assertFalse(self.owner.stop_available)

    async def test_fresh_owner_needs_bootstrap_before_reserved_stop_is_available(self):
        await self.ready()
        self.assertTrue(self.owner.accepting)
        self.assertFalse(self.owner.stop_available)
        with self.assertRaises(CommandAdmissionError):
            await self.owner.stop()
        self.assertEqual(self.transport.count('commit_command'), 0)

    async def test_reserved_command_identity_cannot_be_spent_on_an_ordinary_command(self):
        await self.bootstrapped()
        self.age(1); ticket = self.ticket()
        options = self.allocation(); options['command_id'] = self.stop_id
        before = self.owner.installed_state
        count = self.transport.count('commit_command')
        with self.assertRaises(module.PilotAdmissionRefused):
            await self.owner.protect(ticket, **options)
        self.assert_refused('pilot_reserved_identity')
        self.assertIs(self.owner.installed_state, before)
        self.assertEqual(self.transport.count('commit_command'), count)
        await self.assert_stop()

    async def test_reserved_command_identity_cannot_be_an_economic_allocation(self):
        await self.bootstrapped()
        self.age(1); ticket = self.ticket()
        options = self.allocation(); options['ids'] = (self.stop_id,) + options['ids'][1:]
        count = self.transport.count('commit_command')
        with self.assertRaises(module.PilotAdmissionRefused):
            await self.owner.protect(ticket, **options)
        self.assert_refused('pilot_reserved_identity')
        self.assertEqual(self.transport.count('commit_command'), count)
        await self.assert_stop()

    async def test_refused_decision_releases_unretained_quote_window_for_delayed_stop(self):
        await self.bootstrapped(); self.age(1)
        ticket = self.ticket()
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        before = self.owner.installed_state
        count = self.transport.count('commit_command')
        with self.assertRaises(module.PilotAdmissionRefused):
            await self.owner.decide(ticket, command_id=self.stop_id)
        self.assert_refused('pilot_reserved_identity')
        self.assertIs(self.owner.installed_state, before)
        self.assertIsNone(self.owner.pending_candidate)
        self.age(5)
        await self.owner.heartbeat()
        self.assertIsNone(self.owner.closed_reason)
        self.assertEqual(self.transport.count('commit_command'), count)
        await self.assert_stop()

    async def test_refused_control_releases_selected_decision_window_for_delayed_stop(self):
        await self.bootstrapped(); self.age(1)
        ticket = self.ticket()
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        self.assertTrue(self.owner.decision_due(ticket))
        before = self.owner.installed_state
        count = self.transport.count('commit_command')
        with self.assertRaises(module.PilotAdmissionRefused):
            await self.owner.control('resume', command_id=self.identity())
        self.assert_refused('pilot_control_unsupported')
        self.assertIs(self.owner.installed_state, before)
        self.assertIsNone(self.owner.pending_candidate)
        self.age(5)
        await self.owner.heartbeat()
        self.assertIsNone(self.owner.closed_reason)
        self.assertEqual(self.transport.count('commit_command'), count)
        await self.assert_stop()

    async def test_command_budget_includes_creation_and_keeps_the_last_id_for_stop(self):
        await self.bootstrapped(limits=ProviderPilotLimits(max_commands=5))
        await self.first_decision()
        self.age(1)
        before = self.owner.installed_state
        count = self.transport.count('commit_command')
        with self.assertRaises(module.PilotAdmissionRefused):
            ticket = self.ticket(block=101)
            await self.owner.protect(ticket, **self.allocation())
        self.assert_refused('pilot_command_budget')
        self.assertIs(self.owner.installed_state, before)
        self.assertEqual(self.transport.count('commit_command'), count)
        await self.assert_stop()
        self.assertEqual(len(self.owner._used_command_ids), 5)

    async def test_minimum_budget_can_refuse_a_required_decision_and_still_stop(self):
        await self.bootstrapped(limits=ProviderPilotLimits(max_commands=4))
        self.age(1); ticket = self.ticket()
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        before = self.owner.installed_state
        count = self.transport.count('commit_command')
        with self.assertRaises(module.PilotAdmissionRefused):
            await self.owner.decide(ticket, **self.allocation())
        self.assert_refused('pilot_command_budget')
        self.assertIs(self.owner.installed_state, before)
        self.assertEqual(self.transport.count('commit_command'), count)
        await self.assert_stop()
        self.assertEqual(self.owner.owned_command_count, 4)

    async def test_last_permitted_quote_can_finish_its_required_decision_before_stop(self):
        await self.bootstrapped(limits=ProviderPilotLimits(max_quotes=1))
        await self.first_decision()
        self.assertEqual(self.owner.installed_state.to_dict()['source']['quote_sequence'], 1)
        self.age(1)
        count = self.transport.count('commit_command')
        with self.assertRaises(module.PilotAdmissionRefused):
            ticket = self.ticket(block=101)
            await self.owner.protect(ticket, **self.allocation())
        self.assert_refused('pilot_quote_budget')
        self.assertEqual(self.transport.count('commit_command'), count)
        await self.assert_stop()

    async def test_unused_decision_never_prepares_dispatches_or_spends_allocations(self):
        await self.bootstrapped(); await self.first_decision(); self.age(1)
        ticket = self.ticket(block=101)
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        before = self.owner.installed_state
        used = set(self.owner._used_command_ids)
        options = self.allocation()
        count = self.transport.count('commit_command')
        with patch.object(life, 'prepare_decision', wraps=life.prepare_decision) as planner:
            result = await self.owner.decide(ticket, **options)
        self.assertIsNone(result)
        self.assertEqual(planner.call_count, 0)
        self.assertIs(self.owner.installed_state, before)
        self.assertEqual(self.owner._used_command_ids, used)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertTrue(self.owner.accepting)
        self.age(1)
        next_ticket = self.ticket(block=102)
        await self.owner.protect(next_ticket, command_id=options['command_id'])
        await self.owner.publish_pending(self.sink)
        await self.assert_stop()

    async def test_unused_decision_still_requires_the_identical_accepted_owned_ticket(self):
        await self.bootstrapped(); await self.first_decision(); self.age(1)
        ticket, equal_values = self.ticket(block=101), self.ticket(block=101)
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        count = self.transport.count('commit_command')
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.owner.decide(equal_values, **self.allocation())
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertIsNotNone(self.owner.closed_reason)
        self.assertFalse(self.owner.stop_available)

    async def test_noop_decision_remains_available_when_only_reserved_stop_budget_is_left(self):
        await self.bootstrapped(limits=ProviderPilotLimits(max_commands=6))
        await self.first_decision(); self.age(1)
        ticket = self.ticket(block=101)
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        count = self.transport.count('commit_command')
        self.assertEqual(self.owner.owned_command_count, 5)
        self.assertIsNone(await self.owner.decide(ticket, **self.allocation()))
        self.assertEqual(self.owner.owned_command_count, 5)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertIsNone(self.owner.refusal_reason)
        await self.assert_stop()
        self.assertEqual(self.owner.owned_command_count, 6)

    async def test_stop_witness_overflow_refuses_before_install_or_dispatch(self):
        await self.bootstrapped(); self.age(1)
        ticket = self.ticket()
        before = self.owner.installed_state
        before_json = before.to_dict()
        count = self.transport.count('commit_command')
        with patch.object(module, 'stop_capacity_bytes', return_value=MAX_PAYLOAD_BYTES + 1):
            with self.assertRaises(module.PilotAdmissionRefused):
                await self.owner.protect(ticket, **self.allocation())
        self.assert_refused('pilot_stop_capacity')
        self.assertIs(self.owner.installed_state, before)
        self.assertEqual(before.to_dict(), before_json)
        self.assertEqual(self.transport.count('commit_command'), count)
        await self.assert_stop()

    async def test_pilot_allocation_limits_refuse_before_dispatch_and_keep_stop(self):
        for field in ('ids', 'names'):
            with self.subTest(field=field):
                self.wall.value, self.mono.value = float(WALL), MONO
                self.transport = CommittingTransport()
                self.repo = CommandRepository(self.transport, OWNER, RUN, WORKER, monotonic=self.mono)
                self.owner = None; self.stop_id = self.identity()
                await self.bootstrapped(); self.age(1)
                ticket = self.ticket(); options = self.allocation()
                extra = self.identity() if field == 'ids' else (1, 'Additional pilot name')
                options[field] += (extra,)
                before = self.owner.installed_state
                count = self.transport.count('commit_command')
                with self.assertRaises(module.PilotAdmissionRefused):
                    await self.owner.protect(ticket, **options)
                self.assert_refused('pilot_allocation_budget')
                self.assertIs(self.owner.installed_state, before)
                self.assertEqual(self.transport.count('commit_command'), count)
                await self.assert_stop()

    async def test_duration_bound_preserves_stop_after_the_supported_first_window(self):
        await self.bootstrapped(); await self.first_decision()
        await self.offset(3662)
        count = self.transport.count('commit_command')
        with self.assertRaises(module.PilotAdmissionRefused):
            ticket = self.ticket(block=101)
            await self.owner.protect(ticket, **self.allocation())
        self.assert_refused('pilot_duration')
        self.assertEqual(self.transport.count('commit_command'), count)
        await self.assert_stop()

    async def test_pause_retains_holdings_and_reserved_stop_without_restart(self):
        await self.bootstrapped(low_seed=True); await self.first_decision()
        await self.offset(900)
        ticket = self.ticket(block=101)
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        await self.owner.decide(ticket, raw_minutes(end=END + 900, count=15,
            close='120', wall=self.wall.value - 1, mono=self.mono.value - 1), **self.allocation())
        await self.owner.publish_pending(self.sink)
        await self.offset(901)
        ticket = self.ticket(block=102)
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        await self.owner.decide(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        before = self.owner.installed_state.to_dict()
        self.assertEqual(sum(not row['closed'] for row in before['positions']), 8)
        await self.owner.control('pause', command_id=self.identity())
        await self.owner.publish_pending(self.sink)
        paused = self.owner.installed_state.to_dict()
        self.assertEqual(paused['status'], 'paused')
        self.assertEqual(paused['positions'], before['positions'])
        with self.assertRaises(module.PilotAdmissionRefused):
            await self.owner.control('resume', command_id=self.identity())
        self.assert_refused('pilot_control_unsupported')
        await self.assert_stop()

    async def test_recovery_is_refused_without_allocations_or_dispatch(self):
        await self.bootstrapped()
        count = self.transport.count('commit_command')
        with self.assertRaises(module.PilotAdmissionRefused):
            await self.owner.control('recover', command_id=self.identity())
        self.assert_refused('pilot_control_unsupported')
        self.assertEqual(self.transport.count('commit_command'), count)
        await self.assert_stop()

    async def test_clock_rollback_remains_a_hard_failure_even_with_a_stop_reservation(self):
        await self.bootstrapped()
        self.wall.value -= 1
        self.assertFalse(self.owner.accepting)
        self.assertEqual(self.owner.closed_reason, 'clock_invalid')
        self.assertIsNone(self.owner.refusal_reason)
        self.assertFalse(self.owner.stop_available)
        with self.assertRaises(CommandAdmissionError):
            await self.owner.stop()

    async def test_invalid_clock_after_pilot_refusal_still_hard_closes_reserved_stop(self):
        for field, invalid in (('wall', float('nan')), ('mono', MONO - 1)):
            with self.subTest(clock=field):
                self.wall.value, self.mono.value = float(WALL), MONO
                self.transport = CommittingTransport()
                self.repo = CommandRepository(self.transport, OWNER, RUN, WORKER, monotonic=self.mono)
                self.owner = None; self.stop_id = self.identity()
                await self.bootstrapped()
                with self.assertRaises(module.PilotAdmissionRefused):
                    await self.owner.control('resume', command_id=self.identity())
                self.assert_refused('pilot_control_unsupported')
                before = self.owner.installed_state
                count = self.transport.count('commit_command')
                getattr(self, field).value = invalid
                self.assertFalse(self.owner.stop_available)
                self.assertEqual(self.owner.closed_reason, 'clock_invalid')
                with self.assertRaises(CommandAdmissionError):
                    await self.owner.stop()
                self.assertIs(self.owner.installed_state, before)
                self.assertEqual(self.transport.count('commit_command'), count)

    async def test_stale_source_remains_a_hard_failure(self):
        await self.bootstrapped(); self.age(1)
        count = self.transport.count('commit_command')
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            self.ticket(source_second=int(self.wall.value) - 31)
        self.assertIsNotNone(self.owner.closed_reason)
        self.assertIsNone(self.owner.refusal_reason)
        self.assertFalse(self.owner.stop_available)
        self.assertEqual(self.transport.count('commit_command'), count)

    async def test_lost_ack_resolves_original_candidate_and_publishes_before_stop(self):
        await self.bootstrapped(); self.age(1)
        command_id = self.identity()
        self.transport.fault('commit_command', OSError('reply lost after commit'))
        with self.assertRaises(UncertainCommand):
            await self.owner.control('pause', command_id=command_id)
        command, candidate = self.owner.pending_command, self.owner.pending_candidate
        count = self.transport.count('commit_command')
        self.assertFalse(self.owner.stop_available)
        self.transport.fault('get_command', None)
        self.assertIsNone(await self.owner.reconcile())
        self.assertIs(self.owner.pending_command, command)
        self.assertIs(self.owner.pending_candidate, candidate)
        receipt = await self.owner.reconcile()
        self.assertEqual(receipt.command.command_id, command_id)
        self.assertIs(self.owner.installed_state, candidate.state)
        self.assertFalse(self.owner.stop_available)
        await self.owner.publish_pending(self.sink)
        self.assertEqual(self.transport.count('commit_command'), count)
        # Journal readback establishes identity and state; it never renews a lease.
        self.assertFalse(self.repo.lease_valid)
        await self.owner.heartbeat()
        await self.assert_stop()

    async def test_caller_cancel_keeps_the_original_commit_owned_then_allows_stop(self):
        await self.bootstrapped(); self.age(1)
        gate = self.gate('commit_command')
        task = self.spawn(self.owner.control('pause', command_id=self.identity()))
        await self.entered(gate)
        candidate = self.owner.pending_candidate
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(gate.cancelled)
        self.assertFalse(self.owner.stop_available)
        with self.assertRaises((CommandBusy, CommandAdmissionError)):
            await self.owner.stop()
        gate.release.set(); await self.settled()
        self.assertIs(self.owner.installed_state, candidate.state)
        self.assertFalse(self.owner.stop_available)
        await self.owner.publish_pending(self.sink)
        await self.assert_stop()

    async def test_reserved_stop_lost_ack_keeps_original_id_for_readback_without_resubmission(self):
        await self.bootstrapped()
        self.transport.fault('commit_command', OSError('stop committed; reply lost'))
        count = self.transport.count('commit_command')
        with self.assertRaises(UncertainCommand):
            await self.owner.stop()
        command, candidate = self.owner.pending_command, self.owner.pending_candidate
        self.assertEqual(command.command_id, self.stop_id)
        self.assertEqual(candidate.state.to_dict()['status'], 'stopped')
        self.assertFalse(self.owner.stop_available)
        with self.assertRaises(CommandAdmissionError):
            await self.owner.stop()
        self.transport.fault('get_command', None)
        self.assertIsNone(await self.owner.reconcile())
        self.assertIs(self.owner.pending_command, command)
        self.assertIs(self.owner.pending_candidate, candidate)
        receipt = await self.owner.reconcile()
        self.assertEqual(receipt.command.command_id, self.stop_id)
        self.assertIs(self.owner.installed_state, candidate.state)
        await self.owner.publish_pending(self.sink)
        self.assertEqual(self.transport.count('commit_command'), count + 1)
        self.assertFalse(self.owner.stop_available)

    async def test_reserved_stop_caller_cancellation_keeps_commit_and_publication_owned(self):
        await self.bootstrapped()
        count = self.transport.count('commit_command')
        gate = self.gate('commit_command')
        task = self.spawn(self.owner.stop())
        await self.entered(gate)
        command, candidate = self.owner.pending_command, self.owner.pending_candidate
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(command.command_id, self.stop_id)
        self.assertFalse(gate.cancelled)
        self.assertFalse(self.owner.stop_available)
        gate.release.set(); await self.settled()
        self.assertIs(self.owner.installed_state, candidate.state)
        self.assertEqual(self.owner.installed_state.to_dict()['status'], 'stopped')
        await self.owner.reconcile(); await self.owner.publish_pending(self.sink)
        self.assertEqual(self.transport.count('commit_command'), count + 1)
        self.assertFalse(self.owner.stop_available)

    async def test_owned_task_interruption_closes_admission_but_retained_commit_can_install(self):
        await self.bootstrapped()
        gate = self.gate('commit_command')
        task = self.spawn(self.owner.control('pause', command_id=self.identity()))
        await self.entered(gate)
        candidate = self.owner.pending_candidate
        self.owner._task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.owner.closed_reason, 'operation_interrupted')
        self.assertFalse(self.owner.stop_available)
        self.assertFalse(gate.cancelled)
        gate.release.set(); await self.settled()
        await self.owner.reconcile(); await self.owner.publish_pending(self.sink)
        self.assertIs(self.owner.installed_state, candidate.state)
        self.assertFalse(self.owner.stop_available)

    async def test_owned_task_cancelled_before_first_instruction_cannot_leave_admission_open(self):
        await self.bootstrapped()
        before = self.owner.installed_state
        count = self.transport.count('commit_command')
        cancelled = []
        def cancelling_factory(coroutine):
            task = asyncio.Task(coroutine)
            task.cancel(); cancelled.append(task)
            return task
        with patch.object(module.asyncio, 'create_task', side_effect=cancelling_factory):
            with self.assertRaises(asyncio.CancelledError):
                await self.owner.control('pause', command_id=self.identity())
        await self.settled()
        self.assertTrue(cancelled[0].cancelled())
        self.assertEqual(self.owner.closed_reason, 'operation_interrupted')
        self.assertIs(self.owner.installed_state, before)
        self.assertIsNone(self.owner.pending_candidate)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertFalse(self.owner.stop_available)

    async def test_publication_cancellation_keeps_event_delivery_owned_before_stop(self):
        await self.ready()
        await self.owner.bootstrap(raw_minutes(), **self.allocation(0))
        gate = Gate(); self.gates.append(gate)
        delivered = []
        async def sink(event):
            delivered.append(event)
            if len(delivered) == 1:
                await gate(None, {})
        task = self.spawn(self.owner.publish_pending(sink))
        await self.entered(gate); task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(gate.cancelled)
        self.assertFalse(self.owner.stop_available)
        gate.release.set(); await self.settled()
        self.assertEqual(len(delivered), 9)
        self.assertEqual(len(self.transport.acknowledged), 9)
        self.assertIsNone(self.owner.pending_candidate)
        await self.assert_stop()

    async def test_all_solvers_complete_one_dense_replacement_then_latch_and_stop(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                # Give each solver its own ledger, repository, clocks and owner.
                self.wall.value, self.mono.value = float(WALL), MONO
                self.transport = CommittingTransport()
                self.repo = CommandRepository(self.transport, OWNER, RUN, WORKER, monotonic=self.mono)
                self.owner = None
                self.stop_id = self.identity()
                await self.bootstrapped(algorithm, low_seed=True)
                for serial, offset in enumerate((1, 900, 901, 1800, 1801, 2700, 2701, 3600, 3613), 1):
                    await self.offset(offset)
                    ticket = self.ticket(block=100 + serial)
                    await self.owner.protect(ticket, **self.allocation())
                    await self.owner.publish_pending(self.sink)
                    records = ()
                    if offset % 900 == 0:
                        records = raw_minutes(end=END + offset, count=15,
                            close='120' if (offset // 900) % 2 else '80',
                            wall=self.wall.value - 1, mono=self.mono.value - 1)
                    await self.owner.decide(ticket, records, **self.allocation())
                    if offset == 3613:
                        self.assert_refused('pilot_completed')
                        self.assertFalse(self.owner.stop_available)
                    await self.owner.publish_pending(self.sink)
                state = self.owner.installed_state.to_dict()
                self.assertEqual(state['engine']['generation'], 1)
                self.assertEqual(len(state['accounts']), 16)
                self.assertEqual(len(state['positions']), 16)
                self.assertTrue(all(row['closed'] for row in state['positions']))
                self.assert_refused('pilot_completed')
                await self.assert_stop()


if __name__ == '__main__':
    unittest.main()
