"""Offline replay of the real four solvers and their independent search streams."""

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.security_support import A1, A2, USER_A, OfflineTestMixin, deny_network

with deny_network():
    import numpy as np
    from pydantic import ValidationError
    from fastapi.testclient import TestClient
    from vonneumann.core.colony_config import ColonyConfig, GeneOverride
    from vonneumann.core.evolution import mutate, mutate_assets, inject_diversity_genomes
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.genome import Genome, NUMERIC_GENES, random_genome
    from vonneumann.core.search_random import SearchRandomStreams, validate_search_seed
    from vonneumann.core.strategies import get_strategy
    from vonneumann.core.strategies.genetic_algorithm import crossover, reproduce
    from vonneumann.market.sim_feed import SimulationFeed
    from vonneumann.server.models import StartRequest
    from vonneumann.server.auth import VerifiedUser, require_user
    app_module = importlib.import_module('vonneumann.server.app')


ALGORITHMS = ('genetic_algorithm', 'differential_evolution', 'cma_es', 'particle_swarm')


def config():
    template = Genome(timeframe_minutes=5, rsi_period=5, ema_fast=3, ema_slow=10,
                      num_assets=1, position_size_pct=.5, death_drawdown_pct=.3,
                      benchmark_target_pct=.15, reproduce_target_dollars=50)
    active = ['rsi_oversold', 'volume_threshold']
    return ColonyConfig(enabled_genes=active, available_assets=['SOL/USDC', 'JUP/USDC'],
        gene_overrides={name: GeneOverride(fixed=getattr(template, name))
                        for name in NUMERIC_GENES if name not in active},
        reproduction_interval=3, mutation_rate=.3)


async def make_controller(algorithm, seed='0', pacing=100, colony=A1):
    async def ignore_event(_):
        pass
    controller = GenesisController(SimulationFeed(seed=729), get_strategy(algorithm), colony, USER_A,
        gen0_count=8, max_probes=8, max_capital=10000, seed_capital=100,
        tick_interval_ms=pacing, colony_config=config(), on_event=ignore_event,
        circuit_breaker_drop_pct=1., search_seed=seed)
    await controller.prepare()
    controller.set_lifecycle('running')
    return controller


def snapshot(controller, identities):
    members = list(controller.probes.values())
    generation = controller._evaluation_iteration
    for index, probe in enumerate(members):
        identities.setdefault(probe.probe_id, f'{generation}:{index}')
    genomes = []
    for probe in members:
        data = probe.genome.to_dict()
        data['parent_ids'] = [identities[pid] for pid in data['parent_ids']]
        genomes.append(data)
    return {'genomes': genomes, 'market_time': controller.market_feed.current_timestamp,
            'account_equity': controller.status()['total_capital'],
            'search_spec': controller.status()['search_spec']}


async def trace(algorithm, seed='0', *, noise=False, pacing=100, concurrent=None, generations=4):
    controller = await make_controller(algorithm, seed, pacing)
    other = await make_controller(algorithm, concurrent, 1000, A2) if concurrent is not None else None
    ids = {}
    result = [snapshot(controller, ids)]
    for frame in range(500):
        if noise:
            random.seed(frame + 134)
            random.gauss(0, 1)
            np.random.seed(frame + 293)
            np.random.random(13)
            await asyncio.sleep(0)
        if other is not None:
            await other._tick_all()
        iteration = controller._evaluation_iteration
        await controller._tick_all()
        if controller._evaluation_iteration != iteration:
            result.append(snapshot(controller, ids))
        if len(result) >= generations:
            break
    else:
        raise AssertionError('Real controller did not complete enough common windows')
    # Full synthetic universe advances regardless of the chosen asset subset.
    market = {asset: controller.market_feed.get_current_price(asset) for asset in controller.market_feed._assets}
    return {'trace': result, 'market': market}


