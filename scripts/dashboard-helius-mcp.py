#!/usr/bin/env python3
"""Launch only the reviewed Dashboard Helius MCP with isolated local state.

This verifies the installed artifact, not a provider account or trading readiness.
Tool filtering belongs to the project MCP client configuration. The upstream
server still registers mutation tools; a preload suppresses its reviewed
telemetry endpoint. See HELIUS-TOOLING.md for the bounded scope of that guard.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


ROOT = Path('/Users/redjester/Projects/Next/TheDashboard')
VERSION = '2.3.0'
NODE_SHA256 = '27db838bb204ef7c21df2931f5656e4c8fb32e6e947f363a402b49714d32b5b1'
LOCK_SHA256 = '065fb9500e575103b2edc5c0dab4f63c0f2d620d1044d2a06c577488e000d811'
MANIFEST_SHA256 = '4ba1ca4dc58a75f58997bab30d4f5d9c50e4419a5374df4b6cb1f187f6566659'
ENABLED_TOOLS = (
    'heliusWallet', 'heliusAsset', 'heliusTransaction', 'heliusChain',
    'heliusCompression', 'expandResult',
)


class Refused(RuntimeError):
    """A deliberately secret-free operator error."""


def owned_directory(path: Path, *, private: bool = False) -> None:
    try:
        info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or path.resolve() != path
                or (stat.S_IMODE(info.st_mode) != 0o700 if private
                    else info.st_mode & 0o022)):
            raise ValueError()
    except (OSError, ValueError):
        raise Refused('Dashboard Helius directory ownership, permissions or path mismatch') from None


def read_owned(path: Path, *, maximum: int, mode: int | None = None) -> bytes:
    """Inspect the opened descriptor; refuse links, devices, shared or large files."""
    try:
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            directory = os.fstat(parent)
            if directory.st_uid != os.getuid() or directory.st_mode & 0o022:
                raise ValueError()
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        finally:
            os.close(parent)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or info.st_size > maximum
                    or (mode is not None and stat.S_IMODE(info.st_mode) != mode)
                    or (mode is None and info.st_mode & 0o022)):
                raise ValueError()
            raw = source.read(maximum + 1)
            if len(raw) > maximum:
                raise ValueError()
            return raw
    except (OSError, ValueError):
        raise Refused('Dashboard Helius file unavailable or ownership, type, size or permissions invalid') from None


def read_key(root: Path = ROOT) -> str:
    """Read exactly one private key assignment, never a general dotenv file."""
    owned_directory(root)
    owned_directory(root / 'ssl')
    raw = read_owned(root / 'ssl/helius-mcp.env', maximum=4096, mode=0o600)
    try:
        text = raw.decode('ascii')
    except UnicodeError:
        raise Refused('Dashboard Helius key file must contain only HELIUS_API_KEY=<key>') from None
    assignments = [line.strip() for line in text.splitlines()
                   if line.strip() and not line.lstrip().startswith('#')]
    match = (re.fullmatch(r'HELIUS_API_KEY=([A-Za-z0-9_-]{16,256})', assignments[0])
             if len(assignments) == 1 else None)
    if not match:
        raise Refused('Dashboard Helius key file must contain only HELIUS_API_KEY=<key>')
    return match.group(1)


def module_inventory(runtime: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Hash the complete installed tree, including its exact relative bin links."""
    modules = runtime / 'node_modules'
    owned_directory(modules)
    files: dict[str, str] = {}
    links: dict[str, str] = {}
    for folder, directories, names in os.walk(modules, followlinks=False):
        parent = Path(folder)
        owned_directory(parent)
        for name in list(directories):
            path = parent / name
            if path.is_symlink():
                names.append(name)
                directories.remove(name)
        for name in names:
            path = parent / name
            relative = str(path.relative_to(runtime))
            if path.is_symlink():
                try:
                    target = os.readlink(path)
                    if (path.lstat().st_uid != os.getuid() or Path(target).is_absolute()
                            or not path.resolve().is_relative_to(modules)):
                        raise ValueError()
                except (OSError, ValueError):
                    raise Refused('Dashboard Helius dependency link escaped its runtime') from None
                links[relative] = target
            else:
                files[relative] = hashlib.sha256(read_owned(path, maximum=64 * 1024 * 1024)).hexdigest()
    return files, links


