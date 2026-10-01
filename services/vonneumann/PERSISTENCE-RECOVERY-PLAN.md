# Safe durability and later worker hosting

Source review and staged implementation plan, updated October 1, 2026. SVC-02A's local admission/drain precursor is implemented. DB-03A1 supplies an isolated executable database contract rehearsal; DB-03A2A adds immutable command preparation and an injected-transport repository tested against that contract. DB-03A2B adds exact pure economic plans and typed optimizer-source evidence with a v2 SQL rehearsal. DB-03A2C1 supplies detached in-process engine and optimizer state forks. Complete transition planning, acknowledged installation and the application write-boundary cutover below remain future work. The FILL-01A execution JSON column records accounting detail; it is not an atomic ledger, ownership lease or executable checkpoint.

## What is durable today

`db/repository.py` uses separate service-role PostgREST requests, serialized by an in-process asyncio lock. The manager keeps controller objects, tasks, locks and callbacks only in memory. `server/app.py` creates a new empty manager at process startup; its lifespan performs no recovery. Ownership checks prove the authenticated user owns the current in-memory controller, not that this process exclusively owns its database records.

Probe births, trades, occasional probe metrics, lifecycle changes and sealed generation summaries are persisted. Periodic `simulation_status` messages are broadcast without a database write. The runtime JSON is a latest diagnostic snapshot and is overwritten at later lifecycle/cohort/risk transitions. `last_evaluation` is not append-only evaluation history. The repository cache `_colony_config` starts empty: a newly constructed repository must not update old-run details using that empty cache or it will erase the original configuration.

The cash reserve, exact account transitions, signal cursors, shared indicator state, market/optimizer RNG state and complete optimizer state are not checkpointed. Older persisted trade P&L may be rounded, while engine cash uses unrounded values; FILL-01A preserves new trade values without display rounding. Latest probe cash can lag multiple trades. Reconstructing current cash or reserve from those rows is unsafe. Current history readback and mock repository tests do not prove restart resumption or database RLS correctness.

## Recommended first durability release

The local precursor **SVC-02A is implemented**: start admission precedes the
first write; startup and control tasks remain owned; a permanent controller
drain flag prevents later tick batches; retained controllers are bounded without
eviction. One shutdown task/deadline and owned resource-close attempts retain
pending work and report incomplete cleanup instead of releasing write ownership.
Lost insert acknowledgements use status-only compensation to preserve config.
Public liveness and authenticated readiness remain distinct; durable recovery
is explicitly unavailable. Offline race/lifespan tests cover the acceptance
boundaries. See [the implemented lifecycle contract](WORKER-LIFECYCLE.md).
This precursor does not satisfy the database fencing gate below.

The [DB-03A1 rehearsal](db-contract/README.md) implements the proposed
command/revision/journal boundary in a disposable schema against isolated real
PostgreSQL connections and roles. It exercises exact decimal cash/reserve,
birth/open/close/retire batches, fixed ownership grants, lease expiry after lock
waits, and interruption without adopting old positions. It is outside the
Supabase migration path and is not loaded by the worker. The next stage is
repository/engine integration as one complete write-boundary cutover. Do not
ship a lease-only shim while direct
service-role or authenticated-owner writes can bypass it. Existing normal-stop
feed cleanup is already implemented; extend its failure/race coverage rather
than replacing it wholesale. Shared provider polling comes after local lifecycle
safety and needs immutable observations plus per-colony delivery cursors. Never
couple synthetic clocks by sharing a mutable simulation feed.

Implement fenced interruption and inspection before attempting resume:

1. Introduce a durable lease/run-state record keyed by colony and owner, with worker-instance UUID, monotonically increasing fencing token, database-time lease expiry/heartbeat and committed state revision. A newly created run obtains its lease atomically with creation. Heartbeat loss blocks subsequent authoritative writes and decisions.
2. Require every mutation to verify owner, colony, fencing token, unexpired lease and expected revision inside the same database transaction as the write. A Python precheck followed by a separate request is insufficient. Old workers must not retain a direct-write path around the fence.
3. At startup, atomically classify expired active runs as interrupted and requiring inspection. Preserve configuration, trades, positions, probe states and historical balances. Do not invent closes, mark probes DEAD, reclaim cash, score interrupted cohorts or resume them. Existing `failed` plus a safe `worker_interrupted` code can carry this state initially if a new lifecycle would expand scope excessively.
4. Present interrupted history as unmanaged, with no monitoring guarantee. Pause/resume/recovery controls require the live lease owner. A separate experiment receives a new colony ID and starting notional; it never adopts old balances. Do not add a generic “retry start” that duplicates an uncertain command.
5. Readiness becomes distinct from process liveness: database contract, ownership and reconciliation readiness must pass before accepting new work. One desired instance and one Uvicorn process remain deployment requirements but do not replace fencing during overlapping releases.

