"""Explicit bridges from exact plans to v2 rehearsal command operations.

These pure builders never read credentials, connect to a database, mutate the
engine or convert floats. PreparedCommand and the SQL fixture revalidate their
results at the next boundaries.
"""

from __future__ import annotations

import json

from ..core.decimal_execution import DecimalExecutionConfig, EntryPlan, ExitPlan
from .command_protocol import CommandValidationError, canonical_json, canonical_uuid


def run_configuration(execution: DecimalExecutionConfig, config: dict | None = None) -> dict:
    """Bind the v2 contract and immutable execution policy without overwriting it."""
    if type(execution) is not DecimalExecutionConfig:
        raise CommandValidationError("an exact execution configuration is required")
    if DecimalExecutionConfig.from_dict(execution.to_dict()) != execution:
        raise CommandValidationError("invalid exact execution configuration")
    if config is not None and type(config) is not dict:
        raise CommandValidationError("run configuration must be a JSON object")
    result = json.loads(canonical_json({} if config is None else config))
    required = {"durability_contract_version": 2, "execution": execution.policy()}
    for key, value in required.items():
        if key in result and canonical_json(result[key]) != canonical_json(value):
            raise CommandValidationError("configuration conflicts with the exact execution contract")
        result[key] = value
    return result


def open_operation(entry: EntryPlan, position_id: str, account_id: str, asset: str) -> dict:
    if type(entry) is not EntryPlan:
        raise CommandValidationError("an exact entry plan is required")
    EntryPlan.from_dict(entry.to_dict())
    canonical_uuid(position_id, "position id")
    canonical_uuid(account_id, "account id")
    if type(asset) is not str or not 1 <= len(asset) <= 64:
        raise CommandValidationError("asset must contain between 1 and 64 characters")
    canonical_json(asset)
    return {"kind": "open", "id": position_id, "account_id": account_id, "asset": asset,
            "quantity": entry.quantity, "notional": entry.notional, "fee": entry.fee,
            "execution": entry.to_dict()}


def close_operation(exit: ExitPlan, position_id: str) -> dict:
    if type(exit) is not ExitPlan:
        raise CommandValidationError("an exact exit plan is required")
    ExitPlan.from_dict(exit.to_dict())
    canonical_uuid(position_id, "position id")
    return {"kind": "close", "id": position_id, "proceeds": exit.notional,
            "fee": exit.fee, "execution": exit.to_dict()}
