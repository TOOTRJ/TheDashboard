-- Offline-only numeric/hash boundary, not a command/admission installer.
-- No tables, runtime authority, grants to clients or production-package edits.
DO $guard$ BEGIN
  IF current_setting('dashboard.portable_numeric_wire_fixture',true) IS DISTINCT FROM 'offline-v2'
     OR current_setting('server_encoding') <> 'UTF8'
     OR current_setting('standard_conforming_strings') <> 'on' THEN
    RAISE EXCEPTION 'offline_portable_numeric_wire_fixture_required' USING ERRCODE='22023';
  END IF;
END $guard$;
CREATE SCHEMA vn_portable_numeric_research;
REVOKE ALL ON SCHEMA vn_portable_numeric_research FROM PUBLIC;

CREATE FUNCTION vn_portable_numeric_research.integer_text(value text) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE result numeric;
BEGIN
  IF value IS NULL OR length(value)>100 OR value !~ '^(0|-?[1-9][0-9]*)$' THEN
    RAISE EXCEPTION 'numeric_wire_invalid_integer' USING ERRCODE='22023';
  END IF;
  result:=value::numeric;
  IF abs(result)>115792089237316195423570985008687907853269984665640564039457584007913129639935 THEN
    RAISE EXCEPTION 'numeric_wire_integer_capacity' USING ERRCODE='22023';
  END IF;
  RETURN result;
END $function$;

CREATE FUNCTION vn_portable_numeric_research.binary64(value text) RETURNS bytea
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE sign_bit bit(1); exponent integer; fraction text; bits bit(64);
BEGIN
  IF value IS NULL OR length(value)>100 THEN
    RAISE EXCEPTION 'numeric_wire_invalid_binary64' USING ERRCODE='22023';
  END IF;
  sign_bit:=CASE WHEN left(value,1)='-' THEN B'1' ELSE B'0' END;
  IF value IN ('0x0.0p+0','-0x0.0p+0') THEN
    bits:=sign_bit||0::bit(11)||0::bit(52);
  ELSIF value ~ '^-?0x0\.[0-9a-f]{13}p-1022$' THEN
    fraction:=substring(value from '\.([0-9a-f]{13})p');
    IF fraction='0000000000000' THEN
      RAISE EXCEPTION 'numeric_wire_noncanonical_binary64' USING ERRCODE='22023';
    END IF;
    bits:=sign_bit||0::bit(11)||('x'||fraction)::bit(52);
  ELSIF value ~ '^-?0x1\.[0-9a-f]{13}p[+-](0|[1-9][0-9]{0,3})$'
        AND right(value,3)<>'p-0' THEN
    exponent:=substring(value from 'p([+-][0-9]+)$')::integer;
    IF exponent < -1022 OR exponent > 1023 THEN
      RAISE EXCEPTION 'numeric_wire_nonfinite_binary64' USING ERRCODE='22023';
    END IF;
    fraction:=substring(value from '\.([0-9a-f]{13})p');
    bits:=sign_bit||(exponent+1023)::bit(11)||('x'||fraction)::bit(52);
  ELSE
    RAISE EXCEPTION 'numeric_wire_noncanonical_binary64' USING ERRCODE='22023';
  END IF;
  -- The bit(64)->bigint cast preserves the sign bit as two's complement;
  -- int8send emits those eight big-endian bytes without floating conversion.
  RETURN int8send(bits::bigint);
END $function$;

CREATE FUNCTION vn_portable_numeric_research.walk(value json, depth integer, seen integer, spent integer)
RETURNS TABLE(canonical text,nodes integer,budget integer)
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE kind text; item record; child record; count_items integer;
        tag text; text_value text; parts text[]:=ARRAY[]::text[];
