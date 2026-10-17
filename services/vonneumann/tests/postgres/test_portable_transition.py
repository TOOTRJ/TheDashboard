"""Independent complete original-v2 SQL semantics and accepted-prior provenance."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import unittest
from uuid import UUID

from tests.postgres.harness import IsolatedPostgres,OPT_IN
from tests.postgres.portable_sql_fixture import ga,cp,extra_sequence,recovery_sequence,protective_boundary_sequence,expired_signal_sequence,frozen_completion_sequence
from tests.test_provider_ga_components import provider_trace
from tests.test_provider_contract import OWNER,RUN,WORKER,WALL,MONO,EPOCH,source_inputs,raw_capture
from tests.measure_provider_ga_research import literal
from vonneumann.research import numeric_wire as numbers

ROOT=Path(__file__).resolve().parents[2]
DIRECTORY=ROOT/'db-contract/research'
INSTALLER='vn_portable_semantic_installer'
AUDITOR='vn_portable_semantic_auditor'
FILES=(('portable_numeric_wire.sql','portable_numeric_wire_fixture','offline-v2'),
 ('portable_configuration.sql','portable_configuration_fixture','offline-v2'),
 ('portable_locked_checkpoint.sql','portable_locked_checkpoint_fixture','offline-v2'),
 ('portable_economic_transition.sql','portable_economic_transition_fixture','offline-v2'),
 ('portable_source_transition.sql','portable_source_transition_fixture','offline-v2'),
 ('portable_causal_risk.sql','portable_causal_risk_fixture','offline-v2'),
 ('portable_assessment_transition.sql','portable_assessment_fixture','offline-v2'),
 ('portable_optimizer_graph.sql','portable_optimizer_graph_fixture','offline-v2'),
 ('portable_optimizer_rng.sql','portable_optimizer_rng_fixture','offline-v2'),
 ('portable_model_period_mutation.sql','portable_model_period_fixture','offline-v2'),
 ('portable_optimizer_transition.sql','portable_optimizer_transition_fixture','offline-v2'),
 ('portable_transition.sql','portable_transition_fixture','offline-v2'))


def rewrite_graph(value,alter):
    """Reencode node IDs/refs after a grammar-preserving adversarial change."""
    alter(value)
    ids={};next_id=0
    def walk(node):
        nonlocal next_id
        if type(node) is not dict:return
        if 'ref' in node:node['ref']=ids[node['ref']];return
        if 'node' in node:
            old=node['node'];ids[old]=next_id;node['node']=next_id;next_id+=1
        if node.get('type') in ('list','tuple'):
            for child in node['items']:walk(child)
        elif node.get('type')=='map':
            for _,child in node['entries']:walk(child)
        elif node.get('type')=='object':
            for key in sorted(node['fields']):walk(node['fields'][key])
    walk(value['strategy']);walk(value['cohort'])


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class PortableTransitionSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples=[]
        provider_trace(True,windows=2,model=ga,checkpoint=cp,observer=lambda c,p,w:cls.samples.append((c,p,w)))
        cls.db=IsolatedPostgres().start()
        try:
            cls.db.sql(f'''CREATE ROLE {INSTALLER} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
              CREATE ROLE {AUDITOR} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
              GRANT CREATE ON DATABASE postgres TO {INSTALLER};''')
            for filename,setting,marker in FILES:
                text=(DIRECTORY/filename).read_text()
                denied=cls.db.sql(text,role=INSTALLER,check=False)
                if denied.returncode==0 or f'offline_{setting}_required' not in denied.stderr:
                    raise AssertionError(f'{filename} installed without its guard: {denied.stderr[-500:]}')
                cls.db.sql(f"BEGIN; SET dashboard.{setting}='{marker}';"+text+'COMMIT;',role=INSTALLER)
            cls.db.sql(f'''GRANT USAGE ON SCHEMA vn_portable_semantic_research TO {AUDITOR};
              GRANT EXECUTE ON FUNCTION vn_portable_semantic_research.validate_request(uuid,uuid,text) TO {AUDITOR};''',role=INSTALLER)
            cls.source_sha256={name:hashlib.sha256((DIRECTORY/name).read_bytes()).hexdigest() for name,_,_ in FILES}
        except BaseException:
            cls.db.close();raise

    @classmethod
    def tearDownClass(cls):cls.db.close()

    def setUp(self):
        self.db.sql('''DELETE FROM vn_portable_semantic_research.accepted_heads;
          DELETE FROM vn_portable_semantic_research.accepted_commands;
          DELETE FROM vn_portable_economic_research.allocated;
          DELETE FROM vn_portable_dependency_research.components;
          DELETE FROM vn_portable_dependency_research.checkpoints;''')
        self.db.sql(f'INSERT INTO vn_portable_dependency_research.checkpoints VALUES({literal(RUN)},{literal(OWNER)},1,NULL);')

    def sql(self,wire,*,advance=False,owner=OWNER,run=RUN):
        name='advance_fixture' if advance else 'validate_request'
        return 'SELECT vn_portable_semantic_research.'+name+'('+','.join((literal(owner),literal(run),literal(wire.decode())))+');'

    def audit(self,wire):return json.loads(self.db.scalar(self.sql(wire),role=AUDITOR,timeout=30))
    def advance(self,row):return json.loads(self.db.scalar(self.sql(row[2],advance=True),role=INSTALLER,timeout=30))

    def prefix(self,rows,index):
        self.setUp()
        for row in rows[:index]:self.advance(row)

    def snapshot(self):
        return self.db.scalar('''SELECT jsonb_build_object(
          'checkpoints',(SELECT jsonb_agg(to_jsonb(c) ORDER BY run_id) FROM vn_portable_dependency_research.checkpoints c),
          'components',(SELECT jsonb_agg(to_jsonb(c) ORDER BY sha256) FROM vn_portable_dependency_research.components c),
          'allocated',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM vn_portable_economic_research.allocated c),
          'heads',(SELECT jsonb_agg(to_jsonb(c) ORDER BY run_id) FROM vn_portable_semantic_research.accepted_heads c),
          'commands',(SELECT jsonb_agg(to_jsonb(c) ORDER BY revision) FROM vn_portable_semantic_research.accepted_commands c));''')

    def reject(self,body,expected=None):
        wire=body if type(body) is bytes else numbers.encode(body)
        before=self.snapshot();result=self.db.sql(self.sql(wire),role=AUDITOR,check=False,timeout=30)
        self.assertNotEqual(result.returncode,0)
        if expected is not None:self.assertIn(expected,result.stderr)
        self.assertEqual(self.snapshot(),before)

    def block(self,row,body,kind,alter,entity=None):
        original=next(c for c in row[1].components if c.to_dict()['kind']==kind and (entity is None or c.to_dict()['entity_id']==entity))
        value=original.to_dict();alter(value['body'])
        following=cp.TypedComponent.make(OWNER,RUN,kind,value['entity_id'],value['generation'],value['body'])
        body['components']=[c for c in body['components'] if not(c['kind']==kind and c['entity_id']==value['entity_id'])]
        body['components'].append(following.to_dict())
        for ref in body['checkpoint']['components']:
            if ref['kind']==kind and ref['entity_id']==value['entity_id']:ref.update(following.reference())

    def test_bootstrap_full_original_v2_semantics_and_read_only_authority(self):
        before=self.snapshot();result=self.audit(self.samples[0][2]);self.assertEqual(self.snapshot(),before)
        self.assertEqual(result['format'],'ga-portable-complete-sql-validation-research-v2')
        self.assertTrue(result['original_v2_complete_semantics_verified'])
        self.assertFalse(result['server_accepted_prior_verified'])
        self.assertTrue(result['optimizer_evidence']['completed_offspring_mutation_verified'])
        self.assertFalse(result['native_admission_authority']);self.assertFalse(result['restoration_authority']);self.assertFalse(result['hosted_authority'])
        self.assertEqual(result['command_sha256'],hashlib.sha256(self.samples[0][2]).hexdigest())
        self.assertEqual(result['following_sha256'],hashlib.sha256(numbers.encode(self.samples[0][1].to_dict())).hexdigest())

    def test_two_dense_windows_complete_original_commands_and_both_mating_modes(self):
        operations=set();replacements=0;assessments=0;contracts=set()
        for index,row in enumerate(self.samples):
            with self.subTest(index=index):
                result=self.advance(row);contracts.add(result['validator_sha256'])
                self.assertTrue(result['original_v2_complete_semantics_verified'])
                self.assertEqual(result['server_accepted_prior_verified'],index>0)
                assessments+=len(row[0].history['assessments'])
                if row[0].history['selection']:
                    replacements+=1;operations.update(r['operation'] for r in row[0].history['selection']['offspring'])
        self.assertEqual(len(self.samples),35);self.assertEqual(replacements,2);self.assertEqual(assessments,16)
        self.assertEqual(operations,{'crossover_mutation','clone_mutation'});self.assertEqual(len(contracts),1)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_portable_semantic_research.accepted_commands;'),'35')
        replay=self.db.scalar(self.sql(self.samples[0][2],advance=True),role=INSTALLER)
        self.assertIn('ga-portable-accepted-fixture-replay-v2',replay)
        self.assertEqual(self.db.scalar('SELECT revision FROM vn_portable_dependency_research.checkpoints;'),'36')

    def forge_period_with_every_mirror(self,row,body,*,kind='ema_fast'):
        identity=body['checkpoint']['engine']['members'][0]['id']
        old=next(b.to_dict()['body'][kind] for b in row[1].components if b.to_dict()['kind']=='genome' and b.to_dict()['entity_id']==identity)
        value=(3.0 if float.fromhex(old)!=3 else 4.0).hex() if kind=='ema_fast' else (15.0 if float.fromhex(old)!=15 else 16.0).hex()
        self.block(row,body,'genome',lambda g:g.update({kind:value}),entity=identity)
        for member in body['history']['birth_members']:
            if member['id']==identity:member['genome'][kind]=value
        def alter(graph):
            for key,genome in graph['cohort']['fields']['_genomes']['entries']:
                if key==identity:genome['fields'][kind]['hex']=value
            for key,signature in graph['strategy']['fields']['_cohort']['fields']['_signatures']['entries']:
                if key==identity:
                    for field,coordinate in signature['entries']:
                        if field==kind:coordinate['hex']=value
        self.block(row,body,'optimizer',lambda g:rewrite_graph(g,alter))
        return identity,value

    def test_forged_in_range_offspring_periods_fail_even_when_all_mirrors_agree(self):
        index,row=next((i,r) for i,r in enumerate(self.samples) if r[0].history['selection'])
        self.prefix(self.samples,index);body=numbers.decode(row[2]);self.audit(row[2])
        for gene in ('ema_fast','ema_slow'):
            bad=deepcopy(body);self.forge_period_with_every_mirror(row,bad,kind=gene)
            self.reject(bad,'optimizer_genotype_or_parent_mismatch')
        bad=deepcopy(body);bad['history']['selection']['mutation_operator']='ema-period-triangular-integer-research-v1'
        self.reject(bad,'optimizer_continuation_or_selection')
        bad=deepcopy(body);bad['history']['selection']['offspring'][0]['parent_ids'].reverse()
        # The first pair is sexual in this reviewed seed. All true parents/order
        # remain bound to the independently derived actual tournaments.
        self.assertNotEqual(bad,body);self.reject(bad,'optimizer_continuation_or_selection')
        for field,value in (('version',2),('operation','clone_mutation'),('source_iteration_id','foreign'),('offspring_index',7),('distribution_id',RUN)):
            bad=deepcopy(body);birth=next(o for o in bad['operations'] if o['kind']=='birth');birth['lineage'][field]=value
            self.reject(bad,'optimizer_lineage_mismatch')

    def test_server_accepted_chain_is_required_not_privileged_dependency_seeding(self):
        candidate,capture,_=self.samples[0]
        components=','.join('('+','.join((literal(OWNER),literal(RUN),literal(b.identity),literal(b._wire.decode())))+')' for b in capture.components)
        self.db.sql('INSERT INTO vn_portable_dependency_research.components VALUES '+components+';'+
            f"UPDATE vn_portable_dependency_research.checkpoints SET revision=2,manifest_wire={literal(numbers.encode(capture.to_dict()).decode())};")
        self.reject(self.samples[1][2],'portable_semantic_prior_not_accepted')
        # A held hash is not semantic proof even for a well-formed true candidate.
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_portable_semantic_research.accepted_heads;'),'0')

    def test_server_prior_manifest_original_command_and_validator_are_bound(self):
        self.advance(self.samples[0]);before=self.snapshot()
        # The constraint itself prevents a head from naming a different command,
        # digest or validator, even under privileged fixture administration.
        result=self.db.sql("UPDATE vn_portable_semantic_research.accepted_heads SET command_sha256=repeat('0',64);",check=False)
        self.assertNotEqual(result.returncode,0);self.assertEqual(self.snapshot(),before)
        original=self.samples[0][1].to_dict();original['reserve']='199'
        fake_sha=hashlib.sha256(numbers.encode(original)).hexdigest()
        self.db.sql('BEGIN; DELETE FROM vn_portable_semantic_research.accepted_heads;'+
          f"UPDATE vn_portable_semantic_research.accepted_commands SET manifest_sha256={literal(fake_sha)};"+
          f"INSERT INTO vn_portable_semantic_research.accepted_heads SELECT owner_id,run_id,revision,command_sha256,manifest_sha256,validator_sha256 FROM vn_portable_semantic_research.accepted_commands;"+
          f"UPDATE vn_portable_dependency_research.checkpoints SET manifest_wire={literal(numbers.encode(original).decode())}; COMMIT;")
        body=numbers.decode(self.samples[1][2]);body['prior']['sha256']=fake_sha
        self.reject(body,'portable_semantic_original_prior_binding')

    def test_changed_validator_contract_rejects_retained_semantic_prior(self):
        self.advance(self.samples[0])
        self.db.sql('CREATE FUNCTION vn_portable_semantic_research.contract_drift_fixture() RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$ SELECT true $$;',role=INSTALLER)
        try:self.reject(self.samples[1][2],'portable_semantic_prior_not_accepted')
        finally:self.db.sql('DROP FUNCTION vn_portable_semantic_research.contract_drift_fixture();',role=INSTALLER)

    def test_rehashed_graph_rng_software_types_and_unknown_fields_fail(self):
        row=self.samples[0];body=numbers.decode(row[2])
        changes=[lambda g:g['software'].update(python='3.12.15'),
            lambda g:g['strategy']['fields'].update(callback='unreviewed'),
            lambda g:g['strategy']['fields']['_rng']['words'].__setitem__(10,(g['strategy']['fields']['_rng']['words'][10]+1)%2**32),
            lambda g:g['strategy']['fields']['_rng'].update(index=1),
            lambda g:g['strategy']['fields']['_mutation_event'].update(decimal='1'),
            lambda g:g['strategy']['fields']['_search_epoch'].update(decimal='1'),
            lambda g:g['strategy']['fields']['_search_streams']['fields'].update(seed='7'),
            lambda g:g['cohort']['fields']['member_ids'].update(type='list'),
            lambda g:g['cohort']['fields']['_evaluation_ids']['entries'].append(deepcopy(g['cohort']['fields']['_evaluation_ids']['entries'][0]))]
        for alter in changes:
            bad=deepcopy(body);self.block(row,bad,'optimizer',lambda g:rewrite_graph(g,alter));self.reject(bad)
        bad=deepcopy(body);self.forge_period_with_every_mirror(row,bad);self.reject(bad,'optimizer_genotype_or_parent_mismatch')
        bad=deepcopy(body);bad['checkpoint']['engine']['members'][0]['name']='invented'
        for member in bad['history']['birth_members']:
            if member['id']==bad['checkpoint']['engine']['members'][0]['id']:member['name']='invented'
        self.reject(bad,'optimizer_name_allocation')

    def test_limited_installer_no_client_tables_helpers_or_chain_advance(self):
        metadata=json.loads(self.db.scalar("""SELECT json_agg(x) FROM (SELECT n.nspname,p.proname,p.prosecdef,p.proconfig,r.rolname AS owner
          FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner
          WHERE n.nspname LIKE 'vn_portable_%_research' ORDER BY n.nspname,p.proname)x;"""))
        self.assertTrue(all(r['owner']==INSTALLER and r['proconfig']==['search_path=pg_catalog, pg_temp'] for r in metadata))
        self.assertEqual([(r['nspname'],r['proname']) for r in metadata if r['prosecdef']],
          [('vn_portable_dependency_research','resolve_request'),('vn_portable_semantic_research','validate_request')])
        self.assertEqual(self.db.scalar(f"SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls FROM pg_roles WHERE rolname='{INSTALLER}';"),'f')
        for role in ('anon','authenticated','service_role'):
            self.assertNotEqual(self.db.sql(self.sql(self.samples[0][2]),role=role,check=False).returncode,0)
        for statement in (self.sql(self.samples[0][2],advance=True),
            "SELECT vn_portable_semantic_research.validator_contract();",
            "SELECT vn_portable_optimizer_research.mt_seed(0);",
            "SELECT vn_portable_dependency_research.resolve_request("+','.join((literal(OWNER),literal(RUN),literal(self.samples[0][2].decode())))+");",
            'SELECT * FROM vn_portable_semantic_research.accepted_heads;',
            'SELECT * FROM vn_portable_semantic_research.accepted_commands;',
            'SELECT * FROM vn_portable_economic_research.allocated;',
            'CREATE SCHEMA forbidden_semantic_schema;'):
            self.assertNotEqual(self.db.sql(statement,role=AUDITOR,check=False).returncode,0)
        self.assertEqual(self.db.scalar("""SELECT NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace,
          LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE n.nspname LIKE 'vn_portable_%_research'
          AND a.grantee=0 AND a.privilege_type='EXECUTE');"""),'t')

    def test_original_command_id_replay_conflict_and_late_failure_rollback(self):
        self.advance(self.samples[0]);before=self.snapshot()
        replay=self.db.sql(self.sql(self.samples[0][2],advance=True),role=INSTALLER)
        self.assertIn('accepted-fixture-replay',replay.stdout);self.assertEqual(self.snapshot(),before)
        body=numbers.decode(self.samples[0][2]);body['events']=[]
        denied=self.db.sql(self.sql(numbers.encode(body),advance=True),role=INSTALLER,check=False)
        self.assertIn('portable_semantic_original_id_conflict',denied.stderr);self.assertEqual(self.snapshot(),before)
        # A downstream SQL failure cannot leave partial components/IDs/head/history.
        denied=self.db.sql('BEGIN;'+self.sql(self.samples[1][2],advance=True)+"SELECT 1/0; COMMIT;",role=INSTALLER,check=False,timeout=30)
        self.assertIn('division by zero',denied.stderr);self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_portable_semantic_research.accepted_commands;'),'1')

    def test_complete_controls_risk_recovery_terminal_expiration_cost_and_seed_traces(self):
        recovery=recovery_sequence()
        traces={'cost':extra_sequence(cost=ga.DecimalExecutionConfig('2.123456','15.000001','7.765432')),
            'terminal':extra_sequence(death=True),'risk':extra_sequence(death=True,risk_bps='1000'),
            'controls':extra_sequence(controls=True),'recovery':recovery,
            'frozen_completion':frozen_completion_sequence(),
            'expired_signal':expired_signal_sequence(recovery[:5])}
        for i,(name,price) in enumerate((('stop_edge','97'),('stop_above','97.000000000000000001'),
            ('take_edge','107'),('take_below','106.999999999999999999'))):
            traces[name]=protective_boundary_sequence(recovery[:7],price,1200+i*10)
        for seed in ('1','18446744073709551615'):
            rows=[];provider_trace(False,windows=1,model=ga,checkpoint=cp,search_seed=seed,observer=lambda c,p,w:rows.append((c,p,w)))
            traces['seed_'+seed]=rows
        count=0;finalized=0;frozen=0;epochs=set();statuses=set();mating=set()
        for name,rows in traces.items():
            self.setUp()
            for index,row in enumerate(rows):
                with self.subTest(trace=name,index=index):
                    result=self.advance(row);count+=1
                    self.assertEqual(result['command_sha256'],hashlib.sha256(row[2]).hexdigest())
                    self.assertTrue(result['optimizer_evidence']['completed_offspring_mutation_verified'])
                    finalized+=int(result['assessment_evidence']['finalized_count']['$integer'])
                    frozen+=int(result['assessment_evidence']['new_frozen_count']['$integer'])
                    state=row[0].state.to_dict();epochs.add(state['engine']['lifecycle']['search_epoch']);statuses.add(state['status'])
                    if row[0].history['selection']:mating.update(o['operation'] for o in row[0].history['selection']['offspring'])
            self.assertEqual(int(self.db.scalar('SELECT count(*) FROM vn_portable_semantic_research.accepted_commands;')),len(rows))
        self.assertGreaterEqual(count,150);self.assertGreaterEqual(finalized,72);self.assertGreaterEqual(frozen,16)
        self.assertIn(1,epochs);self.assertTrue({'paused','risk_halted','stopped'}.issubset(statuses))
        self.assertEqual(mating,{'crossover_mutation','clone_mutation'})

    def test_assessment_source_economic_and_causal_forgery_do_not_pass_full_composition(self):
        index,row=next((i,r) for i,r in enumerate(self.samples) if r[0].history['assessments'])
        self.prefix(self.samples,index);body=numbers.decode(row[2]);self.audit(row[2])
        for alter in (lambda b:b['history']['assessments'][0].update(fitness_float64='0x1.0000000000000p+0'),
            lambda b:b['history']['assessments'][0]['metrics'].update(max_drawdown={'numerator':'1','denominator':'100'}),
            lambda b:b['history']['assessments'][0].update(assessment_policy='unreviewed'),
            lambda b:b['history']['assessments'][0].update(cohort_complete=False),
            lambda b:b['history']['assessments'].reverse(),
            lambda b:b['checkpoint'].update(reserve='123'),
            lambda b:b['checkpoint']['engine']['lifecycle']['risk'].update(observed_equity='999'),
            lambda b:b['checkpoint']['engine']['members'][0].update(pending={'signal_at':WALL,'kind':'buy'})):
            bad=deepcopy(body);alter(bad);self.reject(bad)
        bad=deepcopy(body);bad['evidence']['inputs']['provider']['frame']['quote']['document']['response_sha256']='0'*64
        self.reject(bad)
        bad=deepcopy(body);bad['evidence']['inputs']['provider']['frame']['quote']['document']['request']['endpoint']='https://unreviewed.invalid'
        self.reject(bad)

    def test_semantic_validator_holds_current_chain_and_dependencies_until_transaction_end(self):
        self.advance(self.samples[0]);before=self.snapshot();marker='portable-semantic-held-lock'
        holder=self.db.begin_sql("BEGIN; SET application_name='"+marker+"';"+self.sql(self.samples[1][2])+"SELECT pg_sleep(1.5); COMMIT;",role=AUDITOR,timeout=30)
        self.db.wait_until("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='"+marker+"' AND wait_event='PgSleep');")
        for statement in ('UPDATE vn_portable_dependency_research.checkpoints SET revision=revision+1;',
            'DELETE FROM vn_portable_dependency_research.components;',
            'DELETE FROM vn_portable_semantic_research.accepted_heads;',
            'DELETE FROM vn_portable_semantic_research.accepted_commands;'):
            denied=self.db.sql("SET lock_timeout='150ms';"+statement,check=False)
            self.assertIn('lock timeout',denied.stderr)
        holder.wait();self.assertEqual(self.snapshot(),before)

    def test_data_free_held_stop_preserves_positions_and_aborts_without_scores(self):
        ledger=ga.SimulationLedger(OWNER,RUN);prefix=[]
        for row in self.samples:
            state=ledger.accept(row[0]);prefix.append(row)
            if state.to_dict()['positions']:break
        self.assertEqual(len(state.to_dict()['positions']),8)
        at=state.to_dict()['engine']['last_quote']['timestamp']+1
        stopped=ga.prepare_control(state,'stop',source_inputs(at,serial=7000),ledger=ledger)
        capture=cp.capture_owned_candidate(stopped)
        wire=cp.prepare_transport(stopped,capture,command_id=str(UUID(int=99007000)),previous=prefix[-1][1])
        self.prefix(prefix,len(prefix));before=self.snapshot();result=self.audit(wire);self.assertEqual(self.snapshot(),before)
        self.assertTrue(result['original_v2_complete_semantics_verified'])
        self.assertIsNone(numbers.decode(wire)['evidence']['inputs']['provider']['frame'])
        self.assertEqual(capture.resolve()['positions'],state.to_dict()['positions'])
        self.assertTrue(all(a['status']=='aborted' and a['fitness_float64'] is None for a in stopped.history['assessments']))
        bad=numbers.decode(wire);bad['checkpoint']['positions']=[];self.reject(bad)
        bad=numbers.decode(wire);bad['checkpoint']['engine']['lifecycle']['risk']['observed_at']+=1
        self.reject(bad,'causal_lifecycle_after_mismatch')
        accepted=self.advance((stopped,capture,wire));self.assertTrue(accepted['fixture_chain_advanced'])
        self.assertEqual(self.db.scalar('SELECT revision FROM vn_portable_dependency_research.checkpoints;'),str(stopped.state.revision))

    def test_full_original_v2_refusals_are_bounded_and_leave_all_rows_unchanged(self):
        body=numbers.decode(self.samples[0][2])
        for wire in (self.samples[0][2]+b' ',b'x'*262145,b'{"a":true,"a":false}'):
            self.reject(wire)
        for field,value in (('format','ga-provider-compact-command-research-v2'),('owner_id',WORKER),('run_id',WORKER)):
            bad=deepcopy(body);bad[field]=value;self.reject(bad)
        for field,value in (('revision',True),('status','unknown'),('source_model_version','ga-provider-model-research-v1')):
            bad=deepcopy(body);bad['checkpoint'][field]=value;self.reject(bad)
        bad=deepcopy(body);bad['checkpoint']['engine']['generation']=2**31;self.reject(bad)
        for counter in ('_mutation_event','_search_epoch'):
            bad=deepcopy(body)
            self.block(self.samples[0],bad,'optimizer',lambda g:rewrite_graph(g,
                lambda graph:graph['strategy']['fields'][counter].update(decimal=str(2**31))))
            self.reject(bad)

    def test_exact_full_evidence_input_control_and_unused_allocations_are_validated(self):
        body=numbers.decode(self.samples[0][2])
        changes=[lambda b:b['evidence'].update(unknown=None),
            lambda b:b['evidence']['inputs'].update(unknown=None),
            lambda b:b['evidence'].update(control={'action':'stop','trip_id':None}),
            lambda b:b['evidence']['inputs']['ids'].append(b['evidence']['inputs']['ids'][0]),
            lambda b:b['evidence']['inputs']['ids'].append('00000000-0000-0000-0000-00000000ABCD'),
            lambda b:b['evidence']['inputs']['names'].append([True,'unused']),
            lambda b:b['evidence']['inputs']['names'].append([0,' unused']),
            lambda b:b['evidence']['inputs']['names'].append([0,'unused\u00a0space']),
            lambda b:b['evidence']['inputs']['names'].append([0,'a'*129])]
        for mutate in changes:
            bad=deepcopy(body);mutate(bad);self.reject(bad)
        self.advance(self.samples[0])
        ledger=ga.SimulationLedger(OWNER,RUN);state=ledger.accept(self.samples[0][0])
        stopped=ga.prepare_control(state,'stop',source_inputs(WALL+1,serial=8100),ledger=ledger)
        capture=cp.capture_owned_candidate(stopped)
        wire=cp.prepare_transport(stopped,capture,command_id=str(UUID(int=99008100)),previous=self.samples[0][1])
        self.audit(wire)
        bad=numbers.decode(wire);bad['evidence']['control']['unknown']=None;self.reject(bad,'checkpoint_keys_differ')

    def test_original_unicode15_name_printability_matches_python_at_representative_boundaries(self):
        names=['A B','café','e\u0301','🤡🎉','⠁','𠀀','\u00a0','a\u202fb','a\u200cb','a\u2066b',
            ' leading','trailing ','\t','a\nb','\u0378','\u10ffff','\U0002fffe','\U0010ffff','a'*128,'a'*129,'']
        statements=[];expected=[]
        for name in names:
            valid=bool(name and len(name)<=128 and len(name.encode('utf-8'))<=128 and name.strip()==name and name.isprintable())
            statements.append('SELECT vn_portable_semantic_research.printable_name('+literal(json.dumps(name))+'::jsonb);')
            expected.append('t' if valid else 'f')
        self.assertEqual(self.db.sql('\n'.join(statements),role=INSTALLER).stdout.splitlines(),expected)

    def test_temp_catalog_and_type_sentinels_are_never_resolved_under_semantic_owner(self):
        # Benign sentinels only: accidental shadow lookup raises, with no private
        # reads/writes or exploit actions in the sentinel. The valid caller still
        # receives normal read-only semantic acceptance under the corrected path.
        wire=self.samples[0][2];before=self.snapshot()
        setup='''CREATE TEMP TABLE benign_shadow_namespace_marker(x integer);
          CREATE FUNCTION pg_temp.benign_shadow_sentinel() RETURNS boolean LANGUAGE plpgsql AS $sentinel$
          BEGIN RAISE EXCEPTION 'unexpected_benign_shadow_sentinel_execution'; END $sentinel$;
          CREATE TEMP VIEW pg_proc AS SELECT * FROM pg_catalog.pg_proc WHERE pg_temp.benign_shadow_sentinel();
          CREATE TEMP VIEW pg_namespace AS SELECT * FROM pg_catalog.pg_namespace WHERE pg_temp.benign_shadow_sentinel();
          CREATE DOMAIN pg_temp.jsonb AS pg_catalog.jsonb CHECK(pg_temp.benign_shadow_sentinel());'''
        result=self.db.sql(setup+self.sql(wire),role=AUDITOR,timeout=30)
        self.assertNotIn('unexpected_benign_shadow_sentinel_execution',result.stderr)
        self.assertTrue(json.loads(result.stdout)['original_v2_complete_semantics_verified'])
        self.assertEqual(self.snapshot(),before)
