"""Synthetic clock/model boundaries only; no sleep, SQL, Docker or provider I/O."""
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network
from tests.restoration_fixture_clock import (
    planned_wait_us, validate_observed_slot, MAX_CLOCK_US, SETUP_TIMEOUT_SECONDS,
)

with deny_network():
    from tests.test_provider_contract import OWNER, RUN, EPOCH, MONO, raw_capture, raw_minutes, source_inputs
    from vonneumann.research import provider_portable_ga_model as ga
    from tests.postgres import harness


class RestorationFixtureClockTests(OfflineTestMixin, unittest.TestCase):
    def test_one_planned_wait_is_bounded_and_selects_phase_six_through_850(self):
        base = 1_800_000_000 * 1_000_000
        self.assertEqual(base % 900_000_000, 0)
        for phase, expected in ((0, 6_000_000), (5_999_999, 1), (6_000_000, 0),
                                (850_000_000, 0), (850_000_001, 55_999_999),
                                (899_999_999, 6_000_001)):
            with self.subTest(phase=phase):
                delay = planned_wait_us(base + phase)
                self.assertEqual(delay, expected)
                self.assertLessEqual(delay, 56_000_000)
                accepted = validate_observed_slot(base + phase, base + phase + delay)
                self.assertGreaterEqual(accepted, 6_000_000)
                self.assertLessEqual(accepted, 850_000_000)

    def test_setup_timeout_fits_actual_harness_without_starting_a_session(self):
        # Exercise the real timeout guard and command construction, replacing
        # only the process-owning session so no SQL or Docker can be started.
        db = object.__new__(harness.IsolatedPostgres)
        db._container_id = 'f' * 64
        db._docker = ['fixture-docker']
        db._env = {}
        db._sessions = []
        with patch.object(harness, 'SqlSession') as session:
            actual = db.begin_sql('SELECT 1;', timeout=SETUP_TIMEOUT_SECONDS)
            self.assertIs(actual, session.return_value)
            session.assert_called_once()
            command, source, env, timeout = session.call_args.args
            self.assertEqual(timeout, 60)
            self.assertEqual(source, 'SELECT 1;')
            self.assertEqual(env, {})
            self.assertIn('PGOPTIONS=-c statement_timeout=59000', command)
        with patch.object(harness, 'SqlSession') as session:
            with self.assertRaises(ValueError):
                db.begin_sql('SELECT 1;', timeout=61)
            session.assert_not_called()

    def test_clock_types_and_unbounded_values_are_not_coerced(self):
        for value in (True, False, 1.0, '1', None, -1, MAX_CLOCK_US + 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                planned_wait_us(value)
            with self.subTest(after=value), self.assertRaises(ValueError):
                validate_observed_slot(6_000_000, value)

    def test_post_wait_backward_incomplete_and_overshot_observations_refuse_without_replanning(self):
        for before, after in ((0, 5_999_999), (10_000_000, 9_999_999),
                              (849_000_000, 850_000_001), (0, 61_000_000),
                              (899_000_000, 905_999_999)):
            with self.subTest(before=before, after=after), self.assertRaises(ValueError):
                validate_observed_slot(before, after)
        self.assertEqual(validate_observed_slot(899_000_000, 906_000_001), 6_000_001)

    def interrupted(self, seed_second):
        end = (seed_second - 5) // 900 * 900
        history = ga.source.build_history(raw_minutes(end=end, count=61 * 15, close='80',
            wall=seed_second, mono=MONO), prior_bars=[], seed=True,
            wall_us=seed_second * 1_000_000, monotonic_us=int(MONO * 1_000_000))
        ledger = ga.SimulationLedger(OWNER, RUN)
        original = ga.bootstrap(ga.GAConfig('genetic_algorithm', OWNER, RUN,
            asset='SOL/USD', source_epoch=EPOCH), history, source_inputs(seed_second), ledger=ledger)
        state = ledger.accept(original)
        for offset, action in ((1, 'pause'), (2, 'resume')):
            candidate = ga.prepare_control(state, action,
                source_inputs(seed_second + offset, mono=MONO + offset, serial=59 + offset), ledger=ledger)
            state = ledger.accept(candidate)
        data = state.to_dict()
        self.assertTrue(data['engine']['lifecycle']['restart_required'])
        self.assertFalse(data['engine']['lifecycle']['risk']['active'])
        self.assertEqual(data['engine']['cohort']['phase'], 'aborted')
        self.assertEqual(data['engine']['ema']['count'], 61)
        return state, ledger, original, end

    def original_pair(self, state, ledger, seed_second, at):
        # Fixed synthetic timestamps/monotonic relation, not observed real clocks.
        mono = MONO + at - seed_second
        frame = ga.source.make_frame(raw_capture(price='100', block=900,
            source_second=at - 2, wall=at, mono=mono), prior_source=state.to_dict()['source'],
            epoch=EPOCH, wall_now=at, monotonic_now=mono)
        protective = ga.prepare_protective(state, frame, source_inputs(at, mono=mono, serial=70), ledger=ledger)
        state = ledger.accept(protective)
        decision = ga.prepare_decision(state, frame, None,
            source_inputs(at, mono=mono, generation=1, serial=71), ledger=ledger)
        self.assertEqual(decision.transition['evidence']['inputs']['provider']['frame'],
                         protective.transition['evidence']['inputs']['provider']['frame'])
        self.assertIsNone(decision.transition['evidence']['inputs']['provider']['history'])
        accepted = ledger.accept(decision)
        self.assertEqual(accepted.to_dict(), decision.state.to_dict())
        return decision

    def test_exact_last_eligible_second_restarts_and_retires_all_eight_originals(self):
        end = 1_800_000_000; seed = end + 10
        state, ledger, original, observed_end = self.interrupted(seed)
        self.assertEqual(observed_end, end)
        decision = self.original_pair(state, ledger, seed, end + 900)
        old_ids = {account['id'] for account in original.state.to_dict()['accounts']}
        retired = [op['id'] for op in decision.operations if op['kind'] == 'retire']
        born = [op['id'] for op in decision.operations if op['kind'] == 'birth']
        self.assertEqual(len(retired), 8); self.assertEqual(set(retired), old_ids)
        self.assertEqual(len(born), 8); self.assertEqual(len(set(born)), 8)
        self.assertTrue(old_ids.isdisjoint(born))
        data = decision.state.to_dict()
        self.assertEqual({account['id'] for account in data['accounts']}, set(born))
        self.assertEqual(data['engine']['generation'], 1)
        self.assertFalse(data['engine']['lifecycle']['restart_required'])
        self.assertTrue(all(ledger.used(identity) for identity in old_ids))

    def test_first_stale_second_defers_restart_and_retains_original_accounts(self):
        end = 1_800_000_000; seed = end + 10
        state, ledger, original, observed_end = self.interrupted(seed)
        self.assertEqual(observed_end, end)
        decision = self.original_pair(state, ledger, seed, end + 901)
        self.assertEqual(decision.state.to_dict()['accounts'], original.state.to_dict()['accounts'])
        self.assertFalse(any(op['kind'] in {'birth', 'retire'} for op in decision.operations))
        data = decision.state.to_dict()
        self.assertTrue(data['engine']['lifecycle']['restart_required'])
        self.assertEqual(data['engine']['generation'], 0)
        self.assertEqual(data['engine']['cohort']['phase'], 'aborted')
        self.assertFalse(data['engine']['lifecycle']['risk']['active'])

    def test_first_five_seconds_seed_the_older_completed_bar_and_need_fresh_history(self):
        boundary = 1_800_000_000
        for phase in range(5):
            with self.subTest(seed_phase=phase):
                seed = boundary + phase
                state, ledger, original, observed_end = self.interrupted(seed)
                self.assertEqual(observed_end, boundary - 900)
                decision = self.original_pair(state, ledger, seed, seed + 3)
                self.assertEqual(decision.state.to_dict()['accounts'], original.state.to_dict()['accounts'])
                self.assertFalse(any(op['kind'] in {'birth', 'retire'} for op in decision.operations))
                self.assertTrue(decision.state.to_dict()['engine']['lifecycle']['restart_required'])
                self.assertEqual(decision.state.to_dict()['engine']['ema']['last_end'], boundary - 900)


if __name__ == '__main__':
    unittest.main()
