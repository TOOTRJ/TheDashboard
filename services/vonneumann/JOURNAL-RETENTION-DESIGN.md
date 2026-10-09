# Compact paper journal and retention design — research, 2026-10-09

PAPER-COMPACT-03 now has a separately versioned thirteen-slot checkpoint
prototype. It separates stable completed candles and EMA evidence, preserving
all original model/command/history bytes after resolution. This document pins
the next durable-contract obligations. It is not a production migration,
implemented archive, configured budget or permission to delete evidence.

## Required storage boundaries

Use an owner/run/version-bound immutable component store. The proposed key is
`(owner_id, run_id, hash_policy, sha256)`, with explicit component format, kind,
entity and generation. Configuration, source-bars and EMA slots have generation
zero; EMA count, candle ends, source epoch and quote watermark remain independently
validated in the resolved state. Generation zero does not make a supplied block
fresh or authoritative. Genomes, optimizer and cohort retain their actual
generation. No cross-run reuse or recursive references are allowed.

Each accepted original command stores its complete compact request once, its
original UUID, prior checkpoint identity, resulting revision/reference and exact
receipt identity. Store all changed components and all thirteen dependency pins
atomically with it. A manifest is not recoverable from changed blocks alone.
Receipt/readback must prove every referenced component remains available under
the same owner/run/version. Durable allocated identities and parent/cohort/closed
history remain outside the bounded active state; no full-history scan is needed
for uniqueness once appropriate unique keys exist.

The current v5 projection trigger depends on full before/after command fields.
Give the new format its own validated projection path; do not forge a v5 journal
entry or retain a second full journal as the permanent design. Existing v5
records remain readable under their original semantics. Existing incomplete
assessment fields remain explicitly missing, without rescoring or backfilling.

The hash policy is canonical tagged UTF-8 wire SHA256. PostgreSQL `jsonb::text`
is not that encoding. The implementation must prove the actual cross-language
canonicalizer, bounded numeric decoder, duplicate-key handling and bytes-to-JSON
binding before accepting a client digest. The current Python adapter validates
lossless expansion; it is not an independent SQL implementation. Whether the
production store retains canonical bytes, JSONB or both changes physical cost:
the toy measurement stores JSONB only and cannot price an unimplemented layout.

## Transaction sequence and final-boundary checks

1. Authenticate only the exact native issuer/capability. Browser, service-role,
   relay and general worker access must not gain command-table write authority.
   Use the limited installer and pinned catalog/owner manifest in the rehearsal.
2. Lock the owner/run row. Lookup the original UUID before interpreting a new
   prior checkpoint. An already accepted original request returns its original
   receipt; a different complete request with that UUID is a conflict. Replaying
   revision N after revision N+1 must not restore N over the current state.
3. Bind prior revision/digest to the locked committed manifest. Validate the
   complete supplied and retained dependency set, typed slots, scope, version,
   whole command size, aggregate component size and complete resolved state.
4. Independently validate model continuation, complete history/allocated IDs,
   cohort lineage and exact cash/position conservation. Validate source epoch,
   increasing sequence/block/time, original receipt clocks, publication age,
   completed candle contiguity and source/EMA equality. Hash equality alone
   does not prove any of these facts or provider authenticity.
5. Insert original journal, changed blocks, pins, durable identities/history,
   assessment provenance and projection/outbox in one transaction. Apply resource
   accounting under the same lock, including new unique components and pin rows.
6. Recheck source age and current lease/fence at the final boundary after added
   journal/projection work, then commit. A late source/lease failure rolls back
   every effect. No ACK may precede this boundary. A lost reply remains an
   uncertain original command until original-ID readback reconciles it.

A native Stop retains its ordinary body/aggregate validation and independent
cash/holding/history checks. Current Stop aborts the cohort without selection
and preserves positions, balances and any risk latch; it does not claim an exit
or grant later restart authority. Reserve its final revision and capacity for all
eight retained positions, aborted assessment records, receipt, dependencies and
outbox/projection effects. The existing offline 64KiB envelope margin is not a
database row/byte/WAL/lock reserve. Ordinary budget exhaustion must not consume
that reserve. Test this with a filled journal and held locks, not just a small
Stop request. Uncertain prior commands must be reconciled before a later Stop.

## Budgets and rate decisions

Record at least accepted commands/second, original and expanded request bytes,
changed-component bytes, unique stored bytes, thirteen pins per accepted command,
history/projection/receipt rows, table/index/TOAST growth, WAL and archive bytes.
Measure held-position and candle/replacement/Stop cases separately. Warm detoast
query diagnostics do not measure independent validation, contention, final
COMMIT, relay or hosted performance.

