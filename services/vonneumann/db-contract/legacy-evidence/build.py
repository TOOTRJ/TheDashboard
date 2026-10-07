"""Offline, digest-pinned legacy evidence component. Never accepts a connection.

The catalog oracle is reused verbatim apart from its schema-qualified helper.
The B1 classifier's identity call alone uses the proved limited-installer bridge.
This remains a rehearsal component, not a migration or cloud provisioner.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
DEPENDENCIES = {
    'legacy_catalog.sql': 'adb9a26b619f679a8b54e369c7808d352ae7f136a2b15ad08ae38557e06f2e66',
    '003_legacy_retirement.sql': 'eb0b5d31f01c5dd7b9eba5a9107fd6c92c7c5ec442bc087402c65f4f193702a7',
}


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def sources() -> dict[str, str]:
    result = {}
    for name, digest in DEPENDENCIES.items():
        value = (HERE.parent / name).read_text()
        if sha(value) != digest:
            raise ValueError('Reviewed legacy dependency changed: ' + name)
        result[name] = value
    return result


def retirement() -> str:
    value = sources()['003_legacy_retirement.sql']
    if value.count('auth.uid()') != 1:
        raise ValueError('Legacy identity anchor changed')
    value = value.replace('auth.uid()', 'vn_identity.owner_id()')
    schema = 'CREATE SCHEMA vn_legacy AUTHORIZATION vn_contract_owner;\n'
    if value.count(schema) != 1:
        raise ValueError('Legacy schema anchor changed')
    value = value.replace(schema,schema+'SET LOCAL ROLE vn_contract_owner;\n')
    anchor = 'CREATE FUNCTION vn_legacy.classify_run(run uuid) RETURNS jsonb'
    if value.count(anchor) != 1:
        raise ValueError('Legacy classifier creation anchor changed')
    value = value.replace(anchor, 'GRANT USAGE,CREATE ON SCHEMA vn_legacy TO postgres;\nRESET ROLE;\n'+anchor)
    tail = ('GRANT USAGE ON SCHEMA vn_legacy TO authenticated;\n'
            'GRANT EXECUTE ON FUNCTION vn_legacy.classify_run(uuid) TO authenticated;\nRESET ROLE;\nCOMMIT;\n')
    if value.count(tail) != 1:
        raise ValueError('Legacy classifier grant anchor changed')
    # Preserved legacy RLS expressions call managed auth.uid() directly. Create
    # the bounded read-only classifier using existing installer authority;
    # never broaden managed Auth grants for the private owner.
    return value.replace(tail,
        'GRANT EXECUTE ON FUNCTION vn_legacy.classify_run(uuid) TO authenticated;\n'
        'SET LOCAL ROLE vn_contract_owner;\nGRANT USAGE ON SCHEMA vn_legacy TO authenticated;\n'
        'REVOKE USAGE,CREATE ON SCHEMA vn_legacy FROM postgres;\nRESET ROLE;\nCOMMIT;\n')



def build() -> tuple[str, dict]:
    catalog = sources()['legacy_catalog.sql']
    anchor = 'CREATE FUNCTION pg_temp.vn_legacy_tables()'
    if catalog.count(anchor) != 1:
        raise ValueError('Legacy oracle anchor changed')
    catalog = catalog[catalog.index(anchor):].replace('pg_temp.vn_legacy_', 'vn_legacy_evidence.')
    prefix, body = (HERE / 'contract.sql').read_text().split('-- PINNED_CATALOG_ORACLE\n')
    sql = prefix + catalog + '\n' + body
    # Reuse the reviewed narrow $$ function grammar to enumerate every overload.
    spec = importlib.util.spec_from_file_location('v5_manifest_builder', HERE.parent / 'v5/build.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    functions = builder.functions(sql)
    manifest = {
        'version': 1, 'milestone': 'DB-03A2D3B2D1',
        'mode': 'isolated_legacy_evidence_rehearsal_only',
        'production_application_available': False,
        'dependencies_sha256': DEPENDENCIES,
        'retirement_composition_sha256': sha(retirement()),
        'classifier_owner': 'postgres',
        'sources_sha256': {'build.py': sha(Path(__file__).read_text()),
                           'contract.sql': sha((HERE / 'contract.sql').read_text())},
        'package_sha256': sha(sql),
        'functions': [{'signature': builder.signature(m), 'sha256': sha(m[0])}
                      for _, m in sorted(functions.items())],
        'tables': re.findall(r'^CREATE TABLE (vn_\w+\.\w+)', sql, re.M),
        'indexes': [{'name':name,'table':table} for name,table in
                    re.findall(r'^CREATE INDEX ([a-z_]+) ON (vn_\w+\.\w+)',sql,re.M)],
        'attestor_role': {'name':'vn_legacy_attestor','login':False,'inherit':False,
                         'superuser':False,'bypassrls':False,'createrole':False},
        'legacy_trigger': {'name':'vn_legacy_evidence_changed','timing':'AFTER',
                           'events':['INSERT','UPDATE','DELETE','TRUNCATE'],'level':'STATEMENT','enabled':'ALWAYS'},
        'legacy_tables': ['vn_colonies', 'vn_fitness_snapshots', 'vn_generation_stats', 'vn_probes', 'vn_trades'],
        'authenticated': ['vn_legacy_evidence.status(uuid)',
                          'vn_legacy_evidence.archive(uuid,uuid,uuid)',
                          'vn_legacy_evidence.history(uuid,bigint,integer)'],
        'attestor': ['vn_legacy_evidence.capture(uuid,uuid)',
                     'vn_legacy_evidence.attest(uuid,uuid,uuid,jsonb,jsonb)',
                     'vn_legacy_evidence.invalidate(uuid,uuid,text)'],
        'private_tables_exposed': False, 'row_limit': 50000,
        'snapshot_byte_limit': 33554432, 'document_byte_limit': 65536,
        'lock_timeout_ms': 500, 'statement_timeout_ms': 8000,
        'history_page_limit': 100, 'exposure_limit': 200,
        'evidence_lifetime_seconds': 86400,
        'open_gates': ['external_evidence_authenticity_and_managed_attestor_credential',
                       'complete_forward_composition_catalog_overlap_rollback',
                       'selected_service_browser_and_DB03A3_hosted_acceptance'],
    }
    return sql, manifest


if __name__ == '__main__':
    sql, manifest = build()
    (HERE / 'package.sql').write_text(sql)
    (HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
