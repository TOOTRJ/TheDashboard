-- B2 finite installation/getter/Stop research candidate; no native/hosted authority.
-- policy-sha256: e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0
-- Owned-fixture source review required; never a hosted migration.

-- TABLE vn_jupiter_b2_fixture_anchor.package_inputs
CREATE TABLE vn_jupiter_b2_fixture_anchor.package_inputs (
  scope_wire text PRIMARY KEY,
  installation_id text NOT NULL,
  package_wire text NOT NULL,
  actor_manifest_wire text NOT NULL,
  genesis_wire text NOT NULL,
  expected_catalog_sha256 text NOT NULL CHECK (expected_catalog_sha256 ~ '^[0-9a-f]{64}$'),
  retirement_wire text CHECK (pg_catalog.octet_length(retirement_wire)<=4096)
);

-- TABLE vn_jupiter_b2_fixture_anchor.actor_bindings
CREATE TABLE vn_jupiter_b2_fixture_anchor.actor_bindings (
  binding_id text PRIMARY KEY,
  scope_wire text NOT NULL REFERENCES vn_jupiter_b2_fixture_anchor.package_inputs(scope_wire),
  session_oid oid NOT NULL,
  session_name text NOT NULL,
  capabilities text[] NOT NULL CHECK (pg_catalog.array_position(capabilities,NULL) IS NULL AND pg_catalog.cardinality(capabilities) BETWEEN 1 AND 3),
  binding_wire text NOT NULL,
  UNIQUE(session_oid,session_name)
);

-- TABLE vn_jupiter_b2_allocation_research_v3.scope_state
CREATE TABLE vn_jupiter_b2_allocation_research_v3.scope_state (
  scope_wire text PRIMARY KEY,
  head_wire text NOT NULL,
  accounting_wire text NOT NULL
);

-- TABLE vn_jupiter_b2_allocation_research_v3.original_operations
CREATE TABLE vn_jupiter_b2_allocation_research_v3.original_operations (
  action_id text PRIMARY KEY,
  scope_wire text NOT NULL REFERENCES vn_jupiter_b2_allocation_research_v3.scope_state(scope_wire),
  action_kind text NOT NULL CHECK (action_kind IN ('installation','fence_acquire','source_resume','fence_renew','source_stop','packet_reservation','capture_retention')),
  native_sequence bigint NOT NULL CHECK (native_sequence BETWEEN 1 AND 16),
  command_wire text NOT NULL,
  command_sha256 text NOT NULL,
  result_wire text NOT NULL,
  result_sha256 text NOT NULL,
  receipt_wire text,
  receipt_sha256 text,
  writer_xid8 xid8 NOT NULL UNIQUE,
  writer_binding_id text NOT NULL,
  final_function_observation jsonb NOT NULL,
  finalized boolean NOT NULL DEFAULT false,
  UNIQUE(scope_wire,native_sequence),
  CHECK ((finalized AND receipt_wire IS NOT NULL AND receipt_sha256 IS NOT NULL)
    OR (NOT finalized AND receipt_wire IS NULL AND receipt_sha256 IS NULL))
);

-- TABLE vn_jupiter_b2_allocation_research_v3.journal_entries
CREATE TABLE vn_jupiter_b2_allocation_research_v3.journal_entries (
  scope_wire text NOT NULL,
  native_sequence bigint NOT NULL,
  action_id text NOT NULL UNIQUE REFERENCES vn_jupiter_b2_allocation_research_v3.original_operations(action_id),
  journal_wire text NOT NULL,
  journal_sha256 text NOT NULL,
  PRIMARY KEY(scope_wire,native_sequence)
);

-- TABLE vn_jupiter_b2_allocation_research_v3.identities
CREATE TABLE vn_jupiter_b2_allocation_research_v3.identities (
  original_id text PRIMARY KEY,
  scope_wire text NOT NULL,
  record_wire text NOT NULL,
  UNIQUE(scope_wire,original_id)
);

-- TABLE vn_jupiter_b2_allocation_research_v3.domain_facts
CREATE TABLE vn_jupiter_b2_allocation_research_v3.domain_facts (
  semantic_kind text NOT NULL CHECK (semantic_kind IN ('native_genesis_input','native_terminal_allocation','native_epoch_registration','native_fence_record')),
  original_id text NOT NULL REFERENCES vn_jupiter_b2_allocation_research_v3.identities(original_id),
  wire_sha256 text NOT NULL,
  scope_wire text NOT NULL,
  native_sequence bigint NOT NULL,
  original_wire text NOT NULL,
  PRIMARY KEY(semantic_kind,original_id,wire_sha256),
  UNIQUE(scope_wire,native_sequence,semantic_kind,original_id,wire_sha256)
);

-- TABLE vn_jupiter_b2_allocation_research_v3.dependency_associations
CREATE TABLE vn_jupiter_b2_allocation_research_v3.dependency_associations (
  action_id text NOT NULL,
  scope_wire text NOT NULL,
  ordinal bigint NOT NULL CHECK (ordinal BETWEEN 1 AND 7),
  semantic_kind text NOT NULL,
  original_id text NOT NULL,
  wire_sha256 text NOT NULL,
  wire_bytes bigint NOT NULL,
  PRIMARY KEY(action_id,semantic_kind,original_id,wire_sha256),
  UNIQUE(semantic_kind,original_id,wire_sha256,action_id)
);

-- ANCHOR FUNCTION _lock_inputs
CREATE FUNCTION vn_jupiter_b2_fixture_anchor._lock_inputs(requested_scope pg_catalog.text, lock_resume_recorder pg_catalog.bool)
RETURNS pg_catalog.void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE held_genesis text; recorder_binding_id text;
BEGIN
 IF requested_scope IS NULL OR lock_resume_recorder IS NULL OR pg_catalog.octet_length(requested_scope)>2048 THEN RAISE EXCEPTION 'b2_actor_scope_refused'; END IF;
 SELECT p.genesis_wire INTO held_genesis FROM vn_jupiter_b2_fixture_anchor.package_inputs p WHERE p.scope_wire=requested_scope FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_actor_scope_refused'; END IF;
 PERFORM 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings a WHERE a.scope_wire=requested_scope AND a.session_name=session_user AND a.session_oid=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=session_user) FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_actor_scope_refused'; END IF;
 IF lock_resume_recorder THEN
  recorder_binding_id:=held_genesis::jsonb#>>'{initial_acquisition_spec,recorder_principal_binding_id}';
  PERFORM 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings a WHERE a.scope_wire=requested_scope AND a.binding_id=recorder_binding_id FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_actor_scope_refused'; END IF;
 END IF;
END;
$b2$;

-- FUNCTION _c14n
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._c14n(v pg_catalog.jsonb)
RETURNS pg_catalog.text
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE s text;
BEGIN
 IF v IS NULL THEN RAISE EXCEPTION 'b2_invalid_input'; END IF;
 CASE pg_catalog.jsonb_typeof(v)
 WHEN 'object' THEN SELECT '{'||COALESCE(pg_catalog.string_agg(pg_catalog.to_jsonb(e.key)::text||':'||vn_jupiter_b2_allocation_research_v3._c14n(e.value),',' ORDER BY e.key COLLATE "C"),'')||'}' INTO s FROM pg_catalog.jsonb_each(v) e;
 WHEN 'array' THEN SELECT '['||COALESCE(pg_catalog.string_agg(vn_jupiter_b2_allocation_research_v3._c14n(e.value),',' ORDER BY e.ord),'')||']' INTO s FROM pg_catalog.jsonb_array_elements(v) WITH ORDINALITY e(value,ord);
 ELSE s:=v::text;
 END CASE;
 RETURN s;
END;
$b2$;

-- FUNCTION _sha
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._sha(v pg_catalog.text)
RETURNS pg_catalog.text
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
BEGIN
 IF v IS NULL THEN RAISE EXCEPTION 'b2_invalid_input'; END IF;
 RETURN pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v,'UTF8')),'hex');
END;
$b2$;

-- FUNCTION _keys
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._keys(v pg_catalog.jsonb, names pg_catalog.text[])
RETURNS pg_catalog.bool
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE got text[]; wanted text[];
BEGIN
 IF v IS NULL OR pg_catalog.jsonb_typeof(v)<>'object' THEN RETURN false; END IF;
 SELECT pg_catalog.array_agg(key ORDER BY key COLLATE "C") INTO got FROM pg_catalog.jsonb_object_keys(v) key;
 SELECT pg_catalog.array_agg(x ORDER BY x COLLATE "C") INTO wanted FROM pg_catalog.unnest(names) x;
 RETURN got IS NOT DISTINCT FROM wanted;
END;
$b2$;

-- FUNCTION _scope
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._scope(v pg_catalog.jsonb)
RETURNS pg_catalog.text
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE x text;
BEGIN
 IF NOT vn_jupiter_b2_allocation_research_v3._keys(v,ARRAY['owner_id','run_id','market_epoch']) THEN RAISE EXCEPTION 'b2_invalid_scope'; END IF;
 FOREACH x IN ARRAY ARRAY['owner_id','run_id','market_epoch'] LOOP
  IF pg_catalog.jsonb_typeof(v->x) IS DISTINCT FROM 'string' OR (v->>x ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true THEN RAISE EXCEPTION 'b2_invalid_scope'; END IF;
 END LOOP;
 RETURN vn_jupiter_b2_allocation_research_v3._c14n(v);
END;
$b2$;

-- FUNCTION _pin
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._pin(kind pg_catalog.text, id pg_catalog.text, body pg_catalog.text)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
BEGIN
 IF kind IS NULL OR id IS NULL OR body IS NULL THEN RAISE EXCEPTION 'b2_invalid_pin'; END IF;
 RETURN pg_catalog.jsonb_build_object('semantic_kind',kind,'original_id',id,'original_wire',body,'wire_sha256',vn_jupiter_b2_allocation_research_v3._sha(body),'wire_bytes',pg_catalog.octet_length(body)::text);
END;
$b2$;

-- FUNCTION _clock
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._clock()
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE us text;
BEGIN
 us:=pg_catalog.floor(EXTRACT(epoch FROM pg_catalog.clock_timestamp())*1000000)::bigint::text;
 RETURN pg_catalog.jsonb_build_object('observed_at_us',us,'wall_lower_us',us,'wall_upper_us',us);
END;
$b2$;

-- FUNCTION _catalog
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._catalog()
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE answer jsonb;
BEGIN
 -- Immutable reference data itself is deliberately not a self-hash preimage.
 -- Every definition/owner/ACL/type/index/constraint/trigger in both namespaces
 -- is retained; unknown roots/children change this complete scoped inventory.
 WITH namespaces AS(SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')),
 role_pins AS(
  SELECT session_oid AS oid FROM vn_jupiter_b2_fixture_anchor.actor_bindings
  UNION
  SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN('vn_jupiter_b2_sealed_owner','vn_jupiter_b2_anchor_owner','vn_jupiter_b2_actor_issuer')
 ),
 rels AS(SELECT oid FROM pg_catalog.pg_class WHERE relnamespace IN(SELECT oid FROM namespaces) UNION SELECT reltoastrelid FROM pg_catalog.pg_class WHERE relnamespace IN(SELECT oid FROM namespaces) AND reltoastrelid<>0 UNION SELECT indexrelid FROM pg_catalog.pg_index WHERE indrelid IN(SELECT reltoastrelid FROM pg_catalog.pg_class WHERE relnamespace IN(SELECT oid FROM namespaces) AND reltoastrelid<>0)),
 objects AS(SELECT 'pg_catalog.pg_namespace'::regclass::oid classid,oid objid FROM namespaces UNION SELECT 'pg_catalog.pg_class'::regclass::oid,oid FROM rels UNION SELECT 'pg_catalog.pg_type'::regclass::oid,oid FROM pg_catalog.pg_type WHERE typnamespace IN(SELECT oid FROM namespaces) UNION SELECT 'pg_catalog.pg_proc'::regclass::oid,oid FROM pg_catalog.pg_proc WHERE pronamespace IN(SELECT oid FROM namespaces) UNION SELECT 'pg_catalog.pg_constraint'::regclass::oid,oid FROM pg_catalog.pg_constraint WHERE connamespace IN(SELECT oid FROM namespaces) UNION SELECT 'pg_catalog.pg_attrdef'::regclass::oid,oid FROM pg_catalog.pg_attrdef WHERE adrelid IN(SELECT oid FROM rels) UNION SELECT 'pg_catalog.pg_trigger'::regclass::oid,oid FROM pg_catalog.pg_trigger WHERE tgrelid IN(SELECT oid FROM rels))
 SELECT pg_catalog.jsonb_build_object(
  'dependencies',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(d) ORDER BY d.classid,d.objid,d.objsubid,d.refclassid,d.refobjid,d.refobjsubid,d.deptype),'[]'::jsonb) FROM pg_catalog.pg_depend d WHERE EXISTS(SELECT 1 FROM objects o WHERE (o.classid=d.classid AND o.objid=d.objid) OR (o.classid=d.refclassid AND o.objid=d.refobjid))),
  'shared_dependencies',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(d) ORDER BY d.dbid,d.classid,d.objid,d.objsubid,d.refclassid,d.refobjid,d.deptype),'[]'::jsonb) FROM pg_catalog.pg_shdepend d WHERE d.dbid=(SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()) AND EXISTS(SELECT 1 FROM objects o WHERE o.classid=d.classid AND o.objid=d.objid)),
  'default_acl',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(d) ORDER BY d.oid),'[]'::jsonb) FROM pg_catalog.pg_default_acl d),
  'database_identity',(SELECT pg_catalog.jsonb_build_object('oid',oid::text,'name',datname::text,'encoding',encoding) FROM pg_catalog.pg_database WHERE datname=current_database()),
  'server_version_num',pg_catalog.current_setting('server_version_num'),
  'schemas',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('name',n.nspname::text,'oid',n.oid::text,'owner',n.nspowner::text,'acl',pg_catalog.to_jsonb(n.nspacl)) ORDER BY n.nspname COLLATE "C"),'[]'::jsonb) FROM pg_catalog.pg_namespace n WHERE n.nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')),
  'relations',(SELECT COALESCE(pg_catalog.jsonb_agg((pg_catalog.to_jsonb(c)-ARRAY['relpages','reltuples','relallvisible','relallfrozen','relfrozenxid','relminmxid']) ORDER BY c.oid),'[]'::jsonb) FROM pg_catalog.pg_class c WHERE c.relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')) OR c.oid IN (SELECT i.indexrelid FROM pg_catalog.pg_index i WHERE i.indrelid IN (SELECT reltoastrelid FROM pg_catalog.pg_class WHERE relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')))) OR c.oid IN (SELECT reltoastrelid FROM pg_catalog.pg_class WHERE relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')))),
  'attributes',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(a) ORDER BY a.attrelid,a.attnum),'[]'::jsonb) FROM pg_catalog.pg_attribute a WHERE a.attrelid IN(SELECT oid FROM rels)),
  'defaults',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(a) ORDER BY a.oid),'[]'::jsonb) FROM pg_catalog.pg_attrdef a WHERE a.adrelid IN (SELECT oid FROM pg_catalog.pg_class WHERE relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')) UNION SELECT reltoastrelid FROM pg_catalog.pg_class WHERE relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')) AND reltoastrelid<>0 UNION SELECT i.indexrelid FROM pg_catalog.pg_index i WHERE i.indrelid IN (SELECT reltoastrelid FROM pg_catalog.pg_class WHERE relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')) AND reltoastrelid<>0))),
  'constraints',(SELECT COALESCE(pg_catalog.jsonb_agg((pg_catalog.to_jsonb(c)-ARRAY['relpages','reltuples','relallvisible','relallfrozen','relfrozenxid','relminmxid']) ORDER BY c.oid),'[]'::jsonb) FROM pg_catalog.pg_constraint c WHERE c.connamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3'))),
  'indexes',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(i) ORDER BY i.indexrelid),'[]'::jsonb) FROM pg_catalog.pg_index i WHERE i.indrelid IN (SELECT oid FROM pg_catalog.pg_class WHERE relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')) UNION SELECT reltoastrelid FROM pg_catalog.pg_class WHERE relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')) AND reltoastrelid<>0 UNION SELECT i.indexrelid FROM pg_catalog.pg_index i WHERE i.indrelid IN (SELECT reltoastrelid FROM pg_catalog.pg_class WHERE relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')) AND reltoastrelid<>0))),
  'types',(SELECT COALESCE(pg_catalog.jsonb_agg((pg_catalog.to_jsonb(t)||pg_catalog.jsonb_build_object('typinput',t.typinput::oid::text,'typoutput',t.typoutput::oid::text,'typreceive',t.typreceive::oid::text,'typsend',t.typsend::oid::text,'typanalyze',t.typanalyze::oid::text,'typsubscript',t.typsubscript::oid::text)) ORDER BY t.oid),'[]'::jsonb) FROM pg_catalog.pg_type t WHERE t.typnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3'))),
  'functions',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(p) ORDER BY p.oid),'[]'::jsonb) FROM pg_catalog.pg_proc p WHERE p.pronamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3'))),
  'triggers',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(t) ORDER BY t.oid),'[]'::jsonb) FROM pg_catalog.pg_trigger t WHERE t.tgrelid IN (SELECT oid FROM pg_catalog.pg_class WHERE relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')) UNION SELECT reltoastrelid FROM pg_catalog.pg_class WHERE relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')) AND reltoastrelid<>0 UNION SELECT i.indexrelid FROM pg_catalog.pg_index i WHERE i.indrelid IN (SELECT reltoastrelid FROM pg_catalog.pg_class WHERE relnamespace IN (SELECT oid FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_allocation_research_v3')) AND reltoastrelid<>0))),
  'roles',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('oid',r.oid::text,'name',r.rolname::text,'super',r.rolsuper,'inherit',r.rolinherit,'create_role',r.rolcreaterole,'create_db',r.rolcreatedb,'login',r.rolcanlogin,'connection_limit',r.rolconnlimit,'replication',r.rolreplication,'bypass',r.rolbypassrls,'valid_until',r.rolvaliduntil::text,'config',pg_catalog.to_jsonb(r.rolconfig)) ORDER BY r.oid),'[]'::jsonb) FROM pg_catalog.pg_roles r WHERE r.oid IN (SELECT oid FROM role_pins)
    OR (r.oid=10 AND EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vn_jupiter_b2_actor_issuer'))),
  'memberships',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(m) ORDER BY m.oid),'[]'::jsonb) FROM pg_catalog.pg_auth_members m WHERE m.member IN (SELECT oid FROM role_pins) OR m.roleid IN (SELECT oid FROM role_pins)),
  'parameter_acl',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(a) ORDER BY a.oid),'[]'::jsonb) FROM pg_catalog.pg_parameter_acl a),
  'extensions',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(e) ORDER BY e.oid),'[]'::jsonb) FROM pg_catalog.pg_extension e),
  'event_triggers',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.to_jsonb(e) ORDER BY e.oid),'[]'::jsonb) FROM pg_catalog.pg_event_trigger e)
 ) INTO answer;
 IF pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(answer))>1048576 THEN RAISE EXCEPTION 'b2_catalog_bound'; END IF;
 RETURN answer;
END;
$b2$;

-- FUNCTION _check_credential_window
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._check_credential_window(windows pg_catalog.jsonb, observed_us pg_catalog.int8)
RETURNS pg_catalog.void
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE entry jsonb;
BEGIN
 -- Only held callers supply these contexts, from the same authorized snapshot.
 IF windows IS NULL THEN RETURN; END IF;
 FOR entry IN SELECT value FROM pg_catalog.jsonb_array_elements(windows) LOOP
  IF observed_us>=(entry->>'login_until_us')::bigint
  THEN RAISE EXCEPTION 'b2_credential_expired' USING ERRCODE='42501'; END IF;
  IF observed_us<(entry->>'not_before_us')::bigint
  THEN RAISE EXCEPTION 'b2_credential_not_yet_valid' USING ERRCODE='42501'; END IF;
  IF observed_us>=(entry->>'cutoff_us')::bigint THEN
   IF (entry->>'independent_reader')::boolean
   THEN RAISE EXCEPTION 'b2_recovery_window_closed' USING ERRCODE='42501'; END IF;
   RAISE EXCEPTION 'b2_write_window_closed' USING ERRCODE='42501';
  END IF;
 END LOOP;
END;
$b2$;

-- FUNCTION _auth
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._auth(scope pg_catalog.jsonb, capability pg_catalog.text, retired_writer_binding_id pg_catalog.text, terminal_stop_sha pg_catalog.text, terminal_read_sha pg_catalog.text)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE sw text; p vn_jupiter_b2_fixture_anchor.package_inputs%ROWTYPE; a vn_jupiter_b2_fixture_anchor.actor_bindings%ROWTYPE; binding vn_jupiter_b2_fixture_anchor.actor_bindings%ROWTYPE; recorder_id text; rr record; manifest jsonb; pkg jsonb; k text; v jsonb; catalog jsonb; retired vn_jupiter_b2_fixture_anchor.actor_bindings%ROWTYPE; role_index bigint; marker jsonb; writer_profile record; retired_writers jsonb:='[]'; creator_oid oid; creator_grantor_oid oid; scram_profile boolean;
 deadline_profile boolean; getter_precheck boolean:=capability='get_original_precheck';
 getter_context boolean:=capability IN('get_original','get_original_precheck'); independent_reader boolean;
 actor_entry jsonb; actor_entries jsonb; windows jsonb; field text;
 handoff_profile boolean; handoff jsonb; effective_catalog text; issued_us bigint; not_before_us bigint; cutoff_us bigint; login_until_us bigint;
