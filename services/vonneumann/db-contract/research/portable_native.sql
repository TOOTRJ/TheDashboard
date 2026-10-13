-- GUARDED OFFLINE ORIGINAL-V2 ATOMIC LABORATORY. NOT A PRODUCTION MIGRATION.
-- The full v5 package and runtime API remain unchanged. No live authority.
DO $guard$ BEGIN
 IF current_setting('dashboard.portable_native_fixture',true) IS DISTINCT FROM 'offline-v2'
    OR current_setting('server_version_num')<>'170006'
    OR to_regprocedure('vn_portable_semantic_research.advance_fixture(uuid,uuid,text)') IS NULL THEN
  RAISE EXCEPTION 'offline_portable_native_fixture_required' USING ERRCODE='22023'; END IF;
END $guard$;
CREATE SCHEMA vn_portable_native_research;
REVOKE ALL ON SCHEMA vn_portable_native_research FROM PUBLIC;

CREATE TABLE vn_portable_native_research.actor_bindings (
 login name PRIMARY KEY, owner_id uuid NOT NULL,run_id uuid NOT NULL,enabled boolean NOT NULL,
 UNIQUE(owner_id,run_id)
);
CREATE TABLE vn_portable_native_research.package_manifest (
 singleton boolean PRIMARY KEY CHECK(singleton),sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$')
);
CREATE TABLE vn_portable_native_research.runs (
 owner_id uuid NOT NULL,run_id uuid NOT NULL,worker_id uuid NOT NULL,fence bigint NOT NULL CHECK(fence>=1),
 lease_until timestamptz NOT NULL,revision bigint NOT NULL CHECK(revision>=1),
 status text NOT NULL CHECK(status IN ('created','running','paused','risk_halted','stopped','failed')),
 used_bytes bigint NOT NULL CHECK(used_bytes>=0),commands integer NOT NULL CHECK(commands BETWEEN 0 AND 128),
 PRIMARY KEY(owner_id,run_id),FOREIGN KEY(owner_id,run_id) REFERENCES vn_portable_native_research.actor_bindings(owner_id,run_id),
 FOREIGN KEY(owner_id,run_id) REFERENCES vn_portable_dependency_research.checkpoints(owner_id,run_id)
);
CREATE TABLE vn_portable_native_research.commands (
 owner_id uuid NOT NULL,run_id uuid NOT NULL,revision bigint NOT NULL,
 command_id uuid NOT NULL UNIQUE,command_sha256 text NOT NULL CHECK(command_sha256 ~ '^[0-9a-f]{64}$'),
 manifest_sha256 text NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
 validator_sha256 text NOT NULL CHECK(validator_sha256 ~ '^[0-9a-f]{64}$'),
 package_sha256 text NOT NULL CHECK(package_sha256 ~ '^[0-9a-f]{64}$'),
 worker_id uuid NOT NULL,fence bigint NOT NULL,created_xid xid8 NOT NULL,
 source_deadline timestamptz,source_received_latest timestamptz,source_estimated_at timestamptz,
 stop_only boolean NOT NULL,guard_observed_at timestamptz,
 PRIMARY KEY(owner_id,run_id,revision),
 FOREIGN KEY(owner_id,run_id,revision,command_sha256,manifest_sha256,validator_sha256)
  REFERENCES vn_portable_semantic_research.accepted_commands(owner_id,run_id,revision,command_sha256,manifest_sha256,validator_sha256),
 FOREIGN KEY(owner_id,run_id) REFERENCES vn_portable_native_research.runs(owner_id,run_id)
);
CREATE TABLE vn_portable_native_research.dependency_pins (
 owner_id uuid NOT NULL,run_id uuid NOT NULL,revision bigint NOT NULL,ordinal integer NOT NULL CHECK(ordinal BETWEEN 1 AND 13),
 kind text NOT NULL,entity_id text NOT NULL,generation bigint NOT NULL CHECK(generation BETWEEN 0 AND 2147483647),
 sha256 text NOT NULL,
 PRIMARY KEY(owner_id,run_id,revision,ordinal),UNIQUE(owner_id,run_id,revision,kind,entity_id,generation),
 FOREIGN KEY(owner_id,run_id,revision) REFERENCES vn_portable_native_research.commands(owner_id,run_id,revision),
 FOREIGN KEY(owner_id,run_id,sha256) REFERENCES vn_portable_dependency_research.components(owner_id,run_id,sha256)
);
CREATE TABLE vn_portable_native_research.active_projection (
 owner_id uuid NOT NULL,run_id uuid NOT NULL,revision bigint NOT NULL,
 resolved_wire text NOT NULL CHECK(octet_length(resolved_wire)<=262144),
 PRIMARY KEY(owner_id,run_id),FOREIGN KEY(owner_id,run_id,revision) REFERENCES vn_portable_native_research.commands(owner_id,run_id,revision)
);
CREATE TABLE vn_portable_native_research.history_projection (
 owner_id uuid NOT NULL,run_id uuid NOT NULL,revision bigint NOT NULL,
 history_wire text NOT NULL CHECK(octet_length(history_wire)<=262144),
 PRIMARY KEY(owner_id,run_id,revision),FOREIGN KEY(owner_id,run_id,revision) REFERENCES vn_portable_native_research.commands(owner_id,run_id,revision)
);
CREATE TABLE vn_portable_native_research.events (
 owner_id uuid NOT NULL,run_id uuid NOT NULL,revision bigint NOT NULL,ordinal integer NOT NULL CHECK(ordinal BETWEEN 1 AND 33),
 event_wire text NOT NULL CHECK(octet_length(event_wire)<=16384),
 PRIMARY KEY(owner_id,run_id,revision,ordinal),FOREIGN KEY(owner_id,run_id,revision) REFERENCES vn_portable_native_research.commands(owner_id,run_id,revision)
);
REVOKE ALL ON ALL TABLES IN SCHEMA vn_portable_native_research FROM PUBLIC;

