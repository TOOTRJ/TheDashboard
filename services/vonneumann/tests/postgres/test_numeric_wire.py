"""Independent real PG17 numeric/hash proof, limited installer, no hosted DB."""
import hashlib
import json
import math
import os
from pathlib import Path
import random
import struct
import unittest

from tests.postgres.harness import IsolatedPostgres, OPT_IN
from tests.measure_provider_ga_research import literal
from tests.test_partitioned_checkpoint import partition_trace
from vonneumann.research import numeric_wire as numbers

SQL=Path(__file__).resolve().parents[2]/'db-contract'/'research'/'numeric_wire.sql'


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class NumericWireSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=IsolatedPostgres().start()
        try:
            cls.db.sql('''CREATE ROLE vn_wire_installer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
              CREATE ROLE vn_wire_auditor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
              CREATE ROLE vn_wire_relay LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
              GRANT CREATE ON DATABASE postgres TO vn_wire_installer;''')
            denied=cls.db.sql(SQL.read_text(),role='vn_wire_installer',check=False)
            if denied.returncode==0 or 'offline_numeric_wire_fixture_required' not in denied.stderr:
                raise AssertionError('SQL artifact installed without its offline marker')
            cls.db.sql("SET dashboard.numeric_wire_fixture='offline-v1'; BEGIN;"+SQL.read_text()+'COMMIT;',
                       role='vn_wire_installer')
            cls.db.sql('''GRANT USAGE ON SCHEMA vn_numeric_research TO vn_wire_auditor;
              GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA vn_numeric_research TO vn_wire_auditor;''',
                       role='vn_wire_installer')
        except BaseException:
            cls.db.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def audit(self,wire,maximum=262144):
        return json.loads(self.db.scalar('SELECT vn_numeric_research.audit('+
            literal(wire.decode())+','+str(maximum)+');',role='vn_wire_auditor'))

    def reject(self,wire):
        with self.assertRaises(ValueError):
            numbers.decode(wire)
        result=self.db.sql('SELECT vn_numeric_research.audit('+literal(wire.decode())+');',
                           role='vn_wire_auditor',check=False)
        self.assertNotEqual(result.returncode,0)

    def test_limited_installer_owns_invoker_functions_and_clients_are_denied(self):
        rows=json.loads(self.db.scalar("""SELECT json_agg(x) FROM (
          SELECT p.proname,r.rolname AS owner,p.prosecdef,p.proconfig FROM pg_proc p
          JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner
          WHERE n.nspname='vn_numeric_research' ORDER BY p.proname)x;"""))
        self.assertEqual(len(rows),4)
        self.assertTrue(all(r['owner']=='vn_wire_installer' and not r['prosecdef']
            and r['proconfig']==['search_path=pg_catalog'] for r in rows))
        privileges=self.db.scalar("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls FROM pg_roles WHERE rolname='vn_wire_installer';")
        self.assertEqual(privileges,'f')
        for role in ('anon','authenticated','service_role','vn_wire_relay'):
            result=self.db.sql("SELECT vn_numeric_research.audit('{}');",role=role,check=False)
            self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='vn_numeric_research';"),'0')

    def test_exact_hash_for_unicode_controls_key_order_and_large_numeric_values(self):
        value={'z':None,'yes':True,'no':False,'zero':0,'negative':-(2**256-1),
               'revision':2**63-1,'slot':2**64-1,'largest':2**256-1,
               'fraction':0.1,'negative_zero':-0.0,
               'escapes':'"/\\\b\f\n\r\t'+''.join(chr(i) for i in (1,2,3,11,14,31)),
               'é':'emoji 🦉 café','nested':{'😀':'astral','\ue000':'bmp','a':[]}}
        wire=numbers.encode(value); result=self.audit(wire)
        self.assertEqual(result['sha256'],hashlib.sha256(wire).hexdigest())
        self.assertEqual(result['bytes'],len(wire))
        self.assertEqual(result['tagged'],json.loads(wire))
        self.assertEqual(result['tagged']['negative_zero'],{'$float64':'-0x0.0p+0'})
        for integer in (0,2**63-1,2**64-1,2**256-1,-(2**256-1)):
            decoded=self.db.scalar("SELECT vn_numeric_research.integer_text("+literal(str(integer))+");",
                                   role='vn_wire_auditor')
            self.assertEqual(decoded,str(integer))

    def test_binary64_bits_match_500_seeded_finite_values_and_boundary_values(self):
        values=[0.0,-0.0,0.1,1.0,-1.0,float.fromhex('0x1.fffffffffffffp+1023'),
                float.fromhex('0x1.0000000000000p-1022'),
                float.fromhex('0x0.0000000000001p-1022'),
                -float.fromhex('0x0.fffffffffffffp-1022')]
        rng=random.Random(1942)
        while len(values)<509:
            value=struct.unpack('>d',rng.getrandbits(64).to_bytes(8,'big'))[0]
            if math.isfinite(value): values.append(value)
        sql=' UNION ALL '.join('SELECT '+str(i)+",encode(vn_numeric_research.binary64("+
            literal(value.hex())+"),'hex')" for i,value in enumerate(values))
        rows=self.db.scalar(sql+' ORDER BY 1;',role='vn_wire_auditor',timeout=30).splitlines()
        self.assertEqual(rows,[str(i)+'|'+struct.pack('>d',v).hex() for i,v in enumerate(values)])
        wire=numbers.encode(values)
        self.assertEqual(self.audit(wire)['sha256'],hashlib.sha256(wire).hexdigest())

    def test_duplicate_keys_escaped_duplicates_and_noncanonical_json_are_rejected(self):
        for wire in (b'{"x":true,"x":false}',b'{"a":true,"\\u0061":false}',
            b'{"nested":[{"x":true,"x":false}]}',b'{ "x":true}',b'{"z":true,"a":false}',
            b'[true ,false]',b'null ',b' true',b'"\\u0061"',b'"\\/"',b'{"x":"\\u0000"}',
            b'{"x":"\\ud800"}',b'{"x":NaN}',b'{"x":Infinity}',b'{"x":1}',b'{"x":1.0}'):
            with self.subTest(wire=wire): self.reject(wire)

    def test_reserved_tag_collisions_and_noncanonical_integers_are_rejected(self):
        for value in ({'$integer':'01'},{'$integer':'-0'},{'$integer':'+1'},
            {'$integer':'1','extra':False},{'$integer':'1','$float64':'0x0.0p+0'},
            {'$integer':True},{'$integer':str(2**256)},{'$integer':str(-(2**256))},
            {'$integer':'١'},{'$integer':'1'*101}):
            self.reject(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())

    def test_noncanonical_or_nonfinite_binary64_tags_are_rejected(self):
        for value in ('nan','inf','-inf','0.1','0x1p+0','0x1.0000000000000p+00',
            '0x1.0000000000000p-0','0X1.0000000000000p+0','0x1.fffffffffffffp+1024',
            '0x1.0000000000000p-1023','0x0.0000000000000p-1022',
            '0x0.0000000000001p-1023','0x0.0000000000001p+0'):
            self.reject(json.dumps({'$float64':value},separators=(',',':')).encode())

    def test_depth_container_string_nodes_and_traversal_limits_match_python(self):
        value=None
        for _ in range(64): value=[value]
        wire=numbers.encode(value); self.assertEqual(self.audit(wire)['sha256'],hashlib.sha256(wire).hexdigest())
        self.reject(b'['+wire+b']')
        for value in ([None]*4097,'x'*16385,'é'*8193,[[None]*4096]*5,['x'*16000]*17):
            wire=json.dumps(value,separators=(',',':'),ensure_ascii=False).encode()
            with self.subTest(kind=type(value).__name__): self.reject(wire)

    def test_byte_ceiling_exact_boundary_and_caller_cannot_raise_budget(self):
        wire=numbers.encode({'text':'hello','count':2})
        self.assertEqual(self.audit(wire,maximum=len(wire))['bytes'],len(wire))
        for maximum in (len(wire)-1,0,262145):
            result=self.db.sql('SELECT vn_numeric_research.audit('+literal(wire.decode())+','+
                str(maximum)+');',role='vn_wire_auditor',check=False)
            self.assertNotEqual(result.returncode,0)
        result=self.db.sql("SELECT vn_numeric_research.audit(NULL);",role='vn_wire_auditor',check=False)
        self.assertNotEqual(result.returncode,0)
        self.reject(b' '*262145)

    def test_installation_settings_and_helper_budget_parameters_fail_closed(self):
        result=self.db.sql("SET dashboard.numeric_wire_fixture='offline-v1'; SET standard_conforming_strings=off;"+
                           SQL.read_text(),role='vn_wire_installer',check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('offline_numeric_wire_fixture_required',result.stderr)
        for params in ('NULL,0,0','0,NULL,0','0,0,NULL','-1,0,0','0,-1,0','0,0,-1'):
            result=self.db.sql("SELECT * FROM vn_numeric_research.walk('{}',"+params+');',
                               role='vn_wire_auditor',check=False)
            self.assertNotEqual(result.returncode,0)
        # Ordinary clients cannot turn the guarded artifact into a schema installer.
        result=self.db.sql("SET dashboard.numeric_wire_fixture='offline-v1'; CREATE SCHEMA unauthorised;",
                           role='vn_wire_auditor',check=False)
        self.assertNotEqual(result.returncode,0)

    def test_256_seeded_mixed_documents_have_identical_canonical_hashes(self):
        rng=random.Random(989); documents=[]
        for i in range(256):
            floating=struct.unpack('>d',rng.getrandbits(64).to_bytes(8,'big'))[0]
            if not math.isfinite(floating): floating=-0.0
            documents.append({'index':i,'amount':rng.getrandbits(256)*(-1 if i%2 else 1),
                'float':floating,'array':[None,i%2==0,{'key 🦉':'\n\\'+str(i)}],
                'unicode':chr(0x400+i)})
        sql=' UNION ALL '.join('SELECT '+str(i)+",vn_numeric_research.audit("+
            literal(numbers.encode(v).decode())+")->>'sha256'" for i,v in enumerate(documents))
        rows=self.db.scalar(sql+' ORDER BY 1;',role='vn_wire_auditor',timeout=30).splitlines()
        self.assertEqual(rows,[str(i)+'|'+hashlib.sha256(numbers.encode(v)).hexdigest()
                              for i,v in enumerate(documents)])

    def test_complete_owned_partition_commands_and_all_components_match_sql_hashes(self):
        samples=[]
        partition_trace(True,windows=1,observer=lambda c,o,ow,p,w:samples.append((p,w)))
        for capture,wire in samples:
            result=self.audit(wire)
            self.assertEqual(result['sha256'],hashlib.sha256(wire).hexdigest())
            self.assertEqual(result['tagged'],json.loads(wire))
        for block in samples[-1][0].components:
            self.assertEqual(self.audit(block._wire)['sha256'],block.identity)
        if os.environ.get('DASHBOARD_NUMERIC_WIRE_MEASURE')=='1':
            chosen=[('bootstrap',samples[0][1]),('quote',samples[1][1]),
                    ('replacement',max((w for _,w in samples),key=len))]
            sql=['SET plan_cache_mode=force_generic_plan;',
                 'CREATE TEMP TABLE timings(kind text,wire_bytes integer,elapsed_us bigint);']
            for kind,wire in chosen:
                sql.append('DO $measure$ DECLARE t timestamptz;i integer;r jsonb;w text:='+
                    literal(wire.decode())+';BEGIN FOR i IN 1..30 LOOP '+
                    't:=clock_timestamp(); r:=vn_numeric_research.audit(w); '+
                    'INSERT INTO timings VALUES ('+literal(kind)+','+str(len(wire))+
                    ',extract(epoch FROM clock_timestamp()-t)*1000000); END LOOP; END $measure$;')
            sql.append("SELECT json_agg(x) FROM (SELECT kind,wire_bytes,count(*) AS samples,"
                "percentile_cont(.5) WITHIN GROUP(ORDER BY elapsed_us) AS p50_us,"
                "percentile_cont(.95) WITHIN GROUP(ORDER BY elapsed_us) AS p95_us,"
                "max(elapsed_us) AS maximum_us FROM timings GROUP BY kind,wire_bytes ORDER BY kind)x;")
            timings=json.loads(self.db.scalar('\n'.join(sql),role='vn_wire_auditor',timeout=60))
            value={'date':'2026-10-09','identity':self.db.identity,'sql_sha256':hashlib.sha256(SQL.read_bytes()).hexdigest(),
                'scope':'independent canonical tagged numeric wire and SHA256 only; no transition/admission/restart authority',
                'installer':'actual synthetic NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS fixture role',
                'complete_commands':len(samples),'final_components':len(samples[-1][0].components),
                'limits':{'bytes':262144,'nodes':20000,'depth':64,'container_entries':4096,
                          'string_utf8_bytes':16384,'integer_bits':256},
                'warm_server_audit_timings':timings,
                'timing_method':'PL/pgSQL wire variable and force_generic_plan prevent immutable literal constant folding; each sample evaluates the complete audit',
                'timing_exclusions':['transport/TLS','run locks/contention','economic/source/lineage admission',
                    'journal/pins/projections','final source/lease recheck','COMMIT/WAL/relay','hosted tails'],
                'tables_in_installed_artifact':0,'production_grants_or_install':False}
            path=Path(__file__).resolve().parents[2]/'research'/'native-numeric-wire-measurements.json'
            path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
