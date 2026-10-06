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
