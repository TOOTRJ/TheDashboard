# Parallel audit reconciliation — October 21, 2026

This report reconciles released work, prepared candidates and remaining audit
gates. The report itself is documentation; the combined prepared batch also
contains application, guard, fee-research and Helius-tooling changes plus the
review-only V12 archive. Root-observed batch results are identified below. PR111 is accepted on its exact documentation/review tree; the newer app/guard/fee/V12 composition is not claimed released.
[Machine record](PARALLEL-AUDIT-2026-10-21.json), [ordered backlog](TODO.md),
[paper/live readiness](MVP-READINESS.md).

## Released scope and corrected stale backlog entries

| Released work | Evidence and scope | Still open |
| --- | --- | --- |
| PR104: NEST-05A result identity/same-account reply ordering; original-v2 offline SQL value semantics; Next/config 16.4.2 | Merge `9403e14`, seven exact-head jobs in run38984914265, exact READY production and four read-only checks. The released tree contains `result-identity.ts` and the original-v2 defensive receipt. [Release](RELEASE-ACCEPTANCE-2026-10-16.md) | Nestegg formulas/calibration/cross-device write concurrency; native production-profile joins; broader QA |
| PR105: APP-01 sample/evaluator honesty; APP-02 truthful unavailable actions; APP-03 route/configuration validation | Merge `aa96f70`, seven exact-head jobs in run38987405700, exact READY production and four checks. [Release](APP-RELEASE-ACCEPTANCE-2026-10-16.md) | Actual historical evaluation; unavailable reports/wallet/billing features; full all-route browser coverage; NEST-07 export completion |
| PR106: two API tables' independent baseline, least-rights ACL and actual persistence | Merge `89c7979`, seven jobs in run39011604302; exact-project ACL and both POST/committed-SQL/owned-cleanup paths pass. [Acceptance](DB-04-API-BASELINE-ACCEPTANCE-2026-10-17.md) | This is the documented global integration API, not proof of owner-scoped RLS for all routes |
| PR108/109: worker foundations/B1 and Paper Dashboard controls | Accepted composed CI/source trees and production checks. PR107's failed standalone timeout remains preserved. [Receipt](RELEASE-CI-ACCEPTANCE-2026-10-18.md) | Full native authority, source/clock/reader joins, continuous worker operation |
| PR110: three-ordinary/four-SQL CI repair | Merge `02f9056`; eight exact-head jobs, identical tested tree and exact READY production/four checks; separate post-merge run39704739120 also passes eight. [Receipt](RELEASE-PR110-ACCEPTANCE-2026-10-21.md) | Those results do not accept a later documentation head or this prepared app batch |
| PR111: documentation and V11b review archive | Merge `1fcbf0c`, all eight jobs in run39708763776, tested/head/merge tree `aa7576ce…`, exact production `dpl_Gs8rhCg6i9PNgwS1pRXipUtdZ9hG` READY in 17 seconds and four read-only smokes/zero writes at 02:55:31.586Z. [Release](RELEASE-PR111-ACCEPTANCE-2026-10-21.md) | Later prepared app/guard/fee/V12 composition and every runtime/hosted gate remain unaccepted by this release |

TODO's NEST-05A and portable-v2 proof entries no longer say release pending.
APP-01/02/03 close their bounded honesty/validation scopes with the above
evidence; their unavailable product functions, empirical research and wider
acceptance gates are explicitly retained. Historical dated sections and original
immutable experiment/release JSON remain unchanged.

## Current parallel lanes

**B2:** V12 passes all 24 actual local native cases, zero errors/failures/skips,
in 65.258685 seconds. Independent row/key/wire, three-/six-pin closure and
duplicate-original/getter-snapshot race checks now pass. All 896 source hashes
and normal exact-owned cleanup pass; this is a private local laboratory, with
no hosted activity. Full admitted maxima, seven-pin Stop reserve/liveness,
production-owner design, current-base composition/CI and separate source adoption
remain open. [V12 exact evidence](B2-NATIVE-ACCEPTANCE-2026-10-21-V12.md).

**Final composed frontend and source gates:** root's clean Node 24.19.0
`env -i` suite passes **442/442 cases**, zero failures/cancellations/skips/todos,
in **22.70247275 seconds**, including the six new Helius Node cases. The earlier
436-case/23.215-second log and scope remain preserved separately. Whole-project
TypeScript passes with zero diagnostics; lint passes with zero errors and forty
warnings: eighteen set-state-in-effect, eighteen unused variables, three hook
dependencies and one immutability warning. The retained source-bound receipt
hash is in the machine record. App source is unchanged since the type/lint checks; the two new JavaScript paths separately pass scoped lint with zero diagnostics.

The application advisory gate remains **INCOMPLETE**. Preserve the first
120.077-second generic public scan failure. A separately retained bounded recheck
at 2026-10-22T03:03:48.828Z also fails both full and production npm audits with
public bulk-endpoint network timeouts, as classified by root. The package lock
is unchanged. Neither attempt provides findings counts or a clean current result;
no exception is extended. Earlier zero-production/five-exception observations
remain historical and do not substitute for this gate. The Helius runtime's
zero-finding audit uses a separate lock and does not close the application gate.

