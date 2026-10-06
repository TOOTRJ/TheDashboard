"""Fake responses and real owned loopback sockets; no cloud or app configuration."""
from __future__ import annotations
import asyncio
import json
import os
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
from vonneumann.db.command_http import (DashboardCommandHTTPTransport, CommandHTTPBounds,
    CommandHTTPError, DASHBOARD_ORIGIN, COMMAND_SCHEMA, RPC_SIGNATURES, MAX_RESPONSE_BYTES)
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandRepository, UncertainCommand

FAKE_KEY = "sb_secret_" + "fake_fixture_only_" * 3
OWNER, RUN, WORKER = (str(uuid4()) for _ in range(3))
REAL_TRANSPORT = httpx.AsyncHTTPTransport


def arguments(name):
    values = dict(owner_id=OWNER, run=RUN, worker=WORKER, command_id=str(uuid4()),
        configuration={}, initial_cash="100", lease_seconds=30, token=1,
        expected_revision=1, payload={}, through_revision=1, max_events=50,
        max_bytes=65536, event_index=0)
    return {key: values[key] for key in RPC_SIGNATURES[name]}


class LoopbackRoute(httpx.AsyncBaseTransport):
    """Test-only connector, retaining the adapter's actual pinned URL contract."""
    def __init__(self, endpoint, **kwargs):
        self.endpoint = httpx.URL(endpoint)
        assert self.endpoint.host == "127.0.0.1"
        self.inner = REAL_TRANSPORT(**kwargs)

    async def handle_async_request(self, request):
        assert request.url.scheme == "https" and request.url.host == "fxpxsciltakyypunglzr.supabase.co"
        request.url = request.url.copy_with(scheme=self.endpoint.scheme, host=self.endpoint.host, port=self.endpoint.port)
        return await self.inner.handle_async_request(request)

    async def aclose(self): await self.inner.aclose()


class LoopbackServer:
    def __init__(self, handler):
        self.handler = handler; self.requests = []; self.tasks = set(); self.writers = set()

    async def start(self):
        # Exclusive kernel-assigned free loopback port; no existing service changed.
        self.server = await asyncio.start_server(self._serve, "127.0.0.1", 0, limit=16384)
        self.endpoint = f"http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}"
        return self

    async def _serve(self, reader, writer):
        task = asyncio.current_task(); self.tasks.add(task); self.writers.add(writer)
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
            lines = head.decode("ascii").split("\r\n")
            headers = dict(line.split(": ", 1) for line in lines[1:] if line)
            body = await reader.readexactly(int(headers.get("Content-Length", "0")))
            request = {"line": lines[0], "headers": {k.lower(): v for k, v in headers.items()}, "body": body}
            self.requests.append(request); await self.handler(request, writer)
        except (ConnectionError, asyncio.IncompleteReadError): pass
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), .5)
            except (ConnectionError, TimeoutError): pass
            finally:
                self.writers.discard(writer); self.tasks.discard(task)

    async def close(self):
        self.server.close()
        for writer in list(self.writers): writer.close()
        tasks = list(self.tasks)
        for task in tasks: task.cancel()
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 1)
        await asyncio.wait_for(self.server.wait_closed(), 1)


def reply(body=b"null", status=200, headers=None):
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body)), "Connection": "close", **(headers or {})}
    return f"HTTP/1.1 {status} Fixture\r\n".encode() + b"".join(f"{k}: {v}\r\n".encode() for k, v in headers.items()) + b"\r\n" + body


class CommandHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): self.transports = []; self.servers = []

    async def asyncTearDown(self):
        for transport in self.transports: await transport.aclose()
        for server in self.servers: await server.close()

    def mocked(self, handler, bounds=None):
        options = []
        def factory(**kwargs): options.append(kwargs); return httpx.MockTransport(handler)
        with patch("httpx.AsyncHTTPTransport", factory): result = DashboardCommandHTTPTransport(FAKE_KEY, OWNER, bounds=bounds)
        self.transports.append(result); return result, options

    async def loopback(self, handler, bounds=None):
        server = await LoopbackServer(handler).start(); self.servers.append(server)
        with patch("httpx.AsyncHTTPTransport", lambda **kwargs: LoopbackRoute(server.endpoint, **kwargs)):
            transport = DashboardCommandHTTPTransport(FAKE_KEY, OWNER, bounds=bounds)
        self.transports.append(transport); return transport, server

    async def test_exact_pins_owner_headers_and_zero_retry_environment_isolation(self):
        requests = []
        def handler(request): requests.append(request); return httpx.Response(200, content=b"null", headers={"content-type": "application/json"})
        with patch.dict(os.environ, {"HTTPS_PROXY": "https://unrelated.invalid", "SSL_CERT_FILE": "/missing/private-cert", "SUPABASE_URL": "https://other.invalid"}):
            transport, options = self.mocked(handler)
            for name in RPC_SIGNATURES: self.assertIsNone(await transport.rpc(name, arguments(name)))
        self.assertEqual(len(requests), 7)
        for request in requests:
            self.assertEqual(request.method, "POST"); self.assertTrue(str(request.url).startswith(DASHBOARD_ORIGIN + "/rest/v1/rpc/"))
            self.assertEqual(request.headers["Content-Profile"], COMMAND_SCHEMA); self.assertNotIn("Authorization", request.headers)
            self.assertEqual(request.headers["apikey"], FAKE_KEY); self.assertEqual(request.headers["Accept-Encoding"], "identity")
            self.assertEqual(json.loads(request.content)["owner_id"], OWNER)
        self.assertEqual(options[0]["retries"], 0); self.assertFalse(options[0]["trust_env"])
        self.assertTrue(options[0]["verify"]); self.assertIsNone(options[0]["proxy"])
        self.assertFalse(transport._client.follow_redirects); self.assertFalse(transport._client._trust_env)
        self.assertNotIn(FAKE_KEY, repr(transport))
        with self.assertRaises(TypeError): RPC_SIGNATURES["other"] = frozenset()

    async def test_invalid_credentials_owner_and_bounds_fail_before_client_creation(self):
        with patch("httpx.AsyncHTTPTransport", side_effect=AssertionError("Must not construct client")):
            for key in (None, "", "sb_publishable_fake", "eyJhbGciOiJIUzI1NiJ9.fake.signature", FAKE_KEY + "\r\n"):
                with self.assertRaises(CommandHTTPError): DashboardCommandHTTPTransport(key, OWNER)
            with self.assertRaises(CommandHTTPError): DashboardCommandHTTPTransport(FAKE_KEY, "wrong-owner")
        for kwargs in ({"operation_seconds": 0}, {"read_seconds": 16}, {"pool_seconds": True}, {"cleanup_seconds": float("nan")}, {"operation_seconds": .1, "read_seconds": 1}):
            with self.assertRaises(CommandHTTPError): CommandHTTPBounds(**kwargs)

    async def test_invalid_signature_owner_precision_and_request_budgets_never_dispatch(self):
        calls = []; transport, _ = self.mocked(lambda request: calls.append(request))
        bad = [("other", {}), ("get_command", {**arguments("get_command"), "extra": 1}),
               ("get_command", {**arguments("get_command"), "owner_id": str(uuid4())}),
               ("heartbeat", {**arguments("heartbeat"), "token": True}),
               ("create_run", {**arguments("create_run"), "configuration": {"float": .1}}),
               ("create_run", {**arguments("create_run"), "configuration": {"huge": "x" * 327681}}),
               ("read_outbox", {**arguments("read_outbox"), "max_bytes": 65537})]
        deep = []; child = deep
        for _ in range(70): child.append([]); child = child[0]
        bad += [("create_run", {**arguments("create_run"), "configuration": {"deep": deep}}),
                ("create_run", {**arguments("create_run"), "configuration": {"nodes": [None] * 40001}})]
        for name, args in bad:
            with self.assertRaises(CommandHTTPError) as caught: await transport.rpc(name, args)
            self.assertEqual(caught.exception.code, "invalid_request")
        self.assertEqual(calls, [])

    async def test_strict_json_media_encoding_structure_and_declared_length(self):
        for body, headers in [(b'{"duplicate":1,"duplicate":2}', {}), (b"NaN", {}), (b"1.1", {}), (b"1e100000", {}), (b"\xff", {}),
            (b'"\\ud800"', {}), (b"[" * 70 + b"0" + b"]" * 70, {}), (b"null", {"content-type": "text/plain"}),
            (b"null", {"content-encoding": "gzip"}), (b"null", {"content-length": str(MAX_RESPONSE_BYTES + 1)}),
            (b"null", {"preference-applied": "tx=rollback"}), (b"[" + b"null," * 40001 + b"null]", {})]:
            transport, _ = self.mocked(lambda _r, b=body, h=headers: httpx.Response(200, content=b, headers={"content-type": "application/json", **h}))
            with self.assertRaises(CommandHTTPError) as caught: await transport.rpc("get_command", arguments("get_command"))
            self.assertNotIn(FAKE_KEY, str(caught.exception))

    async def test_real_tcp_complete_reply_and_body(self):
        async def handler(_request, writer): writer.write(reply(b'{"revision":1}')); await writer.drain()
        transport, server = await self.loopback(handler)
        self.assertEqual(await transport.rpc("get_command", arguments("get_command")), {"revision": 1})
        self.assertEqual(len(server.requests), 1); self.assertEqual(server.requests[0]["headers"]["content-profile"], COMMAND_SCHEMA)

    async def test_real_tcp_redirect_status_and_truncation_never_retry(self):
        for status in (301, 302, 307, 308, 401, 403, 404, 429, 500, 503):
            async def handler(_request, writer, status=status): writer.write(reply(b"private details", status, {"Location": "http://127.0.0.1:1/other"})); await writer.drain()
            transport, server = await self.loopback(handler)
            with self.assertRaises(CommandHTTPError): await transport.rpc("create_run", arguments("create_run"))
            self.assertEqual(len(server.requests), 1)
        async def handler(_request, writer): writer.write(reply(b"x", headers={"Content-Length": "100"})); await writer.drain()
        transport, server = await self.loopback(handler)
        with self.assertRaises(CommandHTTPError): await transport.rpc("get_command", arguments("get_command"))
        self.assertEqual(len(server.requests), 1)

    async def test_real_tcp_lengthless_response_cap(self):
        async def handler(_request, writer):
            writer.write(b"HTTP/1.1 200 Fixture\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n" + b"x" * (MAX_RESPONSE_BYTES + 1)); await writer.drain()
        transport, server = await self.loopback(handler)
        with self.assertRaises(CommandHTTPError) as caught: await transport.rpc("get_command", arguments("get_command"))
        self.assertEqual(caught.exception.code, "response_too_large"); self.assertEqual(len(server.requests), 1)

    async def test_real_tcp_trickle_whole_deadline(self):
        async def handler(_request, writer):
            writer.write(b"HTTP/1.1 200 Fixture\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n")
            for _ in range(20): writer.write(b" "); await writer.drain(); await asyncio.sleep(.03)
        bounds = CommandHTTPBounds(operation_seconds=.14, connect_seconds=.1, read_seconds=.1, write_seconds=.1, pool_seconds=.01, cleanup_seconds=.2)
        transport, server = await self.loopback(handler, bounds); started = asyncio.get_running_loop().time()
        with self.assertRaises(CommandHTTPError): await transport.rpc("get_command", arguments("get_command"))
        self.assertLess(asyncio.get_running_loop().time() - started, .5); self.assertEqual(len(server.requests), 1)

    async def test_busy_and_close_do_not_cancel_owned_request(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def handler(_request): entered.set(); await release.wait(); return httpx.Response(200, content=b"null", headers={"content-type": "application/json"})
        transport, _ = self.mocked(handler, CommandHTTPBounds(cleanup_seconds=.02))
        task = asyncio.create_task(transport.rpc("get_command", arguments("get_command"))); await entered.wait()
        with self.assertRaises(CommandHTTPError) as caught: await transport.rpc("get_command", arguments("get_command"))
        self.assertEqual(caught.exception.code, "busy")
        with self.assertRaises(CommandHTTPError): await transport.aclose()
        self.assertFalse(task.done()); release.set(); await task; await transport.aclose()
        with self.assertRaises(CommandHTTPError): await transport.rpc("get_command", arguments("get_command"))

    async def test_lost_reply_retains_original_command_then_explicit_readback(self):
        command = PreparedCommand.create(OWNER, RUN, WORKER, {}, "100")
        result = {"run_id": RUN, "revision": 1, "fence": 1, "status": "starting"}
        async def handler(request, writer):
            if request["line"].startswith("POST /rest/v1/rpc/create_run "): return
            writer.write(reply(json.dumps({"request": command.expected_request, "response": result, "request_hash": "a" * 64}).encode())); await writer.drain()
        transport, server = await self.loopback(handler); repo = CommandRepository(transport, OWNER, RUN, WORKER)
        with self.assertRaises(UncertainCommand): await repo.submit(command)
        self.assertIs(repo.pending, command); self.assertTrue(repo.uncertain)
        self.assertEqual((await repo.resolve_pending()).revision, 1)
        self.assertEqual([r["line"].split()[1] for r in server.requests], ["/rest/v1/rpc/create_run", "/rest/v1/rpc/get_command"])

    async def test_cancelled_dispatched_task_keeps_original_uncertainty(self):
        entered = asyncio.Event()
        async def handler(_request, _writer): entered.set(); await asyncio.Event().wait()
        transport, server = await self.loopback(handler); repo = CommandRepository(transport, OWNER, RUN, WORKER)
        command = PreparedCommand.create(OWNER, RUN, WORKER, {}, "100")
        caller = asyncio.create_task(repo.submit(command))
        try:
            await asyncio.wait_for(entered.wait(), 2)
        except TimeoutError:
            if caller.done(): await caller
            raise
        repo._task.cancel()
        with self.assertRaises(asyncio.CancelledError): await caller
        self.assertIs(repo.pending, command); self.assertTrue(repo.uncertain); self.assertEqual(len(server.requests), 1)

    async def test_response_cleanup_is_retained_and_not_repeated(self):
        release = asyncio.Event(); closes = []
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self): yield b"null"
            async def aclose(self): closes.append(1); await release.wait()
        transport, _ = self.mocked(lambda _r: httpx.Response(200, stream=Stream(), headers={"content-type": "application/json"}), CommandHTTPBounds(cleanup_seconds=.02))
        with self.assertRaises(CommandHTTPError): await transport.rpc("get_command", arguments("get_command"))
        self.assertEqual(closes, [1]); self.assertEqual(len(transport._cleanup_tasks), 1)
        with self.assertRaises(CommandHTTPError): await transport.rpc("get_command", arguments("get_command"))
        release.set(); await asyncio.sleep(0); await transport.aclose(); self.assertEqual(closes, [1])

    async def test_synchronous_decode_crossing_deadline_is_not_acknowledged(self):
        transport, _ = self.mocked(lambda _r: httpx.Response(200, content=b"null", headers={"content-type": "application/json"}),
            CommandHTTPBounds(operation_seconds=.03, connect_seconds=.01, read_seconds=.01, write_seconds=.01, pool_seconds=.01))
        def slow_decode(_body): time.sleep(.04); return None
        with patch("vonneumann.db.command_http._decode", slow_decode):
            with self.assertRaises(CommandHTTPError) as caught: await transport.rpc("get_command", arguments("get_command"))
        self.assertEqual(caught.exception.code, "request_failed_or_timed_out")

    async def test_client_close_timeout_retains_same_task_without_repeating(self):
        transport, _ = self.mocked(lambda _r: None, CommandHTTPBounds(cleanup_seconds=.02))
        release = asyncio.Event(); calls = []
        original = transport._client.aclose
        async def close(): calls.append(1); await release.wait(); await original()
        with patch.object(transport._client, "aclose", close):
            with self.assertRaises(CommandHTTPError): await transport.aclose()
            task = transport._client_close
            with self.assertRaises(CommandHTTPError): await transport.aclose()
            self.assertIs(transport._client_close, task); self.assertFalse(task.done())
            release.set(); await transport.aclose()
        self.assertEqual(calls, [1])

    async def test_failed_response_cleanup_still_closes_client_once(self):
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self): yield b"null"
            async def aclose(self): raise RuntimeError("fake fixture close failure")
        transport, _ = self.mocked(lambda _r: httpx.Response(200, stream=Stream(), headers={"content-type": "application/json"}))
        with self.assertRaises(CommandHTTPError): await transport.rpc("get_command", arguments("get_command"))
        with self.assertRaises(CommandHTTPError): await transport.aclose()
        self.assertTrue(transport._client.is_closed)
        self.assertTrue(transport._client_close.done())
        self.transports.remove(transport)  # Failure was explicitly asserted above.
