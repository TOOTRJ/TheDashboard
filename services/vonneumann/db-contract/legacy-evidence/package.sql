-- DB-03A2D3B2D1 isolated evidence/archive component ONLY; no production runner.
BEGIN;
SET LOCAL lock_timeout='500ms';
SET LOCAL statement_timeout='8s';
DO $$ BEGIN
 IF current_setting('dashboard.contract_rehearsal',true) IS DISTINCT FROM 'db03a1-isolated'
    OR current_user<>'postgres' OR session_user<>'postgres'
    OR (SELECT rolsuper FROM pg_roles WHERE rolname=current_user)
    OR to_regnamespace('vn_legacy') IS NULL OR to_regnamespace('vn_identity') IS NULL
    OR to_regnamespace('vn_legacy_evidence') IS NOT NULL
    OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname='vn_legacy_attestor') THEN
  RAISE EXCEPTION 'fresh_limited_legacy_evidence_rehearsal_required';
 END IF;
END $$;
LOCK TABLE public.vn_colonies,public.vn_fitness_snapshots,public.vn_generation_stats,
 public.vn_probes,public.vn_trades IN ACCESS EXCLUSIVE MODE;
SET LOCAL createrole_self_grant='';
CREATE ROLE vn_legacy_attestor NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
 NOINHERIT NOREPLICATION NOBYPASSRLS;
CREATE SCHEMA vn_legacy_evidence AUTHORIZATION vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
REVOKE ALL ON SCHEMA vn_legacy_evidence FROM PUBLIC,anon,authenticated,service_role,authenticator;
RESET ROLE;

-- A SELECT-only private owner cannot LOCK legacy tables in SHARE mode. This
-- installer-owned, parameterless bridge grants exactly that operation, not DML
-- or MAINTAIN. No caller-controlled table, SQL, role, or claim is accepted.
CREATE FUNCTION vn_identity.lock_legacy_evidence() RETURNS void
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 IF current_setting('transaction_isolation')<>'read committed'
    OR current_setting('lock_timeout')::interval<=interval '0'
    OR current_setting('lock_timeout')::interval>interval '500 milliseconds'
    OR current_setting('statement_timeout')::interval<=interval '0'
    OR current_setting('statement_timeout')::interval>interval '8 seconds' THEN
  RAISE EXCEPTION 'bounded_read_committed_legacy_transaction_required' USING ERRCODE='55000';
 END IF;
 LOCK TABLE public.vn_colonies,public.vn_fitness_snapshots,public.vn_generation_stats,
  public.vn_probes,public.vn_trades IN SHARE MODE;
END $$;
REVOKE ALL ON FUNCTION vn_identity.lock_legacy_evidence()
 FROM PUBLIC,anon,authenticated,service_role,authenticator;
GRANT EXECUTE ON FUNCTION vn_identity.lock_legacy_evidence() TO vn_contract_owner;
-- The existing public RLS expressions call auth.uid() directly. Reading these
-- preserved rows as the private owner would require managed Auth grants. This
-- installer-owned aggregate reader instead uses existing installer privileges,
-- explicit owner/run filters and fixed table names, with no raw row disclosure.
CREATE FUNCTION vn_identity.legacy_rows(owner uuid,run uuid) RETURNS jsonb
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp
 SET timezone='UTC' SET extra_float_digits=3 SET datestyle='ISO,YMD' AS $$
DECLARE table_name text; rows_count bigint; bytes_count bigint; max_bytes bigint;
 total_rows bigint:=0; total_bytes bigint:=0; row_digest text;
 summary jsonb:='{}'; open_ids jsonb; links bigint;
BEGIN
 IF owner IS NULL OR run IS NULL THEN RAISE EXCEPTION 'bound_legacy_scope_required' USING ERRCODE='22023'; END IF;
 FOREACH table_name IN ARRAY ARRAY['vn_colonies','vn_fitness_snapshots','vn_generation_stats','vn_probes','vn_trades'] LOOP
  EXECUTE format('SELECT count(*),coalesce(sum(octet_length(to_jsonb(t)::text)),0),'
    'coalesce(max(octet_length(to_jsonb(t)::text)),0) FROM public.%I t '
    'WHERE user_id=$1 AND %I=$2',table_name,CASE WHEN table_name='vn_colonies' THEN 'id' ELSE 'run_id' END)
    INTO rows_count,bytes_count,max_bytes USING owner,run;
  total_rows:=total_rows+rows_count; total_bytes:=total_bytes+bytes_count;
  IF total_rows>50000 OR total_bytes>33554432 OR max_bytes>131072 THEN
   RAISE EXCEPTION 'legacy_snapshot_budget_exceeded' USING ERRCODE='54000';
  END IF;
  EXECUTE format('SELECT encode(sha256(convert_to(coalesce(string_agg('
    'encode(sha256(convert_to(to_jsonb(t)::text,''UTF8'')),''hex''),'''' ORDER BY id),''''),''UTF8'')),''hex'') '
    'FROM public.%I t WHERE user_id=$1 AND %I=$2',table_name,
    CASE WHEN table_name='vn_colonies' THEN 'id' ELSE 'run_id' END) INTO row_digest USING owner,run;
  summary:=summary||jsonb_build_object(table_name,jsonb_build_object('rows',rows_count,'sha256',row_digest));
 END LOOP;
 IF total_rows=0 THEN RAISE EXCEPTION 'legacy_run_unavailable' USING ERRCODE='P0002'; END IF;
 SELECT coalesce(jsonb_agg(id::text ORDER BY id),'[]') INTO open_ids FROM public.vn_trades
  WHERE user_id=owner AND run_id=run AND closed_at IS NULL;
 SELECT count(*) INTO links FROM (
  SELECT p.id FROM public.vn_probes p WHERE p.user_id=owner AND p.run_id=run AND p.parent_id IS NOT NULL
    AND NOT EXISTS(SELECT 1 FROM public.vn_probes q WHERE q.id=p.parent_id AND q.user_id=owner AND q.run_id=run)
  UNION ALL SELECT t.id FROM public.vn_trades t WHERE t.user_id=owner AND t.run_id=run
    AND NOT EXISTS(SELECT 1 FROM public.vn_probes q WHERE q.id=t.probe_id AND q.user_id=owner AND q.run_id=run)
  UNION ALL SELECT f.id FROM public.vn_fitness_snapshots f WHERE f.user_id=owner AND f.run_id=run
    AND NOT EXISTS(SELECT 1 FROM public.vn_probes q WHERE q.id=f.probe_id AND q.user_id=owner AND q.run_id=run)
 ) unresolved;
 IF jsonb_array_length(open_ids)>200 THEN
  RAISE EXCEPTION 'legacy_exposure_budget_exceeded' USING ERRCODE='54000';
 END IF;
 RETURN jsonb_build_object('tables',summary,'open_trade_ids',open_ids,'unresolved_links',links);
