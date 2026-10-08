-- Session-local, read-only review capture. Supply reviewed values in a later,
-- bounded mutation session; never capture and approve within that session.
CREATE TEMP TABLE dashboard_forward_review (review jsonb NOT NULL);
CREATE FUNCTION pg_temp.vn_forward_migrations() RETURNS jsonb LANGUAGE sql STABLE
SET search_path=pg_catalog,pg_temp AS $$
 SELECT coalesce(jsonb_agg(jsonb_build_object('version',version,'name',name,
   'statements_sha256',encode(sha256(convert_to(coalesce(array_to_json(statements)::text,'null'),'UTF8')),'hex'))
   ORDER BY version),'[]'::jsonb) FROM supabase_migrations.schema_migrations
$$;
