-- Additive release admission. Readback, relay, owner reads and conservative
-- expiry interruption remain available when retired; no economic row is erased.
CREATE SCHEMA vn_release AUTHORIZATION vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
REVOKE ALL ON SCHEMA vn_release FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
ALTER DEFAULT PRIVILEGES IN SCHEMA vn_release REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
CREATE TABLE vn_release.state (
 singleton boolean PRIMARY KEY CHECK(singleton),
 release_sha256 text NOT NULL CHECK(release_sha256 ~ '^[0-9a-f]{64}$'),
 state text NOT NULL CHECK(state IN ('closed','open','retired')),
 epoch bigint NOT NULL CHECK(epoch>=0), installed_at timestamptz NOT NULL,
 install_review jsonb NOT NULL CHECK(jsonb_typeof(install_review)='object' AND octet_length(install_review::text)<=524288),
 install_catalog jsonb NOT NULL CHECK(jsonb_typeof(install_catalog)='object' AND octet_length(install_catalog::text)<=1048576)
);
CREATE TABLE vn_release.operations (
 request_id uuid PRIMARY KEY, request jsonb NOT NULL, receipt jsonb NOT NULL,
 recorded_at timestamptz NOT NULL
);
ALTER TABLE vn_release.state ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_release.operations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA vn_release FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
INSERT INTO vn_release.state VALUES(true,'-- RELEASE_ID','closed',0,clock_timestamp(),
 current_setting('dashboard.forward_review')::jsonb,'{}');

CREATE FUNCTION vn_release.require_open() RETURNS void LANGUAGE plpgsql VOLATILE
SET search_path=pg_catalog,vn_release,pg_temp AS $$
DECLARE observed text;
BEGIN
 IF (SELECT install_catalog FROM vn_release.state WHERE singleton) IS DISTINCT FROM vn_release.catalog() THEN
  RAISE EXCEPTION 'release_catalog_drift' USING ERRCODE='55000';
 END IF;
 IF current_setting('transaction_isolation')<>'read committed' THEN
  RAISE EXCEPTION 'release_read_committed_required' USING ERRCODE='55000';
 END IF;
 SELECT state INTO STRICT observed FROM vn_release.state WHERE singleton FOR SHARE;
 IF observed<>'open' THEN
  RAISE EXCEPTION 'release_admission_closed' USING ERRCODE='55000';
 END IF;
END $$;

CREATE FUNCTION vn_release.transition(request_id uuid,expected_epoch bigint,
 target_state text,evidence_sha256 text) RETURNS jsonb LANGUAGE plpgsql VOLATILE
SET search_path=pg_catalog,vn_release,pg_temp AS $$
DECLARE observed vn_release.state%ROWTYPE; original vn_release.operations%ROWTYPE;
 request_body jsonb; result jsonb;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
    OR current_setting('lock_timeout')::interval<=interval '0'
    OR current_setting('lock_timeout')::interval>interval '500 milliseconds'
    OR current_setting('statement_timeout')::interval<=interval '0'
    OR current_setting('statement_timeout')::interval>interval '8 seconds' THEN
  RAISE EXCEPTION 'bounded_release_transaction_required' USING ERRCODE='55000';
 END IF;
 IF request_id IS NULL OR expected_epoch IS NULL OR expected_epoch<0
    OR target_state IS NULL OR target_state NOT IN ('open','retired')
    OR evidence_sha256 IS NULL OR evidence_sha256 !~ '^[0-9a-f]{64}$' THEN
  RAISE EXCEPTION 'invalid_release_transition' USING ERRCODE='22023';
 END IF;
 SELECT * INTO STRICT observed FROM vn_release.state WHERE singleton FOR UPDATE;
 request_body:=jsonb_build_object('request_id',request_id,'expected_epoch',expected_epoch,
   'target_state',target_state,'evidence_sha256',evidence_sha256,'release_sha256',observed.release_sha256);
 SELECT * INTO original FROM vn_release.operations o WHERE o.request_id=transition.request_id;
 IF FOUND THEN
  IF original.request IS DISTINCT FROM request_body THEN
   RAISE EXCEPTION 'release_command_conflict' USING ERRCODE='55000';
  END IF;
  RETURN original.receipt;
 END IF;
 IF observed.install_catalog IS DISTINCT FROM vn_release.catalog() THEN
  RAISE EXCEPTION 'release_catalog_drift' USING ERRCODE='55000';
 END IF;
 IF observed.epoch<>expected_epoch OR observed.state='retired'
    OR (target_state='open' AND observed.state<>'closed') THEN
  RAISE EXCEPTION 'release_transition_conflict' USING ERRCODE='55000';
 END IF;
 UPDATE vn_release.state SET state=target_state,epoch=observed.epoch+1 WHERE singleton;
 result:=request_body||jsonb_build_object('epoch',observed.epoch+1,'previous_state',observed.state,
   'new_state',target_state,'recorded_at',clock_timestamp(),
   'economic_rows_preserved',true,'legacy_writes_restored',false);
 INSERT INTO vn_release.operations VALUES(request_id,request_body,result,clock_timestamp());
 RETURN result;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_release FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay;
RESET ROLE;
