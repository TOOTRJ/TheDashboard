# Local worker admission and draining

SVC-02A, September 30, 2026. This contract covers one manager in one event loop.
It does not provide a database lease, transaction journal, restart restoration,
cross-process coordination or permission for unattended hosting.

## Admission before side effects

Both HTTP start routes reserve a manager-owned startup task before constructing
a repository or sending the initial insert. Admission checking and task
registration contain no intervening await. The reservation remains owned through
insert acknowledgement, preparation, failure compensation and cleanup. Direct
manager creation uses the same admission path; only the reservation's owning
task can enter preparation without a second check.

Duplicate colony IDs are conflicts and cannot replace a controller, lock or task.
The default bound is **32 retained colonies**, counting starting reservations and
running, stopped and failed controllers. The constructor accepts an integer
limit from 1 through 128. This is a mechanical memory/admission bound, not a
measured safe concurrent workload. No new environment variable is introduced.
Terminal state is not evicted to free space. A process restart is not a safe
retention-clearing procedure until durable interruption/reconciliation exists.

An authenticated start rejected before admission returns HTTP 503 with exactly:

```json
{"detail":{"code":"worker_draining","operation":"start","accepted":false}}
```

The other accepted code is `worker_capacity`. These responses contain no run ID,
owner, count or raw provider message. The dashboard recognizes only this exact
shape on the two POST start routes, shows a local explanation and never retries.
After admission, errors keep the existing run identity and uncertain-outcome
semantics; they must never claim `accepted: false`.

An unacknowledged initial insert can still have committed. The manager retains
an owner-visible failure and attempts a status-only terminal update, preserving
the original configuration when the repository's insert cache is empty. Failed
compensation remains explicitly unsaved. No insert is automatically retried.

## One owned shutdown operation

Shutdown permanently closes admission before its first await. Each existing real
controller receives a monotonic drain flag: later resume/lifecycle changes cannot
clear its pause, and the loop cannot start another tick batch. An accepted batch
may finish; draining is not a synthetic trade exit or cash transfer.

Accepted startup tasks are cancelled once. They retain their accepted writes
and compensating status work through acknowledgement. Accepted controls remain
tracked and serialized by colony lock. New controls are rejected during drain;
resume/recovery acknowledgements crossing drain cannot reopen execution. Only
the internal drain can issue the final stop.

One shutdown task and its original **40-second deadline** are reused across
calls. Waiting uses `asyncio.wait`, not cancellation of the owned drain. A caller
can time out or be cancelled while the manager keeps strong references to its
startup, control, supervisor and cleanup work. Repeated shutdown calls neither
restart the deadline nor launch duplicate cleanup. The result is:

```json
{"status":"incomplete","pending_operations":1}
```

`complete` requires drained work, no recorded cleanup failure and acknowledged
required terminal statuses. Zero pending operations alone is insufficient: a
completed close can have failed, or a final status may remain unsaved. A later
call can observe completion after pending work actually finishes. These internal
counts are not published by health/readiness routes.

Each colony has one retained resource-close attempt. Its local **5-second wait**
does not cancel or discard the close task. A late close is still awaited by the
global drain; a failed or cancelled close remains incomplete and is not retried
implicitly. The original **30-second preparation/quiescence waits** remain;
cancellation-draining database operations can outlive those local waits, which
is why the separate global report is needed.

The FastAPI lifespan executes shutdown from `finally`, including exceptional
exit. Incomplete draining raises a safe shutdown error instead of logging a
successful stop. This does not prevent a host, SIGKILL or event-loop teardown
from terminating outstanding work. In-memory references cannot survive process
loss; DB-03A and deployment grace-period validation remain prerequisites.

## Liveness and readiness

Public `GET /api/v1/health` remains HTTP 200 `{"status":"ok"}`. It means the
process can answer, without exposing user activity or dependency information.

Authenticated `GET /api/v1/readiness` currently returns HTTP 503:

```json
{"status":"not_ready","admission":"open","durable_recovery":"unavailable"}
```

Admission can also be `closed_capacity` or `closed_draining`. No owners, run IDs,
retained counts, configuration limits or provider diagnostics are returned.
Open process-local admission does not imply database/recovery readiness. Do not
use the public liveness response as evidence that an unattended worker is safe.

## Acceptance and remaining research

Offline tests use real controllers and in-process HTTP with blocked fake I/O.
They cover last-slot races, duplicate IDs, initial inserts and running-status
acknowledgements crossing drain, cancellation-resistant preparation, repeated
cancellation, resume/recovery acknowledgements, retained positions/cash, slow or
failed close, owner isolation, truthful HTTP errors and actual lifespan cleanup.
Existing repository tests retain locks through repeatedly cancelled thread writes.

Next, rehearse DB-03A's lease/fencing token, idempotent command journal, economic
transactions and direct-write restrictions in isolated PostgreSQL. A lease-only
shim beside unfenced table writes is insufficient. Preserve old configuration
and unresolved positions; classify interruption before attempting resume.
Research real shutdown-tail distributions, transport timeout behavior, SIGTERM/
SIGKILL/rolling overlap, memory at the retained bound, archival policy and shared
provider polling/quotas before setting a host's resources or grace period.

Primary references reviewed September 30, 2026:

- [Python 3.12 asyncio waiting primitives](https://docs.python.org/3.12/library/asyncio-task.html#waiting-primitives): `wait_for` waits for cancellation completion, while `wait` can return pending work without cancelling it. This implementation retains ownership explicitly.
- [Python task creation and shielding](https://docs.python.org/3.12/library/asyncio-task.html#creating-tasks): strong task references and cancellation boundaries matter when the request caller leaves.
- [FastAPI lifespan events](https://fastapi.tiangolo.com/advanced/events/): the async lifespan context owns startup/shutdown cleanup; the project uses `finally` and explicit incomplete-drain reporting.

See [the persistence plan](PERSISTENCE-RECOVERY-PLAN.md) and
[the hosting research](../../WORKER-HOSTING-RESEARCH.md) for the remaining gates.
