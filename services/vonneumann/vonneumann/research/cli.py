"""Run or fully reproduce bounded synthetic EMA research without credentials.

No worker, provider request, wallet, database or account connection is used.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from ..core.execution import ExecutionConfig
from ..core.market_validation import MarketValueError, ProbeStepError
from ..market.dataset import DatasetError
from ..market.feed import MarketFeedError
from .artifacts import ResearchArtifactError, canonical_bytes, load_result, plain_data, write_result
from .runner import ResearchConfig, ResearchError, run_experiment


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run', help='evaluate the fixed grid and controls on a local synthetic dataset')
    run.add_argument('--dataset', required=True, type=Path)
    run.add_argument('--output', required=True, type=Path, help='new result directory; never overwritten')
    run.add_argument('--asset', default='SOL/USDC')
    run.add_argument('--timeframe-minutes', type=int, default=15)
    run.add_argument('--train-minutes', type=int, default=1440)
    run.add_argument('--holdout-minutes', type=int, default=1440)
    run.add_argument('--initial-capital', type=float, default=1000.0)
    run.add_argument('--random-seed', default='0')
    run.add_argument('--random-budget', type=int, default=10)
    run.add_argument('--fee-bps', type=float, default=0.0)
    run.add_argument('--half-spread-bps', type=float, default=0.0)
    run.add_argument('--slippage-bps', type=float, default=0.0)
    verify = sub.add_parser('verify', help='rerun the bound dataset and compare the entire result, including ledgers')
    verify.add_argument('--dataset', required=True, type=Path)
    verify.add_argument('--result', required=True, type=Path)
    return parser


def _summary(artifact, *, verified=False):
    payload = artifact.payload
    return {'result_id': artifact.result_id, 'dataset_id': payload['dataset']['dataset_id'],
            'scope': payload['scope'], 'verification': 'full_replay_equal' if verified else 'created',
            'grid_training_winner': payload['selection']['grid_winner'],
            'random_training_winner': payload['selection']['random']['winner'],
            'random_budget': payload['selection']['random']['budget'],
            'holdout': [{'candidate_id': row['candidate_id'], **plain_data(row['summary'])}
                        for row in payload['evaluations']['holdout']]}


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == 'run':
            config = ResearchConfig(asset=args.asset, timeframe_minutes=args.timeframe_minutes,
                train_minutes=args.train_minutes, holdout_minutes=args.holdout_minutes,
                initial_capital=args.initial_capital, random_seed=args.random_seed,
                random_budget=args.random_budget,
                execution=ExecutionConfig(args.fee_bps, args.half_spread_bps, args.slippage_bps))
            payload = asyncio.run(run_experiment(args.dataset, config))
            written = write_result(args.output, payload)
            artifact = load_result(args.output)
            if artifact.result_id != written.result_id:
                raise ResearchArtifactError('research_integrity')
        else:
            artifact = load_result(args.result)
            config = ResearchConfig.from_dict(plain_data(artifact.payload.get('config')))
            replay = asyncio.run(run_experiment(args.dataset, config))
            if canonical_bytes(artifact.payload) != canonical_bytes(replay):
                raise ResearchArtifactError('research_integrity')
        result = _summary(artifact, verified=args.command == 'verify')
    except (ResearchError, ResearchArtifactError, DatasetError, MarketFeedError) as error:
        print(json.dumps({'error': error.code}, sort_keys=True), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError, MarketValueError, ProbeStepError):
        print(json.dumps({'error': 'research_command_failed'}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
