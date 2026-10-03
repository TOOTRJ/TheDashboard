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
  command_version smallint NOT NULL CHECK (command_version IN (1,2,3)),
  engine_state jsonb,
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

-- The command journal is immutable. Version-3 candidate events are separately
-- materialized below; delivery progress never rewrites the request or receipt.
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
  UNIQUE (run_id, user_id, id, revision),
  FOREIGN KEY (run_id, user_id) REFERENCES vn_durability.runs(id, user_id)
);

CREATE TABLE vn_durability.outbox_events (
  run_id uuid NOT NULL,
  user_id uuid NOT NULL,
  command_id uuid NOT NULL,
  revision bigint NOT NULL CHECK (revision > 0),
  event_index integer NOT NULL CHECK (event_index BETWEEN 0 AND 1024),
  event jsonb NOT NULL CHECK (jsonb_typeof(event)='object' AND octet_length(event::text)<=2048),
  PRIMARY KEY (run_id, command_id, event_index),
  UNIQUE (run_id, revision, event_index),
  FOREIGN KEY (run_id, user_id, command_id, revision)
    REFERENCES vn_durability.commands(run_id, user_id, id, revision)
);

-- One fixed application publisher per run. This is delivery metadata, not a
-- worker lease, trading authority, browser cursor, or restoration checkpoint.
CREATE TABLE vn_durability.outbox_progress (
  run_id uuid PRIMARY KEY,
  user_id uuid NOT NULL,
  acknowledged_revision bigint NOT NULL DEFAULT 0,
  acknowledged_index integer NOT NULL DEFAULT -1,
  CHECK ((acknowledged_revision=0 AND acknowledged_index=-1) OR
         (acknowledged_revision>0 AND acknowledged_index BETWEEN 0 AND 1024)),
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
ALTER TABLE vn_durability.outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.outbox_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.distributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.distribution_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.account_lineage ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_durability.lineage_sources ENABLE ROW LEVEL SECURITY;
CREATE POLICY owner_read ON vn_durability.runs FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.accounts FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.positions FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.account_parents FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.commands FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.outbox_events FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.outbox_progress FOR SELECT TO authenticated USING (user_id = auth.uid());
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
  INSERT INTO vn_durability.outbox_progress(run_id,user_id)
    SELECT run,owner_id WHERE command_kind='create' AND request_body#>>'{config,durability_contract_version}'='3';
  INSERT INTO vn_durability.outbox_events(run_id,user_id,command_id,revision,event_index,event)
    SELECT run,owner_id,command_id,sequence,(ordinal-1)::integer,value
      FROM jsonb_array_elements(CASE WHEN command_kind='batch' AND request_body#>>'{payload,version}'='3'
        THEN request_body#>'{payload,transition,events}' ELSE '[]'::jsonb END) WITH ORDINALITY q(value,ordinal);
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

-- Version 3 is a bounded local exact-engine rehearsal, never a production
-- checkpoint codec or proof that submitted synthetic prices came from a vendor.
CREATE FUNCTION vn_durability.rehearsal_integer(value jsonb, minimum numeric, maximum numeric)
RETURNS numeric LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE result numeric;
BEGIN
  IF value IS NULL OR jsonb_typeof(value) IS DISTINCT FROM 'number' OR
     length(value::text)>100 OR value::text !~ '^(0|[1-9][0-9]*)$' THEN
    RAISE EXCEPTION 'invalid_rehearsal_integer' USING ERRCODE='22023';
  END IF;
  result:=(value::text)::numeric;
  IF result<minimum OR result>maximum THEN RAISE EXCEPTION 'invalid_rehearsal_integer' USING ERRCODE='22023'; END IF;
  RETURN result;
END $$;

CREATE FUNCTION vn_durability.rehearsal_hex(value jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE raw text; exponent integer;
BEGIN
  raw:=value#>>'{}';
  IF jsonb_typeof(value) IS DISTINCT FROM 'string' OR length(raw)>32 OR
     raw !~ '^-?0x[01]\.[0-9a-f]{1,13}p[+-][0-9]{1,4}$' THEN
    RAISE EXCEPTION 'invalid_float_view' USING ERRCODE='22023';
  END IF;
  exponent:=split_part(raw,'p',2)::integer;
  IF raw IN ('0x0.0p+0','-0x0.0p+0') THEN RETURN; END IF;
  IF exponent NOT BETWEEN -1022 AND 1023 OR
     split_part(raw,'p',2)<>(CASE WHEN exponent<0 THEN exponent::text ELSE '+'||exponent::text END) OR
     (raw !~ '^-?0x1\.[0-9a-f]{13}p[+-][0-9]{1,4}$' AND
      (raw !~ '^-?0x0\.[0-9a-f]{13}p-1022$' OR raw ~ '0x0\.0000000000000p')) THEN
    RAISE EXCEPTION 'invalid_float_view' USING ERRCODE='22023';
  END IF;
END $$;

CREATE FUNCTION vn_durability.rehearsal_json(value jsonb, depth integer DEFAULT 0) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE item jsonb; label text;
BEGIN
  IF value IS NULL OR depth>64 THEN RAISE EXCEPTION 'invalid_rehearsal_json' USING ERRCODE='22023'; END IF;
  CASE jsonb_typeof(value)
  WHEN 'number' THEN
    IF length(value::text)>100 OR value::text !~ '^-?(0|[1-9][0-9]*)$' THEN
      RAISE EXCEPTION 'implicit_float_view' USING ERRCODE='22023';
    END IF;
  WHEN 'string' THEN
    IF octet_length(value#>>'{}')>65536 THEN RAISE EXCEPTION 'invalid_rehearsal_json' USING ERRCODE='22023'; END IF;
  WHEN 'array' THEN
    IF jsonb_array_length(value)>4096 THEN RAISE EXCEPTION 'invalid_rehearsal_json' USING ERRCODE='22023'; END IF;
    FOR item IN SELECT v FROM jsonb_array_elements(value) q(v) LOOP
      PERFORM vn_durability.rehearsal_json(item,depth+1);
    END LOOP;
  WHEN 'object' THEN
    IF (SELECT count(*) FROM jsonb_object_keys(value))>256 THEN RAISE EXCEPTION 'invalid_rehearsal_json' USING ERRCODE='22023'; END IF;
    IF value ? 'float64' THEN
      PERFORM vn_durability.exact_keys(value,ARRAY['float64']);
      PERFORM vn_durability.rehearsal_hex(value->'float64');
    ELSE
      FOR label,item IN SELECT * FROM jsonb_each(value) LOOP
        IF length(label)>256 THEN RAISE EXCEPTION 'invalid_rehearsal_json' USING ERRCODE='22023'; END IF;
        PERFORM vn_durability.rehearsal_json(item,depth+1);
      END LOOP;
    END IF;
  WHEN 'boolean' THEN NULL;
  WHEN 'null' THEN NULL;
  ELSE RAISE EXCEPTION 'invalid_rehearsal_json' USING ERRCODE='22023';
  END CASE;
END $$;

CREATE FUNCTION vn_durability.rehearsal_integer_hex(value integer) RETURNS text
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE exponent integer:=0; shifted integer:=value;
BEGIN
  IF value NOT BETWEEN 1 AND 1000000 THEN RAISE EXCEPTION 'invalid_float_integer' USING ERRCODE='22023'; END IF;
  WHILE shifted>=2 LOOP shifted:=shifted/2; exponent:=exponent+1; END LOOP;
  RETURN '0x1.'||lpad(to_hex((value*power(2::numeric,52-exponent)-power(2::numeric,52))::bigint),13,'0')||'p+'||exponent::text;
END $$;

-- Tagged optimizer evidence schema only. No decoder, solver execution, or authorization.
CREATE FUNCTION vn_durability.optimizer_integer(value jsonb, minimum numeric, maximum numeric)
RETURNS numeric LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE result numeric;
BEGIN
  IF value IS NULL OR jsonb_typeof(value) IS DISTINCT FROM 'number' OR
     length(value::text)>79 OR value::text !~ '^(0|-?[1-9][0-9]*)$' THEN
    RAISE EXCEPTION 'invalid_optimizer_integer' USING ERRCODE='22023';
  END IF;
  result:=(value::text)::numeric;
  IF result<minimum OR result>maximum THEN RAISE EXCEPTION 'invalid_optimizer_integer' USING ERRCODE='22023'; END IF;
  RETURN result;
END $$;

CREATE FUNCTION vn_durability.optimizer_decimal(value jsonb) RETURNS numeric
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE result numeric; raw text;
BEGIN
  PERFORM vn_durability.exact_keys(value,ARRAY['type','decimal']);
  raw:=value->>'decimal';
  IF value->>'type' IS DISTINCT FROM 'integer' OR jsonb_typeof(value->'decimal') IS DISTINCT FROM 'string' OR
     length(raw)>79 OR raw !~ '^(0|-?[1-9][0-9]*)$' THEN
    RAISE EXCEPTION 'invalid_optimizer_decimal' USING ERRCODE='22023';
  END IF;
  result:=raw::numeric;
  IF abs(result)>115792089237316195423570985008687907853269984665640564039457584007913129639935 THEN
    RAISE EXCEPTION 'optimizer_integer_overflow' USING ERRCODE='22023';
  END IF;
  RETURN result;
END $$;

CREATE FUNCTION vn_durability.optimizer_bytes(value jsonb, size integer) RETURNS bytea
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE raw text:=value#>>'{}';
BEGIN
  IF jsonb_typeof(value) IS DISTINCT FROM 'string' OR size NOT BETWEEN 0 AND 65536 OR
     length(raw)<>size*2 OR raw !~ '^[0-9a-f]*$' THEN
    RAISE EXCEPTION 'invalid_optimizer_bytes' USING ERRCODE='22023';
  END IF;
  RETURN decode(raw,'hex');
END $$;

CREATE FUNCTION vn_durability.optimizer_array_shape(value jsonb) RETURNS integer
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE dtype text:=value->>'dtype'; size numeric:=1; width integer; item jsonb;
BEGIN
  IF jsonb_typeof(value->'dtype') IS DISTINCT FROM 'string' OR
     dtype !~ '^(\|[biu]1|[<>]([iu][248]|f[48]))$' OR
     jsonb_typeof(value->'shape') IS DISTINCT FROM 'array' OR jsonb_array_length(value->'shape')>4 OR
     jsonb_typeof(value->'strides') IS DISTINCT FROM 'array' OR
     jsonb_array_length(value->'strides')<>jsonb_array_length(value->'shape') OR
     jsonb_typeof(value->'writeable') IS DISTINCT FROM 'boolean' THEN
    RAISE EXCEPTION 'invalid_optimizer_array_shape' USING ERRCODE='22023';
  END IF;
  width:=right(dtype,1)::integer;
  FOR item IN SELECT v FROM jsonb_array_elements(value->'shape') q(v) LOOP
    size:=size*vn_durability.optimizer_integer(item,0,4096);
    IF size>4096 THEN RAISE EXCEPTION 'optimizer_array_capacity' USING ERRCODE='22023'; END IF;
  END LOOP;
  FOR item IN SELECT v FROM jsonb_array_elements(value->'strides') q(v) LOOP
    PERFORM vn_durability.optimizer_integer(item,-65536,65536);
  END LOOP;
  IF size*width>65536 THEN RAISE EXCEPTION 'optimizer_array_capacity' USING ERRCODE='22023'; END IF;
  RETURN size::integer;
END $$;

CREATE FUNCTION vn_durability.optimizer_array(value jsonb) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE size integer; width integer; bytes bytea; base integer; high_byte integer; next_byte integer; i integer;
        dtype text:=value->>'dtype';
BEGIN
  size:=vn_durability.optimizer_array_shape(value); width:=right(dtype,1)::integer;
  IF value->>'order' IS DISTINCT FROM 'C' THEN RAISE EXCEPTION 'invalid_optimizer_array_order' USING ERRCODE='22023'; END IF;
  bytes:=vn_durability.optimizer_bytes(value->'hex',size*width);
  IF substring(dtype,2,1)='f' AND size>0 THEN
    FOR i IN 0..size-1 LOOP
      base:=i*width;
      high_byte:=get_byte(bytes,base+CASE WHEN left(dtype,1)='<' THEN width-1 ELSE 0 END);
      next_byte:=get_byte(bytes,base+CASE WHEN left(dtype,1)='<' THEN width-2 ELSE 1 END);
      IF (high_byte & 127)=127 AND
         ((width=4 AND (next_byte & 128)=128) OR (width=8 AND (next_byte & 240)=240)) THEN
        RAISE EXCEPTION 'nonfinite_optimizer_array' USING ERRCODE='22023';
      END IF;
    END LOOP;
  END IF;
END $$;

CREATE FUNCTION vn_durability.optimizer_history(value jsonb, fields jsonb) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE size integer; term integer; generation numeric; slot integer; expected boolean; pair jsonb;
        dimensions numeric; population numeric;
BEGIN
  PERFORM vn_durability.exact_keys(value,ARRAY['type','dtype','shape','strides','writeable','generation','written_pairs','slots_hex']);
  IF value->>'type' IS DISTINCT FROM 'cmaes-fitness-history-v1' OR value->>'dtype' NOT IN ('<f8','>f8') THEN
    RAISE EXCEPTION 'invalid_optimizer_history' USING ERRCODE='22023';
  END IF;
  size:=vn_durability.optimizer_array_shape(value); term:=size/2;
  generation:=vn_durability.optimizer_integer(value->'generation',0,9223372036854775807);
  IF size<=0 OR mod(size,2)<>0 OR value->'shape' IS DISTINCT FROM jsonb_build_array(size) OR
     jsonb_typeof(value->'written_pairs') IS DISTINCT FROM 'array' OR jsonb_array_length(value->'written_pairs')<>term OR
     jsonb_typeof(value->'slots_hex') IS DISTINCT FROM 'array' OR jsonb_array_length(value->'slots_hex')<>term THEN
    RAISE EXCEPTION 'invalid_optimizer_history' USING ERRCODE='22023';
  END IF;
  dimensions:=vn_durability.optimizer_decimal(fields->'_n_dim');
  population:=vn_durability.optimizer_decimal(fields->'_popsize');
  IF generation<>vn_durability.optimizer_decimal(fields->'_g') OR
     term<>vn_durability.optimizer_decimal(fields->'_funhist_term') OR
     dimensions NOT BETWEEN 1 AND 100 OR population NOT BETWEEN 2 AND 100 OR
     term<>10+div(30*dimensions+population-1,population) THEN
    RAISE EXCEPTION 'optimizer_history_counters_mismatch' USING ERRCODE='22023';
  END IF;
  FOR slot IN 0..term-1 LOOP
    expected:=generation>=term OR (slot>=1 AND slot<=generation);
    IF value->'written_pairs'->slot IS DISTINCT FROM to_jsonb(expected) THEN
      RAISE EXCEPTION 'optimizer_history_mask_mismatch' USING ERRCODE='22023';
    END IF;
    pair:=value->'slots_hex'->slot;
    IF expected THEN
      IF jsonb_typeof(pair) IS DISTINCT FROM 'array' OR jsonb_array_length(pair)<>2 THEN
        RAISE EXCEPTION 'invalid_optimizer_history_pair' USING ERRCODE='22023';
      END IF;
      PERFORM vn_durability.rehearsal_hex(pair->0); PERFORM vn_durability.rehearsal_hex(pair->1);
    ELSIF pair IS DISTINCT FROM 'null'::jsonb THEN
      RAISE EXCEPTION 'optimizer_history_unwritten_memory' USING ERRCODE='22023';
    END IF;
  END LOOP;
END $$;

CREATE FUNCTION vn_durability.optimizer_class_fields(name text) RETURNS text[]
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
BEGIN
  CASE name
    WHEN 'GeneticAlgorithmStrategy' THEN RETURN ARRAY['_cohort','_mutation_event','_rng','_search_epoch','_search_streams','mutation_rate','mutation_strength'];
    WHEN 'DifferentialEvolutionStrategy' THEN RETURN ARRAY['CR','F','_cohort','_mutation_event','_pairs','_phase','_rng','_search_epoch','_search_streams','min_pop'];
    WHEN 'ParticleSwarmStrategy' THEN RETURN ARRAY['_codec','_cohort','_global_best','_mutation_event','_personal_best','_rng','_search_epoch','_search_streams','_velocities','c2','w'];
    WHEN 'CMAEvolutionStrategy' THEN RETURN ARRAY['_awaiting_bind','_bound_genomes','_bound_ids','_codec','_first_generation','_gene_names','_mutation_event','_optimizer','_pending_genomes','_pending_vectors','_rng','_search_epoch','_search_streams'];
    WHEN 'SearchRandomStreams' THEN RETURN ARRAY['algorithm','seed'];
    WHEN 'SelectionCohort' THEN RETURN ARRAY['_bootstrap','_pending','_previous_context','_previous_ids','_signatures','bound_ids','population_size'];
    WHEN 'ParameterCodec' THEN RETURN ARRAY['_assets','_config','domains','names'];
    WHEN 'ColonyConfig' THEN RETURN ARRAY['available_assets','enabled_genes','gene_overrides','max_lifespan_ticks','mutation_rate','reproduction_interval','strategy_profile'];
    WHEN 'GeneOverride' THEN RETURN ARRAY['default','fixed','max','min'];
    WHEN 'GeneDomain' THEN RETURN ARRAY['default','integer','maximum','minimum'];
    WHEN 'Genome' THEN RETURN ARRAY['assets','benchmark_target_pct','death_drawdown_pct','ema_fast','ema_slow','generation','max_open_positions','num_assets','parent_ids','position_size_pct','reproduce_target_dollars','rsi_overbought','rsi_oversold','rsi_period','stop_loss_pct','take_profit_pct','timeframe_minutes','volume_threshold'];
    WHEN 'EvaluatedCandidate' THEN RETURN ARRAY['_genome','cohort_complete','evaluation_id','fitness','iteration_id','num_trades','probe_id','reason','roi','status','terminated_at','window_ends_at','window_started_at'];
    WHEN 'EvaluationCohort' THEN RETURN ARRAY['_evaluation_ids','_evaluations','_genomes','abort_reason','completed_at','ends_at','horizon_seconds','iteration_id','member_ids','phase','started_at'];
    WHEN 'cmaes.CMA@0.13.1' THEN RETURN ARRAY['_B','_C','_D','_ESigma','_Emean','_VSigma','_Vmean','_alpha','_beta_Sigma','_beta_mean','_bounds','_c1','_c_sigma','_cc','_chi_n','_cm','_cmu','_d_sigma','_eta_Sigma','_eta_mean','_funhist_term','_funhist_values','_g','_gamma','_lr_adapt','_mean','_mu','_mu_eff','_n_dim','_n_max_resampling','_p_sigma','_pc','_popsize','_rng','_sigma','_tolconditioncov','_tolfun','_tolx','_tolxup','_weights'];
    ELSE RAISE EXCEPTION 'unknown_optimizer_class' USING ERRCODE='22023';
  END CASE;
END $$;

CREATE FUNCTION vn_durability.optimizer_role(value jsonb, context jsonb, required text, nullable boolean DEFAULT false)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE descriptor jsonb:=value; identity integer;
BEGIN
  IF nullable AND value='null'::jsonb THEN RETURN; END IF;
  IF value ? 'ref' THEN
    identity:=vn_durability.optimizer_integer(value->'ref',0,19999)::integer;
    descriptor:=context->'nodes'->identity;
  END IF;
  IF descriptor IS NULL OR jsonb_typeof(descriptor) IS DISTINCT FROM 'object' OR
     (CASE WHEN descriptor->>'type'='object' THEN descriptor->>'class' ELSE descriptor->>'type' END) IS DISTINCT FROM required THEN
    RAISE EXCEPTION 'optimizer_field_role_mismatch' USING ERRCODE='22023';
  END IF;
END $$;

CREATE FUNCTION vn_durability.optimizer_node(value jsonb, context jsonb, depth integer DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE visits integer:=(context->>'visits')::integer+1; tag text; node integer; item jsonb; pair jsonb;
        fields jsonb; required text[]; label text; name text; seen text[]:=ARRAY[]::text[]; identity integer;
BEGIN
  IF value IS NULL OR visits>20000 OR depth>64 THEN RAISE EXCEPTION 'optimizer_graph_capacity' USING ERRCODE='22023'; END IF;
  context:=jsonb_set(context,'{visits}',to_jsonb(visits));
  IF jsonb_typeof(value) IN ('null','boolean') THEN RETURN context; END IF;
  IF jsonb_typeof(value)='string' THEN
    IF octet_length(value#>>'{}')>4096 THEN RAISE EXCEPTION 'optimizer_string_capacity' USING ERRCODE='22023'; END IF;
    RETURN context;
  END IF;
  IF jsonb_typeof(value) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'untagged_optimizer_value' USING ERRCODE='22023'; END IF;
  IF value ? 'ref' THEN
    PERFORM vn_durability.exact_keys(value,ARRAY['ref']);
    identity:=vn_durability.optimizer_integer(value->'ref',0,19999)::integer;
    IF identity>=jsonb_array_length(context->'nodes') OR (context->'active') @> jsonb_build_array(identity) THEN
      RAISE EXCEPTION 'optimizer_forward_or_cyclic_reference' USING ERRCODE='22023';
    END IF;
    RETURN context;
  END IF;
  tag:=value->>'type';
  IF tag='integer' THEN
    PERFORM vn_durability.optimizer_decimal(value); RETURN context;
  ELSIF tag IN ('float','numpy.float64') THEN
    PERFORM vn_durability.exact_keys(value,ARRAY['type','hex']);
    PERFORM vn_durability.rehearsal_hex(value->'hex'); RETURN context;
  END IF;
  node:=vn_durability.optimizer_integer(value->'node',0,19999)::integer;
  IF node<>jsonb_array_length(context->'nodes') THEN RAISE EXCEPTION 'optimizer_node_order' USING ERRCODE='22023'; END IF;
  context:=jsonb_set(context,'{nodes}',(context->'nodes')||jsonb_build_array(jsonb_build_object('type',tag,'class',value->>'class')));
  context:=jsonb_set(context,'{active}',(context->'active')||jsonb_build_array(node));
  IF tag IN ('list','tuple') THEN
    PERFORM vn_durability.exact_keys(value,ARRAY['node','type','items']);
    IF jsonb_typeof(value->'items') IS DISTINCT FROM 'array' OR jsonb_array_length(value->'items')>4096 THEN
      RAISE EXCEPTION 'optimizer_sequence_capacity' USING ERRCODE='22023';
    END IF;
    FOR item IN SELECT v FROM jsonb_array_elements(value->'items') q(v) LOOP
      context:=vn_durability.optimizer_node(item,context,depth+1);
    END LOOP;
  ELSIF tag='map' THEN
    PERFORM vn_durability.exact_keys(value,ARRAY['node','type','entries']);
    IF jsonb_typeof(value->'entries') IS DISTINCT FROM 'array' OR jsonb_array_length(value->'entries')>4096 THEN
      RAISE EXCEPTION 'optimizer_map_capacity' USING ERRCODE='22023';
    END IF;
    FOR pair IN SELECT v FROM jsonb_array_elements(value->'entries') q(v) LOOP
      IF jsonb_typeof(pair) IS DISTINCT FROM 'array' OR jsonb_array_length(pair)<>2 OR
         jsonb_typeof(pair->0) IS DISTINCT FROM 'string' OR (pair->>0)=ANY(seen) THEN
        RAISE EXCEPTION 'invalid_optimizer_map_entry' USING ERRCODE='22023';
      END IF;
      seen:=array_append(seen,pair->>0);
      context:=vn_durability.optimizer_node(pair->0,context,depth+1);
      context:=vn_durability.optimizer_node(pair->1,context,depth+1);
    END LOOP;
  ELSIF tag='object' THEN
    PERFORM vn_durability.exact_keys(value,ARRAY['node','type','class','fields']);
    IF jsonb_typeof(value->'class') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'invalid_optimizer_class' USING ERRCODE='22023'; END IF;
    name:=value->>'class'; fields:=value->'fields'; required:=vn_durability.optimizer_class_fields(name);
    PERFORM vn_durability.exact_keys(fields,required);
    FOREACH label IN ARRAY required LOOP
      IF name='cmaes.CMA@0.13.1' AND label='_funhist_values' THEN
        PERFORM vn_durability.optimizer_history(fields->label,fields);
      ELSE
        context:=vn_durability.optimizer_node(fields->label,context,depth+1);
      END IF;
    END LOOP;
    IF name IN ('GeneticAlgorithmStrategy','DifferentialEvolutionStrategy','ParticleSwarmStrategy','CMAEvolutionStrategy') THEN
      PERFORM vn_durability.optimizer_role(fields->'_rng',context,'python.Random');
      PERFORM vn_durability.optimizer_role(fields->'_search_streams',context,'SearchRandomStreams');
      PERFORM vn_durability.optimizer_role(fields->'_search_epoch',context,'integer');
      PERFORM vn_durability.optimizer_role(fields->'_mutation_event',context,'integer');
    END IF;
    IF name IN ('GeneticAlgorithmStrategy','DifferentialEvolutionStrategy','ParticleSwarmStrategy') THEN
      PERFORM vn_durability.optimizer_role(fields->'_cohort',context,'SelectionCohort');
    END IF;
    IF name IN ('ParticleSwarmStrategy','CMAEvolutionStrategy') THEN
      PERFORM vn_durability.optimizer_role(fields->'_codec',context,'ParameterCodec',true);
    END IF;
    IF name='CMAEvolutionStrategy' THEN
      PERFORM vn_durability.optimizer_role(fields->'_optimizer',context,'cmaes.CMA@0.13.1',true);
    ELSIF name='cmaes.CMA@0.13.1' THEN
      PERFORM vn_durability.optimizer_role(fields->'_rng',context,'numpy.RandomState');
    ELSIF name='ParameterCodec' THEN
      PERFORM vn_durability.optimizer_role(fields->'_config',context,'ColonyConfig');
    ELSIF name='EvaluatedCandidate' THEN
      PERFORM vn_durability.optimizer_role(fields->'_genome',context,'Genome');
    END IF;
  ELSIF tag='ndarray' THEN
    PERFORM vn_durability.exact_keys(value,ARRAY['node','type','dtype','shape','strides','writeable','order','hex']);
    PERFORM vn_durability.optimizer_array(value);
  ELSIF tag='python.Random' THEN
    PERFORM vn_durability.exact_keys(value,ARRAY['node','type','algorithm','state_version','words','index','gaussian_hex']);
    IF value->>'algorithm' IS DISTINCT FROM 'MT19937' OR
       vn_durability.optimizer_integer(value->'state_version',3,3)<>3 OR
       jsonb_typeof(value->'words') IS DISTINCT FROM 'array' OR jsonb_array_length(value->'words')<>624 THEN
      RAISE EXCEPTION 'invalid_python_random_evidence' USING ERRCODE='22023';
    END IF;
    FOR item IN SELECT v FROM jsonb_array_elements(value->'words') q(v) LOOP
      PERFORM vn_durability.optimizer_integer(item,0,4294967295);
    END LOOP;
    PERFORM vn_durability.optimizer_integer(value->'index',0,624);
    IF value->'gaussian_hex'<>'null'::jsonb THEN PERFORM vn_durability.rehearsal_hex(value->'gaussian_hex'); END IF;
  ELSIF tag='numpy.RandomState' THEN
    PERFORM vn_durability.exact_keys(value,ARRAY['node','type','algorithm','key_dtype','keys_hex','index','has_gaussian','gaussian_hex']);
    IF value->>'algorithm' IS DISTINCT FROM 'MT19937' OR
       jsonb_typeof(value->'key_dtype') IS DISTINCT FROM 'string' OR value->>'key_dtype' NOT IN ('<u4','>u4') THEN
      RAISE EXCEPTION 'invalid_numpy_random_evidence' USING ERRCODE='22023';
    END IF;
    PERFORM vn_durability.optimizer_bytes(value->'keys_hex',2496);
    PERFORM vn_durability.optimizer_integer(value->'index',0,624);
    PERFORM vn_durability.optimizer_integer(value->'has_gaussian',0,1);
    PERFORM vn_durability.rehearsal_hex(value->'gaussian_hex');
  ELSE
    RAISE EXCEPTION 'unknown_optimizer_tag' USING ERRCODE='22023';
  END IF;
  context:=jsonb_set(context,'{active}',(context->'active')-(jsonb_array_length(context->'active')-1));
  RETURN context;
END $$;

CREATE FUNCTION vn_durability.optimizer_evidence(value jsonb, expected_strategy text) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE context jsonb:='{"nodes":[],"active":[],"visits":0}'::jsonb; item jsonb; expected text;
BEGIN
  IF octet_length(value::text)>196608 THEN RAISE EXCEPTION 'optimizer_evidence_capacity' USING ERRCODE='22023'; END IF;
  PERFORM vn_durability.exact_keys(value,ARRAY['version','software','strategy','cohort']);
  IF value->>'version' IS DISTINCT FROM 'optimizer-evidence-v1' THEN RAISE EXCEPTION 'invalid_optimizer_version' USING ERRCODE='22023'; END IF;
  PERFORM vn_durability.exact_keys(value->'software',ARRAY['python','numpy','cmaes']);
  FOR item IN SELECT v FROM jsonb_each(value->'software') q(k,v) LOOP
    IF jsonb_typeof(item) IS DISTINCT FROM 'string' OR length(item#>>'{}')>32 OR
       item#>>'{}' !~ '^[0-9]+\.[0-9]+\.[0-9]+$' THEN
      RAISE EXCEPTION 'invalid_optimizer_software_version' USING ERRCODE='22023';
    END IF;
  END LOOP;
  IF value->'software'->>'cmaes' IS DISTINCT FROM '0.13.1' THEN RAISE EXCEPTION 'unsupported_cma_version' USING ERRCODE='22023'; END IF;
  expected:=CASE expected_strategy WHEN 'genetic_algorithm' THEN 'GeneticAlgorithmStrategy'
    WHEN 'differential_evolution' THEN 'DifferentialEvolutionStrategy' WHEN 'particle_swarm' THEN 'ParticleSwarmStrategy'
    WHEN 'cma_es' THEN 'CMAEvolutionStrategy' ELSE NULL END;
  IF expected IS NULL OR value->'strategy'->>'type' IS DISTINCT FROM 'object' OR
     value->'strategy'->>'class' IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'optimizer_strategy_mismatch' USING ERRCODE='22023';
  END IF;
  context:=vn_durability.optimizer_node(value->'strategy',context);
  context:=vn_durability.optimizer_node(value->'cohort',context);
  PERFORM vn_durability.optimizer_role(value->'cohort',context,'EvaluationCohort');
END $$;


CREATE FUNCTION vn_durability.rehearsal_config(configuration jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE cfg jsonb; initial_amount numeric; seed_amount numeric;
BEGIN
  PERFORM vn_durability.exact_keys(configuration,ARRAY['durability_contract_version','execution','rehearsal']);
  cfg:=configuration->'rehearsal';
  PERFORM vn_durability.exact_keys(cfg,ARRAY['profile','strategy','asset','initial_cash','seed_capital',
    'search_seed','execution','population','horizon_seconds','candle_seconds','max_generations','max_positions','code_version','source']);
  IF configuration->'durability_contract_version'<>'3'::jsonb OR
     cfg->>'profile' IS DISTINCT FROM 'ema-baseline-exact-rehearsal-v1' OR
     cfg->>'code_version' IS DISTINCT FROM 'bounded-exact-rehearsal-v1' OR
     cfg->>'source' IS DISTINCT FROM 'synthetic-exact-fixture-v1' OR
     jsonb_typeof(cfg->'strategy') IS DISTINCT FROM 'string' OR
     cfg->>'strategy' NOT IN ('genetic_algorithm','differential_evolution','particle_swarm','cma_es') OR
     jsonb_typeof(cfg->'asset') IS DISTINCT FROM 'string' OR length(cfg->>'asset') NOT BETWEEN 1 AND 64 OR
     cfg->'population'<>'8'::jsonb OR cfg->'horizon_seconds'<>'3600'::jsonb OR
     cfg->'candle_seconds'<>'900'::jsonb OR cfg->'max_generations'<>'3'::jsonb OR cfg->'max_positions'<>'64'::jsonb OR
     cfg->'execution' IS DISTINCT FROM configuration->'execution' OR
     jsonb_typeof(cfg->'search_seed') IS DISTINCT FROM 'string' OR
     length(cfg->>'search_seed')>20 OR cfg->>'search_seed' !~ '^(0|[1-9][0-9]*)$' THEN
    RAISE EXCEPTION 'invalid_rehearsal_config' USING ERRCODE='22023';
  END IF;
  IF (cfg->>'search_seed')::numeric>18446744073709551615 THEN RAISE EXCEPTION 'invalid_rehearsal_config' USING ERRCODE='22023'; END IF;
  initial_amount:=vn_durability.decimal_units(cfg->'initial_cash',36);
  seed_amount:=vn_durability.decimal_units(cfg->'seed_capital',36);
  IF seed_amount<1e36 OR initial_amount<8*seed_amount OR
     cfg->>'initial_cash'<>vn_durability.decimal_text(initial_amount,36) OR
     cfg->>'seed_capital'<>vn_durability.decimal_text(seed_amount,36) THEN
    RAISE EXCEPTION 'invalid_rehearsal_config' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.execution_policy(cfg->'execution');
END $$;

CREATE FUNCTION vn_durability.rehearsal_view_time(value jsonb) RETURNS numeric
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE raw text; digits text; units numeric:=0; exponent integer; hex_digit text; divisor numeric;
BEGIN
  PERFORM vn_durability.exact_keys(value,ARRAY['float64']);
  PERFORM vn_durability.rehearsal_hex(value->'float64');
  raw:=value->>'float64';
  IF raw IN ('0x0.0p+0','-0x0.0p+0') THEN RETURN 0; END IF;
  IF left(raw,1)='-' THEN RAISE EXCEPTION 'invalid_evaluation_time' USING ERRCODE='22023'; END IF;
  digits:=replace(substring(split_part(raw,'p',1),3),'.','');
  exponent:=split_part(raw,'p',2)::integer-4*(length(split_part(split_part(raw,'p',1),'.',2)));
  FOR i IN 1..length(digits) LOOP
    hex_digit:=substring(digits,i,1);
    units:=units*16+strpos('0123456789abcdef',hex_digit)-1;
  END LOOP;
  IF exponent>=0 THEN units:=units*power(2::numeric,exponent);
  ELSE
    divisor:=power(2::numeric,-exponent);
    IF mod(units,divisor)<>0 THEN RAISE EXCEPTION 'invalid_evaluation_time' USING ERRCODE='22023'; END IF;
    units:=div(units,divisor);
  END IF;
  IF units>253402300799 THEN RAISE EXCEPTION 'invalid_evaluation_time' USING ERRCODE='22023'; END IF;
  RETURN units;
END $$;

CREATE FUNCTION vn_durability.rehearsal_evaluation(state vn_durability.runs, value jsonb, generation integer,
  expected_members jsonb DEFAULT NULL, observed numeric DEFAULT NULL) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE cohort jsonb; result jsonb; source uuid; sources uuid[]:=ARRAY[]::uuid[]; ordinal integer:=0;
        iteration text; started numeric; deadline numeric; completed numeric;
BEGIN
  PERFORM vn_durability.exact_keys(value,ARRAY['cohort','selection']);
  IF jsonb_typeof(value->'selection') IS DISTINCT FROM 'object' OR value->'selection'='{}'::jsonb THEN
    RAISE EXCEPTION 'invalid_evaluation_selection' USING ERRCODE='22023';
  END IF;
  cohort:=value->'cohort'; iteration:=state.id::text||':'||(generation-1)::text;
  PERFORM vn_durability.exact_keys(cohort,ARRAY['policy','iteration_id','phase','member_ids','member_count',
    'completed_count','horizon_seconds','started_at','ends_at','completed_at','abort_reason','evaluations']);
  IF cohort->'policy' IS DISTINCT FROM '{"version":"common-market-window-v1","horizon_unit":"market_minutes",
       "warmup":"all_candidates_ready","early_terminal":"freeze_cash_and_score_until_common_deadline",
       "interruptions":"abort_without_tell","deadline_mark":"first_valid_observation_at_or_after_deadline"}'::jsonb OR
     cohort->>'iteration_id' IS DISTINCT FROM iteration OR cohort->>'phase' IS DISTINCT FROM 'completed' OR
     cohort->'member_count'<>'8'::jsonb OR cohort->'completed_count'<>'8'::jsonb OR cohort->'abort_reason'<>'null'::jsonb OR
     jsonb_typeof(cohort->'member_ids') IS DISTINCT FROM 'array' OR jsonb_array_length(cohort->'member_ids')<>8 OR
     jsonb_typeof(cohort->'evaluations') IS DISTINCT FROM 'array' OR jsonb_array_length(cohort->'evaluations')<>8 OR
     (expected_members IS NOT NULL AND cohort->'member_ids' IS DISTINCT FROM expected_members) OR
     vn_durability.rehearsal_view_time(cohort->'horizon_seconds')<>3600 THEN
    RAISE EXCEPTION 'invalid_completed_evaluation' USING ERRCODE='22023';
  END IF;
  started:=vn_durability.rehearsal_view_time(cohort->'started_at');
  deadline:=vn_durability.rehearsal_view_time(cohort->'ends_at');
  completed:=vn_durability.rehearsal_view_time(cohort->'completed_at');
  IF deadline<>started+3600 OR completed<deadline OR (observed IS NOT NULL AND completed<>observed) THEN
    RAISE EXCEPTION 'invalid_evaluation_window' USING ERRCODE='22023';
  END IF;
  FOR result IN SELECT v FROM jsonb_array_elements(cohort->'evaluations') q(v) LOOP
    PERFORM vn_durability.exact_keys(result,ARRAY['probe_id','evaluation_id','iteration_id','fitness','roi','num_trades',
      'reason','status','cohort_complete','window_started_at','window_ends_at','terminated_at']);
    source:=vn_durability.canonical_id(result->'probe_id');
    IF source=ANY(sources) OR cohort->'member_ids'->ordinal IS DISTINCT FROM result->'probe_id' OR
       result->>'evaluation_id' IS DISTINCT FROM iteration||':'||ordinal::text OR
       result->>'iteration_id' IS DISTINCT FROM iteration OR result->>'status' IS DISTINCT FROM 'completed' OR
       result->'cohort_complete'<>'true'::jsonb OR result->>'reason' IS DISTINCT FROM 'window_complete' OR
       result->'window_started_at' IS DISTINCT FROM cohort->'started_at' OR
       result->'window_ends_at' IS DISTINCT FROM cohort->'ends_at' OR result->'terminated_at' IS DISTINCT FROM cohort->'completed_at' OR
       NOT EXISTS(SELECT 1 FROM vn_durability.accounts WHERE run_id=state.id AND user_id=state.user_id AND id=source AND retired) OR
       vn_durability.rehearsal_integer(result->'num_trades',0,64)<>(SELECT count(*) FROM vn_durability.positions
         WHERE run_id=state.id AND account_id=source AND closed) THEN
      RAISE EXCEPTION 'invalid_completed_candidate' USING ERRCODE='22023';
    END IF;
    PERFORM vn_durability.exact_keys(result->'fitness',ARRAY['float64']);
    PERFORM vn_durability.exact_keys(result->'roi',ARRAY['float64']);
    PERFORM vn_durability.rehearsal_hex(result->'fitness'->'float64');
    PERFORM vn_durability.rehearsal_hex(result->'roi'->'float64');
    sources:=array_append(sources,source); ordinal:=ordinal+1;
  END LOOP;
END $$;

CREATE FUNCTION vn_durability.validate_transition_after(state vn_durability.runs, payload jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE candidate jsonb:=payload->'transition'->'after'; engine jsonb; item jsonb; member jsonb;
        ids uuid[]:=ARRAY[]::uuid[]; entity uuid; account vn_durability.accounts%ROWTYPE;
        position vn_durability.positions%ROWTYPE; amount numeric; prior jsonb; label text; value jsonb;
        members uuid[]:=ARRAY[]::uuid[]; used uuid[]:=ARRAY[]::uuid[];
        equity numeric; peak numeric; draw_num numeric; draw_den numeric; reference numeric;
        genome_parents uuid[]; parent_entity uuid;
BEGIN
  PERFORM vn_durability.exact_keys(candidate,ARRAY['version','owner_id','run_id','revision','status','reserve','accounts','positions','engine']);
  IF candidate->'version'<>'1'::jsonb OR vn_durability.canonical_id(candidate->'owner_id')<>state.user_id OR
     vn_durability.canonical_id(candidate->'run_id')<>state.id OR
     vn_durability.rehearsal_integer(candidate->'revision',1,9223372036854775807)<>state.revision+1 OR
     candidate->>'status' IS DISTINCT FROM state.status OR candidate->>'status'<>'running' OR
     jsonb_typeof(candidate->'reserve') IS DISTINCT FROM 'string' OR
     candidate->>'reserve' IS DISTINCT FROM vn_durability.decimal_text(state.reserve*1e36,36) OR
     jsonb_typeof(candidate->'accounts') IS DISTINCT FROM 'array' OR
     jsonb_typeof(candidate->'positions') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid_transition_projection' USING ERRCODE='22023';
  END IF;
  IF jsonb_array_length(candidate->'accounts') NOT BETWEEN 8 AND 32 OR
     jsonb_array_length(candidate->'accounts')<>(SELECT count(*) FROM vn_durability.accounts WHERE run_id=state.id) OR
     jsonb_array_length(candidate->'positions')>64 OR
     jsonb_array_length(candidate->'positions')<>(SELECT count(*) FROM vn_durability.positions WHERE run_id=state.id) THEN
    RAISE EXCEPTION 'incomplete_transition_projection' USING ERRCODE='22023';
  END IF;
  IF candidate->'accounts' IS DISTINCT FROM (SELECT jsonb_agg(v ORDER BY v->>'id') FROM jsonb_array_elements(candidate->'accounts') q(v)) OR
     candidate->'positions' IS DISTINCT FROM (SELECT coalesce(jsonb_agg(v ORDER BY v->>'id'),'[]'::jsonb) FROM jsonb_array_elements(candidate->'positions') q(v)) THEN
    RAISE EXCEPTION 'noncanonical_transition_order' USING ERRCODE='22023';
  END IF;
  FOR item IN SELECT v FROM jsonb_array_elements(candidate->'accounts') q(v) LOOP
    PERFORM vn_durability.exact_keys(item,ARRAY['id','cash','initial_cash','retired']);
    entity:=vn_durability.canonical_id(item->'id');
    IF entity=ANY(ids) THEN RAISE EXCEPTION 'duplicate_transition_entity' USING ERRCODE='22023'; END IF;
    ids:=array_append(ids,entity);
    SELECT * INTO account FROM vn_durability.accounts WHERE run_id=state.id AND user_id=state.user_id AND id=entity;
    IF NOT FOUND OR jsonb_typeof(item->'cash') IS DISTINCT FROM 'string' OR
       jsonb_typeof(item->'initial_cash') IS DISTINCT FROM 'string' OR
       item->>'cash' IS DISTINCT FROM vn_durability.decimal_text(account.cash*1e36,36) OR
       item->>'initial_cash' IS DISTINCT FROM vn_durability.decimal_text(account.initial_cash*1e36,36) OR
       item->'retired' IS DISTINCT FROM to_jsonb(account.retired) THEN
      RAISE EXCEPTION 'account_projection_mismatch' USING ERRCODE='22023';
    END IF;
  END LOOP;
  FOR item IN SELECT v FROM jsonb_array_elements(candidate->'positions') q(v) LOOP
    PERFORM vn_durability.exact_keys(item,ARRAY['id','account_id','asset','entry','exit','closed']);
    entity:=vn_durability.canonical_id(item->'id');
    IF entity=ANY(ids) THEN RAISE EXCEPTION 'duplicate_transition_entity' USING ERRCODE='22023'; END IF;
    ids:=array_append(ids,entity);
    SELECT * INTO position FROM vn_durability.positions WHERE run_id=state.id AND user_id=state.user_id AND id=entity;
    IF NOT FOUND OR vn_durability.canonical_id(item->'account_id')<>position.account_id OR
       item->'asset' IS DISTINCT FROM to_jsonb(position.asset) OR
       item->'entry' IS DISTINCT FROM position.entry_execution OR
       item->'exit' IS DISTINCT FROM coalesce(position.exit_execution,'null'::jsonb) OR
       item->'closed' IS DISTINCT FROM to_jsonb(position.closed) THEN
      RAISE EXCEPTION 'position_projection_mismatch' USING ERRCODE='22023';
    END IF;
  END LOOP;
  engine:=candidate->'engine';
  PERFORM vn_durability.exact_keys(engine,ARRAY['config','generation','last_quote','decision_timestamp','members',
    'ema','distribution_id','used_ids','last_evaluation','optimizer']);
  IF engine->'config' IS DISTINCT FROM state.config->'rehearsal' OR
     jsonb_typeof(engine->'members') IS DISTINCT FROM 'array' OR jsonb_array_length(engine->'members')<>8 OR
     jsonb_typeof(engine->'used_ids') IS DISTINCT FROM 'array' OR jsonb_array_length(engine->'used_ids')>100 THEN
    RAISE EXCEPTION 'invalid_transition_engine' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.rehearsal_integer(engine->'generation',0,3);
  IF engine->'distribution_id'<>'null'::jsonb THEN
    entity:=vn_durability.canonical_id(engine->'distribution_id');
    IF NOT EXISTS(SELECT 1 FROM vn_durability.distributions WHERE run_id=state.id AND user_id=state.user_id AND id=entity) THEN
      RAISE EXCEPTION 'invalid_transition_distribution' USING ERRCODE='22023';
    END IF;
  END IF;
  IF engine->'last_quote'<>'null'::jsonb THEN
    PERFORM vn_durability.exact_keys(engine->'last_quote',ARRAY['timestamp','price']);
    PERFORM vn_durability.rehearsal_integer(engine->'last_quote'->'timestamp',0,253402300799);
    amount:=vn_durability.decimal_units(engine->'last_quote'->'price',18);
    IF amount<=0 OR engine->'last_quote'->>'price'<>vn_durability.decimal_text(amount,18) THEN
      RAISE EXCEPTION 'invalid_transition_quote' USING ERRCODE='22023';
    END IF;
  END IF;
  IF engine->'decision_timestamp'<>'null'::jsonb THEN
    PERFORM vn_durability.rehearsal_integer(engine->'decision_timestamp',0,253402300799);
  END IF;
  FOR item IN SELECT v FROM jsonb_array_elements(engine->'used_ids') q(v) LOOP
    entity:=vn_durability.canonical_id(item);
    IF entity=ANY(used) THEN RAISE EXCEPTION 'duplicate_transition_identity' USING ERRCODE='22023'; END IF;
    used:=array_append(used,entity);
  END LOOP;
  IF NOT ids<@used THEN RAISE EXCEPTION 'missing_transition_identity' USING ERRCODE='22023'; END IF;
  FOR member IN SELECT v FROM jsonb_array_elements(engine->'members') q(v) LOOP
    PERFORM vn_durability.exact_keys(member,ARRAY['id','name','genome','cursor','pending','num_trades','peak_equity','max_drawdown']);
    entity:=vn_durability.canonical_id(member->'id');
    IF entity=ANY(members) OR jsonb_typeof(member->'name') IS DISTINCT FROM 'string' OR
       octet_length(member->>'name') NOT BETWEEN 1 AND 128 OR
       NOT EXISTS(SELECT 1 FROM vn_durability.accounts WHERE run_id=state.id AND id=entity AND NOT retired) THEN
      RAISE EXCEPTION 'invalid_transition_member' USING ERRCODE='22023';
    END IF;
    members:=array_append(members,entity);
    PERFORM vn_durability.rehearsal_integer(member->'num_trades',0,64);
    PERFORM vn_durability.decimal_units(member->'peak_equity',36);
    IF member->'cursor'<>'null'::jsonb THEN
      PERFORM vn_durability.rehearsal_integer(member->'cursor',0,253402300799);
    END IF;
    PERFORM vn_durability.exact_keys(member->'max_drawdown',ARRAY['numerator','denominator']);
    IF jsonb_typeof(member->'max_drawdown'->'numerator') IS DISTINCT FROM 'string' OR
       jsonb_typeof(member->'max_drawdown'->'denominator') IS DISTINCT FROM 'string' OR
       length(member->'max_drawdown'->>'numerator')>75 OR length(member->'max_drawdown'->>'denominator')>75 OR
       member->'max_drawdown'->>'numerator' !~ '^(0|[1-9][0-9]*)$' OR
       member->'max_drawdown'->>'denominator' !~ '^[1-9][0-9]*$' THEN
      RAISE EXCEPTION 'invalid_transition_drawdown' USING ERRCODE='22023';
    END IF;
    IF (member->'max_drawdown'->>'numerator')::numeric>(member->'max_drawdown'->>'denominator')::numeric THEN
      RAISE EXCEPTION 'invalid_transition_drawdown' USING ERRCODE='22023';
    END IF;
    PERFORM vn_durability.exact_keys(member->'genome',ARRAY['rsi_period','rsi_oversold','rsi_overbought',
      'ema_fast','ema_slow','volume_threshold','position_size_pct','stop_loss_pct','take_profit_pct',
      'max_open_positions','timeframe_minutes','benchmark_target_pct','reproduce_target_dollars',
      'death_drawdown_pct','num_assets','assets','generation','parent_ids']);
    FOR label,value IN SELECT * FROM jsonb_each(member->'genome') LOOP
      IF label NOT IN ('assets','generation','parent_ids') THEN PERFORM vn_durability.rehearsal_hex(value); END IF;
    END LOOP;
    IF (member->'genome')-ARRAY['ema_fast','ema_slow','assets','generation','parent_ids'] IS DISTINCT FROM
       '{"benchmark_target_pct":"0x1.47ae147ae147bp-4","death_drawdown_pct":"0x1.999999999999ap-3",
         "max_open_positions":"0x1.0000000000000p+0","num_assets":"0x1.0000000000000p+0",
         "position_size_pct":"0x1.0000000000000p-2","reproduce_target_dollars":"0x1.4000000000000p+3",
         "rsi_overbought":"0x1.1800000000000p+6","rsi_oversold":"0x1.0000000000000p+5",
         "rsi_period":"0x1.c000000000000p+3","stop_loss_pct":"0x1.eb851eb851eb8p-6",
         "take_profit_pct":"0x1.1eb851eb851ecp-4","timeframe_minutes":"0x1.e000000000000p+3",
         "volume_threshold":"0x1.6666666666666p+0"}'::jsonb OR
       NOT EXISTS(SELECT 1 FROM generate_series(3,12) q(n) WHERE member->'genome'->>'ema_fast'=vn_durability.rehearsal_integer_hex(n)) OR
       NOT EXISTS(SELECT 1 FROM generate_series(15,60) q(n) WHERE member->'genome'->>'ema_slow'=vn_durability.rehearsal_integer_hex(n)) THEN
      RAISE EXCEPTION 'transition_profile_mismatch' USING ERRCODE='22023';
    END IF;
    IF member->'genome'->'assets' IS DISTINCT FROM jsonb_build_array(state.config->'rehearsal'->>'asset') OR
       member->'genome'->'generation' IS DISTINCT FROM engine->'generation' OR
       jsonb_typeof(member->'genome'->'parent_ids') IS DISTINCT FROM 'array' OR
       jsonb_array_length(member->'genome'->'parent_ids')>100 THEN
      RAISE EXCEPTION 'invalid_transition_genome' USING ERRCODE='22023';
    END IF;
    genome_parents:=ARRAY[]::uuid[];
    FOR item IN SELECT v FROM jsonb_array_elements(member->'genome'->'parent_ids') q(v) LOOP
      parent_entity:=vn_durability.canonical_id(item);
      IF parent_entity=ANY(genome_parents) OR NOT EXISTS(SELECT 1 FROM vn_durability.accounts
        WHERE run_id=state.id AND user_id=state.user_id AND id=parent_entity AND retired) THEN
        RAISE EXCEPTION 'invalid_transition_genome_parent' USING ERRCODE='22023';
      END IF;
      genome_parents:=array_append(genome_parents,parent_entity);
    END LOOP;
    IF member->'pending'<>'null'::jsonb THEN
      PERFORM vn_durability.exact_keys(member->'pending',ARRAY['action','signal_at','position_id']);
      IF member->'pending'->>'action' NOT IN ('entry','exit') THEN RAISE EXCEPTION 'invalid_transition_intent' USING ERRCODE='22023'; END IF;
      PERFORM vn_durability.rehearsal_integer(member->'pending'->'signal_at',0,253402300799);
      IF member->'pending'->>'action'='entry' THEN
        IF member->'pending'->'position_id'<>'null'::jsonb OR
           EXISTS(SELECT 1 FROM vn_durability.positions WHERE run_id=state.id AND account_id=entity AND NOT closed) THEN
          RAISE EXCEPTION 'invalid_transition_intent' USING ERRCODE='22023';
        END IF;
      ELSE
        IF NOT EXISTS(SELECT 1 FROM vn_durability.positions WHERE run_id=state.id AND account_id=entity AND
          id=vn_durability.canonical_id(member->'pending'->'position_id') AND NOT closed) THEN
          RAISE EXCEPTION 'invalid_transition_intent' USING ERRCODE='22023';
        END IF;
      END IF;
      IF member->'cursor'='null'::jsonb OR (member->'pending'->>'signal_at')::numeric<(member->>'cursor')::numeric OR
         (member->'pending'->>'signal_at')::numeric>(member->>'cursor')::numeric+900 THEN
        RAISE EXCEPTION 'invalid_transition_intent' USING ERRCODE='22023';
      END IF;
    END IF;
    SELECT v INTO prior FROM jsonb_array_elements(coalesce(state.engine_state->'engine'->'members','[]'::jsonb)) q(v)
      WHERE v->>'id'=entity::text;
    IF FOUND THEN
      IF member->'genome' IS DISTINCT FROM prior->'genome' OR member->'name' IS DISTINCT FROM prior->'name' THEN
        RAISE EXCEPTION 'transition_member_identity_changed' USING ERRCODE='22023';
      END IF;
      IF prior->'cursor'<>'null'::jsonb AND (member->'cursor'='null'::jsonb OR
         (member->>'cursor')::numeric<(prior->>'cursor')::numeric) THEN
        RAISE EXCEPTION 'transition_cursor_regressed' USING ERRCODE='22023';
      END IF;
      peak:=vn_durability.decimal_units(prior->'peak_equity',36);
      draw_num:=(prior->'max_drawdown'->>'numerator')::numeric;
      draw_den:=(prior->'max_drawdown'->>'denominator')::numeric;
      reference:=vn_durability.decimal_units(engine->'last_quote'->'price',18);
      IF payload->'transition'->'evidence'->>'kind'='protective' THEN
        SELECT vn_durability.decimal_units(v->'cash',36) INTO equity
          FROM jsonb_array_elements(state.engine_state->'accounts') q(v) WHERE v->>'id'=entity::text;
        SELECT equity+coalesce(sum(vn_durability.decimal_units(v->'entry'->'quantity',18)*reference),0) INTO equity
          FROM jsonb_array_elements(state.engine_state->'positions') q(v) WHERE v->>'account_id'=entity::text AND v->'closed'='false'::jsonb;
        peak:=greatest(peak,equity);
        IF (peak-equity)*draw_den>draw_num*peak THEN draw_num:=peak-equity; draw_den:=peak; END IF;
        IF member->'cursor' IS DISTINCT FROM prior->'cursor' OR member->'pending' IS DISTINCT FROM
           (CASE WHEN EXISTS(SELECT 1 FROM jsonb_array_elements(payload->'transition'->'evidence'->'actions') q(v)
                             WHERE v->>'account_id'=entity::text) THEN 'null'::jsonb ELSE prior->'pending' END) THEN
          RAISE EXCEPTION 'protective_cursor_changed' USING ERRCODE='22023';
        END IF;
      END IF;
      IF payload->'transition'->'evidence'->>'kind'='protective' OR
         EXISTS(SELECT 1 FROM jsonb_array_elements(payload->'transition'->'evidence'->'actions') q(v) WHERE v->>'account_id'=entity::text) THEN
        SELECT a.cash*1e36+coalesce((SELECT sum(p.quantity*1e18*reference) FROM vn_durability.positions p
          WHERE p.run_id=state.id AND p.account_id=entity AND NOT p.closed),0) INTO equity
          FROM vn_durability.accounts a WHERE a.run_id=state.id AND a.id=entity;
        peak:=greatest(peak,equity);
        IF (peak-equity)*draw_den>draw_num*peak THEN draw_num:=peak-equity; draw_den:=peak; END IF;
      END IF;
      IF member->>'peak_equity' IS DISTINCT FROM vn_durability.decimal_text(peak,36) OR
         (member->'max_drawdown'->>'numerator')::numeric*draw_den<>(member->'max_drawdown'->>'denominator')::numeric*draw_num THEN
        RAISE EXCEPTION 'transition_risk_metrics_mismatch' USING ERRCODE='22023';
      END IF;
    ELSE
      IF member->>'peak_equity' IS DISTINCT FROM state.config->'rehearsal'->>'seed_capital' OR
         member->'max_drawdown' IS DISTINCT FROM '{"numerator":"0","denominator":"1"}'::jsonb OR
         member->'pending'<>'null'::jsonb THEN RAISE EXCEPTION 'invalid_new_member_state' USING ERRCODE='22023'; END IF;
    END IF;
    IF (member->>'num_trades')::integer<>(SELECT count(*) FROM vn_durability.positions
      WHERE run_id=state.id AND account_id=entity AND closed) THEN
      RAISE EXCEPTION 'transition_trade_count_mismatch' USING ERRCODE='22023';
    END IF;
  END LOOP;
  IF (SELECT count(*) FROM vn_durability.accounts WHERE run_id=state.id AND NOT retired)<>8 THEN
    RAISE EXCEPTION 'incomplete_transition_membership' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.exact_keys(engine->'ema',ARRAY['count','last_end','closes','values','previous']);
  PERFORM vn_durability.rehearsal_integer(engine->'ema'->'count',0,4096);
  IF engine->'ema'->'last_end'<>'null'::jsonb THEN PERFORM vn_durability.rehearsal_integer(engine->'ema'->'last_end',0,253402300799); END IF;
  IF jsonb_typeof(engine->'ema'->'closes') IS DISTINCT FROM 'array' OR jsonb_array_length(engine->'ema'->'closes')>64 OR
     jsonb_typeof(engine->'ema'->'values') IS DISTINCT FROM 'object' OR jsonb_typeof(engine->'ema'->'previous') IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'invalid_transition_ema' USING ERRCODE='22023';
  END IF;
  IF jsonb_array_length(engine->'ema'->'closes')<>least((engine->'ema'->>'count')::integer,64) OR
     ((engine->'ema'->'last_end')='null'::jsonb)<>((engine->'ema'->>'count')::integer=0) OR
     (SELECT count(*) FROM jsonb_object_keys(engine->'ema'->'values'))<>greatest(least((engine->'ema'->>'count')::integer,60)-1,0) OR
     (SELECT count(*) FROM jsonb_object_keys(engine->'ema'->'previous'))<>greatest(least((engine->'ema'->>'count')::integer-1,60)-1,0) OR
     EXISTS(SELECT 1 FROM generate_series(2,least((engine->'ema'->>'count')::integer,60)) q(n) WHERE NOT (engine->'ema'->'values') ? n::text) OR
     EXISTS(SELECT 1 FROM generate_series(2,least((engine->'ema'->>'count')::integer-1,60)) q(n) WHERE NOT (engine->'ema'->'previous') ? n::text) THEN
    RAISE EXCEPTION 'invalid_transition_ema_shape' USING ERRCODE='22023';
  END IF;
  FOR item IN SELECT v FROM jsonb_array_elements(engine->'ema'->'closes') q(v) LOOP
    amount:=vn_durability.decimal_units(item,18);
    IF amount<=0 OR item#>>'{}'<>vn_durability.decimal_text(amount,18) THEN RAISE EXCEPTION 'invalid_transition_ema' USING ERRCODE='22023'; END IF;
  END LOOP;
  FOR label,value IN SELECT * FROM jsonb_each(engine->'ema'->'values')
                    UNION ALL SELECT * FROM jsonb_each(engine->'ema'->'previous') LOOP
    IF label !~ '^[1-9][0-9]?$' OR label::integer>60 THEN RAISE EXCEPTION 'invalid_transition_ema' USING ERRCODE='22023'; END IF;
    PERFORM vn_durability.rehearsal_hex(value);
    IF value#>>'{}' LIKE '-%' OR value#>>'{}'='0x0.0p+0' THEN RAISE EXCEPTION 'invalid_transition_ema' USING ERRCODE='22023'; END IF;
  END LOOP;
  FOR member IN SELECT v FROM jsonb_array_elements(engine->'members') q(v) LOOP
    IF member->'cursor'<>'null'::jsonb AND member->'cursor' IS DISTINCT FROM engine->'ema'->'last_end' THEN
      RAISE EXCEPTION 'transition_member_cursor_mismatch' USING ERRCODE='22023';
    END IF;
  END LOOP;
  IF engine->'last_evaluation'<>'null'::jsonb THEN
    PERFORM vn_durability.exact_keys(engine->'last_evaluation',ARRAY['cohort','selection']);
    IF jsonb_typeof(engine->'last_evaluation'->'cohort') IS DISTINCT FROM 'object' OR
       jsonb_typeof(engine->'last_evaluation'->'selection') IS DISTINCT FROM 'object' THEN
      RAISE EXCEPTION 'invalid_transition_evaluation' USING ERRCODE='22023';
    END IF;
    IF state.engine_state IS NOT NULL AND (engine->>'generation')::integer>(state.engine_state->'engine'->>'generation')::integer THEN
      PERFORM vn_durability.rehearsal_evaluation(state,engine->'last_evaluation',(engine->>'generation')::integer,
        (SELECT jsonb_agg(v->'id' ORDER BY ordinal) FROM jsonb_array_elements(state.engine_state->'engine'->'members') WITH ORDINALITY q(v,ordinal)),
        (payload->'transition'->'evidence'->'observation'->>'timestamp')::numeric);
    ELSE
      PERFORM vn_durability.rehearsal_evaluation(state,engine->'last_evaluation',(engine->>'generation')::integer);
    END IF;
  ELSIF (engine->>'generation')::integer<>0 THEN
    RAISE EXCEPTION 'missing_completed_evaluation' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.exact_keys(engine->'optimizer',ARRAY['version','software','strategy','cohort']);
  PERFORM vn_durability.exact_keys(engine->'optimizer'->'software',ARRAY['python','numpy','cmaes']);
  IF engine->'optimizer'->>'version' IS DISTINCT FROM 'optimizer-evidence-v1' OR
     engine->'optimizer'->'software'->>'cmaes' IS DISTINCT FROM '0.13.1' THEN
    RAISE EXCEPTION 'invalid_transition_optimizer' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.rehearsal_json(engine);
  PERFORM vn_durability.optimizer_evidence(engine->'optimizer',state.config->'rehearsal'->>'strategy');
END $$;

CREATE FUNCTION vn_durability.validate_transition_before(state vn_durability.runs, payload jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE transition jsonb:=payload->'transition'; evidence jsonb; inputs jsonb; observation jsonb;
        before_state jsonb; after_state jsonb; action jsonb; operation jsonb; event jsonb; member jsonb;
        kind text; reason text; stamp numeric; event_stamp numeric; price numeric; reference numeric;
        index integer:=0; event_index integer:=0; evaluation_events integer:=0;
        entity uuid; position vn_durability.positions%ROWTYPE; cash numeric; seen uuid[]:=ARRAY[]::uuid[];
        item jsonb; generation numeric; previous_generation numeric; expected_event jsonb;
        old_ids jsonb; new_ids jsonb; consumed integer; expected_ids jsonb; names_used integer:=0;
        before_ema jsonb; after_ema jsonb; expected_closes jsonb; birth_ids jsonb; retire_ids jsonb;
BEGIN
  PERFORM vn_durability.exact_keys(transition,ARRAY['version','before','after','evidence','events']);
  before_state:=transition->'before'; after_state:=transition->'after'; evidence:=transition->'evidence';
  IF transition->'version'<>'1'::jsonb OR before_state IS DISTINCT FROM coalesce(state.engine_state,'null'::jsonb) THEN
    RAISE EXCEPTION 'transition_before_mismatch' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.exact_keys(evidence,ARRAY['kind','inputs','observation','actions']);
  inputs:=evidence->'inputs'; observation:=evidence->'observation'; kind:=evidence->>'kind';
  PERFORM vn_durability.exact_keys(inputs,ARRAY['event_at','wall_at','monotonic_at','ids','names']);
  IF kind IS NULL OR kind NOT IN ('bootstrap','protective','decision') OR
     jsonb_typeof(inputs->'event_at') IS DISTINCT FROM 'string' OR
     jsonb_typeof(inputs->'wall_at') IS DISTINCT FROM 'string' OR
     inputs->>'event_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00$' OR
     inputs->>'wall_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?\+00:00$' OR
     jsonb_typeof(inputs->'ids') IS DISTINCT FROM 'array' OR jsonb_array_length(inputs->'ids')>4096 OR
     jsonb_typeof(inputs->'names') IS DISTINCT FROM 'array' OR jsonb_array_length(inputs->'names')>4096 OR
     jsonb_typeof(evidence->'actions') IS DISTINCT FROM 'array' OR
     jsonb_array_length(evidence->'actions')<>jsonb_array_length(payload->'operations') OR
     jsonb_typeof(transition->'events') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid_transition_evidence' USING ERRCODE='22023';
  END IF;
  PERFORM (inputs->>'wall_at')::timestamptz;
  event_stamp:=extract(epoch FROM (inputs->>'event_at')::timestamptz);
  IF event_stamp<0 OR event_stamp>253402300799 THEN RAISE EXCEPTION 'invalid_transition_time' USING ERRCODE='22023'; END IF;
  PERFORM vn_durability.rehearsal_hex(inputs->'monotonic_at');
  IF inputs->>'monotonic_at' LIKE '-%' AND inputs->>'monotonic_at'<>'-0x0.0p+0' THEN
    RAISE EXCEPTION 'invalid_transition_time' USING ERRCODE='22023';
  END IF;
  FOR item IN SELECT v FROM jsonb_array_elements(inputs->'ids') q(v) LOOP
    entity:=vn_durability.canonical_id(item);
    IF entity=ANY(seen) THEN RAISE EXCEPTION 'duplicate_transition_allocation' USING ERRCODE='22023'; END IF;
    seen:=array_append(seen,entity);
  END LOOP;
  FOR item IN SELECT v FROM jsonb_array_elements(inputs->'names') q(v) LOOP
    IF jsonb_typeof(item) IS DISTINCT FROM 'array' OR jsonb_array_length(item)<>2 OR
       jsonb_typeof(item->1) IS DISTINCT FROM 'string' OR octet_length(item->>1) NOT BETWEEN 1 AND 128 OR
       item->>1<>btrim(item->>1) OR item->>1 ~ '[[:cntrl:]]' THEN
      RAISE EXCEPTION 'invalid_transition_name' USING ERRCODE='22023';
    END IF;
    PERFORM vn_durability.rehearsal_integer(item->0,0,2147483647);
  END LOOP;
  generation:=vn_durability.rehearsal_integer(after_state->'engine'->'generation',0,3);
  IF kind='bootstrap' THEN
    IF state.engine_state IS NOT NULL OR state.revision<>1 OR state.status<>'starting' OR
       observation<>'null'::jsonb OR generation<>0 OR jsonb_array_length(payload->'operations')<>9 OR
       EXISTS(SELECT 1 FROM vn_durability.accounts WHERE run_id=state.id) OR
       EXISTS(SELECT 1 FROM vn_durability.positions WHERE run_id=state.id) OR
       after_state->'engine'->'last_quote'<>'null'::jsonb OR after_state->'engine'->'decision_timestamp'<>'null'::jsonb THEN
      RAISE EXCEPTION 'invalid_transition_bootstrap' USING ERRCODE='22023';
    END IF;
  ELSE
    IF state.engine_state IS NULL OR state.status<>'running' THEN RAISE EXCEPTION 'transition_not_initialized' USING ERRCODE='22023'; END IF;
    previous_generation:=(before_state->'engine'->>'generation')::numeric;
    IF previous_generation>=3 OR generation NOT BETWEEN previous_generation AND previous_generation+1 THEN
      RAISE EXCEPTION 'transition_generation_mismatch' USING ERRCODE='22023';
    END IF;
    PERFORM vn_durability.exact_keys(observation,ARRAY['timestamp','price','candle_end','candle_close']);
    stamp:=vn_durability.rehearsal_integer(observation->'timestamp',0,253402300799);
    price:=vn_durability.decimal_units(observation->'price',18);
    IF price<=0 OR observation->>'price'<>vn_durability.decimal_text(price,18) OR stamp<>event_stamp OR
       after_state->'engine'->'last_quote' IS DISTINCT FROM jsonb_build_object('timestamp',observation->'timestamp','price',observation->'price') OR
       (observation->'candle_end'='null'::jsonb)<>(observation->'candle_close'='null'::jsonb) THEN
      RAISE EXCEPTION 'transition_source_mismatch' USING ERRCODE='22023';
    END IF;
    IF observation->'candle_end'<>'null'::jsonb THEN
      reference:=vn_durability.rehearsal_integer(observation->'candle_end',0,253402300799);
      cash:=vn_durability.decimal_units(observation->'candle_close',18);
      IF mod(reference,900)<>0 OR reference>stamp OR cash<=0 OR
         observation->>'candle_close'<>vn_durability.decimal_text(cash,18) THEN
        RAISE EXCEPTION 'invalid_transition_candle' USING ERRCODE='22023';
      END IF;
    END IF;
    IF kind='protective' THEN
      IF generation<>previous_generation OR observation->'candle_end'<>'null'::jsonb OR
         (before_state->'engine'->'last_quote'<>'null'::jsonb AND stamp<=(before_state->'engine'->'last_quote'->>'timestamp')::numeric) OR
         after_state->'engine'->'decision_timestamp' IS DISTINCT FROM before_state->'engine'->'decision_timestamp' OR
         (after_state->'engine')-ARRAY['last_quote','members'] IS DISTINCT FROM (before_state->'engine')-ARRAY['last_quote','members'] THEN
        RAISE EXCEPTION 'invalid_protective_transition' USING ERRCODE='22023';
      END IF;
      -- A successful protective phase cannot omit a position already beyond a
      -- fixed threshold, then admit an ordinary decision on that same quote.
      FOR position IN SELECT * FROM vn_durability.positions WHERE run_id=state.id AND NOT closed LOOP
        reference:=vn_durability.decimal_units(position.entry_execution->'reference_price',18);
        IF (price*100<=reference*97 OR price*100>=reference*107) AND NOT EXISTS(
          SELECT 1 FROM jsonb_array_elements(payload->'operations') q(v) WHERE v->>'kind'='close' AND v->>'id'=position.id::text) THEN
          RAISE EXCEPTION 'missing_protective_close' USING ERRCODE='22023';
        END IF;
      END LOOP;
    ELSE
      IF before_state->'engine'->'last_quote' IS DISTINCT FROM after_state->'engine'->'last_quote' OR
         after_state->'engine'->'decision_timestamp' IS DISTINCT FROM observation->'timestamp' OR
         (before_state->'engine'->'decision_timestamp'<>'null'::jsonb AND stamp<=(before_state->'engine'->>'decision_timestamp')::numeric) THEN
        RAISE EXCEPTION 'invalid_decision_transition' USING ERRCODE='22023';
      END IF;
    END IF;
  END IF;
  FOR action IN SELECT v FROM jsonb_array_elements(evidence->'actions') q(v) LOOP
    PERFORM vn_durability.exact_keys(action,ARRAY['operation_index','reason','account_id','position_id','signal_at','reference_price']);
    IF vn_durability.rehearsal_integer(action->'operation_index',0,1023)<>index THEN RAISE EXCEPTION 'transition_action_order' USING ERRCODE='22023'; END IF;
    operation:=payload->'operations'->index; reason:=action->>'reason';
    IF operation->>'kind' IN ('open','close') THEN
      IF action->>'position_id' IS DISTINCT FROM operation->>'id' OR
         action->'reference_price' IS DISTINCT FROM observation->'price' OR
         operation->'execution'->'reference_price' IS DISTINCT FROM observation->'price' THEN
        RAISE EXCEPTION 'transition_execution_source_mismatch' USING ERRCODE='22023';
      END IF;
      IF operation->>'kind'='open' THEN
        IF reason IS DISTINCT FROM 'entry_signal' OR kind<>'decision' OR
           action->'account_id' IS DISTINCT FROM operation->'account_id' OR
           operation->'asset' IS DISTINCT FROM state.config->'rehearsal'->'asset' THEN
          RAISE EXCEPTION 'transition_open_reason_mismatch' USING ERRCODE='22023';
        END IF;
        SELECT a.cash INTO cash FROM vn_durability.accounts a WHERE a.run_id=state.id AND a.id=vn_durability.canonical_id(action->'account_id') AND NOT a.retired;
        IF NOT FOUND OR operation->'execution'->>'budget' IS DISTINCT FROM vn_durability.decimal_text(div(cash*1e36,4),36) THEN
          RAISE EXCEPTION 'transition_entry_budget_mismatch' USING ERRCODE='22023';
        END IF;
      ELSE
        SELECT * INTO position FROM vn_durability.positions WHERE run_id=state.id AND id=vn_durability.canonical_id(operation->'id') AND NOT closed;
        IF NOT FOUND OR action->>'account_id' IS DISTINCT FROM position.account_id::text THEN
          RAISE EXCEPTION 'transition_close_identity_mismatch' USING ERRCODE='22023';
        END IF;
        reference:=vn_durability.decimal_units(position.entry_execution->'reference_price',18);
        IF reason='stop_loss' THEN
          IF kind<>'protective' OR price*100>reference*97 THEN RAISE EXCEPTION 'transition_threshold_mismatch' USING ERRCODE='22023'; END IF;
        ELSIF reason='take_profit' THEN
          IF kind<>'protective' OR price*100<reference*107 THEN RAISE EXCEPTION 'transition_threshold_mismatch' USING ERRCODE='22023'; END IF;
        ELSIF reason='exit_signal' THEN
          IF kind<>'decision' THEN RAISE EXCEPTION 'transition_close_reason_mismatch' USING ERRCODE='22023'; END IF;
        ELSIF reason='cohort_liquidation' THEN
          IF kind<>'decision' OR generation<>previous_generation+1 THEN RAISE EXCEPTION 'transition_close_reason_mismatch' USING ERRCODE='22023'; END IF;
        ELSE RAISE EXCEPTION 'transition_close_reason_mismatch' USING ERRCODE='22023';
        END IF;
      END IF;
      IF reason IN ('entry_signal','exit_signal') THEN
        reference:=vn_durability.rehearsal_integer(action->'signal_at',0,253402300799);
        SELECT v INTO member FROM jsonb_array_elements(before_state->'engine'->'members') q(v) WHERE v->'id'=action->'account_id';
        IF NOT FOUND OR member->'pending'->'signal_at' IS DISTINCT FROM action->'signal_at' OR
           member->'pending'->>'action' IS DISTINCT FROM (CASE WHEN reason='entry_signal' THEN 'entry' ELSE 'exit' END) OR
           (reason='exit_signal' AND member->'pending'->'position_id' IS DISTINCT FROM action->'position_id') OR
           member->'cursor'='null'::jsonb OR
           NOT (stamp>reference AND stamp<=(member->>'cursor')::numeric+900) THEN
          RAISE EXCEPTION 'transition_signal_cursor_mismatch' USING ERRCODE='22023';
        END IF;
      ELSIF action->'signal_at'<>'null'::jsonb THEN RAISE EXCEPTION 'invalid_transition_action' USING ERRCODE='22023';
      END IF;
    ELSE
      IF action->'position_id'<>'null'::jsonb OR action->'signal_at'<>'null'::jsonb OR action->'reference_price'<>'null'::jsonb THEN
        RAISE EXCEPTION 'invalid_transition_action' USING ERRCODE='22023';
      END IF;
      IF operation->>'kind'='birth' THEN
        IF action->'account_id' IS DISTINCT FROM operation->'id' OR
           operation->'cash' IS DISTINCT FROM state.config->'rehearsal'->'seed_capital' OR
           reason IS DISTINCT FROM (CASE WHEN kind='bootstrap' THEN 'founder' ELSE 'birth' END) OR
           (kind<>'bootstrap' AND (kind<>'decision' OR generation<>previous_generation+1)) THEN
          RAISE EXCEPTION 'transition_birth_mismatch' USING ERRCODE='22023';
        END IF;
      ELSIF operation->>'kind'='retire' THEN
        IF reason IS DISTINCT FROM 'retire' OR kind<>'decision' OR generation<>previous_generation+1 OR
           action->'account_id' IS DISTINCT FROM operation->'id' THEN RAISE EXCEPTION 'transition_retirement_mismatch' USING ERRCODE='22023'; END IF;
      ELSIF operation->>'kind'='distribution' THEN
        IF reason IS DISTINCT FROM 'distribution' OR kind<>'decision' OR generation<>previous_generation+1 OR
           action->'account_id'<>'null'::jsonb THEN RAISE EXCEPTION 'transition_distribution_mismatch' USING ERRCODE='22023'; END IF;
      ELSIF operation->>'kind'='lifecycle' THEN
        IF reason IS DISTINCT FROM 'lifecycle' OR kind<>'bootstrap' OR operation->>'status'<>'running' OR
           action->'account_id'<>'null'::jsonb THEN RAISE EXCEPTION 'transition_lifecycle_mismatch' USING ERRCODE='22023'; END IF;
      ELSE RAISE EXCEPTION 'invalid_transition_action' USING ERRCODE='22023';
      END IF;
    END IF;
    index:=index+1;
  END LOOP;
  FOR event IN SELECT v FROM jsonb_array_elements(transition->'events') q(v) LOOP
    PERFORM vn_durability.exact_keys(event,ARRAY['kind','at','account_id','position_id','operation_index']);
    IF vn_durability.rehearsal_integer(event->'at',0,253402300799)<>event_stamp THEN RAISE EXCEPTION 'transition_event_time_mismatch' USING ERRCODE='22023'; END IF;
    IF event->>'kind'='evaluation' THEN
      IF kind<>'decision' OR generation<>previous_generation+1 OR event->'account_id'<>'null'::jsonb OR
         event->'position_id'<>'null'::jsonb OR event->'operation_index'<>'null'::jsonb THEN
        RAISE EXCEPTION 'invalid_transition_evaluation_event' USING ERRCODE='22023';
      END IF;
      evaluation_events:=evaluation_events+1;
    ELSE
      action:=evidence->'actions'->event_index;
      expected_event:=jsonb_build_object('kind',action->'reason','at',event->'at','account_id',action->'account_id',
        'position_id',action->'position_id','operation_index',action->'operation_index');
      IF event IS DISTINCT FROM expected_event THEN RAISE EXCEPTION 'transition_event_mismatch' USING ERRCODE='22023'; END IF;
      event_index:=event_index+1;
    END IF;
  END LOOP;
  IF event_index<>index OR evaluation_events<>(CASE WHEN kind='decision' AND generation=previous_generation+1 THEN 1 ELSE 0 END) THEN
    RAISE EXCEPTION 'incomplete_transition_events' USING ERRCODE='22023';
  END IF;
  old_ids:=coalesce(before_state->'engine'->'used_ids','[]'::jsonb);
  new_ids:=after_state->'engine'->'used_ids';
  consumed:=jsonb_array_length(new_ids)-jsonb_array_length(old_ids);
  SELECT coalesce(jsonb_agg(v ORDER BY ordinal),'[]'::jsonb) INTO expected_ids
    FROM jsonb_array_elements(inputs->'ids') WITH ORDINALITY q(v,ordinal) WHERE ordinal<=consumed;
  IF consumed<0 OR new_ids IS DISTINCT FROM old_ids||expected_ids OR
     consumed<>(SELECT count(*) FROM jsonb_array_elements(payload->'operations') q(v) WHERE v->>'kind' IN ('birth','open','distribution')) OR
     EXISTS(SELECT 1 FROM jsonb_array_elements(expected_ids) q(v) WHERE NOT EXISTS(
       SELECT 1 FROM jsonb_array_elements(payload->'operations') x(op) WHERE op->>'kind' IN ('birth','open','distribution') AND op->'id'=v)) THEN
    RAISE EXCEPTION 'transition_identity_allocation_mismatch' USING ERRCODE='22023';
  END IF;
  FOR operation IN SELECT v FROM jsonb_array_elements(payload->'operations') q(v) WHERE v->>'kind'='birth' LOOP
    SELECT v INTO member FROM jsonb_array_elements(after_state->'engine'->'members') q(v) WHERE v->'id'=operation->'id';
    IF NOT FOUND OR inputs->'names'->names_used IS DISTINCT FROM jsonb_build_array(generation,member->'name') THEN
      RAISE EXCEPTION 'transition_name_allocation_mismatch' USING ERRCODE='22023';
    END IF;
    names_used:=names_used+1;
  END LOOP;
  SELECT coalesce(jsonb_agg(v->'id' ORDER BY ordinal),'[]'::jsonb) INTO birth_ids
    FROM jsonb_array_elements(payload->'operations') WITH ORDINALITY q(v,ordinal) WHERE v->>'kind'='birth';
  SELECT coalesce(jsonb_agg(v->'id' ORDER BY ordinal),'[]'::jsonb) INTO retire_ids
    FROM jsonb_array_elements(payload->'operations') WITH ORDINALITY q(v,ordinal) WHERE v->>'kind'='retire';
  IF kind='bootstrap' OR generation=previous_generation+1 THEN
    IF jsonb_array_length(birth_ids)<>8 OR birth_ids IS DISTINCT FROM
       (SELECT jsonb_agg(v->'id' ORDER BY ordinal) FROM jsonb_array_elements(after_state->'engine'->'members') WITH ORDINALITY q(v,ordinal)) THEN
      RAISE EXCEPTION 'transition_birth_membership_mismatch' USING ERRCODE='22023';
    END IF;
    IF kind<>'bootstrap' AND (retire_ids IS DISTINCT FROM
       (SELECT jsonb_agg(v->'id' ORDER BY ordinal) FROM jsonb_array_elements(before_state->'engine'->'members') WITH ORDINALITY q(v,ordinal)) OR
       after_state->'engine'->'last_evaluation'='null'::jsonb) THEN
      RAISE EXCEPTION 'transition_replacement_incomplete' USING ERRCODE='22023';
    END IF;
  ELSIF birth_ids<>'[]'::jsonb OR retire_ids<>'[]'::jsonb OR
        after_state->'engine'->'last_evaluation' IS DISTINCT FROM before_state->'engine'->'last_evaluation' OR
        after_state->'engine'->'distribution_id' IS DISTINCT FROM before_state->'engine'->'distribution_id' THEN
    RAISE EXCEPTION 'unexpected_replacement_state' USING ERRCODE='22023';
  END IF;
  IF kind<>'bootstrap' AND generation=previous_generation AND
     (SELECT jsonb_agg(v->'id' ORDER BY ordinal) FROM jsonb_array_elements(after_state->'engine'->'members') WITH ORDINALITY q(v,ordinal)) IS DISTINCT FROM
     (SELECT jsonb_agg(v->'id' ORDER BY ordinal) FROM jsonb_array_elements(before_state->'engine'->'members') WITH ORDINALITY q(v,ordinal)) THEN
    RAISE EXCEPTION 'transition_member_order_changed' USING ERRCODE='22023';
  END IF;
  IF kind='decision' THEN
    before_ema:=before_state->'engine'->'ema'; after_ema:=after_state->'engine'->'ema';
    IF generation=previous_generation AND
       (after_state->'engine'->'optimizer'->'strategy' IS DISTINCT FROM before_state->'engine'->'optimizer'->'strategy' OR
        (after_state->'engine'->'optimizer' IS DISTINCT FROM before_state->'engine'->'optimizer' AND
         NOT ((before_ema->>'count')::integer<61 AND (after_ema->>'count')::integer>=61))) THEN
      RAISE EXCEPTION 'unexpected_optimizer_progression' USING ERRCODE='22023';
    END IF;
    IF observation->'candle_end'='null'::jsonb OR observation->'candle_end'=before_ema->'last_end' THEN
      IF after_ema IS DISTINCT FROM before_ema OR (observation->'candle_end'<>'null'::jsonb AND
         observation->'candle_close' IS DISTINCT FROM before_ema->'closes'->-1) THEN
        RAISE EXCEPTION 'transition_candle_revision' USING ERRCODE='22023';
      END IF;
    ELSE
      IF before_ema->'last_end'<>'null'::jsonb AND (observation->>'candle_end')::numeric<>(before_ema->>'last_end')::numeric+900 THEN
        RAISE EXCEPTION 'transition_candle_gap' USING ERRCODE='22023';
      END IF;
      SELECT jsonb_agg(v ORDER BY ordinal) INTO expected_closes FROM
        jsonb_array_elements((before_ema->'closes')||jsonb_build_array(observation->'candle_close')) WITH ORDINALITY q(v,ordinal)
        WHERE ordinal>greatest(jsonb_array_length(before_ema->'closes')+1-64,0);
      IF after_ema->'count' IS DISTINCT FROM to_jsonb((before_ema->>'count')::integer+1) OR
         after_ema->'last_end' IS DISTINCT FROM observation->'candle_end' OR
         after_ema->'closes' IS DISTINCT FROM expected_closes OR
         after_ema->'previous' IS DISTINCT FROM before_ema->'values' THEN
        RAISE EXCEPTION 'transition_candle_state_mismatch' USING ERRCODE='22023';
      END IF;
    END IF;
  END IF;
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
    IF (configuration->'durability_contract_version')::text NOT IN ('1','2','3') THEN
      RAISE EXCEPTION 'invalid_contract_version' USING ERRCODE='22023';
    END IF;
    contract_version:=(configuration->>'durability_contract_version')::integer;
  END IF;
  IF contract_version>=2 THEN PERFORM vn_durability.execution_policy(configuration->'execution'); END IF;
  IF contract_version=3 THEN
    PERFORM vn_durability.rehearsal_config(configuration);
    IF initial_cash IS DISTINCT FROM configuration->'rehearsal'->>'initial_cash' THEN
      RAISE EXCEPTION 'rehearsal_initial_cash_mismatch' USING ERRCODE='22023';
    END IF;
  END IF;
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
  IF (payload->'version')::text='3' THEN
    PERFORM vn_durability.exact_keys(payload,ARRAY['version','operations','transition']);
  ELSE
    PERFORM vn_durability.exact_keys(payload,ARRAY['version','operations']);
  END IF;
  IF (payload->'version')::text NOT IN ('1','2','3') OR
     jsonb_typeof(payload->'operations') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  contract_version:=(payload->>'version')::integer;
  IF jsonb_array_length(payload->'operations') NOT BETWEEN (CASE WHEN contract_version=3 THEN 0 ELSE 1 END)
     AND (CASE WHEN contract_version>=2 THEN 1024 ELSE 256 END) THEN
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

  IF contract_version=3 THEN
    PERFORM vn_durability.validate_transition_before(state,payload);
  END IF;

  FOR operation IN SELECT value FROM jsonb_array_elements(payload->'operations') LOOP
    operation_kind := operation->>'kind';
    IF state.status IN ('stopped','failed') THEN RAISE EXCEPTION 'run_terminal' USING ERRCODE='P0001'; END IF;
    IF operation_kind = 'birth' THEN
      IF contract_version>=2 THEN
        PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','cash','lineage']);
      ELSE
        PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','cash','parent_ids']);
      END IF;
      entity := CASE WHEN contract_version>=2 THEN vn_durability.canonical_id(operation->'id')
                     ELSE (operation->>'id')::uuid END;
      cash := vn_durability.money(operation->'cash');
      IF entity IS NULL OR cash <= 0 OR cash > state.reserve THEN
        RAISE EXCEPTION 'invalid_birth' USING ERRCODE='22023';
      END IF;
      IF state.status IN ('paused','risk_halted') THEN
        RAISE EXCEPTION 'invalid_birth' USING ERRCODE='22023';
      END IF;
      INSERT INTO vn_durability.accounts(run_id,user_id,id,cash,initial_cash) VALUES(run,owner_id,entity,cash,cash);
      IF contract_version>=2 THEN
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
    ELSIF operation_kind='distribution' AND contract_version>=2 THEN
      IF state.status IN ('paused','risk_halted') THEN RAISE EXCEPTION 'invalid_distribution' USING ERRCODE='22023'; END IF;
      PERFORM vn_durability.record_distribution(owner_id,run,operation);
    ELSIF operation_kind = 'open' THEN
      IF contract_version>=2 THEN
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
      entity := CASE WHEN contract_version>=2 THEN vn_durability.canonical_id(operation->'id')
                     ELSE (operation->>'id')::uuid END;
      account_id := CASE WHEN contract_version>=2 THEN vn_durability.canonical_id(operation->'account_id')
                         ELSE (operation->>'account_id')::uuid END;
      quantity := vn_durability.money(operation->'quantity');
      notional := vn_durability.money(operation->'notional'); fee := vn_durability.money(operation->'fee');
      SELECT * INTO account FROM vn_durability.accounts a WHERE a.run_id=run AND a.id=account_id AND a.user_id=owner_id;
      IF NOT FOUND OR account.retired OR entity IS NULL OR quantity <= 0 OR notional <= 0 OR
         notional+fee > account.cash OR state.status <> 'running' OR
         (contract_version>=2 AND (execution->>'budget')::numeric>account.cash) OR
         jsonb_typeof(operation->'asset') IS DISTINCT FROM 'string' OR
         length(operation->>'asset') NOT BETWEEN 1 AND 64 THEN
        RAISE EXCEPTION 'invalid_open' USING ERRCODE='22023';
      END IF;
      INSERT INTO vn_durability.positions(run_id,user_id,id,account_id,asset,quantity,notional,entry_fee,entry_execution)
      VALUES(run,owner_id,entity,account_id,operation->>'asset',quantity,notional,fee,execution);
      UPDATE vn_durability.accounts a SET cash=a.cash-notional-fee WHERE a.run_id=run AND a.id=account_id;
    ELSIF operation_kind = 'close' THEN
      IF contract_version>=2 THEN
        PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','proceeds','fee','execution']);
      ELSE
        PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','proceeds','fee']);
      END IF;
      entity := CASE WHEN contract_version>=2 THEN vn_durability.canonical_id(operation->'id')
                     ELSE (operation->>'id')::uuid END;
      close_proceeds := vn_durability.money(operation->'proceeds'); fee := vn_durability.money(operation->'fee');
      SELECT * INTO position FROM vn_durability.positions p WHERE p.run_id=run AND p.id=entity AND p.user_id=owner_id;
      IF NOT FOUND OR position.closed OR fee > close_proceeds THEN RAISE EXCEPTION 'invalid_close' USING ERRCODE='22023'; END IF;
      IF contract_version>=2 THEN
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
      entity := CASE WHEN contract_version>=2 THEN vn_durability.canonical_id(operation->'id')
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

  IF contract_version=3 THEN
    PERFORM vn_durability.validate_transition_after(state,payload);
    state.engine_state:=payload->'transition'->'after';
  END IF;

  -- Recheck after work too: a long blocked statement cannot persist authority
  -- it lost while executing. Row locks prevent a newer fence from intervening.
  IF state.lease_until <= clock_timestamp() THEN RAISE EXCEPTION 'lease_lost' USING ERRCODE='P0001'; END IF;
  UPDATE vn_durability.runs SET reserve=state.reserve,status=state.status,
    requires_reconciliation=state.requires_reconciliation,revision=state.revision+1,
    engine_state=state.engine_state WHERE id=run;
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

-- Reads and acknowledgements deliver already committed candidate events. They
-- require no economic lease and never renew one or authorize a new decision.
-- The caller must cap through_revision at its fully installed local state.
CREATE FUNCTION vn_durability.read_outbox(owner_id uuid, run uuid, through_revision bigint,
  max_events integer DEFAULT 50, max_bytes integer DEFAULT 65536)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE progress vn_durability.outbox_progress%ROWTYPE; item vn_durability.outbox_events%ROWTYPE;
        result jsonb; candidate jsonb; records jsonb:='[]'::jsonb; record jsonb; more boolean:=false;
BEGIN
  IF owner_id IS NULL OR run IS NULL OR through_revision IS NULL OR through_revision<1 OR
     max_events IS NULL OR max_events NOT BETWEEN 1 AND 100 OR
     max_bytes IS NULL OR max_bytes NOT BETWEEN 512 AND 65536 THEN
    RAISE EXCEPTION 'invalid_outbox_request' USING ERRCODE='22023';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM vn_durability.runs r WHERE r.id=run AND r.user_id=owner_id AND
                r.command_version=3 AND through_revision<=r.revision) THEN
    RAISE EXCEPTION 'outbox_unavailable' USING ERRCODE='P0001';
  END IF;
  SELECT * INTO progress FROM vn_durability.outbox_progress p WHERE p.run_id=run AND p.user_id=owner_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'outbox_unavailable' USING ERRCODE='P0001'; END IF;
  result:=jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,
    'through_revision',through_revision,'events',records,'has_more',false);
  -- Only indexed, bounded event rows are visited. Never materialize full
  -- command requests or an unbounded aggregate to build a delivery page.
  FOR item IN SELECT e.* FROM vn_durability.outbox_events e WHERE e.run_id=run AND e.user_id=owner_id
      AND (e.revision,e.event_index)>(progress.acknowledged_revision,progress.acknowledged_index)
      AND e.revision<=through_revision ORDER BY e.revision,e.event_index LIMIT max_events+1 LOOP
    IF jsonb_array_length(records)=max_events THEN more:=true; EXIT; END IF;
    record:=jsonb_build_object('owner_id',owner_id,'run_id',run,
      'event_id',run::text||':'||item.command_id::text||':'||item.event_index::text,
      'command_id',item.command_id,'revision',item.revision,'event_index',item.event_index,'event',item.event);
    candidate:=jsonb_set(result,'{events}',records||jsonb_build_array(record));
    -- Measure the whole response, including UTF-8 and metadata. false is one
    -- byte longer than true, so this remains safe when a later row sets more.
    IF octet_length(candidate::text)>max_bytes THEN
      IF records='[]'::jsonb THEN RAISE EXCEPTION 'outbox_event_exceeds_page' USING ERRCODE='22023'; END IF;
      more:=true; EXIT;
    END IF;
    records:=records||jsonb_build_array(record); result:=candidate;
  END LOOP;
  RETURN jsonb_set(result,'{has_more}',to_jsonb(more));
END $$;

CREATE FUNCTION vn_durability.acknowledge_event(owner_id uuid, run uuid, command_id uuid, event_index integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE progress vn_durability.outbox_progress%ROWTYPE; target vn_durability.outbox_events%ROWTYPE;
        next_event vn_durability.outbox_events%ROWTYPE;
BEGIN
  IF owner_id IS NULL OR run IS NULL OR command_id IS NULL OR event_index IS NULL OR
     event_index NOT BETWEEN 0 AND 1024 THEN
    RAISE EXCEPTION 'invalid_outbox_acknowledgement' USING ERRCODE='22023';
  END IF;
  SELECT * INTO progress FROM vn_durability.outbox_progress p
    WHERE p.run_id=run AND p.user_id=owner_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'outbox_unavailable' USING ERRCODE='P0001'; END IF;
  SELECT * INTO target FROM vn_durability.outbox_events e WHERE e.run_id=run AND e.user_id=owner_id AND
    e.command_id=acknowledge_event.command_id AND e.event_index=acknowledge_event.event_index;
  IF NOT FOUND THEN RAISE EXCEPTION 'outbox_event_unavailable' USING ERRCODE='P0001'; END IF;
  IF (target.revision,target.event_index)>(progress.acknowledged_revision,progress.acknowledged_index) THEN
    SELECT * INTO next_event FROM vn_durability.outbox_events e WHERE e.run_id=run AND e.user_id=owner_id AND
      (e.revision,e.event_index)>(progress.acknowledged_revision,progress.acknowledged_index)
      ORDER BY e.revision,e.event_index LIMIT 1;
    IF NOT FOUND OR (target.command_id,target.event_index) IS DISTINCT FROM (next_event.command_id,next_event.event_index) THEN
      RAISE EXCEPTION 'outbox_acknowledgement_out_of_order' USING ERRCODE='P0001';
    END IF;
    UPDATE vn_durability.outbox_progress p SET acknowledged_revision=target.revision,acknowledged_index=target.event_index
      WHERE p.run_id=run AND p.user_id=owner_id;
  END IF;
  -- Old acknowledgements remain idempotent after the contiguous prefix moves.
  -- Return the requested identity, not the latest checkpoint or a new event.
  RETURN jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,'command_id',target.command_id,
    'event_id',run::text||':'||target.command_id::text||':'||target.event_index::text,'event_index',target.event_index,
    'revision',target.revision,'acknowledged',true);
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
  vn_durability.read_outbox(uuid,uuid,bigint,integer,integer),
  vn_durability.acknowledge_event(uuid,uuid,uuid,integer),
  vn_durability.interrupt_expired(uuid,uuid,bigint,uuid) TO service_role;
COMMIT;
