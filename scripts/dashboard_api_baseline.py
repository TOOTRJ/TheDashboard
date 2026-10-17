"""Pure SQL emission for the independently declared two-table API baseline.

No database/HTTP client, credential lookup or implicit execution exists here.
Native templates must first be frozen from the reviewed owned constructor probe.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


DIRECTORY = Path(__file__).resolve().parents[1] / 'supabase' / 'api-baseline'
TABLES = ('market_sentiment', 'test_events')
ROLES = ('anon', 'authenticated', 'service_role')
TABLE_PRIVILEGES = ('DELETE', 'INSERT', 'MAINTAIN', 'REFERENCES', 'SELECT', 'TRIGGER', 'TRUNCATE', 'UPDATE')
COLUMN_PRIVILEGES = ('INSERT', 'REFERENCES', 'SELECT', 'UPDATE')
COLUMNS = {
    'market_sentiment': ('id', 'score', 'sentiment', 'summary', 'key_factors', 'date', 'source', 'created_at'),
    'test_events': ('id', 'payload', 'source', 'created_at'),
}
# This explicit external pin is replaced only after review of the independent
# constructor probe. Computing a replacement from a caller's file is forbidden.
EXPECTED_FILE_SHA256 = '74f3a96c7e3d3eb759e43307752abbb0541e8d7288ad3fdea23aed4c13488568'
REFUSAL = 'dashboard_api_baseline_refused'


def _read(name: str) -> str:
    path = DIRECTORY / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 262144:
        raise ValueError('dashboard_api_baseline_source_refused')
    return path.read_text(encoding='utf-8')


def _duplicates_refused(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('dashboard_api_baseline_duplicate_expectation_key')
        result[name] = value
    return result


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), sort_keys=True, allow_nan=False)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _expected() -> dict:
    raw = _read('expected.json')
    if hashlib.sha256(raw.encode('utf-8')).hexdigest() != EXPECTED_FILE_SHA256:
        raise ValueError('dashboard_api_baseline_expectation_not_frozen')
    value = json.loads(raw, object_pairs_hook=_duplicates_refused,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_expectation')))
    if (type(value) is not dict
            or set(value) != {'format', 'status', 'constructor_sha256', 'catalog_sha256', 'structure'}
            or value['format'] != 'dashboard-api-independent-native-expectation-v1'
            or value['status'] != 'reviewed-owned-constructor'
            or value['constructor_sha256'] != hashlib.sha256(_read('constructor.sql').encode()).hexdigest()
            or value['catalog_sha256'] != hashlib.sha256(_read('catalog.sql').encode()).hexdigest()
            or type(value['structure']) is not dict or set(value['structure']) != {'tables'}
            or type(value['structure']['tables']) is not dict
            or set(value['structure']['tables']) != set(TABLES)):
        raise ValueError('dashboard_api_baseline_expectation_refused')
    return value['structure']


def catalog_sql() -> str:
    """Return one scoped read-only JSON SELECT, not an observation executor."""
    return _read('catalog.sql').rstrip() + '\n'


def _catalog_expression() -> str:
    source = catalog_sql().strip()
    if not source.endswith(';'):
        raise ValueError('dashboard_api_baseline_catalog_source_refused')
    return '(' + source[:-1] + ')'


def _sections() -> dict[str, str]:
    source = _read('constructor.sql')
    result = {}
    for table in TABLES:
        matches = re.findall(r'^-- BEGIN ' + table + r'\n(.*?)^-- END ' + table + r'$',
                             source, flags=re.MULTILINE | re.DOTALL)
        if len(matches) != 1:
            raise ValueError('dashboard_api_baseline_constructor_source_refused')
        result[table] = matches[0].strip()
    return result


def _execute_constructor(table: str) -> str:
    # Fixed reviewed source, never a request-derived table/SQL identifier.
    return '\n'.join('EXECUTE ' + _literal(statement.strip()) + ';'
                     for statement in _sections()[table].split(';') if statement.strip())


def _permission(table: str, *, broad: bool) -> dict:
    grants = []
    for role in ('postgres',) + ROLES:
        wanted = TABLE_PRIVILEGES if role == 'postgres' or broad else ('INSERT', 'SELECT') if role == 'service_role' else ()
        grants.extend({'grantor': 'postgres', 'grantee': role, 'privilege': privilege, 'grantable': False}
                      for privilege in wanted)
    grants.sort(key=lambda item: (item['grantee'], item['privilege'], item['grantor']))
    effective = []
    for role in ROLES:
        wanted = set(TABLE_PRIVILEGES if broad else ('INSERT', 'SELECT') if role == 'service_role' else ())
        effective.append({'role': role, 'table': {p: p in wanted for p in TABLE_PRIVILEGES},
                          'columns': [{'name': column, 'privileges': {p: p in wanted for p in COLUMN_PRIVILEGES}}
                                      for column in COLUMNS[table]]})
    return {'grants': grants, 'column_acl_present': False, 'adjunct_acl_present': False, 'effective': effective}


def _json_map(*, broad: bool) -> str:
    return _literal(_json({table: _permission(table, broad=broad) for table in TABLES})) + '::pg_catalog.jsonb'


def _refuse(code: str) -> str:
    return "RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='" + REFUSAL + "', DETAIL='" + code + "';"


def _guards(variable: str) -> str:
    # This is an offline installer profile, not authenticated Management-API
    # identity. session_user is recorded, not guessed to be postgres.
    roles = [{'name': name, 'superuser': False, 'inherit': True, 'login': False,
              'bypass_rls': name == 'service_role', 'create_role': False, 'create_db': False,
              'replication': False, 'schema_usage': True, 'schema_create': False,
              'outgoing_memberships': 0} for name in ROLES]
    return f"""
