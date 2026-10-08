"""Owned SQL transport fault/identity/parameter tests, no network."""
from __future__ import annotations
import asyncio
from datetime import datetime,timedelta,timezone
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from psycopg.pq import TransactionStatus
from vonneumann.db.command_sql import DashboardCommandSQLTransport,DashboardCommandSQLPair,CommandSQLError,CommandSQLBounds,HOST
from tests.security_support import USER_A,A1


def certificate():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Offline SQL unit CA')])
    now=datetime.now(timezone.utc)
    return x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(
        x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1)).add_extension(
        x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(key,hashes.SHA256()).public_bytes(serialization.Encoding.PEM)


class Connection:
    def __init__(self,body=b'{"revision":1}'):
        self.pgconn=SimpleNamespace(ssl_in_use=True)
        self.info=SimpleNamespace(server_version=170006,transaction_status=TransactionStatus.IDLE)
        self.calls=[];self.closed=False;self.body=body
        self.close_gate=None
    async def execute(self,sql,params=None,**kwargs):
        self.calls.append((sql,params,kwargs))
        if sql=='BEGIN': self.info.transaction_status=TransactionStatus.INTRANS
        if sql=='COMMIT': self.info.transaction_status=TransactionStatus.IDLE
        return self
    @property
    def statusmessage(self): return 'COMMIT'
    async def fetchone(self): return (None,None) if self.body is None else (len(self.body),self.body)
    async def close(self):
        if self.close_gate is not None: await self.close_gate.wait()
        self.closed=True


class SQLTransportTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls): cls.ca=certificate()
    def setUp(self):
        self.connection=Connection()
        self.transport=DashboardCommandSQLTransport('vn_native_'+'a'*32,'unit-password-'+'b'*32,self.ca,USER_A,A1,'economic')
        self.transport._connect=AsyncMock(return_value=self.connection)
        self.args={'owner_id':USER_A,'run':A1,'command_id':A1}
    async def asyncTearDown(self):
        if self.connection.close_gate is not None: self.connection.close_gate.set()
        try: await self.transport.aclose()
        except CommandSQLError: pass

    async def test_commit_is_explicit_after_validation_and_no_retry_or_prepare(self):
        value=await self.transport.rpc('get_command',self.args)
        self.assertEqual(value,{'revision':1})
        self.assertEqual(self.connection.calls[0][0],'BEGIN')
        self.assertEqual(self.connection.calls[1][0],'SET LOCAL ROLE vn_economic')
        self.assertEqual(self.connection.calls[-1][0],'COMMIT')
        self.assertTrue(all(call[2]=={'prepare':False} for call in self.connection.calls))
        self.assertEqual(self.transport._connect.await_count,1)
        self.assertTrue(self.connection.closed)

    async def test_owner_run_capability_and_signature_refused_before_connect(self):
        for name,args in [('get_command',{**self.args,'owner_id':A1}),('get_command',{**self.args,'run':USER_A}),
            ('get_command',{**self.args,'extra':'x'}),('read_outbox',self.args),('get_command; DROP TABLE x',self.args)]:
            with self.subTest(name=name,args=args):
                with self.assertRaisesRegex(CommandSQLError,'invalid_request'): await self.transport.rpc(name,args)
        self.transport._connect.assert_not_awaited()

    async def test_snapshot_and_parameter_casts_preserve_immutable_json(self):
        entered,release=asyncio.Event(),asyncio.Event()
        async def connect(*args): entered.set();await release.wait();return self.connection
        self.transport._connect=connect
        args={'owner_id':USER_A,'run':A1,'worker':A1,'token':1,'expected_revision':1,'command_id':A1,
              'payload':{'value':'0.000000000000000001','large':9007199254740993}}
        task=asyncio.create_task(self.transport.rpc('commit_command',args))
        await entered.wait();args['payload']['value']='changed';release.set();await task
        query,params,_=self.connection.calls[2]
        self.assertIn('WITH result AS MATERIALIZED',query)
        self.assertIn('payload=>%s::jsonb',query)
        self.assertIn('"value":"0.000000000000000001"',' '.join(str(p) for p in params))
        self.assertNotIn('changed',' '.join(str(p) for p in params))

    async def test_fractional_duplicate_oversized_and_invalid_results_never_commit(self):
        for body in (b'{"x":1.1}',b'{"x":1,"x":2}',b'[]',b'x'*393217,b'{"x":NaN}'):
            self.connection=Connection(body)
            self.transport._connect=AsyncMock(return_value=self.connection)
            with self.subTest(body=body[:32]):
                with self.assertRaises(CommandSQLError): await self.transport.rpc('get_command',self.args)
                self.assertNotIn('COMMIT',[c[0] for c in self.connection.calls])
                self.assertTrue(self.connection.closed)

    async def test_cancellation_keeps_commit_owned_and_blocks_other_requests(self):
        committed,release=asyncio.Event(),asyncio.Event()
        original=self.transport._commit
        async def commit(conn): await original(conn);committed.set();await release.wait()
        self.transport._commit=commit
        task=asyncio.create_task(self.transport.rpc('get_command',self.args))
        await committed.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        with self.assertRaisesRegex(CommandSQLError,'busy'): await self.transport.rpc('get_command',self.args)
        owned=self.transport._active
        release.set();await owned
        self.assertEqual(len([c for c in self.connection.calls if c[0]=='COMMIT']),1)

    async def test_commit_timeout_is_uncertain_closes_connection_and_retains_no_retry(self):
        self.transport._bounds=CommandSQLBounds(commit_seconds=.02)
        async def commit(conn): await asyncio.sleep(10)
        self.transport._commit=commit
        with self.assertRaisesRegex(CommandSQLError,'operation_failed_or_uncertain'):
            await self.transport.rpc('get_command',self.args)
        self.assertTrue(self.connection.closed)
        self.assertFalse(self.transport._io_tasks)
        self.assertEqual(self.transport._connect.await_count,1)
        self.assertEqual(self.transport.last_failure_phase,'commit')

    async def test_explicit_paper_connect_headroom_keeps_one_attempt_and_whole_operation_bound(self):
        self.transport._bounds=CommandSQLBounds(connect_seconds=1.0)
        async def slow_connection(*args):
            await asyncio.sleep(.55)
            return self.connection
        self.transport._connect=AsyncMock(side_effect=slow_connection)
        await self.transport.rpc('get_command',self.args)
        self.assertEqual(self.transport._connect.await_count,1)
        self.assertEqual(self.connection.calls[-1][0],'COMMIT')
        self.assertEqual(self.transport._bounds.operation_seconds,3.0)
        self.assertEqual(CommandSQLBounds().connect_seconds,.5)
        self.assertIsNone(self.transport.last_failure_phase)

    async def test_late_connection_after_timeout_is_owned_and_closed(self):
        self.transport._bounds=CommandSQLBounds(connect_seconds=.01)
        async def delayed_connection(*args):
            try: await asyncio.sleep(10)
            except asyncio.CancelledError: return self.connection
        self.transport._connect=delayed_connection
        # The late driver return must be closed even though _operate never
        # assigned it to its local connection variable.
        with patch('vonneumann.db.command_sql.psycopg.AsyncConnection',Connection):
            with self.assertRaises(CommandSQLError): await self.transport.rpc('get_command',self.args)
        self.assertTrue(self.connection.closed)
        self.assertFalse(self.transport._io_tasks)
        self.assertEqual(self.connection.calls,[])
        self.assertEqual(self.transport.last_failure_phase,'connect')

    async def test_only_original_command_readback_accepts_sql_null(self):
        self.connection.body=None
        self.assertIsNone(await self.transport.rpc('get_command',self.args))
        self.assertEqual(self.connection.calls[-1][0],'COMMIT')
        self.transport._capability='relay'
        self.transport._connect=AsyncMock(return_value=Connection(None))
        with self.assertRaises(CommandSQLError):
            await self.transport.rpc('read_outbox',{'owner_id':USER_A,'run':A1,
                'through_revision':1,'max_events':50,'max_bytes':65536})

    async def test_cleanup_timeout_retains_resources_and_refuses_reuse(self):
        self.transport._bounds=CommandSQLBounds(cleanup_seconds=.02)
        self.connection.close_gate=asyncio.Event()
        with self.assertRaisesRegex(CommandSQLError,'cleanup_pending_or_failed'):
            await self.transport.rpc('get_command',self.args)
        self.assertFalse(self.transport._cleanup.done())
        self.assertEqual(self.transport.last_failure_phase,'cleanup')
        with self.assertRaisesRegex(CommandSQLError,'closed_or_cleanup_pending'):
            await self.transport.rpc('get_command',self.args)
        self.connection.close_gate.set();await self.transport._cleanup
        self.assertTrue(self.connection.closed)

    async def test_explicit_connection_parameters_suppress_credentials_ca_and_service_fallback(self):
        # Use the actual _connect body with only driver/network edges mocked.
        self.transport._connect=DashboardCommandSQLTransport._connect.__get__(self.transport)
        self.transport._resolve=AsyncMock(return_value='203.0.113.10')
        with patch('psycopg.AsyncConnection.connect',new=AsyncMock(return_value=self.connection)) as connect:
            await self.transport.rpc('get_command',self.args)
        kwargs=connect.call_args.kwargs
        self.assertEqual(kwargs['host'],HOST);self.assertEqual(kwargs['hostaddr'],'203.0.113.10')
        self.assertEqual(kwargs['port'],5432);self.assertEqual(kwargs['dbname'],'postgres')
        self.assertEqual(kwargs['sslmode'],'verify-full');self.assertEqual(kwargs['channel_binding'],'require')
        self.assertEqual(kwargs['require_auth'],'scram-sha-256');self.assertEqual(kwargs['sslcertmode'],'disable')
        self.assertEqual(kwargs['sslcrldir'],'')
        self.assertFalse(os.path.exists(kwargs['sslcrl']))
        self.assertEqual(kwargs['sslcert'],os.devnull);self.assertEqual(kwargs['sslkey'],os.devnull)
        self.assertEqual(kwargs['passfile'],os.devnull);self.assertTrue(kwargs['autocommit'])
        self.assertIsNone(kwargs['prepare_threshold'])
        self.assertFalse(os.path.exists(kwargs['sslrootcert']))

    async def test_ambient_configuration_and_foreign_loop_are_refused(self):
        with patch.dict(os.environ,{'PGHOST':'wrong-project.invalid','PGPASSWORD':'unrelated-secret'}):
            with self.assertRaisesRegex(CommandSQLError,'ambient_pg_configuration'):
                await self.transport.rpc('get_command',self.args)
        self.transport._loop=object()
        with self.assertRaisesRegex(CommandSQLError,'foreign_loop'): await self.transport.rpc('get_command',self.args)
        self.transport._loop=asyncio.get_running_loop()

    async def test_driver_errors_do_not_expose_credentials_or_diagnostics(self):
        self.transport._connect=AsyncMock(side_effect=RuntimeError('private-password private-key sql-body'))
        with self.assertRaises(CommandSQLError) as error: await self.transport.rpc('get_command',self.args)
        self.assertNotIn('private',str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)
        self.assertNotIn('unit-password',repr(self.transport))

    async def test_pair_routes_relay_and_economics_with_global_busy_admission(self):
        pair=DashboardCommandSQLPair('vn_native_'+'a'*32,'unit-password-'+'b'*32,
            'vn_native_'+'c'*32,'relay-password-'+'d'*32,self.ca,USER_A,A1)
        economic,relay=Connection(),Connection()
        pair._economic._connect=AsyncMock(return_value=economic)
        pair._relay._connect=AsyncMock(return_value=relay)
        await pair.rpc('get_command',self.args)
        await pair.accept_event({**self.args,'event_index':0})
        self.assertEqual(economic.calls[1][0],'SET LOCAL ROLE vn_economic')
        self.assertEqual(relay.calls[1][0],'SET LOCAL ROLE vn_relay')
        self.assertIn('vn_read.accept_event',relay.calls[2][0])
        await pair.aclose()

    async def test_invalid_bounds_ca_credentials_and_pair_reuse_are_refused(self):
        for value in (0,float('nan'),16,True):
            with self.assertRaises(CommandSQLError): CommandSQLBounds(commit_seconds=value)
        with self.assertRaises(CommandSQLError):
            DashboardCommandSQLTransport('postgres','short',b'bad',USER_A,A1,'economic')
        with self.assertRaisesRegex(CommandSQLError,'credentials_not_separate'):
            DashboardCommandSQLPair('same','x','same','y',self.ca,USER_A,A1)
