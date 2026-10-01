"""Independent C1 snapshot acceptance; no controller startup or external I/O."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import pickle
import random
import unittest
from unittest.mock import patch

from tests.security_support import A1, A2, USER_A, OfflineTestMixin, deny_network

with deny_network():
    from tests.test_search_replay import ALGORITHMS, make_controller
    from vonneumann.core.colony_config import ColonyConfig
    from vonneumann.core.engine_state import EngineDraft, EngineSnapshot, capture_engine_state
    from vonneumann.core.evaluation import EvaluationCohort
    from vonneumann.core.execution import ExecutionConfig, buy_fill, execution_record, sell_fill
    from vonneumann.core.genesis import GenesisController, _GenerationAggregate
    from vonneumann.core.genome import Genome
    from vonneumann.core.probe import Probe, _SignalIntent
    from vonneumann.core.state_components import ProbeData
    from vonneumann.core.strategies.genetic_algorithm import GeneticAlgorithmStrategy
    from vonneumann.core.types import ProbeState, TradeRecord
    from vonneumann.market.candles import CandleHistory, MinuteCandle
    from vonneumann.market.feed import MarketTick, QuoteEvidence


ASSET = "SOL/USDC"
START = 1_704_067_200
STAMP = datetime.fromtimestamp(START, timezone.utc)
P1 = "11111111-2222-4333-8444-555555555551"
P2 = "11111111-2222-4333-8444-555555555552"
P3 = "11111111-2222-4333-8444-555555555553"


class ResourceBomb:
    """A resource must be excluded without invoking copy or call hooks."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("snapshot invoked an operational resource")

    def __deepcopy__(self, memo):
        raise AssertionError("snapshot copied an operational resource")

    async def get_ticks(self, assets):
        raise AssertionError("snapshot acquired market data")

    async def get_candles(self, assets, **kwargs):
        raise AssertionError("snapshot acquired history")


def candle(index):
    price = 1 + index / 1000
    return MinuteCandle(ASSET, START + index * 60, price, price, price, price,
                        10, "engine-state-offline")


class EngineStateTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def controller(self):
        resource = ResourceBomb()
        config = ColonyConfig(available_assets=[ASSET])
        controller = GenesisController(resource, GeneticAlgorithmStrategy(), A1, USER_A,
            max_probes=4, gen0_count=2, seed_capital=100, max_capital=1000,
            colony_config=config, on_event=resource, persist_risk_status=resource,
            search_seed="1729")
        controller.started_at = STAMP
        controller._lifecycle_status = "running"
        controller._running = True
        controller.reserve_capital = 800
        controller.total_deployed = controller._initial_total_capital = 200
        controller.candle_history.ingest([candle(i) for i in range(70)], available_at=START + 70 * 60)
        for index, identity in enumerate((P1, P2)):
            genome = Genome(assets=[ASSET], num_assets=1, timeframe_minutes=5).validate(config)
            probe = Probe(genome, 100, probe_id=identity, probe_name=f"fixture-{index}",
                          clock=lambda: STAMP, candle_history=controller.candle_history)
            probe._clock = resource
            probe.state = ProbeState.OBSERVING
            probe._marks[ASSET] = 1
            controller.probes[identity] = probe
        first = controller.probes[P1]
        first._has_persisted_offspring = True
        first._pending_intents[ASSET] = _SignalIntent(START, START, "entry", None,
                                                      {"rsi": 25.0, "evidence": [1, 2]})
        entry = buy_fill(1, 1, ExecutionConfig())
        first.open_positions[ASSET] = TradeRecord("position-1", P1, ASSET, "BUY", 1, 1,
            opened_at=STAMP, execution=execution_record(ExecutionConfig(), entry))
        first.capital = 99
        exit_fill = sell_fill(entry, 2, ExecutionConfig())
        first.closed_trades.append(TradeRecord("closed-1", P1, ASSET, "BUY", 1, 1,
            exit_price=2, pnl=1, pnl_pct=1, opened_at=STAMP, closed_at=STAMP,
            execution=execution_record(ExecutionConfig(), entry, exit_fill)))
        tick = MarketTick(ASSET, 1, 10, START, QuoteEvidence(100, START, 50))
        controller._latest_ticks[ASSET] = tick
        controller._source_quotes[ASSET] = tick
        controller._latest_prices[ASSET] = 1
        controller._source_slots[ASSET] = 100
        controller._generation_aggregates[0] = _GenerationAggregate(STAMP)
        controller._generation_probe_counts[0] = 2
        controller._cohort_seeds = [first.genome]
        controller.strategy.initialize(list(controller.probes.values()), config)
        controller._cohort = EvaluationCohort("iteration:0", list(controller.probes.values()), 60)
        return controller, resource

    async def test_capture_preserves_two_distinct_probe_records_and_safe_identity(self):
        controller, _ = self.controller()
        snapshot = await capture_engine_state(controller)
        self.assertEqual((snapshot.run_id, snapshot.owner_id, snapshot.mode), (A1, USER_A, "simulation"))
        draft = snapshot.fork()
        self.assertIs(type(draft), EngineDraft)
        self.assertEqual(list(draft.probes), [P1, P2])
        self.assertEqual([p.attributes["probe_id"] for p in draft.probes.values()], [P1, P2])
        self.assertEqual([p.attributes["capital"] for p in draft.probes.values()], [99, 100])
        self.assertIsNot(draft.probes[P1].attributes, draft.probes[P2].attributes)
        self.assertTrue(draft.probes[P1].attributes["_has_persisted_offspring"])
        self.assertNotIn("_has_persisted_offspring", draft.probes[P2].attributes)
        self.assertTrue(all(p.uses_candle_history for p in draft.probes.values()))
        self.assertIs(type(draft.probes[P1]), ProbeData)
        self.assertFalse(hasattr(draft.probes[P1], "tick"))
        self.assertFalse(hasattr(draft, "_tick_all"))

    async def test_source_changes_after_capture_do_not_change_sealed_graph(self):
        controller, _ = self.controller()
        snapshot = await capture_engine_state(controller)
        first = controller.probes[P1]
        controller.reserve_capital = 9
        first.capital = 7
        first.genome.assets.append("JUP/USDC")
        first.open_positions[ASSET].execution["entry"]["quantity"] = 999
        first._pending_intents[ASSET].signals["evidence"].append(3)
        controller._latest_ticks[ASSET].price = 999
        controller._risk_control["recovery_count"] = 99
        controller._generation_aggregates[0].means[0] = 999
        draft = snapshot.fork()
        self.assertEqual(draft.attributes["reserve_capital"], 800)
        self.assertEqual(draft.probes[P1].attributes["capital"], 99)
        self.assertEqual(draft.probes[P1].attributes["genome"].assets, [ASSET])
        self.assertEqual(draft.probes[P1].attributes["open_positions"][ASSET].execution["entry"]["quantity"], 1)
        self.assertEqual(draft.probes[P1].attributes["_pending_intents"][ASSET].signals["evidence"], [1, 2])
        self.assertEqual(draft.attributes["_latest_ticks"][ASSET].price, 1)
        self.assertEqual(draft.attributes["_risk_control"]["recovery_count"], 0)
        self.assertEqual(draft.attributes["_generation_aggregates"][0].means[0], 0)

    async def test_two_drafts_share_no_mutable_graph_with_source_or_each_other(self):
        controller, _ = self.controller()
        snapshot = await capture_engine_state(controller)
        first, second = snapshot.fork(), snapshot.fork()
        first.attributes["_risk_control"]["recovery_count"] = 10
        first.attributes["_generation_aggregates"][0].means[0] = 10
        first.probes[P1].attributes["genome"].assets.append("JUP/USDC")
        first.probes[P1].attributes["closed_trades"][0].execution["entry"]["quantity"] = 10
        first.probes[P1].attributes["_pending_intents"][ASSET].signals["evidence"].append(10)
        first.attributes["_latest_ticks"][ASSET].price = 10
        for untouched in (second, snapshot.fork()):
            self.assertEqual(untouched.attributes["_risk_control"]["recovery_count"], 0)
            self.assertEqual(untouched.attributes["_generation_aggregates"][0].means[0], 0)
            self.assertEqual(untouched.probes[P1].attributes["genome"].assets, [ASSET])
            self.assertEqual(untouched.probes[P1].attributes["closed_trades"][0].execution["entry"]["quantity"], 1)
            self.assertEqual(untouched.probes[P1].attributes["_pending_intents"][ASSET].signals["evidence"], [1, 2])
            self.assertEqual(untouched.attributes["_latest_ticks"][ASSET].price, 1)
        self.assertEqual(controller.probes[P1].genome.assets, [ASSET])
        self.assertEqual(controller._risk_control["recovery_count"], 0)
        # Meaningful aliases inside one source graph stay inside one draft.
        self.assertIs(second.attributes["_latest_ticks"][ASSET], second.attributes["_source_quotes"][ASSET])
        self.assertIs(second.attributes["_cohort_seeds"][0], second.probes[P1].attributes["genome"])
        self.assertIs(second.attributes["_search_streams"], second.strategy._search_streams)

    async def test_capture_and_fork_do_not_call_resources_reports_or_constructors(self):
        controller, resource = self.controller()
        first = controller.probes[P1]
        first.closed_trades = [replace(first.closed_trades[0], trade_id=f"retained-{i}") for i in range(257)]
        controller._worker_draining = True
        controller.state_persisted = True
        random_state = random.getstate()
        with patch.object(Probe, "__init__", side_effect=AssertionError("probe constructor")), \
             patch.object(Probe, "summary", side_effect=AssertionError("probe report")), \
             patch.object(Probe, "_trim_closed_trades", side_effect=AssertionError("retention mutation")), \
             patch.object(GenesisController, "status", side_effect=AssertionError("controller report")), \
             patch("vonneumann.core.genesis.generate_probe_name", side_effect=AssertionError("name RNG")):
            snapshot = await capture_engine_state(controller)
            draft = snapshot.fork()
        self.assertEqual(random.getstate(), random_state)
        self.assertEqual(resource.calls, 0)
        self.assertEqual(len(first.closed_trades), 257)
        self.assertEqual(len(draft.probes[P1].attributes["closed_trades"]), 257)
        self.assertEqual(first._evicted_trade_count, 0)
        self.assertTrue(controller._worker_draining)
        for field in ("market_feed", "_on_event", "_persist_risk_status", "_tick_lock", "_worker_draining",
                      "_running", "_paused", "_feed_closed", "state_persisted", "_wall_started_monotonic"):
            self.assertNotIn(field, draft.attributes)
        for data in draft.probes.values():
            self.assertNotIn("_clock", data.attributes)
            self.assertNotIn("_candle_history", data.attributes)

    async def test_candle_fork_retains_recursive_and_pending_state_without_replay(self):
        controller, _ = self.controller()
        snapshot = await capture_engine_state(controller)
        left, right = snapshot.fork(), snapshot.fork()
        original = controller.candle_history.latest(ASSET, 1)
        self.assertEqual(left.candle_history.latest(ASSET, 1), original)
        self.assertEqual(left.candle_history._assets[ASSET].series[60].pending,
                         controller.candle_history._assets[ASSET].series[60].pending)
        with self.assertRaises(TypeError):
            left.candle_history.latest(ASSET, 1).emas[2] = 5
        left.candle_history.ingest([candle(70)], available_at=START + 71 * 60)
        self.assertEqual(left.candle_history.latest(ASSET, 1).completed_count, 71)
        self.assertEqual(right.candle_history.latest(ASSET, 1).completed_count, 70)
        self.assertEqual(controller.candle_history.latest(ASSET, 1), original)
        self.assertEqual(snapshot.fork().candle_history.latest(ASSET, 1), original)
        right.candle_history.ingest([candle(70)], available_at=START + 71 * 60)
        self.assertEqual(left.candle_history.latest(ASSET, 1), right.candle_history.latest(ASSET, 1))

    async def test_strategy_rng_and_partial_evaluation_are_detached_and_deterministic(self):
        controller, _ = self.controller()
        controller.strategy._rng.gauss(0, 1)  # Include the RNG's cached Gaussian.
        controller._cohort.start(START)
        controller._cohort.record_terminal(controller.probes[P2], "death", START + 10)
        before = controller.strategy._rng.getstate()
        snapshot = await capture_engine_state(controller)
        left, right = snapshot.fork(), snapshot.fork()
        self.assertEqual(controller.strategy._rng.getstate(), before)
        self.assertEqual(left.strategy._rng.getstate(), before)
        self.assertEqual(left.strategy._rng.gauss(0, 1), right.strategy._rng.gauss(0, 1))
        left.strategy._cohort._signatures.clear()
        self.assertEqual(len(right.strategy._cohort._signatures), 2)
        self.assertEqual(len(controller.strategy._cohort._signatures), 2)
        self.assertEqual(left.cohort.phase, "evaluating")
        self.assertEqual(left.cohort.member_ids, (P1, P2))
        left.cohort._evaluations[P2]._genome.assets.append("JUP/USDC")
        self.assertEqual(right.cohort._evaluations[P2]._genome.assets, [ASSET])
        self.assertEqual(controller._cohort._evaluations[P2]._genome.assets, [ASSET])
        self.assertEqual(snapshot.fork().strategy._rng.getstate(), before)

    async def test_capture_waits_for_lock_and_captures_only_post_lock_state(self):
        controller, _ = self.controller()
        await controller._tick_lock.acquire()
        task = asyncio.create_task(capture_engine_state(controller))
        try:
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            controller.reserve_capital = 123
        finally:
            controller._tick_lock.release()
        snapshot = await asyncio.wait_for(task, 1)
        self.assertEqual(snapshot.fork().attributes["reserve_capital"], 123)
        self.assertFalse(controller._tick_lock.locked())

    async def test_cancel_waiting_capture_does_not_release_foreign_lock_or_mutate(self):
        controller, resource = self.controller()
        await controller._tick_lock.acquire()
        task = asyncio.create_task(capture_engine_state(controller))
        try:
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(controller._tick_lock.locked())
            self.assertEqual(controller.reserve_capital, 800)
            self.assertEqual(resource.calls, 0)
        finally:
            controller._tick_lock.release()
        self.assertEqual((await capture_engine_state(controller)).run_id, A1)

    async def test_started_startup_is_rejected_but_unstarted_empty_controller_is_allowed(self):
        controller, _ = self.controller()
        controller._lifecycle_status = "starting"
        with self.assertRaises(ValueError):
            await capture_engine_state(controller)
        self.assertFalse(controller._tick_lock.locked())
        empty = GenesisController(ResourceBomb(), GeneticAlgorithmStrategy(), A2, USER_A)
        self.assertEqual((await capture_engine_state(empty)).fork().probes, {})

    async def test_new_controller_or_probe_fields_fail_closed(self):
        for target in ("controller", "probe"):
            with self.subTest(target=target):
                controller, _ = self.controller()
                obj = controller if target == "controller" else controller.probes[P1]
                obj.future_mutable_state = []
                with self.assertRaises(ValueError):
                    await capture_engine_state(controller)
                self.assertFalse(controller._tick_lock.locked())
                self.assertEqual(obj.future_mutable_state, [])

    async def test_mapping_identity_and_live_dead_ownership_must_be_consistent(self):
        for corruption in ("wrong-key", "duplicate", "wrong-run"):
            with self.subTest(corruption=corruption):
                controller, _ = self.controller()
                if corruption == "wrong-key":
                    controller.probes[P3] = controller.probes.pop(P1)
                elif corruption == "duplicate":
                    controller.dead_probes.append(controller.probes[P1])
                else:
                    controller.run_id = A2
                with self.assertRaises(ValueError):
                    await capture_engine_state(controller)

    async def test_foreign_history_is_rejected_and_absent_history_is_explicit(self):
        controller, _ = self.controller()
        controller.probes[P1]._candle_history = CandleHistory([ASSET])
        with self.assertRaises(ValueError):
            await capture_engine_state(controller)
        controller.probes[P1]._candle_history = None
        draft = (await capture_engine_state(controller)).fork()
        self.assertFalse(draft.probes[P1].uses_candle_history)
        self.assertTrue(draft.probes[P2].uses_candle_history)

    async def test_retained_terminal_data_stays_distinct_from_reserve_ownership(self):
        controller, _ = self.controller()
        retired = controller.probes.pop(P2)
        retired.state, retired.died_at, retired.death_reason = ProbeState.DEAD, STAMP, "fixture-terminal"
        retired.capital = 73
        controller.dead_probes.append(retired)
        snapshot = await capture_engine_state(controller)
        draft = snapshot.fork()
        self.assertEqual(list(draft.probes), [P1])
        self.assertEqual([p.attributes["probe_id"] for p in draft.dead_probes], [P2])
        self.assertEqual(draft.dead_probes[0].attributes["capital"], 73)
        self.assertEqual(draft.dead_probes[0].attributes["state"], ProbeState.DEAD)
        self.assertEqual(draft.attributes["reserve_capital"], 800)
        draft.dead_probes[0].attributes["capital"] = 0
        self.assertEqual(retired.capital, 73)
        self.assertEqual(snapshot.fork().dead_probes[0].attributes["capital"], 73)

    async def test_controller_subclasses_and_nonstandard_locks_are_rejected_before_hooks(self):
        class OtherController(GenesisController):
            pass

        subclass = OtherController(ResourceBomb(), GeneticAlgorithmStrategy(), A1, USER_A)
        with self.assertRaises(ValueError):
            await capture_engine_state(subclass)
        controller, resource = self.controller()
        controller._tick_lock = resource
        with self.assertRaises(ValueError):
            await capture_engine_state(controller)
        self.assertEqual(resource.calls, 0)

    async def test_identity_and_lifecycle_types_are_rejected_without_equality_hooks(self):
        class EqualityBomb:
            def __init__(self):
                self.calls = 0

            def __eq__(self, other):
                self.calls += 1
                raise AssertionError("snapshot invoked untrusted equality")

        for field in ("colony_id", "mode", "_lifecycle_status"):
            with self.subTest(field=field):
                controller, _ = self.controller()
                bomb = EqualityBomb()
                setattr(controller, field, bomb)
                with self.assertRaises(ValueError):
                    await capture_engine_state(controller)
                self.assertEqual(bomb.calls, 0)
                self.assertFalse(controller._tick_lock.locked())

    async def test_snapshot_cannot_be_reassigned_constructed_or_pickled(self):
        controller, _ = self.controller()
        snapshot = await capture_engine_state(controller)
        with self.assertRaises(AttributeError):
            snapshot.run_id = A2
        with self.assertRaises(TypeError):
            EngineSnapshot()
        with self.assertRaises(TypeError):
            pickle.dumps(snapshot)
        self.assertEqual(snapshot.run_id, A1)

    async def test_unknown_nested_resource_or_cycle_is_rejected_without_execution(self):
        for value in (ResourceBomb(), {}):
            controller, _ = self.controller()
            if type(value) is dict:
                value["cycle"] = value
            controller._risk_control["future"] = value
            with self.assertRaises(ValueError):
                await capture_engine_state(controller)
            self.assertFalse(controller._tick_lock.locked())
            if isinstance(value, ResourceBomb):
                self.assertEqual(value.calls, 0)

    async def test_real_four_solver_controllers_capture_after_three_replacements_and_partial_windows(self):
        async def inspect(controller):
            source_ids = list(controller.probes)
            source_dead = [p.probe_id for p in controller.dead_probes]
            source_rng = controller.strategy._rng.getstate()
            source_time = controller.market_feed.current_timestamp
            snapshot = await capture_engine_state(controller)
            left, right = snapshot.fork(), snapshot.fork()
            self.assertEqual(list(left.probes), source_ids)
            self.assertEqual([p.attributes["probe_id"] for p in left.dead_probes], source_dead)
            self.assertEqual(left.attributes["reserve_capital"], controller.reserve_capital)
            self.assertEqual(left.attributes["_evaluation_iteration"], controller._evaluation_iteration)
            for identity, original in controller.probes.items():
                values = left.probes[identity].attributes
                self.assertEqual(values["capital"], original.capital)
                self.assertEqual(values["genome"].to_dict(), original.genome.to_dict())
                self.assertEqual(values["_candle_cursors"], original._candle_cursors)
            for values, original in zip(left.dead_probes, controller.dead_probes):
                self.assertEqual(values.attributes["capital"], original.capital)
                self.assertEqual(values.attributes.get("_has_persisted_offspring"),
                                 getattr(original, "_has_persisted_offspring", None))
            for asset in controller._candle_assets:
                self.assertEqual(left.candle_history.latest(asset, 1), controller.candle_history.latest(asset, 1))
                self.assertEqual(left.candle_history.latest(asset, 5), controller.candle_history.latest(asset, 5))
            self.assertEqual(left.cohort.to_dict(), controller._cohort.to_dict())
            self.assertEqual(left.strategy._rng.getrandbits(64), right.strategy._rng.getrandbits(64))
            self.assertEqual(controller.strategy._rng.getstate(), source_rng)
            if controller.strategy.name == "cma_es":
                # Probe the next real optimizer draw on each private branch;
                # the source optimizer must retain the same next ask as a fresh fork.
                before = controller.strategy._optimizer._rng.get_state()
                before = (before[0], before[1].tobytes(), before[2:])
                first_ask = left.strategy._optimizer.ask().tolist()
                self.assertEqual(first_ask, right.strategy._optimizer.ask().tolist())
                self.assertEqual(first_ask, snapshot.fork().strategy._optimizer.ask().tolist())
                after = controller.strategy._optimizer._rng.get_state()
                self.assertEqual((after[0], after[1].tobytes(), after[2:]), before)
            left.probes[source_ids[0]].attributes["capital"] = 0
            self.assertEqual(right.probes[source_ids[0]].attributes["capital"],
                             controller.probes[source_ids[0]].capital)
            self.assertEqual(controller.market_feed.current_timestamp, source_time)
            return snapshot

        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                controller = await make_controller(algorithm, seed="1729")
                initial = await inspect(controller)
                initial_ids = list(controller.probes)
                initial_iteration = controller._evaluation_iteration
                replacements = 0
                partial_seen = False
                for _ in range(500):
                    previous = controller._evaluation_iteration
                    await controller._tick_all()
                    if not partial_seen and controller._cohort.phase == "evaluating":
                        await inspect(controller)
                        partial_seen = True
                    if controller._evaluation_iteration != previous:
                        await inspect(controller)
                        replacements += 1
                        if replacements == 3:
                            break
                self.assertEqual(replacements, 3)
                self.assertTrue(partial_seen)
                self.assertGreaterEqual(len(controller.dead_probes), 8)
                self.assertTrue(any(getattr(p, "_has_persisted_offspring", False)
                                    for p in controller.dead_probes))
                self.assertEqual(list(initial.fork().probes), initial_ids)
                self.assertEqual(initial.fork().attributes["_evaluation_iteration"], initial_iteration)
