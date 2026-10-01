"""Local, credential-free validation and generation of immutable market fixtures.

This command does not start a worker or evaluate strategies. Synthetic fixtures
describe the existing discrete simulation model, not observed executable prices.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys
from typing import Iterator

from ..core.market_validation import MarketValueError
from ..core.search_random import validate_search_seed
from .dataset import MAX_FRAMES, DatasetError, MarketDataset, load_dataset, write_dataset
from .feed import MarketFeedError
from .sim_feed import BASE_PRICES, SimulationFeed


def _seed(value: str) -> str:
    try:
        return validate_search_seed(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "seed must be canonical decimal text from 0 through 18446744073709551615"
        ) from None


def _frame_count(value: str) -> int:
    if (re.fullmatch(r"[1-9][0-9]{0,9}", value) is None or
            not 1 <= int(value) <= MAX_FRAMES):
        raise argparse.ArgumentTypeError(f"frames must be an integer from 1 through {MAX_FRAMES}")
    return int(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate an existing local dataset bundle")
    validate.add_argument("path", type=Path, help="local dataset directory")
    generate = commands.add_parser("generate-synthetic", help="create a new synthetic fixture bundle")
    generate.add_argument("--output", type=Path, required=True, help="new local directory; never overwritten")
    generate.add_argument("--frames", type=_frame_count, required=True,
                          help=f"number of one-minute frames (1–{MAX_FRAMES})")
    generate.add_argument("--assets", nargs="+", required=True,
                          help="space-separated supported symbols, such as SOL/USDC JUP/USDC")
    generate.add_argument("--seed", type=_seed, default="0", help="canonical unsigned 64-bit decimal text")
    return parser


async def _next_frame(feed: SimulationFeed, assets: list[str], sequence: int) -> dict:
    ticks = await feed.get_ticks(assets)
    candles = await feed.get_candles(assets)
    observed_at = feed.current_timestamp
    return {
        "seq": sequence,
        "observed_at": observed_at,
        "quotes": [
            {"asset": asset, "price": ticks[asset].price, "volume": ticks[asset].volume,
             "source_time": ticks[asset].timestamp, "received_at": observed_at, "source_slot": None,
             "volume_unit": "synthetic_base_token"}
            for asset in assets
        ],
        "candles": [{**asdict(candle), "available_at": observed_at} for candle in candles],
    }


def _frames(feed: SimulationFeed, assets: list[str], count: int) -> Iterator[dict]:
    # A private event loop advances the existing feed once per output frame.
    # The writer consumes this bounded stream; no provider/client is imported.
    with asyncio.Runner() as runner:
        for sequence in range(count):
            yield runner.run(_next_frame(feed, assets, sequence))


def _generate_synthetic_dataset(path: Path, *, frames: int, assets: list[str], seed: str) -> MarketDataset:
    """Validate command inputs before computing frames or publishing any files."""
    if isinstance(frames, bool) or not isinstance(frames, int) or not 1 <= frames <= MAX_FRAMES:
        raise ValueError("invalid_frame_count")
    seed = validate_search_seed(seed)
    if (not isinstance(assets, list) or not assets or len(assets) > len(BASE_PRICES) or
            any(not isinstance(asset, str) or asset not in BASE_PRICES for asset in assets) or
            len(set(assets)) != len(assets)):
        raise ValueError("invalid_assets")
    assets = sorted(assets)
    feed = SimulationFeed(seed=int(seed))
    spec = feed.simulation_spec
    metadata = {
        "source_kind": "synthetic_fixture",
        "network": "synthetic",
        "genesis_hash": None,
        "assets": [{"asset": asset, "mint": f"synthetic:{asset.split('/')[0]}"} for asset in assets],
        "quote_provider": "simulation-gbm-discrete-v1",
        "candle_provider": "simulation-minute-endpoints-v1",
        "quote_currency": "USD",
        "volume_unit": "synthetic_base_token",
        "quote_volume_semantics": "synthetic_per_step",
        "source_time_semantics": "modeled_time",
        "availability_semantics": "modeled",
        "valuation_policy": "usd-reference-only-v1",
        "rights_basis": "synthetic_generated",
        "warmup_minutes": 0,
        "evaluation_start_at": spec["start_timestamp"],
        "evaluation_end_at": spec["start_timestamp"] + frames * spec["step_seconds"],
        "simulation_spec": spec,
    }
    return write_dataset(path, metadata, _frames(feed, assets, frames))


async def generate_synthetic_dataset(
    path: Path, *, frames: int, assets: list[str], seed: str
) -> MarketDataset:
    """Generate a bounded fixture without blocking an existing caller event loop."""
    return await asyncio.to_thread(
        _generate_synthetic_dataset, path, frames=frames, assets=assets, seed=seed
    )


def _summary(dataset: MarketDataset) -> dict:
    """Only declared metadata is printed; never raw observations or file contents."""
    manifest = dataset.manifest
    metadata = manifest["metadata"]
    frames = manifest["frames"]
    candle_starts = {item["asset"]: set() for item in metadata["assets"]}
    for frame in dataset.frames:
        for candle in frame["candles"]:
            candle_starts[candle["asset"]].add(candle["start"])
    coverage = {
        asset: {"count": len(starts), "first_start": min(starts) if starts else None,
                "last_end": max(starts) + 60 if starts else None}
        for asset, starts in candle_starts.items()
    }
    return {
        "dataset_id": dataset.dataset_id,
        "schema_version": manifest["schema_version"],
        "source_kind": metadata["source_kind"],
        "network": metadata["network"],
        "assets": [item["asset"] for item in metadata["assets"]],
        "frame_count": frames["count"],
        "first_observed_at": frames["first_observed_at"],
        "last_observed_at": frames["last_observed_at"],
        "quote_currency": metadata["quote_currency"],
        "volume_unit": metadata["volume_unit"],
        "availability_semantics": metadata["availability_semantics"],
        "candle_coverage": coverage,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "generate-synthetic":
        if (any(asset not in BASE_PRICES for asset in arguments.assets) or
                len(set(arguments.assets)) != len(arguments.assets)):
            parser.error("assets must be distinct supported simulation symbols")
    try:
        if arguments.command == "validate":
            dataset = load_dataset(arguments.path)
        else:
            dataset = asyncio.run(generate_synthetic_dataset(
                arguments.output, frames=arguments.frames,
                assets=arguments.assets, seed=arguments.seed))
    except DatasetError as error:
        print(json.dumps({"error": error.code}, sort_keys=True), file=sys.stderr)
        return 1
    except (OSError, ValueError, MarketValueError, MarketFeedError):
        print(json.dumps({"error": "dataset_command_failed"}), file=sys.stderr)
        return 1
    print(json.dumps(_summary(dataset), sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
