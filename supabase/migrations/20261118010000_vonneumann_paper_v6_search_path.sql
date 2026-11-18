-- Forward hardening of the exact installed Dashboard paper RPC.
-- Explicit pg_temp last prevents implicit temporary type/relation precedence
-- inside SECURITY DEFINER. This changes no body, privileges, rows or credentials.
BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;
DO $paper_hardening$
DECLARE
 target pg_catalog.oid := pg_catalog.to_regprocedure('vn_paper_v6.rpc(pg_catalog.text,pg_catalog.jsonb)');
 actual_body_sha pg_catalog.text;
 actual_config pg_catalog.text[];
 exact_owner pg_catalog.bool;
 exact_function pg_catalog.bool;
BEGIN
 IF target IS NULL THEN
  RAISE EXCEPTION 'paper_search_path_original_missing' USING ERRCODE='55000';
 END IF;
 SELECT pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p.prosrc,'UTF8')),'hex'),
        p.proconfig,
        o.rolname='postgres' AND p.proowner=n.nspowner,
        p.prosecdef AND NOT p.proretset AND l.lanname='plpgsql'
          AND p.prorettype='pg_catalog.jsonb'::pg_catalog.regtype
 INTO actual_body_sha, actual_config, exact_owner, exact_function
 FROM pg_catalog.pg_proc p
 JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
 JOIN pg_catalog.pg_roles o ON o.oid=p.proowner
 JOIN pg_catalog.pg_language l ON l.oid=p.prolang
 WHERE p.oid=target AND n.nspname='vn_paper_v6' AND p.proname='rpc';
 IF actual_body_sha IS DISTINCT FROM 'df41d6fb3180ed6e5318f67f2aab9cc167b410e550d00f547110a3f04fd93809'
    OR exact_owner IS DISTINCT FROM true OR exact_function IS DISTINCT FROM true
    OR (actual_config IS DISTINCT FROM ARRAY['search_path=pg_catalog']::pg_catalog.text[]
        AND actual_config IS DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp']::pg_catalog.text[]) THEN
  RAISE EXCEPTION 'paper_search_path_original_mismatch' USING ERRCODE='55000';
 END IF;
 ALTER FUNCTION vn_paper_v6.rpc(pg_catalog.text,pg_catalog.jsonb)
  SET search_path = pg_catalog, pg_temp;
 IF (SELECT proconfig FROM pg_catalog.pg_proc WHERE oid=target)
    IS DISTINCT FROM ARRAY['search_path=pg_catalog, pg_temp']::pg_catalog.text[] THEN
  RAISE EXCEPTION 'paper_search_path_postcondition_failed' USING ERRCODE='55000';
 END IF;
END $paper_hardening$;
COMMIT;
