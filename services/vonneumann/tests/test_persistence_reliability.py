"""Persistence acknowledgements, safe errors, and cancellation ordering; no I/O."""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_repository_security import RecordingDB, RecordingQuery

with deny_network():
    from vonneumann.db import connection
    from vonneumann.db.repository import EventPersister, PersistenceError, VonNeumannRepository
    from vonneumann.core.types import EventType, FitnessSnapshot, ProbeEvent, TradeRecord


class PersistenceTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.db = RecordingDB()
        self.offline_stack.enter_context(patch("vonneumann.db.repository.get_supabase", return_value=self.db))
        self.repo = VonNeumannRepository(USER_A, A1)

    def test_every_write_failure_propagates_without_provider_details_or_retry(self):
        secret = "private-provider-body-and-credential"
        trade = TradeRecord("t1", "p1", "SOL/USDC", "BUY", 100, 10)
        snapshot = FitnessSnapshot("p1", 0, 1, 0, 0, 0, 0, 0, 0, 100)
        operations = (
            ("insert_probe", ({"probe_id": "p1"},)),
            ("update_probe", ("p1", {"state": "DEAD"})),
            ("insert_trade", (trade,)),
            ("close_trade", ("t1", {"exit_price": 100})),
            ("insert_fitness_snapshot", (snapshot,)),
            ("insert_colony", (A1, "genetic_algorithm", {}, "simulation")),
            ("update_colony_status", (A1, "failed")),
            ("upsert_generation_stats", ({"generation": 1},)),
        )
        for name, args in operations:
            with self.subTest(operation=name), patch.object(
                self.db, "table", side_effect=RuntimeError(secret)
            ) as table, self.assertLogs("vonneumann.db.repository", "ERROR") as logs:
                with self.assertRaises(PersistenceError) as error:
                    getattr(self.repo, name)(*args)
                self.assertEqual(error.exception.operation, name)
                self.assertEqual(error.exception.code, "persistence_failed")
                self.assertNotIn(secret, str(error.exception))
                self.assertNotIn(secret, "".join(logs.output))
                table.assert_called_once()

    def test_empty_or_missing_write_ack_is_not_success(self):
        for response in (None, SimpleNamespace(data=[]), SimpleNamespace(data=None), SimpleNamespace(data={})):
            with self.subTest(response=response), patch.object(RecordingQuery, "execute", return_value=response):
                with self.assertRaises(PersistenceError):
                    self.repo.update_probe("missing", {"state": "DEAD"})

    def test_failed_status_is_durable_without_losing_original_configuration(self):
        config = {"max_probes": 12, "colony_config": {"enabled_genes": ["ema_fast"]}}
        self.repo.insert_colony(A1, "genetic_algorithm", config, "simulation", status="starting")
        config["max_probes"] = 99
        details = {"failure_code": "startup_failed", "state_persisted": False, "open_positions": 0}
        self.repo.update_colony_status(A1, "failed", details=details)
        fields = self.db.calls[-1]["fields"]
        self.assertEqual(fields["status"], "failed")
        self.assertIn("stopped_at", fields)
        self.assertEqual(fields["config"]["max_probes"], 12)
        self.assertEqual(fields["config"]["runtime"]["failure_code"], "startup_failed")
        self.assertIs(fields["config"]["runtime"]["state_persisted"], True)
        self.assertIs(details["state_persisted"], False)
        self.assertIn(("user_id", USER_A), self.db.calls[-1]["filters"])

    def test_failed_write_does_not_advance_cached_config(self):
        self.repo.insert_colony(A1, "genetic_algorithm", {"seed_capital": 100}, "simulation")
        with patch.object(RecordingQuery, "execute", side_effect=RuntimeError("offline")):
            with self.assertRaises(PersistenceError):
                self.repo.update_colony_status(A1, "failed", {"failure_code": "failure"})
        self.assertEqual(self.repo._colony_config, {"seed_capital": 100})

    def test_invalid_lifecycle_state_is_rejected_before_io(self):
        with self.assertRaises(ValueError):
            self.repo.update_colony_status(A1, "pretend-running")
        self.assertEqual(self.db.tables_requested, [])

    def test_connection_failure_is_sanitized(self):
        with patch("vonneumann.db.repository.get_supabase", side_effect=RuntimeError("private-key")):
            with self.assertRaises(PersistenceError) as error:
                VonNeumannRepository(USER_A, A1)
        self.assertEqual(error.exception.operation, "connect")
        self.assertNotIn("private-key", str(error.exception))

    def test_server_db_client_uses_finite_timeout_and_no_session_storage(self):
        with patch.object(connection, "_client", None), patch.object(connection, "create_client", return_value=self.db) as create:
            self.assertIs(connection.get_supabase(), self.db)
        options = create.call_args.kwargs["options"]
        self.assertEqual(options.postgrest_client_timeout, 5)
        self.assertFalse(options.persist_session)
        self.assertFalse(options.auto_refresh_token)


class AsyncPersistenceTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_write_finishes_before_terminal_status_even_after_second_cancel(self):
        started, release = threading.Event(), threading.Event()
        events = []
        with patch("vonneumann.db.repository.get_supabase", return_value=RecordingDB()):
            repo = VonNeumannRepository(USER_A, A1)

        def pending_write(*args):
            started.set()
            if not release.wait(2):
                raise AssertionError("Test did not release pending write")
            events.append("initial-write-complete")

        with patch.object(repo, "insert_probe", side_effect=pending_write), patch.object(
            repo, "update_colony_status", side_effect=lambda *args: events.append("failed-status")
        ):
            initial = asyncio.create_task(repo.execute_async("insert_probe", {"probe_id": "p1"}))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                initial.cancel()
                await asyncio.sleep(0)
                terminal = asyncio.create_task(repo.execute_async("update_colony_status", A1, "failed"))
                initial.cancel()
                await asyncio.sleep(0.01)
                self.assertFalse(terminal.done())
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):
                await initial
            await terminal
        self.assertEqual(events, ["initial-write-complete", "failed-status"])

    async def test_event_persistence_error_reaches_supervisor(self):
        repo = SimpleNamespace(execute_async=AsyncMock(side_effect=PersistenceError("insert_probe")))
        persister = EventPersister(repo)
        with self.assertRaises(PersistenceError):
            await persister.handle(ProbeEvent(EventType.PROBE_BORN, "p1"))
        repo.execute_async.assert_awaited_once()

    async def test_status_notification_does_not_overwrite_managers_durable_transition(self):
        repo = SimpleNamespace(execute_async=AsyncMock())
        await EventPersister(repo).handle(ProbeEvent(EventType.SIMULATION_STATUS, "genesis", {
            "status": "stopped", "run_id": A1,
        }))
        repo.execute_async.assert_not_awaited()

    async def test_unknown_async_operation_is_rejected(self):
        with patch("vonneumann.db.repository.get_supabase", return_value=RecordingDB()):
            repo = VonNeumannRepository(USER_A, A1)
        with self.assertRaises(ValueError):
            await repo.execute_async("__init__", USER_A, A1)


if __name__ == "__main__":
    unittest.main()