This release safely refuses incomplete restoration. It does not close the full DB-03 resume gate. Legacy active rows without leases require an explicit classification plan after older writers are drained or disabled; a missing lease alone is not evidence that an old process is dead.

## Atomic economic boundaries and uncertain writes

Add a versioned append-only command/event journal with unique `(run_id, event_id)`, monotonic sequence, expected revision, normalized payload hash and committed response. A transactional RPC locks the run row, validates the fence, applies projections, records the event/outbox and advances the revision. Repeating the same ID and same payload returns the committed result; a different payload for an existing ID fails. Resolve a lost acknowledgement by stable ID before reissuing work.

Transactions must cover these units:

- Opening: trade/position creation, fee/cash debit and probe account projection.
- Closing: position removal, complete gross/net/cost ledger, cash credit and probe account/drawdown projection.
- Birth: probe creation and reserve debit.
- Retirement: liquidation outcomes, final terminal probe record and reserve credit.
- Cohort replacement: durable batch outcome linking evaluated members, selection, retirements, allocations and newborns. A partially committed batch cannot be reported as complete or retried with new identities.
- Generation completion and lifecycle/risk transitions: event plus their authoritative projection/revision.

Use unrounded canonical economic values. Decode old database pnl_pct as percentage points; the new execution.exit.net_return and in-memory TradeRecord.pnl_pct are fractions. Never hydrate the latter directly from the former. WebSocket publication follows commit and is replayable by durable sequence; clients deduplicate and recover missed messages after reconnect. An outbox does not promise exactly-once network delivery, so UI idempotence remains necessary.

## DB-03A2A: implemented local command boundary

`db/command_protocol.py` prepares immutable, bounded JSON requests with stable
run/worker/command/entity IDs before submission. Economic amounts must already
be exact decimal strings. JSON floats are refused, including in configuration;
this is an intentionally restricted rehearsal protocol, not an implicit encoder
for today's engine configuration. Decimal spelling remains significant.
Factories validate UUIDs, revisions, operation keys, size/depth, relationships
and Unicode. Returned dictionaries are copies of the immutable request bytes.

`db/command_repository.py` accepts an explicitly injected transport. It imports
no application connection, configuration or credentials and is not wired into
the worker. It owns at most one RPC and one unresolved economic command per run.
Caller cancellation leaves the admitted task owned; a later valid reply updates
`last_receipt`. An error or invalid reply retains the original prepared command,
invalidates the local lease and blocks new economic submissions. Read-only
`get_command` compares the entire typed request and committed reply; a NULL
result remains unresolved. There is no automatic POST retry or new command ID.
The server hash is checked for shape only: PostgreSQL JSONB text is not Python's
canonical JSON encoding. Full request equality binds resolution to the command.

Creation acknowledgment grants no local decision lease because it may be an old
replay. A matching heartbeat grants a conservative deadline measured from local
request **start**, less a safety margin, never a fresh interval from reply time.
A late, failed or mismatched renewal leaves admission unavailable. Closing
admission is permanent; a pending renewal cannot reopen it. Readback is allowed
after closure and does not renew a lease. A matching terminal reply prevents
further mutations without fabricating closes, reserve transfers or fitness.

This module acknowledges commands; it does not install engine state, deliver an
outbox or restore a process after restart. Its future caller must install the
matching prepared candidate state before admitting another decision. Cancellation
can leave that caller without a direct return value, so it must reconcile with
`last_receipt` or the original pending command. The full coordinator must retain
that candidate until installation. Do not substitute current mutable engine
events for prepared plans.

