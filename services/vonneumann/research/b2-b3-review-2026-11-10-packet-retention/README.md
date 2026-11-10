# Incomplete and late packet retention

The PostgreSQL 17.6 lab has one synthetic SOL/USD scope, one authenticated
successor and one reserved packet. The new Capture command uses a versioned
policy and binds the exact committed Reservation at position 5. The actual
journal predecessor may be that Reservation or the committed Stop at
position 6. The database records the actual predecessor in the Capture
receipt and preserves the source mode, fence state and consumed Stop reserve.
It checks the original writer and scoped Reservation again at COMMIT and
reconstructs the same chain for independent readback.

## Evidence and request authorization

- Incomplete Capture preserves the original safe response prefix and its
  optional diagnostic. The native validator checks the four dispositions
  `not_received`, `partial_discarded`, `withheld` and `captured_original`
  against the reserved request and any matching capsule. The archive keeps
  original request and receipt clocks, hashes and safe response bytes.
- A pending committed Stop intent blocks fresh Capture until the Stop
  operation commits. The exact preallocated Capture can then be retained
  under the same Reservation ancestor. A live fence is required for a new
  request. Archival retention can occur after its expiry while the scoped
  writer remains authorized.
- The lab transport checks each request through the recorder's authenticated
  database connection. The database reads the committed Reservation, active
  fence, current journal head and Stop intent in one statement snapshot. The
  worker checks the response against the exact safe request digest and uses
  monotonic round-trip time to bound its age. A request already in flight
  may return after Stop intent commits. A subsequent check then refuses and
  the exact response prefix can be archived. The snapshot and the external
  network dispatch are separate events. [PostgreSQL snapshot behavior](https://www.postgresql.org/docs/17/xfunc-volatility.html)
- The restart adapter takes the original Stop command and uses the scoped
  reader to reconcile its exact receipt and journal hash. It returns
  `unknown` for absence, unavailability or invalid evidence. A later Capture
  head still permits independent readback of the committed Stop original.

## Reproduction

Reconstruct the [joined packet parent](../b2-b3-review-2026-11-10-joined-capture/README.md)
and add the pinned `provider_recorded_transport_v3.py` from PR117 main as the
only base override preimage. Apply the [candidate patch](candidate-forward.patch)
and verify the [manifest](candidate-manifest.json). It pins 28 source
postimages and 963 composed files. The lab uses pinned CPython 3.12.14 and
network-disabled PostgreSQL 17.6 fixtures with synthetic TLS/SCRAM actors.
The transport verification uses a fake HTTP handler and the actual
PostgreSQL authorization query.

All 62 native cases passed across 20 fixtures with zero skips. The 57
inherited methods retain their exact bodies and all owned fixtures cleaned
up normally. [Native receipts](native-receipts.json)

All 115 offline tests passed, including 29 existing fake-provider
transport tests and four new restart reconciliation cases. The source
admission and seal checks include the existing synthetic 915-minute
inventory case. [Offline receipts](offline-receipt.json)

## Next lifecycle dependency

The current receipt proves archival retention. Admission must independently
parse the exact retained bytes and recheck current source, fence, clock and
prior-original conditions. A separately authenticated reader must observe
and validate the actual committed admission before storing the original
Availability. A non-admitted packet can reach terminal closure through its
own preallocated action under the same scope lock, with the exact attempted
original pinned and a race test against a delayed Capture. Cache release
requires exact independent reconciliation of that terminal result and all
required dependencies. The managed issuer, hosted interruptions and actual
capacity require separate evidence.
