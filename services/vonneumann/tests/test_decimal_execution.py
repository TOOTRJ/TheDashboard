"""Independent accounting checks for the explicit decimal reference policy.

Fraction-based oracles and hand-calculated balances do not share the planner's
integer implementation. No legacy floating-point fill is converted into a new
fill, and no market provider or configured database is contacted.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import (
    Decimal, FloatOperation, Inexact, Rounded, ROUND_CEILING, ROUND_DOWN,
    getcontext, localcontext,
)
from fractions import Fraction
import json
import random
import unittest

from tests.security_support import deny_network
from vonneumann.core.decimal_execution import (
    DecimalExecutionConfig,
    EntryPlan,
    ExitPlan,
    credit_cash,
    debit_cash,
    mark_value,
    transfer_cash,
)


CASH_SCALE = 36
PRICE_SCALE = QUANTITY_SCALE = 18
MAXIMUM = "1000000000000000000000000000000000000"
MIN_CASH = "0." + "0" * 35 + "1"
MIN_PRICE = "0." + "0" * 17 + "1"


def ratio(value):
    return Fraction(value)


def render(value: Fraction, scale=36) -> str:
    scaled = value * 10**scale
    if scaled.denominator != 1:
        raise AssertionError("Oracle value does not lie on the declared grid")
    amount = scaled.numerator
    sign = "-" if amount < 0 else ""
    whole, fraction = divmod(abs(amount), 10**scale)
    tail = str(fraction).rjust(scale, "0").rstrip("0")
    return sign + str(whole) + ("." + tail if tail else "")


def floor_grid(value: Fraction, scale):
    scaled = value * 10**scale
    return Fraction(scaled.numerator // scaled.denominator, 10**scale)


def ceil_grid(value: Fraction, scale):
    return -floor_grid(-value, scale)


def entry_oracle(budget, reference, fee, spread, slippage):
    fee_rate = ratio(fee) / 10000
    impact = (ratio(spread) + ratio(slippage)) / 10000
    price = ceil_grid(ratio(reference) * (1 + impact), PRICE_SCALE)
    quantity = floor_grid(ratio(budget) / (price * (1 + fee_rate)), QUANTITY_SCALE)
    notional = quantity * price
    charge = ceil_grid(notional * fee_rate, CASH_SCALE)
    debit = notional + charge
    return {"fill_price": render(price), "quantity": render(quantity),
            "notional": render(notional), "fee": render(charge),
            "cash_debit": render(debit), "residual_budget": render(ratio(budget) - debit)}


def exit_oracle(entry, reference, fee, spread, slippage):
    fee_rate = ratio(fee) / 10000
    impact = (ratio(spread) + ratio(slippage)) / 10000
    price = floor_grid(ratio(reference) * (1 - impact), PRICE_SCALE)
    notional = ratio(entry.quantity) * price
    charge = ceil_grid(notional * fee_rate, CASH_SCALE)
    credit = notional - charge
    return {"fill_price": render(price), "quantity": entry.quantity,
            "notional": render(notional), "fee": render(charge),
            "cash_credit": render(credit),
            "gross_pnl": render(notional - ratio(entry.notional)),
            "net_pnl": render(credit - ratio(entry.cash_debit))}


class DecimalExecutionTests(unittest.TestCase):
    def setUp(self):
        self.network_guard = deny_network()
        self.network_guard.__enter__()
        self.addCleanup(self.network_guard.__exit__, None, None, None)

    def config(self, fee="0", spread="0", slippage="0"):
        return DecimalExecutionConfig(fee_bps=fee, half_spread_bps=spread, slippage_bps=slippage)

    def assert_fields(self, value, expected):
        for name, field in expected.items():
            with self.subTest(field=name):
                self.assertEqual(getattr(value, name), field)

    def assert_json_without_floats(self, value):
        if type(value) is dict:
            self.assertTrue(all(type(key) is str for key in value))
            for item in value.values():
                self.assert_json_without_floats(item)
        elif type(value) is list:
            for item in value:
                self.assert_json_without_floats(item)
        else:
            self.assertIn(type(value), (str, int, bool, type(None)))

    def test_hand_calculated_zero_cost_round_trip_conserves_whole_account(self):
        entry = EntryPlan("100", "25", self.config())
        self.assert_fields(entry, {"fill_price": "25", "quantity": "4", "notional": "100",
                                   "fee": "0", "cash_debit": "100", "residual_budget": "0"})
        exited = ExitPlan(entry, "30")
        self.assert_fields(exited, {"kind": "fill", "quantity": "4", "fill_price": "30",
                                    "notional": "120", "fee": "0", "cash_credit": "120",
                                    "gross_pnl": "20", "net_pnl": "20"})
        after_open = debit_cash("100", entry.cash_debit)
        self.assertEqual(after_open, "0")
        self.assertEqual(credit_cash(after_open, exited.cash_credit), "120")

    def test_quantity_residual_stays_cash_and_never_becomes_a_fee(self):
        entry = EntryPlan("100", "3", self.config())
        self.assert_fields(entry, {"quantity": "33.333333333333333333",
                                   "notional": "99.999999999999999999", "fee": "0",
                                   "cash_debit": "99.999999999999999999",
                                   "residual_budget": "0.000000000000000001"})
        self.assertEqual(debit_cash("100", entry.cash_debit), entry.residual_budget)
        exited = ExitPlan(entry, "3")
        self.assertEqual(exited.net_pnl, "0")
        self.assertEqual(credit_cash(entry.residual_budget, exited.cash_credit), "100")

    def test_full_budget_with_costs_never_overspends_and_matches_fraction_oracle(self):
        entry = EntryPlan("100", "123.45", self.config("30", "10", "10"))
        expected = entry_oracle("100", "123.45", "30", "10", "10")
        self.assert_fields(entry, expected)
        self.assertLessEqual(ratio(entry.cash_debit), 100)
        self.assertEqual(ratio(entry.notional) + ratio(entry.fee), ratio(entry.cash_debit))
        self.assertEqual(ratio(entry.cash_debit) + ratio(entry.residual_budget), 100)
        exited = ExitPlan(entry, "130.15")
        self.assert_fields(exited, exit_oracle(entry, "130.15", "30", "10", "10"))
        self.assertEqual(ratio(exited.cash_credit) + ratio(exited.fee), ratio(exited.notional))

    def test_adverse_price_rounding_is_explicit_in_both_directions(self):
        reference = "0.123456789012345678"
        cfg = self.config("0", "0.000001", "0")
        entry = EntryPlan("1", reference, cfg)
        ideal_buy = ratio(reference) * (1 + ratio("0.000001") / 10000)
        self.assertEqual(entry.fill_price, "0.123456789024691357")
        self.assertGreater(ratio(entry.fill_price), ideal_buy)
        self.assertLess(ratio(entry.fill_price) - ideal_buy, ratio(MIN_PRICE))
        exited = ExitPlan(entry, reference)
        ideal_sell = ratio(reference) * (1 - ratio("0.000001") / 10000)
        self.assertLess(ratio(exited.fill_price), ideal_sell)
        self.assertLess(ideal_sell - ratio(exited.fill_price), ratio(MIN_PRICE))
        self.assert_fields(exited, exit_oracle(entry, reference, "0", "0.000001", "0"))

    def test_one_cash_quantum_can_buy_one_quantity_quantum_without_costs(self):
        entry = EntryPlan(MIN_CASH, MIN_PRICE, self.config())
        self.assertEqual(entry.quantity, MIN_PRICE)
        self.assertEqual(entry.cash_debit, MIN_CASH)
        self.assertEqual(entry.notional, MIN_CASH)
        self.assertEqual(entry.residual_budget, "0")
        self.assertEqual(ExitPlan(entry, MIN_PRICE).cash_credit, MIN_CASH)

    def test_fee_rounding_can_produce_zero_credit_fill_without_faking_writeoff(self):
        budget = "0." + "0" * 35 + "2"
        entry = EntryPlan(budget, MIN_PRICE, self.config("1"))
        self.assertEqual(entry.quantity, MIN_PRICE)
        self.assertEqual(entry.notional, MIN_CASH)
        self.assertEqual(entry.fee, MIN_CASH)
        self.assertEqual(entry.cash_debit, budget)
        ordinary = ExitPlan(entry, MIN_PRICE)
        self.assertEqual(ordinary.kind, "fill")
        self.assertEqual(ordinary.notional, MIN_CASH)
        self.assertEqual(ordinary.fee, MIN_CASH)
        self.assertEqual(ordinary.cash_credit, "0")
        self.assertEqual(ordinary.gross_pnl, "0")
        self.assertEqual(ordinary.net_pnl, "-" + budget)
        writeoff = ExitPlan(entry, None)
        self.assertEqual(writeoff.kind, "writeoff")
        self.assertEqual(writeoff.notional, "0")
        self.assertEqual(writeoff.fee, "0")
        self.assertEqual(writeoff.gross_pnl, "-" + MIN_CASH)
        self.assertEqual(writeoff.net_pnl, ordinary.net_pnl)

    def test_sub_lot_budget_rejects_without_consuming_cash(self):
        with self.assertRaises(ValueError):
            EntryPlan(MIN_CASH, "1", self.config())
        with self.assertRaises(ValueError):
            EntryPlan(MIN_CASH, MIN_PRICE, self.config("1"))

    def test_zero_sale_price_requires_explicit_writeoff_and_never_rounds_to_one(self):
        entry = EntryPlan("1", "1", self.config("0", "1"))
        for price in ("0", MIN_PRICE):
            with self.subTest(price=price), self.assertRaises(ValueError):
                ExitPlan(entry, price)
        written_off = ExitPlan(entry, None)
        self.assertEqual(written_off.kind, "writeoff")
        self.assertEqual(written_off.fill_price, "0")
        self.assertEqual(written_off.cash_credit, "0")

    def test_maximum_supported_balance_and_quantity_do_not_silently_clamp(self):
        entry = EntryPlan(MAXIMUM, "1", self.config())
        self.assertEqual(entry.quantity, MAXIMUM)
        self.assertEqual(entry.cash_debit, MAXIMUM)
        self.assertEqual(entry.residual_budget, "0")
        self.assertEqual(ExitPlan(entry, "1").cash_credit, MAXIMUM)
        with self.assertRaises(ValueError):
            EntryPlan(MAXIMUM, MIN_PRICE, self.config())
        with self.assertRaises(ValueError):
            EntryPlan(MAXIMUM, MAXIMUM, self.config("0", "1"))
        with self.assertRaises(ValueError):
            ExitPlan(entry, "1.000000000000000001")

    def test_signed_pnl_does_not_enter_unsigned_cash_balances(self):
        entry = EntryPlan("100", "25", self.config())
        loss = ExitPlan(entry, "20")
        self.assertEqual(loss.gross_pnl, "-20")
        self.assertEqual(loss.net_pnl, "-20")
        self.assertEqual(loss.cash_credit, "80")
        with self.assertRaises(ValueError):
            credit_cash("0", loss.net_pnl)

    def test_mark_value_uses_actual_quantity_without_hypothetical_exit_fees(self):
        entry = EntryPlan("100", "10", self.config("100", "25", "50"))
        actual = mark_value(entry, "12.34567890123456789")
        self.assertEqual(ratio(actual), ratio(entry.quantity) * ratio("12.34567890123456789"))
        exited = ExitPlan(entry, "12.34567890123456789")
        self.assertGreater(ratio(actual), ratio(exited.cash_credit))
        self.assertEqual(mark_value(EntryPlan("100", "3", self.config()), "3"),
                         "99.999999999999999999")

    def test_mark_value_requires_representable_positive_decimal_evidence(self):
        entry = EntryPlan(MAXIMUM, "1", self.config())
        for value in (None, "0", "-1", 1.0, "NaN", "1." + "0" * 19,
                      "1.000000000000000001"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                mark_value(entry, value)

    def test_nonzero_cost_round_trip_loss_equals_all_in_cash_flows(self):
        entry = EntryPlan("123.456", "13.37", self.config("100", "25", "50"))
        exited = ExitPlan(entry, "13.37")
        final_cash = credit_cash(debit_cash("123.456", entry.cash_debit), exited.cash_credit)
        self.assertLess(ratio(final_cash), ratio("123.456"))
        self.assertEqual(ratio(final_cash) - ratio("123.456"), ratio(exited.net_pnl))

    def test_fraction_oracle_and_one_more_lot_affordability_over_deterministic_cases(self):
        rng = random.Random(7083901)
        for index in range(120):
            budget = str(rng.randrange(1, 100000)) + "." + str(rng.randrange(1000000)).zfill(6)
            price = str(rng.randrange(1, 10000)) + "." + str(rng.randrange(10**18)).zfill(18)
            fee = str(rng.randrange(0, 9500)) + "." + str(rng.randrange(1000000)).zfill(6)
            spread = str(rng.randrange(0, 3000))
            slippage = str(rng.randrange(0, 3000))
            with self.subTest(index=index):
                entry = EntryPlan(budget, price, self.config(fee, spread, slippage))
                self.assert_fields(entry, entry_oracle(budget, price, fee, spread, slippage))
                notional = ratio(entry.notional)
                charge = ratio(entry.fee)
                self.assertEqual(notional, ratio(entry.quantity) * ratio(entry.fill_price))
                self.assertEqual(ratio(entry.cash_debit) + ratio(entry.residual_budget), ratio(budget))
                ideal_fee = notional * ratio(fee) / 10000
                self.assertGreaterEqual(charge, ideal_fee)
                self.assertLess(charge - ideal_fee, ratio(MIN_CASH))
                extra_notional = (ratio(entry.quantity) + ratio(MIN_PRICE)) * ratio(entry.fill_price)
                extra_debit = extra_notional + ceil_grid(extra_notional * ratio(fee) / 10000, CASH_SCALE)
                self.assertGreater(extra_debit, ratio(budget))
                exited = ExitPlan(entry, price)
                self.assert_fields(exited, exit_oracle(entry, price, fee, spread, slippage))

    def test_policy_and_records_are_float_free_and_defensive(self):
        cfg = self.config("30", "10", "10")
        entry = EntryPlan("100", "123.45", cfg)
        exited = ExitPlan(entry, "130")
        for value in (cfg.policy(), entry.to_dict(), exited.to_dict()):
            self.assert_json_without_floats(value)
            json.dumps(value, allow_nan=False)
        policy = cfg.policy()
        policy["injected"] = True
        self.assertNotIn("injected", cfg.policy())
        copied = entry.to_dict()
        copied["cash_debit"] = "0"
        self.assertNotEqual(entry.cash_debit, "0")
        self.assertNotEqual(entry.to_dict()["cash_debit"], "0")

    def test_plans_and_config_cannot_be_mutated_after_preparation(self):
        cfg = self.config("30")
        entry = EntryPlan("100", "10", cfg)
        exited = ExitPlan(entry, "11")
        for value, field in ((cfg, "fee_bps"), (entry, "cash_debit"),
                             (entry, "quantity"), (exited, "cash_credit")):
            with self.subTest(field=field), self.assertRaises((AttributeError, TypeError)):
                setattr(value, field, "999")

    def test_record_round_trip_recomputes_from_budget_including_retained_residual(self):
        entry = EntryPlan("100", "3", self.config("1.123456", "2", "3"))
        record = entry.to_dict()
        reconstructed = EntryPlan.from_dict(deepcopy(record))
        self.assertEqual(reconstructed, entry)
        self.assertEqual(reconstructed.residual_budget, entry.residual_budget)
        for exited in (ExitPlan(entry, "3.5"), ExitPlan(entry, None)):
            self.assertEqual(ExitPlan.from_dict(deepcopy(exited.to_dict())), exited)

    def test_entry_replay_rejects_tampered_derived_fields_and_unknown_keys(self):
        entry = EntryPlan("100", "3", self.config("30", "10", "10"))
        for name in ("quantity", "fill_price", "notional", "fee", "cash_debit", "residual_budget"):
            record = entry.to_dict()
            record[name] = "99"
            with self.subTest(field=name), self.assertRaises(ValueError):
                EntryPlan.from_dict(record)
        record = entry.to_dict()
        record["extra"] = "unsupported"
        with self.assertRaises(ValueError):
            EntryPlan.from_dict(record)
        record = entry.to_dict()
        del record["cash_debit"]
        with self.assertRaises(ValueError):
            EntryPlan.from_dict(record)

    def test_legacy_or_unknown_policy_evidence_is_never_implicitly_reinterpreted(self):
        entry = EntryPlan("100", "3", self.config())
        exited = ExitPlan(entry, "4")
        for constructor, record in ((EntryPlan.from_dict, entry.to_dict()),
                                    (ExitPlan.from_dict, exited.to_dict())):
            for version in ("usd-reference-percentage-cost-v1", "future-version", None, 2):
                changed = deepcopy(record)
                changed["version"] = version
                with self.subTest(version=version), self.assertRaises(ValueError):
                    constructor(changed)
        changed = exited.to_dict()
        changed["entry"]["version"] = "usd-reference-percentage-cost-v1"
        with self.assertRaises(ValueError):
            ExitPlan.from_dict(changed)

    def test_even_bypassed_frozen_fields_are_revalidated_before_reuse(self):
        cfg = self.config("30")
        object.__setattr__(cfg, "_fee_units", 0)
        with self.assertRaises(ValueError):
            EntryPlan("100", "3", cfg)
        entry = EntryPlan("100", "3", self.config("30"))
        object.__setattr__(entry, "quantity", "1")
        with self.assertRaises(ValueError):
            ExitPlan(entry, "4")
        with self.assertRaises(ValueError):
            mark_value(entry, "4")

    def test_exit_replay_rejects_tampered_accounting_and_type(self):
        entry = EntryPlan("100", "3", self.config("30", "10", "10"))
        exited = ExitPlan(entry, "4")
        for name in ("quantity", "fill_price", "notional", "fee", "cash_credit", "gross_pnl", "net_pnl"):
            record = exited.to_dict()
            record[name] = "99"
            with self.subTest(field=name), self.assertRaises(ValueError):
                ExitPlan.from_dict(record)
        record = exited.to_dict()
        record["kind"] = "writeoff"
        with self.assertRaises(ValueError):
            ExitPlan.from_dict(record)

    def test_only_exact_decimal_strings_are_accepted_at_economic_boundaries(self):
        invalid = (None, True, False, 1, 1.0, Decimal("1"), Fraction(1), "NaN", "Infinity",
                   "-Infinity", "-0", "-1", "+1", "1e0", ".1", "1.", "01", " 1",
                   "1 ", "1_000", "١", "１", "1\n", "1\x00")
        for value in invalid:
            with self.subTest(value=repr(value)):
                for operation in (
                    lambda: EntryPlan(value, "1", self.config()),
                    lambda: EntryPlan("1", value, self.config()),
                    lambda: self.config(value),
                    lambda: debit_cash(value, "0"),
                    lambda: credit_cash("0", value),
                ):
                    with self.assertRaises(ValueError):
                        operation()

    def test_overscale_values_are_rejected_even_when_extra_digits_are_zero(self):
        with self.assertRaises(ValueError):
            EntryPlan("1." + "0" * 37, "1", self.config())
        with self.assertRaises(ValueError):
            EntryPlan("1", "1." + "0" * 19, self.config())
        with self.assertRaises(ValueError):
            self.config("1." + "0" * 7)
        with self.assertRaises(ValueError):
            credit_cash("0", "0." + "0" * 36 + "1")

    def test_price_cash_and_fee_domain_boundaries_are_explicit(self):
        for budget, price in (("0", "1"), ("1", "0"), (MAXIMUM + "0", "1"), ("1", MAXIMUM + "0")):
            with self.subTest(budget=budget, price=price), self.assertRaises(ValueError):
                EntryPlan(budget, price, self.config())
        for fee, spread, slippage in (("10000", "0", "0"), ("10000.000001", "0", "0"),
                                      ("0", "10000", "0"), ("0", "5000", "5000")):
            with self.subTest(fee=fee, spread=spread, slippage=slippage), self.assertRaises(ValueError):
                self.config(fee, spread, slippage)
        entry = EntryPlan("100", "10", self.config("9999.999999"))
        self.assertLessEqual(ratio(entry.cash_debit), 100)
        self.assertGreaterEqual(ratio(ExitPlan(entry, "10").cash_credit), 0)

    def test_canonical_outputs_have_no_exponent_or_negative_zero(self):
        entry = EntryPlan("100.000", "25.000", self.config("0.000000"))
        self.assertEqual(entry.cash_debit, "100")
        self.assertEqual(entry.quantity, "4")
        self.assertEqual(entry.residual_budget, "0")
        self.assertEqual(ExitPlan(entry, "25.000").net_pnl, "0")
        self.assertEqual(debit_cash("1.000", "1.0"), "0")
        self.assertEqual(credit_cash("0.000", "0"), "0")

    def test_cash_transfer_conserves_total_without_aliasing_or_partial_result(self):
        original_source, original_destination = "100.123", "0.000000000000000000000000000000000001"
        source, destination = transfer_cash(original_source, original_destination, "20.12")
        self.assertEqual(source, "80.003")
        self.assertEqual(ratio(source) + ratio(destination), ratio(original_source) + ratio(original_destination))
        self.assertEqual(transfer_cash("1", "2", "0"), ("1", "2"))
        self.assertEqual(transfer_cash("1", "0", "1"), ("0", "1"))
        for values in (("1", "0", "1.000000000000000000000000000000000001"),
                       ("1", MAXIMUM, MIN_CASH), ("0", "0", "-1")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                transfer_cash(*values)

    def test_cash_helpers_enforce_bounds_without_rounding(self):
        self.assertEqual(debit_cash(MAXIMUM, MAXIMUM), "0")
        self.assertEqual(credit_cash(MAXIMUM, "0"), MAXIMUM)
        self.assertEqual(credit_cash("0", MIN_CASH), MIN_CASH)
        with self.assertRaises(ValueError):
            credit_cash(MAXIMUM, MIN_CASH)
        with self.assertRaises(ValueError):
            debit_cash("0", MIN_CASH)
        with self.assertRaises(ValueError):
            debit_cash("1", "1.000000000000000000000000000000000001")

    def test_hostile_decimal_context_cannot_change_plan_or_account_results(self):
        cfg = self.config("30.123456", "10.987654", "20.000001")
        baseline = EntryPlan("12345678901234567890.123456789012345678901234567890123456",
                             "1234.567890123456789012", cfg)
        expected_exit = ExitPlan(baseline, "4321.987654321098765432")
        expected_transfer = transfer_cash("100.123456789012345678901234567890123456", "1", MIN_CASH)
        for precision, rounding in ((1, ROUND_CEILING), (2, ROUND_DOWN), (7, ROUND_CEILING)):
            with self.subTest(precision=precision, rounding=rounding), localcontext() as context:
                context.prec = precision
                context.rounding = rounding
                context.Emax = 9
                context.Emin = -9
                for signal in (Inexact, Rounded, FloatOperation):
                    context.traps[signal] = True
                settings = (context.prec, context.rounding, context.Emin, context.Emax, dict(context.traps))
                actual = EntryPlan(baseline.budget, baseline.reference_price, cfg)
                self.assertEqual(actual, baseline)
                self.assertEqual(ExitPlan(actual, expected_exit.reference_price), expected_exit)
                self.assertEqual(EntryPlan.from_dict(actual.to_dict()), baseline)
                self.assertEqual(transfer_cash("100.123456789012345678901234567890123456", "1", MIN_CASH), expected_transfer)
                self.assertEqual((getcontext().prec, getcontext().rounding, getcontext().Emin,
                                  getcontext().Emax, dict(getcontext().traps)), settings)
