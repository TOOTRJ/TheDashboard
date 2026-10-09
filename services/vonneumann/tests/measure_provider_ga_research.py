"""Opt-in disposable PostgreSQL storage and fresh cost diagnostic measurements.

Toy storage layout is not a migration, admission contract or hosted benchmark.
The container has no network/ports/production credentials and is always removed.
"""
import json
import platform
from pathlib import Path
import sys

from tests.postgres.harness import IsolatedPostgres
from tests.test_provider_ga_components import provider_trace
from vonneumann.research import numeric_wire as numbers


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def measure_storage():
    rows, blocks = [], {}
    def observe(candidate, capture, wire):
        rows.append((candidate.state.revision, candidate._wire.decode(), wire.decode(), capture.to_dict()))
        for block in capture.components:
            blocks[block.identity] = block._wire.decode()
    trace = provider_trace(True, windows=3, observer=observe)[0]
    with IsolatedPostgres() as db:
        identity = {'image_id': db.identity['image_id'], 'postgres': db.scalar('SELECT version();'),
                    'network': 'none', 'schema': 'toy research tables, not production contract'}
        db.sql('''CREATE SCHEMA experiment;
          CREATE TABLE experiment.full_journal(owner_id uuid NOT NULL, run_id uuid NOT NULL,
            revision bigint NOT NULL, body jsonb NOT NULL, PRIMARY KEY(owner_id,run_id,revision));
          CREATE TABLE experiment.compact_journal(LIKE experiment.full_journal INCLUDING ALL);
          CREATE TABLE experiment.components(digest text PRIMARY KEY, body jsonb NOT NULL);
          CREATE TABLE experiment.dependencies(owner_id uuid NOT NULL, run_id uuid NOT NULL,
            revision bigint NOT NULL, digest text NOT NULL REFERENCES experiment.components(digest),
            PRIMARY KEY(owner_id,run_id,revision,digest));''')
        from tests.test_provider_contract import OWNER, RUN
        sql = ['BEGIN;']
        for digest, body in blocks.items():
            sql.append(f'INSERT INTO experiment.components VALUES ({literal(digest)},{literal(body)}::jsonb);')
        for revision, full, compact, manifest in rows:
            for table, body in (('full_journal', full), ('compact_journal', compact)):
                sql.append(f'INSERT INTO experiment.{table} VALUES ({literal(OWNER)}::uuid,{literal(RUN)}::uuid,{revision},{literal(body)}::jsonb);')
            for ref in manifest['components']:
                sql.append(f'INSERT INTO experiment.dependencies VALUES ({literal(OWNER)}::uuid,{literal(RUN)}::uuid,{revision},{literal(ref["sha256"])});')
        sql.append('COMMIT;')
        db.sql('\n'.join(sql), timeout=60)
        result = {}
        for table in ('full_journal', 'compact_journal', 'components', 'dependencies'):
            name = 'experiment.' + table
            measurement = json.loads(db.scalar(f"SELECT json_build_object('rows', (SELECT count(*) FROM {name}), 'heap_bytes',pg_relation_size('{name}'),'table_including_toast_bytes',pg_table_size('{name}'),'indexes_bytes',pg_indexes_size('{name}'),'total_bytes',pg_total_relation_size('{name}'));"))
            result[table] = measurement
        db.sql('''CREATE TABLE experiment.timings(kind text, elapsed_us bigint);
          DO $measure$ DECLARE t timestamptz; i integer; b jsonb; BEGIN
            FOR i IN 1..100 LOOP
              t:=clock_timestamp(); SELECT body INTO b FROM experiment.full_journal ORDER BY revision DESC LIMIT 1;
              INSERT INTO experiment.timings VALUES ('full_read', extract(epoch FROM clock_timestamp()-t)*1000000);
              t:=clock_timestamp(); SELECT body INTO b FROM experiment.compact_journal ORDER BY revision DESC LIMIT 1;
              INSERT INTO experiment.timings VALUES ('compact_read', extract(epoch FROM clock_timestamp()-t)*1000000);
              t:=clock_timestamp(); PERFORM c.body FROM experiment.dependencies d JOIN experiment.components c USING(digest)
                WHERE d.revision=(SELECT max(revision) FROM experiment.compact_journal);
              INSERT INTO experiment.timings VALUES ('component_lookup', extract(epoch FROM clock_timestamp()-t)*1000000);
            END LOOP;
          END $measure$;''')
        timings = json.loads(db.scalar("SELECT json_agg(x) FROM (SELECT kind, count(*) AS samples, percentile_cont(.5) WITHIN GROUP(ORDER BY elapsed_us) AS p50_us, percentile_cont(.95) WITHIN GROUP(ORDER BY elapsed_us) AS p95_us FROM experiment.timings GROUP BY kind) x;"))
    return {'identity': identity, 'trace': trace, 'relations': result,
        'compact_total_bytes': sum(result[t]['total_bytes'] for t in ('compact_journal','components','dependencies')),
        'warm_server_statement_diagnostics': timings,
        'timing_limits': 'local warm synthetic SQL only; excludes JSON detoast validation, TLS, locks, transport, independent admission, projections, WAL and hosted capacity',
        'storage_limits': 'full candidate journal versus tagged compact journal plus complete pins/component store; no legacy journal retention, extra projections, backups/WAL, receipts or source raw archive'}


