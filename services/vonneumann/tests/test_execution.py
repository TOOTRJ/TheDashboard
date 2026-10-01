"""Independent hand arithmetic and fail-closed deterministic cost accounting."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
import json
import math
import unittest

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.execution import (
        ExecutionConfig, EntryFill, ExitFill, buy_fill, sell_fill, mark_value,
        writeoff_fill, execution_record, parse_execution,
    )
    from vonneumann.core.market_validation import MarketValueError


class ExecutionTests(OfflineTestMixin, unittest.TestCase):
    def reject(self, action):
        with self.assertRaises(MarketValueError) as caught:
            action()
        self.assertEqual(str(caught.exception), "invalid_market_value")

    def test_hand_calculated_entry_mark_exit_and_all_cost_components(self):
        config = ExecutionConfig(fee_bps=10, half_spread_bps=40, slippage_bps=60)
        entry = buy_fill(202.202, 100, config)
        for field, expected in {
            "reference_price": 100, "fill_price": 101, "quantity": 2,
            "notional": 202, "fee": .202, "cash_debit": 202.202,
            "spread_cost": .8, "slippage_cost": 1.2,
        }.items():
            self.assertAlmostEqual(getattr(entry, field), expected, places=12, msg=field)
        cash = 1000 - entry.cash_debit
        self.assertAlmostEqual(cash + mark_value(entry, 100), 997.798, places=12)
        self.assertAlmostEqual(cash + mark_value(entry, 110), 1017.798, places=12)
        exit = sell_fill(entry, 110, config)
        for field, expected in {
            "reference_price": 110, "fill_price": 108.9, "quantity": 2,
            "notional": 217.8, "fee": .2178, "cash_credit": 217.5822,
            "spread_cost": .88, "slippage_cost": 1.32,
            "gross_pnl": 15.8, "net_pnl": 15.3802,
        }.items():
            self.assertAlmostEqual(getattr(exit, field), expected, places=12, msg=field)
        self.assertAlmostEqual(exit.net_return, 15.3802 / 202.202, places=14)
        self.assertAlmostEqual(cash + exit.cash_credit, 1015.3802, places=12)
        reference_profit = entry.quantity * (110 - 100)
        costs = entry.spread_cost + entry.slippage_cost + exit.spread_cost + exit.slippage_cost + entry.fee + exit.fee
        self.assertAlmostEqual(exit.net_pnl, reference_profit - costs, places=12)
        self.assertAlmostEqual(exit.net_pnl, exit.gross_pnl - entry.fee - exit.fee, places=12)

    def test_flat_price_roundtrip_loses_both_sides_costs_once(self):
        config = ExecutionConfig(10, 40, 60)
        entry = buy_fill(202.202, 100, config)
        exit = sell_fill(entry, 100, config)
        self.assertAlmostEqual(exit.net_pnl, -4.4, places=12)
        self.assertAlmostEqual(1000 - entry.cash_debit + exit.cash_credit, 995.6, places=12)
        for _ in range(3):
            self.assertAlmostEqual(mark_value(entry, 100), 200, places=12)
            self.assertEqual(sell_fill(entry, 100, config), exit)

    def test_zero_cost_control_preserves_quantity_cash_and_price_returns(self):
        config = ExecutionConfig()
        entry = buy_fill(125, 2.5, config)
        self.assertEqual((entry.quantity, entry.notional, entry.cash_debit, entry.fee), (50, 125, 125, 0))
        exit = sell_fill(entry, 3, config)
        self.assertEqual((exit.fill_price, exit.cash_credit, exit.net_pnl, exit.gross_pnl), (3, 150, 25, 25))
        self.assertEqual(exit.net_return, .2)
        self.assertEqual(mark_value(entry, 3), 150)

    def test_increasing_each_cost_never_improves_fixed_budget_trade_sequence(self):
        for prices in ((100, 110), (100, 100), (100, 20)):
            for field in ("fee_bps", "half_spread_bps", "slippage_bps"):
                credits = []
                for bps in (0, 1, 10, 100, 1000, 9000):
                    config = ExecutionConfig(**{field: bps})
                    credits.append(sell_fill(buy_fill(500, prices[0], config), prices[1], config).cash_credit)
                self.assertTrue(all(after < before for before, after in zip(credits, credits[1:])), (field, prices))

    def test_cost_config_is_immutable_and_strictly_bounded(self):
        config = ExecutionConfig(10, 20, 30)
        with self.assertRaises(FrozenInstanceError):
            config.fee_bps = 2
        self.assertEqual(ExecutionConfig.from_dict(config.to_dict()), config)
        policy = config.policy()
        self.assertEqual(policy["account_currency"], "USD")
        self.assertEqual(policy["cost_assumptions"], "uncalibrated_scenario")
        policy["config"]["fee_bps"] = 99
        self.assertEqual(config.fee_bps, 10)
        for value in (True, False, "10", None, -1, math.nan, math.inf, 10**400):
            for field in ("fee_bps", "half_spread_bps", "slippage_bps"):
                self.reject(lambda v=value, f=field: ExecutionConfig(**{f: v}))
        for values in ({"fee_bps": 10000}, {"half_spread_bps": 10000},
                       {"half_spread_bps": 5000, "slippage_bps": 5000}):
            self.reject(lambda v=values: ExecutionConfig(**v))
        for value in ({}, {"fee_bps": 0, "half_spread_bps": 0, "slippage_bps": 0, "secret": "private-token"}, None):
            self.reject(lambda v=value: ExecutionConfig.from_dict(v))

    def test_invalid_order_values_and_unrepresentable_arithmetic_fail_without_mutation(self):
        config = ExecutionConfig(10, 20, 30)
        entry = buy_fill(100, 10, config)
        before = entry.to_dict()
        for value in (True, "2", None, 0, -1, math.nan, math.inf, 10**400):
            self.reject(lambda v=value: buy_fill(v, 10, config))
            self.reject(lambda v=value: buy_fill(100, v, config))
            self.reject(lambda v=value: sell_fill(entry, v, config))
            self.reject(lambda v=value: mark_value(entry, v))
        self.reject(lambda: buy_fill(1e308, 1e-308, ExecutionConfig()))  # Quantity itself overflows.
        self.reject(lambda: buy_fill(1e-308, 1e308, ExecutionConfig()))  # Quantity itself underflows.
        self.reject(lambda: buy_fill(100, 1e308, ExecutionConfig(0, 9999, 0)))
        self.reject(lambda: sell_fill(entry, 1e308, config))
        self.assertEqual(entry.to_dict(), before)

    def test_tiny_positive_proceeds_do_not_cancel_to_zero(self):
        config = ExecutionConfig()
        entry = buy_fill(1, 1, config)
        exit = sell_fill(entry, 1e-300, config)
        self.assertEqual(exit.cash_credit, 1e-300)
        self.assertEqual(exit.net_pnl, -1)  # PnL rounding must not reconstruct cash proceeds.
        self.assertEqual(mark_value(entry, 1e-300), 1e-300)
        entry = buy_fill(1e300, 1e300, config)
        self.assertEqual(sell_fill(entry, 1e-300, config).cash_credit, 1e-300)

    def test_representable_tiny_quantity_marks_avoid_intermediate_ratio_underflow(self):
        config = ExecutionConfig()
        entry = buy_fill(1e100, 1e300, config)
        self.assertAlmostEqual(entry.quantity / 1e-200, 1, places=14)
        exit = sell_fill(entry, 1e-100, config)
        self.assertAlmostEqual(exit.cash_credit / 1e-300, 1, places=14)

    def test_extreme_valid_rates_use_positive_direct_proceeds(self):
        bps = math.nextafter(10000.0, 0.0)
        for config in (ExecutionConfig(bps, 0, 0), ExecutionConfig(0, bps, 0)):
            entry = buy_fill(100, 100, config)
            exit = sell_fill(entry, 100, config)
            self.assertGreater(exit.cash_credit, 0)
            self.assertLess(exit.cash_credit, 1e-12)

    def test_unrepresentable_positive_cost_is_not_silently_free(self):
        for config in (ExecutionConfig(1e-300, 0, 0), ExecutionConfig(0, 1e-300, 0)):
            self.reject(lambda c=config: buy_fill(100, 100, c))

    def test_decimal_reference_for_ordinary_nonround_values(self):
        with localcontext() as context:
            context.prec = 60
            D = Decimal
            budget, ref_in, ref_out = D("731.89"), D("0.00003189"), D("0.00003011")
            fee, half, slip = D("17.3") / 10000, D("11.7") / 10000, D("25.4") / 10000
            notional = budget / (1 + fee)
            price = ref_in * (1 + half + slip)
            quantity = notional / price
            proceeds = quantity * ref_out * (1 - half - slip)
            credit = proceeds * (1 - fee)
            entry = buy_fill(float(budget), float(ref_in), ExecutionConfig(17.3, 11.7, 25.4))
            exit = sell_fill(entry, float(ref_out), ExecutionConfig(17.3, 11.7, 25.4))
            for actual, expected in ((entry.notional, notional), (entry.quantity, quantity),
                                     (exit.cash_credit, credit), (exit.net_pnl, credit - budget)):
                self.assertTrue(math.isclose(actual, float(expected), rel_tol=3e-14, abs_tol=1e-13))

    def test_terminal_writeoff_is_distinct_and_charges_no_exit_execution_cost(self):
        config = ExecutionConfig(100, 20, 30)
        entry = buy_fill(100, 10, config)
        exit = writeoff_fill(entry)
        self.assertEqual(exit.kind, "writeoff")
        self.assertEqual((exit.reference_price, exit.fill_price, exit.cash_credit, exit.fee,
                          exit.spread_cost, exit.slippage_cost), (0, 0, 0, 0, 0, 0))
        self.assertEqual(exit.net_pnl, -100)
        self.assertEqual(exit.net_return, -1)
        self.assertEqual(exit.gross_pnl, -entry.notional)
        self.assertEqual(parse_execution(execution_record(config, entry, exit)), (config, entry, exit))

    def test_json_roundtrip_validates_precise_components_and_policy(self):
        config = ExecutionConfig(17.3, 11.7, 25.4)
        entry = buy_fill(731.89, .00003189, config)
        exit = sell_fill(entry, .00003011, config)
        for closed in (None, exit):
            record = execution_record(config, entry, closed)
            self.assertEqual(parse_execution(json.loads(json.dumps(record))), (config, entry, closed))
        with self.assertRaises(FrozenInstanceError):
            entry.fee = 0
        with self.assertRaises(FrozenInstanceError):
            exit.cash_credit = 999
        for section, field in (("entry", "quantity"), ("entry", "cash_debit"),
                               ("entry", "fee"), ("entry", "spread_cost"),
                               ("exit", "cash_credit"), ("exit", "gross_pnl"),
                               ("exit", "net_pnl"), ("exit", "net_return")):
            record = execution_record(config, entry, exit)
            record[section][field] += 1
            self.reject(lambda r=record: parse_execution(r))
        for field, value in (("version", "other"), ("account_currency", "USDC"), ("secret", "private-token")):
            record = execution_record(config, entry, exit)
            record[field] = value
            self.reject(lambda r=record: parse_execution(r))
        self.reject(lambda: sell_fill(entry, .00003011, ExecutionConfig()))


if __name__ == "__main__":
    unittest.main()
