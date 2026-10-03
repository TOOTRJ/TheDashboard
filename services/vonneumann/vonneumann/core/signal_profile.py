"""Versioned signal semantics, separate from evolvable genome parameters."""

LEGACY_PROFILE = "rsi_ema_volume_v1"
EMA_BASELINE_PROFILE = "ema_baseline_v1"
EMA_GENES = frozenset({"ema_fast", "ema_slow"})
# Fixed across all baseline candidates, seeds and narrowed/control domains.
# The supported slow EMA maximum is 60; a crossing also needs the prior bar.
EMA_WARMUP_BARS = 61


def ema_crossing(previous_fast: float, previous_slow: float,
                 fast: float, slow: float) -> tuple[bool, bool]:
    """Entry/exit predicates after the caller validates adjacent warmed bars.

    Indicator inputs are derived binary64 views; these comparisons never
    produce a price, quantity, budget or protective threshold.
    """
    return (previous_fast <= previous_slow and fast > slow,
            previous_fast >= previous_slow and fast < slow)


def signal_policy(profile: str) -> dict:
    if profile == EMA_BASELINE_PROFILE:
        return {
            "version": "ema-crossover-v1", "profile": profile,
            "rsi_enabled": False, "volume_enabled": False,
            "warmup_completed_bars": EMA_WARMUP_BARS,
            "entry": "previous_fast_lte_slow_then_fast_gt_slow",
            "exit": "previous_fast_gte_slow_then_fast_lt_slow",
            "execution": "later_eligible_quote",
        }
    if profile == LEGACY_PROFILE:
        return {
            "version": "rsi-ema-volume-v1", "profile": profile,
            "rsi_enabled": True, "volume_enabled": True,
            "warmup_completed_bars": None,
            "entry": "rsi_oversold_ema_above_and_volume",
            "exit": "rsi_overbought_or_ema_below",
            "execution": "later_eligible_quote",
        }
    raise ValueError("Unknown strategy profile")
