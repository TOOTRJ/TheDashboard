-- DB-03A contract rehearsal ONLY. Not a Supabase migration or runtime dependency.
-- Run solely through tests.postgres.run in its disposable, isolated database.
-- The production VN projections, engine, browser deletion and grants have NOT
-- been cut over. Never deploy this file as a lease-only production patch.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '15s';
DO $$ BEGIN
  IF current_setting('dashboard.contract_rehearsal', true) IS DISTINCT FROM 'db03a1-isolated' THEN
    RAISE EXCEPTION 'isolated_contract_runner_required';
  END IF;
END $$;

CREATE SCHEMA vn_durability AUTHORIZATION vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
-- Schema-specific defaults cannot subtract the global PUBLIC EXECUTE default.
-- This changes only the dedicated fixture owner's defaults, never client roles.
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

CREATE DOMAIN vn_durability.balance AS numeric
  CHECK (VALUE >= 0 AND VALUE <= 1e36 AND scale(VALUE) <= 36);

CREATE TABLE vn_durability.runs (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES auth.users(id),
  worker_id uuid NOT NULL,
  fence bigint NOT NULL CHECK (fence > 0),
  revision bigint NOT NULL CHECK (revision > 0),
  lease_until timestamptz NOT NULL,
  status text NOT NULL CHECK (status IN ('starting','running','paused','risk_halted','stopped','failed')),
  requires_reconciliation boolean NOT NULL DEFAULT false,
  interrupted_at timestamptz,
  config jsonb NOT NULL CHECK (jsonb_typeof(config) = 'object' AND octet_length(config::text) <= 65536),
  command_version smallint NOT NULL CHECK (command_version IN (1,2)),
  initial_cash vn_durability.balance NOT NULL CHECK (initial_cash > 0),
  reserve vn_durability.balance NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (id, user_id)
);

CREATE TABLE vn_durability.accounts (
  run_id uuid NOT NULL,
  user_id uuid NOT NULL,
  id uuid NOT NULL,
  cash vn_durability.balance NOT NULL,
  initial_cash vn_durability.balance NOT NULL CHECK (initial_cash > 0),
  retired boolean NOT NULL DEFAULT false,
  PRIMARY KEY (run_id, id),
  UNIQUE (run_id, user_id, id),
  FOREIGN KEY (run_id, user_id) REFERENCES vn_durability.runs(id, user_id)
);

CREATE TABLE vn_durability.account_parents (
  run_id uuid NOT NULL,
  user_id uuid NOT NULL,
  account_id uuid NOT NULL,
  parent_id uuid NOT NULL,
  CHECK (account_id <> parent_id),
  PRIMARY KEY (run_id, account_id, parent_id),
  FOREIGN KEY (run_id, user_id, account_id) REFERENCES vn_durability.accounts(run_id, user_id, id),
  FOREIGN KEY (run_id, user_id, parent_id) REFERENCES vn_durability.accounts(run_id, user_id, id)
);

-- Distribution provenance is stored once and referenced by an entire cohort.
-- Its iteration string is evidence, not proof of an evaluated cohort table.
CREATE TABLE vn_durability.distributions (
  run_id uuid NOT NULL,
  user_id uuid NOT NULL,
  id uuid NOT NULL,
  stage text NOT NULL CHECK (stage IN ('bootstrap','update')),
  source_iteration_id text NOT NULL CHECK (length(source_iteration_id) BETWEEN 1 AND 256),
  previous_distribution_id uuid,
  CHECK ((stage='bootstrap' AND previous_distribution_id IS NULL) OR
         (stage='update' AND previous_distribution_id IS NOT NULL AND previous_distribution_id<>id)),
  PRIMARY KEY (run_id,id),
  UNIQUE (run_id,user_id,id),
  FOREIGN KEY (run_id,user_id) REFERENCES vn_durability.runs(id,user_id),
  FOREIGN KEY (run_id,user_id,previous_distribution_id)
    REFERENCES vn_durability.distributions(run_id,user_id,id)
);

CREATE TABLE vn_durability.distribution_sources (
  run_id uuid NOT NULL,
  user_id uuid NOT NULL,
  distribution_id uuid NOT NULL,
  source_id uuid NOT NULL,
  ordinal smallint NOT NULL CHECK (ordinal BETWEEN 0 AND 99),
  PRIMARY KEY (run_id,distribution_id,ordinal),
  UNIQUE (run_id,distribution_id,source_id),
  FOREIGN KEY (run_id,user_id,distribution_id) REFERENCES vn_durability.distributions(run_id,user_id,id),
  FOREIGN KEY (run_id,user_id,source_id) REFERENCES vn_durability.accounts(run_id,user_id,id)
);

CREATE TABLE vn_durability.account_lineage (
  run_id uuid NOT NULL,
  user_id uuid NOT NULL,
  account_id uuid NOT NULL,
  strategy text NOT NULL,
  operation text NOT NULL,
  source_iteration_id text,
  offspring_index smallint CHECK (offspring_index BETWEEN 0 AND 99),
  distribution_id uuid,
  evidence jsonb NOT NULL,
  PRIMARY KEY (run_id,account_id),
  UNIQUE (run_id,user_id,account_id),
  UNIQUE (run_id,source_iteration_id,offspring_index),
  FOREIGN KEY (run_id,user_id,account_id) REFERENCES vn_durability.accounts(run_id,user_id,id),
  FOREIGN KEY (run_id,user_id,distribution_id) REFERENCES vn_durability.distributions(run_id,user_id,id)
);

CREATE TABLE vn_durability.lineage_sources (
  run_id uuid NOT NULL,
  user_id uuid NOT NULL,
  account_id uuid NOT NULL,
  role text NOT NULL,
  source_id uuid NOT NULL,
  ordinal smallint NOT NULL CHECK (ordinal BETWEEN 0 AND 1),
  CHECK (account_id<>source_id),
  PRIMARY KEY (run_id,account_id,role,ordinal),
  UNIQUE (run_id,account_id,role,source_id),
  FOREIGN KEY (run_id,user_id,account_id) REFERENCES vn_durability.account_lineage(run_id,user_id,account_id),
  FOREIGN KEY (run_id,user_id,source_id) REFERENCES vn_durability.accounts(run_id,user_id,id)
);

