-- DB-03A2D3B2B canonical fresh v5 component, OFFLINE REVIEW ONLY.
-- Not a complete production cutover or migration. No application loads this SQL.
-- build.py --check reproduces this artifact; only owned isolated tests apply it.
-- DB-03A2D3B2A isolated installer-boundary rehearsal ONLY.
-- Not a migration, production installation runner, or credential provisioner.
-- This transaction is combined with hash-pinned laboratory SQL by the tests.
BEGIN;
SET LOCAL lock_timeout='500ms';
SET LOCAL statement_timeout='15s';
DO $$
DECLARE installer pg_catalog.pg_roles%ROWTYPE;
BEGIN
 IF current_setting('dashboard.contract_rehearsal',true) IS DISTINCT FROM 'db03a1-isolated' THEN
  RAISE EXCEPTION 'isolated_installer_rehearsal_required';
 END IF;
 SELECT * INTO installer FROM pg_catalog.pg_roles WHERE rolname=current_user;
 IF current_setting('server_version_num')::integer NOT BETWEEN 170000 AND 179999 OR
    current_user<>'postgres' OR session_user<>'postgres' OR installer.rolsuper OR
    NOT installer.rolcreaterole OR NOT installer.rolcreatedb OR NOT installer.rolbypassrls OR
    NOT installer.rolinherit OR installer.rolreplication THEN
  RAISE EXCEPTION 'hosted_like_installer_required';
 END IF;
 IF NOT pg_catalog.has_database_privilege(current_user,current_database(),'CREATE') OR
    NOT pg_catalog.has_schema_privilege(current_user,'auth','USAGE') OR
    NOT pg_catalog.has_function_privilege(current_user,'auth.uid()','EXECUTE') OR
    NOT pg_catalog.has_column_privilege(current_user,'auth.users','id','REFERENCES') OR
    pg_catalog.has_schema_privilege(current_user,'auth','USAGE WITH GRANT OPTION') OR
    pg_catalog.has_function_privilege(current_user,'auth.uid()','EXECUTE WITH GRANT OPTION') OR
    pg_catalog.has_column_privilege(current_user,'auth.users','id','REFERENCES WITH GRANT OPTION') THEN
  RAISE EXCEPTION 'measured_auth_dependency_permissions_required';
 END IF;
 IF EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname IN ('vn_contract_owner','vn_economic','vn_relay')) OR
    EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname IN
      ('vn_identity','vn_durability','vn_projection','vn_read')) THEN
  RAISE EXCEPTION 'fresh_installer_rehearsal_required';
 END IF;
 IF (SELECT count(*) FROM pg_catalog.pg_roles WHERE rolname IN
      ('anon','authenticated','service_role','authenticator'))<>4 OR
    EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname IN
      ('anon','authenticated','service_role','authenticator') AND
      (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication OR
       EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members m WHERE m.member=r.oid AND m.admin_option))) THEN
  RAISE EXCEPTION 'api_role_authority_requires_review';
 END IF;
END $$;

SET LOCAL createrole_self_grant='';
CREATE ROLE vn_contract_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
 NOINHERIT NOREPLICATION NOBYPASSRLS;
-- PostgreSQL 17 creator ADMIN membership does not imply SET or inheritance.
-- Explicitly permit installation without inheriting the private owner by default.
-- Preserve the bootstrap-granted ADMIN-only row; a separate self-granted row
-- enables SET. Granting ADMIN back to one's own grantor is rejected by PG17.
GRANT vn_contract_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;

-- Keep the privileged identity bridge owned by the installer, in a schema the
-- private owner cannot CREATE in. No arguments, dynamic SQL or custom claim parser.
CREATE SCHEMA vn_identity AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA vn_identity FROM PUBLIC,anon,authenticated,service_role,authenticator;
CREATE FUNCTION vn_identity.owner_id() RETURNS uuid
 LANGUAGE sql STABLE SECURITY DEFINER
 SET search_path=pg_catalog,pg_temp AS $$ SELECT auth.uid() $$;
REVOKE ALL ON FUNCTION vn_identity.owner_id()
 FROM PUBLIC,anon,authenticated,service_role,authenticator;
GRANT USAGE ON SCHEMA vn_identity TO vn_contract_owner;
GRANT EXECUTE ON FUNCTION vn_identity.owner_id() TO vn_contract_owner;

DO $$
DECLARE owner_role oid:='vn_contract_owner'::regrole; installer_role oid:='postgres'::regrole;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE oid=owner_role AND
      NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND
      NOT rolinherit AND NOT rolreplication AND NOT rolbypassrls) OR
    NOT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname='vn_identity' AND nspowner=installer_role) OR
    NOT EXISTS(SELECT 1 FROM pg_catalog.pg_proc WHERE oid='vn_identity.owner_id()'::regprocedure AND
      proowner=installer_role AND prosecdef AND provolatile='s' AND pronargs=0 AND
      proconfig=ARRAY['search_path=pg_catalog, pg_temp']) OR
    EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members
   WHERE (member=owner_role) OR (roleid=owner_role AND
     (member<>installer_role OR inherit_option OR
      NOT ((grantor=10 AND admin_option AND NOT set_option) OR
           (grantor=installer_role AND NOT admin_option AND set_option))))) OR
    (SELECT count(*) FROM pg_catalog.pg_auth_members WHERE roleid=owner_role)<>2 OR
    NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE roleid=owner_role AND
      member=installer_role AND grantor=10 AND admin_option AND NOT set_option AND NOT inherit_option) OR
    NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE roleid=owner_role AND
      member=installer_role AND grantor=installer_role AND NOT admin_option AND set_option AND NOT inherit_option) OR
    pg_catalog.has_schema_privilege(owner_role,'auth','USAGE') OR
    pg_catalog.has_function_privilege(owner_role,'auth.uid()','EXECUTE') OR
    pg_catalog.has_column_privilege(owner_role,'auth.users','id','REFERENCES') OR
    pg_catalog.has_schema_privilege(owner_role,'vn_identity','CREATE') OR
    NOT pg_catalog.has_function_privilege(owner_role,'vn_identity.owner_id()','EXECUTE') OR
    EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname IN
      ('anon','authenticated','service_role','authenticator') AND
      (pg_catalog.pg_has_role(r.oid,owner_role,'SET') OR
       pg_catalog.pg_has_role(r.oid,owner_role,'USAGE') OR
       pg_catalog.has_schema_privilege(r.oid,'vn_identity','USAGE') OR
       pg_catalog.has_function_privilege(r.oid,'vn_identity.owner_id()','EXECUTE'))) OR
    EXISTS(SELECT 1 FROM pg_catalog.pg_proc p,
      LATERAL pg_catalog.aclexplode(p.proacl) a WHERE p.oid='vn_identity.owner_id()'::regprocedure
      AND (a.grantee NOT IN (owner_role,installer_role) OR a.is_grantable)) THEN
  RAISE EXCEPTION 'installer_boundary_postcondition_failed';
 END IF;
END $$;

-- Capability roles are inert: no login, authenticator grant, or credential.
CREATE ROLE vn_economic NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
CREATE ROLE vn_relay NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;

CREATE SCHEMA vn_durability AUTHORIZATION vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
GRANT USAGE,CREATE ON SCHEMA vn_durability TO postgres;
-- Schema-specific defaults cannot subtract the global PUBLIC EXECUTE default.
-- This changes only the dedicated fixture owner's defaults, never client roles.
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

CREATE DOMAIN vn_durability.balance AS numeric
  CHECK (VALUE >= 0 AND VALUE <= 1e36 AND scale(VALUE) <= 36);

RESET ROLE;
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
  command_version smallint NOT NULL CHECK (command_version=5),
  engine_state jsonb,
  initial_cash vn_durability.balance NOT NULL CHECK (initial_cash > 0),
  reserve vn_durability.balance NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (id, user_id)
);

ALTER TABLE vn_durability.runs OWNER TO vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
REVOKE USAGE,CREATE ON SCHEMA vn_durability FROM postgres;
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

-- The command journal is immutable. Provider-bound candidate events are separately
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

CREATE FUNCTION vn_durability.record_restart_lineage(owner_id uuid, run uuid, child uuid, value jsonb)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE state vn_durability.runs%ROWTYPE; ordinal integer; source uuid; iteration text; expected jsonb;
BEGIN
  SELECT * INTO state FROM vn_durability.runs WHERE id=run AND user_id=owner_id;
  IF NOT FOUND OR state.command_version NOT IN (4,5) OR
     state.engine_state->'engine'->'lifecycle'->'restart_required' IS DISTINCT FROM 'true'::jsonb OR
     state.engine_state->'engine'->'cohort'->>'phase' IS DISTINCT FROM 'aborted' THEN
    RAISE EXCEPTION 'restart_lineage_unavailable' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.exact_keys(value,ARRAY['version','child_id','strategy','operation','source_iteration_id',
    'offspring_index','sources','distribution_id']);
  ordinal:=vn_durability.rehearsal_integer(value->'offspring_index',0,7);
  source:=vn_durability.canonical_id(state.engine_state->'engine'->'members'->ordinal->'id');
  iteration:=state.engine_state->'engine'->'cohort'->>'iteration_id';
  expected:=jsonb_build_object('version',2,'child_id',child,'strategy',state.config->'rehearsal'->>'strategy',
    'operation','restart_clone','source_iteration_id',iteration,'offspring_index',ordinal,'distribution_id',NULL,
    'sources',jsonb_build_array(jsonb_build_object('role','clone_source','source_id',source,'ordinal',0),
                               jsonb_build_object('role','asset_template','source_id',source,'ordinal',0)));
  IF value IS DISTINCT FROM expected OR source=child OR NOT EXISTS(SELECT 1 FROM vn_durability.accounts
      WHERE run_id=run AND user_id=owner_id AND id=source AND retired) THEN
    RAISE EXCEPTION 'invalid_restart_lineage' USING ERRCODE='22023';
  END IF;
  INSERT INTO vn_durability.account_lineage VALUES(run,owner_id,child,value->>'strategy','restart_clone',iteration,ordinal,NULL,value);
  INSERT INTO vn_durability.lineage_sources VALUES(run,owner_id,child,'clone_source',source,0),
                                                 (run,owner_id,child,'asset_template',source,0);
END $$;

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
    WHEN 'ExactMarkColonyConfig' THEN RETURN ARRAY['available_assets','enabled_genes','gene_overrides','max_lifespan_ticks','mutation_rate','reproduction_interval','strategy_profile'];
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
     ((CASE WHEN descriptor->>'type'='object' THEN descriptor->>'class' ELSE descriptor->>'type' END) IS DISTINCT FROM required AND
       (required<>'ColonyConfig' OR descriptor->>'type' IS DISTINCT FROM 'object' OR descriptor->>'class' IS DISTINCT FROM 'ExactMarkColonyConfig')) THEN
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

CREATE FUNCTION vn_durability.lifecycle_config(configuration jsonb) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE cfg jsonb; initial_amount numeric; seed_amount numeric; policy jsonb;
BEGIN
  PERFORM vn_durability.exact_keys(configuration,ARRAY['durability_contract_version','execution','rehearsal']);
  cfg:=configuration->'rehearsal';
  PERFORM vn_durability.exact_keys(cfg,ARRAY['profile','strategy','asset','initial_cash','seed_capital',
    'search_seed','execution','population','horizon_seconds','candle_seconds','max_generations','max_positions','code_version','source','lifecycle_policy']);
  IF configuration->'durability_contract_version'<>'4'::jsonb OR
     cfg->>'profile' IS DISTINCT FROM 'ema-baseline-exact-lifecycle-v1' OR
     cfg->>'code_version' IS DISTINCT FROM 'bounded-exact-lifecycle-v1' OR
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
  policy:=cfg->'lifecycle_policy';
  PERFORM vn_durability.exact_keys(policy,ARRAY['version','account_loss_bps','death_drawdown_bps','max_lifespan_seconds']);
  IF policy->>'version' IS DISTINCT FROM 'exact-common-cohort-lifecycle-v1' OR
     jsonb_typeof(policy->'account_loss_bps') IS DISTINCT FROM 'string' OR
     policy->>'account_loss_bps' !~ '^[1-9][0-9]{0,4}$' OR
     (policy->>'account_loss_bps')::integer NOT BETWEEN 1 AND 10000 OR
     policy->'death_drawdown_bps' IS DISTINCT FROM '"2000"'::jsonb OR
     policy->'max_lifespan_seconds' IS DISTINCT FROM '0'::jsonb THEN
    RAISE EXCEPTION 'invalid_lifecycle_policy' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.execution_policy(cfg->'execution');
END $$;

CREATE FUNCTION vn_durability.lifecycle_optimizer_view(
  value jsonb, evidence jsonb, paths jsonb, budget jsonb, depth integer DEFAULT 0)
RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE visits integer:=(budget->>'visits')::integer+1;
  bytes integer:=(budget->>'bytes')::integer;
  tag text; label text; member jsonb; pair jsonb; result jsonb; nested jsonb;
  path text[]; source jsonb;
BEGIN
  IF value IS NULL THEN RAISE EXCEPTION 'missing_optimizer_audit_value' USING ERRCODE='22023'; END IF;
  bytes:=bytes+CASE WHEN jsonb_typeof(value)='string' THEN octet_length(value#>>'{}')+8 ELSE 16 END;
  IF depth>96 OR visits>100000 OR bytes>1048576 THEN
    RAISE EXCEPTION 'optimizer_audit_expansion_capacity' USING ERRCODE='22023';
  END IF;
  budget:=jsonb_build_object('visits',visits,'bytes',bytes);
  IF jsonb_typeof(value) NOT IN ('array','object') THEN
    RETURN budget||jsonb_build_object('value',value);
  END IF;
  IF jsonb_typeof(value)='array' THEN
    result:='[]'::jsonb;
    FOR member IN SELECT v FROM jsonb_array_elements(value) q(v) LOOP
      nested:=vn_durability.lifecycle_optimizer_view(member,evidence,paths,budget,depth+1);
      budget:=nested-'value'; result:=result||jsonb_build_array(nested->'value');
    END LOOP;
    RETURN budget||jsonb_build_object('value',result);
  END IF;
  IF value ? 'ref' THEN
    IF NOT paths ? (value->>'ref') THEN
      RAISE EXCEPTION 'missing_optimizer_audit_reference' USING ERRCODE='22023';
    END IF;
    SELECT array_agg(v ORDER BY ordinal) INTO path
      FROM jsonb_array_elements_text(paths->(value->>'ref')) WITH ORDINALITY q(v,ordinal);
    source:=evidence #> coalesce(path,ARRAY[]::text[]);
    IF source IS NULL THEN RAISE EXCEPTION 'missing_optimizer_audit_reference' USING ERRCODE='22023'; END IF;
    RETURN vn_durability.lifecycle_optimizer_view(source,evidence,paths,budget,depth+1);
  END IF;
  tag:=value->>'type';
  IF tag='integer' THEN
    RETURN budget||jsonb_build_object('value',to_jsonb(vn_durability.optimizer_decimal(value)));
  ELSIF tag IN ('float','numpy.float64') THEN
    RETURN budget||jsonb_build_object('value',jsonb_build_object('float64',value->'hex'));
  ELSIF tag IN ('tuple','list') THEN
    result:='[]'::jsonb;
    FOR member IN SELECT v FROM jsonb_array_elements(value->'items') q(v) LOOP
      nested:=vn_durability.lifecycle_optimizer_view(member,evidence,paths,budget,depth+1);
      budget:=nested-'value'; result:=result||jsonb_build_array(nested->'value');
    END LOOP;
  ELSIF tag='map' THEN
    result:='{}'::jsonb;
    FOR pair IN SELECT v FROM jsonb_array_elements(value->'entries') q(v) LOOP
      nested:=vn_durability.lifecycle_optimizer_view(pair->0,evidence,paths,budget,depth+1);
      budget:=nested-'value'; label:=pair->>0;
      nested:=vn_durability.lifecycle_optimizer_view(pair->1,evidence,paths,budget,depth+1);
      budget:=nested-'value'; result:=result||jsonb_build_object(label,nested->'value');
    END LOOP;
  ELSE
    -- Object fields become primitive maps. Reviewed array/RNG/history records
    -- remain descriptive maps, with their wire node marker removed.
    result:='{}'::jsonb;
    FOR label,member IN SELECT key,v FROM jsonb_each(
        CASE WHEN tag='object' THEN value->'fields' ELSE value-'node' END) q(key,v) LOOP
      nested:=vn_durability.lifecycle_optimizer_view(to_jsonb(label),evidence,paths,budget,depth+1);
      budget:=nested-'value';
      nested:=vn_durability.lifecycle_optimizer_view(member,evidence,paths,budget,depth+1);
      budget:=nested-'value'; result:=result||jsonb_build_object(label,nested->'value');
    END LOOP;
  END IF;
  RETURN budget||jsonb_build_object('value',result);
END $$;

CREATE FUNCTION vn_durability.lifecycle_optimizer_views(evidence jsonb)
RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE paths jsonb; visits bigint; too_deep boolean; nested jsonb; strategy jsonb;
  result jsonb; budget jsonb:='{"visits":0,"bytes":0}'::jsonb;
BEGIN
  IF evidence IS NULL OR jsonb_typeof(evidence) IS DISTINCT FROM 'object' OR
      octet_length(evidence::text)>196608 THEN
    RAISE EXCEPTION 'optimizer_audit_input_capacity' USING ERRCODE='22023';
  END IF;
  -- Index paths, not full nodes: storing a whole nested node at every level
  -- would multiply memory even before expanding any shared reference.
  WITH RECURSIVE walk(value,path,depth) AS (
    SELECT evidence,ARRAY[]::text[],0
    UNION ALL
    SELECT child.value,walk.path||child.key,walk.depth+1
      FROM walk CROSS JOIN LATERAL (
        SELECT key,value FROM jsonb_each(CASE WHEN jsonb_typeof(walk.value)='object'
                                                   THEN walk.value ELSE '{}'::jsonb END)
        UNION ALL
        SELECT (ordinal-1)::text,value FROM jsonb_array_elements(
          CASE WHEN jsonb_typeof(walk.value)='array' THEN walk.value ELSE '[]'::jsonb END)
          WITH ORDINALITY q(value,ordinal)
      ) child WHERE walk.depth<256
  )
  SELECT count(*),bool_or(depth=256 AND jsonb_typeof(value) IN ('object','array')),
      coalesce(jsonb_object_agg(value->>'node',to_jsonb(path)) FILTER(
        WHERE jsonb_typeof(value)='object' AND value ? 'node'),'{}'::jsonb)
    INTO visits,too_deep,paths FROM walk;
  IF visits>100000 OR coalesce(too_deep,false) THEN
    RAISE EXCEPTION 'optimizer_audit_index_capacity' USING ERRCODE='22023';
  END IF;
  nested:=vn_durability.lifecycle_optimizer_view(evidence->'strategy',evidence,paths,budget);
  strategy:=nested->'value'; budget:=nested-'value';
  nested:=vn_durability.lifecycle_optimizer_view(evidence->'cohort',evidence,paths,budget);
  result:=jsonb_build_object('strategy',strategy,'cohort',nested->'value');
  IF octet_length(result::text)>1048576 THEN
    RAISE EXCEPTION 'optimizer_audit_output_capacity' USING ERRCODE='22023';
  END IF;
  RETURN result;
END $$;

CREATE FUNCTION vn_durability.lifecycle_optimizer_mirror(engine jsonb)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE views jsonb; strategy jsonb; cohort jsonb; mirror jsonb:=engine->'cohort';
  results jsonb; genomes jsonb; evaluation_ids jsonb; row jsonb; member jsonb;
  expected jsonb; actual jsonb; label text; gene jsonb; identity text;
  members text[]; recorded text[]; keys text[]; ordinal bigint;
BEGIN
  views:=vn_durability.lifecycle_optimizer_views(engine->'optimizer');
  strategy:=views->'strategy'; cohort:=views->'cohort';
  FOREACH label IN ARRAY ARRAY['iteration_id','phase','horizon_seconds','started_at','ends_at',
                               'completed_at','abort_reason','member_ids'] LOOP
    IF cohort->label IS DISTINCT FROM mirror->label THEN
      RAISE EXCEPTION 'optimizer_cohort_mirror_mismatch' USING ERRCODE='22023';
    END IF;
  END LOOP;
  IF strategy->'_search_epoch' IS DISTINCT FROM engine->'lifecycle'->'search_epoch' THEN
    RAISE EXCEPTION 'optimizer_search_epoch_mismatch' USING ERRCODE='22023';
  END IF;
  results:=cohort->'_evaluations'; genomes:=cohort->'_genomes'; evaluation_ids:=cohort->'_evaluation_ids';
  IF jsonb_typeof(results) IS DISTINCT FROM 'object' OR jsonb_typeof(genomes) IS DISTINCT FROM 'object' OR
     jsonb_typeof(evaluation_ids) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'optimizer_cohort_maps_missing' USING ERRCODE='22023';
  END IF;
  SELECT coalesce(array_agg(v ORDER BY v),ARRAY[]::text[]) INTO members
    FROM jsonb_array_elements_text(mirror->'member_ids') q(v);
  SELECT coalesce(array_agg(key ORDER BY key),ARRAY[]::text[]) INTO keys FROM jsonb_object_keys(genomes) q(key);
  IF keys IS DISTINCT FROM members THEN RAISE EXCEPTION 'optimizer_genome_membership_mismatch' USING ERRCODE='22023'; END IF;
  SELECT coalesce(array_agg(key ORDER BY key),ARRAY[]::text[]) INTO keys FROM jsonb_object_keys(evaluation_ids) q(key);
  IF keys IS DISTINCT FROM members THEN RAISE EXCEPTION 'optimizer_evaluation_membership_mismatch' USING ERRCODE='22023'; END IF;
  SELECT coalesce(array_agg(v->>'probe_id' ORDER BY v->>'probe_id'),ARRAY[]::text[]) INTO recorded
    FROM jsonb_array_elements(mirror->'evaluations') q(v);
  SELECT coalesce(array_agg(key ORDER BY key),ARRAY[]::text[]) INTO keys FROM jsonb_object_keys(results) q(key);
  IF keys IS DISTINCT FROM recorded THEN RAISE EXCEPTION 'optimizer_frozen_membership_mismatch' USING ERRCODE='22023'; END IF;
  FOR row IN SELECT v FROM jsonb_array_elements(mirror->'evaluations') q(v) LOOP
    identity:=row->>'probe_id'; actual:=results->identity;
    IF actual-'_genome' IS DISTINCT FROM row OR actual->'_genome' IS DISTINCT FROM genomes->identity THEN
      RAISE EXCEPTION 'optimizer_frozen_result_mismatch' USING ERRCODE='22023';
    END IF;
  END LOOP;
  FOR member,ordinal IN SELECT q.v,q.ordinal-1 FROM jsonb_array_elements(engine->'members') WITH ORDINALITY q(v,ordinal) LOOP
    identity:=member->>'id'; expected:='{}'::jsonb;
    FOR label,gene IN SELECT key,value FROM jsonb_each(member->'genome') LOOP
      expected:=expected||jsonb_build_object(label,CASE WHEN jsonb_typeof(gene)='string'
                    THEN jsonb_build_object('float64',gene) ELSE gene END);
    END LOOP;
    IF genomes->identity IS DISTINCT FROM expected OR
       evaluation_ids->identity IS DISTINCT FROM to_jsonb((mirror->>'iteration_id')||':'||ordinal::text) OR
       mirror->'member_ids'->ordinal::integer IS DISTINCT FROM to_jsonb(identity) THEN
      RAISE EXCEPTION 'optimizer_bound_phenotype_mismatch' USING ERRCODE='22023';
    END IF;
  END LOOP;
END $$;

CREATE FUNCTION vn_durability.lifecycle_amount(value jsonb, digits integer DEFAULT 36) RETURNS numeric
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE units numeric;
BEGIN
  units:=vn_durability.decimal_units(value,digits);
  IF value#>>'{}' IS DISTINCT FROM vn_durability.decimal_text(units,digits) THEN
    RAISE EXCEPTION 'noncanonical_lifecycle_amount' USING ERRCODE='22023';
  END IF;
  RETURN units;
END $$;

CREATE FUNCTION vn_durability.lifecycle_equity(run uuid, reserve numeric, price jsonb) RETURNS numeric
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE result numeric; reference numeric;
BEGIN
  SELECT reserve*1e36+coalesce(sum(cash*1e36),0) INTO result FROM vn_durability.accounts WHERE run_id=run;
  IF EXISTS(SELECT 1 FROM vn_durability.positions WHERE run_id=run AND NOT closed) THEN
    reference:=vn_durability.lifecycle_amount(price,18);
    IF reference<=0 THEN RAISE EXCEPTION 'lifecycle_mark_required' USING ERRCODE='22023'; END IF;
    SELECT result+sum(quantity*1e18*reference) INTO result FROM vn_durability.positions WHERE run_id=run AND NOT closed;
  END IF;
  IF result<0 OR result>1e72 THEN RAISE EXCEPTION 'invalid_lifecycle_equity' USING ERRCODE='22023'; END IF;
  RETURN result;
END $$;

CREATE FUNCTION vn_durability.lifecycle_member_metrics(state vn_durability.runs,payload jsonb,member jsonb,prior jsonb)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE identity uuid:=vn_durability.canonical_id(member->'id'); operation jsonb; owned uuid;
        cash numeric; quantity numeric; reference numeric:=0; equity numeric; peak numeric; numerator numeric; denominator numeric;
        terminal_cash numeric; common numeric; eligible boolean:=false; retired boolean:=false; terminal jsonb:=member->'terminal';
        stage integer:=0; kind text:=payload->'transition'->'evidence'->>'kind';
BEGIN
  IF prior IS NULL THEN
    IF member->>'peak_equity' IS DISTINCT FROM state.config->'rehearsal'->>'seed_capital' OR
       member->'max_drawdown' IS DISTINCT FROM '{"numerator":"0","denominator":"1"}'::jsonb OR
       member->'pending'<>'null'::jsonb OR terminal IS DISTINCT FROM 'null'::jsonb OR member->'num_trades'<>'0'::jsonb THEN
      RAISE EXCEPTION 'invalid_new_member_state' USING ERRCODE='22023';
    END IF;
    RETURN;
  END IF;
  IF member->'genome' IS DISTINCT FROM prior->'genome' OR member->'name' IS DISTINCT FROM prior->'name' OR
     (prior->'cursor'<>'null'::jsonb AND (member->'cursor'='null'::jsonb OR (member->>'cursor')::numeric<(prior->>'cursor')::numeric)) THEN
    RAISE EXCEPTION 'lifecycle_member_identity_changed' USING ERRCODE='22023';
  END IF;
  IF prior->'terminal'<>'null'::jsonb THEN
    IF member IS DISTINCT FROM prior THEN RAISE EXCEPTION 'terminal_member_changed' USING ERRCODE='22023'; END IF;
    RETURN;
  END IF;
  peak:=vn_durability.lifecycle_amount(prior->'peak_equity');
  numerator:=(prior->'max_drawdown'->>'numerator')::numeric;
  denominator:=(prior->'max_drawdown'->>'denominator')::numeric;
  SELECT vn_durability.lifecycle_amount(v->'cash') INTO cash
    FROM jsonb_array_elements(state.engine_state->'accounts') q(v) WHERE v->>'id'=identity::text;
  SELECT coalesce(sum(vn_durability.lifecycle_amount(v->'entry'->'quantity',18)),0) INTO quantity
    FROM jsonb_array_elements(state.engine_state->'positions') q(v) WHERE v->>'account_id'=identity::text AND v->'closed'='false'::jsonb;
  IF payload->'transition'->'after'->'engine'->'last_quote'<>'null'::jsonb THEN
    reference:=vn_durability.lifecycle_amount(payload->'transition'->'after'->'engine'->'last_quote'->'price',18);
  END IF;
  -- A synthetic first stage observes the protective reference mark, followed
  -- by every actual fill in order. Retirement never fabricates a zero-value
  -- death mark; terminal.cash freezes the exact amount transferred to reserve.
  FOR operation IN SELECT v FROM (SELECT NULL::jsonb AS v,0::bigint AS ordinal
      UNION ALL SELECT v,ordinal FROM jsonb_array_elements(payload->'operations') WITH ORDINALITY q(v,ordinal)) staged ORDER BY ordinal LOOP
    IF operation IS NOT NULL THEN
      IF operation->>'kind'='open' AND operation->>'account_id'=identity::text THEN
        cash:=cash-vn_durability.lifecycle_amount(operation->'notional')-vn_durability.lifecycle_amount(operation->'fee');
        quantity:=quantity+vn_durability.lifecycle_amount(operation->'quantity',18);
      ELSIF operation->>'kind'='close' THEN
        SELECT p.account_id INTO owned FROM vn_durability.positions p WHERE p.run_id=state.id AND p.id=vn_durability.canonical_id(operation->'id');
        IF owned<>identity THEN CONTINUE; END IF;
        cash:=cash+vn_durability.lifecycle_amount(operation->'proceeds')-vn_durability.lifecycle_amount(operation->'fee');
        quantity:=0;
      ELSIF operation->>'kind'='retire' AND operation->>'id'=identity::text THEN
        terminal_cash:=cash; retired:=true; CONTINUE;
      ELSE CONTINUE;
      END IF;
    ELSIF kind<>'protective' THEN CONTINUE;
    END IF;
    equity:=cash+quantity*reference; peak:=greatest(peak,equity);
    IF (peak-equity)*denominator>numerator*peak THEN numerator:=peak-equity; denominator:=peak; END IF;
    IF equity*10000<=peak*8000 THEN eligible:=true; END IF;
  END LOOP;
  common:=gcd(numerator,denominator);
  IF member->'max_drawdown'->>'numerator' IS DISTINCT FROM trunc(div(numerator,common),0)::text OR
     member->'max_drawdown'->>'denominator' IS DISTINCT FROM trunc(div(denominator,common),0)::text THEN
    RAISE EXCEPTION 'noncanonical_lifecycle_drawdown' USING ERRCODE='22023';
  END IF;
  IF peak<=0 OR member->>'peak_equity' IS DISTINCT FROM vn_durability.decimal_text(peak,36) OR
     (member->'max_drawdown'->>'numerator')::numeric*denominator<>(member->'max_drawdown'->>'denominator')::numeric*numerator THEN
    RAISE EXCEPTION 'lifecycle_member_metrics_mismatch' USING ERRCODE='22023';
  END IF;
  IF terminal<>'null'::jsonb THEN
    PERFORM vn_durability.exact_keys(terminal,ARRAY['reason','at','cash']);
    PERFORM vn_durability.lifecycle_amount(terminal->'cash');
    PERFORM vn_durability.rehearsal_integer(terminal->'at',0,253402300799);
    IF terminal->>'reason' IS DISTINCT FROM 'drawdown' OR NOT retired OR NOT eligible OR quantity<>0 OR
       terminal->>'cash' IS DISTINCT FROM vn_durability.decimal_text(terminal_cash,36) OR
       terminal->'at' IS DISTINCT FROM payload->'transition'->'evidence'->'observation'->'timestamp' OR
       member->'pending' IS DISTINCT FROM 'null'::jsonb THEN
      RAISE EXCEPTION 'invalid_terminal_member' USING ERRCODE='22023';
    END IF;
  ELSIF retired OR eligible THEN RAISE EXCEPTION 'missing_terminal_member' USING ERRCODE='22023';
  END IF;
END $$;

CREATE FUNCTION vn_durability.lifecycle_cohort(state vn_durability.runs,value jsonb,generation integer)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE phase text; iteration text; member jsonb; member_ids uuid[]:=ARRAY[]::uuid[]; results uuid[]:=ARRAY[]::uuid[];
        result jsonb; identity uuid; ordinal integer; completed_count integer:=0; started numeric; ended numeric; completed numeric; terminated numeric;
BEGIN
  PERFORM vn_durability.exact_keys(value,ARRAY['policy','iteration_id','phase','member_ids','member_count',
    'completed_count','horizon_seconds','started_at','ends_at','completed_at','abort_reason','evaluations']);
  phase:=value->>'phase'; iteration:=state.id::text||':'||generation::text;
  IF value->'policy' IS DISTINCT FROM '{"version":"common-market-window-v1","horizon_unit":"market_minutes",
       "warmup":"all_candidates_ready","early_terminal":"freeze_cash_and_score_until_common_deadline",
       "interruptions":"abort_without_tell","deadline_mark":"first_valid_observation_at_or_after_deadline"}'::jsonb OR
     value->>'iteration_id' IS DISTINCT FROM iteration OR phase IS NULL OR phase NOT IN ('warming','evaluating','completed','aborted') OR
     value->'member_count' IS DISTINCT FROM '8'::jsonb OR jsonb_typeof(value->'member_ids') IS DISTINCT FROM 'array' OR
     jsonb_array_length(value->'member_ids')<>8 OR jsonb_typeof(value->'evaluations') IS DISTINCT FROM 'array' OR
     jsonb_array_length(value->'evaluations')>8 OR vn_durability.rehearsal_view_time(value->'horizon_seconds')<>3600 THEN
    RAISE EXCEPTION 'invalid_lifecycle_cohort' USING ERRCODE='22023';
  END IF;
  FOR member IN SELECT v FROM jsonb_array_elements(value->'member_ids') q(v) LOOP
    identity:=vn_durability.canonical_id(member);
    IF identity=ANY(member_ids) OR NOT EXISTS(SELECT 1 FROM vn_durability.accounts
      WHERE run_id=state.id AND user_id=state.user_id AND id=identity) THEN
      RAISE EXCEPTION 'invalid_lifecycle_cohort_member' USING ERRCODE='22023';
    END IF;
    member_ids:=array_append(member_ids,identity);
  END LOOP;
  IF value->'started_at'<>'null'::jsonb THEN started:=vn_durability.rehearsal_view_time(value->'started_at'); END IF;
  IF value->'ends_at'<>'null'::jsonb THEN ended:=vn_durability.rehearsal_view_time(value->'ends_at'); END IF;
  IF value->'completed_at'<>'null'::jsonb THEN completed:=vn_durability.rehearsal_view_time(value->'completed_at'); END IF;
  IF (started IS NULL)<>(ended IS NULL) OR (started IS NOT NULL AND ended<>started+3600) OR
     (phase='warming' AND (started IS NOT NULL OR completed IS NOT NULL OR value->'evaluations'<>'[]'::jsonb)) OR
     (phase='evaluating' AND (started IS NULL OR completed IS NOT NULL)) OR
     (phase='completed' AND (started IS NULL OR completed IS NULL OR completed<ended)) OR
     (phase='aborted' AND (completed IS NULL OR (started IS NOT NULL AND completed<started))) OR
     (phase IN ('completed','aborted') AND jsonb_array_length(value->'evaluations')<>8) OR
     (phase<>'aborted' AND value->'abort_reason' IS DISTINCT FROM 'null'::jsonb) OR
     (phase='aborted' AND (value->>'abort_reason' IS NULL OR value->>'abort_reason' NOT IN ('paused','stopped','risk_halted'))) THEN
    RAISE EXCEPTION 'invalid_lifecycle_cohort_time' USING ERRCODE='22023';
  END IF;
  ordinal:=-1;
  FOR result IN SELECT v FROM jsonb_array_elements(value->'evaluations') q(v) LOOP
    PERFORM vn_durability.exact_keys(result,ARRAY['probe_id','evaluation_id','iteration_id','fitness','roi','num_trades',
      'reason','status','cohort_complete','window_started_at','window_ends_at','terminated_at']);
    identity:=vn_durability.canonical_id(result->'probe_id');
    IF NOT identity=ANY(member_ids) OR identity=ANY(results) OR array_position(member_ids,identity)-1<=ordinal THEN
      RAISE EXCEPTION 'invalid_lifecycle_result_order' USING ERRCODE='22023';
    END IF;
    ordinal:=array_position(member_ids,identity)-1; results:=array_append(results,identity);
    terminated:=vn_durability.rehearsal_view_time(result->'terminated_at');
    IF result->>'evaluation_id' IS DISTINCT FROM iteration||':'||ordinal::text OR result->>'iteration_id' IS DISTINCT FROM iteration OR
       result->'window_started_at' IS DISTINCT FROM value->'started_at' OR result->'window_ends_at' IS DISTINCT FROM value->'ends_at' OR
       result->'cohort_complete' IS DISTINCT FROM to_jsonb(phase='completed') OR
       (started IS NOT NULL AND terminated<started) OR (completed IS NOT NULL AND terminated>completed) THEN
      RAISE EXCEPTION 'invalid_lifecycle_result_identity' USING ERRCODE='22023';
    END IF;
    IF result->>'status'='completed' THEN
      completed_count:=completed_count+1;
      IF NOT EXISTS(SELECT 1 FROM vn_durability.accounts WHERE run_id=state.id AND id=identity AND retired) THEN
        RAISE EXCEPTION 'completed_member_not_retired' USING ERRCODE='22023';
      END IF;
      IF started IS NULL OR result->>'reason' IS NULL OR result->>'reason' NOT IN ('drawdown','window_complete') OR
         (result->>'reason'='window_complete' AND (phase<>'completed' OR terminated<>completed)) OR
         vn_durability.rehearsal_integer(result->'num_trades',0,64)<>(SELECT count(*) FROM vn_durability.positions
           WHERE run_id=state.id AND account_id=identity AND closed) THEN
        RAISE EXCEPTION 'invalid_lifecycle_completed_result' USING ERRCODE='22023';
      END IF;
      PERFORM vn_durability.exact_keys(result->'fitness',ARRAY['float64']);
      PERFORM vn_durability.exact_keys(result->'roi',ARRAY['float64']);
      PERFORM vn_durability.rehearsal_hex(result->'fitness'->'float64');
      PERFORM vn_durability.rehearsal_hex(result->'roi'->'float64');
    ELSIF result->>'status'='aborted' THEN
      IF phase<>'aborted' OR result->'reason' IS DISTINCT FROM value->'abort_reason' OR terminated<>completed OR
         result->'fitness' IS DISTINCT FROM 'null'::jsonb OR result->'roi' IS DISTINCT FROM 'null'::jsonb OR
         result->'num_trades' IS DISTINCT FROM '0'::jsonb THEN
        RAISE EXCEPTION 'invalid_lifecycle_aborted_result' USING ERRCODE='22023';
      END IF;
    ELSE RAISE EXCEPTION 'invalid_lifecycle_result_status' USING ERRCODE='22023';
    END IF;
  END LOOP;
  IF value->'completed_count' IS DISTINCT FROM to_jsonb(completed_count) OR (phase='completed' AND completed_count<>8) THEN
    RAISE EXCEPTION 'invalid_lifecycle_completed_count' USING ERRCODE='22023';
  END IF;
