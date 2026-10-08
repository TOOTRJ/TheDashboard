# Evolutionary trading bot MVP readiness

Reviewed 2026-10-07 against the current implementation and [TODO.md](TODO.md).
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
| Database / transports | Canonical fresh v5 SQL and native SCRAM owner/run authentication are proved offline. The inert HTTP adapter and local PostgREST tests retain reconciliation/transaction evidence; the bounded native async SQL transport now proves real TLS/SCRAM controller/relay and commit recovery offline. Read-only hosted metadata and a bounded TLS-only preflight are complete; actual selected-host IPv6/project-CA/hostname TLS now passes; SSL enforcement and client inventory are complete; managed installer/issuer/history rollback passes, and the closed production migration is applied and independently verified. Actual finite native pair issuance/authentication, owner/run/capability denial and held-session/fresh-login revocation pass on Railway; credentials are removed and ordinary closed startup restored. Provider/relay/lease/tail/interruption acceptance remains. The hosted project runs PostgREST 14.5; fresh v5 SQL is installed with closed admission at epoch0 and fifteen migration versions. All 11,149 user-rejected old bot rows are now deleted after reviewed guarded cleanup and rollback rehearsal; fifteen migration versions, schema and Auth remain. Only curated vn_read is exposed, with two owned Auth/empty-directory and anonymous/private-schema denials verified. The existing owner sees the selected closed paper interface and empty history; nonempty v5/control acceptance remains. Existing public legacy writers remain in service code and must not become a second active writer. |
| Dashboard | Next.js 16.3.8 is deployed. Selected-run targeting and complete bounded legacy history are repaired and released. D3C now prepares the explicitly selected actual v5 view with exact balances/trade/evaluation details, legacy diagnostics, original-ID controls/archive and durable replay. Local browser/SQL owner flow passes. The production paper interface is selected and the existing owner sees zero legacy runs, empty new history and disabled controls while the worker stays closed. Actual nonempty/control/two-user acceptance remains A3. |
| Worker / live execution | The Python worker is hosted on Railway in closed mode. No paper run is active. The Jupiter V2 helper requests quotes without a taker; it cannot sign or execute a swap. |

