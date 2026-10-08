-- Isolated C3B1 experiment only. No production installer or credential runner.
IF current_setting('dashboard.native_issuer_rehearsal',true) IS DISTINCT FROM 'c3b1-isolated' THEN
 RAISE EXCEPTION 'isolated_native_issuer_required' USING ERRCODE='42501';
END IF;
IF current_setting('server_version_num')::integer NOT BETWEEN 170000 AND 179999 OR
 session_user<>'postgres' OR current_user<>'postgres' OR
 NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='postgres' AND NOT rolsuper AND
   rolcreaterole AND rolcreatedb AND rolinherit AND rolbypassrls AND rolreplication) THEN
 RAISE EXCEPTION 'limited_native_issuer_required' USING ERRCODE='42501';
END IF;
IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='vn_contract_owner' AND NOT rolcanlogin AND
 NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolinherit AND
 NOT rolreplication AND NOT rolbypassrls) OR
 NOT pg_has_role('postgres','vn_contract_owner','SET') OR
 (SELECT count(*) FROM pg_auth_members WHERE roleid='vn_contract_owner'::regrole)<>2 OR
 NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid='vn_contract_owner'::regrole AND
   member='postgres'::regrole AND grantor=10 AND admin_option AND NOT inherit_option AND NOT set_option) OR
 NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid='vn_contract_owner'::regrole AND
   member='postgres'::regrole AND grantor='postgres'::regrole AND NOT admin_option AND
   NOT inherit_option AND set_option) OR
 EXISTS(SELECT 1 FROM pg_auth_members WHERE member='vn_contract_owner'::regrole) THEN
 RAISE EXCEPTION 'native_issuer_catalog_requires_review' USING ERRCODE='42501';
END IF;
-- Resolve private object identities under the reviewed SET-only owner. Never
-- grant the installer or API roles additional schema/table privileges.
EXECUTE 'SET LOCAL ROLE vn_contract_owner';
IF NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='vn_access' AND nspowner='vn_contract_owner'::regrole) OR
 NOT EXISTS(SELECT 1 FROM pg_class WHERE oid='vn_access.bindings'::regclass AND
   relowner='vn_contract_owner'::regrole AND relrowsecurity AND NOT relforcerowsecurity) OR
 EXISTS(SELECT 1 FROM pg_policy WHERE polrelid='vn_access.bindings'::regclass) OR
 EXISTS(SELECT 1 FROM pg_class c,LATERAL aclexplode(c.relacl) a WHERE c.oid='vn_access.bindings'::regclass AND
   (a.grantee<>c.relowner OR a.is_grantable)) OR
 EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid='vn_access.bindings'::regclass AND attacl IS NOT NULL) OR
 EXISTS(SELECT 1 FROM pg_namespace n,LATERAL aclexplode(n.nspacl) a WHERE n.nspname='vn_access' AND
   (a.grantee<>n.nspowner OR a.is_grantable)) THEN
 RAISE EXCEPTION 'native_issuer_catalog_requires_review' USING ERRCODE='42501';
END IF;
IF (SELECT count(*) FROM pg_roles WHERE rolname IN ('vn_economic','vn_relay') AND
 NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND
 NOT rolinherit AND NOT rolreplication AND NOT rolbypassrls)<>2 OR
 EXISTS(SELECT 1 FROM pg_auth_members WHERE member IN ('vn_economic'::regrole,'vn_relay'::regrole)) OR
 (SELECT count(*) FROM pg_auth_members WHERE roleid IN ('vn_economic'::regrole,'vn_relay'::regrole) AND
   member='postgres'::regrole AND grantor=10 AND admin_option AND NOT inherit_option AND NOT set_option)<>2 OR
 EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role','authenticator') AND
   (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR
    pg_has_role(oid,'vn_contract_owner','SET') OR pg_has_role(oid,'vn_economic','SET') OR
    pg_has_role(oid,'vn_relay','SET') OR has_schema_privilege(oid,'vn_access','USAGE,CREATE') OR
    has_table_privilege(oid,'vn_access.bindings','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR
    has_any_column_privilege(oid,'vn_access.bindings','SELECT,INSERT,UPDATE,REFERENCES'))) THEN
 RAISE EXCEPTION 'native_issuer_capability_requires_review' USING ERRCODE='42501';
END IF;
EXECUTE 'RESET ROLE';
