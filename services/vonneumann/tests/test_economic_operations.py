"""Exact evidence binding between the pure fill planner and command protocol."""

from copy import deepcopy
from decimal import Decimal
import json
import unittest
from uuid import uuid4

from tests.security_support import deny_network
from vonneumann.core.decimal_execution import DecimalExecutionConfig, EntryPlan, ExitPlan
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.economic_operations import close_operation, open_operation, run_configuration


def identity():
    return str(uuid4())


class EconomicOperationsTests(unittest.TestCase):
    def setUp(self):
        guard = deny_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)
        self.owner, self.run, self.worker = identity(), identity(), identity()
        self.position, self.account = identity(), identity()
        self.config = DecimalExecutionConfig("30", "10", "10")
        self.entry = EntryPlan("100", "123.45", self.config)
        self.exit = ExitPlan(self.entry, "130.15")

    def batch(self, operations, *, version=2):
        return PreparedCommand.batch(self.owner, self.run, self.worker, 1, 1,
                                     operations, version=version)

    def assert_no_float(self, value):
        if type(value) is dict:
            self.assertTrue(all(type(key) is str for key in value))
            for item in value.values():
                self.assert_no_float(item)
        elif type(value) is list:
            for item in value:
                self.assert_no_float(item)
        else:
            self.assertIn(type(value), (str, int, bool, type(None)))

    def test_run_configuration_binds_policy_and_preserves_unrelated_configuration(self):
        source = {"strategy": "fixed", "assets": ["SOL/USDC"], "research": {"seed": "123"}}
        before = deepcopy(source)
        result = run_configuration(self.config, source)
        self.assertEqual(source, before)
        self.assertEqual(result["durability_contract_version"], 2)
        self.assertEqual(result["execution"], self.config.policy())
        for key, value in before.items():
            self.assertEqual(result[key], value)
        result["research"]["seed"] = "changed"
        result["assets"].append("ETH/USDC")
        result["execution"]["config"]["fee_bps"] = "0"
        self.assertEqual(source, before)
        self.assertEqual(self.config.fee_bps, "30")
        self.assertEqual(run_configuration(self.config)["execution"], self.config.policy())

    def test_existing_matching_policy_is_idempotent_but_conflicts_are_rejected(self):
        matching = run_configuration(self.config, {"strategy": "fixture"})
        self.assertEqual(run_configuration(self.config, matching), matching)
        for value in (1, "2", True, None):
            with self.subTest(version=value), self.assertRaises(ValueError):
                run_configuration(self.config, {"durability_contract_version": value})
        conflicting = deepcopy(matching)
        conflicting["execution"]["config"]["fee_bps"] = "31"
        with self.assertRaises(ValueError):
            run_configuration(self.config, conflicting)
        conflicting = deepcopy(matching)
        conflicting["execution"]["version"] = "usd-reference-percentage-cost-v1"
        with self.assertRaises(ValueError):
            run_configuration(self.config, conflicting)

    def test_run_configuration_rejects_implicit_float_or_type_coercions(self):
        for value in ([], "{}", 1, True, {"cash": 1.0}, {"cash": Decimal("1")},
                      {1: "non-string key"}, {"assets": ("SOL/USDC",)}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                run_configuration(self.config, value)
        for value in (None, {}, "30", 30.0):
            with self.subTest(execution=value), self.assertRaises(ValueError):
                run_configuration(value)

    def test_open_operation_binds_exact_scalar_fields_to_full_entry_evidence(self):
        operation = open_operation(self.entry, self.position, self.account, "SOL/USDC")
        self.assertEqual(operation, {
            "kind": "open", "id": self.position, "account_id": self.account,
            "asset": "SOL/USDC", "quantity": self.entry.quantity,
            "notional": self.entry.notional, "fee": self.entry.fee,
            "execution": self.entry.to_dict(),
        })
        self.assert_no_float(operation)
        operation["execution"]["config"]["fee_bps"] = "9999"
        operation["execution"]["cash_debit"] = "0"
        operation["quantity"] = "0"
        fresh = open_operation(self.entry, self.position, self.account, "SOL/USDC")
        self.assertEqual(fresh["execution"], self.entry.to_dict())
        self.assertEqual(fresh["quantity"], self.entry.quantity)

    def test_close_operation_sends_gross_proceeds_and_separate_fee_once(self):
        operation = close_operation(self.exit, self.position)
        self.assertEqual(operation, {
            "kind": "close", "id": self.position, "proceeds": self.exit.notional,
            "fee": self.exit.fee, "execution": self.exit.to_dict(),
        })
        self.assertNotEqual(operation["proceeds"], self.exit.cash_credit)
        self.assert_no_float(operation)
        operation["execution"]["entry"]["quantity"] = "0"
        self.assertEqual(close_operation(self.exit, self.position)["execution"]["entry"],
                         self.entry.to_dict())

    def test_writeoff_evidence_is_explicit_and_keeps_original_entry(self):
        written_off = ExitPlan(self.entry, None)
        operation = close_operation(written_off, self.position)
        self.assertEqual(operation["proceeds"], "0")
        self.assertEqual(operation["fee"], "0")
        self.assertEqual(operation["execution"]["kind"], "writeoff")
        self.assertIsNone(operation["execution"]["reference_price"])
        self.assertEqual(operation["execution"]["entry"], self.entry.to_dict())

    def test_builder_identity_and_asset_validation_does_not_guess(self):
        for value in (None, True, "", "not-a-uuid", "AAAAAAAA-0000-4000-8000-000000000001", 1):
            with self.subTest(identity=value):
                with self.assertRaises(ValueError):
                    open_operation(self.entry, value, self.account, "SOL/USDC")
                with self.assertRaises(ValueError):
                    open_operation(self.entry, self.position, value, "SOL/USDC")
                with self.assertRaises(ValueError):
                    close_operation(self.exit, value)
        for asset in (None, True, "", "x" * 65, "SOL\x00/USDC", "\ud800"):
            with self.subTest(asset=asset), self.assertRaises(ValueError):
                open_operation(self.entry, self.position, self.account, asset)

    def test_builders_reject_wrong_types_and_revalidate_frozen_plan_evidence(self):
        for value in (None, {}, self.entry.to_dict(), self.exit, 1.0):
            with self.subTest(entry_type=type(value)), self.assertRaises(ValueError):
                open_operation(value, self.position, self.account, "SOL/USDC")
        for value in (None, {}, self.exit.to_dict(), self.entry, 1.0):
            with self.subTest(exit_type=type(value)), self.assertRaises(ValueError):
                close_operation(value, self.position)
        entry = EntryPlan("100", "3", self.config)
        object.__setattr__(entry, "cash_debit", "0")
        with self.assertRaises(ValueError):
            open_operation(entry, self.position, self.account, "SOL/USDC")
        exited = ExitPlan(self.entry, "130")
        object.__setattr__(exited, "cash_credit", "0")
        with self.assertRaises(ValueError):
            close_operation(exited, self.position)

    def test_version_two_batch_retains_full_evidence_and_detaches_input_objects(self):
        operations = [open_operation(self.entry, self.position, self.account, "SOL/USDC"),
                      close_operation(self.exit, self.position)]
        original = deepcopy(operations)
        command = self.batch(operations)
        saved = command.request
        self.assertEqual(command.expected_request["payload"], {"version": 2, "operations": original})
        operations[0]["execution"]["config"]["fee_bps"] = "0"
        operations[1]["proceeds"] = "0"
        self.assertEqual(command.request, saved)
        self.assertEqual(command.rpc_args["payload"]["operations"], original)
        self.assert_no_float(command.expected_request)
        json.dumps(command.expected_request, allow_nan=False)

    def test_protocol_version_is_explicit_and_cannot_drop_accounting_evidence(self):
        operation = open_operation(self.entry, self.position, self.account, "SOL/USDC")
        with self.assertRaises(ValueError):
            self.batch([operation], version=1)
        stripped = deepcopy(operation)
        del stripped["execution"]
        with self.assertRaises(ValueError):
            self.batch([stripped], version=2)
        # Legacy operation preparation remains explicitly version 1.
        legacy = self.batch([stripped], version=1)
        self.assertEqual(legacy.expected_request["payload"]["version"], 1)

    def test_protocol_rejects_scalar_and_nested_evidence_disagreement(self):
        opened = open_operation(self.entry, self.position, self.account, "SOL/USDC")
        closed = close_operation(self.exit, self.position)
        for source, fields in ((opened, ("quantity", "notional", "fee")),
                               (closed, ("proceeds", "fee"))):
            for field in fields:
                changed = deepcopy(source)
                changed[field] = "999"
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.batch([changed])
        for source, field in ((opened, "cash_debit"), (closed, "cash_credit")):
            changed = deepcopy(source)
            changed["execution"][field] = "0"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.batch([changed])

    def test_creation_command_keeps_bound_policy_and_exact_initial_cash(self):
        source = run_configuration(self.config, {"strategy": "fixture"})
        command = PreparedCommand.create(self.owner, self.run, self.worker, source, "1000")
        source["execution"]["config"]["fee_bps"] = "0"
        self.assertEqual(command.expected_request["config"]["durability_contract_version"], 2)
        self.assertEqual(command.expected_request["config"]["execution"], self.config.policy())
        self.assertEqual(command.rpc_args["initial_cash"], "1000")
