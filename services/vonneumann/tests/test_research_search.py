"""Budget, information-boundary and selection checks for finite EMA search."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
import random
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.search_random import SearchRandomStreams
    from vonneumann.research.search import search_grid


GRID = tuple((fast, slow) for fast in (3, 5, 8, 12) for slow in (15, 20, 30, 45, 60))
IDS = tuple(f'ema-{fast:02d}-{slow:02d}' for fast, slow in GRID)
GENES = dict(zip(IDS, GRID))
# An irregular score table, including losses, avoids accidentally testing only
# "larger EMA is better" or ranking by candidate identifier.
SCORES = {ident: float(((index * 11) % 23) - 17) / 10 for index, ident in enumerate(IDS)}


class ResearchSearchTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        state = random.getstate()
        self.addCleanup(random.setstate, state)

    def run_search(self, *, algorithm='ga', seed='0', budget=20, scores=None, grid=GRID):
        scores = SCORES if scores is None else scores
        calls = []

        def evaluate(ident):
            calls.append(ident)
            self.assertIn(ident, scores, 'Search requested a candidate outside the finite domain')
            return scores[ident]

        result = search_grid(grid, seed=seed, budget=budget, algorithm=algorithm, evaluate=evaluate)
        return result, calls

    def assert_budget_and_best_seen(self, result, calls, scores):
        budget = result['budget']
        self.assertEqual(len(calls), budget)
        self.assertEqual(result['trial_ids'], calls)
        self.assertEqual(len(result['trials']), budget)
        self.assertEqual(len(result['best_by_budget']), budget)
        self.assertEqual(result['score_cache_hits'], budget)
        self.assertEqual(result['additional_computed_evaluations'], 0)
        seen = set()
        for index, (ident, trial, best) in enumerate(zip(calls, result['trials'], result['best_by_budget']), 1):
            self.assertEqual(trial['budget'], index)
            self.assertEqual(trial['candidate_id'], ident)
            self.assertEqual(trial['fitness'], scores[ident])
            self.assertIs(trial['duplicate'], ident in seen)
            seen.add(ident)
            winner = min(seen, key=lambda candidate: (-scores[candidate], candidate))
            self.assertEqual(best, dict(budget=index, winner=winner, fitness=scores[winner],
                                       unique_trials=len(seen), duplicate_trials=index - len(seen)))
        self.assertEqual(result['winner'], min(seen, key=lambda candidate: (-scores[candidate], candidate)))
        self.assertEqual(result['unique_trials'], len(seen))
        self.assertEqual(result['duplicate_trials'], budget - len(seen))

    def test_both_algorithms_share_private_seeded_initialization_and_exact_budgets(self):
        for seed in ('0', '97', '18446744073709551615'):
            expected = list(IDS)
            SearchRandomStreams(seed, 'ema_grid_random').rng('grid-permutation').shuffle(expected)
            for budget in (1, 2, 3, 4, 5, 11, 20):
                results = {}
                for algorithm in ('random', 'ga'):
                    with self.subTest(seed=seed, budget=budget, algorithm=algorithm):
                        result, calls = self.run_search(algorithm=algorithm, seed=seed, budget=budget)
                        self.assertEqual(result['algorithm'], algorithm)
                        self.assertEqual(result['seed'], seed)
                        self.assertEqual(result['budget'], budget)
                        self.assertEqual(result['order'], expected)
                        self.assert_budget_and_best_seen(result, calls, SCORES)
                        results[algorithm] = result
                shared = min(4, budget)
                self.assertEqual(results['random']['trial_ids'][:shared], results['ga']['trial_ids'][:shared])
                self.assertEqual(results['random']['trial_ids'], expected[:budget])

    def test_every_budget_is_an_identical_prefix_of_the_same_search(self):
        for algorithm in ('random', 'ga'):
            for seed in ('0', '13'):
                full, _ = self.run_search(algorithm=algorithm, seed=seed)
                for budget in range(1, 21):
                    with self.subTest(algorithm=algorithm, seed=seed, budget=budget):
                        partial, calls = self.run_search(algorithm=algorithm, seed=seed, budget=budget)
                        self.assertEqual(partial['order'], full['order'])
                        self.assertEqual(partial['trial_ids'], full['trial_ids'][:budget])
                        self.assertEqual(partial['trials'], full['trials'][:budget])
                        self.assertEqual(partial['best_by_budget'], full['best_by_budget'][:budget])
                        self.assert_budget_and_best_seen(partial, calls, SCORES)

    def test_ga_repeated_candidates_are_evaluated_again_and_consume_request_budget(self):
        repeats = 0
        for seed in map(str, range(8)):
            result, calls = self.run_search(seed=seed)
            self.assert_budget_and_best_seen(result, calls, SCORES)
            repeats += result['duplicate_trials']
            self.assertEqual(sum(count - 1 for count in Counter(calls).values()), result['duplicate_trials'])
        self.assertGreater(repeats, 0, 'Fixtures must actually exercise repeated GA candidates')
        result, calls = self.run_search(algorithm='random')
        self.assertEqual(len(set(calls)), 20)
        self.assertEqual(result['duplicate_trials'], 0)

    def test_ga_parents_come_from_completed_population_and_mutations_change_valid_levels(self):
        observed_mutations = set()
        offspring_count = 0
        for seed in map(str, range(12)):
            result, _ = self.run_search(seed=seed)
            initial = result['trials'][:4]
            for trial in initial:
                self.assertEqual(trial['phase'], 'initialization')
                self.assertEqual(trial['parents'], [])
                self.assertEqual(trial['mutated_loci'], [])
            population = [trial['candidate_id'] for trial in initial]
            for start in range(4, 20, 3):
                children = result['trials'][start:start + 3]
                elite = min(population, key=lambda ident: (-SCORES[ident], ident))
                worst = max(population, key=lambda ident: (-SCORES[ident], ident))
                for child in children:
                    offspring_count += 1
                    self.assertEqual(child['phase'], 'offspring')
                    self.assertEqual(len(child['parents']), 2)
                    self.assertTrue(all(parent in population for parent in child['parents']))
                    # A unique worst slot cannot win a two-distinct-slot tournament.
                    if population.count(worst) == 1:
                        self.assertNotIn(worst, child['parents'])
                    loci = child['mutated_loci']
                    self.assertEqual(len(loci), len(set(loci)))
                    self.assertTrue(set(loci) <= {'ema_fast', 'ema_slow'})
                    observed_mutations.update(loci)
                    for index, name in enumerate(('ema_fast', 'ema_slow')):
                        parents = {GENES[parent][index] for parent in child['parents']}
                        value = GENES[child['candidate_id']][index]
                        if name not in loci:
                            self.assertIn(value, parents)
                        elif len(parents) == 1:
                            self.assertNotIn(value, parents, 'Mutation must choose a different valid level')
                if len(children) == 3:
                    population = [elite] + [child['candidate_id'] for child in children]
        self.assertGreater(offspring_count, 0)
        self.assertEqual(observed_mutations, {'ema_fast', 'ema_slow'})

    def test_ties_choose_lexical_best_seen_even_when_all_fitness_is_negative(self):
        scores = dict.fromkeys(IDS, -9.0)
        for algorithm in ('random', 'ga'):
            result, calls = self.run_search(algorithm=algorithm, seed='45', scores=scores)
            self.assert_budget_and_best_seen(result, calls, scores)
            self.assertEqual(result['winner'], min(calls))

    def test_unrequested_oracle_scores_cannot_affect_or_appear_in_search_result(self):
        for algorithm in ('random', 'ga'):
            first, calls = self.run_search(algorithm=algorithm, seed='81', budget=7)
            altered = {ident: (value if ident in calls else 987654321.0 + index)
                       for index, (ident, value) in enumerate(SCORES.items())}
            self.assertTrue(set(IDS) - set(calls))
            second, later_calls = self.run_search(algorithm=algorithm, seed='81', budget=7, scores=altered)
            self.assertEqual(first, second)
            self.assertEqual(calls, later_calls)
            self.assertNotIn('987654', json.dumps(second))
            self.assertNotIn('oracle', second)
            self.assertNotIn('regret', second)

    def test_twenty_ga_requests_do_not_grant_knowledge_of_an_unseen_optimum(self):
        scores = dict.fromkeys(IDS, 0.0)
        original, calls = self.run_search(seed='0', scores=scores)
        unseen = set(IDS) - set(calls)
        self.assertTrue(unseen, 'This fixture must contain duplicates and an unvisited candidate')
        hidden_best = min(unseen)
        scores[hidden_best] = 1000000.0
        ga, ga_calls = self.run_search(seed='0', scores=scores)
        exhaustive, random_calls = self.run_search(algorithm='random', seed='0', scores=scores)
        self.assertEqual(ga, original)
        self.assertEqual(ga_calls, calls)
        self.assertNotEqual(ga['winner'], hidden_best)
        self.assertEqual(len(set(random_calls)), 20)
        self.assertEqual(exhaustive['winner'], hidden_best)

    def test_mutation_threshold_is_one_quarter_and_crossover_selects_each_parent_locus(self):
        # Controlled RNG decisions isolate selection/crossover/mutation rules;
        # the real, independently seeded permutation still initializes search.
        original_rng = SearchRandomStreams.rng
        parent_slots = iter(((0, 1), (2, 3)))
        crossover_slots = iter((0, 1))
        mutation_draws = iter((0.249999999, 0.25))
        offered_mutations = []

        class ScriptedOffspring:
            def sample(inner, population, count):
                self.assertEqual(list(population), [0, 1, 2, 3])
                self.assertEqual(count, 2)
                return list(next(parent_slots))

            def randrange(inner, stop):
                self.assertEqual(stop, 2)
                return next(crossover_slots)

            def random(inner):
                return next(mutation_draws)

            def choice(inner, values):
                offered_mutations.append(list(values))
                return values[0]

        offspring = ScriptedOffspring()

        def rng(stream, namespace, *indices):
            if namespace == 'offspring':
                self.assertEqual(stream.algorithm, 'ema_grid_ga')
                return offspring
            return original_rng(stream, namespace, *indices)

        scores = dict.fromkeys(IDS, 0.0)
        with patch.object(SearchRandomStreams, 'rng', rng):
            result, calls = self.run_search(seed='63', budget=5, scores=scores)
        left, right = min(calls[:2]), min(calls[2:4])
        child = result['trials'][-1]
        self.assertEqual(child['parents'], [left, right])
        self.assertEqual(child['mutated_loci'], ['ema_fast'])
        legal_other_fast = [value for value in (3, 5, 8, 12) if value != GENES[left][0]]
        self.assertEqual(offered_mutations, [legal_other_fast])
        self.assertEqual(GENES[child['candidate_id']], (legal_other_fast[0], GENES[right][1]))

    def test_repeated_candidate_fitness_must_remain_stationary(self):
        calls = []
        seen = set()

        def evaluate(ident):
            calls.append(ident)
            if ident in seen:
                return 1.0
            seen.add(ident)
            return 0.0

        with self.assertRaises(ValueError):
            search_grid(GRID, seed='0', budget=20, algorithm='ga', evaluate=evaluate)
        self.assertLess(len(calls), 20)
        self.assertIn(calls[-1], calls[:-1])
        self.assertEqual(len(set(calls[:-1])), len(calls) - 1)

    def test_evaluator_failure_propagates_without_requesting_more_scores(self):
        calls = []
        failure = RuntimeError('Offline fixture evaluator failed')

        def evaluate(ident):
            calls.append(ident)
            if len(calls) == 3:
                raise failure
            return 0.0

        with self.assertRaises(RuntimeError) as caught:
            search_grid(GRID, seed='0', budget=20, algorithm='ga', evaluate=evaluate)
        self.assertIs(caught.exception, failure)
        self.assertEqual(len(calls), 3)

    def test_global_rng_noise_and_interleaved_searches_do_not_change_results(self):
        first, _ = self.run_search(seed='173')
        random.seed(9321)
        for _ in range(250):
            random.gauss(0, 1)
        before = random.getstate()
        with patch('random.random', side_effect=AssertionError('Global RNG forbidden')), \
             patch('random.choice', side_effect=AssertionError('Global RNG forbidden')), \
             patch('random.shuffle', side_effect=AssertionError('Global RNG forbidden')), \
             patch('random.sample', side_effect=AssertionError('Global RNG forbidden')):
            self.run_search(seed='9481', algorithm='random')
            self.run_search(seed='912', budget=5)
            second, _ = self.run_search(seed='173')
        self.assertEqual(first, second)
        self.assertEqual(random.getstate(), before)

    def test_inputs_and_returned_trace_do_not_share_mutable_search_state(self):
        original_grid = deepcopy(GRID)
        first, _ = self.run_search(seed='29')
        expected = deepcopy(first)
        first['order'].clear()
        first['trials'][0]['parents'].append('not-a-candidate')
        first['best_by_budget'][0]['fitness'] = -123456
        second, _ = self.run_search(seed='29')
        self.assertEqual(second, expected)
        self.assertEqual(GRID, original_grid)
        self.assertEqual(json.loads(json.dumps(second, allow_nan=False)), second)

    def test_malformed_domains_fail_before_the_first_evaluation(self):
        invalid = [None, (), ((1, 3),), ((1, 3), (1, 4)),
                   ((1, 3), (2, 3)), ((1, 3), (1, 4), (2, 3)),
                   ((1, 3), (1, 4), (2, 3), (2, 4), (1, 3)),
                   ((True, 3), (True, 4), (2, 3), (2, 4)),
                   ((1.0, 3), (1.0, 4), (2, 3), (2, 4)),
                   ((0, 3), (0, 4), (2, 3), (2, 4)),
                   ((-1, 3), (-1, 4), (2, 3), (2, 4)),
                   ((1, 2), (1, 3), (2, 2), (2, 3)),
                   ((1, 3, 5), (1, 4), (2, 3), (2, 4)),
                   tuple((fast, slow) for fast in range(1, 6) for slow in range(6, 11))]
        for grid in invalid:
            with self.subTest(grid=grid), self.assertRaises(ValueError):
                search_grid(grid, seed='0', budget=1, algorithm='ga',
                            evaluate=lambda _: self.fail('Invalid domain reached evaluator'))

    def test_malformed_seed_budget_and_algorithm_fail_before_evaluation(self):
        invalid = [('seed', value) for value in (None, True, 0, 1.0, '', '00', '+1', '-1', ' 1', '1 ',
                                                '18446744073709551616')]
        invalid += [('budget', value) for value in (None, True, 0, -1, 21, 1.0, '2')]
        invalid += [('algorithm', value) for value in (None, True, '', 'GA', 'cma_es', ['ga'])]
        for key, value in invalid:
            config = dict(seed='0', budget=1, algorithm='ga')
            config[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                search_grid(GRID, **config, evaluate=lambda _: self.fail('Invalid config reached evaluator'))

    def test_nonfinite_boolean_or_nonnumeric_fitness_fails_without_more_evaluations(self):
        for invalid in (float('nan'), float('inf'), float('-inf'), 10**400, True, False, None, '1.0'):
            for algorithm in ('random', 'ga'):
                calls = []

                def evaluate(ident):
                    calls.append(ident)
                    return invalid

                with self.subTest(value=invalid, algorithm=algorithm), self.assertRaises(ValueError):
                    search_grid(GRID, seed='0', budget=20, algorithm=algorithm, evaluate=evaluate)
                self.assertEqual(len(calls), 1)

    def test_smallest_rectangle_has_a_fully_evaluated_four_candidate_budget(self):
        grid = ((1, 3), (1, 4), (2, 3), (2, 4))
        scores = {f'ema-{fast:02d}-{slow:02d}': -float(fast + slow) for fast, slow in grid}
        for algorithm in ('random', 'ga'):
            result, calls = self.run_search(algorithm=algorithm, grid=grid, scores=scores, budget=4)
            self.assertEqual(set(calls), set(scores))
            self.assert_budget_and_best_seen(result, calls, scores)


if __name__ == '__main__':
    unittest.main()
