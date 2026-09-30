"""Offline hand-calculated portfolio metric and as-of sampling regressions."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import math
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core import equity_metrics as module
    from vonneumann.core.equity_metrics import (
        EQUITY_METRICS_POLICY, EquityHistory, MAX_RETURN_WINDOW,
        calculate_sharpe, return_statistics,
    )
    from vonneumann.core.market_validation import MarketValueError


class EquityMetricTests(OfflineTestMixin, unittest.TestCase):
    def sample(self, values, *, capacity=MAX_RETURN_WINDOW):
        history = EquityHistory(capacity=capacity)
        for i, equity in enumerate(values):
            history = history.observe(equity, i * 60, i * 60 + 30)
        return history

    def test_hand_calculated_sample_deviation_and_unannualized_sharpe(self):
        result = return_statistics([0.01, 0.03])
        self.assertEqual(result["status"], "available")
        self.assertAlmostEqual(result["mean_excess_return"], 0.02)
        self.assertAlmostEqual(result["sample_standard_deviation"], math.sqrt(0.0002))
        self.assertAlmostEqual(result["sharpe_ratio"], math.sqrt(2))
        self.assertEqual(calculate_sharpe([0.01, 0.03]), result["sharpe_ratio"])

    def test_zero_or_constant_nonzero_returns_never_get_epsilon_sharpe(self):
        for values in ([0, 0, 0], [0.01, 0.01, 0.01], [-0.02, -0.02]):
            with self.subTest(values=values):
                result = return_statistics(values)
                self.assertEqual(result["status"], "zero_variance")
                self.assertEqual(result["sample_standard_deviation"], 0)
                self.assertIsNone(result["sharpe_ratio"])

    def test_empty_and_single_returns_are_insufficient_not_fabricated_zero(self):
        for values in ([], [0.01]):
            result = return_statistics(values)
            self.assertEqual(result["status"], "insufficient_samples")
            self.assertIsNone(result["sharpe_ratio"])
            self.assertEqual(result["return_count"], len(values))

    def test_benchmark_is_per_period_in_both_mean_and_deviation(self):
        result = return_statistics([0.01, 0.03], risk_free_per_period=0.01)
        self.assertAlmostEqual(result["sharpe_ratio"], 1 / math.sqrt(2))
        self.assertAlmostEqual(result["mean_excess_return"], 0.01)
        self.assertAlmostEqual(result["sample_standard_deviation"], math.sqrt(0.0002))

    def test_stable_moments_handle_large_and_tiny_representable_returns(self):
        large = return_statistics([1e308, 0])
        self.assertEqual(large["status"], "available")
        self.assertAlmostEqual(large["sharpe_ratio"], 1 / math.sqrt(2))
        tiny = return_statistics([1e-300, 2e-300])
        self.assertEqual(tiny["status"], "available")
        self.assertAlmostEqual(tiny["sharpe_ratio"], 3 / math.sqrt(2))

    def test_nearly_constant_finite_ratio_is_not_given_an_arbitrary_epsilon_or_cap(self):
        result = return_statistics([1.0, math.nextafter(1.0, 2.0)])
        self.assertEqual(result["status"], "available")
        self.assertTrue(math.isfinite(result["sharpe_ratio"]))
        self.assertGreater(result["sharpe_ratio"], 1e15)

    def test_derived_nonfinite_excess_return_is_explicit_invalid_arithmetic(self):
        result = return_statistics([-1e308, 1e308], risk_free_per_period=-1e308)
        self.assertEqual(result["status"], "invalid_arithmetic")
        self.assertIsNone(result["sharpe_ratio"])
        json.dumps(result, allow_nan=False)

    def test_statistics_reject_invalid_values_and_benchmarks(self):
        invalid = (True, False, None, "private-value", float("nan"), float("inf"), -float("inf"))
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(MarketValueError):
                    return_statistics([0.01, value])
                with self.assertRaises(MarketValueError):
                    return_statistics([0.01, 0.02], risk_free_per_period=value)

    def test_exact_endpoints_produce_hand_calculated_portfolio_returns(self):
        history = self.sample([100, 110, 99])
        self.assertEqual(history.returns, (0.1, -0.1))
        result = history.diagnostic()
        self.assertEqual(result["sharpe_ratio"], 0)
        self.assertEqual(result["return_count"], 2)
        self.assertEqual(result["window_start_endpoint"], 0)
        self.assertEqual(result["last_sample_endpoint"], 120)
        self.assertFalse(result["annualized"])

    def test_first_nonendpoint_observation_does_not_invent_historical_baseline(self):
        history = EquityHistory().observe(100, 10, 40)
        self.assertIsNone(history.last_sample)
        self.assertEqual(history.returns, ())
        history = history.observe(110, 60, 90)
        self.assertEqual(history.last_sample.equity, 110)
        self.assertEqual(history.returns, ())
        self.assertEqual(history.missing_periods, 0)
        self.assertEqual(history.window_start_endpoint, 60)

    def test_crossed_endpoint_uses_previous_frozen_observation_not_future_equity(self):
        original = self.sample([100])
        before = original.observe(110, 50, 80)
        after = before.observe(999, 65, 95)
        self.assertEqual(after.last_sample.endpoint, 60)
        self.assertEqual(after.last_sample.equity, 110)
        self.assertEqual(after.last_sample.observed_at, 50)
        self.assertEqual(after.returns, (0.1,))
        self.assertEqual(after.last_observation.equity, 999)
        self.assertEqual(after.diagnostic()["last_sample_observation_age_seconds"], 10)
        self.assertEqual(original.last_sample.equity, 100)
        self.assertEqual(before.last_observation.equity, 110)

    def test_exact_current_endpoint_wins_over_still_valid_previous_observation(self):
        history = self.sample([100]).observe(110, 50, 80).observe(120, 60, 90)
        self.assertEqual(history.last_sample.equity, 120)
        self.assertEqual(history.last_sample.observed_at, 60)
        self.assertEqual(history.returns, (0.2,))

    def test_one_observation_call_can_cover_two_consecutive_endpoints_without_interpolation(self):
        history = self.sample([100]).observe(110, 59, 89).observe(121, 120, 150)
        self.assertEqual(history.returns, (0.1, 0.1))
        self.assertEqual(history.missing_periods, 0)
        self.assertEqual(history.last_sample.endpoint, 120)

    def test_expiration_is_inclusive_but_a_later_expiration_does_not_relax_carry_cap(self):
        valid = self.sample([100]).observe(110, 30, 60).observe(120, 61, 91)
        self.assertEqual(valid.returns, (0.1,))
        expired = self.sample([100]).observe(110, 30, 59.999).observe(120, 61, 91)
        self.assertEqual(expired.returns, ())
        self.assertEqual(expired.missing_periods, 1)
        too_old = self.sample([100]).observe(110, 29.999, 1e9).observe(120, 61, 91)
        self.assertEqual(too_old.returns, ())
        self.assertEqual(too_old.missing_periods, 1)
        self.assertLess(too_old.last_sample.valid_until, 60)

    def test_cash_observation_cannot_create_flat_returns_through_a_long_pause(self):
        history = EquityHistory().observe(100, 0, 1e9).observe(100, 600, 1e9)
        self.assertEqual(history.last_observation.valid_until, 630)
        self.assertEqual(history.returns, ())
        self.assertEqual(history.missing_periods, 9)
        self.assertEqual(history.last_sample.endpoint, 600)
        self.assertEqual(history.window_start_endpoint, 600)

    def test_gap_resets_previous_segment_without_creating_a_long_period_return(self):
        history = self.sample([100, 110]).observe(220, 180, 210)
        self.assertEqual(history.returns, ())
        self.assertEqual(history.missing_periods, 1)
        self.assertEqual(history.window_start_endpoint, 180)
        self.assertEqual(history.diagnostic()["status"], "insufficient_samples")
        history = history.observe(242, 240, 270)
        self.assertEqual(history.returns, (0.1,))

    def test_valid_first_endpoint_then_gap_then_exact_current_establishes_new_baseline(self):
        history = self.sample([100]).observe(110, 59, 89).observe(150, 180, 210)
        self.assertEqual(history.missing_periods, 1)
        self.assertEqual(history.returns, ())
        self.assertEqual(history.last_sample.equity, 150)
        self.assertEqual(history.window_start_endpoint, 180)

    def test_nonendpoint_after_gap_keeps_last_actual_sample_but_no_contiguous_window(self):
        history = self.sample([100]).observe(110, 59, 89).observe(150, 181, 211)
        self.assertEqual(history.missing_periods, 2)
        self.assertEqual(history.last_sample.endpoint, 60)
        self.assertEqual(history.last_sample.observed_at, 59)
        self.assertIsNone(history.window_start_endpoint)
        self.assertEqual(history.returns, ())
        history = history.observe(160, 240, 270)
        self.assertEqual(history.returns, ())
        self.assertEqual(history.window_start_endpoint, 240)

    def test_arbitrarily_long_gap_uses_bounded_work_and_exact_missing_count(self):
        endpoint = 60 * 10**12
        history = self.sample([100]).observe(101, endpoint, endpoint + 30)
        self.assertEqual(history.missing_periods, 10**12 - 1)
        self.assertEqual(history.last_sample.endpoint, endpoint)
        self.assertEqual(history.returns, ())
        self.assertEqual(history.diagnostic()["last_processed_endpoint"], endpoint)

    def test_duplicate_endpoint_does_not_revise_return_but_updates_next_candidate(self):
        history = self.sample([100, 110])
        repeated = history.observe(120, 60, 90)
        self.assertEqual(repeated.returns, (0.1,))
        self.assertEqual(repeated.last_sample.equity, 110)
        self.assertEqual(repeated.last_observation.equity, 120)
        same_minute = repeated.observe(121, 119, 149).observe(999, 121, 151)
        self.assertEqual(same_minute.returns, (0.1, 0.1))
        self.assertEqual(same_minute.last_sample.equity, 121)

    def test_invalid_input_or_backward_time_leaves_original_history_unchanged(self):
        history = self.sample([100, 110])
        before = history.diagnostic()
        cases = [(value, 120, 150) for value in (True, None, -1, float("nan"), float("inf"), "secret")]
        cases += [(100, stamp, 150) for stamp in (True, None, -1, float("nan"), float("inf"), "secret", 59)]
        cases += [(100, 120, stamp) for stamp in (True, None, -1, float("nan"), float("inf"), "secret", 119)]
        for args in cases:
            with self.subTest(types=tuple(type(value).__name__ for value in args)):
                with self.assertRaises(MarketValueError) as caught:
                    history.observe(*args)
                self.assertNotIn("secret", str(caught.exception))
                self.assertEqual(history.diagnostic(), before)

    def test_terminal_loss_is_a_valid_return_but_returns_from_zero_break_segment(self):
        loss = self.sample([100, 0])
        self.assertEqual(loss.returns, (-1,))
        self.assertEqual(loss.invalid_intervals, 0)
        zero = loss.observe(0, 120, 150)
        self.assertEqual(zero.returns, ())
        self.assertEqual(zero.invalid_intervals, 1)
        self.assertEqual(zero.diagnostic()["status"], "invalid_arithmetic")
        funded = zero.observe(100, 180, 210)
        self.assertEqual(funded.returns, ())
        self.assertEqual(funded.invalid_intervals, 2)
        recovered = funded.observe(110, 240, 270)
        self.assertEqual(recovered.returns, (0.1,))
        self.assertEqual(recovered.diagnostic()["status"], "insufficient_samples")

    def test_nonrepresentable_equity_return_resets_safely_and_can_recover(self):
        history = self.sample([math.nextafter(0, 1), 1e308])
        self.assertEqual(history.returns, ())
        self.assertEqual(history.invalid_intervals, 1)
        self.assertEqual(history.diagnostic()["status"], "invalid_arithmetic")
        self.assertEqual(history.last_sample.equity, 1e308)
        history = history.observe(5e307, 120, 150).observe(5e307, 180, 210)
        self.assertEqual(history.returns, (-0.5, 0))
        self.assertAlmostEqual(history.diagnostic()["sharpe_ratio"], -1 / math.sqrt(2))
        json.dumps(history.diagnostic(), allow_nan=False)

    def test_contiguous_window_is_bounded_and_reports_actual_window_origin(self):
        history = self.sample([100, 101, 103, 106, 110, 115], capacity=3)
        self.assertEqual(len(history.returns), 3)
        self.assertEqual(history.returns, ((106 - 103) / 103, (110 - 106) / 106, (115 - 110) / 110))
        self.assertEqual(history.window_start_endpoint, 120)
        self.assertEqual(history.diagnostic()["return_count"], 3)
        self.assertEqual(history.missing_periods, 0)

    def test_histories_observations_samples_and_policy_are_immutable(self):
        history = self.sample([100])
        for target, attribute, value in ((history, "missing_periods", 10),
                                         (history.last_sample, "equity", 0),
                                         (history.last_observation, "equity", 0)):
            with self.assertRaises(FrozenInstanceError):
                setattr(target, attribute, value)
        with self.assertRaises(TypeError):
            EQUITY_METRICS_POLICY["annualized"] = True
        result = history.diagnostic()
        result["status"] = "changed"
        self.assertEqual(history.diagnostic()["status"], "insufficient_samples")

    def test_capacity_bounds_and_policy_have_explicit_units(self):
        for value in (0, 1, MAX_RETURN_WINDOW + 1, True, 3.0, "3"):
            with self.assertRaises(MarketValueError):
                EquityHistory(capacity=value)
        self.assertEqual(EQUITY_METRICS_POLICY["interval_seconds"], 60)
        self.assertEqual(EQUITY_METRICS_POLICY["max_observation_carry_seconds"], 30)
        self.assertEqual(EQUITY_METRICS_POLICY["benchmark_return_per_period"], 0)
        self.assertFalse(EQUITY_METRICS_POLICY["annualized"])
        self.assertEqual(EQUITY_METRICS_POLICY["statistical_significance"], "not_established")
        json.dumps(dict(EQUITY_METRICS_POLICY), allow_nan=False)

    def test_statistics_are_cached_across_reads_and_same_period_observations(self):
        with patch.object(module, "return_statistics", wraps=module.return_statistics) as compute:
            history = self.sample([100, 110, 99])
            count = compute.call_count
            for _ in range(5):
                self.assertEqual(history.diagnostic()["sharpe_ratio"], 0)
            history = history.observe(100, 121, 151)
            self.assertEqual(history.diagnostic()["sharpe_ratio"], 0)
            self.assertEqual(compute.call_count, count)
            history = history.observe(101, 180, 210)
            self.assertEqual(compute.call_count, count + 1)
            self.assertEqual(history.diagnostic()["return_count"], 3)
            history = history.observe(102, 300, 330)
            self.assertEqual(history.diagnostic()["return_count"], 0)
            self.assertEqual(history.diagnostic()["status"], "insufficient_samples")

    def test_position_sizing_changes_equity_returns_without_equal_trade_weighting(self):
        # $10 earns100%=+$10; $990 loses1%=-$9.90. Trade returns' mean49.5%
        # must not replace these portfolio returns or the ending ROI0.01%.
        history = self.sample([1000, 1010, 1000.1])
        self.assertAlmostEqual(history.returns[0], 0.01)
        self.assertAlmostEqual(history.returns[1], -9.9 / 1010)
        self.assertAlmostEqual(history.last_sample.equity / 1000 - 1, 0.0001)
        self.assertNotAlmostEqual(history.diagnostic()["mean_excess_return"], 0.495)

    def test_cash_no_trade_and_constant_growth_paths_have_explicit_zero_variance(self):
        for values in ([100, 100, 100], [100, 200, 400]):
            result = self.sample(values).diagnostic()
            self.assertEqual(result["status"], "zero_variance")
            self.assertIsNone(result["sharpe_ratio"])
            self.assertEqual(result["missing_periods"], 0)