END $$;
REVOKE ALL ON FUNCTION vn_identity.legacy_rows(uuid,uuid)
 FROM PUBLIC,anon,authenticated,service_role,authenticator;
GRANT EXECUTE ON FUNCTION vn_identity.legacy_rows(uuid,uuid) TO vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
ALTER DEFAULT PRIVILEGES IN SCHEMA vn_legacy_evidence REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

CREATE FUNCTION vn_legacy_evidence.tables() RETURNS text[] LANGUAGE sql IMMUTABLE AS $$
  SELECT ARRAY['vn_colonies','vn_fitness_snapshots','vn_generation_stats','vn_probes','vn_trades']::text[]
$$;
CREATE FUNCTION vn_legacy_evidence.catalog() RETURNS jsonb LANGUAGE sql STABLE
SET search_path=pg_catalog,pg_temp AS $$
WITH RECURSIVE
tables AS (
 SELECT c.* FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname=ANY(vn_legacy_evidence.tables())
),
clients AS (
 SELECT oid FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role','authenticator')
),
ancestors AS (
 SELECT oid AS client,oid AS ancestor,ARRAY[oid] AS path FROM clients
 UNION ALL
 SELECT a.client,m.roleid,a.path||m.roleid FROM ancestors a
 JOIN pg_auth_members m ON m.member=a.ancestor
 WHERE NOT m.roleid=ANY(a.path) AND cardinality(a.path)<16
),
functions AS (
 SELECT p.* FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE (n.nspname='public' AND (p.proname LIKE 'vn\_%' ESCAPE '\' OR p.prosrc ~*
   '(vn_colonies|vn_probes|vn_trades|vn_fitness_snapshots|vn_generation_stats)'))
 OR p.oid IN (SELECT tr.tgfoid FROM pg_trigger tr JOIN tables t ON t.oid=tr.tgrelid)
 OR p.oid IN (SELECT d.objid FROM pg_depend d JOIN tables t ON t.oid=d.refobjid
   WHERE d.classid='pg_proc'::regclass AND d.refclassid='pg_class'::regclass)
)
SELECT jsonb_build_object(
 'tables',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',relname,'kind',relkind,
   'owner',pg_get_userbyid(relowner),'rls',relrowsecurity,'force_rls',relforcerowsecurity,
   'replica_identity',relreplident) ORDER BY relname),'[]'::jsonb) FROM tables),
 'columns',(SELECT coalesce(jsonb_agg(jsonb_build_object('table',t.relname,'name',a.attname,
   'ordinal',a.attnum,'type',format_type(a.atttypid,a.atttypmod),'not_null',a.attnotnull,
   'default',pg_get_expr(d.adbin,d.adrelid),'identity',a.attidentity,'generated',a.attgenerated)
   ORDER BY t.relname,a.attnum),'[]'::jsonb) FROM tables t JOIN pg_attribute a ON a.attrelid=t.oid
   LEFT JOIN pg_attrdef d ON d.adrelid=t.oid AND d.adnum=a.attnum WHERE a.attnum>0 AND NOT a.attisdropped),
 'constraints',(SELECT coalesce(jsonb_agg(jsonb_build_object('table',t.relname,'name',c.conname,
   'validated',c.convalidated,'deferrable',c.condeferrable,'initially_deferred',c.condeferred,
   'definition',pg_get_constraintdef(c.oid,true)) ORDER BY t.relname,c.conname),'[]'::jsonb)
   FROM tables t JOIN pg_constraint c ON c.conrelid=t.oid),
 'indexes',(SELECT coalesce(jsonb_agg(jsonb_build_object('table',t.relname,'name',ic.relname,
   'valid',i.indisvalid,'ready',i.indisready,'definition',pg_get_indexdef(i.indexrelid))
   ORDER BY t.relname,ic.relname),'[]'::jsonb) FROM tables t JOIN pg_index i ON i.indrelid=t.oid
   JOIN pg_class ic ON ic.oid=i.indexrelid),
 'policies',(SELECT coalesce(jsonb_agg(jsonb_build_object('table',tablename,'name',policyname,
   'roles',roles,'command',cmd,'permissive',permissive,'using',qual,'check',with_check)
   ORDER BY tablename,policyname),'[]'::jsonb) FROM pg_policies
   WHERE schemaname='public' AND tablename=ANY(vn_legacy_evidence.tables())),
 'triggers',(SELECT coalesce(jsonb_agg(jsonb_build_object('table',t.relname,'name',tr.tgname,
   'enabled',tr.tgenabled,'definition',pg_get_triggerdef(tr.oid,true)) ORDER BY t.relname,tr.tgname),'[]'::jsonb)
   FROM tables t JOIN pg_trigger tr ON tr.tgrelid=t.oid WHERE NOT tr.tgisinternal),
 'table_acl',(SELECT coalesce(jsonb_agg(jsonb_build_object('table',t.relname,
   'grantor',pg_get_userbyid(a.grantor),'grantee',CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
   'privilege',a.privilege_type,'grantable',a.is_grantable)
   ORDER BY t.relname,a.grantee::regrole::text,a.grantor::regrole::text,a.privilege_type),'[]'::jsonb)
   FROM tables t CROSS JOIN LATERAL aclexplode(coalesce(t.relacl,acldefault('r',t.relowner))) a),
 'column_acl',(SELECT coalesce(jsonb_agg(jsonb_build_object('table',t.relname,'column',c.attname,
   'grantor',pg_get_userbyid(a.grantor),'grantee',CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
   'privilege',a.privilege_type,'grantable',a.is_grantable)
   ORDER BY t.relname,c.attnum,a.grantee::regrole::text,a.grantor::regrole::text,a.privilege_type),'[]'::jsonb)
   FROM tables t JOIN pg_attribute c ON c.attrelid=t.oid
   CROSS JOIN LATERAL aclexplode(c.attacl) a WHERE c.attnum>0 AND NOT c.attisdropped),
 'roles',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',r.rolname,'inherit',r.rolinherit,
   'superuser',r.rolsuper,'bypass_rls',r.rolbypassrls,'create_role',r.rolcreaterole,
   'create_db',r.rolcreatedb,'replication',r.rolreplication) ORDER BY r.rolname),'[]'::jsonb)
   FROM pg_roles r WHERE r.oid IN (SELECT ancestor FROM ancestors)),
 'memberships',(SELECT coalesce(jsonb_agg(jsonb_build_object('member',pg_get_userbyid(m.member),
   'role',pg_get_userbyid(m.roleid),'grantor',pg_get_userbyid(m.grantor),'inherit',m.inherit_option,
   'set',m.set_option,'admin',m.admin_option) ORDER BY m.member::regrole::text,m.roleid::regrole::text,m.grantor::regrole::text),'[]'::jsonb)
   FROM pg_auth_members m WHERE m.member IN (SELECT ancestor FROM ancestors)),
 'membership_truncated',EXISTS(SELECT 1 FROM ancestors a JOIN pg_auth_members m ON m.member=a.ancestor
   WHERE cardinality(a.path)=16 AND NOT m.roleid=ANY(a.path)),
 'defaults',(SELECT coalesce(jsonb_agg(jsonb_build_object('role',pg_get_userbyid(d.defaclrole),
   'schema',n.nspname,'type',d.defaclobjtype,'acl',d.defaclacl::text)
   ORDER BY d.defaclrole::regrole::text,n.nspname NULLS FIRST,d.defaclobjtype),'[]'::jsonb)
   FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
   WHERE d.defaclrole IN (SELECT oid FROM pg_roles WHERE rolname IN ('postgres','supabase_admin'))
     AND (d.defaclnamespace=0 OR n.nspname='public')),
 'functions',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,'name',p.proname,
   'arguments',pg_get_function_identity_arguments(p.oid),'owner',pg_get_userbyid(p.proowner),
   'security_definer',p.prosecdef,'definition_md5',md5(pg_get_functiondef(p.oid)),
   'acl',p.proacl::text,'settings',p.proconfig)
   ORDER BY n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)),'[]'::jsonb)
   FROM functions p JOIN pg_namespace n ON n.oid=p.pronamespace),
 'views',(SELECT coalesce(jsonb_agg(DISTINCT jsonb_build_object('schema',n.nspname,'name',v.relname,
   'kind',v.relkind,'owner',pg_get_userbyid(v.relowner),'options',v.reloptions)),'[]'::jsonb)
   FROM tables t JOIN pg_depend d ON d.refobjid=t.oid AND d.refclassid='pg_class'::regclass
   JOIN pg_rewrite rw ON rw.oid=d.objid AND d.classid='pg_rewrite'::regclass
   JOIN pg_class v ON v.oid=rw.ev_class JOIN pg_namespace n ON n.oid=v.relnamespace
   WHERE v.relkind IN ('v','m')),
 'external_foreign_keys',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,
   'table',source.relname,'target',t.relname,'name',c.conname,'definition',pg_get_constraintdef(c.oid,true))
   ORDER BY n.nspname,source.relname,c.conname),'[]'::jsonb)
   FROM tables t JOIN pg_constraint c ON c.confrelid=t.oid AND c.contype='f'
   JOIN pg_class source ON source.oid=c.conrelid JOIN pg_namespace n ON n.oid=source.relnamespace
   WHERE source.oid NOT IN (SELECT oid FROM tables)),
 'sequences',(SELECT coalesce(jsonb_agg(s.oid::regclass::text ORDER BY s.oid::regclass::text),'[]'::jsonb)
   FROM pg_class s WHERE s.relkind='S' AND (
     s.oid IN (SELECT d.objid FROM pg_depend d JOIN tables t ON t.oid=d.refobjid
       WHERE d.classid='pg_class'::regclass AND d.refclassid='pg_class'::regclass)
     OR s.oid IN (SELECT d.refobjid FROM pg_depend d JOIN pg_attrdef a ON a.oid=d.objid
       JOIN tables t ON t.oid=a.adrelid WHERE d.classid='pg_attrdef'::regclass AND d.refclassid='pg_class'::regclass))),
 'realtime_tables',(SELECT coalesce(jsonb_agg(tablename ORDER BY tablename),'[]'::jsonb)
   FROM pg_publication_tables WHERE pubname='supabase_realtime' AND schemaname='public'
     AND tablename=ANY(vn_legacy_evidence.tables()))
)
$$;


