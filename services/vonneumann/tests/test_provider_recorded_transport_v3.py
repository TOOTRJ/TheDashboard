"""Owned fake/loopback transport fixtures, never public provider contacts."""
from __future__ import annotations

import asyncio
import ast
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import ssl
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import deny_network
with deny_network():
    import httpx
    from vonneumann.market import provider_acquisition_v3 as a,provider_derivation_v3 as d
    from vonneumann.market import provider_recorded_transport_v3 as t

KEY='jup_FAKE_fixture_only_key_12345'
RPC_SECRET='FAKE_rpc_query_key_987654321'
RPC_URL='https://rpc.fixture.invalid/?api-key='+RPC_SECRET
OWNER,RUN,MARKET,PROCESS,ISSUER=[str(UUID(int=value)) for value in (11,12,13,14,15)]


def prepared(index=0):
    binding=a.IssuerBinding(OWNER,RUN,MARKET,PROCESS,ISSUER,
        (('jupiter-price-v3',str(UUID(int=21))),('solana-rpc',str(UUID(int=22)))))
    identities=[str(UUID(int=1000+index*10+offset)) for offset in (1,2,3,4)]
    return t.PreparedPacket(binding,*identities,1,2)


def response_body(request):
    if request.method=='GET':
        return (' {"'+a.MINT+'":{"usdPrice":100.123456789012345678,"blockId":348004023,"decimals":9,"priceChange24h":null}}\n').encode()
    body=json.loads(request.content)
    result=a.GENESIS if body['method']=='getGenesisHash' else time.time_ns()//1_000_000_000-2
    return a.canonical({'jsonrpc':'2.0','id':body['id'],'result':result})


class Stream(httpx.AsyncByteStream):
    def __init__(self,chunks,*,delay=0,close_entered=None,close_release=None,close_error=None):
        self.chunks=chunks;self.delay=delay;self.closed=0
        self.close_entered=close_entered;self.close_release=close_release;self.close_error=close_error
    async def __aiter__(self):
        for chunk in self.chunks:
            if self.delay:await asyncio.sleep(self.delay)
            yield chunk
    async def aclose(self):
        self.closed+=1
        if self.close_entered:self.close_entered.set()
        if self.close_release:await self.close_release.wait()
        if self.close_error:raise self.close_error


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self,handler):self.handler=handler;self.requests=[];self.closed=0
    async def handle_async_request(self,request):
        self.requests.append(request)
        result=self.handler(request)
        return await result if hasattr(result,'__await__') else result
    async def aclose(self):self.closed+=1


def reply(request,*,status=200,body=None,headers=None,stream=None):
    return httpx.Response(status,headers={'content-type':'application/json',**(headers or {})},
        stream=Stream([response_body(request) if body is None else body]) if stream is None else stream)


class CaptureHandler(logging.Handler):
    def __init__(self):super().__init__();self.messages=[]
    def emit(self,record):self.messages.append(record.getMessage())


class SpyFilter(logging.Filter):
    def __init__(self):super().__init__();self.messages=[]
    def filter(self,record):self.messages.append(record.getMessage());return True


class EqualityFilter(logging.Filter):
    def __eq__(self,other):return True


class ProviderRecordedTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.network=deny_network();self.network.__enter__();self.addCleanup(self.network.__exit__,None,None,None)
        self.items=[]
    async def asyncTearDown(self):
        for item in self.items:
            await item.close()

    def fixture(self,handler=None,*,bounds=None):
        fake=FakeTransport((lambda request:reply(request)) if handler is None else handler)
        with patch.object(t,'_transport',return_value=fake):
            item=t.ProviderRecordedTransport(KEY,RPC_URL,read_only_opt_in=True,bounds=bounds)
        self.items.append(item);return item,fake

    async def test_exact_original_trio_scope_bytes_ids_integer_clocks_and_no_authority(self):
        item,fake=self.fixture();plan=prepared()
        result=await item.collect(plan)
        self.assertTrue(result.completed);self.assertEqual(len(result.capsules),3)
        self.assertEqual(len(fake.requests),3)
        self.assertEqual(str(fake.requests[0].url),t.PRICE_URL+'?ids='+a.MINT)
        self.assertEqual(fake.requests[0].headers['x-api-key'],KEY)
        self.assertEqual(fake.requests[0].headers['Accept-Encoding'],'identity')
        for request in fake.requests[1:]:
            self.assertEqual(str(request.url),RPC_URL);self.assertNotIn('x-api-key',request.headers)
            self.assertEqual(set(request.extensions),{'timeout'})
        expected_ids=(plan.price_record_id,plan.genesis_record_id,plan.block_time_record_id)
        for original,expected in zip(result.capsules,expected_ids):
            row=original.to_dict();self.assertEqual(row['record_id'],expected)
            self.assertEqual(row['response_sha256'],hashlib.sha256(original.raw_body).hexdigest())
            self.assertEqual(row['owner_id'],OWNER);self.assertEqual(row['acquisition_epoch'],PROCESS)
            for key in ('request_started_wall_us','received_wall_us','request_started_monotonic_us','received_monotonic_us'):
                self.assertIs(type(row[key]),str);self.assertGreater(int(row[key]),0)
            self.assertNotIn(KEY,row['canonical_public_request_wire']);self.assertNotIn(RPC_SECRET,row['canonical_public_request_wire'])
        self.assertFalse(result.native_admission);self.assertFalse(result.provider_authenticated)
        self.assertFalse(result.running_authority)
        self.assertNotIn(KEY,repr(item));self.assertNotIn(RPC_URL,repr(result))
        self.assertNotIn(KEY,json.dumps(result.summary()))
        # Independently supplied pure clock still creates no authenticated/native authority.
        now=time.time_ns()//1000;mono=time.monotonic_ns()//1000
        clock=a.ClockBound(OWNER,RUN,MARKET,PROCESS,now,now,mono)
        observation=d.derive_observation(*result.capsules,plan.binding,clock,observation_id=plan.observation_id)
        self.assertEqual(observation.to_dict()['price_decimal'],'100.123456789012345678')
        self.assertFalse(observation.native_admission)

    async def test_actual_tls_configuration_ignores_env_ca_proxy_and_keylog_without_writes(self):
        with tempfile.TemporaryDirectory(prefix='dashboard-v3-keylog-') as folder:
            keylog=Path(folder)/'must-not-be-created'
            with patch.dict(os.environ,{'SSLKEYLOGFILE':str(keylog),'SSL_CERT_FILE':'/missing/fake-ca',
                    'SSL_CERT_DIR':'/missing/fake-ca-dir','HTTPS_PROXY':'https://unrelated.invalid'}):
                item,fake=self.fixture();result=await item.collect(prepared())
            self.assertTrue(result.completed);self.assertFalse(keylog.exists())
        self.assertTrue(item._context.check_hostname)
        self.assertEqual(item._context.verify_mode,ssl.CERT_REQUIRED)
        self.assertGreaterEqual(item._context.minimum_version,ssl.TLSVersion.TLSv1_2)
        self.assertIsNone(item._context.keylog_filename)

    async def test_lowlevel_transport_configuration_pins_no_retry_proxy_or_client(self):
        options=[]
        def factory(**kwargs):options.append(kwargs);return FakeTransport(lambda request:reply(request))
        with patch.object(httpx,'AsyncHTTPTransport',side_effect=factory):
            item=t.ProviderRecordedTransport(KEY,RPC_URL,read_only_opt_in=True)
        self.items.append(item)
        self.assertIs(options[0]['verify'],item._context)
        self.assertFalse(options[0]['trust_env']);self.assertEqual(options[0]['retries'],0)
        self.assertIsNone(options[0]['proxy']);self.assertFalse(options[0]['http2'])
        self.assertEqual(options[0]['limits'].max_connections,1)
        self.assertFalse(hasattr(item,'_client'))

    async def test_closed_invalid_configuration_and_prepared_ids_refuse_before_io(self):
        with patch.object(t,'_transport',side_effect=AssertionError('No transport construction')):
            for options in ({},{'read_only_opt_in':False},{'read_only_opt_in':1}):
                with self.assertRaises(t.RecordedTransportError):t.ProviderRecordedTransport(KEY,RPC_URL,**options)
            for key,url in (('',RPC_URL),(KEY+'\r\n',RPC_URL),(KEY,'http://rpc.fixture.invalid'),
                    (KEY,'https://user:pass@rpc.fixture.invalid'),(KEY,RPC_URL+'#secret')):
                with self.assertRaises(t.RecordedTransportError):t.ProviderRecordedTransport(key,url,read_only_opt_in=True)
        for options in ({'operation_us':True},{'read_us':5_000_001},{'cleanup_us':0},{'packet_limit':True},
                        {'result_bytes_limit':1}):
            with self.assertRaises(t.RecordedTransportError):t.TransportBounds(**options)
        with self.assertRaises(a.AcquisitionError):replace(prepared(),price_record_id=prepared().genesis_record_id)
        item,fake=self.fixture()
        with self.assertRaises(t.RecordedTransportError):await item.collect(prepared().wire)
        self.assertEqual(fake.requests,[])

    async def test_non200_redirect_and_error_capsules_retained_no_follow_or_retry(self):
        for status in (301,302,307,308,401,403,429,500):
            with self.subTest(status=status):
                item,fake=self.fixture(lambda request,status=status:reply(request,status=status,body=b'{"error":"fixture"}',
                    headers={'location':'https://other.invalid','x-ratelimit-remaining':'-1'}))
                result=await item.collect(prepared())
                self.assertFalse(result.completed);self.assertEqual(len(fake.requests),1)
                self.assertEqual(len(result.capsules),1)
                self.assertEqual(result.capsules[0].to_dict()['http_status'],str(status))
                self.assertEqual(result.capsules[0].to_dict()['safe_response_metadata']['x_ratelimit_remaining'],'-1')
                self.assertFalse(result.native_admission)

    async def test_wrong_network_null_time_wrong_rpc_identity_and_null_price_block_refuse(self):
        for defect in ('network','time','rpc_id','price_block'):
            def handler(request):
                if request.method=='GET':
                    raw=response_body(request)
                    if defect=='price_block':raw=raw.replace(b'348004023',b'null')
                    return reply(request,body=raw)
                body=json.loads(request.content)
                if defect=='network' and body['method']=='getGenesisHash':return reply(request,body=a.canonical({'jsonrpc':'2.0','id':body['id'],'result':'devnet'}))
                if defect=='time' and body['method']=='getBlockTime':return reply(request,body=a.canonical({'jsonrpc':'2.0','id':body['id'],'result':None}))
                if defect=='rpc_id':return reply(request,body=a.canonical({'jsonrpc':'2.0','id':999,'result':a.GENESIS}))
                return reply(request)
            with self.subTest(defect=defect):
                item,fake=self.fixture(handler);result=await item.collect(prepared())
                self.assertFalse(result.completed);self.assertLessEqual(len(fake.requests),3)
                self.assertEqual(len(result.capsules),len(fake.requests))

    async def test_completed_transport_trio_does_not_grant_old_or_future_source_eligibility(self):
        for offset in (-40,5):
            def handler(request):
                if request.method=='POST':
                    body=json.loads(request.content)
                    if body['method']=='getBlockTime':return reply(request,body=a.canonical({
                        'jsonrpc':'2.0','id':body['id'],'result':time.time_ns()//1_000_000_000+offset}))
                return reply(request)
            item,fake=self.fixture(handler);plan=prepared();result=await item.collect(plan)
            self.assertTrue(result.completed);self.assertEqual(len(fake.requests),3)
            now=time.time_ns()//1000;mono=time.monotonic_ns()//1000
            clock=a.ClockBound(OWNER,RUN,MARKET,PROCESS,now,now,mono)
            with self.assertRaises(a.AcquisitionError):d.derive_observation(
                *result.capsules,plan.binding,clock,observation_id=plan.observation_id)
            self.assertFalse(result.provider_authenticated);self.assertFalse(result.native_admission)

    async def test_body_and_whitelisted_metadata_credential_echo_withheld_not_redacted_capsule(self):
        for defect in ('jup_body','rpc_body','metadata'):
            def handler(request):
                if defect=='jup_body':return reply(request,body=b'{"error":"'+KEY.encode()+b'"}')
                if defect=='rpc_body' and request.method=='POST':return reply(request,body=b'{"error":"'+RPC_SECRET.encode()+b'"}')
                if defect=='metadata':return reply(request,headers={'x-ratelimit-remaining':KEY})
                return reply(request)
            with self.subTest(defect=defect):
                item,fake=self.fixture(handler);result=await item.collect(prepared())
                self.assertFalse(result.completed);self.assertEqual(result.failure_code,'credential_echo_withheld')
                self.assertEqual(len(result.capsules),0 if defect!='rpc_body' else 1)
                self.assertTrue(result.diagnostics);self.assertTrue(dict(result.diagnostics[-1])['incomplete'])
                summary=json.dumps(result.summary());self.assertNotIn(KEY,summary);self.assertNotIn(RPC_SECRET,summary)

    async def test_ordinary_json_escaped_keys_rpc_secrets_and_url_are_withheld_as_incomplete(self):
        for secret,key_name in ((KEY,False),(KEY,True),(RPC_SECRET,False),(RPC_URL,False)):
            escaped=''.join('\\u%04x'%ord(char) for char in secret) if secret!=RPC_URL else secret.replace('/','\\/')
            raw=(('{"'+escaped+'":"fixture"}') if key_name else ('{"error":"'+escaped+'"}')).encode()
            self.assertNotIn(secret.encode(),raw)
            item,fake=self.fixture(lambda request,raw=raw:reply(request,status=401,body=raw))
            result=await item.collect(prepared())
            self.assertFalse(result.completed);self.assertEqual(result.failure_code,'credential_echo_withheld')
            self.assertFalse(result.capsules);self.assertEqual(len(fake.requests),1)
            self.assertTrue(dict(result.diagnostics[0])['incomplete'])
            summary=json.dumps(result.summary());self.assertNotIn(secret,summary)

    async def test_unparseable_or_unsafe_json_scan_withholds_without_reencoding_raw(self):
        for raw in (b'{bad}',b'{"duplicate":1,"duplicate":2}',b'{"error":"\\ud800"}',b'not JSON'):
            item,fake=self.fixture(lambda request,raw=raw:reply(request,status=500,body=raw))
            result=await item.collect(prepared());self.assertFalse(result.completed)
            self.assertEqual(result.failure_code,'invalid_json_for_credential_scan')
            self.assertFalse(result.capsules);self.assertEqual(len(fake.requests),1)

    async def test_length_encoding_duplicate_headers_overflow_and_metadata_types_refuse(self):
        cases=[(b'{}',{'content-length':'999'}),(b'{}',{'content-encoding':'gzip'}),
            (b'x'*(a.BODY_LIMITS['jupiter-price-v3']+1),{}),
            (b'{}',{'x-ratelimit-current':'true'}),(b'{}',{'content-type':'application/json; charset=latin1'})]
        for body,headers in cases:
            with self.subTest(headers=headers):
                item,fake=self.fixture(lambda request:reply(request,body=body,headers=headers))
                result=await item.collect(prepared());self.assertFalse(result.completed)
                self.assertEqual(len(fake.requests),1);self.assertFalse(result.capsules)
        item,fake=self.fixture(lambda request:httpx.Response(200,headers=[('content-type','application/json'),
            ('content-length','2'),('content-length','2')],stream=Stream([b'{}'])))
        result=await item.collect(prepared());self.assertFalse(result.completed);self.assertFalse(result.capsules)

    async def test_whole_packet_trickle_and_synchronous_parser_time_consumes_same_deadline(self):
        bounds=t.TransportBounds(operation_us=80_000,connect_us=50_000,read_us=50_000,write_us=50_000,pool_us=10_000)
        item,fake=self.fixture(lambda request:reply(request,stream=Stream([b'{',b'"x"',b':1}',b' '],delay=.04)),bounds=bounds)
        result=await item.collect(prepared());self.assertFalse(result.completed);self.assertEqual(len(fake.requests),1)
        item,fake=self.fixture(bounds=bounds)
        real=d._price
        def slow(*args):time.sleep(.1);return real(*args)
        with patch.object(d,'_price',side_effect=slow):result=await item.collect(prepared())
        self.assertFalse(result.completed);self.assertEqual(result.failure_code,'acquisition_deadline')
        self.assertEqual(len(fake.requests),1)

    async def test_slow_result_bookkeeping_refuses_success_but_retains_exact_original_trio(self):
        bounds=t.TransportBounds(operation_us=80_000,connect_us=50_000,read_us=50_000,write_us=50_000,pool_us=10_000)
        item,fake=self.fixture(bounds=bounds);original=t.PacketResult.summary;calls=[]
        def slow(result):
            calls.append(result.completed)
            if result.completed:time.sleep(.1)
            return original(result)
        with patch.object(t.PacketResult,'summary',slow):result=await item.collect(prepared())
        self.assertFalse(result.completed);self.assertEqual(result.failure_code,'acquisition_deadline')
        self.assertEqual(len(result.capsules),3);self.assertEqual(len(fake.requests),3)
        self.assertEqual(calls,[True])
        self.assertIs(await item.collect(prepared()),result);self.assertEqual(len(fake.requests),3)

    async def test_failed_result_bookkeeping_closes_and_retains_original_without_summary_retry(self):
        item,fake=self.fixture();calls=[]
        def failed(result):calls.append(result.completed);raise ValueError(KEY+' '+RPC_URL)
        with patch.object(t.PacketResult,'summary',failed):result=await item.collect(prepared())
        self.assertFalse(result.completed);self.assertEqual(result.failure_code,'invalid_or_unavailable_packet')
        self.assertEqual(calls,[True]);self.assertEqual(len(result.capsules),3);self.assertEqual(len(fake.requests),3)
        self.assertEqual(item._retained_bytes,t.PACKET_RESERVE_BYTES)
        self.assertIs(await item.collect(prepared()),result)
        with self.assertRaises(t.RecordedTransportError):await item.collect(prepared(1))
        self.assertEqual(len(fake.requests),3);self.assertNotIn(KEY,json.dumps(result.summary()))

    async def test_cancelled_waiter_keeps_original_packet_and_refuses_fresh_identity(self):
        entered,release=asyncio.Event(),asyncio.Event()
        async def handler(request):
            if len(fake.requests)==1:entered.set();await release.wait()
            return reply(request)
        item,fake=self.fixture(handler);plan=prepared()
        waiter=asyncio.create_task(item.collect(plan));await asyncio.wait_for(entered.wait(),1)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):await waiter
        self.assertTrue(item.busy)
        with self.assertRaises(t.RecordedTransportError):await item.collect(prepared(1))
        release.set();result=await item.collect(plan)
        self.assertTrue(result.completed);self.assertEqual(len(fake.requests),3);self.assertFalse(item.busy)
        cached=await item.collect(plan);self.assertIs(cached,result);self.assertEqual(len(fake.requests),3)

    async def test_original_replay_never_refreshes_receipts_or_conflicts_with_new_payload(self):
        item,fake=self.fixture();plan=prepared();result=await item.collect(plan)
        before=tuple(cap.wire for cap in result.capsules)
        self.assertIs(await item.collect(plan),result);self.assertEqual(len(fake.requests),3)
        self.assertEqual(tuple(cap.wire for cap in result.capsules),before)
        with self.assertRaises(t.RecordedTransportError):await item.collect(replace(plan,genesis_rpc_id=3))
        with self.assertRaises(t.RecordedTransportError):await item.collect(replace(prepared(1),price_record_id=plan.price_record_id))
        await item.close();self.assertIs(await item.collect(plan),result)

    async def test_retention_capacity_refuses_before_next_io_and_preserves_original_results(self):
        item,fake=self.fixture(bounds=t.TransportBounds(packet_limit=1))
        result=await item.collect(prepared())
        with self.assertRaises(t.RecordedTransportError) as caught:await item.collect(prepared(1))
        self.assertEqual(caught.exception.code,'retention_capacity');self.assertEqual(len(fake.requests),3)
        self.assertIs(await item.collect(prepared()),result)

    async def test_owned_log_guard_precedes_existing_filter_preserves_unrelated_tasks_and_exact_cleanup(self):
        logger=logging.getLogger('httpcore.http11');spy=SpyFilter();sink=CaptureHandler();equal=EqualityFilter()
        before=tuple(logger.filters);level=logger.level
        logger.addFilter(spy);logger.filters.append(equal);logger.addHandler(sink);logger.setLevel(logging.DEBUG)
        self.addCleanup(logger.setLevel,level);self.addCleanup(logger.removeHandler,sink)
        self.addCleanup(lambda:logger.filters.__setitem__(slice(None),list(before)))
        started,release=asyncio.Event(),asyncio.Event()
        async def handler(request):
            logger.debug('private headers %s %s',KEY,RPC_URL)
            if len(fake.requests)==1:started.set();await release.wait()
            return reply(request)
        item,fake=self.fixture(handler)
        task=asyncio.create_task(item.collect(prepared()));await asyncio.wait_for(started.wait(),1)
        logger.debug('unrelated task remains visible')
        release.set();result=await task;self.assertTrue(result.completed)
        self.assertEqual(sink.messages,['unrelated task remains visible'])
        self.assertEqual(spy.messages,['unrelated task remains visible'])
        await item.close()
        self.assertEqual(tuple(logger.filters),before+(spy,equal))
        self.assertTrue(any(value is equal for value in logger.filters))
        self.assertFalse(any(value is item._filter for value in logger.filters))

    async def test_default_record_factory_required_before_transport_or_io_without_mutating_it(self):
        real=logging.getLogRecordFactory();seen=[]
        def foreign(*args,**kwargs):seen.append(args);return real(*args,**kwargs)
        with patch.object(t,'_transport',side_effect=AssertionError('No transport construction')):
            logging.setLogRecordFactory(foreign)
            try:
                with self.assertRaises(t.RecordedTransportError):t.ProviderRecordedTransport(KEY,RPC_URL,read_only_opt_in=True)
                self.assertIs(logging.getLogRecordFactory(),foreign);self.assertEqual(seen,[])
            finally:logging.setLogRecordFactory(real)
        item,fake=self.fixture();logging.setLogRecordFactory(foreign)
        try:
            with self.assertRaises(t.RecordedTransportError):await item.collect(prepared())
            self.assertEqual(fake.requests,[])
        finally:logging.setLogRecordFactory(real)

    async def test_two_transports_guard_ownership_and_context_do_not_suppress_other_logs(self):
        first,fake1=self.fixture();second,fake2=self.fixture()
        for logger in first._loggers:
            self.assertTrue(any(value is first._filter for value in logger.filters))
            self.assertTrue(any(value is second._filter for value in logger.filters))
        self.assertTrue((await first.collect(prepared())).completed)
        await first.close()
        self.assertTrue((await second.collect(prepared(1))).completed)
        for logger in second._loggers:self.assertTrue(any(value is second._filter for value in logger.filters))

    async def test_cancelled_waiter_during_cleanup_keeps_guard_and_owned_close_until_finished(self):
        entered,release=asyncio.Event(),asyncio.Event();streams=[]
        def handler(request):
            stream=Stream([response_body(request)],close_entered=entered if not streams else None,
                close_release=release if not streams else None);streams.append(stream)
            return reply(request,stream=stream)
        item,fake=self.fixture(handler);waiter=asyncio.create_task(item.collect(prepared()))
        await asyncio.wait_for(entered.wait(),1);waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):await waiter
        self.assertTrue(item.cleanup_pending)
        for logger in item._loggers:self.assertTrue(any(value is item._filter for value in logger.filters))
        release.set();result=await item.collect(prepared())
        self.assertTrue(result.completed);self.assertTrue(all(stream.closed==1 for stream in streams))
        await item.close();self.assertEqual(fake.closed,1)
        for logger in item._loggers:self.assertFalse(any(value is item._filter for value in logger.filters))

    async def test_private_url_exception_text_is_fixed_and_not_retained_in_diagnostics(self):
        def handler(request):raise httpx.ConnectError(RPC_URL+' '+KEY,request=request)
        item,fake=self.fixture(handler);result=await item.collect(prepared())
        self.assertFalse(result.completed)
        summary=json.dumps(result.summary());self.assertNotIn(KEY,summary);self.assertNotIn(RPC_SECRET,summary)
        self.assertNotIn(KEY,str(t.RecordedTransportError(KEY)))

    async def test_late_original_cleanup_keeps_capsule_pins_and_refuses_next_request(self):
        bounds=t.TransportBounds(operation_us=80_000,connect_us=50_000,read_us=50_000,write_us=50_000,
            pool_us=10_000,cleanup_us=200_000)
        class LateClose(Stream):
            async def aclose(self):self.closed+=1;await asyncio.sleep(.12)
        item,fake=self.fixture(lambda request:reply(request,stream=LateClose([response_body(request)])),bounds=bounds)
        result=await item.collect(prepared())
        self.assertFalse(result.completed);self.assertEqual(len(fake.requests),1)
        self.assertEqual(len(result.capsules),1)
        diagnostic=dict(result.diagnostics[0])
        self.assertEqual(diagnostic['record_id'],prepared().price_record_id)
        self.assertEqual(diagnostic['request_sha256'],hashlib.sha256(a.public_request('jupiter-price-v3')).hexdigest())
        self.assertEqual(diagnostic['endpoint_binding_id'],prepared().binding.endpoint('jupiter-price-v3'))
        while item.cleanup_pending:await asyncio.sleep(.01)

    async def test_cleanup_timeout_preserves_owned_context_and_filters_until_exact_owned_completion(self):
        entered,release=asyncio.Event(),asyncio.Event()
        logger=logging.getLogger('httpcore.connection');sink=CaptureHandler();level=logger.level
        logger.addHandler(sink);logger.setLevel(logging.DEBUG)
        self.addCleanup(logger.setLevel,level);self.addCleanup(logger.removeHandler,sink)
        class SlowClose(Stream):
            async def aclose(self):
                self.closed+=1;entered.set();await release.wait();logger.debug('late private %s',KEY)
        streams=[]
        def handler(request):
            stream=SlowClose([response_body(request)]);streams.append(stream);return reply(request,stream=stream)
        item,fake=self.fixture(handler,bounds=t.TransportBounds(cleanup_us=20_000))
        result=await item.collect(prepared());self.assertEqual(result.failure_code,'cleanup_incomplete')
        self.assertEqual(len(result.capsules),1);self.assertTrue(item.cleanup_pending)
        with self.assertRaises(t.RecordedTransportError):await item.close()
        self.assertEqual(fake.closed,0)
        self.assertTrue(all(any(value is item._filter for value in logger.filters) for logger in item._loggers))
        release.set()
        while item.cleanup_pending:await asyncio.sleep(.01)
        await item.close();self.assertEqual(streams[0].closed,1);self.assertEqual(fake.closed,1)
        self.assertEqual(sink.messages,[])

    async def test_mutated_context_keylog_or_foreign_leading_filter_refused_before_io(self):
        item,fake=self.fixture()
        with tempfile.TemporaryDirectory(prefix='dashboard-v3-explicit-keylog-test-') as folder:
            item._context.keylog_filename=str(Path(folder)/'created-by-test-setter')
            with self.assertRaises(t.RecordedTransportError):await item.collect(prepared())
            self.assertEqual(fake.requests,[])
            item._context.keylog_filename=None
        spy=SpyFilter();logger=item._loggers[0];logger.filters.insert(0,spy)
        try:
            with self.assertRaises(t.RecordedTransportError):await item.collect(prepared())
            self.assertEqual(fake.requests,[])
        finally:logger.filters[:]=[value for value in logger.filters if value is not spy]

    async def test_cancelled_transport_close_waiter_preserves_owned_cleanup_without_second_close(self):
        entered,release=asyncio.Event(),asyncio.Event()
        logger=logging.getLogger('httpcore.connection');sink=CaptureHandler();level=logger.level
        logger.addHandler(sink);logger.setLevel(logging.DEBUG)
        self.addCleanup(logger.setLevel,level);self.addCleanup(logger.removeHandler,sink)
        class ClosingTransport(FakeTransport):
            async def aclose(self):
                self.closed+=1;entered.set();await release.wait();logger.debug('close private %s %s',KEY,RPC_URL)
        fake=ClosingTransport(lambda request:reply(request))
        with patch.object(t,'_transport',return_value=fake):item=t.ProviderRecordedTransport(KEY,RPC_URL,read_only_opt_in=True)
        self.items.append(item);task=asyncio.create_task(item.close());await asyncio.wait_for(entered.wait(),1)
        task.cancel()
        with self.assertRaises(t.RecordedTransportError):await task
        self.assertTrue(item.cleanup_pending);self.assertEqual(fake.closed,1)
        self.assertTrue(all(any(value is item._filter for value in logger.filters) for logger in item._loggers))
        release.set()
        while item.cleanup_pending:await asyncio.sleep(.01)
        await item.close();self.assertEqual(fake.closed,1);self.assertEqual(sink.messages,[])

    async def test_regressed_integer_monotonic_clock_refuses_after_original_capture(self):
        item,fake=self.fixture();actual=item._sample;calls=[]
        def clock():
            wall,mono=actual();calls.append(mono)
            if len(calls)>4:return wall,calls[0]-1
            return wall,mono
        with patch.object(item,'_sample',side_effect=clock):result=await item.collect(prepared())
        self.assertFalse(result.completed);self.assertEqual(len(fake.requests),1)
        self.assertEqual(result.failure_code,'acquisition_deadline')

    async def test_transport_source_has_no_ambient_credentials_uuid_or_native_authority_calls(self):
        source=Path(t.__file__).read_text();tree=ast.parse(source)
        names=[ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node,ast.Call)]
        for forbidden in ('os.getenv','os.environ.get','ssl.create_default_context','uuid4',
                'httpx.AsyncClient','logging.setLogRecordFactory','logging.basicConfig'):
            self.assertNotIn(forbidden,names)
        self.assertNotIn('SourceMark',names);self.assertNotIn('native_admit',names)

    async def test_exact_public_ca_digest_version_and_parser_security_policy_pins(self):
        self.assertEqual(t.TRANSPORT_POLICY_SHA256,hashlib.sha256(t.TRANSPORT_POLICY_WIRE).hexdigest())
        policy=json.loads(t.TRANSPORT_POLICY_WIRE)
        self.assertEqual(policy['acquisition_parser_policy_sha256'],a.POLICY_SHA256)
        self.assertEqual(policy['ca_bundle_sha256'],t.CA_BUNDLE_SHA256)
        self.assertEqual(policy['certifi_version'],t.CERTIFI_VERSION)
        self.assertFalse(policy['native_admission'])
        with tempfile.TemporaryDirectory(prefix='dashboard-v3-wrong-ca-pin-') as folder:
            ca_file,_=tls_fixture(folder)
            with patch.object(t.certifi,'where',return_value=str(ca_file)),patch.object(t,'_transport') as backend:
                with self.assertRaises(t.RecordedTransportError):t.ProviderRecordedTransport(KEY,RPC_URL,read_only_opt_in=True)
                backend.assert_not_called()
        real=t.importlib.metadata.version
        with patch.object(t.importlib.metadata,'version',side_effect=lambda name:'unknown' if name=='certifi' else real(name)),\
                patch.object(t,'_transport') as backend:
            with self.assertRaises(t.RecordedTransportError):t.ProviderRecordedTransport(KEY,RPC_URL,read_only_opt_in=True)
            backend.assert_not_called()


