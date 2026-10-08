"""Explicit closed-host operator command; no paper run, provider or economic write.

Use only a finite canary pair. Keep the original held sessions for operator
revocation, then prove fresh login denial. No startup import or automatic retry.
On success exec the ordinary closed worker. Reports contain allowlisted facts.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from uuid import uuid4

import psycopg
from vonneumann.db.command_sql import DashboardCommandSQLTransport, CommandSQLBounds

CA_SHA = '700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7'


class Refused(RuntimeError):
    pass


def report(phase, **facts):
    print(json.dumps({'dashboard_native_canary': 1, 'phase': phase, **facts}), flush=True)


def configured():
    if (os.environ.get('VN_SERVICE_MODE') != 'closed' or
        os.environ.get('PYTHON_DOTENV_DISABLED') != '1' or
        any(k.startswith('PG') for k in os.environ) or
        any(os.environ.get(k) for k in ('SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_SECRET_KEY',
                                       'RAILWAY_TOKEN', 'RAILWAY_API_TOKEN', 'SUPABASE_DB_PASSWORD'))):
        raise Refused()
    ca = os.environ['VN_DATABASE_CA_PEM'].encode('ascii')
    if hashlib.sha256(ca).hexdigest() != CA_SHA:
        raise Refused()
    owner, run = os.environ['VN_PAPER_OWNER_ID'], os.environ['VN_PAPER_RUN_ID']
    pair = []
    for label in ('ECONOMIC', 'RELAY'):
        pair.append(DashboardCommandSQLTransport(os.environ['VN_' + label + '_LOGIN'],
                    os.environ['VN_' + label + '_PASSWORD'], ca, owner, run, label.lower()))
    if pair[0]._login == pair[1]._login:
        raise Refused()
    return pair, ca, owner, run


async def expect(connection, capability, sql, params, state, message=None):
    try:
        await connection.execute('BEGIN')
        await connection.execute('SET LOCAL ROLE vn_' + capability)
        await connection.execute(sql, params, prepare=False)
    except psycopg.Error as exc:
        if exc.sqlstate != state or (message is not None and exc.diag.message_primary != message):
            raise Refused() from None
        return True
    finally:
        await connection.execute('ROLLBACK')
    raise Refused()


GET = 'SELECT vn_durability.get_command(%s::uuid,%s::uuid,%s::uuid)'
READ = 'SELECT vn_durability.read_outbox(%s::uuid,%s::uuid,1)'


async def default_transport_samples(transport):
    sql = ("WITH r AS MATERIALIZED (SELECT jsonb_build_object('scram',system_user='scram-sha-256:'||session_user::text,"
           "'role',current_user=%s,'ipv6',family(inet_client_addr())=6) AS value) "
           "SELECT octet_length(value::text),convert_to(value::text,'UTF8') FROM r")
    samples = []
    for _ in range(3):
        ready = asyncio.get_running_loop().create_future(); ready.set_result(None)
        start = time.monotonic()
        value = await transport._operate(ready, 'operator-read-only-canary', sql, ('vn_' + transport._capability,))
        if value != {'scram': True, 'role': True, 'ipv6': True}:
            raise Refused()
        samples.append(round(time.monotonic() - start, 6))
    return samples


async def run():
    pair, ca, owner, scope = configured()
    held = []
    temporary = tempfile.TemporaryDirectory(prefix='dashboard-native-canary-', dir='/tmp')
    ca_path = Path(temporary.name) / 'root.crt'; ca_path.write_bytes(ca); ca_path.chmod(0o600)
    absent_crl = Path(temporary.name) / 'absent.crl'
    try:
        samples = []
        for transport in pair:
            samples.append(await default_transport_samples(transport))
            connection = await asyncio.wait_for(transport._connect(ca_path, absent_crl), 3)
            held.append(connection)
            if not connection.pgconn.ssl_in_use or connection.info.server_version // 10000 != 17:
                raise Refused()
        economic, relay = held
        await expect(economic, 'economic', GET, (owner, scope, str(uuid4())), 'P0001', 'run_unavailable')
        await expect(relay, 'relay', READ, (owner, scope), 'P0001', 'outbox_unavailable')
        await expect(economic, 'economic', GET, (str(uuid4()), scope, str(uuid4())), '42501', 'principal_denied')
        await expect(economic, 'economic', GET, (owner, str(uuid4()), str(uuid4())), '42501', 'principal_denied')
        await expect(economic, 'economic', READ, (owner, scope), '42501')
        await expect(relay, 'relay', GET, (owner, scope, str(uuid4())), '42501')
        await expect(economic, 'economic', 'SELECT count(*) FROM vn_durability.runs', (), '42501')
        await expect(relay, 'relay', 'SET LOCAL ROLE vn_economic', (), '42501')
        await expect(economic, 'economic', 'SET LOCAL ROLE vn_contract_owner', (), '42501')
        await expect(economic, 'economic',
                     'SELECT vn_durability.create_run(%s::uuid,%s::uuid,%s::uuid,%s::uuid,%s::jsonb,%s,30)',
                     (owner, scope, str(uuid4()), str(uuid4()), '{}', '10000.00'),
                     '55000', 'release_admission_closed')
        report('waiting_for_original_pair_revocation', tls_verified=True, scram_verified=True,
               channel_binding_required=True, ipv6=True, owner_run_capability_denials=True,
               admission_closed=True, economic_writes=False,
               default_bound_samples_seconds=samples)
        end = time.monotonic() + 45
        revoked = False
        while time.monotonic() < end:
            await asyncio.sleep(1)
            try:
                await expect(economic, 'economic', GET, (owner, scope, str(uuid4())), '42501', 'principal_denied')
                revoked = True; break
            except Refused:
                # Before revocation the scoped nonexistent run is expected.
                await expect(economic, 'economic', GET, (owner, scope, str(uuid4())), 'P0001', 'run_unavailable')
        if not revoked:
            raise Refused()
        await expect(relay, 'relay', READ, (owner, scope), '42501', 'principal_denied')
        for connection in held:
            await connection.close()
        held.clear()
        for transport in pair:
            try:
                unexpected = await asyncio.wait_for(transport._connect(ca_path, absent_crl), 3)
            except psycopg.Error as exc:
                if exc.sqlstate != '28000' and 'is not permitted to log in' not in str(exc):
                    raise Refused() from None
            else:
                await unexpected.close(); raise Refused()
        report('passed', held_session_revocation=True, fresh_login_denied=True,
               paper_run_created=False, admission_closed=True)
    finally:
        for connection in held:
            await connection.close()
        for transport in pair:
            await transport.aclose()
        temporary.cleanup()


if __name__ == '__main__':
    try:
        asyncio.run(asyncio.wait_for(run(), 58))
    except BaseException:
        report('failed', raw_diagnostics_suppressed=True, retry=False)
        raise SystemExit(1) from None
    os.execv('/app/start-worker.sh', ['/app/start-worker.sh'])
