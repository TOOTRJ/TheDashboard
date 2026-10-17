#!/usr/bin/env python3
"""Exact-project Management API, using existing Supabase CLI Keychain read only.

No login/logout/credential write, token output, credential argv, redirect or proxy fallback.
Callers must first resolve verify(), then use a fixed permitted project path.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import types
import urllib.error
import urllib.request

ROOT = Path('/Users/redjester/Projects/Next/TheDashboard')
REF = 'fxpxsciltakyypunglzr'
ORG = 'cqfnnaunmupdyobkyqfo'
NAME = 'The Dashboard'
BASE = 'https://api.supabase.com/v1/projects/' + REF
ALLOWED = {'': frozenset({'GET'}), '/database/query': frozenset({'POST'}),
           '/postgrest': frozenset({'GET', 'PATCH'}), '/api-keys?reveal=true': frozenset({'GET'})}
API_BASELINE_PERMISSIONS_EMITTER_SHA256 = '9286a31aac28bfcafe52c2f7eb90dd60b35712fd1e99a123fa4d7aee918f73ee'


class Refused(RuntimeError):
    pass


def _api_baseline_permissions_sql():
    """Import only held, reviewed regular emitter bytes; never caller source."""
    path = ROOT / 'scripts/dashboard_api_baseline.py'
    try:
        if ROOT.resolve(strict=True) != ROOT or path.parent.resolve(strict=True) != ROOT / 'scripts':
            raise ValueError()
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 65536:
                raise ValueError()
            raw = source.read(65537)
            after = os.fstat(source.fileno())
            named = os.stat(path, follow_symlinks=False)
            identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
            if (not stat.S_ISREG(named.st_mode) or identity(before) != identity(after)
                    or identity(after) != identity(named) or len(raw) != before.st_size
                    or hashlib.sha256(raw).hexdigest() != API_BASELINE_PERMISSIONS_EMITTER_SHA256):
                raise ValueError()
        module = types.ModuleType('dashboard_reviewed_api_baseline_permissions')
        module.__file__ = str(path)
        # Compile the verified held bytes rather than asking an import loader
        # to reopen a filename after its identity/content checks.
        exec(compile(raw, str(path), 'exec'), module.__dict__)
        return module.baseline_sql(apply_acl=True)
    except Exception:
        raise Refused('Reviewed API baseline permissions source unavailable') from None


def credential():
    # Fixed official CLI profile only; never inspect another Keychain service.
    try:
        result = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', 'Supabase CLI',
                                 '-a', 'supabase', '-w'], capture_output=True, timeout=10, check=False)
        if result.returncode or len(result.stdout) > 4096:
            raise ValueError()
        value = result.stdout.decode('ascii').strip()
        if value.startswith('go-keyring-base64:'):
            value = base64.b64decode(value.removeprefix('go-keyring-base64:'), validate=True).decode('ascii')
        elif value.startswith('go-keyring-encoded:'):
            value = bytes.fromhex(value.removeprefix('go-keyring-encoded:')).decode('ascii')
        if re.fullmatch(r'sbp_(?:oauth_)?[a-f0-9]{40}', value) is None:
            raise ValueError()
        return value
    except Exception:
        raise Refused('Existing Supabase CLI profile unavailable; no shared login changed') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Management:
    def __init__(self):
        if ROOT.resolve() != ROOT or (ROOT / 'supabase/.temp/project-ref').read_text().strip() != REF:
            raise Refused('Dashboard linked Supabase target mismatch')
        self._credential = credential()
        self._verified = False

    def _request(self, path, body=None, *, method=None):
        method = method or ('GET' if body is None else 'POST')
        if path not in ALLOWED or method not in ALLOWED[path] or (path and not self._verified):
            raise Refused('Unverified or unauthorized Supabase project path')
        data = None if body is None else json.dumps(body).encode('utf-8')
        request = urllib.request.Request(BASE + path, data=data, headers={
            'Authorization': 'Bearer ' + self._credential, 'Content-Type': 'application/json',
            'User-Agent': 'TheDashboard-Operator/1.0'}, method=method)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=20) as response:
                if response.status not in (200, 201):
                    raise ValueError()
                raw = response.read(1048577)
            if len(raw) > 1048576:
                raise ValueError()
            return json.loads(raw)
        except Exception:
            # An issuance error is uncertain until original-scope readback.
            raise Refused('Supabase Management request failed; response suppressed; reconcile original operation') from None

    def verify(self):
        # A failed refresh must not retain a previous identity admission.
        self._verified = False
        value = self._request('')
        if (not isinstance(value, dict) or
            (value.get('id'), value.get('name'), value.get('organization_id')) != (REF, NAME, ORG)):
            raise Refused('Supabase immutable project/name/owner mismatch')
        self._verified = True
        return {'id': REF, 'name': NAME, 'owner': ORG}

    def query(self, source, parameters=(), *, read_only=True):
        if type(source) is not str or not source or len(source.encode()) > 65536 or type(parameters) not in (tuple, list):
            raise Refused('Bounded query required')
        return self._request('/database/query', {'query': source, 'parameters': list(parameters), 'read_only': read_only})

    def api_baseline_permissions(self):
        """Issue only the fixed reviewed permissions operation after verify()."""
        if getattr(self, '_verified', False) is not True:
            raise Refused('Verified Dashboard project required for API permissions')
        source = _api_baseline_permissions_sql()
        if type(source) is not str or not source or len(source.encode('utf-8')) > 196608:
            raise Refused('Bounded reviewed API permissions query required')
        return self._request('/database/query', {'query': source, 'parameters': [], 'read_only': False})

    def postgrest(self):
        return self._request('/postgrest')

    def expose_reads(self, expected):
        if (expected.get('db_schema') != 'public,graphql_public' or self.postgrest() != expected):
            raise Refused('Exact reviewed Data API configuration changed')
        return self._request('/postgrest', {'db_schema': 'public,graphql_public,vn_read'}, method='PATCH')

    def retire_read_exposure(self, expected):
        if (expected.get('db_schema') != 'public,graphql_public' or
            self.postgrest() != {**expected, 'db_schema': 'public,graphql_public,vn_read'}):
            raise Refused('Exact current Data API configuration changed; review before rollback')
        return self._request('/postgrest', {'db_schema': expected['db_schema']}, method='PATCH')
