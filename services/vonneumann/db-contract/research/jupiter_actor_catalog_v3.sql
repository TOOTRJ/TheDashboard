-- B1 actor/catalog-only research; no source/native/model/trading authority.
-- policy-sha256: 2618f8f4239460112df4b7b21138f103f265353233d35e779e874431057a7c06
-- Execute only split source-bound sections after owned-fixture review.
-- TABLE vn_jupiter_b1_fixture_anchor.installer_reference
CREATE TABLE vn_jupiter_b1_fixture_anchor.installer_reference (
  singleton pg_catalog.bool NOT NULL,
  fixture_id pg_catalog.text NOT NULL,
  database_oid pg_catalog.oid NOT NULL,
  database_name pg_catalog.text NOT NULL,
  server_version_num pg_catalog.int4 NOT NULL,
  actor_catalog_package_sha256 pg_catalog.text NOT NULL,
  installation_manifest_sha256 pg_catalog.text NOT NULL,
  catalog_manifest_sha256 pg_catalog.text NOT NULL,
  role_closure_sha256 pg_catalog.text NOT NULL,
  CONSTRAINT installer_reference_pkey PRIMARY KEY (singleton),
  CONSTRAINT installer_reference_shape CHECK ((singleton AND fixture_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' AND database_oid <> 0 AND pg_catalog.octet_length(database_name) BETWEEN 1 AND 63 AND server_version_num BETWEEN 170000 AND 179999 AND actor_catalog_package_sha256 ~ '^[0-9a-f]{64}$' AND installation_manifest_sha256 ~ '^[0-9a-f]{64}$' AND catalog_manifest_sha256 ~ '^[0-9a-f]{64}$' AND role_closure_sha256 ~ '^[0-9a-f]{64}$') IS TRUE)
);

-- TABLE vn_jupiter_b1_fixture_anchor.expected_functions
CREATE TABLE vn_jupiter_b1_fixture_anchor.expected_functions (
  signature pg_catalog.text NOT NULL,
  spec pg_catalog.jsonb NOT NULL,
  CONSTRAINT expected_functions_pkey PRIMARY KEY (signature),
  CONSTRAINT expected_functions_shape CHECK ((pg_catalog.jsonb_typeof(spec) = 'object' AND spec ?& ARRAY['signature','argument_type_names','argument_names','return_type_name','language','kind','owner_role_name','security_definer','volatility','parallel','strict','leakproof','returns_set','cost_text','rows_text','support_oid_text','variadic_oid_text','default_argument_count_text','all_argument_types','argument_modes','transform_types','binary','sql_body','local_settings','body_sha256','source_package_sha256','execute_role_names'] AND spec - ARRAY['signature','argument_type_names','argument_names','return_type_name','language','kind','owner_role_name','security_definer','volatility','parallel','strict','leakproof','returns_set','cost_text','rows_text','support_oid_text','variadic_oid_text','default_argument_count_text','all_argument_types','argument_modes','transform_types','binary','sql_body','local_settings','body_sha256','source_package_sha256','execute_role_names'] = '{}'::pg_catalog.jsonb AND spec->>'signature' = signature AND spec->>'body_sha256' ~ '^[0-9a-f]{64}$' AND spec->>'source_package_sha256' ~ '^[0-9a-f]{64}$') IS TRUE)
);

-- TABLE vn_jupiter_actor_catalog_research_v3.actor_bindings
CREATE TABLE vn_jupiter_actor_catalog_research_v3.actor_bindings (
  principal_binding_id pg_catalog.text NOT NULL,
  session_user_oid pg_catalog.oid NOT NULL,
  session_user_name pg_catalog.text NOT NULL,
  owner_id pg_catalog.text NOT NULL,
  run_id pg_catalog.text NOT NULL,
  market_epoch pg_catalog.text NOT NULL,
  profile pg_catalog.text NOT NULL,
  capabilities pg_catalog.text[] NOT NULL,
  installation_manifest_sha256 pg_catalog.text NOT NULL,
  CONSTRAINT actor_bindings_pkey PRIMARY KEY (principal_binding_id),
  CONSTRAINT actor_bindings_session_oid_key UNIQUE (session_user_oid),
  CONSTRAINT actor_bindings_session_name_key UNIQUE (session_user_name),
  CONSTRAINT actor_bindings_shape CHECK ((principal_binding_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' AND session_user_oid <> 0 AND pg_catalog.octet_length(session_user_name) BETWEEN 1 AND 63 AND owner_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' AND run_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' AND market_epoch ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' AND profile IN ('recorder','reader','sealer','control') AND capabilities = ARRAY['verify_actor','read_scoped_binding']::pg_catalog.text[] AND installation_manifest_sha256 ~ '^[0-9a-f]{64}$') IS TRUE)
);

-- TABLE vn_jupiter_actor_catalog_research_v3.accepted_pins
CREATE TABLE vn_jupiter_actor_catalog_research_v3.accepted_pins (
  singleton pg_catalog.bool NOT NULL,
  actor_catalog_package_sha256 pg_catalog.text NOT NULL,
  installation_manifest_sha256 pg_catalog.text NOT NULL,
  catalog_manifest_sha256 pg_catalog.text NOT NULL,
  role_closure_sha256 pg_catalog.text NOT NULL,
  CONSTRAINT accepted_pins_pkey PRIMARY KEY (singleton),
  CONSTRAINT accepted_pins_shape CHECK ((singleton AND actor_catalog_package_sha256 ~ '^[0-9a-f]{64}$' AND installation_manifest_sha256 ~ '^[0-9a-f]{64}$' AND catalog_manifest_sha256 ~ '^[0-9a-f]{64}$' AND role_closure_sha256 ~ '^[0-9a-f]{64}$') IS TRUE)
);

-- FUNCTION _c14n
CREATE FUNCTION vn_jupiter_actor_catalog_research_v3._c14n(v pg_catalog.jsonb)
RETURNS pg_catalog.text
LANGUAGE plpgsql IMMUTABLE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET DateStyle = 'ISO, YMD'
SET IntervalStyle = 'postgres'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET row_security = 'on'
SET search_path = 'pg_catalog', 'pg_temp'
SET standard_conforming_strings = 'on'
AS $b1$
DECLARE result pg_catalog.text; t pg_catalog.text;
BEGIN
  IF v IS NULL THEN RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='b1_invalid_input'; END IF;
  t := pg_catalog.jsonb_typeof(v);
  IF t='object' THEN
    SELECT '{'||COALESCE(pg_catalog.string_agg(pg_catalog.to_jsonb(k)::pg_catalog.text||':'||vn_jupiter_actor_catalog_research_v3._c14n(value),',' ORDER BY k COLLATE "C"),'')||'}' INTO result FROM pg_catalog.jsonb_each(v) AS e(k,value);
  ELSIF t='array' THEN
    SELECT '['||COALESCE(pg_catalog.string_agg(vn_jupiter_actor_catalog_research_v3._c14n(value),',' ORDER BY ord),'')||']' INTO result FROM pg_catalog.jsonb_array_elements(v) WITH ORDINALITY AS e(value,ord);
  ELSIF t IN ('string','boolean','null') THEN result := v::pg_catalog.text;
  ELSE RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused';
  END IF;
  RETURN result;
END
$b1$;

-- FUNCTION _binding_core
CREATE FUNCTION vn_jupiter_actor_catalog_research_v3._binding_core()
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET DateStyle = 'ISO, YMD'
SET IntervalStyle = 'postgres'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET row_security = 'on'
SET search_path = 'pg_catalog', 'pg_temp'
SET standard_conforming_strings = 'on'
AS $b1$
DECLARE result pg_catalog.jsonb; n pg_catalog.int4;
BEGIN
  SELECT pg_catalog.count(*) INTO n FROM vn_jupiter_actor_catalog_research_v3.actor_bindings;
  IF n NOT BETWEEN 1 AND 16 OR EXISTS (SELECT 1 FROM vn_jupiter_actor_catalog_research_v3.actor_bindings b LEFT JOIN pg_catalog.pg_roles r ON r.oid=b.session_user_oid WHERE r.oid IS NULL OR r.rolname::pg_catalog.text IS DISTINCT FROM b.session_user_name) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('principal_binding_id',principal_binding_id,'session_user_oid',session_user_oid::pg_catalog.text,'session_user_name',session_user_name,'scope',pg_catalog.jsonb_build_object('owner_id',owner_id,'run_id',run_id,'market_epoch',market_epoch),'profile',profile,'capabilities',pg_catalog.to_jsonb(capabilities)) ORDER BY principal_binding_id COLLATE "C") INTO result FROM vn_jupiter_actor_catalog_research_v3.actor_bindings;
  RETURN result;
END
$b1$;

-- FUNCTION _role_closure
CREATE FUNCTION vn_jupiter_actor_catalog_research_v3._role_closure()
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET DateStyle = 'ISO, YMD'
SET IntervalStyle = 'postgres'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET row_security = 'on'
SET search_path = 'pg_catalog', 'pg_temp'
SET standard_conforming_strings = 'on'
AS $b1$
DECLARE ids pg_catalog.oid[]; result pg_catalog.jsonb; edges pg_catalog.jsonb; params pg_catalog.jsonb;
BEGIN
  PERFORM vn_jupiter_actor_catalog_research_v3._binding_core();
  WITH RECURSIVE reachable(oid) AS (
    SELECT session_user_oid FROM vn_jupiter_actor_catalog_research_v3.actor_bindings
    UNION SELECT m.roleid FROM pg_catalog.pg_auth_members m JOIN reachable n ON m.member=n.oid)
  SELECT pg_catalog.array_agg(oid ORDER BY oid) INTO ids FROM reachable;
  IF pg_catalog.cardinality(ids)>64 OR EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE oid=ANY(ids) AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)) OR EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=ANY(ids) AND admin_option) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('roleid',roleid::pg_catalog.text,'member',member::pg_catalog.text,'grantor',grantor::pg_catalog.text,'admin_option',admin_option,'inherit_option',inherit_option,'set_option',set_option) ORDER BY roleid,member,grantor,admin_option,inherit_option,set_option),'[]'::pg_catalog.jsonb) INTO edges FROM pg_catalog.pg_auth_members WHERE member=ANY(ids);
  SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('parameter_name',p.parname,'grantor_oid',a.grantor::pg_catalog.text,'grantee_oid',a.grantee::pg_catalog.text,'privilege_kind',a.privilege_type,'grantable',a.is_grantable) ORDER BY p.parname COLLATE "C",a.grantor,a.grantee,a.privilege_type COLLATE "C",a.is_grantable),'[]'::pg_catalog.jsonb) INTO params FROM pg_catalog.pg_parameter_acl p CROSS JOIN LATERAL pg_catalog.aclexplode(p.paracl) a WHERE a.grantee=0 OR a.grantee=ANY(ids);
  IF pg_catalog.jsonb_array_length(edges)>256 OR pg_catalog.jsonb_array_length(params)>64 OR pg_catalog.jsonb_array_length(params)>0 THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  SELECT pg_catalog.jsonb_build_object('format','ga-jupiter-b1-role-closure-v3','actor_catalog_policy_sha256','2618f8f4239460112df4b7b21138f103f265353233d35e779e874431057a7c06','nodes',pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('oid',oid::pg_catalog.text,'name',rolname::pg_catalog.text,'login',rolcanlogin,'inherit',rolinherit,'superuser',rolsuper,'createdb',rolcreatedb,'createrole',rolcreaterole,'replication',rolreplication,'bypassrls',rolbypassrls,'connection_limit',rolconnlimit::pg_catalog.text,'valid_until',CASE WHEN rolvaliduntil IS NULL THEN NULL ELSE pg_catalog.to_char(rolvaliduntil,'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') END,'rolconfig',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(c ORDER BY c COLLATE "C")) FROM pg_catalog.unnest(rolconfig) c)) ORDER BY oid),'edges',edges,'parameter_privileges',params) INTO result FROM pg_catalog.pg_roles WHERE oid=ANY(ids);
  RETURN result;
