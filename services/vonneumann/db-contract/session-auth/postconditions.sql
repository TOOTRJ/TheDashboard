SET LOCAL ROLE vn_contract_owner;
DO $$
DECLARE item record; actual oid; api record;
BEGIN
 IF (SELECT count(*) FROM pg_namespace WHERE nspname='vn_access' AND nspowner='vn_contract_owner'::regrole)<>1 OR
    (SELECT count(*) FROM pg_class WHERE relnamespace='vn_access'::regnamespace AND relkind='r'
      AND relname='bindings' AND relowner='vn_contract_owner'::regrole AND relrowsecurity)<>1 OR
    (SELECT count(*) FROM pg_proc WHERE pronamespace='vn_access'::regnamespace)<>2 OR
    EXISTS(SELECT 1 FROM pg_policy WHERE polrelid='vn_access.bindings'::regclass) OR
    EXISTS(SELECT 1 FROM pg_class c,LATERAL aclexplode(c.relacl) a WHERE c.oid='vn_access.bindings'::regclass
      AND (a.grantee<>c.relowner OR a.is_grantable)) OR
    EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid='vn_access.bindings'::regclass AND attacl IS NOT NULL) OR
    EXISTS(SELECT 1 FROM pg_namespace n,LATERAL aclexplode(n.nspacl) a WHERE n.nspname='vn_access'
      AND (a.grantee<>n.nspowner OR a.is_grantable)) OR
    EXISTS(SELECT 1 FROM pg_proc p,LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
      WHERE p.pronamespace='vn_access'::regnamespace AND
      (p.proowner<>'vn_contract_owner'::regrole OR p.prosecdef OR
       p.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp'] OR
       a.grantee<>p.proowner OR a.is_grantable)) OR
    EXISTS(SELECT 1 FROM vn_access.bindings) THEN
  RAISE EXCEPTION 'native_auth_inventory_failed';
 END IF;
 FOR item IN SELECT * FROM (VALUES
-- EXPECTED_BODIES
 ) e(signature,body_hash) LOOP
  actual:=to_regprocedure(item.signature);
  IF actual IS NULL OR NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid=actual AND
     proowner='vn_contract_owner'::regrole AND encode(sha256(convert_to(prosrc,'UTF8')),'hex')=item.body_hash) THEN
   RAISE EXCEPTION 'native_auth_body_failed: %',item.signature;
  END IF;
 END LOOP;
 FOR api IN SELECT oid,rolname FROM pg_roles WHERE rolname IN
   ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay') LOOP
  IF has_schema_privilege(api.oid,'vn_access','USAGE,CREATE') OR
     has_table_privilege(api.oid,'vn_access.bindings','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR
     has_any_column_privilege(api.oid,'vn_access.bindings','SELECT,INSERT,UPDATE,REFERENCES') OR
     has_function_privilege(api.oid,'vn_access.require_actor(uuid,uuid,text,text)','EXECUTE') OR
     has_function_privilege(api.oid,'vn_access.immutable_binding()','EXECUTE') THEN
   RAISE EXCEPTION 'native_auth_raw_authority_failed: %',api.rolname;
  END IF;
 END LOOP;
END $$;
RESET ROLE;
