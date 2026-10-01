# Offline EMA grid, genetic search and control comparisons

Implemented 2026-09-30 as BASE-02A / BASE-03A / BASE-03B. This is a **synthetic mechanics
experiment**, not a historical backtest or evidence of a profitable strategy.
It needs no provider credentials, database, running worker, wallet or network.
The dashboard does not launch it; use the isolated worker Python environment.

## What is evaluated

The runner uses the existing `ReplayFeed`, shared `CandleHistory`, real EMA
`Probe` signals/protective exits, and the existing percentage-cost calculators.
It does not use the live Genesis controller: each candidate has an independent
account, with no shared reserve, capital redistribution, optimizer replacement or
aggregate colony circuit breaker. EMA candidates retain their fixed probe
stop/take/drawdown controls; an early dead candidate holds cash to the deadline.
This comparison does not change the deployed bot's risk policy.

Twenty candidates cover the Cartesian product:

- Fast EMA: 3, 5, 8, 12 completed timeframe bars.
- Slow EMA: 15, 20, 30, 45, 60 completed timeframe bars.

This exhausts the declared twenty points, not every feasible integer EMA pair.
Four additional prespecified training controls are evaluated separately:

| Control | Policy |
| --- | --- |
| Fixed EMA 9/21 | Same EMA controls; separate from the twenty-point grid |
| Cash | Initial USD reference cash, zero interest, no trades |
| Buy-and-hold 25% | Invest 25% of initial cash once; retain 75% cash |
| Buy-and-hold 100% | Invest all initial cash once; separate market-exposure reference |

Both buy-and-hold controls buy on the first quote **after** the window boundary
and sell on its terminal quote. They pay the same declared entry/exit costs,
without rebalancing or protective stop/take/drawdown exits. They are passive
comparators, not alternate configurations of the risk-managed EMA strategy.

Default settings are one SOL/USDC display pair, 15-minute candles, 1,000 USD
reference cash per account, 1,440 training minutes and 1,440 holdout minutes.
The existing EMA profile fixes 25% position sizing, 3% stop, 7% take-profit,
20% drawdown retirement and one position. Timeframe is a fixed experiment
control (integer 5–60), never a search gene. The dataset origin must align to its
UTC candle bucket. An asset absent from the dataset is rejected.

## Frozen chronology and selection

Every candidate requires the same 61 completed timeframe bars. The default
experiment needs **3,795 one-minute frames**: 915 warmup, 1,440 training and 1,440
holdout. Each scored window includes its cash-only boundary observation and its
terminal observation. Training's final quote is also the holdout's cash-only
boundary; the same quote cannot execute a carried trade in the new account.

The runner requires every completed minute on its modeled quote frame. Missing,
delayed or insufficient candle coverage fails, even when the underlying archive
is structurally valid and quote frames continue. This intentionally strict
synthetic contract does not model provider publication delays or historical
availability. Existing provider-replay restrictions remain in force.

No signals execute on the starting boundary. Interior signals retain the real
probe's later-source/receipt execution rule. At the exact terminal quote,
protective risk and drawdown death run before mandatory costed liquidation;
pending entry/exit intents are discarded. Training never uses a later holdout
price to close a position. Holdout preserves only the causal indicator prefix:
accounts, cash, positions, intents, risk peaks and metrics start fresh.

The selection objective is the existing versioned provisional heuristic:

`terminal net portfolio ROI − 2 × observed historical maximum drawdown`

The ledger observes pre-action reference equity, intermediate equity after each
fill, and post-action equity, including terminal costs. Ties use ascending
candidate ID. No Sharpe statistic is used or reported. This avoids presenting the
existing engine's pre-decision return diagnostic as a complete net-cost return
series. The selected training winner need not outperform cash or passive holding.

A private seeded permutation samples the same grid without replacement. A small
reference GA uses the same grid and initial four candidates. Both stop at the
same prespecified logical request budget (default 10, allowed 1–20), and record
best-so-far results only through that budget. The full random permutation remains
metadata; scores beyond the configured prefix are not exposed to that search.
Both access the immutable exhaustive training cache through a scalar callback,
without the full score table, oracle optimum or holdout evidence.

The GA policy is fixed before evaluation:

