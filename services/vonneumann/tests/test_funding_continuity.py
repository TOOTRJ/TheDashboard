"""Offline funding regressions with real optimizers and probe accounting.

The constant-price tests intentionally avoid trading and tick timing so market
returns cannot conceal capital shrinkage caused by population replacement.
"""

from __future__ import annotations

import copy
import math
import random
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.funding import FundingError
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.genome import Genome
    from vonneumann.core.strategies.base import EvolutionResult, EvolutionStrategy
    from vonneumann.core.strategies.cma_es import CMAEvolutionStrategy
    from vonneumann.core.strategies.genetic_algorithm import GeneticAlgorithmStrategy
    from vonneumann.core.strategies.particle_swarm import ParticleSwarmStrategy
    from vonneumann.core.types import EventType, ProbeState
    from vonneumann.db.repository import PersistenceError
    from vonneumann.market.feed import MarketTick


ASSET = "SOL/USDC"


class ConstantFeed:
    async def get_ticks(self, assets):
        return {asset: MarketTick(asset, 100.0, 1_000.0, 0.0) for asset in assets}


class PlannedStrategy(EvolutionStrategy):
    """A fixed evolution plan for boundary cases real strategies rarely emit."""

    name = "funding_test_plan"
    label = "Offline funding plan"

    def __init__(self):
        self.result = EvolutionResult([], [])

    def initialize(self, probes, colony_config):
        pass

    def evolve(self, probes, dead_probes, colony_config):
        return self.result


class FundingContinuityTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        random_state = random.getstate()
        self.addCleanup(random.setstate, random_state)
        random.seed(8128)
        self.events = []

    async def controller(self, strategy=None, *, capital=1_000.0, population=6,
                         max_probes=6, seed=100.0):
        async def event(value):
            self.events.append(value)

        controller = GenesisController(
            ConstantFeed(), strategy or PlannedStrategy(), A1, USER_A,
            gen0_count=population, max_probes=max_probes, max_capital=capital,
            seed_capital=seed, diversity_threshold=0.0, on_event=event,
            colony_config=ColonyConfig(
                enabled_genes=["rsi_period", "rsi_oversold"],
                available_assets=[ASSET],
            ),
        )
        await controller.prepare()
        if isinstance(controller.strategy, CMAEvolutionStrategy):
            # Seed the real installed optimizer, rather than replacing ask/tell.
            controller.strategy._optimizer.reseed_rng(8128)
        self.events.clear()
        return controller

    def plan(self, controller, *, retire=(), count=0):
        children = [Genome(assets=[ASSET], generation=1) for _ in range(count)]
        controller.strategy.result = EvolutionResult(children, list(retire))
        return controller.strategy.result

    def snapshot(self, controller):
        return {
            "reserve": controller.reserve_capital,
            "active": controller.active_capital,
            "deployed": controller.total_deployed,
            "generation": controller.current_generation,
            "dead": [probe.probe_id for probe in controller.dead_probes],
            "probes": {
                key: (probe.state, probe.capital, copy.deepcopy(probe.open_positions),
                      copy.deepcopy(probe.closed_trades))
                for key, probe in controller.probes.items()
            },
        }

    async def assert_rejected_without_retirement(self, controller, code):
        before, events = self.snapshot(controller), list(self.events)
        with patch.object(controller, "_retire_probe",
                          new=AsyncMock(wraps=controller._retire_probe)) as retire:
            with self.assertRaises(FundingError) as raised:
                await controller._evaluate_reproduction()
            self.assertEqual(raised.exception.code, code)
            retire.assert_not_awaited()
        self.assertEqual(self.snapshot(controller), before)
        self.assertEqual(self.events, events)

    def open_position(self, controller, probe, *, exit_price):
        probe.genome.position_size_pct = 0.5
        probe.on_price_update(ASSET, 100.0, 1_000.0)
        self.assertIsNotNone(probe._open_position(ASSET, 100.0, {}))
        probe.on_price_update(ASSET, exit_price, 1_000.0)
        controller._latest_prices[ASSET] = exit_price
        self.assertEqual(probe.capital, 50.0)

    async def assert_sixty_replacements(self, strategy):
        controller = await self.controller(strategy, capital=600.0)
        self.assertEqual(controller.capital_split, 0.45)
        for cycle in range(1, 61):
            previous_ids = set(controller.probes)
            await controller._evaluate_reproduction()
            with self.subTest(strategy=strategy.name, cycle=cycle):
                self.assertEqual(len(controller.live_probes), 6)
                self.assertTrue(previous_ids.isdisjoint(controller.probes))
                self.assertEqual(controller.current_generation, cycle)
                self.assertEqual(len(controller.dead_probes), cycle * 6)
                self.assertAlmostEqual(controller.reserve_capital, 0.0, places=9)
                self.assertAlmostEqual(controller.active_capital, 600.0, places=9)
                self.assertAlmostEqual(controller.reserve_capital +
                                       controller.active_capital, 600.0, places=9)
                for probe in controller.live_probes:
                    self.assertEqual(probe.initial_capital, 100.0)
                    self.assertEqual(probe.capital, 100.0)
                    self.assertEqual(probe.roi, 0.0)
                    self.assertEqual(probe.num_trades, 0)
                if isinstance(strategy, ParticleSwarmStrategy):
                    self.assertEqual(set(strategy._velocities), set(controller.probes))
                    self.assertEqual(set(strategy._personal_best), set(controller.probes))

    async def test_real_particle_swarm_preserves_full_population_for_sixty_cycles(self):
        await self.assert_sixty_replacements(ParticleSwarmStrategy())

    async def test_real_cma_es_preserves_full_population_for_sixty_cycles(self):
        await self.assert_sixty_replacements(CMAEvolutionStrategy())

    async def test_real_ga_partial_replacement_uses_reserve_for_equal_budgets(self):
        controller = await self.controller(GeneticAlgorithmStrategy(), population=10,
                                           max_probes=13, capital=1_300.0)
        for probe in controller.live_probes:
            probe.genome.position_size_pct = 0.5
            for _ in range(3):
                self.assertIsNotNone(probe._open_position(ASSET, 100.0, {}))
                self.assertIsNotNone(probe._close_position(ASSET, 100.0, "TEST"))
        original_ids = set(controller.probes)
        await controller._evaluate_reproduction()
        self.assertEqual(len(controller.dead_probes), 3)
        self.assertEqual(len(controller.live_probes), 13)
        self.assertEqual(len(set(controller.probes) & original_ids), 7)
        self.assertEqual(sum(p.genome.generation == 1 for p in controller.live_probes), 6)
        self.assertTrue(all(p.initial_capital == 100.0 for p in controller.live_probes))
        self.assertAlmostEqual(controller.reserve_capital, 0.0)
        self.assertAlmostEqual(controller.active_capital, 1_300.0)

    async def test_no_retire_children_are_fully_funded_from_reserve(self):
        controller = await self.controller(population=2, max_probes=4, capital=400.0)
        original_ids = set(controller.probes)
        self.plan(controller, count=2)
        await controller._evaluate_reproduction()
        self.assertEqual(len(controller.live_probes), 4)
        self.assertTrue(original_ids.issubset(controller.probes))
        self.assertEqual(controller.dead_probes, [])
        self.assertEqual(controller.reserve_capital, 0.0)
        self.assertEqual(controller.active_capital, 400.0)
        self.assertTrue(all(p.initial_capital == 100.0 for p in controller.live_probes))

    async def test_profit_and_loss_change_reserve_without_changing_candidate_budget(self):
        for exit_price, pnl in ((120.0, 10.0), (80.0, -10.0)):
            with self.subTest(exit_price=exit_price):
                controller = await self.controller(capital=1_000.0)
                parent = controller.live_probes[0]
                self.open_position(controller, parent, exit_price=exit_price)
                self.plan(controller, retire=controller.probes, count=6)
                self.assertAlmostEqual(controller.active_capital +
                                       controller.reserve_capital, 1_000.0 + pnl)
                await controller._evaluate_reproduction()
                self.assertEqual(len(controller.live_probes), 6)
                self.assertTrue(all(p.capital == 100.0 for p in controller.live_probes))
                self.assertEqual(parent.open_positions, {})
                self.assertAlmostEqual(parent.closed_trades[-1].pnl, pnl)
                self.assertAlmostEqual(controller.reserve_capital, 400.0 + pnl)
                self.assertAlmostEqual(controller.active_capital +
                                       controller.reserve_capital, 1_000.0 + pnl)
                closed = [e for e in self.events if e.event_type == EventType.TRADE_CLOSED]
                self.assertEqual(len(closed), 1)

    async def test_unaffordable_full_replacement_keeps_original_positions_open(self):
        controller = await self.controller(capital=600.0)
        self.open_position(controller, controller.live_probes[0], exit_price=80.0)
        self.plan(controller, retire=controller.probes, count=6)
        await self.assert_rejected_without_retirement(controller, "funding_insufficient")

    async def test_unaffordable_no_retire_plan_does_not_partially_spawn(self):
        controller = await self.controller(population=2, max_probes=4, capital=350.0)
        self.plan(controller, count=2)
        await self.assert_rejected_without_retirement(controller, "funding_insufficient")

    async def test_capacity_failure_keeps_every_parent_before_partial_replacement(self):
        controller = await self.controller(capital=1_000.0, max_probes=6)
        self.plan(controller, retire=list(controller.probes)[:2], count=3)
        await self.assert_rejected_without_retirement(controller, "funding_capacity")

    async def test_unknown_retirement_id_cannot_fund_an_extra_child(self):
        controller = await self.controller()
        self.plan(controller, retire=[*controller.probes, "unknown-probe"], count=6)
        await self.assert_rejected_without_retirement(controller, "funding_invalid_plan")

    async def test_duplicate_retirement_id_cannot_count_cash_or_capacity_twice(self):
        controller = await self.controller()
        first = next(iter(controller.probes))
        self.plan(controller, retire=[first, first], count=2)
        await self.assert_rejected_without_retirement(controller, "funding_invalid_plan")

    async def test_invalid_liquidation_prices_cannot_create_funds(self):
        for price in (0.0, -1.0, float("inf"), float("nan")):
            with self.subTest(price=price):
                controller = await self.controller()
                parent = controller.live_probes[0]
                self.open_position(controller, parent, exit_price=100.0)
                controller._latest_prices[ASSET] = price
                parent._price_buffer[ASSET] = []
                self.plan(controller, retire=controller.probes, count=6)
                await self.assert_rejected_without_retirement(controller, "funding_invalid_plan")

    async def test_self_reproduction_funds_equal_children_and_is_idempotent(self):
        controller = await self.controller(population=2, max_probes=3, capital=300.0)
        parent = controller.live_probes[0]
        parent._transition(ProbeState.TRADING)
        parent._trigger_reproduce()
        await controller._handle_self_reproduce(parent)
        self.assertEqual(len(controller.live_probes), 3)
        self.assertEqual(controller.dead_probes, [parent])
        self.assertNotIn(parent.probe_id, controller.probes)
        children = [p for p in controller.live_probes if p.genome.generation == 1]
        self.assertEqual(len(children), 2)
        self.assertTrue(all(p.initial_capital == 100.0 for p in children))
        self.assertTrue(all(p.genome.parent_ids == [parent.probe_id] for p in children))
        self.assertEqual(controller.reserve_capital, 0.0)
        self.assertEqual(controller.active_capital, 300.0)
        completed, events = self.snapshot(controller), list(self.events)
        await controller._handle_self_reproduce(parent)
        self.assertEqual(self.snapshot(controller), completed)
        self.assertEqual(self.events, events)

    async def test_self_reproduction_rejection_retains_parent_intent_and_cash(self):
        for max_probes, capital, code in (
            (3, 200.0, "funding_insufficient"),
            (2, 300.0, "funding_capacity"),
        ):
            with self.subTest(code=code):
                controller = await self.controller(population=2, max_probes=max_probes,
                                                   capital=capital)
                parent = controller.live_probes[0]
                parent._transition(ProbeState.TRADING)
                parent._trigger_reproduce()
                before, events = self.snapshot(controller), list(self.events)
                with self.assertRaises(FundingError) as raised:
                    await controller._handle_self_reproduce(parent)
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(self.snapshot(controller), before)
                self.assertEqual(parent.state, ProbeState.REPRODUCING)
                self.assertEqual(self.events, events)

    async def test_death_handler_never_credits_same_probe_twice(self):
        controller = await self.controller(population=4, max_probes=4, capital=400.0)
        parent = controller.live_probes[0]
        parent._trigger_die("TEST")
        await controller._handle_die(parent)
        self.assertEqual(len(controller.live_probes), 3)
        self.assertEqual(controller.dead_probes, [parent])
        self.assertEqual(controller.reserve_capital, 100.0)
        self.assertEqual(controller.active_capital, 300.0)
        completed = self.snapshot(controller)
        dead_counts = dict(controller._generation_dead_counts)
        events = list(self.events)
        await controller._handle_die(parent)
        self.assertEqual(self.snapshot(controller), completed)
        self.assertEqual(controller._generation_dead_counts, dead_counts)
        self.assertEqual(self.events, events)

    async def test_fractional_exact_budget_survives_sixty_replacements(self):
        controller = await self.controller(ParticleSwarmStrategy(), capital=199.98,
                                           seed=33.33)
        for cycle in range(60):
            await controller._evaluate_reproduction()
            self.assertEqual(len(controller.live_probes), 6, f"cycle {cycle + 1}")
            self.assertTrue(all(p.initial_capital == 33.33 for p in controller.live_probes))
            self.assertAlmostEqual(controller.reserve_capital, 0.0, places=9)
            self.assertAlmostEqual(controller.reserve_capital + controller.active_capital,
                                   199.98, places=9)

    async def test_optional_diversity_requests_only_funded_available_slots(self):
        controller = await self.controller(population=2, max_probes=3, capital=300.0)
        controller.diversity_threshold = 0.5

        def inject(*args, count, **kwargs):
            return [Genome(assets=[ASSET], generation=1) for _ in range(count)]

        with patch.object(controller.strategy, "compute_diversity", return_value=0.0), \
             patch.object(controller.strategy, "inject_diversity", side_effect=inject) as request:
            await controller._check_diversity()
        request.assert_called_once()
        self.assertEqual(request.call_args.kwargs["count"], 1)
        self.assertEqual(len(controller.live_probes), 3)
        self.assertEqual(controller.reserve_capital, 0.0)
        self.assertEqual(controller.active_capital, 300.0)

    async def test_optional_diversity_skips_unaffordable_or_full_population(self):
        for max_probes, capital in ((3, 250.0), (2, 1_000.0)):
            with self.subTest(max_probes=max_probes, capital=capital):
                controller = await self.controller(population=2, max_probes=max_probes,
                                                   capital=capital)
                controller.diversity_threshold = 0.5
                before = self.snapshot(controller)
                with patch.object(controller.strategy, "compute_diversity", return_value=0.0), \
                     patch.object(controller.strategy, "inject_diversity") as request:
                    await controller._check_diversity()
                request.assert_not_called()
                self.assertEqual(self.snapshot(controller), before)

    async def test_failed_birth_persistence_preserves_partial_ledger_without_retry(self):
        controller = await self.controller()
        self.plan(controller, retire=controller.probes, count=6)
        births = []

        async def persist(event):
            if event.event_type == EventType.PROBE_BORN:
                births.append(event.probe_id)
                if len(births) == 2:
                    raise PersistenceError("insert_probe")

        controller._on_event = persist
        with self.assertRaises(PersistenceError):
            await controller._evaluate_reproduction()
        self.assertEqual(len(births), 2)
        self.assertEqual(set(controller.probes), set(births))
        self.assertEqual(len(controller.dead_probes), 6)
        self.assertEqual(controller.reserve_capital, 800.0)
        self.assertEqual(controller.active_capital, 200.0)
        self.assertEqual(controller.reserve_capital + controller.active_capital, 1_000.0)

    async def test_failed_retirement_persistence_keeps_partial_ledger_reconcilable(self):
        controller = await self.controller()
        original_ids = set(controller.probes)
        self.plan(controller, retire=controller.probes, count=6)
        retire_events = []

        async def persist(event):
            if event.event_type == EventType.PROBE_DYING:
                retire_events.append(event.probe_id)
                if len(retire_events) == 2:
                    raise PersistenceError("update_probe")

        controller._on_event = persist
        with self.assertRaises(PersistenceError):
            await controller._evaluate_reproduction()
        self.assertEqual(len(retire_events), 2)
        self.assertEqual(set(controller.probes) |
                         {p.probe_id for p in controller.dead_probes}, original_ids)
        self.assertEqual(controller.reserve_capital +
                         sum(p.total_value for p in controller.probes.values()), 1_000.0)
        self.assertFalse(any(p.genome.generation > 0 for p in controller.probes.values()))

    async def test_last_death_reports_extinction_without_creating_seed_money(self):
        controller = await self.controller(population=2, max_probes=2, capital=200.0)
        parents = list(controller.live_probes)
        for probe in parents:
            probe.genome.position_size_pct = 1.0
            probe.on_price_update(ASSET, 100.0, 1_000.0)
            self.assertIsNotNone(probe._open_position(ASSET, 100.0, {}))
            probe.on_price_update(ASSET, 10.0, 1_000.0)
            probe._trigger_die("drawdown")
        await controller._handle_die(parents[0])
        with self.assertRaises(FundingError) as raised:
            await controller._handle_die(parents[1])
        self.assertEqual(raised.exception.code, "population_extinct")
        self.assertEqual(controller.probes, {})
        self.assertEqual(controller.dead_probes, parents)
        self.assertEqual(controller.reserve_capital, 20.0)
        self.assertEqual(controller.active_capital, 0.0)
        with self.assertRaises(FundingError) as empty_tick:
            await controller._tick_all()
        self.assertEqual(empty_tick.exception.code, "population_extinct")

    async def test_latest_liquidation_quote_controls_budget_instead_of_old_buffer(self):
        for latest, buffered, accepted in ((80.0, 120.0, False), (120.0, 80.0, True)):
            with self.subTest(latest=latest, buffered=buffered):
                controller = await self.controller(capital=600.0)
                parent = controller.live_probes[0]
                self.open_position(controller, parent, exit_price=buffered)
                controller._latest_prices[ASSET] = latest
                self.plan(controller, retire=controller.probes, count=6)
                if accepted:
                    await controller._evaluate_reproduction()
                    self.assertEqual(len(controller.live_probes), 6)
                    self.assertEqual(parent.closed_trades[-1].exit_price, latest)
                    self.assertEqual(controller.active_capital, 600.0)
                    self.assertEqual(controller.reserve_capital, 10.0)
                else:
                    await self.assert_rejected_without_retirement(controller,
                                                                  "funding_insufficient")

    async def test_invalid_offspring_or_lineage_is_rejected_before_any_retirement(self):
        cases = ("not_genome", "nan_gene", "inf_gene", "negative_gene", "empty_assets",
                 "unknown_asset", "duplicate_assets", "invalid_generation", "unknown_parent",
                 "invalid_parent_map_index")
        for case in cases:
            with self.subTest(case=case):
                controller = await self.controller()
                result = self.plan(controller, retire=controller.probes, count=6)
                child = result.offspring[0]
                if case == "not_genome":
                    result.offspring[0] = {"assets": [ASSET]}
                elif case == "nan_gene":
                    child.position_size_pct = float("nan")
                elif case == "inf_gene":
                    child.position_size_pct = float("inf")
                elif case == "negative_gene":
                    child.position_size_pct = -1.0
                elif case == "empty_assets":
                    child.assets = []
                elif case == "unknown_asset":
                    child.assets = ["UNKNOWN/USDC"]
                elif case == "duplicate_assets":
                    child.assets = [ASSET, ASSET]
                elif case == "invalid_generation":
                    child.generation = True
                elif case == "unknown_parent":
                    result.parent_map = {"0": ["unknown-probe"]}
                else:
                    result.parent_map = {"99": [next(iter(controller.probes))]}
                await self.assert_rejected_without_retirement(controller, "funding_invalid_plan")

    async def test_invalid_ledger_values_reject_replacement_before_state_changes(self):
        for field in ("reserve_capital", "seed_capital", "parent_capital"):
            for value in (float("nan"), float("inf"), -1.0):
                with self.subTest(field=field, value=value):
                    controller = await self.controller()
                    parent = controller.live_probes[0]
                    if field == "parent_capital":
                        parent.capital = value
                    else:
                        setattr(controller, field, value)
                    self.plan(controller, retire=controller.probes, count=6)
                    before = repr(self.snapshot(controller))
                    events = list(self.events)
                    with patch.object(controller, "_retire_probe", new=AsyncMock()) as retire:
                        with self.assertRaises(FundingError) as raised:
                            await controller._evaluate_reproduction()
                        self.assertEqual(raised.exception.code, "funding_invalid_plan")
                        retire.assert_not_awaited()
                    self.assertEqual(repr(self.snapshot(controller)), before)
                    self.assertEqual(self.events, events)

    async def test_invalid_reserve_is_rejected_before_death_credits_or_archives(self):
        for value in (float("nan"), float("inf"), -1.0):
            with self.subTest(value=value):
                controller = await self.controller(population=4, max_probes=4, capital=400.0)
                parent = controller.live_probes[0]
                parent._trigger_die("TEST")
                controller.reserve_capital = value
                before = repr(self.snapshot(controller))
                events = list(self.events)
                with self.assertRaises(FundingError) as raised:
                    await controller._handle_die(parent)
                self.assertEqual(raised.exception.code, "funding_invalid_plan")
                self.assertEqual(repr(self.snapshot(controller)), before)
                self.assertEqual(self.events, events)

    async def test_simultaneous_deaths_pool_recoverable_cash_before_extinction(self):
        controller = await self.controller(population=2, max_probes=2, capital=200.0)
        parents = list(controller.live_probes)
        for probe in parents:
            probe.genome.position_size_pct = 1.0
            probe.on_price_update(ASSET, 100.0, 1_000.0)
            self.assertIsNotNone(probe._open_position(ASSET, 100.0, {}))
            probe.on_price_update(ASSET, 50.0, 1_000.0)
            probe._trigger_die("drawdown")
        await controller._handle_die(parents[0])
        self.assertEqual(controller.reserve_capital, 50.0)
        self.assertEqual(controller.active_capital, 50.0)
        self.assertIn(parents[1].probe_id, controller.probes)
        await controller._handle_die(parents[1])
        self.assertEqual(controller.dead_probes, parents)
        self.assertEqual(len(controller.live_probes), 1)
        self.assertEqual(controller.live_probes[0].initial_capital, 100.0)
        self.assertEqual(controller.reserve_capital, 0.0)
        self.assertEqual(controller.active_capital, 100.0)

    async def test_mixed_retirement_roundoff_shortfall_is_rejected_before_retirement(self):
        controller = await self.controller(population=4, max_probes=4,
                                           seed=10_000_000.0, capital=40_000_000.0)
        proceeds = [16_483_721.21, 9_624_465.08, 11_582_861.44, 2_308_952.269999996]
        for parent, cash in zip(controller.live_probes, proceeds):
            parent.capital = cash
        # Rounding each total first hides a real shortfall in the float inputs.
        self.assertEqual(math.fsum(proceeds), 40_000_000.0)
        self.assertLess(math.fsum([*proceeds, *([-10_000_000.0] * 4)]), -1e-9)
        self.plan(controller, retire=controller.probes, count=4)
        await self.assert_rejected_without_retirement(controller, "funding_insufficient")

    async def test_sufficient_mixed_retirement_proceeds_fund_entire_batch(self):
        controller = await self.controller(population=4, max_probes=4,
                                           seed=10_000_000.0, capital=40_000_000.0)
        proceeds = [16_483_721.21, 9_624_465.08, 11_582_861.44, 2_308_952.279999996]
        for parent, cash in zip(controller.live_probes, proceeds):
            parent.capital = cash
        self.plan(controller, retire=controller.probes, count=4)
        await controller._evaluate_reproduction()
        self.assertEqual(len(controller.dead_probes), 4)
        self.assertEqual(len(controller.live_probes), 4)
        self.assertTrue(all(p.initial_capital == 10_000_000.0 for p in controller.live_probes))
        self.assertGreater(controller.reserve_capital, 0.00999)
        self.assertLess(controller.reserve_capital, 0.01001)
        self.assertEqual(controller.active_capital, 40_000_000.0)
        self.assertAlmostEqual(controller.active_capital + controller.reserve_capital,
                               math.fsum(proceeds), places=7)

    async def test_large_fractional_exact_budget_survives_sixty_replacements(self):
        controller = await self.controller(ParticleSwarmStrategy(), population=28,
                                           max_probes=28, seed=100_000.01, capital=2_800_000.28)
        for cycle in range(60):
            await controller._evaluate_reproduction()
            self.assertEqual(len(controller.live_probes), 28, f"cycle {cycle + 1}")
            self.assertTrue(all(p.initial_capital == 100_000.01 for p in controller.live_probes))
            self.assertAlmostEqual(controller.reserve_capital, 0.0, places=9)
            self.assertAlmostEqual(controller.reserve_capital + controller.active_capital,
                                   2_800_000.28, places=8)


if __name__ == "__main__":
    unittest.main()
