# Executable bounded provider controller

`ProviderPilotController` composes the opt-in version-5 paper pilot with the
actual Jupiter price, Solana source-time and Birdeye candle adapters. It owns
the complete bootstrap, tick, supported control and settlement operation. The
production service still selects its existing controller; this component does
not restore a checkpoint, trade a wallet or enable a hosted worker.

The pilot keeps its existing two EMA genes, eight members, one asset, one
evaluation window and reserved stop capacity. See
[PROVIDER-PILOT-CONTRACT.md](PROVIDER-PILOT-CONTRACT.md) for those bounds and
[PROVIDER-COMMAND-CONTRACT.md](PROVIDER-COMMAND-CONTRACT.md) for the v5 request.
The feed, pilot owner, repository, outbox transport and publisher must have no
other callers. Ownership is local to one event loop; it is not a cross-process
lease or restart protocol.

## Whole-operation ownership

Each public asynchronous operation creates one shielded task and retains its
result until its caller or `settle()` consumes it. Caller cancellation does not
cancel an acquisition, committed reply or publication halfway through the tick.
The controller remains busy even if the retained task has already finished.
Another bootstrap, tick or control cannot overlap it. A foreign-loop caller is
rejected before consuming or discarding the original operation.
Explicit interruption of the owned controller task also retains any shielded
provider read. Settlement awaits and consumes that original read before reporting
idle, even when the now-closed owner rejects its result.

The immutable `CommandAllocation` binds one command ID and bounded tuples of
economic IDs and names. Its synchronous allocator is called only for an actual
new command. A retained work record stores the exact phase, allocation, ticket,
owned history, expected revision and continuation before submission. Readback
resolves that original command; it never repeats its planner, allocation,
protection or optimizer evaluation. Missing readback reports `pending` and
does not fetch new market data.

| Operation | Ordered phases |
| --- | --- |
| Fresh bootstrap | Confirm lease; acquire current literal seed history; prepare/submit bootstrap; install acknowledgment; publish all original events |
| Tick | Confirm lease; acquire exact quote; prepare/submit protection; install/publish protection; select useful decision; optionally acquire history from installed cursor; prepare/submit decision; install/publish decision |
| Pause | Settle any original command/events without continuing unsubmitted economics; confirm lease; prepare/submit pause; install/publish |
| Stop | Latch drain; settle original command/events; confirm lease; submit reserved stop; install/publish |
| Settlement | Consume the retained whole task/result or read back the exact original command and publish its original events before any allowed remaining phase |

Readback clears the repository's local lease evidence. Before a recovered tick
can continue unsubmitted economics, the controller must confirm a new heartbeat.
The expected installed revision must match the original command's successor.
Publishing uses bounded count/byte pages until the entire original prefix is
acknowledged; a non-progressing retained page fails visibly. The publisher sees
installed authoritative state. Stable event identities and receiver deduplication
retain the existing coordinator contract.

## Acquisition, decisions and controls

The acquisition helper explicitly accepts the base provider owner and the exact
pilot owner. A normal pilot limit drains acquisition without converting the
separate policy-refusal latch into a hard failure that would spend the reserved
terminal path. Arbitrary subclasses are still rejected.

History uses a five-second acquisition deadline, with an explicit deadline
check after awaited reads and parsing. CPU work cannot be preempted by an asyncio
timeout; overrun is rejected before new command dispatch. Price acquisition
retains its existing standalone deadline. Once a command might have committed,
the controller does not impose a timeout that discards its ownership or create
a fresh command as a replacement.

An unchanged quote returns `deferred`. A plain accepted quote still installs
protection but skips ordinary history, allocation and submission when the
identical acknowledged ticket has no decision work. Incremental history uses
only the installed source cursor and the shared five-second completed-candle
margin. The strict source policy rejects missed/revised bars and invalid
source clocks. Crossing the completion boundary during an otherwise valid
preparation can still reject the decision and close admission. This is a known
safe failure mode; no timestamp is rewritten or installed protection repeated.
A supported boundary deferral policy remains a follow-up.

Drain is checked again after lease, price and candle awaits, before the next
unsubmitted action. It abandons only idle, unsubmitted evidence, invalidating
the old decision ticket. Evidence bound to a retained command/event prefix
cannot be abandoned. This prevents an unused decision window from later
expiring a delayed reserved stop. A stop request during a busy operation latches
drain and returns `CommandBusy`; it is not queued. Consume the original result
or settle its command/events, then explicitly call stop again.

Retrying an uncertain pause/stop first resolves its original ID. If its status
is already installed, the controller returns the original report without a
second allocation, heartbeat or invalid lifecycle transition. Repeated
confirmed same-status control is likewise a read of acknowledged state. Pause
and stop retain holdings, cash and reserve. Resume, recovery and live liquidation
are outside this pilot's policy.

## Explicit bounded scheduling

`ProviderPilotRunner` is a separate local scheduling owner. It requires a fresh
controller, an explicit finite polling interval shorter than its configured
lease and an explicit tick bound no greater than the pilot's quote budget.
An expired server lease cannot be renewed by the next tick. This validation
rejects an obviously invalid wait; it does not prove enough remaining lease
after preparation/publication, nor choose production cadence. There is no hidden
lease-heartbeat worker during waits in this component.
It schedules sequential ticks with a delay after each completed tick; delayed
work never creates a catch-up queue.

