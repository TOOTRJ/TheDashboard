"""Actual optimizer output must fit the exact, bounded lineage command contract.

These tests use synthetic completed windows and the installed CMA optimizer.
No solver is replaced by a mock and no engine, provider, or database is started.
They check provenance conversion, not numerical-weight or checkpoint recovery.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from uuid import uuid4

from tests.security_support import deny_network

with deny_network():
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.evaluation import EvaluationCohort
    from vonneumann.core.genome import Genome
    from vonneumann.core.lineage import LineageValidationError, lineage_plan_from_evolution
    from vonneumann.core.strategies.cma_es import CMAEvolutionStrategy
    from vonneumann.core.strategies.differential_evolution import DifferentialEvolutionStrategy
    from vonneumann.core.strategies.genetic_algorithm import GeneticAlgorithmStrategy
    from vonneumann.core.strategies.particle_swarm import ParticleSwarmStrategy
    from vonneumann.db.command_protocol import PreparedCommand


STRATEGIES = (GeneticAlgorithmStrategy, DifferentialEvolutionStrategy,
              ParticleSwarmStrategy, CMAEvolutionStrategy)


def candidate(identity, genome=None, *, score=0.0):
    return SimpleNamespace(probe_id=identity, genome=genome or Genome(
        assets=["SOL/USDC"], num_assets=1), fitness=score, roi=score, num_trades=0)


def evaluated(probes, iteration="iteration-1", started_at=1000):
    cohort = EvaluationCohort(iteration, probes, 60)
    cohort.start(started_at)
    # Arrival order is deliberately different from cohort membership order.
    return list(cohort.complete(list(reversed(probes)), started_at + 60))


class RealStrategyLineageTests(unittest.TestCase):
    def setUp(self):
        guard = deny_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)
        self.config = ColonyConfig(enabled_genes=["rsi_period"], available_assets=["SOL/USDC"])
        self.owner, self.run, self.worker = [str(uuid4()) for _ in range(3)]

    def proposal(self, strategy_class):
        probes = [candidate(str(uuid4()), score=index / 100) for index in range(100)]
        results = evaluated(probes)
        strategy = strategy_class()
        strategy.initialize(probes, self.config)
        evolution = strategy.evolve(list(reversed(results)), [], self.config)
        children = [str(uuid4()) for _ in probes]
        arguments = {"cohort_member_ids": [probe.probe_id for probe in probes]}
        if strategy.name == "cma_es":
            arguments["distribution_id"] = str(uuid4())
        return strategy, probes, results, evolution, children, arguments

    def command_for_plan(self, plan, retired):
        operations = [{"kind": "retire", "id": source} for source in retired]
        if plan.distribution_operation is not None:
            operations.append(plan.distribution_operation)
        operations.extend({"kind": "birth", "id": lineage.child_id, "cash": "100",
                           "lineage": lineage.to_dict()} for lineage in plan.birth_lineages)
        command = PreparedCommand.batch(self.owner, self.run, self.worker, 1, 2,
                                        operations, version=2)
        self.assertEqual(command.rpc_name, "commit_command")
        self.assertEqual(command.rpc_args["payload"], {"version": 2, "operations": operations})
        self.assertEqual(command.rpc_args["run"], self.run)
        self.assertEqual(command.rpc_args["worker"], self.worker)
        self.assertEqual(command.rpc_args["token"], 1)
        self.assertEqual(command.rpc_args["expected_revision"], 2)
        self.assertLess(len(json.dumps(command.rpc_args["payload"]).encode("utf-8")), 262144)
        self.assertTrue(all("parent_ids" not in item for item in operations))
        # A returned transport dictionary cannot corrupt the retained wire bytes.
        original = command.request
        command.rpc_args["payload"]["operations"].clear()
        self.assertEqual(command.request, original)
        return command

    def assert_raw_maximum_cohort(self, strategy_class):
        strategy, probes, results, evolution, children, arguments = self.proposal(strategy_class)
        original_metadata = deepcopy(evolution.metadata)
        original_parents = deepcopy(evolution.parent_map)
        original_genomes = [genome.to_dict() for genome in evolution.offspring]
        plan = lineage_plan_from_evolution(strategy.name, evolution, list(reversed(results)),
                                           children, **arguments)
        ordered_plan = lineage_plan_from_evolution(strategy.name, evolution, results,
                                                   children, **arguments)
        self.assertEqual(plan, ordered_plan)
        self.assertEqual([item.child_id for item in plan.birth_lineages], children)
        self.assertEqual([item.offspring_index for item in plan.birth_lineages], list(range(100)))
        self.assertEqual(evolution.retire_ids, [probe.probe_id for probe in probes])
        self.assertEqual(evolution.metadata, original_metadata)
        self.assertEqual(evolution.parent_map, original_parents)
        self.assertEqual([genome.to_dict() for genome in evolution.offspring], original_genomes)
        # JSON object ordering is not an ancestry role or donor ordering signal.
        reordered = deepcopy(evolution)
        reordered.metadata = json.loads(json.dumps(reordered.metadata, sort_keys=True))
        self.assertEqual(lineage_plan_from_evolution(strategy.name, reordered, results,
                                                    children, **arguments), plan)
        command = self.command_for_plan(plan, evolution.retire_ids)
        operations = command.rpc_args["payload"]["operations"]
        distributions = [item for item in operations if item["kind"] == "distribution"]
        births = [item for item in operations if item["kind"] == "birth"]
        self.assertEqual(len(births), 100)
        if strategy.name == "cma_es":
            self.assertEqual(len(distributions), 1)
            self.assertEqual(distributions[0]["source_ids"], evolution.retire_ids)
            self.assertEqual(distributions[0]["stage"], "bootstrap")
            self.assertIsNone(distributions[0]["previous_distribution_id"])
            self.assertTrue(all(len(item["lineage"]["sources"]) == 1 for item in births))
            self.assertTrue(all(item["lineage"]["sources"][0]["role"] == "asset_template"
                                for item in births))
            self.assertTrue(all(item["lineage"]["distribution_id"] == distributions[0]["id"]
                                for item in births))
            # All hundred numerical inputs are recorded once, without a false
            # assertion that they were one or two direct genetic parents.
            self.assertTrue(all(item["lineage"]["sources"][0]["source_id"] == probes[-1].probe_id
                                for item in births))
        else:
            self.assertEqual(distributions, [])
            self.assertTrue(all(item["lineage"]["distribution_id"] is None for item in births))

    def test_actual_ga_maximum_cohort_converts_without_rewriting_result(self):
        self.assert_raw_maximum_cohort(GeneticAlgorithmStrategy)

    def test_actual_de_maximum_cohort_converts_with_explicit_role_order(self):
        self.assert_raw_maximum_cohort(DifferentialEvolutionStrategy)

    def test_actual_swarm_maximum_cohort_converts_particle_and_social_sources(self):
        self.assert_raw_maximum_cohort(ParticleSwarmStrategy)

    def test_actual_cma_maximum_cohort_normalizes_distribution_once(self):
        self.assert_raw_maximum_cohort(CMAEvolutionStrategy)

    def test_actual_cma_second_generation_requires_and_preserves_previous_distribution(self):
        strategy, probes, results, evolution, children, arguments = self.proposal(CMAEvolutionStrategy)
        first = lineage_plan_from_evolution(strategy.name, evolution, results, children, **arguments)
        next_probes = [candidate(identity, genome, score=(100 - index) / 100)
                       for index, (identity, genome) in enumerate(zip(children, evolution.offspring))]
        strategy.bind_candidates(next_probes)
        next_results = evaluated(next_probes, "iteration-2", started_at=1120)
        second_evolution = strategy.evolve(list(reversed(next_results)), [], self.config)
        self.assertEqual(second_evolution.metadata["cma_generation"], 1)
        next_children = [str(uuid4()) for _ in next_probes]
        next_arguments = {"cohort_member_ids": children, "distribution_id": str(uuid4())}
        with self.assertRaises(LineageValidationError):
            lineage_plan_from_evolution(strategy.name, second_evolution, next_results,
                                         next_children, **next_arguments)
        next_arguments["previous_distribution_id"] = first.distribution.id
        second = lineage_plan_from_evolution(strategy.name, second_evolution,
                                             list(reversed(next_results)), next_children, **next_arguments)
        self.assertEqual(second.distribution.stage, "update")
        self.assertEqual(second.distribution.previous_distribution_id, first.distribution.id)
        self.assertEqual(second.distribution.source_iteration_id, "iteration-2")
        self.assertEqual(second.distribution.source_ids, tuple(children))
        self.assertTrue(all(item.sources[0].source_id == children[0] for item in second.birth_lineages))
        self.command_for_plan(second, second_evolution.retire_ids)

    def test_swapped_evaluation_ids_are_rejected_for_each_actual_strategy_result(self):
        for strategy_class in STRATEGIES:
            with self.subTest(strategy=strategy_class.name):
                strategy, probes, results, evolution, children, arguments = self.proposal(strategy_class)
                swapped = [replace(member, evaluation_id=results[(index + 1) % len(results)].evaluation_id)
                           for index, member in enumerate(results)]
                with self.assertRaises(LineageValidationError):
                    lineage_plan_from_evolution(strategy.name, evolution, swapped, children, **arguments)


if __name__ == "__main__":
    unittest.main()
