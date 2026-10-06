# Atomic read projections, durable relay and archive rehearsal

DB-03A2D3A, reviewed 2026-10-05. This is an **isolated, inert contract**, not an
applied migration, production browser reader or hosted worker. The SQL is
outside `supabase/migrations`; both fixture files require the isolated runner
marker. Install `002_read_projections.sql` only after the fresh fenced-command
fixture and before any commands exist. It refuses asynchronous backfill over
existing journals. Production adoption still requires D3B/D3C and DB-03A3.

## Authority and transaction boundary

The journal insertion trigger materializes run, probe, trade, sample and
completed-evaluation versions in the economic command transaction. Each row
references the exact owner/run/command/revision composite. Indexes support owner
pagination and latest probe/trade lookup. Raw checkpoints, optimizer graphs,
RNG, command requests and caller-supplied display payloads are not browser data.

Replaying an acknowledged original command does not insert another version.
A projection failure aborts the economic mutation, checkpoint, journal and
outbox together. A later outbox failure also aborts earlier trigger effects:
[PostgreSQL triggers execute within the original transaction](https://www.postgresql.org/docs/17/trigger-definition.html).
Production tests must additionally establish PostgREST transaction-end behavior
and independent committed readback; a JSON reply alone is insufficient.

| Projection | Meaning and boundary |
|---|---|
| Runs | Every command revision, status, reconciliation flag, policy/version, reserve, reference equity, total born/living account counts and retained open positions. Current optimizer population is not the lifetime count. Create/interrupt equity is unavailable; a reference mark carries its source timestamp and does not assert present freshness. |
| Probes | Checkpoint-member versions plus terminal versions for members removed by replacement. Exact account cash, initial cash, equity basis, separate terminal cash, lineage and declared metric availability. |
| Trades | Every opening/closing operation version; key includes a padded operation ordinal so both operations can coexist at one command revision. Collapse current views by `data.id`, not version key. Raw exact entry/exit plans retain costs and rounding evidence. |
| Samples | Post-protection, pre-decision samples only. This differs from legacy sampling; preserve `sampling_policy`, source timestamp, quote sequence and equity basis when comparing histories. |
| Evaluations | Completed cohort and selection evidence once when it changes, with frozen terminal cash for its members. Older evaluations survive replacement. Research float64 scores remain explicitly tagged; unavailable current fitness is not fabricated. |

Amounts remain exact **USD-reference** decimal strings under
`usd-reference-decimal-v2`, with uncalibrated cost assumptions. These are not
on-chain token balances or USDC wallet records. Retirement transfers cash to
reserve and zeros the old account. The trigger reconstructs ordered birth,
open, close and retirement cash flows and verifies them against the accepted
checkpoint before retaining pre-transfer terminal cash. Run equity never adds
that terminal cash to reserve a second time.

For removed members, prior peak/drawdown/closed-trade fields may precede the
final liquidation. Their `metrics_basis=last_observed_before_replacement`
prevents presenting them as fresh final metrics. The completed evaluation and
terminal cash remain separate evidence. A future richer final metric projection
must carry independently validated evidence rather than relabel those fields.

## Curated owner reads

`vn_read.page(run,kind,through_revision,after_revision,after_key,max_rows,max_bytes)`
derives the owner from `auth.uid()` and applies owner/run predicates to every
query. Allowed kinds are runs, probes, trades, samples and evaluations. Readers
pin the first returned revision for all subsequent pages. Append-only versions
cannot appear later below that cutoff. Pages are limited to 100 rows and 65,536
UTF-8 bytes, including the envelope; a single oversized record fails explicitly.
The version tables remain private. Core authenticated SELECT grants are removed
inside this fixture when curated reads are installed.

The security-definer owner bypasses its own table RLS, so explicit owner filters
and role-denial tests are required; enabling RLS alone is insufficient.
[PostgreSQL row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).
Only the authenticated role executes page/events/archive; anon and service_role
cannot execute browser reads, and none receives projection DML or helper access.

The inert TypeScript module `src/lib/probes/durable-read-model.ts` validates
owner/run/version/currency, monotonic cursors, snapshot continuity, response and
collection limits. It publishes a complete snapshot only, supports cancellation
and a finite deadline even if an injected RPC ignores its signal, and keeps
latest entity selection separate from samples/evaluations. USD money and rational
drawdown display use BigInt rounding. Tagged float64 is decoded only for research
scores/genes. It imports no Supabase client and is not selected by existing UI.
Legacy float records continue through their existing reader without conversion.
A future injected RPC must bound its actual network response before parsing.

## Durable acceptance and replay

`vn_read.accept_event(owner_id,run,command_id,event_index)` is a separately scoped
privileged relay capability, distinct from the seven economic command RPCs. SQL
fetches the original committed outbox event; the caller submits identity only.
Stable event identity is `run:command:index`. Under the run row lock, first
acceptance allocates a per-run monotonic relay sequence. Duplicate original
acceptance returns the same sequence and receipt. Concurrency cannot allocate
duplicate sequences. Acceptance order need not equal command/event order.

Economic outbox ACK advances only for an already accepted durable relay row;
the existing command contract still requires a contiguous economic event prefix.
`DurableRelayPublisher` validates the exact original receipt before returning to
the coordinator. It performs no retry or socket broadcast. A lost acceptance or
ACK reply remains original-identity work owned by the coordinator.

`vn_read.events(run,through_sequence,after_sequence,max_rows,max_bytes)` derives
browser ownership and pins a relay cutoff. A delayed event receives a higher
sequence, even if its command revision is old, so it cannot slip below a returned
replay cursor. Readers deduplicate by stable event ID and poll a fresh cutoff on
reconnect. Command revisions remain attached to events for readback, but they are
not an asynchronous delivery cursor. Separate HTTP requests take separate
snapshots under [PostgreSQL Read Committed](https://www.postgresql.org/docs/17/transaction-iso.html);
the cutoff is explicit application evidence rather than an assumed cross-request
transaction. Row/byte bounds and single-record errors match projection pages.

Persisted acceptance permits browser replay with zero subscribers. A WebSocket
send is only an optional wakeup. Retention, consumer progress, pruning and a
production one-attempt relay transport remain separate reviewed dependencies.
No TTL, journal deletion or shared schema exposure is introduced here.

## Run-specific non-destructive archive

`vn_read.archive_run(run,expected_revision,request_id)` locks the exact JWT-owned
run and records presentation metadata only. Eligibility requires a stopped
v4/v5 run, no interruption marker, and a terminal checkpoint and batch journal
at the current expected revision. Starting/running/paused/risk-halted, interrupted,
failed or checkpoint-uncertain runs cannot be archived. Repeating an original
request is idempotent; reuse for a different run/revision or a second archive
request for the same run fails explicitly.

The core marks even orderly stops `requires_reconciliation=true`. Archive keeps
that warning in the receipt along with known-terminal classification, retained
open-position count and exposure disclosure. It does not clear reconciliation,
resume a run, liquidate holdings, transfer money or delete any evidence. A stopped
run with eight known holdings is tested and remains intact after archive.

The old unused four-table `deleteAllProbes` browser helper is removed. Existing
legacy rows are preserved. Legacy archive eligibility remains D3B: saved status
alone does not prove that historical writers are drained or holdings reconciled.
The fixture's archive RPC is not wired to a production button.

## Remaining production preparation and research

1. **D3B: reviewed forward DDL and exact legacy privilege/classification cutover.**
   Generate a reviewed production object manifest from the accepted v5 boundary,
   rather than copying the isolated multi-version fixture. Rehearse captured
   table/column/inherited/SET ROLE/MAINTAIN paths, defaults and unrelated-object
   preservation. Preserve all five public VN tables as owner-readable evidence.
   Classify unmanaged legacy runs, missing metrics/policies and retained holdings;
   never hydrate authoritative state from floats or guess ancestry.
2. **D3C: one selected service authority and compatible operator/read flow.**
   Replace every startup/status/risk/control writer and remove EventPersister from
   economic authority. Add typed owner run discovery, compatible legacy/new detail
   displays, archive discovery and event-page validation/deduplication. Wire the
   new protocol only after migration acceptance; old workers must fail closed.
   Exercise locks, overlapping releases, two real user sessions and rollback.
3. **DB-03A3:** exact target verification, reviewed migration/rollback artifacts,
   approved hosted gateway/schema cache/transaction-end and custom worker-role
   acceptance, then controlled full end-to-end application. The schema remains
   absent on the hosted Dashboard at this checkpoint.
4. **Deep substantial research:** bounded retention and replay backlog/consumer
   cursors, compact checkpoints, production query cost/storage/lease latency,
   legacy classification and sample comparability, and least-privilege relay versus
   economic worker credentials. The local 256 MiB fixture exhausted space when
   retaining multiple independent dense traces. Tests now reset only their owned
   disposable fixture between complete traces; this is not a production retention
   solution or evidence of production capacity.

Additive rollback retains all acknowledged journals/projections and legacy rows,
closes admission and drains owned work. Restore only a compatible reader/service;
never revive unfenced legacy writers over v5 runs or undo economic balances.
[Cutover plan](PRODUCTION-CUTOVER-PLAN.md) and [TODO](../../TODO.md) retain the
remaining acceptance gates. PostgREST profile exposure is a separately scoped
configuration change, not implied by creating an SQL schema:
[PostgREST 14 schemas](https://docs.postgrest.org/en/v14/references/api/schemas.html).
