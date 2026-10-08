# Authoritative bounded paper service

This is the D3C service/browser implementation and HOST-02 packaging candidate.
It remains closed by default. Code deployment to Vercel does not start the Python
worker, apply the forward database package or select this dashboard view.
Actual hosted acceptance, credentials, migration and measured cadence remain open.

## One economic authority

The image starts `vonneumann.server.paper_app:app`, never the legacy application.
`PaperService` owns one configured owner/run/epoch and original start/stop IDs.
It constructs the exact v5 repository, provider pilot owner, native economic/relay
transport, durable relay publisher, controller and finite runner. There is no
EventPersister, legacy CRUD fallback, wallet signer, restoration or live mode.

Start latches before scheduling. HTTP callers do not own its task. Repeated start
requests inspect the same operation; a lost create reply retains the original
command for explicit settlement. Each process gets a new worker identity. A
restart attempting the old run cannot adopt its command/checkpoint as its own;
SQL rejects it and the service stays unresolved without another economic create.

Stop first latches admission. Its HTTP 202 is a request acknowledgment, not proof
of a committed stopped state. Finite budget exhaustion spends the separately
reserved stop ID through the real controller. Stop preserves cash and positions;
it never invents liquidation proceeds. An interruption without a completed
terminal checkpoint remains drained/failed/pending and requires reconciliation.

The initial configured profile is GA, eight candidates, SOL/USD reference,
`ema_fast`/`ema_slow`, one common evaluation window and at most one replacement.
Integers explicitly bound interval to 1–30 seconds, accepted ticks to 1–3,601 and
the configured quote duration to at most 3,660 seconds (one hour plus a 60-second completion margin). These input bounds do not select
a production cadence. A short smoke may stop before any completed evaluation.
Costs are an uncalibrated scenario, not executable Solana fills.

## Browser and API

`NEXT_PUBLIC_VN_SERVICE_MODE=paper-v5` explicitly selects `PaperDashboard`; the
currently deployed legacy selection remains unchanged until A3 approval/gates.
The new view has start, retained-holdings stop, original-operation settlement,
refresh and non-destructive stopped-run archive. It generates no new run/control
IDs. Uncertain archive retries retain the same run/revision/request ID.

Worker requests use the authenticated Supabase user token and exact HTTPS worker
origin. Server Auth verifies the token with the fixed project; only the configured
owner can read/control that pilot. CORS permits only
`https://the-dashboard-chi.vercel.app`. Public `/health` reports process liveness
without calling providers/DB. `/v5/status` reports owned state, reconciliation and
timings; liveness or configuration is not successful hosted acceptance. Control
bodies are capped at 256 bytes/three seconds and reject duplicate JSON keys.

Browser reads use the fixed `fxpxsciltakyypunglzr` REST origin and only the
`vn_read` schema's curated discovery/page/event/archive RPCs. A new bounded
`discover` function is included in the complete forward candidate: final inventory
is now **98 functions and 26 tables**. Authenticated owners see only their runs
and archive receipts; economic/relay/API service roles cannot discover raw data.
Discovery is a refreshable UUID-keyed directory, not a repeatable-read ledger
snapshot. Run details pin every projection kind to one authoritative revision.
Events pin a separate durable sequence and reject gaps/duplicate identities;
reconnect replaces complete history rather than double-appending socket deltas.

All wire responses are at most 64 KiB with finite request/whole-read deadlines.
Exact monetary strings use integer display rounding; tagged floats are decoded
only for research scores. Candidate cash, frozen terminal capital and unavailable
equity remain distinct. Trade fees/P&L and completed/aborted evaluation results are
shown with their original semantics. Legacy run diagnostics retain original
precision/policies and have no v5 resume/control authority.

Worker status and committed history load independently. A worker outage disables
controls while owner-bound committed history remains available. A failed history
refresh retains the last complete snapshot with an explicit error. Token changes,
account remounts, run selection and disposal cancel superseded reads; retired
control replies cannot publish into a newer credential context.

## Image and explicit private configuration

`Dockerfile` pins official Python 3.12.14 Bookworm slim's linux/amd64 leaf digest
`1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a`.
All runtime dependencies install with `--require-hashes --only-binary=:all:`.
The deny-by-default context copies runtime Python, the TLS preflight and entrypoint
only, excluding environment/certificates/tests/agent files. UID/GID is 10001.
One Uvicorn process uses the host's port, bounded concurrency, no access log and a
20-second graceful shutdown budget. No migration executes at build/startup.

