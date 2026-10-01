# Two-gene EMA baseline contract

Implemented 2026-09-30 for BASE-01. This is an opt-in mechanics profile, not an
empirically validated strategy or a recommendation to trade its preset values.

## Explicit profile and experiment controls

`strategy_profile: "ema_baseline_v1"` enables only the EMA crossing signal.
`enabled_genes` must contain exactly `ema_fast` and `ema_slow`; these are integer
periods, with fast strictly below slow. RSI and volume entry/readiness filters are
disabled by the profile, rather than made constant by freezing their genes.
Omitted profile fields preserve the existing `rsi_ema_volume_v1` behavior.

The opt-in dashboard preset starts with SOL/USDC, completed 15-minute candles,
fast periods 3–12, slow periods 15–60, 25% position sizing, a 3% stop, a 7% profit
trigger and one position. Its common evaluation window is 1,440 modeled minutes
after warmup. These are provisional experiment settings. USD reference accounting
and declared execution costs still apply; the asset's display symbol does not
establish USDC/USD parity.

An experiment has one explicit asset and a fixed timeframe, position/exposure
configuration, protective controls and evaluation horizon. Non-EMA genes resolve
to fixed overrides or registry defaults. They may be chosen between experiments,
but cannot evolve within one. The profile rejects extra enabled genes, multiple
assets/positions, unknown profile names and an age-limit override. A baseline
preset cannot be silently downgraded through a contradictory custom profile.
Preset/config serialization copies mutable lists so editing one run cannot change
future runs. The controller takes a private copy of baseline configuration.

All four existing cohort optimizers use these constraints. Independent
profit-triggered reproduction, diversity replenishment and early age retirement
remain suppressed by the common-cohort lifecycle. A malformed proposed genome is
rejected before retirement/funding mutations. Protective stop, take-profit,
drawdown and account-level limits retain precedence over strategy signals.

## Signal timing and warmup

The shared candle history maintains recursive EMAs from the first accepted
completed candle. Each immutable snapshot now includes the previous completed
candle's EMA values and end time. It never reconstructs a prior EMA from a
truncated rolling window.

- Bullish crossing: previous fast ≤ previous slow **and** current fast > current
  slow.
- Bearish crossing: previous fast ≥ previous slow **and** current fast < current
  slow.
- Constantly being above/below is not a new crossing. Equality on the previous
  candle is allowed; equality on the current candle is not a signal.
- Both observations must be adjacent completed candles. Signal comparisons retain
  full price precision, including small token prices.
- Every candidate requires **61 completed bars**, even if its sampled slow period
  is shorter or its configured range is narrowed. This is a fixed initialization
  convention, not proof that EMA initialization bias is negligible.

At the preset's timeframe, 61 bars represent 915 minutes of candle history.
Accepted prehistory may supply those bars. The cohort horizon starts only when
every candidate is ready. Zero volume is valid for this signal profile, while
the common market-data schema continues to validate finite volume and candle
provenance. No RSI computation is needed for baseline readiness or signals.

Existing observation cursors continue to prevent retrospective entry on a
newborn probe or repeated processing of an old/catch-up candle. A new signal queues
an expiring intent; execution requires a later eligible quote. Safety exits do
not wait for signal warmup. Completed cohorts liquidate with declared costs before
scoring. See [execution contract](EXECUTION-CONTRACT.md).

## Persistence and dashboard interpretation

New resolved configuration, runtime status and startup-failure status record
`strategy_profile` plus the exact versioned `signal_policy`. The baseline policy
is `ema-crossover-v1`; the existing signal policy is `rsi-ema-volume-v1`.
The dashboard validates known policy fields before labeling saved results.
Historical records without policy evidence remain unclassified; an EMA-only
gene mask does not prove that RSI/volume were disabled. These fields use existing
configuration/runtime JSON, so this change requires no database migration.

## Research still required

BASE-02 must add the frozen 20-candidate grid with common initial conditions and
traceable signals, fills and metrics. BASE-03 must compare cash, buy-and-hold,
fixed EMA, exhaustive and seeded-random baselines before drawing conclusions
about the evolutionary optimizers. The current four optimizers passing mechanics
tests does not establish economic usefulness.

DATA-01C must explicitly model historical bar availability/fills and preserve
immutable provider provenance before historical evaluation. Existing replay is
still synthetic-only. Research initialization sensitivity (61 bars versus longer
prehistory), chronological holdouts, regime coverage, serial dependence, multiple
testing, neighboring parameter stability and realistic execution costs. Do not
add a third gene until BASE-05's ablation and held-out evidence support it.
