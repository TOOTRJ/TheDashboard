from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capacity import (Deadline, Demand, MINUTE, SECOND, Timing, forecast, max_body_lower_bound,
                      over_limits, quota_can_start, source_limits, transport_can_start)


class CapacityFaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.limits, cls.pins = source_limits()

    def test_source_policy_bounds_and_fixture_identity(self):
        self.assertEqual(len(self.pins), 4)
        self.assertEqual((self.limits.receipt_age_us, self.limits.source_age_us, self.limits.future_us),
                         (5 * SECOND, 30 * SECOND, 2 * SECOND))
        self.assertEqual(self.limits.bodies, (131_072, 65_536, 65_536))
        self.assertEqual(self.limits.supplied_inventory, 4096)

    def test_position_reserve_and_stop_are_independently_accounted(self):
        caps = Demand(16, 100, 100, 100, 1_000_000, 1_000_000, 100)
        reserved_stop = Demand(positions=1, dependency_views=7)
        used = Demand(positions=15, dependency_views=93)
        self.assertEqual(over_limits(used, Demand(positions=1), reserved_stop, caps), ('positions',))
        self.assertEqual(over_limits(used, reserved_stop, Demand(), caps), ())
        self.assertEqual(used, Demand(positions=15, dependency_views=93))

    def test_each_independent_dimension_refuses_with_all_other_axes_free(self):
        caps = Demand(16, 17, 18, 19, 20, 21, 22)
        for axis, cap in vars(caps).items():
            with self.subTest(axis=axis):
                used = Demand(**{axis: cap - 1})
                reserved = Demand(**{axis: 1})
                self.assertEqual(over_limits(used, Demand(), reserved, caps), ())
                self.assertEqual(over_limits(used, Demand(**{axis: 1}), reserved, caps), (axis,))

    def test_retention_admission_exact_pre_io_bytes_and_result_count(self):
        edge = self.limits.hot_result_bytes - self.limits.pre_io_bytes
        count = self.limits.packet_results
        self.assertTrue(transport_can_start(Demand(hot_result_bytes=edge, packet_results=count-1), self.limits))
        self.assertFalse(transport_can_start(Demand(hot_result_bytes=edge+1), self.limits))
        self.assertFalse(transport_can_start(Demand(packet_results=count), self.limits))

    def test_maximum_body_lower_bound_proves_refusal_by_thirteenth_start(self):
        charge = max_body_lower_bound(self.limits)
        self.assertEqual(charge, 611_676)
        self.assertGreater(charge * 12, self.limits.hot_result_bytes - self.limits.pre_io_bytes)
        report = forecast(915, 120, 32, self.limits)
        self.assertEqual(report['max_admitted_maximum_body_packets_without_eviction'], 12)
        self.assertEqual(report['uniform_hot_charge_ceiling_for_last_attempt'], 8030)

    def test_915_minute_120s_fence_already_over_inventory_before_control_reserve(self):
        report = forecast(915, 120, 32, self.limits)
        self.assertEqual(report['minimum_source_positions'], 3660)
        self.assertEqual(report['prepared_allocated_ids'], 10_065)
        self.assertEqual(report['price_requests'], 915)
        self.assertEqual(report['rpc_requests'], 1830)
        self.assertEqual(report['illustrative_fence_positions'], 458)
        self.assertEqual(report['supplied_inventory_margin'], -54)
        self.assertEqual(forecast(945, 180, 32, self.limits)['supplied_inventory_margin'], -31)

    def test_missing_stale_regressing_and_low_quota_refuse_continuation(self):
        start, expiry = 50 * SECOND, 60 * SECOND
        self.assertTrue(quota_can_start(3, start, expiry, self.limits))
        for args in ((2, start, expiry), (3, start, expiry+1), (True, start, expiry),
                     (3, None, expiry), (3, start, start-1), (None, start, expiry)):
            with self.subTest(args=args):
                self.assertFalse(quota_can_start(*args, self.limits))

    def test_each_expiry_independently_refuses_ordinary_at_equality(self):
        limit = Deadline(80, 80, 90, 100, 10, 10)
        self.assertTrue(limit.ordinary_can_start(70, 9))
        self.assertFalse(limit.ordinary_can_start(70, 10))
        generous = Deadline(101, 101, 101, 101, 10, 10)
        for name, edge in (('ordinary_writer_us', 80), ('fence_us', 80),
                           ('stop_writer_us', 90), ('reader_us', 100)):
            with self.subTest(name=name):
                self.assertFalse(replace(generous, **{name: edge}).ordinary_can_start(70, 10))
        self.assertEqual(generous.headroom(80), {'writer':21, 'fence':21, 'stop_writer':11, 'reader':1})

    def test_original_lookup_identity_and_known_guard_do_not_replace_visibility(self):
        edge = 21 * MINUTE
        good = Timing('original', 20, edge-4*SECOND, edge-3*SECOND, edge-2*SECOND, edge-2*SECOND, edge-6*SECOND,
                      edge-2*SECOND, edge-SECOND, edge, 'original')
        self.assertEqual(good.classify(self.limits), 'eligible_fixture')
        for change, expected in (({'visible_us': None}, 'original_readback_required'),
                                 ({'readback_id': 'replacement'}, 'original_readback_required'),
                                 ({'visible_us': edge + 1}, 'minute_missed'),
                                 ({'visible_us': edge - 2*SECOND}, 'clock_order')):
            with self.subTest(change=change):
                self.assertEqual(replace(good, **change).classify(self.limits), expected)

    def test_guard_and_visibility_use_separate_receipt_and_source_edges(self):
        start = 20 * MINUTE
        good = Timing('original', 20, start, start+SECOND, start+2*SECOND, start+2*SECOND, start-24*SECOND,
                      start+2*SECOND, start+6*SECOND-1, start+6*SECOND-1, 'original')
        self.assertEqual(good.classify(self.limits), 'eligible_fixture')
        self.assertEqual(replace(good, recognized_commit_us=start+6*SECOND).classify(self.limits),
                         'receipt_age_at_guard')
        self.assertEqual(replace(good, visible_us=start+6*SECOND).classify(self.limits),
                         'receipt_age_at_visibility')
        self.assertEqual(replace(good, estimated_source_us=start-24*SECOND-2).classify(self.limits), 'source_age')
        future_boundary = good.process_lower_us + self.limits.future_us
        self.assertEqual(replace(good, estimated_source_us=future_boundary).classify(self.limits), 'eligible_fixture')
        self.assertEqual(replace(good, estimated_source_us=future_boundary+1).classify(self.limits), 'source_age')

    def test_native_acceptance_and_visible_readback_use_different_minute_edges(self):
        start = 20 * MINUTE
        immediate = Timing('original', 20, start, start, start, start, start,
                           start, start, start, 'original')
        self.assertEqual(immediate.classify(self.limits), 'minute_missed')
        self.assertEqual(replace(immediate, visible_us=start + 1).classify(self.limits),
                         'eligible_fixture')
        earlier = Timing('original', 20, start-3*SECOND, start-2*SECOND, start-SECOND,
                         start-SECOND, start-2*SECOND, start-1, start, start+1, 'original')
        self.assertEqual(earlier.classify(self.limits), 'minute_missed')

    def test_reserved_stop_and_readback_survive_ordinary_writer_and_fence_expiry(self):
        deadlines = Deadline(80, 80, 101, 111, 10, 10)
        self.assertFalse(deadlines.ordinary_can_start(85, 1))
        self.assertTrue(deadlines.stop_can_start(90))
        self.assertFalse(deadlines.stop_can_start(91))

    def test_late_collection_cannot_hide_behind_early_first_receipt(self):
        start = 20 * MINUTE
        at_limit = Timing('original', 20, start, start+SECOND, start+5*SECOND, start+5*SECOND, start,
                          start+5*SECOND, start+5*SECOND, start+5*SECOND, 'original')
        self.assertEqual(at_limit.classify(self.limits), 'acquisition_deadline')
        self.assertEqual(replace(at_limit, collection_finished_us=start+5*SECOND-1).classify(self.limits),
                         'eligible_fixture')

    def test_invalid_scalar_or_empty_forecast_bound_is_refused(self):
        for make in (lambda: Demand(positions=True), lambda: Demand(allocated_ids=-1),
                     lambda: forecast(915, 0, 32, self.limits), lambda: Deadline(100, 100, 100, 100, 0, 1)):
            with self.assertRaises(ValueError):
                make()


if __name__ == '__main__':
    unittest.main(verbosity=2)
