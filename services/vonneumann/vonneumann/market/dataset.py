"""Bounded immutable offline market archives, not provider authentication.

Version 1 uses UTF-8 JSON with sorted keys, compact separators and one final LF.
Only synthetic fixtures may be played by the offline replay adapter. Observed
provider archives are validation inputs, never a way to bypass live freshness.
Availability is evidence recorded in the archive; a hash proves byte integrity,
not that a provider supplied those bytes or that archive rights were granted.
No process-local monotonic clock, execution cursor or restart state is restored.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Iterable, Mapping

from .candles import MinuteCandle
from .feed import MarketFeedError

SCHEMA_VERSION = "market-dataset-v1"
MAX_FRAMES = 10_000
MAX_DATA_BYTES = 32 * 1024 * 1024
MAX_LINE_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAINNET_GENESIS_HASH = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
# Pinned identity table: importing live adapters would read ambient credentials.
TOKEN_MINTS = MappingProxyType({
    "SOL/USDC": "So11111111111111111111111111111111111111112",
    "JUP/USDC": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "BONK/USDC": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "WIF/USDC": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "JTO/USDC": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
    "PYTH/USDC": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "ORCA/USDC": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "RAY/USDC": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
})

_META_KEYS = frozenset({
    "source_kind", "network", "genesis_hash", "assets", "quote_provider",
    "candle_provider", "quote_currency", "volume_unit", "quote_volume_semantics",
    "source_time_semantics", "availability_semantics", "valuation_policy",
    "rights_basis", "warmup_minutes", "evaluation_start_at", "evaluation_end_at",
    "simulation_spec",
})
_FRAME_KEYS = frozenset({"seq", "observed_at", "quotes", "candles"})
_QUOTE_KEYS = frozenset({"asset", "price", "volume", "volume_unit", "source_time",
                         "received_at", "source_slot"})
_CANDLE_KEYS = frozenset({"asset", "start", "open", "high", "low", "close", "volume",
                          "source", "quote_currency", "volume_unit", "available_at"})
_SPEC_KEYS = frozenset({"model_version", "seed", "start_timestamp", "step_seconds",
                       "drift", "volatility", "volume_noise", "candle_model", "volume_unit"})
_ERROR_CODES = frozenset({"dataset_invalid", "dataset_limits", "dataset_integrity",
                        "dataset_path", "dataset_exists", "dataset_io",
                        "provider_replay_unsupported", "replay_window_unsupported"})


class DatasetError(ValueError):
    """Public errors never include paths, payload strings, or underlying errors."""

    def __init__(self, code: str = "dataset_invalid"):
        self.code = code if code in _ERROR_CODES else "dataset_invalid"
        super().__init__("Offline market dataset validation failed.")


def _fail(code="dataset_invalid"):
    raise DatasetError(code)


def _shape(value, keys):
    if not isinstance(value, dict) or set(value) != keys:
        _fail()


def _number(value, *, positive=False):
    if type(value) not in (int, float):
        _fail()
    try:
        result = float(value)
    except OverflowError:
        _fail()
    if not math.isfinite(result) or (result <= 0 if positive else result < 0):
        _fail()
    return result


def _integer(value, minimum=0, maximum=2**53 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _timestamp(value):
    result = _number(value)
    try:
        datetime.fromtimestamp(result, timezone.utc)
    except (ValueError, OverflowError, OSError):
        _fail()
    return result


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value, depth=0):
    if depth > 12:
        _fail("dataset_limits")
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            _fail()
        return {key: _plain(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item, depth + 1) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    _fail()


def canonical_bytes(value) -> bytes:
    """Versioned bundle encoding; not a claim of RFC 8785 canonicalization."""
    try:
        return (json.dumps(_plain(value), sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError):
        _fail()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _json(raw):
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: _fail())
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        _fail()
    if canonical_bytes(value) != raw:
        _fail("dataset_integrity")
    return value


@dataclass(frozen=True)
class MarketDataset:
    manifest: Mapping
    frames: tuple[Mapping, ...]

    def __post_init__(self):
        # This is an immutable value container; load/write are the validation boundary.
        object.__setattr__(self, "manifest", _freeze(_plain(self.manifest)))
        object.__setattr__(self, "frames", tuple(_freeze(_plain(f)) for f in self.frames))

    @property
    def dataset_id(self) -> str:
        return hashlib.sha256(canonical_bytes(self.manifest)).hexdigest()


def _metadata(meta):
    _shape(meta, _META_KEYS)
    synthetic = meta["source_kind"] == "synthetic_fixture"
    if not synthetic and meta["source_kind"] != "provider_observations":
        _fail()
    expected = {
        "network": "synthetic" if synthetic else "solana-mainnet",
        "genesis_hash": None if synthetic else MAINNET_GENESIS_HASH,
        "quote_provider": "simulation-gbm-discrete-v1" if synthetic else "jupiter-price-v3",
        "candle_provider": "simulation-minute-endpoints-v1" if synthetic else "birdeye-ohlcv-v3",
        "quote_currency": "USD",
        "volume_unit": "synthetic_base_token" if synthetic else "base_token",
        "quote_volume_semantics": "synthetic_per_step" if synthetic else "unavailable_zero_placeholder",
        "source_time_semantics": "modeled_time" if synthetic else "estimated_block_time",
        "availability_semantics": "modeled" if synthetic else "recorded_receipt",
        "valuation_policy": "usd-reference-only-v1",
        "rights_basis": "synthetic_generated" if synthetic else "provider_archive_permission_reviewed",
    }
    if any(meta[key] != value for key, value in expected.items()):
        _fail()
    assets = meta["assets"]
    if not isinstance(assets, list) or not 1 <= len(assets) <= len(TOKEN_MINTS):
        _fail()
    names = []
    for entry in assets:
        _shape(entry, {"asset", "mint"})
        name = entry["asset"]
        if type(name) is not str or name not in TOKEN_MINTS or name in names:
            _fail()
        if entry["mint"] != ("synthetic:" + name.split("/")[0] if synthetic else TOKEN_MINTS[name]):
            _fail()
        names.append(name)
    _integer(meta["warmup_minutes"], maximum=MAX_FRAMES)
    start, end = (_timestamp(meta[key]) for key in ("evaluation_start_at", "evaluation_end_at"))
    if start > end:
        _fail()
    spec = meta["simulation_spec"]
    if synthetic:
        _shape(spec, _SPEC_KEYS)
        if (spec["model_version"] != "gbm-discrete-v1" or
                spec["candle_model"] != "minute-endpoints-v1" or
                spec["volume_unit"] != "synthetic_base_token"):
            _fail()
        seed = spec["seed"]
        if type(seed) is not str or not re.fullmatch(r"0|[1-9][0-9]{0,19}", seed) or int(seed) >= 2**64:
            _fail()
        origin = _timestamp(spec["start_timestamp"])
        if origin % 60 or type(spec["step_seconds"]) not in (int, float) or spec["step_seconds"] != 60:
            _fail()
        for key in ("volatility", "volume_noise"):
            _number(spec[key])
        volatility = _number(spec["volatility"])
        _number(volatility * volatility)
        if type(spec["drift"]) not in (int, float):
            _fail()
        _number(abs(spec["drift"]))
        _timestamp(origin + 60)
        if origin + 60 <= origin:
            _fail()
        if start < origin:
            _fail()
    elif spec is not None:
        _fail()
    return names, synthetic


class _Validator:
    def __init__(self, meta):
        self.names, self.synthetic = _metadata(meta)
        self.meta = meta
        self.count = 0
        self.first = None
        self.last = None
        self.quotes = {}
        self.candles = {name: {} for name in self.names}
        self.last_candle = {}
        self.warmup_delivered = {name: set() for name in self.names}

    def append(self, frame):
        _shape(frame, _FRAME_KEYS)
        if self.count >= MAX_FRAMES:
            _fail("dataset_limits")
        if _integer(frame["seq"]) != self.count:
            _fail()
        observed = _timestamp(frame["observed_at"])
        if self.last is not None and observed <= self.last:
            _fail()
        if self.synthetic and observed != self.meta["simulation_spec"]["start_timestamp"] + (self.count + 1) * 60:
            _fail()
        quotes, candles = frame["quotes"], frame["candles"]
        if not isinstance(quotes, list) or len(quotes) != len(self.names) or not isinstance(candles, list):
            _fail()
        for name, quote in zip(self.names, quotes):
            _shape(quote, _QUOTE_KEYS)
            if quote["asset"] != name or quote["volume_unit"] != self.meta["volume_unit"]:
                _fail()
            _number(quote["price"], positive=True)
            volume = _number(quote["volume"])
            source, received = _timestamp(quote["source_time"]), _timestamp(quote["received_at"])
            if not source <= received <= observed:
                _fail()
            slot = quote["source_slot"]
            if self.synthetic:
                if slot is not None or source != observed or received != observed:
                    _fail()
            else:
                _integer(slot)
                if volume != 0:
                    _fail()
            previous = self.quotes.get(name)
            if previous is not None:
                old_source, old_received, old_slot = previous
                if source < old_source or received < old_received:
                    _fail()
                if not self.synthetic and (slot < old_slot or (slot == old_slot and source != old_source)):
                    _fail()
            self.quotes[name] = source, received, slot
        last_key = None
        for row in candles:
            _shape(row, _CANDLE_KEYS)
            name = row["asset"]
            if type(name) is not str or name not in self.candles:
                _fail()
            start = _integer(row["start"])
            _timestamp(start)
            _timestamp(start + 60)
            key = self.names.index(name), start
            if last_key is not None and key <= last_key:
                _fail()
            last_key = key
            if (row["source"] != self.meta["candle_provider"] or
                    row["quote_currency"] != self.meta["quote_currency"] or
                    row["volume_unit"] != self.meta["volume_unit"]):
                _fail()
            available = _timestamp(row["available_at"])
            if not start + 60 <= available <= observed:
                _fail()
            try:
                MinuteCandle(**{key: value for key, value in row.items() if key != "available_at"})
            except (MarketFeedError, TypeError, ValueError, OverflowError):
                _fail()
            if start in self.candles[name]:
                if self.candles[name][start] != row:
                    _fail()
                continue
            if name in self.last_candle and start != self.last_candle[name] + 60:
                _fail()
            self.candles[name][start] = row
            self.last_candle[name] = start
            if observed <= self.meta["evaluation_start_at"]:
                self.warmup_delivered[name].add(start)
        self.first = observed if self.first is None else self.first
        self.last = observed
        self.count += 1

    def finish(self):
        if not self.count:
            _fail()
        origin = self.meta["simulation_spec"]["start_timestamp"] if self.synthetic else self.first
        start, end = self.meta["evaluation_start_at"], self.meta["evaluation_end_at"]
        if not origin <= start <= end <= self.last:
            _fail()
        warmup = self.meta["warmup_minutes"]
        if warmup:
            boundary = math.floor(start / 60) * 60
            for name in self.names:
                if any(minute not in self.warmup_delivered[name]
                       for minute in range(boundary - warmup * 60, boundary, 60)):
                    _fail()


def _path_parts(path):
    try:
        value = os.fspath(path)
        if type(value) is not str or not value or "\x00" in value:
            _fail("dataset_path")
        parsed = Path(value)
        if ".." in parsed.parts:
            _fail("dataset_path")
        parts = [part for part in parsed.parts if part not in ("/", ".")]
        if not parts:
            _fail("dataset_path")
        return parsed.is_absolute(), parts
    except (ValueError, TypeError):
        _fail("dataset_path")


def _directory(path, *, parent=False):
    absolute, parts = _path_parts(path)
    target = parts[:-1] if parent else parts
    descriptor = None
    try:
        descriptor = os.open("/" if absolute else ".", os.O_RDONLY | os.O_DIRECTORY)
        for part in target:
            next_descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, parts[-1]
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        _fail("dataset_path")


def _read_file(directory, name, limit):
    descriptor = None
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            _fail("dataset_path")
        if info.st_size > limit:
            _fail("dataset_limits")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            data = stream.read(limit + 1)
        if len(data) > limit:
            _fail("dataset_limits")
        return data
    except OSError:
        _fail("dataset_path")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _manifest(metadata, validator, content):
    return {"schema_version": SCHEMA_VERSION, "metadata": metadata,
            "frames": {"file": "frames.jsonl", "sha256": hashlib.sha256(content).hexdigest(),
                       "count": validator.count, "first_observed_at": validator.first,
                       "last_observed_at": validator.last}}


def load_dataset(path) -> MarketDataset:
    """Load an exact two-file regular bundle; reject symlinks in every component."""
    directory, _ = _directory(path)
    try:
        names = set()
        with os.scandir(directory) as entries:
            for entry in entries:
                names.add(entry.name)
                if len(names) > 2:
                    _fail("dataset_path")
        if names != {"manifest.json", "frames.jsonl"}:
            _fail("dataset_path")
        manifest = _json(_read_file(directory, "manifest.json", MAX_MANIFEST_BYTES))
        _shape(manifest, {"schema_version", "metadata", "frames"})
        if manifest["schema_version"] != SCHEMA_VERSION:
            _fail()
        header = manifest["frames"]
        _shape(header, {"file", "sha256", "count", "first_observed_at", "last_observed_at"})
        if header["file"] != "frames.jsonl" or type(header["sha256"]) is not str or not re.fullmatch("[0-9a-f]{64}", header["sha256"]):
            _fail()
        _integer(header["count"], minimum=1, maximum=MAX_FRAMES)
        _timestamp(header["first_observed_at"])
        _timestamp(header["last_observed_at"])
        content = _read_file(directory, "frames.jsonl", MAX_DATA_BYTES)
        if hashlib.sha256(content).hexdigest() != header["sha256"]:
            _fail("dataset_integrity")
        validator = _Validator(manifest["metadata"])
        frames = []
        # splitlines keeps terminators so a missing final LF is not silently fixed.
        for raw in content.splitlines(keepends=True):
            if len(raw) > MAX_LINE_BYTES:
                _fail("dataset_limits")
            frame = _json(raw)
            validator.append(frame)
            frames.append(frame)
        validator.finish()
        if manifest != _manifest(manifest["metadata"], validator, content):
            _fail("dataset_integrity")
        return MarketDataset(manifest, tuple(frames))
    except OSError:
        _fail("dataset_io")
    finally:
        os.close(directory)


def write_dataset(path, metadata: Mapping, frames: Iterable[Mapping]) -> MarketDataset:
    """Validate everything before exclusive creation; never replace any target.

    The manifest is published last. A failed write can leave a new incomplete
    directory, which loaders reject; it never exposes a valid partial dataset.
    No rollback deletes files whose ownership might have changed concurrently.
    """
    meta = _plain(metadata)
    if len(canonical_bytes(meta)) > MAX_MANIFEST_BYTES:
        _fail("dataset_limits")
    validator = _Validator(meta)
    accepted, chunks, size = [], [], 0
    try:
        iterator = iter(frames)
    except TypeError:
        _fail()
    for frame in iterator:
        if validator.count >= MAX_FRAMES:
            _fail("dataset_limits")
        row = _plain(frame)
        raw = canonical_bytes(row)
        size += len(raw)
        if len(raw) > MAX_LINE_BYTES or size > MAX_DATA_BYTES:
            _fail("dataset_limits")
        validator.append(row)
        accepted.append(row)
        chunks.append(raw)
    validator.finish()
    content = b"".join(chunks)
    manifest = _manifest(meta, validator, content)
    manifest_bytes = canonical_bytes(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        _fail("dataset_limits")
    result = MarketDataset(manifest, tuple(accepted))
    parent, name = _directory(path, parent=True)
    directory = None
    try:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            _fail("dataset_exists")
        directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        for filename, data in (("frames.jsonl", content), ("manifest.json", manifest_bytes)):
            descriptor = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        os.fsync(directory)
        os.fsync(parent)
    except OSError:
        _fail("dataset_io")
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)
    return result
