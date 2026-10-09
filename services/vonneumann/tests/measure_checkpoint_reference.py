"""Reproducible offline capacity decomposition, not a throughput or DB benchmark."""
import json
from importlib.metadata import version
import platform
import sys
import unittest

from tests.test_provider_capacity import capacity_trace
from tests.test_provider_contract import ALGORITHMS, OWNER, RUN
from vonneumann.research.checkpoint_reference import CheckpointReference, encode_owned_candidate, jsonb_text_bytes, TRANSPORT
from vonneumann.core import exact_lifecycle, exact_rehearsal


def measure(algorithm, dense):
    rows = []

    def observe(candidate, command):
        before = candidate.transition['before']
        # Placeholder has the same fixed length as the real opaque PG hash.
        # It is not an acknowledged reference or server-derived fingerprint.
        ref = CheckpointReference(OWNER, RUN, 1 if before is None else before['revision'], '0' * 64)
        encoded = encode_owned_candidate(candidate, ref)
        after = candidate.state.to_dict()
        request = command.expected_request
        compact_request = {**request, 'payload': encoded.to_dict()}
        rows.append({'revision': after['revision'], 'generation': after['engine']['generation'],
            'original_payload_bytes': candidate.payload_bytes, 'reference_payload_bytes': encoded.payload_bytes,
            'original_request_bytes': jsonb_text_bytes(request),
            'reference_request_bytes': jsonb_text_bytes(compact_request),
            'expanded_validation_bytes': encoded.expanded_bytes,
            'after_state_bytes': jsonb_text_bytes(after),
            'component_bytes': {key: jsonb_text_bytes(after[key]) for key in ('accounts', 'positions', 'source')}
                | {key: jsonb_text_bytes(after['engine'][key]) for key in
                    ('optimizer', 'used_ids', 'members', 'last_evaluation', 'cohort', 'ema')},
            'accounts': len(after['accounts']), 'positions': len(after['positions']),
            'used_ids': len(after['engine']['used_ids'])})

    original = capacity_trace(algorithm, dense=dense, observer=observe)
    original.pop('duration_seconds')
    original_total = sum(row['original_request_bytes'] for row in rows)
    reference_total = sum(row['reference_request_bytes'] for row in rows)
    return {'algorithm': algorithm, 'dense': dense, 'original_admission': original,
        'accepted_commands': len(rows), 'original_logical_request_bytes': original_total,
        'reference_logical_request_bytes': reference_total,
        'logical_request_bytes_saved': original_total - reference_total,
        'final': rows[-1], 'maximum_reference_payload_bytes': max(row['reference_payload_bytes'] for row in rows),
        'maximum_expanded_validation_bytes': max(row['expanded_validation_bytes'] for row in rows)}


def software():
    return {'python': platform.python_version(), 'numpy': version('numpy'), 'cmaes': version('cmaes'),
        'transport': TRANSPORT, 'model': exact_lifecycle.CODE_VERSION,
        'candidate': exact_rehearsal.CODE_VERSION, 'database_hash_policy': 'postgres17-jsonb-sha256-v1'}


def report():
    return {'version': 1, 'scope': 'synthetic offline prepared transitions only',
        'software': software(),
        'reference_hash': 'fixed-length placeholder; not a server receipt',
        'database_storage_savings_measured': False, 'throughput_measured': False,
        'runtime_or_admission_changed': False,
        'traces': [measure(algorithm, dense) for dense in (False, True) for algorithm in ALGORITHMS]}


class CheckpointCapacityResearchTests(unittest.TestCase):
    def test_dense_ga_reduces_wire_but_does_not_bound_retained_after_state(self):
        result = measure('genetic_algorithm', True)
        self.assertEqual(result['original_admission']['completed_generation'], 3)
        self.assertEqual((result['final']['accounts'], result['final']['positions']), (32, 48))
        self.assertGreater(result['logical_request_bytes_saved'], 0)
        self.assertLess(result['reference_logical_request_bytes'], result['original_logical_request_bytes'])
        self.assertEqual(result['maximum_expanded_validation_bytes'], result['original_admission']['maximum_bytes'])
        self.assertGreater(result['final']['component_bytes']['positions'], 0)
        self.assertGreater(result['final']['used_ids'], 8)

    def test_dense_pso_keeps_existing_inner_capacity_rejection(self):
        result = measure('particle_swarm', True)
        self.assertIsNotNone(result['original_admission']['rejection'])
        self.assertEqual(result['original_admission']['completed_generation'], 2)
        self.assertLessEqual(result['maximum_expanded_validation_bytes'], 262144)


if __name__ == '__main__':
    if sys.argv[1:] == ['--measure']:
        print(json.dumps(report(), indent=2, sort_keys=True))
    else:
        unittest.main()
