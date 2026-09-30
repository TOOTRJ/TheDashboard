"""Hand-calculated portfolio metrics and risk/retirement integration."""

import math
import unittest
from datetime import datetime, timezone

from tests.security_support import OfflineTestMixin, deny_network

with deny_network():
    from vonneumann.core.evolution import compute_fitness
    from vonneumann.core.genome import Genome
    from vonneumann.core.market_validation import MarketValueError
    from vonneumann.core.probe import Probe


class ProbeEquityTests(OfflineTestMixin, unittest.TestCase):
    def test_first_modeled_minute_keeps_funded_birth_baseline(self):
        probe = Probe(Genome(), 100, clock=lambda: datetime.fromtimestamp(0, timezone.utc))
        probe.capital = 110
        probe.observe_equity(assets=set(), observed_at=60, valid_until=90)
        self.assertAlmostEqual(probe._equity_history.returns[0], .1)
        self.assertEqual(probe.metrics()["window_start_endpoint"], 0)

    def probe(self, capital=100.0, **genes):
        settings = {"assets": ["SOL/USDC", "JUP/USDC"], "position_size_pct": 0.5,
                    "max_open_positions": 2.0, "stop_loss_pct": 0.1,
                    "take_profit_pct": 0.5, "death_drawdown_pct": 0.15}
        settings.update(genes)
        probe = Probe(Genome(**settings), capital)
        probe.set_funded()
        probe.set_observing()
        return probe

    def observe(self, probe, stamp):
        return probe.observe_equity(assets=set(probe.open_positions),
                                    observed_at=stamp, valid_until=stamp + 30)

    def test_historical_drawdown_survives_recovery_and_summary_reads(self):
        probe = self.probe()
        for stamp, equity in enumerate((100, 120, 96, 120)):
            probe.capital = equity
            self.observe(probe, stamp * 60)
        self.assertAlmostEqual(probe.max_drawdown, .2)
        self.assertEqual(probe.current_drawdown, 0)
        self.assertFalse(probe._should_die())
        self.assertAlmostEqual(probe.fitness, -.2)
        before = probe._equity_history
        self.assertEqual(probe.summary(), probe.summary())
        self.assertIs(before, probe._equity_history)

    def test_no_trades_has_no_artificial_loss_or_sharpe_reward(self):
        probe = self.probe()
        for stamp in (0, 60, 120, 180):
            self.observe(probe, stamp)
        self.assertEqual(probe.fitness, 0)
        self.assertIsNone(probe.sharpe)
        self.assertEqual(probe.metrics()["status"], "zero_variance")
        self.assertAlmostEqual(compute_fitness(-.1, .1), -.3)
        for invalid in (float("nan"), float("inf"), True):
            with self.assertRaises(MarketValueError):
                compute_fitness(invalid, .1)

    def test_position_sizes_determine_equity_return_including_unrealized_pnl(self):
        probe = self.probe(1_000, position_size_pct=.01)
        for asset in probe.genome.assets:
            probe.on_price_update(asset, 100, 0)
        probe._open_position("SOL/USDC", 100, {})  # $10
        probe.genome.position_size_pct = 1.0
        probe._open_position("JUP/USDC", 100, {})  # remaining $990
        self.observe(probe, 0)
        probe.on_price_update("SOL/USDC", 200, 0)
        probe.on_price_update("JUP/USDC", 99, 0)
        self.observe(probe, 60)
        self.assertAlmostEqual(probe.total_value, 1_000.1)
        self.assertAlmostEqual(probe._equity_history.returns[0], .0001)
        self.assertEqual(probe.num_trades, 0)
        self.assertAlmostEqual(probe.fitness, .0001)

    def test_partial_risk_pass_closes_valid_asset_without_using_stale_sibling(self):
        probe = self.probe()
        for asset in probe.genome.assets:
            probe.on_price_update(asset, 100, 0)
            probe._open_position(asset, 100, {})
        self.observe(probe, 0)
        previous_history = probe._equity_history
        probe.on_price_update("SOL/USDC", 70, 0)
        probe.on_price_update("JUP/USDC", 1_000, 0)  # retained but not eligible
        self.assertFalse(probe.observe_equity(assets={"SOL/USDC"}, observed_at=60,
                                             valid_until=90))
        events = probe.risk_tick(assets={"SOL/USDC"})
        self.assertEqual(len(events), 1)
        self.assertNotIn("SOL/USDC", probe.open_positions)
        self.assertIn("JUP/USDC", probe.open_positions)
        self.assertEqual(probe.peak_capital, 100)
        self.assertEqual(probe.max_drawdown, 0)
        self.assertIs(probe._equity_history, previous_history)

    def test_liquidation_preflight_is_pure_and_close_keeps_worst_drawdown(self):
        probe = self.probe()
        probe.on_price_update("SOL/USDC", 100, 0)
        probe._open_position("SOL/USDC", 100, {})
        self.observe(probe, 0)
        probe.on_price_update("SOL/USDC", 60, 0)
        self.observe(probe, 60)
        probe.on_price_update("SOL/USDC", 100, 0)
        before = repr(probe.__dict__)
        for _ in range(3):
            self.assertEqual(probe.validate_liquidation({"SOL/USDC": 100}), 100)
            self.assertEqual(repr(probe.__dict__), before)
        probe.close_all_positions({"SOL/USDC": 100}, "EVOLUTION")
        self.assertAlmostEqual(probe.max_drawdown, .2)
        self.assertEqual(probe.current_drawdown, 0)
        self.assertAlmostEqual(probe.fitness, -.4)

    def test_terminal_loss_records_full_drawdown_without_fabricating_return_sample(self):
        probe = self.probe(position_size_pct=1)
        probe.on_price_update("SOL/USDC", 100, 0)
        probe._open_position("SOL/USDC", 100, {})
        self.observe(probe, 0)
        probe._close_position("SOL/USDC", 0, "TERMINAL_LOSS", terminal_loss=True)
        self.assertEqual(probe.max_drawdown, 1)
        self.assertEqual(probe.fitness, -3)
        self.observe(probe, 60)
        self.assertEqual(probe._equity_history.returns, (-1.0,))
        self.assertTrue(math.isfinite(probe.fitness))
