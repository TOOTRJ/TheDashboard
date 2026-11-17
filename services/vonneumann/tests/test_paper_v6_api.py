"""Real ASGI controls with synthetic identities and no cloud/provider I/O."""
import json
import time
import unittest
from uuid import uuid4

from tests.security_support import OfflineTestMixin, USER_A, USER_B, deny_network

with deny_network():
    import httpx
    from vonneumann.server.auth import VerifiedUser
    from vonneumann.server.paper_v6_api import create_app, ORIGIN


class Service:
    owner_id = USER_A

    def __init__(self):
        self.run_id = str(uuid4())
        self.calls = []
        self.requests = {}
        self.phase = "idle"

    async def status(self, owner):
        return {"version": 6, "owner_id": owner, "run_id": self.run_id,
                "phase": self.phase, "sequence": len(self.requests)}

    async def start(self, owner, request):
        self.calls.append(("start", owner, request))
        if request in self.requests and self.requests[request] != "start":
            raise RuntimeError("private detail must remain hidden")
        self.requests[request] = "start"
        self.phase = "running"
        return await self.status(owner)

    async def stop(self, owner, request):
        self.calls.append(("stop", owner, request))
        self.requests[request] = "stop"
        self.phase = "stopped"
        return await self.status(owner)

    async def history(self, owner, after, limit):
        self.calls.append(("history", owner, after, limit))
        return {"version": 6, "owner_id": owner, "run_id": self.run_id,
                "records": [], "next_sequence": after, "has_more": False}

    async def close(self):
        self.calls.append(("close",))