**Dashboard and browser guard:** history retains twenty focused passes. Guard v5
is composed across six files, with forty-five focused passes and a passing
original generic build. The owned wrapper preserves the original Next config.
The composed wrapped browser build is READY. Actual 1001-row trade-history browser
acceptance has not been performed; twenty offline SDK cases do not replace it.
All new app changes remain prepared and not yet accepted by exact-head CI/release.

**Nestegg:** the latest eleven goal-math cases pass after peer corrections,
alongside the earlier composed 436 and final 442-case passes. Root observes these actual compiled browser
flows using synthetic accounts and a loopback-only backend:

- Alice's ordinary $1,000,000 goal shows required saving of $1,010/month.
- Editing the goal to 1e12 through Portfolio and saving it to the fake backend
  shows Above calculation limit; required monthly saving, extra saving,
  contributions and growth show Unavailable. The current-pace value 332,955
  remains visible.
- Alice logout, then Bob login on the same hostname, shows only BOBPRIVATEPLAN1
  with 800,000, goal 1,000,000 and 80% progress. Growth-only saving correctly shows
  None needed. Alice's 1e12 goal/plan is not published in Bob's workspace.
- The inspected console has zero warning/error records.

The final browser receipt at 2026-10-22T02:58:07.646170Z is retained and
hash-bound in the machine record. Cleanup verifies the exact owned parent before
SIGTERM, normal exit 0, the owned copy absent and both owned listeners closed;
root also closes only the owned browser tab. No unrelated process/tab is stopped.

These are real rendered synthetic-loopback observations, not real Supabase
Auth/two-user RLS acceptance or exhaustive browser coverage. A minor UI issue
remains: the above-limit goal pace legend is visible although its line is absent.
The older 35-case proof retains its original scope. Household calendar/horizons,
real/nominal inflation, shared retirement/RMD ledger and probability calibration
remain separate open work. NEST-03 stays open until the remaining gates/release.

**Evolution/backtesting:** existing BASE-03B already compares reference GA and
random over the same twenty points and logical budget, shares initialization,
charges duplicates, separates exhaustive-cache computation and retains
fixed/cash/passive controls. The paired wrapper freezes seeds/budgets and source
identities. Seeds on one path are optimizer variation, not independent markets.
The operational solver's 460 legal integer EMA pairs and colony lifecycle need
their own matched-domain/budget adapter.

The all-opportunity fee component is now part of the prepared source composition.
Root's fresh locked CPython 3.12.14 environment passes **21/21 cases**—the fourteen
new opportunity cases and seven existing fee-provenance cases—in **0.598 seconds**,
zero errors/failures/skips. Pip check also passes. The retained receipt verifies
unchanged component/dependency/test source hashes, with no network/database calls;
its receipt and log digests are in the machine record. The earlier private
fourteen-case smoke remains dated preparation evidence. The component has no
runner integration or CI/release acceptance. It retains missing/refused/failed/
uncertain rows and full-population cost denominators, separates exact currencies
and included/sponsored/refund costs, and refuses unknown-as-zero or duplicate
source charging. Declared hashes do not authenticate/calibrate the population.
No genes are added.

**Helius MCP:** local project setup is accepted within the reviewed read scope.
The project server uses `/usr/bin/python3 -I -B` with the absolute Dashboard
launcher and exact working directory. `codex mcp get` confirms no inline key/
configuration environment and exactly six enabled client tools: `heliusWallet`,
`heliusAsset`, `heliusTransaction`, `heliusChain`, `heliusCompression` and
`expandResult`. The four account/write/streaming/knowledge groups remain excluded.
Upstream still registers ten tools; the allowlist is enforced by the project
client rather than removing those registrations.

Root's actual configured launcher initializes/lists the upstream catalog and
performs exactly one MCP read, `heliusChain.getAccountInfo`, for the public System
Program. The expected executable/owner result passes, writes and stderr are zero,
and the owned child closes. The separately accepted direct TLS mainnet health
request remains a distinct earlier read. The acceptance receipt at
2026-10-22T03:10:27.281Z is hash-bound in the machine record. The external SDK/launcher connection is accepted, but Helius tools are not
hot-loaded in this chat: root's current tool inventory contains none.

The pinned `helius-mcp@2.3.0` runtime has 193 installed packages in the ignored
project ssl runtime with owned Node 24/HOME/cache. Sixteen Python and six Node
checks, scoped lint and a mock catalog handshake pass; the mocked handshake
records zero outbound attempts. Its separate npm audit reports zero known
vulnerabilities, but upstream peer-range conflicts still produce ELSPROBLEMS.
Do not describe that dependency graph as clean or infer writing compatibility.
No application dependencies, shared configuration, other agent, signer or cloud
account are changed by this setup.

The reviewed preload suppresses the pinned package's known telemetry fetch
endpoint. It is not a general network or filesystem sandbox. The six-tool client
allowlist and shared-credential mode must remain in force; `expandResult` can
repeat a provider read and consume quota. No signing, mutations, funding, paid
upgrade or live-trading authority follows. [Full installation, exact pins and
limits](HELIUS-TOOLING.md).

