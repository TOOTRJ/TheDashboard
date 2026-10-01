"""Independent real-role acceptance for the isolated version-2 contract.

Integer/Fraction oracles check exact planning against committed PostgreSQL
numeric values; deliberately malformed raw RPCs test the SQL boundary without
the Python validator protecting it. No production connection is constructed.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import json

from tests.postgres.harness import PostgresContractTestCase
from tests.postgres.test_command_adapter import FixtureRpcTransport, identity, literal
from vonneumann.core.decimal_execution import DecimalExecutionConfig, EntryPlan, ExitPlan
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.economic_operations import close_operation, open_operation, run_configuration


TABLES = ("runs", "accounts", "account_parents", "positions", "commands",
          "distributions", "distribution_sources", "account_lineage", "lineage_sources")
NEW_TABLES = ("distributions", "distribution_sources", "account_lineage", "lineage_sources")


def document(value) -> str:
    return literal(json.dumps(value, ensure_ascii=False, allow_nan=False)) + "::jsonb"


def founder(account, cash="100", strategy="cma_es") -> dict:
    return {"kind": "birth", "id": account, "cash": cash, "lineage": {
        "version": 1, "child_id": account, "strategy": strategy, "operation": "founder",
        "source_iteration_id": None, "offspring_index": None, "sources": [], "distribution_id": None,
    }}


def sample(account, distribution, template, *, iteration="cohort:0", index=0, cash="1"):
    result = founder(account, cash)
    result["lineage"].update(operation="distribution_sample", source_iteration_id=iteration,
        offspring_index=index, sources=[{"role": "asset_template", "source_id": template, "ordinal": 0}],
        distribution_id=distribution)
    return result


def distribution(group, sources, *, iteration="cohort:0", previous=None):
    return {"kind": "distribution", "id": group, "stage": "bootstrap" if previous is None else "update",
            "source_iteration_id": iteration, "previous_distribution_id": previous, "source_ids": list(sources)}


def ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


class DecimalLineageContractTests(PostgresContractTestCase):
    def setUp(self):
        self.owner, self.other_owner = identity(), identity()
        self.run, self.worker = identity(), identity()
        self.db.sql(f"INSERT INTO auth.users(id) VALUES ({literal(self.owner)}),({literal(self.other_owner)});")
        self.revision = 0

    def call(self, command):
        result = asyncio.run(FixtureRpcTransport(self.db).rpc(command.rpc_name, command.rpc_args))
        self.revision = result["revision"]
        return result

    def create(self, cash="1000", config=None):
        self.config = config or DecimalExecutionConfig()
        return self.call(PreparedCommand.create(self.owner, self.run, self.worker,
            run_configuration(self.config, {"fixture": "decimal-lineage"}), cash))

    def command(self, operations):
        return PreparedCommand.batch(self.owner, self.run, self.worker, 1, self.revision, operations, version=2)

    def commit(self, operations):
        return self.call(self.command(operations))

    def raw_sql(self, operations, *, version=2, command_id=None):
        args = [literal(self.owner), literal(self.run), literal(self.worker), "1", str(self.revision),
                literal(command_id or identity()), document({"version": version, "operations": operations})]
        return "SELECT vn_durability.commit_command(" + ",".join(args) + ");"

    def reject(self, operations, expected=None, *, version=2):
        before = self.snapshot()
        result = self.db.sql(self.raw_sql(operations, version=version), role="service_role", check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        if expected:
            self.assertIn(expected, result.stderr)
        self.assertEqual(self.snapshot(), before)

    def snapshot(self):
        parts = []
        for table in TABLES:
            key = "id" if table == "runs" else "run_id"
            parts.extend([literal(table), "(SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]'::jsonb) "
                f"FROM vn_durability.{table} t WHERE {key}={literal(self.run)}::uuid)"])
        return json.loads(self.db.scalar("SELECT jsonb_build_object(" + ",".join(parts) + ");"), parse_float=Decimal)

    def test_decimal_planner_sql_roundtrips_match_independent_fraction_oracles(self):
        cases = [
            ("1", "3", "3", DecimalExecutionConfig()),
            ("100", "123.45", "130.25", DecimalExecutionConfig("30", "10", "10")),
            ("0." + "0" * 35 + "1", "0.000000000000000001", "0.000000000000000001", DecimalExecutionConfig()),
            ("1" + "0" * 36, "1000000000000000000", "1000000000000000000", DecimalExecutionConfig()),
            ("1", "1", "1", DecimalExecutionConfig("9999.999999")),
        ]
        for budget, reference, sell_reference, config in cases:
            with self.subTest(budget=budget, reference=reference, config=config.to_dict()):
                self.run, self.worker, self.revision = identity(), identity(), 0
                self.create(budget, config)
                account, position = identity(), identity()
                entry, fee_rate = EntryPlan(budget, reference, config), Fraction(config.fee_bps) / 10000
                impact = (Fraction(config.half_spread_bps) + Fraction(config.slippage_bps)) / 10000
                price = Fraction(ceil_fraction(Fraction(reference) * (1 + impact) * 10**18), 10**18)
                quantity = Fraction((Fraction(budget) / (1 + fee_rate) / price * 10**18).__floor__(), 10**18)
                notional = quantity * price
                fee = Fraction(ceil_fraction(notional * fee_rate * 10**36), 10**36)
                self.assertEqual(Fraction(entry.quantity), quantity)
                self.assertEqual(Fraction(entry.notional), notional)
                self.assertEqual(Fraction(entry.fee), fee)
                self.assertEqual(Fraction(entry.residual_budget), Fraction(budget) - notional - fee)
                self.commit([founder(account, budget), {"kind": "lifecycle", "status": "running"},
                             open_operation(entry, position, account, "SOL/USDC")])
                opened = self.snapshot()
                self.assertEqual(Fraction(opened["accounts"][0]["cash"]), Fraction(budget) - notional - fee)
                self.assertEqual(opened["positions"][0]["entry_execution"], entry.to_dict())
                exit = ExitPlan(entry, sell_reference)
                exit_price = Fraction((Fraction(sell_reference) * (1 - impact) * 10**18).__floor__(), 10**18)
                proceeds = quantity * exit_price
                exit_fee = Fraction(ceil_fraction(proceeds * fee_rate * 10**36), 10**36)
                expected = Fraction(budget) - notional - fee + proceeds - exit_fee
                self.commit([close_operation(exit, position), {"kind": "retire", "id": account}])
                state = self.snapshot()
                self.assertEqual(Fraction(state["runs"][0]["reserve"]), expected)
                self.assertEqual(state["accounts"][0]["cash"], 0)
                self.assertEqual(state["positions"][0]["exit_execution"], exit.to_dict())
                self.assertEqual(len(state["commands"]), 3)

    def test_explicit_writeoff_keeps_unspent_residual_and_reclaims_it_on_retirement(self):
        self.create("1")
        account, position = identity(), identity()
        entry = EntryPlan("1", "3")
        self.assertEqual(entry.residual_budget, "0.000000000000000001")
        self.commit([founder(account, "1"), {"kind": "lifecycle", "status": "running"},
                     open_operation(entry, position, account, "SOL/USDC"),
                     close_operation(ExitPlan(entry, None), position), {"kind": "retire", "id": account}])
        state = self.snapshot()
        self.assertEqual(state["runs"][0]["reserve"], Decimal("0.000000000000000001"))
        self.assertEqual(state["positions"][0]["exit_execution"]["kind"], "writeoff")
        self.assertEqual(state["positions"][0]["proceeds"], 0)

    def test_sql_recomputes_evidence_and_binds_immutable_run_policy_and_declared_budget(self):
        self.create("1")
        account = identity()
        self.commit([founder(account, "1"), {"kind": "lifecycle", "status": "running"}])
        entry = EntryPlan("1", "3")
        valid = open_operation(entry, identity(), account, "SOL/USDC")
        for field in ("fill_price", "quantity", "notional", "fee", "cash_debit", "residual_budget", "version"):
            with self.subTest(field=field):
                changed = deepcopy(valid)
                changed["execution"][field] = ("tampered" if field == "version"
                    else "1" if changed["execution"][field] == "0" else "0")
                self.reject([changed], "invalid_entry_evidence")
        for field in ("quantity", "notional", "fee"):
            changed = deepcopy(valid)
            changed[field] = "1" if changed[field] == "0" else "0"
            self.reject([changed], "entry_evidence_mismatch")
        self.reject([open_operation(EntryPlan("1", "3", DecimalExecutionConfig("1")),
            identity(), account, "SOL/USDC")], "entry_evidence_mismatch")
        overbudget = EntryPlan("1." + "0" * 35 + "1", "3")
        self.assertLess(Fraction(overbudget.cash_debit), 1)
        self.reject([open_operation(overbudget, identity(), account, "SOL/USDC")], "invalid_open")
        self.reject([{key: value for key, value in valid.items() if key != "execution"}], "invalid_payload")
        self.reject([{key: value for key, value in valid.items() if key != "execution"}], "contract_version_mismatch", version=1)

    def test_exit_evidence_must_match_original_entry_and_maximum_cash_overflow_rolls_back(self):
        maximum, tiny = "1" + "0" * 36, "0." + "0" * 35 + "1"
        self.create(maximum)
        account, position = identity(), identity()
        entry = EntryPlan(tiny, "0.000000000000000001")
        self.commit([founder(account, maximum), {"kind": "lifecycle", "status": "running"},
                     open_operation(entry, position, account, "SOL/USDC")])
        self.reject([close_operation(ExitPlan(entry, "0.000000000000000002"), position)], "23514")
        wrong = EntryPlan("0." + "0" * 35 + "2", "0.000000000000000001")
        self.reject([close_operation(ExitPlan(wrong, None), position)], "entry_evidence_mismatch")
        self.commit([close_operation(ExitPlan(entry, "0.000000000000000001"), position),
                     {"kind": "retire", "id": account}])
        self.assertEqual(self.snapshot()["runs"][0]["reserve"], Decimal(maximum))

    def test_v2_operation_uuid_spellings_are_canonical_and_late_rejection_is_atomic(self):
        self.create()
        account = "01234567-89ab-4cde-8f01-23456789abcd"
        spare = "01234567-89ab-4cde-8f01-23456789abce"
        position = "01234567-89ab-4cde-8f01-23456789abcf"
        candidate = "01234567-89ab-4cde-8f01-23456789abc0"
        self.commit([founder(account), founder(spare), {"kind": "lifecycle", "status": "running"}])
        entry = EntryPlan("10", "1")
        opening = open_operation(entry, position, account, "SOL/USDC")
        closing = close_operation(ExitPlan(entry, "1"), position)

        def reject_spellings(operation, field):
            identifier = operation[field]
            for alternate in (identifier.upper(), "{" + identifier + "}", identifier.replace("-", "")):
                with self.subTest(kind=operation["kind"], field=field, alternate=alternate):
                    self.assertNotEqual(alternate, identifier)
                    changed = deepcopy(operation)
                    changed[field] = alternate
                    # The first operation changes reserve/account/lineage projections;
                    # rejection must undo those changes as well as omit the journal.
                    self.reject([founder(identity(), "1"), changed], "invalid_identity")

        reject_spellings(founder(candidate, "1"), "id")
        reject_spellings(opening, "id")
        reject_spellings(opening, "account_id")
        self.commit([opening])
        reject_spellings(closing, "id")
        reject_spellings({"kind": "retire", "id": spare}, "id")
        self.commit([closing, {"kind": "retire", "id": account}, {"kind": "retire", "id": spare}])
        state = self.snapshot()
        self.assertEqual(state["runs"][0]["reserve"], 1000)
        self.assertEqual(len(state["commands"]), 4)

        # Retain the original SQL v1 UUID input behavior while v2 tightens it.
        self.run, self.worker, self.revision = identity(), identity(), 0
        self.call(PreparedCommand.create(self.owner, self.run, self.worker, {}, "100"))
        legacy = [{"kind": "birth", "id": account.upper(), "cash": "10", "parent_ids": []},
                  {"kind": "lifecycle", "status": "running"},
                  {"kind": "open", "id": "{" + position + "}", "account_id": account.replace("-", ""),
                   "asset": "SOL/USDC", "quantity": "1", "notional": "1", "fee": "0"},
                  {"kind": "close", "id": position.upper(), "proceeds": "1", "fee": "0"},
                  {"kind": "retire", "id": account.upper()}]
        self.db.sql(self.raw_sql(legacy, version=1), role="service_role")
        state = self.snapshot()
        self.assertEqual(state["runs"][0]["reserve"], 100)
        self.assertEqual(len(state["commands"]), 2)

    def test_normalized_full_cma_cohort_preserves_all_ordered_sources_within_payload_bound(self):
        self.create("1000")
        parents = [identity() for _ in range(100)]
        self.commit([founder(parent, "1") for parent in parents])
        group = identity()
        children = [identity() for _ in range(100)]
        operations = ([{"kind": "retire", "id": parent} for parent in parents]
            + [distribution(group, parents)]
            + [sample(child, group, parents[37], index=index) for index, child in enumerate(children)])
        command = self.command(operations)
        self.assertLess(len(command.request), 262144)
        self.call(command)
        state = self.snapshot()
        self.assertEqual(len(state["distributions"]), 1)
        self.assertEqual(len(state["distribution_sources"]), 100)
        ordered = sorted(state["distribution_sources"], key=lambda row: row["ordinal"])
        self.assertEqual([row["source_id"] for row in ordered], parents)
        self.assertEqual(len(state["account_lineage"]), 200)
        self.assertEqual(len(state["lineage_sources"]), 100)
        self.assertEqual({row["source_id"] for row in state["lineage_sources"]}, {parents[37]})
        self.assertTrue(all(row["distribution_id"] == group for row in state["account_lineage"] if row["account_id"] in children))
        self.assertEqual(len(state["commands"]), 3)

    def test_distribution_update_chain_and_overlapping_source_roles_remain_distinct(self):
        self.create()
        parents = [identity() for _ in range(4)]
        self.commit([founder(parent) for parent in parents])
        first, second = identity(), identity()
        self.commit([distribution(first, parents),
                     distribution(second, list(reversed(parents)), iteration="cohort:1", previous=first)])
        child = identity()
        birth = founder(child, strategy="differential_evolution")
        birth["lineage"].update(operation="de_rand1bin", source_iteration_id="cohort:1", offspring_index=0,
            sources=[{"role": role, "source_id": source, "ordinal": 0} for role, source in zip(
                ["target", "base", "difference_positive", "difference_negative", "asset_template"], parents + [parents[0]])])
        self.commit([birth])
        state = self.snapshot()
        child_sources = [row for row in state["lineage_sources"] if row["account_id"] == child]
        self.assertEqual(len(child_sources), 5)
        self.assertEqual({row["role"] for row in child_sources if row["source_id"] == parents[0]}, {"target", "asset_template"})
        self.assertEqual(next(row for row in state["distributions"] if row["id"] == second)["previous_distribution_id"], first)

    def test_invalid_lineage_and_late_distribution_failure_roll_back_entire_batch(self):
        self.create()
        parents = [identity() for _ in range(3)]
        self.commit([founder(parent) for parent in parents])
        group = identity()
        self.commit([distribution(group, parents)])
        child = identity()
        valid = sample(child, group, parents[0])
        for changes in ({"child_id": identity()}, {"source_iteration_id": "wrong-iteration"},
                        {"offspring_index": True}, {"distribution_id": identity()}):
            changed = deepcopy(valid)
            changed["lineage"].update(changes)
            self.reject([changed])
        for source in (child, identity()):
            changed = deepcopy(valid)
            changed["lineage"]["sources"][0]["source_id"] = source
            self.reject([changed])
        self.reject([{"kind": "retire", "id": parents[0]}, founder(identity()),
                     distribution(identity(), [parents[0], parents[0]])], "23505")
        self.reject([distribution(identity(), parents, previous=identity())], "23503")
        update = distribution(identity(), parents, previous=group)
        update["previous_distribution_id"] = update["id"]
        self.reject([update], "23514")

    def test_new_lineage_tables_keep_real_role_write_denial_and_owner_read_isolation(self):
        self.create()
        parents, group, child = [identity(), identity()], identity(), identity()
        self.commit([founder(parent) for parent in parents] + [distribution(group, parents), sample(child, group, parents[0])])
        before = self.snapshot()
        for table in NEW_TABLES:
            query = f"SELECT count(*) FROM vn_durability.{table} WHERE run_id={literal(self.run)}::uuid;"
            self.assertGreater(int(self.db.scalar(f"SET request.jwt.claim.sub={literal(self.owner)}; " + query, role="authenticated")), 0)
            self.assertEqual(self.db.scalar(f"SET request.jwt.claim.sub={literal(self.other_owner)}; " + query, role="authenticated"), "0")
            for role in ("anon", "authenticated", "service_role"):
                for source in (f"UPDATE vn_durability.{table} SET run_id=run_id WHERE false;",
                               f"DELETE FROM vn_durability.{table} WHERE false;",
                               f"INSERT INTO vn_durability.{table} SELECT * FROM vn_durability.{table} LIMIT 0;",
                               f"TRUNCATE vn_durability.{table} CASCADE;"):
                    result = self.db.sql(source, role=role, check=False)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("permission denied", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_iteration_labels_reject_python_whitespace_at_the_raw_sql_boundary(self):
        self.create()
        parents = [identity(), identity()]
        self.commit([founder(parent) for parent in parents])
        whitespace = "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680" + "".join(chr(code) for code in range(0x2000, 0x200B)) + "\u2028\u2029\u202f\u205f\u3000"
        self.assertEqual(whitespace.strip(), "")
        for iteration in ("", " ", "\t\r\n", "\x85\xa0", "\u2007\u202f\u3000", whitespace):
            with self.subTest(iteration=repr(iteration)):
                self.reject([distribution(identity(), parents, iteration=iteration)], "invalid_distribution")
                child = identity()
                clone = founder(child, strategy="genetic_algorithm")
                clone["lineage"].update(operation="clone_mutation", source_iteration_id=iteration, offspring_index=0,
                    sources=[{"role": "genetic_parent", "source_id": parents[0], "ordinal": 0}])
                self.reject([clone], "invalid_lineage")

    def test_offspring_slots_cannot_be_claimed_twice_and_late_conflicts_roll_back(self):
        self.create()
        parents, group = [identity(), identity()], identity()
        self.commit([founder(parent) for parent in parents] + [distribution(group, parents)])
        self.commit([sample(identity(), group, parents[0], index=0)])
        self.reject([{"kind": "retire", "id": parents[0]}, founder(identity()),
                     sample(identity(), group, parents[1], index=0)], "23505")
        self.reject([sample(identity(), group, parents[0], index=1),
                     sample(identity(), group, parents[1], index=1)], "23505")
        self.commit([sample(identity(), group, parents[1], index=1)])
        state = self.snapshot()
        children = [row for row in state["account_lineage"] if row["source_iteration_id"] == "cohort:0"]
        self.assertEqual(sorted(row["offspring_index"] for row in children), [0, 1])
        self.assertEqual(len(state["commands"]), 4)

    def test_lineage_sources_and_distribution_links_cannot_cross_owner_or_run(self):
        self.create()
        local = [identity(), identity()]
        self.commit([founder(parent) for parent in local])
        home = self.owner, self.run, self.worker, self.revision
        for foreign_owner in (self.other_owner, self.owner):
            self.owner, self.run, self.worker, self.revision = foreign_owner, identity(), identity(), 0
            self.create()
            foreign, group = [identity(), identity()], identity()
            self.commit([founder(parent) for parent in foreign] + [distribution(group, foreign)])
            self.owner, self.run, self.worker, self.revision = home
            self.reject([distribution(identity(), [local[0], foreign[0]])], "23503")
            self.reject([distribution(identity(), local, previous=group)], "23503")
            self.reject([sample(identity(), group, foreign[0])], "invalid_distribution_lineage")
            child = identity()
            clone = founder(child, strategy="genetic_algorithm")
            clone["lineage"].update(operation="clone_mutation", source_iteration_id="cohort:0", offspring_index=0,
                sources=[{"role": "genetic_parent", "source_id": foreign[0], "ordinal": 0}])
            self.reject([clone], "23503")

    def test_v2_operation_cap_and_private_validators_cannot_be_bypassed(self):
        self.create()
        self.commit([{"kind": "lifecycle", "status": "running"}] * 1024)
        self.assertEqual(len(self.snapshot()["commands"]), 2)
        self.reject([{"kind": "lifecycle", "status": "running"}] * 1025, "invalid_payload")
        for function, arguments in (
            ("decimal_units", "'\"1\"'::jsonb,36"),
            ("decimal_text", "1,36"),
            ("entry_evidence", document(EntryPlan("1", "1").to_dict())),
            ("record_distribution", f"{literal(self.owner)}::uuid,{literal(self.run)}::uuid,'{{}}'::jsonb"),
        ):
            for role in ("anon", "authenticated", "service_role"):
                result = self.db.sql(f"SELECT vn_durability.{function}({arguments});", role=role, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("permission denied", result.stderr)
