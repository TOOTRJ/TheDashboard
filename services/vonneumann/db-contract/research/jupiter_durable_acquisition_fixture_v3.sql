-- Disposable network-none fixture only. No migration or hosted authority.
BEGIN;
CREATE ROLE dcap_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE dcap_recorder LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE dcap_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE dcap_foreign LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE SCHEMA dcap AUTHORIZATION dcap_owner;
REVOKE ALL ON SCHEMA dcap FROM PUBLIC;
SET LOCAL ROLE dcap_owner;
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
CREATE TABLE dcap.scope_access (
    scope_wire text PRIMARY KEY, recorder_oid oid NOT NULL, reader_oid oid NOT NULL,
    issuer jsonb NOT NULL, policies jsonb NOT NULL, issuer_principal_binding_id uuid NOT NULL
);
CREATE TABLE dcap.packets (
    scope_wire text PRIMARY KEY REFERENCES dcap.scope_access, reservation_id uuid NOT NULL UNIQUE,
    capture_id uuid NOT NULL UNIQUE, availability_id uuid NOT NULL, closure_id uuid NOT NULL,
    reservation_wire text NOT NULL, prepared_wire text NOT NULL, reservation_sha256 text NOT NULL,
    reservation_receipt_wire text NOT NULL, capture_wire text, capture_sha256 text, capture_receipt_wire text,
    CHECK ((capture_wire IS NULL) = (capture_sha256 IS NULL)
       AND (capture_wire IS NULL) = (capture_receipt_wire IS NULL))
);
CREATE TABLE dcap.identities (original_id uuid PRIMARY KEY, scope_wire text NOT NULL REFERENCES dcap.packets);

-- Same recursive JSON ordering as the held B2 research canonical encoder.
CREATE FUNCTION dcap.c14n(v jsonb) RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT
SET search_path=pg_catalog,pg_temp AS $$
DECLARE result text;
BEGIN
    CASE jsonb_typeof(v)
    WHEN 'object' THEN
        SELECT '{'||coalesce(string_agg(to_jsonb(x.key)::text||':'||dcap.c14n(x.value),',' ORDER BY x.key COLLATE "C"),'')||'}'
        INTO result FROM jsonb_each(v) x;
    WHEN 'array' THEN
        SELECT '['||coalesce(string_agg(dcap.c14n(x.value),',' ORDER BY x.ord),'')||']'
        INTO result FROM jsonb_array_elements(v) WITH ORDINALITY x(value,ord);
    ELSE result:=v::text;
    END CASE;
    RETURN result;
END $$;
CREATE FUNCTION dcap.sha(v text) RETURNS text LANGUAGE sql IMMUTABLE STRICT
SET search_path=pg_catalog,pg_temp AS $$ SELECT encode(sha256(convert_to(v,'UTF8')),'hex') $$;

CREATE FUNCTION dcap.keys_are(v jsonb, expected text[]) RETURNS boolean LANGUAGE sql IMMUTABLE
SET search_path=pg_catalog,pg_temp AS $$
    SELECT CASE WHEN jsonb_typeof(v)='object' THEN v ?& expected AND v-expected='{}'::jsonb ELSE false END
$$;