END $$;

CREATE FUNCTION vn_durability.lifecycle_state(state vn_durability.runs,payload jsonb,first_trip numeric)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE after_state jsonb:=payload->'transition'->'after'; engine jsonb:=after_state->'engine';
        lifecycle jsonb:=engine->'lifecycle'; risk jsonb:=lifecycle->'risk';
        previous jsonb:=state.engine_state->'engine'->'lifecycle'; prior_risk jsonb:=previous->'risk';
        control jsonb:=payload->'transition'->'evidence'->'control'; kind text:=payload->'transition'->'evidence'->>'kind';
        at_time numeric:=extract(epoch FROM (payload->'transition'->'evidence'->'inputs'->>'event_at')::timestamptz);
        equity numeric; baseline numeric; bps numeric; action text; last jsonb; generation integer;
        changed_generation boolean; restarted boolean; expected_ids jsonb; item jsonb;
BEGIN
  generation:=(engine->>'generation')::integer;
  changed_generation:=state.engine_state IS NOT NULL AND generation>(state.engine_state->'engine'->>'generation')::integer;
  restarted:=changed_generation AND previous->'restart_required'='true'::jsonb;
  action:=control->>'action';
  PERFORM vn_durability.exact_keys(lifecycle,ARRAY['search_epoch','restart_required','signals_after','last_control_at','risk']);
  PERFORM vn_durability.exact_keys(risk,ARRAY['active','baseline_equity','observed_equity','observed_at',
    'trip_id','tripped_at','trip_equity','recovery_count','last_recovered_at']);
  PERFORM vn_durability.rehearsal_integer(lifecycle->'search_epoch',0,generation);
  PERFORM vn_durability.rehearsal_integer(risk->'recovery_count',0,100);
  IF jsonb_typeof(lifecycle->'restart_required') IS DISTINCT FROM 'boolean' OR
     jsonb_typeof(risk->'active') IS DISTINCT FROM 'boolean' OR
     risk->'baseline_equity' IS DISTINCT FROM state.config->'rehearsal'->'initial_cash' THEN
    RAISE EXCEPTION 'invalid_lifecycle_risk' USING ERRCODE='22023';
  END IF;
  FOREACH action IN ARRAY ARRAY['observed_at','tripped_at','last_recovered_at'] LOOP
    IF risk->action<>'null'::jsonb THEN PERFORM vn_durability.rehearsal_integer(risk->action,0,253402300799); END IF;
  END LOOP;
  FOREACH action IN ARRAY ARRAY['signals_after','last_control_at'] LOOP
    IF lifecycle->action<>'null'::jsonb THEN PERFORM vn_durability.rehearsal_integer(lifecycle->action,0,253402300799); END IF;
  END LOOP;
  action:=control->>'action'; baseline:=vn_durability.lifecycle_amount(risk->'baseline_equity');
  bps:=(state.config->'rehearsal'->'lifecycle_policy'->>'account_loss_bps')::numeric;
  PERFORM vn_durability.lifecycle_amount(risk->'observed_equity');
  equity:=vn_durability.lifecycle_equity(state.id,state.reserve,engine->'last_quote'->'price');
  IF risk->>'observed_equity' IS DISTINCT FROM vn_durability.decimal_text(equity,36) OR
     risk->'observed_at' IS DISTINCT FROM (CASE WHEN kind='control' AND action<>'recover' THEN prior_risk->'observed_at' ELSE to_jsonb(at_time)::jsonb END) THEN
    RAISE EXCEPTION 'lifecycle_observed_equity_mismatch' USING ERRCODE='22023';
  END IF;
  IF risk->'trip_id'='null'::jsonb THEN
    IF risk->'active'<>'false'::jsonb OR risk->'tripped_at'<>'null'::jsonb OR risk->'trip_equity'<>'null'::jsonb OR
       risk->'recovery_count'<>'0'::jsonb OR risk->'last_recovered_at'<>'null'::jsonb THEN
      RAISE EXCEPTION 'invalid_lifecycle_trip' USING ERRCODE='22023';
    END IF;
  ELSE
    PERFORM vn_durability.canonical_id(risk->'trip_id');
    IF vn_durability.lifecycle_amount(risk->'trip_equity')*10000>baseline*(10000-bps) THEN
      RAISE EXCEPTION 'invalid_lifecycle_trip_threshold' USING ERRCODE='22023';
    END IF;
    IF risk->'tripped_at'='null'::jsonb OR NOT engine->'used_ids' @> jsonb_build_array(risk->'trip_id') THEN
      RAISE EXCEPTION 'invalid_lifecycle_trip' USING ERRCODE='22023';
    END IF;
  END IF;
  IF first_trip IS NOT NULL THEN
    IF risk->'active'<>'true'::jsonb OR risk->'tripped_at' IS DISTINCT FROM to_jsonb(at_time) OR
       risk->>'trip_equity' IS DISTINCT FROM vn_durability.decimal_text(first_trip,36) OR
       (prior_risk IS NOT NULL AND risk->'trip_id'=prior_risk->'trip_id') OR after_state->>'status'<>'risk_halted' THEN
      RAISE EXCEPTION 'lifecycle_first_trip_mismatch' USING ERRCODE='22023';
    END IF;
  ELSIF previous IS NOT NULL THEN
    IF (risk)-ARRAY['active','observed_equity','observed_at','recovery_count','last_recovered_at'] IS DISTINCT FROM
       (prior_risk)-ARRAY['active','observed_equity','observed_at','recovery_count','last_recovered_at'] OR
       risk->'active' IS DISTINCT FROM (CASE WHEN action='recover' THEN 'false'::jsonb ELSE prior_risk->'active' END) THEN
      RAISE EXCEPTION 'lifecycle_latch_changed' USING ERRCODE='22023';
    END IF;
  END IF;
  IF risk->'active'='true'::jsonb AND EXISTS (SELECT 1 FROM jsonb_array_elements(engine->'members') q(v) WHERE v->'pending'->>'action'='entry') THEN
    RAISE EXCEPTION 'risk_halted_entry_intent' USING ERRCODE='22023';
  END IF;
  IF risk->'active'='true'::jsonb AND after_state->>'status' NOT IN ('risk_halted','stopped') OR
     after_state->>'status'='risk_halted' AND risk->'active'<>'true'::jsonb THEN
    RAISE EXCEPTION 'lifecycle_status_latch_mismatch' USING ERRCODE='22023';
  END IF;
  IF previous IS NULL THEN
    IF lifecycle IS DISTINCT FROM jsonb_build_object('search_epoch',0,'restart_required',false,'signals_after',NULL,'last_control_at',NULL,
      'risk',jsonb_build_object('active',false,'baseline_equity',state.config->'rehearsal'->>'initial_cash',
      'observed_equity',state.config->'rehearsal'->>'initial_cash','observed_at',at_time,'trip_id',NULL,'tripped_at',NULL,
      'trip_equity',NULL,'recovery_count',0,'last_recovered_at',NULL)) THEN
      RAISE EXCEPTION 'invalid_lifecycle_bootstrap' USING ERRCODE='22023';
    END IF;
  ELSE
    IF lifecycle->'search_epoch' IS DISTINCT FROM to_jsonb((previous->>'search_epoch')::integer+CASE WHEN restarted THEN 1 ELSE 0 END) OR
       lifecycle->'last_control_at' IS DISTINCT FROM (CASE WHEN kind='control' THEN to_jsonb(at_time) ELSE previous->'last_control_at' END) OR
       lifecycle->'signals_after' IS DISTINCT FROM (CASE WHEN action IN ('recover','resume') OR restarted THEN to_jsonb(at_time) ELSE previous->'signals_after' END) OR
       risk->'recovery_count' IS DISTINCT FROM to_jsonb((prior_risk->>'recovery_count')::integer+CASE WHEN action='recover' THEN 1 ELSE 0 END) OR
       risk->'last_recovered_at' IS DISTINCT FROM (CASE WHEN action='recover' THEN to_jsonb(at_time) ELSE prior_risk->'last_recovered_at' END) OR
       lifecycle->'restart_required' IS DISTINCT FROM (CASE WHEN restarted THEN 'false'::jsonb
         WHEN first_trip IS NOT NULL OR action IN ('pause','stop') THEN 'true'::jsonb ELSE previous->'restart_required' END) THEN
      RAISE EXCEPTION 'lifecycle_continuation_mismatch' USING ERRCODE='22023';
    END IF;
  END IF;
  PERFORM vn_durability.lifecycle_cohort(state,engine->'cohort',generation);
  SELECT jsonb_agg(v->'id' ORDER BY ordinal) INTO expected_ids FROM jsonb_array_elements(engine->'members') WITH ORDINALITY q(v,ordinal);
  IF engine->'cohort'->'member_ids' IS DISTINCT FROM expected_ids OR
     (engine->'cohort'->>'phase'='aborted') IS DISTINCT FROM (lifecycle->'restart_required'='true'::jsonb) THEN
    RAISE EXCEPTION 'lifecycle_cohort_binding_mismatch' USING ERRCODE='22023';
  END IF;
  last:=engine->'last_evaluation';
  IF last<>'null'::jsonb THEN
    PERFORM vn_durability.exact_keys(last,ARRAY['cohort','selection']);
    IF last->'cohort'->>'iteration_id' !~ ('^'||state.id::text||':[0-3]$') THEN
      RAISE EXCEPTION 'invalid_prior_lifecycle_evaluation' USING ERRCODE='22023';
    END IF;
    IF split_part(last->'cohort'->>'iteration_id',':',2)::integer>generation THEN
      RAISE EXCEPTION 'invalid_prior_lifecycle_evaluation' USING ERRCODE='22023';
    END IF;
    PERFORM vn_durability.lifecycle_cohort(state,last->'cohort',split_part(last->'cohort'->>'iteration_id',':',2)::integer);
    IF NOT ((last->'cohort'->>'phase'='aborted' AND last->'selection'='null'::jsonb) OR
            (last->'cohort'->>'phase'='completed' AND jsonb_typeof(last->'selection')='object' AND last->'selection'<>'{}'::jsonb)) THEN
      RAISE EXCEPTION 'invalid_lifecycle_selection' USING ERRCODE='22023';
    END IF;
  END IF;
END $$;

CREATE FUNCTION vn_durability.lifecycle_candles(prior jsonb,following jsonb,observation jsonb,ingest boolean)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE expected jsonb;
BEGIN
  IF NOT ingest OR observation->'candle_end'='null'::jsonb THEN
    IF following IS DISTINCT FROM prior THEN RAISE EXCEPTION 'lifecycle_history_changed' USING ERRCODE='22023'; END IF;
    RETURN;
  END IF;
  IF observation->'candle_end'=prior->'last_end' THEN
    IF observation->'candle_close' IS DISTINCT FROM prior->'closes'->-1 OR following IS DISTINCT FROM prior THEN
      RAISE EXCEPTION 'lifecycle_history_revision' USING ERRCODE='22023';
    END IF;
    RETURN;
  END IF;
  IF prior->'last_end'<>'null'::jsonb AND (observation->>'candle_end')::numeric<>(prior->>'last_end')::numeric+900 THEN
    RAISE EXCEPTION 'lifecycle_history_gap' USING ERRCODE='22023';
  END IF;
  SELECT jsonb_agg(v ORDER BY ordinal) INTO expected FROM
    jsonb_array_elements(prior->'closes'||jsonb_build_array(observation->'candle_close')) WITH ORDINALITY q(v,ordinal)
    WHERE ordinal>greatest(jsonb_array_length(prior->'closes')+1-64,0);
  IF following->'count' IS DISTINCT FROM to_jsonb((prior->>'count')::integer+1) OR
     following->'last_end' IS DISTINCT FROM observation->'candle_end' OR following->'closes' IS DISTINCT FROM expected OR
     following->'previous' IS DISTINCT FROM prior->'values' THEN
    RAISE EXCEPTION 'lifecycle_history_mismatch' USING ERRCODE='22023';
  END IF;
END $$;

CREATE FUNCTION vn_durability.lifecycle_cohort_continuation(
  state vn_durability.runs,payload jsonb,replacement boolean,restart boolean,
  newly_aborted boolean,ready boolean,moment numeric)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE prior jsonb:=state.engine_state->'engine';
  engine jsonb:=payload->'transition'->'after'->'engine';
  evidence jsonb:=payload->'transition'->'evidence'; kind text:=evidence->>'kind';
  control text:=evidence->'control'->>'action'; old_cohort jsonb:=prior->'cohort';
  cohort jsonb:=engine->'cohort'; audit jsonb; expected jsonb; old_result jsonb;
  result jsonb; old_member jsonb; member jsonb; identity text; label text;
  before_views jsonb; after_views jsonb; old_strategy jsonb; new_strategy jsonb;
  cause text; started boolean; closed boolean; new_candle boolean; fresh_pending boolean;