def tls_fixture(folder,*,hostname_ok=True):
    """Owned ephemeral CA/leaf; no provider CA, key, account, or DNS resolution."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    now=datetime.now(timezone.utc);ca_key=ec.generate_private_key(ec.SECP256R1())
    ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Dashboard owned transport fixture CA')])
    ca=x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key()).serial_number(
        x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(
        now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(ca_key,hashes.SHA256())
    leaf_key=ec.generate_private_key(ec.SECP256R1())
    hosts=['api.jup.ag','rpc.fixture.invalid'] if hostname_ok else ['wrong.fixture.invalid']
    leaf=x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,hosts[0])])).issuer_name(
        ca_name).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
        now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1)).add_extension(
        x509.BasicConstraints(ca=False,path_length=None),critical=True).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(host) for host in hosts]),critical=False).sign(ca_key,hashes.SHA256())
    ca_file,cert_file,key_file=[Path(folder)/name for name in ('ca.pem','leaf.pem','leaf.key')]
    ca_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM));cert_file.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()));key_file.chmod(0o600)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert_file,key_file)
    return ca_file,context


class ProviderRecordedTransportTLSFixtureTests(unittest.IsolatedAsyncioTestCase):
    """Real pinned HTTPX/httpcore/OpenSSL, routed only to our owned 127.0.0.1 port."""
    async def exercise(self,*,wrong_ca=False,hostname_ok=True,truncate=False):
        from httpcore._backends.anyio import AnyIOBackend
        with tempfile.TemporaryDirectory(prefix='dashboard-v3-owned-tls-') as folder:
            ca_file,server_context=tls_fixture(folder,hostname_ok=hostname_ok)
            messages=[];server_tasks=set();writers=set();server_errors=[];handshake_errors=[]
            loop=asyncio.get_running_loop();old_exception_handler=loop.get_exception_handler()
            def owned_fixture_exceptions(loop,context):
                if context.get('message')=='Error on transport creation for incoming connection' and isinstance(
                        context.get('exception'),(ConnectionResetError,ssl.SSLError)):
                    handshake_errors.append(type(context['exception']).__name__)
                else:server_errors.append(context.get('message','unexpected fixture loop error'))
            loop.set_exception_handler(owned_fixture_exceptions)
            async def serve(reader,writer):
                current=asyncio.current_task();server_tasks.add(current);writers.add(writer)
                try:
                    head=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),1)
                    lines=head.split(b'\r\n');method,path,_=lines[0].decode().split(' ')
                    headers={name.lower():value.strip() for name,value in (line.decode().split(':',1) for line in lines[1:] if line)}
                    body=await reader.readexactly(int(headers.get('content-length','0')))
                    messages.append((method,path,headers,body,writer.get_extra_info('ssl_object').version()))
                    outgoing=httpx.Request(method,'https://fixture.invalid',content=body)
                    raw=response_body(outgoing)
                    length=len(raw)+1 if truncate else len(raw)
                    writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(length).encode()+
                        b'\r\nConnection: close\r\n\r\n'+raw);await writer.drain()
                except Exception as error:server_errors.append(type(error).__name__)
                finally:
                    writer.close()
                    try:await writer.wait_closed()
                    except (ConnectionResetError,ssl.SSLError):pass
                    finally:writers.discard(writer);server_tasks.discard(current)
            server=await asyncio.start_server(serve,'127.0.0.1',0,ssl=server_context,ssl_handshake_timeout=1)
            owned_port=server.sockets[0].getsockname()[1];connections=[]
            backend=AnyIOBackend();real_transport=t._transport
            class OnlyOwnedLoopback:
                async def connect_tcp(self,host,port,**kwargs):
                    if (host,port) not in (('api.jup.ag',443),('rpc.fixture.invalid',443)):
                        raise AssertionError('Fixture refused foreign destination')
                    connections.append((host,port))
                    return await backend.connect_tcp('127.0.0.1',owned_port,**kwargs)
                async def connect_unix_socket(self,*args,**kwargs):raise AssertionError('No Unix connections')
                async def sleep(self,seconds):raise AssertionError('No retry backoff')
            def owned_transport(context):
                result=real_transport(context);result._pool._network_backend=OnlyOwnedLoopback();return result
            resolver,connector=socket.getaddrinfo,socket.socket.connect
            def only_resolve(host,*args,**kwargs):
                if host not in ('127.0.0.1',b'127.0.0.1'):raise AssertionError('No foreign DNS')
                return resolver(host,*args,**kwargs)
            def only_connect(sock,address):
                if address!=('127.0.0.1',owned_port):raise AssertionError('No foreign TCP')
                return connector(sock,address)
            keylog=Path(folder)/'inherited-keylog-must-not-exist';item=None
            try:
                # The real production context constructor loads our test-only CA;
                # production has no injectable backend/context API.
                ca_path=t.certifi.where() if wrong_ca else str(ca_file)
                ca_digest=hashlib.sha256(Path(ca_path).read_bytes()).hexdigest()
                with patch.object(t.certifi,'where',return_value=ca_path),patch.object(t,'CA_BUNDLE_SHA256',ca_digest),\
                        patch.object(t,'_transport',side_effect=owned_transport),\
                        patch.object(socket,'getaddrinfo',side_effect=only_resolve),patch.object(socket.socket,'connect',only_connect),\
                        patch.dict(os.environ,{'SSLKEYLOGFILE':str(keylog),'SSL_CERT_FILE':'/missing/unrelated-ca','HTTPS_PROXY':'https://unrelated.invalid'}):
                    item=t.ProviderRecordedTransport(KEY,RPC_URL,read_only_opt_in=True)
                    result=await item.collect(prepared());await item.close()
                self.assertFalse(keylog.exists());self.assertIsNone(item._context.keylog_filename)
                self.assertEqual(len(connections),3 if not (wrong_ca or not hostname_ok or truncate) else 1)
                if wrong_ca or not hostname_ok:
                    self.assertFalse(result.completed);self.assertFalse(result.capsules);self.assertFalse(messages)
                elif truncate:
                    self.assertFalse(result.completed);self.assertFalse(result.capsules);self.assertEqual(len(messages),1)
                else:
                    self.assertTrue(result.completed);self.assertEqual(len(result.capsules),3)
                    self.assertEqual(len(messages),3);self.assertEqual(messages[0][1],'/price/v3?ids='+a.MINT)
                    self.assertEqual(messages[0][2]['x-api-key'],KEY)
                    for message in messages[1:]:
                        self.assertEqual(message[1],'/?api-key='+RPC_SECRET);self.assertNotIn('x-api-key',message[2])
                    self.assertEqual(json.loads(messages[2][3])['params'],[348004023])
                    self.assertTrue(all(message[4] in ('TLSv1.2','TLSv1.3') for message in messages))
                    self.assertFalse(result.provider_authenticated);self.assertFalse(result.native_admission)
            finally:
                if item is not None:await item.close()
                server.close();await server.wait_closed()
                for writer in tuple(writers):writer.close()
                if server_tasks:await asyncio.wait_for(asyncio.gather(*tuple(server_tasks)),2)
                await asyncio.sleep(0)
                loop.set_exception_handler(old_exception_handler)
                self.assertEqual(server_errors,[])
                if not (wrong_ca or not hostname_ok):self.assertEqual(handshake_errors,[])

    async def test_owned_real_tls_original_trio_hostname_ca_and_inherited_keylog(self):await self.exercise()
    async def test_owned_real_wrong_ca_refuses_without_http_retry(self):await self.exercise(wrong_ca=True)
    async def test_owned_real_wrong_hostname_refuses_without_http_retry(self):await self.exercise(hostname_ok=False)
    async def test_owned_real_truncated_http_body_refuses_without_retry(self):await self.exercise(truncate=True)


if __name__=='__main__':unittest.main()
