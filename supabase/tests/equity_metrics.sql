-- Run only after verifying The Dashboard / fxpxsciltakyypunglzr / cqfnnaunmupdyobkyqfo.
-- Test copied schema with fake rows; do not insert into application tables.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';
SET LOCAL search_path = pg_catalog, pg_temp;

CREATE TEMP TABLE equity_metrics_probes
  (LIKE public.vn_probes INCLUDING DEFAULTS INCLUDING CONSTRAINTS) ON COMMIT DROP;
CREATE TEMP TABLE equity_metrics_snapshots
  (LIKE public.vn_fitness_snapshots INCLUDING DEFAULTS INCLUDING CONSTRAINTS) ON COMMIT DROP;

DO $metric_contract$
DECLARE
  table_name text;
  fake_owner CONSTANT uuid := '00000000-0000-4000-8000-000000000001';
  fake_probe CONSTANT uuid := '00000000-0000-4000-8000-000000000002';
  stored jsonb;
  legacy_metadata jsonb;
  expected CONSTANT jsonb := '{"fitness_version":"equity-roi-historical-dd-v1","status":"insufficient_samples","sharpe_ratio":null}';
BEGIN
  FOREACH table_name IN ARRAY ARRAY['equity_metrics_probes', 'equity_metrics_snapshots'] LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_attribute
      WHERE attrelid = ('pg_temp.' || table_name)::regclass AND attname = 'metrics'
        AND atttypid = 'jsonb'::regtype AND NOT attnotnull AND NOT attisdropped
    ) OR NOT EXISTS (
      SELECT 1 FROM pg_attribute
      WHERE attrelid = ('pg_temp.' || table_name)::regclass AND attname = 'sharpe_ratio'
        AND NOT attnotnull AND NOT attisdropped
    ) THEN
      RAISE EXCEPTION 'Metric metadata must be nullable JSONB and Sharpe must allow NULL';
    END IF;
  END LOOP;

  INSERT INTO pg_temp.equity_metrics_probes
    (user_id, probe_name, sharpe_ratio, metrics)
  VALUES (fake_owner, 'metric-contract', NULL, expected)
  RETURNING metrics INTO stored;
  IF stored IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'Probe metric metadata failed to round-trip';
  END IF;
  INSERT INTO pg_temp.equity_metrics_probes (user_id, probe_name, sharpe_ratio)
  VALUES (fake_owner, 'legacy-contract', 1.25)
  RETURNING metrics INTO legacy_metadata;
  IF legacy_metadata IS NOT NULL THEN
    RAISE EXCEPTION 'Legacy probe must not receive an invented metric policy';
  END IF;

  INSERT INTO pg_temp.equity_metrics_snapshots
    (user_id, probe_id, generation, fitness_score, sharpe_ratio, metrics)
  VALUES (fake_owner, fake_probe, 0, -.2, NULL, expected)
  RETURNING metrics INTO stored;
  IF stored IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'Snapshot metric metadata failed to round-trip';
  END IF;
  INSERT INTO pg_temp.equity_metrics_snapshots
    (user_id, probe_id, generation, fitness_score, sharpe_ratio)
  VALUES (fake_owner, fake_probe, 0, .1, 1.25)
  RETURNING metrics INTO legacy_metadata;
  IF legacy_metadata IS NOT NULL THEN
    RAISE EXCEPTION 'Legacy snapshot must not receive an invented metric policy';
  END IF;
END;
$metric_contract$;

SELECT 'equity_metrics_schema_ok' AS contract_result;
ROLLBACK;