BEGIN
  IF depth IS NULL OR seen IS NULL OR spent IS NULL OR depth<0 OR seen<0 OR spent<0 THEN
    RAISE EXCEPTION 'numeric_wire_invalid_budget' USING ERRCODE='22023';
  END IF;
  nodes:=seen+1; budget:=spent+4;
  IF nodes>20000 OR depth>64 OR budget>262144 THEN
    RAISE EXCEPTION 'numeric_wire_structural_capacity' USING ERRCODE='22023';
  END IF;
  kind:=json_typeof(value);
  IF kind='string' THEN
    text_value:=value #>> '{}';
    IF octet_length(text_value)>16384 OR length(text_value)>16384 THEN
      RAISE EXCEPTION 'numeric_wire_string_capacity' USING ERRCODE='22023';
    END IF;
    budget:=budget+octet_length(text_value);
    canonical:=to_json(text_value)::text;
  ELSIF kind='null' THEN
    canonical:='null';
  ELSIF kind='boolean' THEN
    canonical:=CASE WHEN value::text::boolean THEN 'true' ELSE 'false' END;
  ELSIF kind='array' THEN
    count_items:=json_array_length(value);
    IF count_items>4096 THEN
      RAISE EXCEPTION 'numeric_wire_container_capacity' USING ERRCODE='22023';
    END IF;
    FOR item IN SELECT v FROM json_array_elements(value) AS a(v) LOOP
      SELECT * INTO child FROM vn_portable_numeric_research.walk(item.v,depth+1,nodes,budget);
      nodes:=child.nodes; budget:=child.budget;
      parts:=array_append(parts,child.canonical);
    END LOOP;
    canonical:='['||array_to_string(parts,',')||']';
  ELSIF kind='object' THEN
    SELECT count(*) INTO count_items FROM json_each(value);
    IF count_items>4096 THEN
      RAISE EXCEPTION 'numeric_wire_container_capacity' USING ERRCODE='22023';
    END IF;
    SELECT e.key INTO tag FROM json_each(value) e WHERE e.key IN ('$integer','$float64') LIMIT 1;
    IF tag IS NOT NULL THEN
      IF count_items<>1 OR json_typeof(value->tag)<>'string' THEN
        RAISE EXCEPTION 'numeric_wire_tag_collision' USING ERRCODE='22023';
      END IF;
      text_value:=value->>tag;
      IF tag='$integer' THEN
        PERFORM vn_portable_numeric_research.integer_text(text_value);
      ELSE
        PERFORM vn_portable_numeric_research.binary64(text_value);
      END IF;
      canonical:='{'||to_json(tag)::text||':'||to_json(text_value)::text||'}';
    ELSE
      FOR item IN SELECT e.key,e.value FROM json_each(value) e ORDER BY e.key COLLATE "C" LOOP
        SELECT * INTO child FROM vn_portable_numeric_research.walk(to_json(item.key),depth+1,nodes,budget);
        nodes:=child.nodes; budget:=child.budget;
        text_value:=child.canonical;
        SELECT * INTO child FROM vn_portable_numeric_research.walk(item.value,depth+1,nodes,budget);
        nodes:=child.nodes; budget:=child.budget;
        parts:=array_append(parts,text_value||':'||child.canonical);
      END LOOP;
      canonical:='{'||array_to_string(parts,',')||'}';
    END IF;
  ELSE
    RAISE EXCEPTION 'numeric_wire_untagged_number' USING ERRCODE='22023';
  END IF;
  IF budget>262144 OR octet_length(canonical)>262144 THEN
    RAISE EXCEPTION 'numeric_wire_structural_capacity' USING ERRCODE='22023';
  END IF;
  RETURN NEXT;
END $function$;

CREATE FUNCTION vn_portable_numeric_research.audit(wire text, maximum integer DEFAULT 262144) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE parsed json; result record;
BEGIN
  IF wire IS NULL OR maximum IS NULL OR maximum<1 OR maximum>262144
     OR octet_length(wire)>maximum THEN
    RAISE EXCEPTION 'numeric_wire_byte_capacity' USING ERRCODE='22023';
  END IF;
  -- Validate uniqueness before any jsonb conversion can discard duplicate keys.
  IF NOT (wire IS JSON WITH UNIQUE KEYS) THEN
    RAISE EXCEPTION 'numeric_wire_invalid_json_or_duplicate_key' USING ERRCODE='22023';
  END IF;
  parsed:=wire::json;
  SELECT * INTO result FROM vn_portable_numeric_research.walk(parsed,0,0,0);
  IF result.canonical IS DISTINCT FROM wire COLLATE "C" THEN
    RAISE EXCEPTION 'numeric_wire_noncanonical' USING ERRCODE='22023';
  END IF;
  RETURN jsonb_build_object('hash_policy','tagged-numeric-json-utf8-sha256-research-v1',
    'sha256',encode(sha256(convert_to(wire,'UTF8')),'hex'),'bytes',octet_length(wire),
    'nodes',result.nodes,'traversal_bytes',result.budget,'tagged',parsed::jsonb);
END $function$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_portable_numeric_research FROM PUBLIC;
