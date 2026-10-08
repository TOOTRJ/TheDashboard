"""Complete-package admission, overlap, late failure and additive rollback."""
from __future__ import annotations
import json
import os
import time
import unittest
from uuid import uuid4
from tests.postgres import harness,forward_fixture as fixture,legacy_fixture,legacy_evidence_fixture
from tests.postgres.test_session_auth import NativeSessionAuthTests as SessionTools
from tests.postgres.test_command_adapter import literal
from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
from vonneumann.core.provider_lifecycle import ProviderLifecycleConfig
from tests.postgres.test_decimal_lineage_contract import document
from tests.postgres.test_provider_contract import seed_history,quote_frame,decision_inputs
from vonneumann.core import provider_lifecycle

def load_tests(loader,tests,pattern):
 suite=unittest.TestSuite()
 for cls in (ForwardCutoverTests,FullNativeSessionTests):suite.addTests(loader.loadTestsFromTestCase(cls))
 return suite

@unittest.skipUnless(os.environ.get(harness.OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class FullNativeSessionTests(SessionTools):
 @classmethod
 def setUpClass(cls):
  cls.db=fixture.start(cls);fixture.install(cls.db);fixture.transition(cls.db,'open')
 def admin(self,sql,**options):
  result=super().admin(sql,**options)
  if ('CREATE TRIGGER zz_native_delay ' in sql or 'CREATE TRIGGER native_delay ' in sql or
      'DROP TRIGGER zz_native_delay ' in sql or 'DROP TRIGGER native_delay ' in sql):
   # These two inherited deadline experiments intentionally introduce trusted
   # fixture-only sleep triggers. Explicitly review that synthetic fault shape;
   # otherwise the new catalog guard correctly refuses it before the sleep.
   super().admin('UPDATE vn_release.state SET install_catalog=vn_release.catalog() WHERE singleton;')
  return result

@unittest.skipUnless(os.environ.get(harness.OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class ForwardCutoverTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.db=fixture.start(cls)
 def setUp(self):
  self.ids=fixture.reset(self.db)
  self.owner=self.ids['owner'];self.other=self.ids['other']
  self.run,self.worker,self.command=(str(uuid4()) for _ in range(3))
  self.config=ProviderLifecycleConfig(ExactLifecycleConfig('genetic_algorithm',self.owner,self.run,asset='SOL/USD'),str(uuid4()))
 def admin(self,sql,**options):return self.db.sql(sql,role=fixture.ADMIN,**options)
 def create_sql(self):return SessionTools.create_sql(self)
 def get_sql(self):return SessionTools.get_sql(self)
 def heartbeat_sql(self):return SessionTools.heartbeat_sql(self)
 def call(self,sql,**options):return self.db.native(self.economic,'economic',sql,**options)
 def install(self,open=True):
  fixture.install(self.db)
  self.pair=fixture.native_issuer_fixture.Pair.new(self.owner,self.run)
  self.db.issue_pair(self.pair);self.economic,self.relay=self.pair.names
  if open:fixture.transition(self.db,'open')
 def retained(self):
  return self.admin("SELECT jsonb_build_array("+','.join(
   "(SELECT md5(coalesce(string_agg(to_jsonb(t)::text,',' ORDER BY to_jsonb(t)::text),'')) FROM "+t+" t)"
   for t in ['public.'+t for t in legacy_fixture.TABLES]+[
    'vn_durability.runs','vn_durability.commands','vn_durability.accounts','vn_durability.positions',
    'vn_durability.outbox_events','vn_projection.runs','vn_projection.relay_events',
    'vn_legacy_evidence.reviews','vn_legacy_evidence.archives','vn_access.bindings'])+');').stdout.strip()
 def legacy_rows(self):return [self.admin('SELECT md5(coalesce(string_agg(to_jsonb(t)::text,\'\' ORDER BY id),\'\')) FROM public.'+t+' t;').stdout for t in legacy_fixture.TABLES]
 def barrier(self,sql):
  deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   if self.admin(sql).stdout.strip()=='t':return
   time.sleep(.03)
  self.fail('Owned concurrency barrier missing')
 def absent(self):
  self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'vn_%';"),'0')
  self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_roles WHERE rolname IN ('vn_contract_owner','vn_economic','vn_relay','vn_legacy_attestor');"),'0')
 def test_fresh_complete_install_actual_limited_postgres_preserves_rows_and_auth(self):
  before=self.legacy_rows();self.install(open=False)
  self.assertEqual(before,self.legacy_rows())
  self.assertEqual(self.db.scalar("SELECT rolsuper FROM pg_roles WHERE rolname='postgres';"),'f')
  self.assertEqual(self.db.scalar("SELECT has_schema_privilege('vn_contract_owner','auth','USAGE');"),'f')
  self.assertEqual(self.db.scalar("SELECT has_function_privilege('vn_contract_owner','auth.uid()','EXECUTE');"),'f')
  self.assertEqual(self.admin('SELECT state FROM vn_release.state;').stdout.strip(),'closed')
  self.assertEqual(self.admin("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname LIKE 'vn_%';").stdout.strip(),'97')
  self.db.sql((fixture.HERE/'verify.sql').read_text())
 def test_closed_install_denies_even_valid_native_writer_before_mutation(self):
  self.install(open=False);before=self.retained()
  result=self.call(self.create_sql(),check=False)
  self.assertIn('release_admission_closed',result.stderr);self.assertEqual(before,self.retained())
 def test_no_review_and_wrong_target_fail_before_private_objects(self):
  result=fixture.install(self.db,reviewed='',check=False)
  self.assertIn('independent_complete_forward_review_required',result.stderr);self.absent()
  reviewed=fixture.review(self.db).replace('fxpxsciltakyypunglzr','wrong-project')
  result=fixture.install(self.db,reviewed=reviewed,check=False)
  self.assertIn('forward_review_changed_or_target_mismatch',result.stderr);self.absent()
 def test_migration_added_after_independent_review_requires_new_review(self):
  reviewed=fixture.review(self.db)
  self.db.sql("INSERT INTO supabase_migrations.schema_migrations VALUES('20990101000000','unexpected',ARRAY['SELECT 2;']);")
  self.addCleanup(self.db.sql,"DELETE FROM supabase_migrations.schema_migrations WHERE version='20990101000000';")
  result=fixture.install(self.db,reviewed=reviewed,check=False)
  self.assertIn('forward_review_changed_or_target_mismatch',result.stderr);self.absent()
 def test_same_migration_version_with_changed_statements_is_refused(self):
  reviewed=fixture.review(self.db)
  self.db.sql("UPDATE supabase_migrations.schema_migrations SET statements=ARRAY['SELECT 9;'] WHERE version='20260402100000';")
  self.addCleanup(self.db.sql,"UPDATE supabase_migrations.schema_migrations SET statements=ARRAY['SELECT 1;'] WHERE version='20260402100000';")
  result=fixture.install(self.db,reviewed=reviewed,check=False)
  self.assertIn('forward_review_changed_or_target_mismatch',result.stderr);self.absent()
 def test_changed_legacy_catalog_is_refused_and_all_new_objects_rollback(self):
  reviewed=fixture.review(self.db)
  self.db.sql('ALTER TABLE public.vn_colonies ADD COLUMN unreviewed text;')
  result=fixture.install(self.db,reviewed=reviewed,check=False)
  self.assertIn('legacy_catalog_changed_review_again',result.stderr);self.absent()
 def test_late_install_failure_restores_original_grants_and_rows(self):
  before=self.legacy_rows();acl=self.db.scalar("SELECT relacl::text FROM pg_class WHERE oid='public.vn_probes'::regclass;")
  result=fixture.install(self.db,suffix="DO $$ BEGIN RAISE EXCEPTION 'late_complete_failure'; END $$;",check=False)
  self.assertIn('late_complete_failure',result.stderr);self.absent()
  self.assertEqual(before,self.legacy_rows());self.assertEqual(acl,self.db.scalar("SELECT relacl::text FROM pg_class WHERE oid='public.vn_probes'::regclass;"))
 def test_already_open_old_writer_blocks_whole_install_with_bounded_timeout(self):
  reviewed=fixture.review(self.db);marker='forward-old-'+uuid4().hex
  session=self.db.begin_sql("BEGIN; SET application_name='"+marker+"'; UPDATE public.vn_colonies SET status=status; SELECT pg_sleep(2); COMMIT;",role='service_role',timeout=5)
  self.barrier("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='"+marker+"' AND wait_event='PgSleep');")
  started=time.monotonic();result=fixture.install(self.db,reviewed=reviewed,check=False)
  self.assertIn('lock timeout',result.stderr);self.assertLess(time.monotonic()-started,3);self.absent();session.wait()
 def test_already_connected_old_writer_loses_permission_after_committed_cutover(self):
  marker='forward-delayed-'+uuid4().hex
  session=self.db.begin_sql("SET application_name='"+marker+"'; SELECT pg_sleep(2); UPDATE public.vn_colonies SET status=status;",role='service_role',timeout=5)
  self.barrier("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='"+marker+"' AND wait_event='PgSleep');")
  self.install();result=session.wait(check=False)
  self.assertIn('permission denied',result.stderr)
 def test_retirement_preserves_acknowledged_create_and_original_readback(self):
  self.install();self.call(self.create_sql());before=self.retained()
  receipt=fixture.transition(self.db,'retired',epoch=1)
  self.assertTrue(receipt['economic_rows_preserved']);self.assertFalse(receipt['legacy_writes_restored'])
  self.assertEqual(before,self.retained())
  self.assertEqual(json.loads(self.call(self.get_sql()).stdout)['response']['revision'],1)
  for sql in (self.create_sql(),self.heartbeat_sql()):
   result=self.call(sql,check=False);self.assertIn('release_admission_closed',result.stderr)
  self.assertEqual(before,self.retained())
 def test_retired_release_is_terminal_original_transition_replay_survives(self):
  self.install();request=str(uuid4())
  receipt=fixture.transition(self.db,'retired',1,request)
  self.assertEqual(receipt,fixture.transition(self.db,'retired',1,request))
  self.assertIn('release_command_conflict',fixture.transition(self.db,'retired',1,request,evidence='8'*64,check=False).stderr)
  self.assertIn('release_transition_conflict',fixture.transition(self.db,'open',2,check=False).stderr)
 def test_writer_admitted_before_rollback_holds_gate_until_commit(self):
  self.install();marker='forward-admitted-'+uuid4().hex
  session=self.db.begin_native(self.economic,'economic',"BEGIN; SET application_name='"+marker+"'; "+self.create_sql()+" SELECT pg_sleep(2); COMMIT;",timeout=6)
  self.barrier("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='"+marker+"' AND wait_event='PgSleep');")
  result=fixture.transition(self.db,'retired',1,check=False)
  self.assertIn('lock timeout',result.stderr)
  self.assertEqual(self.admin('SELECT state FROM vn_release.state;').stdout.strip(),'open')
  session.wait();fixture.transition(self.db,'retired',1)
  self.assertEqual(json.loads(self.call(self.get_sql()).stdout)['response']['revision'],1)
 def test_rollback_uncommitted_failure_keeps_admission_and_receipts_unchanged(self):
  self.install();result=self.db.sql(fixture.BOUND+"SELECT vn_release.transition('"+str(uuid4())+"',1,'retired','"+'9'*64+"'); SELECT 1/0; COMMIT;",check=False)
  self.assertIn('division by zero',result.stderr)
  self.assertEqual(self.admin('SELECT state FROM vn_release.state;').stdout.strip(),'open')
  self.assertEqual(self.admin('SELECT count(*) FROM vn_release.operations;').stdout.strip(),'1')
 def test_capabilities_and_all_api_roles_cannot_change_or_read_private_release(self):
  self.install()
  for role in ('anon','authenticated','service_role','authenticator'):
   result=self.db.sql('SELECT * FROM vn_release.state;',role=role,check=False)
   self.assertIn('permission denied',result.stderr)
  legacy_evidence_fixture.reviewer(self.db)
  result=self.db.sql('SET ROLE vn_legacy_attestor; SELECT * FROM vn_release.state;',role=legacy_evidence_fixture.ATTESTOR,check=False)
  self.assertIn('permission denied',result.stderr)
  for name,cap in ((self.economic,'economic'),(self.relay,'relay')):
   result=self.db.native(name,cap,"SELECT vn_release.transition('"+str(uuid4())+"',1,'retired','"+'a'*64+"');",check=False)
   self.assertIn('permission denied',result.stderr)
 def test_safe_expiry_interruption_after_retirement_keeps_ledger(self):
  self.install();self.call(self.create_sql());fixture.transition(self.db,'retired',1)
  self.admin("UPDATE vn_durability.runs SET lease_until=clock_timestamp()-interval '1 second' WHERE id='"+self.run+"';")
  result=json.loads(self.call("SELECT vn_durability.interrupt_expired('"+self.owner+"','"+self.run+"',1,'"+str(uuid4())+"');").stdout)
  self.assertEqual(result['status'],'failed');self.assertTrue(result['requires_reconciliation'])
  self.assertEqual(self.admin("SELECT reserve::text FROM vn_durability.runs WHERE id='"+self.run+"';").stdout.strip(),self.config.initial_cash)
 def test_legacy_evidence_archive_remains_available_after_retirement(self):
  self.install();legacy_evidence_fixture.reviewer(self.db)
  receipt,_,_=legacy_evidence_fixture.attest(self.db,self.ids)
  before=self.legacy_rows();fixture.transition(self.db,'retired',1)
  archived=legacy_evidence_fixture.call(self.db,'vn_legacy_evidence.archive('+','.join(literal(v) for v in
   (str(uuid4()),self.ids['run'],receipt['request_id']))+')',owner=self.owner)
  self.assertFalse(archived['live_holdings_verified']);self.assertEqual(before,self.legacy_rows())
 def test_repeated_install_is_refused_without_altering_committed_commands(self):
  self.install();self.call(self.create_sql());before=self.retained()
  result=fixture.install(self.db,check=False)
  self.assertIn('forward_review_changed_or_target_mismatch',result.stderr);self.assertEqual(before,self.retained())
 def test_repeatable_read_transition_and_native_write_refused(self):
  self.install()
  result=self.call('BEGIN ISOLATION LEVEL REPEATABLE READ; '+self.create_sql()+' COMMIT;',check=False)
  self.assertIn('release_read_committed_required',result.stderr)
  result=self.db.sql(fixture.BOUND.replace('BEGIN;','BEGIN ISOLATION LEVEL REPEATABLE READ;')+
   "SELECT vn_release.transition('"+str(uuid4())+"',1,'retired','"+'a'*64+"'); COMMIT;",check=False)
  self.assertIn('bounded_release_transaction_required',result.stderr)
 def commit_sql(self,candidate,command=None):
  before=candidate.transition['before'];revision=1 if before is None else before['revision']
  return 'SELECT vn_durability.commit_command('+','.join((literal(self.owner),literal(self.run),
   literal(self.worker),'1',str(revision),literal(command or str(uuid4())),document({
    'version':5,'operations':candidate.operations,'transition':candidate.transition})))+');'
 def test_all_four_actual_native_solvers_commit_and_drain_relay_after_rollback(self):
  self.install()
  for strategy in ('genetic_algorithm','differential_evolution','particle_swarm','cma_es'):
   with self.subTest(strategy=strategy):
    self.run,self.worker,self.command=(str(uuid4()) for _ in range(3))
    self.config=ProviderLifecycleConfig(ExactLifecycleConfig(strategy,self.owner,self.run,asset='SOL/USD'),str(uuid4()))
    self.pair=fixture.native_issuer_fixture.Pair.new(self.owner,self.run);self.db.issue_pair(self.pair)
    self.economic,self.relay=self.pair.names;self.call(self.create_sql())
    now,mono=time.time(),time.monotonic()
    boot=provider_lifecycle.bootstrap(self.config,seed_history(now,mono),decision_inputs(now,mono))
    self.call(self.commit_sql(boot))
    now,mono=time.time(),time.monotonic();frame=quote_frame(boot.state,now,mono)
    protect=provider_lifecycle.prepare_protective(boot.state,frame,decision_inputs(now,mono))
    self.call(self.commit_sql(protect))
    now,mono=time.time(),time.monotonic()
    decide=provider_lifecycle.prepare_decision(protect.state,frame,None,decision_inputs(now,mono,second=frame['decision_second']))
    command=str(uuid4());self.call(self.commit_sql(decide,command))
    actual=json.loads(self.admin('SELECT engine_state FROM vn_durability.runs WHERE id='+literal(self.run)+';').stdout)
    self.assertEqual(actual,decide.state.to_dict());self.assertEqual(actual['engine']['cohort']['phase'],'evaluating')
  before=self.retained();fixture.transition(self.db,'retired',1);self.assertEqual(before,self.retained())
  page=json.loads(self.db.native(self.relay,'relay','SELECT vn_durability.read_outbox('+','.join((
   literal(self.owner),literal(self.run),'4','50','65536'))+');').stdout)
  self.assertEqual(len(page['events']),9)
  row=page['events'][0]
  args=','.join((literal(self.owner),literal(self.run),literal(row['command_id']),str(row['event_index'])))
  accepted=json.loads(self.db.native(self.relay,'relay','SELECT vn_read.accept_event('+args+');').stdout)
  self.assertTrue(accepted['accepted'])
  self.db.native(self.relay,'relay','SELECT vn_durability.acknowledge_event('+args+');')
  self.assertEqual(actual,json.loads(self.admin('SELECT engine_state FROM vn_durability.runs WHERE id='+literal(self.run)+';').stdout))
  replay=json.loads(self.call('SELECT vn_durability.get_command('+','.join(map(literal,(self.owner,self.run,command)))+');').stdout)
  self.assertEqual(replay['request']['payload']['transition']['after'],actual)
  self.assertIn('release_admission_closed',self.call(self.commit_sql(decide,command),check=False).stderr)
 def test_postcommit_verify_detects_table_column_function_and_legacy_drift(self):
  self.install()
  variants=[('GRANT SELECT ON vn_durability.runs TO service_role;',
     'REVOKE SELECT ON vn_durability.runs FROM service_role;'),
   ('ALTER TABLE vn_release.operations ADD COLUMN unexpected integer;',
     'ALTER TABLE vn_release.operations DROP COLUMN unexpected;'),
   ('GRANT EXECUTE ON FUNCTION vn_release.catalog() TO PUBLIC;',
     'REVOKE EXECUTE ON FUNCTION vn_release.catalog() FROM PUBLIC;'),
   ('ALTER TABLE public.vn_colonies DISABLE TRIGGER vn_legacy_evidence_changed;',
     'ALTER TABLE public.vn_colonies ENABLE ALWAYS TRIGGER vn_legacy_evidence_changed;')]
  for change,repair in variants:
   with self.subTest(change=change):
    self.admin(change)
    result=self.db.sql((fixture.HERE/'verify.sql').read_text(),check=False)
    self.assertNotEqual(result.returncode,0)
    self.assertIn('complete_forward_',result.stderr)
    self.admin(repair)
  self.db.sql((fixture.HERE/'verify.sql').read_text())
 def test_unreviewed_schema_grant_drift_blocks_economics_without_erasing_readback(self):
  self.install();self.call(self.create_sql())
  self.admin('GRANT USAGE ON SCHEMA vn_release TO authenticated;')
  self.assertIn('release_catalog_drift',self.call(self.heartbeat_sql(),check=False).stderr)
  self.assertEqual(json.loads(self.call(self.get_sql()).stdout)['response']['revision'],1)
  self.admin('REVOKE USAGE ON SCHEMA vn_release FROM authenticated;')
