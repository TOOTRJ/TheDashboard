# Exact risk and lifecycle transitions

DB-03A2C2C adds a separately admitted **version 4** lifecycle rehearsal. It uses
fresh, flat, eight-member two-gene EMA runs with the existing four solvers and
exact decimal execution. Version 3 keeps its original wire meaning. Neither
version is wired into the active application controller, and the SQL contract
remains an isolated acceptance fixture outside `supabase/migrations`.

## Risk policy and ordering

The immutable configuration records `exact-common-cohort-lifecycle-v1`, an
account-loss limit in canonical integer basis points (default 3,000), a fixed
2,000-basis-point member drawdown limit, and `max_lifespan_seconds: 0`. The EMA
baseline forbids an age limit; active lifespan termination and broader profiles
remain future work.

Colony equity is reserve plus owned account cash plus exact reference-marked
open holdings. The denominator stays the original initial capital. Recycled
funding, prior generations and recovery never reset it. A loss limit is inclusive:
`equity * 10000 <= initial_capital * (10000 - loss_bps)`. Recovery requires a
strictly higher equity value. Hypothetical liquidation fees are not subtracted
from marks; actual entry/exit costs enter equity when their operations occur.

The protective phase checks the new aggregate mark before processing protective
closes, then checks after each cost-bearing operation. It retains the **first**
threshold crossing and its trip identity even if a subsequent operation improves
equity. This conservative v4 ordering is explicit: a quote that simultaneously
trips colony loss and kills individual members aborts the cohort first; those
members still liquidate/retire but are not newly scored. The older controller's
final aggregate check after the protective pass is not claimed to be identical.

A trip clears entry intents, aborts the current cohort without optimizer
selection, and records its original baseline, first trip equity/time/identity,
latest observed equity/time and recovery audit. Protection, eligible exits and
member deaths remain available while halted. No later entry, distribution or
funding is admitted during that trip. Rebound alone never clears it.

Member termination uses **current** peak-to-equity drawdown, not lifetime maximum
drawdown. Positions close first, exact terminal cash is recorded, and retirement
returns that cash to reserve once. The original ordered eight-member cohort
keeps every frozen terminal result until its common deadline, including when all
eight members die. Only remaining live accounts are retired at replacement;
terminal cash and closed trades cannot be reclaimed or counted twice.

## Controls and interrupted windows

| Control | Permitted source | Result |
| --- | --- | --- |
| Pause | Running | Abort without selection; retain positions; suspend all quote/protective work |
| Resume | Paused | Clear old intents; retain the aborted audit; require a fresh funded evaluation restart |
| Stop | Running, paused or risk-halted | Abort without selection; retain holdings and any risk latch; terminal for this run |
| Recover | Risk-halted with its current trip ID | Require surviving members, matching accepted quote, current complete history and strictly recovered equity; retain the interrupted audit for restart |

Controls preserve original account ownership and never manufacture liquidation
or label retained positions safe. Times cannot regress behind the last source or
control. Stop must be admitted before the coordinator's permanent drain; if drain
already closed admission, no stop write or stopped state is invented.

Resume/recovery do not score the interrupted window. A subsequent independently
accepted later quote starts a complete fresh-funding restart from the original
bound phenotypes. All eight children get fresh IDs and seed cash, reset trades
and fitness, and a new search epoch. Their explicit lineage version 2
`restart_clone` binds the interrupted iteration and ordered original source with
`clone_source` and `asset_template` roles. The flat parent-ID view retains that
source ID, without claiming it was selected from completed fitness. Prior
version-1 ancestry remains unchanged and older command versions reject restart
lineage.

Restart preflight must establish complete funding before optimizer initialization
or selection. Insufficient funds reject the entire candidate without changing its
source; they do not fabricate an account-loss trip. Warmup and stale-history
backfill can advance as history-only candidates until 61 contiguous bars and a
current completed candle are available. Rejecting every incomplete warmup
candidate would otherwise deadlock resume. The fresh restarted cohort remains
warming until a subsequent ready observation; interrupted or same-frame signals
cannot open positions. An already active old window may complete on its first
valid deadline quote even when history has become stale, but its newly funded
cohort waits in warming until current completed history is available.

## Atomic validation and acknowledgments

The state includes an explicit cohort mirror, complete typed optimizer/RNG
continuation, lifecycle/risk audit and terminal-member metadata. Python and SQL
validate the v4 contract explicitly rather than relabeling it as v3. Sequential
operation checks recompute economic rows and risk boundaries. Cohort mirrors are
bound to encoded optimizer cohort evidence, including member order, phenotypes,
terminal results and abort state. Python also binds newly recorded ROI/fitness
views to the exact reclaimed cash and drawdown. SQL checks economic rows and
consistent frozen evidence; it does not independently recompute the binary64
fitness formula, EMA arithmetic, or mathematically prove optimizer selection.

The existing coordinator admits fresh v3 or v4 runs and pins every submitted
candidate to that acknowledged run's version and immutable configuration. It
installs only the matching receipt, emits the transactional outbox events in
order, and reconciles uncertain replies using the original command ID. A lost
reply does not grant a fresh lease: readback can prove a commit, but further work
requires explicit successful heartbeat renewal. Recovery after a delayed reply
still requires an independently accepted later quote before restart economics.

Whole-command byte, ID, account and position bounds remain enforced without
truncation or batch splitting. The three-generation cap blocks further population
replacement; protective and stop/control preparation still work at that cap,
subject to the complete payload and retained-state bounds.

## Remaining acceptance and deeper research

- **Production integration is still open.** No historical checkpoint decoder,
  active-controller replacement, live provider binding, production relay,
  migration or hosted worker is introduced. Do not treat a preserved `running`
  checkpoint as authority to resume an interrupted process.
- **Synthetic freshness is not provider freshness.** Current quote binding,
  contiguous candles and post-control source ordering do not establish wall-time
  availability or freshness after an awaited acknowledgment. Research and test
  provider numeric lexemes, provenance manifests, wall/monotonic expiry,
  post-acknowledgment checks and restart watermarks before transport cutover.
- **Preparation failure requires an operational halt.** If trip-ID allocation,
  payload capacity or any protective preparation fails, the pure planner leaves
  its source unchanged. The future runtime must close ordinary admission rather
  than reuse an older unconsumed observation. Stateless planner purity is not a
  replacement for that operational failure latch.
- **Protection and delivery latency need measurement.** The one-transition outbox
  gate bounds ownership/backlog but a slow relay can delay a protective pass.
  Research bounded decoupling, receiver deduplication retention, journal/outbox
  archival and actual database lease/transaction timing before changing it.
- **Capacity and numerical research remain.** Exercise supported worst-case
  optimizer histories, decimal sizes, repeated interruption growth, memory/body
  bounds and realistic execution costs before expanding beyond this profile.
  Fixed zero lifespan does not satisfy age-based termination acceptance.
- **Economic evidence remains separate.** These tests establish deterministic
  mechanics and persistence rules, not profitability. Representative historical
  datasets, cost-aware holdouts and multiple-testing research remain on the TODO.
