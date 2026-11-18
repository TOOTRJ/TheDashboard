-- One scoped pre-dispatch Stop intent for the verified handoff laboratory.
BEGIN;
SET LOCAL ROLE vn_jupiter_b2_sealed_owner;

CREATE TABLE vn_jupiter_b2_allocation_research_v3.stop_intents (
  scope_wire pg_catalog.text PRIMARY KEY
    REFERENCES vn_jupiter_b2_allocation_research_v3.scope_state(scope_wire)
    CHECK (pg_catalog.octet_length(scope_wire)<=512),
  action_id pg_catalog.text NOT NULL UNIQUE CHECK (action_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
  intent_wire pg_catalog.text NOT NULL CHECK (pg_catalog.octet_length(intent_wire)<=4096),
  registering_xid pg_catalog.xid8 NOT NULL
);

-- FUNCTION _stop_intent_reply
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._stop_intent_reply(stored_wire pg_catalog.text, requested_scope pg_catalog.text, requested_id pg_catalog.text, auth pg_catalog.jsonb)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $intent$
DECLARE intent jsonb; command jsonb;
BEGIN
 IF pg_catalog.jsonb_typeof(auth->'handoff') IS DISTINCT FROM 'object'
  OR stored_wire IS NULL OR pg_catalog.octet_length(stored_wire)>4096
 THEN RAISE EXCEPTION 'b2_stop_intent_profile_refused' USING ERRCODE='42501'; END IF;
 intent:=stored_wire::jsonb;
 command:=(intent->>'original_command_wire')::jsonb;
 IF NOT vn_jupiter_b2_allocation_research_v3._keys(intent,ARRAY[
    'format','installation_id','native_package_sha256','effective_catalog_sha256','handoff_sha256',
    'control_binding_id','original_command_wire','original_command_sha256'])
  OR intent->>'format' IS DISTINCT FROM 'ga-jupiter-b2-stop-intent-research-v3-v1'
  OR vn_jupiter_b2_allocation_research_v3._c14n(intent) IS DISTINCT FROM stored_wire
  OR intent->>'installation_id' IS DISTINCT FROM auth#>>'{package,installation_id}'
  OR intent->>'native_package_sha256' IS DISTINCT FROM auth#>>'{package,native_package_sha256}'
  OR intent->>'effective_catalog_sha256' IS DISTINCT FROM auth->>'effective_catalog_sha256'
  OR intent->>'handoff_sha256' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._sha(
    vn_jupiter_b2_allocation_research_v3._c14n(auth->'handoff'))
  OR (intent->>'original_command_sha256' ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true
  OR intent->>'original_command_sha256' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._sha(intent->>'original_command_wire')
  OR vn_jupiter_b2_allocation_research_v3._c14n(command) IS DISTINCT FROM intent->>'original_command_wire'
  OR command->>'action_kind' IS DISTINCT FROM 'source_stop'
  OR command->>'action_id' IS DISTINCT FROM requested_id
  OR command->>'action_id' IS DISTINCT FROM (auth->>'genesis_wire')::jsonb->>'terminal_stop_action_id'
  OR vn_jupiter_b2_allocation_research_v3._scope(command->'scope') IS DISTINCT FROM requested_scope
  OR NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings b
    CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
      (auth->>'actor_manifest_wire')::jsonb->'bindings') e
    WHERE b.scope_wire=requested_scope AND b.binding_id=intent->>'control_binding_id'
     AND b.capabilities=ARRAY['control','read_original']::text[]
     AND e->>'principal_binding_id'=b.binding_id AND e->>'session_user_oid'=b.session_oid::text
     AND e->>'session_user_name'=b.session_name AND e->'scope'=command->'scope'
     AND e->'capabilities'=pg_catalog.to_jsonb(b.capabilities)
     AND vn_jupiter_b2_allocation_research_v3._c14n(e)=b.binding_wire)
 THEN RAISE EXCEPTION 'b2_stop_intent_pin_refused' USING ERRCODE='42501'; END IF;
 RETURN intent;
END;
$intent$;

