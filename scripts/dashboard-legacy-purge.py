#!/usr/bin/env python3
"""Apply/reconcile the one reviewed, user-authorized invalid legacy bot purge.

No schema, grants, Auth or migration-history changes; no automatic retry. The
private original snapshot and existing closed-release operator are prerequisites.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from uuid import uuid4

ROOT = Path('/Users/redjester/Projects/Next/TheDashboard')
DIRECTORY = ROOT / 'ssl/maintenance-20261007'
STATE = DIRECTORY / 'legacy-purge-original.json'
SOURCE = ROOT / 'supabase/operations/2026-10-07-remove-invalid-legacy-bot-data.sql'
SOURCE_SHA = '671260101efce09d83783f31511b564d6c8f7958edce93f5787714b41c00d379'
BACKUP_SHA = '258a99bdf58f74bd0cb4a534ca5ebe7e01e0de812795809d0f3ba3d9177c9450'
TABLES = ('vn_colonies', 'vn_probes', 'vn_trades', 'vn_fitness_snapshots', 'vn_generation_stats')


class Refused(RuntimeError):
    pass


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cutover = load('dashboard_purge_cutover', ROOT / 'scripts/dashboard-db-cutover.py')
management = load('dashboard_purge_management', ROOT / 'scripts/dashboard-supabase-management.py')


def private_bytes(path):
    if path.parent.is_symlink() or ROOT.resolve() != ROOT:
        raise Refused('Private original path changed')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 16*1024*1024):
            raise Refused('Owned bounded mode-0600 original required')
        return source.read(16*1024*1024+1)


def original():
    value = json.loads(private_bytes(STATE))
    if (hashlib.sha256(private_bytes(DIRECTORY / 'legacy-data-and-migration-history.json')).hexdigest() != BACKUP_SHA
            or set(value.get('data', {})) != set(TABLES)
            or set(value.get('digests', {})) != set(TABLES)
            or any(len(value['data'][table]) != value['digests'][table]['count'] for table in TABLES)
            or value.get('release') != {'state': 'closed', 'epoch': 0, 'v5_runs': 0}
            or value.get('migration_versions') != 15
            or value.get('target', {}).get('supabase', {}).get('id') != management.REF):
        raise Refused('Original private backup/scope differs')
    return value


def save(record):
    temporary = STATE.with_name('legacy-purge-update-' + uuid4().hex + '.json')
    cutover.private_write(temporary, json.dumps(record, indent=2) + '\n')
    os.replace(temporary, STATE)
    directory = os.open(STATE.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def reviewed_source():
    source = SOURCE.read_text()
    result = subprocess.run(['git', 'show', 'origin/main:' + str(SOURCE.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, timeout=15, check=False)
    if (hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA
            or result.returncode or result.stdout != source.encode()):
        raise Refused('Exact reviewed purge source must be merged before application')
    rehearsal = json.loads(private_bytes(Path('/private/tmp/dashboard-oct07-legacy-purge-rehearsal.json')))
    if (rehearsal.get('original_source_sha256') != SOURCE_SHA
            or rehearsal.get('target') != management.REF
            or rehearsal.get('rollback_rehearsal_passed') is not True
            or rehearsal.get('legacy_rows_unchanged') is not True):
        raise Refused('Exact-source managed rollback rehearsal required')
    return source


def current(client):
    values = ','.join("'"+table+"',(SELECT jsonb_build_object('count',count(*),'md5',"
        "md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]'::jsonb)::text)) FROM public."+table+" t)"
        for table in TABLES)
    result = client.query('SELECT jsonb_build_object('+values+') AS digests;')
    if type(result) is not list or len(result) != 1 or set(result[0].get('digests', {})) != set(TABLES):
        raise Refused('Original-scope readback unavailable')
    return result[0]['digests']


def reconcile(client, record):
    digests = current(client)
    if digests == record['digests']:
        raise Refused('Original rows remain; no automatic purge retry')
    if any(value != {'count': 0, 'md5': 'd751713988987e9331980363e24189ce'} for value in digests.values()):
        raise Refused('Original purge outcome differs; no automatic retry')
    # Existing verifier checks all installed bodies/ACLs, exact migration source
    # and the closed release in fresh sessions; data deletion changes none.
    builder, source, manifest = cutover.artifacts()
    cutover.reconcile(builder, source, manifest)
    versions = client.query('SELECT count(*) AS migration_versions FROM supabase_migrations.schema_migrations;')
    if versions != [{'migration_versions': 15}]:
        raise Refused('Migration history changed after purge')
    record['state'] = 'committed_and_verified'
    record['postflight'] = {'row_counts': {table: 0 for table in TABLES},
        'catalog_and_history_verified': True, 'admission': 'closed', 'epoch': 0}
    save(record)
    return {'target': management.REF, 'state': record['state'], **record['postflight'],
        'deleted_rows': {table: record['digests'][table]['count'] for table in TABLES},
        'source_sha256': SOURCE_SHA, 'private_backup_retained': True}


def apply(client, record):
    if record.get('state') != 'prepared':
        raise Refused('Original purge already submitted; reconcile without retry')
    source = reviewed_source()
    if current(client) != record['digests']:
        raise Refused('Original row content changed; no deletion')
    record.update(state='submitted_or_uncertain', source_sha256=SOURCE_SHA,
                  request_id=str(uuid4()))
    save(record)
    client.query(source, read_only=False)
    return reconcile(client, record)


def main():
    if Path.cwd() != ROOT or sys.argv[1:] not in (['apply'], ['reconcile']):
        raise Refused('Use the exact Dashboard directory and apply or reconcile')
    cutover.targets()
    client = management.Management()
    client.verify()
    record = original()
    if sys.argv[1] == 'apply':
        result = apply(client, record)
    else:
        if record.get('state') not in ('submitted_or_uncertain', 'committed_and_verified'):
            raise Refused('No submitted original purge to reconcile')
        result = reconcile(client, record)
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except (Refused, cutover.Refused, management.Refused) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print('Dashboard legacy purge refused; private diagnostics suppressed; reconcile original outcome', file=sys.stderr)
        raise SystemExit(1)
