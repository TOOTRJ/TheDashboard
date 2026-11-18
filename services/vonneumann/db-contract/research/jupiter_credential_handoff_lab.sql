-- Private one-scope, one-recorder laboratory overlay.
BEGIN;
SET LOCAL ROLE vn_jupiter_b2_anchor_owner;
CREATE TABLE vn_jupiter_b2_fixture_anchor.credential_handoff (
 scope_wire pg_catalog.text PRIMARY KEY REFERENCES vn_jupiter_b2_fixture_anchor.package_inputs(scope_wire),
 handoff_id pg_catalog.uuid UNIQUE NOT NULL,
 permit_wire pg_catalog.text NOT NULL CHECK (pg_catalog.octet_length(permit_wire)<=8192),
 stage_xid pg_catalog.xid8,
 handoff_wire pg_catalog.text CHECK (pg_catalog.octet_length(handoff_wire)<=8192),
 CHECK (handoff_wire IS NULL OR stage_xid IS NOT NULL)
);
REVOKE ALL ON TABLE vn_jupiter_b2_fixture_anchor.credential_handoff FROM PUBLIC;
REVOKE ALL ON TYPE vn_jupiter_b2_fixture_anchor.credential_handoff FROM PUBLIC;
GRANT SELECT ON TABLE vn_jupiter_b2_fixture_anchor.credential_handoff TO vn_jupiter_b2_sealed_owner;
RESET ROLE;
SET LOCAL ROLE vn_jupiter_b2_sealed_owner;

-- FUNCTION _read_handoff
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._read_handoff(requested_scope pg_catalog.text)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path='pg_catalog','pg_temp' SET TimeZone='UTC' SET client_encoding='UTF8' SET standard_conforming_strings='on'
AS $handoff$
DECLARE h vn_jupiter_b2_fixture_anchor.credential_handoff%ROWTYPE; marker jsonb; permit jsonb;
BEGIN
 SELECT * INTO h FROM vn_jupiter_b2_fixture_anchor.credential_handoff WHERE scope_wire=requested_scope;
 IF NOT FOUND OR (h.stage_xid IS NULL AND h.handoff_wire IS NULL) THEN RETURN NULL; END IF;
 IF h.handoff_wire IS NULL OR h.stage_xid=pg_catalog.pg_current_xact_id_if_assigned()
 THEN RAISE EXCEPTION 'b2_handoff_marker_refused'; END IF;
 marker:=h.handoff_wire::jsonb; permit:=h.permit_wire::jsonb;
 IF NOT vn_jupiter_b2_allocation_research_v3._keys(marker,ARRAY['handoff_id','permit_sha256','catalog_sha256','head_sha256','fence_sha256','renew_action_id','renew_command_sha256','successor_binding','old_binding_id','observed_us'])
  OR vn_jupiter_b2_allocation_research_v3._c14n(marker) IS DISTINCT FROM h.handoff_wire
  OR marker->>'handoff_id' IS DISTINCT FROM h.handoff_id::text
  OR permit->>'handoff_id' IS DISTINCT FROM h.handoff_id::text
  OR vn_jupiter_b2_allocation_research_v3._scope(permit->'scope') IS DISTINCT FROM requested_scope
  OR marker->>'permit_sha256' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._sha(h.permit_wire)
  OR marker->>'head_sha256' IS DISTINCT FROM permit->>'head_sha256'
  OR marker->>'fence_sha256' IS DISTINCT FROM permit->>'fence_sha256'
  OR marker->>'old_binding_id' IS DISTINCT FROM permit->>'old_binding_id'
  OR marker->>'renew_action_id' IS DISTINCT FROM ((permit->>'renew_wire')::jsonb)->>'action_id'
  OR marker->>'renew_command_sha256' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._sha(permit->>'renew_wire')
  OR (marker->>'catalog_sha256' ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true
  OR (marker->>'observed_us' ~ '^[1-9][0-9]{0,17}$') IS DISTINCT FROM true
  OR marker#>>'{successor_binding,principal_binding_id}' IS DISTINCT FROM permit->>'new_binding_id'
  OR marker#>>'{successor_binding,issuance_id}' IS DISTINCT FROM permit->>'issuance_id'
  OR marker#>>'{successor_binding,credential_generation}' IS DISTINCT FROM '2'
  OR NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings b
   WHERE b.scope_wire=requested_scope AND b.binding_id=permit->>'new_binding_id'
    AND b.session_name=marker#>>'{successor_binding,session_user_name}'
    AND b.session_oid::text=marker#>>'{successor_binding,session_user_oid}'
    AND pg_catalog.to_jsonb(b.capabilities)=marker#>'{successor_binding,capabilities}'
    AND b.binding_wire=vn_jupiter_b2_allocation_research_v3._c14n(marker->'successor_binding'))
 THEN RAISE EXCEPTION 'b2_handoff_marker_refused'; END IF;
 RETURN marker;
