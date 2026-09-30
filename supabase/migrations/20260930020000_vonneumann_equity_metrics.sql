-- Preserve unknown diagnostics as NULL and identify their calculation policy.
-- Existing rows keep metrics NULL: no historical results are reinterpreted.
-- The DO statement makes both table changes atomic even if a runner submits
-- separate statements. The caller must configure and verify its statement
-- deadline; SET LOCAL outside a transaction is not a timeout guarantee.
DO $equity_metrics$
BEGIN
  PERFORM pg_catalog.set_config('lock_timeout', '5s', true);

  ALTER TABLE public.vn_probes
    ADD COLUMN metrics jsonb,
    ALTER COLUMN sharpe_ratio DROP NOT NULL;

  ALTER TABLE public.vn_fitness_snapshots
    ADD COLUMN metrics jsonb,
    ALTER COLUMN sharpe_ratio DROP NOT NULL;
END;
$equity_metrics$;

NOTIFY pgrst, 'reload schema';
