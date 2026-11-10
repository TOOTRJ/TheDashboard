# Durable original Stop intent for one successor handoff

The current deadline candidate has no successor recorder. Its submit branch,
deferred COMMIT guard and historical assembler all require the recorder named
in the installation genesis and the current fence holder. An old-recorder
race would only prove the shared lock mechanism. Use the accepted deadline and
owner-separated retirement composition as the starting point for the separate
K2 handoff package, with the Stop intent guard installed before any successor
Renew can be dispatched. The existing deadline, retirement and socket fixture
packages keep their original behavior.

## One invariant

For a single open scope and its one preallocated Stop ID, the first accepted
native Stop dispatch must use an exact independently observed committed intent.
Once that intent commits, every new operation that could advance the scoped
head refuses except that exact Stop. A committed duplicate remains an exact
readback. An original Stop already dispatched never gets a new head or body.
Only an unregistered draft may be rebuilt, and only after resolving any
ambiguous registration and the new committed head. A recorded Stop intent has
no cancellation, expiry cleanup, replacement or overwrite path in this slice.
Its control credential may expire, which closes economic admission while the
original remains retained for the separate recovery procedure.

## Smallest source-forward contract

Use a new explicitly selected fixture format with a native-owner private table
`stop_intents`. Give the scope primary key and reserved Stop action ID unique
pins. Store the bounded exact canonical Command bytes, their SHA-256, the
actual authorized control binding, the applicable package and catalog pins,
and the actual registering `xid8`. Derive head and action fields from the exact
original bytes and independently verify their projections. One scoped row, one
registration write and two declared keys enter an explicit separately charged
admin reserve. Count the row's exact wire and metadata bytes in both retained
and staged bounds. No new native position, original operations row or second
reserved Stop identity is allocated. Later Stop commit retains this row.

Add only a scoped control register endpoint and an independently authorized
reader endpoint, both exact held signatures with pinned owner, body, grantor
and ACL. No issuer, direct runtime table access or new anchor-owner DML grant.
The native owner owns the intent row and uses the existing lock-only anchor
broker. Register accepts an original Stop Command, never a head, flag or hash
substitute. Reuse the complete existing Stop planning/validation to avoid
recording a permanently unexecutable command. A narrow implementation keeps
public `submit(text)` unchanged and moves its existing preparation to a
private held path with an internal intent-only mode. The new register wrapper
selects that mode only for exact Stop, after full head/Control/original/Stop
budget checks and before any native operation DML. The private mode is never
caller-executable. Budget reserve remains untouched by registration.

Both the intent registration and the successor Renew follow the existing
ordered package SHARE, actual binding SHARE, native scope `FOR UPDATE` locks.
The issuer's handoff keeps its package EXCLUSIVE, ordered binding and scope
locks and refuses existing intent. Read the intent from a **fresh READ
COMMITTED statement after acquiring the scope lock**. A pre-lock MVCC snapshot
or a combined pre-wait intent/head read cannot decide the race. Hold locks
through literal COMMIT. A read-only exact replay can use its normal stable
snapshot because it makes no new head. Keep the control and independent reader
credential windows and the previously validated exact catalog on each action.

Registration inserts one provisional intent and recognizes the existing
standalone literal COMMIT profile with its own deferred guard. At that guard,
recheck the same actual control and exact scope/head/intent, current credential
window, package and commit form. An early forced constraint or an unfinished
transaction must not publish the intent. Existing same-wire durable
registration is idempotent. Changed bytes under the same ID, stale head, wrong
scope/capability, unsupported profile or unreviewed catalog changes refuse.
No success response before recognized commit is sufficient dispatch authority.

The independent getter uses one STABLE statement snapshot and its own live
read authority. It returns the exact row or bounded unknown absence. It must
refuse the registering transaction's own provisional row, using the stored
`xid8`. Only positive matching committed readback allows dispatch. On timeout,
cancellation or a lost reply, keep the exact pending registration bytes and
reconcile through this getter. Never dispatch against unknown absence. The
normal original-operation getter remains the authority for a dispatched Stop's
commit and receipt. A durable intent alone is not a completed Stop.

