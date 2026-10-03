"""Adversarial wire changes against actual bounded exact-engine candidates."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import unittest
from uuid import UUID

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.decision_inputs import DecisionInputs
    from vonneumann.core.exact_rehearsal import (
        ExactCandidate, ExactObservation, ExactRehearsalConfig, ExactRehearsalError,
        bootstrap, prepare_decision, prepare_protective,
    )
    from vonneumann.db.command_protocol import CommandValidationError, PreparedCommand


WORKER = str(UUID(int=9000))
COMMAND = str(UUID(int=9001))


def inputs(at, *, births=False):
    return DecisionInputs(datetime.fromtimestamp(at, timezone.utc),
        datetime.fromtimestamp(1_800_000_000, timezone.utc), 500.0,
        ids=tuple(str(UUID(int=value)) for value in range(100, 108)) if births else (),
        names=tuple((0, f"Candidate {index}") for index in range(8)) if births else ())


def command(candidate, *, transition=None, operations=None, revision=None):
    body = candidate.transition if transition is None else transition
    return PreparedCommand.batch(USER_A, A1, WORKER, 1,
        candidate.state.revision - 1 if revision is None else revision,
        candidate.operations if operations is None else operations,
        command_id=COMMAND, version=3, transition=body)


class TransitionProtocolTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.config = ExactRehearsalConfig("genetic_algorithm", USER_A, A1)
        self.initial = bootstrap(self.config, inputs(0, births=True))
        self.protection = prepare_protective(self.initial.state, ExactObservation(900, "100"), inputs(900))
        self.decision = prepare_decision(self.protection.state,
            ExactObservation(900, "100", 900, "100"), inputs(900))

    def reject(self, candidate, mutation):
        transition = candidate.transition
        mutation(transition)
        with self.assertRaises(CommandValidationError):
            command(candidate, transition=transition)

    def test_complete_replacement_cannot_omit_or_rebind_its_evaluated_cohort(self):
        from tests.test_exact_rehearsal import roundtrip_windows
        config, _final, candidates, _maximum = roundtrip_windows("genetic_algorithm")
        replacement = next(candidate for candidate in candidates
                           if any(event["kind"] == "evaluation" for event in candidate.transition["events"]))

        def prepare(transition):
            return PreparedCommand.batch(config.owner_id, config.run_id, WORKER, 1,
                replacement.state.revision - 1, replacement.operations,
                version=3, transition=transition)

        prepare(replacement.transition)
        changes = (
            lambda e: e.__setitem__("cohort", {}),
            lambda e: e.__setitem__("selection", {}),
            lambda e: e["cohort"]["member_ids"].reverse(),
            lambda e: e["cohort"]["evaluations"].pop(),
            lambda e: e["cohort"]["evaluations"][0].__setitem__("evaluation_id", "wrong-slot"),
            lambda e: e["cohort"]["evaluations"][0].__setitem__("fitness", None),
            lambda e: e["cohort"]["evaluations"][0].__setitem__("num_trades", 64),
            lambda e: e["cohort"].__setitem__("horizon_seconds", {"float64": float(60).hex()}),
        )
        for index, mutation in enumerate(changes):
            with self.subTest(change=index):
                changed = replacement.transition
                mutation(changed["after"]["engine"]["last_evaluation"])
                with self.assertRaises(CommandValidationError):
                    prepare(changed)

    def test_real_bootstrap_and_no_economic_operation_steps_form_immutable_commands(self):
        for algorithm in ("genetic_algorithm", "differential_evolution", "particle_swarm", "cma_es"):
            with self.subTest(algorithm=algorithm):
                config = ExactRehearsalConfig(algorithm, USER_A, A1)
                create = PreparedCommand.create(USER_A, A1, WORKER, config.run_configuration(),
                                                 config.initial_cash, command_id=COMMAND)
                self.assertEqual(create.rpc_args["configuration"], config.run_configuration())
                initial = bootstrap(config, inputs(0, births=True))
                protected = prepare_protective(initial.state, ExactObservation(900, "100"), inputs(900))
                decision = prepare_decision(protected.state,
                    ExactObservation(900, "100", 900, "100"), inputs(900))
                for candidate in (initial, protected, decision):
                    prepared = command(candidate)
                    self.assertEqual(prepared.expected_revision, candidate.state.revision - 1)
                    exposed = candidate.transition
                    exposed["after"]["reserve"] = "0"
                    self.assertEqual(command(candidate).request, prepared.request)
                self.assertEqual(protected.operations, [])
                self.assertEqual(decision.operations, [])
                self.assertNotEqual(protected.transition["after"]["engine"],
                                    decision.transition["after"]["engine"])

    def test_candidate_pair_requires_identical_canonical_owned_state_and_wire(self):
        original = self.initial
        replica = ExactCandidate(original.state, original._wire, original.payload_bytes)
        self.assertEqual(replica.transition, original.transition)
        with self.assertRaises(ExactRehearsalError):
            ExactCandidate(self.protection.state, original._wire, original.payload_bytes)
        mutations = (
            lambda after: after.__setitem__("reserve", "201"),
            # Python structural equality considers False==0. Typed canonical
            # bytes must still distinguish economic boolean fields from ints.
            lambda after: after["accounts"][0].__setitem__("retired", 0),
            lambda after: after.__setitem__("revision", float(after["revision"])),
        )
        for change in mutations:
            payload = json.loads(original._wire)
            change(payload["transition"]["after"])
            wire = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=True, allow_nan=False).encode("ascii")
            measured = len(json.dumps(payload, sort_keys=True, separators=(", ", ": "),
                                      ensure_ascii=False, allow_nan=False).encode("utf-8"))
            with self.subTest(mutation=mutations.index(change)), self.assertRaises(ExactRehearsalError):
                ExactCandidate(original.state, wire, measured)
        with self.assertRaises(ExactRehearsalError):
            ExactCandidate(original.state, original._wire + b" ", original.payload_bytes)
        for false_size in (0, True, original.payload_bytes - 1, original.payload_bytes + 1):
            with self.subTest(size=false_size), self.assertRaises(ExactRehearsalError):
                ExactCandidate(original.state, original._wire, false_size)

    def test_owner_revision_prior_state_and_immutable_policy_mismatches_are_rejected(self):
        changes = (
            lambda t: t["after"].__setitem__("owner_id", str(UUID(int=9002))),
            lambda t: t["after"].__setitem__("run_id", str(UUID(int=9002))),
            lambda t: t["after"].__setitem__("revision", True),
            lambda t: t["after"].__setitem__("revision", 99),
            lambda t: t.__setitem__("before", None),
            lambda t: t["after"]["engine"]["config"].__setitem__("search_seed", "9"),
        )
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.reject(self.protection, change)

    def test_complete_economic_projection_rejects_omissions_minted_cash_and_reordered_rows(self):
        changes = (
            lambda t: t["after"].__setitem__("reserve", "201"),
            lambda t: t["after"]["accounts"][0].__setitem__("cash", "101"),
            lambda t: t["after"]["accounts"].pop(),
            lambda t: t["after"]["accounts"].reverse(),
            lambda t: t["after"]["accounts"].__setitem__(1, deepcopy(t["after"]["accounts"][0])),
            lambda t: t["after"]["accounts"][0].__setitem__("retired", True),
        )
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.reject(self.initial, change)
        with self.assertRaises(CommandValidationError):
            command(self.initial, operations=self.initial.operations[:-1])

    def test_engine_shape_membership_and_allocation_identity_must_be_complete(self):
        changes = (
            lambda t: t["after"]["engine"].__setitem__("extra", "ignored"),
            lambda t: t["after"]["engine"].pop("ema"),
            lambda t: t["after"]["engine"]["members"].pop(),
            lambda t: t["after"]["engine"]["members"].__setitem__(1,
                deepcopy(t["after"]["engine"]["members"][0])),
            lambda t: t["after"]["engine"]["members"][0].__setitem__("id", str(UUID(int=9999))),
            lambda t: t["after"]["engine"]["used_ids"].pop(),
            lambda t: t["after"]["engine"]["used_ids"].append(t["after"]["engine"]["used_ids"][0]),
            lambda t: t["after"]["engine"].__setitem__("generation", True),
        )
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.reject(self.initial, change)

    def test_genome_indicator_and_risk_evidence_cannot_hide_nonfinite_or_ambiguous_values(self):
        changes = (
            lambda t: t["after"]["engine"]["members"][0]["genome"].__setitem__("ema_fast", "nan"),
            lambda t: t["after"]["engine"]["members"][0]["genome"].__setitem__("ema_fast", "3"),
            lambda t: t["after"]["engine"]["members"][0]["genome"].__setitem__("new_gene", "0x1p+0"),
            lambda t: t["after"]["engine"]["members"][0]["max_drawdown"].__setitem__("denominator", "0"),
            lambda t: t["after"]["engine"]["members"][0]["max_drawdown"].__setitem__("numerator", "2"),
            lambda t: t["after"]["engine"]["members"][0]["max_drawdown"].__setitem__("numerator", "00"),
            lambda t: t["after"]["engine"]["ema"]["values"].__setitem__("2", "inf"),
            lambda t: t["after"]["engine"]["ema"].__setitem__("count", True),
            lambda t: t["after"]["engine"]["ema"]["closes"].__setitem__(0, "100.0"),
        )
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.reject(self.decision, change)

    def test_optimizer_evidence_requires_reviewed_graph_not_arbitrary_json(self):
        changes = (
            lambda t: t["after"]["engine"].__setitem__("optimizer", {}),
            lambda t: t["after"]["engine"]["optimizer"].__setitem__("version", "optimizer-evidence-v99"),
            lambda t: t["after"]["engine"]["optimizer"]["strategy"].__setitem__("class", "UnreviewedStrategy"),
            lambda t: t["after"]["engine"]["optimizer"]["strategy"]["fields"].pop("_rng"),
            lambda t: t["after"]["engine"]["optimizer"]["strategy"]["fields"].__setitem__("_rng", {"ref": 999999}),
        )
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.reject(self.initial, change)

    def test_inputs_actions_and_events_cannot_be_detached_from_the_transition(self):
        changes = (
            lambda t: t["evidence"]["inputs"].__setitem__("ids", []),
            lambda t: t["evidence"]["inputs"]["names"].__setitem__(0, [1, "wrong generation"]),
            lambda t: t["evidence"]["actions"].pop(),
            lambda t: t["evidence"]["actions"][0].__setitem__("account_id", str(UUID(int=9999))),
            lambda t: t["events"].pop(),
            lambda t: t["events"].reverse(),
            lambda t: t["events"][0].__setitem__("at", 1),
            lambda t: t["events"][0].__setitem__("operation_index", True),
        )
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.reject(self.initial, change)

    def test_quote_and_decision_time_bind_even_without_economic_operations(self):
        changes = (
            lambda t: t["evidence"]["observation"].__setitem__("timestamp", 901),
            lambda t: t["evidence"]["observation"].__setitem__("price", "101"),
            lambda t: t["after"]["engine"]["last_quote"].__setitem__("price", "101"),
            lambda t: t["evidence"]["inputs"].__setitem__("event_at", "1970-01-01T00:15:00Z"),
            lambda t: t["evidence"]["inputs"].__setitem__("monotonic_at", "500"),
        )
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.reject(self.protection, change)

    def test_protection_and_ordinary_steps_cannot_mutate_a_live_members_identity_or_genes(self):
        def change_gene(transition):
            genome = transition["after"]["engine"]["members"][0]["genome"]
            genome["ema_fast"] = (4.0 if float.fromhex(genome["ema_fast"]) != 4.0 else 5.0).hex()

        for candidate in (self.protection, self.decision):
            for change in (change_gene, lambda t: t["after"]["engine"]["members"][0].__setitem__(
                    "name", "Unallocated Name")):
                with self.subTest(phase=candidate.transition["evidence"]["kind"], mutation=change.__name__):
                    self.reject(candidate, change)
        # Every identity remains otherwise valid; even a reordered protection
        # cohort must fail because it changes the optimizer's ordered binding.
        self.reject(self.protection, lambda t: t["after"]["engine"]["members"].reverse())

    def test_protection_cannot_invent_pending_intent_or_change_completed_cursor(self):
        protected = prepare_protective(self.decision.state, ExactObservation(901, "100"), inputs(901))
        # All fields here satisfy state-schema bounds. Only the before/after
        # continuation rule distinguishes the invented signal from a real one.
        def invent_intent(transition):
            member = transition["after"]["engine"]["members"][0]
            member["cursor"] = 900
            member["pending"] = {"action": "entry", "signal_at": 901, "position_id": None}

        self.reject(protected, invent_intent)
        self.reject(protected, lambda t: t["after"]["engine"]["members"][0].__setitem__("cursor", 900))

    def test_create_configuration_rejects_underfunding_and_unsupported_profile(self):
        changes = (
            lambda c: c["rehearsal"].__setitem__("initial_cash", "799"),
            lambda c: c["rehearsal"].__setitem__("seed_capital", "0.5"),
            lambda c: c["rehearsal"].__setitem__("population", True),
            lambda c: c["rehearsal"].__setitem__("max_generations", 4),
            lambda c: c["rehearsal"].__setitem__("strategy", "new_optimizer"),
            lambda c: c["rehearsal"].__setitem__("source", "unverified_provider"),
        )
        for change in changes:
            with self.subTest(change=changes.index(change)):
                config = self.config.run_configuration()
                change(config)
                with self.assertRaises(CommandValidationError):
                    PreparedCommand.create(USER_A, A1, WORKER, config,
                        config["rehearsal"]["initial_cash"], command_id=COMMAND)


if __name__ == "__main__":
    unittest.main()
