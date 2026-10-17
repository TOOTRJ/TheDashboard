"""Literal offline source facts; no native/authenticated/provider acquisition."""
import ast
import base64
from copy import deepcopy
import hashlib
from pathlib import Path
import unittest
from uuid import UUID

from tests.security_support import deny_network
with deny_network():
    from vonneumann.market import provider_acquisition_v3 as a,source_admission_v3 as v
    from vonneumann.market.source_admission_v3_policy import FORMATS,AUTHORITY,DEPENDENCIES,POLICY_SHA256,POLICY_WIRE,BOUNDS

BASE=1_800_000_000
def uid(number):return str(UUID(int=number))
SCOPE={'owner_id':uid(11),'run_id':uid(12),'market_epoch':uid(13)}


def emit(kind,**data):return v.envelope(kind,{'format':FORMATS[kind],'policy_sha256':POLICY_SHA256,
    'scope':dict(SCOPE),**data,'authority':dict(AUTHORITY)})


def alter(item,change):
    data=item.to_dict();change(data);return v.envelope(item.kind,data)


def utc(at,hi=None):return {'wall_lower_us':str(at),'wall_upper_us':str(at if hi is None else hi),'observed_at_us':str(at)}


def fixture(index=0,*,second=BASE,epoch=20,mono=10_000_000,source_second=None,previous=None,sequence=3,block=42):
    clock_us=second*1_000_000+200_000
    bind=a.IssuerBinding(**SCOPE,acquisition_epoch=uid(epoch),issuer_binding_id=uid(21),
        endpoint_bindings=(('jupiter-price-v3',uid(23)),('solana-rpc',uid(24))))
    isr={key:getattr(bind,key) for key in ('owner_id','run_id','market_epoch','acquisition_epoch','issuer_binding_id','parser_policy_sha256')}
    isr['endpoint_bindings']=[{'provider_family':kind,'endpoint_binding_id':identity} for kind,identity in bind.endpoint_bindings]
    ids=[uid(1000+index*10+offset) for offset in range(1,8)]
    policy={**dict(DEPENDENCIES),'recorder_package_sha256':'a'*64,'native_package_sha256':'b'*64}
    r=emit('Reservation',**dict(zip(('reservation_id','admission_id','capture_id','observation_id','price_record_id','genesis_record_id','block_time_record_id'),ids)),
        genesis_rpc_id='1',block_time_rpc_id='2',issuer=isr,issuer_principal_binding_id=uid(22),policies=policy)
    rdata=r.to_dict();source_second=second-2 if source_second is None else source_second
    requests=[a.public_request('jupiter-price-v3'),a.public_request('solana-rpc',rpc_method='getGenesisHash',rpc_id=1),
        a.public_request('solana-rpc',rpc_method='getBlockTime',rpc_id=2,slot=block)]
    bodies=[('{"'+a.MINT+'":{"usdPrice":100.123456789012345678,"blockId":'+str(block)+',"decimals":9,"priceChange24h":null}}').encode(),
        a.canonical({'jsonrpc':'2.0','id':1,'result':a.GENESIS}),a.canonical({'jsonrpc':'2.0','id':2,'result':source_second})]
    capsules=[a.capture_capsule(bind,record_id=record,provider_family=family,request=request,raw_body=body,http_status=200,
        started_wall_us=clock_us-200000,received_wall_us=clock_us-100000,started_monotonic_us=mono-200000,
        received_monotonic_us=mono-100000) for record,family,request,body in zip(ids[4:],('jupiter-price-v3','solana-rpc','solana-rpc'),requests,bodies)]
    c=emit('Capture',reservation_sha256=r.sha256,capture_id=rdata['capture_id'],observation_id=rdata['observation_id'],
        capsule_wires=[item.wire.decode() for item in capsules],diagnostics=[],collection_completed=True,failure_code=None,eligibility=False)
    previous_hash=None if previous is None else previous['candidate'].sha256
    s=emit('Submission',admission_id=rdata['admission_id'],observation_id=rdata['observation_id'],reservation_sha256=r.sha256,
        capture_sha256=c.sha256,previous_admission_sha256=previous_hash)
    clock={**SCOPE,'acquisition_epoch':uid(epoch),'wall_lower_us':str(clock_us),'wall_upper_us':str(clock_us),'monotonic_us':str(mono)}
    registry=[{'acquisition_epoch':uid(20),'predecessor_epoch':None,'ordinal':'1','issuer_principal_binding_id':uid(22),
        'recorder_package_sha256':'a'*64,'status':'active' if epoch==20 else 'retired'}]
    if epoch!=20:registry.append({'acquisition_epoch':uid(epoch),'predecessor_epoch':uid(20),'ordinal':'2',
        'issuer_principal_binding_id':uid(22),'recorder_package_sha256':'a'*64,'status':'active'})
    ctx=emit('ExpectedContext',current_issuer=isr,current_principal_binding_id=uid(22),policies=policy,epoch_registry=registry,
        expected_reservation_sha256=r.sha256,expected_capture_sha256=c.sha256,expected_previous_admission_sha256=previous_hash,
        prior_ingest_sequence='0' if previous is None else previous['rb'].to_dict()['supplied_ingest_sequence'],
        known_records=[],known_operations=[],original_resolution='fresh_reservation',original_admission_wire=None,
        process_clock=clock,admission_guard=utc(clock_us+100000),final_guard=utc(clock_us+200000))
    prior=None if previous is None else previous['prior']
    candidate=v.validate_submission(r,c,s,ctx,prior=prior)
    rb=emit('OriginalReadback',admission_id=rdata['admission_id'],original_admission_sha256=candidate.sha256,
        original_reservation_sha256=r.sha256,original_capture_sha256=c.sha256,original_submission_sha256=s.sha256,
        observation_id=rdata['observation_id'],native_receipt_sha256='c'*64,native_package_sha256='b'*64,
        supplied_ingest_sequence=str(sequence),supplied_accepted_at_us=str(clock_us+100000),
        readback_guard=utc(clock_us+300000,clock_us+400000),record_pins=candidate.to_dict()['normalized']['record_pins'])
    av=emit('Availability',availability_id=uid(1000+index*10+8),admission_id=rdata['admission_id'],
        original_readback_sha256=rb.sha256,original_admission_sha256=candidate.sha256,readback_guard=rb.to_dict()['readback_guard'],
        available_at_upper_us=str(clock_us+400000))
    prior_witness=emit('PriorWitness',reservation_wire=r.wire.decode(),capture_wire=c.wire.decode(),submission_wire=s.wire.decode(),
        admission_candidate_wire=candidate.wire.decode(),original_readback_wire=rb.wire.decode(),availability_wire=av.wire.decode())
    return dict(r=r,c=c,s=s,ctx=ctx,candidate=candidate,rb=rb,av=av,prior=prior_witness,capsules=capsules)


