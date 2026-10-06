-- DB-03A2D3 isolated projection/relay/archive rehearsal ONLY.
-- Not a migration. No application startup or legacy grants are changed here.
BEGIN;
SET LOCAL lock_timeout='3s';
SET LOCAL statement_timeout='15s';
DO $$ BEGIN
 IF current_setting('dashboard.contract_rehearsal',true) IS DISTINCT FROM 'db03a1-isolated' THEN
  RAISE EXCEPTION 'isolated_contract_runner_required';
 END IF;
END $$;
CREATE SCHEMA vn_projection AUTHORIZATION vn_contract_owner;
CREATE SCHEMA vn_read AUTHORIZATION vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM vn_durability.commands) THEN
  RAISE EXCEPTION 'fresh_contract_required_no_async_backfill';
 END IF;
END $$;

CREATE TABLE vn_projection.runs (
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=8192),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE INDEX runs_owner_page ON vn_projection.runs(user_id,run_id,revision,entity_key);
ALTER TABLE vn_projection.runs ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.probes (
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=4096),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE INDEX probes_owner_page ON vn_projection.probes(user_id,run_id,revision,entity_key);
CREATE INDEX probes_entity_versions ON vn_projection.probes(run_id,entity_key,revision DESC);
ALTER TABLE vn_projection.probes ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.trades (
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=8192),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE INDEX trades_owner_page ON vn_projection.trades(user_id,run_id,revision,entity_key);
CREATE INDEX trades_entity_versions ON vn_projection.trades(run_id,(data->>'id'),revision DESC,entity_key DESC);
ALTER TABLE vn_projection.trades ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.samples (
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=4096),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE INDEX samples_owner_page ON vn_projection.samples(user_id,run_id,revision,entity_key);
ALTER TABLE vn_projection.samples ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.evaluations (
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=32768),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE INDEX evaluations_owner_page ON vn_projection.evaluations(user_id,run_id,revision,entity_key);
ALTER TABLE vn_projection.evaluations ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.relay_events (
 sequence bigint NOT NULL CHECK(sequence>0),
 user_id uuid NOT NULL, run_id uuid NOT NULL, revision bigint NOT NULL,
 command_id uuid NOT NULL, entity_key text NOT NULL CHECK(octet_length(entity_key) BETWEEN 1 AND 256),
 data jsonb NOT NULL CHECK(jsonb_typeof(data)='object' AND octet_length(data::text)<=4096),
 PRIMARY KEY(run_id,revision,entity_key),
 FOREIGN KEY(run_id,user_id,command_id,revision) REFERENCES vn_durability.commands(run_id,user_id,id,revision)
);
CREATE UNIQUE INDEX relay_events_owner_page ON vn_projection.relay_events(user_id,run_id,sequence);
CREATE UNIQUE INDEX relay_events_identity ON vn_projection.relay_events(run_id,entity_key);
ALTER TABLE vn_projection.relay_events ENABLE ROW LEVEL SECURITY;

CREATE TABLE vn_projection.archives (
 user_id uuid NOT NULL, run_id uuid NOT NULL, expected_revision bigint NOT NULL,
 request_id uuid NOT NULL, archived_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 receipt jsonb NOT NULL CHECK(jsonb_typeof(receipt)='object' AND octet_length(receipt::text)<=2048),
 PRIMARY KEY(user_id,request_id), UNIQUE(run_id),
 FOREIGN KEY(run_id,user_id) REFERENCES vn_durability.runs(id,user_id)
);
ALTER TABLE vn_projection.archives ENABLE ROW LEVEL SECURITY;

-- Called only by the journal INSERT trigger under the trusted command owner.
-- Never project from socket events, browser payloads or asynchronously mutated state.
CREATE FUNCTION vn_projection.project_command() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE state vn_durability.runs%ROWTYPE; transition jsonb; before_state jsonb; after_state jsonb;
 member jsonb; prior jsonb; account jsonb; operation jsonb; action jsonb; item jsonb; position jsonb;
 working_cash jsonb:='{}'::jsonb; terminal_cash jsonb:='{}'::jsonb;
 row_data jsonb; old_data jsonb; entity uuid; cash numeric; equity numeric; mark numeric;
 stamp jsonb; source_stamp jsonb; index integer:=0; observation jsonb; evaluation jsonb; cohort jsonb;
 run_equity numeric; open_count integer;
