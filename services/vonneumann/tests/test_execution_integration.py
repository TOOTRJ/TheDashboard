"""Offline end-to-end ledger and optimizer regressions for FILL-01A.

Independent Decimal fixtures deliberately do not call the fill implementation
to calculate expected amounts. The archive replay test injects known valid
next-observation entry intents so every real optimizer actually pays costs.
"""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import asyncio
import importlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_controller_cohorts import CandleQuoteFeed, CohortRecordingStrategy
from tests.test_source_time_controller import ControlledClock, FixedStrategy, MutableSourceFeed
from tests.test_repository_security import RecordingDB
from tests.test_search_replay import ALGORITHMS, config, snapshot

with deny_network():
    from fastapi.testclient import TestClient
    from pydantic import ValidationError
    from vonneumann.core.colony_config import ColonyConfig, GeneOverride
    from vonneumann.core.execution import ExecutionConfig, EXECUTION_VERSION
    from vonneumann.core.genesis import GenesisController
    from vonneumann.core.genome import Genome, NUMERIC_GENES
    from vonneumann.core.market_validation import MarketValueError
    from vonneumann.core.probe import Probe, _SignalIntent
    from vonneumann.core.strategies import get_strategy
    from vonneumann.core.strategies.base import EvolutionResult
    from vonneumann.core.types import EventType, ProbeEvent, ProbeState
    from vonneumann.db.repository import EventPersister, VonNeumannRepository
    from vonneumann.market.dataset_cli import generate_synthetic_dataset
    from vonneumann.market.replay_feed import ReplayFeed
    from vonneumann.market.sim_feed import SimulationFeed
    from vonneumann.server.models import StartRequest
    from vonneumann.server.auth import VerifiedUser, require_user
    app_module = importlib.import_module("vonneumann.server.app")

SOL, JUP = "SOL/USDC", "JUP/USDC"
START = 1_704_067_200.0
COSTS = ExecutionConfig(fee_bps=100, half_spread_bps=100, slippage_bps=100)


def genome(**overrides):
    return Genome(**{
        "assets": [SOL, JUP], "num_assets": 2, "timeframe_minutes": 5,
        "rsi_period": 5, "ema_fast": 3, "ema_slow": 10,
        "position_size_pct": .5, "max_open_positions": 2,
        "stop_loss_pct": .1, "take_profit_pct": .2,
        "death_drawdown_pct": .35, "benchmark_target_pct": .15,
        "reproduce_target_dollars": 50, **overrides,
    })


def probe_state(probe):
    return deepcopy({name: getattr(probe, name) for name in (
        "capital", "peak_capital", "_max_drawdown", "state", "open_positions",
        "closed_trades", "_pending_intents", "died_at", "death_reason")})


def make_probe(costs=COSTS, **overrides):
    probe = Probe(genome(**overrides), 100, execution_config=costs,
                  clock=lambda: datetime.fromtimestamp(START, timezone.utc))
    probe.set_funded()
    probe.set_observing()
    probe._transition(ProbeState.TRADING)
    for asset in (SOL, JUP):
        probe.on_price_update(asset, 100)
    return probe


