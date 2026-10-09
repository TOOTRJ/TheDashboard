-- OFFLINE EXPERIMENT ONLY. Not a migration, v6 package or deployable endpoint.
-- The fixture keeps the ordinary v5 journal as well as this research journal.
-- Measured compact payloads are counterfactual savings, not actual DB savings.
-- No caller grants; the test fixture grants its synthetic economic role only.
DO $$ BEGIN
 IF current_setting('dashboard.checkpoint_reference_fixture',true) IS DISTINCT FROM 'offline-v1' THEN
  RAISE EXCEPTION 'offline_checkpoint_fixture_required';
 END IF;
END $$;

CREATE SCHEMA vn_checkpoint_research;
REVOKE ALL ON SCHEMA vn_checkpoint_research FROM PUBLIC;
CREATE TABLE vn_checkpoint_research.requests (
 run_id uuid NOT NULL,
 command_id uuid NOT NULL,
 owner_id uuid NOT NULL,
 request jsonb NOT NULL,
 response jsonb NOT NULL,
 PRIMARY KEY(run_id,command_id)
);
REVOKE ALL ON vn_checkpoint_research.requests FROM PUBLIC;

CREATE FUNCTION vn_checkpoint_research.descriptor(state vn_durability.runs)
RETURNS jsonb LANGUAGE sql SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object('version',1,'owner_id',(state).user_id,'run_id',(state).id,
   'revision',(state).revision,'hash_policy','postgres17-jsonb-sha256-v1',
   'sha256',encode(sha256(convert_to(coalesce((state).engine_state,'null'::jsonb)::text,'UTF8')),'hex'))
$$;

CREATE FUNCTION vn_checkpoint_research.reference(owner_id uuid, run uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,vn_checkpoint_research,pg_temp AS $$
DECLARE state vn_durability.runs%ROWTYPE;
BEGIN
 SELECT * INTO state FROM vn_durability.runs WHERE id=run AND user_id=owner_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable'; END IF;
 RETURN vn_checkpoint_research.descriptor(state);
END $$;

CREATE FUNCTION vn_checkpoint_research.commit_reference(owner_id uuid, run uuid, worker uuid,
 token bigint, expected_revision bigint, command_id uuid, payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,vn_checkpoint_research,pg_temp AS $$
DECLARE state vn_durability.runs%ROWTYPE; prior vn_checkpoint_research.requests%ROWTYPE;
 request_body jsonb; expanded jsonb; result jsonb;
BEGIN
 IF owner_id IS NULL OR run IS NULL OR worker IS NULL OR token IS NULL OR token<1 OR
    expected_revision IS NULL OR expected_revision<1 OR command_id IS NULL OR
    payload IS NULL OR octet_length(payload::text)>262144 THEN
  RAISE EXCEPTION 'reference_wire_capacity_or_identity';
 END IF;
 PERFORM vn_durability.exact_keys(payload,ARRAY['transport','model_version','before_reference','operations','transition']);
 PERFORM vn_durability.exact_keys(payload->'transition',ARRAY['version','after','evidence','events']);
 IF payload->>'transport' IS DISTINCT FROM 'checkpoint-reference-research-v1' OR
    payload->'model_version' IS DISTINCT FROM '5'::jsonb THEN
  RAISE EXCEPTION 'reference_transport_version';
 END IF;
 request_body:=jsonb_build_object('owner_id',owner_id,'run_id',run,'worker',worker,
   'fence',token,'expected_revision',expected_revision,'command_id',command_id,'payload',payload);
 SELECT * INTO state FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable'; END IF;
 IF state.command_version<>5 OR state.worker_id<>worker OR state.fence<>token OR
    state.lease_until<=clock_timestamp() OR state.interrupted_at IS NOT NULL THEN
  RAISE EXCEPTION 'reference_lease_or_contract_lost';
 END IF;
 -- Original wire equality precedes expansion: replay must not resolve against
 -- a newer checkpoint. Missing rows never authorize a new command identity.
 SELECT * INTO prior FROM vn_checkpoint_research.requests r WHERE r.run_id=run AND r.command_id=commit_reference.command_id;
 IF FOUND THEN
  IF prior.owner_id<>owner_id OR prior.request::text<>request_body::text THEN
   RAISE EXCEPTION 'reference_command_conflict';
  END IF;
  RETURN prior.response;
 END IF;
 IF state.revision<>expected_revision OR state.status IN ('stopped','failed') THEN
  RAISE EXCEPTION 'reference_revision_or_terminal';
 END IF;
 IF (payload->'before_reference')::text IS DISTINCT FROM vn_checkpoint_research.descriptor(state)::text THEN
  RAISE EXCEPTION 'reference_checkpoint_mismatch';
 END IF;
 expanded:=jsonb_build_object('version',5,'operations',payload->'operations','transition',
   (payload->'transition')||jsonb_build_object('before',coalesce(state.engine_state,'null'::jsonb)));
 IF octet_length(expanded::text)>262144 THEN RAISE EXCEPTION 'reference_expanded_capacity'; END IF;
 -- The unchanged v5 boundary independently checks source/model/economics,
 -- projection/outbox atomicity, freshness after effects and final lease time.
 result:=vn_durability.commit_command(owner_id,run,worker,token,expected_revision,command_id,expanded);
 INSERT INTO vn_checkpoint_research.requests VALUES(run,command_id,owner_id,request_body,result);
 -- Research journaling is additional work after v5's final checks. It cannot
 -- widen the transaction's freshness or lease window.
 PERFORM vn_durability.provider_server_fresh(expanded);
 IF state.lease_until<=clock_timestamp() THEN RAISE EXCEPTION 'reference_lease_lost_at_end'; END IF;
 RETURN result;
END $$;

CREATE FUNCTION vn_checkpoint_research.get_reference_command(owner_id uuid, run uuid, command_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,vn_checkpoint_research,pg_temp AS $$
DECLARE result jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM vn_durability.runs WHERE id=run AND user_id=owner_id) THEN
  RAISE EXCEPTION 'run_unavailable';
 END IF;
 SELECT jsonb_build_object('request',r.request,'response',r.response) INTO result
  FROM vn_checkpoint_research.requests r WHERE r.run_id=run AND r.owner_id=get_reference_command.owner_id
   AND r.command_id=get_reference_command.command_id;
 RETURN result;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_checkpoint_research FROM PUBLIC;
