"""Independent operational admission races over actual exact lifecycle states.

Fake receipts may be withheld after a real candidate has been recorded by the
server double. Failure/cancellation therefore never establishes rollback.
"""
from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch
import unittest
from uuid import UUID

from tests.security_support import deny_network
from tests.test_exact_rehearsal import OWNER, RUN, WORKER, inputs
from tests.test_transition_coordinator import Clock, CommittingTransport, Gate
from vonneumann.core import exact_lifecycle as life
from vonneumann.db import command_protocol
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandRepository, CommandAdmissionError, CommandBusy, UncertainCommand
from vonneumann.db import rehearsal_owner as module


class RehearsalOwnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        guard = deny_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)
        self.wall, self.mono = Clock(), Clock()
        self.wall.value = 1000.0
        self.transport = CommittingTransport()
        self.repo = CommandRepository(self.transport, OWNER, RUN, WORKER, monotonic=self.mono)
        self.owner = None
        self.tasks, self.gates = [], []
        self.ids = 9500000
        self.events = []

    async def asyncTearDown(self):
        for gate in self.gates:
            gate.release.set()
        if self.tasks:
            await asyncio.wait_for(asyncio.gather(*self.tasks,return_exceptions=True),3)
        await self.settled()

    def identity(self):
        self.ids += 1
        return str(UUID(int=self.ids))

    def spawn(self, awaitable):
        task = asyncio.create_task(awaitable)
        self.tasks.append(task)
        return task

    def gate(self, rpc, *, error=None):
        gate = Gate(error)
        self.gates.append(gate)
        self.transport.fault(rpc,gate)
        return gate

    async def entered(self, gate):
        await asyncio.wait_for(gate.entered.wait(),3)

    async def settled(self):
        for _ in range(300):
            if not self.repo.busy and (self.owner is None or not self.owner.busy):
                return
            await asyncio.sleep(0)
        self.fail('Owned rehearsal task failed to settle')

    async def sink(self, event):
        self.events.append(event)
        return None

    async def publish(self):
        return await self.owner.publish_pending(self.sink)

    async def ready(self, *, loss='3000', algorithm='genetic_algorithm'):
        config = life.ExactLifecycleConfig(algorithm, OWNER, RUN, account_loss_bps=loss)
        await self.repo.submit(PreparedCommand.create(OWNER,RUN,WORKER,config.run_configuration(),
            config.initial_cash,command_id=self.identity()))
        await self.repo.heartbeat()
        self.owner = module.RehearsalAdmissionOwner(self.repo,self.transport,config,
            wall_clock=self.wall,monotonic=self.mono,max_wait_seconds=5.0)
        return config

    async def bootstrapped(self, **kwargs):
        config = await self.ready(**kwargs)
        await self.owner.bootstrap(inputs(0),command_id=self.identity())
        await self.publish()
        return config

    async def step(self, stamp, price='100', *, end=None, close=None):
        generation = self.owner.installed_state.to_dict()['engine']['generation']
        quote = self.owner.capture_quote(stamp,price)
        await self.owner.protect(quote,inputs(stamp),command_id=self.identity())
        await self.publish()
        await self.owner.decide(quote,inputs(stamp,generation+1),command_id=self.identity(),
            candle_end=end,candle_close=close)
        await self.publish()
        return quote

    async def opened(self, **kwargs):
        config = await self.bootstrapped(**kwargs)
        for bar in range(1,63):
            close = '100' if bar<61 else '80' if bar==61 else '120'
            await self.step(bar*900,end=bar*900,close=close)
        await self.step(55801)
        self.assertEqual(sum(not p['closed'] for p in self.owner.installed_state.to_dict()['positions']),8)
        return config

    def age(self, amount):
        self.wall.value += amount
        self.mono.value += amount

    def assert_closed(self):
        self.assertFalse(self.owner.accepting)
        self.assertIsNotNone(self.owner.closed_reason)

    async def test_bootstrap_owns_actual_state_and_ordered_events_before_admission(self):
        await self.ready()
        self.assertIsNone(self.owner.installed_state)
        await self.owner.bootstrap(inputs(0),command_id=self.identity())
        self.assertEqual(self.owner.installed_state.revision,2)
        self.assertIsNotNone(self.owner.pending_candidate)
        self.assertFalse(self.owner.accepting)
        self.assertEqual(await self.publish(),9)
        self.assertEqual([row['event']['kind'] for row in self.events],['founder']*8+['lifecycle'])
        self.assertTrue(self.owner.accepting)
        self.assertIsNone(self.owner.pending_candidate)

    async def test_stale_before_planning_closes_without_economic_submission(self):
        await self.bootstrapped()
        quote = self.owner.capture_quote(60,'100')
        previous = self.owner.installed_state
        count = self.transport.count('commit_command')
        self.age(5.001)
        with self.assertRaises(CommandAdmissionError):
            await self.owner.protect(quote,inputs(60),command_id=self.identity())
        self.assert_closed()
        self.assertIs(self.owner.installed_state,previous)
        self.assertEqual(self.transport.count('commit_command'),count)
        with self.assertRaises(CommandAdmissionError):
            await self.owner.protect(quote,inputs(60),command_id=self.identity())

    async def test_wall_and_monotonic_regression_each_close_permanently(self):
        for which in ('wall','mono'):
            with self.subTest(which=which):
                self.setUpClocksForFreshOwner()
                await self.bootstrapped()
                quote = self.owner.capture_quote(60,'100')
                getattr(self,which).value -= .001
                with self.assertRaises(CommandAdmissionError):
                    await self.owner.protect(quote,inputs(60),command_id=self.identity())
                self.assert_closed()
                getattr(self,which).value += 100
                self.assertFalse(self.owner.accepting)

    def setUpClocksForFreshOwner(self):
        self.wall,self.mono = Clock(),Clock()
        self.wall.value = 1000.0
        self.transport = CommittingTransport()
        self.repo = CommandRepository(self.transport,OWNER,RUN,WORKER,monotonic=self.mono)
        self.owner = None

    async def test_equal_quote_values_cannot_replace_the_installed_ticket_object(self):
        await self.bootstrapped()
        accepted = self.owner.capture_quote(60,'100')
        other = self.owner.capture_quote(60,'100')
        await self.owner.protect(accepted,inputs(60),command_id=self.identity())
        count = self.transport.count('commit_command')
        with self.assertRaises(CommandAdmissionError):
            await self.owner.decide(other,inputs(60,1),command_id=self.identity(),candle_end=0,candle_close='100')
        self.assert_closed()
        self.assertEqual(self.transport.count('commit_command'),count)

    async def test_successful_decision_consumes_ticket_and_cannot_reuse_old_frame(self):
        await self.bootstrapped()
        quote = await self.step(900,end=900,close='100')
        previous = self.owner.installed_state
        with self.assertRaises(CommandAdmissionError):
            await self.owner.decide(quote,inputs(900,1),command_id=self.identity(),candle_end=900,candle_close='100')
        self.assert_closed()
        self.assertIs(self.owner.installed_state,previous)

    async def test_bootstrap_identity_exhaustion_closes_before_any_command(self):
        await self.ready()
        with self.assertRaises((ValueError,CommandAdmissionError)):
            await self.owner.bootstrap(inputs(0,identities=False),command_id=self.identity())
        self.assert_closed()
        self.assertIsNone(self.owner.installed_state)
        self.assertIsNone(self.owner.pending_candidate)
        self.assertEqual(self.transport.count('commit_command'),0)

    async def test_malformed_command_identity_closes_and_does_not_submit(self):
        await self.ready()
        with self.assertRaises((ValueError,CommandAdmissionError)):
            await self.owner.bootstrap(inputs(0),command_id='bad-command-id')
        self.assert_closed()
        self.assertIsNone(self.owner.installed_state)
        self.assertEqual(self.transport.count('commit_command'),0)

    async def test_cancelled_caller_cannot_cancel_owned_late_ack_installation(self):
        await self.bootstrapped()
        quote = self.owner.capture_quote(60,'100')
        gate = self.gate('commit_command')
        identity = self.identity()
        task = self.spawn(self.owner.protect(quote,inputs(60),command_id=identity))
        await self.entered(gate)
        retained = self.owner.pending_candidate
        self.assertIsNotNone(retained)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertFalse(gate.cancelled)
        self.assertTrue(self.owner.busy)
        gate.release.set()
        await self.settled()
        self.assertIs(self.owner.installed_state,retained.state)
        self.assertEqual(self.transport.count('commit_command'),2)
        await self.owner.decide(quote,inputs(60,1),command_id=self.identity())
        self.assertEqual(self.owner.installed_state.revision,4)

    async def test_concurrent_calls_reject_without_queueing_or_closing_valid_admission(self):
        await self.bootstrapped()
        quote = self.owner.capture_quote(60,'100')
        gate = self.gate('commit_command')
        task = self.spawn(self.owner.protect(quote,inputs(60),command_id=self.identity()))
        await self.entered(gate)
        calls = len(self.transport.calls)
        for operation in (lambda:self.owner.heartbeat(),lambda:self.owner.reconcile(),
                          lambda:self.owner.publish_pending(self.sink),
                          lambda:self.owner.decide(quote,inputs(60,1),command_id=self.identity())):
            with self.assertRaises(CommandBusy):await operation()
        self.assertEqual(len(self.transport.calls),calls)
        gate.release.set();await task
        self.assertIsNone(self.owner.closed_reason)
        self.assertTrue(self.owner.accepting)

    async def test_close_during_commit_preserves_original_candidate_and_installation(self):
        await self.bootstrapped()
        quote=self.owner.capture_quote(60,'100');gate=self.gate('commit_command')
        task=self.spawn(self.owner.protect(quote,inputs(60),command_id=self.identity()))
        await self.entered(gate);retained=self.owner.pending_candidate
        self.owner.close_admission();gate.release.set();await task
        self.assertIs(self.owner.installed_state,retained.state)
        self.assert_closed()
        await self.owner.reconcile();await self.publish()
        self.assert_closed()

    async def test_actual_candidate_byte_capacity_failure_closes_before_submission(self):
        await self.ready()
        with patch.object(life.base,'MAX_PAYLOAD_BYTES',1):
            with self.assertRaises(module.OperationalAdmissionError):
                await self.owner.bootstrap(inputs(0),command_id=self.identity())
        self.assert_closed()
        self.assertEqual(self.owner.closed_reason,'preparation_failed')
        self.assertEqual(self.transport.count('commit_command'),0)
        self.assertIsNone(self.owner.pending_candidate)

    async def test_quote_expires_during_real_planning_before_command_dispatch(self):
        await self.bootstrapped()
        quote=self.owner.capture_quote(60,'100')
        previous=self.owner.installed_state;count=self.transport.count('commit_command')
        original=life.prepare_protective
        def slow_plan(*args,**kwargs):
            candidate=original(*args,**kwargs)
            self.age(5)
            return candidate
        with patch.object(life,'prepare_protective',side_effect=slow_plan) as planner:
            with self.assertRaises(module.OperationalAdmissionError):
                await self.owner.protect(quote,inputs(60),command_id=self.identity())
        self.assertEqual(planner.call_count,1)
        self.assert_closed()
        self.assertEqual(self.owner.closed_reason,'observation_expired')
        self.assertIs(self.owner.installed_state,previous)
        self.assertEqual(self.transport.count('commit_command'),count)

    async def test_quote_expires_during_command_encoding_before_post(self):
        await self.bootstrapped()
        quote=self.owner.capture_quote(60,'100')
        previous=self.owner.installed_state;count=self.transport.count('commit_command')
        original=PreparedCommand.batch
        def slow_command(*args,**kwargs):
            command=original(*args,**kwargs)
            self.age(5)
            return command
        with patch.object(PreparedCommand,'batch',side_effect=slow_command):
            with self.assertRaises(CommandAdmissionError):
                await self.owner.protect(quote,inputs(60),command_id=self.identity())
        self.assert_closed()
        self.assertIs(self.owner.installed_state,previous)
        self.assertEqual(self.transport.count('commit_command'),count)

    async def test_post_ack_expiry_installs_committed_state_but_never_readmits(self):
        await self.bootstrapped()
        quote=self.owner.capture_quote(60,'100');gate=self.gate('commit_command')
        task=self.spawn(self.owner.protect(quote,inputs(60),command_id=self.identity()))
        await self.entered(gate);candidate=self.owner.pending_candidate
        self.age(5);gate.release.set();await task
        self.assertIs(self.owner.installed_state,candidate.state)
        self.assert_closed()
        self.assertEqual(self.owner.closed_reason,'observation_expired')
        await self.owner.reconcile();await self.publish()
        self.assert_closed()
        with self.assertRaises(CommandAdmissionError):self.owner.capture_quote(61,'100')

    async def test_lost_ack_missing_readback_then_original_command_resolves_after_expiry(self):
        await self.bootstrapped()
        quote=self.owner.capture_quote(60,'100');identity=self.identity()
        self.transport.fault('commit_command',RuntimeError('synthetic lost response'))
        with patch.object(life,'prepare_protective',wraps=life.prepare_protective) as planner:
            with self.assertRaises(UncertainCommand):
                await self.owner.protect(quote,inputs(60),command_id=identity)
            candidate=self.owner.pending_candidate
            command=self.owner.pending_command
            self.assertEqual(command.command_id,identity)
            self.transport.fault('get_command',None)
            self.assertIsNone(await self.owner.reconcile())
            self.assertIs(self.owner.pending_candidate,candidate)
            self.assertIs(self.owner.pending_command,command)
            self.age(6)
            receipt=await self.owner.reconcile()
        self.assertEqual(planner.call_count,1)
        self.assertEqual(receipt.command.command_id,identity)
        self.assertIs(self.owner.installed_state,candidate.state)
        self.assert_closed()
        self.assertEqual(self.transport.count('commit_command'),2)

    async def test_foreign_owner_ticket_is_rejected_before_planning(self):
        config=await self.bootstrapped()
        other_transport=CommittingTransport()
        other_repo=CommandRepository(other_transport,OWNER,RUN,WORKER,monotonic=self.mono)
        await other_repo.submit(PreparedCommand.create(OWNER,RUN,WORKER,config.run_configuration(),
            config.initial_cash,command_id=self.identity()))
        await other_repo.heartbeat()
        other=module.RehearsalAdmissionOwner(other_repo,other_transport,config,
            wall_clock=self.wall,monotonic=self.mono)
        foreign=other.capture_quote(60,'100')
        count=self.transport.count('commit_command')
        with self.assertRaises(module.OperationalAdmissionError):
            await self.owner.protect(foreign,inputs(60),command_id=self.identity())
        self.assert_closed()
        self.assertEqual(self.transport.count('commit_command'),count)

    async def test_real_warmup_trip_and_delayed_recovery_ack_do_not_authorize_stale_restart(self):
        await self.opened(loss='50')
        halted=self.owner.capture_quote(55802,'97.5')
        await self.owner.protect(halted,inputs(55802),command_id=self.identity())
        await self.publish()
        state=self.owner.installed_state.to_dict()
        self.assertEqual(state['status'],'risk_halted')
        self.assertEqual(state['engine']['cohort']['phase'],'aborted')
        trip=state['engine']['lifecycle']['risk']['trip_id']
        rebound=self.owner.capture_quote(55803,'100')
        await self.owner.protect(rebound,inputs(55803),command_id=self.identity())
        gate=self.gate('commit_command');identity=self.identity()
        task=self.spawn(self.owner.control('recover',inputs(55803),command_id=identity,
            quote=rebound,candle_end=55800,candle_close='120',trip_id=trip))
        await self.entered(gate);candidate=self.owner.pending_candidate
        self.assertEqual(self.owner.installed_state.to_dict()['status'],'risk_halted')
        self.age(6);gate.release.set();receipt=await task
        self.assertEqual(receipt.command.command_id,identity)
        self.assertIs(self.owner.installed_state,candidate.state)
        self.assertEqual(candidate.state.to_dict()['status'],'running')
        self.assertTrue(candidate.state.to_dict()['engine']['lifecycle']['restart_required'])
        self.assert_closed()
        self.assertEqual(await self.publish(),1)
        self.assert_closed()
        with self.assertRaises(CommandAdmissionError):self.owner.capture_quote(55804,'100')

    async def test_risk_trip_identity_exhaustion_closes_owner_without_mutating_old_state(self):
        await self.opened(loss='50')
        previous=self.owner.installed_state
        count=self.transport.count('commit_command')
        quote=self.owner.capture_quote(55802,'97.5')
        with self.assertRaises(module.OperationalAdmissionError):
            await self.owner.protect(quote,inputs(55802,identities=False),command_id=self.identity())
        self.assert_closed()
        self.assertIs(self.owner.installed_state,previous)
        self.assertEqual(previous.to_dict()['status'],'running')
        self.assertEqual(self.transport.count('commit_command'),count)
        with self.assertRaises(CommandAdmissionError):self.owner.capture_quote(55803,'100')

    async def test_event_delivery_expiry_closes_admission_but_finishes_committed_outbox(self):
        await self.opened()
        quote=self.owner.capture_quote(55802,'97')
        await self.owner.protect(quote,inputs(55802),command_id=self.identity())
        candidate=self.owner.pending_candidate
        self.assertIsNotNone(candidate)
        self.assertEqual(len(candidate.transition['events']),8)
        count=self.transport.count('commit_command')
        gate=Gate();self.gates.append(gate)
        delivered=[]
        async def delayed_sink(event):
            delivered.append(event)
            if len(delivered)==1:
                await gate(None,{})
        task=self.spawn(self.owner.publish_pending(delayed_sink))
        await self.entered(gate)
        self.age(5);gate.release.set()
        self.assertEqual(await task,8)
        self.assertIs(self.owner.installed_state,candidate.state)
        self.assertEqual(len({event['event_id'] for event in delivered}),8)
        self.assertEqual(self.transport.count('commit_command'),count)
        self.assertIsNone(self.owner.pending_candidate)
        self.assert_closed()
        self.assertEqual(self.owner.closed_reason,'observation_expired')
        self.assertEqual(await self.owner.publish_pending(delayed_sink),0)
        self.assertEqual(len(delivered),8)

    async def test_cancelled_publication_remains_owned_through_delivery_and_ack(self):
        await self.ready()
        await self.owner.bootstrap(inputs(0),command_id=self.identity())
        gate=Gate();self.gates.append(gate)
        delivered=[]
        async def delayed_sink(event):
            delivered.append(event)
            if len(delivered)==1:
                await gate(None,{})
        task=self.spawn(self.owner.publish_pending(delayed_sink))
        await self.entered(gate);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertFalse(gate.cancelled)
        self.assertTrue(self.owner.busy)
        self.owner.close_admission();gate.release.set();await self.settled()
        self.assertEqual(len(delivered),9)
        self.assertEqual(len(self.transport.acknowledged),9)
        self.assertIsNone(self.owner.pending_candidate)
        self.assert_closed()

    async def test_invalid_readback_never_installs_or_replans_pending_candidate(self):
        await self.bootstrapped()
        previous=self.owner.installed_state
        quote=self.owner.capture_quote(60,'100');identity=self.identity()
        self.transport.fault('commit_command',RuntimeError('lost response'))
        with self.assertRaises(UncertainCommand):
            await self.owner.protect(quote,inputs(60),command_id=identity)
        candidate=self.owner.pending_candidate
        async def corrupt_receipt(result,_args):
            result['response']['reserve']='999'
            return result
        self.transport.fault('get_command',corrupt_receipt)
        with self.assertRaises(UncertainCommand):await self.owner.reconcile()
        self.assertIs(self.owner.installed_state,previous)
        self.assertIs(self.owner.pending_candidate,candidate)
        self.assertEqual(self.owner.pending_command.command_id,identity)
        self.assertEqual(self.transport.count('commit_command'),2)
        await self.owner.reconcile()
        self.assertIs(self.owner.installed_state,candidate.state)

    async def test_install_failure_retains_receipt_and_reconcile_installs_once(self):
        await self.bootstrapped()
        quote=self.owner.capture_quote(60,'100')
        previous=self.owner.installed_state
        with patch.object(self.owner._coordinator,'_install',side_effect=RuntimeError('install failed')):
            with self.assertRaises(RuntimeError):
                await self.owner.protect(quote,inputs(60),command_id=self.identity())
        candidate=self.owner.pending_candidate
        self.assertIs(self.owner.installed_state,previous)
        self.assertIsNotNone(self.owner.pending_receipt)
        self.assert_closed()
        calls=self.transport.count('commit_command')
        await self.owner.reconcile()
        self.assertIs(self.owner.installed_state,candidate.state)
        self.assertEqual(self.transport.count('commit_command'),calls)
        self.assert_closed()


    async def test_missing_command_id_rejects_before_planning_without_uuid_fallback(self):
        await self.ready()
        with patch.object(life,'bootstrap',wraps=life.bootstrap) as planner, \
             patch.object(command_protocol,'uuid4',side_effect=AssertionError('unexpected identity generation')) as generate:
            with self.assertRaises(module.OperationalAdmissionError):
                await self.owner.bootstrap(inputs(0),command_id=None)
        planner.assert_not_called()
        generate.assert_not_called()
        self.assert_closed()
        self.assertEqual(self.transport.count('commit_command'),0)
        self.assertIsNone(self.owner.pending_candidate)

    async def test_creation_command_id_cannot_be_reused_for_bootstrap(self):
        await self.ready()
        identity=self.repo.last_receipt.command.command_id
        with patch.object(life,'bootstrap',wraps=life.bootstrap) as planner:
            with self.assertRaises(module.OperationalAdmissionError):
                await self.owner.bootstrap(inputs(0),command_id=identity)
        planner.assert_not_called()
        self.assertEqual(self.owner.closed_reason,'command_identity_reused')
        self.assertEqual(self.transport.count('commit_command'),0)
        self.assert_closed()

    async def test_acknowledged_prior_command_id_cannot_be_reused_after_outbox_drain(self):
        await self.bootstrapped()
        identity=self.repo.last_receipt.command.command_id
        quote=self.owner.capture_quote(60,'100')
        before=self.owner.installed_state
        count=self.transport.count('commit_command')
        with patch.object(life,'prepare_protective',wraps=life.prepare_protective) as planner:
            with self.assertRaises(module.OperationalAdmissionError):
                await self.owner.protect(quote,inputs(60),command_id=identity)
        planner.assert_not_called()
        self.assertEqual(self.owner.closed_reason,'command_identity_reused')
        self.assertIs(self.owner.installed_state,before)
        self.assertEqual(self.transport.count('commit_command'),count)

    async def test_command_capacity_counts_creation_and_committed_bootstrap(self):
        self.assertEqual(module.MAX_OWNED_COMMANDS,4096)
        with patch.object(module,'MAX_OWNED_COMMANDS',2):
            await self.bootstrapped()
            self.assertEqual(self.transport.count('create_run'),1)
            self.assertEqual(self.transport.count('commit_command'),1)
            quote=self.owner.capture_quote(60,'100')
            before=self.owner.installed_state
            with patch.object(life,'prepare_protective',wraps=life.prepare_protective) as planner:
                with self.assertRaises(module.OperationalAdmissionError):
                    await self.owner.protect(quote,inputs(60),command_id=self.identity())
            planner.assert_not_called()
            self.assertEqual(self.owner.closed_reason,'command_capacity_exhausted')
            self.assertIs(self.owner.installed_state,before)
            self.assertEqual(self.transport.count('commit_command'),1)
        self.assert_closed()
        with self.assertRaises(module.OperationalAdmissionError):
            await self.owner.protect(quote,inputs(60),command_id=self.identity())

    async def test_task_factory_cancellation_closes_without_planning_or_ticket_retry(self):
        await self.bootstrapped()
        quote=self.owner.capture_quote(60,'100')
        before=self.owner.installed_state
        count=self.transport.count('commit_command')
        with patch.object(life,'prepare_protective',wraps=life.prepare_protective) as planner, \
             patch.object(module.asyncio,'create_task',side_effect=asyncio.CancelledError()):
            with self.assertRaises(module.OperationalAdmissionError):
                await self.owner.protect(quote,inputs(60),command_id=self.identity())
        planner.assert_not_called()
        self.assertFalse(self.owner.busy)
        self.assertEqual(self.owner.closed_reason,'scheduling_failed')
        self.assertIs(self.owner.installed_state,before)
        self.assertIsNone(self.owner.pending_candidate)
        self.assertEqual(self.transport.count('commit_command'),count)
        with self.assertRaises(module.OperationalAdmissionError):
            await self.owner.protect(quote,inputs(60),command_id=self.identity())
        self.assertEqual(self.owner.closed_reason,'scheduling_failed')

    async def test_receipt_budget_and_runtime_clocks_require_finite_exact_numeric_types(self):
        config=await self.ready()
        for invalid in (0,-1,True,float('inf'),float('nan'),60.001,'5'):
            with self.subTest(budget=invalid),self.assertRaises(module.OperationalAdmissionError):
                module.RehearsalAdmissionOwner(self.repo,self.transport,config,
                    wall_clock=self.wall,monotonic=self.mono,max_wait_seconds=invalid)
        for invalid in (float('nan'),float('inf'),-1,True,'1000'):
            for which in ('wall','mono'):
                with self.subTest(clock=which,value=invalid):
                    self.setUpClocksForFreshOwner()
                    await self.ready()
                    getattr(self,which).value=invalid
                    with self.assertRaises(module.OperationalAdmissionError):
                        self.owner.capture_quote(60,'100')
                    self.assertEqual(self.owner.closed_reason,'clock_invalid')
                    self.assert_closed()
                    self.assertEqual(self.transport.count('commit_command'),0)

    async def test_quote_constructor_receipts_and_exact_observation_are_immutable(self):
        await self.ready()
        quote=self.owner.capture_quote(60,'100.000000000000000001')
        self.assertEqual(quote.observation.price,'100.000000000000000001')
        self.assertEqual((quote.received_at,quote.received_monotonic),(1000.0,100.0))
        with self.assertRaises(module.OperationalAdmissionError):
            module.RehearsalQuote(quote.observation,1000.0,100.0,object())
        with self.assertRaises(module.OperationalAdmissionError):
            replace(quote,received_at=1001.0)
        for target,key,value in ((quote,'received_at',1001),(quote,'received_monotonic',101),
                                 (quote.observation,'price','200'),(quote.observation,'timestamp',61)):
            with self.subTest(key=key),self.assertRaises(FrozenInstanceError):
                setattr(target,key,value)
        self.assertTrue(self.owner.accepting)

    async def test_repository_clock_exception_closes_owner_despite_healthy_owner_clocks(self):
        for failure in (RuntimeError('private clock failure'),asyncio.CancelledError()):
            with self.subTest(failure=type(failure).__name__):
                self.setUpClocksForFreshOwner()
                await self.bootstrapped()
                calls=self.transport.count('heartbeat')
                with patch.object(self.repo,'_clock',side_effect=failure):
                    self.assertFalse(self.owner.accepting)
                self.assertEqual(self.owner.closed_reason,'repository_admission_invalid')
                self.assert_closed()
                with self.assertRaises(module.OperationalAdmissionError):
                    await self.owner.heartbeat()
                self.assertEqual(self.transport.count('heartbeat'),calls)
                self.assertEqual(self.owner.closed_reason,'repository_admission_invalid')
