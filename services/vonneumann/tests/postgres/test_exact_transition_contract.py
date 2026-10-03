"""Raw-role validation of complete bounded exact-engine transition envelopes.

Only the disposable PostgreSQL fixture is used. Tamper cases bypass the Python
protocol validator so the server must independently reject the changed claim.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from uuid import UUID
from unittest.mock import patch

from tests.postgres.harness import PostgresContractTestCase
from tests.postgres.test_command_adapter import identity, literal
from tests.postgres.test_decimal_lineage_contract import document
from vonneumann.core.decision_inputs import DecisionInputs
from vonneumann.core.exact_rehearsal import (
    ExactRehearsalConfig, ExactObservation, bootstrap, prepare_protective, prepare_decision,
)
from vonneumann.core.decimal_execution import DecimalExecutionConfig
from tests import test_exact_rehearsal as engine_fixtures


STRATEGIES = ('genetic_algorithm', 'differential_evolution', 'particle_swarm', 'cma_es')


def tagged(value, kind):
    if type(value) is dict:
        if value.get('type') == kind:
            yield value
        for child in value.values():
            yield from tagged(child, kind)
    elif type(value) is list:
        for child in value:
            yield from tagged(child, kind)


class ExactTransitionContractTests(PostgresContractTestCase):
    def setUp(self):
        self.owner, self.run, self.worker = identity(), identity(), identity()
        self.db.sql(f"INSERT INTO auth.users(id) VALUES ({literal(self.owner)});")
        self.allocations = 1000
        self.revision = 1
        self.state = None

    def inputs(self, stamp, generation=0):
        identities = tuple(str(UUID(int=index)) for index in range(self.allocations, self.allocations + 32))
        self.allocations += 32
        return DecisionInputs(datetime.fromtimestamp(stamp, timezone.utc),
            datetime(2026, 10, 2, tzinfo=timezone.utc), float(stamp), identities,
            tuple((generation, f'Fixture-{generation}-{index}') for index in range(8)))

    def config(self, strategy='genetic_algorithm'):
        return ExactRehearsalConfig(strategy, self.owner, self.run,
            execution=DecimalExecutionConfig('30', '10', '10'))

    def create_sql(self, config, initial_cash=None):
        return 'SELECT vn_durability.create_run(' + ','.join((literal(self.owner), literal(self.run),
            literal(self.worker), literal(identity()), document(config.run_configuration()),
            literal(config.initial_cash if initial_cash is None else initial_cash), '120')) + ');'

    def create(self, strategy='genetic_algorithm'):
        config = self.config(strategy)
        self.db.sql(self.create_sql(config), role='service_role')
        return config

    def payload(self, candidate):
        return {'version': 3, 'operations': candidate.operations, 'transition': candidate.transition}

    def sql(self, payload, revision=None, command_id=None):
        return 'SELECT vn_durability.commit_command(' + ','.join((literal(self.owner), literal(self.run),
            literal(self.worker), '1', str(self.revision if revision is None else revision),
            literal(command_id or identity()), document(payload))) + ');'

    def commit(self, candidate):
        result = self.db.sql(self.sql(self.payload(candidate)), role='service_role')
        self.revision += 1
        self.state = candidate.state
        return result

    def snapshot(self):
        parts = []
        for table in ('runs', 'accounts', 'positions', 'commands', 'distributions',
                      'distribution_sources', 'account_lineage', 'lineage_sources'):
            key = 'id' if table == 'runs' else 'run_id'
            # Hash each complete row before aggregation. Materializing hundreds
            # of full before/after journals in one JSONB aggregate needlessly
            # exceeds the disposable server's deliberately small memory bound.
            parts.extend((literal(table), '(SELECT coalesce(jsonb_agg(digest ORDER BY digest),'
                "'[]'::jsonb) FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS digest "
                f"FROM vn_durability.{table} t WHERE {key}={literal(self.run)}::uuid) rows)"))
        return self.db.scalar('SELECT jsonb_build_object(' + ','.join(parts) + ');')

    def reject(self, payload, expected=None):
        before = self.snapshot()
        result = self.db.sql(self.sql(payload), role='service_role', check=False)
        self.assertNotEqual(result.returncode, 0)
        if expected:
            self.assertIn(expected, result.stderr)
        self.assertEqual(self.snapshot(), before)

    def open_prefix(self):
        with patch.object(engine_fixtures, 'OWNER', self.owner), patch.object(engine_fixtures, 'RUN', self.run):
            config, _, candidates, _ = engine_fixtures.roundtrip_windows('genetic_algorithm', collect_all=True)
        index = next(index for index, candidate in enumerate(candidates)
                     if any(op['kind'] == 'open' for op in candidate.operations))
        prefix = candidates[:index + 1]
        statements = [self.create_sql(config)]
        for candidate in prefix:
            before = candidate.transition['before']
            statements.append(self.sql(self.payload(candidate), revision=1 if before is None else before['revision']))
        self.db.sql('\n'.join(statements), role='service_role', timeout=60)
        self.state = prefix[-1].state
        self.revision = self.state.revision
        self.assertEqual(len(self.state.to_dict()['positions']), 8)
        return prefix

    def test_all_four_real_optimizer_bootstraps_bind_complete_state_and_events(self):
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                self.run, self.worker, self.revision = identity(), identity(), 1
                config = self.create(strategy)
                candidate = bootstrap(config, self.inputs(0))
                self.commit(candidate)
                stored = json.loads(self.db.scalar(f'SELECT engine_state FROM vn_durability.runs WHERE id={literal(self.run)};'))
                self.assertEqual(stored, candidate.state.to_dict())
                self.assertEqual(stored['reserve'], '200')
                self.assertEqual(len(stored['accounts']), 8)
                self.assertEqual(len(candidate.transition['events']), 9)

    def test_creation_rejects_unbound_cash_and_unknown_immutable_config(self):
        config = self.config()
        result = self.db.sql(self.create_sql(config, '999'), role='service_role', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('rehearsal_initial_cash_mismatch', result.stderr)
        self.assertEqual(self.db.scalar(f'SELECT count(*) FROM vn_durability.runs WHERE id={literal(self.run)};'), '0')

    def test_bootstrap_rejects_wrong_projection_identity_events_and_mutable_policy(self):
        config = self.create()
        candidate = bootstrap(config, self.inputs(0))
        original = self.payload(candidate)
        mutations = (
            lambda p: p['transition']['after']['accounts'][0].update(cash='101'),
            lambda p: p['transition']['after']['accounts'][0].update(cash=100),
            lambda p: p['transition']['after']['accounts'][0].update(initial_cash=100),
            lambda p: p['transition']['after']['accounts'].pop(),
            lambda p: p['transition']['after'].update(reserve='201'),
            lambda p: p['transition']['after'].update(reserve=200),
            lambda p: p['transition']['after'].update(owner_id=identity()),
            lambda p: p['transition']['after'].update(revision=99),
            lambda p: p['transition']['events'].pop(),
            lambda p: p['transition']['events'][0].update(at=1),
            lambda p: p['transition']['events'][0].update(account_id=identity()),
            lambda p: p['transition']['after']['engine']['config'].update(source='different-source'),
            lambda p: p['transition']['after']['engine']['members'][0]['genome'].update(stop_loss_pct=0.04.hex()),
            lambda p: p['transition']['after']['engine']['members'][0]['genome'].update(ema_fast=2.0.hex()),
            lambda p: p['transition']['after']['engine']['members'][0].update(num_trades=1),
            lambda p: p['transition']['after']['engine']['members'][0].update(name='Invented'),
            lambda p: p['transition']['after']['engine']['members'][0]['genome'].update(parent_ids=[identity()]),
            lambda p: p['transition']['after']['engine']['optimizer']['strategy']['fields'].update(_rng=None),
            lambda p: p['transition']['after']['engine']['optimizer']['strategy']['fields'].update(_rng={'ref': 999999}),
            lambda p: p['transition']['evidence']['inputs'].update(monotonic_at='inf'),
            lambda p: p['transition']['after']['engine']['used_ids'].append(p['transition']['evidence']['inputs']['ids'][8]),
        )
        for mutate in mutations:
            changed = deepcopy(original)
            mutate(changed)
            with self.subTest(mutation=mutations.index(mutate)):
                self.reject(changed)
        self.commit(candidate)

    def test_empty_protective_and_decision_commands_advance_bound_source_once(self):
        self.commit(bootstrap(self.create(), self.inputs(0)))
        observation = ExactObservation(900, '100')
        protective = prepare_protective(self.state, observation, self.inputs(900))
        self.assertEqual(protective.operations, [])
        self.commit(protective)
        decision = prepare_decision(self.state, ExactObservation(900, '100', 900, '100'), self.inputs(900))
        self.assertEqual(decision.operations, [])
        original = self.payload(decision)
        changed = deepcopy(original)
        changed['transition']['before']['reserve'] = '201'
        self.reject(changed, 'transition_before_mismatch')
        changed = deepcopy(original)
        changed['transition']['evidence']['observation']['price'] = '101'
        self.reject(changed, 'transition_source_mismatch')
        self.commit(decision)
        changed = deepcopy(original)
        changed['transition']['before'] = self.state.to_dict()
        changed['transition']['after']['revision'] = self.revision + 1
        self.reject(changed, 'invalid_decision_transition')

    def test_three_complete_traded_replacements_from_each_real_solver_roundtrip_every_state(self):
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                self.run, self.worker, self.revision = identity(), identity(), 1
                # Patch fixture identities only; production clocks, strategies,
                # economics, and transition preparation remain the actual code.
                with patch.object(engine_fixtures, 'OWNER', self.owner), patch.object(engine_fixtures, 'RUN', self.run):
                    config, final, candidates, maximum = engine_fixtures.roundtrip_windows(strategy, collect_all=True)
                statements = [self.create_sql(config)]
                final_command_id = None
                for candidate in candidates:
                    before = candidate.transition['before']
                    revision = 1 if before is None else before['revision']
                    final_command_id = identity()
                    statements.append(self.sql(self.payload(candidate), revision=revision, command_id=final_command_id))
                if strategy == 'cma_es':
                    self.db.sql('\n'.join(statements[:-1]), role='service_role', timeout=60)
                    self.revision = final.transition['before']['revision']
                    # Mutate the actual third-generation CMA candidate through
                    # raw SQL. Every failed codec check follows economic work
                    # in the RPC and must roll the whole replacement back.
                    for case in ('null_rng_dtype', 'nan_array', 'infinite_array',
                                 'unwritten_history', 'integer_overflow', 'boolean_cache_flag',
                                 'empty_completed_cohort', 'swapped_evaluation_members',
                                 'missing_evaluation_result', 'null_evaluation_fitness',
                                 'wrong_evaluation_id', 'short_evaluation_window',
                                 'incorrect_evaluation_trade_count', 'empty_selection',
                                 'negative_current_ema'):
                        with self.subTest(codec_mutation=case):
                            changed = self.payload(final)
                            engine = changed['transition']['after']['engine']
                            evidence = engine['optimizer']
                            cohort = engine['last_evaluation']['cohort']
                            if case == 'null_rng_dtype':
                                next(tagged(evidence, 'numpy.RandomState'))['key_dtype'] = None
                            elif case in ('nan_array', 'infinite_array'):
                                array = next(item for item in tagged(evidence, 'ndarray')
                                             if item['dtype'].endswith('f8') and item['hex'])
                                bits = ('010000000000f07f' if case == 'nan_array' else '000000000000f07f')
                                if array['dtype'].startswith('>'):
                                    bits = bytes.fromhex(bits)[::-1].hex()
                                array['hex'] = bits + array['hex'][16:]
                            elif case == 'unwritten_history':
                                history = next(tagged(evidence, 'cmaes-fitness-history-v1'))
                                slot = history['written_pairs'].index(False)
                                history['slots_hex'][slot] = ['0x0.0p+0', '0x0.0p+0']
                            elif case == 'integer_overflow':
                                next(tagged(evidence, 'integer'))['decimal'] = str(2**256)
                            elif case == 'boolean_cache_flag':
                                next(tagged(evidence, 'numpy.RandomState'))['has_gaussian'] = True
                            elif case == 'empty_completed_cohort':
                                engine['last_evaluation']['cohort'] = {}
                            elif case == 'swapped_evaluation_members':
                                cohort['member_ids'][0], cohort['member_ids'][1] = (
                                    cohort['member_ids'][1], cohort['member_ids'][0])
                            elif case == 'missing_evaluation_result':
                                cohort['evaluations'].pop()
                            elif case == 'null_evaluation_fitness':
                                cohort['evaluations'][0]['fitness'] = None
                            elif case == 'wrong_evaluation_id':
                                cohort['evaluations'][0]['evaluation_id'] = cohort['evaluations'][1]['evaluation_id']
                            elif case == 'short_evaluation_window':
                                cohort['horizon_seconds'] = {'float64': (1800.0).hex()}
                            elif case == 'incorrect_evaluation_trade_count':
                                cohort['evaluations'][0]['num_trades'] += 1
                            elif case == 'empty_selection':
                                engine['last_evaluation']['selection'] = {}
                            else:
                                # Both maps contain the same period. Combining
                                # maps before validation would hide this value.
                                period = next(iter(engine['ema']['previous']))
                                engine['ema']['values'][period] = (-1.0).hex()
                            self.reject(changed)
                    self.db.sql(statements[-1], role='service_role', timeout=60)
                else:
                    self.db.sql('\n'.join(statements), role='service_role', timeout=60)
                stored = json.loads(self.db.scalar(f'SELECT engine_state FROM vn_durability.runs WHERE id={literal(self.run)};'))
                self.assertEqual(stored, final.state.to_dict())
                self.assertEqual(stored['engine']['generation'], 3)
                self.assertEqual(len(stored['accounts']), 32)
                self.assertEqual(sum(not row['retired'] for row in stored['accounts']), 8)
                self.assertTrue(all(row['closed'] for row in stored['positions']))
                self.assertGreaterEqual(len(stored['positions']), 8)
                self.assertLessEqual(maximum, 262144)
                self.assertEqual(int(self.db.scalar(f'SELECT count(*) FROM vn_durability.commands WHERE run_id={literal(self.run)};')),
                                 len(candidates) + 1)
                reasons = {action['reason'] for candidate in candidates
                           for action in candidate.transition['evidence']['actions']}
                self.assertTrue({'entry_signal', 'exit_signal', 'retire', 'birth'}.issubset(reasons))
                self.assertEqual(sum(any(event['kind'] == 'evaluation' for event in candidate.transition['events'])
                                     for candidate in candidates), 3)
                before_replay = self.snapshot()
                self.db.sql(self.sql(self.payload(final), revision=final.transition['before']['revision'],
                                     command_id=final_command_id), role='service_role')
                self.assertEqual(self.snapshot(), before_replay)
                changed = self.payload(final)
                changed['transition']['events'][0]['at'] += 1
                conflict = self.db.sql(self.sql(changed, revision=final.transition['before']['revision'],
                    command_id=final_command_id), role='service_role', check=False)
                self.assertNotEqual(conflict.returncode, 0)
                self.assertIn('command_conflict', conflict.stderr)
                self.assertEqual(self.snapshot(), before_replay)

    def test_same_command_replays_original_complete_envelope_and_changed_event_conflicts(self):
        candidate = bootstrap(self.create(), self.inputs(0))
        payload = self.payload(candidate)
        command_id = identity()
        first = self.db.scalar(self.sql(payload, command_id=command_id), role='service_role')
        before = self.snapshot()
        second = self.db.scalar(self.sql(payload, command_id=command_id), role='service_role')
        self.assertEqual(first, second)
        self.assertEqual(self.snapshot(), before)
        changed = deepcopy(payload)
        changed['transition']['events'][0]['at'] = 1
        result = self.db.sql(self.sql(changed, command_id=command_id), role='service_role', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('command_conflict', result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.db.sql(f"UPDATE vn_durability.runs SET lease_until=clock_timestamp()-interval '1 second' WHERE id={literal(self.run)};")
        resolved = json.loads(self.db.scalar('SELECT vn_durability.get_command(' +
            ','.join((literal(self.owner), literal(self.run), literal(command_id))) + ');', role='service_role'))
        self.assertEqual(resolved['request']['payload'], payload)
        self.assertEqual(resolved['response'], json.loads(first))
        self.assertEqual(len(resolved['request_hash']), 64)

    def test_protective_equality_and_one_unit_neighbors_match_actual_sql_economics(self):
        self.open_prefix()
        stamp = self.state.to_dict()['engine']['last_quote']['timestamp'] + 1
        before = self.snapshot()
        for price, expected in (('97', 'stop_loss'), ('96.999999999999999999', 'stop_loss'),
                                ('97.000000000000000001', None), ('107', 'take_profit'),
                                ('106.999999999999999999', None), ('107.000000000000000001', 'take_profit')):
            with self.subTest(price=price):
                candidate = prepare_protective(self.state, ExactObservation(stamp, price), self.inputs(stamp))
                self.assertEqual(len(candidate.operations), 0 if expected is None else 8)
                self.assertTrue(all(action['reason'] == expected for action in candidate.transition['evidence']['actions']))
                command_id = identity()
                readback = 'SELECT vn_durability.get_command(' + ','.join((literal(self.owner), literal(self.run),
                    literal(command_id))) + ")->'request'->'payload'->'transition'->'after';"
                result = self.db.sql('BEGIN;\n' + self.sql(self.payload(candidate), command_id=command_id) +
                                     '\n' + readback + '\nROLLBACK;', role='service_role')
                rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
                self.assertEqual(rows[-1], candidate.state.to_dict())
                self.assertEqual(self.snapshot(), before)

    def test_raw_protective_tampering_and_late_projection_failure_roll_back_all_closes(self):
        self.open_prefix()
        stamp = self.state.to_dict()['engine']['last_quote']['timestamp'] + 1
        candidate = prepare_protective(self.state, ExactObservation(stamp, '97'), self.inputs(stamp))
        original = self.payload(candidate)
        mutations = (
            lambda p: p['transition']['evidence']['actions'][-1].update(reason='take_profit'),
            lambda p: p['transition']['evidence']['actions'][-1].update(account_id=identity()),
            lambda p: p['transition']['evidence']['actions'][-1].update(position_id=identity()),
            lambda p: p['transition']['evidence']['actions'][-1].update(reference_price='96'),
            lambda p: p['transition']['evidence']['observation'].update(price='96'),
            lambda p: p['transition']['after']['accounts'][-1].update(cash='100'),
            lambda p: p['transition']['after']['positions'][-1].update(closed=False),
            lambda p: p['transition']['after']['engine']['members'][0].update(peak_equity='101'),
            lambda p: p['transition']['after']['engine']['members'][0].update(cursor=900),
            lambda p: p['transition']['after']['engine']['members'][0].update(name='Changed'),
            lambda p: p['transition']['after']['engine']['members'].reverse(),
            lambda p: p['transition']['events'].pop(),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                changed = deepcopy(original)
                mutate(changed)
                self.reject(changed)
        missing = deepcopy(original)
        missing['operations'].pop()
        missing['transition']['evidence']['actions'].pop()
        missing['transition']['events'].pop()
        self.reject(missing, 'missing_protective_close')
        self.commit(candidate)
        self.assertTrue(all(row['closed'] for row in self.state.to_dict()['positions']))

    def test_interruption_preserves_last_committed_engine_checkpoint_without_granting_resume(self):
        candidate = bootstrap(self.create(), self.inputs(0))
        self.commit(candidate)
        checkpoint = candidate.state.to_dict()
        self.db.sql(f"UPDATE vn_durability.runs SET lease_until=clock_timestamp()-interval '1 second' WHERE id={literal(self.run)};")
        response = json.loads(self.db.scalar('SELECT vn_durability.interrupt_expired(' +
            ','.join((literal(self.owner), literal(self.run), str(self.revision), literal(identity()))) + ');', role='service_role'))
        self.assertEqual(response['status'], 'failed')
        self.assertEqual(response['fence'], 2)
        self.assertTrue(response['requires_reconciliation'])
        stored = json.loads(self.db.scalar(f'SELECT engine_state FROM vn_durability.runs WHERE id={literal(self.run)};'))
        self.assertEqual(stored, checkpoint)
        self.assertEqual(stored['revision'], self.revision)
        self.assertEqual(response['revision'], self.revision + 1)
