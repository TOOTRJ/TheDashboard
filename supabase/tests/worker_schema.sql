-- Worker database contract check. Run only after independently verifying:
-- project The Dashboard / fxpxsciltakyypunglzr,
-- organization cqfnnaunmupdyobkyqfo.
-- Example, with that project already verified as this workdir's linked target:
-- supabase --workdir /Users/redjester/Projects/Next/TheDashboard db query --linked --file /Users/redjester/Projects/Next/TheDashboard/supabase/tests/worker_schema.sql
--
-- Reads deployed schema metadata through LIKE/catalogs, never application rows.
-- All inserted rows use fake IDs and exist only in transaction-local temp tables.
-- LIKE does not copy foreign keys, triggers, or RLS policies. This checks column,
-- CHECK, and uniqueness contracts; it does NOT establish RLS isolation, valid
-- cross-table ownership, PostgREST cache readiness, or worker/UI round-trips.
-- A SQL error is a failed check: the caller must not treat a final ROLLBACK as
-- success. An aborted transaction also needs rollback or connection closure.

BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SET LOCAL search_path = pg_catalog, pg_temp;

CREATE TEMP TABLE worker_schema_trades
  (LIKE public.vn_trades INCLUDING DEFAULTS INCLUDING CONSTRAINTS)
  ON COMMIT DROP;

CREATE TEMP TABLE worker_schema_probes
  (LIKE public.vn_probes INCLUDING DEFAULTS INCLUDING CONSTRAINTS)
  ON COMMIT DROP;

-- INCLUDING INDEXES copies both constraint-backed and standalone unique indexes.
-- Keeping all of them detects an obsolete (user_id, generation) uniqueness rule.
CREATE TEMP TABLE worker_schema_generation_stats
  (LIKE public.vn_generation_stats INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)
  ON COMMIT DROP;

DO $worker_schema$
DECLARE
  fake_owner CONSTANT uuid := '00000000-0000-4000-8000-000000000001';
  fake_other_owner CONSTANT uuid := '00000000-0000-4000-8000-000000000002';
  fake_probe CONSTANT uuid := '00000000-0000-4000-8000-000000000003';
  fake_run_a CONSTANT uuid := '00000000-0000-4000-8000-000000000004';
  fake_run_b CONSTANT uuid := '00000000-0000-4000-8000-000000000005';
  fake_parent_a CONSTANT uuid := '00000000-0000-4000-8000-000000000006';
  fake_parent_b CONSTANT uuid := '00000000-0000-4000-8000-000000000007';
  reason text;
  rejected boolean;
  stored_parents jsonb;
  expected_parents jsonb;
  updated_count integer;
BEGIN
  -- Exercise the copied deployed CHECK, rather than compare its SQL spelling.
  FOREACH reason IN ARRAY ARRAY[
    'TAKE_PROFIT', 'STOP_LOSS', 'SIGNAL_EXIT', 'PROBE_DYING',
    'REPRODUCING', 'EVOLUTION', 'TERMINAL_LOSS', NULL
  ]::text[] LOOP
    INSERT INTO pg_temp.worker_schema_trades
      (user_id, probe_id, side, entry_price, amount, exit_reason)
    VALUES (fake_owner, fake_probe, 'BUY', 100, 10, reason);
  END LOOP;
  IF (SELECT count(*) FROM pg_temp.worker_schema_trades) <> 8 THEN
    RAISE EXCEPTION 'Trade exit contract: expected seven reasons and one open trade';
  END IF;

  rejected := false;
  BEGIN
    INSERT INTO pg_temp.worker_schema_trades
      (user_id, probe_id, side, entry_price, amount, exit_reason)
    VALUES (fake_owner, fake_probe, 'BUY', 100, 10, 'INVALID_SCHEMA_TEST_REASON');
  EXCEPTION WHEN check_violation THEN
    rejected := true;
  END;
  IF NOT rejected THEN
    RAISE EXCEPTION 'Trade exit contract: an unknown reason was accepted';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_attribute
    WHERE attrelid = 'pg_temp.worker_schema_probes'::regclass
      AND attname = 'parent_ids' AND NOT attisdropped
      AND atttypid = 'jsonb'::regtype AND attnotnull
  ) THEN
    RAISE EXCEPTION 'Lineage contract: parent_ids must be JSONB NOT NULL';
  END IF;

  INSERT INTO pg_temp.worker_schema_probes (user_id, probe_name)
  VALUES (fake_owner, 'schema-default-parent-check')
  RETURNING parent_ids INTO stored_parents;
  IF stored_parents IS DISTINCT FROM '[]'::jsonb THEN
    RAISE EXCEPTION 'Lineage contract: omitted parent_ids must default to an empty array';
  END IF;

  expected_parents := jsonb_build_array(fake_parent_a::text, fake_parent_b::text);
  INSERT INTO pg_temp.worker_schema_probes (user_id, probe_name, parent_ids)
  VALUES (fake_owner, 'schema-two-parent-check', expected_parents)
  RETURNING parent_ids INTO stored_parents;
  IF stored_parents IS DISTINCT FROM expected_parents THEN
    RAISE EXCEPTION 'Lineage contract: both ordered parent IDs must round-trip';
  END IF;

  rejected := false;
  BEGIN
    INSERT INTO pg_temp.worker_schema_probes (user_id, probe_name, parent_ids)
    VALUES (fake_owner, 'schema-null-parent-check', NULL);
  EXCEPTION WHEN not_null_violation THEN
    rejected := true;
  END;
  IF NOT rejected THEN
    RAISE EXCEPTION 'Lineage contract: explicit NULL parent_ids was accepted';
  END IF;

  -- Same owner/generation in different runs must coexist. Different owners
  -- may also use the same run/generation without an overbroad unique constraint.
  INSERT INTO pg_temp.worker_schema_generation_stats (user_id, run_id, generation)
  VALUES (fake_owner, fake_run_a, 7), (fake_owner, fake_run_b, 7),
         (fake_other_owner, fake_run_a, 7);

  rejected := false;
  BEGIN
    INSERT INTO pg_temp.worker_schema_generation_stats (user_id, run_id, generation)
    VALUES (fake_owner, fake_run_a, 7);
  EXCEPTION WHEN unique_violation THEN
    rejected := true;
  END;
  IF NOT rejected THEN
    RAISE EXCEPTION 'Generation contract: duplicate owner/run/generation was accepted';
  END IF;

  -- Exercise the exact repository conflict target; a deferrable constraint or
  -- an unsuitable partial index cannot silently pass this contract check.
  INSERT INTO pg_temp.worker_schema_generation_stats
    (user_id, run_id, generation, total_probes)
  VALUES (fake_owner, fake_run_a, 7, 12)
  ON CONFLICT (user_id, run_id, generation)
  DO UPDATE SET total_probes = EXCLUDED.total_probes
  RETURNING total_probes INTO updated_count;
  IF updated_count IS DISTINCT FROM 12
     OR (SELECT count(*) FROM pg_temp.worker_schema_generation_stats) <> 3 THEN
    RAISE EXCEPTION 'Generation contract: repository upsert failed to update exactly one row';
  END IF;
END;
$worker_schema$;

-- The only result is a fixed success marker, never rows or supplied values.
SELECT 'worker_schema_contracts_ok' AS contract_result;
ROLLBACK;
