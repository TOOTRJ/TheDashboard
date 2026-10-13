#!/usr/bin/env python3
"""Prepare a fresh hosted wheel bundle; independently validate it without I/O services."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
from email.policy import default
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

from packaging.tags import compatible_tags, cpython_tags, parse_tag
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/check-ci-native-wheels.py"
LOCK = ROOT / "services/vonneumann/requirements-dev.txt"
NAME = "dashboard-native-wheels"
SCHEMA = "dashboard-native-wheels-v1"
MAX_BYTES = 150 * 1024 * 1024
MAX_FILES = 200
MAX_MANIFEST = 512 * 1024
SUPPORTED_PYTHON = (3, 12, 14)
# Debian Bookworm has glibc 2.36. Explicit cross-platform download constraints
# exclude Ubuntu 24.04's glibc 2.39 and unconstrained linux/musllinux binaries.
PLATFORMS = tuple(f"manylinux_2_{minor}_x86_64" for minor in range(36, 4, -1)) + (
    "manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64",
)
ABIS = ("cp312", "abi3", "none")
TARGET = {"python": "3.12.14", "implementation": "cpython", "os": "linux",
          "architecture": "amd64", "glibc_max": "2.36",
          "platforms": list(PLATFORMS), "abis": list(ABIS)}
TAGS = frozenset(cpython_tags((3, 12), abis=ABIS, platforms=PLATFORMS)) | frozenset(
    compatible_tags((3, 12), interpreter="cp312", platforms=PLATFORMS))
PRIVATE_PARTS = {"ssl", ".git", ".vercel", ".aws", ".codex", ".claude"}


def _path(value) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise RuntimeError("Native wheel bundle needs an explicit absolute path")
    path = Path(value)
    if (not path.is_absolute() or path.resolve() != path
            or any(part in PRIVATE_PARTS or part.startswith(".env") for part in path.parts)):
        raise RuntimeError("Native wheel paths must be canonical and cannot use links or private paths")
    return path


def _owned(path: Path, kind: str, mode: int | None = None):
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if kind == "directory" else stat.S_ISREG(info.st_mode)
    if (not valid or info.st_uid != os.getuid()
            or (kind != "directory" and info.st_nlink != 1)
            or (mode is not None and stat.S_IMODE(info.st_mode) != mode)):
        raise RuntimeError("Native wheel fixture has invalid file type, owner, links or permissions")
    return info


def _public_bytes(path: Path, bound: int) -> bytes:
    path = _path(path)
    if not path.is_relative_to(ROOT) or not stat.S_ISREG(path.lstat().st_mode):
        raise RuntimeError("Native wheel binding needs the reviewed public repository files")
    with path.open("rb") as stream:
        result = stream.read(bound + 1)
    if len(result) > bound:
        raise RuntimeError("Native wheel binding exceeds its input bound")
    return result


def locked_packages() -> dict:
    """Admit only this fully resolved lock's pinned names, versions and SHA-256s."""
    packages, pending = {}, ""
    for raw in _public_bytes(LOCK, 2 * 1024 * 1024).decode("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "--only-binary :all:" and not pending:
            continue
        continuation = line.endswith("\\")
        pending += " " + (line[:-1].strip() if continuation else line)
        if continuation:
            continue
        match = re.fullmatch(r" ([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s]+)((?: --hash=sha256:[a-f0-9]{64})+)", pending)
        if not match:
            raise RuntimeError("Native wheel lock must contain only exact hash-required pins")
        name, version = canonicalize_name(match[1]), str(Version(match[2]))
        if name in packages:
            raise RuntimeError("Native wheel lock duplicates a package")
        packages[name] = {"version": version, "hashes": set(re.findall(r"sha256:([a-f0-9]{64})", match[3]))}
        pending = ""
    if pending or not packages or len(packages) > MAX_FILES:
        raise RuntimeError("Native wheel lock is empty, incomplete or too large")
    return packages


def _metadata(archive: zipfile.ZipFile, info, bound: int) -> bytes:
    if info.file_size < 1 or info.file_size > bound or info.flag_bits & 1:
        raise RuntimeError("Native wheel metadata exceeds its bounded plain format")
    with archive.open(info) as stream:
        data = stream.read(bound + 1)
    if len(data) != info.file_size or len(data) > bound:
        raise RuntimeError("Native wheel metadata length does not match")
    return data


def _wheel_metadata(path: Path, name, version, filename_tags) -> None:
    # The entire archive hash has already matched the reviewed lock. Read only
    # bounded WHEEL/METADATA members, never extract or execute wheel contents.
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 10000 or len({entry.filename for entry in entries}) != len(entries):
            raise RuntimeError("Native wheel has excessive or duplicate ZIP members")
        wheel = [entry for entry in entries if entry.filename.endswith(".dist-info/WHEEL")]
        metadata = [entry for entry in entries if entry.filename.endswith(".dist-info/METADATA")]
        if (len(wheel) != 1 or len(metadata) != 1
                or wheel[0].filename.rsplit("/", 1)[0] != metadata[0].filename.rsplit("/", 1)[0]):
            raise RuntimeError("Native wheel has ambiguous distribution metadata")
        prefix = wheel[0].filename.rsplit("/", 1)[0]
        if "/" in prefix or "\\" in prefix or "\x00" in prefix:
            raise RuntimeError("Native wheel metadata cannot use nested or traversing paths")
        distribution, prefix_version = prefix[:-len(".dist-info")].rsplit("-", 1)
        if canonicalize_name(distribution) != name or Version(prefix_version) != version:
            raise RuntimeError("Native wheel metadata directory disagrees with its filename")
        parsed_wheel = BytesParser(policy=default).parsebytes(_metadata(archive, wheel[0], 64 * 1024))
        parsed_metadata = BytesParser(policy=default).parsebytes(_metadata(archive, metadata[0], 1024 * 1024))
        tags = frozenset(tag for value in parsed_wheel.get_all("Tag", []) for tag in parse_tag(value))
        if tags != filename_tags or not tags & TAGS:
            raise RuntimeError("Native wheel internal tags disagree with its compatible filename")
        names, versions = parsed_metadata.get_all("Name", []), parsed_metadata.get_all("Version", [])
        if (len(names) != 1 or len(versions) != 1 or canonicalize_name(names[0]) != name
                or Version(versions[0]) != version):
            raise RuntimeError("Native wheel internal package identity disagrees with its locked pin")
        requires_python = parsed_metadata.get_all("Requires-Python", [])
        if (len(requires_python) > 1 or (requires_python
                and Version(TARGET["python"]) not in SpecifierSet(requires_python[0]))):
            raise RuntimeError("Native wheel metadata requires an unsupported Python version")


def wheel_records(directory: Path) -> list[dict]:
    packages = locked_packages()
    entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
    if len(entries) != len(packages) or len(entries) > MAX_FILES:
        raise RuntimeError("Native wheel bundle must contain exactly every locked package once")
    records, seen, total = [], set(), 0
    for path in entries:
        _path(path)
        info = _owned(path, "file", 0o600)
        if not path.name.endswith(".whl") or info.st_size < 1:
            raise RuntimeError("Native wheel bundle contains a nonwheel or empty file")
        total += info.st_size
        if total > MAX_BYTES:
            raise RuntimeError("Native wheel bundle exceeds 150 MiB")
        name, version, _, tags = parse_wheel_filename(path.name)
        if name not in packages or name in seen or str(version) != packages[name]["version"] or not tags & TAGS:
            raise RuntimeError("Native wheel filename is duplicate, unpinned or incompatible with Bookworm CPython")
        digest = hashlib.sha256()
        hashed_bytes = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hashed_bytes += len(chunk)
                if hashed_bytes > info.st_size:
                    raise RuntimeError("Native wheel changed during bounded hashing")
                digest.update(chunk)
        if hashed_bytes != info.st_size or digest.hexdigest() not in packages[name]["hashes"]:
            raise RuntimeError("Native wheel archive does not match a reviewed lock hash")
        _wheel_metadata(path, name, version, tags)
        seen.add(name)
        records.append({"filename": path.name, "name": name, "version": str(version),
                        "sha256": digest.hexdigest(), "bytes": info.st_size})
    if seen != set(packages):
        raise RuntimeError("Native wheel bundle is missing a locked package")
    return records


def manifest_path(directory: Path) -> Path:
    return directory.with_name(NAME + ".manifest.json")


def bundle_manifest(directory: Path, records: list[dict]) -> dict:
    return {"schema": SCHEMA, "directory": str(directory), "target": TARGET,
            "lock_sha256": hashlib.sha256(_public_bytes(LOCK, 2 * 1024 * 1024)).hexdigest(),
            "helper_sha256": hashlib.sha256(_public_bytes(HELPER, 512 * 1024)).hexdigest(),
            "files": records}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeError("Native wheel manifest cannot have duplicate keys")
        result[key] = value
    return result


def _bundle_directory(directory: Path | str) -> Path:
    directory = _path(directory)
    if directory.name != NAME:
        raise RuntimeError("Native wheel directory must use the reviewed fixture name")
    _owned(directory, "directory", 0o700)
    parent = _owned(directory.parent, "directory")
    if stat.S_IMODE(parent.st_mode) & 0o022:
        raise RuntimeError("Native wheel parent cannot be writable by other users")
    return directory


def validate_bundle(directory: Path | str) -> Path:
    """Pure validation for the SQL parent and sanitized child, including local callers."""
    directory = _bundle_directory(directory)
    sidecar = _path(manifest_path(directory))
    if not sidecar.exists():
        raise RuntimeError("Native wheel bundle needs the current reviewed sibling manifest; legacy loose wheels are unsupported")
    info = _owned(sidecar, "file", 0o600)
    if info.st_size < 1 or info.st_size > MAX_MANIFEST:
        raise RuntimeError("Native wheel manifest exceeds its input bound")
    manifest = json.loads(sidecar.read_bytes(), object_pairs_hook=_unique_object)
    if manifest != bundle_manifest(directory, wheel_records(directory)):
        raise RuntimeError("Native wheel manifest is stale or does not bind the current lock, helper, target and exact files")
    return directory


def _publish_manifest(directory: Path, records: list[dict]) -> None:
    sidecar = manifest_path(directory)
    content = json.dumps(bundle_manifest(directory, records), sort_keys=True, separators=(",", ":")).encode()
    if len(content) > MAX_MANIFEST:
        raise RuntimeError("Native wheel manifest exceeds its publication bound")
    descriptor = os.open(sidecar, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        validate_bundle(directory)
    except BaseException:
        sidecar.unlink()
        raise


def record_existing(directory: Path | str) -> Path:
    """Record only an already manually prepared owned local-temporary wheel bundle."""
    directory = _bundle_directory(directory)
    temporary_roots = (Path(tempfile.gettempdir()).resolve(),
                       Path("/private/tmp") if sys.platform == "darwin" else Path("/tmp"))
    if not any(directory.is_relative_to(root) for root in temporary_roots):
        raise RuntimeError("Existing native wheel recording is restricted to an explicit owned temporary fixture")
    if manifest_path(directory).exists() or manifest_path(directory).is_symlink():
        raise RuntimeError("Native wheel recording refuses to replace an existing manifest")
    _publish_manifest(directory, wheel_records(directory))
    print(json.dumps({"scope": "local-native-wheel-manifest-only", "directory": str(directory)}, sort_keys=True))
    return directory


def prepare(destination: Path | str, inherited: dict[str, str]) -> Path:
    """Download only to this fresh exact fixture on the disposable Dashboard runner."""
    if (inherited.get("GITHUB_ACTIONS") != "true" or inherited.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or inherited.get("GITHUB_REPOSITORY_ID") != "1141090963"):
        raise RuntimeError("Native wheel preparation is restricted to the Dashboard GitHub-hosted runner")
    if (tuple(sys.version_info[:3]) != SUPPORTED_PYTHON or sys.implementation.name != "cpython"
            or sys.platform != "linux" or platform.machine() != "x86_64"):
        raise RuntimeError("Native wheel preparation requires Linux amd64 CPython 3.12.14")
    parent = _path(inherited.get("RUNNER_TEMP"))
    info = _owned(parent, "directory")
    destination = _path(destination)
    if destination != parent / NAME or stat.S_IMODE(info.st_mode) & 0o022:
        raise RuntimeError("Native wheel preparation requires its exact owned runner-temporary destination")
    sidecar = manifest_path(destination)
    if destination.exists() or sidecar.exists() or destination.is_symlink() or sidecar.is_symlink():
        raise RuntimeError("Native wheel preparation refuses an existing destination or manifest")
    locked_packages()  # Refuse unexpected lock directives before any process/network I/O.
    destination.mkdir(mode=0o700)
    command = [sys.executable, "-m", "pip", "download", "--disable-pip-version-check", "--no-input",
               "--require-hashes", "--only-binary=:all:", "--no-cache-dir", "--index-url", "https://pypi.org/simple",
               "--dest", str(destination), "--python-version", "3.12.14", "--implementation", "cp"]
    for abi in ABIS:
        command.extend(("--abi", abi))
    for target_platform in PLATFORMS:
        command.extend(("--platform", target_platform))
    command.extend(("-r", str(LOCK)))
    env = {"PATH": os.defpath, "TMPDIR": str(parent), "LANG": "C", "LC_ALL": "C", "PYTHONUTF8": "1",
           "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1", "PIP_CONFIG_FILE": os.devnull,
           "PIP_NO_INPUT": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=240, check=False)
        if result.returncode:
            raise RuntimeError("Hash-required Bookworm wheel download failed")
        for path in destination.iterdir():
            _path(path)
            _owned(path, "file")
            path.chmod(0o600)
        records = wheel_records(destination)
        _publish_manifest(destination, records)
    except BaseException:
        shutil.rmtree(destination)
        raise
    print(json.dumps({"scope": "github-hosted-native-wheels", "packages": len(records),
                      "bytes": sum(record["bytes"] for record in records), "target": TARGET,
                      "lock_sha256": hashlib.sha256(_public_bytes(LOCK, 2 * 1024 * 1024)).hexdigest()}, sort_keys=True))
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--destination", help="Download to the fresh exact hosted-runner fixture")
    actions.add_argument("--record-existing", help="Validate an owned temporary wheel fixture and create only its absent sibling manifest")
    args = parser.parse_args()
    if args.record_existing:
        record_existing(args.record_existing)
    else:
        prepare(args.destination, dict(os.environ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