CREATE FUNCTION vn_portable_native_research.catalog_fingerprint() RETURNS text
LANGUAGE sql STABLE SET search_path=pg_catalog,pg_temp AS $function$
 WITH RECURSIVE role_scope(oid) AS (SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN ('vn_portable_semantic_installer','vn_portable_native_worker_a','vn_portable_native_worker_b')
  UNION SELECT m.roleid FROM pg_catalog.pg_auth_members m JOIN role_scope r ON r.oid=m.member),
 schemas AS (SELECT n.* FROM pg_catalog.pg_namespace n WHERE n.nspname IN ('vn_portable_numeric_research',
  'vn_portable_configuration_research','vn_portable_dependency_research','vn_portable_economic_research',
  'vn_portable_source_research','vn_portable_causal_research','vn_portable_assessment_research',
  'vn_portable_optimizer_research','vn_portable_semantic_research','vn_portable_native_research')),
 relations AS (SELECT c.* FROM pg_catalog.pg_class c JOIN schemas n ON n.oid=c.relnamespace),
 payload AS (SELECT jsonb_build_object(
 'format','ga-portable-native-catalog-lab-v1','server',version(),'patch',current_setting('server_version_num'),
 'encoding',current_setting('server_encoding'),'standard_strings',current_setting('standard_conforming_strings'),
 'database',(SELECT jsonb_build_object('name',datname,'owner',pg_get_userbyid(datdba),'collate',datcollate,'ctype',datctype,'acl',datacl::text)
   FROM pg_catalog.pg_database WHERE datname=current_database()),
 'schemas',(SELECT jsonb_agg(jsonb_build_object('name',nspname,'owner',pg_get_userbyid(nspowner),'acl',nspacl::text) ORDER BY nspname COLLATE "C") FROM schemas),
 'relations',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'name',c.relname,'kind',c.relkind,
   'owner',pg_get_userbyid(c.relowner),'acl',c.relacl::text,'row_security',c.relrowsecurity,'force_row_security',c.relforcerowsecurity,
   'persistence',c.relpersistence,'options',c.reloptions,'replica_identity',c.relreplident)
   ORDER BY n.nspname COLLATE "C",c.relname COLLATE "C") FROM relations c JOIN schemas n ON n.oid=c.relnamespace),
 'columns',(SELECT jsonb_agg(jsonb_build_object('relation',a.attrelid::regclass::text,'ordinal',a.attnum,'name',a.attname,
   'type',format_type(a.atttypid,a.atttypmod),'not_null',a.attnotnull,'identity',a.attidentity,'generated',a.attgenerated,
   'dropped',a.attisdropped,'acl',a.attacl::text,'storage',a.attstorage,'compression',a.attcompression,
   'collation',a.attcollation::regcollation::text,'default',pg_get_expr(d.adbin,d.adrelid))
   ORDER BY a.attrelid::regclass::text COLLATE "C",a.attnum)
   FROM pg_catalog.pg_attribute a JOIN relations c ON c.oid=a.attrelid LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE a.attnum>0),
 'constraints',(SELECT jsonb_agg(jsonb_build_object('relation',conrelid::regclass::text,'name',conname,'definition',pg_get_constraintdef(oid,true),
   'validated',convalidated,'deferrable',condeferrable,'deferred',condeferred) ORDER BY conrelid::regclass::text COLLATE "C",conname COLLATE "C")
   FROM pg_catalog.pg_constraint WHERE connamespace IN (SELECT oid FROM schemas)),
 'indexes',(SELECT jsonb_agg(jsonb_build_object('definition',pg_get_indexdef(i.indexrelid),'valid',i.indisvalid,'ready',i.indisready,
   'live',i.indislive,'unique',i.indisunique,'immediate',i.indimmediate) ORDER BY i.indexrelid::regclass::text COLLATE "C")
   FROM pg_catalog.pg_index i WHERE i.indrelid IN (SELECT oid FROM relations)),
 'triggers',(SELECT jsonb_agg(jsonb_build_object('relation',tgrelid::regclass::text,'name',tgname,'definition',pg_get_triggerdef(oid,true),
   'enabled',tgenabled,'internal',tgisinternal) ORDER BY tgrelid::regclass::text COLLATE "C",tgname COLLATE "C")
   FROM pg_catalog.pg_trigger WHERE tgrelid IN (SELECT oid FROM relations)),
 'functions',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'definition',pg_get_functiondef(p.oid),
   'owner',pg_get_userbyid(p.proowner),'acl',p.proacl::text,'leakproof',p.proleakproof)
   ORDER BY n.nspname COLLATE "C",p.proname COLLATE "C",pg_get_function_identity_arguments(p.oid) COLLATE "C")
   FROM pg_catalog.pg_proc p JOIN schemas n ON n.oid=p.pronamespace),
 'policies',(SELECT jsonb_agg(jsonb_build_object('relation',polrelid::regclass::text,'name',polname,'command',polcmd,
   'permissive',polpermissive,'roles',polroles,'using',pg_get_expr(polqual,polrelid),'check',pg_get_expr(polwithcheck,polrelid))
   ORDER BY polrelid::regclass::text COLLATE "C",polname COLLATE "C") FROM pg_catalog.pg_policy WHERE polrelid IN (SELECT oid FROM relations)),
 'defaults',(SELECT jsonb_agg(jsonb_build_object('owner',pg_get_userbyid(defaclrole),'schema',defaclnamespace::regnamespace::text,
   'type',defaclobjtype,'acl',defaclacl::text) ORDER BY defaclnamespace,defaclobjtype)
   FROM pg_catalog.pg_default_acl WHERE defaclrole=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='vn_portable_semantic_installer')),
 'roles',(SELECT jsonb_agg(jsonb_build_object('name',rolname,'super',rolsuper,'inherit',rolinherit,'create_role',rolcreaterole,
   'create_db',rolcreatedb,'login',rolcanlogin,'replication',rolreplication,'bypass',rolbypassrls,'settings',rolconfig,'valid_until',rolvaliduntil)
   ORDER BY rolname COLLATE "C") FROM pg_catalog.pg_roles WHERE oid IN (SELECT oid FROM role_scope)),
 'memberships',(SELECT jsonb_agg(jsonb_build_object('role',pg_get_userbyid(roleid),'member',pg_get_userbyid(member),
   'grantor',pg_get_userbyid(grantor),'admin',admin_option,'inherit',inherit_option,'set',set_option) ORDER BY roleid,member,grantor)
   FROM pg_catalog.pg_auth_members WHERE member IN (SELECT oid FROM pg_catalog.pg_roles WHERE oid IN (SELECT oid FROM role_scope))),
 'parameters',(SELECT jsonb_agg(jsonb_build_object('name',parname,'acl',paracl::text) ORDER BY parname COLLATE "C")
   FROM pg_catalog.pg_parameter_acl WHERE EXISTS(SELECT 1 FROM aclexplode(paracl) a WHERE a.grantee=0 OR a.grantee IN (SELECT oid FROM role_scope))),
 'extensions',(SELECT jsonb_agg(jsonb_build_object('name',extname,'version',extversion,'owner',pg_get_userbyid(extowner),
   'schema',extnamespace::regnamespace::text,'relocatable',extrelocatable) ORDER BY extname COLLATE "C") FROM pg_catalog.pg_extension)) AS body)
 SELECT encode(sha256(convert_to(body::text,'UTF8')),'hex') FROM payload
