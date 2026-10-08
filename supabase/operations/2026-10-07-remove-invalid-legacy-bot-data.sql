-- User-authorized removal of invalid pre-existing Von Neumann research data.
-- Exact Dashboard target must be verified externally before this operation.
-- Recovery: original mode-0600 private row snapshot; do not restore invalid data
-- into an accepted v5 ledger. No schema, Auth, migration-history or grants change.
BEGIN;
SET LOCAL transaction_timeout='25s';
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='500ms';
SET LOCAL ROLE vn_contract_owner;
DO $$ BEGIN
 PERFORM 1 FROM vn_release.state WHERE singleton AND state='closed' AND epoch=0 FOR UPDATE;
 IF NOT FOUND OR EXISTS(SELECT 1 FROM vn_durability.runs) THEN
  RAISE EXCEPTION 'legacy_purge_requires_empty_closed_v5'; END IF;
END $$;
RESET ROLE;
LOCK TABLE public.vn_colonies, public.vn_probes, public.vn_trades, public.vn_fitness_snapshots, public.vn_generation_stats IN SHARE ROW EXCLUSIVE MODE NOWAIT;
DO $$ BEGIN
 IF (SELECT count(*) FROM supabase_migrations.schema_migrations) <> 15 THEN
  RAISE EXCEPTION 'legacy_purge_history_changed'; END IF;
 IF EXISTS(SELECT 1 FROM pg_catalog.pg_constraint c WHERE c.contype='f' AND c.confrelid=ANY(ARRAY['public.vn_colonies'::regclass,'public.vn_probes'::regclass,'public.vn_trades'::regclass,'public.vn_fitness_snapshots'::regclass,'public.vn_generation_stats'::regclass]) AND NOT c.conrelid=ANY(ARRAY['public.vn_colonies'::regclass,'public.vn_probes'::regclass,'public.vn_trades'::regclass,'public.vn_fitness_snapshots'::regclass,'public.vn_generation_stats'::regclass])) THEN RAISE EXCEPTION 'legacy_purge_external_dependency'; END IF;
 IF (SELECT count(*) <> 8 OR md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]'::jsonb)::text) <> 'cce2737ed4697f814674e2b84372c3fd' FROM public.vn_colonies t) THEN RAISE EXCEPTION 'legacy_purge_original_rows_changed'; END IF;
 IF (SELECT count(*) <> 497 OR md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]'::jsonb)::text) <> '77fb123a8818732f9459fd3ba5eaf1fe' FROM public.vn_probes t) THEN RAISE EXCEPTION 'legacy_purge_original_rows_changed'; END IF;
 IF (SELECT count(*) <> 807 OR md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]'::jsonb)::text) <> '3317e6c287562f77618a1841c0a9b946' FROM public.vn_trades t) THEN RAISE EXCEPTION 'legacy_purge_original_rows_changed'; END IF;
 IF (SELECT count(*) <> 9837 OR md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]'::jsonb)::text) <> 'ba42b072fd7224d9693b639b90936a65' FROM public.vn_fitness_snapshots t) THEN RAISE EXCEPTION 'legacy_purge_original_rows_changed'; END IF;
 IF (SELECT count(*) <> 0 OR md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]'::jsonb)::text) <> 'd751713988987e9331980363e24189ce' FROM public.vn_generation_stats t) THEN RAISE EXCEPTION 'legacy_purge_original_rows_changed'; END IF;
END $$;
DELETE FROM public.vn_trades;
DELETE FROM public.vn_fitness_snapshots;
DELETE FROM public.vn_generation_stats;
DELETE FROM public.vn_probes;
DELETE FROM public.vn_colonies;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.vn_colonies) OR EXISTS(SELECT 1 FROM public.vn_probes) OR EXISTS(SELECT 1 FROM public.vn_trades) OR EXISTS(SELECT 1 FROM public.vn_fitness_snapshots) OR EXISTS(SELECT 1 FROM public.vn_generation_stats) THEN RAISE EXCEPTION 'legacy_purge_incomplete'; END IF;
END $$;
COMMIT;
