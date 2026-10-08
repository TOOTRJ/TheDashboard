-- Deliberate administrator reconciliation, never a worker startup or migration.
-- The caller must verify the exact Dashboard target and bind the original
-- private input once. Unbound placeholders fail closed. Rehearse with ROLLBACK,
-- independently verify no change, then submit the same original command once.
-- No credential extension, restoration, liquidation or accounting adjustment.
BEGIN;
SET LOCAL lock_timeout='500ms';
SET LOCAL statement_timeout='8s';
DO $operation$
DECLARE input jsonb := '__INPUT_JSON__'::jsonb;
        state record;
        wanted_owner uuid := (input->>'owner')::uuid;
        wanted_run uuid := (input->>'run')::uuid;
        wanted_command uuid := (input->>'command')::uuid;
        before jsonb; request_body jsonb; result jsonb; observed timestamptz;
BEGIN
  IF session_user<>'postgres' OR current_user<>'postgres' OR
     jsonb_typeof(input)<>'object' OR
     (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(input) k) IS DISTINCT FROM
       ARRAY['accounts_sha256','checkpoint_sha256','command','fence','owner',
             'positions_sha256','reserve','revision','run'] OR
     wanted_owner IS NULL OR wanted_run IS NULL OR wanted_command IS NULL OR
     jsonb_typeof(input->'revision') IS DISTINCT FROM 'number' OR
     jsonb_typeof(input->'fence') IS DISTINCT FROM 'number' OR
     (input->>'revision')::bigint NOT BETWEEN 2 AND 4000 OR
     (input->>'fence')::bigint<1 OR
     (input->>'accounts_sha256')!~'^[a-f0-9]{64}$' OR
     (input->>'checkpoint_sha256')!~'^[a-f0-9]{64}$' OR
     (input->>'positions_sha256')!~'^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'maintenance_input_denied' USING ERRCODE='42501';
  END IF;
  EXECUTE 'SET LOCAL ROLE vn_contract_owner';
  LOCK TABLE vn_access.bindings,vn_durability.runs IN SHARE ROW EXCLUSIVE MODE;
  IF NOT EXISTS(SELECT 1 FROM vn_release.state s WHERE s.singleton AND s.state='open' AND s.epoch=1
      AND release_sha256='6b9fceb02278ef9ca978743c43dd2d0dd2cacb49b310689c016fe58d65861fb1'
      AND install_catalog=vn_release.catalog()) OR
     EXISTS(SELECT 1 FROM vn_access.bindings b LEFT JOIN pg_roles p ON p.oid=b.principal_oid
       WHERE b.revoked_at IS NULL OR p.oid IS NULL OR p.rolcanlogin) OR
     EXISTS(SELECT 1 FROM pg_auth_members a JOIN pg_roles p ON p.oid=a.member
       WHERE a.roleid IN ('vn_economic'::regrole,'vn_relay'::regrole)
         AND p.rolcanlogin AND p.oid<>'postgres'::regrole) OR
     (SELECT count(*) FROM vn_access.bindings b JOIN pg_roles p ON p.oid=b.principal_oid
       WHERE b.owner_id=wanted_owner AND b.run_id=wanted_run AND b.revoked_at IS NOT NULL
         AND NOT p.rolcanlogin AND p.rolname=b.principal_name)<>2 THEN
    RAISE EXCEPTION 'revoked_quiescent_scope_required' USING ERRCODE='55000';
  END IF;
  SELECT * INTO state FROM vn_durability.runs r WHERE r.id=wanted_run AND r.user_id=wanted_owner FOR UPDATE;
  IF NOT FOUND OR state.command_version<>5 OR state.status<>'running' OR
     state.interrupted_at IS NOT NULL OR state.requires_reconciliation OR
     state.revision<>(input->>'revision')::bigint OR state.fence<>(input->>'fence')::bigint OR
     state.lease_until>clock_timestamp() OR
     EXISTS(SELECT 1 FROM vn_durability.positions p WHERE p.run_id=wanted_run AND NOT p.closed) OR
     (SELECT count(*) FROM vn_durability.accounts a WHERE a.run_id=wanted_run)<>8 OR
     EXISTS(SELECT 1 FROM vn_durability.commands c WHERE c.run_id=wanted_run AND c.id=wanted_command) THEN
    RAISE EXCEPTION 'original_expired_cash_only_run_required' USING ERRCODE='55000';
  END IF;
  before:=jsonb_build_object('reserve',state.reserve::text,
    'checkpoint_sha256',encode(sha256(convert_to(state.engine_state::text,'UTF8')),'hex'),
    'accounts_sha256',encode(sha256(convert_to((SELECT jsonb_agg(to_jsonb(a) ORDER BY id)::text
      FROM vn_durability.accounts a WHERE a.run_id=wanted_run),'UTF8')),'hex'),
    'positions_sha256',encode(sha256(convert_to(coalesce((SELECT jsonb_agg(to_jsonb(p) ORDER BY id)::text
      FROM vn_durability.positions p WHERE p.run_id=wanted_run),'[]'),'UTF8')),'hex'));
  IF before IS DISTINCT FROM input-ARRAY['owner','run','command','revision','fence']::text[] THEN
    RAISE EXCEPTION 'original_checkpoint_changed' USING ERRCODE='55000';
  END IF;
  observed:=clock_timestamp();
  request_body:=jsonb_build_object('kind','interrupt','owner_id',wanted_owner,'run_id',wanted_run,
    'command_id',wanted_command,'expected_revision',state.revision);
  UPDATE vn_durability.runs SET status='failed',requires_reconciliation=true,
    interrupted_at=observed,fence=state.fence+1,revision=state.revision+1 WHERE id=wanted_run;
  result:=jsonb_build_object('run_id',wanted_run,'revision',state.revision+1,'fence',state.fence+1,
    'status','failed','code','worker_interrupted','requires_reconciliation',true);
  -- The canonical journal helper updates the versioned owner projection
  -- atomically. Interrupts do not create candidate outbox events. Existing
  -- candidate events and relay progress remain unchanged; no ACK is invented.
  PERFORM vn_durability.record_command(wanted_owner,wanted_run,wanted_command,state.revision+1,
    'interrupt',request_body,result);
END $operation$;
RESET ROLE;
COMMIT;
