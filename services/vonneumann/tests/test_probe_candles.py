"""Completed-candle signals, causal quote fills, and independent risk marks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from types import MappingProxyType
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.genome import Genome
    from vonneumann.core.market_validation import MarketValueError, ProbeStepError
    from vonneumann.core.probe import Probe
    from vonneumann.core.types import EventType, ProbeState
    from vonneumann.market.feed import MarketTick, QuoteEvidence


SOL, JUP = "SOL/USDC", "JUP/USDC"


@dataclass(frozen=True)
class Snapshot:
    end: int
    closes: tuple
    volumes: tuple
    emas: object
    completed_count: int = 60
    source: str = "offline-fixture"
    quote_currency: str = "USD"
    volume_unit: str = "token"


class History:
    def __init__(self):
        self.snapshots = {}

    def latest(self, asset, timeframe):
        return self.snapshots.get((asset, timeframe))

    def put(self, asset=SOL, timeframe=1, end=1200, *, closes=None, volumes=None, emas=None):
        self.snapshots[asset, timeframe] = Snapshot(
            end, tuple(closes if closes is not None else (105, 104, 103, 102, 101, 100)),
            tuple(volumes if volumes is not None else [10] * 20 + [20]),
            MappingProxyType(emas if emas is not None else {2: 102, 3: 101}))


class ProbeCandleTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.now = 1200.0
        self.history = History()

    def probe(self, *, history=True, mode="simulation", **genes):
        settings = dict(assets=[SOL], timeframe_minutes=1, rsi_period=5,
                        ema_fast=2, ema_slow=3, rsi_oversold=30,
                        volume_threshold=1.5, benchmark_target_pct=100,
                        reproduce_target_dollars=1000, death_drawdown_pct=.99,
                        stop_loss_pct=.1, take_profit_pct=.2, position_size_pct=.5,
                        max_open_positions=2)
        settings.update(genes)
        probe = Probe(Genome(**settings), 100, mode=mode,
                      clock=lambda: datetime.fromtimestamp(self.now, timezone.utc),
                      candle_history=self.history if history else None)
        probe.set_funded()
        probe.set_observing()
        return probe

    def quote(self, probe, *, asset=SOL, price=100, stamp=None, receipt=None):
        stamp = self.now if stamp is None else stamp
        evidence = QuoteEvidence(77, self.now, receipt) if receipt is not None else None
        probe.on_quote(MarketTick(asset, price, 999_999, stamp, evidence))

    def queue_entry(self, probe, *, asset=SOL, timeframe=1):
        self.history.put(asset, timeframe, int(self.now))
        self.quote(probe, asset=asset)
        self.assertEqual(probe.tick(), [])
        self.assertIn(asset, probe._pending_intents)

    def open(self, probe, *, asset=SOL):
        self.quote(probe, asset=asset)
        event = probe._open_position(asset, 100, {})
        self.assertIsNotNone(event)
        if probe.state == ProbeState.OBSERVING:
            probe._transition(ProbeState.TRADING)
        return probe.open_positions[asset]

    def test_spot_quotes_only_update_marks_and_cannot_warm_indicators(self):
        probe = self.probe()
        for index in range(100):
            self.quote(probe, price=100 + index, stamp=self.now + index)
            self.assertEqual(probe.tick(), [])
        self.assertEqual(probe._marks, {SOL: 199})
        self.assertEqual(probe._has_entry_signal(SOL), (False, {}))
        self.assertFalse(hasattr(probe, "_price_buffer"))
        self.assertFalse(hasattr(probe, "_volume_buffer"))
        self.assertEqual(probe.open_positions, {})

    def test_attach_existing_history_and_child_birth_skip_old_signals(self):
        self.history.put()
        parent = self.probe()
        self.quote(parent)
        self.assertEqual(parent.tick(), [])
        self.assertEqual(parent._pending_intents, {})
        self.now = 1260
        self.history.put(end=1260)
        self.quote(parent)
        parent.tick()
        self.assertIn(SOL, parent._pending_intents)
        child = self.probe()
        self.quote(child)
        child.tick()
        self.assertEqual(child._pending_intents, {})
        self.assertEqual(child._candle_cursors[SOL], 1260)
        self.assertEqual(parent._has_entry_signal(SOL), child._has_entry_signal(SOL))

    def test_new_signal_cannot_fill_same_close_or_same_observation(self):
        probe = self.probe(timeframe_minutes=5, mode="paper")
        self.history.put(timeframe=5)
        self.quote(probe, stamp=1201, receipt=10)
        with patch("vonneumann.core.probe.time.monotonic", return_value=10):
            self.assertEqual(probe.tick(), [])
        self.assertEqual(probe.open_positions, {})
        self.now = 1202
        self.quote(probe, stamp=1202, receipt=10)
        self.assertEqual(probe.tick(), [])
        self.quote(probe, stamp=1200, receipt=11)
        self.assertEqual(probe.tick(), [])
        self.now = 1203
        self.quote(probe, price=105, stamp=1203, receipt=12)
        events = probe.tick()
        self.assertEqual([event.event_type for event in events], [EventType.TRADE_OPENED])
        self.assertEqual(probe.open_positions[SOL].entry_price, 105)
        self.assertEqual(probe.open_positions[SOL].signal_volume_ratio, 2)

    def test_quote_received_before_delayed_candle_availability_cannot_fill_new_signal(self):
        probe = self.probe(timeframe_minutes=5, mode="paper")
        self.history.put(timeframe=5)
        self.quote(probe, stamp=1201, receipt=10)
        with patch("vonneumann.core.probe.time.monotonic", return_value=20):
            self.assertEqual(probe.tick(), [])
        self.assertEqual(probe._pending_intents[SOL].receipt_boundary, 20)
        self.now = 1202
        self.quote(probe, stamp=1202, receipt=15)
        self.assertEqual(probe.tick(), [])
        self.assertEqual(probe.open_positions, {})
        self.now = 1203
        self.quote(probe, price=105, stamp=1203, receipt=21)
        events = probe.tick()
        self.assertEqual([event.event_type for event in events], [EventType.TRADE_OPENED])

    def test_one_minute_simulation_fills_on_next_frame_at_exact_expiry(self):
        probe = self.probe()
        self.queue_entry(probe)
        self.now = 1260
        self.history.put(end=1260)
        self.quote(probe, price=101)
        events = probe.tick()
        self.assertEqual([event.event_type for event in events], [EventType.TRADE_OPENED])
        self.assertEqual(probe.open_positions[SOL].entry_price, 101)
        self.assertEqual(probe.open_positions[SOL].opened_at.timestamp(), 1260)

    def test_old_intent_expires_when_wall_or_quote_time_passes_eligibility(self):
        for quote_stamp in (1259, 1261):
            with self.subTest(quote_stamp=quote_stamp):
                self.now = 1200
                self.history = History()
                probe = self.probe()
                self.queue_entry(probe)
                self.now = 1261 if quote_stamp == 1259 else 1259
                self.quote(probe, stamp=quote_stamp)
                self.assertEqual(probe.tick(), [])
                self.assertEqual(probe._pending_intents, {})
                self.assertEqual(probe.open_positions, {})

    def test_new_bar_supersedes_unexecutable_old_intent(self):
        probe = self.probe()
        self.queue_entry(probe)
        self.now = 1260
        self.history.put(end=1260, emas={2: 99, 3: 101})
        # An unchanged quote is not an eligible next observation.
        self.assertEqual(probe.tick(), [])
        self.assertEqual(probe._pending_intents, {})
        self.assertEqual(probe.open_positions, {})

    def test_catchup_bars_skip_orders_until_next_contiguous_close(self):
        self.history.put()
        probe = self.probe()
        self.now = 1380
        self.history.put(end=1380)
        self.quote(probe)
        probe.tick()
        self.assertEqual(probe._pending_intents, {})
        self.assertEqual(probe._candle_cursors[SOL], 1380)
        self.now = 1440
        self.history.put(end=1440)
        self.quote(probe)
        probe.tick()
        self.assertIn(SOL, probe._pending_intents)
        self.assertEqual(probe.open_positions, {})

    def test_signal_evaluation_runs_once_per_new_completed_bar_not_tick_count(self):
        probe = self.probe(timeframe_minutes=7)
        self.history.put(timeframe=7)
        self.quote(probe)
        with patch.object(probe, "_has_entry_signal", wraps=probe._has_entry_signal) as signal:
            for _ in range(30):
                probe.tick()
            signal.assert_called_once_with(SOL)
        self.assertEqual(probe._tick_count, 30)
        self.assertEqual(probe.open_positions, {})

    def test_volume_uses_twenty_prior_bars_excluding_current(self):
        probe = self.probe()
        self.history.put(volumes=[10] * 20 + [20])
        decision, signals = probe._has_entry_signal(SOL)
        self.assertTrue(decision)
        self.assertEqual(signals["volume_ratio"], 2)
        self.assertEqual(signals["rsi"], 0)

    def test_missing_zero_baseline_and_incomplete_indicators_are_unready(self):
        probe = self.probe()
        variants = ({"volumes": [10] * 20}, {"volumes": [0] * 20 + [100]},
                    {"volumes": [10] * 20 + [0]}, {"emas": {2: 102}},
                    {"closes": [100] * 5})
        for change in variants:
            with self.subTest(change=change):
                self.history.put(**change)
                self.assertFalse(probe._has_entry_signal(SOL)[0])
        self.history.put(volumes=[1e308] * 21)
        self.assertEqual(probe._has_entry_signal(SOL)[1]["volume_ratio"], 1)

    def test_completed_history_changes_cannot_replace_execution_mark(self):
        probe = self.probe()
        held = self.open(probe)
        self.history.put(closes=[1000] * 6, emas={2: 1000, 3: 1000})
        self.assertEqual(probe.total_value, 100)
        self.assertEqual(probe._marked_value(probe.capital, probe.open_positions), 100)
        self.assertEqual(probe.risk_tick(), [])
        self.quote(probe, price=80)
        events = probe.risk_tick()
        self.assertEqual(events[0].data["exit_reason"], "STOP_LOSS")
        self.assertEqual(held.exit_price, 80)
        self.assertEqual(probe.capital, 90)

    def test_risk_close_needs_no_history_and_cancels_queued_exit(self):
        probe = self.probe()
        held = self.open(probe)
        self.history.put(emas={2: 99, 3: 101})
        probe.tick()
        self.assertEqual(probe._pending_intents[SOL].action, "exit")
        self.assertEqual(probe._pending_intents[SOL].trade_id, held.trade_id)
        self.now = 1201
        self.quote(probe, price=80)
        events = probe.tick()
        self.assertEqual([event.data.get("exit_reason") for event in events], ["STOP_LOSS"])
        self.assertEqual(probe._pending_intents, {})
        self.assertEqual(probe.closed_trades, [held])

    def test_risk_loss_reaching_death_threshold_cannot_execute_another_pending_entry(self):
        probe = self.probe(assets=[SOL, JUP], death_drawdown_pct=.05)
        held = self.open(probe, asset=SOL)
        self.history.put(JUP)
        self.quote(probe, asset=JUP)
        self.assertEqual(probe.tick(), [])
        self.assertEqual(probe._pending_intents[JUP].action, "entry")
        self.now = 1201
        self.quote(probe, asset=SOL, price=80)
        self.quote(probe, asset=JUP, price=100)
        events = probe.tick()
        self.assertEqual([event.event_type for event in events],
                         [EventType.TRADE_CLOSED, EventType.PROBE_DYING, EventType.PROBE_DEAD])
        self.assertEqual(events[0].data["exit_reason"], "STOP_LOSS")
        self.assertEqual(probe.closed_trades, [held])
        self.assertEqual(probe.open_positions, {})
        self.assertEqual(probe._pending_intents, {})
        self.assertEqual(probe.capital, 90)
        self.assertEqual(probe.state, ProbeState.DEAD)

    def test_terminal_death_takes_precedence_over_simultaneous_reproduction(self):
        probe = self.probe()
        held = self.open(probe)
        with patch.object(probe, "_should_die", return_value=True), \
             patch.object(probe, "_should_reproduce", return_value=True):
            events = probe.tick()
        self.assertEqual([event.event_type for event in events],
                         [EventType.TRADE_CLOSED, EventType.PROBE_DYING, EventType.PROBE_DEAD])
        self.assertEqual(probe.closed_trades, [held])
        self.assertEqual(probe.state, ProbeState.DEAD)

    def test_reproduction_threshold_clears_pending_entry_before_new_exposure(self):
        probe = self.probe(assets=[SOL, JUP], benchmark_target_pct=.05)
        held = self.open(probe, asset=SOL)
        self.history.put(JUP)
        self.quote(probe, asset=JUP)
        probe.tick()
        self.assertIn(JUP, probe._pending_intents)
        self.now = 1201
        self.quote(probe, asset=SOL, price=115)
        self.quote(probe, asset=JUP, price=100)
        events = probe.tick()
        self.assertEqual([event.event_type for event in events],
                         [EventType.TRADE_CLOSED, EventType.PROBE_REPRODUCING])
        self.assertEqual(probe.closed_trades, [held])
        self.assertEqual(probe._pending_intents, {})
        self.assertEqual(probe.state, ProbeState.REPRODUCING)

    def test_signal_exit_uses_later_quote_and_matches_original_trade(self):
        probe = self.probe()
        held = self.open(probe)
        self.history.put(emas={2: 99, 3: 101})
        self.assertEqual(probe.tick(), [])
        self.now = 1201
        self.quote(probe, price=105)
        events = probe.tick()
        self.assertEqual(events[0].data["exit_reason"], "SIGNAL_EXIT")
        self.assertEqual(held.exit_price, 105)

    def test_replaced_position_cannot_be_closed_by_prior_trade_exit_intent(self):
        probe = self.probe()
        held = self.open(probe)
        self.history.put(emas={2: 99, 3: 101})
        probe.tick()
        # Deliberately simulate a replacement trade without clearing the old
        # intent to exercise the trade identity check itself.
        held.trade_id = "replacement-position"
        self.now = 1201
        self.quote(probe, price=105)
        self.assertEqual(probe.tick(), [])
        self.assertIs(probe.open_positions[SOL], held)
        self.assertEqual(probe.closed_trades, [])

    def test_lifecycle_and_retirement_clear_unexecuted_intents(self):
        for action in ("death", "reproduce", "retire"):
            with self.subTest(action=action):
                self.history = History()
                probe = self.probe()
                self.queue_entry(probe)
                if action == "death":
                    probe._trigger_die("test")
                elif action == "reproduce":
                    probe._transition(ProbeState.TRADING)
                    probe._trigger_reproduce()
                else:
                    probe.close_all_positions({}, "EVOLUTION")
                self.assertEqual(probe._pending_intents, {})

    def test_mark_only_update_cannot_advance_quote_receipt_or_create_fill(self):
        probe = self.probe()
        self.queue_entry(probe)
        self.now = 1201
        probe.on_price_update(SOL, 101, 1000)
        self.assertEqual(probe.tick(), [])
        self.assertEqual(probe._quote_observations, {})
        self.assertEqual(probe.open_positions, {})

    def test_invalid_quote_is_atomic_before_any_mark_change(self):
        probe = self.probe()
        self.quote(probe)
        for tick in (MarketTick(SOL, 101, -1, 1201), MarketTick(SOL, 101, 1, float("nan")),
                     MarketTick(SOL, 101, 1, 1201, QuoteEvidence(77, 1201, -1))):
            with self.subTest(tick=tick):
                before = repr(probe.__dict__)
                with self.assertRaises(MarketValueError):
                    probe.on_quote(tick)
                self.assertEqual(repr(probe.__dict__), before)

    def test_completed_fill_events_survive_later_asset_failure(self):
        probe = self.probe(assets=[SOL, JUP])
        self.history.put(SOL)
        self.history.put(JUP)
        self.quote(probe, asset=SOL)
        self.quote(probe, asset=JUP)
        probe.tick()
        self.now = 1201
        self.quote(probe, asset=SOL, price=101)
        self.quote(probe, asset=JUP, price=101)
        original = probe._open_position
        def open_or_fail(asset, price, signals):
            if asset == JUP:
                raise MarketValueError()
            return original(asset, price, signals)
        with patch.object(probe, "_open_position", side_effect=open_or_fail):
            with self.assertRaises(ProbeStepError) as raised:
                probe.tick()
        self.assertEqual([event.event_type for event in raised.exception.events], [EventType.TRADE_OPENED])
        self.assertEqual(set(probe.open_positions), {SOL})
        self.assertEqual(probe.capital, 50)

    def test_ema_uses_sma_seed_and_all_remaining_closes(self):
        probe = self.probe()
        prices = [10, 11, 13, 12, 14, 16, 15]
        with localcontext() as context:
            context.prec = 60
            expected = sum(map(Decimal, prices[:3])) / Decimal(3)
            alpha = Decimal(2) / Decimal(4)
            for price in prices[3:]:
                expected += (Decimal(price) - expected) * alpha
        self.assertAlmostEqual(probe._compute_ema(prices, 3), float(expected), places=12)
        self.assertEqual(probe._compute_ema([10, 20, 30], 3), 20)
        self.assertIsNone(probe._compute_ema([10, 20], 3))
        self.assertEqual(probe._compute_ema([1e308] * 60, 60), 1e308)
        self.assertEqual(probe._compute_ema([1e-323] * 60, 60), 1e-323)

    def test_shared_recursive_ema_values_are_used_without_reseeding_retained_closes(self):
        probe = self.probe()
        self.history.put(emas={2: 102, 3: 101})
        with patch.object(probe, "_compute_ema", side_effect=AssertionError("Must use shared EMA state")):
            self.assertTrue(probe._has_entry_signal(SOL)[0])
            self.assertFalse(probe._has_exit_signal(SOL))
