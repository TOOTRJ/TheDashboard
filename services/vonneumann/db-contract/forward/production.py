"""Build the reviewed Dashboard-only, closed forward migration without cloud I/O.

This is the deliberate adoption wrapper for the hash-pinned complete package,
not a fixture bootstrap. Only independently captured catalog/history values are
inputs. The scoped operator records this file in migration history atomically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
VERSION = '20261007010000'
NAME = 'vonneumann_closed_v5'
REVIEW = ROOT / 'supabase/audits/2026-10-07-forward-install-review.json'
MIGRATION = ROOT / f'supabase/migrations/{VERSION}_{NAME}.sql'
MANIFEST = ROOT / 'supabase/audits/2026-10-07-forward-install-manifest.json'


def sha(source):
    return hashlib.sha256(source.encode()).hexdigest()


def literal(value):
    return "'" + json.dumps(value, separators=(',', ':')).replace("'", "''") + "'::jsonb"


def build():
    review = json.loads(REVIEW.read_text())
    manifest = json.loads((HERE / 'manifest.json').read_text())
    package = (HERE / 'package.sql').read_text()
    if (review['target'] != manifest['target'] or
        review['release_sha256'] != manifest['release_sha256'] or
        sha(package) != manifest['package_sha256'] or
        not package.startswith('BEGIN;\n') or not package.endswith('COMMIT;\n') or
        any(item['version'] == VERSION for item in review['migration_catalog'])):
        raise ValueError('Reviewed production dependency differs')
    expected = {'version': 1, 'target': review['target'],
                'release_sha256': review['release_sha256'],
                'migration_catalog': review['migration_catalog']}
    legacy = (HERE.parent / 'legacy_catalog.sql').read_text()
    history = (HERE / 'review.sql').read_text()
    # Temp objects and the compatibility opt-in marker belong to the same
    # bounded transaction. The marker is not an authorization boundary.
    legacy = legacy.replace('CREATE TEMP TABLE dashboard_legacy_review (review jsonb NOT NULL);',
                            'CREATE TEMP TABLE dashboard_legacy_review (review jsonb NOT NULL) ON COMMIT DROP;')
    history = history.replace('CREATE TEMP TABLE dashboard_forward_review (review jsonb NOT NULL);',
                              'CREATE TEMP TABLE dashboard_forward_review (review jsonb NOT NULL) ON COMMIT DROP;')
    source = ("-- Authorized exact Dashboard closed installation. Do not apply historical local drafts.\n"
              "-- Verify provider identities outside SQL; prepare backup and additive retirement first.\n"
              "BEGIN;\nSET LOCAL transaction_timeout='25s';\n"
              "SET LOCAL lock_timeout='500ms'; SET LOCAL statement_timeout='8s';\n"
              "SET LOCAL dashboard.contract_rehearsal='db03a1-isolated';\n" + legacy + '\n' + history + '\n' +
              'INSERT INTO pg_temp.dashboard_legacy_review VALUES (' + literal(review['legacy_catalog']) + ');\n' +
              'INSERT INTO pg_temp.dashboard_forward_review VALUES (' + literal(expected) + ');\n' +
              package.removeprefix('BEGIN;\n').removesuffix('COMMIT;\n') +
              "SET LOCAL ROLE vn_contract_owner;\nDO $$ BEGIN\n"
              " IF NOT EXISTS(SELECT 1 FROM vn_release.state WHERE singleton AND state='closed' AND epoch=0)\n"
              " OR EXISTS(SELECT 1 FROM vn_access.bindings) OR EXISTS(SELECT 1 FROM vn_durability.runs) THEN\n"
              " RAISE EXCEPTION 'production_closed_install_postcondition_failed'; END IF;\n"
              "END $$; RESET ROLE;\nCOMMIT;\n")
    return source, {'version': VERSION, 'name': NAME, 'mode': 'reviewed_dashboard_closed_install',
                    'target': review['target'], 'release_sha256': review['release_sha256'],
                    'package_sha256': manifest['package_sha256'], 'migration_sha256': sha(source),
                    'review_sha256': sha(REVIEW.read_text()), 'transaction_timeout_seconds': 25,
                    'installed_admission': 'closed', 'credentials_provisioned': False,
                    'api_exposed': False, 'history_recording': 'scoped operator appends exact source before COMMIT',
                    'rollback': 'drain then original-ID vn_release.transition to retired; retain all history'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source, manifest = build()
    for path, value in ((MIGRATION, source), (MANIFEST, json.dumps(manifest, indent=2, sort_keys=True) + '\n')):
        if args.check:
            if path.read_text() != value:
                raise SystemExit('Reviewed production artifact differs: ' + path.name)
        else:
            path.write_text(value)
    print(json.dumps({'check': args.check, 'version': VERSION, 'migration_sha256': sha(source),
                      'admission': 'closed', 'credentials_provisioned': False}))


if __name__ == '__main__':
    main()
