"""Independent v4 policy acceptance against real exact states and all solvers."""
from __future__ import annotations

from fractions import Fraction
import random
import unittest
from unittest.mock import patch

from tests.security_support import deny_network
from tests.test_exact_rehearsal import ALGORITHMS, OWNER, RUN, inputs
from vonneumann.core import exact_lifecycle as life
from vonneumann.core.decision_inputs import DecisionInputs, DecisionInputError
from vonneumann.core.decimal_execution import CASH_SCALE, DecimalExecutionConfig, _units


def initial(algorithm='genetic_algorithm', *, loss='3000', execution=DecimalExecutionConfig(),
            initial_cash='1000'):
    config = life.ExactLifecycleConfig(algorithm, OWNER, RUN, initial_cash=initial_cash,
                                      execution=execution, account_loss_bps=loss)
    return config, life.bootstrap(config, inputs(0))


def advance(state, stamp, price='100', end=None, close=None):
    generation = state.to_dict()['engine']['generation']
    protected = life.prepare_protective(state, life.ExactObservation(stamp, price), inputs(stamp))
    decided = life.prepare_decision(protected.state,
        life.ExactObservation(stamp, price, end, close), inputs(stamp, generation + 1))
    return protected, decided


def ready_signal(algorithm='genetic_algorithm', **kwargs):
    config, candidate = initial(algorithm, **kwargs)
    for bar in range(1, 63):
        close = '100' if bar < 61 else '80' if bar == 61 else '120'
        _, candidate = advance(candidate.state, bar * 900, end=bar * 900, close=close)
    return config, candidate


def opened(algorithm='genetic_algorithm', **kwargs):
    config, signal = ready_signal(algorithm, **kwargs)
    _, candidate = advance(signal.state, 62 * 900 + 1)
    return config, candidate


def cash_total(data):
    return _units(data['reserve'], CASH_SCALE) + sum(
        _units(row['cash'], CASH_SCALE) for row in data['accounts'])


def live_positions(data):
    return [row for row in data['positions'] if not row['closed']]


