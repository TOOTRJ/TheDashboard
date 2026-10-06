# Inert Dashboard command HTTP transport

DB-03A2D2, reviewed 2026-10-05. This module is deliberately disconnected from
service startup, legacy persistence and production command submission.
[Production cutover](PRODUCTION-CUTOVER-PLAN.md) and DB-03A3 still gate activation.

## Pinned boundary

`DashboardCommandHTTPTransport` owns one HTTPX 0.28.1 async transport/client, on
one event loop with one admitted request. Its constructor takes only an explicit
private modern `sb_secret_` credential, canonical owner UUID and validated
bounds. There is no environment lookup, endpoint/client/header override, global
client, automatic submission retry, redirect, proxy fallback or environment CA
fallback. Both the underlying HTTP transport and client explicitly configure
TLS validation, `trust_env=False`, finite timeouts and a one-connection pool.

The only origin is `https://fxpxsciltakyypunglzr.supabase.co`. The only schema is
`vn_durability`; POST `Content-Profile` selects it. Seven immutable exact
parameter sets cover `create_run`, `heartbeat`, `commit_command`, `get_command`,
`interrupt_expired`, `read_outbox` and `acknowledge_event`. Canonical identity,
owner equality, integer/decimal parameters, node/depth and byte budgets are
validated and copied into immutable bytes before dispatch.

Opaque Supabase secret keys are sent in `apikey` only. Publishable keys and
legacy/custom JWT credentials are unsupported by this initial adapter, rather
than silently interpreted as interchangeable credentials. The owner pin is a
client safety check; it is **not server authentication of a user**. A service-role
credential is broad, and the fixture demonstrates that an authorized worker RPC
can supply another valid owner argument. A custom least-privilege worker role,
gateway authentication and complete privilege cutover need separate review.
[Supabase key semantics](https://supabase.com/docs/guides/getting-started/api-keys).

## Failure and resource ownership

Default engineering bounds are three seconds for request/response/decoding,
connect 0.5s, read/write 1s, pool 0.1s and separately bounded cleanup 1s. These are
configurable positive finite values capped at 15s; each I/O phase must fit the
whole-operation bound. They are not measured production budgets, and one RPC's
bound does not establish a whole-tick/source-age/lease budget.

Only HTTP 200 with identity encoding and strict UTF-8 JSON is accepted. Requests
are capped at 327,680 bytes; responses at 393,216 bytes, with 40,000 JSON nodes
and depth 64. Duplicate keys, non-finite or floating JSON numbers, invalid Unicode,
NUL, unsupported media/encoding, excessive/invalid/truncated lengths and an
explicit applied `tx=rollback` are rejected. Protocol monetary values remain
exact strings. Response limits also cap synchronous parsing work; a post-decode
clock check prevents acknowledgment after the cooperative deadline has elapsed.
Error messages contain fixed local codes, never remote response bodies or keys.

Raw response iteration avoids HTTPX's implicit close-at-EOF. One retained task
owns response closure outside the I/O deadline; cancellation/timeout cannot lose
that task or repeat closure. Pending/failed cleanup closes admission. Shutdown
closes admission before awaiting active work and retained cleanup, owns one
client-close task, and reports incomplete/failed cleanup without cancelling an
owned economic request. The repository owns original-command uncertainty: a lost,
malformed, oversized or cancelled dispatched result is not proof of rollback.
Only explicit readback of the same command ID can resolve it; the transport never
creates a substitute command.

## HTTP and database acceptance

`tests/test_command_http.py` uses fake responses and exclusive kernel-assigned
loopback sockets. It checks exact pins/headers, environment isolation, admission
and response budgets, redirects/error statuses/truncation, lengthless overflow,
trickle deadlines, cancellation, busy/shutdown behavior, retained cleanup and
original-command readback. Its connector rewrites a pinned URL only inside the
test fixture; the production constructor has no endpoint override.

The opt-in `tests/postgres/http_harness.py` runs actual **PostgREST 14.5** with
PostgreSQL 17.6, resolving already-installed images to immutable IDs. PostgREST
14.5 was fetched explicitly for this task to match hosted version metadata; the
runner itself never pulls or installs. It creates only UUID/ownership-labeled
containers and a separate owned bridge with IP masquerading disabled. Docker
29 suppresses published ports on an internal network, so this HTTP fixture uses
a bridge and one exclusive `127.0.0.1` port. This is not a general egress firewall;
all fixture URLs refer only to the owned database/server. PostgreSQL has no host
port and allows the fake authenticator only from that fixture subnet. Images are
read-only, non-root and resource-bounded, with no host file mounts or application
credentials. Cleanup verifies labels and removes exact owned resources only.
The original SQL-only harness retains `--network none`.

Fake locally generated JWTs test audience/expiry/roles; a test-only connector
stands in for Supabase's opaque-key gateway. This does **not** prove hosted gateway
mapping or all production role defaults. Nine real HTTP/database tests cover:

- create/batch/heartbeat/interruption and independent journal/account readback;
- a late invalid operation rolling back all earlier operations;
- exposed schema selection, hidden helpers, anonymous/authenticated write denial,
  JWT rejection, owner-visible/foreign-owner table reads and direct-write denial;
- broad service-role owner-argument behavior;
- forced rollback returning HTTP 200 despite requested `tx=commit`, with no
  committed journal/run; allowed overrides committing only when honored;
- a lost HTTP reply after a real commit resolving the original ID without a
  second create;
- the actual provider-bound v5 controller with fabricated literal provider
  replies: bootstrap, current-clock deferral/tick, installed SQL state, reserved
  stop and contiguous outbox ACKs through the new HTTP adapter.

[PostgREST transaction-end configuration](https://docs.postgrest.org/en/v14/references/configuration.html#db-tx-end)
can ignore transaction preferences. Therefore a JSON success or requested
`Prefer: handling=strict,tx=commit` is not proof of commit. Before activation,
prove the hosted transaction policy with independent committed journal/projection
readback under the complete forward migration and privilege plan.

## Exact hosted metadata and remaining gates

Authenticated project metadata reverified GitHub `TOOTRJ/TheDashboard`
(repository 1141090963), Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`
(team `team_8iNNxiNjrOseD4gdSCHkQEzF`), and Supabase `The Dashboard` /
`fxpxsciltakyypunglzr` (organization `cqfnnaunmupdyobkyqfo`). Two read-only schema
GETs returned hosted PostgREST **14.5**, HTTPS metadata, and HTTP **406/PGRST106**
for `vn_durability`. No command RPC was called on the hosted project. The prior
catalog audit confirms no deployed durability schema. Hosted transaction-end
policy and schema-cache reload acceptance are not established by these reads.

Remaining: DB-03A2D3 atomic/versioned projections and complete forward migration;
DB-03A3 actor-specific/hosted commit, overlap, rollback and service selection;
measured remote source/DB/lease/relay latency; safe interrupted-state handling;
custom worker credential research; preview isolation and hosting. Multi-window
checkpoint expansion and automatic restoration remain separate. See
[the MVP critical path](../../MVP-READINESS.md).
