"""Offline geometry, current-window evidence and real numerical objectives."""

from copy import deepcopy
from dataclasses import replace
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    import numpy as np
    from vonneumann.core.colony_config import ColonyConfig, GeneOverride
    from vonneumann.core.evaluation import EvaluationCohort
    from vonneumann.core.genome import Genome
    from vonneumann.core.parameter_codec import ParameterCodec
    from vonneumann.core.strategies.cma_es import CMAEvolutionStrategy, cmaes_lib
    from vonneumann.core.strategies.particle_swarm import ParticleSwarmStrategy


def candidate(identity, genome, score=0):
    return SimpleNamespace(probe_id=identity, genome=genome, fitness=score, roi=score, num_trades=0)


def evaluated(probes, iteration):
    cohort = EvaluationCohort(f"iteration-{iteration}", probes, 60)
    cohort.start(iteration * 60)
    return list(cohort.complete(probes, (iteration + 1) * 60))


def following(strategy, result, iteration):
    members = [candidate(f"{iteration}:{i}", genome) for i, genome in enumerate(result.offspring)]
    if isinstance(strategy, ParticleSwarmStrategy):
        for index, child in enumerate(members):
            strategy.remap_probe_id(result.parent_map[str(index)][0], child.probe_id)
    strategy.bind_candidates(members)
    return members