CREATE FUNCTION dcap.reserve(s text,r text,p text,availability uuid,closure uuid) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE anchor dcap.scope_access%ROWTYPE; old dcap.packets%ROWTYPE; w jsonb; wanted jsonb; ids uuid[]; rid uuid; cid uuid; h text;
BEGIN
    SELECT * INTO anchor FROM dcap.scope_access WHERE scope_wire=s AND recorder_oid=(session_user::regrole)::oid FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'dcap_scope_refused' USING ERRCODE='42501'; END IF;
    IF r IS NULL OR p IS NULL OR availability IS NULL OR closure IS NULL OR octet_length(r)>8192 OR octet_length(p)>8192 THEN
        RAISE EXCEPTION 'dcap_reservation_shape'; END IF;
    w:=r::jsonb;
    IF NOT dcap.keys_are(w,ARRAY['admission_id','authority','block_time_record_id','block_time_rpc_id','capture_id','format','genesis_record_id','genesis_rpc_id','issuer','issuer_principal_binding_id','observation_id','policies','policy_sha256','price_record_id','reservation_id','scope'])
       OR w->'authority' IS DISTINCT FROM '{"authenticated_principal":false,"calibrated_clock":false,"committed_readback":false,"hosted_authority":false,"lease_authority":false,"live_trading_authority":false,"native_admission":false,"provider_attested":false,"running_authority":false}'::jsonb
       OR dcap.c14n(w) IS DISTINCT FROM r OR dcap.c14n(w->'scope') IS DISTINCT FROM s
       OR w->>'format' IS DISTINCT FROM 'ga-jupiter-source-reservation-research-v3'
       OR w->>'policy_sha256' IS DISTINCT FROM '2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640'
       OR w->'issuer' IS DISTINCT FROM anchor.issuer OR w->'policies' IS DISTINCT FROM anchor.policies
       OR w->>'issuer_principal_binding_id' IS DISTINCT FROM anchor.issuer_principal_binding_id::text THEN
        RAISE EXCEPTION 'dcap_reservation_shape'; END IF;
    wanted:=jsonb_build_object('format','ga-provider-prepared-original-readonly-packet-research-v3',
        'transport_policy_sha256','a62184b94f88dbc248a6f3569e171a60e8a0a530addf8ed8aa943b10433f055e',
        'binding',anchor.issuer-'endpoint_bindings',
        'endpoints',(SELECT jsonb_agg(jsonb_build_array(x.value->'provider_family',x.value->'endpoint_binding_id') ORDER BY x.ord)
                     FROM jsonb_array_elements(anchor.issuer->'endpoint_bindings') WITH ORDINALITY x(value,ord)),
        'price_record_id',w->'price_record_id','genesis_record_id',w->'genesis_record_id',
        'block_time_record_id',w->'block_time_record_id','observation_id',w->'observation_id',
        'genesis_rpc_id',w->'genesis_rpc_id','block_time_rpc_id',w->'block_time_rpc_id');
    IF dcap.c14n(wanted) IS DISTINCT FROM p OR w->>'genesis_rpc_id' IS DISTINCT FROM '1'
       OR w->>'block_time_rpc_id' IS DISTINCT FROM '2' THEN RAISE EXCEPTION 'dcap_prepared_conflict'; END IF;
    rid:=(w->>'reservation_id')::uuid; cid:=(w->>'capture_id')::uuid;
    ids:=ARRAY[rid,cid,(w->>'admission_id')::uuid,(w->>'observation_id')::uuid,(w->>'price_record_id')::uuid,
        (w->>'genesis_record_id')::uuid,(w->>'block_time_record_id')::uuid,availability,closure];
    IF EXISTS (SELECT 1 FROM unnest(ARRAY['reservation_id','capture_id','admission_id','observation_id',
        'price_record_id','genesis_record_id','block_time_record_id']) k WHERE w->>k IS DISTINCT FROM ((w->>k)::uuid)::text)
       OR (SELECT count(DISTINCT id) FROM unnest(ids) id)<>9 OR EXISTS (
        SELECT 1 FROM unnest(ids) id WHERE id::text IN (
            w#>>'{scope,owner_id}',w#>>'{scope,run_id}',w#>>'{scope,market_epoch}',w#>>'{issuer,acquisition_epoch}',
            w#>>'{issuer,issuer_binding_id}',anchor.issuer_principal_binding_id::text,
            w#>>'{issuer,endpoint_bindings,0,endpoint_binding_id}',w#>>'{issuer,endpoint_bindings,1,endpoint_binding_id}')) THEN
        RAISE EXCEPTION 'dcap_identity_conflict'; END IF;
    h:=dcap.sha(r);
    SELECT * INTO old FROM dcap.packets WHERE scope_wire=s;
    IF FOUND THEN
        IF old.reservation_wire=r AND old.prepared_wire=p AND old.availability_id=availability AND old.closure_id=closure THEN
            RETURN jsonb_build_object('created',false,'reservation_sha256',h);
        END IF;
        RAISE EXCEPTION 'dcap_scope_unresolved';
    END IF;
    INSERT INTO dcap.packets (scope_wire,reservation_id,capture_id,availability_id,closure_id,reservation_wire,prepared_wire,
        reservation_sha256,reservation_receipt_wire) VALUES (s,rid,cid,availability,closure,r,p,h,
        dcap.c14n(jsonb_build_object('kind','fixture_reservation','reservation_id',rid,'reservation_sha256',h,
            'scope',s::jsonb,'prepared_sha256',dcap.sha(p),'availability_id',availability,'closure_id',closure)));
    INSERT INTO dcap.identities SELECT id,s FROM unnest(ids) id;
    RETURN jsonb_build_object('created',true,'reservation_sha256',h);
END $$;

CREATE FUNCTION dcap.capture(s text,rid uuid,c text) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE anchor dcap.scope_access%ROWTYPE; old dcap.packets%ROWTYPE; w jsonb; r jsonb;
    source jsonb; original text; record_key text; family text; maximum integer; raw bytea; index_no integer:=0; h text;
BEGIN
    SELECT * INTO anchor FROM dcap.scope_access WHERE scope_wire=s AND recorder_oid=(session_user::regrole)::oid FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'dcap_scope_refused' USING ERRCODE='42501'; END IF;
    SELECT * INTO old FROM dcap.packets WHERE scope_wire=s AND reservation_id=rid;
    IF NOT FOUND THEN RAISE EXCEPTION 'dcap_reservation_missing'; END IF;
    IF c IS NULL OR octet_length(c)>1048576 THEN RAISE EXCEPTION 'dcap_capture_shape'; END IF;
    h:=dcap.sha(c);
    IF old.capture_wire IS NOT NULL THEN
        IF old.capture_wire=c AND old.capture_sha256=h THEN
            RETURN jsonb_build_object('created',false,'capture_sha256',h);
        END IF;
        RAISE EXCEPTION 'dcap_capture_conflict';
    END IF;
    w:=c::jsonb; r:=old.reservation_wire::jsonb;
    IF NOT dcap.keys_are(w,ARRAY['authority','capsule_wires','capture_id','collection_completed','diagnostics','eligibility','failure_code','format','observation_id','policy_sha256','reservation_sha256','scope'])
       OR dcap.c14n(w) IS DISTINCT FROM c OR dcap.c14n(w->'scope') IS DISTINCT FROM s
       OR w->>'format' IS DISTINCT FROM 'ga-jupiter-source-capture-retention-research-v3'
       OR w->>'policy_sha256' IS DISTINCT FROM r->>'policy_sha256' OR w->'authority' IS DISTINCT FROM r->'authority'
       OR w->>'reservation_sha256' IS DISTINCT FROM old.reservation_sha256 OR w->>'capture_id' IS DISTINCT FROM old.capture_id::text
       OR w->>'observation_id' IS DISTINCT FROM r->>'observation_id' OR w->'collection_completed' IS DISTINCT FROM 'true'::jsonb
       OR w->'eligibility' IS DISTINCT FROM 'false'::jsonb OR w->'failure_code' IS DISTINCT FROM 'null'::jsonb
       OR w->'diagnostics' IS DISTINCT FROM '[]'::jsonb OR jsonb_typeof(w->'capsule_wires') IS DISTINCT FROM 'array'
       OR jsonb_array_length(w->'capsule_wires') IS DISTINCT FROM 3 THEN RAISE EXCEPTION 'dcap_capture_shape'; END IF;
    FOR original IN SELECT value FROM jsonb_array_elements_text(w->'capsule_wires') LOOP
        index_no:=index_no+1; source:=original::jsonb;
        record_key:=(ARRAY['price_record_id','genesis_record_id','block_time_record_id'])[index_no];
        family:=CASE WHEN index_no=1 THEN 'jupiter-price-v3' ELSE 'solana-rpc' END;
        maximum:=CASE WHEN index_no=1 THEN 131072 ELSE 65536 END;
        IF NOT dcap.keys_are(source,ARRAY['acquisition_epoch','canonical_public_request_wire','endpoint_binding_id','format','http_status','issuer_binding_id','market_epoch','method','owner_id','parser_policy_sha256','provider_family','raw_response_ref','received_monotonic_us','received_wall_us','record_id','request_sha256','request_started_monotonic_us','request_started_wall_us','response_base64','response_bytes','response_sha256','run_id','safe_response_metadata'])
           OR dcap.c14n(source) IS DISTINCT FROM original OR source->>'format' IS DISTINCT FROM 'ga-provider-acquisition-capsule-research-v3'
           OR source->>'record_id' IS DISTINCT FROM r->>record_key OR source->>'raw_response_ref' IS DISTINCT FROM r->>record_key
           OR source->>'provider_family' IS DISTINCT FROM family OR source->>'http_status' IS DISTINCT FROM '200'
           OR source->>'endpoint_binding_id' IS DISTINCT FROM
              (r#>>(CASE WHEN index_no=1 THEN '{issuer,endpoint_bindings,0,endpoint_binding_id}'::text[]
                        ELSE '{issuer,endpoint_bindings,1,endpoint_binding_id}'::text[] END))
           OR jsonb_typeof(source->'canonical_public_request_wire') IS DISTINCT FROM 'string'
           OR jsonb_typeof(source->'safe_response_metadata') IS DISTINCT FROM 'object'
           OR (source->'safe_response_metadata')-ARRAY['content_type','x_ratelimit_current','x_ratelimit_remaining','x_ratelimit_reset']
              IS DISTINCT FROM '{}'::jsonb
           OR jsonb_typeof(source->'response_base64') IS DISTINCT FROM 'string'
           OR source->>'owner_id' IS DISTINCT FROM r#>>'{scope,owner_id}' OR source->>'run_id' IS DISTINCT FROM r#>>'{scope,run_id}'
           OR source->>'market_epoch' IS DISTINCT FROM r#>>'{scope,market_epoch}'
           OR source->>'acquisition_epoch' IS DISTINCT FROM r#>>'{issuer,acquisition_epoch}'
           OR source->>'issuer_binding_id' IS DISTINCT FROM r#>>'{issuer,issuer_binding_id}'
           OR source->>'parser_policy_sha256' IS DISTINCT FROM r#>>'{issuer,parser_policy_sha256}'
           OR dcap.sha(source->>'canonical_public_request_wire') IS DISTINCT FROM source->>'request_sha256'
           OR source->>'response_base64' IS NULL OR length(source->>'response_base64')>4*((maximum+2)/3) THEN
            RAISE EXCEPTION 'dcap_capsule_conflict'; END IF;
        raw:=decode(source->>'response_base64','base64');
        IF octet_length(raw) NOT BETWEEN 1 AND maximum OR source->>'response_bytes' IS DISTINCT FROM octet_length(raw)::text
           OR encode(sha256(raw),'hex') IS DISTINCT FROM source->>'response_sha256'
           OR replace(encode(raw,'base64'),chr(10),'') IS DISTINCT FROM source->>'response_base64' THEN
            RAISE EXCEPTION 'dcap_raw_conflict'; END IF;
    END LOOP;
    UPDATE dcap.packets SET capture_wire=c,capture_sha256=h,capture_receipt_wire=dcap.c14n(jsonb_build_object(
        'kind','fixture_capture','scope',s::jsonb,'capture_id',old.capture_id,'capture_sha256',h,
        'reservation_sha256',old.reservation_sha256,'eligibility',false)) WHERE scope_wire=s AND reservation_id=rid;
    RETURN jsonb_build_object('created',true,'capture_sha256',h);
END $$;

CREATE FUNCTION dcap.get_original(s text,kind text,target uuid,reservation_hash text,capture_hash text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE original dcap.packets%ROWTYPE;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dcap.scope_access WHERE scope_wire=s AND reader_oid=(session_user::regrole)::oid) THEN
        RAISE EXCEPTION 'dcap_scope_refused' USING ERRCODE='42501'; END IF;
    IF kind IS NULL OR kind NOT IN ('reservation','capture') OR target IS NULL OR reservation_hash IS NULL
       OR NOT (reservation_hash ~ '^[a-f0-9]{64}$') OR (capture_hash IS NOT NULL AND NOT (capture_hash ~ '^[a-f0-9]{64}$'))
       OR (kind='reservation' AND capture_hash IS NOT NULL) THEN RAISE EXCEPTION 'dcap_lookup_shape'; END IF;
    SELECT * INTO original FROM dcap.packets WHERE scope_wire=s
       AND target=CASE WHEN kind='reservation' THEN reservation_id ELSE capture_id END;
    IF NOT FOUND THEN RETURN jsonb_build_object('resolution','observed_absent_unknown'); END IF;
    IF original.reservation_sha256 IS DISTINCT FROM reservation_hash OR
       (original.capture_sha256 IS NOT NULL AND capture_hash IS NOT NULL AND original.capture_sha256<>capture_hash) THEN
        RAISE EXCEPTION 'dcap_lookup_conflict'; END IF;
    IF kind='capture' AND original.capture_wire IS NULL THEN RETURN jsonb_build_object('resolution','observed_absent_unknown'); END IF;
    RETURN jsonb_build_object('resolution','original_committed','reservation_wire',original.reservation_wire,
        'prepared_wire',original.prepared_wire,'reservation_receipt_wire',original.reservation_receipt_wire,
        'capture_wire',CASE WHEN kind='capture' THEN original.capture_wire END,
        'capture_receipt_wire',CASE WHEN kind='capture' THEN original.capture_receipt_wire END);
END $$;
GRANT USAGE ON SCHEMA dcap TO dcap_recorder,dcap_reader,dcap_foreign;
GRANT EXECUTE ON FUNCTION dcap.reserve(text,text,text,uuid,uuid),dcap.capture(text,uuid,text) TO dcap_recorder;
GRANT EXECUTE ON FUNCTION dcap.get_original(text,text,uuid,text,text) TO dcap_reader,dcap_foreign;
COMMIT;
