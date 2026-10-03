# Bounded exact engine/database rehearsal

DB-03A2C2B starts a **new, flat, synthetic research run**. It integrates the
existing four optimizers and EMA crossover predicates with the exact execution
policy and the isolated PostgreSQL command contract. It is not connected to the
application controller, production database, a hosted worker, or a wallet.
The parent C2 and D/A3 production gates remain open. C3's bounded coordinator
and delivery contract are described in [acknowledged transitions](ACKNOWLEDGED-TRANSITIONS.md).

## Admitted experiment

The profile `ema-baseline-exact-rehearsal-v1` fixes eight candidates, one supported
asset, 15-minute completed candles, a shared 61-bar warmup, and one-hour common
evaluation windows. Only the fast and slow EMA genes evolve. Entry budgets use
one quarter of the account's exact available cash, rounded down on cash36.
Stop loss and take profit compare the new reference price against 97% and 107%
of the original **reference entry price**, including equality. Cross-multiplying
integer price units avoids a rounded threshold or binary64 equality error.
Cost-adjusted fill prices are recorded separately by `usd-reference-decimal-v2`.

This profile implements per-position protection and observed account drawdown
for fitness. It is not the full controller's account/colony risk-latch,
early-terminal-member, pause/stop, recovery, diversity or auto-spawn lifecycle.
Those transitions remain parent C2 acceptance before replacing the application
controller; the three-generation limit is an explicit rehearsal admission bound.

Inputs must already contain canonical decimal strings on the reviewed grids:
cash36, price/quantity18 and bps6. Floating-point prices, exponent notation,
noncanonical strings, overscale amounts and old Probe/TradeRecord state cannot
be imported. The only state origin is `bootstrap`; there is no deserializer or
legacy adoption method. Shared signal predicates are reused by the existing
Probe and this rehearsal. Indicator calculations use explicit derived binary64
views; all 59 EMA periods are compared against the existing shared candle
history, including tiny prices and retained-history boundaries. Derived values
never return to the monetary ledger.

## One complete decision

1. Bootstrap allocates all eight founders, debits their seed capital from the
   exact reserve, initializes the chosen real optimizer and common cohort, and
   records the running lifecycle in one candidate.
2. `prepare_protective` consumes a strictly later exact quote and stages every
   triggered stop/take close. It cannot advance candles, selection or the
   optimizer. An independently accepted protective candidate survives a later
   candle/selection preparation failure.
3. `prepare_decision` requires that same protective quote and an unconsumed
   decision cursor. A signal from a completed bar can fill only on a later
   observation, and expires at the completed bar's end plus one timeframe.
   Delayed delivery does not extend that deadline. Source gaps and revisions
   fail; duplicate unchanged candles do not recreate signals.
4. At a common deadline, remaining positions liquidate with exact exit costs
   before fitness is calculated. Complete evaluation results enter the real
   GA, DE, PSO or CMA implementation. Retirement returns each exact residual to
   reserve; all eight births debit it; typed lineage and the next ordered cohort
   are bound in the same transition. PSO transfers each particle's momentum to
   its new identity before binding. CMA retains the actual ask vectors and
   distribution chain across subsequent tell/ask steps.

Candidates own sealed source/candidate state and detached solver/cohort forks.
Preparation failures, exhausted identity/name allocations and capacity errors
leave source state unchanged. Repeating a preparation from the same state and
inputs produces identical operations and evidence. Preparing or inspecting a
candidate does **not** establish that it committed or authorize another decision.
The C3 acknowledgment coordinator enforces that rule for this bounded path;
the application controller has not adopted it.

## Version 3 command envelope

The isolated contract admits `version: 3`, the exact v2 economic operation
schemas, and a required versioned `transition` with `before`, `after`, `evidence`
and `events`. Empty economic operation lists are allowed only in v3 so a pure
source/indicator update still advances a complete atomic checkpoint.

The evidence binds the owner/run/base revision, immutable profile/code/source
policy, explicit UTC and monotonic inputs, allocated identities/names, original
decimal quote/candle observations, action ordering, trade reasons and signal
cursors. The complete candidate contains reserve/accounts, retained closed and
open positions, genomes, active membership, pending intents, shared EMA history,
exact peak-equity/drawdown inputs, completed evaluation/selection results and
optimizer/cohort continuation evidence. Event identity is the immutable command
ID plus its ordered event index, scoped to its run. C3 materializes these events
in an atomic outbox with `run_id:command_id:event_index` identities and ordered
delivery acknowledgments; it is not yet connected to an application relay.

