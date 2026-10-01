"""Real optimizer forks retain deterministic state without sharing mutations."""

from copy import deepcopy
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    import numpy as np
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.evaluation import EvaluationCohort
    from vonneumann.core.genome import Genome
    from vonneumann.core.search_random import SearchRandomStreams
    from vonneumann.core.strategy_fork import StrategyForkError, fork_evaluation, fork_strategy
    from vonneumann.core.strategies.cma_es import CMAEvolutionStrategy, cmaes_lib
    from vonneumann.core.strategies.differential_evolution import DifferentialEvolutionStrategy
    from vonneumann.core.strategies.genetic_algorithm import GeneticAlgorithmStrategy
    from vonneumann.core.strategies.particle_swarm import ParticleSwarmStrategy


KINDS = (GeneticAlgorithmStrategy, DifferentialEvolutionStrategy, ParticleSwarmStrategy, CMAEvolutionStrategy)


def identity(number):
    return str(UUID(int=number))


def probe(number, score=0., genome=None):
    return SimpleNamespace(probe_id=identity(number), fitness=score, roi=score, num_trades=0,
                           genome=genome or Genome(assets=["SOL/USDC"], num_assets=1,
                                                   rsi_oversold=25 + number % 8,
                                                   volume_threshold=1 + (number % 8) / 10))


def evaluated(probes, iteration=0):
    cohort = EvaluationCohort(f"fork-run:{iteration}", probes, 60)
    cohort.start(1000 + iteration * 60)
    return list(cohort.complete(probes, 1060 + iteration * 60))


def state(value):
    """Exact local comparison, including byte representation and RNG caches."""
    kind = type(value)
    if value is None or kind in (str, bool, int, float):
        return value
    if kind is np.float64:
        return "numpy-scalar", value.tobytes()
    if kind is np.ndarray:
        return "array", value.dtype.str, value.shape, value.tobytes()
    if kind is random.Random:
        return "python-rng", value.getstate()
    if kind is np.random.RandomState:
        return "numpy-rng", state(value.get_state())
    if kind in (list, tuple):
        return kind, tuple(state(item) for item in value)
    if kind is dict:
        return tuple((key, state(item)) for key, item in value.items())
    return kind, state(value.__dict__)


def result_state(result):
    return ([genome.to_dict() for genome in result.offspring], result.retire_ids,
            result.parent_map, result.metadata)