END;
$handoff$;

-- FUNCTION _handoff_allows_renew
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._handoff_allows_renew(marker pg_catalog.jsonb, native_position pg_catalog.int8, command_sha pg_catalog.text, writer_binding pg_catalog.text, prior_fence pg_catalog.jsonb, prior_head_sha pg_catalog.text)
RETURNS pg_catalog.bool
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
SET search_path='pg_catalog','pg_temp' SET TimeZone='UTC' SET client_encoding='UTF8' SET standard_conforming_strings='on'
AS $handoff$
BEGIN
 RETURN (writer_binding=marker#>>'{successor_binding,principal_binding_id}' AND
  (CASE WHEN native_position=4 THEN command_sha=marker->>'renew_command_sha256'
    AND prior_head_sha=marker->>'head_sha256'
    AND prior_fence->>'holder_principal_binding_id'=marker->>'old_binding_id'
    AND vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(prior_fence))=marker->>'fence_sha256'
   ELSE native_position BETWEEN 5 AND 16 AND prior_fence->>'holder_principal_binding_id'=writer_binding END)) IS TRUE;
END;
$handoff$;

-- FUNCTION _handoff_catalog_preimage
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._handoff_catalog_preimage(actual pg_catalog.jsonb, old_role pg_catalog.oid, new_role pg_catalog.oid, issuer pg_catalog.oid)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path='pg_catalog','pg_temp' SET TimeZone='UTC' SET client_encoding='UTF8' SET standard_conforming_strings='on'
AS $handoff$
DECLARE item jsonb; n int; cls record; idx text; object_path text[]; acl_atom text;
        native_owner oid:='vn_jupiter_b2_sealed_owner'::pg_catalog.regrole;
        ns_oid oid:='vn_jupiter_b2_allocation_research_v3'::pg_catalog.regnamespace;
        submit_oid oid:='vn_jupiter_b2_allocation_research_v3.submit(pg_catalog.text)'::pg_catalog.regprocedure;
        get_oid oid:='vn_jupiter_b2_allocation_research_v3.get_original(pg_catalog.text)'::pg_catalog.regprocedure;
BEGIN
 -- Only the exact prospective creator edge, three direct ACL atoms, and
 -- three dependent role references are removed. All other K1 facts survive.
 IF (SELECT count(*) FROM pg_catalog.pg_auth_members m WHERE m.roleid=new_role OR m.member=new_role)<>1
  OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members m WHERE m.roleid=new_role AND m.member=issuer
   AND m.grantor=10 AND m.admin_option AND NOT m.set_option AND NOT m.inherit_option)
  OR (SELECT count(*) FROM pg_catalog.jsonb_array_elements(actual->'roles') e WHERE e->>'oid'=new_role::text)<>1
 THEN RAISE EXCEPTION 'b2_handoff_catalog_delta_refused'; END IF;
 SELECT ordinality-1 INTO n FROM pg_catalog.jsonb_array_elements(actual->'roles') WITH ORDINALITY e(value,ordinality)
 WHERE value->>'oid'=old_role::text AND value->'login'='false'::jsonb;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_handoff_catalog_delta_refused'; END IF;
 actual:=pg_catalog.jsonb_set(actual,ARRAY['roles',n::text,'login'],'true'::jsonb,false);
 FOR cls IN SELECT v.* FROM (VALUES
   ('schemas','acl','oid',ns_oid,'pg_catalog.pg_namespace'::pg_catalog.regclass::oid,'USAGE','U'),
   ('functions','proacl','oid',submit_oid,'pg_catalog.pg_proc'::pg_catalog.regclass::oid,'EXECUTE','X'),
   ('functions','proacl','oid',get_oid,'pg_catalog.pg_proc'::pg_catalog.regclass::oid,'EXECUTE','X')
  ) v(section,acl_field,oid_field,obj_oid,class_oid,privilege,letter)
 LOOP
  SELECT e.ordinality::text, e.value->cls.acl_field INTO idx,item
   FROM pg_catalog.jsonb_array_elements(actual->cls.section) WITH ORDINALITY e(value,ordinality)
   WHERE e.value->>cls.oid_field=cls.obj_oid::text;
  IF NOT FOUND THEN RAISE EXCEPTION 'b2_handoff_catalog_delta_refused'; END IF;
  acl_atom:='vn_jupiter_b2_0_recorder_next='||cls.letter||'/vn_jupiter_b2_sealed_owner';
  IF (SELECT count(*) FROM pg_catalog.jsonb_array_elements_text(item) e WHERE e=acl_atom)<>1
   OR (SELECT count(*) FROM pg_catalog.aclexplode(ARRAY[acl_atom::pg_catalog.aclitem]) a
       WHERE a.grantee=new_role AND a.grantor=native_owner AND a.privilege_type=cls.privilege AND NOT a.is_grantable)<>1
   OR (SELECT count(*) FROM pg_catalog.jsonb_array_elements(actual->'shared_dependencies') e
       WHERE e->>'refobjid'=new_role::text AND e->>'refclassid'='pg_catalog.pg_authid'::pg_catalog.regclass::oid::text
        AND e->>'objid'=cls.obj_oid::text AND e->>'classid'=cls.class_oid::text
        AND e->>'objsubid'='0' AND e->>'deptype'='a')<>1
  THEN RAISE EXCEPTION 'b2_handoff_catalog_delta_refused'; END IF;
  object_path:=ARRAY[cls.section,(idx::bigint-1)::text,cls.acl_field];
  actual:=pg_catalog.jsonb_set(actual,object_path,item-acl_atom,false);
 END LOOP;
 IF (SELECT count(*) FROM pg_catalog.jsonb_array_elements(actual->'shared_dependencies') e WHERE e->>'refobjid'=new_role::text)<>3
 THEN RAISE EXCEPTION 'b2_handoff_catalog_delta_refused'; END IF;
 actual:=pg_catalog.jsonb_set(actual,'{roles}',(SELECT pg_catalog.jsonb_agg(value ORDER BY ordinality)
  FROM pg_catalog.jsonb_array_elements(actual->'roles') WITH ORDINALITY e(value,ordinality) WHERE value->>'oid'<>new_role::text),false);
 actual:=pg_catalog.jsonb_set(actual,'{memberships}',(SELECT pg_catalog.jsonb_agg(value ORDER BY ordinality)
  FROM pg_catalog.jsonb_array_elements(actual->'memberships') WITH ORDINALITY e(value,ordinality) WHERE value->>'roleid'<>new_role::text),false);
 RETURN pg_catalog.jsonb_set(actual,'{shared_dependencies}',(SELECT pg_catalog.jsonb_agg(value ORDER BY ordinality)
  FROM pg_catalog.jsonb_array_elements(actual->'shared_dependencies') WITH ORDINALITY e(value,ordinality) WHERE value->>'refobjid'<>new_role::text),false);