The complete forward package/legacy evidence/additive retirement and D3C service/browser
preparation are tested. A non-root pinned amd64 image is built and closed-mode canaries
pass. The exact Railway service is deployed in closed mode, with its production-scoped token,
single US West replica, HTTPS denial, resource limits and actual IPv6/CA/hostname TLS verified.
The $20/month pilot ceiling is approved. Client inventory is resolved; exact-database
SSL enforcement and post-reboot checks pass. Actual managed installer, issuer and
production/history wrapper rollback rehearsals pass after three measured repairs.
Closed application/committed verification, actual finite native sessions and curated exposure now pass.
Hosted real-token Auth/CORS checks pass, and the existing owner sees the selected closed paper page.
The actual Birdeye null-multiplier defect is repaired; hosted warmup and one price capture pass,
but the finite provider assessment stops on remaining quota 9 below its required margin of 12.
Next is actual Jupiter plan/shared-use clarification, further source/lease/relay/resource timing,
then hosted nonempty operator/ownership/failure acceptance before the bounded pilot.
[Exact setup and remaining gates](RAILWAY-SETUP.md). Detailed transport evidence lives in [NATIVE-SQL-TRANSPORT.md](services/vonneumann/NATIVE-SQL-TRANSPORT.md);
The [closed cutover procedure](SUPABASE-CUTOVER.md) records the snapshot, original-outcome
reconciliation and managed profile/Auth/deparser corrections.
actual hosted facts, the credential/rollback plan and revised Railway IPv6 hosting
recommendation live in [HOSTED-NATIVE-PREFLIGHT.md](services/vonneumann/HOSTED-NATIVE-PREFLIGHT.md).

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
| 1 | Resolve shared quotas and establish an operationally valid cadence | DATA-01D, DB-03A2C2D2D2A, HOST-03/04: verify the actual Jupiter plan/shared allowance and Birdeye entitlements/credit cost; finish finite source-age/receipt, remote DB/preparation/relay/lease and CPU/memory measurements. Prove renewal headroom and choose bounds from measurements. The short provider probe stopped on its quota guard; it establishes compatibility and feasibility only. |
| 2 | Prepare and accept the one active worker path | DB-03A2D3C/DB-03A3: finite owner/run credentials, exact native writer/relay binding, full body/grant equality, compatible reads and explicit reviewed admission. Retire every competing legacy startup/status/risk/control writer. Closed schema/TLS/native/Auth/curated/empty-browser acceptance is complete; nonempty hosted operation remains. |
| 3 | Prove security and safe interruption under deployment faults | DB-03/SVC-02, HOST-02 through HOST-06, SEC-03, DEPLOY-01: stale-worker fencing, locks, late/lost replies, overlapping releases, timeout/cancellation and SIGTERM/SIGKILL. Retain and reconcile original commands and holdings, verify readiness/drain and actual resource/cost limits. Use an explicitly isolated test plan; Vercel previews share the production database and are not test isolation. Automatic resume is a separate gate. |
| 4 | Verify the complete operator and ownership flow | UI/ACCEPT gates: browser login → exact selected run → start/pause/stop → accepted commands → committed balance/trade/equity history → reconnect/replay. Two users cannot read/control one another's runs. Display source age, assumed costs, interruption and retained holdings honestly. Static demo market/connection labels are corrected; an empty closed view does not prove active trading. |
| 5 | Run and review the bounded hosted paper pilot | HOST-07: eight candidates, two EMA genes, one market/window and at most one replacement; real feeds with simulated monetary execution. Record source age, resources, quota/cost, failures and shutdown. Review evidence before continuous operation or strategy-quality claims. |


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


## DB-03A2D3B2B checkpoint — 2026-10-06

The canonical fresh v5 component is extracted and rehearsed under the actual
limited installer: v5-only public admission, 72-function dependency/hash/signature/
capability manifest, 18 fresh economic/projection tables and separate inert
economic/relay SQL permissions. Five offline checks and 31 real PostgreSQL cases
cover all four solver seed/protect/decide paths, controller recovery, owner reads,
relay/archive, exact authority and atomic rollback/locks.
[Contract and limits](services/vonneumann/CANONICAL-V5-PACKAGE.md).

Next is actual separate credential/gateway/owner/run authorization and transport,
then durable legacy reconciliation/archive evidence and complete forward-package
composition/rollback. B2/D3 stay open. D3C selects one service authority and wires
browser history/control/archive/replay; A3 proves/applies the complete hosted
cutover. Production timing, safe interruption, preview isolation and hosting still
gate paper MVP launch. The worker remains unhosted; live trading gates are unchanged.


## DB-03A2D3B2C1 checkpoint — 2026-10-06

Separate native economic/relay logins now have an offline authentication and
owner/run authorization proof. Five ordinary artifact checks and twenty real
TLS/SCRAM database cases cover identity/scope, credential lifecycle, revocation,
rollback and actual v5 bootstrap/relay/projections. The hash-pinned canonical v5
component remains unchanged. [Research, contract and limits](services/vonneumann/NATIVE-SESSION-AUTH.md).

This closes C1 only. B2C2 must add the bounded actual async SQL transport with
project/CA pins, transaction/commit ownership, cancellation/lost replies and
original-ID reconciliation. Hosted TLS/native authentication and credentials
remain unconfigured. Durable legacy evidence, complete forward-package and
post-acknowledgment rollback, D3C/A3, real timing/quotas, safe interruption, preview
isolation and hosting still precede the bounded paper pilot. Continuous evolution
still needs compact checkpoints and long-duration acceptance; live trading gates
remain unchanged. No user setup is required for the next offline transport work.
