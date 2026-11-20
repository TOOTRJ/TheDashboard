"""Durable owner controls, warmup Stop and bounded restored history."""
import asyncio
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import deny_network
with deny_network():
    from tests.test_prospective_runtime import MemoryJournal
    from tests.test_prospective_ga_v3_model import fill_policy, new_inputs, inputs_for_mark
    from tests.test_prospective_source_v3 import mark, seal, replaced_mark, END, OWNER, RUN, MARKET, PROCESS, PRINCIPAL, PACKAGE
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

    async def seeded_service(self, observations, *, sleep=asyncio.sleep):
        # These are literal provider-derived originals, not an imported JSON
        # state. Seed the real model and replay that journal through the service.
        if not hasattr(type(self), '_seed_history'):
            marks = tuple(mark(index, price='100') for index in range(915))
            type(self)._seed_history = source.derive_sampled_history(seal(marks))
            type(self)._seed_series = source.derive_close_series(self._seed_history,
                expected_history_sha256=self._seed_history.sha256)
        history, series = self._seed_history, self._seed_series
        artifacts = {('history', history.sha256): history, ('series', series.sha256): series,
            **{('mark', item.sha256): item for item in observations}}
        reader = lambda kind, digest: artifacts[(kind, digest)]
        runtime = ProspectiveRuntime(OWNER, RUN, self.journal, reader)
        await runtime.submit(runtime.prepare_bootstrap(self.config, history, series,
            inputs=new_inputs((END+5)*1_000_000, 54_905_000_000)), command_id=str(UUID(int=900)))
        class ReadyArtifacts:
            async def restore(self): pass
        ready = ReadyArtifacts(); ready.reader = reader
        service = ProspectivePaperService(self.journal, self.feed, self.config,
            artifacts=ready, sleep=sleep)
        self.addAsyncCleanup(service.close)
        return service, runtime.state.to_dict(), reader

    async def test_expired_archived_mark_waits_before_preparation_then_next_fresh_sample_runs(self):
        stale, fresh = mark(915, price='100'), mark(916, price='100')
        calls, phases, clocks = [], [], []
        waiting, release = asyncio.Event(), asyncio.Event()
        service, initial, reader = await self.seeded_service((stale, fresh))
        current = [inputs_for_mark(stale, serial=300, generation=1, offset=5_000_001)]
        def logical_inputs(**kwargs):
            clocks.append(current[0].clock)
            value = current[0]
            return new_inputs(value.event_us, value.clock.monotonic_us,
                serial=300+len(clocks), generation=1)
        service._inputs = logical_inputs
        async def next_observation():
            index = len(calls); calls.append(index)
            if index == 0:
                return SourceBatch(stale)
            if index == 1:
                current[0] = inputs_for_mark(fresh, serial=310, generation=1)
                return SourceBatch(fresh)
            waiting.set(); await release.wait()
            return SourceBatch(fresh)
        self.feed.next_observation = next_observation
        stale_wire, fresh_wire = stale.wire, fresh.wire
        async def paced(seconds):
            phases.append(service._phase)
            self.assertEqual(seconds, service._interval)
            if len(phases) == 1:
                status = await service.status(OWNER)
                self.assertEqual((status['phase'], status['last_failure']),
                    ('waiting_data', 'current_mark_expired'))
                self.assertFalse(status['requires_reconciliation'])
                self.assertEqual(service.runtime.state.to_dict(), initial)
                self.assertEqual(len(self.journal.rows), 1)
                self.assertFalse(service.runtime.pending)
                protective.assert_not_called(); observation.assert_not_called()
            await asyncio.sleep(0)
        service._sleep = paced
        try:
            with patch.object(service.runtime, 'prepare_protective', wraps=service.runtime.prepare_protective) as protective, \
                    patch.object(service.runtime, 'prepare_observation', wraps=service.runtime.prepare_observation) as observation:
                await service.start(OWNER, str(UUID(int=901)))
                await asyncio.wait_for(waiting.wait(), 15)
                status = await service.status(OWNER)
                self.assertEqual((status['phase'], status['last_failure']), ('running', None))
                self.assertEqual(phases, ['waiting_data', 'running'])
                self.assertEqual(protective.call_count, 1)
                self.assertEqual(observation.call_count, 1)
                self.assertEqual([row.to_dict()['witness']['kind'] for row in self.journal.rows],
                    ['bootstrap', 'protective', 'decision'])
                self.assertEqual([row.to_dict()['witness']['mark_sha256'] for row in self.journal.rows[1:]],
                    [fresh.sha256, fresh.sha256])
                self.assertEqual((stale.wire, fresh.wire), (stale_wire, fresh_wire))
                await service.stop(OWNER, str(UUID(int=902)))
                release.set(); await service._task
            restored = ProspectiveRuntime(OWNER, RUN, self.journal, reader)
            restored.restore(self.journal.rows)
            self.assertEqual(restored.state.to_dict(), service.runtime.state.to_dict())
            self.assertEqual(restored.state.to_dict()['status'], 'stopped')
        finally:
            release.set()

    async def test_stop_while_expired_sample_waits_commits_only_stop_and_no_replacement_sample(self):
        # This sample is beyond the next completed-bar boundary. An expired
        # sample must not reach even the history-unavailable protection branch.
        stale = mark(930, price='100')
        waiting, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def paced(_):
            waiting.set(); await release.wait()
        service, initial, reader = await self.seeded_service((stale,), sleep=paced)
        cutoff = (inputs_for_mark(stale, serial=320).clock.wall_lower_us-source.COMPLETION_MARGIN_US) // (
            source.BAR_SECONDS*1_000_000) * source.BAR_SECONDS
        self.assertNotEqual(initial['source']['history_end'], cutoff)
        serial = [320]
        def logical_inputs(**kwargs):
            serial[0] += 1
            return inputs_for_mark(stale, serial=serial[0], generation=1, offset=5_000_001)
        service._inputs = logical_inputs
        async def next_observation():
            calls.append(stale.sha256)
            return SourceBatch(stale)
        self.feed.next_observation = next_observation
        try:
            await service.start(OWNER, str(UUID(int=903)))
            await asyncio.wait_for(waiting.wait(), 15)
            self.assertEqual(service.runtime.state.to_dict(), initial)
            self.assertEqual(len(self.journal.rows), 1)
            stop_id = str(UUID(int=904))
            acknowledgement = await service.stop(OWNER, stop_id)
            self.assertEqual(acknowledgement['last_request_id'], stop_id)
            self.assertEqual(self.journal.controls[-1]['action'], 'stop')
            release.set(); await asyncio.wait_for(service._task, 10)
            status = await service.status(OWNER)
            self.assertEqual((status['phase'], status['last_request_id']), ('stopped', stop_id))
            self.assertEqual(calls, [stale.sha256])
            self.assertEqual([row.to_dict()['witness']['kind'] for row in self.journal.rows],
                ['bootstrap', 'control'])
            self.assertEqual(service.runtime.state.to_dict()['positions'], initial['positions'])
            restored = ProspectiveRuntime(OWNER, RUN, self.journal, reader)
            restored.restore(self.journal.rows)
            self.assertEqual(restored.state.to_dict(), service.runtime.state.to_dict())
        finally:
            release.set()

    async def test_expired_sample_with_malformed_proof_wrong_scope_or_causality_still_fails_closed(self):
        stale = mark(915, price='100')
        row = stale.to_dict()
        expired = inputs_for_mark(stale, serial=330, generation=1, offset=5_000_001)
        for label, sample, inputs in (
            ('malformed_policy_hash', replaced_mark(stale, source_policy_sha256='f'*64), expired),
            ('wrong_epoch', stale, new_inputs(expired.event_us, expired.clock.monotonic_us,
                serial=331, generation=1, epoch=str(UUID(int=999)))),
            ('before_native_readback', stale, new_inputs(int(row['reference']['available_at_upper_us'])-1,
                expired.clock.monotonic_us, serial=332, generation=1)),
        ):
            with self.subTest(label=label):
                self.journal, self.feed = ControlledJournal(), WaitingFeed()
                service, initial, _ = await self.seeded_service((sample,))
                service._inputs = lambda **kwargs: inputs
                calls, intervals = [], []
                async def next_observation():
                    calls.append(label); return SourceBatch(sample)
                async def paced(seconds): intervals.append(seconds)
                self.feed.next_observation, service._sleep = next_observation, paced
                await service.start(OWNER, str(UUID(int=905)))
                await service.wait_ready()
                await asyncio.wait_for(service._task, 15)
                status = await service.status(OWNER)
                self.assertEqual((status['phase'], status['last_failure']), ('failed', 'paper_operation_failed'))
                self.assertEqual(calls, [label]); self.assertEqual(intervals, [])
                self.assertEqual(service.runtime.state.to_dict(), initial)
                self.assertEqual(len(self.journal.rows), 1)
                self.assertFalse(service.runtime.pending)
                await service.close()

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

    async def test_external_native_stop_during_warmup_ends_without_another_provider_call(self):
        start_id, stop_id = str(UUID(int=824)), str(UUID(int=825))
        self.feed.release.set()
        intervals = []
        async def native_stop(_):
            intervals.append(self.service._phase)
            await self.journal.control(stop_id, 'stop')
        self.service._sleep = native_stop
        await self.service.start(OWNER, start_id)
        await self.service.wait_ready()
        await asyncio.wait_for(self.service._task, 2)
        result = await self.service.status(OWNER)
        self.assertEqual(result['phase'], 'stopped')
        self.assertEqual(result['last_request_id'], stop_id)
        self.assertFalse(result['requires_reconciliation'])
        self.assertEqual(intervals, ['warming_up'])
        self.assertEqual(self.feed.calls, 1)
        self.assertEqual(self.journal.rows, [])
        self.assertEqual([(row['action'], row['request_id']) for row in self.journal.controls],
            [('start', start_id), ('stop', stop_id)])
        await self.service.close()

    async def test_local_stop_racing_a_retained_start_poll_cannot_launch_collection_or_replace_ack(self):
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.journal.latest_control
        async def held_poll():
            result = await original()
            if asyncio.current_task() is self.service._task:
                entered.set(); await release.wait()
            return result
        self.journal.latest_control = held_poll
        await self.service.start(OWNER, str(UUID(int=826)))
        await asyncio.wait_for(entered.wait(), 1)
        stop_id = str(UUID(int=827))
        result = await self.service.stop(OWNER, stop_id)
        self.assertEqual(result['last_request_id'], stop_id)
        release.set(); await asyncio.wait_for(self.service._task, 2)
        self.assertEqual((await self.service.status(OWNER))['last_request_id'], stop_id)
        self.assertEqual((await self.service.status(OWNER))['phase'], 'stopped')
        self.assertEqual(self.feed.calls, 0)
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

    async def test_bar_boundary_crossing_waits_for_exact_history_but_still_protects_and_gap_stays_stoppable(self):
        from types import SimpleNamespace
        from vonneumann.server.prospective_source_feed import ProspectiveSourceFeed
        marks = tuple(mark(index, price='100') for index in range(946))
        history = source.derive_sampled_history(seal(marks[:915]))
        series = source.derive_close_series(history, expected_history_sha256=history.sha256)
        advanced = source.derive_sampled_history(seal(marks[900:930], start=END-900,
            end=END+900, seal_id=str(UUID(int=820))), previous=history,
            expected_previous_sha256=history.sha256)
        advanced_series = source.derive_close_series(advanced, expected_history_sha256=advanced.sha256)
        observations = (marks[930], marks[931], marks[945])
        artifacts = {('history', history.sha256): history, ('series', series.sha256): series,
            ('history', advanced.sha256): advanced, ('series', advanced_series.sha256): advanced_series,
            **{('mark', item.sha256): item for item in observations}}
        reader = lambda kind, digest: artifacts[(kind, digest)]
        runtime = ProspectiveRuntime(OWNER, RUN, self.journal, reader)
        await runtime.submit(runtime.prepare_bootstrap(self.config, history, series,
            inputs=new_inputs((END+5)*1_000_000, 54_905_000_000)), command_id=str(UUID(int=821)))

        # The feed checks immediately before the completion margin; collecting
        # the genuine next mark crosses it. Every required minute is present.
        precheck = SimpleNamespace(_history=history)
        self.assertEqual(await ProspectiveSourceFeed._history_update(precheck,
            (END+900)*1_000_000+source.COMPLETION_MARGIN_US-1), (None, None))
        # A later, real missing minute cannot be recreated by an ordinary retry.
        gap = SimpleNamespace(_history=advanced, _marks=list(marks[915:940])+list(marks[941:945]),
            _history_gap=False, _mark_clocks={})
        gap._mark_clock = lambda item: ProspectiveSourceFeed._mark_clock(gap, item)
        self.assertEqual(await ProspectiveSourceFeed._history_update(gap,
            (END+1800)*1_000_000+source.COMPLETION_MARGIN_US), (None, None))
        self.assertTrue(gap._history_gap)

        class ReadyArtifacts:
            async def restore(self): pass
        ready = ReadyArtifacts(); ready.reader = reader
        waiting, release = asyncio.Event(), asyncio.Event()
        calls, acknowledged, phases = [], [], []
        self.feed.ack_history = acknowledged.append
        self.feed.status = lambda: {'observed_minutes': 4, 'required_minutes': 915,
            'history_gap': len(calls) >= 3}
        async def next_observation():
            index = len(calls); calls.append(index)
            if index == 0:
                return SourceBatch(observations[0])
            if index == 1:
                return SourceBatch(observations[1], advanced, advanced_series)
            if index == 2:
                return SourceBatch(observations[2])
            waiting.set(); await release.wait()
            return SourceBatch(marks[945])
        self.feed.next_observation = next_observation
        async def paced(_):
            phases.append(service._phase)
        def clock(binding):
            index = max(0, min(len(calls)-1, len(observations)-1))
            return inputs_for_mark(observations[index], serial=200+index, generation=1).clock
        service = ProspectivePaperService(self.journal, self.feed, self.config,
            artifacts=ready, clock=clock, sleep=paced)
        try:
            await service.start(OWNER, str(UUID(int=822)))
            await asyncio.wait_for(waiting.wait(), 20)
            self.assertEqual(phases, ['waiting_data', 'running', 'waiting_data'])
            self.assertEqual([row.to_dict()['witness']['kind'] for row in self.journal.rows],
                ['bootstrap', 'protective', 'protective', 'decision', 'protective'])
            self.assertEqual(acknowledged, [advanced.sha256])
            status = await service.status(OWNER)
            self.assertEqual(status['phase'], 'waiting_data')
            self.assertTrue(status['warmup']['history_gap'])
            self.assertFalse(status['requires_reconciliation'])
            self.assertEqual(service.runtime.state.to_dict()['source']['history_sha256'], advanced.sha256)
            self.assertEqual(service.runtime.state.to_dict()['engine']['generation'], 0)
            self.assertTrue(all(not row['selection_eligible'] for record in service.runtime.history
                for row in record['assessments']))
            await service.stop(OWNER, str(UUID(int=823)))
            release.set(); await service._task
            self.assertEqual((await service.status(OWNER))['phase'], 'stopped')
        finally:
            release.set()
            await service.close()


if __name__ == '__main__':
    unittest.main()
