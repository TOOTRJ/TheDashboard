# Original portable-v2 restoration contract — offline research, 2026-10-12

`portable_restoration_wire.py`, `portable_restoration_graph.py` and
`portable_restoration.py` reconstruct the original
`ga-portable-provider-model-research-v2` GA-only two-EMA research state. They do
not change economic formulas, selection, mutation, distributions, RNG policy,
model/assessment formats, or the thirteen-slot checkpoint format. They do not
install a production runtime, read credentials, issue a lease, activate a worker,
submit a command, retry an uncertain write, or authorize trading.

## Independent trust boundary

The caller must obtain `ExpectedHead` from a separately authenticated,
owner/run-scoped committed native reader and an independently verified operator
package binding. It supplies the exact owner, run, revision, manifest SHA256,
original command ID/SHA256, accepted semantic validator SHA256 and installed
native catalog SHA256. Do not construct it from the receipt being checked or
from arbitrary browser JSON. A Python value, matching hash, receipt boolean or
test fixture cannot authenticate a server or prove historical semantic admission.
The pure test bindings intentionally use synthetic digests and prove no such
acceptance. The native reader/package join remains a separate gate.

The original semantic and native contracts must admit the same versioned model,
assessment, prior chain and historical identity ledger. A seed, fabricated prior,
hash-only head or provisional return before COMMIT does not satisfy this boundary.
Operator checks must bind the reviewed worker source/dependency package as well
as the installed SQL catalog; a matching model version string alone cannot prove
that code has not changed. Preserve original v2 records under original semantics.

Every decoded/restored result reports `restoration_authority=false` and
`hosted_authority=false`. Checkpoint readback also reports no pending-command
authority; restored model state reports no restored lease or history ledger.
The decoder constructor prevents accidental unchecked checkpoint DTO creation.
These local object checks are validation boundaries, not credentials or a Python
process sandbox.

## Wire and reconstruction rules

The native readback envelope is ordinary UTF-8 PostgreSQL JSON, bounded at
589,824 bytes. Its outer field order/spacing is immaterial. Duplicate/unknown
keys, untagged numbers, unknown formats, malformed UTF-8 and oversized/deep
containers are refused before model construction. Revision fields are canonical
decimal strings, UUIDs canonical lower-case strings and SHA256s exactly 64
lower-case hexadecimal digits. Boolean/integer aliases are refused.

The manifest is at most 65,536 bytes; each component at most 196,608 bytes; the
manifest plus all thirteen component wires at most 262,144 bytes. Inner wires
remain byte-exact canonical tagged numeric UTF-8 JSON. No JSONB reserialization,
rounded JavaScript number or new digest substitutes for the original bytes.
SHA256 binds each wire to its original ordered reference. All thirteen slots
must be present once, in original order: configuration, optimizer, cohort,
eight ordered member genomes, source bars, EMA. Stable slots have generation
zero; variable slots use the original model generation. Scope, reference type,
kind/entity/generation, source model format and revision must all agree.

The exact 17-key observed receipt must bind every independent expected identity
and digest, original model/assessment formats, `record_observed=true` and
`pending_until_commit=false`. Its guard time must be a valid UTC timestamp in
`YYYY-MM-DDTHH:MM:SS.ffffff+00:00` form. It cannot claim final visible-instant
freshness, restoration or hosted authority. This timestamp is a recorded native
guard observation, not a guarantee that the checkpoint is presently fresh.

After bounded primitive/source/economic/cohort/mirror validation, reconstruction
assembles all original configuration, reserve, accounts, held positions, EMA
values/count/previous values, source bars/epoch/watermark, risk latch/counters,
pending decisions, member cursors/assessments, cohort genomes/results and search
state. The graph decoder permits only six reviewed fixed classes: GA strategy,
search streams, selection cohort, genome, evaluated candidate, evaluation cohort.
It preserves ordered maps, aliases and original object field layouts. Missing,
forward or cyclic references and unreviewed classes/tags are refused.