BEGIN
 SELECT * INTO STRICT state FROM vn_durability.runs WHERE id=NEW.run_id AND user_id=NEW.user_id;
 IF state.command_version NOT IN(3,4,5) THEN RETURN NEW; END IF;
 IF state.revision<>NEW.revision THEN RAISE EXCEPTION 'projection_revision_mismatch'; END IF;
 transition:=NEW.request#>'{payload,transition}';
 before_state:=transition->'before'; after_state:=transition->'after';
 observation:=transition#>'{evidence,observation}';
 stamp:=transition#>'{evidence,inputs,market_at}';
 IF stamp IS NULL THEN stamp:=transition#>'{evidence,inputs,quote_at}'; END IF;
 -- Event timestamps are validated by the underlying transition contract.
 source_stamp:=after_state#>'{engine,last_quote,timestamp}';
 IF observation IS NOT NULL AND observation<>'null'::jsonb THEN mark:=(observation->>'price')::numeric;
 ELSE mark:=(after_state#>>'{engine,last_quote,price}')::numeric; END IF;
 IF NEW.kind='batch' THEN
  IF after_state IS NULL OR after_state->>'run_id'<>NEW.run_id::text OR (after_state->>'revision')::bigint<>NEW.revision
   THEN RAISE EXCEPTION 'projection_checkpoint_mismatch'; END IF;
  FOR account IN SELECT v FROM jsonb_array_elements(coalesce(before_state->'accounts','[]'::jsonb)) q(v) LOOP
   working_cash:=jsonb_set(working_cash,ARRAY[account->>'id'],account->'cash');
  END LOOP;
  FOR operation IN SELECT v FROM jsonb_array_elements(NEW.request#>'{payload,operations}') q(v) LOOP
   entity:=(operation->>'id')::uuid;
   action:=transition#>'{evidence,actions}'->index;
   IF action->>'operation_index' IS DISTINCT FROM index::text THEN RAISE EXCEPTION 'projection_action_mismatch'; END IF;
   stamp:=transition->'events'->index->'at';
   -- Event order is not operation order when evaluation precedes retirements.
   SELECT v->'at' INTO stamp FROM jsonb_array_elements(transition->'events') q(v)
    WHERE v->>'operation_index'=index::text;
   IF operation->>'kind'='birth' THEN
    working_cash:=jsonb_set(working_cash,ARRAY[entity::text],operation->'cash');
   ELSIF operation->>'kind'='open' THEN
    cash:=(working_cash->>(operation->>'account_id'))::numeric-(operation->>'notional')::numeric-(operation->>'fee')::numeric;
    working_cash:=jsonb_set(working_cash,ARRAY[operation->>'account_id'],to_jsonb(cash::text));
    row_data:=jsonb_build_object('id',entity,'account_id',operation->'account_id','asset',operation->'asset',
     'opened_at',stamp,'closed_at',NULL,'entry_reason',action->'reason','exit_reason',NULL,
     'quantity',operation->'quantity','entry',operation->'execution','exit',NULL,'closed',false,
     'account_currency','USD','cost_assumptions','uncalibrated_scenario');
    INSERT INTO vn_projection.trades VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,entity::text||':'||lpad(index::text,4,'0'),row_data);
   ELSIF operation->>'kind'='close' THEN
    SELECT to_jsonb(p) INTO STRICT position FROM vn_durability.positions p WHERE p.run_id=NEW.run_id AND p.id=entity;
    cash:=(working_cash->>(position->>'account_id'))::numeric+(operation->>'proceeds')::numeric-(operation->>'fee')::numeric;
    working_cash:=jsonb_set(working_cash,ARRAY[position->>'account_id'],to_jsonb(cash::text));
    SELECT data INTO STRICT old_data FROM vn_projection.trades WHERE run_id=NEW.run_id AND data->>'id'=entity::text ORDER BY revision DESC,entity_key DESC LIMIT 1;
    row_data:=old_data||jsonb_build_object('closed',true,'closed_at',stamp,'exit_reason',action->'reason','exit',operation->'execution');
    INSERT INTO vn_projection.trades VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,entity::text||':'||lpad(index::text,4,'0'),row_data);
   ELSIF operation->>'kind'='retire' THEN
    IF NOT working_cash ? entity::text THEN RAISE EXCEPTION 'projection_missing_terminal_cash'; END IF;
    terminal_cash:=jsonb_set(terminal_cash,ARRAY[entity::text],working_cash->entity::text);
    working_cash:=jsonb_set(working_cash,ARRAY[entity::text],to_jsonb('0'::text));
   END IF;
   index:=index+1;
  END LOOP;
  -- Validate reconstruction before retaining the pre-transfer terminal values.
  FOR account IN SELECT v FROM jsonb_array_elements(after_state->'accounts') q(v) LOOP
   IF (working_cash->>(account->>'id'))::numeric IS DISTINCT FROM (account->>'cash')::numeric THEN
    RAISE EXCEPTION 'projection_cash_reconstruction_mismatch';
   END IF;
  END LOOP;
  FOR member IN SELECT v FROM jsonb_array_elements(after_state#>'{engine,members}') q(v) LOOP
   entity:=(member->>'id')::uuid;
   SELECT v INTO STRICT account FROM jsonb_array_elements(after_state->'accounts') q(v) WHERE v->>'id'=entity::text;
   SELECT data INTO old_data FROM vn_projection.probes WHERE run_id=NEW.run_id AND entity_key=entity::text ORDER BY revision DESC LIMIT 1;
   equity:=(account->>'cash')::numeric;
   IF mark IS NOT NULL THEN
    SELECT equity+coalesce(sum(p.quantity*mark),0) INTO equity FROM vn_durability.positions p
     WHERE p.run_id=NEW.run_id AND p.account_id=entity AND NOT p.closed;
   END IF;
   row_data:=jsonb_build_object('id',entity,'name',member->'name','generation',member#>'{genome,generation}',
    'genome',member->'genome','initial_cash',account->'initial_cash','economic_cash',account->'cash',
    'retired',account->'retired','terminal_cash',coalesce(terminal_cash->entity::text,member#>'{terminal,cash}',old_data->'terminal_cash','null'::jsonb),
    'equity',CASE WHEN account->>'retired'='true' THEN NULL ELSE equity::text END,
    'equity_basis',CASE WHEN account->>'retired'='true' THEN 'terminal_frozen' WHEN mark IS NULL THEN 'cash_without_market_mark' ELSE 'reference_mark' END,
    'metrics_basis','checkpoint_member','peak_equity',member->'peak_equity','max_drawdown',member->'max_drawdown','closed_trades',member->'num_trades',
    'terminal',member->'terminal','account_currency','USD','mark',CASE WHEN mark IS NULL THEN NULL ELSE mark::text END,
    'source_at',source_stamp,'fitness',NULL,'fitness_availability','evaluation_only',
    'lineage',(SELECT evidence FROM vn_durability.account_lineage WHERE run_id=NEW.run_id AND account_id=entity));
   INSERT INTO vn_projection.probes VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,entity::text,row_data);
   IF transition#>>'{evidence,kind}'='protective' THEN
    INSERT INTO vn_projection.samples VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,entity::text,
     jsonb_build_object('id',entity,'at',source_stamp,'equity',row_data->'equity','terminal_cash',row_data->'terminal_cash',
      'economic_cash',account->'cash','mark',row_data->'mark','account_currency','USD','sampling_policy','post_protection_pre_decision_v1',
      'equity_basis',row_data->'equity_basis','quote_sequence',after_state#>'{source,quote_sequence}'));
   END IF;
  END LOOP;
  -- Members removed by replacement require immutable terminal versions too.
  FOR member IN SELECT v FROM jsonb_array_elements(coalesce(before_state#>'{engine,members}','[]'::jsonb)) q(v)
   WHERE NOT EXISTS(SELECT 1 FROM jsonb_array_elements(after_state#>'{engine,members}') q2(m) WHERE m->>'id'=v->>'id') LOOP
   entity:=(member->>'id')::uuid;
   SELECT data INTO STRICT old_data FROM vn_projection.probes WHERE run_id=NEW.run_id AND entity_key=entity::text ORDER BY revision DESC LIMIT 1;
   IF NOT terminal_cash ? entity::text AND old_data->'terminal_cash'='null'::jsonb THEN RAISE EXCEPTION 'projection_missing_retirement_evidence'; END IF;
   row_data:=old_data||jsonb_build_object('economic_cash','0','equity',NULL,'retired',true,
     'terminal_cash',coalesce(terminal_cash->entity::text,old_data->'terminal_cash'),
     'equity_basis','terminal_frozen','metrics_basis','last_observed_before_replacement','terminal',coalesce(member->'terminal','null'::jsonb));
   INSERT INTO vn_projection.probes VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,entity::text,row_data);
  END LOOP;
  evaluation:=after_state#>'{engine,last_evaluation}';
  IF evaluation IS NOT NULL AND evaluation<>'null'::jsonb AND evaluation IS DISTINCT FROM before_state#>'{engine,last_evaluation}' THEN
   cohort:=evaluation->'cohort';
   row_data:=jsonb_build_object('cohort',cohort,'selection',evaluation->'selection','account_currency','USD',
    'scoring_policy','tagged_worker_evaluation_v1','terminal_accounts',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',entity_key,
      'terminal_cash',data->'terminal_cash','initial_cash',data->'initial_cash') ORDER BY entity_key),'[]'::jsonb)
     FROM vn_projection.probes WHERE run_id=NEW.run_id AND revision=NEW.revision AND cohort->'member_ids' ? entity_key));
   INSERT INTO vn_projection.evaluations VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,cohort->>'iteration_id',row_data);
  END IF;
 END IF;
 -- Interrupts retain the last checkpoint but explicitly change authority/status.
 SELECT count(*) INTO open_count FROM vn_durability.positions WHERE run_id=NEW.run_id AND NOT closed;
 run_equity:=NULL;
 IF mark IS NOT NULL AND NEW.kind='batch' THEN
  SELECT state.reserve+coalesce((SELECT sum(a.cash) FROM vn_durability.accounts a WHERE a.run_id=NEW.run_id),0)
   +coalesce((SELECT sum(quantity*mark) FROM vn_durability.positions WHERE run_id=NEW.run_id AND NOT closed),0) INTO run_equity;
 END IF;
 row_data:=jsonb_build_object('id',NEW.run_id,'status',state.status,'requires_reconciliation',state.requires_reconciliation,
  'durability_version',state.command_version,'mode',CASE WHEN state.command_version=5 THEN 'paper' ELSE 'synthetic_rehearsal' END,
  'strategy',state.config#>'{rehearsal,strategy}','asset',state.config#>'{rehearsal,asset}',
  'execution_policy',state.config->'execution','code_version',state.config#>'{rehearsal,code_version}',
  'initial_cash',state.initial_cash::text,'reserve',state.reserve::text,'reference_equity',run_equity::text,
  'equity_availability',CASE WHEN run_equity IS NULL THEN 'unavailable' ELSE 'reference_mark' END,
  'account_currency','USD','generation',state.engine_state#>'{engine,generation}',
  'total_probe_count',(SELECT count(*) FROM vn_durability.accounts WHERE run_id=NEW.run_id),
  'active_probe_count',(SELECT count(*) FROM vn_durability.accounts WHERE run_id=NEW.run_id AND NOT retired),
  'open_position_count',open_count,'retained_exposure',open_count>0,'created_at',state.created_at,
  'committed_at',NEW.committed_at,'source_at',source_stamp,'source_policy',state.config->'source_policy');
 INSERT INTO vn_projection.runs VALUES(NEW.user_id,NEW.run_id,NEW.revision,NEW.id,NEW.run_id::text,row_data);
 RETURN NEW;