END
$b1$;

-- FUNCTION _installation_preimage
CREATE FUNCTION vn_jupiter_actor_catalog_research_v3._installation_preimage()
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET DateStyle = 'ISO, YMD'
SET IntervalStyle = 'postgres'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET row_security = 'on'
SET search_path = 'pg_catalog', 'pg_temp'
SET standard_conforming_strings = 'on'
AS $b1$
DECLARE r record; core pg_catalog.jsonb; scopes pg_catalog.jsonb;
BEGIN
  SELECT * INTO STRICT r FROM vn_jupiter_b1_fixture_anchor.installer_reference WHERE singleton;
  IF r.database_oid IS DISTINCT FROM (SELECT oid FROM pg_catalog.pg_database WHERE datname=pg_catalog.current_database()) OR r.database_name IS DISTINCT FROM pg_catalog.current_database() OR r.server_version_num::pg_catalog.text IS DISTINCT FROM pg_catalog.current_setting('server_version_num') THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  core := vn_jupiter_actor_catalog_research_v3._binding_core();
  SELECT pg_catalog.jsonb_agg(scope ORDER BY scope->>'owner_id' COLLATE "C",scope->>'run_id' COLLATE "C",scope->>'market_epoch' COLLATE "C") INTO scopes FROM (SELECT DISTINCT value->'scope' AS scope FROM pg_catalog.jsonb_array_elements(core)) s;
  RETURN pg_catalog.jsonb_build_object('format','ga-jupiter-b1-installation-manifest-v3','actor_catalog_policy_sha256','2618f8f4239460112df4b7b21138f103f265353233d35e779e874431057a7c06','actor_catalog_package_sha256',r.actor_catalog_package_sha256,'database_identity',pg_catalog.jsonb_build_object('fixture_id',r.fixture_id,'database_oid',r.database_oid::pg_catalog.text,'database_name',r.database_name,'server_version_num',r.server_version_num::pg_catalog.text),'scopes',scopes,'bindings_core',core);
END
$b1$;