-- FUNCTION _existing_stop_intent
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._existing_stop_intent(requested_scope pg_catalog.text, command pg_catalog.jsonb, wire pg_catalog.text, auth pg_catalog.jsonb)
RETURNS pg_catalog.text
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $intent$
DECLARE row_value vn_jupiter_b2_allocation_research_v3.stop_intents%ROWTYPE; intent jsonb;
BEGIN
 IF pg_catalog.current_setting('transaction_isolation')<>'read committed'
  OR pg_catalog.jsonb_typeof(auth->'handoff') IS DISTINCT FROM 'object'
 THEN RAISE EXCEPTION 'b2_stop_intent_profile_refused' USING ERRCODE='42501'; END IF;
 -- This statement must run after the caller acquires its package/binding
 -- and scope locks. VOLATILE gives it the fresh READ COMMITTED snapshot.
 SELECT * INTO row_value FROM vn_jupiter_b2_allocation_research_v3.stop_intents s WHERE s.scope_wire=requested_scope;
 IF NOT FOUND THEN RETURN NULL; END IF;
 intent:=vn_jupiter_b2_allocation_research_v3._stop_intent_reply(row_value.intent_wire,requested_scope,row_value.action_id,auth);
 IF row_value.action_id IS DISTINCT FROM command->>'action_id'
  OR intent->>'original_command_wire' IS DISTINCT FROM wire
  OR intent->>'control_binding_id' IS DISTINCT FROM auth->>'binding_id'
 THEN RAISE EXCEPTION 'b2_stop_intent_conflict' USING ERRCODE='42501'; END IF;
 IF row_value.registering_xid=pg_catalog.pg_current_xact_id_if_assigned()
 THEN RAISE EXCEPTION 'b2_stop_intent_uncommitted' USING ERRCODE='42501'; END IF;
 PERFORM vn_jupiter_b2_allocation_research_v3._check_credential_window(auth->'credential_windows',
  (vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint);
 RETURN row_value.intent_wire;
END;
$intent$;

-- FUNCTION _stage_stop_intent
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._stage_stop_intent(requested_scope pg_catalog.text, command pg_catalog.jsonb, wire pg_catalog.text, auth pg_catalog.jsonb)
RETURNS pg_catalog.text
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $intent$
DECLARE staged_wire text; command_sha text; observed_us bigint;
BEGIN
 -- The shared submit planner has already locked the scope and validated
 -- the full original Stop, prior closure and untouched native budget.
 IF pg_catalog.jsonb_typeof(auth->'handoff') IS DISTINCT FROM 'object'
  OR pg_catalog.jsonb_typeof(auth->'credential_windows') IS DISTINCT FROM 'array'
  OR command#>>'{body,expected_mode}' IS DISTINCT FROM 'open'
  OR (auth->>'effective_catalog_sha256' ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'b2_stop_intent_profile_refused' USING ERRCODE='42501'; END IF;
 command_sha:=vn_jupiter_b2_allocation_research_v3._sha(wire);
 staged_wire:=vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_object(
  'format','ga-jupiter-b2-stop-intent-research-v3-v1','installation_id',auth#>>'{package,installation_id}',
  'native_package_sha256',auth#>>'{package,native_package_sha256}','effective_catalog_sha256',auth->>'effective_catalog_sha256',
  'handoff_sha256',vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(auth->'handoff')),
  'control_binding_id',auth->>'binding_id','original_command_wire',wire,'original_command_sha256',command_sha));
 PERFORM vn_jupiter_b2_allocation_research_v3._stop_intent_reply(staged_wire,requested_scope,command->>'action_id',auth);
 observed_us:=(vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint;
 PERFORM vn_jupiter_b2_allocation_research_v3._check_credential_window(auth->'credential_windows',observed_us);
 INSERT INTO vn_jupiter_b2_allocation_research_v3.stop_intents(scope_wire,action_id,intent_wire,registering_xid)
  VALUES(requested_scope,command->>'action_id',staged_wire,pg_catalog.pg_current_xact_id());
 RETURN vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_object(
  'format','ga-jupiter-b2-stop-intent-provisional-research-v3-v1','scope',command->'scope',
  'action_id',command->>'action_id','original_command_sha256',command_sha,'pending_commit',true));
END;
$intent$;

-- FUNCTION _require_no_stop_intent
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._require_no_stop_intent(requested_scope pg_catalog.text)
RETURNS pg_catalog.void
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $intent$
BEGIN
 IF pg_catalog.current_setting('transaction_isolation')<>'read committed'
 THEN RAISE EXCEPTION 'b2_stop_intent_profile_refused' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM vn_jupiter_b2_allocation_research_v3.stop_intents s WHERE s.scope_wire=requested_scope;
 IF FOUND THEN RAISE EXCEPTION 'b2_stop_intent_pending' USING ERRCODE='42501'; END IF;
END;
$intent$;

-- FUNCTION _require_exact_stop_intent
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._require_exact_stop_intent(requested_scope pg_catalog.text, command pg_catalog.jsonb, wire pg_catalog.text, auth pg_catalog.jsonb)
RETURNS pg_catalog.void
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $intent$
BEGIN
 IF vn_jupiter_b2_allocation_research_v3._existing_stop_intent(requested_scope,command,wire,auth) IS NULL
 THEN RAISE EXCEPTION 'b2_stop_intent_required' USING ERRCODE='42501'; END IF;
