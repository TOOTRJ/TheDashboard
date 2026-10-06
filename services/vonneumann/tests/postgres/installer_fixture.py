"""Hosted-like installation experiment on one owned offline cluster only.

This is deliberately NOT a production SQL packager. It adapts the existing
multi-version laboratory, verifies exact source digests/anchors, and proves the
Auth/ownership boundary needed before extracting canonical v5-only production
DDL. Never call it from a migration, app startup or a configured connection.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parents[2] / 'db-contract'
MANIFEST = DIRECTORY / 'installer_boundary_manifest.json'
MARKER = "SET dashboard.contract_rehearsal='db03a1-isolated';\n"
ADMIN = 'vn_test_admin'

# Only this disposable cluster's bootstrap may use superuser privileges.
# Every installation statement subsequently authenticates as actual postgres,
# now NOSUPERUSER, with the observed Auth grants and no grant options/membership.
HOSTED_BOOTSTRAP = """
-- initdb's OID-10 bootstrap role cannot be demoted. Rename it, then create the
-- actual postgres login as a non-superuser instead of impersonating it with SET.
ALTER ROLE postgres RENAME TO vn_test_bootstrap;
CREATE ROLE postgres LOGIN NOSUPERUSER CREATEDB CREATEROLE INHERIT NOREPLICATION BYPASSRLS;
GRANT CREATE ON DATABASE postgres TO postgres;
GRANT USAGE,CREATE ON SCHEMA public TO postgres;
CREATE ROLE vn_test_auth_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
DROP OWNED BY vn_contract_owner;
DROP ROLE vn_contract_owner;
ALTER SCHEMA auth OWNER TO vn_test_auth_owner;
ALTER TABLE auth.users OWNER TO vn_test_auth_owner;
ALTER FUNCTION auth.uid() OWNER TO vn_test_auth_owner;
REVOKE ALL ON SCHEMA auth FROM postgres;
REVOKE ALL ON TABLE auth.users FROM postgres;
REVOKE ALL ON FUNCTION auth.uid() FROM postgres;
GRANT USAGE ON SCHEMA auth TO postgres;
GRANT EXECUTE ON FUNCTION auth.uid() TO postgres;
GRANT REFERENCES(id) ON auth.users TO postgres;
CREATE ROLE authenticator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT anon,authenticated,service_role TO authenticator WITH INHERIT FALSE, SET TRUE;
"""


def verified_sources() -> dict[str, str]:
    manifest = json.loads(MANIFEST.read_text())
    if manifest['mode'] != 'isolated_installer_rehearsal_only' or manifest['production_application_available']:
        raise ValueError('Not an isolated installer manifest')
    expected = {'001_fenced_commands.sql', '002_read_projections.sql', '004_installer_boundary.sql'}
    if set(manifest['sources_sha256']) != expected:
        raise ValueError('Unexpected installer source set')
    sources = {}
    for name, digest in manifest['sources_sha256'].items():
        data = (DIRECTORY / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Installer laboratory source changed: ' + name)
        sources[name] = data.decode('utf-8')
    return sources


def replace_once(source: str, anchor: str, replacement: str) -> str:
    if source.count(anchor) != 1:
        raise ValueError('Installer laboratory anchor changed')
    return source.replace(anchor, replacement, 1)


def inner_transaction(source: str) -> str:
    source = replace_once(source, 'BEGIN;\n', '')
    return replace_once(source, 'COMMIT;\n', '')


def rehearsal_sql(*, suffix: str = '') -> str:
    sources = verified_sources()
    boundary = replace_once(sources['004_installer_boundary.sql'], 'COMMIT;\n', '')
    core = inner_transaction(sources['001_fenced_commands.sql'])
    core = replace_once(core, 'CREATE SCHEMA vn_durability AUTHORIZATION vn_contract_owner;\n',
        'CREATE SCHEMA vn_durability AUTHORIZATION vn_contract_owner;\n'
        'SET LOCAL ROLE vn_contract_owner;\n'
        'GRANT USAGE,CREATE ON SCHEMA vn_durability TO postgres;\n'
        'RESET ROLE;\n')
    core = replace_once(core, 'CREATE TABLE vn_durability.runs (\n',
        '-- Auth FK is created by postgres using its existing non-grantable REFERENCES.\n'
        'RESET ROLE;\nCREATE TABLE vn_durability.runs (\n')
    core = replace_once(core, '\nCREATE TABLE vn_durability.accounts (\n',
        '\nALTER TABLE vn_durability.runs OWNER TO vn_contract_owner;\n'
        'SET LOCAL ROLE vn_contract_owner;\n'
        'REVOKE USAGE,CREATE ON SCHEMA vn_durability FROM postgres;\n'
        '\nCREATE TABLE vn_durability.accounts (\n')
    # Only read identity expressions change; all economic/validator SQL is retained.
    if core.count('auth.uid()') != 11:
        raise ValueError('Core identity dependency changed')
    core = core.replace('auth.uid()', 'vn_identity.owner_id()')
    reads = inner_transaction(sources['002_read_projections.sql'])
    if reads.count('auth.uid()') != 3:
        raise ValueError('Curated identity dependency changed')
    reads = reads.replace('auth.uid()', 'vn_identity.owner_id()')
    return MARKER + boundary + core + '\nRESET ROLE;\n' + reads + '\nRESET ROLE;\n' + suffix + '\nCOMMIT;\n'
