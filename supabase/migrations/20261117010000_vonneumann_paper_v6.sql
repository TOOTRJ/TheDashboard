-- Dashboard-only continuous paper ledger. No wallet/signing authority.
-- Apply after exact project verification. Roll back by closing worker and revoking
-- its login; retain immutable evidence. This namespace is not exposed to PostgREST.
BEGIN;
CREATE ROLE vn_paper_v6_client NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE SCHEMA vn_paper_v6;
REVOKE ALL ON SCHEMA vn_paper_v6 FROM PUBLIC;
GRANT USAGE ON SCHEMA vn_paper_v6 TO vn_paper_v6_client;
CREATE TABLE vn_paper_v6.bindings (
 login name PRIMARY KEY, owner_id uuid NOT NULL REFERENCES auth.users(id), run_id uuid NOT NULL,
 expires_at timestamptz NOT NULL, UNIQUE(owner_id, run_id)
);
CREATE TABLE vn_paper_v6.runs (
 owner_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL DEFAULT 0,
 head text, bytes bigint NOT NULL DEFAULT 0, PRIMARY KEY(owner_id,run_id),
 CHECK(revision>=0 AND bytes BETWEEN 0 AND 1073741824)
);
CREATE TABLE vn_paper_v6.entries (
 owner_id uuid NOT NULL, run_id uuid NOT NULL, command_id uuid NOT NULL,
 sequence bigint NOT NULL CHECK(sequence>0), sha256 text NOT NULL,
 wire bytea NOT NULL CHECK(octet_length(wire) BETWEEN 1 AND 524288),
 accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(owner_id,run_id,command_id), UNIQUE(owner_id,run_id,sequence)
);
CREATE TABLE vn_paper_v6.rejections (
 owner_id uuid NOT NULL, run_id uuid NOT NULL, command_id uuid NOT NULL,
 wire bytea NOT NULL CHECK(octet_length(wire) BETWEEN 1 AND 524288),
 stop_request_id uuid NOT NULL, accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(owner_id,run_id,command_id)
);
CREATE TABLE vn_paper_v6.artifacts (
 owner_id uuid NOT NULL, run_id uuid NOT NULL, sequence bigint GENERATED ALWAYS AS IDENTITY,
 kind text NOT NULL CHECK(kind IN ('mark','history','series')),
 sha256 text NOT NULL CHECK(sha256 ~ '^[a-f0-9]{64}$'),
 wire bytea NOT NULL CHECK(octet_length(wire) BETWEEN 1 AND 8388608),
 PRIMARY KEY(owner_id,run_id,kind,sha256), UNIQUE(sequence)
);
CREATE TABLE vn_paper_v6.sources (
 owner_id uuid NOT NULL, run_id uuid NOT NULL, packet_id uuid NOT NULL,
 sequence bigint GENERATED ALWAYS AS IDENTITY, sha256 text NOT NULL,
 wire bytea NOT NULL CHECK(octet_length(wire) BETWEEN 1 AND 1048576),
 accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(), receipt_sha256 text NOT NULL,
 PRIMARY KEY(owner_id,run_id,packet_id), UNIQUE(sequence)
);
CREATE TABLE vn_paper_v6.controls (
 owner_id uuid NOT NULL, run_id uuid NOT NULL, request_id uuid NOT NULL,
 sequence bigint GENERATED ALWAYS AS IDENTITY, action text NOT NULL CHECK(action IN ('start','stop')),
 accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(owner_id,run_id,request_id), UNIQUE(sequence)
);
ALTER TABLE vn_paper_v6.bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_paper_v6.runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_paper_v6.entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_paper_v6.rejections ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_paper_v6.artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_paper_v6.sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE vn_paper_v6.controls ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA vn_paper_v6 FROM PUBLIC, anon, authenticated, service_role;

