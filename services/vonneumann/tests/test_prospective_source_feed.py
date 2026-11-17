"""Real original-byte parsing, owned fake providers and durable restart checks."""
import hashlib
import json
import time
import unittest
from unittest.mock import patch

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
