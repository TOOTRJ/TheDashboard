# Forward recorded-provider paper runtime v3 — review proposal, 2026-10-12

The next implementation should be a new recorded-provider paper profile joined
to the proven operator, native admission, restoration and retained evidence.
Original portable v2 is still a synthetic research profile. The existing closed
real-data worker uses the v5 provider lifecycle and single-window limits. Neither
may become v3 by changing a version/source label, disabling a validator or
casting imported dictionaries into owned state. This proposal changes no existing
model, SQL, API, worker, startup, deployment or provider configuration.

`research/runtime_profile_v3_contract.py` freezes an **inert proposal schema**,
not an implemented model/native format. It validates only canonical configuration
bytes and explicit caller identifiers. Its status is
`review_only_not_implemented`; all implementation digests and admission budgets
are null, all authority fields false, and `refuse_runtime_use` always refuses.
There is no environment switch that turns this module into a worker. A reviewed
implementation/package must replace these unresolved bindings through a new
acceptance step; caller-supplied JSON cannot assert that acceptance.

## Current source and primary documentation findings

Read `JUPITER-TOOLING.md` and the pinned official integration skill first, then
the current [complete Jupiter index](https://developers.jup.ag/docs/llms.txt).
The older skill's universal-key/volume-quota claims are not the current contract.
The authoritative versioned YAML URL remains listed, but the browser research
tool could not parse its YAML content type in this review. Current HTML API
reference and endpoint pages were inspected instead; do not report a fresh YAML
hash or full OpenAPI conformance from this review.

Price V3 uses `https://api.jup.ag/price/v3`, with mint IDs and USD reference prices.
The current documentation explains unreliable-mint omission and `blockId` recency.
Its reviewed interface has no historical candle range selector. The `createdAt`
sample is not a price observation receipt. A faster request, reliable-price
heuristics, token decimals or 24-hour change does not establish a fresh executable
fill. Preserve actual receipt/source evidence and refuse missing mint data.
[Price overview](https://developers.jup.ag/docs/price),
[current Price reference](https://developers.jup.ag/docs/api-reference/price).

Jupiter documents organization-wide 60-second sliding limits, path-specific
execute capacity and reset headers that open one oldest-request slot rather than
refill a window. API-key product permissions can constrain allowed paths. Keep
the existing private Dashboard key external to configuration bytes; this task
does not inspect or change keys, quota, team rules or billing. The user's
single-application statement removes another known application under TheOrder,
but does not prove observed continuous capacity or remove portal/header
discrepancies. [Rate-limit semantics](https://developers.jup.ag/docs/portal/rate-limits),
[key permissions](https://developers.jup.ag/docs/portal/api-keys).

Birdeye's current OHLCV V3 page specifies minute candles, USD/raw mode, up to
5,000 returned records, omitted empty candles without padding, and now consistently
describes `outlier=false` as filtering outliers. The proposal pins that flag
explicitly. This is documentation evidence, not a measured response guarantee;
the current adapter intentionally omits the flag. Package availability does not
establish this account's entitlement, target-window completeness, causal
publication time or retention rights. Keep those gates open.
[OHLCV V3](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-v3-ohlcv),
[accessibility table](https://data.birdeye.so/docs/guides/data-accessibility-by-packages).

Solana `getBlockTime` returns an estimated block production time based on ledger
vote timestamps and can lack a time. It is not the provider's publication time
or a price/finality guarantee. The current resolver verifies mainnet genesis and
uses that estimate but does not retain original RPC response bytes. The v3
acquisition corpus must retain the original bounded RPC request/response and
operator endpoint binding if it relies on that estimate.
[Solana getBlockTime](https://solana.com/docs/rpc/http/getblocktime).

## Existing pieces to reuse through explicit new boundaries

| Existing source | Proven role | Required v3 join |
| --- | --- | --- |
| `market/jupiter_feed.py`, `provider_evidence.py`, `exact_records.py` | Bounded Price V3 capture and exact decimal record parsing; no paper swap execution. | New recording contract must retain raw acquisition evidence, authenticated issuer, RPC linkage and explicit process epoch; do not treat `PriceCapture` as a provider-authentication receipt. |
| `market/solana_time.py` | Bounded HTTPS/mainnet check and estimated block time with conservative cache reuse. | Store original request/response bytes and receipt identity, preserve cache age, pin private endpoint identity without exposing URL credentials. |
| `market/birdeye_candles.py` | Explicit SOL/USD provider history path: 915 completed minutes, 61 completed15-minute warmup bars, no padding, complete ranges, revision/scaling checks. | Add explicitly filtered outlier parameters under a new request/document/parser policy. The existing sealed document accepts only its original omitted-flag request; do not strip a parameter or rewrite its request hash to reuse it. |
| `core/provider_acquisition.py`, provider owner/controller/runner and `server/paper_service.py` | Owned operations, original-ID retention, bounded acquisition, close/refuse states and reserved single-window v5 Stop path. | New operator must dispatch by an accepted v3 package/profile and explicit native capability; keep v5 code, bounds and original controls intact. |
| `research/provider_portable_ga_model.py`, thirteen-slot checkpoint, semantic/native laboratory and restoration | Exact GA continuation/history, two EMA genes, original identities, native pins and current-head restoration proof. | New typed v3 state/config/source/command/package. Reuse reviewed mathematical/fixed-class primitives through explicit interfaces, not synthetic-v2 header replacement. |
| Inert checkpoint inspector | Original v2 wire integrity, small honest view, exact amounts and publication gates. | New independently authenticated v3 projection/read schema and scope generation, separate version renderer; keep the v2 inspector's synthetic labels. |

No module in this proposal imports these runtime/provider/database paths. The
reuse map is implementation work still to do.

## Configuration and coherent version map

`paper-provider-runtime-profile-proposal-v3` is bounded at32,768 bytes and uses
canonical UTF-8 JSON. Unknown/missing fields, duplicate keys, raw numeric JSON,
boolean/integer aliases and unsupported values refuse. All counters are
canonical decimal strings. UUIDs are canonical explicit caller inputs. No
credential, wallet, RPC URL, signed transaction, provider response or model state
belongs in this configuration.

The full executable field allowlist is the standalone module's template:

| Section | Exact purpose and approved values |
| --- | --- |
| `scope` | Owner/run UUIDs. Their lexical validity is not authentication; bind separately to the private operator's verified actor. |
| `versions` | The reserved names below, all proposal-only. No v5/v2/native-lab name is interchangeable. |
| `market` | Solana mainnet genesis, fixed wrapped-SOL mint, `SOL/USD`, exact `USD` reference accounting; cash36/price18/quantity18 places; recorded-observation source with uncalibrated paper execution. No USD=USDC or on-chain-fill claim. |
| `search` | GA; only EMA fast3…12 and slow15…60; population8; 15-minute bars; one-hour common cohort; explicit uint64 search seed; account-loss bps1…10000; original integer period mutation and provisional fitness policies. Other economic/selection changes need their own review. |
| `epochs` | Distinct explicit market and acquisition UUIDs; within-process monotonic clocks; original receipts immutable; head-bound explicit rollover; quote sequence preserved. |
| `price` / `rpc` / `history` | Fixed read-only endpoint/method/query semantics, bounded raw bodies and external private auth policy. No client or provider request is created. |
| `provenance` | Authenticated scoped observer, immutable owner/run pins, exact secret-free request, real receipt clocks, independently reparsed derivation; hashes do not authenticate origins. |
| `freshness` | Proposed existing5-second receipt/acquisition,30-second source and2-second future bounds. They require new native tail acceptance and are not an activated cadence. |
| `retention` | Jupiter backtesting retention already user-approved. Birdeye rights and target-window coverage remain unverified. Pin-before-archive policy; no pruning capability. |
| `admission` | Closed; continuous quota unverified; cadence/command/hot/raw/archive budgets null; independent reserved Stop slot/bytes required; original uncertain command reconciled before advancement. |
| `implementation_bindings` | Worker/parser/kernel/lock/semantic/native/projection digests all null until independently accepted implementation exists. Caller claims are refused. |
| `authority` | Provider request, native admission, restoration, lease, hosting and live trading all false. |

Reserved future format names:

| Boundary | Proposed name |
| --- | --- |
| Configuration / model / full transition | `ga-provider-paper-config-v3`, `ga-provider-paper-model-v3`, `ga-provider-paper-transition-v3` |
| Assessment / source | `ga-provider-paper-assessment-v3`, `ga-provider-paper-source-v3` |
| Acquisition record / accepted observation / history manifest | `ga-provider-acquisition-record-v3`, `ga-provider-accepted-observation-v3`, `ga-provider-paper-history-manifest-v3` |
| Checkpoint / component / compact command | `ga-provider-paper-checkpoint-v3`, `ga-provider-paper-component-v3`, `ga-provider-paper-compact-command-v3` |
| Native receipt / readback / original-command lookup | `ga-provider-paper-native-receipt-v3`, `ga-provider-paper-readback-v3`, `ga-provider-paper-original-command-readback-v3` |
| Projection / epoch rollover | `ga-provider-paper-projection-v3`, `ga-provider-paper-epoch-rollover-v3` |

Freeze these names with the eventual complete schemas and implementation/package
hashes before native grants or deployment. A proposal-name reservation is not
an accepted wire version. Preserve original v2 model, checkpoint, assessment,
command, semantic and native digests unchanged.

## Acquisition records, origin trust and derivation

Implement a project-specific authenticated observation issuer, separate from
model commit authority. Proposed roles are `vn_v3_observer` (record submission
only), `vn_v3_native_worker` (scoped command/getter/head/identity capabilities)
and `vn_v3_read_owner` (owner-authenticated projections). None may directly write
private journal/component/identity/accepted-head tables. General browser,
service-role and relay access must not acquire native mutation authority. Pin
actual owners, ACLs, membership, source functions and database build/context in
the independently checked package manifest. These roles are design names; none
is created by this work.

Each acquisition record should have exactly this versioned data boundary:

```text
format, owner_id, run_id, market_epoch, acquisition_epoch, record_id,
issuer_binding_id, provider_family, endpoint_binding_id, method,
canonical_public_request_wire, request_sha256,
http_status, response_bytes, response_sha256, raw_response_ref,
request_started_wall_us, received_wall_us,
request_started_monotonic_us, received_monotonic_us,
safe_response_metadata, parser_policy_sha256
```

All IDs/counters/times/digests use explicit canonical types. The record ID is
reserved by the issuer before its one original acquisition, not regenerated after
a lost record-admission response. Record GET failures/missing data as acquisition
diagnostics, not market observations. Budget any new read attempt separately;
it has a new real receipt and never overwrites the original. Record admission
has its own original-ID lookup and no replacement/retry after uncertain writes.

Retain bounded raw response bytes once in an owner/run/version-scoped immutable
store; use131,072-byte Price,65,536-byte individual RPC and4,194,304-byte Birdeye
bounds initially, matching current adapter capacities. Keep raw blobs outside
the262,144-byte active checkpoint dependency budget. Scope pins make them part
of durable derivation/retention obligations rather than optional diagnostics.
Record only allowlisted non-secret response metadata: content type, status,
provider request ID if safely bounded, and typed quota headers where present.
Never store auth headers, cookies, full credential-bearing RPC URLs, private
environment values or token-bearing exception text. Use an operator-verified
endpoint binding ID for the private RPC connection.

The authenticated record issuer is trusted to report its actual HTTPS acquisition
and clocks. A body hash/signature authenticates retained consistency or that
issuer, not independently the provider's historical publication. SQL cannot
reconstruct a TLS connection from arbitrary caller JSON. Make this trust model
explicit; either accept the scoped issuer as an operator trust boundary or add
an independently controlled recorder/attestation service before claiming more.
Do not label historical downloads as observations the bot saw in the past.

The accepted observation packet should be strictly versioned with:

```text
format, owner_id, run_id, market_epoch, acquisition_epoch, observation_id,
price_record_id, genesis_record_id, block_time_record_id,
history_record_ids, normalized_manifest_sha256,
price_decimal, mint, denomination, block_ref, estimated_source_second,
history_range, source_policy_sha256, parser_package_sha256
```

Allow at most one Price record, one genesis proof bound to the current issuer
session/network, one block-time record and a bounded history-record list for the
fixed market. Exact document references and original raw bodies must be present
under the same scope. Independently reparse JSON with duplicate/nonfinite/type/
byte limits, derive the price/block reference and minute records, and prove
the normalized packet matches those bytes. Do not accept only a supplied hash
or worker-parsed normalized object as full independent derivation. A bootstrap
requires a complete history packet; protection requires the Price/RPC packet;
ordinary decisions use the exact accepted protective packet and required
completed-candle packet; controls request no new history merely to manufacture
a terminal checkpoint. Recovery binds the original acknowledged risk trip and
current accepted mark/history.

## History, clocks and explicit restart protocol

The v3 historical request is Price OHLCV V3, `type=1m`, `mode=range`, USD,
`chart_type=price`, `ui_amount_mode=raw`, `padding=false`, **`outlier=false`**.
Time fields are aligned integer seconds derived from actual acquisition UTC.
For startup, `end=floor((wall_us-5,000,000)/900,000,000)*900` and
`start=end-61*900`, admitting exactly915 complete minutes in `[start,end)`.
For the next completed bar, require `end=previous_end+900` and request
`start=previous_end-900`: exactly30 complete minutes, including one previously
consumed15-minute bar whose values must agree. Admit only the new contiguous
bar. If the actual cutoff is later than that next end, refuse ordinary live
advancement as a backlog; never manufacture missed live quotes/trades or fill
missing buckets.
Every returned row is validated before excluding older/forming boundary rows.
Equal duplicate rows may collapse; differing consumed OHLCV/scaling values
refuse. Reject scaled tokens except the existing explicit unscaled null/one
multiplier case. Aggregate each15 contiguous minutes into a completed bar;
retain61…64 bars and their immutable raw/manifest provenance. This matches the
current provider-specific path, not the legacy3660-minute generic warmup.

A completed-bar timestamp is not historical publication evidence. Record the
current retrieval identity and point-in-time availability separately. Revisions
to consumed overlap must close admission rather than silently recompute prior
EMA/results. Clarify actual outlier/filter behavior, coverage and source
publication/revision semantics with bounded recorded fixtures before the pilot.
Jupiter-only sampled closes are a later separately named dataset; they cannot
be labeled Birdeye OHLCV, real volume or historical executable quotes.

Use two epochs:

- `market_epoch` identifies the durable owner/run source series and persists
  through ordinary restart; quote sequence/block watermark and derived history
  remain monotonic under it.
- `acquisition_epoch` identifies one actual process/client/network-check context.
  Compare monotonic clocks only within this epoch. Retain old receipt epochs
  unchanged; do not apply a new process's lower monotonic value to them or assign
  a new receipt time to cached/archived data.

The versioned epoch-rollover command is a necessary new admission operation.
It binds the exact independently accepted current revision/manifest, new
issuer/process epoch, actual fresh clock samples and separately acquired current
lease/fence. It changes acquisition metadata only: preserve cash, holdings,
risk, generation, selection/RNG state, identities, source sequence/watermark,
pending decisions and prior history. Emit an explicit source-epoch event and
pin old/new provenance. Reject reused process epochs via a retained scoped epoch
ledger. This operation cannot create a lease or resume a paused/stopped run.

After loading, first reconcile any retained original command UUID/hash/wire and
holdings through authenticated getter/head checks. Load grants no authority.
A separately admitted operator may acquire a new fenced lease only after that
reconciliation. Roll over the process epoch explicitly, validate new mainnet
session evidence and current warmup/overlap, then admit a fresh protective frame.
Keep old quote receipts historical and ineligible for new actions. The next
decision expires or processes pending signals through the unchanged original
economics at the new actual observation time; do not clear them silently during
loading. Paused/risk states require their ordinary explicit controls/recovery;
stopped/failed checkpoints do not auto-restart. Stop remains available without
new market data and preserves holdings/balances/risk.

For the first v3 restart MVP, treat any process interruption of an active
evaluation as an explicit coverage gap. Preserve the checkpoint during loading
and rollover; the separately authorized operator then emits an explicit
gap/abort control before selection can proceed. Record a withheld interrupted
assessment with its original last-observed metrics and source provenance; do
not rescore finalized historical records. Preserve holdings and risk. Resume or
recover requires the ordinary acknowledged control and an accepted fresh mark,
then the reviewed restart policy can create a new common cohort/search epoch.
This is an explicit versioned lifecycle event, not automatic decoder reseeding.
For missing bars, request a bounded fresh915-minute current warmup and compare
all retained consumed overlap; refuse revisions/gaps. Historical catchup warms
indicators only, creating no retrospective trades or completed evaluations.
Future seamless window stitching requires a separate causal coverage proof.

Retain the current conservative receipt/source/future bounds as proposed inputs.
Reprove them through actual acquisition, independent parsing, native validation,
locks, projection, COMMIT guard, original getter and relay tails. Compare worker
UTC with independent server time; refuse regressions/future violations. Neither
API completion time nor `createdAt` may replace source time. Unchanged/repeated
marks, missing time and stale history do not create a new sequence or extend
an evaluation by resetting old clocks. Native recorded guard observation remains
distinct from final visible-instant or present freshness guarantees.

## Model, transport, projections and retention

Implement a new sealed v3 configuration/state/candidate module using the reviewed
GA mathematical primitives and the same two-gene/control policies. Its source
evidence comes from accepted v3 observation IDs and original raw derivation,
never from a synthetic-v2 state cast. Preserve the integer mutation/RNG operator,
common cohort windows, provisional fitness and USD-reference execution formulas
unless a separate change is reviewed. A controlled paired corpus can compare
v3 preparation against the original kernel's economic/selection/RNG behavior;
that experiment is not permission to submit relabeled v2 candidates.

Keep the thirteen active checkpoint slots: configuration, optimizer, cohort,
eight ordered genomes, source bars, EMA. New format/schema values explicitly
bind the accepted profile/package and dual-epoch source state. Preserve all
ordered mirrors/RNG cursors and exact amounts. Commands retain original UUID,
original prior revision/digest and complete operations/history/assessment/events
once; changed components are content-addressed without discarding continuation
evidence. Add separate bounded accepted-observation/raw dependency pins, not
unbounded raw blobs in the active wire. Begin with the existing196,608-byte
ordinary/262,144-byte Stop and active aggregate limits; reprove total expanded
wire/native effects before freezing any changed limit. Never split an oversized
economic transition or silently strip evidence.

Proposed private storage is `vn_paper_v3_private`; capability entrypoints and
owner-read projections are separate reviewed schemas. Journal command, component
updates,13 active pins, observation/raw pins, append-only economic/epoch IDs,
assessment/history, projection and events atomically under the owner/run lock.
Original-ID exact replay lookup precedes stale lease/revision/source admission;
changed UUID payloads conflict, and same-transaction provisional returns are not
committed receipts. Bind accepted semantic and source derivation heads to the
actual installed catalog/package. Complete independent source/lease checks after
all effects and at the reviewed recognized COMMIT boundary. Retain the current
laboratory's explicit guarantee limits: source-code testing alone does not prove
the production binary or final visible-instant freshness. A production context
requires its own build/session/guard acceptance.

The v3 projection must expose an owner/run/version/revision manifest and bounded
typed run/account/holding/assessment/evaluation/history records. Include exact
USD amounts, original source/availability provenance, incomplete/withheld status,
and separately observed original control/request receipts. Browser clients may
read their projections and request authorized durable controls; they may not
write the native journal or receive native credentials/RNG state. Use a new
reader namespace/version renderer; preserve v5 readers and original v2 inspector
labels. Scope publications by authenticated account/session generation plus
selected run/read generation, before paint and across late callbacks.

Dependency-safe retention must retain original command and receipt lookup,
13 active pins, every referenced accepted observation/raw request/response,
semantic/native/worker/parser/runtime manifests, economic/epoch identity ledgers
and complete history. Archive integrity is owner-bound; record eligibility,
intent and complete readback before removing hot evidence. No pruning is
implemented by the proposal. An unavailable archive is an explicit reconciliation
failure, never permission to invent state or retry under another command ID.

Set real cadence, finite run duration, command/unique-component/pin/raw/history/
index/TOAST/WAL/archive/Stop budgets from measured growth and p95/p99 tail behavior.
Include warmup, RPC, polling, errors and any future quote-calibration calls in
provider quota/credit budgets. Quota absence/custom headers are not automatically
zero or unlimited; require separately accepted operator evidence. Reserve Stop
and original-request reconciliation before ordinary admission. Keep the Railway
$20/month ceiling; it authorizes no account-wide billing/configuration change.

## Ordered implementation and acceptance map

| Gate | Concrete work and acceptance | Dependencies / parallel work |
| --- | --- | --- |
| R3-01 — Profile/source freeze | Review this proposal; pin new version schemas, source/clock/parameter choices, trust/issuer model and runtime hashes. Resolve Birdeye rights/target coverage, explicit outlier semantics, effective quota and source/processing tails. | Can proceed with offline model/reader fixtures and primary research in parallel. Real recording/retention waits on its own approved plan. |
| R3-02A — Recorded acquisition boundary | New bounded recorder, secret-free request/RPC evidence, exact original IDs, raw store/pins, independently reparsed accepted packets and causal history. Test altered raw bytes, normalized mismatch, wrong issuer/network/scope, missing/null/scaled/gap/revision/outlier/error records. | After01's schema/trust choice. Recorder/parser can be built alongside02B, without provider requests during initial tests. |
| R3-02B — Fresh model/version fork | New sealed v3 state/config/source/candidates with original GA math. Compare full next wires and mirrors on common immutable normalized corpora, including mating, risk, partial windows and retained holdings. Never cast v2/v5 state. | Parallel with02A after frozen interfaces. Native admission waits on both. |
| R3-03 — Operator/native composition | New scoped capabilities, package/catalog/source admission and atomic journal/pins/IDs/history/projections; actual original getter/readback, lease/source/locks/recognized COMMIT/rollback/Stop-capacity tests. Test explicit epoch rollover and all failed effects rollback. | Requires02A+02B, reviewed original native/retention lessons and independent installed-package checks. No production migration yet. |
| R3-04 — Restoration/restart | New v3 bounded decoder; current-head and retained identity/epoch oracle; exact uninterrupted versus restored next full/compact wires; original uncertain-command lookup; explicit process rollover and fresh acquisitions. Prove no load-created lease/activation and held-position/risk preservation. | Depends03 and accepted corpus. UI projection fixtures can proceed in parallel after03's schema freezes. |
| R3-05 — Retention/physical budgets | Archive/readback/pin/receipt proofs, unavailable/forged/foreign archive tests and real table/index/TOAST/WAL/raw growth plus Stop/reconciliation reserves. Set bounded pilot limits and actual cadence from measurements. | Physical measurements after03. Can overlap04 and UI, but activation waits for all. |
| R3-06 — New reader/UI join | New owner-authenticated projection/readback schema and renderer; old/new compatibility, private-session replacement, late replies, history/unknown states, original-ID pending controls and Stop holdings. No model/RNG trust in browser. | After03's frozen projection. Offline fixture work parallel with04/05; exact hosted session join after migration preparation. |
| R3-07 — Closed migration / rollback | Exact target verification; writer drain and pending original reconciliation; forward additive migration; limited installer/catalog/grant checks; old/new read tests; evidence-preserving rollback rehearsal. | After03…06 accepted, before any consequential cloud operation. User authorization applies only to the exact Dashboard targets. |
| R3-08 — Closed hosting / bounded paper pilot | Exact worker image/package/env/catalog/pin/clock identity; remain closed; finite read/acquisition/relay/renewal checks; then bounded two-window/restart/held-position operation under chosen limits and original-ID controls. | Requires01…07 and separate gate decision. Continuous paper operation waits on measured long-duration/resource/failure acceptance; live funding/signing/trading remains outside scope. |

## Migration and rollback contract

Prepare additive v3 schemas/capabilities only. Preserve v5 and synthetic-v2 rows,
hashes, source labels, assessments and controls. Do not alter old command bytes
or rescore incomplete history. A new v3 run begins through its new bootstrap and
recorded corpus; any future economic transfer from an old paper run requires a
separately validated carryover command with both original references, not a
database copy or source-format substitution. Initial MVP may instead leave old
runs readable and create a fresh correctly scoped v3 run.

Before cloud work, verify GitHub `TOOTRJ/TheDashboard`/1141090963, Vercel
`the-dashboard`/`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH` under
`orderoftheredjester`/`team_8iNNxiNjrOseD4gdSCHkQEzF`, Supabase
`The Dashboard`/`fxpxsciltakyypunglzr` under Valentine Jester/
`cqfnnaunmupdyobkyqfo`, and Railway `The Dashboard Worker`/
`38facb49-4de9-4d66-85aa-2861e0306dcf` under workspace
`f3fcd4b2-e424-4c6b-ac33-91196ccc96e1`, production environment
`9bbe52c6-2305-467a-bf39-8d5e1a98e4e4`, service `dashboard-paper-worker`/
`8e78ad4b-1d8f-43e7-898a-3882ac5053d7`. Use repository-isolated helpers/profiles; preserve other projects,
agents, credentials, account-wide settings and processes. A verified target does
not satisfy activation, data rights, freshness or native-package gates.

Drain ordinary admission while preserving the current owner's original pending
request and reserved Stop. Reconcile original IDs before changing writers or
leases; verify actual current heads and held positions. Capture schema/catalog/
role/version manifests and retained readback, install with the limited issuer,
and validate exact hashes/grants plus both old/new reader behavior. Keep new
worker and data acquisition closed until accepted bindings are installed.

Rollback closes v3 ordinary admission first, retains original pending
reconciliation/Stop/read paths and archives no referenced evidence. Preserve
v3 journals, raw corpus, IDs, pins and package manifests. Roll back deployment
selection to the previously accepted closed version and keep old readers
available. Do not send v3 data to v5/v2 writers, delete v3 records, reset an
identity ledger, restore an old head over a newer accepted one, or assume an
uncertain request rolled back. If v3 holdings remain, leave them explicitly
reconciliation-required with the correct version reader/native handler retained.

## What is accepted now and what still needs deeper research

The standalone proposal module passes nine focused offline cases, zero skips
(0.090 seconds): closed deterministic roundtrip, immutable schema/version map,
unknown/nested/version refusal, no v2 relabeling, no quota/retention/package
claim injection, canonical seed/bps/epoch/wire bounds, no resource contact/ID
allocation/seeding, and an import boundary excluding runtime/provider/database/
private environment dependencies. This proves proposal validation only. It
does not prove a v3 model, source corpus, parser, native capability, migration,
UI API or worker conformance; those are the ordered gates above.

Prioritize substantial research on provider publication and revision behavior,
actual filtered/unfiltered minute availability and Birdeye rights; authenticated
recording trust versus externally attestable provenance; restart clock/network
epochs with retained source marks; repeated-block/source-age distributions;
complete native/COMMIT/relay tail bounds; dependency-safe cold archive/version
maintenance and actual raw/index/TOAST/WAL budgets; and common held-out grid versus
evolution performance with calibrated paper execution costs. More generations
or a higher API plan cannot replace independent market evidence or those proofs.
