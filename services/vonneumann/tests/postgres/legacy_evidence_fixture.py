"""Owned synthetic cluster only; no real env, credentials, provider or DSN."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

from tests.postgres import harness, installer_fixture, canonical_fixture, legacy_fixture

HERE = Path(__file__).resolve().parents[2] / 'db-contract/legacy-evidence'
spec = importlib.util.spec_from_file_location('legacy_evidence_builder', HERE / 'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
ATTESTOR = 'vn_test_legacy_reviewer'
ADMIN = installer_fixture.ADMIN
BOUND = "BEGIN; SET LOCAL lock_timeout='500ms'; SET LOCAL statement_timeout='8s';\n"


def package() -> str:
    sql, manifest = builder.build()
    if sql != (HERE/'package.sql').read_text() or manifest != json.loads((HERE/'manifest.json').read_text()):
        raise ValueError('Legacy evidence component/manifest must be rebuilt and reviewed')
    return installer_fixture.MARKER + sql


def start(test_class):
    db = harness.IsolatedPostgres()
    test_class.addClassCleanup(db.close)
    db.start()
    db.sql('CREATE ROLE vn_test_admin LOGIN SUPERUSER;')
    db.sql(installer_fixture.HOSTED_BOOTSTRAP, role=ADMIN)
    db.sql(canonical_fixture.package(), timeout=30)
    bootstrap = legacy_fixture.legacy_bootstrap().replace(
        'CREATE ROLE authenticator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;','')
    # Only trusted local snapshot reconstruction uses the synthetic administrator.
    db.sql(bootstrap+'\nGRANT USAGE ON SCHEMA extensions TO postgres;', role=ADMIN)
    db.sql(legacy_fixture.captured_legacy_schema(), role='postgres')
    return db


def install(db, *, suffix=''):
    reviewed = legacy_fixture.review_sql(db)
    retired = builder.retirement().removesuffix('COMMIT;\n')
    source = package().removeprefix(installer_fixture.MARKER).replace('BEGIN;\n','',1)
    source = source.removesuffix('COMMIT;\n')
    db.sql(reviewed + retired + '\n' + source + '\n' + suffix + '\nCOMMIT;', timeout=20)


def reviewer(db):
    db.sql(f'''CREATE ROLE {ATTESTOR} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT vn_legacy_attestor TO {ATTESTOR} WITH ADMIN FALSE,INHERIT FALSE,SET TRUE;
''', role=ADMIN)


def call(db, expression, *, role='authenticated', owner=None, check=True):
    source=BOUND
    if owner is not None:
        source += 'SET LOCAL request.jwt.claim.sub='+legacy_fixture.literal(owner)+';\n'
    if role==ATTESTOR:
        source += 'SET LOCAL ROLE vn_legacy_attestor;\n'
    source+='SELECT '+expression+';\nCOMMIT;'
    result=db.sql(source, role=role, check=check, timeout=12)
    return json.loads(result.stdout.strip()) if check else result


def document(snapshot):
    now = datetime.now(timezone.utc)-timedelta(seconds=2)
    utc = lambda t:t.isoformat(timespec='microseconds').replace('+00:00','Z')
    return {'version':1, 'provenance':'legacy','owner_id':snapshot['owner_id'],'run_id':snapshot['run_id'],
        'drain':{'inventory_sha256':'1'*64,'evidence_sha256':'2'*64,'observed_at':utc(now),
            'writers':[{'identity':'synthetic-old-worker-process-1','release_sha256':'3'*64,
                        'drain_receipt_sha256':'4'*64,'state':'drained'}]},
        'reconciliation':{'evidence_sha256':'5'*64,'observed_at':utc(now+timedelta(seconds=1)),
            'scope':'legacy_records_and_external_exposure',
            'exposures':[{'identity':'legacy-record-'+trade,'trade_id':trade,'disposition':'unknown_retained',
                'evidence_sha256':'6'*64,'note':'Synthetic review; historical open row is not a verified on-chain holding.'}
                for trade in snapshot['open_trade_ids']]},
        'expires_at':utc(now+timedelta(hours=1))}


def literal_json(value):
    return legacy_fixture.literal(json.dumps(value))+'::jsonb'


def capture(db, ids):
    return call(db, 'vn_legacy_evidence.capture('+legacy_fixture.literal(ids['owner'])+','+
        legacy_fixture.literal(ids['run'])+')', role=ATTESTOR)


def attest(db, ids, *, snapshot=None, doc=None, request=None, check=True):
    snapshot = capture(db,ids) if snapshot is None else snapshot
    doc = document(snapshot) if doc is None else doc
    request = str(uuid4()) if request is None else request
    args=[legacy_fixture.literal(request),legacy_fixture.literal(ids['owner']),legacy_fixture.literal(ids['run']),
          literal_json(snapshot),literal_json(doc)]
    return call(db,'vn_legacy_evidence.attest('+','.join(args)+')',role=ATTESTOR,check=check),snapshot,doc
