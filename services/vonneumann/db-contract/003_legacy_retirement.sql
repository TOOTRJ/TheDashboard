-- DB-03A2D3B1: isolated legacy retirement/classification rehearsal ONLY.
-- Deliberately outside supabase/migrations. This is not the complete v5 DDL.
-- Runner must install legacy_catalog.sql and a reviewed pg_temp expectation.
BEGIN;
SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '8s';
DO $$ BEGIN
  IF current_setting('dashboard.contract_rehearsal', true) IS DISTINCT FROM 'db03a1-isolated'
     OR current_user <> 'postgres'
     OR to_regclass('pg_temp.dashboard_legacy_review') IS NULL THEN
    RAISE EXCEPTION 'isolated_legacy_review_required' USING ERRCODE='42501';
  END IF;
END $$;

-- Readers and in-flight old writers must finish before the reviewed snapshot.
-- This closes already-open transactions too; a saved stopped status is no drain.
LOCK TABLE public.vn_colonies, public.vn_fitness_snapshots,
  public.vn_generation_stats, public.vn_probes, public.vn_trades
  IN ACCESS EXCLUSIVE MODE;

DO $$ DECLARE expected jsonb; actual jsonb; BEGIN
  SELECT review INTO STRICT expected FROM pg_temp.dashboard_legacy_review;
  actual := pg_temp.vn_legacy_catalog();
  IF jsonb_typeof(expected)<>'object' OR octet_length(expected::text)>262144
     OR actual IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'legacy_catalog_changed_review_again' USING ERRCODE='55000';
  END IF;
  IF jsonb_array_length(actual->'tables')<>5 OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relname=ANY(pg_temp.vn_legacy_tables())
      AND (c.relkind<>'r' OR pg_get_userbyid(c.relowner)<>'postgres' OR NOT c.relrowsecurity))
     OR EXISTS (SELECT 1 FROM jsonb_array_elements(actual->'functions') f
       WHERE (f->>'security_definer')::boolean)
     OR jsonb_array_length(actual->'views')<>0
     OR jsonb_array_length(actual->'external_foreign_keys')<>0
     OR jsonb_array_length(actual->'sequences')<>0 THEN
    RAISE EXCEPTION 'legacy_indirect_authority_requires_review' USING ERRCODE='55000';
  END IF;
  IF EXISTS (SELECT 1 FROM jsonb_array_elements(actual->'roles') r
    WHERE (r->>'superuser')::boolean OR (r->>'create_role')::boolean
      OR (r->>'create_db')::boolean OR (r->>'replication')::boolean
      OR r->>'name'='postgres')
     OR (actual->>'membership_truncated')::boolean
     OR EXISTS (SELECT 1 FROM jsonb_array_elements(actual->'memberships') m WHERE (m->>'admin')::boolean) THEN
    RAISE EXCEPTION 'legacy_privileged_role_path_requires_review' USING ERRCODE='55000';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vn_contract_owner'
    AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcanlogin AND NOT rolcreaterole
    AND NOT rolcreatedb AND NOT rolreplication AND NOT rolinherit)
    OR EXISTS (SELECT 1 FROM pg_roles r WHERE r.rolname IN ('anon','authenticated','service_role','authenticator')
      AND (pg_has_role(r.oid,'vn_contract_owner','MEMBER') OR pg_has_role('vn_contract_owner',r.oid,'MEMBER'))) THEN
    RAISE EXCEPTION 'legacy_classifier_owner_requires_review' USING ERRCODE='55000';
  END IF;
  -- All grants issued by another grantor, and grant-option delegation, need a
  -- separate reviewed closure. RESTRICT avoids silently cascading dependencies.
  IF EXISTS (SELECT 1 FROM jsonb_array_elements(actual->'table_acl') a
    WHERE a->>'grantor'<>'postgres' OR (a->>'grantable')::boolean)
     OR EXISTS (SELECT 1 FROM jsonb_array_elements(actual->'column_acl') a
       WHERE a->>'grantor'<>'postgres' OR (a->>'grantable')::boolean) THEN
    RAISE EXCEPTION 'legacy_delegated_grants_require_review' USING ERRCODE='55000';
  END IF;
