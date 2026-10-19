# R3-03A2 scoped native source experiment plan

Status: proposal only, 2026-10-13. This document defines a review boundary for a
future owned, isolated PostgreSQL experiment. It implements no SQL, creates no
role or database, runs no fixture, contacts no provider, and changes no v2/v5,
model, recorder, migration, production or hosting code. The source owner's A1
slice has completed its reviewed final ordering tests and freeze; the native
schemas and capabilities proposed here remain unimplemented and require review.

The immediate objective is to make the database independently establish scoped
original-record identity, serialized ordering, committed outcome and complete
inventory. It is not to make a supplied research envelope authoritative. Every
existing A1 research envelope keeps its nine authority fields literally false
forever. A future installed capability is a separate reviewed artifact; changing
flags, stripping headers or wrapping a digest does not activate these wires.

## Dependencies and decisions that must freeze first

The authoritative A1 inputs are `source_admission_v3.py`,
`source_admission_v3_policy.py` and `SOURCE-ADMISSION-V3-CONTRACT.md` at reviewed
commit `45d2b7aabbb889f4ff628c02a1864e7206192a0d`. Its archived draft JSON/field
lists are not the final schema. Final policy digest is
`2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640`;
source bytes are
`b821b469f50b6fe3554851d348822059a33facb5a77e6133290e1c3283fb9bc6`,
policy module bytes
`305793e9dd9069be3fb215918df121696a2a22fbf240a5de89a9b2254c630403`,
and contract bytes
`f8e750dec18d0ea0f09b9a3a6c42a7dc37489aa7f79952a295d19c7d36044e84`.
The pre-refinement descriptor `baa1ceeadbc2a198865c2d44982e011fb4d3841e4e21cee2fc1d8f23babaa68c`
is historical, not an implementation pin. The final refinement includes:

- Current original admission observed time at least the previous original
  accepted time; corresponding original admission and final UTC lower, upper and
  observed values must each be nonregressing.
- No cross-admission ordering against a distinct reader's availability interval.
  Readback retains its own causal/freshness requirements; its uncertainty is not
  interchangeable with the native database guard.
- Nonregressing block and estimated source time, and exact reference price plus
  estimated source-time equality for a repeated block.
- The same checks for admitted originals in ingest order throughout the complete
  supplied seal inventory, including excluded/unavailable admitted candidates.

These dependencies are reviewed and unchanged by that A1 refinement:

| Dependency | Policy SHA-256 |
| --- | --- |
| Acquisition/parser | `912fd28c718311f9b6f72cf0327a7c6b5f4ec7cc4033744d3306064ed869ac89` |
| Prospective sampled-close source | `3be1de572d954859002546e5d525ddb0fbda71a5ca844368381a98395571aad1` |
| Inert recorded transport | `a62184b94f88dbc248a6f3569e171a60e8a0a530addf8ed8aa943b10433f055e` |

The profile is SOL/USD, wrapped-SOL decimals 9, Price V3 reference `usdPrice`,
literal integer block ID, pinned mainnet genesis and `getBlockTime` for that exact
slot. It produces minute samples and 61 close-only 15-minute bars from 915
complete minutes. It supplies no OHLCV, volume, executable quote, provider
publication timestamp, finality, calibration or profitability evidence. Older
generic OHLCV/Birdeye proposals in `PAPER-RUNTIME-V3-PLAN.md` must not override
this frozen sampled-close profile.

Before implementation, root/source/security review must freeze the new native
receipt/readback/page/request schemas; native guard version and catalog inputs;
trusted recorder/reader clock boundary; terminal-refusal/reconciliation
transaction contract; and the full-inventory capacity gate below. This document
proposes those interfaces without manufacturing a final policy digest.

## Native authority and private installation

