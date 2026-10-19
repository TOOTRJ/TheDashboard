"""Supabase user authentication shared by HTTP and WebSocket entry points.

Token identity is verified by the configured Supabase Auth service. JWT claims
are read only after that verification, to bind the subject and socket expiry.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from ..http_tls import HTTPTLSError, require_no_keylog, verified_http_context

require_no_keylog()
import aiohttp
from fastapi import Header, HTTPException

from ..config import SUPABASE_AUTH_API_KEY, SUPABASE_URL, VN_REQUIRE_HTTPS

AUTH_TIMEOUT_SECONDS = 5.0
MAX_AUTH_RESPONSE_BYTES = 65536
MAX_ACCESS_TOKEN_BYTES = 16_384
MAX_SAFE_TIMESTAMP = 2**53 - 1


@dataclass(frozen=True)
class VerifiedUser:
    id: str
    expires_at: int

    @property
    def user_id(self) -> str:
        return self.id


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _auth_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Authentication service unavailable")


def _auth_user_url() -> str:
    """Build the sole verification endpoint from server configuration, not input."""
    try:
        parsed = urlsplit(SUPABASE_URL)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and not any(char.isspace() for char in SUPABASE_URL)
        )
        parsed.port
        if parsed.scheme == "http":
            valid = valid and not VN_REQUIRE_HTTPS and parsed.hostname in {
                "localhost", "127.0.0.1", "::1"
            }
    except ValueError:
        valid = False
    if not valid or not SUPABASE_AUTH_API_KEY:
        raise _auth_unavailable()
    return SUPABASE_URL.rstrip("/") + "/auth/v1/user"


async def verify_token_with_provider(token: str) -> dict:
    """Network adapter; replace this boundary in offline authentication tests."""
    url = _auth_user_url()
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=AUTH_TIMEOUT_SECONDS),
            trust_env=False,
            connector=aiohttp.TCPConnector(ssl=verified_http_context()),
        ) as session:
            async with session.get(
                url,
                headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_AUTH_API_KEY},
                allow_redirects=False,
            ) as response:
                if response.status in {400, 401, 403}:
                    raise _unauthorized()
                if response.status != 200:
                    raise _auth_unavailable()
                body = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    if len(body) + len(chunk) > MAX_AUTH_RESPONSE_BYTES:
                        raise _auth_unavailable()
                    body.extend(chunk)
                def unique(items):
                    value = {}
                    for key, item in items:
                        if key in value:
                            raise ValueError()
                        value[key] = item
                    return value
                data = json.loads(body.decode('utf-8', errors='strict'), object_pairs_hook=unique)
                if not isinstance(data, dict):
                    raise _auth_unavailable()
                return data
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, HTTPTLSError):
        # Provider response bodies and transport exceptions can contain secrets.
        raise _auth_unavailable() from None


async def verify_access_token(token: str) -> VerifiedUser:
    if (
        not isinstance(token, str)
        or not token
        or len(token.encode("utf-8")) > MAX_ACCESS_TOKEN_BYTES
        or any(char.isspace() for char in token)
    ):
        raise _unauthorized()

    data = await verify_token_with_provider(token)
    try:
        user_id = str(UUID(data["id"]))
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token format")
        payload = parts[1]
        claims = json.loads(base64.b64decode(
            payload + "=" * (-len(payload) % 4), altchars=b"-_", validate=True
        ))
        expires_at = claims["exp"]
        if (
            type(expires_at) is not int
            or expires_at <= time.time()
            or expires_at > MAX_SAFE_TIMESTAMP
            or str(UUID(claims["sub"])) != user_id
        ):
            raise ValueError("Invalid verified claims")
    except (KeyError, TypeError, ValueError, AttributeError, binascii.Error):
        raise _unauthorized() from None
    return VerifiedUser(id=user_id, expires_at=expires_at)


async def require_user(authorization: str = Header(default="")) -> VerifiedUser:
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise _unauthorized()
    return await verify_access_token(parts[1])
