"""Immutable command preparation for the isolated DB-03A contract.

No transport, application configuration or credentials are loaded here. This is
not an adapter from the existing float-based trading engine. Economic values
must already be exact decimal strings: converting a float total such as 100.0
does not establish that separately converted notional and fee sum to that total.

The client encoding is versioned by this module's contract, not PostgreSQL's
JSONB text representation. It is never presented as the server request hash.
Decimal-string spelling is retained ("1" and "1.0" are distinct requests).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import re
from typing import Literal
from uuid import UUID, uuid4

from ..core.decimal_execution import DecimalExecutionConfig, DecimalExecutionError, EntryPlan, ExitPlan
from ..core.lineage import BirthLineage, DistributionLineage, LineageValidationError


MAX_BIGINT = 2**63 - 1
MAX_CONFIG_BYTES = 65536
MAX_PAYLOAD_BYTES = 262144
MAX_JSON_DEPTH = 64
MAX_AMOUNT = Decimal("1000000000000000000000000000000000000")
_AMOUNT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,36})?\Z", re.ASCII)
_STATUSES = frozenset({"running", "paused", "risk_halted", "stopped", "failed"})
CommandKind = Literal["create", "batch", "interrupt"]


class CommandValidationError(ValueError):
    """The command cannot be represented without changing its meaning."""


def canonical_uuid(value: object, name: str = "identity") -> str:
    if type(value) is not str:
        raise CommandValidationError(f"{name} must be a canonical UUID string")
    try:
        parsed = UUID(value)
    except ValueError:
        raise CommandValidationError(f"{name} must be a canonical UUID string") from None
    if str(parsed) != value:
        raise CommandValidationError(f"{name} must be a canonical UUID string")
    return value


def bounded_integer(value: object, name: str = "integer", *, minimum: int = 1,
                    maximum: int = MAX_BIGINT) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CommandValidationError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def decimal_amount(value: object, name: str = "amount", *, positive: bool = False) -> str:
    if type(value) is not str or len(value) > 75 or _AMOUNT.fullmatch(value) is None:
        raise CommandValidationError(f"{name} must be an exact decimal string")
    amount = Decimal(value)  # String construction and comparison do not round.
    if amount > MAX_AMOUNT or (positive and amount <= 0):
        raise CommandValidationError(f"{name} is outside the supported amount range")
    return value


def _json_snapshot(value: object, *, depth: int = 0, ancestors: frozenset[int] = frozenset()):
    """Copy the exact supported JSON subset without coercion or float conversion."""
    if depth > MAX_JSON_DEPTH:
        raise CommandValidationError("JSON nesting exceeds the protocol limit")
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is str:
        if "\x00" in value:
            raise CommandValidationError("JSON strings cannot contain a NUL character")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise CommandValidationError("JSON strings must contain valid Unicode") from None
        return value
    if type(value) not in (dict, list):
        raise CommandValidationError("JSON values must be exact strings, integers, booleans, null, objects or lists; floats are unsupported")
    if id(value) in ancestors:
        raise CommandValidationError("JSON values cannot contain cycles")
    ancestors = ancestors | {id(value)}
    if type(value) is list:
        return [_json_snapshot(item, depth=depth + 1, ancestors=ancestors) for item in value]
    copied = {}
    for key, item in value.items():
        if type(key) is not str:
            raise CommandValidationError("JSON object keys must be strings")
        _json_snapshot(key, depth=depth + 1)
        copied[key] = _json_snapshot(item, depth=depth + 1, ancestors=ancestors)
    return copied


def _encode(value: object, *, postgres_spacing: bool = False) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                          separators=(", ", ": ") if postgres_spacing else (",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CommandValidationError("JSON cannot be represented within the protocol limits") from None


def canonical_json(value: object) -> bytes:
    """Encode the exact protocol JSON subset without Python type coercion."""
    return _encode(_json_snapshot(value))


def _keys(value: object, expected: set[str]) -> None:
    if type(value) is not dict or set(value) != expected:
        raise CommandValidationError("Object keys do not match the command contract")


def _operations(value: object, version: int, *, allow_restart: bool = False) -> None:
    maximum = 256 if version == 1 else 1024
    if type(value) is not list or not 1 <= len(value) <= maximum:
        raise CommandValidationError(f"A batch requires between 1 and {maximum} operations")
    for operation in value:
        if type(operation) is not dict:
            raise CommandValidationError("Each operation must be an object")
        kind = operation.get("kind")
        if kind == "birth":
            _keys(operation, {"kind", "id", "cash", "parent_ids" if version == 1 else "lineage"})
            entity = canonical_uuid(operation["id"], "account id")
            decimal_amount(operation["cash"], "birth cash", positive=True)
            if version == 1:
                parents = operation["parent_ids"]
                if type(parents) is not list or len(parents) > 2:
                    raise CommandValidationError("Birth requires at most two parent identities")
                validated = [canonical_uuid(parent, "parent id") for parent in parents]
                if len(set(validated)) != len(validated) or entity in validated:
                    raise CommandValidationError("Birth parents must be distinct and cannot include the child")
            else:
                try:
                    lineage = BirthLineage.from_dict(operation["lineage"])
                except LineageValidationError:
                    raise CommandValidationError("Birth lineage is invalid") from None
                if lineage.version == 2 and not allow_restart:
                    raise CommandValidationError("Restart lineage requires lifecycle contract v4")
                if lineage.child_id != entity:
                    raise CommandValidationError("Birth lineage is bound to another child")
        elif kind == "distribution" and version == 2:
            try:
                DistributionLineage.from_operation(operation)
            except LineageValidationError:
                raise CommandValidationError("Distribution lineage is invalid") from None
        elif kind == "open":
            keys = {"kind", "id", "account_id", "asset", "quantity", "notional", "fee"}
            _keys(operation, keys | {"execution"} if version == 2 else keys)
            canonical_uuid(operation["id"], "position id")
            canonical_uuid(operation["account_id"], "account id")
            if type(operation["asset"]) is not str or not 1 <= len(operation["asset"]) <= 64:
                raise CommandValidationError("Asset must contain between 1 and 64 characters")
            decimal_amount(operation["quantity"], "quantity", positive=True)
            decimal_amount(operation["notional"], "notional", positive=True)
            decimal_amount(operation["fee"], "entry fee")
            if version == 2:
                try:
                    entry = EntryPlan.from_dict(operation["execution"])
                except DecimalExecutionError:
                    raise CommandValidationError("Entry execution evidence is invalid") from None
                if any(operation[name] != getattr(entry, name) for name in ("quantity", "notional", "fee")):
                    raise CommandValidationError("Open values do not match exact entry evidence")
        elif kind == "close":
            keys = {"kind", "id", "proceeds", "fee"}
            _keys(operation, keys | {"execution"} if version == 2 else keys)
            canonical_uuid(operation["id"], "position id")
            proceeds = decimal_amount(operation["proceeds"], "proceeds")
            fee = decimal_amount(operation["fee"], "exit fee")
            if Decimal(fee) > Decimal(proceeds):
                raise CommandValidationError("Exit fee cannot exceed proceeds")
            if version == 2:
                try:
                    exit_plan = ExitPlan.from_dict(operation["execution"])
                except DecimalExecutionError:
                    raise CommandValidationError("Exit execution evidence is invalid") from None
                if operation["proceeds"] != exit_plan.notional or operation["fee"] != exit_plan.fee:
                    raise CommandValidationError("Close values do not match exact exit evidence")
        elif kind == "retire":
            _keys(operation, {"kind", "id"})
            canonical_uuid(operation["id"], "account id")
        elif kind == "lifecycle":
            _keys(operation, {"kind", "status"})
            if type(operation["status"]) is not str or operation["status"] not in _STATUSES:
                raise CommandValidationError("Unsupported lifecycle status")
        else:
            raise CommandValidationError("Unsupported operation kind")


def _reject_float(_value: str):
    raise CommandValidationError("JSON floating-point numbers are unsupported")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CommandValidationError("Duplicate JSON object keys are unsupported")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class PreparedCommand:
    """A stable submission identity and immutable expected journal request.

    A prepared command is not proof of admission, commit or lease ownership.
    The repository must retain this exact snapshot throughout uncertainty.
    Returned dictionaries are fresh copies; mutating them cannot alter identity.
    """

    kind: CommandKind
    owner_id: str
    run_id: str
    worker_id: str | None
    command_id: str
    fence: int | None
    expected_revision: int | None
    request: bytes

    def __post_init__(self) -> None:
        canonical_uuid(self.owner_id, "owner id")
        canonical_uuid(self.run_id, "run id")
        canonical_uuid(self.command_id, "command id")
        if type(self.request) is not bytes or len(self.request) > MAX_PAYLOAD_BYTES + MAX_CONFIG_BYTES:
            raise CommandValidationError("Request must be bounded immutable JSON bytes")
        try:
            body = json.loads(self.request, parse_float=_reject_float,
                              parse_constant=_reject_float, object_pairs_hook=_unique_object)
        except (ValueError, UnicodeError, RecursionError):
            raise CommandValidationError("Request must be canonical protocol JSON") from None
        body = _json_snapshot(body)
        if self.request != _encode(body):
            raise CommandValidationError("Request must use the canonical client encoding")
        common = {"kind", "owner_id", "run_id", "command_id"}
        if self.kind == "create":
            _keys(body, common | {"worker", "config", "initial_cash", "lease_seconds"})
            canonical_uuid(self.worker_id, "worker id")
            if self.fence is not None or self.expected_revision is not None:
                raise CommandValidationError("Creation cannot supply a fence or prior revision")
            if type(body["config"]) is not dict or len(_encode(body["config"], postgres_spacing=True)) > MAX_CONFIG_BYTES:
                raise CommandValidationError("Configuration must be an object within the SQL size limit")
            version = bounded_integer(body["config"].get("durability_contract_version", 1),
                                      "durability contract version", maximum=4)
            if version >= 2:
                execution = body["config"].get("execution")
                try:
                    if type(execution) is not dict or "config" not in execution:
                        raise DecimalExecutionError("Missing exact execution policy")
                    policy = DecimalExecutionConfig.from_dict(execution["config"]).policy()
                    if canonical_json(execution) != canonical_json(policy):
                        raise DecimalExecutionError("Mismatched exact execution policy")
                except DecimalExecutionError:
                    raise CommandValidationError("Exact creation requires its execution policy") from None
            if version in (3, 4):
                from .transition_protocol import validate_configuration
                if version == 4:
                    from .lifecycle_protocol import validate_configuration
                try:
                    validate_configuration(body["config"], self.owner_id, self.run_id, body["initial_cash"])
                except CommandValidationError:
                    raise
                except (ValueError, TypeError, KeyError, OverflowError):
                    raise CommandValidationError("Invalid bounded rehearsal configuration") from None
            decimal_amount(body["initial_cash"], "initial cash", positive=True)
            bounded_integer(body["lease_seconds"], "lease seconds", maximum=120)
        elif self.kind == "batch":
            _keys(body, common | {"worker", "fence", "expected_revision", "payload"})
            canonical_uuid(self.worker_id, "worker id")
            bounded_integer(self.fence, "fence")
            bounded_integer(self.expected_revision, "expected revision", maximum=MAX_BIGINT - 1)
            bounded_integer(body["fence"], "request fence")
            bounded_integer(body["expected_revision"], "request expected revision", maximum=MAX_BIGINT - 1)
            if type(body["payload"]) is not dict:
                raise CommandValidationError("Payload must be an object")
            version = bounded_integer(body["payload"].get("version"), "payload version", maximum=4)
            _keys(body["payload"], {"version", "operations", "transition"} if version in (3, 4) else {"version", "operations"})
            if len(_encode(body["payload"], postgres_spacing=True)) > MAX_PAYLOAD_BYTES:
                raise CommandValidationError("Payload exceeds the SQL size limit")
            # A v3/v4 cursor/indicator-only decision still advances its complete
            # state atomically. Older economic-only batches remain nonempty.
            if not (version in (3, 4) and body["payload"]["operations"] == []):
                _operations(body["payload"]["operations"], min(version, 2), allow_restart=version == 4)
            if version in (3, 4):
                from .transition_protocol import validate_transition
                if version == 4:
                    from .lifecycle_protocol import validate_transition
                try:
                    validate_transition(body["payload"]["transition"], body["payload"]["operations"],
                                        self.owner_id, self.run_id, self.expected_revision)
                except CommandValidationError:
                    raise
                except (ValueError, TypeError, KeyError, OverflowError):
                    raise CommandValidationError("Invalid bounded rehearsal transition") from None
        elif self.kind == "interrupt":
            _keys(body, common | {"expected_revision"})
            if self.worker_id is not None or self.fence is not None:
                raise CommandValidationError("Interruption cannot claim worker lease authority")
            bounded_integer(self.expected_revision, "expected revision", maximum=MAX_BIGINT - 1)
            bounded_integer(body["expected_revision"], "request expected revision", maximum=MAX_BIGINT - 1)
        else:
            raise CommandValidationError("Unsupported command kind")
        expected_metadata = {"kind": self.kind, "owner_id": self.owner_id,
                             "run_id": self.run_id, "command_id": self.command_id}
        if self.worker_id is not None:
            expected_metadata["worker"] = self.worker_id
        if self.fence is not None:
            expected_metadata["fence"] = self.fence
        if self.expected_revision is not None:
            expected_metadata["expected_revision"] = self.expected_revision
        if any(body[key] != value for key, value in expected_metadata.items()):
            raise CommandValidationError("Command metadata does not match its immutable request")

    @classmethod
    def create(cls, owner_id: str, run_id: str, worker_id: str, config: dict,
               initial_cash: str, lease_seconds: int = 30,
               command_id: str | None = None) -> "PreparedCommand":
        command_id = str(uuid4()) if command_id is None else command_id
        body = _json_snapshot({"kind": "create", "owner_id": owner_id, "run_id": run_id,
                               "worker": worker_id, "command_id": command_id,
                               "config": config, "initial_cash": initial_cash,
                               "lease_seconds": lease_seconds})
        return cls("create", owner_id, run_id, worker_id, command_id, None, None, _encode(body))

    @classmethod
    def batch(cls, owner_id: str, run_id: str, worker_id: str, fence: int,
              expected_revision: int, operations: list[dict],
              command_id: str | None = None, *, version: int = 1,
              transition: dict | None = None) -> "PreparedCommand":
        command_id = str(uuid4()) if command_id is None else command_id
        payload = {"version": version, "operations": operations}
        if transition is not None:
            payload["transition"] = transition
        body = _json_snapshot({"kind": "batch", "owner_id": owner_id, "run_id": run_id,
                               "worker": worker_id, "command_id": command_id, "fence": fence,
                               "expected_revision": expected_revision,
                               "payload": payload})
        return cls("batch", owner_id, run_id, worker_id, command_id, fence, expected_revision, _encode(body))

    @classmethod
    def interrupt(cls, owner_id: str, run_id: str, expected_revision: int,
                  command_id: str | None = None) -> "PreparedCommand":
        command_id = str(uuid4()) if command_id is None else command_id
        body = _json_snapshot({"kind": "interrupt", "owner_id": owner_id, "run_id": run_id,
                               "command_id": command_id, "expected_revision": expected_revision})
        return cls("interrupt", owner_id, run_id, None, command_id, None, expected_revision, _encode(body))

    @property
    def expected_request(self) -> dict:
        return json.loads(self.request)

    @property
    def rpc_name(self) -> str:
        return {"create": "create_run", "batch": "commit_command", "interrupt": "interrupt_expired"}[self.kind]

    @property
    def rpc_args(self) -> dict:
        body = self.expected_request
        args = {"owner_id": self.owner_id, "run": self.run_id, "command_id": self.command_id}
        if self.kind == "create":
            args.update(worker=self.worker_id, configuration=body["config"],
                        initial_cash=body["initial_cash"], lease_seconds=body["lease_seconds"])
        elif self.kind == "batch":
            args.update(worker=self.worker_id, token=self.fence,
                        expected_revision=self.expected_revision, payload=body["payload"])
        else:
            args["expected_revision"] = self.expected_revision
        return args

    @property
    def expected_result_revision(self) -> int:
        return 1 if self.kind == "create" else self.expected_revision + 1  # type: ignore[operator]
