"""Version-four lifecycle acknowledgments preserve the existing ownership gate."""
from __future__ import annotations

import asyncio
import unittest
from uuid import UUID

from tests.security_support import deny_network
from tests.test_exact_rehearsal import ALGORITHMS, OWNER, RUN, WORKER, inputs
from tests.test_exact_lifecycle import initial
from tests.test_transition_coordinator import Clock, CommittingTransport, Gate
from vonneumann.core import exact_lifecycle as life
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandRepository, CommandAdmissionError, UncertainCommand
from vonneumann.db.transition_coordinator import TransitionCoordinator


class LifecycleCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        guard = deny_network(); guard.__enter__()
        self.addCleanup(guard.__exit__,None,None,None)
        self.ids = 9500000

    def identity(self):
        self.ids += 1
        return str(UUID(int=self.ids))

    async def sink(self,event):
        self.delivered.append(event)

    async def create(self, algorithm='genetic_algorithm', loss='3000'):
        self.clock = Clock(); self.transport = CommittingTransport(); self.delivered = []
        self.repo = CommandRepository(self.transport,OWNER,RUN,WORKER,monotonic=self.clock)
        cfg,founders = initial(algorithm,loss=loss)
        await self.repo.submit(PreparedCommand.create(OWNER,RUN,WORKER,cfg.run_configuration(),'1000',command_id=self.identity()))
        self.coordinator = TransitionCoordinator(self.repo,self.transport)
        await self.coordinator.heartbeat()
        await self.adopt(founders)
        return founders

    async def adopt(self,candidate):
        receipt = await self.coordinator.submit(candidate,command_id=self.identity())
        self.assertEqual(receipt.command.expected_request['payload']['version'],4)
        self.assertIs(self.coordinator.installed_state,candidate.state)
        await self.coordinator.publish_pending(self.sink)
        return candidate

    async def advance(self,state,stamp,price='100',end=None,close=None):
        protected = life.prepare_protective(state,life.ExactObservation(stamp,price),inputs(stamp))
        await self.adopt(protected)
        decided = life.prepare_decision(protected.state,life.ExactObservation(stamp,price,end,close),inputs(stamp,1))
        return await self.adopt(decided)

    async def opened(self,loss='3000'):
        current = await self.create(loss=loss)
        for bar in range(1,63):
            close = '100' if bar < 61 else '80' if bar == 61 else '120'
            current = await self.advance(current.state,bar*900,end=bar*900,close=close)
        return await self.advance(current.state,55801)

    async def test_all_solvers_lost_pause_ack_reconciles_same_id_then_resume_and_warmup(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                before = await self.create(algorithm)
                pause = life.prepare_control(before.state,'pause',inputs(1))
                self.transport.fault('commit_command',OSError('lost acknowledged pause'))
                identity = self.identity()
                with self.assertRaises(UncertainCommand):
                    await self.coordinator.submit(pause,command_id=identity)
                self.assertIs(self.coordinator.installed_state,before.state)
                self.assertFalse(self.coordinator.accepting)
                commits = self.transport.count('commit_command')
                receipt = await self.coordinator.reconcile()
                self.assertEqual(receipt.command.command_id,identity)
                self.assertEqual(self.transport.count('commit_command'),commits)
                self.assertIs(self.coordinator.installed_state,pause.state)
                await self.coordinator.publish_pending(self.sink)
                # Uncertain transport invalidates local lease authority even
                # when readback proves the command committed. Renew explicitly.
                await self.coordinator.heartbeat()
                resume = life.prepare_control(pause.state,'resume',inputs(2))
                await self.adopt(resume)
                warmed = await self.advance(resume.state,900,end=900,close='100')
                self.assertEqual(warmed.state.to_dict()['engine']['ema']['count'],1)
                self.assertTrue(warmed.state.to_dict()['engine']['lifecycle']['restart_required'])
                self.assertTrue(self.coordinator.accepting)

    async def test_stop_ack_can_settle_after_drain_and_preserves_open_positions(self):
        before = await self.opened()
        positions = before.state.to_dict()['positions']
        self.assertEqual(sum(not p['closed'] for p in positions),8)
        stop = life.prepare_control(before.state,'stop',inputs(55802))
        gate = Gate(); self.transport.fault('commit_command',gate)
        task = asyncio.create_task(self.coordinator.submit(stop,command_id=self.identity()))
        try:
            await asyncio.wait_for(gate.entered.wait(),2)
            self.coordinator.close_admission()
            self.assertIs(self.coordinator.installed_state,before.state)
            gate.release.set(); await task
            self.assertIs(self.coordinator.installed_state,stop.state)
            self.assertEqual(stop.state.to_dict()['positions'],positions)
            await self.coordinator.publish_pending(self.sink)
            self.assertEqual(self.repo.status,'stopped')
            self.assertFalse(self.coordinator.accepting)
            with self.assertRaises(CommandAdmissionError): await self.coordinator.heartbeat()
        finally:
            gate.release.set(); await asyncio.gather(task,return_exceptions=True)

    async def test_drain_before_control_does_not_silently_write_or_invent_stopped_state(self):
        before = await self.create()
        stop = life.prepare_control(before.state,'stop',inputs(1))
        self.coordinator.close_admission()
        calls = self.transport.count('commit_command')
        with self.assertRaises(CommandAdmissionError):
            await self.coordinator.submit(stop,command_id=self.identity())
        self.assertEqual(self.transport.count('commit_command'),calls)
        self.assertIs(self.coordinator.installed_state,before.state)
        self.assertEqual(self.repo.status,'running')

    async def test_delayed_recovery_ack_cannot_restart_from_the_recovery_observation(self):
        before = await self.opened(loss='50')
        tripped = await self.adopt(life.prepare_protective(before.state,life.ExactObservation(55802,'97.5'),inputs(55802)))
        rebound = await self.adopt(life.prepare_protective(tripped.state,life.ExactObservation(55803,'100'),inputs(55803)))
        trip = rebound.state.to_dict()['engine']['lifecycle']['risk']['trip_id']
        recovered = life.prepare_control(rebound.state,'recover',inputs(55803),life.ExactObservation(55803,'100',55800,'120'),trip)
        gate = Gate(); self.transport.fault('commit_command',gate)
        task = asyncio.create_task(self.coordinator.submit(recovered,command_id=self.identity()))
        try:
            await asyncio.wait_for(gate.entered.wait(),2)
            self.assertIs(self.coordinator.installed_state,rebound.state)
            self.assertFalse(self.coordinator.accepting)
            gate.release.set(); await task
            await self.coordinator.publish_pending(self.sink)
            with self.assertRaises(ValueError):
                life.prepare_decision(self.coordinator.installed_state,life.ExactObservation(55803,'100'),inputs(55803,1))
            following = await self.advance(self.coordinator.installed_state,55804)
            state = following.state.to_dict()
            self.assertEqual(state['engine']['lifecycle']['search_epoch'],1)
            self.assertEqual(state['engine']['cohort']['phase'],'warming')
            self.assertTrue(all(p['closed'] for p in state['positions']))
            self.assertIsNone(state['engine']['last_evaluation']['selection'])
        finally:
            gate.release.set(); await asyncio.gather(task,return_exceptions=True)
