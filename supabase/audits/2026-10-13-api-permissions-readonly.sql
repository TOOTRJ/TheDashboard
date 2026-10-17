-- Catalog/privilege inspection only, scoped to the two existing Dashboard API tables.
WITH RECURSIVE
target AS (
  SELECT c.oid,c.relname,c.relowner,c.relacl,c.relrowsecurity,c.relforcerowsecurity
  FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='public' AND c.relname IN ('test_events','market_sentiment') AND c.relkind='r'
),
roots AS (SELECT oid,rolname FROM pg_catalog.pg_roles WHERE rolname IN ('anon','authenticated','service_role')),
reachable(root,oid) AS (
  SELECT oid,oid FROM roots
  UNION SELECT x.root,m.roleid FROM reachable x JOIN pg_catalog.pg_auth_members m ON m.member=x.oid
)
SELECT pg_catalog.jsonb_build_object(
  'format','dashboard-api-effective-privilege-catalog-v1',
  'tables',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
    'name',t.relname,'owner',(SELECT rolname FROM pg_catalog.pg_roles WHERE oid=t.relowner),
    'raw_acl',t.relacl::text,'rls_enabled',t.relrowsecurity,'rls_forced',t.relforcerowsecurity,
    'policies',(SELECT COALESCE(jsonb_agg(jsonb_build_object('name',p.polname,'command',p.polcmd,'permissive',p.polpermissive,'roles',to_jsonb(p.polroles)) ORDER BY p.polname),'[]'::jsonb) FROM pg_catalog.pg_policy p WHERE p.polrelid=t.oid),
    'column_acl',(SELECT jsonb_agg(jsonb_build_object('column',a.attname,'raw_acl',a.attacl::text) ORDER BY a.attnum) FROM pg_catalog.pg_attribute a WHERE a.attrelid=t.oid AND a.attnum>0 AND NOT a.attisdropped),
    'effective_roles',(SELECT jsonb_agg(jsonb_build_object('role',r.rolname,
      'table',(SELECT jsonb_object_agg(v,has_table_privilege(r.oid,t.oid,v)) FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN']) v),
      'columns',(SELECT jsonb_agg(jsonb_build_object('column',a.attname,'privileges',(SELECT jsonb_object_agg(v,has_column_privilege(r.oid,t.oid,a.attnum,v)) FROM unnest(ARRAY['SELECT','INSERT','UPDATE','REFERENCES']) v)) ORDER BY a.attnum) FROM pg_catalog.pg_attribute a WHERE a.attrelid=t.oid AND a.attnum>0 AND NOT a.attisdropped)
    ) ORDER BY r.rolname) FROM roots r)
  ) ORDER BY t.relname) FROM target t),
  'roles',(SELECT jsonb_agg(jsonb_build_object('name',r.rolname,'oid',r.oid::text,'superuser',r.rolsuper,'inherit',r.rolinherit,'bypass_rls',r.rolbypassrls,'login',r.rolcanlogin,
    'public_schema_usage',has_schema_privilege(r.oid,'public','USAGE'),'public_schema_create',has_schema_privilege(r.oid,'public','CREATE'),
    'reachable_roles',(SELECT jsonb_agg(jsonb_build_object('name',s.rolname,'oid',s.oid::text,'superuser',s.rolsuper,'inherit',s.rolinherit,'bypass_rls',s.rolbypassrls) ORDER BY s.rolname) FROM reachable x JOIN pg_catalog.pg_roles s ON s.oid=x.oid WHERE x.root=r.oid),
    'memberships',(SELECT COALESCE(jsonb_agg(jsonb_build_object('member',m.member::text,'role',m.roleid::text,'admin',m.admin_option,'inherit',m.inherit_option,'set',m.set_option) ORDER BY m.member,m.roleid),'[]'::jsonb) FROM pg_catalog.pg_auth_members m WHERE m.member IN(SELECT oid FROM reachable WHERE root=r.oid))
  ) ORDER BY r.rolname) FROM pg_catalog.pg_roles r WHERE r.oid IN(SELECT oid FROM roots)),
  'public_table_grants',(SELECT COALESCE(jsonb_agg(jsonb_build_object('table',t.relname,'privilege',a.privilege_type,'grantable',a.is_grantable) ORDER BY t.relname,a.privilege_type),'[]'::jsonb) FROM target t CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(t.relacl,pg_catalog.acldefault('r',t.relowner))) a WHERE a.grantee=0),
  'relevant_default_acls',(SELECT COALESCE(jsonb_agg(jsonb_build_object('owner',r.rolname,'schema',n.nspname,'kind',d.defaclobjtype,'raw_acl',d.defaclacl::text) ORDER BY r.rolname,n.nspname,d.defaclobjtype),'[]'::jsonb) FROM pg_catalog.pg_default_acl d JOIN pg_catalog.pg_roles r ON r.oid=d.defaclrole LEFT JOIN pg_catalog.pg_namespace n ON n.oid=d.defaclnamespace WHERE d.defaclrole IN(SELECT relowner FROM target) AND (d.defaclnamespace=0 OR n.nspname='public')),
  'possible_local_function_consumers',(SELECT COALESCE(jsonb_agg(jsonb_build_object('schema',n.nspname,'name',p.proname,'arguments',pg_catalog.pg_get_function_identity_arguments(p.oid),'security_definer',p.prosecdef) ORDER BY n.nspname,p.proname,p.oid),'[]'::jsonb) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT IN('pg_catalog','information_schema') AND (p.prosrc ~ '(\mtest_events\M|\mmarket_sentiment\M)' OR EXISTS(SELECT 1 FROM pg_catalog.pg_depend d WHERE d.classid='pg_catalog.pg_proc'::regclass AND d.objid=p.oid AND d.refclassid='pg_catalog.pg_class'::regclass AND d.refobjid IN(SELECT oid FROM target))))
);
