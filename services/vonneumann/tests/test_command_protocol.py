"""Pure command identity, decimal and immutable-snapshot contract tests."""

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
import json
import unittest

from vonneumann.db.command_protocol import (
    CommandValidationError, MAX_BIGINT, PreparedCommand,
    bounded_integer, canonical_uuid, decimal_amount,
)


OWNER = "10000000-0000-0000-0000-000000000001"
RUN = "20000000-0000-0000-0000-000000000001"
WORKER = "30000000-0000-0000-0000-000000000001"
COMMAND = "40000000-0000-0000-0000-000000000001"
ACCOUNT = "50000000-0000-0000-0000-000000000001"
POSITION = "60000000-0000-0000-0000-000000000001"


def creation(**kwargs):
    return PreparedCommand.create(OWNER, RUN, WORKER, kwargs.pop("config", {}),
                                  kwargs.pop("initial_cash", "100"), command_id=COMMAND, **kwargs)


def batch(operations=None, **kwargs):
    return PreparedCommand.batch(OWNER, RUN, WORKER, kwargs.pop("fence", 1),
                                 kwargs.pop("expected_revision", 1),
                                 operations if operations is not None else [{"kind": "lifecycle", "status": "running"}],
                                 command_id=COMMAND, **kwargs)


class CommandProtocolTests(unittest.TestCase):
    def test_creation_uses_actual_rpc_parameters_and_expected_journal_envelope(self):
        command = creation(config={"strategy": "ema", "threshold": "0.02"}, initial_cash="100.00")
        self.assertEqual(command.rpc_name, "create_run")
        self.assertEqual(command.rpc_args, {"owner_id": OWNER, "run": RUN, "worker": WORKER,
            "command_id": COMMAND, "configuration": {"strategy": "ema", "threshold": "0.02"},
            "initial_cash": "100.00", "lease_seconds": 30})
        self.assertEqual(command.expected_request, {"kind": "create", "owner_id": OWNER,
            "run_id": RUN, "worker": WORKER, "command_id": COMMAND,
            "config": {"strategy": "ema", "threshold": "0.02"}, "initial_cash": "100.00", "lease_seconds": 30})
        self.assertEqual(command.expected_result_revision, 1)
        self.assertIsNone(command.fence)
        self.assertIsNone(command.expected_revision)

    def test_batch_and_interruption_bind_distinct_rpc_shapes(self):
        command = batch(fence=7, expected_revision=9)
        self.assertEqual(command.rpc_name, "commit_command")
        self.assertEqual(command.rpc_args, {"owner_id": OWNER, "run": RUN, "worker": WORKER,
            "command_id": COMMAND, "token": 7, "expected_revision": 9,
            "payload": {"version": 1, "operations": [{"kind": "lifecycle", "status": "running"}]}})
        self.assertEqual(command.expected_result_revision, 10)
        interrupted = PreparedCommand.interrupt(OWNER, RUN, 9, command_id=COMMAND)
        self.assertEqual(interrupted.rpc_name, "interrupt_expired")
        self.assertEqual(interrupted.rpc_args, {"owner_id": OWNER, "run": RUN,
            "expected_revision": 9, "command_id": COMMAND})
        self.assertEqual(interrupted.expected_result_revision, 10)
        self.assertIsNone(interrupted.worker_id)
        self.assertIsNone(interrupted.fence)

    def test_snapshots_survive_mutation_of_inputs_and_returned_copies(self):
        config = {"nested": {"choices": [1, "0.25", True, None]}}
        command = creation(config=config)
        original = command.request
        config["nested"]["choices"].append("changed")
        command.rpc_args["configuration"]["nested"]["choices"].clear()
        command.expected_request["config"].clear()
        self.assertEqual(command.request, original)
        self.assertEqual(command.expected_request["config"]["nested"]["choices"], [1, "0.25", True, None])
        with self.assertRaises(FrozenInstanceError):
            command.command_id = ACCOUNT
        with self.assertRaises(FrozenInstanceError):
            command.request = b"{}"

    def test_batch_snapshot_retains_operation_order_and_nested_parent_ids(self):
        operations = [{"kind": "birth", "id": ACCOUNT, "cash": "1", "parent_ids": [POSITION]},
                      {"kind": "lifecycle", "status": "running"}]
        command = batch(operations)
        operations[0]["parent_ids"].clear()
        operations.reverse()
        self.assertEqual(command.rpc_args["payload"]["operations"][0]["parent_ids"], [POSITION])
        reverse = batch(list(reversed(command.rpc_args["payload"]["operations"])))
        self.assertNotEqual(command.request, reverse.request)

    def test_object_order_is_stable_but_decimal_string_scale_remains_identity(self):
        one = creation(config={"a": 1, "b": [False, None]})
        two = creation(config={"b": [False, None], "a": 1})
        self.assertEqual(one.request, two.request)
        self.assertNotEqual(creation(initial_cash="1").request, creation(initial_cash="1.0").request)

    def test_generated_command_identity_is_allocated_once(self):
        first = PreparedCommand.create(OWNER, RUN, WORKER, {}, "1")
        self.assertEqual(canonical_uuid(first.command_id), first.command_id)
        self.assertEqual(first.rpc_args["command_id"], first.expected_request["command_id"])
        second = PreparedCommand.create(OWNER, RUN, WORKER, {}, "1")
        self.assertNotEqual(first.command_id, second.command_id)

    def test_noncanonical_or_nonstring_identities_are_rejected(self):
        canonical = "abcdefab-0000-0000-0000-000000000001"
        self.assertEqual(canonical_uuid(canonical), canonical)
        for value in (canonical.upper(), canonical.replace("-", ""), "{" + canonical + "}",
                      " " + canonical, "", None, 1, True):
            with self.subTest(value=value), self.assertRaises(CommandValidationError):
                canonical_uuid(value)
        with self.assertRaises(CommandValidationError):
            PreparedCommand.create(OWNER, RUN, WORKER, {}, "1", command_id="")

    def test_boolean_and_out_of_range_integer_metadata_are_rejected(self):
        for value in (True, False, 0, -1, "1", 1.0, MAX_BIGINT + 1, None):
            with self.subTest(value=value), self.assertRaises(CommandValidationError):
                bounded_integer(value)
        self.assertEqual(bounded_integer(MAX_BIGINT), MAX_BIGINT)
        for value in (0, 121, None, True):
            with self.subTest(lease=value), self.assertRaises(CommandValidationError):
                creation(lease_seconds=value)
        with self.assertRaises(CommandValidationError):
            batch(expected_revision=MAX_BIGINT)
        self.assertEqual(batch(expected_revision=MAX_BIGINT - 1).expected_result_revision, MAX_BIGINT)

    def test_exact_decimal_limits_work_under_small_decimal_context(self):
        maximum = "1" + "0" * 36
        tiny = "0." + "0" * 35 + "1"
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(decimal_amount(maximum), maximum)
            self.assertEqual(decimal_amount(tiny, positive=True), tiny)
            self.assertEqual(decimal_amount("123456789.987654321"), "123456789.987654321")
        for value in (100.0, 100, Decimal("100"), True, None, "NaN", "Infinity", "-0", "+1",
                      "01", "1e0", "1.", ".1", " 1", "1\n", "0." + "0" * 36 + "1", maximum + "0"):
            with self.subTest(value=value), self.assertRaises(CommandValidationError):
                decimal_amount(value)
        with self.assertRaises(CommandValidationError):
            decimal_amount("0.000", positive=True)
        self.assertEqual(decimal_amount("0.000"), "0.000")

    def test_generic_config_rejects_lossy_and_unsupported_values(self):
        for value in (1.0, float("nan"), float("inf"), Decimal("1.25"), {1: "value"},
                      (1, 2), {1, 2}, b"value", "bad\x00value", "\ud800"):
            with self.subTest(type=type(value).__name__), self.assertRaises(CommandValidationError):
                creation(config={"value": value})
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(CommandValidationError):
            creation(config={"value": cycle})
        deep = {}
        for _ in range(65):
            deep = {"nested": deep}
        with self.assertRaises(CommandValidationError):
            creation(config=deep)

    def test_jsonb_size_limit_counts_utf8_and_postgres_spacing(self):
        exact = {"x": "a" * (65536 - len('{"x": ""}'))}
        creation(config=exact)
        with self.assertRaises(CommandValidationError):
            creation(config={"x": exact["x"] + "a"})
        with self.assertRaises(CommandValidationError):
            creation(config={"x": "é" * 32764})
        accepted = creation(config={"é": ["😀", "line\nbreak", 10**100]})
        self.assertEqual(accepted.expected_request["config"]["é"][2], 10**100)

    def test_typed_economic_operations_and_zero_proceeds_are_supported(self):
        operations = [
            {"kind": "birth", "id": ACCOUNT, "cash": "100.125", "parent_ids": []},
            {"kind": "lifecycle", "status": "running"},
            {"kind": "open", "id": POSITION, "account_id": ACCOUNT, "asset": "SOL/USDC",
             "quantity": "0.000001", "notional": "20.25", "fee": "0.05"},
            {"kind": "close", "id": POSITION, "proceeds": "0", "fee": "0"},
            {"kind": "retire", "id": ACCOUNT},
            {"kind": "lifecycle", "status": "stopped"},
        ]
        self.assertEqual(batch(operations).rpc_args["payload"]["operations"], operations)

    def test_invalid_operation_shapes_and_state_independent_constraints_reject(self):
        birth = {"kind": "birth", "id": ACCOUNT, "cash": "1", "parent_ids": []}
        opened = {"kind": "open", "id": POSITION, "account_id": ACCOUNT, "asset": "SOL",
                  "quantity": "1", "notional": "1", "fee": "0"}
        invalid = [None, [], {}, {"kind": "unknown"}, {"kind": "retire", "id": ACCOUNT, "extra": True},
                   {"kind": "retire"}, {"kind": "lifecycle", "status": "starting"},
                   {**birth, "cash": 1.0}, {**birth, "parent_ids": [ACCOUNT]},
                   {**birth, "parent_ids": [POSITION, POSITION]}, {**birth, "parent_ids": [RUN, POSITION, OWNER]},
                   {**opened, "quantity": "0"}, {**opened, "asset": ""}, {**opened, "asset": "a" * 65},
                   {"kind": "close", "id": POSITION, "proceeds": "0", "fee": "0.01"}]
        for operation in invalid:
            with self.subTest(operation=operation), self.assertRaises(CommandValidationError):
                batch([operation])
        with self.assertRaises(CommandValidationError):
            batch([])
        batch([{"kind": "lifecycle", "status": "paused"}] * 256)
        with self.assertRaises(CommandValidationError):
            batch([{"kind": "lifecycle", "status": "paused"}] * 257)

    def test_direct_constructor_cannot_detach_metadata_from_request(self):
        command = batch()
        for changes in ({"owner_id": ACCOUNT}, {"worker_id": ACCOUNT}, {"command_id": ACCOUNT},
                        {"fence": 2}, {"expected_revision": 2}, {"kind": "interrupt"}):
            with self.subTest(changes=changes), self.assertRaises(CommandValidationError):
                replace(command, **changes)
        with self.assertRaises(CommandValidationError):
            replace(creation(), fence=1)
        with self.assertRaises(CommandValidationError):
            replace(PreparedCommand.interrupt(OWNER, RUN, 1, command_id=COMMAND), worker_id=WORKER)

    def test_direct_request_requires_canonical_bytes_without_duplicate_keys_or_float(self):
        command = batch()
        for source in (bytearray(command.request), b"{}", b" " + command.request,
                       command.request.replace(b'"version":1', b'"version":1.0'),
                       command.request.replace(b'"version":1', b'"version":true'),
                       command.request.replace(b'"version":1', b'"version":1,"version":1')):
            with self.subTest(source_type=type(source).__name__), self.assertRaises(CommandValidationError):
                replace(command, request=source)
        self.assertEqual(json.loads(command.request), command.expected_request)


if __name__ == "__main__":
    unittest.main()
