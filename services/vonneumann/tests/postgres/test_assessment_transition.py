"""Independent SQL scoring/window proof using owned preparations, no decoder."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import random
import unittest
from uuid import UUID

from tests.postgres.harness import OPT_IN
from tests.postgres.test_causal_risk import CausalRiskSqlTests
from tests.postgres.test_economic_transition import INSTALLER, AUDITOR, extra_sequence
from tests.measure_provider_ga_research import literal
from tests.test_provider_contract import OWNER, RUN, EPOCH, WALL, MONO, END, source_inputs, raw_capture, raw_minutes
from tests.security_support import deny_network
from vonneumann.research import numeric_wire as numbers
from vonneumann.research import partitioned_checkpoint as cp, provider_ga_model as ga

ROOT=Path(__file__).resolve().parents[2]
SQL=ROOT/'db-contract/research/assessment_transition.sql'


def frozen_completion_sequence():
    rows=extra_sequence(death=True)[:-1]
    ledger=ga.SimulationLedger(OWNER,RUN)
    for row in rows: state=ledger.accept(row[0])
    previous=rows[-1][1]
    def accept(candidate):
        nonlocal previous
        capture=cp.capture_owned_candidate(candidate)
        wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=88_000_000+candidate.state.revision)),previous=previous)
        rows.append((candidate,capture,wire)); previous=capture
        return ledger.accept(candidate)
    with deny_network():
        for serial,offset in enumerate((1800,2700,3601),1700):
            wall,mono=WALL+offset,MONO+offset
            frame=ga.source.make_frame(raw_capture(price='101',block=serial,source_second=wall-2,wall=wall-1,mono=mono-1),
                prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=serial*2),ledger=ledger))
            history=ga.source.build_history(raw_minutes(end=END+(offset//900)*900,count=15,close='100',wall=wall-1,mono=mono-1),
                prior_bars=state.to_dict()['source']['bars'],seed=False,wall_us=wall*1_000_000,monotonic_us=int(mono*1_000_000))
            state=accept(ga.prepare_decision(state,frame,history,source_inputs(wall,mono=mono,generation=1,serial=serial*2+1),ledger=ledger))
        accept(ga.prepare_control(state,'stop',source_inputs(wall+1,serial=1800),ledger=ledger))
    return rows


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class AssessmentTransitionSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CausalRiskSqlTests.setUpClass.__func__(cls)
        try:
            cls.extras['frozen_completion']=frozen_completion_sequence()
            source=SQL.read_text(); cls.assessment_sql_sha256=hashlib.sha256(source.encode()).hexdigest()
            cls.installed_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in SQL.parent.glob('*.sql')}
            denied=cls.db.sql(source,role=INSTALLER,check=False)
            if denied.returncode==0 or 'offline_assessment_fixture_required' not in denied.stderr:
                raise AssertionError('Assessment artifact installed without guard')
            cls.db.sql("BEGIN; SET dashboard.assessment_fixture='offline-v1';"+source+'COMMIT;',role=INSTALLER)
            cls.db.sql(f'''REVOKE EXECUTE ON FUNCTION vn_causal_research.validate_request(uuid,uuid,text) FROM {AUDITOR};
              GRANT USAGE ON SCHEMA vn_assessment_research TO {AUDITOR};
              GRANT EXECUTE ON FUNCTION vn_assessment_research.validate_request(uuid,uuid,text) TO {AUDITOR};''',role=INSTALLER)
        except BaseException:
            cls.db.close(); raise

    @classmethod
    def tearDownClass(cls): cls.db.close()

    setUp=CausalRiskSqlTests.setUp
    seed=CausalRiskSqlTests.seed
    prefix=CausalRiskSqlTests.prefix
    snapshot=CausalRiskSqlTests.snapshot
    reject=CausalRiskSqlTests.reject
    phase=CausalRiskSqlTests.phase
    audit=CausalRiskSqlTests.audit
    block=CausalRiskSqlTests.block

    def sql(self,wire):
        return 'SELECT vn_assessment_research.validate_request('+','.join((literal(OWNER),literal(RUN),literal(wire.decode())))+');'

    def reject_assessment(self,body,expected=None):
        self.db.sql('SELECT vn_causal_research.validate_request('+','.join(
            (literal(OWNER),literal(RUN),literal(numbers.encode(body).decode())))+');',role=INSTALLER)
        self.reject(body,expected)

    def finalized(self,rows):
        return next((i,r) for i,r in enumerate(rows) if r[0].history['assessments'])

    def test_complete_ordered_captures_all_economic_source_risk_traces(self):
        count=0; finalized=0; frozen=0
        for name,rows in [('dense',self.samples),*self.extras.items()]:
            self.setUp()
            for i,row in enumerate(rows):
                with self.subTest(trace=name,index=i):
                    before=self.snapshot(); result=self.audit(row[2])
                    self.assertEqual(result['format'],'ga-assessment-validation-research-v1')
                    self.assertNotIn('trace',result['causal_evidence'])
                    self.assertFalse(result['assessment_evidence']['optimizer_rng_lineage_verified'])
                    self.assertEqual(self.snapshot(),before); self.seed(row); count+=1
                    finalized+=int(result['assessment_evidence']['finalized_count']['$integer'])
                    frozen+=int(result['assessment_evidence']['new_frozen_count']['$integer'])
        self.assertEqual(count,165); self.assertGreaterEqual(finalized,80); self.assertGreaterEqual(frozen,16)

    def test_finalized_metrics_policy_identity_order_and_scores_are_independent(self):
        index,row=self.finalized(self.samples); self.prefix(self.samples,index); body=numbers.decode(row[2]); self.audit(row[2])
        mutations=[lambda r:r.update(owner_id=str(UUID(int=123))),lambda r:r.update(run_id=str(UUID(int=124))),
            lambda r:r.update(finalized_revision=r['finalized_revision']-1),lambda r:r.update(finalized_at=r['finalized_at']-1),
            lambda r:r.update(iteration_id=RUN+':100'),lambda r:r.update(evaluation_id=RUN+':0:100'),
            lambda r:r.update(member_index=7),lambda r:r.update(probe_id=str(UUID(int=125))),lambda r:r.update(generation=99),
            lambda r:r.update(reason='drawdown'),lambda r:r.update(selection_eligible=False),lambda r:r.update(cohort_complete=False),
            lambda r:r.update(measurement_basis='interrupted-unscored-snapshot'),lambda r:r.update(early_terminal_frozen=True),
            lambda r:r.update(roi_float64='0x1.0000000000000p+0'),lambda r:r.update(fitness_float64='0x1.0000000000000p+0'),
            lambda r:r['metrics'].update(cash_balance='1'),lambda r:r['metrics'].update(terminal_cash='1'),
            lambda r:r['metrics'].update(has_open_position=True),lambda r:r['metrics'].update(initial_cash='1'),
            lambda r:r['metrics'].update(peak_equity='1'),lambda r:r['metrics'].update(max_drawdown={'numerator':'1','denominator':'100'}),
            lambda r:r['metrics'].update(roi_ratio={'numerator':'1','denominator':'100'}),
            lambda r:r['metrics'].update(roi_float64='0x1.0000000000000p+0'),
            lambda r:r['metrics'].update(fitness_float64='0x1.0000000000000p+0'),
            lambda r:r['metrics'].update(closed_trade_count=100),lambda r:r['metrics'].update(captured_revision=1),
            lambda r:r['metrics'].update(captured_at=1),lambda r:r['metrics']['source'].update(sequence=0),
            lambda r:r['fitness_policy'].update(drawdown_weight={'float64':'0x1.8000000000000p+1'}),
            lambda r:r['evaluation_policy'].update(early_terminal='discard'),lambda r:r['execution'].update(version='unknown'),
            lambda r:r.update(window_started_at=None),lambda r:r.update(window_ends_at=None),
            lambda r:r.update(window_source_start=None),lambda r:r['window_source_end'].update(at=1)]
        for i,alter in enumerate(mutations):
            with self.subTest(mutation=i):
                bad=deepcopy(body); alter(bad['history']['assessments'][0]); self.assertNotEqual(body,bad)
                self.reject_assessment(bad,'assessment_finalized_records_mismatch')
        for records in (body['history']['assessments'][:-1],list(reversed(body['history']['assessments'])),
            [body['history']['assessments'][0]]*8):
            bad=deepcopy(body); bad['history']['assessments']=deepcopy(records); self.reject_assessment(bad)

    def test_common_window_deadline_policy_results_and_source_start_cannot_be_rehashed(self):
        index,row=next((i,r) for i,r in enumerate(self.samples) if r[0].transition['evidence']['kind']=='decision'
            and r[0].state.to_dict()['engine']['cohort']['phase']=='evaluating')
        self.prefix(self.samples,index); body=numbers.decode(row[2])
        bad=deepcopy(body); self.block(row,bad,'cohort',lambda c:c.update(iteration_id='foreign')); self.reject(bad,'checkpoint_model_identity')
        for field,value in [('horizon_seconds',{'float64':(900.0).hex()}),
            ('started_at',None),('ends_at',{'float64':float(WALL+900).hex()}),('completed_at',{'float64':float(WALL).hex()}),
            ('abort_reason','stopped'),('completed_count',8),('evaluations',[{'invented':True}])]:
            bad=deepcopy(body); self.block(row,bad,'cohort',lambda c:c.update({field:value})); self.reject_assessment(bad,'assessment_common_window_mismatch')
        bad=deepcopy(body); bad['checkpoint']['engine']['cohort_source']['sequence']=0; self.reject_assessment(bad)

    def test_unscored_stop_keeps_original_holdings_and_cash_without_mark_refresh(self):
        rows=self.extras['held_stop']; self.prefix(rows,len(rows)-1); body=numbers.decode(rows[-1][2]); self.audit(rows[-1][2])
        records=body['history']['assessments']; self.assertEqual(len(records),8)
        self.assertTrue(all(r['metrics']['has_open_position'] and r['metrics']['terminal_cash'] is None for r in records))
        self.assertTrue(all(r['fitness_float64'] is None and r['metrics']['roi_ratio'] is None for r in records))
        for alter in (lambda r:r.update(selection_eligible=True),lambda r:r['metrics'].update(terminal_cash=r['metrics']['cash_balance']),
            lambda r:r['metrics'].update(roi_ratio={'numerator':'0','denominator':'1'}),lambda r:r['metrics'].update(fitness_float64='0x0.0p+0')):
            bad=deepcopy(body); alter(bad['history']['assessments'][0]); self.reject_assessment(bad)

    def test_first_risk_abort_is_captured_before_later_same_command_liquidation(self):
        rows=self.extras['risk']; index,row=self.finalized(rows); self.prefix(rows,index); self.audit(row[2]); body=numbers.decode(row[2])
        record=body['history']['assessments'][0]; after=row[0].state.to_dict()['engine']['members'][0]
        self.assertTrue(record['metrics']['has_open_position']); self.assertEqual(record['metrics']['closed_trade_count'],0)
        self.assertEqual(after['num_trades'],1); self.assertIsNone(after['assessment'])
        bad=deepcopy(body); bad['history']['assessments'][0]['metrics']['closed_trade_count']=1; self.reject_assessment(bad)
        # Aborted placeholder results have zero trades; economics lives in the
        # withheld record. An early completed result, when present, stays frozen.
        bad=deepcopy(body); self.block(row,bad,'cohort',lambda c:c['evaluations'][0].update(num_trades=1)); self.reject_assessment(bad)

    def test_assessment_event_is_required_once_at_the_actual_capture_point(self):
        for rows in (self.samples,self.extras['risk'],self.extras['controls'],self.extras['held_stop']):
            index,row=self.finalized(rows); self.prefix(rows,index); body=numbers.decode(row[2]); self.audit(row[2])
            pointer=next(i for i,e in enumerate(body['events']) if e['operation_index'] is None)
            for events in (body['events'][:pointer]+body['events'][pointer+1:],
                body['events'][:pointer]+[body['events'][pointer]]+body['events'][pointer:],
                [e for e in body['events'] if e['operation_index'] is not None]+[body['events'][pointer]]):
                bad=deepcopy(body); bad['events']=deepcopy(events); self.assertNotEqual(body,bad)
                self.reject_assessment(bad,'assessment_event_order_mismatch')
            bad=deepcopy(body); bad['events'][pointer]['kind']='evaluation' if bad['events'][pointer]['kind']=='evaluation_aborted' else 'evaluation_aborted'
            self.reject_assessment(bad,'assessment_event_order_mismatch')
        self.prefix(self.samples,1); body=numbers.decode(self.samples[1][2])
        bad=deepcopy(body); bad['events'].append({'kind':'evaluation','at':WALL+1,'account_id':None,'position_id':None,'operation_index':None})
        self.reject_assessment(bad,'assessment_event_order_mismatch')

    def test_terminal_frozen_snapshot_survives_deadline_and_aborted_withholding(self):
        for name in ('frozen_completion','terminal'):
            rows=self.extras[name]; index=next(i for i,r in enumerate(rows) if any(m['assessment'] for m in r[0].state.to_dict()['engine']['members']))
            self.prefix(rows,index); row=rows[index]; self.audit(row[2]); body=numbers.decode(row[2])
            bad=deepcopy(body); bad['checkpoint']['engine']['members'][0]['assessment']['cash_balance']='1'
            bad['history']['retired_accounts'][0]['member']['assessment']['cash_balance']='1'; self.reject_assessment(bad,'assessment_member_frozen_mismatch')
            for final_index in range(index+1,len(rows)):
                self.seed(rows[final_index-1]); self.audit(rows[final_index][2])
                records=rows[final_index][0].history['assessments']
                if not records: continue
                if records[0]['iteration_id']!=row[0].state.to_dict()['engine']['cohort']['iteration_id']:
                    continue  # A later Stop withholds the new warming cohort.
                self.assertTrue(all(r['early_terminal_frozen'] for r in records))
                self.assertTrue(all(r['metrics']['captured_revision']<r['finalized_revision'] for r in records))
                bad=numbers.decode(rows[final_index][2]); bad['history']['assessments'][0]['metrics']['captured_at']=bad['history']['assessments'][0]['finalized_at']
                self.reject_assessment(bad)
                if name=='frozen_completion':
                    self.assertTrue(all(r['status']=='completed' and r['reason']=='drawdown' for r in records))
                else: self.assertTrue(all(r['status']=='aborted' and r['metrics']['roi_float64'] is None for r in records))

    def test_finalization_is_emitted_once_and_frozen_evaluations_cannot_change(self):
        rows=self.extras['terminal']; self.prefix(rows,len(rows)-1); body=numbers.decode(rows[-1][2])
        bad=deepcopy(body); self.block(rows[-1],bad,'cohort',lambda c:c['evaluations'][0].update(fitness={'float64':'0x1.0000000000000p+0'}))
        self.reject_assessment(bad,'assessment_common_window_mismatch')
        rows=self.extras['recovery']; index=next(i for i,r in enumerate(rows) if r[0].transition['evidence']['kind']=='protective'
            and i>7 and r[0].state.to_dict()['status']=='risk_halted')
        self.prefix(rows,index); body=numbers.decode(rows[index][2]); self.assertEqual(body['history']['assessments'],[])
        bad=deepcopy(body); bad['history']['assessments']=deepcopy(rows[7][0].history['assessments']); self.reject_assessment(bad)

    def test_independent_binary64_fitness_matches_fraction_cash_and_drawdown_rounding(self):
        rng=random.Random(74731); statements=[]
        for _ in range(160):
            initial=rng.randrange(1,10**55); cash=rng.randrange(0,initial*3); roi=Fraction(cash-initial,initial)
            drawdown=Fraction(rng.randrange(0,initial+1),initial); fitness=float(roi)-2.0*float(drawdown)
            account={'cash':ga.base._text(cash,36),'initial_cash':ga.base._text(initial,36)}
            member={'peak_equity':account['initial_cash'],'max_drawdown':{'numerator':str(drawdown.numerator),'denominator':str(drawdown.denominator)},'num_trades':0}
            state={'revision':1,'source':{'epoch':EPOCH,'quote_sequence':0,'bars':[[END,'1','hash']],'last_quote':None},'engine':{'ema':{'count':61}}}
            args=','.join(literal(numbers.encode(v).decode())+'::jsonb' for v in (member,account,None,state,0))
            statements.append('SELECT vn_assessment_research.snapshot('+args+") ->> 'fitness_float64' = "+literal(fitness.hex())+';')
        self.assertEqual(self.db.sql('\n'.join(statements),role=INSTALLER).stdout.splitlines(),['t']*160)

    def test_private_installer_functions_and_client_denial(self):
        rows=json.loads(self.db.scalar("""SELECT json_agg(x) FROM (SELECT p.proname,r.rolname AS owner,p.prosecdef,p.proconfig
          FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner
          WHERE n.nspname='vn_assessment_research' ORDER BY p.proname)x;"""))
        self.assertEqual(len(rows),10); self.assertTrue(all(r['owner']==INSTALLER and r['proconfig']==['search_path=pg_catalog'] for r in rows))
        self.assertEqual([r['proname'] for r in rows if r['prosecdef']],['validate_request'])
        for role in ('anon','authenticated','service_role','vn_economic_relay'):
            self.assertNotEqual(self.db.sql(self.sql(self.samples[0][2]),role=role,check=False).returncode,0)
        for statement in ("SELECT vn_assessment_research.transition('{}',NULL,'{}','{}');",
            "SELECT vn_causal_research.capture_finalization('{}','stopped',true);",'SELECT * FROM vn_dependency_research.checkpoints;'):
            self.assertNotEqual(self.db.sql(statement,role=AUDITOR,check=False).returncode,0)

    @unittest.skipUnless(os.environ.get('DASHBOARD_ASSESSMENT_MEASURE')=='1','Optional full assessment timing')
    def test_z_measure_full_boundary(self):
        largest=max(range(len(self.samples)),key=lambda i:len(self.samples[i][2])); measured=[]
        chosen=[('bootstrap',self.samples,0),('quote',self.samples,1),('replacement',self.samples,largest),
            ('early_terminal',self.extras['terminal'],len(self.extras['terminal'])-2),
            ('risk_trip',self.extras['risk'],len(self.extras['risk'])-2),
            ('frozen_completion',self.extras['frozen_completion'],len(self.extras['frozen_completion'])-2),
            ('held_stop',self.extras['held_stop'],len(self.extras['held_stop'])-1)]
        for kind,rows,index in chosen:
            self.prefix(rows,index); wire=rows[index][2]; before=self.snapshot()
            statements=['SET plan_cache_mode=force_generic_plan;','CREATE TEMP TABLE timings(elapsed_us bigint);',
                'DO $m$ DECLARE t timestamptz;i integer;r jsonb;w text:='+literal(wire.decode())+
                '; BEGIN FOR i IN 1..10 LOOP t:=clock_timestamp();r:=vn_assessment_research.validate_request('+
                literal(OWNER)+','+literal(RUN)+',w); INSERT INTO timings VALUES(extract(epoch FROM clock_timestamp()-t)*1000000); END LOOP; END $m$;',
                "SELECT json_build_object('samples',count(*),'p50_us',percentile_cont(.5) WITHIN GROUP(ORDER BY elapsed_us),'p95_us',percentile_cont(.95) WITHIN GROUP(ORDER BY elapsed_us),'maximum_us',max(elapsed_us)) FROM timings;"]
            measured.append({'kind':kind,'wire_bytes':len(wire),**json.loads(self.db.scalar('\n'.join(statements),role=AUDITOR,timeout=60))})
            self.assertEqual(self.snapshot(),before)
        self.assertEqual({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in SQL.parent.glob('*.sql')},self.installed_sha256)
        artifact={'date':'2026-10-11','identity':self.db.identity,'sql_sha256':self.installed_sha256,
            'complete_commands':165,'tables_in_new_artifact':0,'writes_by_validator':0,'production_grants_or_install':False,
            'scope':'economics/source/causal/risk/assessments/common-window; optimizer/RNG/lineage pending',
            'warm_server_validation_timings':measured,'timing_method':'10 volatile full wrapper calls; generic plans; unchanged fixture prior; three resolutions',
            'timing_exclusions':['transport/TLS','contended locks','optimizer/RNG/lineage semantics','native journal/identity insertion/pins/projections',
                'final source/lease boundary','COMMIT/WAL/relay','hosted tails']}
        (ROOT/'research/assessment-transition-measurements.json').write_text(json.dumps(artifact,indent=2,sort_keys=True)+'\n')
