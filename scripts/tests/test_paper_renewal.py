"""Finite-renewal lifecycle tests; no production files or endpoints are used."""
from datetime import datetime,timedelta,timezone
import importlib.util,json,os
from pathlib import Path
import sys,tempfile,unittest,threading
from uuid import uuid4
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
HERE=ROOT/'scripts'
spec=importlib.util.spec_from_file_location('dashboard_paper_renewal_tests',HERE/'dashboard_paper_renewal.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)


class Client:
    def __init__(self,initial,now):
        self.row={**r.identity(initial),'role_deadline':initial['valid_until'],
            'binding_deadline':initial['valid_until'],'db_now':now.isoformat(),
            'can_login':True,'restricted':True,'direct_rpc':True,'no_table_access':True}
        self.writes=0;self.new=None;self.lose=False;self.commit=True
    def verify(self):pass
    def query(self,sql,parameters=(),read_only=True):
        if read_only:return [dict(self.row)]
        self.writes+=1
        if self.commit:self.row.update(role_deadline=self.new,binding_deadline=self.new)
        if self.lose:raise TimeoutError()
        return []


class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name).resolve()
        self.now=datetime.now(timezone.utc)
        self.initial={'owner_id':str(uuid4()),'run_id':str(uuid4()),'db_login':'vn_paper_'+uuid4().hex,
            'role_oid':12345,'valid_until':(self.now+timedelta(hours=2)).isoformat(),
            'state':'issued_verified','db_password':'synthetic-original-unchanged'}
        self.path=self.folder/'credentials-original.json';r.private_write(self.path,self.initial)
        self.original=self.path.read_bytes();self.store=r.RenewalStore(self.path)
        self.client=Client(self.initial,self.now)
    def prepare(self,hours=3):
        self.client.new=(self.now+timedelta(hours=hours)).isoformat()
        return self.store.prepare(self.client,self.client.new)

    def test_lost_ack_reconciles_one_write_chain_and_closure_receipt_preserves_original(self):
        plan=self.prepare();self.client.lose=True
        result=self.store.apply(self.client,plan['operation_id'])
        self.assertEqual(result['state'],'committed_verified');self.assertEqual(self.client.writes,1)
        with self.assertRaises(r.RenewalRefused):self.store.apply(self.client,plan['operation_id'])
        effective=self.store.effective_record();self.assertEqual(effective['valid_until'],self.client.new)
        effective['state']='closed_verified';self.store.save_credential_status(effective)
        self.assertEqual(self.store.effective_record()['state'],'closed_verified')
        self.assertEqual(self.path.read_bytes(),self.original)
        sql=r.renew_sql(self.store.load(plan['operation_id']))
        self.assertNotIn('PASSWORD',sql);self.assertNotIn('GRANT ',sql)

    def test_absent_effect_stays_unresolved_and_blocks_retry_or_new_renewal(self):
        plan=self.prepare();self.client.lose=True;self.client.commit=False
        self.assertEqual(self.store.apply(self.client,plan['operation_id'])['state'],'unresolved')
        with self.assertRaises(r.RenewalRefused):self.store.apply(self.client,plan['operation_id'])
        with self.assertRaises(r.RenewalRefused):self.prepare(4)
        self.assertEqual(self.client.writes,1);self.assertEqual(self.path.read_bytes(),self.original)

    def test_expired_insufficient_headroom_and_over_seven_days_refuse(self):
        for changes,hours in (({'role_deadline':(self.now-timedelta(seconds=1)).isoformat()},3),
            ({'db_now':(self.now+timedelta(hours=1,minutes=50)).isoformat()},3),({},169),({},1)):
            original=dict(self.client.row);self.client.row.update(changes)
            with self.subTest(changes=changes,hours=hours),self.assertRaises(r.RenewalRefused):self.prepare(hours)
            self.client.row=original
        self.assertEqual(self.client.writes,0);self.assertFalse(self.store.folder.exists())

    def test_second_committed_extension_follows_chain_and_ignores_old_active_receipt(self):
        first=self.prepare();self.store.apply(self.client,first['operation_id'])
        self.store.save_credential_status(self.store.effective_record())
        second=self.prepare(4);self.store.apply(self.client,second['operation_id'])
        effective=self.store.effective_record()
        self.assertEqual(effective['valid_until'],self.client.new)
        self.assertEqual(effective['renewal_operation_id'],second['operation_id'])
        self.assertEqual(len(self.store.chain()[0]),2);self.assertEqual(self.path.read_bytes(),self.original)

    def test_wrong_oid_and_mutated_initial_original_refuse(self):
        self.client.row['role_oid']=12346
        with self.assertRaises(r.RenewalRefused):self.prepare()
        self.client.row['role_oid']=12345
        self.path.write_bytes(self.original+b' ')
        with self.assertRaises(r.RenewalRefused):self.prepare()

    def test_private_lock_bars_parallel_preparation(self):
        with self.store.exclusive():
            with self.assertRaises(r.RenewalRefused):self.prepare()
        self.assertFalse(self.store.folder.exists())

    def test_operator_verification_and_close_keep_initial_bytes(self):
        plan=self.prepare();self.store.apply(self.client,plan['operation_id'])
        spec=importlib.util.spec_from_file_location('renewal_operator_hooks',ROOT/'scripts/dashboard-paper-v6.py')
        operator=importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)
        row={'role_oid':self.initial['role_oid'],'binding_exact':True,'restricted':True,
            'role_deadline':True,'binding_deadline':True,'binding_active':True,'can_login':True,
            'no_memberships':True,'direct_rpc':True,'no_table_access':True}
        sql=[]
        def close(client,source,*args,**kwargs):
            sql.append(source);row.update(binding_active=False,can_login=False)
        with patch.object(operator,'CREDENTIAL_STATE',self.path),patch.object(operator,'_initial_credentials',return_value=dict(self.initial)),patch.object(operator,'_renewal_module',return_value=r),patch.object(operator,'_renewal_store',return_value=self.store),patch.object(operator,'_one',side_effect=lambda *args,**kwargs:dict(row)),patch.object(operator,'_query',side_effect=close):
            effective=operator._credentials()
            operator.verify_credentials(self.client,effective)
            operator.rollback(self.client)
            self.assertEqual(operator._credentials()['state'],'closed_verified')
        self.assertIn(self.client.new,sql[0]);self.assertNotIn(self.initial['valid_until'],sql[0])
        self.assertEqual(self.path.read_bytes(),self.original)

    def operator(self):
        spec=importlib.util.spec_from_file_location('renewal_operator_races',ROOT/'scripts/dashboard-paper-v6.py')
        operator=importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)
        return operator

    def test_first_prepare_serializes_verify_and_close_before_initial_freeze(self):
        operator=self.operator();entered,release=threading.Event(),threading.Event();errors=[]
        original_status=self.store.status
        def blocked_status(client):
            entered.set();self.assertTrue(release.wait(3));return original_status(client)
        def prepare():
            try:self.prepare()
            except BaseException as error:errors.append(error)
        with patch.object(operator,'CREDENTIAL_STATE',self.path),patch.object(operator,'_initial_credentials',return_value=dict(self.initial)),patch.object(operator,'_renewal_module',return_value=r),patch.object(operator,'_renewal_store',return_value=self.store),patch.object(self.store,'status',side_effect=blocked_status),patch.object(operator,'_one') as read_status,patch.object(operator,'_write') as rewrite,patch.object(operator,'_query') as close:
            thread=threading.Thread(target=prepare);thread.start()
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(r.RenewalRefused):operator.verify_credentials(self.client)
                with self.assertRaises(r.RenewalRefused):operator.rollback(self.client)
                read_status.assert_not_called();rewrite.assert_not_called();close.assert_not_called()
            finally:release.set();thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertEqual(self.store.originals()[0]['initial_sha256'],r.sha(self.original))

    def test_verify_status_read_is_locked_against_closure_and_stale_receipt_cannot_reopen(self):
        plan=self.prepare();self.store.apply(self.client,plan['operation_id'])
        operator=self.operator();entered,release=threading.Event(),threading.Event();errors=[]
        row={'role_oid':self.initial['role_oid'],'binding_exact':True,'restricted':True,
            'role_deadline':True,'binding_deadline':True,'binding_active':True,'can_login':True,
            'no_memberships':True,'direct_rpc':True,'no_table_access':True}
        block=[True];closed=[False]
        def native_status(*args,**kwargs):
            if block[0]:entered.set();self.assertTrue(release.wait(3))
            return dict(row)
        def native_close(*args,**kwargs):closed[0]=True;row.update(binding_active=False,can_login=False)
        stale=self.store.effective_record()
        def verify():
            try:operator.verify_credentials(self.client,stale)
            except BaseException as error:errors.append(error)
        with patch.object(operator,'CREDENTIAL_STATE',self.path),patch.object(operator,'_initial_credentials',return_value=dict(self.initial)),patch.object(operator,'_renewal_module',return_value=r),patch.object(operator,'_renewal_store',return_value=self.store),patch.object(operator,'_one',side_effect=native_status),patch.object(operator,'_query',side_effect=native_close):
            thread=threading.Thread(target=verify);thread.start()
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(r.RenewalRefused):operator.rollback(self.client)
                self.assertFalse(closed[0])
            finally:release.set();thread.join(3)
            self.assertEqual(errors,[]);block[0]=False
            operator.rollback(self.client)
            self.assertTrue(closed[0])
            with self.assertRaises(operator.Refused):operator.verify_credentials(self.client,stale)
            with self.assertRaises(r.RenewalRefused):self.store.save_credential_status(stale)
        self.assertEqual(self.store.effective_record()['state'],'closed_verified')
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_old_pair_unresolved_can_still_close_without_renewal_retry(self):
        plan=self.prepare();self.client.lose=True;self.client.commit=False
        self.store.apply(self.client,plan['operation_id']);operator=self.operator()
        row={'role_oid':self.initial['role_oid'],'binding_exact':True,'restricted':True,
            'role_deadline':True,'binding_deadline':True,'binding_active':True,'can_login':True,
            'no_memberships':True,'direct_rpc':True,'no_table_access':True}
        def close(*args,**kwargs):row.update(binding_active=False,can_login=False)
        with patch.object(operator,'CREDENTIAL_STATE',self.path),patch.object(operator,'_initial_credentials',return_value=dict(self.initial)),patch.object(operator,'_renewal_module',return_value=r),patch.object(operator,'_renewal_store',return_value=self.store),patch.object(operator,'_one',side_effect=lambda *args,**kwargs:dict(row)),patch.object(operator,'_query',side_effect=close) as write:
            operator.rollback(self.client);write.assert_called_once()
            self.assertIn(self.initial['valid_until'],write.call_args.args[1])
        self.assertEqual(self.store.effective_record()['state'],'closed_verified')
        self.assertEqual(self.store.load(plan['operation_id'])['state'],'unresolved')

    def test_readonly_permission_drift_refuses_before_creating_renewal(self):
        for field in ('restricted','direct_rpc','no_table_access'):
            self.client.row[field]=False
            with self.subTest(field=field),self.assertRaises(r.RenewalRefused):self.prepare()
            self.client.row[field]=True
        self.assertFalse(self.store.folder.exists());self.assertEqual(self.client.writes,0)

    def test_close_intent_bars_prepared_or_new_renewal_even_if_native_login_is_still_active(self):
        plan=self.prepare()
        pending=self.store.effective_record();pending['state']='close_submitted_or_uncertain'
        self.store.save_credential_status(pending)
        with self.assertRaises(r.RenewalRefused):self.store.apply(self.client,plan['operation_id'])
        with self.assertRaises(r.RenewalRefused):self.prepare(4)
        self.assertEqual(self.client.writes,0)


if __name__=='__main__':unittest.main()
