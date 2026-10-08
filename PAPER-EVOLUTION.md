# How the selected paper probes and evolution work

Reviewed against the hosted `paper-v5` implementation on 2026-10-08. This
describes the selected finite, two-gene genetic-algorithm pilot. Older probe
settings and other experimental solvers in the repository are not the current
hosted profile. Paper money and USD reference prices do not represent Solana
wallet balances or executed swaps.

**A probe is one candidate strategy and its independent paper account.** It has
a fixed genome for its evaluation window, a unique identity, cash, positions,
observed equity/risk, trade history, generation and ancestry. A colony compares
eight probes against the same observations. Evolution changes numeric strategy
parameters; it does not rewrite its own software.

| Selected setting | Current value |
| --- | --- |
| Colony paper capital | $1,000 USD |
| Founders | Eight accounts, $100 each; $200 reserve |
| Asset/accounting | SOL/USD reference, long-only, exact decimal ledger |
| Evolvable genes | Integer fast EMA 3–12 and slow EMA 15–60 |
| Search space | 460 valid pairs; fast is always less than slow |
| Candles | Completed 15-minute closes |
| Common warmup | 61 completed bars, covering 15 hours 15 minutes |
| Entry budget | 25% of a probe's available cash; one open position maximum |
| Protective exit | 3% stop loss / 7% take profit from entry reference price |
| Probe termination | 20% observed drawdown from that probe's equity peak |
| Colony breaker | 30% loss from the configured colony equity baseline |
| Evaluation | Common one-hour source-time window |
| Hosted pilot limit | One replacement, then reserved Stop; 60-second deadline grace |
| Execution costs in this pilot | Zero fee, slippage and half-spread; uncalibrated scenario |

RSI and volume filters are disabled. Asset, timeframe, position size, protective
thresholds and lifecycle controls are fixed, not searchable genes. Legacy
`benchmark_target_pct` and `reproduce_target_dollars` fields do not trigger
reproduction in this profile.

**Prices and signals have different jobs.** Jupiter Price V3 supplies USD
reference observations; Solana RPC evidence supports source-time checks.
Birdeye supplies completed historical/current candle closes for the EMA profile.
The dashboard's demo price banner is unrelated to this worker input. Historical
warmup initializes indicators only; it does not invent trades before the run.

An EMA starts from the simple average of its initial period. Later values use
`alpha = 2 / (period + 1)` and
`new_ema = alpha * close + (1 - alpha) * previous_ema`.

An entry signal requires the prior fast EMA to be at or below the slow EMA,
followed by the current fast EMA rising above it. An exit signal requires the
opposite crossing. Being above the slow EMA without a new crossing is not an
entry. Decisions use adjacent, warmed, completed candles with a five-second
completion margin. A queued signal can execute only on a later eligible accepted
price observation; the signal's own observation is not its fill.

Every accepted fresh price also checks protective exits, marked equity and
drawdown. A gap through a stop fills at the next accepted reference price, not a
guaranteed stop price. Protective effects are committed before ordinary candle
decisions, so a later candle/selection failure cannot erase an accepted close.
Terminated probes freeze/retire and remain original cohort members; the algorithm
does not omit losers or replace them early with unevaluated children.

The worker checks source age, receipt/acquisition age, timestamp/block ordering,
completed-bar continuity, owner/run/revision, lease and credential validity.
Rejected input is not admitted, re-timestamped or counted as valid evidence.
The selected paper policy can discard at most two consecutive source regressions
per episode and eight per run, with a 15-second episode deadline. Other failures
retain their separate closure rules. Polling waits at least five seconds after
the previous tick completes, so provider/database work adds to the cadence.

**Evolution needs a complete, comparable cohort.** All eight original probes
share one evaluation start/end and retain their initial phenotype throughout.
The first valid observation at or after the one-hour deadline liquidates
surviving positions under the configured cost model, completes each original
result once, and checks funding/risk before replacement. An individually dead
probe cannot make the cohort complete before that common deadline. Aborted or
partial windows remain history but are not parent-selection input.

The current versioned fitness policy is
`equity-roi-historical-dd-v1`, marked `provisional_heuristic`:

```
ROI = (final net paper cash - starting probe cash) / starting probe cash
fitness = ROI - 2 * observed historical maximum drawdown
```