END $$;
CREATE TRIGGER project_command AFTER INSERT ON vn_durability.commands FOR EACH ROW EXECUTE FUNCTION vn_projection.project_command();

-- Authenticated owner comes from the JWT, never a caller-supplied owner argument.
-- Pages expose bounded curated projections, not commands/checkpoints/optimizer graphs.
CREATE FUNCTION vn_read.page(run uuid, kind text, through_revision bigint DEFAULT NULL,
 after_revision bigint DEFAULT 0, after_key text DEFAULT '', max_rows integer DEFAULT 100,
 max_bytes integer DEFAULT 65536) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE owner_id uuid:=auth.uid(); snapshot bigint; relation text; row record; result jsonb;
 records jsonb:='[]'::jsonb; candidate jsonb; more boolean:=false; cursor jsonb:='null'::jsonb;
BEGIN
 IF owner_id IS NULL OR run IS NULL OR after_revision IS NULL OR after_revision<0 OR after_key IS NULL OR octet_length(after_key)>256 OR
  (after_revision=0 AND after_key<>'') OR max_rows IS NULL OR max_rows NOT BETWEEN 1 AND 100 OR
  max_bytes IS NULL OR max_bytes NOT BETWEEN 512 AND 65536 THEN RAISE EXCEPTION 'invalid_read_page' USING ERRCODE='22023'; END IF;
 IF kind NOT IN('runs','probes','trades','samples','evaluations') OR kind IS NULL THEN
  RAISE EXCEPTION 'invalid_read_kind' USING ERRCODE='22023'; END IF;
 SELECT revision INTO snapshot FROM vn_durability.runs WHERE id=run AND user_id=owner_id;
 IF snapshot IS NULL THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
 snapshot:=coalesce(through_revision,snapshot);
 IF snapshot<1 OR snapshot>(SELECT revision FROM vn_durability.runs WHERE id=run AND user_id=owner_id) OR after_revision>snapshot THEN
  RAISE EXCEPTION 'invalid_read_revision' USING ERRCODE='22023'; END IF;
 relation:=kind;
 result:=jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,'kind',kind,
  'through_revision',snapshot,'records',records,'has_more',false,'next_cursor',cursor);
 FOR row IN EXECUTE format('SELECT revision,command_id,entity_key,data FROM vn_projection.%I WHERE user_id=$1 AND run_id=$2 AND revision<=$3 AND (revision,entity_key)>($4,$5) ORDER BY revision,entity_key LIMIT $6',relation)
 USING owner_id,run,snapshot,after_revision,after_key,max_rows+1 LOOP
  IF jsonb_array_length(records)=max_rows THEN more:=true; EXIT; END IF;
  candidate:=jsonb_set(result,'{records}',records||jsonb_build_array(jsonb_build_object('revision',row.revision,'command_id',row.command_id,'key',row.entity_key,'data',row.data)));
  cursor:=jsonb_build_object('revision',row.revision,'key',row.entity_key);
  candidate:=jsonb_set(candidate,'{next_cursor}',cursor);
  IF octet_length(candidate::text)>max_bytes THEN
   IF records='[]'::jsonb THEN RAISE EXCEPTION 'read_record_exceeds_page' USING ERRCODE='22023'; END IF;
   more:=true; EXIT;
  END IF;
  records:=candidate->'records'; result:=candidate;
 END LOOP;
 RETURN jsonb_set(result,'{has_more}',to_jsonb(more));
