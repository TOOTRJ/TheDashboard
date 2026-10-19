-- Parser-only offline experiment. No tables, clocks, actors, admission or runtime.
DO $guard$ BEGIN
  IF current_setting('dashboard.jupiter_raw_parser_fixture',true) IS DISTINCT FROM 'offline-v3'
     OR current_setting('server_encoding') <> 'UTF8'
     OR current_setting('standard_conforming_strings') <> 'on' THEN
    RAISE EXCEPTION 'jupiter_raw_parser_offline_fixture_required' USING ERRCODE='22023';
  END IF;
END $guard$;
CREATE SCHEMA vn_jupiter_raw_parser_research_v3;
REVOKE ALL ON SCHEMA vn_jupiter_raw_parser_research_v3 FROM PUBLIC;

CREATE FUNCTION vn_jupiter_raw_parser_research_v3.require(ok boolean) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $f$
BEGIN
  IF ok IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'jupiter_raw_parser_invalid' USING ERRCODE='22023';
  END IF;
END $f$;

CREATE FUNCTION vn_jupiter_raw_parser_research_v3.number_token(token text) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $f$
DECLARE mantissa text; exponent_text text; exponent_value numeric;
BEGIN
  PERFORM vn_jupiter_raw_parser_research_v3.require(token IS NOT NULL AND octet_length(token)<=128
    AND token ~ '^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$' AND token <> '-0');
  mantissa:=split_part(lower(token),'e',1);
  PERFORM vn_jupiter_raw_parser_research_v3.require(length(regexp_replace(mantissa,'[-.]','','g'))<=80);
  exponent_text:=split_part(lower(token),'e',2);
  IF exponent_text<>'' THEN
    exponent_value:=exponent_text::numeric;
    PERFORM vn_jupiter_raw_parser_research_v3.require(exponent_value BETWEEN -80 AND 80);
  END IF;
END $f$;

