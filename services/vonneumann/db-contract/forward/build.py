"""Compose the complete cutover candidate offline. No DSN, key or cloud API.

Pinned components retain their distinct reviewed authority. The one transaction
requires an independently supplied migration/catalog review and installs closed.
Production adoption still requires service/browser and hosted acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
TARGET={'supabase_name':'The Dashboard','supabase_ref':'fxpxsciltakyypunglzr',
        'supabase_org':'cqfnnaunmupdyobkyqfo','github_repository_id':1141090963,
        'github_repository':'TOOTRJ/TheDashboard','vercel_project_name':'the-dashboard',
        'vercel_project_id':'prj_wFUe9k9USVreOQcmQKNWRAVsx5fH',
        'vercel_team_id':'team_8iNNxiNjrOseD4gdSCHkQEzF'}
PINNED=json.loads((HERE/'dependencies.json').read_text())

def sha(value): return hashlib.sha256(value.encode()).hexdigest()

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path)
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def inner(value):
 if value.count('BEGIN;\n')!=1 or value.count('COMMIT;\n')!=1:
  raise ValueError('Unreviewed component transaction grammar')
 return value.replace('BEGIN;\n','',1).removesuffix('COMMIT;\n')

def final_functions(source):
 pattern=re.compile(r'^CREATE (?:OR REPLACE )?FUNCTION (vn_\w+\.\w+)\(([\s\S]*?)\)\s*RETURNS[\s\S]*?\$\$([\s\S]*?)\$\$;',re.M)
 matches=list(pattern.finditer(source));result={}
 if len(matches)!=len(re.findall(r'^CREATE (?:OR REPLACE )?FUNCTION ',source,re.M)):
  raise ValueError('Unreviewed forward function grammar')
 for m in matches:
  if m[1] in result and not m[0].startswith('CREATE OR REPLACE FUNCTION '):
   raise ValueError('Unreviewed overload: '+m[1])
  result[m[1]]=m
 return result

def build():
 for path,digest in PINNED.items():
  if sha((ROOT/path).read_text())!=digest: raise ValueError('Reviewed dependency changed: '+path)
 native=module('forward_native',ROOT/'session-auth/build.py')
 evidence=module('forward_evidence',ROOT/'legacy-evidence/build.py')
 v5=native.base
 native_sql,native_manifest=native.build();evidence_sql,evidence_manifest=evidence.build()
 if native_sql!=(ROOT/'session-auth/package.sql').read_text() or evidence_sql!=(ROOT/'legacy-evidence/package.sql').read_text():
  raise ValueError('Component artifact differs from builder')
 dependencies=PINNED
 sources={p:sha((HERE/p).read_text()) for p in ('build.py','dependencies.json','review.sql','admission.sql','catalog.sql')}
 release_id=sha(json.dumps({'dependencies':dependencies,'sources':sources,'target':TARGET},sort_keys=True))
 preflight="""BEGIN;
SET LOCAL lock_timeout='500ms'; SET LOCAL statement_timeout='8s';
DO $$ BEGIN
 IF session_user<>'postgres' OR current_user<>'postgres'
    OR current_setting('transaction_isolation')<>'read committed'
    OR to_regclass('pg_temp.dashboard_forward_review') IS NULL
    OR to_regclass('pg_temp.dashboard_legacy_review') IS NULL THEN
  RAISE EXCEPTION 'independent_complete_forward_review_required';
 END IF;
END $$;
LOCK TABLE supabase_migrations.schema_migrations IN SHARE MODE;
LOCK TABLE public.vn_colonies,public.vn_fitness_snapshots,public.vn_generation_stats,
 public.vn_probes,public.vn_trades IN ACCESS EXCLUSIVE MODE;
