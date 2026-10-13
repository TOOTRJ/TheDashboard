"""Explicit GA-only graph reconstruction from accepted original-v2 evidence.

No pickle, dynamic imports, arbitrary class construction, RNG seeding, bootstrap,
ask/tell, provider request, identifier allocation or live resource is restored.
"""
from __future__ import annotations

import math
import random
import re
import sys

import numpy as np

from ..core.evaluation import EvaluatedCandidate, EvaluationCohort
from ..core.genome import Genome
from ..core.search_random import SearchRandomStreams
from ..core.strategies.genetic_algorithm import GeneticAlgorithmStrategy
from ..core.strategies.cohort_contract import SelectionCohort, candidate_signature
from ..core.optimizer_evidence import _Encoder, EVIDENCE_VERSION, validate_optimizer_evidence
from ..core.strategies.cma_es import cmaes_lib
from .portable_restoration_wire import RestorationError, require, fields, canonical

_GENES = {'rsi_period', 'rsi_oversold', 'rsi_overbought', 'ema_fast', 'ema_slow', 'volume_threshold',
    'position_size_pct', 'stop_loss_pct', 'take_profit_pct', 'max_open_positions', 'timeframe_minutes',
    'benchmark_target_pct', 'reproduce_target_dollars', 'death_drawdown_pct', 'num_assets'}
_CLASSES = {
    'GeneticAlgorithmStrategy': (GeneticAlgorithmStrategy, {'_search_streams', '_search_epoch', '_rng', '_mutation_event',
        'mutation_rate', 'mutation_strength', '_cohort'}),
    'SearchRandomStreams': (SearchRandomStreams, {'seed', 'algorithm'}),
    'SelectionCohort': (SelectionCohort, {'population_size', 'bound_ids', '_signatures', '_pending',
        '_previous_ids', '_previous_context', '_bootstrap'}),
    'Genome': (Genome, _GENES | {'assets', 'generation', 'parent_ids'}),
    'EvaluatedCandidate': (EvaluatedCandidate, {'probe_id', 'evaluation_id', 'iteration_id', '_genome',
        'fitness', 'roi', 'num_trades', 'reason', 'status', 'window_started_at', 'window_ends_at',
        'terminated_at', 'cohort_complete'}),
    'EvaluationCohort': (EvaluationCohort, {'horizon_seconds', 'iteration_id', 'member_ids', '_genomes',
        '_evaluation_ids', '_evaluations', 'phase', 'started_at', 'ends_at', 'completed_at', 'abort_reason'}),
}


def finite_hex(text):
    require(type(text) is str and len(text) <= 32, 'Bounded graph binary64 required')
    try:
        result = float.fromhex(text)
    except (ValueError, OverflowError):
        raise RestorationError('Invalid graph binary64') from None
    require(math.isfinite(result) and result.hex() == text, 'Canonical graph binary64 required')
    return result


def integer(value, minimum=0, maximum=2**63 - 1):
    require(type(value) is int and minimum <= value <= maximum, 'Bounded graph integer required')
    return value


class _GraphDecoder:
    def __init__(self):
        self.nodes = {}
        self.active = set()
        self.visits = 0

    def value(self, value, depth=0):
        self.visits += 1
        require(self.visits <= 20000 and depth <= 64, 'Restoration graph exceeds traversal capacity')
        if value is None or type(value) is bool:
            return value
        if type(value) is str:
            require('\x00' not in value and len(value.encode('utf-8')) <= 4096)
            return value
        require(type(value) is dict, 'Tagged graph value required')
        if value.keys() == {'ref'}:
            node = integer(value['ref'])
            require(node in self.nodes and node not in self.active, 'Missing, forward or cyclic restoration reference')
            return self.nodes[node]
        tag = value.get('type')
        if tag == 'integer':
            fields(value, {'type', 'decimal'})
            text = value['decimal']
            require(type(text) is str and len(text) <= 79 and re.fullmatch(r'0|-?[1-9][0-9]*', text, re.ASCII) is not None)
            result = int(text)
            require(result.bit_length() <= 256)
            return result
        if tag == 'float':
            fields(value, {'type', 'hex'})
            return finite_hex(value['hex'])
        node = integer(value.get('node'))
        require(node == len(self.nodes), 'Graph node traversal order differs')
        self.nodes[node] = None
        self.active.add(node)
        try:
            result = self.compound(value, tag, depth)
            self.nodes[node] = result
            return result
        finally:
            self.active.remove(node)

    def compound(self, value, tag, depth):
        if tag in {'list', 'tuple'}:
            fields(value, {'node', 'type', 'items'})
            require(type(value['items']) is list and len(value['items']) <= 4096)
            items = [self.value(item, depth + 1) for item in value['items']]
            return tuple(items) if tag == 'tuple' else items
        if tag == 'map':
            fields(value, {'node', 'type', 'entries'})
            require(type(value['entries']) is list and len(value['entries']) <= 4096)
            result = {}
            for pair in value['entries']:
                require(type(pair) is list and len(pair) == 2 and type(pair[0]) is str and pair[0] not in result)
                key = self.value(pair[0], depth + 1)
                result[key] = self.value(pair[1], depth + 1)
            return result
        if tag == 'python.Random':
            fields(value, {'node', 'type', 'algorithm', 'state_version', 'words', 'index', 'gaussian_hex'})
            require(value['algorithm'] == 'MT19937' and type(value['state_version']) is int and value['state_version'] == 3)
            require(type(value['words']) is list and len(value['words']) == 624)
            words = tuple(integer(word, maximum=2**32 - 1) for word in value['words'])
            cursor = integer(value['index'], maximum=624)
            gaussian = None if value['gaussian_hex'] is None else finite_hex(value['gaussian_hex'])
            # Invoke the fixed builtin C allocator, never random.Random.__init__/seed.
            result = random.Random.__new__(random.Random)
            result.setstate((3, words + (cursor,), gaussian))
            require(result.getstate() == (3, words + (cursor,), gaussian))
            return result
        if tag == 'object':
            fields(value, {'node', 'type', 'class', 'fields'})
            name = value['class']
            require(type(name) is str and name in _CLASSES, 'Only pinned GA restoration classes are admitted')
            kind, names = _CLASSES[name]
            fields(value['fields'], names)
            result = object.__new__(kind)
            for key in sorted(names):
                object.__setattr__(result, key, self.value(value['fields'][key], depth + 1))
            return result
        raise RestorationError('Unsupported restoration graph type')