The Python MT19937 words, cursor and optional Gaussian cache are installed with
the builtin fixed allocator plus `setstate`; neither RNG initialization/seeding,
bootstrap, fresh identifiers, optimizer evolution nor ask/tell runs during
loading. Search seed/algorithm/epoch/mutation counter and all primitive mirrors
must agree. A read-only original encoder confirms the exact graph round trip.
Only CPython 3.12.14, NumPy 2.5.3 and cmaes 0.13.1 under the reviewed original
evidence header are admitted. Supporting another runtime requires explicit new
acceptance, not silent header rewriting.

Historical readback may be decoded for inspection only when independently
requested. It cannot prepare continuation. A current checkpoint must equal the
independently held current revision and status; there is no automatic rewind.

## Preparation and pending commands

The original public producer requires its complete in-process
`SimulationLedger`. The restoration adapter does not invent one from active
checkpoint rows. The separately authenticated native `lookup_identity_ids`
capability supplies an exact, bounded set of up to 128 offered UUIDs bound to
the same current owner/run/revision/manifest/catalog. Missing or extra lookup
entries, an unknown/stale head, mismatched package or an unchecked allocation
refuse; there is no default `unused=false/true` fallback. An empty allocation set
is valid for a control that needs none. Previously retired IDs remain used.
Names may repeat; no historical name uniqueness is invented.

The adapter stages explicit original frame/history/UTC/monotonic evidence using
the original source validators, then invokes the unchanged original-v2
`_prepare_protective`, `_prepare_decision` or `_prepare_control` kernel. It does
not read a clock, call a provider or create an allocation. The offered allocation
tuple must exactly match the checked oracle set. The native transaction must
still enforce the current head, global historical ID uniqueness, lease/fence,
source freshness and final effects atomically; a preparatory lookup cannot
guarantee that the head remains current until COMMIT.

`prepare_restored_transport` retains the original prior manifest digest and
component digest set and emits only the following original changed components.
It preserves every original operation, history record, assessment/evaluation,
source input and event. Ordinary 196,608-byte and reserved Stop 262,144-byte
limits include the original tagged wire, JSONB representation and expanded
numeric JSON. It returns bytes, never a submission or accepted receipt.

`PendingOriginalRequest` captures the exact saved original command UUID, scope,
wire/hash, resulting manifest/hash and revision. `reconcile_original_request`
interprets only a separately authenticated getter for that same original request.
An observed receipt must return the byte-exact original request and independently
bound package/semantic provenance. An absent lookup remains
`not_observed_uncertain`; it grants no retry or rollback conclusion. A different
UUID/wire/hash is refused. The loader generates no replacement ID or automatic
write/retry. Stop retains holdings, cash and risk state and cannot turn a stopped
checkpoint into a running one.

## Acceptance and remaining ordered joins

The focused offline suite checks exact full next-candidate and compact-command
wires across two generations, both clone/crossover mating, mid-window and pending
signals, early terminal completion, pause/resume with an explicit search restart,
risk halt/recovery, increasing original source cursors and Stop with eight retained
positions. It also checks retired identity reuse refusal, historical inspection,
original uncertain-request reconciliation, duplicate/unknown/truncated/oversized
wires, type/hash/scope/semantic/catalog/receipt/authority rejection, graph/runtime
forgery, and denied configuration/provider/database/network imports. These are
literal synthetic-provider experiments, not provider authenticity, native
durability, profitable results or hosted throughput.

Acceptance receipt: the 15 focused cases pass with zero skips in the isolated
locked worker runtime (90.697 seconds). Five traces contain 78 exact full/compact
next-command comparisons; the resulting second generation includes both clone
and crossover mutation. Run with a sanitized child environment:

```sh
env -i PATH=/private/tmp/dashboard-locked-worker/bin:/usr/bin:/bin \
  PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 \
  PYTHONDONTWRITEBYTECODE=1 /private/tmp/dashboard-locked-worker/bin/python \
  -m unittest tests.test_portable_restoration -v
```

