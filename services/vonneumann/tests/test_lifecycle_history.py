"""Offline terminal persistence, bounded history, and sealed generation regressions."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_funding_continuity import ConstantFeed, PlannedStrategy

with deny_network():
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.genesis import GenesisController, _GenerationAggregate, LIFECYCLE_POLICY
    from vonneumann.core.genome import Genome
    from vonneumann.core.gene_registry import GENE_REGISTRY
    from vonneumann.core.evolution import NUMERIC_GENES
    from vonneumann.core.funding import FundingError
    from vonneumann.core.probe import Probe
    from vonneumann.core.types import EventType, ProbeEvent, ProbeState, TradeRecord
    from vonneumann.core.strategies.base import EvolutionResult
    from vonneumann.db.repository import EventPersister, VonNeumannRepository, PersistenceError


class MemoryQuery:
    """Owner-scoped, JSON-roundtrippable ledger; no connection or credentials."""
    def __init__(self, database, table):
        self.db, self.table = database, table
        self.filters = []

    def insert(self, fields):
        self.operation, self.fields = "insert", deepcopy(fields)
        return self

    def upsert(self, fields, **kwargs):
        self.operation, self.fields = "upsert", deepcopy(fields)
        self.conflict = kwargs.get("on_conflict", "id").split(",")
        return self

    def update(self, fields):
        self.operation, self.fields = "update", deepcopy(fields)
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        if self.operation == "insert":
            rows.append(self.fields)
            return SimpleNamespace(data=[deepcopy(self.fields)])
        if self.operation == "upsert":
            for row in rows:
                if all(row.get(k) == self.fields.get(k) for k in self.conflict):
                    row.update(self.fields)
                    return SimpleNamespace(data=[deepcopy(row)])
            rows.append(self.fields)
            return SimpleNamespace(data=[deepcopy(self.fields)])
        changed = []
        for row in rows:
            if all(row.get(key) == value for key, value in self.filters):
                row.update(self.fields)
                changed.append(deepcopy(row))
        return SimpleNamespace(data=changed)


class MemoryLedger:
    def __init__(self, tables=None):
        self.tables = deepcopy(tables or {})

    def table(self, name):
        return MemoryQuery(self, name)

    def restart(self):
        return MemoryLedger(json.loads(json.dumps(self.tables, allow_nan=False)))


class ProbeHistoryTests(OfflineTestMixin, unittest.TestCase):
    def trade(self, index, pnl):
        return TradeRecord(str(index), "probe", "SOL/USDC", "BUY", 100.0, 20.0,
                           exit_price=100.0 + pnl, pnl=pnl)

    def test_recent_trade_retention_preserves_lifetime_metrics_and_direct_appends(self):
        probe = Probe(Genome(assets=["SOL/USDC"]), 100.0)
        trades = [self.trade(i, pnl) for i, pnl in enumerate([2.0, -1.0, 0.0, 3.0, -2.0, 4.0, 5.0])]
        with patch("vonneumann.core.probe.CLOSED_TRADE_RETENTION", 3):
            probe.closed_trades.extend(trades)
            self.assertEqual(probe.num_trades, 7)
            self.assertEqual(probe.closed_trades, trades[-3:])
            self.assertEqual(probe.winning_trades, 4)
            self.assertAlmostEqual(probe.win_rate, 4 / 7)
            self.assertEqual(probe.total_pnl, 11.0)
            probe.closed_trades.append(self.trade(8, -3.0))
            summary = probe.summary()
            self.assertEqual(summary["total_trades"], 8)
            self.assertEqual(summary["winning_trades"], 4)
            self.assertEqual(summary["total_pnl"], 8.0)
            self.assertEqual(len(probe.closed_trades), 3)
            before = deepcopy((probe.closed_trades, probe._evicted_trade_count, probe._evicted_trade_pnl))
            probe._projected_summary([])
            self.assertEqual((probe.closed_trades, probe._evicted_trade_count, probe._evicted_trade_pnl), before)

    def test_retention_cannot_hide_bad_history_or_partially_increment_totals(self):
        probe = Probe(Genome(), 100.0)
        probe.closed_trades.extend([self.trade(0, math.inf), self.trade(1, 2.0)])
        with patch("vonneumann.core.probe.CLOSED_TRADE_RETENTION", 1):
            with self.assertRaises(ValueError):
                probe.num_trades
        self.assertEqual(len(probe.closed_trades), 2)
        self.assertEqual(probe._evicted_trade_count, 0)

    def test_death_emits_explicit_final_summary_after_intent_and_reproduction_does_not(self):
        when = datetime(2020, 1, 1, tzinfo=timezone.utc)
        probe = Probe(Genome(), 100.0, clock=lambda: when)
        probe.state = ProbeState.TRADING
        reproduce = probe._trigger_reproduce()
        self.assertEqual([e.event_type for e in reproduce], [EventType.PROBE_REPRODUCING])
        self.assertIsNone(probe.died_at)
        self.assertIsNone(reproduce[0].data["death_reason"])
        other = Probe(Genome(), 100.0, clock=lambda: when)
        other.state = ProbeState.TRADING
        death = other._trigger_die("max_lifespan")
        self.assertEqual([e.event_type for e in death], [EventType.PROBE_DYING, EventType.PROBE_DEAD])
        self.assertEqual(death[-1].data["state"], "DEAD")
        self.assertEqual(death[-1].data["died_at"], when.isoformat())
        self.assertEqual(death[-1].data["death_reason"], "max_lifespan")
        self.assertEqual(death[-1].timestamp, when)

    def test_online_generation_numeric_rms_matches_all_pairs_without_genome_storage(self):
        genomes = [Genome(rsi_period=period, assets=["SOL/USDC"]) for period in [5, 10, 20, 30]]
        probes = [Probe(genome, 100.0) for genome in genomes]
        aggregate = _GenerationAggregate(probes[0].born_at)
        for probe in probes:
            aggregate.born(probe)
            aggregate.unacknowledged_births -= 1
            aggregate.terminal(probe)
        distances = []
        for i, left in enumerate(genomes):
            for right in genomes[i+1:]:
                distances.append(sum(((getattr(left, name) - getattr(right, name)) /
                                      (GENE_REGISTRY.get(name).max - GENE_REGISTRY.get(name).min or 1)) ** 2
                                     for name in NUMERIC_GENES))
        expected = round(math.sqrt(sum(distances) / len(distances)), 4)
        self.assertEqual(aggregate.summary(0, probes[0].born_at)["genome_diversity"], expected)
        self.assertEqual(LIFECYCLE_POLICY["generation_diversity_assets"], "excluded")


class LifecycleHistoryTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.ledger = MemoryLedger()
        self.offline_stack.enter_context(patch("vonneumann.db.repository.get_supabase", return_value=self.ledger))
        self.persister = EventPersister(VonNeumannRepository(USER_A, A1))
        self.failure = None

    async def emit(self, event):
        if self.failure is not None and self.failure(event):
            raise PersistenceError("fixture_write")
        await self.persister.handle(event)
        self.events.append(deepcopy(event))

    async def controller(self, population=3, max_probes=6, cohorts=False):
        strategy = PlannedStrategy()
        strategy.supports_cohorts = cohorts
        controller = GenesisController(
            ConstantFeed(), strategy, A1, USER_A, gen0_count=population,
            max_probes=max_probes, max_capital=2000.0, seed_capital=100.0,
            diversity_threshold=0.0, on_event=self.emit,
            colony_config=ColonyConfig(available_assets=["SOL/USDC"]),
        )
        await controller.prepare()
        self.events.clear()
        return controller

    def child(self, generation=1):
        return Genome(assets=["SOL/USDC"], num_assets=1, generation=generation)

    async def die(self, controller, probe):
        for event in probe._trigger_die("max_lifespan"):
            await controller._emit(event)
        await controller._handle_die(probe)

    async def test_reproducing_intent_survives_failed_funding_and_restart_without_false_death(self):
        c = await self.controller(population=1, max_probes=1)
        parent = c.live_probes[0]
        parent.state = ProbeState.TRADING
        for event in parent._trigger_reproduce():
            await c._emit(event)
        with self.assertRaises(FundingError):
            await c._handle_self_reproduce(parent)
        row = self.ledger.restart().tables["vn_probes"][0]
        self.assertEqual(row["state"], "REPRODUCING")
        self.assertNotIn("died_at", row)
        self.assertNotIn("death_reason", row)
        self.assertIn(parent.probe_id, c.probes)
        self.assertEqual(c._archived_probe_count, 0)

    async def test_actual_parentage_and_culls_survive_history_readback_with_final_fields(self):
        c = await self.controller()
        parents = c.live_probes
        for parent in parents:
            parent.state = ProbeState.TRADING
        result = EvolutionResult([self.child(), self.child()], [p.probe_id for p in parents],
                                 {"0": [parents[0].probe_id, parents[1].probe_id], "1": [parents[1].probe_id]})
        await c._apply_replacement(result)
        restarted = self.ledger.restart()
        rows = restarted.tables["vn_probes"]
        for index, parent in enumerate(parents):
            row = next(r for r in rows if r["id"] == parent.probe_id)
            self.assertEqual(row["state"], "DEAD")
            self.assertEqual(row["death_reason"], "evolution_selected" if index < 2 else "evolution_culled")
            self.assertEqual(row["died_at"], parent.died_at.isoformat())
            self.assertEqual(row["current_capital"], 100.0)
        children = [r for r in rows if r["generation"] == 1]
        self.assertEqual(children[0]["parent_ids"], result.parent_map["0"])
        self.assertEqual(children[0]["parent_id"], result.parent_map["0"][0])
        self.assertEqual(restarted.tables["vn_generation_stats"][0]["reproduced_count"], 2)
        intents = [e.probe_id for e in self.events if e.event_type == EventType.PROBE_REPRODUCING]
        self.assertEqual(intents, [parents[0].probe_id, parents[1].probe_id])
        # New repository/persister reads the same persisted truth after process
        # replacement; this is history recovery, not an executable checkpoint.
        with patch("vonneumann.db.repository.get_supabase", return_value=restarted):
            new_repo = VonNeumannRepository(USER_A, A1)
            self.assertEqual(new_repo.db.tables, restarted.tables)

    async def test_terminal_write_failure_preserves_owned_cash_and_no_completion(self):
        c = await self.controller(population=1)
        parent = c.live_probes[0]
        reserve = c.reserve_capital
        self.failure = lambda event: event.event_type == EventType.PROBE_DEAD
        with self.assertRaises(PersistenceError):
            await c._apply_replacement(EvolutionResult([self.child()], [parent.probe_id]))
        self.assertEqual(c.reserve_capital, reserve)
        self.assertIs(c.probes[parent.probe_id], parent)
        self.assertEqual(c.active_capital, 100.0)
        self.assertEqual(c._archived_probe_count, 0)
        self.assertEqual(c.dead_probes, [])
        self.assertNotIn("vn_generation_stats", self.ledger.tables)
        self.assertEqual(self.ledger.tables["vn_probes"][0]["state"], "DYING")

    async def test_failed_terminal_aggregate_cannot_double_credit_owned_cash(self):
        for retirement in (True, False):
            with self.subTest(retirement=retirement):
                c = await self.controller(population=1, cohorts=True)
                parent = c.live_probes[0]
                reserve, active = c.reserve_capital, c.active_capital
                aggregate = c._generation_aggregates[0]
                # Force a partial aggregate update followed by failure, as a
                # malformed value or overflowing later statistic could do.
                def bad_terminal(target, probe):
                    target.terminal_count += 1
                    raise ArithmeticError("offline aggregate failure")
                with patch.object(_GenerationAggregate, "terminal", bad_terminal):
                    with self.assertRaises(ArithmeticError):
                        if retirement:
                            await c._apply_replacement(EvolutionResult([self.child()], [parent.probe_id]))
                        else:
                            await self.die(c, parent)
                self.assertEqual(c.reserve_capital, reserve)
                self.assertEqual(c.active_capital, active)
                self.assertIs(c.probes[parent.probe_id], parent)
                self.assertIs(c._generation_aggregates[0], aggregate)
                self.assertEqual(aggregate.terminal_count, 0)
                self.assertEqual(c._archived_probe_count, 0)

    async def test_failed_birth_cannot_seal_or_complete_prior_generation(self):
        c = await self.controller(population=1)
        parent = c.live_probes[0]
        self.failure = lambda e: e.event_type == EventType.PROBE_BORN and e.data["generation"] == 1
        with self.assertRaises(PersistenceError):
            await c._apply_replacement(EvolutionResult([self.child()], [parent.probe_id]))
        self.assertFalse(c._generation_aggregates[0].sealed)
        self.assertEqual(c._birth_generation_floor, 0)
        self.assertEqual(c._generation_aggregates[1].unacknowledged_births, 1)
        self.assertNotIn("vn_generation_stats", self.ledger.tables)

    async def test_generation_write_failure_retries_without_losing_or_duplicating_completion(self):
        c = await self.controller(population=1)
        parent = c.live_probes[0]
        self.failure = lambda e: e.event_type == EventType.GENERATION_COMPLETE
        with self.assertRaises(PersistenceError):
            await c._apply_replacement(EvolutionResult([self.child()], [parent.probe_id]))
        self.assertTrue(c._generation_aggregates[0].sealed)
        self.assertNotIn(0, c._emitted_generation_stats)
        self.failure = None
        await c._maybe_emit_generation_stats(0)
        await c._maybe_emit_generation_stats(0)
        self.assertNotIn(0, c._generation_aggregates)
        self.assertEqual(len(self.ledger.tables["vn_generation_stats"]), 1)
        self.assertEqual(len([e for e in self.events if e.event_type == EventType.GENERATION_COMPLETE]), 1)

    async def test_all_early_dead_current_cohort_remains_valid_after_cache_eviction(self):
        c = await self.controller(population=4, cohorts=True)
        parents = c.live_probes
        c._cohort.start(c._event_time().timestamp())
        with patch("vonneumann.core.genesis.DEAD_PROBE_RETENTION", 1):
            for parent in parents:
                await self.die(c, parent)
        self.assertEqual(len(c.dead_probes), 1)
        self.assertEqual(c.status()["dead_probes"], 4)
        self.assertNotIn("vn_generation_stats", self.ledger.tables)
        ids = [p.probe_id for p in parents]
        await c._apply_replacement(EvolutionResult([self.child() for _ in parents], [],
                                                  {str(i): ids for i in range(4)}))
        stats = self.ledger.tables["vn_generation_stats"][0]
        self.assertEqual((stats["total_probes"], stats["dead_probes"], stats["reproduced_count"]), (4, 4, 4))
        c._bind_evaluation()
        self.assertTrue(set(c._cohort_parent_generations).isdisjoint(ids))

    async def test_same_generation_diversity_births_prevent_premature_completion(self):
        c = await self.controller(population=1)
        first = c.live_probes[0]
        await self.die(c, first)  # Legacy strategy injects replacement in generation zero.
        self.assertEqual(len(c.live_probes), 1)
        self.assertEqual(c.live_probes[0].genome.generation, 0)
        self.assertNotIn("vn_generation_stats", self.ledger.tables)
        self.assertEqual(c._generation_aggregates[0].count, 2)
        await c._apply_replacement(EvolutionResult([self.child()], list(c.probes)))
        stats = self.ledger.tables["vn_generation_stats"][0]
        self.assertEqual(stats["total_probes"], 2)
        self.assertEqual(stats["dead_probes"], 2)

    async def test_old_surviving_parent_uses_open_birth_generation(self):
        c = await self.controller(population=2)
        old, advancing = c.live_probes
        await c._apply_replacement(EvolutionResult([self.child(3)], [advancing.probe_id]))
        old.state = ProbeState.TRADING
        for event in old._trigger_reproduce():
            await c._emit(event)
        await c._handle_self_reproduce(old)
        self.assertEqual(c._birth_generation_floor, 3)
        children = [p for p in c.live_probes if old.probe_id in p.genome.parent_ids]
        self.assertEqual(len(children), 2)
        self.assertTrue(all(p.genome.generation == 3 for p in children))

    async def test_bounded_completed_state_and_lifetime_counts_over_many_generations(self):
        c = await self.controller(population=1)
        with patch("vonneumann.core.genesis.DEAD_PROBE_RETENTION", 3), patch(
                "vonneumann.core.genesis.GENERATION_HISTORY_RETENTION", 2):
            for generation in range(1, 21):
                await c._apply_replacement(EvolutionResult([self.child(generation)], list(c.probes)))
        self.assertEqual(len(c.dead_probes), 3)
        self.assertEqual(c.status()["dead_probes"], 20)
        self.assertEqual(c.status()["total_probes"], 21)
        self.assertEqual(len(c._generation_aggregates), 1)
        self.assertEqual(len(c._generation_probe_counts), 1)
        self.assertEqual(len(c._emitted_generation_stats), 2)
        self.assertLessEqual(len(c._generation_dead_counts), 1)
        self.assertLessEqual(len(c._generation_reproduced), 1)
        self.assertEqual(len(self.ledger.restart().tables["vn_generation_stats"]), 20)
        with self.assertRaises(FundingError):
            await c._apply_replacement(EvolutionResult([self.child(0)], list(c.probes)))
        self.assertEqual(c._archived_probe_count, 20)

    async def test_incomplete_terminal_and_duplicate_lineage_are_rejected_before_write(self):
        with self.assertRaises(ValueError):
            await self.persister.handle(ProbeEvent(EventType.PROBE_DEAD, "missing", {"state": "DEAD"}))
        with self.assertRaises(ValueError):
            await self.persister.handle(ProbeEvent(EventType.PROBE_BORN, "missing", {"genome": {"parent_ids": ["p", "p"]}}))
        self.assertEqual(self.ledger.tables, {})


if __name__ == "__main__":
    unittest.main()
