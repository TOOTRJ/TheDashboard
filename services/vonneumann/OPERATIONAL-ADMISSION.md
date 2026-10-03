# Operational admission for the exact rehearsal

DB-03A2C2D2A adds `RehearsalAdmissionOwner` around the fresh version-4 lifecycle
planner, command repository and acknowledgment coordinator. The owner supplies
one entry point for preparation, submission, installation, reconciliation and
ordered delivery. It is an executable acceptance component; the active paper
controller and production transport are still separate.

The source remains `synthetic-exact-fixture-v1`. An owner-issued `RehearsalQuote`
binds an exact synthetic timestamp/price to local receipt wall and monotonic
clocks. Its deadline is a **processing-wait budget**, not measured Jupiter source
age. Synthetic event clocks and `DecisionInputs` continue to describe the
simulation timeline. A provider capture cannot be passed into this API, and
changing a synthetic timestamp to receipt time is not an approved adapter.

## Ownership and progression

Construct the owner with a matching acknowledged fresh v4 run and exclusive
access to its repository and outbox transport on one event loop. Renew the lease
through the owner, bootstrap, and publish the bootstrap events. Further calls use
only the owner. It offers no arbitrary-candidate submission or historical-state
adoption API.

1. `capture_quote(timestamp, price)` returns an immutable, owner-bound quote.
   Capturing another equal-valued quote does not renew the earlier quote's budget.
2. `protect(quote, inputs, command_id=...)` prepares protection from the installed
   state and retains the candidate/command until its outcome is established.
3. A matching acknowledgment installs the candidate. Publish any committed events
   before submitting another economic transition.
4. `decide(quote, inputs, ...)` requires the **same quote object** installed by
   protection. An optional completed synthetic candle is validated by the exact
   planner. A successful decision consumes that ticket. Recovery uses the same
   accepted-ticket rule plus the existing risk-trip and complete-history checks.
5. A new protective observation must still advance the synthetic source timestamp.
   Pause/resume/stop/recovery invalidate previously accepted decision tickets.

An owned, shielded task covers each operation, including synchronous preparation.
Caller cancellation cannot cancel admitted work or admit a competing operation.
Preparation is not rerun on reconciliation. One installed state and at most one
pending candidate/outbox remain retained. The API exposes diagnostic state and
pending identities, but those diagnostics do not grant direct repository use.

## Admission checks and irreversible drain

The owner checks trusted process clocks before and after planning. It checks the
quote window again inside the repository-owned task immediately before dispatch,
after command arguments have been materialized. Task scheduling therefore cannot
quietly consume the window between an outer check and the database request.
The repository also rechecks permanent admission and the current lease there.

The default budget is five seconds, configurable to a positive finite value no
larger than sixty seconds for this bounded rehearsal. The budget expires at
equality. Either wall elapsed time or monotonic elapsed time can exhaust it;
nonfinite, negative or regressing clocks close admission. This policy deliberately
fails closed on clock rollback. These clocks are valid only within this owner
instance/process, and cannot be restored from persisted timestamps.

Any protective/ordinary/control preparation failure, depleted input identities,
invalid command identity, exceeded whole-body capacity, failed clock check or
expired active quote window permanently closes this owner's economic admission.
No exception path substitutes an old unconsumed frame or splits a failed batch.
Command IDs must be explicit canonical UUIDs; `None` cannot generate a random ID.
The owner retains at most 4,096 command identities, including the acknowledged
creation, and rejects known reuse or exhausted capacity before planning. It never
evicts an old identity to admit another command. This is a local rehearsal limit,
not a claim of durable restart deduplication or a broader runtime capacity plan.
`closed_reason` records the first bounded diagnostic code. A failed preparation
leaves installed economics unchanged. A closure does not prove the portfolio is
safe, liquidate positions, manufacture a database stop, or implement recovery.

Concurrent calls are rejected without queueing. Lease renewal remains separate
from market-window admission; a heartbeat cannot refresh a quote's receipt time.
Explicit drain cannot be reopened. A durable pause/stop must be admitted before
drain, as in the existing lifecycle contract.

## Delayed acknowledgments and delivery

The coordinator runs the synchronous guard after submission, journal readback,
heartbeat, outbox reads, publisher calls and event acknowledgments, including
failure paths. A guard failure closes future admission without replacing the
original result or exception. Installation itself still has no callbacks/awaits.

| Outcome | Required behavior |
| --- | --- |
| Window/lease/admission fails before transport dispatch | Clear only the provably unsent attempt; no command RPC or journal uncertainty is invented |
| Transport outcome is unknown | Retain the exact original candidate and command ID; read its journal instead of submitting another ID |
| Commit is acknowledged after expiry | Install the committed state, preserve its receipt/events, close further economic admission |
| Journal resolves an expired command | Install the same candidate and continue committed delivery; do not repeat economics |
| Publication or event acknowledgment consumes the budget | Continue retained delivery with stable IDs; do not renew ordinary admission |
| Caller cancels while an owned operation continues | Keep ownership until settlement; reject concurrent decisions |

The guard is a trusted synchronous assertion returning `None`; coroutine/Future
results cannot bypass it. It is not a plugin boundary or a security sandbox.
The injected transport must still execute exactly one pinned RPC without retries,
redirects or credential fallback. Its own internals must not insert unbounded
queues between dispatch and network I/O. Server-side leases/fences remain the
authority for database writes; local checks cannot prove network arrival time.

The owner has no background timer or hard cancellation deadline. Checks run at
consumption and settlement boundaries. A hung transport/publisher retains owned
work and blocks new economics until it resolves. Production transport deadlines,
relay isolation, durable restart and protective-latency measurements remain gates.

## Next contract and research

C2D2 stays open for active-controller ownership and production acceptance.
[Provider command version 5](PROVIDER-COMMAND-CONTRACT.md) now separately binds
source block reference, estimated time, receipt clocks/epoch, decision time,
completed history and pinned mint/USD/unscaled units. Its `ProviderAdmissionOwner`
reuses the ownership mechanics described here with source-aware guards and
current-time historical startup. The v4 owner retains its synthetic meaning.

Deep research remains necessary on Jupiter block-to-slot/fork semantics,
same-slot/equal-second changes, Birdeye publication/revision/outlier behavior,
USD/USDC and scaled-token policy, restart clocks, command/lease/relay latency and
worst-case memory. Prove active-controller ownership before the production
transport/migration cutover. The worker remains unhosted; this component enables
no wallet funding, signing, swaps or live trading.

See [source research](EXACT-SOURCE-RESEARCH.md),
[acknowledged transitions](ACKNOWLEDGED-TRANSITIONS.md), and
[exact lifecycle](EXACT-LIFECYCLE.md).