IF {variable}->>'format' IS DISTINCT FROM 'dashboard-api-two-table-catalog-v1'
   OR {variable}->'complete' IS DISTINCT FROM 'true'::pg_catalog.jsonb
   OR pg_catalog.octet_length({variable}::text)>262144 THEN {_refuse('catalog_incomplete')} END IF;
IF {variable}#>>'{{context,server_version_num}}' IS DISTINCT FROM '170006'
   OR {variable}#>>'{{context,current_user}}' IS DISTINCT FROM 'postgres'
   OR {variable}#>>'{{context,database_encoding}}' IS DISTINCT FROM 'UTF8'
   OR {variable}#>'{{context,roles}}' IS DISTINCT FROM {_literal(_json(roles))}::pg_catalog.jsonb
   OR {variable}#>>'{{context,schema_owner}}' IS NULL
   OR pg_catalog.current_setting('transaction_isolation')<>'read committed'
   OR pg_catalog.current_setting('lock_timeout')<>'1s'
   OR pg_catalog.current_setting('statement_timeout')<>'10s'
   THEN {_refuse('installer_or_role_context')} END IF;
"""


def _collision_guard(variable: str) -> str:
    relation_expected = {}
    for table in TABLES:
        relation_expected[table] = {'name': table, 'kind': 'r', 'root': table, 'label': 'table:' + table}
    for table, index in (('market_sentiment', 'market_sentiment_pkey'),
                         ('market_sentiment', 'market_sentiment_date_key'),
                         ('market_sentiment', 'idx_market_sentiment_date'),
                         ('test_events', 'test_events_pkey'), ('test_events', 'idx_test_events_created_at')):
        relation_expected[index] = {'name': index, 'kind': 'i', 'root': table, 'label': 'index:' + index}
    type_expected = {}
    for table in TABLES:
        type_expected[table] = {'name': table, 'kind': 'c', 'root': table, 'label': 'row-type:' + table}
        type_expected['_' + table] = {'name': '_' + table, 'kind': 'b', 'root': table, 'label': 'array-type:' + table}
    return f"""
FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements({variable}#>'{{collisions,relations}}') LOOP
    IF item IS DISTINCT FROM ({_literal(_json(relation_expected))}::pg_catalog.jsonb)->(item->>'name')
       THEN {_refuse('relation_name_collision')} END IF;
END LOOP;
FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements({variable}#>'{{collisions,types}}') LOOP
    IF item IS DISTINCT FROM ({_literal(_json(type_expected))}::pg_catalog.jsonb)->(item->>'name')
       THEN {_refuse('type_name_collision')} END IF;
END LOOP;
"""


def _fresh_defaults_guard() -> str:
    return f"""
IF EXISTS (
    SELECT 1 FROM pg_catalog.pg_default_acl d
    CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) x
    WHERE d.defaclrole=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='postgres')
      AND d.defaclobjtype='r'
      AND (d.defaclnamespace=0 OR d.defaclnamespace=(SELECT oid FROM pg_catalog.pg_namespace WHERE nspname='public'))
      AND (x.grantee NOT IN (SELECT oid FROM pg_catalog.pg_roles WHERE rolname IN ('postgres','anon','authenticated','service_role'))
           OR x.grantor<>(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='postgres') OR x.is_grantable)
) THEN {_refuse('unreviewed_creation_default_acl')} END IF;
"""


def _transaction(body: str) -> str:
    return """-- Candidate offline SQL. Hosted identity and quiescent administrative
-- ACL/role/default/schema context require separate review; relation locks do
-- not exclude GRANT/REVOKE or global administration. No automatic retry.
BEGIN ISOLATION LEVEL READ COMMITTED;
SET LOCAL search_path=pg_catalog,pg_temp;
SET LOCAL lock_timeout='1s';
SET LOCAL statement_timeout='10s';
DO $dashboard_api_baseline$
DECLARE
    snapshot pg_catalog.jsonb;
    before_snapshot pg_catalog.jsonb;
    after_snapshot pg_catalog.jsonb;
    item pg_catalog.jsonb;
    target pg_catalog.text;
    existing pg_catalog.text[];
BEGIN
""" + body + "\nEND;\n$dashboard_api_baseline$ LANGUAGE plpgsql;\nCOMMIT;\n"


def constructor_sql() -> str:
    """Explicit fresh-fixture constructor. Refuses any planned-name collision.

    This produces the independent native observation used for a later frozen
    expectation. It never synthesizes or accepts a golden catalog itself.
    """
    query = _catalog_expression()
    body = f'snapshot := {query};\n' + _guards('snapshot')
    body += f"""
IF snapshot#>'{{structure,tables}}'<>'{{}}'::pg_catalog.jsonb
   OR snapshot#>'{{collisions,relations}}'<>'[]'::pg_catalog.jsonb
   OR snapshot#>'{{collisions,types}}'<>'[]'::pg_catalog.jsonb
   THEN {_refuse('fresh_constructor_requires_absence')} END IF;
""" + _fresh_defaults_guard()
    for table in TABLES:
        body += _execute_constructor(table) + '\n'
    body += f'after_snapshot := {query};\n' + _guards('after_snapshot') + _collision_guard('after_snapshot')
    body += f"""
IF after_snapshot->'permissions' IS DISTINCT FROM {_json_map(broad=False)}
   OR after_snapshot->'context' IS DISTINCT FROM snapshot->'context'
   OR (SELECT pg_catalog.count(*) FROM pg_catalog.jsonb_object_keys(after_snapshot#>'{{structure,tables}}'))<>2
   THEN {_refuse('fresh_constructor_postcondition')} END IF;
"""
    return _transaction(body)


def baseline_sql(*, apply_acl: bool = False) -> str:
    """Baseline-only by default; True is permissions-only and refuses absence.

    Matching existing baseline/repeat paths create no objects or ACL writes.
    No request/caller can supply expected templates or execute the returned SQL.
    """
    if type(apply_acl) is not bool:
        raise ValueError('dashboard_api_baseline_mode_must_be_boolean')
    expected = _expected()
    query = _catalog_expression()
    gold = _literal(_json(expected)) + '::pg_catalog.jsonb'
    body = """
-- Fixed order. These relation locks protect table structure, not admin ACLs.
FOR target IN SELECT v FROM pg_catalog.unnest(ARRAY['market_sentiment','test_events']) v LOOP
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname='public' AND c.relname=target AND c.relkind<>'r') THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='dashboard_api_baseline_refused', DETAIL='wrong_relation_kind';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname='public' AND c.relname=target
                 AND pg_catalog.pg_get_userbyid(c.relowner)<>'postgres') THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='dashboard_api_baseline_refused', DETAIL='wrong_relation_owner';
    END IF;
    IF pg_catalog.to_regclass('public.' || target) IS NOT NULL THEN
        EXECUTE pg_catalog.format('LOCK TABLE public.%I IN ACCESS EXCLUSIVE MODE',target);
    END IF;