| Component | Policy |
| --- | --- |
| Population | Four; budgets below four stop during shared initialization |
| Selection | Binary tournament over distinct population slots, fitness descending, then candidate ID and slot ascending |
| Crossover | Independently choose each locus from either selected parent |
| Mutation | Probability 0.25 per locus; uniformly select another legal grid level |
| Replacement | One copied elite and three requested children; parents stay frozen during the generation |
| Duplicates | Allowed and charged one request each; no forced unseen-candidate fallback |
| Partial generation | Evaluated children can improve the incumbent; incomplete population is never used for parent selection |
| Stopping | Check before each callback; no budget overshoot or adaptive stopping |

The population and mutation settings are local mechanics choices, not tuned or
recommended trading hyperparameters. This reference GA does **not** replace or
benchmark the production worker's full solver, funding or reproduction lifecycle.
That integration needs its own exact-domain adapter and acceptance evidence.

Each trace records requested ID, returned fitness, initialization/offspring phase,
parents, mutated loci, duplicate status and incumbent. Score-cache reads count
every logical request; unique candidates and duplicates are separate. Copied
elite scores are free reuse, explicitly counted. Both searches perform zero
additional market replays: the runner has already evaluated 20 grid accounts
and four controls. Equal logical budgets are not a measured runtime saving or
equal numbers of unique candidates.

Only after both searches stop does the runner add the fitness gap to the grid
optimum, optimum-fitness hit, canonical-winner hit and GA-minus-random fitness.
A different candidate can tie the optimum with zero gap. Fitness gaps are in
objective units, not return percentages. Random at budget 20 equals exhaustive
search by construction; GA can revisit candidates and miss the optimum even at
20. The harness accepts an underperforming GA result without changing its policy.

The complete training ledger is hashed before holdout decisions. Only the grid
winner, the random winner, the GA winner and the four prespecified controls proceed to
holdout, with duplicate winners evaluated once. Holdout results remain separate;
there is no holdout ranking or reselection. Changing only the dataset suffix
cannot change prior trading, training liquidation or winner selection. Choosing
new seeds/settings after viewing a holdout consumes that holdout for research.

## Result evidence and verification

Each candidate/window has a ledger row for every observation, including the
starting and terminal boundaries. Rows record the dataset frame/time, pre-action
equity, cash, position value, post-action equity, worst drawdown, state, newly
completed EMA values/crossings, pending intents before/after and ordered events.
Every fill records its full execution calculation and intermediate cash/equity.
Event IDs are deterministically mapped locally; random UUIDs and wall-clock
creation times do not enter results. Capturing events immediately preserves the
whole history even when the live probe trims its own trade cache.

The runner independently reconciles fill cash/quantity against the probe account,
closed-trade P&L against final cash, and absence of positions at window completion.
The result also records the input dataset/hash, resolved controls, execution
assumptions, exact boundaries, candidate list, selection/tie-break rules, Python
version and SHA-256 of the relevant source files. Software changes during a run
abort it; cancellation yields without publishing a partial experiment.

Output is a new local directory with exactly `result.json` and `manifest.json`.
The codec uses sorted compact finite ASCII JSON with a final newline. The
manifest contains payload bytes/hash; its own canonical SHA-256 is the result ID.
Limits are 128 MiB payload, 64 KiB manifest and nesting depth 20. Reads reject
symlinks, traversal, nonregular files, missing/extra files, duplicate keys,
noncanonical bytes, excessive sizes and wrong hashes. Loaded data is immutable.

Publication validates before exclusive creation, writes/fsyncs the payload first,
then the manifest and directories. Existing destinations are never overwritten.
A failed I/O operation can leave a new incomplete directory, which the loader
rejects; a late synchronization failure can leave complete readable files without
confirming crash durability. No cleanup deletes possibly reassigned paths. Choose
a new destination after investigating a failed publication.

`load_result` checks structure and byte integrity only. **The `verify` command
reruns the bound dataset and compares the entire payload**, including every
ledger entry and source fingerprint. A changed ledger with freshly recomputed
hashes still fails replay verification. Changed source/runtime versions also fail
exact reproduction. Hashes and replay consistency do not establish authentic
market data or correctness beyond the tested model.

BASE-03B bumps the engine to `ema-grid-mechanics-v2` and fingerprints the search
module. The generic `ema-research-v1` payload and artifact envelope remain valid;
the strict configuration field set is unchanged. Existing `random_seed` and
`random_budget` names now govern both paired searches. Version 1 artifacts remain
readable, but full replay needs their original source/runtime. Version 2 does
not claim byte compatibility: random convergence now ends at the selected budget
and GA evidence/holdout candidates are included. Do not overwrite old artifacts.