class CodecTests(OfflineTestMixin, unittest.TestCase):
    def test_only_active_effective_dimensions_are_encoded(self):
        config = ColonyConfig(enabled_genes=["rsi_period", "volume_threshold", "num_assets"],
                              available_assets=["SOL/USDC"],
                              gene_overrides={"rsi_period": GeneOverride(fixed=17),
                                              "volume_threshold": GeneOverride(min=1.5, max=1.5)})
        codec = ParameterCodec(config)
        self.assertEqual(codec.names, ())
        self.assertEqual(codec.bounds.shape, (0, 2))
        genome = Genome().validate(config)
        self.assertEqual(codec.encode(genome).shape, (0,))
        self.assertEqual(codec.decode([], genome), genome)

    def test_integer_and_coupled_repairs_use_authoritative_validator(self):
        config = ColonyConfig(enabled_genes=["rsi_period", "ema_fast", "ema_slow"],
                              gene_overrides={"ema_fast": GeneOverride(min=10, max=20),
                                              "ema_slow": GeneOverride(min=10, max=20)})
        codec = ParameterCodec(config)
        template = Genome().validate(config)
        values = {"rsi_period": .1, "ema_fast": 1., "ema_slow": 0.}
        raw = np.array([values[name] for name in codec.names])
        result = codec.decode(raw, template)
        self.assertEqual(result.rsi_period, 8)  # 7.5 rounds half up.
        self.assertEqual((result.ema_fast, result.ema_slow), (10, 11))
        self.assertTrue(np.all(codec.encode(result) >= 0))
        self.assertTrue(np.all(codec.encode(result) <= 1))
        np.testing.assert_array_equal(raw, [values[name] for name in codec.names])

    def test_decode_preserves_template_and_deterministic_asset_preferences(self):
        config = ColonyConfig(enabled_genes=["num_assets"], available_assets=["SOL/USDC", "JUP/USDC", "BONK/USDC"])
        template = Genome(num_assets=1, assets=["BONK/USDC"]).validate(config)
        before = deepcopy(template)
        codec = ParameterCodec(config)
        with patch("random.random", side_effect=AssertionError("No hidden asset randomness")), \
                patch("random.sample", side_effect=AssertionError("No hidden asset randomness")):
            expanded = codec.decode([1], template)
        self.assertEqual(expanded.assets, ["BONK/USDC", "SOL/USDC", "JUP/USDC"])
        self.assertEqual(template, before)

    def test_vectors_fail_closed_and_clipping_is_explicit(self):
        config = ColonyConfig(enabled_genes=["volume_threshold"])
        codec = ParameterCodec(config)
        template = Genome().validate(config)
        for values in ([], [0, 1], [[.5]], [float("nan")], [float("inf")], [True], [".5"], [-.1], [1.1]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                codec.decode(values, template)
        self.assertEqual(codec.decode([-100], template, clip=True).volume_threshold, 1)
        self.assertEqual(codec.decode([100], template, clip=True).volume_threshold, 3)
        with self.assertRaises(ValueError):
            codec.decode([float("nan")], template, clip=True)
        mixed = ParameterCodec(ColonyConfig(enabled_genes=["rsi_oversold", "volume_threshold"]))
        with self.assertRaises(ValueError):
            mixed.vector([True, .5])

    def test_encode_rejects_unvalidated_phenotype_and_changed_epoch_configuration(self):
        config = ColonyConfig(enabled_genes=["rsi_period"])
        codec = ParameterCodec(config)
        for genome in (Genome(rsi_period=14.5), Genome(rsi_period=float("nan")), Genome(volume_threshold=2)):
            with self.subTest(genome=genome), self.assertRaises(ValueError):
                codec.encode(genome)
        config.gene_overrides["rsi_period"] = GeneOverride(max=20)
        with self.assertRaises(ValueError):
            codec.check_configuration(config)


class SwarmGeometryTests(OfflineTestMixin, unittest.TestCase):
    def setup_swarm(self, names=("volume_threshold",), positions=(.2, .8), seed=19):
        config = ColonyConfig(enabled_genes=list(names))
        codec = ParameterCodec(config)
        template = Genome().validate(config)
        probes = [candidate(f"initial-{i}", codec.decode([value] * len(names), template))
                  for i, value in enumerate(positions)]
        strategy = ParticleSwarmStrategy()
        strategy._rng.seed(seed)
        strategy.initialize(probes, config)
        strategy.bind_candidates(probes)
        return config, codec, probes, strategy

    def test_scores_reset_instead_of_comparing_different_regimes(self):
        config, codec, probes, strategy = self.setup_swarm()
        probes[0].fitness, probes[1].fitness = 1_000_000, -100
        result = strategy.evolve(evaluated(probes, 0), [], config)
        next_probes = following(strategy, result, 1)
        self.assertTrue(all(value[1] is None for value in strategy._personal_best.values()))
        self.assertIsNone(strategy._global_best)
        next_probes[0].fitness, next_probes[1].fitness = -10, -1
        result = strategy.evolve(evaluated(next_probes, 1), [], config)
        self.assertEqual(strategy._global_best, (next_probes[1].genome.to_dict(), -1))
        self.assertEqual([value[1] for value in strategy._personal_best.values()], [-10, -1])
        self.assertEqual(result.metadata["best_score_iteration_id"], "iteration-1")

    def test_actual_velocity_matches_integer_and_boundary_repairs(self):
        config, codec, probes, strategy = self.setup_swarm(("rsi_period",), (0., 1.))
        strategy._velocities = {probes[0].probe_id: {"rsi_period": -2.},
                                probes[1].probe_id: {"rsi_period": 2.}}
        probes[0].fitness, probes[1].fitness = 2, 1
        result = strategy.evolve(evaluated(probes, 0), [], config)
        for probe, child in zip(probes, result.offspring):
            actual = codec.encode(child) - codec.encode(probe.genome)
            np.testing.assert_array_equal(actual, list(strategy._velocities[probe.probe_id].values()))
        self.assertEqual(strategy._velocities[probes[0].probe_id]["rsi_period"], 0)

    def test_initial_random_velocity_moves_identical_candidates(self):
        config, codec, probes, strategy = self.setup_swarm(positions=(.5,) * 8)
        result = strategy.evolve(evaluated(probes, 0), [], config)
        self.assertTrue(any(child.volume_threshold != probes[0].genome.volume_threshold for child in result.offspring))

    def test_social_ancestry_retains_particle_first_and_only_current_sources(self):
        config, codec, probes, strategy = self.setup_swarm()
        probes[1].fitness = 1
        result = strategy.evolve(list(reversed(evaluated(probes, 0))), [], config)
        self.assertEqual(result.parent_map["0"], [probes[0].probe_id, probes[1].probe_id])
        self.assertEqual(result.parent_map["1"], [probes[1].probe_id])
        self.assertEqual(result.metadata["parent_roles"]["0"]["social_source_id"], probes[1].probe_id)
        self.assertIsNone(result.metadata["parent_roles"]["1"]["social_source_id"])

    def test_incomplete_changed_or_replayed_results_cannot_consume_rng_or_momentum(self):
        config, codec, probes, strategy = self.setup_swarm()
        complete = evaluated(probes, 0)
        invalid = [complete[:-1], [complete[0], complete[0]],
                   [replace(complete[0], cohort_complete=False), complete[1]],
                   [replace(complete[0], fitness=float("inf")), complete[1]]]
        state, velocity = strategy._rng.getstate(), deepcopy(strategy._velocities)
        for batch in invalid:
            with self.assertRaises(ValueError):
                strategy.evolve(batch, [], config)
            self.assertEqual(strategy._rng.getstate(), state)
            self.assertEqual(strategy._velocities, velocity)
        strategy.evolve(complete, [], config)
        with self.assertRaises(ValueError):
            strategy.evolve(complete, [], config)

    def test_terminal_particles_retain_slot_momentum_then_cleanup_on_abort(self):
        config, codec, probes, strategy = self.setup_swarm()
        cohort = EvaluationCohort("early-death", probes, 60)
        cohort.start(0)
        cohort.record_terminal(probes[0], "drawdown", 10)
        result = strategy.evolve(list(cohort.complete(probes[1:], 60)), [probes[0]], config)
        children = following(strategy, result, 1)
        self.assertEqual(set(strategy._velocities), {p.probe_id for p in children})
        self.assertEqual(set(strategy._personal_best), {p.probe_id for p in children})
        strategy.abort_cohort()
        self.assertEqual(strategy._velocities, {})
        self.assertEqual(strategy._personal_best, {})
        self.assertIsNone(strategy._global_best)

    def test_affine_domain_rescaling_preserves_actual_strategy_trajectory(self):
        first = ColonyConfig(enabled_genes=["rsi_oversold", "volume_threshold"], gene_overrides={
            "rsi_oversold": GeneOverride(min=20, max=30), "volume_threshold": GeneOverride(min=1, max=2)})
        second = ColonyConfig(enabled_genes=["rsi_oversold", "volume_threshold"], gene_overrides={
            "rsi_oversold": GeneOverride(min=20, max=40), "volume_threshold": GeneOverride(min=1, max=3)})
        setups = []
        for config in (first, second):
            codec = ParameterCodec(config)
            template = Genome().validate(config)
            probes = [candidate(f"start-{i}", codec.decode(position, template))
                      for i, position in enumerate(([.1, .7], [.9, .6], [.3, .2]))]
            strategy = ParticleSwarmStrategy()
            strategy._rng.seed(123)
            strategy.initialize(probes, config)
            strategy.bind_candidates(probes)
            setups.append([config, codec, probes, strategy])
        for iteration in range(20):
            vectors = []
            for setup in setups:
                config, codec, probes, strategy = setup
                for probe in probes:
                    probe.fitness = -float(np.sum((codec.encode(probe.genome) - .4) ** 2))
                result = strategy.evolve(evaluated(probes, iteration), [], config)
                setup[2] = following(strategy, result, iteration + 1)
                vectors.append([codec.encode(child.genome) for child in setup[2]])
            np.testing.assert_allclose(vectors[0], vectors[1], atol=1e-12)


class NumericalObjectiveTests(OfflineTestMixin, unittest.TestCase):
    def test_cma_tie_template_and_distribution_ancestry_follow_bound_order(self):
        config = ColonyConfig(enabled_genes=["volume_threshold"])
        first = Genome(assets=["JUP/USDC", "SOL/USDC"]).validate(config)
        second = Genome(assets=["BONK/USDC", "WIF/USDC"]).validate(config)
        probes = [candidate("a", first), candidate("b", second), candidate("c", first), candidate("d", second)]
        strategy = CMAEvolutionStrategy()
        strategy.initialize(probes, config)
        result = strategy.evolve(list(reversed(evaluated(probes, 0))), [], config)
        self.assertTrue(all(child.assets == first.assets for child in result.offspring))
        self.assertEqual(result.retire_ids, ["a", "b", "c", "d"])
        self.assertTrue(all(parents == ["a", "b", "c", "d"] for parents in result.parent_map.values()))
        self.assertEqual(result.metadata["asset_template_source_id"], "a")
        self.assertEqual(result.metadata["distribution_source_ids"], ["a", "b", "c", "d"])

    def test_real_cma_uses_unit_sigma_and_avoids_raw_scale_clipping(self):
        config = ColonyConfig()
        template = Genome().validate(config)
        probes = [candidate(str(i), deepcopy(template)) for i in range(12)]
        real_cma = cmaes_lib.CMA
        with patch("vonneumann.core.strategies.cma_es.cmaes_lib.CMA", side_effect=lambda **kwargs: real_cma(**{**kwargs, "seed": 1729})):
            strategy = CMAEvolutionStrategy()
            strategy.initialize(probes, config)
        self.assertEqual(strategy._optimizer._sigma, .3)
        np.testing.assert_array_equal(strategy._optimizer._bounds, strategy._codec.bounds)
        asks = np.array([strategy._optimizer.ask() for _ in range(1000)])
        self.assertLess(float(np.mean((asks == 0) | (asks == 1))), .05)

    def test_zero_active_dimensions_produce_complete_fixed_replacements(self):
        config = ColonyConfig(enabled_genes=[])
        for strategy_type in (CMAEvolutionStrategy, ParticleSwarmStrategy):
            with self.subTest(strategy=strategy_type.__name__):
                strategy = strategy_type()
                probes = [candidate(str(i), Genome().validate(config)) for i in range(4)]
                strategy.initialize(probes, config)
                strategy.bind_candidates(probes)
                for iteration in range(3):
                    result = strategy.evolve(evaluated(probes, iteration), [], config)
                    self.assertEqual(len(result.offspring), 4)
                    self.assertTrue(all(child.generation == iteration + 1 for child in result.offspring))
                    self.assertTrue(all(child.volume_threshold == 1.4 for child in result.offspring))
                    probes = following(strategy, result, iteration + 1)

    def test_cma_fixed_bootstrap_and_generation_cannot_be_rebound_or_spoofed(self):
        for names in ([], ["volume_threshold"]):
            with self.subTest(active=names):
                config = ColonyConfig(enabled_genes=names)
                strategy = CMAEvolutionStrategy()
                probes = [candidate(str(i), Genome().validate(config)) for i in range(4)]
                strategy.initialize(probes, config)
                strangers = [candidate(f"stranger-{i}", deepcopy(probe.genome)) for i, probe in enumerate(probes)]
                with self.assertRaises(ValueError):
                    strategy.bind_candidates(strangers)
                results = evaluated(probes, 0)
                changed = results[0].genome
                changed.generation += 1
                with self.assertRaises(ValueError):
                    strategy.evolve([replace(results[0], _genome=changed), *results[1:]], [], config)
                result = strategy.evolve(results, [], config)
                self.assertEqual(len(result.offspring), 4)

    def test_real_strategies_improve_sphere_and_rotated_quadratic(self):
        real_cma = cmaes_lib.CMA
        for strategy_type in (CMAEvolutionStrategy, ParticleSwarmStrategy):
            for dimensions, rotated in ((1, False), (2, False), (2, True)):
                with self.subTest(strategy=strategy_type.__name__, dimensions=dimensions, rotated=rotated):
                    config = ColonyConfig(enabled_genes=["rsi_oversold", "volume_threshold"][:dimensions])
                    codec = ParameterCodec(config)
                    template = Genome().validate(config)
                    rng = random.Random(41)
                    probes = [candidate(f"initial-{i}", codec.decode([rng.random() for _ in range(dimensions)], template))
                              for i in range(24)]
                    strategy = strategy_type()
                    if isinstance(strategy, ParticleSwarmStrategy):
                        strategy._rng.seed(90)
                    with patch("vonneumann.core.strategies.cma_es.cmaes_lib.CMA", side_effect=lambda **kwargs: real_cma(**{**kwargs, "seed": 17})):
                        strategy.initialize(probes, config)
                    strategy.bind_candidates(probes)
                    for iteration in range(80):
                        for probe in probes:
                            position = codec.encode(probe.genome)
                            delta = position - np.array([.27, .63][:dimensions])
                            if dimensions == 2 and rotated:
                                delta = np.array([[.8, -.6], [.6, .8]]) @ delta
                                cost = float(delta[0] ** 2 + 25 * delta[1] ** 2)
                            else:
                                cost = float(delta @ delta)
                            probe.fitness = -cost
                        result = strategy.evolve(evaluated(probes, iteration), [], config)
                        if iteration == 0:
                            initial = -max(p.fitness for p in probes)
                        final = -max(p.fitness for p in probes)
                        probes = following(strategy, result, iteration + 1)
                    self.assertLess(final, initial * 1e-3)
                    self.assertLess(final, 1e-5)


if __name__ == "__main__":
    unittest.main()