END LOOP;
"""
    body += f'before_snapshot := {query};\n' + _guards('before_snapshot') + _collision_guard('before_snapshot')
    body += f"""
existing := ARRAY(SELECT k FROM pg_catalog.jsonb_object_keys(before_snapshot#>'{{structure,tables}}') k ORDER BY k);
FOR target IN SELECT pg_catalog.unnest(existing) LOOP
    IF before_snapshot#>ARRAY['structure','tables',target] IS DISTINCT FROM ({gold})#>ARRAY['tables',target]
       THEN {_refuse('structural_drift')} END IF;
    IF before_snapshot#>ARRAY['permissions',target] IS DISTINCT FROM ({_json_map(broad=True)})->target
       AND before_snapshot#>ARRAY['permissions',target] IS DISTINCT FROM ({_json_map(broad=False)})->target
       THEN {_refuse('unreviewed_effective_acl')} END IF;
END LOOP;
"""
    if apply_acl:
        body += f"IF pg_catalog.cardinality(existing)<>2 THEN {_refuse('permissions_requires_both_tables')} END IF;\n"
        for table in TABLES:
            body += f"""
IF before_snapshot#>'{{permissions,{table}}}' IS DISTINCT FROM ({_json_map(broad=False)})->'{table}' THEN
    REVOKE ALL PRIVILEGES ON TABLE public.{table} FROM anon,authenticated,service_role;
    GRANT SELECT,INSERT ON TABLE public.{table} TO service_role;
END IF;
"""
    else:
        body += _fresh_defaults_guard()
        for table in TABLES:
            body += f"IF NOT '{table}'=ANY(existing) THEN\n{_execute_constructor(table)}\nEND IF;\n"
    # Separate volatile SPI statements get READ COMMITTED rechecks. No STABLE
    # installed helper, reference-table creation, or extra temp/catalog object.
    body += f'after_snapshot := {query};\n' + _guards('after_snapshot') + _collision_guard('after_snapshot')
    body += f"""
IF after_snapshot->'structure' IS DISTINCT FROM {gold}
   OR after_snapshot->'context' IS DISTINCT FROM before_snapshot->'context'
   OR NOT ((after_snapshot->'identities') @> (before_snapshot->'identities'))
   THEN {_refuse('postcondition_drift')} END IF;
"""
    for table in TABLES:
        if apply_acl:
            body += f"IF after_snapshot#>'{{permissions,{table}}}' IS DISTINCT FROM ({_json_map(broad=False)})->'{table}' THEN {_refuse('permissions_postcondition')} END IF;\n"
        else:
            body += f"""
IF '{table}'=ANY(existing) THEN
    IF after_snapshot#>'{{permissions,{table}}}' IS DISTINCT FROM before_snapshot#>'{{permissions,{table}}}'
       THEN {_refuse('existing_acl_changed')} END IF;
ELSE
    IF after_snapshot#>'{{permissions,{table}}}' IS DISTINCT FROM ({_json_map(broad=False)})->'{table}'
       THEN {_refuse('fresh_acl_postcondition')} END IF;
END IF;
"""
    return _transaction(body)


if __name__ == '__main__':
    raise SystemExit('Library only: SQL execution and credential handling are deliberately absent.')
