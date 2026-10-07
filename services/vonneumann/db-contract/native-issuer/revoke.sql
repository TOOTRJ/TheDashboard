-- Exact pair only. Preserve bindings and acknowledged economic history.
BEGIN;
SET LOCAL lock_timeout='500ms';
SET LOCAL statement_timeout='6s';
SET LOCAL transaction_timeout='10s';
DO $issuer$
DECLARE
-- INPUT_DECLARATIONS
 binding record; stamp timestamptz; index integer; seen integer:=0;
BEGIN
-- CHECK_LIMITED_ISSUER
 FOR index IN 1..2 LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE oid=principal_oids[index] AND rolname=names[index] AND
    NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolinherit AND
    NOT rolreplication AND NOT rolbypassrls AND rolconnlimit BETWEEN 1 AND 2) OR
   NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE roleid=principal_oids[index] AND member='postgres'::regrole AND
     grantor=10 AND admin_option AND NOT inherit_option AND NOT set_option) THEN
   RAISE EXCEPTION 'native_revocation_identity_changed' USING ERRCODE='42501';
  END IF;
 END LOOP;
 EXECUTE 'SET LOCAL ROLE vn_contract_owner';
 FOR binding IN SELECT * FROM vn_access.bindings WHERE issuance_id=ANY(issuance_ids)
   ORDER BY principal_name FOR UPDATE LOOP
  index:=array_position(issuance_ids,binding.issuance_id);
  IF binding.principal_oid<>principal_oids[index] OR binding.principal_name<>names[index] OR
   binding.owner_id<>owner_id_input OR binding.run_id<>run_id_input OR
   binding.capability<>(CASE index WHEN 1 THEN 'economic' ELSE 'relay' END) THEN
   RAISE EXCEPTION 'native_revocation_binding_changed' USING ERRCODE='42501';
  END IF;
  seen:=seen+1;
 END LOOP;
 IF seen<>2 THEN RAISE EXCEPTION 'native_revocation_pair_missing' USING ERRCODE='42501'; END IF;
 stamp:=clock_timestamp();
 UPDATE vn_access.bindings SET revoked_at=stamp WHERE issuance_id=ANY(issuance_ids) AND revoked_at IS NULL;
 EXECUTE 'RESET ROLE';
 -- BEFORE_ROLE_DISABLE
 FOR index IN 1..2 LOOP EXECUTE format('ALTER ROLE %I NOLOGIN',names[index]); END LOOP;
 -- Revalidate after DDL acquires each role's catalog tuple lock. A concurrent
 -- drop/recreate between the first check and ALTER must roll back all effects.
 FOR index IN 1..2 LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE oid=principal_oids[index] AND rolname=names[index] AND
    NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolinherit AND
    NOT rolreplication AND NOT rolbypassrls AND rolconnlimit BETWEEN 1 AND 2) THEN
   RAISE EXCEPTION 'native_revocation_identity_changed' USING ERRCODE='42501';
  END IF;
 END LOOP;
 EXECUTE 'SET LOCAL ROLE vn_contract_owner';
 IF (SELECT count(*) FROM vn_access.bindings WHERE issuance_id=ANY(issuance_ids) AND revoked_at IS NOT NULL)<>2 OR
  EXISTS(SELECT 1 FROM pg_roles WHERE oid=ANY(principal_oids) AND rolcanlogin) THEN
  RAISE EXCEPTION 'native_revocation_postcondition_failed' USING ERRCODE='42501';
 END IF;
 EXECUTE 'RESET ROLE';
END $issuer$;
-- AFTER_REVOCATION
COMMIT;
