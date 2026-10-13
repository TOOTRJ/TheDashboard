-- Independent integer MT19937 equations and CPython 3.12 integer-seed/draw
-- convention. No copied C/Python implementation, entropy or database random().
-- Sources/reproducibility and resource limits are documented in the report.
DO $guard$ BEGIN
 IF current_setting('dashboard.portable_optimizer_rng_fixture',true) IS DISTINCT FROM 'offline-v2'
    OR to_regprocedure('vn_portable_optimizer_research.graph(jsonb)') IS NULL THEN
  RAISE EXCEPTION 'offline_portable_optimizer_rng_fixture_required' USING ERRCODE='22023';
 END IF;
END $guard$;

CREATE FUNCTION vn_portable_optimizer_research.mt_seed(seed numeric) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE words bigint[]:=array_fill(0::bigint,ARRAY[624]); keys bigint[]:=ARRAY[]::bigint[];
 n numeric:=abs(seed); i integer; j integer:=1; cursor integer:=2; mixed bigint;
BEGIN
 IF seed IS NULL OR trunc(seed)<>seed OR n>=power(2::numeric,256) THEN
  RAISE EXCEPTION 'optimizer_seed_capacity' USING ERRCODE='22023'; END IF;
 LOOP keys:=array_append(keys,mod(n,4294967296)::bigint); n:=div(n,4294967296); EXIT WHEN n=0; END LOOP;
 words[1]:=19650218;
 FOR i IN 2..624 LOOP words[i]:=(1812433253*(words[i-1] # (words[i-1]>>30))+(i-1)) & 4294967295; END LOOP;
 FOR i IN 1..624 LOOP
  mixed:=((words[cursor-1] # (words[cursor-1]>>30))*1664525) & 4294967295;
  words[cursor]:=((words[cursor] # mixed)+keys[j]+(j-1)) & 4294967295;
  cursor:=cursor+1; j:=j+1;
  IF cursor=625 THEN words[1]:=words[624]; cursor:=2; END IF;
  IF j>cardinality(keys) THEN j:=1; END IF;
 END LOOP;
 FOR i IN 1..623 LOOP
  mixed:=((words[cursor-1] # (words[cursor-1]>>30))*1566083941) & 4294967295;
  words[cursor]:=((words[cursor] # mixed)-(cursor-1)) & 4294967295;
  cursor:=cursor+1; IF cursor=625 THEN words[1]:=words[624]; cursor:=2; END IF;
 END LOOP;
 words[1]:=2147483648;
 RETURN jsonb_build_object('words',to_jsonb(words),'index',624,'draws',0);
END $function$;

CREATE FUNCTION vn_portable_optimizer_research.namespaced(seed text,namespace text,epoch bigint,indices jsonb DEFAULT '[]') RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE payload text; digest bytea; n numeric:=0; i integer; entry jsonb;
BEGIN
 IF seed IS NULL OR seed !~ '^(0|[1-9][0-9]{0,19})$' OR seed::numeric>18446744073709551615
    OR namespace NOT IN ('strategy','gen0','mutation') OR epoch IS NULL OR epoch<0 OR epoch>2147483647
    OR jsonb_typeof(indices) IS DISTINCT FROM 'array' OR jsonb_array_length(indices)>3 THEN
  RAISE EXCEPTION 'optimizer_namespace' USING ERRCODE='22023'; END IF;
 payload:='["sha256-namespaced-search-v1",'||to_json(seed)::text||','||
  to_json(CASE WHEN namespace='gen0' THEN '' ELSE 'genetic_algorithm' END)::text||','||to_json(namespace)::text||','||epoch::text;
 FOR entry IN SELECT v FROM jsonb_array_elements(indices) a(v) LOOP
  IF jsonb_typeof(entry)='string' AND entry='"generation"'::jsonb THEN payload:=payload||','||entry::text;
  ELSE payload:=payload||','||vn_portable_dependency_research.counter(entry,0,2147483647)::text; END IF;
 END LOOP;
 digest:=sha256(convert_to(payload||']','UTF8'));
 FOR i IN 0..31 LOOP n:=n*256+get_byte(digest,i); END LOOP;
 RETURN vn_portable_optimizer_research.mt_seed(n);
END $function$;

CREATE FUNCTION vn_portable_optimizer_research.mt_next(state jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE words bigint[]; cursor integer:=(state->>'index')::integer; i integer; v bigint; mix bigint; count integer:=(state->>'draws')::integer;
BEGIN
 IF count>=2048 THEN RAISE EXCEPTION 'optimizer_draw_capacity' USING ERRCODE='22023'; END IF;
 SELECT array_agg(a.v::text::bigint ORDER BY a.ordinal) INTO words FROM jsonb_array_elements(state->'words') WITH ORDINALITY a(v,ordinal);
 IF cardinality(words)<>624 OR cursor<0 OR cursor>624 THEN RAISE EXCEPTION 'optimizer_internal_rng' USING ERRCODE='22023'; END IF;
 IF cursor=624 THEN
  FOR i IN 1..624 LOOP
   v:=(words[i]&2147483648) | (words[CASE WHEN i=624 THEN 1 ELSE i+1 END]&2147483647);
   mix:=CASE WHEN (v&1)=1 THEN 2567483615 ELSE 0 END;
   words[i]:=words[CASE WHEN i<=227 THEN i+397 ELSE i-227 END] # (v>>1) # mix;
  END LOOP;
  cursor:=0;
 END IF;
 v:=words[cursor+1]; v:=v # (v>>11); v:=v # ((v<<7)&2636928640); v:=v # ((v<<15)&4022730752); v:=v # (v>>18);
 RETURN jsonb_build_object('words',to_jsonb(words),'index',cursor+1,'draws',count+1,'value',v);
END $function$;

CREATE FUNCTION vn_portable_optimizer_research.mt_random(state jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE a bigint;
BEGIN
 state:=vn_portable_optimizer_research.mt_next(state); a:=(state->>'value')::bigint>>5;
 state:=vn_portable_optimizer_research.mt_next(state);
 RETURN state||jsonb_build_object('numerator',a*67108864+((state->>'value')::bigint>>6));
END $function$;

CREATE FUNCTION vn_portable_optimizer_research.randbelow(state jsonb,n integer) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE bits integer:=1; i integer; v bigint;
BEGIN
 IF n IS NULL OR n<1 OR n>64 THEN RAISE EXCEPTION 'optimizer_sample_bound' USING ERRCODE='22023'; END IF;
 WHILE (1::bigint<<bits)<=n LOOP bits:=bits+1; END LOOP;
 FOR i IN 1..256 LOOP
  state:=vn_portable_optimizer_research.mt_next(state); v:=(state->>'value')::bigint>>(32-bits);
  IF v<n THEN RETURN state||jsonb_build_object('choice',v); END IF;
 END LOOP;
 RAISE EXCEPTION 'optimizer_rejection_capacity' USING ERRCODE='22023';
END $function$;

CREATE FUNCTION vn_portable_optimizer_research.sample(state jsonb,pool jsonb,k integer) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE n integer:=jsonb_array_length(pool); result jsonb:='[]'; i integer; choice integer;
BEGIN
 IF k<0 OR k>n OR n>8 THEN RAISE EXCEPTION 'optimizer_pool_capacity' USING ERRCODE='22023'; END IF;
 IF k>0 THEN FOR i IN 0..k-1 LOOP
  state:=vn_portable_optimizer_research.randbelow(state,n-i); choice:=(state->>'choice')::integer;
  result:=result||jsonb_build_array(pool->choice); pool:=jsonb_set(pool,ARRAY[choice::text],pool->(n-i-1));
 END LOOP; END IF;
 RETURN state||jsonb_build_object('sample',result);
END $function$;

CREATE FUNCTION vn_portable_optimizer_research.rng(graph jsonb,pointer jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE body jsonb:=vn_portable_optimizer_research.node(graph,pointer,'python.Random'); words jsonb;
BEGIN
 SELECT jsonb_agg(to_jsonb(vn_portable_dependency_research.counter(v,0,4294967295)) ORDER BY ordinal) INTO words
 FROM jsonb_array_elements(body->'words') WITH ORDINALITY a(v,ordinal);
 RETURN jsonb_build_object('words',words,'index',vn_portable_dependency_research.counter(body->'index',0,624),'draws',0);
END $function$;

CREATE FUNCTION vn_portable_optimizer_research.same_rng(left_state jsonb,right_state jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
 SELECT left_state->'words'=right_state->'words' AND left_state->'index'=right_state->'index'
$function$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_portable_optimizer_research FROM PUBLIC;
