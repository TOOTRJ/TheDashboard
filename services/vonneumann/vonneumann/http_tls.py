"""Explicit HTTP trust for this worker; never inherit TLS key-log or CA paths.

Call ``require_no_keylog`` before importing aiohttp: its pinned connector module
constructs default contexts at import time. This is a cold-process guard, not a
mechanism for undoing a library import or isolating an untrusted OS process.
"""
from __future__ import annotations

import hashlib
import os
import ssl

import certifi


CERTIFI_CA_SHA256 = "9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f"
MAX_CA_BYTES = 1048576


class HTTPTLSError(RuntimeError):
    """A fixed, non-secret local TLS configuration refusal."""


def require_no_keylog() -> None:
    """Refuse the variable's presence without reading or changing its value."""
    if "SSLKEYLOGFILE" in os.environ:
        raise HTTPTLSError("unsupported_tls_keylog_environment")


def verified_http_context() -> ssl.SSLContext:
    """Use only the reviewed certifi bytes, with verification and no key log.

    ``create_default_context`` would consult SSLKEYLOGFILE independently of a
    client's trust_env setting. Loading exact PEM bytes also avoids a second
    file read or fallback to ambient SSL_CERT_FILE/SSL_CERT_DIR/system roots.
    """
    require_no_keylog()
    try:
        with open(certifi.where(), "rb") as source:
            pem = source.read(MAX_CA_BYTES + 1)
        if not pem or len(pem) > MAX_CA_BYTES or hashlib.sha256(pem).hexdigest() != CERTIFI_CA_SHA256:
            raise HTTPTLSError("unsupported_tls_ca_bundle")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.keylog_filename = None
        context.load_verify_locations(cadata=pem.decode("ascii"))
        return context
    except HTTPTLSError:
        raise
    except Exception:
        raise HTTPTLSError("http_tls_unavailable") from None