PostgreSQL locks the run and requires `before` to equal its stored state. It
independently recomputes exact entry/exit arithmetic and checks economic
projections against the resulting rows, source/reason/threshold evidence,
ownership, complete replacement and event binding. Operations, state, events,
revision and the original command response share one transaction. A rejected
late operation or inconsistent state must roll them all back. Version 1/2
fixture regressions remain separate; a v3 run cannot downgrade its command.

The optimizer encoder admits only reviewed types/fields and records ordered
maps, aliases, numeric array types and full private Python/NumPy RNG state.
Binary64 values use finite hex/byte representations rather than JSON floats.
It does not use pickle or execute serialization hooks. `cmaes` 0.13.1 allocates
an uninitialized fitness-history buffer: only slots written by completed tell
calls are read, and an explicit mask represents the others. The software and
codec versions are bound. SQL validates/stores this evidence; it does not
independently rerun EMA, fitness or selection mathematics or prove a profitable
strategy.

## Measured bounds and research still required

The experiment stops admitting further decisions after three replacements. It
retains at most 32 accounts and 64 positions, with no silent truncation. Every
whole envelope, including both states and all events, must also fit **262,144
bytes using PostgreSQL JSON spacing**. These limits are simultaneous ceilings;
64 retained positions are not a promise that every allowed solver/state fits.
Population replacement is never split to bypass the limit.

The local three-window fixture on October 2 produced these whole-envelope
maxima. Each completed all three windows and bound the next eight-member
cohort. Some valid genomes made no trades in individual windows; all eight
were still evaluated, and every window contained actual trades and nonzero
fitness results.

| Solver | Retained positions | Largest complete payload |
| --- | ---: | ---: |
| Genetic algorithm | 21 | 161,733 bytes |
| Differential evolution | 23 | 175,582 bytes |
| Particle swarm | 24 | 209,607 bytes |
| CMA-ES | 24 | 228,799 bytes |

A denser two-roundtrip-per-window CMA experiment exceeds the byte bound and
fails with the source unchanged. Four sequential local three-window runs used
about 55 MiB peak process RSS in one measurement; that includes the interpreter
and test harness and is not a worker hosting allowance. Python preparation and
local Docker SQL timings likewise are not production PostgREST latency claims.
An initial diagnostic that aggregated hundreds of complete journal requests
into one JSONB result exhausted the disposable database's 512 MiB allowance.
The rollback test now hashes rows before aggregating the small digests. This
does not solve production retention: paginated, byte-bounded journal/outbox
reads and a reviewed storage/retention policy remain required before cutover.

Deeper research remains necessary before enlarging or deploying this path:

- **Source precision and identity:** bound original numeric-lexeme decoding
  before vendor JSON becomes floats; decide explicit precision/overscale rules;
  retain immutable licensed dataset manifests and source hashes. The current
  `synthetic-exact-fixture-v1` label is an input policy, not authenticated vendor
  provenance or an independently verified immutable market dataset.
- **Capacity and checkpoint design:** measure worst-case full evidence,
  allocations, peak RSS and transaction/lease latency for every supported
  population and asset count. Evaluate a compact versioned checkpoint/event
  retention scheme before changing the cap; preserve one atomic replacement.
- **Numerical policy:** independently compare exact costs, partial quantities,
  decimal grid boundaries, float indicator/fitness views and trigger equality.
  This USD reference model is not token-atomic Solana settlement or a calibrated
  market-impact/fee/latency model.
- **Recovery:** the bounded C3 coordinator now retains acknowledgment installation
  and stable event delivery. Still required are schema compatibility/restoration, stale-process
  fencing, real transport behavior and the full legacy cutover (D/A3). An
  interrupted run retains its last engine checkpoint for reconciliation; it
  cannot use that checkpoint's old running status as permission to resume.
- **Performance claims:** obtain the representative historical corpus, realistic
  cost/latency sensitivity, held-out comparisons and multiple-testing controls
  already required by DATA/RES/FILL. Passing synthetic mechanics tests does not
  establish out-of-sample trading performance.

Run the ordinary worker tests with the isolated Python environment. The separate
real PostgreSQL suite requires the explicit opt-in described in
[the contract README](db-contract/README.md) and uses only its owned no-network
temporary container. No production migration belongs in this rehearsal.
