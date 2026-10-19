"""Independent original-body source checks, never native/authentication authority.

No environment, clock reads, UUIDs, provider, storage or database operations.
Expected context, original readback and accepted-age snapshots are supplied
research inputs. Their hashes/shape do not authenticate a real source ledger.
"""
from __future__ import annotations
import base64
from dataclasses import dataclass,field
from datetime import datetime
from decimal import Decimal
from functools import wraps
import hashlib

from . import provider_acquisition_v3 as a
from .source_admission_v3_policy import FIELDS,FORMATS,DEPENDENCIES,AUTHORITY,BOUNDS,POLICY_SHA256
from .provider_evidence import decimal_text
from ..core.decimal_execution import _units,_text,PRICE_SCALE


class SourceAdmissionError(ValueError):
    def __init__(self):super().__init__('Independent source research evidence is invalid or unsupported')


def require(value):
    if not value:raise SourceAdmissionError()


def safe(function):
    @wraps(function)
    def checked(*args,**kwargs):
        try:return function(*args,**kwargs)
        except SourceAdmissionError:raise
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
            raise SourceAdmissionError() from None
    return checked


def fields(value,kind):
    require(type(value) is dict and set(value)==FIELDS[kind]);return value


def count(value,maximum=a.MAX_CLOCK,minimum=0):return a.counter(value,maximum,minimum)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def uuid(value):return a.uuid(value)
def digest(value):return a.digest(value)


def scope(value):
    fields(value,'Scope')
    for item in value.values():uuid(item)
    return value


def policies(value):
    fields(value,'Policies')
    for key,item in value.items():
        digest(item)
        if key in DEPENDENCIES:require(item==DEPENDENCIES[key])
    require(value['acquisition_sha256']==a.POLICY_SHA256)
    return value


def issuer(value):
    fields(value,'Issuer');endpoints=value['endpoint_bindings']
    require(type(endpoints) is list and len(endpoints)==2)
    for entry in endpoints:fields(entry,'EndpointEntry')
    binding=a.IssuerBinding(**{key:item for key,item in value.items() if key!='endpoint_bindings'},
        endpoint_bindings=tuple((entry['provider_family'],entry['endpoint_binding_id']) for entry in endpoints))
    require(set(family for family,_ in binding.endpoint_bindings)=={'jupiter-price-v3','solana-rpc'})
    return binding


def process_clock(value):
    fields(value,'ProcessClock')
    return a.ClockBound(**{key:count(item) if key.endswith('_us') else item for key,item in value.items()})


def guard(value):
    fields(value,'UtcGuard');lo,hi,at=(count(value[key]) for key in ('wall_lower_us','wall_upper_us','observed_at_us'))
    require(lo<=at<=hi and hi-lo<=a.FUTURE_US);return lo,hi,at


@dataclass(frozen=True,slots=True,init=False)
class ResearchEnvelope:
    _wire:bytes=field(repr=False)
    kind:str
    def __init__(self,*args,**kwargs):raise SourceAdmissionError()
    @property
    def wire(self):return self._wire
    @property
    def sha256(self):return sha(self._wire)
    def to_dict(self):return a.read_json(self._wire,BOUNDS['seal_wire_bytes'] if self.kind=='InventorySeal' else BOUNDS['wire_bytes'],exact=True)
    @property
    def native_admission(self):return False
    @property
    def running_authority(self):return False


@safe
def decode(kind,raw):
    require(type(kind) is str and kind in FORMATS and type(raw) is bytes)
    value=a.read_json(raw,BOUNDS['seal_wire_bytes'] if kind=='InventorySeal' else BOUNDS['wire_bytes'],exact=True)
    fields(value,kind);scope(value['scope'])
    require(value['format']==FORMATS[kind] and value['policy_sha256']==POLICY_SHA256)
    fields(value['authority'],'Authority');require(all(item is False for item in value['authority'].values()))
    result=object.__new__(ResearchEnvelope);object.__setattr__(result,'_wire',raw);object.__setattr__(result,'kind',kind)
    _shape(kind,value);return result


@safe
def envelope(kind,value):return decode(kind,a.canonical(value))


def value(envelope,kind):
    require(type(envelope) is ResearchEnvelope and envelope.kind==kind)
    return decode(kind,envelope.wire).to_dict()


def wire(value,kind):
    require(type(value) is str);return decode(kind,value.encode('utf-8'))


def _nullable_digest(item):
    if item is not None:digest(item)


def _pins(rows):
    require(type(rows) is list and len(rows)==3)
    for row in rows:
        fields(row,'RecordPin')
        for key in ('record_id','raw_response_ref','endpoint_binding_id'):uuid(row[key])
        for key in ('capsule_sha256','response_sha256','request_sha256'):digest(row[key])
        require(row['provider_family'] in ('jupiter-price-v3','solana-rpc'))
        for key in ('response_bytes','received_wall_us','received_monotonic_us'):count(row[key])
    require([row['provider_family'] for row in rows]==['jupiter-price-v3','solana-rpc','solana-rpc'])
    for key in ('record_id','raw_response_ref'):require(len({row[key] for row in rows})==3)


