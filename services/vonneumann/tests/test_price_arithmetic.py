"""Offline arithmetic checks for valid prices, RSI, and closed-trade returns.

These tests deliberately do not assert market freshness. Controller failure
isolation is exercised separately from the probe arithmetic.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.genome import Genome
    from vonneumann.core.market_validation import MarketValueError
    from vonneumann.core.probe import Probe
    from vonneumann.core.types import EventType, ProbeState, TradeRecord


ASSET = "SOL/USDC"
OTHER_ASSET = "JUP/USDC"
INVALID_POSITIVE = (None, False, True, 0.0, -1.0, float("nan"), float("inf"),
                    -float("inf"), "100")
INVALID_NONNEGATIVE = (None, False, True, -1.0, float("nan"), float("inf"),
                       -float("inf"), "100")


class PriceArithmeticTests(OfflineTestMixin, unittest.TestCase):
    def probe(self, **genes):
        settings = dict(rsi_period=5.0, assets=[ASSET, OTHER_ASSET],
                        max_open_positions=2.0, position_size_pct=0.5,
                        stop_loss_pct=0.1, take_profit_pct=0.2)
        settings.update(genes)
        probe = Probe(Genome(**settings), initial_capital=100.0)
        probe.set_funded()
        probe.set_observing()
        return probe

    def trade(self, **changes):
        fields = dict(trade_id="test-trade", probe_id="test-probe", pair=ASSET,
                      side="BUY", entry_price=100.0, amount=50.0, exit_price=110.0)
        fields.update(changes)
        return TradeRecord(**fields)

    def open(self, probe, asset=ASSET, price=100.0):
        probe.on_price_update(asset, price, 1_000.0)
        event = probe._open_position(asset, price, {})
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, EventType.TRADE_OPENED)
        return probe.open_positions[asset]

    def assert_invalid_without_mutation(self, probe, action):
        # repr also compares deliberately malformed NaN fields deterministically.
        before = repr(probe.__dict__)
        positions = dict(probe.open_positions)
        with self.assertRaises(MarketValueError) as raised:
            action()
        self.assertEqual(raised.exception.code, "invalid_market_value")
        self.assertEqual(repr(probe.__dict__), before)
        self.assertEqual(set(probe.open_positions), set(positions))
        for asset, position in positions.items():
            self.assertIs(probe.open_positions[asset], position)

    def test_flat_rsi_is_neutral_without_division_by_zero(self):
        self.assertEqual(self.probe()._compute_rsi([100.0] * 6), 50.0)

    def test_rsi_with_gains_and_no_losses_is_one_hundred(self):
        self.assertEqual(self.probe()._compute_rsi([1, 2, 3, 4, 5, 6]), 100.0)

    def test_rsi_with_losses_and_no_gains_is_zero(self):
        self.assertEqual(self.probe()._compute_rsi([6, 5, 4, 3, 2, 1]), 0.0)

    def test_mixed_rsi_preserves_rolling_window_result(self):
        probe = self.probe()
        # Five moves: +2, -1, +1, -1, +5 => gains 8, losses 2 => RSI 80.
        self.assertEqual(probe._compute_rsi([10, 12, 11, 12, 11, 16]), 80.0)
        self.assertEqual(probe._compute_rsi([1_000, 10, 12, 11, 12, 11, 16]), 80.0)

    def test_rsi_waits_for_period_plus_one_valid_prices(self):
        probe = self.probe()
        for prices in ([], [100.0], [100.0] * 5):
            with self.subTest(prices=prices):
                self.assertIsNone(probe._compute_rsi(prices))

    def test_rsi_is_invariant_to_quote_scale(self):
        probe = self.probe()
        for scale in (1e-100, 1e-12, 1.0, 1e12, 1e100):
            with self.subTest(scale=scale):
                self.assertEqual(probe._compute_rsi([value * scale for value in range(1, 7)]),
                                 100.0)
                mixed = [value * scale for value in (10, 12, 11, 12, 11, 16)]
                self.assertAlmostEqual(probe._compute_rsi(mixed), 80.0, places=10)

    def test_large_finite_rsi_inputs_do_not_overflow_gain_and_loss_sums(self):
        # Five moves have two equal gains and three equal losses: RSI is 40.
        prices = [1e308, 5e307] * 3
        self.assertAlmostEqual(self.probe()._compute_rsi(prices), 40.0, places=10)

    def test_indicators_reject_invalid_prices_even_during_warmup(self):
        probe = self.probe()
        for value in INVALID_POSITIVE:
            for prices in ([value], [100.0] * 5 + [value]):
                with self.subTest(value=value, count=len(prices)):
                    with self.assertRaises(MarketValueError):
                        probe._compute_rsi(prices)
                    with self.assertRaises(MarketValueError):
                        probe._compute_ema(prices, 5)

    def test_invalid_market_price_never_enters_either_buffer(self):
        for value in INVALID_POSITIVE:
            with self.subTest(value=value):
                probe = self.probe()
                probe.on_price_update(ASSET, 100.0, 5.0)
                self.assert_invalid_without_mutation(
                    probe, lambda: probe.on_price_update(ASSET, value, 10.0))

    def test_invalid_volume_never_appends_price_first(self):
        for value in INVALID_NONNEGATIVE:
            with self.subTest(value=value):
                probe = self.probe()
                probe.on_price_update(ASSET, 100.0, 5.0)
                self.assert_invalid_without_mutation(
                    probe, lambda: probe.on_price_update(ASSET, 101.0, value))

    def test_valid_zero_volume_and_tiny_price_remain_supported(self):
        probe = self.probe()
        probe.on_price_update(ASSET, 1e-12, 0.0)
        self.assertEqual(probe._marks.get(ASSET), 1e-12)

    def test_quote_updates_retain_only_the_current_mark(self):
        probe = self.probe()
        for index in range(205):
            probe.on_price_update(ASSET, index + 1.0, float(index))
        self.assertEqual(probe._marks.get(ASSET), 205.0)
        self.assertFalse(hasattr(probe, "_price_buffer"))

    def test_huge_integer_market_inputs_raise_typed_errors_without_buffer_mutation(self):
        probe = self.probe()
        huge = 10 ** 1_000
        self.assert_invalid_without_mutation(
            probe, lambda: probe.on_price_update(ASSET, huge, 1.0))
        self.assert_invalid_without_mutation(
            probe, lambda: probe.on_price_update(ASSET, 100.0, huge))

    def test_valid_large_volume_average_preserves_ratio_instead_of_overflowing(self):
        probe = self.probe(ema_fast=2.0, ema_slow=3.0)
        snapshot = SimpleNamespace(end=1260, closes=(100.0,) * 21,
                                   volumes=(1e308,) * 21, emas={2: 100.0, 3: 100.0},
                                   completed_count=21)
        probe.attach_candle_history(SimpleNamespace(latest=lambda *_: snapshot))
        _decision, signals = probe._has_entry_signal(ASSET)
        self.assertEqual(signals["volume_ratio"], 1.0)

    def test_trade_return_distinguishes_explicit_total_loss_from_missing_exit(self):
        self.assertEqual(self.trade(exit_price=0.0).return_pct(), -1.0)
        with self.assertRaises(MarketValueError):
            self.trade(exit_price=None).return_pct()

    def test_trade_returns_preserve_profit_loss_and_break_even(self):
        for exit_price, expected in ((120.0, 0.2), (80.0, -0.2), (100.0, 0.0)):
            with self.subTest(exit_price=exit_price):
                self.assertAlmostEqual(self.trade(exit_price=exit_price).return_pct(), expected)

    def test_trade_return_rejects_malformed_entry_and_exit_prices(self):
        for value in INVALID_POSITIVE:
            with self.subTest(entry=value):
                with self.assertRaises(MarketValueError):
                    self.trade(entry_price=value).return_pct()
        for value in INVALID_NONNEGATIVE:
            with self.subTest(exit=value):
                with self.assertRaises(MarketValueError):
                    self.trade(exit_price=value).return_pct()

    def test_trade_return_overflow_is_rejected(self):
        with self.assertRaises(MarketValueError):
            self.trade(entry_price=1e-308, exit_price=1e308).return_pct()

    def test_invalid_entry_quote_never_debits_cash_or_creates_position(self):
        for value in INVALID_POSITIVE:
            with self.subTest(value=value):
                probe = self.probe()
                self.assert_invalid_without_mutation(
                    probe, lambda: probe._open_position(ASSET, value, {}))

    def test_entry_arithmetic_overflow_is_rejected_before_debit(self):
        probe = self.probe(take_profit_pct=3.0)
        self.assert_invalid_without_mutation(
            probe, lambda: probe._open_position(ASSET, 1e308, {}))
        probe = self.probe(position_size_pct=1e308)
        self.assert_invalid_without_mutation(
            probe, lambda: probe._open_position(ASSET, 100.0, {}))

    def test_position_fraction_cannot_spend_more_cash_than_is_available(self):
        probe = self.probe(position_size_pct=1.01)
        self.assert_invalid_without_mutation(
            probe, lambda: probe._open_position(ASSET, 100.0, {}))

    def test_invalid_cash_or_peak_cannot_be_hidden_by_opening_or_closing(self):
        for field in ("capital", "peak_capital"):
            for value in (None, False, -1.0, float("nan"), float("inf")):
                for action in ("open", "close"):
                    with self.subTest(field=field, value=value, action=action):
                        probe = self.probe()
                        if action == "close":
                            self.open(probe)
                        setattr(probe, field, value)
                        invoke = (lambda: probe._open_position(ASSET, 100.0, {})) \
                            if action == "open" else \
                            (lambda: probe._close_position(ASSET, 110.0, "TEST"))
                        self.assert_invalid_without_mutation(probe, invoke)

    def test_ordinary_invalid_exit_never_removes_position_or_refunds_principal(self):
        for value in INVALID_POSITIVE:
            with self.subTest(value=value):
                probe = self.probe()
                self.open(probe)
                self.assert_invalid_without_mutation(
                    probe, lambda: probe._close_position(ASSET, value, "TEST"))

    def test_explicit_terminal_zero_exit_realizes_entire_position_loss(self):
        probe = self.probe()
        trade = self.open(probe)
        event = probe._close_position(ASSET, 0.0, "TEST", terminal_loss=True)
        self.assertEqual(probe.capital, 50.0)
        self.assertEqual(probe.open_positions, {})
        self.assertEqual(probe.closed_trades, [trade])
        self.assertEqual(trade.exit_price, 0.0)
        self.assertEqual(trade.pnl, -50.0)
        self.assertEqual(trade.pnl_pct, -1.0)
        self.assertEqual(trade.exit_reason, "TERMINAL_LOSS")
        self.assertEqual(event.event_type, EventType.TRADE_CLOSED)
        self.assertEqual(event.data["pnl"], -50.0)
        self.assertEqual(event.data["pnl_pct"], -100.0)
        self.assertEqual(event.data["exit_reason"], "TERMINAL_LOSS")

    def test_terminal_loss_flag_requires_an_explicit_valid_zero(self):
        for value in (None, False, True, -1.0, 100.0, float("nan"), float("inf")):
            with self.subTest(value=value):
                probe = self.probe()
                self.open(probe)
                self.assert_invalid_without_mutation(
                    probe, lambda: probe._close_position(ASSET, value, "TEST", terminal_loss=True))

    def test_invalid_existing_position_is_rejected_before_close_mutation(self):
        for field in ("entry_price", "amount"):
            values = INVALID_POSITIVE if field == "entry_price" else INVALID_NONNEGATIVE
            for value in values:
                with self.subTest(field=field, value=value):
                    probe = self.probe()
                    trade = self.open(probe)
                    setattr(trade, field, value)
                    self.assert_invalid_without_mutation(
                        probe, lambda: probe._close_position(ASSET, 110.0, "TEST"))

    def test_close_return_or_proceeds_overflow_is_rejected_before_pop(self):
        for entry, exit_price, amount in ((1e-308, 1e308, 50.0), (100.0, 300.0, 1e308)):
            with self.subTest(entry=entry, exit_price=exit_price, amount=amount):
                probe = self.probe()
                trade = self.open(probe)
                trade.entry_price, trade.amount = entry, amount
                self.assert_invalid_without_mutation(
                    probe, lambda: probe._close_position(ASSET, exit_price, "TEST"))

    def test_valid_exit_preserves_pnl_and_drawdown_accounting(self):
        for exit_price, cash, pnl, drawdown in ((120.0, 110.0, 10.0, 0.0),
                                               (80.0, 90.0, -10.0, 0.1)):
            with self.subTest(exit_price=exit_price):
                probe = self.probe()
                trade = self.open(probe)
                probe.on_price_update(ASSET, exit_price, 1_000.0)
                event = probe._close_position(ASSET, exit_price, "TEST")
                self.assertEqual(probe.capital, cash)
                self.assertEqual(probe.total_value, cash)
                self.assertEqual(trade.pnl, pnl)
                self.assertEqual(event.data["pnl"], pnl)
                self.assertAlmostEqual(probe.max_drawdown, drawdown)

    def test_positive_exit_proceeds_survive_near_total_loss_cancellation(self):
        probe = self.probe(position_size_pct=1.0)
        trade = self.open(probe, price=1e20)
        probe.on_price_update(ASSET, 1.0, 1_000.0)
        equity_before_close = probe.total_value
        self.assertGreater(equity_before_close, 0.0)
        probe._close_position(ASSET, 1.0, "TEST")
        self.assertGreater(probe.capital, 0.0)
        self.assertEqual(probe.capital, equity_before_close)
        self.assertEqual(trade.exit_price, 1.0)
        self.assertEqual(trade.exit_reason, "TEST")

    def test_representable_close_proceeds_survive_intermediate_ratio_underflow(self):
        probe = self.probe(position_size_pct=1.0)
        trade = self.open(probe, price=1e300)
        probe.on_price_update(ASSET, 1e-24, 1_000.0)
        # exit / entry rounds to zero; the entire amount * exit / entry does not.
        self.assertEqual(1e-24 / 1e300, 0.0)
        probe._close_position(ASSET, 1e-24, "TEST")
        self.assertEqual(probe.capital, 1e-322)
        self.assertEqual(trade.exit_price, 1e-24)
        self.assertEqual(trade.exit_reason, "TEST")

    def test_unrepresentable_positive_proceeds_fail_before_position_mutation(self):
        probe = self.probe(position_size_pct=1.0)
        self.open(probe, price=1e300)
        self.assert_invalid_without_mutation(
            probe, lambda: probe._close_position(ASSET, 1e-100, "TEST"))

    def test_stop_loss_and_take_profit_still_close_at_valid_quotes(self):
        for price, reason in ((90.0, "STOP_LOSS"), (120.0, "TAKE_PROFIT")):
            with self.subTest(price=price):
                probe = self.probe()
                self.open(probe)
                event = probe._check_stop_loss_take_profit(ASSET, price)
                self.assertEqual(event.data["exit_reason"], reason)
                self.assertEqual(probe.open_positions, {})

    def test_lifecycle_missing_second_mark_cannot_partially_close_first_position(self):
        for action in ("death", "reproduce"):
            with self.subTest(action=action):
                probe = self.probe()
                probe._transition(ProbeState.TRADING)
                self.open(probe)
                self.open(probe, OTHER_ASSET)
                probe._marks.pop(OTHER_ASSET, None)
                invoke = probe._trigger_reproduce if action == "reproduce" else \
                    lambda: probe._trigger_die("TEST")
                self.assert_invalid_without_mutation(probe, invoke)

    def test_lifecycle_malformed_second_position_cannot_partially_close_first(self):
        for action in ("death", "reproduce"):
            for bad_entry in (0.0, float("nan")):
                with self.subTest(action=action, bad_entry=bad_entry):
                    probe = self.probe()
                    probe._transition(ProbeState.TRADING)
                    self.open(probe)
                    trade = self.open(probe, OTHER_ASSET)
                    trade.entry_price = bad_entry
                    invoke = probe._trigger_reproduce if action == "reproduce" else \
                        lambda: probe._trigger_die("TEST")
                    self.assert_invalid_without_mutation(probe, invoke)

    def test_lifecycle_cumulative_cash_overflow_cannot_partially_close_positions(self):
        for action in ("death", "reproduce"):
            with self.subTest(action=action):
                probe = self.probe()
                probe._transition(ProbeState.TRADING)
                first = self.open(probe)
                second = self.open(probe, OTHER_ASSET)
                # Each close alone has finite proceeds, but their sum does not.
                probe.capital = 0.0
                first.amount = second.amount = 1e308
                invoke = probe._trigger_reproduce if action == "reproduce" else \
                    lambda: probe._trigger_die("TEST")
                self.assert_invalid_without_mutation(probe, invoke)

    def test_lifecycle_validates_transition_before_any_liquidation(self):
        for action, state in (("reproduce", ProbeState.OBSERVING),
                              ("death", ProbeState.REPRODUCING)):
            with self.subTest(action=action, state=state):
                probe = self.probe()
                self.open(probe)
                probe.state = state
                before = repr(probe.__dict__)
                with self.assertRaises(ValueError):
                    if action == "reproduce":
                        probe._trigger_reproduce()
                    else:
                        probe._trigger_die("TEST")
                self.assertEqual(repr(probe.__dict__), before)

    def test_valid_reproduction_and_death_close_every_position_once(self):
        for action, final_state, final_event in (
            ("death", ProbeState.DEAD, EventType.PROBE_DYING),
            ("reproduce", ProbeState.REPRODUCING, EventType.PROBE_REPRODUCING),
        ):
            with self.subTest(action=action):
                probe = self.probe()
                probe._transition(ProbeState.TRADING)
                self.open(probe)
                self.open(probe, OTHER_ASSET)
                events = probe._trigger_reproduce() if action == "reproduce" else \
                    probe._trigger_die("TEST")
                self.assertEqual(probe.capital, 100.0)
                self.assertEqual(probe.open_positions, {})
                self.assertEqual(len(probe.closed_trades), 2)
                self.assertEqual(probe.state, final_state)
                self.assertEqual([event.event_type for event in events],
                                 [EventType.TRADE_CLOSED, EventType.TRADE_CLOSED, final_event]
                                 + ([EventType.PROBE_DEAD] if action == "death" else []))


if __name__ == "__main__":
    unittest.main()