The source import boundary test separately rejects dotenv/private configuration,
live provider/repository clients and network calls. Pure source/database protocol
validators are allowed; no database driver or credentials are imported by the
restoration modules. The local runtime path is a fixture dependency, not a
production deployment path.

Next joins must proceed in this order:

1. Install the reviewed guarded native laboratory package under its limited
   installer. Independently verify catalog/owner/role/grant and semantic hashes,
   committed current head and accepted original command under scoped reader
   credentials; pass those expected bindings to this decoder. Exercise all 13
   original pins, real independent COMMIT readback, foreign/missing getters,
   current-head identity oracle, stale head, reused retired IDs and original
   request reconciliation. Loading remains closed with every authority false.
2. Define a forward real-provider runtime profile. Original v2 configuration
   explicitly retains `source=synthetic-exact-fixture-v1`; provider-shaped fixture
   documents do not authorize relabeling it as live Jupiter data. Version the
   model/config/source/assessment/checkpoint/command/SQL semantic/projection and
   reader contracts coherently. Specify acquisition authenticity, original raw
   response retention, clock/process epoch policy, rate/error/staleness behavior,
   contiguous completed-candle warmup and immutable history/price provenance.
   Keep original v2 journals readable without mutation or retrospective rescoring.
3. Implement and accept retained archive/receipt/original-ID lookup and all
   dependency pins before deleting evidence. Preserve the append-only identity
   ledger and package/runtime/semantic manifests needed for future restoration.
   Measure table/index/TOAST/WAL/pin/history growth and held-position Stop reserves;
   choose hot/archive limits and bounded pilot duration from those measurements.
4. Join the explicit new projection with old/new UI readers, lost-ACK controls,
   pending Stop and session replacement. Only then prepare exact-target closed
   deployment, writer-drain/rollback steps and bounded Railway restart/multi-window
   acceptance under the approved pilot ceiling. A lease is separately acquired
   only after original pending requests and holdings are reconciled and all gates
   pass. No part of this pure restoration experiment opens that lease path.

`tests/postgres/test_portable_restoration_native.py` contains three guarded
native join cases using the separately reviewed native fixture installer,
independent accepted-head/catalog observations and scoped reader roles. They
cover original committed loading, next control wires, pending/absent/foreign
original getters, historical refusal, head-bound lookup and refused reuse of a
retired ID after restart. Ordinary discovery skips these three explicitly
opt-in cases; that skip is not native acceptance. Actual composed execution with
the defensive semantic package `fb96ac2` and native package `5603cbde` passes
all three cases, zero skips (27.457 seconds), in owned PostgreSQL17.6. The
source-critical comparisons avoid repeated whole-journal snapshots; independent
control cases still verify that loading/preparation changes no rows or lease.
Quotes use the actual laboratory server clock and retain the original native
five-second source guard. No semantic seed, clock GUC, deadline widening,
production schema or credentials are used. This establishes the guarded local
readback/restoration join, not provider authenticity, final-visible durability,
long-duration operation, production migration or hosted authority.

Independent review also found and fixed a malformed nested pending-evidence
error path. A sixteenth focused ordinary case now verifies controlled
`RestorationError` refusal for null/list/string/boolean evidence; valid original
wire semantics are unchanged.

Further substantial research is needed on authenticated provider recording and
publication-time evidence, real source/process-clock transitions after restart,
long-term version/runtime support, dependency-safe cold archive lookup, retention
cost/COMMIT tails and bounded hosted risk-response intervals. These questions
should be resolved with measured joins rather than inferred from canonical hashes.

## CI source-window choreography follow-up — 2026-10-13 UTC

This section records the earlier `d9bb9eb` test choreography. The subsequent
follow-up below supersedes its protective comparison placement; its dated
acceptance and refusal measurements remain historical evidence.

