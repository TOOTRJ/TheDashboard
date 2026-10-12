# Independent causal trading and risk replay

Reviewed 2026-10-11. PAPER-COMPACT-03B3B2 completes03B3B's offline source/causal/
risk milestone for the separately versioned GA provider model. It adds no native
admission, durable effects, checkpoint decoder or runtime trading authority.

## Ordered independent replay

The private validator first binds the original canonical request and locked
prior through03B2, independently checks exact economics/identities through03B3A
and source/indicators through03B3B1, then independently replays the causal model.
It does not call the Python preparer or rely on the client's following hash to
decide whether the financially consistent action is actually allowed.

The replay holds detached account/member/holding maps and consumes each expected
operation/action in original order. New position/trip/cohort UUIDs must consume
the supplied identity prefix at the exact model point. Every requested operation
must be consumed; a missing required operation or an extra action fails.

- Bootstrap must create the complete ordered founder batch, original risk
  baseline, generation zero, warming cohort and zero/empty decision controls.
- Protective quotes require a running or risk-halted state. The account observes
  the current mark first, then each live original member is checked in order.
  Stop-loss closes at or below97% of the original reference entry, take-profit
  at or above107%. Exact integer price units distinguish threshold edges.
- Current member equity is cash plus held quantity times the reference mark.
  Peak equity and the historical maximum drawdown are recomputed after every
  relevant ordered mark/fill, using reduced integer ratios. Retirement never
  fabricates a zero mark: terminal cash freezes before transfer to reserve.
- At the20% member drawdown boundary, the replay requires any remaining death
  close and exact terminal timestamp/cash, then ordered retirement. Retained and
  retired member cursor/pending/trade-count/peak/drawdown/terminal evidence must
  match the derived point, including the pre-transfer retired snapshot.
- Account loss compares all reserve, accounts and holdings against the original
  configured equity baseline. The first inclusive breach latches the trip at
  that exact stage, clears pending entries, aborts the cohort and requires the
  risk-halt operation. Later fills cannot automatically unlatch it. Costs during
  liquidation can trip risk before the remaining valid liquidations finish.
- Ordinary decisions consume the accepted frame only once. An old pending
  crossing can execute only on a strictly later quote within its candle window,
  with the correct flat/held identity and risk permission. Expired intents are
  discarded. New crossing intents derive from the exact previous/current EMA
  ratios and existing holdings after prior eligible fills/protection.
- Warming, replacement and interrupted restart use the model's completed-history
  eligibility and ordered common-window phase/deadline. Replacement/restart
  liquidate before retirement/birth; latched risk prevents the next batch.
  Complete funding, generation capacity, ordered births and new member controls
  are required. Restart increments the search epoch and applies the later-signal
  barrier; it cannot silently tell the interrupted batch.
- Pause/resume/Stop/recover enforce their previous lifecycle status. Controls
  clear pending intents and bind exact control/signal times. Recovery must
  acknowledge the current trip, use the accepted quote/current completed candle,
  have survivors and exceed the original account-loss boundary. The baseline
  remains unchanged, and recovery count/time are independently derived.

Stop uses no new provider frame/history, performs no liquidation and retains
existing holdings. It cannot invent a new risk observation, realized trade or
fresh score. Final server age/lease/resource checks remain native composition.

## What remains outside this layer

This layer derives the lifecycle and cohort phase, using the locked prior's
window identity/deadline.03B3C must independently derive the complete common-
window/cohort structure and assessments, frozen/withheld metrics, fitness,
optimizer graph/RNG continuation, selection ties, genotype controls and lineage.
The replay checks financial and risk evidence in retired members; it does not
yet claim complete optimizer/assessment authority. The original evidence is kept.

The source contract still trusts worker-parsed records/manifests within a declared
clock epoch. A response digest is not external provider authentication, and a
loaded checkpoint never proves clock compatibility or grants a renewed lease.
The next native integration must compose all semantic checks under one verified
prior lock, insert globally unique identities atomically, journal original IDs
and receipts, retain/pin dependencies, project history and recheck final source/
lease freshness.04 restoration and05 retention/closed hosted acceptance remain.

## Actual acceptance

Thirteen actual isolated PostgreSQL17 cases pass. The corpus covers150 complete
owned commands: two traded windows, fractional execution costs, scored/unscored
terminal retirement, risk halt, pause/resume/restart, recovery with eight held
positions, exact stop/take-profit threshold sides, expired signals and Stop with
eight holdings. Every successful/rejected validation leaves durable rows unchanged.

Adversarial cases first pass source/economic validation, then fail causal checks
for changed pending signals/cursors/peak/drawdown, risk observation/baseline/
trip/recovery fields, wrong protective reasons, mismatched trip acknowledgement,
below-boundary recovery, rehashed duplicate decisions, terminal timing, retired
metrics and altered lifecycle policy. This distinguishes causal enforcement from
a hash/shape failure. Required operation/action/allocation order is checked.

A limited synthetic LOGIN installer with no superuser/create-role/create-database/
inherit/bypass authority owns fourteen private functions. All pin pg_catalog
search paths and revoke PUBLIC execution. Only the final definer wrapper is
granted to the fixture auditor; browser/authenticated/service-role/relay,
direct-helper and private table access fail. No new tables or writes are added.
Owned pinned-image fixtures use no network, ports, mounts or application secrets
and are removed after the tests.

## Measurements and further research

[The measurement artifact](research/causal-risk-measurements.json) binds all five
SQL sources and the actual PostgreSQL image. Ten warm full-wrapper samples per
case use a wire variable and generic plans against the unchanged fixture prior.
The current offline composition resolves the full dependencies three times;
that repeated work is included, rather than describing a small request as cheap
validation. Warm p95 is989.980ms for bootstrap,469.678ms for a quote,805.821ms for
replacement,842.613ms for risk trip,577.215ms for recovery and814.777ms for held
Stop. These are not deployed command-rate or trading-latency guarantees.

Excluded work includes assessment/optimizer/RNG/lineage semantics, contended
waiting, native journal/identity/pin/projection effects, final source/lease
checks, COMMIT/WAL/TLS/relay and hosted tails. The SQL SHA256 is
e3f19debaa251f73fe5b0f4ff1528a5693753a3c4ae710762d336acd10ffb4b0.

1. Compose one verified resolution with all pure validators and catalog locks.
   Measure complete validation/contended locks/COMMIT/WAL/TOAST before selecting
   cadence, retention or claiming that the hosted worker fits the budget.
2. Research server-owned, version-bound immutable validation reuse. No client
   flag or unchanged digest alone may authorize bypassing current scope, pins,
   native policy, prior lock or final freshness/lease checks.
3. Prove independent frozen/aborted/final metric timing, exact binary64 fitness,
   MT19937/search-stream continuation, stable selection and actual ancestry.
   Keep full graph/RNG/alias evidence until exact next-wire restoration passes.
4. Research source-byte retention/parser trust and explicit compatible-clock
   handoff after worker restart. Epoch labels and loaded state grant no authority.
5. Continue empirical cost/source-age and baseline/holdout/multi-seed research.
   Short common windows and synthetic crossing fixtures prove implementation
   behavior; they do not establish sufficient trading evidence or profitability.

No hosted migration/schema/grant/native package, Railway deployment/variables/
capabilities, paid data call, archive deletion, billing or live execution change.
The worker remains closed. Rollback is a reviewed code/docs revert; no hosted
research objects exist. The user-owned colonies migration remains excluded.