CREATE FUNCTION vn_paper_v6.rpc(operation text, body jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $f$
DECLARE
 b vn_paper_v6.bindings%ROWTYPE; r vn_paper_v6.runs%ROWTYPE;
 e vn_paper_v6.entries%ROWTYPE; a vn_paper_v6.artifacts%ROWTYPE; j vn_paper_v6.rejections%ROWTYPE;
 s vn_paper_v6.sources%ROWTYPE; c vn_paper_v6.controls%ROWTYPE;
 raw bytea; document jsonb; digest text; key_id uuid; n integer; after_seq bigint;
 result jsonb; stamp timestamptz;
BEGIN
 SELECT * INTO STRICT b FROM vn_paper_v6.bindings WHERE login=session_user::name AND expires_at>clock_timestamp();
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=session_user AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR NOT rolcanlogin OR rolvaliduntil<=clock_timestamp())) THEN
  RAISE EXCEPTION 'paper_principal_refused' USING ERRCODE='42501';
 END IF;
 IF jsonb_typeof(body)<>'object' OR body->>'owner_id' IS DISTINCT FROM b.owner_id::text OR body->>'run_id' IS DISTINCT FROM b.run_id::text THEN
  RAISE EXCEPTION 'paper_scope_refused' USING ERRCODE='42501';
 END IF;
 -- Serialize both source quota and transition/control ordering for this run.
 INSERT INTO vn_paper_v6.runs(owner_id,run_id) VALUES(b.owner_id,b.run_id) ON CONFLICT DO NOTHING;
 SELECT * INTO STRICT r FROM vn_paper_v6.runs WHERE owner_id=b.owner_id AND run_id=b.run_id FOR UPDATE;
 -- A queued operation cannot retain an authorization that expired or changed
 -- while it waited. Preserve the original scope instead of switching bindings.
 -- This is a post-lock check, not a deferred COMMIT deadline; the caller also
 -- owns an eight-second transaction timeout.
 IF NOT EXISTS(SELECT 1 FROM vn_paper_v6.bindings WHERE login=session_user::name
    AND owner_id=b.owner_id AND run_id=b.run_id AND expires_at>clock_timestamp())
    OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname=session_user AND
       (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR NOT rolcanlogin OR rolvaliduntil<=clock_timestamp())) THEN
  RAISE EXCEPTION 'paper_principal_refused' USING ERRCODE='42501';
 END IF;
 IF operation='append' THEN
  key_id=(body->>'command_id')::uuid; raw=decode(body->>'wire','base64');
  SELECT * INTO e FROM vn_paper_v6.entries WHERE owner_id=b.owner_id AND run_id=b.run_id AND command_id=key_id;
  IF FOUND THEN
   IF e.wire IS DISTINCT FROM raw THEN RAISE EXCEPTION 'paper_original_conflict'; END IF;
  ELSE
   SELECT * INTO j FROM vn_paper_v6.rejections WHERE owner_id=b.owner_id AND run_id=b.run_id AND command_id=key_id;
   IF FOUND THEN
    IF j.wire IS DISTINCT FROM raw THEN RAISE EXCEPTION 'paper_original_conflict'; END IF;
    RETURN jsonb_build_object('refused',true,'reason','stop_committed','wire',encode(j.wire,'base64'),'stop_request_id',j.stop_request_id);
   END IF;
   IF octet_length(raw) NOT BETWEEN 1 AND 524288 THEN RAISE EXCEPTION 'paper_entry_bound'; END IF;
   document=convert_from(raw,'UTF8')::jsonb;
   -- Validate the original against its own expected predecessor before checking
   -- Stop. A late original may be valid but stale against the now-stopped head;
   -- its durable refusal must remain independently reconcilable by original ID.
   IF jsonb_typeof(document) IS DISTINCT FROM 'object'
      OR document->>'format' IS DISTINCT FROM 'dashboard-prospective-paper-journal-v1'
      OR document->>'owner_id' IS DISTINCT FROM b.owner_id::text OR document->>'run_id' IS DISTINCT FROM b.run_id::text
      OR document->>'command_id' IS DISTINCT FROM key_id::text
      OR body->>'expected_sequence' IS NULL OR (body->>'expected_sequence')::bigint<0
      OR ((body->>'expected_sequence')::bigint=0 AND body->>'expected_sha256' IS NOT NULL)
      OR ((body->>'expected_sequence')::bigint>0 AND coalesce(body->>'expected_sha256' !~ '^[a-f0-9]{64}$',true))
      OR (document->>'sequence')::bigint IS DISTINCT FROM (body->>'expected_sequence')::bigint+1
      OR document->>'previous_sha256' IS DISTINCT FROM body->>'expected_sha256'
      OR jsonb_typeof(document->'candidate_wire') IS DISTINCT FROM 'string'
      OR coalesce(document->>'candidate_sha256' !~ '^[a-f0-9]{64}$',true)
      OR encode(sha256(convert_to(document->>'candidate_wire','UTF8')),'hex') IS DISTINCT FROM document->>'candidate_sha256' THEN
    RAISE EXCEPTION 'paper_entry_refused';
   END IF;
   SELECT * INTO c FROM vn_paper_v6.controls WHERE owner_id=b.owner_id AND run_id=b.run_id ORDER BY sequence DESC LIMIT 1;
   IF c.action IS DISTINCT FROM 'start' AND NOT (c.action='stop' AND (document->'witness'->>'kind'='epoch_rollover' OR (document->'witness'->>'kind'='control' AND document->'witness'->>'action'='stop'))) THEN
    IF c.action IS DISTINCT FROM 'stop' THEN RAISE EXCEPTION 'paper_control_closed'; END IF;
    INSERT INTO vn_paper_v6.rejections(owner_id,run_id,command_id,wire,stop_request_id)
     VALUES(b.owner_id,b.run_id,key_id,raw,c.request_id) RETURNING * INTO j;
    UPDATE vn_paper_v6.runs SET bytes=bytes+octet_length(raw) WHERE owner_id=b.owner_id AND run_id=b.run_id;
    RETURN jsonb_build_object('refused',true,'reason','stop_committed','wire',encode(j.wire,'base64'),'stop_request_id',j.stop_request_id);
   END IF;
   IF (body->>'expected_sequence')::bigint IS DISTINCT FROM r.revision OR body->>'expected_sha256' IS DISTINCT FROM r.head THEN
    RAISE EXCEPTION 'paper_revision_conflict';
   END IF;
   INSERT INTO vn_paper_v6.entries(owner_id,run_id,command_id,sequence,sha256,wire)
    VALUES(b.owner_id,b.run_id,key_id,r.revision+1,encode(sha256(raw),'hex'),raw) RETURNING * INTO e;
   UPDATE vn_paper_v6.runs SET revision=e.sequence,head=e.sha256,bytes=bytes+octet_length(raw) WHERE owner_id=b.owner_id AND run_id=b.run_id;
  END IF;
  RETURN jsonb_build_object('wire',encode(e.wire,'base64'));
 ELSIF operation='get' THEN
  SELECT * INTO e FROM vn_paper_v6.entries WHERE owner_id=b.owner_id AND run_id=b.run_id AND command_id=(body->>'command_id')::uuid;
  IF FOUND THEN RETURN jsonb_build_object('wire',encode(e.wire,'base64')); END IF;
  SELECT * INTO j FROM vn_paper_v6.rejections WHERE owner_id=b.owner_id AND run_id=b.run_id AND command_id=(body->>'command_id')::uuid;
  RETURN CASE WHEN FOUND THEN jsonb_build_object('refused',true,'reason','stop_committed','wire',encode(j.wire,'base64'),'stop_request_id',j.stop_request_id) ELSE 'null'::jsonb END;
 ELSIF operation='scan' THEN
  n=(body->>'limit')::integer; after_seq=(body->>'after_sequence')::bigint;
  IF n IS NULL OR after_seq IS NULL OR n NOT BETWEEN 1 AND 25 OR after_seq<0 THEN RAISE EXCEPTION 'paper_page_bound'; END IF;
  SELECT coalesce(jsonb_agg(jsonb_build_object('wire',encode(t.wire,'base64')) ORDER BY t.sequence),'[]'::jsonb) INTO result FROM
   (SELECT * FROM vn_paper_v6.entries WHERE owner_id=b.owner_id AND run_id=b.run_id AND sequence>after_seq ORDER BY sequence LIMIT n) t;
  RETURN result;
 ELSIF operation='put_artifact' THEN
  raw=decode(body->>'wire','base64'); digest=body->>'sha256'; document=convert_from(raw,'UTF8')::jsonb;
  IF document->>'format' IS DISTINCT FROM 'dashboard-prospective-source-recipe-v1' OR document->>'kind' IS DISTINCT FROM body->>'kind'
   OR document->>'sha256' IS DISTINCT FROM digest THEN RAISE EXCEPTION 'paper_artifact_refused'; END IF;
  SELECT * INTO a FROM vn_paper_v6.artifacts WHERE owner_id=b.owner_id AND run_id=b.run_id AND kind=body->>'kind' AND sha256=digest;
  IF FOUND THEN IF a.wire IS DISTINCT FROM raw THEN RAISE EXCEPTION 'paper_original_conflict'; END IF;
  ELSE
   INSERT INTO vn_paper_v6.artifacts(owner_id,run_id,kind,sha256,wire) VALUES(b.owner_id,b.run_id,body->>'kind',digest,raw) RETURNING * INTO a;
   UPDATE vn_paper_v6.runs SET bytes=bytes+octet_length(raw) WHERE owner_id=b.owner_id AND run_id=b.run_id;
  END IF;
  RETURN jsonb_build_object('wire',encode(a.wire,'base64'));
 ELSIF operation='get_artifact' THEN
  SELECT * INTO a FROM vn_paper_v6.artifacts WHERE owner_id=b.owner_id AND run_id=b.run_id AND kind=body->>'kind' AND sha256=body->>'sha256';
  RETURN CASE WHEN FOUND THEN jsonb_build_object('wire',encode(a.wire,'base64')) ELSE 'null'::jsonb END;
 ELSIF operation='artifact_inventory' THEN
  n=(body->>'limit')::integer; after_seq=(body->>'after_sequence')::bigint;
  IF n IS NULL OR after_seq IS NULL OR n NOT BETWEEN 1 AND 25 OR after_seq<0 THEN RAISE EXCEPTION 'paper_page_bound'; END IF;
  -- Bound both row count and cumulative retained bytes before JSON/base64.
  -- One8MiBrecipe still fits alone; many small mark recipes share a page.
  SELECT coalesce(jsonb_agg(jsonb_build_object('sequence',t.sequence,'kind',t.kind,'sha256',t.sha256,'wire',encode(t.wire,'base64')) ORDER BY t.sequence),'[]'::jsonb) INTO result FROM
   (SELECT q.*,sum(octet_length(q.wire)) OVER(ORDER BY q.sequence) AS page_bytes FROM
    (SELECT * FROM vn_paper_v6.artifacts WHERE owner_id=b.owner_id AND run_id=b.run_id AND sequence>after_seq ORDER BY sequence LIMIT n) q) t
   WHERE t.page_bytes<=8388608;
  RETURN result;
 ELSIF operation IN ('admit_source','get_source','seal_sources') THEN
  key_id=(body->>'packet_id')::uuid;
  SELECT * INTO s FROM vn_paper_v6.sources WHERE owner_id=b.owner_id AND run_id=b.run_id AND packet_id=key_id;
  IF operation IN ('admit_source','seal_sources') THEN
   raw=decode(body->>'wire','base64');
   IF FOUND THEN IF s.wire IS DISTINCT FROM raw THEN RAISE EXCEPTION 'paper_original_conflict'; END IF;
   ELSE
    IF operation='seal_sources' THEN
     document=convert_from(raw,'UTF8')::jsonb;
     IF document->>'kind' IS DISTINCT FROM 'seal'
      OR document->>'start_second' IS NULL OR document->>'end_second' IS NULL
      OR document->>'through_ingest_sequence' IS NULL OR document->>'records_sha256' IS NULL
      OR (document->>'start_second')::bigint<0 OR (document->>'through_ingest_sequence')::bigint<1
      OR (document->>'start_second')::bigint % 900 <> 0 OR (document->>'end_second')::bigint % 900 <> 0
      OR (document->>'end_second')::bigint-(document->>'start_second')::bigint NOT IN (54900,1800)
      OR (document->>'end_second')::bigint*1000000+5000000>extract(epoch FROM clock_timestamp())*1000000
      OR document->>'records_sha256' !~ '^[a-f0-9]{64}$'
      OR (document->>'through_ingest_sequence')::bigint>coalesce((SELECT max(sequence) FROM vn_paper_v6.sources WHERE owner_id=b.owner_id AND run_id=b.run_id),0) THEN
      RAISE EXCEPTION 'paper_seal_refused';
     END IF;
    END IF;
    stamp=clock_timestamp();digest=encode(sha256(raw),'hex');
    INSERT INTO vn_paper_v6.sources(owner_id,run_id,packet_id,sha256,wire,accepted_at,receipt_sha256)
     VALUES(b.owner_id,b.run_id,key_id,digest,raw,stamp,encode(sha256(convert_to(b.owner_id::text||'/'||b.run_id::text||'/'||key_id::text||'/'||digest||'/'||stamp::text,'UTF8')),'hex')) RETURNING * INTO s;
    UPDATE vn_paper_v6.runs SET bytes=bytes+octet_length(raw) WHERE owner_id=b.owner_id AND run_id=b.run_id;
   END IF;
  END IF;
  IF s.packet_id IS NULL THEN RETURN 'null'::jsonb; END IF;
  RETURN jsonb_build_object('packet_id',s.packet_id,'sequence',s.sequence,'sha256',s.sha256,'wire',encode(s.wire,'base64'),
   'accepted_at_us',(extract(epoch FROM s.accepted_at)*1000000)::bigint,'sealed_at_us',(extract(epoch FROM s.accepted_at)*1000000)::bigint,'available_at_upper_us',ceil(extract(epoch FROM clock_timestamp())*1000000)::bigint,'receipt_sha256',s.receipt_sha256);
 ELSIF operation='source_inventory' THEN
  n=(body->>'limit')::integer;after_seq=(body->>'after_sequence')::bigint;
  IF n IS NULL OR after_seq IS NULL OR n NOT BETWEEN 1 AND 25 OR after_seq<0 THEN RAISE EXCEPTION 'paper_page_bound'; END IF;
  SELECT coalesce(jsonb_agg(jsonb_build_object('packet_id',t.packet_id,'sequence',t.sequence,'sha256',t.sha256,'wire',encode(t.wire,'base64'),
   'accepted_at_us',(extract(epoch FROM t.accepted_at)*1000000)::bigint,'receipt_sha256',t.receipt_sha256) ORDER BY t.sequence),'[]'::jsonb) INTO result FROM
   (SELECT q.*,sum(octet_length(q.wire)) OVER(ORDER BY q.sequence) AS page_bytes FROM
    (SELECT * FROM vn_paper_v6.sources WHERE owner_id=b.owner_id AND run_id=b.run_id AND sequence>after_seq ORDER BY sequence LIMIT n) q) t
   WHERE t.page_bytes<=8388608;
  RETURN result;
 ELSIF operation='control' THEN
  key_id=(body->>'request_id')::uuid;
  SELECT * INTO c FROM vn_paper_v6.controls WHERE owner_id=b.owner_id AND run_id=b.run_id AND request_id=key_id;
  IF FOUND THEN IF c.action IS DISTINCT FROM body->>'action' THEN RAISE EXCEPTION 'paper_original_conflict'; END IF;
  ELSE
   INSERT INTO vn_paper_v6.controls(owner_id,run_id,request_id,action) VALUES(b.owner_id,b.run_id,key_id,body->>'action') RETURNING * INTO c;
  END IF;
  RETURN to_jsonb(c);
 ELSIF operation='latest_control' THEN
  SELECT * INTO c FROM vn_paper_v6.controls WHERE owner_id=b.owner_id AND run_id=b.run_id ORDER BY sequence DESC LIMIT 1;
  RETURN CASE WHEN FOUND THEN to_jsonb(c) ELSE 'null'::jsonb END;
 ELSIF operation='head' THEN
  RETURN jsonb_build_object('sequence',r.revision,'sha256',r.head,'bytes',r.bytes);
 ELSE RAISE EXCEPTION 'paper_operation_refused';
 END IF;
END $f$;
REVOKE ALL ON FUNCTION vn_paper_v6.rpc(text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION vn_paper_v6.rpc(text,jsonb) TO vn_paper_v6_client;
COMMIT;
