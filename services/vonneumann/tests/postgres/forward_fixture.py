"""Complete cutover on an owned synthetic TLS/SCRAM database only."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
from uuid import uuid4
from tests.postgres import installer_fixture,legacy_fixture,canonical_fixture,native_issuer_fixture

HERE=Path(__file__).resolve().parents[2]/'db-contract/forward'
spec=importlib.util.spec_from_file_location('complete_forward_builder',HERE/'build.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
ADMIN=installer_fixture.ADMIN
BOUND="BEGIN; SET LOCAL lock_timeout='500ms'; SET LOCAL statement_timeout='8s'; SET LOCAL ROLE vn_contract_owner;\n"

def start(test_class):
 db=native_issuer_fixture.LimitedIssuerPostgres();test_class.addClassCleanup(db.close);db.start()
 db.sql('CREATE ROLE vn_test_admin LOGIN SUPERUSER;')
 db.sql(installer_fixture.HOSTED_BOOTSTRAP,role=ADMIN)
 bootstrap=legacy_fixture.legacy_bootstrap().replace(
  'CREATE ROLE authenticator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;','')
 db.sql(bootstrap+'\nGRANT USAGE ON SCHEMA extensions TO postgres;',role=ADMIN)
 db.sql(legacy_fixture.captured_legacy_schema())
 versions=json.loads(legacy_fixture.SNAPSHOT.read_text())['inventory']['migration_versions']
 db.sql('CREATE SCHEMA supabase_migrations AUTHORIZATION postgres; '
  'CREATE TABLE supabase_migrations.schema_migrations(version text PRIMARY KEY,name text,statements text[]); '
  'INSERT INTO supabase_migrations.schema_migrations VALUES '+','.join(
   "('%s','synthetic fixture only',ARRAY['SELECT 1;'])"%v for v in versions)+';')
 return db

def reset(db):
 # Trusted observation/fault reset in this owned fixture only, never a runner.
 db.sql('''DROP SCHEMA IF EXISTS vn_release,vn_legacy_evidence,vn_legacy,vn_access,vn_read,vn_projection,vn_durability,vn_identity CASCADE;
DO $$ DECLARE r record; BEGIN FOR r IN SELECT rolname FROM pg_roles WHERE rolname LIKE 'vn_native_%' LOOP
 EXECUTE format('DROP ROLE %I',r.rolname); END LOOP; END $$;
DROP ROLE IF EXISTS vn_test_legacy_reviewer,vn_legacy_attestor,vn_economic,vn_relay;
DO $$ BEGIN IF to_regrole('vn_contract_owner') IS NOT NULL THEN
 DROP OWNED BY vn_contract_owner; DROP ROLE vn_contract_owner; END IF; END $$;
DROP TABLE '''+', '.join('public.'+t for t in legacy_fixture.TABLES)+''' CASCADE;
TRUNCATE auth.users CASCADE;
''',role=ADMIN)
 db.sql(legacy_fixture.captured_legacy_schema())
 return legacy_fixture.seed_legacy_rows(canonical_fixture.CapabilityDatabase(db))

def package():
 sql,manifest=builder.build()
 if sql!=(HERE/'package.sql').read_text() or manifest!=json.loads((HERE/'manifest.json').read_text()):
  raise ValueError('Complete forward artifact differs')
 return sql,manifest

def review(db):
 # Each expectation is observed in a separate completed, read-only session.
 sql,manifest=package()
 migrations=json.loads(db.scalar((HERE/'review.sql').read_text()+'SELECT pg_temp.vn_forward_migrations();'))
 expected={'version':1,'target':builder.TARGET,'release_sha256':manifest['release_sha256'],'migration_catalog':migrations}
 return legacy_fixture.review_sql(db)+(HERE/'review.sql').read_text()+\
  '\nINSERT INTO pg_temp.dashboard_forward_review VALUES('+legacy_fixture.literal(json.dumps(expected))+'::jsonb);\n'

def install(db,reviewed=None,suffix='',check=True):
 sql,_=package()
 if suffix:sql=sql.removesuffix('COMMIT;\n')+suffix+'\nCOMMIT;\n'
 return db.sql((review(db) if reviewed is None else reviewed)+sql,timeout=30,check=check)

def transition(db,target,epoch=0,request=None,evidence='7'*64,check=True):
 source=BOUND+'SELECT vn_release.transition('+','.join((legacy_fixture.literal(request or str(uuid4())),
  str(epoch),legacy_fixture.literal(target),legacy_fixture.literal(evidence)))+'); COMMIT;'
 result=db.sql(source,check=check,timeout=12)
 return json.loads(result.stdout) if check else result