def forged_capture(bundle,index,body):
    cdata=bundle['c'].to_dict();row=a.read_json(cdata['capsule_wires'][index].encode(),a.MAX_CAPSULE_BYTES,exact=True)
    row.update(response_base64=base64.b64encode(body).decode(),response_sha256=v.sha(body),response_bytes=str(len(body)))
    cdata['capsule_wires'][index]=a.canonical(row).decode();c=v.envelope('Capture',cdata)
    s=alter(bundle['s'],lambda data:data.update(capture_sha256=c.sha256))
    ctx=alter(bundle['ctx'],lambda data:data.update(expected_capture_sha256=c.sha256))
    return c,s,ctx


def journal(bundles,start_sequence=1):
    rows=[]
    for f in bundles:
        r=f['r'].to_dict();ingest=f['rb'].to_dict()['supplied_ingest_sequence']
        for key,kind,id_key in (('r','reservation','reservation_id'),('c','capture','capture_id'),
                ('candidate','admission','admission_id'),('av','availability','availability_id')):
            item=f[key];body=item.to_dict()
            rows.append({'inventory_sequence':str(start_sequence+len(rows)),'operation_id':body[id_key],
                'operation_kind':kind,'original_wire_sha256':item.sha256,'admission_id':r['admission_id'],
                'observation_id':r['observation_id'],'reservation_sha256':f['r'].sha256,'capture_sha256':f['c'].sha256,
                'admission_sha256':f['candidate'].sha256,'availability_sha256':f['av'].sha256,
                'ingest_sequence':ingest,'outcome':'source_candidate'})
    return rows


def eligible_pins(bundles):
    return [{'admission_id':f['r'].to_dict()['admission_id'],'admission_sha256':f['candidate'].sha256,
        'original_readback_sha256':f['rb'].sha256,'availability_sha256':f['av'].sha256,
        'ingest_sequence':f['rb'].to_dict()['supplied_ingest_sequence'],
        'accepted_at_us':f['rb'].to_dict()['supplied_accepted_at_us'],
        'available_at_upper_us':f['av'].to_dict()['available_at_upper_us'],
        'price_decimal':f['candidate'].to_dict()['normalized']['price_decimal']} for f in bundles]


def make_seal(rows,bundles,*,start=BASE,end=BASE+915*60,previous=None,identity=90000):
    return emit('InventorySeal',seal_id=uid(identity),start_second=str(start),end_second=str(end),
        seal_guard=utc(end*1000000+5000000),through_ingest_sequence=rows[-1]['inventory_sequence'],
        previous_seal_sha256=None if previous is None else previous.sha256,inventory_entries=rows,
        complete_inventory_sha256=v.sha(a.canonical(rows)),eligible_records_sha256=v.sha(a.canonical(eligible_pins(bundles))),
        recorder_package_sha256='a'*64,source_policy_sha256=DEPENDENCIES['source_sha256'])


def originals(bundles):return tuple(f[key] for f in bundles for key in ('r','c','s','candidate','rb','av'))


def excluded_entries(reservation,capture,start_sequence):
    r=reservation.to_dict()
    return [{'inventory_sequence':str(start_sequence+offset),'operation_id':item.to_dict()[id_key],
        'operation_kind':kind,'original_wire_sha256':item.sha256,'admission_id':r['admission_id'],
        'observation_id':r['observation_id'],'reservation_sha256':reservation.sha256,'capture_sha256':capture.sha256,
        'admission_sha256':None,'availability_sha256':None,'ingest_sequence':None,'outcome':'capture_only'}
        for offset,(item,kind,id_key) in enumerate(((reservation,'reservation','reservation_id'),(capture,'capture','capture_id')))]


