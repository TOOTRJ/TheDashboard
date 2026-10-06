"""Deterministic, offline SQL extraction. Never accepts a DSN or applies SQL.

Input digests pin the reviewed laboratory. Public economic entrypoints are
explicit source, not rewritten multi-version functions. The reference scanner
is specific to these pinned $$-quoted sources, not a general SQL parser.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
SOURCES = {
    '001_fenced_commands.sql': '3312ccf8c28154cc35ef29aa36e66ef016b3e7e76c2a21a0e301b0b1ad30d4f2',
    '002_read_projections.sql': '7b50a45244455dcd3b076bfb60ac02a512d7e59a8c204d3932279ebad4446fe0',
    '004_installer_boundary.sql': 'd3be3f59ef64e95bf5c78aeaf29b484a7e09e2b9f3f76a99210fa9cdac890d12',
}
ECONOMIC = {'create_run','heartbeat','commit_command','get_command','interrupt_expired'}
RELAY = {'read_outbox','acknowledge_event','accept_event'}
READ = {'page','events','archive_run'}
FUNCTION = re.compile(r'^CREATE FUNCTION (vn_\w+\.\w+)\(([\s\S]*?)\)\s*RETURNS[\s\S]*?\$\$([\s\S]*?)\$\$;', re.M)
REFERENCE = re.compile(r'\b(vn_\w+\.\w+)\s*\(')


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def functions(source: str) -> dict[str, re.Match]:
    matches = list(FUNCTION.finditer(source))
    result = {m[1]: m for m in matches}
    if len(matches) != len(result) or len(matches) != len(re.findall(r'^CREATE FUNCTION ', source, re.M)):
        raise ValueError('Unreviewed function grammar or overload')
    return result


def once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError('Extraction anchor changed: ' + old[:60])
    return source.replace(old, new)


def signature(match: re.Match) -> str:
    args = []
    for arg in (match[2].split(',') if match[2].strip() else []):
        words = arg.strip().split()
        if len(words) < 2 or not re.fullmatch(r'(?:[a-z_]+\.)?[a-z_]+(?:\[\])?', words[1]):
            raise ValueError('Unreviewed argument grammar')
        args.append(words[1])
    return match[1] + '(' + ','.join(args) + ')'


def build() -> tuple[str, dict]:
    sources = {}
    for name, digest in SOURCES.items():
        source = (HERE.parent / name).read_text()
        if sha(source) != digest:
            raise ValueError('Reviewed dependency source changed: ' + name)
        sources[name] = source
    entries = (HERE / 'entrypoints.sql').read_text()
    core = sources['001_fenced_commands.sql']
    projections = sources['002_read_projections.sql']
    # No historical public admission; adapt only the curated v5 surface.
    projections = once(projections, "state.command_version NOT IN(4,5)", 'state.command_version<>5')
    projections = once(projections, "CASE WHEN state.command_version=5 THEN 'paper' ELSE 'synthetic_rehearsal' END", "'paper'")
    if projections.count('auth.uid()') != 3:
        raise ValueError('Identity dependency changed')
    projections = projections.replace('auth.uid()', 'vn_identity.owner_id()')
    relations = set(re.findall(r'^CREATE TABLE (vn_\w+\.\w+)',core+'\n'+projections,re.M))
    all_core = functions(core)
    selected = functions(entries)
    projection_functions = functions(projections)
    roots = set(selected) | set(projection_functions)
    pool = all_core | selected | projection_functions
    pending = list(roots)
    needed = set()
    while pending:
        name = pending.pop()
        if name in needed:
            continue
        needed.add(name)
        refs = set(REFERENCE.findall(pool[name][3]))
        unknown = refs - set(pool) - relations - {'vn_identity.owner_id'}
        if unknown:
            raise ValueError('Unknown callable dependency: ' + repr(sorted(unknown)))
        pending.extend(refs & set(pool) - needed)
    forbidden = {'vn_durability.validate_transition_before','vn_durability.validate_transition_after',
                 'vn_durability.rehearsal_config','vn_durability.rehearsal_evaluation'}
    if needed & forbidden:
        raise ValueError('Historical public model accidentally retained')
    boundary = sources['004_installer_boundary.sql']
    boundary = once(boundary, 'COMMIT;\n', '')
    boundary = once(boundary, "rolname='vn_contract_owner') OR", "rolname IN ('vn_contract_owner','vn_economic','vn_relay')) OR")
    boundary += """
