"""In-process HTTP regressions: authentication precedes ownership and mutation."""

from __future__ import annotations

import importlib
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.security_support import (
    A1, A2, B1, MISSING, USER_A, USER_B, FakeController,
    OfflineTestMixin, deny_network, token_for,
)

with deny_network():
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from vonneumann.core.colony_manager import ColonyManager
    from vonneumann.server import auth
    app_module = importlib.import_module("vonneumann.server.app")


class HTTPTestBase(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.manager = ColonyManager()
        self.controllers = {
            A1: FakeController(A1, USER_A),
            A2: FakeController(A2, USER_A),
            B1: FakeController(B1, USER_B),  # Deliberately the globally latest colony.
        }
        self.manager._colonies.update(self.controllers)
        self.offline_stack.enter_context(patch.object(app_module, "colony_manager", self.manager))
        self.client = TestClient(app_module.app)
        self.addCleanup(self.client.close)
        self.previous_overrides = dict(app_module.app.dependency_overrides)
        app_module.app.dependency_overrides.clear()
        self.addCleanup(self.restore_overrides)

    def restore_overrides(self):
        app_module.app.dependency_overrides.clear()
        app_module.app.dependency_overrides.update(self.previous_overrides)

    def assert_no_controls(self):
        self.assertTrue(all(not c.controls for c in self.controllers.values()))


class HTTPAuthenticationTests(HTTPTestBase):
    def setUp(self):
        super().setUp()
        self.provider = self.offline_stack.enter_context(patch.object(
            auth, "verify_token_with_provider", new=AsyncMock(return_value={"id": USER_A})))

    def test_missing_and_malformed_auth_cannot_read_or_control(self):
        cases = ({}, {"Authorization": ""}, {"Authorization": "Basic abc"},
                 {"Authorization": "Bearer"}, {"Authorization": "Bearer "},
                 {"x-api-key": "test-only-retired-shared-key"})
        for headers in cases:
            for method, path in (("get", "/api/v1/status"),
                                 ("get", "/api/v1/colonies/"),
                                 ("get", f"/api/v1/colonies/{A1}"),
                                 ("post", f"/api/v1/colonies/{A1}/pause"),
                                 ("post", f"/api/v1/colonies/{A1}/resume"),
                                 ("post", f"/api/v1/colonies/{A1}/stop"),
                                 ("post", "/api/v1/colonies/"),
                                 ("post", "/api/v1/simulation/start"),
                                 ("post", "/api/v1/simulation/pause"),
                                 ("post", "/api/v1/simulation/resume"),
                                 ("post", "/api/v1/simulation/stop")):
                with self.subTest(headers=headers, path=path):
                    options = {"headers": headers}
                    if method == "post":
                        options["json"] = {}
                    response = getattr(self.client, method)(path, **options)
                    self.assertEqual(response.status_code, 401)
        self.provider.assert_not_awaited()
        self.assert_no_controls()

    def test_provider_rejection_is_unauthorized(self):
        self.provider.side_effect = HTTPException(status_code=401, detail="Invalid access token")
        response = self.client.get("/api/v1/colonies/", headers={
            "Authorization": f"Bearer {token_for()}"})
        self.assertEqual(response.status_code, 401)
        self.assert_no_controls()

    def test_expired_token_cannot_control(self):
        response = self.client.post(f"/api/v1/colonies/{A1}/stop", headers={
            "Authorization": f"Bearer {token_for(expires_at=int(time.time()) - 60)}"})
        self.assertEqual(response.status_code, 401)
        self.assert_no_controls()
        self.assertIn(A1, self.manager._colonies)

    def test_provider_outage_fails_closed_as_unavailable(self):
        self.provider.side_effect = HTTPException(status_code=503, detail="Authentication unavailable")
        response = self.client.post(f"/api/v1/colonies/{A1}/pause", headers={
            "Authorization": f"Bearer {token_for()}"})
        self.assertEqual(response.status_code, 503)
        self.assert_no_controls()

    def test_verified_token_allows_only_its_owner(self):
        headers = {"Authorization": f"Bearer {token_for()}"}
        self.assertEqual(self.client.get(f"/api/v1/colonies/{A1}", headers=headers).status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/colonies/{B1}", headers=headers).status_code, 404)

    def test_public_health_does_not_disclose_user_activity(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_cors_allows_only_explicit_origin_and_auth_header(self):
        for origin, expected in (("http://localhost:3000", 200), ("https://attacker.example", 400)):
            with self.subTest(origin=origin):
                response = self.client.options("/api/v1/colonies/", headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization",
                })
                self.assertEqual(response.status_code, expected)
                self.assertEqual(response.headers.get("access-control-allow-origin"),
                                 origin if expected == 200 else None)


class HTTPOwnershipTests(HTTPTestBase):
    def setUp(self):
        super().setUp()
        self.user_id = USER_A

        async def principal():
            return auth.VerifiedUser(id=self.user_id, expires_at=int(time.time()) + 3600)

        app_module.app.dependency_overrides[auth.require_user] = principal

    def test_list_is_owner_filtered_for_both_users(self):
        for user, expected in ((USER_A, {A1, A2}), (USER_B, {B1})):
            with self.subTest(user=user):
                self.user_id = user
                response = self.client.get("/api/v1/colonies/")
                self.assertEqual(response.status_code, 200)
                self.assertEqual({c["colony_id"] for c in response.json()}, expected)

    def test_each_colony_read_checks_ownership(self):
        for user, allowed in ((USER_A, {A1, A2}), (USER_B, {B1})):
            self.user_id = user
            for colony_id in (A1, A2, B1, MISSING):
                with self.subTest(user=user, colony=colony_id):
                    response = self.client.get(f"/api/v1/colonies/{colony_id}")
                    self.assertEqual(response.status_code, 200 if colony_id in allowed else 404)

    def test_foreign_and_unknown_controls_never_reach_controller(self):
        for user, forbidden in ((USER_A, B1), (USER_B, A1)):
            self.user_id = user
            for colony_id in (forbidden, MISSING):
                for action in ("pause", "resume", "stop"):
                    with self.subTest(user=user, colony=colony_id, action=action):
                        response = self.client.post(f"/api/v1/colonies/{colony_id}/{action}")
                        self.assertEqual(response.status_code, 404)
        self.assert_no_controls()

    def test_controls_target_each_owned_colony_explicitly(self):
        for user, colony_ids in ((USER_A, (A1, A2)), (USER_B, (B1,))):
            self.user_id = user
            for colony_id in colony_ids:
                for action in ("pause", "resume", "stop"):
                    with self.subTest(user=user, colony=colony_id, action=action):
                        response = self.client.post(f"/api/v1/colonies/{colony_id}/{action}")
                        self.assertEqual(response.status_code, 200)
                self.assertEqual(self.controllers[colony_id].controls, ["pause", "resume", "stop"])

    def test_legacy_global_controls_are_gone(self):
        for action in ("pause", "resume", "stop"):
            with self.subTest(action=action):
                response = self.client.post(f"/api/v1/simulation/{action}")
                self.assertEqual(response.status_code, 410)
        self.assert_no_controls()

    def test_status_cannot_expose_global_latest_colony(self):
        response = self.client.get("/api/v1/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["colony_id"], A2)
        self.assertNotIn(B1, response.text)
        self.assertNotIn(USER_B, response.text)

    def test_status_is_stopped_when_authenticated_user_owns_no_colony(self):
        self.user_id = "33333333-3333-4333-8333-333333333333"
        response = self.client.get("/api/v1/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "stopped")
        self.assertNotIn(B1, response.text)
        self.assertNotIn(A1, response.text)

    def test_create_rejects_supplied_user_id_before_any_side_effect(self):
        with patch.object(app_module, "VonNeumannRepository") as repo, \
                patch.object(self.manager, "create_colony", new=AsyncMock()) as create:
            for forged_owner in (USER_A, USER_B):
                with self.subTest(owner=forged_owner):
                    response = self.client.post("/api/v1/colonies/", json={"user_id": forged_owner})
                    self.assertEqual(response.status_code, 422)
            repo.assert_not_called()
            create.assert_not_awaited()

    def test_create_derives_repository_and_controller_owner(self):
        fake_repo = MagicMock()
        fake_repo.execute_async = AsyncMock()
        with patch.object(app_module, "VonNeumannRepository", return_value=fake_repo) as repo, \
                patch.object(self.manager, "create_colony", new=AsyncMock()) as create:
            response = self.client.post("/api/v1/colonies/", json={"mode": "simulation"})
            self.assertEqual(response.status_code, 200)
            create.assert_awaited_once()
            self.assertEqual(create.await_args.kwargs["user_id"], USER_A)
            self.assertEqual(repo.call_args.args[0], USER_A)
            self.assertEqual(repo.call_args.kwargs["run_id"], response.json()["colony_id"])
            fake_repo.execute_async.assert_awaited_once()
            self.assertEqual(fake_repo.execute_async.await_args.args[0], "insert_colony")
            self.assertEqual(fake_repo.execute_async.await_args.kwargs["status"], "starting")


if __name__ == "__main__":
    unittest.main()
