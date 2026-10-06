"""Explicit operator preflight; never imported by worker startup.

Inspect a supplied public CA, or probe only the pinned Dashboard PostgreSQL TLS
endpoint. No StartupMessage, authentication, SQL, credentials, retries, pooler,
system CA/client certificates, environment lookup or arbitrary target is used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import socket
import ssl
import struct
import subprocess
import sys
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes

HOST = 'db.fxpxsciltakyypunglzr.supabase.co'
PORT = 5432
MAX_CA_BYTES = 65536
MAX_RESULT_BYTES = 8192
PROBE_SECONDS = 7.0
CHILD_SECONDS = 10.0
SSL_REQUEST = struct.pack('!II', 8, 80877103)
PEM = re.compile(rb'-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\s]+-----END CERTIFICATE-----')


class PreflightError(RuntimeError):
    """Allowlisted codes only; never echo files, certificates or OS diagnostics."""
    CODES = frozenset({'invalid_ca', 'ca_not_valid', 'invalid_fingerprint',
                       'fingerprint_mismatch', 'dns_failed', 'no_public_address',
                       'network_unavailable', 'timeout', 'tls_refused',
                       'tls_unverified', 'invalid_peer', 'probe_failed',
                       'invalid_result', 'ca_file_unavailable'})

    def __init__(self, code):
        self.code = code if type(code) is str and code in self.CODES else 'probe_failed'
        super().__init__('Dashboard native preflight: ' + self.code)


def inspect_ca(pem: bytes, *, now: datetime | None = None) -> dict:
    """Certificate metadata is evidence, not proof of Dashboard provenance."""
    try:
        if type(pem) is not bytes or not 1 <= len(pem) <= MAX_CA_BYTES:
            raise ValueError()
        blocks = PEM.findall(pem)
        if not blocks or PEM.sub(b'', pem).strip():
            raise ValueError()
        when = now if now is not None else datetime.now(timezone.utc)
        if not isinstance(when, datetime) or when.tzinfo is None:
            raise ValueError()
        certificates = []
        seen = set()
        for block in blocks:
            cert = x509.load_pem_x509_certificate(block)
            if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
                raise ValueError()
            try:
                if not cert.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign:
                    raise ValueError()
            except x509.ExtensionNotFound:
                pass
            if not cert.not_valid_before_utc <= when < cert.not_valid_after_utc:
                raise PreflightError('ca_not_valid')
            digest = cert.fingerprint(hashes.SHA256()).hex()
            if digest in seen:
                raise ValueError()
            seen.add(digest)
            certificates.append({'sha256_der': digest,
                                 'not_before_utc': cert.not_valid_before_utc.isoformat(),
                                 'not_after_utc': cert.not_valid_after_utc.isoformat(),
                                 'remaining_seconds': math.floor((cert.not_valid_after_utc-when).total_seconds())})
        # New context only: no system/default roots, client certificates or CRL.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=pem.decode('ascii'))
        if context.cert_store_stats()['x509_ca'] != len(certificates):
            raise ValueError()
        return {'sha256_pem': hashlib.sha256(pem).hexdigest(),
                'certificates': certificates, 'provenance': 'operator must verify exact-project download'}
    except PreflightError:
        raise
    except Exception:
        raise PreflightError('invalid_ca') from None


def _resolve_address():
    try:
        rows = socket.getaddrinfo(HOST, PORT, type=socket.SOCK_STREAM)
    except Exception:
        raise PreflightError('dns_failed') from None
    families = set()
    selected = None
    try:
        for family, kind, protocol, _, address in rows:
            if family in (socket.AF_INET, socket.AF_INET6) and ipaddress.ip_address(address[0]).is_global:
                families.add('IPv4' if family == socket.AF_INET else 'IPv6')
                if selected is None:
                    selected = (family, kind, protocol, address)
    except Exception:
        raise PreflightError('dns_failed') from None
    if selected is None:
        raise PreflightError('no_public_address')
    return selected, sorted(families)


def _probe(pem: bytes) -> dict:
    """Runs in one owned finite child; DNS cannot extend the parent deadline."""
    ca = inspect_ca(pem)
    deadline = time.monotonic() + PROBE_SECONDS
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=pem.decode('ascii'))
    selected, families = _resolve_address()
    raw = None
    tls = None

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise PreflightError('timeout')
        return value

    try:
        family, kind, protocol, address = selected
        raw = socket.socket(family, kind, protocol)
        raw.settimeout(remaining())
        raw.connect(address)
        raw.settimeout(remaining())
        raw.sendall(SSL_REQUEST)
        raw.settimeout(remaining())
        if raw.recv(1) != b'S':
            raise PreflightError('tls_refused')
        raw.settimeout(remaining())
        tls = context.wrap_socket(raw, server_hostname=HOST)
        remaining()
        cert = x509.load_der_x509_certificate(tls.getpeercert(binary_form=True))
        if not cert.not_valid_before_utc <= datetime.now(timezone.utc) < cert.not_valid_after_utc:
            raise PreflightError('invalid_peer')
        version = tls.version()
        cipher = tls.cipher()
        if version not in ('TLSv1.2', 'TLSv1.3') or not cipher or cipher[2] < 128:
            raise PreflightError('tls_unverified')
        return {'host': HOST, 'port': PORT, 'ca_sha256_pem': ca['sha256_pem'],
                'dns_families': families, 'selected_family': 'IPv4' if family == socket.AF_INET else 'IPv6',
                'tls_verified': True, 'tls_version': version, 'cipher_bits': cipher[2],
                'peer_sha256_der': cert.fingerprint(hashes.SHA256()).hex(),
                'peer_not_after_utc': cert.not_valid_after_utc.isoformat(),
                'startup_message_sent': False, 'authentication': 'not tested',
                'scram_channel_binding': 'not tested'}
    except PreflightError:
        raise
    except (TimeoutError, socket.timeout):
        raise PreflightError('timeout') from None
    except ssl.SSLCertVerificationError:
        raise PreflightError('tls_unverified') from None
    except ssl.SSLError:
        raise PreflightError('tls_refused') from None
    except OSError:
        raise PreflightError('network_unavailable') from None
    except Exception:
        raise PreflightError('probe_failed') from None
    finally:
        for connection in (tls, raw):
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass  # The finite owned child exits; no connection is reused.


def probe(pem: bytes, expected_sha256: str) -> dict:
    ca = inspect_ca(pem)
    if type(expected_sha256) is not str or re.fullmatch(r'[a-f0-9]{64}', expected_sha256) is None:
        raise PreflightError('invalid_fingerprint')
    if ca['sha256_pem'] != expected_sha256:
        raise PreflightError('fingerprint_mismatch')
    try:
        result = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--internal-probe'],
                                input=pem, capture_output=True, timeout=CHILD_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        # run kills and reaps only its own child; no shared processes are touched.
        raise PreflightError('timeout') from None
    except Exception:
        raise PreflightError('probe_failed') from None
    try:
        if len(result.stdout) > MAX_RESULT_BYTES:
            raise ValueError()
        data = json.loads(result.stdout)
        if result.returncode:
            if type(data) is dict and set(data) == {'error'}:
                raise PreflightError(data['error'])
            raise ValueError()
        keys = {'host', 'port', 'ca_sha256_pem', 'dns_families', 'selected_family', 'tls_verified',
                'tls_version', 'cipher_bits', 'peer_sha256_der', 'peer_not_after_utc',
                'startup_message_sent', 'authentication', 'scram_channel_binding'}
        if type(data) is not dict or set(data) != keys or data['host'] != HOST or \
           type(data['port']) is not int or data['port'] != PORT or data['ca_sha256_pem'] != expected_sha256 or \
           data['tls_verified'] is not True or data['startup_message_sent'] is not False or \
           data['authentication'] != 'not tested' or data['scram_channel_binding'] != 'not tested' or \
           data['tls_version'] not in ('TLSv1.2', 'TLSv1.3') or \
           type(data['cipher_bits']) is not int or not 128 <= data['cipher_bits'] <= 512 or \
           data['dns_families'] not in (['IPv4'], ['IPv6'], ['IPv4', 'IPv6']) or \
           data['selected_family'] not in data['dns_families'] or \
           re.fullmatch(r'[a-f0-9]{64}', data['peer_sha256_der']) is None:
            raise ValueError()
        if datetime.fromisoformat(data['peer_not_after_utc']).tzinfo is None:
            raise ValueError()
        return data
    except PreflightError:
        raise
    except Exception:
        raise PreflightError('invalid_result') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ca', help='Explicit public CA file; no environment lookup')
    parser.add_argument('--probe', action='store_true', help='One TLS-only request to the pinned Dashboard host')
    parser.add_argument('--expected-sha256', help='Reviewed SHA-256 of exact supplied CA bytes; required to probe')
    parser.add_argument('--internal-probe', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.internal_probe:
            if args.ca or args.probe or args.expected_sha256:
                raise PreflightError('probe_failed')
            value = _probe(sys.stdin.buffer.read(MAX_CA_BYTES + 1))
        else:
            if not args.ca or bool(args.probe) != bool(args.expected_sha256):
                parser.error('--ca is required; --probe and --expected-sha256 must be used together')
            try:
                with Path(args.ca).open('rb') as source:
                    pem = source.read(MAX_CA_BYTES + 1)
            except Exception:
                raise PreflightError('ca_file_unavailable') from None
            value = probe(pem, args.expected_sha256) if args.probe else inspect_ca(pem)
        print(json.dumps(value, sort_keys=True))
        return 0
    except PreflightError as error:
        print(json.dumps({'error': error.code}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