## Run in an isolated Python environment

From the repository root, activate the project's reviewed worker Python 3.12
environment. Create a parent directory outside source control; each output below
must not already exist. On macOS use a physical path such as `/private/tmp`, since
symlink paths are deliberately rejected. Example with explicitly hypothetical
costs (5 bps fee, 5 bps half-spread and 10 bps adverse slippage on each fill):

```sh
PYTHON_DOTENV_DISABLED=1 PYTHONPATH=services/vonneumann python -B -m vonneumann.market.dataset_cli generate-synthetic \
  --output /private/tmp/dashboard-grid-input --frames 3795 --assets SOL/USDC --seed 42

PYTHON_DOTENV_DISABLED=1 PYTHONPATH=services/vonneumann python -B -m vonneumann.research.cli run \
  --dataset /private/tmp/dashboard-grid-input --output /private/tmp/dashboard-grid-result \
  --fee-bps 5 --half-spread-bps 5 --slippage-bps 10

PYTHON_DOTENV_DISABLED=1 PYTHONPATH=services/vonneumann python -B -m vonneumann.research.cli verify \
  --dataset /private/tmp/dashboard-grid-input --result /private/tmp/dashboard-grid-result
```

The command prints compact JSON with dataset/result identities, declared scope,
training selections and separate holdout summaries. Provider, database, server
configuration and environment-loading imports are not needed. Tests invoke the
real command in fresh processes with network/import guards and no credentials.
Zero cost defaults are explicit frictionless mechanics controls, not estimates.
`--random-seed` controls shared initialization and separate private GA offspring
randomness; `--random-budget` is the equal logical budget for both algorithms.

## Remaining gates and deeper research

Keep BASE-02/03 and Gate B open for empirical evaluation. DATA-01C must supply
representative licensed historical data with truthful availability/provenance;
FILL-01B must justify latency, fees, market impact, capacity and rejected fills.
No historical performance claim follows from this synthetic experiment. The
existing 10,000-frame cap spans less than seven modeled days; larger archives
need streaming result ledgers, capacity measurements and a reviewed data model.

The equal-domain/budget reference GA comparison now has independent regression
coverage, including unseen-score isolation, all budget prefixes and partial
generations. Before drawing search-quality conclusions, predeclare a paired
multi-seed protocol, representative historical windows, failure accounting and
uncertainty summaries. Preserve all attempted settings/seeds and failed runs,
not just winners. Research logical versus unique-evaluation budgets, duplication
cost, initialization/population bias, and integration with the repaired worker
solver before adopting a library or adding genes. Research EMA initialization sensitivity with longer
prehistory, chronological/regime coverage, serial dependence, holdout reuse and
multiple-testing corrections. Do not assume twenty correlated candidates are
independent trials or that a deflated-Sharpe/PBO formula is automatically valid.

Primary research supporting these boundaries, reviewed 2026-09-30:

- [Bergstra and Bengio, Random Search for Hyper-Parameter Optimization](https://jmlr.org/papers/v13/bergstra12a.html): random-search comparison principles; its ML results do not prove an advantage for this trading grid.
- [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html): forward chronology; any financial gap/embargo needs a separate justification.
- [Freqtrade recursive analysis](https://docs.freqtrade.io/en/stable/recursive-analysis/): indicator initialization sensitivity; 61 bars is a reproducibility convention, not a convergence guarantee.
- [Freqtrade backtesting](https://www.freqtrade.io/en/stable/backtesting/): make execution and forced terminal closures explicit; its fill rules are not copied here.
- [Bailey et al., Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) and [Bailey/López de Prado, Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551): selection/multiple-testing risks requiring deeper methodology work before empirical conclusions.
- [pymoo termination](https://pymoo.org/interface/termination.html) separates evaluation limits from generation limits; this implementation enforces its local request limit before every callback.
- [pymoo GA](https://pymoo.org/algorithms/soo/ga.html) exposes duplicate elimination as an explicit choice, while [DEAP algorithms](https://deap.readthedocs.io/en/master/api/algo.html) separates selection, variation and fitness evaluation. These are methodological references; no dependency or third-party implementation is copied into this bounded reference search.

DB-03A/SVC-02 remain prerequisites for unattended worker hosting. This local file
ledger supplies offline experiment evidence; it does not implement the worker's
transactional database ledger, restart recovery or ownership fencing.