BEGIN
 IF getter_context THEN capability:='read_original'; END IF;
 sw:=vn_jupiter_b2_allocation_research_v3._scope(scope);
 SELECT * INTO p FROM vn_jupiter_b2_fixture_anchor.package_inputs WHERE scope_wire=sw;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_actor_scope_refused'; END IF;
 -- The two existing profiles still receive their full target-aware check
 -- below the getter's original lookup. Only the new profile has a separate
 -- application deadline to enforce before that lookup.
 IF getter_precheck AND p.package_wire::jsonb->>'format' IN(
   'ga-jupiter-b2-fixture-package-input-research-v3-v1',
   'ga-jupiter-b2-fixture-direct-scram-research-v3-v1') THEN RETURN NULL; END IF;
 SELECT * INTO a FROM vn_jupiter_b2_fixture_anchor.actor_bindings WHERE scope_wire=sw AND session_name=session_user AND session_oid=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=session_user);
 IF NOT FOUND OR ((CASE WHEN capability='resume_scope' THEN 'control' ELSE capability END)=ANY(a.capabilities)) IS DISTINCT FROM true THEN RAISE EXCEPTION 'b2_actor_scope_refused'; END IF;
 pkg:=p.package_wire::jsonb;
 IF NOT vn_jupiter_b2_allocation_research_v3._keys(pkg,ARRAY['format','native_policy_sha256','installation_id','policies','catalog_manifest_sha256','actor_manifest_sha256','native_package_sha256']) OR (pkg->>'format' IS DISTINCT FROM 'ga-jupiter-b2-fixture-package-input-research-v3-v1' AND pkg->>'format' IS DISTINCT FROM 'ga-jupiter-b2-fixture-direct-scram-research-v3-v1' AND pkg->>'format' IS DISTINCT FROM 'ga-jupiter-b2-fixture-direct-scram-deadlines-research-v3-v1' AND pkg->>'format' IS DISTINCT FROM 'ga-jupiter-b2-fixture-direct-scram-handoff-research-v3-v1') OR pg_catalog.jsonb_typeof(pkg->'installation_id') IS DISTINCT FROM 'string' OR pkg->>'installation_id' IS DISTINCT FROM p.installation_id OR (p.installation_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true OR vn_jupiter_b2_allocation_research_v3._c14n(pkg) IS DISTINCT FROM p.package_wire OR pg_catalog.octet_length(p.package_wire)+pg_catalog.octet_length(p.actor_manifest_wire)+pg_catalog.octet_length(p.genesis_wire)>131072 OR pg_catalog.octet_length(p.genesis_wire)>8192 THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
 handoff_profile:=pkg->>'format'='ga-jupiter-b2-fixture-direct-scram-handoff-research-v3-v1';
 deadline_profile:=handoff_profile OR pkg->>'format'='ga-jupiter-b2-fixture-direct-scram-deadlines-research-v3-v1';
 scram_profile:=deadline_profile OR pkg->>'format'='ga-jupiter-b2-fixture-direct-scram-research-v3-v1';
 IF scram_profile AND (system_user IS DISTINCT FROM ('scram-sha-256:'||session_user::text) OR pg_catalog.inet_client_addr() IS NULL)
 THEN RAISE EXCEPTION 'b2_direct_scram_required' USING ERRCODE='42501'; END IF;
 FOREACH k IN ARRAY ARRAY['native_policy_sha256','catalog_manifest_sha256','actor_manifest_sha256','native_package_sha256'] LOOP
  IF pg_catalog.jsonb_typeof(pkg->k) IS DISTINCT FROM 'string' OR (pkg->>k ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
 END LOOP;
 IF NOT vn_jupiter_b2_allocation_research_v3._keys(pkg->'policies',ARRAY['acquisition_sha256','source_sha256','transport_sha256','a1_schema_sha256','raw_parser_sha256','recorder_package_sha256','reader_package_sha256','native_package_sha256']) THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
 FOR k,v IN SELECT key,value FROM pg_catalog.jsonb_each(pkg->'policies') LOOP
  IF pg_catalog.jsonb_typeof(v) IS DISTINCT FROM 'string' OR (v#>>'{}' ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
 END LOOP;
 IF pkg#>>'{policies,native_package_sha256}' IS DISTINCT FROM pkg->>'native_package_sha256' OR pkg->>'catalog_manifest_sha256' IS DISTINCT FROM p.expected_catalog_sha256 OR pkg->>'actor_manifest_sha256' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._sha(p.actor_manifest_wire) THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
 manifest:=p.actor_manifest_wire::jsonb;
 IF NOT vn_jupiter_b2_allocation_research_v3._keys(manifest,ARRAY['format','native_policy_sha256','scope','installation_id','bindings']) OR manifest->>'format' IS DISTINCT FROM (CASE WHEN deadline_profile THEN 'ga-jupiter-b2-capability-manifest-deadlines-research-v3-v1' ELSE 'ga-jupiter-b2-capability-manifest-research-v3-v1' END) OR manifest->>'native_policy_sha256' IS DISTINCT FROM pkg->>'native_policy_sha256' OR manifest->'scope' IS DISTINCT FROM scope OR manifest->>'installation_id' IS DISTINCT FROM p.installation_id OR pg_catalog.jsonb_typeof(manifest->'bindings') IS DISTINCT FROM 'array' OR pg_catalog.jsonb_array_length(manifest->'bindings')<>4 OR vn_jupiter_b2_allocation_research_v3._c14n(manifest) IS DISTINCT FROM p.actor_manifest_wire THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
 IF deadline_profile AND (SELECT count(DISTINCT e->>'issuance_id')=4
   AND count(DISTINCT e->>'principal_binding_id')=4
   AND pg_catalog.bool_and(pg_catalog.jsonb_typeof(e->'issuance_id')='string'
    AND (e->>'issuance_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS TRUE
    AND e->'credential_generation' IS NOT DISTINCT FROM '"1"'::jsonb)
   FROM pg_catalog.jsonb_array_elements(manifest->'bindings') e) IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
 actor_entries:=manifest->'bindings';
 effective_catalog:=p.expected_catalog_sha256;
 IF handoff_profile THEN
  IF p.retirement_wire IS NOT NULL THEN RAISE EXCEPTION 'b2_handoff_scope_refused'; END IF;
  handoff:=vn_jupiter_b2_allocation_research_v3._read_handoff(sw);
  IF handoff IS NOT NULL THEN
   effective_catalog:=handoff->>'catalog_sha256';
   actor_entries:=actor_entries||pg_catalog.jsonb_build_array(handoff->'successor_binding');
  END IF;
 END IF;
 IF deadline_profile THEN windows:='[]'::jsonb; END IF;
 -- Resume needs both the actual control principal and the installed recorder.
 -- The caller has already taken package, caller and recorder row locks.
 IF capability='resume_scope' THEN
  recorder_id:=p.genesis_wire::jsonb#>>'{initial_acquisition_spec,recorder_principal_binding_id}';
  IF a.capabilities IS DISTINCT FROM ARRAY['control','read_original']::text[] OR recorder_id IS NOT DISTINCT FROM a.binding_id OR NOT EXISTS(
   SELECT 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings z WHERE z.scope_wire=sw AND z.binding_id=recorder_id
   AND z.capabilities=ARRAY['reserve','fence_manage','read_original']::text[]
  ) THEN RAISE EXCEPTION 'b2_actor_scope_refused'; END IF;
 END IF;
 -- The fixture may use the one literal PG17 limited-issuer profile. Its
 -- creator and bootstrap identities are independently checked and sealed in K.
 SELECT oid INTO creator_oid FROM pg_catalog.pg_roles WHERE rolname='vn_jupiter_b2_actor_issuer';
 IF scram_profile AND creator_oid IS NULL THEN RAISE EXCEPTION 'b2_actor_scope_refused'; END IF;
 IF creator_oid IS NOT NULL THEN
  SELECT oid INTO creator_grantor_oid FROM pg_catalog.pg_roles WHERE oid=10 AND rolname='postgres' AND rolsuper;
  IF creator_grantor_oid IS NULL OR creator_oid=creator_grantor_oid
   OR pg_catalog.current_setting('server_version_num')::integer NOT BETWEEN 170000 AND 179999
   OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE oid=creator_oid AND rolcanlogin AND rolcreaterole
    AND NOT rolsuper AND NOT rolinherit AND NOT rolcreatedb AND NOT rolreplication AND NOT rolbypassrls)
  THEN RAISE EXCEPTION 'b2_actor_scope_refused'; END IF;
 END IF;
 FOR binding IN SELECT z.* FROM vn_jupiter_b2_fixture_anchor.actor_bindings z
   WHERE z.scope_wire=sw AND (z.binding_id=a.binding_id OR z.binding_id=recorder_id)
 LOOP
  SELECT * INTO rr FROM pg_catalog.pg_roles WHERE oid=binding.session_oid AND rolname=binding.session_name;
  IF NOT FOUND OR rr.rolsuper OR rr.rolinherit OR rr.rolcreaterole OR rr.rolcreatedb OR rr.rolreplication OR rr.rolbypassrls OR NOT rr.rolcanlogin
   OR EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=binding.session_oid)
   OR (SELECT count(*) FROM pg_catalog.pg_auth_members WHERE roleid=binding.session_oid)<>(CASE WHEN creator_oid IS NULL THEN 0 ELSE 1 END)
   OR (creator_oid IS NOT NULL AND NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members
    WHERE roleid=binding.session_oid AND member=creator_oid AND grantor=creator_grantor_oid
     AND admin_option AND NOT inherit_option AND NOT set_option))
  THEN RAISE EXCEPTION 'b2_actor_scope_refused'; END IF;
  IF scram_profile AND NOT deadline_profile AND (rr.rolvaliduntil IS NULL OR NOT pg_catalog.isfinite(rr.rolvaliduntil) OR pg_catalog.clock_timestamp()>=rr.rolvaliduntil)
  THEN RAISE EXCEPTION 'b2_credential_expired' USING ERRCODE='42501'; END IF;
  IF pg_catalog.octet_length(binding.binding_wire)>2048 THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
  SELECT e INTO actor_entry FROM pg_catalog.jsonb_array_elements(actor_entries) e WHERE vn_jupiter_b2_allocation_research_v3._keys(e,ARRAY['principal_binding_id','database_identity_sha256','session_user_oid','session_user_name','scope','capabilities','recorder_package_sha256','reader_package_sha256','issuer_binding_id','endpoint_bindings','installation_id']||
   CASE WHEN deadline_profile THEN ARRAY['issuance_id','credential_generation','issued_at_us','not_before_us','write_until_us','read_until_us','login_until_us']::text[] ELSE ARRAY[]::text[] END) AND e->'database_identity_sha256'=pg_catalog.to_jsonb(vn_jupiter_b2_allocation_research_v3._sha(current_database()||':'||(SELECT oid::text FROM pg_catalog.pg_database WHERE datname=current_database()))) AND e->'recorder_package_sha256'=pkg#>'{policies,recorder_package_sha256}' AND e->'reader_package_sha256'=pkg#>'{policies,reader_package_sha256}' AND e->'issuer_binding_id'=(p.genesis_wire::jsonb)#>'{initial_acquisition_spec,issuer_binding_id}' AND e->'endpoint_bindings'=(p.genesis_wire::jsonb)#>'{initial_acquisition_spec,endpoint_bindings}' AND e->>'installation_id'=p.installation_id AND vn_jupiter_b2_allocation_research_v3._c14n(e)=binding.binding_wire AND e->>'principal_binding_id'=binding.binding_id AND e->>'session_user_oid'=binding.session_oid::text AND e->>'session_user_name'=binding.session_name AND e->'scope'=scope AND e->'capabilities'=pg_catalog.to_jsonb(binding.capabilities);
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_actor_scope_refused'; END IF;
  IF deadline_profile THEN
   independent_reader:=binding.capabilities=ARRAY['register_reader_epoch','read_original']::text[];
   IF independent_reader AND (NOT getter_context OR capability IS DISTINCT FROM 'read_original'
     OR binding.binding_id IS DISTINCT FROM p.genesis_wire::jsonb#>>'{initial_acquisition_spec,reader_principal_binding_id}')
   THEN RAISE EXCEPTION 'b2_actor_scope_refused' USING ERRCODE='42501'; END IF;
   IF actor_entry->(CASE WHEN independent_reader THEN 'write_until_us' ELSE 'read_until_us' END)
      IS DISTINCT FROM 'null'::jsonb
   THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
   FOREACH field IN ARRAY ARRAY['issued_at_us','not_before_us','login_until_us',
     CASE WHEN independent_reader THEN 'read_until_us' ELSE 'write_until_us' END] LOOP
    IF pg_catalog.jsonb_typeof(actor_entry->field) IS DISTINCT FROM 'string'
     OR (actor_entry->>field ~ '^[1-9][0-9]{0,17}$') IS DISTINCT FROM true
    THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
   END LOOP;
   issued_us:=(actor_entry->>'issued_at_us')::bigint;
   not_before_us:=(actor_entry->>'not_before_us')::bigint;
   login_until_us:=(actor_entry->>'login_until_us')::bigint;
   cutoff_us:=(actor_entry->>(CASE WHEN independent_reader THEN 'read_until_us' ELSE 'write_until_us' END))::bigint;
   IF issued_us>not_before_us OR not_before_us>=cutoff_us OR cutoff_us>login_until_us
    OR login_until_us-issued_us>300000000 OR rr.rolvaliduntil IS NULL OR NOT pg_catalog.isfinite(rr.rolvaliduntil)
   THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
   IF pg_catalog.floor(EXTRACT(epoch FROM rr.rolvaliduntil)*1000000)::bigint IS DISTINCT FROM login_until_us
   THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
   windows:=windows||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
    'not_before_us',not_before_us,'cutoff_us',cutoff_us,'login_until_us',login_until_us,
    'independent_reader',independent_reader));
  END IF;
 END LOOP;
 IF p.package_wire::jsonb->>'native_policy_sha256' IS DISTINCT FROM 'e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0' THEN
  RAISE EXCEPTION 'b2_package_refused';
 END IF;
 IF getter_precheck THEN
  IF deadline_profile THEN PERFORM vn_jupiter_b2_allocation_research_v3._check_credential_window(
   windows,(vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint); END IF;
  RETURN NULL;
 END IF;
 catalog:=vn_jupiter_b2_allocation_research_v3._catalog();
 IF handoff_profile THEN
  IF vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(catalog)) IS DISTINCT FROM effective_catalog
  THEN RAISE EXCEPTION 'b2_handoff_catalog_refused'; END IF;
 ELSIF p.retirement_wire IS NOT NULL THEN
  -- A recorded terminal boundary is checked even when raw K happens to match.
  marker:=p.retirement_wire::jsonb;
  IF pg_catalog.octet_length(p.retirement_wire)>4096
   OR vn_jupiter_b2_allocation_research_v3._c14n(marker) IS DISTINCT FROM p.retirement_wire
   OR NOT vn_jupiter_b2_allocation_research_v3._keys(marker,ARRAY['format','scope','native_package_sha256','catalog_manifest_sha256','stop_action_id','stop_command_sha256','writers'])
   OR marker->>'format' IS DISTINCT FROM 'ga-jupiter-b2-terminal-retirement-fixture-v1'
   OR marker->'scope' IS DISTINCT FROM scope
   OR marker->'native_package_sha256' IS DISTINCT FROM pkg->'native_package_sha256'
   OR marker->'catalog_manifest_sha256' IS DISTINCT FROM pkg->'catalog_manifest_sha256'
   OR pg_catalog.jsonb_typeof(marker->'stop_action_id') IS DISTINCT FROM 'string'
   OR marker->>'stop_action_id' IS DISTINCT FROM p.genesis_wire::jsonb#>>'{terminal_stop_action_id}'
   OR pg_catalog.jsonb_typeof(marker->'stop_command_sha256') IS DISTINCT FROM 'string'
   OR (marker->>'stop_command_sha256' ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true
  THEN RAISE EXCEPTION 'b2_retirement_refused'; END IF;

  IF terminal_stop_sha IS NOT NULL THEN
   IF capability NOT IN('read_original','control')
    OR a.capabilities IS DISTINCT FROM ARRAY['control','read_original']::text[]
    OR terminal_stop_sha IS DISTINCT FROM marker->>'stop_command_sha256'
   THEN RAISE EXCEPTION 'b2_retirement_refused'; END IF;
  ELSIF capability IS DISTINCT FROM 'read_original'
   OR a.capabilities IS DISTINCT FROM ARRAY['register_reader_epoch','read_original']::text[]
   OR a.binding_id IS DISTINCT FROM p.genesis_wire::jsonb#>>'{initial_acquisition_spec,reader_principal_binding_id}'
   OR (retired_writer_binding_id IS NULL AND terminal_read_sha IS NULL)
  THEN RAISE EXCEPTION 'b2_retirement_refused'; END IF;

  FOR writer_profile IN SELECT v.* FROM (VALUES
   ('installation',1::bigint,ARRAY['install','register_epoch','read_original']::text[]),
   ('fence_acquire',2::bigint,ARRAY['reserve','fence_manage','read_original']::text[])
  ) AS v(kind,position,capabilities) ORDER BY v.position
  LOOP
   SELECT w.* INTO retired FROM vn_jupiter_b2_allocation_research_v3.original_operations o
    JOIN vn_jupiter_b2_fixture_anchor.actor_bindings w ON w.scope_wire=o.scope_wire AND w.binding_id=o.writer_binding_id
    WHERE o.scope_wire=sw AND o.native_sequence=writer_profile.position AND o.action_kind=writer_profile.kind AND o.finalized;
   IF NOT FOUND OR retired.binding_id IS NOT DISTINCT FROM a.binding_id
    OR retired.capabilities IS DISTINCT FROM writer_profile.capabilities
    OR pg_catalog.octet_length(retired.binding_wire)>2048
    OR (writer_profile.position=2 AND retired.binding_id IS DISTINCT FROM
        p.genesis_wire::jsonb#>>'{initial_acquisition_spec,recorder_principal_binding_id}')
   THEN RAISE EXCEPTION 'b2_retirement_refused'; END IF;
   IF NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(manifest->'bindings') entry
    WHERE entry->>'principal_binding_id'=retired.binding_id
    AND entry->>'session_user_oid'=retired.session_oid::text AND entry->>'session_user_name'=retired.session_name
    AND entry->'scope'=scope AND entry->>'installation_id'=p.installation_id
    AND entry->'capabilities'=pg_catalog.to_jsonb(retired.capabilities)
    AND vn_jupiter_b2_allocation_research_v3._c14n(entry)=retired.binding_wire)
   THEN RAISE EXCEPTION 'b2_retirement_refused'; END IF;
   retired_writers:=retired_writers||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
    'binding_id',retired.binding_id,'role_name',retired.session_name,'role_oid',retired.session_oid::text,
    'binding_sha256',vn_jupiter_b2_allocation_research_v3._sha(retired.binding_wire)));
   SELECT roles.ordinality INTO role_index
    FROM pg_catalog.jsonb_array_elements(catalog->'roles') WITH ORDINALITY AS roles(value,ordinality)
    WHERE roles.value->>'oid'=retired.session_oid::text AND roles.value->>'name'=retired.session_name
    AND roles.value->'login'='false'::jsonb;
   IF NOT FOUND THEN RAISE EXCEPTION 'b2_retirement_refused'; END IF;
   catalog:=pg_catalog.jsonb_set(catalog,ARRAY['roles',(role_index-1)::text,'login'],'true'::jsonb,false);
  END LOOP;
  IF marker->'writers' IS DISTINCT FROM retired_writers
   OR (terminal_stop_sha IS NULL AND terminal_read_sha IS DISTINCT FROM marker->>'stop_command_sha256'
    AND NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(retired_writers) w
     WHERE w->>'binding_id'=retired_writer_binding_id))
   OR vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(catalog)) IS DISTINCT FROM p.expected_catalog_sha256
  THEN RAISE EXCEPTION 'b2_retirement_refused'; END IF;
 ELSIF vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(catalog)) IS DISTINCT FROM p.expected_catalog_sha256 THEN
  -- Only the public getter for this exact original may supply its writer.
  -- The actual caller has already passed live scoped authorization above.
  IF capability IS DISTINCT FROM 'read_original' OR retired_writer_binding_id IS NULL
   OR retired_writer_binding_id IS NOT DISTINCT FROM a.binding_id
   OR a.capabilities IS DISTINCT FROM ARRAY['register_reader_epoch','read_original']::text[]
   OR a.binding_id IS DISTINCT FROM p.genesis_wire::jsonb#>>'{initial_acquisition_spec,reader_principal_binding_id}'
  THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
  SELECT * INTO retired FROM vn_jupiter_b2_fixture_anchor.actor_bindings w
   WHERE w.scope_wire=sw AND w.binding_id=retired_writer_binding_id;
  IF NOT FOUND OR pg_catalog.octet_length(retired.binding_wire)>2048
   OR (retired.capabilities IN (ARRAY['install','register_epoch','read_original']::text[],
      ARRAY['reserve','fence_manage','read_original']::text[],ARRAY['control','read_original']::text[])) IS DISTINCT FROM true
  THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(manifest->'bindings') entry
   WHERE entry->>'principal_binding_id'=retired.binding_id
   AND entry->>'session_user_oid'=retired.session_oid::text AND entry->>'session_user_name'=retired.session_name
   AND entry->'scope'=scope AND entry->>'installation_id'=p.installation_id
   AND entry->'capabilities'=pg_catalog.to_jsonb(retired.capabilities)
   AND vn_jupiter_b2_allocation_research_v3._c14n(entry)=retired.binding_wire)
  THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
  SELECT roles.ordinality INTO role_index
   FROM pg_catalog.jsonb_array_elements(catalog->'roles') WITH ORDINALITY AS roles(value,ordinality)
   WHERE roles.value->>'oid'=retired.session_oid::text AND roles.value->>'name'=retired.session_name
   AND roles.value->'login'='false'::jsonb;
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_package_refused'; END IF;

  -- Test the one permitted historical preimage against the original held
  -- digest. Every other value, including valid_until and ACLs, stays exact.
  catalog:=pg_catalog.jsonb_set(catalog,ARRAY['roles',(role_index-1)::text,'login'],'true'::jsonb,false);
  IF vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(catalog)) IS DISTINCT FROM p.expected_catalog_sha256 THEN
   RAISE EXCEPTION 'b2_package_refused';
  END IF;
 END IF;
 IF pg_catalog.current_setting('transaction_isolation')<>'read committed' OR pg_catalog.current_setting('TimeZone')<>'UTC' OR pg_catalog.current_setting('session_replication_role')<>'origin' OR pg_catalog.pg_is_in_recovery() OR pg_catalog.pg_my_temp_schema()<>0 THEN RAISE EXCEPTION 'b2_session_refused'; END IF;
 IF deadline_profile THEN PERFORM vn_jupiter_b2_allocation_research_v3._check_credential_window(windows,(vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint); END IF;
 RETURN pg_catalog.jsonb_build_object('handoff_profile',handoff_profile,'handoff',handoff,
  'effective_catalog_sha256',effective_catalog,'credential_windows',windows,'binding_id',a.binding_id,'package',p.package_wire::jsonb,'genesis_wire',p.genesis_wire,'actor_manifest_wire',p.actor_manifest_wire,'terminal_retirement',p.retirement_wire IS NOT NULL);
END;
$b2$;

-- FUNCTION _limits
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._limits()
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
BEGIN RETURN '{"provider_attested":false,"calibrated_clock":false,"hosted_authority":false,"running_authority":false,"live_trading_authority":false,"model_native_join":false}'::jsonb; END;
$b2$;

-- FUNCTION _deps
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._deps(v pg_catalog.jsonb)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE answer jsonb;
BEGIN
 IF pg_catalog.jsonb_typeof(v)<>'array' OR pg_catalog.jsonb_array_length(v)>7 THEN RAISE EXCEPTION 'b2_dependency_refused'; END IF;
 SELECT COALESCE(pg_catalog.jsonb_agg(e ORDER BY e->>'semantic_kind' COLLATE "C",e->>'original_id' COLLATE "C",e->>'wire_sha256' COLLATE "C"),'[]'::jsonb) INTO answer FROM (SELECT DISTINCT value e FROM pg_catalog.jsonb_array_elements(v)) q;
 RETURN answer;
END;
$b2$;

-- FUNCTION _cost
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._cost(c pg_catalog.jsonb, r pg_catalog.jsonb, ids pg_catalog.jsonb, facts pg_catalog.jsonb)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE sw text:=vn_jupiter_b2_allocation_research_v3._scope(c->'scope'); scope jsonb:=c->'scope';
 cw text:=vn_jupiter_b2_allocation_research_v3._c14n(c); rw text:=vn_jupiter_b2_allocation_research_v3._c14n(r);
 h text:=pg_catalog.repeat('f',64); utc jsonb; rec jsonb; jr jsonb; sh jsonb; ac jsonb;
 om jsonb; jm jsonb; sm jsonb; row jsonb; v jsonb; d jsonb; seq text:=r->>'native_sequence';
 nb bigint:=0; kb bigint:=0; dc bigint:=pg_catalog.jsonb_array_length(r->'dependencies');
 ni bigint:=pg_catalog.jsonb_array_length(ids); nf bigint:=pg_catalog.jsonb_array_length(facts);
 tw text; jw text; hw text; aw text; stage bigint; keybytes bigint; ordinal bigint:=0;
BEGIN
 -- Every future clock/resource width is bounded before the first staging DML.
 utc:=pg_catalog.jsonb_build_object('observed_at_us',pg_catalog.repeat('9',19),'wall_lower_us',pg_catalog.repeat('9',19),'wall_upper_us',pg_catalog.repeat('9',19));
 rec:=pg_catalog.jsonb_build_object('format','ga-jupiter-b2-allocation-receipt-research-v3-v1','native_policy_sha256',c->>'native_policy_sha256','scope',scope,'action_id',c->>'action_id','action_kind',c->>'action_kind','original_command_sha256',h,'result_sha256',h,'native_sequence',seq,'previous_native_head_sha256',h,'admission_observation',NULL,'final_function_observation',utc,'commit_processing_observation',utc,'native_package_sha256',h,'catalog_manifest_sha256',h,'limits',vn_jupiter_b2_allocation_research_v3._limits());
 tw:=vn_jupiter_b2_allocation_research_v3._c14n(rec);
 jr:=pg_catalog.jsonb_build_object('native_sequence',seq,'action_id',c->>'action_id','action_kind',c->>'action_kind','original_command_sha256',h,'original_result_sha256',h,'original_receipt_sha256',h,'previous_native_head_sha256',h); jw:=vn_jupiter_b2_allocation_research_v3._c14n(jr);
 sh:=pg_catalog.jsonb_build_object('scope',scope,'native_sequence','16','native_head_sha256',h,'active_acquisition_epoch','ffffffff-ffff-ffff-ffff-ffffffffffff','active_fence_id',CASE WHEN c->>'action_kind' IN('fence_acquire','source_resume','fence_renew','packet_reservation','capture_retention') THEN 'ffffffff-ffff-ffff-ffff-ffffffffffff' ELSE NULL END,'fence_revision','16','source_mode','stopped','last_admission_sha256',NULL,'last_ingest_sequence','0','last_availability_sha256',NULL,'previous_seal_sha256',NULL); hw:=vn_jupiter_b2_allocation_research_v3._c14n(sh);
 ac:='{"committed_positions":"16","logical_UTF8_bytes":"4194304","identity_rows":"96","domain_rows":"25","dependency_rows":"112","retained_rows":"271","row_writes":"512","index_entries":"1024","Stop_reserve_consumed":false}'::jsonb; aw:=vn_jupiter_b2_allocation_research_v3._c14n(ac);
 om:=pg_catalog.jsonb_build_object('scope',scope,'action_id',c->>'action_id','action_kind',c->>'action_kind','native_sequence',seq,'command_sha256',h,'result_sha256',h,'receipt_sha256',h,'command_bytes',pg_catalog.octet_length(cw)::text,'result_bytes',pg_catalog.octet_length(rw)::text,'receipt_bytes',pg_catalog.octet_length(tw)::text,'writer_xid8','18446744073709551615','writer_principal_binding_id','ffffffff-ffff-ffff-ffff-ffffffffffff','finalized',true,'final_function_observation',utc);
 jm:=pg_catalog.jsonb_build_object('scope',scope,'action_id',c->>'action_id','native_sequence',seq,'journal_sha256',h,'journal_bytes',pg_catalog.octet_length(jw)::text);
 sm:=pg_catalog.jsonb_build_object('scope',scope,'head_sha256',h,'head_bytes',pg_catalog.octet_length(hw)::text,'accounting_bytes',pg_catalog.octet_length(aw)::text);
 keybytes:=pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(c->>'action_id')))+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(scope,seq)))+pg_catalog.octet_length('["18446744073709551615"]');
 stage:=pg_catalog.octet_length(cw)+pg_catalog.octet_length(rw)+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(om||'{"receipt_sha256":null,"receipt_bytes":"0","finalized":false}'::jsonb))+keybytes;
 kb:=keybytes+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(scope,seq)))+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(c->>'action_id')))+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(scope)));
 nb:=pg_catalog.octet_length(cw)+pg_catalog.octet_length(rw)+pg_catalog.octet_length(tw)+pg_catalog.octet_length(jw)+pg_catalog.octet_length(hw)+pg_catalog.octet_length(aw)+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(om))+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(jm))+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(sm));
 FOR d IN SELECT value FROM pg_catalog.jsonb_array_elements(r->'dependencies') LOOP
  ordinal:=ordinal+1;
  row:=pg_catalog.jsonb_build_object('scope',scope,'action_id',c->>'action_id','semantic_kind',d->>'semantic_kind','original_id',d->>'original_id','wire_sha256',d->>'wire_sha256','wire_bytes',d->>'wire_bytes','ordinal',ordinal::text);
  nb:=nb+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(row));
  kb:=kb+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(c->>'action_id',d->>'semantic_kind',d->>'original_id',d->>'wire_sha256')))+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(d->>'semantic_kind',d->>'original_id',d->>'wire_sha256',c->>'action_id')));
 END LOOP;
 FOR v IN SELECT value FROM pg_catalog.jsonb_array_elements(ids) LOOP
  row:=pg_catalog.jsonb_build_object('scope',scope,'original_id',v->>'original_id','wire_bytes',pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(v))::text);
  nb:=nb+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(v))+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(row));
  kb:=kb+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(v->>'original_id')))+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(scope,v->>'original_id')));
 END LOOP;
 FOR v IN SELECT value FROM pg_catalog.jsonb_array_elements(facts) LOOP
  row:=pg_catalog.jsonb_build_object('scope',scope,'semantic_kind',v->>'semantic_kind','original_id',v->>'original_id','wire_sha256',v->>'wire_sha256','native_sequence',seq,'wire_bytes',v->>'wire_bytes');
  nb:=nb+(v->>'wire_bytes')::bigint+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(row));
  kb:=kb+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(v->>'semantic_kind',v->>'original_id',v->>'wire_sha256')))+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(scope,seq,v->>'semantic_kind',v->>'original_id',v->>'wire_sha256')));
 END LOOP;

 IF c->>'action_kind'='installation' THEN
  SELECT pg_catalog.jsonb_build_object('package_wire',package_wire,'actor_manifest_wire',actor_manifest_wire,'genesis_wire',genesis_wire,'installation_id',installation_id,'expected_catalog_sha256',expected_catalog_sha256) INTO v FROM vn_jupiter_b2_fixture_anchor.package_inputs WHERE scope_wire=sw;
  IF pg_catalog.octet_length(v->>'package_wire')+pg_catalog.octet_length(v->>'actor_manifest_wire')+pg_catalog.octet_length(v->>'genesis_wire')>131072 THEN RAISE EXCEPTION 'b2_wire_bound'; END IF;
  row:=pg_catalog.jsonb_build_object('scope',scope,'installation_id',v->>'installation_id','expected_catalog_sha256',v->>'expected_catalog_sha256','package_wire_bytes',pg_catalog.octet_length(v->>'package_wire')::text,'actor_manifest_wire_bytes',pg_catalog.octet_length(v->>'actor_manifest_wire')::text,'genesis_wire_bytes',pg_catalog.octet_length(v->>'genesis_wire')::text);
  nb:=nb+pg_catalog.octet_length(v->>'package_wire')+pg_catalog.octet_length(v->>'actor_manifest_wire')+pg_catalog.octet_length(v->>'genesis_wire')+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(row));
  kb:=kb+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(scope)));
  FOR row IN SELECT pg_catalog.jsonb_build_object('binding_id',binding_id,'session_oid',session_oid::text,'session_name',session_name,'capabilities',pg_catalog.to_jsonb(capabilities),'binding_wire',binding_wire) FROM vn_jupiter_b2_fixture_anchor.actor_bindings WHERE scope_wire=sw LOOP
   IF pg_catalog.octet_length(row->>'binding_wire')>2048 THEN RAISE EXCEPTION 'b2_wire_bound'; END IF;
   nb:=nb+pg_catalog.octet_length(row->>'binding_wire')+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n((row-'binding_wire')||pg_catalog.jsonb_build_object('scope',scope,'binding_wire_bytes',pg_catalog.octet_length(row->>'binding_wire')::text)));
   kb:=kb+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(row->>'binding_id')))+pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_array(row->>'session_oid',row->>'session_name')));
  END LOOP;
 END IF;
 RETURN pg_catalog.jsonb_build_object('bytes',(nb+kb)::text,'stage_bytes',stage::text,'new_rows',(2+dc+ni+nf)::text,'row_writes',(3+dc+ni+nf)::text,'index_entries',(6+2*dc+2*ni+2*nf)::text,'identities',ni::text,'domains',nf::text,'dependencies',dc::text);
