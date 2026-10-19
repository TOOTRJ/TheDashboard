"""Actual parser-only PG proof against original public fake bytes. No providers."""
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import time
import unittest

from tests.postgres.harness import IsolatedPostgres,OPT_IN
from tests.security_support import deny_network
from tests.test_source_admission_v3 import fixture
from vonneumann.market import provider_acquisition_v3 as a,source_admission_v3 as v

SQL=Path(__file__).resolve().parents[2]/'db-contract/research/jupiter_raw_parser_v3.sql'
NS='vn_jupiter_raw_parser_research_v3'
POLICY='e7fb225868e9401e5648487e9836d9c0aff817f2ba2cdd63a20b90b75aadb24e'
AUTHORITY={key:False for key in ('authenticated_principal','calibrated_clock','committed_readback','hosted_authority',
    'lease_authority','live_trading_authority','native_admission','provider_attested','running_authority')}


def raw_price(token='100.123456789012345678',block='42',**metadata):
    tail=''.join(','+json.dumps(key)+':'+json.dumps(value,ensure_ascii=False,separators=(',',':')) for key,value in metadata.items())
    return ('{"'+a.MINT+'":{"usdPrice":'+token+',"blockId":'+block+',"decimals":9'+tail+'}}').encode()


def packet(*,price=None,block=42,second=1_800_000_000,rpc_ids=(1,2)):
    req=(a.public_request('jupiter-price-v3'),a.public_request('solana-rpc',rpc_method='getGenesisHash',rpc_id=rpc_ids[0]),
        a.public_request('solana-rpc',rpc_method='getBlockTime',rpc_id=rpc_ids[1],slot=block))
    bodies=(raw_price(block=str(block)) if price is None else price,a.canonical({'jsonrpc':'2.0','id':rpc_ids[0],'result':a.GENESIS}),
        a.canonical({'jsonrpc':'2.0','id':rpc_ids[1],'result':second}))
    return req,bodies


def bytea(value):
    return "pg_catalog.decode('"+value.hex()+"','hex')"


def array(values):
    return 'ARRAY['+','.join(bytea(item) for item in values)+']::bytea[]'


