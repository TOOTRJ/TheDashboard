"""Durable owner controls, warmup Stop and bounded restored history."""
import asyncio
import unittest
from uuid import UUID

from tests.security_support import deny_network
with deny_network():
    from tests.test_prospective_runtime import MemoryJournal
    from tests.test_prospective_ga_v3_model import fill_policy, new_inputs, inputs_for_mark
    from tests.test_prospective_source_v3 import mark, seal, END, OWNER, RUN, MARKET, PROCESS, PRINCIPAL, PACKAGE
    from vonneumann.market import prospective_source_v3 as source
    from vonneumann.research.prospective_ga_v3_policy import V3Config, SourceBinding
    from vonneumann.server.prospective_service import ProspectivePaperService, SourceBatch
    from vonneumann.core.prospective_runtime import ProspectiveRuntime, RuntimeRefused, JournalRejected


class ControlledJournal(MemoryJournal):
    def __init__(self):
        super().__init__()
        self.controls = []

    async def scan(self, after_sequence=0, limit=100):
        # Deliberately return a partial page: only empty ends the read.
        return self.rows[after_sequence:after_sequence+1]

    async def control(self, request_id, action):
        for row in self.controls:
            if row['request_id'] == request_id:
                if row['action'] != action:
                    raise ValueError('control identity collision')
                return row
        row = {'owner_id': OWNER, 'run_id': RUN, 'request_id': request_id,
            'action': action, 'sequence': len(self.controls)+1}
        self.controls.append(row)
        return row

    async def latest_control(self):
        return self.controls[-1] if self.controls else None

    async def head(self):
        return {'sequence': len(self.rows), 'sha256': self.rows[-1].sha256 if self.rows else None}


class EmptyArtifacts:
    reader = staticmethod(lambda *args: None)
    async def restore(self):
        pass


class WaitingFeed:
    current_binding = SourceBinding(OWNER, RUN, MARKET, PROCESS, PRINCIPAL, PACKAGE)

    def __init__(self):
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.calls, self.restored, self.closed = 0, False, False

    async def restore(self):
        self.restored = True

    async def next_observation(self):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return SourceBatch(mark(0))

    def status(self):
        return {'observed_minutes': 1, 'required_minutes': 915}

    async def close(self):
        self.closed = True


class ProspectiveServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        guard = deny_network(); guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)
        self.journal, self.feed = ControlledJournal(), WaitingFeed()
        self.config = V3Config(OWNER, RUN, MARKET, self.feed.current_binding, fill_policy())
        self.service = ProspectivePaperService(self.journal, self.feed,
            self.config, artifacts=EmptyArtifacts())

    async def test_stop_during_inflight_warmup_is_durable_and_bars_bootstrap(self):
        start_id, stop_id = str(UUID(int=700)), str(UUID(int=701))
        await self.service.start(OWNER, start_id)
        await asyncio.wait_for(self.feed.entered.wait(), 1)
        status = await self.service.stop(OWNER, stop_id)
        self.assertEqual(self.journal.controls[-1]['action'], 'stop')
        self.assertEqual(status['last_request_id'], stop_id)
        self.assertEqual(status['phase'], 'stopping')
        self.feed.release.set()
        await asyncio.wait_for(self.service._task, 2)
        status = await self.service.status(OWNER)
        self.assertEqual(status['phase'], 'stopped')
        self.assertIsNone(status['projection'])
        self.assertEqual(status['sequence'], 0)
        self.assertEqual(self.feed.calls, 1)
        await self.service.close()
        self.assertTrue(self.feed.closed)

    async def test_replayed_old_start_cannot_override_later_stop(self):
        start_id, stop_id = str(UUID(int=702)), str(UUID(int=703))
        await self.journal.control(start_id, 'start')
        await self.journal.control(stop_id, 'stop')
        await self.service.wait_ready()
        await self.service._task
        status = await self.service.start(OWNER, start_id)
        self.assertEqual(status['last_request_id'], stop_id)
        self.assertEqual(status['phase'], 'stopped')
        self.assertEqual(self.feed.calls, 0)
        await self.service.close()

    async def test_saved_start_restores_collection_and_owner_privacy(self):
        await self.journal.control(str(UUID(int=704)), 'start')
        await self.service.initialize()
        await asyncio.wait_for(self.feed.entered.wait(), 1)
        self.assertTrue(self.feed.restored)
        with self.assertRaises(RuntimeRefused):
            await self.service.status(str(UUID(int=999)))
        with self.assertRaises(RuntimeRefused):
            await self.service.stop(str(UUID(int=999)), str(UUID(int=705)))
        await self.service.stop(OWNER, str(UUID(int=706)))
        self.feed.release.set()
        await self.service._task
        await self.service.close()

    async def test_history_bounds_refuse_bool_or_negative_cursor(self):
        await self.service.wait_ready()
        for cursor, limit in ((True, 1), (-1, 1), (0, 0), (0, 101)):
            with self.subTest(cursor=cursor, limit=limit), self.assertRaises(RuntimeRefused):
                await self.service.history(OWNER, cursor, limit)
        await self.service.close()

    async def test_stop_is_durable_during_background_recovery_without_partial_projection(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def blocked_scan(**kwargs):
            entered.set()
            await release.wait()
            return []
        self.journal.scan = blocked_scan
        await self.service.initialize()
        await asyncio.wait_for(entered.wait(), 1)
        status = await self.service.status(OWNER)
        self.assertEqual(status['phase'], 'recovering')
        self.assertTrue(status['busy'])
        self.assertIsNone(status['projection'])
        stop_id = str(UUID(int=799))
        stopped = await self.service.stop(OWNER, stop_id)
        self.assertEqual(stopped['last_request_id'], stop_id)
        self.assertEqual(self.journal.controls[-1]['action'], 'stop')
        release.set()
        await self.service.wait_ready()
        await self.service._task
        self.assertEqual((await self.service.status(OWNER))['phase'], 'stopped')
        self.assertEqual(self.feed.calls, 0)
        await self.service.close()

    async def test_known_archived_provider_failure_waits_then_collects_without_economic_rows(self):
        calls, intervals = [], []
        async def next_observation():
            calls.append(True)
            if len(calls) == 1:
                return SourceBatch(None, safe_error='provider_sample_unavailable')
            self.feed.entered.set()
            await self.feed.release.wait()
            return SourceBatch(mark(0))
        async def pace(seconds):
            intervals.append(seconds)
            await asyncio.sleep(0)
        self.feed.next_observation = next_observation
        self.service._sleep = pace
        await self.service.start(OWNER, str(UUID(int=798)))
        await asyncio.wait_for(self.feed.entered.wait(), 1)
        status = await self.service.status(OWNER)
        self.assertEqual(status['phase'], 'waiting_data')
        self.assertFalse(status['requires_reconciliation'])
        self.assertEqual(status['last_failure'], 'provider_sample_unavailable')
        self.assertEqual(len(intervals), 1)
        self.assertEqual(self.journal.rows, [])
        await self.service.stop(OWNER, str(UUID(int=797)))
        self.feed.release.set()
        await self.service._task
        await self.service.close()

    async def test_stop_between_prepared_phases_discards_decision_and_restart_replays_exactly(self):
        marks = tuple(mark(index, price='100') for index in range(915))
        history = source.derive_sampled_history(seal(marks))
        series = source.derive_close_series(history, expected_history_sha256=history.sha256)
        observation = mark(915, price='100')
        artifacts = {('history', history.sha256): history, ('series', series.sha256): series,
            ('mark', observation.sha256): observation}
        reader = lambda kind, digest: artifacts[(kind, digest)]
        runtime = ProspectiveRuntime(OWNER, RUN, self.journal, reader)
        await runtime.submit(runtime.prepare_bootstrap(self.config, history, series,
            inputs=new_inputs((END+5)*1_000_000, 54_905_000_000)), command_id=str(UUID(int=800)))
        committed, release = asyncio.Event(), asyncio.Event()
        original_append = self.journal.append
        async def pause_protective(entry, **kwargs):
            original = await original_append(entry, **kwargs)
            if entry.to_dict()['witness']['kind'] == 'protective':
                committed.set()
                await release.wait()
            return original
        self.journal.append = pause_protective
        class ReadyArtifacts:
            async def restore(self): pass
        ready = ReadyArtifacts(); ready.reader = reader
        async def next_observation():
            return SourceBatch(observation)
        self.feed.next_observation = next_observation
        inputs = inputs_for_mark(observation, serial=100, generation=1)
        service = ProspectivePaperService(self.journal, self.feed, self.config,
            artifacts=ready, clock=lambda binding: inputs.clock)
        await service.start(OWNER, str(UUID(int=801)))
        await asyncio.wait_for(committed.wait(), 10)
        await service.stop(OWNER, str(UUID(int=802)))
        release.set()
        await asyncio.wait_for(service._task, 10)
        kinds = [entry.to_dict()['witness']['kind'] for entry in self.journal.rows]
        self.assertEqual(kinds, ['bootstrap', 'protective', 'control'])
        self.assertEqual(service.runtime.state.to_dict()['status'], 'stopped')
        restored = ProspectiveRuntime(OWNER, RUN, self.journal, reader)
        restored.restore(self.journal.rows)
        self.assertEqual(restored.state.to_dict(), service.runtime.state.to_dict())
        self.assertTrue(all(not assessment['selection_eligible'] for record in restored.history
            for assessment in record['assessments']))
        await service.close()

    async def test_native_stop_wins_prepared_decision_and_completes_without_local_stop_request(self):
        marks = tuple(mark(index, price='100') for index in range(915))
        history = source.derive_sampled_history(seal(marks))
        series = source.derive_close_series(history, expected_history_sha256=history.sha256)
        observation = mark(915, price='100')
        artifacts = {('history', history.sha256): history, ('series', series.sha256): series,
            ('mark', observation.sha256): observation}
        reader = lambda kind, digest: artifacts[(kind, digest)]
        runtime = ProspectiveRuntime(OWNER, RUN, self.journal, reader)
        await runtime.submit(runtime.prepare_bootstrap(self.config, history, series,
            inputs=new_inputs((END+5)*1_000_000, 54_905_000_000)), command_id=str(UUID(int=810)))
        original_append = self.journal.append
        rejected = []
        async def native_stop_before_decision(entry, **kwargs):
            if entry.to_dict()['witness']['kind'] == 'decision':
                await self.journal.control(str(UUID(int=812)), 'stop')
                # A second worker has already committed the model Stop, too.
                # The losing service must replay this advanced native prefix;
                # appending another Stop against its old head would be stale.
                remote = ProspectiveRuntime(OWNER, RUN, self.journal, reader)
                remote.restore(self.journal.rows)
                remote_inputs = inputs_for_mark(observation, serial=111, generation=1)
                await remote.submit(remote.prepare_control('stop', remote_inputs),
                    command_id=str(UUID(int=813)))
                rejected.append(entry)
                raise JournalRejected(entry.wire)
            return await original_append(entry, **kwargs)
        self.journal.append = native_stop_before_decision
        class ReadyArtifacts:
            async def restore(self): pass
        ready = ReadyArtifacts(); ready.reader = reader
        async def next_observation():
            return SourceBatch(observation)
        self.feed.next_observation = next_observation
        inputs = inputs_for_mark(observation, serial=110, generation=1)
        service = ProspectivePaperService(self.journal, self.feed, self.config,
            artifacts=ready, clock=lambda binding: inputs.clock)
        await service.start(OWNER, str(UUID(int=811)))
        await service.wait_ready()
        await asyncio.wait_for(service._task, 15)
        self.assertEqual(len(rejected), 1)
        self.assertFalse(service.runtime.pending)
        self.assertEqual(service.runtime.state.to_dict()['status'], 'stopped')
        self.assertEqual([entry.to_dict()['witness']['kind'] for entry in self.journal.rows],
            ['bootstrap', 'protective', 'control'])
        self.assertEqual((await service.status(OWNER))['last_request_id'], str(UUID(int=812)))
        await service.close()


if __name__ == '__main__':
    unittest.main()
