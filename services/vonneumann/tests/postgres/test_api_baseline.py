"""Opt-in, owned PostgreSQL/PostgREST proof of the two public API tables.

This fixture has no worker schema/bootstrap, hosted connection or real JWT/key.
It reuses the existing local-daemon/image/ownership/cleanup primitives, while
keeping its public-schema exposure and NOLOGIN role bootstrap private here.
Do not infer a hosted Supabase gateway or migration receipt from these tests.
"""
from __future__ import annotations

import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import time
import unittest
from uuid import UUID

import httpx

from tests.postgres.harness import IMAGE, LABEL, OPT_IN
from tests.postgres.http_harness import (
    FAKE_JWT_SECRET, POSTGREST_IMAGE, IsolatedPostgREST, fixture_jwt,
)


ROOT = Path(__file__).resolve().parents[4]
TABLES = ('market_sentiment', 'test_events')
COLUMNS = {
    'market_sentiment': ('id', 'score', 'sentiment', 'summary', 'key_factors', 'date', 'source', 'created_at'),
    'test_events': ('id', 'payload', 'source', 'created_at'),
}
ROLES = ('anon', 'authenticated', 'service_role')
TABLE_PRIVILEGES = ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                    'REFERENCES', 'TRIGGER', 'MAINTAIN')
COLUMN_PRIVILEGES = ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES')
REFUSAL = 'dashboard_api_baseline_refused'
FIXTURE_ADMIN = 'dashboard_api_fixture_admin'
BOOTSTRAP = '''
ALTER ROLE dashboard_api_fixture_admin NOINHERIT;
CREATE ROLE postgres LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS;
ALTER DATABASE postgres OWNER TO postgres;
ALTER SCHEMA public OWNER TO postgres;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE ROLE anon NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS;
CREATE ROLE authenticated NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS;
CREATE ROLE service_role NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT BYPASSRLS;
CREATE ROLE authenticator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT anon, authenticated, service_role TO authenticator;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated, service_role;
CREATE SCHEMA dashboard_api_fixture AUTHORIZATION postgres;
GRANT USAGE ON SCHEMA dashboard_api_fixture TO anon, authenticated, service_role;
CREATE TABLE dashboard_api_fixture.sentinel (id integer PRIMARY KEY, body text NOT NULL);
ALTER TABLE dashboard_api_fixture.sentinel OWNER TO postgres;
INSERT INTO dashboard_api_fixture.sentinel VALUES (1, 'unrelated-owned-fixture');
GRANT SELECT ON dashboard_api_fixture.sentinel TO authenticated;
CREATE FUNCTION dashboard_api_fixture.noop_trigger() RETURNS trigger
  LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;
ALTER FUNCTION dashboard_api_fixture.noop_trigger() OWNER TO postgres;
GRANT EXECUTE ON FUNCTION dashboard_api_fixture.noop_trigger() TO anon, authenticated, service_role;
'''


def literal(value):
    """Quote only fixed/synthetic fixture values, never application inputs."""
    return "'" + str(value).replace("'", "''") + "'"


