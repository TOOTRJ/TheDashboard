"""Bounded, immutable local research result bundles.

Hashes establish byte integrity and content identity, not correct trading
semantics or authentic market observations. The runner owns semantic validation
and reproduction against its bound dataset. This module reads no configuration,
credentials, database, or network service.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Mapping


PAYLOAD_VERSION = "ema-research-v1"
ARTIFACT_VERSION = "ema-research-artifact-v1"
MAX_RESULT_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_DEPTH = 20
_CODES = frozenset({"research_invalid", "research_limits", "research_integrity",
                    "research_path", "research_exists", "research_io"})


class ResearchArtifactError(ValueError):
    """Safe public errors never interpolate payloads, paths or OS messages."""

    def __init__(self, code: str = "research_invalid"):
        self.code = code if isinstance(code, str) and code in _CODES else "research_invalid"
        super().__init__("Offline research artifact validation failed.")


def _fail(code="research_invalid"):
    raise ResearchArtifactError(code) from None


def plain_data(value, _depth=0):
    """Return detached finite JSON data, accepting immutable mappings/tuples.

    Depth is measured from the root at zero. Integer values retain their type
    and exact value, but must also fit a finite floating-point numeric domain.
    This rejects enormous numeric literals instead of admitting JSON infinity
    when a downstream numerical consumer converts them.
    """
    if _depth > MAX_DEPTH:
        _fail("research_limits")
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            _fail()
        return {key: plain_data(item, _depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain_data(item, _depth + 1) for item in value]
    if value is None or type(value) in (str, bool):
        return value
    if type(value) in (int, float):
        try:
            finite = math.isfinite(float(value))
        except (OverflowError, ValueError):
            _fail()
        if finite:
            return value
    _fail()


def _encode(value, limit):
    try:
        encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=True, allow_nan=False)
        chunks, size = [], 1  # The final LF is part of the content hash.
        for part in encoder.iterencode(value):
            raw = part.encode("ascii")
            size += len(raw)
            if size > limit:
                _fail("research_limits")
            chunks.append(raw)
        return b"".join(chunks) + b"\n"
    except ResearchArtifactError:
        raise
    except (ValueError, TypeError, OverflowError, RecursionError):
        _fail()


def canonical_bytes(value):
    """The versioned sorted compact ASCII/LF encoding; not RFC 8785."""
    return _encode(plain_data(value), MAX_RESULT_BYTES)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _json(raw, limit):
    try:
        value = json.loads(raw.decode("ascii"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: _fail())
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        _fail()
    value = plain_data(value)
    if _encode(value, limit) != raw:
        _fail("research_integrity")
    return value


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ResearchResult:
    """Immutable value container; load/write are the integrity boundaries."""

    payload: Mapping
    manifest: Mapping

    def __post_init__(self):
        object.__setattr__(self, "payload", _freeze(plain_data(self.payload)))
        object.__setattr__(self, "manifest", _freeze(plain_data(self.manifest)))

    @property
    def result_id(self) -> str:
        return hashlib.sha256(_encode(plain_data(self.manifest), MAX_MANIFEST_BYTES)).hexdigest()


def _payload(value):
    if not isinstance(value, dict) or value.get("schema_version") != PAYLOAD_VERSION:
        _fail()


def _manifest(content):
    return {"schema_version": ARTIFACT_VERSION,
            "payload": {"file": "result.json", "bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest()}}


def _validate_manifest(value):
    if (not isinstance(value, dict) or set(value) != {"schema_version", "payload"}
            or value["schema_version"] != ARTIFACT_VERSION):
        _fail()
    info = value["payload"]
    if (not isinstance(info, dict) or set(info) != {"file", "bytes", "sha256"}
            or info["file"] != "result.json"
            or type(info["bytes"]) is not int or info["bytes"] < 1
            or type(info["sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", info["sha256"]) is None):
        _fail()
    if info["bytes"] > MAX_RESULT_BYTES:
        _fail("research_limits")


def _path_parts(path):
    try:
        value = os.fspath(path)
        if type(value) is not str or not value or "\x00" in value:
            _fail("research_path")
        os.fsencode(value)
        parsed = Path(value)
        if ".." in parsed.parts:
            _fail("research_path")
        parts = [part for part in parsed.parts if part not in ("/", ".")]
        if not parts:
            _fail("research_path")
        return parsed.is_absolute(), parts
    except (ValueError, TypeError):
        _fail("research_path")


def _directory(path, *, parent=False):
    absolute, parts = _path_parts(path)
    descriptor = None
    try:
        descriptor = os.open("/" if absolute else ".", os.O_RDONLY | os.O_DIRECTORY)
        for part in (parts[:-1] if parent else parts):
            next_descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, parts[-1]
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        _fail("research_path")


def _read_file(directory, filename, limit):
    descriptor = None
    try:
        descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            _fail("research_path")
        if info.st_size > limit:
            _fail("research_limits")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            _fail("research_limits")
        return raw
    except OSError:
        _fail("research_path")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def load_result(path) -> ResearchResult:
    """Verify the exact two regular files, canonical bytes, lengths and hashes."""
    directory, _ = _directory(path)
    try:
        names = set()
        with os.scandir(directory) as entries:
            for entry in entries:
                names.add(entry.name)
                if len(names) > 2:
                    _fail("research_path")
        if names != {"manifest.json", "result.json"}:
            _fail("research_path")
        manifest = _json(_read_file(directory, "manifest.json", MAX_MANIFEST_BYTES), MAX_MANIFEST_BYTES)
        _validate_manifest(manifest)
        content = _read_file(directory, "result.json", MAX_RESULT_BYTES)
        if manifest != _manifest(content):
            _fail("research_integrity")
        payload = _json(content, MAX_RESULT_BYTES)
        _payload(payload)
        return ResearchResult(payload, manifest)
    except OSError:
        _fail("research_io")
    finally:
        os.close(directory)


def write_result(path, new_payload: Mapping) -> ResearchResult:
    """Validate before exclusive creation and publish the manifest last.

    A failed write may leave this newly created directory incomplete; loading
    refuses it. We never delete a path on failure, replace an existing output,
    follow a symlink, or try to repair someone else's partial bundle.
    """
    payload = plain_data(new_payload)
    _payload(payload)
    content = _encode(payload, MAX_RESULT_BYTES)
    manifest = _manifest(content)
    manifest_bytes = _encode(manifest, MAX_MANIFEST_BYTES)
    result = ResearchResult(payload, manifest)
    parent, name = _directory(path, parent=True)
    directory = None
    try:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            _fail("research_exists")
        directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        for filename, raw in (("result.json", content), ("manifest.json", manifest_bytes)):
            descriptor = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        os.fsync(directory)
        os.fsync(parent)
    except OSError:
        _fail("research_io")
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)
    return result