BEGIN
  IF state.engine_state IS NULL THEN RETURN; END IF;
  IF engine->'lifecycle'->'risk'->'trip_id' IS DISTINCT FROM prior->'lifecycle'->'risk'->'trip_id' THEN
    cause:='risk_halted';
  ELSIF kind='control' AND control IN ('pause','stop') THEN
    cause:=CASE control WHEN 'pause' THEN 'paused' ELSE 'stopped' END;
  END IF;
  IF newly_aborted IS DISTINCT FROM (old_cohort->>'phase' IN ('warming','evaluating') AND cause IS NOT NULL) THEN
    RAISE EXCEPTION 'lifecycle_abort_cause_mismatch' USING ERRCODE='22023';
  END IF;
  IF newly_aborted THEN
    IF cohort->>'phase' IS DISTINCT FROM 'aborted' OR cohort->>'abort_reason' IS DISTINCT FROM cause OR
       cohort->'started_at' IS DISTINCT FROM old_cohort->'started_at' OR
       cohort->'ends_at' IS DISTINCT FROM old_cohort->'ends_at' OR
       vn_durability.rehearsal_view_time(cohort->'completed_at')<>moment OR
       engine->'last_evaluation' IS DISTINCT FROM jsonb_build_object('cohort',cohort,'selection',NULL) THEN
      RAISE EXCEPTION 'lifecycle_abort_audit_mismatch' USING ERRCODE='22023';
    END IF;
  ELSIF NOT replacement AND engine->'last_evaluation' IS DISTINCT FROM prior->'last_evaluation' THEN
    RAISE EXCEPTION 'lifecycle_evaluation_audit_changed' USING ERRCODE='22023';
  END IF;

  IF replacement THEN
    IF restart THEN
      IF cohort->>'phase' IS DISTINCT FROM 'warming' OR
         engine->'last_evaluation' IS DISTINCT FROM prior->'last_evaluation' OR
         engine->'distribution_id' IS DISTINCT FROM 'null'::jsonb THEN
        RAISE EXCEPTION 'lifecycle_restart_audit_mismatch' USING ERRCODE='22023';
      END IF;
      audit:=old_cohort;
    ELSE
      audit:=engine->'last_evaluation'->'cohort';
      IF old_cohort->>'phase' IS DISTINCT FROM 'evaluating' OR audit->>'phase' IS DISTINCT FROM 'completed' OR
         audit->'iteration_id' IS DISTINCT FROM old_cohort->'iteration_id' OR
         audit->'member_ids' IS DISTINCT FROM old_cohort->'member_ids' OR
         audit->'started_at' IS DISTINCT FROM old_cohort->'started_at' OR
         audit->'ends_at' IS DISTINCT FROM old_cohort->'ends_at' OR
         vn_durability.rehearsal_view_time(audit->'completed_at')<>moment OR
         cohort->>'phase' IS DISTINCT FROM (CASE WHEN ready THEN 'evaluating' ELSE 'warming' END) OR
         (ready AND vn_durability.rehearsal_view_time(cohort->'started_at')<>moment) THEN
        RAISE EXCEPTION 'lifecycle_completion_audit_mismatch' USING ERRCODE='22023';
      END IF;
    END IF;
  ELSE
    audit:=cohort;
    IF engine->'distribution_id' IS DISTINCT FROM prior->'distribution_id' THEN
      RAISE EXCEPTION 'lifecycle_distribution_changed' USING ERRCODE='22023';
    END IF;
    started:=old_cohort->>'phase'='warming' AND cohort->>'phase'='evaluating';
    IF started THEN
      IF kind<>'decision' OR NOT ready OR engine->'lifecycle'->'risk'->'active' IS DISTINCT FROM 'false'::jsonb OR
         vn_durability.rehearsal_view_time(cohort->'started_at')<>moment THEN
        RAISE EXCEPTION 'lifecycle_unready_window_start' USING ERRCODE='22023';
      END IF;
    ELSIF NOT newly_aborted THEN
      FOREACH label IN ARRAY ARRAY['phase','started_at','ends_at','completed_at','abort_reason'] LOOP
        IF cohort->label IS DISTINCT FROM old_cohort->label THEN
          RAISE EXCEPTION 'lifecycle_window_changed' USING ERRCODE='22023';
        END IF;
      END LOOP;
    END IF;
    IF kind='control' AND control IN ('resume','recover') AND cohort IS DISTINCT FROM old_cohort THEN
      RAISE EXCEPTION 'lifecycle_control_rewrote_aborted_cohort' USING ERRCODE='22023';
    END IF;
    IF newly_aborted THEN
      before_views:=vn_durability.lifecycle_optimizer_views(prior->'optimizer');
      after_views:=vn_durability.lifecycle_optimizer_views(engine->'optimizer');
      old_strategy:=before_views->'strategy'; new_strategy:=after_views->'strategy';
      IF engine->'config'->>'strategy'='cma_es' THEN
        old_strategy:=old_strategy||'{"_optimizer":null,"_codec":null,"_gene_names":[],"_first_generation":true,
          "_pending_vectors":null,"_pending_genomes":null,"_bound_ids":[],"_bound_genomes":{},"_awaiting_bind":false}'::jsonb;
      ELSE
        old_strategy:=jsonb_set(old_strategy,'{_cohort}',old_strategy->'_cohort'||
          '{"population_size":0,"bound_ids":[],"_signatures":{},"_pending":null,"_previous_ids":[],"_previous_context":null,"_bootstrap":false}'::jsonb);
        IF engine->'config'->>'strategy'='differential_evolution' THEN
          old_strategy:=old_strategy||'{"_phase":"uninitialized","_pairs":[]}'::jsonb;
        ELSIF engine->'config'->>'strategy'='particle_swarm' THEN
          old_strategy:=old_strategy||'{"_codec":null,"_velocities":{},"_personal_best":{},"_global_best":null}'::jsonb;
        END IF;
      END IF;
      IF new_strategy IS DISTINCT FROM old_strategy THEN
        RAISE EXCEPTION 'lifecycle_abort_optimizer_mismatch' USING ERRCODE='22023';
      END IF;
    ELSIF engine->'optimizer'->'strategy' IS DISTINCT FROM prior->'optimizer'->'strategy' THEN
      -- Strategy is encoded first. Cohort changes cannot renumber this graph;
      -- raw equality retains ordered maps and shared aliases, unlike views.
      RAISE EXCEPTION 'lifecycle_optimizer_changed' USING ERRCODE='22023';
    END IF;
  END IF;

  -- Existing terminal/aborted rows are immutable, except the explicit
  -- cohort_complete flag when the complete original window is selected.
  FOR old_result IN SELECT v FROM jsonb_array_elements(old_cohort->'evaluations') q(v) LOOP
    expected:=old_result;
    IF replacement AND NOT restart THEN expected:=jsonb_set(expected,'{cohort_complete}','true'::jsonb); END IF;
    SELECT v INTO result FROM jsonb_array_elements(audit->'evaluations') q(v)
      WHERE v->'probe_id'=old_result->'probe_id';
    IF NOT FOUND OR result IS DISTINCT FROM expected THEN
      RAISE EXCEPTION 'lifecycle_frozen_result_changed' USING ERRCODE='22023';
    END IF;
  END LOOP;
  FOR result IN SELECT v FROM jsonb_array_elements(audit->'evaluations') q(v) LOOP
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(old_cohort->'evaluations') q(v) WHERE v->'probe_id'=result->'probe_id') THEN CONTINUE; END IF;
    IF result->>'status'='completed' THEN
      IF replacement AND NOT restart THEN
        IF result->>'reason' IS DISTINCT FROM 'window_complete' OR
           vn_durability.rehearsal_view_time(result->'terminated_at')<>moment THEN
          RAISE EXCEPTION 'lifecycle_completion_invented_terminal' USING ERRCODE='22023';
        END IF;
      ELSE
        SELECT v INTO member FROM jsonb_array_elements(engine->'members') q(v) WHERE v->'id'=result->'probe_id';
        SELECT v INTO old_member FROM jsonb_array_elements(prior->'members') q(v) WHERE v->'id'=result->'probe_id';
        IF member IS NULL OR old_member IS NULL OR member->'terminal'='null'::jsonb OR old_member->'terminal'<>'null'::jsonb OR
           result->>'reason' IS DISTINCT FROM 'drawdown' OR
           vn_durability.rehearsal_view_time(result->'terminated_at')<>(member->'terminal'->>'at')::numeric THEN
          RAISE EXCEPTION 'lifecycle_result_without_terminal' USING ERRCODE='22023';
        END IF;
      END IF;
    ELSIF result->>'status'='aborted' THEN
      IF NOT newly_aborted THEN RAISE EXCEPTION 'lifecycle_result_without_abort' USING ERRCODE='22023'; END IF;
    ELSE RAISE EXCEPTION 'invalid_lifecycle_result_status' USING ERRCODE='22023';
    END IF;
  END LOOP;

  IF replacement THEN RETURN; END IF;
  new_candle:=engine->'ema'->'last_end' IS DISTINCT FROM prior->'ema'->'last_end';
  FOR old_member IN SELECT v FROM jsonb_array_elements(prior->'members') q(v) LOOP
    identity:=old_member->>'id';
    SELECT v INTO member FROM jsonb_array_elements(engine->'members') q(v) WHERE v->>'id'=identity;
    IF NOT FOUND THEN RAISE EXCEPTION 'lifecycle_member_missing' USING ERRCODE='22023'; END IF;
    IF old_member->'terminal'<>'null'::jsonb THEN
      IF member IS DISTINCT FROM old_member THEN RAISE EXCEPTION 'lifecycle_frozen_member_changed' USING ERRCODE='22023'; END IF;
      CONTINUE;
    END IF;
    IF kind='control' THEN
      IF member-'pending' IS DISTINCT FROM old_member-'pending' OR member->'pending' IS DISTINCT FROM 'null'::jsonb THEN
        RAISE EXCEPTION 'lifecycle_control_changed_member' USING ERRCODE='22023';
      END IF;
    ELSIF kind='protective' THEN
      IF member->'cursor' IS DISTINCT FROM old_member->'cursor' THEN
        RAISE EXCEPTION 'lifecycle_protection_changed_cursor' USING ERRCODE='22023';
      END IF;
      expected:=old_member->'pending';
      closed:=EXISTS(SELECT 1 FROM jsonb_array_elements(evidence->'actions') q(v)
        WHERE v->>'account_id'=identity AND v->'position_id'<>'null'::jsonb);
      IF closed OR member->'terminal'<>'null'::jsonb OR
         (engine->'lifecycle'->'risk'->'active'='true'::jsonb AND expected->>'action'='entry') THEN expected:='null'::jsonb; END IF;
      IF member->'pending' IS DISTINCT FROM expected THEN
        RAISE EXCEPTION 'lifecycle_protection_changed_signal' USING ERRCODE='22023';
      END IF;
    ELSIF kind='decision' THEN
      IF (NOT new_candle OR old_cohort->>'phase'<>'evaluating' OR prior->'lifecycle'->'restart_required'='true'::jsonb) AND
         member->'cursor' IS DISTINCT FROM old_member->'cursor' THEN
        RAISE EXCEPTION 'lifecycle_decision_changed_cursor' USING ERRCODE='22023';
      END IF;
      fresh_pending:=member->'pending'<>'null'::jsonb AND member->'pending' IS DISTINCT FROM old_member->'pending';
      IF fresh_pending AND (NOT new_candle OR old_cohort->>'phase'<>'evaluating' OR
          prior->'lifecycle'->'restart_required'='true'::jsonb OR engine->'lifecycle'->'risk'->'active'='true'::jsonb OR
          member->'pending'->'signal_at' IS DISTINCT FROM to_jsonb(moment) OR
          member->'cursor' IS DISTINCT FROM engine->'ema'->'last_end' OR
          (engine->'lifecycle'->'signals_after'<>'null'::jsonb AND
           (member->>'cursor')::numeric<=(engine->'lifecycle'->>'signals_after')::numeric)) THEN
        RAISE EXCEPTION 'lifecycle_invented_signal' USING ERRCODE='22023';
      END IF;
      IF member->'pending'<>'null'::jsonb AND member->'pending'=old_member->'pending' AND
          moment>(old_member->'pending'->>'signal_at')::numeric THEN
        RAISE EXCEPTION 'lifecycle_unconsumed_signal' USING ERRCODE='22023';
      END IF;
    END IF;
  END LOOP;
END $$;

CREATE FUNCTION vn_durability.lifecycle_actions(state vn_durability.runs,payload jsonb,replacement boolean,restart boolean,moment numeric,price numeric)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE transition jsonb:=payload->'transition'; evidence jsonb:=transition->'evidence'; inputs jsonb:=evidence->'inputs';
        prior jsonb:=state.engine_state->'engine'; engine jsonb:=transition->'after'->'engine';
        control jsonb:=evidence->'control'; kind text:=evidence->>'kind'; operation jsonb; action jsonb; event jsonb;
        member jsonb; previous_member jsonb; item jsonb; earlier jsonb; old_result jsonb; new_result jsonb;
        reason text; expected_status text; entity uuid; owned uuid; reference numeric; cash numeric;
        old_ids jsonb; new_ids jsonb; born jsonb:='[]'::jsonb; retired jsonb:='[]'::jsonb; expected jsonb;
        allocated jsonb:='[]'::jsonb; expected_pending jsonb; changed_trip boolean;
        index integer:=0; event_index integer:=0; births integer:=0; evaluations integer:=0; aborts integer:=0; halts integer:=0;
        newly_aborted boolean; ready boolean; position vn_durability.positions%ROWTYPE;
BEGIN
  SELECT coalesce(jsonb_agg(v->'id' ORDER BY ordinal),'[]'::jsonb) INTO old_ids
    FROM jsonb_array_elements(coalesce(prior->'members','[]'::jsonb)) WITH ORDINALITY q(v,ordinal);
  SELECT jsonb_agg(v->'id' ORDER BY ordinal) INTO new_ids FROM jsonb_array_elements(engine->'members') WITH ORDINALITY q(v,ordinal);
  changed_trip:=engine->'lifecycle'->'risk'->'active'='true'::jsonb AND coalesce(prior->'lifecycle'->'risk'->'active','false'::jsonb)='false'::jsonb;
  newly_aborted:=engine->'cohort'->>'phase'='aborted' AND coalesce(prior->'cohort'->>'phase','warming')<>'aborted';
  ready:=(engine->'ema'->>'count')::integer>=61 AND engine->'ema'->'last_end'<>'null'::jsonb AND
    moment BETWEEN (engine->'ema'->>'last_end')::numeric AND (engine->'ema'->>'last_end')::numeric+900;
  IF NOT replacement AND kind<>'bootstrap' AND new_ids IS DISTINCT FROM old_ids THEN
    RAISE EXCEPTION 'lifecycle_membership_changed' USING ERRCODE='22023';
  END IF;
  FOR action,index IN SELECT v,(ordinal-1)::integer FROM jsonb_array_elements(evidence->'actions') WITH ORDINALITY q(v,ordinal) ORDER BY ordinal LOOP
    PERFORM vn_durability.exact_keys(action,ARRAY['operation_index','reason','account_id','position_id','signal_at','reference_price']);
    PERFORM vn_durability.rehearsal_integer(action->'operation_index',0,1023);
    IF action->'operation_index' IS DISTINCT FROM to_jsonb(index) THEN RAISE EXCEPTION 'lifecycle_action_order' USING ERRCODE='22023'; END IF;
    operation:=payload->'operations'->index; reason:=action->>'reason';
    IF operation->>'kind' IN ('open','close') THEN
      entity:=vn_durability.canonical_id(operation->'id'); owned:=vn_durability.canonical_id(action->'account_id');
      IF action->'position_id' IS DISTINCT FROM operation->'id' OR action->'reference_price' IS DISTINCT FROM evidence->'observation'->'price' OR
         operation->'execution'->'reference_price' IS DISTINCT FROM action->'reference_price' OR kind NOT IN ('protective','decision') THEN
        RAISE EXCEPTION 'lifecycle_fill_source_mismatch' USING ERRCODE='22023';
      END IF;
      SELECT v INTO previous_member FROM jsonb_array_elements(prior->'members') q(v) WHERE v->>'id'=owned::text;
      IF NOT FOUND OR previous_member->'terminal'<>'null'::jsonb THEN RAISE EXCEPTION 'lifecycle_fill_member_mismatch' USING ERRCODE='22023'; END IF;
      IF operation->>'kind'='open' THEN
        IF reason IS DISTINCT FROM 'entry_signal' OR kind<>'decision' OR replacement OR
           prior->'lifecycle'->'risk'->'active'<>'false'::jsonb OR prior->'lifecycle'->'restart_required'<>'false'::jsonb OR
           prior->'cohort'->>'phase'<>'evaluating' OR operation->'account_id' IS DISTINCT FROM action->'account_id' OR
           operation->'asset' IS DISTINCT FROM state.config->'rehearsal'->'asset' THEN
          RAISE EXCEPTION 'invalid_lifecycle_entry' USING ERRCODE='22023';
        END IF;
        SELECT a.cash INTO cash FROM vn_durability.accounts a WHERE a.run_id=state.id AND a.id=owned AND NOT a.retired;
        IF NOT FOUND OR operation->'execution'->>'budget' IS DISTINCT FROM vn_durability.decimal_text(div(cash*1e36,4),36) THEN
          RAISE EXCEPTION 'lifecycle_entry_budget_mismatch' USING ERRCODE='22023';
        END IF;
        allocated:=allocated||jsonb_build_array(operation->'id');
      ELSE
        SELECT * INTO position FROM vn_durability.positions WHERE run_id=state.id AND id=entity AND NOT closed;
        IF NOT FOUND THEN
          SELECT v INTO earlier FROM jsonb_array_elements(payload->'operations') WITH ORDINALITY q(v,ordinal)
            WHERE ordinal<=index AND v->>'kind'='open' AND v->>'id'=entity::text;
          IF NOT FOUND OR reason IS DISTINCT FROM 'death_liquidation' THEN RAISE EXCEPTION 'lifecycle_close_missing' USING ERRCODE='22023'; END IF;
          position.account_id:=vn_durability.canonical_id(earlier->'account_id'); position.entry_execution:=earlier->'execution';
        END IF;
        IF position.account_id<>owned THEN RAISE EXCEPTION 'lifecycle_close_owner_mismatch' USING ERRCODE='22023'; END IF;
        reference:=vn_durability.lifecycle_amount(position.entry_execution->'reference_price',18);
        IF reason='stop_loss' THEN
          IF kind<>'protective' OR price*100>reference*97 THEN RAISE EXCEPTION 'lifecycle_threshold_mismatch' USING ERRCODE='22023'; END IF;
        ELSIF reason='take_profit' THEN
          IF kind<>'protective' OR price*100<reference*107 THEN RAISE EXCEPTION 'lifecycle_threshold_mismatch' USING ERRCODE='22023'; END IF;
        ELSIF reason='exit_signal' THEN
          IF kind<>'decision' OR replacement THEN RAISE EXCEPTION 'invalid_lifecycle_signal_close' USING ERRCODE='22023'; END IF;
        ELSIF reason='death_liquidation' THEN
          IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(engine->'members') q(v) WHERE v->>'id'=owned::text AND
            v->'terminal'->>'reason'='drawdown') THEN RAISE EXCEPTION 'missing_terminal_evidence' USING ERRCODE='22023'; END IF;
        ELSIF reason='cohort_liquidation' THEN
          IF kind<>'decision' OR prior->'cohort'->>'phase'<>'evaluating' OR
             moment<vn_durability.rehearsal_view_time(prior->'cohort'->'ends_at') THEN
            RAISE EXCEPTION 'premature_lifecycle_liquidation' USING ERRCODE='22023';
          END IF;
        ELSIF reason='restart_liquidation' THEN
          IF kind<>'decision' OR prior->'lifecycle'->'restart_required'<>'true'::jsonb OR NOT ready OR
             prior->'lifecycle'->'signals_after'='null'::jsonb OR moment<=(prior->'lifecycle'->>'signals_after')::numeric THEN
            RAISE EXCEPTION 'premature_restart_liquidation' USING ERRCODE='22023';
          END IF;
        ELSE RAISE EXCEPTION 'invalid_lifecycle_close_reason' USING ERRCODE='22023';
        END IF;
      END IF;
      IF reason IN ('entry_signal','exit_signal') THEN
        IF previous_member->'pending'='null'::jsonb OR previous_member->'pending'->'signal_at' IS DISTINCT FROM action->'signal_at' OR
           previous_member->'pending'->>'action' IS DISTINCT FROM (CASE WHEN reason='entry_signal' THEN 'entry' ELSE 'exit' END) OR
           (reason='exit_signal' AND previous_member->'pending'->'position_id' IS DISTINCT FROM operation->'id') OR
           previous_member->'cursor'='null'::jsonb OR moment<=(action->>'signal_at')::numeric OR moment>(previous_member->>'cursor')::numeric+900 THEN
          RAISE EXCEPTION 'lifecycle_signal_causality_mismatch' USING ERRCODE='22023';
        END IF;
      ELSIF action->'signal_at' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'unexpected_lifecycle_signal' USING ERRCODE='22023';
      END IF;
    ELSE
      IF action->'position_id' IS DISTINCT FROM 'null'::jsonb OR action->'signal_at' IS DISTINCT FROM 'null'::jsonb OR
         action->'reference_price' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'invalid_lifecycle_action_fields' USING ERRCODE='22023'; END IF;
      IF operation->>'kind'='birth' THEN
        IF (kind='bootstrap' AND reason IS DISTINCT FROM 'founder') OR
           (kind<>'bootstrap' AND (NOT replacement OR reason IS DISTINCT FROM (CASE WHEN restart THEN 'restart_birth' ELSE 'birth' END))) OR
           action->'account_id' IS DISTINCT FROM operation->'id' OR operation->'id' IS DISTINCT FROM new_ids->births OR
           operation->'cash' IS DISTINCT FROM state.config->'rehearsal'->'seed_capital' OR
           operation->'lineage'->'strategy' IS DISTINCT FROM state.config->'rehearsal'->'strategy' THEN
          RAISE EXCEPTION 'lifecycle_birth_binding_mismatch' USING ERRCODE='22023';
        END IF;
        IF kind='bootstrap' THEN
          IF operation->'lineage'->>'operation' IS DISTINCT FROM 'founder' THEN RAISE EXCEPTION 'invalid_lifecycle_founder' USING ERRCODE='22023'; END IF;
        ELSE
          IF operation->'lineage'->'source_iteration_id' IS DISTINCT FROM prior->'cohort'->'iteration_id' OR
             EXISTS(SELECT 1 FROM jsonb_array_elements(operation->'lineage'->'sources') q(v)
               WHERE NOT prior->'cohort'->'member_ids' @> jsonb_build_array(v->'source_id')) OR
             (operation->'lineage'->>'operation'='distribution_sample' AND
               operation->'lineage'->'distribution_id' IS DISTINCT FROM engine->'distribution_id') OR
             operation->'lineage'->'offspring_index' IS DISTINCT FROM to_jsonb(births) OR
             (restart AND operation->'lineage'->>'operation' IS DISTINCT FROM 'restart_clone') OR
             (NOT restart AND operation->'lineage'->>'version' IS DISTINCT FROM '1') THEN
            RAISE EXCEPTION 'lifecycle_birth_lineage_mismatch' USING ERRCODE='22023';
          END IF;
        END IF;
        IF kind<>'bootstrap' AND NOT restart THEN
          IF state.config->'rehearsal'->>'strategy'='cma_es' THEN
            IF operation->'lineage'->>'operation' IS DISTINCT FROM 'distribution_sample' OR
               operation->'lineage'->'distribution_id' IS DISTINCT FROM engine->'distribution_id' OR
               (SELECT count(*) FROM jsonb_array_elements(payload->'operations') q(v) WHERE v->>'kind'='distribution')<>1 THEN
              RAISE EXCEPTION 'lifecycle_cma_distribution_mismatch' USING ERRCODE='22023';
            END IF;
            expected:=prior->'cohort'->'member_ids';
          ELSE
            SELECT coalesce(jsonb_agg(v->'source_id' ORDER BY ordinal),'[]'::jsonb) INTO expected
              FROM jsonb_array_elements(operation->'lineage'->'sources') WITH ORDINALITY q(v,ordinal)
              WHERE v->>'role'<>'asset_template';
          END IF;
          IF engine->'members'->births->'genome'->'parent_ids' IS DISTINCT FROM expected THEN
            RAISE EXCEPTION 'lifecycle_flat_lineage_mismatch' USING ERRCODE='22023';
          END IF;
        END IF;
        born:=born||jsonb_build_array(operation->'id'); births:=births+1;
      ELSIF operation->>'kind'='retire' THEN
        IF action->'account_id' IS DISTINCT FROM operation->'id' OR reason IS NULL OR
           reason NOT IN ('terminal','retire','restart_retire') OR
           (reason<>'terminal' AND (NOT replacement OR reason IS DISTINCT FROM (CASE WHEN restart THEN 'restart_retire' ELSE 'retire' END))) OR
           (reason='terminal' AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(engine->'members') q(v)
             WHERE v->'id'=operation->'id' AND v->'terminal'<>'null'::jsonb)) THEN
          RAISE EXCEPTION 'lifecycle_retirement_mismatch' USING ERRCODE='22023';
        END IF;
        IF reason<>'terminal' THEN retired:=retired||jsonb_build_array(operation->'id'); END IF;
      ELSIF operation->>'kind'='distribution' THEN
        IF NOT replacement OR restart OR reason IS DISTINCT FROM 'distribution' OR
           action->'account_id' IS DISTINCT FROM 'null'::jsonb OR operation->'id' IS DISTINCT FROM engine->'distribution_id' OR
           state.config->'rehearsal'->>'strategy' IS DISTINCT FROM 'cma_es' OR
           operation->'source_ids' IS DISTINCT FROM prior->'cohort'->'member_ids' OR
           operation->'source_iteration_id' IS DISTINCT FROM prior->'cohort'->'iteration_id' OR
           operation->'previous_distribution_id' IS DISTINCT FROM prior->'distribution_id' OR
           operation->>'stage' IS DISTINCT FROM (CASE WHEN prior->'distribution_id'='null'::jsonb THEN 'bootstrap' ELSE 'update' END) THEN
          RAISE EXCEPTION 'invalid_lifecycle_distribution' USING ERRCODE='22023';
        END IF;
      ELSIF operation->>'kind'='lifecycle' THEN
        IF action->'account_id' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'invalid_lifecycle_status_event' USING ERRCODE='22023'; END IF;
        IF kind='bootstrap' THEN
          IF reason IS DISTINCT FROM 'lifecycle' OR operation->>'status' IS DISTINCT FROM 'running' OR index<>8 THEN
            RAISE EXCEPTION 'invalid_lifecycle_initial_status' USING ERRCODE='22023';
          END IF;
        ELSIF kind='control' THEN
          expected_status:=CASE control->>'action' WHEN 'pause' THEN 'paused' WHEN 'stop' THEN 'stopped' ELSE 'running' END;
          IF reason IS DISTINCT FROM control->>'action' OR operation->>'status' IS DISTINCT FROM expected_status THEN
            RAISE EXCEPTION 'lifecycle_control_status_mismatch' USING ERRCODE='22023';
          END IF;
        ELSE
          IF reason IS DISTINCT FROM 'risk_halt' OR operation->>'status' IS DISTINCT FROM 'risk_halted' OR NOT changed_trip THEN
            RAISE EXCEPTION 'invalid_lifecycle_risk_status' USING ERRCODE='22023';
          END IF;
          halts:=halts+1; allocated:=allocated||jsonb_build_array(engine->'lifecycle'->'risk'->'trip_id');
        END IF;
      ELSE RAISE EXCEPTION 'invalid_lifecycle_operation' USING ERRCODE='22023';
      END IF;
    END IF;
  END LOOP;
  IF halts<>(CASE WHEN changed_trip THEN 1 ELSE 0 END) OR births<>(CASE WHEN replacement OR kind='bootstrap' THEN 8 ELSE 0 END) THEN
    RAISE EXCEPTION 'incomplete_lifecycle_operations' USING ERRCODE='22023';
  END IF;
  IF replacement THEN
    SELECT coalesce(jsonb_agg(v->'id' ORDER BY ordinal),'[]'::jsonb) INTO expected FROM jsonb_array_elements(prior->'members') WITH ORDINALITY q(v,ordinal)
      WHERE v->'terminal'='null'::jsonb;
    IF retired IS DISTINCT FROM expected OR born IS DISTINCT FROM new_ids OR changed_trip THEN
      RAISE EXCEPTION 'incomplete_lifecycle_replacement' USING ERRCODE='22023';
    END IF;
  END IF;
  IF replacement OR kind='bootstrap' THEN
    allocated:=new_ids;
    IF NOT restart AND kind<>'bootstrap' AND engine->'distribution_id'<>'null'::jsonb THEN allocated:=allocated||jsonb_build_array(engine->'distribution_id'); END IF;
    FOR member,index IN SELECT v,(ordinal-1)::integer FROM jsonb_array_elements(engine->'members') WITH ORDINALITY q(v,ordinal) ORDER BY ordinal LOOP
      IF inputs->'names'->index IS DISTINCT FROM jsonb_build_array(engine->'generation',member->'name') THEN
        RAISE EXCEPTION 'lifecycle_name_allocation_mismatch' USING ERRCODE='22023';
      END IF;
      IF restart AND ((member->'genome')-ARRAY['generation','parent_ids']) IS DISTINCT FROM
          ((prior->'members'->index->'genome')-ARRAY['generation','parent_ids']) THEN
        RAISE EXCEPTION 'restart_phenotype_changed' USING ERRCODE='22023';
      END IF;
      IF restart AND member->'genome'->'parent_ids' IS DISTINCT FROM jsonb_build_array(old_ids->index) THEN
        RAISE EXCEPTION 'restart_parent_mismatch' USING ERRCODE='22023';
      END IF;
    END LOOP;
  END IF;
  IF engine->'used_ids' IS DISTINCT FROM coalesce(prior->'used_ids','[]'::jsonb)||allocated OR
     allocated IS DISTINCT FROM (SELECT coalesce(jsonb_agg(v ORDER BY ordinal),'[]'::jsonb)
       FROM jsonb_array_elements(inputs->'ids') WITH ORDINALITY q(v,ordinal) WHERE ordinal<=jsonb_array_length(allocated)) THEN
    RAISE EXCEPTION 'lifecycle_identity_allocation_mismatch' USING ERRCODE='22023';
  END IF;
  FOR event IN SELECT v FROM jsonb_array_elements(transition->'events') WITH ORDINALITY q(v,ordinal) ORDER BY ordinal LOOP
    PERFORM vn_durability.exact_keys(event,ARRAY['kind','at','account_id','position_id','operation_index']);
    PERFORM vn_durability.rehearsal_integer(event->'at',0,253402300799);
    IF event->'operation_index'<>'null'::jsonb THEN PERFORM vn_durability.rehearsal_integer(event->'operation_index',0,1023); END IF;
    IF event->'at' IS DISTINCT FROM to_jsonb(moment) THEN RAISE EXCEPTION 'lifecycle_event_time_mismatch' USING ERRCODE='22023'; END IF;
    IF event->>'kind' IN ('evaluation','evaluation_aborted') THEN
      IF event->'account_id' IS DISTINCT FROM 'null'::jsonb OR event->'position_id' IS DISTINCT FROM 'null'::jsonb OR
         event->'operation_index' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'invalid_lifecycle_cohort_event' USING ERRCODE='22023'; END IF;
      IF event->>'kind'='evaluation' THEN evaluations:=evaluations+1; ELSE aborts:=aborts+1; END IF;
    ELSE
      action:=evidence->'actions'->event_index;
      expected:=jsonb_build_object('kind',action->'reason','at',moment,'account_id',action->'account_id',
        'position_id',action->'position_id','operation_index',event_index);
      IF event IS DISTINCT FROM expected THEN RAISE EXCEPTION 'lifecycle_event_action_mismatch' USING ERRCODE='22023'; END IF;
      event_index:=event_index+1;
    END IF;
  END LOOP;
  IF event_index<>jsonb_array_length(payload->'operations') OR evaluations<>(CASE WHEN replacement AND NOT restart THEN 1 ELSE 0 END) OR
     aborts<>(CASE WHEN newly_aborted THEN 1 ELSE 0 END) THEN RAISE EXCEPTION 'incomplete_lifecycle_events' USING ERRCODE='22023'; END IF;
  PERFORM vn_durability.lifecycle_cohort_continuation(state,payload,replacement,restart,newly_aborted,ready,moment);
