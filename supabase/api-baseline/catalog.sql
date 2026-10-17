-- Scoped, read-only, PG17 catalog. No row data, routine bodies or expressions
-- outside the two roots. Native expression trees are compared, never evaluated.
WITH
names(name) AS (VALUES ('market_sentiment'::text), ('test_events'::text)),
roots AS MATERIALIZED (
    SELECT c.* FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    JOIN names t ON t.name=c.relname WHERE n.nspname='public'
),
relations AS MATERIALIZED (
    SELECT r.relname::text AS root, 'table:' || r.relname AS label, r.oid
    FROM roots r
    UNION ALL
    SELECT r.relname::text, 'index:' || c.relname, c.oid
    FROM roots r JOIN pg_catalog.pg_index i ON i.indrelid=r.oid
    JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid
    UNION ALL
    SELECT r.relname::text, 'toast:' || r.relname, r.reltoastrelid FROM roots r WHERE r.reltoastrelid<>0
    UNION ALL
    SELECT r.relname::text, 'toast-index:' || r.relname || ':' ||
        pg_catalog.row_number() OVER (PARTITION BY r.oid ORDER BY i.indexrelid)::text, i.indexrelid
    FROM roots r JOIN pg_catalog.pg_index i ON i.indrelid=r.reltoastrelid
),
attrs AS MATERIALIZED (
    SELECT z.root,z.label,a.* FROM relations z
    JOIN pg_catalog.pg_attribute a ON a.attrelid=z.oid WHERE a.attnum>0
),
defs AS MATERIALIZED (
    SELECT z.root, 'default:' || z.root || ':' || a.attname AS label,d.*
    FROM relations z JOIN pg_catalog.pg_attrdef d ON d.adrelid=z.oid
    JOIN pg_catalog.pg_attribute a ON a.attrelid=d.adrelid AND a.attnum=d.adnum
),
cons AS MATERIALIZED (
    SELECT r.relname::text AS root,'constraint:' || r.relname || ':' || c.conname AS label,c.*
    FROM roots r JOIN pg_catalog.pg_constraint c ON c.conrelid=r.oid
),
types AS MATERIALIZED (
    SELECT r.relname::text AS root,'row-type:' || r.relname AS label,y.*
    FROM roots r JOIN pg_catalog.pg_type y ON y.oid=r.reltype
    UNION ALL
    SELECT r.relname::text,'array-type:' || r.relname,y.* FROM roots r
    JOIN pg_catalog.pg_type v ON v.oid=r.reltype JOIN pg_catalog.pg_type y ON y.oid=v.typarray
),
owned(root,label,classid,objid) AS MATERIALIZED (
    SELECT root,label,'pg_catalog.pg_class'::pg_catalog.regclass::oid,oid FROM relations
    UNION ALL SELECT root,label,'pg_catalog.pg_attrdef'::pg_catalog.regclass::oid,oid FROM defs
    UNION ALL SELECT root,label,'pg_catalog.pg_constraint'::pg_catalog.regclass::oid,oid FROM cons
    UNION ALL SELECT root,label,'pg_catalog.pg_type'::pg_catalog.regclass::oid,oid FROM types
    UNION ALL SELECT r.relname,'trigger:' || r.relname || ':' || t.tgname,
        'pg_catalog.pg_trigger'::pg_catalog.regclass::oid,t.oid
        FROM roots r JOIN pg_catalog.pg_trigger t ON t.tgrelid=r.oid
    UNION ALL SELECT r.relname,'rule:' || r.relname || ':' || w.rulename,
        'pg_catalog.pg_rewrite'::pg_catalog.regclass::oid,w.oid
        FROM roots r JOIN pg_catalog.pg_rewrite w ON w.ev_class=r.oid
    UNION ALL SELECT r.relname,'policy:' || r.relname || ':' || p.polname,
        'pg_catalog.pg_policy'::pg_catalog.regclass::oid,p.oid
        FROM roots r JOIN pg_catalog.pg_policy p ON p.polrelid=r.oid
),
edges AS MATERIALIZED (
    SELECT d.* FROM pg_catalog.pg_depend d
    WHERE EXISTS (SELECT 1 FROM owned o WHERE (o.classid,o.objid)=(d.classid,d.objid))
       OR EXISTS (SELECT 1 FROM owned o WHERE (o.classid,o.objid)=(d.refclassid,d.refobjid))
),
expressions AS MATERIALIZED (
    SELECT root,label,adbin::text AS tree FROM defs
    UNION ALL SELECT root,label,conbin::text FROM cons WHERE conbin IS NOT NULL
),
operator_ids AS MATERIALIZED (
    SELECT DISTINCT e.root,m.v[1]::oid AS oid FROM expressions e
    CROSS JOIN LATERAL pg_catalog.regexp_matches(e.tree,':opno ([0-9]+)','g') m(v)
    WHERE pg_catalog.octet_length(e.tree)<=16384
),
function_ids AS MATERIALIZED (
    SELECT DISTINCT e.root, m.v[1]::oid AS oid FROM expressions e
    CROSS JOIN LATERAL pg_catalog.regexp_matches(e.tree,':(?:funcid|opfuncid) ([0-9]+)','g') m(v)
    WHERE pg_catalog.octet_length(e.tree)<=16384 AND m.v[1]::oid<>0
    UNION
    SELECT f.root,o.oprcode::oid FROM operator_ids f JOIN pg_catalog.pg_operator o ON o.oid=f.oid
    WHERE o.oprcode::oid<>0
),
counts AS MATERIALIZED (
    SELECT (SELECT pg_catalog.count(*) FROM owned) AS objects,
        (SELECT pg_catalog.count(*) FROM attrs) AS attributes,
        (SELECT pg_catalog.count(*) FROM edges) AS dependencies,
        (SELECT pg_catalog.count(*) FROM expressions) AS expressions,
        (SELECT pg_catalog.count(*) FROM function_ids) AS functions,
        (SELECT pg_catalog.count(*) FROM operator_ids) AS operators,
        (SELECT pg_catalog.count(*) FROM expressions WHERE tree IS NULL OR pg_catalog.octet_length(tree)>16384) AS bad_expression,
        (SELECT pg_catalog.count(*) FROM function_ids f LEFT JOIN pg_catalog.pg_proc p ON p.oid=f.oid
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
            WHERE p.oid IS NULL OR n.nspname<>'pg_catalog')+
        (SELECT pg_catalog.count(*) FROM operator_ids f LEFT JOIN pg_catalog.pg_operator o ON o.oid=f.oid
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid=o.oprnamespace
            WHERE o.oid IS NULL OR n.nspname<>'pg_catalog') AS bad_native_lookup,
        (SELECT pg_catalog.count(*) FROM owned o JOIN pg_catalog.pg_shdepend d ON d.classid=o.classid AND d.objid=o.objid
            WHERE d.dbid=(SELECT oid FROM pg_catalog.pg_database WHERE datname=pg_catalog.current_database())) AS shared_dependencies
),
bounded AS MATERIALIZED (
    SELECT *, objects<=64 AND attributes<=128 AND dependencies<=256 AND expressions<=16
        AND functions<=16 AND operators<=16 AND bad_expression=0 AND bad_native_lookup=0 AND shared_dependencies<=128 AS complete
    FROM counts
),
relation_facts AS MATERIALIZED (
    SELECT z.root,z.label,pg_catalog.jsonb_build_object(
        'label',z.label,'schema',n.nspname,'kind',c.relkind,'persistence',c.relpersistence,
        'owner',pg_catalog.pg_get_userbyid(c.relowner),'access_method',am.amname,
        'tablespace',CASE WHEN c.reltablespace=0 THEN 'database-default' ELSE ts.spcname END,
        'column_count',c.relnatts,'check_count',c.relchecks,'typed_table_present',c.reloftype<>0,
        'row_type',rt.label,'toast_relation',tr.label,'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,
        'replica_identity',c.relreplident,'is_partition',c.relispartition,
        'partition_bound_present',c.relpartbound IS NOT NULL,'options_present',c.reloptions IS NOT NULL,
        'columns',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'number',a.attnum,'name',a.attname,'type_oid',a.atttypid::text,
            'type_schema',yn.nspname,'type_name',y.typname,'type_kind',y.typtype,
            'type_base_oid',y.typbasetype::text,'type_not_null',y.typnotnull,
            'typmod',a.atttypmod,'dimensions',a.attndims,'not_null',a.attnotnull,
            'has_default',a.atthasdef,'has_missing',a.atthasmissing,'identity',a.attidentity,
            'generated',a.attgenerated,'dropped',a.attisdropped,'local',a.attislocal,
            'inheritance_count',a.attinhcount,'storage',a.attstorage,'compression',a.attcompression,
            'collation_oid',a.attcollation::text,'collation_schema',cn.nspname,'collation_name',co.collname,
            'collation_provider',co.collprovider,'collation_deterministic',co.collisdeterministic,
            'collation_encoding',co.collencoding,'collation_version',co.collversion,
            'options_present',a.attoptions IS NOT NULL,'fdw_options_present',a.attfdwoptions IS NOT NULL)
            ORDER BY a.attnum) FROM attrs a LEFT JOIN pg_catalog.pg_type y ON y.oid=a.atttypid
            LEFT JOIN pg_catalog.pg_namespace yn ON yn.oid=y.typnamespace
            LEFT JOIN pg_catalog.pg_collation co ON co.oid=a.attcollation
            LEFT JOIN pg_catalog.pg_namespace cn ON cn.oid=co.collnamespace
            WHERE a.attrelid=z.oid),'[]'::pg_catalog.jsonb),
        'index',CASE WHEN i.indexrelid IS NULL THEN NULL ELSE pg_catalog.jsonb_build_object(
            'table',it.label,'attribute_count',i.indnatts,'key_count',i.indnkeyatts,
            'unique',i.indisunique,'nulls_not_distinct',i.indnullsnotdistinct,'primary',i.indisprimary,
            'exclusion',i.indisexclusion,'immediate',i.indimmediate,'clustered',i.indisclustered,
            'valid',i.indisvalid,'ready',i.indisready,'live',i.indislive,'check_xmin',i.indcheckxmin,
            'replica_identity',i.indisreplident,'key_numbers',i.indkey::text,
            'collation_oids',i.indcollation::text,'opclass_oids',i.indclass::text,'options_bits',i.indoption::text,
            'predicate_present',i.indpred IS NOT NULL,'expressions_present',i.indexprs IS NOT NULL,
            'opclasses',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
                'ordinal',u.ord,'oid',oc.oid::text,'schema',onsp.nspname,'name',oc.opcname,
                'owner_oid',oc.opcowner::pg_catalog.int8,'method_oid',oc.opcmethod::text,
                'family_oid',oc.opcfamily::text,'family_schema',fn.nspname,'family_name',f.opfname,
                'input_type_oid',oc.opcintype::text,'key_type_oid',oc.opckeytype::text,'default',oc.opcdefault)
                ORDER BY u.ord) FROM pg_catalog.unnest(i.indclass::oid[]) WITH ORDINALITY u(id,ord)
                LEFT JOIN pg_catalog.pg_opclass oc ON oc.oid=u.id
                LEFT JOIN pg_catalog.pg_namespace onsp ON onsp.oid=oc.opcnamespace
                LEFT JOIN pg_catalog.pg_opfamily f ON f.oid=oc.opcfamily
                LEFT JOIN pg_catalog.pg_namespace fn ON fn.oid=f.opfnamespace),'[]'::pg_catalog.jsonb)) END
        ) AS fact
    FROM relations z JOIN pg_catalog.pg_class c ON c.oid=z.oid
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    LEFT JOIN pg_catalog.pg_am am ON am.oid=c.relam
    LEFT JOIN pg_catalog.pg_tablespace ts ON ts.oid=c.reltablespace
    LEFT JOIN owned rt ON rt.classid='pg_catalog.pg_type'::pg_catalog.regclass AND rt.objid=c.reltype
    LEFT JOIN relations tr ON tr.oid=c.reltoastrelid
    LEFT JOIN pg_catalog.pg_index i ON i.indexrelid=c.oid
    LEFT JOIN relations it ON it.oid=i.indrelid
    WHERE (SELECT complete FROM bounded)
),
table_facts AS MATERIALIZED (
    SELECT r.relname AS name,pg_catalog.jsonb_build_object(
        'relations',COALESCE((SELECT pg_catalog.jsonb_agg(f.fact ORDER BY f.label) FROM relation_facts f WHERE f.root=r.relname),'[]'::pg_catalog.jsonb),
        'defaults',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'label',d.label,'column',d.adnum,
            'tree',CASE WHEN pg_catalog.pg_get_expr(d.adbin,d.adrelid,false) IN
                ('gen_random_uuid()','pg_catalog.gen_random_uuid()','now()','pg_catalog.now()',
                 'CURRENT_DATE','''[]''::jsonb','''grok''::text','''unknown''::text')
                THEN pg_catalog.regexp_replace(d.adbin::text,':location -?[0-9]+',':location -1','g') ELSE NULL END)
            ORDER BY d.label) FROM defs d WHERE d.root=r.relname),'[]'::pg_catalog.jsonb),
        'constraints',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'label',c.label,'name',c.conname,'kind',c.contype,'schema',cn.nspname,
            'validated',c.convalidated,'deferrable',c.condeferrable,'deferred',c.condeferred,
            'local',c.conislocal,'inheritance_count',c.coninhcount,'no_inherit',c.connoinherit,
            'parent_present',c.conparentid<>0,'domain_present',c.contypid<>0,
            'index',oi.label,'referenced_relation',fr.label,'keys',c.conkey,'referenced_keys',c.confkey,
            'exclusion_present',c.conexclop IS NOT NULL,
            'tree',CASE WHEN pg_catalog.pg_get_constraintdef(c.oid,true) IN
                ('PRIMARY KEY (id)','UNIQUE (date)','CHECK (score >= 0 AND score <= 100)',
                 'CHECK (sentiment = ANY (ARRAY[''bullish''::text, ''bearish''::text, ''neutral''::text]))')
                THEN pg_catalog.regexp_replace(c.conbin::text,':location -?[0-9]+',':location -1','g') ELSE NULL END)
            ORDER BY c.label) FROM cons c JOIN pg_catalog.pg_namespace cn ON cn.oid=c.connamespace
            LEFT JOIN relations oi ON oi.oid=c.conindid LEFT JOIN relations fr ON fr.oid=c.confrelid
            WHERE c.root=r.relname),'[]'::pg_catalog.jsonb),
        'types',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'label',y.label,'schema',yn.nspname,'name',y.typname,'owner',pg_catalog.pg_get_userbyid(y.typowner),
            'kind',y.typtype,'relation',yr.label,'element',ye.label,'array',ya.label,
            'base_oid',y.typbasetype::text,'not_null',y.typnotnull,'dimensions',y.typndims,
            'typmod',y.typtypmod,'collation_oid',y.typcollation::text,'default_present',y.typdefault IS NOT NULL,
            'length',y.typlen,'by_value',y.typbyval,'alignment',y.typalign,'storage',y.typstorage,
            'input_oid',y.typinput::pg_catalog.oid::text,'output_oid',y.typoutput::pg_catalog.oid::text,
            'receive_oid',y.typreceive::pg_catalog.oid::text,'send_oid',y.typsend::pg_catalog.oid::text,
            'analyze_oid',y.typanalyze::pg_catalog.oid::text,'subscript_oid',y.typsubscript::pg_catalog.oid::text)
            ORDER BY y.label) FROM types y JOIN pg_catalog.pg_namespace yn ON yn.oid=y.typnamespace
            LEFT JOIN relations yr ON yr.oid=y.typrelid
            LEFT JOIN types ye ON ye.oid=y.typelem LEFT JOIN types ya ON ya.oid=y.typarray
            WHERE y.root=r.relname),'[]'::pg_catalog.jsonb),
        'functions',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'oid',f.oid::text,'schema',pn.nspname,'name',p.proname,'owner_oid',p.proowner::pg_catalog.int8,
            'language',l.lanname,'kind',p.prokind,'argument_types',p.proargtypes::text,
            'return_oid',p.prorettype::text,'returns_set',p.proretset,'strict',p.proisstrict,
            'security_definer',p.prosecdef,'volatility',p.provolatile,'parallel',p.proparallel,
            'configuration_present',p.proconfig IS NOT NULL) ORDER BY f.oid)
            FROM function_ids f LEFT JOIN pg_catalog.pg_proc p ON p.oid=f.oid
            LEFT JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
            LEFT JOIN pg_catalog.pg_language l ON l.oid=p.prolang WHERE f.root=r.relname),'[]'::pg_catalog.jsonb),
        'operators',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'oid',f.oid::text,'schema',onsp.nspname,'name',o.oprname,'owner_oid',o.oprowner::pg_catalog.int8,
            'kind',o.oprkind,'left_oid',o.oprleft::text,'right_oid',o.oprright::text,'result_oid',o.oprresult::text,
            'code_oid',o.oprcode::oid::text,'commutator_oid',o.oprcom::text,'negator_oid',o.oprnegate::text,
            'can_merge',o.oprcanmerge,'can_hash',o.oprcanhash) ORDER BY f.oid)
            FROM operator_ids f LEFT JOIN pg_catalog.pg_operator o ON o.oid=f.oid
            LEFT JOIN pg_catalog.pg_namespace onsp ON onsp.oid=o.oprnamespace WHERE f.root=r.relname),'[]'::pg_catalog.jsonb),
        'adjunct_counts',pg_catalog.jsonb_build_object(
            'triggers',(SELECT pg_catalog.count(*) FROM pg_catalog.pg_trigger t WHERE t.tgrelid=r.oid OR t.tgconstrrelid=r.oid),
            'rules',(SELECT pg_catalog.count(*) FROM pg_catalog.pg_rewrite w WHERE w.ev_class=r.oid),
            'policies',(SELECT pg_catalog.count(*) FROM pg_catalog.pg_policy p WHERE p.polrelid=r.oid),
            'inheritance',(SELECT pg_catalog.count(*) FROM pg_catalog.pg_inherits h WHERE h.inhrelid=r.oid OR h.inhparent=r.oid),
            'partitions',(SELECT pg_catalog.count(*) FROM pg_catalog.pg_partitioned_table p WHERE p.partrelid=r.oid)),
        'dependencies',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'from',COALESCE(so.label,si.identity),'from_class',d.classid::pg_catalog.regclass::text,'from_subid',d.objsubid,
            'to',COALESCE(ro.label,ri.identity),'to_class',d.refclassid::pg_catalog.regclass::text,'to_subid',d.refobjsubid,
            'from_owned',so.label IS NOT NULL,'to_owned',ro.label IS NOT NULL,'kind',d.deptype)
            ORDER BY COALESCE(so.label,si.identity),d.objsubid,COALESCE(ro.label,ri.identity),d.refobjsubid,d.deptype)
            FROM edges d LEFT JOIN owned so ON (so.classid,so.objid)=(d.classid,d.objid)
            LEFT JOIN owned ro ON (ro.classid,ro.objid)=(d.refclassid,d.refobjid)
            CROSS JOIN LATERAL pg_catalog.pg_identify_object(d.classid,d.objid,d.objsubid) si
            CROSS JOIN LATERAL pg_catalog.pg_identify_object(d.refclassid,d.refobjid,d.refobjsubid) ri
            WHERE so.root=r.relname OR ro.root=r.relname),'[]'::pg_catalog.jsonb),
        'shared_structural_dependencies',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'label',o.label,'subid',d.objsubid,'referenced_class',d.refclassid::pg_catalog.regclass::text,
            'referenced_role',pr.rolname,'kind',d.deptype) ORDER BY o.label,d.objsubid,pr.rolname,d.deptype)
            FROM owned o JOIN pg_catalog.pg_shdepend d ON (d.classid,d.objid)=(o.classid,o.objid)
            LEFT JOIN pg_catalog.pg_roles pr ON d.refclassid='pg_catalog.pg_authid'::pg_catalog.regclass AND pr.oid=d.refobjid
            WHERE o.root=r.relname AND d.dbid=(SELECT oid FROM pg_catalog.pg_database WHERE datname=pg_catalog.current_database())
                AND d.deptype<>'a'),'[]'::pg_catalog.jsonb)
        ) AS fact
    FROM roots r WHERE (SELECT complete FROM bounded)
),
permission_facts AS MATERIALIZED (
    SELECT r.relname,pg_catalog.jsonb_build_object(
        'grants',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'grantor',pg_catalog.pg_get_userbyid(x.grantor),'grantee',CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(x.grantee) END,
            'privilege',x.privilege_type,'grantable',x.is_grantable)
            ORDER BY CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(x.grantee) END,
                x.privilege_type,pg_catalog.pg_get_userbyid(x.grantor))
            FROM pg_catalog.aclexplode(COALESCE(r.relacl,pg_catalog.acldefault('r',r.relowner))) x),'[]'::pg_catalog.jsonb),
        'column_acl_present',EXISTS(SELECT 1 FROM attrs a WHERE a.root=r.relname AND a.attacl IS NOT NULL),
        'adjunct_acl_present',EXISTS(SELECT 1 FROM relations z JOIN pg_catalog.pg_class c ON c.oid=z.oid
            WHERE z.root=r.relname AND z.oid<>r.oid AND c.relacl IS NOT NULL)
            OR EXISTS(SELECT 1 FROM types y WHERE y.root=r.relname AND y.typacl IS NOT NULL),
        'effective',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'role',p.rolname,'table', (SELECT pg_catalog.jsonb_object_agg(v,pg_catalog.has_table_privilege(p.oid,r.oid,v))
                FROM pg_catalog.unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN']) v),
            'columns',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
                'name',a.attname,'privileges',(SELECT pg_catalog.jsonb_object_agg(v,pg_catalog.has_column_privilege(p.oid,r.oid,a.attnum,v))
                    FROM pg_catalog.unnest(ARRAY['SELECT','INSERT','UPDATE','REFERENCES']) v)) ORDER BY a.attnum)
                FROM attrs a WHERE a.attrelid=r.oid),'[]'::pg_catalog.jsonb)) ORDER BY p.rolname)
            FROM pg_catalog.pg_roles p WHERE p.rolname IN ('anon','authenticated','service_role')),'[]'::pg_catalog.jsonb)
        ) AS fact FROM roots r WHERE (SELECT complete FROM bounded)
)
SELECT pg_catalog.jsonb_build_object(
    'format','dashboard-api-two-table-catalog-v1','complete',(SELECT complete FROM bounded),
    'counts',(SELECT pg_catalog.to_jsonb(b)-'complete' FROM bounded b),
    'structure',pg_catalog.jsonb_build_object('tables',COALESCE((SELECT pg_catalog.jsonb_object_agg(name,fact ORDER BY name) FROM table_facts),'{}'::pg_catalog.jsonb)),
    'permissions',COALESCE((SELECT pg_catalog.jsonb_object_agg(relname,fact ORDER BY relname) FROM permission_facts),'{}'::pg_catalog.jsonb),
    'collisions',pg_catalog.jsonb_build_object(
        'relations',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('name',c.relname,'kind',c.relkind,
            'root',z.root,'label',z.label) ORDER BY c.relname)
            FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN relations z ON z.oid=c.oid WHERE n.nspname='public' AND c.relname IN
            ('market_sentiment','test_events','market_sentiment_pkey','market_sentiment_date_key','idx_market_sentiment_date','test_events_pkey','idx_test_events_created_at')),'[]'::pg_catalog.jsonb),
        'types',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object('name',y.typname,'kind',y.typtype,
            'root',z.root,'label',z.label) ORDER BY y.typname)
            FROM pg_catalog.pg_type y JOIN pg_catalog.pg_namespace n ON n.oid=y.typnamespace
            LEFT JOIN types z ON z.oid=y.oid WHERE n.nspname='public' AND y.typname IN
            ('market_sentiment','test_events','_market_sentiment','_test_events')),'[]'::pg_catalog.jsonb)),
    'identities',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
        'label',o.label,'class_oid',o.classid::text,'object_oid',o.objid::text) ORDER BY o.label)
        FROM owned o WHERE (SELECT complete FROM bounded)),'[]'::pg_catalog.jsonb),
    'context',pg_catalog.jsonb_build_object(
        'server_version_num',pg_catalog.current_setting('server_version_num'),
        'database',pg_catalog.current_database(),'database_encoding',pg_catalog.getdatabaseencoding(),
        'current_user',current_user,'session_user',session_user,
        'schema_owner',(SELECT pg_catalog.pg_get_userbyid(nspowner) FROM pg_catalog.pg_namespace WHERE nspname='public'),
        'roles',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'name',p.rolname,'superuser',p.rolsuper,'inherit',p.rolinherit,'login',p.rolcanlogin,
            'bypass_rls',p.rolbypassrls,'create_role',p.rolcreaterole,'create_db',p.rolcreatedb,'replication',p.rolreplication,
            'schema_usage',pg_catalog.has_schema_privilege(p.oid,'public','USAGE'),
            'schema_create',pg_catalog.has_schema_privilege(p.oid,'public','CREATE'),
            'outgoing_memberships',(SELECT pg_catalog.count(*) FROM pg_catalog.pg_auth_members m WHERE m.member=p.oid))
            ORDER BY p.rolname) FROM pg_catalog.pg_roles p WHERE p.rolname IN ('anon','authenticated','service_role')),'[]'::pg_catalog.jsonb),
        'default_acls',COALESCE((SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
            'owner',pg_catalog.pg_get_userbyid(d.defaclrole),'schema',n.nspname,'kind',d.defaclobjtype,'acl',d.defaclacl::text)
            ORDER BY d.defaclnamespace,d.defaclobjtype) FROM pg_catalog.pg_default_acl d
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid=d.defaclnamespace
            WHERE d.defaclrole=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='postgres')
                AND (d.defaclnamespace=0 OR n.nspname='public')),'[]'::pg_catalog.jsonb)),
    'limits',pg_catalog.jsonb_build_object('rows_read',false,'schema_or_acl_changed',false,
        'concurrent_acl_excluded',false,'hosted_admission',false)
) AS catalog;
