-- OFFLINE RESOLUTION PROOF ONLY. Not a migration, command, receipt or decoder.
-- No economic/source/history admission, lease, journal, projection or pin writes.
DO $guard$ BEGIN
  IF current_setting('dashboard.portable_locked_checkpoint_fixture',true) IS DISTINCT FROM 'offline-v2'
     OR to_regprocedure('vn_portable_configuration_research.validate(jsonb)') IS NULL
     OR current_setting('server_encoding') <> 'UTF8'
     OR current_setting('standard_conforming_strings') <> 'on'
     OR to_regprocedure('vn_numeric_research.audit(text,integer)') IS NULL THEN
    RAISE EXCEPTION 'offline_portable_locked_checkpoint_fixture_required' USING ERRCODE='22023';
  END IF;
END $guard$;

CREATE SCHEMA vn_portable_dependency_research;
REVOKE ALL ON SCHEMA vn_portable_dependency_research FROM PUBLIC;
-- Fixture seeding is privileged. resolve_request never changes these tables.
CREATE TABLE vn_portable_dependency_research.checkpoints (
  run_id uuid PRIMARY KEY,
  owner_id uuid NOT NULL,
  revision bigint NOT NULL CHECK(revision>=1),
  manifest_wire text,
  UNIQUE(owner_id,run_id),
  CHECK ((revision=1 AND manifest_wire IS NULL) OR
         (revision>=2 AND manifest_wire IS NOT NULL AND octet_length(manifest_wire)<=65536))
);
CREATE TABLE vn_portable_dependency_research.components (
  owner_id uuid NOT NULL,
  run_id uuid NOT NULL,
  sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
  wire text NOT NULL CHECK(octet_length(wire)<=196608),
  PRIMARY KEY(owner_id,run_id,sha256),
  FOREIGN KEY(owner_id,run_id) REFERENCES vn_portable_dependency_research.checkpoints(owner_id,run_id),
  CHECK(sha256=encode(pg_catalog.sha256(convert_to(wire,'UTF8')),'hex'))
);
REVOKE ALL ON ALL TABLES IN SCHEMA vn_portable_dependency_research FROM PUBLIC;

CREATE FUNCTION vn_portable_dependency_research.exact_keys(value jsonb, expected text[])
RETURNS void LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE actual text[];
BEGIN
  IF jsonb_typeof(value) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'checkpoint_object_required' USING ERRCODE='22023';
  END IF;
  SELECT array_agg(k ORDER BY k COLLATE "C") INTO actual FROM jsonb_object_keys(value) k;
  IF coalesce(actual,ARRAY[]::text[]) IS DISTINCT FROM
     (SELECT coalesce(array_agg(k ORDER BY k COLLATE "C"),ARRAY[]::text[]) FROM unnest(expected) k) THEN
    RAISE EXCEPTION 'checkpoint_keys_differ' USING ERRCODE='22023';
  END IF;
END $function$;

CREATE FUNCTION vn_portable_dependency_research.counter(value jsonb, minimum numeric, maximum numeric)
RETURNS bigint LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE result numeric;
BEGIN
  PERFORM vn_portable_dependency_research.exact_keys(value,ARRAY['$integer']);
  IF jsonb_typeof(value->'$integer') IS DISTINCT FROM 'string' THEN
    RAISE EXCEPTION 'checkpoint_integer_required' USING ERRCODE='22023';
  END IF;
  result:=vn_numeric_research.integer_text(value->>'$integer');
  IF minimum IS NULL OR maximum IS NULL OR minimum>maximum OR
     result<minimum OR result>maximum THEN
    RAISE EXCEPTION 'checkpoint_counter_capacity' USING ERRCODE='22023';
  END IF;
  RETURN result::bigint;
END $function$;

CREATE FUNCTION vn_portable_dependency_research.uuid_text(value jsonb)
RETURNS text LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE result text:=value #>> '{}';
BEGIN
  IF jsonb_typeof(value) IS DISTINCT FROM 'string' OR
     result !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'checkpoint_uuid_required' USING ERRCODE='22023';
  END IF;
  RETURN result;
