"""HTTP identity and retained one-run admission, with no cloud/provider I/O."""
import asyncio
import json
import os
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from tests.security_support import OfflineTestMixin, USER_A, USER_B, deny_network, token_for
with deny_network():
 import httpx
 from vonneumann.server.auth import VerifiedUser
 from vonneumann.server import paper_app
 from vonneumann.server.paper_service import PaperService, ServiceRefused

class HeldTransport:
 def __init__(self):
  self.entered,self.release=asyncio.Event(),asyncio.Event();self.calls=[];self.closed=False
 async def rpc(self,name,args):
  self.calls.append((name,args));self.entered.set();await self.release.wait()
  raise ConnectionError('synthetic-secret-must-not-leak')
 async def aclose(self):self.closed=True

class Feed:
 def __init__(self):self.closed=False
 async def close(self):self.closed=True

class PaperServiceTests(OfflineTestMixin,unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  super().setUp();self.transport=HeldTransport();self.feed=Feed()
  self.start,self.stop,self.run=(str(uuid4()) for _ in range(3))
  self.service=PaperService(self.transport,self.transport,self.feed,owner_id=USER_A,
    run_id=self.run,epoch_id=str(uuid4()),start_id=self.start,stop_id=self.stop)
 async def asyncTearDown(self):
  self.transport.release.set();await self.service.close()
 async def test_repeated_start_has_one_retained_task_before_first_await(self):
  a=self.service.start(USER_A,self.start);b=self.service.start(USER_A,self.start)
  self.assertEqual(a['phase'],'starting');self.assertEqual(a,b)
  await self.transport.entered.wait();self.assertEqual(len(self.transport.calls),1)
  self.assertEqual(self.transport.calls[0][0],'create_run')
  with self.assertRaises(ServiceRefused):self.service.start(USER_A,str(uuid4()))
 async def test_other_owner_cannot_read_control_or_settle(self):
  for name,args in [('status',()),('start',(self.start,)),('stop',(self.stop,)),('settle',(self.start,))]:
   with self.subTest(name=name),self.assertRaises(ServiceRefused):getattr(self.service,name)(USER_B,*args)
  self.assertEqual(self.transport.calls,[])
 async def test_stop_before_start_admits_no_create(self):
  self.service.stop(USER_A,self.stop);self.service.start(USER_A,self.start)
  await asyncio.sleep(0);self.assertEqual(self.transport.calls,[])
 async def test_safe_error_status_and_owned_cleanup(self):
  self.service.start(USER_A,self.start);await self.transport.entered.wait()
  self.transport.release.set();await self.service._task
  result=self.service.status(USER_A)
  self.assertEqual(result['phase'],'pending');self.assertTrue(result['requires_reconciliation'])
  self.assertNotIn('synthetic-secret',json.dumps(result));await self.service.close()
  self.assertTrue(self.transport.closed);self.assertTrue(self.feed.closed)
 async def test_closed_selection_and_private_configuration_fail_without_reads(self):
  with patch.dict(os.environ,{'VN_SERVICE_MODE':'closed'},clear=True):self.assertIsNone(paper_app.configured_service())
  with patch.dict(os.environ,{'VN_SERVICE_MODE':'paper-v5'},clear=True),self.assertRaisesRegex(RuntimeError,'explicit_private'):
   paper_app.configured_service()
  self.assertEqual(self.transport.calls,[])
 async def test_production_cadence_and_consumer_inventory_reject_before_native_construction(self):
  environment={'VN_SERVICE_MODE':'paper-v5','PYTHON_DOTENV_DISABLED':'1',
    'VN_ENVIRONMENT':'production','SUPABASE_URL':'https://fxpxsciltakyypunglzr.supabase.co',
    'VN_ALLOWED_ORIGINS':paper_app.ORIGIN,'SUPABASE_PUBLISHABLE_KEY':'sb_publishable_offline_only',
    'VN_JUPITER_SOLE_CONSUMER':'1','VN_PAPER_INTERVAL_SECONDS':'4'}
  with patch('vonneumann.db.command_sql.DashboardCommandSQLPair') as pair:
   with self.assertRaisesRegex(RuntimeError,'invalid_private'):
    paper_app.configured_service(environment)
   pair.assert_not_called()
   environment.update(VN_PAPER_INTERVAL_SECONDS='5',VN_JUPITER_SOLE_CONSUMER='0')
   with self.assertRaisesRegex(RuntimeError,'explicit_private'):
    paper_app.configured_service(environment)
   pair.assert_not_called()
 async def test_http_auth_owner_origin_and_body_shape(self):
  async def user():return VerifiedUser(USER_A,int(time.time())+300)
  app=paper_app.create_app(self.service,verify=user)
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://paper.invalid') as client:
   self.assertEqual((await client.get('/health')).status_code,200)
   rejected=await client.get('/v5/status',headers={'Origin':'https://evil.invalid'})
   self.assertEqual(rejected.status_code,403)
   self.assertEqual(rejected.headers.get('cache-control'),'no-store')
   r=await client.get('/v5/controls');self.assertEqual(r.json()['start_id'],self.start)
   for payload in [{'request_id':self.start,'mode':'live'},{'request_id':str(uuid4())}]:
    self.assertIn((await client.post('/v5/start',json=payload)).status_code,(409,422))
   self.assertEqual((await client.post('/v5/start',content='{"request_id":"'+self.start+'","request_id":"'+self.start+'"}',headers={'Content-Type':'application/json'})).status_code,422)
   self.assertEqual((await client.post('/v5/start',content='x'*257,headers={'Content-Type':'application/json'})).status_code,413)
   self.assertEqual((await client.post('/v5/start',json={'request_id':self.start})).status_code,202)
   self.assertEqual((await client.post('/v5/start',json={'request_id':self.start})).status_code,202)
  async def other():return VerifiedUser(USER_B,int(time.time())+300)
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=paper_app.create_app(self.service,verify=other)),base_url='https://paper.invalid') as client:
   for path in ['/v5/status','/v5/controls']:
    self.assertEqual((await client.get(path)).status_code,404)
   for path in ['/v5/start','/v5/stop','/v5/settle']:
    self.assertEqual((await client.post(path,json={'request_id':self.start})).status_code,404)
 async def test_unauthenticated_closed_app_exposes_only_liveness(self):
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=paper_app.create_app()),base_url='https://paper.invalid') as client:
   self.assertEqual((await client.get('/v5/status')).status_code,401)
   self.assertEqual((await client.get('/docs')).status_code,404)
