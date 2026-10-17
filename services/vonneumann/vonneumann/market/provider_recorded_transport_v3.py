"""Disconnected, explicitly opted-in original Price/RPC read-only transport.

No environment credentials, UUID allocation, native writes/authority, SourceMark,
lease, retry, source sequence, service wiring or running authority. Actual calls
remain a separately gated operator action; initial tests use owned fake endpoints.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import importlib.metadata
import logging
from pathlib import Path
import re
import ssl
import time
from urllib.parse import urlsplit,parse_qsl,unquote

import certifi
import httpx

from . import provider_acquisition_v3 as a,provider_derivation_v3 as d

PRICE_URL='https://api.jup.ag/price/v3'
LOGGER_NAMES=('httpx','httpcore.connection','httpcore.http11','httpcore.http2','httpcore.proxy','httpcore.socks')
_LOG_OWNER=ContextVar('dashboard_v3_owned_transport_log_context',default=None)
PACKET_FORMAT='ga-provider-original-readonly-packet-research-v3'
MAX_CA_BYTES=1024*1024
PACKET_RESERVE_BYTES=1024*1024
CERTIFI_VERSION='2026.7.22'
CA_BUNDLE_SHA256='9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f'
TRANSPORT_POLICY_WIRE=a.canonical({
    'format':'ga-provider-readonly-transport-security-policy-research-v3-v1',
    'acquisition_parser_policy_sha256':a.POLICY_SHA256,
    'httpx_version':'0.28.1','httpcore_version':'1.0.9',
    'certifi_version':CERTIFI_VERSION,'ca_bundle_sha256':CA_BUNDLE_SHA256,
    'tls':'manual-PROTOCOL_TLS_CLIENT-CERT_REQUIRED-hostname-minTLS12-keylogNone-exactCAbytes',
    'requests':'serialized-original-price-mainnetGenesis-exactBlockTime-noRetry-noRedirect-noEnvProxy',
    'clock':'original-time_ns-and-monotonic_ns-integer-us-before-parsing-and-cleanup',
    'deadline':'whole-packet-maximum-5000000us-with-postCPU-guards-and-separately-owned-cleanup',
    'privacy':'trusted-default-LogRecordFactory-owned-ContextVar-first-leaf-filter-identity-cleanup',
    'credential_echo':'bounded-strict-JSON-decoded-keys-strings-and-literal-bytes-withhold-incomplete-never-redact',
    'retention':'bounded-process-local-original-results-no-fresh-IDs-for-uncertain-original',
    'native_admission':False,'provider_authenticated':False,'running_authority':False})
TRANSPORT_POLICY_SHA256=hashlib.sha256(TRANSPORT_POLICY_WIRE).hexdigest()
_ERROR_CODES=frozenset({'invalid_bounds','invalid_private_configuration','unsupported_logging_runtime',
    'invalid_tls_runtime','read_only_collection_closed','unsupported_transport_runtime','foreign_event_loop',
    'acquisition_deadline','invalid_response_metadata','cleanup_incomplete','invalid_response_encoding',
    'invalid_response_length','response_overflow','credential_echo_withheld','invalid_json_for_credential_scan','request_unavailable',
    'invalid_or_unavailable_record','price_http_failure','wrong_network','invalid_or_unavailable_packet',
    'packet_busy','original_packet_pending','collection_closed','invalid_prepared_packet',
    'active_packet_incomplete','original_packet_conflict','original_identity_reused','retention_capacity'})


class RecordedTransportError(RuntimeError):
    def __init__(self,code):
        self.code=code if type(code) is str and code in _ERROR_CODES else 'invalid_or_unavailable_packet'
        super().__init__('Recorded provider transport refused operation: '+self.code)


@dataclass(frozen=True,slots=True)
class TransportBounds:
    operation_us:int=5_000_000
    connect_us:int=500_000
    read_us:int=1_000_000
    write_us:int=1_000_000
    pool_us:int=100_000
    cleanup_us:int=1_000_000
    result_bytes_limit:int=8*1024*1024
    packet_limit:int=4000
    def __post_init__(self):
        for key in ('operation_us','connect_us','read_us','write_us','pool_us','cleanup_us'):
            value=getattr(self,key)
            if type(value) is not int or not 0<value<=5_000_000:
                raise RecordedTransportError('invalid_bounds')
        if max(self.connect_us,self.read_us,self.write_us,self.pool_us)>self.operation_us:
            raise RecordedTransportError('invalid_bounds')
        if type(self.result_bytes_limit) is not int or not PACKET_RESERVE_BYTES<=self.result_bytes_limit<=64*1024*1024 \
                or type(self.packet_limit) is not int or not 1<=self.packet_limit<=4000:
            raise RecordedTransportError('invalid_bounds')


@dataclass(frozen=True,slots=True)
class PreparedPacket:
    """Original explicit reserved identities; lexical validity is not authority."""
    binding:a.IssuerBinding
    price_record_id:str
    genesis_record_id:str
    block_time_record_id:str
    observation_id:str
    genesis_rpc_id:int
    block_time_rpc_id:int
    def __post_init__(self):
        a.require(type(self.binding) is a.IssuerBinding);self.binding.__post_init__()
        a.require(set(family for family,_ in self.binding.endpoint_bindings)=={'jupiter-price-v3','solana-rpc'})
        ids=(self.price_record_id,self.genesis_record_id,self.block_time_record_id,self.observation_id)
        for identity in ids:a.uuid(identity)
        a.require(len(set(ids))==4)
        a.integer(self.genesis_rpc_id,2**31-1,1);a.integer(self.block_time_rpc_id,2**31-1,1)
        a.require(self.genesis_rpc_id!=self.block_time_rpc_id)
    @property
    def wire(self):
        self.__post_init__()
        return a.canonical({'format':'ga-provider-prepared-original-readonly-packet-research-v3',
            'transport_policy_sha256':TRANSPORT_POLICY_SHA256,'binding':{key:getattr(self.binding,key)
            for key in ('owner_id','run_id','market_epoch','acquisition_epoch','issuer_binding_id','parser_policy_sha256')},
            'endpoints':list(self.binding.endpoint_bindings),
            'price_record_id':self.price_record_id,'genesis_record_id':self.genesis_record_id,
            'block_time_record_id':self.block_time_record_id,'observation_id':self.observation_id,
            'genesis_rpc_id':str(self.genesis_rpc_id),'block_time_rpc_id':str(self.block_time_rpc_id)})


@dataclass(frozen=True,slots=True)
class PacketResult:
    """Private original evidence/diagnostics, never a committed native receipt."""
    prepared:PreparedPacket=field(repr=False)
    capsules:tuple=field(repr=False)
    diagnostics:tuple=field(repr=False)
    completed:bool
    failure_code:str|None
    ca_bundle_sha256:str
    @property
    def native_admission(self):return False
    @property
    def running_authority(self):return False
    @property
    def provider_authenticated(self):return False
    def summary(self):
        return {'format':PACKET_FORMAT,'original_observation_id':self.prepared.observation_id,
            'transport_policy_sha256':TRANSPORT_POLICY_SHA256,'ca_bundle_sha256':self.ca_bundle_sha256,
            'records':[{'record_id':item.to_dict()['record_id'],'capsule_sha256':item.sha256}
                       for item in self.capsules],
            'diagnostics':[dict(item) for item in self.diagnostics],
            'completed':self.completed,'failure_code':self.failure_code,
            'provider_authenticated':False,'native_admission':False,'running_authority':False}


def _runtime_loggers():
    if logging.getLogRecordFactory() is not logging.LogRecord:
        raise RecordedTransportError('unsupported_logging_runtime')
    loggers=tuple(logging.getLogger(name) for name in LOGGER_NAMES)
    if any(type(logger) is not logging.Logger for logger in loggers):
        raise RecordedTransportError('unsupported_logging_runtime')
    return loggers


class _OwnedLogFilter(logging.Filter):
    def __init__(self,owner):super().__init__();self.owner=owner
    def filter(self,record):return _LOG_OWNER.get() is not self.owner


def _tls_context():
    """No create_default_context: it honors inherited SSLKEYLOGFILE."""
    try:
        with Path(certifi.where()).open('rb') as handle:ca=handle.read(MAX_CA_BYTES+1)
        if not 0<len(ca)<=MAX_CA_BYTES:raise RecordedTransportError('invalid_tls_runtime')
        digest=hashlib.sha256(ca).hexdigest()
        if digest!=CA_BUNDLE_SHA256:raise RecordedTransportError('invalid_tls_runtime')
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname=True;context.verify_mode=ssl.CERT_REQUIRED
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_verify_locations(cadata=ca.decode('ascii'))
        if context.keylog_filename is not None:raise RecordedTransportError('invalid_tls_runtime')
        return context,digest
    except (OSError,ValueError,UnicodeError):
        raise RecordedTransportError('invalid_tls_runtime') from None


def _transport(context):
    return httpx.AsyncHTTPTransport(verify=context,trust_env=False,proxy=None,retries=0,
        http1=True,http2=False,limits=httpx.Limits(max_connections=1,max_keepalive_connections=1,
                                                keepalive_expiry=5))


def _private_configuration(key,rpc_url):
    if type(key) is not str or not 16<=len(key)<=512 or not re.fullmatch('[A-Za-z0-9_.-]+',key,re.ASCII):
        raise RecordedTransportError('invalid_private_configuration')
    try:
        if type(rpc_url) is not str or not 0<len(rpc_url)<=4096 or '\\' in rpc_url or any(
                char.isspace() or ord(char)<32 or ord(char)==127 for char in rpc_url):raise ValueError()
        parsed=urlsplit(rpc_url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username is not None or parsed.password is not None \
                or parsed.fragment or '#' in rpc_url or parsed.port not in (None,443):raise ValueError()
        parsed.hostname.encode('ascii')
        # Every provided query value is conservatively private. Long path
        # segments may contain credentials too; public request manifests never
        # contain the URL. No redacted body becomes an original capsule.
        secrets=[key,rpc_url]+[value for _,value in parse_qsl(parsed.query,keep_blank_values=True) if value]
        secrets += [unquote(value) for value in parsed.path.split('/') if len(unquote(value))>=16]
        sensitive=tuple(value.encode('utf-8') for value in secrets)
        if any(value in parsed.hostname.encode() for value in sensitive if len(value)>=16):raise ValueError()
        return sensitive
    except (ValueError,TypeError,UnicodeError):
        raise RecordedTransportError('invalid_private_configuration') from None


class ProviderRecordedTransport:
    """One owned loop/packet and retained original result after waiter loss."""
    def __init__(self,key,rpc_url,*,read_only_opt_in=False,bounds=None):
        if read_only_opt_in is not True:raise RecordedTransportError('read_only_collection_closed')
        if bounds is not None and type(bounds) is not TransportBounds:raise RecordedTransportError('invalid_bounds')
        self._bounds=TransportBounds() if bounds is None else bounds;self._bounds.__post_init__()
        self._sensitive=_private_configuration(key,rpc_url)
        if httpx.__version__!='0.28.1' or importlib.metadata.version('httpcore')!='1.0.9' \
                or importlib.metadata.version('certifi')!=CERTIFI_VERSION:
            raise RecordedTransportError('unsupported_transport_runtime')
        self._loggers=_runtime_loggers();self._owner=object();self._filter=_OwnedLogFilter(self._owner)
        self._context,self.ca_bundle_sha256=_tls_context()
        self._transport=_transport(self._context)
        self._key,self._rpc_url=key,rpc_url
        self._loop=None;self._active=None;self._original_wire=None;self._waiter=False
        self._closed=False;self._cleanup_tasks=set();self._cleanup_failed=False;self._close_task=None
        self._results={};self._used_ids=set();self._retained_bytes=0
        for logger in self._loggers:logger.filters.insert(0,self._filter)

    @property
    def native_admission(self):return False
    @property
    def running_authority(self):return False
    @property
    def busy(self):return self._active is not None
    @property
    def cleanup_pending(self):return any(not task.done() for task in self._cleanup_tasks)

    def _bind(self):
        loop=asyncio.get_running_loop()
        if self._loop is None:self._loop=loop
        if loop is not self._loop:raise RecordedTransportError('foreign_event_loop')

    def _guard(self):
        if tuple(_runtime_loggers())!=self._loggers:raise RecordedTransportError('unsupported_logging_runtime')
        for logger in self._loggers:
            positions=[index for index,item in enumerate(logger.filters) if item is self._filter]
            if len(positions)!=1 or any(type(item) is not _OwnedLogFilter for item in logger.filters[:positions[0]]):
                raise RecordedTransportError('unsupported_logging_runtime')
        context=self._context
        if context.check_hostname is not True or context.verify_mode!=ssl.CERT_REQUIRED \
                or context.minimum_version<ssl.TLSVersion.TLSv1_2 or context.keylog_filename is not None:
            raise RecordedTransportError('invalid_tls_runtime')

    def _sample(self):
        wall,mono=time.time_ns()//1000,time.monotonic_ns()//1000
        a.integer(wall);a.integer(mono);return wall,mono

    def _deadline(self,start):
        self._guard()
        elapsed=self._sample()[1]-start
        if not 0<=elapsed<self._bounds.operation_us:raise RecordedTransportError('acquisition_deadline')

    def _sensitive_echo(self,body,metadata,family):
        rows=(body,)+tuple(value.encode() for value in metadata.values())
        if any(secret in row for secret in self._sensitive for row in rows):return True
        # Inspect bounded decoded JSON keys/strings too: ordinary JSON escaping
        # must not smuggle an actual credential into an original raw capsule.
        # Never redact or serialize this decoded view as original evidence.
        try:payload=a.read_json(body,a.BODY_LIMITS[family],numeric=True)
        except a.AcquisitionError:
            raise RecordedTransportError('invalid_json_for_credential_scan') from None
        stack=[payload]
        while stack:
            value=stack.pop()
            if type(value) is dict:stack.extend(value.keys());stack.extend(value.values())
            elif type(value) is list:stack.extend(value)
            elif type(value) is str:
                raw=value.encode('utf-8')
                if any(secret in raw for secret in self._sensitive):return True
        return False

    def _metadata(self,response):
        result={};names={'x-ratelimit-current':'x_ratelimit_current',
            'x-ratelimit-remaining':'x_ratelimit_remaining','x-ratelimit-reset':'x_ratelimit_reset'}
        for source,target in names.items():
            values=response.headers.get_list(source)
            if len(values)>1:raise RecordedTransportError('invalid_response_metadata')
            if values:result[target]=values[0]
        content=response.headers.get_list('content-type')
        if len(content)>1:raise RecordedTransportError('invalid_response_metadata')
        if content:
            parts=[part.strip().lower() for part in content[0].split(';')]
            if parts[0]=='application/json' and all(part in ('charset=utf-8','charset="utf-8"') for part in parts[1:]):
                result['content_type']='application/json'
            elif response.status_code==200:raise RecordedTransportError('invalid_response_metadata')
        return result

    async def _cleanup(self,method):
        async def owned():
            token=_LOG_OWNER.set(self._owner)
            try:self._guard();await method();self._guard()
            finally:_LOG_OWNER.reset(token)
        task=asyncio.create_task(owned());self._cleanup_tasks.add(task)
        def observed(done):
            if done.cancelled() or done.exception() is not None:self._cleanup_failed=True;self._closed=True
            self._cleanup_tasks.discard(done)
        task.add_done_callback(observed)
        try:await asyncio.wait_for(asyncio.shield(task),self._bounds.cleanup_us/1_000_000)
        except (Exception,asyncio.CancelledError):
            self._closed=True
            raise RecordedTransportError('cleanup_incomplete') from None

    async def _capture(self,prepared,family,identity,request,*,deadline_start):
        self._deadline(deadline_start)
        public=a.request_fields(request,family)
        headers={'Accept':'application/json','Accept-Encoding':'identity'}
        if family=='jupiter-price-v3':
            headers['x-api-key']=self._key;url=PRICE_URL
            params=public['parameters'];content=b''
        else:
            headers['Content-Type']='application/json';url=self._rpc_url
            params=None;content=public['body_wire'].encode()
        timeouts=httpx.Timeout(connect=self._bounds.connect_us/1_000_000,read=self._bounds.read_us/1_000_000,
            write=self._bounds.write_us/1_000_000,pool=self._bounds.pool_us/1_000_000)
        outgoing=httpx.Request(public['method'],url,headers=headers,params=params,content=content,
                               extensions={'timeout':timeouts.as_dict()})
        response=None;original=None
        started_wall,started_mono=self._sample()
        original_diagnostic={'record_id':identity,'provider_family':family,
            'endpoint_binding_id':prepared.binding.endpoint(family),
            'request_sha256':hashlib.sha256(request).hexdigest(),
            'request_started_wall_us':str(started_wall),'request_started_monotonic_us':str(started_mono),
            'incomplete':True,'failure_code':'request_unavailable'}
        diagnostic=original_diagnostic
        try:
            self._guard();response=await self._transport.handle_async_request(outgoing)
            self._deadline(deadline_start)
            diagnostic['http_status']=str(response.status_code)
            encodings=response.headers.get_list('content-encoding')
            if len(encodings)>1 or any(value.lower()!='identity' for value in encodings):
                raise RecordedTransportError('invalid_response_encoding')
            lengths=response.headers.get_list('content-length')
            if len(lengths)>1:raise RecordedTransportError('invalid_response_length')
            expected=None
            if lengths:
                expected=a.counter(lengths[0],a.BODY_LIMITS[family])
            body=bytearray()
            async for chunk in response.stream:
                if type(chunk) is not bytes or len(body)+len(chunk)>a.BODY_LIMITS[family]:
                    raise RecordedTransportError('response_overflow')
                body.extend(chunk);self._deadline(deadline_start)
            received_wall,received_mono=self._sample()
            diagnostic['received_wall_us']=str(received_wall)
            diagnostic['received_monotonic_us']=str(received_mono)
            # Receipt is captured before parsing, metadata normalization or cleanup.
            raw=bytes(body)
            if expected is not None and len(raw)!=expected:raise RecordedTransportError('invalid_response_length')
            metadata=self._metadata(response)
            if self._sensitive_echo(raw,metadata,family):raise RecordedTransportError('credential_echo_withheld')
            original=a.capture_capsule(prepared.binding,record_id=identity,provider_family=family,
                request=request,raw_body=raw,http_status=response.status_code,
                started_wall_us=started_wall,received_wall_us=received_wall,
                started_monotonic_us=started_mono,received_monotonic_us=received_mono,
                safe_response_metadata=metadata)
            self._deadline(deadline_start)
            diagnostic=None
        except (Exception,asyncio.CancelledError) as error:
            code=error.code if type(error) is RecordedTransportError else 'invalid_or_unavailable_record'
            diagnostic['failure_code']=code
        finally:
            if response is not None:
                try:await self._cleanup(response.aclose)
                except RecordedTransportError:
                    diagnostic={**original_diagnostic,'failure_code':'cleanup_incomplete'}
        if diagnostic is not None:return original,diagnostic
        try:self._deadline(deadline_start)
        except RecordedTransportError as error:
            return original,{**original_diagnostic,'failure_code':error.code}
        return original,None

    async def _run(self,prepared):
        token=_LOG_OWNER.set(self._owner)
        try:return await self._run_owned(prepared)
        finally:_LOG_OWNER.reset(token)

    async def _run_owned(self,prepared):
        capsules=[];diagnostics=[];failure=None
        try:
            start=self._sample()[1]
            async with asyncio.timeout(self._bounds.operation_us/1_000_000):
                price,diag=await self._capture(prepared,'jupiter-price-v3',prepared.price_record_id,
                    a.public_request('jupiter-price-v3'),deadline_start=start)
                if price is not None:capsules.append(price)
                if diag is not None:diagnostics.append(tuple(diag.items()));raise RecordedTransportError(diag['failure_code'])
                if price.to_dict()['http_status']!='200':raise RecordedTransportError('price_http_failure')
                _,_,block=d._price(price,prepared.binding);self._deadline(start)
                genesis,diag=await self._capture(prepared,'solana-rpc',prepared.genesis_record_id,
                    a.public_request('solana-rpc',rpc_method='getGenesisHash',rpc_id=prepared.genesis_rpc_id),deadline_start=start)
                if genesis is not None:capsules.append(genesis)
                if diag is not None:diagnostics.append(tuple(diag.items()));raise RecordedTransportError(diag['failure_code'])
                _,network=d._rpc(genesis,prepared.binding,'getGenesisHash')
                if network!=a.GENESIS:raise RecordedTransportError('wrong_network')
                self._deadline(start)
                block_time,diag=await self._capture(prepared,'solana-rpc',prepared.block_time_record_id,
                    a.public_request('solana-rpc',rpc_method='getBlockTime',rpc_id=prepared.block_time_rpc_id,slot=block),deadline_start=start)
                if block_time is not None:capsules.append(block_time)
                if diag is not None:diagnostics.append(tuple(diag.items()));raise RecordedTransportError(diag['failure_code'])
                _,source_second=d._rpc(block_time,prepared.binding,'getBlockTime',slot=block)
                a.integer(source_second,a.MAX_SECOND);self._deadline(start)
        except (Exception,asyncio.CancelledError) as error:
            failure=error.code if type(error) is RecordedTransportError else 'invalid_or_unavailable_packet'
            self._closed=True
        result=PacketResult(prepared,tuple(capsules),tuple(diagnostics),failure is None,failure,self.ca_bundle_sha256)
        original_wire=prepared.wire
        try:
            charged=len(original_wire)+sum(len(item.wire)+len(item.raw_body) for item in result.capsules)
            charged+=len(a.canonical(result.summary()))
            if failure is None:self._deadline(start)
        except Exception as error:
            self._closed=True
            code=error.code if type(error) is RecordedTransportError else 'invalid_or_unavailable_packet'
            result=PacketResult(prepared,tuple(capsules),tuple(diagnostics),False,code,self.ca_bundle_sha256)
            # Conservatively charge the already reserved maximum; do not retry
            # failed or late bookkeeping, restamp receipts or replace originals.
            charged=PACKET_RESERVE_BYTES
        self._retained_bytes+=charged
        self._results[prepared.observation_id]=(original_wire,result)
        return result

    async def collect(self,prepared):
        self._bind()
        if type(prepared) is not PreparedPacket:raise RecordedTransportError('invalid_prepared_packet')
        original=prepared.wire
        cached=self._results.get(prepared.observation_id)
        if cached is not None:
            if cached[0]!=original:raise RecordedTransportError('original_packet_conflict')
            if self._active is not None and self._active.done() and self._original_wire==original:
                self._active=None;self._original_wire=None
            return cached[1]
        if self._waiter:raise RecordedTransportError('packet_busy')
        if self._active is not None:
            if original!=self._original_wire:raise RecordedTransportError('original_packet_pending')
        else:
            if self._closed or self.cleanup_pending or self._cleanup_failed:raise RecordedTransportError('collection_closed')
            ids=(prepared.observation_id,prepared.price_record_id,prepared.genesis_record_id,prepared.block_time_record_id)
            if any(identity in self._used_ids for identity in ids):raise RecordedTransportError('original_identity_reused')
            if len(self._results)>=self._bounds.packet_limit or self._retained_bytes+PACKET_RESERVE_BYTES>self._bounds.result_bytes_limit:
                self._closed=True;raise RecordedTransportError('retention_capacity')
            self._guard();self._original_wire=original
            self._used_ids.update(ids)
            self._active=asyncio.create_task(self._run(prepared))
        self._waiter=True
        try:
            result=await asyncio.shield(self._active)
            self._active=None;self._original_wire=None
            return result
        finally:self._waiter=False

    async def close(self):
        self._bind();self._closed=True
        if self._active is not None:
            try:await asyncio.wait_for(asyncio.shield(self._active),self._bounds.operation_us/1_000_000+self._bounds.cleanup_us/1_000_000)
            except (Exception,asyncio.CancelledError):raise RecordedTransportError('active_packet_incomplete') from None
        if self.cleanup_pending:raise RecordedTransportError('cleanup_incomplete')
        if self._close_task is None:
            async def owned_close():
                token=_LOG_OWNER.set(self._owner)
                try:await self._cleanup(self._transport.aclose)
                finally:_LOG_OWNER.reset(token)
            self._close_task=asyncio.create_task(owned_close())
        try:await asyncio.shield(self._close_task)
        except (Exception,asyncio.CancelledError):raise RecordedTransportError('cleanup_incomplete') from None
        if self.cleanup_pending:raise RecordedTransportError('cleanup_incomplete')
        # Exact object identity: an unrelated custom-equality filter cannot make
        # removeFilter discard another callback. Preserve current others' order.
        for logger in self._loggers:logger.filters[:]=[item for item in logger.filters if item is not self._filter]