def baseline_module():
    path = ROOT / 'scripts/dashboard_api_baseline.py'
    if path.is_symlink() or not path.is_file():
        raise RuntimeError('Reviewed regular API baseline helper is required')
    spec = importlib.util.spec_from_file_location('dashboard_api_baseline_fixture', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('API baseline helper cannot be loaded')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class APIBaselineFixture(IsolatedPostgREST):
    """A separate public-only bootstrap, not a widened worker HTTP fixture."""

    api_schemas = ('public',)

    def start(self):
        if self._container_id is not None or self._network_id is not None:
            raise RuntimeError('API baseline fixture is already running')
        self._pin_local_daemon()
        image_id, http_image_id = self._image(IMAGE), self._image(POSTGREST_IMAGE)
        try:
            self._network_id = self._command([
                'network', 'create', '--opt',
                'com.docker.network.bridge.enable_ip_masquerade=false',
                '--label', f'{LABEL}={self._token}', self.network,
            ]).stdout.strip()
            network = self._verify_network()
            subnet = ipaddress.ip_network(network['IPAM']['Config'][0]['Subnet'])
            if subnet.version != 4 or not subnet.is_private:
                raise RuntimeError('API fixture requires a private IPv4 bridge')
            script = (
                'set -eu; mkdir -p /tmp/dashboard-pg/data; '
                'initdb -D /tmp/dashboard-pg/data --auth-local=trust --auth-host=reject '
                '--username=dashboard_api_fixture_admin --encoding=UTF8 --no-locale >/tmp/dashboard-initdb.log; '
                f"echo 'host postgres authenticator {subnet} trust' >>/tmp/dashboard-pg/data/pg_hba.conf; "
                'exec postgres -D /tmp/dashboard-pg/data -k /tmp '
                "-c listen_addresses='*' -c max_connections=30 "
                '-c shared_buffers=32MB -c log_statement=none'
            )
            self._container_id = self._command([
                'run', '--detach', '--pull=never', '--name', self.name,
                '--label', f'{LABEL}={self._token}', '--network', self.network,
                '--network-alias', 'fixture-db', '--read-only', '--user', 'postgres',
                '--cap-drop=ALL', '--security-opt', 'no-new-privileges',
                '--pids-limit', '128', '--memory', '512m', '--cpus', '1',
                '--tmpfs', '/tmp:rw,nosuid,nodev,size=268435456,mode=1777',
                '--entrypoint', '/bin/sh', image_id, '-c', script,
            ], timeout=20).stdout.strip()
            if not re.fullmatch(r'[a-f0-9]{64}', self._container_id):
                raise RuntimeError('API fixture requires an exact owned container ID')
            self._verify_container(self._container_id, postgres=True)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                result = self._command([
                    'exec', self._container_id, 'pg_isready', '-h', '/tmp',
                    '-U', FIXTURE_ADMIN, '-d', 'postgres',
                ], timeout=3, check=False)
                if result.returncode == 0:
                    break
                time.sleep(.1)
            else:
                raise TimeoutError('Owned API PostgreSQL readiness timed out')
            # OID10 must remain a superuser. Give initdb the private admin name,
            # then create a separate non-superuser postgres with only explicitly
            # owned database/schema rights; never reassign system objects.
            self.sql(BOOTSTRAP, role=FIXTURE_ADMIN)
            self.identity = {
                'postgres_image': image_id, 'postgrest_image': http_image_id,
                'postgres_version': self.scalar('SHOW server_version;'),
                'network': 'owned-bridge-no-masquerade', 'api_schema': 'public',
            }
            return self
        except BaseException:
            self.close()
            raise

    def start_http(self):
        """Expose exactly public on a newly owned loopback HTTP port."""
        self.stop_http()
        self._verify_network()
        self._http_id = self._command([
            'run', '--detach', '--pull=never', '--name', self.http_name,
            '--label', f'{LABEL}={self._token}', '--network', self.network,
            '--read-only', '--user', '1000:1000', '--cap-drop=ALL',
            '--security-opt', 'no-new-privileges', '--pids-limit', '128',
            '--memory', '256m', '--cpus', '1', '--publish', '127.0.0.1::3000',
            '--env', 'PGRST_DB_URI=postgres://authenticator@fixture-db:5432/postgres',
            '--env', 'PGRST_DB_SCHEMAS=public', '--env', 'PGRST_DB_ANON_ROLE=anon',
            '--env', f'PGRST_JWT_SECRET={FAKE_JWT_SECRET}',
            '--env', 'PGRST_JWT_AUD=dashboard-fixture', '--env', 'PGRST_DB_TX_END=commit',
            '--env', 'PGRST_DB_POOL=2', '--env', 'PGRST_LOG_LEVEL=error',
            self.identity['postgrest_image'],
        ], timeout=20).stdout.strip()
        if not re.fullmatch(r'[a-f0-9]{64}', self._http_id):
            raise RuntimeError('API fixture requires an exact owned HTTP container ID')
        state = self._verify_container(self._http_id)
        bindings = state['NetworkSettings']['Ports'].get('3000/tcp')
        if (not bindings or len(bindings) != 1 or bindings[0]['HostIp'] != '127.0.0.1'
                or not bindings[0]['HostPort'].isdigit()):
            raise RuntimeError('API fixture HTTP must use one loopback binding')
        self.endpoint = 'http://127.0.0.1:' + bindings[0]['HostPort']
        self.identity['postgrest_version'] = self._command([
            'exec', self._http_id, '/bin/postgrest', '--version',
        ]).stdout.strip()
        deadline = time.monotonic() + 15
        with httpx.Client(trust_env=False, timeout=1, follow_redirects=False) as client:
            while time.monotonic() < deadline:
                try:
                    response = client.get(self.endpoint + '/', headers={
                        'Authorization': 'Bearer ' + fixture_jwt('service_role'),
                    })
                    if response.status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
        self._verify_container(self._http_id)
        raise TimeoutError('Owned API PostgREST readiness timed out')


@unittest.skipUnless(os.environ.get(OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class APIBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = baseline_module()
        cls.db = APIBaselineFixture()
        cls.addClassCleanup(cls.db.close)
        cls.db.start()

    def setUp(self):
        self.db.stop_http()
        self.db.sql('DROP TABLE IF EXISTS public.market_sentiment, public.test_events CASCADE;')

    def apply(self, *, acl=False, check=True):
        return self.db.sql(self.baseline.baseline_sql(apply_acl=acl), timeout=15, check=check)

    def construct(self):
        self.db.sql(self.baseline.constructor_sql(), timeout=15)

    def catalog(self):
        return json.loads(self.db.scalar(self.baseline.catalog_sql(), timeout=15))

    def exists(self, table):
        self.assertIn(table, TABLES)
        return self.db.scalar('SELECT pg_catalog.to_regclass(' + literal('public.' + table)
                              + ') IS NOT NULL;') == 't'

    def actor(self, role, source, *, check=True):
        self.assertIn(role, ROLES)
        # API roles really are NOLOGIN; exercise authenticator membership and
        # PostgreSQL's role switch rather than grant them fixture login access.
        return self.db.sql('BEGIN; SET LOCAL ROLE ' + role + ';' + source + 'COMMIT;',
                           role='authenticator', timeout=15, check=check)

    def fixture_admin(self, source):
        """Only deliberate drift setup/cleanup; never baseline or actor proof."""
        return self.db.sql(source, role=FIXTURE_ADMIN, timeout=15)

    def surrounding(self):
        """Independent before/after proof outside the two-table ACL delta."""
        return json.loads(self.db.scalar('''SELECT jsonb_build_object(
          'roles',(SELECT jsonb_agg(to_jsonb(r) ORDER BY rolname) FROM
            (SELECT rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,rolbypassrls
             FROM pg_catalog.pg_roles WHERE rolname IN ('postgres','anon','authenticated','service_role','authenticator')) r),
          'memberships',(SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY roleid,member),'[]'::jsonb)
            FROM pg_catalog.pg_auth_members m),
          'defaults',(SELECT coalesce(jsonb_agg(to_jsonb(d) ORDER BY oid),'[]'::jsonb)
            FROM pg_catalog.pg_default_acl d),
          'schemas',(SELECT jsonb_agg(to_jsonb(n) ORDER BY oid) FROM
            (SELECT oid,nspname,nspowner,nspacl FROM pg_catalog.pg_namespace
             WHERE nspname IN ('public','dashboard_api_fixture')) n),
          'sentinel',(SELECT jsonb_agg(to_jsonb(s) ORDER BY id) FROM dashboard_api_fixture.sentinel s),
          'sentinel_catalog',(SELECT to_jsonb(c) FROM pg_catalog.pg_class c
             WHERE oid='dashboard_api_fixture.sentinel'::pg_catalog.regclass),
          'sentinel_columns',(SELECT jsonb_agg(to_jsonb(a) ORDER BY attnum)
             FROM pg_catalog.pg_attribute a WHERE attrelid='dashboard_api_fixture.sentinel'::pg_catalog.regclass));'''))

    def table_snapshot(self, table):
        self.assertIn(table, TABLES)
        if not self.exists(table):
            return None
        name = literal('public.' + table)
        return json.loads(self.db.scalar('''SELECT jsonb_build_object(
          'relation',(SELECT to_jsonb(c)||jsonb_build_object('tuple_xmin',c.xmin::text)
            FROM pg_catalog.pg_class c WHERE oid=''' + name + '''::pg_catalog.regclass),
          'columns',(SELECT jsonb_agg(to_jsonb(a)||jsonb_build_object('tuple_xmin',a.xmin::text) ORDER BY attnum) FROM pg_catalog.pg_attribute a
            WHERE attrelid=''' + name + '''::pg_catalog.regclass),
          'defaults',(SELECT coalesce(jsonb_agg(to_jsonb(d)||jsonb_build_object('tuple_xmin',d.xmin::text) ORDER BY oid),'[]'::jsonb)
            FROM pg_catalog.pg_attrdef d WHERE adrelid=''' + name + '''::pg_catalog.regclass),
          'constraints',(SELECT coalesce(jsonb_agg(to_jsonb(c)||jsonb_build_object('tuple_xmin',c.xmin::text) ORDER BY oid),'[]'::jsonb)
            FROM pg_catalog.pg_constraint c WHERE conrelid=''' + name + '''::pg_catalog.regclass),
          'indexes',(SELECT coalesce(jsonb_agg(to_jsonb(i)||jsonb_build_object('tuple_xmin',i.xmin::text) ORDER BY indexrelid),'[]'::jsonb)
            FROM pg_catalog.pg_index i WHERE indrelid=''' + name + '''::pg_catalog.regclass),
          'row_identity',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'ctid',t.ctid::text,'xmin',t.xmin::text) ORDER BY id),'[]'::jsonb)
            FROM public.''' + table + ''' t),
          'rows',(SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id),'[]'::jsonb) FROM public.''' + table + ''' t));'''))

    def seed(self):
        self.db.sql('''INSERT INTO public.test_events(id,payload,source,created_at)
          VALUES ('00000000-0000-0000-0000-000000000001','{"fixture":"retained"}',NULL,NULL);
          INSERT INTO public.market_sentiment(id,score,sentiment,summary,key_factors,date,source,created_at)
          VALUES ('00000000-0000-0000-0000-000000000002',50,'neutral','retained','[]','2024-02-29',NULL,NULL);''')

    def assert_privileges(self):
        # One actual SQL inventory rather than hundreds of process launches.
        # Counts/keys are independently fixed here; missing columns cannot
        # silently shrink the permission matrix under test.
        matrix = json.loads(self.db.scalar('''WITH roles(name) AS
          (VALUES ('anon'),('authenticated'),('service_role')),
          targets(name) AS (VALUES ('market_sentiment'),('test_events')),
          table_privileges(name) AS (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),
            ('TRUNCATE'),('REFERENCES'),('TRIGGER'),('MAINTAIN')),
          column_privileges(name) AS (VALUES ('SELECT'),('INSERT'),('UPDATE'),('REFERENCES'))
          SELECT jsonb_build_object(
            'tables',(SELECT jsonb_agg(jsonb_build_object('table',t.name,'role',r.name,
              'privilege',p.name,'allowed',pg_catalog.has_table_privilege(r.name,'public.'||t.name,p.name))
              ORDER BY t.name,r.name,p.name) FROM targets t CROSS JOIN roles r CROSS JOIN table_privileges p),
            'columns',(SELECT jsonb_agg(jsonb_build_object('table',t.name,'role',r.name,
              'column',a.attname,'privilege',p.name,'allowed',
              pg_catalog.has_column_privilege(r.name,'public.'||t.name,a.attname,p.name))
              ORDER BY t.name,r.name,a.attnum,p.name) FROM targets t CROSS JOIN roles r
              CROSS JOIN column_privileges p JOIN pg_catalog.pg_attribute a
              ON a.attrelid=pg_catalog.to_regclass('public.'||t.name) AND a.attnum>0 AND NOT a.attisdropped));'''))
        expected_tables = {(table, role, privilege) for table in TABLES
                           for role in ROLES for privilege in TABLE_PRIVILEGES}
        expected_columns = {(table, role, column, privilege) for table in TABLES
                            for role in ROLES for column in COLUMNS[table]
                            for privilege in COLUMN_PRIVILEGES}
        self.assertEqual(len(matrix['tables']), len(expected_tables))
        self.assertEqual(len(matrix['columns']), len(expected_columns))
        self.assertEqual({(row['table'], row['role'], row['privilege']) for row in matrix['tables']}, expected_tables)
        self.assertEqual({(row['table'], row['role'], row['column'], row['privilege']) for row in matrix['columns']}, expected_columns)
        for row in matrix['tables'] + matrix['columns']:
            with self.subTest(**row):
                self.assertEqual(row['allowed'], row['role'] == 'service_role'
                                 and row['privilege'] in ('SELECT', 'INSERT'))

    def assert_sql_refuses(self, sql, *, code, role=None):
        result = self.db.sql(sql, check=False) if role is None else self.actor(role, sql, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(code, result.stderr)
        return result

    def test_fixture_has_only_reviewed_public_roles_and_no_worker_contract(self):
        data = self.surrounding()
        roles = {row['rolname']: row for row in data['roles']}
        self.assertFalse(roles['postgres']['rolsuper'])
        self.assertEqual(self.db.scalar('SELECT current_user::text||\'/\'||session_user::text;'), 'postgres/postgres')
        self.assertEqual(self.db.scalar('''SELECT
          (SELECT oid=10 AND rolsuper FROM pg_catalog.pg_roles WHERE rolname='dashboard_api_fixture_admin')
          AND (SELECT oid<>10 AND NOT rolsuper FROM pg_catalog.pg_roles WHERE rolname='postgres');'''), 't')
        self.assertEqual(self.db.scalar('''SELECT count(*) FROM pg_catalog.pg_auth_members
          WHERE roleid=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='dashboard_api_fixture_admin')
             OR member=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='dashboard_api_fixture_admin');'''), '0')
        for role in ROLES:
            self.assertFalse(roles[role]['rolcanlogin'])
            self.assertFalse(roles[role]['rolsuper'])
            self.assertFalse(roles[role]['rolcreaterole'])
            self.assertFalse(roles[role]['rolcreatedb'])
            self.assertTrue(roles[role]['rolinherit'])
            self.assertEqual(roles[role]['rolbypassrls'], role == 'service_role')
        self.assertTrue(roles['authenticator']['rolcanlogin'])
        self.assertFalse(roles['authenticator']['rolinherit'])
        memberships = json.loads(self.db.scalar('''SELECT jsonb_agg(jsonb_build_object(
          'role',r.rolname,'member',m.rolname,'admin',a.admin_option,
          'inherit',a.inherit_option,'set',a.set_option) ORDER BY r.rolname,m.rolname)
          FROM pg_catalog.pg_auth_members a JOIN pg_catalog.pg_roles r ON r.oid=a.roleid
          JOIN pg_catalog.pg_roles m ON m.oid=a.member
          WHERE r.rolname IN ('anon','authenticated','service_role','authenticator')
             OR m.rolname IN ('anon','authenticated','service_role','authenticator');'''))
        self.assertEqual(memberships, [{'role': role, 'member': 'authenticator',
            'admin': False, 'inherit': False, 'set': True} for role in sorted(ROLES)])
        self.assertEqual(self.db.scalar("SELECT pg_catalog.to_regnamespace('vn_durability') IS NULL;"), 't')
        self.assertEqual(self.db.scalar("SELECT pg_catalog.to_regnamespace('auth') IS NULL;"), 't')
        for role in ROLES:
            self.assertEqual(self.db.scalar('SELECT pg_catalog.has_schema_privilege('
                + ','.join(map(literal, (role, 'public', 'USAGE'))) + ');'), 't')
            self.assertEqual(self.db.scalar('SELECT pg_catalog.has_schema_privilege('
                + ','.join(map(literal, (role, 'public', 'CREATE'))) + ');'), 'f')

    def test_fresh_baseline_and_repeat_are_narrow_and_noop(self):
        before = self.surrounding()
        self.apply()
        self.assertTrue(all(self.exists(table) for table in TABLES))
        self.assertEqual(self.surrounding(), before)
        self.assert_privileges()
        self.seed()
        catalogs, snapshots = self.catalog(), {table: self.table_snapshot(table) for table in TABLES}
        self.apply()
        self.apply(acl=True)
        self.assertEqual(self.catalog(), catalogs)
        self.assertEqual({table: self.table_snapshot(table) for table in TABLES}, snapshots)
        self.assertEqual(self.surrounding(), before)

    def test_matching_broad_acl_baseline_is_noop_then_separate_acl_is_narrow(self):
        self.construct(); self.seed()
        self.db.sql('GRANT ALL ON public.market_sentiment, public.test_events TO anon, authenticated, service_role;')
        before, catalogs = self.surrounding(), self.catalog()
        snapshots = {table: self.table_snapshot(table) for table in TABLES}
        self.apply()
        self.assertEqual(self.catalog(), catalogs)
        self.assertEqual({table: self.table_snapshot(table) for table in TABLES}, snapshots)
        self.apply(acl=True)
        self.assert_privileges()
        for table in TABLES:
            after = self.table_snapshot(table)
            self.assertEqual(after['rows'], snapshots[table]['rows'])
            self.assertEqual(after['columns'], snapshots[table]['columns'])
            self.assertEqual(after['relation']['oid'], snapshots[table]['relation']['oid'])
            self.assertEqual(after['relation']['relowner'], snapshots[table]['relation']['relowner'])
        self.assertEqual(self.surrounding(), before)

    def test_either_matching_table_can_exist_without_rewriting_it(self):
        for keep in TABLES:
            with self.subTest(existing=keep):
                self.db.sql('DROP TABLE IF EXISTS public.market_sentiment, public.test_events CASCADE;')
                self.construct(); self.seed()
                missing = next(table for table in TABLES if table != keep)
                self.db.sql('DROP TABLE public.' + missing + ';')
                existing, before = self.table_snapshot(keep), self.surrounding()
                self.apply()
                self.assertEqual(self.table_snapshot(keep), existing)
                self.assertTrue(self.exists(missing))
                self.assertEqual(self.surrounding(), before)
                self.assert_privileges()

    def test_acl_only_refuses_missing_tables_without_creating_either(self):
        before = self.surrounding()
        result = self.apply(acl=True, check=False)
        self.assertNotEqual(result.returncode, 0); self.assertIn(REFUSAL, result.stderr)
        self.assertFalse(any(self.exists(table) for table in TABLES))
        self.assertEqual(self.surrounding(), before)

    def test_all_existing_shapes_are_checked_before_either_missing_creation(self):
        for present in TABLES:
            with self.subTest(drifted_existing=present):
                self.db.sql('DROP TABLE IF EXISTS public.market_sentiment, public.test_events CASCADE;')
                self.construct(); self.seed()
                missing = next(table for table in TABLES if table != present)
                self.db.sql('DROP TABLE public.' + missing + '; ALTER TABLE public.' + present + ' ADD COLUMN drift integer;')
                before, existing = self.surrounding(), self.table_snapshot(present)
                result = self.apply(check=False)
                self.assertNotEqual(result.returncode, 0); self.assertIn(REFUSAL, result.stderr)
                self.assertFalse(self.exists(missing))
                self.assertEqual(self.table_snapshot(present), existing)
                self.assertEqual(self.surrounding(), before)

    def test_atomic_late_failure_rolls_back_already_created_tables(self):
        source = self.baseline.baseline_sql(apply_acl=False)
        endings = list(re.finditer(r'(?m)^COMMIT;\s*$', source))
        self.assertEqual(len(endings), 1, 'Fixture injection requires one reviewed final COMMIT')
        end = endings[0].start()
        injected = source[:end] + '''DO $$ BEGIN
          IF pg_catalog.to_regclass('public.market_sentiment') IS NULL
             OR pg_catalog.to_regclass('public.test_events') IS NULL THEN
            RAISE EXCEPTION 'fixture_creation_not_reached';
          END IF;
          RAISE EXCEPTION 'fixture_after_both_creations';
        END $$;
        ''' + source[end:]
        before = self.surrounding()
        result = self.db.sql(injected, timeout=15, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fixture_after_both_creations', result.stderr)
        self.assertNotIn('fixture_creation_not_reached', result.stderr)
        self.assertFalse(any(self.exists(table) for table in TABLES))
        self.assertEqual(self.surrounding(), before)

    def test_failure_immediately_after_first_create_section_rolls_back_first_table(self):
        source = self.baseline.baseline_sql(apply_acl=False)
        marker = "EXECUTE 'GRANT SELECT, INSERT ON TABLE public.market_sentiment TO service_role';"
        self.assertEqual(source.count(marker), 1, 'Injection must bind the reviewed first CREATE section')
        failure = '''
          IF pg_catalog.to_regclass('public.market_sentiment') IS NULL
             OR pg_catalog.to_regclass('public.test_events') IS NOT NULL THEN
            RAISE EXCEPTION 'fixture_first_section_not_reached';
          END IF;
          RAISE EXCEPTION 'fixture_after_first_create_section';
        '''
        injected = source.replace(marker, marker + failure, 1)
        before = self.surrounding()
        result = self.db.sql(injected, timeout=15, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fixture_after_first_create_section', result.stderr)
        self.assertNotIn('fixture_first_section_not_reached', result.stderr)
        self.assertFalse(any(self.exists(table) for table in TABLES))
        self.assertEqual(self.surrounding(), before)

    def test_held_existing_table_lock_refuses_without_creating_missing_table(self):
        self.construct(); self.seed()
        self.db.sql('DROP TABLE public.market_sentiment;')
        before, existing = self.surrounding(), self.table_snapshot('test_events')
        holder = self.db.begin_sql('''BEGIN;
          SET LOCAL application_name='dashboard-api-baseline-held-lock';
          LOCK TABLE public.test_events IN ACCESS EXCLUSIVE MODE;
          SELECT pg_catalog.pg_sleep(8); ROLLBACK;''', timeout=15)
        try:
            self.db.wait_until('''SELECT EXISTS (
              SELECT 1 FROM pg_catalog.pg_locks l JOIN pg_catalog.pg_stat_activity a ON a.pid=l.pid
              WHERE l.relation='public.test_events'::pg_catalog.regclass
                AND l.mode='AccessExclusiveLock' AND l.granted
                AND a.application_name='dashboard-api-baseline-held-lock');''', timeout=5)
            started = time.monotonic()
            result = self.apply(check=False)
            elapsed = time.monotonic() - started
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('55P03', result.stderr)
            self.assertIn('lock timeout', result.stderr.lower())
            # The server's unchanged one-second lock_timeout causes the refusal;
            # this separate wall bound allows owned client/process overhead.
            self.assertLess(elapsed, 7)
            self.assertFalse(self.exists('market_sentiment'))
        finally:
            try:
                holder.wait(20)
            finally:
                holder.close()
        self.assertEqual(self.table_snapshot('test_events'), existing)
        self.assertEqual(self.surrounding(), before)

    def test_column_default_constraint_index_trigger_policy_and_dependency_drift_refuses(self):
        mutations = (
            'ALTER TABLE public.test_events ADD COLUMN unreviewed integer;',
            "ALTER TABLE public.test_events ALTER COLUMN source SET DEFAULT 'changed';",
            'ALTER TABLE public.test_events ALTER COLUMN payload DROP NOT NULL;',
            'ALTER TABLE public.market_sentiment DROP CONSTRAINT market_sentiment_score_check;'
            'ALTER TABLE public.market_sentiment ADD CONSTRAINT market_sentiment_score_check CHECK(score BETWEEN 0 AND 101);',
            'DROP INDEX public.idx_market_sentiment_date; CREATE INDEX idx_market_sentiment_date ON public.market_sentiment(date ASC);',
            'CREATE INDEX api_fixture_extra ON public.test_events(source);',
            'ALTER TABLE public.test_events OWNER TO authenticator;',
            'ALTER TABLE public.test_events DISABLE ROW LEVEL SECURITY;',
            'ALTER TABLE public.test_events FORCE ROW LEVEL SECURITY;',
            'CREATE TRIGGER api_fixture_drift BEFORE INSERT ON public.test_events '
            'FOR EACH ROW EXECUTE FUNCTION dashboard_api_fixture.noop_trigger();',
            'CREATE POLICY api_fixture_drift ON public.test_events FOR SELECT TO anon USING(true);',
            'CREATE VIEW dashboard_api_fixture.dependency AS SELECT id FROM public.test_events;',
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(drift=index):
                self.db.sql('DROP TABLE IF EXISTS public.market_sentiment, public.test_events CASCADE;')
                self.construct(); self.seed()
                if ' OWNER TO ' in mutation:
                    # Keep independent row snapshots readable after intentional
                    # owner drift; this does not confer baseline installation
                    # authority or alter the three API roles' privileges.
                    self.fixture_admin(mutation + 'GRANT SELECT ON public.test_events TO postgres;')
                else:
                    self.db.sql(mutation)
                try:
                    before, catalogs = self.surrounding(), self.catalog()
                    snapshots = {table: self.table_snapshot(table) for table in TABLES}
                    for acl in (False, True):
                        result = self.apply(acl=acl, check=False)
                        self.assertNotEqual(result.returncode, 0); self.assertIn(REFUSAL, result.stderr)
                        self.assertEqual(self.catalog(), catalogs)
                        self.assertEqual({table: self.table_snapshot(table) for table in TABLES}, snapshots)
                        self.assertEqual(self.surrounding(), before)
                finally:
                    if ' OWNER TO ' in mutation:
                        self.fixture_admin('ALTER TABLE public.test_events OWNER TO postgres;')

    def test_wrong_kind_and_planned_relation_or_type_name_collisions_refuse(self):
        scenarios = (
            ('CREATE VIEW public.test_events AS SELECT 1 AS id;', 'DROP VIEW public.test_events;'),
            ("CREATE TYPE public.market_sentiment AS ENUM('fixture');", 'DROP TYPE public.market_sentiment;'),
            ('CREATE TABLE public.idx_test_events_created_at(id integer);', 'DROP TABLE public.idx_test_events_created_at;'),
        )
        for setup, cleanup in scenarios:
            with self.subTest(setup=setup):
                self.db.sql('DROP TABLE IF EXISTS public.market_sentiment, public.test_events CASCADE;')
                self.db.sql(setup)
                try:
                    before = self.surrounding()
                    result = self.apply(check=False)
                    self.assertNotEqual(result.returncode, 0); self.assertIn(REFUSAL, result.stderr)
                    self.assertEqual(self.surrounding(), before)
                    self.assertFalse(self.exists('market_sentiment'))
                finally:
                    self.db.sql(cleanup)

    def test_planned_array_type_collisions_refuse_without_renaming_existing_types(self):
        for table in TABLES:
            with self.subTest(array_name='_' + table):
                name = 'public._' + table
                self.db.sql('CREATE TYPE ' + name + " AS ENUM('fixture');")
                query = '''SELECT jsonb_agg(to_jsonb(t)||jsonb_build_object('tuple_xmin',t.xmin::text) ORDER BY t.oid)
                  FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace
                  WHERE n.nspname='public';'''
                before, types = self.surrounding(), self.db.scalar(query)
                try:
                    result = self.apply(check=False)
                    self.assertNotEqual(result.returncode, 0); self.assertIn(REFUSAL, result.stderr)
                    self.assertFalse(any(self.exists(target) for target in TABLES))
                    self.assertEqual(self.db.scalar(query), types)
                    self.assertEqual(self.surrounding(), before)
                finally:
                    self.db.sql('DROP TYPE ' + name + ';')

    def test_unreviewed_public_and_column_grants_refuse_without_acl_repair(self):
        for grant in ('GRANT SELECT ON public.test_events TO PUBLIC;',
                      'GRANT SELECT(payload) ON public.test_events TO anon;'):
            with self.subTest(grant=grant):
                self.db.sql('DROP TABLE IF EXISTS public.market_sentiment, public.test_events CASCADE;')
                self.construct(); self.db.sql(grant)
                catalogs, before = self.catalog(), self.surrounding()
                result = self.apply(acl=True, check=False)
                self.assertNotEqual(result.returncode, 0); self.assertIn(REFUSAL, result.stderr)
                self.assertEqual(self.catalog(), catalogs)
                self.assertEqual(self.surrounding(), before)

    def test_unfamiliar_or_inherited_grants_refuse_without_rewriting_roles(self):
        for inherited in (False, True):
            with self.subTest(inherited=inherited):
                self.db.sql('DROP TABLE IF EXISTS public.market_sentiment, public.test_events CASCADE;')
                self.construct()
                self.fixture_admin('CREATE ROLE api_fixture_extra NOLOGIN NOSUPERUSER;'
                                   'GRANT SELECT ON public.test_events TO api_fixture_extra;'
                                   + ('GRANT api_fixture_extra TO anon;' if inherited else ''))
                try:
                    before, catalogs = self.surrounding(), self.catalog()
                    result = self.apply(acl=True, check=False)
                    self.assertNotEqual(result.returncode, 0); self.assertIn(REFUSAL, result.stderr)
                    self.assertEqual(self.catalog(), catalogs)
                    self.assertEqual(self.surrounding(), before)
                finally:
                    self.fixture_admin('REVOKE api_fixture_extra FROM anon;'
                                       'DROP OWNED BY api_fixture_extra; DROP ROLE api_fixture_extra;')

    def test_service_sql_insert_select_returning_and_nullable_default_semantics(self):
        self.apply()
        result = self.actor('service_role', '''INSERT INTO public.test_events(payload)
          VALUES ('{"fixture":"default"}') RETURNING row_to_json(test_events);
          INSERT INTO public.test_events(payload,source,created_at)
          VALUES ('{"fixture":"explicit-null"}',NULL,NULL) RETURNING row_to_json(test_events);''')
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['source'], 'unknown'); self.assertIsNotNone(rows[0]['created_at'])
        self.assertIsNone(rows[1]['source']); self.assertIsNone(rows[1]['created_at'])
        self.assertTrue(all(UUID(row['id']).version == 4 for row in rows))
        result = self.actor('service_role', '''INSERT INTO public.market_sentiment(score,sentiment,summary)
          VALUES (0,'neutral','defaults') RETURNING row_to_json(market_sentiment);
          INSERT INTO public.market_sentiment(score,sentiment,summary,date,source,created_at)
          VALUES (100,'bullish','explicit-null','2024-02-29',NULL,NULL) RETURNING row_to_json(market_sentiment);''')
        sentiments = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
        self.assertEqual(len(sentiments), 2)
        self.assertEqual(sentiments[0]['key_factors'], [])
        self.assertEqual(sentiments[0]['source'], 'grok')
        self.assertEqual(sentiments[0]['date'], self.db.scalar('SELECT CURRENT_DATE::text;'))
        self.assertIsNotNone(sentiments[0]['created_at'])
        self.assertIsNone(sentiments[1]['source']); self.assertIsNone(sentiments[1]['created_at'])
        selected = self.actor('service_role', 'SELECT count(*) FROM public.test_events;')
        self.assertEqual(selected.stdout.strip(), '2')

    def test_native_integer_enum_date_null_and_duplicate_constraints(self):
        self.apply()
        for score, code in (('-1', '23514'), ('101', '23514'), ('2147483648', '22003'), ("'0.5'", '22P02')):
            with self.subTest(score=score):
                self.assert_sql_refuses('INSERT INTO public.market_sentiment(score,sentiment,summary) '
                    f"VALUES ({score},'neutral','invalid');", code=code, role='service_role')
        for source, code in (
            ("INSERT INTO public.market_sentiment(score,sentiment,summary) VALUES (50,'optimistic','invalid');", '23514'),
            ("INSERT INTO public.market_sentiment(score,sentiment,summary,date) VALUES (50,'neutral','invalid','2026-02-30');", '22008'),
            ("INSERT INTO public.test_events(payload) VALUES (NULL);", '23502'),
            ("INSERT INTO public.market_sentiment(score,sentiment,summary,key_factors) VALUES (50,'neutral','invalid',NULL);", '23502'),
        ):
            with self.subTest(code=code, source=source):
                self.assert_sql_refuses(source, code=code, role='service_role')
        self.actor('service_role', "INSERT INTO public.market_sentiment(score,sentiment,summary,date) VALUES (50,'bearish','first','2024-02-29');")
        result = self.assert_sql_refuses("INSERT INTO public.market_sentiment(score,sentiment,summary,date) VALUES (60,'neutral','duplicate','2024-02-29');", code='23505', role='service_role')
        self.assertIn('market_sentiment_date_key', result.stderr)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM public.market_sentiment;'), '1')

    def test_full_effective_privilege_matrix_and_actual_operation_denials(self):
        self.apply(); self.seed(); self.assert_privileges()
        before = {table: self.table_snapshot(table) for table in TABLES}
        for table in TABLES:
            for role in ROLES:
                operations = (
                    f'UPDATE public.{table} SET source=NULL;',
                    f'DELETE FROM public.{table};',
                    f'TRUNCATE public.{table};',
                    f'CREATE TRIGGER fixture_denied BEFORE INSERT ON public.{table} '
                    'FOR EACH ROW EXECUTE FUNCTION dashboard_api_fixture.noop_trigger();',
                )
                for source in operations:
                    with self.subTest(table=table, role=role, source=source):
                        self.assert_sql_refuses(source, code='42501', role=role)
                # PostgreSQL forbids a TEMP-to-permanent foreign key before
                # reaching REFERENCES authorization. Give the tested role a
                # regular owned child so this reaches the actual parent check.
                try:
                    self.fixture_admin('CREATE TABLE dashboard_api_fixture.references_child(id uuid);'
                                       'ALTER TABLE dashboard_api_fixture.references_child OWNER TO ' + role + ';')
                    with self.subTest(table=table, role=role, privilege='REFERENCES'):
                        result = self.assert_sql_refuses(
                            'ALTER TABLE dashboard_api_fixture.references_child ADD FOREIGN KEY(id) '
                            f'REFERENCES public.{table}(id);', code='42501', role=role)
                        self.assertIn(table, result.stderr)
                finally:
                    self.fixture_admin('DROP TABLE IF EXISTS dashboard_api_fixture.references_child;')
                # ANALYZE may successfully return a warning while refusing work.
                result = self.actor(role, f'ANALYZE public.{table};', check=False)
                self.assertTrue('permission denied' in result.stderr.lower()
                                or 'skipping' in result.stderr.lower(), result.stderr)
                if role != 'service_role':
                    self.assert_sql_refuses(f'SELECT * FROM public.{table};', code='42501', role=role)
                    insertion = ("INSERT INTO public.test_events(payload) VALUES ('{}');" if table == 'test_events'
                        else "INSERT INTO public.market_sentiment(score,sentiment,summary,date) VALUES (50,'neutral','denied','2024-03-01');")
                    self.assert_sql_refuses(insertion, code='42501', role=role)
        self.assertEqual({table: self.table_snapshot(table) for table in TABLES}, before)

    def request(self, method, table, *, role='service_role', body=None, object_reply=False):
        self.assertIn(table, TABLES)
        if role is not None:
            self.assertIn(role, ROLES)
        endpoint = httpx.URL(self.db.endpoint)
        self.assertEqual(endpoint.host, '127.0.0.1')
        self.assertEqual(endpoint.scheme, 'http')
        headers = {'Content-Profile': 'public', 'Accept-Profile': 'public'}
        if role is not None:
            headers['Authorization'] = 'Bearer ' + fixture_jwt(role)
        if object_reply:
            headers.update({'Accept': 'application/vnd.pgrst.object+json', 'Prefer': 'return=representation'})
        with httpx.Client(trust_env=False, timeout=3, follow_redirects=False) as client:
            return client.request(method, str(endpoint).rstrip('/') + '/' + table,
                                  params={'select': ','.join(COLUMNS[table])}, headers=headers, json=body)

    def test_http_single_object_insert_default_nulls_readback_and_duplicate(self):
        self.apply(); self.db.start_http()
        response = self.request('POST', 'test_events', body={'payload': {'fixture': 'http'}}, object_reply=True)
        self.assertEqual(response.status_code, 201, response.text)
        event = response.json()
        self.assertEqual(set(event), {'id', 'payload', 'source', 'created_at'})
        self.assertEqual(event['source'], 'unknown'); self.assertIsNotNone(event['created_at'])
        stored = json.loads(self.db.scalar('SELECT row_to_json(t) FROM public.test_events t WHERE id='
                                          + literal(event['id']) + ';'))
        self.assertEqual(stored, event)
        response = self.request('POST', 'test_events', body={'payload': {}, 'source': None, 'created_at': None}, object_reply=True)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIsNone(response.json()['source']); self.assertIsNone(response.json()['created_at'])
        body = {'score': 100, 'sentiment': 'bullish', 'summary': 'http', 'date': '2024-02-29'}
        response = self.request('POST', 'market_sentiment', body=body, object_reply=True)
        self.assertEqual(response.status_code, 201, response.text)
        sentiment = response.json()
        self.assertEqual(set(sentiment), {'id', 'score', 'sentiment', 'summary', 'key_factors', 'date', 'source', 'created_at'})
        self.assertEqual(sentiment['key_factors'], []); self.assertEqual(sentiment['source'], 'grok')
        stored = json.loads(self.db.scalar('SELECT row_to_json(t) FROM public.market_sentiment t WHERE id='
                                          + literal(sentiment['id']) + ';'))
        self.assertEqual(stored, sentiment)
        duplicate = self.request('POST', 'market_sentiment', body=body, object_reply=True)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()['code'], '23505')
        invalid = dict(body, date='2024-03-01', score=.5)
        response = self.request('POST', 'market_sentiment', body=invalid, object_reply=True)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], '22P02')
        for table in TABLES:
            response = self.request('GET', table)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json())

    def test_http_anonymous_authenticated_and_service_write_denials(self):
        self.apply(); self.seed(); self.db.start_http()
        before = {table: self.table_snapshot(table) for table in TABLES}
        for table in TABLES:
            insert = ({'payload': {}} if table == 'test_events' else
                      {'score': 50, 'sentiment': 'neutral', 'summary': 'denied', 'date': '2024-03-01'})
            for role in (None, 'anon', 'authenticated'):
                for method, body in (('GET', None), ('POST', insert), ('PATCH', {'source': None}), ('DELETE', None)):
                    with self.subTest(table=table, role=role, method=method):
                        response = self.request(method, table, role=role, body=body)
                        self.assertIn(response.status_code, (401, 403), response.text)
                        self.assertEqual(response.json()['code'], '42501')
            for method, body in (('PATCH', {'source': None}), ('DELETE', None)):
                response = self.request(method, table, body=body)
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(response.json()['code'], '42501')
        self.assertEqual({table: self.table_snapshot(table) for table in TABLES}, before)


if __name__ == '__main__':
    unittest.main()