class ExactLifecycleTests(unittest.TestCase):
    def setUp(self):
        guard = deny_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)

    def test_policy_is_version_four_with_explicit_no_lifespan_and_strict_bps(self):
        config, candidate = initial()
        self.assertEqual(config.run_configuration()['durability_contract_version'], 4)
        policy = config.to_dict()['lifecycle_policy']
        self.assertEqual(policy['account_loss_bps'], '3000')
        self.assertEqual(policy['death_drawdown_bps'], '2000')
        self.assertEqual(policy['max_lifespan_seconds'], 0)
        self.assertEqual(candidate.state.to_dict()['engine']['cohort']['phase'], 'warming')
        for invalid in (0, 30.0, True, '0', '3000.0', '03000', '10001', '-1', '1e3'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                life.ExactLifecycleConfig('genetic_algorithm', OWNER, RUN, account_loss_bps=invalid)

    def test_colony_trip_exact_boundary_and_neighboring_price_quanta(self):
        _, candidate = opened(loss='50')
        before = candidate.state.to_dict()
        for price, tripped in (('97.5', True), ('97.499999999999999999', True),
                               ('97.500000000000000001', False)):
            with self.subTest(price=price):
                result = life.prepare_protective(candidate.state,
                    life.ExactObservation(55802, price), inputs(55802))
                data = result.state.to_dict()
                self.assertEqual(data['status'], 'risk_halted' if tripped else 'running')
                risk = data['engine']['lifecycle']['risk']
                self.assertEqual(risk['active'], tripped)
                self.assertEqual(risk['baseline_equity'], '1000')
                expected = Fraction(800) + 2 * Fraction(price)
                self.assertEqual(Fraction(risk['observed_equity']), expected)
                self.assertEqual(len(live_positions(data)), 8)
                self.assertEqual(data['engine']['cohort']['phase'], 'aborted' if tripped else 'evaluating')
        self.assertEqual(candidate.state.to_dict(), before)

    def test_halt_is_latched_rebound_does_not_recover_and_stop_loss_still_runs(self):
        _, candidate = opened(loss='50')
        halted = life.prepare_protective(candidate.state, life.ExactObservation(55802, '97.5'), inputs(55802))
        trip = halted.state.to_dict()['engine']['lifecycle']['risk']['trip_id']
        rebound = life.prepare_protective(halted.state, life.ExactObservation(55803, '100'), inputs(55803))
        self.assertEqual(rebound.state.to_dict()['status'], 'risk_halted')
        self.assertEqual(rebound.state.to_dict()['engine']['lifecycle']['risk']['trip_id'], trip)
        decided = life.prepare_decision(rebound.state, life.ExactObservation(55803, '100'), inputs(55803, 1))
        self.assertEqual(decided.operations, [])
        self.assertEqual(decided.state.to_dict()['engine']['generation'], 0)
        protected = life.prepare_protective(decided.state, life.ExactObservation(55804, '97'), inputs(55804))
        self.assertEqual(len([op for op in protected.operations if op['kind'] == 'close']), 8)
        self.assertEqual(protected.state.to_dict()['status'], 'risk_halted')
        self.assertEqual(protected.state.to_dict()['engine']['lifecycle']['risk']['trip_id'], trip)
        self.assertEqual(live_positions(protected.state.to_dict()), [])

    def test_colony_boundary_uses_all_thirty_six_cash_places_without_rounding(self):
        for initial_cash, expected in (('1000.' + '0' * 35 + '1', 'running'),
                                       ('999.' + '9' * 36, 'risk_halted')):
            with self.subTest(initial_cash=initial_cash):
                _, candidate = opened(loss='50', initial_cash=initial_cash)
                result = life.prepare_protective(candidate.state,
                    life.ExactObservation(55802, '97.5'), inputs(55802))
                data = result.state.to_dict()
                self.assertEqual(data['status'], expected)
                self.assertEqual(Fraction(data['engine']['lifecycle']['risk']['observed_equity']),
                                 Fraction(initial_cash) - 5)
                self.assertEqual(data['engine']['lifecycle']['risk']['baseline_equity'], initial_cash)

    def test_recovery_requires_current_trip_strict_equity_and_complete_current_candle(self):
        _, candidate = opened(loss='50')
        halted = life.prepare_protective(candidate.state, life.ExactObservation(55802, '97.5'), inputs(55802))
        trip = halted.state.to_dict()['engine']['lifecycle']['risk']['trip_id']
        with self.assertRaises(ValueError):
            life.prepare_control(halted.state, 'recover', inputs(55802),
                life.ExactObservation(55802, '97.5', 55800, '120'), trip_id=trip)
        rebound = life.prepare_protective(halted.state, life.ExactObservation(55803, '100'), inputs(55803))
        before = rebound.state.to_dict()
        for observation, identity in ((None, trip), (life.ExactObservation(55803, '100'), trip),
                (life.ExactObservation(55803, '100', 55800, '120'), RUN),
                (life.ExactObservation(55802, '100', 55800, '120'), trip),
                (life.ExactObservation(55803, '99', 55800, '120'), trip)):
            with self.subTest(observation=observation, identity=identity), self.assertRaises(ValueError):
                life.prepare_control(rebound.state, 'recover', inputs(55803), observation, trip_id=identity)
        recovered = life.prepare_control(rebound.state, 'recover', inputs(55803),
            life.ExactObservation(55803, '100', 55800, '120'), trip_id=trip)
        data = recovered.state.to_dict()
        risk = data['engine']['lifecycle']['risk']
        self.assertEqual(data['status'], 'running')
        self.assertFalse(risk['active'])
        self.assertEqual(risk['baseline_equity'], '1000')
        self.assertEqual(risk['trip_id'], trip)
        self.assertEqual(risk['recovery_count'], 1)
        self.assertTrue(data['engine']['lifecycle']['restart_required'])
        self.assertEqual(data['engine']['lifecycle']['signals_after'], 55803)
        self.assertTrue(all(member['pending'] is None for member in data['engine']['members']))
        self.assertEqual(data['engine']['cohort']['phase'], 'aborted')
        self.assertEqual(rebound.state.to_dict(), before)
        with self.assertRaises(ValueError):
            life.prepare_decision(recovered.state,
                life.ExactObservation(55803, '100', 55800, '120'), inputs(55803, 1))

    def test_halted_run_cannot_pause_or_resume_and_stopping_preserves_positions(self):
        _, candidate = opened(loss='50')
        halted = life.prepare_protective(candidate.state, life.ExactObservation(55802, '97.5'), inputs(55802))
        before = halted.state.to_dict()
        for action in ('pause', 'resume'):
            with self.subTest(action=action), self.assertRaises(ValueError):
                life.prepare_control(halted.state, action, inputs(55803))
        stopped = life.prepare_control(halted.state, 'stop', inputs(55803))
        data = stopped.state.to_dict()
        self.assertEqual(data['status'], 'stopped')
        self.assertEqual(data['positions'], before['positions'])
        self.assertEqual(data['accounts'], before['accounts'])
        self.assertEqual(data['reserve'], before['reserve'])
        self.assertFalse(any(op['kind'] in {'close', 'retire', 'birth'} for op in stopped.operations))
        self.assertEqual(halted.state.to_dict(), before)
        with self.assertRaises(ValueError):
            life.prepare_protective(stopped.state, life.ExactObservation(55804, '20'), inputs(55804))

    def test_pause_suspends_protection_and_controls_cannot_erase_held_positions(self):
        _, candidate = opened()
        before = candidate.state.to_dict()
        paused = life.prepare_control(candidate.state, 'pause', inputs(55802))
        data = paused.state.to_dict()
        self.assertEqual(data['status'], 'paused')
        self.assertEqual(data['engine']['cohort']['phase'], 'aborted')
        self.assertEqual(data['positions'], before['positions'])
        self.assertEqual(data['accounts'], before['accounts'])
        self.assertFalse(any(event['kind'] == 'evaluation' for event in paused.transition['events']))
        with self.assertRaises(ValueError):
            life.prepare_protective(paused.state, life.ExactObservation(55803, '20'), inputs(55803))
        with self.assertRaises(ValueError):
            life.prepare_decision(paused.state, life.ExactObservation(55801, '100'), inputs(55801))
        stopped = life.prepare_control(paused.state, 'stop', inputs(55803))
        self.assertEqual(stopped.state.to_dict()['positions'], before['positions'])
        self.assertEqual(candidate.state.to_dict(), before)

    def test_all_four_interrupted_searches_restart_unscored_with_fresh_accounts(self):
        random_before = random.getstate()
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                _, candidate = opened(algorithm)
                before = candidate.state.to_dict()
                original_members = before['engine']['members']
                paused = life.prepare_control(candidate.state, 'pause', inputs(55802))
                resumed = life.prepare_control(paused.state, 'resume', inputs(55803))
                self.assertEqual(resumed.state.to_dict()['engine']['cohort']['phase'], 'aborted')
                protected, restarted = advance(resumed.state, 55804, end=55800, close='120')
                data = restarted.state.to_dict()
                self.assertEqual(data['engine']['generation'], 1)
                self.assertEqual(data['engine']['lifecycle']['search_epoch'], 1)
                self.assertFalse(data['engine']['lifecycle']['restart_required'])
                self.assertTrue(all(row['closed'] for row in data['positions']))
                self.assertEqual(cash_total(data), 1000 * 10**CASH_SCALE)
                current = data['engine']['members']
                self.assertEqual(len(current), 8)
                self.assertTrue(set(row['id'] for row in original_members).isdisjoint(row['id'] for row in current))
                self.assertTrue(all(member['num_trades'] == 0 and member['pending'] is None for member in current))
                self.assertEqual(sum(not row['retired'] for row in data['accounts']), 8)
                self.assertTrue(all(row['cash'] == '100' for row in data['accounts'] if not row['retired']))
                self.assertFalse(any(event['kind'] == 'evaluation' for item in (paused, resumed, restarted)
                                     for event in item.transition['events']))
                births = [op for op in restarted.operations if op['kind'] == 'birth']
                self.assertEqual(len(births), 8)
                self.assertEqual([op['lineage']['sources'][0]['source_id'] for op in births],
                                 [row['id'] for row in original_members])
                self.assertTrue(all(op['lineage']['version'] == 2 and
                    op['lineage']['operation'] == 'restart_clone' and
                    [source['role'] for source in op['lineage']['sources']] ==
                    ['clone_source', 'asset_template'] for op in births))
                self.assertEqual(data['engine']['cohort']['phase'], 'warming')
                for old, new in zip(original_members, current):
                    self.assertEqual({key: value for key, value in old['genome'].items()
                                      if key not in {'generation', 'parent_ids'}},
                                     {key: value for key, value in new['genome'].items()
                                      if key not in {'generation', 'parent_ids'}})
                self.assertEqual(candidate.state.to_dict(), before)
                repeat = life.prepare_decision(protected.state,
                    life.ExactObservation(55804, '100', 55800, '120'), inputs(55804, 1))
                self.assertEqual(restarted.transition, repeat.transition)
                _, next_window = advance(restarted.state, 55805, end=55800, close='120')
                self.assertEqual(next_window.state.to_dict()['engine']['cohort']['phase'], 'evaluating')
                self.assertEqual(next_window.operations, [])
                self.assertTrue(all(row['pending'] is None for row in next_window.state.to_dict()['engine']['members']))
        self.assertEqual(random.getstate(), random_before)

    def test_pause_during_warmup_can_accumulate_history_then_restart_without_trading(self):
        _, candidate = initial()
        _, candidate = advance(candidate.state, 900, end=900, close='100')
        paused = life.prepare_control(candidate.state, 'pause', inputs(901))
        resumed = life.prepare_control(paused.state, 'resume', inputs(902))
        candidate = resumed
        for bar in range(2, 62):
            _, candidate = advance(candidate.state, bar * 900, end=bar * 900, close='100')
            data = candidate.state.to_dict()
            self.assertEqual(data['engine']['ema']['count'], bar)
            self.assertEqual(data['positions'], [])
            self.assertFalse(any(event['kind'] == 'evaluation' for event in candidate.transition['events']))
            if bar < 61:
                self.assertEqual(data['engine']['generation'], 0)
                self.assertTrue(data['engine']['lifecycle']['restart_required'])
                self.assertEqual(candidate.operations, [])
        self.assertEqual(data['engine']['generation'], 1)
        self.assertEqual(data['engine']['cohort']['phase'], 'warming')
        self.assertFalse(data['engine']['lifecycle']['restart_required'])
        self.assertEqual(data['engine']['lifecycle']['search_epoch'], 1)

    def test_restart_budget_failure_preserves_aborted_state_and_random_continuation(self):
        _, candidate = opened('cma_es')
        paused = life.prepare_control(candidate.state, 'pause', inputs(55802))
        resumed = life.prepare_control(paused.state, 'resume', inputs(55803))
        protected = life.prepare_protective(resumed.state, life.ExactObservation(55804, '100'), inputs(55804))
        before = protected.state.to_dict()
        original = inputs(55804, 1)
        deficient = DecisionInputs(original.event_at, original.wall_at, original.monotonic_at,
                                   original.ids[:7], original.names)
        wrong_names = DecisionInputs(original.event_at, original.wall_at, original.monotonic_at,
                                     original.ids, inputs(55804, 0).names)
        observation = life.ExactObservation(55804, '100', 55800, '120')
        expected = life.prepare_decision(protected.state, observation, original)
        for budget in (deficient, wrong_names):
            with self.subTest(budget=budget), self.assertRaises(DecisionInputError):
                life.prepare_decision(protected.state, observation, budget)
            self.assertEqual(protected.state.to_dict(), before)
        self.assertEqual(life.prepare_decision(protected.state, observation, original).transition,
                         expected.transition)

    def test_individual_death_includes_exact_boundary_and_frozen_cash_once(self):
        _, candidate = opened()
        for price, terminal in (('20', True), ('19.999999999999999999', True),
                                ('20.000000000000000001', False)):
            with self.subTest(price=price):
                protected = life.prepare_protective(candidate.state,
                    life.ExactObservation(55802, price), inputs(55802))
                data = protected.state.to_dict()
                self.assertEqual(data['status'], 'running')
                self.assertEqual(sum(row['retired'] for row in data['accounts']), 8 if terminal else 0)
                self.assertEqual(len(data['engine']['members']), 8)
                self.assertEqual(sum(member['terminal'] is not None for member in data['engine']['members']),
                                 8 if terminal else 0)
                if terminal:
                    self.assertEqual(len(data['engine']['cohort']['evaluations']), 8)
                    self.assertTrue(all(not row['cohort_complete'] for row in data['engine']['cohort']['evaluations']))
                    self.assertEqual(len([op for op in protected.operations if op['kind'] == 'retire']), 8)
                    again = life.prepare_protective(protected.state,
                        life.ExactObservation(55803, '100'), inputs(55803))
                    self.assertEqual(again.operations, [])
                    self.assertEqual(again.state.to_dict()['reserve'], data['reserve'])
                    self.assertEqual(again.state.to_dict()['engine']['cohort']['evaluations'],
                                     data['engine']['cohort']['evaluations'])

    def test_all_four_all_dead_cohorts_wait_for_deadline_then_tell_complete_order_once(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                _, candidate = opened(algorithm)
                ids = [row['id'] for row in candidate.state.to_dict()['engine']['members']]
                dead = life.prepare_protective(candidate.state, life.ExactObservation(55802, '20'), inputs(55802))
                frozen = dead.state.to_dict()['engine']['cohort']['evaluations']
                self.assertEqual(dead.state.to_dict()['reserve'], '840')
                candidate = dead
                for bar in (63, 64):
                    _, candidate = advance(candidate.state, bar * 900, end=bar * 900, close='120')
                    self.assertEqual(candidate.state.to_dict()['engine']['generation'], 0)
                    self.assertEqual(candidate.state.to_dict()['engine']['cohort']['evaluations'], frozen)
                    self.assertEqual(candidate.operations, [])
                _, final = advance(candidate.state, 65 * 900, end=65 * 900, close='120')
                data = final.state.to_dict()
                self.assertEqual(data['engine']['generation'], 1)
                results = data['engine']['last_evaluation']['cohort']['evaluations']
                self.assertEqual([row['probe_id'] for row in results], ids)
                self.assertTrue(all(row['cohort_complete'] and row['status'] == 'completed' for row in results))
                self.assertEqual([row['fitness'] for row in results], [row['fitness'] for row in frozen])
                self.assertEqual(sum(event['kind'] == 'evaluation' for event in final.transition['events']), 1)
                self.assertFalse(any(op['kind'] == 'retire' for op in final.operations))
                self.assertEqual(sum(op['kind'] == 'birth' for op in final.operations), 8)
                self.assertEqual(data['reserve'], '40')
                self.assertEqual(cash_total(data), 840 * 10**CASH_SCALE)

    def test_partial_terminal_result_stays_frozen_and_survivors_retire_only_at_deadline(self):
        _, candidate = initial()
        for bar in range(1, 63):
            _, candidate = advance(candidate.state, bar * 900, end=bar * 900,
                close='100' if bar < 61 else '80' if bar == 61 else '110')
        _, candidate = advance(candidate.state, 55801)
        count = len(live_positions(candidate.state.to_dict()))
        self.assertGreater(count, 0)
        self.assertLess(count, 8)
        protected = life.prepare_protective(candidate.state, life.ExactObservation(55802, '20'), inputs(55802))
        data = protected.state.to_dict()
        frozen = data['engine']['cohort']['evaluations']
        self.assertEqual(len(frozen), count)
        self.assertEqual(sum(row['retired'] for row in data['accounts']), count)
        self.assertTrue(all(row['roi']['float64'] == float(-.2).hex() for row in frozen))
        candidate = protected
        for bar in (63, 64, 65):
            _, candidate = advance(candidate.state, bar * 900, end=bar * 900, close='110')
        final = candidate.state.to_dict()
        results = final['engine']['last_evaluation']['cohort']['evaluations']
        self.assertEqual(len(results), 8)
        by_id = {row['probe_id']: row for row in results}
        for row in frozen:
            self.assertEqual({key: value for key, value in row.items() if key != 'cohort_complete'},
                             {key: value for key, value in by_id[row['probe_id']].items()
                              if key != 'cohort_complete'})
        self.assertEqual(sum(op['kind'] == 'retire' for op in candidate.operations), 8 - count)
        self.assertEqual(cash_total(final), (1000 - 20 * count) * 10**CASH_SCALE)

    def test_all_dead_halt_cannot_recover_or_refill_after_rebound(self):
        _, candidate = opened(loss='1000')
        dead = life.prepare_protective(candidate.state, life.ExactObservation(55802, '20'), inputs(55802))
        data = dead.state.to_dict()
        self.assertEqual(data['status'], 'risk_halted')
        rebound = life.prepare_protective(dead.state, life.ExactObservation(55803, '1000'), inputs(55803))
        self.assertEqual(rebound.state.to_dict()['reserve'], '840')
        with self.assertRaises(ValueError):
            life.prepare_control(rebound.state, 'recover', inputs(55803),
                life.ExactObservation(55803, '1000', 55800, '120'),
                trip_id=data['engine']['lifecycle']['risk']['trip_id'])
        _, quiet = advance(rebound.state, 58500)
        self.assertEqual(quiet.state.to_dict()['engine']['generation'], 0)
        self.assertEqual(quiet.operations, [])

    def test_failed_restart_funding_preserves_accepted_protection_and_solver(self):
        _, candidate = opened(initial_cash='800')
        paused = life.prepare_control(candidate.state, 'pause', inputs(55802))
        resumed = life.prepare_control(paused.state, 'resume', inputs(55803))
        protected = life.prepare_protective(resumed.state, life.ExactObservation(55804, '97'), inputs(55804))
        before = protected.state.to_dict()
        self.assertEqual(len(live_positions(before)), 0)
        self.assertEqual(cash_total(before), 794 * 10**CASH_SCALE)
        for _ in range(2):
            with self.assertRaises(ValueError):
                life.prepare_decision(protected.state,
                    life.ExactObservation(55804, '97', 55800, '120'), inputs(55804, 1))
            self.assertEqual(protected.state.to_dict(), before)
        self.assertEqual(sum(not row['retired'] for row in before['accounts']), 8)

    def test_failed_preparation_allocations_and_payload_preserve_entire_source(self):
        _, signal = ready_signal()
        at = 55801
        protected = life.prepare_protective(signal.state, life.ExactObservation(at, '100'), inputs(at))
        before = protected.state.to_dict()
        with self.assertRaises(DecisionInputError):
            life.prepare_decision(protected.state, life.ExactObservation(at, '100'), inputs(at, identities=False))
        with patch('vonneumann.core.exact_rehearsal.MAX_PAYLOAD_BYTES', 1024):
            with self.assertRaises(ValueError):
                life.prepare_decision(protected.state, life.ExactObservation(at, '100'), inputs(at, 1))
        self.assertEqual(protected.state.to_dict(), before)
        accepted = life.prepare_decision(protected.state, life.ExactObservation(at, '100'), inputs(at, 1))
        self.assertEqual(sum(op['kind'] == 'open' for op in accepted.operations), 8)
        accepted.transition['after']['engine']['members'].clear()
        self.assertEqual(len(accepted.state.to_dict()['engine']['members']), 8)

    def test_entry_cost_trip_blocks_later_fills_and_discards_remaining_entries(self):
        _, signal = ready_signal(loss='1', execution=DecimalExecutionConfig('100'))
        _, result = advance(signal.state, 55801)
        data = result.state.to_dict()
        self.assertEqual(data['status'], 'risk_halted')
        self.assertEqual(sum(op['kind'] == 'open' for op in result.operations), 1)
        self.assertTrue(all(member['pending'] is None for member in data['engine']['members']))
        self.assertEqual(data['engine']['cohort']['phase'], 'aborted')
        self.assertEqual(data['engine']['generation'], 0)

    def test_deadline_exit_cost_trip_aborts_before_optimizer_selection(self):
        _, candidate = opened(loss='10', execution=DecimalExecutionConfig('35'))
        self.assertEqual(candidate.state.to_dict()['status'], 'running')
        for bar in (63, 64, 65):
            _, candidate = advance(candidate.state, bar * 900, end=bar * 900, close='120')
        data = candidate.state.to_dict()
        self.assertEqual(data['status'], 'risk_halted')
        self.assertEqual(data['engine']['generation'], 0)
        self.assertEqual(data['engine']['cohort']['phase'], 'aborted')
        self.assertEqual(live_positions(data), [])
        self.assertEqual(sum(op['kind'] == 'close' for op in candidate.operations), 8)
        self.assertFalse(any(op['kind'] in {'retire', 'birth', 'distribution'} for op in candidate.operations))
        self.assertFalse(any(event['kind'] == 'evaluation' for event in candidate.transition['events']))
        self.assertIsNone(data['engine']['last_evaluation']['selection'])

    def test_generation_capacity_does_not_disable_protection_or_stop(self):
        _, candidate = initial()
        for bar in range(1, 74):
            _, candidate = advance(candidate.state, bar * 900, end=bar * 900, close='100')
        before = candidate.state.to_dict()
        self.assertEqual(before['engine']['generation'], 3)
        protected = life.prepare_protective(candidate.state,
            life.ExactObservation(65701, '100'), inputs(65701))
        stopped = life.prepare_control(protected.state, 'stop', inputs(65702))
        self.assertEqual(stopped.state.to_dict()['status'], 'stopped')
        self.assertEqual(stopped.state.to_dict()['accounts'], before['accounts'])
        self.assertEqual(candidate.state.to_dict(), before)


if __name__ == '__main__':
    unittest.main()
