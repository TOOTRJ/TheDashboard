# Fresh GA active model and finalized assessment boundary

PAPER-COMPACT-02B1, 2026-10-08. This implements a fresh, credential-free,
**offline** GA model, `ga-active-model-research-v1`. It is not a native v6
command, a provider adapter, a durable checkpoint decoder or production admission.
The v3/v4/v5 implementations and their original limits are unchanged.

The model uses the existing reviewed two-EMA genotype, eight candidates, common
one-hour windows, deterministic GA search, exact cash and reference execution.
It copies the lifecycle rules into a separate module to version new state and
assessment behavior without changing old runs. A regression trace compares every
operation and current balance/holding/member, EMA, risk, cohort and complete
optimizer evidence with v4 through its original three-window limit.

## Active state and history

`GAState` has no public JSON constructor. It owns an in-process solver/cohort
seal, returns detached views/forks and cannot load an old run or checkpoint.
Its active JSON holds exactly eight current accounts/members, at most eight open
positions, reserve, frozen early-terminal snapshots, pending decisions, risk,
source sequence, indicators, cohort and full optimizer evidence. Early-terminal
accounts remain present with their retired flag until the common deadline.
Closed positions and nonmember retired accounts leave **this new active model**
at the candidate boundary; their immutable per-transition history is emitted
in the same complete candidate, together with births, original genes/member
snapshots, allocated identities, selection metadata and finalized assessments.
No production history is deleted or converted.

`SimulationLedger` is a mandatory offline oracle. It holds growing identity and
history indexes outside active state, requires the exact owner/run/prior state,
reexecutes preparation from the original owned seal, and separately replays the
exact cash and holding operations. Missing/altered assessment evidence, a lost
open position, corrupt cash, historical ID reuse, stale state or foreign scope
fail before any simulated acceptance state/history changes. Preparing a candidate
cannot advance the ledger or the original solver. Original-wire replay after
advance preserves the current ledger rather than reinstalling an older state.

This oracle is **not** independently enforced durable uniqueness, SQL model/source
validation, a receipt or a capability. It is not concurrent, bounded retained
history, or process-restorable storage. Its indexes, stored wires and history
intentionally grow. Production removal of historical ID scans still depends on
PAPER-COMPACT-03's independent transactional checks. Python private seals are a
research ownership convention, never a security boundary for untrusted clients.

## Scoring evidence

`ga-finalized-assessment-research-v1` rows are captured in original cohort order:

- On normal completion, required final liquidations run first. Each close applies
  its exact exit plan/cash credit, increments closed-trade count and updates peak
  and historical drawdown. Immediately after `cohort.complete`, before optimizer
  selection or account retirement, all eight final metrics are captured.
- An early protective death captures cash, peak, exact drawdown ratio, closed
  count, original ROI/fitness and source cursor after its own final close and
  before cash transfers to reserve. That snapshot remains frozen until the common
  deadline; finalization changes neither its score nor capture identity/time.
- Pause, Stop or risk interruption emits eight unscored records. ROI/fitness and
  the ROI ratio are explicitly withheld even for an already terminal candidate.
  Cash/drawdown/count observations remain auditable. An unfinished holding is
  labeled `has_open_position`, with `terminal_cash: null`; cash balance is not
  represented as a completed liquidation. An interrupted batch is never told to
  the optimizer. Resume uses a later source and an explicit restart clone.

Every row binds owner/run, original probe/evaluation/iteration, member order,
generation, capture and finalization revisions/times, common-window times and
synthetic source cursor range. It records seed/cash/peak, exact ROI and drawdown
ratios, exact binary64 views supplied to the optimizer, final closed-trade count,
measurement basis, fitness-policy version/formula/weight/provisional status,
evaluation policy and complete exact execution assumptions. The provisional
`ROI - 2 * historical drawdown` objective is unchanged and checked against its
pinned policy. It has not been calibrated for profitability. Existing records
with missing provenance remain missing; no fitness inversion or rescoring occurs.

## Explicit bounds

The whole candidate includes full active before/after, operations, actions,
events, supplied input evidence and that transition's history. Both immutable
wire and conservatively spaced JSON must fit 262,144 bytes; candidates cannot be
split. Fanout is at most eight open holdings, eight newly closed holdings, eight
retirements, eight assessments, 17 allocated identities and 33 operations per
candidate. The eight current members preserve one-position-per-member admission.