def cost_diagnostics():
    from tests.test_provider_contract import OWNER, RUN, WALL, MONO, END, EPOCH, seed_bundle, source_inputs, raw_capture, raw_minutes
    from vonneumann.research import provider_ga_model as ga
    from vonneumann.core.decimal_execution import DecimalExecutionConfig
    from tests.security_support import deny_network
    results = []
    for scenario, cost in [(s, c) for s in ('rising', 'rising_with_temporary_dips')
                           for c in ('0','2','10','50')]:
        with deny_network():
            ledger = ga.SimulationLedger(OWNER, RUN)
            state = ledger.accept(ga.bootstrap(ga.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=EPOCH,
                execution=DecimalExecutionConfig(fee_bps=cost)),seed_bundle(last_close='80'),source_inputs(WALL),ledger=ledger))
            offsets = [1] + [o for bar in range(1,5) for o in (bar*900,bar*900+1)]
            for serial, offset in enumerate(offsets,1):
                wall, mono = WALL+offset, MONO+offset
                # Illustrative rising quote, independent of alternating signal candles.
                price = str(100 + offset // 900)
                if scenario == 'rising_with_temporary_dips' and offset in (1800, 3600):
                    price = '100' if offset == 1800 else '102'
                frame = ga.source.make_frame(raw_capture(price=price,block=100+serial,source_second=wall-2,wall=wall-1,mono=mono-1),
                    prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
                state = ledger.accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=serial*2),ledger=ledger))
                history = None if offset%900 else ga.source.build_history(raw_minutes(end=END+offset,count=15,
                    close='120' if offset//900%2 else '80',wall=wall-1,mono=mono-1),prior_bars=state.to_dict()['source']['bars'],
                    seed=False,wall_us=wall*1000000,monotonic_us=int(mono*1000000))
                state = ledger.accept(ga.prepare_decision(state,frame,history,source_inputs(wall,mono=mono,generation=1,serial=serial*2+1),ledger=ledger))
            assessments = [a for h in ledger.history for a in h['assessments']]
            members = []
            for a in assessments:
                roi, dd = float.fromhex(a['roi_float64']), a['metrics']['max_drawdown']
                drawdown = int(dd['numerator']) / int(dd['denominator'])
                members.append({'probe_id':a['probe_id'],'closed_trades':a['metrics']['closed_trade_count'],
                    'roi':roi,'drawdown':drawdown,'actual_weight_2_fitness':float.fromhex(a['fitness_float64']),
                    'counterfactual_weight_scores':{str(w):roi-w*drawdown for w in (0,.5,1,2,4)},
                    'cash_benchmark_crossover_weight':None if drawdown==0 else roi/drawdown})
            results.append({'quote_scenario':scenario,'fee_bps_per_side':cost,'members':members})
    return {'scope':'eight fresh single-window replays across two synthetic quote paths and four fee scenarios; same seed, candle and receipt schedule within each comparison',
        'weight_scope':'arithmetic diagnostics over freshly finalized metrics, not a re-run of selection under a changed objective or a conversion of old scores',
        'cost_limits':'fee scenarios are illustrative; no calibration, network fees/tips, amount-dependent route, latency or real liquidity',
        'runs':results}


def workload_planning():
    """Conditional arithmetic, not observed/provider/hosted throughput."""
    sizes = {'protective': [], 'decision': []}
    def observe(candidate, capture, wire):
        value = numbers.decode(wire)
        phase = value['evidence']['kind']
        if phase in sizes and not value['components'] and value['evidence']['inputs']['provider']['history'] is None:
            sizes[phase].append(len(wire))
    provider_trace(False, windows=1, observer=observe)
    per_phase = {phase: {'samples':len(rows),'mean_wire_bytes':sum(rows)/len(rows),
                        'minimum_wire_bytes':min(rows),'maximum_wire_bytes':max(rows)}
                 for phase, rows in sizes.items()}
    per_tick = sum(row['mean_wire_bytes'] for row in per_phase.values())
    return {'quote_only_phase_sizes':per_phase,
        'conditional_one_accepted_tick_per_second':{'wire_bytes_per_tick':per_tick,
            'logical_journal_bytes_per_day':per_tick*86400,
            'logical_journal_bytes_per_30_days':per_tick*86400*30},
        'conditions':'two separate protective/decision commands for each accepted fresh frame, continuous 1 Hz; excludes candle/replacement/Stop/projection/raw archive/WAL/receipts and physical compression; no claim that current worker can or does sustain this rate',
        'decision':'bounded active state still needs journal retention/rate/storage acceptance; investigate typed stable source-bar/EMA components after exact continuation proof'}


if __name__ == '__main__':
    if sys.argv[1:] != ['--measure']:
        raise SystemExit('Use --measure and DASHBOARD_ISOLATED_POSTGRES_TESTS=1')
    value = {'date':'2026-10-08','python':platform.python_version(),
             'storage':measure_storage(),'fitness_cost_diagnostics':cost_diagnostics(),
             'workload_planning':workload_planning()}
    path = Path(__file__).resolve().parents[1] / 'research/provider-ga-deep-research.json'
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'artifact':str(path),'relations':value['storage']['relations'],
                      'compact_total_bytes':value['storage']['compact_total_bytes']}))
