"""Owned offline original-v2 atomic journal/catalog/actor/native fixture."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import time
import unittest
from uuid import UUID

from tests.postgres.harness import IsolatedPostgres,OPT_IN
from tests.postgres.test_portable_transition import FILES,INSTALLER
from tests.measure_provider_ga_research import literal
from tests.test_provider_contract import OWNER,RUN,WORKER,EPOCH,MONO,raw_minutes,raw_capture,source_inputs
from vonneumann.research import provider_portable_ga_model as ga,portable_partitioned_checkpoint as cp,numeric_wire as numbers

ROOT=Path(__file__).resolve().parents[2]
DIRECTORY=ROOT/'db-contract/research'
NATIVE=DIRECTORY/'portable_native.sql'
ACTOR='vn_portable_native_worker_a'
OTHER='vn_portable_native_worker_b'
OTHER_RUN=str(UUID(int=93007121))


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class PortableNativeSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=IsolatedPostgres().start()
        try:
            cls.db.sql(f'''CREATE ROLE {INSTALLER} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
             CREATE ROLE {ACTOR} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
             CREATE ROLE {OTHER} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
             GRANT CREATE ON DATABASE postgres TO {INSTALLER};''')
            for filename,setting,marker in FILES:
                cls.db.sql(f"BEGIN; SET dashboard.{setting}='{marker}';"+(DIRECTORY/filename).read_text()+'COMMIT;',role=INSTALLER)
            denied=cls.db.sql(NATIVE.read_text(),role=INSTALLER,check=False)
            if denied.returncode==0 or 'offline_portable_native_fixture_required' not in denied.stderr:raise AssertionError('Native artifact installed without offline guard')
            cls.db.sql("BEGIN; SET dashboard.portable_native_fixture='offline-v2';"+NATIVE.read_text()+'COMMIT;',role=INSTALLER)
            cls.db.sql(f'''INSERT INTO vn_portable_native_research.actor_bindings VALUES
             ('{ACTOR}',{literal(OWNER)},{literal(RUN)},true),('{OTHER}',{literal(WORKER)},{literal(OTHER_RUN)},true);
             GRANT USAGE ON SCHEMA vn_portable_native_research TO {ACTOR},{OTHER};
             GRANT EXECUTE ON FUNCTION vn_portable_native_research.create_run(uuid,uuid,uuid,integer),
              vn_portable_native_research.heartbeat(uuid,uuid,uuid,bigint,integer),
              vn_portable_native_research.commit_command(uuid,uuid,uuid,bigint,text),
              vn_portable_native_research.get_command(uuid,uuid,uuid,text),
              vn_portable_native_research.read_checkpoint(uuid,uuid,bigint,text),
              vn_portable_native_research.lookup_identity_ids(uuid,uuid,bigint,text,jsonb) TO {ACTOR},{OTHER};
             INSERT INTO vn_portable_native_research.package_manifest SELECT true,vn_portable_native_research.catalog_fingerprint();''',role=INSTALLER)
        except BaseException:cls.db.close();raise

    @classmethod
    def tearDownClass(cls):cls.db.close()

    def setUp(self):
        self.db.sql('''DELETE FROM vn_portable_native_research.events;
          DELETE FROM vn_portable_native_research.history_projection;
          DELETE FROM vn_portable_native_research.active_projection;
          DELETE FROM vn_portable_native_research.dependency_pins;
          DELETE FROM vn_portable_native_research.commands;
          DELETE FROM vn_portable_native_research.runs;
          DELETE FROM vn_portable_semantic_research.accepted_heads;
          DELETE FROM vn_portable_semantic_research.accepted_commands;
          DELETE FROM vn_portable_economic_research.allocated;
          DELETE FROM vn_portable_dependency_research.components;
          DELETE FROM vn_portable_dependency_research.checkpoints;''')

    def create(self,lease=60):
        return self.db.sql('SELECT vn_portable_native_research.create_run('+','.join((literal(OWNER),literal(RUN),literal(WORKER),str(lease)))+');',role=ACTOR)

    def bootstrap(self,*,clock_offset=0,end_lag=0):
        now=int(self.db.scalar('SELECT floor(extract(epoch FROM clock_timestamp()));'))+clock_offset
        end=(now-5)//900*900-end_lag
        history=ga.source.build_history(raw_minutes(end=end,count=61*15,close='80',wall=now,mono=MONO),
            prior_bars=[],seed=True,wall_us=now*1000000,monotonic_us=int(MONO*1000000))
        ledger=ga.SimulationLedger(OWNER,RUN)
        candidate=ga.bootstrap(ga.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=EPOCH),history,source_inputs(now),ledger=ledger)
        capture=cp.capture_owned_candidate(candidate)
        wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=96000002)))
        return candidate,capture,wire,ledger

    def sql(self,wire,*,owner=OWNER,run=RUN,worker=WORKER,fence=1):
        return 'SELECT vn_portable_native_research.commit_command('+','.join((literal(owner),literal(run),literal(worker),str(fence),literal(wire.decode())))+');'

    def commit(self,wire):
        result=self.db.sql('BEGIN;'+self.sql(wire)+'COMMIT;',role=ACTOR,timeout=30)
        return json.loads(result.stdout.strip())

    def read(self,row):
        return json.loads(self.db.scalar('SELECT vn_portable_native_research.get_command('+','.join((literal(OWNER),literal(RUN),literal(numbers.decode(row[2])['command_id']),literal(hashlib.sha256(row[2]).hexdigest())))+');',role=ACTOR))

    def manifest_sha(self,row):return hashlib.sha256(numbers.encode(row[1].to_dict())).hexdigest()

    def checkpoint(self,row):
        return json.loads(self.db.scalar('SELECT vn_portable_native_research.read_checkpoint('+','.join((
            literal(OWNER),literal(RUN),str(row[0].state.revision),literal(self.manifest_sha(row))))+');',role=ACTOR))

    def lookup(self,row,ids,*,revision=None,digest=None):
        return 'SELECT vn_portable_native_research.lookup_identity_ids('+','.join((
            literal(OWNER),literal(RUN),str(row[0].state.revision if revision is None else revision),
            literal(self.manifest_sha(row) if digest is None else digest),literal(json.dumps(ids))+'::jsonb'))+');'

    def control(self,row,action,*,serial=10):
        ledger=row[3];state=ledger.accept(row[0]);inputs=row[0].transition['evidence']['inputs']
        at=int(datetime.fromisoformat(inputs['event_at']).timestamp())+1
        candidate=ga.prepare_control(state,action,source_inputs(at,mono=float.fromhex(inputs['monotonic_at'])+1,serial=serial),ledger=ledger)
        capture=cp.capture_owned_candidate(candidate)
        wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=96000000+candidate.state.revision)),previous=row[1])
        return candidate,capture,wire,ledger

    def snapshot(self):
        tables=('vn_portable_native_research.runs','vn_portable_native_research.commands',
            'vn_portable_native_research.dependency_pins','vn_portable_native_research.active_projection',
            'vn_portable_native_research.history_projection','vn_portable_native_research.events',
            'vn_portable_semantic_research.accepted_heads','vn_portable_semantic_research.accepted_commands',
            'vn_portable_economic_research.allocated','vn_portable_dependency_research.components',
            'vn_portable_dependency_research.checkpoints')
        pairs=','.join(literal(table)+',coalesce((SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text COLLATE "C") FROM '+table+" t),'[]'::jsonb)" for table in tables)
        return self.db.scalar('SELECT jsonb_build_object('+pairs+');')

    def reject_sql(self,source,expected,*,role=ACTOR):
        before=self.snapshot();result=self.db.sql(source,role=role,check=False,timeout=30)
        self.assertNotEqual(result.returncode,0,result.stdout)
        self.assertIn(expected,result.stderr)
        self.assertEqual(self.snapshot(),before)
        return result

    def test_actual_catalog_bound_bootstrap_journal_pins_and_readback(self):
        self.create();row=self.bootstrap();reply=self.commit(row[2])
        self.assertTrue(reply['pending_until_commit']);self.assertFalse(reply['record_observed'])
        observed=self.read(row);self.assertTrue(observed['found']);self.assertTrue(observed['receipt']['record_observed'])
        self.assertEqual(observed['original_command_wire'].encode(),row[2])
        self.assertIsNotNone(observed['receipt']['guard_observed_at'])
        self.assertFalse(observed['receipt']['final_visible_instant_freshness'])
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_portable_native_research.commands;'),'1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_portable_native_research.dependency_pins;'),'13')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_portable_native_research.history_projection;'),'1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_portable_native_research.events;'),'9')
        digest=hashlib.sha256(numbers.encode(row[1].to_dict())).hexdigest()
        envelope=json.loads(self.db.scalar('SELECT vn_portable_native_research.read_checkpoint('+','.join((literal(OWNER),literal(RUN),'2',literal(digest)))+');',role=ACTOR))
        self.assertEqual(envelope['manifest_wire'].encode(),numbers.encode(row[1].to_dict()))
        self.assertEqual([w.encode() for w in envelope['component_wires']],[b._wire for b in row[1].components])
        self.assertFalse(envelope['restoration_authority']);self.assertFalse(envelope['hosted_authority'])

    def test_scoped_readback_ignores_benign_temporary_catalog_sentinels(self):
        self.create();row=self.bootstrap();self.commit(row[2])
        command_id=numbers.decode(row[2])['command_id']
        get_sql='SELECT vn_portable_native_research.get_command('+','.join((
            literal(OWNER),literal(RUN),literal(command_id),literal(hashlib.sha256(row[2]).hexdigest())))+');'
        # A raising sentinel detects accidental relation lookup. It performs no
        # private-table writes, permission changes, or external operations.
        source='''CREATE TEMP TABLE portable_catalog_sentinel_seed(value integer);
          CREATE FUNCTION pg_temp.portable_catalog_sentinel() RETURNS boolean
          LANGUAGE plpgsql AS $sentinel$ BEGIN
            RAISE EXCEPTION 'portable_native_benign_catalog_sentinel_called';
          END $sentinel$;
          CREATE TEMP VIEW pg_namespace AS
            SELECT n.* FROM pg_catalog.pg_namespace n
            WHERE pg_temp.portable_catalog_sentinel();
          CREATE TEMP VIEW pg_roles AS
            SELECT r.* FROM pg_catalog.pg_roles r
            WHERE pg_temp.portable_catalog_sentinel();
        '''+get_sql
        response=self.db.sql(source,role=ACTOR,timeout=30)
        observed=json.loads(response.stdout.strip())
        self.assertTrue(observed['found'])
        self.assertEqual(observed['original_command_wire'].encode(),row[2])
        self.assertNotIn('portable_native_benign_catalog_sentinel_called',response.stderr)

    def test_getter_does_not_distinguish_another_owner_id_from_absence(self):
        self.create();row=self.bootstrap();self.commit(row[2])
        ids=(numbers.decode(row[2])['command_id'],str(UUID(int=96000009)))
        responses=[]
        for command_id in ids:
            response=self.db.scalar('SELECT vn_portable_native_research.get_command('+','.join((
                literal(WORKER),literal(OTHER_RUN),literal(command_id),literal(hashlib.sha256(row[2]).hexdigest())))+');',role=OTHER)
            responses.append(json.loads(response))
        self.assertEqual(responses[0],responses[1])
        self.assertFalse(responses[0]['found'])

    def test_worker_scope_and_private_capabilities_are_server_owned(self):
        self.create();row=self.bootstrap()
        self.reject_sql('BEGIN;'+self.sql(row[2],owner=WORKER,run=OTHER_RUN)+'COMMIT;','portable_native_actor_scope')
        self.reject_sql('BEGIN;'+self.sql(row[2])+'COMMIT;','portable_native_actor_scope',role=OTHER)
        for table in ('actor_bindings','package_manifest','runs','commands','dependency_pins','active_projection','history_projection','events'):
            with self.subTest(table=table):
                self.reject_sql('SELECT * FROM vn_portable_native_research.'+table+';','permission denied')
        for helper in ('assert_package()','catalog_fingerprint()','assert_session()'):
            with self.subTest(helper=helper):
                self.reject_sql('SELECT vn_portable_native_research.'+helper+';','permission denied')
        self.reject_sql('SELECT vn_portable_semantic_research.advance_fixture('+','.join((
            literal(OWNER),literal(RUN),literal(row[2].decode())))+');','permission denied')
        self.reject_sql('CREATE TABLE vn_portable_native_research.unowned_table(value integer);','permission denied')
        functions=json.loads(self.db.scalar('''SELECT jsonb_agg(jsonb_build_object('name',p.proname,
          'owner',pg_catalog.pg_get_userbyid(p.proowner),'config',p.proconfig) ORDER BY p.proname)
          FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
          WHERE n.nspname='vn_portable_native_research';'''))
        self.assertEqual(len(functions),12)
        self.assertTrue(all(f['owner']==INSTALLER and f['config']==['search_path=pg_catalog, pg_temp'] for f in functions))

    def test_original_id_replay_before_stale_lease_fence_status_and_source_has_no_effects(self):
        self.create();row=self.bootstrap();self.commit(row[2]);observed=self.read(row)['receipt']
        self.db.sql("UPDATE vn_portable_native_research.runs SET lease_until=clock_timestamp()-interval '1 second',fence=2,status='stopped';")
        before=self.snapshot()
        reply=json.loads(self.db.scalar(self.sql(row[2],worker=str(UUID(int=77)),fence=99),role=ACTOR))
        self.assertEqual(reply,observed);self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.read(row)['receipt'],observed)
        forged=numbers.decode(row[2]);forged['evidence']['unused_extra']='different-original-bytes'
        self.reject_sql('BEGIN;'+self.sql(numbers.encode(forged))+'COMMIT;','portable_native_original_id_conflict')

    def test_lost_reply_reconciles_original_wire_without_new_id_or_mutation(self):
        self.create();row=self.bootstrap();self.commit(row[2]) # Discard pending function reply.
        before=self.snapshot();answer=self.read(row)
        self.assertTrue(answer['found']);self.assertEqual(answer['original_command_wire'].encode(),row[2])
        self.assertTrue(answer['receipt']['record_observed']);self.assertFalse(answer['receipt']['pending_until_commit'])
        self.assertRegex(answer['receipt']['guard_observed_at'],r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$')
        self.assertEqual(self.snapshot(),before)
        self.reject_sql('SELECT vn_portable_native_research.get_command('+','.join((
            literal(OWNER),literal(RUN),literal(numbers.decode(row[2])['command_id']),literal('0'*64)))+');',
            'portable_native_original_id_conflict')

    def test_function_reply_is_not_committed_readback_and_late_error_rolls_back_every_row(self):
        self.create();seed=self.bootstrap();self.commit(seed[2]);row=self.control(seed,'pause');identifier=numbers.decode(row[2])['command_id']
        getter='SELECT vn_portable_native_research.get_command('+','.join((literal(OWNER),literal(RUN),literal(identifier),literal(hashlib.sha256(row[2]).hexdigest())))+');'
        self.reject_sql('BEGIN;'+self.sql(row[2])+getter+'COMMIT;','portable_native_uncommitted_readback')
        self.reject_sql('BEGIN;'+self.sql(row[2])+self.sql(row[2])+'COMMIT;','portable_native_uncommitted_replay')
        self.reject_sql('BEGIN;'+self.sql(row[2])+self.lookup(row,[])+'COMMIT;','portable_native_uncommitted_readback')
        self.reject_sql('BEGIN;'+self.sql(row[2])+'SELECT 1/0;COMMIT;','division by zero')
        self.assertFalse(self.read(row)['found'])

    def test_only_one_new_command_can_be_admitted_per_transaction(self):
        self.create();row=self.bootstrap();self.commit(row[2]);pause=self.control(row,'pause');resume=self.control(pause,'resume',serial=11)
        self.reject_sql('BEGIN;'+self.sql(pause[2])+self.sql(resume[2])+'COMMIT;','portable_native_one_command_per_transaction')
        self.assertFalse(self.read(pause)['found'])

    def test_authentic_clock_rejects_stale_and_future_source_despite_caller_settings(self):
        self.create()
        for offset in (-20,20):
            with self.subTest(offset=offset):
                row=self.bootstrap(clock_offset=offset)
                self.reject_sql("BEGIN;SET dashboard.portable_clock='1900-01-01T00:00:00Z';"+self.sql(row[2])+'COMMIT;',
                    'portable_native_source_expired' if offset<0 else 'portable_native_source_future')

    def test_delayed_commit_source_expiry_rolls_back_pending_rows(self):
        self.create();row=self.bootstrap()
        self.reject_sql('BEGIN;'+self.sql(row[2])+'SELECT pg_sleep(5.1);COMMIT;','portable_native_commit_guard_expired')
        self.assertFalse(self.read(row)['found'])

    def test_delayed_commit_lease_expiry_and_heartbeat_refusals_use_server_time(self):
        self.create();row=self.bootstrap();self.commit(row[2]);pause=self.control(row,'pause')
        self.db.sql("UPDATE vn_portable_native_research.runs SET lease_until=clock_timestamp()+interval '2 seconds';")
        self.reject_sql('BEGIN;'+self.sql(pause[2])+'SELECT pg_sleep(2.1);COMMIT;','portable_native_commit_guard_expired')
        heartbeat='SELECT vn_portable_native_research.heartbeat('+','.join((literal(OWNER),literal(RUN),literal(WORKER),'1','60'))+');'
        self.reject_sql(heartbeat,'portable_native_lease_lost')
        self.assertFalse(self.read(pause)['found'])

    def test_unreviewed_commit_and_session_forms_roll_back(self):
        self.create();seed=self.bootstrap();self.commit(seed[2]);row=self.control(seed,'pause')
        forms=('implicit','immediate','COMMIT WORK;','END;')
        for form in forms:
            source=self.sql(row[2]) if form=='implicit' else 'BEGIN;'+self.sql(row[2])+(
                'SET CONSTRAINTS ALL IMMEDIATE;COMMIT;' if form=='immediate' else form)
            with self.subTest(form=form):self.reject_sql(source,'portable_native_unreviewed_commit_form')
        for prefix in ('BEGIN ISOLATION LEVEL REPEATABLE READ;','BEGIN;SET LOCAL synchronous_commit=off;',
            'CREATE TEMP TABLE native_unused_sentinel(value integer);BEGIN;'):
            with self.subTest(prefix=prefix):self.reject_sql(prefix+self.sql(row[2])+'COMMIT;','portable_native_unreviewed_session')

    def test_catalog_constraints_index_acl_role_parameter_and_owner_drift_refuse_without_data_change(self):
        self.create();row=self.bootstrap()
        actions=(
            'ALTER TABLE vn_portable_native_research.runs ADD CONSTRAINT benign_native_catalog_check CHECK(commands>=0);',
            'CREATE INDEX benign_native_catalog_index ON vn_portable_native_research.runs(status);',
            'GRANT SELECT ON vn_portable_native_research.commands TO '+ACTOR+';',
            'ALTER ROLE '+ACTOR+' SET timezone=\'UTC\';',
            'CREATE ROLE vn_portable_benign_parent NOLOGIN;GRANT vn_portable_benign_parent TO '+ACTOR+';',
            'GRANT SET ON PARAMETER session_replication_role TO '+ACTOR+';',
            'ALTER TABLE vn_portable_native_research.events OWNER TO '+ACTOR+';',
            'ALTER TRIGGER portable_native_commit_guard ON vn_portable_native_research.commands RENAME TO benign_native_guard_name;')
        for action in actions:
            with self.subTest(action=action):
                self.reject_sql('BEGIN;'+action+'SET SESSION AUTHORIZATION '+ACTOR+';'+self.sql(row[2])+'COMMIT;',
                    'portable_native_catalog_drift',role='postgres')

    def test_checkpoint_and_identity_readers_are_exact_scoped_and_head_bound(self):
        self.create();row=self.bootstrap();self.commit(row[2]);before=self.snapshot()
        ids=[member['id'] for member in row[0].state.to_dict()['engine']['members']]
        absent=str(UUID(int=96000099));answer=json.loads(self.db.scalar(self.lookup(row,ids+[absent]),role=ACTOR))
        self.assertEqual(set(answer['identities']),set(ids+[absent]));self.assertEqual(answer['identities'][absent],{'used':False})
        self.assertTrue(all(answer['identities'][identity]=={'used':True,'kind':'account','born_revision':'2'} for identity in ids))
        self.assertEqual(self.snapshot(),before)
        self.reject_sql(self.lookup(row,ids,revision=3),'portable_native_lookup_head_mismatch')
        self.reject_sql(self.lookup(row,ids,digest='0'*64),'portable_native_lookup_head_mismatch')
        self.reject_sql(self.lookup(row,[absent,absent]),'portable_native_duplicate_lookup_id')
        self.reject_sql(self.lookup(row,[str(UUID(int=97000000+i)) for i in range(129)]),'portable_native_identity_lookup_capacity')
        self.reject_sql(self.lookup(row,['NOT-A-UUID']),'checkpoint_uuid_required')
        self.reject_sql('SELECT vn_portable_native_research.read_checkpoint('+','.join((literal(OWNER),literal(RUN),'2',literal('0'*64)))+');',
            'portable_native_checkpoint_unavailable')
        self.reject_sql('DELETE FROM vn_portable_dependency_research.components WHERE sha256=(SELECT sha256 FROM vn_portable_native_research.dependency_pins LIMIT 1);',
            'foreign key constraint',role='postgres')

    def test_history_checkpoint_and_expired_readback_do_not_restore_a_lease(self):
        self.create();row=self.bootstrap();self.commit(row[2]);pause=self.control(row,'pause');self.commit(pause[2])
        historical=self.checkpoint(row);current=self.checkpoint(pause)
        self.assertEqual(historical['receipt']['revision'],'2');self.assertEqual(historical['current_revision'],'3')
        self.assertEqual(current['receipt']['revision'],'3');self.assertEqual(current['current_status'],'paused')
        self.db.sql("UPDATE vn_portable_native_research.runs SET lease_until=clock_timestamp()-interval '1 second';")
        before=self.snapshot();self.assertTrue(self.read(row)['found']);self.checkpoint(row)
        self.assertEqual(self.snapshot(),before)
        self.reject_sql(self.lookup(row,[]),'portable_native_lookup_head_mismatch')

    def test_pause_resume_stop_and_reserved_resource_slots_are_atomic(self):
        self.create();row=self.bootstrap();self.commit(row[2]);pause=self.control(row,'pause');self.commit(pause[2])
        resume=self.control(pause,'resume',serial=11)
        self.db.sql('UPDATE vn_portable_native_research.runs SET commands=127;')
        self.reject_sql('BEGIN;'+self.sql(resume[2])+'COMMIT;','portable_native_stop_slot_reserved')
        stop=self.control(pause,'stop',serial=12);self.commit(stop[2])
        self.assertEqual(self.db.scalar('SELECT commands FROM vn_portable_native_research.runs;'),'128')
        self.assertEqual(self.checkpoint(stop)['current_status'],'stopped')
        before=self.snapshot();self.assertTrue(self.read(stop)['found']);self.assertEqual(self.snapshot(),before)

    def test_byte_reserve_refusal_rolls_back_semantic_advance_but_data_free_stop_remains(self):
        self.create();row=self.bootstrap();self.commit(row[2]);pause=self.control(row,'pause')
        self.db.sql('UPDATE vn_portable_native_research.runs SET used_bytes=8388608;')
        self.reject_sql('BEGIN;'+self.sql(pause[2])+'COMMIT;','portable_native_stop_bytes_reserved')
        stop=self.control(row,'stop',serial=12);self.commit(stop[2])
        self.assertEqual(self.checkpoint(stop)['current_status'],'stopped')
        self.assertLessEqual(int(self.db.scalar('SELECT used_bytes FROM vn_portable_native_research.runs;')),9707520)

    def test_heartbeat_worker_fence_bounds_and_explicit_ascii_commit_forms(self):
        self.create();row=self.bootstrap();self.commit(row[2]);pause=self.control(row,'pause')
        for worker,fence,seconds in ((str(UUID(int=71)),1,60),(WORKER,2,60),(WORKER,1,0),(WORKER,1,61),(WORKER,1,None)):
            args=(literal(OWNER),literal(RUN),literal(worker),str(fence),'NULL' if seconds is None else str(seconds))
            with self.subTest(worker=worker,fence=fence,seconds=seconds):
                self.reject_sql('SELECT vn_portable_native_research.heartbeat('+','.join(args)+');','portable_native_lease_lost')
        lease_before=self.db.scalar('SELECT lease_until::text FROM vn_portable_native_research.runs;')
        heartbeat=json.loads(self.db.scalar('SELECT vn_portable_native_research.heartbeat('+','.join((
            literal(OWNER),literal(RUN),literal(WORKER),'1','60'))+');',role=ACTOR))
        self.assertEqual(heartbeat['revision'],'2');self.assertEqual(heartbeat['fence'],'1')
        self.assertGreater(self.db.scalar('SELECT lease_until::text FROM vn_portable_native_research.runs;'),lease_before)
        self.db.sql('BEGIN;'+self.sql(pause[2])+'\t cOmMiT \n;',role=ACTOR,timeout=30)
        self.assertTrue(self.read(pause)['receipt']['record_observed'])
        resume=self.control(pause,'resume',serial=11)
        self.db.sql('BEGIN;'+self.sql(resume[2])+'\r\n COMMIT \t;',role=ACTOR,timeout=30)
        self.assertEqual(self.checkpoint(resume)['current_status'],'running')

    def test_catalog_drift_after_function_reply_is_rechecked_during_commit_processing(self):
        self.create();row=self.bootstrap();self.commit(row[2]);pause=self.control(row,'pause')
        source='BEGIN;SET SESSION AUTHORIZATION '+ACTOR+';'+self.sql(pause[2])+'''
          SET SESSION AUTHORIZATION DEFAULT;
          ALTER TABLE vn_portable_native_research.events ADD CONSTRAINT benign_guard_catalog_check CHECK(ordinal>0);
        '''+'SET SESSION AUTHORIZATION '+ACTOR+';COMMIT;'
        self.reject_sql(source,'portable_native_catalog_drift',role='postgres')
        self.assertFalse(self.read(pause)['found'])

    def test_run_actor_and_package_locks_survive_until_commit(self):
        self.create();row=self.bootstrap();self.commit(row[2]);pause=self.control(row,'pause')
        session=self.db.begin_sql('BEGIN;'+self.sql(pause[2])+'SELECT pg_sleep(2.5);COMMIT;',role=ACTOR,timeout=20)
        self.db.wait_until("SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_stat_activity WHERE usename='"+ACTOR+"' AND wait_event='PgSleep');")
        probes=('SELECT * FROM vn_portable_native_research.runs FOR UPDATE;',
            'SELECT * FROM vn_portable_native_research.actor_bindings WHERE login=\''+ACTOR+'\' FOR UPDATE;',
            'SELECT * FROM vn_portable_native_research.package_manifest FOR UPDATE;')
        for probe in probes:
            response=self.db.sql("BEGIN;SET LOCAL lock_timeout='250ms';"+probe+'ROLLBACK;',check=False)
            self.assertNotEqual(response.returncode,0);self.assertIn('lock timeout',response.stderr)
        session.wait(25);self.assertTrue(self.read(pause)['receipt']['record_observed'])
        self.assertEqual(self.db.scalar('SELECT fence FROM vn_portable_native_research.runs;'),'1')

    def test_source_estimate_cannot_compose_two_worker_tolerances_past_native_clock(self):
        self.create();seed=self.bootstrap();self.commit(seed[2]);ledger=seed[3];state=ledger.accept(seed[0])
        now=int(self.db.scalar('SELECT floor(extract(epoch FROM clock_timestamp()));'));mono=MONO+1
        # The original worker-relative model validly allows receipt=worker wall
        # and estimated source=worker wall+2. With worker wall=DB-now+2, this
        # composes to DB-now+4; native admission must reject the direct anchor.
        frame=ga.source.make_frame(raw_capture(price='100',source_second=now+4,wall=now+2,mono=mono,age_floor=0),
            prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=now+2,monotonic_now=mono)
        candidate=ga.prepare_protective(state,frame,source_inputs(now+2,mono=mono,serial=1300),ledger=ledger)
        capture=cp.capture_owned_candidate(candidate);wire=cp.prepare_transport(candidate,capture,
            command_id=str(UUID(int=96000130)),previous=seed[1])
        self.reject_sql('BEGIN;'+self.sql(wire)+'COMMIT;','portable_native_source_future')

    def test_latest_bootstrap_receipt_is_checked_even_when_an_earlier_document_is_fresh(self):
        self.create();before=self.snapshot()
        now=int(self.db.scalar('SELECT floor(extract(epoch FROM clock_timestamp()));'))
        end=(now-5)//900*900;mono=MONO
        records=list(raw_minutes(end=end-900,count=900,close='80',wall=now,mono=mono))
        records+=list(raw_minutes(end=end,count=15,close='80',wall=now,mono=mono))
        history=ga.source.build_history(records,prior_bars=[],seed=True,wall_us=now*1_000_000,monotonic_us=int(mono*1_000_000))
        candidate=ga.bootstrap(ga.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=EPOCH),history,
            source_inputs(now,mono=mono,serial=1310),ledger=ga.SimulationLedger(OWNER,RUN))
        capture=cp.capture_owned_candidate(candidate);wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=96000131)))
        # A +4s producer-valid receipt can age into the native +2s allowance
        # during preparation/audit. This is explicitly an adversarial original
        # supplied-history request, not a producer-valid source continuation.
        # Keep the sealed baseline unchanged; construct/encode the attack once.
        # Its far-future claim exceeds the unchanged 30s SQL test timeout.
        body=numbers.decode(wire);documents=body['evidence']['inputs']['provider']['history']['documents']
        self.assertEqual(len(documents),2)
        latest=next(doc for doc in documents if doc['request']['parameters']['time_to']==end)
        self.assertEqual(latest['received_wall_us'],now*1_000_000)
        latest['received_wall_us']=(now+60)*1_000_000
        original_adversarial_wire=numbers.encode(body)
        result=self.db.sql('BEGIN;'+self.sql(original_adversarial_wire)+'COMMIT;',role=ACTOR,check=False,timeout=30)
        self.assertNotEqual(result.returncode,0,result.stdout)
        self.assertIn('portable_native_source_future',result.stderr)
        self.assertEqual(self.snapshot(),before)

    def test_direct_two_second_native_source_estimate_boundary_is_inclusive(self):
        self.create();seed=self.bootstrap();self.commit(seed[2]);ledger=seed[3];state=ledger.accept(seed[0])
        now=int(self.db.scalar('SELECT floor(extract(epoch FROM clock_timestamp()));'));mono=MONO+1
        frame=ga.source.make_frame(raw_capture(price='100',source_second=now+2,wall=now,mono=mono,age_floor=0),
            prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=now,monotonic_now=mono)
        candidate=ga.prepare_protective(state,frame,source_inputs(now,mono=mono,serial=1320),ledger=ledger)
        capture=cp.capture_owned_candidate(candidate);wire=cp.prepare_transport(candidate,capture,
            command_id=str(UUID(int=96000132)),previous=seed[1])
        row=(candidate,capture,wire,ledger);self.commit(wire)
        self.assertTrue(self.read(row)['receipt']['record_observed'])

    def test_any_supplied_history_receipt_participates_in_native_clock_refusal(self):
        self.create();seed=self.bootstrap();self.commit(seed[2]);row=self.control(seed,'pause')
        for offset,expected in ((-20,'portable_native_source_expired'),(20,'portable_native_source_future')):
            with self.subTest(offset=offset):
                now=int(self.db.scalar('SELECT floor(extract(epoch FROM clock_timestamp()));'))
                body=numbers.decode(row[2])
                # This is deliberately invalid control source grammar: even
                # unused supplied document receipt tags are rejected by the
                # native clock guard before semantic advancement. Complete
                # valid decision/history composition is a real-bar probe gate.
                body['evidence']['inputs']['provider']['history']={'documents':[{'received_wall_us':(now+offset)*1_000_000}],
                    'minutes':[],'unscaled':True}
                self.reject_sql('BEGIN;'+self.sql(numbers.encode(body))+'COMMIT;',expected)

    def test_native_projection_text_decodes_to_the_exact_original_checkpoint_header(self):
        self.create();row=self.bootstrap();self.commit(row[2])
        raw=self.db.scalar('SELECT resolved_wire FROM vn_portable_native_research.active_projection;')
        projection=numbers.decode(raw.encode(),maximum=262144)
        self.assertEqual(projection,row[1].resolve())
        self.assertEqual(projection['format'],'ga-portable-provider-checkpoint-research-v2')
        self.assertEqual(projection['source_model_version'],'ga-portable-provider-model-research-v2')
        self.assertNotIn('version',projection)
