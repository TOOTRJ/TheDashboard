"""Verify a fresh scoped database observation for each prepared provider request."""
from __future__ import annotations

from time import monotonic_ns

from ..market import provider_acquisition_v3 as codec
from ..market import source_admission_v3 as source
from ..market.provider_recorded_transport_v3 import PreparedPacket, RecordedTransportError

QUERY_FORMAT = 'ga-jupiter-b3-collection-authorization-query-v2'
OBSERVATION_FORMAT = 'ga-jupiter-b3-collection-authorization-observation-v2'


class NativeRequestAuthorization:
    """Use the authenticated recorder transport to check each request once.

    The scope head and Reservation command come from independent committed
    readback. The database callback executes a fresh statement each time.
    A refused check consumes the local attempt. An approved request may still
    be in flight when Stop commits, so its response follows Capture retention.
    """

    def __init__(self, prepared: PreparedPacket, *, reservation_wire: bytes,
                 reservation_head_sha256: str, query_recorder):
        try:
            codec.require(type(prepared) is PreparedPacket and callable(query_recorder))
            command = codec.read_json(reservation_wire, 16384, exact=True)
            codec.require(command['action_kind'] == 'packet_reservation'
                          and command['body']['prepared_packet_wire'] == prepared.wire.decode())
            scope = source.scope(command['scope'])
            self._query_fields = dict(format=QUERY_FORMAT, scope=scope,
                reservation_id=codec.uuid(command['action_id']), reservation_command_sha256=source.sha(reservation_wire),
                head_sha256=codec.digest(reservation_head_sha256))
            self._fence_id = codec.uuid(command['expected_fence_id'])
            self._fence_revision = command['expected_fence_revision']
            codec.counter(self._fence_revision, maximum=16, minimum=1)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise RecordedTransportError('request_unavailable') from None
        self._prepared = prepared
        self._query_recorder = query_recorder
        self._next = 0
        self._running = False
        self._closed = False

    async def __call__(self, prepared, family, identity, request):
        if self._running or self._closed or self._next == 3:
            raise RecordedTransportError('request_unavailable')
        self._running = True
        verified = False
        try:
            codec.require(prepared is self._prepared)
            expected = (
                ('jupiter-price-v3', prepared.price_record_id, None, None),
                ('solana-rpc', prepared.genesis_record_id, 'getGenesisHash', prepared.genesis_rpc_id),
                ('solana-rpc', prepared.block_time_record_id, 'getBlockTime', prepared.block_time_rpc_id),
            )[self._next]
            codec.require((family, identity) == expected[:2])
            public = codec.request_fields(request, family)
            if family == 'solana-rpc':
                rpc = codec.read_json(public['body_wire'].encode(), codec.MAX_REQUEST_BYTES, numeric=True)
                codec.require((rpc['method'], rpc['id']) == expected[2:])
            query = codec.canonical(dict(self._query_fields, record_id=identity,
                provider_family=family, request_sha256=source.sha(request)))
            before = monotonic_ns()
            raw = await self._query_recorder(query)
            observed = codec.read_json(raw, 2048, exact=True)
            codec.fields(observed, {'format', 'query_sha256', 'fence_id', 'fence_revision', 'observed_at_us', 'valid_until_us'})
            codec.require(observed['format'] == OBSERVATION_FORMAT and observed['query_sha256'] == source.sha(query)
                          and observed['fence_id'] == self._fence_id and observed['fence_revision'] == self._fence_revision)
            remaining_us = codec.counter(observed['valid_until_us']) - codec.counter(observed['observed_at_us'])
            elapsed = monotonic_ns() - before
            # Entire round trip bounds elapsed time since the server sampled its clock.
            codec.require(0 <= elapsed < remaining_us * 1000)
            self._next += 1
            verified = True
        except Exception:
            raise RecordedTransportError('request_unavailable') from None
        finally:
            self._closed = not verified
            self._running = False