Use a new namespace, proposed `vn_jupiter_source_research_v3`, with independent
tables/helpers and no dispatch into a v2 synthetic wrapper. Copy only reviewed
stateless scalar/parser concepts where appropriate; do not call an old admission
entry or change its source. The private installer must have only the owned
fixture's installation capability. Its catalog fingerprint and accepted
bindings are held server-side; actors cannot provision or amend either.

Derive the actor from the actual database `session_user`, with a server-held
binding to owner, run, market epoch, enabled acquisition epoch, issuer binding,
principal-binding UUID, accepted recorder/native package and endpoint/policy
map. Caller UUIDs, `SET ROLE`, application service-role claims, supplied headers,
SHA-256 values and Python constructors do not establish that binding. Proposed
roles are a restricted source recorder, a source reader and a source seal actor;
economic engine authority remains separate. Whether a reviewed recorder also
gets the narrow availability capability must be explicit in the role matrix.

Actors get only scoped entry-point execution. No schema creation, table writes,
sequence manipulation, helper execution, actor provisioning, epoch insertion,
package acceptance or economic mutation is granted. Each owner/run/market has a
held head/fence; epoch rollover is an explicit installer-authorized transition
with its own original operation identity. Retain all past acquisition epochs,
principal/package associations and configuration UUID roles. A→B→A is refused
even after rolling source history no longer contains A. Same-package restart
preserves historical per-record epochs; no cross-process monotonic subtraction,
lease restoration, synthetic clock origin, silent resume or new fifteen-hour
rewarm is implied. Cross-package continuity remains unsupported.

Before any security-definer helper or getter runs, its search path is explicitly
`pg_catalog,pg_temp`, every system catalog is schema-qualified, and all application
objects are explicitly qualified. Read-only getters need the same protections
as mutators. Do not change the database-wide PUBLIC TEMP grant. Use benign
sentinel shadow objects for regression tests, without private-write payloads.

Fingerprint the schema, tables/columns/types, constraints, indexes, triggers,
functions, ownership, ACL/default ACL, accepted actor role attributes, transitive
membership edges, relevant parameter privileges, extension/runtime version and
server patch/build. Reject catalog drift and effective dangerous privileges.
Check `session_replication_role=origin`, reviewed isolation/session settings,
`synchronous_commit=on` and actual `fsync=on` where durability-mode claims are
made. A function-body-only hash or a caller session setting is insufficient.
Exact native/role/catalog validation needs its own source-bound tests; old v2
acceptance cannot establish this new package.

## Proposed storage and linearization

The following are private logical tables, not a migration/schema definition:

| Registry or store | Required invariant |
| --- | --- |
| Accepted package/catalog and actor bindings | Immutable installation pins; explicit accepted scope/capability and one active acquisition epoch. |
| Epoch/configuration identity registry | Complete append-only epoch/configuration UUID history; no reuse or package relabeling. |
| Original identity registry | One original role/packet association per UUID/raw reference; retain excluded/failed allocations and tombstones. |
| Original operations | Exact original request bytes/hash, kind, scope, association, outcome and immutable original result; no replacement bytes. |
| Packet reservations | Seven distinct original operation/observation/record UUIDs, RPC IDs and pinned issuer/policy/package/endpoints before I/O. |
| Captures and raw bodies | Exact safe capsule/body bytes and pins, or bounded original incomplete diagnostic; never eligible by capture alone. |
| Admissions and dependency pins | Independently parsed result and original submission/prior links, actual native sequence/clock/receipt, all immutable originals. |
| Original readback/availability | Original accepted evidence plus separately authenticated reader observation; one immutable original availability fact. |
| Scope journal/head | Contiguous committed write positions, exact operation kind/hash/outcome; last accepted source and previous seal bindings. |
| Seals and seal pins | Complete locked inventory/digests and immutable minute winners with full dependency closure and prior seal link. |

