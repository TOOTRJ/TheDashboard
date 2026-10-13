-- Guarded offline semantic proof. No command, lease, ACK, native effects or grants.
DO $guard$ BEGIN
 IF current_setting('dashboard.portable_economic_transition_fixture',true) IS DISTINCT FROM 'offline-v2'
    OR to_regprocedure('vn_portable_dependency_research.resolve_request(uuid,uuid,text)') IS NULL
    OR current_setting('server_encoding')<>'UTF8'
    OR current_setting('standard_conforming_strings')<>'on' THEN
  RAISE EXCEPTION 'offline_portable_economic_transition_fixture_required' USING ERRCODE='22023';
 END IF;
END $guard$;
CREATE SCHEMA vn_portable_economic_research;
REVOKE ALL ON SCHEMA vn_portable_economic_research FROM PUBLIC;
-- Privileged fixture seeding only. Validation never inserts or reserves an ID.
CREATE TABLE vn_portable_economic_research.allocated (
 id uuid PRIMARY KEY,
 owner_id uuid NOT NULL,
 run_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN ('account','position','risk')),
 born_revision bigint NOT NULL CHECK(born_revision>=2),
 FOREIGN KEY(owner_id,run_id) REFERENCES vn_portable_dependency_research.checkpoints(owner_id,run_id)
);
REVOKE ALL ON vn_portable_economic_research.allocated FROM PUBLIC;

CREATE FUNCTION vn_portable_economic_research.decimal_text(units numeric,digits integer) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE divisor numeric; whole text; tail text;
BEGIN
 IF units IS NULL OR units<>trunc(units) OR digits NOT IN (6,18,36) THEN
  RAISE EXCEPTION 'economic_invalid_units' USING ERRCODE='22023';
 END IF;
 divisor:=power(10::numeric,digits);
 whole:=div(abs(units),divisor)::text;
 tail:=rtrim(lpad(trunc(mod(abs(units),divisor))::text,digits,'0'),'0');
 RETURN CASE WHEN units<0 THEN '-' ELSE '' END||whole||
   CASE WHEN tail='' THEN '' ELSE '.'||tail END;
END $function$;

CREATE FUNCTION vn_portable_economic_research.units(value jsonb,digits integer) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE raw text:=value#>>'{}'; amount numeric; result numeric;
BEGIN
 IF digits IS NULL OR digits NOT IN (6,18,36) OR
    jsonb_typeof(value) IS DISTINCT FROM 'string' OR length(raw)>75 OR
    raw !~ '^(0|[1-9][0-9]*)(\.[0-9]{1,36})?$' THEN
  RAISE EXCEPTION 'economic_invalid_amount' USING ERRCODE='22023';
 END IF;
 amount:=raw::numeric;
 IF amount>1e36 OR scale(amount)>digits THEN
  RAISE EXCEPTION 'economic_amount_capacity' USING ERRCODE='22023';
 END IF;
 result:=trunc(amount*power(10::numeric,digits));
 IF raw IS DISTINCT FROM vn_portable_economic_research.decimal_text(result,digits) THEN
  RAISE EXCEPTION 'economic_noncanonical_amount' USING ERRCODE='22023';
 END IF;
 RETURN result;
END $function$;

