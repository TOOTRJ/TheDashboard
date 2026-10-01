# Safe durability and later worker hosting

Read-only source review, September 30, 2026. This is a future implementation plan. The FILL-01A execution JSON column records accounting detail; it is not an atomic ledger, ownership lease or executable checkpoint.

## What is durable today

`db/repository.py` uses separate service-role PostgREST requests, serialized by an in-process asyncio lock. The manager keeps controller objects, tasks, locks and callbacks only in memory. `server/app.py` creates a new empty manager at process startup; its lifespan performs no recovery. Ownership checks prove the authenticated user owns the current in-memory controller, not that this process exclusively owns its database records.

Probe births, trades, occasional probe metrics, lifecycle changes and sealed generation summaries are persisted. Periodic `simulation_status` messages are broadcast without a database write. The runtime JSON is a latest diagnostic snapshot and is overwritten at later lifecycle/cohort/risk transitions. `last_evaluation` is not append-only evaluation history. The repository cache `_colony_config` starts empty: a newly constructed repository must not update old-run details using that empty cache or it will erase the original configuration.

The cash reserve, exact account transitions, signal cursors, shared indicator state, market/optimizer RNG state and complete optimizer state are not checkpointed. Older persisted trade P&L may be rounded, while engine cash uses unrounded values; FILL-01A preserves new trade values without display rounding. Latest probe cash can lag multiple trades. Reconstructing current cash or reserve from those rows is unsafe. Current history readback and mock repository tests do not prove restart resumption or database RLS correctness.

## Recommended first durability release

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

Hosting then needs a reviewed Linux image, capacity/drain measurements, shared-provider quota budgeting, isolated secrets and exact origins/TLS endpoints, readiness/alerts, and demonstrated SIGTERM/SIGKILL/release-overlap/rollback behavior. A local disk, successful history read or idle health response is insufficient.

## Related dashboard gaps

Keep `/USDC` asset IDs stable but label the versioned model as USD reference accounting. Report cash separately from marked equity and net return; legacy cost/unit metadata remains unknown. Add append-only versioned evaluation/member/result/selection records for historical evolution analysis. Birth-generation summaries and common-window optimizer results are distinct. Preserve dataset/config/code/cost-policy identities, pagination and nullable diagnostics; do not compare heterogeneous or aborted windows as equivalent performance evidence.
