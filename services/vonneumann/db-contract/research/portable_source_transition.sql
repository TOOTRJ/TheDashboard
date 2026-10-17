-- Independent offline source/indicator proof. No production migration or effects.
DO $guard$ BEGIN
 IF current_setting('dashboard.portable_source_transition_fixture',true) IS DISTINCT FROM 'offline-v2'
    OR to_regprocedure('vn_portable_economic_research.transition(jsonb,jsonb,jsonb)') IS NULL
    OR current_setting('server_encoding')<>'UTF8'
    OR current_setting('standard_conforming_strings')<>'on' THEN
  RAISE EXCEPTION 'offline_portable_source_transition_fixture_required' USING ERRCODE='22023';
 END IF;
END $guard$;
CREATE SCHEMA vn_portable_source_research;
REVOKE ALL ON SCHEMA vn_portable_source_research FROM PUBLIC;

CREATE FUNCTION vn_portable_source_research.tag(value numeric) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
 SELECT jsonb_build_object('$integer',trunc(value)::text)
$function$;

-- Exact rational representation of the canonical binary64 tag. No decimal float cast.
CREATE FUNCTION vn_portable_source_research.ratio(value jsonb) RETURNS numeric[]
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE raw text; digits text; mantissa numeric:=0; exponent integer; numerator numeric; denominator numeric:=1;
BEGIN
 IF jsonb_typeof(value)='string' THEN raw:=value#>>'{}';
 ELSE PERFORM vn_portable_dependency_research.exact_keys(value,ARRAY['$binary64']); raw:=value->>'$binary64'; END IF;
 PERFORM vn_portable_numeric_research.binary64(raw);
 IF raw IN ('0x0.0p+0','-0x0.0p+0') THEN RETURN ARRAY[0::numeric,1::numeric]; END IF;
 digits:=replace(substring(split_part(ltrim(raw,'-'),'p',1),3),'.','');
 exponent:=split_part(raw,'p',2)::integer-4*length(split_part(split_part(raw,'p',1),'.',2));
 FOR i IN 1..length(digits) LOOP mantissa:=mantissa*16+strpos('0123456789abcdef',substring(digits,i,1))-1; END LOOP;
 numerator:=mantissa;
 IF exponent>=0 THEN numerator:=numerator*power(2::numeric,exponent);
 ELSE denominator:=power(2::numeric,-exponent); END IF;
 IF left(raw,1)='-' THEN numerator:=-numerator; END IF;
 RETURN ARRAY[numerator,denominator];
END $function$;

-- Independently round an integer ratio to nearest, ties to even, at each Python
-- operation boundary. This avoids PostgreSQL numeric's different tie policy.
CREATE FUNCTION vn_portable_source_research.round_ratio(numerator numeric,denominator numeric) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE n numeric:=abs(numerator); d numeric:=denominator; low integer:=-1075; high integer:=1024;
 middle integer; exponent integer; shift integer; scaled numeric; divisor numeric; k numeric; remainder numeric;
 sign text:=CASE WHEN numerator<0 THEN '-' ELSE '' END; fraction text; raw text;
BEGIN
 IF numerator IS NULL OR denominator IS NULL OR numerator<>trunc(numerator) OR denominator<>trunc(denominator)
    OR denominator<=0 OR n>1e1300 OR d>1e1300 THEN
  RAISE EXCEPTION 'source_invalid_ratio' USING ERRCODE='22023';
 END IF;
 IF n=0 THEN RETURN jsonb_build_object('$binary64','0x0.0p+0'); END IF;
 IF n>=d*power(2::numeric,1024) THEN
  RAISE EXCEPTION 'source_binary64_overflow' USING ERRCODE='22023';
 END IF;
 WHILE high-low>1 LOOP
  middle:=div(low+high,2)::integer;
  IF (CASE WHEN middle>=0 THEN n>=d*power(2::numeric,middle)
          ELSE n*power(2::numeric,-middle)>=d END) THEN low:=middle; ELSE high:=middle; END IF;
 END LOOP;
 exponent:=low;
 IF exponent>1023 THEN RAISE EXCEPTION 'source_binary64_overflow' USING ERRCODE='22023'; END IF;
 shift:=CASE WHEN exponent< -1022 THEN 1074 ELSE 52-exponent END;
 scaled:=n; divisor:=d;
 IF shift>=0 THEN scaled:=scaled*power(2::numeric,shift); ELSE divisor:=divisor*power(2::numeric,-shift); END IF;
 k:=div(scaled,divisor); remainder:=mod(scaled,divisor);
 IF remainder*2>divisor OR (remainder*2=divisor AND mod(k,2)=1) THEN k:=k+1; END IF;
 IF k=0 THEN raw:=sign||'0x0.0p+0';
 ELSIF exponent< -1022 AND k<4503599627370496 THEN
  fraction:=right(encode(int8send(k::bigint),'hex'),13); raw:=sign||'0x0.'||fraction||'p-1022';
 ELSE
  exponent:=greatest(exponent,-1022);
  IF k=9007199254740992 THEN k:=4503599627370496; exponent:=exponent+1; END IF;
  IF exponent>1023 THEN RAISE EXCEPTION 'source_binary64_overflow' USING ERRCODE='22023'; END IF;
  fraction:=right(encode(int8send((k-4503599627370496)::bigint),'hex'),13);
  raw:=sign||'0x1.'||fraction||'p'||CASE WHEN exponent>=0 THEN '+' ELSE '' END||exponent::text;
 END IF;
 PERFORM vn_portable_numeric_research.binary64(raw);
 RETURN jsonb_build_object('$binary64',raw);
