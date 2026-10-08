-- Private metadata-only post-commit oracle. No ledger rows or credentials.
CREATE FUNCTION vn_release.catalog() RETURNS jsonb LANGUAGE sql STABLE
SET search_path=pg_catalog,vn_release,pg_temp AS $$
WITH namespaces AS (
 SELECT * FROM pg_namespace WHERE nspname IN ('vn_identity','vn_access','vn_durability',
  'vn_projection','vn_read','vn_legacy','vn_legacy_evidence','vn_release')
), relations AS (
 SELECT c.*,n.nspname FROM pg_class c JOIN namespaces n ON n.oid=c.relnamespace
)
SELECT jsonb_build_object(
 'schemas',(SELECT jsonb_agg(jsonb_build_array(nspname,pg_get_userbyid(nspowner),nspacl::text) ORDER BY nspname) FROM namespaces),
 'relations',(SELECT jsonb_agg(jsonb_build_array(nspname,relname,relkind,pg_get_userbyid(relowner),
   relrowsecurity,relforcerowsecurity,relreplident,relacl::text,reloptions) ORDER BY nspname,relname) FROM relations),
 'columns',(SELECT jsonb_agg(jsonb_build_array(c.nspname,c.relname,a.attnum,a.attname,
   format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,a.attacl::text,
   pg_get_expr(d.adbin,d.adrelid)) ORDER BY c.nspname,c.relname,a.attnum)
   FROM relations c JOIN pg_attribute a ON a.attrelid=c.oid LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
   WHERE a.attnum>0 AND NOT a.attisdropped),
 'constraints',(SELECT jsonb_agg(jsonb_build_array(c.nspname,c.relname,k.conname,k.contype,k.convalidated,
   k.condeferrable,k.condeferred,pg_get_constraintdef(k.oid,true)) ORDER BY c.nspname,c.relname,k.conname)
   FROM relations c JOIN pg_constraint k ON k.conrelid=c.oid),
 'indexes',(SELECT jsonb_agg(jsonb_build_array(c.nspname,c.relname,i.indisvalid,i.indisready,pg_get_indexdef(i.indexrelid))
   ORDER BY c.nspname,c.relname,pg_get_indexdef(i.indexrelid)) FROM relations c JOIN pg_index i ON i.indrelid=c.oid),
 'triggers',(SELECT jsonb_agg(jsonb_build_array(c.nspname,c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid,true))
   ORDER BY c.nspname,c.relname,t.tgname) FROM relations c JOIN pg_trigger t ON t.tgrelid=c.oid WHERE NOT t.tgisinternal),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.schemaname,p.tablename,p.policyname)
   FROM pg_policies p WHERE p.schemaname IN (SELECT nspname FROM namespaces)),
 'domain',(SELECT jsonb_build_array(format_type(t.oid,NULL),format_type(t.typbasetype,t.typtypmod),
    t.typnotnull,t.typdefault,t.typacl::text,pg_get_userbyid(t.typowner),
    (SELECT jsonb_agg(jsonb_build_array(k.conname,k.convalidated,pg_get_constraintdef(k.oid,true)) ORDER BY k.conname)
      FROM pg_constraint k WHERE k.contypid=t.oid)) FROM pg_type t WHERE t.oid='vn_durability.balance'::regtype),
 'functions',(SELECT jsonb_agg(jsonb_build_array(n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),
    pg_get_userbyid(p.proowner),p.prosecdef,p.provolatile,p.proisstrict,p.proleakproof,p.proparallel,p.proconfig,p.proacl::text,
    encode(sha256(convert_to(prosrc,'UTF8')),'hex')) ORDER BY n.nspname,p.proname,pg_get_function_identity_arguments(p.oid))
    FROM pg_proc p JOIN namespaces n ON n.oid=p.pronamespace),
 'roles',(SELECT jsonb_agg(to_jsonb(r)-'rolpassword' ORDER BY r.rolname) FROM pg_roles r WHERE rolname IN
   ('vn_contract_owner','vn_economic','vn_relay','vn_legacy_attestor')),
 'owner_memberships',(SELECT jsonb_agg(jsonb_build_array(pg_get_userbyid(m.member),pg_get_userbyid(m.roleid),
    m.grantor,m.admin_option,m.inherit_option,m.set_option) ORDER BY m.member,m.roleid,m.grantor)
    FROM pg_auth_members m WHERE m.member='vn_contract_owner'::regrole OR m.roleid='vn_contract_owner'::regrole),
 'defaults',(SELECT jsonb_agg(jsonb_build_array(pg_get_userbyid(d.defaclrole),n.nspname,d.defaclobjtype,d.defaclacl::text)
   ORDER BY d.defaclrole,n.nspname,d.defaclobjtype) FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
   WHERE d.defaclrole='vn_contract_owner'::regrole OR d.defaclnamespace IN (SELECT oid FROM namespaces))
)
$$;
