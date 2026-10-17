"""Inert, owned one-attempt HTTP transport for the Dashboard command contract.

Explicit private modern service key/owner injection only. No environment lookup,
application imports, default client, endpoint override, retries or startup wiring.
A JSON reply is not proof of transaction commit: deployment acceptance must prove
server transaction mode and independent journal/projection readback first.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import math
import re
from typing import Any
from types import MappingProxyType

import httpx

from ..http_tls import HTTPTLSError, verified_http_context
from .command_protocol import canonical_json, canonical_uuid, bounded_integer, decimal_amount

DASHBOARD_ORIGIN = "https://fxpxsciltakyypunglzr.supabase.co"
COMMAND_SCHEMA = "vn_durability"
RPC_SIGNATURES = MappingProxyType({
    "create_run": frozenset({"owner_id", "run", "worker", "command_id", "configuration", "initial_cash", "lease_seconds"}),
    "heartbeat": frozenset({"owner_id", "run", "worker", "token", "lease_seconds"}),
    "commit_command": frozenset({"owner_id", "run", "worker", "token", "expected_revision", "command_id", "payload"}),
    "get_command": frozenset({"owner_id", "run", "command_id"}),
    "interrupt_expired": frozenset({"owner_id", "run", "expected_revision", "command_id"}),
    "read_outbox": frozenset({"owner_id", "run", "through_revision", "max_events", "max_bytes"}),
    "acknowledge_event": frozenset({"owner_id", "run", "command_id", "event_index"}),
})
MAX_REQUEST_BYTES = 327_680
MAX_RESPONSE_BYTES = 393_216
MAX_JSON_NODES = 40_000
MAX_JSON_DEPTH = 64


class CommandHTTPError(RuntimeError):
    """Only fixed local codes are exposed; never server bodies, URLs or keys."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Command HTTP transport refused operation: {code}")


@dataclass(frozen=True, slots=True)
class CommandHTTPBounds:
    operation_seconds: float = 3.0
    connect_seconds: float = .5
    read_seconds: float = 1.0
    write_seconds: float = 1.0
    pool_seconds: float = .1
    cleanup_seconds: float = 1.0

    def __post_init__(self):
        for value in (self.operation_seconds, self.connect_seconds, self.read_seconds,
                      self.write_seconds, self.pool_seconds, self.cleanup_seconds):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 15:
                raise CommandHTTPError("invalid_bounds")
        if max(self.connect_seconds, self.read_seconds, self.write_seconds,
               self.pool_seconds) > self.operation_seconds:
            raise CommandHTTPError("invalid_bounds")


def _arguments(name: str, arguments: dict, owner: str) -> bytes:
    try:
        if type(name) is not str or name not in RPC_SIGNATURES or type(arguments) is not dict or arguments.keys() != RPC_SIGNATURES[name]:
            raise ValueError()
        for key in ("owner_id", "run", "worker", "command_id"):
            if key in arguments:
                canonical_uuid(arguments[key], key)
        if arguments["owner_id"] != owner:
            raise ValueError()
        for key in ("token", "expected_revision", "through_revision"):
            if key in arguments:
                bounded_integer(arguments[key], key)
        if "lease_seconds" in arguments:
            bounded_integer(arguments["lease_seconds"], "lease_seconds", maximum=120)
        if name == "read_outbox":
            bounded_integer(arguments["max_events"], "max_events", maximum=100)
            bounded_integer(arguments["max_bytes"], "max_bytes", minimum=512, maximum=65536)
        if name == "acknowledge_event":
            bounded_integer(arguments["event_index"], "event_index", minimum=0, maximum=1024)
        if name == "create_run":
            if type(arguments["configuration"]) is not dict:
                raise ValueError()
            decimal_amount(arguments["initial_cash"], "initial_cash", positive=True)
        if name == "commit_command" and type(arguments["payload"]) is not dict:
            raise ValueError()
        nodes = 0
        def bounded(value, depth=0):
            nonlocal nodes
            nodes += 1
            if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
                raise ValueError()
            if type(value) is str and len(value) > MAX_REQUEST_BYTES:
                raise ValueError()
            if type(value) is list:
                for child in value:
                    bounded(child, depth + 1)
            elif type(value) is dict:
                for key, child in value.items():
                    bounded(key, depth + 1)
                    bounded(child, depth + 1)
        bounded(arguments)
        body = canonical_json(arguments)  # immutable bytes before the first await
        if len(body) > MAX_REQUEST_BYTES:
            raise ValueError()
        return body
    except (Exception, RecursionError):
        raise CommandHTTPError("invalid_request") from None


