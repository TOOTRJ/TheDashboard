"""Controlled Probe identities and paper receipt time exercise real decisions."""

from copy import deepcopy
from datetime import datetime, timezone
import random
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.genome import Genome
    from vonneumann.core.market_validation import MarketValueError, ProbeStepError
    from vonneumann.core.probe import Probe
    from vonneumann.core.types import EventType, ProbeState
    from vonneumann.market.feed import MarketTick, QuoteEvidence


ASSET = "SOL/USDC"


def identity(index):
    return str(UUID(int=index))


class Sources:
    def __init__(self):
        self.wall = 1200.
        self.monotonic = 20.
        self.next_id = 1
        self.id_calls = 0
        self.monotonic_calls = 0

    def now(self):
        return datetime.fromtimestamp(self.wall, timezone.utc)

    def identify(self):
        result = identity(self.next_id)
        self.next_id += 1
        self.id_calls += 1
        return result

    def monotonic_now(self):
        self.monotonic_calls += 1
        return self.monotonic


class History:
    """Completed offline candle evidence; Probe runs its actual signal logic."""
    def __init__(self):
        self.snapshot = None

    def latest(self, asset, timeframe):
        return self.snapshot

    def publish(self, end=1200):
        self.snapshot = SimpleNamespace(end=end, closes=(105, 104, 103, 102, 101, 100),
            volumes=tuple([10] * 20 + [20]), emas=MappingProxyType({2: 102, 3: 101}),
            completed_count=60, source="offline", quote_currency="USD", volume_unit="token")


