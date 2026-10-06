"""Offline certificate, fixed-target protocol and finite-child acceptance."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from tools import native_tls_preflight as preflight
from vonneumann.db.command_sql import HOST


NOW = datetime.now(timezone.utc)


def certificates(*, ca=True, before=None, after=None, key_usage=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Offline preflight CA')])
    builder = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(
        x509.random_serial_number()).not_valid_before(before or NOW-timedelta(minutes=2)).not_valid_after(
        after or NOW+timedelta(days=90)).add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    if key_usage is not None:
        builder = builder.add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=key_usage,
            crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
    cert = builder.sign(key, hashes.SHA256())
    return key, cert, cert.public_bytes(serialization.Encoding.PEM)


class NativeTLSPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key, cls.cert, cls.pem = certificates()

    def test_metadata_has_exact_file_der_hash_and_expiry_without_subject_or_keys(self):
        result = preflight.inspect_ca(self.pem, now=NOW)
        self.assertEqual(result['sha256_pem'], hashlib.sha256(self.pem).hexdigest())
        self.assertEqual(result['certificates'][0]['sha256_der'], self.cert.fingerprint(hashes.SHA256()).hex())
        self.assertGreater(result['certificates'][0]['remaining_seconds'], 89*86400)
        self.assertNotIn('Offline', json.dumps(result))
        self.assertEqual(preflight.HOST, HOST)

    def test_bad_private_trailing_duplicate_oversized_and_non_ca_material_refused(self):
        _, _, leaf = certificates(ca=False)
        _, _, bad_usage = certificates(key_usage=False)
        private = self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption())
        for pem in (b'', b'x'*65537, self.pem+b'password', private+self.pem,
                    self.pem+self.pem, leaf, bad_usage, self.pem.decode()):
            with self.subTest(kind=str(type(pem))):
                with self.assertRaisesRegex(preflight.PreflightError, 'invalid_ca'):
                    preflight.inspect_ca(pem, now=NOW)

    def test_future_expired_and_mixed_validity_bundles_refused(self):
        _, _, future = certificates(before=NOW+timedelta(days=1))
        _, _, expired = certificates(before=NOW-timedelta(days=3), after=NOW-timedelta(days=1))
        for pem in (future, expired, self.pem+expired):
            with self.assertRaisesRegex(preflight.PreflightError, 'ca_not_valid'):
                preflight.inspect_ca(pem, now=NOW)

    def test_multiple_distinct_current_ca_certificates_can_be_reviewed(self):
        _, _, another = certificates()
        self.assertEqual(len(preflight.inspect_ca(self.pem+another, now=NOW)['certificates']), 2)

    def test_fingerprint_refusal_precedes_child_or_network(self):
        with patch.object(preflight.subprocess, 'run') as run:
            for digest in ('a'*64, 'A'*64, 'not a fingerprint', None):
                with self.assertRaises(preflight.PreflightError): preflight.probe(self.pem, digest)
            run.assert_not_called()

    def test_dns_uses_only_pinned_host_and_one_public_address_without_private_fallback(self):
        rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 5432)),
                (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('2606:4700:4700::1111', 5432, 0, 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.1.1.1', 5432))]
        with patch.object(preflight.socket, 'getaddrinfo', return_value=rows) as resolve:
            selected, families = preflight._resolve_address()
        resolve.assert_called_once_with(HOST, 5432, type=socket.SOCK_STREAM)
        self.assertEqual(selected[0], socket.AF_INET6)
        self.assertEqual(families, ['IPv4', 'IPv6'])
        with patch.object(preflight.socket, 'getaddrinfo', return_value=rows[:1]):
            with self.assertRaisesRegex(preflight.PreflightError, 'no_public_address'): preflight._resolve_address()
        with patch.object(preflight.socket, 'getaddrinfo', side_effect=OSError('secret diagnostic')):
            with self.assertRaisesRegex(preflight.PreflightError, 'dns_failed') as error: preflight._resolve_address()
        self.assertNotIn('secret', str(error.exception))

    def test_child_timeout_has_finite_bound_and_sanitized_result(self):
        digest = hashlib.sha256(self.pem).hexdigest()
        with patch.object(preflight.subprocess, 'run', side_effect=subprocess.TimeoutExpired('private', 10)) as run:
            with self.assertRaisesRegex(preflight.PreflightError, 'timeout'): preflight.probe(self.pem, digest)
        args, kwargs = run.call_args
        self.assertEqual(args[0][1], '-I')
        self.assertEqual(args[0][-1], '--internal-probe')
        self.assertNotIn(self.pem.decode(), ' '.join(args[0]))
        self.assertEqual(kwargs['timeout'], 10)
        self.assertEqual(kwargs['input'], self.pem)

    def test_unknown_child_diagnostics_and_oversized_output_are_never_exposed(self):
        digest = hashlib.sha256(self.pem).hexdigest()
        for value in (SimpleNamespace(returncode=1, stdout=b'{"error":"password-secret"}'),
                      SimpleNamespace(returncode=1, stdout=b'private traceback'),
                      SimpleNamespace(returncode=0, stdout=b'x'*8193)):
            with patch.object(preflight.subprocess, 'run', return_value=value):
                with self.assertRaises(preflight.PreflightError) as error: preflight.probe(self.pem, digest)
                self.assertNotIn('secret', str(error.exception))
                self.assertNotIn('private', str(error.exception))

    def test_real_tls_checks_host_ca_and_sends_only_postgres_ssl_request(self):
        self._real_tls()

    def test_real_wrong_ca_or_hostname_is_refused_without_login(self):
        _, _, wrong_ca = certificates()
        self._real_tls(client_ca=wrong_ca, expect_error='tls_unverified')
        self._real_tls(server_hostname='another-project.supabase.co', expect_error='tls_unverified')

    def test_server_ssl_rejection_never_falls_back_to_plaintext_or_login(self):
        self._real_tls(response=b'N', expect_error='tls_refused')

    def _real_tls(self, *, client_ca=None, server_hostname=HOST, response=b'S', expect_error=None):
        leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        leaf = x509.CertificateBuilder().subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, server_hostname)])).issuer_name(self.cert.subject).public_key(
            leaf_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(
            NOW-timedelta(minutes=1)).not_valid_after(NOW+timedelta(days=2)).add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True).add_extension(
            x509.SubjectAlternativeName([x509.DNSName(server_hostname)]), critical=False).sign(self.key, hashes.SHA256())
        observed = []
        failures = []
        with tempfile.TemporaryDirectory(prefix='dashboard-preflight-test-') as directory:
            crt, key = Path(directory)/'leaf.pem', Path(directory)/'leaf.key'
            crt.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
            key.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            key.chmod(0o600)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(crt, key)
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0)); listener.listen(1); listener.settimeout(3)
                address = listener.getsockname()
                def serve():
                    try:
                        connection, _ = listener.accept()
                        with connection:
                            connection.settimeout(3)
                            packet = bytearray()
                            while len(packet) < 8:
                                part = connection.recv(8-len(packet))
                                if not part: break
                                packet.extend(part)
                            observed.append(bytes(packet)); connection.sendall(response)
                            if response == b'S':
                                try:
                                    with context.wrap_socket(connection, server_side=True) as tls:
                                        observed.append(tls.recv(1))
                                except ssl.SSLError:
                                    pass
                            else:
                                observed.append(connection.recv(1))
                    except Exception as error:
                        failures.append(type(error).__name__)
                thread = threading.Thread(target=serve, daemon=True); thread.start()
                selected = ((socket.AF_INET, socket.SOCK_STREAM, 6, address), ['IPv4'])
                with patch.object(preflight, '_resolve_address', return_value=selected):
                    if expect_error:
                        with self.assertRaisesRegex(preflight.PreflightError, expect_error):
                            preflight._probe(client_ca or self.pem)
                    else:
                        result = preflight._probe(self.pem)
                        self.assertTrue(result['tls_verified'])
                        self.assertFalse(result['startup_message_sent'])
                        digest = hashlib.sha256(self.pem).hexdigest()
                        with patch.object(preflight.subprocess, 'run', return_value=SimpleNamespace(
                            returncode=0, stdout=json.dumps(result).encode())):
                            self.assertEqual(preflight.probe(self.pem, digest), result)
                        for changed in ({'host': 'other.supabase.co'}, {'startup_message_sent': True},
                                        {'authentication': 'proven'}, {'port': 6543}, {'extra': 'private'}):
                            with patch.object(preflight.subprocess, 'run', return_value=SimpleNamespace(
                                returncode=0, stdout=json.dumps({**result, **changed}).encode())):
                                with self.assertRaisesRegex(preflight.PreflightError, 'invalid_result'):
                                    preflight.probe(self.pem, digest)
                thread.join(4)
                self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(observed[0], preflight.SSL_REQUEST)
        if not expect_error or response == b'N': self.assertEqual(observed[1:], [b''])


if __name__ == '__main__':
    unittest.main()
