"""Offline persistence checks for event time independent of processing time."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_repository_security import RecordingDB

with deny_network():
    from vonneumann.core.types import EventType, ProbeEvent
    from vonneumann.db.repository import EventPersister, VonNeumannRepository


class PersistenceClockTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.db = RecordingDB()
        self.offline_stack.enter_context(patch(
            "vonneumann.db.repository.get_supabase", return_value=self.db))
        self.repo = VonNeumannRepository(USER_A, A1)
        self.persister = EventPersister(self.repo)

    def event(self, event_type, timestamp, **changes):
        data = {
            "trade_id": "fixed-trade-id", "pair": "SOL/USDC",
            "entry_price": 100.0, "amount": 20.0, "exit_price": 110.0,
            "exit_reason": "TAKE_PROFIT", "genome": {"parent_ids": []},
            "initial_capital": 100.0, "current_capital": 100.0,
            "peak_capital": 100.0, "generation": 0, "tick": 1,
            "state": "DEAD", "death_reason": "max_lifespan",
            "total_trades": 0, "winning_trades": 0, "total_pnl": 0.0,
            "fitness_score": 0.0, "max_drawdown_pct": 0.0,
        }
        data.update(changes)
        return ProbeEvent(event_type, "fixed-probe-id", data, timestamp=timestamp)

    async def test_simulated_epoch_is_preserved_for_every_lifecycle_timestamp(self):
        timestamp = datetime.fromtimestamp(0, timezone.utc)
        for event_type, table, field in (
            (EventType.PROBE_BORN, "vn_probes", "born_at"),
            (EventType.TRADE_OPENED, "vn_trades", "opened_at"),
            (EventType.TRADE_CLOSED, "vn_trades", "closed_at"),
            (EventType.PROBE_DEAD, "vn_probes", "died_at"),
            (EventType.FITNESS_SNAPSHOT, "vn_fitness_snapshots", "captured_at"),
            (EventType.GENERATION_COMPLETE, "vn_generation_stats", "ended_at"),
        ):
            with self.subTest(event_type=event_type):
                await self.persister.handle(self.event(event_type, timestamp))
                row = self.db.calls[-1]
                self.assertEqual(row["table"], table)
                self.assertEqual(row["fields"][field], "1970-01-01T00:00:00+00:00")

    async def test_transition_intent_never_writes_a_terminal_timestamp(self):
        timestamp = datetime.fromtimestamp(0, timezone.utc)
        for event_type, state in ((EventType.PROBE_DYING, "DYING"),
                                   (EventType.PROBE_REPRODUCING, "REPRODUCING")):
            await self.persister.handle(self.event(event_type, timestamp))
            fields = self.db.calls[-1]["fields"]
            self.assertEqual(fields["state"], state)
            self.assertNotIn("died_at", fields)
            self.assertNotIn("death_reason", fields)

    async def test_payload_dates_cannot_replace_the_authoritative_event_clock(self):
        timestamp = datetime(2020, 1, 1, 0, 1, 2, 345678, tzinfo=timezone.utc)
        for event_type, field in (
            (EventType.PROBE_BORN, "born_at"),
            (EventType.PROBE_DEAD, "died_at"),
            (EventType.TRADE_OPENED, "opened_at"),
            (EventType.TRADE_CLOSED, "closed_at"),
            (EventType.FITNESS_SNAPSHOT, "captured_at"),
            (EventType.GENERATION_COMPLETE, "ended_at"),
        ):
            with self.subTest(event_type=event_type):
                event = self.event(event_type, timestamp, **{field: "2099-12-31T23:59:59+00:00"})
                await self.persister.handle(event)
                self.assertEqual(self.db.calls[-1]["fields"][field], timestamp.isoformat())

    async def test_aware_offset_is_normalized_to_the_same_utc_instant(self):
        local_time = datetime(2020, 1, 1, 1, 2, 3, tzinfo=timezone(timedelta(hours=-7)))
        expected = "2020-01-01T08:02:03+00:00"
        for event_type, field in ((EventType.PROBE_BORN, "born_at"),
                                  (EventType.TRADE_OPENED, "opened_at"),
                                  (EventType.FITNESS_SNAPSHOT, "captured_at")):
            with self.subTest(event_type=event_type):
                await self.persister.handle(self.event(event_type, local_time))
                self.assertEqual(self.db.calls[-1]["fields"][field], expected)

    async def test_naive_and_non_datetime_timestamps_fail_before_database_access(self):
        for timestamp in (None, 0, False, float("inf"), "2020-01-01T00:00:00Z",
                          datetime(2020, 1, 1)):
            for event_type in (EventType.PROBE_BORN, EventType.TRADE_OPENED,
                               EventType.TRADE_CLOSED, EventType.PROBE_DYING,
                               EventType.FITNESS_SNAPSHOT):
                with self.subTest(timestamp=timestamp, event_type=event_type):
                    with self.assertRaises(ValueError) as error:
                        await self.persister.handle(self.event(event_type, timestamp))
                    self.assertEqual(str(error.exception),
                                     "Event timestamp must be a valid timezone-aware datetime")
        self.assertEqual(self.db.tables_requested, [])

    async def test_unrepresentable_utc_time_fails_before_database_access(self):
        timestamp = datetime.min.replace(tzinfo=timezone(timedelta(hours=1)))
        with self.assertRaises(ValueError):
            await self.persister.handle(self.event(EventType.TRADE_OPENED, timestamp))
        self.assertEqual(self.db.tables_requested, [])

    async def test_replaying_same_events_preserves_timestamped_database_payloads(self):
        start = datetime(2001, 1, 1, tzinfo=timezone.utc)
        events = [self.event(kind, start + timedelta(seconds=index * 60))
                  for index, kind in enumerate((EventType.PROBE_BORN, EventType.TRADE_OPENED,
                                                EventType.TRADE_CLOSED, EventType.FITNESS_SNAPSHOT))]
        for event in events:
            await self.persister.handle(event)
        first_pass = list(self.db.calls)
        self.db.calls.clear()
        for event in events:
            await self.persister.handle(event)
        self.assertEqual(self.db.calls, first_pass)
        # This verifies serialization only; it does not claim idempotent DB replay.

    async def test_direct_probe_insert_keeps_optional_born_at_compatibility(self):
        await self.repo.execute_async("insert_probe", {"probe_id": "legacy-probe"})
        self.assertNotIn("born_at", self.db.calls[-1]["fields"])
        supplied = "2000-01-01T00:00:00+00:00"
        await self.repo.execute_async("insert_probe", {"probe_id": "dated-probe", "born_at": supplied})
        self.assertEqual(self.db.calls[-1]["fields"]["born_at"], supplied)


if __name__ == "__main__":
    unittest.main()