The separate counter policy pins signed-bigint revision/source/candle/trade/
search/mutation/recovery limits, rejects before wrapping, and reserves revision
9,223,372,036,854,775,807 for Stop only. Stop consumes no quote/candle/mutation/
trade increment and keeps every unresolved holding. Generations retain the
existing name allocator's signed-32-bit maximum, 2,147,483,647; timestamps retain
the exact observation's 2^40 bound. No claim is made that every bigint value is a
safe JavaScript number: native cross-language serialization remains a reviewed
format decision in 02B2/03. Boundary tests use explicitly trusted artificial
fixtures; they are not checkpoint restoration or provider freshness evidence.

## Acceptance and measured limits

Two real fresh-model traces run 32 completed sparse/dense synthetic windows,
including normal warmup and 755 accepted candidates per trace. Every boundary
keeps eight current accounts, zero to eight open positions and exact conservation
of 1,000 USD including entry-plan debits held in open positions. History grows to
256 retired accounts and 256 finalized assessments per trace. Dense history has
512 closed positions and 776 allocated identities, exceeding both the old
64-position and 100-identity bounds while current state remains bounded.

See [reproducible size artifact](research/ga-active-model-capacity.json) for final
values: maximum active bytes48,983/48,999, final active bytes44,817/44,833 and
maximum complete candidate bytes149,776/168,484 for sparse/dense respectively.
Measurements cover prepared full candidate JSON, not network transport,
SQL/storage/index/TOAST overhead, retained history/oracle memory, polling
throughput, hosting costs, restoration or economic performance. The source is
synthetic observations; real Jupiter/provider document identity, source-clock
freshness and native source admission are **not** part of this format yet.

From the repository root, with the project-isolated Python environment:

```sh
PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_ga_active_model tests.test_active_checkpoint tests.test_checkpoint_reference tests.test_canonical_v5_package tests.test_forward_package -v
PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m tests.measure_ga_active_model --measure
```

All scenarios deny network access. Focused coverage includes final fee/risk/count
changes, early-terminal deadline freezing and interrupted withholding, retained
open holdings on Stop, pause/resume restart without tell, old/new scope/type
refusal, deterministic rejected preparation, complete history tamper refusal,
historical ID reuse, conservative complete-payload failure and reserved Stop at
revision/source overflow boundaries. Unchanged canonical v5/forward packages are
checked with this slice. Final release evidence is kept in the PR.
The final validation passes50 distinct cases:16 fresh model, one runtime boundary,
20 active-format, six checkpoint reference and seven unchanged package checks.
The main49-case batch and the isolated runtime boundary case both pass; Python
parsing and diff checks also pass. No production database/native integration
test, provider freshness test or restored-process acceptance is claimed.

## Remaining ordered work and rollback

1. **PAPER-COMPACT-02B2:** bind this fresh model to the typed component format and
   real provider evidence; specify exact source/current-ledger reconciliation,
   canonical bigint encoding, component invalidation/complete-command limits and
   reserved native Stop budgets. The 02A capture remains v5-only, not a decoder
   for this fresh model. Keep old records/run configuration pinned.
2. **PAPER-COMPACT-03:** independently enforce identities, lineage, closed-fill and
   finalized-assessment completeness, exact economics and full source evidence
   under the run lock; publish history and checkpoint atomically, pin dependencies,
   support original-ID replay/readback and final freshness/lease checks. Prepare
   old/new readers, manifests, forward migration and evidence-preserving rollback.
3. **04/05:** exact GA-only restoration, retention/pins/receipt lookup, then closed
   hosted acceptance and a finite multiple-window paper pilot. The in-process
   fork and synthetic acceptance grant no permission to activate a worker.

**More deep substantial research:** determine the minimal GA/cohort/RNG component
set only after proving full next-command equivalence; measure invalidation across
representative provider activity and real SQL workload; study objective/cost
sensitivity, inactivity bias and comparisons across policy versions using held-out
common windows. Preserve the full optimizer block until that evidence exists.

This slice has no production import, command route, configuration migration,
Supabase writes/grants, Railway changes, retention deletion, live wallet operation
or activation. Rollback is a reviewed code/docs revert; existing v5 data and the
closed worker remain intact. Native/database adoption needs its own prepared
migration and rollback acceptance against the exact Dashboard targets.
