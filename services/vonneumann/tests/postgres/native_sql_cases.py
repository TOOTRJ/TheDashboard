"""Actual driver cases, run only inside the owned offline Linux fixture.

The only patched connection behavior is DNS resolution to the fixture loopback.
TLS hostname, CA, SCRAM channel binding, SQL, roles, transactions and controller
are real. Fault hooks act before/after a real COMMIT, never replace the driver.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import sys
import time
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import psycopg
from psycopg import sql
from tests.postgres.test_provider_controller import LiteralProviderSession
from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
from vonneumann.core.provider_lifecycle import ProviderLifecycleConfig
from vonneumann.core.provider_controller import CommandAllocation, ProviderPilotController
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandRepository, UncertainCommand, CommandAdmissionError
from vonneumann.db.command_sql import DashboardCommandSQLPair, DashboardCommandSQLTransport, CommandSQLBounds, CommandSQLError, HOST, paper_sql_bounds
from vonneumann.db.provider_pilot_owner import ProviderPilotOwner
from vonneumann.db.relay_acceptance import DurableRelayPublisher
from vonneumann.market.jupiter_feed import JupiterFeed


def identity(): return str(uuid4())


class ActualNativeSQLTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        print('Actual Linux driver: psycopg='+psycopg.__version__+'; implementation='+
              psycopg.pq.__impl__+'; libpq='+str(psycopg.pq.version()),file=sys.stderr)

    async def admin_connect(self):
        return await psycopg.AsyncConnection.connect('',host=HOST,hostaddr='127.0.0.1',port=5432,
            dbname='postgres',user='vn_test_admin',password=self.fixture['admin_password'],
            sslmode='verify-full',sslrootcert='/tmp/driver/root.crt',sslcertmode='disable',
            require_auth='scram-sha-256',channel_binding='require',connect_timeout=2,
            autocommit=True,prepare_threshold=None)

    async def issue(self,capability):
        login='vn_native_'+uuid4().hex
        password=secrets.token_hex(32)
        until=(datetime.now(timezone.utc)+timedelta(seconds=600)).isoformat()
        query=sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION '
            'NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD {} VALID UNTIL {}').format(
                sql.Identifier(login),sql.Literal(password),sql.Literal(until))
        await self.admin.execute(query,prepare=False)
        await self.admin.execute(sql.SQL('GRANT {} TO {} WITH ADMIN FALSE,INHERIT FALSE,SET TRUE').format(
            sql.Identifier('vn_'+capability),sql.Identifier(login)),prepare=False)
        await self.admin.execute("INSERT INTO vn_access.bindings "
            "(issuance_id,principal_oid,principal_name,capability,owner_id,run_id,issued_at,not_before,expires_at,recovery_until) "
            "WITH stamp AS MATERIALIZED (SELECT clock_timestamp() AS at) "
            "SELECT %s::uuid,oid,rolname,%s,%s::uuid,%s::uuid,at,at,at+interval '300 seconds',%s::timestamptz "
            "FROM pg_roles,stamp WHERE rolname=%s",
            (identity(),capability,self.owner_id,self.run_id,until,login),prepare=False)
        return login,password

    async def asyncSetUp(self):
        # This fixed tmpfs marker is staged solely by NativeDriverContainer.
        self.fixture=json.loads(Path('/tmp/driver/fixture.json').read_text())
        self.ca=self.fixture['ca'].encode()
        ca=Path('/tmp/driver/root.crt'); ca.write_bytes(self.ca); ca.chmod(0o600)
        self.admin=await self.admin_connect()
        self.owner_id,self.run_id,self.worker_id=identity(),identity(),identity()
        await self.admin.execute('INSERT INTO auth.users(id) VALUES (%s::uuid)',(self.owner_id,))
        self.economic=await self.issue('economic')
        self.relay=await self.issue('relay')
        self.dns=patch.object(DashboardCommandSQLTransport,'_resolve',AsyncMock(return_value='127.0.0.1'))
        self.dns.start()
        self.addCleanup(self.dns.stop)
        self.pair=self.make_pair()
        self.repository=CommandRepository(self.pair,self.owner_id,self.run_id,self.worker_id)
        self.config=ProviderLifecycleConfig(ExactLifecycleConfig('genetic_algorithm',self.owner_id,
                                            self.run_id,asset='SOL/USD'),identity())
        self.feed=None
        self.extra=[]

    def make_pair(self,**options):
        return DashboardCommandSQLPair(*self.economic,*self.relay,self.ca,self.owner_id,self.run_id,**options)

    async def asyncTearDown(self):
        if self.feed is not None: await self.feed.close()
        await self.pair.aclose()
        for transport in self.extra: await transport.aclose()
        await self.admin.close()
        self.assertFalse(self.pair._economic._io_tasks)
        self.assertFalse(self.pair._relay._io_tasks)

    async def scalar(self,query,params=()):
        cursor=await self.admin.execute(query,params,prepare=False)
        return (await cursor.fetchone())[0]

    def create(self):
        return PreparedCommand.create(self.owner_id,self.run_id,self.worker_id,
            self.config.run_configuration(),self.config.initial_cash,command_id=identity(),lease_seconds=120)

    async def journal_count(self):
        return await self.scalar('SELECT count(*) FROM vn_durability.commands WHERE run_id=%s::uuid',(self.run_id,))

    async def controller(self):
        await self.repository.submit(self.create())
        self.feed=JupiterFeed(api_key='synthetic-native-fixture',
            rpc_url='https://controller-fixture.invalid/rpc',birdeye_api_key='synthetic-native-fixture')
        self.feed._session=LiteralProviderSession()
        self.feed._candles._session=LiteralProviderSession(candles=True)
        owner=ProviderPilotOwner(self.repository,self.pair,self.config,stop_command_id=identity())
        publisher=DurableRelayPublisher(self.pair,self.owner_id,self.run_id)
        def allocate(kind,generation):
            return CommandAllocation(identity(),tuple(identity() for _ in range(9)),
                tuple((generation,f'Native-{generation}-{i}') for i in range(8)))
        controller=ProviderPilotController(owner,self.feed,publisher,allocate,lease_seconds=120)
        await controller.heartbeat()
        return owner,controller

    async def test_controller_bootstrap_tick_pause_stop_and_real_relay(self):
        owner,controller=await self.controller()
        report=await controller.bootstrap()
        self.assertEqual((report.status,report.revision),('complete',2))
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            report=await controller.tick()
            if report.status=='complete': break
            self.assertEqual(report.status,'deferred')
            await asyncio.sleep(.05)
        self.assertEqual((report.status,report.quote_sequence),('complete',1))
        self.assertEqual(owner.installed_state.to_dict()['source']['last_quote']['quote']['price'],
                         '100.000000000000000001')
        self.assertEqual((await controller.control('pause')).status,'complete')
        self.assertEqual((await controller.stop()).status,'complete')
        state=await self.scalar('SELECT engine_state FROM vn_durability.runs WHERE id=%s::uuid',(self.run_id,))
        self.assertEqual(state,owner.installed_state.to_dict())
        self.assertEqual(state['status'],'stopped')
        self.assertEqual(await self.scalar('SELECT count(*) FROM vn_projection.probes WHERE run_id=%s::uuid AND revision=%s',
                                         (self.run_id,self.repository.revision)),8)
        self.assertGreater(await self.scalar('SELECT count(*) FROM vn_projection.relay_events WHERE run_id=%s::uuid',
                                            (self.run_id,)),0)
        page=await self.pair.rpc('read_outbox',{'owner_id':self.owner_id,'run':self.run_id,
            'through_revision':self.repository.revision,'max_events':50,'max_bytes':65536})
        self.assertEqual(page['events'],[])
        self.assertFalse(page['has_more'])

    async def test_lost_real_bootstrap_commit_reply_resolves_original_only(self):
        owner,controller=await self.controller()
        original_commit=self.pair._economic._commit
        original_operate=self.pair._economic._operate
        calls=[]
        async def lose_reply(connection):
            calls.append(connection.info.backend_pid)
            await original_commit(connection)
            raise OSError('synthetic lost COMMIT reply')
        async def lose_batch(ready,name,query,params):
            if name=='commit_command':
                with patch.object(self.pair._economic,'_commit',lose_reply):
                    return await original_operate(ready,name,query,params)
            return await original_operate(ready,name,query,params)
        with patch.object(self.pair._economic,'_operate',lose_batch):
            with self.assertRaises(UncertainCommand): await controller.bootstrap()
        original=owner.pending_command
        providers=(len(self.feed._session.calls),len(self.feed._candles._session.calls))
        self.assertIsNone(owner.installed_state)
        self.assertEqual(await self.journal_count(),2)
        self.assertIsNotNone(await self.scalar('SELECT engine_state FROM vn_durability.runs WHERE id=%s::uuid',(self.run_id,)))
        report=await controller.settle()
        self.assertEqual(report.status,'complete')
        self.assertEqual(self.repository.last_receipt.command.command_id,original.command_id)
        self.assertEqual(len(calls),1)
        self.assertEqual(await self.journal_count(),2)
        self.assertEqual(providers,(len(self.feed._session.calls),len(self.feed._candles._session.calls)))

    async def test_cancelled_caller_keeps_real_commit_owned_and_no_overlap(self):
        original_commit=self.pair._economic._commit
        committed,release=asyncio.Event(),asyncio.Event()
        async def hold_reply(connection):
            await original_commit(connection)
            committed.set()
            await release.wait()
        command=self.create()
        with patch.object(self.pair._economic,'_commit',hold_reply):
            task=asyncio.create_task(self.repository.submit(command))
            try:
                await asyncio.wait_for(committed.wait(),2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError): await task
                self.assertTrue(self.repository.busy)
                self.assertEqual(await self.journal_count(),1)
                with self.assertRaises(CommandSQLError):
                    await self.pair.rpc('read_outbox',{'owner_id':self.owner_id,'run':self.run_id,
                        'through_revision':1,'max_events':50,'max_bytes':65536})
            finally: release.set()
            deadline=time.monotonic()+2
            while self.repository.busy and time.monotonic()<deadline: await asyncio.sleep(.01)
        self.assertFalse(self.repository.busy)
        self.assertEqual(self.repository.last_receipt.command.command_id,command.command_id)
        self.assertEqual(await self.journal_count(),1)

    async def test_real_lock_timeout_rolls_back_and_missing_readback_stays_uncertain(self):
        await self.pair.aclose()
        self.pair=self.make_pair(bounds=CommandSQLBounds(operation_seconds=2,connect_seconds=.5,
            statement_seconds=.15,commit_seconds=.5))
        self.repository=CommandRepository(self.pair,self.owner_id,self.run_id,self.worker_id)
        blocker=await self.admin_connect()
        command=self.create()
        try:
            await blocker.execute('BEGIN')
            await blocker.execute('LOCK TABLE vn_durability.runs IN ACCESS EXCLUSIVE MODE')
            started=time.monotonic()
            with self.assertRaises(UncertainCommand): await self.repository.submit(command)
            self.assertLess(time.monotonic()-started,2)
        finally: await blocker.close()
        self.assertEqual(await self.journal_count(),0)
        self.assertEqual(await self.scalar('SELECT count(*) FROM vn_durability.runs WHERE id=%s::uuid',(self.run_id,)),0)
        # No run survived create rollback. Server denial is also inconclusive;
        # preserve the original ID rather than manufacture a replacement.
        with self.assertRaises(UncertainCommand): await self.repository.resolve_pending()
        self.assertEqual(self.repository.pending.command_id,command.command_id)
        with self.assertRaises(CommandAdmissionError): await self.repository.submit(self.create())

    async def test_legacy_paper_limit_refuses_the_same_two_second_real_lock_wait(self):
        await self.pair.aclose()
        self.pair=self.make_pair(bounds=CommandSQLBounds(connect_seconds=1.0))
        self.repository=CommandRepository(self.pair,self.owner_id,self.run_id,self.worker_id)
        blocker=await self.admin_connect()
        command=self.create()
        release=None
        async def release_lock():
            await asyncio.sleep(2)
            await blocker.execute('ROLLBACK')
        try:
            await blocker.execute('BEGIN')
            await blocker.execute('LOCK TABLE vn_durability.runs IN ACCESS EXCLUSIVE MODE')
            release=asyncio.create_task(release_lock())
            with self.assertRaises(UncertainCommand): await self.repository.submit(command)
        finally:
            if release is not None: await release
            await blocker.close()
        self.assertEqual(await self.journal_count(),0)
        self.assertEqual(self.repository.pending.command_id,command.command_id)
        self.assertEqual(self.pair.first_failures['economic']['phase'],'execute')

    async def test_precommit_failure_rolls_back_actual_sql_without_acknowledgment(self):
        reached=[]
        async def before_commit(connection):
            reached.append(connection.info.backend_pid)
            self.assertEqual(connection.info.transaction_status,psycopg.pq.TransactionStatus.INTRANS)
            raise OSError('synthetic connection loss before COMMIT')
        command=self.create()
        with patch.object(self.pair._economic,'_commit',before_commit):
            with self.assertRaises(UncertainCommand): await self.repository.submit(command)
        self.assertEqual(len(reached),1)
        self.assertEqual(await self.journal_count(),0)
        self.assertEqual(await self.scalar('SELECT count(*) FROM vn_durability.runs WHERE id=%s::uuid',(self.run_id,)),0)
        self.assertEqual(self.repository.pending.command_id,command.command_id)

    async def test_paper_profile_commits_original_once_after_two_second_real_lock_wait(self):
        await self.pair.aclose()
        self.pair=self.make_pair(bounds=paper_sql_bounds())
        self.repository=CommandRepository(self.pair,self.owner_id,self.run_id,self.worker_id)
        blocker=await self.admin_connect()
        command=self.create()
        connects=0
        original_connect=self.pair._economic._connect
        async def connect(*args):
            nonlocal connects
            connects+=1
            return await original_connect(*args)
        async def release_lock():
            await asyncio.sleep(2)
            await blocker.execute('ROLLBACK')
        release=None
        try:
            await blocker.execute('BEGIN')
            await blocker.execute('LOCK TABLE vn_durability.runs IN ACCESS EXCLUSIVE MODE')
            release=asyncio.create_task(release_lock())
            started=time.monotonic()
            with patch.object(self.pair._economic,'_connect',connect):
                receipt=await self.repository.submit(command)
            elapsed=time.monotonic()-started
            self.assertGreater(elapsed,1.5)
            self.assertLess(elapsed,5)
            self.assertEqual(receipt.command.command_id,command.command_id)
            self.assertEqual(connects,1)
            self.assertEqual(await self.journal_count(),1)
            self.assertIsNone(self.repository.pending)
            self.assertIsNone(self.pair.first_failures['economic'])
        finally:
            if release is not None: await release
            await blocker.close()

    async def test_paper_profile_still_rolls_back_over_budget_lock_and_retains_original(self):
        await self.pair.aclose()
        self.pair=self.make_pair(bounds=paper_sql_bounds())
        self.repository=CommandRepository(self.pair,self.owner_id,self.run_id,self.worker_id)
        blocker=await self.admin_connect()
        command=self.create()
        try:
            await blocker.execute('BEGIN')
            await blocker.execute('LOCK TABLE vn_durability.runs IN ACCESS EXCLUSIVE MODE')
            started=time.monotonic()
            with self.assertRaises(UncertainCommand): await self.repository.submit(command)
            self.assertLess(time.monotonic()-started,5)
        finally: await blocker.close()
        self.assertEqual(await self.journal_count(),0)
        original=self.pair.first_failures['economic']
        self.assertEqual(original['phase'],'execute')
        self.assertIn(original['code'],('phase_timeout','statement_timeout','query_cancelled','lock_unavailable'))
        with self.assertRaises(UncertainCommand): await self.repository.resolve_pending()
        self.assertEqual(self.pair.first_failures['economic'],original)
        self.assertEqual(self.repository.pending.command_id,command.command_id)
        with self.assertRaises(CommandAdmissionError): await self.repository.submit(self.create())

    async def test_real_commit_reply_timeout_recovers_original_durable_command(self):
        await self.pair.aclose()
        self.pair=self.make_pair(bounds=CommandSQLBounds(commit_seconds=.03))
        self.repository=CommandRepository(self.pair,self.owner_id,self.run_id,self.worker_id)
        original_commit=self.pair._economic._commit
        committed=[]
        async def delay_reply(connection):
            await original_commit(connection)
            committed.append(connection.info.backend_pid)
            await asyncio.sleep(10)
        command=self.create()
        with patch.object(self.pair._economic,'_commit',delay_reply):
            with self.assertRaises(UncertainCommand): await self.repository.submit(command)
        self.assertEqual(len(committed),1)
        self.assertEqual(await self.journal_count(),1)
        self.assertEqual(self.repository.pending.command_id,command.command_id)
        receipt=await self.repository.resolve_pending()
        self.assertEqual(receipt.command.command_id,command.command_id)
        self.assertEqual(await self.journal_count(),1)

    async def test_real_bad_ca_and_password_fail_closed_before_sql(self):
        for password,ca in ((self.economic[1],self.fixture['wrong_ca'].encode()),('x'*64,self.ca)):
            transport=DashboardCommandSQLTransport(self.economic[0],password,ca,self.owner_id,self.run_id,'economic')
            self.extra.append(transport)
            with self.assertRaises(CommandSQLError) as caught:
                await transport.rpc('create_run',self.create().rpc_args)
            self.assertEqual(caught.exception.code,'operation_failed_or_uncertain')
            self.assertNotIn(password,str(caught.exception))
        self.assertEqual(await self.journal_count(),0)

    async def test_server_binding_rejects_forged_owner_run_and_economic_relay(self):
        await self.repository.submit(self.create())
        self.assertIsNone(await self.pair.rpc('get_command',{'owner_id':self.owner_id,
            'run':self.run_id,'command_id':identity()}))
        for owner,run,cap in ((identity(),self.run_id,'economic'),(self.owner_id,identity(),'economic'),
                              (self.owner_id,self.run_id,'relay')):
            transport=DashboardCommandSQLTransport(*self.economic,self.ca,owner,run,cap)
            self.extra.append(transport)
            arguments={'owner_id':owner,'run':run}
            name='get_command' if cap=='economic' else 'read_outbox'
            arguments.update({'command_id':self.repository.last_receipt.command.command_id} if cap=='economic' else
                             {'through_revision':1,'max_events':50,'max_bytes':65536})
            with self.assertRaises(CommandSQLError): await transport.rpc(name,arguments)
        self.assertEqual(await self.journal_count(),1)
