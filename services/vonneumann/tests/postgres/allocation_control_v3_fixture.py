"""Private B2 first-slice fixture; no production installer or native authority.

Source hashes below must be updated only after independent review. A native test
never installs into an existing DB: the ordinary isolated harness owns the entire
network-none cached-image container. The root separately authorizes execution.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import secrets
import select
import subprocess
import time
from uuid import UUID

from tests.postgres.harness import IsolatedPostgres, SqlSession
from tests.postgres.native_issuer_fixture import scram_verifier
from tests.postgres.session_auth_fixture import HOST, NativePostgres
from tests.postgres.actor_catalog_v3_fixture import verify_owned_postgres_image

ROOT = Path(__file__).resolve().parents[2]
N = 'vn_jupiter_b2_allocation_research_v3'
A = 'vn_jupiter_b2_fixture_anchor'
OWNER = 'vn_jupiter_b2_sealed_owner'
ANCHOR_OWNER = 'vn_jupiter_b2_anchor_owner'
SQL_PATH = ROOT / 'db-contract/research/jupiter_allocation_control_v3.sql'
LOADER_PATH = ROOT / 'db-contract/research/allocation_control_v3_source.py'
POLICY_PATH = ROOT / 'research/b2-finite-experiment-policy-2026-10-18-v3.json'
TERMINAL_ADDON_PATH = ROOT / 'db-contract/research/jupiter_terminal_retirement_owner_lab.sql'
HANDOFF_ADDON_PATH = ROOT / 'db-contract/research/jupiter_credential_handoff_lab.sql'
HANDOFF_ADDON_SHA256 = '1fe518402f26deebc44b21f57bc31ad70103f00e8b8f9713c4c6c75885fea82c'
STOP_INTENT_ADDON_PATH = ROOT / 'db-contract/research/jupiter_stop_intent_lab.sql'
STOP_INTENT_ADDON_SHA256 = '90e73e9e9a13fbc5fdd07f86507e34fae010b3bc8d3d226bc5349da9d1661018'
TERMINAL_ADDON_SHA256 = 'a4064e365aa0ef71f8f551703b0c14596b20d42bde318cd969dce9e8d9f4c0e7'
JOINED_ADDON_PATH = ROOT / 'db-contract/research/jupiter_joined_acquisition_lab.sql'
JOINED_ADDON_SHA256 = 'b8558973900b645bc1b863d1c73f838156c9d72974c5ebc5cb54fbfb71d49253'
PACKET_POLICY_PATH = ROOT / 'research/b3-joined-acquisition-lab-policy-v1.json'
PACKET_POLICY_SHA256 = '28b7df36ca970796b7729d29ca0fd0dde861edfdc09579afef160218a05ade51'
PACKET_KINDS = ('packet_reservation', 'capture_retention')
LATE_CAPTURE_POLICY_PATH = ROOT / 'research/b3-joined-capture-retention-lab-policy-v2.json'
LATE_CAPTURE_POLICY_SHA256 = 'c468fa4a7fa8e9122a53abb19ed10d3c1d80f8024dfeefbb8596fef8f1c1f8be'
LATE_CAPTURE_ADDON_PATH = ROOT / 'db-contract/research/jupiter_capture_retention_lab_v2.sql'
LATE_CAPTURE_ADDON_SHA256 = '869d779d1c42268a9e7e95f0f54755b7900ef0fa614aff7961f73754746651be'
SOURCE_SHA256 = 'dcc42004816883eed14d690ab744b0121e5edc417e56bdf0b9cb23809d5a68e5'
LOADER_SHA256 = '048d0468b78a61c83f3d02a33d0879c6576b687ffefb21b5671a398bbb65dcf7'
POLICY_FILE_SHA256 = '0a1c8663f4f6cbf9b299cab11fcdd00a379dbe3ca3493b706ddafca9b75c0f1a'
POLICY_SHA256 = 'e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0'
PROFILES = {'installer':['install','register_epoch','read_original'],
            'recorder':['reserve','fence_manage','read_original'],
            'reader':['register_reader_epoch','read_original'],
            'control':['control','read_original']}
SETTINGS = """SET TimeZone='UTC'; SET DateStyle='ISO,YMD'; SET IntervalStyle='postgres';
SET client_encoding='UTF8'; SET standard_conforming_strings='on';
SET search_path='pg_catalog','pg_temp'; SET row_security='on';
"""
BEGIN = """BEGIN ISOLATION LEVEL READ COMMITTED;
SET LOCAL lock_timeout='1000ms'; SET LOCAL statement_timeout='10000ms';
SET LOCAL transaction_timeout='15000ms'; SET LOCAL idle_in_transaction_session_timeout='10000ms';
SET LOCAL synchronous_commit='on';
"""


def canonical(v):
    return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def sha(v):
    return hashlib.sha256((v if type(v) is bytes else v.encode())).hexdigest()


def literal(v):
    if type(v) is not str or '\x00' in v or len(v.encode())>262144:
        raise ValueError('b2_fixture_literal_refused')
    return "'"+v.replace("'","''")+"'"


def held(path, expected, maximum):
    # Source roots are separately root-created frozen snapshots. This loader
    # refuses links/nonregular bytes and checks the held descriptor + pathname.
    import stat
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=maximum:
            raise ValueError('b2_fixture_source_refused')
        raw=b''
        while len(raw)<=maximum:
            piece=os.read(fd,min(65536,maximum+1-len(raw)))
            if not piece:break
            raw+=piece
        after=os.fstat(fd); named=os.stat(path,follow_symlinks=False)
        if len(raw)>maximum or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) or (after.st_dev,after.st_ino)!=(named.st_dev,named.st_ino) or sha(raw)!=expected:
            raise ValueError('b2_fixture_source_refused')
        return raw
    finally:os.close(fd)


def _projection(relation):
    if not re.fullmatch(r'vn_jupiter_b2_(?:fixture_anchor|allocation_research_v3|reference_anchor|reference_native)\.[a-z_]+',relation):
        raise ValueError('b2_fixture_constructor_refused')
    oid=literal(relation)+'::regclass'
    # Native default/CHECK trees retain every identifier/Const byte; only source
    # locations are removed. FK endpoint names are normalized separately below.
    base=f"""jsonb_build_object(
      'columns',(SELECT jsonb_agg(jsonb_build_object('num',a.attnum,'name',a.attname,'type',a.atttypid::text,'typmod',a.atttypmod,'collation',a.attcollation::text,'null',a.attnotnull,'identity',a.attidentity,'generated',a.attgenerated,'storage',a.attstorage,'compression',a.attcompression,'dropped',a.attisdropped,'options',to_jsonb(a.attoptions),'fdw',to_jsonb(a.attfdwoptions),'missing',a.atthasmissing,'default',regexp_replace(d.adbin::text,':location -?[0-9]+',':location #','g')) ORDER BY a.attnum) FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE a.attrelid={oid} AND a.attnum>0),
      'constraints',(SELECT jsonb_agg(jsonb_build_object('name',c.conname,'kind',c.contype,'deferrable',c.condeferrable,'deferred',c.condeferred,'validated',c.convalidated,'local',c.conislocal,'inh',c.coninhcount,'noinh',c.connoinherit,'keys',to_jsonb(c.conkey),'foreignkeys',to_jsonb(c.confkey),'foreign',CASE WHEN c.confrelid=0 THEN NULL ELSE c.confrelid::regclass::text END,'up',c.confupdtype,'del',c.confdeltype,'match',c.confmatchtype,'pfeq',c.conpfeqop::text,'ppeq',c.conppeqop::text,'ffeq',c.conffeqop::text,'tree',regexp_replace(c.conbin::text,':location -?[0-9]+',':location #','g')) ORDER BY c.conname COLLATE "C") FROM pg_constraint c WHERE c.conrelid={oid}),
      'indexes',(SELECT jsonb_agg(jsonb_build_object('name',c.relname,'am',c.relam::text,'persistence',c.relpersistence,'options',to_jsonb(c.reloptions),'keys',i.indkey::text,'classes',i.indclass::text,'collations',i.indcollation::text,'option',i.indoption::text,'unique',i.indisunique,'primary',i.indisprimary,'exclusion',i.indisexclusion,'immediate',i.indimmediate,'valid',i.indisvalid,'ready',i.indisready,'live',i.indislive,'nulls',i.indnullsnotdistinct,'expr',i.indexprs::text,'pred',i.indpred::text) ORDER BY c.relname COLLATE "C") FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE i.indrelid={oid}))"""

    return f"""jsonb_build_object('table',{base},'toast',(SELECT jsonb_build_object(
      'name_derived',c.relname=('pg_toast_'||{oid}::oid::text),'class',to_jsonb(c)-ARRAY['oid','relname','relfilenode','relpages','reltuples','relallvisible','relallfrozen','relfrozenxid','relminmxid'],
      'columns',(SELECT jsonb_agg(to_jsonb(a)-'attrelid' ORDER BY a.attnum) FROM pg_attribute a WHERE a.attrelid=c.oid),
      'indexes',(SELECT jsonb_agg(jsonb_build_object('name_derived',ic.relname=('pg_toast_'||{oid}::oid::text||'_index'),'class',to_jsonb(ic)-ARRAY['oid','relname','relfilenode','relpages','reltuples','relallvisible','relallfrozen','relfrozenxid','relminmxid'],'index',to_jsonb(i)-ARRAY['indrelid','indexrelid'],'columns',(SELECT jsonb_agg(to_jsonb(a)-'attrelid' ORDER BY a.attnum) FROM pg_attribute a WHERE a.attrelid=ic.oid)) ORDER BY ic.relname) FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid WHERE i.indrelid=c.oid)) FROM pg_class c WHERE c.oid=(SELECT reltoastrelid FROM pg_class WHERE oid={oid})))"""


def constructor_diagnostic(actual, expected, projection_index):
    """Bounded synthetic-catalog diagnostics; never an equality replacement."""
    differences=[]
    remaining=8192
    truncated=False

    def value(v):
        wire=canonical(v).encode('utf8')
        if len(wire)<=4096:return {'value':v}
        return {'UTF8_bytes':len(wire),'sha256':sha(wire),
                'prefix_UTF8':wire[:512].decode('utf8','replace')}

    def visit(a,e,path,depth):
        nonlocal remaining,truncated
        if a==e:return
        remaining-=1
        if remaining<0 or depth>64 or len(differences)>=32:
            truncated=True
            return
        if type(a) is dict and type(e) is dict:
            for key in sorted(set(a)|set(e)):
                part=key.replace('~','~0').replace('/','~1')
                child=path+'/'+part
                if key not in a or key not in e:
                    row={'pointer':child,'actual_present':key in a,'expected_present':key in e}
                    if key in a:row['actual']=value(a[key])
                    if key in e:row['expected']=value(e[key])
                    differences.append(row)
                else:visit(a[key],e[key],child,depth+1)
                if len(differences)>=32 or remaining<0:
                    truncated=True
                    return
        elif type(a) is list and type(e) is list:
            if len(a)!=len(e):
                differences.append({'pointer':path,'actual_length':len(a),'expected_length':len(e)})
            for i in range(min(len(a),len(e))):
                visit(a[i],e[i],path+'/'+str(i),depth+1)
                if len(differences)>=32 or remaining<0:
                    truncated=True
                    return
        else:
            differences.append({'pointer':path,'actual':value(a),'expected':value(e)})

    visit(actual,expected,'',0)
    actual_wire=canonical(actual).encode('utf8')
    expected_wire=canonical(expected).encode('utf8')
    result=dict(format='b2-independent-constructor-diagnostic-v1',
        projection_index=projection_index,differences=differences,truncated=truncated,
        actual_UTF8_bytes=len(actual_wire),expected_UTF8_bytes=len(expected_wire),
        actual_sha256=sha(actual_wire),expected_sha256=sha(expected_wire))
    # Bound exception output even if an unexpected catalog shape is encountered.
    if len(canonical(result).encode('utf8'))>32768:
        result['differences']=differences[:1]
        result['truncated']=True
    return canonical(result)


def compare_constructors(db, source):
    """Separate source-declared constructor, never installed schema as gold."""
    aliases={A:'vn_jupiter_b2_reference_anchor',N:'vn_jupiter_b2_reference_native'}
    ddl='BEGIN;\n'+SETTINGS+''.join(f'CREATE SCHEMA {x};\n' for x in aliases.values())
    for row in source.tables():
        statement=row['ddl']
        for old,new in aliases.items():statement=statement.replace(old+'.',new+'.')
        ddl+=statement+'\n'
    # The full bootstrap already installs this final constraint trigger. Recreate
    # its source-held constructor on the reference table too; never filter its
    # pg_constraint row or adopt the installed constructor as expected state.
    trigger=(f'-- TRIGGER committed_original_guard\n'
      f'CREATE CONSTRAINT TRIGGER committed_original_guard AFTER INSERT ON {N}.original_operations\n'
      f'DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {N}._commit_guard();\n')
    final=(trigger+f'\n-- REVOKES\nREVOKE ALL ON FUNCTION {A}._lock_inputs(pg_catalog.text,pg_catalog.bool) FROM PUBLIC;\n'
      f'REVOKE ALL ON ALL TABLES IN SCHEMA {N} FROM PUBLIC;\n'
      f'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {N} FROM PUBLIC;\n')
    if source.final_sql!=final:raise RuntimeError('b2_reference_guard_source_refused')
    held_trigger=source.final_sql[:len(trigger)]
    original_target=f' ON {N}.original_operations\n'
    if held_trigger.count(original_target)!=1:raise RuntimeError('b2_reference_guard_source_refused')
    # Retain the same original function identity. No reference rows are inserted,
    # so this guard does not execute; the reference transaction is rolled back.
    # All 16 source function bodies/signatures and the actual guard identity are
    # still checked independently after reference cleanup and ownership sealing.
    ddl+=held_trigger.replace(original_target,f' ON {aliases[N]}.original_operations\n',1)
    for row in source.tables():
        actual=row['namespace']+'.'+row['name']; reference=aliases[row['namespace']]+'.'+row['name']
        ddl+=f"SELECT jsonb_build_object('actual',{_projection(actual)},'expected',{_projection(reference)});\n"
    def inventory(schemas):
        ns=','.join(map(literal,schemas))
        return f"""jsonb_build_object('relations',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'name',c.relname,'kind',c.relkind,'persist',c.relpersistence,'options',to_jsonb(c.reloptions),'owner',pg_get_userbyid(c.relowner)) ORDER BY CASE WHEN n.nspname IN('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_reference_anchor') THEN 'anchor' ELSE 'native' END,c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN({ns})),
        'types',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'name',t.typname,'owner',pg_get_userbyid(t.typowner),'len',t.typlen,'val',t.typbyval,'type',t.typtype,'category',t.typcategory,'preferred',t.typispreferred,'defined',t.typisdefined,'delimiter',t.typdelim,'relation',CASE WHEN t.typrelid=0 THEN NULL ELSE t.typrelid::regclass::text END,'subscript',t.typsubscript::oid::text,'element',CASE WHEN t.typelem=0 THEN NULL ELSE t.typelem::regtype::text END,'array',CASE WHEN t.typarray=0 THEN NULL ELSE t.typarray::regtype::text END,'input',t.typinput::oid::text,'output',t.typoutput::oid::text,'receive',t.typreceive::oid::text,'send',t.typsend::oid::text,'analyze',t.typanalyze::oid::text,'align',t.typalign,'storage',t.typstorage,'notnull',t.typnotnull,'base',t.typbasetype::text,'typmod',t.typtypmod,'dims',t.typndims,'collation',t.typcollation::text,'defaultbin',t.typdefaultbin::text,'default',t.typdefault) ORDER BY CASE WHEN n.nspname IN('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_reference_anchor') THEN 'anchor' ELSE 'native' END,t.typname) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname IN({ns})),
        'internal_triggers',(SELECT jsonb_agg(jsonb_build_object('table',t.tgrelid::regclass::text,'function',t.tgfoid::text,'type',t.tgtype,'enabled',t.tgenabled,'deferrable',t.tgdeferrable,'deferred',t.tginitdeferred,'args',encode(t.tgargs,'hex'),'when',t.tgqual::text) ORDER BY CASE WHEN n.nspname IN('vn_jupiter_b2_fixture_anchor','vn_jupiter_b2_reference_anchor') THEN 'anchor' ELSE 'native' END,c.relname,t.tgfoid,t.tgtype,t.tgdeferrable,t.tginitdeferred) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN({ns}) AND t.tgisinternal))"""
    ddl+=f"SELECT jsonb_build_object('actual',{inventory(aliases)},'expected',{inventory(aliases.values())});\n"
    ddl+='ROLLBACK;'
    lines=db.scalar(ddl,timeout=30).splitlines()
    if len(lines)!=9:raise RuntimeError('b2_constructor_inventory_refused')
    for projection_index,line in enumerate(lines):
        pair=json.loads(line)
        expected=canonical(pair['expected'])
        for old,new in aliases.items():expected=expected.replace(new,old)
        if pair['actual']!=json.loads(expected):
            raise RuntimeError('b2_independent_constructor_mismatch:'+constructor_diagnostic(pair['actual'],json.loads(expected),projection_index))
    if db.scalar("SELECT count(*) FROM pg_namespace WHERE nspname IN('vn_jupiter_b2_reference_anchor','vn_jupiter_b2_reference_native');")!='0':
        raise RuntimeError('b2_reference_cleanup_refused')


def verify_functions(db, source, actors, *, getter_only=()):
    rows=json.loads(db.scalar(f"""SELECT jsonb_agg(jsonb_build_object('namespace',p.pronamespace::regnamespace::text,'name',p.proname,'owner',r.rolname,'body',p.prosrc,'args',p.proargtypes::oid[]::text,'names',to_jsonb(p.proargnames),'return',p.prorettype::regtype::text,'lang',l.lanname,'kind',p.prokind,'definer',p.prosecdef,'strict',p.proisstrict,'volatile',p.provolatile,'parallel',p.proparallel,'leak',p.proleakproof,'set',p.proretset,'cost',p.procost::text,'rows',p.prorows::text,'support',p.prosupport::oid::text,'variadic',p.provariadic::text,'defaults',p.pronargdefaults,'alltypes',to_jsonb(p.proallargtypes),'modes',to_jsonb(p.proargmodes),'transforms',to_jsonb(p.protrftypes),'binary',p.probin,'sqlbody',p.prosqlbody::text,'settings',to_jsonb(p.proconfig)) ORDER BY p.proname) FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner JOIN pg_language l ON l.oid=p.prolang WHERE p.pronamespace IN(SELECT oid FROM pg_namespace WHERE nspname IN({literal(A)},{literal(N)}));""",timeout=30))
    if type(rows) is not list or len(rows)!=len(source.functions())+1:raise RuntimeError('b2_source_functions_refused')
    anchor_rows=[row for row in rows if row['namespace']==A]
    rows=[row for row in rows if row['namespace']==N]
    if len(rows)!=len(source.functions()) or len(anchor_rows)!=1:raise RuntimeError('b2_source_functions_refused')
    specs={x['name']:x for x in source.functions()}
    for row in rows:
        expected=specs.pop(row['name'],None)
        if expected is None:raise RuntimeError('b2_source_functions_refused')
        argtypes=expected['argument_types'];args=','.join('pg_catalog.'+t for t in argtypes)
        signature=N+'.'+row['name']+'('+args+')'
        oidargs=db.scalar("SELECT coalesce(array_agg(t),'{}'::oid[])::text FROM pg_proc p CROSS JOIN LATERAL unnest(p.proargtypes::oid[]) t WHERE p.oid="+literal(signature)+'::regprocedure;')
        # Actual argument identities are also resolved from independently held
        # pg_catalog names; comparing only deparsed spelling is insufficient.
        expected_oidargs=db.scalar("SELECT ARRAY["+','.join(literal('pg_catalog.'+t)+'::regtype::oid' for t in argtypes)+"]::oid[]::text;" if argtypes else "SELECT ARRAY[]::oid[]::text;")
        result='void' if row['name']=='_check_credential_window' else 'trigger' if row['name']=='_commit_guard' else ('boolean' if row['name']=='_keys' else ('text' if row['name'] in ('_c14n','_sha','_scope','_reply','get_original','submit','_submit') else 'jsonb'))
        actual={k:row[k] for k in ('owner','body','names','return','lang','kind','definer','strict','volatile','parallel','leak','set','cost','rows','support','variadic','defaults','alltypes','modes','transforms','binary','sqlbody')}
        wanted=dict(owner=OWNER,body=expected['body'],names=expected['argument_names'],lang='plpgsql',kind='f',definer=expected['definer'],strict=False,volatile=expected['volatility'],parallel='u',leak=False,set=False,cost='100',rows='0',support='0',variadic='0',defaults=0,alltypes=None,modes=None,transforms=None,binary=None,sqlbody=None)
        wanted['return']=result
        if actual!=wanted or oidargs!=expected_oidargs or set(row['settings'])!={'search_path=pg_catalog, pg_temp','TimeZone=UTC','client_encoding=UTF8','standard_conforming_strings=on'}:
            raise RuntimeError('b2_source_function_mismatch')
        acl=json.loads(db.scalar(f"SELECT jsonb_agg(jsonb_build_array(coalesce(r.rolname,'PUBLIC'),a.privilege_type,a.is_grantable) ORDER BY coalesce(r.rolname,'PUBLIC') COLLATE \"C\") FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a LEFT JOIN pg_roles r ON r.oid=a.grantee WHERE p.oid={literal(signature)}::regprocedure;"))
        entry_actors=list(actors) if expected['public_entry'] else []
        if row['name']=='submit':entry_actors=[actor for actor in entry_actors if actor not in getter_only]
        allowed=sorted([OWNER]+entry_actors)
        if acl!=[[role,'EXECUTE',False] for role in allowed]:raise RuntimeError('b2_function_acl_refused')
    if specs:raise RuntimeError('b2_source_functions_refused')
    # Closed lab: the separate NOLOGIN anchor owner owns this fixed lock broker.
    row=anchor_rows[0];expected=source.anchor_function()
    if row['name']!='_lock_inputs' or expected['namespace']!=A or expected['owner']!=ANCHOR_OWNER:
        raise RuntimeError('b2_anchor_lock_source_refused')
    actual={k:row[k] for k in ('owner','body','names','return','lang','kind','definer','strict','volatile','parallel','leak','set','cost','rows','support','variadic','defaults','alltypes','modes','transforms','binary','sqlbody')}
    wanted=dict(owner=ANCHOR_OWNER,body=expected['body'],names=['requested_scope','lock_resume_recorder'],lang='plpgsql',kind='f',definer=True,strict=False,volatile='v',parallel='u',leak=False,set=False,cost='100',rows='0',support='0',variadic='0',defaults=0,alltypes=None,modes=None,transforms=None,binary=None,sqlbody=None)
    wanted['return']='void'
    signature=expected['signature']
    oidargs=db.scalar("SELECT array_agg(arg.type_oid ORDER BY arg.ordinal)::text FROM pg_proc p CROSS JOIN LATERAL unnest(p.proargtypes::oid[]) WITH ORDINALITY arg(type_oid,ordinal) WHERE p.oid="+literal(signature)+'::regprocedure;')
    expected_oidargs=db.scalar("SELECT ARRAY['pg_catalog.text'::regtype::oid,'pg_catalog.bool'::regtype::oid]::oid[]::text;")
    if actual!=wanted or oidargs!=expected_oidargs or set(row['settings'])!={'search_path=pg_catalog, pg_temp','TimeZone=UTC','client_encoding=UTF8','standard_conforming_strings=on'}:
        raise RuntimeError('b2_anchor_lock_source_refused')
    acl=json.loads(db.scalar(f"SELECT jsonb_agg(jsonb_build_array(coalesce(r.rolname,'PUBLIC'),a.privilege_type,a.is_grantable,pg_get_userbyid(a.grantor)) ORDER BY coalesce(r.rolname,'PUBLIC') COLLATE \"C\") FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a LEFT JOIN pg_roles r ON r.oid=a.grantee WHERE p.oid={literal(signature)}::regprocedure;"))
    if acl!=[[role,'EXECUTE',False,ANCHOR_OWNER] for role in sorted([ANCHOR_OWNER,OWNER])]:
        raise RuntimeError('b2_anchor_lock_acl_refused')


CREATOR = 'vn_jupiter_b2_actor_issuer'
SCRAM_FORMAT = 'ga-jupiter-b2-fixture-direct-scram-research-v3-v1'
SHORT_RECORDER = 'vn_jupiter_b2_0_recorder'
SUCCESSOR_RECORDER = 'vn_jupiter_b2_0_recorder_next'
HANDOFF_PACKAGE_FORMAT = 'ga-jupiter-b2-fixture-direct-scram-handoff-research-v3-v1'
DEADLINE_PACKAGE_FORMAT = 'ga-jupiter-b2-fixture-direct-scram-deadlines-research-v3-v1'
DEADLINE_MANIFEST_FORMAT = 'ga-jupiter-b2-capability-manifest-deadlines-research-v3-v1'


def verify_seal(db, source, actors, *, creator_edges=False, actor_count=8):
    # Exact stored/effective default-expanded ACL entries, not just the chosen
    # actors' absence of rights. Unknown grantees/grantors/column grants refuse.
    acl=json.loads(db.scalar(f"""SELECT jsonb_build_object(
      'schemas',(SELECT jsonb_agg(jsonb_build_array(n.nspname,coalesce(r.rolname,'PUBLIC'),a.privilege_type,a.is_grantable,pg_get_userbyid(a.grantor)) ORDER BY n.nspname,r.rolname,a.privilege_type) FROM pg_namespace n CROSS JOIN LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a LEFT JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname IN({literal(A)},{literal(N)})),
      'tables',(SELECT jsonb_agg(jsonb_build_array(n.nspname||'.'||c.relname,coalesce(r.rolname,'PUBLIC'),a.privilege_type,a.is_grantable,pg_get_userbyid(a.grantor)) ORDER BY n.nspname,c.relname,r.rolname,a.privilege_type) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a LEFT JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname IN({literal(A)},{literal(N)}) AND c.relkind='r'),
      'types',(SELECT jsonb_agg(jsonb_build_array(n.nspname||'.'||t.typname,coalesce(r.rolname,'PUBLIC'),a.privilege_type,a.is_grantable,pg_get_userbyid(a.grantor)) ORDER BY n.nspname,t.typname,r.rolname,a.privilege_type) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace CROSS JOIN LATERAL aclexplode(coalesce(t.typacl,acldefault('T',t.typowner))) a LEFT JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname IN({literal(A)},{literal(N)}) AND t.typtype='c'),
      'column_grants',(SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN({literal(A)},{literal(N)}) AND a.attacl IS NOT NULL));"""))
    expected=dict(schemas=[],tables=[],types=[],column_grants=0)
    for ns,owner in ((A,ANCHOR_OWNER),(N,OWNER)):
        expected['schemas'] += [[ns,owner,priv,False,owner] for priv in ('CREATE','USAGE')]
    expected['schemas'] += [[N,actor,'USAGE',False,OWNER] for actor in actors]+[[A,OWNER,'USAGE',False,ANCHOR_OWNER]]
    for row in source.tables():
        relation=row['namespace']+'.'+row['name'];owner=ANCHOR_OWNER if row['namespace']==A else OWNER
        expected['tables'] += [[relation,owner,priv,False,owner] for priv in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN')]
        if row['namespace']==A:expected['tables'] += [[relation,OWNER,'SELECT',False,ANCHOR_OWNER]]
        expected['types'] += [[relation,owner,'USAGE',False,owner]]
    for key in ('schemas','tables','types'):
        if sorted(acl[key])!=sorted(expected[key]):raise RuntimeError('b2_closed_acl_inventory_refused')
    if acl['column_grants']!=0:raise RuntimeError('b2_column_acl_refused')
    for schema,wanted in ((A,ANCHOR_OWNER),(N,OWNER)):
        if db.scalar(f"SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname={literal(schema)};")!=wanted:raise RuntimeError('b2_owner_refused')
    for row in source.tables():
        relation=row['namespace']+'.'+row['name'];wanted=ANCHOR_OWNER if row['namespace']==A else OWNER
        check=json.loads(db.scalar(f"SELECT jsonb_build_array(pg_get_userbyid(c.relowner),c.relkind::text,c.relpersistence::text,c.relrowsecurity,c.relforcerowsecurity,c.reloptions,(SELECT count(*) FROM pg_rewrite WHERE ev_class=c.oid),(SELECT count(*) FROM pg_policy WHERE polrelid=c.oid),(SELECT count(*) FROM pg_class x WHERE (x.oid=c.reltoastrelid OR x.oid IN(SELECT indexrelid FROM pg_index WHERE indrelid IN(c.oid,c.reltoastrelid))) AND x.relowner<>c.relowner)) FROM pg_class c WHERE c.oid={literal(relation)}::regclass;"))
        if check!=[wanted,'r','p',False,False,None,0,0,0]:raise RuntimeError('b2_table_shape_refused')
        type_owners=json.loads(db.scalar(f"SELECT jsonb_build_array(pg_get_userbyid(t.typowner),pg_get_userbyid(array_type.typowner)) FROM pg_type t JOIN pg_type array_type ON array_type.oid=t.typarray WHERE t.typrelid={literal(relation)}::regclass;"))
        if type_owners!=[wanted,wanted]:raise RuntimeError('b2_table_type_owner_refused')
        if row['namespace']==N:
            anchor_rights=db.scalar(f"SELECT has_table_privilege({literal(ANCHOR_OWNER)},{literal(relation)},'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR has_any_column_privilege({literal(ANCHOR_OWNER)},{literal(relation)},'SELECT,INSERT,UPDATE,REFERENCES') OR has_type_privilege({literal(ANCHOR_OWNER)},{literal(relation)},'USAGE');")
            if anchor_rights!='f':raise RuntimeError('b2_anchor_native_access_refused')
        for actor in actors:
            rights=db.scalar(f"SELECT has_table_privilege({literal(actor)},{literal(relation)},'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR has_any_column_privilege({literal(actor)},{literal(relation)},'SELECT,INSERT,UPDATE,REFERENCES') OR has_type_privilege({literal(actor)},{literal(relation)},'USAGE') OR has_type_privilege({literal(actor)},{literal(relation+'[]')},'USAGE');")
            if rights!='f':raise RuntimeError('b2_private_table_refused')
        rights=json.loads(db.scalar(f"SELECT jsonb_agg(jsonb_build_array(privilege,has_table_privilege({literal(OWNER)},{literal(relation)},privilege)) ORDER BY privilege) FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN']) privilege;"))
        if any(value!=(row['namespace']==N or privilege=='SELECT') for privilege,value in rights):raise RuntimeError('b2_anchor_write_refused')
    trigger=json.loads(db.scalar(f"SELECT jsonb_agg(jsonb_build_array(t.tgname,t.tgrelid::regclass::text,t.tgfoid::regprocedure::text,t.tgtype,t.tgenabled::text,t.tgdeferrable,t.tginitdeferred,t.tgnargs,encode(t.tgargs,'hex'),t.tgqual::text)) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN({literal(A)},{literal(N)}) AND NOT t.tgisinternal;"))
    if trigger!=[['committed_original_guard',N+'.original_operations',N+'._commit_guard()',5,'O',True,True,0,'',None]]:raise RuntimeError('b2_guard_trigger_refused')
    for actor in actors:
        if db.scalar(f"SELECT has_schema_privilege({literal(actor)},{literal(A)},'USAGE,CREATE') OR has_schema_privilege({literal(actor)},{literal(N)},'CREATE');")!='f':raise RuntimeError('b2_schema_access_refused')
    # Check both actual owner roles independently before capturing catalog gold.
    for sealed_owner in (ANCHOR_OWNER,OWNER):
        role=json.loads(db.scalar(f"SELECT jsonb_build_object('login',rolcanlogin,'super',rolsuper,'inherit',rolinherit,'create_role',rolcreaterole,'create_db',rolcreatedb,'replication',rolreplication,'bypass',rolbypassrls,'connection_limit',rolconnlimit,'default_expiry',rolvaliduntil IS NULL,'default_config',rolconfig IS NULL) FROM pg_catalog.pg_roles WHERE rolname={literal(sealed_owner)};"))
        if role!=dict(login=False,super=False,inherit=False,create_role=False,create_db=False,replication=False,bypass=False,connection_limit=-1,default_expiry=True,default_config=True):
            raise RuntimeError('b2_sealed_owner_attributes_refused')
    if db.scalar(f"SELECT has_schema_privilege({literal(OWNER)},{literal(A)},'CREATE') OR has_schema_privilege({literal(ANCHOR_OWNER)},{literal(N)},'USAGE,CREATE');")!='f':
        raise RuntimeError('b2_sealed_owner_cross_schema_refused')
    sealed_roles=[ANCHOR_OWNER,OWNER,*actors]
    if creator_edges:sealed_roles.append(CREATOR)
    sealed_names=','.join(map(literal,sealed_roles))
    membership=json.loads(db.scalar(f"""SELECT COALESCE(jsonb_agg(jsonb_build_array(m.roleid::text,m.member::text,m.grantor::text,
      m.admin_option,m.inherit_option,m.set_option) ORDER BY m.roleid,m.member,m.grantor),'[]')
      FROM pg_auth_members m WHERE m.roleid IN(SELECT oid FROM pg_roles WHERE rolname IN({sealed_names}))
      OR m.member IN(SELECT oid FROM pg_roles WHERE rolname IN({sealed_names}));"""))
    expected_membership=[]
    if creator_edges:
        issuer=json.loads(db.scalar(f"""SELECT jsonb_build_array(oid::text,rolcanlogin,rolcreaterole,
          rolsuper,rolinherit,rolcreatedb,rolreplication,rolbypassrls)
          FROM pg_roles WHERE rolname={literal(CREATOR)};"""))
        grantor=json.loads(db.scalar("SELECT jsonb_build_array(oid::text,rolsuper) FROM pg_roles WHERE rolname='postgres';"))
        if issuer[1:]!=[True,True,False,False,False,False,False] or issuer[0]==grantor[0] or grantor!=['10',True]:
            raise RuntimeError('b2_creator_identity_refused')
        actor_oids=json.loads(db.scalar(f"SELECT jsonb_agg(oid::text ORDER BY oid) FROM pg_roles WHERE rolname IN({','.join(map(literal,actors))});"))
        if len(actors)!=actor_count or len(actor_oids)!=actor_count or len(set(actor_oids))!=actor_count:
            raise RuntimeError('b2_actor_oid_inventory_refused')
        expected_membership=[[oid,issuer[0],grantor[0],True,False,False] for oid in actor_oids]
    if membership!=expected_membership:raise RuntimeError('b2_membership_refused')


class AllocationScramPostgres(NativePostgres):
    """Existing owned CA/server plus direct actor libpq, with no SET ROLE."""

    recorder_seconds = 35
    issuer_scram = False
    independent_deadlines = False
    scope_count = 2

    def __init__(self):
        super().__init__()
        self.actor_deadlines = {}

    def uses_direct_scram(self, role):
        return role in self.actor_deadlines or (self.issuer_scram and role == CREATOR)

    def synthetic_password_clause(self, role, deadline):
        password = secrets.token_hex(32)
        verifier = scram_verifier(password)
        self.write_private(role+'.pgpass',f'*:5432:postgres:{role}:{password}\n')
        return f'CONNECTION LIMIT 2 PASSWORD {literal(verifier)} VALID UNTIL {literal(deadline)}'

    def actor_ddl(self, actors):
        if self.actor_deadlines or len(set(actors)) != 4*self.scope_count or SHORT_RECORDER not in actors:
            raise RuntimeError('b2_scram_fixture_actor_inventory_refused')
        # One authoritative timestamp with fixed, finite offsets. Use the same
        # absolute values in role creation and in the independent catalog check.
        deadlines = json.loads(self.scalar(f"""WITH now AS MATERIALIZED (SELECT clock_timestamp() AS stamp)
            SELECT jsonb_agg(jsonb_build_array(deadline::text,floor(extract(epoch FROM deadline)*1000000)::bigint)
              ORDER BY deadline) FROM now CROSS JOIN LATERAL
              (VALUES (stamp+interval '{self.recorder_seconds} seconds'),(stamp+interval '180 seconds')) AS d(deadline);"""))
        ddl = []
        for actor in actors:
            deadline, deadline_us = deadlines[0 if actor == SHORT_RECORDER else 1]
            credentials = self.synthetic_password_clause(actor,deadline)
            ddl.append(f'CREATE ROLE {actor} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT '
                f'NOREPLICATION NOBYPASSRLS {credentials};')
            self.actor_deadlines[actor] = deadline_us
        return '\n'.join(ddl)+'\n'

    def verify_actor_deadlines(self):
        roles = ','.join(map(literal,self.actor_deadlines))
        actual = json.loads(self.scalar(f"""SELECT jsonb_object_agg(rolname::text,
          floor(extract(epoch FROM rolvaliduntil)*1000000)::bigint) FROM pg_roles
          WHERE rolname IN({roles}) AND rolcanlogin AND rolconnlimit=2 AND isfinite(rolvaliduntil);"""))
        if actual != self.actor_deadlines:
            raise RuntimeError('b2_scram_fixture_deadline_refused')

    def direct_command(self, role, *, statement_ms, host=HOST, root='root.crt'):
        if (self._container_id is None or not self.uses_direct_scram(role) or not 0 < statement_ms <= 60000
                or host not in (HOST,'wrong.example') or root not in ('root.crt','wrong-root.crt')):
            raise ValueError('b2_direct_fixture_connection_refused')
        conn = f'host={host} hostaddr=127.0.0.1 port=5432 dbname=postgres user={role} sslmode=verify-full '
        conn += f'sslrootcert=/tmp/dashboard-pg/{root} channel_binding=require connect_timeout=2'
        return self._docker+['exec','-i','--env',f'PGPASSFILE=/tmp/dashboard-pg/{role}.pgpass',
            '--env',f'PGOPTIONS=-c statement_timeout={statement_ms}',self._container_id,'psql','-X','-w',
            '-d',conn,'-v','ON_ERROR_STOP=1','-v','VERBOSITY=verbose','-A','-t','-q']

    def begin_sql(self, source, *, role='postgres', timeout=10):
        if not self.uses_direct_scram(role):
            return super().begin_sql(source,role=role,timeout=timeout)
        return self.begin_direct(source,role=role,timeout=timeout)

    def begin_direct(self, source, *, role, timeout=10, host=HOST, root='root.crt'):
        if not 0 < timeout <= 60:
            raise ValueError('b2_direct_fixture_timeout_refused')
        server_ms=max(1,int((timeout-min(1,timeout/2))*1000))
        command=self.direct_command(role,statement_ms=server_ms,host=host,root=root)
        session=SqlSession(command,source,self._env,timeout)
        self._sessions.append(session)
        return session


    def deadline_binding(self, actor, profile, issuance_id):
        login_us=self.actor_deadlines[actor]
        # Exact inverse of the fixed offsets from one real DB issuance stamp.
        issued_us=login_us-(self.recorder_seconds if actor==SHORT_RECORDER else 180)*1_000_000
        cutoff_us=issued_us+self.application_window_seconds(actor,profile)*1_000_000
        return dict(issuance_id=issuance_id,credential_generation='1',
            issued_at_us=str(issued_us),not_before_us=str(issued_us),login_until_us=str(login_us),
            write_until_us=None if profile=='reader' else str(cutoff_us),
            read_until_us=str(cutoff_us) if profile=='reader' else None)


class AllocationDeadlineScramPostgres(AllocationScramPostgres):
    independent_deadlines = True

    def application_window_seconds(self, actor, profile):
        if profile=='reader':
            return 42
        return 24 if actor==SHORT_RECORDER else 150


class AllocationRetirementPostgres(AllocationScramPostgres):
    recorder_seconds = 180
    issuer_scram = True

    def create_scram_issuer(self):
        deadline=self.scalar("SELECT (clock_timestamp()+interval '180 seconds')::text;")
        credentials=self.synthetic_password_clause(CREATOR,deadline)
        sql=f'CREATE ROLE {CREATOR} LOGIN NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS {credentials};'
        result=self.sql(sql,check=False)
        if result.returncode:
            raise RuntimeError('b2_terminal_fixture_issuer_refused')


class AllocationDeadlineRetirementPostgres(AllocationRetirementPostgres):
    independent_deadlines = True
    short_profile = None

    def application_window_seconds(self, actor, profile):
        if profile==self.short_profile and actor==f'vn_jupiter_b2_0_{profile}':
            return 26
        return 150


class AllocationControlWindowRetirementPostgres(AllocationDeadlineRetirementPostgres):
    short_profile = 'control'


class AllocationReaderWindowRetirementPostgres(AllocationDeadlineRetirementPostgres):
    short_profile = 'reader'


class AllocationHandoffPostgres(AllocationDeadlineRetirementPostgres):
    scope_count = 1


class AllocationJoinedPostgres(AllocationHandoffPostgres):
    """Opt into the sealed two-kind provider capture fixture."""


def install_and_verify_terminal_addon(db, expected_functions):
    """Install only in the owned terminal fixture, before independent K capture."""
    source=held(TERMINAL_ADDON_PATH,TERMINAL_ADDON_SHA256,32768).decode('utf8')
    signatures={
        '_terminal_retirement_context':(N,OWNER,['requested_scope','permit_wire','after_disable'],['text','text','boolean'],'text',ANCHOR_OWNER),
        '_stage_terminal_retirement':(A,ANCHOR_OWNER,['requested_scope','requested_permit'],['text','text'],'text',CREATOR),
        '_terminal_retirement_commit_guard':(A,ANCHOR_OWNER,None,[],'trigger',None),
    }
    db.sql(source,timeout=30)
    functions={name:(namespace,owner,args,argtypes,returns,grantee,'v',True)
               for name,(namespace,owner,args,argtypes,returns,grantee) in signatures.items()}
    verify_companion_functions(db,source,'terminal',functions)
    verify_terminal_addon_catalog(db,expected_functions)


def verify_companion_functions(db,source,delimiter,signatures):
    tag=re.escape('$'+delimiter+'$')
    for name,(namespace,owner,args,argtypes,returns,grantee,volatility,definer) in signatures.items():
        body=re.search(r'^-- FUNCTION '+name+r'\nCREATE FUNCTION [^\n]+\n.*?^AS '+tag+r'(.*?)^'+tag+r';',source,re.M|re.S)
        if body is None:
            raise RuntimeError('b2_terminal_held_function_refused')
        signature=f'{namespace}.{name}('+','.join(argtypes)+')'
        actual=json.loads(db.scalar(f"""SELECT jsonb_build_array(pg_get_userbyid(p.proowner),p.prosrc,p.proargnames,
          (SELECT coalesce(jsonb_agg(t::regtype::text ORDER BY i),'[]') FROM unnest(p.proargtypes::oid[]) WITH ORDINALITY v(t,i)),
          p.prorettype::regtype::text,l.lanname,p.prokind,p.prosecdef,p.proisstrict,p.provolatile,p.proparallel,
          p.proleakproof,p.proretset,p.procost::text,p.prorows::text,p.prosupport::oid::text,p.provariadic::text,
          p.pronargdefaults,p.proallargtypes,p.proargmodes,p.protrftypes,p.probin,p.prosqlbody::text,p.proconfig,
          (SELECT jsonb_agg(jsonb_build_array(coalesce(grantee.rolname,'PUBLIC'),pg_get_userbyid(a.grantor),a.privilege_type,a.is_grantable)
          ORDER BY coalesce(grantee.rolname,'PUBLIC') COLLATE "C") FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
          LEFT JOIN pg_roles grantee ON grantee.oid=a.grantee))
          FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang WHERE p.oid={literal(signature)}::regprocedure;"""))
        allowed=sorted([owner]+([grantee] if grantee else []))
        expected=[owner,body.group(1),args,argtypes,returns,'plpgsql','f',definer,False,volatility,'u',False,False,
          '100','0','0','0',0,None,None,None,None,None,
          ['search_path=pg_catalog, pg_temp','TimeZone=UTC','client_encoding=UTF8','standard_conforming_strings=on'],
          [[role,owner,'EXECUTE',False] for role in allowed]]
        if actual!=expected:
            raise RuntimeError('b2_terminal_function_catalog_refused:'+name)
def verify_terminal_addon_catalog(db,expected_functions):
    if db.scalar(f"SELECT count(*) FROM pg_proc WHERE pronamespace IN({literal(A)}::regnamespace,{literal(N)}::regnamespace);")!=str(expected_functions):
        raise RuntimeError('b2_terminal_function_inventory_refused')
    schema_grants=json.loads(db.scalar(f"""SELECT jsonb_agg(jsonb_build_array(n.nspname,pg_get_userbyid(a.grantee),
       pg_get_userbyid(a.grantor),a.privilege_type,a.is_grantable) ORDER BY n.nspname)
      FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a
      WHERE (n.nspname={literal(A)} AND a.grantee={literal(CREATOR)}::regrole)
         OR (n.nspname={literal(N)} AND a.grantee={literal(ANCHOR_OWNER)}::regrole);"""))
    if schema_grants!=sorted([[A,CREATOR,ANCHOR_OWNER,'USAGE',False],[N,ANCHOR_OWNER,OWNER,'USAGE',False]]):
        raise RuntimeError('b2_terminal_schema_acl_refused')
    attr=json.loads(db.scalar(f"""SELECT jsonb_build_array(a.attnum,a.atttypid::regtype::text,a.attnotnull,a.atthasdef,a.attacl)
      FROM pg_attribute a WHERE a.attrelid={literal(A+'.package_inputs')}::regclass AND a.attname='retirement_permit_wire';"""))
    if attr!=[8,'text',False,False,None]:
        raise RuntimeError('b2_terminal_permit_column_refused')
    if db.scalar(f"""SELECT count(*) FROM pg_constraint c WHERE c.conrelid={literal(A+'.package_inputs')}::regclass
       AND c.contype='c' AND c.conkey=ARRAY[8]::smallint[] AND c.convalidated
       AND pg_get_expr(c.conbin,c.conrelid)='(octet_length(retirement_permit_wire) <= 8192)';""")!='1':
        raise RuntimeError('b2_terminal_permit_constraint_refused')
    trigger=json.loads(db.scalar(f"""SELECT jsonb_build_array(t.tgfoid::regprocedure::text,t.tgtype,t.tgenabled,
      t.tgdeferrable,t.tginitdeferred,t.tgnargs,pg_get_triggerdef(t.oid)) FROM pg_trigger t
      WHERE NOT t.tgisinternal AND t.tgrelid={literal(A+'.package_inputs')}::regclass
       AND t.tgname='committed_terminal_retirement_guard';"""))
    if trigger[:-1]!=[A+'._terminal_retirement_commit_guard()',17,'O',True,True,0] or not all(
       part in trigger[-1].lower() for part in ('new.retirement_permit_wire is not null','old.retirement_wire is distinct from new.retirement_wire',
        'old.retirement_permit_wire is distinct from new.retirement_permit_wire')):
        raise RuntimeError('b2_terminal_trigger_refused')
    rights=db.scalar(f"""SELECT EXISTS(SELECT 1 FROM pg_class c WHERE c.relnamespace IN({literal(A)}::regnamespace,{literal(N)}::regnamespace)
       AND c.relkind='r' AND (has_table_privilege({literal(CREATOR)},c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
       OR has_any_column_privilege({literal(CREATOR)},c.oid,'SELECT,INSERT,UPDATE,REFERENCES')))
       OR pg_has_role({literal(CREATOR)},{literal(ANCHOR_OWNER)},'SET') OR pg_has_role({literal(CREATOR)},{literal(OWNER)},'SET');""")
    if rights!='f':
        raise RuntimeError('b2_terminal_issuer_effective_acl_refused')


def install_and_verify_handoff_addons(db, terminal_functions, control, reader):
    handoff=held(HANDOFF_ADDON_PATH,HANDOFF_ADDON_SHA256,65536).decode('utf8')
    stop=held(STOP_INTENT_ADDON_PATH,STOP_INTENT_ADDON_SHA256,65536).decode('utf8')
    handoff_signatures={
        '_read_handoff':(N,OWNER,['requested_scope'],['text'],'jsonb',None,'s',False),
        '_handoff_allows_renew':(N,OWNER,['marker','native_position','command_sha','writer_binding','prior_fence','prior_head_sha'],
            ['jsonb','bigint','text','text','jsonb','text'],'boolean',None,'i',False),
        '_handoff_catalog_preimage':(N,OWNER,['actual','old_role','new_role','issuer'],['jsonb','oid','oid','oid'],'jsonb',None,'s',False),
        '_handoff_native':(N,OWNER,['requested_scope','requested_id','phase'],['text','uuid','text'],'text',ANCHOR_OWNER,'v',True),
        '_stage_credential_handoff':(A,ANCHOR_OWNER,['requested_scope','requested_id'],['text','uuid'],'void',CREATOR,'v',True),
        '_finish_credential_handoff':(A,ANCHOR_OWNER,['requested_scope','requested_id'],['text','uuid'],'text',CREATOR,'v',True),
        '_commit_credential_handoff':(A,ANCHOR_OWNER,None,[],'trigger',None,'v',True),
    }
    stop_signatures={
        '_stop_intent_reply':(N,OWNER,['stored_wire','requested_scope','requested_id','auth'],['text','text','text','jsonb'],'jsonb',None,'s',False),
        '_existing_stop_intent':(N,OWNER,['requested_scope','command','wire','auth'],['text','jsonb','text','jsonb'],'text',None,'v',False),
        '_stage_stop_intent':(N,OWNER,['requested_scope','command','wire','auth'],['text','jsonb','text','jsonb'],'text',None,'v',False),
        '_require_no_stop_intent':(N,OWNER,['requested_scope'],['text'],'void',None,'v',False),
        '_require_exact_stop_intent':(N,OWNER,['requested_scope','command','wire','auth'],['text','jsonb','text','jsonb'],'void',None,'v',False),
        'record_stop_intent':(N,OWNER,['wire'],['text'],'text',control,'v',True),
        'get_stop_intent':(N,OWNER,['wire'],['text'],'text',reader,'s',True),
        '_stop_intent_commit_guard':(N,OWNER,None,[],'trigger',None,'v',True),
    }
    db.sql(handoff,timeout=30)
    db.sql(stop,timeout=30)
    verify_companion_functions(db,handoff,'handoff',handoff_signatures)
    verify_companion_functions(db,stop,'intent',stop_signatures)
    if db.scalar(f"SELECT count(*) FROM pg_proc WHERE pronamespace IN({literal(A)}::regnamespace,{literal(N)}::regnamespace);")!=str(terminal_functions+len(handoff_signatures)+len(stop_signatures)):
        raise RuntimeError('b2_handoff_function_inventory_refused')
    verify_handoff_table(db,A+'.credential_handoff',ANCHOR_OWNER,OWNER,
        [['scope_wire','text',True],['handoff_id','uuid',True],['permit_wire','text',True],
         ['stage_xid','xid8',False],['handoff_wire','text',False]],
        ['CHECK (handoff_wire IS NULL OR stage_xid IS NOT NULL)','CHECK (octet_length(handoff_wire) <= 8192)',
         'CHECK (octet_length(permit_wire) <= 8192)',f'FOREIGN KEY (scope_wire) REFERENCES {A}.package_inputs(scope_wire)',
         'PRIMARY KEY (scope_wire)','UNIQUE (handoff_id)'],
        ['committed_credential_handoff_guard',A+'._commit_credential_handoff()',17,'O',True,True])
    verify_handoff_table(db,N+'.stop_intents',OWNER,None,
        [['scope_wire','text',True],['action_id','text',True],['intent_wire','text',True],['registering_xid','xid8',True]],
        ["CHECK (action_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text)",'CHECK (octet_length(intent_wire) <= 4096)',
         'CHECK (octet_length(scope_wire) <= 512)',f'FOREIGN KEY (scope_wire) REFERENCES {N}.scope_state(scope_wire)',
         'PRIMARY KEY (scope_wire)','UNIQUE (action_id)'],
        ['committed_stop_intent_guard',N+'._stop_intent_commit_guard()',5,'O',True,True])


def install_and_verify_joined_addon(db, parent_functions, *, late_capture=False):
    held(PACKET_POLICY_PATH, PACKET_POLICY_SHA256, 8192)
    if late_capture:
        held(LATE_CAPTURE_POLICY_PATH, LATE_CAPTURE_POLICY_SHA256, 8192)
        source=held(LATE_CAPTURE_ADDON_PATH, LATE_CAPTURE_ADDON_SHA256, 65536).decode('utf8')
    else:
        source=held(JOINED_ADDON_PATH, JOINED_ADDON_SHA256, 32768).decode('utf8')
    signatures={
        '_packet_capture':(N,OWNER,['wire','reservation_wire','capture_id'],['text','text','text'],'jsonb',None,'i',False),
        '_packet_plan':(N,OWNER,['command','auth','position_no','writer_binding','fence','prior_wire'],
            ['jsonb','jsonb','bigint','text','jsonb','text'],'jsonb',None,'s',False),
    }
    if late_capture:
        signatures['_collection_authorization']=(N,OWNER,['wire'],['text'],'text',None,'s',False)
    db.sql(source, timeout=30)
    verify_companion_functions(db, source, 'packet', signatures)
    if db.scalar(f"SELECT count(*) FROM pg_proc WHERE pronamespace IN({literal(A)}::regnamespace,{literal(N)}::regnamespace);")!=str(parent_functions+len(signatures)):
        raise RuntimeError('b3_joined_function_inventory_refused')


def verify_handoff_table(db,relation,owner,grantee,columns,constraints,trigger):
    oid=literal(relation)+'::regclass'
    actual=json.loads(db.scalar(f"""SELECT jsonb_build_object(
     'owner',(SELECT jsonb_build_array(pg_get_userbyid(c.relowner),c.relkind::text,c.relpersistence::text,c.relrowsecurity,c.relforcerowsecurity,c.reloptions) FROM pg_class c WHERE c.oid={oid}),
     'columns',(SELECT jsonb_agg(jsonb_build_array(a.attname,a.atttypid::regtype::text,a.attnotnull) ORDER BY a.attnum) FROM pg_attribute a
       WHERE a.attrelid={oid} AND a.attnum>0 AND NOT a.attisdropped AND a.attacl IS NULL AND NOT a.atthasdef AND a.attgenerated=''),
     'constraints',(SELECT jsonb_agg(pg_get_constraintdef(c.oid,true) ORDER BY pg_get_constraintdef(c.oid,true) COLLATE "C") FROM pg_constraint c WHERE c.conrelid={oid} AND c.convalidated AND c.contype<>'t'),
     'triggers',(SELECT jsonb_agg(jsonb_build_array(t.tgname,t.tgfoid::regprocedure::text,t.tgtype,t.tgenabled,t.tgdeferrable,t.tginitdeferred))
       FROM pg_trigger t WHERE t.tgrelid={oid} AND NOT t.tgisinternal),
     'acl',(SELECT jsonb_agg(jsonb_build_array(coalesce(grantee.rolname,'PUBLIC'),pg_get_userbyid(a.grantor),a.privilege_type,a.is_grantable)
       ORDER BY grantee.rolname COLLATE "C",a.privilege_type COLLATE "C") FROM pg_class c CROSS JOIN LATERAL
       aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a LEFT JOIN pg_roles grantee ON grantee.oid=a.grantee WHERE c.oid={oid}));"""))
    privileges=('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN')
    acl=[[owner,owner,privilege,False] for privilege in privileges]
    if grantee is not None:
        acl.append([grantee,owner,'SELECT',False])
    expected=dict(owner=[owner,'r','p',False,False,None],columns=columns,
        constraints=sorted(constraints),triggers=[trigger],acl=sorted(acl))
    if actual!=expected:
        details={k:dict(actual=actual[k],expected=expected[k]) for k in expected if actual[k]!=expected[k]}
        raise RuntimeError('b2_handoff_table_catalog_refused:'+relation+':'+canonical(details)[:4096])


class AllocationFixture:
    def __init__(self,db,*,creator_edges=False,joined=False,late_capture=False):
        if type(creator_edges) is not bool:raise RuntimeError('b2_fixture_creator_mode_refused')
        if not isinstance(db,IsolatedPostgres) or db.identity.get('network')!='none':raise RuntimeError('b2_owned_fixture_required')
        self.db=db
        self.direct_scram=isinstance(db,AllocationScramPostgres)
        self.independent_deadlines=self.direct_scram and db.independent_deadlines
        self.owner_retirement=isinstance(db,AllocationRetirementPostgres)
        self.handoff=isinstance(db,AllocationHandoffPostgres)
        self.joined=isinstance(db,AllocationJoinedPostgres)
        if type(joined) is not bool or type(late_capture) is not bool or ((joined or late_capture) and not self.joined):
            raise RuntimeError('b3_fixture_profile_refused')
        self.late_capture=late_capture
        self.scope_count=db.scope_count if self.direct_scram else 2
        if self.direct_scram and not creator_edges:
            raise RuntimeError('b2_scram_fixture_creator_required')
        self.arrangements=0  # Trusted fixture provenance only; no actor capability.
        raw=held(SQL_PATH,SOURCE_SHA256,262144);loader=held(LOADER_PATH,LOADER_SHA256,32768)
        self.source_api={'__file__':str(LOADER_PATH),'__name__':'b2_reviewed_source'}
        # Dataclasses require a real module identity, while held bytes—not a
        # second pathname read—remain the executed source.
        import types,sys
        module=types.ModuleType('b2_reviewed_source');module.__file__=str(LOADER_PATH);sys.modules[module.__name__]=module
        exec(compile(loader,str(LOADER_PATH),'exec'),module.__dict__)
        self.source_api=module.__dict__
        self.source=module.extract_source(raw,expected_sql_sha256=SOURCE_SHA256,expected_policy_sha256=POLICY_SHA256)
        self.policy=json.loads(held(POLICY_PATH,POLICY_FILE_SHA256,65536))
        if sha(canonical(self.policy))!=POLICY_SHA256:raise RuntimeError('b2_policy_refused')
        image=json.loads(db._command(['image','inspect',db.identity['image_id']]).stdout)[0]
        verify_owned_postgres_image(image,db.identity)
        self.scopes=[];self.actors=[]
        for serial in range(self.scope_count):
            base=10000+serial*100
            u=lambda i:str(UUID(int=base+i))
            scope=dict(owner_id=u(1),run_id=u(2),market_epoch=u(3))
            actors={name:'vn_jupiter_b2_'+str(serial)+'_'+name for name in PROFILES}
            bindings={name:u(5+i) for i,name in enumerate(PROFILES)}
            self.actors.extend(actors.values())
            self.scopes.append(dict(scope=scope,installation_id=u(4),actors=actors,bindings=bindings,
                issuer=u(9),endpoints=[u(10),u(11)],registration=u(12),epoch=u(13),stop_id=u(14),action_id=u(15)))
        bootstrap='BEGIN;\n'+''.join(
            f'CREATE ROLE {owner} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;\n'
            for owner in (ANCHOR_OWNER,OWNER))
        actor_ddl=''.join(f'CREATE ROLE {actor} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;\n' for actor in self.actors)
        if creator_edges:
            if self.owner_retirement:
                db.create_scram_issuer()
            else:
                db.sql(f'CREATE ROLE {CREATOR} LOGIN NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;')
            if db.scalar(f"SELECT session_user={literal(CREATOR)} AND current_user=session_user AND rolcreaterole AND NOT rolsuper FROM pg_roles WHERE rolname=session_user;",role=CREATOR)!='t':
                raise RuntimeError('b2_actual_limited_creator_required')
            issue_prefix="BEGIN; SET LOCAL createrole_self_grant='';\n"
            if self.direct_scram:
                actor_ddl=db.actor_ddl(self.actors)
                # No verifier-bearing SQL diagnostics leave the fixture.
                issued=db.sql(issue_prefix+actor_ddl+'COMMIT;\n',role=CREATOR,check=False)
                if issued.returncode:
                    raise RuntimeError('b2_scram_fixture_issuer_refused')
                db.verify_actor_deadlines()
            else:
                db.sql(issue_prefix+actor_ddl+'COMMIT;\n',role=CREATOR)
        else:
            bootstrap+=actor_ddl
        bootstrap+=f'CREATE SCHEMA {A}; CREATE SCHEMA {N}; REVOKE ALL ON SCHEMA {A},{N} FROM PUBLIC;\n'+raw.decode()
        db.sql(bootstrap+'COMMIT;\n',timeout=30)
        compare_constructors(db,self.source)
        seal=f'BEGIN;\nALTER SCHEMA {A} OWNER TO {ANCHOR_OWNER}; ALTER SCHEMA {N} OWNER TO {OWNER};\n'
        seal+=''.join(f'ALTER TABLE {ns}.{name} OWNER TO {ANCHOR_OWNER if ns==A else OWNER};\n'
                      for ns,name in module.TABLES)
        seal+=''.join(f"ALTER FUNCTION {row['signature']} OWNER TO {OWNER};\n" for row in self.source.functions())
        broker=self.source.anchor_function()['signature']
        seal+=f'ALTER FUNCTION {broker} OWNER TO {ANCHOR_OWNER};\n'
        # Grant explicitly from the final anchor owner. The disposable
        # bootstrap superuser needs no persistent role membership.
        seal+=f'SET LOCAL ROLE {ANCHOR_OWNER}; GRANT USAGE ON SCHEMA {A} TO {OWNER};\n'
        seal+=f'GRANT SELECT ON {A}.package_inputs,{A}.actor_bindings TO {OWNER};\n'
        seal+=f'GRANT EXECUTE ON FUNCTION {broker} TO {OWNER}; RESET ROLE;\n'
        seal+='REVOKE ALL ON TYPE '+','.join(ns+'.'+name for ns,name in module.TABLES)+' FROM PUBLIC;\n'
        getter_only={scope['actors']['reader'] for scope in self.scopes} if self.independent_deadlines else set()
        for actor in self.actors:
            entries=f'{N}.get_original(text)' if actor in getter_only else f'{N}.submit(text),{N}.get_original(text)'
            seal+=f'GRANT USAGE ON SCHEMA {N} TO {actor}; GRANT EXECUTE ON FUNCTION {entries} TO {actor};\n'
        seal+='COMMIT;';db.sql(seal,timeout=30)
        verify_functions(db,self.source,self.actors,getter_only=getter_only)
        verify_seal(db,self.source,self.actors,creator_edges=creator_edges,actor_count=4*self.scope_count)
        if self.owner_retirement:
            terminal_functions=len(self.source.functions())+1+3
            install_and_verify_terminal_addon(db,terminal_functions)
        if self.handoff:
            install_and_verify_handoff_addons(db,terminal_functions,
                self.scopes[0]['actors']['control'],self.scopes[0]['actors']['reader'])
        if self.joined:
            install_and_verify_joined_addon(db, terminal_functions+15, late_capture=self.late_capture)
        # Real immutable scope/sessionOID/name/capability inputs are independently
        # specified here, not granted by a caller-supplied binding boolean.
        for scope in self.scopes:
            values=[]
            dbid=sha(db.scalar('SELECT current_database()||\':\'||oid::text FROM pg_database WHERE datname=current_database();'))
            for profile,actor in scope['actors'].items():
                oid=db.scalar(f'SELECT oid::text FROM pg_roles WHERE rolname={literal(actor)};')
                values.append(dict(principal_binding_id=scope['bindings'][profile],database_identity_sha256=dbid,
                    session_user_oid=oid,session_user_name=actor,scope=scope['scope'],capabilities=PROFILES[profile],
                    recorder_package_sha256=sha('synthetic-b2-recorder-package'),reader_package_sha256=sha('synthetic-b2-reader-package'),
                    issuer_binding_id=scope['issuer'],endpoint_bindings=[dict(provider_family=family,endpoint_binding_id=eid) for family,eid in zip(('jupiter-price-v3','solana-rpc'),scope['endpoints'])],installation_id=scope['installation_id']))
                if self.independent_deadlines:
                    issuance_id=str(UUID(int=UUID(scope['bindings'][profile]).int+1_000_000))
                    values[-1].update(db.deadline_binding(actor,profile,issuance_id))
            manifest_format=DEADLINE_MANIFEST_FORMAT if self.independent_deadlines else 'ga-jupiter-b2-capability-manifest-research-v3-v1'
            scope['manifest']=dict(format=manifest_format,native_policy_sha256=POLICY_SHA256,scope=scope['scope'],installation_id=scope['installation_id'],bindings=values)
            sw=canonical(scope['scope'])
            db.sql(f"INSERT INTO {A}.package_inputs VALUES({literal(sw)},{literal(scope['installation_id'])},'{{}}',{literal(canonical(scope['manifest']))},'{{}}',{literal('0'*64)},NULL);")
            for binding in values:
                db.sql(f"INSERT INTO {A}.actor_bindings VALUES({literal(binding['principal_binding_id'])},{literal(sw)},{binding['session_user_oid']},{literal(binding['session_user_name'])},ARRAY[{','.join(map(literal,binding['capabilities']))}]::text[],{literal(canonical(binding))});")
        # Only now, after independent constructors, complete source signatures /
        # bodies, effective privilege checks, and known actor input verification,
        # may this owned fixture capture its instance-specific K as held gold.
        frame=json.loads(db.scalar(SETTINGS+f"WITH k AS MATERIALIZED(SELECT {N}._catalog() value) SELECT jsonb_build_object('value',value,'wire',{N}._c14n(value),'sha',{N}._sha({N}._c14n(value))) FROM k;",timeout=30))
        if canonical(frame['value'])!=frame['wire'] or sha(frame['wire'])!=frame['sha']:raise RuntimeError('b2_catalog_canonical_refused')
        self.catalog=frame
        for scope in self.scopes:self._finish_scope(scope)

    def _finish_scope(self,s):
        manifest=dict(format='ga-jupiter-b2-native-package-manifest-research-v3-v1',policy_sha256=POLICY_SHA256,SQL_sha256=SOURCE_SHA256,source_validator_sha256=LOADER_SHA256,
            constructor_catalog_sha256=self.catalog['sha'],capability_manifest_sha256=sha(canonical(s['manifest'])))
        if set(manifest)!=set(self.policy['source_gold']['native_package_manifest']):raise RuntimeError('b2_native_manifest_shape_refused')
        m=sha(canonical(manifest))
        policies={key:sha('synthetic-b2-'+key) for key in ('acquisition_sha256','source_sha256','transport_sha256','a1_schema_sha256','raw_parser_sha256')}
        if self.joined:
            from vonneumann.market import source_admission_v3
            policies.update(source_admission_v3.DEPENDENCIES, a1_schema_sha256=source_admission_v3.POLICY_SHA256)
        policies.update(recorder_package_sha256=sha('synthetic-b2-recorder-package'),reader_package_sha256=sha('synthetic-b2-reader-package'),native_package_sha256=m)
        roles=[(k,s['scope'][k]) for k in ('owner_id','run_id','market_epoch')]+[('installation_id',s['installation_id'])]+[('principal_binding_id',v) for v in s['bindings'].values()]+[('issuer_binding_id',s['issuer'])]+[('endpoint_binding_id',x) for x in s['endpoints']]+[('registration_id',s['registration']),('acquisition_epoch',s['epoch']),('control_action_id',s['stop_id'])]
        specs=[dict(original_id=uid,identity_role=role,association=dict(owner_id=s['scope']['owner_id'],run_id=None if role=='owner_id' else s['scope']['run_id'],market_epoch=None if role in ('owner_id','run_id') else s['scope']['market_epoch'],packet_reservation_id=None)) for role,uid in roles]
        genesis=dict(format='ga-jupiter-b2-genesis-registry-research-v3-v1',scope=s['scope'],identity_specs=specs,
          initial_acquisition_spec=dict(registration_id=s['registration'],acquisition_epoch=s['epoch'],predecessor_epoch=None,recorder_principal_binding_id=s['bindings']['recorder'],reader_principal_binding_id=s['bindings']['reader'],issuer_binding_id=s['issuer'],recorder_package_sha256=policies['recorder_package_sha256'],reader_package_sha256=policies['reader_package_sha256'],policies=policies,endpoint_bindings=s['manifest']['bindings'][0]['endpoint_bindings']),terminal_stop_action_id=s['stop_id'])
        self.source_api['validate_genesis'](genesis,expected_scope=s['scope'],expected_binding_ids=list(s['bindings'].values()),expected_policies=policies,expected_installation_id=s['installation_id'])
        if self.handoff:
            package_format=HANDOFF_PACKAGE_FORMAT
        elif self.independent_deadlines:
            package_format=DEADLINE_PACKAGE_FORMAT
        else:
            package_format=SCRAM_FORMAT if self.direct_scram else 'ga-jupiter-b2-fixture-package-input-research-v3-v1'
        package=dict(format=package_format,native_policy_sha256=POLICY_SHA256,installation_id=s['installation_id'],policies=policies,catalog_manifest_sha256=self.catalog['sha'],actor_manifest_sha256=sha(canonical(s['manifest'])),native_package_sha256=m)
        head=dict(scope=s['scope'],native_sequence='0',native_head_sha256=sha(canonical(dict(format='ga-jupiter-b2-empty-head-research-v3-v1',native_policy_sha256=POLICY_SHA256,scope=s['scope']))),active_acquisition_epoch=None,active_fence_id=None,fence_revision='0',source_mode='uninstalled',last_admission_sha256=None,last_ingest_sequence='0',last_availability_sha256=None,previous_seal_sha256=None)
        accounting=dict(committed_positions='0',logical_UTF8_bytes='0',identity_rows='0',domain_rows='0',dependency_rows='0',retained_rows='6',row_writes='0',index_entries='0',Stop_reserve_consumed=False)
        self.db.sql(f"BEGIN; UPDATE {A}.package_inputs SET package_wire={literal(canonical(package))},genesis_wire={literal(canonical(genesis))},expected_catalog_sha256={literal(self.catalog['sha'])} WHERE scope_wire={literal(canonical(s['scope']))}; INSERT INTO {N}.scope_state VALUES({literal(canonical(s['scope']))},{literal(canonical(head))},{literal(canonical(accounting))}); COMMIT;")
        s.update(package=package,genesis=genesis,head=head,accounting=accounting,native_manifest=manifest)

    def reset(self):
        self.arrangements+=1
        # Trusted test arrangement only, never an installed API, retry, or
        # history rewrite by an actor. Each test retains original bytes once.
        self.db.sql('BEGIN; '+''.join('DELETE FROM '+N+'.'+n+';' for n in ('dependency_associations','domain_facts','identities','journal_entries','original_operations','scope_state'))+' COMMIT;')
        for s in self.scopes:
            sw=literal(canonical(s['scope']))
            self.db.sql(f"BEGIN; UPDATE {A}.package_inputs SET package_wire={literal(canonical(s['package']))},actor_manifest_wire={literal(canonical(s['manifest']))},genesis_wire={literal(canonical(s['genesis']))},expected_catalog_sha256={literal(self.catalog['sha'])},retirement_wire=NULL WHERE scope_wire={sw}; INSERT INTO {N}.scope_state VALUES({sw},{literal(canonical(s['head']))},{literal(canonical(s['accounting']))}); COMMIT;")

    def owner_retirement_sql(self, s, stop):
        """One exact closed fixture procedure, never an installed actor API."""
        if self.db.identity.get('network')!='none' or s is not self.scopes[0]:
            raise ValueError('b2_owned_retirement_scope_refused')
        fixed_roles=('vn_jupiter_b2_0_installer','vn_jupiter_b2_0_recorder')
        if tuple(s['actors'][profile] for profile in ('installer','recorder'))!=fixed_roles:
            raise ValueError('b2_owned_retirement_role_refused')
        if (set(stop)!={'format','native_policy_sha256','scope','action_id','action_kind','expected_head',
                        'expected_fence_id','expected_fence_revision','body'}
                or stop['format']!='ga-jupiter-b2-allocation-command-research-v3-v1'
                or stop['native_policy_sha256']!=POLICY_SHA256 or stop['scope']!=s['scope']
                or stop['action_kind']!='source_stop' or stop['action_id']!=s['stop_id']
                or stop['expected_fence_id'] is not None or stop['expected_fence_revision'] is not None
                or set(stop['expected_head'])!={'native_sequence','native_head_sha256','previous_seal_sha256'}
                or stop['expected_head']['native_sequence']!='3' or stop['expected_head']['previous_seal_sha256'] is not None
                or set(stop['body'])!={'expected_control_sha256','expected_mode'} or stop['body']['expected_mode']!='open'):
            raise ValueError('b2_owned_retirement_original_refused')
        package=s['package']
        members={row['principal_binding_id']:row for row in s['manifest']['bindings']}
        selected=[members[s['bindings'][profile]] for profile in ('installer','recorder')]
        writers=[dict(binding_id=row['principal_binding_id'],role_name=row['session_user_name'],
            role_oid=row['session_user_oid'],binding_sha256=sha(canonical(row))) for row in selected]
        marker=dict(format='ga-jupiter-b2-terminal-retirement-fixture-v1',scope=s['scope'],
            native_package_sha256=package['native_package_sha256'],catalog_manifest_sha256=package['catalog_manifest_sha256'],
            stop_action_id=s['stop_id'],stop_command_sha256=sha(canonical(stop)),writers=writers)
        marker_wire=canonical(marker)
        if len(marker_wire.encode('utf8'))>4096:
            raise ValueError('b2_owned_retirement_wire_refused')
        scope=literal(canonical(s['scope']))
        locked_bindings=''
        for row in selected:
            locked_bindings+=f"""
 PERFORM 1 FROM {A}.actor_bindings a
  WHERE a.scope_wire={scope} AND a.binding_id={literal(row['principal_binding_id'])}
   AND a.session_name={literal(row['session_user_name'])} AND a.session_oid={row['session_user_oid']}::oid
   AND a.binding_wire={literal(canonical(row))} AND to_jsonb(a.capabilities)={literal(canonical(row['capabilities']))}::jsonb
  FOR UPDATE NOWAIT;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_owned_retirement_role_refused'; END IF;
 PERFORM 1 FROM pg_catalog.pg_roles r WHERE r.oid={row['session_user_oid']}::oid
  AND r.rolname={literal(row['session_user_name'])} AND r.rolcanlogin;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_owned_retirement_role_refused'; END IF;
"""
        sql=BEGIN+SETTINGS+f"""
DO $b2_retirement$
DECLARE head jsonb; account jsonb;
BEGIN
 IF session_user IS DISTINCT FROM 'postgres' THEN RAISE EXCEPTION 'b2_owned_retirement_owner_refused'; END IF;
 PERFORM 1 FROM {A}.package_inputs p WHERE p.scope_wire={scope}
  AND p.retirement_wire IS NULL AND p.package_wire={literal(canonical(package))}
  AND p.genesis_wire={literal(canonical(s['genesis']))} AND p.actor_manifest_wire={literal(canonical(s['manifest']))}
  AND p.expected_catalog_sha256={literal(self.catalog['sha'])}
 FOR UPDATE NOWAIT;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_owned_retirement_package_refused'; END IF;
 {locked_bindings}
 SELECT st.head_wire::jsonb,st.accounting_wire::jsonb INTO head,account
  FROM {N}.scope_state st WHERE st.scope_wire={scope} FOR UPDATE NOWAIT;
 IF NOT FOUND OR head->>'source_mode' IS DISTINCT FROM 'open'
  OR head->>'native_sequence' IS DISTINCT FROM '3' OR head->>'fence_revision' IS DISTINCT FROM '1'
  OR pg_catalog.jsonb_typeof(head->'active_fence_id') IS DISTINCT FROM 'string'
  OR head->>'active_acquisition_epoch' IS DISTINCT FROM {literal(s['epoch'])}
  OR account->'Stop_reserve_consumed' IS DISTINCT FROM 'false'::jsonb
  OR pg_catalog.jsonb_build_object('native_sequence',head->>'native_sequence',
       'native_head_sha256',head->>'native_head_sha256','previous_seal_sha256',NULL)
       IS DISTINCT FROM {literal(canonical(stop['expected_head']))}::jsonb
  OR NOT EXISTS(SELECT 1 FROM {N}.original_operations o WHERE o.scope_wire={scope}
       AND o.native_sequence=3 AND o.action_kind='source_resume' AND o.finalized
       AND o.command_sha256={literal(stop['body']['expected_control_sha256'])})
  OR {N}._sha({N}._c14n({N}._catalog())) IS DISTINCT FROM {literal(self.catalog['sha'])}
 THEN RAISE EXCEPTION 'b2_owned_retirement_head_refused'; END IF;
 ALTER ROLE vn_jupiter_b2_0_installer NOLOGIN;
 ALTER ROLE vn_jupiter_b2_0_recorder NOLOGIN;
 UPDATE {A}.package_inputs SET retirement_wire={literal(marker_wire)}
  WHERE scope_wire={scope} AND retirement_wire IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'b2_owned_retirement_marker_refused'; END IF;
END;
$b2_retirement$;
COMMIT;
"""
        return marker,sql

    def restore_owned_retirement(self, s):
        """Dispose of the synthetic test arrangement, not a runtime restore."""
        if self.db.identity.get('network')!='none' or s is not self.scopes[0]:
            raise ValueError('b2_owned_retirement_scope_refused')
        scope=literal(canonical(s['scope']))
        self.db.sql(BEGIN+f"""
SELECT scope_wire FROM {A}.package_inputs WHERE scope_wire={scope} FOR UPDATE NOWAIT;
ALTER ROLE vn_jupiter_b2_0_installer LOGIN;
ALTER ROLE vn_jupiter_b2_0_recorder LOGIN;
UPDATE {A}.package_inputs SET retirement_wire=NULL WHERE scope_wire={scope};
COMMIT;
""")

    def head(self,s):
        return json.loads(self.db.scalar(f'SELECT head_wire FROM {N}.scope_state WHERE scope_wire={literal(canonical(s["scope"]))};'))

    def command(self,s,kind='installation',*,action_id=None):
        head=self.head(s);p=s['package']
        body=(dict(installation_id=s['installation_id'],scope=s['scope'],policies=p['policies'],catalog_manifest_sha256=p['catalog_manifest_sha256'],actor_manifest_sha256=p['actor_manifest_sha256'],genesis_registry_sha256=sha(canonical(s['genesis']))) if kind=='installation' else dict(expected_control_sha256=None,expected_mode='paused'))
        digest=LATE_CAPTURE_POLICY_SHA256 if self.late_capture and kind=='capture_retention' else (PACKET_POLICY_SHA256 if kind in PACKET_KINDS else POLICY_SHA256)
        return dict(format='ga-jupiter-b2-allocation-command-research-v3-v1',native_policy_sha256=digest,scope=s['scope'],action_id=action_id or (s['action_id'] if kind=='installation' else s['stop_id']),action_kind=kind,expected_head={k:head[k] for k in ('native_sequence','native_head_sha256','previous_seal_sha256')},expected_fence_id=None,expected_fence_revision=None,body=body)

    def query(self,c):
        return dict(format='ga-jupiter-b2-original-query-research-v3-v1',native_policy_sha256=c['native_policy_sha256'],scope=c['scope'],target_kind=c['action_kind'],target_id=c['action_id'],expected_original_command_sha256=sha(canonical(c)),correlation=dict(kind='original_action_id',id=c['action_id']))

    def call(self,fn,value,role):
        if fn not in ('submit','get_original'):raise ValueError('b2_fixture_entry_refused')
        wire=canonical(value)
        if self.joined and fn=='submit' and value.get('action_kind')=='capture_retention':
            if '\x00' in wire or len(wire.encode())>1048576:
                raise ValueError('b3_fixture_capture_literal_refused')
            sql_literal="'"+wire.replace("'","''")+"'"
        else:
            sql_literal=literal(wire)
        return f'SELECT {N}.{fn}({sql_literal});\n'

    def get(self,c,role):
        result=self.db.sql(SETTINGS+self.call('get_original',self.query(c),role),role=role)
        if not result.stdout.endswith('\n') or result.stdout.count('\n')!=1 or len(result.stdout.encode())>8388608:raise RuntimeError('b2_fixture_response_refused')
        value=json.loads(result.stdout)
        if canonical(value)+'\n'!=result.stdout:raise RuntimeError('b2_fixture_response_refused')
        return value

    def snapshot(self):
        rows=[]
        for ns,name in self.source_api['TABLES']:
            value=json.loads(self.db.scalar(f"SELECT coalesce(jsonb_agg(jsonb_build_object('row',to_jsonb(t),'xmin',xmin::text,'ctid',ctid::text) ORDER BY to_jsonb(t)::text),'[]') FROM {ns}.{name} t;"))
            rows.append([ns,name,value])
        return rows

    def writer(self,role):return StepSession(self.db,role)

    def anchor_session(self):
        # Trusted mutation/lock arrangement only, never an actor API.
        return StepSession(self.db,'postgres',trusted_anchor=True)

    def wait_for_blocker(self,waiter_pid,blocker_pid):
        if type(waiter_pid) is not int or type(blocker_pid) is not int or min(waiter_pid,blocker_pid)<=0 or waiter_pid==blocker_pid:
            raise ValueError('b2_owned_backend_identity_refused')
        deadline=time.monotonic()+.6
        while True:
            found=json.loads(self.db.scalar(f'SELECT to_jsonb(pg_blocking_pids({waiter_pid}));',timeout=1))
            if found==[blocker_pid]:return
            if time.monotonic()>=deadline:raise RuntimeError('b2_owned_lock_event_unobserved')


class StepSession:
    """One exact tracked writer, bounded20s; no inherited provider credentials."""
    def __init__(self,db,role,*,trusted_anchor=False):
        direct_issuer=role==CREATOR and isinstance(db,AllocationRetirementPostgres)
        actors={f'vn_jupiter_b2_{i}_{p}' for i in range(2) for p in PROFILES}
        if isinstance(db,AllocationHandoffPostgres):
            actors.add(SUCCESSOR_RECORDER)
        allowed=role=='postgres' if trusted_anchor is True else (trusted_anchor is False and (role in actors or direct_issuer))
        if not allowed:raise ValueError('b2_writer_role_refused')
        self.deadline=time.monotonic()+20;self.buffer=b'';self.db=db
        if isinstance(db,AllocationScramPostgres) and not trusted_anchor:
            command=db.direct_command(role,statement_ms=10000)
        else:
            command=db._docker+['exec','-i','--env','PGOPTIONS=-c statement_timeout=10000',db._container_id,'psql','-X','-w','-h','/tmp','-U',role,'-d','postgres','-v','ON_ERROR_STOP=1','-v','VERBOSITY=verbose','-A','-t','-q']
        self._process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=db._env,bufsize=0)
        db._sessions.append(self)
        self.send(BEGIN+SETTINGS)

    def send(self,text):
        if time.monotonic()>=self.deadline:raise TimeoutError('b2_owned_writer_timeout')
        self._process.stdin.write(text.encode());self._process.stdin.flush()

    def line(self):
        while b'\n' not in self.buffer:
            left=self.deadline-time.monotonic()
            if left<=0 or not select.select([self._process.stdout],[],[],left)[0]:raise TimeoutError('b2_owned_writer_timeout')
            data=os.read(self._process.stdout.fileno(),65536)
            if not data:raise RuntimeError('b2_owned_writer_refused:'+self.failure_stderr())
            self.buffer+=data
            if len(self.buffer)>8388608:raise RuntimeError('b2_owned_response_bound')
        line,self.buffer=self.buffer.split(b'\n',1)
        return line.decode()

    def backend_pid(self):
        self.send('SELECT pg_catalog.pg_backend_pid();\n')
        value=self.line()
        if not re.fullmatch(r'[1-9][0-9]{0,9}',value):raise RuntimeError('b2_owned_backend_identity_refused')
        return int(value)

    def failure_stderr(self):
        # Retain only this tracked synthetic-database child's bounded stderr.
        # Drain before waiting so a full error pipe cannot deadlock observation.
        raw=b''
        while True:
            left=self.deadline-time.monotonic()
            if left<=0 or not select.select([self._process.stderr],[],[],left)[0]:
                raise TimeoutError('b2_owned_writer_diagnostic_timeout')
            part=os.read(self._process.stderr.fileno(),min(4096,32769-len(raw)))
            if not part:break
            raw+=part
            if len(raw)>32768:raise RuntimeError('b2_owned_writer_stderr_bound')
        self._process.wait(timeout=max(.001,self.deadline-time.monotonic()))
        return raw.decode('utf8','replace')

    def finish(self,command='COMMIT;',*,check=True):
        self.send(command+'\n');self._process.stdin.close()
        left=max(.001,self.deadline-time.monotonic())
        code=self._process.wait(timeout=left)
        stderr=self._process.stderr.read(32768).decode()
        if check and code:raise RuntimeError('b2_owned_writer_refused:'+next((x for x in stderr.splitlines() if 'b2_' in x),'fixed refusal'))
        return code,stderr

    def close(self):
        if self._process.poll() is None:
            self._process.kill();self._process.wait(timeout=5)
        for stream in (self._process.stdin,self._process.stdout,self._process.stderr):
            if stream is not None and not stream.closed:stream.close()
