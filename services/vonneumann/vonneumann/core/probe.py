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
import math
import uuid
from copy import copy
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable, Optional

from .clock import clock_datetime, utc_now
from .evolution import compute_fitness, compute_sharpe
from .genome import Genome
from .market_validation import (
    MarketValueError,
    ProbeStepError,
    finite_number,
    nonnegative_value,
    position_value,
    positive_price,
    trade_return,
)
from .types import EventType, ProbeEvent, ProbeState, STATE_TRANSITIONS, TradeRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ClosePlan:
    asset: str
    trade: TradeRecord
    exit_price: float
    pnl_pct: float
    pnl: float
    capital: float
    peak_capital: float
    reason: str
    closed_at: datetime
    event: ProbeEvent


class Probe:
    """A single autonomous trading probe."""

    def __init__(
        self,
        genome: Genome,
        initial_capital: float,
        mode: str = "simulation",
        probe_id: Optional[str] = None,
        probe_name: Optional[str] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self._clock = clock or utc_now
        self.probe_id = probe_id or str(uuid.uuid4())
        self.probe_name = probe_name or f"Probe-G{genome.generation}-{self.probe_id[:4]}"
        self.genome = genome
        self.mode = mode

        self.initial_capital = positive_price(initial_capital)
        self.capital = self.initial_capital
        self.peak_capital = self.initial_capital

        self.state = ProbeState.BORN
        self.born_at = self._now()
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

    def _now(self) -> datetime:
        return clock_datetime(self._clock())

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
            current_price = positive_price(prices[-1])
            total += position_value(trade.amount, trade.entry_price, current_price)
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
        prices = [positive_price(price) for price in prices]
        period = self.genome.int_genes()["rsi_period"]
        if len(prices) < period + 1:
            return None
        deltas = [prices[-i] - prices[-(i + 1)] for i in range(1, period + 1)]
        scale = max(abs(delta) for delta in deltas)
        if scale == 0:
            # Explicit project convention for a flat rolling window.
            return 50.0
        # The common period and scale cancel in RSI. Scaling deltas avoids
        # overflow without a fixed epsilon that distorts small-price assets.
        gains = math.fsum(delta / scale for delta in deltas if delta > 0)
        losses = math.fsum(-delta / scale for delta in deltas if delta < 0)
        if losses == 0:
            return 100.0
        if gains == 0:
            return 0.0
        return 100.0 * gains / (gains + losses)

    def _compute_ema(self, prices: list[float], period: int) -> Optional[float]:
        prices = [positive_price(price) for price in prices]
        if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
            raise MarketValueError()
        if len(prices) < period:
            return None
        k = 2 / (period + 1)
        ema = prices[-period]
        for price in prices[len(prices) - period + 1 :]:
            ema = positive_price(ema + (price - ema) * k)
        return ema

    def _has_entry_signal(self, asset: str) -> tuple[bool, dict]:
        """Check entry: RSI oversold + EMA crossover + volume spike."""
        prices = self._price_buffer[asset]
        volumes = [nonnegative_value(volume) for volume in self._volume_buffer[asset]]
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
            scale = max(volumes[-20:])
            if scale > 0:
                average_scaled = math.fsum(volume / scale for volume in volumes[-20:]) / 20
                volume_ratio = finite_number((volumes[-1] / scale) / average_scaled)
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
        current_price = positive_price(current_price)
        capital = nonnegative_value(self.capital)
        nonnegative_value(self.peak_capital)
        if asset in self.open_positions:
            return None
        max_pos = self.genome.int_genes()["max_open_positions"]
        if len(self.open_positions) >= max_pos:
            return None

        fraction = nonnegative_value(self.genome.position_size_pct)
        if fraction > 1:
            raise MarketValueError()
        size_usdc = nonnegative_value(capital * fraction)
        capital_after = nonnegative_value(capital - size_usdc)
        if size_usdc < 0.01:
            return None

        stop_loss = nonnegative_value(self.genome.stop_loss_pct)
        take_profit = nonnegative_value(self.genome.take_profit_pct)
        sl_price = positive_price(current_price * (1 - stop_loss))
        tp_price = positive_price(current_price * (1 + take_profit))
        opened_at = self._now()

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
            opened_at=opened_at,
        )

        self.open_positions[asset] = trade
        self.capital = capital_after

        logger.info(
            f"[Probe {self.probe_id[:8]}] OPEN {asset} @ ${current_price:.4f} "
            f"size=${size_usdc:.2f} SL=${sl_price:.4f} TP=${tp_price:.4f}"
        )

        return ProbeEvent(
            event_type=EventType.TRADE_OPENED,
            probe_id=self.probe_id,
            timestamp=opened_at,
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
        self, asset: str, current_price: float, reason: str, *, terminal_loss: bool = False
    ) -> Optional[ProbeEvent]:
        if asset not in self.open_positions:
            return None
        plans = self._plan_closures({asset: (current_price, reason, terminal_loss)})
        return self._apply_close_plan(plans[0])

    def _marked_value(self, capital: float, positions: dict[str, TradeRecord],
                      marks: Optional[dict[str, float]] = None) -> float:
        """Strict valuation for decisions, without changing reporting fallback."""
        value = nonnegative_value(capital)
        for asset, trade in positions.items():
            prices = self._price_buffer.get(asset, [])
            price = marks.get(asset) if marks is not None else (prices[-1] if prices else None)
            mark = positive_price(price)
            entry = positive_price(trade.entry_price)
            amount = nonnegative_value(trade.amount)
            marked = position_value(amount, entry, mark)
            value = nonnegative_value(value + marked)
        return value

    def _plan_closures(self, requests: dict[str, tuple[float, str, bool]], *,
                       marks: Optional[dict[str, float]] = None) -> list[_ClosePlan]:
        """Validate a whole cashflow before touching any trade or ledger field."""
        capital = nonnegative_value(self.capital)
        peak = nonnegative_value(self.peak_capital)
        remaining = dict(self.open_positions)
        plans = []
        for asset, (raw_price, reason, terminal_loss) in requests.items():
            if not isinstance(terminal_loss, bool):
                raise MarketValueError()
            if terminal_loss:
                price = nonnegative_value(raw_price)
                if price != 0:
                    raise MarketValueError()
                reason = "TERMINAL_LOSS"
            else:
                price = positive_price(raw_price)
            trade = remaining.pop(asset)
            amount = nonnegative_value(trade.amount)
            return_pct = trade_return(trade.entry_price, price)
            # Derive proceeds directly: amount + amount * return can cancel
            # an ordinary positive exit down to zero after a near-total loss.
            proceeds = position_value(amount, trade.entry_price, price)
            pnl = finite_number(proceeds - amount)
            capital = nonnegative_value(capital + proceeds)
            percent = finite_number(return_pct * 100)
            try:
                value = self._marked_value(capital, remaining, marks)
            except MarketValueError:
                if marks is not None:
                    raise
                # A bad OTHER position must not block a valid risk-reducing
                # close. Its risk check will fail separately; retain the peak
                # until the remaining portfolio has a valid valuation.
            else:
                peak = max(peak, value)
            closed_at = self._now()
            event = ProbeEvent(
                event_type=EventType.TRADE_CLOSED,
                probe_id=self.probe_id,
                timestamp=closed_at,
                data={
                    "trade_id": trade.trade_id,
                    "pair": asset,
                    "entry_price": trade.entry_price,
                    "exit_price": price,
                    "pnl": round(pnl, 4),
                    "pnl_pct": round(percent, 2),
                    "exit_reason": reason,
                },
            )
            plans.append(_ClosePlan(asset, trade, price, return_pct, pnl, capital,
                                    peak, reason, closed_at, event))
        return plans

    def _apply_close_plan(self, plan: _ClosePlan) -> ProbeEvent:
        trade = self.open_positions.pop(plan.asset)
        trade.exit_price = plan.exit_price
        trade.closed_at = plan.closed_at
        trade.exit_reason = plan.reason
        trade.pnl_pct = plan.pnl_pct
        trade.pnl = plan.pnl
        self.capital = plan.capital
        self.peak_capital = plan.peak_capital
        self.closed_trades.append(trade)
        logger.info(
            f"[Probe {self.probe_id[:8]}] CLOSE {plan.asset} @ ${plan.exit_price:.4f} "
            f"PnL=${plan.pnl:.2f} ({plan.reason})"
        )
        return plan.event

    def _liquidation_plans(self, prices: dict[str, float], reason: str) -> list[_ClosePlan]:
        marks = {asset: positive_price(prices.get(asset)) for asset in self.open_positions}
        return self._plan_closures(
            {asset: (price, reason, False) for asset, price in marks.items()}, marks=marks)

    def validate_liquidation(self, prices: dict[str, float]) -> float:
        """Return final cash only if every required mark and close is valid."""
        plans = self._liquidation_plans(prices, "EVOLUTION")
        self._projected_summary(plans)
        return plans[-1].capital if plans else nonnegative_value(self.capital)

    def close_all_positions(self, prices: dict[str, float], reason: str) -> list[ProbeEvent]:
        """Close a fully validated batch, preserving each existing trade object."""
        plans = self._liquidation_plans(prices, reason)
        self._projected_summary(plans)
        return [self._apply_close_plan(plan) for plan in plans]

    def _check_stop_loss_take_profit(
        self, asset: str, current_price: float
    ) -> Optional[ProbeEvent]:
        if asset not in self.open_positions:
            return None
        trade = self.open_positions[asset]
        current_price = positive_price(current_price)
        nonnegative_value(trade.amount)
        ret = trade_return(trade.entry_price, current_price)

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
        price = positive_price(price)
        volume = nonnegative_value(volume)
        self._price_buffer[asset].append(price)
        self._volume_buffer[asset].append(volume)
        # Keep buffer bounded
        if len(self._price_buffer[asset]) > 200:
            self._price_buffer[asset].pop(0)
            self._volume_buffer[asset].pop(0)

    # ── Main tick ────────────────────────────────────────────────────────

    def risk_tick(self, *, assets: Optional[set[str]] = None) -> list[ProbeEvent]:
        """Check every eligible held asset, retaining events if another fails.

        Genesis supplies the assets with accepted observations for this tick.
        Direct callers may omit the filter to check every held asset. A single
        valid quote is enough for a stop; indicator warm-up is irrelevant here.
        """
        events: list[ProbeEvent] = []
        if self.state not in (ProbeState.OBSERVING, ProbeState.TRADING):
            return events
        first_error = None
        for asset in list(self.open_positions):
            if assets is not None and asset not in assets:
                continue
            try:
                prices = self._price_buffer.get(asset, [])
                price = positive_price(prices[-1] if prices else None)
                event = self._check_stop_loss_take_profit(asset, price)
                if event is not None:
                    events.append(event)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise ProbeStepError(events, first_error) from first_error
        return events

    def tick(self, *, check_risk: bool = True) -> list[ProbeEvent]:
        """
        Main decision loop. Called once per candle close.
        Returns list of events for Genesis to handle.
        """
        events: list[ProbeEvent] = []

        if self.state not in (ProbeState.OBSERVING, ProbeState.TRADING):
            return events

        try:
            if check_risk:
                events.extend(self.risk_tick())
            # Decisions require a valid current portfolio value. Reporting's
            # historical missing-mark fallback remains a separate contract.
            value = self._marked_value(self.capital, self.open_positions)
            self.peak_capital = max(nonnegative_value(self.peak_capital), value)

            self._tick_count += 1
            timeframe = self.genome.int_genes()["timeframe_minutes"]
            evaluate_signals = (self._tick_count % timeframe == 0)

            for asset in self.genome.assets:
                prices = self._price_buffer.get(asset, [])
                if len(prices) < 2 or not evaluate_signals:
                    continue
                current_price = positive_price(prices[-1])

                if asset not in self.open_positions:
                    has_signal, signals = self._has_entry_signal(asset)
                    if has_signal:
                        evt = self._open_position(asset, current_price, signals)
                        if evt:
                            if self.state == ProbeState.OBSERVING:
                                self._transition(ProbeState.TRADING)
                            events.append(evt)
                elif self._has_exit_signal(asset):
                    evt = self._close_position(asset, current_price, "SIGNAL_EXIT")
                    if evt:
                        events.append(evt)

            if self._should_reproduce():
                events.extend(self._trigger_reproduce())
            elif self._should_die():
                events.extend(self._trigger_die("drawdown"))
        except ProbeStepError as exc:
            raise ProbeStepError([*events, *exc.events], exc.cause) from exc
        except Exception as exc:
            raise ProbeStepError(events, exc) from exc
        return events

    def _lifecycle_plan(self, new_state: ProbeState, close_reason: str, *,
                        death_reason: Optional[str] = None
                        ) -> tuple[list[_ClosePlan], dict, Optional[datetime]]:
        if new_state not in STATE_TRANSITIONS.get(self.state, []):
            raise ValueError(f"Invalid transition: {self.state.value} -> {new_state.value}")
        marks = {}
        for asset in self.open_positions:
            prices = self._price_buffer.get(asset, [])
            marks[asset] = positive_price(prices[-1] if prices else None)
        plans = self._liquidation_plans(marks, close_reason)
        data, died_at = self._projected_summary(plans, new_state, death_reason=death_reason)
        return plans, data, died_at

    def _projected_summary(self, plans: list[_ClosePlan],
                           new_state: Optional[ProbeState] = None, *,
                           death_reason: Optional[str] = None
                           ) -> tuple[dict, Optional[datetime]]:
        # Compute the terminal event before committing. A malformed historical
        # return or overflowing fitness calculation must not lose close events
        # after the portfolio has already been liquidated. Scheduled evolution
        # uses this same check for every parent before retiring the first one.
        positive_price(self.initial_capital)
        projected = copy(self)
        projected.open_positions = {}
        projected.closed_trades = self.closed_trades + [
            replace(plan.trade, exit_price=plan.exit_price, closed_at=plan.closed_at,
                    exit_reason=plan.reason, pnl_pct=plan.pnl_pct, pnl=plan.pnl)
            for plan in plans
        ]
        if plans:
            projected.capital = plans[-1].capital
            projected.peak_capital = plans[-1].peak_capital
        if new_state is not None:
            projected.state = new_state
        if new_state == ProbeState.DYING:
            projected.died_at = self._now()
            projected.death_reason = death_reason
        try:
            data = projected.summary()
            for value in data.values():
                if isinstance(value, (int, float)):
                    finite_number(value)
        except ArithmeticError:
            raise MarketValueError() from None
        return data, projected.died_at

    def _trigger_reproduce(self) -> list[ProbeEvent]:
        plans, data, _ = self._lifecycle_plan(ProbeState.REPRODUCING, "REPRODUCING")
        event_time = self._now()
        events = [self._apply_close_plan(plan) for plan in plans]
        self._transition(ProbeState.REPRODUCING)
        events.append(
            ProbeEvent(
                event_type=EventType.PROBE_REPRODUCING,
                probe_id=self.probe_id,
                timestamp=event_time,
                data=data,
            )
        )
        return events

    def _trigger_die(self, reason: str) -> list[ProbeEvent]:
        plans, data, died_at = self._lifecycle_plan(
            ProbeState.DYING, "PROBE_DYING", death_reason=reason)
        events = [self._apply_close_plan(plan) for plan in plans]
        logger.warning(
            f"[Probe {self.probe_id[:8]}] DYING. Reason={reason}"
        )
        self._transition(ProbeState.DYING)
        self.died_at = died_at
        self.death_reason = reason
        events.append(
            ProbeEvent(
                event_type=EventType.PROBE_DYING,
                probe_id=self.probe_id,
                timestamp=died_at,
                data={"reason": reason, **data},
            )
        )

        self._transition(ProbeState.DEAD)
        return events
