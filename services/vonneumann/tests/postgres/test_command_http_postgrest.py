"""Actual PostgREST 14.5 schema, JWT, grant and commit/readback acceptance.

The test-only route stands in for the opaque-key gateway with a fake fixture
JWT. It does not establish hosted gateway authentication or production config.
"""
import json
import asyncio
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
from tests.postgres.harness import OPT_IN
from tests.postgres.http_harness import IsolatedPostgREST, fixture_jwt
from tests.test_command_http import FAKE_KEY, REAL_TRANSPORT, LoopbackServer, LoopbackRoute
from vonneumann.db.command_http import DashboardCommandHTTPTransport, CommandHTTPError
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandRepository, UncertainCommand


class PostgrestRoute(httpx.AsyncBaseTransport):
    def __init__(self, endpoint, **kwargs):
        self.endpoint = httpx.URL(endpoint)
        assert self.endpoint.host == "127.0.0.1"
        self.inner = REAL_TRANSPORT(**kwargs)

    async def handle_async_request(self, request):
        assert request.url.host == "fxpxsciltakyypunglzr.supabase.co"
        assert request.headers["apikey"] == FAKE_KEY
        request.url = self.endpoint.copy_with(path=request.url.path.removeprefix("/rest/v1"))
        request.headers["Authorization"] = "Bearer " + fixture_jwt("service_role")
        return await self.inner.handle_async_request(request)

    async def aclose(self): await self.inner.aclose()


class PostgRESTCommandHTTPTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get(OPT_IN) != "1": raise unittest.SkipTest("Requires isolated PostgreSQL opt-in")
        cls.db = IsolatedPostgREST()
        cls.addClassCleanup(cls.db.close)
        cls.db.start()

    async def asyncSetUp(self):
        self.owner, self.other, self.run, self.worker = (str(uuid4()) for _ in range(4))
        self.db.sql(f"INSERT INTO auth.users(id) VALUES ('{self.owner}'),('{self.other}');")
        self.transports = []

    async def asyncTearDown(self):
        for transport in self.transports: await transport.aclose()

    def transport(self):
        with patch("httpx.AsyncHTTPTransport", lambda **kw: PostgrestRoute(self.db.endpoint, **kw)):
            transport = DashboardCommandHTTPTransport(FAKE_KEY, self.owner)
        self.transports.append(transport)
        return transport

    def create(self): return PreparedCommand.create(self.owner, self.run, self.worker, {}, "100", lease_seconds=120)

    async def raw(self, path, *, role="service_role", owner=None, body=None, profile="vn_durability", preference=None, token=None):
        headers = {"Content-Profile": profile, "Accept-Profile": profile}
        if role is not None: headers["Authorization"] = "Bearer " + (token or fixture_jwt(role, owner))
        if preference: headers["Prefer"] = preference
        async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
            if body is None: return await client.get(self.db.endpoint + path, headers=headers)
            return await client.post(self.db.endpoint + path, json=body, headers=headers)

    def count(self, table):
        return self.db.scalar(f"SELECT count(*) FROM vn_durability.{table} WHERE {'id' if table=='runs' else 'run_id'}='{self.run}';")

    async def test_create_batch_readback_outbox_and_independent_commit(self):
        transport = self.transport(); repo = CommandRepository(transport, self.owner, self.run, self.worker)
        command = self.create(); self.assertEqual((await repo.submit(command)).revision, 1)
        self.assertEqual(self.count("runs"), "1"); self.assertEqual(self.count("commands"), "1")
        await repo.heartbeat(lease_seconds=120)
        account = str(uuid4())
        batch = PreparedCommand.batch(self.owner, self.run, self.worker, 1, 1,
            [{"kind": "birth", "id": account, "cash": "25", "parent_ids": []}, {"kind": "lifecycle", "status": "running"}])
        self.assertEqual((await repo.submit(batch)).revision, 2)
        self.assertEqual(self.db.scalar(f"SELECT reserve::text FROM vn_durability.runs WHERE id='{self.run}';"), "75")
        self.assertEqual(self.count("accounts"), "1"); self.assertEqual(self.count("commands"), "2")
        readback = await transport.rpc("get_command", {"owner_id": self.owner, "run": self.run, "command_id": batch.command_id})
        self.assertEqual(readback["request"], batch.expected_request)
        self.db.sql(f"UPDATE vn_durability.runs SET lease_until=clock_timestamp()-interval '1 second' WHERE id='{self.run}';")
        interrupted = PreparedCommand.interrupt(self.owner, self.run, 2)
        result = await transport.rpc(interrupted.rpc_name, interrupted.rpc_args)
        self.assertEqual((result["revision"], result["fence"], result["status"]), (3, 2, "failed"))
        self.assertEqual(self.count("commands"), "3")

    async def test_v5_controller_bootstrap_tick_reserved_stop_and_outbox_over_http(self):
        from tests.postgres.test_provider_controller import LiteralProviderSession
        from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
        from vonneumann.core.provider_lifecycle import ProviderLifecycleConfig
        from vonneumann.core.provider_controller import CommandAllocation, ProviderPilotController
        from vonneumann.db.provider_pilot_owner import ProviderPilotOwner
        from vonneumann.market.jupiter_feed import JupiterFeed
        identity = lambda: str(uuid4())
        config = ProviderLifecycleConfig(ExactLifecycleConfig("genetic_algorithm", self.owner, self.run, asset="SOL/USD"), identity())
        transport = self.transport(); repo = CommandRepository(transport, self.owner, self.run, self.worker)
        await repo.submit(PreparedCommand.create(self.owner, self.run, self.worker, config.run_configuration(), config.initial_cash, lease_seconds=120))
        owner = ProviderPilotOwner(repo, transport, config, stop_command_id=identity())
        feed = JupiterFeed(api_key="local-fixture-only", rpc_url="https://controller-fixture.invalid/rpc", birdeye_api_key="local-fixture-only")
        feed._session = LiteralProviderSession(); feed._candles._session = LiteralProviderSession(candles=True)
        events = []
        async def publish(event):
            self.assertLessEqual(event["revision"], owner.installed_state.to_dict()["revision"])
            events.append(event)
        def allocate(kind, generation):
            return CommandAllocation(identity(), tuple(identity() for _ in range(9)), tuple((generation, f"Http-{generation}-{index}") for index in range(8)))
        controller = ProviderPilotController(owner, feed, publish, allocate, lease_seconds=120)
        try:
            await controller.heartbeat()
            self.assertEqual((await controller.bootstrap()).status, "complete")
            deadline = asyncio.get_running_loop().time() + 8
            while True:
                report = await controller.tick()
                if report.status == "complete": break
                self.assertEqual(report.status, "deferred")
                self.assertLess(asyncio.get_running_loop().time(), deadline)
                await asyncio.sleep(.05)
            self.assertEqual(report.quote_sequence, 1)
            self.assertEqual((await controller.stop()).status, "complete")
            state = owner.installed_state.to_dict()
            self.assertEqual(json.loads(self.db.scalar(f"SELECT engine_state FROM vn_durability.runs WHERE id='{self.run}';")), state)
            page = await transport.rpc("read_outbox", {"owner_id": self.owner, "run": self.run, "through_revision": state["revision"], "max_events": 100, "max_bytes": 65536})
            self.assertEqual(page["events"], []); self.assertFalse(page["has_more"])
            self.assertTrue(events); self.assertEqual(len(events), len({event["event_id"] for event in events}))
        finally:
            controller.close_admission()
            await feed.close()

    async def test_late_invalid_operation_rolls_back_entire_batch(self):
        transport = self.transport(); command = self.create(); await transport.rpc(command.rpc_name, command.rpc_args)
        batch = PreparedCommand.batch(self.owner, self.run, self.worker, 1, 1,
            [{"kind": "birth", "id": str(uuid4()), "cash": "25", "parent_ids": []}, {"kind": "birth", "id": str(uuid4()), "cash": "999", "parent_ids": []}])
        with self.assertRaises(CommandHTTPError): await transport.rpc(batch.rpc_name, batch.rpc_args)
        self.assertEqual(self.count("accounts"), "0"); self.assertEqual(self.count("commands"), "1")
        self.assertEqual(self.db.scalar(f"SELECT reserve::text FROM vn_durability.runs WHERE id='{self.run}';"), "100")

    async def test_roles_jwt_schema_and_hidden_helper_rejections(self):
        command = self.create()
        for role in (None, "anon", "authenticated"):
            response = await self.raw("/rpc/create_run", role=role, owner=self.owner, body=command.rpc_args)
            self.assertIn(response.status_code, (401, 403))
        for token in ("bad.fixture.jwt", fixture_jwt("service_role", expired=True), fixture_jwt("service_role", audience="wrong"), fixture_jwt("unknown_role")):
            response = await self.raw("/rpc/create_run", body=command.rpc_args, token=token)
            self.assertIn(response.status_code, (400, 401, 403))
        response = await self.raw("/rpc/create_run", body=command.rpc_args, profile="public")
        self.assertEqual(response.status_code, 406)
        response = await self.raw("/rpc/money", body={"value": "1"})
        self.assertIn(response.status_code, (403, 404))
        self.assertEqual(self.count("commands"), "0")

    async def test_authenticated_owner_reads_and_direct_table_writes_denied(self):
        command = self.create(); await self.transport().rpc(command.rpc_name, command.rpc_args)
        self.assertEqual((await self.raw("/runs", role="authenticated", owner=self.owner)).json()[0]["id"], self.run)
        self.assertEqual((await self.raw("/runs", role="authenticated", owner=self.other)).json(), [])
        response = await self.raw("/runs", body={"id": str(uuid4()), "user_id": self.owner})
        self.assertEqual(response.status_code, 403)
        response = await self.raw("/runs", role="authenticated", owner=self.owner, body={"id": str(uuid4()), "user_id": self.owner})
        self.assertEqual(response.status_code, 403)

    async def test_service_role_owner_argument_is_not_user_authentication(self):
        # Privileged worker RPC can create for another valid owner; client pinning
        # is not a server security boundary against a stolen service credential.
        command = PreparedCommand.create(self.other, self.run, self.worker, {}, "100")
        response = await self.raw("/rpc/create_run", body=command.rpc_args)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.scalar(f"SELECT user_id FROM vn_durability.runs WHERE id='{self.run}';"), self.other)

    async def test_forced_rollback_returns_200_but_has_no_committed_journal(self):
        self.db.start_http("rollback")
        try:
            command = self.create(); response = await self.raw("/rpc/create_run", body=command.rpc_args, preference="handling=strict,tx=commit")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("tx=commit", response.headers.get("preference-applied", ""))
            self.assertEqual(self.count("commands"), "0"); self.assertEqual(self.count("runs"), "0")
        finally: self.db.start_http("commit")

    async def test_allow_override_commit_and_explicit_rollback_evidence(self):
        self.db.start_http("rollback-allow-override")
        try:
            command = self.create(); response = await self.raw("/rpc/create_run", body=command.rpc_args, preference="handling=strict,tx=commit")
            self.assertEqual(response.status_code, 200); self.assertIn("tx=commit", response.headers["preference-applied"])
            self.assertEqual(self.count("commands"), "1")
            other = PreparedCommand.create(self.owner, str(uuid4()), self.worker, {}, "100")
            response = await self.raw("/rpc/create_run", body=other.rpc_args, preference="handling=strict,tx=rollback")
            self.assertEqual(response.status_code, 200); self.assertIn("tx=rollback", response.headers["preference-applied"])
            self.assertEqual(self.db.scalar(f"SELECT count(*) FROM vn_durability.runs WHERE id='{other.run_id}';"), "0")
        finally: self.db.start_http("commit")

    async def test_lost_http_reply_after_real_commit_resolves_original_id(self):
        command = self.create()
        async def gateway(request, writer):
            path = request["line"].split()[1].removeprefix("/rest/v1")
            response = await self.raw(path, body=json.loads(request["body"]))
            self.assertEqual(response.status_code, 200)
            if path == "/rpc/create_run": return  # Commit already happened; reply deliberately lost.
            from tests.test_command_http import reply
            writer.write(reply(response.content)); await writer.drain()
        server = await LoopbackServer(gateway).start()
        try:
            with patch("httpx.AsyncHTTPTransport", lambda **kw: LoopbackRoute(server.endpoint, **kw)):
                transport = DashboardCommandHTTPTransport(FAKE_KEY, self.owner)
            self.transports.append(transport)
            repo = CommandRepository(transport, self.owner, self.run, self.worker)
            with self.assertRaises(UncertainCommand): await repo.submit(command)
            self.assertEqual(self.count("commands"), "1"); self.assertIs(repo.pending, command)
            self.assertEqual((await repo.resolve_pending()).revision, 1)
            self.assertEqual(len(server.requests), 2); self.assertEqual(self.count("commands"), "1")
        finally: await server.close()