The Railway candidate uses `/health`, restart `NEVER`, zero configured overlap and
30-second drain. One replica, no sleeping, service-specific outbound IPv6 and region
must be explicitly verified on the eventual exact service; these are not proven
by `railway.json`. Failures require operator review, not automatic adoption.

Closed mode needs no credentials. Paper mode requires every input explicitly in
the exact service's private store:

| Input | Required value or scope |
| --- | --- |
| `VN_SERVICE_MODE` | `paper-v5`, only after acceptance gates |
| `PYTHON_DOTENV_DISABLED` | `1` |
| `VN_ENVIRONMENT` | `production` |
| `VN_ALLOWED_ORIGINS` | Exact production dashboard origin above |
| `SUPABASE_URL` | `https://fxpxsciltakyypunglzr.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | Same project's modern public Auth key |
| `VN_DATABASE_CA_PEM` | Reviewed exact project's supplied PEM |
| `VN_ECONOMIC_LOGIN`, `VN_ECONOMIC_PASSWORD` | Dedicated issued economic principal |
| `VN_RELAY_LOGIN`, `VN_RELAY_PASSWORD` | Separate issued relay principal |
| `VN_PAPER_OWNER_ID`, `VN_PAPER_RUN_ID`, `VN_PAPER_EPOCH_ID` | Reviewed UUIDs, immutable DB issuance binding |
| `VN_PAPER_START_ID`, `VN_PAPER_STOP_ID` | Distinct retained original UUIDs |
| `VN_PAPER_INTERVAL_SECONDS`, `VN_PAPER_MAX_TICKS` | Explicit measured and bounded pilot configuration |
| `JUPITER_API_KEY`, `BIRDEYE_API_KEY`, `VN_SOLANA_RPC_URL` | Explicit provider settings/accepted shared quotas |

The new entrypoint deliberately requires `JUPITER_API_KEY`, independent of the
legacy `JUP_API_KEY` environment fallback. It rejects broad Supabase service/secret
keys and Railway deployment tokens in worker runtime. Deployment credentials are
operator-only. Frontend receives public mode/endpoint values, never DB passwords,
provider credentials, CA secret-store configuration or Railway token.

## Validation and limits

Full worker discovery: **1,683 tests, 227 expected SQL opt-in skips**. The separate
39-case forward/native suite and two new HTTP/native SQL cases exercise actual
TLS/SCRAM principals, complete package, owner discovery, repeated start, lost-create
settlement, restart refusal, real reserved stop, projections/relay and archive.
Provider responses and Auth identities are synthetic in that offline flow.
The final combined forward/native/HTTP/service/artifact rerun passes **50 tests in
91.068 seconds**. Full frontend regression passes **155 tests**, with TypeScript,
zero-error/warning focused lint and isolated production build successful.

Frontend checks cover original-ID controls, synchronous double clicks, token/read
disposal, unavailable worker history, archive replay, revision pinning, strict
owner/cursor/event bounds and exact trade/evaluation display. The actual browser
offline fixture demonstrates start/stop/archive/discovery/legacy diagnostics with
no browser console warnings/errors; it is not hosted Auth/market acceptance.

The real amd64 image built and ran non-root with network none/read-only filesystem:
health 200, unauthenticated status 401, legacy/docs routes 404, no env/ssl/test/agent
files. Closed startup took 6.739 seconds under local arm64 emulation. SIGTERM
completed lifespan and server shutdown in 0.230 seconds. Uvicorn re-raises the
captured SIGTERM, so exit 143 is expected; this is not an active-run shutdown,
resource percentile, Railway timing or graceful stop proof.

## Next gates and research

Follow [Railway setup](../../RAILWAY-SETUP.md) and C3B/A3 before activation:
selected-host IPv6/CA/hostname TLS, exact managed installer/issuer capability,
fresh target/catalog/migration history, reviewed forward execution and fresh-session
postflight, independently issued economic/relay credentials, owner-only `vn_read`
API exposure, two-user hosted browser/API/database acceptance and additive retirement.
Then measure actual provider/DB/relay/lease tails, shared quotas, resource/cost use,
kill/overlap/revocation/expiry behavior before the bounded pilot.

**More deep and substantial research remains required** for connection/COMMIT/lease
tails, remote source-age semantics and candle-boundary deferral, quota/credit billing,
managed privilege hooks, Auth transport maintenance, interrupted exposure, native
dependency/CA maintenance, retention and compact multi-window checkpoints. The first
service intentionally cannot provide continuous evolution or automatic restoration.

## Deliberate hosted controller assessment

`python -m tools.paper_controller_canary` is an explicit operator entrypoint,
not ordinary startup. It requires closed public API mode, finite-controller-v1
selection, a confirmed sole Jupiter consumer, at most thirty ticks and a minimum
five-second interval. The ordinary strict configured-service constructor builds
one actual native-v5 run. The assessment measures complete controller phases,
individual native RPC operations, actual provider calls/source ages and process
resources through its reserved terminal stop. The public API stays closed.
Results are finite min/median/max measurements, not statistical tail guarantees.
Failure retains the original run/command for inspection; no automatic retry or
new identity is admitted. Private exact-target activation, credentials, original
operation journal and rollback review must precede selection.

The temporary invoker credential operator still permits issuance only while the
reviewed release is closed. Exact original-pair revocation is permitted while
closed, open or retired, preserving bindings and economic history. It remains
private, has no definer elevation, and is removed after each reviewed operation.

Production configuration additionally requires the explicit
`VN_JUPITER_SOLE_CONSUMER=1` inventory acknowledgement and at least5s between
runner captures. Direct offline service fixtures may use a shorter cadence;
they do not select production.


## Paper SQL profile and original failure evidence — 2026-10-08

The selected paper service and finite controller assessment share fixed native
bounds: connection1s, each statement/lock3s, whole RPC5s, COMMIT0.5s and
cleanup1s. These connection-local settings address an actual hosted57014
statement timeout; generic transport defaults remain3s/0.5s/1.5s/0.5s/1s.
No retry, pooling, freshness/lease/expiry widening or automatic resume is added.
The first native failure per principal remains available in authenticated status
as `first_transport_failures`, with only allowlisted phase/category/SQLSTATE/code.
Later readback and cleanup cannot replace it, and returned dictionaries are
copies. Server error text, SQL/arguments, credentials and connection details are
not retained or published. Unknown fields/codes/SQLSTATEs are suppressed.
The canary reports the same evidence through its measurement wrapper.

## Explicit paper source-order policy — 2026-10-08

The selected paper service and finite canary enable bounded discard of an exact
`MarketFeedError(source_slot_regressed)` from the feed before quote admission.
Default acquisition/controller consumers retain fatal behavior. At most2 responses
are discarded between admitted tickets,8 in the run, and an episode may last less
than15 monotonic seconds. No quote/economic identity is allocated. Each discard
returns a normal deferred tick; the runner owns its next serial paced request.
Unchanged/fractional receipts cannot reset the episode. Only an admitted ticket
resets the episode count/deadline; the whole-run count persists. Clock failures,
stale data, invalid timestamps, malformed replies and deadlines are never discarded.
Accepted source watermarks, age anchors,30s source and5s receipt/acquisition limits
remain unchanged. Authenticated `source_order` and canary measurements contain
only fixed counters/limits/limit labels, copied independently of the retained state.

A recognized feed refusal before admission ends ordinary pilot polling with
`provider_capture_failed`, retaining the original reserved Stop only if its existing
owner/lease/capacity remain valid. No hard failure is reopened. Pending commands,
publication, admitted-evidence failures, unknown exception types and invalid clocks
retain their original settlement/hard-closure paths. One requested Stop settles
retained refusal work before its same reserved command; missing/lost replies cannot
cause a fresh ID or duplicate submission. A committed Stop can record an aborted,
unscored evaluation while retaining cash/reserve/positions; native interruption
has a different contract and does not invent candidate events or ACKs.

Validation: 173 focused offline cases pass on default asyncio (51.331s) and
production uvloop (50.119s). Thirteen actual offline Linux native TLS/SCRAM cases
pass (15.047s; outer owned fixture20.248s), including real feed-regression/SQL
invariance, next-source admission and one original reserved Stop after a feed
refusal. Lost Stop replies/missing readback, hard-closure non-reopening and
server lease refusal are covered. Local/native acceptance is complete; reviewed
release and new hosted assessment/hour remain separate gates.

The selected paper runner explicitly reserves6s before paced waits/renewals,
matching the5s SQL operation plus1s independent cleanup. Generic runners retain
the4s reserve for their3s+1s profile. Insufficient headroom drains without another
provider request or economic command; the120s database lease remains unchanged.
54 focused runner/service/canary cases pass under production uvloop.