END $$;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
  ON public.vn_colonies, public.vn_fitness_snapshots, public.vn_generation_stats,
     public.vn_probes, public.vn_trades
  FROM PUBLIC, anon, authenticated, service_role, authenticator RESTRICT;

-- Explicit column pass, even though table REVOKE also revokes corresponding
-- column privileges. Preserve existing SELECT; never grant new anonymous reads.
DO $$ DECLARE t text; columns text; BEGIN
  FOREACH t IN ARRAY pg_temp.vn_legacy_tables() LOOP
    SELECT string_agg(quote_ident(attname),', ' ORDER BY attnum) INTO columns
      FROM pg_attribute WHERE attrelid=format('public.%I',t)::regclass
        AND attnum>0 AND NOT attisdropped;
    EXECUTE format('REVOKE INSERT (%s), UPDATE (%s), REFERENCES (%s) ON public.%I '
      'FROM PUBLIC, anon, authenticated, service_role, authenticator RESTRICT',
      columns,columns,columns,t);
  END LOOP;
END $$;

-- Reject remaining inheritance/SET ROLE authority instead of modifying roles
-- or grants on anything outside these five tables. A failure rolls back ALL.
DO $$ DECLARE r record; t text; privilege text; BEGIN
  FOR r IN SELECT (j->>'name') AS name FROM jsonb_array_elements(
    pg_temp.vn_legacy_catalog()->'roles') j LOOP
    FOREACH t IN ARRAY pg_temp.vn_legacy_tables() LOOP
      FOREACH privilege IN ARRAY ARRAY['INSERT','UPDATE','DELETE','TRUNCATE',
                                       'REFERENCES','TRIGGER','MAINTAIN'] LOOP
        IF has_table_privilege(r.name,format('public.%I',t),privilege) THEN
          RAISE EXCEPTION 'legacy_write_path_survived_retirement' USING ERRCODE='42501';
        END IF;
      END LOOP;
      FOREACH privilege IN ARRAY ARRAY['INSERT','UPDATE','REFERENCES'] LOOP
        IF has_any_column_privilege(r.name,format('public.%I',t),privilege) THEN
          RAISE EXCEPTION 'legacy_column_write_path_survived_retirement' USING ERRCODE='42501';
        END IF;
      END LOOP;
    END LOOP;
  END LOOP;
END $$;

-- Only the dedicated rehearsal owner gains the narrowly required read scope.
-- Production owner/credential creation and auth dependencies are a D3B2 gate.
GRANT SELECT ON public.vn_colonies, public.vn_fitness_snapshots,
  public.vn_generation_stats, public.vn_probes, public.vn_trades TO vn_contract_owner;
CREATE SCHEMA vn_legacy AUTHORIZATION vn_contract_owner;
REVOKE ALL ON SCHEMA vn_legacy FROM PUBLIC, anon, authenticated, service_role, authenticator;
SET LOCAL ROLE vn_contract_owner;
ALTER DEFAULT PRIVILEGES IN SCHEMA vn_legacy REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

