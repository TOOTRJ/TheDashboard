"""Real bounded exact candidates: source isolation, causal fills and all solvers."""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
import random
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import deny_network
from vonneumann.core.decision_inputs import DecisionInputs, DecisionInputError
from vonneumann.core.decimal_execution import DecimalExecutionConfig, _units, CASH_SCALE
from vonneumann.core.exact_rehearsal import (ExactRehearsalConfig, ExactObservation,
    ExactRehearsalError, ExactState, bootstrap, prepare_protective, prepare_decision,
    MAX_PAYLOAD_BYTES)
from vonneumann.db.command_protocol import PreparedCommand


OWNER, RUN, WORKER = (str(UUID(int=i)) for i in (1, 2, 3))
ALGORITHMS = ('genetic_algorithm', 'differential_evolution', 'particle_swarm', 'cma_es')


def inputs(at, generation=0, *, identities=True, names=True):
    dt = datetime.fromtimestamp(at, timezone.utc)
    return DecisionInputs(dt, dt, float(at),
        tuple(str(UUID(int=100000 + at * 100 + i)) for i in range(9)) if identities else (),
        tuple((generation, f'Generation-{generation}-{i}') for i in range(8)) if names else ())


def initial(algorithm='genetic_algorithm', execution=DecimalExecutionConfig()):
    config = ExactRehearsalConfig(algorithm, OWNER, RUN, execution=execution)
    return config, bootstrap(config, inputs(0))


def advance(state, stamp, price='100', end=None, close=None):
    generation = state.to_dict()['engine']['generation']
    protected = prepare_protective(state, ExactObservation(stamp, price),
                                   inputs(stamp, generation + 1, identities=False, names=False))
    candidate = prepare_decision(protected.state, ExactObservation(stamp, price, end, close),
                                  inputs(stamp, generation + 1))
    return protected, candidate


def ready_signal(algorithm='genetic_algorithm', delay=0, execution=DecimalExecutionConfig()):
    config, candidate = initial(algorithm, execution)
    for bar in range(1, 63):
        close = '100' if bar < 61 else '80' if bar == 61 else '120'
        _, candidate = advance(candidate.state, bar * 900 + (delay if bar == 62 else 0),
                                end=bar * 900, close=close)
    return config, candidate


def roundtrip_windows(algorithm, *, collect_all=False):
    config, candidate = initial(algorithm)
    interesting = [candidate]
    maximum = candidate.payload_bytes
    for bar in range(1, 74):
        # One cross up, cross down, then two low bars per common window.
        close = '100' if bar < 61 else ('200' if (bar - 61) % 4 == 1 else '40')
        for stamp, candle in ((bar * 900, True), (bar * 900 + 1, False)):
            if candidate.state.to_dict()['engine']['generation'] == 3:
                break
            price = '99' if bar >= 61 and (bar - 61) % 4 == 2 and not candle else '100'
            protected, candidate = advance(candidate.state, stamp, price,
                bar * 900 if candle else None, close if candle else None)
            maximum = max(maximum, protected.payload_bytes, candidate.payload_bytes)
            if collect_all or protected.operations:
                interesting.append(protected)
            if collect_all or candidate.operations:
                interesting.append(candidate)
    return config, candidate, interesting, maximum


