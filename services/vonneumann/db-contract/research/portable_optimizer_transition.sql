-- Offline graph, mirrors, founder/restart phenotypes, selection RNG and ancestry.
-- Original-v2 offspring periods are independently derived with the bound integer operator.
DO $guard$ BEGIN
 IF current_setting('dashboard.portable_optimizer_transition_fixture',true) IS DISTINCT FROM 'offline-v2'
    OR to_regprocedure('vn_portable_optimizer_research.same_rng(jsonb,jsonb)') IS NULL THEN
  RAISE EXCEPTION 'offline_portable_optimizer_transition_fixture_required' USING ERRCODE='22023';
 END IF;
END $guard$;

CREATE FUNCTION vn_portable_optimizer_research.profile(value jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE fixed jsonb:='{"rsi_period":"0x1.c000000000000p+3","rsi_oversold":"0x1.0000000000000p+5","rsi_overbought":"0x1.1800000000000p+6", "volume_threshold":"0x1.6666666666666p+0","position_size_pct":"0x1.0000000000000p-2","stop_loss_pct":"0x1.eb851eb851eb8p-6","take_profit_pct":"0x1.1eb851eb851ecp-4","max_open_positions":"0x1.0000000000000p+0","timeframe_minutes":"0x1.e000000000000p+3","benchmark_target_pct":"0x1.47ae147ae147bp-4","reproduce_target_dollars":"0x1.4000000000000p+3","death_drawdown_pct":"0x1.999999999999ap-3","num_assets":"0x1.0000000000000p+0"}';
 fast numeric[]; slow numeric[];
BEGIN
 PERFORM vn_portable_dependency_research.exact_keys(value,vn_portable_optimizer_research.fields('Genome'));
 fast:=vn_portable_source_research.ratio(value->'ema_fast'); slow:=vn_portable_source_research.ratio(value->'ema_slow');
 IF value-ARRAY['ema_fast','ema_slow','assets','generation','parent_ids'] IS DISTINCT FROM fixed
    OR mod(fast[1],fast[2])<>0 OR fast[1]<fast[2]*3 OR fast[1]>fast[2]*12
    OR mod(slow[1],slow[2])<>0 OR slow[1]<slow[2]*15 OR slow[1]>slow[2]*60
    OR value->'assets' IS DISTINCT FROM '["SOL/USD"]'::jsonb
    OR jsonb_typeof(value->'parent_ids') IS DISTINCT FROM 'array' OR jsonb_array_length(value->'parent_ids')>2 THEN
  RAISE EXCEPTION 'optimizer_phenotype_controls' USING ERRCODE='22023'; END IF;
 PERFORM vn_portable_dependency_research.counter(value->'generation',0,2147483647);
 RETURN value;
END $function$;

CREATE FUNCTION vn_portable_optimizer_research.strategy(graph jsonb,state jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE raw jsonb:=vn_portable_optimizer_research.node(graph,graph->'strategy','object','GeneticAlgorithmStrategy')->'fields';
 result jsonb:=vn_portable_optimizer_research.plain(graph,graph->'strategy')->'fields'; selection jsonb;
BEGIN
 PERFORM vn_portable_optimizer_research.node(graph,raw->'_search_streams','object','SearchRandomStreams');
 selection:=vn_portable_optimizer_research.node(graph,raw->'_cohort','object','SelectionCohort')->'fields';
 PERFORM vn_portable_optimizer_research.node(graph,selection->'bound_ids','tuple');
 PERFORM vn_portable_optimizer_research.node(graph,selection->'_previous_ids','tuple');
 PERFORM vn_portable_optimizer_research.node(graph,selection->'_signatures','map');
 IF selection->'_previous_context'<>'null'::jsonb THEN PERFORM vn_portable_optimizer_research.node(graph,selection->'_previous_context','tuple'); END IF;
 IF result->'mutation_rate' IS DISTINCT FROM '{"float64":"0x1.999999999999ap-3"}'::jsonb OR
    result->'mutation_strength' IS DISTINCT FROM '{"float64":"0x1.3333333333333p-3"}'::jsonb OR
    result->'_search_streams' IS DISTINCT FROM jsonb_build_object('class','SearchRandomStreams','fields',
      jsonb_build_object('seed',state#>'{engine,config,search_seed}','algorithm','genetic_algorithm')) OR
    result->'_search_epoch' IS DISTINCT FROM state#>'{engine,lifecycle,search_epoch}' OR
    result#>'{_cohort,fields,_pending}' IS DISTINCT FROM 'null'::jsonb THEN
  RAISE EXCEPTION 'optimizer_strategy_controls' USING ERRCODE='22023'; END IF;
 PERFORM vn_portable_dependency_research.counter(result->'_mutation_event',0,2147483647);
 RETURN result||jsonb_build_object('rng',vn_portable_optimizer_research.rng(graph,raw->'_rng'));
END $function$;

CREATE FUNCTION vn_portable_optimizer_research.tournament(state jsonb,ids jsonb,scores jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE row jsonb; best text; score numeric[]; incumbent numeric[];
BEGIN
 state:=vn_portable_optimizer_research.sample(state,ids,3);
 FOR row IN SELECT v FROM jsonb_array_elements(state->'sample') a(v) LOOP
  score:=vn_portable_source_research.ratio(scores->(row#>>'{}'));
  IF best IS NULL OR score[1]*incumbent[2]>incumbent[1]*score[2] THEN best:=row#>>'{}'; incumbent:=score; END IF;
 END LOOP;
 RETURN state||jsonb_build_object('winner',best);
END $function$;

CREATE FUNCTION vn_portable_optimizer_research.selection(state jsonb,ids jsonb,scores jsonb,genomes jsonb,generation jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE pair integer; child integer; parent text; mate text; pool jsonb; sexual boolean; operation text; parents jsonb;
 threshold numeric[]:=vn_portable_source_research.ratio('"0x1.3333333333333p-2"');
 operations jsonb:='[]'; templates jsonb:='[]'; a jsonb; b jsonb; key text; row jsonb;
BEGIN
 FOR pair IN 0..3 LOOP
  state:=vn_portable_optimizer_research.tournament(state,ids,scores); parent:=state->>'winner';
  SELECT jsonb_agg(v ORDER BY ordinal) INTO pool FROM jsonb_array_elements(ids) WITH ORDINALITY t(v,ordinal) WHERE v<>to_jsonb(parent);
  state:=vn_portable_optimizer_research.tournament(state,pool,scores); mate:=state->>'winner';
  state:=vn_portable_optimizer_research.mt_random(state);
  sexual:=(state->>'numerator')::numeric*threshold[2]>threshold[1]*9007199254740992;
  operation:=CASE WHEN sexual THEN 'crossover_mutation' ELSE 'clone_mutation' END;
  parents:=jsonb_build_array(parent); IF sexual THEN parents:=parents||jsonb_build_array(mate); END IF;
  a:=(genomes->parent)||jsonb_build_object('generation',generation,'parent_ids',parents); b:=a;
  IF sexual THEN
   FOREACH key IN ARRAY ARRAY['ema_fast','ema_slow'] LOOP
    state:=vn_portable_optimizer_research.mt_random(state);
    IF (state->>'numerator')::numeric>4503599627370496 THEN b:=jsonb_set(b,ARRAY[key],genomes#>ARRAY[mate,key]);
    ELSE a:=jsonb_set(a,ARRAY[key],genomes#>ARRAY[mate,key]); END IF;
   END LOOP;
   -- Both children sample the fixed one-asset pool. randbelow(1) still consumes
   -- rejection draws; omitting these would corrupt the following tournament.
   state:=vn_portable_optimizer_research.randbelow(state,1); state:=vn_portable_optimizer_research.randbelow(state,1);
  END IF;
  templates:=templates||jsonb_build_array(a,b);
  FOR child IN pair*2..pair*2+1 LOOP operations:=operations||jsonb_build_array(jsonb_build_object(
   'offspring_index',vn_portable_source_research.tag(child),'operation',operation,'parent_ids',parents)); END LOOP;
 END LOOP;
 RETURN jsonb_build_object('rng',state,'offspring',operations,'templates',templates);
END $function$;

CREATE FUNCTION vn_portable_optimizer_research.transition(request jsonb,previous jsonb,following jsonb,causal jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE graph jsonb:=vn_portable_optimizer_research.graph(following#>'{engine,optimizer}'); old_graph jsonb; strategy jsonb; old_strategy jsonb;
 cohort jsonb:=following#>'{engine,cohort}'; old_cohort jsonb; expected jsonb; expected_selection jsonb; selection_fields jsonb;
 ids jsonb:=cohort->'member_ids'; old_ids jsonb; order_ids jsonb:='[]'; sigs jsonb:='{}'; scores jsonb:='{}'; genomes jsonb:='{}';
 member jsonb; row jsonb; record jsonb; id text; ordinal integer:=0; generation jsonb:=following#>'{engine,generation}';
 event bigint; rng jsonb; proposed jsonb; selection jsonb:='null'; lineage jsonb; operation jsonb; birth_index integer:=0; sources jsonb;
 changed boolean:=false; replaced boolean:=(causal->>'replaced')::boolean; restart boolean:=(causal->>'restart')::boolean;
 finalized jsonb:=causal#>'{trace,finalized}'; template jsonb; founder_rng jsonb; period bigint; mutated jsonb; fast numeric[]; slow numeric[];
BEGIN
 strategy:=vn_portable_optimizer_research.strategy(graph,following);
 IF previous IS NOT NULL THEN
  old_graph:=vn_portable_optimizer_research.graph(previous#>'{engine,optimizer}'); old_strategy:=vn_portable_optimizer_research.strategy(old_graph,previous);
  old_cohort:=previous#>'{engine,cohort}'; old_ids:=old_cohort->'member_ids'; changed:=replaced OR restart;
  order_ids:=vn_portable_optimizer_research.map_order(old_graph,vn_portable_optimizer_research.node(old_graph,old_graph->'cohort','object','EvaluationCohort')#>'{fields,_evaluations}');
  PERFORM vn_portable_optimizer_research.mirrors(previous,old_graph,order_ids);
  FOR row IN SELECT v FROM jsonb_array_elements(old_ids) a(v) LOOP
   IF causal#>'{trace,frozen}' ? (row#>>'{}') THEN order_ids:=order_ids||jsonb_build_array(row); END IF;
  END LOOP;
  IF finalized<>'null'::jsonb THEN
   FOR row IN SELECT v FROM jsonb_array_elements(old_ids) a(v) LOOP
    IF NOT order_ids @> jsonb_build_array(row) THEN order_ids:=order_ids||jsonb_build_array(row); END IF;
   END LOOP;
  END IF;
  IF changed THEN order_ids:='[]'; END IF;
 END IF;
 PERFORM vn_portable_optimizer_research.mirrors(following,graph,order_ids);
 FOR member IN SELECT v FROM jsonb_array_elements(following#>'{engine,members}') a(v) LOOP
  PERFORM vn_portable_optimizer_research.profile(member->'genome'); id:=member->>'id';
  sigs:=sigs||jsonb_build_object(id,(vn_portable_optimizer_research.genome(member->'genome')->'fields')-'parent_ids');
 END LOOP;
 IF previous IS NULL OR restart THEN
  event:=0; rng:=vn_portable_optimizer_research.namespaced(following#>>'{engine,config,search_seed}','strategy',
    vn_portable_dependency_research.counter(following#>'{engine,lifecycle,search_epoch}',0,2147483647));
  expected_selection:=jsonb_build_object('population_size',vn_portable_source_research.tag(8),'bound_ids',ids,'_signatures',sigs,
   '_pending',NULL,'_previous_ids','[]'::jsonb,'_previous_context',NULL,'_bootstrap',true);
 ELSE
  event:=vn_portable_dependency_research.counter(old_strategy->'_mutation_event',0,2147483647); rng:=old_strategy->'rng';
  expected_selection:=old_strategy#>'{_cohort,fields}';
  IF replaced THEN
   FOR member IN SELECT v FROM jsonb_array_elements(previous#>'{engine,members}') a(v) LOOP genomes:=genomes||jsonb_build_object(member->>'id',member->'genome'); END LOOP;
   FOR record IN SELECT v FROM jsonb_array_elements(request#>'{history,assessments}') a(v) LOOP scores:=scores||jsonb_build_object(record->>'probe_id',record->'fitness_float64'); END LOOP;
   proposed:=vn_portable_optimizer_research.selection(rng,old_ids,scores,genomes,generation); rng:=proposed->'rng'; event:=event+1;
   selection:=jsonb_build_object('selection_policy','completed-window-generational-ga-v1','iteration_id',old_cohort->'iteration_id',
    'evaluation_accounts',vn_portable_source_research.tag(8),'offspring',proposed->'offspring',
    'mutation_operator','ema-period-triangular-integer-v1');
   expected_selection:=jsonb_build_object('population_size',vn_portable_source_research.tag(8),'bound_ids',ids,'_signatures',sigs,
    '_pending',NULL,'_previous_ids',old_ids,'_previous_context',jsonb_build_array(old_cohort->'iteration_id',old_cohort->'started_at',old_cohort->'ends_at'),'_bootstrap',false);
  ELSIF finalized<>'null'::jsonb AND (finalized->>'aborted')::boolean THEN
   expected_selection:=jsonb_build_object('population_size',vn_portable_source_research.tag(0),'bound_ids','[]'::jsonb,'_signatures','{}'::jsonb,
    '_pending',NULL,'_previous_ids','[]'::jsonb,'_previous_context',NULL,'_bootstrap',false);
  END IF;
 END IF;
 selection_fields:=strategy#>'{_cohort,fields}';
 IF strategy->'_mutation_event' IS DISTINCT FROM vn_portable_source_research.tag(event) OR selection_fields IS DISTINCT FROM expected_selection
    OR NOT vn_portable_optimizer_research.same_rng(rng,strategy->'rng') OR request#>'{history,selection}' IS DISTINCT FROM selection THEN
  RAISE EXCEPTION 'optimizer_continuation_or_selection' USING ERRCODE='22023'; END IF;
 IF vn_portable_optimizer_research.map_order(graph,vn_portable_optimizer_research.node(graph,
    vn_portable_optimizer_research.node(graph,graph->'strategy','object','GeneticAlgorithmStrategy')#>'{fields,_cohort}','object','SelectionCohort')#>'{fields,_signatures}')
    IS DISTINCT FROM selection_fields->'bound_ids' THEN RAISE EXCEPTION 'optimizer_signature_order' USING ERRCODE='22023'; END IF;
 FOR member IN SELECT v FROM jsonb_array_elements(following#>'{engine,members}') a(v) LOOP
  IF previous IS NULL THEN
   founder_rng:=vn_portable_optimizer_research.namespaced(following#>>'{engine,config,search_seed}','gen0',0,jsonb_build_array(vn_portable_source_research.tag(ordinal)));
   founder_rng:=vn_portable_optimizer_research.randbelow(founder_rng,10); period:=(founder_rng->>'choice')::bigint+3;
   template:=jsonb_set(member->'genome','{ema_fast}',vn_portable_source_research.round_ratio(period,1)->'$binary64');
   founder_rng:=vn_portable_optimizer_research.randbelow(founder_rng,46); period:=(founder_rng->>'choice')::bigint+15;
   template:=jsonb_set(template,'{ema_slow}',vn_portable_source_research.round_ratio(period,1)->'$binary64');
   template:=template||jsonb_build_object('parent_ids','[]'::jsonb);
   lineage:=jsonb_build_object('version',vn_portable_source_research.tag(1),'child_id',member->'id','strategy','genetic_algorithm','operation','founder',
    'source_iteration_id',NULL,'offspring_index',NULL,'sources','[]'::jsonb,'distribution_id',NULL);
  ELSIF restart THEN
   row:=previous#>ARRAY['engine','members',ordinal::text];
   template:=(row->'genome')||jsonb_build_object('generation',generation,'parent_ids',jsonb_build_array(row->'id'));
   sources:=jsonb_build_array(jsonb_build_object('role','clone_source','source_id',row->'id','ordinal',vn_portable_source_research.tag(0)),
    jsonb_build_object('role','asset_template','source_id',row->'id','ordinal',vn_portable_source_research.tag(0)));
   lineage:=jsonb_build_object('version',vn_portable_source_research.tag(2),'child_id',member->'id','strategy','genetic_algorithm','operation','restart_clone',
    'source_iteration_id',old_cohort->'iteration_id','offspring_index',vn_portable_source_research.tag(ordinal),'sources',sources,'distribution_id',NULL);
  ELSIF replaced THEN
   row:=proposed->'offspring'->ordinal; template:=proposed->'templates'->ordinal;
   -- Derive both periods solely from the server-accepted prior, actual
   -- tournament/crossover template and original per-child namespace. Supplied
   -- child periods never enter the derivation, even when every mirror agrees.
   fast:=vn_portable_source_research.ratio(template->'ema_fast');
   slow:=vn_portable_source_research.ratio(template->'ema_slow');
   mutated:=vn_portable_optimizer_research.portable_periods((fast[1]/fast[2])::integer,(slow[1]/slow[2])::integer,
    following#>>'{engine,config,search_seed}',vn_portable_dependency_research.counter(old_strategy->'_search_epoch',0,2147483647),
    event-1,ordinal,row->>'operation'='crossover_mutation');
   template:=template||jsonb_build_object('ema_fast',vn_portable_source_research.round_ratio(
    vn_portable_dependency_research.counter(mutated->'ema_fast',3,12),1)->'$binary64',
    'ema_slow',vn_portable_source_research.round_ratio(vn_portable_dependency_research.counter(mutated->'ema_slow',15,60),1)->'$binary64');
   sources:='[]'; birth_index:=0;
   FOR record IN SELECT v FROM jsonb_array_elements(row->'parent_ids') a(v) LOOP
    sources:=sources||jsonb_build_array(jsonb_build_object('role','genetic_parent','source_id',record,'ordinal',vn_portable_source_research.tag(birth_index))); birth_index:=birth_index+1;
   END LOOP;
   lineage:=jsonb_build_object('version',vn_portable_source_research.tag(1),'child_id',member->'id','strategy','genetic_algorithm','operation',row->'operation',
    'source_iteration_id',old_cohort->'iteration_id','offspring_index',vn_portable_source_research.tag(ordinal),'sources',sources,'distribution_id',NULL);
  ELSE
   row:=previous#>ARRAY['engine','members',ordinal::text]; template:=row->'genome'; lineage:=NULL;
   IF member->'name' IS DISTINCT FROM row->'name' THEN RAISE EXCEPTION 'optimizer_member_name_changed' USING ERRCODE='22023'; END IF;
  END IF;
  IF member->'genome' IS DISTINCT FROM template THEN RAISE EXCEPTION 'optimizer_genotype_or_parent_mismatch' USING ERRCODE='22023'; END IF;
  IF previous IS NULL OR changed THEN
   IF request#>ARRAY['evidence','inputs','names',ordinal::text] IS DISTINCT FROM jsonb_build_array(generation,member->'name') THEN
    RAISE EXCEPTION 'optimizer_name_allocation' USING ERRCODE='22023'; END IF;
   SELECT v INTO operation FROM jsonb_array_elements(request->'operations') a(v) WHERE v->>'kind'='birth' AND v->'id'=member->'id';
   IF operation->'lineage' IS DISTINCT FROM lineage THEN RAISE EXCEPTION 'optimizer_lineage_mismatch' USING ERRCODE='22023'; END IF;
  END IF;
  ordinal:=ordinal+1;
 END LOOP;
 RETURN jsonb_build_object('graph_nodes',vn_portable_source_research.tag((graph->>'next')::integer),'strategy_draws',vn_portable_source_research.tag((rng->>'draws')::integer),
  'selection_rng_and_parentage_verified',true,'completed_offspring_mutation_verified',true,'restoration_authority',false);
END $function$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_portable_optimizer_research FROM PUBLIC;
