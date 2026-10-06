# Evolutionary trading bot MVP readiness

Reviewed 2026-10-06 against the current implementation and [TODO.md](TODO.md).
This distinguishes tested components, deployed application behavior, and the
integration work still required. Completing engine tests is not a hosted bot
release or evidence of a profitable strategy.

## Current position

| Area | Status and practical meaning |
|---|---|
| Core evolutionary engine | Phase 2's 12 entries are complete. Funding, indicator/time handling, population continuity, fitness, risk controls and optimizer constraints have regression coverage. |
| Small strategy | `ema_baseline_v1` evolves two parameters: fast and slow EMA periods. Asset, timeframe and other controls stay fixed; RSI/volume signal filters are disabled. All candidates share 61 completed warmup bars. |
| Research evaluator | Synthetic replay, a twenty-pair exhaustive grid, cash/passive/fixed-EMA/random controls, and an equal-budget reference GA are implemented. Training-only selection and fresh chronological holdout accounts are tested. Representative historical research and calibrated fills remain open. |
| Exact paper controller | An opt-in provider-bound v5 controller, command repository, lease fencing and event outbox work in offline/local database rehearsals. They are not yet selected by the production service. |
| Database / HTTP | The inert transport pins the exact Dashboard host/schema/RPCs. Local real HTTP faults and PostgREST acceptance exercise original-ID reconciliation and transaction semantics. The hosted project runs PostgREST 14.5; `vn_durability` is not exposed or deployed. Existing public legacy writers remain in service code. |
| Dashboard | Next.js 16.3.8 is deployed. Selected-run targeting and complete bounded legacy history are repaired locally and released. Fresh versioned projections, detail pagination and two-owner end-to-end acceptance remain. |
| Worker / live execution | The Python worker is unhosted. Runtime modes are simulation/paper. The Jupiter V2 helper requests quotes without a taker; it cannot sign or execute a swap. |

The next implementation focus is DB-03A2D3, followed by DB-03A3's complete verified
cutover. Detailed transport evidence lives in
[COMMAND-HTTP-CONTRACT.md](services/vonneumann/COMMAND-HTTP-CONTRACT.md).

## First hosted paper MVP: ordered critical path

The proposed first MVP is a **supervised bounded pilot**, with eight candidates,
one SOL/USD reference market, two EMA genes, one evaluation window and at most
one replacement. It has no restart/resume capability. Current conservative caps
are 3,601 accepted quotes, 3,600 quote seconds and 4,000 total commands; the
terminal stop has reserved capacity. These caps do not establish a one-second
production cadence. A stop retains positions and reports them; it does not
invent liquidation proceeds.

| Order | Remaining work | Todo / acceptance |
|---|---|---|
| 1 | Complete the authoritative database and browser contract | DB-03A2D3: atomic command writes plus versioned run/probe/trade/sample/evaluation projections; compatible historical reads; archive rules; durable event relay with ACK/replay/deduplication; replacement of every startup/status/risk/control writer. Review exact-object grants and inheritance, with no second economic writer. |
| 2 | Rehearse and apply the full forward cutover | DB-03A3: two owners plus anonymous access, late failures, locks, lost replies, stale workers and rolling overlap; reviewed migration and rollback; fresh exact-project verification. Prove hosted schema/JWT/transaction-end behavior with independent committed readback before selecting the new service path. |
| 3 | Establish an operationally valid market cadence | DB-03A2C2D2D2A, DATA-01/02, HOST-03/04: measure actual source age, receipt deferrals, provider/DB/preparation/relay tails, remaining lease headroom, CPU/memory and organization-wide quotas. Choose polling/renewal bounds from measurements. Do not raise freshness limits or silently relabel stale data to make the pilot run. |
| 4 | Make crashes and restarts fail visibly and safely | DB-03/SVC-02/HOST-01: fence stale owners, retain unresolved original commands and holdings, reconcile interrupted runs and expose their state in the dashboard. For this bounded MVP, stop/interruption is acceptable; automatic continuation of an old strategy state is a separate acceptance gate. |
| 5 | Package and connect the hosted worker | HOST-02 through HOST-06, SEC-03, DEPLOY-01: reproducible non-root Linux image, one Uvicorn process, measured startup/drain/resource bounds, private worker secrets, exact authenticated HTTPS/WSS origins, readiness/alerts, and demonstrated deploy/rollback behavior. Establish preview/test database isolation before integration writes. Reverify the selected new hosting service/account/region and obtain its explicit cost authorization. |
| 6 | Verify the complete operator flow | UI-01/02/03/05 and ACCEPT gates: browser login → exact selected run → start/pause/stop → accepted commands → committed account/trade/equity history → reconnect/replay; two users cannot read or control one another's runs. Display source age, assumed fill costs, interruption and retained positions honestly. |
| 7 | Run and review the bounded hosted paper pilot | HOST-07: observe real feeds and mocked monetary execution, resource use, failures, quota/cost and shutdown. Retain reproducible evidence and rollback criteria. Engineering correctness does not establish profitability. |

