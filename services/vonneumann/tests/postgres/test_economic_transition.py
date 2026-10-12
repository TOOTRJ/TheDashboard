"""Actual independent economic/identity checks; no hosted DB or commit API."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import random
import time
import unittest
from uuid import UUID

from tests.postgres.harness import IsolatedPostgres, OPT_IN
from tests.measure_provider_ga_research import literal
from tests.test_partitioned_checkpoint import partition_trace
from tests.test_provider_contract import (OWNER,RUN,WORKER,EPOCH,WALL,MONO,END,
    source_inputs,seed_bundle,raw_capture,raw_minutes)
from tests.security_support import deny_network
from vonneumann.core.decimal_execution import DecimalExecutionConfig,EntryPlan,ExitPlan,_text
from vonneumann.research import numeric_wire as numbers
from vonneumann.research import partitioned_checkpoint as cp, provider_ga_model as ga

ROOT=Path(__file__).resolve().parents[2]
DIRECTORY=ROOT/'db-contract'/'research'
SQL=DIRECTORY/'economic_transition.sql'
INSTALLER='vn_economic_installer'
AUDITOR='vn_economic_auditor'


def extra_sequence(*,risk_bps='9000',cost=DecimalExecutionConfig(),death=False,controls=False):
    """Literal provider evidence, exact owned preparations and complete history."""
    rows=[]; previous=None
    ledger=ga.SimulationLedger(OWNER,RUN)
    def accept(candidate):
        nonlocal previous
        capture=cp.capture_owned_candidate(candidate)
        wire=cp.prepare_transport(candidate,capture,
            command_id=str(UUID(int=50_000_000+candidate.state.revision)),previous=previous)
        rows.append((candidate,capture,wire))
        previous=capture
        return ledger.accept(candidate)
    with deny_network():
        state=accept(ga.bootstrap(ga.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',
            source_epoch=EPOCH,execution=cost,account_loss_bps=risk_bps),
            seed_bundle(last_close='80'),source_inputs(WALL),ledger=ledger))
        offsets=(1,900,901) if death or controls else (1,900,901,1800,1801,2700,2701,3600,3601)
        for serial,offset in enumerate(offsets,1):
            wall,mono=WALL+offset,MONO+offset
            frame=ga.source.make_frame(raw_capture(price='101.234567890123456789',
                block=100+serial,source_second=wall-2,wall=wall-1,mono=mono-1),
                prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=serial*2),ledger=ledger))
            history=None if offset%900 else ga.source.build_history(
                raw_minutes(end=END+offset,count=15,close='120' if offset//900%2 else '80',
                    wall=wall-1,mono=mono-1),prior_bars=state.to_dict()['source']['bars'],
                seed=False,wall_us=wall*1_000_000,monotonic_us=int(mono*1_000_000))
            state=accept(ga.prepare_decision(state,frame,history,
                source_inputs(wall,mono=mono,generation=state.to_dict()['engine']['generation']+1,serial=serial*2+1),ledger=ledger))
        if death:
            wall,mono=WALL+902,MONO+902
            frame=ga.source.make_frame(raw_capture(price='0.1',block=105,source_second=wall-2,
                wall=wall-1,mono=mono-1),prior_source=state.to_dict()['source'],epoch=EPOCH,
                wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=80),ledger=ledger))
        if controls:
            at=state.to_dict()['engine']['last_quote']['timestamp']
            state=accept(ga.prepare_control(state,'pause',source_inputs(at+1,serial=900),ledger=ledger))
            state=accept(ga.prepare_control(state,'resume',source_inputs(at+2,serial=901),ledger=ledger))
            wall,mono=at+3,MONO+905
            frame=ga.source.make_frame(raw_capture(price='101.234567890123456789',block=200,
                source_second=wall-2,wall=wall-1,mono=mono-1),prior_source=state.to_dict()['source'],
                epoch=EPOCH,wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=902),ledger=ledger))
            state=accept(ga.prepare_decision(state,frame,None,
                source_inputs(wall,mono=mono,generation=1,serial=903),ledger=ledger))
        at=state.to_dict()['engine']['last_quote']['timestamp']+1
        accept(ga.prepare_control(state,'stop',source_inputs(at,serial=904),ledger=ledger))
    return rows


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class EconomicTransitionSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples=[]
        partition_trace(True,windows=2,observer=lambda c,o,ow,p,w:cls.samples.append((c,p,w)))
        cls.extras={'cost':extra_sequence(cost=DecimalExecutionConfig('2.123456','15.000001','7.765432')),
            'terminal':extra_sequence(death=True),'risk':extra_sequence(death=True,risk_bps='1000'),
            'controls':extra_sequence(controls=True)}
        ledger=ga.SimulationLedger(OWNER,RUN); held=[]
        with deny_network():
            for row in cls.samples:
                state=ledger.accept(row[0]); held.append(row)
                if state.to_dict()['positions']: break
            at=state.to_dict()['engine']['last_quote']['timestamp']+1
            stop=ga.prepare_control(state,'stop',source_inputs(at,serial=999),ledger=ledger)
            capture=cp.capture_owned_candidate(stop)
            held.append((stop,capture,cp.prepare_transport(stop,capture,
                command_id=str(UUID(int=60_000_000)),previous=held[-1][1])))
        cls.extras['held_stop']=held
        cls.db=IsolatedPostgres().start()
        try:
            cls.db.sql(f'''CREATE ROLE {INSTALLER} LOGIN NOSUPERUSER NOCREATEDB
              NOCREATEROLE NOINHERIT NOBYPASSRLS;
              CREATE ROLE {AUDITOR} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
              CREATE ROLE vn_economic_relay LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
              GRANT CREATE ON DATABASE postgres TO {INSTALLER};''')
            denied=cls.db.sql(SQL.read_text(),role=INSTALLER,check=False)
            if denied.returncode==0 or 'offline_economic_transition_fixture_required' not in denied.stderr:
                raise AssertionError('Economic artifact installed without guard')
            source="BEGIN; SET dashboard.numeric_wire_fixture='offline-v1';"+(DIRECTORY/'numeric_wire.sql').read_text()
            source+="SET dashboard.locked_checkpoint_fixture='offline-v1';"+(DIRECTORY/'locked_checkpoint.sql').read_text()
            source+="SET dashboard.economic_transition_fixture='offline-v1';"+SQL.read_text()+'COMMIT;'
            cls.db.sql(source,role=INSTALLER)
            cls.db.sql(f'''GRANT USAGE ON SCHEMA vn_economic_research TO {AUDITOR};
              GRANT EXECUTE ON FUNCTION vn_economic_research.validate_request(uuid,uuid,text) TO {AUDITOR};''',role=INSTALLER)
        except BaseException:
            cls.db.close(); raise

    @classmethod
    def tearDownClass(cls): cls.db.close()

    def setUp(self):
        self.db.sql('DELETE FROM vn_economic_research.allocated; DELETE FROM vn_dependency_research.components; DELETE FROM vn_dependency_research.checkpoints;')
        self.db.sql(f'INSERT INTO vn_dependency_research.checkpoints VALUES({literal(RUN)},{literal(OWNER)},1,NULL);')

    def sql(self,wire):
        return 'SELECT vn_economic_research.validate_request('+','.join(
            (literal(OWNER),literal(RUN),literal(wire.decode())))+');'

    def audit(self,wire):
        return json.loads(self.db.scalar(self.sql(wire),role=AUDITOR))

    def seed(self,row):
        candidate,capture,_=row
        components=','.join('('+','.join((literal(OWNER),literal(RUN),literal(b.identity),
            literal(b._wire.decode())))+')' for b in capture.components)
        roles={op['id']:'account' if op['kind']=='birth' else 'position'
            for op in candidate.operations if op['kind'] in ('birth','open')}
        before=candidate.transition['before']
        old=None if before is None else before['engine']['lifecycle']['risk']['trip_id']
        new=candidate.state.to_dict()['engine']['lifecycle']['risk']['trip_id']
        if new is not None and new!=old: roles[new]='risk'
        self.assertEqual(set(roles),set(candidate.history['allocated_ids']))
        statements=['BEGIN;',f'INSERT INTO vn_dependency_research.components VALUES {components} ON CONFLICT DO NOTHING;']
        if roles:
            identities=','.join('('+','.join((literal(i),literal(OWNER),literal(RUN),literal(kind),
                str(candidate.state.revision)))+')' for i,kind in roles.items())
            statements.append(f'INSERT INTO vn_economic_research.allocated VALUES {identities};')
        statements.append(f"UPDATE vn_dependency_research.checkpoints SET revision={capture.to_dict()['revision']},manifest_wire={literal(numbers.encode(capture.to_dict()).decode())} WHERE run_id={literal(RUN)}; COMMIT;")
        self.db.sql('\n'.join(statements))

    def prefix(self,rows,index):
        self.setUp()
        for row in rows[:index]: self.seed(row)

    def snapshot(self):
        return self.db.scalar("""SELECT jsonb_build_object(
          'checkpoints',(SELECT jsonb_agg(to_jsonb(c) ORDER BY run_id) FROM vn_dependency_research.checkpoints c),
          'components',(SELECT jsonb_agg(to_jsonb(c) ORDER BY sha256) FROM vn_dependency_research.components c),
          'identities',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM vn_economic_research.allocated c));""")

    def reject(self,body,expected=None):
        before=self.snapshot()
        wire=body if type(body) is bytes else numbers.encode(body)
        denied=self.db.sql(self.sql(wire),role=AUDITOR,check=False)
        self.assertNotEqual(denied.returncode,0)
        if expected: self.assertIn(expected,denied.stderr)
        self.assertEqual(self.snapshot(),before)

    def phase(self,kind,rows=None):
        rows=self.samples if rows is None else rows
        return next((i,r) for i,r in enumerate(rows) if any(op['kind']==kind for op in r[0].operations))

    def test_all_complete_commands_replay_money_holdings_and_history_without_writes(self):
        total=0
        for name,rows in [('dense',self.samples),*self.extras.items()]:
            self.setUp()
            for row in rows:
                candidate,capture,wire=row; before=self.snapshot()
                result=self.audit(wire)
                self.assertEqual(result['command_sha256'],hashlib.sha256(wire).hexdigest())
                self.assertEqual(result['following_sha256'],hashlib.sha256(numbers.encode(capture.to_dict())).hexdigest())
                self.assertEqual(result['economic_evidence']['reserve'],candidate.state.to_dict()['reserve'])
                self.assertEqual(result['economic_evidence']['closed_count'],len(candidate.history['closed_positions']))
                self.assertEqual(set(result['economic_evidence']['allocated']),set(candidate.history['allocated_ids']))
                self.assertEqual(self.snapshot(),before)
                self.seed(row); total+=1
        self.assertGreater(total,70)
        self.assertTrue(any(c.history['retired_accounts'] for c,_,_ in self.extras['terminal']))
        self.assertTrue(any(c.state.to_dict()['engine']['lifecycle']['risk']['trip_id'] for c,_,_ in self.extras['risk']))
        self.assertEqual(self.extras['controls'][-2][0].state.to_dict()['engine']['generation'],1)
        self.assertEqual(len(self.extras['controls'][-1][0].state.to_dict()['positions']),0)

    def test_limited_installer_private_helpers_and_only_validator_capability(self):
        rows=json.loads(self.db.scalar("""SELECT json_agg(x) FROM (
          SELECT p.proname,r.rolname AS owner,p.prosecdef,p.proconfig FROM pg_proc p
          JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner
          WHERE n.nspname='vn_economic_research' ORDER BY p.proname)x;"""))
        self.assertEqual(len(rows),9)
        self.assertTrue(all(r['owner']==INSTALLER and r['proconfig']==['search_path=pg_catalog'] for r in rows))
        self.assertEqual([r['proname'] for r in rows if r['prosecdef']],['validate_request'])
        for role in ('anon','authenticated','service_role','vn_economic_relay'):
            self.assertNotEqual(self.db.sql(self.sql(self.samples[0][2]),role=role,check=False).returncode,0)
        for statement in ('SELECT * FROM vn_economic_research.allocated;',
            'SELECT * FROM vn_dependency_research.checkpoints;',
            "SELECT vn_economic_research.units('\"1\"',36);",
            "SELECT vn_dependency_research.resolve_request(NULL,NULL,'{}');",
            'CREATE SCHEMA forbidden_economic_schema;'):
            self.assertNotEqual(self.db.sql(statement,role=AUDITOR,check=False).returncode,0)

    def test_independent_entry_exit_arithmetic_in_128_seeded_fractional_cases(self):
        rng=random.Random(1103)
        for index in range(128):
            cfg=DecimalExecutionConfig(_text(rng.randrange(1,10**8),6),
                _text(rng.randrange(10**7),6),_text(rng.randrange(10**7),6))
            budget=_text(rng.randrange(10**30,10**38),36)
            price=_text(rng.randrange(10**16,10**22),18)
            entry=EntryPlan(budget,price,cfg)
            exit_plan=ExitPlan(entry,_text(rng.randrange(10**16,10**22),18))
            for function,args,expected in (
                ('entry',[entry.to_dict()],entry.to_dict()),
                ('exit',[exit_plan.to_dict(),entry.to_dict()],exit_plan.to_dict())):
                result=self.db.scalar('SELECT vn_economic_research.'+function+'('+
                    ','.join(literal(numbers.encode(a).decode())+'::jsonb' for a in args)+');',role=INSTALLER)
                self.assertEqual(json.loads(result),json.loads(numbers.encode(expected)))
        for text in ('01','1.0','+1','-0','1e1','NaN','0.'+'1'*37,'1'+'0'*37):
            result=self.db.sql('SELECT vn_economic_research.units('+literal(json.dumps(text))+'::jsonb,36);',role=INSTALLER,check=False)
            self.assertNotEqual(result.returncode,0)

    def test_well_hashed_reserve_and_account_manipulation_are_rejected(self):
        body=numbers.decode(self.samples[0][2])
        for alter in (lambda b:b['checkpoint'].update(reserve='201'),
            lambda b:b['checkpoint']['accounts'][0].update(cash='101'),
            lambda b:b['checkpoint']['accounts'][0].update(initial_cash='99'),
            lambda b:b['checkpoint']['accounts'][0].update(retired=True),
            lambda b:b['checkpoint']['accounts'].reverse(),
            lambda b:b['checkpoint']['accounts'][0].update(cash='100.0'),
            lambda b:b['checkpoint']['accounts'][0].update(cash=True)):
            bad=deepcopy(body); alter(bad); self.reject(bad)

    def test_tampered_fill_units_costs_budget_and_original_entry_fail(self):
        for kind in ('open','close'):
            index,row=self.phase(kind,self.extras['cost'])
            self.prefix(self.extras['cost'],index)
            body=numbers.decode(row[2]); i=next(i for i,o in enumerate(body['operations']) if o['kind']==kind)
            for field in ('quantity','notional','fee','fill_price',
                          'cash_debit' if kind=='open' else 'cash_credit'):
                bad=deepcopy(body); bad['operations'][i]['execution'][field]='1'
                self.reject(bad)
            bad=deepcopy(body)
            if kind=='open':
                original=bad['operations'][i]['execution']
                plan=EntryPlan('50',original['reference_price'],DecimalExecutionConfig.from_dict(original['config']))
                bad['operations'][i].update(execution=plan.to_dict(),quantity=plan.quantity,
                    notional=plan.notional,fee=plan.fee)
            else:
                bad['operations'][i]['execution']['entry']['reference_price']='999'
            self.reject(bad)

    def test_closed_and_retired_snapshots_cannot_be_omitted_reordered_or_changed(self):
        index,row=self.phase('retire'); self.prefix(self.samples,index)
        body=numbers.decode(row[2])
        self.assertTrue(body['history']['closed_positions'])
        for alter in (lambda b:b['history']['closed_positions'].pop(),
            lambda b:b['history']['closed_positions'].reverse(),
            lambda b:b['history']['closed_positions'][0]['exit'].update(net_pnl='1'),
            lambda b:b['history']['retired_accounts'].pop(),
            lambda b:b['history']['retired_accounts'].reverse(),
            lambda b:b['history']['retired_accounts'][0]['account'].update(cash='0'),
            lambda b:b['history']['retired_accounts'][0]['member'].update(num_trades=0)):
            bad=deepcopy(body); alter(bad); self.reject(bad)

    def test_allocations_births_trade_counts_and_event_binding_are_complete(self):
        body=numbers.decode(self.samples[0][2])
        for alter in (lambda b:b['history']['allocated_ids'].pop(),
            lambda b:b['history']['allocated_ids'].reverse(),
            lambda b:b['history']['allocated_ids'].append(b['history']['allocated_ids'][0]),
            lambda b:b['history']['birth_members'].pop(),
            lambda b:b['checkpoint']['engine']['members'][0].update(num_trades=1),
            lambda b:b['evidence']['actions'][0].update(operation_index=1),
            lambda b:b['events'].pop(),
            lambda b:b['events'].reverse(),
            lambda b:b['events'][0].update(kind='invented'),
            lambda b:b['history'].update(owner_id=WORKER)):
            bad=deepcopy(body); alter(bad); self.reject(bad)

    def test_prior_catalog_missing_wrong_role_and_historical_cross_kind_reuse_fail(self):
        self.seed(self.samples[0])
        account=self.samples[0][0].state.to_dict()['accounts'][0]['id']
        self.db.sql(f"DELETE FROM vn_economic_research.allocated WHERE id={literal(account)};")
        self.reject(numbers.decode(self.samples[1][2]),'economic_prior_identity_unavailable')
        self.setUp(); self.seed(self.samples[0])
        self.db.sql(f"UPDATE vn_economic_research.allocated SET kind='position' WHERE id={literal(account)};")
        self.reject(numbers.decode(self.samples[1][2]),'economic_prior_identity_unavailable')
        self.setUp()
        identity=self.samples[0][0].history['allocated_ids'][0]
        self.db.sql('INSERT INTO vn_economic_research.allocated VALUES('+','.join(
            (literal(identity),literal(OWNER),literal(RUN),literal('position'),'2'))+');')
        self.reject(numbers.decode(self.samples[0][2]),'economic_historical_identity_reuse')

    def test_stop_keeps_holdings_and_does_not_invent_realized_economic_history(self):
        rows=self.extras['held_stop']; stop=rows[-1]
        self.prefix(rows,len(rows)-1)
        result=self.audit(stop[2])
        self.assertEqual(len(stop[0].state.to_dict()['positions']),8)
        self.assertEqual(result['economic_evidence']['closed_count'],0)
        # Controls sequence pauses while eight positions remain open.
        rows=self.extras['controls']; index=next(i for i,r in enumerate(rows) if
            r[0].transition['evidence']['kind']=='control')
        self.prefix(rows,index)
        body=numbers.decode(rows[index][2])
        self.assertEqual(len(body['checkpoint']['positions']),8)
        bad=deepcopy(body); bad['checkpoint']['positions']=[]
        self.reject(bad,'economic_complete_cash_or_holding_mismatch')

    def test_double_closes_retirement_with_holdings_and_unknown_operations_fail(self):
        index,row=self.phase('close'); self.prefix(self.samples,index)
        body=numbers.decode(row[2])
        closes=[i for i,o in enumerate(body['operations']) if o['kind']=='close']
        bad=deepcopy(body); bad['operations'][closes[1]]=deepcopy(bad['operations'][closes[0]])
        self.reject(bad,'economic_close_unavailable')
        holder=row[0].transition['before']['positions'][0]['account_id']
        bad=deepcopy(body); bad['operations'][0]={'kind':'retire','id':holder}
        self.reject(bad,'economic_retire_binding')
        bad=deepcopy(body); bad['operations'][0]['kind']='transfer'
        self.reject(bad,'economic_unknown_operation')

    def test_terminal_cash_frozen_evidence_and_reserved_trade_counter_cannot_change(self):
        rows=self.extras['terminal']; self.prefix(rows,len(rows)-1)
        body=numbers.decode(rows[-1][2])
        bad=deepcopy(body); bad['checkpoint']['engine']['members'][0]['terminal']['cash']='1'
        self.reject(bad,'economic_frozen_terminal_mismatch')
        bad=deepcopy(body); bad['checkpoint']['engine']['members'][0]['assessment']['cash_balance']='1'
        self.reject(bad,'economic_frozen_terminal_mismatch')
        index,row=self.phase('retire'); self.prefix(self.samples,index)
        prior=self.samples[index-1][1].to_dict()
        prior['engine']['members'][0]['num_trades']=2**63-2
        self.db.sql(f"UPDATE vn_dependency_research.checkpoints SET manifest_wire={literal(numbers.encode(prior).decode())};")
        body=numbers.decode(row[2])
        body['prior']['sha256']=hashlib.sha256(numbers.encode(prior)).hexdigest()
        self.reject(body,'economic_trade_count_mismatch')

    def test_prior_catalog_foreign_scope_future_revision_and_global_unique_key(self):
        self.seed(self.samples[0])
        account=self.samples[0][0].state.to_dict()['accounts'][0]['id']
        self.db.sql(f"UPDATE vn_economic_research.allocated SET born_revision=3 WHERE id={literal(account)};")
        self.reject(numbers.decode(self.samples[1][2]),'economic_prior_identity_unavailable')
        self.db.sql(f"INSERT INTO vn_dependency_research.checkpoints VALUES({literal(WORKER)},{literal(WORKER)},1,NULL);"+
            f"UPDATE vn_economic_research.allocated SET born_revision=2,owner_id={literal(WORKER)},run_id={literal(WORKER)} WHERE id={literal(account)};")
        self.reject(numbers.decode(self.samples[1][2]),'economic_prior_identity_unavailable')
        denied=self.db.sql('INSERT INTO vn_economic_research.allocated VALUES('+','.join(
            (literal(account),literal(OWNER),literal(RUN),literal('risk'),'2'))+');',check=False)
        self.assertIn('duplicate key',denied.stderr)

    def test_prior_identity_rows_remain_locked_through_the_validation_transaction(self):
        self.seed(self.samples[0]); marker='economic-identity-holder'
        holder=self.db.begin_sql(f"BEGIN; SET application_name='{marker}'; "+
            self.sql(self.samples[1][2])+"SELECT pg_sleep(1.5); COMMIT;",role=AUDITOR)
        deadline=time.monotonic()+4
        while self.db.scalar(f"SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name={literal(marker)} AND wait_event='PgSleep');")!='t':
            if time.monotonic()>deadline: raise AssertionError('Owned identity-lock barrier missed')
            time.sleep(.02)
        account=self.samples[0][0].state.to_dict()['accounts'][0]['id']
        denied=self.db.sql("SET lock_timeout='150ms'; DELETE FROM vn_economic_research.allocated WHERE id="+literal(account)+';',check=False)
        self.assertIn('lock timeout',denied.stderr)
        holder.wait()
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_economic_research.allocated;'),'8')

    @unittest.skipUnless(os.environ.get('DASHBOARD_ECONOMIC_TRANSITION_MEASURE')=='1',
                         'Optional full-boundary timing requires explicit opt-in')
    def test_z_measure_resolved_economic_boundary_without_effects(self):
        largest=max(range(len(self.samples)),key=lambda i:len(self.samples[i][2]))
        chosen=[('bootstrap',self.samples,0),('quote',self.samples,1),
            ('replacement',self.samples,largest),('risk_trip',self.extras['risk'],len(self.extras['risk'])-2),
            ('held_stop',self.extras['held_stop'],len(self.extras['held_stop'])-1)]
        measured=[]
        for kind,rows,index in chosen:
            self.prefix(rows,index); wire=rows[index][2]; before=self.snapshot()
            source=['SET plan_cache_mode=force_generic_plan;',
                'CREATE TEMP TABLE timings(elapsed_us bigint);',
                'DO $measure$ DECLARE t timestamptz;i integer;r jsonb;w text:='+
                literal(wire.decode())+'; BEGIN FOR i IN 1..30 LOOP t:=clock_timestamp(); '+
                'r:=vn_economic_research.validate_request('+literal(OWNER)+','+literal(RUN)+',w); '+
                'INSERT INTO timings VALUES(extract(epoch FROM clock_timestamp()-t)*1000000); END LOOP; END $measure$;',
                """SELECT json_build_object('samples',count(*),
                  'p50_us',percentile_cont(.5) WITHIN GROUP(ORDER BY elapsed_us),
                  'p95_us',percentile_cont(.95) WITHIN GROUP(ORDER BY elapsed_us),
                  'maximum_us',max(elapsed_us)) FROM timings;"""]
            timing=json.loads(self.db.scalar('\n'.join(source),role=AUDITOR,timeout=60))
            measured.append({'kind':kind,'wire_bytes':len(wire),**timing})
            self.assertEqual(self.snapshot(),before)
        artifact={'date':'2026-10-11','identity':self.db.identity,
            'sql_sha256':hashlib.sha256(SQL.read_bytes()).hexdigest(),
            'numeric_sql_sha256':hashlib.sha256((DIRECTORY/'numeric_wire.sql').read_bytes()).hexdigest(),
            'resolution_sql_sha256':hashlib.sha256((DIRECTORY/'locked_checkpoint.sql').read_bytes()).hexdigest(),
            'provider_checkpoint_sha256':hashlib.sha256((ROOT/'vonneumann/research/provider_checkpoint.py').read_bytes()).hexdigest(),
            'scope':'offline independent exact economic replay and allocated identity checks only; no commit/admission authority',
            'complete_commands':len(self.samples)+sum(map(len,self.extras.values())),
            'fill_pairs':128,'tables_in_new_artifact':1,'writes_by_validator':0,
            'warm_server_validation_timings':measured,
            'timing_method':'30 full volatile wrapper calls with wire variable and generic plans; unchanged privileged fixture prior',
            'timing_exclusions':['transport/TLS','contended locks','complete source/risk/assessment/optimizer/lineage semantics',
                'journal/identity reservation/dependency pin/projection writes','final source/lease recheck',
                'COMMIT/WAL/relay','hosted tails'],
            'production_grants_or_install':False}
        (ROOT/'research/economic-transition-measurements.json').write_text(json.dumps(artifact,indent=2,sort_keys=True)+'\n')

    def test_semantic_scope_does_not_claim_source_fitness_or_optimizer_authority(self):
        body=numbers.decode(self.samples[0][2])
        # A later semantic layer must reject these source changes. This layer
        # validates economic effects only and leaves every fixture row unchanged.
        body['evidence']['inputs']['provider']['wall_us']=0
        before=self.snapshot(); self.audit(numbers.encode(body)); self.assertEqual(self.snapshot(),before)
