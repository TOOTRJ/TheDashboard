-- Exact The Dashboard / fxpxsciltakyypunglzr only; verify provider IDs outside SQL.
-- Read-only bounded metadata, no application rows/passwords/role verifiers or persistent DDL.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL lock_timeout='1s'; SET LOCAL statement_timeout='15s';
-- Match the session-local install oracle's deparser context exactly. Without
-- this, identical FKs/triggers appear qualified in one capture and unqualified
-- in the other, creating false drift after an otherwise valid installation.
SET LOCAL search_path=pg_catalog,pg_temp;
WITH legacy_catalog AS (
WITH RECURSIVE
tables AS (
 SELECT c.* FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname=ANY(ARRAY['vn_colonies','vn_fitness_snapshots','vn_generation_stats','vn_probes','vn_trades']::text[])
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
   WHERE schemaname='public' AND tablename=ANY(ARRAY['vn_colonies','vn_fitness_snapshots','vn_generation_stats','vn_probes','vn_trades']::text[])),
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
     AND tablename=ANY(ARRAY['vn_colonies','vn_fitness_snapshots','vn_generation_stats','vn_probes','vn_trades']::text[]))
)
), migrations AS (
 SELECT coalesce(jsonb_agg(jsonb_build_object('version',version,'name',name,
  'statements_sha256',encode(sha256(convert_to(coalesce(array_to_json(statements)::text,'null'),'UTF8')),'hex'))
  ORDER BY version),'[]'::jsonb) AS catalog FROM supabase_migrations.schema_migrations
)
SELECT jsonb_build_object('legacy',legacy_catalog.jsonb_build_object,'migrations',migrations.catalog,
 'read_only',current_setting('transaction_read_only'),'isolation',current_setting('transaction_isolation')) AS review
FROM legacy_catalog CROSS JOIN migrations;
ROLLBACK;
