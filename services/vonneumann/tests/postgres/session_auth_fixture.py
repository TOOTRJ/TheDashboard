"""Synthetic TLS/SCRAM inside the owned network-none container, never hosted.

Keys and passwords are generated in memory, passed through stdin, and live only
in this container's tmpfs. No host ports, host mounts, application secrets, or
shared certificate/password files are used. The hostname is a certificate-test
string; hostaddr pins every client to the owned container's loopback interface.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re
import secrets
import subprocess
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from tests.postgres import harness, installer_fixture

HOST='db.fxpxsciltakyypunglzr.supabase.co'
DIRECTORY=Path(__file__).resolve().parents[2]/'db-contract'/'session-auth'
spec=importlib.util.spec_from_file_location('native_auth_builder',DIRECTORY/'build.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def package():
    sql,manifest=builder.build()
    if (DIRECTORY/'package.sql').read_text()!=sql or json.loads((DIRECTORY/'manifest.json').read_text())!=manifest:
        raise ValueError('Native-auth artifacts must be rebuilt and reviewed')
    return installer_fixture.MARKER+sql


class NativePostgres(harness.IsolatedPostgres):
    def startup_script(self):
        return (
            'set -eu; mkdir -p /tmp/dashboard-pg/data; '
            'initdb -D /tmp/dashboard-pg/data --auth-local=trust --auth-host=reject '
            '--username=postgres --encoding=UTF8 --no-locale >/tmp/dashboard-initdb.log; '
            "printf '%s\\n' 'local all all trust' 'hostssl all all 127.0.0.1/32 scram-sha-256' "
            "'host all all 0.0.0.0/0 reject' > /tmp/dashboard-pg/data/pg_hba.conf; "
            'n=0; while [ ! -f /tmp/dashboard-pg/tls-ready ]; do '
            'n=$((n+1)); [ "$n" -le 300 ]; sleep .1; done; '
            'exec postgres -D /tmp/dashboard-pg/data -k /tmp '
            '-c listen_addresses=127.0.0.1 -c max_connections=30 '
            '-c shared_buffers=32MB -c log_statement=none -c password_encryption=scram-sha-256 '
            '-c ssl=on -c ssl_cert_file=/tmp/dashboard-pg/server.crt '
            '-c ssl_key_file=/tmp/dashboard-pg/server.key'
        )

    def write_private(self, name, value):
        if not re.fullmatch(r'[a-z0-9_.-]+',name) or self._container_id is None:
            raise ValueError('Invalid owned fixture file')
        result=subprocess.run(self._docker+['exec','-i',self._container_id,'/bin/sh','-c',
            'umask 077; mkdir -p /tmp/dashboard-pg; cat > /tmp/dashboard-pg/'+name],
            input=value,text=True,capture_output=True,env=self._env,timeout=5)
        if result.returncode:
            raise RuntimeError('Owned fixture file write failed')

    def prepare_container(self):
        now=datetime.now(timezone.utc)
        ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Dashboard synthetic test CA')])
        ca=x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key()).serial_number(
            x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1)).add_extension(
            x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(ca_key,hashes.SHA256())
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cert=x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,HOST)])).issuer_name(
            ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
            now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1)).add_extension(
            x509.SubjectAlternativeName([x509.DNSName(HOST)]),critical=False).sign(ca_key,hashes.SHA256())
        self.write_private('root.crt',ca.public_bytes(serialization.Encoding.PEM).decode())
        wrong_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        wrong_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Dashboard wrong test CA')])
        wrong=x509.CertificateBuilder().subject_name(wrong_name).issuer_name(wrong_name).public_key(wrong_key.public_key()).serial_number(
            x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1)).add_extension(
            x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(wrong_key,hashes.SHA256())
        self.write_private('wrong-root.crt',wrong.public_bytes(serialization.Encoding.PEM).decode())
        self.write_private('server.crt',cert.public_bytes(serialization.Encoding.PEM).decode())
        self.write_private('server.key',key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode())
        self.write_private('tls-ready','ready')

    def begin_native(self, role, capability, source, *, timeout=10, host=HOST, sslmode='verify-full', password_file=None, root='root.crt'):
        if self._container_id is None or not re.fullmatch(r'vn_native_[a-f0-9]{32}',role):
            raise ValueError('Invalid native fixture role')
        if capability not in ('economic','relay') or host not in (HOST,'wrong.example') or sslmode not in ('verify-full','disable'):
            raise ValueError('Unreviewed fixture connection option')
        if root not in ('root.crt','wrong-root.crt'):
            raise ValueError('Unreviewed fixture CA')
        if not 0<timeout<=60:
            raise ValueError('Unbounded fixture session')
        password_file=role+'.pgpass' if password_file is None else password_file
        if not re.fullmatch(r'[a-z0-9_.-]+',password_file):
            raise ValueError('Invalid owned password file')
        server_ms=max(1,int((timeout-min(1,timeout/2))*1000))
        conn=f'host={host} hostaddr=127.0.0.1 port=5432 dbname=postgres user={role} sslmode={sslmode} '
        conn+='sslrootcert=/tmp/dashboard-pg/'+root+' channel_binding=require connect_timeout=2'
        command=self._docker+['exec','-i','--env','PGPASSFILE=/tmp/dashboard-pg/'+password_file,
            '--env',f'PGOPTIONS=-c statement_timeout={server_ms}',self._container_id,'psql','-X','-w',
            '-d',conn,'-v','ON_ERROR_STOP=1','-v','VERBOSITY=verbose','-A','-t','-q']
        session=harness.SqlSession(command,'SET ROLE vn_'+capability+';\n'+source,self._env,timeout)
        self._sessions.append(session)
        return session

    def native(self, role, capability, source, *, check=True, timeout=10, **options):
        return self.begin_native(role,capability,source,timeout=timeout,**options).wait(timeout+6,check=check)

    def issue(self, owner, run, capability, *, expires=300, recovery=600, delay=0):
        # Fixture-only DBA provisioning, NOT an application issuer. Lifetime
        # overrides are bounded by the SQL schema, and no secret is returned.
        role='vn_native_'+uuid4().hex
        password=secrets.token_hex(32)
        until=(datetime.now(timezone.utc)+timedelta(seconds=recovery)).isoformat()
        self.sql(f"CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS "
            f"CONNECTION LIMIT 2 PASSWORD '{password}' VALID UNTIL '{until}';\n"
            f'GRANT vn_{capability} TO {role} WITH ADMIN FALSE,INHERIT FALSE,SET TRUE;',role=installer_fixture.ADMIN)
        self.write_private(role+'.pgpass',f'*:5432:postgres:{role}:{password}\n')
        self.sql(f"SET ROLE vn_contract_owner; INSERT INTO vn_access.bindings "
            "(issuance_id,principal_oid,principal_name,capability,owner_id,run_id,issued_at,not_before,expires_at,recovery_until) "
            f"WITH stamp AS MATERIALIZED (SELECT clock_timestamp() AS at) SELECT '{uuid4()}',oid,rolname,'{capability}','{owner}','{run}',at,"
            f"at+interval '{delay} seconds',at+interval '{expires} seconds',"
            f"'{until}' FROM pg_roles,stamp WHERE rolname='{role}';",role='postgres')
        return role


def start(test_class):
    db=NativePostgres()
    test_class.addClassCleanup(db.close)
    db.start()
    db.sql('CREATE ROLE vn_test_admin LOGIN SUPERUSER;')
    db.sql(installer_fixture.HOSTED_BOOTSTRAP,role=installer_fixture.ADMIN)
    db.sql(package(),timeout=30)
    return db