def _shape(kind,v):
    # Common scalars are checked on every typed revalidation. Context and seal
    # relation checks remain in their public full validators.
    nullable_hashes={'Submission':{'previous_admission_sha256'},'AdmissionCandidate':{'previous_admission_sha256'},
        'ExpectedContext':{'expected_previous_admission_sha256'},'InventorySeal':{'previous_seal_sha256'}}
    for key,item in v.items():
        if key.endswith('_sha256'):
            if item is not None or key not in nullable_hashes.get(kind,set()):digest(item)
        elif key.endswith('_id') and not key.endswith('_rpc_id'):uuid(item)
    if kind=='Reservation':
        binding=issuer(v['issuer']);policies(v['policies'])
        require({key:getattr(binding,key) for key in FIELDS['Scope']}==v['scope'])
        ids=[v[key] for key in ('reservation_id','admission_id','capture_id','observation_id','price_record_id','genesis_record_id','block_time_record_id')]
        require(len(set(ids))==7 and v['issuer_principal_binding_id'] not in ids)
        configuration=set(v['scope'].values())|{binding.acquisition_epoch,binding.issuer_binding_id,v['issuer_principal_binding_id']}
        configuration.update(endpoint for _,endpoint in binding.endpoint_bindings)
        require(not set(ids)&configuration)
        require(count(v['genesis_rpc_id'],2**31-1,1)!=count(v['block_time_rpc_id'],2**31-1,1))
    elif kind=='Capture':
        require(type(v['capsule_wires']) is list and len(v['capsule_wires'])<=3 and all(type(item) is str for item in v['capsule_wires']))
        require(type(v['diagnostics']) is list and len(v['diagnostics'])<=1)
        require(type(v['collection_completed']) is bool and v['eligibility'] is False)
        require(v['failure_code'] is None or type(v['failure_code']) is str and v['failure_code'] in _FAILURES)
        require((v['failure_code'] is None)==v['collection_completed'])
        require(not v['collection_completed'] or len(v['capsule_wires'])==3 and not v['diagnostics'])
        for row in v['diagnostics']:
            fields(row,'Diagnostic')
            for key in ('record_id','endpoint_binding_id'):uuid(row[key])
            digest(row['request_sha256']);require(row['provider_family'] in ('jupiter-price-v3','solana-rpc'))
            for key in ('request_started_wall_us','request_started_monotonic_us'):count(row[key])
            for key in ('received_wall_us','received_monotonic_us'):
                if row[key] is not None:count(row[key])
            require((row['received_wall_us'] is None)==(row['received_monotonic_us'] is None))
            if row['http_status'] is not None:count(row['http_status'],599,100)
            require(row['body_state'] in ('not_received','partial_discarded','withheld','captured_original') and row['incomplete'] is True
                and row['failure_code'] in _FAILURES)
            if row['body_state']=='not_received':require(row['received_wall_us'] is None)
    elif kind=='ExpectedContext':
        issuer(v['current_issuer']);policies(v['policies']);process_clock(v['process_clock'])
        guard(v['admission_guard']);guard(v['final_guard']);count(v['prior_ingest_sequence'])
        require(v['original_resolution'] in ('fresh_reservation','original_committed','unknown'))
        require((v['original_admission_wire'] is not None)==(v['original_resolution']=='original_committed'))
        if v['original_admission_wire'] is not None:wire(v['original_admission_wire'],'AdmissionCandidate')
        _registry(v)
        for name,shape,limit in (('known_records','KnownRecord','known_records'),('known_operations','KnownOperation','known_operations')):
            require(type(v[name]) is list and len(v[name])<=BOUNDS[limit])
            for row in v[name]:
                fields(row,shape)
                for key,item in row.items():
                    if key.endswith('_id') or key=='raw_response_ref':uuid(item)
                    elif key.endswith('_sha256'):digest(item)
                if shape=='KnownOperation':require(row['operation_kind'] in _OP_KINDS)
        _known(v)
    elif kind=='PriorWitness':
        for key,shape in (('reservation_wire','Reservation'),('capture_wire','Capture'),('submission_wire','Submission'),
                ('admission_candidate_wire','AdmissionCandidate'),('original_readback_wire','OriginalReadback'),('availability_wire','Availability')):
            wire(v[key],shape)
    elif kind=='AdmissionCandidate':
        count(v['expected_prior_ingest_sequence']);process_clock(v['process_clock']);guard(v['admission_guard']);guard(v['final_guard'])
        n=fields(v['normalized'],'Normalized');_pins(n['record_pins'])
        require((n['asset'],n['mint'],n['decimals'],n['denomination'],n['valuation'],n['genesis_hash'],n['source_time_basis'])==
            ('SOL/USD',a.MINT,'9','USD','reference_mark',a.GENESIS,'estimated-block-production-not-provider-publication'))
        require(type(n['price_decimal']) is str and _text(_units(n['price_decimal'],PRICE_SCALE,positive=True),PRICE_SCALE)==n['price_decimal'])
        count(n['block_ref'],2**64-1);count(n['estimated_source_second'],a.MAX_SECOND)
        require(count(n['source_age_floor_us'])<=count(n['source_age_ceiling_us'],a.MAX_SOURCE_AGE_US))
        require(type(n['receipt_age_ceilings_us']) is list and len(n['receipt_age_ceilings_us'])==3)
        for item in n['receipt_age_ceilings_us']:count(item,a.MAX_RECEIPT_AGE_US-1)
    elif kind=='OriginalReadback':
        count(v['supplied_ingest_sequence'],a.MAX_CLOCK,1);count(v['supplied_accepted_at_us']);guard(v['readback_guard']);_pins(v['record_pins'])
    elif kind=='Availability':
        guard(v['readback_guard']);require(count(v['available_at_upper_us'])==count(v['readback_guard']['wall_upper_us']))
    elif kind=='InventorySeal':
        uuid(v['seal_id']);guard(v['seal_guard']);count(v['through_ingest_sequence'],a.MAX_CLOCK,1)
        start,end=(count(v[key],a.MAX_SECOND) for key in ('start_second','end_second'))
        require(start%900==end%900==0 and end-start in (915*60,1800)
            and count(v['seal_guard']['wall_lower_us'])>=end*1_000_000+5_000_000)
        require(v['source_policy_sha256']==DEPENDENCIES['source_sha256'])
        require(type(v['inventory_entries']) is list and 0<len(v['inventory_entries'])<=BOUNDS['inventory_entries'])
        for row in v['inventory_entries']:
            fields(row,'InventoryEntry');uuid(row['operation_id'])
            count(row['inventory_sequence'],a.MAX_CLOCK,1);require(row['operation_kind'] in _OP_KINDS)
            digest(row['original_wire_sha256'])
            if row['outcome']=='seal_boundary':
                require(row['operation_kind']=='seal' and all(row[key] is None for key in
                    ('admission_id','observation_id','reservation_sha256','capture_sha256','admission_sha256','availability_sha256','ingest_sequence')))
                continue
            require(row['operation_kind']!='seal');uuid(row['admission_id']);uuid(row['observation_id']);digest(row['reservation_sha256'])
            for key in ('capture_sha256','admission_sha256','availability_sha256'):_nullable_digest(row[key])
            if row['ingest_sequence'] is not None:count(row['ingest_sequence'],a.MAX_CLOCK,1)
            require(row['outcome'] in ('reserved_pending','capture_only','refused_source','source_candidate'))
            if row['outcome']=='reserved_pending':require(all(row[key] is None for key in ('capture_sha256','admission_sha256','availability_sha256','ingest_sequence')))
            elif row['outcome'] in ('capture_only','refused_source'):
                require(row['capture_sha256'] is not None and all(row[key] is None for key in ('admission_sha256','availability_sha256','ingest_sequence')))
            else:require(all(row[key] is not None for key in ('capture_sha256','admission_sha256','ingest_sequence')))


