"""Exact-source research views agree with the production shared candle EMA."""

import unittest

from vonneumann.core.exact_rehearsal import ExactObservation, _append_candle
from vonneumann.market.candles import CandleHistory, MinuteCandle


class ExactIndicatorViewsTests(unittest.TestCase):
    def test_all_periods_match_shared_history_through_warmup_crossings_and_retention(self):
        for small in (False, True):
            with self.subTest(tiny_price=small):
                history = CandleHistory(["SOL/USDC"])
                engine = {"ema": {"count": 0, "last_end": None, "closes": [], "values": {}, "previous": {}}}
                for bar in range(1, 78):
                    units = 100 + (bar % 7) * 3 if bar % 11 else 80
                    price = f"0.000000000000000{units:03}".rstrip("0") if small else str(units)
                    end = bar * 900
                    # A constant exact close within each fifteen-minute bucket
                    # lets the independent production aggregator form that bar.
                    derived = float(price)
                    history.ingest([MinuteCandle("SOL/USDC", minute, derived, derived,
                        derived, derived, 1.0, "synthetic-exact-fixture-v1")
                        for minute in range(end - 900, end, 60)], available_at=float(end))
                    _append_candle(engine, ExactObservation(end, price, end, price))
                    shared = history.latest("SOL/USDC", 15)
                    self.assertEqual(engine["ema"]["count"], shared.completed_count)
                    self.assertEqual(engine["ema"]["values"],
                                     {str(period): value.hex() for period, value in shared.emas.items()})
                    self.assertEqual(engine["ema"]["previous"],
                                     {str(period): value.hex() for period, value in shared.previous_emas.items()})
                    self.assertEqual([float(value) for value in engine["ema"]["closes"]], list(shared.closes))


if __name__ == "__main__":
    unittest.main()