END $$;

-- Sequence is allocated under the same run lock as commands. Delayed acceptance
-- cannot add an event below a previously returned replay cutoff/cursor.
CREATE FUNCTION vn_read.accept_event(owner_id uuid, run uuid, command_id uuid, event_index integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE item vn_durability.outbox_events%ROWTYPE; identity text; receipt jsonb; seq bigint;
BEGIN
 IF owner_id IS NULL OR run IS NULL OR command_id IS NULL OR event_index IS NULL OR event_index NOT BETWEEN 0 AND 1024 THEN
  RAISE EXCEPTION 'invalid_relay_event' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'relay_event_unavailable' USING ERRCODE='P0001'; END IF;
 SELECT * INTO item FROM vn_durability.outbox_events e WHERE e.user_id=owner_id AND e.run_id=run AND e.command_id=accept_event.command_id AND e.event_index=accept_event.event_index;
 IF NOT FOUND THEN RAISE EXCEPTION 'relay_event_unavailable' USING ERRCODE='P0001'; END IF;
 identity:=run::text||':'||command_id::text||':'||event_index::text;
 SELECT sequence INTO seq FROM vn_projection.relay_events WHERE run_id=run AND entity_key=identity;
 IF seq IS NULL THEN
  SELECT coalesce(max(sequence),0)+1 INTO seq FROM vn_projection.relay_events WHERE user_id=owner_id AND run_id=run;
  INSERT INTO vn_projection.relay_events VALUES(seq,owner_id,run,item.revision,command_id,identity,
   jsonb_build_object('event_id',identity,'event_index',event_index,'event',item.event));
 END IF;
 IF NOT EXISTS(SELECT 1 FROM vn_projection.relay_events WHERE run_id=run AND revision=item.revision AND entity_key=identity
   AND user_id=owner_id AND data=jsonb_build_object('event_id',identity,'event_index',event_index,'event',item.event)) THEN
  RAISE EXCEPTION 'relay_event_conflict' USING ERRCODE='P0001'; END IF;
 receipt:=jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,'command_id',command_id,'event_index',event_index,'event_id',identity,'revision',item.revision,'sequence',seq,'accepted',true);
 RETURN receipt;
