"""Independent locked component resolution; fixture seeding is NOT a commit."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time
import unittest

from tests.postgres.harness import IsolatedPostgres, OPT_IN
from tests.measure_provider_ga_research import literal
from tests.test_partitioned_checkpoint import partition_trace
from tests.test_provider_contract import OWNER, RUN, WORKER, source_inputs
from vonneumann.research import numeric_wire as numbers
from vonneumann.research import partitioned_checkpoint as cp
from vonneumann.research import provider_ga_model as ga
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT/'db-contract'/'research'/'locked_checkpoint.sql'
NUMERIC = ROOT/'db-contract'/'research'/'numeric_wire.sql'
INSTALLER = 'vn_resolution_installer'
AUDITOR = 'vn_resolution_auditor'
RELAY = 'vn_resolution_relay'


@unittest.skipUnless(os.environ.get(OPT_IN)=='1', 'Requires isolated PostgreSQL opt-in')
class LockedCheckpointSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = []
        partition_trace(True, windows=2,
            observer=lambda c,o,ow,p,w: cls.samples.append((c,p,w)))
        cls.db = IsolatedPostgres().start()
        try:
            cls.db.sql(f'''CREATE ROLE {INSTALLER} LOGIN NOSUPERUSER NOCREATEDB
              NOCREATEROLE NOINHERIT NOBYPASSRLS;
              CREATE ROLE {AUDITOR} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
              CREATE ROLE {RELAY} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
              GRANT CREATE ON DATABASE postgres TO {INSTALLER};''')
            denied = cls.db.sql(SQL.read_text(), role=INSTALLER, check=False)
            if denied.returncode == 0 or 'offline_locked_checkpoint_fixture_required' not in denied.stderr:
                raise AssertionError('Resolution installed without its offline guard')
            cls.db.sql("BEGIN; SET dashboard.numeric_wire_fixture='offline-v1';"+
                NUMERIC.read_text()+"SET dashboard.locked_checkpoint_fixture='offline-v1';"+
                SQL.read_text()+'COMMIT;', role=INSTALLER)
            cls.db.sql(f'''GRANT USAGE ON SCHEMA vn_dependency_research TO {AUDITOR};
              GRANT EXECUTE ON FUNCTION vn_dependency_research.resolve_request(uuid,uuid,text)
              TO {AUDITOR};''', role=INSTALLER)
        except BaseException:
            cls.db.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.sql('DELETE FROM vn_dependency_research.components; DELETE FROM vn_dependency_research.checkpoints;')
        self.db.sql(f'INSERT INTO vn_dependency_research.checkpoints VALUES({literal(RUN)},{literal(OWNER)},1,NULL);')

    def request_sql(self, wire, owner=OWNER, run=RUN):
        return 'SELECT vn_dependency_research.resolve_request('+','.join(
            (literal(owner), literal(run), literal(wire.decode())))+');'

    def resolve(self, wire):
        return json.loads(self.db.scalar(self.request_sql(wire), role=AUDITOR))

    def seed(self, capture):
        # Explicit privileged test operation; resolver does not accept/commit state.
        rows = ','.join('('+','.join((literal(OWNER),literal(RUN),
            literal(b.identity),literal(b._wire.decode())))+')' for b in capture.components)
        self.db.sql(f'''BEGIN;
          INSERT INTO vn_dependency_research.components VALUES {rows} ON CONFLICT DO NOTHING;
          UPDATE vn_dependency_research.checkpoints SET revision={capture.to_dict()['revision']},
            manifest_wire={literal(numbers.encode(capture.to_dict()).decode())} WHERE run_id={literal(RUN)};
          COMMIT;''')

    def snapshot(self):
        return self.db.scalar("""SELECT jsonb_build_object(
          'checkpoints',(SELECT jsonb_agg(to_jsonb(c) ORDER BY run_id) FROM vn_dependency_research.checkpoints c),
          'components',(SELECT jsonb_agg(to_jsonb(c) ORDER BY sha256) FROM vn_dependency_research.components c));""")

    def reject(self, body, expected=None, owner=OWNER, run=RUN):
        before = self.snapshot()
        wire = body if type(body) is bytes else numbers.encode(body)
        denied = self.db.sql(self.request_sql(wire, owner, run), role=AUDITOR, check=False)
        self.assertNotEqual(denied.returncode, 0)
        if expected is not None:
            self.assertIn(expected, denied.stderr)
        self.assertEqual(self.snapshot(), before)

    @staticmethod
    def replace_block(body, kind, mutate):
        index = next(i for i,b in enumerate(body['components']) if b['kind']==kind)
        block = body['components'][index]
        old = hashlib.sha256(numbers.encode(block)).hexdigest()
        mutate(block)
        new = hashlib.sha256(numbers.encode(block)).hexdigest()
        ref = next(r for r in body['checkpoint']['components'] if r['sha256']==old)
        ref.update(kind=block['kind'],entity_id=block['entity_id'],
            generation=block['generation'],sha256=new)

    def test_independent_expansion_matches_complete_owned_state_for_two_windows(self):
        previous = None
        before = self.snapshot()
        for candidate,capture,wire in self.samples:
            result = self.resolve(wire)
            self.assertEqual(result['command_sha256'], hashlib.sha256(wire).hexdigest())
            self.assertEqual(result['following']['manifest_sha256'],
                hashlib.sha256(numbers.encode(capture.to_dict())).hexdigest())
            self.assertEqual(numbers.encode(capture.resolve()),
                result['following']['wire'].encode())
            if previous is None:
                self.assertIsNone(result['prior'])
            else:
                self.assertEqual(numbers.encode(previous.resolve()), result['prior']['wire'].encode())
            self.assertLessEqual(result['following']['dependency_bytes'],262144)
            self.assertEqual(self.snapshot(), before)
            self.seed(capture)
            before = self.snapshot()
            previous = capture
        self.assertEqual(len(self.samples),35)
        self.assertEqual(previous.to_dict()['engine']['generation'],2)
        self.assertGreater(int(self.db.scalar('SELECT count(*) FROM vn_dependency_research.components;')),13)

    def test_actual_limited_installer_and_only_resolver_capability(self):
        rows = json.loads(self.db.scalar("""SELECT json_agg(x) FROM (
          SELECT p.proname,r.rolname AS owner,p.prosecdef,p.proconfig FROM pg_proc p
          JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner
          WHERE n.nspname='vn_dependency_research' ORDER BY p.proname)x;"""))
        self.assertEqual(len(rows),7)
        self.assertTrue(all(r['owner']==INSTALLER and r['proconfig']==['search_path=pg_catalog'] for r in rows))
        self.assertEqual([r['proname'] for r in rows if r['prosecdef']], ['resolve_request'])
        self.assertEqual(self.db.scalar(f"SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls FROM pg_roles WHERE rolname='{INSTALLER}';"),'f')
        for role in ('anon','authenticated','service_role',RELAY):
            denied = self.db.sql(self.request_sql(self.samples[0][2]),role=role,check=False)
            self.assertNotEqual(denied.returncode,0)
        for statement in (
            'SELECT * FROM vn_dependency_research.checkpoints;',
            'SELECT * FROM vn_dependency_research.components;',
            "SELECT vn_dependency_research.counter('{\"$integer\":\"1\"}',0,2);",
            "SELECT vn_numeric_research.audit('{}');",
            'CREATE SCHEMA forbidden_resolution_schema;'):
            self.assertNotEqual(self.db.sql(statement,role=AUDITOR,check=False).returncode,0)
        self.assertEqual(self.db.scalar("""SELECT NOT EXISTS(SELECT 1 FROM pg_proc p,
          LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE
          p.pronamespace='vn_dependency_research'::regnamespace AND a.grantee=0
          AND a.privilege_type='EXECUTE');"""),'t')

    def test_original_wire_scope_and_format_fail_closed(self):
        body = numbers.decode(self.samples[0][2])
        for field,value in (('owner_id',WORKER),('run_id',WORKER),
            ('command_id','00000000-0000-0000-0000-00000000ABCD'),('format',cp.FORMAT)):
            changed = deepcopy(body); changed[field]=value
            self.reject(changed)
        changed=deepcopy(body); changed['owner_id']=WORKER
        self.reject(changed, 'checkpoint_run_unavailable', owner=WORKER)
        changed=deepcopy(body); changed['run_id']=WORKER
        self.reject(changed, 'checkpoint_run_unavailable', run=WORKER)
        self.reject(self.samples[0][2]+b' ', 'numeric_wire_noncanonical')
        changed = deepcopy(body); changed['extra']=None
        self.reject(changed,'checkpoint_keys_differ')
        changed = deepcopy(body); changed['components'].append(changed['components'][0])
        self.reject(changed,'checkpoint_request_capacity')

    def test_exact_prior_hash_revision_and_bootstrap_rules(self):
        boot,quote = self.samples[:2]
        body = numbers.decode(boot[2]); body['prior']={'revision':1,'sha256':'0'*64}
        self.reject(body,'checkpoint_bootstrap_prior')
        self.reject(numbers.decode(quote[2]),'checkpoint_bootstrap_prior')
        self.seed(boot[1])
        body = numbers.decode(quote[2])
        for change in ({'sha256':'0'*64},{'revision':3},{'revision':True}):
            bad = deepcopy(body); bad['prior'].update(change)
            self.reject(bad)
        bad = deepcopy(body); bad['prior']=None
        self.reject(bad,'checkpoint_object_required')
        bad = deepcopy(body); bad['checkpoint']['revision']=4
        self.reject(bad,'checkpoint_manifest_binding')
        self.seed(quote[1])
        self.reject(body,'checkpoint_prior_mismatch')

    def test_missing_duplicate_unreferenced_and_foreign_components(self):
        body = numbers.decode(self.samples[0][2])
        bad = deepcopy(body); bad['components'].pop()
        self.reject(bad,'checkpoint_missing_or_duplicate_reference')
        bad = deepcopy(body); bad['components'][-1]=bad['components'][0]
        self.reject(bad,'checkpoint_duplicate_supplied_component')
        bad = deepcopy(body); bad['checkpoint']['components'][-1]=bad['checkpoint']['components'][0]
        self.reject(bad,'checkpoint_unused_supplied_component')
        for field in ('owner_id','run_id'):
            bad = deepcopy(body); bad['components'][0][field]=WORKER
            self.reject(bad,'checkpoint_component_scope_or_format')
        bad = deepcopy(body)
        self.replace_block(bad,'ema',lambda b:b.update(format='ga-provider-component-research-v1'))
        self.reject(bad,'checkpoint_component_scope_or_format')
        bad = deepcopy(body); bad['checkpoint']['components'][0]['sha256']='A'*64
        self.reject(bad,'checkpoint_reference_digest')

    def test_slot_generation_member_and_model_identity_are_independent(self):
        body = numbers.decode(self.samples[0][2])
        for field,value in (('format','ga-provider-checkpoint-research-v1'),
                            ('source_model_version','native-v6'),('revision',True)):
            bad = deepcopy(body); bad['checkpoint'][field]=value
            self.reject(bad)
        bad = deepcopy(body); bad['checkpoint']['engine']['members'][-1]=bad['checkpoint']['engine']['members'][0]
        self.reject(bad,'checkpoint_duplicate_member')
        bad = deepcopy(body); bad['checkpoint']['engine']['ema']={}
        self.reject(bad,'checkpoint_keys_differ')
        bad = deepcopy(body); bad['checkpoint']['source']['bars']=[]
        self.reject(bad,'checkpoint_engine_slots')
        for kind in ('configuration','source_bars','ema','genome'):
            bad = deepcopy(body)
            self.replace_block(bad,kind,lambda b:b.update(generation=1))
            self.reject(bad)
        for kind,mutate in (
            ('configuration',lambda b:b['body'].update(strategy='cma_es')),
            ('optimizer',lambda b:b['body']['strategy'].update({'class':'CMAESStrategy'})),
            ('cohort',lambda b:b['body'].update(member_ids=list(reversed(b['body']['member_ids'])))),
            ('cohort',lambda b:b['body'].update(iteration_id='different:0')),
            ('cohort',lambda b:b['body'].update(member_count=True))):
            bad = deepcopy(body); self.replace_block(bad,kind,mutate)
            self.reject(bad)

    def test_retained_prior_cannot_be_repaired_by_caller_supplied_blocks(self):
        boot,quote = self.samples[:2]
        self.seed(boot[1])
        missing = boot[1].components[-1]
        self.db.sql(f"DELETE FROM vn_dependency_research.components WHERE sha256={literal(missing.identity)};")
        body = numbers.decode(quote[2]); body['components']=[missing.to_dict()]
        self.reject(body,'checkpoint_missing_or_duplicate_reference')
        # Even a valid hashed component stored under the correct table scope must
        # validate its ORIGINAL embedded scope when used.
        self.setUp()
        self.seed(boot[1])
        block = missing.to_dict(); block['owner_id']=WORKER
        wire = numbers.encode(block); digest=hashlib.sha256(wire).hexdigest()
        manifest = boot[1].to_dict()
        manifest['components'][-1]['sha256']=digest
        self.db.sql('INSERT INTO vn_dependency_research.components VALUES('+','.join(
            (literal(OWNER),literal(RUN),literal(digest),literal(wire.decode())))+');'+
            f"UPDATE vn_dependency_research.checkpoints SET manifest_wire={literal(numbers.encode(manifest).decode())};")
        body = numbers.decode(quote[2])
        body['prior']['sha256']=hashlib.sha256(numbers.encode(manifest)).hexdigest()
        self.reject(body,'checkpoint_component_scope_or_format')

    def test_configuration_cannot_change_across_the_exact_prior(self):
        self.seed(self.samples[0][1])
        body = numbers.decode(self.samples[1][2])
        block = deepcopy(self.samples[0][1].components[0].to_dict())
        block['body']['research_note']='changed'
        body['components']=[block]
        body['checkpoint']['components'][0]['sha256']=hashlib.sha256(numbers.encode(block)).hexdigest()
        self.reject(body,'checkpoint_prior_model_binding')

    def test_dependency_and_request_capacity_charge_retained_components(self):
        boot,quote = self.samples[:2]
        self.seed(boot[1])
        manifest = boot[1].to_dict()
        for index,kind in ((11,'source_bars'),(12,'ema')):
            block=boot[1].components[index].to_dict()
            block['body']={'bars':[], 'padding':['x'*14000]*10} if kind=='source_bars' else {'padding':['x'*14000]*10}
            wire=numbers.encode(block); digest=hashlib.sha256(wire).hexdigest()
            manifest['components'][index]['sha256']=digest
            self.db.sql('INSERT INTO vn_dependency_research.components VALUES('+','.join(
                (literal(OWNER),literal(RUN),literal(digest),literal(wire.decode())))+');')
        # source_bars rejects invented fields before expanded use; first test the
        # aggregate on the large EMA + canonical bars body without extra keys.
        block=boot[1].components[11].to_dict(); block['body']['bars']=[['x'*14000]]*10
        wire=numbers.encode(block); digest=hashlib.sha256(wire).hexdigest()
        manifest['components'][11]['sha256']=digest
        self.db.sql('INSERT INTO vn_dependency_research.components VALUES('+','.join(
            (literal(OWNER),literal(RUN),literal(digest),literal(wire.decode())))+');')
        self.db.sql(f"UPDATE vn_dependency_research.checkpoints SET manifest_wire={literal(numbers.encode(manifest).decode())};")
        body=numbers.decode(quote[2]); body['prior']['sha256']=hashlib.sha256(numbers.encode(manifest)).hexdigest()
        self.reject(body,'checkpoint_dependency_capacity')
        self.reject(b'x'*262145,'numeric_wire_byte_capacity')

    def test_reserved_revision_requires_stop_shape_and_counters_are_exact(self):
        boot,quote=self.samples[:2]; self.seed(boot[1])
        maximum=2**63-1
        manifest=boot[1].to_dict(); manifest['revision']=maximum-1
        self.db.sql(f"UPDATE vn_dependency_research.checkpoints SET revision={maximum-1},manifest_wire={literal(numbers.encode(manifest).decode())};")
        body=numbers.decode(quote[2]); body['prior']={'revision':maximum-1,
            'sha256':hashlib.sha256(numbers.encode(manifest)).hexdigest()}
        body['checkpoint']['revision']=maximum
        self.reject(body,'checkpoint_stop_revision_reserved')
        body['evidence']['kind']='control'; body['evidence']['control']={'action':'stop'}
        body['checkpoint']['status']='stopped'
        self.resolve(numbers.encode(body)) # Shape/numeric proof ONLY, not Stop admission.
        self.db.sql(f"UPDATE vn_dependency_research.checkpoints SET revision={maximum};")
        self.reject(body,'checkpoint_revision_exhausted')

    def test_prior_is_read_after_waiting_for_run_lock(self):
        boot,quote=self.samples[:2]; self.seed(boot[1])
        marker='dependency-prior-holder'
        holder=self.db.begin_sql(f"BEGIN; SET application_name='{marker}'; "
            f"SELECT run_id FROM vn_dependency_research.checkpoints WHERE run_id={literal(RUN)} FOR UPDATE; "
            f"SELECT pg_sleep(1.5); UPDATE vn_dependency_research.checkpoints SET revision=3,"
            f"manifest_wire={literal(numbers.encode(quote[1].to_dict()).decode())} WHERE run_id={literal(RUN)}; COMMIT;")
        self.wait_barrier(marker,'PgSleep')
        waiting=self.db.begin_sql(self.request_sql(quote[2]),role=AUDITOR)
        holder.wait()
        denied=waiting.wait(check=False)
        self.assertIn('checkpoint_prior_mismatch',denied.stderr)
        self.assertEqual(self.db.scalar('SELECT revision FROM vn_dependency_research.checkpoints;'),'3')

    def wait_barrier(self, marker, event):
        deadline=time.monotonic()+4
        while self.db.scalar(f"SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name={literal(marker)} AND wait_event={literal(event)});")!='t':
            if time.monotonic()>=deadline:
                raise AssertionError('Owned SQL session missed its barrier')
            time.sleep(.02)

    def test_repeatable_read_rejects_concurrently_changed_prior(self):
        boot,quote=self.samples[:2]; self.seed(boot[1])
        marker='dependency-repeatable-holder'
        holder=self.db.begin_sql(f"BEGIN; SET application_name='{marker}'; "
            f"SELECT run_id FROM vn_dependency_research.checkpoints WHERE run_id={literal(RUN)} FOR UPDATE; "
            f"SELECT pg_sleep(1.5); UPDATE vn_dependency_research.checkpoints SET revision=3,"
            f"manifest_wire={literal(numbers.encode(quote[1].to_dict()).decode())} WHERE run_id={literal(RUN)}; COMMIT;")
        self.wait_barrier(marker,'PgSleep')
        waiting=self.db.begin_sql('BEGIN ISOLATION LEVEL REPEATABLE READ; '
            'SELECT 1 FROM vn_dependency_research.checkpoints;'+self.request_sql(quote[2])+
            'COMMIT;',role=INSTALLER)
        holder.wait()
        denied=waiting.wait(check=False)
        self.assertIn('could not serialize access due to concurrent update',denied.stderr)
        self.assertEqual(self.db.scalar('SELECT revision FROM vn_dependency_research.checkpoints;'),'3')

    def test_resolver_holds_run_and_retained_rows_until_transaction_end(self):
        boot,quote=self.samples[:2]; self.seed(boot[1])
        marker='dependency-resolution-holder'
        holder=self.db.begin_sql(f"BEGIN; SET application_name='{marker}';"+
            self.request_sql(quote[2])+"SELECT pg_sleep(1.5); COMMIT;",role=AUDITOR)
        self.wait_barrier(marker,'PgSleep')
        block=boot[1].components[-1]
        for statement in (
            f"UPDATE vn_dependency_research.checkpoints SET revision=revision+1 WHERE run_id={literal(RUN)};",
            f"DELETE FROM vn_dependency_research.components WHERE sha256={literal(block.identity)};"):
            denied=self.db.sql("SET lock_timeout='150ms';"+statement,check=False)
            self.assertIn('lock timeout',denied.stderr)
        holder.wait()
        self.assertEqual(self.db.scalar('SELECT revision FROM vn_dependency_research.checkpoints;'),'2')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_dependency_research.components;'),'13')

    def test_reference_order_and_typed_mismatch_are_checked_without_losing_evidence(self):
        body=numbers.decode(self.samples[0][2])
        changed=deepcopy(body); changed['components'].reverse()
        changed['checkpoint']['components'].reverse()
        result=self.resolve(numbers.encode(changed))
        self.assertEqual(result['following']['wire'].encode(),numbers.encode(self.samples[0][1].resolve()))
        for field,value in (('kind','genome'),('entity_id',WORKER),('generation',True)):
            changed=deepcopy(body); changed['checkpoint']['components'][0][field]=value
            self.reject(changed,'checkpoint_reference_binding')
        changed=deepcopy(body); changed['checkpoint']['engine']['members'][0]['id']=WORKER
        self.reject(changed,'checkpoint_reference_slot_or_generation')

    def test_real_stop_preserves_eight_holdings_and_exact_interrupted_evidence(self):
        ledger=ga.SimulationLedger(OWNER,RUN)
        for candidate,capture,_ in self.samples:
            state=ledger.accept(candidate)
            if state.to_dict()['positions']:
                prior=capture
                break
        self.assertEqual(len(state.to_dict()['positions']),8)
        self.seed(prior)
        at=state.to_dict()['engine']['last_quote']['timestamp']+1
        stopped=ga.prepare_control(state,'stop',source_inputs(at,serial=700),ledger=ledger)
        capture=cp.capture_owned_candidate(stopped)
        wire=cp.prepare_transport(stopped,capture,command_id=str(UUID(int=701)),previous=prior)
        before=self.snapshot()
        result=self.resolve(wire)
        self.assertEqual(result['following']['wire'].encode(),numbers.encode(capture.resolve()))
        self.assertEqual(numbers.decode(result['following']['wire'].encode())['positions'],state.to_dict()['positions'])
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(numbers.decode(wire)['history']['closed_positions'],[])
        self.assertTrue(all(a['status']=='aborted' and a['fitness_float64'] is None
            for a in stopped.history['assessments']))

    def test_resolution_is_explicitly_not_economic_source_or_history_admission(self):
        # Deliberate boundary test: bytes/slots can be valid while economics and
        # original event/history/source evidence are invalid. No commit occurs.
        body=numbers.decode(self.samples[0][2])
        body['checkpoint']['reserve']='invalid-money'
        body['operations']=[]; body['history']={}; body['events']=[]
        body['evidence']={'unvalidated_source':'not-a-provider'}
        before=self.snapshot()
        result=self.resolve(numbers.encode(body))
        resolved=numbers.decode(result['following']['wire'].encode())
        self.assertEqual(resolved['reserve'],'invalid-money')
        self.assertEqual(self.snapshot(),before)

    @unittest.skipUnless(os.environ.get('DASHBOARD_LOCKED_CHECKPOINT_MEASURE')=='1',
                         'Optional server measurement requires explicit opt-in')
    def test_z_measure_full_locked_resolution_without_committing(self):
        largest=max(range(len(self.samples)),key=lambda i:len(self.samples[i][2]))
        chosen=[('bootstrap',0),('quote',1),('replacement',largest)]
        measurements=[]
        for kind,index in chosen:
            self.setUp()
            if index:
                self.seed(self.samples[index-1][1])
            wire=self.samples[index][2]
            result=self.resolve(wire)
            before=self.snapshot()
            sql=["SET plan_cache_mode=force_generic_plan;",
                'CREATE TEMP TABLE timings(elapsed_us bigint);',
                'DO $measure$ DECLARE t timestamptz;i integer;r jsonb;w text:='+
                literal(wire.decode())+';BEGIN FOR i IN 1..30 LOOP '+
                't:=clock_timestamp(); r:=vn_dependency_research.resolve_request('+
                literal(OWNER)+','+literal(RUN)+',w); INSERT INTO timings VALUES ('+
                'extract(epoch FROM clock_timestamp()-t)*1000000); END LOOP; END $measure$;',
                """SELECT json_build_object('samples',count(*),
                  'p50_us',percentile_cont(.5) WITHIN GROUP(ORDER BY elapsed_us),
                  'p95_us',percentile_cont(.95) WITHIN GROUP(ORDER BY elapsed_us),
                  'maximum_us',max(elapsed_us)) FROM timings;"""]
            timing=json.loads(self.db.scalar('\n'.join(sql),role=AUDITOR,timeout=60))
            measurements.append({'kind':kind,'request_bytes':len(wire),
                'following_dependency_bytes':result['following']['dependency_bytes'],
                'following_resolved_bytes':result['following']['resolved_bytes'],**timing})
            self.assertEqual(self.snapshot(),before)
        value={'date':'2026-10-11','identity':self.db.identity,
            'sql_sha256':hashlib.sha256(SQL.read_bytes()).hexdigest(),
            'numeric_sql_sha256':hashlib.sha256(NUMERIC.read_bytes()).hexdigest(),
            'complete_commands':len(self.samples),'generations_replaced':2,
            'component_slots':13,'scope':'offline read-only locked prior/component/slot/model-identity resolution only',
            'warm_server_resolution_timings':measurements,
            'timing_method':'30 full volatile resolver calls with a PL/pgSQL wire variable and force_generic_plan; unchanged synthetic prior between calls',
            'timing_exclusions':['transport/TLS','contended lock wait',
                'full economic/source/history/lineage admission','journal/dependency-pin/projection writes',
                'final source/lease recheck','COMMIT/WAL/relay','hosted tails'],
            'tables_in_installed_artifact':2,'writes_by_resolver':0,
            'production_grants_or_install':False}
        (ROOT/'research'/'locked-checkpoint-measurements.json').write_text(
            json.dumps(value,indent=2,sort_keys=True)+'\n')
