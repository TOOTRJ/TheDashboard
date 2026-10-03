# Acknowledged transition installation and event delivery

DB-03A2C3 places one `TransitionCoordinator` around the bounded exact rehearsal
and its command repository. It starts only after an acknowledged fresh version-3 or version-4
run creation. It does not adopt a historical run or decode persisted optimizer
state. The application controller, production database and hosted worker remain
behind the broader C2/D/A3 acceptance gates.

## Ownership and installation

The coordinator and repository belong exclusively to one owner on one event
loop. Create the run through the repository, construct the coordinator, and
renew its lease through `coordinator.heartbeat()`. Further economic commands,
resolution and heartbeat calls belong to the coordinator; direct concurrent
repository use is outside the contract and cannot establish local engine state.

`submit(candidate, command_id=...)` validates the complete prior state and the
acknowledged run configuration, then retains the exact candidate and prepared
command before its first suspension. A strongly owned shielded task covers
submission, acknowledgment validation and installation. Canceling the caller
does not discard the admitted request or skip installation after a late reply.

Installation checks the complete command, identity, fence, revision, status and
exact reserve before one synchronous state-pointer assignment. Harmless decimal
trailing zeros in the database response do not change the money value. No
callbacks or awaits occur within installation. An installation failure retains
the receipt and original candidate and blocks further decisions.

`reconcile()` resolves only the original pending command, or uses the repository's
matching retained late receipt if the repository already cleared its pending
request. Missing or malformed readback preserves uncertainty. Reconciliation
never submits a new economic request or repeats preparation, optimizer tell/ask,
funding, liquidation or evolution. It also retries installation of an already
acknowledged candidate without redoing the decision.

`close_admission()` permanently closes economics and heartbeat renewal. Existing
work may still settle, install and publish; none of those actions reopens the
drain latch. A confirmed old receipt can be installed after lease expiry, while
new decisions require a renewed current lease. Scheduling failure before an
owned request can start is a local admission failure; uncertainty after an
admitted RPC requires original-ID readback.

## Durable, ordered delivery

The isolated SQL transaction writes each v3/v4 candidate event into immutable
`outbox_events` alongside economics, engine state, journal and receipt. Separate
`outbox_progress` records the contiguous acknowledged prefix for one fixed
application publisher. No delivery update rewrites monetary state or the
original command. Empty-event decisions advance state without inventing a
notification.

Each event includes owner, run, command, revision, index and payload. Its stable
identity is **`run_id:command_id:event_index`**. Including the run is necessary:
two runs may legally reuse a command UUID. Consumers must deduplicate by this
full identity and reject conflicting content for an existing identity.

After installation, call
`publish_pending(publisher, max_events=50, max_bytes=65536)`. The publisher is an
async callable receiving a detached normalized event and returning `None` only
when its fixed relay has accepted it. Keep the same relay/deduplication namespace
across retries; switching callbacks does not create a second subscription.
This success does not prove that every browser received the event.

The coordinator verifies every page's identity, revision, order, payload and
completion indication against its retained candidate before publication. The
server returns at most 100 events and 65,536 serialized bytes per page, including
metadata. It walks bounded indexed event rows, never full command/checkpoint
journals. A single event that cannot fit a requested byte limit fails explicitly.
Delivery remains blocked until the caller supplies a sufficient admitted limit.

Each successful callback is followed by an idempotent acknowledgment for that
same event. The database serializes the publisher checkpoint and rejects skips.
If callback success is known but the database acknowledgment is lost or invalid,
retry sends only that original acknowledgment. If callback completion is
ambiguous, retry can deliver the same event identity again. The contract is
**at-least-once delivery with receiver deduplication**, not exactly-once network
delivery. Caller cancellation cannot start an overlapping delivery attempt.

New economic decisions remain blocked until all events of the retained candidate
are acknowledged. This bounds the local backlog to one admitted transition and
preserves order, but couples decision throughput to relay availability. Heartbeat
renewal is still possible between delivery attempts while admission remains open.
Read/ack RPCs are lease-free delivery operations over committed events; they grant
no trading authority, do not renew a lease, and remain usable after interruption.

Version 4 adds risk, early terminal members, pause/stop and explicit recovery
within the same installation/outbox boundary. See [the lifecycle contract](EXACT-LIFECYCLE.md).
A durable stop must be admitted before permanent `close_admission()`; drain
cannot be undone to manufacture a stop receipt.

## Boundaries and further research

- This publishes v3/v4 candidate events only. Creation and interruption use separate
  existing command receipts; complete lifecycle/browser notification coverage
  remains a production integration task. An old checkpoint's `running` field
  cannot be treated as authority to resume an interrupted run.
- The local candidate's optimizer state cannot yet be restored after process
  death. Durable events remain in SQL, but restart adoption, schema compatibility,
  a separately owned relay and browser reconnect acceptance remain open.
- One fixed publisher checkpoint is not a broadcast subscription system. Research
  relay durability, receiver deduplication retention, authenticated owner/run
  routing and reconnect ordering before wiring a real browser or external sink.
- SQL page bounds do not bound an untrusted HTTP response before JSON decoding.
  The future pinned transport must enforce decompressed-body, request deadline,
  retry and redirect constraints. Measure PostgREST behavior and lease timing.
- Event rows and journal history are not deleted by this slice. Research storage
  growth, archival and safe retention floors for unresolved commands and replay
  consumers before expanding the profile or deploying an unattended worker.
- The one-transition delivery gate is conservative. Measure protective latency
  during slow publication before choosing any bounded decoupling scheme; do not
  remove the gate without proving admission, ordering and failure behavior.

The ownership design follows Python's guidance on [shielding and retained task
references](https://docs.python.org/3.12/library/asyncio-task.html#shielding-from-cancellation)
and [eager task factories](https://docs.python.org/3.12/library/asyncio-task.html#eager-task-factory).
Atomic state/outbox storage and duplicate-aware delivery follow the
[transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).
Unique ordering and the absence of skipped earlier events follow PostgreSQL's
[SELECT and row-locking semantics](https://www.postgresql.org/docs/current/sql-select.html).