class PaperV6APITests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.service = Service()

    def client(self, owner=USER_A, service=True):
        async def user():
            return VerifiedUser(owner, int(time.time()) + 300)
        app = create_app(self.service if service else None, verify=user)
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://paper.invalid")

    async def test_real_start_status_stop_and_history_use_authenticated_owner(self):
        request = str(uuid4())
        async with self.client() as client:
            status = await client.get("/v6/status", headers={"Origin": ORIGIN})
            self.assertEqual(status.json()["phase"], "idle")
            for _ in range(2):
                result = await client.post("/v6/start", json={"request_id": request})
                self.assertEqual(result.status_code, 202)
                self.assertEqual(result.json()["sequence"], 1)
                self.assertEqual(result.headers["cache-control"], "no-store")
            stop = await client.post("/v6/stop", json={"request_id": str(uuid4())})
            self.assertEqual(stop.json()["phase"], "stopped")
            self.assertEqual((await client.get("/v6/history?after_sequence=1&limit=20")).status_code, 200)
        self.assertEqual(self.service.calls[-1], ("history", USER_A, 1, 20))
        self.assertTrue(all(call[1] == USER_A for call in self.service.calls))

    async def test_other_owner_cannot_read_or_control(self):
        async with self.client(USER_B) as client:
            for path in ("/v6/status", "/v6/history"):
                self.assertEqual((await client.get(path)).status_code, 404)
            for path in ("/v6/start", "/v6/stop"):
                self.assertEqual((await client.post(path, json={"request_id": str(uuid4())})).status_code, 404)
        self.assertEqual(self.service.calls, [])

    async def test_closed_state_and_default_auth(self):
        async with self.client(service=False) as client:
            self.assertEqual((await client.get("/v6/status")).status_code, 503)
            self.assertEqual((await client.get("/health")).json(), {"alive": True, "version": "paper-service-v6"})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="https://paper.invalid") as client:
            self.assertEqual((await client.get("/v6/status")).status_code, 401)
            self.assertEqual((await client.get("/docs")).status_code, 404)

    async def test_origin_and_bounded_exact_json_controls(self):
        request = str(uuid4())
        async with self.client() as client:
            response = await client.get("/v6/status", headers={"Origin": "https://foreign.invalid"})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.headers["cache-control"], "no-store")
            for value in ({"request_id": request, "live": True}, {"request_id": 123},
                          {"request_id": request.upper()}, {"request_id": "not-a-uuid"}, []):
                self.assertEqual((await client.post("/v6/start", json=value)).status_code, 422)
            duplicate = json.dumps({"request_id": request})[:-1] + ',"request_id":"' + request + '"}'
            self.assertEqual((await client.post("/v6/start", content=duplicate,
                headers={"Content-Type": "application/json"})).status_code, 422)
            self.assertEqual((await client.post("/v6/start", content="x" * 257,
                headers={"Content-Type": "application/json"})).status_code, 413)
            self.assertEqual((await client.post("/v6/start", content="{}")).status_code, 415)
        self.assertEqual(self.service.calls, [])

    async def test_history_bounds_and_duplicate_parameters_refuse_before_service(self):
        async with self.client() as client:
            for query in ("limit=0", "limit=101", "after_sequence=-1", "after_sequence=01",
                          "after_sequence=9007199254740992", "limit=1&limit=2", "owner_id=" + USER_B):
                self.assertEqual((await client.get("/v6/history?" + query)).status_code, 422)
        self.assertEqual(self.service.calls, [])

    async def test_invalid_or_oversized_responses_and_failure_messages_are_private(self):
        async with self.client() as client:
            self.service.requests[str(uuid4())] = "stop"
            request = next(iter(self.service.requests))
            response = await client.post("/v6/start", json={"request_id": request})
            self.assertEqual(response.status_code, 409)
            self.assertNotIn("private detail", response.text)
            async def invalid(owner):
                return {"version": 6, "owner_id": USER_B}
            self.service.status = invalid
            self.assertEqual((await client.get("/v6/status")).status_code, 503)
            async def oversized(owner):
                return {"version": 6, "owner_id": owner, "large": "x" * 262144}
            self.service.status = oversized
            self.assertEqual((await client.get("/v6/status")).status_code, 503)

    async def test_lifespan_initializes_the_real_service_then_controls_warmup_and_stop(self):
        from tests.test_prospective_service import ControlledJournal, WaitingFeed, EmptyArtifacts
        from tests.test_prospective_ga_v3_model import fill_policy
        from tests.test_prospective_source_v3 import OWNER, RUN, MARKET
        from vonneumann.research.prospective_ga_v3_policy import V3Config
        from vonneumann.server.prospective_service import ProspectivePaperService

        journal, feed = ControlledJournal(), WaitingFeed()
        service = ProspectivePaperService(journal, feed,
            V3Config(OWNER, RUN, MARKET, feed.current_binding, fill_policy()), artifacts=EmptyArtifacts())
        async def user():
            return VerifiedUser(OWNER, int(time.time()) + 300)
        app = create_app(service, verify=user)
        async with app.router.lifespan_context(app):
            await service.wait_ready()
            self.assertTrue(feed.restored)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://paper.invalid") as client:
                initial = (await client.get("/v6/status")).json()
                self.assertEqual(initial["phase"], "idle")
                self.assertIsNone(initial["revision"])
                start_id, stop_id = str(uuid4()), str(uuid4())
                for _ in range(2):
                    response = await client.post("/v6/start", json={"request_id": start_id})
                    self.assertEqual(response.status_code, 202)
                await feed.entered.wait()
                self.assertEqual(len(journal.controls), 1)
                current = (await client.get("/v6/status")).json()
                self.assertEqual(current["phase"], "warming_up")
                self.assertEqual(current["warmup"], {"observed_minutes": 1, "required_minutes": 915})
                response = await client.post("/v6/stop", json={"request_id": stop_id})
                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.json()["last_request_id"], stop_id)
                feed.release.set()
                await service._task
                final = (await client.get("/v6/status")).json()
                self.assertEqual(final["phase"], "stopped")
                self.assertEqual((await client.get("/v6/history")).json()["records"], [])
        self.assertTrue(feed.closed)

    async def test_liveness_status_and_durable_stop_remain_available_during_blocked_replay(self):
        import asyncio
        from tests.test_prospective_service import ControlledJournal, WaitingFeed, EmptyArtifacts
        from tests.test_prospective_ga_v3_model import fill_policy
        from tests.test_prospective_source_v3 import OWNER, RUN, MARKET
        from vonneumann.research.prospective_ga_v3_policy import V3Config
        from vonneumann.server.prospective_service import ProspectivePaperService

        entered, release = asyncio.Event(), asyncio.Event()
        class RecoveringJournal(ControlledJournal):
            async def scan(self, after_sequence=0, limit=100):
                entered.set()
                await release.wait()
                return await super().scan(after_sequence, limit)
        journal, feed = RecoveringJournal(), WaitingFeed()
        service = ProspectivePaperService(journal, feed,
            V3Config(OWNER, RUN, MARKET, feed.current_binding, fill_policy()), artifacts=EmptyArtifacts())
        async def user():
            return VerifiedUser(OWNER, int(time.time()) + 300)
        app = create_app(service, verify=user)
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(entered.wait(), 1)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://paper.invalid") as client:
                try:
                    self.assertEqual((await asyncio.wait_for(client.get("/health"), 1)).status_code, 200)
                    status = (await asyncio.wait_for(client.get("/v6/status"), 1)).json()
                    self.assertEqual(status["phase"], "recovering")
                    self.assertTrue(status["busy"])
                    self.assertIsNone(status["projection"])
                    request = str(uuid4())
                    response = await asyncio.wait_for(client.post("/v6/stop", json={"request_id": request}), 1)
                    self.assertEqual(response.status_code, 202)
                    self.assertEqual(response.json()["last_request_id"], request)
                    self.assertEqual(journal.controls[-1]["action"], "stop")
                    self.assertEqual(feed.calls, 0)
                finally:
                    release.set()
                    await service.wait_ready()
                    await service._task
        self.assertTrue(feed.closed)
