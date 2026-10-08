"""Independent provider-clock, ownership and late-ack races; all I/O is fake."""
from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from unittest.mock import patch
import unittest
from uuid import UUID

from tests.security_support import deny_network
from tests.test_exact_rehearsal import OWNER, RUN, WORKER
from tests.test_provider_contract import (
    EPOCH, END, WALL, MONO, raw_capture, raw_minutes,
)
from tests.test_transition_coordinator import Clock, CommittingTransport, Gate
from vonneumann.core import exact_lifecycle as kernel
from vonneumann.core import provider_lifecycle as life
from vonneumann.market.provider_contract import ProviderDeferred, ProviderSourceError
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandRepository, CommandAdmissionError, CommandBusy, UncertainCommand
from vonneumann.db import provider_owner as module


class ProviderOwnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        guard = deny_network();guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)
        self.wall, self.mono = Clock(), Clock()
        self.wall.value, self.mono.value = float(WALL), MONO
        self.transport = CommittingTransport()
        self.repo = CommandRepository(self.transport, OWNER, RUN, WORKER, monotonic=self.mono)
        self.owner = None
        self.identities = 12_000_000
        self.tasks, self.gates, self.events = [], [], []

    async def asyncTearDown(self):
        for gate in self.gates:gate.release.set()
        if self.tasks:
            await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), 3)
        await self.settled()

    def identity(self):
        self.identities += 1
        return str(UUID(int=self.identities))

    def allocation(self, generation=1, *, ids=True):
        return {'ids': tuple(self.identity() for _ in range(9)) if ids else (),
                'names': tuple((generation, f'Provider-owner-{generation}-{i}') for i in range(8)),
                'command_id': self.identity()}

    def age(self, delta):
        self.wall.value += delta;self.mono.value += delta

    def spawn(self, operation):
        task = asyncio.create_task(operation);self.tasks.append(task)
        return task

    def gate(self, rpc):
        gate = Gate();self.gates.append(gate);self.transport.fault(rpc, gate)
        return gate

    async def entered(self, gate):
        await asyncio.wait_for(gate.entered.wait(), 3)

    async def settled(self):
        for _ in range(400):
            if not self.repo.busy and (self.owner is None or not self.owner.busy):return
            await asyncio.sleep(0)
        self.fail('Provider-owned work did not settle')

    async def sink(self, event):
        self.events.append(event)

    async def ready(self):
        config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig('genetic_algorithm',
            OWNER, RUN, asset='SOL/USD'), EPOCH)
        await self.repo.submit(PreparedCommand.create(OWNER, RUN, WORKER,
            config.run_configuration(), config.initial_cash, command_id=self.identity()))
        self.owner = module.ProviderAdmissionOwner(self.repo, self.transport, config,
            wall_clock=self.wall, monotonic=self.mono)
        await self.owner.heartbeat()
        return config

    async def bootstrapped(self):
        await self.ready()
        await self.owner.bootstrap(raw_minutes(), **self.allocation(0))
        await self.owner.publish_pending(self.sink)

    def ticket(self, *, block=100, price='100', source_second=None):
        return self.owner.capture_quote(raw_capture(block=block, price=price,
            source_second=int(self.wall.value) - 2 if source_second is None else source_second,
            wall=self.wall.value - 1, mono=self.mono.value - 1))

    def assert_closed(self):
        self.assertFalse(self.owner.accepting)
        self.assertIsNotNone(self.owner.closed_reason)

    async def test_current_bootstrap_keeps_provider_envelope_and_no_historical_trades(self):
        await self.bootstrapped()
        state = self.owner.installed_state.to_dict()
        self.assertEqual(state['source']['epoch'], EPOCH)
        self.assertEqual(state['engine']['ema']['count'], 61)
        self.assertEqual(state['positions'], [])
        self.assertEqual(state['engine']['cohort']['phase'], 'warming')
        self.assertEqual(len(self.events), 9)
        calls = [args for name, args in self.transport.calls if name == 'commit_command']
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['payload']['version'], 5)
        self.assertEqual(calls[0]['payload']['transition']['evidence']['source']['phase'], 'bootstrap')
        self.assertTrue(self.owner.accepting)

    async def test_seed_record_membership_is_owned_before_task_scheduling(self):
        await self.ready()
        records = list(raw_minutes())
        original_digest = records[0].document.response_sha256
        original_owned = self.owner._owned
        replacement = raw_minutes(close='900')
        async def mutate_before_scheduling(operation):
            records[:] = replacement
            return await original_owned(operation)
        with patch.object(self.owner, '_owned', side_effect=mutate_before_scheduling):
            await self.owner.bootstrap(records, **self.allocation(0))
        self.assertTrue(all(row.close == '900' for row in records))
        self.assertEqual(self.owner.installed_state.to_dict()['engine']['ema']['closes'], ['100'] * 61)
        retained = self.owner.pending_candidate.transition['evidence']['source']['history']
        self.assertEqual(retained['documents'][0]['response_sha256'], original_digest)
        self.assertEqual(len(retained['minutes']), 915)

    async def test_arbitrary_record_generator_is_rejected_without_consumption(self):
        await self.ready()
        consumed = []
        def arbitrary_records():
            consumed.append(True)
            yield from raw_minutes()
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.owner.bootstrap(arbitrary_records(), **self.allocation(0))
        self.assertEqual(consumed, [])
        self.assert_closed()
        self.assertEqual(self.transport.count('commit_command'), 0)

    async def test_oversized_record_container_closes_before_scheduling(self):
        await self.ready()
        oversized = [raw_minutes(count=15)[0]] * 20_001
        with patch.object(self.owner, '_owned', wraps=self.owner._owned) as owned:
            with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
                await self.owner.bootstrap(oversized, **self.allocation(0))
        self.assertEqual(owned.call_count, 0)
        self.assert_closed()
        self.assertEqual(self.transport.count('commit_command'), 0)

    async def test_decision_requires_identical_owned_ticket_and_not_equal_values(self):
        await self.bootstrapped();self.age(1)
        accepted, other = self.ticket(), self.ticket()
        await self.owner.protect(accepted, **self.allocation())
        count = self.transport.count('commit_command')
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.owner.decide(other, **self.allocation())
        self.assert_closed()
        self.assertEqual(self.transport.count('commit_command'), count)

    async def test_ticket_cannot_be_mutated_or_reused_after_a_decision(self):
        await self.bootstrapped();self.age(1)
        ticket = self.ticket()
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            ticket._wire = b'{}'
        detached = ticket.frame;detached['quote']['price'] = '999'
        self.assertEqual(ticket.frame['quote']['price'], '100')
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.decide(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.owner.decide(ticket, **self.allocation())
        self.assert_closed()

    async def test_duplicate_source_defers_without_refreshing_or_closing_admission(self):
        await self.bootstrapped();self.age(1)
        source_second = int(self.wall.value) - 2
        ticket = self.ticket(source_second=source_second)
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.decide(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)
        before = self.owner.installed_state.to_dict()['source']
        count = self.transport.count('commit_command');self.age(1)
        with self.assertRaises(ProviderDeferred):self.ticket(source_second=source_second)
        self.assertIsNone(self.owner.closed_reason)
        self.assertTrue(self.owner.accepting)
        self.assertEqual(self.owner.installed_state.to_dict()['source'], before)
        self.assertEqual(self.transport.count('commit_command'), count)

    async def test_higher_block_with_equal_estimate_advances_on_actual_later_second(self):
        await self.bootstrapped();self.age(1)
        source_second = int(self.wall.value) - 2
        ticket = self.ticket(source_second=source_second)
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.decide(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink);self.age(1)
        next_ticket = self.ticket(block=101, source_second=source_second)
        await self.owner.protect(next_ticket, **self.allocation())
        state = self.owner.installed_state.to_dict()
        self.assertEqual(state['source']['quote_sequence'], 2)
        self.assertEqual(state['source']['last_quote']['quote']['estimated_source_second'], source_second)
        self.assertEqual(state['engine']['last_quote']['timestamp'], int(self.wall.value))

    async def test_expired_ticket_fails_before_planning_without_any_command(self):
        await self.bootstrapped();self.age(1)
        ticket = self.ticket();previous = self.owner.installed_state
        count = self.transport.count('commit_command');self.age(4)
        with patch.object(life, 'prepare_protective', wraps=life.prepare_protective) as planner:
            with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
                await self.owner.protect(ticket, **self.allocation())
        self.assertEqual(planner.call_count, 0)
        self.assertIs(self.owner.installed_state, previous)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assert_closed()

    async def test_late_ack_installs_original_candidate_then_closes_source_admission(self):
        await self.bootstrapped();self.age(1)
        ticket = self.ticket();gate = self.gate('commit_command')
        task = self.spawn(self.owner.protect(ticket, **self.allocation()))
        await self.entered(gate);candidate = self.owner.pending_candidate
        self.age(5);gate.release.set();await task
        self.assertIs(self.owner.installed_state, candidate.state)
        self.assert_closed()
        count = self.transport.count('commit_command')
        await self.owner.reconcile();await self.owner.publish_pending(self.sink)
        self.assertEqual(self.transport.count('commit_command'), count)
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.owner.decide(ticket, **self.allocation())

    async def test_source_age_can_expire_before_receipt_budget_during_ack(self):
        await self.bootstrapped();self.age(1)
        ticket = self.ticket(source_second=int(self.wall.value) - 29)
        gate = self.gate('commit_command')
        task = self.spawn(self.owner.protect(ticket, **self.allocation()))
        await self.entered(gate);candidate = self.owner.pending_candidate
        self.age(2);gate.release.set();await task
        self.assertIs(self.owner.installed_state, candidate.state)
        # The original receipt is only three seconds old; source age is 31.
        self.assertLess(self.wall.value * 1_000_000 - ticket.frame['quote']['document']['received_wall_us'], 5_000_000)
        self.assert_closed()

    async def test_caller_cancellation_does_not_cancel_committed_owned_work(self):
        await self.bootstrapped();self.age(1)
        ticket = self.ticket();gate = self.gate('commit_command')
        task = self.spawn(self.owner.protect(ticket, **self.allocation()))
        await self.entered(gate);candidate = self.owner.pending_candidate
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertFalse(gate.cancelled)
        self.assertTrue(self.owner.busy)
        with self.assertRaises(CommandBusy):await self.owner.decide(ticket, **self.allocation())
        gate.release.set();await self.settled()
        self.assertIs(self.owner.installed_state, candidate.state)
        await self.owner.decide(ticket, **self.allocation())
        self.assertEqual(self.owner.installed_state.revision, 4)

    async def test_missing_readback_retains_original_source_and_resolves_after_expiry(self):
        await self.bootstrapped();self.age(1)
        ticket = self.ticket();options = self.allocation()
        self.transport.fault('commit_command', RuntimeError('lost response'))
        with patch.object(life, 'prepare_protective', wraps=life.prepare_protective) as planner:
            with self.assertRaises(UncertainCommand):await self.owner.protect(ticket, **options)
            candidate = self.owner.pending_candidate;command = self.owner.pending_command
            self.transport.fault('get_command', None)
            self.assertIsNone(await self.owner.reconcile())
            self.assertIs(self.owner.pending_candidate, candidate)
            self.assertIs(self.owner.pending_command, command)
            self.age(6);receipt = await self.owner.reconcile()
            self.assertEqual(planner.call_count, 1)
        self.assertEqual(receipt.command.command_id, options['command_id'])
        self.assertIs(self.owner.installed_state, candidate.state)
        self.assertEqual(self.transport.count('commit_command'), 2)
        self.assert_closed()

    async def test_committed_seed_receipt_is_consumed_before_slow_outbox_delivery(self):
        await self.ready()
        await self.owner.bootstrap(raw_minutes(), **self.allocation(0))
        candidate = self.owner.pending_candidate
        gate = Gate();self.gates.append(gate)
        delivered = []
        async def sink(event):
            delivered.append(event)
            if len(delivered) == 1:await gate(None, {})
        task = self.spawn(self.owner.publish_pending(sink))
        await self.entered(gate);self.age(5);gate.release.set()
        self.assertEqual(await task, 9)
        self.assertIs(self.owner.installed_state, candidate.state)
        self.assertEqual(len(self.transport.acknowledged), 9)
        self.assertIsNone(self.owner.pending_candidate)
        self.assertTrue(self.owner.accepting)
        self.assertIsNone(self.owner._history)
        self.age(1)
        ticket = self.ticket()
        await self.owner.protect(ticket, **self.allocation())
        self.assertEqual(self.owner.installed_state.revision, 3)

    async def test_seed_receipt_expiring_before_ack_still_closes_admission(self):
        await self.ready()
        gate = self.gate('commit_command')
        task = self.spawn(self.owner.bootstrap(raw_minutes(), **self.allocation(0)))
        await self.entered(gate); candidate = self.owner.pending_candidate
        self.age(5); gate.release.set(); await task
        self.assertIs(self.owner.installed_state, candidate.state)
        await self.owner.publish_pending(self.sink)
        self.assertEqual(len(self.transport.acknowledged), 9)
        self.assert_closed()

    async def test_invalid_seed_never_dispatches_economics(self):
        await self.ready()
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.owner.bootstrap(raw_minutes()[:-1], **self.allocation(0))
        self.assert_closed()
        self.assertIsNone(self.owner.installed_state)
        self.assertEqual(self.transport.count('commit_command'), 0)

    async def test_expired_source_age_cannot_be_refreshed_by_recent_receipt(self):
        await self.bootstrapped();self.age(1)
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            self.ticket(source_second=int(self.wall.value) - 31)
        self.assert_closed()
        self.assertEqual(self.transport.count('commit_command'), 1)