-- FUNCTION _catalog_preimage
CREATE FUNCTION vn_jupiter_actor_catalog_research_v3._catalog_preimage()
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET DateStyle = 'ISO, YMD'
SET IntervalStyle = 'postgres'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET row_security = 'on'
SET search_path = 'pg_catalog', 'pg_temp'
SET standard_conforming_strings = 'on'
AS $b1$
DECLARE anchor_ref record; nsids pg_catalog.oid[]; tableids pg_catalog.oid[]; classids pg_catalog.oid[]; typeids pg_catalog.oid[]; procids pg_catalog.oid[]; rec record; wanted pg_catalog.jsonb; actual pg_catalog.jsonb; rows pg_catalog.jsonb:='[]'::pg_catalog.jsonb; defaults pg_catalog.jsonb; rolecfg pg_catalog.jsonb; protected pg_catalog.jsonb; runtime pg_catalog.jsonb; sealed pg_catalog.oid; params pg_catalog.jsonb;
BEGIN
  SELECT * INTO STRICT anchor_ref FROM vn_jupiter_b1_fixture_anchor.installer_reference WHERE singleton;
  SELECT oid INTO STRICT sealed FROM pg_catalog.pg_roles WHERE rolname='vn_jupiter_b1_sealed_owner' AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=sealed OR roleid=sealed) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.oid IN(SELECT session_user_oid FROM vn_jupiter_actor_catalog_research_v3.actor_bindings) OR r.rolname IN('postgres','vn_jupiter_b1_installer','vn_jupiter_b1_sealed_owner') GROUP BY r.oid,r.rolconfig HAVING pg_catalog.cardinality(r.rolconfig) IS DISTINCT FROM (SELECT pg_catalog.count(DISTINCT pg_catalog.split_part(v,'=',1)) FROM pg_catalog.unnest(r.rolconfig) v) AND r.rolconfig IS NOT NULL) OR EXISTS(SELECT 1 FROM pg_catalog.pg_db_role_setting s WHERE s.setdatabase IN(0,anchor_ref.database_oid) AND (s.setrole=0 OR s.setrole IN(SELECT session_user_oid FROM vn_jupiter_actor_catalog_research_v3.actor_bindings) OR s.setrole IN(SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN('postgres','vn_jupiter_b1_installer','vn_jupiter_b1_sealed_owner'))) AND pg_catalog.cardinality(s.setconfig) IS DISTINCT FROM (SELECT pg_catalog.count(DISTINCT pg_catalog.split_part(v,'=',1)) FROM pg_catalog.unnest(s.setconfig) v)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  SELECT pg_catalog.array_agg(oid ORDER BY oid) INTO nsids FROM pg_catalog.pg_namespace WHERE nspname IN ('vn_jupiter_actor_catalog_research_v3','vn_jupiter_b1_fixture_anchor');
  IF pg_catalog.cardinality(nsids) IS DISTINCT FROM 2 OR EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname='vn_jupiter_actor_catalog_research_v3' AND nspowner<>sealed) OR EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner WHERE n.nspname='vn_jupiter_b1_fixture_anchor' AND r.rolname<>'postgres') THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  SELECT pg_catalog.array_agg(c.oid ORDER BY c.oid) INTO tableids FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE (n.nspname='vn_jupiter_actor_catalog_research_v3' AND c.relname IN ('actor_bindings','accepted_pins') OR n.nspname='vn_jupiter_b1_fixture_anchor' AND c.relname IN ('installer_reference','expected_functions')) AND c.relkind='r';
  IF pg_catalog.cardinality(tableids) IS DISTINCT FROM 4 OR EXISTS(SELECT 1 FROM pg_catalog.pg_class c WHERE c.relnamespace=ANY(nsids) AND c.oid<>ALL(tableids) AND NOT (c.relkind='i' AND EXISTS(SELECT 1 FROM pg_catalog.pg_index i WHERE i.indexrelid=c.oid AND i.indrelid=ANY(tableids)))) OR EXISTS(SELECT 1 FROM pg_catalog.pg_class c WHERE c.oid=ANY(tableids) AND (c.relpersistence<>'p' OR c.relrowsecurity OR c.relforcerowsecurity OR c.relispartition OR c.reloptions IS NOT NULL OR c.relreplident<>'d')) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  SELECT pg_catalog.array_agg(oid ORDER BY oid) INTO classids FROM pg_catalog.pg_class WHERE oid=ANY(tableids) OR oid IN(SELECT indexrelid FROM pg_catalog.pg_index WHERE indrelid=ANY(tableids)) OR oid IN(SELECT reltoastrelid FROM pg_catalog.pg_class WHERE oid=ANY(tableids) AND reltoastrelid<>0) OR oid IN(SELECT indexrelid FROM pg_catalog.pg_index WHERE indrelid IN(SELECT reltoastrelid FROM pg_catalog.pg_class WHERE oid=ANY(tableids) AND reltoastrelid<>0));
  SELECT pg_catalog.array_agg(t.oid ORDER BY t.oid) INTO typeids FROM pg_catalog.pg_type t WHERE t.oid IN(SELECT reltype FROM pg_catalog.pg_class WHERE oid=ANY(tableids)) OR t.oid IN(SELECT typarray FROM pg_catalog.pg_type WHERE typrelid=ANY(tableids));
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_type WHERE typnamespace=ANY(nsids) AND oid<>ALL(typeids)) OR EXISTS(SELECT 1 FROM pg_catalog.pg_trigger WHERE tgrelid=ANY(classids)) OR EXISTS(SELECT 1 FROM pg_catalog.pg_policy WHERE polrelid=ANY(classids)) OR EXISTS(SELECT 1 FROM pg_catalog.pg_rewrite WHERE ev_class=ANY(classids)) OR EXISTS(SELECT 1 FROM pg_catalog.pg_event_trigger WHERE evtenabled<>'D') THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_operator WHERE oprnamespace=ANY(nsids)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_opclass WHERE opcnamespace=ANY(nsids)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_opfamily WHERE opfnamespace=ANY(nsids)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_collation WHERE collnamespace=ANY(nsids)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_conversion WHERE connamespace=ANY(nsids)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_ts_config WHERE cfgnamespace=ANY(nsids)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_ts_dict WHERE dictnamespace=ANY(nsids)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_ts_parser WHERE prsnamespace=ANY(nsids)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_ts_template WHERE tmplnamespace=ANY(nsids)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_statistic_ext WHERE stxnamespace=ANY(nsids)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  IF (SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc WHERE pronamespace=ANY(nsids))<>8 OR (SELECT pg_catalog.count(*) FROM vn_jupiter_b1_fixture_anchor.expected_functions)<>8 THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  SELECT pg_catalog.array_agg(oid ORDER BY oid) INTO procids FROM pg_catalog.pg_proc WHERE pronamespace=ANY(nsids);
  FOR rec IN SELECT p.*,n.nspname::pg_catalog.text AS namespace,l.lanname::pg_catalog.text AS language,o.rolname::pg_catalog.text AS owner_name FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace JOIN pg_catalog.pg_language l ON l.oid=p.prolang JOIN pg_catalog.pg_roles o ON o.oid=p.proowner WHERE p.oid=ANY(procids) LOOP
    actual := pg_catalog.jsonb_build_object('signature',rec.namespace||'.'||rec.proname::pg_catalog.text||'('||COALESCE((SELECT pg_catalog.string_agg(n.nspname::pg_catalog.text||'.'||t.typname::pg_catalog.text,',' ORDER BY ord) FROM pg_catalog.unnest(rec.proargtypes::pg_catalog.oid[]) WITH ORDINALITY a(oid,ord) JOIN pg_catalog.pg_type t ON t.oid=a.oid JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace),'')||')','argument_type_names',(SELECT COALESCE(pg_catalog.jsonb_agg(n.nspname::pg_catalog.text||'.'||t.typname::pg_catalog.text ORDER BY ord),'[]'::pg_catalog.jsonb) FROM pg_catalog.unnest(rec.proargtypes::pg_catalog.oid[]) WITH ORDINALITY a(oid,ord) JOIN pg_catalog.pg_type t ON t.oid=a.oid JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace),'argument_names',pg_catalog.to_jsonb(rec.proargnames),'return_type_name',(SELECT n.nspname::pg_catalog.text||'.'||t.typname::pg_catalog.text FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace WHERE t.oid=rec.prorettype),'language',rec.language,'kind',rec.prokind::pg_catalog.text,'owner_role_name',rec.owner_name,'security_definer',rec.prosecdef,'volatility',rec.provolatile::pg_catalog.text,'parallel',rec.proparallel::pg_catalog.text,'strict',rec.proisstrict,'leakproof',rec.proleakproof,'returns_set',rec.proretset,'cost_text',rec.procost::pg_catalog.text,'rows_text',rec.prorows::pg_catalog.text,'support_oid_text',rec.prosupport::pg_catalog.oid::pg_catalog.text,'variadic_oid_text',rec.provariadic::pg_catalog.text,'default_argument_count_text',rec.pronargdefaults::pg_catalog.text,'all_argument_types',pg_catalog.to_jsonb(rec.proallargtypes),'argument_modes',pg_catalog.to_jsonb(rec.proargmodes),'transform_types',pg_catalog.to_jsonb(rec.protrftypes),'binary',rec.probin,'sql_body',rec.prosqlbody::pg_catalog.text,'local_settings',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(v ORDER BY v COLLATE "C")) FROM pg_catalog.unnest(rec.proconfig) v),'body_sha256',pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(rec.prosrc,'UTF8')),'hex'),'source_package_sha256',anchor_ref.actor_catalog_package_sha256,'execute_role_names',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(o.rolname::pg_catalog.text ORDER BY o.rolname::pg_catalog.text COLLATE "C")) FROM pg_catalog.aclexplode(COALESCE(rec.proacl,pg_catalog.acldefault('f',rec.proowner))) a LEFT JOIN pg_catalog.pg_roles o ON o.oid=a.grantee));
    SELECT spec INTO STRICT wanted FROM vn_jupiter_b1_fixture_anchor.expected_functions WHERE signature=actual->>'signature';
    IF actual IS DISTINCT FROM wanted OR rec.proowner<>sealed OR EXISTS(SELECT 1 FROM pg_catalog.aclexplode(COALESCE(rec.proacl,pg_catalog.acldefault('f',rec.proowner))) a WHERE a.is_grantable OR a.grantee=0) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    rows := rows || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('kind','routine','namespace',rec.namespace,'identity',actual->>'signature','oid',rec.oid::pg_catalog.text,'owner_oid',rec.proowner::pg_catalog.text,'owner_name',(SELECT rolname::pg_catalog.text FROM pg_catalog.pg_roles WHERE oid=(rec.proowner::pg_catalog.text)::pg_catalog.oid),'attributes',pg_catalog.jsonb_build_object('source_spec',actual,'language_oid',rec.prolang::pg_catalog.text,'argument_type_oids',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(x::pg_catalog.text ORDER BY ord)) FROM pg_catalog.unnest(rec.proargtypes::pg_catalog.oid[]) WITH ORDINALITY u(x,ord)),'return_type_oid',rec.prorettype::pg_catalog.text,'owner_oid',rec.proowner::pg_catalog.text,'support_oid',rec.prosupport::pg_catalog.oid::pg_catalog.text,'argument_defaults',rec.proargdefaults::pg_catalog.text,'configuration',pg_catalog.to_jsonb(rec.proconfig),'body_sha256',pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(rec.prosrc,'UTF8')),'hex'),'definition',pg_catalog.pg_get_functiondef(rec.oid)),'acl_is_null',rec.proacl IS NULL,'effective_acl',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('grantor_oid',grantor::pg_catalog.text,'grantee_oid',grantee::pg_catalog.text,'privilege_kind',privilege_type,'grantable',is_grantable) ORDER BY grantor,grantee,privilege_type COLLATE "C",is_grantable) FROM pg_catalog.aclexplode(COALESCE(rec.proacl,pg_catalog.acldefault('f',rec.proowner)))),'[]'::pg_catalog.jsonb)));
  END LOOP;
  FOR rec IN SELECT n.*,n.nspname::pg_catalog.text AS namespace FROM pg_catalog.pg_namespace n WHERE oid=ANY(nsids) LOOP
    rows := rows || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('kind','namespace','namespace',rec.namespace,'identity',rec.nspname::pg_catalog.text,'oid',rec.oid::pg_catalog.text,'owner_oid',rec.nspowner::pg_catalog.text,'owner_name',(SELECT rolname::pg_catalog.text FROM pg_catalog.pg_roles WHERE oid=(rec.nspowner::pg_catalog.text)::pg_catalog.oid),'attributes',pg_catalog.jsonb_build_object('original_name',rec.nspname::pg_catalog.text),'acl_is_null',rec.nspacl IS NULL,'effective_acl',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('grantor_oid',grantor::pg_catalog.text,'grantee_oid',grantee::pg_catalog.text,'privilege_kind',privilege_type,'grantable',is_grantable) ORDER BY grantor,grantee,privilege_type COLLATE "C",is_grantable) FROM pg_catalog.aclexplode(COALESCE(rec.nspacl,pg_catalog.acldefault('n',rec.nspowner)))),'[]'::pg_catalog.jsonb)));
  END LOOP;
  FOR rec IN SELECT c.*,n.nspname::pg_catalog.text AS namespace,a.amname::pg_catalog.text AS method FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_catalog.pg_am a ON a.oid=c.relam WHERE c.oid=ANY(classids) LOOP
    rows := rows || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('kind','relation','namespace',rec.namespace,'identity',rec.relname::pg_catalog.text,'oid',rec.oid::pg_catalog.text,'owner_oid',rec.relowner::pg_catalog.text,'owner_name',(SELECT rolname::pg_catalog.text FROM pg_catalog.pg_roles WHERE oid=(rec.relowner::pg_catalog.text)::pg_catalog.oid),'attributes',pg_catalog.jsonb_build_object('relkind',rec.relkind::pg_catalog.text,'persistence',rec.relpersistence::pg_catalog.text,'access_method_name',rec.method,'access_method_oid',rec.relam::pg_catalog.text,'row_type_oid',rec.reltype::pg_catalog.text,'toast_oid',rec.reltoastrelid::pg_catalog.text,'reloptions',pg_catalog.to_jsonb(rec.reloptions),'tablespace_oid',rec.reltablespace::pg_catalog.text,'replica_identity',rec.relreplident::pg_catalog.text,'rls',rec.relrowsecurity,'forced_rls',rec.relforcerowsecurity,'partition_flag',rec.relispartition,'partition_bound',rec.relpartbound::pg_catalog.text,'inheritance_parents',(SELECT COALESCE(pg_catalog.jsonb_agg(inhparent::pg_catalog.text ORDER BY inhseqno),'[]'::pg_catalog.jsonb) FROM pg_catalog.pg_inherits WHERE inhrelid=rec.oid)),'acl_is_null',rec.relacl IS NULL,'effective_acl',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('grantor_oid',grantor::pg_catalog.text,'grantee_oid',grantee::pg_catalog.text,'privilege_kind',privilege_type,'grantable',is_grantable) ORDER BY grantor,grantee,privilege_type COLLATE "C",is_grantable) FROM pg_catalog.aclexplode(COALESCE(rec.relacl,pg_catalog.acldefault('r',rec.relowner)))),'[]'::pg_catalog.jsonb)));
  END LOOP;
  FOR rec IN SELECT a.*,n.nspname::pg_catalog.text AS namespace,c.relname::pg_catalog.text AS relation_name,t.typname::pg_catalog.text AS type_name,tn.nspname::pg_catalog.text AS type_namespace,co.collname::pg_catalog.text AS collation_name,cn.nspname::pg_catalog.text AS collation_namespace,d.adbin,d.adrelid FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_type t ON t.oid=a.atttypid JOIN pg_catalog.pg_namespace tn ON tn.oid=t.typnamespace LEFT JOIN pg_catalog.pg_collation co ON co.oid=a.attcollation LEFT JOIN pg_catalog.pg_namespace cn ON cn.oid=co.collnamespace LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE a.attrelid=ANY(classids) AND a.attnum>0 LOOP
    rows := rows || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('kind','column','namespace',rec.namespace,'identity',rec.relation_name||'.'||rec.attnum::pg_catalog.text||'.'||rec.attname::pg_catalog.text,'oid',rec.attrelid::pg_catalog.text,'owner_oid',NULL,'owner_name',NULL,'attributes',pg_catalog.jsonb_build_object('relation_oid',rec.attrelid::pg_catalog.text,'ordinal',rec.attnum::pg_catalog.text,'name',rec.attname::pg_catalog.text,'type_name',rec.type_namespace||'.'||rec.type_name,'type_oid',rec.atttypid::pg_catalog.text,'typmod',rec.atttypmod::pg_catalog.text,'collation_name',CASE WHEN rec.attcollation=0 THEN NULL ELSE rec.collation_namespace||'.'||rec.collation_name END,'collation_oid',rec.attcollation::pg_catalog.text,'not_null',rec.attnotnull,'dropped',rec.attisdropped,'identity',rec.attidentity::pg_catalog.text,'generated',rec.attgenerated::pg_catalog.text,'storage',rec.attstorage::pg_catalog.text,'compression',rec.attcompression::pg_catalog.text,'options',pg_catalog.to_jsonb(rec.attoptions),'fdw_options',pg_catalog.to_jsonb(rec.attfdwoptions),'default_expression',CASE WHEN rec.adbin IS NULL THEN NULL ELSE pg_catalog.pg_get_expr(rec.adbin,rec.adrelid,false) END),'acl_is_null',rec.attacl IS NULL,'effective_acl',CASE WHEN rec.attacl IS NULL THEN '[]'::pg_catalog.jsonb ELSE COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('grantor_oid',grantor::pg_catalog.text,'grantee_oid',grantee::pg_catalog.text,'privilege_kind',privilege_type,'grantable',is_grantable) ORDER BY grantor,grantee,privilege_type COLLATE "C",is_grantable) FROM pg_catalog.aclexplode(COALESCE(rec.attacl,pg_catalog.acldefault('c',0::pg_catalog.oid)))),'[]'::pg_catalog.jsonb) END));
  END LOOP;
  FOR rec IN SELECT t.*,n.nspname::pg_catalog.text AS namespace,e.typacl AS element_acl,e.typowner AS element_owner FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace LEFT JOIN pg_catalog.pg_type e ON e.oid=t.typelem WHERE t.oid=ANY(typeids) LOOP
    rows := rows || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('kind','type','namespace',rec.namespace,'identity',rec.typname::pg_catalog.text,'oid',rec.oid::pg_catalog.text,'owner_oid',rec.typowner::pg_catalog.text,'owner_name',(SELECT rolname::pg_catalog.text FROM pg_catalog.pg_roles WHERE oid=(rec.typowner::pg_catalog.text)::pg_catalog.oid),'attributes',pg_catalog.jsonb_build_object('kind',rec.typtype::pg_catalog.text,'category',rec.typcategory::pg_catalog.text,'relation_oid',rec.typrelid::pg_catalog.text,'base_oid',rec.typbasetype::pg_catalog.text,'array_oid',rec.typarray::pg_catalog.text,'element_oid',rec.typelem::pg_catalog.text,'dimensions',rec.typndims::pg_catalog.text,'typmod',rec.typtypmod::pg_catalog.text,'delimiter',rec.typdelim::pg_catalog.text,'length',rec.typlen::pg_catalog.text,'alignment',rec.typalign::pg_catalog.text,'storage',rec.typstorage::pg_catalog.text,'collation_oid',rec.typcollation::pg_catalog.text,'by_value',rec.typbyval,'not_null',rec.typnotnull,'default_expression',rec.typdefault,'input_oid',rec.typinput::pg_catalog.oid::pg_catalog.text,'output_oid',rec.typoutput::pg_catalog.oid::pg_catalog.text,'receive_oid',rec.typreceive::pg_catalog.oid::pg_catalog.text,'send_oid',rec.typsend::pg_catalog.oid::pg_catalog.text,'typmod_in_oid',rec.typmodin::pg_catalog.oid::pg_catalog.text,'typmod_out_oid',rec.typmodout::pg_catalog.oid::pg_catalog.text,'analyze_oid',rec.typanalyze::pg_catalog.oid::pg_catalog.text,'subscript_oid',rec.typsubscript::pg_catalog.oid::pg_catalog.text),'acl_is_null',rec.typacl IS NULL,'effective_acl',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('grantor_oid',grantor::pg_catalog.text,'grantee_oid',grantee::pg_catalog.text,'privilege_kind',privilege_type,'grantable',is_grantable) ORDER BY grantor,grantee,privilege_type COLLATE "C",is_grantable) FROM pg_catalog.aclexplode(CASE WHEN rec.typelem<>0 AND rec.typcategory='A' THEN COALESCE(rec.element_acl,pg_catalog.acldefault('T',rec.element_owner)) ELSE COALESCE(rec.typacl,pg_catalog.acldefault('T',rec.typowner)) END)),'[]'::pg_catalog.jsonb)));
  END LOOP;
  FOR rec IN SELECT co.*,n.nspname::pg_catalog.text AS namespace FROM pg_catalog.pg_constraint co JOIN pg_catalog.pg_namespace n ON n.oid=co.connamespace WHERE co.conrelid=ANY(classids) OR co.contypid=ANY(typeids) LOOP
    rows := rows || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('kind','constraint','namespace',rec.namespace,'identity',rec.conname::pg_catalog.text,'oid',rec.oid::pg_catalog.text,'owner_oid',NULL,'owner_name',NULL,'attributes',pg_catalog.jsonb_build_object('relation_oid',rec.conrelid::pg_catalog.text,'domain_oid',rec.contypid::pg_catalog.text,'type',rec.contype::pg_catalog.text,'key_columns',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(x::pg_catalog.text ORDER BY ord)) FROM pg_catalog.unnest(rec.conkey) WITH ORDINALITY u(x,ord)),'foreign_fields',pg_catalog.jsonb_build_object('table',rec.confrelid::pg_catalog.text,'keys',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(x::pg_catalog.text ORDER BY ord)) FROM pg_catalog.unnest(rec.confkey) WITH ORDINALITY u(x,ord)),'update',rec.confupdtype::pg_catalog.text,'delete',rec.confdeltype::pg_catalog.text,'match',rec.confmatchtype::pg_catalog.text),'deferrable',rec.condeferrable,'deferred',rec.condeferred,'validated',rec.convalidated,'index_oid',rec.conindid::pg_catalog.text,'parent_oid',rec.conparentid::pg_catalog.text,'inherited',rec.coninhcount::pg_catalog.text,'local',rec.conislocal,'no_inherit',rec.connoinherit,'definition',pg_catalog.pg_get_constraintdef(rec.oid,false)),'acl_is_null',NULL,'effective_acl',NULL));
  END LOOP;
  FOR rec IN SELECT i.*,c.relname::pg_catalog.text AS index_name,n.nspname::pg_catalog.text AS namespace FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE i.indexrelid=ANY(classids) LOOP
    rows := rows || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('kind','index','namespace',rec.namespace,'identity',rec.index_name,'oid',rec.indexrelid::pg_catalog.text,'owner_oid',NULL,'owner_name',NULL,'attributes',pg_catalog.jsonb_build_object('relation_oid',rec.indrelid::pg_catalog.text,'access_method',(SELECT a.amname::pg_catalog.text FROM pg_catalog.pg_class c JOIN pg_catalog.pg_am a ON a.oid=c.relam WHERE c.oid=rec.indexrelid),'key_count',rec.indnkeyatts::pg_catalog.text,'total_count',rec.indnatts::pg_catalog.text,'unique',rec.indisunique,'primary',rec.indisprimary,'exclusion',rec.indisexclusion,'immediate',rec.indimmediate,'valid',rec.indisvalid,'ready',rec.indisready,'live',rec.indislive,'nulls_not_distinct',rec.indnullsnotdistinct,'key_columns',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(x::pg_catalog.text ORDER BY ord)) FROM pg_catalog.unnest(rec.indkey::pg_catalog.int2[]) WITH ORDINALITY u(x,ord)),'opclasses',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(x::pg_catalog.text ORDER BY ord)) FROM pg_catalog.unnest(rec.indclass::pg_catalog.oid[]) WITH ORDINALITY u(x,ord)),'collations',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(x::pg_catalog.text ORDER BY ord)) FROM pg_catalog.unnest(rec.indcollation::pg_catalog.oid[]) WITH ORDINALITY u(x,ord)),'options',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(x::pg_catalog.text ORDER BY ord)) FROM pg_catalog.unnest(rec.indoption::pg_catalog.int2[]) WITH ORDINALITY u(x,ord)),'expressions',CASE WHEN rec.indexprs IS NULL THEN NULL ELSE pg_catalog.pg_get_expr(rec.indexprs,rec.indrelid,false) END,'predicate',CASE WHEN rec.indpred IS NULL THEN NULL ELSE pg_catalog.pg_get_expr(rec.indpred,rec.indrelid,false) END,'definition',pg_catalog.pg_get_indexdef(rec.indexrelid,0,false)),'acl_is_null',NULL,'effective_acl',NULL));
  END LOOP;
  FOR rec IN SELECT d.* FROM pg_catalog.pg_depend d WHERE (classid='pg_catalog.pg_class'::pg_catalog.regclass AND objid=ANY(classids)) OR (classid='pg_catalog.pg_type'::pg_catalog.regclass AND objid=ANY(typeids)) OR (classid='pg_catalog.pg_proc'::pg_catalog.regclass AND objid=ANY(procids)) OR (classid='pg_catalog.pg_constraint'::pg_catalog.regclass AND objid IN(SELECT oid FROM pg_catalog.pg_constraint WHERE conrelid=ANY(classids))) OR (classid='pg_catalog.pg_namespace'::pg_catalog.regclass AND objid=ANY(nsids)) LOOP
    IF rec.refclassid='pg_catalog.pg_namespace'::pg_catalog.regclass THEN
      IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE oid=rec.refobjid AND (oid=ANY(nsids) OR nspname IN('pg_catalog','pg_toast'))) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    ELSIF rec.refclassid='pg_catalog.pg_type'::pg_catalog.regclass THEN
      IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace WHERE t.oid=rec.refobjid AND (t.oid=ANY(typeids) OR n.nspname='pg_catalog')) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    ELSIF rec.refclassid='pg_catalog.pg_proc'::pg_catalog.regclass THEN
      IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE p.oid=rec.refobjid AND (p.oid=ANY(procids) OR n.nspname='pg_catalog')) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    ELSIF rec.refclassid='pg_catalog.pg_class'::pg_catalog.regclass THEN
      IF NOT rec.refobjid=ANY(classids) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    ELSIF rec.refclassid='pg_catalog.pg_language'::pg_catalog.regclass THEN
      IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_language WHERE oid=rec.refobjid AND lanname='plpgsql' AND lanpltrusted) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    ELSIF rec.refclassid='pg_catalog.pg_collation'::pg_catalog.regclass THEN
      IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_collation c JOIN pg_catalog.pg_namespace n ON n.oid=c.collnamespace WHERE c.oid=rec.refobjid AND n.nspname='pg_catalog') THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    ELSIF rec.refclassid='pg_catalog.pg_operator'::pg_catalog.regclass THEN
      IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_operator o JOIN pg_catalog.pg_namespace n ON n.oid=o.oprnamespace WHERE o.oid=rec.refobjid AND n.nspname='pg_catalog') THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    ELSIF rec.refclassid='pg_catalog.pg_opclass'::pg_catalog.regclass THEN
      IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_opclass o JOIN pg_catalog.pg_namespace n ON n.oid=o.opcnamespace WHERE o.oid=rec.refobjid AND n.nspname='pg_catalog') THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    ELSIF rec.refclassid='pg_catalog.pg_constraint'::pg_catalog.regclass THEN
      IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_constraint WHERE oid=rec.refobjid AND conrelid=ANY(classids)) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    ELSE RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    rows := rows || pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('kind','dependency','namespace',''::pg_catalog.text,'identity',rec.classid::pg_catalog.text||':'||rec.objid::pg_catalog.text||':'||rec.objsubid::pg_catalog.text||':'||rec.refclassid::pg_catalog.text||':'||rec.refobjid::pg_catalog.text||':'||rec.refobjsubid::pg_catalog.text||':'||rec.deptype::pg_catalog.text,'oid',rec.objid::pg_catalog.text,'owner_oid',NULL,'owner_name',NULL,'attributes',pg_catalog.jsonb_build_object('object_class_oid',rec.classid::pg_catalog.text,'object_oid',rec.objid::pg_catalog.text,'object_subid',rec.objsubid::pg_catalog.text,'referenced_class_oid',rec.refclassid::pg_catalog.text,'referenced_oid',rec.refobjid::pg_catalog.text,'referenced_subid',rec.refobjsubid::pg_catalog.text,'type',rec.deptype::pg_catalog.text),'acl_is_null',NULL,'effective_acl',NULL));
  END LOOP;
  FOR rec IN SELECT d.* FROM pg_catalog.pg_shdepend d WHERE dbid=anchor_ref.database_oid AND ((classid='pg_catalog.pg_class'::pg_catalog.regclass AND objid=ANY(classids)) OR (classid='pg_catalog.pg_type'::pg_catalog.regclass AND objid=ANY(typeids)) OR (classid='pg_catalog.pg_proc'::pg_catalog.regclass AND objid=ANY(procids)) OR (classid='pg_catalog.pg_namespace'::pg_catalog.regclass AND objid=ANY(nsids))) LOOP
    IF rec.refclassid<>'pg_catalog.pg_authid'::pg_catalog.regclass OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE oid=rec.refobjid AND (rolname IN('postgres','vn_jupiter_b1_installer','vn_jupiter_b1_sealed_owner') OR oid IN(SELECT session_user_oid FROM vn_jupiter_actor_catalog_research_v3.actor_bindings))) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
    rows:=rows||pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('kind','dependency','namespace','','identity','shared:'||rec.classid::pg_catalog.text||':'||rec.objid::pg_catalog.text||':'||rec.objsubid::pg_catalog.text||':'||rec.refclassid::pg_catalog.text||':'||rec.refobjid::pg_catalog.text||':'||rec.deptype::pg_catalog.text,'oid',rec.objid::pg_catalog.text,'owner_oid',NULL,'owner_name',NULL,'attributes',pg_catalog.jsonb_build_object('object_class_oid',rec.classid::pg_catalog.text,'object_oid',rec.objid::pg_catalog.text,'object_subid',rec.objsubid::pg_catalog.text,'referenced_class_oid',rec.refclassid::pg_catalog.text,'referenced_oid',rec.refobjid::pg_catalog.text,'referenced_subid','0','type',rec.deptype::pg_catalog.text),'acl_is_null',NULL,'effective_acl',NULL));
  END LOOP;
  IF pg_catalog.jsonb_array_length(rows)>1024 THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  SELECT pg_catalog.jsonb_agg(value ORDER BY value->>'kind' COLLATE "C",value->>'namespace' COLLATE "C",value->>'identity' COLLATE "C",(value->>'oid')::pg_catalog.oid) INTO rows FROM pg_catalog.jsonb_array_elements(rows);
  SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('owner_oid',d.defaclrole::pg_catalog.text,'namespace_oid',d.defaclnamespace::pg_catalog.text,'namespace_name',n.nspname::pg_catalog.text,'object_kind',d.defaclobjtype::pg_catalog.text,'acl',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('grantor_oid',grantor::pg_catalog.text,'grantee_oid',grantee::pg_catalog.text,'privilege_kind',privilege_type,'grantable',is_grantable) ORDER BY grantor,grantee,privilege_type COLLATE "C",is_grantable) FROM pg_catalog.aclexplode(d.defaclacl)),'[]'::pg_catalog.jsonb)) ORDER BY d.defaclrole,d.defaclnamespace,d.defaclobjtype),'[]'::pg_catalog.jsonb) INTO defaults FROM pg_catalog.pg_default_acl d LEFT JOIN pg_catalog.pg_namespace n ON n.oid=d.defaclnamespace WHERE d.defaclnamespace=ANY(nsids) OR d.defaclnamespace=0 AND d.defaclrole IN(SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN('postgres','vn_jupiter_b1_installer','vn_jupiter_b1_sealed_owner'));
  SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('database_oid',s.setdatabase::pg_catalog.text,'role_oid',s.setrole::pg_catalog.text,'settings',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(c ORDER BY c COLLATE "C")) FROM pg_catalog.unnest(s.setconfig) c)) ORDER BY s.setdatabase,s.setrole),'[]'::pg_catalog.jsonb) INTO rolecfg FROM pg_catalog.pg_db_role_setting s WHERE s.setdatabase IN(0,anchor_ref.database_oid) AND (s.setrole=0 OR s.setrole IN(SELECT session_user_oid FROM vn_jupiter_actor_catalog_research_v3.actor_bindings) OR s.setrole IN(SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN('postgres','vn_jupiter_b1_installer','vn_jupiter_b1_sealed_owner')));
  SELECT pg_catalog.jsonb_build_object('nodes',pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('oid',oid::pg_catalog.text,'name',rolname::pg_catalog.text,'login',rolcanlogin,'inherit',rolinherit,'superuser',rolsuper,'createdb',rolcreatedb,'createrole',rolcreaterole,'replication',rolreplication,'bypassrls',rolbypassrls,'connection_limit',rolconnlimit::pg_catalog.text,'valid_until',CASE WHEN rolvaliduntil IS NULL THEN NULL ELSE pg_catalog.to_char(rolvaliduntil,'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') END,'rolconfig',(SELECT pg_catalog.to_jsonb(pg_catalog.array_agg(c ORDER BY c COLLATE "C")) FROM pg_catalog.unnest(rolconfig) c)) ORDER BY oid),'edges',(SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('roleid',m.roleid::pg_catalog.text,'member',m.member::pg_catalog.text,'grantor',m.grantor::pg_catalog.text,'admin_option',m.admin_option,'inherit_option',m.inherit_option,'set_option',m.set_option) ORDER BY m.roleid,m.member,m.grantor,m.admin_option,m.inherit_option,m.set_option),'[]'::pg_catalog.jsonb) FROM pg_catalog.pg_auth_members m WHERE m.member IN(SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN('postgres','vn_jupiter_b1_installer','vn_jupiter_b1_sealed_owner')) OR m.roleid IN(SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN('postgres','vn_jupiter_b1_installer','vn_jupiter_b1_sealed_owner')))) INTO protected FROM pg_catalog.pg_roles WHERE rolname IN('postgres','vn_jupiter_b1_installer','vn_jupiter_b1_sealed_owner');
  IF pg_catalog.current_setting('client_encoding')<>'UTF8' OR pg_catalog.current_setting('server_encoding')<>'UTF8' OR pg_catalog.current_setting('TimeZone')<>'UTC' OR pg_catalog.current_setting('DateStyle')<>'ISO, YMD' OR pg_catalog.current_setting('IntervalStyle')<>'postgres' OR pg_catalog.current_setting('standard_conforming_strings')<>'on' OR pg_catalog.current_setting('row_security')<>'on' THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  SELECT pg_catalog.jsonb_build_object('server_version_num',pg_catalog.current_setting('server_version_num'),'server_encoding',pg_catalog.current_setting('server_encoding'),'client_encoding',pg_catalog.current_setting('client_encoding'),'TimeZone',pg_catalog.current_setting('TimeZone'),'DateStyle',pg_catalog.current_setting('DateStyle'),'IntervalStyle',pg_catalog.current_setting('IntervalStyle'),'standard_conforming_strings',pg_catalog.current_setting('standard_conforming_strings'),'row_security',pg_catalog.current_setting('row_security'),'database_metadata',pg_catalog.jsonb_build_object('encoding',d.encoding::pg_catalog.text,'collation',d.datcollate,'ctype',d.datctype,'locale_provider',d.datlocprovider::pg_catalog.text,'locale',d.datlocale,'icu_rules',d.daticurules,'collation_version',d.datcollversion)) INTO runtime FROM pg_catalog.pg_database d WHERE d.oid=anchor_ref.database_oid;
  RETURN pg_catalog.jsonb_build_object('format','ga-jupiter-b1-catalog-manifest-v3','actor_catalog_policy_sha256','2618f8f4239460112df4b7b21138f103f265353233d35e779e874431057a7c06','database_identity',vn_jupiter_actor_catalog_research_v3._installation_preimage()->'database_identity','invariant_runtime',runtime,'catalog_objects',rows,'default_acl_rows',defaults,'database_role_settings',rolecfg,'protected_roles',protected,'bindings_core',vn_jupiter_actor_catalog_research_v3._binding_core(),'expected_function_rows',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('signature',signature,'spec',spec) ORDER BY signature COLLATE "C") FROM vn_jupiter_b1_fixture_anchor.expected_functions),'role_closure',vn_jupiter_actor_catalog_research_v3._role_closure());
