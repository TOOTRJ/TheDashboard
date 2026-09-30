"""Versioned, explicitly owned search randomness independent of market paths."""

from __future__ import annotations

import hashlib
import json
import random
import re

SEARCH_POLICY = 'sha256-namespaced-search-v1'
MAX_SEARCH_SEED = 2**64 - 1


def validate_search_seed(value: str) -> str:
    """Keep the complete uint64 value across JavaScript/JSON transports."""
    if (not isinstance(value, str) or re.fullmatch(r'0|[1-9][0-9]{0,19}', value) is None
            or int(value) > MAX_SEARCH_SEED):
        raise ValueError('Search seed must be a canonical decimal string from 0 through 18446744073709551615')
    return value


def private_rng(rng: random.Random | None = None) -> random.Random:
    """Compatibility calls get a fresh reproducible stream, never global state."""
    return rng if rng is not None else random.Random(0)


class SearchRandomStreams:
    def __init__(self, seed: str = '0', algorithm: str = 'genetic_algorithm'):
        self.seed = validate_search_seed(seed)
        if not isinstance(algorithm, str) or not algorithm:
            raise ValueError('Search algorithm must be a nonempty name')
        self.algorithm = algorithm

    def derive(self, namespace: str, epoch: int = 0, *indices: str | int) -> int:
        if not isinstance(namespace, str) or not namespace:
            raise ValueError('Search stream namespace is required')
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
            raise ValueError('Search epoch must be a nonnegative integer')
        if any(isinstance(i, bool) or not isinstance(i, (str, int)) for i in indices):
            raise ValueError('Search stream indices must be explicit strings or integers')
        # Gen-0 is shared across algorithms for comparable starting populations.
        # Strategy and mutation streams include the algorithm identity.
        algorithm = '' if namespace == 'gen0' else self.algorithm
        payload = [SEARCH_POLICY, self.seed, algorithm, namespace, epoch, *indices]
        digest = hashlib.sha256(json.dumps(payload, separators=(',', ':'), ensure_ascii=True).encode()).digest()
        return int.from_bytes(digest, 'big')

    def rng(self, namespace: str, epoch: int = 0, *indices: str | int) -> random.Random:
        return random.Random(self.derive(namespace, epoch, *indices))

    def spec(self, epoch: int = 0) -> dict:
        # Import lazily: genome construction itself uses private_rng above.
        from .gene_registry import GENOME_POLICY
        from .parameter_codec import PARAMETER_POLICY
        self.derive('validate', epoch)
        return {'version': 'search-spec-v1', 'seed': self.seed, 'algorithm': self.algorithm,
                'epoch': epoch, 'stream_policy': SEARCH_POLICY,
                'search_generator': 'python-MT19937', 'cma_generator': 'numpy-RandomState-MT19937',
                'gen0_stream': 'epoch/candidate-index; shared across algorithms',
                'mutation_stream': 'algorithm/epoch/event/candidate-index',
                'strategy_stream': 'algorithm/epoch; private sequential draws',
                'genome_policy_version': GENOME_POLICY['version'],
                'parameter_policy_version': (PARAMETER_POLICY['version']
                    if self.algorithm in {'cma_es', 'particle_swarm'} else 'effective-gene-domains'),
                'restart_policy': 'increment epoch after aborted evaluation',
                'replay_scope': 'from start with identical config, market data, software, and lifecycle events',
                'optimizer_state_checkpointed': False}
