"""Offline selection proofs: bounded GA and same-window paired DE."""

from copy import deepcopy
from dataclasses import replace
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.evaluation import EvaluationCohort
    from vonneumann.core.genome import AVAILABLE_ASSETS, Genome
    from vonneumann.core.strategies.cohort_contract import candidate_signature
    from vonneumann.core.strategies.genetic_algorithm import GeneticAlgorithmStrategy, crossover
    from vonneumann.core.strategies.differential_evolution import DifferentialEvolutionStrategy, _de_trial


def candidate(identity, score=0., genome=None):
    return SimpleNamespace(probe_id=identity, genome=genome or Genome(
        assets=['SOL/USDC'], num_assets=1), fitness=score, roi=score, num_trades=0)


def completed(probes, iteration='bootstrap', start=1000):
    cohort = EvaluationCohort(iteration, probes, 60)
    cohort.start(start)
    return list(cohort.complete(probes, start + 60))


def next_members(result, prefix='next', scores=None):
    return [candidate(f'{prefix}-{i}', (scores or [0.] * len(result.offspring))[i], genome)
            for i, genome in enumerate(result.offspring)]


def phenotype(genome):
    result = candidate_signature(genome)
    result.pop('generation')
    return result


class SelectionTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.config = ColonyConfig(enabled_genes=['volume_threshold'],
                                   available_assets=['SOL/USDC'], mutation_rate=0)

    def setup_strategy(self, kind, count=None, scores=None):
        count = count or (2 if kind is GeneticAlgorithmStrategy else 8)
        probes = [candidate(f'initial-{i}', (scores or [0.] * count)[i],
                            Genome(assets=['SOL/USDC'], num_assets=1,
                                   volume_threshold=1.1 + i / 10)) for i in range(count)]
        strategy = kind()
        strategy.initialize(probes, self.config)
        strategy.bind_candidates(probes)
        return strategy, probes

    def test_ga_small_odd_and_even_populations_include_negative_and_no_trade_windows(self):
        for size in (2, 3, 4, 7):
            with self.subTest(size=size):
                strategy, probes = self.setup_strategy(GeneticAlgorithmStrategy, size,
                                                       [-.1 * i for i in range(size)])
                result = strategy.evolve(completed(probes), [], self.config)
                self.assertEqual(len(result.offspring), size)
                self.assertEqual(set(result.retire_ids), {p.probe_id for p in probes})
                self.assertEqual(set(result.parent_map), {str(i) for i in range(size)})
                self.assertTrue(all(set(ids) <= set(result.retire_ids)
                                    for ids in result.parent_map.values()))

    def test_ga_tournament_prefers_best_negative_score_and_asexual_lineage_is_one_parent(self):
        strategy, probes = self.setup_strategy(GeneticAlgorithmStrategy, 3, [-5., -1., -3.])
        with patch.object(strategy._rng, 'random', return_value=0):
            result = strategy.evolve(completed(probes), [], self.config)
        self.assertEqual(list(result.parent_map.values()), [['initial-1']] * 3)
        self.assertTrue(all(phenotype(g) == phenotype(probes[1].genome) for g in result.offspring))
        self.assertTrue(all(x['operation'] == 'clone_mutation' for x in result.metadata['offspring']))

    def test_ga_crossover_lineage_names_both_actual_parents(self):
        strategy, probes = self.setup_strategy(GeneticAlgorithmStrategy)
        with patch.object(strategy._rng, 'random', return_value=.99):
            result = strategy.evolve(completed(probes), [], self.config)
        self.assertTrue(all(set(ids) == {'initial-0', 'initial-1'} for ids in result.parent_map.values()))
        self.assertTrue(all(x['operation'] == 'crossover_mutation' for x in result.metadata['offspring']))

    def test_ga_asset_union_preserves_parent_order_before_sampling(self):
        seen = []
        def sample(population, count):
            seen.append(list(population))
            return list(population)[:count]
        first, second, third = AVAILABLE_ASSETS[:3]
        a = Genome(assets=[first, second], num_assets=2)
        b = Genome(assets=[second, third], num_assets=2)
        rng = random.Random(0)
        with patch.object(rng, 'sample', side_effect=sample):
            crossover(a, b, 1, rng=rng)
        self.assertEqual(seen[:2], [[first, second, third]] * 2)

    def test_de_rejects_insufficient_or_odd_actual_account_capacity(self):
        for size in (0, 2, 4, 6, 7, 9):
            with self.subTest(size=size), self.assertRaises(ValueError):
                DifferentialEvolutionStrategy().initialize([candidate(str(i)) for i in range(size)], self.config)

    def test_de_bootstrap_keeps_best_half_but_returns_constant_funded_account_count(self):
        strategy, probes = self.setup_strategy(DifferentialEvolutionStrategy,
                                               scores=[-8., -7., -6., -5., -4., -3., -2., -1.])
        result = strategy.evolve(list(reversed(completed(probes))), [], self.config)
        self.assertEqual(result.metadata['selected_ids'], ['initial-7', 'initial-6', 'initial-5', 'initial-4'])
        self.assertEqual(len(result.offspring), 8)
        self.assertEqual(len(result.retire_ids), 8)
        for i, identity in enumerate(result.metadata['selected_ids']):
            self.assertEqual(result.parent_map[str(i)], [identity])
            self.assertEqual(phenotype(result.offspring[i]), phenotype(probes[int(identity[-1])].genome))
            self.assertEqual(set(result.parent_map[str(i + 4)]), set(result.metadata['selected_ids']))

    def test_de_pair_comparison_uses_current_window_only_with_ties_retaining_target(self):
        strategy, probes = self.setup_strategy(DifferentialEvolutionStrategy,
                                               scores=[0., 0., 0., 0., 100., 100., 100., 100.])
        first = strategy.evolve(completed(probes), [], self.config)
        following = next_members(first, scores=[-.2, -.2, 0., 1., -.1, -.3, 0., .5])
        strategy.bind_candidates(following)
        second = strategy.evolve(list(reversed(completed(following, 'paired', 1060))), [], self.config)
        winners = ['next-4', 'next-1', 'next-2', 'next-3']
        self.assertEqual(second.metadata['selected_ids'], winners)
        self.assertEqual([p['accepted_trial'] for p in second.metadata['pair_selections']],
                         [True, False, False, False])
        for i, winner in enumerate(winners):
            self.assertEqual(second.parent_map[str(i)], [winner])
            self.assertEqual(set(second.parent_map[str(i + 4)]), set(winners))
            role = second.metadata['next_pairs'][i]
            self.assertEqual(role['trial_contributors']['target'], winner)
            self.assertEqual(set(role['trial_contributors'].values()), set(winners))
            self.assertEqual(len(set(role['trial_contributors'].values())), 4)

    def test_de_early_dead_trials_are_compared_at_shared_deadline_and_cannot_be_donors_when_worse(self):
        strategy, probes = self.setup_strategy(DifferentialEvolutionStrategy)
        first = strategy.evolve(completed(probes), [], self.config)
        following = next_members(first)
        strategy.bind_candidates(following)
        cohort = EvaluationCohort('paired-deaths', following, 60)
        cohort.start(1060)
        for probe in following[4:]:
            probe.fitness, probe.roi = -1., -.5
            cohort.record_terminal(probe, 'drawdown', 1070)
        result = strategy.evolve(list(cohort.complete(following[:4], 1120)), [], self.config)
        self.assertEqual(result.metadata['selected_ids'], [p.probe_id for p in following[:4]])
        self.assertTrue(all(not pair['accepted_trial'] for pair in result.metadata['pair_selections']))
        self.assertTrue(all(set(ids) <= {p.probe_id for p in following[:4]}
                            for ids in result.parent_map.values()))

    def test_de_forced_donor_uses_active_dimension_even_with_zero_crossover_probability(self):
        target, a, b, c = [Genome(assets=['SOL/USDC'], num_assets=1, volume_threshold=x)
                           for x in (1., 2., 3., 2.)]
        trial = _de_trial(target, a, b, c, .5, 0., self.config)
        self.assertEqual(trial.volume_threshold, 2.5)
        expected = phenotype(target)
        expected['volume_threshold'] = 2.5
        self.assertEqual(phenotype(trial), expected)

    def test_no_active_genes_are_bounded_clones_with_truthful_ancestry(self):
        config = ColonyConfig(enabled_genes=[])
        for kind in (GeneticAlgorithmStrategy, DifferentialEvolutionStrategy):
            with self.subTest(strategy=kind.__name__):
                strategy, probes = self.setup_strategy(kind)
                result = strategy.evolve(completed(probes), [], config)
                self.assertEqual(len(result.offspring), len(probes))
                by_id = {p.probe_id: p for p in probes}
                for index, child in enumerate(result.offspring):
                    parent_ids = result.parent_map[str(index)]
                    self.assertEqual(len(parent_ids), 1)
                    self.assertEqual(phenotype(child), phenotype(by_id[parent_ids[0]].genome))
                following = next_members(result)
                strategy.bind_candidates(following)
                next_result = strategy.evolve(completed(following, 'next', 1060), [], config)
                self.assertEqual(len(next_result.offspring), len(probes))
                if kind is DifferentialEvolutionStrategy:
                    self.assertTrue(all(not pair['accepted_trial']
                                        for pair in next_result.metadata['pair_selections']))

    def test_de_non_evolvable_coupled_gene_repair_reverts_instead_of_changing_fixed_control(self):
        config = ColonyConfig(enabled_genes=['rsi_oversold'])
        target = Genome(assets=['SOL/USDC'], num_assets=1, rsi_oversold=30, rsi_overbought=40)
        donors = [deepcopy(target) for _ in range(3)]
        donors[0].rsi_oversold = 40
        operations = []
        trial = _de_trial(target, *donors, .8, 1., config, operations=operations)
        self.assertEqual(phenotype(trial), phenotype(target))
        self.assertEqual(operations, ['fixed_repair_clone'])

    def test_invalid_or_mixed_evidence_rejected_atomically_for_both_algorithms(self):
        for kind in (GeneticAlgorithmStrategy, DifferentialEvolutionStrategy):
            strategy, probes = self.setup_strategy(kind)
            results = completed(probes)
            changed = results[0].genome
            changed.generation += 1
            cases = [results[:-1], [results[0], *results[:-1]], probes]
            for edits in ({'probe_id': 'foreign'}, {'fitness': float('nan')}, {'roi': float('inf')},
                          {'num_trades': -1}, {'num_trades': True}, {'cohort_complete': False},
                          {'status': 'aborted'}, {'iteration_id': 'other'}, {'window_started_at': 999},
                          {'window_ends_at': 1200}, {'evaluation_id': results[1].evaluation_id},
                          {'_genome': changed}, {'terminated_at': 900}):
                cases.append([replace(results[0], **edits), *results[1:]])
            for batch in cases:
                with self.subTest(strategy=kind.__name__, batch=batch), self.assertRaises(ValueError):
                    strategy.evolve(batch, [], self.config)
                self.assertFalse(strategy._cohort.awaiting_bind)
            self.assertEqual(len(strategy.evolve(results, [], self.config).offspring), len(probes))

    def test_binding_enforces_pending_order_generation_and_fresh_ids_but_allows_assigned_lineage(self):
        strategy, probes = self.setup_strategy(DifferentialEvolutionStrategy,
                                               scores=list(range(8)))
        first = strategy.evolve(completed(probes), [], self.config)
        following = next_members(first)
        cases = [following[:-1], [following[0], *following[:-1]],
                 [following[1], following[0], *following[2:]]]
        for batch in cases:
            with self.subTest(ids=[p.probe_id for p in batch]), self.assertRaises(ValueError):
                strategy.bind_candidates(batch)
            self.assertTrue(strategy._cohort.awaiting_bind)
        for change in ('generation', 'ema_fast'):
            setattr(following[0].genome, change, getattr(following[0].genome, change) + 1)
            with self.assertRaises(ValueError):
                strategy.bind_candidates(following)
            setattr(following[0].genome, change, getattr(following[0].genome, change) - 1)
        following[0].probe_id = probes[0].probe_id
        with self.assertRaises(ValueError):
            strategy.bind_candidates(following)
        following[0].probe_id = 'next-0'
        for probe in following:
            probe.genome.parent_ids = ['controller-assigned-ancestry']
        strategy.bind_candidates(following)
        with self.assertRaises(ValueError):
            strategy.bind_candidates(following)
        strategy.evolve(completed(following, 'paired', 1060), [], self.config)

    def test_unbound_double_initialize_reused_context_and_abort_cannot_bypass_contract(self):
        for kind in (GeneticAlgorithmStrategy, DifferentialEvolutionStrategy):
            with self.subTest(strategy=kind.__name__):
                strategy, probes = self.setup_strategy(kind)
                first = strategy.evolve(completed(probes), [], self.config)
                following = next_members(first)
                with self.assertRaises(ValueError):
                    strategy.initialize(following, self.config)
                with self.assertRaises(ValueError):
                    strategy.evolve(completed(following, 'next', 1060), [], self.config)
                strategy.bind_candidates(following)
                for iteration, start in [('bootstrap', 1060), ('next', 1000)]:
                    with self.assertRaises(ValueError):
                        strategy.evolve(completed(following, iteration, start), [], self.config)
                strategy.abort_cohort()
                with self.assertRaises(ValueError):
                    strategy.evolve(completed(following, 'next', 1060), [], self.config)
                strategy.initialize(following, self.config)
                strategy.bind_candidates(following)
                strategy.evolve(completed(following, 'restarted', 1120), [], self.config)

    def test_de_known_quadratic_objective_retains_best_and_converges_without_trading_network(self):
        strategy, probes = self.setup_strategy(DifferentialEvolutionStrategy, count=20)
        strategy._rng.seed(107)
        strategy.F = .5
        errors = []
        for generation in range(30):
            for probe in probes:
                probe.fitness = -(probe.genome.volume_threshold - 2.123) ** 2
                probe.roi = probe.fitness
            errors.append(-max(p.fitness for p in probes))
            result = strategy.evolve(completed(probes, f'objective-{generation}', 1000 + 60 * generation),
                                     [], self.config)
            probes = next_members(result, f'g{generation + 1}')
            strategy.bind_candidates(probes)
        self.assertTrue(all(after <= before for before, after in zip(errors, errors[1:])))
        self.assertLess(errors[-1], 1e-6)


if __name__ == '__main__':
    unittest.main()