END
$b1$;

-- FUNCTION _checked_actor
CREATE FUNCTION vn_jupiter_actor_catalog_research_v3._checked_actor(p_owner pg_catalog.text, p_run pg_catalog.text, p_market pg_catalog.text, p_capability pg_catalog.text)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET DateStyle = 'ISO, YMD'
SET IntervalStyle = 'postgres'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET row_security = 'on'
SET search_path = 'pg_catalog', 'pg_temp'
SET standard_conforming_strings = 'on'
AS $b1$
DECLARE b vn_jupiter_actor_catalog_research_v3.actor_bindings%ROWTYPE; r record; a vn_jupiter_actor_catalog_research_v3.accepted_pins%ROWTYPE; manifest pg_catalog.jsonb; roles pg_catalog.jsonb; catalog pg_catalog.jsonb; m pg_catalog.text; k pg_catalog.text; rs pg_catalog.text; result pg_catalog.jsonb;
BEGIN
  IF p_owner IS NULL OR p_run IS NULL OR p_market IS NULL OR p_capability IS NULL THEN RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='b1_invalid_input'; END IF;
  IF pg_catalog.octet_length(p_owner)+pg_catalog.octet_length(p_run)+pg_catalog.octet_length(p_market)+pg_catalog.octet_length(p_capability)>4096 OR (p_owner ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM TRUE OR (p_run ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM TRUE OR (p_market ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM TRUE OR p_capability NOT IN('verify_actor','read_scoped_binding') THEN RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='b1_invalid_input'; END IF;
  IF current_user::pg_catalog.text <> 'vn_jupiter_b1_sealed_owner' THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  SELECT * INTO STRICT b FROM vn_jupiter_actor_catalog_research_v3.actor_bindings WHERE owner_id=p_owner COLLATE "C" AND run_id=p_run COLLATE "C" AND market_epoch=p_market COLLATE "C" AND session_user_name=session_user::pg_catalog.text AND session_user_oid=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=session_user);
  IF NOT p_capability=ANY(b.capabilities) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  SELECT * INTO STRICT r FROM vn_jupiter_b1_fixture_anchor.installer_reference WHERE singleton;
  SELECT * INTO STRICT a FROM vn_jupiter_actor_catalog_research_v3.accepted_pins WHERE singleton;
  IF a.actor_catalog_package_sha256 IS DISTINCT FROM r.actor_catalog_package_sha256 OR a.installation_manifest_sha256 IS DISTINCT FROM r.installation_manifest_sha256 OR a.catalog_manifest_sha256 IS DISTINCT FROM r.catalog_manifest_sha256 OR a.role_closure_sha256 IS DISTINCT FROM r.role_closure_sha256 OR EXISTS(SELECT 1 FROM vn_jupiter_actor_catalog_research_v3.actor_bindings WHERE installation_manifest_sha256 IS DISTINCT FROM r.installation_manifest_sha256) THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  manifest:=vn_jupiter_actor_catalog_research_v3._installation_preimage(); roles:=vn_jupiter_actor_catalog_research_v3._role_closure(); catalog:=vn_jupiter_actor_catalog_research_v3._catalog_preimage();
  m:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(vn_jupiter_actor_catalog_research_v3._c14n(manifest),'UTF8')),'hex'); rs:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(vn_jupiter_actor_catalog_research_v3._c14n(roles),'UTF8')),'hex'); k:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(vn_jupiter_actor_catalog_research_v3._c14n(catalog),'UTF8')),'hex');
  IF m IS DISTINCT FROM r.installation_manifest_sha256 OR rs IS DISTINCT FROM r.role_closure_sha256 OR k IS DISTINCT FROM r.catalog_manifest_sha256 THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  result:=pg_catalog.jsonb_build_object('format','ga-jupiter-actor-catalog-evidence-research-v3-b1-v3','actor_catalog_policy_sha256','2618f8f4239460112df4b7b21138f103f265353233d35e779e874431057a7c06','scope',pg_catalog.jsonb_build_object('owner_id',b.owner_id,'run_id',b.run_id,'market_epoch',b.market_epoch),'principal_binding_id',b.principal_binding_id,'session_user_oid',b.session_user_oid::pg_catalog.text,'session_user_name',b.session_user_name,'profile',b.profile,'capability_checked',p_capability,'actor_catalog_package_sha256',r.actor_catalog_package_sha256,'installation_manifest_sha256',m,'accepted_catalog_sha256',r.catalog_manifest_sha256,'observed_catalog_sha256',k,'role_closure_sha256',rs,'limits','{"availability_authority":false,"calibrated_clock":false,"capture_retention":false,"committed_packet_readback":false,"complete_inventory":false,"epoch_registry":false,"history_seal":false,"hosted_authority":false,"lease_authority":false,"live_trading_authority":false,"model_native_join":false,"native_source_admission":false,"original_identity_registry":false,"provider_attested":false,"running_authority":false,"source_freshness":false,"terminal_resolution":false}'::pg_catalog.jsonb);
  IF pg_catalog.octet_length(vn_jupiter_actor_catalog_research_v3._c14n(result))>8192 THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  RETURN result;
