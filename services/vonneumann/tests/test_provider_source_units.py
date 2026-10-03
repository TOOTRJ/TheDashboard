"""Small adversarial checks independent of the end-to-end provider traces."""
from copy import deepcopy
from unittest import TestCase
from tests.security_support import OfflineTestMixin
from tests.test_provider_contract import (source, raw_capture, state_source, WALL, MONO,
                                          EPOCH, source_inputs, seed_bundle, OWNER, RUN, kernel)


class ProviderSourceBoundaryTests(OfflineTestMixin, TestCase):
    def test_clock_domain_and_negative_zero_are_numeric_not_monetary(self):
        for value in (True, False, "1", float('nan'), float('inf'), -1, 10**11):
            with self.subTest(value=type(value).__name__), self.assertRaises(source.ProviderSourceError):
                source.clock_us(value)
        self.assertEqual(source.clock_us(10**10), 10**16)
        self.assertEqual(source.clock_us(-0.0), 0)

    def test_policy_epoch_requires_exact_canonical_uuid_and_detached_policy(self):
        for epoch in ('unbound', EPOCH.upper().replace('a', 'A') + ' ', 1, None):
            with self.subTest(epoch=type(epoch).__name__), self.assertRaises(source.ProviderSourceError):
                source.source_policy(epoch)
        policy = source.source_policy(EPOCH)
        policy['max_source_age_us'] = 0
        self.assertEqual(source.source_policy(EPOCH)['max_source_age_us'], 30_000_000)

    def test_safe_failure_never_echoes_caller_message(self):
        error = source.ProviderSourceError('secret-request-or-payload')
        self.assertNotIn('secret', str(error))

    def test_quote_wire_rejects_unknown_keys_and_noncanonical_amounts(self):
        original = source.quote_wire(raw_capture())
        for price in (1.0, True, '100.0', '1e2', '-0', '0', '0.0000000000000000001'):
            quote = deepcopy(original); quote['price'] = price
            with self.subTest(price=price), self.assertRaises(source.ProviderSourceError):
                source.validate_quote_wire(quote)
        quote = deepcopy(original); quote['document']['authorization'] = 'private'
        with self.assertRaises(source.ProviderSourceError):
            source.validate_quote_wire(quote)

    def test_frame_sequence_bool_and_clock_regression_are_not_deferred(self):
        frame = source.make_frame(raw_capture(), prior_source=state_source(), epoch=EPOCH,
                                  wall_now=WALL, monotonic_now=MONO)
        frame['sequence'] = True
        with self.assertRaises(source.ProviderSourceError):
            source.check_frame(frame, wall_us=WALL*1_000_000, monotonic_us=int(MONO*1_000_000))

    def test_new_provider_frame_carries_conservative_age_across_unequal_clocks(self):
        first = source.make_frame(raw_capture(age_floor=20.0), prior_source=state_source(), epoch=EPOCH,
                                  wall_now=WALL, monotonic_now=MONO)
        capture = raw_capture(block=101, source_second=WALL-2, wall=WALL, mono=MONO+1)
        following = source.make_frame(capture, prior_source=state_source(first), epoch=EPOCH,
                                       wall_now=WALL+1, monotonic_now=MONO+2)
        self.assertEqual(following['quote']['source_age_floor_us'],22_000_000)
        following['quote']['source_age_floor_us'] = 0
        with self.assertRaises(source.ProviderSourceError):
            source.validate_frame(following, prior_source=state_source(first), epoch=EPOCH)

    def test_prequote_control_preserves_verified_seed_under_local_projection(self):
        from vonneumann.core import provider_lifecycle as life
        from vonneumann.db import provider_protocol
        config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig('genetic_algorithm', OWNER, RUN,
                                               'SOL/USD'), EPOCH)
        start = life.bootstrap(config, seed_bundle(), source_inputs(WALL))
        paused = life.prepare_control(start.state, 'pause', source_inputs(WALL+1, mono=MONO+1))
        self.assertEqual(paused.state.to_dict()['engine']['ema']['count'], 61)
        self.assertIsNone(paused.state.to_dict()['engine']['last_quote'])
        projected = provider_protocol.model_transition(paused.transition)
        self.assertEqual(projected['before']['engine']['ema']['count'], 0)
        self.assertEqual(projected['after']['engine']['ema']['count'], 0)
        altered = paused.transition
        altered['after']['engine']['ema']['values']['60'] = '0x1.0p+0'
        with self.assertRaises(ValueError):
            provider_protocol.validate_transition(altered, paused.operations, OWNER, RUN, 2)

    def test_nonmarket_control_cannot_regress_accepted_quote_monotonic_clock(self):
        from vonneumann.core import provider_lifecycle as life
        config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig('genetic_algorithm', OWNER, RUN,
                                               'SOL/USD'), EPOCH)
        start = life.bootstrap(config, seed_bundle(), source_inputs(WALL))
        frame = source.make_frame(raw_capture(), prior_source=start.state.to_dict()['source'], epoch=EPOCH,
                                  wall_now=WALL+1, monotonic_now=MONO+1)
        protected = life.prepare_protective(start.state, frame, source_inputs(WALL+1, mono=MONO+1))
        with self.assertRaises(ValueError):
            life.prepare_control(protected.state, 'pause', source_inputs(WALL+1, mono=MONO+0.5))
