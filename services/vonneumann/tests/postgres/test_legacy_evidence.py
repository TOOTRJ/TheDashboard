"""Real limited-installer evidence, owner isolation, rollback and race cases."""
from __future__ import annotations
from copy import deepcopy
import json
import os
import unittest
from uuid import uuid4

from tests.postgres import harness, legacy_fixture as legacy, canonical_fixture
from tests.postgres import legacy_evidence_fixture as fixture


@unittest.skipUnless(os.environ.get(harness.OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class LegacyEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=fixture.start(cls)
        cls.db.sql('CREATE TABLE public.legacy_evidence_test_gate(released boolean); INSERT INTO public.legacy_evidence_test_gate VALUES(false); '
                   'GRANT SELECT,UPDATE ON public.legacy_evidence_test_gate TO postgres;',role=fixture.ADMIN)

    def setUp(self):
        self.db.sql('''DROP SCHEMA IF EXISTS vn_legacy_evidence,vn_legacy CASCADE;
DROP FUNCTION IF EXISTS vn_identity.lock_legacy_evidence(),vn_identity.legacy_rows(uuid,uuid);
DROP ROLE IF EXISTS vn_test_legacy_reviewer,vn_legacy_attestor;
DROP TABLE '''+', '.join('public.'+t for t in legacy.TABLES)+''' CASCADE;
TRUNCATE auth.users CASCADE; UPDATE public.legacy_evidence_test_gate SET released=false;
''',role=fixture.ADMIN)
        self.db.sql(legacy.captured_legacy_schema())
        self.ids=legacy.seed_legacy_rows(canonical_fixture.CapabilityDatabase(self.db))
        fixture.install(self.db)
        fixture.reviewer(self.db)

    def call(self,expression,**kwargs):
        kwargs.setdefault('owner',self.ids['owner'])
        return fixture.call(self.db,expression,**kwargs)

    def status(self,run=None,**kwargs):
        return self.call('vn_legacy_evidence.status('+legacy.literal(run or self.ids['run'])+')',**kwargs)

    def archive(self,review,request=None,run=None,**kwargs):
        request=request or str(uuid4())
        return self.call('vn_legacy_evidence.archive('+','.join(legacy.literal(v) for v in
            (request,run or self.ids['run'],review))+')',**kwargs)

    def invalidate(self,review,request=None,reason='Operator evidence withdrawn',**kwargs):
        return fixture.call(self.db,'vn_legacy_evidence.invalidate('+','.join(legacy.literal(v) for v in
            (request or str(uuid4()),review,reason))+')',role=fixture.ATTESTOR,**kwargs)

    def retained_rows(self):
        return [json.loads(self.db.scalar("SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]') FROM public."+t+' t;',role=fixture.ADMIN))
                for t in legacy.TABLES]

    def test_actual_non_superuser_installer_and_preserved_auth_dependencies(self):
        self.assertEqual(self.db.scalar("SELECT rolsuper FROM pg_roles WHERE rolname='postgres';"),'f')
        self.assertEqual(self.db.scalar("SELECT has_schema_privilege('vn_contract_owner','auth','USAGE');"),'f')
        self.assertEqual(self.db.scalar("SELECT has_function_privilege('vn_contract_owner','auth.uid()','EXECUTE');"),'t')
        denied=self.db.sql('SET ROLE vn_contract_owner; SELECT auth.uid();',check=False)
        self.assertIn('42501',denied.stderr)
        self.assertEqual(self.db.scalar("SELECT has_table_privilege('vn_contract_owner','public.vn_probes','UPDATE,MAINTAIN');"),'f')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_trigger WHERE tgname='vn_legacy_evidence_changed' AND tgenabled='A';"),'5')
        # The composed bounded classifier works without granting managed Auth.
        classified=self.call('vn_legacy.classify_run('+legacy.literal(self.ids['run'])+')')
        self.assertEqual(classified['counts']['trades']['open_records'],1)
        self.assertFalse(classified['live_holdings_verified'])

    def test_stopped_and_empty_records_never_replace_review(self):
        status=self.status()
        self.assertFalse(status['review']['eligible'])
        self.assertFalse(status['archived'])
        result=self.archive(str(uuid4()),check=False)
        self.assertIn('legacy_archive_evidence_required',result.stderr)

    def test_valid_review_non_destructive_archive_and_owner_history(self):
        before=self.retained_rows()
        receipt,snapshot,doc=fixture.attest(self.db,self.ids)
        self.assertTrue(self.status()['review']['eligible'])
        self.assertIn('retained_or_uncertain_exposure',self.status()['review']['warnings'])
        archived=self.archive(receipt['request_id'])
        self.assertEqual(archived['revision'],snapshot['revision'])
        self.assertTrue(self.status()['archived'])
        self.assertFalse(archived['live_holdings_verified'])
        self.assertFalse(archived['restoration_available'])
        self.assertEqual(before,self.retained_rows())
        page=self.call('vn_legacy_evidence.history('+legacy.literal(self.ids['run'])+',0,1)')
        self.assertEqual(page['records'],[archived])
        self.assertEqual(page['next_sequence'],archived['sequence'])
        self.assertEqual(self.call('vn_legacy_evidence.history('+legacy.literal(self.ids['run'])+','+
            str(page['next_sequence'])+',1)')['records'],[])

    def test_snapshot_hashes_ignore_caller_timezone_and_float_print_settings(self):
        before=fixture.capture(self.db,self.ids)
        args=legacy.literal(self.ids['owner'])+','+legacy.literal(self.ids['run'])
        result=self.db.scalar(fixture.BOUND+"SET LOCAL timezone='Pacific/Honolulu'; SET LOCAL extra_float_digits=-3; "+
            'SET LOCAL ROLE vn_legacy_attestor; SELECT vn_legacy_evidence.capture('+args+'); COMMIT;',role=fixture.ATTESTOR)
        self.assertEqual(json.loads(result),before)

    def test_oversized_retained_row_is_refused_without_partial_review(self):
        self.db.sql("UPDATE public.vn_probes SET metrics=jsonb_build_object('oversized',repeat('x',131073)) WHERE id="+
            legacy.literal(self.ids['probe'])+';')
        result=fixture.call(self.db,'vn_legacy_evidence.capture('+legacy.literal(self.ids['owner'])+','+
            legacy.literal(self.ids['run'])+')',role=fixture.ATTESTOR,check=False)
        self.assertIn('legacy_snapshot_budget_exceeded',result.stderr)

    def test_stale_future_unordered_duplicate_writer_and_oversized_documents_fail(self):
        snap=fixture.capture(self.db,self.ids);valid=fixture.document(snap)
        variants=[]
        for field,value in [('expires_at','2000-01-01T00:00:00Z'),('expires_at','2100-01-01T00:00:00Z')]:
            doc=deepcopy(valid);doc[field]=value;variants.append(doc)
        doc=deepcopy(valid);doc['drain']['observed_at']='2100-01-01T00:00:00Z';variants.append(doc)
        doc=deepcopy(valid);doc['drain']['writers']*=2;variants.append(doc)
        doc=deepcopy(valid);doc['drain']['writers'][0]['identity']='x'*65537;variants.append(doc)
        doc=deepcopy(valid);doc['drain']['evidence_sha256']='not-a-digest';variants.append(doc)
        for doc in variants:
            result,_,_=fixture.attest(self.db,self.ids,snapshot=snap,doc=doc,check=False)
            self.assertIn('22023',result.stderr)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_legacy_evidence.reviews;',role=fixture.ADMIN),'0')

    def test_two_owner_and_non_owner_requests_are_denied_without_disclosure(self):
        receipt,_,_=fixture.attest(self.db,self.ids)
        archived=self.archive(receipt['request_id'])
        for run in (self.ids['run'],str(uuid4())):
            result=self.status(run,owner=self.ids['other'],check=False)
            self.assertIn('legacy_run_unavailable',result.stderr)
        result=self.archive(receipt['request_id'],request=archived['request_id'],owner=self.ids['other'],check=False)
        self.assertIn('legacy_archive_unavailable',result.stderr)
        result=self.status(owner='',check=False)
        self.assertIn('legacy_owner_required',result.stderr)
        for role in ('anon','service_role','authenticator'):
            result=self.status(role=role,check=False)
            self.assertIn('42501',result.stderr)

    def test_separate_attestor_not_claims_or_an_api_membership(self):
        snap=fixture.capture(self.db,self.ids)
        args=','.join([legacy.literal(str(uuid4())),legacy.literal(self.ids['owner']),legacy.literal(self.ids['run']),
                     fixture.literal_json(snap),fixture.literal_json(fixture.document(snap))])
        for role in ('authenticated','service_role','authenticator','anon'):
            result=self.call('vn_legacy_evidence.attest('+args+')',role=role,check=False)
            self.assertIn('42501',result.stderr)
        # Even deliberately delegated capability is refused for a shared API login.
        self.db.sql('GRANT vn_legacy_attestor TO authenticator WITH INHERIT FALSE,SET TRUE;',role=fixture.ADMIN)
        try:
            result=self.db.sql(fixture.BOUND+'SET LOCAL ROLE vn_legacy_attestor; SELECT vn_legacy_evidence.capture('+
                legacy.literal(self.ids['owner'])+','+legacy.literal(self.ids['run'])+'); COMMIT;',role='authenticator',check=False)
            self.assertIn('separate_legacy_attestor_required',result.stderr)
        finally:self.db.sql('REVOKE vn_legacy_attestor FROM authenticator;',role=fixture.ADMIN)

    def test_raw_tables_helpers_and_installer_bridges_are_denied(self):
        for role in ('authenticated','anon','service_role','authenticator',fixture.ATTESTOR):
            prefix='SET LOCAL ROLE vn_legacy_attestor;' if role==fixture.ATTESTOR else ''
            for expression in ['SELECT * FROM vn_legacy_evidence.reviews;',
                'UPDATE vn_legacy_evidence.gate SET revision=0;',
                'SELECT vn_legacy_evidence.catalog();','SELECT vn_legacy_evidence.snapshot(NULL,NULL);',
                'SELECT vn_identity.legacy_rows(NULL,NULL);','SELECT vn_identity.lock_legacy_evidence();']:
                result=self.db.sql(fixture.BOUND+prefix+expression+' COMMIT;',role=role,check=False)
                self.assertIn('42501',result.stderr,(role,expression))

    def test_original_review_id_replays_after_data_change_without_new_approval(self):
        receipt,snap,doc=fixture.attest(self.db,self.ids)
        self.db.sql('UPDATE public.vn_probes SET current_capital=42 WHERE id='+legacy.literal(self.ids['probe'])+';')
        again,_,_=fixture.attest(self.db,self.ids,request=receipt['request_id'],snapshot=snap,doc=doc)
        self.assertEqual(receipt,again)
        self.assertFalse(self.status()['review']['eligible'])
        self.assertIn('legacy_rows_changed',self.status()['review']['blockers'])
        changed=deepcopy(doc);changed['reconciliation']['evidence_sha256']='7'*64
        result,_,_=fixture.attest(self.db,self.ids,request=receipt['request_id'],snapshot=snap,doc=changed,check=False)
        self.assertIn('legacy_request_identity_conflict',result.stderr)

    def test_original_archive_id_replays_after_invalidation_without_hiding_status(self):
        receipt,_,_=fixture.attest(self.db,self.ids)
        archived=self.archive(receipt['request_id'])
        invalid=self.invalidate(receipt['request_id'])
        self.assertEqual(archived,self.archive(receipt['request_id'],request=archived['request_id']))
        status=self.status()
        self.assertTrue(status['archive_recorded'])
        self.assertFalse(status['archived'])
        self.assertTrue(status['archive_invalidated'])
        self.assertIn('review_invalidated',status['review']['blockers'])
        self.assertEqual(invalid,self.invalidate(receipt['request_id'],request=invalid['request_id']))
        bad=self.invalidate(receipt['request_id'],request=invalid['request_id'],reason='Different reason',check=False)
        self.assertIn('legacy_request_identity_conflict',bad.stderr)

    def test_snapshot_change_then_restore_still_invalidates_all_original_evidence(self):
        receipt,_,_=fixture.attest(self.db,self.ids)
        self.archive(receipt['request_id'])
        self.db.sql("UPDATE public.vn_probes SET current_capital=9 WHERE id="+legacy.literal(self.ids['probe'])+'; '+
                    "UPDATE public.vn_probes SET current_capital=0 WHERE id="+legacy.literal(self.ids['probe'])+';')
        self.assertFalse(self.status()['archived'])
        self.assertEqual(self.status()['revision'],2)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_legacy_evidence.changes;',role=fixture.ADMIN),'2')

    def test_insert_delete_zero_row_and_other_owner_changes_invalidate_conservatively(self):
        receipt,_,_=fixture.attest(self.db,self.ids)
        statements=["UPDATE public.vn_colonies SET status='stopped' WHERE false;",
                    'DELETE FROM public.vn_generation_stats WHERE false;',
                    'UPDATE public.vn_probes SET current_capital=0 WHERE user_id='+legacy.literal(self.ids['other'])+';',
                    'INSERT INTO public.vn_generation_stats(user_id,run_id,generation) VALUES('+legacy.literal(self.ids['other'])+','+
                        legacy.literal(self.ids['other_run'])+',1);']
        for statement in statements:
            self.db.sql(statement)
            self.assertFalse(self.status()['review']['eligible'])
        self.assertEqual(self.status()['revision'],4)

    def test_replica_mode_mutations_still_increment_evidence_revision(self):
        receipt,_,_=fixture.attest(self.db,self.ids)
        self.db.sql('SET session_replication_role=replica; UPDATE public.vn_probes SET current_capital=7; RESET session_replication_role;',role=fixture.ADMIN)
        self.assertFalse(self.status()['review']['eligible'])
        self.assertEqual(self.status()['revision'],1)

    def test_truncate_records_invalidation_and_preserves_review_journal(self):
        receipt,_,_=fixture.attest(self.db,self.ids)
        self.db.sql('TRUNCATE public.vn_fitness_snapshots;')
        self.assertFalse(self.status()['review']['eligible'])
        self.assertEqual(self.db.scalar("SELECT operation FROM vn_legacy_evidence.changes;",role=fixture.ADMIN),'TRUNCATE')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_legacy_evidence.reviews;',role=fixture.ADMIN),'1')

    def test_row_mutation_rollback_restores_revision_and_review_validity(self):
        receipt,_,_=fixture.attest(self.db,self.ids)
        before=self.retained_rows()
        self.db.sql('BEGIN; UPDATE public.vn_probes SET current_capital=77; ROLLBACK;')
        self.assertEqual(self.retained_rows(),before)
        self.assertTrue(self.status()['review']['eligible'])
        self.assertEqual(self.status()['revision'],0)

    def test_catalog_column_grant_and_policy_drift_fail_closed(self):
        receipt,_,_=fixture.attest(self.db,self.ids)
        self.db.sql('GRANT UPDATE(current_capital) ON public.vn_probes TO authenticated;')
        result=self.status(check=False)
        self.assertIn('legacy_catalog_evidence_changed',result.stderr)
        self.db.sql('REVOKE UPDATE(current_capital) ON public.vn_probes FROM authenticated;')
        # Exact known policy name is derived from the captured catalog, not guessed.
        name=self.db.scalar("SELECT policyname FROM pg_policies WHERE tablename='vn_probes' AND cmd='SELECT' ORDER BY policyname LIMIT 1;")
        self.db.sql('ALTER POLICY '+legacy.ident(name)+' ON public.vn_probes USING(true);')
        self.assertIn('legacy_catalog_evidence_changed',self.status(check=False).stderr)

    def test_trigger_disabled_or_function_changed_fails_closed(self):
        fixture.attest(self.db,self.ids)
        self.db.sql('ALTER TABLE public.vn_trades DISABLE TRIGGER vn_legacy_evidence_changed;')
        self.assertIn('legacy_catalog_evidence_changed',self.status(check=False).stderr)

    def test_private_helper_permission_or_body_drift_fails_closed(self):
        fixture.attest(self.db,self.ids)
        self.db.sql("GRANT EXECUTE ON FUNCTION vn_identity.legacy_rows(uuid,uuid) TO authenticated;")
        self.assertIn('legacy_catalog_evidence_changed',self.status(check=False).stderr)

    def test_attestor_capability_role_drift_fails_closed(self):
        fixture.attest(self.db,self.ids)
        self.db.sql('ALTER ROLE vn_legacy_attestor LOGIN;',role=fixture.ADMIN)
        self.assertIn('legacy_catalog_evidence_changed',self.status(check=False).stderr)

    def test_expired_review_and_revoked_attestor_do_not_hide_a_run(self):
        receipt,_,_=fixture.attest(self.db,self.ids)
        self.archive(receipt['request_id'])
        self.db.sql('ALTER ROLE '+fixture.ATTESTOR+' NOLOGIN;',role=fixture.ADMIN)
        self.assertFalse(self.status()['archived'])
        self.assertIn('attestor_identity_changed',self.status()['review']['blockers'])
        self.db.sql('ALTER ROLE '+fixture.ATTESTOR+' LOGIN;',role=fixture.ADMIN)
        self.db.sql("UPDATE vn_legacy_evidence.reviews SET expires_at=clock_timestamp()-interval '1 second';",role=fixture.ADMIN)
        self.assertIn('evidence_expired',self.status()['review']['blockers'])
        self.assertFalse(self.status()['archived'])

    def test_missing_duplicate_extra_or_foreign_open_record_coverage_is_rejected(self):
        snap=fixture.capture(self.db,self.ids); valid=fixture.document(snap)
        variants=[]
        missing=deepcopy(valid);missing['reconciliation']['exposures']=[];variants.append(missing)
        duplicate=deepcopy(valid);duplicate['reconciliation']['exposures']*=2;variants.append(duplicate)
        foreign=deepcopy(valid);foreign['reconciliation']['exposures'][0]['trade_id']=str(uuid4());variants.append(foreign)
        for doc in variants:
            result,_,_=fixture.attest(self.db,self.ids,snapshot=snap,doc=doc,check=False)
            self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_legacy_evidence.reviews;',role=fixture.ADMIN),'0')

    def test_external_retained_exposure_is_explicit_even_with_zero_open_rows(self):
        self.db.sql('UPDATE public.vn_trades SET closed_at=now();')
        snap=fixture.capture(self.db,self.ids);doc=fixture.document(snap)
        doc['reconciliation']['exposures']=[{'identity':'external-wallet-exposure','trade_id':None,
            'disposition':'retained','evidence_sha256':'a'*64,'note':'Separate synthetic retained exposure.'}]
        receipt,_,_=fixture.attest(self.db,self.ids,snapshot=snap,doc=doc)
        archived=self.archive(receipt['request_id'])
        self.assertIn('retained_or_uncertain_exposure',archived['warnings'])
        self.assertFalse(archived['live_holdings_verified'])

    def test_null_enum_fields_and_caller_boolean_are_not_evidence(self):
        snap=fixture.capture(self.db,self.ids);valid=fixture.document(snap)
        variants=[]
        for key in ('provenance','expires_at'):
            doc=deepcopy(valid);doc[key]=None;variants.append(doc)
        doc=deepcopy(valid);doc['drain']['writers'][0]['state']=None;variants.append(doc)
        doc=deepcopy(valid);doc['reconciliation']['scope']=None;variants.append(doc)
        doc=deepcopy(valid);doc['reconciliation']['exposures'][0]['disposition']=None;variants.append(doc)
        doc=deepcopy(valid);doc['writer_drained']=True;variants.append(doc)
        for doc in variants:
            result,_,_=fixture.attest(self.db,self.ids,snapshot=snap,doc=doc,check=False)
            self.assertIn('22023',result.stderr)

    def test_unbound_scope_remains_unavailable_and_orphan_links_remain_warned(self):
        result=fixture.call(self.db,'vn_legacy_evidence.capture('+legacy.literal(self.ids['owner'])+',NULL)',role=fixture.ATTESTOR,check=False)
        self.assertIn('bound_legacy_scope_required',result.stderr)
        orphan={**self.ids,'run':self.ids['orphan']}
        receipt,_,_=fixture.attest(self.db,orphan)
        archived=self.archive(receipt['request_id'],run=self.ids['orphan'])
        self.assertIn('unresolved_legacy_relationships',archived['warnings'])

    def test_old_snapshot_cannot_be_attested_after_retained_row_change(self):
        snap=fixture.capture(self.db,self.ids);doc=fixture.document(snap)
        self.db.sql("UPDATE public.vn_probes SET current_capital=1;")
        result,_,_=fixture.attest(self.db,self.ids,snapshot=snap,doc=doc,check=False)
        self.assertIn('legacy_snapshot_changed_review_again',result.stderr)

    def test_unbounded_or_old_snapshot_transactions_are_rejected(self):
        for prefix in ('BEGIN;','BEGIN ISOLATION LEVEL REPEATABLE READ;',
                       "BEGIN; SET LOCAL lock_timeout='1s'; SET LOCAL statement_timeout='8s';"):
            result=self.db.sql(prefix+' SET LOCAL ROLE vn_legacy_attestor; SELECT vn_legacy_evidence.capture('+
                legacy.literal(self.ids['owner'])+','+legacy.literal(self.ids['run'])+'); COMMIT;',role=fixture.ATTESTOR,check=False)
            self.assertIn('bounded_read_committed_legacy_transaction_required',result.stderr)

    def test_late_review_or_archive_failure_leaves_no_partial_acknowledgment(self):
        snap=fixture.capture(self.db,self.ids);doc=fixture.document(snap)
        request=str(uuid4())
        expression='vn_legacy_evidence.attest('+','.join([legacy.literal(request),legacy.literal(self.ids['owner']),
            legacy.literal(self.ids['run']),fixture.literal_json(snap),fixture.literal_json(doc)])+')'
        result=self.db.sql(fixture.BOUND+'SET LOCAL ROLE vn_legacy_attestor; SELECT '+expression+'; SELECT 1/0; COMMIT;',role=fixture.ATTESTOR,check=False)
        self.assertIn('22012',result.stderr)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_legacy_evidence.reviews;',role=fixture.ADMIN),'0')
        receipt,_,_=fixture.attest(self.db,self.ids)
        expression='vn_legacy_evidence.archive('+','.join(legacy.literal(v) for v in (str(uuid4()),self.ids['run'],receipt['request_id']))+')'
        result=self.db.sql(fixture.BOUND+'SET LOCAL request.jwt.claim.sub='+legacy.literal(self.ids['owner'])+
            '; SELECT '+expression+'; SELECT 1/0; COMMIT;',role='authenticated',check=False)
        self.assertIn('22012',result.stderr)
        self.assertFalse(self.status()['archive_recorded'])

    def test_held_old_writer_causes_bounded_failure_then_stale_review_denial(self):
        receipt,_,_=fixture.attest(self.db,self.ids)
        held=self.db.begin_sql("BEGIN; UPDATE public.vn_probes SET current_capital=1; SELECT pg_advisory_lock(7319561); "+
            'DO $$ BEGIN LOOP EXIT WHEN (SELECT released FROM public.legacy_evidence_test_gate); PERFORM pg_sleep(.025); END LOOP; END $$; COMMIT;',timeout=8)
        try:
            self.db.wait_until("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid=7319561 AND granted);")
            result=self.archive(receipt['request_id'],check=False)
            self.assertIn('55P03',result.stderr)
        finally:self.db.sql('UPDATE public.legacy_evidence_test_gate SET released=true;');held.wait(timeout=8)
        self.assertIn('legacy_archive_evidence_required',self.archive(receipt['request_id'],check=False).stderr)
        self.assertFalse(self.status()['archive_recorded'])

    def test_archive_holds_writer_until_commit_then_new_change_invalidates_it(self):
        receipt,_,_=fixture.attest(self.db,self.ids)
        self.db.sql('GRANT SELECT ON public.legacy_evidence_test_gate TO authenticated;',role=fixture.ADMIN)
        expression='vn_legacy_evidence.archive('+','.join(legacy.literal(v) for v in (str(uuid4()),self.ids['run'],receipt['request_id']))+')'
        held=self.db.begin_sql(fixture.BOUND+'SET LOCAL request.jwt.claim.sub='+legacy.literal(self.ids['owner'])+'; SELECT '+expression+
            '; SELECT pg_advisory_lock(7319562); DO $$ BEGIN LOOP EXIT WHEN (SELECT released FROM public.legacy_evidence_test_gate); '
            'PERFORM pg_sleep(.025); END LOOP; END $$; COMMIT;',role='authenticated',timeout=8)
        try:
            self.db.wait_until("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid=7319562 AND granted);")
            writer=self.db.begin_sql("SET lock_timeout='4s'; UPDATE public.vn_probes SET current_capital=22;",timeout=6)
            self.db.wait_until("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE relation='public.vn_probes'::regclass AND NOT granted);")
            self.assertFalse(writer.done)
        finally:self.db.sql('UPDATE public.legacy_evidence_test_gate SET released=true;');held.wait(timeout=8)
        writer.wait(timeout=6)
        self.assertTrue(self.status()['archive_recorded'])
        self.assertFalse(self.status()['archived'])

    def test_fresh_review_after_mutation_can_archive_without_erasing_audit(self):
        first,_,_=fixture.attest(self.db,self.ids)
        self.archive(first['request_id'])
        self.db.sql("UPDATE public.vn_probes SET current_capital=12;")
        second,_,_=fixture.attest(self.db,self.ids)
        self.archive(second['request_id'])
        self.assertTrue(self.status()['archived'])
        page=self.call('vn_legacy_evidence.history('+legacy.literal(self.ids['run'])+',0,100)')
        self.assertEqual(len(page['records']),2)
        self.assertEqual([row['review_id'] for row in page['records']],[first['request_id'],second['request_id']])

    def test_history_bounds_are_finite(self):
        for args in ('-1,1','0,101','0,0','NULL,1','0,NULL'):
            result=self.call('vn_legacy_evidence.history('+legacy.literal(self.ids['run'])+','+args+')',check=False)
            self.assertIn('invalid_legacy_history_bound',result.stderr)

    def test_installation_late_failure_rolls_back_retirement_and_new_objects(self):
        class Cleanup:
            def addClassCleanup(self,fn):self.close=fn
        cleanup=Cleanup();db=fixture.start(cleanup)
        try:
            legacy.seed_legacy_rows(canonical_fixture.CapabilityDatabase(db))
            before=json.loads(db.scalar(legacy.MARKER+legacy.CATALOG.read_text()+'SELECT pg_temp.vn_legacy_catalog();'))
            with self.assertRaises(harness.SqlFailure):fixture.install(db,suffix='SELECT 1/0;')
            after=json.loads(db.scalar(legacy.MARKER+legacy.CATALOG.read_text()+'SELECT pg_temp.vn_legacy_catalog();'))
            self.assertEqual(before,after)
            self.assertEqual(db.scalar("SELECT to_regnamespace('vn_legacy_evidence') IS NULL;"),'t')
            self.assertEqual(db.scalar("SELECT count(*) FROM pg_roles WHERE rolname='vn_legacy_attestor';"),'0')
            self.assertEqual(db.scalar("SELECT has_table_privilege('service_role','public.vn_trades','INSERT');"),'t')
        finally:cleanup.close()

    def test_unexpected_installer_default_function_grant_aborts_atomically(self):
        class Cleanup:
            def addClassCleanup(self,fn):self.close=fn
        cleanup=Cleanup();db=fixture.start(cleanup)
        try:
            legacy.seed_legacy_rows(canonical_fixture.CapabilityDatabase(db))
            db.sql('CREATE ROLE vn_test_unexpected_default NOLOGIN; ALTER DEFAULT PRIVILEGES FOR ROLE postgres '
                'GRANT EXECUTE ON FUNCTIONS TO vn_test_unexpected_default;',role=fixture.ADMIN)
            with self.assertRaises(harness.SqlFailure) as caught:fixture.install(db)
            self.assertIn('legacy_evidence_privilege_postcondition_failed',caught.exception.result.stderr)
            self.assertEqual(db.scalar("SELECT to_regnamespace('vn_legacy_evidence') IS NULL;"),'t')
            self.assertEqual(db.scalar("SELECT has_table_privilege('service_role','public.vn_trades','INSERT');"),'t')
            self.assertEqual(db.scalar("SELECT count(*) FROM pg_roles WHERE rolname='vn_legacy_attestor';"),'0')
        finally:cleanup.close()


if __name__=='__main__':unittest.main()