_FAILURES=frozenset(('acquisition_deadline','invalid_response_metadata','cleanup_incomplete','invalid_response_encoding',
    'invalid_response_length','response_overflow','credential_echo_withheld','invalid_json_for_credential_scan','request_unavailable',
    'invalid_or_unavailable_record','price_http_failure','wrong_network','invalid_or_unavailable_packet',
    'unsupported_logging_runtime','invalid_tls_runtime','unsupported_transport_runtime'))
_OP_KINDS=frozenset(('reservation','capture','admission','availability','seal'))


def _registry(v):
    rows=v['epoch_registry'];require(type(rows) is list and 0<len(rows)<=BOUNDS['epoch_entries'])
    epochs=set();last=None;current=issuer(v['current_issuer'])
    for index,row in enumerate(rows):
        fields(row,'EpochEntry');epoch=uuid(row['acquisition_epoch']);require(epoch not in epochs);epochs.add(epoch)
        require(count(row['ordinal'])==index+1 and row['predecessor_epoch']==last)
        uuid(row['issuer_principal_binding_id']);digest(row['recorder_package_sha256'])
        require(row['status']==('active' if index==len(rows)-1 else 'retired'));last=epoch
    require(last==current.acquisition_epoch and rows[-1]['issuer_principal_binding_id']==v['current_principal_binding_id']
        and rows[-1]['recorder_package_sha256']==v['policies']['recorder_package_sha256'])
    require({key:getattr(current,key) for key in FIELDS['Scope']}==v['scope'])


def _known(v):
    records={};raws={};operations={}
    for row in v['known_records']:
        require(row['record_id'] not in records);records[row['record_id']]=row
        original=(row['response_sha256'],row['reservation_sha256'],row['record_id'],row['capsule_sha256'])
        prior=raws.setdefault(row['raw_response_ref'],original);require(prior==original)
    for row in v['known_operations']:
        require(row['operation_id'] not in operations);operations[row['operation_id']]=row
    require(not set(operations)&(set(records)|set(raws)))
    for row in v['known_records']:
        require(row['raw_response_ref'] not in records or row['raw_response_ref']==row['record_id'])
    return records,raws,operations


