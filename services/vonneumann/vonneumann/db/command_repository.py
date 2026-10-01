"""In-process command boundary for the isolated DB-03A rehearsal.

This module deliberately has no production client, environment lookup or engine
hook. An injected transport must execute exactly one schema-pinned RPC, without
automatic retries, redirects or fallback credentials. It returns decoded JSON,
not a PostgREST response object. The existing CRUD repository is NOT replaced.

A missing response never proves rollback. Keep the original prepared command
and resolve its journal entry read-only; even a missing entry is inconclusive.
This repository tracks acknowledgment, not a complete engine checkpoint. Its
caller must install the corresponding candidate state before making decisions
and publish only after installation. See PERSISTENCE-RECOVERY-PLAN.md.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
import json
import math
import re
import time
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

from .command_protocol import PreparedCommand, canonical_json


class CommandAdmissionError(ValueError):
    """The local boundary refused a command before submitting any RPC."""


class CommandBusy(CommandAdmissionError):
    """An owned RPC is still running; do not queue competing work."""


class UncertainCommand(RuntimeError):
    """The original command remains pending; only read-only resolution is safe."""


class CommandTransport(Protocol):
    async def rpc(self, name: str, arguments: dict[str, Any]) -> Any:
        """Make one request to the pinned contract schema and return its JSON."""
        ...


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


def _uuid(value: str) -> str:
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("canonical UUID required")
    return value


def _positive_integer(value: Any) -> bool:
    return type(value) is int and 0 < value <= 9223372036854775807


def _balance(value: Any) -> bool:
    # PostgreSQL may preserve trailing fractional zeros in its numeric output.
    return (type(value) is str and len(value) <= 75
            and re.fullmatch(r"(0|[1-9][0-9]*)(\.[0-9]{1,36})?", value) is not None
            and Decimal(value) <= Decimal("1e36"))


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    command: PreparedCommand
    _response: bytes

    @property
    def response(self) -> dict[str, Any]:
        return json.loads(self._response)

    @property
    def revision(self) -> int:
        return self.response["revision"]

    @property
    def fence(self) -> int:
        return self.response["fence"]

    @property
    def status(self) -> str:
        return self.response["status"]


class CommandRepository:
    """One run, one owned RPC and at most one unresolved economic command.

    All calls must occur on one event loop. Caller cancellation cannot cancel an
    admitted RPC. The repository retains that task and consumes its exception;
    a later successful reply is available through ``last_receipt``. There is no
    automatic submission retry or restore/adopt-existing-run API.
    """

    def __init__(
        self, transport: CommandTransport, owner_id: str, run_id: str,
        worker_id: str, *, monotonic: Callable[[], float] = time.monotonic,
        lease_margin: float = 0.25,
    ) -> None:
        self._owner_id = _uuid(owner_id)
        self._run_id = _uuid(run_id)
        self._worker_id = _uuid(worker_id)
        if (type(lease_margin) not in (float, int)
                or not math.isfinite(lease_margin) or not 0 < lease_margin < 1):
            raise ValueError("lease margin must be positive and below one second")
        self._transport = transport
        self._clock = monotonic
        self._margin = lease_margin
        self._revision = 0
        self._fence: int | None = None
        self._status: str | None = None
        self._command_version: int | None = None
        self._pending: PreparedCommand | None = None
        self._uncertain = False
        self._admission_open = True
        self._lease_deadline: float | None = None
        self._last_clock: float | None = None
        self._last_receipt: CommandReceipt | None = None
        self._task: asyncio.Task[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def owner_id(self) -> str:
        return self._owner_id

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def fence(self) -> int | None:
        return self._fence

    @property
    def status(self) -> str | None:
        return self._status

    @property
    def command_version(self) -> int | None:
        return self._command_version

    @property
    def pending(self) -> PreparedCommand | None:
        return self._pending

    @property
    def uncertain(self) -> bool:
        return self._uncertain

    @property
    def busy(self) -> bool:
        return self._task is not None

    @property
    def last_receipt(self) -> CommandReceipt | None:
        return self._last_receipt

    def _now(self) -> float:
        observed = self._clock()
        if (type(observed) not in (float, int) or not math.isfinite(observed)
                or (self._last_clock is not None and observed < self._last_clock)):
            self._lease_deadline = None
            raise CommandAdmissionError("invalid monotonic clock")
        self._last_clock = observed
        return observed

    @property
    def lease_valid(self) -> bool:
        return (self._lease_deadline is not None
                and self._now() < self._lease_deadline
                and self._status not in ("stopped", "failed"))

    @property
    def accepting(self) -> bool:
        return (self._admission_open and not self.busy and self._pending is None
                and self.lease_valid)

    def close_admission(self) -> None:
        """Permanently close mutation admission; pending readback remains allowed."""
        self._admission_open = False
        self._lease_deadline = None

    def _idle(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise CommandAdmissionError("repository belongs to another event loop")
        if self.busy:
            raise CommandBusy("an owned command request is still running")

    async def _owned(self, operation: Callable[[], Awaitable[Any]]) -> Any:
        ready = asyncio.get_running_loop().create_future()

        async def run() -> Any:
            try:
                # Also safe with Python 3.12's eager task factory: execution
                # cannot finish before this repository records task ownership.
                await ready
                return await operation()
            finally:
                self._task = None

        wrapper = run()
        try:
            task = asyncio.create_task(wrapper)
        except Exception:
            wrapper.close()
            self._lease_deadline = None
            if self._pending is not None:
                self._mark_uncertain()
            raise CommandAdmissionError("owned request could not be scheduled") from None
        self._task = task
        ready.set_result(None)
        def completed(done: asyncio.Task[Any]) -> None:
            # Also clean up if loop shutdown cancels the wrapper before it ever
            # enters run(). A caller's shielded cancellation cannot do this.
            if self._task is done:
                self._task = None
            if done.cancelled():
                self._lease_deadline = None
                if self._pending is not None:
                    self._mark_uncertain()
            else:
                # Retrieving the exception does not change awaiters' results.
                done.exception()

        task.add_done_callback(completed)
        return await asyncio.shield(task)

    async def submit(self, command: PreparedCommand) -> CommandReceipt:
        self._idle()
        if not self._admission_open:
            raise CommandAdmissionError("command admission is closed")
        if self._pending is not None:
            raise CommandAdmissionError("resolve the original pending command first")
        if not isinstance(command, PreparedCommand):
            raise CommandAdmissionError("a prepared command is required")
        if command.owner_id != self.owner_id or command.run_id != self.run_id:
            raise CommandAdmissionError("command identity does not match this repository")
        if command.kind != "interrupt" and command.worker_id != self.worker_id:
            raise CommandAdmissionError("command worker does not match this repository")
        if command.kind == "create":
            if self._revision != 0:
                raise CommandAdmissionError("run creation was already acknowledged")
        else:
            if command.expected_revision != self._revision or self._fence is None:
                raise CommandAdmissionError("command revision is stale or run is unknown")
            if self._status in ("stopped", "failed"):
                raise CommandAdmissionError("run is terminal")
            if command.kind == "batch":
                if command.expected_request["payload"]["version"] != self._command_version:
                    raise CommandAdmissionError("command version does not match this run")
                if command.fence != self._fence or not self.lease_valid:
                    raise CommandAdmissionError("a current acknowledged lease is required")
        # No await occurs between admission and recording/owning the attempt.
        self._pending = command
        return await self._owned(lambda: self._submit(command))

    async def _submit(self, command: PreparedCommand) -> CommandReceipt:
        try:
            response = await self._transport.rpc(command.rpc_name, command.rpc_args)
            receipt = self._validate(command, response)
            self._adopt(receipt)
            return receipt
        except asyncio.CancelledError:
            self._mark_uncertain()
            raise
        except Exception:
            self._mark_uncertain()
            raise UncertainCommand("command outcome is uncertain; resolve its original ID") from None

    def _mark_uncertain(self) -> None:
        self._uncertain = True
        self._lease_deadline = None

    def _validate(self, command: PreparedCommand, response: Any) -> CommandReceipt:
        keys = {"run_id", "revision", "fence", "status"}
        if command.kind == "batch":
            keys.add("reserve")
        elif command.kind == "interrupt":
            keys.update(("code", "requires_reconciliation"))
        if type(response) is not dict or response.keys() != keys:
            raise ValueError("invalid command response")
        expected_fence = 1 if command.kind == "create" else self._fence
        if command.kind == "interrupt":
            expected_fence = self._fence + 1 if self._fence is not None else None
        if (response["run_id"] != self.run_id
                or not _positive_integer(response["revision"])
                or response["revision"] != command.expected_result_revision
                or not _positive_integer(response["fence"])
                or response["fence"] != expected_fence):
            raise ValueError("invalid command identity or version")
        expected_status = self._status
        if command.kind == "create":
            expected_status = "starting"
        elif command.kind == "interrupt":
            expected_status = "failed"
            if (response["code"] != "worker_interrupted"
                    or response["requires_reconciliation"] is not True):
                raise ValueError("invalid interruption response")
        else:
            for operation in command.expected_request["payload"]["operations"]:
                if operation["kind"] == "lifecycle":
                    expected_status = operation["status"]
            if not _balance(response["reserve"]):
                raise ValueError("invalid balance response")
        if type(response["status"]) is not str or response["status"] != expected_status:
            raise ValueError("invalid command status")
        return CommandReceipt(command, _json_bytes(response))

    def _adopt(self, receipt: CommandReceipt) -> None:
        if receipt.command.kind == "create":
            self._command_version = receipt.command.expected_request["config"].get("durability_contract_version", 1)
        self._revision = receipt.revision
        self._fence = receipt.fence
        self._status = receipt.status
        self._last_receipt = receipt
        self._pending = None
        self._uncertain = False
        # Create can be an old replay, and journal readback never renews a lease.
        if receipt.command.kind != "batch" or receipt.status in ("stopped", "failed"):
            self._lease_deadline = None

    async def resolve_pending(self) -> CommandReceipt | None:
        self._idle()
        if self._pending is None:
            return None
        command = self._pending
        return await self._owned(lambda: self._resolve(command))

    async def _resolve(self, command: PreparedCommand) -> CommandReceipt | None:
        self._lease_deadline = None
        try:
            result = await self._transport.rpc("get_command", {
                "owner_id": self.owner_id, "run": self.run_id,
                "command_id": command.command_id,
            })
            if result is None:
                self._mark_uncertain()
                return None
            if type(result) is not dict or result.keys() != {"request", "response", "request_hash"}:
                raise ValueError("invalid journal entry")
            # Compare typed JSON, not Python dict equality (True equals 1 there).
            # The hash is format-checked only: PG jsonb::text is not our JSON
            # encoding. Identity is established by the complete stored request.
            if (canonical_json(result["request"]) != command.request
                    or type(result["request_hash"]) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", result["request_hash"]) is None):
                raise ValueError("journal does not match the prepared command")
            receipt = self._validate(command, result["response"])
            self._adopt(receipt)
            return receipt
        except asyncio.CancelledError:
            self._mark_uncertain()
            raise
        except Exception:
            self._mark_uncertain()
            raise UncertainCommand("original command could not be resolved") from None

    async def heartbeat(self, lease_seconds: int = 30) -> None:
        self._idle()
        if not self._admission_open or self._pending is not None:
            raise CommandAdmissionError("lease renewal is not admitted")
        if self._fence is None or self._status in ("stopped", "failed"):
            raise CommandAdmissionError("a known active run is required")
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 120:
            raise CommandAdmissionError("lease seconds must be an integer from 1 to 120")
        self._lease_deadline = None
        return await self._owned(lambda: self._heartbeat(lease_seconds))

    async def _heartbeat(self, lease_seconds: int) -> None:
        try:
            started = self._now()
            result = await self._transport.rpc("heartbeat", {
                "owner_id": self.owner_id, "run": self.run_id, "worker": self.worker_id,
                "token": self._fence, "lease_seconds": lease_seconds,
            })
            if (type(result) is not dict or result.keys() != {"run_id", "revision", "fence"}
                    or result["run_id"] != self.run_id
                    or not _positive_integer(result["revision"])
                    or result["revision"] != self._revision
                    or not _positive_integer(result["fence"])
                    or result["fence"] != self._fence):
                raise ValueError("invalid lease response")
            deadline = started + lease_seconds - self._margin
            if self._now() >= deadline:
                raise ValueError("lease response arrived too late")
            # Closing admission during an owned renewal cannot reopen it.
            if self._admission_open:
                self._lease_deadline = deadline
        except asyncio.CancelledError:
            self._lease_deadline = None
            raise
        except Exception:
            self._lease_deadline = None
            raise CommandAdmissionError("lease renewal was not confirmed") from None
