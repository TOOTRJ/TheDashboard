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
 diagnostic jsonb; diagnostic_index int; capsule_count int; clock_value text; body_state text;
 price_raw bytea; price_text text; price_record json; slot_token text; expected_request text;
 mint constant text:='So11111111111111111111111111111111111111112';
 record_keys constant text[]:=ARRAY['price_record_id','genesis_record_id','block_time_record_id'];
 failure_codes constant text[]:=ARRAY['acquisition_deadline','invalid_response_metadata','cleanup_incomplete',
  'invalid_response_encoding','invalid_response_length','response_overflow','credential_echo_withheld',
  'invalid_json_for_credential_scan','request_unavailable','invalid_or_unavailable_record','price_http_failure',
  'wrong_network','invalid_or_unavailable_packet','unsupported_logging_runtime','invalid_tls_runtime',
  'unsupported_transport_runtime'];
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
  OR pg_catalog.jsonb_typeof(c->'collection_completed') IS DISTINCT FROM 'boolean'
  OR c->'eligibility' IS DISTINCT FROM 'false'::jsonb
  OR pg_catalog.jsonb_typeof(c->'capsule_wires') IS DISTINCT FROM 'array'
  OR pg_catalog.jsonb_typeof(c->'diagnostics') IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'b3_capture_shape'; END IF;
 capsule_count:=pg_catalog.jsonb_array_length(c->'capsule_wires');
 IF capsule_count>3 OR pg_catalog.jsonb_array_length(c->'diagnostics')>1
  OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(c->'capsule_wires') e(value)
   WHERE pg_catalog.jsonb_typeof(e.value) IS DISTINCT FROM 'string')
  OR (CASE WHEN c->'collection_completed'='true'::jsonb THEN
      capsule_count<>3 OR c->'failure_code' IS DISTINCT FROM 'null'::jsonb OR c->'diagnostics'<>'[]'::jsonb
     ELSE ((c->>'failure_code')=ANY(failure_codes)) IS DISTINCT FROM true END)
 THEN RAISE EXCEPTION 'b3_capture_shape'; END IF;
 FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements_text(c->'capsule_wires') LOOP
  index_no:=index_no+1; capsule:=item::jsonb;
  record_key:=record_keys[index_no];
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
   OR capsule->>'provider_family' IS DISTINCT FROM family
   OR pg_catalog.jsonb_typeof(capsule->'http_status') IS DISTINCT FROM 'string'
   OR (capsule->>'http_status' ~ '^[1-5][0-9]{2}$') IS DISTINCT FROM true
   OR (c->'collection_completed'='true'::jsonb AND capsule->>'http_status'<>'200')
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
    OR body->>'id' IS DISTINCT FROM (r->>(CASE WHEN index_no=2 THEN 'genesis_rpc_id' ELSE 'block_time_rpc_id' END))
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
   clock_value:=capsule->>clock_key;
   IF pg_catalog.jsonb_typeof(capsule->clock_key) IS DISTINCT FROM 'string'
    OR (clock_value ~ '^(0|[1-9][0-9]{0,18})$') IS DISTINCT FROM true
    OR (pg_catalog.length(clock_value)=19 AND clock_value COLLATE "C">'9223372036854775807')
   THEN RAISE EXCEPTION 'b3_capsule_conflict'; END IF;
  END LOOP;
  IF (capsule->>'request_started_wall_us')::bigint>(capsule->>'received_wall_us')::bigint
   OR (capsule->>'request_started_monotonic_us')::bigint>(capsule->>'received_monotonic_us')::bigint
  THEN RAISE EXCEPTION 'b3_capsule_conflict'; END IF;
  raw:=pg_catalog.decode(capsule->>'response_base64','base64');
  IF pg_catalog.octet_length(raw)>max_bytes
   OR (pg_catalog.octet_length(raw)=0 AND capsule->>'http_status'='200')
   OR capsule->'response_bytes' IS DISTINCT FROM pg_catalog.to_jsonb(pg_catalog.octet_length(raw)::text)
   OR pg_catalog.encode(pg_catalog.sha256(raw),'hex') IS DISTINCT FROM capsule->>'response_sha256'
   OR pg_catalog.replace(pg_catalog.encode(raw,'base64'),pg_catalog.chr(10),'') IS DISTINCT FROM capsule->>'response_base64'
  THEN RAISE EXCEPTION 'b3_raw_conflict'; END IF;
  IF index_no=1 THEN price_raw:=raw; END IF;
 END LOOP;

 IF c->'diagnostics'<>'[]'::jsonb THEN
  diagnostic:=c#>'{diagnostics,0}';
  SELECT i INTO diagnostic_index FROM pg_catalog.generate_subscripts(record_keys,1) i
   WHERE diagnostic->'record_id'=r->record_keys[i];
  body_state:=diagnostic->>'body_state';
  IF NOT vn_jupiter_b2_allocation_research_v3._keys(diagnostic,ARRAY['record_id','provider_family',
      'endpoint_binding_id','request_sha256','request_started_wall_us','request_started_monotonic_us',
      'received_wall_us','received_monotonic_us','http_status','body_state','incomplete','failure_code'])
   OR diagnostic_index IS NULL OR diagnostic_index>capsule_count+1
   OR diagnostic->>'provider_family' IS DISTINCT FROM (CASE WHEN diagnostic_index=1 THEN 'jupiter-price-v3' ELSE 'solana-rpc' END)
   OR diagnostic->'endpoint_binding_id' IS DISTINCT FROM
      (r#>(CASE WHEN diagnostic_index=1 THEN '{issuer,endpoint_bindings,0,endpoint_binding_id}'::text[]
       ELSE '{issuer,endpoint_bindings,1,endpoint_binding_id}'::text[] END))
   OR (body_state IN('not_received','partial_discarded','withheld','captured_original')) IS DISTINCT FROM true
   OR (body_state='captured_original') IS DISTINCT FROM (diagnostic_index<=capsule_count)
   OR diagnostic->'incomplete' IS DISTINCT FROM 'true'::jsonb
   OR ((diagnostic->>'failure_code')=ANY(failure_codes)) IS DISTINCT FROM true
   OR (diagnostic->'http_status'<>'null'::jsonb AND (pg_catalog.jsonb_typeof(diagnostic->'http_status')<>'string'
       OR (diagnostic->>'http_status' ~ '^[1-5][0-9]{2}$') IS DISTINCT FROM true))
   OR (diagnostic->'received_wall_us'='null'::jsonb) IS DISTINCT FROM (diagnostic->'received_monotonic_us'='null'::jsonb)
   OR (body_state='not_received' AND diagnostic->'received_wall_us'<>'null'::jsonb)
   OR (body_state='withheld' AND diagnostic->'received_wall_us'='null'::jsonb)
  THEN RAISE EXCEPTION 'b3_diagnostic_conflict'; END IF;

  FOREACH clock_key IN ARRAY ARRAY['received_wall_us','received_monotonic_us','request_started_wall_us','request_started_monotonic_us'] LOOP
   clock_value:=diagnostic->>clock_key;
   IF clock_value IS NULL AND clock_key IN('received_wall_us','received_monotonic_us') THEN CONTINUE; END IF;
   IF pg_catalog.jsonb_typeof(diagnostic->clock_key) IS DISTINCT FROM 'string'
    OR (clock_value ~ '^(0|[1-9][0-9]{0,18})$') IS DISTINCT FROM true
    OR (pg_catalog.length(clock_value)=19 AND clock_value COLLATE "C">'9223372036854775807')
   THEN RAISE EXCEPTION 'b3_diagnostic_conflict'; END IF;
  END LOOP;

  IF body_state='captured_original' THEN
   capsule:=(c->'capsule_wires'->>(diagnostic_index-1))::jsonb;
   FOREACH clock_key IN ARRAY ARRAY['request_sha256','received_wall_us','received_monotonic_us',
       'request_started_wall_us','request_started_monotonic_us','http_status'] LOOP
    IF diagnostic->clock_key IS DISTINCT FROM capsule->clock_key THEN RAISE EXCEPTION 'b3_diagnostic_conflict'; END IF;
   END LOOP;
  ELSE
   IF diagnostic_index=1 THEN
    request:=pg_catalog.jsonb_build_object('format','ga-provider-public-request-research-v3','method','GET',
     'endpoint','https://api.jup.ag/price/v3','chain','solana','parameters',pg_catalog.jsonb_build_object('ids',mint),
     'body_wire',NULL);
   ELSE
    body:=pg_catalog.jsonb_build_object('id',(r->>(CASE WHEN diagnostic_index=2 THEN 'genesis_rpc_id' ELSE 'block_time_rpc_id' END))::int,
     'jsonrpc','2.0','method',(CASE WHEN diagnostic_index=2 THEN 'getGenesisHash' ELSE 'getBlockTime' END),
     'params','[]'::jsonb);
    IF diagnostic_index=3 THEN
     -- The request used the block ID from the already retained Jupiter body.
     -- Use json for the field so numeric exponent and decimal spellings stay visible.
     BEGIN
      price_text:=pg_catalog.convert_from(price_raw,'UTF8');
      IF (price_text IS JSON OBJECT WITH UNIQUE KEYS) IS DISTINCT FROM true THEN RAISE EXCEPTION 'b3_diagnostic_conflict'; END IF;
      price_record:=price_text::json->mint;
      slot_token:=price_record->>'blockId';
     EXCEPTION WHEN character_not_in_repertoire OR untranslatable_character THEN
      RAISE EXCEPTION 'b3_diagnostic_conflict';
     END;
     IF pg_catalog.json_typeof(price_record->'blockId') IS DISTINCT FROM 'number'
      OR (slot_token ~ '^(0|[1-9][0-9]{0,19})$') IS DISTINCT FROM true
      OR (pg_catalog.length(slot_token)=20 AND slot_token COLLATE "C">'18446744073709551615')
     THEN RAISE EXCEPTION 'b3_diagnostic_conflict'; END IF;
     body:=pg_catalog.jsonb_set(body,'{params}',pg_catalog.jsonb_build_array(slot_token::numeric));
    END IF;
    request:=pg_catalog.jsonb_build_object('format','ga-provider-public-request-research-v3','method','POST',
     'endpoint','operator-bound-solana-rpc','chain','solana','parameters','{}'::jsonb,
     'body_wire',vn_jupiter_b2_allocation_research_v3._c14n(body));
   END IF;
   expected_request:=vn_jupiter_b2_allocation_research_v3._c14n(request);
   IF pg_catalog.jsonb_typeof(diagnostic->'request_sha256') IS DISTINCT FROM 'string'
    OR diagnostic->>'request_sha256' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._sha(expected_request)
   THEN RAISE EXCEPTION 'b3_diagnostic_conflict'; END IF;
  END IF;
 END IF;
 RETURN pg_catalog.jsonb_build_object('original_a1_reservation_sha256',c->>'reservation_sha256',
   'original_a1_capture_sha256',vn_jupiter_b2_allocation_research_v3._sha(wire),
   'collection_completed',c->'collection_completed','eligibility',false,'terminal',false);
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
  OR (CASE WHEN command->>'action_kind'='capture_retention' THEN
   command->'expected_fence_id' IS DISTINCT FROM 'null'::jsonb OR command->'expected_fence_revision' IS DISTINCT FROM 'null'::jsonb
   ELSE command->'expected_fence_id' IS DISTINCT FROM fence->'fence_id' OR command->'expected_fence_revision' IS DISTINCT FROM fence->'revision' END)
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
  IF command->>'action_kind' IS DISTINCT FROM 'capture_retention' OR position_no NOT IN(6,7)
   OR command->>'native_policy_sha256' IS DISTINCT FROM 'c468fa4a7fa8e9122a53abb19ed10d3c1d80f8024dfeefbb8596fef8f1c1f8be'
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