END;
$b2$;

-- FUNCTION _budget
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._budget(scope_wire pg_catalog.text, kind pg_catalog.text, cost pg_catalog.jsonb)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE a jsonb; b jsonb; reserve bigint:=CASE WHEN kind='source_stop' THEN 0 ELSE 1 END; past_stage bigint:=0; v record; admin bigint;
BEGIN
 SELECT accounting_wire::jsonb INTO a FROM vn_jupiter_b2_allocation_research_v3.scope_state s WHERE s.scope_wire=_budget.scope_wire;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_scope_refused'; END IF;
 IF a->'Stop_reserve_consumed'='true'::jsonb THEN reserve:=0; END IF;
 SELECT CASE WHEN p.package_wire::jsonb->>'format'='ga-jupiter-b2-fixture-direct-scram-handoff-research-v3-v1' THEN 1 ELSE 0 END INTO admin
 FROM vn_jupiter_b2_fixture_anchor.package_inputs p WHERE p.scope_wire=_budget.scope_wire;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_scope_refused'; END IF;
 -- Derived counters are never hidden persisted fields in Accounting.
 FOR v IN SELECT o.command_wire::jsonb c,o.result_wire::jsonb r FROM vn_jupiter_b2_allocation_research_v3.original_operations o WHERE o.scope_wire=_budget.scope_wire AND o.finalized LOOP
  past_stage:=past_stage+(vn_jupiter_b2_allocation_research_v3._cost(v.c,v.r,'[]','[]')->>'stage_bytes')::bigint;
 END LOOP;
 IF (a->>'committed_positions')::bigint+1+reserve>16 OR (a->>'logical_UTF8_bytes')::bigint+(cost->>'bytes')::bigint+reserve*76533+admin*65536>4194304 OR (a->>'retained_rows')::bigint+(cost->>'new_rows')::bigint+reserve*9+admin*3>271 OR (a->>'identity_rows')::bigint+(cost->>'identities')::bigint>96 OR (a->>'domain_rows')::bigint+(cost->>'domains')::bigint>25 OR (a->>'dependency_rows')::bigint+(cost->>'dependencies')::bigint+reserve*7>112 OR (a->>'row_writes')::bigint+(cost->>'row_writes')::bigint+reserve*10+admin*5>512 OR (a->>'index_entries')::bigint+(cost->>'index_entries')::bigint+reserve*20+admin*6>1024 THEN RAISE EXCEPTION 'b2_budget_refused'; END IF;
 IF (a->>'row_writes')::bigint+(a->>'committed_positions')::bigint+(cost->>'row_writes')::bigint+1+reserve*11+admin*5>1024 OR (a->>'index_entries')::bigint+3*(a->>'committed_positions')::bigint+(cost->>'index_entries')::bigint+3+reserve*23+admin*10>2048 OR (a->>'logical_UTF8_bytes')::bigint+past_stage+(cost->>'bytes')::bigint+(cost->>'stage_bytes')::bigint+reserve*144142+admin*98304>8388608 THEN RAISE EXCEPTION 'b2_budget_refused'; END IF;
 b:=pg_catalog.jsonb_build_object('committed_positions',((a->>'committed_positions')::bigint+1)::text,'logical_UTF8_bytes',((a->>'logical_UTF8_bytes')::bigint+(cost->>'bytes')::bigint)::text,'identity_rows',((a->>'identity_rows')::bigint+(cost->>'identities')::bigint)::text,'domain_rows',((a->>'domain_rows')::bigint+(cost->>'domains')::bigint)::text,'dependency_rows',((a->>'dependency_rows')::bigint+(cost->>'dependencies')::bigint)::text,'retained_rows',((a->>'retained_rows')::bigint+(cost->>'new_rows')::bigint)::text,'row_writes',((a->>'row_writes')::bigint+(cost->>'row_writes')::bigint)::text,'index_entries',((a->>'index_entries')::bigint+(cost->>'index_entries')::bigint)::text,'Stop_reserve_consumed',kind='source_stop' OR a->'Stop_reserve_consumed'='true'::jsonb);
 RETURN b;
END;
$b2$;

