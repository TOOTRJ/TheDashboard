"""Reproducible GA checkpoint-format sizes, not full-command or cost savings."""
import json
from pathlib import Path
import sys

import numpy as np

from tests.security_support import deny_network
from tests.test_active_checkpoint import ga_trace
from vonneumann.research.active_checkpoint import (
    FORMAT, HASH_POLICY, capture_owned_candidate, component_updates,
)
from vonneumann.research.checkpoint_reference import jsonb_text_bytes


def measurements():
    traces = []
    with deny_network():
        for dense in (False, True):
            result, candidates = ga_trace(dense)
            previous = None
            totals = {'full_after_state_bytes': 0, 'resolved_active_bytes': 0,
                      'manifest_bytes': 0, 'hypothetical_checkpoint_write_bytes': 0,
                      'changed_components': 0, 'captures_without_changed_components': 0}
            maxima = {key: 0 for key in ('manifest_bytes', 'resolved_active_bytes',
                                        'hypothetical_checkpoint_write_bytes', 'open_positions')}
            generations = []
            for candidate in candidates:
                current = capture_owned_candidate(candidate)
                resolved = current.resolve()
                changed = current.components if previous is None else component_updates(previous, current)
                sizes = {'full_after_state_bytes': jsonb_text_bytes(candidate.state.to_dict()),
                         'resolved_active_bytes': current.resolved_bytes,
                         'manifest_bytes': current.manifest_bytes,
                         'hypothetical_checkpoint_write_bytes': jsonb_text_bytes({
                             'manifest': current.to_dict(),
                             'new_components': [block.to_dict() for block in changed]})}
                for key, size in sizes.items(): totals[key] += size
                totals['changed_components'] += len(changed)
                totals['captures_without_changed_components'] += not changed
                for key in maxima:
                    maxima[key] = max(maxima[key], len(resolved['positions']) if key == 'open_positions' else sizes[key])
                if previous is None or resolved['engine']['generation'] != previous.resolve()['engine']['generation']:
                    generations.append({'generation': resolved['engine']['generation'],
                        'source_accounts': len(candidate.state.to_dict()['accounts']),
                        'source_positions': len(candidate.state.to_dict()['positions']),
                        'active_accounts': len(resolved['accounts']),
                        'active_open_positions': len(resolved['positions']),
                        'active_bytes': current.resolved_bytes,
                        'manifest_bytes': current.manifest_bytes,
                        'changed_components': len(changed)})
                previous = current
            traces.append({'dense': dense, 'admitted_v5_candidates': len(candidates),
                           'original_completed_generation': result['completed_generation'],
                           'original_rejection': result['rejection'], 'totals': totals,
                           'maxima': maxima, 'generation_checkpoints': generations})
    return {'format': FORMAT, 'hash_policy': HASH_POLICY,
            'software': {'python': '.'.join(map(str, sys.version_info[:3])), 'numpy': np.__version__},
            'source_model_version': 5, 'synthetic': True,
            'scope': 'admitted existing sparse/dense GA captures; skipped intermediate price seconds',
            'limits': 'unchanged original v5 generation, identity, source and command limits',
            'measurement_basis': 'existing PostgreSQL-spacing byte-admission estimate; hashes use canonical UTF-8 JSON',
            'exclusions': ['operations/events/input evidence', 'before checkpoint/reference',
                           'create/heartbeat/relay/stop', 'server retention/ACKs', 'SQL storage/index/TOAST',
                           'native admission', 'optimizer restoration', 'sustained latency/throughput/cost'],
            'interpretation': 'checkpoint format comparison only; hypothetical writes assume validated previous components remain available',
            'traces': traces}


if __name__ == '__main__':
    if sys.argv[1:] != ['--measure']:
        raise SystemExit('Use --measure; this creates only the owned synthetic artifact')
    report = measurements()
    target = Path(__file__).resolve().parents[1] / 'research' / 'active-checkpoint-capacity.json'
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'artifact': str(target), 'traces': report['traces']}, indent=2, sort_keys=True))
