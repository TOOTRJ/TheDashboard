"""
The Probe -- the core autonomous trading agent.

Each probe has:
  - A unique ID and genome (trading strategy)
  - A state machine (BORN -> OBSERVING -> TRADING -> DEAD/REPRODUCING)
  - Self-contained RSI/EMA/volume signal logic
  - Position management with stop loss and take profit
  - No database dependency -- fires events for Genesis to handle
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from .evolution import compute_fitness, compute_sharpe
from .genome import Genome
from .types import EventType, ProbeEvent, ProbeState, STATE_TRANSITIONS, TradeRecord

logger = logging.getLogger(__name__)


class Probe:
    """A single autonomous trading probe."""

    def __init__(
        self,
        genome: Genome,
        initial_capital: float,
        mode: str = "simulation",
        probe_id: Optional[str] = None,
        probe_name: Optional[str] = None,
    ):
        self.probe_id = probe_id or str(uuid.uuid4())
        self.probe_name = probe_name or f"Probe-G{genome.generation}-{self.probe_id[:4]}"
        self.genome = genome
        self.mode = mode

        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.peak_capital = initial_capital

        self.state = ProbeState.BORN
        self.born_at = datetime.now(timezone.utc)
        self.died_at: Optional[datetime] = None
        self.death_reason: Optional[str] = None

        self.birth_tick: int = 0  # Set by Genesis on spawn
        self._tick_count: int = 0  # Internal tick counter for timeframe gating
        self.open_positions: dict[str, TradeRecord] = {}
        self.closed_trades: list[TradeRecord] = []

        # Price/volume buffers (populated via on_price_update)
        self._price_buffer: dict[str, list[float]] = {
            asset: [] for asset in genome.assets
        }
        self._volume_buffer: dict[str, list[float]] = {
            asset: [] for asset in genome.assets
        }

        logger.info(
            f"[Probe {self.probe_id[:8]}] Born. Gen={genome.generation} "
            f"Capital=${initial_capital:.2f}"
        )

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def open_position_value(self) -> float:
        """Mark-to-market USDC value of all open positions at latest price."""
        total = 0.0
        for asset, trade in self.open_positions.items():
            if trade.entry_price <= 0 or trade.amount <= 0:
                continue
            prices = self._price_buffer.get(asset, [])
            if not prices:
                total += trade.amount
                continue
            current_price = prices[-1]
            total += trade.amount * (current_price / trade.entry_price)
        return total

    @property
    def total_value(self) -> float:
        """Total portfolio value: free USDC + mark-to-market open positions."""
        return self.capital + self.open_position_value

    @property
    def roi(self) -> float:
        if self.initial_capital == 0:
            return 0.0
        return (self.total_value - self.initial_capital) / self.initial_capital

    @property
    def profit(self) -> float:
        return self.total_value - self.initial_capital

    @property
    def max_drawdown(self) -> float:
        if self.peak_capital == 0:
            return 0.0
        return max(0.0, (self.peak_capital - self.total_value) / self.peak_capital)

    @property
    def num_trades(self) -> int:
        return len(self.closed_trades)

    @property
    def win_rate(self) -> float:
        wins = sum(1 for t in self.closed_trades if (t.pnl or 0) > 0)
        return wins / self.num_trades if self.num_trades > 0 else 0.0

    @property
    def winning_trades(self) -> int:
        return sum(1 for t in self.closed_trades if (t.pnl or 0) > 0)

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl or 0 for t in self.closed_trades)

    @property
    def fitness(self) -> float:
        returns = [t.return_pct() for t in self.closed_trades]
        sharpe = compute_sharpe(returns)
        return compute_fitness(
            roi=self.roi,
            sharpe=sharpe,
            max_drawdown=self.max_drawdown,
            num_trades=self.num_trades,
            win_rate=self.win_rate,
        )

    @property
    def sharpe(self) -> float:
        returns = [t.return_pct() for t in self.closed_trades]
        return compute_sharpe(returns)

    def summary(self) -> dict:
        return {
            "probe_id": self.probe_id,
            "probe_name": self.probe_name,
            "state": self.state.value,
            "generation": self.genome.generation,
            "current_capital": round(self.capital, 4),
            "open_position_value": round(self.open_position_value, 4),
            "total_value": round(self.total_value, 4),
            "initial_capital": round(self.initial_capital, 4),
            "peak_capital": round(self.peak_capital, 4),
            "roi_pct": round(self.roi * 100, 2),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "total_trades": self.num_trades,
            "winning_trades": self.winning_trades,
            "total_pnl": round(self.total_pnl, 4),
            "win_rate_pct": round(self.win_rate * 100, 2),
            "fitness_score": round(self.fitness, 4),
            "sharpe_ratio": round(self.sharpe, 4),
            "open_positions": len(self.open_positions),
            "assets": self.genome.assets,
            "genome": self.genome.to_dict(),
            "born_at": self.born_at.isoformat(),
            "died_at": self.died_at.isoformat() if self.died_at else None,
            "death_reason": self.death_reason,
            "birth_tick": self.birth_tick,
            "mode": self.mode,
        }

    # ── State transitions ────────────────────────────────────────────────

    def _transition(self, new_state: ProbeState) -> None:
        allowed = STATE_TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            raise ValueError(
                f"Invalid transition: {self.state.value} -> {new_state.value}"
            )
        old = self.state
        self.state = new_state
        logger.debug(f"[Probe {self.probe_id[:8]}] {old.value} -> {new_state.value}")

    def set_funded(self) -> None:
        self._transition(ProbeState.FUNDED)

    def set_observing(self) -> None:
        self._transition(ProbeState.OBSERVING)

    # ── Signal computation ───────────────────────────────────────────────

    def _compute_rsi(self, prices: list[float]) -> Optional[float]:
        period = self.genome.int_genes()["rsi_period"]
        if len(prices) < period + 1:
            return None
        gains, losses = [], []
        for i in range(1, period + 1):
            delta = prices[-i] - prices[-(i + 1)]
            (gains if delta > 0 else losses).append(abs(delta))
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 1e-9
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _compute_ema(self, prices: list[float], period: int) -> Optional[float]:
        if len(prices) < period:
            return None
        k = 2 / (period + 1)
        ema = prices[-period]
        for price in prices[-period + 1 :]:
            ema = price * k + ema * (1 - k)
        return ema

    def _has_entry_signal(self, asset: str) -> tuple[bool, dict]:
        """Check entry: RSI oversold + EMA crossover + volume spike."""
        prices = self._price_buffer[asset]
        volumes = self._volume_buffer[asset]
        g = self.genome
        ints = g.int_genes()

        rsi = self._compute_rsi(prices)
        ema_fast = self._compute_ema(prices, ints["ema_fast"])
        ema_slow = self._compute_ema(prices, ints["ema_slow"])

        if any(v is None for v in [rsi, ema_fast, ema_slow]):
            return False, {}

        rsi_signal = rsi < g.rsi_oversold
        trend_signal = ema_fast > ema_slow

        volume_ratio = 0.0
        volume_signal = True
        if len(volumes) >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            if avg_vol > 0:
                volume_ratio = volumes[-1] / avg_vol
                volume_signal = volume_ratio > g.volume_threshold

        all_met = rsi_signal and trend_signal and volume_signal
        signals = {
            "rsi": round(rsi, 2),
            "ema_fast": round(ema_fast, 4),
            "ema_slow": round(ema_slow, 4),
            "volume_ratio": round(volume_ratio, 2),
        }
        return all_met, signals

    def _has_exit_signal(self, asset: str) -> bool:
        """Exit: RSI overbought OR EMA fast < slow."""
        prices = self._price_buffer[asset]
        g = self.genome
        ints = g.int_genes()

        rsi = self._compute_rsi(prices)
        ema_fast = self._compute_ema(prices, ints["ema_fast"])
        ema_slow = self._compute_ema(prices, ints["ema_slow"])

        if any(v is None for v in [rsi, ema_fast, ema_slow]):
            return False

        return rsi > g.rsi_overbought or ema_fast < ema_slow

    # ── Position management ──────────────────────────────────────────────

    def _open_position(
        self, asset: str, current_price: float, signals: dict
    ) -> Optional[ProbeEvent]:
        if asset in self.open_positions:
            return None
        max_pos = self.genome.int_genes()["max_open_positions"]
        if len(self.open_positions) >= max_pos:
            return None

        size_usdc = self.capital * self.genome.position_size_pct
        if size_usdc < 0.01:
            return None

        sl_price = current_price * (1 - self.genome.stop_loss_pct)
        tp_price = current_price * (1 + self.genome.take_profit_pct)

        trade = TradeRecord(
            trade_id=str(uuid.uuid4()),
            probe_id=self.probe_id,
            pair=asset,
            side="BUY",
            entry_price=current_price,
            amount=size_usdc,
            signal_rsi=signals.get("rsi"),
            signal_ema_fast=signals.get("ema_fast"),
            signal_ema_slow=signals.get("ema_slow"),
            signal_volume_ratio=signals.get("volume_ratio"),
            stop_loss_price=sl_price,
            take_profit_price=tp_price,
        )

        self.open_positions[asset] = trade
        self.capital -= size_usdc

        logger.info(
            f"[Probe {self.probe_id[:8]}] OPEN {asset} @ ${current_price:.4f} "
            f"size=${size_usdc:.2f} SL=${sl_price:.4f} TP=${tp_price:.4f}"
        )

        return ProbeEvent(
            event_type=EventType.TRADE_OPENED,
            probe_id=self.probe_id,
            data={
                "trade_id": trade.trade_id,
                "pair": asset,
                "entry_price": current_price,
                "amount": size_usdc,
                "stop_loss_price": sl_price,
                "take_profit_price": tp_price,
                **signals,
            },
        )

    def _close_position(
        self, asset: str, current_price: float, reason: str
    ) -> Optional[ProbeEvent]:
        if asset not in self.open_positions:
            return None

        trade = self.open_positions.pop(asset)
        trade.exit_price = current_price
        trade.closed_at = datetime.now(timezone.utc)
        trade.exit_reason = reason
        trade.pnl_pct = trade.return_pct()
        trade.pnl = trade.amount * trade.pnl_pct

        self.capital += trade.amount + trade.pnl
        self.peak_capital = max(self.peak_capital, self.total_value)
        self.closed_trades.append(trade)

        logger.info(
            f"[Probe {self.probe_id[:8]}] CLOSE {asset} @ ${current_price:.4f} "
            f"PnL=${trade.pnl:.2f} ({reason})"
        )

        return ProbeEvent(
            event_type=EventType.TRADE_CLOSED,
            probe_id=self.probe_id,
            data={
                "trade_id": trade.trade_id,
                "pair": asset,
                "entry_price": trade.entry_price,
                "exit_price": current_price,
                "pnl": round(trade.pnl, 4),
                "pnl_pct": round(trade.pnl_pct * 100, 2),
                "exit_reason": reason,
            },
        )

    def _check_stop_loss_take_profit(
        self, asset: str, current_price: float
    ) -> Optional[ProbeEvent]:
        if asset not in self.open_positions:
            return None
        trade = self.open_positions[asset]
        ret = (current_price - trade.entry_price) / trade.entry_price

        if ret <= -self.genome.stop_loss_pct:
            return self._close_position(asset, current_price, "STOP_LOSS")
        if ret >= self.genome.take_profit_pct:
            return self._close_position(asset, current_price, "TAKE_PROFIT")
        return None

    # ── Lifecycle checks ─────────────────────────────────────────────────

    def _should_reproduce(self) -> bool:
        roi_met = self.roi >= self.genome.benchmark_target_pct
        dollar_met = self.profit >= self.genome.reproduce_target_dollars
        return roi_met or dollar_met

    def _should_die(self) -> bool:
        return self.max_drawdown >= self.genome.death_drawdown_pct

    # ── Price feed input ─────────────────────────────────────────────────

    def on_price_update(self, asset: str, price: float, volume: float = 0.0) -> None:
        """Called by Genesis for each market tick."""
        if asset not in self._price_buffer:
            return
        self._price_buffer[asset].append(price)
        self._volume_buffer[asset].append(volume)
        # Keep buffer bounded
        if len(self._price_buffer[asset]) > 200:
            self._price_buffer[asset].pop(0)
            self._volume_buffer[asset].pop(0)

    # ── Main tick ────────────────────────────────────────────────────────

    def tick(self) -> list[ProbeEvent]:
        """
        Main decision loop. Called once per candle close.
        Returns list of events for Genesis to handle.
        """
        events: list[ProbeEvent] = []

        if self.state not in (ProbeState.OBSERVING, ProbeState.TRADING):
            return events

        # Track peak total value (including unrealized gains) for drawdown calc.
        self.peak_capital = max(self.peak_capital, self.total_value)

        self._tick_count += 1
        timeframe = self.genome.int_genes()["timeframe_minutes"]
        evaluate_signals = (self._tick_count % timeframe == 0)

        for asset in self.genome.assets:
            prices = self._price_buffer.get(asset, [])
            if len(prices) < 2:
                continue
            current_price = prices[-1]

            # Check SL/TP every tick (risk management never skips)
            evt = self._check_stop_loss_take_profit(asset, current_price)
            if evt:
                events.append(evt)

            # Entry/exit signals only on the probe's timeframe interval
            if not evaluate_signals:
                continue

            # Entry logic
            if asset not in self.open_positions:
                has_signal, signals = self._has_entry_signal(asset)
                if has_signal:
                    if self.state == ProbeState.OBSERVING:
                        self._transition(ProbeState.TRADING)
                    evt = self._open_position(asset, current_price, signals)
                    if evt:
                        events.append(evt)
            else:
                # Exit logic (signal-based)
                if self._has_exit_signal(asset):
                    evt = self._close_position(asset, current_price, "SIGNAL_EXIT")
                    if evt:
                        events.append(evt)

        # Lifecycle checks
        if self._should_reproduce():
            events.extend(self._trigger_reproduce())
        elif self._should_die():
            events.extend(self._trigger_die("drawdown"))

        return events

    def _trigger_reproduce(self) -> list[ProbeEvent]:
        events: list[ProbeEvent] = []
        logger.info(
            f"[Probe {self.probe_id[:8]}] REPRODUCING! ROI={self.roi*100:.1f}% "
            f"Profit=${self.profit:.2f} Fitness={self.fitness:.3f}"
        )
        # Close all open positions
        for asset in list(self.open_positions.keys()):
            prices = self._price_buffer.get(asset, [])
            price = prices[-1] if prices else 0
            evt = self._close_position(asset, price, "REPRODUCING")
            if evt:
                events.append(evt)

        self._transition(ProbeState.REPRODUCING)
        events.append(
            ProbeEvent(
                event_type=EventType.PROBE_REPRODUCING,
                probe_id=self.probe_id,
                data=self.summary(),
            )
        )
        return events

    def _trigger_die(self, reason: str) -> list[ProbeEvent]:
        events: list[ProbeEvent] = []
        logger.warning(
            f"[Probe {self.probe_id[:8]}] DYING. Reason={reason} "
            f"Drawdown={self.max_drawdown*100:.1f}%"
        )
        # Close all open positions
        for asset in list(self.open_positions.keys()):
            prices = self._price_buffer.get(asset, [])
            price = prices[-1] if prices else 0
            evt = self._close_position(asset, price, "PROBE_DYING")
            if evt:
                events.append(evt)

        self._transition(ProbeState.DYING)
        self.died_at = datetime.now(timezone.utc)
        self.death_reason = reason
        events.append(
            ProbeEvent(
                event_type=EventType.PROBE_DYING,
                probe_id=self.probe_id,
                data={"reason": reason, **self.summary()},
            )
        )

        self._transition(ProbeState.DEAD)
        return events