CREATE FUNCTION vn_jupiter_raw_parser_research_v3.walk(value json,depth integer,seen integer,numeric_allowed boolean)
RETURNS integer LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $f$
DECLARE kind text; item record; keys bytea[]:=ARRAY[]::bytea[]; key_bytes bytea; n integer:=0;
BEGIN
  PERFORM vn_jupiter_raw_parser_research_v3.require(depth BETWEEN 0 AND 32 AND seen BETWEEN 0 AND 199999
    AND numeric_allowed IS NOT NULL AND value IS NOT NULL);
  seen:=seen+1; kind:=pg_catalog.json_typeof(value);
  IF kind='object' THEN
    FOR item IN SELECT * FROM pg_catalog.json_each(value) LOOP
      n:=n+1; seen:=seen+1;
      PERFORM vn_jupiter_raw_parser_research_v3.require(n<=1024 AND seen<=200000);
      key_bytes:=pg_catalog.convert_to(item.key,'UTF8');
      PERFORM vn_jupiter_raw_parser_research_v3.require(array_position(keys,key_bytes) IS NULL);
      keys:=array_append(keys,key_bytes);
      seen:=vn_jupiter_raw_parser_research_v3.walk(item.value,depth+1,seen,numeric_allowed);
    END LOOP;
  ELSIF kind='array' THEN
    FOR item IN SELECT * FROM pg_catalog.json_array_elements(value) LOOP
      n:=n+1; PERFORM vn_jupiter_raw_parser_research_v3.require(n<=5000);
      seen:=vn_jupiter_raw_parser_research_v3.walk(item.value,depth+1,seen,numeric_allowed);
    END LOOP;
  ELSIF kind='string' THEN
    -- Decoding every string forces PostgreSQL to validate all Unicode escapes,
    -- including unused values. Its text cannot represent NUL or lone surrogates.
    PERFORM pg_catalog.convert_to(value #>> '{}','UTF8');
  ELSIF kind='number' THEN
    PERFORM vn_jupiter_raw_parser_research_v3.require(numeric_allowed);
    PERFORM vn_jupiter_raw_parser_research_v3.number_token(value::text);
  ELSE
    PERFORM vn_jupiter_raw_parser_research_v3.require(kind IN ('null','boolean'));
  END IF;
  RETURN seen;
END $f$;

CREATE FUNCTION vn_jupiter_raw_parser_research_v3.read_json(raw bytea,maximum integer,numeric_allowed boolean)
RETURNS json LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $f$
DECLARE source text; value json; c integer; quoted boolean:=false; escaped boolean:=false; depth integer:=0; i integer;
BEGIN
  PERFORM vn_jupiter_raw_parser_research_v3.require(maximum IN (4096,65536,131072)
    AND raw IS NOT NULL AND octet_length(raw) BETWEEN 1 AND maximum);
  source:=pg_catalog.convert_from(raw,'UTF8');
  PERFORM vn_jupiter_raw_parser_research_v3.require(left(source,1)<>chr(65279));
  -- UTF8 was validated above. ASCII JSON delimiters are single bytes; scanning
  -- byte offsets avoids repeated multibyte substring walks over large bodies.
  FOR i IN 0..octet_length(raw)-1 LOOP
    c:=pg_catalog.get_byte(raw,i);
    IF quoted THEN
      IF escaped THEN escaped:=false;
      ELSIF c=92 THEN escaped:=true;
      ELSIF c=34 THEN quoted:=false; END IF;
    ELSIF c=34 THEN quoted:=true;
    ELSIF c IN (91,123) THEN
      depth:=depth+1; PERFORM vn_jupiter_raw_parser_research_v3.require(depth<=32);
    ELSIF c IN (93,125) THEN
      depth:=depth-1; PERFORM vn_jupiter_raw_parser_research_v3.require(depth>=0);
    END IF;
  END LOOP;
  value:=source::json;
  PERFORM vn_jupiter_raw_parser_research_v3.walk(value,0,0,numeric_allowed);
  RETURN value;
EXCEPTION WHEN SQLSTATE '22P02' OR SQLSTATE '22021' OR SQLSTATE '22P05' THEN
  RAISE EXCEPTION 'jupiter_raw_parser_invalid' USING ERRCODE='22023';
END $f$;

CREATE FUNCTION vn_jupiter_raw_parser_research_v3.canonical(value json) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $f$
DECLARE kind text:=pg_catalog.json_typeof(value); item record; pieces text[]:=ARRAY[]::text[];
BEGIN
  IF kind='object' THEN
    FOR item IN SELECT * FROM pg_catalog.json_each(value) ORDER BY key COLLATE "C" LOOP
      pieces:=array_append(pieces,pg_catalog.to_json(item.key)::text||':'||vn_jupiter_raw_parser_research_v3.canonical(item.value));
    END LOOP;
    RETURN '{'||array_to_string(pieces,',')||'}';
  ELSIF kind='array' THEN
    FOR item IN SELECT * FROM pg_catalog.json_array_elements(value) LOOP
      pieces:=array_append(pieces,vn_jupiter_raw_parser_research_v3.canonical(item.value));
    END LOOP;
    RETURN '['||array_to_string(pieces,',')||']';
  ELSIF kind='string' THEN RETURN pg_catalog.to_json(value #>> '{}')::text;
  ELSE RETURN value::text;
  END IF;
END $f$;

CREATE FUNCTION vn_jupiter_raw_parser_research_v3.fields(value json,required text[],allowed text[]) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $f$
DECLARE keys text[];
BEGIN
  PERFORM vn_jupiter_raw_parser_research_v3.require(pg_catalog.json_typeof(value)='object');
  SELECT array_agg(key) INTO keys FROM pg_catalog.json_each(value);
  PERFORM vn_jupiter_raw_parser_research_v3.require(coalesce(keys,ARRAY[]::text[]) @> required
    AND allowed @> coalesce(keys,ARRAY[]::text[]));
END $f$;

CREATE FUNCTION vn_jupiter_raw_parser_research_v3.integer_value(value json,maximum numeric,minimum numeric DEFAULT 0)
RETURNS numeric LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $f$
DECLARE token text:=value::text; result numeric;
BEGIN
  PERFORM vn_jupiter_raw_parser_research_v3.require(pg_catalog.json_typeof(value)='number' AND token ~ '^(0|-?[1-9][0-9]*)$');
  PERFORM vn_jupiter_raw_parser_research_v3.number_token(token);
  result:=token::numeric;
  PERFORM vn_jupiter_raw_parser_research_v3.require(result BETWEEN minimum AND maximum);
  RETURN result;
END $f$;

CREATE FUNCTION vn_jupiter_raw_parser_research_v3.decimal_plain(value json,positive boolean) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $f$
DECLARE token text:=value::text; mantissa text; digits text; tail text; whole text; exponent integer:=0; point integer; fraction integer;
BEGIN
  PERFORM vn_jupiter_raw_parser_research_v3.require(pg_catalog.json_typeof(value)='number' AND positive IS NOT NULL);
  PERFORM vn_jupiter_raw_parser_research_v3.number_token(token);
  PERFORM vn_jupiter_raw_parser_research_v3.require(left(token,1)<>'-');
  mantissa:=split_part(lower(token),'e',1);
  IF position('e' in lower(token))>0 THEN exponent:=split_part(lower(token),'e',2)::numeric::integer; END IF;
  fraction:=CASE WHEN position('.' in mantissa)>0 THEN length(split_part(mantissa,'.',2)) ELSE 0 END;
  exponent:=exponent-fraction;
  PERFORM vn_jupiter_raw_parser_research_v3.require(exponent BETWEEN -80 AND 80);
  digits:=ltrim(replace(mantissa,'.',''),'0');
  IF digits='' THEN PERFORM vn_jupiter_raw_parser_research_v3.require(NOT positive); RETURN '0'; END IF;
  PERFORM vn_jupiter_raw_parser_research_v3.require(length(digits)<=80);
  point:=length(digits)+exponent;
  IF point<=0 THEN whole:='0'; tail:=repeat('0',-point)||digits;
  ELSIF point>=length(digits) THEN whole:=digits||repeat('0',point-length(digits)); tail:='';
  ELSE whole:=left(digits,point); tail:=substr(digits,point+1); END IF;
  tail:=rtrim(tail,'0');
  PERFORM vn_jupiter_raw_parser_research_v3.require(length(whole)<=80 AND length(tail)<=80);
  RETURN whole||CASE WHEN tail='' THEN '' ELSE '.'||tail END;
END $f$;

-- The timestamp routines independently encode the pinned CPython 3.12.14
-- fromisoformat acceptance semantics. No PostgreSQL timestamp cast is used.
CREATE FUNCTION vn_jupiter_raw_parser_research_v3.time_piece(value text) RETURNS integer[]
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $f$
DECLARE vals integer[]:=ARRAY[0,0,0,0,0]; p integer:=1; ending integer:=length(value)+1;
        c text; separators boolean:=true; i integer; take integer; fragment text;
BEGIN
  FOR i IN 1..3 LOOP
    fragment:=substr(value,p,2);
    PERFORM vn_jupiter_raw_parser_research_v3.require(fragment ~ '^[0-9]{2}$');
    vals[i]:=fragment::integer; p:=p+2; c:=substr(value,p,1); p:=p+1;
    IF i=1 THEN separators:=(c=':'); END IF;
    IF p>=ending THEN vals[5]:=CASE WHEN c='' THEN 0 ELSE 1 END; RETURN vals;
    ELSIF separators AND c=':' THEN CONTINUE;
    ELSIF c IN ('.',',') THEN EXIT;
    ELSIF NOT separators THEN p:=p-1;
    ELSE PERFORM vn_jupiter_raw_parser_research_v3.require(false); END IF;
  END LOOP;
  take:=least(6,ending-p); fragment:=substr(value,p,take);
  PERFORM vn_jupiter_raw_parser_research_v3.require(take>0 AND fragment ~ '^[0-9]+$');
  vals[4]:=fragment::integer*(ARRAY[100000,10000,1000,100,10,1])[take]; p:=p+take;
  WHILE substr(value,p,1) ~ '^[0-9]$' LOOP p:=p+1; END LOOP;
  vals[5]:=CASE WHEN p>=ending THEN 0 ELSE 1 END;
  RETURN vals;
END $f$;

CREATE FUNCTION vn_jupiter_raw_parser_research_v3.created_at(value json) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $f$
DECLARE stamp text; datepart text; rest text; sep integer; idx integer; year integer; month integer; day integer;
        week integer; weekday integer:=1; jan date; datevalue date; parts integer[]; offsetparts integer[]; zone integer:=0; i integer;
BEGIN
  PERFORM vn_jupiter_raw_parser_research_v3.require(pg_catalog.json_typeof(value)='string');
  stamp:=value #>> '{}'; PERFORM vn_jupiter_raw_parser_research_v3.require(length(stamp) BETWEEN 1 AND 64);
  stamp:=replace(stamp,'Z','+00:00');
  IF length(stamp)=7 THEN sep:=7;
  ELSIF substr(stamp,5,1)='-' THEN
    IF substr(stamp,6,1)='W' THEN
      PERFORM vn_jupiter_raw_parser_research_v3.require(length(stamp)>=8);
      IF length(stamp)>8 AND substr(stamp,9,1)='-' THEN
        PERFORM vn_jupiter_raw_parser_research_v3.require(length(stamp)<>9);
        sep:=CASE WHEN length(stamp)>10 AND substr(stamp,11,1) ~ '^[0-9]$' THEN 8 ELSE 10 END;
      ELSE sep:=8; END IF;
    ELSE sep:=10; END IF;
  ELSIF substr(stamp,5,1)='W' THEN
    idx:=8; WHILE idx<=length(stamp) AND substr(stamp,idx,1) ~ '^[0-9]$' LOOP idx:=idx+1; END LOOP;
    sep:=CASE WHEN idx<10 THEN idx-1 WHEN (idx-1)%2=0 THEN 7 ELSE 8 END;
  ELSE sep:=8; END IF;
  datepart:=left(stamp,sep);
  PERFORM vn_jupiter_raw_parser_research_v3.require(left(datepart,4) ~ '^[0-9]{4}$');
  year:=left(datepart,4)::integer; PERFORM vn_jupiter_raw_parser_research_v3.require(year BETWEEN 1 AND 9999);
  IF datepart ~ '^[0-9]{4}(-W[0-9]{2}(-[0-9])?|W[0-9]{2}[0-9]?)$' THEN
    rest:=substr(datepart,5); rest:=replace(rest,'-',''); week:=substr(rest,2,2)::integer;
    IF length(rest)=4 THEN weekday:=right(rest,1)::integer; END IF;
    jan:=pg_catalog.make_date(year,1,4);
    PERFORM vn_jupiter_raw_parser_research_v3.require(weekday BETWEEN 1 AND 7 AND week BETWEEN 1 AND 53
      AND (week<53 OR pg_catalog.extract('isodow',pg_catalog.make_date(year,1,1))=4
        OR (pg_catalog.extract('isodow',pg_catalog.make_date(year,1,1))=3 AND year%4=0 AND (year%100<>0 OR year%400=0))));
    datevalue:=jan-(pg_catalog.extract('isodow',jan)::integer-1)+(week-1)*7+weekday-1;
    PERFORM vn_jupiter_raw_parser_research_v3.require(pg_catalog.extract('year',datevalue) BETWEEN 1 AND 9999);
  ELSE
    PERFORM vn_jupiter_raw_parser_research_v3.require(datepart ~ '^([0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2})$');
    rest:=replace(datepart,'-',''); month:=substr(rest,5,2)::integer; day:=substr(rest,7,2)::integer;
    datevalue:=pg_catalog.make_date(year,month,day);
  END IF;
  rest:=substr(stamp,sep+2);
  FOR i IN 1..length(rest) LOOP IF substr(rest,i,1) IN ('+','-') THEN zone:=i; EXIT; END IF; END LOOP;
  PERFORM vn_jupiter_raw_parser_research_v3.require(zone>1);
  parts:=vn_jupiter_raw_parser_research_v3.time_piece(left(rest,zone-1));
  offsetparts:=vn_jupiter_raw_parser_research_v3.time_piece(substr(rest,zone+1));
  -- CPython returns UTC when the integral offset is zero, even if its parsed
  -- fractional offset is nonzero. Preserve this compatibility rather than cast.
  PERFORM vn_jupiter_raw_parser_research_v3.require(parts[1]<=23 AND parts[2]<=59 AND parts[3]<=59
    AND offsetparts[5]=0 AND offsetparts[1]=0 AND offsetparts[2]=0 AND offsetparts[3]=0);
EXCEPTION WHEN SQLSTATE '22008' THEN
  RAISE EXCEPTION 'jupiter_raw_parser_invalid' USING ERRCODE='22023';
END $f$;

CREATE FUNCTION vn_jupiter_raw_parser_research_v3.parse_original_trio(public_request_wires bytea[],raw_bodies bytea[])
RETURNS text LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $f$
DECLARE requests json[]:=ARRAY[]::json[]; bodies json[]:=ARRAY[]::json[]; rpc json[]:=ARRAY[]::json[];
        current json; info json; result json; originals json[]:=ARRAY[]::json[]; authority json;
        i integer; price text; block numeric; source_second numeric; ids numeric[]:=ARRAY[]::numeric[];
        mint constant text:='So11111111111111111111111111111111111111112';
        genesis constant text:='5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d';
BEGIN
  PERFORM vn_jupiter_raw_parser_research_v3.require(array_ndims(public_request_wires)=1 AND array_ndims(raw_bodies)=1
    AND array_lower(public_request_wires,1)=1 AND array_lower(raw_bodies,1)=1
    AND cardinality(public_request_wires)=3 AND cardinality(raw_bodies)=3);
  FOR i IN 1..3 LOOP
    current:=vn_jupiter_raw_parser_research_v3.read_json(public_request_wires[i],4096,false);
    PERFORM vn_jupiter_raw_parser_research_v3.fields(current,ARRAY['format','method','endpoint','chain','parameters','body_wire'],
      ARRAY['format','method','endpoint','chain','parameters','body_wire']);
    PERFORM vn_jupiter_raw_parser_research_v3.require(current->>'format'='ga-provider-public-request-research-v3'
      AND current->>'chain'='solana' AND public_request_wires[i]=convert_to(vn_jupiter_raw_parser_research_v3.canonical(current),'UTF8'));
    requests:=array_append(requests,current);
    bodies:=array_append(bodies,vn_jupiter_raw_parser_research_v3.read_json(raw_bodies[i],CASE WHEN i=1 THEN 131072 ELSE 65536 END,true));
    IF i=1 THEN
      PERFORM vn_jupiter_raw_parser_research_v3.require(current->>'method'='GET' AND current->>'endpoint'='https://api.jup.ag/price/v3'
        AND pg_catalog.json_typeof(current->'body_wire')='null');
      PERFORM vn_jupiter_raw_parser_research_v3.fields(current->'parameters',ARRAY['ids'],ARRAY['ids']);
      PERFORM vn_jupiter_raw_parser_research_v3.require(pg_catalog.json_typeof(current->'parameters'->'ids')='string' AND current->'parameters'->>'ids'=mint);
    ELSE
      PERFORM vn_jupiter_raw_parser_research_v3.require(current->>'method'='POST' AND current->>'endpoint'='operator-bound-solana-rpc'
        AND pg_catalog.json_typeof(current->'body_wire')='string');
      PERFORM vn_jupiter_raw_parser_research_v3.fields(current->'parameters',ARRAY[]::text[],ARRAY[]::text[]);
      info:=vn_jupiter_raw_parser_research_v3.read_json(convert_to(current->>'body_wire','UTF8'),4096,true);
      PERFORM vn_jupiter_raw_parser_research_v3.fields(info,ARRAY['jsonrpc','id','method','params'],ARRAY['jsonrpc','id','method','params']);
      PERFORM vn_jupiter_raw_parser_research_v3.require(pg_catalog.json_typeof(info->'jsonrpc')='string' AND info->>'jsonrpc'='2.0'
        AND pg_catalog.json_typeof(info->'method')='string' AND info->>'method'=CASE WHEN i=2 THEN 'getGenesisHash' ELSE 'getBlockTime' END
        AND current->>'body_wire'=vn_jupiter_raw_parser_research_v3.canonical(info));
      ids:=array_append(ids,vn_jupiter_raw_parser_research_v3.integer_value(info->'id',2147483647,1));
      rpc:=array_append(rpc,info);
    END IF;
    originals:=array_append(originals,pg_catalog.json_build_object('provider_family',CASE WHEN i=1 THEN 'jupiter-price-v3' ELSE 'solana-rpc' END,
      'request_sha256',encode(sha256(public_request_wires[i]),'hex'),'request_bytes',octet_length(public_request_wires[i])::text,
      'response_sha256',encode(sha256(raw_bodies[i]),'hex'),'response_bytes',octet_length(raw_bodies[i])::text));
  END LOOP;
  PERFORM vn_jupiter_raw_parser_research_v3.fields(bodies[1],ARRAY[mint],ARRAY[mint]);
  info:=bodies[1]->mint;
  PERFORM vn_jupiter_raw_parser_research_v3.fields(info,ARRAY['usdPrice','blockId','decimals'],
    ARRAY['usdPrice','blockId','decimals','createdAt','liquidity','priceChange24h']);
  price:=vn_jupiter_raw_parser_research_v3.decimal_plain(info->'usdPrice',true);
  PERFORM vn_jupiter_raw_parser_research_v3.require(length(price)<=75 AND length(split_part(price,'.',2))<=18
    AND price::numeric<=1000000000000000000000000000000000000);
  block:=vn_jupiter_raw_parser_research_v3.integer_value(info->'blockId',18446744073709551615);
  PERFORM vn_jupiter_raw_parser_research_v3.require(vn_jupiter_raw_parser_research_v3.integer_value(info->'decimals',9)=9);
  IF info->'createdAt' IS NOT NULL THEN PERFORM vn_jupiter_raw_parser_research_v3.created_at(info->'createdAt'); END IF;
  IF info->'liquidity' IS NOT NULL THEN PERFORM vn_jupiter_raw_parser_research_v3.decimal_plain(info->'liquidity',false); END IF;
  IF info->'priceChange24h' IS NOT NULL THEN
    PERFORM vn_jupiter_raw_parser_research_v3.require(pg_catalog.json_typeof(info->'priceChange24h') IN ('null','number'));
  END IF;
  PERFORM vn_jupiter_raw_parser_research_v3.require(ids[1]<>ids[2] AND pg_catalog.json_typeof(rpc[1]->'params')='array'
    AND pg_catalog.json_array_length(rpc[1]->'params')=0 AND pg_catalog.json_typeof(rpc[2]->'params')='array'
    AND pg_catalog.json_array_length(rpc[2]->'params')=1
    AND vn_jupiter_raw_parser_research_v3.integer_value(rpc[2]->'params'->0,18446744073709551615)=block);
  FOR i IN 2..3 LOOP
    PERFORM vn_jupiter_raw_parser_research_v3.fields(bodies[i],ARRAY['jsonrpc','id','result'],ARRAY['jsonrpc','id','result']);
    PERFORM vn_jupiter_raw_parser_research_v3.require(pg_catalog.json_typeof(bodies[i]->'jsonrpc')='string'
      AND bodies[i]->>'jsonrpc'='2.0' AND vn_jupiter_raw_parser_research_v3.integer_value(bodies[i]->'id',2147483647,1)=ids[i-1]);
  END LOOP;
  PERFORM vn_jupiter_raw_parser_research_v3.require(pg_catalog.json_typeof(bodies[2]->'result')='string' AND bodies[2]->>'result'=genesis);
  source_second:=vn_jupiter_raw_parser_research_v3.integer_value(bodies[3]->'result',10000000000);
  authority:=pg_catalog.json_build_object('authenticated_principal',false,'calibrated_clock',false,'committed_readback',false,
    'hosted_authority',false,'lease_authority',false,'live_trading_authority',false,'native_admission',false,'provider_attested',false,'running_authority',false);
  result:=pg_catalog.json_build_object('format','ga-jupiter-source-raw-parser-projection-research-v3',
    'parser_policy_sha256','e7fb225868e9401e5648487e9836d9c0aff817f2ba2cdd63a20b90b75aadb24e',
    'source_profile','jupiter-price-v3-prospective-minute-sampled-close-v1','asset','SOL/USD','mint',mint,'decimals','9',
    'denomination','USD','valuation','reference_mark','genesis_hash',genesis,'price_decimal',price,'block_ref',block::text,
    'estimated_source_second',source_second::text,'originals',originals,'authority',authority);
  PERFORM vn_jupiter_raw_parser_research_v3.require(octet_length(vn_jupiter_raw_parser_research_v3.canonical(result))<=8192);
  RETURN vn_jupiter_raw_parser_research_v3.canonical(result);
EXCEPTION WHEN SQLSTATE '22P02' OR SQLSTATE '22021' OR SQLSTATE '22P05' OR SQLSTATE '22003' OR SQLSTATE '22008' OR SQLSTATE '22023' THEN
  RAISE EXCEPTION 'jupiter_raw_parser_invalid' USING ERRCODE='22023';
END $f$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_jupiter_raw_parser_research_v3 FROM PUBLIC;
