# DB-03A1: isolated fenced transaction contract

This directory is an **executable design rehearsal**, not a Supabase migration.
The application does not load this SQL. It does not repair production persistence
until the complete repository, engine and browser write paths are cut over.
Never copy this file into the migration directory as a lease-only patch.

Run the real PostgreSQL tests from `services/vonneumann`:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
  python -m tests.postgres.run --allow-isolated-postgres
```

Use the isolated worker Python environment. The harness requires an already
running local Docker daemon and the already available PostgreSQL 17.6 image;
it never installs tools, downloads images, starts Docker, or connects to a
configured PostgreSQL/Supabase URL. See [harness isolation](../tests/postgres/README.md).
Ordinary worker test discovery skips these opt-in tests.

The DB-03A2A Python command layer is now tested against this fixture through an
allowlisted, fixture-only SQL transport in `tests/postgres/test_command_adapter.py`.
`db/command_protocol.py` seals command identity/payloads; `db/command_repository.py`
owns one request and resolves uncertain outcomes without resubmission. Fast
protocol/repository tests also run in ordinary discovery. Neither module is
imported by the application runtime or creates a production connection.
See [implemented boundary and engine incompatibilities](../PERSISTENCE-RECOVERY-PLAN.md#db-03a2a-implemented-local-command-boundary).

## Contract boundaries

The SQL creates only the disposable `vn_durability` schema. Minimal account,
position and reserve projections exercise economic transactions without
pretending the existing `public.vn_*` tables have been migrated. Fake users
and client roles belong to the disposable cluster. No real user or application
credential is read.

The server owns authoritative cash/reserve changes. The worker proposes typed
operations with stable command/run/entity IDs allocated **before** submission.
It does not send arbitrary table names, column updates, or a trusted hash.
The request, economic changes, committed response, journal sequence and revision
commit or roll back together. One batch occupies one revision and one journal
entry, even when it contains many operations.

| RPC | Behavior |
| --- | --- |
| `create_run(owner, run, worker, command, config, initial_cash, lease_seconds)` | Atomically inserts the run, initial reserve, lease at fence 1, and creation journal at revision 1. A competing creator cannot replace ownership or reset funds. |
| `heartbeat(owner, run, worker, fence, lease_seconds)` | Locks the run, checks database time after the lock, and renews only an unexpired matching active lease. It does not advance the economic revision. |
| `commit_command(owner, run, worker, fence, expected_revision, command, payload)` | Verifies ownership/fence/lease, resolves exact repeated commands, rejects stale revisions, applies the entire batch, and appends the committed result. Expiry is rechecked after operations. |
| `get_command(owner, run, command)` | Read-only resolution available after lease loss. Returns the original request, server-computed hash and committed result, or SQL NULL when no committed row is visible. |
| `interrupt_expired(owner, run, expected_revision, command)` | Serializes with other operations, verifies expiry and revision, increments the fence, records `worker_interrupted`, and marks the run failed/requiring reconciliation. It preserves all economic projections and original config. |

There is deliberately no lease takeover/resume RPC. An expired run is inspected
and interrupted; a separate experiment needs a new ID and funding declaration.
`stopped` and `failed` runs cannot accept new economic commands. Interruption
does not close positions, retire probes, reclaim balances, or score candidates.
Legacy production runs without this contract are not implicitly adopted.

Repeated `create_run` returns its original committed response; it does **not**
renew ownership. A worker must verify its lease before making decisions. A
stale worker's mutating RPC fails even if its command previously committed;
the read-only resolver establishes what happened after lease loss. A missing
resolver row is not proof that an earlier request failed: it may still be
in flight in another transaction. Never issue a new ID on that evidence.

Creation/heartbeat replies currently omit the lease deadline. Before any worker
integration, expose the authoritative deadline with a clock/latency policy or
implement a conservative request-start monotonic deadline. A delayed acknowledgment
must never grant a fresh full lease interval for process-side decisions.

All mutating RPCs are intended to be one short PostgREST transaction. PostgreSQL
retains the run lock until transaction end. No newer fence can pass that lock
before an older transaction commits or rolls back. A caller that wraps an RPC
in a long explicit SQL transaction can delay visibility; the production cutover
must set statement/idle-transaction timeouts and must not make trading decisions
from an uncommitted result. Passing a lease check does not grant authority for
later independent work.

## Typed batch operations

`payload` has exactly `{"version":1,"operations":[...]}`. There must be 1–256
operations and at most 256 KiB of PostgreSQL JSONB text. Every operation has
exact keys; extra or missing keys fail the entire transaction.

| Kind | Required fields in addition to `kind` | Atomic effect |
| --- | --- | --- |
| `birth` | `id`, `cash`, `parent_ids` | Create an account and debit reserve. Up to two unique existing parents must belong to the same owner/run. Paused/risk-halted runs reject births. |
| `open` | `id`, `account_id`, `asset`, `quantity`, `notional`, `fee` | Insert a position and debit notional plus entry fee from a nonretired account. Requires running status, sufficient cash and no other open position for that account/asset. |
| `close` | `id`, `proceeds`, `fee` | Preserve the position record with its exit values and credit net proceeds exactly once. Zero proceeds explicitly support terminal loss. |
| `retire` | `id` | Require no open positions, credit remaining account cash to reserve, zero the account cash and retain the retired account. |
| `lifecycle` | `status` | Change to running/paused/risk_halted/stopped/failed in the same transaction. Starting is creation-only. Terminal changes retain reconciliation requirements. A risk halt cannot be cleared or bypassed through pause; recovery is unavailable in this rehearsal. |

Close/retire/birth sequences can represent an economic replacement batch. A bad
last child rolls back earlier closes, reserve credits and retirements. This
does **not** yet represent production cohort membership, selection evidence,
generation seals or optimizer state; those must join the atomic boundary at
integration rather than be saved afterward.

Balances use exact PostgreSQL `numeric`; JSON money/quantity fields are decimal
strings, never JSON floats. This rehearsal permits 0–10^36, at most 36 decimal
places, no exponent notation/sign/leading zeros, and bounded string length.
These are provisional protocol limits, not researched market or token limits.
Initial capital, birth capital, quantity and entry notional must be positive;
fees must be nonnegative; close fees cannot exceed proceeds. There is no silent
rounding, synthetic liquidation or assumption that one USD reference unit is an
on-chain USDC balance. Pricing, market freshness, fee calibration and allowed
asset identities remain application responsibilities to bind at cutover.

The fingerprint covers owner/run/command identity, command kind, worker/fence,
expected revision and payload as applicable. SHA-256 is computed by PostgreSQL
over its UTF-8 JSONB text. JSON key order and whitespace are normalized; array
order and decimal-string spelling remain significant. `"1"` and `"1.0"` are
conservatively different requests. Version 1 numeric formatting in arbitrary
configuration also remains significant. The full stored request is compared
as well as retained, so hash collisions cannot authorize a changed request.
This is a PostgreSQL-17 protocol representation, not a promise of cross-language
JSON canonicalization. A versioned client encoder and cross-version hash
fixtures are required before runtime use.

## Privilege and identity boundary

The fixture uses independent connections for `anon`, `authenticated`, and
`service_role`. The latter really has `BYPASSRLS`, but has no direct table DML,
TRUNCATE, or journal mutation privilege. It can execute only the five explicit
RPCs. `authenticated` has owner-only SELECT and no RPC execution; `anon` has
neither schema access nor RPC execution. Every relationship includes owner/run,
including parent edges and positions' account references.

Tables and privileged functions belong to a dedicated NOLOGIN, non-superuser
role without client membership. Function search paths put `pg_catalog` first
and `pg_temp` last, and all application relation references are qualified.
PUBLIC execution is revoked in the same transaction as creation. There is no
caller-settable session flag that bypasses the contract.
The dedicated owner's global function default also removes PUBLIC execution:
a schema-only default revoke cannot subtract PostgreSQL's global default.
The installation marker used by the test runner only reduces accidental manual
execution; it is not a security boundary or an authorization mechanism.

The worker RPC's owner argument comes from trusted authenticated server code.
This protects owner/run relationships and browser isolation; it does **not**
make a compromised service-role credential incapable of impersonating another
owner. Credential scoping, custom worker role feasibility, exposed RPC schema,
JWT validation and actual Supabase grants require a separate target-specific
review. No global/shared account role is changed by this rehearsal.

## Remaining production cutover, in order

1. **Inventory real legacy data and grants read-only.** Count null/orphan/cross-run
   identities; resolve the existing locally modified historical migration
   without overwriting it. Record all VN writer paths, inherited grants, browser
   deletion, indexes, trigger behavior and current API ownership checks.
2. **Define complete engine transaction plans.** Prepare births, opens, closes,
   terminal retirement and whole cohort replacement without first mutating
   authoritative in-memory balances. Include genomes, valuation/risk metrics,
   evaluation membership/results/selection, generation state and source/code/
   cost-policy identities. Reconcile DB numeric values with the float engine
   explicitly; never round the ledger merely to satisfy this prototype.
   Integrate ENG-05 risk-trip identity, recovery acknowledgment and fresh-source
   evidence before introducing a risk-recovery command. Persist resolved genome
   limits and allowed assets before enforcing complete entry policy in SQL.
3. **Integrate the local command adapter with complete staged engine state.**
   The injected-transport adapter is implemented and rehearsed under DB-03A2A;
   production transport, state installation and publication remain open. Allocate
   stable IDs before submission, bind canonical payloads, compare committed
   replies, freeze decisions on uncertain outcomes, resolve by the original ID,
   and publish only after commit. Readiness remains unavailable until this flow
   and every write path pass acceptance. No automatic retry with a fresh ID.
4. **Prepare the complete forward migration and compatibility plan.** Map these
   projections to actual VN tables; stage owner/run FKs without guessing old
   owners or deleting history. Revoke exact VN direct writes for authenticated
   and service-role paths alongside the RPC adapter. Remove/replace browser
   `deleteAllProbes` with a reviewed archive policy. Preserve unrelated grants.
5. **Prove integrated recovery and release overlap.** Test real engine → RPC →
   database → readback/UI; interruption with positions and evaluation cohorts;
   stable event replay after reconnect; lost acknowledgments; expired workers;
   SIGTERM/SIGKILL and migration/rollback. Verify the exact Dashboard targets
   again before any authorized cloud application.

Do deeper research before finalizing lease/heartbeat durations and measured
latency, numeric precision and token units, retention/pruning of command
evidence, journal size and indexing, browser event pagination/replay, legacy-run
classification, service-role grant inheritance, and versioned solver/EMA/RNG
checkpoints. The 30-second default lease and 120-second cap are test contract
parameters, not a measured hosting recommendation.

The tests establish SQL transaction/permission/concurrency behavior in one
disposable PostgreSQL cluster. They do not establish actual Supabase/PostgREST
privileges, network exactly-once delivery, provider correctness, process restart
restoration, power-loss durability, host capacity, or trading profitability.

## Primary references

- [PostgreSQL row locks](https://www.postgresql.org/docs/17/explicit-locking.html):
  locks serialize changes through transaction end; they do not by themselves
  make separate application requests atomic.
- [PostgreSQL clocks](https://www.postgresql.org/docs/17/functions-datetime.html):
  `now()` is transaction-start time, while `clock_timestamp()` observes current
  time during execution; evaluate expiry after lock waits.
- [Security-definer functions](https://www.postgresql.org/docs/17/sql-createfunction.html):
  fixed safe search paths, controlled ownership and explicit execution grants.
- [Default privileges](https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html):
  revoke PUBLIC execution in the dedicated owner's global defaults; per-schema
  defaults alone cannot remove a global grant.
- [Row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html):
  `BYPASSRLS` does not replace object permissions; role bypass must be tested.
- [Binary hash functions](https://www.postgresql.org/docs/17/functions-binarystring.html):
  the SHA-256 primitive used for stored request fingerprints.
