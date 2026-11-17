"""Held-source B2 first-slice loader. No connections, gold adoption or authority.

Exact expected source/policy pins must come from independent review. Extracted
source constructors/specifications are inputs to an independently reviewed owned
fixture; a current catalog hash is never accepted merely because this file ran.
"""
from dataclasses import dataclass
import hashlib
import json
import re

NAMESPACE = 'vn_jupiter_b2_allocation_research_v3'
ANCHOR = 'vn_jupiter_b2_fixture_anchor'
OWNER = 'vn_jupiter_b2_sealed_owner'
ANCHOR_OWNER = 'vn_jupiter_b2_anchor_owner'
POLICY_SHA256 = 'e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0'
HEX = re.compile(r'[0-9a-f]{64}\Z')
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
TABLES = ((ANCHOR, 'package_inputs'), (ANCHOR, 'actor_bindings'),
          *((NAMESPACE, n) for n in ('scope_state', 'original_operations',
           'journal_entries', 'identities', 'domain_facts', 'dependency_associations')))
FUNCTIONS = {
 '_c14n': (('v','jsonb'),), '_sha': (('v','text'),),
 '_keys': (('v','jsonb'),('names','text[]')), '_scope': (('v','jsonb'),),
 '_pin': (('kind','text'),('id','text'),('body','text')), '_clock': (),
 '_catalog': (), '_check_credential_window': (('windows','jsonb'),('observed_us','int8')),
 '_auth': (('scope','jsonb'),('capability','text'),('retired_writer_binding_id','text'),('terminal_stop_sha','text'),('terminal_read_sha','text')),
 '_limits': (), '_deps': (('v','jsonb'),),
 '_cost': (('c','jsonb'),('r','jsonb'),('ids','jsonb'),('facts','jsonb')),
 '_budget': (('scope_wire','text'),('kind','text'),('cost','jsonb')),
 '_reply': (('scope','jsonb'),('target_id','text'),('expected_sha','text'),('getter_recovery','bool'),('terminal_stop_sha','text')),
 'get_original': (('wire','text'),), '_submit': (('wire','text'),('register_stop_intent','bool')), 'submit': (('wire','text'),), '_commit_guard': (),
}
IMMUTABLE = frozenset(('_c14n','_sha','_keys','_scope','_pin','_limits','_deps','_check_credential_window'))
VOLATILE = frozenset(('_clock','_submit','submit','_commit_guard'))
DEFINER = frozenset(('submit','get_original','_commit_guard'))
TEXT = frozenset(('_c14n','_sha','_scope','_reply','get_original','_submit','submit'))


class SourceRefusal(ValueError):
    pass


def refuse():
    raise SourceRefusal('b2_source_refused') from None


def canonical(v):
    return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


@dataclass(frozen=True)
class ReviewedSource:
    sql_sha256: str
    policy_sha256: str
    table_rows_json: str
    function_rows_json: str
    anchor_sql: str
    native_sql: str
    final_sql: str
    anchor_function_json: str
    # These fields identify bytes, not a verified catalog or an installed actor.

    def tables(self):
        return json.loads(self.table_rows_json)

    def functions(self):
        return json.loads(self.function_rows_json)

    def anchor_function(self):
        return json.loads(self.anchor_function_json)


def function_header(name):
    args=', '.join(a+' pg_catalog.'+t for a,t in FUNCTIONS[name])
    result='void' if name=='_check_credential_window' else 'trigger' if name=='_commit_guard' else ('bool' if name=='_keys' else ('text' if name in TEXT else 'jsonb'))
    volatility='IMMUTABLE' if name in IMMUTABLE else ('VOLATILE' if name in VOLATILE else 'STABLE')
    return (f'CREATE FUNCTION {NAMESPACE}.{name}({args})\n'
      f'RETURNS pg_catalog.{result}\nLANGUAGE plpgsql {volatility} SECURITY '+('DEFINER' if name in DEFINER else 'INVOKER')+'\n'
      'CALLED ON NULL INPUT PARALLEL UNSAFE COST 100\n'
      "SET search_path = 'pg_catalog', 'pg_temp'\nSET TimeZone = 'UTC'\n"
      "SET client_encoding = 'UTF8'\nSET standard_conforming_strings = 'on'\nAS $b2$\n")