END $$;

CREATE FUNCTION vn_durability.validate_lifecycle_before(state vn_durability.runs,payload jsonb)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE transition jsonb:=payload->'transition'; evidence jsonb; inputs jsonb; observation jsonb; control jsonb;
        before_state jsonb; after_state jsonb; prior jsonb; engine jsonb; lifecycle jsonb; kind text; action text;
        stamp numeric; price numeric; reference numeric; moment numeric; generation integer; previous_generation integer;
        old_ids jsonb; new_ids jsonb; born jsonb; retired jsonb; expected jsonb; allocated jsonb:='[]'::jsonb;
        seen uuid[]:=ARRAY[]::uuid[]; entity uuid; item jsonb; member jsonb; operation jsonb; earlier jsonb; reason text;
        record jsonb; event jsonb; position vn_durability.positions%ROWTYPE; index integer:=0; event_index integer:=0;
        evaluations integer:=0; aborted integer:=0; new_trip integer:=0; birth_index integer:=0; count_ids integer;
        replacement boolean; restart boolean; ingest boolean; ready boolean; prior_phase text; new_phase text;
BEGIN
  PERFORM vn_durability.exact_keys(transition,ARRAY['version','before','after','evidence','events']);
  before_state:=transition->'before'; after_state:=transition->'after'; evidence:=transition->'evidence';
  prior:=before_state->'engine'; engine:=after_state->'engine'; lifecycle:=prior->'lifecycle';
  IF transition->'version' IS DISTINCT FROM '1'::jsonb OR before_state IS DISTINCT FROM coalesce(state.engine_state,'null'::jsonb) THEN
    RAISE EXCEPTION 'lifecycle_before_mismatch' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.exact_keys(evidence,ARRAY['kind','inputs','observation','actions','control']);
  inputs:=evidence->'inputs'; observation:=evidence->'observation'; control:=evidence->'control'; kind:=evidence->>'kind';
  PERFORM vn_durability.exact_keys(inputs,ARRAY['event_at','wall_at','monotonic_at','ids','names']);
  IF kind IS NULL OR kind NOT IN ('bootstrap','protective','decision','control') OR
     jsonb_typeof(inputs->'event_at') IS DISTINCT FROM 'string' OR jsonb_typeof(inputs->'wall_at') IS DISTINCT FROM 'string' OR
     inputs->>'event_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00$' OR
     inputs->>'wall_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?\+00:00$' OR
     jsonb_typeof(inputs->'ids') IS DISTINCT FROM 'array' OR jsonb_array_length(inputs->'ids')>4096 OR
     jsonb_typeof(inputs->'names') IS DISTINCT FROM 'array' OR jsonb_array_length(inputs->'names')>4096 OR
     jsonb_typeof(evidence->'actions') IS DISTINCT FROM 'array' OR
     jsonb_array_length(evidence->'actions')<>jsonb_array_length(payload->'operations') OR
     jsonb_typeof(transition->'events') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid_lifecycle_evidence' USING ERRCODE='22023';
  END IF;
  PERFORM (inputs->>'wall_at')::timestamptz;
  moment:=extract(epoch FROM (inputs->>'event_at')::timestamptz);
  IF moment<0 OR moment>253402300799 THEN RAISE EXCEPTION 'invalid_lifecycle_time' USING ERRCODE='22023'; END IF;
  PERFORM vn_durability.rehearsal_hex(inputs->'monotonic_at');
  IF inputs->>'monotonic_at' LIKE '-%' AND inputs->>'monotonic_at'<>'-0x0.0p+0' THEN
    RAISE EXCEPTION 'invalid_lifecycle_time' USING ERRCODE='22023';
  END IF;
  FOR item IN SELECT v FROM jsonb_array_elements(inputs->'ids') q(v) LOOP
    entity:=vn_durability.canonical_id(item);
    IF entity=ANY(seen) THEN RAISE EXCEPTION 'duplicate_lifecycle_identity' USING ERRCODE='22023'; END IF;
    seen:=array_append(seen,entity);
  END LOOP;
  FOR item IN SELECT v FROM jsonb_array_elements(inputs->'names') q(v) LOOP
    IF jsonb_typeof(item) IS DISTINCT FROM 'array' OR jsonb_array_length(item)<>2 OR
       jsonb_typeof(item->1) IS DISTINCT FROM 'string' OR octet_length(item->>1) NOT BETWEEN 1 AND 128 OR
       item->>1<>btrim(item->>1) OR item->>1 ~ '[[:cntrl:]]' THEN
      RAISE EXCEPTION 'invalid_lifecycle_name' USING ERRCODE='22023';
    END IF;
    PERFORM vn_durability.rehearsal_integer(item->0,0,2147483647);
  END LOOP;
  generation:=vn_durability.rehearsal_integer(engine->'generation',0,3);
  previous_generation:=CASE WHEN state.engine_state IS NULL THEN 0 ELSE (prior->>'generation')::integer END;
  replacement:=generation=previous_generation+1;
  restart:=replacement AND lifecycle->'restart_required'='true'::jsonb;
  prior_phase:=prior->'cohort'->>'phase'; new_phase:=engine->'cohort'->>'phase';
  IF generation NOT BETWEEN previous_generation AND previous_generation+1 OR
     (kind<>'decision' AND replacement) OR (kind<>'control' AND control IS DISTINCT FROM 'null'::jsonb) THEN
    RAISE EXCEPTION 'invalid_lifecycle_generation' USING ERRCODE='22023';
  END IF;
  IF kind='bootstrap' THEN
    IF state.engine_state IS NOT NULL OR state.revision<>1 OR state.status<>'starting' OR generation<>0 OR
       observation IS DISTINCT FROM 'null'::jsonb OR jsonb_array_length(payload->'operations')<>9 OR
       engine->'last_quote' IS DISTINCT FROM 'null'::jsonb OR engine->'decision_timestamp' IS DISTINCT FROM 'null'::jsonb OR
       engine->'ema' IS DISTINCT FROM '{"count":0,"last_end":null,"closes":[],"values":{},"previous":{}}'::jsonb OR
       engine->'distribution_id' IS DISTINCT FROM 'null'::jsonb OR engine->'last_evaluation' IS DISTINCT FROM 'null'::jsonb OR
       new_phase IS DISTINCT FROM 'warming' THEN
      RAISE EXCEPTION 'invalid_lifecycle_bootstrap' USING ERRCODE='22023';
    END IF;
  ELSE
    IF state.engine_state IS NULL OR state.status NOT IN ('running','paused','risk_halted') OR
       (prior->'last_quote'<>'null'::jsonb AND moment<(prior->'last_quote'->>'timestamp')::numeric) OR
       (lifecycle->'last_control_at'<>'null'::jsonb AND moment<(lifecycle->>'last_control_at')::numeric) THEN
      RAISE EXCEPTION 'invalid_lifecycle_source_time' USING ERRCODE='22023';
    END IF;
  END IF;
  IF observation<>'null'::jsonb THEN
    PERFORM vn_durability.exact_keys(observation,ARRAY['timestamp','price','candle_end','candle_close']);
    stamp:=vn_durability.rehearsal_integer(observation->'timestamp',0,253402300799);
    price:=vn_durability.lifecycle_amount(observation->'price',18);
    IF price<=0 OR stamp<>moment OR (observation->'candle_end'='null'::jsonb)<>(observation->'candle_close'='null'::jsonb) OR
       engine->'last_quote' IS DISTINCT FROM jsonb_build_object('timestamp',stamp,'price',observation->'price') THEN
      RAISE EXCEPTION 'lifecycle_quote_mismatch' USING ERRCODE='22023';
    END IF;
    IF observation->'candle_end'<>'null'::jsonb THEN
      reference:=vn_durability.rehearsal_integer(observation->'candle_end',0,253402300799);
      IF mod(reference,900)<>0 OR reference>stamp OR vn_durability.lifecycle_amount(observation->'candle_close',18)<=0 THEN
        RAISE EXCEPTION 'invalid_lifecycle_candle' USING ERRCODE='22023';
      END IF;
    END IF;
  ELSIF kind IN ('protective','decision') THEN RAISE EXCEPTION 'lifecycle_quote_required' USING ERRCODE='22023';
  END IF;
  IF kind='protective' THEN
    IF state.status NOT IN ('running','risk_halted') OR observation->'candle_end'<>'null'::jsonb OR
       (prior->'last_quote'<>'null'::jsonb AND stamp<=(prior->'last_quote'->>'timestamp')::numeric) OR
       engine->'decision_timestamp' IS DISTINCT FROM prior->'decision_timestamp' THEN
      RAISE EXCEPTION 'invalid_lifecycle_protection' USING ERRCODE='22023';
    END IF;
    FOR position IN SELECT * FROM vn_durability.positions WHERE run_id=state.id AND NOT closed LOOP
      reference:=vn_durability.lifecycle_amount(position.entry_execution->'reference_price',18);
      IF (price*100<=reference*97 OR price*100>=reference*107) AND NOT EXISTS(
        SELECT 1 FROM jsonb_array_elements(payload->'operations') WITH ORDINALITY q(v,ordinal)
        WHERE v->>'kind'='close' AND v->>'id'=position.id::text AND
          payload->'transition'->'evidence'->'actions'->((ordinal-1)::integer)->>'reason'=
          CASE WHEN price*100<=reference*97 THEN 'stop_loss' ELSE 'take_profit' END) THEN
        RAISE EXCEPTION 'missing_lifecycle_protection' USING ERRCODE='22023';
      END IF;
    END LOOP;
  ELSIF kind='decision' THEN
    IF state.status NOT IN ('running','risk_halted') OR engine->'last_quote' IS DISTINCT FROM prior->'last_quote' OR
       engine->'decision_timestamp' IS DISTINCT FROM observation->'timestamp' OR
       (prior->'decision_timestamp'<>'null'::jsonb AND stamp<=(prior->>'decision_timestamp')::numeric) THEN
      RAISE EXCEPTION 'invalid_lifecycle_decision' USING ERRCODE='22023';
    END IF;
  ELSIF kind='control' THEN
    PERFORM vn_durability.exact_keys(control,ARRAY['action','trip_id']); action:=control->>'action';
    IF action IS NULL OR action NOT IN ('pause','resume','stop','recover') OR jsonb_array_length(payload->'operations')<>1 OR
       engine->'decision_timestamp' IS DISTINCT FROM prior->'decision_timestamp' OR engine->'last_quote' IS DISTINCT FROM prior->'last_quote' OR
       (action='pause' AND state.status<>'running') OR (action='resume' AND state.status<>'paused') OR
       (action='recover' AND state.status<>'risk_halted') OR
       (action<>'recover' AND (control->'trip_id' IS DISTINCT FROM 'null'::jsonb OR observation IS DISTINCT FROM 'null'::jsonb)) THEN
      RAISE EXCEPTION 'invalid_lifecycle_control' USING ERRCODE='22023';
    END IF;
    IF action='recover' THEN
      IF lifecycle->'risk'->'active' IS DISTINCT FROM 'true'::jsonb OR control->'trip_id' IS DISTINCT FROM lifecycle->'risk'->'trip_id' OR
         observation='null'::jsonb OR observation->'candle_end'='null'::jsonb OR stamp>(observation->>'candle_end')::numeric+900 OR
         (engine->'ema'->>'count')::integer<61 OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(prior->'members') q(v) WHERE v->'terminal'='null'::jsonb) OR
         vn_durability.lifecycle_equity(state.id,state.reserve,observation->'price')*10000<=state.initial_cash*1e36*
           (10000-(state.config->'rehearsal'->'lifecycle_policy'->>'account_loss_bps')::numeric) THEN
        RAISE EXCEPTION 'invalid_lifecycle_recovery' USING ERRCODE='22023';
      END IF;
    END IF;
  END IF;
  IF kind<>'bootstrap' THEN
    ingest:=(kind='decision' AND lifecycle->'risk'->'active'='false'::jsonb) OR (kind='control' AND action='recover');
    PERFORM vn_durability.lifecycle_candles(prior->'ema',engine->'ema',observation,ingest);
  END IF;
  ready:=(engine->'ema'->>'count')::integer>=61 AND engine->'ema'->'last_end'<>'null'::jsonb AND
    stamp BETWEEN (engine->'ema'->>'last_end')::numeric AND (engine->'ema'->>'last_end')::numeric+900;
  IF kind='decision' AND prior_phase='evaluating' AND moment>=vn_durability.rehearsal_view_time(prior->'cohort'->'ends_at') AND
     NOT replacement AND new_phase<>'aborted' THEN
    RAISE EXCEPTION 'lifecycle_deadline_not_completed' USING ERRCODE='22023';
  END IF;
  IF replacement THEN
    IF state.status<>'running' OR lifecycle->'risk'->'active'<>'false'::jsonb OR
       (restart AND (prior_phase<>'aborted' OR NOT ready OR lifecycle->'signals_after'='null'::jsonb OR stamp<=(lifecycle->>'signals_after')::numeric)) OR
       (NOT restart AND (prior_phase<>'evaluating' OR stamp<vn_durability.rehearsal_view_time(prior->'cohort'->'ends_at'))) THEN
      RAISE EXCEPTION 'invalid_lifecycle_replacement' USING ERRCODE='22023';
    END IF;
  END IF;
  -- Action, allocation, cohort and event ordering are checked below before any
  -- mutation. A syntactically valid engine projection alone is insufficient.
  PERFORM vn_durability.lifecycle_actions(state,payload,replacement,coalesce(restart,false),moment,price);
END $$;

CREATE FUNCTION vn_durability.validate_lifecycle_after(state vn_durability.runs, payload jsonb, first_trip numeric) RETURNS void
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
     candidate->>'status' IS DISTINCT FROM state.status OR candidate->>'status' NOT IN ('running','paused','risk_halted','stopped') OR
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
    'ema','distribution_id','used_ids','last_evaluation','optimizer','lifecycle','cohort']);
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
    PERFORM vn_durability.exact_keys(member,ARRAY['id','name','genome','cursor','pending','num_trades','peak_equity','max_drawdown','terminal']);
    entity:=vn_durability.canonical_id(member->'id');
    IF entity=ANY(members) OR jsonb_typeof(member->'name') IS DISTINCT FROM 'string' OR
       octet_length(member->>'name') NOT BETWEEN 1 AND 128 OR
       NOT EXISTS(SELECT 1 FROM vn_durability.accounts WHERE run_id=state.id AND id=entity AND retired=(member->'terminal'<>'null'::jsonb)) THEN
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
    PERFORM vn_durability.lifecycle_member_metrics(state,payload,member,prior);
    IF (member->>'num_trades')::integer<>(SELECT count(*) FROM vn_durability.positions
      WHERE run_id=state.id AND account_id=entity AND closed) THEN
      RAISE EXCEPTION 'transition_trade_count_mismatch' USING ERRCODE='22023';
    END IF;
  END LOOP;
  IF (SELECT count(*) FROM vn_durability.accounts WHERE run_id=state.id AND NOT retired)<>
     (SELECT count(*) FROM jsonb_array_elements(engine->'members') q(v) WHERE v->'terminal'='null'::jsonb) THEN
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
    IF member->'cursor'<>'null'::jsonb AND (engine->'ema'->'last_end'='null'::jsonb OR (member->>'cursor')::numeric>(engine->'ema'->>'last_end')::numeric) THEN
      RAISE EXCEPTION 'transition_member_cursor_mismatch' USING ERRCODE='22023';
    END IF;
  END LOOP;
  PERFORM vn_durability.lifecycle_state(state,payload,first_trip);
  PERFORM vn_durability.exact_keys(engine->'optimizer',ARRAY['version','software','strategy','cohort']);
  PERFORM vn_durability.exact_keys(engine->'optimizer'->'software',ARRAY['python','numpy','cmaes']);
  IF engine->'optimizer'->>'version' IS DISTINCT FROM 'optimizer-evidence-v1' OR
     engine->'optimizer'->'software'->>'cmaes' IS DISTINCT FROM '0.13.1' THEN
    RAISE EXCEPTION 'invalid_transition_optimizer' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.rehearsal_json(engine);
  PERFORM vn_durability.optimizer_evidence(engine->'optimizer',state.config->'rehearsal'->>'strategy');
  PERFORM vn_durability.lifecycle_optimizer_mirror(engine);
END $$;

CREATE FUNCTION vn_durability.provider_us(value jsonb) RETURNS numeric
LANGUAGE sql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
 SELECT vn_durability.rehearsal_integer(value,0,10000000000000000)
$$;

CREATE FUNCTION vn_durability.provider_hex_us(value jsonb) RETURNS numeric
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE raw text; digits text; amount numeric:=0; exponent integer; denominator numeric;
BEGIN
 PERFORM vn_durability.rehearsal_hex(value); raw:=value#>>'{}';
 IF raw IN ('0x0.0p+0','-0x0.0p+0') THEN RETURN 0; END IF;
 IF left(raw,1)='-' THEN RAISE EXCEPTION 'invalid_provider_clock' USING ERRCODE='22023'; END IF;
 digits:=replace(substring(split_part(raw,'p',1),3),'.','');
 exponent:=split_part(raw,'p',2)::integer-4*length(split_part(split_part(raw,'p',1),'.',2));
 FOR i IN 1..length(digits) LOOP amount:=amount*16+strpos('0123456789abcdef',substring(digits,i,1))-1; END LOOP;
 amount:=amount*1000000;
 IF exponent>=0 THEN amount:=amount*power(2::numeric,exponent);
 ELSE denominator:=power(2::numeric,-exponent); amount:=div(amount,denominator)+CASE WHEN mod(amount,denominator)>0 THEN 1 ELSE 0 END;
 END IF;
 IF amount>10000000000000000 THEN RAISE EXCEPTION 'invalid_provider_clock' USING ERRCODE='22023'; END IF;
 RETURN amount;
END $$;

CREATE FUNCTION vn_durability.provider_config(configuration jsonb) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE policy jsonb:=configuration->'source_policy'; epoch uuid;
BEGIN
 PERFORM vn_durability.exact_keys(configuration,ARRAY['durability_contract_version','execution','rehearsal','source_policy']);
 IF configuration->'durability_contract_version' IS DISTINCT FROM '5'::jsonb OR
    configuration->'rehearsal'->'asset' IS DISTINCT FROM '"SOL/USD"'::jsonb THEN
  RAISE EXCEPTION 'invalid_provider_config' USING ERRCODE='22023'; END IF;
 epoch:=vn_durability.canonical_id(policy->'epoch');
 IF policy-'epoch' IS DISTINCT FROM '{"version":"jupiter-birdeye-sol-usd-v1","asset":"SOL/USD","mint":"So11111111111111111111111111111111111111112","chain":"solana","denomination":"USD","valuation":"reference_mark","source_time_policy":"jupiter-block-id-as-slot-estimated-time-v1","clock_policy":"conservative-integer-microseconds-v1","max_source_age_us":30000000,"future_tolerance_us":2000000,"max_receipt_age_us":5000000,"candle_seconds":900,"candle_completion_us":5000000,"seed_bars":61,"max_history_bars":64,"source_order":"strict-block-ref-nondecreasing-estimate-v1","evidence_trust":"worker-parsed-records-and-manifests-v1","outlier_policy":"provider-default-omitted"}'::jsonb THEN
  RAISE EXCEPTION 'invalid_provider_policy' USING ERRCODE='22023'; END IF;
 PERFORM vn_durability.lifecycle_config((configuration-'source_policy')||'{"durability_contract_version":4}'::jsonb);
END $$;

CREATE FUNCTION vn_durability.provider_mint(value text) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE alphabet text:='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
 amount numeric:=0; zeroes integer:=0; bytes integer:=0;
BEGIN
 IF value IS NULL OR value !~ '^[1-9A-HJ-NP-Za-km-z]{32,44}$' THEN
  RAISE EXCEPTION 'invalid_provider_mint' USING ERRCODE='22023'; END IF;
 FOR i IN 1..length(value) LOOP amount:=amount*58+strpos(alphabet,substring(value,i,1))-1; END LOOP;
 WHILE zeroes<length(value) AND substring(value,zeroes+1,1)='1' LOOP zeroes:=zeroes+1; END LOOP;
 WHILE amount>0 LOOP amount:=div(amount,256); bytes:=bytes+1; END LOOP;
 IF bytes+zeroes<>32 THEN RAISE EXCEPTION 'invalid_provider_mint' USING ERRCODE='22023'; END IF;
END $$;

CREATE FUNCTION vn_durability.provider_document(value jsonb, provider text) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE request jsonb; params jsonb; mints text[]; mint text; lower_time numeric; upper_time numeric;
BEGIN
 PERFORM vn_durability.exact_keys(value,ARRAY['provider','parser_policy','request','request_sha256','response_sha256','response_bytes','received_wall_us','received_monotonic_us']);
 IF value->'provider' IS DISTINCT FROM to_jsonb(provider) OR value->'parser_policy' IS DISTINCT FROM '"provider-json-exact-v1"'::jsonb OR
    jsonb_typeof(value->'request_sha256') IS DISTINCT FROM 'string' OR value->>'request_sha256' !~ '^[a-f0-9]{64}$' OR
    jsonb_typeof(value->'response_sha256') IS DISTINCT FROM 'string' OR value->>'response_sha256' !~ '^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION 'invalid_provider_document' USING ERRCODE='22023'; END IF;
 PERFORM vn_durability.provider_us(value->'received_wall_us'); PERFORM vn_durability.provider_us(value->'received_monotonic_us');
 PERFORM vn_durability.rehearsal_integer(value->'response_bytes',1,CASE WHEN provider='jupiter-price-v3' THEN 131072 ELSE 4194304 END);
 request:=value->'request'; params:=request->'parameters';
 PERFORM vn_durability.exact_keys(request,ARRAY['method','endpoint','chain','parameters']);
 IF request->'method' IS DISTINCT FROM '"GET"'::jsonb OR request->'chain' IS DISTINCT FROM '"solana"'::jsonb THEN
  RAISE EXCEPTION 'invalid_provider_request' USING ERRCODE='22023'; END IF;
 IF provider='jupiter-price-v3' THEN
  PERFORM vn_durability.exact_keys(params,ARRAY['ids']);
  IF request->'endpoint' IS DISTINCT FROM '"https://api.jup.ag/price/v3"'::jsonb OR
     jsonb_typeof(params->'ids') IS DISTINCT FROM 'string' OR octet_length(params->>'ids')>2250 THEN
   RAISE EXCEPTION 'invalid_provider_request' USING ERRCODE='22023'; END IF;
  mints:=string_to_array(params->>'ids',',');
  IF cardinality(mints) NOT BETWEEN 1 AND 50 OR NOT 'So11111111111111111111111111111111111111112'=ANY(mints) OR
     (SELECT count(DISTINCT m) FROM unnest(mints) q(m))<>cardinality(mints) OR
     EXISTS(SELECT 1 FROM unnest(mints) q(m) WHERE m !~ '^[1-9A-HJ-NP-Za-km-z]{32,44}$') THEN
   RAISE EXCEPTION 'invalid_provider_request' USING ERRCODE='22023'; END IF;
  FOREACH mint IN ARRAY mints LOOP PERFORM vn_durability.provider_mint(mint); END LOOP;
 ELSIF provider='birdeye-ohlcv-v3' THEN
  PERFORM vn_durability.exact_keys(params,ARRAY['address','type','mode','time_from','time_to','currency','chart_type','ui_amount_mode','padding']);
  IF request->'endpoint' IS DISTINCT FROM '"https://public-api.birdeye.so/defi/v3/ohlcv"'::jsonb OR
     params-ARRAY['time_from','time_to'] IS DISTINCT FROM '{"address":"So11111111111111111111111111111111111111112","type":"1m","mode":"range","currency":"usd","chart_type":"price","ui_amount_mode":"raw","padding":"false"}'::jsonb THEN
   RAISE EXCEPTION 'invalid_provider_request' USING ERRCODE='22023'; END IF;
  lower_time:=vn_durability.rehearsal_integer(params->'time_from',0,10000000000);
  upper_time:=vn_durability.rehearsal_integer(params->'time_to',0,10000000000);
  IF mod(lower_time,60)<>0 OR mod(upper_time,60)<>0 OR upper_time<=lower_time OR upper_time-lower_time>299940 THEN
   RAISE EXCEPTION 'invalid_provider_request' USING ERRCODE='22023'; END IF;
 ELSE RAISE EXCEPTION 'invalid_provider_kind' USING ERRCODE='22023'; END IF;
END $$;

CREATE FUNCTION vn_durability.provider_receipt(value jsonb, wall_us numeric, mono_us numeric, server boolean DEFAULT false) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE wall numeric:=vn_durability.provider_us(value->'received_wall_us'); mono numeric:=vn_durability.provider_us(value->'received_monotonic_us');
BEGIN
 IF wall_us<wall OR (NOT server AND mono_us<mono) OR wall_us-wall>=5000000 OR
    (NOT server AND mono_us-mono>=5000000) THEN
  RAISE EXCEPTION 'provider_receipt_expired' USING ERRCODE='22023'; END IF;
END $$;

CREATE FUNCTION vn_durability.provider_frame(value jsonb) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE quote jsonb:=value->'quote'; moment numeric; wall numeric; mono numeric;
BEGIN
 PERFORM vn_durability.exact_keys(value,ARRAY['sequence','decision_second','decision_wall_us','decision_monotonic_us','quote']);
 PERFORM vn_durability.rehearsal_integer(value->'sequence',1,4096);
 moment:=vn_durability.rehearsal_integer(value->'decision_second',0,10000000000);
 wall:=vn_durability.provider_us(value->'decision_wall_us'); mono:=vn_durability.provider_us(value->'decision_monotonic_us');
 PERFORM vn_durability.exact_keys(quote,ARRAY['price','block_ref','estimated_source_second','source_age_floor_us','document']);
 IF vn_durability.lifecycle_amount(quote->'price',18)<=0 THEN RAISE EXCEPTION 'invalid_provider_price' USING ERRCODE='22023'; END IF;
 PERFORM vn_durability.rehearsal_integer(quote->'block_ref',0,18446744073709551615);
 PERFORM vn_durability.rehearsal_integer(quote->'estimated_source_second',0,10000000000);
 PERFORM vn_durability.provider_us(quote->'source_age_floor_us');
 PERFORM vn_durability.provider_document(quote->'document','jupiter-price-v3');
 IF (wall<moment*1000000 OR wall>(moment+1)*1000000) OR moment<ceil((quote->'document'->>'received_wall_us')::numeric/1000000) OR
    wall<(quote->'document'->>'received_wall_us')::numeric OR mono<(quote->'document'->>'received_monotonic_us')::numeric THEN
  RAISE EXCEPTION 'invalid_provider_frame_clock' USING ERRCODE='22023'; END IF;
