"""Core types for the Von Neumann trading system."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from .market_validation import trade_return


class ProbeState(str, Enum):
    BORN = "BORN"
    FUNDED = "FUNDED"
    OBSERVING = "OBSERVING"
    TRADING = "TRADING"
    REPRODUCING = "REPRODUCING"
    DYING = "DYING"
    DEAD = "DEAD"


# Valid state transitions (current -> allowed next states)
STATE_TRANSITIONS: dict[ProbeState, list[ProbeState]] = {
    ProbeState.BORN: [ProbeState.FUNDED],
    ProbeState.FUNDED: [ProbeState.OBSERVING],
    ProbeState.OBSERVING: [ProbeState.TRADING, ProbeState.DYING],
    ProbeState.TRADING: [ProbeState.REPRODUCING, ProbeState.DYING],
    ProbeState.REPRODUCING: [ProbeState.DEAD],
    ProbeState.DYING: [ProbeState.DEAD],
    ProbeState.DEAD: [],
}


@dataclass
class TradeRecord:
    trade_id: str
    probe_id: str
    pair: str
    side: str  # 'BUY' | 'SELL'
    entry_price: float
    amount: float  # USDC size
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    signal_rsi: Optional[float] = None
    signal_ema_fast: Optional[float] = None
    signal_ema_slow: Optional[float] = None
    signal_volume_ratio: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None

    def return_pct(self) -> float:
        return trade_return(self.entry_price, self.exit_price)


@dataclass
class FitnessSnapshot:
    probe_id: str
    generation: int
    tick: int
    fitness_score: float
    roi: float
    sharpe_ratio: Optional[float]
    max_drawdown: float
    win_rate: float
    trade_count: int
    current_capital: float
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: Optional[dict] = None


class EventType(str, Enum):
    PROBE_BORN = "probe_born"
    PROBE_FUNDED = "probe_funded"
    PROBE_OBSERVING = "probe_observing"
    TRADE_OPENED = "trade_opened"
    TRADE_CLOSED = "trade_closed"
    PROBE_REPRODUCING = "probe_reproducing"
    PROBE_DYING = "probe_dying"
    PROBE_DEAD = "probe_dead"
    GENERATION_COMPLETE = "generation_complete"
    SIMULATION_STATUS = "simulation_status"
    CIRCUIT_BREAKER = "circuit_breaker"
    PROBE_UPDATE = "probe_update"
    PRICE_UPDATE = "price_update"
    FITNESS_SNAPSHOT = "fitness_snapshot"


@dataclass
class ProbeEvent:
    event_type: EventType
    probe_id: str
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_ws_message(self) -> dict:
        return {
            "type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": {"probe_id": self.probe_id, **self.data},
        }