def verify_runtime(root: Path = ROOT) -> dict:
    """No credential access, child processes, network requests or shared config."""
    owned_directory(root)
    owned_directory(root / 'ssl')
    owned_directory(root / 'scripts')
    read_owned(root / 'scripts/dashboard-helius-no-telemetry.mjs', maximum=65536)
    runtime = root / 'ssl/helius-mcp-runtime'
    owned_directory(runtime, private=True)
    for name in ('bin', 'home', 'tmp', 'npm-cache'):
        owned_directory(runtime / name, private=True)
    raw = read_owned(runtime / 'runtime-integrity.json', maximum=2 * 1024 * 1024, mode=0o600)
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise Refused('Dashboard Helius runtime manifest does not match the reviewed pin')
    try:
        manifest = json.loads(raw)
    except (UnicodeError, ValueError):
        raise Refused('Dashboard Helius runtime manifest is invalid') from None
    if (manifest.get('package'), manifest.get('version'), manifest.get('node_sha256'),
            manifest.get('package_lock_sha256')) != ('helius-mcp', VERSION, NODE_SHA256, LOCK_SHA256):
        raise Refused('Dashboard Helius package or runtime identity mismatch')
    if hashlib.sha256(read_owned(runtime / 'bin/node', maximum=128 * 1024 * 1024, mode=0o700)).hexdigest() != NODE_SHA256:
        raise Refused('Dashboard Helius Node binary does not match the verified pin')
    if hashlib.sha256(read_owned(runtime / 'package-lock.json', maximum=2 * 1024 * 1024)).hexdigest() != LOCK_SHA256:
        raise Refused('Dashboard Helius dependency lock does not match the reviewed pin')
    files, links = module_inventory(runtime)
    if files != manifest.get('files') or links != manifest.get('symlinks'):
        raise Refused('Dashboard Helius installed dependency tree differs from the reviewed manifest')
    return {
        'package': 'helius-mcp', 'version': VERSION, 'node_version': manifest['node_version'],
        'runtime': str(runtime), 'manifest_sha256': MANIFEST_SHA256,
        'package_lock_sha256': LOCK_SHA256, 'verified_files': len(files),
        'verified_links': len(links), 'recommended_enabled_tools': list(ENABLED_TOOLS),
        'credential_read': False, 'provider_requests': 0,
        'scope': 'local artifact integrity only; client tool filtering and telemetry policy remain required',
    }


def child_environment(key: str, root: Path = ROOT) -> dict[str, str]:
    """Build from literals, never inherit tokens, NODE_OPTIONS, proxies or dotenv."""
    runtime = root / 'ssl/helius-mcp-runtime'
    return {
        'PATH': str(runtime / 'bin') + ':/usr/bin:/bin',
        'HOME': str(runtime / 'home'), 'TMPDIR': str(runtime / 'tmp'),
        'LANG': 'en_US.UTF-8', 'NO_COLOR': '1',
        'HELIUS_API_KEY': key, 'HELIUS_NETWORK': 'mainnet-beta',
        'HELIUS_MCP_SHARED_CREDENTIAL': '1',
    }


def launch(root: Path = ROOT) -> None:
    verify_runtime(root)  # Refuse a replaced runtime before reading the private key.
    key = read_key(root)
    runtime = root / 'ssl/helius-mcp-runtime'
    node = str(runtime / 'bin/node')
    entry = str(runtime / 'node_modules/helius-mcp/dist/index.js')
    blocker = str(root / 'scripts/dashboard-helius-no-telemetry.mjs')
    os.chdir(root)
    try:
        os.execve(node, [node, '--import', blocker, entry], child_environment(key, root))
    except OSError:
        raise Refused('Dashboard Helius MCP could not start; raw process error suppressed') from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', nargs='?', default='stdio', choices=('verify-runtime', 'stdio'))
    args = parser.parse_args(argv)
    try:
        if args.operation == 'verify-runtime':
            print(json.dumps(verify_runtime(), indent=2))
        else:
            launch()
        return 0
    except Refused as error:
        print('Dashboard Helius MCP refused: ' + str(error), file=sys.stderr)
        return 1
    except OSError:
        print('Dashboard Helius MCP refused: local runtime unavailable; raw error suppressed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