CREATE FUNCTION vn_legacy.classify_run(run uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE owner_id uuid := auth.uid(); colony jsonb; counts jsonb; probes jsonb;
  trades jsonb; samples jsonb; generations bigint; blockers jsonb;
BEGIN
  IF owner_id IS NULL THEN RAISE EXCEPTION 'legacy_owner_required' USING ERRCODE='42501'; END IF;
  SELECT jsonb_build_object('status',c.status,'mode',c.mode) INTO colony
    FROM public.vn_colonies c WHERE c.user_id=owner_id AND c.id=run;
  SELECT jsonb_build_object('rows',count(*),
    'metrics_unavailable',count(*) FILTER(WHERE p.metrics IS NULL OR jsonb_typeof(p.metrics)<>'object'),
    'ancestry_array_unavailable',count(*) FILTER(WHERE p.parent_ids='[]'::jsonb OR jsonb_typeof(p.parent_ids)<>'array'),
    'scalar_parent_records',count(*) FILTER(WHERE p.parent_id IS NOT NULL),
    'unresolved_parent_records',count(*) FILTER(WHERE p.parent_id IS NOT NULL AND NOT EXISTS(
      SELECT 1 FROM public.vn_probes parent WHERE parent.id=p.parent_id AND parent.user_id=owner_id
        AND parent.run_id IS NOT DISTINCT FROM p.run_id))) INTO probes
    FROM public.vn_probes p WHERE p.user_id=owner_id AND p.run_id IS NOT DISTINCT FROM run;
  SELECT jsonb_build_object('rows',count(*),'open_records',count(*) FILTER(WHERE t.closed_at IS NULL),
    'execution_unavailable',count(*) FILTER(WHERE t.execution IS NULL OR jsonb_typeof(t.execution)<>'object'),
    'unresolved_probe_records',count(*) FILTER(WHERE NOT EXISTS(
      SELECT 1 FROM public.vn_probes p WHERE p.id=t.probe_id AND p.user_id=owner_id
        AND p.run_id IS NOT DISTINCT FROM t.run_id))) INTO trades
    FROM public.vn_trades t WHERE t.user_id=owner_id AND t.run_id IS NOT DISTINCT FROM run;
  SELECT jsonb_build_object('rows',count(*),
    'metrics_unavailable',count(*) FILTER(WHERE f.metrics IS NULL OR jsonb_typeof(f.metrics)<>'object'),
    'unresolved_probe_records',count(*) FILTER(WHERE NOT EXISTS(
      SELECT 1 FROM public.vn_probes p WHERE p.id=f.probe_id AND p.user_id=owner_id
        AND p.run_id IS NOT DISTINCT FROM f.run_id))) INTO samples
    FROM public.vn_fitness_snapshots f WHERE f.user_id=owner_id AND f.run_id IS NOT DISTINCT FROM run;
  SELECT count(*) INTO generations FROM public.vn_generation_stats g
    WHERE g.user_id=owner_id AND g.run_id IS NOT DISTINCT FROM run;
  IF colony IS NULL AND (probes->>'rows')::bigint=0 AND (trades->>'rows')::bigint=0
      AND (samples->>'rows')::bigint=0 AND generations=0 THEN
    RAISE EXCEPTION 'legacy_run_unavailable' USING ERRCODE='P0002';
  END IF;
  blockers := '["writer_drain_unproven","reconciliation_unproven","no_authoritative_checkpoint"]'::jsonb;
  IF run IS NULL THEN blockers := blockers || '"unbound_run"'::jsonb; END IF;
  IF (trades->>'open_records')::bigint>0 THEN
    blockers := blockers || '"unreconciled_open_records"'::jsonb;
  END IF;
  IF (probes->>'unresolved_parent_records')::bigint>0
      OR (trades->>'unresolved_probe_records')::bigint>0
      OR (samples->>'unresolved_probe_records')::bigint>0 THEN
    blockers := blockers || '"relationship_evidence_unresolved"'::jsonb;
  END IF;
  counts := jsonb_build_object('probes',probes,'trades',trades,'samples',samples,'generation_rows',generations);
  RETURN jsonb_build_object('version',1,'kind','legacy','owner_id',owner_id,'run_id',run,
    'authority',CASE WHEN colony IS NULL THEN 'legacy_unmanaged' ELSE 'legacy_unfenced' END,
    'saved_colony',colony,'counts',counts,'archive_eligible',false,'archive_blockers',blockers,
    'currency_policy','legacy_unknown','sampling_policy','legacy_unknown',
    'restoration_available',false,'live_holdings_verified',false,
    'metrics_verified',false,'execution_verified',false,'ancestry_verified',false);
END $$;
REVOKE ALL ON FUNCTION vn_legacy.classify_run(uuid) FROM PUBLIC, anon, authenticated, service_role, authenticator;
GRANT USAGE ON SCHEMA vn_legacy TO authenticated;
GRANT EXECUTE ON FUNCTION vn_legacy.classify_run(uuid) TO authenticated;
RESET ROLE;
COMMIT;
