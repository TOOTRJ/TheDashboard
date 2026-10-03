"""Real bounded v4 lifecycle traces against owned offline PostgreSQL."""
from __future__ import annotations
import json
from copy import deepcopy
from tests.lifecycle_fixtures import lifecycle_trace
from tests.postgres.harness import PostgresContractTestCase
from tests.postgres.test_command_adapter import identity, literal
from tests.postgres.test_decimal_lineage_contract import document

STRATEGIES = ('genetic_algorithm', 'differential_evolution', 'particle_swarm', 'cma_es')

class LifecycleContractTests(PostgresContractTestCase):
    def setUp(self):
        self.owner, self.run, self.worker = identity(), identity(), identity()
        self.db.sql(f'INSERT INTO auth.users(id) VALUES ({literal(self.owner)});')

    def create_sql(self, config):
        return 'SELECT vn_durability.create_run(' + ','.join((literal(self.owner), literal(self.run),
            literal(self.worker), literal(identity()), document(config.run_configuration()),
            literal(config.initial_cash), '120')) + ');'

    def payload(self, candidate):
        return {'version': 4, 'operations': candidate.operations, 'transition': candidate.transition}

    def sql(self, payload, command_id=None):
        before = payload['transition']['before']
        revision = 1 if before is None else before['revision']
        return 'SELECT vn_durability.commit_command(' + ','.join((literal(self.owner), literal(self.run),
            literal(self.worker), '1', str(revision), literal(command_id or identity()), document(payload))) + ');'

    def apply_trace(self, kind, strategy='genetic_algorithm'):
        self.run, self.worker = identity(), identity()
        config, candidates = lifecycle_trace(kind, strategy=strategy, owner_id=self.owner, run_id=self.run)
        self.db.sql(self.create_sql(config), role='service_role')
        # Preserve all no-op checkpoints while bounding client/server memory.
        for start in range(0, len(candidates), 20):
            batch = candidates[start:start+20]
            self.db.sql('\n'.join(self.sql(self.payload(c)) for c in batch), role='service_role', timeout=60)
            if batch[-1].state.to_dict()['status'] != 'stopped':
                self.db.sql('SELECT vn_durability.heartbeat(' + ','.join((literal(self.owner), literal(self.run),
                    literal(self.worker), '1', '120')) + ');', role='service_role')
        final = candidates[-1].state.to_dict()
        stored = json.loads(self.db.scalar(f'SELECT engine_state FROM vn_durability.runs WHERE id={literal(self.run)};'))
        self.assertEqual(stored, final)
        self.assertEqual(int(self.db.scalar(f'SELECT count(*) FROM vn_durability.commands WHERE run_id={literal(self.run)};')), len(candidates)+1)
        expected_events = sum(len(c.transition['events']) for c in candidates)
        self.assertEqual(int(self.db.scalar(f'SELECT count(*) FROM vn_durability.outbox_events WHERE run_id={literal(self.run)};')), expected_events)
        return config, candidates

    def test_all_four_solvers_complete_window_and_frozen_terminal_replacements(self):
        for strategy in STRATEGIES:
            for kind in ('replacement', 'terminal'):
                with self.subTest(strategy=strategy, kind=kind):
                    _, candidates = self.apply_trace(kind, strategy)
                    engine = candidates[-1].state.to_dict()['engine']
                    self.assertEqual(engine['generation'], 1)
                    self.assertEqual(engine['last_evaluation']['cohort']['completed_count'], 8)
                    self.assertEqual(engine['last_evaluation']['cohort']['phase'], 'completed')
                    if kind == 'terminal':
                        self.assertTrue(all(r['reason'] == 'drawdown' for r in engine['last_evaluation']['cohort']['evaluations']))

    def test_all_four_solvers_recover_and_restart_without_scoring_aborted_cohort(self):
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                _, candidates = self.apply_trace('recover', strategy)
                final = candidates[-1].state.to_dict()
                self.assertEqual(final['status'], 'running')
                self.assertEqual(final['engine']['lifecycle']['search_epoch'], 1)
                self.assertEqual(final['engine']['lifecycle']['risk']['recovery_count'], 1)
                self.assertIsNone(final['engine']['last_evaluation']['selection'])
                self.assertEqual(final['engine']['cohort']['phase'], 'warming')
                self.assertEqual(self.db.scalar(f"SELECT count(*) FROM vn_durability.account_lineage WHERE run_id={literal(self.run)} AND operation='restart_clone';"), '8')

    def test_pause_resume_stop_and_stale_history_keep_their_exact_boundaries(self):
        for kind in ('pause_resume', 'pause_stop', 'stale_restart'):
            with self.subTest(kind=kind):
                _, candidates = self.apply_trace(kind)
                final = candidates[-1].state.to_dict()
                if kind == 'pause_stop':
                    self.assertEqual(final['status'], 'stopped')
                    self.assertEqual(sum(not p['closed'] for p in final['positions']), 8)
                    self.assertIsNone(final['engine']['last_evaluation']['selection'])
                else:
                    self.assertEqual(final['engine']['lifecycle']['search_epoch'], 1)
                    self.assertEqual(final['engine']['cohort']['phase'], 'warming')
                if kind == 'stale_restart':
                    for c in candidates:
                        state = c.state.to_dict()
                        quote = state['engine']['last_quote']
                        if quote and 58502 <= quote['timestamp'] < 58505:
                            self.assertEqual(state['engine']['generation'], 0)
                            self.assertEqual(len(state['accounts']), 8)

    def test_cost_crossing_blocks_further_entry_or_selection_at_first_fill(self):
        for kind in ('entry_cost', 'deadline_cost'):
            with self.subTest(kind=kind):
                _, candidates = self.apply_trace(kind)
                final = candidates[-1].state.to_dict()
                self.assertEqual(final['status'], 'risk_halted')
                self.assertEqual(final['engine']['generation'], 0)
                self.assertEqual(final['engine']['cohort']['phase'], 'aborted')
                self.assertIsNone(final['engine']['last_evaluation']['selection'])
                if kind == 'entry_cost':
                    self.assertEqual(len(final['positions']), 1)
                else:
                    self.assertEqual(len(final['positions']), 8)
                    self.assertTrue(all(p['closed'] for p in final['positions']))

    def test_original_id_replay_and_readback_return_one_checkpoint_and_event_set(self):
        config, candidates = lifecycle_trace('pause_stop', owner_id=self.owner, run_id=self.run)
        self.db.sql(self.create_sql(config), role='service_role')
        payload, command_id = self.payload(candidates[0]), identity()
        first = self.db.scalar(self.sql(payload, command_id), role='service_role')
        self.assertEqual(self.db.scalar(self.sql(payload, command_id), role='service_role'), first)
        read = json.loads(self.db.scalar('SELECT vn_durability.get_command(' + ','.join((literal(self.owner), literal(self.run), literal(command_id))) + ');', role='service_role'))
        self.assertEqual(read['request']['payload'], payload)
        self.assertEqual(read['response'], json.loads(first))
        self.assertEqual(self.db.scalar(f'SELECT count(*) FROM vn_durability.outbox_events WHERE run_id={literal(self.run)};'), '9')
        changed = deepcopy(payload)
        changed['transition']['events'][0]['at'] = 1
        result = self.db.sql(self.sql(changed, command_id), role='service_role', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('command_conflict', result.stderr)
        self.assertEqual(self.db.scalar(f'SELECT revision FROM vn_durability.runs WHERE id={literal(self.run)};'), '2')