CREATE FUNCTION vn_portable_economic_research.configuration(value jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE fee numeric; spread numeric; slip numeric;
BEGIN
 PERFORM vn_portable_dependency_research.exact_keys(value,ARRAY['fee_bps','half_spread_bps','slippage_bps']);
 fee:=vn_portable_economic_research.units(value->'fee_bps',6);
 spread:=vn_portable_economic_research.units(value->'half_spread_bps',6);
 slip:=vn_portable_economic_research.units(value->'slippage_bps',6);
 IF fee>=1e10 OR spread+slip>=1e10 THEN
  RAISE EXCEPTION 'economic_invalid_execution_config' USING ERRCODE='22023';
 END IF;
 RETURN value;
END $function$;

CREATE FUNCTION vn_portable_economic_research.policy(value jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE expected jsonb;
BEGIN
 expected:=jsonb_build_object('version','usd-reference-decimal-v2','account_currency','USD',
  'cost_assumptions','uncalibrated_scenario','valuation','reference_mark',
  'cash_scale',jsonb_build_object('$integer','36'),
  'quantity_scale',jsonb_build_object('$integer','18'),
  'price_scale',jsonb_build_object('$integer','18'),
  'bps_scale',jsonb_build_object('$integer','6'),
  'rounding',jsonb_build_object('buy_price','up','sell_price','down','quantity','down',
    'fee','up','residual','retain_cash'),
  'config',vn_portable_economic_research.configuration(value->'config'));
 IF value IS DISTINCT FROM expected THEN
  RAISE EXCEPTION 'economic_execution_policy_mismatch' USING ERRCODE='22023';
 END IF;
 RETURN value;
END $function$;

CREATE FUNCTION vn_portable_economic_research.entry(value jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE cfg jsonb; budget numeric; reference numeric; price numeric; quantity numeric;
 cap numeric; notional numeric; fee numeric; debit numeric; rate numeric; impact numeric; expected jsonb;
BEGIN
 PERFORM vn_portable_dependency_research.exact_keys(value,ARRAY['version','config','budget','reference_price',
  'fill_price','quantity','notional','fee','cash_debit','residual_budget']);
 cfg:=vn_portable_economic_research.configuration(value->'config');
 budget:=vn_portable_economic_research.units(value->'budget',36);
 reference:=vn_portable_economic_research.units(value->'reference_price',18);
 rate:=vn_portable_economic_research.units(cfg->'fee_bps',6);
 impact:=vn_portable_economic_research.units(cfg->'half_spread_bps',6)+vn_portable_economic_research.units(cfg->'slippage_bps',6);
 price:=div(reference*(1e10+impact)+1e10-1,1e10);
 cap:=div(budget*1e10,1e10+rate); quantity:=div(cap,nullif(price,0));
 notional:=quantity*price; fee:=div(notional*rate+1e10-1,1e10); debit:=notional+fee;
 IF budget<=0 OR reference<=0 OR price<=0 OR price>1e54 OR quantity IS NULL OR
    quantity<=0 OR quantity>1e54 OR notional<=0 OR debit>budget OR debit>1e72 THEN
  RAISE EXCEPTION 'economic_invalid_entry' USING ERRCODE='22023';
 END IF;
 expected:=jsonb_build_object('version','usd-reference-decimal-v2','config',cfg,
  'budget',vn_portable_economic_research.decimal_text(budget,36),
  'reference_price',vn_portable_economic_research.decimal_text(reference,18),
  'fill_price',vn_portable_economic_research.decimal_text(price,18),
  'quantity',vn_portable_economic_research.decimal_text(quantity,18),
  'notional',vn_portable_economic_research.decimal_text(notional,36),
  'fee',vn_portable_economic_research.decimal_text(fee,36),
  'cash_debit',vn_portable_economic_research.decimal_text(debit,36),
  'residual_budget',vn_portable_economic_research.decimal_text(budget-debit,36));
 IF value IS DISTINCT FROM expected THEN
  RAISE EXCEPTION 'economic_entry_mismatch' USING ERRCODE='22023';
 END IF;
 RETURN expected;
END $function$;

CREATE FUNCTION vn_portable_economic_research.exit(value jsonb,stored jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE original jsonb; cfg jsonb; reference numeric; quantity numeric; rate numeric;
 impact numeric; price numeric; notional numeric; fee numeric; credit numeric; expected jsonb;
BEGIN
 PERFORM vn_portable_dependency_research.exact_keys(value,ARRAY['version','entry','kind','reference_price',
  'fill_price','quantity','notional','fee','cash_credit','gross_pnl','net_pnl']);
 original:=vn_portable_economic_research.entry(value->'entry');
 IF stored IS NULL OR original IS DISTINCT FROM stored THEN
  RAISE EXCEPTION 'economic_original_entry_mismatch' USING ERRCODE='22023';
 END IF;
 -- This provider-GA profile only performs observed fills, never writeoffs.
 reference:=vn_portable_economic_research.units(value->'reference_price',18);
 cfg:=original->'config'; quantity:=vn_portable_economic_research.units(original->'quantity',18);
 rate:=vn_portable_economic_research.units(cfg->'fee_bps',6);
 impact:=vn_portable_economic_research.units(cfg->'half_spread_bps',6)+vn_portable_economic_research.units(cfg->'slippage_bps',6);
 price:=div(reference*(1e10-impact),1e10); notional:=quantity*price;
 fee:=div(notional*rate+1e10-1,1e10); credit:=notional-fee;
 IF reference<=0 OR price<=0 OR price>1e54 OR notional<=0 OR notional>1e72 OR credit<0 OR credit>1e72 THEN
  RAISE EXCEPTION 'economic_invalid_exit' USING ERRCODE='22023';
 END IF;
 expected:=jsonb_build_object('version','usd-reference-decimal-v2','entry',original,
  'kind','fill','reference_price',vn_portable_economic_research.decimal_text(reference,18),
  'fill_price',vn_portable_economic_research.decimal_text(price,18),'quantity',original->'quantity',
  'notional',vn_portable_economic_research.decimal_text(notional,36),
  'fee',vn_portable_economic_research.decimal_text(fee,36),'cash_credit',vn_portable_economic_research.decimal_text(credit,36),
  'gross_pnl',vn_portable_economic_research.decimal_text(notional-vn_portable_economic_research.units(original->'notional',36),36),
  'net_pnl',vn_portable_economic_research.decimal_text(credit-vn_portable_economic_research.units(original->'cash_debit',36),36));
 IF value IS DISTINCT FROM expected THEN
  RAISE EXCEPTION 'economic_exit_mismatch' USING ERRCODE='22023';
 END IF;
 RETURN expected;
END $function$;

CREATE FUNCTION vn_portable_economic_research.state(value jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE cfg jsonb; seed numeric; ids text[]:=ARRAY[]::text[]; ordered text[];
 accounts jsonb:='{}'; positions jsonb:='{}'; members jsonb:='{}'; roles jsonb:='{}';
 row jsonb; identity text; holder text; cash numeric; plan jsonb; held text[]:=ARRAY[]::text[];
BEGIN
 cfg:=vn_portable_economic_research.policy(value#>'{engine,config,execution}');
 seed:=vn_portable_economic_research.units(value#>'{engine,config,seed_capital}',36);
 PERFORM vn_portable_economic_research.units(value->'reserve',36);
 IF seed<=0 OR value#>>'{engine,config,asset}' IS DISTINCT FROM 'SOL/USD' OR
    jsonb_typeof(value->'accounts') IS DISTINCT FROM 'array' OR jsonb_array_length(value->'accounts')<>8 OR
    jsonb_typeof(value->'positions') IS DISTINCT FROM 'array' OR jsonb_array_length(value->'positions')>8 THEN
  RAISE EXCEPTION 'economic_state_capacity_or_profile' USING ERRCODE='22023';
 END IF;
 FOR row IN SELECT v FROM jsonb_array_elements(value#>'{engine,members}') a(v) LOOP
  identity:=vn_portable_dependency_research.uuid_text(row->'id');
  members:=members||jsonb_build_object(identity,row);
 END LOOP;
 FOR row IN SELECT v FROM jsonb_array_elements(value->'accounts') a(v) LOOP
  PERFORM vn_portable_dependency_research.exact_keys(row,ARRAY['id','cash','initial_cash','retired']);
  identity:=vn_portable_dependency_research.uuid_text(row->'id');
  cash:=vn_portable_economic_research.units(row->'cash',36);
  IF accounts ? identity OR NOT members ? identity OR
     vn_portable_economic_research.units(row->'initial_cash',36)<>seed OR
     jsonb_typeof(row->'retired') IS DISTINCT FROM 'boolean' OR
     (row->'retired'='true'::jsonb) IS DISTINCT FROM (members#>ARRAY[identity,'terminal']<>'null'::jsonb) OR
     (row->'retired'='true'::jsonb AND cash<>0) THEN
   RAISE EXCEPTION 'economic_account_binding' USING ERRCODE='22023';
  END IF;
  PERFORM vn_portable_dependency_research.counter(members#>ARRAY[identity,'num_trades'],0,9223372036854775806);
  ids:=array_append(ids,identity); accounts:=accounts||jsonb_build_object(identity,row);
  roles:=roles||jsonb_build_object(identity,'account');
 END LOOP;
 SELECT array_agg(x ORDER BY x COLLATE "C") INTO ordered FROM unnest(ids) x;
 IF ordered IS DISTINCT FROM ids THEN
  RAISE EXCEPTION 'economic_account_order' USING ERRCODE='22023';
 END IF;
 ids:=ARRAY[]::text[];
 FOR row IN SELECT v FROM jsonb_array_elements(value->'positions') a(v) LOOP
  PERFORM vn_portable_dependency_research.exact_keys(row,ARRAY['id','account_id','asset','entry','exit','closed']);
  identity:=vn_portable_dependency_research.uuid_text(row->'id');
  holder:=vn_portable_dependency_research.uuid_text(row->'account_id');
  plan:=vn_portable_economic_research.entry(row->'entry');
  IF positions ? identity OR roles ? identity OR NOT accounts ? holder OR holder=ANY(held) OR
     accounts#>ARRAY[holder,'retired']<>'false'::jsonb OR
     row->'asset' IS DISTINCT FROM value#>'{engine,config,asset}' OR
     plan->'config' IS DISTINCT FROM cfg->'config' OR
     row->'exit' IS DISTINCT FROM 'null'::jsonb OR row->'closed' IS DISTINCT FROM 'false'::jsonb THEN
   RAISE EXCEPTION 'economic_position_binding' USING ERRCODE='22023';
  END IF;
  ids:=array_append(ids,identity); held:=array_append(held,holder);
  positions:=positions||jsonb_build_object(identity,row);
  roles:=roles||jsonb_build_object(identity,'position');
 END LOOP;
 SELECT coalesce(array_agg(x ORDER BY x COLLATE "C"),ARRAY[]::text[]) INTO ordered FROM unnest(ids) x;
 IF ordered IS DISTINCT FROM ids THEN
  RAISE EXCEPTION 'economic_position_order' USING ERRCODE='22023';
 END IF;
 IF value#>'{engine,lifecycle,risk,trip_id}' IS NULL THEN
  RAISE EXCEPTION 'economic_risk_identity_required' USING ERRCODE='22023';
 END IF;
 IF value#>'{engine,lifecycle,risk,trip_id}'<>'null'::jsonb THEN
  identity:=vn_portable_dependency_research.uuid_text(value#>'{engine,lifecycle,risk,trip_id}');
  IF roles ? identity THEN
   RAISE EXCEPTION 'economic_identity_role_conflict' USING ERRCODE='22023';
  END IF;
  roles:=roles||jsonb_build_object(identity,'risk');
 END IF;
 RETURN jsonb_build_object('accounts',accounts,'positions',positions,'members',members,'roles',roles);
END $function$;

CREATE FUNCTION vn_portable_economic_research.transition(request jsonb,previous jsonb,following jsonb)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $function$
DECLARE prior jsonb; after jsonb; history jsonb:=request->'history'; cfg jsonb;
 accounts jsonb:='{}'; positions jsonb:='{}'; old_roles jsonb:='{}'; new_roles jsonb:='{}';
 trade_counts jsonb:='{}'; retired jsonb:='[]'; closed jsonb:='[]'; births jsonb:='[]';
 allocated text[]:=ARRAY[]::text[]; birth_ids text[]:=ARRAY[]::text[]; declared text[]:=ARRAY[]::text[];
 reserve numeric; seed numeric; cash numeric; new_cash numeric; op jsonb; row jsonb; member jsonb;
 kind text; identity text; holder text; plan jsonb; expected jsonb; action jsonb; event jsonb;
 idx integer:=0; seen_events integer[]:=ARRAY[]::integer[]; event_idx integer;
 reference jsonb; old_trip jsonb; new_trip jsonb; role record; expected_accounts jsonb;
 expected_positions jsonb; previous_count bigint; count_closed bigint;
BEGIN
 after:=vn_portable_economic_research.state(following);
 cfg:=following#>'{engine,config,execution,config}';
 seed:=vn_portable_economic_research.units(following#>'{engine,config,seed_capital}',36);
 IF previous IS NULL THEN
  reserve:=vn_portable_economic_research.units(following#>'{engine,config,initial_cash}',36);
  IF reserve<=0 OR request#>>'{evidence,kind}' IS DISTINCT FROM 'bootstrap' THEN
   RAISE EXCEPTION 'economic_bootstrap_binding' USING ERRCODE='22023';
  END IF;
 ELSE
  prior:=vn_portable_economic_research.state(previous);
  accounts:=prior->'accounts'; positions:=prior->'positions'; old_roles:=prior->'roles';
  reserve:=vn_portable_economic_research.units(previous->'reserve',36);
 END IF;
 PERFORM vn_portable_dependency_research.exact_keys(history,ARRAY['owner_id','run_id','revision',
  'allocated_ids','closed_positions','birth_members','retired_accounts','assessments','selection']);
 IF history->'owner_id' IS DISTINCT FROM following->'owner_id' OR
    history->'run_id' IS DISTINCT FROM following->'run_id' OR
    history->'revision' IS DISTINCT FROM following->'revision' THEN
  RAISE EXCEPTION 'economic_history_scope' USING ERRCODE='22023';
 END IF;
 FOR role IN SELECT * FROM (VALUES ('allocated_ids',17),('closed_positions',8),
   ('birth_members',8),('retired_accounts',8),('assessments',8)) a(key,maximum) LOOP
  IF jsonb_typeof(history->role.key) IS DISTINCT FROM 'array' OR
     jsonb_array_length(history->role.key)>role.maximum THEN
   RAISE EXCEPTION 'economic_history_capacity' USING ERRCODE='22023';
  END IF;
 END LOOP;
 IF jsonb_typeof(request->'operations') IS DISTINCT FROM 'array' OR
    jsonb_array_length(request->'operations')>33 OR
    jsonb_typeof(request#>'{evidence,actions}') IS DISTINCT FROM 'array' OR
    jsonb_array_length(request#>'{evidence,actions}')<>jsonb_array_length(request->'operations') OR
    jsonb_typeof(request->'events') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION 'economic_operation_action_capacity' USING ERRCODE='22023';
 END IF;
 FOR op IN SELECT v FROM jsonb_array_elements(request->'operations') a(v) LOOP
  kind:=op->>'kind'; identity:=NULL; holder:=NULL; reference:='null'::jsonb;
  action:=request#>ARRAY['evidence','actions',idx::text];
  PERFORM vn_portable_dependency_research.exact_keys(action,ARRAY['operation_index','reason',
    'account_id','position_id','signal_at','reference_price']);
  IF vn_portable_dependency_research.counter(action->'operation_index',0,32)<>idx OR
     jsonb_typeof(action->'reason') IS DISTINCT FROM 'string' OR length(action->>'reason') NOT BETWEEN 1 AND 64 THEN
   RAISE EXCEPTION 'economic_action_index' USING ERRCODE='22023';
  END IF;
  IF kind='birth' THEN
   PERFORM vn_portable_dependency_research.exact_keys(op,ARRAY['kind','id','cash','lineage']);
   identity:=vn_portable_dependency_research.uuid_text(op->'id'); holder:=identity;
   cash:=vn_portable_economic_research.units(op->'cash',36);
   IF accounts ? identity OR old_roles ? identity OR new_roles ? identity OR cash<>seed OR cash>reserve OR
      op#>'{lineage,child_id}' IS DISTINCT FROM op->'id' OR
      op#>>'{lineage,strategy}' IS DISTINCT FROM 'genetic_algorithm' THEN
    RAISE EXCEPTION 'economic_birth_binding' USING ERRCODE='22023';
   END IF;
   reserve:=reserve-cash;
   accounts:=accounts||jsonb_build_object(identity,jsonb_build_object('id',identity,
    'cash',vn_portable_economic_research.decimal_text(cash,36),'initial_cash',op->'cash','retired',false));
   new_roles:=new_roles||jsonb_build_object(identity,'account');
   allocated:=array_append(allocated,identity); birth_ids:=array_append(birth_ids,identity);
  ELSIF kind='open' THEN
   PERFORM vn_portable_dependency_research.exact_keys(op,ARRAY['kind','id','account_id','asset','quantity','notional','fee','execution']);
   identity:=vn_portable_dependency_research.uuid_text(op->'id');
   holder:=vn_portable_dependency_research.uuid_text(op->'account_id');
   plan:=vn_portable_economic_research.entry(op->'execution');
   cash:=vn_portable_economic_research.units(accounts#>ARRAY[holder,'cash'],36);
   IF NOT accounts ? holder OR accounts#>ARRAY[holder,'retired'] IS DISTINCT FROM 'false'::jsonb OR
      positions ? identity OR old_roles ? identity OR new_roles ? identity OR
      EXISTS(SELECT 1 FROM jsonb_each(positions) p WHERE p.value->>'account_id'=holder) OR
      plan->'config' IS DISTINCT FROM cfg OR op->'asset' IS DISTINCT FROM following#>'{engine,config,asset}' OR
      plan->>'budget' IS DISTINCT FROM vn_portable_economic_research.decimal_text(div(cash,4),36) OR
      plan->'reference_price' IS DISTINCT FROM request#>'{evidence,observation,price}' OR
      op->'quantity' IS DISTINCT FROM plan->'quantity' OR op->'fee' IS DISTINCT FROM plan->'fee' OR
      op->'notional' IS DISTINCT FROM plan->'notional' THEN
    RAISE EXCEPTION 'economic_open_binding' USING ERRCODE='22023';
   END IF;
   new_cash:=cash-vn_portable_economic_research.units(plan->'cash_debit',36);
   accounts:=jsonb_set(accounts,ARRAY[holder,'cash'],to_jsonb(vn_portable_economic_research.decimal_text(new_cash,36)));
   positions:=positions||jsonb_build_object(identity,jsonb_build_object('id',identity,
    'account_id',holder,'asset',op->'asset','entry',plan,'exit',NULL,'closed',false));
   new_roles:=new_roles||jsonb_build_object(identity,'position'); allocated:=array_append(allocated,identity);
   reference:=plan->'reference_price';
  ELSIF kind='close' THEN
   PERFORM vn_portable_dependency_research.exact_keys(op,ARRAY['kind','id','proceeds','fee','execution']);
   identity:=vn_portable_dependency_research.uuid_text(op->'id'); row:=positions->identity;
   IF row IS NULL THEN RAISE EXCEPTION 'economic_close_unavailable' USING ERRCODE='22023'; END IF;
   holder:=row->>'account_id'; plan:=vn_portable_economic_research.exit(op->'execution',row->'entry');
   IF op->'proceeds' IS DISTINCT FROM plan->'notional' OR op->'fee' IS DISTINCT FROM plan->'fee' OR
      plan->'reference_price' IS DISTINCT FROM request#>'{evidence,observation,price}' THEN
    RAISE EXCEPTION 'economic_close_binding' USING ERRCODE='22023';
   END IF;
   cash:=vn_portable_economic_research.units(accounts#>ARRAY[holder,'cash'],36);
   new_cash:=cash+vn_portable_economic_research.units(plan->'cash_credit',36);
   IF new_cash>1e72 THEN RAISE EXCEPTION 'economic_cash_overflow' USING ERRCODE='22023'; END IF;
   accounts:=jsonb_set(accounts,ARRAY[holder,'cash'],to_jsonb(vn_portable_economic_research.decimal_text(new_cash,36)));
   positions:=positions-identity; closed:=closed||jsonb_build_array(row||jsonb_build_object('exit',plan,'closed',true));
   count_closed:=coalesce((trade_counts->>holder)::bigint,0)+1;
   trade_counts:=trade_counts||jsonb_build_object(holder,count_closed);
   reference:=plan->'reference_price';
  ELSIF kind='retire' THEN
   PERFORM vn_portable_dependency_research.exact_keys(op,ARRAY['kind','id']);
   identity:=vn_portable_dependency_research.uuid_text(op->'id'); holder:=identity; row:=accounts->identity;
   IF row IS NULL OR row->'retired' IS DISTINCT FROM 'false'::jsonb OR
      NOT old_roles ? identity OR old_roles->>identity<>'account' OR
      EXISTS(SELECT 1 FROM jsonb_each(positions) p WHERE p.value->>'account_id'=identity) THEN
    RAISE EXCEPTION 'economic_retire_binding' USING ERRCODE='22023';
   END IF;
   retired:=retired||jsonb_build_array(row);
   reserve:=reserve+vn_portable_economic_research.units(row->'cash',36);
   IF reserve>1e72 THEN RAISE EXCEPTION 'economic_reserve_overflow' USING ERRCODE='22023'; END IF;
   accounts:=jsonb_set(accounts,ARRAY[identity],row||jsonb_build_object('cash','0','retired',true));
  ELSIF kind='lifecycle' THEN
   PERFORM vn_portable_dependency_research.exact_keys(op,ARRAY['kind','status']);
   IF op->'status' IS DISTINCT FROM following->'status' THEN
    RAISE EXCEPTION 'economic_lifecycle_status_binding' USING ERRCODE='22023';
   END IF;
  ELSE
   RAISE EXCEPTION 'economic_unknown_operation' USING ERRCODE='22023';
  END IF;
  IF (kind='birth' AND action->>'reason' NOT IN ('founder','birth','restart_birth')) OR
     (kind='open' AND action->>'reason'<>'entry_signal') OR
     (kind='close' AND action->>'reason' NOT IN ('stop_loss','take_profit','exit_signal',
        'cohort_liquidation','death_liquidation','restart_liquidation')) OR
     (kind='retire' AND action->>'reason' NOT IN ('terminal','retire','restart_retire')) OR
     (kind='lifecycle' AND action->>'reason' NOT IN ('lifecycle','risk_halt','pause','resume','stop','recover')) THEN
   RAISE EXCEPTION 'economic_action_reason' USING ERRCODE='22023';
  END IF;
  IF action->'account_id' IS DISTINCT FROM to_jsonb(holder) AND
     NOT(holder IS NULL AND action->'account_id'='null'::jsonb) THEN
   RAISE EXCEPTION 'economic_action_account' USING ERRCODE='22023';
  END IF;
  IF action->'position_id' IS DISTINCT FROM (CASE WHEN kind IN ('open','close') THEN op->'id' ELSE 'null'::jsonb END) OR
     action->'reference_price' IS DISTINCT FROM reference THEN
   RAISE EXCEPTION 'economic_action_position_or_price' USING ERRCODE='22023';
  END IF;
  idx:=idx+1;
 END LOOP;
 FOR event IN SELECT v FROM jsonb_array_elements(request->'events') a(v) LOOP
  PERFORM vn_portable_dependency_research.exact_keys(event,ARRAY['kind','at','account_id','position_id','operation_index']);
  IF event->'operation_index'<>'null'::jsonb THEN
   event_idx:=vn_portable_dependency_research.counter(event->'operation_index',0,32);
   IF event_idx>=idx OR event_idx<>cardinality(seen_events) THEN
    RAISE EXCEPTION 'economic_event_index' USING ERRCODE='22023';
   END IF;
   action:=request#>ARRAY['evidence','actions',event_idx::text];
   IF event->'kind' IS DISTINCT FROM action->'reason' OR
      event->'account_id' IS DISTINCT FROM action->'account_id' OR
      event->'position_id' IS DISTINCT FROM action->'position_id' THEN
    RAISE EXCEPTION 'economic_event_binding' USING ERRCODE='22023';
   END IF;
   seen_events:=array_append(seen_events,event_idx);
  ELSIF event->>'kind' NOT IN ('evaluation','evaluation_aborted') OR
        event->'account_id' IS DISTINCT FROM 'null'::jsonb OR
        event->'position_id' IS DISTINCT FROM 'null'::jsonb THEN
   RAISE EXCEPTION 'economic_extra_event_shape' USING ERRCODE='22023';
  END IF;
 END LOOP;
 IF cardinality(seen_events)<>idx THEN RAISE EXCEPTION 'economic_missing_event' USING ERRCODE='22023'; END IF;
 new_trip:=following#>'{engine,lifecycle,risk,trip_id}'; old_trip:=previous#>'{engine,lifecycle,risk,trip_id}';
 IF new_trip<>'null'::jsonb AND new_trip IS DISTINCT FROM old_trip THEN
  identity:=vn_portable_dependency_research.uuid_text(new_trip);
  IF old_roles ? identity OR new_roles ? identity THEN
   RAISE EXCEPTION 'economic_identity_role_conflict' USING ERRCODE='22023';
  END IF;
  new_roles:=new_roles||jsonb_build_object(identity,'risk'); allocated:=array_append(allocated,identity);
 END IF;
 FOR row IN SELECT v FROM jsonb_array_elements(history->'allocated_ids') a(v) LOOP
  identity:=vn_portable_dependency_research.uuid_text(row);
  IF identity=ANY(declared) THEN RAISE EXCEPTION 'economic_duplicate_allocation' USING ERRCODE='22023'; END IF;
  declared:=array_append(declared,identity);
 END LOOP;
 IF cardinality(declared)<>cardinality(allocated) OR
    EXISTS(SELECT 1 FROM unnest(declared) x WHERE NOT x=ANY(allocated)) OR
    jsonb_typeof(request#>'{evidence,inputs,ids}') IS DISTINCT FROM 'array' OR
    (SELECT coalesce(jsonb_agg(v ORDER BY ordinal),'[]') FROM
      jsonb_array_elements(request#>'{evidence,inputs,ids}') WITH ORDINALITY a(v,ordinal)
      WHERE ordinal<=cardinality(declared)) IS DISTINCT FROM to_jsonb(declared) THEN
  RAISE EXCEPTION 'economic_allocation_binding' USING ERRCODE='22023';
 END IF;
 FOR role IN SELECT key,value FROM jsonb_each(accounts) LOOP
  IF NOT (after->'accounts') ? role.key AND
     (role.value->'retired'<>'true'::jsonb OR role.value->>'cash'<>'0') THEN
   RAISE EXCEPTION 'economic_removed_live_account' USING ERRCODE='22023';
  END IF;
 END LOOP;
 SELECT coalesce(jsonb_agg(a.value ORDER BY a.key COLLATE "C"),'[]') INTO expected_accounts
  FROM jsonb_each(accounts) a WHERE (after->'members') ? a.key;
 SELECT coalesce(jsonb_agg(a.value ORDER BY a.key COLLATE "C"),'[]') INTO expected_positions FROM jsonb_each(positions) a;
 IF following->>'reserve' IS DISTINCT FROM vn_portable_economic_research.decimal_text(reserve,36) OR
    following->'accounts' IS DISTINCT FROM expected_accounts OR following->'positions' IS DISTINCT FROM expected_positions THEN
  RAISE EXCEPTION 'economic_complete_cash_or_holding_mismatch' USING ERRCODE='22023';
 END IF;
 SELECT coalesce(jsonb_agg(v ORDER BY v->>'id' COLLATE "C"),'[]') INTO expected FROM jsonb_array_elements(closed) a(v);
 IF history->'closed_positions' IS DISTINCT FROM expected OR jsonb_array_length(history->'retired_accounts')<>jsonb_array_length(retired) THEN
  RAISE EXCEPTION 'economic_closed_or_retired_history_mismatch' USING ERRCODE='22023';
 END IF;
 idx:=0;
 FOR row IN SELECT v FROM jsonb_array_elements(history->'retired_accounts') a(v) LOOP
  PERFORM vn_portable_dependency_research.exact_keys(row,ARRAY['account','member']);
  identity:=row#>>'{account,id}'; member:=row->'member';
  PERFORM vn_portable_dependency_research.exact_keys(member,ARRAY['id','name','genome','cursor','pending',
    'num_trades','peak_equity','max_drawdown','terminal','assessment']);
  IF row->'account' IS DISTINCT FROM retired->idx OR member->>'id' IS DISTINCT FROM identity OR
     member->'genome' IS DISTINCT FROM prior#>ARRAY['members',identity,'genome'] OR
     member->'name' IS DISTINCT FROM prior#>ARRAY['members',identity,'name'] THEN
   RAISE EXCEPTION 'economic_retired_snapshot_mismatch' USING ERRCODE='22023';
  END IF;
  IF member->'terminal'<>'null'::jsonb AND
     member#>'{terminal,cash}' IS DISTINCT FROM row#>'{account,cash}' THEN
   RAISE EXCEPTION 'economic_terminal_cash_mismatch' USING ERRCODE='22023';
  END IF;
  IF (after->'members') ? identity AND
     member->'terminal' IS DISTINCT FROM after#>ARRAY['members',identity,'terminal'] THEN
   RAISE EXCEPTION 'economic_terminal_snapshot_mismatch' USING ERRCODE='22023';
  END IF;
  previous_count:=vn_portable_dependency_research.counter(prior#>ARRAY['members',identity,'num_trades'],0,9223372036854775806);
  IF vn_portable_dependency_research.counter(member->'num_trades',0,9223372036854775806)<>previous_count::numeric+coalesce((trade_counts->>identity)::numeric,0) THEN
   RAISE EXCEPTION 'economic_trade_count_mismatch' USING ERRCODE='22023';
  END IF;
  idx:=idx+1;
 END LOOP;
 FOR member IN SELECT v FROM jsonb_array_elements(following#>'{engine,members}') a(v) LOOP
  identity:=member->>'id';
  IF identity=ANY(birth_ids) THEN
   births:=births||jsonb_build_array(member);
   previous_count:=0;
   IF member->'terminal' IS DISTINCT FROM 'null'::jsonb OR member->'assessment' IS DISTINCT FROM 'null'::jsonb OR
      member->'pending' IS DISTINCT FROM 'null'::jsonb OR
      member->'peak_equity' IS DISTINCT FROM following#>'{engine,config,seed_capital}' OR
      member->'max_drawdown' IS DISTINCT FROM '{"numerator":"0","denominator":"1"}'::jsonb THEN
    RAISE EXCEPTION 'economic_newborn_metrics_mismatch' USING ERRCODE='22023';
   END IF;
  ELSE
   previous_count:=vn_portable_dependency_research.counter(prior#>ARRAY['members',identity,'num_trades'],0,9223372036854775806);
   IF prior#>ARRAY['members',identity,'terminal']<>'null'::jsonb AND
      (member->'terminal' IS DISTINCT FROM prior#>ARRAY['members',identity,'terminal'] OR
       member->'assessment' IS DISTINCT FROM prior#>ARRAY['members',identity,'assessment']) THEN
    RAISE EXCEPTION 'economic_frozen_terminal_mismatch' USING ERRCODE='22023';
   END IF;
  END IF;
  IF vn_portable_dependency_research.counter(member->'num_trades',0,9223372036854775806)<>previous_count::numeric+coalesce((trade_counts->>identity)::numeric,0) THEN
   RAISE EXCEPTION 'economic_trade_count_mismatch' USING ERRCODE='22023';
  END IF;
 END LOOP;
 IF history->'birth_members' IS DISTINCT FROM births OR
    (cardinality(birth_ids) NOT IN (0,8)) OR
    (previous IS NULL AND cardinality(birth_ids)<>8) OR
    (previous IS NOT NULL AND (cardinality(birth_ids)=8) IS DISTINCT FROM
      (following#>'{engine,generation}' IS DISTINCT FROM previous#>'{engine,generation}')) OR
    (cardinality(birth_ids)=8 AND
      (SELECT jsonb_agg(v->'id') FROM jsonb_array_elements(following#>'{engine,members}') a(v)) IS DISTINCT FROM to_jsonb(birth_ids)) THEN
  RAISE EXCEPTION 'economic_birth_history_or_generation_mismatch' USING ERRCODE='22023';
 END IF;
 RETURN jsonb_build_object('allocated',new_roles,'prior_roles',old_roles,
  'reserve',vn_portable_economic_research.decimal_text(reserve,36),
  'closed_count',jsonb_array_length(closed),'retired_count',jsonb_array_length(retired),'birth_count',cardinality(birth_ids));
END $function$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_portable_economic_research FROM PUBLIC;
