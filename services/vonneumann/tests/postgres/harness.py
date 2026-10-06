"""A disposable local PostgreSQL instance, never a connection to an existing DB."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import unittest
import uuid


OPT_IN = "DASHBOARD_ISOLATED_POSTGRES_TESTS"
IMAGE = "public.ecr.aws/supabase/postgres:17.6.1.095"
CONTRACT = Path(__file__).resolve().parents[2] / "db-contract" / "001_fenced_commands.sql"
LABEL = "com.thedashboard.isolated-postgres-test"

BOOTSTRAP = """
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE ROLE anon LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE authenticated LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE service_role LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
CREATE ROLE vn_contract_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE SCHEMA auth;
CREATE TABLE auth.users (id uuid PRIMARY KEY);
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
 SELECT coalesce(nullif(current_setting('request.jwt.claim.sub', true), ''),
                 nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid
$$;
REVOKE ALL ON SCHEMA auth FROM PUBLIC;
REVOKE ALL ON FUNCTION auth.uid() FROM PUBLIC;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role, vn_contract_owner;
GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated, service_role, vn_contract_owner;
GRANT REFERENCES (id) ON auth.users TO vn_contract_owner;
"""


class SqlFailure(RuntimeError):
    """An expected-safe fixture SQL call failed."""

    def __init__(self, result: subprocess.CompletedProcess[str]):
        self.result = result
        super().__init__(result.stderr.strip() or f"psql exited {result.returncode}")


class SqlSession:
    """One independent psql connection with a bounded, background communicate."""

    def __init__(self, command: list[str], source: str, env: dict[str, str], timeout: float):
        self._process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )
        self._done = threading.Event()
        self._result: subprocess.CompletedProcess[str] | None = None
        self._failure: BaseException | None = None

        def communicate() -> None:
            try:
                stdout, stderr = self._process.communicate(source, timeout=timeout)
                self._result = subprocess.CompletedProcess(command, self._process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired as exc:
                self._failure = exc
                self._process.kill()
                try:
                    self._process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            except BaseException as exc:
                self._failure = exc
            finally:
                self._done.set()

        self._thread = threading.Thread(target=communicate, daemon=True)
        self._thread.start()

    @property
    def done(self) -> bool:
        return self._done.is_set()

    def wait(self, timeout: float = 15, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        if not self._done.wait(timeout):
            raise TimeoutError("Owned PostgreSQL test session did not finish before deadline")
        if self._failure is not None:
            raise self._failure
        assert self._result is not None
        if check and self._result.returncode:
            raise SqlFailure(self._result)
        return self._result

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.kill()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise RuntimeError("Owned psql client did not stop")


class IsolatedPostgres:
    """Runs the already-installed image with no network, ports, mounts or secrets.

    Every SQL call uses a new connection authenticated as the requested fixture
    role. No SET ROLE and no inherited Supabase or PostgreSQL URL are used.
    """

    def __init__(self) -> None:
        if os.environ.get(OPT_IN) != "1":
            raise RuntimeError(f"Explicit opt-in required: {OPT_IN}=1")
        binary = shutil.which("docker")
        if binary is None:
            raise RuntimeError("Docker is required; this harness never installs or starts it")
        # Deliberately exclude arbitrary inherited application/API credentials.
        allowed_env = {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "DOCKER_HOST",
                       "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_API_VERSION"}
        self._env = {key: value for key, value in os.environ.items() if key in allowed_env}
        self._docker = [binary]
        self._token = uuid.uuid4().hex
        self.name = f"dashboard-db03a-test-{self._token}"
        self._container_id: str | None = None
        self._sessions: list[SqlSession] = []
        self.identity: dict[str, str] = {}

    def _command(self, args: list[str], *, timeout: float = 10, check: bool = True):
        result = subprocess.run(self._docker + args, text=True, capture_output=True,
                                env=self._env, timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(result.stderr.strip() or "Owned Docker command failed")
        return result

    def _pin_local_daemon(self) -> None:
        host = self._env.get("DOCKER_HOST")
        if not host:
            context = self._env.get("DOCKER_CONTEXT")
            if not context:
                context = self._command(["context", "show"]).stdout.strip()
            host = self._command(["context", "inspect", context, "--format",
                                  "{{.Endpoints.docker.Host}}"]).stdout.strip()
        if not host.startswith("unix:///"):
            raise RuntimeError("Refusing nonlocal Docker daemon; a unix socket is required")
        self._env.pop("DOCKER_HOST", None)
        self._env.pop("DOCKER_CONTEXT", None)
        self._docker.extend(["--host", host])

    def start(self) -> "IsolatedPostgres":
        if self._container_id is not None:
            raise RuntimeError("Harness is already running")
        self._pin_local_daemon()
        # Require an installed image and pin its ID for the entire run.
        image_info = json.loads(self._command(["image", "inspect", IMAGE]).stdout)[0]
        image_id = image_info["Id"]
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
            raise RuntimeError("Docker did not return an immutable image ID")
        script = self.startup_script()
        try:
            result = self._command([
                "run", "--detach", "--pull=never", "--name", self.name,
                "--label", f"{LABEL}={self._token}", "--network", "none",
                "--read-only", "--user", "postgres", "--cap-drop=ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", "128",
                "--memory", "512m", "--cpus", "1",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=268435456,mode=1777",
                "--entrypoint", "/bin/sh", image_id, "-c", script,
            ], timeout=20)
            self._container_id = result.stdout.strip()
            if not re.fullmatch(r"[a-f0-9]{64}", self._container_id):
                raise RuntimeError("Docker did not return an exact container ID")
            state = json.loads(self._command(["inspect", self._container_id]).stdout)[0]
            if (state["Config"]["Labels"].get(LABEL) != self._token
                    or state["HostConfig"]["NetworkMode"] != "none"
                    or state["HostConfig"].get("PortBindings")
                    or any(mount["Type"] != "tmpfs" for mount in state["Mounts"])):
                raise RuntimeError("Owned PostgreSQL container isolation verification failed")
            self.prepare_container()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                ready = self._command(["exec", self._container_id, "pg_isready",
                                       "-h", "/tmp", "-U", "postgres", "-d", "postgres"],
                                      timeout=3, check=False)
                if ready.returncode == 0:
                    self.sql(BOOTSTRAP)
                    self.identity = {
                        "image": IMAGE,
                        "image_id": image_id,
                        "postgres_version": self.scalar("SHOW server_version;"),
                        "network": "none",
                    }
                    return self
                time.sleep(.1)
            raise TimeoutError("Owned PostgreSQL did not become ready within 30 seconds")
        except BaseException:
            self.close()
            raise

    def startup_script(self) -> str:
        """Default fixture is socket-only; subclasses cannot alter Docker isolation."""
        return (
            "set -eu; mkdir -p /tmp/dashboard-pg/data; "
            "initdb -D /tmp/dashboard-pg/data --auth-local=trust --auth-host=reject "
            "--username=postgres --encoding=UTF8 --no-locale >/tmp/dashboard-initdb.log; "
            "exec postgres -D /tmp/dashboard-pg/data -k /tmp "
            "-c listen_addresses='' -c max_connections=30 "
            "-c shared_buffers=32MB -c log_statement=none"
        )

    def prepare_container(self) -> None:
        """Optional owned tmpfs setup before PostgreSQL becomes ready."""

    def begin_sql(self, source: str, *, role: str = "postgres", timeout: float = 10) -> SqlSession:
        if self._container_id is None:
            raise RuntimeError("Owned PostgreSQL container is not running")
        if not re.fullmatch(r"[a-z_][a-z_0-9]*", role):
            raise ValueError("Invalid fixture role")
        if not 0 < timeout <= 60:
            raise ValueError("SQL timeout must be between zero and 60 seconds")
        # Server timeout also terminates the backend if its local Docker client dies.
        server_ms = max(1, int((timeout - min(1, timeout / 2)) * 1000))
        command = self._docker + [
            "exec", "-i", "--env", f"PGOPTIONS=-c statement_timeout={server_ms}",
            self._container_id, "psql", "-X", "-w", "-h", "/tmp", "-U", role,
            "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-A", "-t", "-q",
        ]
        session = SqlSession(command, source, self._env, timeout)
        self._sessions.append(session)
        return session

    def sql(self, source: str, *, role: str = "postgres", check: bool = True,
            timeout: float = 10) -> subprocess.CompletedProcess[str]:
        return self.begin_sql(source, role=role, timeout=timeout).wait(timeout + 6, check=check)

    def scalar(self, source: str, *, role: str = "postgres", timeout: float = 10) -> str:
        return self.sql(source, role=role, timeout=timeout).stdout.strip()

    def wait_until(self, source: str, expected: str = "t", *, timeout: float = 5) -> str:
        deadline = time.monotonic() + timeout
        actual = ""
        while time.monotonic() < deadline:
            actual = self.scalar(source, timeout=min(2, max(.1, deadline - time.monotonic())))
            if actual == expected:
                return actual
            time.sleep(.025)
        raise TimeoutError(f"PostgreSQL fixture condition not reached; last result: {actual!r}")

    def apply_contract(self) -> None:
        self.sql("SET dashboard.contract_rehearsal = 'db03a1-isolated';\n" + CONTRACT.read_text(),
                 timeout=30)

    def close(self) -> None:
        failures = []
        for session in self._sessions:
            try:
                session.close()
            except Exception as exc:
                failures.append(str(exc))
        self._sessions.clear()
        # A run timeout may have created a container without returning its ID.
        identity = self._container_id or self.name
        inspected = self._command(["inspect", identity], check=False)
        if inspected.returncode == 0:
            state = json.loads(inspected.stdout)[0]
            if state["Config"]["Labels"].get(LABEL) != self._token:
                raise RuntimeError("Refusing cleanup: container ownership label does not match")
            self._command(["rm", "--force", state["Id"]], timeout=15)
        elif "no such" not in inspected.stderr.lower():
            failures.append("Could not verify owned container cleanup")
        self._container_id = None
        if failures:
            raise RuntimeError("; ".join(failures))

    def __enter__(self) -> "IsolatedPostgres":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.close()


class PostgresContractTestCase(unittest.TestCase):
    """One disposable database per test class; subclasses own fixture resets."""

    db: IsolatedPostgres

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if os.environ.get(OPT_IN) != "1":
            raise unittest.SkipTest("Use tests.postgres.run --allow-isolated-postgres")
        cls.db = IsolatedPostgres()
        cls.addClassCleanup(cls.db.close)
        cls.db.start()
        cls.db.apply_contract()