Use one locked scope head as the serialization point for every source write.
Within a scope, take locks in one fixed order: actor/package binding, scope head,
original operation/reservation, then its dependency/identity rows. Before any
cross-scope/global UUID lookup, define one canonical UUID ordering or equivalent
unique-constraint protocol for identity acquisition; otherwise two packets with
oppositely ordered colliding identities could deadlock. Review and test that
protocol separately. A global identity constraint
can refuse cross-owner collisions, but a getter must never reveal another
owner's existence. Configuration IDs and original packet IDs cannot alias.
A raw reference may equal its own record UUID only where the frozen A1/transport
contract allows; it cannot alias another operation/record or acquire a second
packet association.

Assign a journal position from the locked transactional head, not a caller value
or an independent sequence whose rolled-back values create journal gaps. An
admission's ingest sequence equals its own journal position. Reservation,
capture, availability and seal writes consume positions too, so successive
admission sequences may have gaps. Exact replay appends nothing and preserves
the original position. Commit request, original result/receipt, dependencies,
identity associations, journal and head together; failure rolls all of that
operation back. Do not claim a failed admission transaction durably saved a
capture, a diagnostic or a terminal refusal.

Allow one admitted write operation per transaction and enforce it server-side.
No two distinct originals may chain through one transaction with multiple
deferred guards. Readback of an actor's own uncommitted admission is refused.
All authenticated identities and holds must be rechecked under the locks, not
only before parsing or before waiting on another writer.

## Original lifecycle and candidate interface

Names below are proposed experiment operations, not callable production APIs.
Requests bind exact original scope/kind/ID/hash and expected pins; native fields
are generated from held state, never accepted as desired sequence or time.

1. `reserve_original_packet(original_reservation_wire)` performs minimal bounded
   original lookup first. Exact committed replay returns its original result
   before current epoch/age checks. A fresh call validates the actor and package,
   reserves the original UUID roles under the head, and commits a reservation
   receipt. Only independently resolved committed reservation permits later
   collection in the A3 recorder. No provider I/O happens inside SQL.
2. `retain_original_capture(reservation_id, expected_hash, original_capture_wire)`
   independently validates bounded safe capsules/diagnostics and original IDs,
   then atomically retains them with a capture-only journal event. It is allowed
   to retain stale/source-invalid originals under a narrowly reviewed capture
   capability; it does not make them eligible or refresh their receipts.
3. `admit_original_packet(original_submission_wire, original_process_clock)`
   resolves the exact durable reservation/capture and last accepted prior from
   native storage. No client `ExpectedContext`, accepted candidate, epoch chain,
   known-ID subset or supplied prior replaces that native state. Reparse all
   originals, recompute source/receipt/carried age and ordering, generate the
   candidate/provisional native receipt, and check a genuine final native guard
   after all expensive work/writes before returning pending commit.
4. `get_original_packet(scope, original_id, expected_request_sha256)` returns
   scoped immutable reservation/capture/submission/candidate/receipt pins and
   requested originals, or bounded pages. Conflicting owned bytes refuse;
   another owner's existing ID and a random absent ID return the same absence.
   The result explicitly distinguishes committed, historical/current,
   unresolved and absent observation. Historical original facts remain readable
   after source/lease/epoch expiry; getters never restamp source evidence.
5. `register_original_availability(original_observation_wire)` retains the
   separately authenticated recorder/reader's actual observation of the original
   committed readback. It verifies exact original links and causal/age bounds,
   records the original UTC upper bound once, and consumes its own journal
   position. SQL row visibility/getter return alone cannot prove that a remote
   reader received and validated bytes. A2 can prove scoped association/storage
   and server visibility; A3 must supply the trusted actual reader process and
   original clock-observation protocol. No current cache getter or replay gives
   an old packet a later, fresher availability.
6. `reconcile_original_packet(original_id, expected_wire_sha256)` locks the same
   original operation and reservation against late writers and reports original
   committed result, terminally closed refusal/absence, or still unresolved.
   A missing nonlocking getter after timeout proves only observed absence. It
   does not establish that an earlier transaction cannot still commit.
