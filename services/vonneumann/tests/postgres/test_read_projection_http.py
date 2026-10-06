"""Local PostgREST 14.5 command-to-projection-to-owner-reader/relay proof."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
from tests.postgres.harness import OPT_IN
from tests.postgres.http_harness import IsolatedPostgREST, fixture_jwt
from tests.postgres import test_command_http_postgrest as command_http_tests
from tests.test_command_http import FAKE_KEY
from vonneumann.db.command_http import DashboardCommandHTTPTransport
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandRepository
from vonneumann.db.relay_acceptance import DurableRelayPublisher


class ProjectionHTTPFixture(IsolatedPostgREST):
    api_schemas = ('vn_durability', 'vn_read')

    def apply_contract(self):
        super().apply_contract()
        sql = Path(__file__).resolve().parents[2] / 'db-contract' / '002_read_projections.sql'
        self.sql("SET dashboard.contract_rehearsal='db03a1-isolated';\n" + sql.read_text(), timeout=30)


class ReadProjectionHTTPTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get(OPT_IN) != '1':
            raise unittest.SkipTest('Requires isolated PostgreSQL opt-in')
        cls.db = ProjectionHTTPFixture()
        cls.addClassCleanup(cls.db.close)
        cls.db.start()

    async def asyncSetUp(self):
        self.owner, self.other, self.run, self.worker = (str(uuid4()) for _ in range(4))
        self.db.sql(f"INSERT INTO auth.users VALUES('{self.owner}'),('{self.other}');")
        self.client = httpx.AsyncClient(trust_env=False, timeout=3)
        self.transports = []

    async def asyncTearDown(self):
        for transport in self.transports: await transport.aclose()
        await self.client.aclose()

    async def raw(self, name, args, role='authenticated', owner=None):
        headers = {'Content-Profile':'vn_read', 'Accept-Profile':'vn_read'}
        if role is not None: headers['Authorization'] = 'Bearer ' + fixture_jwt(role, owner or self.owner)
        return await self.client.post(self.db.endpoint + '/rpc/' + name, json=args, headers=headers)

    def transport(self):
        with patch('httpx.AsyncHTTPTransport', lambda **kw: command_http_tests.PostgrestRoute(self.db.endpoint, **kw)):
            transport = DashboardCommandHTTPTransport(FAKE_KEY, self.owner)
        self.transports.append(transport)
        return transport

    async def accept_event(self, arguments):
        response = await self.raw('accept_event', arguments, role='service_role')
        response.raise_for_status()
        return response.json()

    async def test_v5_controller_to_atomic_history_durable_relay_and_owner_read(self):
        from tests.postgres.test_provider_controller import LiteralProviderSession
        from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
        from vonneumann.core.provider_lifecycle import ProviderLifecycleConfig
        from vonneumann.core.provider_controller import CommandAllocation, ProviderPilotController
        from vonneumann.db.provider_pilot_owner import ProviderPilotOwner
        from vonneumann.market.jupiter_feed import JupiterFeed
        identity = lambda: str(uuid4())
        config = ProviderLifecycleConfig(ExactLifecycleConfig('genetic_algorithm', self.owner, self.run, asset='SOL/USD'), identity())
        transport = self.transport()
        repository = CommandRepository(transport, self.owner, self.run, self.worker)
        await repository.submit(PreparedCommand.create(self.owner, self.run, self.worker,
            config.run_configuration(), config.initial_cash, lease_seconds=120))
        owner = ProviderPilotOwner(repository, transport, config, stop_command_id=identity())
        feed = JupiterFeed(api_key='local-fixture-only', rpc_url='https://controller-fixture.invalid/rpc', birdeye_api_key='local-fixture-only')
        feed._session = LiteralProviderSession(); feed._candles._session = LiteralProviderSession(candles=True)
        def allocate(kind, generation):
            return CommandAllocation(identity(),tuple(identity() for _ in range(9)),
                tuple((generation,f'Read-{generation}-{index}') for index in range(8)))
        publisher = DurableRelayPublisher(self, self.owner, self.run)
        controller = ProviderPilotController(owner, feed, publisher, allocate, lease_seconds=120)
        try:
            await controller.heartbeat()
            self.assertEqual((await controller.bootstrap()).status, 'complete')
            deadline = asyncio.get_running_loop().time() + 8
            while True:
                report = await controller.tick()
                if report.status == 'complete': break
                self.assertEqual(report.status, 'deferred')
                self.assertLess(asyncio.get_running_loop().time(), deadline)
                await asyncio.sleep(.05)
            self.assertEqual((await controller.stop()).status, 'complete')
            final = owner.installed_state.to_dict()
            self.assertEqual(json.loads(self.db.scalar(f"SELECT engine_state FROM vn_durability.runs WHERE id='{self.run}';")), final)
            response = await self.raw('page', {'run':self.run,'kind':'runs'})
            self.assertEqual(response.status_code,200)
            latest = response.json()['records'][-1]
            self.assertEqual(latest['revision'],final['revision'])
            self.assertEqual(latest['data']['status'],'stopped')
            self.assertEqual(latest['data']['mode'],'paper')
            self.assertEqual(latest['data']['account_currency'],'USD')
            self.assertNotIn('optimizer',response.text)
            probes = (await self.raw('page',{'run':self.run,'kind':'probes'})).json()
            self.assertEqual(len({r['key'] for r in probes['records']}),8)
            events = (await self.raw('events',{'run':self.run})).json()
            self.assertTrue(events['records'])
            ids = [r['data']['event_id'] for r in events['records']]
            self.assertEqual(len(ids),len(set(ids)))
            outbox = await transport.rpc('read_outbox',{'owner_id':self.owner,'run':self.run,
                'through_revision':final['revision'],'max_events':100,'max_bytes':65536})
            self.assertEqual(outbox['events'],[])
            archive = await self.raw('archive_run',{'run':self.run,'expected_revision':final['revision'],'request_id':identity()})
            self.assertEqual(archive.status_code,200,archive.json())
            self.assertTrue(archive.json()['archived'])
        finally:
            controller.close_admission()
            await feed.close()

    async def test_two_owners_anonymous_and_privileged_read_denial(self):
        from tests.lifecycle_fixtures import lifecycle_trace
        from tests.postgres.test_decimal_lineage_contract import document
        from tests.postgres.test_command_adapter import literal
        config, candidates = lifecycle_trace('pause_stop',owner_id=self.owner,run_id=self.run)
        command = str(uuid4())
        self.db.sql('SELECT vn_durability.create_run(' + ','.join((literal(self.owner),literal(self.run),
            literal(self.worker),literal(command),document(config.run_configuration()),literal(config.initial_cash),'120')) + ');',role='service_role')
        for role in (None,'anon','service_role'):
            response = await self.raw('page',{'run':self.run,'kind':'runs'},role=role)
            self.assertIn(response.status_code,(401,403,404))
        response = await self.raw('page',{'run':self.run,'kind':'runs'},owner=self.other)
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.json()['message'],'run_unavailable')
        self.assertEqual((await self.raw('page',{'run':self.run,'kind':'runs'})).status_code,200)
        for schema,table in (('vn_durability','commands'),('vn_read','probes'),('vn_projection','probes')):
            headers={'Accept-Profile':schema,'Authorization':'Bearer '+fixture_jwt('authenticated',self.owner)}
            response=await self.client.get(self.db.endpoint+'/'+table,headers=headers)
            self.assertIn(response.status_code,(403,404,406))
        response = await self.raw('archive_run',{'run':self.run,'expected_revision':1,'request_id':str(uuid4())})
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.json()['message'],'archive_unavailable')
