#!/usr/bin/env python3
"""Finite exact-project pair, durable original outcome, bound inputs, no retries.

No worker selection or admission change. Private files stay in ignored ssl/.
The temporary invoker adapter is removed after issuance/revocation reconciliation.
"""
import base64
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sys
from uuid import UUID, uuid4

ROOT = Path('/Users/redjester/Projects/Next/TheDashboard')
DIRECTORY = ROOT / 'ssl/maintenance-20261007'
STATE = DIRECTORY / 'native-canary-original.json'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


cutover = module('native_target_verifier', ROOT / 'scripts/dashboard-db-cutover.py')
management = module('native_management', ROOT / 'scripts/dashboard-supabase-management.py')
builder = module('native_bound_builder', ROOT / 'services/vonneumann/db-contract/native-issuer/operator.py')


def private_read(path):
    if path.is_symlink() or path.parent.is_symlink():
        raise cutover.Refused('Private operation path changed')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'r') as source:
        info = os.fstat(source.fileno())
        if info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 32768:
            raise cutover.Refused('Owned private operation file required')
        return json.load(source)


def save(record):
    replacement = DIRECTORY / ('native-state-' + uuid4().hex + '.json')
    cutover.private_write(replacement, json.dumps(record, indent=2) + '\n')
    os.replace(replacement, STATE)
    fd = os.open(DIRECTORY, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def verifier(password):
    if not re.fullmatch('[a-f0-9]{64}', password):
        raise cutover.Refused('Independent bounded password required')
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 4096)
    stored = hashlib.sha256(hmac.digest(salted, b'Client Key', 'sha256')).digest()
    server = hmac.digest(salted, b'Server Key', 'sha256')
    b64 = lambda b: base64.b64encode(b).decode('ascii')
    return f'SCRAM-SHA-256$4096:{b64(salt)}${b64(stored)}:{b64(server)}'


def prepare():
    if STATE.exists():
        raise cutover.Refused('Original native operation exists; reconcile instead of replacing')
    owner = private_read(DIRECTORY / 'bot-owner-scope.json')
    if owner.get('legacy_owner_count') != 1 or not owner.get('legacy_owner_auth_match'):
        raise cutover.Refused('One verified legacy bot owner required')
    value = owner['legacy_owner_ids'][0]
    if str(UUID(value)) != value:
        raise cutover.Refused('Canonical bot owner required')
    record = {'version': 1, 'state': 'prepared', 'owner': value, 'run': str(uuid4()),
              'names': ['vn_native_' + uuid4().hex for _ in range(2)],
              'issuances': [str(uuid4()) for _ in range(2)],
              'passwords': [secrets.token_hex(32) for _ in range(2)],
              'write_seconds': 3600, 'recovery_seconds': 7200, 'delay_seconds': 0,
              'adapter_sha256': hashlib.sha256(builder.install().encode()).hexdigest(),
              'purpose': 'no-run closed native-session canary'}
    record['verifiers'] = [verifier(p) for p in record['passwords']]
    cutover.private_write(STATE, json.dumps(record, indent=2) + '\n')
    return record


def verified_adapter(client):
    if cutover.command(['git', 'show', 'origin/main:services/vonneumann/db-contract/native-issuer/operator.py']) != (ROOT / 'services/vonneumann/db-contract/native-issuer/operator.py').read_bytes():
        raise cutover.Refused('Native operator must be reviewed and merged before application')
    # A fresh complete installed-body check before every consequential operation.
    cutover.sql_file(ROOT / 'services/vonneumann/db-contract/forward/verify.sql')
    exists = client.query("SELECT to_regnamespace('dashboard_native_operator') IS NOT NULL AS present")
    if exists != [{'present': False}]:
        raise cutover.Refused('Temporary native adapter already exists; review/reconcile original operation')
    client.query(builder.install(), read_only=False)


