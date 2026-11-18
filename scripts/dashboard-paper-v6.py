#!/usr/bin/env python3
"""Exact Dashboard production paper installation; no automatic write retries.

Private originals are retained under ignored ssl/. A failed response permits
original-scope readback, never another issuance or a replacement migration.
Rollback closes only this operation's login/binding and retains all evidence.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
from uuid import UUID, uuid4

ROOT = Path('/Users/redjester/Projects/Next/TheDashboard')
DIRECTORY = ROOT / 'ssl/paper-v6-20261117'
SCHEMA_STATE = DIRECTORY / 'schema-original.json'
CREDENTIAL_STATE = DIRECTORY / 'credentials-original.json'
MIGRATION = ROOT / 'supabase/migrations/20261117010000_vonneumann_paper_v6.sql'
VERSION, NAME = '20261117010000', 'vonneumann_paper_v6'
BASE_SHA256 = 'd49f9646f15584a36df82c8704383bd8cc8f279d5f8064d631d7a013b56ddc44'
HARDENING = ROOT / 'supabase/migrations/20261118010000_vonneumann_paper_v6_search_path.sql'
HARDENING_STATE = DIRECTORY / 'search-path-hardening-original.json'
HARDENING_VERSION, HARDENING_NAME = '20261118010000', 'vonneumann_paper_v6_search_path'
OWNER = '1f785684-f05b-4ba7-8465-672780c93336'
TABLES = ['artifacts', 'bindings', 'controls', 'entries', 'rejections', 'runs', 'sources']
MAX_BODY = 65536


class Refused(RuntimeError):
    pass


def _require(value, reason='paper_operator_precondition_failed'):
    if not value:
        raise Refused(reason)


def _management():
    path = ROOT / 'scripts/dashboard-supabase-management.py'
    spec = importlib.util.spec_from_file_location('dashboard_paper_management', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Management()


def _migration_source(path):
    _require(not path.is_symlink() and path.parent.resolve() == ROOT / 'supabase/migrations')
    raw = path.read_bytes()
    _require(0 < len(raw) <= 24576 and raw.endswith(b'COMMIT;\n')
        and len(re.findall(rb'^BEGIN;$', raw, re.M)) == 1
        and len(re.findall(rb'^COMMIT;$', raw, re.M)) == 1)
    return raw.decode('utf-8'), hashlib.sha256(raw).hexdigest()


def _source():
    source, digest = _migration_source(MIGRATION)
    _require(digest == BASE_SHA256, 'original_base_migration_changed')
    return source, digest


def _hardening_source():
    return _migration_source(HARDENING)


def _private_directory():
    _require(ROOT.resolve() == ROOT and not (ROOT / 'ssl').is_symlink())
    ignored = subprocess.run(['git', 'check-ignore', '--no-index', '-q', 'ssl/paper-v6-20261117/original.json'],
        cwd=ROOT, capture_output=True, timeout=5, check=False)
    _require(ignored.returncode == 0, 'private_directory_must_remain_ignored')
    DIRECTORY.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = DIRECTORY.lstat()
    _require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
        and not info.st_mode & 0o077, 'owned_private_directory_required')


def _write(path, value, *, replace=False):
    _private_directory()
    _require(path.parent == DIRECTORY and not path.is_symlink())
    target = DIRECTORY / ('replacement-' + uuid4().hex + '.json') if replace else path
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as destination:
        destination.write(json.dumps(value, sort_keys=True, indent=2) + '\n')
        destination.flush(); os.fsync(destination.fileno())
    if replace:
        os.replace(target, path)
    directory = os.open(DIRECTORY, os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)


def _read(path):
    _private_directory()
    _require(path.parent == DIRECTORY and not path.is_symlink())
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'r') as source:
        info = os.fstat(source.fileno())
        _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and not info.st_mode & 0o077 and 0 < info.st_size <= 32768)
        value = json.load(source)
    _require(type(value) is dict)
    return value


def _query(client, sql, parameters=(), *, read_only=True):
    body = {'query': sql, 'parameters': list(parameters), 'read_only': read_only}
    _require(len(json.dumps(body).encode('utf-8')) <= MAX_BODY, 'management_body_bound')
    return client.query(sql, parameters, read_only=read_only)


def _one(client, sql, parameters=()):
    rows = _query(client, sql, parameters)
    _require(type(rows) is list and len(rows) == 1 and type(rows[0]) is dict)
    return rows[0]


def _original_schema():
    record = _read(SCHEMA_STATE)
    _, digest = _source()
    _require(record.get('version') == VERSION and record.get('sha256') == digest,
        'original_migration_changed')
    return record


def prepare():
    source, digest = _source()
    _, hardening = _hardening_source()
    record = {'format': 1, 'version': VERSION, 'name': NAME, 'sha256': digest,
        'state': 'prepared', 'migration_bytes': len(source.encode()),
        'prepared_at': datetime.now(timezone.utc).isoformat(),
        'hardening_version': HARDENING_VERSION, 'hardening_sha256': hardening}
    _write(SCHEMA_STATE, record)
    return record


def preflight(client):
    client.verify()
    row = _one(client, "SELECT to_regnamespace('vn_paper_v6') IS NULL AS schema_absent, "
        "NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='vn_paper_v6_client') AS client_absent, "
        "NOT EXISTS(SELECT 1 FROM supabase_migrations.schema_migrations WHERE version IN ($1,$2)) AS version_absent, "
        "current_setting('server_version_num')::integer/10000=17 AS server_supported", (VERSION,HARDENING_VERSION))
    _require(row == {'schema_absent': True, 'client_absent': True, 'version_absent': True, 'server_supported': True},
        'paper_schema_preflight_mismatch')
    return row


def _history_insert(source, version, name):
    encoded = base64.b64encode(source.encode()).decode('ascii')
    return ("INSERT INTO supabase_migrations.schema_migrations(version,name,statements) VALUES('" + version
        + "','" + name + "',ARRAY[convert_from(decode('" + encoded + "','base64'),'UTF8')]);\n")


def schema_install_sql(source):
    _require(hashlib.sha256(source.encode()).hexdigest() == BASE_SHA256)
    forward, _ = _hardening_source()
    forward_body = re.sub(r'^BEGIN;\n', '', forward.removesuffix('COMMIT;\n'), count=1, flags=re.M)
    return (source.removesuffix('COMMIT;\n')+_history_insert(source,VERSION,NAME)
        +forward_body+_history_insert(forward,HARDENING_VERSION,HARDENING_NAME)+'COMMIT;\n')


def hardening_install_sql(source):
    _require(source == _hardening_source()[0])
    return source.removesuffix('COMMIT;\n')+_history_insert(source,HARDENING_VERSION,HARDENING_NAME)+'COMMIT;\n'


def _verify_hardening_receipt(client, record=None):
    _, digest = _hardening_source()
    if record is not None:
        _require(record['version'] == HARDENING_VERSION and record['sha256'] == digest)
    row = _one(client, "SELECT name, cardinality(statements)=1 AS one_source, "
        "encode(sha256(convert_to(statements[1],'UTF8')),'hex') AS sha256 "
        "FROM supabase_migrations.schema_migrations WHERE version=$1", (HARDENING_VERSION,))
    _require(row == {'name': HARDENING_NAME, 'one_source': True, 'sha256': digest},
        'original_hardening_receipt_mismatch')
    return {'version': HARDENING_VERSION, 'sha256': digest}


def verify_schema(client, record=None, *, require_hardening=True):
    record = _original_schema() if record is None else record
    source, digest = _source()
    _require(record['sha256'] == digest)
    client.verify()
    row = _one(client, "SELECT name, cardinality(statements)=1 AS one_source, "
        "encode(sha256(convert_to(statements[1],'UTF8')),'hex') AS sha256 "
        "FROM supabase_migrations.schema_migrations WHERE version=$1", (VERSION,))
    _require(row == {'name': NAME, 'one_source': True, 'sha256': digest}, 'original_schema_receipt_mismatch')
    function_body = source.split('AS $f$', 1)[1].split('$f$;', 1)[0]
    expected_body = hashlib.sha256(function_body.encode()).hexdigest()
    path_check = "p.proconfig=ARRAY['search_path=pg_catalog, pg_temp']::text[]"
    if not require_hardening:
        path_check = "("+path_check+" OR p.proconfig=ARRAY['search_path=pg_catalog']::text[])"
    checks = _one(client, "SELECT "
        "(SELECT array_agg(c.relname::text ORDER BY c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='vn_paper_v6' AND c.relkind='r') AS tables, "
        "(SELECT bool_and(c.relrowsecurity AND c.relowner=n.nspowner) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='vn_paper_v6' AND c.relkind='r') AS owned_rls, "
        "(SELECT NOT(rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls) FROM pg_roles WHERE rolname='vn_paper_v6_client') AS client_restricted, "
        "(SELECT p.prosecdef AND "+path_check+" AND p.proowner=n.nspowner AND encode(sha256(convert_to(p.prosrc,'UTF8')),'hex')=$1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE p.oid=to_regprocedure('vn_paper_v6.rpc(text,jsonb)')) AS rpc_exact, "
        "has_schema_privilege('vn_paper_v6_client','vn_paper_v6','USAGE') AND has_function_privilege('vn_paper_v6_client','vn_paper_v6.rpc(text,jsonb)','EXECUTE') AS client_rpc, "
        "NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='vn_paper_v6' AND c.relkind='r' AND has_table_privilege('vn_paper_v6_client',c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')) AS no_client_tables, "
        "NOT EXISTS(SELECT 1 FROM (VALUES('anon'),('authenticated'),('service_role')) r(name) WHERE has_schema_privilege(r.name,'vn_paper_v6','USAGE') OR has_function_privilege(r.name,'vn_paper_v6.rpc(text,jsonb)','EXECUTE')) AS no_api_access, "
        "NOT EXISTS(SELECT 1 FROM pg_namespace n, LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a WHERE n.nspname='vn_paper_v6' AND a.grantee=0) AS no_public_schema, "
        "NOT EXISTS(SELECT 1 FROM pg_proc p, LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE p.oid=to_regprocedure('vn_paper_v6.rpc(text,jsonb)') AND a.grantee=0) AS no_public_rpc", (expected_body,))
    _require(checks.get('tables') == TABLES and all(value is True for key, value in checks.items() if key != 'tables'),
        'installed_paper_schema_security_mismatch')
    _require('vn_paper_v6' not in client.postgrest().get('db_schema', '').split(','), 'private_schema_exposed')
    result = {'version': VERSION, 'sha256': digest, 'tables': len(TABLES),
        'base_contract_verified': True, 'security_verified': require_hardening}
    if require_hardening:
        result['hardening'] = _verify_hardening_receipt(client)
    return result


def apply_schema(client):
    record = _original_schema()
    _require(record['state'] == 'prepared', 'schema_already_submitted_reconcile_only')
    preflight(client)
    source, _ = _source()
    if 'hardening_sha256' in record:
        _require(record['hardening_sha256'] == _hardening_source()[1], 'prepared_hardening_source_changed')
    sql = schema_install_sql(source)
    record['state'] = 'submitted_or_uncertain'; _write(SCHEMA_STATE, record, replace=True)
    client.verify()  # fresh exact project/name/organization before the only write
    try:
        _query(client, sql, read_only=False)
    except Exception:
        pass
    # Original version/hash readback, never retry the DDL on a missing reply.
    result = verify_schema(client, record)
    record['state'] = 'installed_verified'; _write(SCHEMA_STATE, record, replace=True)
    return result


def prepare_hardening():
    source, digest = _hardening_source()
    record = {'format': 1, 'version': HARDENING_VERSION, 'name': HARDENING_NAME,
        'sha256': digest, 'base_version': VERSION, 'base_sha256': _source()[1],
        'state': 'prepared', 'migration_bytes': len(source.encode()),
        'prepared_at': datetime.now(timezone.utc).isoformat()}
    _write(HARDENING_STATE, record)
    return record


def _original_hardening():
    record = _read(HARDENING_STATE)
    _require(record.get('version') == HARDENING_VERSION
        and record.get('sha256') == _hardening_source()[1]
        and record.get('base_version') == VERSION and record.get('base_sha256') == _source()[1],
        'original_hardening_source_changed')
    return record


def preflight_hardening(client, record=None):
    record = _original_hardening() if record is None else record
    _require(record['sha256'] == _hardening_source()[1])
    verify_schema(client, require_hardening=False)
    row = _one(client, "SELECT NOT EXISTS(SELECT 1 FROM supabase_migrations.schema_migrations WHERE version=$1) AS version_absent", (HARDENING_VERSION,))
    _require(row == {'version_absent': True}, 'hardening_version_already_present_reconcile_only')
    return {'base_verified': True, 'hardening_version_absent': True}


def verify_hardening(client, record=None):
    record = _original_hardening() if record is None else record
    result = verify_schema(client)
    _require(result['hardening'] == {'version': record['version'], 'sha256': record['sha256']})
    return result['hardening']


def apply_hardening(client):
    record = _original_hardening()
    _require(record['state'] == 'prepared', 'hardening_already_submitted_reconcile_only')
    preflight_hardening(client, record)
    sql = hardening_install_sql(_hardening_source()[0])
    record['state'] = 'submitted_or_uncertain'; _write(HARDENING_STATE, record, replace=True)
    client.verify()
    try: _query(client, sql, read_only=False)
    except Exception: pass
    result = verify_hardening(client, record)
    record['state'] = 'installed_verified'; _write(HARDENING_STATE, record, replace=True)
    return result


def _repo_email():
    result = subprocess.run(['git', 'config', '--local', 'user.email'], cwd=ROOT,
        capture_output=True, timeout=5, check=False)
    value = result.stdout.decode('utf-8').strip()
    _require(result.returncode == 0 and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value) is not None,
        'verified_repository_email_required')
    return value


def verify_owner(client):
    client.verify()
    row = _one(client, "SELECT id=$1::uuid AS exact_owner, lower(email)=lower($2) AS repository_email_matches, "
        "email_confirmed_at IS NOT NULL AS confirmed FROM auth.users WHERE id=$1::uuid", (OWNER, _repo_email()))
    _require(row == {'exact_owner': True, 'repository_email_matches': True, 'confirmed': True}, 'paper_owner_mismatch')


def _verifier(password):
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac('sha256', password.encode('ascii'), salt, 4096)
    stored = hashlib.sha256(hmac.digest(salted, b'Client Key', 'sha256')).digest()
    server = hmac.digest(salted, b'Server Key', 'sha256')
    b64 = lambda value: base64.b64encode(value).decode('ascii')
    return f'SCRAM-SHA-256$4096:{b64(salt)}${b64(stored)}:{b64(server)}'


def prepare_credentials(client):
    schema = verify_schema(client)
    verify_owner(client)
    now = datetime.now(timezone.utc)
    password = secrets.token_hex(32)
    record = {'format': 1, 'state': 'prepared', 'owner_id': OWNER,
        'run_id': str(uuid4()), 'market_epoch_id': str(uuid4()), 'principal_binding_id': str(uuid4()),
        'db_login': 'vn_paper_' + uuid4().hex, 'db_password': password, 'scram_verifier': _verifier(password),
        'prepared_at': now.isoformat(), 'valid_until': (now+timedelta(days=7)).isoformat(),
        'migration_sha256': schema['sha256'], 'purpose': 'single-owner production reference-mark paper pilot'}
    _write(CREDENTIAL_STATE, record)
    return record


def _credentials():
    record = _read(CREDENTIAL_STATE)
    _require(record.get('owner_id') == OWNER and record.get('migration_sha256') == _source()[1])
    for key in ('run_id', 'market_epoch_id', 'principal_binding_id'):
        _require(str(UUID(record[key])) == record[key])
    _require(re.fullmatch(r'vn_paper_[a-f0-9]{32}', record['db_login']) is not None
        and re.fullmatch(r'[a-f0-9]{64}', record['db_password']) is not None
        and re.fullmatch(r'SCRAM-SHA-256\$4096:[A-Za-z0-9+/]{22}==\$[A-Za-z0-9+/]{43}=:[A-Za-z0-9+/]{43}=', record['scram_verifier']) is not None)
    start, end = [datetime.fromisoformat(record[key]) for key in ('prepared_at', 'valid_until')]
    _require(start.utcoffset() == end.utcoffset() == timedelta(0) and end-start == timedelta(days=7))
    return record


def _literal(value):
    _require(type(value) is str and '\x00' not in value)
    return "'" + value.replace("'", "''") + "'"


def credential_install_sql(record):
    login, owner, run, expiry, verifier = [_literal(record[key]) for key in
        ('db_login', 'owner_id', 'run_id', 'valid_until', 'scram_verifier')]
    # Only a salted SCRAM verifier is sent. No plaintext password enters SQL or
    # process arguments; format(%I/%L) also quotes every identifier/value natively.
    return ("BEGIN; SET LOCAL statement_timeout='8s'; SET LOCAL lock_timeout='1s'; "
        "DO $operator$ BEGIN "
        f"IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname={login}) OR EXISTS(SELECT 1 FROM vn_paper_v6.bindings WHERE owner_id={owner}::uuid AND run_id={run}::uuid) THEN RAISE EXCEPTION 'paper_original_exists'; END IF; "
        f"EXECUTE format('CREATE ROLE %I LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD %L VALID UNTIL %L',{login},{verifier},{expiry}); "
        f"EXECUTE format('GRANT CONNECT ON DATABASE postgres TO %I',{login}); "
        f"EXECUTE format('GRANT USAGE ON SCHEMA vn_paper_v6 TO %I',{login}); "
        f"EXECUTE format('GRANT EXECUTE ON FUNCTION vn_paper_v6.rpc(text,jsonb) TO %I',{login}); "
        f"INSERT INTO vn_paper_v6.bindings(login,owner_id,run_id,expires_at) VALUES({login}::name,{owner}::uuid,{run}::uuid,{expiry}::timestamptz); "
        "END $operator$; COMMIT;")


def verify_credentials(client, record=None, *, closed=False, allow_expired=False):
    record = _credentials() if record is None else record
    client.verify()
    row = _one(client, "SELECT r.oid AS role_oid, b.owner_id=$2::uuid AND b.run_id=$3::uuid AS binding_exact, "
        "NOT(r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolinherit OR r.rolreplication OR r.rolbypassrls) AND r.rolconnlimit=2 AS restricted, "
        "r.rolcanlogin AS can_login, r.rolvaliduntil=$4::timestamptz AS role_deadline, "
        "b.expires_at=$4::timestamptz AS binding_deadline, b.expires_at>clock_timestamp() AS binding_active, "
        "NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) AS no_memberships, "
        "has_schema_privilege(r.oid,'vn_paper_v6','USAGE') AND has_function_privilege(r.oid,'vn_paper_v6.rpc(text,jsonb)','EXECUTE') AS direct_rpc, "
        "NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='vn_paper_v6' AND c.relkind='r' AND has_table_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')) AS no_table_access "
        "FROM pg_roles r JOIN vn_paper_v6.bindings b ON b.login=r.rolname WHERE r.rolname=$1",
        (record['db_login'], OWNER, record['run_id'], record['valid_until']))
    _require(all(row.get(key) is True for key in ('binding_exact', 'restricted', 'role_deadline', 'no_memberships', 'direct_rpc', 'no_table_access')))
    if 'role_oid' in record:
        _require(row['role_oid'] == record['role_oid'], 'original_login_identity_changed')
    if closed:
        _require(row['can_login'] is False and row['binding_active'] is False, 'paper_login_not_closed')
    else:
        _require(row['can_login'] is True and row['binding_deadline'] is True
            and (allow_expired or row['binding_active'] is True))
    record['role_oid'] = row['role_oid']
    record['state'] = 'closed_verified' if closed else 'issued_verified'
    _write(CREDENTIAL_STATE, record, replace=True)
    return {'state': record['state'], 'owner_id': OWNER, 'run_id': record['run_id'],
        'valid_until': record['valid_until'], 'credential_output': False}


def issue_credentials(client):
    record = _credentials()
    _require(record['state'] == 'prepared', 'credential_already_submitted_reconcile_only')
    _require(datetime.fromisoformat(record['valid_until']) > datetime.now(timezone.utc))
    verify_schema(client); verify_owner(client)
    absent = _one(client, "SELECT NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1) AS role_absent, "
        "NOT EXISTS(SELECT 1 FROM vn_paper_v6.bindings WHERE owner_id=$2::uuid AND run_id=$3::uuid) AS binding_absent",
        (record['db_login'], OWNER, record['run_id']))
    _require(absent == {'role_absent': True, 'binding_absent': True})
    record['state'] = 'submitted_or_uncertain'; _write(CREDENTIAL_STATE, record, replace=True)
    client.verify()
    try: _query(client, credential_install_sql(record), read_only=False)
    except Exception: pass
    return verify_credentials(client, record)


def credential_close_sql(record):
    _require(type(record.get('role_oid')) is int and record['role_oid'] > 0)
    login, run, expiry = [_literal(record[key]) for key in ('db_login', 'run_id', 'valid_until')]
    oid = str(record['role_oid'])
    # The readback above is insufficient by itself: validate again inside this
    # transaction before addressing a role by name. The binding row stays locked
    # through the close. A second OID check also rolls back if an external actor
    # replaces the name after the first check but before ALTER ROLE resolves it.
    return ("BEGIN; SET LOCAL statement_timeout='8s'; SET LOCAL lock_timeout='1s'; "
        "DO $operator$ DECLARE original_binding vn_paper_v6.bindings%ROWTYPE; BEGIN "
        "SELECT * INTO STRICT original_binding FROM vn_paper_v6.bindings WHERE login=" + login
        + "::name AND owner_id='" + OWNER + "'::uuid AND run_id=" + run
        + "::uuid AND expires_at=" + expiry + "::timestamptz FOR UPDATE; "
        "IF NOT EXISTS(SELECT 1 FROM pg_roles r WHERE r.rolname=" + login + " AND r.oid=" + oid
        + "::oid AND r.rolvaliduntil=" + expiry + "::timestamptz AND r.rolconnlimit=2 "
        "AND NOT(r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolinherit OR r.rolreplication OR r.rolbypassrls) "
        "AND NOT EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid)) "
        "THEN RAISE EXCEPTION 'paper_original_role_changed'; END IF; "
        "EXECUTE format('ALTER ROLE %I NOLOGIN PASSWORD NULL'," + login + "); "
        "IF NOT EXISTS(SELECT 1 FROM pg_roles r WHERE r.rolname=" + login + " AND r.oid=" + oid
        + "::oid AND NOT r.rolcanlogin AND r.rolvaliduntil=" + expiry
        + "::timestamptz) THEN RAISE EXCEPTION 'paper_original_role_changed'; END IF; "
        "UPDATE vn_paper_v6.bindings SET expires_at=least(expires_at,clock_timestamp()) WHERE login="
        + login + "::name AND owner_id='" + OWNER + "'::uuid AND run_id=" + run
        + "::uuid AND expires_at=" + expiry + "::timestamptz; END $operator$; COMMIT;")


def rollback(client):
    record = _credentials()
    _require(type(record.get('role_oid')) is int and record['role_oid'] > 0,
        'original_issued_role_oid_required')
    # Expiry bars new RPC work but must not prevent closing this exact login.
    # No role is dropped and no other scope or environment is changed.
    verify_credentials(client, record, allow_expired=True)
    record['state'] = 'close_submitted_or_uncertain'; _write(CREDENTIAL_STATE, record, replace=True)
    client.verify()
    sql = credential_close_sql(record)
    try: _query(client, sql, read_only=False)
    except Exception: pass
    return verify_credentials(client, record, closed=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'plan', 'apply-schema', 'verify',
        'prepare-hardening', 'plan-hardening', 'apply-hardening', 'verify-hardening',
        'prepare-credentials', 'issue-credentials', 'verify-credentials', 'rollback'))
    action = parser.parse_args(argv).action
    if action == 'prepare':
        record = prepare()
        result = {'state': record['state'], 'version': VERSION, 'sha256': record['sha256']}
    elif action == 'prepare-hardening':
        record = prepare_hardening()
        result = {'state': record['state'], 'version': HARDENING_VERSION, 'sha256': record['sha256']}
    else:
        client = _management()
        if action == 'plan':
            record = _original_schema(); result = {'state': record['state'], 'preflight': preflight(client)}
        elif action == 'apply-schema': result = apply_schema(client)
        elif action == 'verify': result = verify_schema(client)
        elif action == 'plan-hardening': result = preflight_hardening(client)
        elif action == 'apply-hardening': result = apply_hardening(client)
        elif action == 'verify-hardening':
            record = _original_hardening(); result = verify_hardening(client, record)
            record['state'] = 'installed_verified'; _write(HARDENING_STATE, record, replace=True)
        elif action == 'prepare-credentials':
            record = prepare_credentials(client)
            result = {'state': record['state'], 'owner_id': OWNER, 'run_id': record['run_id'],
                'valid_until': record['valid_until']}
        elif action == 'issue-credentials': result = issue_credentials(client)
        elif action == 'verify-credentials':
            record = _credentials()
            result = verify_credentials(client, record, closed=record['state'] in ('close_submitted_or_uncertain', 'closed_verified'))
        else: result = rollback(client)
    print(json.dumps({'operation': action, 'target': 'The Dashboard/fxpxsciltakyypunglzr/cqfnnaunmupdyobkyqfo',
        'result': result, 'service_mode_changed': False, 'secret_output': False}))


if __name__ == '__main__':
    try: main()
    except Exception:
        print(json.dumps({'refused': True, 'raw_diagnostics_suppressed': True,
            'next': 'Inspect retained original scope and verify exact readback; do not retry writes automatically'}))
        sys.exit(1)
