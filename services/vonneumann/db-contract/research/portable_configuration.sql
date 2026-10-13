-- Original portable v2 configuration contract. Offline proof, never runtime authority.
-- This reviewed literal is generated from the original v2 template; it is not
-- inferred from the request. JSONB exact equality preserves numeric tags/types.
DO $guard$ BEGIN
 IF current_setting('dashboard.portable_configuration_fixture',true) IS DISTINCT FROM 'offline-v2'
    OR to_regprocedure('vn_numeric_research.audit(text,integer)') IS NULL THEN
  RAISE EXCEPTION 'offline_portable_configuration_fixture_required' USING ERRCODE='22023'; END IF;
END $guard$;
CREATE SCHEMA vn_portable_configuration_research;
REVOKE ALL ON SCHEMA vn_portable_configuration_research FROM PUBLIC;

CREATE FUNCTION vn_portable_configuration_research.template() RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $function$
 SELECT '{"assessment_policy":"ga-portable-provider-assessment-research-v2","asset":"SOL/USD","candle_seconds":{"$integer":"900"},"code_version":"fresh-ga-portable-provider-research-v2","counter_policy":{"generation_maximum":"2147483647","last_revision":"stop_only","maximum":"9223372036854775807","ordinary_revision_maximum":"9223372036854775806","overflow":"reject_without_install","timestamp_maximum":"1099511627776","version":"signed-bigint-reserved-stop-research-v1"},"execution":{"account_currency":"USD","bps_scale":{"$integer":"6"},"cash_scale":{"$integer":"36"},"config":{"fee_bps":"0","half_spread_bps":"0","slippage_bps":"0"},"cost_assumptions":"uncalibrated_scenario","price_scale":{"$integer":"18"},"quantity_scale":{"$integer":"18"},"rounding":{"buy_price":"up","fee":"up","quantity":"down","residual":"retain_cash","sell_price":"down"},"valuation":"reference_mark","version":"usd-reference-decimal-v2"},"horizon_seconds":{"$integer":"3600"},"initial_cash":"1000","lifecycle_policy":{"account_loss_bps":"3000","death_drawdown_bps":"2000","max_lifespan_seconds":{"$integer":"0"},"version":"ga-active-common-cohort-portable-research-v2"},"max_generations":{"$integer":"2147483647"},"max_positions":{"$integer":"8"},"mutation_policy":{"asexual_rate_per_million":{"$integer":"300000"},"asset":"fixed_SOL/USD_no_mutation_draw","decision":"integer_cross_product_lt","domains":{"ema_fast":[{"$integer":"3"},{"$integer":"12"}],"ema_slow":[{"$integer":"15"},{"$integer":"60"}]},"epoch_event_maximum":{"$integer":"2147483647"},"genes":["ema_fast","ema_slow"],"radii":{"ema_fast":{"$integer":"3"},"ema_slow":{"$integer":"15"}},"rejection_attempts":{"$integer":"256"},"rounding":"none_integer_sum_then_clamp","sexual_rate_per_million":{"$integer":"200000"},"step":"difference_of_two_uniform_integers_inclusive_zero_radius","uniform_denominator":"9007199254740992","version":"ema-period-triangular-integer-v1","word_budget":{"$integer":"2048"}},"population":{"$integer":"8"},"profile":"ema-ga-portable-provider-research-v2","search_seed":"0","seed_capital":"100","source":"synthetic-exact-fixture-v1","source_policy":{"asset":"SOL/USD","candle_completion_us":{"$integer":"5000000"},"candle_seconds":{"$integer":"900"},"chain":"solana","clock_policy":"conservative-integer-microseconds-v1","denomination":"USD","epoch":"00000000-0000-0000-0000-000000000001","evidence_trust":"worker-parsed-records-and-manifests-v1","future_tolerance_us":{"$integer":"2000000"},"max_history_bars":{"$integer":"64"},"max_receipt_age_us":{"$integer":"5000000"},"max_source_age_us":{"$integer":"30000000"},"mint":"So11111111111111111111111111111111111111112","outlier_policy":"provider-default-omitted","seed_bars":{"$integer":"61"},"sequence_maximum":"9223372036854775806","source_order":"strict-block-ref-nondecreasing-estimate-v1","source_time_policy":"jupiter-block-id-as-slot-estimated-time-v1","valuation":"reference_mark","version":"ga-provider-source-research-v1"},"strategy":"genetic_algorithm"}'::jsonb
