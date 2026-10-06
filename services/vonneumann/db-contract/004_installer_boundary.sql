-- DB-03A2D3B2A isolated installer-boundary rehearsal ONLY.
-- Not a migration, production installation runner, or credential provisioner.
-- This transaction is combined with hash-pinned laboratory SQL by the tests.
BEGIN;
SET LOCAL lock_timeout='500ms';
SET LOCAL statement_timeout='15s';
DO $$
DECLARE installer pg_catalog.pg_roles%ROWTYPE;
BEGIN
 IF current_setting('dashboard.contract_rehearsal',true) IS DISTINCT FROM 'db03a1-isolated' THEN
  RAISE EXCEPTION 'isolated_installer_rehearsal_required';
 END IF;
 SELECT * INTO installer FROM pg_catalog.pg_roles WHERE rolname=current_user;
 IF current_setting('server_version_num')::integer NOT BETWEEN 170000 AND 179999 OR
    current_user<>'postgres' OR session_user<>'postgres' OR installer.rolsuper OR
    NOT installer.rolcreaterole OR NOT installer.rolcreatedb OR NOT installer.rolbypassrls OR
    NOT installer.rolinherit OR installer.rolreplication THEN
  RAISE EXCEPTION 'hosted_like_installer_required';
 END IF;
 IF NOT pg_catalog.has_database_privilege(current_user,current_database(),'CREATE') OR
    NOT pg_catalog.has_schema_privilege(current_user,'auth','USAGE') OR
    NOT pg_catalog.has_function_privilege(current_user,'auth.uid()','EXECUTE') OR
    NOT pg_catalog.has_column_privilege(current_user,'auth.users','id','REFERENCES') OR
    pg_catalog.has_schema_privilege(current_user,'auth','USAGE WITH GRANT OPTION') OR
    pg_catalog.has_function_privilege(current_user,'auth.uid()','EXECUTE WITH GRANT OPTION') OR
    pg_catalog.has_column_privilege(current_user,'auth.users','id','REFERENCES WITH GRANT OPTION') THEN
  RAISE EXCEPTION 'measured_auth_dependency_permissions_required';
 END IF;
 IF EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='vn_contract_owner') OR
    EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname IN
      ('vn_identity','vn_durability','vn_projection','vn_read')) THEN
  RAISE EXCEPTION 'fresh_installer_rehearsal_required';
 END IF;
 IF (SELECT count(*) FROM pg_catalog.pg_roles WHERE rolname IN
      ('anon','authenticated','service_role','authenticator'))<>4 OR
    EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname IN
      ('anon','authenticated','service_role','authenticator') AND
      (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication OR
       EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members m WHERE m.member=r.oid AND m.admin_option))) THEN
  RAISE EXCEPTION 'api_role_authority_requires_review';
 END IF;
END $$;

SET LOCAL createrole_self_grant='';
CREATE ROLE vn_contract_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
 NOINHERIT NOREPLICATION NOBYPASSRLS;
-- PostgreSQL 17 creator ADMIN membership does not imply SET or inheritance.
-- Explicitly permit installation without inheriting the private owner by default.
-- Preserve the bootstrap-granted ADMIN-only row; a separate self-granted row
-- enables SET. Granting ADMIN back to one's own grantor is rejected by PG17.
GRANT vn_contract_owner TO postgres WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;

-- Keep the privileged identity bridge owned by the installer, in a schema the
-- private owner cannot CREATE in. No arguments, dynamic SQL or custom claim parser.
CREATE SCHEMA vn_identity AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA vn_identity FROM PUBLIC,anon,authenticated,service_role,authenticator;
CREATE FUNCTION vn_identity.owner_id() RETURNS uuid
 LANGUAGE sql STABLE SECURITY DEFINER
 SET search_path=pg_catalog,pg_temp AS $$ SELECT auth.uid() $$;
REVOKE ALL ON FUNCTION vn_identity.owner_id()
 FROM PUBLIC,anon,authenticated,service_role,authenticator;
GRANT USAGE ON SCHEMA vn_identity TO vn_contract_owner;
GRANT EXECUTE ON FUNCTION vn_identity.owner_id() TO vn_contract_owner;

DO $$
DECLARE owner_role oid:='vn_contract_owner'::regrole; installer_role oid:='postgres'::regrole;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE oid=owner_role AND
      NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND
      NOT rolinherit AND NOT rolreplication AND NOT rolbypassrls) OR
    NOT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname='vn_identity' AND nspowner=installer_role) OR
    NOT EXISTS(SELECT 1 FROM pg_catalog.pg_proc WHERE oid='vn_identity.owner_id()'::regprocedure AND
      proowner=installer_role AND prosecdef AND provolatile='s' AND pronargs=0 AND
      proconfig=ARRAY['search_path=pg_catalog, pg_temp']) OR
    EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members
   WHERE (member=owner_role) OR (roleid=owner_role AND
     (member<>installer_role OR inherit_option OR
      NOT ((grantor=10 AND admin_option AND NOT set_option) OR
           (grantor=installer_role AND NOT admin_option AND set_option))))) OR
    (SELECT count(*) FROM pg_catalog.pg_auth_members WHERE roleid=owner_role)<>2 OR
    NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE roleid=owner_role AND
      member=installer_role AND grantor=10 AND admin_option AND NOT set_option AND NOT inherit_option) OR
    NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE roleid=owner_role AND
      member=installer_role AND grantor=installer_role AND NOT admin_option AND set_option AND NOT inherit_option) OR
    pg_catalog.has_schema_privilege(owner_role,'auth','USAGE') OR
    pg_catalog.has_function_privilege(owner_role,'auth.uid()','EXECUTE') OR
    pg_catalog.has_column_privilege(owner_role,'auth.users','id','REFERENCES') OR
    pg_catalog.has_schema_privilege(owner_role,'vn_identity','CREATE') OR
    NOT pg_catalog.has_function_privilege(owner_role,'vn_identity.owner_id()','EXECUTE') OR
    EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname IN
      ('anon','authenticated','service_role','authenticator') AND
      (pg_catalog.pg_has_role(r.oid,owner_role,'SET') OR
       pg_catalog.pg_has_role(r.oid,owner_role,'USAGE') OR
       pg_catalog.has_schema_privilege(r.oid,'vn_identity','USAGE') OR
       pg_catalog.has_function_privilege(r.oid,'vn_identity.owner_id()','EXECUTE'))) OR
    EXISTS(SELECT 1 FROM pg_catalog.pg_proc p,
      LATERAL pg_catalog.aclexplode(p.proacl) a WHERE p.oid='vn_identity.owner_id()'::regprocedure
      AND (a.grantee NOT IN (owner_role,installer_role) OR a.is_grantable)) THEN
  RAISE EXCEPTION 'installer_boundary_postcondition_failed';
 END IF;
END $$;
COMMIT;