-- Capability roles are inert: no login, authenticator grant, or credential.
CREATE ROLE vn_economic NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
CREATE ROLE vn_relay NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
"""
    schema = core[core.index('CREATE SCHEMA vn_durability'):core.index('-- Trusted internal helpers:')]
    schema = once(schema, 'command_version IN (1,2,3,4,5)', 'command_version=5')
    schema = schema.replace('Version-3 candidate events','Provider-bound candidate events')
    # Raw core reads are not a supported API. No inert owner-read policies whose
    # presence could suggest a later table SELECT grant is safe.
    schema = re.sub(r'^CREATE POLICY owner_read .*\n', '', schema, flags=re.M)
    schema = once(schema, 'SET LOCAL ROLE vn_contract_owner;', '''SET LOCAL ROLE vn_contract_owner;
GRANT USAGE,CREATE ON SCHEMA vn_durability TO postgres;''')
    schema = once(schema, 'CREATE TABLE vn_durability.runs (', 'RESET ROLE;\nCREATE TABLE vn_durability.runs (')
    schema = once(schema, 'CREATE TABLE vn_durability.accounts (', '''ALTER TABLE vn_durability.runs OWNER TO vn_contract_owner;
SET LOCAL ROLE vn_contract_owner;
REVOKE USAGE,CREATE ON SCHEMA vn_durability FROM postgres;
CREATE TABLE vn_durability.accounts (''')
    helpers = '\n\n'.join(m[0] for name,m in all_core.items() if name in needed and name not in selected)
    proj_schema = projections[projections.index('CREATE SCHEMA vn_projection'):projections.index('-- Called only by the journal')]
    proj_body = projections[projections.index('-- Called only by the journal'):projections.index('-- Explicit schema/function grants only;')]
    sql = '''-- DB-03A2D3B2B canonical fresh v5 component, OFFLINE REVIEW ONLY.
-- Not a complete production cutover or migration. No application loads this SQL.
-- build.py --check reproduces this artifact; only owned isolated tests apply it.
''' + boundary + '\n' + schema + '\n' + helpers + '\n' + entries + '\nRESET ROLE;\n' + proj_schema + proj_body
    roles = 'PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay'
    grants = []
    metadata = []
    final_functions = functions(sql)
    for name, match in final_functions.items():
        leaf = name.split('.')[1]
        role = 'vn_economic' if leaf in ECONOMIC else 'vn_relay' if leaf in RELAY else 'authenticated' if leaf in READ else None
        # owner_id bridge belongs to postgres and grants only the private owner.
        if name == 'vn_identity.owner_id':
            role = 'vn_contract_owner'
        sig = signature(match)
        if role and role != 'vn_contract_owner':
            grants.append('GRANT EXECUTE ON FUNCTION ' + sig + ' TO ' + role + ';')
        metadata.append({'name': name, 'signature': sig, 'ddl_sha256': sha(match[0]),
                         'body_sha256': sha(match[3]), 'dependencies': sorted(set(REFERENCE.findall(match[3])) - relations),
                         'execute_role': role, 'security_definer': 'SECURITY DEFINER' in match[0].split('AS $$')[0]})
    sql += '\n-- Exact capabilities; no managed service_role economic authority.\n'
    for namespace in ('vn_durability','vn_projection','vn_read'):
        sql += f'REVOKE ALL ON SCHEMA {namespace} FROM {roles};\n'
        sql += f'REVOKE ALL ON ALL TABLES IN SCHEMA {namespace} FROM {roles};\n'
        sql += f'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {namespace} FROM {roles};\n'
    sql += 'REVOKE ALL ON DOMAIN vn_durability.balance FROM ' + roles + ';\n'
    sql += 'GRANT USAGE ON SCHEMA vn_durability TO vn_economic,vn_relay;\nGRANT USAGE ON SCHEMA vn_read TO authenticated,vn_relay;\n'
    sql += '\n'.join(grants) + '\n'
    expected = ',\n'.join("('%s','%s',%s,'%s')" %
        (m['signature'], m['body_sha256'], "'"+m['execute_role']+"'" if m['execute_role'] else 'NULL',
         'postgres' if m['name']=='vn_identity.owner_id' else 'vn_contract_owner') for m in metadata)
    postconditions = once((HERE / 'postconditions.sql').read_text(), '-- EXPECTED_FUNCTIONS', expected)
    postconditions = once(postconditions, '-- EXPECTED_FUNCTION_COUNT', str(len(metadata)))
    sql += postconditions + '\nRESET ROLE;\nCOMMIT;\n'
    manifest = {'mode': 'canonical_fresh_v5_offline_component', 'production_application_available': False,
                'admitted_command_versions': [5], 'sources_sha256': SOURCES,
                'entrypoints_sha256': sha(entries), 'postconditions_sha256': sha((HERE/'postconditions.sql').read_text()),
                'package_sha256': sha(sql), 'functions': metadata,
                'removed_core_functions': sorted(set(all_core) - needed),
                'schemas': ['vn_identity','vn_durability','vn_projection','vn_read'],
                'tables': sorted(re.findall(r'^CREATE TABLE (vn_\w+\.\w+)', sql, re.M)),
                'indexes': sorted(re.findall(r'^CREATE (?:UNIQUE )?INDEX (\w+)', sql, re.M)),
                'triggers': sorted(re.findall(r'^CREATE TRIGGER (\w+)', sql, re.M)),
                'object_ddl': [
                    {'name':m[1], 'kind':'table', 'ddl':m[0], 'ddl_sha256':sha(m[0])}
                    for m in re.finditer(r'^CREATE TABLE (vn_\w+\.\w+) \([\s\S]*?^\);',sql,re.M)
                ] + [
                    {'name':m[2], 'kind':m[1].lower(), 'ddl':m[0], 'ddl_sha256':sha(m[0])}
                    for m in re.finditer(r'^CREATE (?:UNIQUE )?(INDEX|TRIGGER|DOMAIN) (\w+(?:\.\w+)?)[\s\S]*?;',sql,re.M)
                ],
                'policies': [], 'capability_roles': ['vn_economic','vn_relay'],
                'credential_or_gateway_configuration': False}
    return sql, manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    sql, manifest = build()
    artifacts={'package.sql':sql,'manifest.json':json.dumps(manifest,indent=2,sort_keys=True)+'\n'}
    for name, body in artifacts.items():
        if args.check:
            if (HERE/name).read_text()!=body:
                raise SystemExit('Canonical artifact differs: ' + name)
        else:
            (HERE/name).write_text(body)
    print(json.dumps({'check':args.check,'functions':len(manifest['functions']),
                      'removed':manifest['removed_core_functions'],'package_sha256':manifest['package_sha256']}))

if __name__=='__main__':
    main()