For an **unattended continuously evolving paper MVP**, add compact/versioned
multi-window checkpoint commands (DB-03A2C2D2D3), supported larger profiles and
journal retention, then long-duration/load and restart acceptance. Current dense
PSO/CMA repeated-window states exceed the existing command budget in demonstrated
cases. A single-window pilot must not be presented as unlimited evolution.
Automatic checkpoint restoration also needs complete source/clock/RNG/account
rebinding and independent restart proof; it is not accomplished by storing one
balance or restarting a process.

## Real trading MVP: additional work after paper acceptance

Real trading is a separate implementation and authorization phase, not an
additional environment variable. Start with one allowlisted asset pair and a
small, explicitly promoted fixed champion. Keep evolving candidate accounts in
paper mode until a separate promotion policy is validated.

| Order | Additional gate | Implementation and evidence |
|---|---|---|
| 1 | LIVE-01: empirical strategy and promotion policy | Representative retained data with source/availability evidence, realistic costs and slippage, controls, prespecified multiple seeds and untouched holdouts. Define small exposure and promotion/rejection rules. Do not select a live champion from synthetic fitness or repeated holdout tuning. |
| 2 | LIVE-02: custody and independent risk admission | Dedicated narrowly funded wallet, reviewed signer/key management, exact owner/asset allowlist, per-order/total/daily-loss limits, kill switch and operator controls. Define what halting entries means for existing positions and protective exits during outages. Separate later explicit funding/signing/activation authorization is required. |
| 3 | LIVE-03: token and transaction validation | Integer atomic quantities, independently verified mint decimals and token programs, native SOL/WSOL handling, USDC versus USD accounting, transfer-fee/extensions/authority risks, route/slippage bounds, transaction programs/accounts/recipient/spend validation and fee/tip/rent budgets before signing. |
| 4 | LIVE-04: execution with durable uncertainty handling | Implement a durable intent/signature state machine across prepare, sign, submit, unknown, confirmed/finalized, failed and expired states. Reconcile the same original transaction after timeout or restart before deciding whether any new order is permissible. A fresh quote/order is not proof that a prior transaction failed. |
| 5 | LIVE-05: actual fills and wallet reconciliation | Reconcile transaction and balance evidence, fees/priority fees/tips/rent/refunds, token flows, realized/unrealized P&L and startup holdings. Reject unknown or mismatched balances. Paper USD reference balances and declared percentage costs cannot serve as the real wallet ledger. |
| 6 | LIVE-06: fault drills and a separately approved canary | Mock signing/execution contracts, outages, expiry/finality, duplicate/replayed responses, restarts and old/new workers; shadow mode with no signing; independent security review; then an explicitly authorized minimal-capital canary with confirmed records and rollback/entry-halt criteria. Expand only after evidence supports it. |
| 7 | LIVE-07: measure execution infrastructure before expanding | Benchmark data arrival, decision, quote, submission, landing and confirmed fill tails/costs. Compare current Helius/RPC plus managed Jupiter routing with self-managed build/Sender/Jito/streaming only for a measured bottleneck. The current candle strategy has not established an HFT requirement. |

