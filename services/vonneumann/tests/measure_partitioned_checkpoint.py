"""Opt-in same-trace physical comparison; toy layout, never a migration."""
import json
from pathlib import Path
import platform
import sys
from uuid import UUID

from tests.postgres.harness import IsolatedPostgres
from tests.test_partitioned_checkpoint import partition_trace
from tests.test_provider_ga_components import provider_trace
from tests.test_provider_contract import OWNER, RUN
from tests.measure_provider_ga_research import literal
from tests.security_support import deny_network
from tests.test_provider_contract import WALL, MONO, EPOCH, seed_bundle, source_inputs, raw_capture
from vonneumann.research import provider_ga_model as ga
from vonneumann.research import provider_checkpoint as old_cp


def relation(db, table):
    name='experiment.'+table
    return json.loads(db.scalar(f"SELECT json_build_object('rows',(SELECT count(*) FROM {name}),"
        f"'heap_bytes',pg_relation_size('{name}'),'table_including_toast_bytes',pg_table_size('{name}'),"
        f"'indexes_bytes',pg_indexes_size('{name}'),'total_bytes',pg_total_relation_size('{name}'));"))


def planning(metrics):
    phases={phase:{version:sum(row[version] for row in samples)/len(samples)
                   for version in ('v1','v2')} | {'samples':len(samples)}
            for phase,samples in metrics['quote_only'].items()}
    per_tick={version:sum(row[version] for row in phases.values()) for version in ('v1','v2')}
    rates=[]
    for hz in (0.1,0.2,1):
        rates.append({'accepted_frames_per_second':hz,
            'commands_per_second':2*hz,
            'v1_logical_bytes_per_day':per_tick['v1']*hz*86400,
            'v2_logical_bytes_per_day':per_tick['v2']*hz*86400,
            'v2_minutes_to_128_mib_logical':128*1024**2/per_tick['v2']/hz/60})
    return {'quote_only_phase_means':phases,'wire_bytes_per_two_command_tick':per_tick,
            'conditional_rates':rates,
            'limits':'fixture sample means, not observed scheduling, steady workload, hosted throughput or physical cost; excludes candles/replacements/Stop/projections/raw archive/receipts/WAL/backup',
            'budget_status':'128 MiB is an illustrative logical journal planning budget, not a configured database limit or approved retention policy; never delete dependencies/identity evidence on a timer'}


def quote_only_driver(dense, windows, observer):
    """64 sequential fresh frames, no completed candle; synthetic two commands/frame."""
    ledger=ga.SimulationLedger(OWNER,RUN); previous=None; last=None
    def accept(candidate):
        nonlocal previous,last
        capture=old_cp.capture_owned_candidate(candidate)
        wire=old_cp.prepare_transport(candidate,capture,previous=previous,
            command_id=str(UUID(int=40_000_000+candidate.state.revision)))
        state=ledger.accept(candidate)
        observer(candidate,capture,wire)
        previous,last=capture,candidate
        return state
    with deny_network():
        state=accept(ga.bootstrap(ga.GAConfig('genetic_algorithm',OWNER,RUN,
            asset='SOL/USD',source_epoch=EPOCH),seed_bundle(last_close='80'),source_inputs(WALL),ledger=ledger))
        for serial in range(1,65):
            wall,mono=WALL+serial,MONO+serial
            frame=ga.source.make_frame(raw_capture(block=100+serial,source_second=wall-2,wall=wall-1,mono=mono-1),
                prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=serial*2),ledger=ledger))
            state=accept(ga.prepare_decision(state,frame,None,source_inputs(wall,mono=mono,serial=serial*2+1),ledger=ledger))
    return {'final_generation':state.to_dict()['engine']['generation'],
            'assessments':sum(len(h['assessments']) for h in ledger.history),
            'closed_positions':sum(len(h['closed_positions']) for h in ledger.history)},last,previous,ledger