7. `seal_observed_interval(original_seal_request)` freezes the complete native
   inventory at a locked head, independently derives eligible originals/minute
   winners, and writes an immutable seal plus dependency pins. Its own write is
   outside its own inventory digest; it appears as `seal_boundary` at the next
   journal position for the next seal.
8. `get_original_seal`/`get_source_head` returns exact originals and a head-bound
   inventory/page commitment for future sampled-history joining. No engine lease,
   economic command capability or active runtime flag is produced.

Native original replay compares original request bytes as well as their digest,
all package/policy links and scope/kind. This precedes fresh source, current
epoch, fence and revision checks, while still requiring authorized scoped
read/replay capability. The last accepted prior must have its durable original
readback and availability resolved before a new prior-linked packet is admitted;
the source owner confirms this conservative serial A1 lifecycle. A later reader
interval is not a lower bound for a distinct current native guard.

For terminal refusal, propose a separate locked `close_original_refusal`
operation after reconciliation, with its own preallocated original closure-action
UUID and links to the same original admission and capture. It permanently
prevents that admission ID from later succeeding and adds no replacement packet.
It may record a safe whitelisted classification, but must not attest that an
unobserved rolled-back validator actually produced a result. The source owner
confirms that frozen A1 v1 has no such action: `refused_source` is only a supplied
Capture classification, not a persistent native terminal refusal. The closure
therefore needs a separately versioned native event/policy/journal schema before
implementation. It must not be squeezed into an old capture/admission event,
invent a successful candidate, change an A1 enum or mutate the original
reservation/capture. Unknown outcomes stay unresolved and block replacement.
No automatic resend/reacquisition is introduced by A2; any future authorized
same-byte resubmission first proves terminal absence/fence serialization and
still satisfies original freshness, or closes that original without admission.

Acquisition-epoch enable/rollover, scope-fence acquisition/renewal and terminal
closure are native control facts in addition to A1's five source write kinds.
Their exact original request schemas and complete journal mapping also need
root freeze. A narrow held fence/expiry is independently acquired under the
actual server clock; no readback/state provides it. Check matching actor/epoch/
fence and unexpired hold before fresh mutation, after expensive work and during
recognized commit processing. Renewal is explicit and cannot rewrite packet
clocks or be inferred from replay. Original replay/getters remain expiry-tolerant
facts, without fresh mutation permission. Neither an epoch transition nor a
fence can retire a still-unknown original to permit replacement.

The new native complete inventory must include these control/closure facts or
bind a separately complete held control journal and its exact head in the native
seal. This is a schema decision, not an invitation to omit writes. A1's current
contiguous five-kind supplied journal cannot silently acquire extra kinds or
positions. If it is returned as a consistency projection, its limited meaning
and independent position mapping must be explicit; it is never the full native
inventory. Freeze the new native sequence/projection mapping and test it before
claiming a native seal or forwarding one into sampled history.

Reconciliation needs an enforceable retained state machine, not a timeout enum:

| Original fact | Permitted next transition |
| --- | --- |
| Observed absent from a nonlocking getter | Still unknown; no replacement, new availability or collection. |
| Committed original reservation, no capture | Its exact original capture or separately versioned terminal closure after locked reconciliation. |
| Committed capture, admission result unresolved | Resolve that exact original submission/outcome; no fresh submission ID or changed body. |
| Committed admission, availability unresolved | Retrieve original committed readback and resolve the one prepared original availability action; no later clock/ID substituted after lost acknowledgment. |
| Committed original availability | Immutable facts/replay; a new prior-linked packet only under independently current bindings. |
| Committed terminal closure | Permanent non-admission tombstone for the original, including future delayed/queued writers after locks are released. |

