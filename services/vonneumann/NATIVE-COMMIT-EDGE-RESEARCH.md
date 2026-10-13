# Native commit guard: evidence and limits

Research checked 2026-10-13 UTC / 2026-10-12 America/Denver. This is an
**offline implementation and review contract**, not a migration, credential
provisioning request, Supabase verification, or authorization to enable a worker.
No provider credentials or hosted database were used in this research.

## Recommended guarantee

A deferred constraint trigger can check database-clock freshness and retained
lease/source/head bindings **during processing of a recognized explicit COMMIT**.
It cannot prove that those age limits still hold at the final durable commit,
visibility to another connection, or acknowledgement received by the client.
Keep these claims separate in code, receipts, tests, and readiness documentation.

The proposed strict `current_query()` allowlist is useful as a fail-closed
restriction on supported transaction forms. It is not an authentication boundary,
a PostgreSQL parser, proof of every preceding statement, or proof that the guard
is the last action before persistence. Authentication and immutable owner/run
capabilities must come from the verified session and private retained state.

If a pending acceptance criterion requires freshness **at the final commit
instant**, this research does not close it. A guard receipt should say
`freshness_checked_at_commit_guard`, with the actual database check time; it must
not silently become `fresh_at_durable_commit`. A bounded admission/guard policy
can be designed and tested now. An absolute final-time requirement needs an
explicitly revised contract or a stronger mechanism whose remaining timing
assumptions are proved. An observed short tail is not a proof of an upper bound.

## Evidence pinned to upstream PostgreSQL 17.6

The official PostgreSQL source mirror's `REL_17_6` tag resolved through the public
GitHub API to commit `7885b94dd81b98bbab9ed878680d156df7bf857f`. Public raw files
were downloaded with no authentication and hashed locally; commit-pinned
`xact.c` independently matched the tag download. The hashes below identify the
inspected evidence, not the binary running in a provider or fixture image.

| File under `src/backend/` | SHA-256 |
| --- | --- |
| `access/transam/xact.c` | `a22ce79a0654be793bb988cb5b48ee9712c4ba6a4ce72d8bca1179c8c7b2370b` |
| `commands/trigger.c` | `491628db26054d04120c2ff11a6122c45b912c367002c3474515c0c35dad0acc` |
| `tcop/postgres.c` | `801793541d67065a5e658e6eaf55f72ca70e30d3f23a8778b6205c9516b23832` |
| `utils/adt/misc.c` | `91a88f67912aef30f3645a04fbb587ef8351443d145a3d424f4c694d4dfc38d5` |
| `storage/ipc/procarray.c` | `2095d9a9823405117e58c99829f7e5f37d7133f054c71ceaeb750d441622e714` |
| `commands/tablecmds.c` | `f0b8320a5fe64c1b3b4a4fc9740bf110ed444d107045f48eeb1a32309a86f3a4` |
| `commands/async.c` | `a451364fbff669aee6f568331ef824bf32e43bf6fe97d91f3eb2d71816c9973a` |

