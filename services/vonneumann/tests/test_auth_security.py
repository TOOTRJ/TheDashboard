"""Exercise the real token verifier with a fake HTTP provider, never real Auth."""

from __future__ import annotations

import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import USER_A, USER_B, OfflineTestMixin, deny_network, token_for

with deny_network():
    import aiohttp
    from fastapi import HTTPException
    from vonneumann import config
    from vonneumann.server import auth


class FakeResponse:
    def __init__(self, status=200, body=None, error=None, raw=None):
        self.status = status
        self.body = {"id": USER_A} if body is None else body
        self.error = error
        self.raw = raw
        self.content = self
        self.bytes_delivered = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def iter_chunked(self, size):
        if self.error:
            raise self.error
        raw = json.dumps(self.body).encode() if self.raw is None else self.raw
        for at in range(0, len(raw), size):
            chunk = raw[at:at + size]
            self.bytes_delivered += len(chunk)
            yield chunk


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url, **options):
        self.calls.append((url, options))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class ProviderVerificationTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.offline_stack.enter_context(patch.object(auth, "SUPABASE_URL", "https://security-tests.invalid"))
        self.offline_stack.enter_context(patch.object(auth, "SUPABASE_AUTH_API_KEY", "test-only-publishable"))
        self.offline_stack.enter_context(patch.object(auth, "VN_REQUIRE_HTTPS", False))

    async def test_real_verifier_uses_fixed_auth_host_and_no_redirects_or_proxy_env(self):
        token = token_for()
        session = FakeSession(FakeResponse())
        with patch.object(auth.aiohttp, "ClientSession", return_value=session) as factory:
            principal = await auth.verify_access_token(token)
        self.assertEqual(principal.id, USER_A)
        self.assertGreater(principal.expires_at, time.time())
        self.assertFalse(factory.call_args.kwargs["trust_env"])
        self.assertGreater(factory.call_args.kwargs["timeout"].total, 0)
        self.assertLessEqual(factory.call_args.kwargs["timeout"].total, 5)
        self.assertEqual(session.calls, [("https://security-tests.invalid/auth/v1/user", {
            "headers": {"Authorization": f"Bearer {token}", "apikey": "test-only-publishable"},
            "allow_redirects": False,
        })])

    async def test_http_rejections_outages_and_redirects_fail_closed(self):
        for status in (400, 401, 403, 301, 302, 307, 429, 500, 503):
            with self.subTest(status=status):
                session = FakeSession(FakeResponse(status=status))
                with patch.object(auth.aiohttp, "ClientSession", return_value=session):
                    with self.assertRaises(HTTPException) as caught:
                        await auth.verify_access_token(token_for())
                self.assertEqual(caught.exception.status_code, 401 if status in (400, 401, 403) else 503)

    async def test_transport_errors_and_invalid_provider_json_are_sanitized(self):
        marker = "test-secret-that-must-not-be-exposed"
        cases = (
            aiohttp.ClientConnectionError(marker), asyncio.TimeoutError(marker),
            FakeResponse(error=ValueError(marker)), FakeResponse(body=[]),
        )
        for response in cases:
            with self.subTest(response=type(response).__name__):
                with patch.object(auth.aiohttp, "ClientSession", return_value=FakeSession(response)):
                    with self.assertRaises(HTTPException) as caught:
                        await auth.verify_access_token(token_for())
                self.assertEqual(caught.exception.status_code, 503)
                self.assertNotIn(marker, str(caught.exception.detail))

    async def test_forged_unexpired_claims_do_not_bypass_provider_verification(self):
        session = FakeSession(FakeResponse(status=401))
        with patch.object(auth.aiohttp, "ClientSession", return_value=session):
            with self.assertRaises(HTTPException) as caught:
                await auth.verify_access_token(token_for(expires_at=int(time.time()) + 999999))
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(len(session.calls), 1)

    async def test_oversize_auth_profile_stream_stops_at_finite_limit(self):
        response = FakeResponse(raw=b' ' * (auth.MAX_AUTH_RESPONSE_BYTES * 4))
        with patch.object(auth.aiohttp, 'ClientSession', return_value=FakeSession(response)):
            with self.assertRaises(HTTPException) as caught:
                await auth.verify_access_token(token_for())
        self.assertEqual(caught.exception.status_code, 503)
        self.assertLessEqual(response.bytes_delivered, auth.MAX_AUTH_RESPONSE_BYTES + 8192)

    async def test_duplicate_identity_and_invalid_utf8_fail_closed(self):
        for raw in (b'{"id":"' + USER_A.encode() + b'","id":"' + USER_B.encode() + b'"}', b'{"id":"\xff"}'):
            with patch.object(auth.aiohttp, 'ClientSession', return_value=FakeSession(FakeResponse(raw=raw))):
                with self.assertRaises(HTTPException) as caught:
                    await auth.verify_access_token(token_for())
            self.assertEqual(caught.exception.status_code, 503)

    async def test_claims_must_match_verified_provider_identity_and_expiry(self):
        invalid_tokens = (
            token_for(USER_B), token_for(expires_at=int(time.time()) - 1),
            token_for(exp=0), token_for(exp=True), token_for(exp="9999999999"),
            token_for(exp=2 ** 53), token_for(exp=10 ** 100),
            token_for(exp=float("nan")), token_for(exp=None), token_for(sub=None),
            "header.not-base64!.signature", "not-a-jwt",
        )
        for token in invalid_tokens:
            with self.subTest(token_kind=token.split(".")[0]):
                with patch.object(auth, "verify_token_with_provider", new=AsyncMock(return_value={"id": USER_A})):
                    with self.assertRaises(HTTPException) as caught:
                        await auth.verify_access_token(token)
                self.assertEqual(caught.exception.status_code, 401)

    async def test_bad_provider_identity_is_not_an_authenticated_user(self):
        for body in ({}, {"id": None}, {"id": 123}, {"id": "not-a-uuid"}):
            with self.subTest(body=body):
                with patch.object(auth.aiohttp, "ClientSession", return_value=FakeSession(FakeResponse(body=body))):
                    with self.assertRaises(HTTPException) as caught:
                        await auth.verify_access_token(token_for())
                self.assertEqual(caught.exception.status_code, 401)

    async def test_empty_whitespace_and_oversized_tokens_never_reach_provider(self):
        with patch.object(auth, "verify_token_with_provider", new=AsyncMock()) as provider:
            for token in (None, "", " ", "abc def", "a" * (auth.MAX_ACCESS_TOKEN_BYTES + 1)):
                with self.subTest(length=len(token) if isinstance(token, str) else None):
                    with self.assertRaises(HTTPException) as caught:
                        await auth.verify_access_token(token)
                    self.assertEqual(caught.exception.status_code, 401)
            provider.assert_not_awaited()

    async def test_invalid_server_auth_url_fails_before_http(self):
        urls = ("", "http://example.com", "ftp://security-tests.invalid", "https://name:pass@example.com",
                "https://example.com/arbitrary", "https://example.com?key=bad", "https://example.com#bad")
        with patch.object(auth.aiohttp, "ClientSession") as factory:
            for url in urls:
                with self.subTest(url=url), patch.object(auth, "SUPABASE_URL", url):
                    with self.assertRaises(HTTPException) as caught:
                        await auth.verify_token_with_provider(token_for())
                    self.assertEqual(caught.exception.status_code, 503)
            factory.assert_not_called()

    async def test_production_rejects_plaintext_auth_even_on_loopback(self):
        with patch.object(auth, "SUPABASE_URL", "http://localhost:54321"), \
                patch.object(auth, "VN_REQUIRE_HTTPS", True), \
                patch.object(auth.aiohttp, "ClientSession") as factory:
            with self.assertRaises(HTTPException) as caught:
                await auth.verify_token_with_provider(token_for())
        self.assertEqual(caught.exception.status_code, 503)
        factory.assert_not_called()

    async def test_missing_auth_api_key_fails_before_http(self):
        with patch.object(auth, "SUPABASE_AUTH_API_KEY", ""), \
                patch.object(auth.aiohttp, "ClientSession") as factory:
            with self.assertRaises(HTTPException) as caught:
                await auth.verify_token_with_provider(token_for())
        self.assertEqual(caught.exception.status_code, 503)
        factory.assert_not_called()