$function$;

CREATE FUNCTION vn_portable_native_research.assert_package() RETURNS text
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $function$
DECLARE expected text; actual text:=vn_portable_native_research.catalog_fingerprint();
BEGIN
 SELECT sha256 INTO expected FROM vn_portable_native_research.package_manifest WHERE singleton FOR SHARE;
 IF expected IS NULL OR expected IS DISTINCT FROM actual THEN
  RAISE EXCEPTION 'portable_native_catalog_drift' USING ERRCODE='22023'; END IF;
 RETURN actual;
END $function$;

CREATE FUNCTION vn_portable_native_research.assert_actor(p_owner uuid,p_run uuid) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $function$
DECLARE binding vn_portable_native_research.actor_bindings%ROWTYPE;
BEGIN
 SELECT * INTO binding FROM vn_portable_native_research.actor_bindings b WHERE b.login=session_user::name FOR SHARE;
 IF NOT FOUND OR NOT binding.enabled OR binding.owner_id IS DISTINCT FROM p_owner OR binding.run_id IS DISTINCT FROM p_run THEN
  RAISE EXCEPTION 'portable_native_actor_scope' USING ERRCODE='42501'; END IF;
END $function$;

CREATE FUNCTION vn_portable_native_research.assert_session() RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $function$
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' OR current_setting('synchronous_commit')<>'on'
    OR current_setting('fsync')<>'on' OR current_setting('session_replication_role')<>'origin'
    OR current_setting('server_version_num')<>'170006' OR current_setting('server_encoding')<>'UTF8'
    OR pg_my_temp_schema()<>0 OR EXISTS(SELECT 1 FROM pg_catalog.pg_cursors WHERE is_holdable) THEN
  RAISE EXCEPTION 'portable_native_unreviewed_session' USING ERRCODE='22023'; END IF;
