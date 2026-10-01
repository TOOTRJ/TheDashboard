"""Data-fork isolation without clocks, constructors, feed I/O or reporting."""

from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from types import MappingProxyType
import unittest
from unittest.mock import patch

from tests.security_support import deny_network

with deny_network():
    from vonneumann.core.equity_metrics import EquityHistory
    from vonneumann.core.genome import Genome
    from vonneumann.core.probe import Probe, _SignalIntent
    from vonneumann.core.state_components import (
        ProbeData, StateComponentError, capture_probe_data, fork_probe_data, fork_candle_history,
    )
    from vonneumann.core.types import TradeRecord
    from vonneumann.market.candles import CandleHistory, MinuteCandle
    from vonneumann.market.feed import MarketTick


ASSET = "SOL/USDC"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def candle(index, price=None):
    close = float(index + 10 if price is None else price)
    return MinuteCandle(ASSET, index * 60, close, close, close, close, 1.0, "offline-fixture")


def history(count=61):
    result = CandleHistory([ASSET])
    result.ingest([candle(index) for index in range(count)], available_at=count * 60)
    return result


def history_values(value):
    return tuple(value.latest(ASSET, timeframe) for timeframe in range(1, 61))


class StateComponentTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(deny_network())

    def probe(self, *, candles=None):
        return Probe(Genome(assets=[ASSET], num_assets=1, timeframe_minutes=1), 100,
                     clock=lambda: NOW, candle_history=candles)

    def test_probe_capture_is_data_only_and_never_invokes_resources_or_reporting(self):
        candles = history()
        probe = self.probe(candles=candles)
        probe._pending_intents[ASSET] = _SignalIntent(3660.0, 3661.0, "entry", None, {"rsi": 20.0})
        probe._has_persisted_offspring = True
        probe._clock = lambda: self.fail("capture called the probe clock")
        for target in ("__init__", "summary", "_trim_closed_trades", "attach_candle_history"):
            self.stack.enter_context(patch.object(Probe, target, side_effect=AssertionError("unexpected behavior")))
        data = capture_probe_data(probe)
        self.assertIs(type(data), ProbeData)
        self.assertTrue(data.uses_candle_history)
        self.assertNotIn("_clock", data.attributes)
        self.assertNotIn("_candle_history", data.attributes)
        self.assertFalse(hasattr(data, "tick"))
        self.assertFalse(hasattr(data, "_now"))
        self.assertEqual(data.attributes["_candle_cursors"], probe._candle_cursors)
        self.assertEqual(data.attributes["_pending_intents"], probe._pending_intents)
        self.assertTrue(data.attributes["_has_persisted_offspring"])
        self.assertIsNot(data.attributes["genome"], probe.genome)

    def test_capture_does_not_trim_retained_trades_or_reset_lifetime_counters(self):
        probe = self.probe()
        probe.closed_trades = [TradeRecord(str(i), probe.probe_id, ASSET, "BUY", 1.0, 1.0,
                              exit_price=2.0, pnl=1.0, pnl_pct=1.0, opened_at=NOW, closed_at=NOW)
                              for i in range(300)]
        probe._evicted_trade_count, probe._evicted_winning_trades, probe._evicted_trade_pnl = 7, 3, -5.25
        data = capture_probe_data(probe)
        self.assertEqual(len(probe.closed_trades), 300)
        self.assertEqual(len(data.attributes["closed_trades"]), 300)
        self.assertEqual(data.attributes["_evicted_trade_count"], 7)
        self.assertEqual(data.attributes["_evicted_winning_trades"], 3)
        self.assertEqual(data.attributes["_evicted_trade_pnl"], -5.25)
        self.assertEqual([trade.trade_id for trade in data.attributes["closed_trades"]], [str(i) for i in range(300)])

    def test_live_data_and_two_forks_are_independent_and_retain_internal_aliases(self):
        probe = self.probe()
        signals = {"rsi": 23.123456789}
        trade = TradeRecord("position", probe.probe_id, ASSET, "BUY", 3.0, 30.0,
                            execution={"shared_signals": signals}, opened_at=NOW)
        probe.open_positions[ASSET] = trade
        probe._pending_intents[ASSET] = _SignalIntent(60.0, 61.0, "exit", "position", signals)
        probe._equity_history = EquityHistory().observe(100, 0, 30).observe(101, 60, 90)
        data = capture_probe_data(probe)
        fork = fork_probe_data(data)
        other = fork_probe_data(data)
        self.assertIs(fork.attributes["open_positions"][ASSET].execution["shared_signals"],
                      fork.attributes["_pending_intents"][ASSET].signals)
        self.assertIs(fork.attributes["_equity_history"].returns,
                      fork.attributes["_equity_history"]._statistics_returns)
        fork.attributes["genome"].assets.append("JUP/USDC")
        fork.attributes["open_positions"][ASSET].execution["shared_signals"]["rsi"] = 1.0
        probe.genome.rsi_period = 50.0
        signals["rsi"] = 99.0
        self.assertEqual(data.attributes["genome"].assets, [ASSET])
        self.assertEqual(data.attributes["genome"].rsi_period, 14.0)
        self.assertEqual(other.attributes["_pending_intents"][ASSET].signals["rsi"], 23.123456789)
        self.assertEqual(data.attributes["_pending_intents"][ASSET].signals["rsi"], 23.123456789)

    def test_shared_capture_memo_preserves_explicit_data_aliases_without_resources(self):
        first, second = self.probe(), self.probe()
        second.genome = first.genome
        second.execution_config = first.execution_config
        memo = {}
        left, right = capture_probe_data(first, memo=memo), capture_probe_data(second, memo=memo)
        self.assertIs(left.attributes["genome"], right.attributes["genome"])
        self.assertIs(left.attributes["execution_config"], right.attributes["execution_config"])
        self.assertIsNot(left.attributes["genome"], first.genome)
        self.assertFalse(left.uses_candle_history)

    def test_repeated_probe_capture_with_shared_memo_cannot_reuse_temporary_wrapper_id(self):
        probes = [self.probe() for _ in range(100)]
        for index, probe in enumerate(probes):
            probe.capital = float(index)
            probe._tick_count = index
        memo = {}
        captured = [capture_probe_data(probe, memo=memo) for probe in probes]
        self.assertEqual([data.attributes["probe_id"] for data in captured],
                         [probe.probe_id for probe in probes])
        self.assertEqual([data.attributes["capital"] for data in captured], list(range(100)))
        self.assertEqual([data.attributes["_tick_count"] for data in captured], list(range(100)))
        self.assertEqual(len({id(data.attributes) for data in captured}), 100)

    def test_current_position_and_v1_floating_values_are_preserved_without_conversion(self):
        probe = self.probe()
        probe.set_funded()
        probe.set_observing()
        probe.on_quote(MarketTick(ASSET, 3.7, 1.0, NOW.timestamp()))
        probe._open_position(ASSET, 3.7, {"rsi": 22.0})
        probe.observe_equity(assets={ASSET}, observed_at=NOW.timestamp(), valid_until=NOW.timestamp() + 30)
        data = capture_probe_data(probe)
        self.assertEqual(data.attributes["capital"].hex(), probe.capital.hex())
        self.assertEqual(data.attributes["open_positions"][ASSET].execution, probe.open_positions[ASSET].execution)
        self.assertEqual(data.attributes["_equity_history"], probe._equity_history)
        self.assertEqual(data.attributes["_quote_observations"], probe._quote_observations)

    def test_probe_rejects_unknown_fields_missing_fields_and_mid_risk_capture(self):
        for mutation in (lambda p: setattr(p, "unreviewed_state", {}),
                         lambda p: delattr(p, "_pending_intents"),
                         lambda p: setattr(p, "_valuation_assets", {ASSET}),
                         lambda p: setattr(p, "capital", True),
                         lambda p: setattr(p, "birth_tick", 1.0),
                         lambda p: setattr(p, "_candle_history", object())):
            probe = self.probe()
            mutation(probe)
            with self.assertRaises(StateComponentError):
                capture_probe_data(probe)

    def test_nested_dataclasses_reject_resources_wrong_types_and_illicit_fields(self):
        mutations = [
            lambda p: p.genome.assets.append(lambda: None),
            lambda p: setattr(p.genome, "rsi_period", "14"),
            lambda p: object.__setattr__(p.execution_config, "hidden_resource", object()),
            lambda p: object.__setattr__(p._equity_history, "_statistics_returns", (object(),)),
            lambda p: object.__setattr__(p._equity_history, "_statistics", (("bad", lambda: None),)),
            lambda p: p._pending_intents.update({ASSET: _SignalIntent(60.0, 61.0, "entry", None, {"bad": object()})}),
            lambda p: p._pending_intents.update({ASSET: _SignalIntent(60.0, 61.0, "entry", None, {"bad": p.genome})}),
        ]
        for mutation in mutations:
            probe = self.probe()
            mutation(probe)
            with self.subTest(mutation=mutation), self.assertRaises(StateComponentError):
                capture_probe_data(probe)

    def test_fork_revalidates_dto_and_rejects_nested_cycles_and_nonfinite_values(self):
        data = capture_probe_data(self.probe())
        data.attributes["_marks"][ASSET] = float("nan")
        with self.assertRaises(StateComponentError):
            fork_probe_data(data)
        data = capture_probe_data(self.probe())
        signals = {}
        signals["cycle"] = signals
        data.attributes["_pending_intents"][ASSET] = _SignalIntent(60, 61, "entry", None, signals)
        with self.assertRaises(StateComponentError):
            fork_probe_data(data)
        with self.assertRaises(StateComponentError):
            fork_probe_data(ProbeData(data.attributes, 1))

    def test_candle_fork_preserves_recursive_ema_and_pending_bucket_without_constructor(self):
        original = history(61)
        with patch.object(CandleHistory, "__init__", side_effect=AssertionError("constructor called")):
            copied = fork_candle_history(original)
        self.assertEqual(history_values(copied), history_values(original))
        self.assertIsNot(copied._assets[ASSET], original._assets[ASSET])
        minute = copied._assets[ASSET].minutes[60 * 60]
        self.assertIs(copied._assets[ASSET].series[60].pending[0], minute)
        self.assertIsNot(minute, original._assets[ASSET].minutes[60 * 60])
        for timeframe in range(1, 61):
            self.assertEqual(copied._assets[ASSET].series[timeframe].emas,
                             original._assets[ASSET].series[timeframe].emas)
        further = [candle(index) for index in range(61, 121)]
        copied.ingest(further, available_at=121 * 60)
        self.assertEqual(original.last_start(ASSET), 60 * 60)
        original.ingest(further, available_at=121 * 60)
        self.assertEqual(history_values(copied), history_values(original))
        self.assertEqual(copied._assets[ASSET].series[60].pending,
                         original._assets[ASSET].series[60].pending)

    def test_candle_snapshots_remain_immutable_and_unshared_maps(self):
        original = history(61)
        copied = fork_candle_history(original)
        before, after = original.latest(ASSET, 1), copied.latest(ASSET, 1)
        self.assertIsNot(before, after)
        self.assertIsNot(before.emas, after.emas)
        self.assertIs(type(after.emas), MappingProxyType)
        with self.assertRaises(TypeError):
            after.emas[2] = 999.0
        with self.assertRaises(AttributeError):
            after.close = 999.0
        self.assertEqual(before, after)

    def test_candle_fork_rejects_unreviewed_attrs_and_nested_wrong_types(self):
        mutations = [
            lambda h: setattr(h, "feed", object()),
            lambda h: setattr(h._assets[ASSET], "callback", lambda: None),
            lambda h: h._assets[ASSET].series[1].closes.append(object()),
            lambda h: object.__setattr__(h.latest(ASSET, 1), "hidden", object()),
            lambda h: object.__setattr__(h.latest(ASSET, 1), "closes", (lambda: None,)),
            lambda h: h._assets[ASSET].series.pop(60),
        ]
        for mutation in mutations:
            value = history(3)
            mutation(value)
            with self.subTest(mutation=mutation), self.assertRaises(StateComponentError):
                fork_candle_history(value)


if __name__ == "__main__":
    unittest.main()