The injected transport's future production implementation must pin the schema
and verified project, own its client and shutdown lifecycle, disable retries,
redirects and environment-proxy fallback, bound responses/timeouts and establish
that a successful response represents a committed transaction. The installed
PostgREST client's `schema()` creates a new client; do not assume it preserves an
injected client's settings. Actual PostgREST transaction-end preferences, exposed
schema, role/JWT grants and overlapping old clients require acceptance tests.
See [Python task ownership/cancellation](https://docs.python.org/3.12/library/asyncio-task.html#shielding-from-cancellation),
[HTTPX timeout phases](https://www.python-httpx.org/advanced/timeouts/), and
[PostgREST transaction termination](https://docs.postgrest.org/en/v14/references/transactions.html).

## Engine integration findings and next boundaries

Two reproduced incompatibilities now have explicit local v2 contracts; adopting
them into complete engine state remains required before wiring these commands:

- The current `buy_fill(100, 123.45, fee_bps=30, half_spread_bps=10,
  slippage_bps=10)` reports a float cash debit of `100.0`, but converting its
  notional and fee independently to decimal strings sums to
  `100.00000000000000734`. The exact SQL ledger correctly rejects that debit
  against a 100 balance. DB-03A2B's `usd-reference-decimal-v2` uses cash36,
  price/quantity18 and bps6 integer grids with conservative price/fee rounding
  and retained budget residuals. Pure plans and independent SQL recomputation
  agree without converting existing floats or changing v1 history. Signals/optimizer calculations
  can remain floats while authoritative economic arithmetic becomes consistent.
- CMA-ES currently records every distribution-source member as ancestry, while
  v1 rehearsal births allow only two parents; DE can also need four sources.
  V2 stores an ordered CMA distribution once and references it from child
  records, with separate template and algorithm-role bindings. The offline
  converter validates actual result metadata for all four optimizers rather
  than inferring roles from a flat list. No source truncation or runtime
  `parent_ids` rewrite occurs. See [the v2 contract](db-contract/README.md).

V2 run configuration binds its command version and exact execution policy.
The repository rejects version mismatches before transport, and SQL enforces
the same binding and validates complete entry/exit evidence. All lineage,
distribution, cash and position changes occupy one command transaction.
V1 support is retained only as fixture regression compatibility; a later
production migration must not retain a weaker mutation route around v2.

The 100-member normalized ancestry plan fits the bounded rehearsal payload,
but full engine replacements can carry many positions and additional metadata.
DB-03A2C must prove capacity for the complete plan before admitting a run; do
not split population replacement into partially committed commands. Iteration
and previous-distribution references remain provenance until complete cohort
and checkpoint state independently binds them. There is no automatic restart
restoration or optimizer-weight reconstruction in the lineage converter.

Blindly deep-copying `GenesisController` is unsuitable: immutable candle
snapshots contain `MappingProxyType` (which fails `deepcopy`), and controllers
own locks, feeds, callbacks and shutdown latches. Separate a data-only
`EngineState` from immutable decision evidence and operational resources.
Construct a complete candidate state and sealed command before submission;
install it by a prevalidated state replacement after matching acknowledgment.
Never let that installation reset a permanent worker-drain latch. Failure to
publish a committed event must not repeat economic operations or optimizer tell.

Plan semantic units independently of network acquisition: a protective pass
(including risk trips), ordinary decisions plus consumed signal cursors,
birth/death reserve transfers, full completed-cohort replacement, and lifecycle
or evidence-backed risk recovery. Preserve the existing guarantee that valid
protective closes can complete before a later candle outage stops decisions.

`_plan_closures` is a useful starting point but still retains mutable trade/event
references and must bind exact position IDs and base revision. Opening, birth,
retirement and replacement currently mutate before persistence. Cohort
completion and solver `tell`/`ask` also mutate results, candidate mappings and
private RNG state. Introduce controlled strategy forks with alias-isolation and
deterministic progression tests. In-process forks are not a versioned durable
checkpoint; do not persist arbitrary pickles. Retired historical terminal
capital is a separate fact from current cash ownership transferred to reserve.

### DB-03A2C1: explicit in-process state forks

`core/engine_state.py` supplies `capture_engine_state(controller)`, which waits
for the existing tick/recovery lock and performs its capture synchronously
inside that lock. A started-but-still-starting controller is rejected because
the current startup preparation is not protected by this lock. Call from the
controller's owning event loop, without already holding the lock. This does
not add thread safety or replace lifecycle coordination.

An `EngineSnapshot` owns a sealed detached graph. Its public identity properties
are immutable values; `fork()` returns a new `EngineDraft` with independent
mutable containers, probe data, shared indicator history, cohort and optimizer
state. Probe data records its relationship to the one draft history without
carrying a runnable `Probe` or bound clock. Capture reads raw attributes and
never calls reporting properties, constructors, `attach_candle_history`, feeds,
name generators, or optimizer `ask`/`tell`. Reporting currently trims retained
closed trades, and attaching history resets cursors/intents, so neither is a
safe cloning mechanism. Known fields are explicitly classified; unknown
fields, resource-bearing graphs and unsupported solver versions fail closed.

| Captured data | Excluded operational resources |
| --- | --- |
| Account/position/trade data, retained counters and equity history | Probe clocks, network feeds and feed cursors |
| Genomes, configuration, source quotes/slots and signal cursors/intents | Event/persistence callbacks, clients, tasks and locks |
| Shared recursive EMA state, completed/pending candles and evaluation membership | Wall-clock pacing origin and new wall/monotonic observations |
| Reserve/baseline, generation aggregates and risk trip/recovery records | Running/paused/draining/feed-closed latches and persistence-ack flags |
| Optimizer candidates, private RNG state and pending CMA ask vectors | New identity/name allocation and durable ownership/lease authority |

`core/state_components.py` detaches nested mutable values even inside frozen
records: signal dictionaries, historical genomes and candle mappings cannot
alias the source or another draft. It preserves the optional persisted-offspring
flag without triggering trade-retention side effects. Controller and probe
identity relationships and shared-history ownership are checked before sealing.

`core/strategy_fork.py` supports exactly the four current optimizers and their
evaluation state. It preserves Python and NumPy random-generator state, including
Gaussian caches, and copies solver arrays, candidate maps and configuration.
It deliberately bypasses copy/pickle hooks. The installed **cmaes 0.13.1**
[`CMA` serialization implementation](https://github.com/CyberAgentAILab/cmaes/blob/v0.13.1/cmaes/_cma.py)
omits `_rng` and creates a fresh unseeded generator on restoration. Therefore
ordinary `deepcopy` is not a deterministic fork of that solver. The reviewed
helper pins its private-state shape/version and copies the actual RNG state;
unknown versions require renewed compatibility tests. Python's
[copy documentation](https://docs.python.org/3.12/library/copy.html) explains
custom copy/serialization behavior, and its
[lock contract](https://docs.python.org/3.12/library/asyncio-sync.html#asyncio.Lock)
defines the event-loop synchronization used here.

This is **in-process data isolation only**. The current engine is not replaced
or run on drafts. Captured binary64 values are not silently converted to the
new exact ledger policy. No install, transaction submission, durable checkpoint,
restart restoration or event-delivery API is provided. Snapshot pickling is
explicitly rejected. Original monotonic quote times are retained as evidence,
not granted freshness in another process.

The remaining C2/C3 boundaries must supply frozen decision inputs and controlled
clock/identity/name sources, stage exact protective and ordinary decisions,
birth/death and full cohort/recovery transitions, bind complete state/events to
one command, and install only its matching acknowledgment. Cancellation must
retain the candidate even if the repository later advances its revision. A
lost reply requires original-ID readback; absence is still uncertain. Verify
candidate reserve against the committed result. Installation or publication
failure cannot repeat optimizer tell or economic writes, and a drain latch
cannot be reset by old candidate state.

**Measured capacity constraint:** with 100 CMA retirements/births and one shared
distribution, representative zero-fee integer-valued close evidence produces
301 operations / 112,499 bytes at one position per member, 401 / 170,199 at two,
and 501 / 232,899 at three. Three assets per probe are within the current gene
limits. The same three-position shape with budget 100, reference
123.456789012345678901, exit 124.123456789012345678 and fee/spread/slippage of
30/10/10 bps takes 390,099 bytes, already exceeding the 262,144-byte cap before
full state/events. These are representative payload fixtures, not a trace of
the current float engine or a universal byte estimate. Four/eight-position
stress cases exceed the current per-probe asset limit and cannot stand in for
supported genome acceptance.
Research and test bounded full-transition admission, peak fork memory/latency,
checkpoint codecs and solver version upgrades before changing limits. A larger
payload allowance alone does not establish transaction latency or host capacity.

## Forward migration and authorization requirements

Current `run_id` columns are nullable and lack colony foreign keys. Child records have scalar probe FKs that do not establish matching owner/run. Current authenticated-owner policies allow direct insertion, mutation and deletion of worker-owned records. Service-role writes bypass RLS.

For the new contract:

- New state/event/command tables require non-null versioned identities, owner/colony FKs, unique event/sequence constraints, valid states/revisions and finite money/JSON limits. Use targeted owner/run/sequence indexes.
- Establish referenced unique composite keys such as colonies `(id,user_id)` and probes `(id,user_id,run_id)`, then corresponding composite FKs on child records. Parent lineage needs validated source-edge ownership or equivalent RPC/trigger checks; a JSON array alone does not enforce it.
- Audit legacy null, orphaned and cross-run rows before validation. Do not silently assign owners, create replacement colonies, delete rows or reinterpret history. Stage forward constraints where needed; retain a documented historical compatibility path.
- Keep authenticated owner-only SELECT. Remove direct authenticated/anonymous mutation paths for authoritative worker tables. Revoke default PUBLIC execution on privileged functions; grant only intended worker RPC execution. Restrict service-role direct VN writes or enforce a database guard so previous worker versions cannot bypass fencing. Do not change unrelated schema or role grants.
- Privileged functions use a fixed safe search path, qualified object names and explicit identity/payload validation; no dynamic SQL. Replace broad browser deletion with an authorized archived-run operation that preserves the chosen audit policy.
- Rehearse migrations against isolated PostgreSQL, including locks/timeouts, grants, RLS and ownership constraints, before target verification and authorized application to the Dashboard database.

## Minimum acceptance tests

Use actual isolated PostgreSQL roles/connections as well as fast unit tests:

- Two processes compete for one lease; only one owns it. After expiry/takeover, a delayed old-owner mutation and stale heartbeat are rejected.
- Kill at each economic boundary, including during a population batch. No double debit/credit or fabricated completion occurs.
- Simulate committed transaction plus lost HTTP acknowledgement. Same-ID replay produces one result; changed-payload replay fails.
- Cross-owner and cross-run reads/writes/relationships fail; browser direct mutations and stale service-worker paths cannot bypass the contract.
- Interruption preserves original configuration and unresolved rows, disables controls, and never invokes worker reconstruction or optimizer tell.
- Reconnect replays durable events without duplicate rows; unavailable state remains distinct from an empty successful result.

## What full resume later requires

A versioned atomic checkpoint must include probe cash/open positions and lifetime counters; reserve ownership; historical peak/drawdown; risk baseline/trip/recovery; cohort membership and pending/completed results; generation seals/aggregates; pending commands and event cursors; exact shared candle/EMA origin and recursive state; equity sample/gap state; signal/decision cursors; search epochs and private RNG state; and solver-specific state including CMA ask vectors/covariance/paths and PSO/DE mappings. Record code/dependency/policy versions and dataset identity.

Synthetic/replay continuation additionally requires frame cursor, per-asset delivery watermarks and exact feed RNG state. A seed alone does not restore the current state. Paper restart must obtain new source evidence, never reuse process-local monotonic timestamps, discard expired pending intents and ordinarily abort the interrupted evaluation without tell. Restoring shared EMA from an arbitrary short history changes the strategy. Full live execution would additionally need on-chain reconciliation and remains unauthorized.

Before integration, deepen research on database/PostgREST role inheritance and
custom worker credentials, exact numeric serialization versus the float engine,
lease durations under measured lock/transport latency, bounded event retention
and replay pagination, and versioned checkpoint compatibility. DB-03A1's cash
and position fixtures do not persist complete genomes/cohorts/metrics/RNG state,
and its temporary-cluster backend-termination checks are not power-loss or
production host acceptance.

Hosting then needs a reviewed Linux image, capacity/drain measurements, shared-provider quota budgeting, isolated secrets and exact origins/TLS endpoints, readiness/alerts, and demonstrated SIGTERM/SIGKILL/release-overlap/rollback behavior. A local disk, successful history read or idle health response is insufficient.

## Related dashboard gaps

Keep `/USDC` asset IDs stable but label the versioned model as USD reference accounting. Report cash separately from marked equity and net return; legacy cost/unit metadata remains unknown. Add append-only versioned evaluation/member/result/selection records for historical evolution analysis. Birth-generation summaries and common-window optimizer results are distinct. Preserve dataset/config/code/cost-policy identities, pagination and nullable diagnostics; do not compare heterogeneous or aborted windows as equivalent performance evidence.
