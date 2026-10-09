"""Reproduce complete fresh-model sizes; never a hosted/cost/throughput claim."""
import json
import platform
import sys
from pathlib import Path
from tests.security_support import deny_network
from tests.test_ga_active_model import trace
from vonneumann.research.ga_active_model import MODEL_FORMAT, COMMAND_FORMAT, ASSESSMENT_FORMAT


def measure():
    with deny_network():
        records = [trace(dense=dense)[0] for dense in (False, True)]
    return {'model': MODEL_FORMAT, 'command': COMMAND_FORMAT, 'assessment': ASSESSMENT_FORMAT,
        'software': {'python': platform.python_version()}, 'population': 8,
        'source': 'deterministic synthetic observations, no network or production credentials',
        'limits': {'complete_candidate_bytes': 262144, 'current_accounts': 8, 'open_positions': 8},
        'measurement_scope': 'actual prepared full active before/after plus operations, events, input evidence and per-command history; PostgreSQL-spaced JSON bound',
        'excluded': ['native reference/components and SQL admission', 'provider provenance/clock freshness',
            'original-command IDs/receipts, transport and heartbeat/relay/Stop overhead',
            'database tables/indexes/TOAST, retained history and simulation ledger memory',
            'hosted cost, throughput, latency, restart/decoder and profitability'], 'traces': records}


if __name__ == '__main__':
    if sys.argv[1:] != ['--measure']: raise SystemExit('Use --measure for credential-free synthetic measurements')
    artifact = Path(__file__).resolve().parents[1] / 'research/ga-active-model-capacity.json'
    value = measure()
    artifact.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    print(json.dumps(value, sort_keys=True))
