"""Exact Dashboard TLS transport for the owner-scoped continuous paper journal.

Private login/CA are constructor inputs. No environment, DSN, pooler, proxy,
shared profile, transaction retry or wallet operation is used here.
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import tempfile
from uuid import UUID
import psycopg

from ..core.prospective_runtime import JournalEntry, JournalRejected

HOST = 'db.fxpxsciltakyypunglzr.supabase.co'
MAX_REPLY = 32 * 1024 * 1024


class JournalUnavailable(RuntimeError):
    pass


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError('invalid_paper_identity')
    return value


def _raw(value):
    if type(value) is not str:
        raise JournalUnavailable('invalid_paper_readback')
    # PostgreSQL base64 output wraps lines; remove only ASCII newlines.
    return base64.b64decode(value.replace('\n', ''), validate=True)


class ProspectiveSQLJournal:
    def __init__(self, login, password, ca_pem, owner_id, run_id):
        try:
            if type(login) is not str or re.fullmatch(r'vn_paper_[a-f0-9]{32}', login) is None:
                raise ValueError()
            if type(password) is not str or not 32 <= len(password) <= 256 or not password.isascii() or any(ord(c)<33 or ord(c)>126 for c in password):
                raise ValueError()
            if type(ca_pem) is not bytes or not 1 <= len(ca_pem) <= 65536 or b'PRIVATE KEY' in ca_pem:
                raise ValueError()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cadata=ca_pem.decode('ascii'))
            if context.cert_store_stats()['x509_ca'] < 1:
                raise ValueError()
            self.owner_id, self.run_id = _uuid(owner_id), _uuid(run_id)
        except Exception:
            raise JournalUnavailable('invalid_paper_configuration') from None
        self._login, self._password, self._ca = login, password, ca_pem
        self._lock, self._closed = asyncio.Lock(), False
        self._cleanup_failed = False
        self._tasks = set()

    async def _rpc_owned(self, operation, body):
        # Cleanup belongs to the admitted transaction. Queued reconciliation
        # cannot connect until that cleanup has confirmed or poisoned this client.
        async with self._lock:
            return await self._operate(operation, body)

    async def _operate(self, operation, body):
        connection = None
        try:
            if self._closed or self._cleanup_failed or any(k.startswith('PG') for k in os.environ):
                raise JournalUnavailable('paper_transport_closed')
            with tempfile.TemporaryDirectory(prefix='dashboard-paper-sql-') as folder:
                cert = Path(folder)/'root.crt'; cert.write_bytes(self._ca); cert.chmod(0o600)
                async with asyncio.timeout(8):
                    connection = await psycopg.AsyncConnection.connect(host=HOST,port=5432,
                        dbname='postgres',user=self._login,password=self._password,
                        sslmode='verify-full',sslrootcert=str(cert),sslcert=os.devnull,sslkey=os.devnull,sslcertmode='disable',
                        ssl_min_protocol_version='TLSv1.2',sslnegotiation='postgres',sslsni='1',
                        require_auth='scram-sha-256',channel_binding='require',gssencmode='disable',
                        sslcrl=str(Path(folder)/'absent.crl'),sslcrldir='',passfile=str(Path(folder)/'absent.pass'),
                        service='',connect_timeout=5,application_name='dashboard-paper-v6',
                        options='-c search_path=pg_catalog -c statement_timeout=5000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=7000 -c transaction_timeout=8000 -c synchronous_commit=on')
                    if not connection.pgconn.ssl_in_use or connection.info.server_version//10000 != 17:
                        raise JournalUnavailable('paper_connection_unverified')
                    # Byte cap is applied in SQL before bytes cross the wire.
                    cursor = await connection.execute('WITH x AS MATERIALIZED (SELECT vn_paper_v6.rpc(%s::text,%s::jsonb)::text AS v) SELECT octet_length(v), CASE WHEN octet_length(v)<=%s THEN convert_to(v,\'UTF8\') END FROM x',
                        (operation,json.dumps({'owner_id':self.owner_id,'run_id':self.run_id,**body},separators=(',',':')),MAX_REPLY),prepare=False)
                    row = await cursor.fetchone()
                    if not row or type(row[0]) is not int or not 0 < row[0] <= MAX_REPLY or type(row[1]) is not bytes or len(row[1]) != row[0]:
                        raise JournalUnavailable('paper_readback_bound')
                    value = json.loads(row[1])
                    await connection.commit()
                    return value
        except (Exception, asyncio.CancelledError):
            raise JournalUnavailable('paper_operation_failed_or_uncertain') from None
        finally:
            if connection is not None:
                try:
                    async with asyncio.timeout(1):
                        await connection.close()
                except (Exception, asyncio.CancelledError):
                    self._cleanup_failed = True
                    raise JournalUnavailable('paper_cleanup_unconfirmed') from None

    async def _rpc(self, operation, body):
        # Retain ownership through caller cancellation. Reconciliation may begin
        # only after this admitted operation completes or its own deadline expires.
        task = asyncio.create_task(self._rpc_owned(operation,body))
        self._tasks.add(task)
        def done(t):
            self._tasks.discard(t)
            if not t.cancelled():
                t.exception()
        task.add_done_callback(done)
        return await asyncio.shield(task)

    async def append(self, entry, *, expected_sequence, expected_sha256):
        if type(entry) is not JournalEntry:
            raise JournalUnavailable('invalid_paper_entry')
        value = await self._rpc('append',{'command_id':entry.to_dict()['command_id'],
            'expected_sequence':expected_sequence,'expected_sha256':expected_sha256,
            'wire':base64.b64encode(entry.wire).decode('ascii')})
        return self._entry(value)

    def _entry(self, value):
        raw = _raw(value['wire'])
        entry = JournalEntry(raw)
        row = entry.to_dict()
        if (row['owner_id'],row['run_id']) != (self.owner_id,self.run_id):
            raise JournalUnavailable('paper_original_scope_mismatch')
        if value.get('refused') is True:
            if value.get('reason') != 'stop_committed':
                raise JournalUnavailable('paper_rejection_refused')
            _uuid(value['stop_request_id'])
            raise JournalRejected(raw, 'stop_committed')
        return entry

    async def get(self, command_id):
        value = await self._rpc('get',{'command_id':_uuid(command_id)})
        return None if value is None else self._entry(value)

    async def scan(self, after_sequence=0, limit=25):
        values = await self._rpc('scan',{'after_sequence':after_sequence,'limit':min(limit,25)})
        return [JournalEntry(_raw(row['wire'])) for row in values]

    async def put_artifact(self, kind, sha256, wire):
        value = await self._rpc('put_artifact',{'kind':kind,'sha256':sha256,'wire':base64.b64encode(wire).decode('ascii')})
        return _raw(value['wire'])

    async def get_artifact(self, kind, sha256):
        value = await self._rpc('get_artifact',{'kind':kind,'sha256':sha256})
        return None if value is None else _raw(value['wire'])

    async def artifact_inventory(self, after_sequence=0, limit=25):
        # SQL caps the complete page at8MiB of raw recipes, at most25rows.
        values = await self._rpc('artifact_inventory',{'after_sequence':after_sequence,'limit':min(limit,25)})
        return [{**row,'wire':_raw(row['wire'])} for row in values]

    async def admit_source(self, packet_id, wire):
        value = await self._rpc('admit_source',{'packet_id':_uuid(packet_id),'wire':base64.b64encode(wire).decode('ascii')})
        return self._source(value)

    def _source(self, value):
        if value is None:
            return None
        value = {**value,'wire':_raw(value['wire'])}
        if hashlib.sha256(value['wire']).hexdigest() != value['sha256']:
            raise JournalUnavailable('paper_original_digest_mismatch')
        return value

    async def seal_sources(self, seal_id, start_second, end_second, records_sha256, through_ingest_sequence):
        wire = json.dumps({'kind':'seal','start_second':start_second,'end_second':end_second,
            'records_sha256':records_sha256,'through_ingest_sequence':through_ingest_sequence},sort_keys=True,separators=(',',':')).encode()
        value = await self._rpc('seal_sources',{'packet_id':_uuid(seal_id),'wire':base64.b64encode(wire).decode('ascii')})
        return self._source(value)

    async def get_source(self, packet_id):
        return self._source(await self._rpc('get_source',{'packet_id':_uuid(packet_id)}))

    async def source_inventory(self, after_sequence=0, limit=25):
        values = await self._rpc('source_inventory',{'after_sequence':after_sequence,'limit':min(limit,25)})
        return [self._source(row) for row in values]

    async def control(self, request_id, action):
        return await self._rpc('control',{'request_id':_uuid(request_id),'action':action})

    async def latest_control(self):
        return await self._rpc('latest_control',{})

    async def head(self):
        return await self._rpc('head',{})

    async def close(self):
        self._closed = True
        if self._tasks:
            await asyncio.gather(*(asyncio.shield(t) for t in tuple(self._tasks)),return_exceptions=True)