Cancellation of its caller drains new controller admission and retains the
original runner task/result. Already admitted work settles before the runner
reports drained. Explicit stop requests likewise drain and use the reserved
terminal path only after original work is idle. Uncertain command or publication
failure remains visible and requires explicit settlement, rather than a retry
spin. Merely reaching a finite tick limit does not invent an automatic stop.
The executable runner is opt-in and absent from service startup/selection.

The interval check is necessary but does not reserve the remaining lease. Its
deadline starts at the prior renewal request, before acquisition, preparation
and publication. Production acceptance must account for that completed work,
the configured wait, renewal dispatch/tail and the repository's local margin.
Before supporting long waits, expose validated remaining-lease evidence and
either reject a wait without headroom or renew sequentially while idle before
expiry. A heartbeat must never compete with an owned tick or event prefix.
No default cadence or new arbitrary timing margin is selected by this increment.

## Timing evidence and remaining gates

Every controller report contains immutable cumulative phase measurements:
history/price acquisition, lease renewal, owner submission, reconciliation and
publication, together with elapsed whole-operation time. `owner_submission`
includes candidate preparation, the complete stop-capacity witness, validation
and transport acknowledgment. It is not a separate database-only latency.
Publication includes all bounded pages and delivery acknowledgments. Reports
do not emit provider keys, raw credential-bearing requests or response bodies.

Offline tests use literal HTTP documents through the real adapters, strict
pilot, actual solvers and command/outbox validators. Their clocks are controlled
to exercise freshness, boundary, cancellation and lost-reply cases. These
timings cannot select cadence or prove the five-second source-age budget.
All 58 new focused tests pass (35 controller, 23 runner). Complete ordinary
worker discovery passed 1,404 tests in 232.926 seconds with 17 expected opt-in/
database skips; the 16 dedicated GitHub helper cases also pass. See configuration
report section 46 and the PR for the frozen acceptance and review evidence.
The opt-in PostgreSQL suite and latency CLI use actual process/server clocks
and the existing no-network, no-port, no-mount disposable PostgreSQL fixture.
Their HTTP documents remain local fabricated inputs. Even successful local SQL
measurements exclude real provider publication age, remote RPC/PostgREST, host
load, organization-wide quotas and browser/durable relay latency.

**Completed local acceptance (2026-10-05):** after the user started the existing
Colima daemon, all six new real PostgreSQL controller/runner cases passed in
13.952 seconds. Full isolated SQL discovery passed **116 tests in 507.692
seconds** without application, fixture or SQL-contract corrections. The
current-clock latency CLI then passed, verifying three accepted quotes, exact
SQL projection, reserved stop and 11 unique fully acknowledged events. Ordinary
opt-in skips remain distinct from these actual SQL executions.

The measured fixture uses the cached ARM64 PostgreSQL 17.6 image, a uniquely
owned container limited to one CPU/512 MiB, no network, exposed ports or host mounts, and fabricated
HTTP responses through the real adapters. Nine other containers were running;
their identities remained present after owned cleanup. No daemon/context or
shared settings were changed by the task. This accepts the bounded local
executable controller; its parents and production selection remain open.

| Local operation | Accepted operation (ms) | First request through completion (ms) | Deferred attempts |
| --- | ---: | ---: | ---: |
| Bootstrap | 645.382 | 645.550 | 0 |
| First quote/protection/decision | 344.824 | 442.211 | 1 |
| Second quote/protection | 190.775 | 800.938 | 7 |
| Third quote/protection | 212.108 | 1,010.231 | 9 |
| Reserved stop | 288.205 | 288.570 | 0 |

Accepted-operation time excludes an earlier deferred acquisition attempt;
request-through-completion and all-attempt phase totals include it and the real
waits. The observed maximum cumulative owner-submission phase was 311.138 ms,
including protection plus decision in one tick. Bootstrap publication measured
356.813 ms across nine event acknowledgments; stop publication measured 91.312
ms across two. The entire measurement used six economic commits, one creation,
22 heartbeats, three outbox reads and 11 delivery acknowledgments. The 17 receipt
deferrals show why this laboratory's short retry spacing is not a proposed
production schedule. Lease/headroom and redundant renewal scheduling still need
measured production policy.

These are five observed flat-GA/local-sink samples, not percentiles, worst-case
bounds, dense PSO/CMA replacement acceptance or a five-second production guarantee.
No actual provider request, remote PostgREST, durable/browser relay or hosted
worker was measured. `production_cadence_established` is explicitly false.

To reproduce sequentially, from `services/vonneumann` in an isolated development
environment with dotenv disabled, use:

```sh
python -m tests.postgres.run --allow-isolated-postgres
python -m tests.postgres.provider_controller_latency --allow-isolated-postgres
```

Run the harnesses sequentially. They require the existing cached PostgreSQL
image and create/remove only their uniquely labeled, no-network containers.
No production database, provider credentials or application environment files
are used. The latency utility measures bootstrap, three distinct accepted
quotes, reserved stop and complete publication; it includes real deferred
attempts and waiting instead of substituting clock jumps. Its output explicitly
states that production cadence has not been established.

**Deep research before selecting cadence or expanding:** measure provider
source-age and server/lease/outbox tails under realistic load; five-second
cumulative feasibility; complete preparation/stop-witness CPU and memory;
protective exposure during slow publication or slower polling; shared Jupiter
organization quotas and Birdeye history publication/revisions; supported
completion-boundary deferral; interrupted-history catch-up and restart clock
rebinding; durable relay deduplication; compact checkpoint replay/retention.
Production transport, legacy privileges, archive compatibility, migration,
durable recovery and hosting remain separate D/A3/HOST gates.