CREATE TABLE vn_durability.positions (
  run_id uuid NOT NULL,
  user_id uuid NOT NULL,
  id uuid NOT NULL,
  account_id uuid NOT NULL,
  asset text NOT NULL CHECK (length(asset) BETWEEN 1 AND 64),
  quantity vn_durability.balance NOT NULL CHECK (quantity > 0),
  notional vn_durability.balance NOT NULL CHECK (notional > 0),
  entry_fee vn_durability.balance NOT NULL,
  proceeds vn_durability.balance,
  exit_fee vn_durability.balance,
  entry_execution jsonb,
  exit_execution jsonb,
  CHECK (exit_execution IS NULL OR entry_execution IS NOT NULL),
  closed boolean NOT NULL DEFAULT false,
  CHECK ((NOT closed AND proceeds IS NULL AND exit_fee IS NULL) OR
         (closed AND proceeds IS NOT NULL AND exit_fee IS NOT NULL AND proceeds >= exit_fee)),
  PRIMARY KEY (run_id, id),
  FOREIGN KEY (run_id, user_id, account_id) REFERENCES vn_durability.accounts(run_id, user_id, id)
);

-- One immutable committed command is also one ordered outbox event. Delivery
-- acknowledgements are deliberately not part of this immutable journal.
CREATE TABLE vn_durability.commands (
  run_id uuid NOT NULL,
  user_id uuid NOT NULL,
  id uuid NOT NULL,
  revision bigint NOT NULL CHECK (revision > 0),
  kind text NOT NULL CHECK (kind IN ('create','batch','interrupt')),
  request jsonb NOT NULL,
  request_hash bytea NOT NULL CHECK (octet_length(request_hash) = 32),
  response jsonb NOT NULL,
  committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (run_id, id),
  UNIQUE (run_id, revision),
  FOREIGN KEY (run_id, user_id) REFERENCES vn_durability.runs(id, user_id)
);

CREATE INDEX runs_owner ON vn_durability.runs(user_id, id);
CREATE INDEX accounts_owner ON vn_durability.accounts(user_id, run_id, id);
CREATE INDEX positions_owner ON vn_durability.positions(user_id, run_id, id);
CREATE UNIQUE INDEX one_open_position_per_asset
  ON vn_durability.positions(run_id, account_id, asset) WHERE NOT closed;
CREATE INDEX parents_owner ON vn_durability.account_parents(user_id, run_id);
CREATE INDEX commands_owner_sequence ON vn_durability.commands(user_id, run_id, revision);

ALTER TABLE vn_durability.runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.account_parents ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.distributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.distribution_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.account_lineage ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.lineage_sources ENABLE ROW LEVEL SECURITY;
CREATE POLICY owner_read ON vn_durability.runs FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.accounts FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.positions FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.account_parents FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.commands FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.distributions FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.distribution_sources FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.account_lineage FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.lineage_sources FOR SELECT TO authenticated USING (user_id = auth.uid());

-- Trusted internal helpers: never granted to an API role. No caller-set GUC can
-- confer write authority. Tables and SECURITY DEFINER functions have the same
-- dedicated NOLOGIN owner; clients receive neither owner membership nor DML.
CREATE FUNCTION vn_durability.exact_keys(value jsonb, keys text[]) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
BEGIN
  IF value IS NULL OR jsonb_typeof(value) IS DISTINCT FROM 'object' OR
     NOT value ?& keys OR value - keys <> '{}'::jsonb THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE = '22023';
  END IF;
END $$;

CREATE FUNCTION vn_durability.money(value jsonb) RETURNS numeric
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE result numeric; raw text;
BEGIN
  raw := value #>> '{}';
  IF value IS NULL OR jsonb_typeof(value) IS DISTINCT FROM 'string' OR
     length(raw) > 75 OR raw !~ '^(0|[1-9][0-9]*)(\.[0-9]{1,36})?$' THEN
    RAISE EXCEPTION 'invalid_amount' USING ERRCODE = '22023';
  END IF;
  result := raw::numeric;
  IF result > 1e36 THEN RAISE EXCEPTION 'invalid_amount' USING ERRCODE = '22023'; END IF;
  RETURN result;
END $$;

CREATE FUNCTION vn_durability.record_command(
  owner_id uuid, run uuid, command_id uuid, sequence bigint,
  command_kind text, request_body jsonb, result jsonb
) RETURNS void LANGUAGE sql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
  INSERT INTO vn_durability.commands(run_id,user_id,id,revision,kind,request,request_hash,response)
  VALUES (run,owner_id,command_id,sequence,command_kind,request_body,
          sha256(convert_to(request_body::text,'UTF8')),result);
$$;

-- Version-2 arithmetic uses integer-valued numeric units. div/mod avoid
-- PostgreSQL division scale selection; no ambient rounding context is trusted.
CREATE FUNCTION vn_durability.decimal_units(value jsonb, digits integer) RETURNS numeric
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE amount numeric;
BEGIN
  amount := vn_durability.money(value);
  IF digits NOT IN (6,18,36) OR scale(amount)>digits THEN
    RAISE EXCEPTION 'invalid_decimal_grid' USING ERRCODE='22023';
  END IF;
  RETURN trunc(amount*power(10::numeric,digits));
END $$;