class ProbeDecisionSourcesTests(OfflineTestMixin, unittest.TestCase):
    def make_probe(self, *, mode="paper", id_factory=None, monotonic_clock=None, explicit_id=None):
        sources, history = Sources(), History()
        genome = Genome(assets=[ASSET], num_assets=1, timeframe_minutes=5, rsi_period=5,
                        ema_fast=2, ema_slow=3, rsi_oversold=30, volume_threshold=1.5,
                        benchmark_target_pct=100, reproduce_target_dollars=1000,
                        death_drawdown_pct=.99, stop_loss_pct=.1, take_profit_pct=.2,
                        position_size_pct=.5, max_open_positions=1)
        probe = Probe(genome, 100, mode=mode, probe_id=explicit_id,
            clock=sources.now, candle_history=history,
            id_factory=sources.identify if id_factory is None else id_factory,
            monotonic_clock=sources.monotonic_now if monotonic_clock is None else monotonic_clock)
        probe.set_funded()
        probe.set_observing()
        return probe, sources, history

    @staticmethod
    def quote(probe, sources, *, stamp, receipt, price=100):
        probe.on_quote(MarketTick(ASSET, price, 999_999, stamp,
                                 QuoteEvidence(77, sources.wall, receipt)))

    def trace(self):
        probe, sources, history = self.make_probe()
        self.assertEqual(probe.probe_id, identity(1))
        self.assertEqual(probe.born_at, sources.now())
        history.publish()
        self.quote(probe, sources, stamp=1201, receipt=10)
        self.assertEqual(probe.tick(), [])
        self.assertEqual(probe._pending_intents[ASSET].receipt_boundary, 20)
        self.assertEqual(sources.monotonic_calls, 1)
        sources.wall = 1202
        self.quote(probe, sources, stamp=1202, receipt=15)
        self.assertEqual(probe.tick(), [])
        self.assertEqual(probe.open_positions, {})
        sources.wall = 1203
        self.quote(probe, sources, stamp=1203, receipt=21, price=105)
        events = probe.tick()
        self.assertEqual([event.event_type for event in events], [EventType.TRADE_OPENED])
        self.assertEqual(events[0].timestamp, sources.now())
        self.assertEqual(events[0].data["trade_id"], identity(2))
        trade = probe.open_positions[ASSET]
        self.assertEqual(trade.opened_at, sources.now())
        self.assertEqual(trade.trade_id, identity(2))
        sources.wall = 1204
        self.quote(probe, sources, stamp=1204, receipt=22, price=90)
        closing = probe.tick()
        self.assertEqual([event.event_type for event in closing], [EventType.TRADE_CLOSED])
        self.assertEqual(closing[0].timestamp, sources.now())
        self.assertEqual(trade.closed_at, sources.now())
        self.assertEqual(sources.id_calls, 2)
        self.assertEqual(sources.monotonic_calls, 1)
        self.assertEqual(probe.open_positions, {})
        return [event.to_ws_message() for event in events + closing], probe.capital

    def test_actual_paper_decisions_replay_ids_times_and_receipt_order_without_global_sources(self):
        before = random.getstate()
        with patch("vonneumann.core.probe.uuid.uuid4", side_effect=AssertionError("global identity used")), \
             patch("vonneumann.core.probe.time.monotonic", side_effect=AssertionError("global monotonic used")), \
             patch("vonneumann.core.probe.utc_now", side_effect=AssertionError("global clock used")):
            self.assertEqual(self.trace(), self.trace())
        self.assertEqual(random.getstate(), before)

    def test_dynamic_defaults_honor_patches_after_probe_construction(self):
        sources, history = Sources(), History()
        with patch("vonneumann.core.probe.uuid.uuid4", return_value=UUID(int=1)):
            probe = Probe(Genome(assets=[ASSET], num_assets=1), 100, clock=sources.now)
        self.assertEqual(probe.probe_id, identity(1))
        with patch("vonneumann.core.probe.uuid.uuid4", return_value=UUID(int=2)):
            event = probe._open_position(ASSET, 100, {})
        self.assertEqual(event.data["trade_id"], identity(2))
        # A default wrapper must resolve time.monotonic at use, not capture the
        # builtin in a default argument or retain its value from construction.
        paper, sources, history = self.make_probe()
        paper._monotonic_clock = Probe(Genome(), 100)._monotonic_clock
        history.publish()
        self.quote(paper, sources, stamp=1201, receipt=10)
        with patch("vonneumann.core.probe.time.monotonic", return_value=30):
            paper.tick()
        self.assertEqual(paper._pending_intents[ASSET].receipt_boundary, 30)

    def test_generated_ids_are_canonical_but_explicit_legacy_probe_identity_is_preserved(self):
        for generated in (None, 1, True, UUID(int=1), "", "not-an-id", identity(1).replace("-", ""),
                          "{00000000-0000-0000-0000-000000000001}",
                          "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"):
            with self.subTest(generated=generated), self.assertRaises(ValueError):
                Probe(Genome(), 100, id_factory=lambda: generated)
        probe, sources, _ = self.make_probe(explicit_id="historical-probe-id")
        self.assertEqual(probe.probe_id, "historical-probe-id")
        self.assertEqual(sources.id_calls, 0)
        probe._open_position(ASSET, 100, {})
        self.assertEqual(probe.open_positions[ASSET].trade_id, identity(1))

    def test_invalid_or_raising_trade_id_source_cannot_change_economic_state(self):
        def unavailable():
            raise RuntimeError("identity unavailable")
        for source in (lambda: "bad-id", unavailable):
            with self.subTest(source=source):
                probe, _, _ = self.make_probe(id_factory=source, explicit_id=identity(1))
                before = (probe.capital, deepcopy(probe.open_positions), list(probe.closed_trades), probe.state)
                with self.assertRaises((ValueError, RuntimeError)):
                    probe._open_position(ASSET, 100, {})
                self.assertEqual((probe.capital, probe.open_positions, probe.closed_trades, probe.state), before)

    def test_trade_id_source_failure_preserves_eligible_pending_signal(self):
        for failing in (lambda: "not-canonical", iter(()).__next__):
            with self.subTest(source=failing):
                probe, sources, history = self.make_probe()
                history.publish()
                self.quote(probe, sources, stamp=1201, receipt=10)
                probe.tick()
                pending = probe._pending_intents[ASSET]
                sources.wall = 1203
                self.quote(probe, sources, stamp=1203, receipt=21)
                probe._id_factory = failing
                with self.assertRaises(ProbeStepError) as error:
                    probe.tick()
                self.assertEqual(error.exception.events, ())
                self.assertIs(probe._pending_intents[ASSET], pending)
                self.assertEqual(probe.capital, 100)
                self.assertEqual(probe.open_positions, {})
                probe._id_factory = sources.identify
                events = probe.tick()
                self.assertEqual([event.event_type for event in events], [EventType.TRADE_OPENED])
                self.assertEqual(probe._pending_intents, {})
                self.assertEqual(sources.id_calls, 2)

    def test_invalid_or_raising_monotonic_source_does_not_consume_candle(self):
        def unavailable():
            raise RuntimeError("clock unavailable")
        for source in (lambda: float("nan"), lambda: -1, lambda: True, unavailable):
            with self.subTest(source=source):
                probe, sources, history = self.make_probe(monotonic_clock=source)
                history.publish()
                self.quote(probe, sources, stamp=1201, receipt=10)
                cursors, intents = dict(probe._candle_cursors), dict(probe._pending_intents)
                with self.assertRaises((MarketValueError, RuntimeError)):
                    probe._discover_candle_signals()
                self.assertEqual(probe._candle_cursors, cursors)
                self.assertEqual(probe._pending_intents, intents)

    def test_simulation_never_uses_paper_monotonic_source(self):
        def unexpected():
            raise AssertionError("paper clock used in simulation")
        probe, sources, history = self.make_probe(mode="simulation", monotonic_clock=unexpected)
        history.publish()
        probe.on_quote(MarketTick(ASSET, 100, 20, 1200))
        self.assertEqual(probe.tick(), [])
        self.assertEqual(probe._pending_intents[ASSET].receipt_boundary, 1200)

    def test_rejected_or_duplicate_open_does_not_consume_an_identity(self):
        probe, sources, _ = self.make_probe()
        probe.capital = .001
        self.assertIsNone(probe._open_position(ASSET, 100, {}))
        self.assertEqual(sources.id_calls, 1)
        probe.capital = 100
        probe._open_position(ASSET, 100, {})
        self.assertIsNone(probe._open_position(ASSET, 100, {}))
        self.assertEqual(sources.id_calls, 2)

    def test_repeated_trade_identity_rejects_before_cash_or_positions_change(self):
        probe, sources, _ = self.make_probe()
        probe.genome.max_open_positions = 2
        probe._open_position(ASSET, 100, {})
        original = probe.open_positions[ASSET]
        for repeated in (probe.probe_id, original.trade_id):
            with self.subTest(repeated=repeated):
                probe._id_factory = lambda: repeated
                before = (probe.capital, dict(probe.open_positions), list(probe.closed_trades))
                with self.assertRaisesRegex(ValueError, "repeated"):
                    probe._open_position("JUP/USDC", 1, {})
                self.assertEqual((probe.capital, probe.open_positions, probe.closed_trades), before)
        probe._close_position(ASSET, 100, "test")
        cash = probe.capital
        probe._id_factory = lambda: original.trade_id
        with self.assertRaisesRegex(ValueError, "repeated"):
            probe._open_position(ASSET, 100, {})
        self.assertEqual(probe.capital, cash)
        self.assertEqual(probe.open_positions, {})
        self.assertEqual(probe.closed_trades, [original])

    def test_noncallable_sources_fail_at_construction(self):
        for kwargs in ({"id_factory": "id"}, {"monotonic_clock": 10}, {"id_factory": False}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Probe(Genome(), 100, **kwargs)


if __name__ == "__main__":
    unittest.main()
