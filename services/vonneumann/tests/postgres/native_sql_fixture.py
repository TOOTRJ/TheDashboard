"""Run the real Linux driver beside only this task's network-none PostgreSQL.

No host ports/mounts, application environment, download, or shared credentials.
An explicitly supplied wheel directory must contain the hash-locked Linux wheels.
Synthetic observer credentials travel through stdin and stay in owned tmpfs.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tarfile
from uuid import uuid4

from tests.postgres import harness, installer_fixture

IMAGE='python:3.12.14-slim-bookworm'
LABEL='com.thedashboard.native-sql-test'
ROOT=Path(__file__).resolve().parents[2]


class NativeDriverContainer:
    def __init__(self, database):
        self.db=database
        self.token=uuid4().hex
        self.name='dashboard-native-sql-'+self.token
        self.container=None

    def _stdin(self, command, data, timeout=30):
        result=subprocess.run(self.db._docker+command,input=data,capture_output=True,
                              env=self.db._env,timeout=timeout)
        if result.returncode:
            raise RuntimeError('Owned native SQL fixture staging failed')
        return result

    def start(self):
        wheels=Path(os.environ.get('DASHBOARD_NATIVE_SQL_WHEELS',''))
        if not wheels.is_absolute() or not wheels.is_dir():
            raise RuntimeError('Explicit hash-locked Linux wheel directory is required')
        files=list(wheels.iterdir())
        if not files or any(p.is_symlink() or not p.is_file() or p.suffix!='.whl' for p in files) or \
           sum(p.stat().st_size for p in files)>150*1024*1024:
            raise RuntimeError('Unreviewed native SQL wheel directory')
        image=json.loads(self.db._command(['image','inspect',IMAGE]).stdout)[0]['Id']
        if not re.fullmatch('sha256:[a-f0-9]{64}',image):
            raise RuntimeError('Invalid native SQL image ID')
        try:
            result=self.db._command(['run','--detach','--pull=never','--name',self.name,
                '--label',LABEL+'='+self.token,'--network','container:'+self.db._container_id,
                '--read-only','--user','1000:1000','--cap-drop=ALL','--security-opt','no-new-privileges',
                '--pids-limit','128','--memory','768m','--cpus','1',
                # Binary wheels need executable mappings. Only this offline,
                # nonroot tmpfs admits them; the image root stays read-only.
                '--tmpfs','/tmp:rw,exec,nosuid,nodev,size=536870912,mode=1777',
                '--entrypoint','/bin/sh',image,'-c','exec sleep 600'],timeout=20)
            self.container=result.stdout.strip()
            if not re.fullmatch('[a-f0-9]{64}',self.container):
                raise RuntimeError('Invalid owned native SQL container ID')
            state=json.loads(self.db._command(['inspect',self.container]).stdout)[0]
            if state['Config']['Labels'].get(LABEL)!=self.token or \
               state['HostConfig']['NetworkMode']!='container:'+self.db._container_id or \
               state['HostConfig'].get('PortBindings') or \
               any(m['Type']!='tmpfs' for m in state['Mounts']):
                raise RuntimeError('Native SQL container isolation check failed')
            buffer=io.BytesIO()
            with tarfile.open(fileobj=buffer,mode='w') as archive:
                # Explicit source extensions exclude env, certificates, caches,
                # app state, git, and other agents' files.
                for directory in ('vonneumann','tests'):
                    for path in sorted((ROOT/directory).rglob('*.py')):
                        if path.is_symlink(): raise RuntimeError('Source symlink refused')
                        archive.add(path,arcname='source/'+str(path.relative_to(ROOT)),recursive=False)
                archive.add(ROOT/'requirements-dev.txt',arcname='requirements-dev.txt')
                for path in sorted(files): archive.add(path,arcname='wheels/'+path.name,recursive=False)
            self._stdin(['exec','-i',self.container,'/bin/sh','-c',
                         'umask 077; mkdir -p /tmp/driver; tar -xf - -C /tmp/driver'],buffer.getvalue())
            installed=self.db._command(['exec',self.container,'python','-m','pip','--isolated','install',
                '--no-index','--find-links=/tmp/driver/wheels','--require-hashes',
                '--target=/tmp/driver/lib','-r','/tmp/driver/requirements-dev.txt'],timeout=60,check=False)
            if installed.returncode:
                raise RuntimeError('Hash-locked offline Linux dependency install failed')
            password=secrets.token_hex(32)
            until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
            self.db.sql(f"ALTER ROLE {installer_fixture.ADMIN} PASSWORD '{password}' VALID UNTIL '{until}';",
                        role=installer_fixture.ADMIN)
            ca=self.db._command(['exec',self.db._container_id,'cat','/tmp/dashboard-pg/root.crt']).stdout
            wrong=self.db._command(['exec',self.db._container_id,'cat','/tmp/dashboard-pg/wrong-root.crt']).stdout
            payload=json.dumps({'admin_password':password,'ca':ca,'wrong_ca':wrong}).encode()
            self._stdin(['exec','-i',self.container,'/bin/sh','-c',
                'umask 077; cat > /tmp/driver/fixture.json'],payload)
            return self
        except BaseException:
            self.close()
            raise

    def run(self):
        result=self.db._command(['exec','--workdir','/tmp/driver/source',
            '--env','PYTHONPATH=/tmp/driver/lib:/tmp/driver/source',
            '--env','PYTHON_DOTENV_DISABLED=1','--env','PYTHONDONTWRITEBYTECODE=1',
            self.container,'python','-m','unittest','tests.postgres.native_sql_cases','-v'],
            timeout=90,check=False)
        return result

    def close(self):
        result=self.db._command(['inspect',self.container or self.name],check=False)
        if result.returncode==0:
            state=json.loads(result.stdout)[0]
            if state['Config']['Labels'].get(LABEL)!=self.token:
                raise RuntimeError('Refusing unowned native SQL container cleanup')
            self.db._command(['rm','--force',state['Id']],timeout=15)
        elif 'no such' not in result.stderr.lower():
            raise RuntimeError('Could not verify native SQL fixture cleanup')
        self.container=None
