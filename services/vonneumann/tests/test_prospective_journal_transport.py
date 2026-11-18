"""Mocked native transport identity, cancellation and original-wire regressions."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import OfflineTestMixin, USER_A, A1, A2, deny_network
with deny_network():
    import psycopg
    from tests.test_command_sql import certificate
    from vonneumann.core.prospective_runtime import FORMAT, JournalEntry, JournalRejected
    from vonneumann.db.prospective_journal import ProspectiveSQLJournal, JournalUnavailable, HOST, MAX_REPLY


def encoded(raw):
    return base64.b64encode(raw).decode("ascii")


def entry(owner=USER_A, run=A1):
    candidate = "{}"
    return JournalEntry(json.dumps({"format": FORMAT, "owner_id": owner, "run_id": run,
        "command_id": A2, "sequence": "1", "previous_sha256": None, "witness": {},
        "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest(), "candidate_wire": candidate},
        sort_keys=True, separators=(",", ":")).encode())


class Connection:
    def __init__(self, value=None):
        self.pgconn = SimpleNamespace(ssl_in_use=True)
        self.info = SimpleNamespace(server_version=170006)
        self.value = {"sequence": 0, "sha256": None, "bytes": 0} if value is None else value
        self.row = None
        self.calls, self.commits, self.closed = [], 0, False
        self.commit_entered, self.close_entered = asyncio.Event(), asyncio.Event()
        self.commit_gate, self.close_gate, self.close_error = None, None, None

    async def execute(self, query, params, **options):
        self.calls.append((query, params, options))
        return self

    async def fetchone(self):
        if self.row is not None:
            return self.row
        raw = json.dumps(self.value).encode()
        return len(raw), raw

    async def commit(self):
        self.commits += 1
        self.commit_entered.set()
        if self.commit_gate is not None:
            await self.commit_gate.wait()

    async def close(self):
        self.close_entered.set()
        if self.close_gate is not None:
            await self.close_gate.wait()
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class ProspectiveJournalTransportTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.ca = certificate()

    def setUp(self):
        super().setUp()
        self.journal = ProspectiveSQLJournal("vn_paper_" + "a" * 32, "synthetic-password-" + "b" * 32,
            self.ca, USER_A, A1)
        self.connection = Connection()
        self.connections = [self.connection]
        self.connect = AsyncMock(return_value=self.connection)
        self.offline_stack.enter_context(patch("vonneumann.db.prospective_journal.psycopg.AsyncConnection.connect", self.connect))
        self.offline_stack.enter_context(patch.dict(os.environ, {}, clear=True))

    async def asyncTearDown(self):
        for connection in self.connections:
            for gate in (connection.commit_gate, connection.close_gate):
                if gate is not None:
                    gate.set()
        await self.journal.close()

    async def test_constructor_rejects_wrong_scope_and_private_configuration_without_io(self):
        valid = ["vn_paper_" + "a" * 32, "synthetic-password-" + "b" * 32, self.ca, USER_A, A1]
        for index, value in ((0, "postgres"), (0, "vn_paper_" + "A" * 32), (1, "short"),
                (1, "x" * 31 + "\n"), (1, "é" * 32), (2, b"PRIVATE KEY"),
                (2, b"not-a-certificate"), (3, "not-a-uuid"), (4, A1.upper())):
            values = list(valid); values[index] = value
            with self.subTest(index=index), self.assertRaisesRegex(JournalUnavailable, "^invalid_paper_configuration$"):
                ProspectiveSQLJournal(*values)
        self.connect.assert_not_awaited()

    async def test_connection_pins_target_tls_auth_private_ca_and_bounded_parameterized_query(self):
        observed = {}
        async def connect(**options):
            observed.update(options)
            cert = Path(options["sslrootcert"])
            self.assertEqual(cert.read_bytes(), self.ca)
            self.assertEqual(stat.S_IMODE(cert.stat().st_mode), 0o600)
            return self.connection
        self.connect.side_effect = connect
        result = await self.journal.head()
        self.assertEqual(result["sequence"], 0)
        expected = {"host": HOST, "port": 5432, "dbname": "postgres", "user": self.journal._login,
            "password": self.journal._password, "sslmode": "verify-full", "sslcert": os.devnull,
            "sslkey": os.devnull, "sslcertmode": "disable", "ssl_min_protocol_version": "TLSv1.2",
            "sslnegotiation": "postgres", "sslsni": "1", "require_auth": "scram-sha-256",
            "channel_binding": "require", "gssencmode": "disable",
            "connect_timeout": 5, "application_name": "dashboard-paper-v6"}
        for key, value in expected.items():
            self.assertEqual(observed[key], value, key)
        self.assertNotIn("service", observed)
        self.assertFalse(Path(observed["sslrootcert"]).exists())
        self.assertIn("statement_timeout=5000", observed["options"])
        self.assertIn("lock_timeout=3000", observed["options"])
        self.assertIn("synchronous_commit=on", observed["options"])
        query, params, options = self.connection.calls[0]
        self.assertIn("vn_paper_v6.rpc(%s::text,%s::jsonb)", query)
        self.assertIn("octet_length(v)<=%s", query)
        self.assertEqual(options, {"prepare": False})
        self.assertEqual(params[0], "head")
        self.assertEqual(json.loads(params[1]), {"owner_id": USER_A, "run_id": A1})
        self.assertEqual(params[2], MAX_REPLY)
        self.assertEqual(self.connection.commits, 1)
        self.assertTrue(self.connection.closed)

    async def test_inherited_pg_configuration_and_closed_transport_refuse_before_connect(self):
        for variable in ("PGPASSWORD", "PGSERVICE", "PGSERVICEFILE"):
            with self.subTest(variable=variable), patch.dict(os.environ, {variable: "synthetic-private-do-not-read"}):
                with self.assertRaisesRegex(JournalUnavailable, "^paper_operation_failed_or_uncertain$"):
                    await self.journal.head()
        self.connect.assert_not_awaited()
        await self.journal.close()
        with self.assertRaises(JournalUnavailable):
            await self.journal.head()
        self.connect.assert_not_awaited()

    async def test_failures_are_fixed_private_safe_and_have_no_implicit_retry(self):
        for stage in ("connect", "execute", "commit"):
            self.connect.reset_mock()
            self.connect.side_effect = None
            self.connection = Connection(); self.connections.append(self.connection)
            self.connect.return_value = self.connection
            if stage == "connect":
                self.connect.side_effect = ConnectionError("https://private.invalid/?api-key=secret")
            else:
                setattr(self.connection, stage, AsyncMock(side_effect=ConnectionError("private password secret")))
            with self.subTest(stage=stage), self.assertRaisesRegex(JournalUnavailable, "^paper_operation_failed_or_uncertain$"):
                await self.journal.head()
            self.assertEqual(self.connect.await_count, 1)
            if stage != "connect":
                self.assertTrue(self.connection.closed)

    async def test_server_tls_version_and_response_bounds_fail_before_commit(self):
        for changes in ({"ssl": False}, {"version": 160009}, {"row": (MAX_REPLY + 1, b"")},
                {"row": (True, b"x")}, {"row": (2, b"x")}, {"row": (2, "{}")}):
            self.connection = Connection(); self.connections.append(self.connection)
            self.connection.pgconn.ssl_in_use = changes.get("ssl", True)
            self.connection.info.server_version = changes.get("version", 170006)
            self.connection.row = changes.get("row")
            self.connect.return_value = self.connection
            with self.subTest(changes=changes), self.assertRaises(JournalUnavailable):
                await self.journal.head()
            self.assertEqual(self.connection.commits, 0)
            self.assertTrue(self.connection.closed)

    async def test_cancellation_retains_the_original_commit_and_close_waits_for_it(self):
        self.connection.commit_gate = asyncio.Event()
        caller = asyncio.create_task(self.journal.control(A2, "stop"))
        await self.connection.commit_entered.wait()
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertEqual(self.connection.commits, 1)
        self.assertEqual(len(self.journal._tasks), 1)
        closing = asyncio.create_task(self.journal.close())
        await asyncio.sleep(0)
        self.assertFalse(closing.done())
        self.connection.commit_gate.set()
        await closing
        self.assertTrue(self.connection.closed)
        self.assertEqual(self.connect.await_count, 1)
        self.assertEqual(self.connection.commits, 1)

    async def test_queued_rpc_waits_for_the_original_connection_cleanup(self):
        second = Connection(); self.connections.append(second)
        self.connect.side_effect = [self.connection, second]
        self.connection.close_gate = asyncio.Event()
        original = asyncio.create_task(self.journal.head())
        await self.connection.close_entered.wait()
        follow = asyncio.create_task(self.journal.latest_control())
        await asyncio.sleep(0.01)
        self.assertEqual(self.connect.await_count, 1)
        self.assertFalse(original.done())
        self.assertFalse(follow.done())
        self.connection.close_gate.set()
        await original; await follow
        self.assertEqual(self.connect.await_count, 2)

    async def test_cleanup_failure_poisoning_uses_a_fixed_error_and_bars_next_connect(self):
        self.connection.close_error = ConnectionError("private cleanup token")
        with self.assertRaisesRegex(JournalUnavailable, "^paper_cleanup_unconfirmed$"):
            await self.journal.head()
        with self.assertRaisesRegex(JournalUnavailable, "^paper_operation_failed_or_uncertain$"):
            await self.journal.latest_control()
        self.assertEqual(self.connect.await_count, 1)

    async def test_original_entry_get_scan_and_compare_and_swap_wire_are_exact(self):
        original = entry()
        self.journal._rpc = AsyncMock(return_value={"wire": encoded(original.wire)})
        committed = await self.journal.append(original, expected_sequence=0, expected_sha256=None)
        self.assertEqual(committed.wire, original.wire)
        operation, body = self.journal._rpc.call_args.args
        self.assertEqual(operation, "append")
        self.assertEqual(body, {"command_id": A2, "expected_sequence": 0, "expected_sha256": None, "wire": encoded(original.wire)})
        self.assertEqual((await self.journal.get(A2)).wire, original.wire)
        self.journal._rpc.return_value = None
        self.assertIsNone(await self.journal.get(A2))
        self.journal._rpc.return_value = [{"wire": encoded(original.wire)}]
        rows = await self.journal.scan(0, 100)
        self.assertEqual(rows[0].wire, original.wire)
        self.assertEqual(self.journal._rpc.call_args.args, ("scan", {"after_sequence": 0, "limit": 25}))

    async def test_source_artifact_and_controls_preserve_original_ids_bytes_and_native_clock(self):
        raw = b'{"kind":"complete","capsules":[]}'
        receipt = {"packet_id": A2, "sequence": 1, "sha256": hashlib.sha256(raw).hexdigest(), "wire": encoded(raw),
            "accepted_at_us": 123456789, "available_at_upper_us": 123456790, "receipt_sha256": "1" * 64}
        self.journal._rpc = AsyncMock(return_value=receipt)
        result = await self.journal.admit_source(A2, raw)
        self.assertEqual(result["wire"], raw)
        self.assertEqual(result["accepted_at_us"], receipt["accepted_at_us"])
        self.assertEqual(self.journal._rpc.call_args.args, ("admit_source", {"packet_id": A2, "wire": encoded(raw)}))
        self.assertEqual((await self.journal.get_source(A2))["wire"], raw)
        self.journal._rpc.return_value = [{**receipt}]
        self.assertEqual((await self.journal.source_inventory(0, 100))[0]["wire"], raw)
        self.assertEqual(self.journal._rpc.call_args.args, ("source_inventory", {"after_sequence": 0, "limit": 25}))
        self.journal._rpc.return_value = {"wire": encoded(raw)}
        self.assertEqual(await self.journal.get_artifact("mark", "1" * 64), raw)
        await self.journal.put_artifact("mark", "1" * 64, raw)
        self.assertEqual(self.journal._rpc.call_args.args, ("put_artifact", {"kind": "mark", "sha256": "1" * 64, "wire": encoded(raw)}))
        self.journal._rpc.return_value = [{"wire": encoded(raw), "sequence": 1}]
        await self.journal.artifact_inventory(0, 25)
        self.assertEqual(self.journal._rpc.call_args.args, ("artifact_inventory", {"after_sequence": 0, "limit": 25}))
        self.journal._rpc.return_value = {"action": "stop", "request_id": A2}
        await self.journal.control(A2, "stop")
        self.assertEqual(self.journal._rpc.call_args.args, ("control", {"request_id": A2, "action": "stop"}))
        self.journal._rpc.return_value = {**receipt, "sha256": "0" * 64}
        with self.assertRaisesRegex(JournalUnavailable, "^paper_original_digest_mismatch$"):
            await self.journal.get_source(A2)

    async def test_authenticated_stop_rejection_keeps_exact_original_wire_and_is_not_unknown(self):
        original = entry()
        self.journal._rpc = AsyncMock(return_value={"refused": True, "reason": "stop_committed",
            "wire": encoded(original.wire), "stop_request_id": A1})
        for operation in (lambda: self.journal.append(original, expected_sequence=0, expected_sha256=None),
                lambda: self.journal.get(A2)):
            with self.assertRaises(JournalRejected) as rejected:
                await operation()
            self.assertEqual(rejected.exception.wire, original.wire)
            self.assertEqual(rejected.exception.reason, "stop_committed")
        self.journal._rpc.return_value = {"refused": True, "reason": "private-unrecognized-reason",
            "wire": encoded(original.wire), "stop_request_id": A1}
        with self.assertRaisesRegex(JournalUnavailable, "^paper_rejection_refused$"):
            await self.journal.get(A2)
        self.journal._rpc.return_value = {"refused": True, "reason": "stop_committed",
            "wire": encoded(entry(owner=A1).wire), "stop_request_id": A1}
        with self.assertRaisesRegex(JournalUnavailable, "^paper_original_scope_mismatch$"):
            await self.journal.get(A2)


class LibpqServiceSelectionTests(unittest.TestCase):
    """Real libpq, restricted to an absent socket in a new private directory.

    No existing database, TCP address, credential source or external endpoint is
    reachable through these explicit parameters. PGSERVICEFILE is deliberately
    synthetic here to distinguish profile lookup from the Unix-socket attempt;
    the actual journal rejects every ambient PG variable before connecting.
    """
    def test_omitted_service_skips_nonexistent_profile_and_reaches_only_absent_socket(self):
        with tempfile.TemporaryDirectory(prefix="dashboard-libpq-") as folder:
            directory = Path(folder).resolve()
            environment = {"HOME": str(directory), "PGSERVICEFILE": str(directory/"absent.conf"),
                "LANG": "C", "LC_ALL": "C"}
            options = {"host": str(directory), "port": 5432, "dbname": "postgres",
                "user": "synthetic_no_database", "password": "synthetic_unused_password",
                "connect_timeout": 1, "passfile": str(directory/"absent.pass")}
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaises(psycopg.OperationalError) as omitted:
                    psycopg.Connection.connect(**options)
                self.assertIn(str(directory/".s.PGSQL.5432"), str(omitted.exception))
                self.assertNotIn("definition of service", str(omitted.exception))
                for service in ("", "dashboard_missing_original_profile"):
                    with self.subTest(service=service), self.assertRaises(psycopg.OperationalError) as selected:
                        psycopg.Connection.connect(**options, service=service)
                    self.assertIn("service", str(selected.exception).lower())
                    self.assertNotIn(str(directory/".s.PGSQL.5432"), str(selected.exception))
