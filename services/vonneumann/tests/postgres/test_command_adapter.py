"""Repository/protocol integration against the isolated DB-03A SQL fixture.

The transport below is test-only: it accepts a fixed RPC allowlist, connects to
the harness's own temporary cluster as service_role, and never imports settings,
accepts a database URL or invokes a production Supabase/PostgREST adapter.
Administrative SQL is restricted to fake-user setup, observation and expiry
injection. These checks do not establish the legacy engine's write cutover.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from decimal import Decimal
import json
import unittest
import uuid

from tests.postgres.harness import PostgresContractTestCase
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import (
    CommandAdmissionError,
    CommandRepository,
    UncertainCommand,
)


def identity() -> str:
    return str(uuid.uuid4())


def literal(value: object) -> str:
    """Escape fixture literals explicitly, including backslashes in JSON text."""
    if value is None:
        return "NULL"
    if type(value) is int:
        return str(value)
    if type(value) is not str or "\x00" in value:
        raise ValueError("Fixture SQL requires a string, integer or null literal")
    return "E'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


# Neither function names nor parameter ordering can be supplied by a caller.
_RPC_PARAMETERS = {
    "create_run": (
        ("owner_id", "uuid"), ("run", "uuid"), ("worker", "uuid"),
        ("command_id", "uuid"), ("configuration", "jsonb"),
        ("initial_cash", "text"), ("lease_seconds", "integer"),
    ),
    "commit_command": (
        ("owner_id", "uuid"), ("run", "uuid"), ("worker", "uuid"),
        ("token", "bigint"), ("expected_revision", "bigint"),
        ("command_id", "uuid"), ("payload", "jsonb"),
    ),
    "get_command": (("owner_id", "uuid"), ("run", "uuid"), ("command_id", "uuid")),
    "heartbeat": (
        ("owner_id", "uuid"), ("run", "uuid"), ("worker", "uuid"),
        ("token", "bigint"), ("lease_seconds", "integer"),
    ),
    "interrupt_expired": (
        ("owner_id", "uuid"), ("run", "uuid"),
        ("expected_revision", "bigint"), ("command_id", "uuid"),
    ),
    "read_outbox": (
        ("owner_id", "uuid"), ("run", "uuid"), ("through_revision", "bigint"),
        ("max_events", "integer"), ("max_bytes", "integer"),
    ),
    "acknowledge_event": (
        ("owner_id", "uuid"), ("run", "uuid"), ("command_id", "uuid"), ("event_index", "integer"),
    ),
}


class FixtureRpcTransport:
    """An injected transport with real SQL commits and optional lost replies."""

    def __init__(self, database):
        self.database = database
        self.calls: list[tuple[str, dict]] = []
        self.drop_reply_once: str | None = None

    async def rpc(self, name: str, args: dict):
        if name not in _RPC_PARAMETERS:
            raise ValueError("RPC is outside the fixture allowlist")
        parameters = _RPC_PARAMETERS[name]
        if set(args) != {key for key, _kind in parameters}:
            raise ValueError("RPC arguments do not match the fixture contract")
        rendered = []
        for key, kind in parameters:
            value = args[key]
            if kind == "jsonb":
                value = json.dumps(value, ensure_ascii=False, allow_nan=False,
                                   separators=(",", ":"))
            rendered.append(literal(value) + "::" + kind)
        source = "SELECT vn_durability." + name + "(" + ",".join(rendered) + ");"
        self.calls.append((name, deepcopy(args)))
        result = await asyncio.to_thread(self.database.scalar, source, role="service_role")
        if self.drop_reply_once == name:
            self.drop_reply_once = None
            raise ConnectionError("Deliberate fixture reply loss after commit")
        return json.loads(result) if result else None


class CommandAdapterTests(PostgresContractTestCase, unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner, self.run_id, self.worker = identity(), identity(), identity()
        self.configuration = {
            "strategy": "fixture-only",
            "nested": {"retained": [1, True, None]},
            "literal_text": "owner's \\ path; SELECT 'quoted';\nnext line",
        }
        self.db.sql(f"INSERT INTO auth.users(id) VALUES ({literal(self.owner)}::uuid);")
        self.transport = FixtureRpcTransport(self.db)
        self.repository = CommandRepository(self.transport, self.owner, self.run_id, self.worker)

    def create_command(self, initial_cash="1000"):
        return PreparedCommand.create(self.owner, self.run_id, self.worker,
                                      self.configuration, initial_cash)

    def batch_command(self, revision, operations):
        return PreparedCommand.batch(self.owner, self.run_id, self.worker, 1, revision, operations)

    async def create_and_heartbeat(self, initial_cash="1000"):
        receipt = await self.repository.submit(self.create_command(initial_cash))
        await self.repository.heartbeat()
        self.assertTrue(self.repository.lease_valid)
        return receipt

    @staticmethod
    def birth(account, cash="100", parents=None):
        return {"kind": "birth", "id": account, "cash": cash, "parent_ids": parents or []}

    @staticmethod
    def opened(position, account, *, notional="20", fee="0.5"):
        return {"kind": "open", "id": position, "account_id": account, "asset": "SOL/USDC",
                "quantity": "1.25", "notional": notional, "fee": fee}

    def snapshot(self) -> dict:
        result = {}
        for table in ("runs", "accounts", "account_parents", "positions", "commands"):
            key = "id" if table == "runs" else "run_id"
            result[table] = json.loads(self.db.scalar(
                f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), '[]'::jsonb) "
                f"FROM vn_durability.{table} t WHERE {key}={literal(self.run_id)}::uuid;"
            ), parse_float=Decimal)
        return result

    def expire(self) -> None:
        self.db.sql("UPDATE vn_durability.runs SET lease_until=clock_timestamp()-interval '1 second' "
                    f"WHERE id={literal(self.run_id)}::uuid;")

    def rpc_names(self) -> list[str]:
        return [name for name, _args in self.transport.calls]

    async def test_repository_commits_one_atomic_economic_batch_with_exact_balances(self):
        created = await self.create_and_heartbeat("1000.123456789012345678901234567890123456")
        self.assertEqual((created.revision, created.fence, created.status), (1, 1, "starting"))
        account, position = identity(), identity()
        command = self.batch_command(1, [
            self.birth(account, "100.123"), {"kind": "lifecycle", "status": "running"},
            self.opened(position, account, notional="20.012", fee="0.003"),
            {"kind": "close", "id": position, "proceeds": "25.019", "fee": "0.007"},
            {"kind": "retire", "id": account},
        ])
        receipt = await self.repository.submit(command)
        self.assertEqual(receipt.command, command)
        self.assertEqual((receipt.revision, receipt.fence, receipt.status), (2, 1, "running"))
        expected = "1005.120456789012345678901234567890123456"
        self.assertEqual(receipt.response["reserve"], expected)
        state = self.snapshot()
        self.assertEqual(state["runs"][0]["reserve"], Decimal(expected))
        self.assertEqual(state["runs"][0]["config"], self.configuration)
        self.assertEqual(state["accounts"][0]["cash"], 0)
        self.assertTrue(state["accounts"][0]["retired"])
        self.assertTrue(state["positions"][0]["closed"])
        self.assertEqual(sorted(row["revision"] for row in state["commands"]), [1, 2])
        self.assertEqual(self.rpc_names(), ["create_run", "heartbeat", "commit_command"])
        self.assertIsNone(self.repository.pending)

    async def test_lost_creation_reply_resolves_the_original_command_without_another_write(self):
        command = self.create_command()
        self.transport.drop_reply_once = "create_run"
        with self.assertRaises(UncertainCommand):
            await self.repository.submit(command)
        self.assertEqual(self.repository.pending, command)
        self.assertTrue(self.repository.uncertain)
        before = self.snapshot()
        self.assertEqual(len(before["commands"]), 1)
        receipt = await self.repository.resolve_pending()
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.command, command)
        self.assertEqual((receipt.revision, receipt.status), (1, "starting"))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.rpc_names(), ["create_run", "get_command"])
        self.assertIsNone(self.repository.pending)
        self.assertFalse(self.repository.lease_valid, "Readback must not silently renew authority")
        await self.repository.heartbeat()
        self.assertTrue(self.repository.lease_valid)

    async def test_lost_batch_reply_resolves_after_lease_expiry_without_post_replay(self):
        await self.create_and_heartbeat()
        account, position = identity(), identity()
        command = self.batch_command(1, [self.birth(account),
            {"kind": "lifecycle", "status": "running"}, self.opened(position, account)])
        self.transport.drop_reply_once = "commit_command"
        with self.assertRaises(UncertainCommand):
            await self.repository.submit(command)
        self.assertEqual(self.repository.pending, command)
        self.expire()
        before = self.snapshot()
        receipt = await self.repository.resolve_pending()
        self.assertEqual((receipt.revision, receipt.status), (2, "running"))
        self.assertEqual(receipt.command, command)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(before["commands"]), 2)
        self.assertEqual(before["runs"][0]["reserve"], 900)
        self.assertEqual(before["accounts"][0]["cash"], Decimal("79.5"))
        self.assertEqual(len(before["positions"]), 1)
        self.assertFalse(before["positions"][0]["closed"])
        self.assertEqual(self.rpc_names(), ["create_run", "heartbeat", "commit_command", "get_command"])
        self.assertFalse(self.repository.lease_valid)

    async def test_late_sql_rejection_rolls_back_batch_and_null_resolution_keeps_admission_frozen(self):
        await self.create_and_heartbeat()
        account, position = identity(), identity()
        await self.repository.submit(self.batch_command(1, [self.birth(account),
            {"kind": "lifecycle", "status": "running"}, self.opened(position, account)]))
        before = self.snapshot()
        command = self.batch_command(2, [
            {"kind": "close", "id": position, "proceeds": "25", "fee": "0.5"},
            {"kind": "retire", "id": account}, self.birth(identity(), "100", [account]),
            self.birth(identity(), "100000000"),
        ])
        with self.assertRaises(UncertainCommand):
            await self.repository.submit(command)
        self.assertEqual(self.snapshot(), before, "A late rejection must roll back every economic row")
        self.assertEqual(self.repository.pending, command)
        self.assertIsNone(await self.repository.resolve_pending())
        self.assertEqual(self.repository.pending, command)
        self.assertTrue(self.repository.uncertain)
        self.assertEqual(self.snapshot(), before)
        calls = deepcopy(self.transport.calls)
        with self.assertRaises(CommandAdmissionError):
            await self.repository.submit(self.batch_command(2, [{"kind": "lifecycle", "status": "paused"}]))
        with self.assertRaises(CommandAdmissionError):
            await self.repository.heartbeat()
        self.assertEqual(self.transport.calls, calls, "Unresolved commands must never trigger another write")
        self.assertEqual(self.rpc_names().count("commit_command"), 2)
        self.assertEqual(self.rpc_names().count("get_command"), 1)

    async def test_expired_interruption_preserves_positions_and_resolves_after_admission_closes(self):
        await self.create_and_heartbeat()
        account, position = identity(), identity()
        await self.repository.submit(self.batch_command(1, [self.birth(account),
            {"kind": "lifecycle", "status": "running"}, self.opened(position, account)]))
        self.expire()
        before = self.snapshot()
        command = PreparedCommand.interrupt(self.owner, self.run_id, 2)
        self.transport.drop_reply_once = "interrupt_expired"
        with self.assertRaises(UncertainCommand):
            await self.repository.submit(command)
        self.repository.close_admission()
        receipt = await self.repository.resolve_pending()
        self.assertEqual((receipt.revision, receipt.fence, receipt.status), (3, 2, "failed"))
        self.assertEqual(receipt.response["code"], "worker_interrupted")
        after = self.snapshot()
        for table in ("accounts", "positions", "account_parents"):
            self.assertEqual(after[table], before[table])
        self.assertEqual(after["runs"][0]["reserve"], before["runs"][0]["reserve"])
        self.assertEqual(after["runs"][0]["config"], self.configuration)
        self.assertTrue(after["runs"][0]["requires_reconciliation"])
        self.assertIsNotNone(after["runs"][0]["interrupted_at"])
        self.assertEqual(len(after["commands"]), 3)
        self.assertFalse(self.repository.accepting)
        self.assertFalse(self.repository.lease_valid)
        self.assertIsNone(self.repository.pending)
        self.assertEqual(self.rpc_names()[-2:], ["interrupt_expired", "get_command"])


if __name__ == "__main__":
    unittest.main()