CREATE TABLE vn_legacy_evidence.gate (
 singleton boolean PRIMARY KEY CHECK(singleton), revision bigint NOT NULL CHECK(revision>=0),
 baseline jsonb NOT NULL, installed_at timestamptz NOT NULL
);
CREATE TABLE vn_legacy_evidence.changes (
 revision bigint PRIMARY KEY, table_name text NOT NULL, operation text NOT NULL,
 changed_at timestamptz NOT NULL, actor name NOT NULL
);
CREATE TABLE vn_legacy_evidence.reviews (
 request_id uuid PRIMARY KEY, owner_id uuid NOT NULL, run_id uuid NOT NULL,
 snapshot jsonb NOT NULL, document jsonb NOT NULL,
 attestor_oid oid NOT NULL, attestor_name name NOT NULL,
 recorded_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
 receipt jsonb NOT NULL
);
CREATE TABLE vn_legacy_evidence.invalidations (
 request_id uuid PRIMARY KEY, review_id uuid NOT NULL REFERENCES vn_legacy_evidence.reviews(request_id),
 reason text NOT NULL, actor_oid oid NOT NULL, actor_name name NOT NULL,
 recorded_at timestamptz NOT NULL, receipt jsonb NOT NULL
);
CREATE TABLE vn_legacy_evidence.archives (
 sequence bigint PRIMARY KEY CHECK(sequence>0), request_id uuid UNIQUE NOT NULL,
 owner_id uuid NOT NULL, run_id uuid NOT NULL,
 review_id uuid NOT NULL REFERENCES vn_legacy_evidence.reviews(request_id),
 recorded_at timestamptz NOT NULL, receipt jsonb NOT NULL
);
CREATE INDEX legacy_reviews_scope ON vn_legacy_evidence.reviews(owner_id,run_id,recorded_at DESC,request_id DESC);
CREATE INDEX legacy_invalidations_review ON vn_legacy_evidence.invalidations(review_id);
CREATE INDEX legacy_archives_scope ON vn_legacy_evidence.archives(owner_id,run_id,sequence);

