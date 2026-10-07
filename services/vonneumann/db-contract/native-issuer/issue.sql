-- Fixture-only templates receive validated synthetic values through stdin.
BEGIN;
SET LOCAL lock_timeout='500ms';
SET LOCAL statement_timeout='6s';
SET LOCAL transaction_timeout='10s';
SET LOCAL createrole_self_grant='';
SET LOCAL password_encryption='scram-sha-256';
DO $issuer$
DECLARE
-- INPUT_DECLARATIONS
 stamp timestamptz; deadline timestamptz; leaf text; index integer; principal oid;
BEGIN
-- CHECK_LIMITED_ISSUER
 IF names[1]=names[2] OR issuance_ids[1]=issuance_ids[2] OR
  EXISTS(SELECT 1 FROM pg_roles WHERE rolname=ANY(names)) THEN
  RAISE EXCEPTION 'native_issuer_fresh_names_required' USING ERRCODE='42710';
 END IF;
 EXECUTE 'SET LOCAL ROLE vn_contract_owner';
 IF EXISTS(SELECT 1 FROM vn_access.bindings WHERE principal_name=ANY(names) OR issuance_id=ANY(issuance_ids)) THEN
  RAISE EXCEPTION 'native_issuer_fresh_bindings_required' USING ERRCODE='42710';
 END IF;
 EXECUTE 'RESET ROLE';
 stamp:=clock_timestamp(); deadline:=stamp+recovery_seconds*interval '1 second';
 FOR index IN 1..2 LOOP
  leaf:=CASE index WHEN 1 THEN 'vn_economic' ELSE 'vn_relay' END;
  EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD %L VALID UNTIL %L',
    names[index],verifiers[index],deadline);
  EXECUTE format('GRANT %I TO %I WITH ADMIN FALSE,INHERIT FALSE,SET TRUE GRANTED BY postgres',leaf,names[index]);
 END LOOP;
 EXECUTE 'SET LOCAL ROLE vn_contract_owner';
 INSERT INTO vn_access.bindings(issuance_id,principal_oid,principal_name,capability,owner_id,run_id,
  issued_at,not_before,expires_at,recovery_until)
 SELECT issuance_ids[i],r.oid,r.rolname,CASE i WHEN 1 THEN 'economic' ELSE 'relay' END,owner_id_input,run_id_input,
  stamp,stamp+delay_seconds*interval '1 second',stamp+write_seconds*interval '1 second',deadline
 FROM generate_series(1,2) i JOIN pg_roles r ON r.rolname=names[i];
 IF NOT FOUND THEN RAISE EXCEPTION 'native_issuer_binding_missing'; END IF;
 EXECUTE 'RESET ROLE';
 FOR index IN 1..2 LOOP
  SELECT oid INTO STRICT principal FROM pg_roles WHERE rolname=names[index];
  leaf:=CASE index WHEN 1 THEN 'vn_economic' ELSE 'vn_relay' END;
  IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE oid=principal AND NOT rolcanlogin AND NOT rolsuper AND
    NOT rolcreatedb AND NOT rolcreaterole AND NOT rolinherit AND NOT rolreplication AND NOT rolbypassrls AND
    rolconnlimit=2 AND rolvaliduntil=deadline) OR
   (SELECT count(*) FROM pg_auth_members WHERE member=principal)<>1 OR
   NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=principal AND roleid=leaf::regrole AND
     grantor='postgres'::regrole AND NOT admin_option AND NOT inherit_option AND set_option) OR
   (SELECT count(*) FROM pg_auth_members WHERE roleid=principal)<>1 OR
   NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid=principal AND member='postgres'::regrole AND
     grantor=10 AND admin_option AND NOT inherit_option AND NOT set_option) OR
   EXISTS(SELECT 1 FROM pg_db_role_setting WHERE setrole=principal) THEN
   RAISE EXCEPTION 'native_issuer_role_postcondition_failed' USING ERRCODE='42501';
  END IF;
  EXECUTE format('ALTER ROLE %I LOGIN',names[index]);
 END LOOP;
 EXECUTE 'SET LOCAL ROLE vn_contract_owner';
 IF (SELECT count(*) FROM vn_access.bindings WHERE issuance_id=ANY(issuance_ids) AND
   principal_name=ANY(names) AND owner_id=owner_id_input AND run_id=run_id_input AND
   issued_at=stamp AND not_before=stamp+delay_seconds*interval '1 second' AND
   expires_at=stamp+write_seconds*interval '1 second' AND recovery_until=deadline AND revoked_at IS NULL)<>2 THEN
  RAISE EXCEPTION 'native_issuer_pair_postcondition_failed' USING ERRCODE='42501';
 END IF;
 EXECUTE 'RESET ROLE';
END $issuer$;
-- AFTER_ISSUANCE
COMMIT;