def reconcile(client, record):
    # Public scope identifiers only in this SQL, never passwords or verifiers.
    if any(re.fullmatch('vn_native_[a-f0-9]{32}', n) is None for n in record['names']):
        raise cutover.Refused('Original principal scope invalid')
    ids = ','.join("'" + str(UUID(v)) + "'" for v in record['issuances'])
    query = ("BEGIN READ ONLY; SET LOCAL statement_timeout='6s'; SET LOCAL lock_timeout='500ms'; "
             "SET LOCAL ROLE vn_contract_owner; SELECT jsonb_agg(jsonb_build_object("
             "'issuance',b.issuance_id,'name',b.principal_name,'oid',b.principal_oid,'capability',b.capability,"
             "'owner',b.owner_id,'run',b.run_id,'issued_at',b.issued_at,'expires_at',b.expires_at,"
             "'recovery_until',b.recovery_until,'revoked',b.revoked_at,'login',r.rolcanlogin,"
             "'restricted',NOT(r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolinherit OR r.rolreplication OR r.rolbypassrls) AND r.rolconnlimit=2,"
             "'deadline_matches',r.rolvaliduntil=b.recovery_until) ORDER BY b.capability) AS receipt "
             "FROM vn_access.bindings b JOIN pg_roles r ON r.oid=b.principal_oid "
             f"WHERE b.issuance_id IN ({ids}); ROLLBACK;")
    result = client.query(query)
    if len(result) != 1 or result[0].get('receipt') is None:
        raise cutover.Refused('Original native pair not committed; no automatic issuance retry')
    rows = result[0]['receipt']
    if len(rows) != 2:
        raise cutover.Refused('Original native pair incomplete')
    for i, row in enumerate(rows):
        if ((row['issuance'], row['name'], row['capability'], row['owner'], row['run']) !=
            (record['issuances'][i], record['names'][i], ('economic', 'relay')[i], record['owner'], record['run']) or
            not row['restricted'] or not row['deadline_matches'] or
            ('oids' in record and row['oid'] != record['oids'][i])):
            raise cutover.Refused('Original native pair identity changed')
    record['oids'] = [r['oid'] for r in rows]
    record['receipt'] = rows
    record['state'] = 'revoked_verified' if all(r['revoked'] and not r['login'] for r in rows) else 'issued_verified'
    save(record)
    return record


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('prepare', 'issue', 'reconcile', 'revoke'):
        raise cutover.Refused('Choose prepare, issue, reconcile or revoke')
    action = sys.argv[1]
    cutover.targets(require_credential_free=action in ('prepare', 'issue'))
    client = management.Management(); target = client.verify()
    if action == 'prepare':
        record = prepare()
    else:
        record = private_read(STATE)
        if record['adapter_sha256'] != hashlib.sha256(builder.install().encode()).hexdigest():
            raise cutover.Refused('Original reviewed native adapter changed')
        if action == 'reconcile':
            record = reconcile(client, record)
        else:
            expected = 'prepared' if action == 'issue' else 'issued_verified'
            if record['state'] != expected:
                raise cutover.Refused('Original state requires readback; no automatic retry')
            verified_adapter(client)
            record['state'] = action + '_submitted_or_uncertain'; save(record)
            keys = ('owner', 'run', 'names', 'issuances', 'verifiers', 'write_seconds', 'recovery_seconds', 'delay_seconds') if action == 'issue' else ('owner', 'run', 'names', 'issuances', 'oids')
            values = {k: record[k] for k in keys}
            try:
                client.query(f'SELECT {builder.SCHEMA}.{action}($1::jsonb)', [json.dumps(values)], read_only=False)
            finally:
                # The adapter has no private inputs in its definition. Cleanup
                # cannot undo an acknowledged pair or delete its binding.
                client.query(builder.remove(), read_only=False)
            record = reconcile(client, record)
    print(json.dumps({'target': target, 'operation': action, 'state': record['state'],
                      'admission': 'closed', 'run_created': False, 'secret_output': False}))


if __name__ == '__main__':
    try: main()
    except Exception:
        print(json.dumps({'refused': True, 'raw_diagnostics_suppressed': True,
                          'next': 'Inspect original private state and fresh identity/readback; do not create a replacement pair'}))
        sys.exit(1)
