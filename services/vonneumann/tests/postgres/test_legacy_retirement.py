"""Captured legacy grant retirement, preserved evidence and overlap acceptance."""
from __future__ import annotations
import json
import hashlib
import os
import unittest

from tests.postgres import harness
from tests.postgres import legacy_fixture as fixture


@unittest.skipUnless(os.environ.get(harness.OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class LegacyRetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = harness.IsolatedPostgres()
        cls.addClassCleanup(cls.db.close)
        cls.db.start()
        cls.db.sql(fixture.legacy_bootstrap())
        cls.db.sql("""
CREATE TABLE public.legacy_unrelated_sentinel (id integer PRIMARY KEY, value text);
INSERT INTO public.legacy_unrelated_sentinel VALUES (1,'preserve');
CREATE TABLE public.legacy_test_gate (released boolean NOT NULL);
INSERT INTO public.legacy_test_gate VALUES(false);
GRANT SELECT ON public.legacy_test_gate TO authenticated;
""")

    def setUp(self):
        self.extra_roles=[]
        self.db.sql('DROP SCHEMA IF EXISTS vn_legacy CASCADE;\n'+
            'DROP TABLE IF EXISTS '+', '.join('public.'+t for t in fixture.TABLES)+' CASCADE;\n'+
            'TRUNCATE auth.users CASCADE; UPDATE public.legacy_test_gate SET released=false;')
        self.db.sql(fixture.captured_legacy_schema())
        self.ids=fixture.seed_legacy_rows(self.db)

    def tearDown(self):
        for role in self.extra_roles:
            self.db.sql('DROP OWNED BY '+fixture.ident(role)+' CASCADE; DROP ROLE '+fixture.ident(role)+';')

    def catalog(self):
        return json.loads(self.db.scalar(fixture.MARKER+fixture.CATALOG.read_text()+
            '\nSELECT pg_temp.vn_legacy_catalog();'))

    def evidence(self):
        values=[]
        for t in fixture.TABLES:
            values.append(json.loads(self.db.scalar("SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),"
                "'[]'::jsonb) FROM public."+t+' t;')))
        return values

    def retire(self, prefix=None, suffix='', check=True):
        return self.db.sql((prefix or fixture.review_sql(self.db))+
            fixture.RETIREMENT.read_text().removesuffix('COMMIT;\n')+suffix+'\nCOMMIT;',
            check=check,timeout=12)

    def classify(self, run=None, owner=None, role='authenticated'):
        # run=None explicitly addresses unbound legacy rows; no synthetic run ID.
        owner=owner or self.ids['owner']
        return json.loads(self.db.scalar('SET request.jwt.claim.sub='+fixture.literal(owner)+'; '+
            'SELECT vn_legacy.classify_run('+fixture.literal(run)+'::uuid);',role=role))

    def add_role(self, suffix, *, inherit=True, settable=True, admin=False):
        role='legacy_test_'+suffix
        self.extra_roles.append(role)
        self.db.sql('CREATE ROLE '+fixture.ident(role)+' NOLOGIN NOSUPERUSER NOCREATEROLE NOBYPASSRLS; '+
            'GRANT '+fixture.ident(role)+' TO authenticated WITH INHERIT '+str(inherit).upper()+
            ', SET '+str(settable).upper()+', ADMIN '+str(admin).upper()+';')
        return role

    def test_captured_shape_and_all_eight_initial_privileges(self):
        v=self.catalog()
        for field,count in [('tables',5),('columns',93),('constraints',19),('indexes',25),('policies',18),('triggers',2)]:
            self.assertEqual(len(v[field]),count)
        self.assertEqual(len(v['memberships']),3)
        self.assertEqual(len(v['defaults']),6)
        for role in ('anon','authenticated','service_role'):
            for t in fixture.TABLES:
                for p in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN'):
                    self.assertEqual(self.db.scalar(f"SELECT has_table_privilege('{role}','public.{t}','{p}');"),'t')

    def test_retirement_preserves_rows_definitions_policies_defaults_and_unrelated_objects(self):
        before=self.catalog(); rows=self.evidence()
        sentinel=self.db.scalar("SELECT relacl::text FROM pg_class WHERE oid='public.legacy_unrelated_sentinel'::regclass;")
        self.retire()
        after=self.catalog()
        for k in before:
            if k not in ('table_acl','column_acl'): self.assertEqual(after[k],before[k],k)
        self.assertEqual(self.evidence(),rows)
        self.assertEqual(self.db.scalar("SELECT relacl::text FROM pg_class WHERE oid='public.legacy_unrelated_sentinel'::regclass;"),sentinel)
        self.assertEqual(self.db.scalar("SELECT value FROM public.legacy_unrelated_sentinel WHERE id=1;"),'preserve')
        self.db.sql('CREATE TABLE public.legacy_new_unrelated_after (id integer);')
        try:
            self.assertEqual(self.db.scalar("SELECT has_table_privilege('authenticated','public.legacy_new_unrelated_after','INSERT,MAINTAIN');"),'t')
        finally: self.db.sql('DROP TABLE public.legacy_new_unrelated_after;')

    def test_direct_dml_and_maintenance_privileges_are_denied_for_every_api_role(self):
        self.retire()
        statements=[
            f"INSERT INTO public.vn_probes(user_id,probe_name) VALUES('{self.ids['owner']}','forbidden');",
            "UPDATE public.vn_probes SET current_capital=999;",
            "DELETE FROM public.vn_probes;", "TRUNCATE public.vn_probes;",
            "CREATE TABLE public.legacy_forbidden_fk (id uuid REFERENCES public.vn_probes(id));",
            "CREATE TRIGGER legacy_forbidden BEFORE UPDATE ON public.vn_probes FOR EACH ROW EXECUTE FUNCTION public.vn_set_updated_at();",
            'REINDEX TABLE public.vn_probes;', 'LOCK TABLE public.vn_probes IN ACCESS EXCLUSIVE MODE;',
        ]
        for role in ('anon','authenticated','service_role','authenticator'):
            for t in fixture.TABLES:
                for privilege in ('INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN'):
                    self.assertEqual(self.db.scalar(f"SELECT has_table_privilege('{role}','public.{t}','{privilege}');"),'f')
                for privilege in ('INSERT','UPDATE','REFERENCES'):
                    self.assertEqual(self.db.scalar(f"SELECT has_any_column_privilege('{role}','public.{t}','{privilege}');"),'f')
            for statement in statements:
                with self.subTest(role=role,sql=statement.split()[0]):
                    result=self.db.sql('BEGIN; SET request.jwt.claim.sub='+fixture.literal(self.ids['owner'])+'; '+
                        statement+' ROLLBACK;',role=role,check=False)
                    self.assertNotEqual(result.returncode,0)
                    self.assertIn('42501',result.stderr)
        self.assertEqual(self.db.scalar("SELECT rolbypassrls FROM pg_roles WHERE rolname='service_role';"),'t')

    def test_owner_reads_survive_but_other_owner_and_anon_cannot_read_owned_rows(self):
        self.retire()
        for role,owner,count in [('authenticated',self.ids['owner'],3),('authenticated',self.ids['other'],1),('anon',None,0)]:
            prefix='' if owner is None else 'SET request.jwt.claim.sub='+fixture.literal(owner)+'; '
            self.assertEqual(self.db.scalar(prefix+'SELECT count(*) FROM public.vn_probes;',role=role),str(count))
        result=self.db.sql('SELECT vn_legacy.classify_run('+fixture.literal(self.ids['other_run'])+');',role='authenticated',check=False)
        self.assertIn('42501',result.stderr)
        result=self.db.sql('SET request.jwt.claim.sub='+fixture.literal(self.ids['owner'])+'; SELECT vn_legacy.classify_run('+
            fixture.literal(self.ids['other_run'])+');',role='authenticated',check=False)
        self.assertIn('P0002',result.stderr)
        for role in ('anon','service_role','authenticator'):
            result=self.db.sql('SELECT vn_legacy.classify_run(NULL);',role=role,check=False)
            self.assertIn('42501',result.stderr)

    def test_classifier_keeps_stopped_unfenced_and_open_evidence_unreconciled(self):
        self.retire()
        v=self.classify(self.ids['run'])
        self.assertEqual(v['authority'],'legacy_unfenced')
        self.assertEqual(v['saved_colony']['status'],'stopped')
        self.assertFalse(v['archive_eligible'])
        self.assertFalse(v['live_holdings_verified'])
        self.assertFalse(v['restoration_available'])
        self.assertEqual(v['counts']['trades']['open_records'],1)
        self.assertEqual(v['counts']['trades']['execution_unavailable'],1)
        self.assertEqual(v['counts']['samples']['metrics_unavailable'],1)
        self.assertIn('writer_drain_unproven',v['archive_blockers'])
        self.assertIn('unreconciled_open_records',v['archive_blockers'])
        self.assertEqual(v['currency_policy'],'legacy_unknown')
        self.assertEqual(v['sampling_policy'],'legacy_unknown')
        self.assertNotIn('genome',json.dumps(v))

    def test_classifier_retains_orphan_unbound_and_scalar_parent_unknowns(self):
        self.retire()
        v=self.classify(self.ids['orphan'])
        self.assertEqual(v['authority'],'legacy_unmanaged')
        self.assertIsNone(v['saved_colony'])
        self.assertEqual(v['counts']['probes']['scalar_parent_records'],1)
        self.assertEqual(v['counts']['probes']['ancestry_array_unavailable'],1)
        self.assertEqual(v['counts']['probes']['unresolved_parent_records'],1)
        self.assertIn('relationship_evidence_unresolved',v['archive_blockers'])
        unbound=self.classify()
        self.assertIsNone(unbound['run_id'])
        self.assertEqual(unbound['counts']['probes']['rows'],1)
        self.assertIn('unbound_run',unbound['archive_blockers'])

    def test_complete_old_fields_and_zero_open_trades_do_not_prove_archive_eligibility(self):
        self.db.sql("UPDATE public.vn_trades SET closed_at=now(),execution='{}',exit_price=100,pnl=0,pnl_pct=0,exit_reason='SIGNAL_EXIT'; "+
            "UPDATE public.vn_probes SET metrics='{}'; UPDATE public.vn_fitness_snapshots SET metrics='{}';")
        self.retire()
        v=self.classify(self.ids['run'])
        self.assertEqual(v['counts']['trades']['open_records'],0)
        self.assertEqual(v['counts']['trades']['execution_unavailable'],0)
        self.assertNotIn('unreconciled_open_records',v['archive_blockers'])
        self.assertFalse(v['archive_eligible'])
        self.assertFalse(v['metrics_verified'])
        self.assertFalse(v['execution_verified'])
        self.assertFalse(v['ancestry_verified'])
        self.assertIn('reconciliation_unproven',v['archive_blockers'])

    def test_explicit_column_and_public_write_grants_are_retired_with_select_preserved(self):
        self.db.sql('GRANT UPDATE(current_capital),INSERT(probe_name),REFERENCES(id),SELECT(probe_name) ON public.vn_probes TO authenticated; '+
            'GRANT UPDATE(current_capital) ON public.vn_probes TO PUBLIC;')
        self.retire()
        acl=self.catalog()['column_acl']
        self.assertEqual([(a['privilege'],a['column']) for a in acl],[('SELECT','probe_name')])
        self.assertEqual(self.db.scalar("SELECT has_column_privilege('authenticated','public.vn_probes','probe_name','SELECT');"),'t')

    def test_catalog_drift_between_review_and_lock_fails_before_any_revocation(self):
        reviewed=fixture.review_sql(self.db)
        self.db.sql('GRANT UPDATE(current_capital) ON public.vn_probes TO PUBLIC;')
        before=self.catalog(); rows=self.evidence()
        result=self.retire(prefix=reviewed,check=False)
        self.assertIn('legacy_catalog_changed_review_again',result.stderr)
        self.assertEqual(self.catalog(),before)
        self.assertEqual(self.evidence(),rows)
        self.assertEqual(self.db.scalar("SELECT to_regnamespace('vn_legacy') IS NULL;"),'t')

    def test_inherited_and_settable_alias_writes_abort_atomically_without_changing_memberships(self):
        for suffix,inherit,settable in [('inherit',True,False),('set',False,True)]:
            role=self.add_role(suffix,inherit=inherit,settable=settable)
            self.db.sql('GRANT UPDATE(current_capital),REFERENCES(id) ON public.vn_probes TO '+fixture.ident(role)+';')
            before=self.catalog()
            result=self.retire(check=False)
            self.assertIn('legacy_column_write_path_survived_retirement',result.stderr)
            self.assertEqual(self.catalog(),before)
            self.assertEqual(self.db.scalar("SELECT has_table_privilege('authenticated','public.vn_trades','INSERT');"),'t')
            self.db.sql('REVOKE ALL(current_capital,id) ON public.vn_probes FROM '+fixture.ident(role)+';')

    def test_membership_admin_and_createrole_capabilities_require_separate_review(self):
        role=self.add_role('admin',admin=True)
        result=self.retire(check=False)
        self.assertIn('legacy_privileged_role_path_requires_review',result.stderr)
        self.db.sql('REVOKE '+fixture.ident(role)+' FROM authenticated; ALTER ROLE '+fixture.ident(role)+' CREATEROLE; '+
            'GRANT '+fixture.ident(role)+' TO authenticated WITH INHERIT FALSE,SET TRUE;')
        result=self.retire(check=False)
        self.assertIn('legacy_privileged_role_path_requires_review',result.stderr)

    def test_nested_maintain_role_path_is_not_fixed_by_rewriting_shared_memberships(self):
        first=self.add_role('nested_first',inherit=False,settable=True)
        second='legacy_test_nested_second'
        self.extra_roles.insert(0,second)
        self.db.sql('CREATE ROLE '+fixture.ident(second)+' NOLOGIN; GRANT '+fixture.ident(second)+' TO '+fixture.ident(first)+
            ' WITH INHERIT TRUE,SET TRUE; GRANT MAINTAIN ON public.vn_probes TO '+fixture.ident(second)+';')
        before=self.catalog()
        result=self.retire(check=False)
        self.assertIn('legacy_write_path_survived_retirement',result.stderr)
        self.assertEqual(self.catalog(),before)

    def test_function_or_policy_drift_requires_fresh_review(self):
        reviewed=fixture.review_sql(self.db)
        self.db.sql('ALTER FUNCTION public.vn_set_updated_at() SET search_path=pg_catalog;')
        try:
            result=self.retire(prefix=reviewed,check=False)
            self.assertIn('legacy_catalog_changed_review_again',result.stderr)
        finally: self.db.sql('ALTER FUNCTION public.vn_set_updated_at() RESET search_path;')
        reviewed=fixture.review_sql(self.db)
        self.db.sql('ALTER POLICY "vn_probes_select_own" ON public.vn_probes USING (true);')
        result=self.retire(prefix=reviewed,check=False)
        self.assertIn('legacy_catalog_changed_review_again',result.stderr)

    def test_classifier_owner_cannot_be_inherited_or_have_bypassrls(self):
        self.db.sql('GRANT vn_contract_owner TO authenticated WITH INHERIT TRUE,SET FALSE;')
        try:
            result=self.retire(check=False)
            self.assertIn('legacy_classifier_owner_requires_review',result.stderr)
        finally: self.db.sql('REVOKE vn_contract_owner FROM authenticated;')
        self.db.sql('ALTER ROLE vn_contract_owner BYPASSRLS;')
        try:
            result=self.retire(check=False)
            self.assertIn('legacy_classifier_owner_requires_review',result.stderr)
        finally: self.db.sql('ALTER ROLE vn_contract_owner NOBYPASSRLS;')

    def test_presentation_rollback_keeps_legacy_writes_denied_and_history_intact(self):
        before=self.evidence()
        self.retire()
        self.db.sql('DROP SCHEMA vn_legacy CASCADE;')
        self.assertEqual(self.evidence(),before)
        for role in ('anon','authenticated','service_role'):
            self.assertEqual(self.db.scalar(f"SELECT has_table_privilege('{role}','public.vn_probes','UPDATE');"),'f')

    def test_delegated_grant_option_and_security_definer_bypass_are_rejected(self):
        self.db.sql('GRANT UPDATE ON public.vn_probes TO authenticated WITH GRANT OPTION;')
        result=self.retire(check=False)
        self.assertIn('legacy_delegated_grants_require_review',result.stderr)
        self.db.sql('REVOKE GRANT OPTION FOR UPDATE ON public.vn_probes FROM authenticated; '+
            'CREATE FUNCTION public.vn_legacy_bypass() RETURNS bigint LANGUAGE sql SECURITY DEFINER AS $$SELECT count(*) FROM public.vn_probes$$;')
        try:
            result=self.retire(check=False)
            self.assertIn('legacy_indirect_authority_requires_review',result.stderr)
        finally: self.db.sql('DROP FUNCTION public.vn_legacy_bypass();')

    def test_unexpected_view_or_external_incoming_fk_requires_review(self):
        self.db.sql('CREATE VIEW public.legacy_dependency_view AS SELECT id FROM public.vn_probes;')
        try:
            result=self.retire(check=False)
            self.assertIn('legacy_indirect_authority_requires_review',result.stderr)
        finally: self.db.sql('DROP VIEW public.legacy_dependency_view;')
        self.db.sql('CREATE TABLE public.legacy_dependency_fk (id uuid REFERENCES public.vn_probes(id));')
        try:
            result=self.retire(check=False)
            self.assertIn('legacy_indirect_authority_requires_review',result.stderr)
        finally: self.db.sql('DROP TABLE public.legacy_dependency_fk;')

    def test_shared_default_sequence_dependency_requires_review_and_is_preserved(self):
        self.db.sql('CREATE SEQUENCE public.legacy_test_default_seq; '+
            "ALTER TABLE public.vn_probes ALTER COLUMN generation SET DEFAULT nextval('public.legacy_test_default_seq');")
        try:
            before=self.catalog()
            result=self.retire(check=False)
            self.assertIn('legacy_indirect_authority_requires_review',result.stderr)
            self.assertEqual(self.catalog(),before)
            self.assertEqual(self.db.scalar("SELECT to_regclass('public.legacy_test_default_seq') IS NOT NULL;"),'t')
        finally:
            self.db.sql('ALTER TABLE public.vn_probes ALTER COLUMN generation SET DEFAULT 0; DROP SEQUENCE public.legacy_test_default_seq;')

    def test_late_failure_restores_grants_and_removes_new_classifier(self):
        before=self.catalog(); rows=self.evidence()
        result=self.retire(suffix='SELECT 1/0;',check=False)
        self.assertIn('22012',result.stderr)
        self.assertEqual(self.catalog(),before)
        self.assertEqual(self.evidence(),rows)
        self.assertEqual(self.db.scalar("SELECT to_regnamespace('vn_legacy') IS NULL;"),'t')

    def test_old_writer_lock_times_out_without_partial_retirement(self):
        before=self.catalog()
        held=self.db.begin_sql('BEGIN; SET request.jwt.claim.sub='+fixture.literal(self.ids['owner'])+'; '+
            "UPDATE public.vn_probes SET current_capital=1 WHERE id="+fixture.literal(self.ids['probe'])+'; '+
            "SELECT pg_advisory_lock(7319551); DO $$ BEGIN LOOP EXIT WHEN (SELECT released FROM public.legacy_test_gate); "+
            "PERFORM pg_sleep(.025); END LOOP; END $$; COMMIT;",role='authenticated',timeout=8)
        try:
            self.db.wait_until("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid=7319551 AND granted);")
            result=self.retire(check=False)
            self.assertIn('55P03',result.stderr)
            self.assertEqual(self.catalog(),before)
        finally:
            self.db.sql('UPDATE public.legacy_test_gate SET released=true;')
            held.wait(timeout=8)
        self.retire()
        self.assertEqual(self.classify(self.ids['run'])['counts']['probes']['rows'],1)

    def test_session_open_before_retirement_cannot_late_write_after_commit(self):
        held=self.db.begin_sql('BEGIN; SET request.jwt.claim.sub='+fixture.literal(self.ids['owner'])+'; '+
            "SELECT pg_advisory_lock(7319552); DO $$ BEGIN LOOP EXIT WHEN (SELECT released FROM public.legacy_test_gate); "+
            "PERFORM pg_sleep(.025); END LOOP; END $$; "+
            "UPDATE public.vn_probes SET current_capital=999; COMMIT;",role='authenticated',timeout=8)
        try:
            self.db.wait_until("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND objid=7319552 AND granted);")
            self.retire()
        finally: self.db.sql('UPDATE public.legacy_test_gate SET released=true;')
        result=held.wait(timeout=8,check=False)
        self.assertIn('42501',result.stderr)
        self.assertEqual(self.db.scalar('SELECT current_capital FROM public.vn_probes WHERE id='+fixture.literal(self.ids['probe'])+';'),'0')

    def test_authenticator_set_role_denies_writes_after_retirement(self):
        self.retire()
        for role in ('anon','authenticated','service_role'):
            result=self.db.sql('BEGIN; SET LOCAL ROLE '+role+'; SET request.jwt.claim.sub='+fixture.literal(self.ids['owner'])+
                '; DELETE FROM public.vn_trades; ROLLBACK;',role='authenticator',check=False)
            self.assertIn('42501',result.stderr)

    def test_missing_or_duplicate_review_or_marker_cannot_apply(self):
        result=self.db.sql(fixture.RETIREMENT.read_text(),check=False)
        self.assertIn('isolated_legacy_review_required',result.stderr)
        for insert in ('','INSERT INTO pg_temp.dashboard_legacy_review SELECT pg_temp.vn_legacy_catalog() FROM generate_series(1,2);'):
            result=self.db.sql(fixture.MARKER+fixture.CATALOG.read_text()+insert+fixture.RETIREMENT.read_text(),check=False)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(self.db.scalar("SELECT has_table_privilege('authenticated','public.vn_probes','INSERT');"),'t')

    def test_reviewed_manifest_pins_the_executable_rehearsal_artifacts(self):
        manifest=json.loads((fixture.CONTRACT_DIR/'legacy_retirement_manifest.json').read_text())
        self.assertEqual(manifest['mode'],'isolated_rehearsal_only')
        self.assertFalse(manifest['production_application_available'])
        for name,digest in manifest['sources_sha256'].items():
            self.assertEqual(hashlib.sha256((fixture.CONTRACT_DIR/name).read_bytes()).hexdigest(),digest)

    def test_v5_atomic_projections_do_not_need_a_second_legacy_economic_writer(self):
        # Coexistence proof, not deployment of the multi-version laboratory.
        import time
        from uuid import uuid4
        from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
        from vonneumann.core import provider_lifecycle as core
        from tests.postgres import test_provider_contract as provider
        self.retire()
        legacy=self.evidence()
        self.db.apply_contract()
        self.addCleanup(lambda:self.db.sql('DROP SCHEMA vn_read,vn_projection,vn_durability CASCADE;'))
        projections=fixture.CONTRACT_DIR/'002_read_projections.sql'
        self.db.sql(fixture.MARKER+projections.read_text(),timeout=30)
        run,worker,command=(str(uuid4()) for _ in range(3))
        config=core.ProviderLifecycleConfig(ExactLifecycleConfig('genetic_algorithm',self.ids['owner'],run,asset='SOL/USD'),str(uuid4()))
        arguments=[fixture.literal(self.ids['owner']),fixture.literal(run),fixture.literal(worker),fixture.literal(command),
            fixture.literal(json.dumps(config.run_configuration()))+'::jsonb',fixture.literal(config.initial_cash),'120']
        self.db.sql('SELECT vn_durability.create_run('+','.join(arguments)+');',role='service_role')
        now,mono=time.time(),time.monotonic()
        candidate=core.bootstrap(config,provider.seed_history(now,mono),provider.decision_inputs(now,mono))
        payload={'version':5,'operations':candidate.operations,'transition':candidate.transition}
        arguments=[fixture.literal(self.ids['owner']),fixture.literal(run),fixture.literal(worker),'1','1',fixture.literal(str(uuid4())),
            fixture.literal(json.dumps(payload))+'::jsonb']
        self.db.sql('SELECT vn_durability.commit_command('+','.join(arguments)+');',role='service_role',timeout=30)
        self.assertEqual(self.db.scalar('SELECT engine_state FROM vn_durability.runs WHERE id='+fixture.literal(run)+';'),
            self.db.scalar('SELECT '+fixture.literal(json.dumps(candidate.state.to_dict()))+'::jsonb;'))
        page=json.loads(self.db.scalar('SET request.jwt.claim.sub='+fixture.literal(self.ids['owner'])+
            '; SELECT vn_read.page('+fixture.literal(run)+",'probes');",role='authenticated'))
        self.assertEqual(len(page['records']),8)
        self.assertEqual(self.evidence(),legacy)
        self.assertFalse(self.classify(self.ids['run'])['archive_eligible'])