END $$;

CREATE FUNCTION vn_durability.provider_fresh_frame(value jsonb, wall_us numeric, mono_us numeric, server boolean DEFAULT false) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE quote jsonb:=value->'quote'; doc jsonb:=quote->'document'; stamp numeric:=(quote->>'estimated_source_second')::numeric*1000000;
 initial_age numeric; floor_age numeric; elapsed numeric;
BEGIN
 PERFORM vn_durability.provider_receipt(doc,wall_us,mono_us,server);
 initial_age:=(doc->>'received_wall_us')::numeric-stamp;
 floor_age:=greatest(0,initial_age,(quote->>'source_age_floor_us')::numeric);
 elapsed:=CASE WHEN server THEN greatest(0,wall_us-(doc->>'received_wall_us')::numeric) ELSE mono_us-(doc->>'received_monotonic_us')::numeric END;
 IF initial_age < -2000000 OR wall_us-stamp < -2000000 OR
    greatest(wall_us-stamp,floor_age+elapsed)>30000000 THEN
  RAISE EXCEPTION 'provider_quote_stale' USING ERRCODE='22023'; END IF;
 IF NOT server AND (wall_us<(value->>'decision_wall_us')::numeric OR mono_us<(value->>'decision_monotonic_us')::numeric) THEN
  RAISE EXCEPTION 'provider_clock_regressed' USING ERRCODE='22023'; END IF;
END $$;

CREATE FUNCTION vn_durability.provider_bars(value jsonb) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE item jsonb; stamp numeric; previous numeric;
BEGIN
 IF jsonb_typeof(value) IS DISTINCT FROM 'array' OR jsonb_array_length(value) NOT BETWEEN 61 AND 64 THEN
  RAISE EXCEPTION 'invalid_provider_bars' USING ERRCODE='22023'; END IF;
 FOR item IN SELECT v FROM jsonb_array_elements(value) q(v) LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'array' OR jsonb_array_length(item)<>3 THEN
   RAISE EXCEPTION 'invalid_provider_bar' USING ERRCODE='22023'; END IF;
  stamp:=vn_durability.rehearsal_integer(item->0,900,10000000000);
  IF mod(stamp,900)<>0 OR (previous IS NOT NULL AND stamp<>previous+900) OR
     vn_durability.lifecycle_amount(item->1,18)<=0 OR jsonb_typeof(item->2) IS DISTINCT FROM 'string' OR item->>2 !~ '^[a-f0-9]{64}$' THEN
   RAISE EXCEPTION 'invalid_provider_bar' USING ERRCODE='22023'; END IF;
  previous:=stamp;
 END LOOP;
END $$;

CREATE FUNCTION vn_durability.provider_history(value jsonb, old_bars jsonb, seed boolean, wall_us numeric, mono_us numeric) RETURNS jsonb
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE docs jsonb; minutes jsonb; doc jsonb; old_doc jsonb; item jsonb; ordinal integer:=0;
 idx integer; used integer[]:=ARRAY[]::integer[]; stamp numeric; previous numeric; ending numeric; bars jsonb:='[]'::jsonb;
 pairs text:=''; fingerprint text; latest numeric; result jsonb;
BEGIN
 PERFORM vn_durability.exact_keys(value,ARRAY['documents','minutes','unscaled']);
 docs:=value->'documents'; minutes:=value->'minutes';
 IF value->'unscaled' IS DISTINCT FROM 'true'::jsonb OR jsonb_typeof(docs) IS DISTINCT FROM 'array' OR
    jsonb_array_length(docs) NOT BETWEEN 1 AND 4 OR jsonb_typeof(minutes) IS DISTINCT FROM 'array' OR
    jsonb_array_length(minutes)<>(CASE WHEN seed THEN 915 ELSE 15 END) THEN
  RAISE EXCEPTION 'invalid_provider_history' USING ERRCODE='22023'; END IF;
 FOR doc IN SELECT v FROM jsonb_array_elements(docs) q(v) LOOP
  PERFORM vn_durability.provider_document(doc,'birdeye-ohlcv-v3');
  PERFORM vn_durability.provider_receipt(doc,wall_us,mono_us);
  IF old_doc IS NOT NULL AND ROW(doc->>'response_sha256',doc->>'request_sha256',(doc->>'received_wall_us')::numeric,(doc->>'received_monotonic_us')::numeric)
     <=ROW(old_doc->>'response_sha256',old_doc->>'request_sha256',(old_doc->>'received_wall_us')::numeric,(old_doc->>'received_monotonic_us')::numeric) THEN
   RAISE EXCEPTION 'provider_document_order' USING ERRCODE='22023'; END IF;
  old_doc:=doc;
 END LOOP;
 FOR item IN SELECT v FROM jsonb_array_elements(minutes) q(v) LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'array' OR jsonb_array_length(item)<>3 THEN
   RAISE EXCEPTION 'invalid_provider_minute' USING ERRCODE='22023'; END IF;
  stamp:=vn_durability.rehearsal_integer(item->0,60,9999999940);
  idx:=vn_durability.rehearsal_integer(item->2,0,jsonb_array_length(docs)-1); doc:=docs->idx;
  IF mod(stamp,60)<>0 OR (previous IS NULL AND mod(stamp,900)<>0) OR (previous IS NOT NULL AND stamp<>previous+60) OR
     vn_durability.lifecycle_amount(item->1,18)<=0 OR stamp<(doc->'request'->'parameters'->>'time_from')::numeric OR
     stamp+60>(doc->'request'->'parameters'->>'time_to')::numeric THEN
   RAISE EXCEPTION 'invalid_provider_minute' USING ERRCODE='22023'; END IF;
  ending:=(floor(stamp/900)+1)*900;
  IF ending*1000000+5000000>(doc->>'received_wall_us')::numeric OR ending*1000000+5000000>wall_us THEN
   RAISE EXCEPTION 'provider_candle_incomplete' USING ERRCODE='22023'; END IF;
  IF NOT idx=ANY(used) THEN used:=array_append(used,idx); END IF;
  pairs:=pairs||CASE WHEN mod(ordinal,15)=0 THEN '' ELSE ',' END||'['||stamp::text||','||(item->1)::text||']';
  ordinal:=ordinal+1; previous:=stamp;
  IF mod(ordinal,15)=0 THEN
   fingerprint:=encode(sha256(convert_to('['||pairs||']','UTF8')),'hex');
   bars:=bars||jsonb_build_array(jsonb_build_array(stamp+60,item->1,fingerprint)); pairs:='';
  END IF;
 END LOOP;
 latest:=floor((wall_us-5000000)/900000000)*900;
 IF cardinality(used)<>jsonb_array_length(docs) OR previous+60<>latest OR
    (NOT seed AND (bars->0->0)::text<>(to_jsonb((old_bars->-1->>0)::numeric+900))::text) THEN
  RAISE EXCEPTION 'provider_history_cursor' USING ERRCODE='22023'; END IF;
 result:=CASE WHEN seed THEN bars ELSE old_bars||bars END;
 SELECT jsonb_agg(v ORDER BY q.ordinal) INTO result FROM jsonb_array_elements(result) WITH ORDINALITY q(v,ordinal)
  WHERE q.ordinal>greatest(jsonb_array_length(result)-64,0);
 RETURN result;
END $$;

CREATE FUNCTION vn_durability.provider_state(value jsonb, epoch jsonb) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE source jsonb:=value->'source'; frame jsonb;
BEGIN
 PERFORM vn_durability.exact_keys(value,ARRAY['version','owner_id','run_id','revision','status','reserve','accounts','positions','engine','source']);
 PERFORM vn_durability.exact_keys(source,ARRAY['version','epoch','quote_sequence','last_quote','bars']);
 IF source->'version' IS DISTINCT FROM '1'::jsonb OR source->'epoch' IS DISTINCT FROM epoch THEN
  RAISE EXCEPTION 'provider_epoch_mismatch' USING ERRCODE='22023'; END IF;
 PERFORM vn_durability.rehearsal_integer(source->'quote_sequence',0,4096);
 PERFORM vn_durability.provider_bars(source->'bars'); frame:=source->'last_quote';
 IF frame='null'::jsonb THEN
  IF source->'quote_sequence'<>'0'::jsonb OR value->'engine'->'last_quote' IS DISTINCT FROM 'null'::jsonb THEN
   RAISE EXCEPTION 'provider_quote_projection' USING ERRCODE='22023'; END IF;
 ELSE
  PERFORM vn_durability.provider_frame(frame);
  IF frame->'sequence' IS DISTINCT FROM source->'quote_sequence' OR value->'engine'->'last_quote' IS DISTINCT FROM
     jsonb_build_object('timestamp',frame->'decision_second','price',frame->'quote'->'price') THEN
   RAISE EXCEPTION 'provider_quote_projection' USING ERRCODE='22023'; END IF;
 END IF;
 IF value->'engine'->'ema'->'last_end' IS DISTINCT FROM source->'bars'->-1->0 OR
    value->'engine'->'ema'->'closes' IS DISTINCT FROM (SELECT jsonb_agg(v->1 ORDER BY ordinal) FROM jsonb_array_elements(source->'bars') WITH ORDINALITY q(v,ordinal)) THEN
  RAISE EXCEPTION 'provider_ema_source_mismatch' USING ERRCODE='22023'; END IF;
END $$;