class OriginConfigurationTests(OfflineTestMixin, unittest.TestCase):
    def test_empty_configuration_does_not_allow_all_origins(self):
        self.assertEqual(config.parse_allowed_origins(""), ())

    def test_exact_origins_are_normalized_and_deduplicated(self):
        with patch.object(config, "VN_REQUIRE_HTTPS", False):
            self.assertEqual(config.parse_allowed_origins(
                "http://localhost:3000/, https://dashboard.example, http://localhost:3000"
            ), ("http://localhost:3000", "https://dashboard.example"))

    def test_wildcards_paths_credentials_and_public_http_are_rejected(self):
        with patch.object(config, "VN_REQUIRE_HTTPS", False):
            for origin in ("*", "https://*.example.com", "https://example.com/path",
                           "https://user:pass@example.com", "https://example.com?x=y",
                           "https://example.com#fragment", "http://example.com", "http://localhost:bad"):
                with self.subTest(origin=origin), self.assertRaises(ValueError):
                    config.parse_allowed_origins(origin)

    def test_production_rejects_http_localhost_origin(self):
        with patch.object(config, "VN_REQUIRE_HTTPS", True), self.assertRaises(ValueError):
            config.parse_allowed_origins("http://localhost:3000")


if __name__ == "__main__":
    unittest.main()
