# Provider-bound exact paper contract

DB-03A2C2D2B introduces command version **5**, a fresh `ProviderLifecycleConfig`
and `ProviderAdmissionOwner`. This connects immutable Jupiter/Birdeye captures
to the bounded two-gene, eight-member exact lifecycle model, its command journal,
and isolated PostgreSQL acceptance. It is not wired into the active controller,
production database transport or a hosted worker.

## Identity, units and trust

The policy pins Solana's wrapped SOL mint
`So11111111111111111111111111111111111111112`, nine token decimals, unscaled
Birdeye price candles and **USD reference marks**. The accounting asset is
`SOL/USD`; a legacy feed label of `SOL/USDC` cannot claim USDC settlement.
Price values must fit the existing positive 18-place exact grid without rounding.
The active controller's asset registry is unchanged. An explicit
`ExactMarkColonyConfig` preserves the new model's type in owned optimizer forks
and evidence, including particle swarm and CMA-ES.

The mandatory outer source policy distinguishes v5 from synthetic v3/v4. The
nested rehearsal profile identifies the reused unchanged economic kernel; it is
not the source authority. Config, state, transition, repository, coordinator,
journal and outbox preserve version 5 and its epoch. Existing validators receive
only declared local model projections; those projections are never emitted as
provider commands or persisted in place of the original request.

Each consumed quote/history bundle carries the provider, exact endpoint and
request, parser version, request/response SHA-256, response length and receipt
clocks. The worker reparses immutable original bytes before constructing the
bundle. SQL checks structure, policy, source relationships and economic binding.
**A manifest is not proof of provider authenticity or of derivation from a hash.**
The database trusts the worker's parsed records; raw bodies and RPC responses are
not archived in this command. No genesis/finality or independently authenticated
market-data claim is made.

## Four separate time/order meanings

| Value | Meaning and admission rule |
| --- | --- |
| Block reference | Jupiter `blockId`, ordered strictly for new protection; mapping to a Solana RPC slot remains an explicitly named local resolver policy |
| Estimated source second | Nondecreasing estimated block time; different block references may share it |
| Receipt clocks | Original wall/monotonic readings in one owner process epoch; a duplicate retrieval cannot renew accepted anchors |
| Decision second | Floor of the actual owner wall sample; strictly advances protection, without constructing `previous + 1` |

Identical same-block/price/source-time snapshots and valid same-second schedules
are deferred before command ownership. A fractional-second receipt also waits
until an actual whole-second decision can follow its availability. Future runtime
wiring must retain that capture for a later clock sample; repeatedly replacing it
with a just-fetched snapshot can keep deferring and is not an integration plan. Conflicting same-block values, regressing
references/times/clocks and stale evidence fail closed. Deferral does not bypass
freshness checks. Conservative source-age floors carry forward even when wall
and monotonic clocks progress differently.

Clocks in the wire contract are bounded integer microseconds. Exact integer or
binary64 ratios are used to floor original receipts and ceil current samples;
prices never use binary64 conversion. Decision seconds are taken from the
original sample, so rounding a fractional microsecond cannot invent a future
second. The wall and monotonic readings in decision evidence must match the
source envelope. Quote frames may precede preparation; preparation must validate
the same immutable frame again at its later actual time.

Both receipt ages must be nonnegative and **less than five seconds**. Source age
must be at most **30 seconds**, and a source may be at most two seconds ahead.
These are conservative local policies, not provider SLAs. The owner checks them
before and after planning, at actual repository dispatch, and after awaited
submission/readback/heartbeat/outbox operations. SQL independently checks server
wall freshness before and after new command effects. An original-ID replay
returns its original receipt under existing lease/fence gates; it does not try
to make old source evidence fresh again.

## Honest historical startup

The two EMA genes need **61 completed 15-minute bars**, derived from exactly
**915 consecutive one-minute closes**. Startup fetches historical data at today's
actual receipt time. It seeds indicators at that current time while leaving the
cohort warming and member signal cursors/pending actions empty. There are no
imaginary past fills, evaluations or historical decision timestamps.

Every consumed minute must be inside its original raw, unpadded, USD request
window, and each 15-minute end must precede contributing receipts by at least
the local five-second completion margin. Seed history ends at the latest
eligible UTC boundary. Documents must still fit the current five-second receipt
budget; parsing and submission time consume that budget.