$function$;

CREATE FUNCTION vn_portable_configuration_research.amount(value jsonb,digits integer) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE raw text:=value#>>'{}'; amount numeric; canonical text; whole text; tail text;
BEGIN
 IF digits IS NULL OR digits NOT IN (6,36) OR jsonb_typeof(value) IS DISTINCT FROM 'string'
    OR length(raw)>75 OR raw !~ '^(0|[1-9][0-9]*)(\.[0-9]{1,36})?$' THEN
  RAISE EXCEPTION 'portable_configuration_amount' USING ERRCODE='22023'; END IF;
 amount:=raw::numeric;
 IF amount>1e36 OR scale(amount)>digits THEN RAISE EXCEPTION 'portable_configuration_amount' USING ERRCODE='22023'; END IF;
 whole:=trunc(amount)::text; tail:=rtrim(split_part(raw,'.',2),'0');
 canonical:=whole||CASE WHEN tail='' THEN '' ELSE '.'||tail END;
 IF raw IS DISTINCT FROM canonical THEN RAISE EXCEPTION 'portable_configuration_amount' USING ERRCODE='22023'; END IF;
 RETURN amount*power(10::numeric,digits);
END $function$;

CREATE FUNCTION vn_portable_configuration_research.validate(value jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE reviewed jsonb:=vn_portable_configuration_research.template(); masked jsonb:=value;
 path text[]; paths text[]:=ARRAY['initial_cash','seed_capital','search_seed','execution/config/fee_bps',
 'execution/config/half_spread_bps','execution/config/slippage_bps','lifecycle_policy/account_loss_bps','source_policy/epoch'];
 field text; setting jsonb; initial numeric; seed numeric; fee numeric; spread numeric; slip numeric;
BEGIN
 FOREACH field IN ARRAY paths LOOP
  path:=string_to_array(field,'/'); setting:=value#>path;
  IF jsonb_typeof(setting) IS DISTINCT FROM 'string' OR length(setting#>>'{}') NOT BETWEEN 1 AND 75 THEN
   RAISE EXCEPTION 'portable_configuration_type_or_policy' USING ERRCODE='22023'; END IF;
  masked:=jsonb_set(masked,path,reviewed#>path,false);
 END LOOP;
 IF masked IS DISTINCT FROM reviewed THEN
  RAISE EXCEPTION 'portable_configuration_type_or_policy' USING ERRCODE='22023'; END IF;
 initial:=vn_portable_configuration_research.amount(value->'initial_cash',36);
 seed:=vn_portable_configuration_research.amount(value->'seed_capital',36);
 fee:=vn_portable_configuration_research.amount(value#>'{execution,config,fee_bps}',6);
 spread:=vn_portable_configuration_research.amount(value#>'{execution,config,half_spread_bps}',6);
 slip:=vn_portable_configuration_research.amount(value#>'{execution,config,slippage_bps}',6);
 IF seed<1e36 OR seed*8>initial OR fee>=1e10 OR spread+slip>=1e10 THEN
  RAISE EXCEPTION 'portable_configuration_economics' USING ERRCODE='22023'; END IF;
 IF value->>'search_seed' !~ '^(0|[1-9][0-9]{0,19})$' OR (value->>'search_seed')::numeric>18446744073709551615
    OR value#>>'{lifecycle_policy,account_loss_bps}' !~ '^[1-9][0-9]{0,4}$'
    OR (value#>>'{lifecycle_policy,account_loss_bps}')::integer>10000
    OR value#>>'{source_policy,epoch}' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
  RAISE EXCEPTION 'portable_configuration_setting' USING ERRCODE='22023'; END IF;
 RETURN value;
END $function$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_portable_configuration_research FROM PUBLIC;