def _capsule(raw,binding):
    # Independently verify the outer original envelope, then parse raw provider
    # bodies below. No derive_observation, age-record or normalized header reuse.
    require(type(raw) is str);encoded=raw.encode('utf-8')
    row=a.fields(a.read_json(encoded,a.MAX_CAPSULE_BYTES,exact=True),a._CAPSULE_KEYS)
    require(row['format']==a.FORMAT)
    for key in ('owner_id','run_id','market_epoch','acquisition_epoch','issuer_binding_id','parser_policy_sha256'):
        require(row[key]==getattr(binding,key))
    uuid(row['record_id']);uuid(row['raw_response_ref']);family=row['provider_family']
    require(family in ('jupiter-price-v3','solana-rpc') and row['endpoint_binding_id']==binding.endpoint(family))
    require(type(row['canonical_public_request_wire']) is str)
    request=row['canonical_public_request_wire'].encode();public=a.request_fields(request,family)
    require(row['method']==public['method'] and digest(row['request_sha256'])==sha(request))
    status=count(row['http_status'],599,100);size=count(row['response_bytes'],a.BODY_LIMITS[family])
    require(type(row['response_base64']) is str and len(row['response_base64'])<=((a.BODY_LIMITS[family]+2)//3)*4)
    body=base64.b64decode(row['response_base64'],validate=True)
    require(base64.b64encode(body).decode()==row['response_base64'] and len(body)==size
        and (size>0 or status!=200) and digest(row['response_sha256'])==sha(body))
    times=[count(row[key]) for key in ('request_started_wall_us','received_wall_us','request_started_monotonic_us','received_monotonic_us')]
    require(times[0]<=times[1] and times[2]<=times[3]);a._metadata(row['safe_response_metadata'])
    pin={key:row[key] for key in FIELDS['RecordPin'] if key!='capsule_sha256'};pin['capsule_sha256']=sha(encoded)
    return row,public,body,pin


@safe
def validate_capture(reservation,capture):
    r=value(reservation,'Reservation');c=value(capture,'Capture');binding=issuer(r['issuer'])
    require(c['scope']==r['scope'] and c['reservation_sha256']==reservation.sha256
        and c['capture_id']==r['capture_id'] and c['observation_id']==r['observation_id'])
    ids=[r[key] for key in ('price_record_id','genesis_record_id','block_time_record_id')]
    parsed=[_capsule(raw,binding) for raw in c['capsule_wires']]
    for index,(row,public,_,_) in enumerate(parsed):
        require(row['record_id']==ids[index] and row['provider_family']==('jupiter-price-v3' if index==0 else 'solana-rpc'))
        if index:
            expected=a.public_request('solana-rpc',rpc_method='getGenesisHash' if index==1 else 'getBlockTime',
                rpc_id=count(r['genesis_rpc_id'] if index==1 else r['block_time_rpc_id'],2**31-1,1),
                **({} if index==1 else {'slot':a.read_json(public['body_wire'].encode(),a.MAX_REQUEST_BYTES,numeric=True)['params'][0]}))
            require(row['canonical_public_request_wire'].encode()==expected)
    for row in c['diagnostics']:
        require(row['record_id'] in ids);index=ids.index(row['record_id'])
        require(index<=len(parsed) and row['provider_family']==('jupiter-price-v3' if index==0 else 'solana-rpc')
            and row['endpoint_binding_id']==binding.endpoint(row['provider_family']))
        same=next((item[0] for item in parsed if item[0]['record_id']==row['record_id']),None)
        require((same is not None)==(row['body_state']=='captured_original'))
        if same is not None:
            require(all(row[key]==same[key] for key in ('request_sha256','request_started_wall_us',
                'request_started_monotonic_us','received_wall_us','received_monotonic_us','http_status')))
        elif index==0:require(row['request_sha256']==sha(a.public_request('jupiter-price-v3')))
        elif index==1:require(row['request_sha256']==sha(a.public_request('solana-rpc',rpc_method='getGenesisHash',rpc_id=count(r['genesis_rpc_id']))))
        else:
            _,block=_price(a.read_json(parsed[0][2],a.BODY_LIMITS['jupiter-price-v3'],numeric=True))
            require(row['request_sha256']==sha(a.public_request('solana-rpc',rpc_method='getBlockTime',rpc_id=count(r['block_time_rpc_id']),slot=block)))
        if row['body_state']=='withheld':require(row['received_wall_us'] is not None)
    namespaces={r[key] for key in ('reservation_id','admission_id','capture_id','observation_id')}
    namespaces.update(r['scope'].values());namespaces.update((binding.acquisition_epoch,binding.issuer_binding_id,r['issuer_principal_binding_id']))
    namespaces.update(endpoint for _,endpoint in binding.endpoint_bindings)
    for row,_,_,_ in parsed:
        require(row['raw_response_ref'] not in namespaces and row['raw_response_ref'] not in set(ids)-{row['record_id']})
    require(len({row['raw_response_ref'] for row,_,_,_ in parsed})==len(parsed))
    return capture


def _number(item,positive=False):return decimal_text(item,positive=positive)


def _price(payload):
    info=a.fields(payload,{a.MINT})[a.MINT]
    require(type(info) is dict and {'usdPrice','blockId','decimals'}<=set(info)<=
        {'usdPrice','blockId','decimals','createdAt','liquidity','priceChange24h'})
    price=_number(info['usdPrice'],True);require(_text(_units(price,PRICE_SCALE,positive=True),PRICE_SCALE)==price)
    block=a.integer(info['blockId'],2**64-1);require(type(info['decimals']) is int and info['decimals']==9)
    if 'createdAt' in info:
        stamp=info['createdAt'];require(type(stamp) is str and 0<len(stamp)<=64)
        parsed=datetime.fromisoformat(stamp.replace('Z','+00:00'));require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds()==0)
    if 'liquidity' in info:_number(info['liquidity'])
    if 'priceChange24h' in info:require(info['priceChange24h'] is None or type(info['priceChange24h']) in (int,Decimal))
    return price,block


def _parse_trio(r,c):
    binding=issuer(r['issuer']);rows=[_capsule(raw,binding) for raw in c['capsule_wires']]
    require(c['collection_completed'] and len(rows)==3 and all(row[0]['http_status']=='200' for row in rows))
    payloads=[a.read_json(row[2],a.BODY_LIMITS[row[0]['provider_family']],numeric=True) for row in rows]
    price,block=_price(payloads[0])
    for index,rpc_id,method,params in ((1,count(r['genesis_rpc_id']),'getGenesisHash',[]),
            (2,count(r['block_time_rpc_id']),'getBlockTime',[block])):
        reply=a.fields(payloads[index],{'jsonrpc','id','result'})
        require(reply['jsonrpc']=='2.0' and type(reply['id']) is int and reply['id']==rpc_id)
        request=a.read_json(rows[index][1]['body_wire'].encode(),a.MAX_REQUEST_BYTES,numeric=True)
        require(request['method']==method and request['params']==params)
    require(payloads[1]['result']==a.GENESIS and type(payloads[1]['result']) is str)
    source=a.integer(payloads[2]['result'],a.MAX_SECOND)
    return rows,price,block,source


def _baseline(r,c,clock):
    rows,price,block,source=_parse_trio(r,c);require(clock.acquisition_epoch==r['issuer']['acquisition_epoch'])
    require({key:getattr(clock,key) for key in FIELDS['Scope']}==r['scope'])
    receipts=[];source_floor=source_ceiling=0;source_us=source*1_000_000
    require(source_us<=clock.wall_lower_us+a.FUTURE_US)
    for index,(row,_,_,_) in enumerate(rows):
        sw,rw,sm,rm=(count(row[key]) for key in ('request_started_wall_us','received_wall_us','request_started_monotonic_us','received_monotonic_us'))
        require(rm-sm<a.MAX_RECEIPT_AGE_US and rw-sw<a.MAX_RECEIPT_AGE_US and abs((rw-sw)-(rm-sm))<=a.FUTURE_US
            and clock.monotonic_us>=rm and rw<=clock.wall_lower_us+a.FUTURE_US)
        floor=max(0,clock.wall_lower_us-rw,clock.monotonic_us-rm)
        ceiling=max(floor,clock.wall_upper_us-rw);require(ceiling<a.MAX_RECEIPT_AGE_US);receipts.append(str(ceiling))
        if index==0:
            original=max(0,rw-source_us)
            source_floor=max(0,clock.wall_lower_us-source_us,original+floor)
            source_ceiling=max(source_floor,clock.wall_upper_us-source_us,original+ceiling)
    require(source_ceiling<=a.MAX_SOURCE_AGE_US)
    return {'asset':'SOL/USD','mint':a.MINT,'decimals':'9','denomination':'USD','valuation':'reference_mark',
        'price_decimal':price,'block_ref':str(block),'genesis_hash':a.GENESIS,'estimated_source_second':str(source),
        'source_time_basis':'estimated-block-production-not-provider-publication','source_age_floor_us':str(source_floor),
        'source_age_ceiling_us':str(source_ceiling),'receipt_age_ceilings_us':receipts,'record_pins':[row[3] for row in rows]}


def _final(normalized,clock,admission,final):
    alo,ahi,aat=guard(admission);flo,fhi,fat=guard(final)
    require(alo>=clock.wall_lower_us and flo>=alo and fhi>=ahi and fat>=aat)
    delta=max(0,fhi-clock.wall_lower_us)
    require(all(count(item)+delta<a.MAX_RECEIPT_AGE_US for item in normalized['receipt_age_ceilings_us'])
        and count(normalized['source_age_ceiling_us'])+delta<=a.MAX_SOURCE_AGE_US)
    require(count(normalized['estimated_source_second'])*1_000_000<=alo+a.FUTURE_US)


def _source_order(current,previous):
    block=count(current['block_ref'],2**64-1);old_block=count(previous['block_ref'],2**64-1)
    source=count(current['estimated_source_second']);old_source=count(previous['estimated_source_second'])
    require(block>=old_block and source>=old_source and (block!=old_block or
        source==old_source and current['price_decimal']==previous['price_decimal']))


def _native_guard_order(admission,final,prior_admission,prior_final,prior_accepted):
    current=guard(admission);previous=guard(prior_admission)
    require(current[2]>=prior_accepted and all(now>=old for now,old in zip(current,previous)))
    require(all(now>=old for now,old in zip(guard(final),guard(prior_final))))


def _candidate_baseline(candidate,reservation,capture,submission):
    n=value(candidate,'AdmissionCandidate');r=value(reservation,'Reservation');c=value(capture,'Capture');s=value(submission,'Submission')
    validate_capture(reservation,capture)
    require(n['scope']==r['scope']==c['scope']==s['scope'] and n['admission_id']==r['admission_id']==s['admission_id']
        and n['observation_id']==r['observation_id']==s['observation_id']
        and n['reservation_sha256']==s['reservation_sha256']==reservation.sha256
        and n['capture_sha256']==s['capture_sha256']==capture.sha256 and n['submission_sha256']==submission.sha256
        and n['previous_admission_sha256']==s['previous_admission_sha256'])
    clock=process_clock(n['process_clock']);baseline=_baseline(r,c,clock)
    for key,item in baseline.items():
        if key not in ('source_age_floor_us','source_age_ceiling_us'):require(n['normalized'][key]==item)
    require(count(n['normalized']['source_age_floor_us'])>=count(baseline['source_age_floor_us'])
        and count(n['normalized']['source_age_ceiling_us'])>=count(baseline['source_age_ceiling_us']))
    _final(n['normalized'],clock,n['admission_guard'],n['final_guard']);return n


@safe
def validate_readback(candidate,reservation,capture,submission,readback,availability):
    n=_candidate_baseline(candidate,reservation,capture,submission);rb=value(readback,'OriginalReadback');av=value(availability,'Availability')
    require(rb['scope']==av['scope']==n['scope'] and rb['admission_id']==av['admission_id']==n['admission_id']
        and rb['observation_id']==n['observation_id'] and rb['original_admission_sha256']==av['original_admission_sha256']==candidate.sha256
        and rb['original_reservation_sha256']==reservation.sha256 and rb['original_capture_sha256']==capture.sha256
        and rb['original_submission_sha256']==submission.sha256 and av['original_readback_sha256']==readback.sha256
        and av['readback_guard']==rb['readback_guard'] and rb['record_pins']==n['normalized']['record_pins'])
    require(rb['native_package_sha256']==value(reservation,'Reservation')['policies']['native_package_sha256'])
    require(count(rb['supplied_ingest_sequence'])>count(n['expected_prior_ingest_sequence']))
    lo,hi,_=guard(rb['readback_guard']);accepted=count(rb['supplied_accepted_at_us'])
    require(accepted==count(n['admission_guard']['observed_at_us']) and lo>=count(n['final_guard']['wall_upper_us'])
        and accepted<=lo and hi==count(av['available_at_upper_us']))
    return readback,availability


def _prior(witness,expected):
    p=value(witness,'PriorWitness');objects=[wire(p[key],kind) for key,kind in (
        ('reservation_wire','Reservation'),('capture_wire','Capture'),('submission_wire','Submission'),
        ('admission_candidate_wire','AdmissionCandidate'),('original_readback_wire','OriginalReadback'),('availability_wire','Availability'))]
    r,c,s,n,rb,av=objects;require(n.sha256==digest(expected))
    validate_readback(n,r,c,s,rb,av);v=value(n,'AdmissionCandidate');require(v['scope']==p['scope']);return v,objects


@safe
def validate_submission(reservation,capture,submission,context,*,prior=None):
    r=value(reservation,'Reservation');c=value(capture,'Capture');s=value(submission,'Submission');ctx=value(context,'ExpectedContext')
    validate_capture(reservation,capture)
    require(r['scope']==s['scope']==ctx['scope'] and s['admission_id']==r['admission_id'] and s['observation_id']==r['observation_id']
        and s['reservation_sha256']==ctx['expected_reservation_sha256']==reservation.sha256
        and s['capture_sha256']==ctx['expected_capture_sha256']==capture.sha256 and r['policies']==ctx['policies'])
    require(ctx['original_resolution']!='unknown')
    if ctx['original_resolution']=='original_committed':
        original=wire(ctx['original_admission_wire'],'AdmissionCandidate')
        _candidate_baseline(original,reservation,capture,submission)
        # The immutable original's own guards/snapshot are checked, never the
        # caller's newly supplied stale clock. This returns that same research
        # original, not current eligibility, sequence or authentication.
        return original
    require(r['issuer']==ctx['current_issuer'] and r['issuer_principal_binding_id']==ctx['current_principal_binding_id']
        and s['previous_admission_sha256']==ctx['expected_previous_admission_sha256'])
    records,raws,operations=_known(ctx)
    fresh={r[key] for key in ('reservation_id','admission_id','capture_id','observation_id','price_record_id','genesis_record_id','block_time_record_id')}
    own_operations={r['reservation_id']:('reservation',reservation.sha256),r['capture_id']:('capture',capture.sha256)}
    for identity in fresh&set(operations):
        require(identity in own_operations and (operations[identity]['operation_kind'],operations[identity]['original_wire_sha256'])==own_operations[identity])
    for identity in fresh&(set(records)|set(raws)):
        require(identity in {r[key] for key in ('price_record_id','genesis_record_id','block_time_record_id')})
    clock=process_clock(ctx['process_clock']);normalized=_baseline(r,c,clock)
    for pin in normalized['record_pins']:
        require(pin['record_id'] not in raws or pin['raw_response_ref']==pin['record_id'])
        require(pin['raw_response_ref'] not in records or pin['raw_response_ref']==pin['record_id'])
        require(pin['raw_response_ref'] not in operations and (pin['raw_response_ref'] not in raws or
            raws[pin['raw_response_ref']]==(pin['response_sha256'],reservation.sha256,pin['record_id'],pin['capsule_sha256'])))
        if pin['record_id'] in records:
            known=records[pin['record_id']]
            require(all(known[key]==pin[key] for key in ('record_id','capsule_sha256','raw_response_ref','response_sha256'))
                and known['reservation_sha256']==reservation.sha256)
    if prior is None:require(s['previous_admission_sha256'] is None and count(ctx['prior_ingest_sequence'])==0)
    else:
        old,objects=_prior(prior,s['previous_admission_sha256']);oldn=old['normalized'];old_clock=process_clock(old['process_clock'])
        require(old['scope']==r['scope'] and count(ctx['prior_ingest_sequence'])==count(value(objects[4],'OriginalReadback')['supplied_ingest_sequence']))
        oldr=value(objects[0],'Reservation');require(oldr['policies']==r['policies'])
        historical=next((row for row in ctx['epoch_registry'] if row['acquisition_epoch']==old_clock.acquisition_epoch),None)
        require(historical is not None and historical['issuer_principal_binding_id']==oldr['issuer_principal_binding_id']
            and historical['recorder_package_sha256']==oldr['policies']['recorder_package_sha256'])
        _source_order(normalized,oldn)
        _native_guard_order(ctx['admission_guard'],ctx['final_guard'],old['admission_guard'],old['final_guard'],
            count(value(objects[4],'OriginalReadback')['supplied_accepted_at_us']))
        if clock.acquisition_epoch==old_clock.acquisition_epoch:
            require(clock.wall_lower_us>=old_clock.wall_lower_us and clock.monotonic_us>=old_clock.monotonic_us)
            elapsed_lo=elapsed_hi=clock.monotonic_us-old_clock.monotonic_us
        else:
            require(clock.wall_lower_us>=old_clock.wall_upper_us)
            elapsed_lo=clock.wall_lower_us-old_clock.wall_upper_us;elapsed_hi=clock.wall_upper_us-old_clock.wall_lower_us
        shift=(count(normalized['estimated_source_second'])-count(oldn['estimated_source_second']))*1_000_000
        floor=max(count(normalized['source_age_floor_us']),count(oldn['source_age_floor_us'])+elapsed_lo-shift,0)
        ceil=max(count(normalized['source_age_ceiling_us']),count(oldn['source_age_ceiling_us'])+elapsed_hi-shift,floor)
        require(ceil<=a.MAX_SOURCE_AGE_US);normalized.update(source_age_floor_us=str(floor),source_age_ceiling_us=str(ceil))
        oldpins=oldn['record_pins'];oldids={old['admission_id'],old['observation_id'],oldr['reservation_id'],oldr['capture_id']}
        oldids.update(pin['record_id'] for pin in oldpins);oldids.update(pin['raw_response_ref'] for pin in oldpins)
        require(not fresh&oldids)
        for pin in normalized['record_pins']:
            for previous in oldpins:
                if pin['raw_response_ref']==previous['raw_response_ref']:require(pin['response_sha256']==previous['response_sha256'])
    _final(normalized,clock,ctx['admission_guard'],ctx['final_guard'])
    result={'format':FORMATS['AdmissionCandidate'],'policy_sha256':POLICY_SHA256,'scope':r['scope'],
        'admission_id':r['admission_id'],'observation_id':r['observation_id'],'reservation_sha256':reservation.sha256,
        'capture_sha256':capture.sha256,'submission_sha256':submission.sha256,'previous_admission_sha256':s['previous_admission_sha256'],
        'expected_prior_ingest_sequence':ctx['prior_ingest_sequence'],'process_clock':ctx['process_clock'],
        'admission_guard':ctx['admission_guard'],'final_guard':ctx['final_guard'],'normalized':normalized,'authority':dict(AUTHORITY)}
    return envelope('AdmissionCandidate',result)


@safe
def validate_seal(seal,original_operations,*,previous=None,expected_previous_sha256=None):
    v=value(seal,'InventorySeal');require(type(original_operations) is tuple and len(original_operations)<=BOUNDS['original_dependencies'])
    lookup={}
    for item in original_operations:
        require(type(item) is ResearchEnvelope);checked=decode(item.kind,item.wire);body=checked.to_dict()
        require(body['scope']==v['scope'])
        id_key={'Reservation':'reservation_id','Capture':'capture_id','Submission':'admission_id','AdmissionCandidate':'admission_id',
            'OriginalReadback':'admission_id','Availability':'availability_id','InventorySeal':'seal_id'}
        require(item.kind in id_key)
        identity=body[id_key[item.kind]]
        # Submission/readback are returned original dependencies, not extra
        # independently allocated write commands with the admission UUID.
        key=(item.kind,identity)
        require(key not in lookup);lookup[key]=checked
    by_hash={(item.kind,item.sha256):item for item in lookup.values()}
    # Check aliases throughout this supplied witness, not just inside one
    # reservation. This is not a complete/authenticated native UUID registry.
    configuration=set(v['scope'].values());identities={};records={}
    for item in lookup.values():
        if item.kind!='Reservation':continue
        body=item.to_dict();binding=issuer(body['issuer'])
        require(body['policies']['recorder_package_sha256']==v['recorder_package_sha256'])
        configuration.update((binding.acquisition_epoch,binding.issuer_binding_id,body['issuer_principal_binding_id']))
        configuration.update(endpoint for _,endpoint in binding.endpoint_bindings)
        for role in ('reservation_id','admission_id','capture_id','observation_id','price_record_id','genesis_record_id','block_time_record_id'):
            identity=body[role];require(identity not in identities);identities[identity]=(role,item.sha256)
            if role.endswith('_record_id'):records[identity]=item.sha256
    raws={}
    for item in lookup.values():
        body=item.to_dict()
        if item.kind=='Capture':
            retained=by_hash.get(('Reservation',body['reservation_sha256']));require(retained is not None)
            require(identities.get(body['capture_id'])==('capture_id',retained.sha256))
            for raw in body['capsule_wires']:
                capsule=a.fields(a.read_json(raw.encode(),a.MAX_CAPSULE_BYTES,exact=True),a._CAPSULE_KEYS)
                record,reference=uuid(capsule['record_id']),uuid(capsule['raw_response_ref'])
                require(records.get(record)==retained.sha256 and (reference not in identities or reference==record))
                association=(record,retained.sha256,sha(raw.encode()))
                require(reference not in raws);raws[reference]=association
        elif item.kind=='Availability':
            identity=body['availability_id'];require(identity not in identities and identity not in raws)
            identities[identity]=('availability_id',item.sha256)
        elif item.kind in ('Submission','OriginalReadback'):
            candidate=lookup.get(('AdmissionCandidate',body['admission_id']));require(candidate is not None)
            original=candidate.to_dict()
            if item.kind=='Submission':
                require(item.sha256==original['submission_sha256'] and body['observation_id']==original['observation_id']
                    and body['reservation_sha256']==original['reservation_sha256'] and body['capture_sha256']==original['capture_sha256'])
            else:
                require(body['original_admission_sha256']==candidate.sha256 and body['observation_id']==original['observation_id']
                    and body['original_reservation_sha256']==original['reservation_sha256']
                    and body['original_capture_sha256']==original['capture_sha256']
                    and body['original_submission_sha256']==original['submission_sha256'])
                retained=by_hash.get(('Reservation',original['reservation_sha256']));require(retained is not None)
                lo,_,_=guard(body['readback_guard']);accepted=count(body['supplied_accepted_at_us'])
                require(body['native_package_sha256']==retained.to_dict()['policies']['native_package_sha256']
                    and body['record_pins']==original['normalized']['record_pins']
                    and accepted==count(original['admission_guard']['observed_at_us'])
                    and lo>=count(original['final_guard']['wall_upper_us']) and accepted<=lo
                    and count(body['supplied_ingest_sequence'])>count(original['expected_prior_ingest_sequence']))
    require(not configuration&(set(identities)|set(raws)))
    for reference,(record,_,_) in raws.items():require(reference not in identities or reference==record)
    for identity in [v['seal_id']]+[identity for kind,identity in lookup if kind=='InventorySeal']:
        require(identity not in identities and identity not in raws and identity not in configuration)
    rows=v['inventory_entries'];first=1
    if previous is None:require(v['previous_seal_sha256'] is None and expected_previous_sha256 is None)
    else:
        old=value(previous,'InventorySeal');require(previous.sha256==digest(expected_previous_sha256)==v['previous_seal_sha256']
            and old['scope']==v['scope'] and old['recorder_package_sha256']==v['recorder_package_sha256']
            and count(v['end_second'])==count(old['end_second'])+900
            and count(v['start_second'])==count(old['end_second'])-900)
        first=count(old['through_ingest_sequence'])+1
    require(count(v['end_second'])-count(v['start_second'])==(915*60 if previous is None else 1800))
    require([count(row['inventory_sequence']) for row in rows]==list(range(first,count(v['through_ingest_sequence'])+1)))
    require(len({row['operation_id'] for row in rows})==len(rows))
    require(sha(a.canonical(rows))==v['complete_inventory_sha256'])
    # A1 checks full supplied operation positioning and immutable links. Native
    # inventory completeness and eligible SourceMark conversion remain separate.
    selected={};eligible=[];seen_admissions=set();checked_captures=set();checked_candidates=set();ordered_candidates={}
    all_rows=rows if previous is None else old['inventory_entries']+rows
    require(len({row['operation_id'] for row in all_rows})==len(all_rows))
    write_kind={'reservation':'Reservation','capture':'Capture','admission':'AdmissionCandidate','availability':'Availability','seal':'InventorySeal'}
    inventoried={(write_kind[row['operation_kind']],row['operation_id']) for row in all_rows}
    supplied={(kind,identity) for kind,identity in lookup if kind in set(write_kind.values())}
    require(supplied==inventoried)
    source_positions={row['operation_id']:row['inventory_sequence'] for row in all_rows if row['operation_kind']=='admission'}
    for (kind,identity),item in lookup.items():
        if kind=='OriginalReadback':require(source_positions.get(identity)==item.to_dict()['supplied_ingest_sequence'])
    for row in all_rows:
        kind=write_kind[row['operation_kind']]
        original=lookup.get((kind,row['operation_id']));require(original is not None and original.sha256==row['original_wire_sha256'])
        body=original.to_dict();require(body['scope']==v['scope'])
        require(row['operation_id']!=v['seal_id'])
        if row['outcome']=='seal_boundary':
            expected_boundary=previous.sha256 if row in rows else old['previous_seal_sha256']
            require(previous is not None and original.sha256==expected_boundary and row['operation_id']==body['seal_id']
                and body['recorder_package_sha256']==v['recorder_package_sha256']
                and count(body['end_second'])<=count(old['end_second'])
                and count(row['inventory_sequence'])==count(body['through_ingest_sequence'])+1)
            continue
        if kind=='Reservation':require(body['admission_id']==row['admission_id'] and body['observation_id']==row['observation_id'] and original.sha256==row['reservation_sha256'])
        if kind=='Capture':require(body['observation_id']==row['observation_id'] and body['reservation_sha256']==row['reservation_sha256'] and original.sha256==row['capture_sha256'])
        if kind=='AdmissionCandidate':require(body['admission_id']==row['admission_id'] and body['observation_id']==row['observation_id']
            and body['reservation_sha256']==row['reservation_sha256'] and body['capture_sha256']==row['capture_sha256'])
        if kind=='Availability':require(body['admission_id']==row['admission_id'] and body['original_admission_sha256']==row['admission_sha256']
            and original.sha256==row['availability_sha256'])
        if row['capture_sha256'] is not None:
            retained_r=by_hash.get(('Reservation',row['reservation_sha256']))
            retained_c=by_hash.get(('Capture',row['capture_sha256']))
            require(retained_r is not None and retained_c is not None)
            capture_key=(retained_r.wire,retained_c.wire)
            if capture_key not in checked_captures:
                validate_capture(retained_r,retained_c);checked_captures.add(capture_key)
            require(retained_r.to_dict()['admission_id']==row['admission_id'] and retained_r.to_dict()['observation_id']==row['observation_id'])
        if row['operation_kind']=='admission':require(row['ingest_sequence']==row['inventory_sequence'] and row['admission_sha256']==original.sha256)
        if row['outcome']=='source_candidate':
            candidate=lookup.get(('AdmissionCandidate',row['admission_id']));require(candidate is not None and candidate.sha256==row['admission_sha256'])
            r=by_hash.get(('Reservation',row['reservation_sha256']))
            c=by_hash.get(('Capture',row['capture_sha256']))
            s=lookup.get(('Submission',row['admission_id']));rb=lookup.get(('OriginalReadback',row['admission_id']))
            av=by_hash.get(('Availability',row['availability_sha256']))
            require(all(item is not None for item in (r,c,s)))
            require(source_positions.get(row['admission_id'])==row['ingest_sequence'])
            require(value(r,'Reservation')['policies']['recorder_package_sha256']==v['recorder_package_sha256'])
            require(row['observation_id']==candidate.to_dict()['observation_id'])
            candidate_key=(candidate.wire,r.wire,c.wire,s.wire)
            if candidate_key not in checked_candidates:
                _candidate_baseline(candidate,r,c,s);checked_candidates.add(candidate_key)
            ordered_candidates[row['admission_id']]=(count(row['ingest_sequence']),candidate.to_dict())
            if row['availability_sha256'] is None:continue
            require(rb is not None and av is not None)
            require(row['ingest_sequence']==rb.to_dict()['supplied_ingest_sequence'])
            if row['admission_id'] in seen_admissions:continue
            validate_readback(candidate,r,c,s,rb,av)
            seen_admissions.add(row['admission_id'])
            cand=candidate.to_dict();normalized=cand['normalized'];clock=process_clock(cand['process_clock'])
            accepted=count(rb.to_dict()['supplied_accepted_at_us']);available=count(av.to_dict()['available_at_upper_us'])
            minute=accepted//60_000_000;start=count(v['start_second'])*1_000_000;end=count(v['end_second'])*1_000_000
            if not start<=accepted<end or available>(minute+1)*60_000_000:continue
            delta=max(0,available-clock.wall_lower_us)
            if available<clock.wall_upper_us or any(count(age)+delta>=a.MAX_RECEIPT_AGE_US for age in normalized['receipt_age_ceilings_us']):continue
            if any(count(pin['received_wall_us'])>accepted+a.FUTURE_US or available-count(pin['received_wall_us'])>=a.MAX_RECEIPT_AGE_US for pin in normalized['record_pins']):continue
            if count(normalized['source_age_ceiling_us'])+max(0,accepted-clock.wall_lower_us)>a.MAX_SOURCE_AGE_US:continue
            pin={'admission_id':row['admission_id'],'admission_sha256':candidate.sha256,
                'original_readback_sha256':rb.sha256,'availability_sha256':av.sha256,'ingest_sequence':row['ingest_sequence'],
                'accepted_at_us':str(accepted),'available_at_upper_us':str(available),'price_decimal':normalized['price_decimal']}
            eligible.append(pin);winner=selected.get(minute)
            if winner is None or (accepted,count(row['ingest_sequence']))>(count(winner['accepted_at_us']),count(winner['ingest_sequence'])):selected[minute]=pin
    prior_candidate=None
    for _,current in sorted(ordered_candidates.values(),key=lambda item:item[0]):
        if prior_candidate is not None:
            _source_order(current['normalized'],prior_candidate['normalized'])
            _native_guard_order(current['admission_guard'],current['final_guard'],prior_candidate['admission_guard'],
                prior_candidate['final_guard'],count(prior_candidate['admission_guard']['observed_at_us']))
        prior_candidate=current
    eligible.sort(key=lambda pin:count(pin['ingest_sequence']))
    require(sha(a.canonical(eligible))==v['eligible_records_sha256'])
    require(set(selected)==set(range(count(v['start_second'])//60,count(v['end_second'])//60)))
    return seal