END;
$intent$;

-- FUNCTION record_stop_intent
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3.record_stop_intent(wire pg_catalog.text)
RETURNS pg_catalog.text
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $intent$
BEGIN
 RETURN vn_jupiter_b2_allocation_research_v3._submit(wire,true);
END;
$intent$;

-- FUNCTION get_stop_intent
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3.get_stop_intent(wire pg_catalog.text)
RETURNS pg_catalog.text
LANGUAGE plpgsql STABLE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $intent$
DECLARE query jsonb; sw text; auth jsonb; row_value vn_jupiter_b2_allocation_research_v3.stop_intents%ROWTYPE;
        intent jsonb; response text;
BEGIN
 IF wire IS NULL OR pg_catalog.octet_length(wire)>2048 THEN RAISE EXCEPTION 'b2_stop_intent_query_refused'; END IF;
 query:=wire::jsonb;
 IF NOT vn_jupiter_b2_allocation_research_v3._keys(query,ARRAY[
   'format','native_policy_sha256','scope','target_kind','target_id','expected_original_command_sha256','correlation'])
  OR query->>'format' IS DISTINCT FROM 'ga-jupiter-b2-original-query-research-v3-v1'
  OR query->>'native_policy_sha256' IS DISTINCT FROM 'e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0'
  OR query->>'target_kind' IS DISTINCT FROM 'source_stop'
  OR pg_catalog.jsonb_typeof(query->'target_id') IS DISTINCT FROM 'string'
  OR (query->>'target_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true
  OR pg_catalog.jsonb_typeof(query->'expected_original_command_sha256') IS DISTINCT FROM 'string'
  OR (query->>'expected_original_command_sha256' ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true
  OR query->'correlation' IS DISTINCT FROM pg_catalog.jsonb_build_object('kind','original_action_id','id',query->>'target_id')
  OR vn_jupiter_b2_allocation_research_v3._c14n(query) IS DISTINCT FROM wire
 THEN RAISE EXCEPTION 'b2_stop_intent_query_refused'; END IF;
 sw:=vn_jupiter_b2_allocation_research_v3._scope(query->'scope');
 auth:=vn_jupiter_b2_allocation_research_v3._auth(query->'scope','get_original',NULL,NULL,NULL);
 IF pg_catalog.jsonb_typeof(auth->'handoff') IS DISTINCT FROM 'object'
  OR pg_catalog.jsonb_typeof(auth->'credential_windows') IS DISTINCT FROM 'array'
  OR auth->>'binding_id' IS DISTINCT FROM (auth->>'genesis_wire')::jsonb#>>'{initial_acquisition_spec,reader_principal_binding_id}'
  OR query->>'target_id' IS DISTINCT FROM (auth->>'genesis_wire')::jsonb->>'terminal_stop_action_id'
 THEN RAISE EXCEPTION 'b2_stop_intent_reader_refused' USING ERRCODE='42501'; END IF;
 SELECT * INTO row_value FROM vn_jupiter_b2_allocation_research_v3.stop_intents s WHERE s.scope_wire=sw;
 IF FOUND THEN
  IF row_value.registering_xid=pg_catalog.pg_current_xact_id_if_assigned()
  THEN RAISE EXCEPTION 'b2_stop_intent_uncommitted' USING ERRCODE='42501'; END IF;
  intent:=vn_jupiter_b2_allocation_research_v3._stop_intent_reply(row_value.intent_wire,sw,row_value.action_id,auth);
  IF row_value.action_id IS DISTINCT FROM query->>'target_id'
   OR intent->>'original_command_sha256' IS DISTINCT FROM query->>'expected_original_command_sha256'
  THEN RAISE EXCEPTION 'b2_stop_intent_conflict' USING ERRCODE='42501'; END IF;
 END IF;
 response:=vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_object(
  'format','ga-jupiter-b2-stop-intent-observation-research-v3-v1','scope',query->'scope','action_id',query->>'target_id',
  'resolution',CASE WHEN intent IS NULL THEN 'observed_absent_unknown' ELSE 'observed_committed_exact' END,
  'intent_wire',row_value.intent_wire));
 IF pg_catalog.octet_length(response)>12288 THEN RAISE EXCEPTION 'b2_stop_intent_query_bound'; END IF;
 PERFORM vn_jupiter_b2_allocation_research_v3._check_credential_window(auth->'credential_windows',
  (vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint);
 RETURN response;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
 RAISE EXCEPTION 'b2_stop_intent_query_refused';
END;
$intent$;

-- FUNCTION _stop_intent_commit_guard
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._stop_intent_commit_guard()
RETURNS pg_catalog.trigger
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $intent$
DECLARE intent jsonb; command jsonb; auth jsonb; head jsonb; accounting jsonb;
BEGIN
 IF pg_catalog.btrim(pg_catalog.current_query(),E' \t\r\n\f'||pg_catalog.chr(11)) NOT IN('COMMIT','COMMIT;')
 THEN RAISE EXCEPTION 'b2_stop_intent_commit_form_refused'; END IF;
 IF NEW.registering_xid IS DISTINCT FROM pg_catalog.pg_current_xact_id()
  OR pg_catalog.current_setting('synchronous_commit')<>'on' OR pg_catalog.current_setting('fsync')<>'on'
 THEN RAISE EXCEPTION 'b2_stop_intent_origin_refused'; END IF;
 command:=(NEW.intent_wire::jsonb->>'original_command_wire')::jsonb;
 auth:=vn_jupiter_b2_allocation_research_v3._auth(command->'scope','control',NULL,NULL,NULL);
 intent:=vn_jupiter_b2_allocation_research_v3._stop_intent_reply(NEW.intent_wire,NEW.scope_wire,NEW.action_id,auth);
 SELECT s.head_wire::jsonb,s.accounting_wire::jsonb INTO head,accounting
 FROM vn_jupiter_b2_allocation_research_v3.scope_state s WHERE s.scope_wire=NEW.scope_wire FOR UPDATE;
 IF NOT FOUND OR intent->>'control_binding_id' IS DISTINCT FROM auth->>'binding_id'
  OR head->>'source_mode' IS DISTINCT FROM 'open'
  OR accounting->'Stop_reserve_consumed' IS DISTINCT FROM 'false'::jsonb
  OR command->'expected_head' IS DISTINCT FROM pg_catalog.jsonb_build_object(
    'native_sequence',head->'native_sequence','native_head_sha256',head->'native_head_sha256','previous_seal_sha256',head->'previous_seal_sha256')
  OR EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.original_operations o
    WHERE o.action_id=NEW.action_id OR o.writer_xid8=NEW.registering_xid)
 THEN RAISE EXCEPTION 'b2_stop_intent_origin_refused'; END IF;
 PERFORM vn_jupiter_b2_allocation_research_v3._check_credential_window(auth->'credential_windows',
  (vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint);
 RETURN NEW;
END;
$intent$;

CREATE CONSTRAINT TRIGGER committed_stop_intent_guard AFTER INSERT ON vn_jupiter_b2_allocation_research_v3.stop_intents
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION vn_jupiter_b2_allocation_research_v3._stop_intent_commit_guard();

REVOKE ALL ON TABLE vn_jupiter_b2_allocation_research_v3.stop_intents FROM PUBLIC;
REVOKE ALL ON TYPE vn_jupiter_b2_allocation_research_v3.stop_intents FROM PUBLIC;
REVOKE ALL ON FUNCTION
 vn_jupiter_b2_allocation_research_v3._stop_intent_reply(pg_catalog.text,pg_catalog.text,pg_catalog.text,pg_catalog.jsonb),
 vn_jupiter_b2_allocation_research_v3._existing_stop_intent(pg_catalog.text,pg_catalog.jsonb,pg_catalog.text,pg_catalog.jsonb),
 vn_jupiter_b2_allocation_research_v3._stage_stop_intent(pg_catalog.text,pg_catalog.jsonb,pg_catalog.text,pg_catalog.jsonb),
 vn_jupiter_b2_allocation_research_v3._require_no_stop_intent(pg_catalog.text),
 vn_jupiter_b2_allocation_research_v3._require_exact_stop_intent(pg_catalog.text,pg_catalog.jsonb,pg_catalog.text,pg_catalog.jsonb),
 vn_jupiter_b2_allocation_research_v3.record_stop_intent(pg_catalog.text),
 vn_jupiter_b2_allocation_research_v3.get_stop_intent(pg_catalog.text),
 vn_jupiter_b2_allocation_research_v3._stop_intent_commit_guard()
FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vn_jupiter_b2_allocation_research_v3.record_stop_intent(pg_catalog.text) TO vn_jupiter_b2_0_control;
GRANT EXECUTE ON FUNCTION vn_jupiter_b2_allocation_research_v3.get_stop_intent(pg_catalog.text) TO vn_jupiter_b2_0_reader;
COMMIT;
