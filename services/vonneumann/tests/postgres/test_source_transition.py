"""Independent original-wire source and binary64 proof in owned local PostgreSQL."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import random
import time
import unittest
from uuid import UUID

from tests.postgres.harness import OPT_IN
from tests.postgres.test_economic_transition import EconomicTransitionSqlTests, INSTALLER, AUDITOR
from tests.measure_provider_ga_research import literal
from tests.test_provider_contract import OWNER, RUN, EPOCH, WALL, MONO, seed_bundle, source_inputs, raw_capture
from tests.security_support import deny_network
from vonneumann.core import exact_rehearsal as base
from vonneumann.research import numeric_wire as numbers
from vonneumann.research import partitioned_checkpoint as cp, provider_ga_model as ga

ROOT=Path(__file__).resolve().parents[2]
SQL=ROOT/'db-contract'/'research'/'source_transition.sql'


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class SourceTransitionSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EconomicTransitionSqlTests.setUpClass.__func__(cls)
        try:
            source=SQL.read_text(); cls.source_sql_sha256=hashlib.sha256(source.encode()).hexdigest()
            denied=cls.db.sql(source,role=INSTALLER,check=False)
            if denied.returncode==0 or 'offline_source_transition_fixture_required' not in denied.stderr:
                raise AssertionError('Source artifact installed without offline guard')
            cls.db.sql("BEGIN; SET dashboard.source_transition_fixture='offline-v1';"+source+'COMMIT;',role=INSTALLER)
            cls.db.sql(f'''REVOKE EXECUTE ON FUNCTION vn_economic_research.validate_request(uuid,uuid,text) FROM {AUDITOR};
              GRANT USAGE ON SCHEMA vn_source_research TO {AUDITOR};
              GRANT EXECUTE ON FUNCTION vn_source_research.validate_request(uuid,uuid,text) TO {AUDITOR};''',role=INSTALLER)
        except BaseException:
            cls.db.close(); raise

    @classmethod
    def tearDownClass(cls): cls.db.close()

    setUp=EconomicTransitionSqlTests.setUp
    seed=EconomicTransitionSqlTests.seed
    prefix=EconomicTransitionSqlTests.prefix
    snapshot=EconomicTransitionSqlTests.snapshot
    reject=EconomicTransitionSqlTests.reject
    phase=EconomicTransitionSqlTests.phase
    audit=EconomicTransitionSqlTests.audit

    def sql(self,wire):
        return 'SELECT vn_source_research.validate_request('+','.join(
            (literal(OWNER),literal(RUN),literal(wire.decode())))+');'

    def block(self,row,body,kind,alter):
        original=next(b.to_dict() for b in row[1].components if b.to_dict()['kind']==kind)
        old=hashlib.sha256(numbers.encode(original)).hexdigest()
        alter(original['body'])
        new=hashlib.sha256(numbers.encode(original)).hexdigest()
        body['components']=[b for b in body['components'] if hashlib.sha256(numbers.encode(b)).hexdigest()!=old]
        body['components'].append(original)
        for ref in body['checkpoint']['components']:
            if ref['sha256']==old: ref['sha256']=new
        return body

    def test_complete_provider_control_risk_and_held_stop_traces(self):
        total=0
        for name,rows in [('dense',self.samples),*self.extras.items()]:
            self.setUp()
            for row in rows:
                before=self.snapshot(); result=self.audit(row[2])
                self.assertEqual(result['format'],'ga-source-validation-research-v1')
                self.assertEqual(int(result['source_evidence']['source_sequence']['$integer']),row[0].state.to_dict()['source']['quote_sequence'])
                self.assertEqual(self.snapshot(),before)
                self.seed(row); total+=1
        self.assertEqual(total,93)

    def test_binary64_ratio_rounding_ties_subnormal_and_seeded_operations(self):
        rng=random.Random(73119); cases=[]
        ratios=[Fraction(0),Fraction(1),Fraction(-1),Fraction(1,2**1074),
            Fraction(1,2**1075),Fraction(3,2**1075),Fraction(2**53+1,2**53),
            Fraction(2**53+3,2**53),Fraction(-(2**53+1),2**53),Fraction(1,10**18),Fraction(10**36)]
        for _ in range(96):
            value=math.ldexp(rng.uniform(-2,2),rng.randint(-1000,900))
            ratios.append(Fraction(value))
        for f in ratios:
            expected=float(f).hex()
            statement=f"vn_source_research.round_ratio({f.numerator}::numeric,{f.denominator}::numeric)"
            cases.append(f"SELECT {statement} = {literal(json.dumps({'$binary64':expected}))}::jsonb;")
        for _ in range(128):
            left=math.ldexp(rng.uniform(-2,2),rng.randint(-90,90)); right=math.ldexp(rng.uniform(0.1,2),rng.randint(-90,90))
            for name,expected in [('add',left+right),('subtract',left-right),('multiply',left*right),('divide',left/right)]:
                args=','.join((literal(name),literal(json.dumps({'$binary64':left.hex()}))+'::jsonb',literal(json.dumps({'$binary64':right.hex()}))+'::jsonb'))
                cases.append(f"SELECT vn_source_research.binary_operation({args}) = {literal(json.dumps({'$binary64':expected.hex()}))}::jsonb;")
        output=self.db.sql('\n'.join(cases),role=INSTALLER).stdout.splitlines()
        self.assertEqual(len(output),619); self.assertEqual(set(output),{'t'})
        zero_cases=[]
        for left,right in [(0.0,0.0),(-0.0,0.0),(0.0,-0.0),(-0.0,-0.0),(-0.0,1.0),(0.0,-1.0)]:
            for name,expected in [('add',left+right),('subtract',left-right),('multiply',left*right)]:
                args=','.join((literal(name),literal(json.dumps({'$binary64':left.hex()}))+'::jsonb',literal(json.dumps({'$binary64':right.hex()}))+'::jsonb'))
                zero_cases.append(f"SELECT vn_source_research.binary_operation({args}) = {literal(json.dumps({'$binary64':expected.hex()}))}::jsonb;")
            if right:
                args=','.join((literal('divide'),literal(json.dumps({'$binary64':left.hex()}))+'::jsonb',literal(json.dumps({'$binary64':right.hex()}))+'::jsonb'))
                zero_cases.append(f"SELECT vn_source_research.binary_operation({args}) = {literal(json.dumps({'$binary64':(left/right).hex()}))}::jsonb;")
        self.assertEqual(set(self.db.sql('\n'.join(zero_cases),role=INSTALLER).stdout.splitlines()),{'t'})
        self.assertEqual(len(zero_cases),20)
        for exponent in (1024,1025):
            denied=self.db.sql(f'SELECT vn_source_research.round_ratio({2**exponent}::numeric,1);',role=INSTALLER,check=False)
            self.assertNotEqual(denied.returncode,0); self.assertIn('source_binary64_overflow',denied.stderr)

    def test_all_59_seed_periods_and_continuation_on_adversarial_price_sequences(self):
        rng=random.Random(79249)
        profiles=[['0.000000000000000001']*68,['1000000000000000000000000000000000000']*68,
            ['100.000000000000000001','100.000000000000000003']*34,
            ['0.000000000000000001','1000000000000000000000000000000000000']*34]
        # Decimal monetary strings remain canonical; indicators alone are binary64.
        from vonneumann.core.decimal_execution import _text
        profiles.extend([[_text(rng.randrange(1,10**43),18) for _ in range(68)] for _ in range(4)])
        for profile in profiles:
            engine={'ema':{'count':0,'last_end':None,'closes':[],'values':{},'previous':{}}}
            bars=[]
            for i,price in enumerate(profile):
                end=(i+1)*900; bars.append([end,price,'0'*64])
                base._append_candle(engine,base.ExactObservation(100000,price,end,price))
                if i==60:
                    initial=deepcopy(engine['ema'])
                    actual=json.loads(self.db.scalar('SELECT vn_source_research.indicators(NULL,'+
                        literal(numbers.encode(bars).decode())+'::jsonb);',role=INSTALLER))
                    self.assertEqual(actual,json.loads(numbers.encode(initial)))
            actual=json.loads(self.db.scalar('SELECT vn_source_research.indicators('+
                literal(numbers.encode(initial).decode())+'::jsonb,'+
                literal(numbers.encode(bars[61:]).decode())+'::jsonb);',role=INSTALLER))
            self.assertEqual(actual,json.loads(numbers.encode(engine['ema'])))

    def test_request_hash_provider_endpoint_mint_and_policy_binding(self):
        body=numbers.decode(self.samples[0][2])
        for alter in (
            lambda d:d.update(request_sha256='0'*64),
            lambda d:d.update(response_bytes=0),
            lambda d:d.update(parser_policy='unreviewed'),
            lambda d:d['request'].update(endpoint='https://wrong.invalid/ohlcv'),
            lambda d:d['request']['parameters'].update(address='11111111111111111111111111111111'),
            lambda d:d['request']['parameters'].update(time_to=d['request']['parameters']['time_to']+60)):
            bad=deepcopy(body); alter(bad['evidence']['inputs']['provider']['history']['documents'][0]); self.reject(bad)
        bad=deepcopy(body)
        self.block(self.samples[0],bad,'configuration',lambda b:b['source_policy'].update(max_receipt_age_us=6000000))
        self.reject(bad,'source_policy_mismatch')

    def test_original_minutes_contiguity_range_completion_and_document_use(self):
        body=numbers.decode(self.samples[0][2])
        changes=(lambda h:h['minutes'][1].__setitem__(0,h['minutes'][0][0]),
            lambda h:h['minutes'][1].__setitem__(1,'0'),
            lambda h:h['minutes'][1].__setitem__(2,1),
            lambda h:h['minutes'].reverse(),lambda h:h.update(unscaled=False),
            lambda h:h['documents'].append(deepcopy(h['documents'][0])),
            lambda h:h['documents'][0].update(received_wall_us=h['minutes'][-1][0]*1000000),
            lambda h:h['minutes'][-1].__setitem__(1,'100.000000000000000001'))
        for alter in changes:
            bad=deepcopy(body); alter(bad['evidence']['inputs']['provider']['history']); self.reject(bad)

    def test_well_hashed_seed_indicators_previous_and_candle_fingerprint(self):
        row=self.samples[0]; body=numbers.decode(row[2])
        for field in ('values','previous'):
            bad=deepcopy(body)
            self.block(row,bad,'ema',lambda b:b[field].update({'2':math.nextafter(100.0,math.inf).hex()}))
            self.reject(bad,'source_indicator_recurrence_mismatch')
        bad=deepcopy(body)
        self.block(row,bad,'source_bars',lambda b:b['bars'][0].__setitem__(2,'0'*64))
        self.reject(bad,'source_after_mismatch')

    def test_sequence_block_source_clock_and_carried_age_continuation(self):
        index,row=next((i,r) for i,r in enumerate(self.samples) if r[0].transition['evidence']['kind']=='protective'
            and r[0].transition['before']['source']['last_quote'] is not None)
        self.prefix(self.samples,index); body=numbers.decode(row[2]); old=row[0].transition['before']['source']['last_quote']
        for alter in (lambda f:f.update(sequence=f['sequence']+1),
            lambda f:f['quote'].update(block_ref=old['quote']['block_ref']),
            lambda f:f['quote'].update(estimated_source_second=old['quote']['estimated_source_second']-1),
            lambda f:f['quote']['document'].update(received_monotonic_us=old['quote']['document']['received_monotonic_us']),
            lambda f:f.update(decision_wall_us=old['decision_wall_us']-1)):
            bad=deepcopy(body); alter(bad['evidence']['inputs']['provider']['frame']); self.reject(bad)
        bad=deepcopy(body); bad['evidence']['inputs']['provider']['frame']['quote']['source_age_floor_us']=30000001
        self.reject(bad,'source_quote_stale')

    def test_carried_age_floor_cannot_be_reset_in_a_consistently_rehashed_frame(self):
        rows=[]; old=None; ledger=ga.SimulationLedger(OWNER,RUN)
        def accept(candidate):
            nonlocal old
            capture=cp.capture_owned_candidate(candidate)
            wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=71000000+candidate.state.revision)),previous=old)
            rows.append((candidate,capture,wire)); old=capture
            return ledger.accept(candidate)
        with deny_network():
            state=accept(ga.bootstrap(ga.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=EPOCH),seed_bundle(),source_inputs(WALL),ledger=ledger))
            for i in (1,2):
                frame=ga.source.make_frame(raw_capture(block=100+i,source_second=WALL-19,wall=WALL+i-1,mono=MONO+i-1),
                    prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=WALL+i,monotonic_now=MONO+i)
                state=accept(ga.prepare_protective(state,frame,source_inputs(WALL+i,mono=MONO+i,serial=i),ledger=ledger))
        self.prefix(rows,2); self.audit(rows[2][2])
        body=numbers.decode(rows[2][2]); frame=body['evidence']['inputs']['provider']['frame']
        self.assertGreater(frame['quote']['source_age_floor_us'],0)
        frame['quote']['source_age_floor_us']=0
        body['checkpoint']['source']['last_quote']=deepcopy(frame)
        self.reject(body,'source_frame_continuation')

    def test_unsigned_64_bit_provider_blocks_are_preserved_and_bounded(self):
        index,row=next((i,r) for i,r in enumerate(self.samples) if r[0].transition['evidence']['kind']=='protective')
        self.prefix(self.samples,index); body=numbers.decode(row[2])
        frame=body['evidence']['inputs']['provider']['frame']; frame['quote']['block_ref']=2**64-1
        body['checkpoint']['source']['last_quote']=deepcopy(frame)
        self.audit(numbers.encode(body))
        for value in (-1,2**64,True):
            bad=deepcopy(body); bad['evidence']['inputs']['provider']['frame']['quote']['block_ref']=value
            bad['checkpoint']['source']['last_quote']=deepcopy(bad['evidence']['inputs']['provider']['frame'])
            self.reject(bad)

    def test_receipt_expiry_boundary_future_tolerance_and_input_clock_binding(self):
        index,row=next((i,r) for i,r in enumerate(self.samples) if r[0].transition['evidence']['kind']=='protective')
        self.prefix(self.samples,index); body=numbers.decode(row[2]); provider=body['evidence']['inputs']['provider']
        for alter in (lambda p:p['frame']['quote']['document'].update(received_monotonic_us=p['monotonic_us']-5000000),
            lambda p:p['frame']['quote']['document'].update(received_wall_us=p['wall_us']-5000000),
            lambda p:p['frame']['quote'].update(estimated_source_second=p['wall_us']//1000000+3),
            lambda p:p.update(wall_us=p['wall_us']+1),lambda p:p.update(monotonic_us=p['monotonic_us']+1)):
            bad=deepcopy(body); alter(bad['evidence']['inputs']['provider']); self.reject(bad)
        # The fixed receipt ceiling is exclusive; source age ceiling is inclusive.
        self.db.sql("SELECT vn_source_research.receipt('{\"received_wall_us\":{\"$integer\":\"1\"},\"received_monotonic_us\":{\"$integer\":\"1\"}}',5000000,5000000);",role=INSTALLER)

    def test_canonical_utc_microseconds_and_exact_binary_clock_ceil(self):
        index,row=next((i,r) for i,r in enumerate(self.samples) if r[0].transition['evidence']['kind']=='protective')
        self.prefix(self.samples,index); body=numbers.decode(row[2]); inputs=body['evidence']['inputs']
        inputs['wall_at']=inputs['wall_at'].replace('+00:00','.000001+00:00')
        inputs['provider']['wall_us']+=1
        inputs['monotonic_at']=math.nextafter(float.fromhex(inputs['monotonic_at']),math.inf).hex()
        inputs['provider']['monotonic_us']+=1
        self.audit(numbers.encode(body))
        for alter in (lambda i:i.update(wall_at=i['wall_at'].replace('.000001','.1')),
            lambda i:i.update(wall_at=i['wall_at'].replace('.000001','.000000')),
            lambda i:i.update(wall_at=i['wall_at'].replace('+00:00','Z')),
            lambda i:i.update(monotonic_at={'$binary64':i['monotonic_at']})):
            bad=deepcopy(body); alter(bad['evidence']['inputs']); self.reject(bad,'source_input_clock_shape')

    def test_exact_accepted_frame_observation_and_unchanged_stop_source(self):
        index,row=next((i,r) for i,r in enumerate(self.samples) if r[0].transition['evidence']['kind']=='decision')
        self.prefix(self.samples,index); body=numbers.decode(row[2])
        bad=deepcopy(body); bad['evidence']['inputs']['provider']['frame']['quote']['price']='100.000000000000000001'
        self.reject(bad,'source_accepted_frame_required')
        bad=deepcopy(body); bad['evidence']['observation']['price']='999'; self.reject(bad)
        rows=self.extras['held_stop']; self.prefix(rows,len(rows)-1); body=numbers.decode(rows[-1][2])
        bad=deepcopy(body); bad['evidence']['inputs']['provider']['frame']=deepcopy(rows[-2][0].state.to_dict()['source']['last_quote'])
        self.reject(bad,'source_control_mismatch')
        bad=deepcopy(body); bad['checkpoint']['source']['quote_sequence']+=1; self.reject(bad)

    def test_response_digest_is_a_manifest_binding_not_provider_authentication(self):
        body=numbers.decode(self.samples[0][2])
        body['evidence']['inputs']['provider']['history']['documents'][0]['response_sha256']='0'*64
        result=self.audit(numbers.encode(body))
        self.assertEqual(result['source_evidence']['original_document_trust'],'worker-parsed-records-and-manifests-v1')
        # Raw response bytes are not present in this versioned compact request.
        # The independent validator cannot authenticate an external body from a hash.

    def test_limited_installer_helper_isolation_and_read_only_scope(self):
        catalog=json.loads(self.db.scalar("""SELECT json_agg(x) FROM (
          SELECT p.proname,r.rolname AS owner,p.prosecdef,p.proconfig FROM pg_proc p
          JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner
          WHERE n.nspname='vn_source_research' ORDER BY p.proname)x;"""))
        self.assertEqual(len(catalog),17)
        self.assertTrue(all(r['owner']==INSTALLER and r['proconfig']==['search_path=pg_catalog'] for r in catalog))
        self.assertEqual([r['proname'] for r in catalog if r['prosecdef']],['validate_request'])
        for role in ('anon','authenticated','service_role','vn_economic_relay'):
            self.assertNotEqual(self.db.sql(self.sql(self.samples[0][2]),role=role,check=False).returncode,0)
        for statement in ('SELECT * FROM vn_dependency_research.checkpoints;',
            'SELECT vn_source_research.round_ratio(1,2);',
            'SELECT vn_economic_research.validate_request(NULL,NULL,\'{}\');',
            'CREATE SCHEMA forbidden_source_schema;'):
            self.assertNotEqual(self.db.sql(statement,role=AUDITOR,check=False).returncode,0)

    @unittest.skipUnless(os.environ.get('DASHBOARD_SOURCE_TRANSITION_MEASURE')=='1','Optional complete-wrapper timing')
    def test_z_measure_complete_source_boundary(self):
        largest=max(range(len(self.samples)),key=lambda i:len(self.samples[i][2]))
        chosen=[('bootstrap',self.samples,0),('quote',self.samples,1),('replacement',self.samples,largest),
            ('risk_trip',self.extras['risk'],len(self.extras['risk'])-2),
            ('held_stop',self.extras['held_stop'],len(self.extras['held_stop'])-1)]
        measured=[]
        for kind,rows,index in chosen:
            self.prefix(rows,index); wire=rows[index][2]; before=self.snapshot()
            source=['SET plan_cache_mode=force_generic_plan;','CREATE TEMP TABLE timings(elapsed_us bigint);',
                'DO $measure$ DECLARE t timestamptz;i integer;r jsonb;w text:='+literal(wire.decode())+
                '; BEGIN FOR i IN 1..10 LOOP t:=clock_timestamp(); r:=vn_source_research.validate_request('+
                literal(OWNER)+','+literal(RUN)+',w); INSERT INTO timings VALUES(extract(epoch FROM clock_timestamp()-t)*1000000); END LOOP; END $measure$;',
                "SELECT json_build_object('samples',count(*),'p50_us',percentile_cont(.5) WITHIN GROUP(ORDER BY elapsed_us),'p95_us',percentile_cont(.95) WITHIN GROUP(ORDER BY elapsed_us),'maximum_us',max(elapsed_us)) FROM timings;"]
            timing=json.loads(self.db.scalar('\n'.join(source),role=AUDITOR,timeout=60))
            measured.append({'kind':kind,'wire_bytes':len(wire),**timing}); self.assertEqual(self.snapshot(),before)
        directory=ROOT/'db-contract/research'
        self.assertEqual(hashlib.sha256(SQL.read_bytes()).hexdigest(),self.source_sql_sha256,'Installed SQL changed during measurement')
        artifact={'date':'2026-10-11','identity':self.db.identity,
            'sql_sha256':{name:hashlib.sha256((directory/name).read_bytes()).hexdigest()
                for name in ('numeric_wire.sql','locked_checkpoint.sql','economic_transition.sql','source_transition.sql')},
            'scope':'offline independent economics/identities/source/indicators; no causal trading/risk replay/optimizer/commit authority',
            'complete_commands':93,'independent_binary64_cases':639,'indicator_profiles':8,
            'indicator_periods':59,'indicator_seed_bars':61,'indicator_continuation_bars':7,
            'tables_in_new_artifact':0,'writes_by_validator':0,'warm_server_validation_timings':measured,
            'timing_method':'10 full volatile wrapper calls with a wire variable and generic plans; unchanged fixture prior; includes repeated dependency resolution',
            'timing_exclusions':['transport/TLS','contended locks','causal trading/risk/assessment/optimizer/lineage semantics',
                'journal/identity reservation/pins/projections','final source/lease boundary','COMMIT/WAL/relay','hosted tails'],
            'production_grants_or_install':False}
        (ROOT/'research/source-transition-measurements.json').write_text(json.dumps(artifact,indent=2,sort_keys=True)+'\n')