CREATE FUNCTION vn_durability.decimal_text(units numeric, digits integer) RETURNS text
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE whole text; fraction text; divisor numeric;
BEGIN
  IF units IS NULL OR units<>trunc(units) OR digits NOT IN (6,18,36) THEN
    RAISE EXCEPTION 'invalid_decimal_units' USING ERRCODE='22023';
  END IF;
  divisor:=power(10::numeric,digits);
  whole:=div(abs(units),divisor)::text;
  fraction:=rtrim(lpad(trunc(mod(abs(units),divisor))::text,digits,'0'),'0');
  RETURN CASE WHEN units<0 THEN '-' ELSE '' END || whole ||
    CASE WHEN fraction='' THEN '' ELSE '.'||fraction END;
END $$;

CREATE FUNCTION vn_durability.execution_config(value jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE fee numeric; spread numeric; slip numeric; expected jsonb;
BEGIN
  PERFORM vn_durability.exact_keys(value,ARRAY['fee_bps','half_spread_bps','slippage_bps']);
  fee:=vn_durability.decimal_units(value->'fee_bps',6);
  spread:=vn_durability.decimal_units(value->'half_spread_bps',6);
  slip:=vn_durability.decimal_units(value->'slippage_bps',6);
  IF fee>=1e10 OR spread+slip>=1e10 THEN
    RAISE EXCEPTION 'invalid_execution_config' USING ERRCODE='22023';
  END IF;
  expected:=jsonb_build_object('fee_bps',vn_durability.decimal_text(fee,6),
    'half_spread_bps',vn_durability.decimal_text(spread,6),'slippage_bps',vn_durability.decimal_text(slip,6));
  IF value::text<>expected::text THEN
    RAISE EXCEPTION 'noncanonical_execution_config' USING ERRCODE='22023';
  END IF;
  RETURN expected;
END $$;

CREATE FUNCTION vn_durability.execution_policy(value jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE expected jsonb;
BEGIN
  expected:=jsonb_build_object('version','usd-reference-decimal-v2','account_currency','USD',
    'cost_assumptions','uncalibrated_scenario','valuation','reference_mark',
    'cash_scale',36,'quantity_scale',18,'price_scale',18,'bps_scale',6,
    'rounding',jsonb_build_object('buy_price','up','sell_price','down','quantity','down','fee','up','residual','retain_cash'),
    'config',vn_durability.execution_config(value->'config'));
  IF value IS NULL OR value::text<>expected::text THEN
    RAISE EXCEPTION 'invalid_execution_policy' USING ERRCODE='22023';
  END IF;
  RETURN expected;
END $$;

CREATE FUNCTION vn_durability.entry_evidence(value jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE cfg jsonb; budget numeric; reference numeric; fee_rate numeric; impact numeric;
        price numeric; quantity numeric; cap numeric; notional numeric; fee numeric; debit numeric; expected jsonb;
BEGIN
  PERFORM vn_durability.exact_keys(value,ARRAY['version','config','budget','reference_price','fill_price',
    'quantity','notional','fee','cash_debit','residual_budget']);
  cfg:=vn_durability.execution_config(value->'config');
  budget:=vn_durability.decimal_units(value->'budget',36);
  reference:=vn_durability.decimal_units(value->'reference_price',18);
  fee_rate:=vn_durability.decimal_units(cfg->'fee_bps',6);
  impact:=vn_durability.decimal_units(cfg->'half_spread_bps',6)+vn_durability.decimal_units(cfg->'slippage_bps',6);
  price:=div(reference*(1e10+impact)+1e10-1,1e10);
  IF budget<=0 OR reference<=0 OR price<=0 OR price>1e54 THEN
    RAISE EXCEPTION 'invalid_entry_evidence' USING ERRCODE='22023';
  END IF;
  cap:=div(budget*1e10,1e10+fee_rate);
  quantity:=div(cap,price);
  notional:=quantity*price;
  fee:=div(notional*fee_rate+1e10-1,1e10);
  debit:=notional+fee;
  IF quantity<=0 OR quantity>1e54 OR notional<=0 OR debit>budget OR debit>1e72 THEN
    RAISE EXCEPTION 'invalid_entry_evidence' USING ERRCODE='22023';
  END IF;
  expected:=jsonb_build_object('version','usd-reference-decimal-v2','config',cfg,
    'budget',vn_durability.decimal_text(budget,36),'reference_price',vn_durability.decimal_text(reference,18),
    'fill_price',vn_durability.decimal_text(price,18),'quantity',vn_durability.decimal_text(quantity,18),
    'notional',vn_durability.decimal_text(notional,36),'fee',vn_durability.decimal_text(fee,36),
    'cash_debit',vn_durability.decimal_text(debit,36),'residual_budget',vn_durability.decimal_text(budget-debit,36));
  IF value::text<>expected::text THEN RAISE EXCEPTION 'invalid_entry_evidence' USING ERRCODE='22023'; END IF;
  RETURN expected;
END $$;

CREATE FUNCTION vn_durability.exit_evidence(value jsonb, stored_entry jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE entry jsonb; cfg jsonb; kind text; reference numeric; reference_value jsonb;
        price numeric; quantity numeric; notional numeric; fee numeric; credit numeric;
        fee_rate numeric; impact numeric; expected jsonb;
BEGIN
  PERFORM vn_durability.exact_keys(value,ARRAY['version','entry','kind','reference_price','fill_price',
    'quantity','notional','fee','cash_credit','gross_pnl','net_pnl']);
  entry:=vn_durability.entry_evidence(value->'entry');
  IF stored_entry IS NULL OR entry::text<>stored_entry::text THEN
    RAISE EXCEPTION 'entry_evidence_mismatch' USING ERRCODE='22023';
  END IF;
  cfg:=entry->'config';
  quantity:=vn_durability.decimal_units(entry->'quantity',18);
  fee_rate:=vn_durability.decimal_units(cfg->'fee_bps',6);
  impact:=vn_durability.decimal_units(cfg->'half_spread_bps',6)+vn_durability.decimal_units(cfg->'slippage_bps',6);
  IF value->'reference_price'='null'::jsonb THEN
    kind:='writeoff'; price:=0; notional:=0; fee:=0; reference_value:='null'::jsonb;
  ELSE
    reference:=vn_durability.decimal_units(value->'reference_price',18);
    price:=div(reference*(1e10-impact),1e10);
    notional:=quantity*price;
    IF reference<=0 OR price<=0 OR price>1e54 OR notional<=0 OR notional>1e72 THEN
      RAISE EXCEPTION 'invalid_exit_evidence' USING ERRCODE='22023';
    END IF;
    fee:=div(notional*fee_rate+1e10-1,1e10);
    kind:='fill'; reference_value:=to_jsonb(vn_durability.decimal_text(reference,18));
  END IF;
  credit:=notional-fee;
  IF credit<0 OR credit>1e72 THEN RAISE EXCEPTION 'invalid_exit_evidence' USING ERRCODE='22023'; END IF;
  expected:=jsonb_build_object('version','usd-reference-decimal-v2','entry',entry,'kind',kind,
    'reference_price',reference_value,'fill_price',vn_durability.decimal_text(price,18),
    'quantity',entry->>'quantity','notional',vn_durability.decimal_text(notional,36),
    'fee',vn_durability.decimal_text(fee,36),'cash_credit',vn_durability.decimal_text(credit,36),
    'gross_pnl',vn_durability.decimal_text(notional-vn_durability.decimal_units(entry->'notional',36),36),
    'net_pnl',vn_durability.decimal_text(credit-vn_durability.decimal_units(entry->'cash_debit',36),36));
  IF value::text<>expected::text THEN RAISE EXCEPTION 'invalid_exit_evidence' USING ERRCODE='22023'; END IF;
  RETURN expected;
END $$;

CREATE FUNCTION vn_durability.canonical_id(value jsonb) RETURNS uuid
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE result uuid;
BEGIN
  IF value IS NULL OR jsonb_typeof(value)<>'string' THEN
    RAISE EXCEPTION 'invalid_identity' USING ERRCODE='22023';
  END IF;
  result:=(value#>>'{}')::uuid;
  IF result::text<>value#>>'{}' THEN RAISE EXCEPTION 'invalid_identity' USING ERRCODE='22023'; END IF;
  RETURN result;
END $$;

-- Match Python str.strip() rather than a locale-dependent SQL whitespace class.
CREATE FUNCTION vn_durability.valid_iteration(value jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, vn_durability, pg_temp AS $$
  SELECT coalesce(jsonb_typeof(value)='string' AND length(value#>>'{}') BETWEEN 1 AND 256 AND
    btrim(value#>>'{}',U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000')<>'',false);
$$;

CREATE FUNCTION vn_durability.record_distribution(owner_id uuid, run uuid, value jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE entity uuid; prior uuid; source uuid; source_value jsonb; index integer:=0; stage text; iteration text;
BEGIN
  PERFORM vn_durability.exact_keys(value,ARRAY['kind','id','stage','source_iteration_id','previous_distribution_id','source_ids']);
  entity:=vn_durability.canonical_id(value->'id'); stage:=value->>'stage'; iteration:=value->>'source_iteration_id';
  IF value->'previous_distribution_id'<>'null'::jsonb THEN
    prior:=vn_durability.canonical_id(value->'previous_distribution_id');
  END IF;
  IF stage IS NULL OR stage NOT IN ('bootstrap','update') OR
     NOT vn_durability.valid_iteration(value->'source_iteration_id') OR
     jsonb_typeof(value->'source_ids')<>'array' THEN
    RAISE EXCEPTION 'invalid_distribution' USING ERRCODE='22023';
  END IF;
  IF jsonb_array_length(value->'source_ids') NOT BETWEEN 2 AND 100 THEN
    RAISE EXCEPTION 'invalid_distribution' USING ERRCODE='22023';
  END IF;
  INSERT INTO vn_durability.distributions(run_id,user_id,id,stage,source_iteration_id,previous_distribution_id)
    VALUES(run,owner_id,entity,stage,iteration,prior);
  FOR source_value IN SELECT v FROM jsonb_array_elements(value->'source_ids') AS q(v) LOOP
    source:=vn_durability.canonical_id(source_value);
    INSERT INTO vn_durability.distribution_sources VALUES(run,owner_id,entity,source,index);
    index:=index+1;
  END LOOP;
END $$;

CREATE FUNCTION vn_durability.record_lineage(owner_id uuid, run uuid, child uuid, value jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE strategy text; operation text; iteration text; child_index integer; distribution uuid;
        expected_roles text[]; ids uuid[]:=ARRAY[]::uuid[]; source jsonb; source_id uuid;
        source_index integer:=1; expected_ordinal integer; source_count integer;
BEGIN
  PERFORM vn_durability.exact_keys(value,ARRAY['version','child_id','strategy','operation','source_iteration_id',
    'offspring_index','sources','distribution_id']);
  IF (value->'version')::text<>'1' OR vn_durability.canonical_id(value->'child_id')<>child OR
     jsonb_typeof(value->'strategy')<>'string' OR jsonb_typeof(value->'operation')<>'string' OR
     jsonb_typeof(value->'sources')<>'array' THEN
    RAISE EXCEPTION 'invalid_lineage' USING ERRCODE='22023';
  END IF;
  strategy:=value->>'strategy'; operation:=value->>'operation';
  IF strategy NOT IN ('genetic_algorithm','differential_evolution','particle_swarm','cma_es') THEN
    RAISE EXCEPTION 'invalid_lineage' USING ERRCODE='22023';
  END IF;
  IF value->'distribution_id'<>'null'::jsonb THEN distribution:=vn_durability.canonical_id(value->'distribution_id'); END IF;
  source_count:=jsonb_array_length(value->'sources');
  IF operation='founder' THEN
    IF value->'source_iteration_id'<>'null'::jsonb OR value->'offspring_index'<>'null'::jsonb OR
       distribution IS NOT NULL OR source_count<>0 THEN RAISE EXCEPTION 'invalid_lineage' USING ERRCODE='22023'; END IF;
    expected_roles:=ARRAY[]::text[];
  ELSE
    IF NOT vn_durability.valid_iteration(value->'source_iteration_id') OR
       jsonb_typeof(value->'offspring_index')<>'number' OR (value->'offspring_index')::text !~ '^(0|[1-9][0-9]?)$' THEN
      RAISE EXCEPTION 'invalid_lineage' USING ERRCODE='22023';
    END IF;
    iteration:=value->>'source_iteration_id'; child_index:=(value->>'offspring_index')::integer;
    IF strategy='genetic_algorithm' AND operation IN ('clone_mutation','no_active_clone','fixed_repair_clone') THEN
      expected_roles:=ARRAY['genetic_parent'];
    ELSIF strategy='genetic_algorithm' AND operation='crossover_mutation' THEN
      expected_roles:=ARRAY['genetic_parent','genetic_parent'];
    ELSIF strategy='differential_evolution' AND operation IN ('target_clone','no_active_clone','fixed_repair_clone') THEN
      expected_roles:=ARRAY['target','asset_template'];
    ELSIF strategy='differential_evolution' AND operation='de_rand1bin' THEN
      expected_roles:=ARRAY['target','base','difference_positive','difference_negative','asset_template'];
    ELSIF strategy='particle_swarm' AND operation='swarm_update' AND source_count=3 THEN
      expected_roles:=ARRAY['particle','social','asset_template'];
    ELSIF strategy='particle_swarm' AND operation IN ('swarm_update','no_active_clone') THEN
      expected_roles:=ARRAY['particle','asset_template'];
    ELSIF strategy='cma_es' AND operation='no_active_clone' THEN
      expected_roles:=ARRAY['clone_source','asset_template'];
    ELSIF strategy='cma_es' AND operation='distribution_sample' AND distribution IS NOT NULL THEN
      expected_roles:=ARRAY['asset_template'];
    ELSE RAISE EXCEPTION 'invalid_lineage' USING ERRCODE='22023';
    END IF;
    IF NOT (strategy='cma_es' AND operation='distribution_sample') AND distribution IS NOT NULL THEN
      RAISE EXCEPTION 'invalid_lineage' USING ERRCODE='22023';
    END IF;
  END IF;
  IF source_count<>cardinality(expected_roles) THEN RAISE EXCEPTION 'invalid_lineage' USING ERRCODE='22023'; END IF;
  FOR source IN SELECT v FROM jsonb_array_elements(value->'sources') AS q(v) LOOP
    PERFORM vn_durability.exact_keys(source,ARRAY['role','source_id','ordinal']);
    expected_ordinal:=CASE WHEN operation='crossover_mutation' THEN source_index-1 ELSE 0 END;
    IF source->>'role'<>expected_roles[source_index] OR
       (source->'ordinal')::text<>expected_ordinal::text THEN
      RAISE EXCEPTION 'invalid_lineage_source' USING ERRCODE='22023';
    END IF;
    source_id:=vn_durability.canonical_id(source->'source_id');
    IF source_id=child THEN RAISE EXCEPTION 'invalid_lineage_source' USING ERRCODE='22023'; END IF;
    ids:=array_append(ids,source_id); source_index:=source_index+1;
  END LOOP;
  IF (strategy='genetic_algorithm' AND operation='crossover_mutation' AND ids[1]=ids[2]) OR
     (strategy='differential_evolution' AND ids[1]<>ids[cardinality(ids)]) OR
     (strategy='differential_evolution' AND operation='de_rand1bin' AND
       (SELECT count(DISTINCT id) FROM unnest(ids[1:4]) AS q(id))<>4) OR
     (strategy='particle_swarm' AND ids[1]<>ids[cardinality(ids)]) OR
     (strategy='particle_swarm' AND cardinality(ids)=3 AND ids[1]=ids[2]) OR
     (strategy='cma_es' AND operation='no_active_clone' AND ids[1]<>ids[2]) THEN
    RAISE EXCEPTION 'invalid_lineage_source' USING ERRCODE='22023';
  END IF;
  IF distribution IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM vn_durability.distributions d JOIN vn_durability.distribution_sources s
      ON (d.run_id,d.user_id,d.id)=(s.run_id,s.user_id,s.distribution_id)
    WHERE d.run_id=run AND d.user_id=owner_id AND d.id=distribution AND d.source_iteration_id=iteration AND s.source_id=ids[1]
  ) THEN RAISE EXCEPTION 'invalid_distribution_lineage' USING ERRCODE='22023'; END IF;
  INSERT INTO vn_durability.account_lineage VALUES(run,owner_id,child,strategy,operation,iteration,child_index,distribution,value);
  FOR source IN SELECT v FROM jsonb_array_elements(value->'sources') AS q(v) LOOP
    INSERT INTO vn_durability.lineage_sources VALUES(run,owner_id,child,source->>'role',
      vn_durability.canonical_id(source->'source_id'),(source->>'ordinal')::smallint);
  END LOOP;
END $$;

CREATE FUNCTION vn_durability.create_run(
  owner_id uuid, run uuid, worker uuid, command_id uuid, configuration jsonb,
  initial_cash text, lease_seconds integer DEFAULT 30
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE amount numeric; request_body jsonb; result jsonb;
        existing vn_durability.commands%ROWTYPE; inserted uuid; contract_version integer:=1;
BEGIN
  IF owner_id IS NULL OR run IS NULL OR worker IS NULL OR command_id IS NULL OR
     lease_seconds IS NULL OR lease_seconds NOT BETWEEN 1 AND 120 OR
     configuration IS NULL OR jsonb_typeof(configuration) IS DISTINCT FROM 'object' OR
     octet_length(configuration::text) > 65536 THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE = '22023';
  END IF;
  amount := vn_durability.money(to_jsonb(initial_cash));
  IF amount <= 0 THEN RAISE EXCEPTION 'invalid_amount' USING ERRCODE = '22023'; END IF;
  IF configuration ? 'durability_contract_version' THEN
    IF (configuration->'durability_contract_version')::text NOT IN ('1','2') THEN
      RAISE EXCEPTION 'invalid_contract_version' USING ERRCODE='22023';
    END IF;
    contract_version:=(configuration->>'durability_contract_version')::integer;
  END IF;
  IF contract_version=2 THEN PERFORM vn_durability.execution_policy(configuration->'execution'); END IF;
  request_body := jsonb_build_object('kind','create','owner_id',owner_id,'run_id',run,'command_id',command_id,
                                     'worker',worker,'config',configuration,
                                     'initial_cash',initial_cash,'lease_seconds',lease_seconds);
  INSERT INTO vn_durability.runs(id,user_id,worker_id,fence,revision,lease_until,status,config,command_version,initial_cash,reserve)
  VALUES (run,owner_id,worker,1,1,clock_timestamp()+make_interval(secs=>lease_seconds),
          'starting',configuration,contract_version,amount,amount)
  ON CONFLICT (id) DO NOTHING RETURNING id INTO inserted;
  -- ON CONFLICT waits for a competing creator's commit before this row lock.
  PERFORM 1 FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE = 'P0001'; END IF;
  IF inserted IS NULL THEN
    SELECT * INTO existing FROM vn_durability.commands WHERE run_id=run AND id=command_id AND user_id=owner_id;
    IF NOT FOUND OR existing.kind <> 'create' OR existing.request::text <> request_body::text THEN
      RAISE EXCEPTION 'command_conflict' USING ERRCODE = 'P0001';
    END IF;
    -- This is readback of the original grant, NEVER a renewal. Callers must
    -- verify/heartbeat the lease before decisions; get_command is preferred.
    RETURN existing.response;
  END IF;
  IF (SELECT lease_until FROM vn_durability.runs WHERE id=run) <= clock_timestamp() THEN
    RAISE EXCEPTION 'lease_lost' USING ERRCODE='P0001';
  END IF;
  result := jsonb_build_object('run_id',run,'revision',1,'fence',1,'status','starting');
  PERFORM vn_durability.record_command(owner_id,run,command_id,1,'create',request_body,result);
  RETURN result;
END $$;

CREATE FUNCTION vn_durability.heartbeat(
  owner_id uuid, run uuid, worker uuid, token bigint, lease_seconds integer DEFAULT 30
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE state vn_durability.runs%ROWTYPE; observed timestamptz;
BEGIN
  IF owner_id IS NULL OR run IS NULL OR worker IS NULL OR token IS NULL OR token < 1 OR
     lease_seconds IS NULL OR lease_seconds NOT BETWEEN 1 AND 120 THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE = '22023';
  END IF;
  SELECT * INTO state FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
  observed := clock_timestamp(); -- MUST be evaluated after acquiring the lock.
  IF state.worker_id <> worker OR state.fence <> token OR state.lease_until <= observed OR
     state.status IN ('stopped','failed') OR state.interrupted_at IS NOT NULL THEN
    RAISE EXCEPTION 'lease_lost' USING ERRCODE='P0001';
  END IF;
  UPDATE vn_durability.runs SET lease_until=observed+make_interval(secs=>lease_seconds) WHERE id=run;
  RETURN jsonb_build_object('run_id',run,'revision',state.revision,'fence',state.fence);
END $$;

CREATE FUNCTION vn_durability.commit_command(
  owner_id uuid, run uuid, worker uuid, token bigint, expected_revision bigint,
  command_id uuid, payload jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE state vn_durability.runs%ROWTYPE; existing vn_durability.commands%ROWTYPE;
        account vn_durability.accounts%ROWTYPE; position vn_durability.positions%ROWTYPE;
        request_body jsonb; result jsonb; operation jsonb; operation_kind text;
        entity uuid; account_id uuid; parent uuid; cash numeric; quantity numeric;
        notional numeric; fee numeric; close_proceeds numeric; next_status text;
        contract_version integer; execution jsonb;
BEGIN
  IF owner_id IS NULL OR run IS NULL OR worker IS NULL OR token IS NULL OR token < 1 OR
     expected_revision IS NULL OR expected_revision < 1 OR command_id IS NULL OR
     payload IS NULL OR octet_length(payload::text) > 262144 THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.exact_keys(payload,ARRAY['version','operations']);
  IF (payload->'version')::text NOT IN ('1','2') OR
     jsonb_typeof(payload->'operations') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  contract_version:=(payload->>'version')::integer;
  IF jsonb_array_length(payload->'operations') NOT BETWEEN 1 AND (CASE WHEN contract_version=2 THEN 1024 ELSE 256 END) THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  request_body := jsonb_build_object('kind','batch','owner_id',owner_id,'run_id',run,'command_id',command_id,
                                     'worker',worker,'fence',token,
                                     'expected_revision',expected_revision,'payload',payload);
  SELECT * INTO state FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
  IF state.command_version<>contract_version THEN RAISE EXCEPTION 'contract_version_mismatch' USING ERRCODE='22023'; END IF;
  IF state.worker_id <> worker OR state.fence <> token OR state.lease_until <= clock_timestamp() OR
     state.interrupted_at IS NOT NULL THEN
    RAISE EXCEPTION 'lease_lost' USING ERRCODE='P0001';
  END IF;
  SELECT * INTO existing FROM vn_durability.commands WHERE run_id=run AND id=command_id;
  IF FOUND THEN
    IF existing.kind <> 'batch' OR existing.request::text <> request_body::text THEN
      RAISE EXCEPTION 'command_conflict' USING ERRCODE='P0001';
    END IF;
    RETURN existing.response;
  END IF;
  IF state.revision <> expected_revision THEN RAISE EXCEPTION 'revision_conflict' USING ERRCODE='P0001'; END IF;
  IF state.status IN ('stopped','failed') THEN RAISE EXCEPTION 'run_terminal' USING ERRCODE='P0001'; END IF;

  FOR operation IN SELECT value FROM jsonb_array_elements(payload->'operations') LOOP
    operation_kind := operation->>'kind';
    IF state.status IN ('stopped','failed') THEN RAISE EXCEPTION 'run_terminal' USING ERRCODE='P0001'; END IF;
    IF operation_kind = 'birth' THEN
      IF contract_version=2 THEN
        PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','cash','lineage']);
      ELSE
        PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','cash','parent_ids']);
      END IF;
      entity := CASE WHEN contract_version=2 THEN vn_durability.canonical_id(operation->'id')
                     ELSE (operation->>'id')::uuid END;
      cash := vn_durability.money(operation->'cash');
      IF entity IS NULL OR cash <= 0 OR cash > state.reserve THEN
        RAISE EXCEPTION 'invalid_birth' USING ERRCODE='22023';
      END IF;
      IF state.status IN ('paused','risk_halted') THEN
        RAISE EXCEPTION 'invalid_birth' USING ERRCODE='22023';
      END IF;
      INSERT INTO vn_durability.accounts(run_id,user_id,id,cash,initial_cash) VALUES(run,owner_id,entity,cash,cash);
      IF contract_version=2 THEN
        PERFORM vn_durability.record_lineage(owner_id,run,entity,operation->'lineage');
      ELSE
        IF jsonb_typeof(operation->'parent_ids') IS DISTINCT FROM 'array' OR
           jsonb_array_length(operation->'parent_ids')>2 THEN
          RAISE EXCEPTION 'invalid_birth' USING ERRCODE='22023';
        END IF;
        FOR parent IN SELECT value::uuid FROM jsonb_array_elements_text(operation->'parent_ids') LOOP
          INSERT INTO vn_durability.account_parents VALUES (run,owner_id,entity,parent);
        END LOOP;
      END IF;
      state.reserve := state.reserve-cash;
    ELSIF operation_kind='distribution' AND contract_version=2 THEN
      IF state.status IN ('paused','risk_halted') THEN RAISE EXCEPTION 'invalid_distribution' USING ERRCODE='22023'; END IF;
      PERFORM vn_durability.record_distribution(owner_id,run,operation);
    ELSIF operation_kind = 'open' THEN
      IF contract_version=2 THEN
        PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','account_id','asset','quantity','notional','fee','execution']);
        execution:=vn_durability.entry_evidence(operation->'execution');
        IF execution->'config' IS DISTINCT FROM state.config->'execution'->'config' OR
           operation->'quantity' IS DISTINCT FROM execution->'quantity' OR
           operation->'notional' IS DISTINCT FROM execution->'notional' OR operation->'fee' IS DISTINCT FROM execution->'fee' THEN
          RAISE EXCEPTION 'entry_evidence_mismatch' USING ERRCODE='22023';
        END IF;
      ELSE
        PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','account_id','asset','quantity','notional','fee']);
        execution:=NULL;
      END IF;
      entity := CASE WHEN contract_version=2 THEN vn_durability.canonical_id(operation->'id')
                     ELSE (operation->>'id')::uuid END;
      account_id := CASE WHEN contract_version=2 THEN vn_durability.canonical_id(operation->'account_id')
                         ELSE (operation->>'account_id')::uuid END;
      quantity := vn_durability.money(operation->'quantity');
      notional := vn_durability.money(operation->'notional'); fee := vn_durability.money(operation->'fee');
      SELECT * INTO account FROM vn_durability.accounts a WHERE a.run_id=run AND a.id=account_id AND a.user_id=owner_id;
      IF NOT FOUND OR account.retired OR entity IS NULL OR quantity <= 0 OR notional <= 0 OR
         notional+fee > account.cash OR state.status <> 'running' OR
         (contract_version=2 AND (execution->>'budget')::numeric>account.cash) OR
         jsonb_typeof(operation->'asset') IS DISTINCT FROM 'string' OR
         length(operation->>'asset') NOT BETWEEN 1 AND 64 THEN
        RAISE EXCEPTION 'invalid_open' USING ERRCODE='22023';
      END IF;
      INSERT INTO vn_durability.positions(run_id,user_id,id,account_id,asset,quantity,notional,entry_fee,entry_execution)
      VALUES(run,owner_id,entity,account_id,operation->>'asset',quantity,notional,fee,execution);
      UPDATE vn_durability.accounts a SET cash=a.cash-notional-fee WHERE a.run_id=run AND a.id=account_id;
    ELSIF operation_kind = 'close' THEN
      IF contract_version=2 THEN
        PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','proceeds','fee','execution']);
      ELSE
        PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','proceeds','fee']);
      END IF;
      entity := CASE WHEN contract_version=2 THEN vn_durability.canonical_id(operation->'id')
                     ELSE (operation->>'id')::uuid END;
      close_proceeds := vn_durability.money(operation->'proceeds'); fee := vn_durability.money(operation->'fee');
      SELECT * INTO position FROM vn_durability.positions p WHERE p.run_id=run AND p.id=entity AND p.user_id=owner_id;
      IF NOT FOUND OR position.closed OR fee > close_proceeds THEN RAISE EXCEPTION 'invalid_close' USING ERRCODE='22023'; END IF;
      IF contract_version=2 THEN
        execution:=vn_durability.exit_evidence(operation->'execution',position.entry_execution);
        IF operation->'proceeds' IS DISTINCT FROM execution->'notional' OR operation->'fee' IS DISTINCT FROM execution->'fee' THEN
          RAISE EXCEPTION 'exit_evidence_mismatch' USING ERRCODE='22023';
        END IF;
      ELSE execution:=NULL;
      END IF;
      UPDATE vn_durability.positions p SET closed=true,proceeds=close_proceeds,exit_fee=fee,exit_execution=execution
        WHERE p.run_id=run AND p.id=entity;
      UPDATE vn_durability.accounts a SET cash=a.cash+close_proceeds-fee WHERE a.run_id=run AND a.id=position.account_id;
    ELSIF operation_kind = 'retire' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id']);
      entity := CASE WHEN contract_version=2 THEN vn_durability.canonical_id(operation->'id')
                     ELSE (operation->>'id')::uuid END;
      SELECT * INTO account FROM vn_durability.accounts a WHERE a.run_id=run AND a.id=entity AND a.user_id=owner_id;
      IF NOT FOUND OR account.retired OR EXISTS (
        SELECT 1 FROM vn_durability.positions p WHERE p.run_id=run AND p.account_id=entity AND NOT p.closed
      ) THEN RAISE EXCEPTION 'invalid_retirement' USING ERRCODE='22023'; END IF;
      state.reserve := state.reserve+account.cash;
      UPDATE vn_durability.accounts a SET cash=0,retired=true WHERE a.run_id=run AND a.id=entity;
    ELSIF operation_kind = 'lifecycle' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','status']);
      next_status := operation->>'status';
      IF next_status IS NULL OR next_status NOT IN ('running','paused','risk_halted','stopped','failed') THEN
        RAISE EXCEPTION 'invalid_lifecycle' USING ERRCODE='22023';
      END IF;
      -- Recovery needs the production risk-trip/freshness contract. This
      -- rehearsal has no such evidence and must not clear the halt indirectly.
      IF state.status='risk_halted' AND next_status NOT IN ('risk_halted','stopped','failed') THEN
        RAISE EXCEPTION 'risk_recovery_unavailable' USING ERRCODE='P0001';
      END IF;
      state.status := next_status;
      IF next_status IN ('stopped','failed') THEN state.requires_reconciliation := true; END IF;
    ELSE
      RAISE EXCEPTION 'invalid_operation' USING ERRCODE='22023';
    END IF;
  END LOOP;

  -- Recheck after work too: a long blocked statement cannot persist authority
  -- it lost while executing. Row locks prevent a newer fence from intervening.
  IF state.lease_until <= clock_timestamp() THEN RAISE EXCEPTION 'lease_lost' USING ERRCODE='P0001'; END IF;
  UPDATE vn_durability.runs SET reserve=state.reserve,status=state.status,
    requires_reconciliation=state.requires_reconciliation,revision=state.revision+1 WHERE id=run;
  result := jsonb_build_object('run_id',run,'revision',state.revision+1,'fence',state.fence,
                               'status',state.status,'reserve',state.reserve::text);
  PERFORM vn_durability.record_command(owner_id,run,command_id,state.revision+1,'batch',request_body,result);
  RETURN result;
END $$;

CREATE FUNCTION vn_durability.get_command(owner_id uuid, run uuid, command_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE result jsonb;
BEGIN
  IF owner_id IS NULL OR run IS NULL OR command_id IS NULL THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM vn_durability.runs WHERE id=run AND user_id=owner_id) THEN
    RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001';
  END IF;
  SELECT jsonb_build_object('response',response,'request',request,
                            'request_hash',encode(request_hash,'hex')) INTO result
    FROM vn_durability.commands WHERE run_id=run AND user_id=owner_id AND id=command_id;
  -- NULL is specifically absent journal evidence, NOT proof of rollback: an
  -- earlier request may still be in flight. Never automatically issue a new ID.
  RETURN result;
END $$;

CREATE FUNCTION vn_durability.interrupt_expired(
  owner_id uuid, run uuid, expected_revision bigint, command_id uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE state vn_durability.runs%ROWTYPE; existing vn_durability.commands%ROWTYPE;
        request_body jsonb; result jsonb; observed timestamptz;
BEGIN
  IF owner_id IS NULL OR run IS NULL OR expected_revision IS NULL OR expected_revision < 1 OR command_id IS NULL THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  request_body := jsonb_build_object('kind','interrupt','owner_id',owner_id,'run_id',run,
                                     'command_id',command_id,'expected_revision',expected_revision);
  SELECT * INTO state FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
  SELECT * INTO existing FROM vn_durability.commands WHERE run_id=run AND id=command_id;
  IF FOUND THEN
    IF existing.kind <> 'interrupt' OR existing.request::text <> request_body::text THEN
      RAISE EXCEPTION 'command_conflict' USING ERRCODE='P0001';
    END IF;
    RETURN existing.response;
  END IF;
  IF state.revision <> expected_revision THEN RAISE EXCEPTION 'revision_conflict' USING ERRCODE='P0001'; END IF;
  observed := clock_timestamp();
  IF state.lease_until > observed OR state.status IN ('stopped','failed') OR state.interrupted_at IS NOT NULL THEN
    RAISE EXCEPTION 'not_interruptible' USING ERRCODE='P0001';
  END IF;
  UPDATE vn_durability.runs SET status='failed',requires_reconciliation=true,interrupted_at=observed,
    fence=state.fence+1,revision=state.revision+1 WHERE id=run;
  result := jsonb_build_object('run_id',run,'revision',state.revision+1,'fence',state.fence+1,
                               'status','failed','code','worker_interrupted','requires_reconciliation',true);
  PERFORM vn_durability.record_command(owner_id,run,command_id,state.revision+1,'interrupt',request_body,result);
  RETURN result;
END $$;

REVOKE ALL ON SCHEMA vn_durability FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON ALL TABLES IN SCHEMA vn_durability FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_durability FROM PUBLIC, anon, authenticated, service_role;
GRANT USAGE ON SCHEMA vn_durability TO authenticated, service_role;
GRANT SELECT ON ALL TABLES IN SCHEMA vn_durability TO authenticated;
GRANT EXECUTE ON FUNCTION vn_durability.create_run(uuid,uuid,uuid,uuid,jsonb,text,integer),
  vn_durability.heartbeat(uuid,uuid,uuid,bigint,integer),
  vn_durability.commit_command(uuid,uuid,uuid,bigint,bigint,uuid,jsonb),
  vn_durability.get_command(uuid,uuid,uuid),
  vn_durability.interrupt_expired(uuid,uuid,bigint,uuid) TO service_role;
COMMIT;