def storage(quote_only=False):
    rows=[]; blocks={1:{},2:{}}
    def observe(candidate,old,old_wire,new,new_wire):
        rows.append((candidate.state.revision,candidate._wire.decode(),old_wire.decode(),new_wire.decode(),
                     old.to_dict(),new.to_dict()))
        for version,capture in ((1,old),(2,new)):
            for block in capture.components: blocks[version][block.identity]=block._wire.decode()
    metrics,*_=partition_trace(True,windows=0 if quote_only else 3,observer=observe,
        driver=quote_only_driver if quote_only else provider_trace)
    with IsolatedPostgres() as db:
        db.sql('''CREATE SCHEMA experiment;
        CREATE TABLE experiment.full_journal(owner_id uuid NOT NULL,run_id uuid NOT NULL,
          revision bigint NOT NULL,body jsonb NOT NULL,PRIMARY KEY(owner_id,run_id,revision));
        CREATE TABLE experiment.v1_journal(LIKE experiment.full_journal INCLUDING ALL);
        CREATE TABLE experiment.v2_journal(LIKE experiment.full_journal INCLUDING ALL);
        CREATE TABLE experiment.v1_components(digest text PRIMARY KEY,body jsonb NOT NULL);
        CREATE TABLE experiment.v2_components(LIKE experiment.v1_components INCLUDING ALL);
        CREATE TABLE experiment.v1_dependencies(owner_id uuid NOT NULL,run_id uuid NOT NULL,
          revision bigint NOT NULL,digest text NOT NULL REFERENCES experiment.v1_components(digest),
          PRIMARY KEY(owner_id,run_id,revision,digest));
        CREATE TABLE experiment.v2_dependencies(owner_id uuid NOT NULL,run_id uuid NOT NULL,
          revision bigint NOT NULL,digest text NOT NULL REFERENCES experiment.v2_components(digest),
          PRIMARY KEY(owner_id,run_id,revision,digest));''')
        sql=['BEGIN;']
        for version,components in blocks.items():
            for digest,body in components.items():
                sql.append(f'INSERT INTO experiment.v{version}_components VALUES ({literal(digest)},{literal(body)}::jsonb);')
        for revision,full,v1,v2,m1,m2 in rows:
            for table,wire in (('full_journal',full),('v1_journal',v1),('v2_journal',v2)):
                sql.append(f'INSERT INTO experiment.{table} VALUES ({literal(OWNER)},{literal(RUN)},{revision},{literal(wire)}::jsonb);')
            for version,manifest in ((1,m1),(2,m2)):
                for ref in manifest['components']:
                    sql.append(f'INSERT INTO experiment.v{version}_dependencies VALUES ({literal(OWNER)},{literal(RUN)},{revision},{literal(ref["sha256"])});')
        sql.append('COMMIT;'); db.sql('\n'.join(sql),timeout=60)
        tables=('full_journal','v1_journal','v2_journal','v1_components','v2_components',
                'v1_dependencies','v2_dependencies')
        relations={table:relation(db,table) for table in tables}
        # Force materialization with octet_length(body::text); simple SELECT body
        # can leave TOAST unread. These are warm local server diagnostics only.
        db.sql('''CREATE TABLE experiment.timings(kind text,elapsed_us bigint);
        DO $measure$ DECLARE t timestamptz;i integer;n bigint;v integer;BEGIN
          FOR i IN 1..100 LOOP
            FOR v IN 1..2 LOOP
              t:=clock_timestamp();
              EXECUTE format('SELECT octet_length(body::text) FROM experiment.v%s_journal ORDER BY revision DESC LIMIT 1',v) INTO n;
              INSERT INTO experiment.timings VALUES ('v'||v||'_journal_detoast',extract(epoch FROM clock_timestamp()-t)*1000000);
              t:=clock_timestamp();
              EXECUTE format('SELECT sum(octet_length(c.body::text)) FROM experiment.v%s_dependencies d JOIN experiment.v%s_components c USING(digest) WHERE d.revision=(SELECT max(revision) FROM experiment.v%s_journal)',v,v,v) INTO n;
              INSERT INTO experiment.timings VALUES ('v'||v||'_all_dependencies_detoast',extract(epoch FROM clock_timestamp()-t)*1000000);
            END LOOP;
          END LOOP;
        END $measure$;''')
        timings=json.loads(db.scalar("SELECT json_agg(x) FROM (SELECT kind,count(*) AS samples,percentile_cont(.5) WITHIN GROUP(ORDER BY elapsed_us) AS p50_us,percentile_cont(.95) WITHIN GROUP(ORDER BY elapsed_us) AS p95_us FROM experiment.timings GROUP BY kind ORDER BY kind)x;"))
        pinned=next(iter(blocks[2]))
        refusal=db.sql(f'DELETE FROM experiment.v2_components WHERE digest={literal(pinned)};',check=False)
        if refusal.returncode==0 or 'foreign key' not in refusal.stderr.lower():
            raise AssertionError('Referenced component deletion was not refused by actual PostgreSQL')
        if int(db.scalar('SELECT count(*) FROM experiment.v2_components;'))!=len(blocks[2]):
            raise AssertionError('Refused component deletion changed stored evidence')
        identity={'image_id':db.identity['image_id'],'postgres':db.scalar('SELECT version();'),
                  'network':'none','schema':'isolated toy tables; no production admission or limited-role proof'}
    return {'identity':identity,'workload':'64 fresh quote-only frames/129 commands' if quote_only else 'three dense windows/51 commands',
            'trace':metrics,'relations':relations,
            'layout_total_bytes':{'full':relations['full_journal']['total_bytes'],
                **{f'v{v}':sum(relations[f'v{v}_{t}']['total_bytes'] for t in ('journal','components','dependencies')) for v in (1,2)}},
            'referenced_component_delete_refused':True,'warm_server_detoast_diagnostics':timings,
            'timing_limits':'forces JSONB detoast/text materialization; excludes independent model validation, contention, TLS/transport, COMMIT/relay, WAL and hosted tail latency',
            'storage_limits':'indexes/TOAST/full checkpoint dependency pins included; no legacy duplicate journal/projections/source raw archive/receipt/archive/backup/WAL'}


if __name__=='__main__':
    if sys.argv[1:]!=['--measure']:
        raise SystemExit('Use --measure and DASHBOARD_ISOLATED_POSTGRES_TESTS=1')
    traces=[]
    for dense in (False,True):
        metrics,*_=partition_trace(dense,windows=32)
        traces.append(metrics)
        print(json.dumps({'completed_trace':dense,'candidates':metrics['candidates']}),flush=True)
    measured=storage()
    quote_measured=storage(quote_only=True)
    value={'date':'2026-10-09','python':platform.python_version(),
        'format':'ga-provider-checkpoint-research-v2',
        'traces':[{k:v for k,v in m.items() if k!='quote_only'} for m in traces],
        'conditional_journal_planning':[planning(m) for m in traces],
        'storage':measured,'quote_only_storage':quote_measured,
        'excluded':['runtime restoration','native admission','migration','activation','profitability','hosted performance']}
    for measured_trace in (measured,quote_measured):
        measured_trace['conditional_journal_planning']=planning(measured_trace['trace'])
        measured_trace['trace'].pop('quote_only')
    path=Path(__file__).resolve().parents[1]/'research/partitioned-checkpoint-capacity.json'
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'artifact':str(path),'layout_total_bytes':measured['layout_total_bytes']}))