CREATE FUNCTION vn_legacy_evidence.current_catalog() RETURNS jsonb
 LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $$
 SELECT vn_legacy_evidence.catalog()||jsonb_build_object('evidence_contract',jsonb_build_object(
  'schemas',(SELECT jsonb_agg(jsonb_build_object('oid',oid,'name',nspname,'owner',nspowner,'acl',nspacl::text) ORDER BY nspname)
   FROM pg_namespace WHERE nspname IN ('vn_legacy_evidence','vn_legacy','vn_identity')),
  'roles',(SELECT jsonb_agg(jsonb_build_object('oid',oid,'name',rolname,'login',rolcanlogin,'super',rolsuper,
   'bypass',rolbypassrls,'create_role',rolcreaterole,'create_db',rolcreatedb,'replication',rolreplication,'inherit',rolinherit) ORDER BY rolname)
   FROM pg_roles WHERE rolname IN ('vn_contract_owner','vn_legacy_attestor')),
  'functions',(SELECT jsonb_agg(jsonb_build_object('oid',p.oid,'owner',p.proowner,'definition',pg_get_functiondef(p.oid),
   'acl',p.proacl::text) ORDER BY p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname IN ('vn_legacy_evidence','vn_legacy') OR
    (n.nspname='vn_identity' AND p.proname IN ('owner_id','lock_legacy_evidence','legacy_rows'))),
  'tables',(SELECT jsonb_agg(jsonb_build_object('oid',c.oid,'owner',c.relowner,'name',c.relname,'kind',c.relkind,
   'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,'acl',c.relacl::text,
   'columns',(SELECT jsonb_agg(jsonb_build_object('name',a.attname,'type',format_type(a.atttypid,a.atttypmod),
     'not_null',a.attnotnull,'acl',a.attacl::text,'default',pg_get_expr(d.adbin,d.adrelid)) ORDER BY a.attnum)
    FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
    WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),
   'constraints',(SELECT jsonb_agg(jsonb_build_object('definition',pg_get_constraintdef(oid,true),'validated',convalidated)
    ORDER BY conname) FROM pg_constraint WHERE conrelid=c.oid),
   'indexes',(SELECT jsonb_agg(jsonb_build_object('definition',pg_get_indexdef(indexrelid),'valid',indisvalid,'ready',indisready)
    ORDER BY indexrelid) FROM pg_index WHERE indrelid=c.oid)) ORDER BY c.relname)
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='vn_legacy_evidence' AND c.relkind='r')
 ))
$$;

CREATE FUNCTION vn_legacy_evidence.bump() RETURNS trigger
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE next_revision bigint;
BEGIN
 IF TG_TABLE_SCHEMA<>'public' OR NOT TG_TABLE_NAME=ANY(vn_legacy_evidence.tables()) THEN
  RAISE EXCEPTION 'unexpected_legacy_invalidation_source';
 END IF;
 UPDATE vn_legacy_evidence.gate SET revision=revision+1 WHERE singleton RETURNING revision INTO STRICT next_revision;
 INSERT INTO vn_legacy_evidence.changes VALUES(next_revision,TG_TABLE_NAME,TG_OP,clock_timestamp(),session_user);
 RETURN NULL;
END $$;

CREATE FUNCTION vn_legacy_evidence.attestor_guard() RETURNS void
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE principal pg_roles%ROWTYPE;
BEGIN
 SELECT * INTO principal FROM pg_roles WHERE rolname=session_user;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='vn_legacy_attestor' AND NOT rolcanlogin
     AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication AND NOT rolinherit)
    OR NOT principal.rolcanlogin OR principal.rolsuper OR principal.rolbypassrls
    OR principal.rolcreaterole OR principal.rolcreatedb OR principal.rolreplication
    OR principal.rolinherit OR principal.rolname IN ('anon','authenticated','service_role','authenticator','postgres')
    OR NOT pg_has_role(principal.oid,'vn_legacy_attestor','SET')
    OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=principal.oid AND
       (roleid<>'vn_legacy_attestor'::regrole OR admin_option OR inherit_option OR NOT set_option))
    OR (SELECT count(*) FROM pg_auth_members WHERE member=principal.oid)<>1 THEN
  RAISE EXCEPTION 'separate_legacy_attestor_required' USING ERRCODE='42501';
 END IF;
