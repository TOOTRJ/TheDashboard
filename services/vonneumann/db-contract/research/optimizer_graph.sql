-- Offline GA graph/mirror proof. This never constructs Python objects.
DO $guard$ BEGIN
 IF current_setting('dashboard.optimizer_graph_fixture',true) IS DISTINCT FROM 'offline-v1'
    OR to_regprocedure('vn_assessment_research.validate_request(uuid,uuid,text)') IS NULL THEN
  RAISE EXCEPTION 'offline_optimizer_graph_fixture_required' USING ERRCODE='22023';
 END IF;
END $guard$;
CREATE SCHEMA vn_optimizer_research;
REVOKE ALL ON SCHEMA vn_optimizer_research FROM PUBLIC;

CREATE FUNCTION vn_optimizer_research.fields(name text) RETURNS text[]
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $function$
 SELECT CASE name
 WHEN 'GeneticAlgorithmStrategy' THEN ARRAY['_search_streams','_search_epoch','_rng','_mutation_event','mutation_rate','mutation_strength','_cohort']
 WHEN 'SearchRandomStreams' THEN ARRAY['seed','algorithm']
 WHEN 'SelectionCohort' THEN ARRAY['population_size','bound_ids','_signatures','_pending','_previous_ids','_previous_context','_bootstrap']
 WHEN 'Genome' THEN ARRAY['rsi_period','rsi_oversold','rsi_overbought','ema_fast','ema_slow','volume_threshold','position_size_pct','stop_loss_pct',
  'take_profit_pct','max_open_positions','timeframe_minutes','benchmark_target_pct','reproduce_target_dollars','death_drawdown_pct','num_assets','assets','generation','parent_ids']
 WHEN 'EvaluatedCandidate' THEN ARRAY['probe_id','evaluation_id','iteration_id','_genome','fitness','roi','num_trades','reason','status','window_started_at','window_ends_at','terminated_at','cohort_complete']
 WHEN 'EvaluationCohort' THEN ARRAY['horizon_seconds','iteration_id','member_ids','_genomes','_evaluation_ids','_evaluations','phase','started_at','ends_at','completed_at','abort_reason'] END
$function$;

CREATE FUNCTION vn_optimizer_research.walk(value jsonb,ctx jsonb,depth integer) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE typ text:=jsonb_typeof(value); kind text; node_id integer; pointer jsonb; body jsonb; output jsonb; entry record;
 keys text[]; key text; count integer:=(ctx->>'visits')::integer+1; seen text[]:=ARRAY[]::text[];