END $$;

CREATE FUNCTION vn_read.events(run uuid, through_sequence bigint DEFAULT NULL,
 after_sequence bigint DEFAULT 0, max_rows integer DEFAULT 100, max_bytes integer DEFAULT 65536)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE owner_id uuid:=auth.uid(); snapshot bigint; latest bigint; row record; result jsonb; candidate jsonb;
 records jsonb:='[]'::jsonb; more boolean:=false;
BEGIN
 IF owner_id IS NULL OR run IS NULL OR after_sequence IS NULL OR after_sequence<0 OR
  max_rows IS NULL OR max_rows NOT BETWEEN 1 AND 100 OR max_bytes IS NULL OR max_bytes NOT BETWEEN 512 AND 65536 THEN
  RAISE EXCEPTION 'invalid_event_page' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM vn_durability.runs WHERE id=run AND user_id=owner_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
 SELECT coalesce(max(sequence),0) INTO latest FROM vn_projection.relay_events WHERE user_id=owner_id AND run_id=run;
 snapshot:=coalesce(through_sequence,latest);
 IF snapshot<0 OR snapshot>latest OR after_sequence>snapshot THEN RAISE EXCEPTION 'invalid_event_sequence' USING ERRCODE='22023'; END IF;
 result:=jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,'through_sequence',snapshot,
  'records',records,'has_more',false,'next_sequence',after_sequence);
 FOR row IN SELECT * FROM vn_projection.relay_events WHERE user_id=owner_id AND run_id=run
  AND sequence>after_sequence AND sequence<=snapshot ORDER BY sequence LIMIT max_rows+1 LOOP
  IF jsonb_array_length(records)=max_rows THEN more:=true; EXIT; END IF;
  candidate:=jsonb_set(result,'{records}',records||jsonb_build_array(jsonb_build_object('sequence',row.sequence,
   'revision',row.revision,'command_id',row.command_id,'data',row.data)));
  candidate:=jsonb_set(candidate,'{next_sequence}',to_jsonb(row.sequence));
  IF octet_length(candidate::text)>max_bytes THEN
   IF records='[]'::jsonb THEN RAISE EXCEPTION 'read_record_exceeds_page' USING ERRCODE='22023'; END IF;
   more:=true; EXIT;
  END IF;
  records:=candidate->'records'; result:=candidate;
 END LOOP;
 RETURN jsonb_set(result,'{has_more}',to_jsonb(more));
