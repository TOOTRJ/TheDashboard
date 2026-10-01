"""Bounded two-gene searches over a cached, stationary training evaluator.

Only the callback can expose a score. Neither search receives the oracle table,
holdout results, or future candidates' scores. Repeated requests consume budget.
"""
from __future__ import annotations

import math

from ..core.search_random import SearchRandomStreams, validate_search_seed


SEARCH_POLICY = {
    'version': 'ema-discrete-search-v1',
    'budget': 'logical score requests, including duplicates; one immutable training cache',
    'initialization': 'shared seeded permutation; up to four unique initial candidates',
    'random': 'permutation prefix without replacement',
    'ga': {
        'population': 4, 'elite_copies': 1, 'offspring_per_generation': 3,
        'tournament': 'two distinct population slots; fitness descending, ID then slot ascending',
        'crossover': 'uniform independent choice of parent at each locus',
        'mutation_probability_per_locus': 0.25,
        'mutation': 'uniform other legal level; no repair or forced unseen candidate',
        'duplicates': 'allowed; each request consumes budget, including already known candidates',
        'elite': 'copied score; no new request; reuse count recorded',
        'partial_generation': 'contributes to best seen; never installed as parent population',
    },
    'winner': 'best requested training score; ties by ascending candidate ID',
    'stopping': 'fixed request budget; no early stopping or holdout feedback',
}


def _id(pair):
    return f'ema-{pair[0]:02d}-{pair[1]:02d}'


def search_grid(grid, *, seed, budget, algorithm, evaluate):
    """Search a rectangular grid; evaluate reads a precomputed training cache.

This is a deliberately small reference GA, not the worker's production solver.
The budget does not count the separate exhaustive benchmark or free elite reuse.
"""
    validate_search_seed(seed)
    if (not isinstance(grid, (tuple, list)) or not 4 <= len(grid) <= 20 or
            any(not isinstance(pair, (tuple, list)) or len(pair) != 2 or
                any(type(value) is not int or not 1 <= value <= 999 for value in pair) or
                pair[0] >= pair[1] for pair in grid)):
        raise ValueError('Invalid search domain')
    pairs = tuple(tuple(pair) for pair in grid)
    fast, slow = sorted({pair[0] for pair in pairs}), sorted({pair[1] for pair in pairs})
    if (len(fast) < 2 or len(slow) < 2 or len(set(pairs)) != len(pairs) or
            set(pairs) != {(f, s) for f in fast for s in slow}):
        raise ValueError('Search domain must be a unique rectangular grid')
    if type(budget) is not int or not 1 <= budget <= len(pairs) or algorithm not in ('random', 'ga'):
        raise ValueError('Invalid search policy')
    if not callable(evaluate):
        raise ValueError('Training evaluator required')
    definitions = {_id(pair): pair for pair in pairs}
    order = list(definitions)
    SearchRandomStreams(seed, 'ema_grid_random').rng('grid-permutation').shuffle(order)
    rng = SearchRandomStreams(seed, 'ema_grid_ga').rng('offspring')
    scores, trials, progress = {}, [], []
    elite_reuses = 0

    def winner(ids):
        return min(ids, key=lambda ident: (-scores[ident], ident))

    def request(ident, phase, parents=(), mutated_loci=()):
        duplicate = ident in scores
        value = evaluate(ident)
        try:
            finite = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError('Training fitness must be finite numeric data')
        if duplicate and scores[ident] != value:
            raise ValueError('Training fitness changed during search')
        scores[ident] = value
        n = len(trials) + 1
        trials.append(dict(budget=n, candidate_id=ident, fitness=value, duplicate=duplicate,
                           phase=phase, parents=list(parents), mutated_loci=list(mutated_loci)))
        best = winner(scores)
        progress.append(dict(budget=n, winner=best, fitness=scores[best],
                             unique_trials=len(scores), duplicate_trials=n - len(scores)))

    if algorithm == 'random':
        for ident in order[:budget]:
            request(ident, 'initialization' if len(trials) < 4 else 'random')
    else:
        population = order[:min(4, budget)]
        for ident in population:
            request(ident, 'initialization')
        while len(trials) < budget:
            # Parents are frozen for the whole generation. A partial final
            # generation cannot affect subsequent tournament decisions.
            children = [winner(population)]
            elite_reuses += 1

            def tournament():
                slots = rng.sample(range(len(population)), 2)
                slot = min(slots, key=lambda i: (-scores[population[i]], population[i], i))
                return population[slot]

            for _ in range(3):
                if len(trials) == budget:
                    break
                parents = [tournament(), tournament()]
                pair, mutations = [], []
                for locus, (name, levels) in enumerate((('ema_fast', fast), ('ema_slow', slow))):
                    value = definitions[parents[rng.randrange(2)]][locus]
                    if rng.random() < 0.25:
                        value = rng.choice([level for level in levels if level != value])
                        mutations.append(name)
                    pair.append(value)
                ident = _id(pair)
                request(ident, 'offspring', parents, mutations)
                children.append(ident)
            if len(children) == 4:
                population = children

    return dict(algorithm=algorithm, seed=seed, budget=budget, order=order,
                sampling='without_replacement' if algorithm == 'random' else 'genetic_with_replacement',
                unique_trials=len(scores), duplicate_trials=budget - len(scores),
                score_cache_hits=budget, additional_computed_evaluations=0, elite_score_reuses=elite_reuses,
                trial_ids=[row['candidate_id'] for row in trials], trials=trials,
                winner=winner(scores), best_by_budget=progress)