PR104 head `897ec2ad369d82ccef80b05a4bbd475f630a1a3b` executes 205 SQL4
cases in `885.928s`, with zero skips but one error in the retired-ID restoration join:
the first protective commit reaches
`portable_native_final_source_or_lease_expired`. This is a failed full-shard
result, not accepted SQL4 execution. The fixture had constructed an original
source frame before independently reading the prior native head/catalog,
checkpoint and identity oracle and cold-decoding its complete optimizer graph.
That test work consumed the unchanged five-second native source interval.

The test-only repair restores the independently observed committed prior head
and asked-ID oracle before a new original literal capture. It samples genuine
database wall time and retains the first original fractional receipt. Original
v2 requires an integral action second at or after the receipt's ceiling, so the
fixture waits on the genuine clock before observing its action time. It derives
an integral action clock from that actual observation for both frame and
DecisionInputs, avoiding the old binary64-ceiling versus datetime-rounding
one-microsecond representation edge without changing the model or adding a
future offset. The fixture's MONO relation remains synthetic; these measurements
are not real worker or cross-process acquisition-clock acceptance.

The restored protective full/compact wire equivalence is checked byte-for-byte
before the one original submission. While its committed head is
actually current, an independent installer observation binds its accepted
head/catalog/semantic contract, and a single scoped actor read captures the
original checkpoint plus current-head asked-ID oracle. The one original
decision is then submitted immediately with the exact same frame and command
ID. Complete reconstruction and full/compact next-wire comparison use the
immutable saved snapshot after native submission, off the admission critical
path. No second submission or retry occurs. The saved envelope denotes current
**at capture**, not present continuation authority at decode time. The subsequent
scoped current checkpoint read independently observes the accepted decision.
Retired-ID, stale-head and no-write refusal assertions remain intact.

The original three-case `27.457s` acceptance above remains tied to its older
source/package. The following local results are separate chronological evidence:

- Moving only the first restore before capture produces a three-case `38.795s`
  run with two passes and a correct final source-or-lease refusal on the delayed
  decision. It is not acceptance of cold restoration inside the source window.
- The saved-snapshot choreography with a floor-second receipt passes all three
  cases in `46.862s`, zero skips. Host intervals from capture staging are
  `1.935139s` for protective commit, `4.035750s` for decision commit and
  `4.514984s` through the delayed equivalence comparison. These are scoped
  observations, not throughput or native-only latency bounds.
- A same-sample fractional receipt/action attempt produces a three-case
  `15.367s` run with two passes and one original `ProviderDeferred` before any
  native pending source request; the genuine integral-action wait is required.
- Fractional receipt plus genuine action wait passes all three cases in
  `24.439s`, zero skips. A later reporting run takes `23.540s` and exposes the
  one-microsecond representation edge on the second protective before submission;
  its first protective and decision already pass native guards. That run is not
  full-class acceptance.
- The final observed-integral-action/reporting path passes the affected case
  in `17.695s`, zero skips. Actual original receipt to action wall delay is
  `0.483848s`. Independently recorded native guard timestamps are `1.646198s`
  and `2.895655s` after that same original receipt for protective and decision.
  Host intervals after action observation are `1.157909s` through protective
  commit, `2.407094s` through decision commit and `2.739567s` through the delayed
  exact equivalence comparison. The other two cases retain their preceding
  full-class acceptance; complete final-head CI remains required.

All runs use the owned cached network-none PostgreSQL17.6 fixture and locked
CPython3.12.14, and remove their exact owned container. No SQL/model/decoder,
native lease/source limit, wire version, production connection, provider request
or credential changes. Native SQL remains SHA256
`76e23d44a296c838238e5545c9ea498eb86d2ac5caee9798236aee1f8a5bf5c4`.
The prior genuine-bar Stop receipt is unchanged. This proof does not establish
cold restoration plus decision admission within five seconds, present authority
from saved snapshots, continuous hosted operation or a final-visible freshness
bound. Native/worker/resource tails, including the proposed Railway CPU budget,
still require measured acceptance; a slower host cannot extend the guard or
rebase an original receipt to compensate.

## Captured-head pair equivalence and refusal diagnosis — 2026-10-13 UTC

