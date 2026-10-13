# Guarded original-v2 native laboratory interface

This is a separate offline research contract after the complete original-v2
semantic proof. It does not modify the v5 package, production schema, runtime
worker, credentials, grants, migrations, leases or activation settings. The
following interface is frozen for the parallel decoder/readback investigation.
Its guarded implementation passes20 actual owned PostgreSQL cases; broader
restoration, retention, provider/runtime and hosting joins remain separate gates.

The private `vn_portable_native_research` package uses the same limited fixture
installer as the complete semantic laboratory and distinct fixed LOGIN fixture
worker roles. A private held binding maps the actual `session_user` to exactly
one owner/run. No caller may provision its owner binding or infer authority from
an owner UUID, saved state or a restored checkpoint. Clients receive only the
reviewed entry-point capabilities; helpers and every raw table remain private.

The initial entry points are:

- `create_run(owner,run,worker,lease_seconds)` creates the empty revision-one run
  and first fence with the genuine server clock and the private actor binding.
- `heartbeat(owner,run,worker,fence,lease_seconds)` renews only the matching
  unexpired worker/fence under the held run/actor locks.
- `commit_command(owner,run,worker,fence,original_wire)` accepts the original
  compact v2 request. Exact owner/run/ID/hash replay lookup precedes stale source,
  lease and revision checks; changed bytes or scope are refused. It composes the
  existing complete semantic entry once and atomically retains the original
  command, all immutable dependency pins, receipt, events and projections.
- `get_command(owner,run,command_id,expected_command_sha)` observes the original
  retained request/receipt for uncertainty resolution. An absent ID is distinct
  from a conflicting digest. A response prepared before COMMIT does not prove a
  committed outcome; loading/retrying a new ID is never reconciliation.
- `read_checkpoint(owner,run,revision,expected_manifest_sha)` returns the original
  manifest wire, all thirteen referenced component wires in manifest order,
  original command ID/hash and semantic-validator/native-package digests. Pending
  request and closed/active status remain explicit. Readback does not grant a
  lease, capability or permission to install/activate a worker.
- `lookup_identity_ids(owner,run,current_revision,current_manifest_sha,ids)`
  provides the exact asked canonical UUID set, bounded to128 unique IDs, under
  the held current-head/actor/package locks. Used IDs carry their original
  account/position/risk kind and decimal birth revision. Unasked IDs are unknown;
  a client must not infer unused membership. Historical heads and a caller's own
  uncommitted head are refused. Display names may repeat. The thirteen-slot state
  does not contain the historical used-ID ledger; neither fresh nor active-only
  client indexes establish history or permit native continuation.

Receipt format is `ga-portable-native-receipt-lab-v1`, with exact owner/run/command
UUIDs, original command SHA256, revision as a decimal string, original manifest
SHA256, original model/assessment headers, semantic validator SHA256 and native
package/catalog SHA256. An entry-point result remains pending until its separate
transaction COMMIT; independent getter observation resolves a lost reply.
Raw manifest/dependency aggregate remains capped at262144 bytes. The separately
versioned readback envelope cap is589824 bytes for JSON escaping plus metadata;
old v5/native-client caps retain their original meaning.

The native package fingerprint must bind exact schema/table/column/constraint/
index/trigger/function definitions, owner/ACL/default-ACL and relevant actor role/
membership metadata, extension metadata and PostgreSQL server patch/build, plus
its original semantic function-source contract. Caller-controlled clocks,
configuration settings, search paths or permission claims are not authority.
No actor receives schema/table creation or raw dependency/identity/journal writes.
A private immutable per-command pin row binds each of the thirteen referenced
blocks. Full original continuation and original-ID receipts remain retained.
No deletion/archive operation is provided before restoration, original pending
request/Stop lookup and dependency-safe retention are independently accepted.

## Commit processing and durable outcome are separate

A check at function return can expire before a later client COMMIT. A deferred
constraint trigger alone can be forced earlier with `SET CONSTRAINTS IMMEDIATE`.
The proposed laboratory guard therefore investigates only a standalone explicit
`COMMIT`/`COMMIT;` frontend message, with case and ASCII whitespace normalization.
Implicit commits, multi-statement batches, force-immediate constraints, other
transaction-control forms and prepared transactions are refused. A temporary
schema or holdable cursor is refused as defense in depth without changing the
database-wide PUBLIC TEMP grant. Read committed, synchronous_commit on, fsync on
and session_replication_role origin remain required. These are laboratory
constraints, not a production guard.

PostgreSQL17 documents that constraint triggers can be forced early and that
`current_query()` contains the client query message, potentially multiple
statements. Its pinned REL_17_6 source returns `debug_query_string`, sets it from
simple/extended query source, and fires deferred triggers before cursor close,
transaction callbacks, ON COMMIT work, notifications/SSI, WAL flush and final
visibility. Statement/transaction/client deadlines do not establish a hard
last-check-to-durable-commit bound or prove that a timeout rolled back. This guard
can at most prove freshness during recognized commit processing. Lease/fence
locks prevent a competing replacement while held; wall-clock expiry still occurs.
A lost/late commit reply needs the original-ID independent readback.

