-- Offline ordered causal/risk replay. No native effects or runtime capability.
DO $guard$ BEGIN
 IF current_setting('dashboard.causal_risk_fixture',true) IS DISTINCT FROM 'offline-v1'
    OR to_regprocedure('vn_source_research.validate_request(uuid,uuid,text)') IS NULL THEN
  RAISE EXCEPTION 'offline_causal_risk_fixture_required' USING ERRCODE='22023';
 END IF;
END $guard$;
CREATE SCHEMA vn_causal_research;
REVOKE ALL ON SCHEMA vn_causal_research FROM PUBLIC;

CREATE FUNCTION vn_causal_research.member_projection(value jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $function$
 SELECT jsonb_build_object('id',value->'id','cursor',value->'cursor','pending',value->'pending',
  'num_trades',value->'num_trades','peak_equity',value->'peak_equity','max_drawdown',value->'max_drawdown','terminal',value->'terminal')
$function$;

CREATE FUNCTION vn_causal_research.allocate(ctx jsonb,identity jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE i integer:=(ctx->>'allocation')::integer;
BEGIN
 IF identity IS NULL OR identity IS DISTINCT FROM ctx#>ARRAY['inputs','ids',i::text] THEN
  RAISE EXCEPTION 'causal_allocation_order' USING ERRCODE='22023'; END IF;
 RETURN ctx||jsonb_build_object('allocation',i+1);
END $function$;

CREATE FUNCTION vn_causal_research.consume(ctx jsonb,kind text,reason text,account text,position_id text,
 signal jsonb DEFAULT 'null',price jsonb DEFAULT 'null',status text DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE i integer:=(ctx->>'index')::integer; op jsonb:=ctx->'operations'->i; expected jsonb;
BEGIN
 expected:=jsonb_build_object('operation_index',vn_source_research.tag(i),'reason',reason,
  'account_id',account,'position_id',position_id,'signal_at',signal,'reference_price',price);
 IF op IS NULL OR op->>'kind' IS DISTINCT FROM kind OR ctx->'actions'->i IS DISTINCT FROM expected
    OR (kind IN ('birth','retire') AND op->>'id' IS DISTINCT FROM account)
    OR (kind='close' AND op->>'id' IS DISTINCT FROM position_id)
    OR (kind='open' AND (op->>'id' IS DISTINCT FROM position_id OR op->>'account_id' IS DISTINCT FROM account))
    OR (kind='lifecycle' AND op IS DISTINCT FROM jsonb_build_object('kind','lifecycle','status',status)) THEN
  RAISE EXCEPTION 'causal_required_operation_mismatch' USING ERRCODE='22023'; END IF;
 RETURN ctx||jsonb_build_object('index',i+1);
END $function$;

CREATE FUNCTION vn_causal_research.equity(ctx jsonb,identity text DEFAULT NULL) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE total numeric:=0; row record; held jsonb;
BEGIN
 IF identity IS NULL THEN
  total:=vn_economic_research.units(ctx->'reserve',36);
  FOR row IN SELECT * FROM jsonb_each(ctx->'accounts') LOOP
   total:=total+vn_economic_research.units(row.value->'cash',36);
  END LOOP;
  FOR row IN SELECT * FROM jsonb_each(ctx->'holdings') LOOP
   total:=total+vn_economic_research.units(row.value#>'{entry,quantity}',18)*vn_source_research.price(ctx->'price');
  END LOOP;
 ELSE
  total:=vn_economic_research.units(ctx#>ARRAY['accounts',identity,'cash'],36);
  held:=ctx#>ARRAY['holdings',identity];
  IF held IS NOT NULL THEN total:=total+vn_economic_research.units(held#>'{entry,quantity}',18)*vn_source_research.price(ctx->'price'); END IF;
 END IF;
 IF total<0 OR total>1e72 THEN RAISE EXCEPTION 'causal_equity_capacity' USING ERRCODE='22023'; END IF;
 RETURN total;
END $function$;

CREATE FUNCTION vn_causal_research.member_risk(ctx jsonb,identity text) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE member jsonb:=ctx#>ARRAY['members',identity]; equity numeric; peak numeric; n numeric; d numeric; divisor numeric;
BEGIN
 equity:=vn_causal_research.equity(ctx,identity);
 peak:=greatest(equity,vn_economic_research.units(member->'peak_equity',36));
 n:=vn_numeric_research.integer_text(member#>>'{max_drawdown,numerator}');
 d:=vn_numeric_research.integer_text(member#>>'{max_drawdown,denominator}');
 IF peak<=0 OR n<0 OR d<=0 OR n>d OR gcd(n,d)<>1 THEN RAISE EXCEPTION 'causal_invalid_drawdown' USING ERRCODE='22023'; END IF;
 member:=member||jsonb_build_object('peak_equity',vn_economic_research.decimal_text(peak,36));
 IF (peak-equity)*d>n*peak THEN
  divisor:=gcd(peak-equity,peak);
  member:=member||jsonb_build_object('max_drawdown',jsonb_build_object('numerator',div(peak-equity,divisor)::text,'denominator',div(peak,divisor)::text));
 END IF;
 RETURN jsonb_set(ctx,ARRAY['members',identity],member);
END $function$;

CREATE FUNCTION vn_causal_research.account_risk(ctx jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE risk jsonb:=ctx#>'{lifecycle,risk}'; equity numeric:=vn_causal_research.equity(ctx);
 baseline numeric:=vn_economic_research.units(risk->'baseline_equity',36); trip jsonb; row record;
BEGIN
 risk:=risk||jsonb_build_object('observed_equity',vn_economic_research.decimal_text(equity,36),'observed_at',ctx->'at');
 ctx:=jsonb_set(ctx,'{lifecycle,risk}',risk);
 IF risk->'active'='true'::jsonb OR equity*10000>baseline*(10000-(ctx->>'loss_bps')::integer) THEN RETURN ctx; END IF;
 trip:=ctx#>'{following_lifecycle,risk,trip_id}'; ctx:=vn_causal_research.allocate(ctx,trip);
 risk:=risk||jsonb_build_object('active',true,'trip_id',trip,'tripped_at',ctx->'at','trip_equity',vn_economic_research.decimal_text(equity,36));
 ctx:=jsonb_set(ctx,'{lifecycle,risk}',risk);
 FOR row IN SELECT * FROM jsonb_each(ctx->'members') LOOP
  IF row.value#>>'{pending,action}'='entry' THEN ctx:=jsonb_set(ctx,ARRAY['members',row.key,'pending'],'null'); END IF;
 END LOOP;
 ctx:=jsonb_set(ctx,'{lifecycle,restart_required}','true');
 ctx:=ctx||jsonb_build_object('phase','aborted','status','risk_halted');
 RETURN vn_causal_research.consume(ctx,'lifecycle','risk_halt',NULL,NULL,'null','null','risk_halted');
END $function$;

CREATE FUNCTION vn_causal_research.close_position(ctx jsonb,identity text,reason text,signal jsonb DEFAULT 'null') RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE held jsonb:=ctx#>ARRAY['holdings',identity]; op jsonb; member jsonb; cash numeric;
BEGIN
 IF held IS NULL THEN RETURN ctx; END IF;
 op:=ctx->'operations'->(ctx->>'index')::integer;
 ctx:=vn_causal_research.consume(ctx,'close',reason,identity,held->>'id',signal,ctx->'price');
 cash:=vn_economic_research.units(ctx#>ARRAY['accounts',identity,'cash'],36)+vn_economic_research.units(op#>'{execution,cash_credit}',36);
 ctx:=jsonb_set(ctx,ARRAY['accounts',identity,'cash'],to_jsonb(vn_economic_research.decimal_text(cash,36)));
 ctx:=jsonb_set(ctx,'{holdings}',(ctx->'holdings')-identity);
 member:=ctx#>ARRAY['members',identity];
 member:=member||jsonb_build_object('pending',NULL,'num_trades',vn_source_research.tag(vn_dependency_research.counter(member->'num_trades',0,9223372036854775805)+1));
 ctx:=jsonb_set(ctx,ARRAY['members',identity],member);
 RETURN vn_causal_research.member_risk(ctx,identity);
END $function$;

CREATE FUNCTION vn_causal_research.open_position(ctx jsonb,identity text,signal jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE op jsonb:=ctx->'operations'->(ctx->>'index')::integer; cash numeric; held jsonb;
BEGIN
 ctx:=vn_causal_research.allocate(ctx,op->'id');
 ctx:=vn_causal_research.consume(ctx,'open','entry_signal',identity,op->>'id',signal,ctx->'price');
 cash:=vn_economic_research.units(ctx#>ARRAY['accounts',identity,'cash'],36)-vn_economic_research.units(op#>'{execution,cash_debit}',36);
 ctx:=jsonb_set(ctx,ARRAY['accounts',identity,'cash'],to_jsonb(vn_economic_research.decimal_text(cash,36)));
 held:=jsonb_build_object('id',op->'id','account_id',identity,'asset','SOL/USD','entry',op->'execution','exit',NULL,'closed',false);
 ctx:=jsonb_set(ctx,'{holdings}',(ctx->'holdings')||jsonb_build_object(identity,held));
 ctx:=jsonb_set(ctx,ARRAY['members',identity,'pending'],'null');
 RETURN vn_causal_research.member_risk(ctx,identity);
END $function$;

CREATE FUNCTION vn_causal_research.retire(ctx jsonb,identity text,reason text) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE account jsonb:=ctx#>ARRAY['accounts',identity]; member jsonb:=ctx#>ARRAY['members',identity]; reserve numeric;
BEGIN
 IF account->'retired' IS DISTINCT FROM 'false'::jsonb OR ctx->'holdings' ? identity THEN
  RAISE EXCEPTION 'causal_invalid_retirement' USING ERRCODE='22023'; END IF;
 ctx:=vn_causal_research.consume(ctx,'retire',reason,identity,NULL);
 ctx:=jsonb_set(ctx,'{retired}',(ctx->'retired')||jsonb_build_array(vn_causal_research.member_projection(member)));
 reserve:=vn_economic_research.units(ctx->'reserve',36)+vn_economic_research.units(account->'cash',36);
 ctx:=ctx||jsonb_build_object('reserve',vn_economic_research.decimal_text(reserve,36));
 ctx:=jsonb_set(ctx,ARRAY['accounts',identity],account||jsonb_build_object('cash','0','retired',true));
 RETURN jsonb_set(ctx,ARRAY['members',identity,'pending'],'null');
END $function$;

CREATE FUNCTION vn_causal_research.terminal(ctx jsonb,identity text) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE member jsonb:=ctx#>ARRAY['members',identity]; peak numeric; equity numeric;
BEGIN
 IF member->'terminal'<>'null'::jsonb THEN RETURN ctx; END IF;
 ctx:=vn_causal_research.member_risk(ctx,identity); member:=ctx#>ARRAY['members',identity];
 peak:=vn_economic_research.units(member->'peak_equity',36); equity:=vn_causal_research.equity(ctx,identity);
 IF equity*10000>peak*8000 THEN RETURN ctx; END IF;
 ctx:=vn_causal_research.close_position(ctx,identity,'death_liquidation');
 ctx:=jsonb_set(ctx,ARRAY['members',identity,'terminal'],jsonb_build_object('reason','drawdown','at',ctx->'at','cash',ctx#>ARRAY['accounts',identity,'cash']));
 RETURN vn_causal_research.retire(ctx,identity,'terminal');
END $function$;

CREATE FUNCTION vn_causal_research.pending(ctx jsonb,identity text,allow_entry boolean) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE member jsonb:=ctx#>ARRAY['members',identity]; pending jsonb:=member->'pending'; held jsonb:=ctx#>ARRAY['holdings',identity];
 at numeric:=vn_dependency_research.counter(ctx->'at',0,1099511627776);
BEGIN
 IF pending='null'::jsonb THEN RETURN ctx; END IF;
 PERFORM vn_dependency_research.exact_keys(pending,ARRAY['action','signal_at','position_id']);
 IF at<=vn_dependency_research.counter(pending->'signal_at',0,1099511627776) THEN RETURN ctx; END IF;
 IF at<=vn_dependency_research.counter(member->'cursor',900,10000000000)+900 THEN
  IF pending->>'action'='entry' AND held IS NULL AND allow_entry THEN
   ctx:=vn_causal_research.open_position(ctx,identity,pending->'signal_at');
  ELSIF pending->>'action'='exit' AND held IS NOT NULL AND held->'id'=pending->'position_id' THEN
   ctx:=vn_causal_research.close_position(ctx,identity,'exit_signal',pending->'signal_at');
  END IF;
  ctx:=vn_causal_research.account_risk(ctx); ctx:=vn_causal_research.terminal(ctx,identity); ctx:=vn_causal_research.account_risk(ctx);
 END IF;
 RETURN jsonb_set(ctx,ARRAY['members',identity,'pending'],'null');
END $function$;

CREATE FUNCTION vn_causal_research.signal(ema jsonb,genome jsonb,holding jsonb,at jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE fast numeric[]:=vn_source_research.ratio(genome->'ema_fast'); slow numeric[]:=vn_source_research.ratio(genome->'ema_slow');
 f text; s text; pf numeric[]; ps numeric[]; cf numeric[]; cs numeric[]; action text;
BEGIN
 IF mod(fast[1],fast[2])<>0 OR mod(slow[1],slow[2])<>0 OR fast[1]<2*fast[2]
    OR slow[1]>60*slow[2] OR fast[1]*slow[2]>=slow[1]*fast[2] THEN
  RAISE EXCEPTION 'causal_invalid_ema_genes' USING ERRCODE='22023'; END IF;
 f:=div(fast[1],fast[2])::text; s:=div(slow[1],slow[2])::text;
 pf:=vn_source_research.ratio(ema#>ARRAY['previous',f]); ps:=vn_source_research.ratio(ema#>ARRAY['previous',s]);
 cf:=vn_source_research.ratio(ema#>ARRAY['values',f]); cs:=vn_source_research.ratio(ema#>ARRAY['values',s]);
 IF holding IS NULL AND pf[1]*ps[2]<=ps[1]*pf[2] AND cf[1]*cs[2]>cs[1]*cf[2] THEN action:='entry';
 ELSIF holding IS NOT NULL AND pf[1]*ps[2]>=ps[1]*pf[2] AND cf[1]*cs[2]<cs[1]*cf[2] THEN action:='exit';
 ELSE RETURN 'null'; END IF;
 RETURN jsonb_build_object('action',action,'signal_at',at,'position_id',holding->'id');
END $function$;

CREATE FUNCTION vn_causal_research.transition(request jsonb,previous jsonb,following jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $function$
DECLARE ctx jsonb; maps jsonb; members jsonb; accounts jsonb; holdings jsonb; ids jsonb; row jsonb; id text;
 kind text:=request#>>'{evidence,kind}'; control text:=request#>>'{evidence,control,action}';
 at numeric:=extract(epoch FROM (request#>>'{evidence,inputs,event_at}')::timestamptz);
 ema jsonb:=following#>'{engine,ema}'; end_at numeric:=vn_dependency_research.counter(ema->'last_end',900,10000000000);
 life jsonb; expected_risk jsonb; cfg jsonb:=following#>'{engine,config}'; policy jsonb:=cfg->'lifecycle_policy';
 ready boolean; new_candle boolean; replacement boolean:=false; restart boolean:=false; due numeric[];
 held jsonb; reference numeric; price numeric; pending jsonb; next_ids jsonb; gen bigint; pointer integer; expected jsonb;
BEGIN
 PERFORM vn_dependency_research.exact_keys(policy,ARRAY['version','account_loss_bps','death_drawdown_bps','max_lifespan_seconds']);
 IF policy-ARRAY['account_loss_bps'] IS DISTINCT FROM jsonb_build_object('version','ga-active-common-cohort-research-v1',
    'death_drawdown_bps','2000','max_lifespan_seconds',vn_source_research.tag(0))
    OR jsonb_typeof(policy->'account_loss_bps') IS DISTINCT FROM 'string' OR policy->>'account_loss_bps' !~ '^[1-9][0-9]{0,4}$'
    OR (policy->>'account_loss_bps')::integer>10000 THEN RAISE EXCEPTION 'causal_lifecycle_policy' USING ERRCODE='22023'; END IF;
 ready:=end_at<=at AND at<=end_at+900;
 IF previous IS NULL THEN
  expected_risk:=jsonb_build_object('active',false,'baseline_equity',cfg->'initial_cash','observed_equity',cfg->'initial_cash',
    'observed_at',vn_source_research.tag(at),'trip_id',NULL,'tripped_at',NULL,'trip_equity',NULL,
    'recovery_count',vn_source_research.tag(0),'last_recovered_at',NULL);
  life:=jsonb_build_object('search_epoch',vn_source_research.tag(0),'restart_required',false,'signals_after',NULL,'last_control_at',NULL,'risk',expected_risk);
  IF kind<>'bootstrap' OR following->>'status' IS DISTINCT FROM 'running' OR following#>'{engine,lifecycle}' IS DISTINCT FROM life
     OR following#>'{engine,decision_timestamp}' IS DISTINCT FROM 'null'::jsonb OR following#>>'{engine,cohort,phase}' IS DISTINCT FROM 'warming'
     OR following#>'{engine,generation}' IS DISTINCT FROM vn_source_research.tag(0) THEN
   RAISE EXCEPTION 'causal_bootstrap_lifecycle' USING ERRCODE='22023'; END IF;
  FOR row IN SELECT v FROM jsonb_array_elements(following#>'{engine,members}') a(v) LOOP
   IF row->'cursor' IS DISTINCT FROM 'null'::jsonb OR row->'pending' IS DISTINCT FROM 'null'::jsonb THEN
    RAISE EXCEPTION 'causal_bootstrap_member' USING ERRCODE='22023'; END IF;
  END LOOP;
  IF jsonb_array_length(request->'operations')<>9 OR request#>'{operations,8}' IS DISTINCT FROM '{"kind":"lifecycle","status":"running"}'::jsonb
     OR request#>'{evidence,actions,8}' IS DISTINCT FROM jsonb_build_object('operation_index',vn_source_research.tag(8),'reason','lifecycle',
       'account_id',NULL,'position_id',NULL,'signal_at',NULL,'reference_price',NULL) THEN
   RAISE EXCEPTION 'causal_bootstrap_operations' USING ERRCODE='22023'; END IF;
  FOR pointer IN 0..7 LOOP
   id:=following#>>ARRAY['engine','members',pointer::text,'id'];
   expected:=jsonb_build_object('operation_index',vn_source_research.tag(pointer),'reason','founder','account_id',id,
      'position_id',NULL,'signal_at',NULL,'reference_price',NULL);
   IF request#>ARRAY['evidence','actions',pointer::text] IS DISTINCT FROM expected OR
      request#>ARRAY['evidence','inputs','ids',pointer::text] IS DISTINCT FROM to_jsonb(id) THEN
    RAISE EXCEPTION 'causal_bootstrap_allocation_or_reason' USING ERRCODE='22023'; END IF;
  END LOOP;
  RETURN jsonb_build_object('phase','warming','risk',expected_risk,'replaced',false,'restart',false);
 END IF;
 IF previous->>'status' NOT IN ('running','paused','risk_halted') THEN RAISE EXCEPTION 'causal_terminal_prior' USING ERRCODE='22023'; END IF;
 maps:=vn_economic_research.state(previous); members:=maps->'members'; accounts:=maps->'accounts';
 SELECT coalesce(jsonb_object_agg(v->>'account_id',v),'{}') INTO holdings FROM jsonb_array_elements(previous->'positions') a(v);
 SELECT jsonb_agg(v->'id' ORDER BY ordinal) INTO ids FROM jsonb_array_elements(previous#>'{engine,members}') WITH ORDINALITY a(v,ordinal);
 ctx:=jsonb_build_object('members',members,'accounts',accounts,'holdings',holdings,'ids',ids,'reserve',previous->'reserve',
   'lifecycle',previous#>'{engine,lifecycle}','following_lifecycle',following#>'{engine,lifecycle}',
   'status',previous->'status','phase',previous#>'{engine,cohort,phase}',
   'index',0,'allocation',0,'retired','[]'::jsonb,'operations',request->'operations','actions',request#>'{evidence,actions}',
   'inputs',request#>'{evidence,inputs}','price',request#>'{evidence,observation,price}','at',vn_source_research.tag(at),
   'loss_bps',(policy->>'account_loss_bps')::integer);
 gen:=vn_dependency_research.counter(previous#>'{engine,generation}',0,2147483647);
 new_candle:=ema->'count' IS DISTINCT FROM previous#>'{engine,ema,count}';
 IF kind='protective' THEN
  IF previous->>'status' NOT IN ('running','risk_halted') THEN RAISE EXCEPTION 'causal_paused_quote' USING ERRCODE='22023'; END IF;
  ctx:=vn_causal_research.account_risk(ctx); price:=vn_source_research.price(ctx->'price');
  FOR row IN SELECT v FROM jsonb_array_elements(ids) a(v) LOOP
   id:=row#>>'{}';
   IF ctx#>ARRAY['members',id,'terminal']<>'null'::jsonb THEN CONTINUE; END IF;
   ctx:=vn_causal_research.member_risk(ctx,id); held:=ctx#>ARRAY['holdings',id];
   IF held IS NOT NULL THEN
    reference:=vn_source_research.price(held#>'{entry,reference_price}');
    IF price*100<=reference*97 THEN ctx:=vn_causal_research.close_position(ctx,id,'stop_loss'); ctx:=vn_causal_research.account_risk(ctx);
    ELSIF price*100>=reference*107 THEN ctx:=vn_causal_research.close_position(ctx,id,'take_profit'); ctx:=vn_causal_research.account_risk(ctx); END IF;
   END IF;
   ctx:=vn_causal_research.terminal(ctx,id); ctx:=vn_causal_research.account_risk(ctx);
  END LOOP;
 ELSIF kind='decision' THEN
  IF previous->>'status' NOT IN ('running','risk_halted') OR
     (previous#>'{engine,decision_timestamp}'<>'null'::jsonb AND at<=vn_dependency_research.counter(previous#>'{engine,decision_timestamp}',0,1099511627776)) THEN
   RAISE EXCEPTION 'causal_duplicate_or_paused_decision' USING ERRCODE='22023'; END IF;
  IF ctx#>'{lifecycle,risk,active}'='true'::jsonb THEN
   FOR row IN SELECT v FROM jsonb_array_elements(ids) a(v) LOOP
    id:=row#>>'{}'; IF ctx#>ARRAY['members',id,'terminal']='null'::jsonb THEN ctx:=vn_causal_research.pending(ctx,id,false); END IF;
   END LOOP;
  ELSIF ctx#>'{lifecycle,restart_required}'='true'::jsonb THEN
   restart:=ready;
   IF restart AND (ctx->>'phase'<>'aborted' OR ctx#>'{lifecycle,signals_after}'='null'::jsonb OR
      at<=vn_dependency_research.counter(ctx#>'{lifecycle,signals_after}',0,1099511627776)) THEN
    RAISE EXCEPTION 'causal_restart_clock' USING ERRCODE='22023'; END IF;
  ELSIF ctx->>'phase'='warming' THEN
   IF ready THEN ctx:=ctx||jsonb_build_object('phase','evaluating'); END IF;
  ELSIF ctx->>'phase'='evaluating' THEN
   due:=vn_source_research.ratio(to_jsonb(previous#>>'{engine,cohort,ends_at,float64}'));
   replacement:=at*due[2]>=due[1];
   IF NOT replacement THEN
    FOR row IN SELECT v FROM jsonb_array_elements(ids) a(v) LOOP
     id:=row#>>'{}'; IF ctx#>ARRAY['members',id,'terminal']<>'null'::jsonb THEN CONTINUE; END IF;
     ctx:=vn_causal_research.pending(ctx,id,ctx#>'{lifecycle,risk,active}'='false'::jsonb);
     IF ctx#>ARRAY['members',id,'terminal']<>'null'::jsonb OR ctx#>'{lifecycle,risk,active}'='true'::jsonb THEN CONTINUE; END IF;
     IF new_candle THEN
      pending:='null';
      IF at<=end_at+900 AND (ctx#>'{lifecycle,signals_after}'='null'::jsonb OR end_at>vn_dependency_research.counter(ctx#>'{lifecycle,signals_after}',0,1099511627776)) THEN
       pending:=vn_causal_research.signal(ema,ctx#>ARRAY['members',id,'genome'],ctx#>ARRAY['holdings',id],ctx->'at');
      END IF;
      ctx:=jsonb_set(ctx,ARRAY['members',id,'cursor'],ema->'last_end'); ctx:=jsonb_set(ctx,ARRAY['members',id,'pending'],pending);
     END IF;
    END LOOP;
   END IF;
  ELSE RAISE EXCEPTION 'causal_invalid_cohort_phase' USING ERRCODE='22023'; END IF;
  IF replacement OR restart THEN
   FOR row IN SELECT v FROM jsonb_array_elements(ids) a(v) LOOP
    id:=row#>>'{}'; IF ctx#>ARRAY['members',id,'terminal']='null'::jsonb THEN
     ctx:=vn_causal_research.close_position(ctx,id,CASE WHEN restart THEN 'restart_liquidation' ELSE 'cohort_liquidation' END);
     ctx:=vn_causal_research.account_risk(ctx);
    END IF;
   END LOOP;
   IF ctx#>'{lifecycle,risk,active}'='true'::jsonb THEN replacement:=false; restart:=false;
   ELSE
    IF gen>=2147483647 OR vn_causal_research.equity(ctx)<vn_economic_research.units(cfg->'seed_capital',36)*8 THEN
     RAISE EXCEPTION 'causal_replacement_capacity' USING ERRCODE='22023'; END IF;
    SELECT jsonb_agg(v->'id' ORDER BY ordinal) INTO next_ids FROM jsonb_array_elements(following#>'{engine,members}') WITH ORDINALITY a(v,ordinal);
    FOR row IN SELECT v FROM jsonb_array_elements(next_ids) a(v) LOOP ctx:=vn_causal_research.allocate(ctx,row); END LOOP;
    FOR row IN SELECT v FROM jsonb_array_elements(ids) a(v) LOOP
     id:=row#>>'{}'; IF ctx#>ARRAY['members',id,'terminal']='null'::jsonb THEN
      ctx:=vn_causal_research.retire(ctx,id,CASE WHEN restart THEN 'restart_retire' ELSE 'retire' END);
     END IF;
    END LOOP;
    FOR row IN SELECT v FROM jsonb_array_elements(following#>'{engine,members}') a(v) LOOP
     id:=row->>'id'; ctx:=vn_causal_research.consume(ctx,'birth',CASE WHEN restart THEN 'restart_birth' ELSE 'birth' END,id,NULL);
     expected:=jsonb_build_object('id',id,'cursor',ema->'last_end','pending',NULL,'num_trades',vn_source_research.tag(0),
       'peak_equity',cfg->'seed_capital','max_drawdown',jsonb_build_object('numerator','0','denominator','1'),'terminal',NULL);
     IF vn_causal_research.member_projection(row) IS DISTINCT FROM expected THEN RAISE EXCEPTION 'causal_new_member_state' USING ERRCODE='22023'; END IF;
    END LOOP;
    gen:=gen+1;
    IF restart THEN
     ctx:=jsonb_set(ctx,'{lifecycle,search_epoch}',vn_source_research.tag(vn_dependency_research.counter(ctx#>'{lifecycle,search_epoch}',0,2147483646)+1));
     ctx:=jsonb_set(ctx,'{lifecycle,restart_required}','false'); ctx:=jsonb_set(ctx,'{lifecycle,signals_after}',ctx->'at');
    END IF;
    ctx:=ctx||jsonb_build_object('phase',CASE WHEN restart OR NOT ready THEN 'warming' ELSE 'evaluating' END);
   END IF;
  END IF;
 ELSIF kind='control' THEN
  IF control NOT IN ('pause','resume','recover','stop') OR
     (control='pause' AND previous->>'status'<>'running') OR (control='resume' AND previous->>'status'<>'paused') OR
     (control='recover' AND previous->>'status'<>'risk_halted') THEN RAISE EXCEPTION 'causal_control_status' USING ERRCODE='22023'; END IF;
  IF control='recover' THEN
   IF ctx#>'{lifecycle,risk,active}'<>'true'::jsonb OR request#>'{evidence,control,trip_id}' IS DISTINCT FROM ctx#>'{lifecycle,risk,trip_id}'
      OR NOT ready OR NOT EXISTS(SELECT 1 FROM jsonb_each(ctx->'members') m WHERE m.value->'terminal'='null'::jsonb) THEN
    RAISE EXCEPTION 'causal_recovery_eligibility' USING ERRCODE='22023'; END IF;
   ctx:=vn_causal_research.account_risk(ctx);
   IF vn_causal_research.equity(ctx)*10000<=vn_economic_research.units(ctx#>'{lifecycle,risk,baseline_equity}',36)*(10000-(ctx->>'loss_bps')::integer) THEN
    RAISE EXCEPTION 'causal_recovery_original_boundary' USING ERRCODE='22023'; END IF;
   ctx:=jsonb_set(ctx,'{lifecycle,risk,active}','false'); ctx:=jsonb_set(ctx,'{lifecycle,risk,recovery_count}',
     vn_source_research.tag(vn_dependency_research.counter(ctx#>'{lifecycle,risk,recovery_count}',0,9223372036854775805)+1));
   ctx:=jsonb_set(ctx,'{lifecycle,risk,last_recovered_at}',ctx->'at');
  ELSIF request#>'{evidence,control,trip_id}' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'causal_unexpected_trip_ack' USING ERRCODE='22023'; END IF;
  IF control IN ('pause','stop') THEN
   ctx:=jsonb_set(ctx,'{lifecycle,restart_required}','true');
   IF ctx->>'phase' NOT IN ('aborted','completed') THEN ctx:=ctx||jsonb_build_object('phase','aborted'); END IF;
  END IF;
  FOR row IN SELECT v FROM jsonb_array_elements(ids) a(v) LOOP ctx:=jsonb_set(ctx,ARRAY['members',row#>>'{}','pending'],'null'); END LOOP;
  IF control IN ('resume','recover') THEN ctx:=jsonb_set(ctx,'{lifecycle,signals_after}',ctx->'at'); END IF;
  ctx:=jsonb_set(ctx,'{lifecycle,last_control_at}',ctx->'at');
  ctx:=ctx||jsonb_build_object('status',CASE control WHEN 'pause' THEN 'paused' WHEN 'stop' THEN 'stopped' ELSE 'running' END);
  ctx:=vn_causal_research.consume(ctx,'lifecycle',control,NULL,NULL,'null','null',ctx->>'status');
 ELSE RAISE EXCEPTION 'causal_invalid_phase' USING ERRCODE='22023'; END IF;
 IF (ctx->>'index')::integer<>jsonb_array_length(request->'operations') OR
    (ctx->>'allocation')::integer<>jsonb_array_length(request#>'{history,allocated_ids}') OR
    following#>'{engine,lifecycle}' IS DISTINCT FROM ctx->'lifecycle' OR following->'status' IS DISTINCT FROM ctx->'status'
    OR following#>'{engine,generation}' IS DISTINCT FROM vn_source_research.tag(gen)
    OR following#>>'{engine,cohort,phase}' IS DISTINCT FROM ctx->>'phase'
    OR following#>'{engine,decision_timestamp}' IS DISTINCT FROM
      (CASE WHEN kind='decision' THEN ctx->'at' ELSE previous#>'{engine,decision_timestamp}' END) THEN
  RAISE EXCEPTION 'causal_lifecycle_after_mismatch' USING ERRCODE='22023'; END IF;
 IF NOT replacement AND NOT restart THEN
  SELECT jsonb_agg(v->'id' ORDER BY ordinal) INTO next_ids FROM jsonb_array_elements(following#>'{engine,members}') WITH ORDINALITY a(v,ordinal);
  IF next_ids IS DISTINCT FROM ids THEN RAISE EXCEPTION 'causal_membership_changed' USING ERRCODE='22023'; END IF;
  FOR row IN SELECT v FROM jsonb_array_elements(following#>'{engine,members}') a(v) LOOP
   IF vn_causal_research.member_projection(row) IS DISTINCT FROM vn_causal_research.member_projection(ctx#>ARRAY['members',row->>'id']) THEN
    RAISE EXCEPTION 'causal_member_after_mismatch' USING ERRCODE='22023'; END IF;
  END LOOP;
 END IF;
 expected:='[]';
 FOR row IN SELECT v FROM jsonb_array_elements(request#>'{history,retired_accounts}') a(v) LOOP expected:=expected||jsonb_build_array(vn_causal_research.member_projection(row->'member')); END LOOP;
 IF expected IS DISTINCT FROM ctx->'retired' THEN RAISE EXCEPTION 'causal_retired_member_mismatch' USING ERRCODE='22023'; END IF;
 RETURN jsonb_build_object('phase',ctx->'phase','risk',ctx#>'{lifecycle,risk}','replaced',replacement,'restart',restart,
  'retired_member_evidence',ctx->'retired');
END $function$;

CREATE FUNCTION vn_causal_research.validate_request(owner_id uuid,run_id uuid,wire text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $function$
DECLARE source jsonb; resolved jsonb; causal jsonb;
BEGIN
 source:=vn_source_research.validate_request(owner_id,run_id,wire);
 resolved:=vn_dependency_research.resolve_request(owner_id,run_id,wire);
 causal:=vn_causal_research.transition(wire::jsonb,(resolved#>>'{prior,wire}')::jsonb,(resolved#>>'{following,wire}')::jsonb);
 RETURN source||jsonb_build_object('format','ga-causal-risk-validation-research-v1','causal_evidence',causal,
   'scope','economics-identities-source-indicators-causal-trading-and-risk-only');
END $function$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_causal_research FROM PUBLIC;