END $function$;

CREATE FUNCTION vn_portable_native_research.receipt(value vn_portable_native_research.commands,observed boolean) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
 SELECT jsonb_build_object('format','ga-portable-native-receipt-lab-v1','owner_id',value.owner_id,'run_id',value.run_id,
  'command_id',value.command_id,'command_sha256',value.command_sha256,'revision',value.revision::text,
  'manifest_sha256',value.manifest_sha256,'model_format','ga-portable-provider-model-research-v2',
  'assessment_format','ga-portable-provider-assessment-research-v2','semantic_validator_sha256',value.validator_sha256,
  'native_package_sha256',value.package_sha256,'record_observed',observed,'pending_until_commit',NOT observed,
  'guard_observed_at',CASE WHEN value.guard_observed_at IS NULL THEN NULL ELSE
   to_char(value.guard_observed_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US')||'+00:00' END,'final_visible_instant_freshness',false,
  'restoration_authority',false,'hosted_authority',false)
$function$;

CREATE FUNCTION vn_portable_native_research.create_run(p_owner uuid,p_run uuid,p_worker uuid,lease_seconds integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $function$
DECLARE contract text;
BEGIN
 PERFORM vn_portable_native_research.assert_actor(p_owner,p_run);PERFORM vn_portable_native_research.assert_session();
 contract:=vn_portable_native_research.assert_package();
 IF p_worker IS NULL OR lease_seconds IS NULL OR lease_seconds NOT BETWEEN 1 AND 60 THEN RAISE EXCEPTION 'portable_native_run_input' USING ERRCODE='22023'; END IF;
 INSERT INTO vn_portable_dependency_research.checkpoints VALUES(p_run,p_owner,1,NULL);
 INSERT INTO vn_portable_native_research.runs VALUES(p_owner,p_run,p_worker,1,clock_timestamp()+make_interval(secs=>lease_seconds),1,'created',0,0);
 RETURN jsonb_build_object('owner_id',p_owner,'run_id',p_run,'worker_id',p_worker,'fence','1','revision','1','native_package_sha256',contract,
  'hosted_authority',false);
END $function$;

CREATE FUNCTION vn_portable_native_research.heartbeat(p_owner uuid,p_run uuid,p_worker uuid,p_fence bigint,lease_seconds integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $function$
DECLARE state vn_portable_native_research.runs%ROWTYPE;
BEGIN
 PERFORM vn_portable_native_research.assert_actor(p_owner,p_run);PERFORM vn_portable_native_research.assert_session();
 PERFORM vn_portable_native_research.assert_package();
 SELECT * INTO state FROM vn_portable_native_research.runs r WHERE r.owner_id=p_owner AND r.run_id=p_run FOR UPDATE;
 IF NOT FOUND OR state.worker_id IS DISTINCT FROM p_worker OR state.fence IS DISTINCT FROM p_fence
    OR state.lease_until<=clock_timestamp() OR state.status IN ('stopped','failed') OR lease_seconds IS NULL OR lease_seconds NOT BETWEEN 1 AND 60 THEN
  RAISE EXCEPTION 'portable_native_lease_lost' USING ERRCODE='22023'; END IF;
 UPDATE vn_portable_native_research.runs SET lease_until=clock_timestamp()+make_interval(secs=>lease_seconds) WHERE owner_id=p_owner AND run_id=p_run;
 RETURN jsonb_build_object('revision',state.revision::text,'fence',state.fence::text,'hosted_authority',false);
END $function$;

CREATE FUNCTION vn_portable_native_research.commit_command(p_owner uuid,p_run uuid,p_worker uuid,p_fence bigint,wire text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $function$
DECLARE request jsonb; digest text; id uuid; state vn_portable_native_research.runs%ROWTYPE;
 replay vn_portable_native_research.commands%ROWTYPE; stored text; checked jsonb; manifest jsonb; ref record; event record;
 resolved jsonb; catalog text; deadline timestamptz; latest_receipt timestamptz; source_time timestamptz;
 server_now timestamptz; stop_only boolean; next_revision bigint;
 component_before bigint; component_after bigint; old_active bigint; charge bigint; history_wire text;
 record vn_portable_native_research.commands%ROWTYPE;
BEGIN
 PERFORM vn_portable_native_research.assert_actor(p_owner,p_run);PERFORM vn_portable_native_research.assert_session();
 catalog:=vn_portable_native_research.assert_package();
 checked:=vn_portable_numeric_research.audit(wire,262144);request:=checked->'tagged';digest:=checked->>'sha256';
 id:=vn_portable_dependency_research.uuid_text(request->'command_id')::uuid;
 -- Exact original-ID lookup occurs before expiry/fence/revision/source checks.
 SELECT * INTO replay FROM vn_portable_native_research.commands c WHERE c.command_id=id FOR SHARE;
 IF FOUND THEN
  SELECT command_wire INTO stored FROM vn_portable_semantic_research.accepted_commands c
   WHERE c.owner_id=replay.owner_id AND c.run_id=replay.run_id AND c.revision=replay.revision FOR SHARE;
  IF replay.owner_id IS DISTINCT FROM p_owner OR replay.run_id IS DISTINCT FROM p_run OR replay.command_sha256 IS DISTINCT FROM digest
     OR stored IS DISTINCT FROM wire THEN RAISE EXCEPTION 'portable_native_original_id_conflict' USING ERRCODE='22023'; END IF;
  IF replay.created_xid=pg_current_xact_id() THEN RAISE EXCEPTION 'portable_native_uncommitted_replay' USING ERRCODE='22023'; END IF;
  RETURN vn_portable_native_research.receipt(replay,true);
 END IF;
 IF EXISTS(SELECT 1 FROM vn_portable_native_research.commands c WHERE c.created_xid=pg_current_xact_id()) THEN
  RAISE EXCEPTION 'portable_native_one_command_per_transaction' USING ERRCODE='22023'; END IF;
 SELECT * INTO state FROM vn_portable_native_research.runs r WHERE r.owner_id=p_owner AND r.run_id=p_run FOR UPDATE;
 server_now:=clock_timestamp();
 IF NOT FOUND OR state.worker_id IS DISTINCT FROM p_worker OR state.fence IS DISTINCT FROM p_fence OR state.lease_until<=server_now
    OR state.status IN ('stopped','failed') THEN RAISE EXCEPTION 'portable_native_lease_lost' USING ERRCODE='22023'; END IF;
 stop_only:=request#>>'{evidence,kind}'='control' AND request#>>'{evidence,control,action}'='stop' AND request#>>'{checkpoint,status}'='stopped';
 IF state.commands>=128 OR (NOT stop_only AND state.commands>=127) THEN RAISE EXCEPTION 'portable_native_stop_slot_reserved' USING ERRCODE='22023'; END IF;
 -- Only original server-independent source evidence is inspected here. Real
 -- commit-processing age is derived from server time, never a caller clock GUC.
 IF stop_only OR (request#>>'{evidence,kind}'='control' AND request#>>'{evidence,control,action}' IN ('pause','resume')) THEN deadline:=NULL;
 ELSIF request#>>'{evidence,kind}'='bootstrap' THEN deadline:=NULL;
 ELSE
  latest_receipt:=to_timestamp(vn_portable_source_research.clock(request#>'{evidence,inputs,provider,frame,quote,document,received_wall_us}')/1000000);
  source_time:=to_timestamp(vn_portable_dependency_research.counter(request#>'{evidence,inputs,provider,frame,quote,estimated_source_second}',0,10000000000)::double precision);
  deadline:=least(latest_receipt,
  latest_receipt
   +make_interval(secs=>(25000000-vn_portable_source_research.clock(request#>'{evidence,inputs,provider,frame,quote,source_age_floor_us}'))::double precision/1000000),
  source_time+interval '25 seconds'); END IF;
 -- Bootstrap documents are converted below through the strict tagged counter.
 IF request#>>'{evidence,kind}'='bootstrap' THEN
  SELECT min(to_timestamp(vn_portable_source_research.clock(v->'received_wall_us')/1000000)),
   max(to_timestamp(vn_portable_source_research.clock(v->'received_wall_us')/1000000)) INTO deadline,latest_receipt
   FROM jsonb_array_elements(request#>'{evidence,inputs,provider,history,documents}') a(v);
 END IF;
 -- The original worker-relative two-second allowances must not compose into
 -- four seconds relative to the native server clock. Bind each latest receipt
 -- and estimated source anchor directly to this one genuine observation.
 IF latest_receipt>server_now+interval '2 seconds' OR source_time>server_now+interval '2 seconds' THEN
  RAISE EXCEPTION 'portable_native_source_future' USING ERRCODE='22023'; END IF;
 IF deadline IS NOT NULL THEN deadline:=deadline+interval '5 seconds';
  IF deadline<=server_now THEN RAISE EXCEPTION 'portable_native_source_expired' USING ERRCODE='22023'; END IF;
 ELSIF NOT stop_only AND request#>>'{evidence,kind}' NOT IN ('control') THEN
  RAISE EXCEPTION 'portable_native_source_required' USING ERRCODE='22023'; END IF;
 SELECT coalesce(sum(octet_length(c.wire)),0) INTO component_before FROM vn_portable_dependency_research.components c WHERE c.owner_id=p_owner AND c.run_id=p_run;
 SELECT coalesce(octet_length(resolved_wire),0) INTO old_active FROM vn_portable_native_research.active_projection a WHERE a.owner_id=p_owner AND a.run_id=p_run;
 old_active:=coalesce(old_active,0);
 checked:=vn_portable_semantic_research.advance_fixture(p_owner,p_run,wire);
 manifest:=request->'checkpoint';next_revision:=vn_portable_dependency_research.counter(manifest->'revision',2,9223372036854775807);
 -- The semantic helper already advanced its locked, validated head. Expansion
 -- here projects that held original manifest, never an independently read prior.
 SELECT jsonb_object_agg(c.sha256,vn_portable_dependency_research.block(c.wire,p_owner,p_run)) INTO resolved
  FROM vn_portable_dependency_research.components c WHERE c.owner_id=p_owner AND c.run_id=p_run AND c.sha256 IN
   (SELECT v->>'sha256' FROM jsonb_array_elements(manifest->'components') a(v));
 resolved:=vn_portable_dependency_research.expand(manifest,resolved,p_owner,p_run,next_revision);
 history_wire:=vn_portable_dependency_research.canonical(request->'history');
 SELECT coalesce(sum(octet_length(c.wire)),0) INTO component_after FROM vn_portable_dependency_research.components c WHERE c.owner_id=p_owner AND c.run_id=p_run;
 charge:=octet_length(wire)+(component_after-component_before)+octet_length(history_wire)
  +coalesce((SELECT sum(octet_length(vn_portable_dependency_research.canonical(v))) FROM jsonb_array_elements(request->'events') a(v)),0)
  +octet_length(resolved->>'wire')-old_active+8192;
 IF state.used_bytes+charge>(CASE WHEN stop_only THEN 9707520 ELSE 8388608 END) THEN
  RAISE EXCEPTION 'portable_native_stop_bytes_reserved' USING ERRCODE='22023'; END IF;
 INSERT INTO vn_portable_native_research.commands VALUES(p_owner,p_run,next_revision,id,digest,checked->>'following_sha256',
  checked->>'validator_sha256',catalog,p_worker,p_fence,pg_current_xact_id(),deadline,latest_receipt,source_time,stop_only,NULL) RETURNING * INTO record;
 FOR ref IN SELECT v,ordinal FROM jsonb_array_elements(manifest->'components') WITH ORDINALITY a(v,ordinal) LOOP
  INSERT INTO vn_portable_native_research.dependency_pins VALUES(p_owner,p_run,next_revision,ref.ordinal,ref.v->>'kind',ref.v->>'entity_id',
   vn_portable_dependency_research.counter(ref.v->'generation',0,2147483647),ref.v->>'sha256');
 END LOOP;
 INSERT INTO vn_portable_native_research.active_projection VALUES(p_owner,p_run,next_revision,resolved->>'wire')
  ON CONFLICT ON CONSTRAINT active_projection_pkey DO UPDATE SET revision=excluded.revision,resolved_wire=excluded.resolved_wire;
 INSERT INTO vn_portable_native_research.history_projection VALUES(p_owner,p_run,next_revision,history_wire);
 FOR event IN SELECT v,ordinal FROM jsonb_array_elements(request->'events') WITH ORDINALITY a(v,ordinal) LOOP
  INSERT INTO vn_portable_native_research.events VALUES(p_owner,p_run,next_revision,event.ordinal,vn_portable_dependency_research.canonical(event.v));
 END LOOP;
 UPDATE vn_portable_native_research.runs SET revision=next_revision,status=manifest->>'status',used_bytes=state.used_bytes+charge,commands=state.commands+1
  WHERE owner_id=p_owner AND run_id=p_run;
 -- This final function check is only defense in depth. The pending constraint
 -- guard repeats the check at recognized commit processing, never final WAL time.
 server_now:=clock_timestamp();
 IF state.lease_until<=server_now OR (deadline IS NOT NULL AND deadline<=server_now)
    OR latest_receipt>server_now+interval '2 seconds' OR source_time>server_now+interval '2 seconds' THEN
  RAISE EXCEPTION 'portable_native_final_source_or_lease_expired' USING ERRCODE='22023'; END IF;
 RETURN vn_portable_native_research.receipt(record,false);
END $function$;

CREATE FUNCTION vn_portable_native_research.commit_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $function$
DECLARE state vn_portable_native_research.runs%ROWTYPE; observed timestamptz;
BEGIN
 IF current_query() IS NULL OR translate(current_query(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ') COLLATE "C" !~ '^[ \t\r\n]*COMMIT[ \t\r\n]*;?[ \t\r\n]*$' THEN
  RAISE EXCEPTION 'portable_native_unreviewed_commit_form' USING ERRCODE='22023'; END IF;
 PERFORM vn_portable_native_research.assert_session();PERFORM vn_portable_native_research.assert_actor(NEW.owner_id,NEW.run_id);
 IF NEW.package_sha256 IS DISTINCT FROM vn_portable_native_research.assert_package() THEN
  RAISE EXCEPTION 'portable_native_catalog_drift' USING ERRCODE='22023'; END IF;
 SELECT * INTO state FROM vn_portable_native_research.runs r WHERE r.owner_id=NEW.owner_id AND r.run_id=NEW.run_id FOR UPDATE;
 observed:=clock_timestamp();
 IF NOT FOUND OR state.worker_id IS DISTINCT FROM NEW.worker_id OR state.fence IS DISTINCT FROM NEW.fence
    OR state.lease_until<=observed OR (NEW.source_deadline IS NOT NULL AND NEW.source_deadline<=observed)
    OR NEW.source_received_latest>observed+interval '2 seconds' OR NEW.source_estimated_at>observed+interval '2 seconds' THEN
  RAISE EXCEPTION 'portable_native_commit_guard_expired' USING ERRCODE='22023'; END IF;
 UPDATE vn_portable_native_research.commands SET guard_observed_at=observed
  WHERE owner_id=NEW.owner_id AND run_id=NEW.run_id AND revision=NEW.revision;
 RETURN NULL;
END $function$;
CREATE CONSTRAINT TRIGGER portable_native_commit_guard AFTER INSERT ON vn_portable_native_research.commands
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION vn_portable_native_research.commit_guard();

CREATE FUNCTION vn_portable_native_research.get_command(p_owner uuid,p_run uuid,p_id uuid,p_sha text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $function$
DECLARE record vn_portable_native_research.commands%ROWTYPE; original text; result jsonb;
BEGIN
 PERFORM vn_portable_native_research.assert_actor(p_owner,p_run);PERFORM vn_portable_native_research.assert_package();
 SELECT * INTO record FROM vn_portable_native_research.commands c WHERE c.owner_id=p_owner AND c.run_id=p_run AND c.command_id=p_id FOR SHARE;
 IF NOT FOUND THEN RETURN jsonb_build_object('format','ga-portable-native-command-readback-lab-v1','found',false); END IF;
 IF record.owner_id IS DISTINCT FROM p_owner OR record.run_id IS DISTINCT FROM p_run OR record.command_sha256 IS DISTINCT FROM p_sha THEN
  RAISE EXCEPTION 'portable_native_original_id_conflict' USING ERRCODE='22023'; END IF;
 IF record.created_xid=pg_current_xact_id() THEN RAISE EXCEPTION 'portable_native_uncommitted_readback' USING ERRCODE='22023'; END IF;
 SELECT command_wire INTO original FROM vn_portable_semantic_research.accepted_commands c WHERE c.owner_id=p_owner AND c.run_id=p_run AND c.revision=record.revision FOR SHARE;
 result:=jsonb_build_object('format','ga-portable-native-command-readback-lab-v1','found',true,
  'receipt',vn_portable_native_research.receipt(record,true),'original_command_wire',original);
 IF octet_length(result::text)>589824 THEN RAISE EXCEPTION 'portable_native_readback_capacity' USING ERRCODE='22023'; END IF;
 RETURN result;
END $function$;

CREATE FUNCTION vn_portable_native_research.read_checkpoint(p_owner uuid,p_run uuid,p_revision bigint,p_sha text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $function$
DECLARE record vn_portable_native_research.commands%ROWTYPE; original text; manifest text; blocks jsonb; result jsonb;
 total bigint; state vn_portable_native_research.runs%ROWTYPE;
BEGIN
 PERFORM vn_portable_native_research.assert_actor(p_owner,p_run);PERFORM vn_portable_native_research.assert_package();
 SELECT * INTO state FROM vn_portable_native_research.runs r WHERE r.owner_id=p_owner AND r.run_id=p_run FOR SHARE;
 SELECT * INTO record FROM vn_portable_native_research.commands c WHERE c.owner_id=p_owner AND c.run_id=p_run AND c.revision=p_revision FOR SHARE;
 IF NOT FOUND OR record.manifest_sha256 IS DISTINCT FROM p_sha THEN RAISE EXCEPTION 'portable_native_checkpoint_unavailable' USING ERRCODE='22023'; END IF;
 IF record.created_xid=pg_current_xact_id() THEN RAISE EXCEPTION 'portable_native_uncommitted_readback' USING ERRCODE='22023'; END IF;
 SELECT command_wire INTO original FROM vn_portable_semantic_research.accepted_commands c WHERE c.owner_id=p_owner AND c.run_id=p_run AND c.revision=p_revision FOR SHARE;
 manifest:=vn_portable_dependency_research.canonical(original::jsonb->'checkpoint');
 SELECT jsonb_agg(to_jsonb(c.wire) ORDER BY p.ordinal),sum(octet_length(c.wire)) INTO blocks,total
  FROM vn_portable_native_research.dependency_pins p JOIN vn_portable_dependency_research.components c
   ON c.owner_id=p.owner_id AND c.run_id=p.run_id AND c.sha256=p.sha256
  WHERE p.owner_id=p_owner AND p.run_id=p_run AND p.revision=p_revision;
 IF jsonb_array_length(blocks)<>13 OR total+octet_length(manifest)>262144 OR
    encode(sha256(convert_to(manifest,'UTF8')),'hex') IS DISTINCT FROM p_sha THEN RAISE EXCEPTION 'portable_native_checkpoint_binding' USING ERRCODE='22023'; END IF;
 result:=jsonb_build_object('format','ga-portable-native-checkpoint-readback-lab-v1','manifest_wire',manifest,'component_wires',blocks,
  'receipt',vn_portable_native_research.receipt(record,true),'current_revision',state.revision::text,'current_status',state.status,
  'pending_command_authority',false,'restoration_authority',false,'hosted_authority',false);
 IF octet_length(result::text)>589824 THEN RAISE EXCEPTION 'portable_native_readback_capacity' USING ERRCODE='22023'; END IF;
 RETURN result;
END $function$;
CREATE FUNCTION vn_portable_native_research.lookup_identity_ids(p_owner uuid,p_run uuid,p_revision bigint,p_manifest_sha text,ids jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $function$
DECLARE entry jsonb; requested_id text; seen text[]:=ARRAY[]::text[]; result jsonb:='{}'; allocation vn_portable_economic_research.allocated%ROWTYPE;
 state vn_portable_native_research.runs%ROWTYPE; head_sha text; head_xid xid8; head_guard timestamptz; catalog text;
BEGIN
 PERFORM vn_portable_native_research.assert_actor(p_owner,p_run);catalog:=vn_portable_native_research.assert_package();
 SELECT * INTO state FROM vn_portable_native_research.runs r WHERE r.owner_id=p_owner AND r.run_id=p_run FOR SHARE;
 IF NOT FOUND OR state.revision IS DISTINCT FROM p_revision THEN RAISE EXCEPTION 'portable_native_lookup_head_mismatch' USING ERRCODE='22023'; END IF;
 SELECT manifest_sha256,created_xid,guard_observed_at INTO head_sha,head_xid,head_guard FROM vn_portable_native_research.commands c
  WHERE c.owner_id=p_owner AND c.run_id=p_run AND c.revision=p_revision FOR SHARE;
 IF head_sha IS DISTINCT FROM p_manifest_sha OR (state.revision>1 AND head_sha IS NULL) THEN
  RAISE EXCEPTION 'portable_native_lookup_head_mismatch' USING ERRCODE='22023'; END IF;
 IF state.revision>1 AND (head_xid=pg_current_xact_id() OR head_guard IS NULL) THEN
  RAISE EXCEPTION 'portable_native_uncommitted_readback' USING ERRCODE='22023'; END IF;
 IF jsonb_typeof(ids) IS DISTINCT FROM 'array' OR jsonb_array_length(ids)>128 THEN
  RAISE EXCEPTION 'portable_native_identity_lookup_capacity' USING ERRCODE='22023'; END IF;
 FOR entry IN SELECT v FROM jsonb_array_elements(ids) a(v) LOOP
  requested_id:=vn_portable_dependency_research.uuid_text(entry);
  IF requested_id=ANY(seen) THEN RAISE EXCEPTION 'portable_native_duplicate_lookup_id' USING ERRCODE='22023'; END IF;
  seen:=array_append(seen,requested_id);
  SELECT * INTO allocation FROM vn_portable_economic_research.allocated a WHERE a.id=requested_id::uuid AND a.owner_id=p_owner AND a.run_id=p_run FOR SHARE;
  result:=result||jsonb_build_object(requested_id,CASE WHEN FOUND THEN jsonb_build_object('used',true,'kind',allocation.kind,'born_revision',allocation.born_revision::text)
    ELSE jsonb_build_object('used',false) END);
 END LOOP;
 RETURN jsonb_build_object('format','ga-portable-native-identity-lookup-lab-v1','owner_id',p_owner,'run_id',p_run,'revision',state.revision::text,'manifest_sha256',head_sha,
  'native_package_sha256',catalog,'identities',result,'restoration_authority',false,'hosted_authority',false);
END $function$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_portable_native_research FROM PUBLIC;
