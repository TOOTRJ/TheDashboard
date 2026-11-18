"""Owned research proof of exact reservation/capture durability and no recollection."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import unittest

from tests.postgres.harness import IsolatedPostgres, OPT_IN
from vonneumann.market import provider_acquisition_v3 as acquisition, source_admission_v3 as source

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT/'db-contract/research/jupiter_durable_acquisition_fixture_v3.sql'
WIRES = ROOT/'tests/postgres/durable_acquisition_fixture_v3.json'
WIRES_SHA = '58d13f9dc8e9c2175013d4b22154dd98f6aaa7d2b5131da3ad506e7d4e44d34e'
RECORDER = 'dcap_recorder'
READER = 'dcap_reader'
FOREIGN = 'dcap_foreign'


def fixed(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def quote(text):
    fixed(type(text) is str and '\x00' not in text,'invalid fixture input')
    return "'"+text.replace("'","''")+"'"


def read(row, kind):
    return source.wire(row,kind)


class Packet:
    def __init__(self,row):
        self.reservation=read(row['reservation_wire'],'Reservation')
        self.prepared_wire=row['prepared_wire']
        self.capture=read(row['capture_wire'],'Capture') if 'capture_wire' in row else None
        self.expected=self.reservation.to_dict()
        self.scope=acquisition.canonical(self.expected['scope']).decode()
        self.availability_id=acquisition.uuid(row['availability_id'])
        self.closure_id=acquisition.uuid(row['closure_id'])
        self.raw_bodies=self.verify_capture(self.capture) if self.capture is not None else None

    def reservation_only(self):
        return Packet({'reservation_wire':self.reservation.wire.decode(),'prepared_wire':self.prepared_wire,
                       'availability_id':self.availability_id,'closure_id':self.closure_id})

    def verify_capture(self, capture):
        source.validate_capture(self.reservation,capture)
        issuer=source.issuer(self.expected['issuer'])
        return tuple(acquisition.decode_capsule(item.encode(),issuer).raw_body
                     for item in capture.to_dict()['capsule_wires'])

    @property
    def reserve_sql(self):
        args=(self.scope,self.reservation.wire.decode(),self.prepared_wire,self.availability_id,self.closure_id)
        return 'SELECT dcap.reserve('+','.join(map(quote,args))+');'

    def capture_sql(self, capture):
        args=(self.scope,self.expected['reservation_id'],capture.wire.decode())
        return 'SELECT dcap.capture('+','.join(map(quote,args))+');'

    def get_sql(self, kind, *, capture_sha=None, scope=None):
        args=(self.scope if scope is None else scope,kind,self.expected[kind+'_id'],self.reservation.sha256)
        return 'SELECT dcap.get_original('+','.join(map(quote,args))+','+(quote(capture_sha) if capture_sha else 'NULL')+');'

    def verify_get(self,row,kind,expected_capture_sha=None):
        if row=={'resolution':'observed_absent_unknown'}:
            return row
        fixed(set(row)=={'resolution','reservation_wire','prepared_wire','reservation_receipt_wire',
                         'capture_wire','capture_receipt_wire'} and row['resolution']=='original_committed',
              'unexpected fixture getter shape')
        fixed(row['reservation_wire']==self.reservation.wire.decode() and row['prepared_wire']==self.prepared_wire,
              'original reservation or plan changed')
        reserved=json.loads(row['reservation_receipt_wire'])
        fixed(acquisition.canonical(reserved).decode()==row['reservation_receipt_wire'] and reserved=={
            'kind':'fixture_reservation','scope':self.expected['scope'],'reservation_id':self.expected['reservation_id'],
            'reservation_sha256':self.reservation.sha256,'prepared_sha256':digest(self.prepared_wire),
            'availability_id':self.availability_id,'closure_id':self.closure_id},'reservation receipt mismatch')
        if kind=='reservation':
            fixed(row['capture_wire'] is None and row['capture_receipt_wire'] is None,'unexpected reservation capture')
            return row
        capture=read(row['capture_wire'],'Capture'); recorded=json.loads(row['capture_receipt_wire'])
        self.verify_capture(capture)
        fixed(expected_capture_sha is None or capture.sha256==expected_capture_sha,'expected capture hash changed')
        fixed(acquisition.canonical(recorded).decode()==row['capture_receipt_wire'] and recorded=={
            'kind':'fixture_capture','scope':self.expected['scope'],'capture_id':self.expected['capture_id'],
            'capture_sha256':capture.sha256,'reservation_sha256':self.reservation.sha256,'eligibility':False},
            'capture receipt mismatch')
        return row


class RecoveryReader:
    def __init__(self,db):
        self.db=db

    def reconcile(self,packet,kind,expected_capture_sha=None):
        row=json.loads(self.db.scalar(packet.get_sql(kind,capture_sha=expected_capture_sha),role=READER))
        return packet.verify_get(row,kind,expected_capture_sha)

    @property
    def cache_release_allowed(self):
        # This fixture owns no admission, availability or terminal closure.
        return False


class Recorder(RecoveryReader):
    """One ephemeral grant after acknowledged COMMIT and independent exact readback."""
    def __init__(self,db):
        super().__init__(db)
        self._permit=None
        self._attempted=False

    def prepare(self,packet):
        fixed(not self._attempted,'recorder already attempted a reservation')
        self._attempted=True
        # db.sql raises for a failed or missing transaction acknowledgment.
        receipt=json.loads(self.db.scalar('BEGIN;\n'+packet.reserve_sql+'\nCOMMIT;',role=RECORDER))
        fixed(set(receipt)=={'created','reservation_sha256'} and type(receipt['created']) is bool
              and receipt['reservation_sha256']==packet.reservation.sha256,'reservation write reply mismatch')
        if not receipt['created']:
            return None
        observed=self.reconcile(packet,'reservation')
        fixed(observed['resolution']=='original_committed','reservation is unresolved')
        permit=object(); self._permit=(permit,packet)
        return permit

    def collect_once(self,permit,collector):
        owned=self._permit
        fixed(owned is not None and permit is owned[0],'collection permit is unavailable')
        self._permit=None
        packet=owned[1]
        capture=collector(packet.prepared_wire)
        packet.verify_capture(capture)
        return capture

@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class DurableAcquisitionNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data=WIRES.read_bytes()
        fixed(hashlib.sha256(data).hexdigest()==WIRES_SHA,'held fixture hash changed')
        cls.packets=tuple(Packet(row) for row in json.loads(data))
        cls.db=IsolatedPostgres().start()
        cls.addClassCleanup(cls.db.close)
        cls.db.sql(SQL.read_text(),timeout=15)
        p=cls.packets[0]; e=p.expected
        cls.db.sql(f'''INSERT INTO dcap.scope_access VALUES ({quote(p.scope)},'{RECORDER}'::regrole::oid,
            '{READER}'::regrole::oid,{quote(acquisition.canonical(e['issuer']).decode())}::jsonb,
            {quote(acquisition.canonical(e['policies']).decode())}::jsonb,{quote(e['issuer_principal_binding_id'])});''')

    def setUp(self):
        self.db.sql('TRUNCATE dcap.identities, dcap.packets;')
        self.packet,self.other=self.packets
        self.calls=[]

    def collect(self,prepared):
        self.calls.append(digest(prepared))
        self.assertEqual(prepared,self.packet.prepared_wire)
        return self.packet.capture

    def refuse(self,statement,role,reason):
        reply=self.db.sql(statement,role=role,check=False)
        self.assertNotEqual(reply.returncode,0)
        self.assertEqual(reply.stdout,'')
        self.assertIn(reason,reply.stderr)

    def snapshot(self):
        return self.db.scalar("""SELECT jsonb_build_array(
          (SELECT jsonb_agg(to_jsonb(p) ORDER BY reservation_id) FROM dcap.packets p),
          (SELECT jsonb_agg(to_jsonb(i) ORDER BY original_id) FROM dcap.identities i));""")

    def start_capture(self,capture,committed):
        application='dashboard_dcap_'+('committed' if committed else 'provisional')
        wait_sql='SELECT pg_sleep(10);'
        first='SET application_name='+quote(application)+';\nBEGIN;\n'+self.packet.capture_sql(capture)+'\n'
        statement=(first+'COMMIT;\n'+wait_sql if committed else first+wait_sql+'\nCOMMIT;')
        session=self.db.begin_sql(statement,role=RECORDER,timeout=15)
        guard=(f"datname=current_database() AND usename='{RECORDER}' AND backend_type='client backend' "
               f"AND pid<>pg_backend_pid() AND application_name={quote(application)} AND wait_event='PgSleep' "
               "AND rtrim(btrim(query,E' \\t\\r\\n'),';')='SELECT pg_sleep(10)'")
        self.db.wait_until(f'SELECT count(*)=1 FROM pg_stat_activity WHERE {guard};',timeout=3)
        identity=json.loads(self.db.scalar(f'SELECT jsonb_build_array(pid,backend_start::text) FROM pg_stat_activity WHERE {guard};'))
        self.assertEqual(len(identity),2)
        pid,started=identity
        self.assertIs(type(pid),int); self.assertGreater(pid,0)
        exact=f"pid={pid} AND datname=current_database() AND usename='{RECORDER}' AND backend_type='client backend' AND backend_start={quote(started)}::timestamptz"
        return session,exact,guard

    def terminate(self,session,exact,guard):
        self.assertEqual('t',self.db.scalar(f'''SELECT coalesce((SELECT pg_terminate_backend(pid,2000)
          FROM pg_stat_activity WHERE {exact} AND {guard}),false);''',timeout=4))
        self.assertEqual('t',self.db.scalar(f'SELECT NOT EXISTS(SELECT 1 FROM pg_stat_activity WHERE {exact});'))
        self.assertNotEqual(0,session.wait(timeout=5,check=False).returncode)

    def check_reader_no_collection(self,packet):
        fresh=RecoveryReader(self.db); identity=packet.reservation_only()
        self.assertIsNone(identity.capture); self.assertIsNone(identity.raw_bodies)
        self.assertEqual(fresh.reconcile(identity,'reservation')['resolution'],'original_committed')
        self.assertFalse(hasattr(fresh,'prepare')); self.assertFalse(hasattr(fresh,'collect_once'))
        retry=Recorder(self.db)
        self.assertIsNone(retry.prepare(identity))  # Existing committed reservation supplies no new grant.
        with self.assertRaisesRegex(RuntimeError,'collection permit is unavailable'):
            retry.collect_once(None,self.collect)
        self.assertFalse(fresh.cache_release_allowed)
        self.assertEqual(len(self.calls),1)
        return fresh,identity

    def test_original_capture_commit_and_backend_loss_reconcile_without_recollection(self):
        packet=self.packet; recorder=Recorder(self.db)
        raw_reservation=packet.reservation.wire.decode()
        altered=packet.reservation.to_dict(); altered['extra']='not an allowed reservation field'
        self.refuse(packet.reserve_sql.replace(quote(raw_reservation),quote(acquisition.canonical(altered).decode())),
                    RECORDER,'dcap_reservation_shape')
        altered=packet.reservation.to_dict(); altered['authority']['running_authority']=True
        self.refuse(packet.reserve_sql.replace(quote(raw_reservation),quote(acquisition.canonical(altered).decode())),
                    RECORDER,'dcap_reservation_shape')
        self.refuse(packet.reserve_sql.replace(quote(packet.closure_id),quote(packet.availability_id)),
                    RECORDER,'dcap_identity_conflict')
        permit=recorder.prepare(packet)
        capture=recorder.collect_once(permit,self.collect)
        with self.assertRaisesRegex(RuntimeError,'collection permit is unavailable'):
            recorder.collect_once(permit,self.collect)
        capsule=json.loads(capture.to_dict()['capsule_wires'][0]); capsule['response_sha256']='0'*64
        altered=capture.to_dict(); altered['capsule_wires'][0]=acquisition.canonical(capsule).decode()
        wrong=source.envelope('Capture',altered)
        self.refuse(packet.capture_sql(wrong),RECORDER,'dcap_raw_conflict')
        altered=capture.to_dict(); altered['extra']='not an allowed capture field'
        self.refuse(packet.capture_sql(capture).replace(quote(capture.wire.decode()),quote(acquisition.canonical(altered).decode())),
                    RECORDER,'dcap_capture_shape')
        self.refuse(self.other.reserve_sql,RECORDER,'dcap_scope_unresolved')
        self.refuse(packet.reserve_sql,READER,'permission denied')
        self.refuse(packet.capture_sql(capture),READER,'permission denied')
        self.refuse(packet.get_sql('capture'),RECORDER,'permission denied')
        self.refuse(packet.get_sql('capture'),FOREIGN,'dcap_scope_refused')
        self.refuse(packet.get_sql('capture',scope='{}'),READER,'dcap_scope_refused')
        session,exact,guard=self.start_capture(capture,True)
        self.assertEqual('t',self.db.scalar(f'SELECT capture_sha256={quote(capture.sha256)} FROM dcap.packets;'))
        self.terminate(session,exact,guard)
        before=self.snapshot()
        fresh,identity=self.check_reader_no_collection(packet)
        recovered=fresh.reconcile(identity,'capture')  # No capture bytes or digest supplied to the reader.
        self.assertEqual(recovered['capture_wire'],capture.wire.decode())
        self.assertEqual(identity.verify_capture(read(recovered['capture_wire'],'Capture')),packet.raw_bodies)
        self.assertEqual(recovered,fresh.reconcile(identity,'capture',capture.sha256))
        self.refuse(packet.get_sql('capture',capture_sha='0'*64),READER,'dcap_lookup_conflict')
        self.assertEqual(before,self.snapshot())
        self.assertEqual(self.db.scalar('SELECT count(*) FROM dcap.identities;'),'9')
        self.assertFalse(fresh.cache_release_allowed)
        self.observation={'capture_committed':True,'exact_capture_sha256':capture.sha256,
            'exact_receipt_sha256':digest(recovered['capture_receipt_wire']),'raw_body_count':3,
            'collector_callback_count':len(self.calls),'backend_terminated':True,'cache_release_allowed':False}

    def test_provisional_capture_process_loss_remains_unknown_and_blocks_collection(self):
        packet=self.packet; recorder=Recorder(self.db)
        capture=recorder.collect_once(recorder.prepare(packet),self.collect)
        before=self.snapshot()
        session,exact,guard=self.start_capture(capture,False)
        self.assertEqual(recorder.reconcile(packet,'capture'),{'resolution':'observed_absent_unknown'})
        self.terminate(session,exact,guard)
        fresh,identity=self.check_reader_no_collection(packet)
        self.assertEqual(fresh.reconcile(identity,'capture'),{'resolution':'observed_absent_unknown'})
        self.refuse(self.other.reserve_sql,RECORDER,'dcap_scope_unresolved')
        self.assertEqual(before,self.snapshot())
        self.assertEqual(self.db.scalar('SELECT count(*) FROM dcap.identities;'),'9')
        self.observation={'capture_committed':False,'resolution':'observed_absent_unknown',
            'collector_callback_count':len(self.calls),'backend_terminated':True,'cache_release_allowed':False}
