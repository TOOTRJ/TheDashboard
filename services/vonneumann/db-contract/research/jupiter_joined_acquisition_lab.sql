-- Held add-on for one owned, network-disabled native acquisition fixture.
BEGIN;
SET LOCAL ROLE vn_jupiter_b2_sealed_owner;
SET LOCAL search_path=pg_catalog,pg_temp;

-- FUNCTION _packet_capture
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._packet_capture(wire pg_catalog.text, reservation_wire pg_catalog.text, capture_id pg_catalog.text)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path='pg_catalog','pg_temp' SET TimeZone='UTC' SET client_encoding='UTF8' SET standard_conforming_strings='on'
AS $packet$
DECLARE c jsonb; r jsonb:=reservation_wire::jsonb; capsule jsonb; request jsonb; body jsonb;
 item text; record_key text; family text; max_bytes int; raw bytea; index_no int:=0; clock_key text;
BEGIN
 IF wire IS NULL OR pg_catalog.octet_length(wire)>524288 THEN RAISE EXCEPTION 'b3_capture_shape'; END IF;
 c:=wire::jsonb;
 IF NOT vn_jupiter_b2_allocation_research_v3._keys(c,ARRAY['authority','capsule_wires','capture_id','collection_completed',
    'diagnostics','eligibility','failure_code','format','observation_id','policy_sha256','reservation_sha256','scope'])
  OR vn_jupiter_b2_allocation_research_v3._c14n(c) IS DISTINCT FROM wire
  OR c->'scope' IS DISTINCT FROM r->'scope' OR c->'authority' IS DISTINCT FROM r->'authority'
  OR c->>'format' IS DISTINCT FROM 'ga-jupiter-source-capture-retention-research-v3'
  OR c->'policy_sha256' IS DISTINCT FROM r->'policy_sha256'
  OR c->>'reservation_sha256' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._sha(reservation_wire)
  OR c->>'capture_id' IS DISTINCT FROM capture_id OR c->'capture_id' IS DISTINCT FROM r->'capture_id'
  OR c->'observation_id' IS DISTINCT FROM r->'observation_id'
  OR c->'collection_completed' IS DISTINCT FROM 'true'::jsonb OR c->'eligibility' IS DISTINCT FROM 'false'::jsonb
  OR c->'failure_code' IS DISTINCT FROM 'null'::jsonb OR c->'diagnostics' IS DISTINCT FROM '[]'::jsonb
  OR pg_catalog.jsonb_typeof(c->'capsule_wires') IS DISTINCT FROM 'array'
  OR pg_catalog.jsonb_array_length(c->'capsule_wires')<>3
 THEN RAISE EXCEPTION 'b3_capture_shape'; END IF;
 FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements_text(c->'capsule_wires') LOOP
  index_no:=index_no+1; capsule:=item::jsonb;
  record_key:=(ARRAY['price_record_id','genesis_record_id','block_time_record_id'])[index_no];
  family:=CASE WHEN index_no=1 THEN 'jupiter-price-v3' ELSE 'solana-rpc' END;
  max_bytes:=CASE WHEN index_no=1 THEN 131072 ELSE 65536 END;
  IF NOT vn_jupiter_b2_allocation_research_v3._keys(capsule,ARRAY['acquisition_epoch','canonical_public_request_wire',
     'endpoint_binding_id','format','http_status','issuer_binding_id','market_epoch','method','owner_id',
     'parser_policy_sha256','provider_family','raw_response_ref','received_monotonic_us','received_wall_us','record_id',
     'request_sha256','request_started_monotonic_us','request_started_wall_us','response_base64','response_bytes',
     'response_sha256','run_id','safe_response_metadata'])
   OR vn_jupiter_b2_allocation_research_v3._c14n(capsule) IS DISTINCT FROM item
   OR capsule->>'format' IS DISTINCT FROM 'ga-provider-acquisition-capsule-research-v3'
   OR capsule->'record_id' IS DISTINCT FROM r->record_key OR capsule->'raw_response_ref' IS DISTINCT FROM r->record_key
   OR capsule->>'provider_family' IS DISTINCT FROM family OR capsule->'http_status' IS DISTINCT FROM '"200"'::jsonb
   OR capsule->'endpoint_binding_id' IS DISTINCT FROM
      (r#>(CASE WHEN index_no=1 THEN '{issuer,endpoint_bindings,0,endpoint_binding_id}'::text[]
       ELSE '{issuer,endpoint_bindings,1,endpoint_binding_id}'::text[] END))
   OR capsule->'owner_id' IS DISTINCT FROM r#>'{scope,owner_id}'
   OR capsule->'run_id' IS DISTINCT FROM r#>'{scope,run_id}'
   OR capsule->'market_epoch' IS DISTINCT FROM r#>'{scope,market_epoch}'
   OR capsule->'acquisition_epoch' IS DISTINCT FROM r#>'{issuer,acquisition_epoch}'
   OR capsule->'issuer_binding_id' IS DISTINCT FROM r#>'{issuer,issuer_binding_id}'
   OR capsule->'parser_policy_sha256' IS DISTINCT FROM r#>'{issuer,parser_policy_sha256}'
   OR pg_catalog.jsonb_typeof(capsule->'canonical_public_request_wire') IS DISTINCT FROM 'string'
   OR pg_catalog.octet_length(capsule->>'canonical_public_request_wire')>4096
   OR vn_jupiter_b2_allocation_research_v3._sha(capsule->>'canonical_public_request_wire') IS DISTINCT FROM capsule->>'request_sha256'
   OR pg_catalog.jsonb_typeof(capsule->'safe_response_metadata') IS DISTINCT FROM 'object'
   OR (capsule->'safe_response_metadata')-ARRAY['content_type','x_ratelimit_current','x_ratelimit_remaining','x_ratelimit_reset'] IS DISTINCT FROM '{}'::jsonb
   OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_each(capsule->'safe_response_metadata') e
      WHERE pg_catalog.jsonb_typeof(e.value) IS DISTINCT FROM 'string' OR CASE e.key
       WHEN 'content_type' THEN e.value IS DISTINCT FROM '"application/json"'::jsonb
       WHEN 'x_ratelimit_current' THEN CASE WHEN (e.value#>>'{}') ~ '^(0|[1-9][0-9]{0,18})$'
        THEN (e.value#>>'{}')::numeric>9223372036854775807 ELSE true END
       WHEN 'x_ratelimit_remaining' THEN CASE WHEN (e.value#>>'{}') ~ '^(0|-?[1-9][0-9]{0,18})$'
        THEN (e.value#>>'{}')::numeric NOT BETWEEN -9223372036854775808 AND 9223372036854775807 ELSE true END
       WHEN 'x_ratelimit_reset' THEN CASE WHEN (e.value#>>'{}') ~ '^(0|[1-9][0-9]{0,10})$'
        THEN (e.value#>>'{}')::numeric>10000000000 ELSE true END
       ELSE true END)
   OR pg_catalog.jsonb_typeof(capsule->'response_base64') IS DISTINCT FROM 'string'
   OR pg_catalog.length(capsule->>'response_base64')>4*((max_bytes+2)/3)
  THEN RAISE EXCEPTION 'b3_capsule_conflict'; END IF;
  request:=(capsule->>'canonical_public_request_wire')::jsonb;
  IF NOT vn_jupiter_b2_allocation_research_v3._keys(request,ARRAY['format','method','endpoint','chain','parameters','body_wire'])
   OR vn_jupiter_b2_allocation_research_v3._c14n(request) IS DISTINCT FROM capsule->>'canonical_public_request_wire'
   OR request->>'format' IS DISTINCT FROM 'ga-provider-public-request-research-v3'
   OR request->>'chain' IS DISTINCT FROM 'solana' OR request->'method' IS DISTINCT FROM capsule->'method'
  THEN RAISE EXCEPTION 'b3_capsule_conflict'; END IF;
  IF index_no=1 THEN
   IF request->>'method' IS DISTINCT FROM 'GET' OR request->>'endpoint' IS DISTINCT FROM 'https://api.jup.ag/price/v3'
    OR request->'body_wire' IS DISTINCT FROM 'null'::jsonb
    OR request->'parameters' IS DISTINCT FROM '{"ids":"So11111111111111111111111111111111111111112"}'::jsonb
   THEN RAISE EXCEPTION 'b3_capsule_conflict'; END IF;
  ELSE
   IF request->>'method' IS DISTINCT FROM 'POST' OR request->>'endpoint' IS DISTINCT FROM 'operator-bound-solana-rpc'
    OR request->'parameters' IS DISTINCT FROM '{}'::jsonb OR pg_catalog.jsonb_typeof(request->'body_wire') IS DISTINCT FROM 'string'
   THEN RAISE EXCEPTION 'b3_capsule_conflict'; END IF;
   body:=(request->>'body_wire')::jsonb;
   IF NOT vn_jupiter_b2_allocation_research_v3._keys(body,ARRAY['id','jsonrpc','method','params'])
    OR vn_jupiter_b2_allocation_research_v3._c14n(body) IS DISTINCT FROM request->>'body_wire'
    OR body->'jsonrpc' IS DISTINCT FROM '"2.0"'::jsonb
    OR pg_catalog.jsonb_typeof(body->'id') IS DISTINCT FROM 'number'
    OR body->>'id' IS DISTINCT FROM (index_no-1)::text
    OR body->>'method' IS DISTINCT FROM (CASE WHEN index_no=2 THEN 'getGenesisHash' ELSE 'getBlockTime' END)
    OR (CASE WHEN index_no=2 THEN body->'params' IS DISTINCT FROM '[]'::jsonb
       ELSE pg_catalog.jsonb_typeof(body->'params') IS DISTINCT FROM 'array'
         OR pg_catalog.jsonb_array_length(body->'params')<>1
         OR pg_catalog.jsonb_typeof(body#>'{params,0}') IS DISTINCT FROM 'number'
         OR (body#>>'{params,0}' ~ '^(0|[1-9][0-9]{0,19})$') IS DISTINCT FROM true
         OR (body#>>'{params,0}')::numeric>18446744073709551615 END)
   THEN RAISE EXCEPTION 'b3_capsule_conflict'; END IF;
  END IF;
  FOREACH clock_key IN ARRAY ARRAY['received_wall_us','received_monotonic_us','request_started_wall_us','request_started_monotonic_us'] LOOP
   IF pg_catalog.jsonb_typeof(capsule->clock_key) IS DISTINCT FROM 'string'
    OR (capsule->>clock_key ~ '^(0|[1-9][0-9]{0,18})$') IS DISTINCT FROM true
   THEN RAISE EXCEPTION 'b3_capsule_conflict'; END IF;
  END LOOP;
  IF (capsule->>'request_started_wall_us')::bigint>(capsule->>'received_wall_us')::bigint
   OR (capsule->>'request_started_monotonic_us')::bigint>(capsule->>'received_monotonic_us')::bigint
  THEN RAISE EXCEPTION 'b3_capsule_conflict'; END IF;
  raw:=pg_catalog.decode(capsule->>'response_base64','base64');
  IF pg_catalog.octet_length(raw) NOT BETWEEN 1 AND max_bytes
   OR capsule->'response_bytes' IS DISTINCT FROM pg_catalog.to_jsonb(pg_catalog.octet_length(raw)::text)
   OR pg_catalog.encode(pg_catalog.sha256(raw),'hex') IS DISTINCT FROM capsule->>'response_sha256'
   OR pg_catalog.replace(pg_catalog.encode(raw,'base64'),pg_catalog.chr(10),'') IS DISTINCT FROM capsule->>'response_base64'
  THEN RAISE EXCEPTION 'b3_raw_conflict'; END IF;
 END LOOP;
 RETURN pg_catalog.jsonb_build_object('original_a1_reservation_sha256',c->>'reservation_sha256',
   'original_a1_capture_sha256',vn_jupiter_b2_allocation_research_v3._sha(wire),
   'collection_completed',true,'eligibility',false,'terminal',false);
END;
$packet$;

-- FUNCTION _packet_plan
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._packet_plan(command pg_catalog.jsonb, auth pg_catalog.jsonb,
 position_no pg_catalog.int8, writer_binding pg_catalog.text, fence pg_catalog.jsonb, prior_wire pg_catalog.text)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path='pg_catalog','pg_temp' SET TimeZone='UTC' SET client_encoding='UTF8' SET standard_conforming_strings='on'
AS $packet$
DECLARE g jsonb:=(auth->>'genesis_wire')::jsonb; p jsonb:=auth#>'{package,policies}'; prior jsonb:=prior_wire::jsonb;
 b jsonb:=command->'body'; scope jsonb:=command->'scope'; r jsonb; prepared jsonb; issuer jsonb; policy jsonb;
 ids jsonb:='{}'; identity_rows jsonb:='[]'; value_text text; role_key text; deps jsonb; outcome jsonb;
 ch text:=vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(command));
 reservation_roles text[]:=ARRAY['reservation_id','capture_id','admission_id','observation_id','price_record_id','genesis_record_id','block_time_record_id'];
 native_roles text[]:=ARRAY['read_observation_id','availability_id','closure_id','reconcile_id'];
BEGIN
 IF pg_catalog.jsonb_typeof(auth->'handoff') IS DISTINCT FROM 'object'
  OR auth#>>'{handoff,successor_binding,principal_binding_id}' IS DISTINCT FROM writer_binding
  OR fence->>'holder_principal_binding_id' IS DISTINCT FROM writer_binding OR fence->'scope' IS DISTINCT FROM scope
  OR fence->'acquisition_epoch' IS DISTINCT FROM g#>'{initial_acquisition_spec,acquisition_epoch}'
  OR fence->'revision' IS DISTINCT FROM '"2"'::jsonb OR fence->'native_sequence' IS DISTINCT FROM '"4"'::jsonb
  OR command->'expected_fence_id' IS DISTINCT FROM fence->'fence_id'
  OR command->'expected_fence_revision' IS DISTINCT FROM fence->'revision'
  OR p->>'a1_schema_sha256' IS DISTINCT FROM '2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640'
  OR p->>'acquisition_sha256' IS DISTINCT FROM '912fd28c718311f9b6f72cf0327a7c6b5f4ec7cc4033744d3306064ed869ac89'
  OR p->>'source_sha256' IS DISTINCT FROM '3be1de572d954859002546e5d525ddb0fbda71a5ca844368381a98395571aad1'
  OR p->>'transport_sha256' IS DISTINCT FROM 'a62184b94f88dbc248a6f3569e171a60e8a0a530addf8ed8aa943b10433f055e'
  OR prior->'scope' IS DISTINCT FROM scope
 THEN RAISE EXCEPTION 'b3_packet_authority_refused' USING ERRCODE='42501'; END IF;
 IF command->>'action_kind'='packet_reservation' THEN
  IF position_no<>5 OR prior->>'action_kind' IS DISTINCT FROM 'fence_renew'
   OR NOT vn_jupiter_b2_allocation_research_v3._keys(b,ARRAY['reservation_wire','prepared_packet_wire','read_observation_id','availability_id','closure_id','reconcile_id'])
   OR pg_catalog.jsonb_typeof(b->'reservation_wire') IS DISTINCT FROM 'string'
   OR pg_catalog.jsonb_typeof(b->'prepared_packet_wire') IS DISTINCT FROM 'string'
   OR pg_catalog.octet_length(b->>'reservation_wire')>8192 OR pg_catalog.octet_length(b->>'prepared_packet_wire')>8192
  THEN RAISE EXCEPTION 'b3_reservation_refused'; END IF;
  issuer:=scope||pg_catalog.jsonb_build_object('acquisition_epoch',g#>'{initial_acquisition_spec,acquisition_epoch}',
    'issuer_binding_id',g#>'{initial_acquisition_spec,issuer_binding_id}',
    'endpoint_bindings',g#>'{initial_acquisition_spec,endpoint_bindings}','parser_policy_sha256',p->'acquisition_sha256');
  policy:=p-ARRAY['a1_schema_sha256','raw_parser_sha256','reader_package_sha256'];
  r:=(b->>'reservation_wire')::jsonb;
  IF NOT vn_jupiter_b2_allocation_research_v3._keys(r,ARRAY['admission_id','authority','block_time_record_id','block_time_rpc_id',
     'capture_id','format','genesis_record_id','genesis_rpc_id','issuer','issuer_principal_binding_id','observation_id','policies',
     'policy_sha256','price_record_id','reservation_id','scope'])
   OR vn_jupiter_b2_allocation_research_v3._c14n(r) IS DISTINCT FROM b->>'reservation_wire'
   OR r->'scope' IS DISTINCT FROM scope OR r->'issuer' IS DISTINCT FROM issuer OR r->'policies' IS DISTINCT FROM policy
   OR r->'policy_sha256' IS DISTINCT FROM p->'a1_schema_sha256'
   OR r->>'format' IS DISTINCT FROM 'ga-jupiter-source-reservation-research-v3'
   OR r->'issuer_principal_binding_id' IS DISTINCT FROM pg_catalog.to_jsonb(writer_binding)
   OR r->'reservation_id' IS DISTINCT FROM command->'action_id'
   OR r->'genesis_rpc_id' IS DISTINCT FROM '"1"'::jsonb OR r->'block_time_rpc_id' IS DISTINCT FROM '"2"'::jsonb
   OR r->'authority' IS DISTINCT FROM '{"authenticated_principal":false,"calibrated_clock":false,"committed_readback":false,"hosted_authority":false,"lease_authority":false,"live_trading_authority":false,"native_admission":false,"provider_attested":false,"running_authority":false}'::jsonb
  THEN RAISE EXCEPTION 'b3_reservation_refused'; END IF;
  prepared:=pg_catalog.jsonb_build_object('format','ga-provider-prepared-original-readonly-packet-research-v3',
    'transport_policy_sha256',p->'transport_sha256','binding',issuer-'endpoint_bindings',
    'endpoints',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(e.value->'provider_family',e.value->'endpoint_binding_id') ORDER BY e.ord)
      FROM pg_catalog.jsonb_array_elements(issuer->'endpoint_bindings') WITH ORDINALITY e(value,ord)),
    'price_record_id',r->'price_record_id','genesis_record_id',r->'genesis_record_id','block_time_record_id',r->'block_time_record_id',
    'observation_id',r->'observation_id','genesis_rpc_id',r->'genesis_rpc_id','block_time_rpc_id',r->'block_time_rpc_id');
  IF vn_jupiter_b2_allocation_research_v3._c14n(prepared) IS DISTINCT FROM b->>'prepared_packet_wire'
  THEN RAISE EXCEPTION 'b3_prepared_conflict'; END IF;
  FOREACH role_key IN ARRAY (reservation_roles||native_roles) LOOP
   value_text:=CASE WHEN role_key=ANY(reservation_roles) THEN r->>role_key ELSE b->>role_key END;
   IF (CASE WHEN role_key=ANY(reservation_roles) THEN pg_catalog.jsonb_typeof(r->role_key)
       ELSE pg_catalog.jsonb_typeof(b->role_key) END) IS DISTINCT FROM 'string'
    OR (value_text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true
    OR value_text IN(writer_binding,auth#>>'{handoff,successor_binding,issuance_id}',auth#>>'{handoff,handoff_id}')
    OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_each_text(ids) e WHERE e.value=value_text)
   THEN RAISE EXCEPTION 'b3_identity_conflict'; END IF;
   ids:=ids||pg_catalog.jsonb_build_object(role_key,value_text);
   identity_rows:=identity_rows||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('original_id',value_text,
    'identity_role',role_key,'association',scope||pg_catalog.jsonb_build_object('packet_reservation_id',command->>'action_id'),
    'original_allocation_sha256',ch,'first_native_sequence',position_no::text));
  END LOOP;
  outcome:=pg_catalog.jsonb_build_object('packet_ids',ids,
    'original_a1_reservation_sha256',vn_jupiter_b2_allocation_research_v3._sha(b->>'reservation_wire'),
    'prepared_packet_sha256',vn_jupiter_b2_allocation_research_v3._sha(b->>'prepared_packet_wire'),
    'capture_status','unresolved');
 ELSE
  IF command->>'action_kind' IS DISTINCT FROM 'capture_retention' OR position_no<>6
   OR prior->>'action_kind' IS DISTINCT FROM 'packet_reservation'
   OR NOT vn_jupiter_b2_allocation_research_v3._keys(b,ARRAY['reservation_action_id','capture_wire'])
   OR b->'reservation_action_id' IS DISTINCT FROM prior->'action_id'
   OR pg_catalog.jsonb_typeof(b->'capture_wire') IS DISTINCT FROM 'string'
   OR prior->'expected_fence_id' IS DISTINCT FROM fence->'fence_id'
   OR prior->'expected_fence_revision' IS DISTINCT FROM fence->'revision'
  THEN RAISE EXCEPTION 'b3_capture_refused'; END IF;
  outcome:=vn_jupiter_b2_allocation_research_v3._packet_capture(b->>'capture_wire',prior#>>'{body,reservation_wire}',command->>'action_id')
    ||pg_catalog.jsonb_build_object('reservation_action_id',prior->>'action_id');
 END IF;
 deps:=vn_jupiter_b2_allocation_research_v3._deps(pg_catalog.jsonb_build_array(
  vn_jupiter_b2_allocation_research_v3._pin('native_command',prior->>'action_id',prior_wire),
  vn_jupiter_b2_allocation_research_v3._pin('native_fence_record',fence->>'fence_id',vn_jupiter_b2_allocation_research_v3._c14n(fence))));
 RETURN pg_catalog.jsonb_build_object('ids',identity_rows,'dependencies',deps,'body',outcome);
END;
$packet$;

REVOKE ALL ON FUNCTION vn_jupiter_b2_allocation_research_v3._packet_capture(pg_catalog.text,pg_catalog.text,pg_catalog.text),
 vn_jupiter_b2_allocation_research_v3._packet_plan(pg_catalog.jsonb,pg_catalog.jsonb,pg_catalog.int8,pg_catalog.text,pg_catalog.jsonb,pg_catalog.text)
 FROM PUBLIC;
RESET ROLE;
COMMIT;
