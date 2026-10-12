"""Ordered source-valid economic commands still need independent causal/risk replay."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import unittest
from uuid import UUID

from tests.postgres.harness import OPT_IN
from tests.postgres.test_economic_transition import INSTALLER, AUDITOR
from tests.postgres.test_source_transition import SourceTransitionSqlTests
from tests.measure_provider_ga_research import literal
from tests.test_provider_contract import OWNER, RUN, EPOCH, WALL, MONO, source_inputs, seed_bundle, raw_capture, raw_minutes
from tests.security_support import deny_network
from vonneumann.research import numeric_wire as numbers
from vonneumann.research import partitioned_checkpoint as cp, provider_ga_model as ga
from vonneumann.core.decimal_execution import _text, _units

ROOT=Path(__file__).resolve().parents[2]
SQL=ROOT/'db-contract/research/causal_risk.sql'


def recovery_sequence():
    rows=[]; old=None; ledger=ga.SimulationLedger(OWNER,RUN)
    def accept(candidate):
        nonlocal old
        capture=cp.capture_owned_candidate(candidate)
        wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=80000000+candidate.state.revision)),previous=old)
        rows.append((candidate,capture,wire)); old=capture
        return ledger.accept(candidate)
    with deny_network():
        state=accept(ga.bootstrap(ga.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=EPOCH,account_loss_bps='49'),
            seed_bundle(last_close='80'),source_inputs(WALL),ledger=ledger))
        for i,offset in enumerate((1,900,901),1):
            wall,mono=WALL+offset,MONO+offset
            frame=ga.source.make_frame(raw_capture(price='100',block=100+i,source_second=wall-2,wall=wall-1,mono=mono-1),
                prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=i*2),ledger=ledger))
            history=None if offset%900 else ga.source.build_history(raw_minutes(end=state.to_dict()['source']['bars'][-1][0]+900,
                count=15,close='120',wall=wall-1,mono=mono-1),prior_bars=state.to_dict()['source']['bars'],seed=False,
                wall_us=wall*1000000,monotonic_us=int(mono*1000000))
            state=accept(ga.prepare_decision(state,frame,history,source_inputs(wall,mono=mono,serial=i*2+1),ledger=ledger))
        if len(state.to_dict()['positions'])!=8: raise AssertionError('Recovery fixture did not hold eight positions')
        for i,price in ((902,'97.5'),(903,'101')):
            wall,mono=WALL+i,MONO+i
            frame=ga.source.make_frame(raw_capture(price=price,block=200+i,source_second=wall-2,wall=wall-1,mono=mono-1),
                prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=i),ledger=ledger))
        state=accept(ga.prepare_control(state,'recover',source_inputs(wall,mono=mono,serial=950),frame=frame,
            trip_id=state.to_dict()['engine']['lifecycle']['risk']['trip_id'],ledger=ledger))
        wall,mono=WALL+904,MONO+904
        frame=ga.source.make_frame(raw_capture(price='101',block=2000,source_second=wall-2,wall=wall-1,mono=mono-1),
            prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
        state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=951),ledger=ledger))
        state=accept(ga.prepare_decision(state,frame,None,source_inputs(wall,mono=mono,generation=1,serial=952),ledger=ledger))
        accept(ga.prepare_control(state,'stop',source_inputs(wall+1,serial=953),ledger=ledger))
    return rows


def protective_boundary_sequence(prefix,price,serial):
    rows=list(prefix); ledger=ga.SimulationLedger(OWNER,RUN)
    with deny_network():
        for candidate,_,_ in prefix: state=ledger.accept(candidate)
        wall,mono=WALL+902,MONO+902
        frame=ga.source.make_frame(raw_capture(price=price,block=4000,source_second=wall-2,wall=wall-1,mono=mono-1),
            prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
        for candidate in (ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=serial),ledger=ledger),):
            capture=cp.capture_owned_candidate(candidate)
            wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=90000000+serial)),previous=rows[-1][1])
            rows.append((candidate,capture,wire)); state=ledger.accept(candidate)
        stop=ga.prepare_control(state,'stop',source_inputs(wall+1,serial=serial+1),ledger=ledger)
        capture=cp.capture_owned_candidate(stop)
        rows.append((stop,capture,cp.prepare_transport(stop,capture,command_id=str(UUID(int=91000000+serial)),previous=rows[-1][1])))
    return rows


def expired_signal_sequence(prefix):
    rows=list(prefix); ledger=ga.SimulationLedger(OWNER,RUN)
    def accept(candidate):
        capture=cp.capture_owned_candidate(candidate)
        wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=92000000+candidate.state.revision)),previous=rows[-1][1])
        rows.append((candidate,capture,wire)); return ledger.accept(candidate)
    with deny_network():
        for candidate,_,_ in prefix: state=ledger.accept(candidate)
        wall,mono=WALL+1801,MONO+1801
        frame=ga.source.make_frame(raw_capture(price='100',block=5000,source_second=wall-2,wall=wall-1,mono=mono-1),
            prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
        state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=1400),ledger=ledger))
        state=accept(ga.prepare_decision(state,frame,None,source_inputs(wall,mono=mono,serial=1401),ledger=ledger))
        accept(ga.prepare_control(state,'stop',source_inputs(wall+1,serial=1402),ledger=ledger))
    return rows


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class CausalRiskSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SourceTransitionSqlTests.setUpClass.__func__(cls)
        try:
            cls.extras['recovery']=recovery_sequence()
            for i,(name,price) in enumerate((('stop_edge','97'),('stop_above','97.000000000000000001'),
                ('take_edge','107'),('take_below','106.999999999999999999'))):
                cls.extras[name]=protective_boundary_sequence(cls.extras['recovery'][:7],price,1200+i*10)
            cls.extras['expired_signal']=expired_signal_sequence(cls.extras['recovery'][:5])
            source=SQL.read_text(); cls.causal_sql_sha256=hashlib.sha256(source.encode()).hexdigest()
            denied=cls.db.sql(source,role=INSTALLER,check=False)
            if denied.returncode==0 or 'offline_causal_risk_fixture_required' not in denied.stderr:
                raise AssertionError('Causal artifact installed without offline guard')
            cls.db.sql("BEGIN; SET dashboard.causal_risk_fixture='offline-v1';"+source+'COMMIT;',role=INSTALLER)
            cls.db.sql(f'''REVOKE EXECUTE ON FUNCTION vn_source_research.validate_request(uuid,uuid,text) FROM {AUDITOR};
              GRANT USAGE ON SCHEMA vn_causal_research TO {AUDITOR};
              GRANT EXECUTE ON FUNCTION vn_causal_research.validate_request(uuid,uuid,text) TO {AUDITOR};''',role=INSTALLER)
        except BaseException:
            cls.db.close(); raise

    @classmethod
    def tearDownClass(cls): cls.db.close()

    setUp=SourceTransitionSqlTests.setUp
    seed=SourceTransitionSqlTests.seed
    prefix=SourceTransitionSqlTests.prefix
    snapshot=SourceTransitionSqlTests.snapshot
    reject=SourceTransitionSqlTests.reject
    phase=SourceTransitionSqlTests.phase
    audit=SourceTransitionSqlTests.audit
    block=SourceTransitionSqlTests.block

    def sql(self,wire):
        return 'SELECT vn_causal_research.validate_request('+','.join(
            (literal(OWNER),literal(RUN),literal(wire.decode())))+');'

    def reject_causal(self,body,expected=None):
        wire=numbers.encode(body)
        self.db.sql('SELECT vn_source_research.validate_request('+','.join(
            (literal(OWNER),literal(RUN),literal(wire.decode())))+');',role=INSTALLER)
        self.reject(body,expected)

    def test_complete_ordered_traces_and_recovery(self):
        count=0
        for name,rows in [('dense',self.samples),*self.extras.items()]:
            self.setUp()
            for i,row in enumerate(rows):
                with self.subTest(trace=name,index=i,kind=row[0].transition['evidence']['kind']):
                    before=self.snapshot(); result=self.audit(row[2])
                    self.assertEqual(result['format'],'ga-causal-risk-validation-research-v1')
                    self.assertEqual(self.snapshot(),before); self.seed(row); count+=1
        self.assertEqual(count,150)

    def test_expired_pending_signal_is_discarded_without_an_entry(self):
        rows=self.extras['expired_signal']; self.prefix(rows,len(rows)-2); row=rows[-2]
        self.assertEqual(sum(m['pending'] is not None for m in rows[4][0].state.to_dict()['engine']['members']),8)
        self.audit(row[2]); self.assertEqual(len(row[0].operations),0)
        self.assertEqual(len(row[0].state.to_dict()['positions']),0)
        self.assertTrue(all(m['pending'] is None for m in row[0].state.to_dict()['engine']['members']))

    def test_rehashed_duplicate_decision_fails_after_source_and_money_pass(self):
        index,row=next((i,r) for i,r in enumerate(self.samples) if r[0].transition['evidence']['kind']=='decision')
        self.prefix(self.samples,index+1); body=numbers.decode(row[2]); manifest=row[1].to_dict()
        body['command_id']=str(UUID(int=93939393)); body['prior']={'revision':manifest['revision'],'sha256':hashlib.sha256(numbers.encode(manifest)).hexdigest()}
        body['checkpoint']=deepcopy(manifest); body['checkpoint']['revision']+=1; body['components']=[]
        body['operations']=[]; body['evidence']['actions']=[]; body['events']=[]
        body['history']={'owner_id':OWNER,'run_id':RUN,'revision':body['checkpoint']['revision'],
            'allocated_ids':[],'closed_positions':[],'birth_members':[],'retired_accounts':[],'assessments':[],'selection':None}
        self.reject_causal(body,'causal_duplicate_or_paused_decision')

    def test_protective_exit_thresholds_are_inclusive_at_exact_decimal_units(self):
        for name,count in [('stop_edge',8),('stop_above',0),('take_edge',8),('take_below',0)]:
            rows=self.extras[name]; self.prefix(rows,len(rows)-2); row=rows[-2]
            self.audit(row[2]); self.assertEqual(sum(o['kind']=='close' for o in row[0].operations),count)
            self.assertEqual(len(row[0].state.to_dict()['positions']),8-count)
        rows=self.extras['stop_edge']; self.prefix(rows,len(rows)-2); body=numbers.decode(rows[-2][2])
        action=next(a for a in body['evidence']['actions'] if a['reason']=='stop_loss'); idx=action['operation_index']
        action['reason']='take_profit'; next(e for e in body['events'] if e['operation_index']==idx)['kind']='take_profit'
        self.reject_causal(body,'causal_required_operation_mismatch')

    def test_recovery_ack_and_baseline_cannot_be_changed_and_restart_is_later(self):
        rows=self.extras['recovery']; index=next(i for i,r in enumerate(rows) if r[0].transition['evidence']['control'] is not None
            and r[0].transition['evidence']['control']['action']=='recover')
        self.prefix(rows,index); body=numbers.decode(rows[index][2]); self.audit(rows[index][2])
        bad=deepcopy(body); bad['evidence']['control']['trip_id']=str(UUID(int=918273)); self.reject_causal(bad,'causal_recovery_eligibility')
        for field,value in [('baseline_equity','995'),('recovery_count',0),('last_recovered_at',WALL)]:
            bad=deepcopy(body); bad['checkpoint']['engine']['lifecycle']['risk'][field]=value; self.reject_causal(bad,'causal_lifecycle_after_mismatch')
        # The next owned decision restarts only after a distinct protective quote.
        restart=rows[-2][0]
        self.assertEqual(restart.state.to_dict()['engine']['generation'],1)
        self.assertGreater(restart.transition['evidence']['observation']['timestamp'],rows[index][0].transition['evidence']['observation']['timestamp'])

    def test_source_and_money_valid_recovery_below_original_boundary_fails(self):
        rows=self.extras['recovery']; self.prefix(rows,8)
        body=numbers.decode(rows[9][2]); prior=rows[7][1].to_dict(); at=rows[7][0].transition['evidence']['observation']['timestamp']
        body['prior']={'revision':prior['revision'],'sha256':hashlib.sha256(numbers.encode(prior)).hexdigest()}
        body['checkpoint']=deepcopy(prior); body['checkpoint']['revision']+=1; body['checkpoint']['status']='running'; body['components']=[]
        life=body['checkpoint']['engine']['lifecycle']; life.update(signals_after=at,last_control_at=at)
        life['risk'].update(active=False,recovery_count=1,last_recovered_at=at)
        inputs=deepcopy(rows[7][0].transition['evidence']['inputs']); inputs['provider']['phase']='control'
        body['evidence']['inputs']=inputs
        body['evidence']['observation']={'timestamp':at,'price':'97.5','candle_end':prior['source']['last_quote']['decision_second']//900*900,
            'candle_close':rows[7][0].state.to_dict()['source']['bars'][-1][1]}
        body['evidence']['observation']['candle_end']=rows[7][0].state.to_dict()['source']['bars'][-1][0]
        body['history'].update(revision=body['checkpoint']['revision'])
        for event in body['events']: event['at']=at
        self.reject_causal(body,'causal_recovery_original_boundary')

    def test_paid_data_free_stop_cannot_remove_holdings_or_fabricate_risk_updates(self):
        rows=self.extras['held_stop']; self.prefix(rows,len(rows)-1); body=numbers.decode(rows[-1][2]); self.audit(rows[-1][2])
        bad=deepcopy(body); bad['checkpoint']['engine']['lifecycle']['risk']['observed_at']+=1
        self.reject_causal(bad,'causal_lifecycle_after_mismatch')
        self.assertEqual(len(rows[-1][0].state.to_dict()['positions']),8)

    def test_source_and_economic_valid_member_pending_cursor_and_metrics_mutations_fail(self):
        index,row=next((i,r) for i,r in enumerate(self.samples) if any(m['pending'] for m in r[0].state.to_dict()['engine']['members']))
        self.prefix(self.samples,index); body=numbers.decode(row[2])
        for alter in (lambda m:m.update(pending=None),lambda m:m['pending'].update(signal_at=m['pending']['signal_at']-1),
            lambda m:m.update(cursor=m['cursor']+900),lambda m:m.update(peak_equity='101'),
            lambda m:m.update(max_drawdown={'numerator':'1','denominator':'100'})):
            bad=deepcopy(body); member=next(m for m in bad['checkpoint']['engine']['members'] if m['pending']); alter(member)
            self.reject_causal(bad,'causal_member_after_mismatch')

    def test_risk_latch_original_baseline_control_and_terminal_mutations_fail(self):
        rows=self.extras['recovery']; index=next(i for i,r in enumerate(rows) if r[0].state.to_dict()['status']=='risk_halted')
        self.prefix(rows,index); body=numbers.decode(rows[index][2])
        for field,value in [('observed_equity','1000'),('baseline_equity','999'),('trip_equity','999'),('tripped_at',WALL),('recovery_count',1)]:
            bad=deepcopy(body); bad['checkpoint']['engine']['lifecycle']['risk'][field]=value; self.reject_causal(bad)
        rows=self.extras['terminal']; index=len(rows)-2; self.prefix(rows,index); body=numbers.decode(rows[index][2])
        bad=deepcopy(body); member=bad['checkpoint']['engine']['members'][0]; member['terminal']['at']-=1
        retired=next(r for r in bad['history']['retired_accounts'] if r['member']['id']==member['id'])
        retired['member']['terminal']['at']=member['terminal']['at']
        self.reject_causal(bad,'causal_member_after_mismatch')

    def test_lifecycle_policy_and_retired_metrics_cannot_be_forged(self):
        row=self.samples[0]; body=numbers.decode(row[2])
        for field,value in [('account_loss_bps','0001'),('death_drawdown_bps','2001'),('max_lifespan_seconds',1)]:
            bad=deepcopy(body); self.block(row,bad,'configuration',lambda b:b['lifecycle_policy'].update({field:value}))
            self.reject_causal(bad,'causal_lifecycle_policy')
        index,row=self.phase('retire'); self.prefix(self.samples,index); body=numbers.decode(row[2])
        bad=deepcopy(body); bad['history']['retired_accounts'][0]['member']['peak_equity']='999'
        self.reject_causal(bad,'causal_retired_member_mismatch')

    def test_causal_action_reasons_and_signal_times_cannot_change(self):
        for kind in ('open','close'):
            index,row=self.phase(kind); self.prefix(self.samples,index); body=numbers.decode(row[2])
            idx=next(i for i,o in enumerate(body['operations']) if o['kind']==kind)
            for field,value in [('reason','death_liquidation'),('signal_at',WALL)]:
                bad=deepcopy(body); bad['evidence']['actions'][idx][field]=value
                if field=='reason':
                    event=next(e for e in bad['events'] if e['operation_index']==idx); event['kind']=value
                self.reject(bad)

    def test_limited_installer_wrapper_and_no_durable_writes(self):
        rows=json.loads(self.db.scalar("""SELECT json_agg(x) FROM (
          SELECT p.proname,r.rolname AS owner,p.prosecdef,p.proconfig FROM pg_proc p
          JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner
          WHERE n.nspname='vn_causal_research' ORDER BY p.proname)x;"""))
        self.assertEqual(len(rows),14)
        self.assertTrue(all(r['owner']==INSTALLER and r['proconfig']==['search_path=pg_catalog'] for r in rows))
        self.assertEqual([r['proname'] for r in rows if r['prosecdef']],['validate_request'])
        for role in ('anon','authenticated','service_role','vn_economic_relay'):
            self.assertNotEqual(self.db.sql(self.sql(self.samples[0][2]),role=role,check=False).returncode,0)
        for statement in ('SELECT * FROM vn_economic_research.allocated;',
            "SELECT vn_causal_research.transition('{}',NULL,'{}');",
            "SELECT vn_source_research.validate_request(NULL,NULL,'{}');"):
            self.assertNotEqual(self.db.sql(statement,role=AUDITOR,check=False).returncode,0)

    @unittest.skipUnless(os.environ.get('DASHBOARD_CAUSAL_RISK_MEASURE')=='1','Optional full semantic wrapper timing')
    def test_z_measure_complete_causal_boundary(self):
        largest=max(range(len(self.samples)),key=lambda i:len(self.samples[i][2]))
        recovery=self.extras['recovery']; recover_index=next(i for i,r in enumerate(recovery) if r[0].transition['evidence']['control'] is not None
            and r[0].transition['evidence']['control']['action']=='recover')
        chosen=[('bootstrap',self.samples,0),('quote',self.samples,1),('replacement',self.samples,largest),
            ('risk_trip',self.extras['risk'],len(self.extras['risk'])-2),('recovery',recovery,recover_index),
            ('held_stop',self.extras['held_stop'],len(self.extras['held_stop'])-1)]
        measured=[]
        for kind,rows,index in chosen:
            self.prefix(rows,index); wire=rows[index][2]; before=self.snapshot()
            source=['SET plan_cache_mode=force_generic_plan;','CREATE TEMP TABLE timings(elapsed_us bigint);',
                'DO $measure$ DECLARE t timestamptz;i integer;r jsonb;w text:='+literal(wire.decode())+
                '; BEGIN FOR i IN 1..10 LOOP t:=clock_timestamp(); r:=vn_causal_research.validate_request('+
                literal(OWNER)+','+literal(RUN)+',w); INSERT INTO timings VALUES(extract(epoch FROM clock_timestamp()-t)*1000000); END LOOP; END $measure$;',
                "SELECT json_build_object('samples',count(*),'p50_us',percentile_cont(.5) WITHIN GROUP(ORDER BY elapsed_us),'p95_us',percentile_cont(.95) WITHIN GROUP(ORDER BY elapsed_us),'maximum_us',max(elapsed_us)) FROM timings;"]
            timing=json.loads(self.db.scalar('\n'.join(source),role=AUDITOR,timeout=60))
            measured.append({'kind':kind,'wire_bytes':len(wire),**timing}); self.assertEqual(self.snapshot(),before)
        directory=ROOT/'db-contract/research'
        self.assertEqual(hashlib.sha256(SQL.read_bytes()).hexdigest(),self.causal_sql_sha256,'Installed SQL changed during measurement')
        artifact={'date':'2026-10-11','identity':self.db.identity,
            'sql_sha256':{name:hashlib.sha256((directory/name).read_bytes()).hexdigest()
                for name in ('numeric_wire.sql','locked_checkpoint.sql','economic_transition.sql','source_transition.sql','causal_risk.sql')},
            'scope':'offline independent economics/identities/source/indicators/causal actions/risk; no assessment/optimizer/lineage/commit authority',
            'complete_commands':150,'tables_in_new_artifact':0,'writes_by_validator':0,
            'warm_server_validation_timings':measured,
            'timing_method':'10 full volatile wrapper calls with wire variable/generic plans; unchanged fixture prior; includes three resolutions',
            'timing_exclusions':['transport/TLS','contended locks','assessment/optimizer/RNG/lineage semantics',
                'journal/identity reservation/pins/projections','final source/lease boundary','COMMIT/WAL/relay','hosted tails'],
            'production_grants_or_install':False}
        (ROOT/'research/causal-risk-measurements.json').write_text(json.dumps(artifact,indent=2,sort_keys=True)+'\n')