class ExactRehearsalTests(unittest.TestCase):
    def setUp(self):
        guard = deny_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)

    def bridge(self, candidate):
        before = candidate.transition['before']
        revision = 1 if before is None else before['revision']
        command = PreparedCommand.batch(OWNER, RUN, WORKER, 1, revision,
            candidate.operations, version=3, transition=candidate.transition)
        self.assertEqual(command.rpc_args['payload']['transition'], candidate.transition)
        return command

    def test_all_four_real_solvers_finish_three_traded_windows_and_bind_next_cohort(self):
        random_before = random.getstate()
        maxima = {}
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                config, final, interesting, maximum = roundtrip_windows(algorithm)
                state = final.state.to_dict()
                self.assertEqual(state['engine']['generation'], 3)
                self.assertEqual(len(state['accounts']), 32)
                self.assertEqual(sum(not row['retired'] for row in state['accounts']), 8)
                self.assertGreaterEqual(len(state['positions']), 8)
                self.assertTrue(all(row['closed'] for row in state['positions']))
                final_cash = _units(state['reserve'], CASH_SCALE) + sum(
                    _units(row['cash'], CASH_SCALE) for row in state['accounts'])
                signed_pnl = sum((-1 if row['exit']['net_pnl'].startswith('-') else 1) *
                    _units(row['exit']['net_pnl'].lstrip('-'), CASH_SCALE) for row in state['positions'])
                self.assertEqual(final_cash, _units(config.initial_cash, CASH_SCALE) + signed_pnl)
                evaluations = [item for item in interesting
                    if any(event['kind'] == 'evaluation' for event in item.transition['events'])]
                self.assertEqual(len(evaluations), 3)
                for item in evaluations:
                    cohort = item.state.to_dict()['engine']['last_evaluation']['cohort']
                    self.assertEqual(cohort['phase'], 'completed')
                    self.assertEqual(cohort['member_count'], 8)
                    self.assertTrue(any(result['num_trades'] >= 1 for result in cohort['evaluations']))
                    self.assertTrue(all(result['status'] == 'completed' and result['cohort_complete']
                                        for result in cohort['evaluations']))
                    self.assertTrue(any(float.fromhex(result['fitness']['float64']) != 0
                                        for result in cohort['evaluations']))
                    self.bridge(item)
                self.assertTrue(any(action['reason'] == 'exit_signal' for item in interesting
                                    for action in item.transition['evidence']['actions']))
                self.assertLessEqual(maximum, MAX_PAYLOAD_BYTES)
                maxima[algorithm] = maximum
                self.bridge(interesting[0])
                if algorithm == 'cma_es':
                    distributions = [op for item in interesting for op in item.operations if op['kind'] == 'distribution']
                    self.assertEqual([op['stage'] for op in distributions], ['bootstrap', 'update', 'update'])
                    self.assertEqual(distributions[-1]['previous_distribution_id'], distributions[-2]['id'])
        self.assertEqual(random.getstate(), random_before)
        self.assertEqual(set(maxima), set(ALGORITHMS))

    def test_same_signal_does_not_fill_until_a_later_observation_and_snapshot_is_sealed(self):
        _, signal = ready_signal()
        before = signal.state.to_dict()
        self.assertEqual(before['positions'], [])
        self.assertTrue(all(member['pending']['action'] == 'entry' for member in before['engine']['members']))
        stamp = 62 * 900 + 1
        protected = prepare_protective(signal.state, ExactObservation(stamp, '100'), inputs(stamp))
        first = prepare_decision(protected.state, ExactObservation(stamp, '100'), inputs(stamp, 1))
        second = prepare_decision(protected.state, ExactObservation(stamp, '100'), inputs(stamp, 1))
        self.assertEqual(first.transition, second.transition)
        self.assertEqual(first.operations, second.operations)
        self.assertEqual(signal.state.to_dict(), before)
        self.assertEqual(len(first.operations), 8)
        self.assertTrue(all(op['execution']['budget'] == '25' for op in first.operations))
        first.transition['after']['accounts'].clear()
        first.operations.clear()
        self.assertEqual(len(first.state.to_dict()['accounts']), 8)
        with self.assertRaises(AttributeError):
            first.state.extra = None
        with self.assertRaises(ExactRehearsalError):
            ExactState(before)
        with self.assertRaises(ExactRehearsalError):
            prepare_decision(signal.state, ExactObservation(62 * 900, '100'), inputs(62 * 900))
        self.bridge(first)

    def test_exact_protective_thresholds_include_equalities_without_binary64_rounding(self):
        _, signal = ready_signal()
        _, opened = advance(signal.state, 62 * 900 + 1)
        cases = [('97', 'stop_loss'), ('96.999999999999999999', 'stop_loss'),
                 ('97.000000000000000001', None), ('107', 'take_profit'),
                 ('106.999999999999999999', None), ('107.000000000000000001', 'take_profit')]
        for price, reason in cases:
            with self.subTest(price=price):
                stamp = 62 * 900 + 2
                candidate = prepare_protective(opened.state, ExactObservation(stamp, price), inputs(stamp))
                self.assertEqual(len(candidate.operations), 8 if reason else 0)
                if reason:
                    self.assertEqual({row['reason'] for row in candidate.transition['evidence']['actions']}, {reason})
                    self.bridge(candidate)
        self.assertTrue(all(not row['closed'] for row in opened.state.to_dict()['positions']))

    def test_failed_candle_after_protection_cannot_erase_protective_candidate(self):
        _, signal = ready_signal()
        _, opened = advance(signal.state, 62 * 900 + 1)
        at = 64 * 900
        protected = prepare_protective(opened.state, ExactObservation(at, '97'), inputs(at))
        accepted = protected.state.to_dict()
        with self.assertRaises(ExactRehearsalError):
            prepare_decision(protected.state, ExactObservation(at, '97', at, '97'), inputs(at, 1))
        self.assertEqual(protected.state.to_dict(), accepted)
        self.assertTrue(all(position['closed'] for position in accepted['positions']))
        self.assertTrue(all(not position['closed'] for position in opened.state.to_dict()['positions']))
        self.bridge(protected)

    def test_late_candle_availability_does_not_extend_signal_expiration(self):
        _, signal = ready_signal(delay=899)
        members = signal.state.to_dict()['engine']['members']
        self.assertTrue(all(member['pending']['signal_at'] == 62 * 900 + 899 for member in members))
        _, equality = advance(signal.state, 63 * 900)
        self.assertEqual(len(equality.operations), 8)
        _, expired = advance(signal.state, 63 * 900 + 1)
        self.assertEqual(expired.operations, [])
        self.assertTrue(all(member['pending'] is None for member in expired.state.to_dict()['engine']['members']))

    def test_identity_exhaustion_and_oversize_reject_the_entire_candidate(self):
        _, signal = ready_signal()
        at = 62 * 900 + 1
        protected = prepare_protective(signal.state, ExactObservation(at, '100'), inputs(at))
        before = protected.state.to_dict()
        with self.assertRaises(DecisionInputError):
            prepare_decision(protected.state, ExactObservation(at, '100'), inputs(at, identities=False))
        with patch('vonneumann.core.exact_rehearsal.MAX_PAYLOAD_BYTES', 1024):
            with self.assertRaises(ExactRehearsalError):
                prepare_decision(protected.state, ExactObservation(at, '100'), inputs(at, 1))
        self.assertEqual(protected.state.to_dict(), before)
        accepted = prepare_decision(protected.state, ExactObservation(at, '100'), inputs(at, 1))
        self.assertEqual(len(accepted.operations), 8)

    def test_repeated_identity_and_wrong_generation_budget_do_not_partially_bootstrap(self):
        config, expected = initial()
        dt = datetime.fromtimestamp(0, timezone.utc)
        with self.assertRaises(DecisionInputError):
            bootstrap(config, DecisionInputs(dt, dt, 0., inputs(0).ids, ((1, 'Wrong'),) * 8))
        self.assertEqual(bootstrap(config, inputs(0)).transition, expected.transition)
        _, signal = ready_signal()
        at = 62 * 900 + 1
        protected = prepare_protective(signal.state, ExactObservation(at, '100'), inputs(at))
        owned = signal.state.to_dict()['engine']['used_ids'][0]
        bad = DecisionInputs(datetime.fromtimestamp(at, timezone.utc), dt, float(at), (owned,), ())
        with self.assertRaises(ExactRehearsalError):
            prepare_decision(protected.state, ExactObservation(at, '100'), bad)

    def test_legacy_floats_unsupported_profiles_invalid_source_and_wrong_phase_fail_closed(self):
        for price in (100., '100.0', '1e2', '0', '-1', '0.0000000000000000001'):
            with self.subTest(price=price), self.assertRaises(ValueError):
                ExactObservation(900, price)
        with self.assertRaises(ExactRehearsalError):
            ExactRehearsalConfig('unknown', OWNER, RUN)
        with self.assertRaises(ValueError):
            ExactRehearsalConfig('genetic_algorithm', OWNER, RUN, initial_cash=1000.)
        _, start = initial()
        with self.assertRaises(ExactRehearsalError):
            prepare_decision(start.state, ExactObservation(900, '100'), inputs(900))
        first = prepare_protective(start.state, ExactObservation(900, '100'), inputs(900))
        with self.assertRaises(ExactRehearsalError):
            prepare_protective(first.state, ExactObservation(900, '100'), inputs(900))
        with self.assertRaises(ExactRehearsalError):
            prepare_decision(first.state, ExactObservation(900, '99'), inputs(900))

    def test_failed_selection_allocation_keeps_all_four_solver_forks_repeatable(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                _, signal = ready_signal(algorithm)
                _, candidate = advance(signal.state, 62 * 900 + 1)
                _, candidate = advance(candidate.state, 63 * 900, end=63 * 900, close='80')
                _, candidate = advance(candidate.state, 63 * 900 + 1, price='99')
                _, candidate = advance(candidate.state, 64 * 900, end=64 * 900, close='80')
                at = 65 * 900
                protected = prepare_protective(candidate.state, ExactObservation(at, '100'), inputs(at))
                observation = ExactObservation(at, '100', at, '80')
                before = protected.state.to_dict()
                too_short = inputs(at, 1)
                too_short = DecisionInputs(too_short.event_at, too_short.wall_at,
                    too_short.monotonic_at, too_short.ids[:4], too_short.names)
                with self.assertRaises(DecisionInputError):
                    prepare_decision(protected.state, observation, too_short)
                self.assertEqual(protected.state.to_dict(), before)
                first = prepare_decision(protected.state, observation, inputs(at, 1))
                second = prepare_decision(protected.state, observation, inputs(at, 1))
                self.assertEqual(first.transition, second.transition)
                self.assertEqual(first.operations, second.operations)
                self.assertEqual(protected.state.to_dict(), before)
                self.assertEqual(first.state.to_dict()['engine']['generation'], 1)
                self.bridge(first)

    def test_real_cma_large_history_is_rejected_without_splitting_or_adopting_state(self):
        _, candidate = initial('cma_es')
        rejected = False
        for bar in range(1, 74):
            close = '100' if bar < 61 else ('80' if bar % 2 else '120')
            for stamp, candle in ((bar * 900, True), (bar * 900 + 1, False)):
                generation = candidate.state.to_dict()['engine']['generation']
                if generation >= 3:
                    break
                price = '99' if bar >= 61 and bar % 2 and not candle else '100'
                source = candidate.state
                before = source.to_dict()
                try:
                    protected = prepare_protective(source, ExactObservation(stamp, price), inputs(stamp))
                    source = protected.state
                    before = source.to_dict()
                    observation = ExactObservation(stamp, price, bar * 900, close) if candle else ExactObservation(stamp, price)
                    candidate = prepare_decision(source, observation, inputs(stamp, generation + 1))
                except ExactRehearsalError as error:
                    self.assertIn('whole candidate exceeds payload capacity', str(error))
                    self.assertEqual(source.to_dict(), before)
                    self.assertGreaterEqual(len(before['positions']), 32)
                    rejected = True
                    break
            if rejected:
                break
        self.assertTrue(rejected, 'the concrete dense trace must exercise whole-envelope admission')

    def test_costs_and_terminal_liquidation_flow_into_complete_evaluation(self):
        config, signal = ready_signal(execution=DecimalExecutionConfig('30', '5', '10'))
        _, candidate = advance(signal.state, 62 * 900 + 1)
        for bar in (63, 64, 65):
            _, candidate = advance(candidate.state, bar * 900, end=bar * 900, close='120')
        data = candidate.state.to_dict()
        self.assertEqual(data['engine']['generation'], 1)
        self.assertEqual(len(data['positions']), 8)
        self.assertTrue(all(position['closed'] for position in data['positions']))
        by_id = {position['account_id']: position for position in data['positions']}
        evaluation = data['engine']['last_evaluation']['cohort']['evaluations']
        for result in evaluation:
            position = by_id[result['probe_id']]
            self.assertGreater(_units(position['entry']['fee'], CASH_SCALE), 0)
            self.assertGreater(_units(position['exit']['fee'], CASH_SCALE), 0)
            self.assertTrue(position['exit']['net_pnl'].startswith('-'))
            loss = _units(position['exit']['net_pnl'][1:], CASH_SCALE)
            exact_roi_view = float(Fraction(-loss, _units(config.seed_capital, CASH_SCALE)))
            self.assertEqual(float.fromhex(result['roi']['float64']), exact_roi_view)
            self.assertLess(float.fromhex(result['fitness']['float64']), exact_roi_view)
        final_cash = _units(data['reserve'], CASH_SCALE) + sum(_units(a['cash'], CASH_SCALE) for a in data['accounts'])
        exact_losses = sum(_units(p['exit']['net_pnl'][1:], CASH_SCALE) for p in data['positions'])
        self.assertEqual(final_cash, _units(config.initial_cash, CASH_SCALE) - exact_losses)
        self.assertEqual(sum(action['reason'] == 'cohort_liquidation' for action in candidate.transition['evidence']['actions']), 8)
        self.bridge(candidate)

    def test_minimum_price_grid_remains_exact_through_entry_and_exit(self):
        _, signal = ready_signal()
        at = 62 * 900 + 1
        _, opened = advance(signal.state, at, price='0.000000000000000001')
        self.assertEqual(len(opened.operations), 8)
        for operation in opened.operations:
            self.assertEqual(operation['quantity'], '25000000000000000000')
            self.assertEqual(operation['notional'], '25')
        closed = prepare_protective(opened.state,
            ExactObservation(at + 1, '0.000000000000000002'), inputs(at + 1))
        self.assertEqual(len(closed.operations), 8)
        self.assertTrue(all(operation['proceeds'] == '50' for operation in closed.operations))
        self.assertTrue(all(account['cash'] == '125' for account in closed.state.to_dict()['accounts']))
        self.bridge(opened)
        self.bridge(closed)

    def test_exact_profile_does_not_read_mutable_application_preset_registry(self):
        config, before = initial()
        with patch.dict('vonneumann.core.colony_config.PRESET_CONFIGS', {'ema_baseline_v1': None}):
            after = bootstrap(config, inputs(0))
        self.assertEqual(before.transition, after.transition)
        with patch.dict('vonneumann.core.gene_registry.GENOME_POLICY', {'version': 'future-policy'}):
            with self.assertRaises(ExactRehearsalError):
                bootstrap(config, inputs(0))

    def test_permuted_identity_budgets_keep_canonical_projection_order(self):
        config, _ = initial()
        original = inputs(0)
        permuted = DecisionInputs(original.event_at, original.wall_at, original.monotonic_at,
                                  tuple(reversed(original.ids)), original.names)
        candidate = bootstrap(config, permuted)
        rows = candidate.state.to_dict()['accounts']
        self.assertEqual([row['id'] for row in rows], sorted(row['id'] for row in rows))
        self.bridge(candidate)


if __name__ == '__main__':
    unittest.main()