END $$;

CREATE FUNCTION vn_legacy_evidence.snapshot(owner uuid,run uuid) RETURNS jsonb
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE rev bigint; actual jsonb; expected jsonb;
BEGIN
 IF owner IS NULL OR run IS NULL THEN
  RAISE EXCEPTION 'bound_legacy_scope_required' USING ERRCODE='22023';
 END IF;
 PERFORM vn_identity.lock_legacy_evidence();
 -- All evidence/archive operations and legacy mutation triggers share this row.
 SELECT revision,baseline INTO STRICT rev,expected FROM vn_legacy_evidence.gate WHERE singleton FOR UPDATE;
 actual:=vn_legacy_evidence.current_catalog();
 IF actual IS DISTINCT FROM expected THEN
  RAISE EXCEPTION 'legacy_catalog_evidence_changed' USING ERRCODE='55000';
 END IF;
 RETURN jsonb_build_object('version',1,'provenance','legacy','owner_id',owner,'run_id',run,
  'revision',rev)||vn_identity.legacy_rows(owner,run);
END $$;

CREATE FUNCTION vn_legacy_evidence.capture(owner uuid,run uuid) RETURNS jsonb
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
BEGIN
 PERFORM vn_legacy_evidence.attestor_guard();
 RETURN vn_legacy_evidence.snapshot(owner,run);
END $$;

CREATE FUNCTION vn_legacy_evidence.keys(value jsonb,expected text[]) RETURNS boolean
 LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
 SELECT CASE WHEN jsonb_typeof(value)='object' THEN
  (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(value) k)=
  (SELECT array_agg(k ORDER BY k) FROM unnest(expected) k) ELSE false END