END $function$;

CREATE FUNCTION vn_portable_dependency_research.canonical(value jsonb)
RETURNS text LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $function$
  SELECT canonical FROM vn_numeric_research.walk(value::json,0,0,0)
$function$;

CREATE FUNCTION vn_portable_dependency_research.block(wire text, owner_id uuid, run_id uuid)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE kind text; entity text; generation bigint; checked jsonb; value jsonb;
BEGIN
  checked:=vn_numeric_research.audit(wire,196608);
  value:=checked->'tagged';
  PERFORM vn_portable_dependency_research.exact_keys(value,
    ARRAY['format','hash_policy','owner_id','run_id','kind','entity_id','generation','body']);
  IF value->>'format' IS DISTINCT FROM 'ga-portable-provider-component-research-v2' OR
     value->>'hash_policy' IS DISTINCT FROM 'tagged-numeric-json-utf8-sha256-research-v1' OR
     vn_portable_dependency_research.uuid_text(value->'owner_id') IS DISTINCT FROM owner_id::text OR
     vn_portable_dependency_research.uuid_text(value->'run_id') IS DISTINCT FROM run_id::text OR
     jsonb_typeof(value->'body') IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'checkpoint_component_scope_or_format' USING ERRCODE='22023';
  END IF;
  kind:=value->>'kind'; entity:=value->>'entity_id';
  generation:=vn_portable_dependency_research.counter(value->'generation',0,2147483647);
  IF jsonb_typeof(value->'kind') IS DISTINCT FROM 'string' OR
     jsonb_typeof(value->'entity_id') IS DISTINCT FROM 'string' OR
     kind NOT IN ('configuration','optimizer','cohort','genome','source_bars','ema') THEN
    RAISE EXCEPTION 'checkpoint_component_slot' USING ERRCODE='22023';
  END IF;
  IF kind='genome' THEN
    PERFORM vn_portable_dependency_research.uuid_text(value->'entity_id');
  ELSIF entity<>kind OR (kind IN ('configuration','source_bars','ema') AND generation<>0) THEN
    RAISE EXCEPTION 'checkpoint_component_slot' USING ERRCODE='22023';
  END IF;
  IF octet_length(value::text)>196608 THEN
    RAISE EXCEPTION 'checkpoint_component_capacity' USING ERRCODE='22023';
  END IF;
  RETURN jsonb_build_object('sha256',checked->'sha256','wire',wire,'tagged',value);
END $function$;

CREATE FUNCTION vn_portable_dependency_research.expand(manifest jsonb, blocks jsonb,
  owner_id uuid, run_id uuid, revision bigint)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE checked jsonb; wire text; total integer; ref jsonb; entry jsonb; body jsonb;
  generation bigint; expected_generation bigint; kind text; entity text; digest text;
  slots jsonb:='{}'; seen text[]:=ARRAY[]::text[]; ids text[]:=ARRAY[]::text[];
  members jsonb:='[]'; member jsonb; expanded jsonb; result jsonb;