def reference(requests,bodies):
    """Frozen A1 reparses the originals; no normalized native result is its input."""
    with deny_network():
        f=fixture();rdata=f['r'].to_dict();cdata=f['c'].to_dict()
        rdata['genesis_rpc_id']=str(a.read_json(a.request_fields(requests[1],'solana-rpc')['body_wire'].encode(),4096,numeric=True)['id'])
        rdata['block_time_rpc_id']=str(a.read_json(a.request_fields(requests[2],'solana-rpc')['body_wire'].encode(),4096,numeric=True)['id'])
        reservation=v.envelope('Reservation',rdata);cdata['reservation_sha256']=reservation.sha256
        for index,(request,body) in enumerate(zip(requests,bodies)):
            row=a.read_json(cdata['capsule_wires'][index].encode(),a.MAX_CAPSULE_BYTES,exact=True)
            row.update(canonical_public_request_wire=request.decode(),request_sha256=hashlib.sha256(request).hexdigest(),
                response_base64=base64.b64encode(body).decode(),response_sha256=hashlib.sha256(body).hexdigest(),response_bytes=str(len(body)))
            cdata['capsule_wires'][index]=a.canonical(row).decode()
        capture=v.envelope('Capture',cdata);v.validate_capture(reservation,capture)
        _,price,block,source=v._parse_trio(reservation.to_dict(),capture.to_dict())
        return price,str(block),str(source)


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class JupiterRawParserV3SqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=IsolatedPostgres().start();cls.measurements=[]
        try:
            cls.db.sql('''CREATE ROLE vn_jup_parser_installer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
              CREATE ROLE vn_jup_parser_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
              GRANT CREATE ON DATABASE postgres TO vn_jup_parser_installer;''')
            refused=cls.db.sql(SQL.read_text(),role='vn_jup_parser_installer',check=False)
            if refused.returncode==0 or 'jupiter_raw_parser_offline_fixture_required' not in refused.stderr:
                raise AssertionError('Parser installed without opt-in marker')
            cls.db.sql("SET dashboard.jupiter_raw_parser_fixture='offline-v3'; BEGIN;"+SQL.read_text()+'COMMIT;',
                role='vn_jup_parser_installer',timeout=30)
            cls.db.sql('GRANT USAGE ON SCHEMA '+NS+' TO vn_jup_parser_reader; GRANT EXECUTE ON FUNCTION '+
                NS+'.parse_original_trio(bytea[],bytea[]) TO vn_jup_parser_reader;',role='vn_jup_parser_installer')
        except BaseException:
            cls.db.close();raise

    @classmethod
    def tearDownClass(cls):
        try:
            print('JUPITER_RAW_PARSER_V3_MEASUREMENTS '+json.dumps({'fixture':cls.db.identity,'sql_sha256':hashlib.sha256(SQL.read_bytes()).hexdigest(),
                'parser_policy_sha256':POLICY,'observations':cls.measurements,'admission_authority':False,'provider_acquisition':False},sort_keys=True))
        finally:cls.db.close()

    def query(self,requests,bodies):
        return 'SELECT '+NS+'.parse_original_trio('+array(requests)+','+array(bodies)+');'

    def accept(self,requests,bodies):
        expected=reference(requests,bodies);started=time.monotonic()
        wire=self.db.scalar(self.query(requests,bodies),role='vn_jup_parser_reader',timeout=30).encode()
        elapsed=time.monotonic()-started;result=json.loads(wire)
        self.assertEqual(wire,a.canonical(result));self.assertLessEqual(len(wire),8192)
        self.assertEqual(set(result),{'format','parser_policy_sha256','source_profile','asset','mint','decimals','denomination','valuation',
            'genesis_hash','price_decimal','block_ref','estimated_source_second','originals','authority'})
        self.assertEqual((result['price_decimal'],result['block_ref'],result['estimated_source_second']),expected)
        self.assertEqual(result['format'],'ga-jupiter-source-raw-parser-projection-research-v3')
        self.assertEqual(result['parser_policy_sha256'],POLICY);self.assertEqual(result['authority'],AUTHORITY)
        self.assertEqual(result['source_profile'],'jupiter-price-v3-prospective-minute-sampled-close-v1')
        self.assertEqual((result['asset'],result['mint'],result['decimals'],result['denomination'],result['valuation'],result['genesis_hash']),
            ('SOL/USD',a.MINT,'9','USD','reference_mark',a.GENESIS))
        for i,item in enumerate(result['originals']):
            self.assertEqual(item,{'provider_family':'jupiter-price-v3' if i==0 else 'solana-rpc',
                'request_sha256':hashlib.sha256(requests[i]).hexdigest(),'request_bytes':str(len(requests[i])),
                'response_sha256':hashlib.sha256(bodies[i]).hexdigest(),'response_bytes':str(len(bodies[i]))})
        return elapsed,len(wire)

    def reject(self,requests,bodies,*,reference_refusal=True):
        if reference_refusal:
            with self.assertRaises((ValueError,UnicodeError,KeyError,TypeError)):reference(requests,bodies)
        result=self.db.sql(self.query(requests,bodies),role='vn_jup_parser_reader',check=False,timeout=30)
        self.assertNotEqual(result.returncode,0);self.assertIn('jupiter_raw_parser_invalid',result.stderr)

    def generic(self,raw,*,maximum=131072,accept=True):
        expected=None
        if accept:expected=a.read_json(raw,maximum,numeric=True)
        else:
            with self.assertRaises(a.AcquisitionError):a.read_json(raw,maximum,numeric=True)
        result=self.db.sql('SELECT '+NS+'.read_json('+bytea(raw)+','+str(maximum)+',true);',role='vn_jup_parser_installer',check=False,timeout=30)
        self.assertEqual(result.returncode==0,accept,result.stderr)
        return expected

    def test_private_installation_no_tables_no_public_helpers(self):
        self.assertEqual(self.db.scalar("SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='"+NS+"';"),'0')
        rows=json.loads(self.db.scalar("SELECT json_agg(x) FROM (SELECT p.proname,p.prosecdef,p.provolatile,p.proconfig,r.rolname FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace JOIN pg_catalog.pg_roles r ON r.oid=p.proowner WHERE n.nspname='"+NS+"') x;"))
        self.assertTrue(rows);self.assertTrue(all(x['rolname']=='vn_jup_parser_installer' and x['proconfig']==['search_path=pg_catalog, pg_temp'] and x['provolatile']=='i' for x in rows))
        self.assertEqual([x['proname'] for x in rows if x['prosecdef']],['parse_original_trio'])
        for role in ('anon','authenticated','service_role'):
            result=self.db.sql(self.query(*packet()),role=role,check=False);self.assertNotEqual(result.returncode,0)
        for helper in ('require(true)','read_json(decode(\'7b7d\',\'hex\'),4096,true)'):
            result=self.db.sql('SELECT '+NS+'.'+helper+';',role='vn_jup_parser_reader',check=False);self.assertNotEqual(result.returncode,0)

    def test_minimal_full_and_original_whitespace_bytes(self):
        for body in (raw_price(),raw_price(priceChange24h=None,liquidity=120,createdAt='2026-10-13T12:34:56.123456Z'),
                b' \n'+raw_price()+b'\t '):
            self.accept(*packet(price=body))

    def test_exact_decimal_grid_bounds_and_lexical_forms(self):
        for token,expected in (('1.2300e2','123'),('1e-18','0.000000000000000001'),('1e36','1'+36*'0'),('0.00000100','0.000001')):
            self.assertEqual(reference(*packet(price=raw_price(token)))[0],expected);self.accept(*packet(price=raw_price(token)))
        for token in ('0','-0','-0.0','-1','1e-19','1.0000000000000000001','1e37','1e81','1e-81','0.'+'0'*80+'1e1'):
            with self.subTest(token=token):self.reject(*packet(price=raw_price(token)))

    def test_unsigned_integer_and_rpc_boundaries(self):
        self.accept(*packet(block=2**64-1,second=10_000_000_000,rpc_ids=(2**31-1,2**31-2)))
        self.accept(*packet(block=0,second=0))
        for token in ('true','"42"','42.0','42e0','-1','18446744073709551616','null'):
            self.reject(*packet(price=raw_price(block=token)))

    def test_boolean_decimal_integer_substitutions_across_fields(self):
        req,bodies=packet()
        for old,new,index in ((b'"decimals":9',b'"decimals":9.0',0),(b'"decimals":9',b'"decimals":true',0),
                (b'"id":1',b'"id":1.0',1),(b'1800000000',b'1800000000.0',2),(b'1800000000',b'true',2)):
            changed=list(bodies);changed[index]=changed[index].replace(old,new);self.reject(req,changed)

    def test_nullable_change_signed_unused_numbers_and_liquidity(self):
        for token in ('null','-0.0','-123.45','-1e80','0.'+'0'*78+'1e-80'):
            self.accept(*packet(price=raw_price().replace(b'"decimals":9',('"decimals":9,"priceChange24h":'+token).encode())))
        for token in ('true','"1"','[]','{}','1e81','-0'):
            self.reject(*packet(price=raw_price().replace(b'"decimals":9',('"decimals":9,"priceChange24h":'+token).encode())))
        for token in ('-0.0','-1','1e81','0.'+'0'*78+'1e-80'):
            self.reject(*packet(price=raw_price().replace(b'"decimals":9',('"decimals":9,"liquidity":'+token).encode())))

    def test_duplicate_decoded_keys_and_unused_nested_values(self):
        req,bodies=packet()
        for body in (b'{"jsonrpc":"2.0","id":2,"id":2,"result":1800000000}',
                b'{"jsonrpc":"2.0","id":2,"\\u0069d":2,"result":1800000000}'):
            self.reject(req,(*bodies[:2],body))
        for raw in (b'{"unused":{"a":1,"\\u0061":2}}',b'{"a":"\\u0000"}',b'{"unused":"\\ud800"}'):
            self.generic(raw,accept=False)

    def test_full_unicode_validation_and_depth_quote_scanner(self):
        for raw in (b'"\\ud83e\\udd89"','{"é":"🦉","é":"é","quoted":"[\\\"\\\\]"}'.encode(),b'{"x":"\\ud800\\udc00"}'):
            self.generic(raw)
        for raw in (b'\xef\xbb\xbf{}',b'"\xff"',b'"\\ud800"',b'"\\udc00"',b'"\\u0000"',b'{"x":NaN}',b'{} false'):
            self.generic(raw,accept=False)
        self.generic(b'['*32+b'null'+b']'*32);self.generic(b'['*33+b'null'+b']'*33,accept=False)

    def test_structural_members_arrays_and_node_budget(self):
        self.generic(a.canonical({str(i):None for i in range(1024)}));self.generic(a.canonical({str(i):None for i in range(1025)}),accept=False)
        self.generic(b'['+b','.join([b'null']*5000)+b']');self.generic(b'['+b','.join([b'null']*5001)+b']',accept=False)
        result=self.db.sql('SELECT '+NS+".walk('[null]',0,199999,true);",role='vn_jup_parser_installer',check=False)
        self.assertNotEqual(result.returncode,0)

    def test_numeric_lexeme_coefficient_exponent_boundaries(self):
        for raw in (b'9'*80,b'1e80',b'-1e-80',b'0.0',b'1e+'+b'0'*123+b'1'):
            self.generic(raw)
        for raw in (b'9'*81,b'1e81',b'1e-81',b'-0',b'1e'+b'0'*126+b'1'):
            self.generic(raw,accept=False)

    def test_requests_are_exact_canonical_public_originals(self):
        req,bodies=packet()
        for change in (lambda x:b' '+x,lambda x:x.replace(b'api.jup.ag',b'evil.example'),
                lambda x:x.replace(b'"chain":"solana"',b'"chain":"solana","unknown":false'),
                lambda x:x.replace(b'"chain":"solana"',b'"chain":"solana","\\u0063hain":"solana"')):
            changed=list(req);changed[0]=change(changed[0]);self.reject(changed,bodies)
        changed=list(req);changed[2]=a.public_request('solana-rpc',rpc_method='getBlockTime',rpc_id=2,slot=43);self.reject(changed,bodies)
        self.reject(*packet(rpc_ids=(1,1)),reference_refusal=False)

    def test_exact_source_identity_and_unknown_reply_fields(self):
        req,bodies=packet()
        for index,body in ((0,raw_price().replace(a.MINT.encode(),b'wrongMint')),(0,raw_price().replace(b'"blockId":42',b'"blockId":null')),
                (1,a.canonical({'jsonrpc':'2.0','id':1,'result':'devnet'})),(2,a.canonical({'jsonrpc':'2.0','id':2,'result':None})),
                (2,a.canonical({'jsonrpc':'2.0','id':2,'result':1800000000,'error':None}))):
            changed=list(bodies);changed[index]=body;self.reject(req,changed)

    def test_timestamp_actual_cpython_parity(self):
        dates=('2026-10-13','20261013','2026-W42-2','2026W422','2026-W42','2026W42',
            '2020-W53-7','2021-W53-1','2026-02-29','0000-01-01','9999-12-31')
        times=('12:34:56Z','123456+00','12+0000','12:34.5-00:00','12:34:56,1234567+00:00:00.5',
            '12x+00','12+00x','24:00+00','12:60+00','12:34:60+00','12:34+01','12:34','12:34:56+00:00:00.000001')
        samples=[d+'T'+t for d in dates for t in times]
        samples+=['2026-10-13'+sep+'12:34+00' for sep in (' ','🦉','1','-','Z')]
        self.db.sql('CREATE FUNCTION '+NS+'.timestamp_case(value json) RETURNS boolean LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$ BEGIN PERFORM '+NS+".created_at(value); RETURN true; EXCEPTION WHEN SQLSTATE '22023' THEN RETURN false; END $$;",role='vn_jup_parser_installer')
        expected=[]
        for stamp in samples:
            try:
                value=datetime.fromisoformat(stamp.replace('Z','+00:00'));okay=value.tzinfo is not None and value.utcoffset().total_seconds()==0
            except ValueError:okay=False
            expected.append('t' if okay else 'f')
        query=' UNION ALL '.join('SELECT '+str(i)+','+NS+'.timestamp_case('+bytea(a.canonical(stamp))+"::text::json)" for i,stamp in enumerate(samples))
        # bytea::text is hexadecimal, so use explicit UTF8 conversion instead.
        query=' UNION ALL '.join('SELECT '+str(i)+','+NS+'.timestamp_case(pg_catalog.convert_from('+bytea(a.canonical(stamp))+",'UTF8')::json)" for i,stamp in enumerate(samples))
        actual=self.db.scalar(query+' ORDER BY 1;',role='vn_jup_parser_installer',timeout=30).splitlines()
        self.assertEqual(actual,[str(i)+'|'+okay for i,okay in enumerate(expected)])
        for stamp in ('2026-W42-2🦉12:34:56Z','20261013T123456+00','2026-10-13T12:34:56+00:00:00.5'):
            self.accept(*packet(price=raw_price(createdAt=stamp)))

    def test_body_exact_cap_and_measured_traversal(self):
        req,bodies=packet();measurements=[]
        for i,limit in enumerate((131072,65536,65536)):
            changed=list(bodies);changed[i]=bodies[i]+b' '*(limit-len(bodies[i]));elapsed,size=self.accept(req,changed)
            measurements.append({'family_index':i,'body_bytes':len(changed[i]),'client_elapsed_seconds':elapsed,'projection_bytes':size})
            changed[i]+=b' ';self.reject(req,changed)
        self.measurements.extend(measurements)

    def test_private_helpers_and_temp_sentinel_cannot_change_parser(self):
        req,bodies=packet()
        source="CREATE TEMP VIEW pg_namespace AS SELECT 'sentinel'::text AS nspname; CREATE TEMP VIEW pg_proc AS SELECT 'sentinel'::text AS proname;"+self.query(req,bodies)
        result=json.loads(self.db.scalar(source,role='vn_jup_parser_reader'))
        self.assertEqual(result['price_decimal'],reference(req,bodies)[0]);self.assertEqual(result['authority'],AUTHORITY)

    def test_input_arrays_cannot_hide_or_omit_originals(self):
        req,bodies=packet()
        for source in ('NULL,'+array(bodies),array(req[:2])+','+array(bodies),array(req)+','+array(bodies)+( '||ARRAY[NULL]::bytea[]'),
                "'[0:2]={NULL,NULL,NULL}'::bytea[],"+array(bodies)):
            result=self.db.sql('SELECT '+NS+'.parse_original_trio('+source+');',role='vn_jup_parser_reader',check=False)
            self.assertNotEqual(result.returncode,0);self.assertIn('jupiter_raw_parser_invalid',result.stderr)
