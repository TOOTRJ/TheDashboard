"""Owned offline v5 package fixture. No production connection or authentication.

The small facade reuses reviewed provider/controller test cases under real
separate SQL roles. Only fixture observation/seeding uses the test administrator;
RPC admission executes as independent non-admin client logins with SET-only
capability membership. This is not a custom-JWT or hosted credential test.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import re

from tests.postgres import harness, installer_fixture

DIRECTORY = Path(__file__).resolve().parents[2] / 'db-contract' / 'v5'
spec = importlib.util.spec_from_file_location('canonical_v5_builder', DIRECTORY / 'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def package() -> str:
    sql, expected = builder.build()
    if (DIRECTORY / 'package.sql').read_text() != sql or json.loads((DIRECTORY / 'manifest.json').read_text()) != expected:
        raise ValueError('Canonical package/manifest must be rebuilt and reviewed')
    return installer_fixture.MARKER + sql


class CapabilityDatabase:
    def __init__(self, real):
        self.real = real

    def sql(self, source, *, role='postgres', **options):
        if role == 'service_role':
            match = re.match(r'^SELECT vn_(?:durability|read)\.(\w+)\(', source)
            leaf = match[1] if match else None
            if leaf in builder.ECONOMIC:
                role = 'vn_economic'
            elif leaf in builder.RELAY:
                role = 'vn_relay'
        if role in ('vn_economic','vn_relay'):
            source = 'SET ROLE ' + role + ';\n' + source
            role = 'vn_test_economic_client' if role == 'vn_economic' else 'vn_test_relay_client'
        elif role == 'postgres':
            # Fixture-only seeding, fault injection and trusted observations.
            role = installer_fixture.ADMIN
        return self.real.sql(source, role=role, **options)

    def scalar(self, source, **options):
        return self.sql(source, **options).stdout.strip()


def start(test_class):
    real = harness.IsolatedPostgres()
    test_class.addClassCleanup(real.close)
    real.start()
    real.sql('CREATE ROLE vn_test_admin LOGIN SUPERUSER;')
    real.sql(installer_fixture.HOSTED_BOOTSTRAP, role=installer_fixture.ADMIN)
    # Installation MUST authenticate as the limited actual postgres login.
    real.sql(package(), timeout=30)
    real.sql('''
CREATE ROLE vn_test_economic_client LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
CREATE ROLE vn_test_relay_client LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT vn_economic TO vn_test_economic_client WITH ADMIN FALSE,INHERIT FALSE,SET TRUE;
GRANT vn_relay TO vn_test_relay_client WITH ADMIN FALSE,INHERIT FALSE,SET TRUE;
''', role=installer_fixture.ADMIN)
    return CapabilityDatabase(real)