A reconciler may report safely terminal absence only when the same transaction
has committed an enforceable scope/ID/request-hash-bound tombstone or equivalent
reviewed terminal fence. Holding a lock and observing no row is insufficient:
a queued original writer could otherwise acquire that lock later and succeed.
Every original writer must check the closure under the same serialized lock.
Close/reconcile/availability actions also have their own original IDs, bytes and
lost-acknowledgment getters; an uncertain closure is not a license to repeat it
under a new ID. Reconciliation records supplied safe classifications, not proof
of an unobserved failure branch. Freeze the exact full original submission/body
and dependency links retained by a terminal closure before implementation.

## Independent raw parser and exact time semantics

Do not cast raw responses directly to `jsonb` and accept the resulting object as
independent parsing. That loses duplicate keys and numeric lexeme/type evidence.
The proposed first experiment uses new private bounded native lexical/structural
helpers over original UTF-8 bytes, preserving integer-versus-decimal tokens and
decoded key uniqueness before using numeric values. It retains original bytes;
JSONB may be an internal post-validation view only.

Match the reviewed parser grammar: strict UTF-8, no BOM/NUL/lone surrogate,
maximum nesting 32, at most 1,024 object members, 5,000 array entries and 200,000
visited nodes; numeric tokens at most 128 bytes, at most 80 significand digits,
exponents −80…80, finite exact decimal values and literal `-0` refusal. Integers
such as block/RPC ID/source result require integer-token type and bounds;
`true`, `1.0` and `1e0` cannot substitute. Decimal prices retain exact scale-18
normalization with integer arithmetic and bounded range, without binary64 or
implicit zero. Canonical envelopes require exact decoded field sets, canonical
counter/UUID/digest/string serialization, literal formats and false flags.
Python's key sorting/UTF-8 JSON escaping must be matched where hashing canonical
generated wires; SQL `jsonb::text` key order/spacing is not a canonical hash.
If a faithful bounded native parser cannot meet the reviewed grammar, stop at
that implementation gate instead of delegating authority to a supplied Python
candidate. Reuse of stateless lexer concepts requires review and new tests.

Reparse Price→genesis→exact-slot block time independently, checking safe original
request hash/endpoint/method/RPC ID/arguments and raw lengths/base64/hashes. Price
raw cap is 131,072 bytes; each RPC cap is 65,536. Keep nullable optional
`priceChange24h` ignored but retained, and null block ID/time hard-refused. Invalid
unused numeric fields still receive the frozen JSON grammar validation.

Store clocks as exact integer UTC microseconds within the original signed-64-bit
bound. Use exact PostgreSQL numeric epoch extraction/conversion before range
checked integer encoding; no double-precision `date_part`, binary64 conversion,
second-floor authority or synthetic monotonic origin. In the lab, genuine DB
clock samples are recorded explicitly as observations, not proof of calibrated
UTC. Future accepted clock uncertainty/calibration belongs to a separately
reviewed recorder/native deployment boundary and cannot be asserted by an input.

Under the locked original head, capture actual native admission time after raw
parsing/age/identity checks; capture actual final function time after remaining
projection/storage work. Recheck the unchanged original receipt ages strictly
below 5,000,000 µs, source-age ceiling at most 30,000,000 µs and future tolerance
at most 2,000,000 µs, with conservative elapsed upper bounds. No receipt refresh,
floor-based next-second wait or replaced fresh response is allowed. Same-epoch
monotonic carry and cross-epoch conservative UTC carry come from complete
retained original witnesses, never a supplied smaller age snapshot. Apply the
final A1 cross-admission component ordering and repeated-block equality under
serialization. A genuine native UTC regression is a refusal, not a timestamp
adjustment. Reader availability remains its distinct original observation.

Define accepted-at as the original native admission observation, matching A1;
it is not COMMIT visibility. Candidate final guard describes the final function
observation. The native transaction receipt separately records any recognized
commit-processing guard; do not rewrite/re-hash the candidate later to imply
that its original final guard occurred at durable/visible commit.