Primary sources: [SET CONSTRAINTS](https://www.postgresql.org/docs/17/sql-set-constraints.html),
[session information](https://www.postgresql.org/docs/17/functions-info.html),
[REL_17_6 current_query implementation](https://github.com/postgres/postgres/blob/REL_17_6/src/backend/utils/adt/misc.c),
[transaction processing](https://github.com/postgres/postgres/blob/REL_17_6/src/backend/access/transam/xact.c),
[frontend query processing](https://github.com/postgres/postgres/blob/REL_17_6/src/backend/tcop/postgres.c).
Native/decoder/restoration/retention/hosted authority stays false until its
corresponding actual package/capability/transaction/recovery tests pass. Even a
successful temporary-memory fixture will not prove power-loss durability,
representative provider authenticity, final-visible-instant freshness, hosted
latency/cost, continuous operation or profitability.

## Exact readback records and actual acceptance

The receipt has exactly17 keys: format, owner_id, run_id, command_id,
command_sha256, revision, manifest_sha256, model_format, assessment_format,
semantic_validator_sha256, native_package_sha256, record_observed,
pending_until_commit, guard_observed_at, final_visible_instant_freshness,
restoration_authority and hosted_authority. Its observed timestamp is normalized
UTC with exactly six fractional digits and `+00:00`. Pending receipts have a
null timestamp and record_observed=false; observed original receipts have the
recorded commit-guard timestamp and pending_until_commit=false. All three
freshness/restoration/hosting authority flags remain false.

Checkpoint envelope format is `ga-portable-native-checkpoint-readback-lab-v1`,
with exactly format, manifest_wire, component_wires, receipt, current_revision,
current_status, pending_command_authority, restoration_authority and
hosted_authority. Status is created/running/paused/risk_halted/stopped/failed.
Historical receipt revisions may be below the current revision; this grants no
permission to prepare against an old head. The manifest and ordered thirteen
component wires are the original inner canonical numeric wires. The outer
JSONB text is bounded UTF-8 JSON and is not lexically compact canonical JSON.

Command getter format is `ga-portable-native-command-readback-lab-v1`.
Absence returns only format/found=false. Observed results add only receipt and
original_command_wire. Another owner's existing ID and a genuinely absent ID
produce the same scoped absence result. Identity lookup format is
`ga-portable-native-identity-lookup-lab-v1` with owner_id, run_id, revision,
manifest_sha256, native_package_sha256, identities, restoration_authority=false
and hosted_authority=false. Each asked ID is either `{used:false}` or
`{used:true,kind:account|position|risk,born_revision:decimal-string}`.

The actual20-case suite passes with zero skips in83.614 seconds on the pinned
owned PostgreSQL17.6 arm64 fixture. It covers atomic original journal/head,
thirteen pins, events and projections; normal scope/private capability denial;
unchanged exact replay before stale fence/lease/status/source; lost-reply original
wire readback; own uncommitted getter/oracle/replay refusal; complete late rollback;
one new command per transaction; genuine stale/future source and delayed source/
lease expiry; recognized mixed-case ASCII COMMIT forms and refused session/forms;
catalog constraint/index/owner/ACL/role/transitive membership/parameter metadata
drift before admission and after the function reply; held run/actor/package locks;
benign temporary catalog sentinels; exact scoped head-bound identity queries;
historical checkpoint reads after lease expiry; and reserved Stop command/byte
capacity. All rejected operations compare every mutable native, semantic,
dependency and identity table before and after. No sentinel performs private
writes, permission changes or external operations. No image, database-wide PUBLIC
TEMP privilege, shared tool/process/account or hosted setting is changed.

The command limit is127 ordinary commands with the128th slot reserved for Stop.
Logical retained wire charges are capped at8388608 ordinary bytes with1318912
additional reserved Stop bytes (maximum9707520). Original command wire is retained
once in the semantic journal; native pins/receipts bind it by exact ID/hash/revision.
The charge includes original command, newly retained component wires, full history
and events, replacement active projection and an8192-byte row allowance. This is
logical accounting; actual tables/indexes/TOAST/WAL, power-loss durability and
hosted storage cost are unmeasured. Full original history, identities, pins and
Stop receipts remain retained and no pruning operation exists.

The exact genuinely timed held-position Stop trace remains a separately opt-in
clock-boundary acceptance until recorded; ordinary CI does not wait for a future
bar. Catalog binding records server-reported patch/build and extension metadata,
not binary equivalence with the cited upstream source. Current actor capabilities
do not include a replacement lease-acquisition API. Original v2 configuration
continues to name `synthetic-exact-fixture-v1`; real Jupiter acquisition requires
an explicit forward runtime/configuration/model/transport profile, at least v3,
with honest source labeling and an authenticated acquisition/continuation corpus.
Original v2 must not be relabeled or deployed as a live-provider runtime. Native
production admission, restoration/activation, retention deletion and hosting
authority remain closed.