def self_rehashed_seal_original(bundle,previous,*,price=None,admission_us=None):
    result=dict(bundle);r=bundle['r'].to_dict()
    if price is not None:
        block=bundle['candidate'].to_dict()['normalized']['block_ref']
        body=('{"'+a.MINT+'":{"usdPrice":'+price+',"blockId":'+block+',"decimals":9,"priceChange24h":null}}').encode()
        result['c'],result['s'],_=forged_capture(bundle,0,body)
    result['s']=alter(result['s'],lambda data:data.update(previous_admission_sha256=previous['candidate'].sha256))
    data=result['candidate'].to_dict();data.update(capture_sha256=result['c'].sha256,submission_sha256=result['s'].sha256,
        previous_admission_sha256=previous['candidate'].sha256,
        expected_prior_ingest_sequence=previous['rb'].to_dict()['supplied_ingest_sequence'])
    if price is not None:
        capsule=a.read_json(result['c'].to_dict()['capsule_wires'][0].encode(),a.MAX_CAPSULE_BYTES,exact=True)
        data['normalized']['price_decimal']=price
        data['normalized']['record_pins'][0].update(capsule_sha256=v.sha(result['c'].to_dict()['capsule_wires'][0].encode()),
            response_sha256=capsule['response_sha256'],response_bytes=capsule['response_bytes'])
    if admission_us is not None:data['admission_guard']=utc(admission_us)
    result['candidate']=v.envelope('AdmissionCandidate',data)
    result['rb']=alter(result['rb'],lambda rb:rb.update(original_admission_sha256=result['candidate'].sha256,
        original_capture_sha256=result['c'].sha256,original_submission_sha256=result['s'].sha256,
        supplied_accepted_at_us=data['admission_guard']['observed_at_us'],record_pins=data['normalized']['record_pins']))
    result['av']=alter(result['av'],lambda av:av.update(original_admission_sha256=result['candidate'].sha256,
        original_readback_sha256=result['rb'].sha256))
    return result


class SourceAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.network=deny_network();self.network.__enter__();self.addCleanup(self.network.__exit__,None,None,None)

    def test_independent_original_trio_exact_decimal_policy_and_no_authority(self):
        f=fixture();n=f['candidate'].to_dict()['normalized']
        self.assertEqual(n['price_decimal'],'100.123456789012345678');self.assertEqual(n['block_ref'],'42')
        self.assertEqual(n['source_age_ceiling_us'],'2200000')
        self.assertFalse(f['candidate'].native_admission);self.assertFalse(f['candidate'].running_authority)
        self.assertTrue(all(item is False for item in f['candidate'].to_dict()['authority'].values()))
        self.assertEqual(POLICY_SHA256,hashlib.sha256(POLICY_WIRE).hexdigest())

    def test_required_hashes_never_accept_null_as_an_unchecked_reference(self):
        f=fixture()
        for item,key in ((f['rb'],'native_receipt_sha256'),(f['ctx'],'expected_capture_sha256'),
                (f['s'],'reservation_sha256'),(f['candidate'],'submission_sha256'),(f['av'],'original_readback_sha256')):
            with self.assertRaises(v.SourceAdmissionError):alter(item,lambda data:data.update({key:None}))

    def test_new_rehashed_wrong_mint_decimal_boolean_block_null_network_slot_or_rpc_id_refuse(self):
        f=fixture()
        cases=[(0,b'{"wrong":{"usdPrice":100,"blockId":42,"decimals":9}}'),
            (0,('{"'+a.MINT+'":{"usdPrice":true,"blockId":42,"decimals":9}}').encode()),
            (0,('{"'+a.MINT+'":{"usdPrice":100,"blockId":null,"decimals":9}}').encode()),
            (0,('{"'+a.MINT+'":{"usdPrice":100,"blockId":43,"decimals":9}}').encode()),
            (0,('{"'+a.MINT+'":{"usdPrice":100,"blockId":42,"decimals":true}}').encode()),
            (1,a.canonical({'jsonrpc':'2.0','id':1,'result':'devnet'})),
            (2,a.canonical({'jsonrpc':'2.0','id':999,'result':BASE-2})),
            (2,a.canonical({'jsonrpc':'2.0','id':2,'result':None}))]
        for index,raw in cases:
            with self.subTest(index=index,raw=raw[:40]):
                c,s,ctx=forged_capture(f,index,raw)
                v.validate_capture(f['r'],c)  # Capture retention is separate from source validity.
                with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'],c,s,ctx)

    def test_duplicate_raw_json_and_unsupported_fields_refuse_independent_parser(self):
        f=fixture()
        for raw in (b'{"jsonrpc":"2.0","id":2,"id":2,"result":1800000000}',
                b'{"jsonrpc":"2.0","id":2,"result":1800000000,"error":null}'):
            c,s,ctx=forged_capture(f,2,raw)
            with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'],c,s,ctx)

    def test_all_fields_types_versions_bool_aliases_and_authority_checked(self):
        f=fixture()
        for original,change in ((f['r'],lambda data:data.update(genesis_rpc_id=True)),
                (f['candidate'],lambda data:data['authority'].update(native_admission=True)),
                (f['ctx'],lambda data:data.update(prior_ingest_sequence=0)),
                (f['candidate'],lambda data:data.update(extra='unknown')),
                (f['s'],lambda data:data.update(policy_sha256='d'*64))):
            with self.assertRaises(v.SourceAdmissionError):alter(original,change)

    def test_capture_completed_nullability_and_withheld_diagnostic_cannot_be_source(self):
        f=fixture();r=f['r'].to_dict();row={'record_id':r['price_record_id'],'provider_family':'jupiter-price-v3',
            'endpoint_binding_id':uid(23),'request_sha256':v.sha(a.public_request('jupiter-price-v3')),
            'request_started_wall_us':str(BASE*1000000),'request_started_monotonic_us':'9800000',
            'received_wall_us':str(BASE*1000000+100000),'received_monotonic_us':'9900000','http_status':'401',
            'body_state':'withheld','incomplete':True,'failure_code':'credential_echo_withheld'}
        capture=alter(f['c'],lambda data:data.update(capsule_wires=[],diagnostics=[row],collection_completed=False,failure_code='credential_echo_withheld'))
        v.validate_capture(f['r'],capture)
        s=alter(f['s'],lambda data:data.update(capture_sha256=capture.sha256))
        ctx=alter(f['ctx'],lambda data:data.update(expected_capture_sha256=capture.sha256))
        with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'],capture,s,ctx)
        with self.assertRaises(v.SourceAdmissionError):alter(capture,lambda data:data.update(collection_completed=True,failure_code=None))
        bad=alter(f['c'],lambda data:data.update(diagnostics=[row],collection_completed=False,failure_code='cleanup_incomplete'))
        with self.assertRaises(v.SourceAdmissionError):v.validate_capture(f['r'],bad)

    def test_completed_original_capsule_with_cleanup_diagnostic_preserved_but_ineligible(self):
        f=fixture();row=f['capsules'][2].to_dict()
        diagnostic={key:row[key] for key in ('record_id','provider_family','endpoint_binding_id','request_sha256',
            'request_started_wall_us','request_started_monotonic_us','received_wall_us','received_monotonic_us','http_status')}
        diagnostic.update(body_state='captured_original',incomplete=True,failure_code='cleanup_incomplete')
        capture=alter(f['c'],lambda data:data.update(diagnostics=[diagnostic],collection_completed=False,failure_code='cleanup_incomplete'))
        self.assertIs(v.validate_capture(f['r'],capture),capture)
        self.assertEqual(len(capture.to_dict()['capsule_wires']),3)

    def test_exact_current_retained_reservation_capture_and_records_are_not_fresh_reallocation(self):
        f=fixture();r=f['r'].to_dict();known=[]
        for pin in f['candidate'].to_dict()['normalized']['record_pins']:
            known.append({key:pin[key] for key in ('record_id','capsule_sha256','raw_response_ref','response_sha256')})
            known[-1]['reservation_sha256']=f['r'].sha256
        ops=[{'operation_id':r['reservation_id'],'operation_kind':'reservation','original_wire_sha256':f['r'].sha256},
            {'operation_id':r['capture_id'],'operation_kind':'capture','original_wire_sha256':f['c'].sha256}]
        ctx=alter(f['ctx'],lambda data:data.update(known_records=known,known_operations=ops))
        self.assertEqual(v.validate_submission(f['r'],f['c'],f['s'],ctx).wire,f['candidate'].wire)
        for change in (lambda data:data['known_records'][0].update(reservation_sha256='d'*64),
                lambda data:data['known_records'][0].update(capsule_sha256='d'*64),
                lambda data:data['known_operations'][0].update(operation_kind='capture')):
            bad=alter(ctx,change)
            with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'],f['c'],f['s'],bad)

    def test_rehashed_current_raw_reference_cannot_alias_another_known_record_id(self):
        f=fixture();cdata=f['c'].to_dict()
        row=a.read_json(cdata['capsule_wires'][0].encode(),a.MAX_CAPSULE_BYTES,exact=True)
        row['raw_response_ref']=uid(6000);cdata['capsule_wires'][0]=a.canonical(row).decode()
        c=v.envelope('Capture',cdata);s=alter(f['s'],lambda data:data.update(capture_sha256=c.sha256))
        known={'record_id':uid(6000),'capsule_sha256':'d'*64,'raw_response_ref':uid(6001),
            'response_sha256':'e'*64,'reservation_sha256':'f'*64}
        ctx=alter(f['ctx'],lambda data:data.update(expected_capture_sha256=c.sha256,known_records=[known]))
        v.validate_capture(f['r'],c)
        with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'],c,s,ctx)

    def test_identical_body_reservation_cannot_reuse_another_original_record_raw_reference(self):
        f=fixture();cdata=f['c'].to_dict();row=a.read_json(cdata['capsule_wires'][0].encode(),a.MAX_CAPSULE_BYTES,exact=True)
        row['raw_response_ref']=uid(6001);cdata['capsule_wires'][0]=a.canonical(row).decode()
        c=v.envelope('Capture',cdata);s=alter(f['s'],lambda data:data.update(capture_sha256=c.sha256))
        known={'record_id':uid(6000),'capsule_sha256':'d'*64,'raw_response_ref':uid(6001),
            'response_sha256':row['response_sha256'],'reservation_sha256':f['r'].sha256}
        ctx=alter(f['ctx'],lambda data:data.update(expected_capture_sha256=c.sha256,known_records=[known]))
        v.validate_capture(f['r'],c)
        with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'],c,s,ctx)

    def test_replay_preserves_original_before_current_freshness_without_new_clock_or_sequence(self):
        f=fixture();original=f['candidate']
        ctx=alter(f['ctx'],lambda data:data.update(original_resolution='original_committed',original_admission_wire=original.wire.decode(),
            process_clock={**data['process_clock'],'wall_lower_us':str((BASE+100)*1000000),'wall_upper_us':str((BASE+100)*1000000)},
            admission_guard=utc((BASE+100)*1000000),final_guard=utc((BASE+100)*1000000)))
        replay=v.validate_submission(f['r'],f['c'],f['s'],ctx)
        self.assertEqual(replay.wire,original.wire)
        altered=alter(f['s'],lambda data:data.update(previous_admission_sha256='d'*64))
        with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'],f['c'],altered,ctx)

    def test_unknown_missing_getter_is_not_terminal_absence_or_fresh(self):
        f=fixture();ctx=alter(f['ctx'],lambda data:data.update(original_resolution='unknown'))
        with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'],f['c'],f['s'],ctx)

    def test_final_guard_receipt_and_source_budget_fractional_boundaries(self):
        f=fixture();at=BASE*1000000+200000
        # Receipt age100000 + native elapsed4900000 == 5s must refuse.
        ctx=alter(f['ctx'],lambda data:data.update(final_guard=utc(at+4900000)))
        with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'],f['c'],f['s'],ctx)
        good=alter(f['ctx'],lambda data:data.update(final_guard=utc(at+4899999)))
        self.assertEqual(v.validate_submission(f['r'],f['c'],f['s'],good).to_dict()['normalized'],f['candidate'].to_dict()['normalized'])
        with self.assertRaises(v.SourceAdmissionError):fixture(source_second=BASE-30)
        with self.assertRaises(v.SourceAdmissionError):fixture(source_second=BASE+3)

    def test_current_raw_immutable_byte_and_request_hash_mismatch_refuse(self):
        f=fixture();cdata=f['c'].to_dict();row=a.read_json(cdata['capsule_wires'][0].encode(),a.MAX_CAPSULE_BYTES,exact=True)
        for key in ('request_sha256','response_sha256'):
            bad=deepcopy(row);bad[key]='d'*64;cdata['capsule_wires'][0]=a.canonical(bad).decode()
            c=v.envelope('Capture',cdata)
            with self.assertRaises(v.SourceAdmissionError):v.validate_capture(f['r'],c)

    def test_same_epoch_and_cross_epoch_original_age_carry_and_no_source_rebase(self):
        old=fixture()
        new=fixture(1,second=BASE+1,mono=11000000,source_second=BASE-2,previous=old,sequence=7)
        self.assertEqual(new['candidate'].to_dict()['normalized']['source_age_ceiling_us'],'3200000')
        restarted=fixture(2,second=BASE+1,epoch=30,mono=1000000,source_second=BASE-2,previous=old,sequence=7)
        self.assertEqual(restarted['candidate'].to_dict()['normalized']['source_age_ceiling_us'],'3200000')
        with self.assertRaises(v.SourceAdmissionError):fixture(3,second=BASE+31,mono=41000000,source_second=BASE-2,previous=old,sequence=7)

    def test_prior_snapshot_cannot_fall_below_independent_original_raw_clock_baseline(self):
        old=fixture();candidate=alter(old['candidate'],lambda data:data['normalized'].update(source_age_floor_us='0',source_age_ceiling_us='0'))
        with self.assertRaises(v.SourceAdmissionError):v.validate_readback(candidate,old['r'],old['c'],old['s'],old['rb'],old['av'])

    def test_old_source_lower_block_time_and_reused_prior_record_ids_refuse(self):
        old=fixture()
        with self.assertRaises(v.SourceAdmissionError):fixture(1,second=BASE+1,source_second=BASE-3,previous=old,sequence=7)
        with self.assertRaises(v.SourceAdmissionError):fixture(0,second=BASE+1,previous=old,sequence=7)

    def test_same_block_changed_raw_price_refuses_even_with_fresh_originals_and_rehashed_links(self):
        old=fixture();new=fixture(1,second=BASE+1,mono=11000000,source_second=BASE-2,previous=old,sequence=7)
        raw=('{"'+a.MINT+'":{"usdPrice":101,"blockId":42,"decimals":9,"priceChange24h":null}}').encode()
        c,s,ctx=forged_capture(new,0,raw)
        v.validate_capture(new['r'],c)
        with self.assertRaises(v.SourceAdmissionError):v.validate_submission(new['r'],c,s,ctx,prior=old['prior'])

    def test_higher_sequence_later_monotonic_cannot_regress_original_native_acceptance_or_final_guard(self):
        old=fixture();new=fixture(1,second=BASE+1,mono=11000000,source_second=BASE-2,previous=old,sequence=7)
        def current(data):
            # Original receipt UTC is ahead of this bounded supplied process
            # interval within its existing two-second skew tolerance; mono
            # advances genuinely and raw/source age guards otherwise pass.
            data['process_clock']['wall_lower_us']=data['process_clock']['wall_upper_us']=str(BASE*1000000+200000)
            data['admission_guard']=utc(BASE*1000000+300000)
            data['final_guard']=utc(BASE*1000000+400000)
        equal=alter(new['ctx'],current)
        self.assertEqual(v.validate_submission(new['r'],new['c'],new['s'],equal,prior=old['prior']).to_dict()['admission_guard'],
            old['candidate'].to_dict()['admission_guard'])
        for key,at in (('admission_guard',BASE*1000000+250000),('final_guard',BASE*1000000+399999)):
            ctx=alter(equal,lambda data:data.update({key:utc(at)}))
            with self.assertRaises(v.SourceAdmissionError):v.validate_submission(new['r'],new['c'],new['s'],ctx,prior=old['prior'])

    def test_epoch_reuse_registry_and_package_drift_refuse(self):
        f=fixture()
        def reused(data):
            data['epoch_registry'][0]['status']='retired';data['epoch_registry'].append({**data['epoch_registry'][0],
                'ordinal':'2','predecessor_epoch':uid(20),'status':'active'})
        with self.assertRaises(v.SourceAdmissionError):alter(f['ctx'],reused)
        ctx=alter(f['ctx'],lambda data:data['policies'].update(native_package_sha256='d'*64))
        with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'],f['c'],f['s'],ctx)

    def test_retired_registry_principal_and_package_must_match_original_prior_reservation(self):
        old=fixture();new=fixture(1,second=BASE+1,epoch=30,mono=1000000,source_second=BASE-2,previous=old,sequence=7)
        for change in (lambda data:data['epoch_registry'][0].update(issuer_principal_binding_id=uid(70)),
                lambda data:data['epoch_registry'][0].update(recorder_package_sha256='d'*64)):
            ctx=alter(new['ctx'],change)
            with self.assertRaises(v.SourceAdmissionError):v.validate_submission(new['r'],new['c'],new['s'],ctx,prior=old['prior'])

    def test_readback_and_availability_preserve_original_hash_time_sequence_and_package(self):
        f=fixture();v.validate_readback(f['candidate'],f['r'],f['c'],f['s'],f['rb'],f['av'])
        for change in (lambda data:data.update(original_admission_sha256='d'*64),
                lambda data:data.update(native_package_sha256='d'*64),
                lambda data:data.update(supplied_accepted_at_us=str(BASE*1000000)),
                lambda data:data.update(readback_guard=utc(BASE*1000000))):
            rb=alter(f['rb'],change)
            with self.assertRaises(v.SourceAdmissionError):v.validate_readback(f['candidate'],f['r'],f['c'],f['s'],rb,f['av'])
        with self.assertRaises(v.SourceAdmissionError):alter(f['av'],lambda data:data.update(available_at_upper_us='0'))

    def test_namespace_aliases_and_reference_only_or_dict_inputs_refuse(self):
        f=fixture()
        with self.assertRaises(v.SourceAdmissionError):alter(f['r'],lambda data:data.update(observation_id=SCOPE['owner_id']))
        with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'].to_dict(),f['c'],f['s'],f['ctx'])
        with self.assertRaises(v.SourceAdmissionError):v.validate_submission(f['r'],f['c'],f['s'],f['ctx'],prior=f['candidate'])

    def test_pure_module_has_no_normalized_derivation_wrapper_clock_random_env_native_calls(self):
        tree=ast.parse(Path(v.__file__).read_text())
        names=[ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node,ast.Call)]
        for forbidden in ('d.derive_observation','a.assess_record_age','source.capture_mark','time.time_ns','uuid4','os.getenv','os.environ.get'):
            self.assertNotIn(forbidden,names)
        self.assertNotIn('provider_derivation_v3',Path(v.__file__).read_text())


class SourceSealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with deny_network():
            cls.bundles=[];previous=None
            for index in range(915):
                previous=fixture(index,second=BASE+index*60,mono=10_000_000+index*60_000_000,
                    previous=previous,sequence=4*index+3,block=42+index)
                cls.bundles.append(previous)
            cls.rows=journal(cls.bundles);cls.seal=make_seal(cls.rows,cls.bundles);cls.dependencies=originals(cls.bundles)
    def setUp(self):
        self.network=deny_network();self.network.__enter__();self.addCleanup(self.network.__exit__,None,None,None)

    def test_full_915_original_minute_supplied_inventory_raw_dependencies_and_false_authority(self):
        self.assertIs(v.validate_seal(self.seal,self.dependencies),self.seal)
        self.assertEqual(len(self.bundles),915);self.assertEqual(len(self.rows),3660)
        self.assertFalse(self.seal.native_admission);self.assertFalse(self.seal.running_authority)

    def test_late_original_availability_with_matching_rehashed_eligible_digest_cannot_fill_minute(self):
        changed=dict(self.bundles[-1]);late=(BASE+915*60)*1000000+1
        changed['rb']=alter(changed['rb'],lambda data:data.update(readback_guard=utc(late)))
        changed['av']=alter(changed['av'],lambda data:data.update(readback_guard=utc(late),available_at_upper_us=str(late),
            original_readback_sha256=changed['rb'].sha256))
        bundles=self.bundles[:-1]+[changed];rows=journal(bundles)
        seal=make_seal(rows,bundles)
        # Deliberately rehash the supplied eligible set without the late mark;
        # refusal must come from the missing minute, not stale pointer hashes.
        seal=alter(seal,lambda data:data.update(eligible_records_sha256=v.sha(a.canonical(eligible_pins(bundles[:-1])))))
        v.validate_readback(changed['candidate'],changed['r'],changed['c'],changed['s'],changed['rb'],changed['av'])
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(seal,originals(bundles))

    def test_missing_original_getter_not_replaced_by_valid_hash_only(self):
        dependencies=tuple(item for item in self.dependencies if item is not self.bundles[-1]['c'])
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(self.seal,dependencies)

    def test_supplied_pending_write_cannot_be_omitted_from_complete_supplied_inventory(self):
        pending=fixture(9999)['r']
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(self.seal,self.dependencies+(pending,))

    def test_excluded_capture_outcome_must_resolve_and_validate_original_capture_pair(self):
        f=fixture(9999);cdata=f['c'].to_dict();cdata['capsule_wires']=['not a capsule']
        cdata.update(collection_completed=False,failure_code='invalid_or_unavailable_packet')
        capture=v.envelope('Capture',cdata);r=f['r'].to_dict()
        extra=[{'inventory_sequence':str(3661+offset),'operation_id':item.to_dict()[id_key],
            'operation_kind':kind,'original_wire_sha256':item.sha256,'admission_id':r['admission_id'],
            'observation_id':r['observation_id'],'reservation_sha256':f['r'].sha256,'capture_sha256':capture.sha256,
            'admission_sha256':None,'availability_sha256':None,'ingest_sequence':None,'outcome':'refused_source'}
            for offset,(item,kind,id_key) in enumerate(((f['r'],'reservation','reservation_id'),(capture,'capture','capture_id')))]
        seal=make_seal(self.rows+extra,self.bundles)
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(seal,self.dependencies+(f['r'],capture))
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(seal,self.dependencies+(f['r'],))

    def test_omitted_or_changed_operation_position_with_rehashed_inventory_refuses(self):
        for rows in (self.rows[:2]+self.rows[3:],self.rows[:-1]+[{**self.rows[-1],'inventory_sequence':'3661'}]):
            seal=make_seal(rows,self.bundles)
            with self.assertRaises(v.SourceAdmissionError):v.validate_seal(seal,self.dependencies)

    def test_admission_sequence_must_match_its_own_original_journal_operation(self):
        rows=deepcopy(self.rows);rows[2]['ingest_sequence']='4';seal=make_seal(rows,self.bundles)
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(seal,self.dependencies)

    def test_rehashed_cross_packet_reservation_journal_association_refuses(self):
        rows=deepcopy(self.rows);other=self.bundles[1]
        for key in ('admission_id','observation_id'):rows[0][key]=other['r'].to_dict()[key]
        rows[0].update(reservation_sha256=other['r'].sha256,capture_sha256=other['c'].sha256,
            admission_sha256=other['candidate'].sha256,availability_sha256=other['av'].sha256,
            ingest_sequence=other['rb'].to_dict()['supplied_ingest_sequence'])
        seal=make_seal(rows,self.bundles)
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(seal,self.dependencies)

    def test_original_dependency_same_kind_id_different_wire_does_not_silently_overwrite(self):
        changed=alter(self.bundles[0]['candidate'],lambda data:data['normalized'].update(source_age_ceiling_us='2300000'))
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(self.seal,self.dependencies+(changed,))

    def test_identical_original_dependency_is_not_a_second_write_or_lookup_entry(self):
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(self.seal,self.dependencies+(self.bundles[0]['r'],))

    def test_unrelated_or_foreign_scope_getter_cannot_be_ignored_in_supplied_witness(self):
        f=fixture(9999)
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(self.seal,self.dependencies+(f['s'],))
        changed=alter(self.bundles[0]['s'],lambda data:data['scope'].update(owner_id=uid(700)))
        dependencies=tuple(changed if item is self.bundles[0]['s'] else item for item in self.dependencies)
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(self.seal,dependencies)

    def test_cross_packet_record_raw_and_observation_aliases_refuse_after_rehashing(self):
        f=fixture(9999);first=self.bundles[0]['r'].to_dict()
        for alias in ('record','raw','observation'):
            rdata=f['r'].to_dict();cdata=f['c'].to_dict()
            capsule=a.read_json(cdata['capsule_wires'][0].encode(),a.MAX_CAPSULE_BYTES,exact=True)
            if alias=='record':
                rdata['price_record_id']=first['price_record_id'];capsule['record_id']=first['price_record_id']
            elif alias=='raw':capsule['raw_response_ref']=first['price_record_id']
            else:rdata['observation_id']=first['observation_id'];cdata['observation_id']=first['observation_id']
            cdata['capsule_wires'][0]=a.canonical(capsule).decode();r=v.envelope('Reservation',rdata)
            cdata['reservation_sha256']=r.sha256;c=v.envelope('Capture',cdata)
            v.validate_capture(r,c)
            seal=make_seal(self.rows+excluded_entries(r,c,3661),self.bundles)
            with self.assertRaises(v.SourceAdmissionError):v.validate_seal(seal,self.dependencies+(r,c))

    def test_rehashed_baseline_valid_extra_original_cannot_regress_consumer_order_or_change_same_block_price(self):
        old=self.bundles[-1];oldn=old['candidate'].to_dict()['normalized'];second=BASE+914*60
        # Extra originals remain within the already covered last minute, so a
        # missing-anchor refusal cannot hide the required sequence-order gate.
        for failure in ('accepted','block','source','same_block_price'):
            extra=fixture(9999,second=second+(failure=='same_block_price'),
                mono=10_000_000+914*60_000_000+(failure=='same_block_price')*1_000_000,
                source_second=second-3 if failure=='source' else int(oldn['estimated_source_second']),
                sequence=3663,block=int(oldn['block_ref'])+(-1 if failure=='block' else 1 if failure=='source' else 0))
            extra=self_rehashed_seal_original(extra,old,price='101' if failure=='same_block_price' else None,
                admission_us=second*1000000+250000 if failure=='accepted' else None)
            v.validate_readback(extra['candidate'],extra['r'],extra['c'],extra['s'],extra['rb'],extra['av'])
            rows=self.rows+journal([extra],3661);seal=make_seal(rows,self.bundles+[extra])
            with self.assertRaises(v.SourceAdmissionError):v.validate_seal(seal,self.dependencies+originals([extra]))

    def test_supplied_unavailable_readback_still_requires_original_acceptance_pins_and_position(self):
        old=self.bundles[-1];second=BASE+914*60+1
        extra=fixture(9999,second=second,mono=10_000_000+914*60_000_000+1_000_000,
            sequence=3663,block=int(old['candidate'].to_dict()['normalized']['block_ref'])+1)
        extra=self_rehashed_seal_original(extra,old)
        rows=journal([extra],3661)[:3]
        for row in rows:row['availability_sha256']=None
        seal=make_seal(self.rows+rows,self.bundles)
        dependencies=self.dependencies+tuple(extra[key] for key in ('r','c','s','candidate','rb'))
        self.assertIs(v.validate_seal(seal,dependencies),seal)
        for key,changed in (('supplied_accepted_at_us','0'),('supplied_ingest_sequence','3664')):
            rb=alter(extra['rb'],lambda data:data.update({key:changed}))
            bad=tuple(rb if item is extra['rb'] else item for item in dependencies)
            with self.assertRaises(v.SourceAdmissionError):v.validate_seal(seal,bad)

    def test_outcome_nullability_and_current_self_inventoried_seal_refuse(self):
        rows=deepcopy(self.rows);rows[0]['outcome']='capture_only'
        with self.assertRaises(v.SourceAdmissionError):make_seal(rows,self.bundles)
        row={'inventory_sequence':'3661','operation_id':self.seal.to_dict()['seal_id'],'operation_kind':'seal',
            'original_wire_sha256':self.seal.sha256,'admission_id':None,'observation_id':None,'reservation_sha256':None,
            'capture_sha256':None,'admission_sha256':None,'availability_sha256':None,'ingest_sequence':None,'outcome':'seal_boundary'}
        seal=make_seal(self.rows+[row],self.bundles)
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(seal,self.dependencies+(self.seal,))

    def test_single_next_interval_prior_seal_boundary_and_original_overlap(self):
        added=[];previous=self.bundles[-1]
        for index in range(915,930):
            # Prior seal takes journal position3661, ahead of these new writes.
            previous=fixture(index,second=BASE+index*60,mono=10_000_000+index*60_000_000,
                previous=previous,sequence=4*index+4,block=42+index)
            added.append(previous)
        boundary={'inventory_sequence':'3661','operation_id':self.seal.to_dict()['seal_id'],'operation_kind':'seal',
            'original_wire_sha256':self.seal.sha256,'admission_id':None,'observation_id':None,'reservation_sha256':None,
            'capture_sha256':None,'admission_sha256':None,'availability_sha256':None,'ingest_sequence':None,'outcome':'seal_boundary'}
        rows=[boundary]+journal(added,3662);retained=self.bundles[-15:]+added
        end=BASE+930*60
        seal=make_seal(rows,retained,start=end-1800,end=end,previous=self.seal,identity=90001)
        dependencies=self.dependencies+originals(added)+(self.seal,)
        self.assertIs(v.validate_seal(seal,dependencies,previous=self.seal,expected_previous_sha256=self.seal.sha256),seal)
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(seal,dependencies,previous=self.seal,expected_previous_sha256='d'*64)
        # A lookup replay keeps its old journal position. Even identical old
        # bytes cannot be appended as a new operation in the next interval.
        original=self.bundles[0]['r'];body=original.to_dict()
        repeated={'inventory_sequence':'3722','operation_id':body['reservation_id'],'operation_kind':'reservation',
            'original_wire_sha256':original.sha256,'admission_id':body['admission_id'],'observation_id':body['observation_id'],
            'reservation_sha256':original.sha256,'capture_sha256':None,'admission_sha256':None,'availability_sha256':None,
            'ingest_sequence':None,'outcome':'reserved_pending'}
        bad=make_seal(rows+[repeated],retained,start=end-1800,end=end,previous=self.seal,identity=90001)
        with self.assertRaises(v.SourceAdmissionError):v.validate_seal(bad,dependencies,previous=self.seal,expected_previous_sha256=self.seal.sha256)
        # A second increment keeps precisely the prior/new supplied write
        # intervals and both original seal boundaries, without inventing packet
        # links for a seal or requiring unrelated older write envelopes.
        next_added=[];previous=added[-1]
        for index in range(930,945):
            previous=fixture(index,second=BASE+index*60,mono=10_000_000+index*60_000_000,
                previous=previous,sequence=4*index+5,block=42+index)
            next_added.append(previous)
        next_boundary={**boundary,'inventory_sequence':'3722','operation_id':seal.to_dict()['seal_id'],
            'original_wire_sha256':seal.sha256}
        next_rows=[next_boundary]+journal(next_added,3723);next_end=BASE+945*60
        following=make_seal(next_rows,added+next_added,start=next_end-1800,end=next_end,previous=seal,identity=90002)
        next_dependencies=originals(added+next_added)+(self.seal,seal)
        self.assertIs(v.validate_seal(following,next_dependencies,previous=seal,expected_previous_sha256=seal.sha256),following)


if __name__=='__main__':unittest.main()