def _decode(body: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result

    def integer(value):
        if len(value) > 128:
            raise ValueError()
        return int(value)

    def reject_number(_value):
        raise ValueError()

    try:
        value = json.loads(body.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                           parse_int=integer, parse_float=reject_number, parse_constant=reject_number)
        work = [(value, 0)]
        nodes = 0
        while work:
            item, depth = work.pop()
            nodes += 1
            if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
                raise ValueError()
            if type(item) is str:
                if "\x00" in item:
                    raise ValueError()
                item.encode("utf-8", errors="strict")
            elif type(item) is list:
                work.extend((child, depth + 1) for child in item)
            elif type(item) is dict:
                work.extend((child, depth + 1) for pair in item.items() for child in pair)
        return value
    except (Exception, RecursionError):
        raise CommandHTTPError("invalid_json") from None


class DashboardCommandHTTPTransport:
    """One loop and one active request; callers retain command-level ownership.

    Constructor performs no I/O. The gateway receives an opaque sb_secret key in
    apikey only. JWT/publishable/legacy keys are deliberately unsupported pending
    their separate authentication/least-privilege review. No request can alter the
    fixed origin/schema, methods, headers or seven exact parameter signatures.
    """

    def __init__(self, service_key: str, owner_id: str, *, bounds: CommandHTTPBounds | None = None):
        if type(service_key) is not str or re.fullmatch(r"sb_secret_[A-Za-z0-9_-]{16,256}", service_key) is None:
            raise CommandHTTPError("unsupported_credential")
        try:
            self._owner = canonical_uuid(owner_id, "owner_id")
        except Exception:
            raise CommandHTTPError("invalid_owner") from None
        if bounds is not None and type(bounds) is not CommandHTTPBounds:
            raise CommandHTTPError("invalid_bounds")
        self._bounds = bounds or CommandHTTPBounds()
        limits = httpx.Limits(max_connections=1, max_keepalive_connections=1, keepalive_expiry=5.0)
        try:
            context = verified_http_context()
        except HTTPTLSError:
            raise CommandHTTPError("tls_configuration_unavailable") from None
        owned = httpx.AsyncHTTPTransport(verify=context, trust_env=False, proxy=None, retries=0,
                                         http1=True, http2=False, limits=limits)
        self._client = httpx.AsyncClient(transport=owned, verify=context, trust_env=False,
            follow_redirects=False, limits=limits, timeout=httpx.Timeout(
                connect=self._bounds.connect_seconds, read=self._bounds.read_seconds,
                write=self._bounds.write_seconds, pool=self._bounds.pool_seconds),
            headers={"apikey": service_key, "Content-Profile": COMMAND_SCHEMA,
                     "Accept": "application/json", "Content-Type": "application/json",
                     "Accept-Encoding": "identity", "Prefer": "handling=strict,tx=commit"})
        self._loop = None
        self._active = None
        self._closed = False
        self._cleanup_failed = False
        self._cleanup_tasks: set[asyncio.Task] = set()
        self._client_close = None

    def _bind_loop(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        if self._loop is not loop:
            raise CommandHTTPError("foreign_loop")

    async def _cleanup(self, close):
        task = asyncio.create_task(close())
        self._cleanup_tasks.add(task)
        def completed(done):
            self._cleanup_tasks.discard(done)
            if done.cancelled() or done.exception() is not None:
                self._cleanup_failed = True
        task.add_done_callback(completed)
        try:
            await asyncio.wait_for(asyncio.shield(task), self._bounds.cleanup_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise CommandHTTPError("cleanup_pending_or_failed") from None

    async def rpc(self, name: str, arguments: dict[str, Any]) -> Any:
        self._bind_loop()
        if self._closed or self._cleanup_failed or self._cleanup_tasks:
            raise CommandHTTPError("closed_or_cleanup_pending")
        if self._active is not None:
            raise CommandHTTPError("busy")
        body = _arguments(name, arguments, self._owner)
        self._active = asyncio.current_task()
        response = None
        try:
            deadline = asyncio.get_running_loop().time() + self._bounds.operation_seconds
            async with asyncio.timeout(self._bounds.operation_seconds):
                request = self._client.build_request("POST", f"{DASHBOARD_ORIGIN}/rest/v1/rpc/{name}", content=body)
                response = await self._client.send(request, stream=True, follow_redirects=False)
                if response.status_code != 200:
                    raise CommandHTTPError("http_rejected")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise CommandHTTPError("unsupported_encoding")
                media = response.headers.get("content-type", "").lower().split(";")
                if media[0].strip() != "application/json" or any(part.strip() not in ("charset=utf-8", "charset=\"utf-8\"") for part in media[1:]):
                    raise CommandHTTPError("unsupported_media")
                length = response.headers.get("content-length")
                if length is not None and (not length.isascii() or not length.isdigit() or len(length) > 9 or int(length) > MAX_RESPONSE_BYTES):
                    raise CommandHTTPError("invalid_response_length")
                if "tx=rollback" in response.headers.get("preference-applied", "").lower().replace(" ", ""):
                    raise CommandHTTPError("rollback_preference")
                chunks = bytearray()
                # Consume the raw stream without HTTPX's implicit EOF close.
                # One retained cleanup below owns closure outside the I/O deadline.
                async for chunk in response.stream:
                    if type(chunk) is not bytes or len(chunks) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise CommandHTTPError("response_too_large")
                    chunks.extend(chunk)
                if length is not None and len(chunks) != int(length):
                    raise CommandHTTPError("invalid_response_length")
                value = _decode(bytes(chunks))
                # A cooperative timeout cannot interrupt synchronous JSON work.
                # The byte/node/depth bounds cap that work; do not acknowledge
                # its result if it has crossed the whole-operation deadline.
                if asyncio.get_running_loop().time() >= deadline:
                    raise CommandHTTPError("request_failed_or_timed_out")
                return value
        except asyncio.CancelledError:
            raise
        except CommandHTTPError:
            raise
        except Exception:
            raise CommandHTTPError("request_failed_or_timed_out") from None
        finally:
            try:
                if response is not None:
                    await self._cleanup(response.aclose)
            finally:
                self._active = None

    async def aclose(self):
        self._bind_loop()
        self._closed = True
        active = self._active
        if active is asyncio.current_task():
            raise CommandHTTPError("busy")
        try:
            if active is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(active), self._bounds.cleanup_seconds)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if not active.done():
                        raise
                    # The request caller owns its failure; it must not prevent
                    # closing resources once the retained operation is done.
            if self._cleanup_tasks:
                await asyncio.wait_for(asyncio.shield(asyncio.gather(*self._cleanup_tasks, return_exceptions=True)), self._bounds.cleanup_seconds)
            if self._client_close is None:
                self._client_close = asyncio.create_task(self._client.aclose())
                self._client_close.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            await asyncio.wait_for(asyncio.shield(self._client_close), self._bounds.cleanup_seconds)
            if self._cleanup_failed:
                raise CommandHTTPError("cleanup_pending_or_failed")
        except asyncio.CancelledError:
            raise
        except Exception:
            raise CommandHTTPError("cleanup_pending_or_failed") from None
