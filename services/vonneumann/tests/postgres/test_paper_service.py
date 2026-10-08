"""HTTP → actual native TLS/SCRAM → full forward package → owner reads.

Only provider wire responses and HTTP authentication are synthetic. No cloud
credential, production environment, host port or external network is accessed.
"""
import asyncio
from copy import deepcopy
import json
import os
import time
import unittest
from uuid import uuid4
from tests.security_support import deny_network
from tests.postgres import harness,forward_fixture as fixture
from tests.postgres.test_command_adapter import literal,_RPC_PARAMETERS
from tests.postgres.test_provider_controller import LiteralProviderSession
with deny_network():
 import httpx
 from vonneumann.market.jupiter_feed import JupiterFeed
 from vonneumann.server.auth import VerifiedUser
 from vonneumann.server.paper_app import create_app
 from vonneumann.server.paper_service import PaperService

class NativePair:
 def __init__(self,db,pair):self.db,self.pair=db,pair;self.calls=[];self.drop=None;self.closed=False
 async def rpc(self,name,args):
  params=_RPC_PARAMETERS['acknowledge_event' if name=='accept_event' else name]
  schema='vn_read' if name=='accept_event' else 'vn_durability'
  values=[literal(json.dumps(args[k]) if cast=='jsonb' else args[k])+'::'+cast for k,cast in params]
  sql='SELECT '+schema+'.'+name+'('+','.join(values)+');'
  relay=name in ('accept_event','read_outbox','acknowledge_event')
  self.calls.append((name,deepcopy(args)))
  result=await asyncio.to_thread(self.db.native,self.pair.names[int(relay)],'relay' if relay else 'economic',sql)
  if self.drop==name:self.drop=None;raise ConnectionError('synthetic lost committed reply')
  return json.loads(result.stdout) if result.stdout.strip() else None
 async def accept_event(self,args):return await self.rpc('accept_event',args)
 async def aclose(self):self.closed=True

@unittest.skipUnless(os.environ.get(harness.OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class PaperFlowSqlTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):cls.db=fixture.start(cls)
 def setUp(self):
  self.ids=fixture.reset(self.db);fixture.install(self.db);fixture.transition(self.db,'open')
  self.run,self.epoch,self.start,self.stop=(str(uuid4()) for _ in range(4))
  pair=fixture.native_issuer_fixture.Pair.new(self.ids['owner'],self.run);self.db.issue_pair(pair)
  self.transport=NativePair(self.db,pair)
  self.feed=JupiterFeed(api_key='offline-only',birdeye_api_key='offline-only',rpc_url='https://controller-fixture.invalid/rpc')
  self.feed._session=LiteralProviderSession();self.feed._candles._session=LiteralProviderSession(candles=True)
  self.service=PaperService(self.transport,self.transport,self.feed,owner_id=self.ids['owner'],run_id=self.run,
    epoch_id=self.epoch,start_id=self.start,stop_id=self.stop,max_ticks=1,interval=1)
 async def asyncTearDown(self):await self.service.close()
 def owner_sql(self,sql,owner=None):
  return self.db.sql("SET request.jwt.claims="+literal(json.dumps({'sub':owner or self.ids['owner'],'role':'authenticated'}))+"; "+sql,role='authenticated')
 async def wait(self):
  await asyncio.wait_for(asyncio.shield(self.service._task),20)
 async def test_http_start_full_native_projection_relay_stop_discovery_archive(self):
  async def user():return VerifiedUser(self.ids['owner'],int(time.time())+300)
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.service,verify=user)),base_url='https://paper.invalid') as client:
   for _ in range(2):self.assertEqual((await client.post('/v5/start',json={'request_id':self.start})).status_code,202)
   await self.wait();s=(await client.get('/v5/status')).json()
  self.assertEqual(s['phase'],'stopped',s)
  self.assertEqual(sum(n=='create_run' for n,_ in self.transport.calls),1)
  state=json.loads(self.db.sql("SELECT engine_state FROM vn_durability.runs WHERE id='"+self.run+"';",role=fixture.ADMIN).stdout)
  self.assertEqual(state['status'],'stopped');self.assertEqual(len(state['accounts']),8)
  directory=json.loads(self.owner_sql('SELECT vn_read.discover();').stdout)
  self.assertEqual(directory['records'][0]['run_id'],self.run)
  self.assertEqual(json.loads(self.owner_sql('SELECT vn_read.discover();',self.ids['other']).stdout)['records'],[])
  page=json.loads(self.owner_sql("SELECT vn_read.page('"+self.run+"','probes');").stdout)
  self.assertGreaterEqual(len(page['records']),8)
  events=json.loads(self.owner_sql("SELECT vn_read.events('"+self.run+"');").stdout)
  self.assertTrue(events['records']);self.assertEqual([e['sequence'] for e in events['records']],list(range(1,len(events['records'])+1)))
  request=str(uuid4());receipt=json.loads(self.owner_sql("SELECT vn_read.archive_run('"+self.run+"',"+str(s['revision'])+",'"+request+"');").stdout)
  self.assertTrue(receipt['archived']);self.assertEqual(receipt['run_id'],self.run)
  self.assertEqual(json.loads(self.owner_sql('SELECT vn_read.discover();').stdout)['records'][0]['archive_receipt'],receipt)
  fixture.transition(self.db,'retired',1)
  self.assertEqual(json.loads(self.owner_sql('SELECT vn_read.discover();').stdout)['records'][0]['archive_receipt'],receipt)
 async def test_lost_create_reply_original_settlement_and_restart_refusal(self):
  self.transport.drop='create_run';self.service.start(self.ids['owner'],self.start);await self.wait()
  self.assertEqual(self.service.status(self.ids['owner'])['phase'],'pending')
  self.service.settle(self.ids['owner'],self.start);await self.wait()
  self.assertEqual(self.service.status(self.ids['owner'])['phase'],'stopped')
  self.assertEqual(sum(n=='create_run' for n,_ in self.transport.calls),1)
  other=PaperService(self.transport,self.transport,self.feed,owner_id=self.ids['owner'],run_id=self.run,
   epoch_id=self.epoch,start_id=self.start,stop_id=self.stop,max_ticks=1,interval=1)
  other.start(self.ids['owner'],self.start);await asyncio.wait_for(other._task,5)
  self.assertEqual(other.status(self.ids['owner'])['phase'],'pending')
  other.settle(self.ids['owner'],self.start);await asyncio.wait_for(other._task,5)
  self.assertEqual(other.status(self.ids['owner'])['phase'],'pending')
  self.assertEqual(other.repository.revision,0);self.assertIsNone(other.runner)
  self.assertEqual(sum(n=='create_run' for n,_ in self.transport.calls),2)
  count=self.db.sql("SELECT count(*) FROM vn_durability.commands WHERE run_id='"+self.run+"' AND kind='create';",role=fixture.ADMIN).stdout.strip()
  self.assertEqual(count,'1')