class StrategyForkTests(OfflineTestMixin, unittest.TestCase):
    def setup_strategy(self, kind, *, fixed=False):
        config = ColonyConfig(enabled_genes=[] if fixed else ["rsi_oversold", "volume_threshold"],
                              available_assets=["SOL/USDC"], mutation_rate=.3)
        members = [probe(i + 1, float(i)) for i in range(8)]
        for member in members:
            member.genome.validate(config)
        strategy = kind()
        strategy.configure_search(SearchRandomStreams("18446744073709551615", strategy.name), epoch=3)
        strategy.initialize(members, config)
        if kind is not CMAEvolutionStrategy:
            strategy.bind_candidates(members)
        return strategy, config, members

    def test_all_real_strategies_fork_deterministically_through_four_generations(self):
        for kind in KINDS:
            with self.subTest(strategy=kind.__name__):
                source, config, members = self.setup_strategy(kind)
                branch = fork_strategy(source)
                for generation in range(4):
                    observations = evaluated(members, generation)
                    before = state(source)
                    staged = branch.evolve(list(reversed(observations)), [], config)
                    self.assertEqual(state(source), before)
                    committed = source.evolve(observations, [], config)
                    self.assertEqual(result_state(staged), result_state(committed))
                    self.assertEqual(state(branch), state(source))
                    # Fork while a proposal is waiting for its fresh accounts.
                    branch = fork_strategy(branch)
                    next_members = [probe(100 * (generation + 1) + i, float(7 - i), deepcopy(genome))
                                    for i, genome in enumerate(committed.offspring)]
                    for optimizer in (source, branch):
                        if kind is ParticleSwarmStrategy:
                            for i, member in enumerate(next_members):
                                optimizer.remap_probe_id(committed.parent_map[str(i)][0], member.probe_id)
                        optimizer.bind_candidates(deepcopy(next_members))
                    self.assertEqual(state(source), state(branch))
                    members = next_members

    def test_all_strategies_support_fixed_and_aborted_forks(self):
        for kind in KINDS:
            with self.subTest(strategy=kind.__name__):
                source, config, members = self.setup_strategy(kind, fixed=True)
                branch = fork_strategy(source)
                observations = evaluated(members)
                self.assertEqual(result_state(source.evolve(observations, [], config)),
                                 result_state(branch.evolve(observations, [], config)))
                source.abort_cohort()
                branch = fork_strategy(source)
                self.assertEqual(state(source), state(branch))

    def test_pending_and_nested_branch_mutation_cannot_change_source_or_sibling(self):
        for kind in KINDS:
            with self.subTest(strategy=kind.__name__):
                source, config, members = self.setup_strategy(kind)
                source.evolve(evaluated(members), [], config)
                branch, sibling = fork_strategy(source), fork_strategy(source)
                expected = state(source)
                branch._rng.random()
                branch._search_streams.seed = "17"
                branch._search_epoch += 1
                branch._mutation_event += 1
                if kind is CMAEvolutionStrategy:
                    branch._optimizer._mean[0] = .123
                    branch._optimizer._C[0, 0] = 9
                    branch._optimizer._rng.normal()
                    branch._pending_vectors[0][0] = .456
                    branch._pending_genomes[0].assets.append("JUP/USDC")
                else:
                    branch._cohort._pending[0]["assets"].append("JUP/USDC")
                if kind is ParticleSwarmStrategy:
                    first = next(iter(branch._velocities))
                    branch._velocities[first]["volume_threshold"] = 999
                    branch._personal_best[first][0]["assets"].append("JUP/USDC")
                    branch._global_best[0]["assets"].append("JUP/USDC")
                if getattr(branch, "_codec", None) is not None:
                    branch._codec._config.enabled_genes.clear()
                    branch._codec._assets.append("JUP/USDC")
                self.assertEqual(state(source), expected)
                self.assertEqual(state(sibling), expected)

    def test_python_and_numpy_gaussian_caches_are_preserved(self):
        source, _, _ = self.setup_strategy(CMAEvolutionStrategy)
        source._rng.gauss(0, 1)
        source._optimizer._rng.normal()
        self.assertIsNotNone(source._rng.getstate()[2])
        self.assertEqual(source._optimizer._rng.get_state()[3], 1)
        branch = fork_strategy(source)
        self.assertEqual([source._rng.gauss(0, 1) for _ in range(17)],
                         [branch._rng.gauss(0, 1) for _ in range(17)])
        np.testing.assert_array_equal(source._optimizer._rng.normal(size=17),
                                      branch._optimizer._rng.normal(size=17))

    def test_mutable_resource_and_nonfinite_python_rng_cache_is_rejected(self):
        for cache in ([], {}, lambda: None, object(), float("nan"), float("inf"), 0, True):
            with self.subTest(cache_type=type(cache)):
                source, _, _ = self.setup_strategy(GeneticAlgorithmStrategy)
                source._rng.gauss_next = cache
                with self.assertRaises(StrategyForkError):
                    fork_strategy(source)
                with self.assertRaises(StrategyForkError):
                    fork_strategy(source, memo={id(source._rng): random.Random(0)})
                self.assertIs(source._rng.gauss_next, cache)

    def test_cma_fork_bypasses_lossy_deepcopy_hooks_and_preserves_next_asks(self):
        source, _, _ = self.setup_strategy(CMAEvolutionStrategy)
        source._optimizer.ask()
        naive = deepcopy(source._optimizer)
        self.assertNotEqual(state(source._optimizer._rng), state(naive._rng))
        with patch.object(cmaes_lib.CMA, "__getstate__", side_effect=AssertionError("serialization used")), \
             patch.object(cmaes_lib.CMA, "__setstate__", side_effect=AssertionError("serialization used")), \
             patch.object(cmaes_lib.CMA, "__init__", side_effect=AssertionError("constructor used")), \
             patch.object(CMAEvolutionStrategy, "initialize", side_effect=AssertionError("initialize used")), \
             patch.object(CMAEvolutionStrategy, "configure_search", side_effect=AssertionError("reset used")):
            branch = fork_strategy(source)
        for _ in range(12):
            np.testing.assert_array_equal(source._optimizer.ask(), branch._optimizer.ask())
        for name, value in source._optimizer.__dict__.items():
            if type(value) is np.ndarray:
                self.assertFalse(np.shares_memory(value, branch._optimizer.__dict__[name]), name)

    def test_failed_cma_branch_does_not_consume_source_cohort_or_randomness(self):
        source, config, members = self.setup_strategy(CMAEvolutionStrategy)
        observations = evaluated(members)
        branch = fork_strategy(source)
        before = state(source)
        with patch.object(branch._optimizer, "ask", side_effect=RuntimeError("candidate failure")):
            with self.assertRaisesRegex(RuntimeError, "candidate failure"):
                branch.evolve(observations, [], config)
        self.assertEqual(state(source), before)
        retry = fork_strategy(source)
        self.assertEqual(result_state(retry.evolve(observations, [], config)),
                         result_state(source.evolve(observations, [], config)))

    def test_shared_aliases_are_preserved_but_array_views_fail_explicitly(self):
        source, _, _ = self.setup_strategy(CMAEvolutionStrategy)
        source._optimizer._B = source._optimizer._C
        branch = fork_strategy(source)
        self.assertIs(branch._optimizer._B, branch._optimizer._C)
        self.assertIsNot(branch._optimizer._C, source._optimizer._C)
        source._optimizer._B = source._optimizer._C.view()
        with self.assertRaisesRegex(StrategyForkError, "overlapping"):
            fork_strategy(source)
        with self.assertRaisesRegex(StrategyForkError, "overlapping"):
            fork_strategy(source, memo={id(source._optimizer._C): source._optimizer._C.copy()})

    def test_unknown_classes_fields_resources_and_solver_versions_fail_closed(self):
        class Unsupported(GeneticAlgorithmStrategy):
            pass
        with self.assertRaises(StrategyForkError):
            fork_strategy(Unsupported())
        source, _, _ = self.setup_strategy(ParticleSwarmStrategy)
        source.transport = object()
        with self.assertRaises(StrategyForkError):
            fork_strategy(source)
        del source.transport
        source._personal_best["resource"] = lambda: None
        with self.assertRaises(StrategyForkError):
            fork_strategy(source)
        source, _, _ = self.setup_strategy(CMAEvolutionStrategy)
        with patch.object(cmaes_lib, "__version__", "future-version"):
            with self.assertRaises(StrategyForkError):
                fork_strategy(source)
        source._optimizer._mean = np.array([object()], dtype=object)
        with self.assertRaises(StrategyForkError):
            fork_strategy(source)

    def test_numeric_array_metadata_cannot_carry_a_shared_resource(self):
        source, _, _ = self.setup_strategy(CMAEvolutionStrategy)
        resource = []
        vector = np.array([.5], dtype=np.dtype("float64", metadata={"resource": resource}))
        source._pending_vectors = [vector]
        with self.assertRaises(StrategyForkError):
            fork_strategy(source)
        with self.assertRaises(StrategyForkError):
            fork_strategy(source, memo={id(vector): vector.copy()})
        self.assertEqual(resource, [])

    def test_shared_internal_memo_reuses_only_equivalent_detached_owned_state(self):
        source, _, _ = self.setup_strategy(ParticleSwarmStrategy)
        streams = deepcopy(source._search_streams)
        config = deepcopy(source._codec._config)
        memo = {id(source._search_streams): streams, id(source._codec._config): config}
        branch = fork_strategy(source, memo=memo)
        self.assertIs(branch._search_streams, streams)
        self.assertIs(branch._codec._config, config)
        self.assertIs(fork_strategy(source, memo=memo), branch)
        for invalid in (source._search_streams, object(), SearchRandomStreams("17", source.name)):
            with self.subTest(invalid=type(invalid)), self.assertRaises(StrategyForkError):
                fork_strategy(source, memo={id(source._search_streams): invalid})
        invalid_config = deepcopy(source._codec._config)
        invalid_config.enabled_genes = source._codec._config.enabled_genes
        with self.assertRaises(StrategyForkError):
            fork_strategy(source, memo={id(source._codec._config): invalid_config})
        source._personal_best["alias"] = source._personal_best[next(iter(source._personal_best))]
        aliased = source._personal_best
        split = {key: deepcopy(value) for key, value in aliased.items()}
        with self.assertRaises(StrategyForkError):
            fork_strategy(source, memo={id(aliased): split})