CREATE FUNCTION vn_durability.provider_model_payload(payload jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE result jsonb:=payload; transition jsonb:=payload->'transition';
BEGIN
 transition:=jsonb_set(transition,'{after}',(transition->'after')-'source');
 IF transition->'before'<>'null'::jsonb THEN transition:=jsonb_set(transition,'{before}',(transition->'before')-'source'); END IF;
 transition:=jsonb_set(transition,'{evidence}',(transition->'evidence')-'source');
 IF transition->'before'='null'::jsonb OR transition->'before'->'engine'->'last_quote'='null'::jsonb THEN
  IF transition->'before'<>'null'::jsonb THEN
   transition:=jsonb_set(transition,'{before,engine,ema}','{"count":0,"last_end":null,"closes":[],"values":{},"previous":{}}'::jsonb);
  END IF;
  transition:=jsonb_set(transition,'{after,engine,ema}','{"count":0,"last_end":null,"closes":[],"values":{},"previous":{}}'::jsonb);
 END IF;
 RETURN jsonb_set(result,'{transition}',transition)||'{"version":4}'::jsonb;
END $$;

CREATE FUNCTION vn_durability.provider_model_run(state vn_durability.runs) RETURNS vn_durability.runs
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
BEGIN
 state.config:=(state.config-'source_policy')||'{"durability_contract_version":4}'::jsonb;
 state.command_version:=4;
 IF state.engine_state IS NOT NULL THEN
  state.engine_state:=state.engine_state-'source';
  IF state.engine_state->'engine'->'last_quote'='null'::jsonb THEN
   state.engine_state:=jsonb_set(state.engine_state,'{engine,ema}','{"count":0,"last_end":null,"closes":[],"values":{},"previous":{}}'::jsonb);
  END IF;
 END IF;
 RETURN state;
END $$;

CREATE FUNCTION vn_durability.provider_before(state vn_durability.runs, payload jsonb) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE transition jsonb:=payload->'transition'; before_state jsonb:=transition->'before'; after_state jsonb:=transition->'after';
 evidence jsonb:=transition->'evidence'; source jsonb:=evidence->'source'; before_source jsonb:=before_state->'source';
 after_source jsonb:=after_state->'source'; frame jsonb:=source->'frame'; history jsonb:=source->'history'; expected jsonb; bars jsonb;
 wall numeric; mono numeric; old_frame jsonb; observation jsonb:=evidence->'observation'; kind text:=evidence->>'kind'; recovery boolean;
 input_wall numeric; moment numeric; ema jsonb; label text; value jsonb;
BEGIN
 PERFORM vn_durability.exact_keys(evidence,ARRAY['kind','inputs','observation','actions','control','source']);
 PERFORM vn_durability.exact_keys(source,ARRAY['version','phase','frame','history','wall_us','monotonic_us']);
 IF source->'version' IS DISTINCT FROM '1'::jsonb OR source->'phase' IS DISTINCT FROM evidence->'kind' OR
    before_state IS DISTINCT FROM coalesce(state.engine_state,'null'::jsonb) THEN
  RAISE EXCEPTION 'provider_before_mismatch' USING ERRCODE='22023'; END IF;
 wall:=vn_durability.provider_us(source->'wall_us'); mono:=vn_durability.provider_us(source->'monotonic_us');
 input_wall:=extract(epoch FROM (evidence->'inputs'->>'wall_at')::timestamptz)*1000000;
 moment:=extract(epoch FROM (evidence->'inputs'->>'event_at')::timestamptz);
 IF input_wall IS NULL OR moment IS NULL OR wall<>input_wall OR
    mono<>vn_durability.provider_hex_us(evidence->'inputs'->'monotonic_at') THEN
  RAISE EXCEPTION 'provider_decision_clock_mismatch' USING ERRCODE='22023'; END IF;
 PERFORM vn_durability.provider_state(after_state,state.config->'source_policy'->'epoch');
 IF before_state<>'null'::jsonb THEN
  PERFORM vn_durability.provider_state(before_state,state.config->'source_policy'->'epoch');
  old_frame:=before_source->'last_quote';
  IF old_frame<>'null'::jsonb AND (wall<(old_frame->>'decision_wall_us')::numeric OR mono<(old_frame->>'decision_monotonic_us')::numeric) THEN
   RAISE EXCEPTION 'provider_clock_regressed' USING ERRCODE='22023'; END IF;
 END IF;
 recovery:=kind='control' AND evidence->'control'->>'action'='recover';
 IF kind='bootstrap' THEN
  IF before_state<>'null'::jsonb OR frame IS DISTINCT FROM 'null'::jsonb OR history='null'::jsonb OR (wall<moment*1000000 OR wall>(moment+1)*1000000) THEN
   RAISE EXCEPTION 'invalid_provider_bootstrap' USING ERRCODE='22023'; END IF;
  bars:=vn_durability.provider_history(history,NULL,true,wall,mono);
  expected:=jsonb_build_object('version',1,'epoch',state.config->'source_policy'->'epoch','quote_sequence',0,'last_quote',NULL,'bars',bars);
  -- Shape/seed binding is independent of the empty-EMA local kernel projection.
  -- PostgreSQL does not recompute the binary64 indicator recurrence.
  ema:=after_state->'engine'->'ema';
  PERFORM vn_durability.exact_keys(ema,ARRAY['count','last_end','closes','values','previous']);
  IF ema->'count' IS DISTINCT FROM '61'::jsonb OR jsonb_typeof(ema->'values') IS DISTINCT FROM 'object' OR
     jsonb_typeof(ema->'previous') IS DISTINCT FROM 'object' OR
     (SELECT count(*) FROM jsonb_object_keys(ema->'values'))<>59 OR (SELECT count(*) FROM jsonb_object_keys(ema->'previous'))<>59 OR
     EXISTS(SELECT 1 FROM generate_series(2,60) q(n) WHERE NOT (ema->'values')?n::text OR NOT (ema->'previous')?n::text) THEN
   RAISE EXCEPTION 'provider_seed_ema_shape' USING ERRCODE='22023'; END IF;
  FOR label,value IN SELECT * FROM jsonb_each(ema->'values') UNION ALL SELECT * FROM jsonb_each(ema->'previous') LOOP
   PERFORM vn_durability.rehearsal_hex(value);
   IF value#>>'{}' LIKE '-%' OR value#>>'{}'='0x0.0p+0' THEN RAISE EXCEPTION 'provider_seed_ema_shape' USING ERRCODE='22023'; END IF;
  END LOOP;
 ELSE
  expected:=before_source; bars:=before_source->'bars';
  IF old_frame='null'::jsonb AND after_state->'engine'->'ema' IS DISTINCT FROM before_state->'engine'->'ema' THEN
   RAISE EXCEPTION 'provider_prequote_seed_changed' USING ERRCODE='22023'; END IF;
  IF kind='protective' THEN
   PERFORM vn_durability.provider_frame(frame);
   IF history IS DISTINCT FROM 'null'::jsonb OR (frame->>'sequence')::integer<>(before_source->>'quote_sequence')::integer+1 THEN
    RAISE EXCEPTION 'provider_protection_sequence' USING ERRCODE='22023'; END IF;
   IF old_frame<>'null'::jsonb AND ((frame->>'decision_second')::numeric<=(old_frame->>'decision_second')::numeric OR
      (frame->>'decision_wall_us')::numeric<(old_frame->>'decision_wall_us')::numeric OR
      (frame->>'decision_monotonic_us')::numeric<(old_frame->>'decision_monotonic_us')::numeric OR
      (frame->'quote'->>'block_ref')::numeric<=(old_frame->'quote'->>'block_ref')::numeric OR
      (frame->'quote'->>'estimated_source_second')::numeric<(old_frame->'quote'->>'estimated_source_second')::numeric OR
      (frame->'quote'->'document'->>'received_wall_us')::numeric<(old_frame->'quote'->'document'->>'received_wall_us')::numeric OR
      (frame->'quote'->'document'->>'received_monotonic_us')::numeric<=(old_frame->'quote'->'document'->>'received_monotonic_us')::numeric) THEN
    RAISE EXCEPTION 'provider_source_regressed' USING ERRCODE='22023'; END IF;
   IF old_frame<>'null'::jsonb AND (frame->'quote'->>'source_age_floor_us')::numeric < greatest(0,
      greatest(0,(frame->'quote'->'document'->>'received_wall_us')::numeric-(old_frame->'quote'->>'estimated_source_second')::numeric*1000000,
       greatest(0,(old_frame->'quote'->'document'->>'received_wall_us')::numeric-(old_frame->'quote'->>'estimated_source_second')::numeric*1000000,
        (old_frame->'quote'->>'source_age_floor_us')::numeric)+(frame->'quote'->'document'->>'received_monotonic_us')::numeric-
        (old_frame->'quote'->'document'->>'received_monotonic_us')::numeric)-
       ((frame->'quote'->>'estimated_source_second')::numeric-(old_frame->'quote'->>'estimated_source_second')::numeric)*1000000) THEN
    RAISE EXCEPTION 'provider_age_floor_regressed' USING ERRCODE='22023'; END IF;
   expected:=expected||jsonb_build_object('quote_sequence',frame->'sequence','last_quote',frame);
  ELSIF kind='decision' OR recovery THEN
   IF frame IS DISTINCT FROM old_frame OR frame='null'::jsonb THEN RAISE EXCEPTION 'provider_unprotected_quote' USING ERRCODE='22023'; END IF;
   IF history<>'null'::jsonb THEN bars:=vn_durability.provider_history(history,bars,false,wall,mono); END IF;
   IF (recovery OR before_state->'engine'->'lifecycle'->'risk'->'active'='false'::jsonb) AND
      (bars->-1->>0)::numeric<>floor((wall-5000000)/900000000)*900 THEN
    RAISE EXCEPTION 'provider_history_stale' USING ERRCODE='22023'; END IF;
   IF NOT recovery AND before_state->'engine'->'lifecycle'->'risk'->'active'='true'::jsonb AND history<>'null'::jsonb THEN
    RAISE EXCEPTION 'provider_halted_history' USING ERRCODE='22023'; END IF;
   expected:=expected||jsonb_build_object('bars',bars);
  ELSIF kind='control' THEN
   IF frame IS DISTINCT FROM 'null'::jsonb OR history IS DISTINCT FROM 'null'::jsonb OR (wall<moment*1000000 OR wall>(moment+1)*1000000) THEN
    RAISE EXCEPTION 'provider_control_source' USING ERRCODE='22023'; END IF;
  ELSE RAISE EXCEPTION 'invalid_provider_phase' USING ERRCODE='22023'; END IF;
 END IF;
 IF expected IS DISTINCT FROM after_source THEN RAISE EXCEPTION 'provider_after_mismatch' USING ERRCODE='22023'; END IF;
 IF frame<>'null'::jsonb THEN
  PERFORM vn_durability.provider_fresh_frame(frame,wall,mono);
  IF moment IS DISTINCT FROM (frame->>'decision_second')::numeric OR observation->'timestamp' IS DISTINCT FROM frame->'decision_second' OR
     observation->'price' IS DISTINCT FROM frame->'quote'->'price' THEN
   RAISE EXCEPTION 'provider_economic_quote_mismatch' USING ERRCODE='22023'; END IF;
  IF kind='protective' THEN
   IF observation->'candle_end' IS DISTINCT FROM 'null'::jsonb OR observation->'candle_close' IS DISTINCT FROM 'null'::jsonb THEN
    RAISE EXCEPTION 'provider_protection_candle' USING ERRCODE='22023'; END IF;
  ELSIF history<>'null'::jsonb OR recovery THEN
   IF observation->'candle_end' IS DISTINCT FROM bars->-1->0 OR observation->'candle_close' IS DISTINCT FROM bars->-1->1 THEN
    RAISE EXCEPTION 'provider_candle_projection' USING ERRCODE='22023'; END IF;
  ELSIF observation->'candle_end' IS DISTINCT FROM 'null'::jsonb OR observation->'candle_close' IS DISTINCT FROM 'null'::jsonb THEN
   RAISE EXCEPTION 'provider_unbound_candle' USING ERRCODE='22023'; END IF;
 END IF;
END $$;

CREATE FUNCTION vn_durability.provider_server_fresh(payload jsonb) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE source jsonb:=payload->'transition'->'evidence'->'source'; doc jsonb; wall numeric:=ceil(extract(epoch FROM clock_timestamp())*1000000);
BEGIN
 IF wall<(source->>'wall_us')::numeric THEN RAISE EXCEPTION 'provider_decision_future' USING ERRCODE='22023'; END IF;
 IF source->'frame'<>'null'::jsonb THEN PERFORM vn_durability.provider_fresh_frame(source->'frame',wall,NULL,true); END IF;
 IF source->'history'<>'null'::jsonb THEN
  FOR doc IN SELECT v FROM jsonb_array_elements(source->'history'->'documents') q(v) LOOP
   PERFORM vn_durability.provider_receipt(doc,wall,NULL,true);
  END LOOP;
 END IF;
END $$;
-- Canonical v5 admission and journaling. Private helpers are extracted separately.
-- Review this source; build.py never synthesizes public economic admission.

CREATE FUNCTION vn_durability.record_command(
  owner_id uuid, run uuid, command_id uuid, sequence bigint,
  command_kind text, request_body jsonb, result jsonb
) RETURNS void LANGUAGE sql SET search_path = pg_catalog, vn_durability, pg_temp AS $$
  INSERT INTO vn_durability.commands(run_id,user_id,id,revision,kind,request,request_hash,response)
  VALUES (run,owner_id,command_id,sequence,command_kind,request_body,
          sha256(convert_to(request_body::text,'UTF8')),result);
  INSERT INTO vn_durability.outbox_progress(run_id,user_id)
    SELECT run,owner_id WHERE command_kind='create' AND request_body#>>'{config,durability_contract_version}' ='5';
  INSERT INTO vn_durability.outbox_events(run_id,user_id,command_id,revision,event_index,event)
    SELECT run,owner_id,command_id,sequence,(ordinal-1)::integer,value
      FROM jsonb_array_elements(CASE WHEN command_kind='batch' AND request_body#>>'{payload,version}' ='5'
        THEN request_body#>'{payload,transition,events}' ELSE '[]'::jsonb END) WITH ORDINALITY q(value,ordinal);
$$;

CREATE FUNCTION vn_durability.create_run(
  owner_id uuid, run uuid, worker uuid, command_id uuid, configuration jsonb,
  initial_cash text, lease_seconds integer DEFAULT 30
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE amount numeric; request_body jsonb; result jsonb;
        existing vn_durability.commands%ROWTYPE; inserted uuid;
BEGIN
  IF owner_id IS NULL OR run IS NULL OR worker IS NULL OR command_id IS NULL OR
     lease_seconds IS NULL OR lease_seconds NOT BETWEEN 1 AND 120 OR
     configuration IS NULL OR jsonb_typeof(configuration) IS DISTINCT FROM 'object' OR
     octet_length(configuration::text) > 65536 THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE = '22023';
  END IF;
  amount := vn_durability.money(to_jsonb(initial_cash));
  IF amount <= 0 THEN RAISE EXCEPTION 'invalid_amount' USING ERRCODE = '22023'; END IF;
  PERFORM vn_durability.provider_config(configuration);
  IF initial_cash IS DISTINCT FROM configuration->'rehearsal'->>'initial_cash' THEN
    RAISE EXCEPTION 'rehearsal_initial_cash_mismatch' USING ERRCODE='22023';
  END IF;
  request_body := jsonb_build_object('kind','create','owner_id',owner_id,'run_id',run,'command_id',command_id,
                                     'worker',worker,'config',configuration,
                                     'initial_cash',initial_cash,'lease_seconds',lease_seconds);
  INSERT INTO vn_durability.runs(id,user_id,worker_id,fence,revision,lease_until,status,config,command_version,initial_cash,reserve)
  VALUES (run,owner_id,worker,1,1,clock_timestamp()+make_interval(secs=>lease_seconds),
          'starting',configuration,5,amount,amount)
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
        entity uuid; account_id uuid; cash numeric; quantity numeric;
        notional numeric; fee numeric; close_proceeds numeric; next_status text;
        execution jsonb; first_trip numeric; risk_blocked boolean:=false;
        observed_equity numeric; risk_threshold numeric; risk_price jsonb;
        model_state vn_durability.runs; model_payload jsonb;
BEGIN
  IF owner_id IS NULL OR run IS NULL OR worker IS NULL OR token IS NULL OR token < 1 OR
     expected_revision IS NULL OR expected_revision < 1 OR command_id IS NULL OR
     payload IS NULL OR octet_length(payload::text) > 262144 THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.exact_keys(payload,ARRAY['version','operations','transition']);
  IF payload->'version' IS DISTINCT FROM '5'::jsonb OR
     jsonb_typeof(payload->'operations') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  IF jsonb_array_length(payload->'operations') NOT BETWEEN 0 AND 1024 THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  request_body := jsonb_build_object('kind','batch','owner_id',owner_id,'run_id',run,'command_id',command_id,
                                     'worker',worker,'fence',token,
                                     'expected_revision',expected_revision,'payload',payload);
  SELECT * INTO state FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
  IF state.command_version<>5 THEN RAISE EXCEPTION 'contract_version_mismatch' USING ERRCODE='22023'; END IF;
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

  PERFORM vn_durability.provider_before(state,payload);
  PERFORM vn_durability.provider_server_fresh(payload);
  model_state:=vn_durability.provider_model_run(state);
  model_payload:=vn_durability.provider_model_payload(payload);
  PERFORM vn_durability.validate_lifecycle_before(model_state,model_payload);
  risk_blocked:=coalesce(state.engine_state->'engine'->'lifecycle'->'risk'->'active'='true'::jsonb,false);
  risk_price:=payload->'transition'->'after'->'engine'->'last_quote'->'price';
  risk_threshold:=state.initial_cash*1e36*(10000-(state.config->'rehearsal'->'lifecycle_policy'->>'account_loss_bps')::numeric);
  IF payload->'transition'->'evidence'->>'kind'='protective' AND NOT risk_blocked THEN
    observed_equity:=vn_durability.lifecycle_equity(run,state.reserve,risk_price);
    IF observed_equity*10000<=risk_threshold THEN first_trip:=observed_equity; risk_blocked:=true; END IF;
  END IF;

  FOR operation IN SELECT value FROM jsonb_array_elements(payload->'operations') WITH ORDINALITY q(value,ordinal) ORDER BY ordinal LOOP
    operation_kind := operation->>'kind';
    IF risk_blocked AND operation_kind IN ('open','birth','distribution') THEN
      RAISE EXCEPTION 'lifecycle_risk_admission_blocked' USING ERRCODE='22023';
    END IF;
    IF state.status IN ('stopped','failed') THEN RAISE EXCEPTION 'run_terminal' USING ERRCODE='P0001'; END IF;
    IF operation_kind = 'birth' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','cash','lineage']);
      entity := vn_durability.canonical_id(operation->'id');
      cash := vn_durability.money(operation->'cash');
      IF entity IS NULL OR cash <= 0 OR cash > state.reserve THEN
        RAISE EXCEPTION 'invalid_birth' USING ERRCODE='22023';
      END IF;
      IF state.status IN ('paused','risk_halted') THEN
        RAISE EXCEPTION 'invalid_birth' USING ERRCODE='22023';
      END IF;
      INSERT INTO vn_durability.accounts(run_id,user_id,id,cash,initial_cash) VALUES(run,owner_id,entity,cash,cash);
      IF operation->'lineage'->'version'='2'::jsonb THEN
        PERFORM vn_durability.record_restart_lineage(owner_id,run,entity,operation->'lineage');
      ELSE
        PERFORM vn_durability.record_lineage(owner_id,run,entity,operation->'lineage');
      END IF;
      state.reserve := state.reserve-cash;
    ELSIF operation_kind='distribution' THEN
      IF state.status IN ('paused','risk_halted') THEN RAISE EXCEPTION 'invalid_distribution' USING ERRCODE='22023'; END IF;
      PERFORM vn_durability.record_distribution(owner_id,run,operation);
    ELSIF operation_kind = 'open' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','account_id','asset','quantity','notional','fee','execution']);
      execution:=vn_durability.entry_evidence(operation->'execution');
      IF execution->'config' IS DISTINCT FROM state.config->'execution'->'config' OR
         operation->'quantity' IS DISTINCT FROM execution->'quantity' OR
         operation->'notional' IS DISTINCT FROM execution->'notional' OR operation->'fee' IS DISTINCT FROM execution->'fee' THEN
        RAISE EXCEPTION 'entry_evidence_mismatch' USING ERRCODE='22023';
      END IF;
      entity := vn_durability.canonical_id(operation->'id');
      account_id := vn_durability.canonical_id(operation->'account_id');
      quantity := vn_durability.money(operation->'quantity');
      notional := vn_durability.money(operation->'notional'); fee := vn_durability.money(operation->'fee');
      SELECT * INTO account FROM vn_durability.accounts a WHERE a.run_id=run AND a.id=account_id AND a.user_id=owner_id;
      IF NOT FOUND OR account.retired OR entity IS NULL OR quantity <= 0 OR notional <= 0 OR
         notional+fee > account.cash OR state.status <> 'running' OR
         ((execution->>'budget')::numeric>account.cash) OR
         jsonb_typeof(operation->'asset') IS DISTINCT FROM 'string' OR
         length(operation->>'asset') NOT BETWEEN 1 AND 64 THEN
        RAISE EXCEPTION 'invalid_open' USING ERRCODE='22023';
      END IF;
      INSERT INTO vn_durability.positions(run_id,user_id,id,account_id,asset,quantity,notional,entry_fee,entry_execution)
      VALUES(run,owner_id,entity,account_id,operation->>'asset',quantity,notional,fee,execution);
      UPDATE vn_durability.accounts a SET cash=a.cash-notional-fee WHERE a.run_id=run AND a.id=account_id;
    ELSIF operation_kind = 'close' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','proceeds','fee','execution']);
      entity := vn_durability.canonical_id(operation->'id');
      close_proceeds := vn_durability.money(operation->'proceeds'); fee := vn_durability.money(operation->'fee');
      SELECT * INTO position FROM vn_durability.positions p WHERE p.run_id=run AND p.id=entity AND p.user_id=owner_id;
      IF NOT FOUND OR position.closed OR fee > close_proceeds THEN RAISE EXCEPTION 'invalid_close' USING ERRCODE='22023'; END IF;
      execution:=vn_durability.exit_evidence(operation->'execution',position.entry_execution);
      IF operation->'proceeds' IS DISTINCT FROM execution->'notional' OR operation->'fee' IS DISTINCT FROM execution->'fee' THEN
        RAISE EXCEPTION 'exit_evidence_mismatch' USING ERRCODE='22023';
      END IF;
      UPDATE vn_durability.positions p SET closed=true,proceeds=close_proceeds,exit_fee=fee,exit_execution=execution
        WHERE p.run_id=run AND p.id=entity;
      UPDATE vn_durability.accounts a SET cash=a.cash+close_proceeds-fee WHERE a.run_id=run AND a.id=position.account_id;
    ELSIF operation_kind = 'retire' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id']);
      entity := vn_durability.canonical_id(operation->'id');
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
      -- Recovery still requires the complete provider/lifecycle control evidence.
      IF state.status='risk_halted' AND next_status NOT IN ('risk_halted','stopped','failed') AND NOT
         (next_status='running' AND payload->'transition'->'evidence'->>'kind'='control' AND
          payload->'transition'->'evidence'->'control'->>'action'='recover') THEN
        RAISE EXCEPTION 'risk_recovery_unavailable' USING ERRCODE='P0001';
      END IF;
      IF next_status='risk_halted' AND first_trip IS NULL THEN RAISE EXCEPTION 'unjustified_risk_halt' USING ERRCODE='22023'; END IF;
      IF state.status='risk_halted' AND next_status='running' THEN risk_blocked:=false; END IF;
      state.status := next_status;
      IF next_status IN ('stopped','failed') THEN state.requires_reconciliation := true; END IF;
    ELSE
      RAISE EXCEPTION 'invalid_operation' USING ERRCODE='22023';
    END IF;
    IF operation_kind IN ('open','close') AND NOT risk_blocked THEN
      observed_equity:=vn_durability.lifecycle_equity(run,state.reserve,risk_price);
      IF observed_equity*10000<=risk_threshold THEN first_trip:=observed_equity; risk_blocked:=true; END IF;
    END IF;
  END LOOP;

  model_state:=vn_durability.provider_model_run(state);
  PERFORM vn_durability.validate_lifecycle_after(model_state,model_payload,first_trip);
  -- Server freshness after every economic effect is still statement atomic.
  PERFORM vn_durability.provider_server_fresh(payload);
  state.engine_state:=payload->'transition'->'after';

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
                r.command_version=5 AND through_revision<=r.revision) THEN
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

RESET ROLE;
CREATE SCHEMA vn_projection AUTHORIZATION vn_contract_owner;
CREATE SCHEMA vn_read AUTHORIZATION vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM vn_durability.commands) THEN
  RAISE EXCEPTION 'fresh_contract_required_no_async_backfill';
 END IF;
END $$;

CREATE TABLE vn_projection.runs (
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=8192),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE INDEX runs_owner_page ON vn_projection.runs(user_id,run_id,revision,entity_key);
ALTER TABLE vn_projection.runs ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.probes (
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=4096),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE INDEX probes_owner_page ON vn_projection.probes(user_id,run_id,revision,entity_key);
CREATE INDEX probes_entity_versions ON vn_projection.probes(run_id,entity_key,revision DESC);
ALTER TABLE vn_projection.probes ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.trades (
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=8192),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE INDEX trades_owner_page ON vn_projection.trades(user_id,run_id,revision,entity_key);
CREATE INDEX trades_entity_versions ON vn_projection.trades(run_id,(data->>'id'),revision DESC,entity_key DESC);
ALTER TABLE vn_projection.trades ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.samples (
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=4096),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE INDEX samples_owner_page ON vn_projection.samples(user_id,run_id,revision,entity_key);
ALTER TABLE vn_projection.samples ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.evaluations (
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=32768),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE INDEX evaluations_owner_page ON vn_projection.evaluations(user_id,run_id,revision,entity_key);
ALTER TABLE vn_projection.evaluations ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.relay_events (
 sequence bigint NOT NULL CHECK(sequence>0),
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=4096),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE UNIQUE INDEX relay_events_owner_page ON vn_projection.relay_events(user_id,run_id,sequence);
CREATE UNIQUE INDEX relay_events_identity ON vn_projection.relay_events(run_id,entity_key);
ALTER TABLE vn_projection.relay_events ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.archives (
 user_id uuid NOT NULL, run_id uuid NOT NULL, expected_revision bigint NOT NULL,
 request_id uuid NOT NULL, archived_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 receipt jsonb NOT NULL CHECK(jsonb_typeof(receipt)='object' AND octet_length(receipt::text)<=2048),
 PRIMARY KEY(user_id,request_id), UNIQUE(run_id),
 FOREIGN KEY(run_id,user_id) REFERENCES vn_durability.runs(id,user_id)
);
ALTER TABLE vn_projection.archives ENABLE ROW LEVEL SECURITY;

-- Called only by the journal INSERT trigger under the trusted command owner.
-- Never project from socket events, browser payloads or asynchronously mutated state.
CREATE FUNCTION vn_projection.project_command() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE state vn_durability.runs%ROWTYPE; transition jsonb; before_state jsonb; after_state jsonb;
 member jsonb; prior jsonb; account jsonb; operation jsonb; action jsonb; item jsonb; position jsonb;
 working_cash jsonb:='{}'::jsonb; terminal_cash jsonb:='{}'::jsonb;
 row_data jsonb; old_data jsonb; entity uuid; cash numeric; equity numeric; mark numeric;
 stamp jsonb; source_stamp jsonb; index integer:=0; observation jsonb; evaluation jsonb; cohort jsonb;
 run_equity numeric; open_count integer;
BEGIN
 SELECT * INTO STRICT state FROM vn_durability.runs WHERE id=NEW.run_id AND user_id=NEW.user_id;
 IF state.command_version NOT IN(3,4,5) THEN RETURN NEW; END IF;
 IF state.revision<>NEW.revision THEN RAISE EXCEPTION 'projection_revision_mismatch'; END IF;
 transition:=NEW.request#>'{payload,transition}';
 before_state:=transition->'before'; after_state:=transition->'after';
 observation:=transition#>'{evidence,observation}';
 stamp:=transition#>'{evidence,inputs,market_at}';
 IF stamp IS NULL THEN stamp:=transition#>'{evidence,inputs,quote_at}'; END IF;
 -- Event timestamps are validated by the underlying transition contract.
 source_stamp:=after_state#>'{engine,last_quote,timestamp}';
 IF observation IS NOT NULL AND observation<>'null'::jsonb THEN mark:=(observation->>'price')::numeric;
 ELSE mark:=(after_state#>>'{engine,last_quote,price}')::numeric; END IF;
 IF NEW.kind='batch' THEN
  IF after_state IS NULL OR after_state->>'run_id'<>NEW.run_id::text OR (after_state->>'revision')::bigint<>NEW.revision
   THEN RAISE EXCEPTION 'projection_checkpoint_mismatch'; END IF;
  FOR account IN SELECT v FROM jsonb_array_elements(coalesce(before_state->'accounts','[]'::jsonb)) q(v) LOOP
   working_cash:=jsonb_set(working_cash,ARRAY[account->>'id'],account->'cash');
  END LOOP;
  FOR operation IN SELECT v FROM jsonb_array_elements(NEW.request#>'{payload,operations}') q(v) LOOP
   entity:=(operation->>'id')::uuid;
   action:=transition#>'{evidence,actions}'->index;
   IF action->>'operation_index' IS DISTINCT FROM index::text THEN RAISE EXCEPTION 'projection_action_mismatch'; END IF;
   stamp:=transition->'events'->index->'at';
   -- Event order is not operation order when evaluation precedes retirements.
   SELECT v->'at' INTO stamp FROM jsonb_array_elements(transition->'events') q(v)
    WHERE v->>'operation_index'=index::text;
   IF operation->>'kind'='birth' THEN
    working_cash:=jsonb_set(working_cash,ARRAY[entity::text],operation->'cash');
   ELSIF operation->>'kind'='open' THEN
    cash:=(working_cash->>(operation->>'account_id'))::numeric-(operation->>'notional')::numeric-(operation->>'fee')::numeric;
    working_cash:=jsonb_set(working_cash,ARRAY[operation->>'account_id'],to_jsonb(cash::text));
    row_data:=jsonb_build_object('id',entity,'account_id',operation->'account_id','asset',operation->'asset',
     'opened_at',stamp,'closed_at',NULL,'entry_reason',action->'reason','exit_reason',NULL,
     'quantity',operation->'quantity','entry',operation->'execution','exit',NULL,'closed',false,
     'account_currency','USD','cost_assumptions','uncalibrated_scenario');
    INSERT INTO vn_projection.trades VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,entity::text||':'||lpad(index::text,4,'0'),row_data);
   ELSIF operation->>'kind'='close' THEN
    SELECT to_jsonb(p) INTO STRICT position FROM vn_durability.positions p WHERE p.run_id=NEW.run_id AND p.id=entity;
    cash:=(working_cash->>(position->>'account_id'))::numeric+(operation->>'proceeds')::numeric-(operation->>'fee')::numeric;
    working_cash:=jsonb_set(working_cash,ARRAY[position->>'account_id'],to_jsonb(cash::text));
    SELECT data INTO STRICT old_data FROM vn_projection.trades WHERE run_id=NEW.run_id AND data->>'id'=entity::text ORDER BY revision DESC,entity_key DESC LIMIT 1;
    row_data:=old_data||jsonb_build_object('closed',true,'closed_at',stamp,'exit_reason',action->'reason','exit',operation->'execution');
    INSERT INTO vn_projection.trades VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,entity::text||':'||lpad(index::text,4,'0'),row_data);
   ELSIF operation->>'kind'='retire' THEN
    IF NOT working_cash ? entity::text THEN RAISE EXCEPTION 'projection_missing_terminal_cash'; END IF;
    terminal_cash:=jsonb_set(terminal_cash,ARRAY[entity::text],working_cash->entity::text);
    working_cash:=jsonb_set(working_cash,ARRAY[entity::text],to_jsonb('0'::text));
   END IF;
   index:=index+1;
  END LOOP;
  -- Validate reconstruction before retaining the pre-transfer terminal values.
  FOR account IN SELECT v FROM jsonb_array_elements(after_state->'accounts') q(v) LOOP
   IF (working_cash->>(account->>'id'))::numeric IS DISTINCT FROM (account->>'cash')::numeric THEN
    RAISE EXCEPTION 'projection_cash_reconstruction_mismatch';
   END IF;
  END LOOP;
  FOR member IN SELECT v FROM jsonb_array_elements(after_state#>'{engine,members}') q(v) LOOP
   entity:=(member->>'id')::uuid;
   SELECT v INTO STRICT account FROM jsonb_array_elements(after_state->'accounts') q(v) WHERE v->>'id'=entity::text;
   SELECT data INTO old_data FROM vn_projection.probes WHERE run_id=NEW.run_id AND entity_key=entity::text ORDER BY revision DESC LIMIT 1;
   equity:=(account->>'cash')::numeric;
   IF mark IS NOT NULL THEN
    SELECT equity+coalesce(sum(p.quantity*mark),0) INTO equity FROM vn_durability.positions p
     WHERE p.run_id=NEW.run_id AND p.account_id=entity AND NOT p.closed;
   END IF;
   row_data:=jsonb_build_object('id',entity,'name',member->'name','generation',member#>'{genome,generation}',
    'genome',member->'genome','initial_cash',account->'initial_cash','economic_cash',account->'cash',
    'retired',account->'retired','terminal_cash',coalesce(terminal_cash->entity::text,member#>'{terminal,cash}',old_data->'terminal_cash','null'::jsonb),
    'equity',CASE WHEN account->>'retired'='true' THEN NULL ELSE equity::text END,
    'equity_basis',CASE WHEN account->>'retired'='true' THEN 'terminal_frozen' WHEN mark IS NULL THEN 'cash_without_market_mark' ELSE 'reference_mark' END,
    'metrics_basis','checkpoint_member','peak_equity',member->'peak_equity','max_drawdown',member->'max_drawdown','closed_trades',member->'num_trades',
    'terminal',member->'terminal','account_currency','USD','mark',CASE WHEN mark IS NULL THEN NULL ELSE mark::text END,
    'source_at',source_stamp,'fitness',NULL,'fitness_availability','evaluation_only',
    'lineage',(SELECT evidence FROM vn_durability.account_lineage WHERE run_id=NEW.run_id AND account_id=entity));
   INSERT INTO vn_projection.probes VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,entity::text,row_data);
   IF transition#>>'{evidence,kind}'='protective' THEN
    INSERT INTO vn_projection.samples VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,entity::text,
     jsonb_build_object('id',entity,'at',source_stamp,'equity',row_data->'equity','terminal_cash',row_data->'terminal_cash',
      'economic_cash',account->'cash','mark',row_data->'mark','account_currency','USD','sampling_policy','post_protection_pre_decision_v1',
      'equity_basis',row_data->'equity_basis','quote_sequence',after_state#>'{source,quote_sequence}'));
   END IF;
  END LOOP;
  -- Members removed by replacement require immutable terminal versions too.
  FOR member IN SELECT v FROM jsonb_array_elements(coalesce(before_state#>'{engine,members}','[]'::jsonb)) q(v)
   WHERE NOT EXISTS(SELECT 1 FROM jsonb_array_elements(after_state#>'{engine,members}') q2(m) WHERE m->>'id'=v->>'id') LOOP
   entity:=(member->>'id')::uuid;
   SELECT data INTO STRICT old_data FROM vn_projection.probes WHERE run_id=NEW.run_id AND entity_key=entity::text ORDER BY revision DESC LIMIT 1;
   IF NOT terminal_cash ? entity::text AND old_data->'terminal_cash'='null'::jsonb THEN RAISE EXCEPTION 'projection_missing_retirement_evidence'; END IF;
   row_data:=old_data||jsonb_build_object('economic_cash','0','equity',NULL,'retired',true,
     'terminal_cash',coalesce(terminal_cash->entity::text,old_data->'terminal_cash'),
     'equity_basis','terminal_frozen','metrics_basis','last_observed_before_replacement','terminal',coalesce(member->'terminal','null'::jsonb));
   INSERT INTO vn_projection.probes VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,entity::text,row_data);
  END LOOP;
  evaluation:=after_state#>'{engine,last_evaluation}';
  IF evaluation IS NOT NULL AND evaluation<>'null'::jsonb AND evaluation IS DISTINCT FROM before_state#>'{engine,last_evaluation}' THEN
   cohort:=evaluation->'cohort';
   row_data:=jsonb_build_object('cohort',cohort,'selection',evaluation->'selection','account_currency','USD',
    'scoring_policy','tagged_worker_evaluation_v1','terminal_accounts',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',entity_key,
      'terminal_cash',data->'terminal_cash','initial_cash',data->'initial_cash') ORDER BY entity_key),'[]'::jsonb)
     FROM vn_projection.probes WHERE run_id=NEW.run_id AND revision=NEW.revision AND cohort->'member_ids' ? entity_key));
   INSERT INTO vn_projection.evaluations VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,cohort->>'iteration_id',row_data);
  END IF;
 END IF;
 -- Interrupts retain the last checkpoint but explicitly change authority/status.
 SELECT count(*) INTO open_count FROM vn_durability.positions WHERE run_id=NEW.run_id AND NOT closed;
 run_equity:=NULL;
 IF mark IS NOT NULL AND NEW.kind='batch' THEN
  SELECT state.reserve+coalesce((SELECT sum(a.cash) FROM vn_durability.accounts a WHERE a.run_id=NEW.run_id),0)
   +coalesce((SELECT sum(quantity*mark) FROM vn_durability.positions WHERE run_id=NEW.run_id AND NOT closed),0) INTO run_equity;
 END IF;
 row_data:=jsonb_build_object('id',NEW.run_id,'status',state.status,'requires_reconciliation',state.requires_reconciliation,
  'durability_version',state.command_version,'mode','paper',
  'strategy',state.config#>'{rehearsal,strategy}','asset',state.config#>'{rehearsal,asset}',
  'execution_policy',state.config->'execution','code_version',state.config#>'{rehearsal,code_version}',
  'initial_cash',state.initial_cash::text,'reserve',state.reserve::text,'reference_equity',run_equity::text,
  'equity_availability',CASE WHEN run_equity IS NULL THEN 'unavailable' ELSE 'reference_mark' END,
  'account_currency','USD','generation',state.engine_state#>'{engine,generation}',
  'total_probe_count',(SELECT count(*) FROM vn_durability.accounts WHERE run_id=NEW.run_id),
  'active_probe_count',(SELECT count(*) FROM vn_durability.accounts WHERE run_id=NEW.run_id AND NOT retired),
  'open_position_count',open_count,'retained_exposure',open_count>0,'created_at',state.created_at,
  'committed_at',NEW.committed_at,'source_at',source_stamp,'source_policy',state.config->'source_policy');
 INSERT INTO vn_projection.runs VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,NEW.run_id::text,row_data);
 RETURN NEW;
END $$;
CREATE TRIGGER project_command AFTER INSERT ON vn_durability.commands FOR EACH ROW EXECUTE FUNCTION vn_projection.project_command();

-- Authenticated owner comes from the JWT, never a caller-supplied owner argument.
-- Pages expose bounded curated projections, not commands/checkpoints/optimizer graphs.
CREATE FUNCTION vn_read.page(run uuid, kind text, through_revision bigint DEFAULT NULL,
 after_revision bigint DEFAULT 0, after_key text DEFAULT '', max_rows integer DEFAULT 100,
 max_bytes integer DEFAULT 65536) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE owner_id uuid:=vn_identity.owner_id(); snapshot bigint; relation text; row record; result jsonb;
 records jsonb:='[]'::jsonb; candidate jsonb; more boolean:=false; cursor jsonb:='null'::jsonb;
BEGIN
 IF owner_id IS NULL OR run IS NULL OR after_revision IS NULL OR after_revision<0 OR after_key IS NULL OR octet_length(after_key)>256 OR
  (after_revision=0 AND after_key<>'') OR max_rows IS NULL OR max_rows NOT BETWEEN 1 AND 100 OR
  max_bytes IS NULL OR max_bytes NOT BETWEEN 512 AND 65536 THEN RAISE EXCEPTION 'invalid_read_page' USING ERRCODE='22023'; END IF;
 IF kind NOT IN('runs','probes','trades','samples','evaluations') OR kind IS NULL THEN
  RAISE EXCEPTION 'invalid_read_kind' USING ERRCODE='22023'; END IF;
 SELECT revision INTO snapshot FROM vn_durability.runs WHERE id=run AND user_id=owner_id;
 IF snapshot IS NULL THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
 snapshot:=coalesce(through_revision,snapshot);
 IF snapshot<1 OR snapshot>(SELECT revision FROM vn_durability.runs WHERE id=run AND user_id=owner_id) OR after_revision>snapshot THEN
  RAISE EXCEPTION 'invalid_read_revision' USING ERRCODE='22023'; END IF;
 relation:=kind;
 result:=jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,'kind',kind,
  'through_revision',snapshot,'records',records,'has_more',false,'next_cursor',cursor);
 FOR row IN EXECUTE format('SELECT revision,command_id,entity_key,data FROM vn_projection.%I WHERE user_id=$1 AND run_id=$2 AND revision<=$3 AND (revision,entity_key)>($4,$5) ORDER BY revision,entity_key LIMIT $6',relation)
 USING owner_id,run,snapshot,after_revision,after_key,max_rows+1 LOOP
  IF jsonb_array_length(records)=max_rows THEN more:=true; EXIT; END IF;
  candidate:=jsonb_set(result,'{records}',records||jsonb_build_array(jsonb_build_object('revision',row.revision,'command_id',row.command_id,'key',row.entity_key,'data',row.data)));
  cursor:=jsonb_build_object('revision',row.revision,'key',row.entity_key);
  candidate:=jsonb_set(candidate,'{next_cursor}',cursor);
  IF octet_length(candidate::text)>max_bytes THEN
   IF records='[]'::jsonb THEN RAISE EXCEPTION 'read_record_exceeds_page' USING ERRCODE='22023'; END IF;
   more:=true; EXIT;
  END IF;
  records:=candidate->'records'; result:=candidate;
 END LOOP;
 RETURN jsonb_set(result,'{has_more}',to_jsonb(more));
END $$;

-- Sequence is allocated under the same run lock as commands. Delayed acceptance
-- cannot add an event below a previously returned replay cutoff/cursor.
CREATE FUNCTION vn_read.accept_event(owner_id uuid, run uuid, command_id uuid, event_index integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE item vn_durability.outbox_events%ROWTYPE; identity text; receipt jsonb; seq bigint;
BEGIN
 IF owner_id IS NULL OR run IS NULL OR command_id IS NULL OR event_index IS NULL OR event_index NOT BETWEEN 0 AND 1024 THEN
  RAISE EXCEPTION 'invalid_relay_event' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'relay_event_unavailable' USING ERRCODE='P0001'; END IF;
 SELECT * INTO item FROM vn_durability.outbox_events e WHERE e.user_id=owner_id AND e.run_id=run AND e.command_id=accept_event.command_id AND e.event_index=accept_event.event_index;
 IF NOT FOUND THEN RAISE EXCEPTION 'relay_event_unavailable' USING ERRCODE='P0001'; END IF;
 identity:=run::text||':'||command_id::text||':'||event_index::text;
 SELECT sequence INTO seq FROM vn_projection.relay_events WHERE run_id=run AND entity_key=identity;
 IF seq IS NULL THEN
  SELECT coalesce(max(sequence),0)+1 INTO seq FROM vn_projection.relay_events WHERE user_id=owner_id AND run_id=run;
  INSERT INTO vn_projection.relay_events VALUES(seq,owner_id,run,item.revision,command_id,identity,
   jsonb_build_object('event_id',identity,'event_index',event_index,'event',item.event));
 END IF;
 IF NOT EXISTS(SELECT 1 FROM vn_projection.relay_events WHERE run_id=run AND revision=item.revision AND entity_key=identity
   AND user_id=owner_id AND data=jsonb_build_object('event_id',identity,'event_index',event_index,'event',item.event)) THEN
  RAISE EXCEPTION 'relay_event_conflict' USING ERRCODE='P0001'; END IF;
 receipt:=jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,'command_id',command_id,'event_index',event_index,'event_id',identity,'revision',item.revision,'sequence',seq,'accepted',true);
 RETURN receipt;
END $$;

CREATE FUNCTION vn_read.events(run uuid, through_sequence bigint DEFAULT NULL,
 after_sequence bigint DEFAULT 0, max_rows integer DEFAULT 100, max_bytes integer DEFAULT 65536)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE owner_id uuid:=vn_identity.owner_id(); snapshot bigint; latest bigint; row record; result jsonb; candidate jsonb;
 records jsonb:='[]'::jsonb; more boolean:=false;
