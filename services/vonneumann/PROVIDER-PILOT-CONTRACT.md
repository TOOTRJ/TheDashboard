# Bounded provider paper pilot

The opt-in `ProviderPilotOwner` adds a supported admission policy to the fresh
version-5 paper owner. It retains the two EMA genes, eight members, complete
economic and optimizer evidence, source provenance, acknowledgment ownership,
and stable outbox identities. It is not selected by the production service and
does not fetch providers, restore state, sign transactions, or trade a wallet.

The dense capacity traces showed that later PSO and CMA replacements cannot fit
the existing command limit. Even earlier states need an explicit stop reserve:
a stop may append an aborted evaluation and can exceed the previous command.
This pilot admits only a single evaluation window and proves terminal byte
capacity for each prospective state before dispatch. It does not promise that
every legal price or configuration can advance indefinitely.

## Local policy and admission

| Bound | Policy |
| --- | --- |
| Genes and population | Existing fixed v5 profile: two EMA genes, eight members, SOL/USD |
| Accepted quote budget | Default 3,601, configurable down to 1 |
| Total command budget | Default 4,000, configurable down to 4; includes creation, bootstrap and the reserved stop |
| Quote timeline | At most 3,600 seconds after the first installed protective quote |
| Replacement/search epoch | One replacement; no restart, resume or recovery in this pilot |
| Per-operation allocations | At most nine UUIDs and eight bounded names |
| Terminal allocations | Empty UUID and name tuples; one distinct reserved command ID |
| Wire/retention limits | Existing limits unchanged: 262,144 bytes, 64 positions, 32 accounts; base owner ledger remains 4,096 IDs |

`ProviderPilotLimits` is a frozen local policy. It does not add fields to, or
reinterpret, the acknowledged v5 configuration. The owner copies its limits and
validates allocations before asynchronous work. The reserved stop identity
cannot be used by another command or as an economic allocation. Ordinary work
can never spend the final reserved command slot. Uncertain submissions remain
counted and retain their original identity; heartbeat and event acknowledgments
do not spend economic-command identities.

Each protection remains authoritative for account/member risk and source
ordering. `decision_due()` and `decide()` suppress an ordinary decision only
when the installed state has no work for that identical accepted owner ticket.
Useful work includes a newly eligible completed candle, current-history warmup,
a pending action needing consumption or cleanup, and the evaluation deadline.
Halted runs select retained exits only. New candles use the shared five-second
completion margin, rather than the raw 15-minute boundary. A skipped decision
does not prepare a candidate, advance an indicator or solver, dispatch an RPC,
or consume the supplied unused command ID.

This removes the mandatory second command for every plain quote. Creation and
bootstrap plus 3,601 protections, a handful of candle/fill decisions, and stop
can fit the bounded ledger. Actual command admission enforces the bound even
if controls or signal patterns require more work. This arithmetic is not a
one-Hz operating recommendation or a measured provider/database deadline.

## Constructive stop reservation

Before dispatching every prospective nonterminal candidate, the owner prepares
a detached complete v5 stop from that candidate's sealed state. The witness
uses empty allocations and maximum supported clocks: event second `10**10`,
wall microseconds `10**16`, and monotonic `float(10**10)`. The witness remains
inside the pure helper; it is never installed, published, returned as a
candidate, or submitted to the repository.

The reserve is the greater of the witness's PostgreSQL-spacing payload bytes
and compact ASCII candidate bytes, plus nine bytes. Both candidate limits matter:
JSON Unicode escaping can make the ASCII view longer than the UTF-8 SQL view.
The margin covers seven characters for an actual wall timestamp's optional
`.ffffff` suffix and two for the longest legal subnormal monotonic hexadecimal
form. Newly written integer seconds and microseconds already have maximal width
in the witness. Newly written aborted-cohort float timestamps are whole seconds;
their legal widths are bounded by the witness. Existing before-state, source,
prices, genomes and historical fields are unchanged. No identities, names or
economic marks are newly allocated by stop.

If either complete stop representation plus this margin exceeds the unchanged
cap, the prospective state is refused without installation or solver/RNG
advancement. A later actual stop is prepared again from the installed seal
using current owner clocks and the reserved identity. Its size is checked against
the retained reservation. The existing semantic validators, repository, lease,
receipt binding and publication rules still apply.

The old exact builders now identify explicit wire/retention capacity failures
with `ExactCapacityError`, a subclass of the existing error. Existing v3/v4/v5
error catches and rejection semantics remain compatible. Invalid evidence or
an arbitrary candidate is not converted into a capacity refusal.

## Refusal, terminal control and settlement