The upstream `misc.c` implementation returns `debug_query_string` or NULL. The
frontend code supplies the simple-query text or prepared statement source text;
this is not a reconstructed current SQL statement. This matches the documented
possibility of multiple statements in one value. A `SECURITY DEFINER` function's
`current_user` is its execution identity, so session authentication cannot be
inferred from that value alone. [Pinned `misc.c` source](https://github.com/postgres/postgres/blob/7885b94dd81b98bbab9ed878680d156df7bf857f/src/backend/utils/adt/misc.c),
[session information functions](https://www.postgresql.org/docs/17/functions-info.html).

In the inspected `CommitTransaction`, PostgreSQL runs pending deferred triggers
and pre-commit portal handling in a loop. A portal can queue more trigger work.
`AfterTriggerFireDeferred` also drains newly queued deferred events in a loop.
Afterward come transaction callbacks, parallel cleanup, ON COMMIT actions,
pending file syncs, notification work, and serialization checks. Eventually the
commit record is flushed when required; synchronous replication can add a wait.
The transaction is subsequently removed from the running transaction array and
locks are released. These are distinct stages after a SQL guard.
[Pinned commit implementation](https://github.com/postgres/postgres/blob/7885b94dd81b98bbab9ed878680d156df7bf857f/src/backend/access/transam/xact.c),
[pinned deferred-trigger implementation](https://github.com/postgres/postgres/blob/7885b94dd81b98bbab9ed878680d156df7bf857f/src/backend/commands/trigger.c),
[pinned visibility bookkeeping](https://github.com/postgres/postgres/blob/7885b94dd81b98bbab9ed878680d156df7bf857f/src/backend/storage/ipc/procarray.c).

Relevant positions in the **hashed** `xact.c` are deferred triggers at 2212,
portals at 2219, callbacks at 2230, ON COMMIT actions at 2261, notification work at
2279, serialization check at 2289, interrupt hold at 2292, transaction-timeout
disable at 2306, `RecordTransactionCommit` at 2315, and
`ProcArrayEndTransaction` at 2339. Within `RecordTransactionCommit`, WAL flush is
at 1481 and synchronous-replication wait at 1536. These line numbers belong to
the retrieved bytes; a different source hash requires its own review.

`finish_xact_command` disables the active statement timeout **before** calling
`CommitTransactionCommand`. Commit processing later disables the transaction
timeout before the durable commit call, with interrupts held during that part
of cleanup. Timeouts still help bound some earlier work and detect unhealthy
sessions. They do not establish a maximum guard-to-flush/visibility/acknowledgement
delay or guarantee rollback after a client gives up.
[Pinned frontend implementation](https://github.com/postgres/postgres/blob/7885b94dd81b98bbab9ed878680d156df7bf857f/src/backend/tcop/postgres.c),
[PostgreSQL timeout settings](https://www.postgresql.org/docs/17/runtime-config-client.html).

This ordering is consistent with later pre-commit failures and uncertain client
outcomes. A full notification queue can fail a transaction during commit;
notification processing has its own insertion lock. A disconnect after local
commit cannot undo that commit. Neither a return value from the mutating
function nor a successful guard is yet a committed response.
[NOTIFY documentation](https://www.postgresql.org/docs/17/sql-notify.html),
[pinned notification implementation](https://github.com/postgres/postgres/blob/7885b94dd81b98bbab9ed878680d156df7bf857f/src/backend/commands/async.c).

## Initial supported client contract

Use an explicit transaction, one admitted mutation, and a separately transmitted
standalone `COMMIT` or `COMMIT;`. Restrict whitespace to a specified ASCII byte
set and case folding to ASCII; locale-sensitive Unicode normalization must not
expand the allowlist. Reject NULL, comments, additional semicolons/statements,
Unicode whitespace, `END`, `COMMIT WORK`, `COMMIT AND CHAIN`, prepared transaction
forms, transaction control inside a procedure, and implicit auto-commit. These
are intentional compatibility restrictions, not claims that other PostgreSQL
syntax is invalid. [COMMIT syntax](https://www.postgresql.org/docs/17/sql-commit.html).

Simple-query messages can carry multiple statements. Extended Parse accepts one;
Sync can commit implicitly, while leaving a BEGIN-opened transaction open. Test
the actual driver's wire sequence, preparation and pooling behavior; a Python
`.commit()` call alone is insufficient evidence. Start without pipeline mode.
Await the commit response and final transaction status; an earlier function
response is provisional.
[Frontend/backend message flow](https://www.postgresql.org/docs/17/protocol-flow.html),
[libpq pipeline mode](https://www.postgresql.org/docs/17/libpq-pipeline-mode.html).

Require the actual authenticated worker session, exact pinned owner/run
capability, read committed isolation, and `synchronous_commit=on` at admission
and in the guard. Require reviewed server durability settings including
`fsync=on`; checking one user-settable GUC is insufficient. `synchronous_commit`
controls acknowledgement requirements, and `off` can acknowledge data that a
crash subsequently loses. Replication settings and provider guarantees need a
separate recorded review; upstream documentation is not proof of hosted
configuration. [WAL configuration and durability modes](https://www.postgresql.org/docs/17/runtime-config-wal.html).

The initial transport must have no allocated backend temporary schema and no
holdable cursors at admission **and** in the guard. Use fresh sessions where
necessary; dropping a temp object is not proof that the backend never allocated
its temporary namespace. `pg_cursors` includes SQL, protocol, and SPI cursors,
including internal cursors, so reject the actual holdable property rather than
assuming every cursor is user-created. This closes specific extra user-code
paths; it does not bound core commit work. [Cursor view](https://www.postgresql.org/docs/17/view-pg-cursors.html).

The database normally grants TEMP to PUBLIC. Revoking a direct worker TEMP grant
does not remove its PUBLIC-derived permission. Do not change the shared/project
database PUBLIC ACL to make this research pass. Detect forbidden session state
and fail closed instead. Object ownership and role membership can also convey
privileges; direct ACL inspection alone is incomplete.
[PostgreSQL privilege rules](https://www.postgresql.org/docs/17/ddl-priv.html).

The COMMIT text says nothing about earlier separately transmitted commands.
The controlled client should send only the reviewed transaction sequence, but
that client policy must not be presented as a database-enforced prohibition of
all SQL. For example, TEMP/cursor rejection does not exclude an earlier NOTIFY
or all extension callbacks. Restrict role authority and validate catalog/session
state, while preserving the documented unbounded post-guard timing limitation.

## Guard, catalog, and lock requirements

1. Perform dynamic checks inside the actual deferred trigger body. Forcing
   `SET CONSTRAINTS ... IMMEDIATE` runs pending checks early, so fail closed on
   that query form; do not mark a caller-controlled GUC as proof of commit.
   Do not put dynamic freshness in an AFTER trigger's `WHEN`: its condition
   decides whether to queue the event at the row change, before deferred firing.
   Test a forced check followed by a delay and attempted COMMIT. Trigger names
   only order triggers for the same event/relation; an alphabetically late name
   does not create a global final trigger.
   [Constraint timing](https://www.postgresql.org/docs/17/sql-set-constraints.html),
   [trigger ordering and cascades](https://www.postgresql.org/docs/17/trigger-definition.html).
2. Bind the trigger relation, operation, identity, exact pending command, and
   expected event count. A receipt update must not inadvertently requeue the
   same guard forever. Failures must roll back the private journal, projection,
   source pins, and head together. A returned provisional row is not published.
3. Read the real database clock immediately before the freshness decision and
   retain that check time. Do not use `now()`, transaction-start or
   statement-start timestamps, a caller clock, or a test override as authority.
   Freshness requires both source age and future-time/skew rules; a trusted
   retained digest proves byte identity, not provider truth.
   [Database time semantics](https://www.postgresql.org/docs/17/functions-datetime.html).
4. Freeze and verify the package's callable signatures/bodies, function owner
   and security attributes/search path, effective execute permissions, schema
   privileges, table/column definitions, constraints, unique indexes, policies,
   trigger definitions/enabled modes, role attributes/membership, and the
   expected private readback surface. Include every helper and admission/guard
   function. A hash of function bodies and PostgreSQL major version alone is
   not this catalog/ACL contract. Resolve defaults and inherited/PUBLIC grants.
5. Keep worker roles distinct from owners/installers, without table-write,
   schema-create, trigger-create, ownership, privileged SET, or bypass powers.
   Revoke default PUBLIC execute for new private functions in their creation
   transaction; grant only reviewed entry/readback interfaces. Qualify object
   references and use a fixed safe function search path with `pg_temp` last.
   Never trust caller-set role labels or custom settings.
   [Safe SECURITY DEFINER functions](https://www.postgresql.org/docs/17/sql-createfunction.html).
6. Hold the relevant run/head, lease/fence, source-pin and retained-prior locks
   in a documented deterministic order through transaction completion. Require
   exact owner, command ID and wire hash, expected head revision, fence/lease,
   prior digest, and source/package binding again in the guard. Competing writers
   must observe the completed prior transaction before advancing a fence/head.
   [Lock lifetimes and conflicts](https://www.postgresql.org/docs/17/explicit-locking.html).

This lock contract prevents concurrent conflicting authority from advancing
while an accepted transaction holds its locks. It does not stop wall-clock lease
expiry after the guard, nor make a source price remain current. A subsequent
decision needs fresh source and lease admission again. Current native work
remains paper/offline; transaction signing and live trade submission are separate
future authorization and freshness boundaries.

An upstream source tag, server version string, and package SQL hash do not prove
that a vendor image has the same binary, patches, extensions, callbacks or
settings. Pin the tested image digest and server metadata separately. Future
hosted admission must verify the exact Dashboard project and owner, TLS identity,
transport/pooler behavior, installed catalog contract, role authority and
durability configuration without inspecting another project's contents.

## Unknown COMMIT outcome and replay

After COMMIT is sent, a timeout, cancellation attempt, disconnect, or missing
acknowledgement is an **unknown result**. Preserve the original command ID and
canonical bytes; do not allocate a new ID, reconstruct evidence, or infer absence
from a lagging replica. Cancellation is asynchronous and may arrive after the
target command finished.
[Cancellation and message completion](https://www.postgresql.org/docs/17/protocol-flow.html#PROTOCOL-FLOW-CANCELING-REQUESTS).

Reconcile through the exact reviewed private owner/run readback on a verified
authoritative connection. A found committed request/receipt must match the
original wire hash and relevant revision/package binding. Readback should remain
available after lease expiry because it resolves past delivery, not new trading
authority. A conflicting ID/request must fail. A confirmed absent result may
permit resubmission of the **same** ID and bytes under the separately reviewed
admission/replay policy; an unresolved readback keeps the worker closed. Report
accepted, rejected, and unknown outcomes distinctly.

## Required offline acceptance and deeper research

The following are required tests or evidence to collect. They are not test
results claimed by this document. Use only owned credential-free fixtures and
task processes; do not inject faults or change roles in hosted/shared systems.

| Priority | Test/evidence | Required observation |
| --- | --- | --- |
| P0 | Fresh valid request, standalone explicit COMMIT | Exact atomic private receipt/head/projection/pin install; only committed readback is published. |
| P0 | Fresh at entry, expired before deferred guard | COMMIT fails and all private rows remain unchanged. Cover source and lease separately using real database time. |
| P0 | Force constraints early, then delay | Early check cannot authorize a later commit; unchanged rows. |
| P0 | Full unsupported transaction-form matrix | Multi-statement buffers, implicit Sync/autocommit, comments, Unicode whitespace, END/CHAIN/2PC/procedure control fail closed. Run actual simple and extended clients. |
| P0 | Catalog/session/identity tampering | Wrong role, owner membership, altered trigger/index/helper/ACL, unsafe isolation or durability mode, fake clocks, temp schema and holdable cursor reject. |
| P0 | Two sessions compete on retained run/fence/head | Real synchronization barriers demonstrate lock wait, exact prior/revision checks, and no conflicting install. |
| P0 | Lost acknowledgement: committed and rolled-back cases | Same original ID/wire resolves exactly once; no new-ID retry, duplicate economic change or stale-replica absence assumption. |
| P1 | Trigger recursion and later pre-commit errors | Guard event count is bounded; any pre-commit failure leaves the whole private change absent. |
| P1 | Delayed work after a fresh guard | Isolated fault injection demonstrates the final-time limitation or catalog/session rejection of the attempted extra user-code path. Never report it as a hard tail bound. |
| P1 | Actual Python driver and pooler protocol | Pin driver/libpq versions; capture sanitized BEGIN/entry/COMMIT and response/status evidence, including failure recovery. Do not assume context-manager defaults. |
| P1 | Guard-to-visibility/acknowledgement measurements | Report distributions under controlled contention/faults with image/config provenance. Measurements support operational margins, not absolute guarantees. |
| P1 | Vendor/source/config review | Verify exact tested binary/image, extensions and callbacks, durability settings, package/catalog lock/fingerprint coverage, and primary readback routing. |

The remaining research should explicitly resolve what final-time freshness the
product needs, how its age budget is divided across acquisition, decisions,
admission and commit, and how an old-but-atomically-committed paper event is
represented. Assess whether a conservative margin and worker stop policy meet
that requirement; do not label that statistical or operational policy a proved
deadline. Keep hosted native admission, restoration and release gates open until
their own end-to-end evidence exists.
