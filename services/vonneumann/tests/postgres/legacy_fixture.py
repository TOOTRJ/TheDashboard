"""Synthetic rows in the captured legacy catalog; no historical scripts/secrets.

This file is for an owned offline PostgreSQL fixture only. SQL definitions come
from the committed, reviewed metadata snapshot, never a live connection/string.
"""
from __future__ import annotations
import json
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
SNAPSHOT = ROOT / 'supabase/audits/2026-10-05-vonneumann-inventory.json'
CONTRACT_DIR = Path(__file__).resolve().parents[2] / 'db-contract'
CATALOG = CONTRACT_DIR / 'legacy_catalog.sql'
RETIREMENT = CONTRACT_DIR / '003_legacy_retirement.sql'
MARKER = "SET dashboard.contract_rehearsal='db03a1-isolated';\n"
TABLES = ('vn_colonies','vn_fitness_snapshots','vn_generation_stats','vn_probes','vn_trades')


def ident(value: str) -> str:
    return '"' + value.replace('"','""') + '"'


def literal(value) -> str:
    if value is None: return 'NULL'
    return "'" + str(value).replace("'", "''") + "'"


def legacy_bootstrap() -> str:
    return """
CREATE ROLE supabase_admin NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE authenticator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE anon INHERIT; ALTER ROLE authenticated INHERIT; ALTER ROLE service_role INHERIT;
GRANT anon,authenticated,service_role TO authenticator WITH INHERIT FALSE, SET TRUE;
GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role,authenticator;
CREATE SCHEMA extensions;
CREATE EXTENSION moddatetime WITH SCHEMA extensions;
ALTER FUNCTION extensions.moddatetime() OWNER TO supabase_admin;
CREATE FUNCTION public.vn_set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at=now(); RETURN NEW; END $$;
GRANT EXECUTE ON FUNCTION public.vn_set_updated_at() TO anon,authenticated,service_role;
""" + '\n'.join(
        f'ALTER DEFAULT PRIVILEGES FOR ROLE {role} IN SCHEMA public GRANT ALL ON {kind} '
        'TO postgres,anon,authenticated,service_role;'
        for role in ('postgres','supabase_admin') for kind in ('TABLES','SEQUENCES','FUNCTIONS'))


def captured_legacy_schema() -> str:
    v = json.loads(SNAPSHOT.read_text())['inventory']
    assert len(v['columns'])==93 and len(v['constraints'])==19 and len(v['indexes'])==25
    assert len(v['policies'])==18 and set(t['name'] for t in v['tables'])==set(TABLES)
    statements = ['SET search_path=public,extensions;']
    for t in TABLES:
        columns = []
        for c in v['columns']:
            if c['table']!=t: continue
            columns.append(ident(c['name'])+' '+c['type']+
                (' DEFAULT '+c['default'] if c['default'] is not None else '')+
                (' NOT NULL' if c['not_null'] else ''))
        statements.append('CREATE TABLE public.'+ident(t)+' ('+', '.join(columns)+');')
    # FKs are added only after every referenced table exists.
    for c in sorted(v['constraints'],key=lambda c: c['type']=='f'):
        statements.append('ALTER TABLE public.'+ident(c['table'])+' ADD CONSTRAINT '+
            ident(c['name'])+' '+c['definition']+';')
    constrained = {c['name'] for c in v['constraints'] if c['type'] in ('p','u')}
    for i in v['indexes']:
        if i['name'] not in constrained: statements.append(i['definition']+';')
    for t in TABLES:
        statements.extend(['ALTER TABLE public.'+ident(t)+' ENABLE ROW LEVEL SECURITY;',
            'GRANT ALL ON public.'+ident(t)+' TO anon,authenticated,service_role;'])
    for p in v['policies']:
        statement = ('CREATE POLICY '+ident(p['name'])+' ON public.'+ident(p['table'])+
            ' AS '+p['permissive']+' FOR '+p['command']+' TO PUBLIC')
        if p['using'] is not None: statement += ' USING ('+p['using']+')'
        if p['check'] is not None: statement += ' WITH CHECK ('+p['check']+')'
        statements.append(statement+';')
    for t in v['triggers']: statements.append(t['definition']+';')
    statements.append('RESET search_path;')
    return '\n'.join(statements)


def seed_legacy_rows(db):
    ids = {k: str(uuid4()) for k in ('owner','other','run','orphan','probe','orphan_probe','other_probe','other_run','unbound_probe')}
    q = {k:literal(v) for k,v in ids.items()}
    db.sql(f"""
INSERT INTO auth.users VALUES ({q['owner']}),({q['other']});
INSERT INTO public.vn_colonies(id,user_id,status) VALUES
 ({q['run']},{q['owner']},'stopped'),({q['other_run']},{q['other']},'stopped');
INSERT INTO public.vn_probes(id,user_id,run_id,probe_name,parent_id) VALUES
 ({q['probe']},{q['owner']},{q['run']},'legacy-main',NULL),
 ({q['orphan_probe']},{q['owner']},{q['orphan']},'legacy-orphan',{q['probe']}),
 ({q['other_probe']},{q['other']},{q['other_run']},'other-owner',NULL),
 ({q['unbound_probe']},{q['owner']},NULL,'legacy-unbound',NULL);
INSERT INTO public.vn_trades(user_id,run_id,probe_id,side,entry_price,amount) VALUES
 ({q['owner']},{q['run']},{q['probe']},'BUY',100,1),
 ({q['owner']},{q['orphan']},{q['orphan_probe']},'BUY',100,1),
 ({q['other']},{q['other_run']},{q['other_probe']},'BUY',100,1);
INSERT INTO public.vn_fitness_snapshots(user_id,run_id,probe_id,generation,fitness_score) VALUES
 ({q['owner']},{q['orphan']},{q['orphan_probe']},0,-1),
 ({q['owner']},{q['run']},{q['probe']},0,-2);
INSERT INTO public.vn_generation_stats(user_id,run_id,generation) VALUES ({q['owner']},{q['run']},0);
""")
    return ids


def review_sql(db) -> str:
    """Capture outside the mutation session; drift between review/lock must fail."""
    value = db.scalar(MARKER+CATALOG.read_text()+'\nSELECT pg_temp.vn_legacy_catalog();')
    return MARKER+CATALOG.read_text()+ '\nINSERT INTO pg_temp.dashboard_legacy_review VALUES ('+literal(value)+'::jsonb);\n'
