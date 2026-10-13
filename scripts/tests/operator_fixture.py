"""Test-only source relocation; production operator targets stay unchanged."""
from contextlib import ExitStack, contextmanager
import builtins
import importlib.abc
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PINNED_ROOT = Path('/Users/redjester/Projects/Next/TheDashboard')
ROOT_ASSIGNMENT = "ROOT = Path('/Users/redjester/Projects/Next/TheDashboard')"
SOURCES = frozenset({
    'scripts/dashboard-db-cutover.py', 'scripts/dashboard-supabase-management.py',
    'scripts/dashboard-native-credentials.py', 'scripts/dashboard-legacy-purge.py',
    'services/vonneumann/db-contract/forward/production.py',
    'services/vonneumann/db-contract/native-issuer/operator.py',
})
_ORIGINAL_SPEC = importlib.util.spec_from_file_location
_ORIGINAL_OPEN = builtins.open
_ORIGINAL_IO_OPEN = io.open
_ORIGINAL_OS_OPEN = os.open
PRIVATE_NAMES = frozenset({'ssl', '.vercel', '.aws', '.codex', '.claude'})


def deny_private_path(file):
    if isinstance(file, int): return
    path = Path(os.path.abspath(os.fsdecode(file)))
    for candidate in (path, path.resolve()):
        try:
            parts = candidate.relative_to(ROOT).parts
        except ValueError:
            parts = ()
        if parts and (parts[0] in PRIVATE_NAMES or parts[0].startswith('.env')):
            raise AssertionError('Operator fixtures cannot read repository credentials or private configuration')
        if candidate.is_relative_to(Path('/Users/redjester/.config/vercel-dashboard-codex')):
            raise AssertionError('Operator fixtures cannot read the private Vercel profile')


def fixture_open(file, *args, **kwargs):
    deny_private_path(file); return _ORIGINAL_OPEN(file, *args, **kwargs)


def fixture_io_open(file, *args, **kwargs):
    deny_private_path(file); return _ORIGINAL_IO_OPEN(file, *args, **kwargs)


def fixture_os_open(file, *args, **kwargs):
    deny_private_path(file); return _ORIGINAL_OS_OPEN(file, *args, **kwargs)


def reviewed_path(location):
    requested = Path(location)
    if '..' in requested.parts:
        raise AssertionError('Fixture source cannot traverse paths')
    for base in (PINNED_ROOT, ROOT):
        try:
            relative = requested.relative_to(base).as_posix()
        except ValueError:
            continue
        if relative in SOURCES:
            actual = ROOT / relative
            if actual.resolve() != actual or not actual.is_file():
                raise AssertionError('Fixture source must be an unchanged regular source path')
            return relative, actual
    raise AssertionError('Fixture admits only reviewed operator/artifact source paths')


def relocated_source(relative, source):
    if relative not in SOURCES:
        raise AssertionError('Unreviewed fixture source')
    if relative.startswith('scripts/'):
        lines = source.splitlines(keepends=True)
        if sum(line.rstrip('\r\n') == ROOT_ASSIGNMENT for line in lines) != 1:
            raise AssertionError('Exact production root assignment changed; review before testing')
        replacement = f'ROOT = Path({str(ROOT)!r})'
        return ''.join(replacement + line[len(ROOT_ASSIGNMENT):]
                       if line.rstrip('\r\n') == ROOT_ASSIGNMENT else line for line in lines)
    return source


class FixtureLoader(importlib.abc.Loader):
    def __init__(self, relative, actual): self.relative, self.actual = relative, actual
    def create_module(self, spec): return None
    def exec_module(self, module):
        module.__file__ = str(self.actual)
        source = relocated_source(self.relative, self.actual.read_text())
        exec(compile(source, str(self.actual), 'exec'), module.__dict__)


def fixture_spec(name, location, *args, **kwargs):
    if args or kwargs:
        raise AssertionError('Unexpected operator fixture import options')
    relative, actual = reviewed_path(location)
    return _ORIGINAL_SPEC(name, actual, loader=FixtureLoader(relative, actual))


def refused(*args, **kwargs):
    raise AssertionError('Offline operator fixture attempted a real process or network operation')


@contextmanager
def scope():
    with ExitStack() as stack:
        stack.enter_context(patch.object(importlib.util, 'spec_from_file_location', fixture_spec))
        stack.enter_context(patch.object(subprocess, 'run', side_effect=refused))
        stack.enter_context(patch.object(urllib.request, 'build_opener', side_effect=refused))
        stack.enter_context(patch.object(urllib.request, 'urlopen', side_effect=refused))
        stack.enter_context(patch.object(builtins, 'open', fixture_open))
        stack.enter_context(patch.object(io, 'open', fixture_io_open))
        stack.enter_context(patch.object(os, 'open', fixture_os_open))
        yield


def load(name, relative):
    with scope():
        spec = fixture_spec(name, PINNED_ROOT / relative)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
