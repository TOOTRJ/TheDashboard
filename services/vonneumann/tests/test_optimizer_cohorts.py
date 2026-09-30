"""Offline cohort identity, terminal accounting, and original CMA ask vectors."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    import numpy as np
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.evaluation import EvaluationCohort
    from vonneumann.core.genome import Genome
    from vonneumann.core.strategies.cma_es import CMAEvolutionStrategy


def candidate(identity: str, *, score=0.0, genome=None):
    return SimpleNamespace(probe_id=identity, genome=genome or Genome(
        assets=['SOL/USDC'], num_assets=1), fitness=score, roi=score, num_trades=0)


def evaluated(probes, iteration='iteration-1'):
    cohort = EvaluationCohort(iteration, probes, 60)
    cohort.start(1000)
    return list(cohort.complete(probes, 1060))


class CohortLedgerTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.probes = [candidate('a'), candidate('b'), candidate('c')]
        self.cohort = EvaluationCohort('cohort-1', self.probes, 120)

    def test_clock_waits_for_explicit_readiness_and_shared_full_horizon(self):
        self.assertEqual(self.cohort.phase, 'warming')
        self.assertFalse(self.cohort.due(99999))
        self.cohort.start(4000)
        self.assertFalse(self.cohort.due(4119.999))
        self.assertTrue(self.cohort.due(4120))
        with self.assertRaises(ValueError):
            self.cohort.complete(self.probes, 4119)
        results = self.cohort.complete(list(reversed(self.probes)), 4120)
        self.assertEqual([result.probe_id for result in results], ['a', 'b', 'c'])
        self.assertTrue(all(result.window_started_at == 4000 and result.window_ends_at == 4120
                            for result in results))
        self.assertEqual(len({result.evaluation_id for result in results}), 3)
        self.assertEqual(self.cohort.to_dict()['completed_count'], 3)

    def test_early_death_remains_in_original_slot_with_frozen_terminal_score(self):
        self.cohort.start(1000)
        self.probes[1].fitness, self.probes[1].roi = -.8, -.2
        early = self.cohort.record_terminal(self.probes[1], 'drawdown', 1030)
        self.probes[1].fitness = 99999
        self.probes[1].genome.rsi_period = 19
        with self.assertRaises(ValueError):
            self.cohort.record_terminal(self.probes[1], 'drawdown', 1031)
        results = self.cohort.complete([self.probes[2], self.probes[0]], 1120)
        self.assertFalse(early.cohort_complete)
        self.assertTrue(results[1].cohort_complete)
        self.assertEqual(results[1].fitness, -.8)
        self.assertEqual(results[1].reason, 'drawdown')
        self.assertEqual(results[1].terminated_at, 1030)
        self.assertEqual(results[1].genome.rsi_period, 14)

    def test_all_dead_batch_waits_until_original_deadline(self):
        self.cohort.start(1000)
        for probe in self.probes:
            self.cohort.record_terminal(probe, 'drawdown', 1010)
        self.assertEqual(self.cohort.phase, 'evaluating')
        with self.assertRaises(ValueError):
            self.cohort.complete([], 1119)
        self.assertEqual(len(self.cohort.complete([], 1120)), 3)

    def test_duplicate_completion_and_foreign_or_missing_members_are_rejected(self):
        self.cohort.start(1000)
        for probes in (self.probes[:2], [*self.probes, self.probes[0]],
                       [*self.probes, candidate('foreign')]):
            with self.subTest(ids=[p.probe_id for p in probes]), self.assertRaises(ValueError):
                self.cohort.complete(probes, 1120)
            self.assertEqual(self.cohort.evaluations, ())
        self.cohort.complete(self.probes, 1120)
        with self.assertRaises(ValueError):
            self.cohort.complete(self.probes, 1120)

    def test_invalid_score_or_changed_genome_cannot_partially_complete_batch(self):
        self.cohort.start(1000)
        self.probes[2].fitness = float('nan')
        with self.assertRaises(ValueError):
            self.cohort.complete(self.probes, 1120)
        self.assertEqual(self.cohort.evaluations, ())
        self.probes[2].fitness = 0
        self.probes[2].genome.rsi_period = 15
        with self.assertRaises(ValueError):
            self.cohort.complete(self.probes, 1120)
        self.assertEqual(self.cohort.evaluations, ())

    def test_result_and_returned_genome_are_detached_from_mutable_probe(self):
        self.cohort.start(1000)
        result = self.cohort.complete(self.probes, 1120)[0]
        with self.assertRaises(FrozenInstanceError):
            result.fitness = 20
        result.genome.rsi_period = 99
        self.probes[0].genome.rsi_period = 100
        self.assertEqual(result.genome.rsi_period, 14)

    def test_abort_records_unscored_members_and_never_produces_complete_batch(self):
        self.cohort.start(1000)
        self.cohort.record_terminal(self.probes[0], 'drawdown', 1010)
        self.cohort.abort('risk_halted', 1030)
        self.assertEqual(self.cohort.phase, 'aborted')
        self.assertEqual(len(self.cohort.evaluations), 3)
        self.assertEqual([e.status for e in self.cohort.evaluations], ['completed', 'aborted', 'aborted'])
        self.assertIsNone(self.cohort.evaluations[1].fitness)
        self.assertEqual(self.cohort.to_dict()['completed_count'], 1)
        self.assertTrue(all(not result.cohort_complete for result in self.cohort.evaluations))
        with self.assertRaises(ValueError):
            self.cohort.complete(self.probes, 1120)
        with self.assertRaises(ValueError):
            self.cohort.abort('stopped', 1121)

    def test_invalid_identity_horizon_and_timestamps_fail_without_advancement(self):
        for ids in ([], [self.probes[0], self.probes[0]]):
            with self.assertRaises(ValueError):
                EvaluationCohort('id', ids, 60)
        for horizon in (0, -1, float('inf'), float('nan'), True):
            with self.assertRaises(ValueError):
                EvaluationCohort('id', self.probes, horizon)
        with self.assertRaises(ValueError):
            self.cohort.record_terminal(self.probes[0], 'drawdown', 0)
        with self.assertRaises(ValueError):
            self.cohort.start(float('inf'))
        self.assertEqual(self.cohort.phase, 'warming')


class RecordingCMA:
    def __init__(self, *, mean, sigma, bounds, population_size):
        self.population_size = population_size
        self.generation = 0
        self.ask_count = 0
        self.tells = []
        self.fail_ask = False
        self.dimension = len(mean)

    def ask(self):
        if self.fail_ask:
            raise RuntimeError('optimizer-failed')
        self.ask_count += 1
        # Unit asks decode to integer phenotypes; reconstructing from those
        # repaired phenotypes cannot substitute for the original ask arrays.
        return np.full(self.dimension, 0.125 + (self.ask_count % 7) / 10)

    def tell(self, solutions):
        self.tells.append([(vector.copy(), score) for vector, score in solutions])
        self.generation += 1


class CMACohortTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.offline_stack.enter_context(patch('vonneumann.core.strategies.cma_es.cmaes_lib.CMA', RecordingCMA))
        self.config = ColonyConfig(enabled_genes=['rsi_period'], available_assets=['SOL/USDC'])
        self.probes = [candidate('a'), candidate('b'), candidate('c')]
        self.strategy = CMAEvolutionStrategy()
        self.strategy.initialize(self.probes, self.config)
        self.optimizer = self.strategy._optimizer

    def ask_next(self):
        result = self.strategy.evolve(evaluated(self.probes), [], self.config)
        return [candidate(f'next-{index}', genome=genome, score=index / 10)
                for index, genome in enumerate(result.offspring)]

    def test_bootstrap_is_not_told_then_original_raw_vectors_match_reordered_dead_results(self):
        following = self.ask_next()
        self.assertEqual(self.optimizer.tells, [])
        raw = [vector.copy() for vector in self.strategy._pending_vectors]
        self.assertTrue(all(not np.array_equal(self.strategy._codec.encode(probe.genome), vector)
                            for probe, vector in zip(following, raw)))
        self.strategy.bind_candidates(following)
        cohort = EvaluationCohort('cohort-asked', following, 60)
        cohort.start(1000)
        cohort.record_terminal(following[1], 'drawdown', 1020)
        results = list(cohort.complete([following[0], following[2]], 1060))
        self.strategy.evolve(list(reversed(results)), [following[1]], self.config)
        self.assertEqual(len(self.optimizer.tells), 1)
        for index, ((vector, score), expected) in enumerate(zip(self.optimizer.tells[0], raw)):
            np.testing.assert_array_equal(vector, expected)
            self.assertEqual(score, -index / 10)

    def test_missing_duplicate_foreign_or_changed_candidates_never_reach_tell(self):
        following = self.ask_next()
        self.strategy.bind_candidates(following)
        results = evaluated(following, 'asked')
        wrong = replace(results[0], probe_id='foreign')
        changed = results[0].genome
        changed.rsi_period += 1
        cases = (results[:-1], [results[0], results[0], results[2]], [wrong, *results[1:]],
                 [replace(results[0], _genome=changed), *results[1:]],
                 [replace(results[0], iteration_id='different'), *results[1:]],
                 [replace(results[0], evaluation_id=results[1].evaluation_id), *results[1:]],
                 [replace(results[0], window_ends_at=2000), *results[1:]],
                 [replace(results[0], window_ends_at=float('nan')), *results[1:]],
                 [replace(results[0], fitness=float('nan')), *results[1:]])
        for batch in cases:
            with self.subTest(batch=batch), self.assertRaises(ValueError):
                self.strategy.evolve(batch, [], self.config)
            self.assertEqual(self.optimizer.tells, [])
        self.strategy.evolve(results, [], self.config)
        self.assertEqual(len(self.optimizer.tells), 1)

    def test_asked_binding_must_be_ordered_complete_unique_and_single_use(self):
        following = self.ask_next()
        following[1].genome.ema_fast += 1
        with self.assertRaises(ValueError):
            self.strategy.bind_candidates(following)
        following[1].genome.ema_fast -= 1
        for batch in (following[:2], [following[0], following[0], following[2]]):
            with self.assertRaises(ValueError):
                self.strategy.bind_candidates(batch)
        self.strategy.bind_candidates(following)
        with self.assertRaises(ValueError):
            self.strategy.bind_candidates(following)

    def test_batch_cannot_be_told_twice_or_unbound(self):
        following = self.ask_next()
        with self.assertRaises(ValueError):
            self.strategy.evolve(evaluated(following), [], self.config)
        self.strategy.bind_candidates(following)
        result = evaluated(following, 'asked')
        self.strategy.evolve(result, [], self.config)
        with self.assertRaises(ValueError):
            self.strategy.evolve(result, [], self.config)
        self.assertEqual(len(self.optimizer.tells), 1)

    def test_abort_discards_pending_asks_and_cannot_tell_old_window(self):
        following = self.ask_next()
        self.strategy.bind_candidates(following)
        cohort = EvaluationCohort('aborted', following, 60)
        cohort.start(1000)
        cohort.abort('paused', 1010)
        with self.assertRaises(ValueError):
            self.strategy.evolve(list(cohort.evaluations), [], self.config)
        self.strategy.abort_cohort()
        self.assertIsNone(self.strategy._optimizer)
        with self.assertRaises(ValueError):
            self.strategy.evolve(evaluated(following), [], self.config)
        self.strategy.initialize(self.probes, self.config)
        self.strategy.bind_candidates(self.probes)  # Bootstrap binding is idempotent.
        self.strategy.evolve(evaluated(self.probes, 'restarted'), [], self.config)
        self.assertEqual(self.optimizer.tells, [])

    def test_all_early_terminal_candidates_cannot_tell_before_deadline_or_after_abort(self):
        following = self.ask_next()
        self.strategy.bind_candidates(following)
        cohort = EvaluationCohort('all-early', following, 60)
        cohort.start(1000)
        for probe in following:
            cohort.record_terminal(probe, 'drawdown', 1010)
        with self.assertRaises(ValueError):
            self.strategy.evolve(list(cohort.evaluations), [], self.config)
        self.assertEqual(self.optimizer.tells, [])
        cohort.abort('risk_halted', 1020)
        with self.assertRaises(ValueError):
            self.strategy.evolve(list(cohort.evaluations), [], self.config)
        self.assertEqual(self.optimizer.tells, [])

    def test_failed_next_ask_cannot_rebind_consumed_vectors_or_repeat_tell(self):
        following = self.ask_next()
        self.strategy.bind_candidates(following)
        self.optimizer.fail_ask = True
        with self.assertRaises(RuntimeError):
            self.strategy.evolve(evaluated(following), [], self.config)
        self.assertEqual(len(self.optimizer.tells), 1)
        with self.assertRaises(ValueError):
            self.strategy.bind_candidates(following)
        with self.assertRaises(ValueError):
            self.strategy.evolve(evaluated(following), [], self.config)
        self.assertEqual(len(self.optimizer.tells), 1)

    def test_raw_probe_objects_cannot_bypass_cohort_completion(self):
        with self.assertRaises(ValueError):
            self.strategy.evolve(self.probes, [], self.config)
        self.assertEqual(self.optimizer.ask_count, 0)


class ActualCMACohortTests(OfflineTestMixin, unittest.TestCase):
    def test_actual_library_retains_population_after_one_early_death_each_iteration(self):
        config = ColonyConfig(enabled_genes=['rsi_period', 'ema_fast'], available_assets=['SOL/USDC'])
        probes = [candidate(f'initial-{i}') for i in range(4)]
        strategy = CMAEvolutionStrategy()
        strategy.initialize(probes, config)
        for iteration in range(5):
            cohort = EvaluationCohort(f'actual-{iteration}', probes, 60)
            cohort.start(1000 + iteration * 60)
            probes[0].fitness, probes[0].roi = -.6, -.2
            cohort.record_terminal(probes[0], 'drawdown', 1010 + iteration * 60)
            results = cohort.complete(probes[1:], 1060 + iteration * 60)
            offspring = strategy.evolve(list(results), [], config).offspring
            self.assertEqual(len(offspring), 4)
            self.assertEqual(strategy._optimizer.generation, iteration)
            probes = [candidate(f'{iteration}-next-{i}', genome=genome)
                      for i, genome in enumerate(offspring)]
            strategy.bind_candidates(probes)


if __name__ == '__main__':
    unittest.main()
