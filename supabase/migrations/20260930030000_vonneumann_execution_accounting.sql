-- New trades retain their versioned reference-account execution breakdown.
-- Existing rows remain NULL: their costs and accounting units are not inferred.
-- This additive history field is not a transactional ledger or restart checkpoint.
DO $execution_accounting$
BEGIN
  PERFORM pg_catalog.set_config('lock_timeout', '5s', true);

  ALTER TABLE public.vn_trades
    ADD COLUMN execution jsonb;
END;
$execution_accounting$;

NOTIFY pgrst, 'reload schema';