Pilot limits have a separate `refusal_reason` latch. Completion of generation 1,
byte/identity policy refusal, or unsupported pilot control stops new ordinary
work. `stop_available` may remain true after the original command and events
settle. A refused unsubmitted plan releases its unretained quote/history window
so that a discarded ticket cannot later expire the independent stop channel.
Evidence still retained for uncertainty or publication is preserved.

Existing hard failures keep their stricter latch: invalid clocks, stale source
evidence, bad quote identity, task interruption, or rejected submission can
close both ordinary and terminal admission. A stop reservation proves byte and
identity capacity, not provider freshness, lease availability, successful network
delivery, or safety after an interrupted process. Readback does not renew a lease;
a confirmed heartbeat may be required after reconciliation. No latch is reopened.

Pause retains holdings and aborted evaluation evidence. Resume/recovery/restart
are outside this single-window pilot. `stop()` owns the original reserved command
through caller cancellation, lost acknowledgment, installation and event delivery.
It cannot compete with a retained command or event prefix. Stop records `stopped`
and retains positions, cash and reserve; it does not fabricate liquidation.

## Acceptance and follow-up research

Offline tests use literal provider records, real solver forks and real command
validation with fake RPC/outbox I/O. They cover every solver through a dense
first replacement, complete stop bounds, legal Unicode names and clock widths,
unchanged state/RNG after pure reservation, command/quote/duration limits,
suppressed no-ops, delayed stops after refusals, hard failures, caller/task
cancellation, lost acknowledgments and publication ownership. SQL and v5 request
meaning are unchanged. See configuration report section 45 and the release PR
for completed test and release evidence.

Final worker discovery completed **1,346 tests in 226.816 seconds**, passing
with 16 expected opt-in/database skips. All 44 new owner/policy cases passed
independently; 35 focused policy/existing provider-capacity/owner regressions and
16 dedicated GitHub helper tests also passed. No SQL fixture changed, so the
prior 110 isolated PostgreSQL cases are historical acceptance, not a new rerun.

The reproducible `python -m tests.measure_provider_pilot --measure` trace uses
the actual owner, literal provider fixtures and fake ledger/outbox. Each solver
completes 22 economic commands (creation, bootstrap, ten protections, nine
decisions and stop), suppresses one no-op, and retains 16 accounts/positions.

| Solver | Largest SQL-spacing payload | Largest reserved stop bound | Longest measured owner operation |
| --- | ---: | ---: | ---: |
| Genetic algorithm | 162,750 bytes | 162,770 bytes | 0.123 seconds |
| Differential evolution | 165,918 bytes | 165,938 bytes | 0.121 seconds |
| Particle swarm | 201,885 bytes | 182,904 bytes | 0.153 seconds |
| CMA-ES | 207,017 bytes | 198,136 bytes | 0.140 seconds |

These local single traces include actual preparation, stop witness, command
validation, fake RPC, receipt checks and installation. They exclude real
provider, database and durable relay latency, use sparse timestamp jumps and
explicit fake lease heartbeats, and establish no worst-case runtime guarantee.

Next, an executable controller must own the entire acquisition/protection/
history/decision/control coroutine and settle retained work before the next
tick. Measure cumulative provider, preparation (including the stop witness),
database and outbox latency before selecting cadence. Local fake-transport
timings establish only preparation overhead. Production transport, legacy
cutover, preview isolation, migrations and hosting remain gated in `TODO.md`.

**Research further before longer runs:** a new v6 command could replace the
duplicated full `before` state with an exact prior immutable command ID/revision.
Keep complete `after`, operations, events, source and optimizer evidence. Under
the SQL run lock, resolve one same-owner/run prior journal row, verify its full
after-state equals the locked checkpoint, expand locally for existing semantic
checks, and journal/read back the original compact request. Replay must compare
the original request before new-transition checks. Missing prior evidence must
fail closed; archive/retention, bounded expansion, cancellation, source freshness
and prior-row availability need explicit acceptance. Python canonical JSON and
PostgreSQL `jsonb::text` hashes are not interchangeable state digests.

Read-only sizing of the demonstrated failures suggests useful headroom: PSO's
complete logical v5 payload would be 276,586 bytes; replacing its 126,160-byte
prior state with a 70-byte identity/revision reference gives 150,496 bytes. CMA's
262,797-byte payload similarly becomes 143,497 bytes. These are representation
estimates, not accepted commands or an implemented v6 contract. Internal v3/v4
builders also reject before v5 wrapping, so compaction needs a reviewed sealed
logical draft and wire separation, rather than a final JSON shortcut.

Continue deeper research on shared provider quotas, actual publication/fork/
revision semantics, interrupted history, slower-cadence protective exposure,
journal/outbox memory and legal retention, process restart clock rebinding and
the cumulative five-second feasibility. The pilot is not restart/restoration
authority. Existing primary-source findings are in
[EXACT-SOURCE-RESEARCH.md](EXACT-SOURCE-RESEARCH.md).
