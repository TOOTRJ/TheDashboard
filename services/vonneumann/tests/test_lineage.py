"""Offline ancestry proofs from real optimizer proposals and versioned commands."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.decimal_execution import DecimalExecutionConfig
    from vonneumann.core.evaluation import EvaluationCohort
    from vonneumann.core.genome import Genome
    from vonneumann.core.lineage import (
        BirthLineage, DistributionLineage, LineagePlan, LineageValidationError,
        SourceBinding, lineage_plan_from_evolution,
    )
    from vonneumann.core.strategies.cma_es import CMAEvolutionStrategy
    from vonneumann.core.strategies.differential_evolution import DifferentialEvolutionStrategy
    from vonneumann.core.strategies.genetic_algorithm import GeneticAlgorithmStrategy
    from vonneumann.core.strategies.particle_swarm import ParticleSwarmStrategy
    from vonneumann.db.command_protocol import CommandValidationError, MAX_PAYLOAD_BYTES, PreparedCommand


def uid(number):
    return str(UUID(int=number))


OWNER, RUN, WORKER = uid(900001), uid(900002), uid(900003)
ITERATION = f"{RUN}:0"


def member(identity, score, genome=None):
    return SimpleNamespace(probe_id=identity, fitness=score, roi=score, num_trades=0,
                           genome=genome or Genome(assets=["SOL/USDC"], num_assets=1,
                                                   volume_threshold=1 + score / 100))


def complete(probes, *, iteration=ITERATION, start=1000):
    cohort = EvaluationCohort(iteration, probes, 60)
    cohort.start(start)
    return list(cohort.complete(probes, start + 60))


def prepare(operations, *, version=2):
    return PreparedCommand.batch(OWNER, RUN, WORKER, 1, 1, operations, version=version)


class LineageTypesTests(OfflineTestMixin, unittest.TestCase):
    def test_founder_exact_shape_all_strategies_and_copy_isolation(self):
        for strategy in ("genetic_algorithm", "differential_evolution", "particle_swarm", "cma_es"):
            with self.subTest(strategy=strategy):
                founder = BirthLineage.founder(uid(10), strategy)
                encoded = founder.to_dict()
                self.assertEqual(BirthLineage.from_dict(encoded), founder)
                encoded["sources"].append({"role": "genetic_parent", "source_id": uid(1), "ordinal": 0})
                self.assertEqual(founder.sources, ())
                with self.assertRaises(FrozenInstanceError):
                    founder.strategy = "cma_es"
                with self.assertRaises(LineageValidationError):
                    BirthLineage.from_dict(encoded)

    def test_role_cardinality_and_source_template_binding_for_each_algorithm(self):
        cases = [
            ("genetic_algorithm", "clone_mutation", (SourceBinding("genetic_parent", uid(1)),)),
            ("genetic_algorithm", "crossover_mutation", (SourceBinding("genetic_parent", uid(1)), SourceBinding("genetic_parent", uid(2), 1))),
            ("differential_evolution", "target_clone", (SourceBinding("target", uid(1)), SourceBinding("asset_template", uid(1)))),
            ("differential_evolution", "de_rand1bin", tuple(SourceBinding(role, uid(i + 1)) for i, role in enumerate(("target", "base", "difference_positive", "difference_negative"))) + (SourceBinding("asset_template", uid(1)),)),
            ("particle_swarm", "swarm_update", (SourceBinding("particle", uid(1)), SourceBinding("social", uid(2)), SourceBinding("asset_template", uid(1)))),
            ("particle_swarm", "swarm_update", (SourceBinding("particle", uid(1)), SourceBinding("asset_template", uid(1)))),
            ("cma_es", "no_active_clone", (SourceBinding("clone_source", uid(1)), SourceBinding("asset_template", uid(1)))),
        ]
        for strategy, operation, sources in cases:
            with self.subTest(strategy=strategy, operation=operation, count=len(sources)):
                lineage = BirthLineage(uid(10), strategy, operation, ITERATION, 0, sources)
                self.assertEqual(BirthLineage.from_dict(lineage.to_dict()), lineage)
                for wrong in (sources[:-1], sources + (sources[0],)):
                    with self.assertRaises(LineageValidationError):
                        replace(lineage, sources=wrong)
                with self.assertRaises(LineageValidationError):
                    replace(lineage, child_id=uid(1))

    def test_genetic_duplicate_parents_and_wrong_role_order_are_rejected(self):
        with self.assertRaises(LineageValidationError):
            BirthLineage(uid(10), "genetic_algorithm", "crossover_mutation", ITERATION, 0,
                         (SourceBinding("genetic_parent", uid(1)), SourceBinding("genetic_parent", uid(1), 1)))
        with self.assertRaises(LineageValidationError):
            BirthLineage(uid(10), "differential_evolution", "target_clone", ITERATION, 0,
                         (SourceBinding("asset_template", uid(1)), SourceBinding("target", uid(1))))
        with self.assertRaises(LineageValidationError):
            BirthLineage(uid(10), "particle_swarm", "swarm_update", ITERATION, 0,
                         (SourceBinding("particle", uid(1)), SourceBinding("social", uid(1)), SourceBinding("asset_template", uid(1))))

    def test_lineage_identity_text_version_and_immutable_input_validation(self):
        lineage = BirthLineage(uid(10), "genetic_algorithm", "clone_mutation", ITERATION, 0,
                               (SourceBinding("genetic_parent", uid(1)),))
        for edits in ({"child_id": "not-a-uuid"}, {"child_id": uid(10).replace("-", "")},
                      {"source_iteration_id": ""}, {"source_iteration_id": " "},
                      {"source_iteration_id": "x" * 257}, {"source_iteration_id": "bad\0text"},
                      {"source_iteration_id": None}, {"offspring_index": True},
                      {"offspring_index": 100}, {"sources": list(lineage.sources)},
                      {"distribution_id": uid(20)}, {"strategy": []}):
            with self.subTest(edits=edits), self.assertRaises(LineageValidationError):
                replace(lineage, **edits)
        for edits in ({"version": True}, {"version": 2}, {"extra": 1}, {"sources": [{"role": "guess"}]}):
            with self.subTest(edits=edits), self.assertRaises(LineageValidationError):
                BirthLineage.from_dict({**lineage.to_dict(), **edits})

    def test_distribution_full_membership_prior_chain_and_detached_operations(self):
        sources = tuple(uid(i) for i in range(1, 101))
        bootstrap = DistributionLineage(uid(500), "bootstrap", ITERATION, None, sources)
        update = DistributionLineage(uid(501), "update", f"{RUN}:1", bootstrap.id, sources)
        self.assertEqual(DistributionLineage.from_operation(update.to_operation()), update)
        encoded = bootstrap.to_operation()
        self.assertEqual(len(encoded["source_ids"]), 100)
        encoded["source_ids"].clear()
        self.assertEqual(bootstrap.source_ids, sources)
        for edits in ({"source_ids": sources + (uid(101),)}, {"source_ids": sources[:-1] + (sources[0],)},
                      {"source_ids": (sources[0],)}, {"source_ids": list(sources)},
                      {"previous_distribution_id": uid(501)}, {"stage": "update"}):
            with self.subTest(edits=edits), self.assertRaises(LineageValidationError):
                replace(bootstrap, **edits)
        with self.assertRaises(LineageValidationError):
            replace(update, previous_distribution_id=update.id)

    def test_direct_plan_enforces_common_context_membership_and_child_order(self):
        distribution = DistributionLineage(uid(500), "bootstrap", ITERATION, None, (uid(1), uid(2)))
        children = tuple(BirthLineage(uid(10 + i), "cma_es", "distribution_sample", ITERATION, i,
                                      (SourceBinding("asset_template", uid(1)),), distribution.id) for i in range(2))
        plan = LineagePlan(distribution, children)
        self.assertEqual(len(plan.distribution_operation["source_ids"]), 2)
        plan.distribution_operation["source_ids"].clear()
        self.assertEqual(len(plan.distribution_operation["source_ids"]), 2)
        for candidate in ((children[1], children[0]),
                          (children[0], replace(children[1], source_iteration_id="other")),
                          (children[0], replace(children[1], child_id=uid(2))),
                          (children[0], replace(children[1], sources=(SourceBinding("asset_template", uid(3)),)))):
            with self.subTest(children=candidate), self.assertRaises(LineageValidationError):
                LineagePlan(distribution, candidate)
        with self.assertRaises(LineageValidationError):
            LineagePlan(None, children)
        genetic = BirthLineage(uid(12), "genetic_algorithm", "clone_mutation", ITERATION, 1,
                               (SourceBinding("genetic_parent", uid(1)),))
        with self.assertRaises(LineageValidationError):
            LineagePlan(None, (replace(genetic, child_id=uid(11), offspring_index=0), replace(genetic, strategy="cma_es", operation="no_active_clone", sources=(SourceBinding("clone_source", uid(1)), SourceBinding("asset_template", uid(1))))))


class EvolutionLineageTests(OfflineTestMixin, unittest.TestCase):
    def proposal(self, kind, *, count=8, genes=None):
        config = ColonyConfig(enabled_genes=["volume_threshold"] if genes is None else genes,
                              available_assets=["SOL/USDC"], mutation_rate=0)
        probes = [member(uid(i + 1), float(i)) for i in range(count)]
        for probe in probes:
            probe.genome.validate(config)
        strategy = kind()
        strategy._rng.seed(127)
        strategy.initialize(probes, config)
        if kind is not CMAEvolutionStrategy:
            strategy.bind_candidates(probes)
        evaluated = complete(probes)
        result = strategy.evolve(list(reversed(evaluated)), [], config)
        return strategy, config, probes, evaluated, result

    def convert(self, strategy, result, evaluated, *, child_start=1001, **kwargs):
        return lineage_plan_from_evolution(strategy.name, result, list(reversed(evaluated)),
            [uid(child_start + i) for i in range(len(evaluated))],
            cohort_member_ids=[item.probe_id for item in evaluated], **kwargs)

    def test_actual_ga_clones_and_crossover_preserve_order_without_mutating_proposal(self):
        for random_value, operation in ((0, "clone_mutation"), (.99, "crossover_mutation")):
            with self.subTest(operation=operation), patch("random.Random.random", return_value=random_value):
                strategy, _, _, evaluated, result = self.proposal(GeneticAlgorithmStrategy, count=2)
            plan = self.convert(strategy, result, evaluated)
            for index, child in enumerate(plan.birth_lineages):
                self.assertEqual(child.operation, operation)
                self.assertEqual([binding.source_id for binding in child.sources], result.parent_map[str(index)])
            before = plan.birth_lineages[0].to_dict()
            result.metadata["offspring"][0]["parent_ids"].clear()
            result.parent_map["0"].clear()
            self.assertEqual(plan.birth_lineages[0].to_dict(), before)

    def test_actual_de_preserves_all_four_donors_and_role_order_after_json_key_sort(self):
        strategy, _, _, evaluated, result = self.proposal(DifferentialEvolutionStrategy)
        expected = self.convert(strategy, result, evaluated)
        result.metadata = json.loads(json.dumps(result.metadata, sort_keys=True))
        actual = self.convert(strategy, result, evaluated)
        self.assertEqual(actual, expected)
        for index, child in enumerate(actual.birth_lineages):
            roles = [binding.role for binding in child.sources]
            if index < 4:
                self.assertEqual(roles, ["target", "asset_template"])
            else:
                self.assertEqual(roles, ["target", "base", "difference_positive", "difference_negative", "asset_template"])
                self.assertEqual(len({binding.source_id for binding in child.sources}), 4)
                self.assertEqual([binding.source_id for binding in child.sources[:-1]], result.parent_map[str(index)])

    def test_actual_de_pair_selection_is_bound_to_ordered_target_trial_slots(self):
        strategy, config, _, evaluated, first = self.proposal(DifferentialEvolutionStrategy)
        self.convert(strategy, first, evaluated)
        probes = [member(uid(1001 + i), [-2., -2., 0., 1., -1., -3., 0., .5][i], genome)
                  for i, genome in enumerate(first.offspring)]
        strategy.bind_candidates(probes)
        evaluated = complete(probes, iteration=f"{RUN}:1", start=1060)
        second = strategy.evolve(evaluated, [], config)
        self.convert(strategy, second, evaluated, child_start=2001)
        invalid = deepcopy(second)
        decisions = invalid.metadata["pair_selections"]
        decisions[0]["target_id"], decisions[1]["target_id"] = decisions[1]["target_id"], decisions[0]["target_id"]
        # Equal target scores make this an otherwise plausible alternative pairing.
        with self.assertRaises(LineageValidationError):
            self.convert(strategy, invalid, evaluated, child_start=2001)

    def test_actual_pso_separates_particle_social_and_asset_template(self):
        strategy, _, _, evaluated, result = self.proposal(ParticleSwarmStrategy, count=4)
        plan = self.convert(strategy, result, evaluated)
        for index, child in enumerate(plan.birth_lineages):
            self.assertEqual(child.sources[0], SourceBinding("particle", evaluated[index].probe_id))
            self.assertEqual(child.sources[-1], SourceBinding("asset_template", evaluated[index].probe_id))
            if index != 3:
                self.assertEqual(child.sources[1], SourceBinding("social", evaluated[3].probe_id))
            else:
                self.assertEqual(len(child.sources), 2)

    def test_actual_cma_bootstrap_update_and_non_uuid_iteration_provenance(self):
        strategy, config, _, evaluated, first = self.proposal(CMAEvolutionStrategy, count=4)
        initial = self.convert(strategy, first, evaluated, distribution_id=uid(500))
        self.assertEqual(initial.distribution.stage, "bootstrap")
        self.assertEqual(initial.distribution.source_iteration_id, ITERATION)
        self.assertEqual(initial.distribution.source_ids, tuple(item.probe_id for item in evaluated))
        self.assertTrue(all(child.sources == (SourceBinding("asset_template", evaluated[-1].probe_id),)
                            for child in initial.birth_lineages))
        probes = [member(uid(1001 + i), float(i), genome) for i, genome in enumerate(first.offspring)]
        strategy.bind_candidates(probes)
        evaluated = complete(probes, iteration=f"{RUN}:1", start=1060)
        second = strategy.evolve(evaluated, [], config)
        with self.assertRaises(LineageValidationError):
            self.convert(strategy, second, evaluated, child_start=2001, distribution_id=uid(501))
        update = self.convert(strategy, second, evaluated, child_start=2001,
                              distribution_id=uid(501), previous_distribution_id=uid(500))
        self.assertEqual(update.distribution.stage, "update")
        self.assertEqual(update.distribution.previous_distribution_id, initial.distribution.id)

    def test_actual_no_active_gene_results_are_clones_for_all_four_algorithms(self):
        for kind in (GeneticAlgorithmStrategy, DifferentialEvolutionStrategy, ParticleSwarmStrategy, CMAEvolutionStrategy):
            with self.subTest(kind=kind.__name__):
                strategy, _, _, evaluated, result = self.proposal(kind, genes=[])
                plan = self.convert(strategy, result, evaluated)
                self.assertIsNone(plan.distribution)
                self.assertTrue(all(len({source.source_id for source in child.sources}) == 1 for child in plan.birth_lineages))
                self.assertTrue(all(child.operation in {"no_active_clone", "target_clone"} for child in plan.birth_lineages))
                with self.assertRaises(LineageValidationError):
                    self.convert(strategy, result, evaluated, distribution_id=uid(500))

    def test_converter_rejects_incomplete_mixed_nonfinite_and_malformed_evaluation_evidence(self):
        strategy, _, _, evaluated, result = self.proposal(GeneticAlgorithmStrategy)
        cases = [evaluated[:-1], [evaluated[0], *evaluated[:-1]]]
        for edits in ({"probe_id": []}, {"probe_id": uid(800)}, {"iteration_id": "other"},
                      {"window_started_at": 999}, {"window_ends_at": 1200}, {"fitness": float("nan")},
                      {"roi": float("inf")}, {"num_trades": True}, {"cohort_complete": False},
                      {"status": "aborted"}, {"evaluation_id": evaluated[1].evaluation_id},
                      {"terminated_at": 900}):
            cases.append([replace(evaluated[0], **edits), *evaluated[1:]])
        ids = [item.probe_id for item in evaluated]
        for evidence in cases:
            with self.subTest(evidence=evidence), self.assertRaises(LineageValidationError):
                lineage_plan_from_evolution(strategy.name, result, evidence,
                    [uid(1001 + i) for i in range(8)], cohort_member_ids=ids)
        for children, members in ((ids, ids), ([uid(1001 + i) for i in range(8)], ids[:-1]),
                                  ([uid(1001 + i) for i in range(8)], list(reversed(ids)))):
            with self.assertRaises(LineageValidationError):
                lineage_plan_from_evolution(strategy.name, result, evaluated, children, cohort_member_ids=members)

    def test_converter_rejects_missing_roles_unknown_sources_and_contradictory_metadata(self):
        for kind in (GeneticAlgorithmStrategy, DifferentialEvolutionStrategy, ParticleSwarmStrategy, CMAEvolutionStrategy):
            strategy, _, _, evaluated, result = self.proposal(kind)
            kwargs = {"distribution_id": uid(500)} if kind is CMAEvolutionStrategy else {}
            cases = []
            missing = deepcopy(result)
            missing.metadata = {}
            cases.append(missing)
            unknown = deepcopy(result)
            unknown.parent_map["0"] = [uid(799)]
            cases.append(unknown)
            incomplete = deepcopy(result)
            incomplete.offspring.pop()
            cases.append(incomplete)
            duplicate = deepcopy(result)
            duplicate.parent_map["0"] *= 2
            cases.append(duplicate)
            for invalid in cases:
                with self.subTest(kind=kind.__name__), self.assertRaises(LineageValidationError):
                    self.convert(strategy, invalid, evaluated, **kwargs)
        strategy, _, _, evaluated, result = self.proposal(DifferentialEvolutionStrategy)
        for edit in ("phase", "operation"):
            invalid = deepcopy(result)
            if edit == "phase":
                invalid.metadata["phase"] = []
            else:
                invalid.metadata["next_pairs"][0]["operation"] = []
            with self.assertRaises(LineageValidationError):
                self.convert(strategy, invalid, evaluated)
        invalid = deepcopy(result)
        invalid.metadata["next_pairs"][0]["trial_contributors"] = {"target": invalid.metadata["selected_ids"][0]}
        with self.assertRaises(LineageValidationError):
            self.convert(strategy, invalid, evaluated)

    def test_cma_distribution_membership_cannot_be_truncated_or_reordered(self):
        strategy, _, _, evaluated, result = self.proposal(CMAEvolutionStrategy, count=4)
        for sources in (result.retire_ids[:2], list(reversed(result.retire_ids))):
            invalid = deepcopy(result)
            invalid.metadata["distribution_source_ids"] = sources
            with self.assertRaises(LineageValidationError):
                self.convert(strategy, invalid, evaluated, distribution_id=uid(500))

    def test_normalized_100_member_replacement_is_complete_and_within_payload_bound(self):
        strategy, _, _, evaluated, result = self.proposal(CMAEvolutionStrategy, count=100)
        plan = self.convert(strategy, result, evaluated, distribution_id=uid(500))
        operations = [{"kind": "retire", "id": item.probe_id} for item in evaluated]
        operations.append(plan.distribution_operation)
        operations.extend({"kind": "birth", "id": child.child_id, "cash": "1", "lineage": child.to_dict()}
                          for child in plan.birth_lineages)
        command = prepare(operations)
        payload = command.rpc_args["payload"]
        encoded = json.dumps(payload, ensure_ascii=False, separators=(", ", ": ")).encode()
        self.assertLess(len(encoded), MAX_PAYLOAD_BYTES)
        self.assertEqual(len(payload["operations"]), 201)
        self.assertEqual(len(payload["operations"][100]["source_ids"]), 100)
        self.assertEqual([child.child_id for child in plan.birth_lineages], [uid(1001 + i) for i in range(100)])
        self.assertEqual([child.distribution_id for child in plan.birth_lineages], [uid(500)] * 100)
        # This proves lineage-only replacement capacity, not all positions/evidence/checkpoints.


class LineageProtocolTests(OfflineTestMixin, unittest.TestCase):
    def test_versioned_birth_shapes_and_distribution_operation_are_not_interchangeable(self):
        legacy = {"kind": "birth", "id": uid(10), "cash": "1", "parent_ids": []}
        typed = {"kind": "birth", "id": uid(10), "cash": "1", "lineage": BirthLineage.founder(uid(10)).to_dict()}
        self.assertEqual(prepare([legacy], version=1).rpc_args["payload"]["version"], 1)
        self.assertEqual(prepare([typed]).rpc_args["payload"]["version"], 2)
        for operations, version in (([legacy], 2), ([typed], 1),
                                    ([DistributionLineage(uid(500), "bootstrap", ITERATION, None, (uid(1), uid(2))).to_operation()], 1),
                                    ([{**typed, "id": uid(11)}], 2)):
            with self.assertRaises(CommandValidationError):
                prepare(operations, version=version)

    def test_v2_operation_limit_expands_without_weakening_payload_limit(self):
        operations = [{"kind": "retire", "id": uid(1 + i)} for i in range(1024)]
        self.assertEqual(len(prepare(operations).rpc_args["payload"]["operations"]), 1024)
        with self.assertRaises(CommandValidationError):
            prepare(operations + [{"kind": "retire", "id": uid(2000)}])
        with self.assertRaises(CommandValidationError):
            prepare(operations[:257], version=1)
        bloated = [{"kind": "birth", "id": uid(i + 1), "cash": "1",
                    "lineage": BirthLineage.founder(uid(i + 1)).to_dict()} for i in range(1024)]
        with self.assertRaisesRegex(CommandValidationError, "size limit|bounded immutable"):
            prepare(bloated)
        self.assertEqual(len(bloated), 1024)  # No partial/truncated replacement is returned.

    def test_v2_creation_requires_exact_typed_policy_and_explicit_version(self):
        policy = DecimalExecutionConfig(fee_bps="1", slippage_bps="2").policy()
        config = {"durability_contract_version": 2, "execution": policy}
        command = PreparedCommand.create(OWNER, RUN, WORKER, config, "100")
        policy["config"]["fee_bps"] = "999"
        self.assertEqual(command.rpc_args["configuration"]["execution"]["config"]["fee_bps"], "1")
        for bad in ({"durability_contract_version": 2}, {"durability_contract_version": True},
                    {"durability_contract_version": 3}, {"durability_contract_version": "2"},
                    {"durability_contract_version": 2, "execution": {**policy, "valuation": "other"}},
                    {"durability_contract_version": 2, "execution": {**policy, "quantity_scale": True}}):
            with self.subTest(config=bad), self.assertRaises(CommandValidationError):
                PreparedCommand.create(OWNER, RUN, WORKER, bad, "100")
        for config in ({}, {"durability_contract_version": 1}):
            PreparedCommand.create(OWNER, RUN, WORKER, config, "100")


if __name__ == "__main__":
    unittest.main()