**CI/release:** PR111 is merged as
`1fcbf0c84f4fcb5f8b06095e498df1a3965adea6` at 2026-10-22T02:48:43Z. All eight
jobs in run39708763776 pass. Head `764d00a`, tested checkout `ebe02c7` and actual merge
share tree `aa7576cebc2608122324a8a8bba0d14d1f0c498c`, confirmed by scoped fetch.
The browser verifies exact Vercel project/team; production
`dpl_Gs8rhCg6i9PNgwS1pRXipUtdZ9hG` is READY in 17 seconds from the merge/current alias.
Four read-only smokes pass with zero writes at 02:55:31.586Z. This releases the
PR111 documentation/V11b archive, not the later prepared composition above.
[Full source/target/smoke evidence](RELEASE-PR111-ACCEPTANCE-2026-10-21.md).

## Credential and hosted boundary

The user confirms all three historically deployed provider keys are Dashboard-only.
Manual browser-side key creation and private handoff remain pending; the ignored
mode-0600 destination is prepared. Never put new keys in chat, tracked files,
shared settings, Vercel browser variables or the worker unnecessarily. Identify
each Dashboard consumer, coordinate replacement, verify access/usage and retire
old keys. This documentation neither creates nor rotates credentials.

Root's exact-target read-only Supabase receipt at
`2026-10-22T02:28:31.993654Z` checks `The Dashboard` / `fxpxsciltakyypunglzr`,
organization `cqfnnaunmupdyobkyqfo`. All 32 original finite principals from sixteen
issuance records have matching normalized original names/OIDs, registry-revoked,
NOLOGIN and expired state, with **zero sessions and zero reused names**. The
prior local assertion failure was text/type normalization, not an observed
target or identity change. No SQL writes, new issuance, password rotation or
session termination follows from this check. The sanitized original receipt is
retained privately and hash-bound in the machine record; no credential or
password-verifier content is copied.

The replacement Railway project token verifies the pinned project/workspace/
production environment/service. Current configuration has nineteen variable
names: eleven system and eight explicit settings, configured closed with both
dotenv-disable flags; there is no current runtime provider/database/native key
name. The old `cf05895d…` deployment reports SUCCESS in metadata. These facts
do not prove incident exposure absent or fresh in-container image/mode/TLS/Auth.
Review usage, complete scoped key response and verify platform recovery before
any closed-hosted redeployment/acceptance. The Railway operator token belongs to
its private project helper file, not Vercel or worker runtime; an unused `.env`
duplicate is not a runtime credential. Preserve the other coding agent's
credentials, tools, processes and project throughout. [Incident assessment](RAILWAY-INCIDENT-ASSESSMENT-2026-10-21.md).

## Dependencies and parallel work

| Work | Can proceed in parallel now | Required predecessor for final acceptance |
| --- | --- | --- |
| Scoped credential response | Manual provider handoff; usage and consumer inventory | Original target/dependency proof before coordinated updates; platform restoration before hosted reacceptance |
| B2 | Independent admitted maxima/reserve analysis and review | Complete boundary proof → production owner design → current-base composition/actual CI → separate adoption |
| Dashboard and Nestegg | Disjoint UI/math tests, peer review and synthetic browser preparation | Focused/composed/types/lint and partial synthetic browser pass; trade browser/legend/advisory gates → exact-head CI/release |
| Research | Pure scenario review, family registry, availability/split contract, solver adapter and EMA-prefix design | Freeze choices and clocks → authorized representative data/calibration → prespecified forward experiments/untouched holdout |
| Restoration/retention/readers | Versioned design and offline fixtures after contract freeze | Durable native receipts/source/clock joins before restore proof, reader authority or pruning |
| Hosted paper | Runbooks, fault and budget plans | Complete closed package, incident response and migration/rollback → fresh closed image/TLS/Auth → finite faults/windows → sustained operation |

Cloud mutations and releases remain serialized even when code/research preparation
is parallel. Preview currently shares production Supabase values; a preview is
not a write-safe isolated database. Keep the worker closed and respect the approved
$20/month pilot design ceiling without changing billing or account-wide policy.

Deep substantial research remains necessary for representative point-in-time
history/gaps/revisions/survivorship; all-outcome execution costs and refunds;
liquidity/notional and timestamped currency conversion; complete experiment-family
choices/exclusions/holdout access; EMA initialization sensitivity; serial
dependence/effective trials/statistical-method eligibility; household calendar,
benefit/tax/RMD and probability assumptions; and measured target-host storage,
query/lock/WAL, quota and cost tails. The [empirical follow-up](EMPIRICAL-EVALUATION-FOLLOWUP-2026-10-16.md)
and [capacity research](WORKER-CAPACITY-RETENTION-RESEARCH-2026-10-17.md) retain
their detailed questions and source limitations.

The original finite owner hour is accepted. Continuous paper still requires the
new complete package and sustained evidence. Real trading additionally requires
empirical promotion, custody/independent risk, token-atomic transactions, durable
submission uncertainty and wallet/P&L reconciliation, shadow/fault proof and
separate explicit funding/signing/activation authorization.
