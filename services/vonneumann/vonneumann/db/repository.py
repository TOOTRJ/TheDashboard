"""
Database repository -- CRUD operations for all Von Neumann tables.
Uses Supabase PostgREST via the service role client.
Every write is tagged with a run_id to isolate simulation sessions.
"""

from __future__ import annotations

import asyncio
import logging
import math
from copy import deepcopy
from datetime import datetime, timezone
from typing import Callable

from .connection import get_supabase
from ..core.types import ProbeEvent, EventType, TradeRecord, FitnessSnapshot

logger = logging.getLogger(__name__)


class PersistenceError(RuntimeError):
    """A write was not acknowledged; provider messages must stay private."""

    code = "persistence_failed"

    def __init__(self, operation: str):
        self.operation = operation
        super().__init__("Colony data could not be saved. Check database readiness before retrying.")


class VonNeumannRepository:
    """All database operations for the Von Neumann system."""

    def __init__(self, user_id: str, run_id: str):
        if not user_id or not run_id:
            raise ValueError("Repository requires an authenticated owner and colony ID")
        self.user_id = user_id
        self.run_id = run_id
        self._write_lock: asyncio.Lock | None = None
        self._colony_config: dict = {}
        try:
            self.db = get_supabase()
        except Exception:
            raise PersistenceError("connect") from None

    async def execute_async(self, operation: str, *args, **kwargs) -> None:
        """Serialize writes off the event loop and drain an in-flight write on cancellation.

        Final failure status must not race a still-running initialization write.
        The client has finite transport timeouts. Writes are never retried here.
        """
        if operation not in {
            "insert_probe", "update_probe", "update_probe_metrics", "insert_trade",
            "close_trade", "insert_fitness_snapshot", "insert_colony",
            "update_colony_status", "upsert_generation_stats",
        }:
            raise ValueError("Unsupported persistence operation")
        if self._write_lock is None:
            self._write_lock = asyncio.Lock()
        async with self._write_lock:
            task = asyncio.create_task(asyncio.to_thread(getattr(self, operation), *args, **kwargs))
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue  # A second shutdown request must not release the write lock.
                    except Exception:
                        break
                if not task.cancelled():
                    task.exception()  # Retrieve any failure; the caller owns cancellation.
                raise

    @staticmethod
    def _write(operation: str, action: Callable) -> None:
        try:
            result = action()
            # PostgREST writes use its default representation response. An empty
            # update means no row matched, not a successfully persisted state.
            rows = getattr(result, "data", None)
            if not isinstance(rows, list) or not rows:
                raise PersistenceError(operation)
        except Exception:
            logger.error("[DB] %s was not acknowledged", operation)
            raise PersistenceError(operation) from None

    # ── Probes ───────────────────────────────────────────────────────────

    def insert_probe(self, probe_data: dict) -> None:
        parent_ids = probe_data.get("parent_ids") or []
        row = {
            "id": probe_data["probe_id"],
            "user_id": self.user_id,
            "run_id": self.run_id,
            "probe_name": probe_data.get("probe_name", ""),
            "generation": probe_data.get("generation", 0),
            "parent_id": probe_data.get("parent_id"),
            "parent_ids": parent_ids,
            "state": probe_data.get("state", "BORN"),
            "genome": probe_data.get("genome", {}),
            "initial_capital": probe_data.get("initial_capital", 0),
            "current_capital": probe_data.get("current_capital", 0),
            "peak_capital": probe_data.get("peak_capital", 0),
            "total_trades": probe_data.get("total_trades", 0),
            "winning_trades": probe_data.get("winning_trades", 0),
            "total_pnl": probe_data.get("total_pnl", 0),
            "max_drawdown": probe_data.get("max_drawdown_pct", 0) / 100.0,
            "sharpe_ratio": probe_data.get("sharpe_ratio"),
            "fitness_score": probe_data.get("fitness_score", 0),
            "metrics": deepcopy(probe_data.get("metrics")),
            "mode": probe_data.get("mode", "simulation"),
        }
        # Only set born_at if explicitly provided (otherwise DB default kicks in)
        if probe_data.get("born_at"):
            row["born_at"] = probe_data["born_at"]
        self._write("insert_probe", lambda: self.db.table("vn_probes").insert(row).execute())

    def update_probe(self, probe_id: str, fields: dict) -> None:
        self._validate_update_fields(fields)
        self._write("update_probe", lambda:
            (self.db.table("vn_probes").update(fields)
             .eq("id", probe_id).eq("user_id", self.user_id)
             .eq("run_id", self.run_id).execute()))

    def update_probe_metrics(self, probe_data: dict) -> None:
        fields = {
            "state": probe_data.get("state"),
            "current_capital": probe_data.get("current_capital"),
            "peak_capital": probe_data.get("peak_capital"),
            "total_trades": probe_data.get("total_trades"),
            "winning_trades": probe_data.get("winning_trades"),
            "total_pnl": probe_data.get("total_pnl"),
            "fitness_score": probe_data.get("fitness_score"),
        }
        fields = {k: v for k, v in fields.items() if v is not None}
        if probe_data.get("max_drawdown_pct") is not None:
            fields["max_drawdown"] = probe_data["max_drawdown_pct"] / 100.0
        # Explicit unknown diagnostics must clear a previously available value;
        # omitting a field in a partial update must preserve the stored value.
        for name in ("sharpe_ratio", "metrics"):
            if name in probe_data:
                fields[name] = deepcopy(probe_data[name])
        if fields:
            self.update_probe(probe_data["probe_id"], fields)

    # ── Trades ───────────────────────────────────────────────────────────

    def insert_trade(self, trade: TradeRecord, mode: str = "simulation") -> None:
        row = {
            "id": trade.trade_id,
            "user_id": self.user_id,
            "run_id": self.run_id,
            "probe_id": trade.probe_id,
            "side": trade.side,
            "pair": trade.pair,
            "entry_price": trade.entry_price,
            "amount": trade.amount,
            "execution": deepcopy(trade.execution),
            "signal_rsi": trade.signal_rsi,
            "signal_ema_fast": trade.signal_ema_fast,
            "signal_ema_slow": trade.signal_ema_slow,
            "signal_volume_ratio": trade.signal_volume_ratio,
            "stop_loss_price": trade.stop_loss_price,
            "take_profit_price": trade.take_profit_price,
            "opened_at": trade.opened_at.isoformat(),
            "mode": mode,
        }
        self._write("insert_trade", lambda: self.db.table("vn_trades").insert(row).execute())

    def close_trade(self, trade_id: str, fields: dict) -> None:
        self._validate_update_fields(fields)
        self._write("close_trade", lambda:
            (self.db.table("vn_trades").update(fields)
             .eq("id", trade_id).eq("user_id", self.user_id)
             .eq("run_id", self.run_id).execute()))

    # ── Fitness snapshots ────────────────────────────────────────────────

    def insert_fitness_snapshot(self, snapshot: FitnessSnapshot) -> None:
        row = {
            "user_id": self.user_id,
            "run_id": self.run_id,
            "probe_id": snapshot.probe_id,
            "generation": snapshot.generation,
            "tick": snapshot.tick,
            "fitness_score": snapshot.fitness_score,
            "roi": snapshot.roi,
            "sharpe_ratio": snapshot.sharpe_ratio,
            "max_drawdown": snapshot.max_drawdown,
            "win_rate": snapshot.win_rate,
            "trade_count": snapshot.trade_count,
            "current_capital": snapshot.current_capital,
            "captured_at": snapshot.captured_at.isoformat(),
            "metrics": deepcopy(snapshot.metrics),
        }
        self._write("insert_fitness_snapshot", lambda:
            self.db.table("vn_fitness_snapshots").insert(row).execute())

    # ── Colonies ──────────────────────────────────────────────────────────

    def insert_colony(self, colony_id: str, strategy: str, config: dict, mode: str,
                      status: str = "running") -> None:
        self._validate_colony_id(colony_id)
        self._validate_status(status)
        snapshot = deepcopy(config)
        self._write("insert_colony", lambda:
            self.db.table("vn_colonies").insert({
                "id": colony_id,
                "user_id": self.user_id,
                "strategy": strategy,
                "config": snapshot,
                "mode": mode,
                "status": status,
            }).execute())
        self._colony_config = snapshot

    def update_colony_status(self, colony_id: str, status: str, details: dict | None = None) -> None:
        self._validate_colony_id(colony_id)
        self._validate_status(status)
        fields: dict = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
        snapshot = deepcopy(self._colony_config)
        if details is not None:
            # Runtime diagnostics live in the existing JSON config column. No
            # schema addition or loss of the original request config is needed.
            snapshot["runtime"] = {**deepcopy(details), "state_persisted": True}
            fields["config"] = snapshot
        if status in {"stopped", "failed"}:
            fields["stopped_at"] = datetime.now(timezone.utc).isoformat()
        self._write("update_colony_status", lambda:
            (self.db.table("vn_colonies").update(fields)
             .eq("id", self.run_id).eq("user_id", self.user_id).execute()))
        self._colony_config = snapshot

    # ── Generation stats ─────────────────────────────────────────────────

    def upsert_generation_stats(self, stats: dict) -> None:
        row = {
            **stats,
            "user_id": self.user_id,
            "run_id": self.run_id,
        }
        self._write("upsert_generation_stats", lambda:
            self.db.table("vn_generation_stats").upsert(
                row, on_conflict="user_id,run_id,generation"
            ).execute())

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in {"starting", "running", "paused", "risk_halted", "stopped", "failed"}:
            raise ValueError("Unsupported colony status")

    @staticmethod
    def _validate_update_fields(fields: dict) -> None:
        """Service-role writes must never reassign record identity or ownership."""
        if {"id", "user_id", "run_id"}.intersection(fields):
            raise ValueError("Record identity and ownership cannot be updated")

    def _validate_colony_id(self, colony_id: str) -> None:
        if colony_id != self.run_id:
            raise ValueError("Colony does not match this repository's run")