def extract_source(raw, *, expected_sql_sha256, expected_policy_sha256):
    if type(raw) is not bytes or not 0<len(raw)<=262144:
        refuse()
    if (type(expected_sql_sha256) is not str or not HEX.fullmatch(expected_sql_sha256)
        or type(expected_policy_sha256) is not str or expected_policy_sha256!=POLICY_SHA256
        or hashlib.sha256(raw).hexdigest()!=expected_sql_sha256):
        refuse()
    try:
        src=raw.decode('utf8','strict')
    except UnicodeError:
        refuse()
    prefix=(f'-- B2 finite installation/getter/Stop research candidate; no native/hosted authority.\n'
      f'-- policy-sha256: {POLICY_SHA256}\n-- Owned-fixture source review required; never a hosted migration.\n\n')
    if not src.startswith(prefix) or '\x00' in src or '\r' in src:
        refuse()
    rest=src[len(prefix):]
    tables=[]; funcs=[]; anchor=[]; native=[]
    for ns,name in TABLES:
        mark=f'-- TABLE {ns}.{name}\n'; start=f'CREATE TABLE {ns}.{name} (\n'
        if not rest.startswith(mark+start): refuse()
        end=rest.find('\n);\n',len(mark+start))
        if end<0: refuse()
        ddl=rest[len(mark):end+4]
        body=ddl[len(start):-3]
        if any(x in body for x in (';','--','/*','*/','$b2$','\\')):refuse()
        tables.append({'namespace':ns,'name':name,'ddl':ddl,'body_sha256':hashlib.sha256(body.encode()).hexdigest()})
        (anchor if ns==ANCHOR else native).append(ddl)
        rest=rest[end+5:]
    anchor_header=(f'CREATE FUNCTION {ANCHOR}._lock_inputs(requested_scope pg_catalog.text, lock_resume_recorder pg_catalog.bool)\n'
      'RETURNS pg_catalog.void\nLANGUAGE plpgsql VOLATILE SECURITY DEFINER\n'
      'CALLED ON NULL INPUT PARALLEL UNSAFE COST 100\n'
      "SET search_path = 'pg_catalog', 'pg_temp'\nSET TimeZone = 'UTC'\n"
      "SET client_encoding = 'UTF8'\nSET standard_conforming_strings = 'on'\nAS $b2$\n")
    mark='-- ANCHOR FUNCTION _lock_inputs\n'
    if not rest.startswith(mark+anchor_header):refuse()
    end=rest.find('\n$b2$;\n',len(mark+anchor_header))
    if end<0:refuse()
    body=rest[len(mark+anchor_header):end]
    if not body.strip() or '$b2$' in body:refuse()
    anchor_function=dict(namespace=ANCHOR,name='_lock_inputs',
      signature=ANCHOR+'._lock_inputs(pg_catalog.text,pg_catalog.bool)',argument_names=['requested_scope','lock_resume_recorder'],
      argument_types=['text','bool'],header=anchor_header,body='\n'+body+'\n',
      body_sha256=hashlib.sha256(('\n'+body+'\n').encode()).hexdigest(),
      owner=ANCHOR_OWNER,definer=True,volatility='v',public_entry=False)
    rest=rest[end+len('\n$b2$;\n\n'):]
    for name,args in FUNCTIONS.items():
        mark=f'-- FUNCTION {name}\n'; header=function_header(name)
        if not rest.startswith(mark+header):refuse()
        end=rest.find('\n$b2$;\n',len(mark+header))
        if end<0:refuse()
        body=rest[len(mark+header):end]
        if not body.strip() or '$b2$' in body:refuse()
        ddl=rest[len(mark):end+len('\n$b2$;')]
        funcs.append({'name':name,'signature':NAMESPACE+'.'+name+'('+','.join('pg_catalog.'+t for _,t in args)+')',
          'argument_names':[a for a,_ in args] or None,'argument_types':[t for _,t in args],
          'header':header,'body':'\n'+body+'\n','body_sha256':hashlib.sha256(('\n'+body+'\n').encode()).hexdigest(),
          'owner':OWNER,'definer':name in DEFINER,'volatility':'i' if name in IMMUTABLE else ('v' if name in VOLATILE else 's'),
          'public_entry':name in ('submit','get_original')})
        native.append(ddl);rest=rest[end+len('\n$b2$;\n\n'):]
    final=(f'-- TRIGGER committed_original_guard\nCREATE CONSTRAINT TRIGGER committed_original_guard AFTER INSERT ON {NAMESPACE}.original_operations\n'
      f'DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {NAMESPACE}._commit_guard();\n\n'
      f'-- REVOKES\nREVOKE ALL ON FUNCTION {ANCHOR}._lock_inputs(pg_catalog.text,pg_catalog.bool) FROM PUBLIC;\n'
      f'REVOKE ALL ON ALL TABLES IN SCHEMA {NAMESPACE} FROM PUBLIC;\nREVOKE ALL ON ALL FUNCTIONS IN SCHEMA {NAMESPACE} FROM PUBLIC;\n')
    if rest!=final:refuse()
    return ReviewedSource(expected_sql_sha256,expected_policy_sha256,canonical(tables).decode(),canonical(funcs).decode(),
      '\n\n'.join(anchor),'\n\n'.join(native),final,canonical(anchor_function).decode())