END $$;

CREATE FUNCTION vn_projection.require_relay_acceptance() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,vn_projection,pg_temp AS $$
BEGIN
 IF (NEW.acknowledged_revision,NEW.acknowledged_index)>(OLD.acknowledged_revision,OLD.acknowledged_index) AND
  NOT EXISTS(SELECT 1 FROM vn_projection.relay_events WHERE run_id=NEW.run_id AND user_id=NEW.user_id AND revision=NEW.acknowledged_revision
   AND (data->>'event_index')::integer=NEW.acknowledged_index) THEN
  RAISE EXCEPTION 'durable_relay_acceptance_required' USING ERRCODE='P0001';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER require_relay_acceptance BEFORE UPDATE ON vn_durability.outbox_progress FOR EACH ROW EXECUTE FUNCTION vn_projection.require_relay_acceptance();

CREATE FUNCTION vn_read.archive_run(run uuid, expected_revision bigint, request_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,vn_projection,pg_temp AS $$
DECLARE owner_id uuid:=auth.uid(); state vn_durability.runs%ROWTYPE; existing vn_projection.archives%ROWTYPE; receipt jsonb; positions integer;
BEGIN
 IF owner_id IS NULL OR run IS NULL OR expected_revision IS NULL OR expected_revision<1 OR request_id IS NULL THEN
  RAISE EXCEPTION 'invalid_archive_request' USING ERRCODE='22023'; END IF;
 SELECT * INTO state FROM vn_durability.runs WHERE id=run AND user_id=owner_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'run_unavailable' USING ERRCODE='P0001'; END IF;
 SELECT * INTO existing FROM vn_projection.archives WHERE user_id=owner_id AND archives.request_id=archive_run.request_id;
 IF FOUND THEN
  IF existing.run_id<>run OR existing.expected_revision<>expected_revision THEN RAISE EXCEPTION 'archive_request_conflict'; END IF;
  RETURN existing.receipt;
 END IF;
 -- The core marks orderly stops reconciliation-required too. Archive is
 -- presentation only: prove a complete known stopped checkpoint/journal and
 -- retain that warning; never clear reconciliation or infer liquidation.
 IF state.revision<>expected_revision OR state.status<>'stopped' OR state.command_version NOT IN(4,5) OR
  state.interrupted_at IS NOT NULL OR state.engine_state->>'status' IS DISTINCT FROM 'stopped' OR
  (state.engine_state->>'revision')::bigint IS DISTINCT FROM state.revision OR NOT EXISTS(
   SELECT 1 FROM vn_durability.commands c WHERE c.run_id=run AND c.user_id=owner_id AND
    c.revision=state.revision AND c.kind='batch') THEN
  RAISE EXCEPTION 'archive_unavailable' USING ERRCODE='P0001'; END IF;
 SELECT count(*) INTO positions FROM vn_durability.positions WHERE run_id=run AND NOT closed;
 receipt:=jsonb_build_object('version',1,'owner_id',owner_id,'run_id',run,'request_id',request_id,'revision',expected_revision,
  'archived',true,'retained_open_positions',positions,'retained_exposure',positions>0,
  'requires_reconciliation',state.requires_reconciliation,'classification','known_terminal_checkpoint');
 IF EXISTS(SELECT 1 FROM vn_projection.archives WHERE run_id=run) THEN
  RAISE EXCEPTION 'archive_request_conflict' USING ERRCODE='P0001'; END IF;
 INSERT INTO vn_projection.archives(user_id,run_id,expected_revision,request_id,receipt)
 VALUES(owner_id,run,expected_revision,request_id,receipt);
 RETURN receipt;
END $$;

-- Explicit schema/function grants only; curated reads replace core checkpoint reads.
REVOKE ALL ON SCHEMA vn_projection,vn_read FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON ALL TABLES IN SCHEMA vn_projection FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vn_projection,vn_read FROM PUBLIC,anon,authenticated,service_role;
REVOKE SELECT ON vn_durability.runs,vn_durability.accounts,vn_durability.positions,vn_durability.account_parents,
 vn_durability.commands,vn_durability.outbox_events,vn_durability.outbox_progress,vn_durability.distributions,
 vn_durability.distribution_sources,vn_durability.account_lineage,vn_durability.lineage_sources FROM authenticated;
GRANT USAGE ON SCHEMA vn_read TO authenticated,service_role;
GRANT EXECUTE ON FUNCTION vn_read.page(uuid,text,bigint,bigint,text,integer,integer),
 vn_read.archive_run(uuid,bigint,uuid),
 vn_read.events(uuid,bigint,bigint,integer,integer) TO authenticated;
GRANT EXECUTE ON FUNCTION vn_read.accept_event(uuid,uuid,uuid,integer) TO service_role;
COMMIT;
