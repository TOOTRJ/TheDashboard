# Dashboard VN production cutover inventory and plan

DB-03A2D1, 2026-10-05. This increment records a read-only deployed inventory,
the legacy writer/read paths and a concrete forward plan. It does not install
the rehearsal schema, change grants, select a controller or start a worker.

The only authorized targets are GitHub `TOOTRJ/TheDashboard` / `1141090963`,
Vercel `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`, team
`team_8iNNxiNjrOseD4gdSCHkQEzF`, and Supabase `The Dashboard` /
`fxpxsciltakyypunglzr`, organization `cqfnnaunmupdyobkyqfo`. Provider metadata,
both local cloud pins and the cached database connection identity were verified.
The unrelated Supabase connector was not used. The preceding release is
[PR40](https://github.com/TOOTRJ/TheDashboard/pull/40), merge
`22af3190c0171671747d69e971807144a2fa3322`, READY production
`dpl_6rxutLU4iyGA3328ZhP7NkePYU4y`, with four read-only application checks passed.

**DB-03A2D1A checkpoint (2026-10-05):** the independent browser history repair
now merges owner-filtered colony and probe-only runs with validated complete
bounded pagination and retired-session cancellation. Probe-only records remain
historical evidence with unknown colony authority; no rows are backfilled. The
135-test offline suite reproduces all 24 runs/16 legacy groups in the measured
shape. Separate HTTP pages are not an atomic snapshot; versioned projections,
other detail-reader pagination and actual actor-specific RLS acceptance remain
open. See configuration preflight section 48. Inventory counts below remain the
dated pre-repair snapshot, not a new live browser observation.

**DB-03A2D3B1 checkpoint (2026-10-05):** fresh sequential read-only inventory
matches all recorded catalog/count fields. The isolated legacy retirement and
owner-only classification pass 25 PostgreSQL cases, with source/object/grant
manifest, column/inherited/SET ROLE/MAINTAIN denial, unrelated-object preservation,
late rollback, old-writer overlap and actual v5 projection coexistence.
[Contract and current installation findings](LEGACY-WRITE-RETIREMENT.md).
Hosted `postgres` cannot grant the fixture's auth dependencies onward. B2 must
prove a complete v5 forward package under actual installer privileges and a
durable legacy drain/reconciliation/archive evidence policy. B1 remains outside
migrations/startup; D3B/D3C/A3 remain open. Dedicated Vercel login and all exact
targets were reverified on 2026-10-06. Source/merge READY deployment and read-only
smoke acceptance remain release gates; immutable evidence belongs in the PR.
No cloud migration is included in this increment.

## Verified aggregate and catalog evidence

The [audit SQL](../../supabase/audits/vonneumann-cutover-inventory.sql) runs one
repeatable-read, read-only transaction, with a one-second lock timeout and
15-second statement timeout, ending in rollback. Supabase CLI 2.84.2 executed
it through the verified linked project's Management API. Returned session
metadata confirms all four settings; this is distinct from earlier migration
runner timeout assumptions. Failed draft queries made no mutations. The final
query passed. No application row IDs, configuration/genome bodies, API keys or
function bodies are output. The
[dated catalog/count snapshot](../../supabase/audits/2026-10-05-vonneumann-inventory.json)
retains exact definitions/ACL metadata for review; re-inventory before any
mutation because counts and grants can change.

| Legacy table | Rows | Non-null runs | Rows without a colony | Important retained unknowns |
| --- | ---: | ---: | ---: | --- |
| `vn_colonies` | 8 | 8 colony identities | — | All saved statuses are stopped; saved status is not current worker authority. |
| `vn_probes` | 497 | 24 | 160 | All `metrics` are SQL NULL; all new `parent_ids` arrays are empty. 257 scalar `parent_id` relationships remain. |
| `vn_trades` | 807 | 15 | 126 | All `execution` records are SQL NULL; 17 rows have no close timestamp. |
| `vn_fitness_snapshots` | 9,837 | 10 | 1,098 | All `metrics` are SQL NULL. |
| `vn_generation_stats` | 0 | 0 | 0 | No persisted generation summaries in this snapshot. |

Each populated table has one distinct owner. All four child tables have zero
NULL run IDs. The snapshot finds zero missing probe references, matching-row
owner/run disagreements, scalar-parent missing/self/cross-owner/cross-run
relationships, malformed ancestry arrays or duplicate generation groups.
The five validated NOT NULL owner FKs and the explicit colony-owner check
preserve owner existence in this snapshot. These observations do not prove
two-user RLS isolation, reconstruct missing metadata or prevent future invalid
relationships. No closed trade lacks the checked exit fields and no open trade
contains those fields; this is shape evidence, not a cash/position reconciliation.

**The pre-repair history reader omitted 16 probe-only runs.** The 160 probes without
colony records belong to 16 owner/run groups whose owner also has colony rows.
Before D1A, `fetchColonyRuns()` returned only colony-derived history whenever that query was
nonempty; its probe fallback then did not run. This is a measured compatibility
gap, not evidence that those older records should be deleted or assigned newly
invented colony records. See
[the reader](../../src/lib/probes/probes-supabase.ts#L156).

All five tables are owned by `postgres`, have RLS enabled without FORCE RLS,
and retain 18 permissive policies scoped to PUBLIC with `auth.uid() = user_id`.
There are 93 columns, 19 validated constraints and 25 valid/ready indexes.
The four nullable UUID `run_id` columns have no colony FK; probe, trade and
snapshot relations bind scalar probe IDs rather than composite owner/run IDs.
JSON ancestry has no relationship constraint. Generation uniqueness remains
`(user_id, run_id, generation)`, which does not prohibit duplicate NULL-run keys.
The snapshot's three incoming VN FKs are the scalar parent, trade and snapshot
links; no external incoming FK, immediate dependent view, related sequence,
unexpected VN relation or VN realtime publication is present.

The two non-internal update triggers are enabled. Colony updates resolve to
`extensions.moddatetime`; probe updates resolve to `public.vn_set_updated_at`.
Both functions are security-invoker. Trigger-associated built-in FK functions
are included in the snapshot too. No selected function is security-definer.
The deployed `vn_durability` schema is absent. All fourteen tracked migration
versions exactly match the live ledger. A matching version does not establish
equality with an edited historical file. The user's colony-migration edit is
preserved at SHA-256
`a62079713f387e1fa8abbf22ac4e109a163ba22c6fa4a2bb751bf0fa026793cc`;
its already-correct deployed trigger must not be replayed to resolve that edit.

## Effective privilege boundary

| Role | Effective privileges on each of the five VN tables | RLS/role behavior |
| --- | --- | --- |
| `anon` | SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN | No BYPASSRLS; ordinary owner policies do not grant anonymous row ownership. |
| `authenticated` | Same eight privileges | Owner policies permit the declared operations on owned rows; no fence/revision check. |
| `service_role` | Same eight privileges | BYPASSRLS is true; direct CRUD remains a route around fenced commands. |
| `authenticator` | None directly | Can SET ROLE to the three API roles; does not inherit their table privileges. |

There are no explicit column ACLs. The membership scan is not truncated; its
three edges are the authenticator's non-inherited, settable API roles. Exact
table ACLs and independently computed column/table privileges are retained in
the snapshot. PostgreSQL 17 MAINTAIN is included. These metadata results are
not evidence that Data API exposes a TRUNCATE operation or that an anonymous
request can bypass RLS. RLS filters ordinary row operations; TRUNCATE and
REFERENCES privileges are not owner-filtered by RLS. Actor-specific denial
tests remain required. [PostgreSQL row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

The `postgres` defaults in `public` grant broad table/sequence/function access
to the API roles. `vn_set_updated_at()` also has PUBLIC EXECUTE. It is an invoker
trigger function, not a demonstrated privileged RPC bypass. Preserve shared
extensions and unrelated objects. Do not change `postgres` defaults globally
to fix VN; create the reviewed dedicated VN owner with its own safe defaults,
and explicitly revoke/grant each new function in its installation transaction.
New functions' default PUBLIC execution and inherited privileges require
separate attention. [PostgreSQL function security](https://www.postgresql.org/docs/17/sql-createfunction.html),
[role membership](https://www.postgresql.org/docs/17/role-membership.html).

Function discovery covers the durability schema, public VN names/source-string
matches, direct relation dependencies and functions bound to VN triggers across
schemas. Source matching is a heuristic. It cannot prove the absence of dynamic
SQL, external clients or differently named wrappers without recorded dependencies.
Views are immediate catalog dependencies. Future migration review must inspect
every new callable path and exact signature; no claim of universal bypass
coverage is made here.

The recorded role settings include anon statement timeout 3 seconds,
authenticated timeout 8 seconds, and authenticator statement/lock timeout
8 seconds. The queried allowlist contains no `pgrst.db_schemas` or `db_tx_end`
override. That absence does not establish the hosted service's effective API
configuration. No JWT secret or unrestricted settings response was inspected.

## Existing writer, read and event paths

| Path | Current behavior | Required replacement |
| --- | --- | --- |
| FastAPI start and startup compensation, `server/app.py` | Service-role colony INSERT and separate status/runtime UPDATE | One versioned creation/control boundary, original-ID resolution, no legacy CRUD fallback. |
| `core/colony_manager.py` and risk callbacks | Process-local mutable `GenesisController`; separately persisted lifecycle | Explicit opt-in selection only after acceptance, database lease/fence authority and retained drain/settlement. |
| `db/repository.py` / `EventPersister` | Probe births/metrics/deaths, trade opens/closes, snapshots and generation upserts are separate writes | All economic operations plus required projections/journal/outbox commit in the same command transaction. |
| Browser `probes-supabase.ts` | D1A merged owner-bound history with validated bounded pages; other detail queries retain direct casts/unpaginated reads | Versioned validated owner-only read models and bounded pagination for all remaining detail readers. |
| Former exported `deleteAllProbes()` | Removed in D3A; its prior four sequential date-filtered DELETEs had no selected-run filter | B1 rehearses equivalent direct-mutation denial; B2/C/A3 gate reviewed production run-specific archive and privilege cutover. |
| `_make_dual_handler` / `server/websocket.py` | Persist one legacy event then attempt socket broadcast; send failure/zero subscribers is not durable delivery | Durable relay acceptance, stable IDs and replay/deduplication before acknowledging an outbox event. |

The active worker uses `SUPABASE_SERVICE_ROLE_KEY`. Its repository serializes
owned writes, drains cancellation and does not automatically retry, but lacks
stable economic command IDs and atomic multi-table transitions. Founder and
replacement/retirement paths mutate memory before separate event persistence.
Replacing only `EventPersister` misses colony startup/status/risk/control writes.
The new provider controller and injected `CommandTransport` are not selected by
the service. Readiness still refuses durable recovery. Relevant code:
[service construction](vonneumann/server/app.py#L139),
[legacy repository](vonneumann/db/repository.py#L47),
[controller selection](vonneumann/core/colony_manager.py#L279),
[browser helper](../../src/lib/probes/probes-supabase.ts#L207),
[socket publication](vonneumann/server/websocket.py#L32).

## Preferred authority and read-model plan

Preserve the five current public tables as owner-readable legacy evidence.
Fresh v5 runs must use separate authoritative durability records and explicitly
versioned read projections. Do not hydrate them from old float balances or
attach older rows to a guessed new owner/run. Use a dedicated non-login,
non-superuser owner with no API-role membership, exact auth dependencies,
qualified names and safe function search paths. The isolated SQL file is
reference/rehearsal material, not a migration ready to copy into production.

The preferred browser surface is a bounded `vn_read` schema/read API; normal
browser access should not expose full checkpoints, optimizer state or command
requests. Preserve the public legacy schema and unrelated API exposure. A
versioned history adapter merges fresh runs, legacy colonies and the 16
probe-only runs, de-duplicates by provenance plus owner/run, and retains explicit
unknown lifecycle/policy fields. A probe-only run is historical/unmanaged, not
implicitly active or safely resumable. Pagination and aggregate summaries must
be server-defined, not inferred from a truncated page. The schema names/API
exposure and complete object definitions need acceptance before installation.

| Current UI projection | Exact source | Required committed projection |
| --- | --- | --- |
| Colony/config/runtime | `runs`, immutable config, checkpoint lifecycle/source/cohort state | Version, owner/run/revision, strategy/mode/reference currency, start/stop times, policy/source/code identities, reconciliation and availability. |
| Probe/genome/ancestry | Accounts, current members, typed lineage/distributions and command transitions | Indexed birth/name/genome/history, typed parents, lifecycle, exact/display metrics and immutable terminal values. |
| Trades | Positions, entry/exit execution and action/source evidence | Timestamps/reasons, USD reference versus SOL/USDC labels, signal/cost policy, gross/net P&L and committed revision. |
| Fitness samples | Source marks, member risk/cohort evidence | Explicit sampling policy and stable sample identity; retained indexed time series with unavailable diagnostics. |
| Generations/evaluations | Completed cohort/evaluation/selection and lineage evidence | Immutable evaluated membership/results/selection and versioned aggregates; do not overwrite earlier history. |
| Browser events | Ordered outbox records | Versioned owner/run/revision/event identity, validated UI envelope, durable relay/replay cursor and browser deduplication. |

**Retired cash is not terminal capital.** Retirement sweeps account cash into
reserve and sets `accounts.cash` to zero. Historical capital/ROI must retain the
terminal/evaluation value before that transfer. Otherwise a successful retired
member would appear to lose all capital. See
[retirement](vonneumann/core/exact_lifecycle.py#L182) and
[replacement](vonneumann/core/exact_rehearsal.py#L509).

**The newest checkpoint is not complete UI history.** Cohort replacement
replaces `engine.members` and `engine.last_evaluation`. Persist historical birth,
terminal, trade and evaluation projections during the same command transaction
when readback requires them. An asynchronous projection is acceptable only with
specified durable replay/checkpoint, lag and revision semantics. Do not use
`EventPersister` as a second economic writer after outbox publication.

Hex/tagged optimizer/genome floats and canonical decimal money need a validated
read adapter; current TypeScript row casts and the v1 percentage-cost parser
cannot consume v5 state directly. Keep exact values authoritative, define bounded
display conversion explicitly, and preserve old NULL execution/metrics as
unknown. The empty new ancestry arrays do not establish no historical ancestry;
scalar/embedded evidence must remain intact without an invented backfill.

Archive is presentation metadata, never economic liquidation or deletion.
The replacement must bind the authenticated owner and selected run/provenance,
preserve all journals/projections/legacy rows, record an audit event and reject
active or uncertain authoritative runs. Stop can retain holdings; archived
history must still disclose unmanaged retained exposure. Legacy classification
and archive eligibility need an explicit accepted policy. Never interpret a
missing lease as proof that an older process has stopped.

## Pinned transport and API acceptance

Implement one owned HTTPX adapter, pinned to
`https://fxpxsciltakyypunglzr.supabase.co`, the reviewed schema and seven exact
RPC names/signatures. The rehearsal grants are `create_run`, `heartbeat`,
`commit_command`, `get_command`, `interrupt_expired`, `read_outbox` and
`acknowledge_event`; all helper functions remain private. A separate archive/read
surface must not broaden those economic RPCs. Trusted server authentication
binds the owner argument; a service-role key is still capable of supplying another
owner, so custom worker-role feasibility remains a security research gate.

PostgREST uses `Content-Profile` for POST RPC and `Accept-Profile` for GET/HEAD;
exposure and schema USAGE are separate prerequisites. Never copy broad example
grants from documentation. Opaque Supabase secret/publishable keys are not JWTs;
classify privately. Send opaque `sb_secret_…`/`sb_publishable_…` keys in `apikey`;
use `Authorization: Bearer` only for a genuine validated JWT under the reviewed
authentication contract.
[PostgREST schemas](https://docs.postgrest.org/en/v14/references/api/schemas.html),
[Supabase custom schemas](https://supabase.com/docs/guides/api/using-custom-schemas),
[API keys](https://supabase.com/docs/guides/getting-started/api-keys).

HTTPX 0.28.1 is the repository's pinned version. Configure both the owned
transport and client explicitly: TLS verification, no environment proxy/CA
fallback, zero retries, no redirects, finite pool/phase timeouts and one whole
operation deadline. Client settings do not reconfigure an injected transport.
Bound streaming bytes before decoding; reject unexpected compression/media
types, invalid UTF-8/JSON, duplicate keys, nonfinite values and excess structure.
Content-Length and per-chunk read timeout alone do not bound a whole response.
Close responses/clients through retained owned cleanup. A dispatched command's
lost, malformed, oversized or cancelled reply retains original-ID uncertainty;
there is no automatic repeat of a dispatched mutating POST. Explicit original-ID
readback remains permitted, including a read RPC using POST. These requirements follow the exact
[transport implementation](https://raw.githubusercontent.com/encode/httpx/0.28.1/httpx/_transports/default.py),
[client implementation](https://raw.githubusercontent.com/encode/httpx/0.28.1/httpx/_client.py),
[timeouts](https://www.python-httpx.org/advanced/timeouts/) and
[streaming closure](https://www.python-httpx.org/async/).

Pin the hosted PostgREST version, exposed schema order, extra search path,
max-row/pool/acquisition limits, pre-request hook, role/function timeout and JWT
role/audience behavior. The safe Management API configuration allowlist can
help; its full response may contain `jwt_secret` and must never be printed.
It does not independently document the effective transaction-end setting.
[Service config reference](https://supabase.com/docs/reference/api/v1-get-postgrest-service-config).

A successful HTTP reply or `Prefer: tx=commit` is not sufficient under an
unverified `db-tx-end` mode. Prove all accepted writes/journal/outbox/projections
persist together through subsequent independent readback. Test forced rollback,
ignored preferences, late constraints, loss after commit and reused-ID payload
mismatch. The cited PostgREST 14 documentation is a contract reference, not proof
of the hosted version. [Transaction configuration](https://docs.postgrest.org/en/v14/references/configuration.html#db-tx-end),
[preferences](https://docs.postgrest.org/en/v14/references/api/preferences.html),
[transactions](https://docs.postgrest.org/en/v14/references/transactions.html).

## Forward sequence and rollback gates

1. Reverify the exact targets/catalog and freeze the object-by-object forward
   migration/read-model/archive plan. Keep the modified historical migration
   outside it. Do not invent missing owners, ancestry, costs, clocks or balances.
2. Implement the inert pinned transport; test local real HTTP faults and isolated
   PostgREST schema/JWT/commit behavior. No service selection or credential/env
   change is required for this increment. Complete required read/event adapters
   and complete authoritative projections before cutover.
3. Rehearse the full forward migration under the captured effective grants,
   representative legacy gaps, two owners, anon, column/inherited privilege
   attempts, lock contention and injected late failure. Install helpers with
   private execution in one transaction. Leave unrelated grants/defaults intact.
4. Drain/disable all old worker versions and browser mutation paths. Deploy the
   compatible read/API release with new admission disabled. Apply reviewed
   exact-object VN grant changes together with the complete transport/projection
   migration. Deny legacy INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER/MAINTAIN
   to API roles/PUBLIC and verify no effective column/inherited bypass remains.
   Keep necessary owner-only reads. Do not revoke schema USAGE or shared role
   permissions needed by unrelated Dashboard features.
5. Prove engine → command RPC → journal/projection → owner read/UI and durable
   relay/reconnect, interruption/overlap, SIGTERM/SIGKILL and original-ID
   reconciliation. A socket broadcast with no clients is not durable relay ACK.
6. Measure actual provider/DB/lease/CPU/relay tails and remaining lease headroom,
   then justify a supported bounded cadence. Only accepted cutover, recovery,
   preview isolation and hosting gates permit worker selection/launch.

This plan does not authorize enabling resume/recovery, old-run adoption, live
wallet operations or trading. Project identity verification is necessary but
does not establish runtime readiness.

Rollback is additive: close admission and drain owned work, retain acknowledged
v5 records and legacy history, and restore only a compatible read/application
path. Once v5 commands exist, never re-enable unfenced old writers over those
runs, drop journals, undo balances or remove projections needed for reconciliation.
Before any new commands exist, exact captured VN grants may support a separately
rehearsed restoration; that is not a generic rollback command. Re-inventory after
failure and prefer a reviewed forward correction. This inventory-only release
itself rolls back by a code/document revert and requires no database rollback.

## Further substantial research

Before final cutover/hosting, resolve custom worker-role/JWT scope, hosted
transaction-end and schema-cache behavior, durable relay ACK/replay/pagination,
legacy unmanaged/archival classification, projection/sample comparability,
journal retention/compact checkpoint dependencies, remaining-lease scheduling,
organization-wide provider quotas, source publication tails and dense PSO/CMA
CPU/capacity under actual load. The five local controller measurements do not
establish production percentiles or safe protective exposure. Keep
DB-03A2C2D2D2A, D3, DB-03A2D/DB-03A3 and hosting parents open until their
individual acceptance evidence exists.

## DB-03A2D3A preparation checkpoint — 2026-10-05

The fresh exact-target read-only inventory still reports 8 stopped legacy colonies,
497 probes, 807 trades and 9,837 snapshots; the fourteen-version migration ledger
and absence of the durability schema are unchanged. D3A now rehearses atomic
projection history, terminal cash, owner reads, durable sequenced relay/ACK/replay
and non-destructive archive. [Detailed contract](READ-PROJECTION-CONTRACT.md).
The old bulk-delete helper is removed, while current legacy readers and writers
retain their existing production selection. No migration, hosted command or bot
launch is included. D3B must prepare the complete reviewed forward object/grant
manifest and classify legacy archive eligibility. D3C must replace all service
writers and wire compatible typed browser discovery/details/relay/archive, with
old-worker overlap and additive rollback drills. DB-03A3 applies only the accepted
complete cutover. Local contract testing is not hosted schema exposure or capacity
acceptance; preserve all outstanding research and gating listed above.
