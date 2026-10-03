"""Current-history admission after pauses and delayed warmup delivery."""
from __future__ import annotations

import unittest

from tests.security_support import deny_network
from tests.test_exact_lifecycle import advance, initial, opened
from tests.test_exact_rehearsal import inputs, initial as initial_v3
from vonneumann.core import exact_lifecycle as life


class LifecycleFreshnessTests(unittest.TestCase):
    def setUp(self):
        guard = deny_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)

    def paused_and_resumed(self, resume_at):
        _, current = opened()
        paused = life.prepare_control(current.state, 'pause', inputs(55802))
        resumed = life.prepare_control(paused.state, 'resume', inputs(resume_at))
        return current, resumed

    def test_long_pause_accepts_contiguous_backfill_without_restarting_on_stale_history(self):
        original, resumed = self.paused_and_resumed(58501)
        original_accounts = original.state.to_dict()['accounts']
        original_positions = original.state.to_dict()['positions']
        original_members = original.state.to_dict()['engine']['members']
        _, candidate = advance(resumed.state, 58502)
        self.assertEqual(candidate.operations, [])
        self.assertEqual(candidate.state.to_dict()['engine']['generation'], 0)
        self.assertTrue(candidate.state.to_dict()['engine']['lifecycle']['restart_required'])
        for stamp, end in ((58503, 56700), (58504, 57600)):
            with self.subTest(end=end):
                _, candidate = advance(candidate.state, stamp, end=end, close='100')
                data = candidate.state.to_dict()
                self.assertEqual(candidate.operations, [])
                self.assertEqual(data['engine']['generation'], 0)
                self.assertEqual(data['engine']['cohort']['phase'], 'aborted')
                self.assertEqual(data['engine']['lifecycle']['search_epoch'], 0)
                self.assertEqual(data['engine']['ema']['last_end'], end)
                self.assertEqual(data['accounts'], original_accounts)
                self.assertEqual(data['positions'], original_positions)
                self.assertEqual([m['id'] for m in data['engine']['members']],
                                 [m['id'] for m in original_members])
                self.assertTrue(all(m['pending'] is None for m in data['engine']['members']))
        _, restarted = advance(candidate.state, 58505, end=58500, close='100')
        data = restarted.state.to_dict()
        self.assertEqual(data['engine']['generation'], 1)
        self.assertEqual(data['engine']['lifecycle']['search_epoch'], 1)
        self.assertEqual(data['engine']['cohort']['phase'], 'warming')
        self.assertEqual(sum(op['kind'] == 'birth' for op in restarted.operations), 8)
        self.assertTrue(all(row['closed'] for row in data['positions']))
        self.assertFalse(any(event['kind'] == 'evaluation' for event in restarted.transition['events']))
        self.assertEqual(original.state.to_dict()['accounts'], original_accounts)
        self.assertEqual(original.state.to_dict()['positions'], original_positions)

    def test_fresh_history_deadline_is_inclusive_for_restart(self):
        _, resumed = self.paused_and_resumed(56699)
        # The retained last candle ends at 55800: age900 is permitted, 901 is not.
        for stamp, expected_births in ((56700, 8), (56701, 0)):
            with self.subTest(stamp=stamp):
                _, result = advance(resumed.state, stamp)
                self.assertEqual(sum(op['kind'] == 'birth' for op in result.operations), expected_births)
                self.assertEqual(result.state.to_dict()['engine']['generation'], int(bool(expected_births)))
                self.assertFalse(any(event['kind'] == 'evaluation' for event in result.transition['events']))

    def test_delayed_warmup_requires_current_history_before_common_clock_starts(self):
        _, candidate = initial()
        for bar in range(1, 61):
            _, candidate = advance(candidate.state, bar * 900, end=bar * 900, close='100')
        for stamp, end, close in ((56701, 54900, '80'), (56702, 55800, '120')):
            _, candidate = advance(candidate.state, stamp, end=end, close=close)
            data = candidate.state.to_dict()
            self.assertGreaterEqual(data['engine']['ema']['count'], 61)
            self.assertEqual(data['engine']['cohort']['phase'], 'warming')
            self.assertIsNone(data['engine']['cohort']['started_at'])
            self.assertEqual(data['positions'], [])
            self.assertEqual(candidate.operations, [])
            self.assertTrue(all(member['pending'] is None for member in data['engine']['members']))
        _, ready = advance(candidate.state, 56703, end=56700, close='120')
        cohort = ready.state.to_dict()['engine']['cohort']
        self.assertEqual(cohort['phase'], 'evaluating')
        self.assertEqual(float.fromhex(cohort['started_at']['float64']), 56703)
        self.assertEqual(float.fromhex(cohort['ends_at']['float64']), 60303)
        self.assertEqual(ready.operations, [])
        self.assertTrue(all(member['pending'] is None for member in ready.state.to_dict()['engine']['members']))

    def test_version_three_state_cannot_be_adopted_as_lifecycle_state(self):
        _, candidate = initial_v3()
        before = candidate.state.to_dict()
        with self.assertRaises(life.ExactRehearsalError):
            life.prepare_protective(candidate.state, life.ExactObservation(1, '100'), inputs(1))
        with self.assertRaises(life.ExactRehearsalError):
            life.prepare_control(candidate.state, 'pause', inputs(1))
        self.assertEqual(candidate.state.to_dict(), before)

    def test_completed_old_window_can_replace_but_new_window_waits_for_current_history(self):
        _, candidate = opened()
        for bar in (63, 64):
            _, candidate = advance(candidate.state, bar * 900, end=bar * 900, close='120')
        # The first valid quote after the old deadline closes and scores that
        # complete window, but its last candle is now901seconds old.
        _, replacement = advance(candidate.state, 58501)
        data = replacement.state.to_dict()
        self.assertEqual(data['engine']['generation'], 1)
        self.assertEqual(data['engine']['last_evaluation']['cohort']['phase'], 'completed')
        self.assertEqual(data['engine']['cohort']['phase'], 'warming')
        self.assertIsNone(data['engine']['cohort']['started_at'])
        self.assertEqual(sum(op['kind'] == 'birth' for op in replacement.operations), 8)
        _, waiting = advance(replacement.state, 58502)
        self.assertEqual(waiting.state.to_dict()['engine']['cohort']['phase'], 'warming')
        self.assertEqual(waiting.operations, [])
        _, ready = advance(waiting.state, 58503, end=58500, close='120')
        cohort = ready.state.to_dict()['engine']['cohort']
        self.assertEqual(cohort['phase'], 'evaluating')
        self.assertEqual(float.fromhex(cohort['started_at']['float64']), 58503)
        self.assertEqual(ready.operations, [])


if __name__ == '__main__':
    unittest.main()
