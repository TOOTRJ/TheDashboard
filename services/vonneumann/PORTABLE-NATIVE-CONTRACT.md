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

## Rejection-only direct native source-clock correction

The historical20-case acceptance predates a direct source future-anchor check.
Original worker-relative two-second receipt/source allowances can otherwise
compose to an estimated source four seconds ahead of the database clock. Native
admission now captures one genuine server time after the run lock and bounds the
latest receipt and estimated source directly to that observation plus two seconds.
Bootstrap checks the latest document receipt as well as the oldest deadline.
Those private anchors are retained beside the deadline and are checked again at
the final function observation and recognized COMMIT guard observation. No caller
clock GUC, changed original v2 policy/header, or longer age window is introduced.

The corrected23-case actual suite passes with zero skips in126.398 seconds. Three
new cases exercise the composed four-second estimate, a fresh first bootstrap
document hiding a later future document, and an allowed direct two-second estimate.
The original20-case receipt remains unchanged; the exact corrected sources and
results are recorded separately in `research/portable-native-clock-acceptance.json`.
Decision/recovery history-document receipt composition is being hardened in a
subsequent rejection-only slice before any broader native source acceptance.

The subsequent history correction includes every supplied history document in
the same genuine native clock bounds: the earliest receipt can shorten the
five-second admission/COMMIT deadline, and the latest receipt can trigger the
direct two-second future refusal. This applies to decision/recovery as well as
bootstrap, preserving source-age limits and all original v2 semantic headers.
The corrected24-case actual suite passes with zero skips in75.576 seconds. A
normal refusal regression checks stale/future receipt tags even in invalid unused
control history before any semantic write. Complete value-valid decision/history
clock-refusal and held-position Stop proof is separately gated by the genuinely
timed bar probe. Sources/results are recorded in
`research/portable-native-history-clock-acceptance.json`; older source-bound
receipts remain unchanged and do not establish this later correction.

## Genuine next-bar held-position Stop acceptance

The separately opt-in probe now passes completely against the final all-history
clock package. Its exact SQL SHA256 is
`76e23d44a296c838238e5545c9ea498eb86d2ac5caee9798236aee1f8a5bf5c4`,
and the accepted historical probe source SHA256 is
`c505e18fb3c5403d59f7f16aeed1f4fc4f84d26439af1ac7bb380f51026cf052`.
`research/portable-native-genuine-stop-acceptance.json` retains the complete
eight-command original-ID/hash/manifest/guard-time trace and fixture identity.
The run takes664.320501 seconds, including the real wait from the04:00 UTC bar
to the04:15 UTC bar on2026-10-13. This is a timed correctness experiment, not a
latency, throughput, fill, hosted-cost or profitability measurement.

The worker starts a genuine-clock warming/evaluating cohort, renews only its
original60-second lease31 times, waits for the next real completed bar plus the
unchanged completion margin, creates the original crossover signal, and opens
eight positions at a later actual quote. It then admits data-free Stop while
retaining exact positions, accounts and reserve. Stop is independently observed
at04:15:13.476886 UTC. The decoded native active projection equals the original
owned checkpoint, including its original checkpoint/model headers. An exact
original Stop replay changes no row. Final status is stopped, revision9, eight
commands, an unexpired lease, and722093 logical retained bytes within the original
reserved budget. The exact UUID-owned fixture and running PID record are cleaned.

Every accepted receipt/input clock comes from actual server UTC or the actual
process monotonic clock. No future timestamp, seeded native head, replaced
receipt or relaxed source/lease/guard rule creates the accepted trace. The source
label remains `synthetic-exact-fixture-v1`, and all production admission,
final-visible-instant, restoration, retention-deletion and hosting authority
flags remain false. The fixture uses literal local provider documents and no
provider, wallet, remote account or other process operation.

Earlier probe attempts that failed their driver type/header assertions are not
accepted evidence. A separate timing-sensitive future-history experiment also
did not establish refusal: by native admission its proposed timestamp had aged
into the allowed genuine-clock window, so acceptance was correct. Original24
clock regressions remain the source-bound refusal evidence; this successful
positive trace does not close additional real-provider/tail/authentication gates.

Ordinary CI never waits for a real bar. Explicit reproduction requires the locked
worker interpreter, cwd `services/vonneumann`, both
`DASHBOARD_ISOLATED_POSTGRES_TESTS=1` and
`DASHBOARD_PORTABLE_NATIVE_REAL_BAR_PROBE=1`, and
`-m research.run_portable_native_bar_probe --maximum-seconds 970 --output
/private/tmp/<task-owned-output>.json`. The30..970-second deadline is enforced;
the output must be task-owned temporary storage. The optional running record
identifies only this probe's PID so a SIGINT can execute its owned cleanup.
No shared daemon/tool/process is stopped or reconfigured.

## Later CLI output-ownership repair

The accepted genuine-Stop receipt above remains historical evidence for its
recorded SQL and complete probe-source hashes. Its original probe source is
retained at commit `52a4929bce065e8438d8270d360966b88b46ec8d`. A later repair
changes only the CLI's local output rights; it does not rewrite that receipt,
relabel the previous trace, or establish a new timed/native acceptance. The exact
`run()` function source remains byte-identical, with SHA256
`25153c91f462114c6caf73518cf8adf6db925fb03c6ab387b8a575ae752e557e`.
SQL, assertions, genuine-clock bounds and source/lease rules remain unchanged.

Both explicit opt-ins and the 30..970-second bound are checked before any file
operation. Output paths must be canonical absolute `.json` paths beneath
`/private/tmp`; traversed parents are pinned through no-follow directory
descriptors, and nested parents beneath that system temporary directory must
belong to the current user with private permissions. The output and its
`.running.json` sibling are exclusively created as mode0600 regular files.
Parent identities, leaf identities, ownership and private modes are checked
before and after publication and again during final cleanup. Cleanup removes
only this invocation's matching created PID record or unpublished output through
the held parent descriptor. Existing or replaced objects are preserved; the
helper never changes their permissions. The output reservation is empty while
pending, and an incomplete or failed output grants no acceptance or authority.

Thirteen ordinary, credential-free tests cover absent opt-ins, invalid deadlines,
existing-file collisions, symlinks, noncanonical paths, nonprivate parents,
exclusive mode0600 creation, failure cleanup, changed leaf identities/modes,
renamed parents and staged replacements after publication. They also compare the
frozen `run()` source hash. These are local file-rights tests, with a stubbed
runner; they do not execute a real-bar wait, SQL fixture or provider request.
The boundary assumes a trusted local operator and is not an OS sandbox against
a hostile process under the same user. Observed replacement causes refusal,
and uncertain command outcomes still require reconciliation by the original ID
rather than a fresh-ID retry.
