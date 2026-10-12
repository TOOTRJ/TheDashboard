# Independent exact economic transition proof — 2026-10-11

PAPER-COMPACT-03B3A validates the economic and allocated-identity portion of the
new provider-GA model after03B2 resolves its exact locked prior. It independently
replays original operations and compares complete balances, holdings and economic
history. The parent03B3 remains open for source, risk, assessment, optimizer and
selection/lineage semantics; this layer is not native command admission.

## Exact units and policy

Cash uses36 decimal places, price/quantity18 and basis-point settings6.
Canonical finite nonnegative decimal strings are bounded to1e36. PostgreSQL
numeric stores integer-valued units; div/mod implement explicit rounding without
using binary64 money or assuming division's selected decimal scale.
Buy prices and fees round up, sell prices and quantities down, and residual
budget remains cash. The reviewed USD-reference policy and complete execution
configuration must match. These are uncalibrated paper scenarios, not Solana
token-atomic settlement or a claim about real executable fills.
[PostgreSQL exact numeric types](https://www.postgresql.org/docs/17/datatype-numeric.html),
[integer quotient/remainder functions](https://www.postgresql.org/docs/17/functions-math.html).

Entry and exit evidence is recomputed from the supplied budget/reference/config.
Every price, quantity, notional, fee, debit/credit, residual and signed realized
P&L string must equal that result. Exits retain the exact original entry and
this profile permits observed fills only, not invented writeoffs.

## Economic and identity boundary

The wrapper invokes03B2 with the original wire and keeps its run/component locks.
It audits prior/following account and position shape, currency/configuration,
canonical amounts, member ownership, ordering, one position/member and retired
flags. It then replays all operations in their original order:

- Births debit reserve by exactly the configured seed and bind the child identity.
- Opens use one quarter of current cash in integer units, bind the reference
  price to observation/action evidence, debit the recomputed plan and retain
  the complete entry. Duplicate identities or second holdings fail.
- Closes require an existing owned holding, preserve its entry, credit exact
  proceeds less fees and increment the closed-trade count.
- Retirement requires an active liquidated account, records its PRE-transfer
  cash, moves that cash to reserve and retains its retired zero balance.
- Lifecycle operations bind the final status without inventing money effects.

After replay, reserve and all eight current accounts/positions must match the
checkpoint completely. Removed accounts must be retired with zero cash.
Sorted closed positions and ordered retired snapshots match history exactly.
Birth history matches actual following members; full-cohort generation changes,
newborn metrics, terminal cash, existing frozen terminal evidence and exact
trade-count increments are checked. Trade-count addition uses numeric to reject
the reserved-counter boundary without signed-bigint overflow/wrap.

Financial actions and indexed events preserve operation order, IDs and prices;
missing, duplicate, reordered and invented economic records fail. Full causal
signal/threshold/event-time and assessment meaning still require03B3B/C.

All allocated IDs must match actual births, opens or new risk-trip identities,
without duplicates or role overlap, and match the consumed input-ID prefix.
The private fixture catalog has a GLOBAL UUID primary key across identity kinds.
Prior identities require the correct owner/run/kind and a nonfuture birth
revision; their rows remain shared-locked through the transaction. An already
allocated historical UUID fails regardless of kind or owner.

The validator does not INSERT or RESERVE identities. An absence check does not
protect simultaneous new allocations in different runs. The future atomic
native writer must insert the unique IDs with the command and handle uniqueness/
unknown-commit failures through original-ID reconciliation. Privileged fixture
seeding is acceptance scaffolding, never a command/receipt protocol.

## Capturing a risk halt after cohort abort

The new risk fixture exposed a real research capture bug. The model can abort
the cohort before protective liquidation makes members terminal. Those members
have no scored terminal evaluation, but the old capture validator required a
scored frozen snapshot for every terminal member.

Capture now requires a frozen snapshot exactly when the cohort retains a
completed drawdown evaluation. Existing pre-abort scored snapshots remain
mandatory and unchanged through Stop; later unscored terminals cannot invent one.
Four dedicated regressions cover risk abort, deletion/invention of snapshots
and later Stop. No generator, scoring formula, native v5 policy or hosted row
is changed; the new owned state retains its original bytes.

## Actual acceptance and diagnostic measurements

Fifteen actual isolated PostgreSQL17.6 cases and21 Python format/capture/package
checks pass. Ninety-three complete commands cover dense windows/replacements,
fractional nonzero costs, terminal retirement, risk halt, pause/resume, restart
and Stop with all eight holdings. Another128 seeded entry/exit pairs compare
independent SQL arithmetic with Python integer plans, including fractional grids
and negative realized P&L.

Negative cases include well-hashed balance manipulation, noncanonical money,
changed budgets/fees/original entries, double closes, retirement with holdings,
missing/reordered/changed history and events, identity reuse or wrong scope/role/
future revision, counter exhaustion and mutated frozen terminal cash. The real
limited installer owns one new private table and nine functions. Only the
wrapper is a definer function; fixed pg_catalog search paths and auditor-only
execution are verified. Browser/service-role/relay and direct table/helper
access are denied. Owned fixtures have no network/ports/mounts/secrets and are
removed after acceptance. Successful and failed validation install no state.

Thirty warm full-wrapper samples per case include numeric/locked resolution,
both expanded states, economic replay and catalog checks. Source/image hashes
and exclusions are pinned in
[economic-transition-measurements.json](research/economic-transition-measurements.json).

| Request | Original bytes | p50 milliseconds | p95 milliseconds | Maximum milliseconds |
| --- | ---: | ---: | ---: | ---: |
| Bootstrap |128,635 |172.470 |179.307 |179.540 |
| Quote |9,192 |152.696 |160.377 |163.712 |
| Replacement |149,024 |271.305 |283.386 |288.546 |
| Risk trip |140,391 |275.023 |286.770 |291.511 |
| Stop with holdings |106,885 |270.231 |284.560 |343.121 |

These exclude contended waits, full source/risk/assessment/optimizer/lineage
semantics, native journal/identity reservation/pin/projection effects, final
source/lease checks, COMMIT/WAL/TLS/relay and hosted tails. They establish no
production cadence, protective deadline, cost or continuous readiness.

## Remaining semantics and substantial research

03B3B next independently enforces original provider documents/epoch/sequence/
clocks/watermarks, candle contiguity/completion and EMA continuation/equality.
Bind operation eligibility to accepted protective/decision observations, causal
signals, thresholds, account/member drawdown and lifecycle/risk/recovery rules.
A deliberate boundary test changes source clocks while retaining valid economics;
this layer returns evidence without authority and the source layer must reject it.

03B3C must validate complete finalized/withheld assessment metrics/provenance,
early-terminal freezes, common-window completion, fitness/tie order, optimizer/
RNG/cohort continuation and actual selection/genotype/lineage sources. Then03
composes original journals/receipts, identity/component pins, projections, final
freshness and Stop resources with limited installer/catalog/reader/rollback
rehearsals.04 gates exact restoration;05 gates retention and hosted paper acceptance.

**Deep substantial research:** complete retained semantic/lock/COMMIT/WAL/TOAST
tails under nonzero-cost/held-position/risk/restart workloads; independent binary64
EMA/fitness interoperability; source age and receipt clock distributions; safe
immutable-validation reuse; cross-run uniqueness races and archive/original-ID
recovery. Preserve full RNG/source/frozen evidence until exact next-command
restoration is proven. Calibrate real costs and baselines separately.

Rollback is a reviewed code/docs revert. No hosted objects, grants, migrations,
Railway deployment/configuration, activation or live execution occur here.
Reproduce with the isolated hash-locked worker environment from the repo root:

    DASHBOARD_ISOLATED_POSTGRES_TESTS=1 DASHBOARD_ECONOMIC_TRANSITION_MEASURE=1 PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.postgres.test_economic_transition -v
    PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_provider_terminal_capture tests.test_partitioned_checkpoint tests.test_canonical_v5_package tests.test_forward_package -v
