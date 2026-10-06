-- Verify the installed callable inventory, source bodies and explicit/effective
-- capabilities before COMMIT. A caller GUC is only an accidental-use guard.
DO $$
DECLARE item record; actual oid; api record; allowed boolean;
BEGIN
 IF (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      WHERE n.nspname IN ('vn_identity','vn_durability','vn_projection','vn_read'))<>-- EXPECTED_FUNCTION_COUNT
    OR (SELECT count(*) FROM pg_namespace WHERE nspname IN ('vn_identity','vn_durability','vn_projection','vn_read'))<>4 OR
    (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname IN ('vn_durability','vn_projection') AND c.relkind='r')<>18 OR
    EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_durability','vn_projection') AND
      (c.relowner<>'vn_contract_owner'::regrole OR (c.relkind='r' AND NOT c.relrowsecurity))) OR
    EXISTS(SELECT 1 FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_durability','vn_projection')) OR
    EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
      LATERAL aclexplode(c.relacl) a WHERE n.nspname IN ('vn_durability','vn_projection')
      AND (a.grantee<>c.relowner OR a.is_grantable)) OR
    EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_durability','vn_projection') AND a.attacl IS NOT NULL) THEN
  RAISE EXCEPTION 'canonical_table_postcondition_failed'; END IF;
 FOR item IN SELECT * FROM (VALUES
-- EXPECTED_FUNCTIONS
 ) e(signature,body_hash,execute_role,owner_role) LOOP
  actual:=to_regprocedure(item.signature);
  IF actual IS NULL OR NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid=actual AND
     proowner=item.owner_role::regrole AND encode(sha256(convert_to(prosrc,'UTF8')),'hex')=item.body_hash AND
     proconfig IN (ARRAY['search_path=pg_catalog, vn_durability, pg_temp'],
                   ARRAY['search_path=pg_catalog, vn_projection, pg_temp'],
                   ARRAY['search_path=pg_catalog, pg_temp'])) OR
     EXISTS(SELECT 1 FROM pg_proc p,LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
       WHERE p.oid=actual AND (a.is_grantable OR
         a.grantee NOT IN (p.proowner,coalesce(to_regrole(item.execute_role),p.proowner)))) THEN
   RAISE EXCEPTION 'canonical_function_postcondition_failed: %',item.signature; END IF;
  FOR api IN SELECT oid,rolname FROM pg_roles WHERE rolname IN
    ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay') LOOP
   allowed:=coalesce(api.rolname=item.execute_role,false);
   IF has_function_privilege(api.oid,actual,'EXECUTE') IS DISTINCT FROM allowed OR
      has_function_privilege(api.oid,actual,'EXECUTE WITH GRANT OPTION') THEN
    RAISE EXCEPTION 'canonical_capability_postcondition_failed: %, %',item.signature,api.rolname; END IF;
  END LOOP;
 END LOOP;
 -- Newly-created roles must stay inert; installing a credential is a later gate.
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('vn_economic','vn_relay') AND
    (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit OR rolreplication OR rolbypassrls)) OR
    EXISTS(SELECT 1 FROM pg_auth_members WHERE member IN ('vn_economic'::regrole,'vn_relay'::regrole)) OR
    EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid IN ('vn_economic'::regrole,'vn_relay'::regrole) AND
      (member<>'postgres'::regrole OR grantor<>10 OR NOT admin_option OR inherit_option OR set_option)) OR
    (SELECT count(*) FROM pg_auth_members WHERE roleid IN ('vn_economic'::regrole,'vn_relay'::regrole))<>2 THEN
  RAISE EXCEPTION 'canonical_role_postcondition_failed'; END IF;
 FOR api IN SELECT oid,rolname FROM pg_roles WHERE rolname IN
    ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay') LOOP
  IF pg_has_role(api.oid,'vn_contract_owner','SET') OR pg_has_role(api.oid,'vn_contract_owner','USAGE') OR
     has_schema_privilege(api.oid,'vn_identity','USAGE') OR
     has_schema_privilege(api.oid,'vn_durability','CREATE') OR
     has_schema_privilege(api.oid,'vn_projection','USAGE') OR
     has_schema_privilege(api.oid,'vn_read','CREATE') OR
     EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE n.nspname IN ('vn_durability','vn_projection') AND c.relkind='r' AND
        (has_table_privilege(api.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR
         has_any_column_privilege(api.oid,c.oid,'SELECT,INSERT,UPDATE,REFERENCES'))) THEN
   RAISE EXCEPTION 'canonical_raw_authority_postcondition_failed: %',api.rolname; END IF;
 END LOOP;
END $$;
