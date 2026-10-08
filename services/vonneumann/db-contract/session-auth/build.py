"""Offline native-auth composition; never reads credentials or connects to a DB."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
BASE_SHA='738d95e37d56e2ef8e445bf4bd57414d0019dbb48f6d75e3e810580f6c15c183'
spec=importlib.util.spec_from_file_location('session_auth_v5_dependency',HERE.parent/'v5'/'build.py')
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def build():
    source, base_manifest=base.build()
    if base.sha(source)!=BASE_SHA or (HERE.parent/'v5'/'package.sql').read_text()!=source:
        raise ValueError('Reviewed v5 dependency changed')
    access=(HERE/'access.sql').read_text()
    guards=[]
    replacements=[]
    for name,match in base.functions(source).items():
        operation=name.split('.')[1]
        if operation not in base.ECONOMIC|base.RELAY:
            continue
        capability='economic' if operation in base.ECONOMIC else 'relay'
        call=f"PERFORM vn_access.require_actor(owner_id,run,'{capability}','{operation}');"
        body=base.once(match[3],'BEGIN\n','BEGIN\n  '+call+'\n')
        # Specific to the pinned PL/pgSQL grammar. Never match RETURNING or
        # inline nested SQL. Fail closed if any return escapes line admission.
        returns=len(re.findall(r'\bRETURN\s',body))
        body,count=re.subn(r'^(\s*)RETURN\s',lambda m:m[1]+call+'\n'+m[1]+'RETURN ',body,flags=re.M)
        if count!=returns or count<1:
            raise ValueError('Unreviewed return grammar: '+name)
        ddl=base.once(match[0],match[3],body).replace('CREATE FUNCTION ','CREATE OR REPLACE FUNCTION ',1)
        replacements.append(ddl)
        guards.append({'name':name,'signature':base.signature(match),'capability':capability,
                       'body_sha256':base.sha(body),'successful_returns':count})
    if len(guards)!=8:
        raise ValueError('Capability inventory changed')
    sql=base.once(source,'COMMIT;\n','')+'\n'+access+'\nSET LOCAL ROLE vn_contract_owner;\n'+'\n\n'.join(replacements)+'\nRESET ROLE;\n'
    # Check the new bodies/ownership/ACL after replacing entrypoints. The base
    # package already checked unchanged functions, tables and API capabilities.
    expected=',\n'.join("('%s','%s')"%(g['signature'],g['body_sha256']) for g in guards)
    helpers=base.functions(access)
    expected+=',\n'+',\n'.join("('%s','%s')"%(base.signature(m),base.sha(m[3])) for m in helpers.values())
    post=(HERE/'postconditions.sql').read_text()
    sql+=base.once(post,'-- EXPECTED_BODIES',expected)+'\nCOMMIT;\n'
    manifest={'mode':'native_direct_session_auth_offline_candidate','production_application_available':False,
              'base_package_sha256':BASE_SHA,'access_sha256':base.sha(access),
              'postconditions_sha256':base.sha(post),'package_sha256':base.sha(sql),
              'guarded_functions':guards,'unchanged_base_functions':len(base_manifest['functions'])-8,
              'provisioned_credentials':False,'supported_connection_profiles':['direct_tls_scram'],
              'maximum_write_lifetime_seconds':7200,'maximum_recovery_lifetime_seconds':86400}
    return sql,manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    sql,manifest=build()
    for name,body in {'package.sql':sql,'manifest.json':json.dumps(manifest,indent=2,sort_keys=True)+'\n'}.items():
        if args.check:
            if (HERE/name).read_text()!=body:
                raise SystemExit('Native-auth artifact differs: '+name)
        else:
            (HERE/name).write_text(body)
    print(json.dumps({'check':args.check,'guarded_functions':len(manifest['guarded_functions']),
                      'package_sha256':manifest['package_sha256']}))


if __name__=='__main__':
    main()