Investigate a deferred commit-processing guard under the previously researched
restrictions, but implement/version it separately from v2. It rechecks all held
bindings, original budgets and catalog/session invariants using a genuine clock
at the guard. One standalone ASCII-normalized `COMMIT` frontend message, no
multi-command batch, prepared transaction, force-immediate constraint, implicit
commit or unreviewed transaction form is admitted by that laboratory contract.
Temp state/holdable cursors and deferred-trigger bypass paths need explicit
tests without global privilege changes. A COMMIT-text check is a bounded
laboratory defense, not client authentication.

Freshness at recognized commit processing is the maximum claim. PostgreSQL may
perform later deferred/user/core work, WAL flush, replication waiting and
visibility changes. Timeout/cancellation does not prove rollback or a hard
guard-to-durability bound. A function-return failure and a deferred COMMIT failure
have distinct safe error codes. A post-rollback diagnostic records a later
observation and original-ID/head outcome; it never claims the exact failed guard
instant or definite source-versus-lease branch from a combined exception.

## Complete inventory, minute eligibility and seals

Build inventory from actual held native journal state. The caller provides an
expected head/previous seal, not an authoritative list. Resolve both directions
of coverage for all reservations, captures, accepted/refused/unknown packet
outcomes, availability and prior seal writes through the selected journal head.
Keep pending/excluded operations; do not omit them to obtain a usable seal.
Original getter dependencies are immutable links, not invented extra write
events. Original submission/readback IDs may share the accepted operation's ID
only in the distinct frozen semantic kind; there is one admission write event.

The scope lock serializes reservation/admission/availability/seal and explicit
terminal closure. Once sealed, a later operation has a larger journal position
and later actual observation; it cannot revise the frozen eligible set. A packet
first resolved after sealing cannot backdate its readback upper bound or enter
an earlier minute. Pending originals remain in the original inventory and are
reconciled without reopening that seal. Failure of required coverage or a
missing minute refuses the seal atomically while retaining already committed
original operations. Holding a seal lock cannot manufacture a prior timestamp.

For each minute use accepted-at within `[start,end)` and separately authenticated
original committed-readback upper no later than minute end, with all original
receipt/source/causal bounds checked. Pick latest accepted-at, then its unique
ingest sequence; preserve A1's distinct eligible-record digest. Check source and
native clock nonregression for every admitted original in ingest order, including
ones not eligible for a minute. A repeated block preserves exact price/time.
No interpolation, missing-anchor fill, retrospective data fetch or old candidate
header cast supplies a minute. Final sealing is no earlier than period end plus
the unchanged five-second margin.

Initial native sealing requires 915 complete minutes; incremental seal advances
15 minutes and retains the previous 15-minute overlap in its 30-minute interval.
The old history's retained 900 minute anchors remain exact originals in the
later full history bridge. A2 does not construct a `SampledHistory` by casting its
inventory seal: that authenticated bridge is the separate R3-03B model/source
join. Reads may be bounded pages bound to the same immutable head/digest; paging
does not change the single A1 seal's structural limits or prove completeness by
itself.

## Finite limits and measurements

Keep A1's per-envelope 4 MiB, seal 8 MiB, 4,096 inventory/known-record/known-operation
entries, 128 epochs and 24,576 original dependency bounds. Keep the transport's
1 MiB per-packet pre-I/O reserve and 8 MiB/4,000 packet engineering cache distinct
from durable storage, aggregate process memory and source warmup. Native raw
storage may deduplicate exact original bytes by private immutable identity, but
must retain each full original association, receipt and dependency pin. No
pruning, deletion eligibility, cache release or capacity-driven evidence loss is
introduced here.

Those per-seal witness limits do not cap or erase the lifetime append-only native
identity, epoch, command, closure and storage registries. Bounded pages can query
retained historical membership against an immutable native head; unasked or
unreturned IDs remain unknown. Raw-body deduplication is physical exact-byte
sharing only: every distinct raw-reference/record/reservation association and
original capsule pin remains intact, with no new A1 identity-reuse exception.

