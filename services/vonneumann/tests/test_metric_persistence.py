"""Metric precision, policy metadata, and explicit unknown diagnostic storage."""

from copy import deepcopy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_repository_security import RecordingDB

with deny_network():
    from vonneumann.core.types import EventType, ProbeEvent
    from vonneumann.db.repository import EventPersister, VonNeumannRepository


class MetricPersistenceTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.db = RecordingDB()
        self.offline_stack.enter_context(patch("vonneumann.db.repository.get_supabase", return_value=self.db))
        self.repo = VonNeumannRepository(USER_A, A1)
        self.persister = EventPersister(self.repo)
        self.timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.metadata = {
            "fitness_version": "equity-roi-historical-dd-v1",
            "policy_version": "offline-diagnostic-policy",
            "status": "insufficient_samples", "sharpe_ratio": None,
            "return_count": 1, "missing_periods": 0,
            "current_drawdown": 0.0123456789123,
        }
        self.summary = {
            "probe_id": "probe-1", "probe_name": "Metric fixture", "state": "TRADING",
            "genome": {"parent_ids": []}, "initial_capital": 100,
            "current_capital": 112.3456789123, "peak_capital": 127.23456789123,
            "max_drawdown_pct": 20.123456789123, "fitness_score": -.214567891234,
            "total_trades": 3, "winning_trades": 2, "total_pnl": 12.3456789123,
            "sharpe_ratio": None, "metrics": self.metadata,
        }

    async def test_birth_update_and_terminal_events_preserve_authoritative_metrics(self):
        for kind in (EventType.PROBE_BORN, EventType.PROBE_UPDATE,
                     EventType.PROBE_DYING, EventType.PROBE_REPRODUCING):
            with self.subTest(kind=kind):
                await self.persister.handle(ProbeEvent(kind, "probe-1", self.summary, self.timestamp))
                row = self.db.calls[-1]["fields"]
                for field in ("current_capital", "peak_capital", "fitness_score",
                              "total_trades", "winning_trades", "total_pnl"):
                    self.assertEqual(row[field], self.summary[field])
                self.assertEqual(row["max_drawdown"], self.summary["max_drawdown_pct"] / 100)
                self.assertIsNone(row["sharpe_ratio"])
                self.assertEqual(row["metrics"], self.metadata)
                self.assertIsNot(row["metrics"], self.metadata)
        self.assertTrue(all(call["table"] == "vn_probes" for call in self.db.calls))

    async def test_explicit_unknown_clears_previous_diagnostic_and_metadata(self):
        self.repo.update_probe_metrics({"probe_id": "probe-1", "sharpe_ratio": 1.23456789123,
                                        "metrics": self.metadata})
        self.repo.update_probe_metrics({"probe_id": "probe-1", "sharpe_ratio": None, "metrics": None})
        fields = self.db.calls[-1]["fields"]
        self.assertEqual(fields, {"sharpe_ratio": None, "metrics": None})
        self.assertEqual(set(self.db.calls[-1]["filters"]), {
            ("id", "probe-1"), ("user_id", USER_A), ("run_id", A1)})

    async def test_omitted_partial_fields_do_not_clear_saved_diagnostics_or_drawdown(self):
        self.repo.update_probe_metrics({"probe_id": "probe-1", "current_capital": 101.123456789})
        self.assertEqual(self.db.calls[-1]["fields"], {"current_capital": 101.123456789})
        self.repo.update_probe_metrics({"probe_id": "probe-1"})
        self.assertEqual(len(self.db.calls), 1)

    async def test_snapshot_preserves_null_and_full_precision_metadata(self):
        data = {"generation": 2, "tick": 50, "fitness_score": -.214567891234,
                "roi": .123456789123, "sharpe_ratio": None,
                "max_drawdown": .23456789123, "win_rate": 2 / 3,
                "trade_count": 3, "current_capital": 112.3456789123,
                "metrics": self.metadata}
        expected = deepcopy(data)
        await self.persister.handle(ProbeEvent(EventType.FITNESS_SNAPSHOT, "probe-1", data, self.timestamp))
        row = self.db.calls[-1]["fields"]
        for field, value in expected.items():
            self.assertEqual(row[field], value)
        self.assertEqual(row["captured_at"], self.timestamp.isoformat())
        self.assertEqual(row["run_id"], A1)
        data["metrics"]["status"] = "changed-after-write"
        self.assertEqual(row["metrics"], expected["metrics"])

    async def test_available_sharpe_is_not_rounded_or_overwritten(self):
        value = .123456789123456
        data = {**self.summary, "sharpe_ratio": value,
                "metrics": {**self.metadata, "sharpe_ratio": value, "status": "available"}}
        await self.persister.handle(ProbeEvent(EventType.PROBE_UPDATE, "probe-1", data, self.timestamp))
        row = self.db.calls[-1]["fields"]
        self.assertEqual(row["sharpe_ratio"], value)
        self.assertEqual(row["metrics"]["sharpe_ratio"], value)

    async def test_missing_metadata_is_not_assigned_a_new_policy(self):
        self.repo.insert_probe({"probe_id": "legacy-probe", "sharpe_ratio": 2.5})
        row = self.db.calls[-1]["fields"]
        self.assertIsNone(row["metrics"])
        self.assertEqual(row["sharpe_ratio"], 2.5)
