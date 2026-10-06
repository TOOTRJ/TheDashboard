-- Fresh native-login binding candidate. No login/password is provisioned here.
RESET ROLE;
CREATE SCHEMA vn_access AUTHORIZATION vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
GRANT USAGE,CREATE ON SCHEMA vn_access TO postgres;
RESET ROLE;
-- Existing non-grantable Auth REFERENCES is sufficient; no managed Auth edit.
CREATE TABLE vn_access.bindings (
 issuance_id uuid PRIMARY KEY,
 principal_oid oid UNIQUE NOT NULL,
 principal_name text UNIQUE NOT NULL CHECK(principal_name ~ '^vn_native_[a-f0-9]{32}$'),
 capability text NOT NULL CHECK(capability IN ('economic','relay')),
 owner_id uuid NOT NULL REFERENCES auth.users(id),
 run_id uuid NOT NULL,
 issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 not_before timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 recovery_until timestamptz NOT NULL,
 revoked_at timestamptz,
 CHECK(isfinite(issued_at) AND isfinite(not_before) AND isfinite(expires_at) AND isfinite(recovery_until)),
 CHECK(issued_at <= not_before AND not_before < expires_at AND expires_at <= recovery_until),
 CHECK(expires_at <= issued_at + interval '2 hours' AND recovery_until <= issued_at + interval '24 hours'),
 CHECK(revoked_at IS NULL OR (isfinite(revoked_at) AND revoked_at >= issued_at))
);
ALTER TABLE vn_access.bindings OWNER TO vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
REVOKE USAGE,CREATE ON SCHEMA vn_access FROM postgres;
ALTER TABLE vn_access.bindings ENABLE ROW LEVEL SECURITY;

CREATE FUNCTION vn_access.immutable_binding() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF TG_OP='DELETE' OR
    (to_jsonb(NEW)-'revoked_at') IS DISTINCT FROM (to_jsonb(OLD)-'revoked_at') OR
    OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL OR NEW.revoked_at > clock_timestamp() THEN
  RAISE EXCEPTION 'binding_immutable' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_binding BEFORE UPDATE OR DELETE ON vn_access.bindings
FOR EACH ROW EXECUTE FUNCTION vn_access.immutable_binding();

-- INVOKER-only private helper, called inside the reviewed SECURITY DEFINER RPCs.
-- session_user survives SET ROLE and SECURITY DEFINER; caller JWT/GUCs do not
-- authenticate native SQL. The direct-connection profile requires real SCRAM.
-- TLS enforcement belongs to verified client configuration and hosted server
-- policy: pg_stat_ssl is redacted under SET ROLE/SECURITY DEFINER. Do not grant
-- broad statistics access just to read it. Poolers need a separate hosted proof.
CREATE FUNCTION vn_access.require_actor(owner_id uuid, run uuid, capability text, operation text)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
DECLARE binding vn_access.bindings%ROWTYPE; principal pg_catalog.pg_roles%ROWTYPE;
        required_role oid; observed timestamptz;
BEGIN
 SELECT * INTO principal FROM pg_catalog.pg_roles WHERE rolname=session_user;
 IF NOT FOUND OR NOT principal.rolcanlogin OR principal.rolsuper OR principal.rolcreatedb OR
    principal.rolcreaterole OR principal.rolinherit OR principal.rolreplication OR principal.rolbypassrls OR
    principal.rolconnlimit NOT BETWEEN 1 AND 2 OR
    system_user IS DISTINCT FROM ('scram-sha-256:' || session_user::text) OR
    inet_client_addr() IS NULL THEN
  RAISE EXCEPTION 'principal_denied' USING ERRCODE='42501';
 END IF;
 required_role:=CASE capability WHEN 'economic' THEN 'vn_economic'::regrole
                               WHEN 'relay' THEN 'vn_relay'::regrole END;
 IF required_role IS NULL OR operation NOT IN
   ('create_run','heartbeat','commit_command','get_command','interrupt_expired',
    'read_outbox','acknowledge_event','accept_event') OR
    (capability='economic') IS DISTINCT FROM
      (operation IN ('create_run','heartbeat','commit_command','get_command','interrupt_expired')) OR
    (SELECT count(*) FROM pg_catalog.pg_auth_members WHERE member=principal.oid)<>1 OR
    NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=principal.oid AND roleid=required_role
      AND NOT admin_option AND NOT inherit_option AND set_option) THEN
  RAISE EXCEPTION 'principal_denied' USING ERRCODE='42501';
 END IF;
 -- Serialize revocation with any admitted transaction. Recheck the wall clock
 -- after acquiring the lock and before each successful RPC return, including
 -- idempotent replay. Expiry after journal/projection effects rolls them back.
 SELECT * INTO binding FROM vn_access.bindings WHERE principal_oid=principal.oid
   AND principal_name=session_user::text FOR SHARE;
 observed:=clock_timestamp();
 IF NOT FOUND OR binding.owner_id IS DISTINCT FROM owner_id OR binding.run_id IS DISTINCT FROM run OR
    binding.capability IS DISTINCT FROM capability OR binding.revoked_at IS NOT NULL OR
    observed < binding.not_before OR principal.rolvaliduntil IS NULL OR
    NOT isfinite(principal.rolvaliduntil) OR principal.rolvaliduntil > binding.recovery_until OR
    principal.rolvaliduntil < binding.expires_at OR observed >= principal.rolvaliduntil OR
    observed >= (CASE WHEN operation='get_command' THEN binding.recovery_until ELSE binding.expires_at END) THEN
  RAISE EXCEPTION 'principal_denied' USING ERRCODE='42501';
 END IF;
END $$;

REVOKE ALL ON SCHEMA vn_access FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON ALL TABLES IN SCHEMA vn_access FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_access FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
RESET ROLE;
