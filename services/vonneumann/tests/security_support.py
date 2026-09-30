"""Offline fixtures shared by the worker security regression tests.

Import this module before the application. The settings below affect only the
test process; no developer environment file or real credential is read.
"""

from __future__ import annotations

import base64
from contextlib import ExitStack, contextmanager
import json
import os
import time
from unittest.mock import patch

os.environ.update({
    "PYTHON_DOTENV_DISABLED": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "SUPABASE_URL": "https://security-tests.invalid",
    "NEXT_PUBLIC_SUPABASE_URL": "https://security-tests.invalid",
    "SUPABASE_SERVICE_ROLE_KEY": "test-only-secret-never-use-remotely",
    "SUPABASE_ANON_KEY": "test-only-publishable",
    "SUPABASE_PUBLISHABLE_KEY": "test-only-publishable",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY": "test-only-publishable",
    "VN_API_KEY": "test-only-retired-shared-key",
    "VN_ENVIRONMENT": "test",
    "VN_ALLOWED_ORIGINS": "http://localhost:3000",
    "JUP_API_KEY": "",
    "BIRDEYE_API_KEY": "",
})

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
A1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"
A2 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"
B1 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"
MISSING = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ORIGIN = "http://localhost:3000"


def token_for(user_id=USER_A, expires_at=None, **claims):
    """An explicitly fake JWT, accepted only by our mocked Auth provider."""
    payload = {"sub": user_id, "exp": int(time.time()) + 3600 if expires_at is None else expires_at}
    payload.update(claims)

    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    return ".".join((encode({"alg": "HS256", "typ": "JWT"}), encode(payload), "fake-signature"))


@contextmanager
def deny_network():
    """Fail unexpected outbound I/O without preventing asyncio's socketpair."""
    with ExitStack() as stack:
        for target in ("socket.getaddrinfo", "socket.create_connection",
                       "socket.socket.connect", "socket.socket.connect_ex"):
            stack.enter_context(patch(target, side_effect=AssertionError(
                "Security tests must not contact a network or database")))
        yield


class OfflineTestMixin:
    def setUp(self):
        super().setUp()
        self.offline_stack = ExitStack()
        self.addCleanup(self.offline_stack.close)
        self.offline_stack.enter_context(deny_network())
        self.offline_stack.enter_context(patch(
            "vonneumann.db.repository.get_supabase",
            side_effect=AssertionError("Real repository access is forbidden in security tests"),
        ))


class FakeController:
    """No background task, price feed, or database; records actual controls."""

    def __init__(self, colony_id, user_id):
        self.colony_id = colony_id
        self.run_id = colony_id
        self.user_id = user_id
        self.controls = []
        self.lifecycle = "running"
        self.state_persisted = False

    def status(self):
        return {"colony_id": self.colony_id, "run_id": self.run_id,
                "user_id": self.user_id, "status": self.lifecycle}

    def set_lifecycle(self, status):
        self.lifecycle = status

    async def wait_for_tick(self):
        pass

    async def quiesce(self):
        pass

    def pause(self):
        self.controls.append("pause")

    def resume(self):
        self.controls.append("resume")

    async def stop(self):
        self.controls.append("stop")
