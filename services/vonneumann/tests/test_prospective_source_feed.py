"""Real original-byte parsing, owned fake providers and durable restart checks."""
import asyncio
import hashlib
import json
import time
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import deny_network
with deny_network():
    from tests import test_provider_recorded_transport_v3 as provider_fixture
    from tests import test_prospective_source_v3 as source_fixture
    from vonneumann.core.prospective_artifacts import SourceRecipeStore
    from vonneumann.market import provider_acquisition_v3 as acquisition
    from vonneumann.market import provider_recorded_transport_v3 as transport
    from vonneumann.market import prospective_source_v3 as source
    from vonneumann.server.prospective_source_feed import (
        MARK_CACHE_WINDOW_US, ProspectiveSourceFeed, SourceFeedRefused, decode_packet,
    )


class SourceJournal:
    def __init__(self):
        self.sources, self.artifacts = {}, {}
        self.lost_source_reply = self.lost_artifact_reply = False
        self.admits = 0
        self.getter_delay_us = 0
        self.seal_clock = None
        self.source_sequence_stride, self.source_page_size = 1, 25

    async def admit_source(self, packet_id, wire):
        self.admits += 1
        if packet_id in self.sources:
            if self.sources[packet_id]['wire'] != wire:
                raise ValueError('original_conflict')
        else:
            accepted = time.time_ns() // 1000
            self.sources[packet_id] = {'packet_id': packet_id, 'wire': wire,
                'sequence': len(self.sources) * self.source_sequence_stride + 1,
                'sha256': hashlib.sha256(wire).hexdigest(),
                'accepted_at_us': accepted, 'receipt_sha256': hashlib.sha256(
                    wire + str(accepted).encode()).hexdigest()}
        if self.lost_source_reply:
            self.lost_source_reply = False
            raise ConnectionError('private database detail')
        return await self.get_source(packet_id)

    async def get_source(self, packet_id):
        row = self.sources.get(packet_id)
        if row is None:
            return None
        return {**row, 'available_at_upper_us': max(row['accepted_at_us'],
            time.time_ns() // 1000) + self.getter_delay_us}

    async def source_inventory(self, after_sequence=0, limit=25):
        return [row for row in self.sources.values() if row['sequence'] > after_sequence][:
            min(limit, self.source_page_size)]

    async def put_artifact(self, kind, digest, wire):
        key = kind, digest
        if key in self.artifacts and self.artifacts[key]['wire'] != wire:
            raise ValueError('original_conflict')
        self.artifacts.setdefault(key, {'kind': kind, 'sha256': digest,
            'wire': wire, 'sequence': len(self.artifacts) + 1})
        if self.lost_artifact_reply:
            self.lost_artifact_reply = False
            raise ConnectionError('private artifact detail')
        return self.artifacts[key]['wire']

    async def get_artifact(self, kind, digest):
        row = self.artifacts.get((kind, digest))
        return None if row is None else row['wire']

    async def artifact_inventory(self, after_sequence=0, limit=1):
        return [row for row in self.artifacts.values() if row['sequence'] > after_sequence][:1]

    async def seal_sources(self, seal_id, start_second, end_second, records_sha256, through_ingest_sequence):
        wire = acquisition.canonical({'kind': 'seal', 'start_second': start_second,
            'end_second': end_second, 'records_sha256': records_sha256,
            'through_ingest_sequence': through_ingest_sequence})
        await self.admit_source(seal_id, wire)
        self.sources[seal_id]['accepted_at_us'] = self.seal_clock
        return await self.get_source(seal_id)


class ProspectiveSourceFeedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.network = deny_network(); self.network.__enter__()
        self.addCleanup(self.network.__exit__, None, None, None)
        self.journal = SourceJournal()
        self.binding = provider_fixture.prepared().binding
        self.store = SourceRecipeStore(self.journal, self.binding.owner_id, self.binding.run_id)
        self.http, self.feeds = [], []

    async def asyncTearDown(self):
        for feed in self.feeds:
            await feed.close()

    def factory(self, handler=None):
        def create():
            fake = provider_fixture.FakeTransport(handler or provider_fixture.reply)
            self.http.append(fake)
            with patch.object(transport, '_transport', return_value=fake):
                return transport.ProviderRecordedTransport(provider_fixture.KEY,
                    provider_fixture.RPC_URL, read_only_opt_in=True)
        return create

    async def feed(self, *, factory=None):
        item = ProspectiveSourceFeed(self.binding, source_fixture.PACKAGE, self.journal,
            self.store, factory or self.factory())
        self.feeds.append(item)
        await item.restore()
        return item

    def stale_first_reply(self, request, *, transport_number=1):
        """Actual completed capsules; only the first packet's source is old."""
        if len(self.http) == transport_number and request.method == 'POST':
            body = json.loads(request.content)
            if body['method'] == 'getBlockTime':
                return provider_fixture.reply(request, body=acquisition.canonical({
                    'jsonrpc': '2.0', 'id': body['id'],
                    'result': time.time_ns() // 1_000_000_000 - 40}))
        return provider_fixture.reply(request)

    def assert_original_retained(self, packet_id, original):
        self.assertEqual(self.journal.sources[packet_id], original)
        self.assertEqual(hashlib.sha256(original['wire']).hexdigest(), original['sha256'])
        packet, prepared, clock, capsules = decode_packet(original['wire'])
        self.assertTrue(packet['completed'])
        self.assertEqual(len(capsules), 3)
        return prepared, clock, capsules

    async def test_stale_complete_source_is_retained_then_a_paced_new_sample_can_qualify(self):
        feed = await self.feed(factory=self.factory(self.stale_first_reply))
        unavailable = await feed.next_observation()
        packet_id, original = next(iter(self.journal.sources.items()))
        original = dict(original)
        prepared, clock, _ = self.assert_original_retained(packet_id, original)
        self.assertIsNone(unavailable.mark)
        self.assertEqual(unavailable.safe_error, 'provider_sample_unavailable')
        self.assertEqual(feed.status()['source_last_safe_error'], 'provider_source_expired')
        self.assertEqual(feed.status()['source_process_samples_unavailable'], 1)
        self.assertEqual(feed.status()['source_process_samples_accepted'], 0)
        self.assertIsNone(feed._pending); self.assertIsNone(feed._pending_native)
        self.assertFalse(feed._marks); self.assertFalse(self.journal.artifacts)
        self.assertEqual(self.http[0].closed, 1)
        with patch('vonneumann.server.prospective_source_feed.asyncio.sleep', new_callable=AsyncMock) as paced:
            accepted = await feed.next_observation()
        self.assertTrue(any(call.args[0] > 0 for call in paced.await_args_list))
        self.assertEqual([len(item.requests) for item in self.http], [3, 3])
        self.assertIs(type(accepted.mark), source.SourceMark)
        reference = accepted.mark.to_dict()['reference']
        self.assertNotEqual(reference['record_admission_id'], packet_id)
        fresh = decode_packet(self.journal.sources[reference['record_admission_id']]['wire'])[1]
        self.assertNotEqual(fresh.observation_id, prepared.observation_id)
        self.assertEqual(decode_packet(original['wire'])[2], clock)
        self.assert_original_retained(packet_id, original)
        self.assertEqual(feed.status()['source_process_sample_attempts'], 2)
        self.assertEqual(feed.status()['source_process_samples_accepted'], 1)

    async def test_delayed_first_native_read_is_not_restamped_into_a_fresh_mark(self):
        self.journal.getter_delay_us = 6_000_000
        reads = []
        real_get = self.journal.get_source
        async def observed_get(packet_id):
            row = await real_get(packet_id)
            reads.append(None if row is None else dict(row))
            return row
        self.journal.get_source = observed_get
        feed = await self.feed()
        unavailable = await feed.next_observation()
        packet_id, original = next(iter(self.journal.sources.items()))
        original = dict(original)
        _, clock, capsules = self.assert_original_retained(packet_id, original)
        self.assertEqual(unavailable.safe_error, 'provider_sample_unavailable')
        self.assertEqual(feed.status()['source_last_safe_error'], 'provider_receipt_expired')
        first_read = reads[-1]
        self.assertGreaterEqual(first_read['available_at_upper_us'] -
            min(int(item.to_dict()['received_wall_us']) for item in capsules), 6_000_000)
        self.assertFalse(self.journal.artifacts); self.assertFalse(feed._marks)
        self.assertIsNone(feed._pending); self.assertEqual(self.http[0].closed, 1)
        self.journal.getter_delay_us = 0
        with patch('vonneumann.server.prospective_source_feed.asyncio.sleep', new_callable=AsyncMock) as paced:
            fresh = await feed.next_observation()
        self.assertTrue(any(call.args[0] > 0 for call in paced.await_args_list))
        self.assertNotEqual(fresh.mark.to_dict()['reference']['record_admission_id'], packet_id)
        self.assertEqual([len(item.requests) for item in self.http], [3, 3])
        self.assertEqual(sum(item['packet_id'] == packet_id for item in reads), 2)
        self.assertEqual(decode_packet(original['wire'])[2], clock)
        self.assert_original_retained(packet_id, original)

    async def test_lost_source_ack_reconciles_same_stale_original_before_new_provider_io(self):
        feed = await self.feed(factory=self.factory(self.stale_first_reply))
        self.journal.lost_source_reply = True
        with self.assertRaises(SourceFeedRefused):
            await feed.next_observation()
        packet_id, wire = feed._pending
        original = dict(self.journal.sources[packet_id])
        self.assertIsNone(feed._pending_native)
        self.assertEqual(feed.status()['source_process_samples_unavailable'], 0)
        unavailable = await feed.next_observation()
        self.assertIsNone(unavailable.mark)
        self.assertEqual(feed.status()['source_last_safe_error'], 'provider_source_expired')
        self.assertEqual(self.journal.admits, 1)
        self.assertEqual([len(item.requests) for item in self.http], [3])
        self.assertEqual(original['wire'], wire)
        self.assert_original_retained(packet_id, original)
        with patch('vonneumann.server.prospective_source_feed.asyncio.sleep', new_callable=AsyncMock):
            accepted = await feed.next_observation()
        self.assertIs(type(accepted.mark), source.SourceMark)
        self.assertEqual(self.journal.admits, 2)
        self.assertEqual(feed.status()['source_process_reconciliations'], 1)
        self.assertEqual([len(item.requests) for item in self.http], [3, 3])

    async def test_unknown_native_readback_never_becomes_an_unavailable_sample(self):
        feed = await self.feed(factory=self.factory(self.stale_first_reply))
        real_get = self.journal.get_source
        reads = 0
        async def uncertain_get(packet_id):
            nonlocal reads
            reads += 1
            if reads >= 2:
                raise ConnectionError('private uncertain readback')
            return await real_get(packet_id)
        self.journal.get_source = uncertain_get
        for _ in range(2):
            with self.assertRaises(SourceFeedRefused):
                await feed.next_observation()
            self.assertIsNotNone(feed._pending)
            self.assertIsNone(feed._pending_native)
            self.assertEqual(feed.status()['source_process_samples_unavailable'], 0)
            self.assertEqual(self.journal.admits, 1)
            self.assertEqual([len(item.requests) for item in self.http], [3])
            self.assertFalse(self.journal.artifacts)

    async def test_changed_native_bytes_or_original_identity_cannot_be_disposed_as_stale(self):
        for defect in ('wire', 'packet_id'):
            with self.subTest(defect=defect):
                self.journal = SourceJournal()
                self.store = SourceRecipeStore(self.journal, self.binding.owner_id, self.binding.run_id)
                start_http = len(self.http)
                feed = await self.feed(factory=self.factory(lambda request:
                    self.stale_first_reply(request, transport_number=start_http + 1)))
                self.journal.lost_source_reply = True
                with self.assertRaises(SourceFeedRefused):
                    await feed.next_observation()
                packet_id, wire = feed._pending
                original_get = self.journal.get_source
                async def changed_get(identity):
                    row = await original_get(identity)
                    return {**row, defect: wire + b' ' if defect == 'wire' else provider_fixture.RUN}
                self.journal.get_source = changed_get
                with self.assertRaises(SourceFeedRefused):
                    await feed.next_observation()
                self.assertEqual(feed._pending, (packet_id, wire))
                self.assertIsNone(feed._pending_native)
                self.assertEqual(feed.status()['source_process_samples_unavailable'], 0)
                self.assertEqual(len(self.http), start_http + 1)
                self.assertFalse(self.journal.artifacts)

    async def test_foreign_original_clock_scope_fails_closed_before_stale_disposition(self):
        feed = await self.feed(factory=self.factory(self.stale_first_reply))
        def foreign_clock(binding):
            now, mono = time.time_ns() // 1000, time.monotonic_ns() // 1000
            return acquisition.ClockBound(provider_fixture.ISSUER, binding.run_id,
                binding.market_epoch, binding.acquisition_epoch, now, now, mono)
        with patch('vonneumann.server.prospective_source_feed._clock', side_effect=foreign_clock):
            with self.assertRaises(SourceFeedRefused):
                await feed.next_observation()
        self.assertIsNotNone(feed._pending)
        self.assertEqual(feed.status()['source_process_samples_unavailable'], 0)
        self.assertFalse(self.journal.artifacts)
        self.assertEqual([len(item.requests) for item in self.http], [3])

    async def test_typed_error_from_artifact_io_does_not_clear_the_original_latch(self):
        feed = await self.feed()
        original_put = self.journal.put_artifact
        async def uncertain_artifact(kind, digest, wire):
            await original_put(kind, digest, wire)
            raise acquisition.SampleUnavailable('provider_receipt_expired')
        self.journal.put_artifact = uncertain_artifact
        with self.assertRaises(SourceFeedRefused):
            await feed.next_observation()
        pending = feed._pending
        native_clock = feed._pending_native['available_at_upper_us']
        self.assertTrue(feed._recipe_attempted)
        self.assertEqual(len(self.journal.artifacts), 1)
        self.assertEqual(feed.status()['source_process_samples_unavailable'], 0)
        # Even a later typed pure error cannot abandon an earlier uncertain
        # recipe attempt. This is a fault injection, not rewritten parser data.
        with patch('vonneumann.server.prospective_source_feed.mark_recipe',
                side_effect=acquisition.SampleUnavailable('provider_receipt_expired')):
            with self.assertRaises(SourceFeedRefused):
                await feed.next_observation()
        self.assertEqual(feed._pending, pending)
        self.assertEqual(feed._pending_native['available_at_upper_us'], native_clock)
        self.assertEqual(feed.status()['source_process_samples_unavailable'], 0)
        self.assertEqual([len(item.requests) for item in self.http], [3])
        self.assertEqual(self.http[0].closed, 0)

    async def test_unavailable_cleanup_failure_retains_pending_until_cleanup_is_verified(self):
        actual_factory = self.factory(self.stale_first_reply)
        transports = []
        def create():
            item = actual_factory(); original_close = item.close
            async def failed_close():
                raise ConnectionError('private cleanup detail')
            item.close = failed_close
            transports.append((item, original_close))
            return item
        feed = await self.feed(factory=create)
        try:
            for _ in range(2):
                with self.assertRaises(SourceFeedRefused):
                    await feed.next_observation()
                self.assertIsNotNone(feed._pending)
                self.assertIsNotNone(feed._pending_native)
                self.assertEqual(feed.status()['source_process_samples_unavailable'], 0)
                self.assertEqual([len(item.requests) for item in self.http], [3])
                self.assertEqual(self.http[0].closed, 0)
            pending = feed._pending
        finally:
            for item, original_close in transports:
                item.close = original_close
        batch = await feed.next_observation()
        self.assertEqual(batch.safe_error, 'provider_sample_unavailable')
        self.assertIsNone(feed._pending)
        self.assertIn(pending[0], self.journal.sources)
        self.assertEqual(self.http[0].closed, 1)

    async def test_cancelled_unavailable_cleanup_cannot_release_the_pending_original(self):
        actual_factory = self.factory(self.stale_first_reply)
        entered, release = asyncio.Event(), asyncio.Event()
        transports = []
        def create():
            item = actual_factory(); original_close = item.close
            async def blocked_close():
                entered.set(); await release.wait(); await original_close()
            item.close = blocked_close
            transports.append((item, original_close))
            return item
        feed = await self.feed(factory=create)
        task = asyncio.create_task(feed.next_observation())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            pending = feed._pending
            original_native = dict(feed._pending_native)
            task.cancel()
            with self.assertRaises(SourceFeedRefused):
                await task
            self.assertEqual(feed._pending, pending)
            self.assertEqual(feed._pending_native, original_native)
            self.assertEqual(feed.status()['source_process_samples_unavailable'], 0)
            self.assertFalse(feed._busy)
            self.assertEqual([len(item.requests) for item in self.http], [3])
            self.assertEqual(self.http[0].closed, 0)
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            for item, original_close in transports:
                item.close = original_close

    async def test_success_cleanup_failure_reconciles_one_original_before_appending_its_mark(self):
        actual_factory = self.factory()
        transports = []
        def create():
            item = actual_factory(); original_close = item.close
            async def failed_close():
                raise ConnectionError('private success cleanup detail')
            item.close = failed_close
            transports.append((item, original_close))
            return item
        feed = await self.feed(factory=create)
        try:
            with self.assertRaises(SourceFeedRefused):
                await feed.next_observation()
            pending = feed._pending
            first_available = feed._pending_native['available_at_upper_us']
            original = dict(self.journal.sources[pending[0]])
            recipe = next(iter(self.journal.artifacts.values()))['wire']
            self.assertTrue(feed._recipe_attempted)
            self.assertFalse(feed._marks)
            self.assertEqual(feed.status()['source_process_samples_accepted'], 0)
            self.assertEqual(feed.status()['source_process_samples_unavailable'], 0)
        finally:
            for item, original_close in transports:
                item.close = original_close
        # A later getter may be slow; it cannot replace the first independently
        # verified read clock of this already attempted immutable recipe.
        self.journal.getter_delay_us = 100_000_000
        accepted = await feed.next_observation()
        self.assertEqual(accepted.mark.to_dict()['reference']['record_admission_id'], pending[0])
        self.assertEqual(int(accepted.mark.to_dict()['reference']['available_at_upper_us']), first_available)
        self.assertEqual(len(feed._marks), 1)
        self.assertEqual(len(self.journal.artifacts), 1)
        self.assertEqual(next(iter(self.journal.artifacts.values()))['wire'], recipe)
        self.assert_original_retained(pending[0], original)
        self.assertEqual(self.journal.admits, 1)
        self.assertEqual([len(item.requests) for item in self.http], [3])
        self.assertEqual(self.http[0].closed, 1)
        self.assertIsNone(feed._pending)
        self.assertFalse(feed._recipe_attempted)
        self.assertEqual(feed.status()['source_process_samples_accepted'], 1)
        self.assertEqual(feed.status()['source_process_reconciliations'], 1)

    async def test_registered_mark_status_and_trim_do_not_reparse_existing_wires(self):
        feed = await self.feed()
        mark = (await feed.next_observation()).mark
        before = feed.status()
        originals = {key: dict(value) for key, value in self.journal.artifacts.items()}
        sources = {key: dict(value) for key, value in self.journal.sources.items()}
        with patch.object(source.SourceMark, 'to_dict', side_effect=AssertionError('hot path reparsed wire')):
            status = feed.status()
            feed._trim_marks()
            again = feed.status()
        for key in ('observed_minutes', 'source_records', 'source_ready'):
            self.assertEqual(status[key], before[key]); self.assertEqual(again[key], before[key])
        self.assertEqual(feed._marks, [mark])
        self.assertEqual(self.journal.artifacts, originals)
        self.assertEqual(self.journal.sources, sources)

    async def test_clock_cache_rejects_a_cached_distinct_object_under_the_same_lookup_key(self):
        feed = await self.feed()
        original = (await feed.next_observation()).mark
        # The public recipe reader reconstructs a different immutable object
        # from the exact retained evidence, without a new provider read.
        replay = self.store.reader('mark', original.sha256)
        self.assertIsNot(replay, original); self.assertEqual(replay.wire, original.wire)
        reference = replay.to_dict()['reference']
        feed._mark_clocks[id(replay)] = (original, 1, 2)
        actual_to_dict, reads = source.SourceMark.to_dict, []
        def traced(mark):
            reads.append(mark)
            return actual_to_dict(mark)
        with patch.object(source.SourceMark, 'to_dict', new=traced):
            clocks = feed._mark_clock(replay)
        self.assertEqual(reads, [replay])
        self.assertEqual(clocks, (int(reference['accepted_at_us']), int(reference['available_at_upper_us'])))
        self.assertIs(feed._mark_clocks[id(replay)][0], replay)
        self.assertEqual([len(item.requests) for item in self.http], [3])

    async def test_trim_evicts_old_clock_references_without_changing_native_evidence(self):
        feed = await self.feed()
        await feed.next_observation()
        artifacts = {key: dict(value) for key, value in self.journal.artifacts.items()}
        sources = {key: dict(value) for key, value in self.journal.sources.items()}
        marks = [source_fixture.mark(index) for index in (0, 62, 63, 1009)]
        feed._marks = list(marks)
        feed.status()  # Registers these genuine pure-fixture bookkeeping inputs.
        with patch.object(source.SourceMark, 'to_dict', side_effect=AssertionError('trim reparsed cached wire')):
            feed._trim_marks()
        self.assertEqual(feed._marks, marks[2:])
        self.assertEqual(set(feed._mark_clocks), {id(mark) for mark in marks[2:]})
        for mark in marks[2:]:
            self.assertIs(feed._mark_clocks[id(mark)][0], mark)
        self.assertEqual(self.journal.artifacts, artifacts)
        self.assertEqual(self.journal.sources, sources)
        feed._marks = []
        feed._trim_marks()
        self.assertFalse(feed._mark_clocks)
        self.assertEqual(self.journal.artifacts, artifacts)

    async def test_restart_preserves_unavailable_original_and_only_restores_verified_marks(self):
        feed = await self.feed(factory=self.factory(self.stale_first_reply))
        await feed.next_observation()
        old_id, old_original = next(iter(self.journal.sources.items()))
        old_original = dict(old_original)
        with patch('vonneumann.server.prospective_source_feed.asyncio.sleep', new_callable=AsyncMock):
            fresh = await feed.next_observation()
        before = {key: dict(value) for key, value in self.journal.sources.items()}
        restored = await self.feed(factory=lambda: self.fail('restart cannot recollect'))
        self.assertEqual([mark.wire for mark in restored._marks], [fresh.mark.wire])
        self.assertEqual(self.journal.sources, before)
        self.assert_original_retained(old_id, old_original)
        self.assertEqual([len(item.requests) for item in self.http], [3, 3])

    async def test_stale_price_cannot_hide_a_later_genuine_clock_causality_failure(self):
        captured = []
        actual_factory = self.factory()
        def create():
            item = actual_factory(); original_collect = item.collect
            async def collect(prepared):
                result = await original_collect(prepared)
                captured.append(result)
                return result
            item.collect = collect
            return item
        def mixed_clock(binding):
            price = captured[-1].capsules[0].to_dict()
            wall = int(price['received_wall_us']) + 6_000_000
            return acquisition.ClockBound(binding.owner_id, binding.run_id,
                binding.market_epoch, binding.acquisition_epoch, wall, wall,
                int(price['received_monotonic_us']))
        feed = await self.feed(factory=create)
        with patch('vonneumann.server.prospective_source_feed._clock', side_effect=mixed_clock):
            with self.assertRaises(SourceFeedRefused):
                await feed.next_observation()
        packet_id, wire = feed._pending
        packet, prepared, clock, capsules = decode_packet(wire)
        self.assertTrue(packet['completed'])
        with self.assertRaises(acquisition.SampleUnavailable):
            acquisition.assess_record_age(capsules[0], prepared.binding, clock)
        with self.assertRaises(acquisition.AcquisitionError) as invalid:
            acquisition.assess_record_age(capsules[1], prepared.binding, clock)
        self.assertNotIsInstance(invalid.exception, acquisition.SampleUnavailable)
        self.assertEqual(self.journal.sources[packet_id]['wire'], wire)
        self.assertIsNotNone(feed._pending_native)
        self.assertEqual(feed.status()['source_process_samples_unavailable'], 0)
        self.assertFalse(self.journal.artifacts)
        self.assertEqual([len(item.requests) for item in self.http], [3])

    async def test_real_capsules_and_native_original_clocks_precede_mark_and_warmup(self):
        feed = await self.feed(factory=self.factory(lambda request:
            provider_fixture.reply(request, headers={'x-ratelimit-remaining': '42'})))
        batch = await feed.next_observation()
        self.assertIs(type(batch.mark), source.SourceMark)
        self.assertIsNone(batch.history); self.assertIsNone(batch.series)
        self.assertEqual([len(fake.requests) for fake in self.http], [3])
        self.assertEqual(self.http[0].closed, 1)
        row = next(iter(self.journal.sources.values()))
        packet, prepared, clock, capsules = decode_packet(row['wire'])
        self.assertTrue(packet['completed']); self.assertEqual(len(capsules), 3)
        reference = batch.mark.to_dict()['reference']
        self.assertEqual(int(reference['accepted_at_us']), row['accepted_at_us'])
        self.assertEqual(reference['record_admission_id'], row['packet_id'])
        self.assertEqual(reference['observation_id'], prepared.observation_id)
        self.assertEqual(batch.mark.to_dict()['original_observation_clock']['wall_lower_us'],
            str(clock.wall_lower_us))
        self.assertNotIn(provider_fixture.KEY.encode(), row['wire'])
        self.assertNotIn(provider_fixture.RPC_SECRET.encode(), row['wire'])
        self.assertEqual(feed.status()['required_minutes'], 915)
        self.assertFalse(feed.status()['source_ready'])
        status = feed.status()
        self.assertEqual(status['source_process_sample_attempts'], 1)
        self.assertEqual(status['source_process_samples_accepted'], 1)
        self.assertEqual(status['source_last_request_count'], 3)
        self.assertEqual(status['source_last_response_bytes'], [len(item.raw_body) for item in capsules])
        self.assertEqual(status['source_last_jupiter_remaining'], 42)
        for field in ('source_last_provider_duration_us', 'source_last_native_retention_duration_us',
            'source_last_recipe_duration_us', 'source_last_sample_duration_us', 'source_last_original_age_us'):
            self.assertIs(type(status[field]), int)
            self.assertGreaterEqual(status[field], 0)
        self.assertNotIn(provider_fixture.KEY, json.dumps(status))
        self.assertNotIn(provider_fixture.RPC_URL, json.dumps(status))

    async def test_lost_commit_reply_reconciles_same_original_before_any_new_provider_io(self):
        feed = await self.feed(); self.journal.lost_source_reply = True
        with self.assertRaises(SourceFeedRefused):
            await feed.next_observation()
        packet_id, original = feed._pending
        self.assertEqual(self.journal.sources[packet_id]['wire'], original)
        batch = await feed.next_observation()
        self.assertEqual(batch.mark.to_dict()['reference']['record_admission_id'], packet_id)
        self.assertEqual(self.journal.admits, 1)
        self.assertEqual([len(fake.requests) for fake in self.http], [3])
        self.assertEqual(feed.status()['source_process_reconciliations'], 1)
        self.assertEqual(feed.status()['source_process_failures'], 1)
        self.assertIsNone(feed.status()['source_last_safe_error'])

    async def test_uncertain_recipe_write_preserves_original_first_read_availability(self):
        feed = await self.feed(); self.journal.lost_artifact_reply = True
        with self.assertRaises(SourceFeedRefused):
            await feed.next_observation()
        original_available = feed._pending_native['available_at_upper_us']
        original_wire = next(iter(self.journal.artifacts.values()))['wire']
        self.journal.getter_delay_us = 1_000_000
        batch = await feed.next_observation()
        self.assertEqual(int(batch.mark.to_dict()['reference']['available_at_upper_us']), original_available)
        self.assertEqual(next(iter(self.journal.artifacts.values()))['wire'], original_wire)
        self.assertEqual([len(fake.requests) for fake in self.http], [3])

    async def test_restart_rederives_raw_originals_without_restamping_or_provider_io(self):
        feed = await self.feed(); original = (await feed.next_observation()).mark
        self.journal.getter_delay_us = 100_000_000
        restored = await self.feed(factory=lambda: self.fail('restart cannot recollect'))
        self.assertEqual([mark.wire for mark in restored._marks], [original.wire])
        self.assertEqual([len(fake.requests) for fake in self.http], [3])

    async def test_incomplete_original_is_archived_and_never_becomes_a_mark(self):
        feed = await self.feed(factory=self.factory(lambda request:
            provider_fixture.reply(request, status=503)))
        batch = await feed.next_observation()
        self.assertIsNone(batch.mark)
        self.assertEqual(batch.safe_error, 'provider_sample_unavailable')
        packet = decode_packet(next(iter(self.journal.sources.values()))['wire'])[0]
        self.assertFalse(packet['completed'])
        self.assertFalse(self.journal.artifacts)
        self.assertEqual(feed._marks, [])
        self.assertEqual([len(fake.requests) for fake in self.http], [1])
        self.assertIsNone(feed._pending)
        self.assertEqual(self.http[0].closed, 1)
        self.assertEqual(feed.status()['source_process_samples_unavailable'], 1)
        self.assertEqual(feed.status()['source_process_samples_accepted'], 0)
        self.assertEqual(feed.status()['source_last_safe_error'], 'provider_sample_unavailable')

    async def test_changed_native_original_is_refused_on_restart(self):
        feed = await self.feed(); await feed.next_observation()
        row = next(iter(self.journal.sources.values()))
        row['receipt_sha256'] = 'f' * 64
        with self.assertRaises(SourceFeedRefused):
            await self.feed()

    async def test_restart_reads_inventory_until_empty_and_preserves_sequence_gaps(self):
        feed = await self.feed()
        self.journal.source_sequence_stride, self.journal.source_page_size = 3, 1
        first = (await feed.next_observation()).mark
        feed._next_monotonic = None
        second = (await feed.next_observation()).mark
        restored = await self.feed(factory=lambda: self.fail('restart cannot recollect'))
        self.assertEqual([mark.sha256 for mark in restored._marks], [first.sha256, second.sha256])
        self.assertEqual([int(mark.to_dict()['reference']['ingest_sequence'])
            for mark in restored._marks], [1, 4])

    async def test_complete_warmup_requires_native_original_seal_and_missing_minute_refuses(self):
        feed = await self.feed()
        feed._marks = [source_fixture.mark(index) for index in range(915)]
        self.journal.seal_clock = source_fixture.END * 1_000_000 + source.COMPLETION_MARGIN_US
        now = self.journal.seal_clock
        removed = feed._marks.pop(100)
        self.assertEqual(await feed._history_update(now), (None, None))
        self.assertFalse(self.journal.sources)
        feed._marks.insert(100, removed)
        history, series = await feed._history_update(now)
        self.assertEqual(history.to_dict()['range']['observed_minutes'], '915')
        self.assertEqual(series.to_dict()['history_sha256'], history.sha256)
        seal = self.journal.sources[history.to_dict()['seal_id']]
        self.assertEqual(seal['accepted_at_us'], now)
        self.assertEqual(len(self.journal.artifacts), 2)
        self.assertFalse(feed.status()['history_gap'])
        next_end = source_fixture.END + source.BAR_SECONDS
        self.journal.seal_clock = next_end * 1_000_000 + source.COMPLETION_MARGIN_US
        self.assertEqual(await feed._history_update(self.journal.seal_clock), (None, None))
        self.assertTrue(feed.status()['history_gap'])
        feed._marks.extend(source_fixture.mark(index) for index in range(915, 930))
        advanced, advanced_series = await feed._history_update(self.journal.seal_clock)
        self.assertEqual(advanced.to_dict()['previous_history_sha256'], history.sha256)
        self.assertEqual(advanced.to_dict()['range']['observed_minutes'], '915')
        self.assertEqual(len(advanced.to_dict()['appended_bars']), 1)
        feed._publications = [(history, series), (advanced, advanced_series)]
        feed._history_digests = [history.sha256, advanced.sha256]
        feed.ack_history(history.sha256)
        self.assertEqual([item[0].sha256 for item in feed._publications], [advanced.sha256])
        feed.ack_history(advanced.sha256)
        self.assertEqual(feed._publications, [])
        with self.assertRaises(SourceFeedRefused):
            feed.ack_history('f' * 64)
        feed._marks.extend(source_fixture.mark(index) for index in range(930, 1010))
        originals = dict(self.journal.artifacts)
        feed._trim_marks()
        latest = int(feed._marks[-1].to_dict()['reference']['accepted_at_us'])
        oldest = int(feed._marks[0].to_dict()['reference']['accepted_at_us'])
        self.assertLessEqual(latest - oldest, MARK_CACHE_WINDOW_US)
        self.assertEqual(len(feed._marks), 947)
        self.assertEqual(self.journal.artifacts, originals)
        self.assertEqual(feed._history.sha256, advanced.sha256)