The next full hosted CI execution at PR104 head
`c58177afe7d22ab17b6ee21da91ec2b9e7d5a73d`, run `38357623351`, SQL4 job
`115164075775`, executes 205 cases in `869.304s`, zero skips, with one error in
the same retired-ID join, now during the original **decision** submission.
Its `portable_native_final_source_or_lease_expired` exception is the function's
final check after semantic/projection work, before the pending reply; it is not
the separately named deferred COMMIT-trigger refusal. That exception combines
source, lease and future-anchor predicates. The old traceback has no observed
guard timestamp or retained failed row, so it cannot conclusively distinguish
which predicate failed. It remains a failed full-shard result. A later local
pass does not erase it or establish a hosted latency bound.

Before editing this follow-up, one diagnostic-only execution of the unchanged
`c58177a` affected case passes in `15.654s`, zero skips. Its genuine native
protective/decision guards are `1.980503s`/`3.072967s` after the first original
receipt; receipt-to-integral-action delay is `0.941202s`. The duplicated
protective full/compact comparison takes `0.171293s`, the mandatory current
protective snapshot/oracle capture takes `0.141386s`, and original decision
submission takes `0.653094s` on this local fixture. These phase observations
explain avoidable test work; they cannot attribute the earlier CI refusal or
guarantee performance on slower or contended hosts.

The revised case is named
`test_captured_current_head_equivalence_retains_retired_ids_after_original_pair`.
Before creating a fresh original frame, the fixture saves the independently
observed actual prior head/catalog binding, its exact scoped checkpoint, and
the asked-ID oracle. It prepares and submits the original protective once,
without repeating the restored producer's graph/next-wire calculation on the
source-critical path. It then independently observes the actual committed
protective head/catalog and saves that current checkpoint/oracle before
preparing and submitting the original decision once with the identical frame.
No prospective head or provisional receipt authorizes either capture.

Only after the pair succeeds does it reconstruct **both** saved checkpoints.
Each comparison retains exact complete restored state, all thirteen original
component wires, the independently bound expected manifest and asked IDs,
and byte equality of the complete candidate and compact transport. The later
snapshot does not authorize present continuation: `is_current` describes its
independently observed head **at capture**. No saved snapshot submits, replays,
reacquires/renews a lease or refreshes a quote. A subsequent independent read
checks the actual accepted decision head. Retired historical identity,
stale-head refusal, original-ID reconciliation and no-write checks remain;
the second protective also receives its complete equivalence comparison after
its one original submission. Data-free restored controls retain comparisons
and database immutability checks before their own submissions.

The source submission helper emits fixed laboratory metadata after an original
SQL refusal and rollback. It derives the original request's source deadline
with the unchanged minimum-receipt/source-age/source-time/history formula,
observes one later native clock plus retained lease/current accepted head,
and reads the original command ID/hash through the scoped getter. This is a
**later observation**, not the failed check's clock or proof of its exact
branch. Integer diagnostic arithmetic does not replace the native timestamp
calculation. The helper re-raises the original `SqlFailure`; diagnostic or
output failure cannot conceal it. It never retries, rebases or submits a
replacement. If diagnosis is unavailable it records only a controlled error
type, without raw request/error content.

A fourth, related native case prepares one genuine original protective under
lease60, waits six genuine database seconds, verifies before first submission
that its original source allowance has elapsed while the lease remains live,
and submits it exactly once. It requires the named native source-expired
refusal, original-ID absence, unchanged accepted head and complete table
equality after rollback. The diagnostic asserts later source expiry/live lease
without claiming to have observed the failed guard instant. A separate pure
mocked error-preservation subproof makes no database call and verifies that a
reporter/output error preserves the same original exception instance; it is
not a second native submission.

The first revised four-case execution takes `25.993s`, zero skips, with the
original three cases passing; the new expiry case encounters a test-helper
`last_control_at=None` assumption before any original source preparation or
attempt. Its pair records actual native guard offsets `1.740023s`/`2.899260s`.
The helper now treats an absent prior control as no control-order wait, while
retaining the same genuine fractional receipt and observed integral action
logic. The relevant ordinary restoration module passes 16 cases in `52.863s`,
zero skips. Final four-case acceptance is recorded separately below.

