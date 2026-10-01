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
CREATE POLICY owner_read ON vn_durability.runs FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.accounts FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.positions FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.account_parents FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY owner_read ON vn_durability.commands FOR SELECT TO authenticated USING (user_id = auth.uid());

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
  request_body := jsonb_build_object('kind','create','owner_id',owner_id,'run_id',run,'command_id',command_id,
                                     'worker',worker,'config',configuration,
                                     'initial_cash',initial_cash,'lease_seconds',lease_seconds);
  INSERT INTO vn_durability.runs(id,user_id,worker_id,fence,revision,lease_until,status,config,initial_cash,reserve)
  VALUES (run,owner_id,worker,1,1,clock_timestamp()+make_interval(secs=>lease_seconds),
          'starting',configuration,amount,amount)
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
BEGIN
  IF owner_id IS NULL OR run IS NULL OR worker IS NULL OR token IS NULL OR token < 1 OR
     expected_revision IS NULL OR expected_revision < 1 OR command_id IS NULL OR
     payload IS NULL OR octet_length(payload::text) > 262144 THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  PERFORM vn_durability.exact_keys(payload,ARRAY['version','operations']);
  IF payload->'version' IS DISTINCT FROM '1'::jsonb OR
     jsonb_typeof(payload->'operations') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  IF jsonb_array_length(payload->'operations') NOT BETWEEN 1 AND 256 THEN
    RAISE EXCEPTION 'invalid_payload' USING ERRCODE='22023';
  END IF;
  request_body := jsonb_build_object('kind','batch','owner_id',owner_id,'run_id',run,'command_id',command_id,
                                     'worker',worker,'fence',token,
                                     'expected_revision',expected_revision,'payload',payload);
  SELECT * INTO state FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
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
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','cash','parent_ids']);
      entity := (operation->>'id')::uuid;
      cash := vn_durability.money(operation->'cash');
      IF entity IS NULL OR cash <= 0 OR cash > state.reserve OR
         jsonb_typeof(operation->'parent_ids') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'invalid_birth' USING ERRCODE='22023';
      END IF;
      IF jsonb_array_length(operation->'parent_ids') > 2 OR state.status IN ('paused','risk_halted') THEN
        RAISE EXCEPTION 'invalid_birth' USING ERRCODE='22023';
      END IF;
      INSERT INTO vn_durability.accounts(run_id,user_id,id,cash,initial_cash) VALUES(run,owner_id,entity,cash,cash);
      FOR parent IN SELECT value::uuid FROM jsonb_array_elements_text(operation->'parent_ids') LOOP
        INSERT INTO vn_durability.account_parents VALUES (run,owner_id,entity,parent);
      END LOOP;
      state.reserve := state.reserve-cash;
    ELSIF operation_kind = 'open' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','account_id','asset','quantity','notional','fee']);
      entity := (operation->>'id')::uuid; account_id := (operation->>'account_id')::uuid;
      quantity := vn_durability.money(operation->'quantity');
      notional := vn_durability.money(operation->'notional'); fee := vn_durability.money(operation->'fee');
      SELECT * INTO account FROM vn_durability.accounts a WHERE a.run_id=run AND a.id=account_id AND a.user_id=owner_id;
      IF NOT FOUND OR account.retired OR entity IS NULL OR quantity <= 0 OR notional <= 0 OR
         notional+fee > account.cash OR state.status <> 'running' OR
         jsonb_typeof(operation->'asset') IS DISTINCT FROM 'string' OR
         length(operation->>'asset') NOT BETWEEN 1 AND 64 THEN
        RAISE EXCEPTION 'invalid_open' USING ERRCODE='22023';
      END IF;
      INSERT INTO vn_durability.positions(run_id,user_id,id,account_id,asset,quantity,notional,entry_fee)
      VALUES(run,owner_id,entity,account_id,operation->>'asset',quantity,notional,fee);
      UPDATE vn_durability.accounts a SET cash=a.cash-notional-fee WHERE a.run_id=run AND a.id=account_id;
    ELSIF operation_kind = 'close' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id','proceeds','fee']);
      entity := (operation->>'id')::uuid;
      close_proceeds := vn_durability.money(operation->'proceeds'); fee := vn_durability.money(operation->'fee');
      SELECT * INTO position FROM vn_durability.positions p WHERE p.run_id=run AND p.id=entity AND p.user_id=owner_id;
      IF NOT FOUND OR position.closed OR fee > close_proceeds THEN RAISE EXCEPTION 'invalid_close' USING ERRCODE='22023'; END IF;
      UPDATE vn_durability.positions p SET closed=true,proceeds=close_proceeds,exit_fee=fee
        WHERE p.run_id=run AND p.id=entity;
      UPDATE vn_durability.accounts a SET cash=a.cash+close_proceeds-fee WHERE a.run_id=run AND a.id=position.account_id;
    ELSIF operation_kind = 'retire' THEN
      PERFORM vn_durability.exact_keys(operation,ARRAY['kind','id']);
      entity := (operation->>'id')::uuid;
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
