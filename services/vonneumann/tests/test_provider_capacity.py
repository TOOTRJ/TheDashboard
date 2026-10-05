"""Offline capacity acceptance for complete v5 transitions.

Run ``python -m tests.test_provider_capacity --measure`` to reproduce the
measurements. These traces deliberately skip uninteresting intermediate quote
seconds; they measure payload retention, not sustainable polling or latency.
"""
from __future__ import annotations

import json
import hashlib
import sys
import time
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import deny_network
from tests.test_provider_contract import (
    ALGORITHMS, END, EPOCH, MONO, OWNER, RUN, WALL, WORKER,
    kernel, life, raw_capture, raw_minutes, seed_bundle, source, source_inputs,
)
from vonneumann.core import exact_rehearsal as base
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.rehearsal_owner import MAX_OWNED_COMMANDS


def _payload_size(payload):
    return len(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                          allow_nan=False, separators=(', ', ': ')).encode('utf-8'))


def capacity_trace(algorithm, *, dense):
    """Prepare real owned transitions and validate every accepted command.

    Audit the actual serialization before its existing cap rejection; this
    never bypasses admission, changes a cap or installs a rejected candidate.
    Dense candles alternate high/low closes and retain substantially more
    closed positions than the one-entry-per-window fixture.
    """
    started = time.perf_counter()
    result = {'algorithm': algorithm, 'dense': dense, 'maximum_bytes': 0,
              'maximum_operations': 0, 'replacements': [], 'rejection': None}
    serialization = {}
    serialization_hashes = {}
    real_json = base._json

    def audit(value):
        wire = real_json(value)
        if (type(value) is dict and value.get('version') in (4, 5)
                and 'operations' in value and 'transition' in value):
            serialization[value['version']] = _payload_size(value)
            serialization_hashes[value['version']] = hashlib.sha256(wire).hexdigest()
        return wire

    def admit(candidate):
        before = candidate.transition['before']
        command = PreparedCommand.batch(OWNER, RUN, WORKER, 1,
            1 if before is None else before['revision'], candidate.operations,
            command_id=str(UUID(int=31_000_000 + candidate.state.revision)),
            version=5, transition=candidate.transition)
        measured = _payload_size(command.expected_request['payload'])
        if measured != candidate.payload_bytes or measured > base.MAX_PAYLOAD_BYTES:
            raise AssertionError('Candidate and actual command capacity differ')
        result['maximum_bytes'] = max(result['maximum_bytes'], measured)
        result['maximum_operations'] = max(result['maximum_operations'], len(candidate.operations))
        return candidate

    with deny_network(), patch.object(base, '_json', side_effect=audit):
        config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig(
            algorithm, OWNER, RUN, asset='SOL/USD'), EPOCH)
        candidate = admit(life.bootstrap(config, seed_bundle(last_close='80'), source_inputs(WALL)))
        result['bootstrap_bytes'] = candidate.payload_bytes
        # The first cohort starts at +1 and each one-hour replacement occurs
        # at +3601, +7201 and +10801. Each bar has a later independent fill quote.
        offsets = [1] + [offset for bar in range(1, 13)
                         for offset in (bar * 900, bar * 900 + 1)]
        for serial, offset in enumerate(offsets, 1):
            wall, mono = WALL + offset, MONO + offset
            generation = candidate.state.to_dict()['engine']['generation']
            frame = source.make_frame(raw_capture(block=100 + serial,
                source_second=wall - 2, wall=wall - 1, mono=mono - 1),
                prior_source=candidate.state.to_dict()['source'], epoch=EPOCH,
                wall_now=wall, monotonic_now=mono)
            protected = admit(life.prepare_protective(candidate.state, frame,
                source_inputs(wall, mono=mono, generation=generation + 1, serial=serial * 2)))
            history = None
            if offset % 900 == 0:
                bar = offset // 900
                high = bar % 2 == 1 if dense else bar % 4 == 1
                history = source.build_history(raw_minutes(end=END + offset, count=15,
                    close='120' if high else '80', wall=wall - 1, mono=mono - 1),
                    prior_bars=protected.state.to_dict()['source']['bars'], seed=False,
                    wall_us=wall * 1_000_000, monotonic_us=int(mono * 1_000_000))
            previous = protected.state.to_dict()
            serialization.clear()
            serialization_hashes.clear()
            inputs = source_inputs(wall, mono=mono, generation=generation + 1, serial=serial * 2 + 1)
            try:
                prepared = life.prepare_decision(protected.state, frame, history, inputs)
            except base.ExactRehearsalError as error:
                if 'payload capacity' not in str(error):
                    raise AssertionError('Dense trace failed for a reason other than capacity') from error
                if protected.state.to_dict() != previous:
                    raise AssertionError('Rejected capacity preparation changed owned state') from error
                sizes, hashes, message = dict(serialization), dict(serialization_hashes), str(error)
                # Repeating pure preparation from the same seal and inputs
                # must reproduce every optimizer/cohort/economic byte. This
                # catches hidden solver/RNG advancement despite detached data.
                serialization.clear(); serialization_hashes.clear()
                try:
                    life.prepare_decision(protected.state, frame, history, inputs)
                except base.ExactRehearsalError as repeated:
                    if (str(repeated) != message or serialization != sizes
                            or serialization_hashes != hashes
                            or protected.state.to_dict() != previous):
                        raise AssertionError('Rejected capacity preparation is not reproducible') from repeated
                else:
                    raise AssertionError('Repeated oversized preparation unexpectedly succeeded')
                result['rejection'] = {'offset': offset, 'generation': generation,
                    'positions': len(previous['positions']), 'message': message,
                    'serialized_payload_bytes': sizes,
                    'repeated_rejection_preserves_owned_state': True}
                break
            candidate = admit(prepared)
            current = candidate.state.to_dict()
            if current['engine']['generation'] != generation:
                result['replacements'].append({'generation': current['engine']['generation'],
                    'bytes': candidate.payload_bytes, 'operations': len(candidate.operations),
                    'positions': len(current['positions']), 'accounts': len(current['accounts'])})
        result['completed_generation'] = candidate.state.to_dict()['engine']['generation']
        result['duration_seconds'] = time.perf_counter() - started
    return result