END;
$handoff$;

-- FUNCTION _handoff_native
CREATE FUNCTION vn_jupiter_b2_allocation_research_v3._handoff_native(requested_scope pg_catalog.text, requested_id pg_catalog.uuid, phase pg_catalog.text)
RETURNS pg_catalog.text
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path='pg_catalog','pg_temp' SET TimeZone='UTC' SET client_encoding='UTF8' SET standard_conforming_strings='on'
AS $handoff$
DECLARE p vn_jupiter_b2_fixture_anchor.package_inputs%ROWTYPE; h vn_jupiter_b2_fixture_anchor.credential_handoff%ROWTYPE;
 b vn_jupiter_b2_fixture_anchor.actor_bindings%ROWTYPE; permit jsonb; package jsonb; genesis jsonb; manifest jsonb;
 head jsonb; acct jsonb; install jsonb; fence jsonb; renewal jsonb; old_entry jsonb; issued jsonb; marker jsonb; actual jsonb;
 issuer record; successor record; field text; profile record; live_count integer; observed bigint; marker_clock bigint;
 next_binding text; next_name text:='vn_jupiter_b2_0_recorder_next'; old_login boolean; last_commit_us bigint;
BEGIN
 IF session_user IS DISTINCT FROM 'vn_jupiter_b2_actor_issuer' OR system_user IS DISTINCT FROM ('scram-sha-256:'||session_user::text)
  OR pg_catalog.inet_client_addr() IS NULL OR pg_catalog.current_setting('transaction_isolation')<>'read committed'
  OR phase IS NULL OR phase NOT IN('stage','grant','finish','commit')
 THEN RAISE EXCEPTION 'b2_handoff_issuer_refused' USING ERRCODE='42501'; END IF;
 SELECT * INTO issuer FROM pg_catalog.pg_roles WHERE rolname=session_user AND rolcanlogin AND rolcreaterole AND NOT rolsuper
  AND NOT rolinherit AND NOT rolcreatedb AND NOT rolreplication AND NOT rolbypassrls AND pg_catalog.isfinite(rolvaliduntil);
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_handoff_issuer_refused' USING ERRCODE='42501'; END IF;
 SELECT * INTO p FROM vn_jupiter_b2_fixture_anchor.package_inputs WHERE scope_wire=requested_scope AND retirement_wire IS NULL AND retirement_permit_wire IS NULL;
 IF NOT FOUND OR (SELECT count(*) FROM vn_jupiter_b2_fixture_anchor.package_inputs)<>1
 THEN RAISE EXCEPTION 'b2_handoff_scope_refused'; END IF;
 SELECT * INTO h FROM vn_jupiter_b2_fixture_anchor.credential_handoff WHERE scope_wire=requested_scope AND handoff_id=requested_id;
 IF NOT FOUND OR (phase='stage' AND (h.stage_xid IS NOT NULL OR h.handoff_wire IS NOT NULL))
  OR (phase<>'stage' AND h.stage_xid IS DISTINCT FROM pg_catalog.pg_current_xact_id())
  OR ((phase='commit') IS DISTINCT FROM (h.handoff_wire IS NOT NULL))
 THEN RAISE EXCEPTION 'b2_handoff_permit_refused'; END IF;
 permit:=h.permit_wire::jsonb; package:=p.package_wire::jsonb; genesis:=p.genesis_wire::jsonb; manifest:=p.actor_manifest_wire::jsonb;
 IF NOT vn_jupiter_b2_allocation_research_v3._keys(permit,ARRAY['handoff_id','scope','installation_id','package_sha256','catalog_sha256','head_sha256','old_binding_id','old_binding_sha256','fence_sha256','renew_wire','stop_id','issuer_oid','new_binding_id','issuance_id','issued_at_us','write_until_us','login_until_us','expires_us'])
  OR vn_jupiter_b2_allocation_research_v3._c14n(permit) IS DISTINCT FROM h.permit_wire
  OR permit->>'handoff_id' IS DISTINCT FROM requested_id::text
  OR vn_jupiter_b2_allocation_research_v3._scope(permit->'scope') IS DISTINCT FROM requested_scope
  OR permit->>'installation_id' IS DISTINCT FROM p.installation_id
  OR permit->>'package_sha256' IS DISTINCT FROM package->>'native_package_sha256'
  OR permit->>'catalog_sha256' IS DISTINCT FROM p.expected_catalog_sha256
  OR package->>'catalog_manifest_sha256' IS DISTINCT FROM p.expected_catalog_sha256
  OR package->>'actor_manifest_sha256' IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._sha(p.actor_manifest_wire)
  OR package->>'format' IS DISTINCT FROM 'ga-jupiter-b2-fixture-direct-scram-handoff-research-v3-v1'
  OR manifest->>'format' IS DISTINCT FROM 'ga-jupiter-b2-capability-manifest-deadlines-research-v3-v1'
  OR permit->>'issuer_oid' IS DISTINCT FROM issuer.oid::text
  OR permit->>'stop_id' IS DISTINCT FROM genesis->>'terminal_stop_action_id'
  OR permit->>'old_binding_id' IS DISTINCT FROM genesis#>>'{initial_acquisition_spec,recorder_principal_binding_id}'
 THEN RAISE EXCEPTION 'b2_handoff_permit_refused'; END IF;
 FOREACH field IN ARRAY ARRAY['new_binding_id','issuance_id'] LOOP
  IF (permit->>field ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true
  THEN RAISE EXCEPTION 'b2_handoff_permit_refused'; END IF;
 END LOOP;
 FOREACH field IN ARRAY ARRAY['issued_at_us','write_until_us','login_until_us','expires_us'] LOOP
  IF (permit->>field ~ '^[1-9][0-9]{0,17}$') IS DISTINCT FROM true THEN RAISE EXCEPTION 'b2_handoff_permit_refused'; END IF;
 END LOOP;
 next_binding:=permit->>'new_binding_id';
 IF next_binding IS NOT DISTINCT FROM permit->>'issuance_id'
  OR EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities i WHERE i.original_id IN(next_binding,permit->>'issuance_id'))
  OR EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(manifest->'bindings') e WHERE e->>'issuance_id'=permit->>'issuance_id')
 THEN RAISE EXCEPTION 'b2_handoff_permit_refused'; END IF;
 SELECT * INTO b FROM vn_jupiter_b2_fixture_anchor.actor_bindings WHERE scope_wire=requested_scope AND binding_id=permit->>'old_binding_id';
 IF NOT FOUND OR b.capabilities IS DISTINCT FROM ARRAY['reserve','fence_manage','read_original']::text[]
  OR vn_jupiter_b2_allocation_research_v3._sha(b.binding_wire) IS DISTINCT FROM permit->>'old_binding_sha256'
  OR NOT EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(manifest->'bindings') e
   WHERE e->>'principal_binding_id'=b.binding_id AND e->>'session_user_oid'=b.session_oid::text
    AND e->>'session_user_name'=b.session_name AND vn_jupiter_b2_allocation_research_v3._c14n(e)=b.binding_wire)
 THEN RAISE EXCEPTION 'b2_handoff_permit_refused'; END IF;
 old_entry:=b.binding_wire::jsonb;
 SELECT s.head_wire::jsonb,s.accounting_wire::jsonb INTO head,acct
  FROM vn_jupiter_b2_allocation_research_v3.scope_state s WHERE s.scope_wire=requested_scope FOR UPDATE NOWAIT;
 IF NOT FOUND OR head->>'native_sequence' IS DISTINCT FROM '3' OR head->>'source_mode' IS DISTINCT FROM 'open'
  OR head->>'fence_revision' IS DISTINCT FROM '1' OR head->>'native_head_sha256' IS DISTINCT FROM permit->>'head_sha256'
  OR acct->'Stop_reserve_consumed' IS DISTINCT FROM 'false'::jsonb
 THEN RAISE EXCEPTION 'b2_handoff_head_refused'; END IF;
 SELECT (o.receipt_wire::jsonb#>>'{commit_processing_observation,observed_at_us}')::bigint INTO last_commit_us
 FROM vn_jupiter_b2_allocation_research_v3.original_operations o JOIN vn_jupiter_b2_allocation_research_v3.journal_entries j
   ON j.scope_wire=o.scope_wire AND j.native_sequence=o.native_sequence AND j.action_id=o.action_id
 WHERE o.scope_wire=requested_scope AND o.native_sequence=3 AND o.action_kind='source_resume' AND o.finalized
   AND o.receipt_sha256=vn_jupiter_b2_allocation_research_v3._sha(o.receipt_wire)
   AND j.journal_sha256=head->>'native_head_sha256';
 IF NOT FOUND OR last_commit_us IS NULL THEN RAISE EXCEPTION 'b2_handoff_head_refused'; END IF;
 PERFORM vn_jupiter_b2_allocation_research_v3._require_no_stop_intent(requested_scope);
 SELECT o.command_wire::jsonb->'body' INTO install FROM vn_jupiter_b2_allocation_research_v3.original_operations o
  WHERE o.scope_wire=requested_scope AND o.native_sequence=1 AND o.action_kind='installation' AND o.finalized;
 IF NOT FOUND OR install IS DISTINCT FROM pg_catalog.jsonb_build_object(
  'installation_id',p.installation_id,'scope',permit->'scope','policies',package->'policies',
  'catalog_manifest_sha256',package->'catalog_manifest_sha256','actor_manifest_sha256',package->'actor_manifest_sha256',
  'genesis_registry_sha256',vn_jupiter_b2_allocation_research_v3._sha(p.genesis_wire))
 THEN RAISE EXCEPTION 'b2_handoff_head_refused'; END IF;
 SELECT o.result_wire::jsonb#>'{result_body,original_fence_record}' INTO fence FROM vn_jupiter_b2_allocation_research_v3.original_operations o
  WHERE o.scope_wire=requested_scope AND o.native_sequence=2 AND o.action_kind='fence_acquire' AND o.finalized AND o.writer_binding_id=b.binding_id;
 IF NOT FOUND OR fence->>'holder_principal_binding_id' IS DISTINCT FROM b.binding_id
  OR fence->>'fence_id' IS DISTINCT FROM head->>'active_fence_id' OR fence->>'revision' IS DISTINCT FROM '1'
  OR vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(fence)) IS DISTINCT FROM permit->>'fence_sha256'
 THEN RAISE EXCEPTION 'b2_handoff_head_refused'; END IF;
 renewal:=(permit->>'renew_wire')::jsonb;
 IF vn_jupiter_b2_allocation_research_v3._c14n(renewal) IS DISTINCT FROM permit->>'renew_wire'
  OR renewal IS DISTINCT FROM pg_catalog.jsonb_build_object('format','ga-jupiter-b2-allocation-command-research-v3-v1',
   'native_policy_sha256',package->'native_policy_sha256','scope',permit->'scope','action_id',renewal->'action_id','action_kind','fence_renew',
   'expected_head',pg_catalog.jsonb_build_object('native_sequence','3','native_head_sha256',head->'native_head_sha256','previous_seal_sha256',NULL),
   'expected_fence_id',fence->'fence_id','expected_fence_revision','1',
   'body',pg_catalog.jsonb_build_object('fence_id',fence->'fence_id','expected_revision','1','requested_duration_us','60000000'))
  OR (renewal->>'action_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true
  OR renewal->>'action_id' IN(next_binding,permit->>'issuance_id')
  OR EXISTS(SELECT 1 FROM vn_jupiter_b2_allocation_research_v3.identities WHERE original_id=renewal->>'action_id')
 THEN RAISE EXCEPTION 'b2_handoff_permit_refused'; END IF;
 observed:=(vn_jupiter_b2_allocation_research_v3._clock()->>'observed_at_us')::bigint;
 IF observed>=(permit->>'expires_us')::bigint
  OR observed>=pg_catalog.floor(EXTRACT(epoch FROM issuer.rolvaliduntil)*1000000)::bigint OR observed<last_commit_us
  OR observed+5000000>=(fence->>'expires_at_us')::bigint
  OR observed<(permit->>'issued_at_us')::bigint OR observed+5000000>=(permit->>'write_until_us')::bigint
  OR (permit->>'write_until_us')::bigint>=(permit->>'login_until_us')::bigint
  OR (permit->>'login_until_us')::bigint-(permit->>'issued_at_us')::bigint>300000000
  OR observed+5000000>=(old_entry->>'write_until_us')::bigint
 THEN RAISE EXCEPTION 'b2_handoff_clock_refused'; END IF;
 FOR profile IN SELECT x.* FROM (VALUES
   (ARRAY['control','read_original']::text[],'write_until_us'),
   (ARRAY['register_reader_epoch','read_original']::text[],'read_until_us')) x(capabilities,cutoff)
 LOOP
  SELECT count(*) INTO live_count FROM vn_jupiter_b2_fixture_anchor.actor_bindings s JOIN pg_catalog.pg_roles r
   ON r.oid=s.session_oid AND r.rolname=s.session_name
   WHERE s.scope_wire=requested_scope AND s.capabilities=profile.capabilities AND r.rolcanlogin AND pg_catalog.isfinite(r.rolvaliduntil)
    AND EXISTS(SELECT 1 FROM pg_catalog.jsonb_array_elements(manifest->'bindings') e
     WHERE vn_jupiter_b2_allocation_research_v3._c14n(e)=s.binding_wire
      AND e->>'principal_binding_id'=s.binding_id AND e->>'session_user_oid'=s.session_oid::text AND e->>'session_user_name'=s.session_name
      AND (e->>'not_before_us')::bigint<=observed AND (e->>profile.cutoff)::bigint>observed+5000000
      AND (e->>'login_until_us')::bigint=pg_catalog.floor(EXTRACT(epoch FROM r.rolvaliduntil)*1000000)::bigint
      AND (e->>'login_until_us')::bigint>observed+5000000);
  IF live_count<>1 THEN RAISE EXCEPTION 'b2_handoff_clock_refused'; END IF;
 END LOOP;

 SELECT rolcanlogin INTO old_login FROM pg_catalog.pg_roles WHERE oid=b.session_oid AND rolname=b.session_name;
 IF NOT FOUND OR old_login IS DISTINCT FROM (phase='stage') THEN RAISE EXCEPTION 'b2_handoff_role_refused'; END IF;
 IF phase='stage' THEN
  actual:=vn_jupiter_b2_allocation_research_v3._catalog();
  IF vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(actual)) IS DISTINCT FROM p.expected_catalog_sha256
   OR EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=next_name)
   OR EXISTS(SELECT 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings WHERE binding_id=next_binding)
  THEN RAISE EXCEPTION 'b2_handoff_catalog_delta_refused'; END IF;
  RETURN NULL;
 END IF;
 SELECT * INTO successor FROM pg_catalog.pg_roles WHERE rolname=next_name AND rolcanlogin AND rolconnlimit=2
  AND NOT rolsuper AND NOT rolinherit AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication AND NOT rolbypassrls
  AND rolconfig IS NULL AND pg_catalog.isfinite(rolvaliduntil);
 IF NOT FOUND OR pg_catalog.floor(EXTRACT(epoch FROM successor.rolvaliduntil)*1000000)::bigint IS DISTINCT FROM (permit->>'login_until_us')::bigint
  OR (SELECT count(*) FROM pg_catalog.pg_auth_members m WHERE m.roleid=successor.oid OR m.member=successor.oid)<>1
  OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members m WHERE m.roleid=successor.oid AND m.member=issuer.oid AND m.grantor=10 AND m.admin_option AND NOT m.set_option AND NOT m.inherit_option)
 THEN RAISE EXCEPTION 'b2_handoff_role_refused'; END IF;
 issued:=old_entry||pg_catalog.jsonb_build_object('principal_binding_id',next_binding,'session_user_oid',successor.oid::text,'session_user_name',next_name,
  'issuance_id',permit->>'issuance_id','credential_generation','2','issued_at_us',permit->>'issued_at_us','not_before_us',permit->>'issued_at_us',
  'write_until_us',permit->>'write_until_us','login_until_us',permit->>'login_until_us');
 IF phase='grant' THEN
  IF EXISTS(SELECT 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings WHERE binding_id=next_binding OR session_oid=successor.oid)
  THEN RAISE EXCEPTION 'b2_handoff_role_refused'; END IF;
  GRANT USAGE ON SCHEMA vn_jupiter_b2_allocation_research_v3 TO vn_jupiter_b2_0_recorder_next;
  GRANT EXECUTE ON FUNCTION vn_jupiter_b2_allocation_research_v3.submit(pg_catalog.text),vn_jupiter_b2_allocation_research_v3.get_original(pg_catalog.text) TO vn_jupiter_b2_0_recorder_next;
  RETURN vn_jupiter_b2_allocation_research_v3._c14n(issued);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings s WHERE s.scope_wire=requested_scope
   AND s.binding_id=next_binding AND s.session_oid=successor.oid AND s.session_name=next_name
   AND s.capabilities=b.capabilities AND s.binding_wire=vn_jupiter_b2_allocation_research_v3._c14n(issued))
 THEN RAISE EXCEPTION 'b2_handoff_role_refused'; END IF;
 actual:=vn_jupiter_b2_allocation_research_v3._catalog();
 IF vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(
  vn_jupiter_b2_allocation_research_v3._handoff_catalog_preimage(actual,b.session_oid,successor.oid,issuer.oid))) IS DISTINCT FROM p.expected_catalog_sha256
 THEN RAISE EXCEPTION 'b2_handoff_catalog_delta_refused'; END IF;
 marker_clock:=CASE WHEN phase='commit' THEN (h.handoff_wire::jsonb->>'observed_us')::bigint ELSE observed END;
 IF marker_clock IS NULL OR marker_clock<(permit->>'issued_at_us')::bigint OR marker_clock<last_commit_us OR marker_clock>observed
 THEN RAISE EXCEPTION 'b2_handoff_clock_refused'; END IF;
 RETURN vn_jupiter_b2_allocation_research_v3._c14n(pg_catalog.jsonb_build_object('handoff_id',requested_id::text,'permit_sha256',vn_jupiter_b2_allocation_research_v3._sha(h.permit_wire),
  'catalog_sha256',vn_jupiter_b2_allocation_research_v3._sha(vn_jupiter_b2_allocation_research_v3._c14n(actual)),
  'head_sha256',permit->'head_sha256','fence_sha256',permit->'fence_sha256','renew_action_id',renewal->'action_id',
  'renew_command_sha256',vn_jupiter_b2_allocation_research_v3._sha(permit->>'renew_wire'),'old_binding_id',b.binding_id,
  'successor_binding',issued,'observed_us',marker_clock::text));
