"""Durable original-byte provider collection for the single-owner paper worker.

Only Price and read-only RPC requests are used. Native commit clocks and fresh
original readback provide the RecordReference; local packet clocks are sampled
once and retained unchanged. Restart never restamps an old provider response.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
import hashlib
import time
from uuid import UUID, uuid4, uuid5

from ..core.prospective_artifacts import (
    SourceRecipe, SourceRecipeReader, history_recipe, mark_recipe, series_recipe,
)
from ..core.prospective_runtime import _decoded, _encoded
from ..market import provider_acquisition_v3 as acquisition
from ..market import provider_derivation_v3 as derivation
from ..market import prospective_source_v3 as source
from ..market.provider_recorded_transport_v3 import PreparedPacket
from ..research.prospective_ga_v3_policy import SourceBinding

FORMAT = 'dashboard-paper-original-source-packet-v1'
MAX_PACKET_BYTES = 1024 * 1024
MARK_CACHE_WINDOW_US = (source.WARMUP_MINUTES * 60 + 2 * source.BAR_SECONDS + 60) * 1_000_000


class SourceFeedRefused(RuntimeError):
    """Fixed diagnostics prevent provider/database exception text leaking."""


def _require(condition, code='source_original_mismatch'):
    if not condition:
        raise SourceFeedRefused(code)


def _binding_dict(binding):
    value = asdict(binding)
    value['endpoint_bindings'] = [list(pair) for pair in binding.endpoint_bindings]
    return value


def _decode_binding(value):
    value = dict(value)
    value['endpoint_bindings'] = tuple(tuple(pair) for pair in value['endpoint_bindings'])
    return acquisition.IssuerBinding(**value)


def _clock(binding):
    # These are actual local UTC/monotonic observations, never a synthetic
    # history timestamp. Native acceptance and readback are separate DB clocks.
    wall = time.time_ns() // 1000
    monotonic = time.monotonic_ns() // 1000
    return acquisition.ClockBound(binding.owner_id, binding.run_id,
        binding.market_epoch, binding.acquisition_epoch, wall, wall, monotonic)


def encode_packet(result, clock):
    prepared = result.prepared
    return acquisition.canonical({'format': FORMAT, 'binding': _binding_dict(prepared.binding),
        'prepared_wire': prepared.wire.decode('utf-8'), 'clock': _encoded(asdict(clock)),
        'capsules': [capsule.wire.decode('utf-8') for capsule in result.capsules],
        'completed': result.completed, 'failure_code': result.failure_code,
        'diagnostics': [dict(item) for item in result.diagnostics]})


def decode_packet(wire):
    value = acquisition.read_json(wire, MAX_PACKET_BYTES, exact=True)
    acquisition.fields(value, {'format', 'binding', 'prepared_wire', 'clock',
        'capsules', 'completed', 'failure_code', 'diagnostics'})
    _require(value['format'] == FORMAT and type(value['completed']) is bool)
    binding = _decode_binding(value['binding'])
    clock = acquisition.ClockBound(**_decoded(value['clock']))
    _require(all(getattr(binding, key) == getattr(clock, key)
        for key in ('owner_id', 'run_id', 'market_epoch', 'acquisition_epoch')))
    prepared = acquisition.read_json(value['prepared_wire'].encode('utf-8'), 16384, exact=True)
    original = PreparedPacket(binding, *(prepared[key] for key in (
        'price_record_id', 'genesis_record_id', 'block_time_record_id', 'observation_id')),
        int(prepared['genesis_rpc_id']), int(prepared['block_time_rpc_id']))
    _require(original.wire.decode('utf-8') == value['prepared_wire']
        and type(value['capsules']) is list and len(value['capsules']) <= 3)
    capsules = tuple(acquisition.decode_capsule(raw.encode('utf-8'), binding)
        for raw in value['capsules'])
    if value['completed']:
        _require(len(capsules) == 3 and value['failure_code'] is None)
        _require(tuple(item.to_dict()['record_id'] for item in capsules) == (
            original.price_record_id, original.genesis_record_id, original.block_time_record_id))
    return value, original, clock, capsules


class ProspectiveSourceFeed:
    def __init__(self, binding, recorder_package_sha256, journal, source_store,
                 transport_factory, *, interval_seconds=20):
        _require(type(binding) is acquisition.IssuerBinding, 'invalid_source_configuration')
        binding.__post_init__(); acquisition.digest(recorder_package_sha256)
        _require(callable(transport_factory) and type(interval_seconds) is int
            and 20 <= interval_seconds <= 60, 'invalid_source_configuration')
        self.binding, self.package_sha256 = binding, recorder_package_sha256
        self.journal, self.store, self.transport_factory = journal, source_store, transport_factory
        self.current_binding = SourceBinding(binding.owner_id, binding.run_id, binding.market_epoch,
            binding.acquisition_epoch, binding.issuer_binding_id, recorder_package_sha256)
        self.interval_seconds = interval_seconds
        self._marks, self._history, self._series = [], None, None
        self._mark_clocks = {}
        self._publications, self._history_digests = [], []
        self._pending, self._pending_native, self._transport = None, None, None
        self._admit_attempted = False
        self._recipe_attempted = False
        self._next_monotonic = None
        self._history_gap = False
        self._closed, self._restored, self._busy = False, False, False
        self._sample_started_ns = None
        self._last_success_monotonic_us = None
        # Process counters reset on restart. Only counts, byte lengths and fixed
        # safe diagnostics enter status; no raw bodies, URLs, keys or exceptions.
        self._metrics = {'source_process_sample_attempts': 0,
            'source_process_samples_accepted': 0, 'source_process_samples_unavailable': 0,
            'source_process_failures': 0, 'source_process_reconciliations': 0,
            'source_last_provider_duration_us': None, 'source_last_native_retention_duration_us': None,
            'source_last_recipe_duration_us': None, 'source_last_sample_duration_us': None,
            'source_last_original_age_us': None, 'source_last_response_bytes': [],
            'source_last_request_count': 0, 'source_last_jupiter_remaining': None,
            'source_last_safe_error': None, 'source_last_success_at_us': None}

    def status(self):
        complete = set()
        for mark in self._marks:
            accepted, available = self._mark_clock(mark)
            minute = accepted // 60_000_000 * 60
            if minute * 1_000_000 < available <= (minute + 60) * 1_000_000:
                complete.add(minute)
        latest = max(complete, default=None)
        consecutive = 0
        while latest is not None and latest in complete and consecutive < source.WARMUP_MINUTES:
            consecutive += 1; latest -= 60
        return {'observed_minutes': consecutive, 'required_minutes': source.WARMUP_MINUTES,
            'source_records': len(self._marks), 'source_ready': self._history is not None,
            'source_original_pending': self._pending is not None,
            'history_gap': self._history_gap, **self._metrics,
            'source_microseconds_since_success': None if self._last_success_monotonic_us is None else
                max(0, time.monotonic_ns() // 1000 - self._last_success_monotonic_us)}

    async def _measure(self, field, operation):
        started = time.monotonic_ns()
        try:
            return await operation
        finally:
            self._metrics[field] = max(0, (time.monotonic_ns() - started) // 1000)

    def _sample_duration(self):
        if self._sample_started_ns is not None:
            self._metrics['source_last_sample_duration_us'] = max(0,
                (time.monotonic_ns() - self._sample_started_ns) // 1000)

    def _response_metrics(self, result):
        self._metrics['source_last_response_bytes'] = [len(item.raw_body) for item in result.capsules]
        identities = {item.to_dict()['record_id'] for item in result.capsules}
        identities.update(dict(item)['record_id'] for item in result.diagnostics
            if type(dict(item).get('record_id')) is str)
        self._metrics['source_last_request_count'] = min(3, len(identities))
        self._metrics['source_last_jupiter_remaining'] = None
        for item in result.capsules:
            row = item.to_dict()
            if row['provider_family'] == 'jupiter-price-v3':
                remaining = row['safe_response_metadata'].get('x_ratelimit_remaining')
                if type(remaining) is str and remaining.isascii() and remaining.isdecimal() and len(remaining) <= 12:
                    self._metrics['source_last_jupiter_remaining'] = int(remaining)

    def set_consumed_history_sha256(self, digest):
        """Advance publication only after the service's durable model readback."""
        if digest is None:
            return
        acquisition.digest(digest)
        _require(digest in self._history_digests, 'source_history_original_missing')
        position = self._history_digests.index(digest)
        consumed = set(self._history_digests[:position + 1])
        self._publications = [(history, series) for history, series in self._publications
            if history.sha256 not in consumed]

    ack_history = set_consumed_history_sha256

    def _mark_clock(self, mark):
        # These immutable objects were constructed/replayed through the public
        # parser. Cache only bookkeeping clocks, bound to the identical object.
        # Revalidating thousands of full wires during status/trim ages the fresh
        # observation before model admission on the small production CPU.
        cached = self._mark_clocks.get(id(mark))
        if cached is None or cached[0] is not mark:
            reference = mark.to_dict()['reference']
            cached = (mark, int(reference['accepted_at_us']), int(reference['available_at_upper_us']))
            self._mark_clocks[id(mark)] = cached
        return cached[1:]

    def _trim_marks(self):
        if not self._marks:
            self._mark_clocks.clear()
            return
        latest = max(self._mark_clock(mark)[0] for mark in self._marks)
        cutoff = latest - MARK_CACHE_WINDOW_US
        self._marks = [mark for mark in self._marks
            if self._mark_clock(mark)[0] >= cutoff]
        self._mark_clocks = {id(mark): self._mark_clocks[id(mark)] for mark in self._marks}

    async def _persist(self, recipe):
        returned = await self.store.put(recipe.kind, recipe.sha256, recipe.wire)
        _require(returned is None or returned == recipe.wire, 'source_recipe_write_mismatch')
        _require(await self.store.get(recipe.kind, recipe.sha256) == recipe.wire,
            'source_recipe_readback_mismatch')

    def _check_receipt(self, receipt, packet_id, wire, *, require_read_clock=True):
        _require(type(receipt) is dict and receipt.get('packet_id') == packet_id
            and receipt.get('wire') == wire
            and receipt.get('sha256') == hashlib.sha256(wire).hexdigest())
        for field in ('sequence', 'accepted_at_us'):
            _require(type(receipt.get(field)) is int and receipt[field] > 0)
        acquisition.digest(receipt.get('receipt_sha256'))
        if require_read_clock:
            _require(type(receipt.get('available_at_upper_us')) is int
                and receipt['accepted_at_us'] <= receipt['available_at_upper_us'])
        return receipt

    async def _check_seal(self, reference):
        original = await self.journal.get_source(reference.seal_id)
        expected = acquisition.canonical({'kind': 'seal',
            'start_second': reference.start_second, 'end_second': reference.end_second,
            'records_sha256': reference.records_sha256,
            'through_ingest_sequence': reference.through_ingest_sequence})
        self._check_receipt(original, reference.seal_id, expected)
        _require(original['accepted_at_us'] == reference.sealed_at_us)

    async def restore(self):
        _require(not self._busy and self._pending is None, 'source_busy')
        cached = {}
        for kind in ('mark', 'history', 'series'):
            for digest, wire in await self.store.scan(kind):
                recipe = SourceRecipe(wire)
                _require((recipe.kind, recipe.sha256) == (kind, digest))
                cached[(kind, digest)] = wire
        reader = SourceRecipeReader(self.binding.owner_id, self.binding.run_id,
            lambda kind, digest: cached[(kind, digest)])
        originals, after_sequence = {}, 0
        while True:
            rows = await self.journal.source_inventory(after_sequence=after_sequence, limit=25)
            if not rows:
                break
            for row in rows:
                _require(type(row.get('sequence')) is int and row['sequence'] > after_sequence)
                self._check_receipt(row, row.get('packet_id'), row.get('wire'), require_read_clock=False)
                _require(row['packet_id'] not in originals)
                originals[row['packet_id']] = row
                after_sequence = row['sequence']
        marks = []
        for (kind, digest), wire in cached.items():
            if kind != 'mark':
                continue
            mark = reader(kind, digest); reference = mark.to_dict()['reference']
            _require(mark.to_dict()['scope']['market_epoch'] == self.binding.market_epoch
                and reference['recorder_package_sha256'] == self.package_sha256)
            native = originals.get(reference['record_admission_id'])
            _require(type(native) is dict and type(native.get('wire')) is bytes)
            self._check_receipt(native, reference['record_admission_id'], native['wire'], require_read_clock=False)
            packet, prepared, clock, capsules = decode_packet(native['wire'])
            _require(packet['completed'] and prepared.observation_id == reference['observation_id']
                and native['sequence'] == int(reference['ingest_sequence'])
                and native['accepted_at_us'] == int(reference['accepted_at_us'])
                and native['receipt_sha256'] == reference['native_record_receipt_sha256'])
            original, replay = mark_recipe(*capsules, prepared.binding, clock,
                source.RecordReference(**{key: int(value) if key in {
                    'ingest_sequence', 'accepted_at_us', 'available_at_upper_us'} else value
                    for key, value in reference.items()}))
            _require(original.sha256 == digest and replay.wire == wire)
            marks.append(mark)
        marks.sort(key=lambda mark: int(mark.to_dict()['reference']['ingest_sequence']))
        _require(len({mark.to_dict()['reference']['ingest_sequence'] for mark in marks}) == len(marks))
        histories = sorted((reader(kind, digest) for kind, digest in cached if kind == 'history'),
            key=lambda item: int(item.to_dict()['range']['end']))
        for previous, current in zip(histories, histories[1:]):
            _require(current.to_dict()['previous_history_sha256'] == previous.sha256,
                'source_history_branch_or_gap')
        for (kind, _), wire in cached.items():
            if kind == 'history':
                reference = source.SealReference(**_decoded(SourceRecipe(wire).to_dict()['inputs']['reference']))
                await self._check_seal(reference)
        self._publications, self._history_digests = [], []
        for history in histories:
            series, recipe = series_recipe(history)
            _require(cached.get(('series', series.sha256)) == recipe.wire)
            self._publications.append((history, series))
            self._history_digests.append(history.sha256)
        history = histories[-1] if histories else None
        if history is not None:
            _require(history.to_dict()['scope']['market_epoch'] == self.binding.market_epoch)
            series, recipe = series_recipe(history)
            _require(cached.get(('series', series.sha256)) == recipe.wire)
            self._history, self._series = history, series
        self._marks = marks
        # Every retained history was validated above against the full immutable
        # inventory. This drops only redundant process cache entries; original
        # packets and replay recipes remain in the scoped native journal.
        self._trim_marks()
        self._restored = True

    async def _retain_pending(self):
        packet_id, wire = self._pending
        if not self._admit_attempted:
            # This preallocated identity has never been dispatched by this feed.
            # Consume the latch before awaiting; uncertain returns reconcile by
            # getter on the next attempt rather than resubmitting blindly.
            self._admit_attempted = True
            acknowledged = await self.journal.admit_source(packet_id, wire)
            original = await self.journal.get_source(packet_id)
            self._check_receipt(acknowledged, packet_id, wire)
        else:
            self._metrics['source_process_reconciliations'] += 1
            original = await self.journal.get_source(packet_id)
            if original is None:
                # The owned transport serializes this getter after the admitted
                # transaction has ended. Only the same immutable ID/wire can be
                # retried after that independently observed absence.
                acknowledged = await self.journal.admit_source(packet_id, wire)
                original = await self.journal.get_source(packet_id)
                self._check_receipt(acknowledged, packet_id, wire)
        self._check_receipt(original, packet_id, wire)
        if self._pending_native is None:
            self._pending_native = original
        else:
            _require(all(original[key] == self._pending_native[key] for key in (
                'packet_id', 'sequence', 'sha256', 'wire', 'accepted_at_us', 'receipt_sha256')))
        # A retry of recipe persistence keeps the first independent read clock.
        return self._pending_native

    async def _complete_unavailable(self, reason):
        from .prospective_service import SourceBatch
        _require(self._pending is not None and self._pending_native is not None
            and not self._recipe_attempted, 'source_original_or_artifact_unresolved')
        # Cleanup belongs to this original. A failed/cancelled close must retain
        # its latch; collecting a replacement while cleanup is unknown is unsafe.
        if self._transport is not None:
            await self._transport.close()
            self._transport = None
        self._pending, self._pending_native = None, None
        self._admit_attempted = False
        self._metrics['source_process_samples_unavailable'] += 1
        self._metrics['source_last_safe_error'] = reason
        self._sample_duration()
        return SourceBatch(None, safe_error='provider_sample_unavailable')

    async def _history_update(self, now_us):
        if self._history is None:
            end = ((now_us - source.COMPLETION_MARGIN_US) // 1_000_000 // source.BAR_SECONDS) * source.BAR_SECONDS
            start = end - source.WARMUP_MINUTES * 60
        else:
            previous_end = int(self._history.to_dict()['range']['end'])
            start, end = previous_end - source.BAR_SECONDS, previous_end + source.BAR_SECONDS
            if now_us < end * 1_000_000 + source.COMPLETION_MARGIN_US:
                return None, None
        marks = tuple(mark for mark in self._marks
            if start * 1_000_000 <= self._mark_clock(mark)[0] < end * 1_000_000)
        if not marks or len(marks) > source.MAX_RECORDS:
            return None, None
        minutes = {self._mark_clock(mark)[0] // 60_000_000 * 60
            for mark in marks if self._mark_clock(mark)[1] <=
                (self._mark_clock(mark)[0] // 60_000_000 + 1) * 60_000_000}
        if any(minute not in minutes for minute in range(start, end, 60)):
            self._history_gap = self._history is not None
            return None, None
        digest = source.record_set_digest(marks)
        # The immutable native original supplies the seal clock. Deterministic
        # identity reconciles an uncertain seal without making a replacement.
        seal_id = str(uuid5(UUID(self.binding.run_id), f'{start}:{end}:{digest}'))
        through = max(int(mark.to_dict()['reference']['ingest_sequence']) for mark in marks)
        await self.journal.seal_sources(seal_id, start, end, digest, through)
        native = await self.journal.get_source(seal_id)
        _require(type(native) is dict and native.get('packet_id') == seal_id
            and type(native.get('sealed_at_us', native.get('accepted_at_us'))) is int)
        sealed = native.get('sealed_at_us', native['accepted_at_us'])
        reference = source.SealReference(self.binding.owner_id, self.binding.run_id,
            self.binding.market_epoch, seal_id, digest, through, start, end, sealed, self.package_sha256)
        await self._check_seal(reference)
        history, history_original = history_recipe(marks, reference, previous=self._history)
        series, series_original = series_recipe(history)
        await self._persist(history_original); await self._persist(series_original)
        self._history, self._series = history, series
        self._history_gap = False
        # Retain only the rolling model window plus the current unsealed period.
        # Every original remains in the native source journal and recipe store.
        keep_from = (end - source.WARMUP_MINUTES * 60) * 1_000_000
        self._marks = [mark for mark in self._marks
            if self._mark_clock(mark)[0] >= keep_from]
        self._mark_clocks = {id(mark): self._mark_clocks[id(mark)] for mark in self._marks}
        return history, series

    async def next_observation(self):
        from .prospective_service import SourceBatch
        _require(not self._closed and self._restored and not self._busy, 'source_feed_not_ready')
        self._busy = True
        try:
            if self._pending is None:
                # History reconstruction may parse thousands of originals and
                # write several native artifacts. Finish it before collecting
                # the fresh mark that the model must consume within five seconds.
                if not self._publications and self._marks:
                    history, series = await self._history_update(time.time_ns() // 1000)
                    if history is not None:
                        self._publications.append((history, series))
                        self._history_digests.append(history.sha256)
                if self._next_monotonic is not None:
                    await asyncio.sleep(max(0, self._next_monotonic - time.monotonic()))
                _require(not self._closed, 'source_feed_closed')
                self._next_monotonic = time.monotonic() + self.interval_seconds
                prepared = PreparedPacket(self.binding, *(str(uuid4()) for _ in range(4)), 1, 2)
                self._sample_started_ns = time.monotonic_ns()
                self._metrics['source_process_sample_attempts'] += 1
                self._transport = self.transport_factory()
                result = await self._measure('source_last_provider_duration_us', self._transport.collect(prepared))
                self._response_metrics(result)
                clock = _clock(self.binding)
                packet_wire = encode_packet(result, clock)
                _require(len(packet_wire) <= MAX_PACKET_BYTES, 'source_packet_too_large')
                self._pending = (str(uuid4()), packet_wire)
                self._admit_attempted = False
                self._recipe_attempted = False
            native = await self._measure('source_last_native_retention_duration_us', self._retain_pending())
            packet_id, wire = self._pending
            packet, prepared, clock, capsules = decode_packet(wire)
            if not packet['completed']:
                # A known failed read is safe to try again on a later tick only
                # after this exact attempt's retained original is independently
                # observed. Uncertain database outcomes keep the pending ID.
                return await self._complete_unavailable('provider_sample_unavailable')
            try:
                # Only pure parsing/mark construction may classify a retained
                # sample as permanently unavailable. No artifact call is inside
                # this catch, and an earlier uncertain write keeps its latch.
                observed = derivation.derive_observation(*capsules, prepared.binding, clock,
                    observation_id=prepared.observation_id)
                reference = source.RecordReference(self.binding.owner_id, self.binding.run_id,
                    self.binding.market_epoch, prepared.binding.acquisition_epoch, prepared.observation_id,
                    observed.sha256, packet_id, native['sequence'], native['accepted_at_us'],
                    native['available_at_upper_us'], prepared.binding.issuer_binding_id,
                    self.package_sha256, native['receipt_sha256'])
                mark, recipe = mark_recipe(*capsules, prepared.binding, clock, reference)
            except acquisition.SampleUnavailable as error:
                return await self._complete_unavailable(error.reason)
            self._recipe_attempted = True
            await self._measure('source_last_recipe_duration_us', self._persist(recipe))
            if self._transport is not None:
                await self._transport.close()
                self._transport = None
            self._marks.append(mark)
            self._trim_marks()
            self._pending, self._pending_native = None, None
            self._admit_attempted = False
            self._recipe_attempted = False
            self._metrics['source_process_samples_accepted'] += 1
            self._metrics['source_last_safe_error'] = None
            self._metrics['source_last_success_at_us'] = native['accepted_at_us']
            self._last_success_monotonic_us = time.monotonic_ns() // 1000
            self._metrics['source_last_original_age_us'] = max(0, self._last_success_monotonic_us -
                min(int(item.to_dict()['received_monotonic_us']) for item in capsules))
            self._sample_duration()
            history, series = self._publications[0] if self._publications else (None, None)
            return SourceBatch(mark, history, series)
        except (Exception, asyncio.CancelledError):
            # The owning service stops on this fixed diagnostic. Pending bytes
            # stay available for exact same-ID reconciliation in this process.
            self._metrics['source_process_failures'] += 1
            self._metrics['source_last_safe_error'] = 'source_collection_failed_or_pending'
            self._sample_duration()
            raise SourceFeedRefused('source_collection_failed_or_pending') from None
        finally:
            self._busy = False

    async def close(self):
        self._closed = True
        if self._transport is not None:
            await self._transport.close(); self._transport = None