This change removes duplicate proof calculations, rather than proving that
the full restored worker can complete cold reconstruction and admission inside
five seconds. The mandatory original producer, accepted-head/oracle read and
full native validation still consume the unchanged allowance. Native/resource
tail measurement remains an open runtime gate, including Railway's proposed
CPU allocation; a contended host may legitimately refuse the original. The
original semantic/model/source/decoder/SQL, native lease60/source5/future2
bounds, wire versions, all false authority flags and the historical genuine
Stop receipt remain unchanged. Native SQL SHA256 remains
`76e23d44a296c838238e5545c9ea498eb86d2ac5caee9798236aee1f8a5bf5c4`.
No provider, production database, cloud account, credential or other project's
process is accessed. A fresh complete final-head CI result is still required.

The final focused native class passes all four cases in `33.380s`, zero skips,
under locked CPython3.12.14 and the owned cached network-none PostgreSQL17.6
fixture; exact owned-container cleanup completes. Actual recorded native
protective/decision guards are `1.658530s`/`2.816193s` after the same original
receipt. Receipt-to-action delay is `0.798434s`; host intervals after action
are `0.851351s` through protective commit, `2.008753s` through decision commit,
and `2.559175s` through both delayed equivalence comparisons. The mandatory
current protective snapshot/oracle capture takes `0.151602s`.

The deterministic refusal case reports its later receipt age as `7.371844s`,
with `51.162866s` of lease remaining at that later observation; the original
ID is absent and the accepted bootstrap revision2 and complete tables remain
unchanged. The same-error/no-database-call output-failure subproof passes.
These are dated scoped measurements, not guard-to-WAL bounds, throughput
claims, cold-restoration admission or complete hosted CI acceptance.

## Explicit COMMIT followed by same-session readback — 2026-10-13

Head360d4a2's completed hosted run still fails the first original decision.
Its later diagnostic observes receipt age5.246318s and a live lease; the
protective guard is2.281214s after that original receipt. The later clock is
not the failed guard instant. The complete source-transition trace now passes,
so it does not explain this remaining restoration refusal.

The follow-up fixture submits the unchanged original protective in one ACTOR
connection, with explicit BEGIN/native call/COMMIT. The same connection then
performs the complete checkpoint and asked-ID getters in a new transaction.
Both native functions retain their actor/package/current-head checks and
same-transaction provisional-readback refusal. A separate fresh installer
connection then verifies the actual accepted current head and catalog before
preparing the decision. No SET ROLE, pooled connection, heartbeat, clock
adjustment or new native/model/decoder version is introduced. Each SQL call
still establishes its own connection as the requested fixture role; this one
call deliberately spans the two documented transactions. The final decision
load continues to use independent connections.

Exit zero and exactly two complete LF-delimited JSON records are required.
Pending first output, malformed/partial output, process timeout or a later SQL
error stops continuation. Since an error can occur after the explicit COMMIT,
the combined helper reports an uncertain original outcome and reads only that
original ID/hash through a fresh scoped getter. It preserves the original
exception and never retries or submits a decision. The added actual
post-COMMIT SELECT1/0 regression confirms the original protective is committed,
submitted once, independently readable and unchanged by the subsequent load;
there is no decision row.

All five native cases pass36.091s with zero skips. Recorded native guard offsets
are1.602325s/2.676209s after the same original receipt; actual integral-action
delay is0.773236s. Fixed laboratory host-phase timings separate model,
checkpoint, transport, original SQL submission, native readback and the fresh
operator query. They remain process observations, not the failed native clock.
The connection optimization saves one client startup; these local measurements
do not establish a hosted speedup or a five-second cold-restoration bound.
All full/compact comparisons,13 original wires, retired-ID/stale-head checks,
original reconciliation, data-free controls and unchanged native guards remain.