END $function$;

CREATE FUNCTION vn_portable_source_research.binary_operation(operation text,left_value jsonb,right_value jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE l numeric[]:=vn_portable_source_research.ratio(left_value); r numeric[]:=vn_portable_source_research.ratio(right_value); n numeric; d numeric;
 left_negative boolean:=left(coalesce(left_value->>'$binary64',left_value#>>'{}'),1)='-';
 right_negative boolean:=left(coalesce(right_value->>'$binary64',right_value#>>'{}'),1)='-';
BEGIN
 CASE operation
 WHEN 'add' THEN n:=l[1]*r[2]+r[1]*l[2]; d:=l[2]*r[2];
 WHEN 'subtract' THEN n:=l[1]*r[2]-r[1]*l[2]; d:=l[2]*r[2];
 WHEN 'multiply' THEN n:=l[1]*r[1]; d:=l[2]*r[2];
 WHEN 'divide' THEN n:=l[1]*r[2]; d:=l[2]*r[1];
 ELSE RAISE EXCEPTION 'source_invalid_binary_operation' USING ERRCODE='22023'; END CASE;
 IF n=0 AND d<>0 AND
    ((operation IN ('multiply','divide') AND left_negative IS DISTINCT FROM right_negative)
      OR (operation='add' AND l[1]=0 AND r[1]=0 AND left_negative AND right_negative)
      OR (operation='subtract' AND l[1]=0 AND r[1]=0 AND left_negative AND NOT right_negative)) THEN
  RETURN jsonb_build_object('$binary64','-0x0.0p+0');
 END IF;
 IF d<0 THEN d:=-d; n:=-n; END IF;
 RETURN vn_portable_source_research.round_ratio(n,d);
END $function$;

CREATE FUNCTION vn_portable_source_research.clock(value jsonb) RETURNS numeric
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
 SELECT vn_portable_dependency_research.counter(value,0,10000000000000000)
$function$;

CREATE FUNCTION vn_portable_source_research.block(value jsonb) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE result numeric;
BEGIN
 PERFORM vn_portable_dependency_research.exact_keys(value,ARRAY['$integer']);
 IF jsonb_typeof(value->'$integer') IS DISTINCT FROM 'string' THEN
  RAISE EXCEPTION 'source_invalid_block' USING ERRCODE='22023'; END IF;
 result:=vn_portable_numeric_research.integer_text(value->>'$integer');
 IF result<0 OR result>18446744073709551615 THEN RAISE EXCEPTION 'source_invalid_block' USING ERRCODE='22023'; END IF;
 RETURN result;
END $function$;

CREATE FUNCTION vn_portable_source_research.price(value jsonb) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE result numeric:=vn_portable_economic_research.units(value,18);
BEGIN
 IF result<=0 THEN RAISE EXCEPTION 'source_invalid_price' USING ERRCODE='22023'; END IF;
 RETURN result;
END $function$;

CREATE FUNCTION vn_portable_source_research.mint(value text) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE alphabet text:='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'; n numeric:=0; zeroes integer:=0; bytes integer:=0;
BEGIN
 IF value IS NULL OR value !~ '^[1-9A-HJ-NP-Za-km-z]{32,44}$' THEN RAISE EXCEPTION 'source_invalid_mint' USING ERRCODE='22023'; END IF;
 FOR i IN 1..length(value) LOOP n:=n*58+strpos(alphabet,substring(value,i,1))-1; END LOOP;
 WHILE zeroes<length(value) AND substring(value,zeroes+1,1)='1' LOOP zeroes:=zeroes+1; END LOOP;
 WHILE n>0 LOOP n:=div(n,256); bytes:=bytes+1; END LOOP;
 IF bytes+zeroes<>32 THEN RAISE EXCEPTION 'source_invalid_mint' USING ERRCODE='22023'; END IF;
END $function$;

CREATE FUNCTION vn_portable_source_research.document(value jsonb,provider text) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE request jsonb:=value->'request'; params jsonb:=request->'parameters'; mints text[]; m text;
 lower_time numeric; upper_time numeric; canonical text; parameter_text text;
BEGIN
 PERFORM vn_portable_dependency_research.exact_keys(value,ARRAY['provider','parser_policy','request','request_sha256','response_sha256','response_bytes','received_wall_us','received_monotonic_us']);
 IF value->>'provider' IS DISTINCT FROM provider OR value->>'parser_policy' IS DISTINCT FROM 'provider-json-exact-v1'
    OR jsonb_typeof(value->'request_sha256') IS DISTINCT FROM 'string' OR value->>'request_sha256' !~ '^[a-f0-9]{64}$'
    OR jsonb_typeof(value->'response_sha256') IS DISTINCT FROM 'string' OR value->>'response_sha256' !~ '^[a-f0-9]{64}$' THEN
  RAISE EXCEPTION 'source_invalid_document' USING ERRCODE='22023'; END IF;
 PERFORM vn_portable_source_research.clock(value->'received_wall_us'); PERFORM vn_portable_source_research.clock(value->'received_monotonic_us');
 PERFORM vn_portable_dependency_research.counter(value->'response_bytes',1,CASE WHEN provider='jupiter-price-v3' THEN 131072 ELSE 4194304 END);
 PERFORM vn_portable_dependency_research.exact_keys(request,ARRAY['method','endpoint','chain','parameters']);
 IF request->>'method' IS DISTINCT FROM 'GET' OR request->>'chain' IS DISTINCT FROM 'solana' THEN
  RAISE EXCEPTION 'source_invalid_request' USING ERRCODE='22023'; END IF;
 IF provider='jupiter-price-v3' THEN
  PERFORM vn_portable_dependency_research.exact_keys(params,ARRAY['ids']);
  IF request->>'endpoint' IS DISTINCT FROM 'https://api.jup.ag/price/v3' OR jsonb_typeof(params->'ids') IS DISTINCT FROM 'string'
     OR length(params->>'ids')>2250 THEN RAISE EXCEPTION 'source_invalid_request' USING ERRCODE='22023'; END IF;
  mints:=string_to_array(params->>'ids',',');
  IF cardinality(mints) NOT BETWEEN 1 AND 50 OR NOT 'So11111111111111111111111111111111111111112'=ANY(mints)
     OR (SELECT count(DISTINCT x) FROM unnest(mints) a(x))<>cardinality(mints) THEN
   RAISE EXCEPTION 'source_invalid_request' USING ERRCODE='22023'; END IF;
  FOREACH m IN ARRAY mints LOOP PERFORM vn_portable_source_research.mint(m); END LOOP;
  parameter_text:='{"ids":'||(params->'ids')::text||'}';
 ELSIF provider='birdeye-ohlcv-v3' THEN
  PERFORM vn_portable_dependency_research.exact_keys(params,ARRAY['address','type','mode','time_from','time_to','currency','chart_type','ui_amount_mode','padding']);
  IF request->>'endpoint' IS DISTINCT FROM 'https://public-api.birdeye.so/defi/v3/ohlcv'
     OR params-ARRAY['time_from','time_to'] IS DISTINCT FROM '{"address":"So11111111111111111111111111111111111111112","type":"1m","mode":"range","currency":"usd","chart_type":"price","ui_amount_mode":"raw","padding":"false"}'::jsonb THEN
   RAISE EXCEPTION 'source_invalid_request' USING ERRCODE='22023'; END IF;
  lower_time:=vn_portable_dependency_research.counter(params->'time_from',0,10000000000);
  upper_time:=vn_portable_dependency_research.counter(params->'time_to',0,10000000000);
  IF mod(lower_time,60)<>0 OR mod(upper_time,60)<>0 OR upper_time<=lower_time OR upper_time-lower_time>299940 THEN
   RAISE EXCEPTION 'source_invalid_request' USING ERRCODE='22023'; END IF;
  parameter_text:='{"address":"So11111111111111111111111111111111111111112","chart_type":"price","currency":"usd","mode":"range","padding":"false","time_from":'||lower_time::text||',"time_to":'||upper_time::text||',"type":"1m","ui_amount_mode":"raw"}';
 ELSE RAISE EXCEPTION 'source_invalid_provider' USING ERRCODE='22023'; END IF;
 canonical:='{"chain":"solana","endpoint":'||(request->'endpoint')::text||',"method":"GET","parameters":'||parameter_text||'}';
 IF encode(sha256(convert_to(canonical,'UTF8')),'hex') IS DISTINCT FROM value->>'request_sha256' THEN
  RAISE EXCEPTION 'source_request_hash_mismatch' USING ERRCODE='22023'; END IF;
END $function$;

CREATE FUNCTION vn_portable_source_research.receipt(doc jsonb,wall numeric,mono numeric) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE w numeric:=vn_portable_source_research.clock(doc->'received_wall_us'); m numeric:=vn_portable_source_research.clock(doc->'received_monotonic_us');
BEGIN
 IF wall<w OR mono<m OR greatest(wall-w,mono-m)>=5000000 THEN
  RAISE EXCEPTION 'source_receipt_expired' USING ERRCODE='22023'; END IF;
END $function$;

CREATE FUNCTION vn_portable_source_research.frame(value jsonb,wall numeric,mono numeric) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE q jsonb:=value->'quote'; doc jsonb:=q->'document'; at numeric; w numeric; m numeric; stamp numeric; initial_age numeric;
BEGIN
 PERFORM vn_portable_dependency_research.exact_keys(value,ARRAY['sequence','decision_second','decision_wall_us','decision_monotonic_us','quote']);
 PERFORM vn_portable_dependency_research.counter(value->'sequence',1,9223372036854775806);
 at:=vn_portable_dependency_research.counter(value->'decision_second',0,10000000000);
 w:=vn_portable_source_research.clock(value->'decision_wall_us'); m:=vn_portable_source_research.clock(value->'decision_monotonic_us');
 PERFORM vn_portable_dependency_research.exact_keys(q,ARRAY['price','block_ref','estimated_source_second','source_age_floor_us','document']);
 PERFORM vn_portable_source_research.price(q->'price'); PERFORM vn_portable_source_research.block(q->'block_ref');
 stamp:=vn_portable_dependency_research.counter(q->'estimated_source_second',0,10000000000)*1000000;
 PERFORM vn_portable_source_research.clock(q->'source_age_floor_us'); PERFORM vn_portable_source_research.document(doc,'jupiter-price-v3');
 IF w<at*1000000 OR w>(at+1)*1000000 OR at<div(vn_portable_source_research.clock(doc->'received_wall_us')+999999,1000000)
    OR wall<w OR mono<m THEN RAISE EXCEPTION 'source_frame_clock_mismatch' USING ERRCODE='22023'; END IF;
 PERFORM vn_portable_source_research.receipt(doc,wall,mono);
 initial_age:=greatest(0,vn_portable_source_research.clock(doc->'received_wall_us')-stamp,vn_portable_source_research.clock(q->'source_age_floor_us'));
 IF stamp-wall>2000000 OR stamp-vn_portable_source_research.clock(doc->'received_wall_us')>2000000
    OR greatest(wall-stamp,initial_age+mono-vn_portable_source_research.clock(doc->'received_monotonic_us'))>30000000 THEN
  RAISE EXCEPTION 'source_quote_stale' USING ERRCODE='22023'; END IF;
END $function$;

CREATE FUNCTION vn_portable_source_research.bars(value jsonb) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE row jsonb; stamp numeric; previous numeric;
BEGIN
 IF jsonb_typeof(value) IS DISTINCT FROM 'array' OR jsonb_array_length(value) NOT BETWEEN 61 AND 64 THEN
  RAISE EXCEPTION 'source_invalid_bars' USING ERRCODE='22023'; END IF;
 FOR row IN SELECT v FROM jsonb_array_elements(value) a(v) LOOP
  IF jsonb_typeof(row) IS DISTINCT FROM 'array' OR jsonb_array_length(row)<>3 THEN RAISE EXCEPTION 'source_invalid_bar' USING ERRCODE='22023'; END IF;
  stamp:=vn_portable_dependency_research.counter(row->0,900,10000000000); PERFORM vn_portable_source_research.price(row->1);
  IF mod(stamp,900)<>0 OR (previous IS NOT NULL AND stamp<>previous+900)
     OR jsonb_typeof(row->2) IS DISTINCT FROM 'string' OR row->>2 !~ '^[a-f0-9]{64}$' THEN
   RAISE EXCEPTION 'source_invalid_bar' USING ERRCODE='22023'; END IF;
  previous:=stamp;
 END LOOP;
END $function$;

CREATE FUNCTION vn_portable_source_research.history(value jsonb,old_bars jsonb,seed boolean,wall numeric,mono numeric) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE docs jsonb:=value->'documents'; minutes jsonb:=value->'minutes'; doc jsonb; old_doc jsonb; row jsonb;
 index integer; used integer[]:=ARRAY[]::integer[]; stamp numeric; previous numeric; ending numeric; ordinal integer:=0;
 pairs text:=''; result jsonb:='[]';
BEGIN
 PERFORM vn_portable_dependency_research.exact_keys(value,ARRAY['documents','minutes','unscaled']);
 IF value->'unscaled' IS DISTINCT FROM 'true'::jsonb OR jsonb_typeof(docs) IS DISTINCT FROM 'array'
    OR jsonb_array_length(docs) NOT BETWEEN 1 AND 4 OR jsonb_typeof(minutes) IS DISTINCT FROM 'array'
    OR jsonb_array_length(minutes)<>(CASE WHEN seed THEN 915 ELSE 15 END) THEN
  RAISE EXCEPTION 'source_invalid_history' USING ERRCODE='22023'; END IF;
 FOR doc IN SELECT v FROM jsonb_array_elements(docs) a(v) LOOP
  PERFORM vn_portable_source_research.document(doc,'birdeye-ohlcv-v3'); PERFORM vn_portable_source_research.receipt(doc,wall,mono);
  IF old_doc IS NOT NULL AND ROW(doc->>'response_sha256',doc->>'request_sha256',vn_portable_source_research.clock(doc->'received_wall_us'),vn_portable_source_research.clock(doc->'received_monotonic_us'))
      <=ROW(old_doc->>'response_sha256',old_doc->>'request_sha256',vn_portable_source_research.clock(old_doc->'received_wall_us'),vn_portable_source_research.clock(old_doc->'received_monotonic_us')) THEN
   RAISE EXCEPTION 'source_document_order' USING ERRCODE='22023'; END IF;
  old_doc:=doc;
 END LOOP;
 FOR row IN SELECT v FROM jsonb_array_elements(minutes) a(v) LOOP
  IF jsonb_typeof(row) IS DISTINCT FROM 'array' OR jsonb_array_length(row)<>3 THEN RAISE EXCEPTION 'source_invalid_minute' USING ERRCODE='22023'; END IF;
  stamp:=vn_portable_dependency_research.counter(row->0,60,9999999940);
  index:=vn_portable_dependency_research.counter(row->2,0,jsonb_array_length(docs)-1)::integer; doc:=docs->index;
  PERFORM vn_portable_source_research.price(row->1);
  IF mod(stamp,60)<>0 OR (previous IS NULL AND mod(stamp,900)<>0) OR (previous IS NOT NULL AND stamp<>previous+60)
     OR stamp<vn_portable_dependency_research.counter(doc#>'{request,parameters,time_from}',0,10000000000)
     OR stamp+60>vn_portable_dependency_research.counter(doc#>'{request,parameters,time_to}',0,10000000000) THEN
   RAISE EXCEPTION 'source_minute_binding' USING ERRCODE='22023'; END IF;
  ending:=(div(stamp,900)+1)*900;
  IF ending*1000000+5000000>wall OR ending*1000000+5000000>vn_portable_source_research.clock(doc->'received_wall_us') THEN
   RAISE EXCEPTION 'source_candle_incomplete' USING ERRCODE='22023'; END IF;
  IF NOT index=ANY(used) THEN used:=array_append(used,index); END IF;
  pairs:=pairs||CASE WHEN mod(ordinal,15)=0 THEN '' ELSE ',' END||'['||stamp::text||','||(row->1)::text||']';
  ordinal:=ordinal+1; previous:=stamp;
  IF mod(ordinal,15)=0 THEN
   result:=result||jsonb_build_array(jsonb_build_array(vn_portable_source_research.tag(stamp+60),row->1,
      encode(sha256(convert_to('['||pairs||']','UTF8')),'hex'))); pairs:='';
  END IF;
 END LOOP;
 IF cardinality(used)<>jsonb_array_length(docs) OR previous+60<>floor((wall-5000000)/900000000)*900
    OR (NOT seed AND vn_portable_dependency_research.counter(result#>'{0,0}',900,10000000000)<>vn_portable_dependency_research.counter(old_bars#>'{-1,0}',900,10000000000)+900) THEN
  RAISE EXCEPTION 'source_history_cursor' USING ERRCODE='22023'; END IF;
 RETURN result;
END $function$;

CREATE FUNCTION vn_portable_source_research.indicators(previous jsonb,bars jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE result jsonb:=coalesce(previous,'{"count":{"$integer":"0"},"last_end":null,"closes":[],"values":{},"previous":{}}'::jsonb);
 row jsonb; closes jsonb; values jsonb; key text; count bigint; price jsonb; old jsonb; next jsonb; alpha jsonb;
 seed_window jsonb; item jsonb; ratio numeric[]; scale_units numeric; scale_value jsonb; sum_units numeric;
 denominator numeric:=power(2::numeric,1074);
BEGIN
 FOR row IN SELECT v FROM jsonb_array_elements(bars) a(v) LOOP
  count:=vn_portable_dependency_research.counter(result->'count',0,9223372036854775805)::bigint+1;
  closes:=(result->'closes')||jsonb_build_array(row->1);
  SELECT jsonb_agg(v ORDER BY ordinal) INTO closes FROM jsonb_array_elements(closes) WITH ORDINALITY a(v,ordinal)
    WHERE ordinal>greatest(jsonb_array_length(closes)-64,0);
  values:=result->'values'; result:=jsonb_set(result,'{previous}',values);
  price:=vn_portable_source_research.round_ratio(vn_portable_source_research.price(row->1),1e18);
  FOR period IN 2..60 LOOP
   key:=period::text;
   IF count=period THEN
    SELECT jsonb_agg(v ORDER BY ordinal) INTO seed_window FROM jsonb_array_elements(closes) WITH ORDINALITY a(v,ordinal)
     WHERE ordinal>jsonb_array_length(closes)-period;
    SELECT max(vn_portable_source_research.price(v)) INTO scale_units FROM jsonb_array_elements(seed_window) a(v);
    scale_value:=vn_portable_source_research.round_ratio(scale_units,1e18); sum_units:=0;
    FOR item IN SELECT v FROM jsonb_array_elements(seed_window) a(v) LOOP
     ratio:=vn_portable_source_research.ratio(vn_portable_source_research.binary_operation('divide',
       vn_portable_source_research.round_ratio(vn_portable_source_research.price(item),1e18),scale_value));
     sum_units:=sum_units+ratio[1]*div(denominator,ratio[2]);
    END LOOP;
    next:=vn_portable_source_research.binary_operation('multiply',scale_value,
       vn_portable_source_research.binary_operation('divide',vn_portable_source_research.round_ratio(sum_units,denominator),
         vn_portable_source_research.round_ratio(period,1)));
   ELSIF count>period THEN
    old:=values->key;
    alpha:=vn_portable_source_research.round_ratio(2,period+1);
    next:=vn_portable_source_research.binary_operation('add',old,vn_portable_source_research.binary_operation('multiply',
       vn_portable_source_research.binary_operation('subtract',price,old),alpha));
   ELSE CONTINUE;
   END IF;
   ratio:=vn_portable_source_research.ratio(next);
   IF ratio[1]<=0 THEN RAISE EXCEPTION 'source_invalid_indicator' USING ERRCODE='22023'; END IF;
   values:=values||jsonb_build_object(key,next->>'$binary64');
  END LOOP;
  result:=result||jsonb_build_object('count',vn_portable_source_research.tag(count),'last_end',row->0,'closes',closes,'values',values);
 END LOOP;
 RETURN result;
END $function$;

CREATE FUNCTION vn_portable_source_research.state(value jsonb,epoch jsonb) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE source jsonb:=value->'source'; frame jsonb:=source->'last_quote'; ema jsonb:=value#>'{engine,ema}';
BEGIN
 PERFORM vn_portable_dependency_research.exact_keys(source,ARRAY['version','epoch','quote_sequence','last_quote','bars']);
 IF source->>'version' IS DISTINCT FROM 'ga-provider-source-research-v1' OR source->'epoch' IS DISTINCT FROM epoch THEN
  RAISE EXCEPTION 'source_epoch_mismatch' USING ERRCODE='22023'; END IF;
 PERFORM vn_portable_dependency_research.uuid_text(epoch); PERFORM vn_portable_source_research.bars(source->'bars');
 PERFORM vn_portable_dependency_research.counter(source->'quote_sequence',0,9223372036854775806);
 IF frame='null'::jsonb THEN
  IF source->'quote_sequence' IS DISTINCT FROM vn_portable_source_research.tag(0) OR value#>'{engine,last_quote}' IS DISTINCT FROM 'null'::jsonb THEN
   RAISE EXCEPTION 'source_quote_projection' USING ERRCODE='22023'; END IF;
 ELSE
  PERFORM vn_portable_source_research.frame(frame,vn_portable_source_research.clock(frame->'decision_wall_us'),vn_portable_source_research.clock(frame->'decision_monotonic_us'));
  IF source->'quote_sequence' IS DISTINCT FROM frame->'sequence' OR value#>'{engine,last_quote}' IS DISTINCT FROM
     jsonb_build_object('timestamp',frame->'decision_second','price',frame#>'{quote,price}') THEN
   RAISE EXCEPTION 'source_quote_projection' USING ERRCODE='22023'; END IF;
 END IF;
 PERFORM vn_portable_dependency_research.exact_keys(ema,ARRAY['count','last_end','closes','values','previous']);
 PERFORM vn_portable_dependency_research.counter(ema->'count',61,9223372036854775806);
 IF ema->'last_end' IS DISTINCT FROM source#>'{bars,-1,0}' OR ema->'closes' IS DISTINCT FROM
   (SELECT jsonb_agg(v->1 ORDER BY ordinal) FROM jsonb_array_elements(source->'bars') WITH ORDINALITY a(v,ordinal)) THEN
  RAISE EXCEPTION 'source_indicator_projection' USING ERRCODE='22023'; END IF;
END $function$;

CREATE FUNCTION vn_portable_source_research.transition(request jsonb,previous jsonb,following jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE evidence jsonb:=request->'evidence'; inputs jsonb:=evidence->'inputs'; provider jsonb:=inputs->'provider';
 phase text:=evidence->>'kind'; control text:=evidence#>>'{control,action}'; frame jsonb:=provider->'frame'; history jsonb:=provider->'history';
 source jsonb:=following->'source'; expected jsonb; additions jsonb:='[]'; bars jsonb; epoch jsonb:=following#>'{engine,config,source_policy,epoch}';
 wall numeric; mono numeric; at numeric; ratio numeric[]; last jsonb; q jsonb; oq jsonb; doc jsonb; odoc jsonb; carried numeric;
 event_time timestamptz; wall_time timestamptz; canonical_wall text;
 observation jsonb; config jsonb; row record;
BEGIN
 PERFORM vn_portable_dependency_research.exact_keys(provider,ARRAY['phase','frame','history','wall_us','monotonic_us']);
 IF provider->>'phase' IS DISTINCT FROM phase OR phase NOT IN ('bootstrap','protective','decision','control') THEN
  RAISE EXCEPTION 'source_phase_mismatch' USING ERRCODE='22023'; END IF;
 wall:=vn_portable_source_research.clock(provider->'wall_us'); mono:=vn_portable_source_research.clock(provider->'monotonic_us');
 IF jsonb_typeof(inputs->'wall_at') IS DISTINCT FROM 'string' OR inputs->>'wall_at' !~ '^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{6})?\+00:00$'
    OR jsonb_typeof(inputs->'monotonic_at') IS DISTINCT FROM 'string'
    OR jsonb_typeof(inputs->'event_at') IS DISTINCT FROM 'string' OR inputs->>'event_at' !~ '^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$' THEN
  RAISE EXCEPTION 'source_input_clock_shape' USING ERRCODE='22023'; END IF;
 event_time:=(inputs->>'event_at')::timestamptz; wall_time:=(inputs->>'wall_at')::timestamptz;
 canonical_wall:=to_char(wall_time AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS')||
   CASE WHEN mod(extract(microseconds FROM wall_time),1000000)=0 THEN ''
        ELSE '.'||to_char(wall_time AT TIME ZONE 'UTC','US') END||'+00:00';
 IF inputs->>'event_at' IS DISTINCT FROM to_char(event_time AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS')||'+00:00'
    OR inputs->>'wall_at' IS DISTINCT FROM canonical_wall THEN
  RAISE EXCEPTION 'source_input_clock_shape' USING ERRCODE='22023'; END IF;
 at:=extract(epoch FROM event_time);
 ratio:=vn_portable_source_research.ratio(inputs->'monotonic_at');
 IF ratio[1]<0 OR mono<>div(ratio[1]*1000000+ratio[2]-1,ratio[2])
    OR wall<>extract(epoch FROM wall_time)*1000000 THEN
  RAISE EXCEPTION 'source_input_clock_binding' USING ERRCODE='22023'; END IF;
 config:=following#>'{engine,config,source_policy}';
 PERFORM vn_portable_dependency_research.exact_keys(config,ARRAY['version','sequence_maximum','epoch','asset','mint','chain','denomination','valuation','source_time_policy','clock_policy','max_source_age_us','future_tolerance_us','max_receipt_age_us','candle_seconds','candle_completion_us','seed_bars','max_history_bars','source_order','evidence_trust','outlier_policy']);
 IF config-ARRAY['epoch','max_source_age_us','future_tolerance_us','max_receipt_age_us','candle_seconds','candle_completion_us','seed_bars','max_history_bars'] IS DISTINCT FROM
  '{"version":"ga-provider-source-research-v1","sequence_maximum":"9223372036854775806","asset":"SOL/USD","mint":"So11111111111111111111111111111111111111112","chain":"solana","denomination":"USD","valuation":"reference_mark","source_time_policy":"jupiter-block-id-as-slot-estimated-time-v1","clock_policy":"conservative-integer-microseconds-v1","source_order":"strict-block-ref-nondecreasing-estimate-v1","evidence_trust":"worker-parsed-records-and-manifests-v1","outlier_policy":"provider-default-omitted"}'::jsonb THEN
  RAISE EXCEPTION 'source_policy_mismatch' USING ERRCODE='22023'; END IF;
 FOR row IN SELECT * FROM (VALUES ('max_source_age_us',30000000),('future_tolerance_us',2000000),('max_receipt_age_us',5000000),('candle_seconds',900),('candle_completion_us',5000000),('seed_bars',61),('max_history_bars',64)) a(key,value) LOOP
  IF config->row.key IS DISTINCT FROM vn_portable_source_research.tag(row.value) THEN RAISE EXCEPTION 'source_policy_mismatch' USING ERRCODE='22023'; END IF;
 END LOOP;
 PERFORM vn_portable_source_research.state(following,epoch);
 IF previous IS NULL THEN
  IF phase<>'bootstrap' OR frame IS DISTINCT FROM 'null'::jsonb OR history IS NULL OR history='null'::jsonb
     OR wall<at*1000000 OR wall>(at+1)*1000000 THEN RAISE EXCEPTION 'source_bootstrap_mismatch' USING ERRCODE='22023'; END IF;
  additions:=vn_portable_source_research.history(history,'[]',true,wall,mono);
  expected:=jsonb_build_object('version','ga-provider-source-research-v1','epoch',epoch,
     'quote_sequence',vn_portable_source_research.tag(0),'last_quote',NULL,'bars',additions);
 ELSE
  PERFORM vn_portable_source_research.state(previous,epoch); expected:=previous->'source'; last:=expected->'last_quote';
  IF (last<>'null'::jsonb AND (phase<>'control' OR control='recover') AND
        (wall<vn_portable_source_research.clock(last->'decision_wall_us') OR mono<vn_portable_source_research.clock(last->'decision_monotonic_us')))
     OR (last<>'null'::jsonb AND at<vn_portable_dependency_research.counter(last->'decision_second',0,10000000000))
     OR (previous#>'{engine,lifecycle,last_control_at}'<>'null'::jsonb AND at<vn_portable_dependency_research.counter(previous#>'{engine,lifecycle,last_control_at}',0,10000000000)) THEN
   RAISE EXCEPTION 'source_clock_regressed' USING ERRCODE='22023'; END IF;
  IF phase='protective' THEN
   IF history IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'source_protective_history' USING ERRCODE='22023'; END IF;
   PERFORM vn_portable_source_research.frame(frame,wall,mono);
   IF vn_portable_dependency_research.counter(frame->'sequence',1,9223372036854775806)<>vn_portable_dependency_research.counter(expected->'quote_sequence',0,9223372036854775806)+1 THEN
    RAISE EXCEPTION 'source_sequence_mismatch' USING ERRCODE='22023'; END IF;
   IF last<>'null'::jsonb THEN
    q:=frame->'quote'; oq:=last->'quote'; doc:=q->'document'; odoc:=oq->'document';
    carried:=greatest(0,greatest(vn_portable_source_research.clock(doc->'received_wall_us')-vn_portable_dependency_research.counter(oq->'estimated_source_second',0,10000000000)*1000000,
      greatest(0,vn_portable_source_research.clock(odoc->'received_wall_us')-vn_portable_dependency_research.counter(oq->'estimated_source_second',0,10000000000)*1000000,vn_portable_source_research.clock(oq->'source_age_floor_us'))+
      vn_portable_source_research.clock(doc->'received_monotonic_us')-vn_portable_source_research.clock(odoc->'received_monotonic_us'))-
      (vn_portable_dependency_research.counter(q->'estimated_source_second',0,10000000000)-vn_portable_dependency_research.counter(oq->'estimated_source_second',0,10000000000))*1000000);
    IF vn_portable_dependency_research.counter(frame->'decision_second',0,10000000000)<=vn_portable_dependency_research.counter(last->'decision_second',0,10000000000)
       OR vn_portable_source_research.clock(frame->'decision_wall_us')<vn_portable_source_research.clock(last->'decision_wall_us')
       OR vn_portable_source_research.clock(frame->'decision_monotonic_us')<vn_portable_source_research.clock(last->'decision_monotonic_us')
       OR vn_portable_source_research.block(q->'block_ref')<=vn_portable_source_research.block(oq->'block_ref')
       OR vn_portable_dependency_research.counter(q->'estimated_source_second',0,10000000000)<vn_portable_dependency_research.counter(oq->'estimated_source_second',0,10000000000)
       OR vn_portable_source_research.clock(doc->'received_wall_us')<vn_portable_source_research.clock(odoc->'received_wall_us')
       OR vn_portable_source_research.clock(doc->'received_monotonic_us')<=vn_portable_source_research.clock(odoc->'received_monotonic_us')
       OR vn_portable_source_research.clock(q->'source_age_floor_us')<carried THEN
     RAISE EXCEPTION 'source_frame_continuation' USING ERRCODE='22023'; END IF;
   END IF;
   expected:=expected||jsonb_build_object('quote_sequence',frame->'sequence','last_quote',frame);
  ELSIF phase='decision' OR (phase='control' AND control='recover') THEN
   PERFORM vn_portable_source_research.frame(frame,wall,mono);
   IF frame IS DISTINCT FROM last THEN RAISE EXCEPTION 'source_accepted_frame_required' USING ERRCODE='22023'; END IF;
  ELSIF phase<>'control' OR frame IS DISTINCT FROM 'null'::jsonb OR history IS DISTINCT FROM 'null'::jsonb
     OR wall<at*1000000 OR wall>(at+1)*1000000 THEN
   RAISE EXCEPTION 'source_control_mismatch' USING ERRCODE='22023'; END IF;
  IF history<>'null'::jsonb THEN
   IF phase='protective' OR (previous#>'{engine,lifecycle,risk,active}'='true'::jsonb AND control IS DISTINCT FROM 'recover') THEN
    RAISE EXCEPTION 'source_history_not_eligible' USING ERRCODE='22023'; END IF;
   additions:=vn_portable_source_research.history(history,expected->'bars',false,wall,mono);
   bars:=(expected->'bars')||additions;
   SELECT jsonb_agg(v ORDER BY ordinal) INTO bars FROM jsonb_array_elements(bars) WITH ORDINALITY a(v,ordinal)
    WHERE ordinal>greatest(jsonb_array_length(bars)-64,0);
   expected:=jsonb_set(expected,'{bars}',bars);
  END IF;
 END IF;
 IF source IS DISTINCT FROM expected THEN RAISE EXCEPTION 'source_after_mismatch' USING ERRCODE='22023'; END IF;
 IF following#>'{engine,ema}' IS DISTINCT FROM vn_portable_source_research.indicators(previous#>'{engine,ema}',additions) THEN
  RAISE EXCEPTION 'source_indicator_recurrence_mismatch' USING ERRCODE='22023'; END IF;
 observation:=CASE WHEN frame='null'::jsonb THEN 'null'::jsonb ELSE jsonb_build_object('timestamp',frame->'decision_second','price',frame#>'{quote,price}',
  'candle_end',CASE WHEN history<>'null'::jsonb OR control='recover' THEN source#>'{bars,-1,0}' ELSE 'null'::jsonb END,
  'candle_close',CASE WHEN history<>'null'::jsonb OR control='recover' THEN source#>'{bars,-1,1}' ELSE 'null'::jsonb END) END;
 IF evidence->'observation' IS DISTINCT FROM observation OR
    (frame<>'null'::jsonb AND at<>vn_portable_dependency_research.counter(frame->'decision_second',0,10000000000)) THEN
  RAISE EXCEPTION 'source_observation_mismatch' USING ERRCODE='22023'; END IF;
 RETURN jsonb_build_object('phase',phase,'source_sequence',source->'quote_sequence','candle_count',following#>'{engine,ema,count}',
   'original_document_trust','worker-parsed-records-and-manifests-v1','indicator_arithmetic','integer-ratio-binary64-ties-even-v1');
END $function$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_portable_source_research FROM PUBLIC;
