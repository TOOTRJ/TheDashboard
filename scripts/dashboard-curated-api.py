#!/usr/bin/env python3
"""Exact-project curated schema exposure; no grants, secret rotation or run start."""
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path('/Users/redjester/Projects/Next/TheDashboard')
STATE = ROOT / 'ssl/maintenance-20261007/curated-api-original.json'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


native = load('curated_private_file', ROOT / 'scripts/dashboard-native-credentials.py')
management = native.management
cutover = native.cutover


def save(record):
    temporary = STATE.with_name('curated-update-' + native.uuid4().hex + '.json')
    cutover.private_write(temporary, json.dumps(record, indent=2) + '\n')
    os.replace(temporary, STATE)
    fd = os.open(STATE.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def preflight(client):
    cutover.sql_file(ROOT / 'services/vonneumann/db-contract/forward/verify.sql')
    current = client.postgrest()
    if current.get('db_schema') != 'public,graphql_public':
        raise cutover.Refused('Reviewed original schema exposure changed')
    if cutover.command(['git', 'show', 'origin/main:scripts/dashboard-curated-api.py']) != Path(__file__).read_bytes():
        raise cutover.Refused('Curated API operator must be reviewed and merged')
    return current


def reconcile(client, record):
    observed = client.postgrest()
    desired = {**record['before'], 'db_schema': 'public,graphql_public,vn_read'}
    if observed == desired:
        record['state'] = 'exposed_verified'
    elif observed == record['before']:
        record['state'] = 'original_configuration_verified'
    else:
        raise cutover.Refused('Original Data API change unresolved; do not overwrite other settings')
    save(record)
    return record


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('preflight', 'apply', 'reconcile', 'rollback'):
        raise cutover.Refused('Choose preflight, apply, reconcile or rollback')
    action = sys.argv[1]
    cutover.targets()
    client = management.Management(); target = client.verify()
    if action == 'preflight':
        current = preflight(client)
        state = 'reviewed_original_configuration'
    elif action == 'apply':
        if STATE.exists():
            raise cutover.Refused('Original API operation exists; reconcile instead of resubmitting')
        current = preflight(client)
        record = {'version': 1, 'state': 'submitted_or_uncertain', 'before': current,
                  'scope': 'Add only vn_read; preserve all other Data API settings and grants'}
        cutover.private_write(STATE, json.dumps(record, indent=2) + '\n')
        try: client.expose_reads(current)
        except management.Refused: pass
        record = reconcile(client, record); state = record['state']
        if state != 'exposed_verified':
            raise cutover.Refused('Original exposure did not commit; no automatic retry')
    else:
        record = native.private_read(STATE)
        if action == 'rollback':
            client.retire_read_exposure(record['before'])
        record = reconcile(client, record); state = record['state']
    print(json.dumps({'target': target, 'action': action, 'state': state,
                      'curated_schema': 'vn_read', 'private_schemas_exposed': False,
                      'grants_changed': False, 'admission': 'closed'}))


if __name__ == '__main__':
    try: main()
    except Exception:
        print(json.dumps({'refused': True, 'raw_diagnostics_suppressed': True,
                          'next': 'Reconcile the original exact-project configuration; no automatic resubmission'}))
        sys.exit(1)