The capacity artifact derives logical journals at 0.1, 0.2 and 1 accepted frames
per second with two accepted commands/frame. These are planning inputs, not
selected rates. Its 128MiB example is an illustrative logical-journal budget,
not a cloud limit or retention entitlement. Synthetic reference marks, paper
protective checks and actual provider availability do not establish that a slower
check interval is safe. Measure source age and risk response before reducing
protective frequency. Do not increase paid requests or hosting/billing limits
to conceal unbounded storage. The user-approved Railway pilot ceiling remains
$20/month; no new billing assumption is made for Supabase or Jupiter.

Choose a measured hot journal/unique-component/pin budget and a bounded pilot
duration before activating continuous operation. On budget pressure, stop
ordinary advancement while the independently reserved Stop/reconciliation path
remains available. A bounded pilot may end safely before a full archive service
is ready; continuous acceptance requires a proven archive/retention path.

## Dependency-safe archival protocol

Never delete a command or block simply because its timestamp is old. Pin at least:

- the current committed checkpoint and all dependencies;
- every original pending/uncertain command, its prior and proposed dependencies;
- required Stop/recovery records and any checkpoint chosen for restoration;
- unacknowledged projection/relay work and complete original-ID receipts;
- historical checkpoint/assessment/lineage evidence that has not been verified
  in an immutable owner-bound archive.

Maintain durable original-ID lookup after archival, including complete request
identity, receipt identity, archive locator/hash and archived run/version. Merely
keeping a hash is insufficient if replay equality or checkpoint reconstruction
still requires unavailable bytes. Retain uniqueness/ancestry evidence needed by
new commands; an archived UUID must not become available for reuse.

Create an immutable archive containing the original command, full dependency
closure, exact history/provenance and a versioned manifest. Read it back and verify
scope, canonical bytes, every digest, original-ID/receipt lookup and the complete
checkpoint before switching any reader. Pin the archive during the switch.
Removal of hot dependencies and release of their component pins is a separate
atomic operation under the owner/run lock after reader/relay/pending checks.
Garbage-collect only blocks with no remaining hot, pending, recovery, receipt or
archive dependencies. Test missing/archive-corrupt/foreign/version-mismatched
records and cancellation at every boundary. No archive deletions are authorized
by this design alone.

Use composite foreign keys with restrictive deletion to enforce scoped dependency
integrity. Add an index appropriate to reverse component-pin lookup before
garbage collection. The current toy experiment proves referenced component
deletion fails in PostgreSQL, but uses digest-only fixture keys and cannot prove
production owner isolation, archive correctness or privilege restrictions.
PostgreSQL recommends constraints such as foreign keys/uniqueness for cross-row
integrity rather than cross-table `CHECK` expressions.
[PostgreSQL constraints](https://www.postgresql.org/docs/17/ddl-constraints.html).

Deleting rows does not immediately return table storage to the filesystem. Plan
vacuum/reuse/partition lifecycle and measure retained dead tuples/index/TOAST;
do not extrapolate a smaller live row count directly into a smaller bill.
[PostgreSQL vacuuming](https://www.postgresql.org/docs/17/routine-vacuuming.html).
Large values may compress or live in TOAST, so logical JSON bytes are not physical
disk bytes; the measurement includes table/index/TOAST totals and forces text
materialization for warm read diagnostics.
[PostgreSQL TOAST](https://www.postgresql.org/docs/17/storage-toast.html),
[storage size functions](https://www.postgresql.org/docs/17/functions-admin.html).

## Ordered acceptance and rollback

The next implementation slice is the limited-role SQL/native contract, including
the canonical numeric/hash boundary, original UUID/replay/readback, complete
independent admission, dependency pins and native Stop/resource accounting.
Then prove explicit restoration and the complete next prepared wire across
mid-window, early-terminal, replacement, stopped and uncertain-commit cases.
Only afterward remove GA/RNG evidence or implement archive pruning.

Before hosted migration: close and drain writers/relay, capture exact target and
catalog manifests, rehearse old/new readers and native installer permissions,
review forward migration validation and an evidence-preserving rollback. A
rollback closes the new writer and preserves versioned evidence; it does not
translate newer commands into v5 or drop their journal/component/history rows.
Current prototype rollback is a code/docs revert: no hosted database objects,
worker changes or archives are created by this slice.

**Deep substantial research still needed:** a realistic retained workload with
validation/lock/COMMIT/WAL/TOAST tails; stable-block invalidation under actual
provider publication and revision behavior; archive cost/readback/retention
rights; dependency indexing and cleanup races; explicit continuation before
minimal RNG reduction. Keep the existing full optimizer and two-EMA profile.