BEGIN
 IF depth>24 OR count>4096 THEN RAISE EXCEPTION 'optimizer_graph_capacity' USING ERRCODE='22023'; END IF;
 ctx:=ctx||jsonb_build_object('visits',count);
 IF typ IN ('null','boolean','string') THEN
  IF typ='string' AND octet_length(value#>>'{}')>4096 THEN RAISE EXCEPTION 'optimizer_string_capacity' USING ERRCODE='22023'; END IF;
  RETURN ctx||jsonb_build_object('value',value);
 END IF;
 IF typ<>'object' THEN RAISE EXCEPTION 'optimizer_typed_value_required' USING ERRCODE='22023'; END IF;
 IF value ? 'ref' THEN
  PERFORM vn_dependency_research.exact_keys(value,ARRAY['ref']);
  node_id:=vn_dependency_research.counter(value->'ref',0,255); body:=ctx#>ARRAY['nodes',node_id::text];
  -- The GA copier has no mutable/nonempty compound aliases. Its shared empty
  -- tuples are legitimate immutable sentinels. No active/forward ref is legal.
  IF body IS NULL OR body->>'type'<>'tuple' OR body->'items'<>'[]'::jsonb THEN
   RAISE EXCEPTION 'optimizer_unreviewed_alias_or_cycle' USING ERRCODE='22023'; END IF;
  RETURN ctx||jsonb_build_object('value',jsonb_build_object('$node',node_id));
 END IF;
 kind:=value->>'type';
 IF kind='integer' THEN
  PERFORM vn_dependency_research.exact_keys(value,ARRAY['type','decimal']);
  IF jsonb_typeof(value->'decimal') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'optimizer_integer_type' USING ERRCODE='22023'; END IF;
  PERFORM vn_numeric_research.integer_text(value->>'decimal');
  RETURN ctx||jsonb_build_object('value',jsonb_build_object('$integer',value->'decimal'));
 ELSIF kind='float' THEN
  PERFORM vn_dependency_research.exact_keys(value,ARRAY['type','hex']);
  PERFORM vn_source_research.ratio(value->'hex');
  RETURN ctx||jsonb_build_object('value',jsonb_build_object('float64',value->'hex'));
 END IF;
 node_id:=vn_dependency_research.counter(value->'node',0,255);
 IF node_id<>(ctx->>'next')::integer THEN RAISE EXCEPTION 'optimizer_node_order' USING ERRCODE='22023'; END IF;
 ctx:=ctx||jsonb_build_object('next',node_id+1); pointer:=jsonb_build_object('$node',node_id);
 IF kind IN ('list','tuple') THEN
  PERFORM vn_dependency_research.exact_keys(value,ARRAY['node','type','items']);
  IF jsonb_typeof(value->'items') IS DISTINCT FROM 'array' OR jsonb_array_length(value->'items')>16 THEN
   RAISE EXCEPTION 'optimizer_sequence_capacity' USING ERRCODE='22023'; END IF;
  output:='[]';
  FOR entry IN SELECT v FROM jsonb_array_elements(value->'items') a(v) LOOP
   ctx:=vn_optimizer_research.walk(entry.v,ctx,depth+1); output:=output||jsonb_build_array(ctx->'value');
  END LOOP;
  IF kind='tuple' AND output='[]'::jsonb THEN
   IF ctx ? 'empty_tuple' THEN RAISE EXCEPTION 'optimizer_duplicate_empty_tuple' USING ERRCODE='22023'; END IF;
   ctx:=ctx||jsonb_build_object('empty_tuple',node_id);
  END IF;
  body:=jsonb_build_object('type',kind,'items',output);
 ELSIF kind='map' THEN
  PERFORM vn_dependency_research.exact_keys(value,ARRAY['node','type','entries']);
  IF jsonb_typeof(value->'entries') IS DISTINCT FROM 'array' OR jsonb_array_length(value->'entries')>32 THEN
   RAISE EXCEPTION 'optimizer_map_capacity' USING ERRCODE='22023'; END IF;
  output:='[]';
  FOR entry IN SELECT v FROM jsonb_array_elements(value->'entries') a(v) LOOP
   IF jsonb_typeof(entry.v) IS DISTINCT FROM 'array' OR jsonb_array_length(entry.v)<>2 OR jsonb_typeof(entry.v->0) IS DISTINCT FROM 'string' THEN
    RAISE EXCEPTION 'optimizer_map_entry' USING ERRCODE='22023'; END IF;
   key:=entry.v->>0;
   IF octet_length(key)>4096 OR key=ANY(seen) THEN RAISE EXCEPTION 'optimizer_map_key' USING ERRCODE='22023'; END IF;
   seen:=array_append(seen,key); ctx:=vn_optimizer_research.walk(entry.v->1,ctx,depth+1);
   output:=output||jsonb_build_array(jsonb_build_array(key,ctx->'value'));
  END LOOP;
  body:=jsonb_build_object('type',kind,'entries',output);
 ELSIF kind='object' THEN
  PERFORM vn_dependency_research.exact_keys(value,ARRAY['node','type','class','fields']);
  keys:=vn_optimizer_research.fields(value->>'class');
  IF keys IS NULL THEN RAISE EXCEPTION 'optimizer_class_not_allowed' USING ERRCODE='22023'; END IF;
  PERFORM vn_dependency_research.exact_keys(value->'fields',keys); output:='{}';
  FOR entry IN SELECT e.key,e.value FROM jsonb_each(value->'fields') e ORDER BY e.key COLLATE "C" LOOP
   ctx:=vn_optimizer_research.walk(entry.value,ctx,depth+1); output:=output||jsonb_build_object(entry.key,ctx->'value');
  END LOOP;
  body:=jsonb_build_object('type',kind,'class',value->'class','fields',output);
  IF value->>'class'='Genome' THEN
   PERFORM vn_optimizer_research.node(ctx,output->'assets','list');
   PERFORM vn_optimizer_research.node(ctx,output->'parent_ids','list');
  ELSIF value->>'class'='EvaluatedCandidate' THEN
   PERFORM vn_optimizer_research.node(ctx,output->'_genome','object','Genome');
  END IF;
 ELSIF kind='python.Random' THEN
  PERFORM vn_dependency_research.exact_keys(value,ARRAY['node','type','algorithm','state_version','words','index','gaussian_hex']);
  IF value->>'algorithm' IS DISTINCT FROM 'MT19937' OR value->'state_version' IS DISTINCT FROM vn_source_research.tag(3)
     OR value->'gaussian_hex' IS DISTINCT FROM 'null'::jsonb OR jsonb_typeof(value->'words') IS DISTINCT FROM 'array'
     OR jsonb_array_length(value->'words')<>624 THEN RAISE EXCEPTION 'optimizer_rng_shape' USING ERRCODE='22023'; END IF;
  PERFORM vn_dependency_research.counter(value->'index',0,624);
  FOR entry IN SELECT v FROM jsonb_array_elements(value->'words') a(v) LOOP PERFORM vn_dependency_research.counter(entry.v,0,4294967295); END LOOP;
  body:=value-'node';
 ELSE RAISE EXCEPTION 'optimizer_type_not_allowed' USING ERRCODE='22023'; END IF;
 ctx:=jsonb_set(ctx,'{nodes}',(ctx->'nodes')||jsonb_build_object(node_id::text,body));
 RETURN ctx||jsonb_build_object('value',pointer);
END $function$;

CREATE FUNCTION vn_optimizer_research.graph(value jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE ctx jsonb:='{"nodes":{},"next":0,"visits":0}'; strategy jsonb;
BEGIN
 PERFORM vn_dependency_research.exact_keys(value,ARRAY['version','software','strategy','cohort']);
 IF value->>'version' IS DISTINCT FROM 'optimizer-evidence-v1' OR value->'software' IS DISTINCT FROM
    '{"python":"3.12.14","numpy":"2.5.3","cmaes":"0.13.1"}'::jsonb THEN
  RAISE EXCEPTION 'optimizer_software_or_version' USING ERRCODE='22023'; END IF;
 ctx:=vn_optimizer_research.walk(value->'strategy',ctx,0); strategy:=ctx->'value';
 ctx:=vn_optimizer_research.walk(value->'cohort',ctx,0);
 RETURN ctx||jsonb_build_object('strategy',strategy,'cohort',ctx->'value');
END $function$;

CREATE FUNCTION vn_optimizer_research.node(graph jsonb,value jsonb,kind text,name text DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE body jsonb;
BEGIN
 PERFORM vn_dependency_research.exact_keys(value,ARRAY['$node']); body:=graph#>ARRAY['nodes',value->>'$node'];
 IF body IS NULL OR body->>'type' IS DISTINCT FROM kind OR (name IS NOT NULL AND body->>'class' IS DISTINCT FROM name) THEN
  RAISE EXCEPTION 'optimizer_field_role' USING ERRCODE='22023'; END IF;
 RETURN body;
END $function$;

CREATE FUNCTION vn_optimizer_research.plain(graph jsonb,value jsonb,depth integer DEFAULT 0) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE body jsonb; result jsonb; entry record;
BEGIN
 IF depth>24 THEN RAISE EXCEPTION 'optimizer_plain_capacity' USING ERRCODE='22023'; END IF;
 IF NOT (jsonb_typeof(value)='object' AND value ? '$node') THEN RETURN value; END IF;
 body:=graph#>ARRAY['nodes',value->>'$node'];
 IF body->>'type' IN ('list','tuple') THEN
  result:='[]'; FOR entry IN SELECT v FROM jsonb_array_elements(body->'items') a(v) LOOP
   result:=result||jsonb_build_array(vn_optimizer_research.plain(graph,entry.v,depth+1)); END LOOP;
 ELSIF body->>'type'='map' THEN
  result:='{}'; FOR entry IN SELECT v FROM jsonb_array_elements(body->'entries') a(v) LOOP
   result:=result||jsonb_build_object(entry.v->>0,vn_optimizer_research.plain(graph,entry.v->1,depth+1)); END LOOP;
 ELSIF body->>'type'='object' THEN
  result:='{}'; FOR entry IN SELECT * FROM jsonb_each(body->'fields') LOOP
   result:=result||jsonb_build_object(entry.key,vn_optimizer_research.plain(graph,entry.value,depth+1)); END LOOP;
  result:=jsonb_build_object('class',body->'class','fields',result);
 ELSE result:=body; END IF;
 IF octet_length(result::text)>196608 THEN RAISE EXCEPTION 'optimizer_plain_bytes' USING ERRCODE='22023'; END IF;
 RETURN result;
END $function$;

CREATE FUNCTION vn_optimizer_research.map_order(graph jsonb,value jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $function$
 SELECT coalesce(jsonb_agg(v->0 ORDER BY ordinal),'[]') FROM jsonb_array_elements(
   vn_optimizer_research.node(graph,value,'map')->'entries') WITH ORDINALITY a(v,ordinal)
$function$;

CREATE FUNCTION vn_optimizer_research.genome(value jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE result jsonb:=value; entry record;
BEGIN
 FOR entry IN SELECT * FROM jsonb_each(value-ARRAY['assets','generation','parent_ids']) LOOP
  PERFORM vn_source_research.ratio(entry.value); result:=jsonb_set(result,ARRAY[entry.key],jsonb_build_object('float64',entry.value));
 END LOOP;
 RETURN jsonb_build_object('class','Genome','fields',result);
END $function$;

CREATE FUNCTION vn_optimizer_research.mirrors(state jsonb,graph jsonb,expected_order jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE root jsonb; fields jsonb; cohort jsonb:=state#>'{engine,cohort}'; expected jsonb; genomes jsonb:='{}'; ids jsonb; evaluations jsonb:='{}';
 member jsonb; row jsonb; key text; id text; eval_ids jsonb:='{}'; ordinal integer:=0; evaluation_order jsonb:='[]';
BEGIN
 root:=vn_optimizer_research.node(graph,graph->'cohort','object','EvaluationCohort'); fields:=root->'fields';
 ids:=cohort->'member_ids';
 PERFORM vn_optimizer_research.node(graph,fields->'member_ids','tuple');
 PERFORM vn_optimizer_research.node(graph,fields->'_genomes','map');
 PERFORM vn_optimizer_research.node(graph,fields->'_evaluation_ids','map');
 PERFORM vn_optimizer_research.node(graph,fields->'_evaluations','map');
 FOR member IN SELECT v FROM jsonb_array_elements(state#>'{engine,members}') a(v) LOOP
  id:=member->>'id'; genomes:=genomes||jsonb_build_object(id,vn_optimizer_research.genome(member->'genome'));
  eval_ids:=eval_ids||jsonb_build_object(id,(cohort->>'iteration_id')||':'||ordinal::text); ordinal:=ordinal+1;
 END LOOP;
 FOR row IN SELECT v FROM jsonb_array_elements(cohort->'evaluations') a(v) LOOP
  id:=row->>'probe_id'; evaluations:=evaluations||jsonb_build_object(id,jsonb_build_object('class','EvaluatedCandidate',
   'fields',(row-'cohort_complete')||jsonb_build_object('cohort_complete',row->'cohort_complete','_genome',genomes->id)));
  evaluation_order:=evaluation_order||jsonb_build_array(id);
 END LOOP;
 expected:=(cohort-ARRAY['policy','member_count','completed_count','evaluations'])||jsonb_build_object('_genomes',genomes,
  '_evaluation_ids',eval_ids,'_evaluations',evaluations);
 IF vn_optimizer_research.plain(graph,graph->'cohort') IS DISTINCT FROM jsonb_build_object('class','EvaluationCohort','fields',expected)
    OR vn_optimizer_research.map_order(graph,fields->'_genomes') IS DISTINCT FROM ids
    OR vn_optimizer_research.map_order(graph,fields->'_evaluation_ids') IS DISTINCT FROM ids
    OR vn_optimizer_research.map_order(graph,fields->'_evaluations') IS DISTINCT FROM expected_order THEN
  RAISE EXCEPTION 'optimizer_evaluation_mirror' USING ERRCODE='22023'; END IF;
 RETURN graph;
END $function$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_optimizer_research FROM PUBLIC;