BEGIN
 IF owner_id IS NULL OR run IS NULL OR after_sequence IS NULL OR after_sequence<0 OR
  max_rows IS NULL OR max_rows NOT BETWEEN 1 AND 100 OR max_bytes IS NULL OR max_bytes NOT BETWEEN 512 AND 65536 THEN
  RAISE EXCEPTION 'invalid_event_page' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM vn_durability.runs WHERE id=run AND user_id=owner_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
 SELECT coalesce(max(sequence),0) INTO latest FROM vn_projection.relay_events WHERE user_id=owner_id AND run_id=run;
 snapshot:=coalesce(through_sequence,latest);
 IF snapshot<0 OR snapshot>latest OR after_sequence>snapshot THEN RAISE EXCEPTION 'invalid_event_sequence' USING ERRCODE='22023'; END IF;
 result:=jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,'through_sequence',snapshot,
  'records',records,'has_more',false,'next_sequence',after_sequence);
 FOR row IN SELECT * FROM vn_projection.relay_events WHERE user_id=owner_id AND run_id=run
  AND sequence>after_sequence AND sequence<=snapshot ORDER BY sequence LIMIT max_rows+1 LOOP
  IF jsonb_array_length(records)=max_rows THEN more:=true; EXIT; END IF;
  candidate:=jsonb_set(result,'{records}',records||jsonb_build_array(jsonb_build_object('sequence',row.sequence,
   'revision',row.revision,'command_id',row.command_id,'data',row.data)));
  candidate:=jsonb_set(candidate,'{next_sequence}',to_jsonb(row.sequence));
  IF octet_length(candidate::text)>max_bytes THEN
   IF records='[]'::jsonb THEN RAISE EXCEPTION 'read_record_exceeds_page' USING ERRCODE='22023'; END IF;
   more:=true; EXIT;
  END IF;
  records:=candidate->'records'; result:=candidate;
 END LOOP;
 RETURN jsonb_set(result,'{has_more}',to_jsonb(more));
END $$;

CREATE FUNCTION vn_projection.require_relay_acceptance() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,vn_projection,pg_temp AS $$
BEGIN
 IF (NEW.acknowledged_revision,NEW.acknowledged_index)>(OLD.acknowledged_revision,OLD.acknowledged_index) AND
  NOT EXISTS(SELECT 1 FROM vn_projection.relay_events WHERE run_id=NEW.run_id AND user_id=NEW.user_id AND revision=NEW.acknowledged_revision
   AND (data->>'event_index')::integer=NEW.acknowledged_index) THEN
  RAISE EXCEPTION 'durable_relay_acceptance_required' USING ERRCODE='P0001';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER require_relay_acceptance BEFORE UPDATE ON vn_durability.outbox_progress FOR EACH ROW EXECUTE FUNCTION vn_projection.require_relay_acceptance();

CREATE FUNCTION vn_read.archive_run(run uuid, expected_revision bigint, request_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE owner_id uuid:=vn_identity.owner_id(); state vn_durability.runs%ROWTYPE; existing vn_projection.archives%ROWTYPE; receipt jsonb; positions integer;
BEGIN
 IF owner_id IS NULL OR run IS NULL OR expected_revision IS NULL OR expected_revision<1 OR request_id IS NULL THEN
  RAISE EXCEPTION 'invalid_archive_request' USING ERRCODE='22023'; END IF;
 SELECT * INTO state FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
 SELECT * INTO existing FROM vn_projection.archives WHERE user_id=owner_id AND archives.request_id=archive_run.request_id;
 IF FOUND THEN
  IF existing.run_id<>run OR existing.expected_revision<>expected_revision THEN RAISE EXCEPTION 'archive_request_conflict'; END IF;
  RETURN existing.receipt;
 END IF;
 -- The core marks orderly stops reconciliation-required too. Archive is
 -- presentation only: prove a complete known stopped checkpoint/journal and
 -- retain that warning; never clear reconciliation or infer liquidation.
 IF state.revision<>expected_revision OR state.status<>'stopped' OR state.command_version<>5 OR
  state.interrupted_at IS NOT NULL OR state.engine_state->>'status' IS DISTINCT FROM 'stopped' OR
  (state.engine_state->>'revision')::bigint IS DISTINCT FROM state.revision OR NOT EXISTS(
   SELECT 1 FROM vn_durability.commands c WHERE c.run_id=run AND c.user_id=owner_id AND
    c.revision=state.revision AND c.kind='batch') THEN
  RAISE EXCEPTION 'archive_unavailable' USING ERRCODE='P0001'; END IF;
 SELECT count(*) INTO positions FROM vn_durability.positions WHERE run_id=run AND NOT closed;
 receipt:=jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,'request_id',request_id,'revision',expected_revision,
  'archived',true,'retained_open_positions',positions,'retained_exposure',positions>0,
  'requires_reconciliation',state.requires_reconciliation,'classification','known_terminal_checkpoint');
 IF EXISTS(SELECT 1 FROM vn_projection.archives WHERE run_id=run) THEN
  RAISE EXCEPTION 'archive_request_conflict' USING ERRCODE='P0001'; END IF;
 INSERT INTO vn_projection.archives(user_id,run_id,expected_revision,request_id,receipt)
 VALUES(owner_id,run,expected_revision,request_id,receipt);
 RETURN receipt;
END $$;


-- Exact capabilities; no managed service_role economic authority.
REVOKE ALL ON SCHEMA vn_durability FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON ALL TABLES IN SCHEMA vn_durability FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_durability FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON SCHEMA vn_projection FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON ALL TABLES IN SCHEMA vn_projection FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_projection FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON SCHEMA vn_read FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON ALL TABLES IN SCHEMA vn_read FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_read FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON DOMAIN vn_durability.balance FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
GRANT USAGE ON SCHEMA vn_durability TO vn_economic,vn_relay;
GRANT USAGE ON SCHEMA vn_read TO authenticated,vn_relay;
GRANT EXECUTE ON FUNCTION vn_durability.create_run(uuid,uuid,uuid,uuid,jsonb,text,integer) TO vn_economic;
GRANT EXECUTE ON FUNCTION vn_durability.heartbeat(uuid,uuid,uuid,bigint,integer) TO vn_economic;
GRANT EXECUTE ON FUNCTION vn_durability.commit_command(uuid,uuid,uuid,bigint,bigint,uuid,jsonb) TO vn_economic;
GRANT EXECUTE ON FUNCTION vn_durability.get_command(uuid,uuid,uuid) TO vn_economic;
GRANT EXECUTE ON FUNCTION vn_durability.interrupt_expired(uuid,uuid,bigint,uuid) TO vn_economic;
GRANT EXECUTE ON FUNCTION vn_durability.read_outbox(uuid,uuid,bigint,integer,integer) TO vn_relay;
GRANT EXECUTE ON FUNCTION vn_durability.acknowledge_event(uuid,uuid,uuid,integer) TO vn_relay;
GRANT EXECUTE ON FUNCTION vn_read.page(uuid,text,bigint,bigint,text,integer,integer) TO authenticated;
GRANT EXECUTE ON FUNCTION vn_read.accept_event(uuid,uuid,uuid,integer) TO vn_relay;
GRANT EXECUTE ON FUNCTION vn_read.events(uuid,bigint,bigint,integer,integer) TO authenticated;
GRANT EXECUTE ON FUNCTION vn_read.archive_run(uuid,bigint,uuid) TO authenticated;
-- Verify the installed callable inventory, source bodies and explicit/effective
-- capabilities before COMMIT. A caller GUC is only an accidental-use guard.
DO $$
DECLARE item record; actual oid; api record; allowed boolean;
BEGIN
 IF (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      WHERE n.nspname IN ('vn_identity','vn_durability','vn_projection','vn_read'))<>72
    OR (SELECT count(*) FROM pg_namespace WHERE nspname IN ('vn_identity','vn_durability','vn_projection','vn_read'))<>4 OR
    (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname IN ('vn_durability','vn_projection') AND c.relkind='r')<>18 OR
    EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_durability','vn_projection') AND
      (c.relowner<>'vn_contract_owner'::regrole OR (c.relkind='r' AND NOT c.relrowsecurity))) OR
    EXISTS(SELECT 1 FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_durability','vn_projection')) OR
    EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
      LATERAL aclexplode(c.relacl) a WHERE n.nspname IN ('vn_durability','vn_projection')
      AND (a.grantee<>c.relowner OR a.is_grantable)) OR
    EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_durability','vn_projection') AND a.attacl IS NOT NULL) THEN
  RAISE EXCEPTION 'canonical_table_postcondition_failed'; END IF;
 FOR item IN SELECT * FROM (VALUES
('vn_identity.owner_id()','c628b78ce1d2a3b15ddbaf7b0a5838fa26c925d332103e53f34ba73b9b227604','vn_contract_owner','postgres'),
('vn_durability.exact_keys(jsonb,text[])','d9f3b2ca5568583c5605af160a3b5ca396ad192b80ef01265cc385fa16ed1f8f',NULL,'vn_contract_owner'),
('vn_durability.money(jsonb)','3f7ff844afb4adc7af6c4e3f41a58bb89454ef2e61b1420937f365096e5fd70f',NULL,'vn_contract_owner'),
('vn_durability.decimal_units(jsonb,integer)','0ce52862453a84b6f684e7519fc12b6b27e85a28908f5528d983ee849fa04699',NULL,'vn_contract_owner'),
('vn_durability.decimal_text(numeric,integer)','e7974c191c93db5db5dfea0c0e1d556a75fe4fb97b12d62a999cbaebc7f47670',NULL,'vn_contract_owner'),
('vn_durability.execution_config(jsonb)','80b54a747f7720ade400db09a5a2bafffdec33e67e4907feddda2f2b7974fb6d',NULL,'vn_contract_owner'),
('vn_durability.execution_policy(jsonb)','3eeea7c4a832b72adf347f487a9e3fda40bccdd2d6d883cd46b0b32370ef2f02',NULL,'vn_contract_owner'),
('vn_durability.entry_evidence(jsonb)','85d73cb1e26e692b7728ef91537001fa005651d3c142b477591d583c4e168534',NULL,'vn_contract_owner'),
('vn_durability.exit_evidence(jsonb,jsonb)','e0e6c4c055ac82779b4b4eeb6d795211e0d67ca2b3bdd9ae8702e9a2ca46f15c',NULL,'vn_contract_owner'),
('vn_durability.canonical_id(jsonb)','f841db557e13b418b24ff443d158db0f98541e5aa92c51d92d518cf8d42f2352',NULL,'vn_contract_owner'),
('vn_durability.valid_iteration(jsonb)','02f87309967b95c8df87faa027469e7612d79ceffa1a0b46a9f10f8f81cd01a0',NULL,'vn_contract_owner'),
('vn_durability.record_distribution(uuid,uuid,jsonb)','bbfbc6765ad815f18cd1c64fe0692af180e0a3f1a975189e4a8563ec7be8b745',NULL,'vn_contract_owner'),
('vn_durability.record_lineage(uuid,uuid,uuid,jsonb)','7e90095c05fc8faeddbb602a83fa0ab1e8efb066a89f1b772bed303fa3eed990',NULL,'vn_contract_owner'),
('vn_durability.record_restart_lineage(uuid,uuid,uuid,jsonb)','50a23b77010dbcb01b10de4d1edb8d84057d6632755c01478a304913b6a73e83',NULL,'vn_contract_owner'),
('vn_durability.rehearsal_integer(jsonb,numeric,numeric)','52e9fbbea1e0862199aa733051506954fda518d6d0975ac919ac99b8d04bab86',NULL,'vn_contract_owner'),
('vn_durability.rehearsal_hex(jsonb)','f94f88a3ffe6f7d1608333b90d4cce84e33a040314f7d34926549b658ec771b9',NULL,'vn_contract_owner'),
('vn_durability.rehearsal_json(jsonb,integer)','618390b76556aae45d4f6a4175bcc9cdd39ad9e6c46cc6704f769898b1310599',NULL,'vn_contract_owner'),
('vn_durability.rehearsal_integer_hex(integer)','f67b881a39b82f0a18a4e8cb26ae21b55ed1d26c2a8a30b0488b08c61ba03267',NULL,'vn_contract_owner'),
('vn_durability.optimizer_integer(jsonb,numeric,numeric)','33139f5b727aaf975ebba661cb296f748743dd3ccd52f512f82ba11f59f426bf',NULL,'vn_contract_owner'),
('vn_durability.optimizer_decimal(jsonb)','94d790efbeed8df37ae7eeb424f7f0a1d6d07b63bab612012d2a3b82d2e5bf83',NULL,'vn_contract_owner'),
('vn_durability.optimizer_bytes(jsonb,integer)','b7df16fdc0dd4bcf969c72c5577f9cb55a13b8aed614c3a565e007b6f8e89dc8',NULL,'vn_contract_owner'),
('vn_durability.optimizer_array_shape(jsonb)','ac6f536740f9fcd1a698a011d7cb284a4a231e01af4181aefe39f063a083fd93',NULL,'vn_contract_owner'),
('vn_durability.optimizer_array(jsonb)','93c82847ef5f72408604d0b37ab11497e3a3baa47dab6ba54d0b9de168189877',NULL,'vn_contract_owner'),
('vn_durability.optimizer_history(jsonb,jsonb)','00abd5daa5d7ee7dc0e8ba8c147f04d8dc73015a91ff2a20f5725996948b3eb3',NULL,'vn_contract_owner'),
('vn_durability.optimizer_class_fields(text)','f279f51df2c8eac7247c5f4a496528213a77f971005a7e7a9f2681b2a1cd0b4d',NULL,'vn_contract_owner'),
('vn_durability.optimizer_role(jsonb,jsonb,text,boolean)','36054a5a5c3fbbf4b9095aa6408db27550a249d5cb2bc74b45fe36b536056773',NULL,'vn_contract_owner'),
('vn_durability.optimizer_node(jsonb,jsonb,integer)','e10a9b16f4d82fc01b14a83fa24c569d0c89850560e9fed232536e1fbe7d7157',NULL,'vn_contract_owner'),
('vn_durability.optimizer_evidence(jsonb,text)','6bcd98f371911317b75a6b99a203836e4e8bbf698007bc937969171688204946',NULL,'vn_contract_owner'),
('vn_durability.rehearsal_view_time(jsonb)','0ad92b290b7fba263986d49766eefb9df746bf724b2b7690072351bdb97e1d98',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_config(jsonb)','6ae08ef5ef63ea2b9c4a3ea8198986898a1fdc2463e556d17e8d28361655dcf2',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_optimizer_view(jsonb,jsonb,jsonb,jsonb,integer)','be81cebeda3af4504fc0589f2e77e36be5098ee7b3eba0569d3d7eceadb39049',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_optimizer_views(jsonb)','bad4b3f57ceff48a662b09c48b374f7121c120ea1e992e943e57f18e7a7d733c',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_optimizer_mirror(jsonb)','972f2c381ba17963cfe8c4645e1f6d16ae9c61d1a9889251b29e913b834a4d2f',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_amount(jsonb,integer)','177ecae6dab17599eede21367256cb991950d69cb1a29495d1f3aea6133e14f0',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_equity(uuid,numeric,jsonb)','17de133d73ced5e0333feecf11c173ea4044a2ab275d7e47a57dcd18aa5a7d10',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_member_metrics(vn_durability.runs,jsonb,jsonb,jsonb)','a8244e31f5a3baeffe30428b2ce52729895d054d9b3aeb46ad73123b4fa0b4c8',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_cohort(vn_durability.runs,jsonb,integer)','1a6ad24244f8fd78488d148333524d6e6f7315771f252a6440a86c8b9634fc0d',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_state(vn_durability.runs,jsonb,numeric)','0e31231118ad0cf7e754236200c9d073f2740ca95bcbcd3e10b128e57e04f51d',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_candles(jsonb,jsonb,jsonb,boolean)','51f61658f76d6e2bbab0bcfca2f322b0ca59c6fdc4d696a3157e8dc9c5cd006b',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_cohort_continuation(vn_durability.runs,jsonb,boolean,boolean,boolean,boolean,numeric)','4805a3775a8bf98bee83b951b0db2c2bcd483a5bca394811b80ae74ce310f2a7',NULL,'vn_contract_owner'),
('vn_durability.lifecycle_actions(vn_durability.runs,jsonb,boolean,boolean,numeric,numeric)','a515a79debe84a5d53576fa43866b483ec45f97f78e19302f5536d20e4ad39da',NULL,'vn_contract_owner'),
('vn_durability.validate_lifecycle_before(vn_durability.runs,jsonb)','b1722f24ba94fe65a01cac5b1e083dfaf47c54458a0b2f2b2b4ec50040a0f294',NULL,'vn_contract_owner'),
('vn_durability.validate_lifecycle_after(vn_durability.runs,jsonb,numeric)','ef4742d30c93cf1f04eead80a841ed15d56dce33d7faf561cd84b3f5f4cb3c7d',NULL,'vn_contract_owner'),
('vn_durability.provider_us(jsonb)','e19eba145fc166706658fc40f84b3a59dc2c162d685ccc025c333ef491a6ba29',NULL,'vn_contract_owner'),
('vn_durability.provider_hex_us(jsonb)','2235960be55c6c159d4af4e4e00ce7d731ab396042e785564b9cf4ec0ff55351',NULL,'vn_contract_owner'),
('vn_durability.provider_config(jsonb)','4ca462749d55a5bef50a8976448c3196a3670120e7178f0afb934100a0f03c9f',NULL,'vn_contract_owner'),
('vn_durability.provider_mint(text)','ad0941ec5063c227d792902263dc51a5ed63146ecbb1736f10b278c2cba77347',NULL,'vn_contract_owner'),
('vn_durability.provider_document(jsonb,text)','24e33789555de3ad6855fd09b7463240268f23be10efa93d6a8bb1f61ddc0e68',NULL,'vn_contract_owner'),
('vn_durability.provider_receipt(jsonb,numeric,numeric,boolean)','e6f23abfc1c30f9b0426962573662bad9f1310a381420c213ceb5f293f345bff',NULL,'vn_contract_owner'),
('vn_durability.provider_frame(jsonb)','f872b47417472271e3bb55e3b2565fd9a4bc34d29a32e3fc5f51922c88b3b8bd',NULL,'vn_contract_owner'),
('vn_durability.provider_fresh_frame(jsonb,numeric,numeric,boolean)','932fd091ae3cf28fac9653c195a91413771fd9a5b980289a65bb708951245b53',NULL,'vn_contract_owner'),
('vn_durability.provider_bars(jsonb)','a0fe1c55e55e4b8121114a96f0fe8bc27c0f19e5c61da96a8326348ef8019ae1',NULL,'vn_contract_owner'),
('vn_durability.provider_history(jsonb,jsonb,boolean,numeric,numeric)','ae4f3e4c4b06e7419b4b07c7fb2530bcaba4bcbb8e9240c11b0d3d878a5401a8',NULL,'vn_contract_owner'),
('vn_durability.provider_state(jsonb,jsonb)','9c689699f394185714256b919577c8c98b78cb1d9793a38bb8af50b1199df9a6',NULL,'vn_contract_owner'),
('vn_durability.provider_model_payload(jsonb)','2e8e6ce05a1138b93a54d435afaeb86eb561722da149520f793e8db32980331f',NULL,'vn_contract_owner'),
('vn_durability.provider_model_run(vn_durability.runs)','8a23c995a3c862c688024eeb1381d6d1a72805ebefccb70f5d25d9806df5fd93',NULL,'vn_contract_owner'),
('vn_durability.provider_before(vn_durability.runs,jsonb)','44bc3ad213897b957e4becebfea58e1726206360d0f6dd721d43bdbaf7c668ba',NULL,'vn_contract_owner'),
('vn_durability.provider_server_fresh(jsonb)','d9a9c0d9bade76a5d47709fba4abcf8cca6f136f7b7763f7f030bd754e190ea7',NULL,'vn_contract_owner'),
('vn_durability.record_command(uuid,uuid,uuid,bigint,text,jsonb,jsonb)','4596980944508c01c791167808a38f7b860baed7783bd21340501c35c5c1f823',NULL,'vn_contract_owner'),
('vn_durability.create_run(uuid,uuid,uuid,uuid,jsonb,text,integer)','fe9b5a316b83cb775e134cf7fd95418a0928d7eec38a435c6df8c1efca794c00','vn_economic','vn_contract_owner'),
('vn_durability.heartbeat(uuid,uuid,uuid,bigint,integer)','26f854853e535db9b0748652cf9172e7cd084815e1f2a6635df9fa38be3bc7c2','vn_economic','vn_contract_owner'),
('vn_durability.commit_command(uuid,uuid,uuid,bigint,bigint,uuid,jsonb)','9f5c753b5cdb1556bf2ab34175a259ad3c38f0feb7e9559faacc061408da2298','vn_economic','vn_contract_owner'),
('vn_durability.get_command(uuid,uuid,uuid)','1850642accd346cc2150aa938803df4bcef098b37deb6278cb55fc80b6560ef3','vn_economic','vn_contract_owner'),
('vn_durability.interrupt_expired(uuid,uuid,bigint,uuid)','a05056d3ef2b0329c78d13af0ffde4acc3146a2ce2b6922c3223d72f2d8b3fe0','vn_economic','vn_contract_owner'),
('vn_durability.read_outbox(uuid,uuid,bigint,integer,integer)','2e8803f058e615772059f38e63650d6740458ff2ae0260cc8bbb48620a8c21de','vn_relay','vn_contract_owner'),
('vn_durability.acknowledge_event(uuid,uuid,uuid,integer)','83d09077c21a39695928028f9cbdc8ee43c1400f5a673c320f32c05f31d323ae','vn_relay','vn_contract_owner'),
('vn_projection.project_command()','b7d2cbd953494aa8ea9ae2da498fa1b30e27de8450e2eecde48cea7eb05421ca',NULL,'vn_contract_owner'),
('vn_read.page(uuid,text,bigint,bigint,text,integer,integer)','3383561d18c60c48bfe8637f885c139c7824fd9dcd5987348029dc1d11949bdf','authenticated','vn_contract_owner'),
('vn_read.accept_event(uuid,uuid,uuid,integer)','b9fd18570c84ca0aa810d2000b32ed837464aeaff1e8ccae869061fb7e76bac6','vn_relay','vn_contract_owner'),
('vn_read.events(uuid,bigint,bigint,integer,integer)','7d62d492b9bfc51ff0b28fe95b72c481fe91e5fb0e86e42c551364732ade754f','authenticated','vn_contract_owner'),
('vn_projection.require_relay_acceptance()','295044afe8bd95c5573e5a0baad294d9025eb76da538687030da354e0a93692c',NULL,'vn_contract_owner'),
('vn_read.archive_run(uuid,bigint,uuid)','0b5b8cdd104e9bb355c8c6b66d0e957da66cb21042eb6448fbefefa7790cb04c','authenticated','vn_contract_owner')
 ) e(signature,body_hash,execute_role,owner_role) LOOP
  actual:=to_regprocedure(item.signature);
  IF actual IS NULL OR NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid=actual AND
     proowner=item.owner_role::regrole AND encode(sha256(convert_to(prosrc,'UTF8')),'hex')=item.body_hash AND
     proconfig IN (ARRAY['search_path=pg_catalog, vn_durability, pg_temp'],
                   ARRAY['search_path=pg_catalog, vn_projection, pg_temp'],
                   ARRAY['search_path=pg_catalog, pg_temp'])) OR
     EXISTS(SELECT 1 FROM pg_proc p,LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
       WHERE p.oid=actual AND (a.is_grantable OR
         a.grantee NOT IN (p.proowner,coalesce(to_regrole(item.execute_role),p.proowner)))) THEN
   RAISE EXCEPTION 'canonical_function_postcondition_failed: %',item.signature; END IF;
  FOR api IN SELECT oid,rolname FROM pg_roles WHERE rolname IN
    ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay') LOOP
   allowed:=coalesce(api.rolname=item.execute_role,false);
   IF has_function_privilege(api.oid,actual,'EXECUTE') IS DISTINCT FROM allowed OR
      has_function_privilege(api.oid,actual,'EXECUTE WITH GRANT OPTION') THEN
    RAISE EXCEPTION 'canonical_capability_postcondition_failed: %, %',item.signature,api.rolname; END IF;
  END LOOP;
 END LOOP;
 -- Newly-created roles must stay inert; installing a credential is a later gate.
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('vn_economic','vn_relay') AND
    (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit OR rolreplication OR rolbypassrls)) OR
    EXISTS(SELECT 1 FROM pg_auth_members WHERE member IN ('vn_economic'::regrole,'vn_relay'::regrole)) OR
    EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid IN ('vn_economic'::regrole,'vn_relay'::regrole) AND
      (member<>'postgres'::regrole OR grantor<>10 OR NOT admin_option OR inherit_option OR set_option)) OR
    (SELECT count(*) FROM pg_auth_members WHERE roleid IN ('vn_economic'::regrole,'vn_relay'::regrole))<>2 THEN
  RAISE EXCEPTION 'canonical_role_postcondition_failed'; END IF;
 FOR api IN SELECT oid,rolname FROM pg_roles WHERE rolname IN
    ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay') LOOP
  IF pg_has_role(api.oid,'vn_contract_owner','SET') OR pg_has_role(api.oid,'vn_contract_owner','USAGE') OR
     has_schema_privilege(api.oid,'vn_identity','USAGE') OR
     has_schema_privilege(api.oid,'vn_durability','CREATE') OR
     has_schema_privilege(api.oid,'vn_projection','USAGE') OR
     has_schema_privilege(api.oid,'vn_read','CREATE') OR
     EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE n.nspname IN ('vn_durability','vn_projection') AND c.relkind='r' AND
        (has_table_privilege(api.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR
         has_any_column_privilege(api.oid,c.oid,'SELECT,INSERT,UPDATE,REFERENCES'))) THEN
   RAISE EXCEPTION 'canonical_raw_authority_postcondition_failed: %',api.rolname; END IF;
 END LOOP;
END $$;

RESET ROLE;

-- Fresh native-login binding candidate. No login/password is provisioned here.
RESET ROLE;
CREATE SCHEMA vn_access AUTHORIZATION vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
GRANT USAGE,CREATE ON SCHEMA vn_access TO postgres;
RESET ROLE;
-- Existing non-grantable Auth REFERENCES is sufficient; no managed Auth edit.
CREATE TABLE vn_access.bindings (
 issuance_id uuid PRIMARY KEY,
 principal_oid oid UNIQUE NOT NULL,
 principal_name text UNIQUE NOT NULL CHECK(principal_name ~ '^vn_native_[a-f0-9]{32}$'),
 capability text NOT NULL CHECK(capability IN ('economic','relay')),
 owner_id uuid NOT NULL REFERENCES auth.users(id),
 run_id uuid NOT NULL,
 issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 not_before timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 recovery_until timestamptz NOT NULL,
 revoked_at timestamptz,
 CHECK(isfinite(issued_at) AND isfinite(not_before) AND isfinite(expires_at) AND isfinite(recovery_until)),
 CHECK(issued_at <= not_before AND not_before < expires_at AND expires_at <= recovery_until),
 CHECK(expires_at <= issued_at + interval '2 hours' AND recovery_until <= issued_at + interval '24 hours'),
 CHECK(revoked_at IS NULL OR (isfinite(revoked_at) AND revoked_at >= issued_at))
);
ALTER TABLE vn_access.bindings OWNER TO vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
REVOKE USAGE,CREATE ON SCHEMA vn_access FROM postgres;
ALTER TABLE vn_access.bindings ENABLE ROW LEVEL SECURITY;

CREATE FUNCTION vn_access.immutable_binding() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF TG_OP='DELETE' OR
    (to_jsonb(NEW)-'revoked_at') IS DISTINCT FROM (to_jsonb(OLD)-'revoked_at') OR
    OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL OR NEW.revoked_at > clock_timestamp() THEN
  RAISE EXCEPTION 'binding_immutable' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_binding BEFORE UPDATE OR DELETE ON vn_access.bindings
