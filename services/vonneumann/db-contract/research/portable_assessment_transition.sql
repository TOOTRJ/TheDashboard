-- Offline independent assessment/common-window proof. No restore or writer.
DO $guard$ BEGIN
 IF current_setting('dashboard.portable_assessment_fixture',true) IS DISTINCT FROM 'offline-v2'
    OR to_regprocedure('vn_portable_causal_research.transition(jsonb,jsonb,jsonb)') IS NULL THEN
  RAISE EXCEPTION 'offline_portable_assessment_fixture_required' USING ERRCODE='22023';
 END IF;
END $guard$;
CREATE SCHEMA vn_portable_assessment_research;
REVOKE ALL ON SCHEMA vn_portable_assessment_research FROM PUBLIC;

CREATE FUNCTION vn_portable_assessment_research.float_view(value jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $function$
 SELECT CASE WHEN value IS NULL OR value='null'::jsonb THEN 'null'::jsonb
  ELSE jsonb_build_object('float64',value->'$binary64') END
$function$;

CREATE FUNCTION vn_portable_assessment_research.time_view(value jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $function$
 SELECT vn_portable_assessment_research.float_view(vn_portable_source_research.round_ratio(
   vn_portable_dependency_research.counter(value,0,1099511627776),1))
$function$;

CREATE FUNCTION vn_portable_assessment_research.policy() RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $function$
 SELECT jsonb_build_object('version','common-market-window-v1','horizon_unit','market_minutes',
  'warmup','all_candidates_ready','early_terminal','freeze_cash_and_score_until_common_deadline',
  'interruptions','abort_without_tell','deadline_mark','first_valid_observation_at_or_after_deadline')
$function$;

CREATE FUNCTION vn_portable_assessment_research.source_cursor(state jsonb,at jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $function$
 SELECT jsonb_build_object('policy','ga-provider-source-research-v1','epoch',state#>'{source,epoch}',
  'sequence',state#>'{source,quote_sequence}','at',at,'candle_count',state#>'{engine,ema,count}',
  'bar',state#>'{source,bars,-1}','frame',state#>'{source,last_quote}')
$function$;

CREATE FUNCTION vn_portable_assessment_research.snapshot(member jsonb,account jsonb,holding jsonb,state jsonb,at jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE cash numeric:=vn_portable_economic_research.units(account->'cash',36);
 initial numeric:=vn_portable_economic_research.units(account->'initial_cash',36);
 n numeric; d numeric; g numeric; roi jsonb; dd jsonb; fitness jsonb;
 held boolean:=holding IS NOT NULL AND holding<>'null'::jsonb;
BEGIN
 IF initial<=0 THEN RAISE EXCEPTION 'assessment_zero_initial_cash' USING ERRCODE='22023'; END IF;
 n:=cash-initial; d:=initial; g:=gcd(n,d); n:=div(n,g); d:=div(d,g);
 roi:=vn_portable_source_research.round_ratio(n,d);
 dd:=vn_portable_source_research.round_ratio(vn_numeric_research.integer_text(member#>>'{max_drawdown,numerator}'),
   vn_numeric_research.integer_text(member#>>'{max_drawdown,denominator}'));
 fitness:=vn_portable_source_research.binary_operation('subtract',roi,
   vn_portable_source_research.binary_operation('multiply','{"$binary64":"0x1.0000000000000p+1"}',dd));
 RETURN jsonb_build_object('captured_revision',state->'revision','captured_at',at,
  'cash_balance',account->'cash','terminal_cash',CASE WHEN held THEN 'null'::jsonb ELSE account->'cash' END,
  'has_open_position',held,'initial_cash',account->'initial_cash','peak_equity',member->'peak_equity',
  'max_drawdown',member->'max_drawdown','roi_ratio',jsonb_build_object('numerator',n::text,'denominator',d::text),
  'roi_float64',roi->'$binary64','fitness_float64',fitness->'$binary64','closed_trade_count',member->'num_trades',
  'source',vn_portable_assessment_research.source_cursor(state,at));
END $function$;

CREATE FUNCTION vn_portable_assessment_research.cohort(state jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE ids jsonb; gen bigint:=vn_portable_dependency_research.counter(state#>'{engine,generation}',0,2147483647);
BEGIN
 SELECT jsonb_agg(v->'id' ORDER BY ordinal) INTO ids FROM jsonb_array_elements(state#>'{engine,members}') WITH ORDINALITY a(v,ordinal);
 RETURN jsonb_build_object('policy',vn_portable_assessment_research.policy(),'iteration_id',(state->>'run_id')||':'||gen::text,
  'phase','warming','member_ids',ids,'member_count',vn_portable_source_research.tag(8),'completed_count',vn_portable_source_research.tag(0),
  'horizon_seconds','{"float64":"0x1.c200000000000p+11"}'::jsonb,'started_at',NULL,'ends_at',NULL,
  'completed_at',NULL,'abort_reason',NULL,'evaluations','[]'::jsonb);
END $function$;

CREATE FUNCTION vn_portable_assessment_research.result(member jsonb,metrics jsonb,cohort jsonb,ordinal integer,
 reason text,at jsonb,aborted boolean,complete boolean) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $function$
 SELECT jsonb_build_object('probe_id',member->'id','evaluation_id',(cohort->>'iteration_id')||':'||ordinal::text,
  'iteration_id',cohort->'iteration_id','fitness',CASE WHEN aborted THEN 'null'::jsonb ELSE jsonb_build_object('float64',metrics->'fitness_float64') END,
  'roi',CASE WHEN aborted THEN 'null'::jsonb ELSE jsonb_build_object('float64',metrics->'roi_float64') END,
  'num_trades',CASE WHEN aborted THEN vn_portable_source_research.tag(0) ELSE metrics->'closed_trade_count' END,
  'reason',reason,'status',CASE WHEN aborted THEN 'aborted' ELSE 'completed' END,'cohort_complete',complete,
  'window_started_at',cohort->'started_at','window_ends_at',cohort->'ends_at','terminated_at',vn_portable_assessment_research.time_view(at))
$function$;

CREATE FUNCTION vn_portable_assessment_research.record(state jsonb,cohort jsonb,member jsonb,metrics jsonb,result jsonb,
 ordinal integer,at jsonb,reason text,aborted boolean,frozen boolean,window_source jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $function$
 SELECT jsonb_build_object('format','ga-portable-provider-assessment-research-v2','owner_id',state->'owner_id','run_id',state->'run_id',
  'finalized_revision',state->'revision','finalized_at',at,'iteration_id',cohort->'iteration_id',
  'evaluation_id',(cohort->>'iteration_id')||':'||ordinal::text,'member_index',vn_portable_source_research.tag(ordinal),
  'probe_id',member->'id','generation',member#>'{genome,generation}',
  'status',CASE WHEN aborted THEN 'aborted' ELSE 'completed' END,'reason',CASE WHEN aborted THEN to_jsonb(reason) ELSE result->'reason' END,
  'selection_eligible',NOT aborted,'cohort_complete',NOT aborted,
  'window_started_at',CASE WHEN cohort->'started_at'='null'::jsonb THEN 'null'::jsonb ELSE jsonb_build_object('$float64',cohort#>'{started_at,float64}') END,
  'window_ends_at',CASE WHEN cohort->'ends_at'='null'::jsonb THEN 'null'::jsonb ELSE jsonb_build_object('$float64',cohort#>'{ends_at,float64}') END,
  'window_source_start',window_source,'window_source_end',vn_portable_assessment_research.source_cursor(state,at),
  'fitness_policy',jsonb_build_object('version','equity-roi-historical-dd-v1',
    'formula','portfolio_roi - 2 * observed_historical_max_drawdown','drawdown_weight','{"float64":"0x1.0000000000000p+1"}'::jsonb,
    'status','provisional_heuristic','sharpe_in_fitness',false),
  'evaluation_policy',vn_portable_assessment_research.policy(),'execution',state#>'{engine,config,execution}',
  'measurement_basis',CASE WHEN aborted THEN 'interrupted-unscored-snapshot' ELSE 'post-liquidation-closed-fills' END,
  'early_terminal_frozen',frozen,'roi_float64',CASE WHEN aborted THEN 'null'::jsonb ELSE metrics->'roi_float64' END,
  'fitness_float64',CASE WHEN aborted THEN 'null'::jsonb ELSE metrics->'fitness_float64' END,
  'metrics',CASE WHEN aborted THEN metrics||jsonb_build_object('roi_ratio',NULL,'roi_float64',NULL,'fitness_float64',NULL) ELSE metrics END)
$function$;

CREATE FUNCTION vn_portable_assessment_research.transition(request jsonb,previous jsonb,following jsonb,causal jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE cohort jsonb; window_source jsonb; at jsonb:=vn_portable_source_research.tag(extract(epoch FROM (request#>>'{evidence,inputs,event_at}')::timestamptz));
 trace jsonb:=causal->'trace'; finalized jsonb:=trace->'finalized'; frozen jsonb:='{}'; results jsonb:='{}'; rows jsonb:='[]'; records jsonb:='[]';
 member jsonb; marker jsonb; metrics jsonb; result jsonb; entry record; id text; ordinal integer; count integer:=0;
 aborted boolean; changed boolean:=false; original jsonb; expected jsonb; started jsonb; due jsonb;
 event_rows jsonb:='[]'; action jsonb; op_count integer:=jsonb_array_length(request->'operations'); i integer;
BEGIN
 IF following#>>'{engine,config,assessment_policy}' IS DISTINCT FROM 'ga-portable-provider-assessment-research-v2' THEN
  RAISE EXCEPTION 'assessment_policy_mismatch' USING ERRCODE='22023'; END IF;
 IF previous IS NULL THEN
  cohort:=vn_portable_assessment_research.cohort(following); window_source:='null'; original:=following#>'{engine,members}';
 ELSE
  cohort:=previous#>'{engine,cohort}'; window_source:=previous#>'{engine,cohort_source}'; original:=previous#>'{engine,members}';
  FOR entry IN SELECT v,ordinality FROM jsonb_array_elements(original) WITH ORDINALITY a(v,ordinality) LOOP
   member:=entry.v; id:=member->>'id'; ordinal:=entry.ordinality-1; metrics:=member->'assessment';
   marker:=trace#>ARRAY['frozen',id];
   IF marker IS NOT NULL THEN
    IF metrics<>'null'::jsonb OR member->'terminal'<>'null'::jsonb OR cohort->>'phase'<>'evaluating' THEN
     RAISE EXCEPTION 'assessment_refrozen_member' USING ERRCODE='22023'; END IF;
    metrics:=vn_portable_assessment_research.snapshot(marker->'member',marker->'account',marker->'holding',following,at);
   END IF;
   frozen:=frozen||jsonb_build_object(id,metrics);
  END LOOP;
  FOR entry IN SELECT v FROM jsonb_array_elements(cohort->'evaluations') a(v) LOOP
   results:=results||jsonb_build_object(entry.v->>'probe_id',entry.v);
  END LOOP;
  FOR entry IN SELECT v,ordinality FROM jsonb_array_elements(original) WITH ORDINALITY a(v,ordinality) LOOP
   member:=entry.v; id:=member->>'id'; ordinal:=entry.ordinality-1;
   IF trace->'frozen' ? id THEN
    IF results ? id THEN RAISE EXCEPTION 'assessment_duplicate_terminal_result' USING ERRCODE='22023'; END IF;
    result:=vn_portable_assessment_research.result(member,frozen->id,cohort,ordinal,'drawdown',at,false,false);
    results:=results||jsonb_build_object(id,result);
   END IF;
  END LOOP;
  IF finalized<>'null'::jsonb THEN
   aborted:=(finalized->>'aborted')::boolean;
   IF cohort->>'phase' IN ('completed','aborted') THEN RAISE EXCEPTION 'assessment_refinalized_cohort' USING ERRCODE='22023'; END IF;
   FOR entry IN SELECT v,ordinality FROM jsonb_array_elements(original) WITH ORDINALITY a(v,ordinality) LOOP
    member:=entry.v; id:=member->>'id'; ordinal:=entry.ordinality-1; metrics:=frozen->id;
    IF metrics='null'::jsonb THEN metrics:=vn_portable_assessment_research.snapshot(finalized#>ARRAY['members',id],
      finalized#>ARRAY['accounts',id],finalized#>ARRAY['holdings',id],following,at); END IF;
    result:=results->id;
    IF result IS NULL THEN
     result:=vn_portable_assessment_research.result(member,metrics,cohort,ordinal,finalized->>'reason',at,aborted,NOT aborted);
    ELSIF NOT aborted THEN result:=result||jsonb_build_object('cohort_complete',true); END IF;
    results:=results||jsonb_build_object(id,result);
    records:=records||jsonb_build_array(vn_portable_assessment_research.record(following,cohort,member,metrics,result,ordinal,at,
      finalized->>'reason',aborted,(frozen->id)<>'null'::jsonb,window_source));
   END LOOP;
   cohort:=cohort||jsonb_build_object('phase',CASE WHEN aborted THEN 'aborted' ELSE 'completed' END,
    'completed_at',vn_portable_assessment_research.time_view(at),'abort_reason',CASE WHEN aborted THEN finalized->'reason' ELSE 'null'::jsonb END);
  END IF;
  FOR entry IN SELECT v FROM jsonb_array_elements(original) a(v) LOOP
   result:=results->(entry.v->>'id');
   IF result IS NOT NULL THEN rows:=rows||jsonb_build_array(result); IF result->>'status'='completed' THEN count:=count+1; END IF; END IF;
  END LOOP;
  cohort:=cohort||jsonb_build_object('evaluations',rows,'completed_count',vn_portable_source_research.tag(count));
  changed:=(causal->>'replaced')::boolean OR (causal->>'restart')::boolean;
  IF changed THEN cohort:=vn_portable_assessment_research.cohort(following); window_source:='null'; END IF;
  IF cohort->>'phase'='warming' AND causal->>'phase'='evaluating' THEN
   started:=vn_portable_assessment_research.time_view(at);
   due:=vn_portable_assessment_research.float_view(vn_portable_source_research.binary_operation('add',
     jsonb_build_object('$binary64',started->'float64'),'{"$binary64":"0x1.c200000000000p+11"}'));
   cohort:=cohort||jsonb_build_object('phase','evaluating','started_at',started,'ends_at',due);
   window_source:=vn_portable_assessment_research.source_cursor(following,at);
  END IF;
 END IF;
 IF following#>'{engine,cohort}' IS DISTINCT FROM cohort OR following#>'{engine,cohort_source}' IS DISTINCT FROM window_source THEN
  RAISE EXCEPTION 'assessment_common_window_mismatch' USING ERRCODE='22023'; END IF;
 IF request#>'{history,assessments}' IS DISTINCT FROM records THEN
  RAISE EXCEPTION 'assessment_finalized_records_mismatch' USING ERRCODE='22023'; END IF;
 -- Indexed events already bind to causally consumed actions. Require the one
 -- unindexed assessment event at the replay-derived capture point as well.
 FOR i IN 0..op_count LOOP
  IF finalized<>'null'::jsonb AND (finalized->>'operation_index')::integer=i THEN
   event_rows:=event_rows||jsonb_build_array(jsonb_build_object('kind',
    CASE WHEN (finalized->>'aborted')::boolean THEN 'evaluation_aborted' ELSE 'evaluation' END,
    'at',at,'account_id',NULL,'position_id',NULL,'operation_index',NULL));
  END IF;
  IF i<op_count THEN
   action:=request#>ARRAY['evidence','actions',i::text];
   event_rows:=event_rows||jsonb_build_array(jsonb_build_object('kind',action->'reason','at',at,
    'account_id',action->'account_id','position_id',action->'position_id','operation_index',vn_portable_source_research.tag(i)));
  END IF;
 END LOOP;
 IF request->'events' IS DISTINCT FROM event_rows THEN
  RAISE EXCEPTION 'assessment_event_order_mismatch' USING ERRCODE='22023'; END IF;
 FOR member IN SELECT v FROM jsonb_array_elements(following#>'{engine,members}') a(v) LOOP
  expected:=CASE WHEN previous IS NULL OR changed THEN 'null'::jsonb ELSE frozen->(member->>'id') END;
  IF member->'assessment' IS DISTINCT FROM expected THEN RAISE EXCEPTION 'assessment_member_frozen_mismatch' USING ERRCODE='22023'; END IF;
 END LOOP;
 FOR entry IN SELECT v FROM jsonb_array_elements(request#>'{history,retired_accounts}') a(v) LOOP
  id:=entry.v#>>'{member,id}';
  IF entry.v#>'{member,assessment}' IS DISTINCT FROM frozen->id THEN
   RAISE EXCEPTION 'assessment_retired_frozen_mismatch' USING ERRCODE='22023'; END IF;
 END LOOP;
 RETURN jsonb_build_object('finalized_count',vn_portable_source_research.tag(jsonb_array_length(records)),
  'new_frozen_count',vn_portable_source_research.tag((SELECT count(*) FROM jsonb_object_keys(trace->'frozen'))),'cohort_phase',cohort->'phase',
  'optimizer_rng_lineage_verified',false);
END $function$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_portable_assessment_research FROM PUBLIC;