def reconstruct_graph(evidence, state):
    """Decode exact classes and independently check all authoritative mirrors."""
    fields(evidence, {'version', 'software', 'strategy', 'cohort'})
    require(evidence['version'] == EVIDENCE_VERSION)
    fields(evidence['software'], {'python', 'numpy', 'cmaes'})
    runtime = {'python': '.'.join(map(str, sys.version_info[:3])), 'numpy': np.__version__,
               'cmaes': None if cmaes_lib is None else cmaes_lib.__version__}
    require(runtime == {'python': '3.12.14', 'numpy': '2.5.3', 'cmaes': '0.13.1'}
            and evidence['software'] == runtime, 'Restoration requires the exact reviewed dependency runtime')
    validate_optimizer_evidence(evidence)
    decoder = _GraphDecoder()
    strategy = decoder.value(evidence['strategy'])
    cohort = decoder.value(evidence['cohort'])
    require(type(strategy) is GeneticAlgorithmStrategy and type(cohort) is EvaluationCohort)
    require(type(strategy._search_streams) is SearchRandomStreams and type(strategy._rng) is random.Random
            and type(strategy._cohort) is SelectionCohort)
    engine, configuration = state['engine'], state['engine']['config']
    require(strategy._search_streams.algorithm == 'genetic_algorithm'
            and strategy._search_streams.seed == configuration['search_seed'])
    integer(strategy._search_epoch, maximum=2**31 - 2)
    integer(strategy._mutation_event, maximum=2**31 - 2)
    require(type(engine['lifecycle']['search_epoch']) is int
            and strategy._search_epoch == engine['lifecycle']['search_epoch'])
    require(type(strategy.mutation_rate) is float and strategy.mutation_rate.hex() == (0.2).hex()
            and type(strategy.mutation_strength) is float and strategy.mutation_strength.hex() == (0.15).hex())
    members = engine['members']
    ids = tuple(member['id'] for member in members)
    require(type(cohort.member_ids) is tuple and cohort.member_ids == ids
            and list(cohort._genomes) == list(ids) and list(cohort._evaluation_ids) == list(ids))
    require(list(cohort._evaluations) == [identifier for identifier in ids if identifier in cohort._evaluations])
    from ..core import exact_rehearsal as base
    for index, member in enumerate(members):
        genome = cohort._genomes[member['id']]
        require(type(genome) is Genome and base._genome_dict(genome) == member['genome'])
        require(cohort._evaluation_ids[member['id']] == f'{cohort.iteration_id}:{index}')
        result = cohort._evaluations.get(member['id'])
        if result is not None:
            require(type(result) is EvaluatedCandidate and type(result._genome) is Genome
                    and base._genome_dict(result._genome) == member['genome'])
    require(canonical(base._views(cohort.to_dict())) == canonical(engine['cohort']),
            'Restored cohort differs from its original primitive mirror')
    selection = strategy._cohort
    require(type(selection._bootstrap) is bool and selection._pending is None)
    if engine['lifecycle']['restart_required']:
        require(type(selection.population_size) is int and selection.population_size == 0
                and selection.bound_ids == () and selection._signatures == {}
                and selection._previous_ids == () and selection._previous_context is None
                and selection._bootstrap is False, 'Aborted selection state differs')
    else:
        require(type(selection.population_size) is int and selection.population_size == 8
                and type(selection.bound_ids) is tuple and selection.bound_ids == ids
                and list(selection._signatures) == list(ids))
        for identifier in ids:
            require(canonical(base._views(selection._signatures[identifier])) ==
                    canonical(base._views(candidate_signature(cohort._genomes[identifier]))))
    # Re-encode through the read-only original encoder (no fresh-state copier,
    # constructor, seed or optimizer call) to verify graph order and alias identity.
    encoder = _Encoder()
    rebuilt = {'version': EVIDENCE_VERSION, 'software': runtime,
               'strategy': encoder.value(strategy), 'cohort': encoder.value(cohort)}
    require(canonical(rebuilt) == canonical(evidence), 'Restored graph/alias/RNG round trip differs')
    return strategy, cohort