-- FUNCTION _reply
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._reply(scope pg_catalog.jsonb, target_id pg_catalog.text, expected_sha pg_catalog.text, getter_recovery pg_catalog.bool, terminal_stop_sha pg_catalog.text)
RETURNS pg_catalog.text
LANGUAGE plpgsql STABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE sw text:=vn_jupiter_b2_allocation_research_v3._scope(scope); a jsonb; target vn_jupiter_b2_allocation_research_v3.original_operations%ROWTYPE; o record; j record; c jsonb; r jsonb; t jsonb; prev text; pins jsonb:='[]'; answer jsonb; body text; count_seen bigint:=0; d jsonb; g jsonb; spec jsonb; expected_record jsonb; expected_facts jsonb; base_facts jsonb; installation_pin jsonb; acquire_pin jsonb; fence_pin jsonb; fence jsonb; epoch jsonb; terminal jsonb; utc jsonb; field text; role text; issued bigint; expires bigint; acquisitions bigint; resumes bigint; renewals bigint; resume_pin jsonb; renew_pin jsonb; next_fence_pin jsonb; next_fence jsonb; next_issued bigint; previous_hold_commit_us bigint; latest_renew_position bigint; renewed_facts jsonb:='[]'; prior_control_sha text; stop_mode text; stop_revision text; packet_plan jsonb; packet_identities bigint; packet_count bigint; packet_tip bigint; predecessor_wire text; predecessor_commit_us bigint; late_capture boolean; reserve_wire text; reserve_head text; stop_seen boolean:=false;
BEGIN
 SELECT * INTO target FROM vn_jupiter_b2_allocation_research_v3.original_operations WHERE action_id=target_id AND scope_wire=sw;
 a:=vn_jupiter_b2_allocation_research_v3._auth(scope,CASE WHEN getter_recovery IS TRUE THEN 'get_original' ELSE 'read_original' END,
  CASE WHEN getter_recovery IS TRUE AND target.finalized AND target.command_sha256=expected_sha
   THEN target.writer_binding_id END,
  terminal_stop_sha,
  CASE WHEN getter_recovery IS TRUE AND target.finalized AND target.command_sha256=expected_sha
   AND target.action_kind='source_stop' AND target.native_sequence=4 THEN target.command_sha256 END);
 IF terminal_stop_sha IS NOT NULL AND (a->>'terminal_retirement')::boolean
  AND (target.action_kind IS DISTINCT FROM 'source_resume' OR target.native_sequence IS DISTINCT FROM 3)
 THEN RAISE EXCEPTION 'b2_retirement_refused'; END IF;
 g:=(a->>'genesis_wire')::jsonb;
 IF target.action_id IS NULL THEN RAISE EXCEPTION 'b2_original_absent'; END IF;
 IF target.writer_xid8=pg_catalog.pg_current_xact_id_if_assigned() THEN RAISE EXCEPTION 'b2_writer_transaction'; END IF;
 IF NOT target.finalized OR target.command_sha256 IS DISTINCT FROM expected_sha THEN RAISE EXCEPTION 'b2_original_refused'; END IF;
 SELECT count(*) INTO acquisitions FROM vn_jupiter_b2_allocation_research_v3.original_operations WHERE scope_wire=sw AND action_kind='fence_acquire' AND finalized;
 SELECT count(*) INTO resumes FROM vn_jupiter_b2_allocation_research_v3.original_operations
  WHERE scope_wire=sw AND action_kind='source_resume' AND (finalized OR writer_xid8=pg_catalog.pg_current_xact_id_if_assigned());
 SELECT count(*) INTO renewals FROM vn_jupiter_b2_allocation_research_v3.original_operations
  WHERE scope_wire=sw AND action_kind='fence_renew' AND (finalized OR writer_xid8=pg_catalog.pg_current_xact_id_if_assigned());
 SELECT count(*) INTO packet_count FROM vn_jupiter_b2_allocation_research_v3.original_operations
  WHERE scope_wire=sw AND action_kind='packet_reservation' AND (finalized OR writer_xid8=pg_catalog.pg_current_xact_id_if_assigned());
 packet_identities:=packet_count*11;
 IF acquisitions>1 OR resumes>1 OR renewals>12 OR packet_count>1 THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
 prev:=vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_object('format','ga-jupiter-b2-empty-head-research-v3-v1','native_policy_sha256','e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0','scope',scope)));
 -- This STABLE function and its STABLE readers share one parent SELECT snapshot.
 FOR o IN SELECT * FROM vn_jupiter_b2_allocation_research_v3.original_operations WHERE scope_wire=sw AND native_sequence<=target.native_sequence ORDER BY native_sequence LOOP
  count_seen:=count_seen+1;
  IF count_seen IS DISTINCT FROM o.native_sequence OR NOT o.finalized OR o.writer_xid8=pg_catalog.pg_current_xact_id_if_assigned() OR vn_jupiter_b2_allocation_research_v3._sha(o.command_wire) IS DISTINCT FROM o.command_sha256 OR vn_jupiter_b2_allocation_research_v3._sha(o.result_wire) IS DISTINCT FROM o.result_sha256 OR vn_jupiter_b2_allocation_research_v3._sha(o.receipt_wire) IS DISTINCT FROM o.receipt_sha256 THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
  c:=o.command_wire::jsonb; r:=o.result_wire::jsonb; t:=o.receipt_wire::jsonb;
  late_capture:=(o.action_kind='capture_retention' AND pg_catalog.to_regprocedure('vn_jupiter_b2_allocation_research_v3._collection_authorization(text)') IS NOT NULL) IS TRUE;
  IF NOT vn_jupiter_b2_allocation_research_v3._keys(c,ARRAY['format','native_policy_sha256','scope','action_id','action_kind','expected_head','expected_fence_id','expected_fence_revision','body']) OR NOT vn_jupiter_b2_allocation_research_v3._keys(r,ARRAY['format','native_policy_sha256','scope','action_id','action_kind','native_sequence','original_command_sha256','dependencies','result_body','limits']) OR NOT vn_jupiter_b2_allocation_research_v3._keys(t,ARRAY['format','native_policy_sha256','scope','action_id','action_kind','original_command_sha256','result_sha256','native_sequence','previous_native_head_sha256','admission_observation','final_function_observation','commit_processing_observation','native_package_sha256','catalog_manifest_sha256','limits']) OR c->>'format' IS DISTINCT FROM 'ga-jupiter-b2-allocation-command-research-v3-v1' OR r->>'format' IS DISTINCT FROM 'ga-jupiter-b2-allocation-result-research-v3-v1' OR t->>'format' IS DISTINCT FROM 'ga-jupiter-b2-allocation-receipt-research-v3-v1' OR c->>'native_policy_sha256' IS DISTINCT FROM (CASE WHEN late_capture THEN 'c468fa4a7fa8e9122a53abb19ed10d3c1d80f8024dfeefbb8596fef8f1c1f8be' WHEN o.action_kind IN('packet_reservation','capture_retention') THEN '28b7df36ca970796b7729d29ca0fd0dde861edfdc09579afef160218a05ade51' ELSE a#>>'{package,native_policy_sha256}' END) OR r->>'native_policy_sha256' IS DISTINCT FROM c->>'native_policy_sha256' OR t->>'native_policy_sha256' IS DISTINCT FROM c->>'native_policy_sha256' OR r->>'action_kind' IS DISTINCT FROM o.action_kind OR t->>'action_kind' IS DISTINCT FROM o.action_kind OR r->'limits' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._limits() OR t->>'native_package_sha256' IS DISTINCT FROM a#>>'{package,native_package_sha256}' OR t->>'catalog_manifest_sha256' IS DISTINCT FROM
    (CASE WHEN o.native_sequence>3 THEN a->>'effective_catalog_sha256' ELSE a#>>'{package,catalog_manifest_sha256}' END) OR vn_jupiter_b2_allocation_research_v3._c14n(c) IS DISTINCT FROM o.command_wire OR vn_jupiter_b2_allocation_research_v3._c14n(r) IS DISTINCT FROM o.result_wire OR vn_jupiter_b2_allocation_research_v3._c14n(t) IS DISTINCT FROM o.receipt_wire OR r->'dependencies' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._deps(r->'dependencies') THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
  IF c->'scope' IS DISTINCT FROM scope OR c->>'action_id' IS DISTINCT FROM o.action_id OR c->>'action_kind' IS DISTINCT FROM o.action_kind OR c->'expected_head' IS DISTINCT FROM (CASE WHEN late_capture THEN pg_catalog.jsonb_build_object('native_sequence','5','native_head_sha256',reserve_head,'previous_seal_sha256',NULL)
   ELSE pg_catalog.jsonb_build_object('native_sequence',(o.native_sequence-1)::text,'native_head_sha256',prev,'previous_seal_sha256',NULL) END) OR (CASE WHEN NOT late_capture AND o.action_kind IN('source_resume','fence_renew','packet_reservation','capture_retention') THEN
  c->'expected_fence_id' IS DISTINCT FROM fence->'fence_id' OR c->'expected_fence_revision' IS DISTINCT FROM fence->'revision'
 ELSE c->'expected_fence_id' IS DISTINCT FROM 'null'::jsonb OR c->'expected_fence_revision' IS DISTINCT FROM 'null'::jsonb END) OR r->>'original_command_sha256' IS DISTINCT FROM o.command_sha256 OR r->>'action_id' IS DISTINCT FROM o.action_id OR r->'scope' IS DISTINCT FROM scope OR r->>'native_sequence' IS DISTINCT FROM o.native_sequence::text OR t->>'original_command_sha256' IS DISTINCT FROM o.command_sha256 OR t->>'result_sha256' IS DISTINCT FROM o.result_sha256 OR t->>'action_id' IS DISTINCT FROM o.action_id OR t->'scope' IS DISTINCT FROM scope OR t->>'native_sequence' IS DISTINCT FROM o.native_sequence::text OR t->>'previous_native_head_sha256' IS DISTINCT FROM prev OR t->'limits' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._limits() OR t->'final_function_observation' IS DISTINCT FROM o.final_function_observation OR t->'admission_observation' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
  FOR utc IN SELECT value FROM pg_catalog.jsonb_array_elements(pg_catalog.jsonb_build_array(t->'final_function_observation',t->'commit_processing_observation')) LOOP
   IF NOT vn_jupiter_b2_allocation_research_v3._keys(utc,ARRAY['observed_at_us','wall_lower_us','wall_upper_us']) THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   FOREACH field IN ARRAY ARRAY['observed_at_us','wall_lower_us','wall_upper_us'] LOOP
    IF pg_catalog.jsonb_typeof(utc->field) IS DISTINCT FROM 'string' OR (utc->>field ~ '^(0|[1-9][0-9]{0,18})$') IS DISTINCT FROM true OR utc->>field IS DISTINCT FROM utc->>'observed_at_us' THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   END LOOP;
  END LOOP;
  IF (t#>>'{commit_processing_observation,observed_at_us}')::bigint<(t#>>'{final_function_observation,observed_at_us}')::bigint THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
  IF o.action_kind='installation' THEN
   IF o.native_sequence<>1
    OR NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements((a->>'actor_manifest_wire')::jsonb->'bindings') e
     WHERE e->>'principal_binding_id'=o.writer_binding_id AND e->'capabilities'='["install","register_epoch","read_original"]'::jsonb)
    OR c->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('installation_id',a#>>'{package,installation_id}','scope',scope,'policies',a#>'{package,policies}','catalog_manifest_sha256',a#>>'{package,catalog_manifest_sha256}','actor_manifest_sha256',a#>>'{package,actor_manifest_sha256}','genesis_registry_sha256',vn_jupiter_b2_allocation_research_v3._sha(a->>'genesis_wire')) THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   FOR spec IN SELECT value FROM pg_catalog.jsonb_array_elements(g->'identity_specs') UNION ALL SELECT pg_catalog.jsonb_build_object('original_id',o.action_id,'identity_role','native_operation_id','association',pg_catalog.jsonb_build_object('owner_id',scope->>'owner_id','run_id',scope->>'run_id','market_epoch',scope->>'market_epoch','packet_reservation_id',NULL)) LOOP
    expected_record:=pg_catalog.jsonb_build_object('original_id',spec->>'original_id','identity_role',spec->>'identity_role','association',spec->'association','original_allocation_sha256',o.command_sha256,'first_native_sequence','1');
    IF NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities i WHERE i.scope_wire=sw AND i.original_id=spec->>'original_id' AND i.record_wire=vn_jupiter_b2_allocation_research_v3._c14n(expected_record)) THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   END LOOP;
   IF (SELECT count(*) FROM vn_jupiter_b2_allocation_research_v3.identities WHERE scope_wire=sw)<>15+2*acquisitions+resumes+renewals+packet_identities THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   epoch:=(g->'initial_acquisition_spec')||pg_catalog.jsonb_build_object('scope',scope,'ordinal','1','original_command_sha256',o.command_sha256);
   terminal:=pg_catalog.jsonb_build_object('format','ga-jupiter-b2-terminal-allocation-research-v3-v1','scope',scope,'installation_id',a#>>'{package,installation_id}','stop_action_id',g->>'terminal_stop_action_id','allocation_command_sha256',o.command_sha256,'first_native_sequence','1');
   expected_facts:=vn_jupiter_b2_allocation_research_v3._deps(pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_genesis_input',a#>>'{package,installation_id}',a->>'genesis_wire'),vn_jupiter_b2_allocation_research_v3._pin('native_epoch_registration',epoch->>'registration_id',vn_jupiter_b2_allocation_research_v3._c14n(epoch)),vn_jupiter_b2_allocation_research_v3._pin('native_terminal_allocation',g->>'terminal_stop_action_id',vn_jupiter_b2_allocation_research_v3._c14n(terminal))));
   IF r->'dependencies' IS DISTINCT FROM expected_facts OR r->'result_body' IS DISTINCT FROM (c->'body')-ARRAY['scope','policies'] OR (SELECT count(*) FROM vn_jupiter_b2_allocation_research_v3.domain_facts WHERE scope_wire=sw)<>3+acquisitions+renewals THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   base_facts:=expected_facts;
   installation_pin:=vn_jupiter_b2_allocation_research_v3._pin('native_command',o.action_id,o.command_wire);
  ELSIF o.action_kind='fence_acquire' THEN
   -- Independently reconstruct the record and identity rows from the original,
   -- held epoch, bound writer and the original accepted clock observations.
   fence:=r#>'{result_body,original_fence_record}';
   IF o.native_sequence<>2 OR base_facts IS NULL OR acquire_pin IS NOT NULL OR o.writer_binding_id IS DISTINCT FROM g#>>'{initial_acquisition_spec,recorder_principal_binding_id}' OR NOT vn_jupiter_b2_allocation_research_v3._keys(r->'result_body',ARRAY['original_fence_record']) OR pg_catalog.jsonb_typeof(fence->'issued_at_us') IS DISTINCT FROM 'string' OR (fence->>'issued_at_us' ~ '^(0|[1-9][0-9]{0,18})$') IS DISTINCT FROM true OR pg_catalog.jsonb_typeof(c#>'{body,fence_id}') IS DISTINCT FROM 'string' OR (c#>>'{body,fence_id}' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true OR c#>>'{body,fence_id}' IS NOT DISTINCT FROM o.action_id THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   IF c->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('fence_id',c#>>'{body,fence_id}','acquisition_epoch',g#>>'{initial_acquisition_spec,acquisition_epoch}','holder_principal_binding_id',o.writer_binding_id,'requested_duration_us','60000000') THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   issued:=(fence->>'issued_at_us')::bigint; expires:=issued+60000000;
   IF fence IS DISTINCT FROM pg_catalog.jsonb_build_object('fence_id',c#>>'{body,fence_id}','scope',scope,'holder_principal_binding_id',o.writer_binding_id,'acquisition_epoch',g#>>'{initial_acquisition_spec,acquisition_epoch}','revision','1','issued_at_us',issued::text,'expires_at_us',expires::text,'original_command_sha256',o.command_sha256,'native_sequence','2') OR issued>(t#>>'{final_function_observation,observed_at_us}')::bigint OR (t#>>'{commit_processing_observation,observed_at_us}')::bigint>=expires OR pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(fence))>1024 THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   FOREACH role IN ARRAY ARRAY['native_operation_id','fence_id'] LOOP
    expected_record:=pg_catalog.jsonb_build_object('original_id',CASE WHEN role='fence_id' THEN c#>>'{body,fence_id}' ELSE o.action_id END,'identity_role',role,'association',scope||'{"packet_reservation_id":null}'::jsonb,'original_allocation_sha256',o.command_sha256,'first_native_sequence','2');
    IF NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities i WHERE i.scope_wire=sw AND i.original_id=expected_record->>'original_id' AND i.record_wire=vn_jupiter_b2_allocation_research_v3._c14n(expected_record)) THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   END LOOP;
   fence_pin:=vn_jupiter_b2_allocation_research_v3._pin('native_fence_record',fence->>'fence_id',vn_jupiter_b2_allocation_research_v3._c14n(fence));
   acquire_pin:=vn_jupiter_b2_allocation_research_v3._pin('native_command',o.action_id,o.command_wire);
   expected_facts:=vn_jupiter_b2_allocation_research_v3._deps(base_facts||pg_catalog.jsonb_build_array(installation_pin,fence_pin));
   IF r->'dependencies' IS DISTINCT FROM expected_facts OR NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.domain_facts d WHERE d.scope_wire=sw AND d.native_sequence=2 AND d.semantic_kind='native_fence_record' AND d.original_id=fence->>'fence_id' AND d.original_wire=fence_pin->>'original_wire' AND d.wire_sha256=fence_pin->>'wire_sha256') THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
  ELSIF o.action_kind='source_resume' THEN
   IF o.native_sequence<>3 OR acquire_pin IS NULL OR resume_pin IS NOT NULL
    OR c->'body' IS DISTINCT FROM '{"expected_control_sha256":null,"expected_mode":"paused"}'::jsonb
    OR NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements((a->>'actor_manifest_wire')::jsonb->'bindings') e
     WHERE e->>'principal_binding_id'=o.writer_binding_id AND e->'capabilities'='["control","read_original"]'::jsonb)
    OR o.writer_binding_id IS NOT DISTINCT FROM fence->>'holder_principal_binding_id'
    OR (t#>>'{final_function_observation,observed_at_us}')::bigint<issued
    OR (t#>>'{commit_processing_observation,observed_at_us}')::bigint>=expires
    OR r->'result_body' IS DISTINCT FROM '{"previous_mode":"paused","resulting_mode":"open","previous_control_sha256":null,"resulting_fence_revision":"1"}'::jsonb
   THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   expected_record:=pg_catalog.jsonb_build_object('original_id',o.action_id,'identity_role','control_action_id','association',scope||'{"packet_reservation_id":null}'::jsonb,'original_allocation_sha256',o.command_sha256,'first_native_sequence','3');
   IF NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities i WHERE i.scope_wire=sw AND i.original_id=o.action_id AND i.record_wire=vn_jupiter_b2_allocation_research_v3._c14n(expected_record)) THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   expected_facts:=vn_jupiter_b2_allocation_research_v3._deps(base_facts||pg_catalog.jsonb_build_array(installation_pin,acquire_pin,fence_pin));
   IF r->'dependencies' IS DISTINCT FROM expected_facts THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   resume_pin:=vn_jupiter_b2_allocation_research_v3._pin('native_command',o.action_id,o.command_wire);
   prior_control_sha:=o.command_sha256;
   previous_hold_commit_us:=(t#>>'{commit_processing_observation,observed_at_us}')::bigint;
  ELSIF o.action_kind='fence_renew' THEN
   next_fence:=r#>'{result_body,original_fence_record}';
   IF o.native_sequence NOT BETWEEN 4 AND 15 OR resume_pin IS NULL
    OR o.native_sequence IS DISTINCT FROM COALESCE(latest_renew_position+1,4)
    OR c->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('fence_id',fence->>'fence_id','expected_revision',fence->>'revision','requested_duration_us','60000000')
    OR pg_catalog.jsonb_typeof(next_fence->'issued_at_us') IS DISTINCT FROM 'string'
    OR (next_fence->>'issued_at_us' ~ '^(0|[1-9][0-9]{0,18})$') IS DISTINCT FROM true
   THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   IF a->'handoff' IS DISTINCT FROM 'null'::jsonb THEN
    IF NOT vn_jupiter_b2_allocation_research_v3._handoff_allows_renew(a->'handoff',o.native_sequence,o.command_sha256,o.writer_binding_id,fence,prev)
    THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   ELSIF o.writer_binding_id IS DISTINCT FROM g#>>'{initial_acquisition_spec,recorder_principal_binding_id}'
     OR o.writer_binding_id IS DISTINCT FROM fence->>'holder_principal_binding_id'
   THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   next_issued:=(next_fence->>'issued_at_us')::bigint;
   IF next_issued<previous_hold_commit_us OR next_issued<issued
    OR (a->'handoff' IS DISTINCT FROM 'null'::jsonb AND next_issued<(a#>>'{handoff,observed_us}')::bigint)
    OR next_issued>(t#>>'{final_function_observation,observed_at_us}')::bigint
    OR (t#>>'{commit_processing_observation,observed_at_us}')::bigint>=expires
    OR next_fence IS DISTINCT FROM pg_catalog.jsonb_build_object('fence_id',fence->>'fence_id','scope',scope,
     'holder_principal_binding_id',o.writer_binding_id,'acquisition_epoch',fence->>'acquisition_epoch',
     'revision',(o.native_sequence-2)::text,'issued_at_us',next_issued::text,'expires_at_us',(next_issued+60000000)::text,
     'original_command_sha256',o.command_sha256,'native_sequence',o.native_sequence::text)
    OR r->'result_body' IS DISTINCT FROM pg_catalog.jsonb_build_object('original_fence_record',next_fence,'previous_fence_sha256',fence_pin->>'wire_sha256')
   THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   expected_record:=pg_catalog.jsonb_build_object('original_id',o.action_id,'identity_role','native_operation_id',
    'association',scope||'{"packet_reservation_id":null}'::jsonb,'original_allocation_sha256',o.command_sha256,'first_native_sequence',o.native_sequence::text);
   IF NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities i WHERE i.scope_wire=sw AND i.original_id=o.action_id AND i.record_wire=vn_jupiter_b2_allocation_research_v3._c14n(expected_record)) THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   next_fence_pin:=vn_jupiter_b2_allocation_research_v3._pin('native_fence_record',fence->>'fence_id',vn_jupiter_b2_allocation_research_v3._c14n(next_fence));
   expected_facts:=vn_jupiter_b2_allocation_research_v3._deps(base_facts||pg_catalog.jsonb_build_array(installation_pin,COALESCE(renew_pin,resume_pin),fence_pin,next_fence_pin));
   IF (next_fence_pin->>'wire_bytes')::bigint>1024 OR r->'dependencies' IS DISTINCT FROM expected_facts
    OR NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.domain_facts d WHERE d.scope_wire=sw AND d.native_sequence=o.native_sequence
     AND d.semantic_kind='native_fence_record' AND d.original_id=next_fence_pin->>'original_id'
     AND d.original_wire=next_fence_pin->>'original_wire' AND d.wire_sha256=next_fence_pin->>'wire_sha256')
   THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   renew_pin:=vn_jupiter_b2_allocation_research_v3._pin('native_command',o.action_id,o.command_wire);
   latest_renew_position:=o.native_sequence;
   renewed_facts:=renewed_facts||pg_catalog.jsonb_build_array(
    pg_catalog.jsonb_build_object('position',o.native_sequence,'pin',next_fence_pin));
   fence:=next_fence;
   fence_pin:=next_fence_pin;
   issued:=next_issued;
   expires:=issued+60000000;
   previous_hold_commit_us:=(t#>>'{commit_processing_observation,observed_at_us}')::bigint;
  ELSIF o.action_kind IN('packet_reservation','capture_retention') THEN
   IF latest_renew_position IS DISTINCT FROM 4 OR packet_tip IS NOT NULL AND packet_tip<>5
    OR (late_capture AND (packet_tip IS DISTINCT FROM 5 OR reserve_head IS NULL
     OR o.native_sequence IS DISTINCT FROM (CASE WHEN stop_seen THEN 7 ELSE 6 END)))
    OR (t#>>'{final_function_observation,observed_at_us}')::bigint<predecessor_commit_us
    OR (t#>>'{final_function_observation,observed_at_us}')::bigint<issued
    OR (NOT late_capture AND (t#>>'{commit_processing_observation,observed_at_us}')::bigint>=expires)
   THEN RAISE EXCEPTION 'b3_original_assembly_refused'; END IF;
   packet_plan:=vn_jupiter_b2_allocation_research_v3._packet_plan(c,a,o.native_sequence,o.writer_binding_id,fence,
    CASE WHEN late_capture THEN reserve_wire ELSE predecessor_wire END);
   IF r->'dependencies' IS DISTINCT FROM packet_plan->'dependencies'
    OR r->'result_body' IS DISTINCT FROM packet_plan->'body'
    OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(packet_plan->'ids') expected(record_value)
     WHERE NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities i WHERE i.scope_wire=sw
      AND i.original_id=expected.record_value->>'original_id' AND i.record_wire=vn_jupiter_b2_allocation_research_v3._c14n(expected.record_value)))
   THEN RAISE EXCEPTION 'b3_original_assembly_refused'; END IF;
   packet_tip:=o.native_sequence;
  ELSIF o.action_kind='source_stop' THEN
   stop_mode:=CASE WHEN resume_pin IS NULL THEN 'paused' ELSE 'open' END;
   stop_revision:=CASE WHEN renew_pin IS NOT NULL THEN (latest_renew_position-1)::text WHEN acquire_pin IS NULL THEN '1' ELSE '2' END;
   IF base_facts IS NULL OR o.native_sequence<>(CASE WHEN renew_pin IS NOT NULL THEN COALESCE(packet_tip,latest_renew_position)+1 WHEN resume_pin IS NOT NULL THEN 4 WHEN acquire_pin IS NOT NULL THEN 3 ELSE 2 END)
    OR o.action_id IS DISTINCT FROM g->>'terminal_stop_action_id'
    OR c->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('expected_control_sha256',prior_control_sha,'expected_mode',stop_mode)
    OR r->'result_body' IS DISTINCT FROM pg_catalog.jsonb_build_object('previous_mode',stop_mode,'resulting_mode','stopped','previous_control_sha256',prior_control_sha,'resulting_fence_revision',stop_revision)
    OR NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements((a->>'actor_manifest_wire')::jsonb->'bindings') e
     WHERE e->>'principal_binding_id'=o.writer_binding_id AND e->'capabilities'='["control","read_original"]'::jsonb)
   THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   expected_facts:=base_facts||pg_catalog.jsonb_build_array(installation_pin);
   IF renew_pin IS NOT NULL THEN
    expected_facts:=expected_facts||pg_catalog.jsonb_build_array(resume_pin,renew_pin,fence_pin);
   ELSIF acquire_pin IS NOT NULL THEN
    expected_facts:=expected_facts||pg_catalog.jsonb_build_array(COALESCE(resume_pin,acquire_pin),fence_pin);
   END IF;
   IF r->'dependencies' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._deps(expected_facts) THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
   stop_seen:=true;
  ELSE RAISE EXCEPTION 'b2_kind_not_implemented';
  END IF;
  SELECT * INTO j FROM vn_jupiter_b2_allocation_research_v3.journal_entries WHERE scope_wire=sw AND native_sequence=o.native_sequence;
  IF NOT FOUND OR j.action_id IS DISTINCT FROM o.action_id OR j.journal_wire IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_object('native_sequence',o.native_sequence::text,'action_id',o.action_id,'action_kind',o.action_kind,'original_command_sha256',o.command_sha256,'original_result_sha256',o.result_sha256,'original_receipt_sha256',o.receipt_sha256,'previous_native_head_sha256',prev)) OR vn_jupiter_b2_allocation_research_v3._sha(j.journal_wire) IS DISTINCT FROM j.journal_sha256 THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
  FOR d IN SELECT value FROM pg_catalog.jsonb_array_elements(r->'dependencies') LOOP
   IF vn_jupiter_b2_allocation_research_v3._sha(d->>'original_wire') IS DISTINCT FROM d->>'wire_sha256' OR pg_catalog.octet_length(d->>'original_wire')::text IS DISTINCT FROM d->>'wire_bytes' OR NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.dependency_associations x WHERE x.action_id=o.action_id AND x.scope_wire=sw AND x.semantic_kind=d->>'semantic_kind' AND x.original_id=d->>'original_id' AND x.wire_sha256=d->>'wire_sha256' AND x.wire_bytes::text=d->>'wire_bytes' AND x.ordinal=(SELECT z.ord FROM pg_catalog.jsonb_array_elements(r->'dependencies') WITH ORDINALITY z(value,ord) WHERE z.value=d)) THEN RAISE EXCEPTION 'b2_dependency_refused'; END IF;
   IF d->>'semantic_kind'='native_command' THEN
    IF NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.original_operations z WHERE z.action_id=d->>'original_id' AND z.scope_wire=sw AND z.command_wire=d->>'original_wire' AND z.command_sha256=d->>'wire_sha256' AND z.finalized AND z.native_sequence<o.native_sequence) THEN RAISE EXCEPTION 'b2_dependency_refused'; END IF;
   ELSE
    IF NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.domain_facts z WHERE z.scope_wire=sw AND z.semantic_kind=d->>'semantic_kind' AND z.original_id=d->>'original_id' AND z.wire_sha256=d->>'wire_sha256' AND z.original_wire=d->>'original_wire' AND z.native_sequence<=o.native_sequence) THEN RAISE EXCEPTION 'b2_dependency_refused'; END IF;
   END IF;
  END LOOP;
  IF pg_catalog.jsonb_array_length(r->'dependencies') IS DISTINCT FROM (SELECT count(*) FROM vn_jupiter_b2_allocation_research_v3.dependency_associations WHERE action_id=o.action_id AND scope_wire=sw) THEN RAISE EXCEPTION 'b2_dependency_refused'; END IF;
  IF o.action_id IS DISTINCT FROM target_id THEN pins:=pins||pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_command',o.action_id,o.command_wire),vn_jupiter_b2_allocation_research_v3._pin('native_result',o.action_id,o.result_wire),vn_jupiter_b2_allocation_research_v3._pin('native_receipt',o.action_id,o.receipt_wire)); END IF;
  prev:=j.journal_sha256; predecessor_wire:=o.command_wire;
  predecessor_commit_us:=(t#>>'{commit_processing_observation,observed_at_us}')::bigint;
  IF o.action_kind='packet_reservation' THEN reserve_wire:=o.command_wire; reserve_head:=j.journal_sha256; END IF;
 END LOOP;
 IF count_seen IS DISTINCT FROM target.native_sequence THEN RAISE EXCEPTION 'b2_original_assembly_refused'; END IF;
 FOR o IN SELECT * FROM vn_jupiter_b2_allocation_research_v3.domain_facts WHERE scope_wire=sw AND native_sequence<=target.native_sequence LOOP
  IF vn_jupiter_b2_allocation_research_v3._sha(o.original_wire) IS DISTINCT FROM o.wire_sha256 THEN RAISE EXCEPTION 'b2_dependency_refused'; END IF;
  IF o.semantic_kind='native_fence_record' AND o.native_sequence BETWEEN 4 AND 15 THEN
   -- Each later version must have been independently derived from the exact
   -- acquired identity and contiguous prior Renew chain above.
   IF NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(renewed_facts) f(value)
    WHERE f.value->'position'=pg_catalog.to_jsonb(o.native_sequence)
    AND f.value#>>'{pin,original_id}'=o.original_id
    AND f.value#>>'{pin,wire_sha256}'=o.wire_sha256
    AND f.value#>>'{pin,original_wire}'=o.original_wire)
   THEN RAISE EXCEPTION 'b2_dependency_refused'; END IF;
  ELSIF NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities i WHERE i.original_id=o.original_id
   AND i.scope_wire=sw AND i.record_wire::jsonb->>'first_native_sequence'=o.native_sequence::text)
  THEN RAISE EXCEPTION 'b2_dependency_refused'; END IF;
  pins:=pins||pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin(o.semantic_kind,o.original_id,o.original_wire));
 END LOOP;
 SELECT COALESCE(pg_catalog.jsonb_agg(v ORDER BY v->>'semantic_kind' COLLATE "C",v->>'original_id' COLLATE "C",v->>'wire_sha256' COLLATE "C"),'[]') INTO pins FROM(SELECT DISTINCT value v FROM pg_catalog.jsonb_array_elements(pins)) x;
 IF pg_catalog.jsonb_array_length(pins)>70 THEN RAISE EXCEPTION 'b2_reply_bound'; END IF;
 answer:=pg_catalog.jsonb_build_object('format','ga-jupiter-b2-original-reply-research-v3-v1','native_policy_sha256',(target.command_wire::jsonb)->>'native_policy_sha256','scope',scope,'target_kind',target.action_kind,'target_id',target.action_id,'original_command_wire',target.command_wire,'original_result_wire',target.result_wire,'original_receipt_wire',target.receipt_wire,'dependencies',pins,'observed_head',(SELECT pg_catalog.jsonb_build_object('native_sequence',head_wire::jsonb->>'native_sequence','native_head_sha256',head_wire::jsonb->>'native_head_sha256','previous_seal_sha256',NULL) FROM vn_jupiter_b2_allocation_research_v3.scope_state WHERE scope_wire=sw),'limits',vn_jupiter_b2_allocation_research_v3._limits());
 body:=vn_jupiter_b2_allocation_research_v3._c14n(answer);
 IF pg_catalog.octet_length(body)+1>8388608 THEN RAISE EXCEPTION 'b2_reply_bound'; END IF;
 IF a->'credential_windows' IS DISTINCT FROM 'null'::jsonb
 THEN PERFORM vn_jupiter_b2_allocation_research_v3._check_credential_window(a->'credential_windows',(vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint); END IF;
 RETURN body;
END;
$b2$;

-- FUNCTION get_original
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3.get_original(wire pg_catalog.text)
RETURNS pg_catalog.text
LANGUAGE plpgsql STABLE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE q jsonb; sw text; o record; obs jsonb; a jsonb; body text;
BEGIN
 IF wire IS NULL OR pg_catalog.octet_length(wire)>2048 THEN RAISE EXCEPTION 'b2_invalid_query'; END IF;
 q:=wire::jsonb;
 IF q->>'format'='ga-jupiter-b3-collection-authorization-query-v2' THEN
  IF NOT (pg_catalog.to_regprocedure('vn_jupiter_b2_allocation_research_v3._collection_authorization(text)') IS NOT NULL) THEN RAISE EXCEPTION 'b2_invalid_query'; END IF;
  RETURN vn_jupiter_b2_allocation_research_v3._collection_authorization(wire);
 END IF;
 IF vn_jupiter_b2_allocation_research_v3._c14n(q)<>wire OR NOT vn_jupiter_b2_allocation_research_v3._keys(q,ARRAY['format','native_policy_sha256','scope','target_kind','target_id','expected_original_command_sha256','correlation']) OR q->>'format' IS DISTINCT FROM 'ga-jupiter-b2-original-query-research-v3-v1' OR q->>'native_policy_sha256' IS DISTINCT FROM (CASE WHEN q->>'target_kind'='capture_retention' AND pg_catalog.to_regprocedure('vn_jupiter_b2_allocation_research_v3._collection_authorization(text)') IS NOT NULL THEN 'c468fa4a7fa8e9122a53abb19ed10d3c1d80f8024dfeefbb8596fef8f1c1f8be' WHEN q->>'target_kind' IN('packet_reservation','capture_retention') THEN '28b7df36ca970796b7729d29ca0fd0dde861edfdc09579afef160218a05ade51' ELSE 'e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0' END) OR (pg_catalog.jsonb_typeof(q->'target_kind') IS DISTINCT FROM 'string' OR q->>'target_kind' NOT IN('installation','fence_acquire','source_resume','fence_renew','source_stop','packet_reservation','capture_retention')) OR pg_catalog.jsonb_typeof(q->'target_id')<>'string' OR (q->>'target_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true OR (CASE WHEN q->>'target_kind'='capture_retention' AND q->'expected_original_command_sha256'='null'::jsonb
     THEN false ELSE pg_catalog.jsonb_typeof(q->'expected_original_command_sha256') IS DISTINCT FROM 'string'
     OR (q->>'expected_original_command_sha256' ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true END) OR q->'correlation' IS DISTINCT FROM pg_catalog.jsonb_build_object('kind','original_action_id','id',q->>'target_id') THEN RAISE EXCEPTION 'b2_invalid_query'; END IF;
 sw:=vn_jupiter_b2_allocation_research_v3._scope(q->'scope');
 -- Authenticate caller and deadline without granting a catalog-drift exception
 -- before the exact scoped original, if any, selects the full getter check.
 PERFORM vn_jupiter_b2_allocation_research_v3._auth(q->'scope','get_original_precheck',NULL,NULL,NULL);
 IF q->'expected_original_command_sha256'='null'::jsonb THEN
  a:=vn_jupiter_b2_allocation_research_v3._auth(q->'scope','get_original',NULL,NULL,NULL);
  IF pg_catalog.jsonb_typeof(a->'handoff') IS DISTINCT FROM 'object'
   OR a->>'binding_id' IS DISTINCT FROM (a->>'genesis_wire')::jsonb#>>'{initial_acquisition_spec,reader_principal_binding_id}'
   OR a#>>'{package,policies,a1_schema_sha256}' IS DISTINCT FROM '2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640'
  THEN RAISE EXCEPTION 'b3_capture_reader_refused' USING ERRCODE='42501'; END IF;
 END IF;
 SELECT * INTO o FROM vn_jupiter_b2_allocation_research_v3.original_operations WHERE action_id=q->>'target_id' AND scope_wire=sw;
 IF FOUND THEN
  IF o.action_kind<>q->>'target_kind' OR (o.command_wire::jsonb)->>'native_policy_sha256' IS DISTINCT FROM q->>'native_policy_sha256' THEN
   PERFORM vn_jupiter_b2_allocation_research_v3._auth(q->'scope','get_original',NULL,NULL,NULL);
   RAISE EXCEPTION 'b2_original_refused';
  END IF;
  RETURN vn_jupiter_b2_allocation_research_v3._reply(q->'scope',q->>'target_id',COALESCE(q->>'expected_original_command_sha256',o.command_sha256),true,NULL);
 END IF;
 a:=vn_jupiter_b2_allocation_research_v3._auth(q->'scope','get_original',NULL,NULL,NULL);
 obs:=pg_catalog.jsonb_build_object('format','ga-jupiter-b2-query-observation-research-v3-v1','native_policy_sha256',q->>'native_policy_sha256','scope',q->'scope','target_kind',q->>'target_kind','target_id',q->>'target_id','correlation',q->'correlation','resolution','observed_absent_unknown','observed_head',(SELECT head_wire::jsonb - ARRAY['scope','active_acquisition_epoch','active_fence_id','fence_revision','source_mode','last_admission_sha256','last_ingest_sequence','last_availability_sha256'] FROM vn_jupiter_b2_allocation_research_v3.scope_state WHERE scope_wire=sw),'original_operation_pin',NULL,'limits',vn_jupiter_b2_allocation_research_v3._limits());
 body:=vn_jupiter_b2_allocation_research_v3._c14n(obs);
 IF a->'credential_windows' IS DISTINCT FROM 'null'::jsonb
 THEN PERFORM vn_jupiter_b2_allocation_research_v3._check_credential_window(a->'credential_windows',(vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint); END IF;
 RETURN body;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RAISE EXCEPTION 'b2_invalid_query';
END;
$b2$;

-- FUNCTION _submit
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._submit(wire pg_catalog.text, register_stop_intent pg_catalog.bool)
RETURNS pg_catalog.text
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE c jsonb; sw text; a jsonb; p jsonb; g jsonb; h jsonb; oldop record; st record; spec jsonb; ass jsonb; idrow jsonb; epoch jsonb; terminal jsonb; v jsonb; d jsonb; deps jsonb; ids jsonb:='[]'; facts jsonb:='[]'; r jsonb; cw text; ch text; rw text; seq bigint; cost jsonb; chk jsonb; ordinal bigint:=0; role text; expected_body jsonb; prior record; prior_reply jsonb; prior_result jsonb; fence jsonb; issued bigint; expires bigint; final_obs jsonb; prior_control_sha text; previous_mode text; next_fence_record jsonb; previous_expiry bigint; previous_commit_us bigint; control_original record; existing_intent text; packet_plan jsonb; packet_renew record; packet_stop boolean; late_capture boolean; reserve_wire text; reserve_head text;
BEGIN
 IF register_stop_intent IS NULL OR wire IS NULL OR pg_catalog.octet_length(wire)>1048576 THEN RAISE EXCEPTION 'b2_invalid_command'; END IF;
 c:=wire::jsonb;
 late_capture:=(c->>'action_kind'='capture_retention' AND pg_catalog.to_regprocedure('vn_jupiter_b2_allocation_research_v3._collection_authorization(text)') IS NOT NULL) IS TRUE;
 IF c->>'action_kind' IS DISTINCT FROM 'capture_retention' AND pg_catalog.octet_length(wire)>16384
 THEN RAISE EXCEPTION 'b2_invalid_command'; END IF;
 IF vn_jupiter_b2_allocation_research_v3._c14n(c) IS DISTINCT FROM wire OR NOT vn_jupiter_b2_allocation_research_v3._keys(c,ARRAY['format','native_policy_sha256','scope','action_id','action_kind','expected_head','expected_fence_id','expected_fence_revision','body']) OR c->>'format' IS DISTINCT FROM 'ga-jupiter-b2-allocation-command-research-v3-v1' OR c->>'native_policy_sha256' IS DISTINCT FROM (CASE WHEN c->>'action_kind'='capture_retention' AND pg_catalog.to_regprocedure('vn_jupiter_b2_allocation_research_v3._collection_authorization(text)') IS NOT NULL THEN 'c468fa4a7fa8e9122a53abb19ed10d3c1d80f8024dfeefbb8596fef8f1c1f8be' WHEN c->>'action_kind' IN('packet_reservation','capture_retention') THEN '28b7df36ca970796b7729d29ca0fd0dde861edfdc09579afef160218a05ade51' ELSE 'e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0' END) OR pg_catalog.jsonb_typeof(c->'action_id') IS DISTINCT FROM 'string' OR (c->>'action_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true THEN RAISE EXCEPTION 'b2_invalid_command'; END IF;
 sw:=vn_jupiter_b2_allocation_research_v3._scope(c->'scope');
 IF c->>'action_kind' NOT IN('installation','fence_acquire','source_resume','fence_renew','source_stop','packet_reservation','capture_retention') OR pg_catalog.jsonb_typeof(c->'action_kind') IS DISTINCT FROM 'string' THEN
  PERFORM vn_jupiter_b2_allocation_research_v3._auth(c->'scope','read_original',NULL,NULL,NULL); RAISE EXCEPTION 'b2_kind_not_implemented';
 END IF;
 IF register_stop_intent THEN
  IF c->>'action_kind' IS DISTINCT FROM 'source_stop'
  THEN RAISE EXCEPTION 'b2_stop_intent_profile_refused' USING ERRCODE='42501'; END IF;
 ELSE
  a:=vn_jupiter_b2_allocation_research_v3._auth(c->'scope','read_original',NULL,
   CASE WHEN c->>'action_kind'='source_stop' THEN vn_jupiter_b2_allocation_research_v3._sha(wire) END,NULL);
  IF c->>'action_kind' IN('packet_reservation','capture_retention')
   AND (NOT (a->>'handoff_profile')::boolean
    OR a#>>'{package,policies,a1_schema_sha256}' IS DISTINCT FROM '2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640')
  THEN RAISE EXCEPTION 'b2_kind_not_implemented'; END IF;
  -- Exact read-authorized replay precedes fresh head/mode/counter checks.
  SELECT * INTO oldop FROM vn_jupiter_b2_allocation_research_v3.original_operations WHERE action_id=c->>'action_id';
  IF FOUND THEN
   IF oldop.scope_wire IS DISTINCT FROM sw OR oldop.action_kind IS DISTINCT FROM c->>'action_kind' OR oldop.command_wire IS DISTINCT FROM wire THEN RAISE EXCEPTION 'b2_original_conflict'; END IF;
   RETURN vn_jupiter_b2_allocation_research_v3._reply(c->'scope',c->>'action_id',vn_jupiter_b2_allocation_research_v3._sha(wire),false,NULL);
  END IF;
 END IF;
 PERFORM vn_jupiter_b2_fixture_anchor._lock_inputs(sw,c->>'action_kind'='source_resume');
 -- Reauthorize from a fresh statement snapshot while the required input rows are held.
 a:=vn_jupiter_b2_allocation_research_v3._auth(c->'scope',CASE c->>'action_kind' WHEN 'installation' THEN 'install' WHEN 'fence_acquire' THEN 'fence_manage' WHEN 'fence_renew' THEN 'fence_manage' WHEN 'source_resume' THEN 'resume_scope' WHEN 'packet_reservation' THEN 'reserve' WHEN 'capture_retention' THEN 'reserve' ELSE 'control' END,NULL,CASE WHEN c->>'action_kind'='source_stop' THEN vn_jupiter_b2_allocation_research_v3._sha(wire) END,NULL); p:=a->'package'; g:=(a->>'genesis_wire')::jsonb;
 SELECT * INTO st FROM vn_jupiter_b2_allocation_research_v3.scope_state WHERE scope_wire=sw FOR UPDATE;
 IF NOT FOUND OR pg_catalog.current_setting('synchronous_commit')<>'on' OR pg_catalog.current_setting('fsync')<>'on' THEN RAISE EXCEPTION 'b2_session_refused'; END IF;
 IF register_stop_intent THEN
  existing_intent:=vn_jupiter_b2_allocation_research_v3._existing_stop_intent(sw,c,wire,a);
  IF existing_intent IS NOT NULL THEN RETURN existing_intent; END IF;
  IF EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.original_operations o WHERE o.action_id=c->>'action_id')
  THEN RAISE EXCEPTION 'b2_stop_intent_conflict' USING ERRCODE='42501'; END IF;
 ELSIF c->>'action_kind'='source_stop' AND pg_catalog.jsonb_typeof(a->'handoff')='object' THEN
  PERFORM vn_jupiter_b2_allocation_research_v3._require_exact_stop_intent(sw,c,wire,a);
 END IF;
 h:=st.head_wire::jsonb;
 IF (a->>'handoff_profile')::boolean AND c->>'action_kind'<>'source_stop'
  AND NOT (late_capture AND h->>'source_mode'='stopped')
 THEN PERFORM vn_jupiter_b2_allocation_research_v3._require_no_stop_intent(sw); END IF;
 IF EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.original_operations WHERE writer_xid8=pg_catalog.pg_current_xact_id()) THEN RAISE EXCEPTION 'b2_one_new_operation'; END IF;
 IF (NOT late_capture AND c->'expected_head' IS DISTINCT FROM pg_catalog.jsonb_build_object('native_sequence',h->>'native_sequence','native_head_sha256',h->>'native_head_sha256','previous_seal_sha256',NULL)) OR (CASE WHEN NOT late_capture AND c->>'action_kind' IN('source_resume','fence_renew','packet_reservation','capture_retention') THEN
  c->'expected_fence_id' IS DISTINCT FROM h->'active_fence_id' OR c->'expected_fence_revision' IS DISTINCT FROM h->'fence_revision'
 ELSE c->'expected_fence_id' IS DISTINCT FROM 'null'::jsonb OR c->'expected_fence_revision' IS DISTINCT FROM 'null'::jsonb END) THEN RAISE EXCEPTION 'b2_stale_head'; END IF;
 seq:=(h->>'native_sequence')::bigint+1; ch:=vn_jupiter_b2_allocation_research_v3._sha(wire);
 IF c->>'action_kind'='installation' THEN
  IF seq<>1 OR EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.original_operations WHERE scope_wire=sw) OR NOT vn_jupiter_b2_allocation_research_v3._keys(c->'body',ARRAY['installation_id','scope','policies','catalog_manifest_sha256','actor_manifest_sha256','genesis_registry_sha256']) THEN RAISE EXCEPTION 'b2_installation_refused'; END IF;
  expected_body:=pg_catalog.jsonb_build_object('installation_id',p->>'installation_id','scope',c->'scope','policies',p->'policies','catalog_manifest_sha256',p->>'catalog_manifest_sha256','actor_manifest_sha256',p->>'actor_manifest_sha256','genesis_registry_sha256',vn_jupiter_b2_allocation_research_v3._sha(a->>'genesis_wire'));
  IF c->'body' IS DISTINCT FROM expected_body OR g->'scope' IS DISTINCT FROM c->'scope' OR g->>'format' IS DISTINCT FROM 'ga-jupiter-b2-genesis-registry-research-v3-v1' OR pg_catalog.jsonb_array_length(g->'identity_specs')<>14 THEN RAISE EXCEPTION 'b2_installation_refused'; END IF;
  IF NOT vn_jupiter_b2_allocation_research_v3._keys(g,ARRAY['format','scope','identity_specs','initial_acquisition_spec','terminal_stop_action_id']) OR pg_catalog.jsonb_typeof(g->'identity_specs') IS DISTINCT FROM 'array' OR vn_jupiter_b2_allocation_research_v3._c14n(g) IS DISTINCT FROM a->>'genesis_wire' THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(g->'identity_specs') x WHERE NOT vn_jupiter_b2_allocation_research_v3._keys(x,ARRAY['original_id','identity_role','association']) OR pg_catalog.jsonb_typeof(x->'identity_role') IS DISTINCT FROM 'string') THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
  IF (SELECT pg_catalog.jsonb_object_agg(q.role,q.cnt) FROM(SELECT value->>'identity_role' role,count(*) cnt FROM pg_catalog.jsonb_array_elements(g->'identity_specs') GROUP BY value->>'identity_role') q) IS DISTINCT FROM '{"owner_id":1,"run_id":1,"market_epoch":1,"installation_id":1,"principal_binding_id":4,"issuer_binding_id":1,"endpoint_binding_id":2,"registration_id":1,"acquisition_epoch":1,"control_action_id":1}'::jsonb THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
  FOR spec IN SELECT value FROM pg_catalog.jsonb_array_elements(g->'identity_specs') UNION ALL SELECT pg_catalog.jsonb_build_object('original_id',c->>'action_id','identity_role','native_operation_id','association',pg_catalog.jsonb_build_object('owner_id',c#>>'{scope,owner_id}','run_id',c#>>'{scope,run_id}','market_epoch',c#>>'{scope,market_epoch}','packet_reservation_id',NULL)) LOOP
   IF NOT vn_jupiter_b2_allocation_research_v3._keys(spec,ARRAY['original_id','identity_role','association']) OR pg_catalog.jsonb_typeof(spec->'original_id') IS DISTINCT FROM 'string' OR (spec->>'original_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
   role:=spec->>'identity_role';
   IF pg_catalog.jsonb_typeof(spec->'identity_role') IS DISTINCT FROM 'string' OR (role IN('owner_id','run_id','market_epoch','installation_id','principal_binding_id','issuer_binding_id','endpoint_binding_id','registration_id','acquisition_epoch','control_action_id','native_operation_id')) IS DISTINCT FROM true THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
   IF (role IN('owner_id','run_id','market_epoch') AND spec->>'original_id' IS DISTINCT FROM c#>>ARRAY['scope',role]) OR (role='installation_id' AND spec->>'original_id' IS DISTINCT FROM p->>'installation_id') OR (role='control_action_id' AND spec->>'original_id' IS DISTINCT FROM g->>'terminal_stop_action_id') OR (role='principal_binding_id' AND NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings z WHERE z.scope_wire=sw AND z.binding_id=spec->>'original_id')) THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
   ass:=pg_catalog.jsonb_build_object('owner_id',c#>>'{scope,owner_id}','run_id',CASE WHEN role='owner_id' THEN NULL ELSE c#>>'{scope,run_id}' END,'market_epoch',CASE WHEN role IN('owner_id','run_id') THEN NULL ELSE c#>>'{scope,market_epoch}' END,'packet_reservation_id',NULL);
   IF spec->'association' IS DISTINCT FROM ass THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
   idrow:=pg_catalog.jsonb_build_object('original_id',spec->>'original_id','identity_role',role,'association',ass,'original_allocation_sha256',ch,'first_native_sequence',seq::text);
   IF EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(ids) x WHERE x->>'original_id'=spec->>'original_id') THEN RAISE EXCEPTION 'b2_identity_conflict'; END IF;
   IF EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities WHERE original_id=spec->>'original_id') THEN RAISE EXCEPTION 'b2_identity_conflict'; END IF;
   ids:=ids||pg_catalog.jsonb_build_array(idrow);
  END LOOP;
  v:=g->'initial_acquisition_spec';
  IF NOT vn_jupiter_b2_allocation_research_v3._keys(v,ARRAY['registration_id','acquisition_epoch','predecessor_epoch','recorder_principal_binding_id','reader_principal_binding_id','issuer_binding_id','recorder_package_sha256','reader_package_sha256','policies','endpoint_bindings']) OR v->'predecessor_epoch' IS DISTINCT FROM 'null'::jsonb OR v->'policies' IS DISTINCT FROM p->'policies' OR v->'recorder_package_sha256' IS DISTINCT FROM p#>'{policies,recorder_package_sha256}' OR v->'reader_package_sha256' IS DISTINCT FROM p#>'{policies,reader_package_sha256}' THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
  FOREACH role IN ARRAY ARRAY['registration_id','acquisition_epoch','issuer_binding_id'] LOOP
   IF NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(g->'identity_specs') x WHERE x->>'identity_role'=role AND x->>'original_id'=v->>role) THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
  END LOOP;
  IF NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings z WHERE z.scope_wire=sw AND z.binding_id=v->>'recorder_principal_binding_id' AND 'reserve'=ANY(z.capabilities)) OR NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings z WHERE z.scope_wire=sw AND z.binding_id=v->>'reader_principal_binding_id' AND 'register_reader_epoch'=ANY(z.capabilities)) THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
  IF pg_catalog.jsonb_typeof(v->'endpoint_bindings') IS DISTINCT FROM 'array' OR pg_catalog.jsonb_array_length(v->'endpoint_bindings')<>2 THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
  FOR spec IN SELECT value FROM pg_catalog.jsonb_array_elements(v->'endpoint_bindings') WITH ORDINALITY z(value,ord) LOOP
   IF NOT vn_jupiter_b2_allocation_research_v3._keys(spec,ARRAY['provider_family','endpoint_binding_id']) OR spec->>'provider_family' NOT IN('jupiter-price-v3','solana-rpc') OR NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(g->'identity_specs') x WHERE x->>'identity_role'='endpoint_binding_id' AND x->>'original_id'=spec->>'endpoint_binding_id') THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
  END LOOP;
  IF v#>>'{endpoint_bindings,0,provider_family}' IS DISTINCT FROM 'jupiter-price-v3' OR v#>>'{endpoint_bindings,1,provider_family}' IS DISTINCT FROM 'solana-rpc' OR v#>>'{endpoint_bindings,0,endpoint_binding_id}' IS NOT DISTINCT FROM v#>>'{endpoint_bindings,1,endpoint_binding_id}' THEN RAISE EXCEPTION 'b2_genesis_refused'; END IF;
  epoch:=(g->'initial_acquisition_spec')||pg_catalog.jsonb_build_object('scope',c->'scope','ordinal','1','original_command_sha256',ch);
  terminal:=pg_catalog.jsonb_build_object('format','ga-jupiter-b2-terminal-allocation-research-v3-v1','scope',c->'scope','installation_id',p->>'installation_id','stop_action_id',g->>'terminal_stop_action_id','allocation_command_sha256',ch,'first_native_sequence',seq::text);
  facts:=pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_genesis_input',p->>'installation_id',a->>'genesis_wire'),vn_jupiter_b2_allocation_research_v3._pin('native_epoch_registration',epoch->>'registration_id',vn_jupiter_b2_allocation_research_v3._c14n(epoch)),vn_jupiter_b2_allocation_research_v3._pin('native_terminal_allocation',g->>'terminal_stop_action_id',vn_jupiter_b2_allocation_research_v3._c14n(terminal)));
  deps:=vn_jupiter_b2_allocation_research_v3._deps(facts);
  expected_body:=(c->'body') - ARRAY['scope','policies'];
 ELSIF c->>'action_kind'='fence_acquire' THEN
  -- Narrow next slice: only the original paused installed epoch, no existing
  -- fence, no packet/pending state, and one exact scoped recorder binding.
  IF seq<>2 OR h->>'source_mode' IS DISTINCT FROM 'paused' OR h->'active_fence_id' IS DISTINCT FROM 'null'::jsonb OR h->>'fence_revision' IS DISTINCT FROM '0' OR h->>'active_acquisition_epoch' IS DISTINCT FROM g#>>'{initial_acquisition_spec,acquisition_epoch}' OR a->>'binding_id' IS DISTINCT FROM g#>>'{initial_acquisition_spec,recorder_principal_binding_id}' OR pg_catalog.jsonb_typeof(c#>'{body,fence_id}') IS DISTINCT FROM 'string' OR (c#>>'{body,fence_id}' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true OR c->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('fence_id',c#>>'{body,fence_id}','acquisition_epoch',h->>'active_acquisition_epoch','holder_principal_binding_id',a->>'binding_id','requested_duration_us','60000000') THEN RAISE EXCEPTION 'b2_fence_acquire_refused'; END IF;
  IF c->>'action_id' IS NOT DISTINCT FROM c#>>'{body,fence_id}' OR EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities i WHERE i.original_id IN(c->>'action_id',c#>>'{body,fence_id}')) THEN RAISE EXCEPTION 'b2_identity_conflict'; END IF;
  SELECT * INTO prior FROM vn_jupiter_b2_allocation_research_v3.original_operations z WHERE z.scope_wire=sw AND z.native_sequence=1 AND z.action_kind='installation' AND z.finalized;
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_installation_refused'; END IF;
  prior_reply:=vn_jupiter_b2_allocation_research_v3._reply(c->'scope',prior.action_id,prior.command_sha256,false,NULL)::jsonb;
  PERFORM 1 FROM vn_jupiter_b2_allocation_research_v3.journal_entries j WHERE j.scope_wire=sw AND j.native_sequence=1 AND j.journal_sha256=h->>'native_head_sha256';
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_stale_head'; END IF;
  prior_result:=(prior_reply->>'original_result_wire')::jsonb;
  issued:=(vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint;
  IF issued<0 THEN RAISE EXCEPTION 'b2_fence_clock_refused'; END IF;
  expires:=issued+60000000;
  fence:=pg_catalog.jsonb_build_object('fence_id',c#>>'{body,fence_id}','scope',c->'scope','holder_principal_binding_id',a->>'binding_id','acquisition_epoch',h->>'active_acquisition_epoch','revision','1','issued_at_us',issued::text,'expires_at_us',expires::text,'original_command_sha256',ch,'native_sequence','2');
  ass:=(c->'scope')||'{"packet_reservation_id":null}'::jsonb;
  FOREACH role IN ARRAY ARRAY['native_operation_id','fence_id'] LOOP
   ids:=ids||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('original_id',CASE WHEN role='fence_id' THEN c#>>'{body,fence_id}' ELSE c->>'action_id' END,'identity_role',role,'association',ass,'original_allocation_sha256',ch,'first_native_sequence','2'));
  END LOOP;
  facts:=pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_fence_record',fence->>'fence_id',vn_jupiter_b2_allocation_research_v3._c14n(fence)));
  deps:=vn_jupiter_b2_allocation_research_v3._deps((prior_result->'dependencies')||pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_command',prior.action_id,prior.command_wire))||facts);
  expected_body:=pg_catalog.jsonb_build_object('original_fence_record',fence);
 ELSIF c->>'action_kind'='source_resume' THEN
  IF seq<>3 OR h->>'source_mode' IS DISTINCT FROM 'paused'
   OR pg_catalog.jsonb_typeof(h->'active_fence_id') IS DISTINCT FROM 'string'
   OR h->>'fence_revision' IS DISTINCT FROM '1'
   OR h->>'active_acquisition_epoch' IS DISTINCT FROM g#>>'{initial_acquisition_spec,acquisition_epoch}'
   OR c->'body' IS DISTINCT FROM '{"expected_control_sha256":null,"expected_mode":"paused"}'::jsonb
  THEN RAISE EXCEPTION 'b2_Resume_refused'; END IF;
  IF EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities i WHERE i.original_id=c->>'action_id') THEN RAISE EXCEPTION 'b2_identity_conflict'; END IF;
  SELECT * INTO prior FROM vn_jupiter_b2_allocation_research_v3.original_operations z
   WHERE z.scope_wire=sw AND z.native_sequence=2 AND z.action_kind='fence_acquire' AND z.finalized;
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_Resume_refused'; END IF;
  prior_reply:=vn_jupiter_b2_allocation_research_v3._reply(c->'scope',prior.action_id,prior.command_sha256,false,NULL)::jsonb;
  PERFORM 1 FROM vn_jupiter_b2_allocation_research_v3.journal_entries j WHERE j.scope_wire=sw AND j.native_sequence=2 AND j.journal_sha256=h->>'native_head_sha256';
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_stale_head'; END IF;
  prior_result:=(prior_reply->>'original_result_wire')::jsonb;
  fence:=prior_result#>'{result_body,original_fence_record}';
  IF fence->'fence_id' IS DISTINCT FROM h->'active_fence_id'
   OR fence->'revision' IS DISTINCT FROM h->'fence_revision'
   OR fence->'acquisition_epoch' IS DISTINCT FROM h->'active_acquisition_epoch'
   OR fence->>'holder_principal_binding_id' IS DISTINCT FROM g#>>'{initial_acquisition_spec,recorder_principal_binding_id}'
  THEN RAISE EXCEPTION 'b2_Resume_refused'; END IF;
  issued:=(fence->>'issued_at_us')::bigint;
  expires:=(fence->>'expires_at_us')::bigint;
  ids:=pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('original_id',c->>'action_id','identity_role','control_action_id','association',(c->'scope')||'{"packet_reservation_id":null}'::jsonb,'original_allocation_sha256',ch,'first_native_sequence','3'));
  deps:=vn_jupiter_b2_allocation_research_v3._deps((prior_result->'dependencies')||pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_command',prior.action_id,prior.command_wire)));
  expected_body:='{"previous_mode":"paused","resulting_mode":"open","previous_control_sha256":null,"resulting_fence_revision":"1"}'::jsonb;
 ELSIF c->>'action_kind'='fence_renew' THEN
  -- Position sixteen reaches _budget as an otherwise valid ordinary attempt.
  IF seq NOT BETWEEN 4 AND 16 OR h->>'source_mode' IS DISTINCT FROM 'open'
   OR pg_catalog.jsonb_typeof(h->'active_fence_id') IS DISTINCT FROM 'string' OR h->>'fence_revision' IS DISTINCT FROM (seq-3)::text
   OR h->>'active_acquisition_epoch' IS DISTINCT FROM g#>>'{initial_acquisition_spec,acquisition_epoch}'
   OR (a->'handoff'='null'::jsonb AND a->>'binding_id' IS DISTINCT FROM g#>>'{initial_acquisition_spec,recorder_principal_binding_id}')
   OR c->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('fence_id',h->>'active_fence_id','expected_revision',h->>'fence_revision','requested_duration_us','60000000')
  THEN RAISE EXCEPTION 'b2_fence_renew_refused'; END IF;
  IF EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities i WHERE i.original_id=c->>'action_id') THEN RAISE EXCEPTION 'b2_identity_conflict'; END IF;
  SELECT * INTO prior FROM vn_jupiter_b2_allocation_research_v3.original_operations z
   WHERE z.scope_wire=sw AND z.native_sequence=seq-1 AND z.finalized
   AND z.action_kind=CASE WHEN seq=4 THEN 'source_resume' ELSE 'fence_renew' END;
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_fence_renew_refused'; END IF;
  prior_reply:=vn_jupiter_b2_allocation_research_v3._reply(c->'scope',prior.action_id,prior.command_sha256,false,NULL)::jsonb;
  PERFORM 1 FROM vn_jupiter_b2_allocation_research_v3.journal_entries j WHERE j.scope_wire=sw AND j.native_sequence=seq-1 AND j.journal_sha256=h->>'native_head_sha256';
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_stale_head'; END IF;
  prior_result:=(prior_reply->>'original_result_wire')::jsonb;
  SELECT * INTO oldop FROM vn_jupiter_b2_allocation_research_v3.original_operations z
   WHERE z.scope_wire=sw AND z.native_sequence=1 AND z.action_kind='installation' AND z.finalized;
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_installation_refused'; END IF;
  next_fence_record:=prior_result#>'{result_body,original_fence_record}';
  SELECT pg_catalog.jsonb_agg(value) INTO deps FROM pg_catalog.jsonb_array_elements(prior_result->'dependencies')
   WHERE (value->>'semantic_kind'<>'native_command' OR value->>'original_id'=oldop.action_id)
   AND CASE WHEN seq=4 OR value->>'semantic_kind'<>'native_fence_record' THEN true
     ELSE value->>'original_wire'=vn_jupiter_b2_allocation_research_v3._c14n(next_fence_record) END;
  SELECT (value->>'original_wire')::jsonb INTO fence FROM pg_catalog.jsonb_array_elements(deps)
   WHERE value->>'semantic_kind'='native_fence_record';
  IF NOT FOUND OR fence->'fence_id' IS DISTINCT FROM h->'active_fence_id'
   OR fence->'revision' IS DISTINCT FROM h->'fence_revision'
   OR fence->'acquisition_epoch' IS DISTINCT FROM h->'active_acquisition_epoch'
  THEN RAISE EXCEPTION 'b2_fence_renew_refused'; END IF;
  IF a->'handoff' IS DISTINCT FROM 'null'::jsonb THEN
   IF NOT vn_jupiter_b2_allocation_research_v3._handoff_allows_renew(a->'handoff',seq,ch,a->>'binding_id',fence,h->>'native_head_sha256')
   THEN RAISE EXCEPTION 'b2_fence_renew_refused'; END IF;
  ELSIF fence->>'holder_principal_binding_id' IS DISTINCT FROM a->>'binding_id'
  THEN RAISE EXCEPTION 'b2_fence_renew_refused'; END IF;
  previous_expiry:=(fence->>'expires_at_us')::bigint;
  previous_commit_us:=((prior_reply->>'original_receipt_wire')::jsonb#>>'{commit_processing_observation,observed_at_us}')::bigint;
  issued:=(vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint;
  IF issued<previous_commit_us OR issued>=previous_expiry
   OR (a->'handoff' IS DISTINCT FROM 'null'::jsonb AND issued<(a#>>'{handoff,observed_us}')::bigint)
  THEN RAISE EXCEPTION 'b2_fence_clock_refused'; END IF;
  expires:=issued+60000000;
  next_fence_record:=pg_catalog.jsonb_build_object('fence_id',fence->>'fence_id','scope',c->'scope',
   'holder_principal_binding_id',a->>'binding_id','acquisition_epoch',h->>'active_acquisition_epoch',
   'revision',(seq-2)::text,'issued_at_us',issued::text,'expires_at_us',expires::text,'original_command_sha256',ch,'native_sequence',seq::text);
  ids:=pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('original_id',c->>'action_id','identity_role','native_operation_id',
   'association',(c->'scope')||'{"packet_reservation_id":null}'::jsonb,'original_allocation_sha256',ch,'first_native_sequence',seq::text));
  facts:=pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_fence_record',fence->>'fence_id',vn_jupiter_b2_allocation_research_v3._c14n(next_fence_record)));
  deps:=vn_jupiter_b2_allocation_research_v3._deps(deps||pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_command',prior.action_id,prior.command_wire))||facts);
  expected_body:=pg_catalog.jsonb_build_object('original_fence_record',next_fence_record,
   'previous_fence_sha256',vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(fence)));
 ELSIF c->>'action_kind' IN('packet_reservation','capture_retention') THEN
  IF pg_catalog.jsonb_typeof(a->'handoff') IS DISTINCT FROM 'object'
   OR a#>>'{package,policies,a1_schema_sha256}' IS DISTINCT FROM '2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640'
   OR (NOT late_capture AND (h->>'source_mode' IS DISTINCT FROM 'open' OR h->>'fence_revision' IS DISTINCT FROM '2'
    OR seq IS DISTINCT FROM (CASE WHEN c->>'action_kind'='packet_reservation' THEN 5 ELSE 6 END)))
   OR (late_capture AND (((seq=6 AND h->>'source_mode'='open' AND h->>'fence_revision'='2')
    OR (seq=7 AND h->>'source_mode'='stopped' AND h->>'fence_revision'='3' AND h->'active_fence_id'='null'::jsonb)) IS DISTINCT FROM true
    OR h->>'active_acquisition_epoch' IS DISTINCT FROM g#>>'{initial_acquisition_spec,acquisition_epoch}'))
  THEN RAISE EXCEPTION 'b3_packet_head_refused'; END IF;
  SELECT * INTO prior FROM vn_jupiter_b2_allocation_research_v3.original_operations z
   WHERE z.scope_wire=sw AND z.native_sequence=seq-1 AND z.finalized
   AND z.action_kind=CASE seq WHEN 5 THEN 'fence_renew' WHEN 6 THEN 'packet_reservation' WHEN 7 THEN 'source_stop' END;
  IF NOT FOUND THEN RAISE EXCEPTION 'b3_packet_head_refused'; END IF;
  prior_reply:=vn_jupiter_b2_allocation_research_v3._reply(c->'scope',prior.action_id,prior.command_sha256,false,NULL)::jsonb;
  PERFORM 1 FROM vn_jupiter_b2_allocation_research_v3.journal_entries j WHERE j.scope_wire=sw AND j.native_sequence=seq-1 AND j.journal_sha256=h->>'native_head_sha256';
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_stale_head'; END IF;
  SELECT z.result_wire::jsonb#>'{result_body,original_fence_record}' INTO fence
  FROM vn_jupiter_b2_allocation_research_v3.original_operations z WHERE z.scope_wire=sw AND z.native_sequence=4 AND z.action_kind='fence_renew' AND z.finalized;
  IF NOT FOUND THEN RAISE EXCEPTION 'b3_packet_head_refused'; END IF;
  IF late_capture THEN
   IF seq=6 AND h->'active_fence_id' IS DISTINCT FROM fence->'fence_id'
   THEN RAISE EXCEPTION 'b3_packet_head_refused'; END IF;
   SELECT z.command_wire,j.journal_sha256 INTO reserve_wire,reserve_head
    FROM vn_jupiter_b2_allocation_research_v3.original_operations z
    JOIN vn_jupiter_b2_allocation_research_v3.journal_entries j USING(scope_wire,native_sequence,action_id)
    WHERE z.scope_wire=sw AND z.native_sequence=5 AND z.action_kind='packet_reservation' AND z.finalized;
   IF NOT FOUND OR c->'expected_head' IS DISTINCT FROM pg_catalog.jsonb_build_object(
    'native_sequence','5','native_head_sha256',reserve_head,'previous_seal_sha256',NULL)
   THEN RAISE EXCEPTION 'b3_capture_ancestor_refused'; END IF;
  END IF;
  packet_plan:=vn_jupiter_b2_allocation_research_v3._packet_plan(c,a,seq,a->>'binding_id',fence,
   CASE WHEN late_capture THEN reserve_wire ELSE prior.command_wire END);
  ids:=packet_plan->'ids'; deps:=packet_plan->'dependencies'; expected_body:=packet_plan->'body';
  IF EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(ids) v
    JOIN vn_jupiter_b2_allocation_research_v3.identities i ON i.original_id=v.value->>'original_id')
  THEN RAISE EXCEPTION 'b2_identity_conflict'; END IF;
  issued:=((prior_reply->>'original_receipt_wire')::jsonb#>>'{commit_processing_observation,observed_at_us}')::bigint;
  expires:=(fence->>'expires_at_us')::bigint;
  IF NOT late_capture AND (vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint NOT BETWEEN issued AND expires-1
  THEN RAISE EXCEPTION 'b2_fence_clock_refused'; END IF;
 ELSE
  packet_stop:=pg_catalog.jsonb_typeof(a->'handoff')='object' AND seq IN(6,7)
   AND EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.original_operations z WHERE z.scope_wire=sw AND z.native_sequence=seq-1 AND z.finalized
     AND z.action_kind=CASE WHEN seq=6 THEN 'packet_reservation' ELSE 'capture_retention' END);
  previous_mode:=CASE WHEN seq>=4 THEN 'open' ELSE 'paused' END;
  IF seq NOT BETWEEN 2 AND 16 OR h->>'source_mode' IS DISTINCT FROM previous_mode
   OR ((a->>'terminal_retirement')::boolean AND seq<>4)
   OR (seq=2 AND (h->'active_fence_id' IS DISTINCT FROM 'null'::jsonb OR h->>'fence_revision' IS DISTINCT FROM '0'))
   OR (seq>=3 AND pg_catalog.jsonb_typeof(h->'active_fence_id') IS DISTINCT FROM 'string')
   OR (seq IN(3,4) AND h->>'fence_revision' IS DISTINCT FROM '1')
   OR (seq>=5 AND h->>'fence_revision' IS DISTINCT FROM (CASE WHEN packet_stop THEN '2' ELSE (seq-3)::text END))
   OR c->>'action_id' IS DISTINCT FROM g->>'terminal_stop_action_id'
  THEN RAISE EXCEPTION 'b2_Stop_refused'; END IF;
  -- Resolve the exact committed prefix. Stop does not require current recorder
  -- authority or a live hold, including from the newly reachable open state.
  SELECT * INTO oldop FROM vn_jupiter_b2_allocation_research_v3.original_operations WHERE scope_wire=sw AND native_sequence=1 AND action_kind='installation' AND finalized;
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_installation_refused'; END IF;
  IF (oldop.command_wire::jsonb)->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('installation_id',p->>'installation_id','scope',c->'scope','policies',p->'policies','catalog_manifest_sha256',p->>'catalog_manifest_sha256','actor_manifest_sha256',p->>'actor_manifest_sha256','genesis_registry_sha256',vn_jupiter_b2_allocation_research_v3._sha(a->>'genesis_wire')) THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
  SELECT * INTO prior FROM vn_jupiter_b2_allocation_research_v3.original_operations z
   WHERE z.scope_wire=sw AND z.native_sequence=seq-1 AND z.finalized
   AND z.action_kind=CASE WHEN packet_stop THEN CASE WHEN seq=6 THEN 'packet_reservation' ELSE 'capture_retention' END ELSE CASE seq WHEN 2 THEN 'installation' WHEN 3 THEN 'fence_acquire' WHEN 4 THEN 'source_resume' ELSE 'fence_renew' END END;
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_Stop_refused'; END IF;
  prior_reply:=vn_jupiter_b2_allocation_research_v3._reply(c->'scope',prior.action_id,prior.command_sha256,false,ch)::jsonb;
  prior_result:=(prior_reply->>'original_result_wire')::jsonb;
  PERFORM 1 FROM vn_jupiter_b2_allocation_research_v3.journal_entries j WHERE j.scope_wire=sw AND j.native_sequence=seq-1 AND j.journal_sha256=h->>'native_head_sha256';
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_stale_head'; END IF;
  deps:=prior_result->'dependencies';
  IF seq=4 THEN
   prior_control_sha:=prior.command_sha256;
   SELECT pg_catalog.jsonb_agg(value) INTO deps FROM pg_catalog.jsonb_array_elements(deps)
    WHERE value->>'semantic_kind'<>'native_command' OR value->>'original_id'=oldop.action_id;
  ELSIF seq>=5 THEN
   -- The previous Renew may pin another Renew as its prior head. Resolve
   -- Resume separately and retain only the current version for this Stop.
   SELECT z.action_id,z.command_wire,z.command_sha256 INTO control_original
    FROM vn_jupiter_b2_allocation_research_v3.original_operations z
    WHERE z.scope_wire=sw AND z.native_sequence=3 AND z.action_kind='source_resume' AND z.finalized;
   IF NOT FOUND THEN RAISE EXCEPTION 'b2_Stop_refused'; END IF;
   prior_control_sha:=control_original.command_sha256;
   IF packet_stop THEN
    SELECT * INTO packet_renew FROM vn_jupiter_b2_allocation_research_v3.original_operations z
     WHERE z.scope_wire=sw AND z.native_sequence=4 AND z.action_kind='fence_renew' AND z.finalized;
    IF NOT FOUND THEN RAISE EXCEPTION 'b2_Stop_refused'; END IF;
    prior_result:=packet_renew.result_wire::jsonb;
    deps:=prior_result->'dependencies';
   END IF;
   next_fence_record:=prior_result#>'{result_body,original_fence_record}';
   SELECT pg_catalog.jsonb_agg(value) INTO deps FROM pg_catalog.jsonb_array_elements(deps)
    WHERE (value->>'semantic_kind'<>'native_command' OR value->>'original_id'=oldop.action_id)
    AND (value->>'semantic_kind'<>'native_fence_record' OR value->>'original_wire'=vn_jupiter_b2_allocation_research_v3._c14n(next_fence_record));
   deps:=deps||pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_command',control_original.action_id,control_original.command_wire));
  END IF;
  IF seq>=3 THEN
   SELECT (value->>'original_wire')::jsonb INTO fence FROM pg_catalog.jsonb_array_elements(deps)
    WHERE value->>'semantic_kind'='native_fence_record';
   IF NOT FOUND OR fence->'fence_id' IS DISTINCT FROM h->'active_fence_id'
    OR fence->'revision' IS DISTINCT FROM h->'fence_revision'
    OR fence->'acquisition_epoch' IS DISTINCT FROM h->'active_acquisition_epoch'
   THEN RAISE EXCEPTION 'b2_Stop_refused'; END IF;
  END IF;
  IF c->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('expected_control_sha256',prior_control_sha,'expected_mode',previous_mode) THEN RAISE EXCEPTION 'b2_Stop_refused'; END IF;
  IF packet_stop THEN
   deps:=vn_jupiter_b2_allocation_research_v3._deps(deps||pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_command',packet_renew.action_id,packet_renew.command_wire)));
  ELSE
   deps:=vn_jupiter_b2_allocation_research_v3._deps(deps||pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_command',prior.action_id,prior.command_wire)));
  END IF;
  expected_body:=pg_catalog.jsonb_build_object('previous_mode',previous_mode,'resulting_mode','stopped','previous_control_sha256',prior_control_sha,'resulting_fence_revision',((h->>'fence_revision')::bigint+1)::text);
 END IF;
 r:=pg_catalog.jsonb_build_object('format','ga-jupiter-b2-allocation-result-research-v3-v1','native_policy_sha256',c->>'native_policy_sha256','scope',c->'scope','action_id',c->>'action_id','action_kind',c->>'action_kind','native_sequence',seq::text,'original_command_sha256',ch,'dependencies',deps,'result_body',expected_body,'limits',vn_jupiter_b2_allocation_research_v3._limits()); rw:=vn_jupiter_b2_allocation_research_v3._c14n(r);
 IF pg_catalog.octet_length(rw)>131072 OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(facts) x WHERE (x->>'wire_bytes')::bigint>CASE x->>'semantic_kind' WHEN 'native_genesis_input' THEN 8192 WHEN 'native_epoch_registration' THEN 2048 WHEN 'native_terminal_allocation' THEN 1024 WHEN 'native_fence_record' THEN 1024 ELSE 0 END) THEN RAISE EXCEPTION 'b2_wire_bound'; END IF;
 cost:=vn_jupiter_b2_allocation_research_v3._cost(c,r,ids,facts);
 chk:=vn_jupiter_b2_allocation_research_v3._budget(sw,c->>'action_kind',cost);
 IF register_stop_intent THEN
  RETURN vn_jupiter_b2_allocation_research_v3._stage_stop_intent(sw,c,wire,a);
 END IF;
 -- Full future finalization upper + every Stop component is checked BEFORE DML.
 FOR v IN SELECT value FROM pg_catalog.jsonb_array_elements(ids) ORDER BY value->>'original_id' COLLATE "C" LOOP
  INSERT INTO vn_jupiter_b2_allocation_research_v3.identities VALUES(v->>'original_id',sw,vn_jupiter_b2_allocation_research_v3._c14n(v));
 END LOOP;
 FOR v IN SELECT value FROM pg_catalog.jsonb_array_elements(facts) ORDER BY value->>'semantic_kind' COLLATE "C",value->>'original_id' COLLATE "C",value->>'wire_sha256' COLLATE "C" LOOP
  INSERT INTO vn_jupiter_b2_allocation_research_v3.domain_facts VALUES(v->>'semantic_kind',v->>'original_id',v->>'wire_sha256',sw,seq,v->>'original_wire');
 END LOOP;
 FOR d IN SELECT value FROM pg_catalog.jsonb_array_elements(deps) LOOP
  ordinal:=ordinal+1;
  INSERT INTO vn_jupiter_b2_allocation_research_v3.dependency_associations VALUES(c->>'action_id',sw,ordinal,d->>'semantic_kind',d->>'original_id',d->>'wire_sha256',(d->>'wire_bytes')::bigint);
 END LOOP;
 final_obs:=vn_jupiter_b2_allocation_research_v3._clock();
 IF a->'credential_windows' IS DISTINCT FROM 'null'::jsonb
 THEN PERFORM vn_jupiter_b2_allocation_research_v3._check_credential_window(a->'credential_windows',(final_obs->>'observed_at_us')::bigint); END IF;
 IF c->>'action_kind' IN('fence_acquire','source_resume','fence_renew','packet_reservation','capture_retention')
  AND ((final_obs->>'observed_at_us')::bigint<issued OR (NOT late_capture AND (final_obs->>'observed_at_us')::bigint>=expires)
   OR (c->>'action_kind'='fence_renew' AND (final_obs->>'observed_at_us')::bigint>=previous_expiry))
 THEN RAISE EXCEPTION 'b2_fence_clock_refused'; END IF;
 INSERT INTO vn_jupiter_b2_allocation_research_v3.original_operations(action_id,scope_wire,action_kind,native_sequence,command_wire,command_sha256,result_wire,result_sha256,writer_xid8,writer_binding_id,final_function_observation) VALUES(c->>'action_id',sw,c->>'action_kind',seq,wire,ch,rw,vn_jupiter_b2_allocation_research_v3._sha(rw),pg_catalog.pg_current_xact_id(),a->>'binding_id',final_obs);
 RETURN vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_object('format','ga-jupiter-b2-provisional-research-v3-v1','native_policy_sha256',c->>'native_policy_sha256','scope',c->'scope','action_id',c->>'action_id','action_kind',c->>'action_kind','original_command_sha256',ch,'pending_commit',true,'limits',vn_jupiter_b2_allocation_research_v3._limits()));
EXCEPTION WHEN unique_violation THEN RAISE EXCEPTION 'b2_identity_conflict'; WHEN invalid_text_representation OR numeric_value_out_of_range THEN RAISE EXCEPTION 'b2_invalid_command';
END;
$b2$;

-- FUNCTION submit
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3.submit(wire pg_catalog.text)
RETURNS pg_catalog.text
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
BEGIN
 RETURN vn_jupiter_b2_allocation_research_v3._submit(wire,false);
END;
$b2$;

-- FUNCTION _commit_guard
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._commit_guard()
RETURNS pg_catalog.trigger
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $b2$
DECLARE o vn_jupiter_b2_allocation_research_v3.original_operations%ROWTYPE; c jsonb; r jsonb; a jsonb; p jsonb; g jsonb; st record; h jsonb; obs jsonb; rec jsonb; tw text; jw text; nexthead jsonb; ids jsonb; facts jsonb; cost jsonb; accounting jsonb; original_installation jsonb; fence jsonb; issued bigint; expires bigint; role text; expected_record jsonb; next_fence text; prior record; prior_reply jsonb; prior_result jsonb; expected_deps jsonb; expected_body jsonb; prior_control_sha text; previous_mode text; next_fence_record jsonb; previous_expiry bigint; previous_commit_us bigint; control_original record; packet_plan jsonb; packet_renew record; packet_stop boolean; late_capture boolean; reserve_wire text; reserve_head text;
BEGIN
 IF pg_catalog.btrim(pg_catalog.current_query(),E' \t\r\n\f'||pg_catalog.chr(11)) NOT IN('COMMIT','COMMIT;') THEN RAISE EXCEPTION 'b2_commit_form_refused'; END IF;
 SELECT * INTO o FROM vn_jupiter_b2_allocation_research_v3.original_operations WHERE action_id=NEW.action_id FOR UPDATE;
 IF NOT FOUND OR o.finalized OR o.writer_xid8<>pg_catalog.pg_current_xact_id() THEN RAISE EXCEPTION 'b2_commit_origin_refused'; END IF;
 c:=o.command_wire::jsonb; r:=o.result_wire::jsonb;
 late_capture:=(o.action_kind='capture_retention' AND pg_catalog.to_regprocedure('vn_jupiter_b2_allocation_research_v3._collection_authorization(text)') IS NOT NULL) IS TRUE;
 a:=vn_jupiter_b2_allocation_research_v3._auth(c->'scope',CASE o.action_kind WHEN 'installation' THEN 'install' WHEN 'fence_acquire' THEN 'fence_manage' WHEN 'fence_renew' THEN 'fence_manage' WHEN 'source_resume' THEN 'resume_scope' WHEN 'packet_reservation' THEN 'reserve' WHEN 'capture_retention' THEN 'reserve' ELSE 'control' END,NULL,CASE WHEN o.action_kind='source_stop' THEN o.command_sha256 END,NULL); p:=a->'package'; g:=(a->>'genesis_wire')::jsonb;
 IF o.action_kind='installation' THEN original_installation:=c;
 ELSE SELECT command_wire::jsonb INTO original_installation FROM vn_jupiter_b2_allocation_research_v3.original_operations WHERE scope_wire=o.scope_wire AND action_kind='installation' AND finalized;
 END IF;
 IF original_installation->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('installation_id',p->>'installation_id','scope',c->'scope','policies',p->'policies','catalog_manifest_sha256',p->>'catalog_manifest_sha256','actor_manifest_sha256',p->>'actor_manifest_sha256','genesis_registry_sha256',vn_jupiter_b2_allocation_research_v3._sha(a->>'genesis_wire')) THEN RAISE EXCEPTION 'b2_package_refused'; END IF;
 IF a->>'binding_id' IS DISTINCT FROM o.writer_binding_id OR pg_catalog.current_setting('synchronous_commit')<>'on' OR pg_catalog.current_setting('fsync')<>'on' THEN RAISE EXCEPTION 'b2_commit_origin_refused'; END IF;
 SELECT * INTO st FROM vn_jupiter_b2_allocation_research_v3.scope_state WHERE scope_wire=o.scope_wire FOR UPDATE; h:=st.head_wire::jsonb;
 IF o.action_kind='source_stop' AND pg_catalog.jsonb_typeof(a->'handoff')='object' THEN
  PERFORM vn_jupiter_b2_allocation_research_v3._require_exact_stop_intent(o.scope_wire,c,o.command_wire,a);
 END IF;
 IF (a->>'handoff_profile')::boolean AND o.action_kind<>'source_stop'
  AND NOT (late_capture AND h->>'source_mode'='stopped')
 THEN PERFORM vn_jupiter_b2_allocation_research_v3._require_no_stop_intent(o.scope_wire); END IF;
 IF NOT late_capture AND c->'expected_head' IS DISTINCT FROM pg_catalog.jsonb_build_object('native_sequence',h->>'native_sequence','native_head_sha256',h->>'native_head_sha256','previous_seal_sha256',NULL) THEN RAISE EXCEPTION 'b2_stale_head'; END IF;
 SELECT COALESCE(pg_catalog.jsonb_agg(record_wire::jsonb),'[]') INTO ids FROM vn_jupiter_b2_allocation_research_v3.identities WHERE scope_wire=o.scope_wire AND record_wire::jsonb->>'original_allocation_sha256'=o.command_sha256;
 SELECT COALESCE(pg_catalog.jsonb_agg(vn_jupiter_b2_allocation_research_v3._pin(semantic_kind,original_id,original_wire)),'[]') INTO facts FROM vn_jupiter_b2_allocation_research_v3.domain_facts WHERE scope_wire=o.scope_wire AND native_sequence=o.native_sequence;
 cost:=vn_jupiter_b2_allocation_research_v3._cost(c,r,ids,facts); accounting:=vn_jupiter_b2_allocation_research_v3._budget(o.scope_wire,o.action_kind,cost);
 IF o.action_kind='fence_acquire' THEN
  fence:=r#>'{result_body,original_fence_record}';
  IF o.native_sequence<>2 OR h->>'native_sequence' IS DISTINCT FROM '1' OR h->>'source_mode' IS DISTINCT FROM 'paused' OR h->'active_fence_id' IS DISTINCT FROM 'null'::jsonb OR h->>'fence_revision' IS DISTINCT FROM '0' OR h->>'active_acquisition_epoch' IS DISTINCT FROM g#>>'{initial_acquisition_spec,acquisition_epoch}' OR a->>'binding_id' IS DISTINCT FROM g#>>'{initial_acquisition_spec,recorder_principal_binding_id}' OR NOT vn_jupiter_b2_allocation_research_v3._keys(r->'result_body',ARRAY['original_fence_record']) OR pg_catalog.jsonb_typeof(fence->'issued_at_us') IS DISTINCT FROM 'string' OR (fence->>'issued_at_us' ~ '^(0|[1-9][0-9]{0,18})$') IS DISTINCT FROM true OR pg_catalog.jsonb_typeof(c#>'{body,fence_id}') IS DISTINCT FROM 'string' OR (c#>>'{body,fence_id}' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true OR c#>>'{body,fence_id}' IS NOT DISTINCT FROM o.action_id THEN RAISE EXCEPTION 'b2_fence_commit_refused'; END IF;
  IF c->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('fence_id',c#>>'{body,fence_id}','acquisition_epoch',h->>'active_acquisition_epoch','holder_principal_binding_id',a->>'binding_id','requested_duration_us','60000000') THEN RAISE EXCEPTION 'b2_fence_commit_refused'; END IF;
  issued:=(fence->>'issued_at_us')::bigint; expires:=issued+60000000;
  IF fence IS DISTINCT FROM pg_catalog.jsonb_build_object('fence_id',c#>>'{body,fence_id}','scope',c->'scope','holder_principal_binding_id',a->>'binding_id','acquisition_epoch',h->>'active_acquisition_epoch','revision','1','issued_at_us',issued::text,'expires_at_us',expires::text,'original_command_sha256',o.command_sha256,'native_sequence','2') OR pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(fence))>1024 OR facts IS DISTINCT FROM pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_fence_record',fence->>'fence_id',vn_jupiter_b2_allocation_research_v3._c14n(fence))) OR pg_catalog.jsonb_array_length(ids)<>2 THEN RAISE EXCEPTION 'b2_fence_commit_refused'; END IF;
  FOREACH role IN ARRAY ARRAY['native_operation_id','fence_id'] LOOP
   expected_record:=pg_catalog.jsonb_build_object('original_id',CASE WHEN role='fence_id' THEN c#>>'{body,fence_id}' ELSE o.action_id END,'identity_role',role,'association',(c->'scope')||'{"packet_reservation_id":null}'::jsonb,'original_allocation_sha256',o.command_sha256,'first_native_sequence','2');
   IF NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(ids) v WHERE v.value=expected_record) THEN RAISE EXCEPTION 'b2_fence_commit_refused'; END IF;
  END LOOP;
  next_fence:=fence->>'fence_id';
 ELSIF o.action_kind IN('packet_reservation','capture_retention') THEN
  IF c->>'native_policy_sha256' IS DISTINCT FROM (CASE WHEN late_capture THEN 'c468fa4a7fa8e9122a53abb19ed10d3c1d80f8024dfeefbb8596fef8f1c1f8be' ELSE '28b7df36ca970796b7729d29ca0fd0dde861edfdc09579afef160218a05ade51' END)
   OR (NOT late_capture AND (h->>'source_mode' IS DISTINCT FROM 'open' OR h->>'fence_revision' IS DISTINCT FROM '2'
    OR c->'expected_fence_id' IS DISTINCT FROM h->'active_fence_id' OR c->'expected_fence_revision' IS DISTINCT FROM h->'fence_revision'))
   OR (late_capture AND ((o.native_sequence=6 AND h->>'source_mode'='open' AND h->>'fence_revision'='2')
    OR (o.native_sequence=7 AND h->>'source_mode'='stopped' AND h->>'fence_revision'='3' AND h->'active_fence_id'='null'::jsonb)) IS DISTINCT FROM true)
   OR h->>'active_acquisition_epoch' IS DISTINCT FROM g#>>'{initial_acquisition_spec,acquisition_epoch}'
   OR o.native_sequence IS DISTINCT FROM (h->>'native_sequence')::bigint+1
   OR pg_catalog.octet_length(o.command_wire)>(CASE WHEN o.action_kind='capture_retention' THEN 1048576 ELSE 16384 END)
   OR pg_catalog.octet_length(o.result_wire)>131072
   OR vn_jupiter_b2_allocation_research_v3._c14n(c) IS DISTINCT FROM o.command_wire OR vn_jupiter_b2_allocation_research_v3._sha(o.command_wire) IS DISTINCT FROM o.command_sha256
   OR vn_jupiter_b2_allocation_research_v3._c14n(r) IS DISTINCT FROM o.result_wire OR vn_jupiter_b2_allocation_research_v3._sha(o.result_wire) IS DISTINCT FROM o.result_sha256
  THEN RAISE EXCEPTION 'b3_packet_commit_refused'; END IF;
  SELECT * INTO prior FROM vn_jupiter_b2_allocation_research_v3.original_operations z
   WHERE z.scope_wire=o.scope_wire AND z.native_sequence=o.native_sequence-1 AND z.finalized
   AND z.action_kind=CASE o.native_sequence WHEN 5 THEN 'fence_renew' WHEN 6 THEN 'packet_reservation' WHEN 7 THEN 'source_stop' END;
  IF NOT FOUND THEN RAISE EXCEPTION 'b3_packet_commit_refused'; END IF;
  prior_reply:=vn_jupiter_b2_allocation_research_v3._reply(c->'scope',prior.action_id,prior.command_sha256,false,NULL)::jsonb;
  IF NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.journal_entries j WHERE j.scope_wire=o.scope_wire AND j.native_sequence=prior.native_sequence AND j.journal_sha256=h->>'native_head_sha256')
  THEN RAISE EXCEPTION 'b2_stale_head'; END IF;
  SELECT z.result_wire::jsonb#>'{result_body,original_fence_record}' INTO fence
   FROM vn_jupiter_b2_allocation_research_v3.original_operations z WHERE z.scope_wire=o.scope_wire AND z.native_sequence=4 AND z.action_kind='fence_renew' AND z.finalized;
  IF NOT FOUND THEN RAISE EXCEPTION 'b3_packet_commit_refused'; END IF;
  IF late_capture THEN
   IF o.native_sequence=6 AND h->'active_fence_id' IS DISTINCT FROM fence->'fence_id'
   THEN RAISE EXCEPTION 'b3_packet_head_refused'; END IF;
   SELECT z.command_wire,j.journal_sha256 INTO reserve_wire,reserve_head
    FROM vn_jupiter_b2_allocation_research_v3.original_operations z
    JOIN vn_jupiter_b2_allocation_research_v3.journal_entries j USING(scope_wire,native_sequence,action_id)
    WHERE z.scope_wire=o.scope_wire AND z.native_sequence=5 AND z.action_kind='packet_reservation' AND z.finalized;
   IF NOT FOUND OR c->'expected_head' IS DISTINCT FROM pg_catalog.jsonb_build_object(
    'native_sequence','5','native_head_sha256',reserve_head,'previous_seal_sha256',NULL)
   THEN RAISE EXCEPTION 'b3_capture_ancestor_refused'; END IF;
  END IF;
  packet_plan:=vn_jupiter_b2_allocation_research_v3._packet_plan(c,a,o.native_sequence,o.writer_binding_id,fence,
   CASE WHEN late_capture THEN reserve_wire ELSE prior.command_wire END);
  IF (SELECT pg_catalog.jsonb_agg(value ORDER BY value->>'original_id' COLLATE "C") FROM pg_catalog.jsonb_array_elements(ids))
   IS DISTINCT FROM (SELECT pg_catalog.jsonb_agg(value ORDER BY value->>'original_id' COLLATE "C") FROM pg_catalog.jsonb_array_elements(packet_plan->'ids'))
   OR facts IS DISTINCT FROM '[]'::jsonb
   OR r IS DISTINCT FROM pg_catalog.jsonb_build_object('format','ga-jupiter-b2-allocation-result-research-v3-v1',
    'native_policy_sha256',c->>'native_policy_sha256','scope',c->'scope','action_id',o.action_id,'action_kind',o.action_kind,
    'native_sequence',o.native_sequence::text,'original_command_sha256',o.command_sha256,
    'dependencies',packet_plan->'dependencies','result_body',packet_plan->'body','limits',vn_jupiter_b2_allocation_research_v3._limits())
   OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(packet_plan->'dependencies') WITH ORDINALITY d(value,ord)
    WHERE NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.dependency_associations x
     WHERE x.scope_wire=o.scope_wire AND x.action_id=o.action_id AND x.ordinal=d.ord
      AND x.semantic_kind=d.value->>'semantic_kind' AND x.original_id=d.value->>'original_id'
      AND x.wire_sha256=d.value->>'wire_sha256' AND x.wire_bytes::text=d.value->>'wire_bytes'))
   OR (SELECT count(*) FROM vn_jupiter_b2_allocation_research_v3.dependency_associations x WHERE x.action_id=o.action_id)<>2
  THEN RAISE EXCEPTION 'b3_packet_commit_refused'; END IF;
  issued:=((prior_reply->>'original_receipt_wire')::jsonb#>>'{commit_processing_observation,observed_at_us}')::bigint;
  expires:=(fence->>'expires_at_us')::bigint;
  next_fence:=h->>'active_fence_id';
 ELSIF o.action_kind IN('source_resume','fence_renew','source_stop') THEN
  IF o.native_sequence IS DISTINCT FROM (h->>'native_sequence')::bigint+1
   OR h->>'active_acquisition_epoch' IS DISTINCT FROM g#>>'{initial_acquisition_spec,acquisition_epoch}'
   OR (o.action_kind<>'fence_renew' AND facts IS DISTINCT FROM '[]'::jsonb)
  THEN RAISE EXCEPTION 'b2_control_commit_refused'; END IF;
  SELECT * INTO prior FROM vn_jupiter_b2_allocation_research_v3.original_operations z
   WHERE z.scope_wire=o.scope_wire AND z.native_sequence=o.native_sequence-1 AND z.finalized;
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_control_commit_refused'; END IF;
  prior_reply:=vn_jupiter_b2_allocation_research_v3._reply(c->'scope',prior.action_id,prior.command_sha256,false,CASE WHEN o.action_kind='source_stop' THEN o.command_sha256 END)::jsonb;
  prior_result:=(prior_reply->>'original_result_wire')::jsonb;
  IF prior_reply#>>'{observed_head,native_head_sha256}' IS DISTINCT FROM h->>'native_head_sha256'
   OR NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.journal_entries j WHERE j.scope_wire=o.scope_wire AND j.native_sequence=prior.native_sequence AND j.journal_sha256=h->>'native_head_sha256')
  THEN RAISE EXCEPTION 'b2_stale_head'; END IF;
  expected_deps:=prior_result->'dependencies';
  IF o.action_kind='source_resume' THEN
   IF o.native_sequence<>3 OR prior.action_kind IS DISTINCT FROM 'fence_acquire'
    OR h->>'source_mode' IS DISTINCT FROM 'paused' OR h->>'fence_revision' IS DISTINCT FROM '1'
    OR c->'expected_fence_id' IS DISTINCT FROM h->'active_fence_id' OR c->'expected_fence_revision' IS DISTINCT FROM h->'fence_revision'
    OR c->'body' IS DISTINCT FROM '{"expected_control_sha256":null,"expected_mode":"paused"}'::jsonb
   THEN RAISE EXCEPTION 'b2_control_commit_refused'; END IF;
   expected_record:=pg_catalog.jsonb_build_object('original_id',o.action_id,'identity_role','control_action_id','association',(c->'scope')||'{"packet_reservation_id":null}'::jsonb,'original_allocation_sha256',o.command_sha256,'first_native_sequence','3');
   IF ids IS DISTINCT FROM pg_catalog.jsonb_build_array(expected_record) THEN RAISE EXCEPTION 'b2_control_commit_refused'; END IF;
   expected_body:='{"previous_mode":"paused","resulting_mode":"open","previous_control_sha256":null,"resulting_fence_revision":"1"}'::jsonb;
   next_fence:=h->>'active_fence_id';
  ELSIF o.action_kind='fence_renew' THEN
   IF o.native_sequence NOT BETWEEN 4 AND 15
    OR prior.action_kind IS DISTINCT FROM (CASE WHEN o.native_sequence=4 THEN 'source_resume' ELSE 'fence_renew' END)
    OR h->>'source_mode' IS DISTINCT FROM 'open' OR h->>'fence_revision' IS DISTINCT FROM (o.native_sequence-3)::text
    OR (a->'handoff'='null'::jsonb AND a->>'binding_id' IS DISTINCT FROM g#>>'{initial_acquisition_spec,recorder_principal_binding_id}')
    OR c->'expected_fence_id' IS DISTINCT FROM h->'active_fence_id' OR c->'expected_fence_revision' IS DISTINCT FROM h->'fence_revision'
    OR c->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('fence_id',h->>'active_fence_id','expected_revision',h->>'fence_revision','requested_duration_us','60000000')
   THEN RAISE EXCEPTION 'b2_fence_commit_refused'; END IF;
   expected_record:=pg_catalog.jsonb_build_object('original_id',o.action_id,'identity_role','native_operation_id',
    'association',(c->'scope')||'{"packet_reservation_id":null}'::jsonb,'original_allocation_sha256',o.command_sha256,'first_native_sequence',o.native_sequence::text);
   IF ids IS DISTINCT FROM pg_catalog.jsonb_build_array(expected_record) THEN RAISE EXCEPTION 'b2_fence_commit_refused'; END IF;
   next_fence_record:=prior_result#>'{result_body,original_fence_record}';
   SELECT pg_catalog.jsonb_agg(value) INTO expected_deps FROM pg_catalog.jsonb_array_elements(expected_deps)
    WHERE (value->>'semantic_kind'<>'native_command' OR value->>'original_id'=original_installation->>'action_id')
    AND CASE WHEN o.native_sequence=4 OR value->>'semantic_kind'<>'native_fence_record' THEN true
      ELSE value->>'original_wire'=vn_jupiter_b2_allocation_research_v3._c14n(next_fence_record) END;
   next_fence:=h->>'active_fence_id';
  ELSE
   packet_stop:=pg_catalog.jsonb_typeof(a->'handoff')='object' AND (
    (o.native_sequence=6 AND prior.action_kind='packet_reservation') OR (o.native_sequence=7 AND prior.action_kind='capture_retention'));
   previous_mode:=CASE WHEN o.native_sequence>=4 THEN 'open' ELSE 'paused' END;
   IF o.native_sequence NOT BETWEEN 2 AND 16
    OR ((a->>'terminal_retirement')::boolean AND o.native_sequence<>4)
    OR (NOT packet_stop AND prior.action_kind IS DISTINCT FROM (CASE o.native_sequence WHEN 2 THEN 'installation' WHEN 3 THEN 'fence_acquire' WHEN 4 THEN 'source_resume' ELSE 'fence_renew' END))
    OR h->>'source_mode' IS DISTINCT FROM previous_mode
    OR c->'expected_fence_id' IS DISTINCT FROM 'null'::jsonb OR c->'expected_fence_revision' IS DISTINCT FROM 'null'::jsonb
    OR o.action_id IS DISTINCT FROM g->>'terminal_stop_action_id' OR ids IS DISTINCT FROM '[]'::jsonb
    OR (o.native_sequence=2 AND (h->'active_fence_id' IS DISTINCT FROM 'null'::jsonb OR h->>'fence_revision' IS DISTINCT FROM '0'))
    OR (o.native_sequence IN(3,4) AND h->>'fence_revision' IS DISTINCT FROM '1')
    OR (o.native_sequence>=5 AND h->>'fence_revision' IS DISTINCT FROM (CASE WHEN packet_stop THEN '2' ELSE (o.native_sequence-3)::text END))
   THEN RAISE EXCEPTION 'b2_control_commit_refused'; END IF;
   IF o.native_sequence=4 THEN
    prior_control_sha:=prior.command_sha256;
    SELECT pg_catalog.jsonb_agg(value) INTO expected_deps FROM pg_catalog.jsonb_array_elements(expected_deps)
     WHERE value->>'semantic_kind'<>'native_command' OR value->>'original_id'=original_installation->>'action_id';
   ELSIF o.native_sequence>=5 THEN
    SELECT z.action_id,z.command_wire,z.command_sha256 INTO control_original
     FROM vn_jupiter_b2_allocation_research_v3.original_operations z
     WHERE z.scope_wire=o.scope_wire AND z.native_sequence=3 AND z.action_kind='source_resume' AND z.finalized;
    IF NOT FOUND THEN RAISE EXCEPTION 'b2_control_commit_refused'; END IF;
    prior_control_sha:=control_original.command_sha256;
    IF packet_stop THEN
     SELECT * INTO packet_renew FROM vn_jupiter_b2_allocation_research_v3.original_operations z
      WHERE z.scope_wire=o.scope_wire AND z.native_sequence=4 AND z.action_kind='fence_renew' AND z.finalized;
     IF NOT FOUND THEN RAISE EXCEPTION 'b2_control_commit_refused'; END IF;
     prior_result:=packet_renew.result_wire::jsonb;
     expected_deps:=prior_result->'dependencies';
    END IF;
    next_fence_record:=prior_result#>'{result_body,original_fence_record}';
    SELECT pg_catalog.jsonb_agg(value) INTO expected_deps FROM pg_catalog.jsonb_array_elements(expected_deps)
     WHERE (value->>'semantic_kind'<>'native_command' OR value->>'original_id'=original_installation->>'action_id')
     AND (value->>'semantic_kind'<>'native_fence_record' OR value->>'original_wire'=vn_jupiter_b2_allocation_research_v3._c14n(next_fence_record));
    expected_deps:=expected_deps||pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_command',control_original.action_id,control_original.command_wire));
   END IF;
   IF c->'body' IS DISTINCT FROM pg_catalog.jsonb_build_object('expected_control_sha256',prior_control_sha,'expected_mode',previous_mode) THEN RAISE EXCEPTION 'b2_control_commit_refused'; END IF;
   expected_body:=pg_catalog.jsonb_build_object('previous_mode',previous_mode,'resulting_mode','stopped','previous_control_sha256',prior_control_sha,'resulting_fence_revision',((h->>'fence_revision')::bigint+1)::text);
  END IF;
  IF o.native_sequence>=3 THEN
   SELECT (value->>'original_wire')::jsonb INTO fence FROM pg_catalog.jsonb_array_elements(expected_deps)
    WHERE value->>'semantic_kind'='native_fence_record';
   IF NOT FOUND OR fence->'fence_id' IS DISTINCT FROM h->'active_fence_id'
    OR fence->'revision' IS DISTINCT FROM h->'fence_revision'
    OR fence->'acquisition_epoch' IS DISTINCT FROM h->'active_acquisition_epoch'
    OR fence->>'holder_principal_binding_id' IS DISTINCT FROM
      (CASE WHEN a->'handoff' IS DISTINCT FROM 'null'::jsonb AND o.native_sequence>4
        THEN a#>>'{handoff,successor_binding,principal_binding_id}' ELSE g#>>'{initial_acquisition_spec,recorder_principal_binding_id}' END)
   THEN RAISE EXCEPTION 'b2_control_commit_refused'; END IF;
   IF o.action_kind='source_resume' THEN
    issued:=(fence->>'issued_at_us')::bigint;
    expires:=(fence->>'expires_at_us')::bigint;
   ELSIF o.action_kind='fence_renew' THEN
    next_fence_record:=r#>'{result_body,original_fence_record}';
    IF pg_catalog.jsonb_typeof(next_fence_record->'issued_at_us') IS DISTINCT FROM 'string'
     OR (next_fence_record->>'issued_at_us' ~ '^(0|[1-9][0-9]{0,18})$') IS DISTINCT FROM true
    THEN RAISE EXCEPTION 'b2_fence_commit_refused'; END IF;
    issued:=(next_fence_record->>'issued_at_us')::bigint;
    expires:=issued+60000000;
    previous_expiry:=(fence->>'expires_at_us')::bigint;
    previous_commit_us:=((prior_reply->>'original_receipt_wire')::jsonb#>>'{commit_processing_observation,observed_at_us}')::bigint;
    IF issued<previous_commit_us OR issued>=previous_expiry
     OR (a->'handoff' IS DISTINCT FROM 'null'::jsonb AND issued<(a#>>'{handoff,observed_us}')::bigint)
     OR next_fence_record IS DISTINCT FROM pg_catalog.jsonb_build_object('fence_id',fence->>'fence_id','scope',c->'scope',
      'holder_principal_binding_id',a->>'binding_id','acquisition_epoch',h->>'active_acquisition_epoch',
      'revision',(o.native_sequence-2)::text,'issued_at_us',issued::text,'expires_at_us',expires::text,'original_command_sha256',o.command_sha256,'native_sequence',o.native_sequence::text)
     OR pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(next_fence_record))>1024
     OR facts IS DISTINCT FROM pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_fence_record',fence->>'fence_id',vn_jupiter_b2_allocation_research_v3._c14n(next_fence_record)))
    THEN RAISE EXCEPTION 'b2_fence_commit_refused'; END IF;
    IF a->'handoff' IS DISTINCT FROM 'null'::jsonb THEN
     IF NOT vn_jupiter_b2_allocation_research_v3._handoff_allows_renew(a->'handoff',o.native_sequence,o.command_sha256,o.writer_binding_id,fence,h->>'native_head_sha256')
     THEN RAISE EXCEPTION 'b2_fence_commit_refused'; END IF;
    END IF;
    expected_body:=pg_catalog.jsonb_build_object('original_fence_record',next_fence_record,
     'previous_fence_sha256',vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(fence)));
    expected_deps:=expected_deps||facts;
   END IF;
  END IF;
  IF packet_stop THEN
   expected_deps:=vn_jupiter_b2_allocation_research_v3._deps(expected_deps||pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_command',packet_renew.action_id,packet_renew.command_wire)));
  ELSE
   expected_deps:=vn_jupiter_b2_allocation_research_v3._deps(expected_deps||pg_catalog.jsonb_build_array(vn_jupiter_b2_allocation_research_v3._pin('native_command',prior.action_id,prior.command_wire)));
  END IF;
  IF r->'dependencies' IS DISTINCT FROM expected_deps OR r->'result_body' IS DISTINCT FROM expected_body
   OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(expected_deps) WITH ORDINALITY d(value,ord)
    WHERE NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.dependency_associations x
     WHERE x.scope_wire=o.scope_wire AND x.action_id=o.action_id AND x.ordinal=d.ord
     AND x.semantic_kind=d.value->>'semantic_kind' AND x.original_id=d.value->>'original_id'
     AND x.wire_sha256=d.value->>'wire_sha256' AND x.wire_bytes::text=d.value->>'wire_bytes'))
   OR pg_catalog.jsonb_array_length(expected_deps) IS DISTINCT FROM
    (SELECT count(*) FROM vn_jupiter_b2_allocation_research_v3.dependency_associations x WHERE x.scope_wire=o.scope_wire AND x.action_id=o.action_id)
  THEN RAISE EXCEPTION 'b2_control_commit_refused'; END IF;
 END IF;
 obs:=vn_jupiter_b2_allocation_research_v3._clock();
 IF a->'credential_windows' IS DISTINCT FROM 'null'::jsonb
 THEN PERFORM vn_jupiter_b2_allocation_research_v3._check_credential_window(a->'credential_windows',(obs->>'observed_at_us')::bigint); END IF;
 IF (obs->>'observed_at_us')::bigint<(o.final_function_observation->>'observed_at_us')::bigint THEN RAISE EXCEPTION 'b2_clock_regression'; END IF;
 IF o.action_kind IN('fence_acquire','source_resume','fence_renew','packet_reservation','capture_retention')
  AND (issued>(o.final_function_observation->>'observed_at_us')::bigint OR (NOT late_capture AND (obs->>'observed_at_us')::bigint>=expires)
   OR (o.action_kind='fence_renew' AND (obs->>'observed_at_us')::bigint>=previous_expiry))
 THEN RAISE EXCEPTION 'b2_fence_clock_refused'; END IF;
 rec:=pg_catalog.jsonb_build_object('format','ga-jupiter-b2-allocation-receipt-research-v3-v1','native_policy_sha256',c->>'native_policy_sha256','scope',c->'scope','action_id',o.action_id,'action_kind',o.action_kind,'original_command_sha256',o.command_sha256,'result_sha256',o.result_sha256,'native_sequence',o.native_sequence::text,'previous_native_head_sha256',h->>'native_head_sha256','admission_observation',NULL,'final_function_observation',o.final_function_observation,'commit_processing_observation',obs,'native_package_sha256',p->>'native_package_sha256','catalog_manifest_sha256',a->>'effective_catalog_sha256','limits',vn_jupiter_b2_allocation_research_v3._limits()); tw:=vn_jupiter_b2_allocation_research_v3._c14n(rec);
 jw:=vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_object('native_sequence',o.native_sequence::text,'action_id',o.action_id,'action_kind',o.action_kind,'original_command_sha256',o.command_sha256,'original_result_sha256',o.result_sha256,'original_receipt_sha256',vn_jupiter_b2_allocation_research_v3._sha(tw),'previous_native_head_sha256',h->>'native_head_sha256'));
 nexthead:=pg_catalog.jsonb_build_object('scope',c->'scope','native_sequence',o.native_sequence::text,'native_head_sha256',vn_jupiter_b2_allocation_research_v3._sha(jw),'active_acquisition_epoch',g#>>'{initial_acquisition_spec,acquisition_epoch}','active_fence_id',next_fence,'fence_revision',CASE o.action_kind WHEN 'installation' THEN '0' WHEN 'source_resume' THEN h->>'fence_revision' WHEN 'packet_reservation' THEN h->>'fence_revision' WHEN 'capture_retention' THEN h->>'fence_revision' ELSE ((h->>'fence_revision')::bigint+1)::text END,'source_mode',CASE o.action_kind WHEN 'source_stop' THEN 'stopped' WHEN 'source_resume' THEN 'open' WHEN 'fence_renew' THEN 'open' WHEN 'packet_reservation' THEN 'open' WHEN 'capture_retention' THEN h->>'source_mode' ELSE 'paused' END,'last_admission_sha256',NULL,'last_ingest_sequence','0','last_availability_sha256',NULL,'previous_seal_sha256',NULL);
 IF pg_catalog.octet_length(tw)>4096 OR pg_catalog.octet_length(jw)>1024 OR pg_catalog.octet_length(vn_jupiter_b2_allocation_research_v3._c14n(nexthead))>2048 THEN RAISE EXCEPTION 'b2_wire_bound'; END IF;
 UPDATE vn_jupiter_b2_allocation_research_v3.original_operations SET receipt_wire=tw,receipt_sha256=vn_jupiter_b2_allocation_research_v3._sha(tw),finalized=true WHERE action_id=o.action_id;
 INSERT INTO vn_jupiter_b2_allocation_research_v3.journal_entries VALUES(o.scope_wire,o.native_sequence,o.action_id,jw,vn_jupiter_b2_allocation_research_v3._sha(jw));
 UPDATE vn_jupiter_b2_allocation_research_v3.scope_state SET head_wire=vn_jupiter_b2_allocation_research_v3._c14n(nexthead),accounting_wire=vn_jupiter_b2_allocation_research_v3._c14n(accounting) WHERE scope_wire=o.scope_wire;
 RETURN NEW;
END;
$b2$;

-- TRIGGER committed_original_guard
CREATE CONSTRAINT TRIGGER committed_original_guard AFTER INSERT ON vn_jupiter_b2_allocation_research_v3.original_operations
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION vn_jupiter_b2_allocation_research_v3._commit_guard();

-- REVOKES
REVOKE ALL ON FUNCTION vn_jupiter_b2_fixture_anchor._lock_inputs(pg_catalog.text,pg_catalog.bool) FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA vn_jupiter_b2_allocation_research_v3 FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_jupiter_b2_allocation_research_v3 FROM PUBLIC;