At one successful packet per minute, 915 minutes consume 3,660 writes for
reservation/capture/admission/availability. Only 436 entries remain in a 4,096-row
initial inventory for extra attempts, diagnostic/closure writes and other
boundaries. More frequent acquisition quickly exceeds that seal bound. This is a
real design gate: choose and measure a supported initial cadence/capacity before
implementation, or review a new forward paged-seal policy. Do not silently
truncate, widen, relabel or treat getter paging as an enlarged seal. Original
dependency caps also do not establish an aggregate byte/RSS bound.

A short isolated fixture cannot produce a genuine complete initial warmup by
seeding past native acceptance/readback times, advancing a test clock, relabeling
synthetic records or omitting 900 minutes. An actual initial 915-minute trace
needs approximately 15 hours 15 minutes of retained prospective observations
(plus alignment/sealing), unless a reviewed native installation already retains
that authentic history. A2's ordinary suite should prove raw parsing, original
transactions, scoped registry and minute/selection mechanisms without claiming
full warmup. Full native initial/incremental seal acceptance remains a separately
opt-in bounded long experiment or a later actual closed prospective pilot.

Record encoded bytes, row/index/TOAST allocation, dependency counts, fixture
identity, actual source/package/catalog digests, CPU/RSS and lock/parse/function
guard/commit/readback elapsed observations. Report maximum observed resource
tail and guard-to-source/lease headroom without asserting a universal SLA or
extrapolated monthly cost. Railway's 0.25-CPU pilot and $20 ceiling are later
resource/cost gates, not A2 fixture capacity assumptions. Any five-second failure
is retained evidence; changing a bound or resubmitting a fresh original is not a
performance fix.

## Proposed acceptance matrix and implementation order

Only after schema review, use the existing owned UUID fixture pattern with the
verified cached PostgreSQL 17.6 arm64 image, no image pull/tag/global role or tool
change, network none, sanitized locked Python child, explicit cwd and exact
owned cleanup. Serialize heavy fixtures with root. No shared Supabase, provider
credential, cloud account, production process or Railway worker is involved.
Fixture actor authorization is a lab database fact, not TLS/provider/calibrated
clock attestation. Source-bound evidence must distinguish this from activation.

| Order | Focused experiment | Required evidence and refusal boundary |
| --- | --- | --- |
| 1 | Native parser/codec | Independent raw trio agrees with A1 normalized value/pins; exact byte preservation. Duplicate/unknown keys, Boolean/integer/decimal/exponent boundaries, unsafe Unicode, null/wrong mint/network/slot/RPC, base64/hash/size/depth/node limits and forged normalized/hash-only candidates refuse. |
| 2 | Private installation/actor binding | Two owned scopes and narrow capabilities; no caller owner/epoch/package provision, raw writes or economic authority. Foreign-ID getter equals absent; benign temp-catalog sentinel is not executed; role/parameter/constraint/index/ACL/catalog drift refuses. |
| 3 | Original reservation/capture | Durable pre-I/O seven-ID reservation; exact replay no writes; wrong same-ID bytes/cross-packet raw/config aliases refuse. Incomplete/stale safe capture persists only by its separate accepted action and never becomes source eligible. |
| 4 | Original admission/order | Actual clock and head-assigned sequence; complete original dependencies/prior reparsed. Same-/cross-epoch age floor, repeated-block price/time and current/prior UTC component nonregression; forged supplied prior, omitted epochs, A→B→A and backward clock/source refuse without partial writes. |
| 5 | Atomic rollback/commit forms | Exactly one admitted operation per transaction; original row/head/pins/journal atomically commit or all roll back. Genuine source expiry during final function and during recognized COMMIT have separate outcomes; unreviewed forms/session/trigger bypass refuse. No timeout proves terminal absence. |
| 6 | Lost acknowledgment/reconciliation | Drop original reply, retrieve same committed original from another scoped connection, compare every byte/hash/receipt, replay without append. Concurrent original writer and reconciliation lock cannot return terminal absence while that writer may commit. Changed-original conflict has no replacement request. |
| 7 | Availability/restart | Independently committed-row read plus separately bound actual reader observation, exact original upper once; late/unknown observation does not fill minute. Resolve last admission availability before new prior-linked original; stale-epoch originals readable, new epoch monotonic reset never ages old history as new. |
| 8 | Complete journal/minute mechanisms | Interleaved pending/excluded/diagnostic originals, equal-acceptance sequence tie, late availability, per-minute gap and post-seal attempted insertion. Native inventory coverage/rollback is checked from operator observations, not caller lists. Bounded inspection is not a fabricated initial seal. |
| 9 | Source-bound genuine long seal | Opt-in deadline/reservation/resource plan, actual 915-minute warmup followed by 15-minute increment and exact overlap; final native history bridge still separate. No default CI fifteen-hour sleep, seeded native history or skipped-required proof. |

