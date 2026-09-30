"""
Database repository -- CRUD operations for all Von Neumann tables.
Uses Supabase PostgREST via the service role client.
Every write is tagged with a run_id to isolate simulation sessions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from .connection import get_supabase
from ..core.types import ProbeEvent, EventType, TradeRecord, FitnessSnapshot

logger = logging.getLogger(__name__)


class VonNeumannRepository:
    """All database operations for the Von Neumann system."""

    def __init__(self, user_id: str, run_id: str):
        self.user_id = user_id
        self.run_id = run_id
        self.db = get_supabase()

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
            "total_trades": 0,
            "winning_trades": 0,
            "total_pnl": 0,
            "max_drawdown": 0,
            "sharpe_ratio": 0,
            "fitness_score": 0,
            "mode": probe_data.get("mode", "simulation"),
        }
        # Only set born_at if explicitly provided (otherwise DB default kicks in)
        if probe_data.get("born_at"):
            row["born_at"] = probe_data["born_at"]
        try:
            self.db.table("vn_probes").insert(row).execute()
        except Exception as e:
            logger.error(f"[DB] insert_probe failed: {e}")

    def update_probe(self, probe_id: str, fields: dict) -> None:
        try:
            self.db.table("vn_probes").update(fields).eq("id", probe_id).execute()
        except Exception as e:
            logger.error(f"[DB] update_probe failed: {e}")

    def update_probe_metrics(self, probe_data: dict) -> None:
        fields = {
            "state": probe_data.get("state"),
            "current_capital": probe_data.get("current_capital"),
            "peak_capital": probe_data.get("peak_capital"),
            "total_trades": probe_data.get("total_trades"),
            "winning_trades": probe_data.get("winning_trades"),
            "total_pnl": probe_data.get("total_pnl"),
            "max_drawdown": probe_data.get("max_drawdown_pct", 0) / 100.0,
            "sharpe_ratio": probe_data.get("sharpe_ratio"),
            "fitness_score": probe_data.get("fitness_score"),
        }
        fields = {k: v for k, v in fields.items() if v is not None}
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
            "signal_rsi": trade.signal_rsi,
            "signal_ema_fast": trade.signal_ema_fast,
            "signal_ema_slow": trade.signal_ema_slow,
            "signal_volume_ratio": trade.signal_volume_ratio,
            "stop_loss_price": trade.stop_loss_price,
            "take_profit_price": trade.take_profit_price,
            "opened_at": trade.opened_at.isoformat(),
            "mode": mode,
        }
        try:
            self.db.table("vn_trades").insert(row).execute()
        except Exception as e:
            logger.error(f"[DB] insert_trade failed: {e}")

    def close_trade(self, trade_id: str, fields: dict) -> None:
        try:
            self.db.table("vn_trades").update(fields).eq("id", trade_id).execute()
        except Exception as e:
            logger.error(f"[DB] close_trade failed: {e}")

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
        }
        try:
            self.db.table("vn_fitness_snapshots").insert(row).execute()
        except Exception as e:
            logger.error(f"[DB] insert_fitness_snapshot failed: {e}")

    # ── Colonies ──────────────────────────────────────────────────────────

    def insert_colony(self, colony_id: str, strategy: str, config: dict, mode: str) -> None:
        try:
            self.db.table("vn_colonies").insert({
                "id": colony_id,
                "user_id": self.user_id,
                "strategy": strategy,
                "config": config,
                "mode": mode,
            }).execute()
        except Exception as e:
            logger.error(f"[DB] insert_colony failed: {e}")

    def update_colony_status(self, colony_id: str, status: str) -> None:
        fields: dict = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
        if status == "stopped":
            fields["stopped_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self.db.table("vn_colonies").update(fields).eq("id", colony_id).execute()
        except Exception as e:
            logger.error(f"[DB] update_colony_status failed: {e}")

    # ── Generation stats ─────────────────────────────────────────────────

    def upsert_generation_stats(self, stats: dict) -> None:
        row = {
            "user_id": self.user_id,
            "run_id": self.run_id,
            **stats,
        }
        try:
            self.db.table("vn_generation_stats").upsert(
                row, on_conflict="user_id,run_id,generation"
            ).execute()
        except Exception as e:
            logger.error(f"[DB] upsert_generation_stats failed: {e}")


class EventPersister:
    """
    Handles ProbeEvents by persisting relevant ones to the database.
    Passed as the on_event callback to GenesisController.
    """

    def __init__(self, repo: VonNeumannRepository, mode: str = "simulation"):
        self.repo = repo
        self.mode = mode

    async def handle(self, event: ProbeEvent) -> None:
        etype = event.event_type
        data = event.data

        if etype == EventType.PROBE_BORN:
            parent_ids = data.get("genome", {}).get("parent_ids", []) or []
            self.repo.insert_probe({
                "probe_id": event.probe_id,
                "probe_name": data.get("probe_name", ""),
                "generation": data.get("generation", 0),
                "parent_id": parent_ids[0] if parent_ids else None,
                "parent_ids": parent_ids,
                "state": data.get("state", "OBSERVING"),
                "genome": data.get("genome", {}),
                "initial_capital": data.get("initial_capital", 0),
                "current_capital": data.get("current_capital", 0),
                "peak_capital": data.get("peak_capital", 0),
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
            )
            self.repo.insert_trade(trade, mode=self.mode)

        elif etype == EventType.TRADE_CLOSED:
            self.repo.close_trade(data["trade_id"], {
                "exit_price": data.get("exit_price"),
                "pnl": data.get("pnl"),
                "pnl_pct": data.get("pnl_pct"),
                "exit_reason": data.get("exit_reason"),
                "closed_at": event.timestamp.isoformat(),
            })

        elif etype == EventType.PROBE_UPDATE:
            self.repo.update_probe_metrics(data)

        elif etype in (EventType.PROBE_DYING, EventType.PROBE_REPRODUCING):
            reason = data.get("death_reason") or data.get("reason", etype.value)
            self.repo.update_probe(event.probe_id, {
                "state": "DEAD",
                "death_reason": reason,
                "died_at": event.timestamp.isoformat(),
                "current_capital": data.get("current_capital", 0),
                "total_trades": data.get("total_trades", 0),
                "winning_trades": data.get("winning_trades", 0),
                "total_pnl": data.get("total_pnl", 0),
                "fitness_score": data.get("fitness_score", 0),
                "sharpe_ratio": data.get("sharpe_ratio", 0),
                "max_drawdown": (data.get("max_drawdown_pct", 0) or 0) / 100.0,
            })

        elif etype == EventType.FITNESS_SNAPSHOT:
            snapshot = FitnessSnapshot(
                probe_id=event.probe_id,
                generation=data.get("generation", 0),
                tick=data.get("tick", 0),
                fitness_score=data.get("fitness_score", 0),
                roi=data.get("roi", 0),
                sharpe_ratio=data.get("sharpe_ratio", 0),
                max_drawdown=data.get("max_drawdown", 0),
                win_rate=data.get("win_rate", 0),
                trade_count=data.get("trade_count", 0),
                current_capital=data.get("current_capital", 0),
            )
            self.repo.insert_fitness_snapshot(snapshot)

        elif etype == EventType.GENERATION_COMPLETE:
            self.repo.upsert_generation_stats(data)

        elif etype == EventType.SIMULATION_STATUS:
            if data.get("status") == "stopped":
                run_id = data.get("run_id") or data.get("colony_id")
                if run_id:
                    self.repo.update_colony_status(run_id, "stopped")