class EventPersister:
    """
    Handles ProbeEvents by persisting relevant ones to the database.
    Passed as the on_event callback to GenesisController.
    """

    def __init__(self, repo: VonNeumannRepository, mode: str = "simulation"):
        self.repo = repo
        self.mode = mode

    @staticmethod
    def _event_timestamp(event: ProbeEvent) -> datetime:
        """Preserve the event's market clock, never replace it with write time."""
        timestamp = event.timestamp
        try:
            if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
                raise ValueError()
            return timestamp.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Event timestamp must be a valid timezone-aware datetime") from None

    async def handle(self, event: ProbeEvent) -> None:
        etype = event.event_type
        data = event.data
        timestamp = self._event_timestamp(event)

        if etype == EventType.PROBE_BORN:
            parent_ids = data.get("genome", {}).get("parent_ids", []) or []
            if (not isinstance(parent_ids, list) or
                    any(not isinstance(pid, str) or not pid for pid in parent_ids) or
                    len(set(parent_ids)) != len(parent_ids)):
                raise ValueError("Probe lineage must contain unique parent identities")
            await self.repo.execute_async("insert_probe", {
                "probe_id": event.probe_id,
                "probe_name": data.get("probe_name", ""),
                "generation": data.get("generation", 0),
                "parent_id": parent_ids[0] if parent_ids else None,
                "parent_ids": list(parent_ids),
                "state": data.get("state", "OBSERVING"),
                "genome": data.get("genome", {}),
                "initial_capital": data.get("initial_capital", 0),
                "current_capital": data.get("current_capital", 0),
                "peak_capital": data.get("peak_capital", 0),
                "total_trades": data.get("total_trades", 0),
                "winning_trades": data.get("winning_trades", 0),
                "total_pnl": data.get("total_pnl", 0),
                "max_drawdown_pct": data.get("max_drawdown_pct", 0),
                "sharpe_ratio": data.get("sharpe_ratio"),
                "fitness_score": data.get("fitness_score", 0),
                "metrics": deepcopy(data.get("metrics")),
                "born_at": timestamp.isoformat(),
                "mode": self.mode,
            })

        elif etype == EventType.TRADE_OPENED:
            trade = TradeRecord(
                trade_id=data["trade_id"],
                probe_id=event.probe_id,
                pair=data.get("pair", ""),
                side="BUY",
                entry_price=data.get("entry_price", 0),
                amount=data.get("amount", 0),
                signal_rsi=data.get("rsi"),
                signal_ema_fast=data.get("ema_fast"),
                signal_ema_slow=data.get("ema_slow"),
                signal_volume_ratio=data.get("volume_ratio"),
                stop_loss_price=data.get("stop_loss_price"),
                take_profit_price=data.get("take_profit_price"),
                opened_at=timestamp,
                execution=deepcopy(data.get("execution")),
            )
            await self.repo.execute_async("insert_trade", trade, mode=self.mode)

        elif etype == EventType.TRADE_CLOSED:
            await self.repo.execute_async("close_trade", data["trade_id"], {
                "exit_price": data.get("exit_price"),
                "pnl": data.get("pnl"),
                "pnl_pct": data.get("pnl_pct"),
                "exit_reason": data.get("exit_reason"),
                "closed_at": timestamp.isoformat(),
                "execution": deepcopy(data.get("execution")),
            })

        elif etype == EventType.PROBE_UPDATE:
            await self.repo.execute_async("update_probe_metrics", data)

        elif etype in (EventType.PROBE_DYING, EventType.PROBE_REPRODUCING, EventType.PROBE_DEAD):
            fields = {"state": {
                EventType.PROBE_DYING: "DYING", EventType.PROBE_REPRODUCING: "REPRODUCING",
                EventType.PROBE_DEAD: "DEAD",
            }[etype]}
            # Partial transition messages preserve known metrics; absent values
            # are never fabricated as zero. Only explicit death commits terminal
            # state/time after the complete liquidation and retirement path.
            numeric_fields = ("current_capital", "peak_capital", "total_trades",
                              "winning_trades", "total_pnl", "fitness_score", "max_drawdown_pct")
            terminal = etype == EventType.PROBE_DEAD
            for name in numeric_fields:
                if terminal or name in data:
                    value = data.get(name)
                    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                            not math.isfinite(value)):
                        raise ValueError("Lifecycle metrics must be complete finite numbers")
                    fields["max_drawdown" if name == "max_drawdown_pct" else name] = (
                        value / 100.0 if name == "max_drawdown_pct" else value)
            for name in ("sharpe_ratio", "metrics"):
                if name in data:
                    fields[name] = deepcopy(data[name])
            if terminal:
                reason = data.get("death_reason")
                if data.get("state") != "DEAD" or not isinstance(reason, str) or not reason:
                    raise ValueError("A terminal event requires final state and death reason")
                fields.update(death_reason=reason, died_at=timestamp.isoformat())
            await self.repo.execute_async("update_probe", event.probe_id, fields)

        elif etype == EventType.FITNESS_SNAPSHOT:
            snapshot = FitnessSnapshot(
                probe_id=event.probe_id,
                generation=data.get("generation", 0),
                tick=data.get("tick", 0),
                fitness_score=data.get("fitness_score", 0),
                roi=data.get("roi", 0),
                sharpe_ratio=data.get("sharpe_ratio"),
                max_drawdown=data.get("max_drawdown", 0),
                win_rate=data.get("win_rate", 0),
                trade_count=data.get("trade_count", 0),
                current_capital=data.get("current_capital", 0),
                captured_at=timestamp,
                metrics=deepcopy(data.get("metrics")),
            )
            await self.repo.execute_async("insert_fitness_snapshot", snapshot)

        elif etype == EventType.GENERATION_COMPLETE:
            await self.repo.execute_async("upsert_generation_stats", {
                **data, "ended_at": timestamp.isoformat(),
            })

        # ColonyManager persists lifecycle transitions before announcing them.
        # Status notifications must not issue a second, potentially stale write.
