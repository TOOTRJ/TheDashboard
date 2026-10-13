-- Independently derived integer-only proposal. No native/model integration.
DO $guard$ BEGIN
 IF current_setting('dashboard.portable_model_period_fixture',true) IS DISTINCT FROM 'offline-v2'
    OR to_regprocedure('vn_portable_optimizer_research.namespaced(text,text,bigint,jsonb)') IS NULL THEN
  RAISE EXCEPTION 'offline_portable_model_period_fixture_required' USING ERRCODE='22023'; END IF;
END $guard$;
CREATE FUNCTION vn_portable_optimizer_research.portable_periods(fast integer,slow integer,seed text,epoch bigint,event bigint,child integer,sexual boolean) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE state jsonb; rate bigint; i integer; original integer; following integer; radius integer; lo integer; hi integer;
 left_draw integer; right_draw integer; delta integer; mutated boolean; uniform_n numeric; trace jsonb:='[]'; result integer[]:=ARRAY[]::integer[];
BEGIN
 IF fast IS NULL OR fast<3 OR fast>12 OR slow IS NULL OR slow<15 OR slow>60 OR epoch IS NULL OR epoch<0 OR epoch>2147483647
    OR event IS NULL OR event<0 OR event>2147483647 OR child IS NULL OR child<0 OR child>7 OR sexual IS NULL THEN
  RAISE EXCEPTION 'portable_period_input' USING ERRCODE='22023'; END IF;
 state:=vn_portable_optimizer_research.namespaced(seed,'mutation',epoch,jsonb_build_array('generation',vn_portable_source_research.tag(event),vn_portable_source_research.tag(child)));
 rate:=CASE WHEN sexual THEN 200000 ELSE 300000 END;
 FOR i IN 0..1 LOOP
  original:=CASE WHEN i=0 THEN fast ELSE slow END; lo:=CASE WHEN i=0 THEN 3 ELSE 15 END;
  hi:=CASE WHEN i=0 THEN 12 ELSE 60 END; radius:=CASE WHEN i=0 THEN 3 ELSE 15 END;
  state:=vn_portable_optimizer_research.mt_random(state); uniform_n:=(state->>'numerator')::numeric;
  mutated:=uniform_n*1000000<rate::numeric*9007199254740992;
  left_draw:=NULL;right_draw:=NULL;delta:=0;
  IF mutated THEN
   state:=vn_portable_optimizer_research.randbelow(state,radius+1);left_draw:=(state->>'choice')::integer;
   state:=vn_portable_optimizer_research.randbelow(state,radius+1);right_draw:=(state->>'choice')::integer;delta:=left_draw-right_draw;
  END IF;
  following:=least(hi,greatest(lo,original+delta));result:=array_append(result,following);
  trace:=trace||jsonb_build_array(jsonb_build_object('gene',CASE WHEN i=0 THEN 'ema_fast' ELSE 'ema_slow' END,
   'uniform_numerator',vn_portable_source_research.tag(uniform_n),'mutated',mutated,
   'left',CASE WHEN left_draw IS NULL THEN 'null'::jsonb ELSE vn_portable_source_research.tag(left_draw) END,
   'right',CASE WHEN right_draw IS NULL THEN 'null'::jsonb ELSE vn_portable_source_research.tag(right_draw) END,
   'delta',vn_portable_source_research.tag(delta),'before',vn_portable_source_research.tag(original),'after',vn_portable_source_research.tag(following)));
 END LOOP;
 RETURN jsonb_build_object('operator','ema-period-triangular-integer-v1','ema_fast',vn_portable_source_research.tag(result[1]),
  'ema_slow',vn_portable_source_research.tag(result[2]),'rate_per_million',vn_portable_source_research.tag(rate),'draws',vn_portable_source_research.tag((state->>'draws')::integer),
  'trace',trace,'model_integration',true,'restoration_authority',false);
END $function$;
REVOKE ALL ON FUNCTION vn_portable_optimizer_research.portable_periods(integer,integer,text,bigint,bigint,integer,boolean) FROM PUBLIC;