-- FUNCTION _collection_authorization
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._collection_authorization(wire pg_catalog.text)
RETURNS pg_catalog.text
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path='pg_catalog','pg_temp' SET TimeZone='UTC' SET client_encoding='UTF8' SET standard_conforming_strings='on'
AS $packet$
DECLARE q jsonb; sw text; a jsonb; h jsonb; reservation_row record; reply jsonb; receipt jsonb;
 r jsonb; fence jsonb; observed bigint; cutoff bigint; expected_record text;
BEGIN
 IF wire IS NULL OR pg_catalog.octet_length(wire)>2048 THEN RAISE EXCEPTION 'b3_collection_query_refused'; END IF;
 q:=wire::jsonb;
 IF vn_jupiter_b2_allocation_research_v3._c14n(q) IS DISTINCT FROM wire
  OR NOT vn_jupiter_b2_allocation_research_v3._keys(q,ARRAY['format','scope','reservation_id','reservation_command_sha256','head_sha256','record_id','provider_family','request_sha256'])
  OR q->'format' IS DISTINCT FROM '"ga-jupiter-b3-collection-authorization-query-v2"'::jsonb
  OR pg_catalog.jsonb_typeof(q->'reservation_id') IS DISTINCT FROM 'string'
  OR (q->>'reservation_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true
  OR pg_catalog.jsonb_typeof(q->'record_id') IS DISTINCT FROM 'string'
  OR (q->>'record_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true
  OR q->'provider_family' NOT IN ('"jupiter-price-v3"'::jsonb,'"solana-rpc"'::jsonb)
  OR EXISTS (SELECT 1 FROM pg_catalog.unnest(ARRAY['reservation_command_sha256','head_sha256','request_sha256']) f(key)
   WHERE pg_catalog.jsonb_typeof(q->f.key) IS DISTINCT FROM 'string' OR (q->>f.key ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true)
 THEN RAISE EXCEPTION 'b3_collection_query_refused'; END IF;
 sw:=vn_jupiter_b2_allocation_research_v3._scope(q->'scope');
 a:=vn_jupiter_b2_allocation_research_v3._auth(q->'scope','reserve',NULL,NULL,NULL);
 IF pg_catalog.jsonb_typeof(a->'handoff') IS DISTINCT FROM 'object'
  OR a#>>'{handoff,successor_binding,principal_binding_id}' IS DISTINCT FROM a->>'binding_id'
  OR a#>>'{package,policies,a1_schema_sha256}' IS DISTINCT FROM '2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640'
 THEN RAISE EXCEPTION 'b3_collection_actor_refused' USING ERRCODE='42501'; END IF;
 SELECT head_wire::jsonb INTO h FROM vn_jupiter_b2_allocation_research_v3.scope_state WHERE scope_wire=sw;
 IF NOT FOUND OR h->>'source_mode' IS DISTINCT FROM 'open' OR h->>'native_sequence' IS DISTINCT FROM '5'
  OR h->>'native_head_sha256' IS DISTINCT FROM q->>'head_sha256' OR h->>'fence_revision' IS DISTINCT FROM '2'
 THEN RAISE EXCEPTION 'b3_collection_head_refused'; END IF;
 -- Keep the intent lookup in the same MVCC snapshot as the journal head.
 IF EXISTS (SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.stop_intents WHERE scope_wire=sw)
 THEN RAISE EXCEPTION 'b2_stop_intent_pending' USING ERRCODE='42501'; END IF;
 SELECT * INTO reservation_row FROM vn_jupiter_b2_allocation_research_v3.original_operations o
 WHERE o.scope_wire=sw AND o.action_kind='packet_reservation' AND o.native_sequence=5 AND o.finalized
 AND o.action_id=q->>'reservation_id' AND o.command_sha256=q->>'reservation_command_sha256' AND o.writer_binding_id=a->>'binding_id';
 IF NOT FOUND THEN RAISE EXCEPTION 'b3_collection_reservation_refused'; END IF;
 reply:=vn_jupiter_b2_allocation_research_v3._reply(q->'scope',reservation_row.action_id,reservation_row.command_sha256,false,NULL)::jsonb;
 IF reply#>>'{observed_head,native_head_sha256}' IS DISTINCT FROM h->>'native_head_sha256'
 THEN RAISE EXCEPTION 'b3_collection_head_refused'; END IF;
 receipt:=(reply->>'original_receipt_wire')::jsonb;
 r:=(reservation_row.command_wire::jsonb#>>'{body,reservation_wire}')::jsonb;
 IF q->>'provider_family'='jupiter-price-v3' THEN
  expected_record:=r->>'price_record_id';
 ELSE
  IF q->>'record_id'=r->>'genesis_record_id' THEN expected_record:=r->>'genesis_record_id';
  ELSE expected_record:=r->>'block_time_record_id'; END IF;
 END IF;
 IF q->>'record_id' IS DISTINCT FROM expected_record THEN RAISE EXCEPTION 'b3_collection_record_refused'; END IF;
 SELECT (d->>'original_wire')::jsonb INTO fence FROM pg_catalog.jsonb_array_elements((reply->>'original_result_wire')::jsonb->'dependencies') d
 WHERE d->>'semantic_kind'='native_fence_record' AND d->>'original_id'=h->>'active_fence_id';
 IF NOT FOUND OR fence->>'holder_principal_binding_id' IS DISTINCT FROM a->>'binding_id'
  OR fence->>'revision' IS DISTINCT FROM h->>'fence_revision' OR fence->>'acquisition_epoch' IS DISTINCT FROM h->>'active_acquisition_epoch'
 THEN RAISE EXCEPTION 'b3_collection_fence_refused'; END IF;
 SELECT pg_catalog.min(least((w->>'cutoff_us')::bigint,(w->>'login_until_us')::bigint)) INTO cutoff
 FROM pg_catalog.jsonb_array_elements(a->'credential_windows') w;
 IF cutoff IS NULL THEN RAISE EXCEPTION 'b3_collection_actor_refused' USING ERRCODE='42501'; END IF;
 cutoff:=least(cutoff,(fence->>'expires_at_us')::bigint);
 observed:=(vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint;
 PERFORM vn_jupiter_b2_allocation_research_v3._check_credential_window(a->'credential_windows',observed);
 IF observed<(receipt#>>'{commit_processing_observation,observed_at_us}')::bigint OR observed>=cutoff
 THEN RAISE EXCEPTION 'b3_collection_fence_refused'; END IF;
 RETURN vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_object(
  'format','ga-jupiter-b3-collection-authorization-observation-v2','query_sha256',vn_jupiter_b2_allocation_research_v3._sha(wire),
  'fence_id',fence->>'fence_id','fence_revision',fence->>'revision','observed_at_us',observed::text,'valid_until_us',cutoff::text));
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RAISE EXCEPTION 'b3_collection_query_refused';
END;
$packet$;

REVOKE ALL ON FUNCTION vn_jupiter_b2_allocation_research_v3._packet_capture(pg_catalog.text,pg_catalog.text,pg_catalog.text),
 vn_jupiter_b2_allocation_research_v3._packet_plan(pg_catalog.jsonb,pg_catalog.jsonb,pg_catalog.int8,pg_catalog.text,pg_catalog.jsonb,pg_catalog.text),
 vn_jupiter_b2_allocation_research_v3._collection_authorization(pg_catalog.text)
 FROM PUBLIC;
RESET ROLE;
COMMIT;