class SearchSeedTests(OfflineTestMixin, unittest.TestCase):
    def test_optional_canonical_uint64_string_rejects_lossy_and_ambiguous_input(self):
        self.assertEqual(StartRequest().search_seed, '0')
        for seed in ('0', '1', '9007199254740993', '18446744073709551615'):
            self.assertEqual(StartRequest(search_seed=seed).model_dump()['search_seed'], seed)
        for seed in (None, True, False, 0, 1, 1.0, -1, '', '01', '00', '+1', '-1', '1.0',
                     ' 1', '1 ', '1e2', '١', '18446744073709551616', '9' * 100):
            with self.subTest(seed=seed):
                with self.assertRaises(ValidationError):
                    StartRequest(search_seed=seed)
                with self.assertRaises(ValueError):
                    validate_search_seed(seed)

    def test_namespace_derivation_has_stable_vector_and_separates_semantic_coordinates(self):
        streams = SearchRandomStreams('18446744073709551615', 'cma_es')
        payload = ['sha256-namespaced-search-v1', '18446744073709551615', 'cma_es',
                   'mutation', 2, 'generation', 3, 4]
        expected = int.from_bytes(hashlib.sha256(json.dumps(payload, separators=(',', ':')).encode()).digest(), 'big')
        self.assertEqual(streams.derive('mutation', 2, 'generation', 3, 4), expected)
        self.assertNotEqual(expected, streams.derive('mutation', 2, 'generation', 3, 5))
        self.assertNotEqual(expected, streams.derive('strategy', 2, 'generation', 3, 4))
        self.assertNotEqual(expected, streams.derive('mutation', 3, 'generation', 3, 4))
        self.assertEqual(streams.derive('gen0', 0, 1),
                         SearchRandomStreams(streams.seed, 'particle_swarm').derive('gen0', 0, 1))
        spec = streams.spec(2)
        self.assertEqual(json.loads(json.dumps(spec, allow_nan=False))['seed'], streams.seed)
        spec['seed'] = '9'
        self.assertEqual(streams.spec(2)['seed'], streams.seed)
        self.assertFalse(spec['optimizer_state_checkpointed'])

    def test_helper_defaults_are_private_and_reproducible_without_global_draws(self):
        with ExitStack() as stack:
            for method in ('random', 'uniform', 'randint', 'randrange', 'sample', 'choice', 'gauss'):
                stack.enter_context(patch(f'random.{method}', side_effect=AssertionError('global random used')))
            first = random_genome(colony_config=config())
            self.assertEqual(first.to_dict(), random_genome(colony_config=config()).to_dict())
            self.assertEqual(mutate(deepcopy(first), colony_config=config()).to_dict(),
                             mutate(deepcopy(first), colony_config=config()).to_dict())
            self.assertEqual(mutate_assets(first.assets, config()), mutate_assets(first.assets, config()))
            crossover(first, first, 1, config())
            reproduce(first, None, colony_config=config())
            inject_diversity_genomes([], 0, colony_config=config())
            for algorithm in ALGORITHMS:
                strategy = get_strategy(algorithm)
                self.assertEqual(strategy._search_streams.seed, '0')


class SearchReplayTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        state, np_state = random.getstate(), np.random.get_state()
        self.addCleanup(random.setstate, state)
        self.addCleanup(np.random.set_state, np_state)

    async def test_all_real_solvers_replay_with_global_noise_concurrent_colonies_and_changed_pacing(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                reference = await trace(algorithm, '18446744073709551615')
                delayed = await trace(algorithm, '18446744073709551615',
                                      noise=True, pacing=60000, concurrent='17')
                self.assertEqual(reference, delayed)
                self.assertGreaterEqual(len(reference['trace']), 4)
                self.assertNotEqual(reference['trace'][0]['genomes'], reference['trace'][-1]['genomes'])

    async def test_search_seed_changes_genomes_while_market_path_is_identical(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                first = await trace(algorithm, '10')
                second = await trace(algorithm, '11')
                self.assertNotEqual(first['trace'][0]['genomes'], second['trace'][0]['genomes'])
                self.assertEqual(first['market'], second['market'])
                self.assertEqual([x['market_time'] for x in first['trace']],
                                 [x['market_time'] for x in second['trace']])

    async def test_aborted_restart_advances_explicit_epoch_and_replays_same_lifecycle(self):
        for algorithm in ALGORITHMS:
            first, second = await make_controller(algorithm, '18'), await make_controller(algorithm, '18', colony=A2)
            for controller in (first, second):
                controller.set_lifecycle('paused')
                controller.set_lifecycle('running')
                await controller._restart_evaluation()
                self.assertEqual(controller.status()['search_spec']['epoch'], 1)
                self.assertEqual(controller.strategy._search_epoch, 1)
            self.assertEqual([p.genome.to_dict() for p in first.probes.values()],
                             [p.genome.to_dict() for p in second.probes.values()])
            self.assertEqual(first.strategy._rng.getstate(), second.strategy._rng.getstate())

    async def test_fresh_processes_ignore_python_hash_seed_for_all_solver_traces(self):
        source = ('import asyncio,json; from tests.test_search_replay import trace,ALGORITHMS,deny_network; '
                  '\nasync def run():\n return {a:await trace(a,"27",generations=3) for a in ALGORITHMS}'
                  '\nwith deny_network():\n print(json.dumps(asyncio.run(run()),sort_keys=True,allow_nan=False))')
        package_root = str(Path(__file__).resolve().parents[1])
        outputs = []
        for hash_seed in ('1', '987654'):
            env = {'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': package_root,
                   'PYTHONHASHSEED': hash_seed, 'PYTHON_DOTENV_DISABLED': '1',
                   'PYTHONDONTWRITEBYTECODE': '1'}
            process = subprocess.run([sys.executable, '-c', source], env=env, check=True,
                                      capture_output=True, text=True, timeout=60)
            outputs.append(json.loads(process.stdout))
        self.assertEqual(outputs[0], outputs[1])


class SearchApiTests(OfflineTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(app_module.app)
        self.addCleanup(self.client.close)
        before = dict(app_module.app.dependency_overrides)
        self.addCleanup(lambda: (app_module.app.dependency_overrides.clear(),
                                 app_module.app.dependency_overrides.update(before)))
        app_module.app.dependency_overrides[require_user] = lambda: VerifiedUser(USER_A, int(time.time()) + 3600)
        self.fake_repo = MagicMock()
        self.fake_repo.execute_async = AsyncMock()
        self.repo = self.offline_stack.enter_context(patch.object(app_module, 'VonNeumannRepository',
                                                                  return_value=self.fake_repo))
        self.create = self.offline_stack.enter_context(patch.object(app_module.colony_manager,
                                                                     'create_colony', new=AsyncMock()))

    def test_invalid_seed_is_rejected_before_repository_or_controller_creation(self):
        for seed in (True, 1, 1.0, '01', '-1', '18446744073709551616', None):
            with self.subTest(seed=seed):
                response = self.client.post('/api/v1/colonies/', json={'search_seed': seed})
                self.assertEqual(response.status_code, 422, response.text)
        self.repo.assert_not_called()
        self.create.assert_not_awaited()

    def test_full_precision_seed_and_versioned_spec_reach_insert_controller_response_and_runtime(self):
        seed = '18446744073709551615'
        response = self.client.post('/api/v1/colonies/', json={'search_seed': seed, 'strategy': 'cma_es'})
        self.assertEqual(response.status_code, 200, response.text)
        spec = SearchRandomStreams(seed, 'cma_es').spec()
        inserted = self.fake_repo.execute_async.await_args.args[3]
        self.assertEqual(inserted['search_seed'], seed)
        self.assertEqual(inserted['search_spec'], spec)
        self.assertEqual(response.json()['search_spec'], spec)
        self.assertEqual(StartRequest.model_validate(response.json()['config']).search_seed, seed)
        self.assertEqual(self.create.await_args.kwargs['search_seed'], seed)
        persist = self.create.await_args.kwargs['persist_status']
        later_spec = SearchRandomStreams(seed, 'cma_es').spec(3)
        asyncio.run(persist({'status': 'paused', 'search_spec': later_spec}))
        details = self.fake_repo.execute_async.await_args.kwargs['details']
        self.assertEqual(details['search_spec'], later_spec)


if __name__ == '__main__':
    unittest.main()
