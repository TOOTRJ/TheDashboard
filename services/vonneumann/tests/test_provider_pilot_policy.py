"""Offline acceptance for the separate local v5 paper-pilot admission policy."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import math
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network
from tests.test_provider_contract import (
    ALGORITHMS, END, EPOCH, MONO, OWNER, RUN, WALL,
    kernel, life, raw_capture, raw_minutes, seed_bundle, source, source_inputs,
)

with deny_network():
    from vonneumann.core import exact_rehearsal as base
    from vonneumann.core.decision_inputs import DecisionInputs
    from vonneumann.core.provider_pilot import (
        PilotCapacityError, ProviderPilotLimits, decision_required, stop_capacity_bytes,
    )


def bootstrap(algorithm='genetic_algorithm', *, loss_bps='3000', name=None):
    config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig(
        algorithm, OWNER, RUN, asset='SOL/USD', account_loss_bps=loss_bps), EPOCH)
    inputs = source_inputs(WALL)
    if name is not None:
        inputs = replace(inputs, names=tuple((0, name) for _ in range(8)))
    return life.bootstrap(config, seed_bundle(last_close='80'), inputs)


def tick(candidate, offset, serial, *, close=None, price='100'):
    wall, mono = WALL + offset, MONO + offset
    generation = candidate.state.to_dict()['engine']['generation']
    frame = source.make_frame(raw_capture(price=price, block=100 + serial,
        source_second=wall - 2, wall=wall - 1, mono=mono - 1),
        prior_source=candidate.state.to_dict()['source'], epoch=EPOCH,
        wall_now=wall, monotonic_now=mono)
    protected = life.prepare_protective(candidate.state, frame,
        source_inputs(wall, mono=mono, generation=generation + 1, serial=serial * 2))
    history = None
    if close is not None:
        history = source.build_history(raw_minutes(
            end=END + offset // 900 * 900, count=15, close=close,
            wall=wall - 1, mono=mono - 1),
            prior_bars=protected.state.to_dict()['source']['bars'], seed=False,
            wall_us=wall * 1_000_000, monotonic_us=int(mono * 1_000_000))
    decided = life.prepare_decision(protected.state, frame, history,
        source_inputs(wall, mono=mono, generation=generation + 1, serial=serial * 2 + 1))
    return protected, decided


def selector_state(state, mutate):
    """Use a detached test-only fork to cover internal selector branches.

    Production callers have no public JSON restore/import interface. Economic
    acceptance below uses real preparations rather than these branch fixtures.
    """
    data, strategy, cohort = state._fork()
    mutate(data)
    return base.ExactState._seal(data, strategy, cohort)


class ProviderPilotLimitsTests(OfflineTestMixin, unittest.TestCase):
    def test_defaults_and_fixed_bounds_do_not_change_v5_configuration(self):
        limits = ProviderPilotLimits()
        self.assertEqual((limits.max_quotes, limits.max_commands), (3601, 4000))
        self.assertEqual((limits.MAX_ELAPSED_QUOTE_SECONDS, limits.MAX_GENERATION,
            limits.MAX_SEARCH_EPOCH, limits.MAX_IDS, limits.MAX_NAMES), (3600, 1, 0, 9, 8))
        config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig(
            'genetic_algorithm', OWNER, RUN, asset='SOL/USD'), EPOCH)
        self.assertEqual(config.run_configuration()['durability_contract_version'], 5)
        self.assertEqual(base.MAX_GENERATIONS, 3)
        self.assertEqual(base.MAX_PAYLOAD_BYTES, 262144)

    def test_exact_integer_boundaries(self):
        for quotes in (1, 3601):
            for commands in (4, 4000):
                with self.subTest(quotes=quotes, commands=commands):
                    limits = ProviderPilotLimits(quotes, commands)
                    limits.__post_init__()
        for quotes in (True, False, 0, 3602, 1.0, '1', None):
            with self.subTest(quotes=quotes), self.assertRaises(PilotCapacityError):
                ProviderPilotLimits(max_quotes=quotes)
        for commands in (True, False, 3, 4001, 4.0, '4', None):
            with self.subTest(commands=commands), self.assertRaises(PilotCapacityError):
                ProviderPilotLimits(max_commands=commands)

    def test_frozen_limits_revalidate_setter_bypass(self):
        limits = ProviderPilotLimits()
        with self.assertRaises(FrozenInstanceError):
            limits.max_quotes = 1
        object.__setattr__(limits, 'max_commands', 4096)
        with self.assertRaises(PilotCapacityError):
            limits.__post_init__()


class ProviderPilotStopCapacityTests(OfflineTestMixin, unittest.TestCase):
    def assert_pure_stop_bound(self, state):
        before = state.to_dict()
        bound = stop_capacity_bytes(state)
        self.assertEqual(stop_capacity_bytes(state), bound)
        self.assertEqual(state.to_dict(), before)
        self.assertLessEqual(bound, base.MAX_PAYLOAD_BYTES)
        witness_inputs = DecisionInputs(
            datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=10**10),
            datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=10**16),
            float(10**10), (), ())
        witness = life.prepare_control(state, 'stop', witness_inputs)
        self.assertEqual(bound, max(witness.payload_bytes, len(witness._wire)) + 9)
        self.assertEqual(witness.state.to_dict()['status'], 'stopped')
        self.assertEqual(witness.state.to_dict()['source'], before['source'])
        self.assertEqual(witness.state.to_dict()['positions'], before['positions'])
        # Compare an actual nonfuture control with a fractional wall reading.
        event = datetime.fromtimestamp(WALL + 4000, timezone.utc)
        actual_inputs = DecisionInputs(event, event + timedelta(microseconds=999999),
                                      MONO + 4000.999999, (), ())
        actual = life.prepare_control(state, 'stop', actual_inputs)
        self.assertLessEqual(actual.payload_bytes, bound)
        self.assertLessEqual(len(actual._wire), bound)
        self.assertEqual(state.to_dict(), before)

    def test_real_all_solver_states_reserve_complete_stop_without_advancing_rng(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                candidate = bootstrap(algorithm)
                self.assert_pure_stop_bound(candidate.state)
                for serial, (offset, close) in enumerate(((1, None), (900, '120'),
                        (901, None), (1800, '80'), (1801, None),
                        (2700, '80'), (2701, None), (3601, '80')), 1):
                    original = candidate
                    protected, decided = tick(original, offset, serial, close=close)
                    self.assert_pure_stop_bound(protected.state)
                    self.assert_pure_stop_bound(decided.state)
                    # Preparing the same next transition after the witnesses
                    # must reproduce all solver, RNG, cohort, and ledger bytes.
                    repeated_protect, repeated_decide = tick(original, offset, serial, close=close)
                    self.assertEqual(repeated_protect._wire, protected._wire)
                    self.assertEqual(repeated_decide._wire, decided._wire)
                    candidate = decided
                self.assertEqual(candidate.state.to_dict()['engine']['generation'], 1)

    def test_real_paused_and_risk_halted_states_can_reserve_stop(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                candidate = bootstrap(algorithm)
                paused = life.prepare_control(candidate.state, 'pause', source_inputs(WALL + 1))
                self.assert_pure_stop_bound(paused.state)
                candidate = bootstrap(algorithm, loss_bps='1')
                _, candidate = tick(candidate, 1, 1)
                _, candidate = tick(candidate, 900, 2, close='120')
                _, candidate = tick(candidate, 901, 3)
                _, candidate = tick(candidate, 902, 4, price='95')
                self.assertEqual(candidate.state.to_dict()['status'], 'risk_halted')
                self.assert_pure_stop_bound(candidate.state)

    def test_legal_unicode_names_reserve_both_encodings_for_all_solvers(self):
        # Exactly 128 UTF-8 bytes, permitted by DecisionInputs. Each non-BMP
        # character needs a surrogate pair in the existing ASCII wire.
        name = '\U0001f642' * 32
        self.assertEqual(len(name.encode('utf-8')), 128)
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                candidate = bootstrap(algorithm, name=name)
                _, candidate = tick(candidate, 1, 1)
                self.assertTrue(all(member['name'] == name for member
                    in candidate.state.to_dict()['engine']['members']))
                self.assert_pure_stop_bound(candidate.state)
                event = datetime.fromtimestamp(WALL + 4000, timezone.utc)
                actual = life.prepare_control(candidate.state, 'stop', DecisionInputs(
                    event, event + timedelta(microseconds=999999), MONO + 4000.999999, (), ()))
                self.assertIn(b'\\ud83d\\ude42', actual._wire)
                bound = stop_capacity_bytes(candidate.state)
                self.assertLessEqual(actual.payload_bytes, bound)
                self.assertLessEqual(len(actual._wire), bound)

    def test_clock_width_reservation_covers_fractional_wall_and_subnormal_hex(self):
        state = bootstrap().state  # No prior quote requires a minimum monotonic reading.
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        event = epoch + timedelta(seconds=10**10 - 1)
        wall = event + timedelta(microseconds=999999)
        tiny = math.nextafter(0.0, 1.0)
        actual = life.prepare_control(state, 'stop', DecisionInputs(event, wall, tiny, (), ()))
        self.assertLessEqual(actual.payload_bytes, stop_capacity_bytes(state))
        self.assertLessEqual(len(actual._wire), stop_capacity_bytes(state))
        self.assertEqual(len(wall.isoformat()) - len(event.isoformat()), 7)
        self.assertEqual(len(tiny.hex()) - len(float(10**10).hex()), 2)

    def test_payload_boundary_is_inclusive_after_reserve(self):
        state = bootstrap().state
        class Witness:
            payload_bytes = base.MAX_PAYLOAD_BYTES - 9
            _wire = b'x' * (base.MAX_PAYLOAD_BYTES - 9)
        with patch.object(life, 'prepare_control', return_value=Witness()) as prepare:
            self.assertEqual(stop_capacity_bytes(state), base.MAX_PAYLOAD_BYTES)
            prepare.assert_called_once()
            inputs = prepare.call_args.args[2]
            self.assertEqual((inputs.ids, inputs.names), ((), ()))
            self.assertEqual(inputs.event_at.timestamp(), 10**10)
            self.assertEqual(inputs.monotonic_at, float(10**10))
        Witness.payload_bytes += 1
        with patch.object(life, 'prepare_control', return_value=Witness()), self.assertRaises(PilotCapacityError):
            stop_capacity_bytes(state)
        Witness.payload_bytes -= 1
        Witness._wire += b'x'
        with patch.object(life, 'prepare_control', return_value=Witness()), self.assertRaises(PilotCapacityError):
            stop_capacity_bytes(state)

    def test_terminal_and_nonowned_states_reject_without_preparation(self):
        state = bootstrap().state
        stopped = life.prepare_control(state, 'stop', source_inputs(WALL + 1)).state
        for invalid in (None, state.to_dict(), stopped):
            with self.subTest(type=type(invalid)), patch.object(life, 'prepare_control') as prepare:
                with self.assertRaises(PilotCapacityError):
                    stop_capacity_bytes(invalid)
                prepare.assert_not_called()
        with patch.object(life, 'prepare_control', side_effect=base.ExactRehearsalError('cap')):
            with self.assertRaises(PilotCapacityError):
                stop_capacity_bytes(state)


class ProviderPilotDecisionSelectorTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.boot = bootstrap()
        _, self.started = tick(self.boot, 1, 1)

    def test_warming_current_history_starts_evaluation_but_plain_ticks_skip(self):
        self.assertTrue(decision_required(self.boot.state, WALL))
        self.assertFalse(decision_required(self.started.state, WALL + 2))
        unchanged = self.started.state.to_dict()
        self.assertFalse(decision_required(self.started.state, WALL + 3))
        self.assertEqual(self.started.state.to_dict(), unchanged)

    def test_completed_boundary_and_due_window_require_decision(self):
        state = self.started.state
        self.assertFalse(decision_required(state, END + 899))
        self.assertFalse(decision_required(state, END + 900))
        self.assertFalse(decision_required(state, END + 904))
        self.assertTrue(decision_required(state, END + 905))
        # Retain current provider history so the due-cohort branch is tested
        # independently of a missing candle boundary.
        due = WALL + 3601
        state = selector_state(state, lambda data:
            data['source']['bars'][-1].__setitem__(0, due // 900 * 900))
        self.assertFalse(decision_required(state, due - 1))
        self.assertTrue(decision_required(state, due))

    def test_pending_after_signal_requires_consumption_even_when_expired_or_mismatched(self):
        def pending(data):
            data['engine']['members'][0]['pending'] = {
                'action': 'entry', 'signal_at': WALL + 2, 'position_id': None}
        state = selector_state(self.started.state, pending)
        self.assertFalse(decision_required(state, WALL + 2))
        self.assertTrue(decision_required(state, WALL + 3))
        # No new completed boundary hides the expired-pending branch.
        expired = WALL + 1000
        state = selector_state(state, lambda data:
            data['source']['bars'][-1].__setitem__(0, expired // 900 * 900))
        self.assertTrue(decision_required(state, expired))
        state = selector_state(state, lambda data: data['engine']['members'][0]['pending'].update(
            action='exit', position_id='00000000-0000-0000-0000-000000000099'))
        self.assertTrue(decision_required(state, expired))

    def test_terminal_members_pending_does_not_trigger_decision(self):
        def terminal(data):
            member = data['engine']['members'][0]
            member['pending'] = {'action': 'entry', 'signal_at': WALL + 1, 'position_id': None}
            member['terminal'] = {'reason': 'drawdown', 'at': WALL + 1, 'cash': '100'}
        state = selector_state(self.started.state, terminal)
        self.assertFalse(decision_required(state, WALL + 2))

    def test_halted_only_selects_retained_exits_and_ignores_history_restart_due(self):
        def halt(data):
            data['status'] = 'risk_halted'
            data['engine']['lifecycle']['risk']['active'] = True
            data['engine']['lifecycle']['restart_required'] = True
        state = selector_state(self.started.state, halt)
        self.assertFalse(decision_required(state, WALL + 3601))
        state = selector_state(state, lambda data: data['engine']['members'][0].update(
            pending={'action': 'entry', 'signal_at': WALL + 1, 'position_id': None}))
        self.assertFalse(decision_required(state, WALL + 3601))
        state = selector_state(state, lambda data:
            data['engine']['members'][0]['pending'].update(action='exit'))
        self.assertTrue(decision_required(state, WALL + 3601))

    def test_paused_stopped_and_consumed_timestamps_never_select(self):
        paused = life.prepare_control(self.started.state, 'pause',
                                      source_inputs(WALL + 2, mono=MONO + 2)).state
        stopped = life.prepare_control(paused, 'stop',
                                       source_inputs(WALL + 3, mono=MONO + 3)).state
        for state in (paused, stopped):
            self.assertFalse(decision_required(state, WALL + 3601))
        self.assertFalse(decision_required(self.started.state, WALL + 1))
        self.assertFalse(decision_required(self.started.state, WALL))

    def test_restart_conservatively_selects_with_current_history(self):
        state = selector_state(self.started.state, lambda data:
            data['engine']['lifecycle'].update(restart_required=True))
        self.assertTrue(decision_required(state, WALL + 2))

    def test_invalid_timestamps_and_nonprovider_state_reject(self):
        for stamp in (True, False, -1, 10**10 + 1, 1.0, '1', None):
            with self.subTest(stamp=stamp), self.assertRaises(PilotCapacityError):
                decision_required(self.started.state, stamp)
        plain = kernel.bootstrap(kernel.ExactLifecycleConfig('genetic_algorithm', OWNER, RUN),
                                 source_inputs(WALL)).state
        for invalid in (None, self.started.state.to_dict(), plain):
            with self.subTest(type=type(invalid)), self.assertRaises(PilotCapacityError):
                decision_required(invalid, WALL)


if __name__ == '__main__':
    unittest.main()
