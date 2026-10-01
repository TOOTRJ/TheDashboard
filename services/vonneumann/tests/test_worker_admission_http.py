"""Independent HTTP admission and actual lifespan regressions; no external I/O."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from tests.security_support import (
    B1, USER_A, USER_B, FakeController, OfflineTestMixin, deny_network, token_for,
)

with deny_network():
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from vonneumann.core.colony_manager import ColonyManager
    from vonneumann.server import auth
    app_module = importlib.import_module("vonneumann.server.app")


START_ROUTES = ("/api/v1/colonies/", "/api/v1/simulation/start")


class AdmissionHTTPTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        previous = dict(app_module.app.dependency_overrides)
        app_module.app.dependency_overrides.clear()
        self.addCleanup(lambda: self._restore_overrides(previous))
        self.provider = self.offline_stack.enter_context(patch.object(
            auth, "verify_token_with_provider", new=AsyncMock(return_value={"id": USER_A})))
        self.offline_stack.enter_context(patch.object(app_module.logging, "basicConfig"))

    @staticmethod
    def _restore_overrides(previous):
        app_module.app.dependency_overrides.clear()
        app_module.app.dependency_overrides.update(previous)

    @staticmethod
    def manager_for(state):
        manager = ColonyManager(max_retained_colonies=1)
        if state != "open":
            # Terminal history still occupies retention capacity. Include a
            # different owner so an exact response also checks non-disclosure.
            retained = FakeController(B1, USER_B)
            retained.lifecycle = "failed"
            manager._colonies[B1] = retained
        manager._draining = state == "closed_draining"
        return manager

    def test_public_health_is_fixed_liveness_even_when_admission_is_closed(self):
        for state in ("open", "closed_capacity", "closed_draining"):
            with self.subTest(state=state), \
                 patch.object(app_module, "colony_manager", self.manager_for(state)), \
                 patch.object(app_module, "VonNeumannRepository") as repository, \
                 TestClient(app_module.app) as client:
                response = client.get("/api/v1/health")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"status": "ok"})
                repository.assert_not_called()
        self.provider.assert_not_awaited()

    def test_readiness_is_authenticated_and_never_claims_durable_readiness(self):
        for state in ("open", "closed_capacity", "closed_draining"):
            manager = self.manager_for(state)
            with self.subTest(state=state), patch.object(app_module, "colony_manager", manager), \
                 patch.object(app_module, "VonNeumannRepository") as repository, \
                 patch.object(manager, "_create_feed") as feed, \
                 TestClient(app_module.app) as client:
                for user_id in (USER_A, USER_B):
                    self.provider.return_value = {"id": user_id}
                    response = client.get("/api/v1/readiness", headers={
                        "Authorization": f"Bearer {token_for(user_id)}"})
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json(), {
                        "status": "not_ready", "admission": state,
                        "durable_recovery": "unavailable",
                    })
                repository.assert_not_called()
                feed.assert_not_called()

    def test_missing_or_malformed_auth_precedes_readiness_and_start_admission(self):
        manager = self.manager_for("closed_draining")
        with patch.object(app_module, "colony_manager", manager), \
             patch.object(manager, "admission_status", side_effect=AssertionError("Admission before auth")) as admission, \
             patch.object(app_module, "VonNeumannRepository") as repository, \
             TestClient(app_module.app) as client:
            for headers in ({}, {"Authorization": "Basic private"}, {"Authorization": "Bearer "}):
                self.assertEqual(client.get("/api/v1/readiness", headers=headers).status_code, 401)
                for path in START_ROUTES:
                    response = client.post(path, json={}, headers=headers)
                    self.assertEqual(response.status_code, 401)
                    self.assertNotIn("accepted", response.json())
            admission.assert_not_called()
            repository.assert_not_called()
        self.provider.assert_not_awaited()

    def test_authentication_outage_does_not_become_a_known_admission_rejection(self):
        manager = self.manager_for("closed_capacity")
        self.provider.side_effect = HTTPException(status_code=503, detail="Authentication unavailable")
        with patch.object(app_module, "colony_manager", manager), \
             patch.object(manager, "admission_status", side_effect=AssertionError("Admission before auth")) as admission, \
             patch.object(app_module, "VonNeumannRepository") as repository, \
             TestClient(app_module.app) as client:
            headers = {"Authorization": f"Bearer {token_for()}"}
            responses = [client.get("/api/v1/readiness", headers=headers)]
            responses.extend(client.post(path, json={}, headers=headers) for path in START_ROUTES)
            for response in responses:
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"detail": "Authentication unavailable"})
            admission.assert_not_called()
            repository.assert_not_called()

    def test_both_start_routes_reject_before_repository_feed_or_controller_construction(self):
        for state, code in (("closed_capacity", "worker_capacity"), ("closed_draining", "worker_draining")):
            manager = self.manager_for(state)
            with self.subTest(state=state), patch.object(app_module, "colony_manager", manager), \
                 patch.object(app_module, "VonNeumannRepository") as repository, \
                 patch.object(manager, "_create_feed") as feed, \
                 patch.object(manager, "create_colony", new=AsyncMock()) as create, \
                 TestClient(app_module.app) as client:
                for path in START_ROUTES:
                    response = client.post(path, json={}, headers={
                        "Authorization": f"Bearer {token_for()}"})
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json(), {"detail": {
                        "code": code, "operation": "start", "accepted": False,
                    }})
                repository.assert_not_called()
                feed.assert_not_called()
                create.assert_not_awaited()
                self.assertEqual(set(manager._colonies), {B1})
                self.assertEqual(manager._start_tasks, {})

    def test_admitted_start_cancelled_by_drain_keeps_run_identity_and_uncertain_response(self):
        for path in START_ROUTES:
            manager = ColonyManager()
            entered = threading.Event()
            release = asyncio.Event()
            writes = []

            async def operation(name, *args, **kwargs):
                if name == "insert_colony":
                    entered.set()
                    await release.wait()
                writes.append((name, args, kwargs))

            repository = SimpleNamespace(execute_async=AsyncMock(side_effect=operation))
            with self.subTest(path=path), patch.object(app_module, "colony_manager", manager), \
                 patch.object(app_module, "VonNeumannRepository", return_value=repository) as construct, \
                 patch.object(manager, "_create_feed") as feed, \
                 patch.object(app_module.ws_manager, "broadcast_to_user", new=AsyncMock()), \
                 TestClient(app_module.app) as client, ThreadPoolExecutor(max_workers=1) as executor:
                request = executor.submit(client.post, path, json={}, headers={
                    "Authorization": f"Bearer {token_for()}"})
                try:
                    self.assertTrue(entered.wait(5), "Accepted start did not reach its initial write")
                    drain = client.portal.start_task_soon(manager.shutdown)
                    readiness = client.get("/api/v1/readiness", headers={
                        "Authorization": f"Bearer {token_for()}"})
                    self.assertEqual(readiness.json()["admission"], "closed_draining")
                finally:
                    # Always release the mock write so a failed assertion cannot
                    # strand a request or the actual application lifespan.
                    client.portal.call(release.set)
                response = request.result(timeout=5)
                self.assertEqual(drain.result(timeout=5)["status"], "complete")
                self.assertEqual(response.status_code, 503)
                detail = response.json()["detail"]
                self.assertEqual(set(detail), {"code", "message", "colony_id", "state_persisted"})
                self.assertEqual(detail["code"], "worker_draining")
                self.assertEqual(str(UUID(detail["colony_id"])), detail["colony_id"])
                self.assertIs(detail["state_persisted"], True)
                self.assertEqual(construct.call_args.args[0], USER_A)
                self.assertEqual(construct.call_args.kwargs["run_id"], detail["colony_id"])
                self.assertEqual([name for name, _, _ in writes], ["insert_colony", "update_colony_status"])
                self.assertEqual(writes[-1][1][1], "failed")
                self.assertEqual(manager.get_owned_colony(detail["colony_id"], USER_A).lifecycle_status, "failed")
                self.assertIsNone(manager.get_owned_colony(detail["colony_id"], USER_B))
                feed.assert_not_called()


class AdmissionLifespanTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.offline_stack.enter_context(patch.object(app_module.logging, "basicConfig"))

    def test_actual_testclient_lifespan_closes_admission_and_awaits_real_shutdown(self):
        manager = ColonyManager()
        with patch.object(app_module, "colony_manager", manager), \
             patch.object(manager, "shutdown", new=AsyncMock(wraps=manager.shutdown)) as shutdown, \
             patch.object(app_module, "logger") as logger:
            with TestClient(app_module.app) as client:
                self.assertEqual(client.get("/api/v1/health").json(), {"status": "ok"})
                self.assertEqual(manager.admission_status(), "open")
                shutdown.assert_not_awaited()
            shutdown.assert_awaited_once()
            self.assertEqual(manager.admission_status(), "closed_draining")
            logger.info.assert_any_call("[Server] Von Neumann service stopped")

    def test_incomplete_actual_lifespan_raises_and_does_not_log_successful_stop(self):
        manager = ColonyManager()
        with patch.object(app_module, "colony_manager", manager), \
             patch.object(manager, "shutdown", new=AsyncMock(return_value={"status": "incomplete", "pending_operations": 1})) as shutdown, \
             patch.object(app_module, "logger") as logger:
            with self.assertRaisesRegex(RuntimeError, "Worker drain incomplete"):
                with TestClient(app_module.app) as client:
                    self.assertEqual(client.get("/api/v1/health").status_code, 200)
            shutdown.assert_awaited_once()
            logger.error.assert_called_once()
            self.assertFalse(any(call.args == ("[Server] Von Neumann service stopped",)
                                 for call in logger.info.call_args_list))


class ExceptionalLifespanTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.offline_stack.enter_context(patch.object(app_module.logging, "basicConfig"))

    async def test_exception_thrown_into_lifespan_still_awaits_shutdown(self):
        manager = ColonyManager()
        with patch.object(app_module, "colony_manager", manager), \
             patch.object(manager, "shutdown", new=AsyncMock(wraps=manager.shutdown)) as shutdown, \
             patch.object(app_module, "logger") as logger:
            with self.assertRaisesRegex(LookupError, "body failure"):
                async with app_module.app.router.lifespan_context(app_module.app):
                    raise LookupError("body failure")
            shutdown.assert_awaited_once()
            self.assertEqual(manager.admission_status(), "closed_draining")
            self.assertFalse(any(call.args == ("[Server] Von Neumann service stopped",)
                                 for call in logger.info.call_args_list))

    async def test_incomplete_shutdown_after_body_exception_still_reports_drain_failure(self):
        manager = ColonyManager()
        with patch.object(app_module, "colony_manager", manager), \
             patch.object(manager, "shutdown", new=AsyncMock(return_value={"status": "incomplete", "pending_operations": 1})) as shutdown, \
             patch.object(app_module, "logger") as logger:
            with self.assertRaisesRegex(RuntimeError, "Worker drain incomplete"):
                async with app_module.app.router.lifespan_context(app_module.app):
                    raise LookupError("body failure")
            shutdown.assert_awaited_once()
            logger.error.assert_called_once()
            self.assertFalse(any(call.args == ("[Server] Von Neumann service stopped",)
                                 for call in logger.info.call_args_list))


if __name__ == "__main__":
    unittest.main()
