"""Explicit decision clocks and identities without ambient resource access."""

from contextlib import ExitStack
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone, tzinfo
from decimal import Decimal
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import deny_network
from vonneumann.core.decision_inputs import (
    DecisionInputError, DecisionInputs, MAX_ALLOCATIONS, MAX_GENERATION, MAX_NAME_BYTES,
)


EVENT_AT = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
WALL_AT = datetime(2026, 10, 1, 6, 7, 8, tzinfo=timezone.utc)
IDS = tuple(str(UUID(int=index)) for index in range(1, 5))


class DecisionInputsTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(deny_network())

    def inputs(self, **overrides):
        values = dict(event_at=EVENT_AT, wall_at=WALL_AT, monotonic_at=123.5,
                      ids=IDS, names=((0, "Swift-Falcon-G0"), (1, "Calm-Owl-G1")))
        values.update(overrides)
        return DecisionInputs(**values)

    def test_fixed_clocks_and_allocations_use_no_ambient_time_randomness_or_uuid(self):
        for target in ("time.time", "time.monotonic", "uuid.uuid4", "random.choice",
                       "random.getrandbits"):
            self.stack.enter_context(patch(target, side_effect=AssertionError("ambient source used")))
        inputs = self.inputs()
        cursor = inputs.new_cursor()
        for _ in range(3):
            self.assertIs(cursor.event_time(), EVENT_AT)
            self.assertIs(cursor.wall_time(), WALL_AT)
            self.assertEqual(cursor.monotonic_time(), 123.5)
        self.assertEqual(tuple(cursor.next_id() for _ in IDS), IDS)
        self.assertEqual(cursor.probe_name(0), "Swift-Falcon-G0")
        self.assertEqual(cursor.probe_name(1), "Calm-Owl-G1")
        with self.assertRaises(DecisionInputError):
            cursor.next_id()
        with self.assertRaises(DecisionInputError):
            cursor.probe_name(2)

    def test_cursors_are_independently_repeatable_and_budgets_are_separate(self):
        inputs = self.inputs()
        first, second = inputs.new_cursor(), inputs.new_cursor()
        self.assertIsNot(first, second)
        self.assertEqual(first.next_id(), IDS[0])
        self.assertEqual(first.next_id(), IDS[1])
        self.assertEqual(second.probe_name(0), "Swift-Falcon-G0")
        self.assertEqual(second.next_id(), IDS[0])
        self.assertEqual(first.probe_name(0), "Swift-Falcon-G0")
        self.assertEqual(second.next_id(), IDS[1])
        self.assertEqual(tuple(first.next_id() for _ in range(2)), IDS[2:])
        fresh = inputs.new_cursor()
        self.assertEqual(tuple(fresh.next_id() for _ in IDS), IDS)
        self.assertEqual(inputs.ids, IDS)
        self.assertEqual(inputs.names, ((0, "Swift-Falcon-G0"), (1, "Calm-Owl-G1")))

    def test_generation_mismatch_and_invalid_request_do_not_consume_names(self):
        cursor = self.inputs().new_cursor()
        for value in (1, -1, MAX_GENERATION + 1, True, 0.0, "0", None):
            with self.subTest(generation=value), self.assertRaises(DecisionInputError):
                cursor.probe_name(value)
        self.assertEqual(cursor.probe_name(0), "Swift-Falcon-G0")
        with self.assertRaises(DecisionInputError):
            cursor.probe_name(0)
        self.assertEqual(cursor.probe_name(1), "Calm-Owl-G1")
        for _ in range(2):
            with self.assertRaises(DecisionInputError):
                cursor.probe_name(1)

    def test_empty_budgets_fail_closed_but_clocks_remain_available(self):
        cursor = self.inputs(ids=(), names=()).new_cursor()
        for _ in range(2):
            with self.assertRaises(DecisionInputError):
                cursor.next_id()
            with self.assertRaises(DecisionInputError):
                cursor.probe_name(0)
        self.assertEqual(cursor.event_time(), EVENT_AT)
        self.assertEqual(cursor.wall_time(), WALL_AT)
        self.assertEqual(cursor.monotonic_time(), 123.5)

    def test_record_is_frozen_and_contains_only_immutable_allocations(self):
        inputs = self.inputs()
        for field, value in (("event_at", WALL_AT), ("monotonic_at", 1.0),
                             ("ids", ()), ("names", ())):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(inputs, field, value)
        with self.assertRaises((AttributeError, TypeError)):
            inputs.extra = "unexpected"
        self.assertFalse(hasattr(inputs, "__dict__"))
        self.assertFalse(hasattr(inputs.new_cursor(), "__dict__"))

    def test_clocks_require_exact_utc_builtin_datetimes_without_custom_tz_hooks(self):
        class CustomDatetime(datetime):
            pass

        class CustomTimezone(tzinfo):
            def utcoffset(self, dt):
                raise AssertionError("custom timezone executed")

        bad = (None, "2026-10-01", EVENT_AT.timestamp(), datetime(2026, 1, 1),
               EVENT_AT.replace(tzinfo=timezone(timedelta(hours=1))),
               EVENT_AT.replace(tzinfo=CustomTimezone()),
               CustomDatetime(2026, 1, 1, tzinfo=timezone.utc))
        for field in ("event_at", "wall_at"):
            for value in bad:
                with self.subTest(field=field, type=type(value)), self.assertRaises(DecisionInputError):
                    self.inputs(**{field: value})
        named_utc = EVENT_AT.replace(tzinfo=timezone(timedelta(0), "Explicit-UTC"))
        self.assertEqual(self.inputs(event_at=named_utc).new_cursor().event_time(), EVENT_AT)

    def test_monotonic_clock_rejects_nonfinite_negative_and_coerced_values(self):
        class FloatSubclass(float):
            pass

        for value in (None, True, 0, "1.0", Decimal("1"), float("nan"), float("inf"),
                      -float("inf"), -0.001, FloatSubclass(1.0)):
            with self.subTest(value=value), self.assertRaises(DecisionInputError):
                self.inputs(monotonic_at=value)
        self.assertEqual(self.inputs(monotonic_at=0.0).new_cursor().monotonic_time(), 0.0)

    def test_all_identifiers_validate_before_any_cursor_can_be_created(self):
        upper = "abcdefab-0000-0000-0000-000000000001".upper()
        malformed = (None, True, UUID(IDS[0]), "", "not-a-uuid", IDS[0].replace("-", ""),
                     "{" + IDS[0] + "}", upper, "x" * 36)
        for value in malformed:
            with self.subTest(value=value), self.assertRaises(DecisionInputError):
                self.inputs(ids=(IDS[0], value))
        with self.assertRaises(DecisionInputError):
            self.inputs(ids=(IDS[0], IDS[1], IDS[0]))
        for value in (list(IDS), iter(IDS), IDS[0], {IDS[0]}, None):
            with self.subTest(type=type(value)), self.assertRaises(DecisionInputError):
                self.inputs(ids=value)

    def test_names_validate_complete_shape_types_text_and_generation_upfront(self):
        malformed = (None, [0, "Name"], (0,), (0, "Name", "extra"), (True, "Name"),
                     (-1, "Name"), (MAX_GENERATION + 1, "Name"), (0.0, "Name"),
                     (0, None), (0, ""), (0, " "), (0, " Name"), (0, "Name "),
                     (0, "Name\n"), (0, "Name\x00"), (0, "\ud800"))
        for value in malformed:
            with self.subTest(type=type(value)), self.assertRaises(DecisionInputError):
                self.inputs(names=((0, "First"), value))
        for value in ([(0, "Name")], iter(((0, "Name"),)), {0: "Name"}, None):
            with self.subTest(type=type(value)), self.assertRaises(DecisionInputError):
                self.inputs(names=value)

    def test_allocation_count_and_name_byte_bounds_are_explicit(self):
        ids = tuple(str(UUID(int=index)) for index in range(MAX_ALLOCATIONS))
        names = ((MAX_GENERATION, "x" * MAX_NAME_BYTES),) * MAX_ALLOCATIONS
        inputs = self.inputs(ids=ids, names=names)
        self.assertEqual(inputs.new_cursor().probe_name(MAX_GENERATION), "x" * MAX_NAME_BYTES)
        with self.assertRaises(DecisionInputError):
            self.inputs(ids=ids + (str(UUID(int=MAX_ALLOCATIONS)),))
        with self.assertRaises(DecisionInputError):
            self.inputs(names=names + ((0, "Overflow"),))
        for name in ("x" * (MAX_NAME_BYTES + 1), "é" * (MAX_NAME_BYTES // 2 + 1)):
            with self.subTest(length=len(name)), self.assertRaises(DecisionInputError):
                self.inputs(names=((0, name),))
        self.assertEqual(self.inputs(names=((0, "é" * (MAX_NAME_BYTES // 2)),)).names[0][1],
                         "é" * (MAX_NAME_BYTES // 2))


if __name__ == "__main__":
    unittest.main()
