"""Frozen, bounded paired synthetic experiments with complete replay verification.

This wraps the unchanged reference evaluator, not the production colony solver.
Search seeds describe algorithm variability on one dataset, not independent
market evidence. Child artifacts include every trial and complete account ledger.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import sys

from ..core.execution import ExecutionConfig
from ..core.search_random import validate_search_seed
from ..market.dataset import DatasetError, MAX_FRAMES
from ..market.replay_feed import ReplayFeed
from .artifacts import (ARTIFACT_VERSION, MAX_RESULT_BYTES, ResearchArtifactError,
                        ResearchResult, canonical_bytes, load_result, plain_data, write_result)
from .runner import ResearchConfig, ResearchError, run_experiment, source_fingerprint

VERSION = 'ema-paired-synthetic-protocol-v1'
PLAN_FORMAT = 'ema-paired-plan-v1'
RESULT_FORMAT = 'ema-paired-result-v1'
MAX_CHILDREN = 16
MAX_LEDGER_ROWS = 2_000_000
BASELINE_POLICY = {
    'version': 'fixed-grid-reference-controls-v1',
    'domain': 'twenty_declared_ema_pairs', 'objective': 'ROI_minus_2_historical_max_drawdown',
    'search': 'reference_GA_and_random_shared_initialization_equal_logical_requests',
    'duplicates': 'charged; no_forced_unseen_fallback',
    'selection': 'training_only_then_fresh_holdout; no_holdout_reselection',
    'controls': ['cash', 'fixed-ema-09-21', 'buy-hold-25', 'buy-hold-100'],
    'passive': '25_percent_exposure_and_100_percent_market_reference; no_protective_exits',
    'computation': '24_training_accounts_per_child; cached_search_scores; no_runtime_savings_claim',
    'primary': 'heldout_GA_minus_paired_random_net_fitness',
    'inference': 'descriptive_only; seeds_are_not_independent_market_samples',
}
_BASELINE_WIRE = canonical_bytes(BASELINE_POLICY)
CONTROL_IDS = ('cash', 'fixed-ema-09-21', 'buy-hold-25', 'buy-hold-100')


class PairedResearchError(ValueError):
    def __init__(self, code='paired_invalid'):
        self.code = code if code in {'paired_invalid', 'paired_context', 'paired_capacity', 'paired_integrity'} else 'paired_invalid'
        super().__init__('Paired research contract refused the evidence.')


def _source():
    root = Path(__file__).resolve().parent
    return source_fingerprint() | {
        'services/vonneumann/vonneumann/research/' + name:
            hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ('protocol.py', 'artifacts.py')}


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise PairedResearchError()


def _json(wire):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PairedResearchError()
            result[key] = value
        return result
    if type(wire) is not bytes or len(wire) > 65536:
        raise PairedResearchError('paired_capacity')
    try:
        value = json.loads(wire.decode('ascii'), object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(PairedResearchError()))
        if canonical_bytes(value) != wire:
            raise PairedResearchError('paired_integrity')
        return value
    except (UnicodeError, TypeError, ValueError, OverflowError, RecursionError):
        raise PairedResearchError() from None


def _config(value):
    _keys(value, {'asset', 'timeframe_minutes', 'train_minutes', 'holdout_minutes',
                  'initial_capital', 'execution'})
    try:
        return ResearchConfig.from_dict(value | {'random_seed': '0', 'random_budget': 1})
    except (TypeError, ValueError, OverflowError):
        raise PairedResearchError() from None


@dataclass(frozen=True, slots=True)
class PairedProtocol:
    _wire: bytes

    def __post_init__(self):
        value = _json(self._wire)
        _keys(value, {'version', 'scope', 'dataset', 'engine_source_sha256', 'python',
                      'base_config', 'seeds', 'budgets', 'baseline_policy', 'limits'})
        if (value['version'] != VERSION or value['scope'] != 'synthetic_mechanics_only' or
                value['python'] != '3.12.14' or
                canonical_bytes(value['baseline_policy']) != _BASELINE_WIRE or
                value['limits'] != {'children': MAX_CHILDREN, 'ledger_rows': MAX_LEDGER_ROWS, 'result_bytes': MAX_RESULT_BYTES}):
            raise PairedResearchError()
        _keys(value['dataset'], {'dataset_id', 'schema_version', 'frames_sha256', 'frame_count',
               'source_kind', 'quote_currency', 'volume_unit', 'availability_semantics', 'valuation_policy', 'playback_policy'})
        pinned = {'schema_version': 'market-dataset-v1', 'source_kind': 'synthetic_fixture',
                  'quote_currency': 'USD', 'volume_unit': 'synthetic_base_token',
                  'availability_semantics': 'modeled', 'valuation_policy': 'usd-reference-only-v1',
                  'playback_policy': 'synthetic-whole-frame-once-v1'}
        if (any(value['dataset'][key] != expected for key, expected in pinned.items()) or
                type(value['dataset']['frame_count']) is not int or
                not 1 <= value['dataset']['frame_count'] <= MAX_FRAMES):
            raise PairedResearchError()
        for digest in (value['dataset']['dataset_id'], value['dataset']['frames_sha256']):
            if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise PairedResearchError()
        sources = value['engine_source_sha256']
        expected_names = set(_source())
        if type(sources) is not dict or set(sources) != expected_names:
            raise PairedResearchError()
        if any(type(v) is not str or len(v) != 64 or any(c not in '0123456789abcdef' for c in v) for v in sources.values()):
            raise PairedResearchError()
        config = _config(value['base_config'])
        if config.required_frames > value['dataset']['frame_count']:
            raise PairedResearchError('paired_capacity')
        seeds, budgets = value['seeds'], value['budgets']
        if (type(seeds) is not list or not 1 <= len(seeds) <= 8 or
                type(budgets) is not list or not 1 <= len(budgets) <= 4 or
                any(type(v) is not str for v in seeds) or
                any(type(v) is not int or not 1 <= v <= 20 for v in budgets)):
            raise PairedResearchError()
        try:
            for seed in seeds:
                validate_search_seed(seed)
        except (TypeError, ValueError):
            raise PairedResearchError() from None
        if len(set(seeds)) != len(seeds) or budgets != sorted(set(budgets)):
            raise PairedResearchError()
        children = len(seeds) * len(budgets)
        rows = children * (24 * (config.train_minutes + 1) + 7 * (config.holdout_minutes + 1))
        if children > MAX_CHILDREN or rows > MAX_LEDGER_ROWS:
            raise PairedResearchError('paired_capacity')

    @classmethod
    def freeze(cls, dataset_path, config, *, seeds, budgets):
        if type(config) is not ResearchConfig or type(seeds) is not tuple or type(budgets) is not tuple:
            raise PairedResearchError()
        feed = ReplayFeed(dataset_path)  # Retains original provider-replay refusal.
        if config.asset not in feed._assets or feed.simulation_spec['start_timestamp'] % (config.timeframe_minutes * 60):
            raise PairedResearchError('paired_context')
        base = config.to_dict()
        base.pop('random_seed'); base.pop('random_budget')
        return cls(canonical_bytes({'version': VERSION, 'scope': 'synthetic_mechanics_only',
            'dataset': feed.dataset_spec, 'engine_source_sha256': _source(), 'python': platform.python_version(),
            'base_config': base, 'seeds': list(seeds), 'budgets': list(budgets),
            'baseline_policy': json.loads(_BASELINE_WIRE),
            'limits': {'children': MAX_CHILDREN, 'ledger_rows': MAX_LEDGER_ROWS, 'result_bytes': MAX_RESULT_BYTES}}))

    @classmethod
    def from_dict(cls, value):
        return cls(canonical_bytes(value))

    def to_dict(self):
        return _json(self._wire)

    @property
    def protocol_id(self):
        return hashlib.sha256(self._wire).hexdigest()


def _context(dataset_path, protocol):
    if type(protocol) is not PairedProtocol:
        raise PairedResearchError()
    value = protocol.to_dict()
    if (canonical_bytes(ReplayFeed(dataset_path).dataset_spec) != canonical_bytes(value['dataset']) or
            _source() != value['engine_source_sha256'] or platform.python_version() != value['python']):
        raise PairedResearchError('paired_context')
    return value


def _artifact(payload):
    wire = canonical_bytes(payload)
    manifest = {'schema_version': ARTIFACT_VERSION,
                'payload': {'file': 'result.json', 'bytes': len(wire), 'sha256': hashlib.sha256(wire).hexdigest()}}
    artifact = ResearchResult(payload, manifest)
    return {'result_id': artifact.result_id, 'manifest': manifest, 'payload': payload}


def _difference(left, right):
    fields = ('fitness', 'roi', 'max_drawdown', 'net_pnl', 'total_costs', 'num_trades')
    result = {}
    for field in fields:
        a, b = left[field], right[field]
        if type(a) not in (int, float) or type(b) not in (int, float) or not math.isfinite(a) or not math.isfinite(b):
            raise PairedResearchError('paired_integrity')
        difference = a - b
        if not math.isfinite(difference):
            raise PairedResearchError('paired_integrity')
        result[field] = difference
    return result


def _row(payload, seed, budget):
    selection = payload['selection']
    if any(selection[a]['seed'] != seed or type(selection[a]['budget']) is not int or selection[a]['budget'] != budget for a in ('ga', 'random')):
        raise PairedResearchError('paired_integrity')
    summaries = {row['candidate_id']: row['summary'] for row in payload['evaluations']['holdout']}
    ids = {'ga': selection['ga']['winner'], 'random': selection['random']['winner'],
           'grid': selection['grid_winner']} | {name: name for name in CONTROL_IDS}
    selected = {name: summaries[identity] for name, identity in ids.items()}
    return {'seed': seed, 'budget': budget, 'training_selected_ids': ids,
            'holdout_summaries': selected,
            'ga_minus_random': _difference(selected['ga'], selected['random']),
            'ga_minus_controls': {name: _difference(selected['ga'], selected[name])
                                 for name in ('grid', *CONTROL_IDS)},
            'requests': {algorithm: {key: selection[algorithm][key] for key in
                 ('budget', 'unique_trials', 'duplicate_trials', 'score_cache_hits',
                  'additional_computed_evaluations', 'elite_score_reuses')} for algorithm in ('ga', 'random')},
            'exhaustive_training_accounts_charged': 24}


async def run_protocol(dataset_path, protocol):
    value = _context(dataset_path, protocol)
    base = _config(value['base_config'])
    children, rows, spent = [], [], 0
    # Sequential children: no shared RNG, mutable account, parallel fixture or
    # sampled market independence is introduced by this protocol wrapper.
    for seed in value['seeds']:
        for budget in value['budgets']:
            _context(dataset_path, protocol)
            payload = await run_experiment(dataset_path, replace(base, random_seed=seed, random_budget=budget))
            if payload['scope'] != 'synthetic_mechanics_only':
                raise PairedResearchError('paired_integrity')
            artifact = _artifact(payload)
            spent += artifact['manifest']['payload']['bytes']
            if spent > MAX_RESULT_BYTES:
                raise PairedResearchError('paired_capacity')
            children.append({'seed': seed, 'budget': budget, **artifact})
            rows.append(_row(payload, seed, budget))
    _context(dataset_path, protocol)
    distributions = []
    for budget in value['budgets']:
        differences = [row['ga_minus_random']['fitness'] for row in rows if row['budget'] == budget]
        distributions.append({'budget': budget, 'seed_pairs': len(differences),
            'ga_minus_random_fitness': {'minimum': min(differences), 'median': statistics.median(differences), 'maximum': max(differences)},
            'greater_count': sum(d > 0 for d in differences), 'equal_count': sum(d == 0 for d in differences),
            'less_count': sum(d < 0 for d in differences), 'inference': 'descriptive_only'})
    result = {'schema_version': 'ema-research-v1', 'format': RESULT_FORMAT,
        'scope': 'synthetic_mechanics_only', 'protocol_id': protocol.protocol_id,
        'protocol': value, 'children': children, 'paired_rows': rows, 'distributions': distributions,
        'claims': {'empirical_performance': False, 'production_solver_compared': False,
                   'calibrated_execution': False, 'independent_market_samples': False,
                   'runtime_savings': False, 'native_admission': False}}
    if len(canonical_bytes(result)) > MAX_RESULT_BYTES:
        raise PairedResearchError('paired_capacity')
    return result


def write_plan(path, protocol):
    if type(protocol) is not PairedProtocol:
        raise PairedResearchError()
    return write_result(path, {'schema_version': 'ema-research-v1', 'format': PLAN_FORMAT,
                              'scope': 'synthetic_mechanics_only', 'protocol': protocol.to_dict()})


def load_plan(path):
    payload = plain_data(load_result(path).payload)
    _keys(payload, {'schema_version', 'format', 'scope', 'protocol'})
    if payload['format'] != PLAN_FORMAT or payload['scope'] != 'synthetic_mechanics_only':
        raise PairedResearchError()
    return PairedProtocol.from_dict(payload['protocol'])


async def verify_result(dataset_path, path):
    artifact = load_result(path)
    payload = plain_data(artifact.payload)
    _keys(payload, {'schema_version', 'format', 'scope', 'protocol_id', 'protocol',
                    'children', 'paired_rows', 'distributions', 'claims'})
    if payload['format'] != RESULT_FORMAT or payload['scope'] != 'synthetic_mechanics_only':
        raise PairedResearchError()
    protocol = PairedProtocol.from_dict(payload['protocol'])
    if payload['protocol_id'] != protocol.protocol_id:
        raise PairedResearchError('paired_integrity')
    replay = await run_protocol(dataset_path, protocol)
    if canonical_bytes(replay) != canonical_bytes(payload):
        raise PairedResearchError('paired_integrity')
    return artifact


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan', help='freeze a bounded synthetic protocol before evaluation')
    plan.add_argument('--dataset', type=Path, required=True); plan.add_argument('--output', type=Path, required=True)
    plan.add_argument('--seed', action='append', required=True); plan.add_argument('--budget', action='append', type=int, required=True)
    plan.add_argument('--timeframe-minutes', type=int, default=15)
    plan.add_argument('--train-minutes', type=int, default=1440); plan.add_argument('--holdout-minutes', type=int, default=1440)
    plan.add_argument('--initial-capital', type=float, default=1000.0); plan.add_argument('--asset', default='SOL/USDC')
    for name in ('fee-bps', 'half-spread-bps', 'slippage-bps'): plan.add_argument('--' + name, type=float, default=0.0)
    run = sub.add_parser('run'); run.add_argument('--dataset', type=Path, required=True)
    run.add_argument('--plan', type=Path, required=True); run.add_argument('--output', type=Path, required=True)
    verify = sub.add_parser('verify'); verify.add_argument('--dataset', type=Path, required=True)
    verify.add_argument('--result', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'plan':
            config = ResearchConfig(asset=args.asset, timeframe_minutes=args.timeframe_minutes,
                train_minutes=args.train_minutes, holdout_minutes=args.holdout_minutes, initial_capital=args.initial_capital,
                execution=ExecutionConfig(args.fee_bps, args.half_spread_bps, args.slippage_bps))
            protocol = PairedProtocol.freeze(args.dataset, config, seeds=tuple(args.seed), budgets=tuple(args.budget))
            artifact = write_plan(args.output, protocol); count = 0
        elif args.command == 'run':
            protocol = load_plan(args.plan)
            payload = asyncio.run(run_protocol(args.dataset, protocol))
            artifact = write_result(args.output, payload); count = len(payload['children'])
        else:
            artifact = asyncio.run(verify_result(args.dataset, args.result))
            count = len(artifact.payload['children'])
        print(json.dumps({'artifact_id': artifact.result_id, 'scope': 'synthetic_mechanics_only',
                          'children': count, 'verification': 'full_replay_equal' if args.command == 'verify' else args.command}, sort_keys=True))
        return 0
    except (PairedResearchError, ResearchError, ResearchArtifactError, DatasetError) as error:
        print(json.dumps({'error': error.code}, sort_keys=True), file=sys.stderr)
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        print('{"error":"paired_command_failed"}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
