"""Independent graph/MT/selection/parentage proof; no Gaussian or restoration grant."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import random
import unittest

from tests.postgres.harness import OPT_IN
from tests.postgres.test_assessment_transition import AssessmentTransitionSqlTests
from tests.postgres.test_economic_transition import INSTALLER, AUDITOR
from tests.measure_provider_ga_research import literal
from tests.test_provider_contract import OWNER, RUN
from vonneumann.core.search_random import SearchRandomStreams
from vonneumann.research import numeric_wire as numbers

ROOT=Path(__file__).resolve().parents[2]
DIRECTORY=ROOT/'db-contract/research'
FILES=('optimizer_graph.sql','optimizer_rng.sql','optimizer_transition.sql')


def rewrite_graph(value,alter):
    """Reencode node IDs/refs after a grammar-preserving synthetic alteration."""
    alter(value)
    ids={}; next_id=0
    def walk(node):
        nonlocal next_id
        if not isinstance(node,dict): return
        if 'ref' in node:
            node['ref']=ids[node['ref']]; return
        if 'node' in node:
            old=node['node']; ids[old]=next_id; node['node']=next_id; next_id+=1
        kind=node.get('type')
        if kind in ('list','tuple'):
            for child in node['items']: walk(child)
        elif kind=='map':
            for _,child in node['entries']: walk(child)
        elif kind=='object':
            for key in sorted(node['fields']): walk(node['fields'][key])
    walk(value['strategy']); walk(value['cohort'])


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class OptimizerTransitionSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        AssessmentTransitionSqlTests.setUpClass.__func__(cls)
        try:
            for filename,setting in zip(FILES,('optimizer_graph_fixture','optimizer_rng_fixture','optimizer_transition_fixture')):
                source=(DIRECTORY/filename).read_text(); denied=cls.db.sql(source,role=INSTALLER,check=False)
                if denied.returncode==0 or f'offline_{setting}_required' not in denied.stderr:
                    raise AssertionError(f'{filename} installed without its guard')
                cls.db.sql(f"BEGIN; SET dashboard.{setting}='offline-v1';"+source+'COMMIT;',role=INSTALLER)
            cls.db.sql(f'''REVOKE EXECUTE ON FUNCTION vn_assessment_research.validate_request(uuid,uuid,text) FROM {AUDITOR};
              GRANT USAGE ON SCHEMA vn_optimizer_research TO {AUDITOR};
              GRANT EXECUTE ON FUNCTION vn_optimizer_research.validate_request(uuid,uuid,text) TO {AUDITOR};''',role=INSTALLER)
            cls.installed_sha256={name:hashlib.sha256((DIRECTORY/name).read_bytes()).hexdigest() for name in
                ('numeric_wire.sql','locked_checkpoint.sql','economic_transition.sql','source_transition.sql','causal_risk.sql','assessment_transition.sql',*FILES)}
        except BaseException:
            cls.db.close(); raise

    @classmethod
    def tearDownClass(cls): cls.db.close()

    setUp=AssessmentTransitionSqlTests.setUp
    seed=AssessmentTransitionSqlTests.seed
    prefix=AssessmentTransitionSqlTests.prefix
    snapshot=AssessmentTransitionSqlTests.snapshot
    reject=AssessmentTransitionSqlTests.reject
    phase=AssessmentTransitionSqlTests.phase
    audit=AssessmentTransitionSqlTests.audit
    block=AssessmentTransitionSqlTests.block

    def sql(self,wire):
        return 'SELECT vn_optimizer_research.validate_request('+','.join((literal(OWNER),literal(RUN),literal(wire.decode())))+');'

    def reject_optimizer(self,body,expected=None):
        wire=numbers.encode(body)
        self.db.sql('SELECT vn_assessment_research.validate_request('+','.join((literal(OWNER),literal(RUN),literal(wire.decode())))+');',role=INSTALLER)
        self.reject(body,expected)

    def replace_optimizer(self,row,body,alter):
        self.block(row,body,'optimizer',lambda graph:rewrite_graph(graph,alter))

    def test_bootstrap_founders_and_mirrors(self):
        result=self.audit(self.samples[0][2]); self.assertEqual(result['format'],'ga-optimizer-selection-validation-research-v1')
        self.assertEqual(int(result['optimizer_evidence']['strategy_draws']['$integer']),0)
        self.assertFalse(result['optimizer_evidence']['completed_offspring_mutation_verified'])
        self.assertFalse(result['optimizer_evidence']['restoration_authority'])

    def test_integer_seed_words_twist_and_draws_match_pinned_python(self):
        seeds=[0,1,-1,2**32-1,2**32,2**64-1,2**128+13,2**255,2**256-1]
        seeds+=[random.Random(93211).getrandbits(256)]
        statements=[]
        for seed in seeds:
            rng=random.Random(seed); words=list(rng.getstate()[1][:-1]); cursor=rng.getstate()[1][-1]
            statements.append('SELECT vn_optimizer_research.mt_seed('+str(seed)+") -> 'words' = "+literal(json.dumps(words))+'::jsonb;')
            for count in (1,623,624,625,1249):
                rng=random.Random(seed)
                for _ in range(count): word=rng.getrandbits(32)
                expected={'words':list(rng.getstate()[1][:-1]),'index':rng.getstate()[1][-1],'value':word}
                statements.append('DO $v$ DECLARE r jsonb:=vn_optimizer_research.mt_seed('+str(seed)+'); i integer; BEGIN FOR i IN 1..'+str(count)+
                    " LOOP r:=vn_optimizer_research.mt_next(r); END LOOP; IF (r-ARRAY['draws']) IS DISTINCT FROM "+literal(json.dumps(expected))+
                    "::jsonb THEN RAISE EXCEPTION 'vector_mismatch'; END IF; END $v$; SELECT true;")
        self.assertEqual(self.db.sql('\n'.join(statements),role=INSTALLER,timeout=60).stdout.splitlines(),['t']*len(statements))

    def test_namespaces_random_sample_and_fixed_asset_consumption(self):
        statements=[]
        for seed in ('0','18446744073709551615','123987'):
            streams=SearchRandomStreams(seed)
            for namespace,epoch,indices in [('strategy',0,()),('strategy',7,()),('gen0',0,(3,)),('mutation',2,('generation',9,7))]:
                rng=streams.rng(namespace,epoch,*indices); args=','.join((literal(seed),literal(namespace),str(epoch),literal(numbers.encode(list(indices)).decode())+'::jsonb'))
                statements.append('SELECT vn_optimizer_research.namespaced('+args+") -> 'words' = "+literal(json.dumps(list(rng.getstate()[1][:-1])))+'::jsonb;')
                value=rng.random(); statements.append('SELECT vn_source_research.round_ratio((vn_optimizer_research.mt_random(vn_optimizer_research.namespaced('+args+
                    "))->>'numerator')::numeric,9007199254740992) ->> '$binary64' = "+literal(value.hex())+';')
            for pool,k in [(['a'],1),(list('abcdefgh'),3),(list('abcdefg'),3)]:
                rng=streams.rng('strategy',0); sample=rng.sample(pool,k); state=rng.getstate()[1]
                args=','.join((literal(seed),literal('strategy'),'0'))
                expression='vn_optimizer_research.sample(vn_optimizer_research.namespaced('+args+'),'+literal(json.dumps(pool))+'::jsonb,'+str(k)+')'
                statements.append('SELECT ('+expression+") -> 'sample' = "+literal(json.dumps(sample))+'::jsonb;')
                statements.append('SELECT ('+expression+") -> 'words' = "+literal(json.dumps(list(state[:-1])))+'::jsonb AND ('+expression+
                    ")->>'index' = "+literal(str(state[-1]))+';')
        self.assertEqual(self.db.sql('\n'.join(statements),role=INSTALLER,timeout=60).stdout.splitlines(),['t']*len(statements))

    def test_complete_composed_traces_and_unchanged_durable_rows(self):
        count=0
        for name,rows in [('dense',self.samples),*self.extras.items()]:
            self.setUp()
            for i,row in enumerate(rows):
                with self.subTest(trace=name,index=i):
                    before=self.snapshot(); result=self.audit(row[2]); self.assertEqual(self.snapshot(),before)
                    self.assertTrue(result['optimizer_evidence']['selection_rng_and_parentage_verified'])
                    self.assertFalse(result['optimizer_evidence']['completed_offspring_mutation_verified'])
                    self.seed(row); count+=1
        self.assertEqual(count,165)

    def test_rehashed_graph_schema_software_alias_roles_and_capacity_are_private_checks(self):
        row=self.samples[0]; body=numbers.decode(row[2])
        alterations=[lambda g:g['software'].update(python='3.12.15'),
            lambda g:g['strategy']['fields'].update(callback='unreviewed'),
            lambda g:g['strategy']['fields']['_search_streams'].update(**{'class':'OtherStreams'}),
            lambda g:g['strategy']['fields']['_rng'].update(gaussian_hex='0x0.0p+0'),
            lambda g:g['strategy']['fields'].__setitem__('_rng',{'ref':0}),
            lambda g:g['cohort']['fields']['member_ids'].update(type='list'),
            lambda g:g['cohort']['fields']['_genomes']['entries'][0][1]['fields']['assets'].update(type='tuple'),
            lambda g:g['cohort']['fields']['_evaluation_ids']['entries'].append(deepcopy(g['cohort']['fields']['_evaluation_ids']['entries'][0]))]
        for i,alter in enumerate(alterations):
            with self.subTest(mutation=i):
                bad=deepcopy(body); self.replace_optimizer(row,bad,alter); self.assertNotEqual(body,bad); self.reject_optimizer(bad)
        bad=deepcopy(body); self.block(row,bad,'optimizer',lambda g:g['strategy'].update(node=1)); self.reject_optimizer(bad,'optimizer_node_order')

    def test_rehashed_rng_words_index_search_epoch_and_mutation_counter_fail(self):
        for rows,index in [(self.samples,0),(self.samples,1),(self.samples,18),(self.extras['controls'],8)]:
            row=rows[index]; self.prefix(rows,index); body=numbers.decode(row[2]); self.audit(row[2])
            changes=[lambda g:g['strategy']['fields']['_rng']['words'].__setitem__(10,(g['strategy']['fields']['_rng']['words'][10]+1)%2**32),
                lambda g:g['strategy']['fields']['_rng'].update(index=(g['strategy']['fields']['_rng']['index']+1)%625),
                lambda g:g['strategy']['fields']['_mutation_event'].update(decimal=str(int(g['strategy']['fields']['_mutation_event']['decimal'])+1)),
                lambda g:g['strategy']['fields']['_search_epoch'].update(decimal=str(int(g['strategy']['fields']['_search_epoch']['decimal'])+1)),
                lambda g:g['strategy']['fields']['_search_streams']['fields'].update(seed='7')]
            for i,alter in enumerate(changes):
                with self.subTest(index=index,change=i):
                    bad=deepcopy(body); self.replace_optimizer(row,bad,alter); self.reject_optimizer(bad)

    def test_cohort_genomes_results_and_selection_mirrors_cannot_be_rehashed(self):
        rows=self.extras['terminal']; index=len(rows)-2; self.prefix(rows,index); row=rows[index]; body=numbers.decode(row[2]); self.audit(row[2])
        for alter in (lambda g:g['cohort']['fields']['_genomes']['entries'][0][1]['fields']['ema_fast'].update(
            hex=(4.0 if g['cohort']['fields']['_genomes']['entries'][0][1]['fields']['ema_fast']['hex']==(3.0).hex() else 3.0).hex()),
            lambda g:g['cohort']['fields']['_evaluation_ids']['entries'][0].__setitem__(1,'foreign'),
            lambda g:g['cohort']['fields']['_evaluations']['entries'][0][1]['fields']['fitness'].update(hex=(1.0).hex()),
            lambda g:g['cohort']['fields']['_evaluations']['entries'].reverse(),
            lambda g:g['strategy']['fields']['_cohort']['fields']['_signatures']['entries'].reverse(),
            lambda g:g['strategy']['fields']['_cohort']['fields'].update(_bootstrap=False)):
            bad=deepcopy(body); self.replace_optimizer(row,bad,alter); self.assertNotEqual(body,bad); self.reject_optimizer(bad)

    def test_actual_tournament_parentage_and_full_birth_lineage_cannot_change(self):
        index=18; row=self.samples[index]; self.prefix(self.samples,index); body=numbers.decode(row[2]); self.audit(row[2])
        self.assertEqual({r['fitness_float64'] for r in body['history']['assessments']},{'0x0.0p+0'})
        # A tied completed window still uses the first member of each random
        # tournament, not the first member in the original or sorted cohort.
        bad=deepcopy(body); bad['history']['selection']['offspring'][0]['parent_ids'].reverse(); self.reject_optimizer(bad)
        for field,value in [('version',2),('operation','clone_mutation'),('source_iteration_id','foreign'),('offspring_index',7),('distribution_id',RUN)]:
            bad=deepcopy(body); birth=next(o for o in bad['operations'] if o['kind']=='birth'); birth['lineage'][field]=value
            self.reject_optimizer(bad,'optimizer_lineage_mismatch')
        bad=deepcopy(body); birth=next(o for o in bad['operations'] if o['kind']=='birth'); birth['lineage']['sources'].reverse()
        self.reject_optimizer(bad,'optimizer_lineage_mismatch')

    def test_founder_ordinary_restart_gene_and_name_controls_are_bound(self):
        cases=[(self.samples,0),(self.samples,1),(self.extras['controls'],len(self.extras['controls'])-2)]
        for rows,index in cases:
            self.prefix(rows,index); row=rows[index]; body=numbers.decode(row[2]); self.audit(row[2])
            bad=deepcopy(body)
            first=next(c.to_dict() for c in row[1].components if c.to_dict()['kind']=='genome')
            identity=first['entity_id']; old=first['body']['ema_fast']; value=(4.0 if float.fromhex(old)!=4 else 5.0).hex()
            original_hash=hashlib.sha256(numbers.encode(first)).hexdigest(); first['body']['ema_fast']=value; new_hash=hashlib.sha256(numbers.encode(first)).hexdigest()
            bad['components']=[c for c in bad['components'] if hashlib.sha256(numbers.encode(c)).hexdigest()!=original_hash]+[first]
            for ref in bad['checkpoint']['components']:
                if ref['sha256']==original_hash: ref['sha256']=new_hash
            for member in bad['history']['birth_members']:
                if member['id']==identity:member['genome']['ema_fast']=value
            def alter(g):
                for key,genome in g['cohort']['fields']['_genomes']['entries']:
                    if key==identity:genome['fields']['ema_fast']['hex']=value
                for key,signature in g['strategy']['fields']['_cohort']['fields']['_signatures']['entries']:
                    if key==identity:
                        for field,coordinate in signature['entries']:
                            if field=='ema_fast': coordinate['hex']=value
            self.replace_optimizer(row,bad,alter); self.reject_optimizer(bad)
            # A display name must consume its original generation/name prefix.
            bad=deepcopy(body); bad['checkpoint']['engine']['members'][0]['name']='invented'
            if index==0 or rows is not self.samples:
                for member in bad['history']['birth_members']:
                    if member['id']==bad['checkpoint']['engine']['members'][0]['id']: member['name']='invented'
            self.reject_optimizer(bad)

    def test_limit_installer_and_no_client_helper_or_table_capability(self):
        metadata=json.loads(self.db.scalar("""SELECT json_agg(x) FROM (SELECT p.proname,p.prosecdef,p.proconfig,r.rolname AS owner
          FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner
          WHERE n.nspname='vn_optimizer_research' ORDER BY p.proname)x;"""))
        self.assertEqual(len(metadata),22)
        self.assertTrue(all(r['owner']==INSTALLER and r['proconfig']==['search_path=pg_catalog'] for r in metadata))
        self.assertEqual([r['proname'] for r in metadata if r['prosecdef']],['validate_request'])
        for role in ('anon','authenticated','service_role','vn_economic_relay'):
            self.assertNotEqual(self.db.sql(self.sql(self.samples[0][2]),role=role,check=False).returncode,0)
        for statement in ("SELECT vn_optimizer_research.mt_seed(0);","SELECT vn_optimizer_research.graph('{}');",
            'SELECT * FROM vn_dependency_research.checkpoints;'):
            self.assertNotEqual(self.db.sql(statement,role=AUDITOR,check=False).returncode,0)

    def test_completed_mutation_is_explicitly_not_yet_authority(self):
        row=self.samples[18]; self.prefix(self.samples,18); body=numbers.decode(row[2]); self.audit(row[2])
        first=next(c.to_dict() for c in row[1].components if c.to_dict()['kind']=='genome'); identity=first['entity_id']
        old=hashlib.sha256(numbers.encode(first)).hexdigest(); value=(3.0 if first['body']['ema_fast']!=(3.0).hex() else 4.0).hex()
        first['body']['ema_fast']=value; new=hashlib.sha256(numbers.encode(first)).hexdigest()
        body['components']=[c for c in body['components'] if hashlib.sha256(numbers.encode(c)).hexdigest()!=old]+[first]
        for ref in body['checkpoint']['components']:
            if ref['sha256']==old:ref['sha256']=new
        for member in body['history']['birth_members']:
            if member['id']==identity:member['genome']['ema_fast']=value
        def alter(g):
            for key,genome in g['cohort']['fields']['_genomes']['entries']:
                if key==identity:genome['fields']['ema_fast']['hex']=value
            for key,signature in g['strategy']['fields']['_cohort']['fields']['_signatures']['entries']:
                if key==identity:
                    for field,coordinate in signature['entries']:
                        if field=='ema_fast':coordinate['hex']=value
        self.replace_optimizer(row,body,alter); result=self.audit(numbers.encode(body))
        self.assertFalse(result['optimizer_evidence']['completed_offspring_mutation_verified'])
        self.assertFalse(result['optimizer_evidence']['restoration_authority'])

    @unittest.skipUnless(os.environ.get('DASHBOARD_OPTIMIZER_MEASURE')=='1','Optional complete optimizer timing')
    def test_z_measure_full_boundary(self):
        chosen=[('bootstrap',self.samples,0),('quote',self.samples,1),('replacement',self.samples,18),
            ('early_terminal',self.extras['terminal'],len(self.extras['terminal'])-2),
            ('restart',self.extras['controls'],len(self.extras['controls'])-2),
            ('held_stop',self.extras['held_stop'],len(self.extras['held_stop'])-1)]
        measured=[]
        for kind,rows,index in chosen:
            self.prefix(rows,index); wire=rows[index][2]; before=self.snapshot()
            source=['SET plan_cache_mode=force_generic_plan;','CREATE TEMP TABLE timings(elapsed_us bigint);',
                'DO $m$ DECLARE t timestamptz;i integer;r jsonb;w text:='+literal(wire.decode())+
                '; BEGIN FOR i IN 1..10 LOOP t:=clock_timestamp();r:=vn_optimizer_research.validate_request('+literal(OWNER)+','+literal(RUN)+
                ',w); INSERT INTO timings VALUES(extract(epoch FROM clock_timestamp()-t)*1000000); END LOOP; END $m$;',
                "SELECT json_build_object('samples',count(*),'p50_us',percentile_cont(.5) WITHIN GROUP(ORDER BY elapsed_us),'p95_us',percentile_cont(.95) WITHIN GROUP(ORDER BY elapsed_us),'maximum_us',max(elapsed_us)) FROM timings;"]
            measured.append({'kind':kind,'wire_bytes':len(wire),**json.loads(self.db.scalar('\n'.join(source),role=AUDITOR,timeout=60))})
            self.assertEqual(self.snapshot(),before)
        self.assertEqual({name:hashlib.sha256((DIRECTORY/name).read_bytes()).hexdigest() for name in self.installed_sha256},self.installed_sha256)
        artifact={'date':'2026-10-12','identity':self.db.identity,'installed_sql_sha256':self.installed_sha256,'complete_commands':165,
            'scope':'economics/source/risk/assessment/graph/mirrors/founders/restart/selection RNG/parentage; completed Gaussian mutation pending',
            'tables_in_new_artifact':0,'writes_by_validator':0,'production_grants_or_install':False,'warm_server_validation_timings':measured,
            'timing_method':'10 full volatile wrapper calls; wire variable/generic plans; unchanged fixture prior; three resolutions',
            'timing_exclusions':['completed offspring Gaussian mutation proof','transport/TLS','contended locks','native journal/identity insertion/pins/projections',
                'final source/lease boundary','COMMIT/WAL/relay','hosted tails']}
        (ROOT/'research/optimizer-transition-measurements.json').write_text(json.dumps(artifact,indent=2,sort_keys=True)+'\n')