Subsequent decisions consume either no new bar or exactly the next 15 minutes.
Current history is required for ordinary decisions and recovery. Risk-halted
protection and eligible exits can proceed without ingesting candles. All supplied
retained overlap is compared before selection, including changes smaller than
binary64 precision. Partial retained-bar overlap, gaps and revisions reject.
Bar fingerprints cover exact minute timestamps/closes, not retrieval metadata,
so an unchanged refetch remains valid. Only the latest 64 bar fingerprints and
closes are retained; at most four source documents occur in a history bundle.

A seed requires a narrow validation projection: until the first accepted quote,
local v4 validation sees its original empty EMA, while v5 independently validates
the actual seeded state and forbids seed changes. Python recomputes all seeded
EMA values; SQL validates the seed shape and close/source binding but does not
independently recompute binary64 indicator or optimizer mathematics. After the
first quote, normal model continuation validates the actual EMA.

## Ownership and failure behavior

Create and acknowledge a fresh v5 run, then construct its exclusive owner on one
event loop. Callers allocate bounded IDs/names and explicit command IDs; the
owner supplies all decision clocks.

1. `bootstrap(records, ids=..., names=..., command_id=...)` seeds current history.
2. Publish committed bootstrap events before further economics.
3. `capture_quote(capture)` returns an immutable owner-issued ticket.
4. `protect(ticket, ...)` owns and settles protection. Publish its events.
5. `decide(ticket, records=..., ...)` requires that exact accepted ticket;
   recovery also requires it and the current risk trip. Publish committed events.

One shielded task owns preparation through settlement. Invalid evidence,
preparation/ID/capacity failure or expired active evidence permanently closes
new economics. The whole command remains capped at 256 KiB, with no splitting,
truncation or automatic threshold increases. Existing 4,096-ID and lifecycle
capacity bounds remain in force.

An acknowledged candidate still installs after expiry, and its stable event IDs
still publish. Uncertain outcomes retain the original command/candidate for
readback; no substitute command is generated. Historical source receipts remain
retained through pending bootstrap/decision delivery. A new process cannot claim
clock compatibility or resume merely by copying the source epoch.

## Acceptance and remaining gates

Offline tests use literal provider JSON and real exact parsers, all four actual
solvers, injected owner clocks and controlled transport/cancellation races.
Opt-in PostgreSQL tests use a uniquely owned no-network local container and real
server clocks. The SQL fixture is guarded and outside `supabase/migrations`.
Acceptance passed 1,229 ordinary worker tests and 110 isolated PostgreSQL tests,
including 46 new ordinary cases and 15 new database cases. See configuration
report section 43 and the release PR for measured runs and immutable release IDs.

Measured whole-command PostgreSQL-spacing sizes in the independent complete-window
trace (one bootstrap, eight protective and eight decision commands per solver):

| Solver | Bootstrap bytes | Largest protective bytes | Largest decision/replacement bytes |
| --- | ---: | ---: | ---: |
| Genetic algorithm | 80,426 | 122,843 | 142,990 |
| Differential evolution | 80,522 | 122,955 | 146,726 |
| Particle swarm | 99,787 | 161,613 | 183,016 |
| CMA-ES | 95,549 | 153,265 | 188,148 |

The largest tested replacement contains generation 1 and eight historical closed
positions; all 68 measured payloads fit the unchanged 262,144-byte limit. These
are fixture measurements, not worst-case admission or production latency claims.
They do not establish dense-history, later-generation, control/recovery or broader
profile capacity. Do not increase the cap to bypass a failed complete command.

C2D2 and its parent gates remain open until the active controller is proved to
use this ownership path. Production transport, bounded checkpoint reconstruction,
legacy row/grant compatibility, reviewed migrations, preview database isolation,
capacity/latency measurements and hosting remain separate prerequisites.

Deeper research is required on Jupiter block/slot/fork and same-block update
semantics; Birdeye publication/revision/outlier behavior and acquisition rights;
USD/USDC/scaled-token expansion; process-restart clock rebinding and missed-history
policy; source/lease/relay latency and five-second admission feasibility; complete
command size, raw parser memory, journal/outbox retention and slow-publisher
protective latency. The five-second candle margin is not a historical
publication guarantee. Historical provider access can seed current indicators;
reproducible comparative backtests still need frozen datasets and an availability
model. See [primary-source research](EXACT-SOURCE-RESEARCH.md).
