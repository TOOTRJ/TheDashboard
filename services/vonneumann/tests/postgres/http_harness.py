"""Opt-in local PostgREST fixture with an owned private Docker bridge.

Never reads application credentials, exposes PostgreSQL to the host, pulls images,
or connects to an existing database. Fake JWTs test PostgREST, not Supabase's
opaque-key gateway. Cleanup verifies ownership before removing exact resources.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import time

from tests.postgres.harness import IsolatedPostgres, IMAGE, LABEL, BOOTSTRAP

POSTGREST_IMAGE = "public.ecr.aws/supabase/postgrest:v14.5"
FAKE_JWT_SECRET = "dashboard_local_fixture_only_0123456789abcdef"


def fixture_jwt(role, owner=None, *, expired=False, audience="dashboard-fixture"):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=")
    claims = {"role": role, "aud": audience, "exp": int(time.time()) + (-60 if expired else 300)}
    if owner: claims["sub"] = owner
    message = encode({"alg": "HS256", "typ": "JWT"}) + b"." + encode(claims)
    signature = base64.urlsafe_b64encode(hmac.new(FAKE_JWT_SECRET.encode(), message, hashlib.sha256).digest()).rstrip(b"=")
    return (message + b"." + signature).decode()


class IsolatedPostgREST(IsolatedPostgres):
    api_schemas = ("vn_durability",)

    def __init__(self):
        super().__init__()
        self.network = f"dashboard-http-test-{self._token}"
        self.http_name = f"dashboard-postgrest-test-{self._token}"
        self._http_id = None
        self._network_id = None
        self.endpoint = None

    def _image(self, reference):
        value = json.loads(self._command(["image", "inspect", reference]).stdout)[0]["Id"]
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
            raise RuntimeError("Fixture image ID is invalid")
        return value

    def start(self):
        self._pin_local_daemon()
        image_id, http_image_id = self._image(IMAGE), self._image(POSTGREST_IMAGE)
        try:
            # Docker 29 internal networks suppress published ports. Use a
            # separate owned bridge with outbound IP masquerading disabled;
            # only HTTP is host-published, exclusively on loopback. This is not
            # a general egress firewall; every fixture URL is local/owned.
            self._network_id = self._command(["network", "create", "--opt", "com.docker.network.bridge.enable_ip_masquerade=false", "--label", f"{LABEL}={self._token}", self.network]).stdout.strip()
            network = self._verify_network()
            subnet = ipaddress.ip_network(network["IPAM"]["Config"][0]["Subnet"])
            if subnet.version != 4 or not subnet.is_private:
                raise RuntimeError("Fixture network requires a private IPv4 subnet")
            script = (
                "set -eu; mkdir -p /tmp/dashboard-pg/data; "
                "initdb -D /tmp/dashboard-pg/data --auth-local=trust --auth-host=trust "
                "--username=postgres --encoding=UTF8 --no-locale >/tmp/dashboard-initdb.log; "
                f"echo 'host postgres authenticator {subnet} trust' >>/tmp/dashboard-pg/data/pg_hba.conf; "
                "exec postgres -D /tmp/dashboard-pg/data -k /tmp -c listen_addresses='*' "
                "-c max_connections=30 -c shared_buffers=32MB -c log_statement=none"
            )
            self._container_id = self._command([
                "run", "--detach", "--pull=never", "--name", self.name, "--label", f"{LABEL}={self._token}",
                "--network", self.network, "--network-alias", "fixture-db", "--read-only", "--user", "postgres",
                "--cap-drop=ALL", "--security-opt", "no-new-privileges", "--pids-limit", "128", "--memory", "512m", "--cpus", "1",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=268435456,mode=1777", "--entrypoint", "/bin/sh", image_id, "-c", script,
            ], timeout=20).stdout.strip()
            self._verify_container(self._container_id, postgres=True)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                result = self._command(["exec", self._container_id, "pg_isready", "-h", "/tmp", "-U", "postgres"], timeout=3, check=False)
                if result.returncode == 0: break
                time.sleep(.1)
            else: raise TimeoutError("Owned fixture PostgreSQL readiness timed out")
            self.sql(BOOTSTRAP + "CREATE ROLE authenticator LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS; GRANT anon,authenticated,service_role TO authenticator;")
            self.apply_contract()
            self.identity = {"postgres_image": image_id, "postgrest_image": http_image_id,
                             "postgres_version": self.scalar("SHOW server_version;"), "network": "owned-bridge-no-masquerade"}
            self.start_http("commit", image_id=http_image_id)
            return self
        except BaseException:
            self.close()
            raise

    def _verify_network(self):
        state = json.loads(self._command(["network", "inspect", self._network_id]).stdout)[0]
        if (state["Name"] != self.network or state.get("Labels", {}).get(LABEL) != self._token
                or state.get("Options", {}).get("com.docker.network.bridge.enable_ip_masquerade") != "false"):
            raise RuntimeError("Owned fixture bridge verification failed")
        if set(state.get("Containers", {})) - {self._container_id, self._http_id}:
            raise RuntimeError("Fixture bridge contains an unowned container")
        return state

    def _verify_container(self, identifier, *, postgres=False):
        state = json.loads(self._command(["inspect", identifier]).stdout)[0]
        if (state["Config"]["Labels"].get(LABEL) != self._token or not state["HostConfig"]["ReadonlyRootfs"]
                or state["HostConfig"]["NetworkMode"] != self.network
                or set(state["NetworkSettings"]["Networks"]) != {self.network}
                or any(m["Type"] != "tmpfs" for m in state["Mounts"])):
            raise RuntimeError("Owned fixture container verification failed")
        ports = state["HostConfig"].get("PortBindings") or {}
        if postgres and ports: raise RuntimeError("PostgreSQL fixture must not publish ports")
        if not postgres and (set(ports) != {"3000/tcp"} or len(ports["3000/tcp"]) != 1
                or ports["3000/tcp"][0]["HostIp"] != "127.0.0.1"):
            raise RuntimeError("HTTP fixture must publish only one loopback port")
        return state

    def start_http(self, transaction_end, *, image_id=None):
        if transaction_end not in ("commit", "rollback", "commit-allow-override", "rollback-allow-override"):
            raise ValueError("Unsupported fixture transaction policy")
        if self.api_schemas not in (("vn_durability",), ("vn_durability", "vn_read")):
            raise ValueError("Unsupported fixture schema exposure")
        self.stop_http()
        self._verify_network()
        image_id = image_id or self.identity["postgrest_image"]
        self._http_id = self._command([
            "run", "--detach", "--pull=never", "--name", self.http_name, "--label", f"{LABEL}={self._token}",
            "--network", self.network, "--read-only", "--user", "1000:1000", "--cap-drop=ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "128", "--memory", "256m", "--cpus", "1",
            "--publish", "127.0.0.1::3000", "--env", "PGRST_DB_URI=postgres://authenticator@fixture-db:5432/postgres",
            "--env", "PGRST_DB_SCHEMAS=" + ",".join(self.api_schemas), "--env", "PGRST_DB_ANON_ROLE=anon",
            "--env", f"PGRST_JWT_SECRET={FAKE_JWT_SECRET}", "--env", "PGRST_JWT_AUD=dashboard-fixture",
            "--env", f"PGRST_DB_TX_END={transaction_end}", "--env", "PGRST_DB_POOL=2", "--env", "PGRST_LOG_LEVEL=error", image_id,
        ], timeout=20).stdout.strip()
        state = self._verify_container(self._http_id)
        bindings = state["NetworkSettings"]["Ports"].get("3000/tcp")
        if not bindings or len(bindings) != 1 or bindings[0]["HostIp"] != "127.0.0.1":
            raise RuntimeError("Fixture HTTP loopback binding unavailable: " + repr({"bindings": bindings, "state": state["State"]["Status"], "exit": state["State"]["ExitCode"]}))
        self.endpoint = "http://127.0.0.1:" + bindings[0]["HostPort"]
        # Ordinary safe metadata only; never dump unrestricted image environment/logs.
        self.identity["postgrest_version"] = self._command(["exec", self._http_id, "/bin/postgrest", "--version"]).stdout.strip()
        import httpx
        deadline = time.monotonic() + 15
        observed = "no response"
        with httpx.Client(trust_env=False, timeout=1) as client:
            while time.monotonic() < deadline:
                try:
                    response = client.get(self.endpoint + "/", headers={"Authorization": "Bearer " + fixture_jwt("service_role")})
                    if response.status_code == 200: return
                    observed = str(response.status_code)
                    try: observed += " " + str(response.json().get("code", ""))
                    except (ValueError, AttributeError): pass
                except httpx.HTTPError as error: observed = type(error).__name__
                time.sleep(.1)
        state = self._verify_container(self._http_id)
        raise TimeoutError(f"Owned fixture PostgREST readiness timed out ({observed}; state {state['State']['Status']}; exit {state['State']['ExitCode']})")

    def stop_http(self):
        identity = self._http_id or self.http_name
        state = self._command(["inspect", identity], check=False)
        if state.returncode == 0:
            value = json.loads(state.stdout)[0]
            if value["Config"]["Labels"].get(LABEL) != self._token:
                raise RuntimeError("Refusing unrelated HTTP fixture cleanup")
            self._command(["rm", "--force", value["Id"]], timeout=15)
        elif "no such" not in state.stderr.lower(): raise RuntimeError("HTTP fixture cleanup could not verify ownership")
        self._http_id = None
        self.endpoint = None

    def close(self):
        self.stop_http()
        super().close()
        identity = self._network_id or self.network
        result = self._command(["network", "inspect", identity], check=False)
        if result.returncode == 0:
            state = json.loads(result.stdout)[0]
            if state.get("Labels", {}).get(LABEL) != self._token or state.get("Containers"):
                raise RuntimeError("Refusing network cleanup: ownership mismatch or remaining containers")
            self._command(["network", "rm", state["Id"]], timeout=15)
        elif "no such" not in result.stderr.lower() and "not found" not in result.stderr.lower(): raise RuntimeError("Fixture network cleanup could not verify ownership")
        self._network_id = None