Robust genuine-clock negatives stage unrelated snapshots before source capture,
submit exactly one original and observe actual server time at the test boundary.
For example, retain one original, wait genuinely at least six seconds with an
independently known live fixture lease/fence, then submit once and require source
expiry plus unchanged admission/head/pins/journal and original getter absence.
Do not depend on a nominal +3/+4-second timestamp staying outside the two-second
future tolerance during slow parsing/snapshots. Future negatives may use a
clearly labeled adversarial supplied original well beyond the real future
bound, with before/after actual clock measurements; those prove refusal, not a
producer-valid source. Close boundary positives retain their true observed
headroom rather than silently moving timestamps or retrying.

Native fixture tests may use an independently constructed synthetic original
trio under a restricted lab recorder. They prove SQL parsing/identity/clock
guards against those original bytes, not real acquisition provenance. A1's
915-minute supplied synthetic corpus remains a separate pure schema test; never
import its supplied native clocks as database authority to close step 9.

Proposed implementation files, after approval: a new native SQL package, a new
private strict raw parser package if separable, a new owned PostgreSQL fixture,
focused source-native tests and a source-bound experiment receipt/contract.
Do not edit `portable_native.sql`, old worker/native clients, migrations,
TODO/preflight, model/source/A1 policy or runtime flags in this lane. Root owns
any later integration and dependency reprioritization.

The remaining ordered chain is final A1 freeze → A2 parser/registry/original
transactions and short native acceptance → independently authenticated
availability/journal/seal closure → A3 durable recorder/reconciliation/acknowledged
cache release → R3-03B full source/model/native/compact/restoration join →
operator-auth/release rehearsal → exact-target finite prospective resource/quota/
cost pilot. Parser, readback decoder and bounded UI/report work can proceed in
parallel after their schemas freeze. Source-native writes, trusted availability,
complete seals and runtime activation cannot skip their preceding authority
gates. Full 915-minute native closure may extend into the authorized finite
prospective pilot; until it passes, warmup/running authority remains false.

## Review status

This draft was prepared from read-only local A1/source/transport contracts and
the original-v2 commit-processing lessons. No new tests or fixture operations
were run for it. The source owner reports final A1 41 cases passing in 288.718
seconds, zero skips, reviewed by root/security and committed with the pins above;
that is A1 consistency evidence, not new native acceptance. Root and both peers
found no proposal overclaim, with the explicit native decisions retained here.
Open decisions are the exact native schemas/terminal-refusal/control-journal
mapping, trusted readback-clock protocol, native parser feasibility and supported
single-seal inventory capacity. The separately scoped
`R3-03A2A-RAW-PARSER-EXPERIMENT-DESIGN.md` can receive implementation authorization
before those wider schema decisions; it produces only a research raw-value
projection. No remote action or authority expansion is authorized by either
document.
