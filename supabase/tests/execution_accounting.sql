-- Verify The Dashboard / fxpxsciltakyypunglzr / cqfnnaunmupdyobkyqfo first.
-- Only temporary copied-schema rows are fixtures; this does not test RLS/FKs.
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';
SET LOCAL search_path = pg_catalog, pg_temp;
CREATE TEMP TABLE execution_trades
  (LIKE public.vn_trades INCLUDING DEFAULTS INCLUDING CONSTRAINTS) ON COMMIT DROP;
DO $contract$
DECLARE
  fake_owner CONSTANT uuid := '00000000-0000-4000-8000-000000000001';
  fake_probe CONSTANT uuid := '00000000-0000-4000-8000-000000000002';
  expected CONSTANT jsonb := '{"version":"usd-reference-percentage-cost-v1","account_currency":"USD","config":{"fee_bps":10,"half_spread_bps":100,"slippage_bps":0},"entry":{"reference_price":100,"fill_price":101,"quantity":2,"notional":202,"fee":0.202,"cash_debit":202.202,"spread_cost":2,"slippage_cost":0},"exit":{"kind":"fill","reference_price":110,"fill_price":108.9,"quantity":2,"notional":217.8,"fee":0.2178,"cash_credit":217.5822,"spread_cost":2.2,"slippage_cost":0,"gross_pnl":15.8,"net_pnl":15.3802,"net_return":0.07606354041997607}}';
  stored jsonb;
  trade_id uuid;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid='pg_temp.execution_trades'::regclass
    AND attname='execution' AND atttypid='jsonb'::regtype AND NOT attnotnull AND NOT attisdropped)
  THEN RAISE EXCEPTION 'Execution metadata must be nullable JSONB'; END IF;
  INSERT INTO pg_temp.execution_trades (user_id,probe_id,side,entry_price,amount)
    VALUES(fake_owner,fake_probe,'BUY',100,202.202) RETURNING execution INTO stored;
  IF stored IS NOT NULL THEN RAISE EXCEPTION 'Legacy trade received invented execution metadata'; END IF;
  INSERT INTO pg_temp.execution_trades (user_id,probe_id,side,entry_price,amount,execution)
    VALUES(fake_owner,fake_probe,'BUY',101,202.202,jsonb_set(expected,'{exit}','null')) RETURNING id INTO trade_id;
  UPDATE pg_temp.execution_trades SET exit_price=108.9,pnl=15.3802,
    pnl_pct=7.606354041997607,execution=expected WHERE id=trade_id RETURNING execution INTO stored;
  IF stored IS DISTINCT FROM expected THEN RAISE EXCEPTION 'Execution metadata failed to round-trip'; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_temp.execution_trades WHERE id=trade_id
    AND pnl=15.3802 AND pnl_pct=7.606354041997607 AND execution->'exit'->>'kind'='fill')
  THEN RAISE EXCEPTION 'Ledger values lost precision'; END IF;
END;
$contract$;
SELECT 'execution_accounting_schema_ok' AS contract_result;
ROLLBACK;
