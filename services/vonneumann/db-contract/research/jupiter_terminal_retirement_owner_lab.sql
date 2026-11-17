-- Private owner-separated terminal slice for the fixed SCRAM laboratory.
BEGIN;
SET LOCAL ROLE vn_jupiter_b2_anchor_owner;
ALTER TABLE vn_jupiter_b2_fixture_anchor.package_inputs ADD COLUMN retirement_permit_wire pg_catalog.text CHECK (pg_catalog.octet_length(retirement_permit_wire)<=8192);
RESET ROLE;
SET LOCAL ROLE vn_jupiter_b2_sealed_owner;

-- FUNCTION _terminal_retirement_context
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._terminal_retirement_context(requested_scope pg_catalog.text, permit_wire pg_catalog.text, after_disable pg_catalog.bool)
RETURNS pg_catalog.text
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $terminal$
DECLARE permit jsonb; command jsonb; package jsonb; genesis jsonb; held_catalog jsonb; actor_manifest jsonb; installed_body jsonb;
        inputs vn_jupiter_b2_fixture_anchor.package_inputs%ROWTYPE;
        head jsonb; accounting jsonb; expected_profile record; binding record; role_index bigint;
        writer_ids jsonb:='[]'; writers jsonb:='[]'; observed timestamptz; issuer_deadline timestamptz;
        observed_us bigint; deadline_profile record; survivor jsonb; survivor_login_until timestamptz;
        field text; issued_us bigint; not_before_us bigint; cutoff_us bigint; login_until_us bigint;
