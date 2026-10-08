# Evolutionary trading bot MVP readiness

Reviewed 2026-10-08 against the current implementation and [TODO.md](TODO.md).
This distinguishes tested components, deployed application behavior, and the
integration work still required. Completing engine tests is not a hosted bot
release or evidence of a profitable strategy.

Latest hosted checkpoint 2026-10-08: PR71 is merged and its exact production
source/author/project/team/alias and four smokes passed. A separately issued
thirty-price native controller assessment now passes at revision34, including
original lost-reply reconciliation, relay and reserved stop. Nonempty owner
history and anonymous/other-owner denials pass. The new intended-owner pilot
starts once through the dashboard, but fails after two prices at revision5;
first replacement and the hour remain unaccepted. Nine events are fully relayed,
eight cash accounts remain unchanged and there are no positions. Retained status
shows a generic controller failure and no native transport phase; a specific
provider/freshness cause is not established.

Ordinary closed Railway restoration25f88091-979d-485d-bb29-7ffc7c1fb49c is SUCCESS;
original variables are restored and the original pair is revoked/NOLOGIN. Late
interruption is correctly denied after its two-hour write expiry; recovery_until
permits readback only. The original committed run still needs explicit maintenance
reconciliation. Fixed provider/acquisition/controller/service failure labels and
a hash-bound cash-only administrator operation are prepared and tested, awaiting
release and actual managed rollback/apply. Dedicated file-backed Vercel sign-in
is needed before that release. No worker is active and no wallet operation has
been performed. HOST-07 remains open.
[Fresh evidence](supabase/audits/2026-10-08-fresh-native-controller-and-pilot.json),
[ordered next work](TODO.md), [activation/rollback](PAPER-MVP-ACTIVATION.md).

## Current position

| Area | Status and practical meaning |
|---|---|
| Core evolutionary engine | Phase 2's 12 entries are complete. Funding, indicator/time handling, population continuity, fitness, risk controls and optimizer constraints have regression coverage. |
| Small strategy | `ema_baseline_v1` evolves two parameters: fast and slow EMA periods. Asset, timeframe and other controls stay fixed; RSI/volume signal filters are disabled. All candidates share 61 completed warmup bars. |
| Research evaluator | Synthetic replay, a twenty-pair exhaustive grid, cash/passive/fixed-EMA/random controls, and an equal-budget reference GA are implemented. Training-only selection and fresh chronological holdout accounts are tested. Representative historical research and calibrated fills remain open. |
| Exact paper controller | The selected native-v5 path now passes the actual thirty-price hosted controller, lost-reply, relay and reserved-stop assessment. The real owner's start commits through the browser. Its latest hour attempt fails after two prices; fixed provider/stage diagnostics are prepared before another assessment. The worker is currently closed. |
| Database / transports | Fifteen migrations install98 functions/26 tables; full body/catalog/grant verification passes. SSL, Railway IPv6/project-CA/hostname TLS/SCRAM/channel binding and finite owner/run/capability checks pass. Curated vn_read provides owner-only nonempty history; anonymous/private/other-owner access is denied. Release admission is OPEN at epoch1, while every issued native pair is revoked/NOLOGIN and runtime is closed. All11,149 user-rejected old rows are deleted; Auth is retained. One expired committed run awaits guarded cash-only maintenance reconciliation. No old competing writer is selected. |
| Dashboard | Next.js16.3.8 and the selected paper-v5 interface are deployed. The real owner starts once and sees eight candidates and committed history. Worker failures are distinguished from the last committed run status; closed mode disables controls and retains history. Complete pinned reads poll independently from status. Final first-replacement/trade/evaluation/replay browser acceptance remains open. |
| Worker / live execution | Railway's exact Dashboard service is restored to ordinary closed startup with original variables and revoked pilot credentials. No paper process is running; an expired database run requires explicit reconciliation. The Jupiter V2 helper remains quote-only and cannot sign or execute a swap. |

The exact source, project/service/owner identities, US West replica, HTTPS,
resource limits and outbound IPv6/TLS are verified. The $20/month pilot ceiling
is approved. Actual installer/issuer rollback, closed migration, finite native
sessions/revocation, owner reads/Auth/CORS,61-bar warmup and paced provider/native
controller checks pass. These finite successes do not establish the one-hour
pilot, interruption with positions, unattended restoration, statistical timing
tails or economic performance. The latest failed run is preserved, runtime is
closed, and original finite write authority is not extended. Further release
needs dedicated Vercel sign-in; then apply the reviewed original maintenance
reconciliation and diagnose the provider/controller failure before a new hour.
[Current evidence](supabase/audits/2026-10-08-fresh-native-controller-and-pilot.json),
[setup](RAILWAY-SETUP.md), [native transport](services/vonneumann/NATIVE-SQL-TRANSPORT.md),
[closed cutover](SUPABASE-CUTOVER.md), [hosted preflight](services/vonneumann/HOSTED-NATIVE-PREFLIGHT.md).

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
| 1 | Release fixed diagnostics and reconcile the original expired run | PAPER-FAILURE-EVIDENCE1/PAPER-EXPIRED-MAINT1: dedicated Dashboard Vercel sign-in, exact-target/source review, actual original-input rollback rehearsal and once-only cash-only interruption. Prove unchanged economics/checkpoint and candidate outbox/relay progress; verify the terminal owner projection without fabricating an event or ACK. |
| 2 | Diagnose and repair the observed controller/provider failure | The fresh thirty-price native assessment passes; the actual owner hour still fails after two prices. Capture fixed acquisition/controller/provider labels, repair the established cause and repeat one finite assessment under unchanged source/receipt/lease bounds. Do not infer a provider cause from null SQL phases. |
| 3 | Complete workload/security/interrupt evidence for the bounded profile | DATA-01E, D2D2A, HOST-02…06/A3: retain finite source/quota/DB/relay/resource measurements, owner isolation and original-ID settlement. Complete unresolved fault/overlap/outage exposure checks. Continuous quota/tail/restart readiness remains separate. |
| 4 | Verify complete operator and ownership flow at the final window | Actual login/start/eight-candidate/nonempty history works. Verify complete first-replacement balance/trade/evaluation history, reconnect/replay and owner isolation at the final committed revision. Costs remain uncalibrated; stop retains holdings and restart requires reconciliation. |
| 5 | Accept the supervised one-hour pilot, then close/review | HOST-07: eight candidates, two EMA genes, one SOL/USD reference window, at most one replacement, real feeds/simulated economics and reserved stop. Record resource/quota/failure evidence, restore closed runtime and revoke the finite pair. No profitability or live-trading claim follows from this mechanical acceptance. |

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