END
$b1$;

-- FUNCTION verify_scoped_actor
CREATE FUNCTION vn_jupiter_actor_catalog_research_v3.verify_scoped_actor(owner_id pg_catalog.text, run_id pg_catalog.text, market_epoch pg_catalog.text, required_capability pg_catalog.text)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET DateStyle = 'ISO, YMD'
SET IntervalStyle = 'postgres'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET row_security = 'on'
SET search_path = 'pg_catalog', 'pg_temp'
SET standard_conforming_strings = 'on'
AS $b1$
BEGIN
  IF owner_id IS NULL OR run_id IS NULL OR market_epoch IS NULL OR required_capability IS NULL THEN RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='b1_invalid_input'; END IF;
  RETURN vn_jupiter_actor_catalog_research_v3._checked_actor(owner_id,run_id,market_epoch,required_capability);
EXCEPTION WHEN SQLSTATE '22023' THEN RAISE;
  WHEN OTHERS THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused';
END
$b1$;

-- FUNCTION get_scoped_binding
CREATE FUNCTION vn_jupiter_actor_catalog_research_v3.get_scoped_binding(owner_id pg_catalog.text, run_id pg_catalog.text, market_epoch pg_catalog.text, requested_binding_id pg_catalog.text)
RETURNS pg_catalog.jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
CALLED ON NULL INPUT PARALLEL UNSAFE COST 100
SET DateStyle = 'ISO, YMD'
SET IntervalStyle = 'postgres'
SET TimeZone = 'UTC'
SET client_encoding = 'UTF8'
SET row_security = 'on'
SET search_path = 'pg_catalog', 'pg_temp'
SET standard_conforming_strings = 'on'
AS $b1$
DECLARE evidence pg_catalog.jsonb; result pg_catalog.jsonb;
BEGIN
  IF owner_id IS NULL OR run_id IS NULL OR market_epoch IS NULL OR requested_binding_id IS NULL THEN RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='b1_invalid_input'; END IF;
  IF pg_catalog.octet_length(owner_id)+pg_catalog.octet_length(run_id)+pg_catalog.octet_length(market_epoch)+pg_catalog.octet_length(requested_binding_id)>4096 OR (requested_binding_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM TRUE THEN RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='b1_invalid_input'; END IF;
  evidence:=vn_jupiter_actor_catalog_research_v3._checked_actor(owner_id,run_id,market_epoch,'read_scoped_binding');
  result:=pg_catalog.jsonb_build_object('format','ga-jupiter-actor-catalog-binding-lookup-research-v3-b1-v3','actor_catalog_policy_sha256','2618f8f4239460112df4b7b21138f103f265353233d35e779e874431057a7c06','scope',evidence->'scope','requested_binding_id',requested_binding_id,'resolution',CASE WHEN requested_binding_id=evidence->>'principal_binding_id' THEN 'found' ELSE 'absent' END,'evidence',CASE WHEN requested_binding_id=evidence->>'principal_binding_id' THEN evidence ELSE NULL END,'limits','{"availability_authority":false,"calibrated_clock":false,"capture_retention":false,"committed_packet_readback":false,"complete_inventory":false,"epoch_registry":false,"history_seal":false,"hosted_authority":false,"lease_authority":false,"live_trading_authority":false,"model_native_join":false,"native_source_admission":false,"original_identity_registry":false,"provider_attested":false,"running_authority":false,"source_freshness":false,"terminal_resolution":false}'::pg_catalog.jsonb);
  IF pg_catalog.octet_length(vn_jupiter_actor_catalog_research_v3._c14n(result))>8192 THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused'; END IF;
  RETURN result;
EXCEPTION WHEN SQLSTATE '22023' THEN RAISE;
  WHEN OTHERS THEN RAISE EXCEPTION USING ERRCODE='55000', MESSAGE='b1_actor_catalog_refused';
END
$b1$;

REVOKE ALL ON FUNCTION vn_jupiter_actor_catalog_research_v3._c14n(pg_catalog.jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION vn_jupiter_actor_catalog_research_v3._binding_core() FROM PUBLIC;
REVOKE ALL ON FUNCTION vn_jupiter_actor_catalog_research_v3._role_closure() FROM PUBLIC;
REVOKE ALL ON FUNCTION vn_jupiter_actor_catalog_research_v3._installation_preimage() FROM PUBLIC;
REVOKE ALL ON FUNCTION vn_jupiter_actor_catalog_research_v3._catalog_preimage() FROM PUBLIC;
REVOKE ALL ON FUNCTION vn_jupiter_actor_catalog_research_v3._checked_actor(pg_catalog.text,pg_catalog.text,pg_catalog.text,pg_catalog.text) FROM PUBLIC;
REVOKE ALL ON FUNCTION vn_jupiter_actor_catalog_research_v3.verify_scoped_actor(pg_catalog.text,pg_catalog.text,pg_catalog.text,pg_catalog.text) FROM PUBLIC;
REVOKE ALL ON FUNCTION vn_jupiter_actor_catalog_research_v3.get_scoped_binding(pg_catalog.text,pg_catalog.text,pg_catalog.text,pg_catalog.text) FROM PUBLIC;