class ExecutionProbeTests(OfflineTestMixin, unittest.TestCase):
    def test_hand_calculated_entry_mark_and_exit_reconcile_cash_quantity_and_costs(self):
        probe = make_probe()
        opened = probe._open_position(SOL, 100, {})
        trade = probe.open_positions[SOL]
        quantity = Decimal(50) / Decimal("1.01") / Decimal(102)
        entry_notional = Decimal(50) / Decimal("1.01")
        entry = trade.execution["entry"]
        self.assertEqual(trade.execution["version"], EXECUTION_VERSION)
        self.assertEqual(trade.execution["account_currency"], "USD")
        self.assertEqual(probe.metrics()["execution_sampling"], "pre_decision")
        self.assertIs(probe.metrics()["terminal_execution_costs_in_returns"], False)
        self.assertEqual(trade.amount, 50)
        self.assertEqual(trade.entry_price, 102)
        self.assertEqual(trade.reference_entry_price, 100)
        self.assertEqual(trade.stop_loss_price, 90)
        self.assertEqual(trade.take_profit_price, 120)
        self.assertAlmostEqual(entry["quantity"], float(quantity))
        self.assertAlmostEqual(entry["notional"], float(entry_notional))
        self.assertAlmostEqual(entry["fee"], float(entry_notional / 100))
        self.assertAlmostEqual(entry["spread_cost"], float(quantity))
        self.assertAlmostEqual(entry["slippage_cost"], float(quantity))
        self.assertEqual(opened.data["execution"], trade.execution)
        self.assertAlmostEqual(probe.total_value, float(Decimal(50) + 100 * quantity))
        self.assertLess(probe.total_value, probe.initial_capital)
        self.assertAlmostEqual(trade.marked_value(110), float(110 * quantity))

        closed = probe._close_position(SOL, 110, "FIXTURE")
        credit = quantity * Decimal("107.8") * Decimal(".99")
        net = credit - 50
        self.assertAlmostEqual(probe.capital, float(50 + credit))
        self.assertAlmostEqual(trade.exit_price, 107.8)
        self.assertAlmostEqual(trade.pnl, float(net))
        self.assertAlmostEqual(trade.return_pct(), float(net / 50))
        self.assertAlmostEqual(closed.data["pnl_pct"], float(net / 50 * 100))
        self.assertAlmostEqual(probe.total_pnl, float(net))
        self.assertAlmostEqual(probe.roi, float(net / 100))
        accounting = probe.summary()["metrics"]["accounting"]
        self.assertEqual(accounting["execution_policy"], COSTS.policy())
        self.assertEqual(accounting["position_value"], 0)
        self.assertEqual(accounting["cash"], accounting["equity"])
        self.assertEqual(accounting["roi"], probe.roi)
        self.assertEqual(json.loads(json.dumps(trade.execution, allow_nan=False)), trade.execution)

    def test_reference_thresholds_ignore_entry_spread_but_realized_profit_pays_both_sides(self):
        costs = ExecutionConfig(fee_bps=100, half_spread_bps=500, slippage_bps=100)
        probe = make_probe(costs, stop_loss_pct=.05, take_profit_pct=.02)
        probe._open_position(SOL, 100, {})
        self.assertIsNone(probe._check_stop_loss_take_profit(SOL, 99))
        stop = probe._check_stop_loss_take_profit(SOL, 94)
        self.assertEqual(stop.data["exit_reason"], "STOP_LOSS")
        self.assertAlmostEqual(stop.data["exit_price"], 94 * .94)
        self.assertLess(stop.data["pnl_pct"], -6)
        probe = make_probe(costs, stop_loss_pct=.05, take_profit_pct=.02)
        probe._open_position(SOL, 100, {})
        take = probe._check_stop_loss_take_profit(SOL, 103)
        self.assertEqual(take.data["exit_reason"], "TAKE_PROFIT")
        self.assertLess(take.data["pnl"], 0)  # Reference TP is not a promise of net profit.

    def test_forced_death_batch_preserves_identity_and_records_net_terminal_equity(self):
        probe = make_probe()
        for asset in (SOL, JUP):
            probe._open_position(asset, 100, {})
        trades = list(probe.open_positions.values())
        before = probe_state(probe)
        expected = probe.validate_liquidation({SOL: 100, JUP: 100})
        self.assertEqual(before, probe_state(probe))
        events = probe._trigger_die("fixture")
        closes = [event for event in events if event.event_type == EventType.TRADE_CLOSED]
        self.assertEqual(len(closes), 2)
        self.assertTrue(all(a is b for a, b in zip(trades, probe.closed_trades)))
        self.assertEqual(probe.capital, expected)
        self.assertAlmostEqual(probe.total_pnl, expected - 100)
        self.assertEqual(events[-1].data["metrics"]["accounting"]["equity"], expected)
        self.assertTrue(all(event.data["execution"]["exit"]["kind"] == "fill" for event in closes))

    def test_invalid_second_close_cannot_commit_first_or_mutate_preflight(self):
        probe = make_probe()
        for asset in (SOL, JUP):
            probe._open_position(asset, 100, {})
        probe.open_positions[JUP].execution["entry"]["quantity"] += 1
        before = probe_state(probe)
        for action in (probe.validate_liquidation,
                       lambda prices: probe.close_all_positions(prices, "EVOLUTION")):
            with self.assertRaises(MarketValueError):
                action({SOL: 100, JUP: 100})
            self.assertEqual(before, probe_state(probe))

    def test_terminal_writeoff_is_explicit_zero_credit_and_loses_all_in_entry_budget(self):
        probe = make_probe()
        probe._open_position(SOL, 100, {})
        closed = probe._close_position(SOL, 0, "ignored", terminal_loss=True)
        trade = probe.closed_trades[0]
        self.assertEqual(probe.capital, 50)
        self.assertEqual(trade.pnl, -50)
        self.assertEqual(trade.return_pct(), -1)
        self.assertEqual(closed.data["exit_reason"], "TERMINAL_LOSS")
        self.assertEqual(trade.execution["exit"]["kind"], "writeoff")
        self.assertEqual(trade.execution["exit"]["fee"], 0)


class ExecutionPersistenceTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    async def test_event_persister_saves_full_precision_execution_and_accounting_with_owner_scope(self):
        db = RecordingDB()
        with patch("vonneumann.db.repository.get_supabase", return_value=db):
            repo = VonNeumannRepository(USER_A, A1)
        persister = EventPersister(repo)
        probe = make_probe(ExecutionConfig(17.125, 9.625, 4.375))
        opened = probe._open_position(SOL, 100.123456789012, {})
        expected_entry = deepcopy(opened.data["execution"])
        await persister.handle(opened)
        closed = probe._close_position(SOL, 103.876543210987, "FIXTURE")
        await persister.handle(closed)
        await persister.handle(ProbeEvent(EventType.PROBE_UPDATE, probe.probe_id,
                                         probe.summary(), timestamp=closed.timestamp))
        insert, update, metrics = db.calls[-3:]
        self.assertEqual(insert["fields"]["execution"], expected_entry)
        self.assertEqual(insert["fields"]["entry_price"], opened.data["entry_price"])
        self.assertNotEqual(insert["fields"]["entry_price"], round(opened.data["entry_price"], 4))
        self.assertEqual(update["fields"]["execution"], closed.data["execution"])
        self.assertEqual(update["fields"]["pnl"], closed.data["pnl"])
        self.assertEqual(update["fields"]["pnl_pct"], closed.data["pnl_pct"])
        self.assertEqual(metrics["fields"]["metrics"]["accounting"], probe.metrics()["accounting"])
        self.assertEqual(insert["fields"]["user_id"], USER_A)
        self.assertEqual(insert["fields"]["run_id"], A1)
        self.assertIn(("user_id", USER_A), update["filters"])
        self.assertIn(("run_id", A1), update["filters"])
        saved = deepcopy(update["fields"]["execution"])
        closed.data["execution"]["exit"]["fee"] = -1
        self.assertEqual(update["fields"]["execution"], saved)


class ExecutionControllerTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.clock = ControlledClock()
        self.clock.wall = START
        self.offline_stack.enter_context(patch("vonneumann.market.quote_freshness.time", self.clock))
        self.offline_stack.enter_context(patch("vonneumann.core.probe.time", self.clock))
        self.events, self.saved = [], []

    async def controller(self, *, costs=COSTS, threshold=1, cohort=True, capital=200):
        strategy = CohortRecordingStrategy() if cohort else FixedStrategy()
        self.feed = CandleQuoteFeed(self.clock) if cohort else MutableSourceFeed(self.clock)
        template = genome()
        config = ColonyConfig(available_assets=[SOL, JUP], enabled_genes=["rsi_oversold", "volume_threshold"],
            gene_overrides={name: GeneOverride(fixed=getattr(template, name)) for name in NUMERIC_GENES
                            if name not in {"rsi_oversold", "volume_threshold"}}, reproduction_interval=2)
        async def event(value):
            self.events.append(value)
        async def save(value):
            self.saved.append(deepcopy(value))
        self.c = GenesisController(self.feed, strategy, A1, USER_A, mode="paper",
            gen0_count=2, max_probes=2, max_capital=capital, seed_capital=100,
            diversity_threshold=0, colony_config=config, execution_config=costs,
            circuit_breaker_drop_pct=threshold, on_event=event, persist_risk_status=save)
        self.c._event_time = lambda: datetime.fromtimestamp(self.clock.wall, timezone.utc)
        with patch("vonneumann.core.genesis.random_genome", side_effect=lambda **_: genome()):
            await self.c.prepare()
        self.c.set_lifecycle("running")
        self.events.clear()
        return self.c

    async def tick(self, seconds=1):
        self.clock.advance(seconds)
        if isinstance(self.feed, MutableSourceFeed):
            self.feed.response = self.feed.prices(slot=100 + self.c.tick_count + 1)
        await self.c._tick_all()

    async def test_completed_candidate_scores_include_exit_fees_and_replacement_cannot_restore_losses(self):
        costs = ExecutionConfig(fee_bps=1000)
        c = await self.controller(costs=costs, capital=400)
        await self.tick()
        previous = list(c.live_probes)
        for probe in previous:
            probe._open_position(SOL, 100, {})
        await self.tick(c._cohort.ends_at - self.clock.wall)
        expected_cash = float(Decimal(50) + Decimal(50) / Decimal("1.1") * Decimal(".9"))
        expected_roi = (expected_cash - 100) / 100
        self.assertEqual(len(c.strategy.received), 1)
        for evaluation in c.strategy.received[0]:
            self.assertEqual(evaluation.num_trades, 1)
            self.assertAlmostEqual(evaluation.roi, expected_roi)
            self.assertAlmostEqual(evaluation.fitness, 3 * expected_roi)
        closes = [event for event in self.events if event.event_type == EventType.TRADE_CLOSED]
        self.assertEqual(len(closes), 2)
        self.assertTrue(all(event.data["exit_reason"] == "EVOLUTION" for event in closes))
        self.assertAlmostEqual(c.reserve_capital + c.active_capital, 200 + 2 * expected_cash)
        self.assertTrue(all(probe.execution_config == costs for probe in c.live_probes))
        self.assertTrue(all(not probe.open_positions for probe in c.live_probes))

    async def test_exit_cost_circuit_breaker_aborts_cohort_before_optimizer_tell(self):
        c = await self.controller(costs=ExecutionConfig(fee_bps=1000), threshold=.07)
        await self.tick()
        ids = set(c.probes)
        for probe in c.live_probes:
            probe._open_position(SOL, 100, {})
        await self.tick(c._cohort.ends_at - self.clock.wall)
        self.assertEqual(c.lifecycle_status, "risk_halted")
        self.assertEqual(c._cohort.phase, "aborted")
        self.assertEqual(c.strategy.received, [])
        self.assertEqual(set(c.probes), ids)
        self.assertTrue(all(not probe.open_positions for probe in c.live_probes))
        self.assertEqual(sum(event.event_type == EventType.TRADE_CLOSED for event in self.events), 2)
        self.assertEqual(sum(event.event_type == EventType.CIRCUIT_BREAKER for event in self.events), 1)
        self.assertEqual(self.saved[-1]["status"], "risk_halted")

    async def test_replacement_exit_costs_halt_before_any_child_is_funded(self):
        c = await self.controller(costs=ExecutionConfig(fee_bps=1000),
                                  threshold=.035, cohort=False, capital=400)
        await self.tick()
        parents = list(c.live_probes)
        for probe in parents:
            probe._open_position(SOL, 100, {})
        # Entry loss is 9.09 / 400; both exits raise it to 18.18 / 400.
        self.assertFalse(c._check_circuit_breaker())
        result = EvolutionResult([genome(generation=1) for _ in parents],
            [probe.probe_id for probe in parents],
            {str(index): [probe.probe_id] for index, probe in enumerate(parents)})
        await c._apply_replacement(result)
        self.assertEqual(c.lifecycle_status, "risk_halted")
        self.assertFalse(c.probes)
        self.assertEqual(len(c.dead_probes), 2)
        self.assertFalse(any(event.event_type == EventType.PROBE_BORN for event in self.events))
        self.assertEqual(sum(event.event_type == EventType.TRADE_CLOSED for event in self.events), 2)
        expected = float(Decimal(300) + Decimal(100) / Decimal("1.1") * Decimal(".9"))
        self.assertAlmostEqual(c.reserve_capital, expected)
        self.assertEqual(self.saved[-1]["status"], "risk_halted")

    async def test_entry_cost_breaker_prevents_next_asset_and_next_probe_from_adding_risk(self):
        c = await self.controller(threshold=.003, cohort=False)
        for probe in c.live_probes:
            for asset in (SOL, JUP):
                probe._pending_intents[asset] = _SignalIntent(self.clock.wall, self.clock.mono, "entry", None, {})
        await self.tick()
        self.assertEqual(c.lifecycle_status, "risk_halted")
        self.assertEqual(sum(len(p.open_positions) for p in c.live_probes), 1)
        self.assertTrue(all(not p._pending_intents for p in c.live_probes))
        self.assertEqual(sum(event.event_type == EventType.TRADE_OPENED for event in self.events), 1)
        self.assertEqual(sum(event.event_type == EventType.CIRCUIT_BREAKER for event in self.events), 1)
        self.assertLess(c.status()["total_capital"], 200)
        self.assertEqual(self.saved[-1]["status"], "risk_halted")

    async def test_invalid_sibling_cohort_preflight_never_liquidates_first_candidate(self):
        c = await self.controller()
        await self.tick()
        probes = list(c.live_probes)
        for probe in probes:
            probe._open_position(SOL, 100, {})
        probes[1].open_positions[SOL].execution["entry"]["quantity"] += 1
        before = [probe_state(probe) for probe in probes]
        self.clock.advance(c._cohort.ends_at - self.clock.wall)
        # Invoke the actual cohort boundary with current accepted quotes; the
        # earlier risk pass would independently fail this malformed position.
        with patch.object(c, "_require_current_quotes"), patch.object(c, "_mark_price", return_value=100):
            with self.assertRaises(MarketValueError):
                await c._evaluate_reproduction()
        self.assertEqual([probe_state(probe) for probe in probes], before)
        self.assertEqual(c.strategy.received, [])
        self.assertFalse(any(event.event_type == EventType.TRADE_CLOSED for event in self.events))


class ExecutionReplayTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    async def test_all_four_solvers_replay_real_paid_trades_and_net_scores_across_pacing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "fixture"
            await generate_synthetic_dataset(path, frames=201, assets=[SOL, JUP], seed="729")
            for algorithm in ALGORITHMS:
                with self.subTest(algorithm=algorithm):
                    controllers, events = [], ([], [])
                    for index, (feed, pacing) in enumerate(((SimulationFeed(seed=729), 100), (ReplayFeed(path), 5000))):
                        async def event(value, index=index):
                            if value.event_type in {EventType.TRADE_OPENED, EventType.TRADE_CLOSED}:
                                events[index].append((value.event_type.value, value.timestamp.isoformat(),
                                    {key: deepcopy(val) for key, val in value.data.items() if key != "trade_id"}))
                        c = GenesisController(feed, get_strategy(algorithm), A1, USER_A,
                            gen0_count=8, max_probes=8, max_capital=10000, seed_capital=100,
                            tick_interval_ms=pacing, colony_config=config(), on_event=event,
                            circuit_breaker_drop_pct=1, search_seed="19", execution_config=COSTS)
                        await c.prepare()
                        c.set_lifecycle("running")
                        controllers.append(c)
                    identities, entered = ({}, {}), (set(), set())
                    for c, ids in zip(controllers, identities):
                        snapshot(c, ids)
                    generations = 0
                    for _ in range(200):
                        iteration = controllers[0]._evaluation_iteration
                        for index, c in enumerate(controllers):
                            cohort = c._cohort
                            if cohort.phase == "evaluating" and cohort.iteration_id not in entered[index]:
                                entered[index].add(cohort.iteration_id)
                                now = c.market_feed.current_timestamp
                                for probe in c.live_probes:
                                    probe._pending_intents[probe.genome.assets[0]] = _SignalIntent(now, now, "entry", None, {})
                            await c._tick_all()
                        self.assertEqual(controllers[0]._latest_prices, controllers[1]._latest_prices)
                        if controllers[0]._evaluation_iteration != iteration:
                            traces = []
                            for c, ids in zip(controllers, identities):
                                data = snapshot(c, ids)
                                data["search_spec"].pop("dataset_spec")
                                traces.append(data)
                            self.assertEqual(traces[0], traces[1])
                            generations += 1
                            if generations == 4:
                                break
                    self.assertEqual(generations, 4)
                    self.assertEqual(events[0], events[1])
                    closes = [data for kind, _, data in events[0] if kind == EventType.TRADE_CLOSED.value]
                    self.assertGreaterEqual(len(closes), 8 * generations)
                    self.assertTrue(all(data["execution"]["entry"]["fee"] > 0 and
                                        data["execution"]["exit"]["fee"] > 0 for data in closes))
                    for c in controllers:
                        net = sum(data["pnl"] for data in closes)
                        self.assertAlmostEqual(c.reserve_capital + c.active_capital, 10000 + net, places=8)
                        self.assertEqual(c.status()["total_capital"], round(10000 + net, 2))
                        self.assertTrue(all(not p.open_positions for p in c.live_probes))


