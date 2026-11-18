"""Real PostgreSQL original-ID, stop-ordering, scope and atomic quota checks."""
import base64
import hashlib
import json
from pathlib import Path
import unittest
from tests.postgres import harness

OWNER='10000000-0000-4000-8000-000000000001'
RUN='10000000-0000-4000-8000-000000000002'
LOGIN='vn_paper_'+'a'*32
COMMAND='10000000-0000-4000-8000-000000000003'
START='10000000-0000-4000-8000-000000000004'
STOP='10000000-0000-4000-8000-000000000005'
MIGRATIONS=Path(__file__).resolve().parents[4]/'supabase/migrations'
BASE_SQL=MIGRATIONS/'20261117010000_vonneumann_paper_v6.sql'
SEARCH_PATH_SQL=MIGRATIONS/'20261118010000_vonneumann_paper_v6_search_path.sql'


def encoded(raw): return base64.b64encode(raw).decode()
def canonical(row): return json.dumps(row,sort_keys=True,separators=(',',':')).encode()


class ProspectiveJournalSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        if os.environ.get(harness.OPT_IN)!='1':
            raise unittest.SkipTest('Explicit isolated PostgreSQL opt-in required')
        cls.db=harness.IsolatedPostgres();cls.addClassCleanup(cls.db.close);cls.db.start()
        cls.db.sql(BASE_SQL.read_text())
        cls.db.sql(SEARCH_PATH_SQL.read_text())
        cls.db.sql(f"INSERT INTO auth.users VALUES('{OWNER}'); CREATE ROLE {LOGIN} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS VALID UNTIL '2099-01-01'; GRANT vn_paper_v6_client TO {LOGIN}; INSERT INTO vn_paper_v6.bindings VALUES('{LOGIN}','{OWNER}','{RUN}','2099-01-01');")

    def setUp(self):
        self.db.sql('TRUNCATE vn_paper_v6.entries,vn_paper_v6.rejections,vn_paper_v6.artifacts,vn_paper_v6.sources,vn_paper_v6.controls,vn_paper_v6.runs RESTART IDENTITY;')

    def query(self,op,body=None,*,role=LOGIN):
        data={'owner_id':OWNER,'run_id':RUN,**(body or {})}
        return "SELECT vn_paper_v6.rpc('"+op+"',$paper$"+json.dumps(data)+"$paper$::jsonb);"

    def rpc(self,op,body=None):
        return json.loads(self.db.scalar(self.query(op,body),role=LOGIN))

    def start(self): return self.rpc('control',{'request_id':START,'action':'start'})

    def entry(self,command=COMMAND,sequence=1,prior=None,kind='bootstrap'):
        candidate='{}'
        row={'format':'dashboard-prospective-paper-journal-v1','owner_id':OWNER,'run_id':RUN,
            'command_id':command,'sequence':str(sequence),'previous_sha256':prior,
            'witness':{'kind':kind,**({'action':'stop'} if kind=='control' else {})},
            'candidate_wire':candidate,'candidate_sha256':hashlib.sha256(candidate.encode()).hexdigest()}
        return canonical(row)

    def append(self,raw,expected=0,prior=None):
        return self.rpc('append',{'command_id':json.loads(raw)['command_id'],'wire':encoded(raw),'expected_sequence':expected,'expected_sha256':prior})

    def test_original_ack_survives_later_stop_and_conflicts_refuse(self):
        self.start();wire=self.entry();self.append(wire)
        self.rpc('control',{'request_id':STOP,'action':'stop'})
        self.assertEqual(base64.b64decode(self.append(wire)['wire']),wire)
        self.assertEqual(self.rpc('head')['sequence'],1)
        changed=json.loads(wire);changed['witness']={'kind':'decision'}
        result=self.db.sql(self.query('append',{'command_id':COMMAND,'wire':encoded(canonical(changed)),'expected_sequence':0}),role=LOGIN,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.rpc('head')['sequence'],1)

    def test_stop_orders_before_economic_append_but_terminal_can_commit(self):
        self.start();self.rpc('control',{'request_id':STOP,'action':'stop'})
        raw=self.entry()
        rejected=self.append(raw)
        self.assertTrue(rejected['refused'])
        self.assertEqual(self.rpc('get',{'command_id':COMMAND}),rejected)
        self.append(self.entry(command='10000000-0000-4000-8000-000000000099',kind='control'))
        self.assertEqual(self.rpc('head')['sequence'],1)

    def test_stale_revision_cannot_replace_durable_head(self):
        self.start();wire=self.entry();self.append(wire)
        other=self.entry('10000000-0000-4000-8000-000000000099')
        result=self.db.sql(self.query('append',{'command_id':json.loads(other)['command_id'],'wire':encoded(other),'expected_sequence':0}),role=LOGIN,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.rpc('head')['sha256'],hashlib.sha256(wire).hexdigest())
        self.assertEqual(len(self.rpc('scan',{'after_sequence':0,'limit':25})),1)

    def test_runtime_has_only_scoped_function_access(self):
        for role in ('anon','authenticated','service_role'):
            self.assertNotEqual(self.db.sql(self.query('head'),role=role,check=False).returncode,0)
        self.assertNotEqual(self.db.sql('SELECT * FROM vn_paper_v6.entries;',role=LOGIN,check=False).returncode,0)
        self.assertNotEqual(self.db.sql(self.query('head',{'owner_id':RUN}),role=LOGIN,check=False).returncode,0)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_tables WHERE schemaname='vn_paper_v6' AND rowsecurity"),'7')

    def test_packet_original_and_native_clock_readback(self):
        raw=b'{"kind":"complete","capsules":[]}'
        row=self.rpc('admit_source',{'packet_id':COMMAND,'wire':encoded(raw)})
        read=self.rpc('get_source',{'packet_id':COMMAND})
        self.assertEqual(read['accepted_at_us'],row['accepted_at_us'])
        self.assertEqual(read['receipt_sha256'],row['receipt_sha256'])
        self.assertGreaterEqual(read['available_at_upper_us'],read['accepted_at_us'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),read['sha256'])
        self.assertNotEqual(self.db.sql(self.query('admit_source',{'packet_id':COMMAND,'wire':encoded(raw+b' ')}),role=LOGIN,check=False).returncode,0)

    def test_quota_failure_rolls_back_original_and_byte_accounting(self):
        self.rpc('head');self.db.sql(f"UPDATE vn_paper_v6.runs SET bytes=1073741820 WHERE owner_id='{OWNER}';")
        self.assertNotEqual(self.db.sql(self.query('admit_source',{'packet_id':COMMAND,'wire':encoded(b'larger-than-budget')}),role=LOGIN,check=False).returncode,0)
        self.assertIsNone(self.rpc('get_source',{'packet_id':COMMAND}))
        self.assertEqual(self.rpc('head')['bytes'],1073741820)

    def test_control_identity_is_immutable_and_stop_survives_without_model(self):
        self.start();stop=self.rpc('control',{'request_id':STOP,'action':'stop'})
        self.assertEqual(self.rpc('latest_control'),stop)
        self.assertEqual(stop['owner_id'],OWNER)
        self.assertNotEqual(self.db.sql(self.query('control',{'request_id':STOP,'action':'start'}),role=LOGIN,check=False).returncode,0)
        self.assertEqual(self.rpc('head')['sequence'],0)

    def test_artifact_original_bytes_and_seal_future_are_refused(self):
        key='1'*64;raw=canonical({'format':'dashboard-prospective-source-recipe-v1','kind':'mark','sha256':key,'inputs':{}})
        self.rpc('put_artifact',{'kind':'mark','sha256':key,'wire':encoded(raw)})
        result=self.rpc('get_artifact',{'kind':'mark','sha256':key})
        self.assertEqual(base64.b64decode(result['wire']),raw)
        self.assertNotEqual(self.db.sql(self.query('put_artifact',{'kind':'mark','sha256':key,'wire':encoded(raw+b' ')}),role=LOGIN,check=False).returncode,0)
        future=canonical({'kind':'seal','start_second':4102444800,'end_second':4102499700,'records_sha256':'2'*64,'through_ingest_sequence':1})
        self.assertNotEqual(self.db.sql(self.query('seal_sources',{'packet_id':COMMAND,'wire':encoded(future)}),role=LOGIN,check=False).returncode,0)

    def test_missing_page_or_seal_fields_cannot_remove_bounds(self):
        for op in ('scan','artifact_inventory','source_inventory'):
            for body in ({'after_sequence':0},{'limit':1},{'limit':None,'after_sequence':0}):
                self.assertNotEqual(self.db.sql(self.query(op,body),role=LOGIN,check=False).returncode,0)
        missing=canonical({'kind':'seal'})
        self.assertNotEqual(self.db.sql(self.query('seal_sources',{'packet_id':COMMAND,'wire':encoded(missing)}),role=LOGIN,check=False).returncode,0)
        self.assertEqual(self.rpc('artifact_inventory',{'after_sequence':0,'limit':25}),[])

    def test_artifact_page_bounds_total_bytes_while_small_rows_share_page(self):
        self.rpc('head')
        # Admin-only fixture inserts large retained values to exercise the actual
        # SQL inventory byte limit, independent of transport and recipe parsers.
        self.db.sql(f"INSERT INTO vn_paper_v6.artifacts(owner_id,run_id,kind,sha256,wire) SELECT '{OWNER}','{RUN}','mark',lpad(i::text,64,'0'),decode(repeat('61',3145728),'hex') FROM generate_series(1,4) i;",timeout=20)
        page=self.rpc('artifact_inventory',{'after_sequence':0,'limit':25})
        self.assertEqual(len(page),2)
        self.assertLessEqual(sum(len(base64.b64decode(r['wire'])) for r in page),8388608)
        next_page=self.rpc('artifact_inventory',{'after_sequence':page[-1]['sequence'],'limit':25})
        self.assertEqual(len(next_page),2)

    def test_committed_stop_rejection_is_original_after_later_start(self):
        self.start();self.rpc('control',{'request_id':STOP,'action':'stop'})
        wire=self.entry();rejected=self.append(wire)
        self.rpc('control',{'request_id':'10000000-0000-4000-8000-000000000088','action':'start'})
        self.assertEqual(self.append(wire),rejected)
        self.assertEqual(self.rpc('get',{'command_id':COMMAND}),rejected)
        self.assertEqual(self.rpc('head')['sequence'],0)
        self.assertEqual(self.rpc('scan',{'after_sequence':0,'limit':25}),[])

    def test_late_original_after_stop_model_commit_has_immutable_rejection(self):
        self.start()
        first = self.entry(); self.append(first)
        first_head = self.rpc('head')
        pending_id = '10000000-0000-4000-8000-000000000098'
        pending = self.entry(pending_id, sequence=2, prior=first_head['sha256'], kind='decision')
        self.rpc('control', {'request_id': STOP, 'action': 'stop'})
        terminal = self.entry('10000000-0000-4000-8000-000000000099', sequence=2,
            prior=first_head['sha256'], kind='control')
        self.append(terminal, expected=1, prior=first_head['sha256'])
        stopped_head = self.rpc('head')
        rejected = self.append(pending, expected=1, prior=first_head['sha256'])
        self.assertTrue(rejected['refused'])
        self.assertEqual(rejected['stop_request_id'], STOP)
        self.assertEqual(base64.b64decode(rejected['wire']), pending)
        self.assertEqual(self.rpc('get', {'command_id': pending_id}), rejected)
        self.assertEqual(self.append(pending, expected=1, prior=first_head['sha256']), rejected)
        self.assertEqual(self.rpc('head')['sequence'], stopped_head['sequence'])
        self.assertEqual(self.rpc('head')['sha256'], stopped_head['sha256'])
        self.assertEqual(len(self.rpc('scan', {'after_sequence': 0, 'limit': 25})), 2)

    def test_expiry_while_waiting_for_run_lock_refuses_before_write(self):
        self.rpc('head')
        self.addCleanup(self.db.sql,
            f"UPDATE vn_paper_v6.bindings SET expires_at='2099-01-01' WHERE login='{LOGIN}';")
        holder = self.db.begin_sql(f"BEGIN; SELECT 1 FROM vn_paper_v6.runs WHERE owner_id='{OWNER}' AND run_id='{RUN}' FOR UPDATE; SELECT pg_sleep(3) /* v6 expiry holder */; COMMIT;", timeout=6)
        self.db.wait_until("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE query LIKE '%v6 expiry holder%' AND wait_event='PgSleep');")
        self.db.sql(f"UPDATE vn_paper_v6.bindings SET expires_at=clock_timestamp()+interval '1 second' WHERE login='{LOGIN}';")
        waiting = self.db.begin_sql(self.query('admit_source',
            {'packet_id': COMMAND, 'wire': encoded(b'original must not commit')}), role=LOGIN, timeout=6)
        self.db.wait_until(f"SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename='{LOGIN}' AND wait_event_type='Lock');")
        holder.wait()
        result = waiting.wait(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('paper_principal_refused', result.stderr)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_paper_v6.sources;'), '0')
        self.assertEqual(self.db.scalar('SELECT bytes FROM vn_paper_v6.runs;'), '0')

    def test_missing_candidate_hash_is_not_accepted_as_an_original_or_rejection(self):
        self.start()
        for action in ('start', 'stop'):
            if action == 'stop':
                self.rpc('control', {'request_id': STOP, 'action': 'stop'})
            invalid = json.loads(self.entry())
            del invalid['candidate_wire']; del invalid['candidate_sha256']
            outcome = self.db.sql(self.query('append', {'command_id': COMMAND,
                'wire': encoded(canonical(invalid)), 'expected_sequence': 0,
                'expected_sha256': None}), role=LOGIN, check=False)
            self.assertNotEqual(outcome.returncode, 0)
            self.assertIn('paper_entry_refused', outcome.stderr)
        self.assertEqual(self.rpc('head')['sequence'], 0)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_paper_v6.rejections;'), '0')


class ProspectiveJournalSearchPathSQLTests(unittest.TestCase):
    def setUp(self):
        import os
        if os.environ.get(harness.OPT_IN) != '1':
            self.skipTest('Explicit isolated PostgreSQL opt-in required')
        self.db = harness.IsolatedPostgres()
        self.addCleanup(self.db.close)
        self.db.start()
        self.db.sql(BASE_SQL.read_text())

    def test_temporary_type_cannot_override_the_trusted_uuid_type(self):
        # An intentionally rejecting local type provides a harmless resolution
        # sentinel. The fixed RPC must keep using pg_catalog.uuid.
        self.db.sql(f"INSERT INTO auth.users VALUES('{OWNER}'); "
            f"CREATE ROLE {LOGIN} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS VALID UNTIL '2099-01-01'; "
            f"GRANT USAGE ON SCHEMA vn_paper_v6 TO {LOGIN}; "
            f"GRANT EXECUTE ON FUNCTION vn_paper_v6.rpc(text,jsonb) TO {LOGIN}; "
            f"INSERT INTO vn_paper_v6.bindings VALUES('{LOGIN}','{OWNER}','{RUN}','2099-01-01');")
        request = json.dumps({'owner_id': OWNER, 'run_id': RUN, 'command_id': COMMAND})
        shadow = ("CREATE TEMP TABLE initialize_paper_temp(x pg_catalog.int4); "
            "CREATE DOMAIN pg_temp.uuid AS pg_catalog.uuid CHECK(false); "
            f"SELECT vn_paper_v6.rpc('get',$wire${request}$wire$::pg_catalog.jsonb);")
        before = self.db.sql(shadow, role=LOGIN, check=False)
        self.assertNotEqual(before.returncode, 0)
        self.assertIn("violates check constraint", before.stderr)
        self.db.sql(SEARCH_PATH_SQL.read_text())
        self.assertEqual(self.db.scalar("SELECT proconfig::text FROM pg_catalog.pg_proc WHERE oid='vn_paper_v6.rpc(text,jsonb)'::regprocedure;"),
            '{"search_path=pg_catalog, pg_temp"}')
        after = self.db.sql(shadow, role=LOGIN, check=False)
        self.assertEqual(after.returncode, 0)
        self.assertEqual(self.db.scalar(f"SELECT vn_paper_v6.rpc('head',$wire${request}$wire$::jsonb)->>'sequence';", role=LOGIN), '0')
        foreign = json.dumps({'owner_id': RUN, 'run_id': RUN})
        self.assertNotEqual(self.db.sql(f"SELECT vn_paper_v6.rpc('head',$wire${foreign}$wire$::jsonb);",
            role=LOGIN, check=False).returncode, 0)
        self.db.sql(SEARCH_PATH_SQL.read_text())

    def test_forward_refuses_unreviewed_configuration_body_and_owner(self):
        self.db.sql('ALTER FUNCTION vn_paper_v6.rpc(text,jsonb) SET search_path=pg_catalog,public,pg_temp;')
        refused = self.db.sql(SEARCH_PATH_SQL.read_text(), check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('paper_search_path_original_mismatch', refused.stderr)
        self.db.sql('ALTER FUNCTION vn_paper_v6.rpc(text,jsonb) SET search_path=pg_catalog;')
        function = 'CREATE OR REPLACE FUNCTION' + BASE_SQL.read_text().split('CREATE FUNCTION', 1)[1].split('$f$;', 1)[0] + '$f$;'
        changed = function.replace('END $f$;', 'END\n-- unreviewed fixture body\n$f$;')
        self.assertNotEqual(function, changed)
        self.db.sql(changed)
        refused = self.db.sql(SEARCH_PATH_SQL.read_text(), check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('paper_search_path_original_mismatch', refused.stderr)
        self.db.sql(function)
        self.db.sql('CREATE ROLE paper_unreviewed_owner NOLOGIN; '
            'ALTER FUNCTION vn_paper_v6.rpc(text,jsonb) OWNER TO paper_unreviewed_owner;')
        refused = self.db.sql(SEARCH_PATH_SQL.read_text(), check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('paper_search_path_original_mismatch', refused.stderr)
