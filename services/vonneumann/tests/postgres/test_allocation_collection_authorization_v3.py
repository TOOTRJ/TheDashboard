"""Use authentic scoped PostgreSQL observations at a fake HTTP transport boundary."""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from tests.postgres.allocation_control_v3_fixture import BEGIN, SETTINGS
from tests.postgres.harness import OPT_IN
from tests.postgres.test_allocation_capture_join_v3 import as_wire, decode_wire, synthetic_capture
from tests.postgres.test_allocation_capture_retention_v3 import AllocationCaptureRetentionNativeCase
from tests.test_provider_recorded_transport_v3 import FakeTransport, KEY, RPC_URL, reply
from vonneumann.market import provider_acquisition_v3 as acquisition, provider_recorded_transport_v3 as transport
from vonneumann.market import source_admission_v3 as source
from vonneumann.research.native_collection_authorization import NativeRequestAuthorization, QUERY_FORMAT


@unittest.skipUnless(os.environ.get(OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class AllocationCollectionAuthorizationNativeTests(AllocationCaptureRetentionNativeCase):
    def test_stop_during_first_provider_request_blocks_the_next_request(self):
        original_reserve = as_wire(self.reserve)
        self.submit_bytes(original_reserve)
        self.read_original(self.reserve)
        head = self.assert_head(5, 'open')
        self.assert_reserved_ids()
        stop = self.stop_command()
        provider_calls = []
        witnesses = []

        async def query_recorder(query):
            result = self.db.sql(SETTINGS + self.sql_call('get_original', query), role=self.recorder)
            witnesses.append(decode_wire(query))
            self.assertEqual(result.stdout.count('\n'), 1)
            return result.stdout.rstrip('\n').encode()

        def first_response(request):
            provider_calls.append(request.method)
            self.assertEqual(provider_calls, ['GET'])
            self.db.sql(BEGIN + SETTINGS + self.sql_call('record_stop_intent', as_wire(stop)) + 'COMMIT;\n',
                        role=self.control)
            self.assert_head(5, 'open')
            return reply(request)

        first_query = dict(format=QUERY_FORMAT, scope=self.reserve['scope'], reservation_id=self.reserve['action_id'],
            reservation_command_sha256=source.sha(original_reserve), head_sha256=head['native_head_sha256'],
            record_id=self.prepared.price_record_id, provider_family='jupiter-price-v3',
            request_sha256=source.sha(acquisition.public_request('jupiter-price-v3')))
        self.assert_sql_refused(SETTINGS + self.sql_call('get_original', as_wire(first_query)),
                                self.reader, 'b2_actor_scope_refused')
        self.assert_sql_refused(SETTINGS + self.sql_call('get_original', as_wire(dict(first_query, head_sha256='0' * 64))),
                                self.recorder, 'b3_collection_head_refused')

        gate = NativeRequestAuthorization(self.prepared, reservation_wire=original_reserve,
            reservation_head_sha256=head['native_head_sha256'], query_recorder=query_recorder)
        fake = FakeTransport(first_response)

        async def collect():
            with patch.object(transport, '_transport', return_value=fake), patch.object(
                transport.importlib.metadata, 'version', side_effect={'httpcore': '1.0.9', 'certifi': transport.CERTIFI_VERSION}.__getitem__,
            ):
                item = transport.ProviderRecordedTransport(KEY, RPC_URL, read_only_opt_in=True, authorize_request=gate)
            try:
                return await item.collect(self.prepared)
            finally:
                await item.close()

        result = asyncio.run(collect())
        self.assertEqual(witnesses, [first_query])
        self.assertEqual(provider_calls, ['GET'])
        self.assertEqual(len(result.capsules), 1)
        self.assertFalse(result.completed)
        self.assertEqual(result.failure_code, 'request_unavailable')
        self.assertEqual(result.diagnostics, ())
        genesis = acquisition.public_request('solana-rpc', rpc_method='getGenesisHash', rpc_id=self.prepared.genesis_rpc_id)
        pending_query = dict(first_query, record_id=self.prepared.genesis_record_id, provider_family='solana-rpc',
                             request_sha256=source.sha(genesis))
        self.assert_sql_refused(SETTINGS + self.sql_call('get_original', as_wire(pending_query)),
                                self.recorder, 'b2_stop_intent_pending')

        capture_value = synthetic_capture(self.reservation, self.prepared).to_dict()
        capture_value.update(capsule_wires=[result.capsules[0].wire.decode()], diagnostics=[],
                             collection_completed=False, failure_code=result.failure_code)
        capture = source.validate_capture(self.reservation, source.envelope('Capture', capture_value))
        capture_command = self.capture_command(capture)
        self.stop_with_dispatch_gate(stop, 6, already_registered=True)
        self.submit_bytes(as_wire(capture_command))
        recovered = self.read_capture(self.packet_ids['capture_id'])
        self.assertEqual(decode_wire(recovered['original_command_wire'].encode())['body']['capture_wire'], capture.wire.decode())
        self.assert_head(7, 'stopped')
        self.assertEqual(provider_calls, ['GET'])