BEGIN
  PERFORM vn_portable_dependency_research.exact_keys(manifest,ARRAY['format','source_model_version',
    'owner_id','run_id','revision','status','reserve','accounts','positions','engine','source','components']);
  IF manifest->>'format' IS DISTINCT FROM 'ga-portable-provider-checkpoint-research-v2' OR
     manifest->>'source_model_version' IS DISTINCT FROM 'ga-portable-provider-model-research-v2' OR
     vn_portable_dependency_research.uuid_text(manifest->'owner_id') IS DISTINCT FROM owner_id::text OR
     vn_portable_dependency_research.uuid_text(manifest->'run_id') IS DISTINCT FROM run_id::text OR
     vn_portable_dependency_research.counter(manifest->'revision',2,9223372036854775807)<>revision OR
     jsonb_typeof(manifest->'status') IS DISTINCT FROM 'string' OR
     manifest->>'status' NOT IN ('running','paused','risk_halted','stopped','failed') THEN
    RAISE EXCEPTION 'checkpoint_manifest_binding' USING ERRCODE='22023';
  END IF;
  wire:=vn_portable_dependency_research.canonical(manifest);
  checked:=vn_numeric_research.audit(wire,65536);
  total:=octet_length(wire);
  IF octet_length(manifest::text)>65536 OR
     jsonb_typeof(manifest->'components') IS DISTINCT FROM 'array' OR
     jsonb_array_length(manifest->'components')<>13 OR
     jsonb_typeof(blocks) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'checkpoint_complete_component_set' USING ERRCODE='22023';
  END IF;
  PERFORM vn_portable_dependency_research.exact_keys(manifest->'engine',
    ARRAY['generation','last_quote','decision_timestamp','lifecycle','cohort_source','members']);
  generation:=vn_portable_dependency_research.counter(manifest#>'{engine,generation}',0,2147483647);
  IF jsonb_typeof(manifest->'source') IS DISTINCT FROM 'object' OR
     (manifest->'source') ? 'bars' OR
     jsonb_typeof(manifest#>'{engine,members}') IS DISTINCT FROM 'array' OR
     jsonb_array_length(manifest#>'{engine,members}')<>8 THEN
    RAISE EXCEPTION 'checkpoint_engine_slots' USING ERRCODE='22023';
  END IF;
  FOR member IN SELECT v FROM jsonb_array_elements(manifest#>'{engine,members}') a(v) LOOP
    PERFORM vn_portable_dependency_research.exact_keys(member,ARRAY['id','name','cursor','pending',
      'num_trades','peak_equity','max_drawdown','terminal','assessment']);
    entity:=vn_portable_dependency_research.uuid_text(member->'id');
    IF entity=ANY(ids) THEN
      RAISE EXCEPTION 'checkpoint_duplicate_member' USING ERRCODE='22023';
    END IF;
    ids:=array_append(ids,entity);
  END LOOP;
  FOR ref IN SELECT v FROM jsonb_array_elements(manifest->'components') a(v) LOOP
    PERFORM vn_portable_dependency_research.exact_keys(ref,ARRAY['kind','entity_id','generation','sha256']);
    kind:=ref->>'kind'; entity:=ref->>'entity_id'; digest:=ref->>'sha256';
    IF jsonb_typeof(ref->'sha256') IS DISTINCT FROM 'string' OR
       digest !~ '^[0-9a-f]{64}$' OR digest=ANY(seen) OR NOT blocks ? digest THEN
      RAISE EXCEPTION 'checkpoint_missing_or_duplicate_reference' USING ERRCODE='22023';
    END IF;
    -- Entries are constructed exactly once by the private block() helper while
    -- resolving this request. Only resolve_request is granted to the auditor.
    entry:=blocks->digest;
    body:=entry->'tagged';
    IF entry->>'sha256'<>digest OR
       body->'kind' IS DISTINCT FROM ref->'kind' OR
       body->'entity_id' IS DISTINCT FROM ref->'entity_id' OR
       body->'generation' IS DISTINCT FROM ref->'generation' THEN
      RAISE EXCEPTION 'checkpoint_reference_binding' USING ERRCODE='22023';
    END IF;
    expected_generation:=CASE WHEN kind IN ('configuration','source_bars','ema') THEN 0 ELSE generation END;
    IF vn_portable_dependency_research.counter(ref->'generation',0,2147483647)<>expected_generation OR
       (kind='genome' AND NOT entity=ANY(ids)) OR slots ? (kind||':'||entity) THEN
      RAISE EXCEPTION 'checkpoint_reference_slot_or_generation' USING ERRCODE='22023';
    END IF;
    seen:=array_append(seen,digest);
    slots:=slots||jsonb_build_object(kind||':'||entity,body->'body');
    total:=total+octet_length(entry->>'wire');
    IF total>262144 THEN
      RAISE EXCEPTION 'checkpoint_dependency_capacity' USING ERRCODE='22023';
    END IF;
  END LOOP;
  -- Thirteen unique allowlisted slots imply all five fixed slots and eight genomes.
  IF NOT slots ?& ARRAY['configuration:configuration','optimizer:optimizer','cohort:cohort',
                        'source_bars:source_bars','ema:ema'] THEN
    RAISE EXCEPTION 'checkpoint_fixed_slot_missing' USING ERRCODE='22023';
  END IF;
  PERFORM vn_portable_dependency_research.exact_keys(slots->'source_bars:source_bars',ARRAY['bars']);
  PERFORM vn_portable_configuration_research.validate(slots->'configuration:configuration');
  IF slots#>>'{configuration:configuration,strategy}' IS DISTINCT FROM 'genetic_algorithm' OR
     slots#>>'{optimizer:optimizer,strategy,class}' IS DISTINCT FROM 'GeneticAlgorithmStrategy' OR
     slots#>'{cohort:cohort,member_ids}' IS DISTINCT FROM to_jsonb(ids) OR
     slots#>>'{cohort:cohort,iteration_id}' IS DISTINCT FROM (run_id::text||':'||generation::text) OR
     vn_portable_dependency_research.counter(slots#>'{cohort:cohort,member_count}',8,8)<>8 THEN
    RAISE EXCEPTION 'checkpoint_model_identity' USING ERRCODE='22023';
  END IF;
  FOR member IN SELECT v FROM jsonb_array_elements(manifest#>'{engine,members}') a(v) LOOP
    body:=slots->('genome:'||(member->>'id'));
    IF body IS NULL OR vn_portable_dependency_research.counter(body->'generation',0,2147483647)<>generation THEN
      RAISE EXCEPTION 'checkpoint_genome_generation' USING ERRCODE='22023';
    END IF;
    members:=members||jsonb_build_array(member||jsonb_build_object('genome',body));
  END LOOP;
  expanded:=(manifest-'components')||jsonb_build_object(
    'engine',(manifest->'engine')||jsonb_build_object('config',slots->'configuration:configuration',
      'optimizer',slots->'optimizer:optimizer','cohort',slots->'cohort:cohort',
      'ema',slots->'ema:ema','members',members),
    'source',(manifest->'source')||(slots->'source_bars:source_bars'));
  wire:=vn_portable_dependency_research.canonical(expanded);
  result:=vn_numeric_research.audit(wire,262144);
  IF octet_length(expanded::text)>262144 THEN
    RAISE EXCEPTION 'checkpoint_expanded_capacity' USING ERRCODE='22023';
  END IF;
  RETURN jsonb_build_object('manifest_sha256',checked->'sha256','wire',wire,
    'dependency_bytes',total,'resolved_bytes',octet_length(wire));
END $function$;

CREATE FUNCTION vn_portable_dependency_research.resolve_request(owner_id uuid, run_id uuid, request_wire text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $function$
DECLARE current vn_portable_dependency_research.checkpoints%ROWTYPE; audited jsonb; request jsonb;
  following jsonb; previous jsonb; prior jsonb; prior_result jsonb; next_result jsonb;
  supplied jsonb:='{}'; retained jsonb:='{}';
  entry jsonb; ref record; digest text; component jsonb; stored text; checked jsonb;
  maximum integer; next_revision bigint; prior_generation bigint; next_generation bigint;
  prior_total integer; next_total integer; component_bytes integer;
BEGIN
  IF owner_id IS NULL OR run_id IS NULL THEN
    RAISE EXCEPTION 'checkpoint_scope_required' USING ERRCODE='22023';
  END IF;
  audited:=vn_numeric_research.audit(request_wire,262144);
  request:=audited->'tagged';
  PERFORM vn_portable_dependency_research.exact_keys(request,ARRAY['format','command_id','owner_id','run_id',
    'prior','checkpoint','components','operations','history','evidence','events']);
  PERFORM vn_portable_dependency_research.uuid_text(request->'command_id');
  IF request->>'format' IS DISTINCT FROM 'ga-portable-provider-compact-command-research-v2' OR
     vn_portable_dependency_research.uuid_text(request->'owner_id') IS DISTINCT FROM owner_id::text OR
     vn_portable_dependency_research.uuid_text(request->'run_id') IS DISTINCT FROM run_id::text THEN
    RAISE EXCEPTION 'checkpoint_request_scope_or_format' USING ERRCODE='22023';
  END IF;
  following:=request->'checkpoint';
  maximum:=CASE WHEN request#>>'{evidence,control,action}'='stop' AND
    request#>>'{evidence,kind}'='control' AND following->>'status'='stopped'
    THEN 262144 ELSE 196608 END;
  IF octet_length(request_wire)>maximum OR octet_length(request::text)>maximum OR
     jsonb_typeof(request->'components') IS DISTINCT FROM 'array' OR
     jsonb_array_length(request->'components')>13 THEN
    RAISE EXCEPTION 'checkpoint_request_capacity' USING ERRCODE='22023';
  END IF;
  -- All authoritative prior reads occur AFTER this lock returns. No stale cache.
  SELECT * INTO current FROM vn_portable_dependency_research.checkpoints c
    WHERE c.run_id=resolve_request.run_id AND c.owner_id=resolve_request.owner_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'checkpoint_run_unavailable' USING ERRCODE='22023';
  END IF;
  IF current.revision>=9223372036854775807 THEN
    RAISE EXCEPTION 'checkpoint_revision_exhausted' USING ERRCODE='22023';
  END IF;
  next_revision:=current.revision+1;
  IF next_revision=9223372036854775807 AND maximum<>262144 THEN
    RAISE EXCEPTION 'checkpoint_stop_revision_reserved' USING ERRCODE='22023';
  END IF;
  prior:=request->'prior';
  IF current.manifest_wire IS NULL THEN
    IF prior IS DISTINCT FROM 'null'::jsonb THEN
      RAISE EXCEPTION 'checkpoint_bootstrap_prior' USING ERRCODE='22023';
    END IF;
  ELSE
    checked:=vn_numeric_research.audit(current.manifest_wire,65536);
    previous:=checked->'tagged';
    PERFORM vn_portable_dependency_research.exact_keys(prior,ARRAY['revision','sha256']);
    IF vn_portable_dependency_research.counter(prior->'revision',2,9223372036854775807)<>current.revision OR
       prior->'sha256' IS DISTINCT FROM checked->'sha256' THEN
      RAISE EXCEPTION 'checkpoint_prior_mismatch' USING ERRCODE='22023';
    END IF;
  END IF;
  FOR component IN SELECT v FROM jsonb_array_elements(request->'components') a(v) LOOP
    entry:=vn_portable_dependency_research.block(vn_portable_dependency_research.canonical(component),owner_id,run_id);
    digest:=entry->>'sha256';
    IF supplied ? digest THEN
      RAISE EXCEPTION 'checkpoint_duplicate_supplied_component' USING ERRCODE='22023';
    END IF;
    supplied:=supplied||jsonb_build_object(digest,entry);
  END LOOP;
  -- Bound both reference sets before scanning. Sorted component locks prevent
  -- reference-order-dependent lock cycles. FOR SHARE pins rows for this txn only.
  IF jsonb_typeof(following->'components') IS DISTINCT FROM 'array' OR
     jsonb_array_length(following->'components')<>13 OR
     (previous IS NOT NULL AND (jsonb_typeof(previous->'components') IS DISTINCT FROM 'array' OR
       jsonb_array_length(previous->'components')<>13)) THEN
    RAISE EXCEPTION 'checkpoint_complete_component_set' USING ERRCODE='22023';
  END IF;
  prior_total:=coalesce(octet_length(current.manifest_wire),0);
  next_total:=octet_length(vn_portable_dependency_research.canonical(following));
  IF next_total>65536 THEN
    RAISE EXCEPTION 'checkpoint_manifest_capacity' USING ERRCODE='22023';
  END IF;
  FOR ref IN SELECT DISTINCT (v->>'sha256') COLLATE "C" AS hash FROM (
    SELECT v FROM jsonb_array_elements(following->'components') a(v)
    UNION ALL SELECT v FROM jsonb_array_elements(coalesce(previous->'components','[]')) a(v)
  ) refs ORDER BY hash LOOP
    digest:=ref.hash;
    IF digest IS NULL OR digest !~ '^[0-9a-f]{64}$' THEN
      RAISE EXCEPTION 'checkpoint_reference_digest' USING ERRCODE='22023';
    END IF;
    SELECT c.wire INTO stored FROM vn_portable_dependency_research.components c
      WHERE c.owner_id=resolve_request.owner_id AND c.run_id=resolve_request.run_id
        AND c.sha256=digest FOR SHARE;
    -- Charge original bytes before decoding/materializing retained blocks.
    -- Each checkpoint has its own full dependency budget even when shared.
    component_bytes:=coalesce(octet_length(stored),
      octet_length(supplied#>>ARRAY[digest,'wire']),0);
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(coalesce(previous->'components','[]')) r
      WHERE r->>'sha256'=digest) THEN
      prior_total:=prior_total+component_bytes;
    END IF;
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(following->'components') r
      WHERE r->>'sha256'=digest) THEN
      next_total:=next_total+component_bytes;
    END IF;
    IF prior_total>262144 OR next_total>262144 THEN
      RAISE EXCEPTION 'checkpoint_dependency_capacity' USING ERRCODE='22023';
    END IF;
    -- FOUND must be captured by the row value; the capacity probes above also
    -- execute SQL and would overwrite PL/pgSQL's implicit FOUND flag.
    IF stored IS NOT NULL THEN
      entry:=vn_portable_dependency_research.block(stored,owner_id,run_id);
      IF entry->>'sha256'<>digest OR
         (supplied ? digest AND supplied#>>ARRAY[digest,'wire'] IS DISTINCT FROM stored) THEN
        RAISE EXCEPTION 'checkpoint_retained_component_mismatch' USING ERRCODE='22023';
      END IF;
      retained:=retained||jsonb_build_object(digest,entry);
    END IF;
  END LOOP;
  -- Supplied blocks may only satisfy FOLLOWING references, never repair a lost prior.
  IF previous IS NOT NULL THEN
    prior_result:=vn_portable_dependency_research.expand(previous,retained,owner_id,run_id,current.revision);
  END IF;
  FOR ref IN SELECT k FROM jsonb_object_keys(supplied) k LOOP
    IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(following->'components') r
      WHERE r->>'sha256'=ref.k) THEN
      RAISE EXCEPTION 'checkpoint_unused_supplied_component' USING ERRCODE='22023';
    END IF;
    retained:=retained||jsonb_build_object(ref.k,supplied->ref.k);
  END LOOP;
  next_result:=vn_portable_dependency_research.expand(following,retained,owner_id,run_id,next_revision);
  next_generation:=vn_portable_dependency_research.counter(following#>'{engine,generation}',0,2147483647);
  IF previous IS NULL THEN
    IF next_generation<>0 THEN
      RAISE EXCEPTION 'checkpoint_bootstrap_generation' USING ERRCODE='22023';
    END IF;
  ELSE
    prior_generation:=vn_portable_dependency_research.counter(previous#>'{engine,generation}',0,2147483647);
    IF next_generation<prior_generation OR next_generation>prior_generation+1 OR
       previous->>'status' IN ('stopped','failed') OR
       NOT EXISTS(SELECT 1 FROM jsonb_array_elements(following->'components') n,
         jsonb_array_elements(previous->'components') p
         WHERE n->>'kind'='configuration' AND p->>'kind'='configuration' AND n=p) THEN
      RAISE EXCEPTION 'checkpoint_prior_model_binding' USING ERRCODE='22023';
    END IF;
  END IF;
  RETURN jsonb_build_object('format','ga-portable-locked-resolution-research-v2',
    'command_sha256',audited->'sha256','prior',prior_result,'following',next_result,
    'full_semantic_authority',false,'native_admission_authority',false,'restoration_authority',false);
END $function$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_portable_dependency_research FROM PUBLIC;