Drawdown is the largest observed `(peak equity - current equity) / peak equity`
over accepted observations, including marked open positions. It is not the
unobserved continuous-market maximum between observations. Money calculations
use exact scaled decimal/integer amounts; EMA values and finite ranking views
use binary64. Cash supports 36 decimal places; prices and quantities support
18. These are accounting bounds, not evidence of provider or fill precision.

| Example | ROI | Maximum observed drawdown | Fitness |
| --- | --- | --- | --- |
| A | 10% | 3% | 0.04 |
| B | 8% | 1% | 0.06 |

B ranks above A under this policy despite its lower return. Trade count, win
rate, dollar-profit milestones and Sharpe are not direct breeding rewards. A
valid no-trade probe can score zero. A losing cohort is still valid evidence;
the algorithm can breed the best relative loser. There is no profitable/live
promotion threshold in this selection rule.

**Parent selection and mutation are stochastic but reproducible.** Each parent
tournament samples up to three original completed candidates and chooses the
highest fitness in that sample. The mate comes from a tournament excluding the
first parent. The choice is roughly 70% two-parent crossover and 30% one-parent
copy per reproduction decision; a finite generation need not match those
percentages exactly.

Uniform crossover selects each active gene from a parent and creates complementary
children. Each active gene independently has a 20% mutation chance after crossover,
or 30% after one-parent copying. Gaussian mutation uses standard deviation 15%
of that gene's configured range; validation rounds integer genes using the
reviewed half-up rule and clamps them to their domain. Fixed controls remain
unchanged. Mutation may round to the same value, and duplicate children are
allowed. The production GA has no guaranteed unchanged elite survivor.

The private seeded search streams record founders, selection and child mutation
state. Reproducing a result requires the same software/profile, seed, input
observations and event order, not merely the same seed. Stored lineage names
the actual one or two parents and operation; it is not a claim of equal genetic
contribution or a future profit guarantee.

After a valid full selection, all eight original accounts retire. Their cash
returns to the reserve, and eight new generation-1 accounts receive $100 each
from existing colony money. The system does not manufacture capital or let a
winner's larger starting account bias the next comparison. If a full next
cohort cannot be funded, replacement is refused. The finite hosted pilot stops
after this first replacement, so the new cohort is aborted/unscored; that is
expected and does not invalidate the completed founder results.

**Durability is separate from fitness.** Supabase atomically stores economic
effects, source/action evidence, engine/checkpoint state and ordered events.
Relay acknowledgments and browser projections track the same committed identities.
The dashboard publishes a complete bounded snapshot at one revision; it retains
the last complete snapshot and reports a read error if any record is malformed.
The Railway worker computes decisions; Vercel hosts controls/history; Supabase
stores authoritative paper records. No signing key or live swap is involved.

**Remaining acceptance and research are explicit.** One hour yields about four
new 15-minute bars and tests mechanics, not strategy profitability or stable
multi-generation improvement. Before performance claims or gene expansion, the
backlog requires realistic cost/fill calibration, longer representative windows,
multiple seeds, held-out data, equal-budget grid/random/baseline comparisons,
diversity/elitism and objective-weight evaluation. Continuous operation also
needs bounded versioned checkpoints/retention, restart/recovery and measured
quota/cost/resource tails. The dashboard still needs the configured worker versus
selected-history distinction and richer assessment/lineage details. See
[TODO.md](TODO.md), [MVP readiness](MVP-READINESS.md), and the dated pilot audits
for actual progress and limitations.

Implementation references:

- [Pinned profile and exact accounting views](services/vonneumann/vonneumann/core/exact_rehearsal.py)
- [Protective decisions and complete replacement](services/vonneumann/vonneumann/core/exact_lifecycle.py)
- [Cohort completion and abort semantics](services/vonneumann/vonneumann/core/evaluation.py)
- [Fitness policy](services/vonneumann/vonneumann/core/evolution.py)
- [Parent selection, crossover and mutation](services/vonneumann/vonneumann/core/strategies/genetic_algorithm.py)
- [Signal rules](services/vonneumann/vonneumann/core/signal_profile.py)
- [Browser's complete snapshot and detail readers](src/lib/probes/paper-api.ts)