$$;
CREATE FUNCTION vn_legacy_evidence.text_ok(value jsonb) RETURNS boolean
 LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
 SELECT coalesce(jsonb_typeof(value)='string' AND length(value#>>'{}') BETWEEN 1 AND 240
   AND (value#>>'{}')!~'[[:cntrl:]]',false)
$$;
CREATE FUNCTION vn_legacy_evidence.hash_ok(value jsonb) RETURNS boolean
 LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$
 SELECT coalesce(jsonb_typeof(value)='string' AND (value#>>'{}')~'^[a-f0-9]{64}$',false)
$$;

CREATE FUNCTION vn_legacy_evidence.validate_document(document jsonb,snapshot jsonb) RETURNS timestamptz
 LANGUAGE plpgsql VOLATILE SET search_path=pg_catalog,pg_temp AS $$
DECLARE writer jsonb; exposure jsonb; seen text[]:=ARRAY[]::text[]; ids jsonb;
 drain_time timestamptz; reconcile_time timestamptz; expires timestamptz; now_time timestamptz:=clock_timestamp();
BEGIN
 IF document IS NULL OR octet_length(document::text)>65536 OR
   NOT vn_legacy_evidence.keys(document,ARRAY['version','provenance','owner_id','run_id','drain','reconciliation','expires_at']) OR
   document->'version'<>'1'::jsonb OR document->>'provenance' IS DISTINCT FROM 'legacy' OR
   document->'owner_id' IS DISTINCT FROM snapshot->'owner_id' OR
   document->'run_id' IS DISTINCT FROM snapshot->'run_id' OR
   NOT vn_legacy_evidence.keys(document->'drain',ARRAY['inventory_sha256','evidence_sha256','observed_at','writers']) OR
   NOT vn_legacy_evidence.keys(document->'reconciliation',ARRAY['evidence_sha256','observed_at','exposures','scope']) OR
   NOT vn_legacy_evidence.hash_ok(document->'drain'->'inventory_sha256') OR
   NOT vn_legacy_evidence.hash_ok(document->'drain'->'evidence_sha256') OR
   NOT vn_legacy_evidence.hash_ok(document->'reconciliation'->'evidence_sha256') OR
   document->'reconciliation'->>'scope' IS DISTINCT FROM 'legacy_records_and_external_exposure' OR
   jsonb_typeof(document->'drain'->'writers') IS DISTINCT FROM 'array' OR
   jsonb_array_length(document->'drain'->'writers') NOT BETWEEN 1 AND 32 OR
   jsonb_typeof(document->'reconciliation'->'exposures') IS DISTINCT FROM 'array' OR
   jsonb_array_length(document->'reconciliation'->'exposures')>200 THEN
  RAISE EXCEPTION 'invalid_legacy_evidence_document' USING ERRCODE='22023';
 END IF;
 FOR writer IN SELECT value FROM jsonb_array_elements(document->'drain'->'writers') LOOP
  IF NOT vn_legacy_evidence.keys(writer,ARRAY['identity','release_sha256','drain_receipt_sha256','state']) OR
    NOT vn_legacy_evidence.text_ok(writer->'identity') OR
    NOT vn_legacy_evidence.hash_ok(writer->'release_sha256') OR
    NOT vn_legacy_evidence.hash_ok(writer->'drain_receipt_sha256') OR writer->>'state' IS DISTINCT FROM 'drained' OR
    writer->>'identity'=ANY(seen) THEN
   RAISE EXCEPTION 'invalid_legacy_writer_inventory' USING ERRCODE='22023';
  END IF;
  seen:=array_append(seen,writer->>'identity');
 END LOOP;
 IF jsonb_typeof(document->'drain'->'observed_at')<>'string' OR
    jsonb_typeof(document->'reconciliation'->'observed_at')<>'string' OR
    jsonb_typeof(document->'expires_at')<>'string' OR
    document->'drain'->>'observed_at'!~'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$' OR
    document->'reconciliation'->>'observed_at'!~'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$' OR
    document->>'expires_at'!~'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$' THEN
  RAISE EXCEPTION 'invalid_legacy_evidence_time' USING ERRCODE='22023';
 END IF;
 drain_time:=(document->'drain'->>'observed_at')::timestamptz;
 reconcile_time:=(document->'reconciliation'->>'observed_at')::timestamptz;
 expires:=(document->>'expires_at')::timestamptz;
 IF drain_time>reconcile_time OR reconcile_time>now_time OR
    drain_time<now_time-interval '24 hours' OR expires<=now_time OR expires>drain_time+interval '24 hours' THEN
  RAISE EXCEPTION 'stale_or_unordered_legacy_evidence' USING ERRCODE='22023';
 END IF;
 seen:=ARRAY[]::text[];
 FOR exposure IN SELECT value FROM jsonb_array_elements(document->'reconciliation'->'exposures') LOOP
  IF NOT vn_legacy_evidence.keys(exposure,ARRAY['identity','trade_id','disposition','evidence_sha256','note']) OR
    NOT vn_legacy_evidence.text_ok(exposure->'identity') OR
    NOT vn_legacy_evidence.text_ok(exposure->'note') OR
    NOT vn_legacy_evidence.hash_ok(exposure->'evidence_sha256') OR
    coalesce(exposure->>'disposition' NOT IN ('resolved','retained','unknown_retained'),true) OR
    (exposure->'trade_id'<>'null'::jsonb AND
      (jsonb_typeof(exposure->'trade_id')<>'string' OR NOT snapshot->'open_trade_ids' ? (exposure->>'trade_id'))) OR
    exposure->>'identity'=ANY(seen) THEN
   RAISE EXCEPTION 'invalid_legacy_exposure_evidence' USING ERRCODE='22023';
  END IF;
  seen:=array_append(seen,exposure->>'identity');
 END LOOP;
 SELECT coalesce(jsonb_agg(value->>'trade_id' ORDER BY value->>'trade_id'),'[]') INTO ids
  FROM jsonb_array_elements(document->'reconciliation'->'exposures') WHERE value->'trade_id'<>'null'::jsonb;
 IF ids IS DISTINCT FROM snapshot->'open_trade_ids' THEN
  RAISE EXCEPTION 'legacy_open_record_coverage_required' USING ERRCODE='22023';
 END IF;
 RETURN expires;
END $$;

CREATE FUNCTION vn_legacy_evidence.attest(request uuid,owner uuid,run uuid,expected jsonb,document jsonb) RETURNS jsonb
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE old vn_legacy_evidence.reviews%ROWTYPE; actual jsonb; receipt jsonb; expires timestamptz;
BEGIN
 PERFORM vn_legacy_evidence.attestor_guard();
 IF request IS NULL OR expected IS NULL OR document IS NULL THEN
  RAISE EXCEPTION 'legacy_original_request_required' USING ERRCODE='22023';
 END IF;
 PERFORM vn_identity.lock_legacy_evidence();
 PERFORM 1 FROM vn_legacy_evidence.gate WHERE singleton FOR UPDATE;
 SELECT * INTO old FROM vn_legacy_evidence.reviews WHERE request_id=request;
 IF FOUND THEN
  IF old.owner_id IS DISTINCT FROM owner OR old.run_id IS DISTINCT FROM run OR old.snapshot IS DISTINCT FROM expected OR
    old.document IS DISTINCT FROM document OR old.attestor_oid<>(SELECT oid FROM pg_roles WHERE rolname=session_user) OR
    old.attestor_name<>session_user THEN
   RAISE EXCEPTION 'legacy_request_identity_conflict' USING ERRCODE='22023';
  END IF;
  RETURN old.receipt; -- Original committed result; never a renewed approval.
 END IF;
 actual:=vn_legacy_evidence.snapshot(owner,run);
 IF actual IS DISTINCT FROM expected THEN
  RAISE EXCEPTION 'legacy_snapshot_changed_review_again' USING ERRCODE='55000';
 END IF;
 expires:=vn_legacy_evidence.validate_document(document,actual);
 receipt:=jsonb_build_object('version',1,'provenance','legacy','request_id',request,'owner_id',owner,'run_id',run,
  'revision',actual->'revision','recorded_at',clock_timestamp(),'expires_at',expires,'kind','review');
 INSERT INTO vn_legacy_evidence.reviews VALUES(request,owner,run,actual,document,
  (SELECT oid FROM pg_roles WHERE rolname=session_user),session_user,(receipt->>'recorded_at')::timestamptz,expires,receipt);
 RETURN receipt;
END $$;

CREATE FUNCTION vn_legacy_evidence.invalidate(request uuid,review uuid,reason text) RETURNS jsonb
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE old vn_legacy_evidence.invalidations%ROWTYPE; receipt jsonb;
BEGIN
 PERFORM vn_legacy_evidence.attestor_guard();
 PERFORM vn_identity.lock_legacy_evidence();
 PERFORM 1 FROM vn_legacy_evidence.gate WHERE singleton FOR UPDATE;
 SELECT * INTO old FROM vn_legacy_evidence.invalidations WHERE request_id=request;
 IF FOUND THEN
  IF old.review_id IS DISTINCT FROM review OR old.reason IS DISTINCT FROM reason OR
    old.actor_oid<>(SELECT oid FROM pg_roles WHERE rolname=session_user) OR old.actor_name<>session_user THEN
   RAISE EXCEPTION 'legacy_request_identity_conflict' USING ERRCODE='22023';
  END IF;
  RETURN old.receipt;
 END IF;
 IF request IS NULL OR review IS NULL OR NOT vn_legacy_evidence.text_ok(to_jsonb(reason)) OR
    NOT EXISTS(SELECT 1 FROM vn_legacy_evidence.reviews WHERE request_id=review) THEN
  RAISE EXCEPTION 'legacy_review_unavailable' USING ERRCODE='P0002';
 END IF;
 receipt:=jsonb_build_object('version',1,'provenance','legacy','kind','invalidation',
  'request_id',request,'review_id',review,'recorded_at',clock_timestamp());
 INSERT INTO vn_legacy_evidence.invalidations VALUES(request,review,reason,
  (SELECT oid FROM pg_roles WHERE rolname=session_user),session_user,(receipt->>'recorded_at')::timestamptz,receipt);
 RETURN receipt;
END $$;

CREATE FUNCTION vn_legacy_evidence.review_status(review uuid,actual jsonb) RETURNS jsonb
 LANGUAGE plpgsql VOLATILE SET search_path=pg_catalog,pg_temp AS $$
DECLARE row vn_legacy_evidence.reviews%ROWTYPE; blockers jsonb:='[]'; warnings jsonb:='[]';
BEGIN
 SELECT * INTO row FROM vn_legacy_evidence.reviews WHERE request_id=review AND
  owner_id=(actual->>'owner_id')::uuid AND run_id=(actual->>'run_id')::uuid;
 IF NOT FOUND THEN RETURN jsonb_build_object('eligible',false,'blockers',jsonb_build_array('review_unavailable'),'warnings',warnings); END IF;
 IF row.snapshot IS DISTINCT FROM actual THEN blockers:=blockers||'"legacy_rows_changed"'::jsonb; END IF;
 IF row.expires_at<=clock_timestamp() THEN blockers:=blockers||'"evidence_expired"'::jsonb; END IF;
 IF EXISTS(SELECT 1 FROM vn_legacy_evidence.invalidations WHERE review_id=review) THEN
  blockers:=blockers||'"review_invalidated"'::jsonb;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE oid=row.attestor_oid AND rolname=row.attestor_name AND rolcanlogin
    AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication AND NOT rolinherit)
    OR NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=row.attestor_oid AND roleid='vn_legacy_attestor'::regrole
     AND set_option AND NOT admin_option AND NOT inherit_option)
    OR (SELECT count(*) FROM pg_auth_members WHERE member=row.attestor_oid)<>1 THEN
  blockers:=blockers||'"attestor_identity_changed"'::jsonb;
 END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(row.document->'reconciliation'->'exposures')
   WHERE value->>'disposition' IN ('retained','unknown_retained')) THEN
  warnings:=warnings||'"retained_or_uncertain_exposure"'::jsonb;
 END IF;
 IF (actual->>'unresolved_links')::bigint>0 THEN warnings:=warnings||'"unresolved_legacy_relationships"'::jsonb; END IF;
 RETURN jsonb_build_object('eligible',blockers='[]'::jsonb,'blockers',blockers,'warnings',warnings,
  'holdings_policy','reviewed_legacy_evidence_not_v5_accounting','live_holdings_verified',false,'restoration_available',false);
END $$;

CREATE FUNCTION vn_legacy_evidence.status(run uuid) RETURNS jsonb
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE owner uuid:=vn_identity.owner_id(); actual jsonb; review uuid; archived vn_legacy_evidence.archives%ROWTYPE;
 status jsonb; archive_valid boolean:=false;
BEGIN
 IF owner IS NULL THEN RAISE EXCEPTION 'legacy_owner_required' USING ERRCODE='42501'; END IF;
 actual:=vn_legacy_evidence.snapshot(owner,run);
 SELECT request_id INTO review FROM vn_legacy_evidence.reviews WHERE owner_id=owner AND run_id=run
  ORDER BY recorded_at DESC,request_id DESC LIMIT 1;
 status:=vn_legacy_evidence.review_status(review,actual);
 SELECT * INTO archived FROM vn_legacy_evidence.archives WHERE owner_id=owner AND run_id=run
  ORDER BY sequence DESC LIMIT 1;
 IF FOUND THEN archive_valid:=(vn_legacy_evidence.review_status(archived.review_id,actual)->>'eligible')::boolean; END IF;
 RETURN jsonb_build_object('version',1,'provenance','legacy','owner_id',owner,'run_id',run,'revision',actual->'revision',
  'review_id',review,'review',status,'archive_recorded',archived.request_id IS NOT NULL,'archived',archive_valid,
  'archive_invalidated',archived.request_id IS NOT NULL AND NOT archive_valid,
  'archive_receipt',archived.receipt,'legacy_policy','legacy_unknown');
END $$;

CREATE FUNCTION vn_legacy_evidence.archive(request uuid,run uuid,review uuid) RETURNS jsonb
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE owner uuid:=vn_identity.owner_id(); actual jsonb; old vn_legacy_evidence.archives%ROWTYPE;
 status jsonb; receipt jsonb; next_sequence bigint;
BEGIN
 IF owner IS NULL THEN RAISE EXCEPTION 'legacy_owner_required' USING ERRCODE='42501'; END IF;
 IF request IS NULL OR run IS NULL OR review IS NULL THEN
  RAISE EXCEPTION 'legacy_original_request_required' USING ERRCODE='22023';
 END IF;
 PERFORM vn_identity.lock_legacy_evidence();
 PERFORM 1 FROM vn_legacy_evidence.gate WHERE singleton FOR UPDATE;
 SELECT * INTO old FROM vn_legacy_evidence.archives WHERE request_id=request;
 IF FOUND THEN
  IF old.owner_id<>owner OR old.run_id<>run OR old.review_id<>review THEN
   RAISE EXCEPTION 'legacy_archive_unavailable' USING ERRCODE='P0002';
  END IF;
  RETURN old.receipt; -- Immutable original acknowledgment; read status for current validity.
 END IF;
 actual:=vn_legacy_evidence.snapshot(owner,run);
 status:=vn_legacy_evidence.review_status(review,actual);
 IF NOT (status->>'eligible')::boolean THEN
  RAISE EXCEPTION 'legacy_archive_evidence_required' USING ERRCODE='55000';
 END IF;
 SELECT coalesce(max(sequence),0)+1 INTO next_sequence FROM vn_legacy_evidence.archives;
 receipt:=jsonb_build_object('version',1,'provenance','legacy','kind','archive','request_id',request,
  'owner_id',owner,'run_id',run,'review_id',review,'revision',actual->'revision','sequence',next_sequence,
  'recorded_at',clock_timestamp(),'warnings',status->'warnings','live_holdings_verified',false,'restoration_available',false);
 INSERT INTO vn_legacy_evidence.archives VALUES(next_sequence,request,owner,run,review,
  (receipt->>'recorded_at')::timestamptz,receipt);
 RETURN receipt;
END $$;

CREATE FUNCTION vn_legacy_evidence.history(run uuid,after_sequence bigint,limit_rows integer) RETURNS jsonb
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE owner uuid:=vn_identity.owner_id(); records jsonb;
BEGIN
 IF owner IS NULL THEN RAISE EXCEPTION 'legacy_owner_required' USING ERRCODE='42501'; END IF;
 IF run IS NULL OR after_sequence IS NULL OR after_sequence<0 OR limit_rows IS NULL OR limit_rows NOT BETWEEN 1 AND 100 THEN
  RAISE EXCEPTION 'invalid_legacy_history_bound' USING ERRCODE='22023';
 END IF;
 PERFORM vn_legacy_evidence.snapshot(owner,run);
 SELECT coalesce(jsonb_agg(receipt ORDER BY sequence),'[]') INTO records FROM (
  SELECT receipt,sequence FROM vn_legacy_evidence.archives WHERE owner_id=owner AND run_id=run
   AND sequence>after_sequence ORDER BY sequence LIMIT limit_rows
 ) page;
 RETURN jsonb_build_object('version',1,'provenance','legacy','owner_id',owner,'run_id',run,'records',records,
  'next_sequence',coalesce((records->-1->>'sequence')::bigint,after_sequence));
END $$;

-- Private tables/helpers never become an API or economic/relay capability.
REVOKE ALL ON ALL TABLES IN SCHEMA vn_legacy_evidence FROM PUBLIC,anon,authenticated,service_role,authenticator;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_legacy_evidence FROM PUBLIC,anon,authenticated,service_role,authenticator;
GRANT USAGE ON SCHEMA vn_legacy_evidence TO authenticated,vn_legacy_attestor;
GRANT EXECUTE ON FUNCTION vn_legacy_evidence.status(uuid),vn_legacy_evidence.archive(uuid,uuid,uuid),
 vn_legacy_evidence.history(uuid,bigint,integer) TO authenticated;
GRANT EXECUTE ON FUNCTION vn_legacy_evidence.capture(uuid,uuid),
 vn_legacy_evidence.attest(uuid,uuid,uuid,jsonb,jsonb),vn_legacy_evidence.invalidate(uuid,uuid,text) TO vn_legacy_attestor;
GRANT USAGE ON SCHEMA vn_legacy_evidence TO postgres;
GRANT EXECUTE ON FUNCTION vn_legacy_evidence.bump() TO postgres;
RESET ROLE;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['vn_colonies','vn_fitness_snapshots','vn_generation_stats','vn_probes','vn_trades'] LOOP
  EXECUTE format('CREATE TRIGGER vn_legacy_evidence_changed AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE '
   'ON public.%I FOR EACH STATEMENT EXECUTE FUNCTION vn_legacy_evidence.bump()',t);
  EXECUTE format('ALTER TABLE public.%I ENABLE ALWAYS TRIGGER vn_legacy_evidence_changed',t);
 END LOOP;
END $$;
SET LOCAL ROLE vn_contract_owner;
REVOKE USAGE ON SCHEMA vn_legacy_evidence FROM postgres;
REVOKE EXECUTE ON FUNCTION vn_legacy_evidence.bump() FROM postgres;
INSERT INTO vn_legacy_evidence.gate VALUES(true,0,vn_legacy_evidence.current_catalog(),clock_timestamp());
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_proc p,LATERAL aclexplode(p.proacl) a WHERE
      p.oid IN ('vn_identity.lock_legacy_evidence()'::regprocedure,'vn_identity.legacy_rows(uuid,uuid)'::regprocedure)
      AND (a.is_grantable OR a.grantee NOT IN ('postgres'::regrole,'vn_contract_owner'::regrole))) OR
    EXISTS(SELECT 1 FROM pg_proc p,LATERAL aclexplode(p.proacl) a WHERE
      p.oid='vn_legacy.classify_run(uuid)'::regprocedure AND
      (a.is_grantable OR a.grantee NOT IN ('postgres'::regrole,'authenticated'::regrole))) OR
    EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
    LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
    WHERE n.nspname='vn_legacy_evidence' AND (c.relkind<>'r' AND c.relkind<>'i'
     OR (c.relkind='r' AND (a.grantee<>'vn_contract_owner'::regrole OR a.is_grantable)))) OR
    EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='vn_legacy_evidence' AND a.attacl IS NOT NULL) OR
    EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace,
      LATERAL aclexplode(p.proacl) a WHERE n.nspname='vn_legacy_evidence' AND
       (a.is_grantable OR (a.grantee<>'vn_contract_owner'::regrole AND
        NOT (a.grantee='authenticated'::regrole AND p.oid IN
         ('vn_legacy_evidence.status(uuid)'::regprocedure,'vn_legacy_evidence.archive(uuid,uuid,uuid)'::regprocedure,
          'vn_legacy_evidence.history(uuid,bigint,integer)'::regprocedure)) AND
        NOT (a.grantee='vn_legacy_attestor'::regrole AND p.oid IN
         ('vn_legacy_evidence.capture(uuid,uuid)'::regprocedure,'vn_legacy_evidence.attest(uuid,uuid,uuid,jsonb,jsonb)'::regprocedure,
          'vn_legacy_evidence.invalidate(uuid,uuid,text)'::regprocedure))))) THEN
  RAISE EXCEPTION 'legacy_evidence_privilege_postcondition_failed' USING ERRCODE='42501';
 END IF;
END $$;
RESET ROLE;
COMMIT;