def validate_genesis(g, *, expected_scope, expected_binding_ids, expected_policies, expected_installation_id):
    """Validate independently held fixture inputs before constructing source gold."""
    if type(g) is not dict or set(g)!={'format','scope','identity_specs','initial_acquisition_spec','terminal_stop_action_id'}:
        refuse()
    if g['format']!='ga-jupiter-b2-genesis-registry-research-v3-v1' or type(g['scope']) is not dict or g['scope']!=expected_scope:
        refuse()
    if type(expected_scope) is not dict or set(expected_scope)!={'owner_id','run_id','market_epoch'} or any(type(v) is not str or not UUID.fullmatch(v) for v in expected_scope.values()):refuse()
    if type(expected_binding_ids) is not list or len(expected_binding_ids)!=4 or any(type(v) is not str or not UUID.fullmatch(v) for v in expected_binding_ids) or len(set(expected_binding_ids))!=4:refuse()
    if type(expected_installation_id) is not str or not UUID.fullmatch(expected_installation_id):refuse()
    specs=g['identity_specs']
    if type(specs) is not list or len(specs)!=14 or any(type(x) is not dict or type(x.get('original_id')) is not str or not UUID.fullmatch(x['original_id']) for x in specs) or len({x['original_id'] for x in specs})!=14:
        refuse()
    roles={'owner_id':1,'run_id':1,'market_epoch':1,'installation_id':1,'principal_binding_id':4,
           'issuer_binding_id':1,'endpoint_binding_id':2,'registration_id':1,'acquisition_epoch':1,'control_action_id':1}
    actual={}
    for x in specs:
        if type(x) is not dict or set(x)!={'original_id','identity_role','association'} or type(x['original_id']) is not str or not UUID.fullmatch(x['original_id']):refuse()
        role=x['identity_role']
        if type(role) is not str or role not in roles:refuse()
        if role in expected_scope and x['original_id']!=expected_scope[role]:refuse()
        if role=='installation_id' and x['original_id']!=expected_installation_id:refuse()
        actual.setdefault(role,[]).append(x['original_id'])
        association={'owner_id':expected_scope['owner_id'],'run_id':None if role=='owner_id' else expected_scope['run_id'],
          'market_epoch':None if role in ('owner_id','run_id') else expected_scope['market_epoch'],'packet_reservation_id':None}
        if x['association']!=association:refuse()
    if {k:len(v) for k,v in actual.items()}!=roles or set(actual['principal_binding_id'])!=set(expected_binding_ids):refuse()
    if type(expected_policies) is not dict or set(expected_policies)!={'acquisition_sha256','source_sha256','transport_sha256','a1_schema_sha256','raw_parser_sha256','recorder_package_sha256','reader_package_sha256','native_package_sha256'} or any(type(v) is not str or not HEX.fullmatch(v) for v in expected_policies.values()):refuse()
    i=g['initial_acquisition_spec']
    required={'registration_id','acquisition_epoch','predecessor_epoch','recorder_principal_binding_id','reader_principal_binding_id','issuer_binding_id','recorder_package_sha256','reader_package_sha256','policies','endpoint_bindings'}
    if type(i) is not dict or set(i)!=required or i['predecessor_epoch'] is not None or i['policies']!=expected_policies:
        refuse()
    for key in ('registration_id','acquisition_epoch','issuer_binding_id'):
        if i[key]!=actual[key][0]:refuse()
    if g['terminal_stop_action_id']!=actual['control_action_id'][0] or i['recorder_principal_binding_id'] not in expected_binding_ids or i['reader_principal_binding_id'] not in expected_binding_ids:refuse()
    if type(i['endpoint_bindings']) is not list or len(i['endpoint_bindings'])!=2 or any(type(x) is not dict or set(x)!={'provider_family','endpoint_binding_id'} for x in i['endpoint_bindings']) or [x.get('provider_family') for x in i['endpoint_bindings']]!=['jupiter-price-v3','solana-rpc'] or {x.get('endpoint_binding_id')for x in i['endpoint_bindings']}!=set(actual['endpoint_binding_id']):refuse()
    if i['recorder_package_sha256']!=expected_policies['recorder_package_sha256'] or i['reader_package_sha256']!=expected_policies['reader_package_sha256']:refuse()
    if actual['owner_id'][0]!=expected_scope['owner_id'] or actual['run_id'][0]!=expected_scope['run_id'] or actual['market_epoch'][0]!=expected_scope['market_epoch']:refuse()
    raw=canonical(g)
    if len(raw)>8192:refuse()
    return raw