DO $$ DECLARE expected jsonb; legacy_review jsonb; BEGIN
 SELECT review INTO STRICT expected FROM pg_temp.dashboard_forward_review;
 IF expected IS DISTINCT FROM jsonb_build_object('version',1,'target','-- TARGET'::jsonb,
   'release_sha256','-- RELEASE_ID','migration_catalog',pg_temp.vn_forward_migrations())
    OR to_regnamespace('vn_release') IS NOT NULL OR to_regnamespace('vn_access') IS NOT NULL
    OR to_regnamespace('vn_legacy') IS NOT NULL OR to_regnamespace('vn_legacy_evidence') IS NOT NULL THEN
  RAISE EXCEPTION 'forward_review_changed_or_target_mismatch' USING ERRCODE='55000';
 END IF;
 SELECT review INTO STRICT legacy_review FROM pg_temp.dashboard_legacy_review;
 PERFORM set_config('dashboard.forward_review',jsonb_build_object('forward',expected,
   'legacy_catalog_sha256',encode(sha256(convert_to(legacy_review::text,'UTF8')),'hex'))::text,true);
END $$;
""".replace('-- TARGET',json.dumps(TARGET,sort_keys=True)).replace('-- RELEASE_ID',release_id)
 gate=(HERE/'admission.sql').read_text().replace('-- RELEASE_ID',release_id)
 sql=preflight+inner(native_sql)+'\n'+inner(evidence.retirement())+'\n'+inner(evidence_sql)+'\n'+gate
 guards=[];replacements=[]
 for name,m in final_functions(native_sql).items():
  if name not in {'vn_durability.create_run','vn_durability.heartbeat','vn_durability.commit_command'}: continue
  call='PERFORM vn_release.require_open();'
  body=v5.once(m[3],'BEGIN\n','BEGIN\n  '+call+'\n')
  count=len(re.findall(r'\bRETURN\s',body))
  body,n=re.subn(r'^(\s*)RETURN\s',lambda x:x[1]+call+'\n'+x[1]+'RETURN ',body,flags=re.M)
  if n!=count or n<1:raise ValueError('Unreviewed release return grammar')
  ddl=v5.once(m[0],m[3],body)
  replacements.append(ddl);guards.append(name)
 if len(guards)!=3:raise ValueError('Release guard inventory changed')
 sql+='\nSET LOCAL ROLE vn_contract_owner;\n'+(HERE/'catalog.sql').read_text()+'\n'+\
  'REVOKE ALL ON FUNCTION vn_release.catalog() FROM PUBLIC,anon,authenticated,service_role,authenticator,vn_economic,vn_relay,vn_legacy_attestor;\n'+\
  '\n'.join(replacements)+'\nUPDATE vn_release.state SET install_catalog=vn_release.catalog() WHERE singleton;\nRESET ROLE;\n'
 functions=final_functions(sql)
 policies={m['name']:m['execute_role'] for m in json.loads((ROOT/'v5/manifest.json').read_text())['functions']}
 for name in ('vn_identity.lock_legacy_evidence','vn_identity.legacy_rows'):policies[name]='vn_contract_owner'
 policies['vn_legacy.classify_run']='authenticated'
 for sig in evidence_manifest['authenticated']:policies[sig.split('(')[0]]='authenticated'
 for sig in evidence_manifest['attestor']:policies[sig.split('(')[0]]='vn_legacy_attestor'
 metadata=[{'signature':v5.signature(m),'body_sha256':sha(m[3]),'ddl_sha256':sha(m[0]),
   'owner':'postgres' if name.startswith('vn_identity.') or name=='vn_legacy.classify_run' else 'vn_contract_owner',
   'execute_role':policies.get(name),'security_definer':'SECURITY DEFINER' in m[0].split('AS $$')[0]}
   for name,m in sorted(functions.items())]
 expected=',\n'.join("('%s','%s','%s',%s,%s)"%(m['signature'],m['body_sha256'],m['owner'],
  "'"+m['execute_role']+"'" if m['execute_role'] else 'NULL',str(m['security_definer']).lower()) for m in metadata)
 post='''SET LOCAL ROLE vn_contract_owner;
DO $$ DECLARE item record; api record; legacy_expected jsonb; BEGIN
 FOR item IN SELECT * FROM (VALUES
-- FINAL_BODIES
) expected(signature,body_sha256,owner_role,execute_role,security_definer) LOOP
  IF to_regprocedure(item.signature) IS NULL OR
    (SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid=to_regprocedure(item.signature))
      IS DISTINCT FROM item.body_sha256 OR
    NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=to_regprocedure(item.signature)
      AND p.proowner=item.owner_role::regrole AND p.prosecdef=item.security_definer AND NOT p.proleakproof) OR
    EXISTS(SELECT 1 FROM pg_proc p,LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
      WHERE p.oid=to_regprocedure(item.signature) AND (a.is_grantable OR
       a.grantee NOT IN (p.proowner,coalesce(to_regrole(item.execute_role),p.proowner)))) THEN
   RAISE EXCEPTION 'complete_forward_body_changed';
  END IF;
  FOR api IN SELECT oid,rolname FROM pg_roles WHERE rolname IN
   ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay','vn_legacy_attestor') LOOP
   IF has_function_privilege(api.oid,to_regprocedure(item.signature),'EXECUTE') IS DISTINCT FROM
      coalesce(api.rolname=item.execute_role,false) OR
      has_function_privilege(api.oid,to_regprocedure(item.signature),'EXECUTE WITH GRANT OPTION') THEN
    RAISE EXCEPTION 'complete_forward_function_authority_changed';
   END IF;
  END LOOP;
 END LOOP;
 IF (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname IN ('vn_identity','vn_access','vn_durability','vn_projection','vn_read','vn_legacy','vn_legacy_evidence','vn_release'))<>-- FUNCTION_COUNT THEN
  RAISE EXCEPTION 'unexpected_complete_forward_function';
 END IF;
 IF (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE n.nspname IN ('vn_access','vn_durability','vn_projection','vn_legacy_evidence','vn_release') AND c.relkind='r')<>26
    OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_access','vn_durability','vn_projection','vn_legacy_evidence','vn_release') AND
      (c.relkind NOT IN ('r','i') OR c.relowner<>'vn_contract_owner'::regrole OR
        (c.relkind='r' AND (c.relforcerowsecurity OR
          (n.nspname='vn_legacy_evidence' AND c.relrowsecurity) OR
          (n.nspname<>'vn_legacy_evidence' AND NOT c.relrowsecurity)))))
    OR EXISTS(SELECT 1 FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_access','vn_durability','vn_projection','vn_legacy_evidence','vn_release'))
    OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
      LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
      WHERE n.nspname IN ('vn_access','vn_durability','vn_projection','vn_legacy_evidence','vn_release') AND c.relkind='r'
      AND (a.grantee<>c.relowner OR a.is_grantable))
    OR EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('vn_access','vn_durability','vn_projection','vn_legacy_evidence','vn_release') AND a.attacl IS NOT NULL) THEN
  RAISE EXCEPTION 'complete_forward_raw_authority_changed';
 END IF;
 SELECT baseline INTO STRICT legacy_expected FROM vn_legacy_evidence.gate WHERE singleton;
 IF legacy_expected IS DISTINCT FROM vn_legacy_evidence.current_catalog() THEN
  RAISE EXCEPTION 'complete_forward_legacy_catalog_changed';
 END IF;
 IF (SELECT install_catalog FROM vn_release.state WHERE singleton) IS DISTINCT FROM vn_release.catalog() THEN
  RAISE EXCEPTION 'complete_forward_catalog_changed';
 END IF;
 IF (SELECT count(*) FROM pg_class WHERE relnamespace='vn_release'::regnamespace AND relkind='r')<>2
    OR EXISTS(SELECT 1 FROM pg_class c WHERE c.relnamespace='vn_release'::regnamespace
      AND (c.relowner<>'vn_contract_owner'::regrole OR (c.relkind='r' AND (NOT c.relrowsecurity OR c.relforcerowsecurity))))
    OR EXISTS(SELECT 1 FROM pg_policy WHERE polrelid IN ('vn_release.state'::regclass,'vn_release.operations'::regclass))
    OR EXISTS(SELECT 1 FROM pg_class c,LATERAL aclexplode(c.relacl) a WHERE c.relnamespace='vn_release'::regnamespace
      AND (a.grantee<>c.relowner OR a.is_grantable))
    OR EXISTS(SELECT 1 FROM pg_proc p,LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
      WHERE p.pronamespace='vn_release'::regnamespace AND
      (p.proowner<>'vn_contract_owner'::regrole OR a.grantee<>p.proowner OR a.is_grantable OR p.prosecdef
       OR p.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, vn_release, pg_temp'])) THEN
  RAISE EXCEPTION 'release_private_authority_postcondition_failed';
 END IF;
 FOR api IN SELECT oid FROM pg_roles WHERE rolname IN
   ('anon','authenticated','service_role','authenticator','vn_economic','vn_relay','vn_legacy_attestor') LOOP
  IF has_schema_privilege(api.oid,'vn_release','USAGE,CREATE') OR
    has_table_privilege(api.oid,'vn_release.state','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR
    has_table_privilege(api.oid,'vn_release.operations','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR
    has_any_column_privilege(api.oid,'vn_release.state','SELECT,INSERT,UPDATE,REFERENCES') OR
    has_any_column_privilege(api.oid,'vn_release.operations','SELECT,INSERT,UPDATE,REFERENCES') OR
    has_function_privilege(api.oid,'vn_release.require_open()','EXECUTE') OR
    has_function_privilege(api.oid,'vn_release.transition(uuid,bigint,text,text)','EXECUTE') THEN
   RAISE EXCEPTION 'release_api_authority_postcondition_failed';
  END IF;
 END LOOP;
END $$;
RESET ROLE;
'''.replace('-- FINAL_BODIES',expected).replace('-- FUNCTION_COUNT',str(len(functions)))
 sql+=post+'COMMIT;\n'
 manifest={'version':1,'milestone':'DB-03A2D3B2D2','mode':'complete_forward_offline_candidate',
  'production_application_available':False,'credentials_provisioned':False,'installed_admission':'closed',
  'target':TARGET,'release_sha256':release_id,'package_sha256':sha(sql),'dependencies_sha256':dependencies,
  'sources_sha256':sources,'release_guarded_functions':sorted(guards),
  'functions':metadata,
  'tables':re.findall(r'^CREATE TABLE (vn_\w+\.\w+)',sql,re.M),
  'object_ddl':[{'name':m[1],'kind':'table','ddl':m[0],'ddl_sha256':sha(m[0])}
     for m in re.finditer(r'^CREATE TABLE (vn_\w+\.\w+) \([\s\S]*?^\);',sql,re.M)]+
    [{'name':m[2],'kind':m[1].lower(),'ddl':m[0],'ddl_sha256':sha(m[0])}
     for m in re.finditer(r'^CREATE (?:UNIQUE )?(INDEX|TRIGGER|DOMAIN) (\w+(?:\.\w+)?)[\s\S]*?;',sql,re.M)],
  'postcommit_sha256':sha('BEGIN READ ONLY;\nSET LOCAL lock_timeout=\'500ms\'; SET LOCAL statement_timeout=\'8s\';\n'+post+'COMMIT;\n'),
  'rollback':'vn_release.transition(original_request_id,current_epoch,retired,evidence_sha256)',
  'retained_authority':['get_command','interrupt_expired','read_outbox','acknowledge_event','accept_event','owner_reads','archive'],
  'open_gates':['service_browser_integration','selected_host_managed_acceptance','DB03A3_reviewed_migration']}
 return sql,manifest

def postcommit(sql):
 anchor='SET LOCAL ROLE vn_contract_owner;\nDO $$ DECLARE item record; api record; legacy_expected jsonb; BEGIN\n'
 if sql.count(anchor)!=1:raise ValueError('Postcommit oracle anchor changed')
 return "BEGIN READ ONLY;\nSET LOCAL lock_timeout='500ms'; SET LOCAL statement_timeout='8s';\n"+sql[sql.index(anchor):]

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
 sql,manifest=build()
 for name,value in {'package.sql':sql,'manifest.json':json.dumps(manifest,indent=2,sort_keys=True)+'\n','verify.sql':postcommit(sql)}.items():
  if args.check:
   if (HERE/name).read_text()!=value:raise SystemExit('Forward artifact differs: '+name)
  else:(HERE/name).write_text(value)
 print(json.dumps({'check':args.check,'functions':len(manifest['functions']),'tables':len(manifest['tables']),
  'release_sha256':manifest['release_sha256'],'package_sha256':manifest['package_sha256']}))

if __name__=='__main__':main()