END;
$handoff$;
REVOKE ALL ON FUNCTION vn_jupiter_b2_allocation_research_v3._read_handoff(pg_catalog.text),
 vn_jupiter_b2_allocation_research_v3._handoff_allows_renew(pg_catalog.jsonb,pg_catalog.int8,pg_catalog.text,pg_catalog.text,pg_catalog.jsonb,pg_catalog.text),
 vn_jupiter_b2_allocation_research_v3._handoff_catalog_preimage(pg_catalog.jsonb,pg_catalog.oid,pg_catalog.oid,pg_catalog.oid),
 vn_jupiter_b2_allocation_research_v3._handoff_native(pg_catalog.text,pg_catalog.uuid,pg_catalog.text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vn_jupiter_b2_allocation_research_v3._handoff_native(pg_catalog.text,pg_catalog.uuid,pg_catalog.text) TO vn_jupiter_b2_anchor_owner;
RESET ROLE;
SET LOCAL ROLE vn_jupiter_b2_anchor_owner;

-- FUNCTION _stage_credential_handoff
CREATE FUNCTION vn_jupiter_b2_fixture_anchor._stage_credential_handoff(requested_scope pg_catalog.text, requested_id pg_catalog.uuid)
RETURNS pg_catalog.void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path='pg_catalog','pg_temp' SET TimeZone='UTC' SET client_encoding='UTF8' SET standard_conforming_strings='on'
AS $handoff$
DECLARE old_binding text;
BEGIN
 IF session_user IS DISTINCT FROM 'vn_jupiter_b2_actor_issuer' OR system_user IS DISTINCT FROM ('scram-sha-256:'||session_user::text)
  OR pg_catalog.inet_client_addr() IS NULL OR requested_scope IS NULL OR pg_catalog.octet_length(requested_scope)>512
 THEN RAISE EXCEPTION 'b2_handoff_issuer_refused' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM vn_jupiter_b2_fixture_anchor.package_inputs WHERE scope_wire=requested_scope FOR UPDATE NOWAIT;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_handoff_scope_refused'; END IF;
 SELECT permit_wire::jsonb->>'old_binding_id' INTO old_binding FROM vn_jupiter_b2_fixture_anchor.credential_handoff
  WHERE scope_wire=requested_scope AND handoff_id=requested_id AND stage_xid IS NULL AND handoff_wire IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_handoff_permit_refused'; END IF;
 PERFORM 1 FROM vn_jupiter_b2_fixture_anchor.actor_bindings WHERE scope_wire=requested_scope AND binding_id=old_binding FOR UPDATE NOWAIT;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_handoff_permit_refused'; END IF;
 PERFORM 1 FROM vn_jupiter_b2_fixture_anchor.credential_handoff WHERE scope_wire=requested_scope AND handoff_id=requested_id FOR UPDATE NOWAIT;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_handoff_permit_refused'; END IF;
 PERFORM vn_jupiter_b2_allocation_research_v3._handoff_native(requested_scope,requested_id,'stage');
 UPDATE vn_jupiter_b2_fixture_anchor.credential_handoff SET stage_xid=pg_catalog.pg_current_xact_id()
 WHERE scope_wire=requested_scope AND handoff_id=requested_id;
END;
$handoff$;

-- FUNCTION _finish_credential_handoff
CREATE FUNCTION vn_jupiter_b2_fixture_anchor._finish_credential_handoff(requested_scope pg_catalog.text, requested_id pg_catalog.uuid)
RETURNS pg_catalog.text
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path='pg_catalog','pg_temp' SET TimeZone='UTC' SET client_encoding='UTF8' SET standard_conforming_strings='on'
AS $handoff$
DECLARE binding jsonb; binding_wire text; marker text;
BEGIN
 binding_wire:=vn_jupiter_b2_allocation_research_v3._handoff_native(requested_scope,requested_id,'grant');
 binding:=binding_wire::jsonb;
 INSERT INTO vn_jupiter_b2_fixture_anchor.actor_bindings(binding_id,scope_wire,session_oid,session_name,capabilities,binding_wire)
 VALUES(binding->>'principal_binding_id',requested_scope,(binding->>'session_user_oid')::oid,binding->>'session_user_name',
 ARRAY['reserve','fence_manage','read_original']::text[],binding_wire);
 marker:=vn_jupiter_b2_allocation_research_v3._handoff_native(requested_scope,requested_id,'finish');
 UPDATE vn_jupiter_b2_fixture_anchor.credential_handoff SET handoff_wire=marker
  WHERE scope_wire=requested_scope AND handoff_id=requested_id AND stage_xid=pg_catalog.pg_current_xact_id();
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_handoff_marker_refused'; END IF;
 RETURN marker;
END;
$handoff$;

-- FUNCTION _commit_credential_handoff
CREATE FUNCTION vn_jupiter_b2_fixture_anchor._commit_credential_handoff()
RETURNS pg_catalog.trigger
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path='pg_catalog','pg_temp' SET TimeZone='UTC' SET client_encoding='UTF8' SET standard_conforming_strings='on'
AS $handoff$
DECLARE h vn_jupiter_b2_fixture_anchor.credential_handoff%ROWTYPE;
BEGIN
 IF pg_catalog.btrim(pg_catalog.current_query(),E' \t\r\n\f'||pg_catalog.chr(11)) NOT IN('COMMIT','COMMIT;')
 THEN RAISE EXCEPTION 'b2_handoff_commit_form_refused'; END IF;
 SELECT * INTO h FROM vn_jupiter_b2_fixture_anchor.credential_handoff WHERE scope_wire=NEW.scope_wire AND handoff_id=NEW.handoff_id;
 IF NOT FOUND OR h.permit_wire IS DISTINCT FROM NEW.permit_wire OR h.stage_xid IS DISTINCT FROM NEW.stage_xid OR h.handoff_wire IS NULL
  OR h.handoff_wire IS DISTINCT FROM vn_jupiter_b2_allocation_research_v3._handoff_native(h.scope_wire,h.handoff_id,'commit')
 THEN RAISE EXCEPTION 'b2_handoff_marker_refused'; END IF;
 RETURN NEW;
END;
$handoff$;
CREATE CONSTRAINT TRIGGER committed_credential_handoff_guard
 AFTER UPDATE ON vn_jupiter_b2_fixture_anchor.credential_handoff
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
 WHEN (OLD.stage_xid IS NULL AND NEW.stage_xid IS NOT NULL)
 EXECUTE FUNCTION vn_jupiter_b2_fixture_anchor._commit_credential_handoff();
REVOKE ALL ON FUNCTION vn_jupiter_b2_fixture_anchor._stage_credential_handoff(pg_catalog.text,pg_catalog.uuid),
 vn_jupiter_b2_fixture_anchor._finish_credential_handoff(pg_catalog.text,pg_catalog.uuid),
 vn_jupiter_b2_fixture_anchor._commit_credential_handoff() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vn_jupiter_b2_fixture_anchor._stage_credential_handoff(pg_catalog.text,pg_catalog.uuid),
 vn_jupiter_b2_fixture_anchor._finish_credential_handoff(pg_catalog.text,pg_catalog.uuid) TO vn_jupiter_b2_actor_issuer;
RESET ROLE;
COMMIT;
