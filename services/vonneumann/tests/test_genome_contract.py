"""Offline phenotype and operator regressions for configured genome controls."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from vonneumann.core.colony_config import ColonyConfig, GeneOverride, PRESET_CONFIGS
from vonneumann.core.evaluation import EvaluationCohort
from vonneumann.core.evolution import inject_diversity_genomes, mutate
from vonneumann.core.gene_registry import GENE_REGISTRY, GeneType
from vonneumann.core.genome import AVAILABLE_ASSETS, Genome, random_genome
from vonneumann.core.strategies.cma_es import CMAEvolutionStrategy
from vonneumann.core.strategies.differential_evolution import _de_trial
from vonneumann.core.strategies.genetic_algorithm import crossover, reproduce
from vonneumann.core.strategies.particle_swarm import ParticleSwarmStrategy
from vonneumann.server.models import StartRequest, build_colony_config


class GenomeContractTests(unittest.TestCase):
    def setUp(self):
        self.rng_state = random.getstate()
        random.seed(8128)
        # No real sockets, database or credentials are involved in these tests.
        self.socket_patch = patch("socket.socket", side_effect=AssertionError("Network is forbidden"))
        self.socket_patch.start()

    def tearDown(self):
        self.socket_patch.stop()
        random.setstate(self.rng_state)

    def assert_valid(self, genome, config):
        domains = config.resolve_gene_domains()
        for name, domain in domains.items():
            value = getattr(genome, name)
            self.assertTrue(math.isfinite(value), name)
            self.assertGreaterEqual(value, domain.minimum, name)
            self.assertLessEqual(value, domain.maximum, name)
            if domain.integer:
                self.assertEqual(value, int(value), name)
            if not domain.evolvable:
                self.assertEqual(value, domain.default, name)
        self.assertLess(genome.ema_fast, genome.ema_slow)
        self.assertLess(genome.stop_loss_pct, genome.take_profit_pct)
        self.assertEqual(len(genome.assets), genome.num_assets)
        self.assertEqual(len(set(genome.assets)), len(genome.assets))
        self.assertTrue(set(genome.assets) <= set(config.get_effective_assets()))
        self.assertEqual(genome.int_genes()["num_assets"], len(genome.assets))

    def config(self):
        return ColonyConfig(enabled_genes=["ema_slow", "take_profit_pct", "rsi_period", "position_size_pct"],
            available_assets=AVAILABLE_ASSETS[:3], gene_overrides={
                "ema_fast": GeneOverride(fixed=19), "ema_slow": GeneOverride(min=18, max=23),
                "stop_loss_pct": GeneOverride(fixed=.05), "take_profit_pct": GeneOverride(min=.04, max=.08),
                "num_assets": GeneOverride(fixed=3), "rsi_period": GeneOverride(min=10, max=12),
                "position_size_pct": GeneOverride(min=.1, max=.15),
                "timeframe_minutes": GeneOverride(default=7),
            })

    def test_fixed_asset_count_survives_many_initializations(self):
        for count in (1, 2, 3):
            config = ColonyConfig(gene_overrides={"num_assets": GeneOverride(fixed=count)})
            for _ in range(50):
                genome = random_genome(colony_config=config)
                self.assert_valid(genome, config)
                self.assertEqual(genome.num_assets, count)

    def test_disabled_genes_use_resolved_defaults_instead_of_random_values(self):
        config = ColonyConfig(enabled_genes=[], gene_overrides={
            "rsi_period": GeneOverride(default=12), "position_size_pct": GeneOverride(min=.1, max=.2),
        })
        for _ in range(30):
            genome = random_genome(colony_config=config)
            self.assert_valid(genome, config)
            self.assertEqual(genome.rsi_period, 12)
            self.assertEqual(genome.position_size_pct, .2)
            self.assertEqual(genome.timeframe_minutes, 15)

    def test_all_integer_phenotypes_are_canonical_before_relationship_checks(self):
        genome = Genome(ema_fast=10.4, ema_slow=10.49, rsi_period=10.5).validate()
        self.assertLess(genome.ema_fast, genome.ema_slow)
        self.assertEqual(genome.rsi_period, 11)
        for gene in GENE_REGISTRY.all_genes():
            if gene.gene_type == GeneType.INT:
                self.assertEqual(getattr(genome, gene.name), int(getattr(genome, gene.name)))
        with self.assertRaises(ValueError):
            Genome(ema_fast=10.4).int_genes()

    def test_fixed_or_disabled_partner_is_never_rewritten_to_repair_constraints(self):
        cases = [
            (ColonyConfig(gene_overrides={"ema_fast": GeneOverride(fixed=19), "ema_slow": GeneOverride(min=20)}), "ema_fast", 19),
            (ColonyConfig(gene_overrides={"ema_slow": GeneOverride(fixed=10)}), "ema_slow", 10),
            (ColonyConfig(enabled_genes=["ema_slow"], gene_overrides={"ema_fast": GeneOverride(default=19)}), "ema_fast", 19),
            (ColonyConfig(gene_overrides={"stop_loss_pct": GeneOverride(fixed=.05)}), "stop_loss_pct", .05),
            (ColonyConfig(gene_overrides={"take_profit_pct": GeneOverride(fixed=.03)}), "take_profit_pct", .03),
        ]
        for config, name, expected in cases:
            genome = Genome(ema_fast=20, ema_slow=10, stop_loss_pct=.1, take_profit_pct=.03).validate(config)
            self.assert_valid(genome, config)
            self.assertEqual(getattr(genome, name), expected)

    def test_overlapping_active_ranges_project_inside_both_configured_domains(self):
        config = ColonyConfig(gene_overrides={
            "ema_fast": GeneOverride(min=15, max=20), "ema_slow": GeneOverride(min=16, max=20),
            "stop_loss_pct": GeneOverride(min=.04, max=.08), "take_profit_pct": GeneOverride(min=.03, max=.05),
        })
        for fast in (15, 16.49, 20, 100):
            for slow in (-100, 16, 17.2, 20):
                self.assert_valid(Genome(ema_fast=fast, ema_slow=slow, stop_loss_pct=.1, take_profit_pct=.03).validate(config), config)

    def test_validation_is_atomic_deterministic_and_consumes_no_rng(self):
        config = self.config()
        genome = Genome(assets=["SOL/USDC", "SOL/USDC", "unsupported"], num_assets=1)
        before_rng = random.getstate()
        genome.validate(config)
        expected = deepcopy(genome.to_dict())
        for _ in range(10):
            genome.validate(config)
        self.assertEqual(random.getstate(), before_rng)
        self.assertEqual(genome.to_dict(), expected)
        self.assertEqual(genome.assets, AVAILABLE_ASSETS[:3])
        genome.assets = [False]
        before = deepcopy(genome.to_dict())
        with self.assertRaises(ValueError):
            genome.validate(config)
        self.assertEqual(genome.to_dict(), before)

    def test_bad_numeric_inputs_are_rejected_even_for_fixed_genes(self):
        for value in (True, False, "12", None, math.nan, math.inf, -math.inf, 10 ** 400):
            for config in (ColonyConfig(), ColonyConfig(gene_overrides={"rsi_period": GeneOverride(fixed=12)})):
                with self.assertRaises(ValueError):
                    Genome(rsi_period=value).validate(config)
                if value is not None:
                    with self.assertRaises(ValueError):
                        ColonyConfig(gene_overrides={"rsi_period": GeneOverride(default=value)}).resolve_gene_domains()

    def test_one_asset_pool_clips_only_implicit_count_default(self):
        for enabled in (None, []):
            config = ColonyConfig(available_assets=[AVAILABLE_ASSETS[0]], enabled_genes=enabled)
            genome = Genome(num_assets=3, assets=AVAILABLE_ASSETS[:3]).validate(config)
            self.assertEqual(genome.num_assets, 1)
            self.assert_valid(genome, config)
        for override in (GeneOverride(fixed=2), GeneOverride(default=2), GeneOverride(min=2)):
            with self.assertRaises(ValueError):
                ColonyConfig(available_assets=[AVAILABLE_ASSETS[0]], gene_overrides={"num_assets": override}).resolve_gene_domains()

    def test_zero_width_domains_are_not_optimizer_dimensions(self):
        config = ColonyConfig(gene_overrides={"rsi_period": GeneOverride(min=12, max=12)})
        self.assertFalse(config.is_gene_evolvable("rsi_period"))
        self.assertEqual(config.get_effective_range("rsi_period"), (12, 12, 12))
        self.assertEqual(random_genome(colony_config=config).rsi_period, 12)
        with self.assertRaises(ValueError):
            ColonyConfig(gene_overrides={"ema_fast": GeneOverride(min=100, max=2)}).resolve_gene_domains()

    def test_all_built_in_presets_generate_valid_genomes_without_mutating_configs(self):
        before = {name: config.to_dict() for name, config in PRESET_CONFIGS.items()}
        for config in PRESET_CONFIGS.values():
            for _ in range(20):
                self.assert_valid(random_genome(colony_config=config), config)
        self.assertEqual(before, {name: config.to_dict() for name, config in PRESET_CONFIGS.items()})

    def test_mutation_crossover_reproduction_and_diversity_preserve_controls(self):
        config = self.config()
        parents = [random_genome(colony_config=config) for _ in range(2)]
        dead = [SimpleNamespace(probe_id="dead", genome=parents[0], fitness=1)]
        for _ in range(30):
            children = [mutate(deepcopy(parents[0]), mutation_rate=1, mutation_strength=10, colony_config=config)]
            children.extend(crossover(*parents, generation=1, colony_config=config))
            children.extend(reproduce(parents[0], None, 2, mutation_rate=1, colony_config=config))
            children.extend(reproduce(*parents, num_children=2, mutation_rate=1, colony_config=config))
            children.extend(inject_diversity_genomes(parents, 1, dead, config, 2))
            children.extend(inject_diversity_genomes(parents, 1, None, config, 2))
            for child in children:
                self.assert_valid(child, config)

    def test_mutation_noise_uses_configured_active_range(self):
        config = ColonyConfig(enabled_genes=["position_size_pct"], gene_overrides={"position_size_pct": GeneOverride(min=.1, max=.2)})
        genome = random_genome(colony_config=config)
        rng = random.Random(0)
        with patch.object(rng, "random", return_value=0), patch.object(rng, "gauss", return_value=0) as noise:
            mutate(genome, mutation_rate=1, mutation_strength=.15, colony_config=config, rng=rng)
        noise.assert_called_once()
        self.assertAlmostEqual(noise.call_args.args[1], .015)

    def test_de_and_pso_outputs_use_the_same_actual_phenotype(self):
        config = self.config()
        parents = [random_genome(colony_config=config) for _ in range(4)]
        for _ in range(30):
            self.assert_valid(_de_trial(*parents, F=10, CR=1, colony_config=config), config)
        probes = [SimpleNamespace(probe_id=f"p{i}", genome=genome, fitness=float(i), roi=0, num_trades=3)
                  for i, genome in enumerate(parents)]
        strategy = ParticleSwarmStrategy()
        strategy.initialize(probes, config)
        for velocity in strategy._velocities.values():
            velocity.update({name: 100 for name in velocity})
        cohort = EvaluationCohort("phenotype-test", probes, 60)
        cohort.start(0)
        for child in strategy.evolve(list(cohort.complete(probes, 60)), [], config).offspring:
            self.assert_valid(child, config)

    def test_cma_ask_projects_controls_and_retains_unmodified_optimizer_vectors(self):
        config = self.config()
        probes = [SimpleNamespace(probe_id=f"p{i}", genome=random_genome(colony_config=config), fitness=0., roi=0., num_trades=0)
                  for i in range(4)]
        strategy = CMAEvolutionStrategy()
        strategy.initialize(probes, config)
        cohort = EvaluationCohort("iteration", probes, 60)
        cohort.start(0)
        results = cohort.complete(probes, 60)
        children = strategy.evolve(list(results), [], config).offspring
        self.assertEqual(len(children), 4)
        for child in children:
            self.assert_valid(child, config)
        self.assertTrue(any(any(float(vector[i]) != getattr(child, name) for i, name in enumerate(strategy._gene_names))
                            for child, vector in zip(children, strategy._pending_vectors)))

    def test_shared_browser_api_configuration_fixtures(self):
        cases = json.loads((Path(__file__).parent / "fixtures/genome-config-contract.json").read_text())
        for case in cases:
            with self.subTest(case=case["name"]):
                if case["accepted"]:
                    request = StartRequest(colony_config=case["config"])
                    config = build_colony_config(request)
                    self.assert_valid(random_genome(colony_config=config), config)
                    serialized = config.to_dict()
                    serialized.pop("mutation_rate", None)
                    rebuilt = build_colony_config(StartRequest(colony_config=serialized, mutation_rate=config.mutation_rate))
                    self.assertEqual(config.resolve_gene_domains(), rebuilt.resolve_gene_domains())
                else:
                    with self.assertRaises(ValueError):
                        StartRequest(colony_config=case["config"])


if __name__ == "__main__":
    unittest.main()
