"""No provider/DB calls: private child imports, mocks and owned TLS loopback."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from vonneumann import http_tls


SERVICE = Path(__file__).resolve().parents[1]
GUARDED_MODULES = (
    "vonneumann.market.jupiter_feed", "vonneumann.market.birdeye_candles",
    "vonneumann.market.birdeye_feed", "vonneumann.server.auth",
    "vonneumann.core.provider_acquisition", "vonneumann.server.app",
)


def child_env():
    return {"PATH": "/usr/bin:/bin", "PYTHON_DOTENV_DISABLED": "1",
            "PYTHONDONTWRITEBYTECODE": "1", "VN_ENVIRONMENT": "test"}


class HTTPTLSInheritanceTests(unittest.TestCase):
    def test_verified_context_uses_exact_ca_and_never_default_context(self):
        with patch.object(ssl, "create_default_context", side_effect=AssertionError("default context")), \
                patch.dict(os.environ, {"SSL_CERT_FILE": "/missing/task-only-ca",
                                        "SSL_CERT_DIR": "/missing/task-only-ca-dir"}):
            context = http_tls.verified_http_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertIsNone(context.keylog_filename)
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)

    def test_keylog_presence_refuses_before_ca_or_context_without_environment_mutation(self):
        for value in ("", "task-only-private-keylog-marker"):
            with self.subTest(empty=not value), patch.dict(os.environ, {"SSLKEYLOGFILE": value}), \
                    patch.object(http_tls.certifi, "where", side_effect=AssertionError("CA lookup")), \
                    patch.object(ssl, "SSLContext", side_effect=AssertionError("context")):
                before = dict(os.environ)
                with self.assertRaisesRegex(http_tls.HTTPTLSError, "^unsupported_tls_keylog_environment$"):
                    http_tls.verified_http_context()
                self.assertEqual(dict(os.environ), before)

    def test_ca_digest_refusal_precedes_context(self):
        with tempfile.TemporaryDirectory(prefix="dashboard-http-ca-test-") as directory:
            ca = Path(directory) / "fake-ca.pem"
            ca.write_bytes(b"task-owned-unreviewed-ca")
            with patch.object(http_tls.certifi, "where", return_value=str(ca)), \
                    patch.object(ssl, "SSLContext", side_effect=AssertionError("context")):
                with self.assertRaisesRegex(http_tls.HTTPTLSError, "^unsupported_tls_ca_bundle$"):
                    http_tls.verified_http_context()

    def test_missing_oversized_and_invalid_ca_errors_have_fixed_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="dashboard-http-ca-test-") as directory:
            ca = Path(directory) / "private-path-marker.pem"
            cases = (None, b"x" * (http_tls.MAX_CA_BYTES + 1), b"not a PEM bundle")
            for data in cases:
                with self.subTest(kind="missing" if data is None else len(data)):
                    if data is not None:
                        ca.write_bytes(data)
                    else:
                        ca.unlink(missing_ok=True)
                    digest = "0" * 64 if data is None else hashlib.sha256(data).hexdigest()
                    with patch.object(http_tls.certifi, "where", return_value=str(ca)), \
                            patch.object(http_tls, "CERTIFI_CA_SHA256", digest):
                        with self.assertRaises(http_tls.HTTPTLSError) as caught:
                            http_tls.verified_http_context()
                    self.assertIn(str(caught.exception), {"unsupported_tls_ca_bundle", "http_tls_unavailable"})
                    self.assertNotIn("private-path-marker", str(caught.exception))

    def test_cold_guarded_imports_refuse_before_aiohttp_and_create_no_ambient_files(self):
        script = '''import importlib,json,os,socket,sys
sys.path.insert(0,sys.argv[1])
def denied(*args,**kwargs): raise AssertionError("network forbidden")
socket.create_connection=denied
socket.socket.connect=denied
socket.socket.connect_ex=denied
before=dict(os.environ)
try:
 importlib.import_module(sys.argv[2])
except Exception as error:
 print(json.dumps({"type":type(error).__name__,"error":str(error),
   "aiohttp_imported":"aiohttp" in sys.modules,"unchanged":before==dict(os.environ)}))
else:
 raise AssertionError("guard was bypassed")
'''
        with tempfile.TemporaryDirectory(prefix="dashboard-http-import-test-") as directory:
            parent = Path(directory)
            keylog, ca, ca_dir = (parent / name for name in ("fake-keylog", "fake-ca", "fake-ca-directory"))
            for module in GUARDED_MODULES:
                for value in (str(keylog), ""):
                    with self.subTest(module=module, empty=not value):
                        env = {**child_env(), "SSLKEYLOGFILE": value, "SSL_CERT_FILE": str(ca),
                               "SSL_CERT_DIR": str(ca_dir), "HTTPS_PROXY": "https://fake-proxy.invalid"}
                        # Do not use -I: it would hide the CPython environment hook
                        # whose cold-import boundary this regression exercises.
                        result = subprocess.run([sys.executable, "-c", script, str(SERVICE), module],
                            env=env, cwd=directory, capture_output=True, text=True, timeout=20, check=True)
                        self.assertEqual(result.stderr, "")
                        self.assertEqual(json.loads(result.stdout), {"type": "HTTPTLSError",
                            "error": "unsupported_tls_keylog_environment", "aiohttp_imported": False,
                            "unchanged": True})
                        self.assertEqual(list(parent.iterdir()), [])

    def test_cold_httpx_constructor_refuses_keylog_before_transport_and_creates_no_file(self):
        script = '''import json,sys
sys.path.insert(0,sys.argv[1])
from unittest.mock import patch
from vonneumann.db.command_http import DashboardCommandHTTPTransport
with patch("httpx.AsyncHTTPTransport",side_effect=AssertionError("transport forbidden")):
 try: DashboardCommandHTTPTransport("sb_secret_"+"fake_fixture_only_"*3,"11111111-1111-4111-8111-111111111111")
 except Exception as error: print(json.dumps({"type":type(error).__name__,"error":str(error)}))
 else: raise AssertionError("guard was bypassed")
'''
        with tempfile.TemporaryDirectory(prefix="dashboard-http-import-test-") as directory:
            keylog = Path(directory) / "fake-keylog"
            result = subprocess.run([sys.executable, "-c", script, str(SERVICE)],
                env={**child_env(), "SSLKEYLOGFILE": str(keylog)}, cwd=directory,
                capture_output=True, text=True, timeout=20, check=True)
            self.assertEqual(result.stderr, "")
            self.assertEqual(json.loads(result.stdout), {"type": "CommandHTTPError",
                "error": "Command HTTP transport refused operation: tls_configuration_unavailable"})
            self.assertFalse(keylog.exists())


class HTTPAdapterContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_tls_refusal_is_fixed_unavailable_before_session_creation(self):
        from fastapi import HTTPException
        from vonneumann.server import auth
        with patch.object(auth, "_auth_user_url", return_value="https://fake-auth.invalid/auth/v1/user"), \
                patch.object(auth, "verified_http_context", side_effect=http_tls.HTTPTLSError("fake-private-marker")), \
                patch.object(auth.aiohttp, "TCPConnector") as connector, \
                patch.object(auth.aiohttp, "ClientSession") as factory:
            with self.assertRaises(HTTPException) as caught:
                await auth.verify_token_with_provider("fake-only")
            connector.assert_not_called(); factory.assert_not_called()
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail, "Authentication service unavailable")
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertNotIn("fake-private-marker", str(caught.exception))

    async def test_httpx_tls_refusal_preserves_fixed_transport_error_before_construction(self):
        import httpx
        from vonneumann.db import command_http
        with patch.object(command_http, "verified_http_context", side_effect=http_tls.HTTPTLSError("fake-private-marker")), \
                patch.object(httpx, "AsyncHTTPTransport") as factory, \
                patch.object(httpx, "AsyncClient") as client:
            with self.assertRaises(command_http.CommandHTTPError) as caught:
                command_http.DashboardCommandHTTPTransport("sb_secret_" + "fake_fixture_only_" * 3,
                    "11111111-1111-4111-8111-111111111111")
            factory.assert_not_called(); client.assert_not_called()
        self.assertEqual(caught.exception.code, "tls_configuration_unavailable")
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertNotIn("fake-private-marker", str(caught.exception))

    async def test_all_owned_aiohttp_sessions_receive_verified_connector(self):
        modules = {name: importlib.import_module(name) for name in GUARDED_MODULES[:4]}
        context = http_tls.verified_http_context()
        connector = object()
        session = type("FakeSession", (), {"closed": False})()
        feed_cases = (
            (modules[GUARDED_MODULES[0]], lambda module: module.JupiterFeed(api_key="fake-only",
                rpc_url="https://fake-rpc.invalid", birdeye_api_key="fake-only")),
            (modules[GUARDED_MODULES[1]], lambda module: module.BirdeyeCandles("fake-only", {})),
            (modules[GUARDED_MODULES[2]], lambda module: module.BirdeyeFeed(api_key="fake-only")),
        )
        for module, build in feed_cases:
            with self.subTest(module=module.__name__), patch.object(module, "verified_http_context", return_value=context), \
                    patch.object(module.aiohttp, "TCPConnector", return_value=connector) as tcp, \
                    patch.object(module.aiohttp, "ClientSession", return_value=session) as factory:
                feed = build(module)
                self.assertIs(await feed._get_session(), session)
                tcp.assert_called_once_with(ssl=context)
                self.assertIs(factory.call_args.kwargs["connector"], connector)
                self.assertFalse(factory.call_args.kwargs["trust_env"])
        auth = modules[GUARDED_MODULES[3]]
        class AuthSession:
            async def __aenter__(self):
                raise RuntimeError("stop before any dispatch")
            async def __aexit__(self, *args):
                return False
        with patch.object(auth, "verified_http_context", return_value=context), \
                patch.object(auth, "_auth_user_url", return_value="https://fake-auth.invalid/auth/v1/user"), \
                patch.object(auth.aiohttp, "TCPConnector", return_value=connector) as tcp, \
                patch.object(auth.aiohttp, "ClientSession", return_value=AuthSession()) as factory:
            with self.assertRaisesRegex(RuntimeError, "^stop before any dispatch$"):
                await auth.verify_token_with_provider("fake-only")
            tcp.assert_called_once_with(ssl=context)
            self.assertIs(factory.call_args.kwargs["connector"], connector)
            self.assertFalse(factory.call_args.kwargs["trust_env"])

    async def test_httpx_receives_same_explicit_context_and_zero_retry(self):
        import httpx
        from vonneumann.db import command_http
        context = http_tls.verified_http_context()
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"null"))
        with patch.object(command_http, "verified_http_context", return_value=context), \
                patch.object(httpx, "AsyncHTTPTransport", return_value=transport) as factory:
            owner = command_http.DashboardCommandHTTPTransport("sb_secret_" + "fake_fixture_only_" * 3,
                "11111111-1111-4111-8111-111111111111")
        try:
            self.assertIs(factory.call_args.kwargs["verify"], context)
            self.assertFalse(factory.call_args.kwargs["trust_env"])
            self.assertEqual(factory.call_args.kwargs["retries"], 0)
            self.assertIsNone(factory.call_args.kwargs["proxy"])
        finally:
            await owner.aclose()


class HTTPTLSLoopbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.now = datetime.now(timezone.utc)
        cls.ca_key = ec.generate_private_key(ec.SECP256R1())
        cls.name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Task-owned HTTP TLS CA")])
        cls.ca = x509.CertificateBuilder().subject_name(cls.name).issuer_name(cls.name).public_key(
            cls.ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
            cls.now - timedelta(days=2)).not_valid_after(cls.now + timedelta(days=2)).add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(cls.ca_key, hashes.SHA256())
        cls.ca_pem = cls.ca.public_bytes(serialization.Encoding.PEM)

    def test_genuine_tls_validates_owned_ca_and_hostname(self):
        self.handshake()

    def test_genuine_tls_rejects_wrong_hostname(self):
        self.handshake(hostname="wrong-task-owned.invalid", rejected=True)

    def test_genuine_tls_rejects_expired_certificate(self):
        self.handshake(expired=True, rejected=True)

    def test_genuine_tls_rejects_untrusted_certificate(self):
        self.handshake(untrusted=True, rejected=True)

    def handshake(self, *, hostname="task-owned.invalid", expired=False, untrusted=False, rejected=False):
        leaf_key = ec.generate_private_key(ec.SECP256R1())
        leaf = x509.CertificateBuilder().subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "task-owned.invalid")])).issuer_name(self.name).public_key(
            leaf_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
            self.now - timedelta(days=1)).not_valid_after(self.now - timedelta(minutes=1) if expired
            else self.now + timedelta(days=1)).add_extension(x509.BasicConstraints(ca=False, path_length=None),
            critical=True).add_extension(x509.SubjectAlternativeName([x509.DNSName("task-owned.invalid")]),
            critical=False).sign(self.ca_key, hashes.SHA256())
        failures, finished = [], threading.Event()
        with tempfile.TemporaryDirectory(prefix="dashboard-http-tls-loopback-") as directory:
            ca, crt, key = (Path(directory) / name for name in ("ca.pem", "leaf.pem", "leaf.key"))
            ca.write_bytes(self.ca_pem)
            crt.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
            with key.open("xb") as target:
                target.write(leaf_key.private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            key.chmod(0o600)
            server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server.load_cert_chain(crt, key)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0)); listener.listen(1); listener.settimeout(3)
                address = listener.getsockname()
                def serve():
                    try:
                        connection, _ = listener.accept()
                        with connection:
                            connection.settimeout(3)
                            try:
                                with server.wrap_socket(connection, server_side=True) as secured:
                                    self.assertEqual(secured.recv(1), b"x")
                            except ssl.SSLError:
                                if not rejected:
                                    failures.append("unexpected-server-tls-error")
                    except Exception as error:
                        failures.append(type(error).__name__)
                    finally:
                        finished.set()
                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                with patch.object(http_tls.certifi, "where", return_value=str(ca)), \
                        patch.object(http_tls, "CERTIFI_CA_SHA256", hashlib.sha256(self.ca_pem).hexdigest()):
                    client = http_tls.verified_http_context()
                if untrusted:
                    client = http_tls.verified_http_context()
                try:
                    with socket.create_connection(address, timeout=3) as connection:
                        if rejected:
                            with self.assertRaises(ssl.SSLCertVerificationError):
                                client.wrap_socket(connection, server_hostname=hostname)
                        else:
                            with client.wrap_socket(connection, server_hostname=hostname) as secured:
                                secured.sendall(b"x")
                finally:
                    self.assertTrue(finished.wait(4))
                    thread.join(1)
                    self.assertFalse(thread.is_alive())
            self.assertIsNone(client.keylog_filename)
            self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