class EvaluationForkTests(OfflineTestMixin, unittest.TestCase):
    def test_all_phases_are_copied_without_running_the_constructor(self):
        for phase in ("warming", "evaluating", "completed", "aborted"):
            with self.subTest(phase=phase):
                probes = [probe(i) for i in range(1, 4)]
                source = EvaluationCohort("iteration", probes, 60)
                if phase != "warming":
                    source.start(1000)
                    source.record_terminal(probes[0], "drawdown", 1010)
                if phase == "completed":
                    source.complete(probes[1:], 1060)
                elif phase == "aborted":
                    source.abort("paused", 1020)
                with patch.object(EvaluationCohort, "__init__", side_effect=AssertionError("constructor used")):
                    branch = fork_evaluation(source)
                self.assertEqual(state(source), state(branch))
                before = state(source)
                branch._genomes[probes[0].probe_id].assets.append("JUP/USDC")
                if branch.evaluations:
                    branch.evaluations[0]._genome.assets.append("BONK/USDC")
                self.assertEqual(state(source), before)

    def test_staged_completion_and_abort_leave_original_partial_window_unchanged(self):
        probes = [probe(i) for i in range(1, 4)]
        source = EvaluationCohort("iteration", probes, 60)
        source.start(1000)
        source.record_terminal(probes[0], "drawdown", 1010)
        completed, aborted = fork_evaluation(source), fork_evaluation(source)
        before = state(source)
        completed.complete(probes[1:], 1060)
        aborted.abort("paused", 1020)
        self.assertEqual(state(source), before)
        self.assertEqual(source.phase, "evaluating")
        self.assertFalse(source.evaluations[0].cohort_complete)
        self.assertTrue(all(result.cohort_complete for result in completed.evaluations))
        self.assertEqual(aborted.phase, "aborted")

    def test_evaluation_internal_genome_aliases_and_root_memo_are_preserved(self):
        probes = [probe(i) for i in range(1, 3)]
        source = EvaluationCohort("iteration", probes, 60)
        source.start(1000)
        terminal = source.record_terminal(probes[0], "drawdown", 1010)
        genome = source._genomes[probes[0].probe_id]
        terminal.__dict__["_genome"] = genome  # Exercise a valid shared local data alias.
        root_copy = deepcopy(genome)
        branch = fork_evaluation(source, memo={id(genome): root_copy})
        self.assertIs(branch._genomes[probes[0].probe_id], root_copy)
        self.assertIs(branch.evaluations[0]._genome, root_copy)
        self.assertIsNot(branch.evaluations[0], terminal)


if __name__ == "__main__":
    unittest.main()
