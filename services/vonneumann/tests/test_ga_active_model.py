"""Fresh GA mechanics and atomic offline ledger/provenance acceptance."""
from copy import deepcopy
from fractions import Fraction
import json
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network
from tests.test_exact_rehearsal import OWNER, RUN, WORKER, inputs
from vonneumann.core import exact_rehearsal as base, exact_lifecycle as old
from vonneumann.core.decimal_execution import DecimalExecutionConfig, CASH_SCALE, _units
from vonneumann.research import ga_active_model as ga


def initial(**kwargs):
    ledger = ga.SimulationLedger(OWNER, RUN)
    config = ga.GAConfig('genetic_algorithm', OWNER, RUN, **kwargs)
    candidate = ga.bootstrap(config, inputs(0), ledger=ledger)
    ledger.accept(candidate)
    return ledger, candidate


def advance(ledger, state, stamp, price='100', end=None, close=None):
    generation = state.to_dict()['engine']['generation']
    protected = ga.prepare_protective(state, ga.ExactObservation(stamp, price), inputs(stamp), ledger=ledger)
    ledger.accept(protected)
    candidate = ga.prepare_decision(protected.state, ga.ExactObservation(stamp, price, end, close),
        inputs(stamp, generation + 1), ledger=ledger)
    ledger.accept(candidate)
    return protected, candidate


def ready(**kwargs):
    ledger, candidate = initial(**kwargs)
    for bar in range(1, 63):
        close = '100' if bar < 61 else '80' if bar == 61 else '120'
        _, candidate = advance(ledger, candidate.state, bar * 900, end=bar * 900, close=close)
    return ledger, candidate


def opened(**kwargs):
    ledger, signal = ready(**kwargs)
    _, candidate = advance(ledger, signal.state, 62 * 900 + 1)
    return ledger, candidate


def trace(*, dense, windows=32, observer=None):
    ledger, candidate = initial()
    measured = {'dense': dense, 'requested_windows': windows, 'accepted_candidates': 1,
        'maximum_active_bytes': len(base._json(candidate.state.to_dict())),
        'maximum_command_bytes': candidate.payload_bytes, 'maximum_positions': 0,
        'maximum_history_bytes': len(base._json(candidate.history))}
    def observe(c):
        state = c.state.to_dict()
        measured['accepted_candidates'] += 1
        measured['maximum_active_bytes'] = max(measured['maximum_active_bytes'], len(base._json(state)))
        measured['maximum_command_bytes'] = max(measured['maximum_command_bytes'], c.payload_bytes)
        measured['maximum_positions'] = max(measured['maximum_positions'], len(state['positions']))
        measured['maximum_history_bytes'] = max(measured['maximum_history_bytes'], len(base._json(c.history)))
        assert len(state['accounts']) == len(state['engine']['members']) == 8
        assert all(not p['closed'] for p in state['positions'])
        assert 'used_ids' not in state['engine'] and 'last_evaluation' not in state['engine']
        assert sum(_units(a['cash'], CASH_SCALE) for a in state['accounts']) + _units(state['reserve'], CASH_SCALE) + sum(
            _units(p['entry']['cash_debit'], CASH_SCALE) for p in state['positions']) == 1000 * 10**CASH_SCALE
        if observer: observer(c)
    for bar in range(1, 61 + windows * 4 + 1):
        if bar < 61: close = '100'
        else:
            high = bar % 2 == 0 if dense else (bar - 61) % 4 == 1
            close = '120' if high else '80'
        for stamp, candle in ((bar * 900, True), (bar * 900 + 1, False)):
            if candidate.state.to_dict()['engine']['generation'] == windows: break
            protected, candidate = advance(ledger, candidate.state, stamp,
                end=bar * 900 if candle else None, close=close if candle else None)
            observe(protected); observe(candidate)
    data = candidate.state.to_dict()
    histories = ledger.history
    measured.update(completed_windows=data['engine']['generation'],
        final_active_bytes=len(base._json(data)), final_accounts=len(data['accounts']),
        final_positions=len(data['positions']), final_quote_sequence=data['source']['quote_sequence'],
        final_candle_count=data['engine']['ema']['count'],
        finalized_assessments=sum(len(h['assessments']) for h in histories),
        closed_positions=sum(len(h['closed_positions']) for h in histories),
        retired_accounts=sum(len(h['retired_accounts']) for h in histories),
        historical_identities=len(ledger._identities))
    return measured, ledger, candidate