BEGIN
 IF session_user IS DISTINCT FROM 'vn_jupiter_b2_actor_issuer'
  OR system_user IS DISTINCT FROM ('scram-sha-256:'||session_user::text)
  OR pg_catalog.inet_client_addr() IS NULL OR after_disable IS NULL
 THEN RAISE EXCEPTION 'b2_terminal_issuer_refused' USING ERRCODE='42501'; END IF;
 IF permit_wire IS NULL OR pg_catalog.octet_length(permit_wire)>8192 THEN RAISE EXCEPTION 'b2_terminal_permit_refused'; END IF;
 permit:=permit_wire::jsonb;
 IF NOT vn_jupiter_b2_allocation_research_v3._keys(permit,ARRAY['format','permit_id','scope','native_package_sha256','catalog_manifest_sha256','stop_command_wire','writer_binding_ids','expires_at_us','issuer_oid'])
  OR permit->>'format' IS DISTINCT FROM 'ga-jupiter-b2-terminal-permit-fixture-v1'
  OR (permit->>'permit_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true
  OR (permit->>'expires_at_us' ~ '^[0-9]{16}$') IS DISTINCT FROM true
  OR vn_jupiter_b2_allocation_research_v3._c14n(permit) IS DISTINCT FROM permit_wire
  OR vn_jupiter_b2_allocation_research_v3._scope(permit->'scope') IS DISTINCT FROM requested_scope
  OR pg_catalog.jsonb_typeof(permit->'stop_command_wire') IS DISTINCT FROM 'string'
 THEN RAISE EXCEPTION 'b2_terminal_permit_refused'; END IF;
 SELECT r.rolvaliduntil INTO issuer_deadline FROM pg_catalog.pg_roles r
  WHERE r.rolname=session_user AND r.oid::text=permit->>'issuer_oid' AND r.rolcanlogin AND r.rolcreaterole
  AND NOT r.rolsuper AND NOT r.rolinherit AND NOT r.rolcreatedb AND NOT r.rolreplication AND NOT r.rolbypassrls
  AND pg_catalog.isfinite(r.rolvaliduntil);
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_terminal_issuer_refused' USING ERRCODE='42501'; END IF;

 -- The anchor caller already holds the package and the two writer bindings.
 SELECT * INTO inputs FROM vn_jupiter_b2_fixture_anchor.package_inputs WHERE scope_wire=requested_scope;
 IF NOT FOUND OR inputs.retirement_permit_wire IS DISTINCT FROM permit_wire
  OR (inputs.retirement_wire IS NOT NULL) IS DISTINCT FROM after_disable
 THEN RAISE EXCEPTION 'b2_terminal_permit_refused'; END IF;
 package:=inputs.package_wire::jsonb;
 genesis:=inputs.genesis_wire::jsonb;
 IF package->>'format' NOT IN('ga-jupiter-b2-fixture-direct-scram-research-v3-v1','ga-jupiter-b2-fixture-direct-scram-deadlines-research-v3-v1')
  OR package->>'format' IS NULL
  OR vn_jupiter_b2_allocation_research_v3._c14n(package) IS DISTINCT FROM inputs.package_wire
  OR package->>'installation_id' IS DISTINCT FROM inputs.installation_id
  OR package#>>'{policies,native_package_sha256}' IS DISTINCT FROM package->>'native_package_sha256'
  OR package->'native_package_sha256' IS DISTINCT FROM permit->'native_package_sha256'
  OR package->'catalog_manifest_sha256' IS DISTINCT FROM permit->'catalog_manifest_sha256'
  OR package->>'catalog_manifest_sha256' IS DISTINCT FROM inputs.expected_catalog_sha256
  OR package->>'actor_manifest_sha256' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._sha(inputs.actor_manifest_wire)
 THEN RAISE EXCEPTION 'b2_terminal_permit_refused'; END IF;
 actor_manifest:=inputs.actor_manifest_wire::jsonb;
 IF actor_manifest->>'format' IS DISTINCT FROM (CASE package->>'format'
   WHEN 'ga-jupiter-b2-fixture-direct-scram-deadlines-research-v3-v1' THEN 'ga-jupiter-b2-capability-manifest-deadlines-research-v3-v1'
   ELSE 'ga-jupiter-b2-capability-manifest-research-v3-v1' END)
 THEN RAISE EXCEPTION 'b2_terminal_profile_refused'; END IF;

 command:=(permit->>'stop_command_wire')::jsonb;
 IF NOT vn_jupiter_b2_allocation_research_v3._keys(command,ARRAY['format','native_policy_sha256','scope','action_id','action_kind','expected_head','expected_fence_id','expected_fence_revision','body'])
  OR vn_jupiter_b2_allocation_research_v3._c14n(command) IS DISTINCT FROM permit->>'stop_command_wire'
  OR command->>'format' IS DISTINCT FROM 'ga-jupiter-b2-allocation-command-research-v3-v1'
  OR command->'native_policy_sha256' IS DISTINCT FROM package->'native_policy_sha256'
  OR command->'scope' IS DISTINCT FROM permit->'scope' OR command->>'action_kind' IS DISTINCT FROM 'source_stop'
  OR command->>'action_id' IS DISTINCT FROM genesis->>'terminal_stop_action_id'
  OR command->'expected_fence_id' IS DISTINCT FROM 'null'::jsonb OR command->'expected_fence_revision' IS DISTINCT FROM 'null'::jsonb
  OR NOT vn_jupiter_b2_allocation_research_v3._keys(command->'body',ARRAY['expected_control_sha256','expected_mode'])
  OR command#>>'{body,expected_mode}' IS DISTINCT FROM 'open'
 THEN RAISE EXCEPTION 'b2_terminal_original_refused'; END IF;
 SELECT st.head_wire::jsonb,st.accounting_wire::jsonb INTO head,accounting
  FROM vn_jupiter_b2_allocation_research_v3.scope_state st WHERE st.scope_wire=requested_scope FOR UPDATE NOWAIT;
 IF NOT FOUND OR head->>'source_mode' IS DISTINCT FROM 'open' OR head->>'native_sequence' IS DISTINCT FROM '3'
  OR head->>'fence_revision' IS DISTINCT FROM '1' OR pg_catalog.jsonb_typeof(head->'active_fence_id') IS DISTINCT FROM 'string'
  OR head->>'active_acquisition_epoch' IS DISTINCT FROM genesis#>>'{initial_acquisition_spec,acquisition_epoch}'
  OR accounting->'Stop_reserve_consumed' IS DISTINCT FROM 'false'::jsonb
  OR pg_catalog.jsonb_build_object('native_sequence',head->'native_sequence','native_head_sha256',head->'native_head_sha256',
   'previous_seal_sha256',head->'previous_seal_sha256') IS DISTINCT FROM command->'expected_head'
  OR NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.original_operations o WHERE o.scope_wire=requested_scope
   AND o.native_sequence=3 AND o.action_kind='source_resume' AND o.finalized AND o.command_sha256=command#>>'{body,expected_control_sha256}')
 THEN RAISE EXCEPTION 'b2_terminal_head_refused'; END IF;

 SELECT o.command_wire::jsonb->'body' INTO installed_body
 FROM vn_jupiter_b2_allocation_research_v3.original_operations o
 WHERE o.scope_wire=requested_scope AND o.native_sequence=1 AND o.action_kind='installation' AND o.finalized
  AND o.command_sha256=vn_jupiter_b2_allocation_research_v3._sha(o.command_wire);
 IF NOT FOUND OR installed_body IS DISTINCT FROM pg_catalog.jsonb_build_object(
  'installation_id',inputs.installation_id,'scope',permit->'scope','policies',package->'policies',
  'catalog_manifest_sha256',package->'catalog_manifest_sha256','actor_manifest_sha256',package->'actor_manifest_sha256',
  'genesis_registry_sha256',vn_jupiter_b2_allocation_research_v3._sha(inputs.genesis_wire))
 THEN RAISE EXCEPTION 'b2_terminal_installation_refused'; END IF;

 held_catalog:=vn_jupiter_b2_allocation_research_v3._catalog();
 FOR expected_profile IN SELECT v.* FROM (VALUES
   ('installation',1::bigint,ARRAY['install','register_epoch','read_original']::text[]),
   ('fence_acquire',2::bigint,ARRAY['reserve','fence_manage','read_original']::text[])
  ) AS v(kind,position,capabilities) ORDER BY v.position
 LOOP
  SELECT w.* INTO binding FROM vn_jupiter_b2_allocation_research_v3.original_operations o
   JOIN vn_jupiter_b2_fixture_anchor.actor_bindings w ON w.scope_wire=o.scope_wire AND w.binding_id=o.writer_binding_id
   WHERE o.scope_wire=requested_scope AND o.native_sequence=expected_profile.position AND o.action_kind=expected_profile.kind AND o.finalized;
  IF NOT FOUND OR binding.capabilities IS DISTINCT FROM expected_profile.capabilities
   OR (expected_profile.position=2 AND binding.binding_id IS DISTINCT FROM genesis#>>'{initial_acquisition_spec,recorder_principal_binding_id}')
   OR NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(actor_manifest->'bindings') entry
      WHERE entry->>'principal_binding_id'=binding.binding_id AND entry->>'session_user_oid'=binding.session_oid::text
      AND entry->>'session_user_name'=binding.session_name AND entry->'scope'=permit->'scope'
      AND vn_jupiter_b2_allocation_research_v3._c14n(entry)=binding.binding_wire)
  THEN RAISE EXCEPTION 'b2_terminal_writer_refused'; END IF;
  SELECT x.ordinality INTO role_index FROM pg_catalog.jsonb_array_elements(held_catalog->'roles') WITH ORDINALITY x(value,ordinality)
   WHERE x.value->>'oid'=binding.session_oid::text AND x.value->>'name'=binding.session_name
    AND x.value->'login'=pg_catalog.to_jsonb(NOT after_disable);
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_terminal_writer_refused'; END IF;
  IF after_disable THEN
   held_catalog:=pg_catalog.jsonb_set(held_catalog,ARRAY['roles',(role_index-1)::text,'login'],'true'::jsonb,false);
  END IF;
  writer_ids:=writer_ids||pg_catalog.jsonb_build_array(binding.binding_id);
  writers:=writers||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object(
   'binding_id',binding.binding_id,'role_name',binding.session_name,'role_oid',binding.session_oid::text,
   'binding_sha256',vn_jupiter_b2_allocation_research_v3._sha(binding.binding_wire)));
 END LOOP;
 IF writer_ids IS DISTINCT FROM permit->'writer_binding_ids'
  OR vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(held_catalog)) IS DISTINCT FROM inputs.expected_catalog_sha256
 THEN RAISE EXCEPTION 'b2_terminal_catalog_refused'; END IF;

 -- Clock observed after the package, binding and scope locks and exact K.
 observed:=pg_catalog.clock_timestamp();
 observed_us:=pg_catalog.floor(EXTRACT(epoch FROM observed)*1000000)::bigint;
 IF issuer_deadline<=observed OR observed_us >= (permit->>'expires_at_us')::bigint
  OR (SELECT pg_catalog.jsonb_build_array(
      count(*) FILTER(WHERE b.capabilities=ARRAY['control','read_original']::text[]),
      count(*) FILTER(WHERE b.capabilities=ARRAY['register_reader_epoch','read_original']::text[]
       AND b.binding_id=genesis#>>'{initial_acquisition_spec,reader_principal_binding_id}'))
      FROM vn_jupiter_b2_fixture_anchor.actor_bindings b JOIN pg_catalog.pg_roles r ON r.oid=b.session_oid AND r.rolname=b.session_name
      WHERE b.scope_wire=requested_scope AND r.rolcanlogin AND pg_catalog.isfinite(r.rolvaliduntil)
      AND r.rolvaliduntil>observed+interval '5 seconds'
      AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(actor_manifest->'bindings') e
       WHERE e->>'principal_binding_id'=b.binding_id AND e->>'session_user_oid'=b.session_oid::text
        AND e->>'session_user_name'=b.session_name AND e->'scope'=permit->'scope'
        AND e->'capabilities'=pg_catalog.to_jsonb(b.capabilities)
        AND vn_jupiter_b2_allocation_research_v3._c14n(e)=b.binding_wire)) IS DISTINCT FROM '[1,1]'::jsonb
 THEN RAISE EXCEPTION 'b2_terminal_window_refused'; END IF;
 IF package->>'format'='ga-jupiter-b2-fixture-direct-scram-deadlines-research-v3-v1' THEN
  -- The package lock and the exact manifest/role check above hold these
  -- bindings. The authenticated issuer cannot replace either window.
  FOR deadline_profile IN SELECT v.* FROM (VALUES
    (ARRAY['control','read_original']::text[],'write_until_us','read_until_us','b2_terminal_control_window_refused'),
    (ARRAY['register_reader_epoch','read_original']::text[],'read_until_us','write_until_us','b2_terminal_reader_window_refused')
   ) AS v(capabilities,cutoff,other_cutoff,refusal)
  LOOP
   SELECT b.binding_wire::jsonb,r.rolvaliduntil INTO survivor,survivor_login_until
   FROM vn_jupiter_b2_fixture_anchor.actor_bindings b JOIN pg_catalog.pg_roles r
    ON r.oid=b.session_oid AND r.rolname=b.session_name
   WHERE b.scope_wire=requested_scope AND b.capabilities=deadline_profile.capabilities AND r.rolcanlogin
    AND (deadline_profile.cutoff='write_until_us' OR
     b.binding_id=genesis#>>'{initial_acquisition_spec,reader_principal_binding_id}')
    AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(actor_manifest->'bindings') e
     WHERE e->>'principal_binding_id'=b.binding_id AND e->>'session_user_oid'=b.session_oid::text
      AND e->>'session_user_name'=b.session_name AND e->'scope'=permit->'scope'
      AND e->'capabilities'=pg_catalog.to_jsonb(b.capabilities)
      AND vn_jupiter_b2_allocation_research_v3._c14n(e)=b.binding_wire);
   IF NOT FOUND OR survivor->'credential_generation' IS DISTINCT FROM '"1"'::jsonb
    OR survivor->(deadline_profile.other_cutoff) IS DISTINCT FROM 'null'::jsonb
    OR survivor_login_until IS NULL OR NOT pg_catalog.isfinite(survivor_login_until)
   THEN RAISE EXCEPTION 'b2_terminal_deadline_profile_refused'; END IF;
   FOREACH field IN ARRAY ARRAY['issued_at_us','not_before_us','login_until_us',deadline_profile.cutoff] LOOP
    IF pg_catalog.jsonb_typeof(survivor->field) IS DISTINCT FROM 'string'
     OR (survivor->>field ~ '^[1-9][0-9]{0,17}$') IS DISTINCT FROM true
    THEN RAISE EXCEPTION 'b2_terminal_deadline_profile_refused'; END IF;
   END LOOP;
   issued_us:=(survivor->>'issued_at_us')::bigint;
   not_before_us:=(survivor->>'not_before_us')::bigint;
   cutoff_us:=(survivor->>(deadline_profile.cutoff))::bigint;
   login_until_us:=(survivor->>'login_until_us')::bigint;
   IF issued_us>not_before_us OR not_before_us>=cutoff_us OR cutoff_us>login_until_us
    OR login_until_us-issued_us>300000000
    OR login_until_us IS DISTINCT FROM pg_catalog.floor(EXTRACT(epoch FROM survivor_login_until)*1000000)::bigint
   THEN RAISE EXCEPTION 'b2_terminal_deadline_profile_refused'; END IF;
   IF observed_us<not_before_us OR cutoff_us<=observed_us+5000000
   THEN RAISE EXCEPTION '%',deadline_profile.refusal USING ERRCODE='42501'; END IF;
  END LOOP;
 END IF;
 RETURN vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_object(
  'format','ga-jupiter-b2-terminal-retirement-fixture-v1','scope',permit->'scope',
  'native_package_sha256',permit->'native_package_sha256','catalog_manifest_sha256',permit->'catalog_manifest_sha256',
  'stop_action_id',command->'action_id','stop_command_sha256',vn_jupiter_b2_allocation_research_v3._sha(permit->>'stop_command_wire'),
  'writers',writers));
