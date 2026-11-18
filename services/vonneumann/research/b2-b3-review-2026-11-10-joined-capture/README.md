# Native capture in the handoff and Stop journal

This held PostgreSQL 17.6 candidate covers one synthetic SOL/USD scope,
one authenticated successor and one complete packet. Renew at position 4
transfers the existing fence. Reservation at position 5 and Capture at
position 6 reuse the same scope lock, head, fence, identity registry,
original operations and deferred COMMIT guard. A distinct packet policy
digest names the new wire protocol. The sealed catalog and native package
bind the packet functions to the existing handoff and control functions.

Reservation stores eleven distinct IDs and the original A1 Reservation and
PreparedPacket wires. Its result records the packet as unresolved. Capture
retains the three original capsules and all original raw bodies in the
preallocated Capture command. The native reader can recover them using
only the scoped Capture ID. Wrong digests, unauthorized readers, malformed
RPC numbers or protocol versions, raw byte hash mismatches and stale
heads refuse. The result retains eligibility and terminal flags as false.

The worker collection adapter requires the exact provisional Reservation
reply returned after acknowledged COMMIT, followed by an independent
reader's exact committed command, result, receipt, direct dependency pins
and current journal head. It consumes its single local attempt before any
callback. A replay or lost acknowledgment supplies no collection grant.
The Stop adapter validates the independent reader's entire canonical
intent observation and submits the original bytes once through the
separate control connection. After an uncertain submit or restart,
reconciliation of the original is the worker boundary. Native exact replay
preserves the original outcome. The local guard does not create a durable
dispatch claim shared across worker processes.

## Joined interruption cases

| Fault | Observed behavior |
| --- | --- |
| Recorder backend terminated after Capture COMMIT | A fresh TLS/SCRAM reader recovers the original Capture, three bodies and receipt without another callback. Gated Stop commits at position 7, and the older operations and capture remain readable. |
| Recorder backend terminated with Capture still provisional | Stop intent is visibly waiting on the shared lock. After the writer is terminated, the independent reader sees unresolved Capture, the exact intent commits and gated Stop commits at position 6. A late Capture cannot advance the stopped journal. |
| Reservation COMMIT succeeds but the worker loses the acknowledgment | The eleven reserved IDs and exact receipt remain readable. The gate grants no provider I/O, a competing Reservation refuses, and gated Stop can commit at position 6. |

Each interruption identifies the owned backend before terminating it. The
fixture uses held synthetic provider responses and no network. All 57
native cases passed across 15 fixtures, including the 54 inherited cases.
There were zero skips and all owned fixtures cleaned up normally.
[Final native receipts](native-receipts.json).

The first joined candidate stopped during installation on an
unparenthesized `CASE` expression in the COMMIT function. The next candidate passed the
three interruption cases. The final correction tightened the native RPC
wire checks and added decimal ID and numeric protocol version refusals.
[Prior native receipts](prior-native-attempts.json).

The separate offline suite passed 82 tests, including eleven worker-gate
cases and the existing synthetic 915-minute inventory case. The first
strict runner invocation stopped at an inherited pure-import probe that
starts a Python subprocess. The successful rerun permitted only that
probe's exact program, executable and clean environment.
[Offline receipt](offline-receipt.json).

## Reproduce the exact candidate

Reconstruct the accepted [handoff and Stop parent](../b2-review-2026-11-10-credential-handoff/README.md)
and the disjoint [standalone capture parent](../b3-review-2026-11-10-durable-acquisition/README.md).
Apply the [joined forward patch](candidate-joined-forward.patch) to the
combined 13 parent files. Verify all 20 postimages and the exact tests
listed in the [manifest](candidate-manifest.json). The native runner adds
those files to 936 tracked PR117 main blobs for 956 total source files.
It uses pinned CPython 3.12.14, an allowlisted dependency inventory and
the previously reviewed PostgreSQL 17.6 ARM64 image. Each native run uses
an owned network-disabled fixture with no published port or host mount.

## Remaining production gates

The lab's fresh Capture requires the exact current head and a live fence.
Safe incomplete captures and retention against a scoped ancestor after
Stop or expiry require a separate rule and tests. The collection gate
establishes the journal head at readback. Fence expiry and Stop intent can
occur without changing that head, so production collection needs a live
fence and pending-Stop check at the I/O boundary and a defined policy for
an in-flight request. A stopped scope can still contain an unresolved
packet. Source admission, independent Availability, terminal closure and
reconciled cache release remain separate. The managed issuer, hosted
interruptions and sustained capacity need their own acceptance evidence.
