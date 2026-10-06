"""Inert native Dashboard transport: one owned transaction and no retries.

Explicit synthetic/approved credentials and CA only; no startup selection,
environment credential lookup, pooler, DSN, shell subprocess or host override.
The caller/repository retains original command identity on every uncertain exit.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import tempfile
from typing import Any

import psycopg
from psycopg.pq import TransactionStatus

from .command_http import _arguments, _decode, MAX_RESPONSE_BYTES, CommandHTTPError
from .command_protocol import canonical_json, canonical_uuid

HOST='db.fxpxsciltakyypunglzr.supabase.co'
ECONOMIC=frozenset({'create_run','heartbeat','commit_command','get_command','interrupt_expired'})
RELAY=frozenset({'read_outbox','acknowledge_event','accept_event'})
CASTS={'owner_id':'uuid','run':'uuid','worker':'uuid','command_id':'uuid',
       'configuration':'jsonb','payload':'jsonb','initial_cash':'text',
       'lease_seconds':'integer','token':'bigint','expected_revision':'bigint',
       'through_revision':'bigint','max_events':'integer','max_bytes':'integer','event_index':'integer'}


class CommandSQLError(RuntimeError):
    """Fixed codes only, never driver errors, SQL arguments, paths or credentials."""
    def __init__(self,code):
        self.code=code
        super().__init__('Command SQL transport refused operation: '+code)


@dataclass(frozen=True,slots=True)
class CommandSQLBounds:
    operation_seconds: float=3.0
    connect_seconds: float=.5
    statement_seconds: float=1.5
    commit_seconds: float=.5
    cleanup_seconds: float=1.0

    def __post_init__(self):
        values=(self.operation_seconds,self.connect_seconds,self.statement_seconds,self.commit_seconds,self.cleanup_seconds)
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<v<=15 for v in values) or \
           max(self.connect_seconds,self.statement_seconds,self.commit_seconds)>self.operation_seconds:
            raise CommandSQLError('invalid_bounds')


def _ambient_guard():
    # Fail closed rather than changing the shared process environment. libpq's
    # service/hostaddr/options/SSL defaults otherwise admit ambient fallback.
    if any(k.startswith('PG') for k in os.environ):
        raise CommandSQLError('ambient_pg_configuration')


def _query(name,arguments,owner,run,capability):
    try:
        if type(name) is not str or name not in (ECONOMIC if capability=='economic' else RELAY):
            raise ValueError()
        body=_arguments('acknowledge_event' if name=='accept_event' else name,arguments,owner)
        values=json.loads(body)
        if values['run']!=run:
            raise ValueError()
        keys=sorted(values)
        schema='vn_read' if name=='accept_event' else 'vn_durability'
        call=schema+'.'+name+'('+','.join(k+'=>%s::'+CASTS[k] for k in keys)+')'
        # MATERIALIZED evaluates the volatile RPC exactly once. Only a capped
        # UTF-8 bytea crosses the wire; JSONB driver decoding cannot round money.
        query='WITH result AS MATERIALIZED (SELECT '+call+' AS value) SELECT octet_length(value::text), '
        query+=f"CASE WHEN octet_length(value::text)<={MAX_RESPONSE_BYTES} THEN convert_to(value::text,'UTF8') END FROM result"
        params=tuple(canonical_json(values[k]).decode() if CASTS[k]=='jsonb' else values[k] for k in keys)
        return query,params
    except (ValueError,KeyError,CommandHTTPError,RecursionError):
        raise CommandSQLError('invalid_request') from None


class DashboardCommandSQLTransport:
    """One event loop/active operation; fresh connection for each RPC.

    Caller cancellation leaves the admitted transaction owned until its deadline
    and cleanup. No operation retries or fallback connection profiles exist.
    Native login and CA parameters are private and are never included in repr.
    """
    def __init__(self,login: str,password: str,ca_pem: bytes,owner_id: str,run_id: str,
                 capability: str,*,bounds: CommandSQLBounds|None=None):
        try:
            if type(login) is not str or re.fullmatch(r'vn_native_[a-f0-9]{32}',login) is None or \
               type(password) is not str or not 32<=len(password)<=256 or not password.isascii() or \
               any(ord(c)<33 or ord(c)>126 for c in password):
                raise ValueError()
            if capability not in ('economic','relay') or type(capability) is not str:
                raise ValueError()
            self._owner=canonical_uuid(owner_id)
            self._run=canonical_uuid(run_id)
            if type(ca_pem) is not bytes or not 1<=len(ca_pem)<=65536:
                raise ValueError()
            # No default/system roots or client certificates are loaded.
            check=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            check.load_verify_locations(cadata=ca_pem.decode('ascii'))
            if b'PRIVATE KEY' in ca_pem or check.cert_store_stats()['x509_ca']<1:
                raise ValueError()
            if bounds is not None and type(bounds) is not CommandSQLBounds:
                raise ValueError()
        except Exception:
            raise CommandSQLError('invalid_configuration') from None
        _ambient_guard()
        if psycopg.pq.__impl__!='binary' or psycopg.pq.version()<170000:
            raise CommandSQLError('unsupported_driver')
        self._login,self._password,self._ca=login,password,ca_pem
        self._capability=capability
        self._bounds=bounds or CommandSQLBounds()
        self._loop=None
        self._active=None
        self._closed=False
        self._cleanup_failed=False
        self._cleanup=None
        self._io_tasks=set()

    def _bind_loop(self):
        loop=asyncio.get_running_loop()
        if self._loop is None: self._loop=loop
        if self._loop is not loop: raise CommandSQLError('foreign_loop')

    async def _resolve(self):
        rows=await asyncio.get_running_loop().getaddrinfo(HOST,5432,type=socket.SOCK_STREAM)
        for family,_,_,_,address in rows:
            if family in (socket.AF_INET,socket.AF_INET6):
                ip=ipaddress.ip_address(address[0])
                if ip.is_global: return str(ip)
        raise CommandSQLError('invalid_address')

    async def _connect(self,ca_path,crl_path):
        address=await self._resolve()
        _ambient_guard()
        ms=max(1,int(self._bounds.statement_seconds*1000))
        whole=max(1,int(self._bounds.operation_seconds*1000))
        return await psycopg.AsyncConnection.connect('',host=HOST,hostaddr=address,port=5432,
            dbname='postgres',user=self._login,password=self._password,passfile=os.devnull,
            sslmode='verify-full',sslrootcert=str(ca_path),sslcrl=str(crl_path),sslcrldir='',
            sslcert=os.devnull,sslkey=os.devnull,sslcertmode='disable',
            ssl_min_protocol_version='TLSv1.2',sslnegotiation='postgres',sslsni='1',
            require_auth='scram-sha-256',channel_binding='require',gssencmode='disable',
            client_encoding='UTF8',application_name='dashboard-native-'+self._capability,
            connect_timeout=2,autocommit=True,prepare_threshold=None,
            options=f'-c search_path=pg_catalog -c statement_timeout={ms} -c lock_timeout={ms} '
                    f'-c idle_in_transaction_session_timeout={whole} -c transaction_timeout={whole} '
                    '-c synchronous_commit=on')

    async def _io(self,operation,seconds):
        task=asyncio.create_task(operation)
        self._io_tasks.add(task)
        def done(value):
            if not value.cancelled(): value.exception()
        task.add_done_callback(done)
        return await asyncio.wait_for(asyncio.shield(task),seconds)

    async def _commit(self,connection):
        result=await connection.execute('COMMIT',prepare=False)
        if result.statusmessage!='COMMIT' or connection.info.transaction_status!=TransactionStatus.IDLE:
            raise CommandSQLError('commit_unconfirmed')

    async def _dispose(self,connection):
        if connection is not None:
            await connection.close()
        # A connect task can complete just after its phase deadline. Retrieve
        # and close that late connection as well; ownership never disappears.
        tasks=list(self._io_tasks)
        for task in tasks:
            if not task.done(): task.cancel()
        if tasks:
            results=await asyncio.gather(*tasks,return_exceptions=True)
            for value in results:
                if isinstance(value,psycopg.AsyncConnection): await value.close()
            self._io_tasks.difference_update(tasks)

    async def _operate(self,ready,name,query,params):
        await ready
        connection=None
        directory=None
        try:
            deadline=asyncio.get_running_loop().time()+self._bounds.operation_seconds
            async with asyncio.timeout(self._bounds.operation_seconds):
                # Owned public CA and an explicit absent CRL file replace
                # libpq home-file defaults. An empty CRL directory would enable
                # CRL checks and reject a CA with no CRL. No password is written.
                directory=tempfile.TemporaryDirectory(prefix='dashboard-sql-',dir='/tmp')
                ca_path=Path(directory.name)/'root.crt'
                ca_path.write_bytes(self._ca); ca_path.chmod(0o600)
                connection=await self._io(self._connect(ca_path,Path(directory.name)/'absent.crl'),self._bounds.connect_seconds)
                if not connection.pgconn.ssl_in_use or connection.info.server_version//10000!=17:
                    raise CommandSQLError('connection_unverified')
                await self._io(connection.execute('BEGIN',prepare=False),self._bounds.statement_seconds)
                await self._io(connection.execute('SET LOCAL ROLE vn_'+self._capability,prepare=False),self._bounds.statement_seconds)
                cursor=await self._io(connection.execute(query,params,prepare=False),self._bounds.statement_seconds)
                row=await self._io(cursor.fetchone(),self._bounds.statement_seconds)
                if type(row) is not tuple or len(row)!=2:
                    raise CommandSQLError('invalid_response')
                length,body=row
                if length is None and body is None and name=='get_command':
                    value=None
                elif type(length) is int and 0<length<=MAX_RESPONSE_BYTES and type(body) is bytes and len(body)==length:
                    value=_decode(body)
                    if type(value) is not dict: raise CommandSQLError('invalid_response')
                else:
                    raise CommandSQLError('invalid_response')
                if asyncio.get_running_loop().time()>=deadline:
                    raise CommandSQLError('operation_timed_out')
                await self._io(self._commit(connection),self._bounds.commit_seconds)
                if asyncio.get_running_loop().time()>=deadline:
                    raise CommandSQLError('operation_timed_out')
                return value
        except CommandSQLError:
            raise
        except (Exception,asyncio.CancelledError):
            raise CommandSQLError('operation_failed_or_uncertain') from None
        finally:
            # Cleanup outlives timeouts and caller cancellation. Retain its task
            # and resources until completion, and refuse reuse while pending.
            async def clean():
                try: await self._dispose(connection)
                finally:
                    if directory is not None: directory.cleanup()
            self._cleanup=asyncio.create_task(clean())
            self._cleanup.add_done_callback(lambda t: None if t.cancelled() else t.exception())
            try:
                await asyncio.wait_for(asyncio.shield(self._cleanup),self._bounds.cleanup_seconds)
            except (Exception,asyncio.CancelledError):
                self._cleanup_failed=True
                raise CommandSQLError('cleanup_pending_or_failed') from None

    async def rpc(self,name:str,arguments:dict[str,Any])->Any:
        self._bind_loop()
        if self._closed or self._cleanup_failed or (self._cleanup is not None and not self._cleanup.done()):
            raise CommandSQLError('closed_or_cleanup_pending')
        if self._active is not None: raise CommandSQLError('busy')
        _ambient_guard()
        query,params=_query(name,arguments,self._owner,self._run,self._capability)
        ready=asyncio.get_running_loop().create_future()
        task=asyncio.create_task(self._operate(ready,name,query,params))
        self._active=task
        def done(value):
            if self._active is value: self._active=None
            if not value.cancelled(): value.exception()
        task.add_done_callback(done)
        ready.set_result(None)
        return await asyncio.shield(task)

    async def accept_event(self,arguments:dict)->dict:
        return await self.rpc('accept_event',arguments)

    async def aclose(self):
        self._bind_loop(); self._closed=True
        if self._active is asyncio.current_task(): raise CommandSQLError('busy')
        try:
            if self._active is not None:
                try: await asyncio.wait_for(asyncio.shield(self._active),self._bounds.cleanup_seconds)
                except Exception:
                    if self._active is not None and not self._active.done(): raise
            if self._cleanup is not None:
                await asyncio.wait_for(asyncio.shield(self._cleanup),self._bounds.cleanup_seconds)
            if self._cleanup_failed: raise CommandSQLError('cleanup_pending_or_failed')
        except asyncio.CancelledError:
            raise
        except Exception:
            raise CommandSQLError('cleanup_pending_or_failed') from None


class DashboardCommandSQLPair:
    """Route the existing repository/controller interface through two principals."""
    def __init__(self,economic_login,economic_password,relay_login,relay_password,ca_pem,
                 owner_id,run_id,*,bounds=None):
        if economic_login==relay_login: raise CommandSQLError('credentials_not_separate')
        self._economic=DashboardCommandSQLTransport(economic_login,economic_password,ca_pem,owner_id,run_id,'economic',bounds=bounds)
        self._relay=DashboardCommandSQLTransport(relay_login,relay_password,ca_pem,owner_id,run_id,'relay',bounds=bounds)
        self._closed=False
        self._close_task=None

    async def rpc(self,name,arguments):
        if self._closed: raise CommandSQLError('closed_or_cleanup_pending')
        if any(t._active is not None for t in (self._economic,self._relay)):
            raise CommandSQLError('busy')
        if any(t._cleanup_failed or (t._cleanup is not None and not t._cleanup.done()) for t in (self._economic,self._relay)):
            raise CommandSQLError('closed_or_cleanup_pending')
        target=self._economic if type(name) is str and name in ECONOMIC else self._relay
        return await target.rpc(name,arguments)

    async def accept_event(self,arguments):
        return await self.rpc('accept_event',arguments)

    async def aclose(self):
        self._closed=True
        if self._close_task is None:
            async def close_both():
                return await asyncio.gather(self._economic.aclose(),self._relay.aclose(),return_exceptions=True)
            self._close_task=asyncio.create_task(close_both())
            self._close_task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        results=await asyncio.shield(self._close_task)
        if any(isinstance(r,BaseException) for r in results):
            raise CommandSQLError('cleanup_pending_or_failed') from None