For the new package, every fresh Stop `submit` requires the exact matching
committed intent under the scoped locks. Compare stored `xid8` with current
transaction identity so `register` plus `submit` in one transaction refuses.
Validate the full original wire and hash, scope/head/role and applicable K.
Apply the same guard at literal COMMIT. Every new head-advancing non-Stop
branch refuses a live intent before DML, including the successor Renew and any
future ordinary controls or data admissions. Recheck this condition in the
existing deferred operation guard under the retained locks. Original committed
replays stay read-only and retain their existing clock restrictions.

The one-scope K2 handoff must first prove exact successor authorization in
`submit`, deferred COMMIT and `_reply`, retained K1/K2 catalog and actor lineage,
old-recorder denial, same ID replay and exact receipt recovery. It checks intent
absence under the same scope lock. The first Stop-intent case records after
committed K2 handoff, with position-three head still unchanged. This narrower
scope avoids asserting that an old K1 intent can cross a handoff or that a new
owner terminal marker automatically works after K2. Those joins are explicit
future gates.

## Exact isolated acceptance

Use separately owned fixture runs over the same frozen scope and supported
clock bounds. Verify actual TLS/SCRAM actors, literal COMMIT guards, exact K2
lineage and original receipt reads. Use actual blockers with stable snapshot
and database clocks rather than sleeps as a concurrency witness.

1. **Intent wins.** At open Resume3 after genuine successor handoff, the real
   control stages exact Stop4 intent and holds its scope lock. The independent
   reader sees no durable intent yet. Observe genuine successor Renew4 blocked
   on that scope lock. Commit the exact intent. Renew4 must wake with a fresh
   snapshot, refuse specifically because of the intent, and leave all native
   rows and head unchanged. A fresh independent getter returns exact committed
   Stop4 bytes. The live control dispatches only that original and the reader
   gets its original Stop receipt at position four. Retain the intent and
   unchanged earlier original wires. Repeat registration with exact bytes
   idempotently. Changed Stop4 bytes under the reserved ID refuse.
2. **Renew wins.** Hold provisional genuine successor Renew4 first and observe
   exact Stop4 intent registration waiting. Commit Renew4. Registration must
   wake, see the advanced head, refuse stale and leave the intent row absent.
   No Stop was dispatched in this branch. Verify the exact Renew4 receipt and
   current head, then prepare the first Stop5 using the same preallocated
   action ID. Record/read back its exact intent and commit the original Stop5.
   Verify the independently counted reserve and exact original history.
3. **Rollback and uncertainty.** Force incomplete registration, early
   `SET CONSTRAINTS ALL IMMEDIATE`, same-transaction register+submit and a lost
   registration reply. No caller may see its own row as durable. A rolled-back
   intent must leave no row or new native effect and a waiting successor can
   proceed. An acknowledged exact committed row or independently resolved
   original permits exactly one dispatch. Unknown absence never does. Match
   all scoped snapshots and exact original replies after refusal.
4. **Boundaries.** Test an unregistered Stop attempt, wrong actor/scope/head,
   changed Stop digest under a recorded ID, direct intent-table access, expired
   control/reader, and package/handoff drift. Stop still uses its real reserve.
   No WAL or storage maximum, persistent worker adoption, cross-scope behavior
   or hosted authority follows from these cases.

Current source locations are the `_lock_inputs` package/binding lock broker,
the `submit` scope lock and exact Stop planning branch, `_commit_guard`'s
recognized literal COMMIT/late clock, and the single-snapshot `get_original`
pattern. The existing `ProviderPilotController` is a v5 consumer and cannot
supply this B2 pre-dispatch guarantee by reusing its process-local stop latch.
The first real B2 controller needs an explicit record → independent exact
readback → submit → original receipt reconciliation path.

Prepared by read-only source review. No SQL candidate, native test execution,
repository edit, Docker operation or hosted action accompanies this design.
