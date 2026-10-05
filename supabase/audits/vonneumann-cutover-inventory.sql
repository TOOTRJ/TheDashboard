-- DB-03A2D1: metadata and aggregate counts ONLY, not a migration.
-- Verify The Dashboard / fxpxsciltakyypunglzr / cqfnnaunmupdyobkyqfo
-- through provider metadata and the repository link BEFORE executing.
-- Never use an unrelated connector or substitute another database URL.
-- No row identities, configuration JSON, credentials or function bodies output.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '15s';

WITH RECURSIVE
tables AS (
  SELECT c.*, n.nspname
  FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='public' AND c.relname IN (
    'vn_colonies','vn_probes','vn_trades','vn_fitness_snapshots','vn_generation_stats')
),
clients AS (
  SELECT oid, rolname, rolinherit, rolbypassrls, rolsuper
  FROM pg_catalog.pg_roles
  WHERE rolname IN ('anon','authenticated','service_role','authenticator')
),
ancestors AS (
  SELECT c.oid AS client, c.oid AS ancestor, ARRAY[c.oid] AS path FROM clients c
  UNION ALL
  SELECT a.client, m.roleid, a.path || m.roleid
  FROM ancestors a JOIN pg_catalog.pg_auth_members m ON m.member=a.ancestor
  WHERE NOT m.roleid=ANY(a.path) AND cardinality(a.path)<16
),
probes AS (
  SELECT p.*,
    c.id AS colony_id, c.user_id AS colony_owner, c.mode AS colony_mode,
    parent.id AS linked_parent_id, parent.user_id AS parent_owner,
    parent.run_id AS parent_run
  FROM public.vn_probes p
  LEFT JOIN public.vn_colonies c ON c.id=p.run_id
  LEFT JOIN public.vn_probes parent ON parent.id=p.parent_id
),
parent_elements AS (
  SELECT p.id, p.user_id, p.run_id, e.value,
    CASE WHEN jsonb_typeof(e.value)='string' AND (e.value #>> '{}') ~*
      '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
      THEN (e.value #>> '{}')::uuid END AS parent_id
  FROM public.vn_probes p
  CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(p.parent_ids)='array' THEN p.parent_ids ELSE '[]'::jsonb END
  ) e
),
functions AS (
  SELECT p.*,n.nspname FROM pg_catalog.pg_proc p
  JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='vn_durability' OR (n.nspname='public' AND (
    p.proname LIKE 'vn\_%' ESCAPE '\' OR p.prosrc ~*
    '(vn_colonies|vn_probes|vn_trades|vn_fitness_snapshots|vn_generation_stats)'))
    OR p.oid IN (SELECT tr.tgfoid FROM pg_catalog.pg_trigger tr JOIN tables t ON t.oid=tr.tgrelid)
    OR p.oid IN (SELECT d.objid FROM pg_catalog.pg_depend d JOIN tables t ON t.oid=d.refobjid
      WHERE d.classid='pg_proc'::regclass AND d.refclassid='pg_class'::regclass)
),
sequences AS (
  SELECT DISTINCT s.* FROM pg_catalog.pg_class s
  WHERE s.relkind='S' AND (
    s.oid IN (SELECT d.objid FROM pg_catalog.pg_depend d JOIN tables t ON t.oid=d.refobjid
      WHERE d.classid='pg_class'::regclass AND d.refclassid='pg_class'::regclass)
    OR s.oid IN (SELECT d.refobjid FROM pg_catalog.pg_depend d
      JOIN pg_catalog.pg_attrdef a ON a.oid=d.objid JOIN tables t ON t.oid=a.adrelid
      WHERE d.classid='pg_attrdef'::regclass AND d.refclassid='pg_class'::regclass))
),
row_counts AS (
  SELECT 'vn_colonies' AS table_name, jsonb_build_object(
    'total', count(*), 'null_owner', count(*) FILTER(WHERE c.user_id IS NULL),
    'missing_auth_owner', count(*) FILTER(WHERE c.user_id IS NOT NULL AND u.id IS NULL),
    'distinct_owners',count(DISTINCT c.user_id),
    'statuses', (SELECT coalesce(jsonb_object_agg(status,n), '{}'::jsonb)
      FROM (SELECT CASE WHEN status IN ('starting','running','paused','risk_halted','stopped','failed')
        THEN status ELSE 'unsupported' END AS status,count(*) n
        FROM public.vn_colonies GROUP BY 1) s),
    'unsupported_mode',count(*) FILTER(WHERE c.mode NOT IN ('simulation','paper','live')),
    'config_not_object',count(*) FILTER(WHERE jsonb_typeof(c.config) IS DISTINCT FROM 'object')
  ) AS counts
  FROM public.vn_colonies c LEFT JOIN auth.users u ON u.id=c.user_id
  UNION ALL
  SELECT 'vn_probes', jsonb_build_object(
    'total',count(*), 'null_owner',count(*) FILTER(WHERE user_id IS NULL),
    'distinct_owners',count(DISTINCT user_id),'distinct_nonnull_runs',count(DISTINCT run_id),
    'distinct_owner_run_groups',count(DISTINCT (user_id,run_id)),
    'null_run',count(*) FILTER(WHERE run_id IS NULL),
    'missing_colony',count(*) FILTER(WHERE run_id IS NOT NULL AND colony_id IS NULL),
    'missing_colony_owner_run_groups',count(DISTINCT (user_id,run_id)) FILTER(WHERE run_id IS NOT NULL AND colony_id IS NULL),
    'missing_colony_groups_hidden_by_reader',count(DISTINCT (user_id,run_id)) FILTER(
      WHERE run_id IS NOT NULL AND colony_id IS NULL AND EXISTS(
        SELECT 1 FROM public.vn_colonies c WHERE c.user_id=probes.user_id)),
    'colony_owner_mismatch',count(*) FILTER(WHERE colony_id IS NOT NULL AND user_id IS DISTINCT FROM colony_owner),
    'colony_mode_mismatch',count(*) FILTER(WHERE colony_id IS NOT NULL AND mode IS DISTINCT FROM colony_mode),
    'missing_parent',count(*) FILTER(WHERE parent_id IS NOT NULL AND linked_parent_id IS NULL),
    'self_parent',count(*) FILTER(WHERE parent_id=id),
    'scalar_parent_present',count(*) FILTER(WHERE parent_id IS NOT NULL),
    'parent_owner_mismatch',count(*) FILTER(WHERE linked_parent_id IS NOT NULL AND user_id IS DISTINCT FROM parent_owner),
    'parent_bound_run_mismatch',count(*) FILTER(WHERE linked_parent_id IS NOT NULL AND run_id IS NOT NULL AND parent_run IS NOT NULL AND run_id<>parent_run),
    'parent_unbound_run',count(*) FILTER(WHERE linked_parent_id IS NOT NULL AND (run_id IS NULL OR parent_run IS NULL)),
    'parent_ids_not_array',count(*) FILTER(WHERE jsonb_typeof(parent_ids) IS DISTINCT FROM 'array'),
    'parent_ids_empty_array',count(*) FILTER(WHERE parent_ids='[]'::jsonb),
    'null_sharpe',count(*) FILTER(WHERE sharpe_ratio IS NULL),
    'null_metrics',count(*) FILTER(WHERE metrics IS NULL),
    'json_null_metrics',count(*) FILTER(WHERE metrics='null'::jsonb),
    'metrics_wrong_shape',count(*) FILTER(WHERE metrics IS NOT NULL AND jsonb_typeof(metrics) NOT IN ('object','null'))
  ) FROM probes
  UNION ALL
  SELECT 'vn_trades', jsonb_build_object(
    'total',count(*),'null_owner',count(*) FILTER(WHERE t.user_id IS NULL),
    'distinct_owners',count(DISTINCT t.user_id),'distinct_nonnull_runs',count(DISTINCT t.run_id),
    'distinct_owner_run_groups',count(DISTINCT (t.user_id,t.run_id)),
    'null_run',count(*) FILTER(WHERE t.run_id IS NULL),
    'missing_colony',count(*) FILTER(WHERE t.run_id IS NOT NULL AND c.id IS NULL),
    'colony_owner_mismatch',count(*) FILTER(WHERE c.id IS NOT NULL AND t.user_id IS DISTINCT FROM c.user_id),
    'colony_mode_mismatch',count(*) FILTER(WHERE c.id IS NOT NULL AND t.mode IS DISTINCT FROM c.mode),
    'missing_probe',count(*) FILTER(WHERE p.id IS NULL),
    'probe_owner_mismatch',count(*) FILTER(WHERE p.id IS NOT NULL AND t.user_id IS DISTINCT FROM p.user_id),
    'probe_bound_run_mismatch',count(*) FILTER(WHERE p.id IS NOT NULL AND t.run_id IS NOT NULL AND p.run_id IS NOT NULL AND t.run_id<>p.run_id),
    'probe_unbound_run',count(*) FILTER(WHERE p.id IS NOT NULL AND (t.run_id IS NULL OR p.run_id IS NULL)),
    'open',count(*) FILTER(WHERE t.closed_at IS NULL),
    'null_execution',count(*) FILTER(WHERE t.execution IS NULL),
    'json_null_execution',count(*) FILTER(WHERE t.execution='null'::jsonb),
    'execution_wrong_shape',count(*) FILTER(WHERE t.execution IS NOT NULL AND jsonb_typeof(t.execution) NOT IN ('object','null')),
    'closed_missing_exit_fields',count(*) FILTER(WHERE t.closed_at IS NOT NULL AND
      (t.exit_price IS NULL OR t.pnl IS NULL OR t.pnl_pct IS NULL OR t.exit_reason IS NULL)),
    'open_with_exit_fields',count(*) FILTER(WHERE t.closed_at IS NULL AND
      (t.exit_price IS NOT NULL OR t.pnl IS NOT NULL OR t.pnl_pct IS NOT NULL OR t.exit_reason IS NOT NULL))
  ) FROM public.vn_trades t
  LEFT JOIN public.vn_probes p ON p.id=t.probe_id
  LEFT JOIN public.vn_colonies c ON c.id=t.run_id
  UNION ALL
  SELECT 'vn_fitness_snapshots', jsonb_build_object(
    'total',count(*),'null_owner',count(*) FILTER(WHERE f.user_id IS NULL),
    'distinct_owners',count(DISTINCT f.user_id),'distinct_nonnull_runs',count(DISTINCT f.run_id),
    'distinct_owner_run_groups',count(DISTINCT (f.user_id,f.run_id)),
    'null_run',count(*) FILTER(WHERE f.run_id IS NULL),
    'missing_colony',count(*) FILTER(WHERE f.run_id IS NOT NULL AND c.id IS NULL),
    'colony_owner_mismatch',count(*) FILTER(WHERE c.id IS NOT NULL AND f.user_id IS DISTINCT FROM c.user_id),
    'missing_probe',count(*) FILTER(WHERE p.id IS NULL),
    'probe_owner_mismatch',count(*) FILTER(WHERE p.id IS NOT NULL AND f.user_id IS DISTINCT FROM p.user_id),
    'probe_bound_run_mismatch',count(*) FILTER(WHERE p.id IS NOT NULL AND f.run_id IS NOT NULL AND p.run_id IS NOT NULL AND f.run_id<>p.run_id),
    'probe_unbound_run',count(*) FILTER(WHERE p.id IS NOT NULL AND (f.run_id IS NULL OR p.run_id IS NULL)),
    'null_metrics',count(*) FILTER(WHERE f.metrics IS NULL),
    'json_null_metrics',count(*) FILTER(WHERE f.metrics='null'::jsonb),
    'metrics_wrong_shape',count(*) FILTER(WHERE f.metrics IS NOT NULL AND jsonb_typeof(f.metrics) NOT IN ('object','null'))
  ) FROM public.vn_fitness_snapshots f
  LEFT JOIN public.vn_probes p ON p.id=f.probe_id
  LEFT JOIN public.vn_colonies c ON c.id=f.run_id
  UNION ALL
  SELECT 'vn_generation_stats', jsonb_build_object(
    'total',count(*),'null_owner',count(*) FILTER(WHERE g.user_id IS NULL),
    'distinct_owners',count(DISTINCT g.user_id),'distinct_nonnull_runs',count(DISTINCT g.run_id),
    'distinct_owner_run_groups',count(DISTINCT (g.user_id,g.run_id)),
    'null_run',count(*) FILTER(WHERE g.run_id IS NULL),
    'missing_colony',count(*) FILTER(WHERE g.run_id IS NOT NULL AND c.id IS NULL),
    'colony_owner_mismatch',count(*) FILTER(WHERE c.id IS NOT NULL AND g.user_id IS DISTINCT FROM c.user_id),
    'duplicate_owner_run_generation_groups',
      (SELECT count(*) FROM (SELECT user_id,run_id,generation FROM public.vn_generation_stats
         GROUP BY user_id,run_id,generation HAVING count(*)>1) duplicates)
  ) FROM public.vn_generation_stats g LEFT JOIN public.vn_colonies c ON c.id=g.run_id
)
SELECT jsonb_build_object(
  'session',jsonb_build_object('read_only',current_setting('transaction_read_only'),
    'isolation',current_setting('transaction_isolation'),
    'statement_timeout',current_setting('statement_timeout'),
    'lock_timeout',current_setting('lock_timeout'),
    'postgres_version',current_setting('server_version')),
  'tables',(SELECT jsonb_agg(jsonb_build_object('name',t.relname,
    'owner',pg_get_userbyid(t.relowner),'rls',t.relrowsecurity,'force_rls',t.relforcerowsecurity,
    'replica_identity',t.relreplident) ORDER BY t.relname) FROM tables t),
  'columns',(SELECT jsonb_agg(jsonb_build_object('table',t.relname,'name',a.attname,
    'type',format_type(a.atttypid,a.atttypmod),'not_null',a.attnotnull,
    'default',pg_get_expr(d.adbin,d.adrelid),'column_acl',a.attacl::text)
    ORDER BY t.relname,a.attnum)
    FROM tables t JOIN pg_catalog.pg_attribute a ON a.attrelid=t.oid
    LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=t.oid AND d.adnum=a.attnum
    WHERE a.attnum>0 AND NOT a.attisdropped),
  'constraints',(SELECT jsonb_agg(jsonb_build_object('table',t.relname,'name',c.conname,
    'type',c.contype,'validated',c.convalidated,'definition',pg_get_constraintdef(c.oid,true))
    ORDER BY t.relname,c.conname) FROM tables t JOIN pg_catalog.pg_constraint c ON c.conrelid=t.oid),
  'incoming_foreign_keys',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,
    'table',source.relname,'owner',pg_get_userbyid(source.relowner),'target',t.relname,
    'name',c.conname,'validated',c.convalidated,'deferrable',c.condeferrable,
    'initially_deferred',c.condeferred,'definition',pg_get_constraintdef(c.oid,true))
    ORDER BY n.nspname,source.relname,c.conname),'[]'::jsonb)
    FROM tables t JOIN pg_catalog.pg_constraint c ON c.confrelid=t.oid AND c.contype='f'
    JOIN pg_catalog.pg_class source ON source.oid=c.conrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=source.relnamespace),
  'indexes',(SELECT jsonb_agg(jsonb_build_object('table',t.relname,'name',ic.relname,
    'valid',i.indisvalid,'ready',i.indisready,'definition',pg_get_indexdef(i.indexrelid))
    ORDER BY t.relname,ic.relname) FROM tables t JOIN pg_catalog.pg_index i ON i.indrelid=t.oid
    JOIN pg_catalog.pg_class ic ON ic.oid=i.indexrelid),
  'triggers',(SELECT jsonb_agg(jsonb_build_object('table',t.relname,'name',tr.tgname,
    'enabled',tr.tgenabled,'function_schema',n.nspname,'function',p.proname,
    'security_definer',p.prosecdef,'function_owner',pg_get_userbyid(p.proowner),
    'definition',pg_get_triggerdef(tr.oid,true)) ORDER BY t.relname,tr.tgname)
    FROM tables t JOIN pg_catalog.pg_trigger tr ON tr.tgrelid=t.oid
    JOIN pg_catalog.pg_proc p ON p.oid=tr.tgfoid
    JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE NOT tr.tgisinternal),
  'policies',(SELECT jsonb_agg(jsonb_build_object('table',tablename,'name',policyname,
    'roles',roles,'command',cmd,'permissive',permissive,'using',qual,'check',with_check)
    ORDER BY tablename,policyname) FROM pg_catalog.pg_policies
    WHERE schemaname='public' AND tablename IN (SELECT relname FROM tables)),
  'table_acl',(SELECT jsonb_agg(jsonb_build_object('table',t.relname,
    'grantee',CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
    'grantor',pg_get_userbyid(a.grantor),'privilege',a.privilege_type,'grantable',a.is_grantable)
    ORDER BY t.relname,a.grantee,a.privilege_type)
    FROM tables t CROSS JOIN LATERAL aclexplode(coalesce(t.relacl,acldefault('r',t.relowner))) a),
  'effective_table_privileges',(SELECT jsonb_agg(jsonb_build_object('role',r.rolname,'table',t.relname,
    'select',has_table_privilege(r.oid,t.oid,'SELECT'),'insert',has_table_privilege(r.oid,t.oid,'INSERT'),
    'update',has_table_privilege(r.oid,t.oid,'UPDATE'),'delete',has_table_privilege(r.oid,t.oid,'DELETE'),
    'truncate',has_table_privilege(r.oid,t.oid,'TRUNCATE'),'references',has_table_privilege(r.oid,t.oid,'REFERENCES'),
    'trigger',has_table_privilege(r.oid,t.oid,'TRIGGER'),'maintain',has_table_privilege(r.oid,t.oid,'MAINTAIN'),
    'any_column_select',has_any_column_privilege(r.oid,t.oid,'SELECT'),
    'any_column_insert',has_any_column_privilege(r.oid,t.oid,'INSERT'),
    'any_column_update',has_any_column_privilege(r.oid,t.oid,'UPDATE'))
    ORDER BY r.rolname,t.relname) FROM clients r CROSS JOIN tables t),
  'client_roles',(SELECT jsonb_agg(jsonb_build_object('name',rolname,'inherit',rolinherit,
    'bypass_rls',rolbypassrls,'superuser',rolsuper) ORDER BY rolname) FROM clients),
  'reachable_role_memberships',(SELECT coalesce(jsonb_agg(jsonb_build_object(
    'member',pg_get_userbyid(m.member),'granted_role',pg_get_userbyid(m.roleid),
    'inherit',m.inherit_option,'set',m.set_option,'admin',m.admin_option)
    ORDER BY m.member,m.roleid),'[]'::jsonb) FROM pg_catalog.pg_auth_members m
    WHERE m.member IN (SELECT ancestor FROM ancestors)),
  'membership_scan_truncated',EXISTS(SELECT 1 FROM ancestors a
    JOIN pg_catalog.pg_auth_members m ON m.member=a.ancestor
    WHERE cardinality(a.path)=16 AND NOT m.roleid=ANY(a.path)),
  'schema_privileges',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'owner',pg_get_userbyid(n.nspowner),
    'role',r.rolname,'usage',has_schema_privilege(r.oid,n.oid,'USAGE'),
    'create',has_schema_privilege(r.oid,n.oid,'CREATE')) ORDER BY n.nspname,r.rolname)
    FROM pg_catalog.pg_namespace n CROSS JOIN clients r WHERE n.nspname IN ('public','vn_durability')),
  'settable_role_privileges',(SELECT coalesce(jsonb_agg(jsonb_build_object('client',c.rolname,
    'reachable_role',r.rolname,'inherited',pg_has_role(c.oid,r.oid,'USAGE'),
    'settable',pg_has_role(c.oid,r.oid,'SET'),'superuser',r.rolsuper,'bypass_rls',r.rolbypassrls)
    ORDER BY c.rolname,r.rolname),'[]'::jsonb)
    FROM (SELECT DISTINCT client,ancestor FROM ancestors) a
    JOIN clients c ON c.oid=a.client JOIN pg_catalog.pg_roles r ON r.oid=a.ancestor
    WHERE a.client<>a.ancestor),
  'vn_functions',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,'name',p.proname,
    'arguments',pg_get_function_identity_arguments(p.oid),'owner',pg_get_userbyid(p.proowner),
    'security_definer',p.prosecdef,'acl',p.proacl::text,
    'reviewed_settings',(SELECT jsonb_agg(v ORDER BY v) FROM unnest(p.proconfig) v
      WHERE split_part(v,'=',1) IN ('search_path','statement_timeout','lock_timeout','row_security')))
    ORDER BY n.nspname,p.proname,p.oid),'[]'::jsonb)
    FROM functions p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace),
  'vn_function_privileges',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,
    'name',p.proname,'arguments',pg_get_function_identity_arguments(p.oid),
    'role',r.rolname,'execute',has_function_privilege(r.oid,p.oid,'EXECUTE'))
    ORDER BY n.nspname,p.proname,p.oid,r.rolname),'[]'::jsonb)
    FROM functions p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace CROSS JOIN clients r),
  'dependent_views',(SELECT coalesce(jsonb_agg(DISTINCT jsonb_build_object('schema',n.nspname,
    'name',v.relname,'kind',v.relkind,'owner',pg_get_userbyid(v.relowner),
    'options',v.reloptions)),'[]'::jsonb)
    FROM tables t JOIN pg_catalog.pg_depend d ON d.refobjid=t.oid AND d.refclassid='pg_class'::regclass
    JOIN pg_catalog.pg_rewrite rw ON rw.oid=d.objid AND d.classid='pg_rewrite'::regclass
    JOIN pg_catalog.pg_class v ON v.oid=rw.ev_class
    JOIN pg_catalog.pg_namespace n ON n.oid=v.relnamespace WHERE v.relkind IN ('v','m')),
  'unexpected_vn_relations',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,
    'name',c.relname,'kind',c.relkind,'owner',pg_get_userbyid(c.relowner)) ORDER BY n.nspname,c.relname),'[]'::jsonb)
    FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname IN ('public','vn_durability') AND c.relkind IN ('r','p','v','m','S')
      AND (n.nspname='vn_durability' OR c.relname LIKE 'vn\_%' ESCAPE '\')
      AND c.oid NOT IN (SELECT oid FROM tables)),
  'related_default_acl',(SELECT coalesce(jsonb_agg(jsonb_build_object('role',pg_get_userbyid(d.defaclrole),
    'schema',n.nspname,'type',d.defaclobjtype,'acl',d.defaclacl::text)
    ORDER BY d.defaclrole,d.defaclnamespace,d.defaclobjtype),'[]'::jsonb)
    FROM pg_catalog.pg_default_acl d LEFT JOIN pg_catalog.pg_namespace n ON n.oid=d.defaclnamespace
    WHERE d.defaclrole IN (SELECT relowner FROM tables UNION SELECT proowner FROM functions
      UNION SELECT nspowner FROM pg_catalog.pg_namespace WHERE nspname='vn_durability')
      AND (d.defaclnamespace=0 OR n.nspname IN ('public','vn_durability'))),
  'related_sequences',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,
    'name',s.relname,'owner',pg_get_userbyid(s.relowner),'acl',s.relacl::text)
    ORDER BY n.nspname,s.relname),'[]'::jsonb)
    FROM sequences s JOIN pg_catalog.pg_namespace n ON n.oid=s.relnamespace),
  'sequence_privileges',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema',n.nspname,
    'name',s.relname,'role',r.rolname,'select',has_sequence_privilege(r.oid,s.oid,'SELECT'),
    'usage',has_sequence_privilege(r.oid,s.oid,'USAGE'),'update',has_sequence_privilege(r.oid,s.oid,'UPDATE'))
    ORDER BY n.nspname,s.relname,r.rolname),'[]'::jsonb)
    FROM sequences s JOIN pg_catalog.pg_namespace n ON n.oid=s.relnamespace CROSS JOIN clients r),
  'reviewed_role_database_settings',(SELECT coalesce(jsonb_agg(jsonb_build_object(
    'role',CASE WHEN s.setrole=0 THEN 'ALL' ELSE pg_get_userbyid(s.setrole) END,
    'database_scope',CASE WHEN s.setdatabase=0 THEN 'ALL' ELSE 'CURRENT' END,
    'setting',v) ORDER BY s.setrole,s.setdatabase,v),'[]'::jsonb)
    FROM pg_catalog.pg_db_role_setting s CROSS JOIN LATERAL unnest(s.setconfig) v
    WHERE (s.setdatabase=0 OR s.setdatabase=(SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()))
      AND (s.setrole=0 OR s.setrole IN (SELECT oid FROM clients UNION SELECT proowner FROM functions UNION SELECT relowner FROM tables))
      AND split_part(v,'=',1) IN ('pgrst.db_schemas','pgrst.db_extra_search_path','pgrst.db_tx_end',
        'pgrst.db_pre_request','pgrst.db_max_rows','pgrst.db_pool','pgrst.db_pool_acquisition_timeout',
        'pgrst.jwt_aud','statement_timeout','lock_timeout','search_path','row_security')),
  'realtime_tables',(SELECT coalesce(jsonb_agg(jsonb_build_object('publication',pubname,'table',tablename)
    ORDER BY pubname,tablename),'[]'::jsonb) FROM pg_catalog.pg_publication_tables
    WHERE schemaname='public' AND tablename IN (SELECT relname FROM tables)),
  'durability_schema_present',EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname='vn_durability'),
  'migration_versions',(SELECT jsonb_agg(version ORDER BY version) FROM supabase_migrations.schema_migrations),
  'row_counts',(SELECT jsonb_object_agg(table_name,counts) FROM row_counts),
  'parent_array_counts',(SELECT jsonb_build_object(
    'elements',count(*),'invalid_uuid',count(*) FILTER(WHERE e.parent_id IS NULL),
    'self_parent',count(*) FILTER(WHERE e.parent_id=e.id),
    'missing_parent',count(*) FILTER(WHERE e.parent_id IS NOT NULL AND p.id IS NULL),
    'owner_mismatch',count(*) FILTER(WHERE p.id IS NOT NULL AND e.user_id IS DISTINCT FROM p.user_id),
    'bound_run_mismatch',count(*) FILTER(WHERE p.id IS NOT NULL AND e.run_id IS NOT NULL AND p.run_id IS NOT NULL AND e.run_id<>p.run_id),
    'unbound_run',count(*) FILTER(WHERE p.id IS NOT NULL AND (e.run_id IS NULL OR p.run_id IS NULL)),
    'duplicate_groups',(SELECT count(*) FROM (SELECT id,value FROM parent_elements GROUP BY id,value HAVING count(*)>1) duplicates)
  ) FROM parent_elements e LEFT JOIN public.vn_probes p ON p.id=e.parent_id)
) AS inventory;
ROLLBACK;
