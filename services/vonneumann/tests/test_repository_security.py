"""Owner/run defense-in-depth tests against an in-memory PostgREST recorder."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.security_support import A1, B1, USER_A, USER_B, OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.db.repository import VonNeumannRepository


class RecordingQuery:
    def __init__(self, db, table):
        self.db = db
        self.call = {"table": table, "filters": []}

    def update(self, fields):
        self.call.update(operation="update", fields=fields)
        return self

    def insert(self, fields):
        self.call.update(operation="insert", fields=fields)
        return self

    def upsert(self, fields, **options):
        self.call.update(operation="upsert", fields=fields, options=options)
        return self

    def eq(self, field, value):
        self.call["filters"].append((field, value))
        return self

    def execute(self):
        self.db.calls.append(self.call)
        return SimpleNamespace(data=[self.call.get("fields", {})])


class RecordingDB:
    def __init__(self):
        self.calls = []
        self.tables_requested = []

    def table(self, name):
        self.tables_requested.append(name)
        return RecordingQuery(self, name)


class RepositorySecurityTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.db = RecordingDB()
        self.client_getter = self.offline_stack.enter_context(patch(
            "vonneumann.db.repository.get_supabase", return_value=self.db))
        self.repo = VonNeumannRepository(USER_A, A1)

    def test_empty_context_is_rejected_before_creating_client(self):
        for owner, run_id in (("", A1), (USER_A, ""), (None, A1), (USER_A, None)):
            with self.subTest(owner=owner, run_id=run_id):
                self.client_getter.reset_mock()
                with self.assertRaises(ValueError):
                    VonNeumannRepository(owner, run_id)
                self.client_getter.assert_not_called()

    def test_probe_and_trade_updates_include_owner_and_run(self):
        self.repo.update_probe("probe-1", {"state": "DEAD"})
        self.repo.close_trade("trade-1", {"exit_reason": "STOP_LOSS"})
        for call, table, record_id in zip(
            self.db.calls, ("vn_probes", "vn_trades"), ("probe-1", "trade-1")
        ):
            with self.subTest(table=table):
                self.assertEqual(call["table"], table)
                self.assertEqual(set(call["filters"]), {
                    ("id", record_id), ("user_id", USER_A), ("run_id", A1)})
        self.assertEqual(len(self.db.calls), 2)

    def test_update_payload_cannot_replace_identity_even_with_same_value(self):
        for operation in (self.repo.update_probe, self.repo.close_trade):
            for field, value in (("id", "record-1"), ("user_id", USER_A),
                                 ("user_id", USER_B), ("run_id", A1), ("run_id", B1)):
                with self.subTest(operation=operation.__name__, field=field, value=value):
                    with self.assertRaises(ValueError):
                        operation("record-1", {field: value, "state": "DEAD"})
        self.assertEqual(self.db.tables_requested, [])

    def test_colony_operations_cannot_target_another_run(self):
        with self.assertRaises(ValueError):
            self.repo.insert_colony(B1, "genetic_algorithm", {}, "simulation")
        with self.assertRaises(ValueError):
            self.repo.update_colony_status(B1, "stopped")
        self.assertEqual(self.db.tables_requested, [])

    def test_colony_update_filters_by_owner_and_exact_run(self):
        self.repo.update_colony_status(A1, "paused")
        call, = self.db.calls
        self.assertEqual(call["table"], "vn_colonies")
        self.assertEqual(set(call["filters"]), {("id", A1), ("user_id", USER_A)})
        self.assertEqual(call["fields"]["status"], "paused")

    def test_generation_event_cannot_spoof_owner_or_run(self):
        self.repo.upsert_generation_stats({"user_id": USER_B, "run_id": B1, "generation": 7})
        call, = self.db.calls
        self.assertEqual(call["fields"]["user_id"], USER_A)
        self.assertEqual(call["fields"]["run_id"], A1)
        self.assertEqual(call["fields"]["generation"], 7)
        self.assertEqual(call["options"]["on_conflict"], "user_id,run_id,generation")

    def test_probe_insert_owner_comes_from_repository(self):
        self.repo.insert_probe({"probe_id": "probe-1", "user_id": USER_B, "run_id": B1})
        call, = self.db.calls
        self.assertEqual(call["fields"]["user_id"], USER_A)
        self.assertEqual(call["fields"]["run_id"], A1)


if __name__ == "__main__":
    unittest.main()
