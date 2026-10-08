#!/usr/bin/env python3
"""Explicit, exact-target closed migration operator; never selects other projects.

No passwords/DSNs, blanket db push, automatic retries, credential issuance,
API exposure, admission opening or destructive rollback. Management SQL output
stays private. An uncertain reply is reconciled against the original source.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path('/Users/redjester/Projects/Next/TheDashboard')
REF = 'fxpxsciltakyypunglzr'
ORG = 'cqfnnaunmupdyobkyqfo'
PROJECT = 'prj_wFUe9k9USVreOQcmQKNWRAVsx5fH'
TEAM = 'team_8iNNxiNjrOseD4gdSCHkQEzF'
NODE = '/Users/redjester/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
VC = '/opt/homebrew/lib/node_modules/vercel/dist/vc.js'
PROFILE = '/Users/redjester/.config/vercel-dashboard-codex'
STATE = ROOT / 'ssl/maintenance-20261007/closed-install-outcome.json'


class Refused(RuntimeError):
    pass


def command(args, *, env=None, timeout=50):
    try:
        result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True,
                                timeout=timeout, check=False)
        if result.returncode:
            raise ValueError()
        return result.stdout
    except Exception:
        raise Refused('Scoped operation failed or timed out; raw output suppressed') from None


def json_command(args, **options):
    try:
        raw = command(args, **options)
        if len(raw) > 8_000_000:
            raise ValueError()
        return json.loads(raw)
    except Refused:
        raise
    except Exception:
        raise Refused('Unexpected scoped response; raw output suppressed') from None


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def artifacts():
    builder = load('dashboard_closed_migration', ROOT / 'services/vonneumann/db-contract/forward/production.py')
    source, manifest = builder.build()
    if (builder.MIGRATION.read_text() != source or
        json.loads(builder.MANIFEST.read_text()) != manifest or
        hashlib.sha256(source.encode()).hexdigest() != manifest['migration_sha256']):
        raise Refused('Reviewed migration artifacts differ')
    return builder, source, manifest


def targets(*, require_credential_free=True):
    g = json_command(['python3', 'scripts/dashboard-github.py', 'verify'])
    if (g.get('login'), g.get('user_id'), g.get('repository'), g.get('repository_id')) != (
        'biggrizzly11', 16749816, 'TOOTRJ/TheDashboard', 1141090963):
        raise Refused('GitHub target mismatch')
    p = json.loads((ROOT / '.vercel/project.json').read_text())
    if (p.get('projectId'), p.get('orgId'), p.get('projectName')) != (PROJECT, TEAM, 'the-dashboard'):
        raise Refused('Vercel local target mismatch')
    env = dict(os.environ)
    for key in ('VERCEL_TOKEN', 'VERCEL_ORG_ID', 'VERCEL_PROJECT_ID'):
        env.pop(key, None)
    env.update(NO_UPDATE_NOTIFIER='1', VERCEL_TOKEN_STORAGE='file')
    vc = [NODE, VC, '--global-config', PROFILE, '--scope', TEAM, '--cwd', str(ROOT)]
    # Resolve the CLI project context as well as immutable API identity.
    command(vc + ['project', 'inspect', PROJECT, '--non-interactive'], env=env)
    remote = json_command(vc + ['api', f'/v9/projects/{PROJECT}', '--raw'], env=env)
    if (remote.get('id'), remote.get('name'), remote.get('accountId'),
        remote.get('link', {}).get('repoId')) != (PROJECT, 'the-dashboard', TEAM, 1141090963):
        raise Refused('Vercel remote target mismatch')
    projects = json_command(['supabase', 'projects', 'list', '--workdir', str(ROOT), '--output', 'json'])
    s = next((item for item in projects if item.get('id') == REF), None)
    if not s or (s.get('name'), s.get('organization_id')) != ('The Dashboard', ORG):
        raise Refused('Supabase target mismatch')
    if (ROOT / 'supabase/.temp/project-ref').read_text().strip() != REF:
        raise Refused('Supabase local target mismatch')
    ssl = json_command(['supabase', 'ssl-enforcement', 'get', '--project-ref', REF,
                        '--workdir', str(ROOT), '--output', 'json', '--agent=no', '--experimental'])
    if ssl != {'appliedSuccessfully': True, 'currentConfig': {'database': True}}:
        raise Refused('Applied database SSL enforcement required')
    railway = load('dashboard_closed_host', ROOT / 'scripts/dashboard-railway.py')
    token = railway.token()
    host = railway.verify_service(token)
    variables = railway.query(token,
        'query($service:String!,$environment:String!,$project:String!) { variables(serviceId:$service,environmentId:$environment,projectId:$project) }',
        {'service': railway.SERVICE, 'environment': railway.ENVIRONMENT, 'project': railway.PROJECT})['variables']
    if (variables.get('VN_SERVICE_MODE') != 'closed' or
        variables.get('VN_DOTENV_DISABLED') != '1' or
        any(key in variables for key in ('RAILWAY_TOKEN', 'RAILWAY_API_TOKEN', 'SUPABASE_SERVICE_ROLE_KEY',
                                        'SUPABASE_SECRET_KEY', 'SUPABASE_DB_PASSWORD')) or
        (require_credential_free and any(key in variables for key in ('VN_ECONOMIC_PASSWORD', 'VN_RELAY_PASSWORD')))):
        raise Refused('Verified closed credential-free worker required')
    return {'github': g, 'vercel': {'id': PROJECT, 'name': 'the-dashboard', 'owner': TEAM},
            'supabase': {'id': REF, 'name': 'The Dashboard', 'owner': ORG, 'ssl_enforced': True},
            'railway': {'id': railway.PROJECT, 'service': railway.SERVICE,
                        'closed': True, 'deployment': host['service']['latestDeployment']}}


def sql_file(path):
    return json_command(['supabase', 'db', 'query', '--linked', '--workdir', str(ROOT),
                         '--file', str(path), '--output', 'json', '--agent=no'])


def private_write(path, source):
    if path.parent.is_symlink() or path.is_symlink():
        raise Refused('Private operation path must not be a symlink')
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as out:
        out.write(source)
        out.flush()
        os.fsync(out.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def save_state(record):
    """Keep the original complete record until its replacement is durable."""
    if STATE.is_symlink() or STATE.parent.is_symlink():
        raise Refused('Original operation path changed')
    replacement = STATE.with_name('outcome-' + uuid.uuid4().hex + '.json')
    private_write(replacement, json.dumps(record, indent=2) + '\n')
    os.replace(replacement, STATE)
    directory = os.open(STATE.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def history_wrapper(source, version, name):
    if (not re.fullmatch(r'\d{14}', version) or not re.fullmatch(r'[a-z0-9_]+', name) or
        len(re.findall(r'^COMMIT;$', source, re.MULTILINE)) != 1 or not source.endswith('COMMIT;\n')):
        raise Refused('Unreviewed transaction/history grammar')
    quoted = "'" + source.replace("'", "''") + "'"
    return source.removesuffix('COMMIT;\n') + (
        f"INSERT INTO supabase_migrations.schema_migrations(version,name,statements)\n"
        f"VALUES('{version}','{name}',ARRAY[{quoted}]);\nCOMMIT;\n")


def preflight(builder, source, manifest):
    current = sql_file(ROOT / 'supabase/audits/vonneumann-forward-review.sql')
    review = json.loads(builder.REVIEW.read_text())
    if (len(current) != 1 or set(current[0]) != {'review'} or
        current[0]['review'] != {'legacy': review['legacy_catalog'], 'migrations': review['migration_catalog'],
                                'read_only': 'on', 'isolation': 'repeatable read'}):
        raise Refused('Independent catalog/history changed; review again before mutation')
    if command(['git', 'show', f'origin/main:{builder.MIGRATION.relative_to(ROOT)}']) != source.encode():
        raise Refused('Exact migration must be reviewed and merged before application')
    backup = ROOT / 'ssl/maintenance-20261007/legacy-data-and-migration-history.json'
    if (backup.is_symlink() or not backup.is_file() or backup.stat().st_uid != os.getuid() or
        backup.stat().st_mode & 0o077 or
        hashlib.sha256(backup.read_bytes()).hexdigest() != '258a99bdf58f74bd0cb4a534ca5ebe7e01e0de812795809d0f3ba3d9177c9450'):
        raise Refused('Reviewed private legacy/history snapshot required')
    return {'independent_review_matches': True, 'reviewed_source_merged': True,
            'private_snapshot_matches': True, 'admission': 'closed'}


def reconcile(builder, source, manifest):
    # Both queries use fresh, read-only bounded sessions. An absent or incorrect
    # original install is a failed reconciliation, never permission to retry.
    sql_file(ROOT / 'services/vonneumann/db-contract/forward/verify.sql')
    quoted = "'" + source.replace("'", "''") + "'"
    query = ("BEGIN READ ONLY; SET LOCAL statement_timeout='8s'; SET LOCAL lock_timeout='500ms'; "
             f"SELECT jsonb_build_object('history_matches',EXISTS(SELECT 1 FROM supabase_migrations.schema_migrations "
             f"WHERE version='{builder.VERSION}' AND name='{builder.NAME}' AND statements=ARRAY[{quoted}])) AS receipt; ROLLBACK;")
    path = ROOT / 'ssl/maintenance-20261007' / ('postflight-' + uuid.uuid4().hex + '.sql')
    private_write(path, query)
    result = sql_file(path)
    # Management API returns the final result set; verify release separately so
    # this acceptance does not assume multi-statement result aggregation.
    if result != [{'receipt': {'history_matches': True}}]:
        raise Refused('Original committed migration history did not reconcile')
    path.unlink()
    query = ("BEGIN READ ONLY; SET LOCAL statement_timeout='8s'; SET LOCAL lock_timeout='500ms'; "
             "SET LOCAL ROLE vn_contract_owner; SELECT jsonb_build_object('release_sha256',release_sha256,"
             "'state',state,'epoch',epoch) AS release FROM vn_release.state WHERE singleton; ROLLBACK;")
    path = ROOT / 'ssl/maintenance-20261007' / ('release-' + uuid.uuid4().hex + '.sql')
    private_write(path, query)
    result = sql_file(path)
    expected = [{'release': {'release_sha256': manifest['release_sha256'], 'state': 'closed', 'epoch': 0}}]
    if result != expected:
        raise Refused('Original closed release did not reconcile')
    path.unlink()
    return {'fresh_catalog_verified': True, 'original_history_matches': True,
            'release_sha256': manifest['release_sha256'], 'admission': 'closed', 'epoch': 0}


def apply(builder, source, manifest):
    gates = preflight(builder, source, manifest)
    record = {'request_id': str(uuid.uuid4()), 'target': manifest['target'],
              'migration_sha256': manifest['migration_sha256'], 'version': builder.VERSION,
              'status': 'outcome_unknown_until_fresh_postflight', 'gates': gates}
    # Existence of this original operation prevents a blind second application.
    private_write(STATE, json.dumps(record, indent=2) + '\n')
    path = STATE.with_name('original-closed-install.sql')
    private_write(path, history_wrapper(source, builder.VERSION, builder.NAME))
    try:
        sql_file(path)
    except Refused:
        print(json.dumps({'application_reply': 'uncertain_or_rejected', 'automatic_retry': False}))
    acceptance = reconcile(builder, source, manifest)
    record.update(status='committed_and_verified_closed', acceptance=acceptance)
    save_state(record)
    return acceptance


def main():
    action = sys.argv[1] if len(sys.argv) == 2 else 'verify'
    if action not in ('verify', 'preflight', 'apply', 'reconcile'):
        raise Refused('Use verify, preflight, apply or original-outcome reconcile')
    builder, source, manifest = artifacts()
    identity = targets()
    if action == 'verify':
        outcome = {'migration_sha256': manifest['migration_sha256'], 'version': builder.VERSION}
    elif action == 'preflight':
        outcome = preflight(builder, source, manifest)
    elif action == 'apply':
        outcome = apply(builder, source, manifest)
    else:
        retained = json.loads(STATE.read_text())
        if (retained.get('migration_sha256'), retained.get('version'), retained.get('target')) != (
            manifest['migration_sha256'], builder.VERSION, manifest['target']):
            raise Refused('Original operation identity differs')
        outcome = reconcile(builder, source, manifest)
        retained.update(status='committed_and_verified_closed', acceptance=outcome)
        save_state(retained)
    print(json.dumps({'targets': identity, 'action': action, 'outcome': outcome}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc) if isinstance(exc, Refused) else 'Dashboard operation refused; private diagnostics suppressed', file=sys.stderr)
        raise SystemExit(1)
