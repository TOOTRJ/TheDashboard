"""Limited-DBA issuance experiment in owned offline TLS/SCRAM containers only.

Not a production runner: no DSN, environment credential, app import or cloud I/O.
Synthetic passwords/verifiers stay in memory and the owned container's tmpfs.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import subprocess
from uuid import UUID, uuid4

from tests.postgres import installer_fixture, session_auth_fixture

DIRECTORY = Path(__file__).resolve().parents[2] / 'db-contract' / 'native-issuer'
BASE_SHA = '28d5c947c08f1c5a4f3a604cc68d54e35b4269c8f1cca042743d43dbc2140f14'
MARKER = "SET dashboard.native_issuer_rehearsal='c3b1-isolated';\n"


def sources():
    manifest = json.loads((DIRECTORY / 'manifest.json').read_text())
    if manifest.get('mode') != 'isolated_limited_native_issuer_rehearsal' or manifest.get('production_application_available') is not False:
        raise ValueError('Not an isolated native issuer manifest')
    base, _ = session_auth_fixture.builder.build()
    if hashlib.sha256(base.encode()).hexdigest() != BASE_SHA or manifest.get('native_auth_sha256') != BASE_SHA:
        raise ValueError('Reviewed native-auth dependency changed')
    if set(manifest['sources_sha256']) != {'boundary.sql', 'issue.sql', 'revoke.sql'}:
        raise ValueError('Unexpected native issuer source set')
    result = {}
    for name, digest in manifest['sources_sha256'].items():
        data = (DIRECTORY / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Reviewed native issuer source changed')
        result[name] = data.decode()
    return result


def canonical_uuid(value):
    if not isinstance(value, str):
        raise ValueError('Canonical fixture UUID required')
    try:
        canonical = str(UUID(value))
    except (ValueError, AttributeError):
        raise ValueError('Canonical fixture UUID required') from None
    if canonical != value:
        raise ValueError('Canonical fixture UUID required')
    return value


def seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError('Finite fixture lifetime required')
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Finite fixture lifetime required') from None
    if not parsed.is_finite() or parsed.as_tuple().exponent < -6:
        raise ValueError('Finite fixture lifetime required')
    return parsed


def scram_verifier(password):
    # ASCII-only synthetic secrets avoid SASLprep ambiguity. PostgreSQL accepts
    # a precomputed SCRAM verifier; real client authentication proves the format.
    if not isinstance(password, str) or not re.fullmatch('[a-f0-9]{64}', password):
        raise ValueError('Synthetic fixture password required')
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 4096)
    client = hmac.digest(salted, b'Client Key', 'sha256')
    server = hmac.digest(salted, b'Server Key', 'sha256')
    encode = lambda value: base64.b64encode(value).decode('ascii')
    return f'SCRAM-SHA-256$4096:{encode(salt)}${encode(hashlib.sha256(client).digest())}:{encode(server)}'


@dataclass(frozen=True)
class Scope:
    owner: str
    run: str
    names: tuple[str, str]
    issuances: tuple[str, str]

    def declarations(self):
        canonical_uuid(self.owner); canonical_uuid(self.run)
        if (type(self.names) is not tuple or type(self.issuances) is not tuple or
                len(self.names) != 2 or len(set(self.names)) != 2 or len(self.issuances) != 2 or
                len(set(self.issuances)) != 2):
            raise ValueError('Independent fixture pair required')
        for name in self.names:
            if not isinstance(name, str) or not re.fullmatch('vn_native_[a-f0-9]{32}', name):
                raise ValueError('Fresh fixture principal required')
        for issuance in self.issuances:
            canonical_uuid(issuance)
        arrays = lambda values: 'ARRAY[' + ','.join("'" + value + "'" for value in values) + ']'
        return (f" owner_id_input uuid:='{self.owner}'; run_id_input uuid:='{self.run}';\n"
                f' names text[]:={arrays(self.names)}; issuance_ids uuid[]:={arrays(self.issuances)};\n')


@dataclass(frozen=True)
class Pair(Scope):
    passwords: tuple[str, str] = field(repr=False)
    write_seconds: object = 300
    recovery_seconds: object = 600
    delay_seconds: object = 0

    @classmethod
    def new(cls, owner, run, **limits):
        return cls(owner, run, tuple('vn_native_' + uuid4().hex for _ in range(2)),
                   tuple(str(uuid4()) for _ in range(2)), tuple(secrets.token_hex(32) for _ in range(2)), **limits)

    def declarations(self):
        scope = super().declarations()
        if type(self.passwords) is not tuple or len(self.passwords) != 2 or len(set(self.passwords)) != 2:
            raise ValueError('Independent fixture passwords required')
        write, recovery, delay = map(seconds, (self.write_seconds, self.recovery_seconds, self.delay_seconds))
        if not 0 <= delay < write <= 7200 or not write <= recovery <= 86400:
            raise ValueError('Bounded fixture lifetimes required')
        verifiers = tuple(scram_verifier(password) for password in self.passwords)
        arrays = lambda values: 'ARRAY[' + ','.join("'" + value + "'" for value in values) + ']'
        declaration = (scope + f' verifiers text[]:={arrays(verifiers)};\n'
                       f' write_seconds numeric:={write}; recovery_seconds numeric:={recovery}; delay_seconds numeric:={delay};')
        return declaration, verifiers


def compose(name, declarations):
    reviewed = sources()
    source = reviewed[name]
    for anchor, value in (('-- INPUT_DECLARATIONS', declarations), ('-- CHECK_LIMITED_ISSUER', reviewed['boundary.sql'])):
        if source.count(anchor) != 1:
            raise ValueError('Native issuer template anchor changed')
        source = source.replace(anchor, value)
    return MARKER + source


class LimitedIssuerPostgres(session_auth_fixture.NativePostgres):
    def __init__(self):
        super().__init__()
        self.pairs = {}
        self.sensitive_values = []

    def issue_source(self, pair):
        declarations, verifiers = pair.declarations()
        self.sensitive_values.extend((*pair.passwords, *verifiers))
        return compose('issue.sql', declarations)

    def private_sql(self, source, **options):
        # Even expected fixture errors may contain DO context. Return only safe
        # SQL diagnostics with every known synthetic secret/verifier redacted.
        result = self.sql(source, check=False, **options)
        stdout, stderr = result.stdout, result.stderr
        for value in self.sensitive_values:
            stdout, stderr = stdout.replace(value, '[redacted]'), stderr.replace(value, '[redacted]')
        return subprocess.CompletedProcess(result.args, result.returncode, stdout, stderr)

    def issue_pair(self, pair, *, source=None, check=True):
        result = self.private_sql(self.issue_source(pair) if source is None else source)
        if result.returncode:
            if check:
                raise RuntimeError('Limited fixture issuance failed: ' + result.stderr)
            return result
        for name, password in zip(pair.names, pair.passwords):
            self.write_private(name + '.pgpass', f'*:5432:postgres:{name}:{password}\n')
            self.pairs[name] = pair
        return result

    def issue(self, owner, run, capability, *, expires=300, recovery=600, delay=0):
        if capability not in ('economic', 'relay'):
            raise ValueError('Fixture capability required')
        pair = Pair.new(owner, run, write_seconds=expires, recovery_seconds=recovery, delay_seconds=delay)
        self.issue_pair(pair)
        return pair.names[0 if capability == 'economic' else 1]

    def revoke_source(self, pair, oids):
        # Revocation needs retained public scope/OIDs, never old passwords or
        # a usable write lifetime. It must work when secret storage is lost.
        scope = Scope(pair.owner,pair.run,pair.names,pair.issuances).declarations()
        if type(oids) is not tuple or len(oids) != 2 or len(set(oids)) != 2 or any(type(oid) is not int or not 0 < oid < 2**32 for oid in oids):
            raise ValueError('Exact fixture principal OIDs required')
        declaration = scope + f' principal_oids oid[]:=ARRAY[{oids[0]},{oids[1]}];'
        return compose('revoke.sql', declaration)

    def oids(self, pair):
        return tuple(int(self.scalar(f"SELECT oid FROM pg_roles WHERE rolname='{name}';")) for name in pair.names)


def start(test_class):
    db = LimitedIssuerPostgres()
    test_class.addClassCleanup(db.close)
    db.start()
    db.sql('CREATE ROLE vn_test_admin LOGIN SUPERUSER;')
    db.sql(installer_fixture.HOSTED_BOOTSTRAP, role=installer_fixture.ADMIN)
    db.sql(session_auth_fixture.package(), timeout=30)
    return db