class GAActiveModelTests(OfflineTestMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with deny_network():
            cls.traces = {d: trace(dense=d) for d in (False, True)}
            cls.open = opened()

    def test_many_sparse_dense_windows_bound_current_state_and_exact_economics(self):
        for dense, (stats, ledger, candidate) in self.traces.items():
            with self.subTest(dense=dense):
                self.assertEqual(stats['completed_windows'], 32)
                self.assertEqual(stats['finalized_assessments'], 256)
                self.assertEqual(stats['retired_accounts'], 256)
                self.assertEqual(stats['final_accounts'], 8)
                self.assertLess(stats['maximum_active_bytes'], 65536)
                self.assertLess(stats['maximum_command_bytes'], base.MAX_PAYLOAD_BYTES)
                self.assertLessEqual(stats['maximum_positions'], 8)
                self.assertGreater(stats['historical_identities'], 100)
                self.assertGreater(stats['closed_positions'], 64)
                for h in ledger.history:
                    for a in h['assessments']:
                        self.assertTrue(a['selection_eligible'])
                        self.assertEqual(a['format'], ga.ASSESSMENT_FORMAT)
                        self.assertEqual(a['finalized_revision'], h['revision'])
                        self.assertEqual(a['metrics']['captured_revision'], h['revision'])
                        self.assertFalse(a['metrics']['has_open_position'])
                        self.assertEqual(a['metrics']['terminal_cash'], '100')
                        self.assertEqual(a['fitness_float64'], a['metrics']['fitness_float64'])
                        self.assertEqual(a['execution']['config']['fee_bps'], '0')

    def test_final_close_updates_cash_count_and_drawdown_before_scoring(self):
        ledger, candidate = opened(execution=DecimalExecutionConfig(fee_bps='100', half_spread_bps='50'))
        # Keep holdings below the 7% take-profit boundary; normal deadline closes
        # them after a new peak and adds fees/adverse execution to drawdown.
        for bar in (63, 64):
            _, candidate = advance(ledger, candidate.state, bar * 900, price='101', end=bar * 900, close='120')
        protected, candidate = advance(ledger, candidate.state, 65 * 900, price='100', end=65 * 900, close='120')
        rows = candidate.history['assessments']
        self.assertEqual(len(rows), 8)
        self.assertEqual(len(candidate.history['closed_positions']), 8)
        self.assertEqual(candidate.state.to_dict()['engine']['generation'], 1)
        old_members = {m['id']: m for m in protected.state.to_dict()['engine']['members']}
        for row in rows:
            m = row['metrics']; before = old_members[row['probe_id']]
            self.assertEqual(before['num_trades'], 0)
            self.assertEqual(m['closed_trade_count'], 1)
            self.assertLess(Fraction(m['terminal_cash']), 100)
            dd = Fraction(int(m['max_drawdown']['numerator']), int(m['max_drawdown']['denominator']))
            old_dd = Fraction(int(before['max_drawdown']['numerator']), int(before['max_drawdown']['denominator']))
            self.assertGreater(dd, old_dd)
            roi = Fraction(m['terminal_cash']) / 100 - 1
            self.assertEqual(float(roi).hex(), m['roi_float64'])
            self.assertEqual((float(roi) - 2 * float(dd)).hex(), m['fitness_float64'])
            self.assertEqual(row['fitness_policy']['version'], ga.FITNESS_POLICY['version'])
            self.assertEqual(row['measurement_basis'], 'post-liquidation-closed-fills')

    def test_early_terminal_freezes_metrics_until_common_deadline(self):
        ledger, candidate = opened(account_loss_bps='10000')
        terminal = ga.prepare_protective(candidate.state, ga.ExactObservation(55802, '0.1'), inputs(55802), ledger=ledger)
        ledger.accept(terminal)
        state = terminal.state.to_dict()
        self.assertTrue(all(m['terminal'] for m in state['engine']['members']))
        snapshots = {m['id']: m['assessment'] for m in state['engine']['members']}
        self.assertEqual(len(state['accounts']), 8)
        self.assertEqual(state['positions'], [])
        candidate = terminal
        for bar in (63, 64, 65):
            _, candidate = advance(ledger, candidate.state, bar * 900, end=bar * 900, close='120')
        self.assertEqual(len(candidate.history['assessments']), 8)
        for row in candidate.history['assessments']:
            self.assertTrue(row['early_terminal_frozen'])
            self.assertEqual(row['metrics'], snapshots[row['probe_id']])
            self.assertLess(row['metrics']['captured_revision'], row['finalized_revision'])
            self.assertEqual(row['reason'], 'drawdown')
            self.assertTrue(row['selection_eligible'])

    def test_abort_withholds_all_scores_and_retains_open_holdings(self):
        ledger, candidate = opened()
        before = candidate.state.to_dict()
        stopped = ga.prepare_control(candidate.state, 'stop', inputs(55802), ledger=ledger)
        ledger.accept(stopped)
        self.assertEqual(stopped.state.to_dict()['positions'], before['positions'])
        self.assertEqual(len(stopped.history['assessments']), 8)
        self.assertIsNone(stopped.history['selection'])
        for row in stopped.history['assessments']:
            self.assertFalse(row['selection_eligible'])
            self.assertEqual(row['status'], 'aborted')
            self.assertIsNone(row['fitness_float64'])
            self.assertIsNone(row['roi_float64'])
            self.assertIsNone(row['metrics']['fitness_float64'])
            self.assertIsNone(row['metrics']['terminal_cash'])
            self.assertTrue(row['metrics']['has_open_position'])
        with self.assertRaises(ValueError):
            ga.prepare_protective(stopped.state, ga.ExactObservation(55803, '100'), inputs(55803), ledger=ledger)

    def test_abort_after_early_terminal_withholds_frozen_scores(self):
        ledger, candidate = opened(account_loss_bps='10000')
        terminal = ga.prepare_protective(candidate.state, ga.ExactObservation(55802, '0.1'), inputs(55802), ledger=ledger)
        ledger.accept(terminal)
        stopped = ga.prepare_control(terminal.state, 'stop', inputs(55803), ledger=ledger)
        ledger.accept(stopped)
        for row in stopped.history['assessments']:
            self.assertTrue(row['early_terminal_frozen'])
            self.assertIsNone(row['metrics']['fitness_float64'])
            self.assertIsNone(row['metrics']['roi_ratio'])
            self.assertIsNotNone(row['metrics']['terminal_cash'])

    def test_pause_resume_restart_does_not_tell_aborted_results(self):
        ledger, candidate = opened()
        pause = ga.prepare_control(candidate.state, 'pause', inputs(55802), ledger=ledger); ledger.accept(pause)
        resume = ga.prepare_control(pause.state, 'resume', inputs(55803), ledger=ledger); ledger.accept(resume)
        _, following = advance(ledger, resume.state, 55804)
        self.assertEqual(following.state.to_dict()['engine']['generation'], 1)
        self.assertEqual(following.history['assessments'], [])
        self.assertIsNone(following.history['selection'])
        self.assertEqual(following.state.to_dict()['engine']['cohort']['phase'], 'warming')
        self.assertEqual(len(following.history['closed_positions']), 8)
        self.assertTrue(all(op['lineage']['operation'] == 'restart_clone'
            for op in following.operations if op['kind'] == 'birth'))

    def test_historical_reuse_rejected_after_original_account_leaves_active_state(self):
        stats, original_ledger, candidate = self.traces[False]
        ledger = deepcopy(original_ledger)
        founder = ledger.history[0]['allocated_ids'][0]
        self.assertNotIn(founder, {m['id'] for m in candidate.state.to_dict()['engine']['members']})
        data, strategy, cohort = candidate.state._fork()
        builder = ga._Builder(data, inputs(999999, 33).new_cursor(), 999999, ledger)
        with self.assertRaisesRegex(ValueError, 'identity reuse'): builder.allocate(founder)
        self.assertEqual(ledger._current, candidate.state.to_dict())

    def test_preparation_does_not_publish_and_repeated_wire_is_identical(self):
        ledger, candidate = initial()
        before = candidate.state.to_dict(); histories = ledger.history
        args = (candidate.state, ga.ExactObservation(1, '100'), inputs(1))
        one = ga.prepare_protective(*args, ledger=ledger)
        two = ga.prepare_protective(*args, ledger=ledger)
        self.assertEqual(one._wire, two._wire)
        self.assertEqual(ledger.history, histories)
        self.assertEqual(candidate.state.to_dict(), before)
        ledger.accept(one)
        self.assertEqual(ledger.accept(two).to_dict(), one.state.to_dict())
        with self.assertRaisesRegex(ValueError, 'prior state'):
            ga.prepare_protective(candidate.state, ga.ExactObservation(2, '100'), inputs(2), ledger=ledger)

    def test_wrong_owner_run_old_state_non_ga_and_direct_decode_fail(self):
        ledger, candidate = initial()
        foreign = ga.SimulationLedger(WORKER, RUN)
        with self.assertRaisesRegex(ValueError, 'owner/run'):
            ga.prepare_control(candidate.state, 'stop', inputs(1), ledger=foreign)
        with self.assertRaises(ValueError): ga.GAState(candidate.state.to_dict())
        with self.assertRaises(ValueError): ga.GAConfig('particle_swarm', OWNER, RUN)
        previous = old.bootstrap(old.ExactLifecycleConfig('genetic_algorithm', OWNER, RUN), inputs(0))
        with self.assertRaises(ValueError): ga.prepare_control(previous.state, 'stop', inputs(1), ledger=ledger)
        with self.assertRaises(ValueError): old.prepare_control(candidate.state, 'stop', inputs(1))
        with self.assertRaises(ValueError): ledger.accept(previous)

    def boundary_state(self, field, value):
        ledger, candidate = initial()
        data, strategy, cohort = candidate.state._fork()
        target = data
        for key in field[:-1]: target = target[key]
        target[field[-1]] = value
        state = ga.GAState._seal(data, strategy, cohort)
        # Trusted fixture setup for a boundary; explicitly not a restore API.
        ledger._current = state.to_dict()
        ledger._owned_current = state
        return ledger, state

    def test_reserved_final_revision_accepts_only_stop_without_overflow(self):
        ledger, state = self.boundary_state(('revision',), ga.MAX_COUNTER - 1)
        with self.assertRaises(base.ExactCapacityError):
            ga.prepare_control(state, 'pause', inputs(1), ledger=ledger)
        with self.assertRaises(base.ExactCapacityError):
            ga.prepare_protective(state, ga.ExactObservation(1, '100'), inputs(1), ledger=ledger)
        stopped = ga.prepare_control(state, 'stop', inputs(1), ledger=ledger)
        self.assertEqual(stopped.state.revision, ga.MAX_COUNTER)
        ledger.accept(stopped)
        self.assertEqual(stopped.state.to_dict()['status'], 'stopped')

    def test_source_counter_passes_old_cap_then_rejects_before_wrap_with_stop_available(self):
        ledger, state = self.boundary_state(('source', 'quote_sequence'), 4095)
        next_one = ga.prepare_protective(state, ga.ExactObservation(1, '100'), inputs(1), ledger=ledger)
        self.assertEqual(next_one.state.to_dict()['source']['quote_sequence'], 4096)
        ledger, state = self.boundary_state(('source', 'quote_sequence'), ga.MAX_COUNTER - 1)
        before = state.to_dict()
        with self.assertRaises(base.ExactCapacityError):
            ga.prepare_protective(state, ga.ExactObservation(1, '100'), inputs(1), ledger=ledger)
        self.assertEqual(state.to_dict(), before)
        stopped = ga.prepare_control(state, 'stop', inputs(1), ledger=ledger)
        ledger.accept(stopped)
        self.assertEqual(stopped.state.to_dict()['source']['quote_sequence'], ga.MAX_COUNTER - 1)
        self.assertEqual(base.MAX_GENERATIONS, 3)

    def test_policy_drift_and_invalid_integer_counter_rejected(self):
        with patch.dict(ga.FITNESS_POLICY, {'drawdown_weight': 3.0}):
            with self.assertRaisesRegex(ValueError, 'policy changed'): initial()
        for value in (True, -1, 1.0, ga.MAX_COUNTER):
            with self.subTest(value=value), self.assertRaises(base.ExactCapacityError):
                ga._counter(value, 'test')

    def test_generation_name_limit_and_complete_payload_failure_preserve_stop(self):
        with self.assertRaisesRegex(ValueError, 'generation capacity'):
            ga._capacity({'engine': {'generation': ga.MAX_GENERATION}})
        ledger, candidate = initial()
        normal = inputs(1)
        oversized = ga.DecisionInputs(normal.event_at, normal.wall_at, normal.monotonic_at,
            normal.ids, tuple((0, 'N' * 128) for _ in range(4096)))
        before = candidate.state.to_dict(); history = ledger.history
        with self.assertRaises(base.ExactCapacityError):
            ga.prepare_protective(candidate.state, ga.ExactObservation(1, '100'), oversized, ledger=ledger)
        self.assertEqual(candidate.state.to_dict(), before)
        self.assertEqual(ledger.history, history)
        stopped = ga.prepare_control(candidate.state, 'stop', inputs(1, identities=False, names=False), ledger=ledger)
        ledger.accept(stopped)
        self.assertEqual(stopped.state.to_dict()['status'], 'stopped')

    def test_first_three_windows_match_existing_lifecycle_operations_and_solver(self):
        legacy = old.bootstrap(old.ExactLifecycleConfig('genetic_algorithm', OWNER, RUN), inputs(0))
        def compare(fresh):
            nonlocal legacy
            e = fresh.transition['evidence']
            stamp = fresh.state.to_dict()['engine']['last_quote']['timestamp']
            generation = legacy.state.to_dict()['engine']['generation']
            observation = old.ExactObservation(**e['observation'])
            if e['kind'] == 'protective':
                legacy = old.prepare_protective(legacy.state, observation, inputs(stamp))
            else:
                legacy = old.prepare_decision(legacy.state, observation, inputs(stamp, generation + 1))
            a, b = fresh.state.to_dict(), legacy.state.to_dict()
            self.assertEqual(fresh.operations, legacy.operations)
            self.assertEqual(a['reserve'], b['reserve'])
            members = {m['id'] for m in b['engine']['members']}
            self.assertEqual(a['accounts'], [row for row in b['accounts'] if row['id'] in members])
            self.assertEqual(a['positions'], [p for p in b['positions'] if not p['closed']])
            for key in ('optimizer', 'cohort', 'ema', 'lifecycle', 'generation'):
                self.assertEqual(a['engine'][key], b['engine'][key])
            self.assertEqual([{k: v for k, v in m.items() if k != 'assessment'} for m in a['engine']['members']],
                             b['engine']['members'])
        stats, _, _ = trace(dense=True, windows=3, observer=compare)
        self.assertEqual(stats['completed_windows'], 3)

    def test_omitted_or_changed_finalized_records_rejected_without_publication(self):
        ledger, candidate = opened()
        for bar in (63, 64):
            _, candidate = advance(ledger, candidate.state, bar * 900, end=bar * 900, close='120')
        protected = ga.prepare_protective(candidate.state, ga.ExactObservation(58500, '100'), inputs(58500), ledger=ledger)
        ledger.accept(protected)
        finalized = ga.prepare_decision(protected.state, ga.ExactObservation(58500, '100', 58500, '120'),
                                       inputs(58500, 1), ledger=ledger)
        for change in ('omit', 'cash', 'count', 'policy', 'owner'):
            p = json.loads(finalized._wire)
            if change == 'omit': p['history']['assessments'].pop()
            elif change == 'cash': p['history']['assessments'][0]['metrics']['terminal_cash'] = '999'
            elif change == 'count': p['history']['assessments'][0]['metrics']['closed_trade_count'] += 1
            elif change == 'policy': p['history']['assessments'][0]['fitness_policy']['version'] = 'invented'
            else: p['history']['assessments'][0]['owner_id'] = WORKER
            size = len(json.dumps(p, sort_keys=True, ensure_ascii=False, separators=(', ', ': ')).encode())
            forged = ga.GACandidate(finalized.state, base._json(p), size)
            before, history = deepcopy(ledger._current), ledger.history
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'provenance boundary'):
                ledger.accept(forged)
            self.assertEqual(ledger._current, before)
            self.assertEqual(ledger.history, history)
        ledger.accept(finalized)
        current = ledger._current
        ledger.accept(protected)  # Original replay after advance cannot roll back current state.
        self.assertEqual(ledger._current, current)

    def test_ledger_rejects_corrupt_economics_and_omitted_holding_atomically(self):
        ledger, candidate = initial()
        prepared = ga.prepare_protective(candidate.state, ga.ExactObservation(1, '100'), inputs(1), ledger=ledger)
        for mutate in ('cash', 'positions'):
            source_ledger, held = opened() if mutate == 'positions' else (ledger, candidate)
            if mutate == 'positions':
                prepared = ga.prepare_protective(held.state, ga.ExactObservation(55802, '100'), inputs(55802), ledger=source_ledger)
            data, strategy, cohort = prepared.state._fork()
            if mutate == 'cash': data['reserve'] = '0'
            else: data['positions'].pop()
            payload = json.loads(prepared._wire); payload['transition']['after'] = data
            wire = base._json(payload)
            size = len(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(', ', ': ')).encode())
            forged = ga.GACandidate(ga.GAState._seal(data, strategy, cohort), wire, size)
            original = deepcopy(source_ledger._current); history = source_ledger.history
            with self.assertRaisesRegex(ValueError, 'boundary differs'): source_ledger.accept(forged)
            self.assertEqual(source_ledger._current, original)
            self.assertEqual(source_ledger.history, history)


class GAProductionBoundaryTests(OfflineTestMixin, unittest.TestCase):
    def test_research_candidate_cannot_enter_existing_runtime_versions(self):
        from vonneumann.db.command_protocol import PreparedCommand
        _, candidate = initial()
        for version in (5, 6):
            with self.subTest(version=version), self.assertRaises(ValueError):
                PreparedCommand.batch(OWNER, RUN, WORKER, 1, 1, candidate.operations,
                    version=version, transition=candidate.transition)


if __name__ == '__main__': unittest.main()