class ProviderCapacityTests(unittest.TestCase):
    def test_sparse_three_replacements_fit_as_complete_actual_commands(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                result = capacity_trace(algorithm, dense=False)
                self.assertIsNone(result['rejection'])
                self.assertEqual(result['completed_generation'], base.MAX_GENERATIONS)
                self.assertEqual([row['generation'] for row in result['replacements']], [1, 2, 3])
                self.assertEqual(result['replacements'][-1]['accounts'], 32)
                self.assertLessEqual(result['maximum_bytes'], base.MAX_PAYLOAD_BYTES)

    def test_dense_retention_rejects_complete_oversized_candidates_without_mutation(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                result = capacity_trace(algorithm, dense=True)
                rejection = result['rejection']
                if algorithm in ('genetic_algorithm', 'differential_evolution'):
                    self.assertIsNone(rejection)
                    self.assertEqual(result['completed_generation'], 3)
                    self.assertEqual(result['replacements'][-1]['positions'], 48)
                else:
                    self.assertIsNotNone(rejection)
                    expected_generation = 2 if algorithm == 'particle_swarm' else 1
                    self.assertEqual(result['completed_generation'], expected_generation)
                    self.assertEqual(rejection['generation'], expected_generation)
                    self.assertTrue(any(size > base.MAX_PAYLOAD_BYTES
                        for size in rejection['serialized_payload_bytes'].values()))
                self.assertLessEqual(result['maximum_bytes'], base.MAX_PAYLOAD_BYTES)

    def test_one_hz_two_phase_commands_exhaust_owner_before_one_hour_window(self):
        # Create and bootstrap each consume one identity. Heartbeats and outbox
        # acknowledgments do not change the economic-command count.
        fixed_commands = 2
        complete_quotes = (MAX_OWNED_COMMANDS - fixed_commands) // 2
        # Including the quote that starts the cohort, an uninterrupted 1 Hz
        # window needs 3,601 pairs to observe its first due timestamp.
        required_quotes = base.HORIZON_SECONDS + 1
        self.assertEqual(complete_quotes, 2047)
        self.assertLess(complete_quotes, required_quotes)
        self.assertGreater(required_quotes * 2 + fixed_commands, MAX_OWNED_COMMANDS)
        self.assertEqual(required_quotes * 2 + fixed_commands, 7204)
        self.assertLessEqual(required_quotes, 4096)  # Separate source watermark bound.
        self.assertEqual(base.MAX_GENERATIONS, 3)


if __name__ == '__main__':
    if sys.argv[1:] == ['--measure']:
        print(json.dumps([capacity_trace(algorithm, dense=dense)
            for dense in (False, True) for algorithm in ALGORITHMS], indent=2, sort_keys=True))
    else:
        unittest.main()