class ExecutionApiTests(OfflineTestMixin, unittest.TestCase):
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
        self.repo = self.offline_stack.enter_context(patch.object(app_module, "VonNeumannRepository", return_value=self.fake_repo))
        self.create = self.offline_stack.enter_context(patch.object(app_module.colony_manager, "create_colony", new=AsyncMock()))

    def test_malformed_cost_objects_reject_before_storage_or_worker_creation(self):
        base = COSTS.to_dict()
        invalid = [None, True, 1, "zero", {}, {"fee_bps": 0}, {**base, "unknown": 1},
                   {**base, "half_spread_bps": 5000, "slippage_bps": 5000}]
        invalid += [{**base, key: value} for key in base for value in (-1, 10000, True, False, "1", None)]
        for value in invalid:
            with self.subTest(execution=value):
                response = self.client.post("/api/v1/colonies/", json={"execution": value})
                self.assertEqual(response.status_code, 422, response.text)
        for value in (float("inf"), float("nan")):
            with self.assertRaises(ValidationError):
                StartRequest(execution={**base, "fee_bps": value})
        self.repo.assert_not_called()
        self.create.assert_not_awaited()

    def test_cost_policy_passes_unchanged_to_controller_saved_config_response_and_runtime(self):
        costs = ExecutionConfig(17.125, 9.625, 4.375)
        response = self.client.post("/api/v1/colonies/", json={"execution": costs.to_dict()})
        self.assertEqual(response.status_code, 200, response.text)
        saved = self.fake_repo.execute_async.await_args.args[3]
        self.assertEqual(saved["execution"], costs.to_dict())
        self.assertEqual(saved["execution_policy"], costs.policy())
        self.assertEqual(response.json()["config"]["execution"], costs.to_dict())
        self.assertEqual(self.create.await_args.kwargs["execution_config"], costs)
        persist = self.create.await_args.kwargs["persist_status"]
        asyncio.run(persist({"status": "paused", "execution_policy": costs.policy()}))
        self.assertEqual(self.fake_repo.execute_async.await_args.kwargs["details"]["execution_policy"], costs.policy())
        asyncio.run(persist({"status": "failed", "failure_code": "startup_failed"}))
        self.assertEqual(self.fake_repo.execute_async.await_args.kwargs["details"]["execution_policy"], costs.policy())
        self.assertEqual(StartRequest().execution.model_dump(), ExecutionConfig().to_dict())


if __name__ == "__main__":
    unittest.main()