FOR EACH ROW EXECUTE FUNCTION vn_access.immutable_binding();

-- INVOKER-only private helper, called inside the reviewed SECURITY DEFINER RPCs.
-- session_user survives SET ROLE and SECURITY DEFINER; caller JWT/GUCs do not
-- authenticate native SQL. The direct-connection profile requires real SCRAM.
-- TLS enforcement belongs to verified client configuration and hosted server
-- policy: pg_stat_ssl is redacted under SET ROLE/SECURITY DEFINER. Do not grant
-- broad statistics access just to read it. Poolers need a separate hosted proof.
CREATE FUNCTION vn_access.require_actor(owner_id uuid, run uuid, capability text, operation text)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
DECLARE binding vn_access.bindings%ROWTYPE; principal pg_catalog.pg_roles%ROWTYPE;
        required_role oid; observed timestamptz;
BEGIN
 SELECT * INTO principal FROM pg_catalog.pg_roles WHERE rolname=session_user;
 IF NOT FOUND OR NOT principal.rolcanlogin OR principal.rolsuper OR principal.rolcreatedb OR
    principal.rolcreaterole OR principal.rolinherit OR principal.rolreplication OR principal.rolbypassrls OR
    principal.rolconnlimit NOT BETWEEN 1 AND 2 OR
    system_user IS DISTINCT FROM ('scram-sha-256:' || session_user::text) OR
    inet_client_addr() IS NULL THEN
  RAISE EXCEPTION 'principal_denied' USING ERRCODE='42501';
 END IF;
 required_role:=CASE capability WHEN 'economic' THEN 'vn_economic'::regrole
                               WHEN 'relay' THEN 'vn_relay'::regrole END;
 IF required_role IS NULL OR operation NOT IN
   ('create_run','heartbeat','commit_command','get_command','interrupt_expired',
    'read_outbox','acknowledge_event','accept_event') OR
    (capability='economic') IS DISTINCT FROM
      (operation IN ('create_run','heartbeat','commit_command','get_command','interrupt_expired')) OR
    (SELECT count(*) FROM pg_catalog.pg_auth_members WHERE member=principal.oid)<>1 OR
    NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=principal.oid AND roleid=required_role
      AND NOT admin_option AND NOT inherit_option AND set_option) THEN
  RAISE EXCEPTION 'principal_denied' USING ERRCODE='42501';
 END IF;
 -- Serialize revocation with any admitted transaction. Recheck the wall clock
 -- after acquiring the lock and before each successful RPC return, including
 -- idempotent replay. Expiry after journal/projection effects rolls them back.
 SELECT * INTO binding FROM vn_access.bindings WHERE principal_oid=principal.oid
   AND principal_name=session_user::text FOR SHARE;
 observed:=clock_timestamp();
 IF NOT FOUND OR binding.owner_id IS DISTINCT FROM owner_id OR binding.run_id IS DISTINCT FROM run OR
    binding.capability IS DISTINCT FROM capability OR binding.revoked_at IS NOT NULL OR
    observed < binding.not_before OR principal.rolvaliduntil IS NULL OR
    NOT isfinite(principal.rolvaliduntil) OR principal.rolvaliduntil > binding.recovery_until OR
    principal.rolvaliduntil < binding.expires_at OR observed >= principal.rolvaliduntil OR
    observed >= (CASE WHEN operation='get_command' THEN binding.recovery_until ELSE binding.expires_at END) THEN
  RAISE EXCEPTION 'principal_denied' USING ERRCODE='42501';
 END IF;
END $$;

REVOKE ALL ON SCHEMA vn_access FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON ALL TABLES IN SCHEMA vn_access FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_access FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
RESET ROLE;

SET LOCAL ROLE vn_contract_owner;
CREATE OR REPLACE FUNCTION vn_durability.create_run(
  owner_id uuid, run uuid, worker uuid, command_id uuid, configuration jsonb,
  initial_cash text, lease_seconds integer DEFAULT 30
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE amount numeric; request_body jsonb; result jsonb;
        existing vn_durability.commands%ROWTYPE; inserted uuid;
BEGIN
  PERFORM vn_access.require_actor(owner_id,run,'economic','create_run');
  IF owner_id IS NULL OR run IS NULL OR worker IS NULL OR command_id IS NULL OR
     lease_seconds IS NULL OR lease_seconds NOT BETWEEN 1 AND 120 OR
     configuration IS NULL OR jsonb_typeof(configuration) IS DISTINCT FROM 'object' OR
     octet_length(configuration::text) > 65536 THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE = '22023';
  END IF;
  amount := vn_durability.money(to_jsonb(initial_cash));
  IF amount <= 0 THEN RAISE EXCEPTION 'invalid_amount' USING ERRCODE = '22023'; END IF;
  PERFORM vn_durability.provider_config(configuration);
  IF initial_cash IS DISTINCT FROM configuration->'rehearsal'->>'initial_cash' THEN
    RAISE EXCEPTION 'rehearsal_initial_cash_mismatch' USING ERRCODE='22023';
  END IF;
  request_body := jsonb_build_object('kind','create','owner_id',owner_id,'run_id',run,'command_id',command_id,
                                     'worker',worker,'config',configuration,
                                     'initial_cash',initial_cash,'lease_seconds',lease_seconds);
  INSERT INTO vn_durability.runs(id,user_id,worker_id,fence,revision,lease_until,status,config,command_version,initial_cash,reserve)
  VALUES (run,owner_id,worker,1,1,clock_timestamp()+make_interval(secs=>lease_seconds),
          'starting',configuration,5,amount,amount)
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
    PERFORM vn_access.require_actor(owner_id,run,'economic','create_run');
    RETURN existing.response;
  END IF;
  IF (SELECT lease_until FROM vn_durability.runs WHERE id=run) <= clock_timestamp() THEN
    RAISE EXCEPTION 'lease_lost' USING ERRCODE='P0001';
  END IF;
  result := jsonb_build_object('run_id',run,'revision',1,'fence',1,'status','starting');
  PERFORM vn_durability.record_command(owner_id,run,command_id,1,'create',request_body,result);
  PERFORM vn_access.require_actor(owner_id,run,'economic','create_run');
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION vn_durability.heartbeat(
  owner_id uuid, run uuid, worker uuid, token bigint, lease_seconds integer DEFAULT 30
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE state vn_durability.runs%ROWTYPE; observed timestamptz;
BEGIN
  PERFORM vn_access.require_actor(owner_id,run,'economic','heartbeat');
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
  PERFORM vn_access.require_actor(owner_id,run,'economic','heartbeat');
  RETURN jsonb_build_object('run_id',run,'revision',state.revision,'fence',state.fence);
END $$;

CREATE OR REPLACE FUNCTION vn_durability.commit_command(
  owner_id uuid, run uuid, worker uuid, token bigint, expected_revision bigint,
  command_id uuid, payload jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE state vn_durability.runs%ROWTYPE; existing vn_durability.commands%ROWTYPE;
        account vn_durability.accounts%ROWTYPE; position vn_durability.positions%ROWTYPE;
        request_body jsonb; result jsonb; operation jsonb; operation_kind text;
        entity uuid; account_id uuid; cash numeric; quantity numeric;
        notional numeric; fee numeric; close_proceeds numeric; next_status text;
        execution jsonb; first_trip numeric; risk_blocked boolean:=false;
        observed_equity numeric; risk_threshold numeric; risk_price jsonb;
        model_state vn_durability.runs; model_payload jsonb;
BEGIN
  PERFORM vn_access.require_actor(owner_id,run,'economic','commit_command');
  IF owner_id IS NULL OR run IS NULL OR worker IS NULL OR token IS NULL OR token < 1 OR
     expected_revision IS NULL OR expected_revision < 1 OR command_id IS NULL OR
     payload IS NULL OR octet_length(payload::text) > 262144 THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.exact_keys(payload,ARRAY['version','operations','transition']);
  IF payload->'version' IS DISTINCT FROM '5'::jsonb OR
     jsonb_typeof(payload->'operations') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  IF jsonb_array_length(payload->'operations') NOT BETWEEN 0 AND 1024 THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  request_body := jsonb_build_object('kind','batch','owner_id',owner_id,'run_id',run,'command_id',command_id,
                                     'worker',worker,'fence',token,
                                     'expected_revision',expected_revision,'payload',payload);
  SELECT * INTO state FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
  IF state.command_version<>5 THEN RAISE EXCEPTION 'contract_version_mismatch' USING ERRCODE='22023'; END IF;
  IF state.worker_id <> worker OR state.fence <> token OR state.lease_until <= clock_timestamp() OR
     state.interrupted_at IS NOT NULL THEN
    RAISE EXCEPTION 'lease_lost' USING ERRCODE='P0001';
  END IF;
  SELECT * INTO existing FROM vn_durability.commands WHERE run_id=run AND id=command_id;
  IF FOUND THEN
    IF existing.kind <> 'batch' OR existing.request::text <> request_body::text THEN
      RAISE EXCEPTION 'command_conflict' USING ERRCODE='P0001';
    END IF;
    PERFORM vn_access.require_actor(owner_id,run,'economic','commit_command');
    RETURN existing.response;
  END IF;
  IF state.revision <> expected_revision THEN RAISE EXCEPTION 'revision_conflict' USING ERRCODE='P0001'; END IF;
  IF state.status IN ('stopped','failed') THEN RAISE EXCEPTION 'run_terminal' USING ERRCODE='P0001'; END IF;

  PERFORM vn_durability.provider_before(state,payload);
  PERFORM vn_durability.provider_server_fresh(payload);
  model_state:=vn_durability.provider_model_run(state);
  model_payload:=vn_durability.provider_model_payload(payload);
  PERFORM vn_durability.validate_lifecycle_before(model_state,model_payload);
  risk_blocked:=coalesce(state.engine_state->'engine'->'lifecycle'->'risk'->'active'='true'::jsonb,false);
  risk_price:=payload->'transition'->'after'->'engine'->'last_quote'->'price';
  risk_threshold:=state.initial_cash*1e36*(10000-(state.config->'rehearsal'->'lifecycle_policy'->>'account_loss_bps')::numeric);
  IF payload->'transition'->'evidence'->>'kind'='protective' AND NOT risk_blocked THEN
    observed_equity:=vn_durability.lifecycle_equity(run,state.reserve,risk_price);
    IF observed_equity*10000<=risk_threshold THEN first_trip:=observed_equity; risk_blocked:=true; END IF;
  END IF;

  FOR operation IN SELECT value FROM jsonb_array_elements(payload->'operations') WITH ORDINALITY q(value,ordinal) ORDER BY ordinal LOOP
    operation_kind := operation->>'kind';
    IF risk_blocked AND operation_kind IN ('open','birth','distribution') THEN
      RAISE EXCEPTION 'lifecycle_risk_admission_blocked' USING ERRCODE='22023';
    END IF;
    IF state.status IN ('stopped','failed') THEN RAISE EXCEPTION 'run_terminal' USING ERRCODE='P0001'; END IF;
    IF operation_kind = 'birth' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','cash','lineage']);
      entity := vn_durability.canonical_id(operation->'id');
      cash := vn_durability.money(operation->'cash');
      IF entity IS NULL OR cash <= 0 OR cash > state.reserve THEN
        RAISE EXCEPTION 'invalid_birth' USING ERRCODE='22023';
      END IF;
      IF state.status IN ('paused','risk_halted') THEN
        RAISE EXCEPTION 'invalid_birth' USING ERRCODE='22023';
      END IF;
      INSERT INTO vn_durability.accounts(run_id,user_id,id,cash,initial_cash) VALUES(run,owner_id,entity,cash,cash);
      IF operation->'lineage'->'version'='2'::jsonb THEN
        PERFORM vn_durability.record_restart_lineage(owner_id,run,entity,operation->'lineage');
      ELSE
        PERFORM vn_durability.record_lineage(owner_id,run,entity,operation->'lineage');
      END IF;
      state.reserve := state.reserve-cash;
    ELSIF operation_kind='distribution' THEN
      IF state.status IN ('paused','risk_halted') THEN RAISE EXCEPTION 'invalid_distribution' USING ERRCODE='22023'; END IF;
      PERFORM vn_durability.record_distribution(owner_id,run,operation);
    ELSIF operation_kind = 'open' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','account_id','asset','quantity','notional','fee','execution']);
      execution:=vn_durability.entry_evidence(operation->'execution');
      IF execution->'config' IS DISTINCT FROM state.config->'execution'->'config' OR
         operation->'quantity' IS DISTINCT FROM execution->'quantity' OR
         operation->'notional' IS DISTINCT FROM execution->'notional' OR operation->'fee' IS DISTINCT FROM execution->'fee' THEN
        RAISE EXCEPTION 'entry_evidence_mismatch' USING ERRCODE='22023';
      END IF;
      entity := vn_durability.canonical_id(operation->'id');
      account_id := vn_durability.canonical_id(operation->'account_id');
      quantity := vn_durability.money(operation->'quantity');
      notional := vn_durability.money(operation->'notional'); fee := vn_durability.money(operation->'fee');
      SELECT * INTO account FROM vn_durability.accounts a WHERE a.run_id=run AND a.id=account_id AND a.user_id=owner_id;
      IF NOT FOUND OR account.retired OR entity IS NULL OR quantity <= 0 OR notional <= 0 OR
         notional+fee > account.cash OR state.status <> 'running' OR
         ((execution->>'budget')::numeric>account.cash) OR
         jsonb_typeof(operation->'asset') IS DISTINCT FROM 'string' OR
         length(operation->>'asset') NOT BETWEEN 1 AND 64 THEN
        RAISE EXCEPTION 'invalid_open' USING ERRCODE='22023';
      END IF;
      INSERT INTO vn_durability.positions(run_id,user_id,id,account_id,asset,quantity,notional,entry_fee,entry_execution)
      VALUES(run,owner_id,entity,account_id,operation->>'asset',quantity,notional,fee,execution);
      UPDATE vn_durability.accounts a SET cash=a.cash-notional-fee WHERE a.run_id=run AND a.id=account_id;
    ELSIF operation_kind = 'close' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','proceeds','fee','execution']);
      entity := vn_durability.canonical_id(operation->'id');
      close_proceeds := vn_durability.money(operation->'proceeds'); fee := vn_durability.money(operation->'fee');
      SELECT * INTO position FROM vn_durability.positions p WHERE p.run_id=run AND p.id=entity AND p.user_id=owner_id;
      IF NOT FOUND OR position.closed OR fee > close_proceeds THEN RAISE EXCEPTION 'invalid_close' USING ERRCODE='22023'; END IF;
      execution:=vn_durability.exit_evidence(operation->'execution',position.entry_execution);
      IF operation->'proceeds' IS DISTINCT FROM execution->'notional' OR operation->'fee' IS DISTINCT FROM execution->'fee' THEN
        RAISE EXCEPTION 'exit_evidence_mismatch' USING ERRCODE='22023';
      END IF;
      UPDATE vn_durability.positions p SET closed=true,proceeds=close_proceeds,exit_fee=fee,exit_execution=execution
        WHERE p.run_id=run AND p.id=entity;
      UPDATE vn_durability.accounts a SET cash=a.cash+close_proceeds-fee WHERE a.run_id=run AND a.id=position.account_id;
    ELSIF operation_kind = 'retire' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id']);
      entity := vn_durability.canonical_id(operation->'id');
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
      -- Recovery still requires the complete provider/lifecycle control evidence.
      IF state.status='risk_halted' AND next_status NOT IN ('risk_halted','stopped','failed') AND NOT
         (next_status='running' AND payload->'transition'->'evidence'->>'kind'='control' AND
          payload->'transition'->'evidence'->'control'->>'action'='recover') THEN
        RAISE EXCEPTION 'risk_recovery_unavailable' USING ERRCODE='P0001';
      END IF;
      IF next_status='risk_halted' AND first_trip IS NULL THEN RAISE EXCEPTION 'unjustified_risk_halt' USING ERRCODE='22023'; END IF;
      IF state.status='risk_halted' AND next_status='running' THEN risk_blocked:=false; END IF;
      state.status := next_status;
      IF next_status IN ('stopped','failed') THEN state.requires_reconciliation := true; END IF;
    ELSE
      RAISE EXCEPTION 'invalid_operation' USING ERRCODE='22023';
    END IF;
    IF operation_kind IN ('open','close') AND NOT risk_blocked THEN
      observed_equity:=vn_durability.lifecycle_equity(run,state.reserve,risk_price);
      IF observed_equity*10000<=risk_threshold THEN first_trip:=observed_equity; risk_blocked:=true; END IF;
    END IF;
  END LOOP;

  model_state:=vn_durability.provider_model_run(state);
  PERFORM vn_durability.validate_lifecycle_after(model_state,model_payload,first_trip);
  -- Server freshness after every economic effect is still statement atomic.
  PERFORM vn_durability.provider_server_fresh(payload);
  state.engine_state:=payload->'transition'->'after';

  -- Recheck after work too: a long blocked statement cannot persist authority
  -- it lost while executing. Row locks prevent a newer fence from intervening.
  IF state.lease_until <= clock_timestamp() THEN RAISE EXCEPTION 'lease_lost' USING ERRCODE='P0001'; END IF;
  UPDATE vn_durability.runs SET reserve=state.reserve,status=state.status,
    requires_reconciliation=state.requires_reconciliation,revision=state.revision+1,
    engine_state=state.engine_state WHERE id=run;
  result := jsonb_build_object('run_id',run,'revision',state.revision+1,'fence',state.fence,
                               'status',state.status,'reserve',state.reserve::text);
  PERFORM vn_durability.record_command(owner_id,run,command_id,state.revision+1,'batch',request_body,result);
  PERFORM vn_access.require_actor(owner_id,run,'economic','commit_command');
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION vn_durability.get_command(owner_id uuid, run uuid, command_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE result jsonb;
BEGIN
  PERFORM vn_access.require_actor(owner_id,run,'economic','get_command');
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
  PERFORM vn_access.require_actor(owner_id,run,'economic','get_command');
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION vn_durability.interrupt_expired(
  owner_id uuid, run uuid, expected_revision bigint, command_id uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, vn_durability, pg_temp AS $$
DECLARE state vn_durability.runs%ROWTYPE; existing vn_durability.commands%ROWTYPE;
        request_body jsonb; result jsonb; observed timestamptz;
BEGIN
  PERFORM vn_access.require_actor(owner_id,run,'economic','interrupt_expired');
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
    PERFORM vn_access.require_actor(owner_id,run,'economic','interrupt_expired');
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
  PERFORM vn_access.require_actor(owner_id,run,'economic','interrupt_expired');
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION vn_durability.read_outbox(owner_id uuid, run uuid, through_revision bigint,
  max_events integer DEFAULT 50, max_bytes integer DEFAULT 65536)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE progress vn_durability.outbox_progress%ROWTYPE; item vn_durability.outbox_events%ROWTYPE;
        result jsonb; candidate jsonb; records jsonb:='[]'::jsonb; record jsonb; more boolean:=false;
BEGIN
  PERFORM vn_access.require_actor(owner_id,run,'relay','read_outbox');
  IF owner_id IS NULL OR run IS NULL OR through_revision IS NULL OR through_revision<1 OR
     max_events IS NULL OR max_events NOT BETWEEN 1 AND 100 OR
     max_bytes IS NULL OR max_bytes NOT BETWEEN 512 AND 65536 THEN
    RAISE EXCEPTION 'invalid_outbox_request' USING ERRCODE='22023';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM vn_durability.runs r WHERE r.id=run AND r.user_id=owner_id AND
                r.command_version=5 AND through_revision<=r.revision) THEN
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
  PERFORM vn_access.require_actor(owner_id,run,'relay','read_outbox');
  RETURN jsonb_set(result,'{has_more}',to_jsonb(more));
END $$;

CREATE OR REPLACE FUNCTION vn_durability.acknowledge_event(owner_id uuid, run uuid, command_id uuid, event_index integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,vn_durability,pg_temp AS $$
DECLARE progress vn_durability.outbox_progress%ROWTYPE; target vn_durability.outbox_events%ROWTYPE;
        next_event vn_durability.outbox_events%ROWTYPE;
BEGIN
  PERFORM vn_access.require_actor(owner_id,run,'relay','acknowledge_event');
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
  PERFORM vn_access.require_actor(owner_id,run,'relay','acknowledge_event');
  RETURN jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,'command_id',target.command_id,
    'event_id',run::text||':'||target.command_id::text||':'||target.event_index::text,'event_index',target.event_index,
    'revision',target.revision,'acknowledged',true);
END $$;

CREATE OR REPLACE FUNCTION vn_read.accept_event(owner_id uuid, run uuid, command_id uuid, event_index integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE item vn_durability.outbox_events%ROWTYPE; identity text; receipt jsonb; seq bigint;
BEGIN
  PERFORM vn_access.require_actor(owner_id,run,'relay','accept_event');
 IF owner_id IS NULL OR run IS NULL OR command_id IS NULL OR event_index IS NULL OR event_index NOT BETWEEN 0 AND 1024 THEN
  RAISE EXCEPTION 'invalid_relay_event' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'relay_event_unavailable' USING ERRCODE='P0001'; END IF;
 SELECT * INTO item FROM vn_durability.outbox_events e WHERE e.user_id=owner_id AND e.run_id=run AND e.command_id=accept_event.command_id AND e.event_index=accept_event.event_index;
 IF NOT FOUND THEN RAISE EXCEPTION 'relay_event_unavailable' USING ERRCODE='P0001'; END IF;
 identity:=run::text||':'||command_id::text||':'||event_index::text;
 SELECT sequence INTO seq FROM vn_projection.relay_events WHERE run_id=run AND entity_key=identity;
 IF seq IS NULL THEN
  SELECT coalesce(max(sequence),0)+1 INTO seq FROM vn_projection.relay_events WHERE user_id=owner_id AND run_id=run;
  INSERT INTO vn_projection.relay_events VALUES(seq,owner_id,run,item.revision,command_id,identity,
   jsonb_build_object('event_id',identity,'event_index',event_index,'event',item.event));
 END IF;
 IF NOT EXISTS(SELECT 1 FROM vn_projection.relay_events WHERE run_id=run AND revision=item.revision AND entity_key=identity
   AND user_id=owner_id AND data=jsonb_build_object('event_id',identity,'event_index',event_index,'event',item.event)) THEN
  RAISE EXCEPTION 'relay_event_conflict' USING ERRCODE='P0001'; END IF;
 receipt:=jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,'command_id',command_id,'event_index',event_index,'event_id',identity,'revision',item.revision,'sequence',seq,'accepted',true);
 PERFORM vn_access.require_actor(owner_id,run,'relay','accept_event');
 RETURN receipt;
END $$;
RESET ROLE;
SET LOCAL ROLE vn_contract_owner;
DO $$
DECLARE item record; actual oid; api record;
BEGIN
 IF (SELECT count(*) FROM pg_namespace WHERE nspname='vn_access' AND nspowner='vn_contract_owner'::regrole)<>1 OR
    (SELECT count(*) FROM pg_class WHERE relnamespace='vn_access'::regnamespace AND relkind='r'
      AND relname='bindings' AND relowner='vn_contract_owner'::regrole AND relrowsecurity)<>1 OR
    (SELECT count(*) FROM pg_proc WHERE pronamespace='vn_access'::regnamespace)<>2 OR
    EXISTS(SELECT 1 FROM pg_policy WHERE polrelid='vn_access.bindings'::regclass) OR
    EXISTS(SELECT 1 FROM pg_class c,LATERAL aclexplode(c.relacl) a WHERE c.oid='vn_access.bindings'::regclass
      AND (a.grantee<>c.relowner OR a.is_grantable)) OR
    EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid='vn_access.bindings'::regclass AND attacl IS NOT NULL) OR
    EXISTS(SELECT 1 FROM pg_namespace n,LATERAL aclexplode(n.nspacl) a WHERE n.nspname='vn_access'
      AND (a.grantee<>n.nspowner OR a.is_grantable)) OR
    EXISTS(SELECT 1 FROM pg_proc p,LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
      WHERE p.pronamespace='vn_access'::regnamespace AND
      (p.proowner<>'vn_contract_owner'::regrole OR p.prosecdef OR
       p.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp'] OR
       a.grantee<>p.proowner OR a.is_grantable)) OR
    EXISTS(SELECT 1 FROM vn_access.bindings) THEN
  RAISE EXCEPTION 'native_auth_inventory_failed';
 END IF;
 FOR item IN SELECT * FROM (VALUES
('vn_durability.create_run(uuid,uuid,uuid,uuid,jsonb,text,integer)','b7a4fe85fc1620f73b24716261e2fe2f3e1cc7d7aa2f430297d64ff9b1e98926'),
('vn_durability.heartbeat(uuid,uuid,uuid,bigint,integer)','b219dee473362b7fbcc3ab331823c46dad537254e722ef0afaba627cc875e622'),
('vn_durability.commit_command(uuid,uuid,uuid,bigint,bigint,uuid,jsonb)','9c2a1e7a0c86fea0a4f86b25a595f856d3b0c6e65af0152990ac346e51a5426f'),
('vn_durability.get_command(uuid,uuid,uuid)','605da54c2b1142258048dc0ad170d5a706dd7f9293c0467906dee38415807dd7'),
('vn_durability.interrupt_expired(uuid,uuid,bigint,uuid)','970f44076e4e136cc87dbe39ec5d1493e1c9f9ef4a2221709be8a3e25ad670a2'),
('vn_durability.read_outbox(uuid,uuid,bigint,integer,integer)','374ddc0e4fc587b008d7f28308528d4cb860fd0e4477af3f75fb144d39b53a13'),
('vn_durability.acknowledge_event(uuid,uuid,uuid,integer)','684f34264ddcea3f266c46a9b42ad04b15047306c5ff02b176b930fb7e727b2d'),
('vn_read.accept_event(uuid,uuid,uuid,integer)','93c554920853f373a84cb49728e8db1edfd1551c0789a37753f140598731c94c'),
('vn_access.immutable_binding()','4c177aea6ee3f5555205ded67fcf3ca71e44dd53d4113ab918da9889aab1f401'),
('vn_access.require_actor(uuid,uuid,text,text)','07a4ff07b9e5e8f618d353efd3a8d8266a2b896dfd6aba976ccfba0f548e5644')
 ) e(signature,body_hash) LOOP
  actual:=to_regprocedure(item.signature);
  IF actual IS NULL OR NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid=actual AND
     proowner='vn_contract_owner'::regrole AND encode(sha256(convert_to(prosrc,'UTF8')),'hex')=item.body_hash) THEN
   RAISE EXCEPTION 'native_auth_body_failed: %',item.signature;
  END IF;
 END LOOP;
 FOR api IN SELECT oid,rolname FROM pg_roles WHERE rolname IN
   ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay') LOOP
  IF has_schema_privilege(api.oid,'vn_access','USAGE,CREATE') OR
     has_table_privilege(api.oid,'vn_access.bindings','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR
     has_any_column_privilege(api.oid,'vn_access.bindings','SELECT,INSERT,UPDATE,REFERENCES') OR
     has_function_privilege(api.oid,'vn_access.require_actor(uuid,uuid,text,text)','EXECUTE') OR
     has_function_privilege(api.oid,'vn_access.immutable_binding()','EXECUTE') THEN
   RAISE EXCEPTION 'native_auth_raw_authority_failed: %',api.rolname;
  END IF;
 END LOOP;
END $$;
RESET ROLE;

COMMIT;