END;
$terminal$;
REVOKE ALL ON FUNCTION vn_jupiter_b2_allocation_research_v3._terminal_retirement_context(pg_catalog.text,pg_catalog.text,pg_catalog.bool) FROM PUBLIC;
GRANT USAGE ON SCHEMA vn_jupiter_b2_allocation_research_v3 TO vn_jupiter_b2_anchor_owner;
GRANT EXECUTE ON FUNCTION vn_jupiter_b2_allocation_research_v3._terminal_retirement_context(pg_catalog.text,pg_catalog.text,pg_catalog.bool) TO vn_jupiter_b2_anchor_owner;
RESET ROLE;
SET LOCAL ROLE vn_jupiter_b2_anchor_owner;

-- FUNCTION _stage_terminal_retirement
CREATE FUNCTION vn_jupiter_b2_fixture_anchor._stage_terminal_retirement(requested_scope pg_catalog.text, requested_permit pg_catalog.text)
RETURNS pg_catalog.text
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $terminal$
DECLARE p vn_jupiter_b2_fixture_anchor.package_inputs%ROWTYPE; permit jsonb; locked integer; marker text;
BEGIN
 IF session_user IS DISTINCT FROM 'vn_jupiter_b2_actor_issuer'
  OR system_user IS DISTINCT FROM ('scram-sha-256:'||session_user::text)
  OR pg_catalog.inet_client_addr() IS NULL
 THEN RAISE EXCEPTION 'b2_terminal_issuer_refused' USING ERRCODE='42501'; END IF;
 IF requested_scope IS NULL OR pg_catalog.octet_length(requested_scope)>512 OR requested_permit IS NULL
  OR (requested_permit ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true
 THEN RAISE EXCEPTION 'b2_terminal_permit_refused'; END IF;
 SELECT * INTO p FROM vn_jupiter_b2_fixture_anchor.package_inputs WHERE scope_wire=requested_scope FOR UPDATE NOWAIT;
 IF NOT FOUND OR p.retirement_wire IS NOT NULL OR p.retirement_permit_wire IS NULL THEN RAISE EXCEPTION 'b2_terminal_permit_refused'; END IF;
 permit:=p.retirement_permit_wire::jsonb;
 IF permit->>'permit_id' IS DISTINCT FROM requested_permit OR pg_catalog.jsonb_typeof(permit->'writer_binding_ids') IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'b2_terminal_permit_refused'; END IF;
 IF pg_catalog.jsonb_array_length(permit->'writer_binding_ids')<>2 THEN RAISE EXCEPTION 'b2_terminal_permit_refused'; END IF;
 PERFORM 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings b WHERE b.scope_wire=requested_scope
  AND b.binding_id IN(SELECT v FROM pg_catalog.jsonb_array_elements_text(permit->'writer_binding_ids') v)
  ORDER BY b.binding_id COLLATE "C" FOR UPDATE NOWAIT;
 GET DIAGNOSTICS locked=ROW_COUNT;
 IF locked<>2 THEN RAISE EXCEPTION 'b2_terminal_writer_refused'; END IF;
 marker:=vn_jupiter_b2_allocation_research_v3._terminal_retirement_context(requested_scope,p.retirement_permit_wire,false);
 UPDATE vn_jupiter_b2_fixture_anchor.package_inputs SET retirement_wire=marker WHERE scope_wire=requested_scope;
 RETURN marker;
END;
$terminal$;

-- FUNCTION _terminal_retirement_commit_guard
CREATE FUNCTION vn_jupiter_b2_fixture_anchor._terminal_retirement_commit_guard()
RETURNS pg_catalog.trigger
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET search_path = 'pg_catalog', 'pg_temp'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET standard_conforming_strings = 'on'
AS $terminal$
BEGIN
 IF pg_catalog.btrim(pg_catalog.current_query(),E' \t\r\n\f'||pg_catalog.chr(11)) NOT IN('COMMIT','COMMIT;')
 THEN RAISE EXCEPTION 'b2_terminal_commit_form_refused'; END IF;
 IF OLD.retirement_wire IS NOT NULL OR NEW.retirement_wire IS NULL
  OR OLD.retirement_permit_wire IS DISTINCT FROM NEW.retirement_permit_wire
  OR NEW.retirement_wire IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._terminal_retirement_context(NEW.scope_wire,NEW.retirement_permit_wire,true)
 THEN RAISE EXCEPTION 'b2_terminal_marker_refused'; END IF;
 RETURN NEW;
END;
$terminal$;
REVOKE ALL ON FUNCTION vn_jupiter_b2_fixture_anchor._stage_terminal_retirement(pg_catalog.text,pg_catalog.text) FROM PUBLIC;
REVOKE ALL ON FUNCTION vn_jupiter_b2_fixture_anchor._terminal_retirement_commit_guard() FROM PUBLIC;
GRANT USAGE ON SCHEMA vn_jupiter_b2_fixture_anchor TO vn_jupiter_b2_actor_issuer;
GRANT EXECUTE ON FUNCTION vn_jupiter_b2_fixture_anchor._stage_terminal_retirement(pg_catalog.text,pg_catalog.text) TO vn_jupiter_b2_actor_issuer;
CREATE CONSTRAINT TRIGGER committed_terminal_retirement_guard AFTER UPDATE ON vn_jupiter_b2_fixture_anchor.package_inputs
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
WHEN ((OLD.retirement_permit_wire IS NOT NULL OR NEW.retirement_permit_wire IS NOT NULL)
 AND (OLD.retirement_wire IS DISTINCT FROM NEW.retirement_wire
  OR (OLD.retirement_permit_wire IS NOT NULL AND OLD.retirement_permit_wire IS DISTINCT FROM NEW.retirement_permit_wire)))
EXECUTE FUNCTION vn_jupiter_b2_fixture_anchor._terminal_retirement_commit_guard();
RESET ROLE;
COMMIT;