Current official Jupiter guidance recommends its managed Swap V2
[`/order` + signing + `/execute`](https://developers.jup.ag/docs/swap/order-and-execute)
path. This is the proposed first execution integration; it still requires our
own transaction validation, durable reconciliation and actual wallet accounting.
Without `taker`, `/order` supplies a quote, not a transaction. Jupiter's
`totalInputAmount`/`totalOutputAmount` represent wallet flows and must not be
confused with route-result amounts.
[Solana confirmation guidance](https://solana.com/developers/cookbook/transactions/confirmation)
reinforces the need to distinguish submission, confirmation and expiration.
No live transaction has been performed in this work.

## Research to pull forward before dependent implementation

- **Database/auth:** custom worker role versus broad service-role key, role
  inheritance, hosted gateway JWT/schema-cache/transaction settings, exact
  privilege retirement, independent commit evidence and rollback compatibility.
- **Data/timing:** Jupiter block-reference/fork/same-block semantics; Birdeye
  publication/revision/outlier and historical availability semantics; USD/USDC
  parity; clock rebinding after interruption; actual source-age and lease tails.
- **Capacity/recovery:** compact checkpoint expansion correctness, retention and
  pagination, worst-case dense optimizer payload/memory/latency, long-run event
  delivery, restore versus safely interrupted operation.
- **Strategy/fills:** representative history, multiple-test bias, equal unique
  and logical search budgets, cost-sensitive objectives, liquidity/size/slippage,
  out-of-sample performance and adverse execution conditions.
- **Operations/execution:** shared provider entitlements and monthly cost,
  host/region measurements, signer threat model, token extensions, transaction
  expiry/finality/reconciliation, independent review and canary metrics.

Jupiter [quotas are organization-wide](https://developers.jup.ag/docs/portal/rate-limits);
separate API keys do not create separate account capacity. Coordinate budgets
with other applications without changing their keys or configuration.

More genes, extra assets, additional optimizers, a replacement optimization
library, broader Nestegg work and cosmetic dashboard work are outside the
critical path for this narrow paper MVP. Keep the two-gene baseline until the
whole system and empirical comparisons justify adding complexity.

## DB-03A2D3A checkpoint — 2026-10-05

Atomic projection/terminal/evaluation history, owner-scoped bounded pages, durable
sequenced relay/ACK/replay and retained-holdings archive now have an isolated SQL
and actual v5/local PostgREST rehearsal. Exact display/collection/relay adapters
remain inert. The unused bulk-delete browser helper is removed. [Contract](services/vonneumann/READ-PROJECTION-CONTRACT.md).
This completes D3A, not the D3 parent or a hosted paper MVP. Next are D3B reviewed
production DDL/legacy privilege and classification cutover, D3C one service
writer/read/operator flow, and DB-03A3 application acceptance. Timing, packaging,
credentials, safe interruption, preview isolation and hosted pilot gates retain
the order above. Real trading still requires LIVE-01 through LIVE-07 separately.

## DB-03A2D3B1 checkpoint — 2026-10-05

The isolated legacy write-retirement/classification slice passes 25 PostgreSQL
cases, including exact table/column/maintenance denial, two-owner history,
inherited/SET ROLE paths, preserved defaults/unrelated objects and old-worker
overlap. Actual v5 bootstrap/projections work without writing retired legacy
tables. [Contract](services/vonneumann/LEGACY-WRITE-RETIREMENT.md). Hosted
`postgres` lacks grant options on the fixture's auth dependencies, so the next
critical step is **D3B2**, a v5-only production DDL/object/credential package with
actual installer acceptance and durable legacy drain/reconciliation/archive
evidence. B1 does not complete D3B or apply a migration. D3C service/browser
selection and DB-03A3 full cutover follow; the paper worker remains unhosted.
Dedicated Dashboard login and all exact targets were reverified on 2026-10-06.
B1 release requires exact-source/merge READY deployments and read-only smokes;
immutable release evidence belongs in its PR. Real trading gates are unchanged.

## DB-03A2D3B2A checkpoint — 2026-10-06

The installer/Auth dependency now has an executable hosted-like proof: an actual
NOSUPERUSER postgres login installs the laboratory through a narrow Auth identity
bridge and existing REFERENCES privilege, without changing managed Auth grants.
All four v5 bootstraps and owner-scoped eight-probe reads pass; denial, preservation,
late rollback and FK lock timeout are included in 17 PostgreSQL cases.
[Scope, evidence and credential research](services/vonneumann/INSTALLER-BOUNDARY.md).

This closes B2A only. Canonical v5-only production DDL/manifest, separate economic/
relay credentials, durable legacy reconciliation/archive evidence and additive
rollback remain B2 work. D3C service/browser selection and A3 hosted full-cutover
acceptance still follow. The paper worker remains unhosted. PR45 is the verified
preceding source release; immutable B2A deployment evidence belongs in its PR.
