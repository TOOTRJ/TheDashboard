# Worker capacity and retention research — 2026-10-17

B2 should first account separately for committed journal events, allocated identities, retained bytes, dependency associations and terminal reserves. A longer fence cadence does not settle all these limits. Measure the bounded mechanisms, then review a new seal representation if required; retain original evidence while durable same-ID handoff is developed.

This is research, not an implemented capacity policy or an activation gate passed. No SQL, tests, Docker, provider/account requests, installation or repository changes were performed. Existing Jupiter backtesting-retention permission remains accepted. Railway, hosted worker operation and live trading remain closed under their existing gates.

## What the existing bounds mean

The separate B1 actor/catalog prototype at `05fa5354743ac209fc950370570cafad1842e2d1` validates installed actors and catalog evidence. It has **no packet/source journal**. The future sixteen-kind native lifecycle is a proposal. A1's 4,096 known-operation/record/inventory-entry bounds, borrowed as proposed per-seal engineering bounds, are **not an installed lifetime database-row quota**. Getters and exact replay do not create journal positions; a committed diagnostic capture or terminal closure does. Command/result/receipt are distinct views of one allocated action, not three positions.

Source anchors in that frozen package: `R3-03A2-NATIVE-LIFECYCLE-SCHEMA-PROPOSAL.md:51`, `:138`, `:750`; `SOURCE-ADMISSION-V3-CONTRACT.md:223`. Paths are under `services/vonneumann`; their presence in a local package does not imply current-base adoption.

For one `(owner, run, market_epoch)` scope and one fully successful packet per minute:

| Quantity | Per packet | 915-minute minimum |
|---|---:|---:|
| Source events: reservation/capture/admission/availability | 4 | 3,660 |
| Prepared packet UUIDs | 11 | 10,065 |
| Provider record identities | 3 | 2,745 |
| Current fixed transport requests | 1 Price + 2 RPC | 915 Price + 1,830 RPC |
| Naive distinct dependency views | 20 | 18,300 |
| Maximum original provider bodies | 262,144 B | 239,861,760 B |
| Base64 for those separate bodies | 349,532 B | 319,821,780 B |

The dependency count is a planning inventory, not a frozen physical schema. Unused prepared closure UUIDs remain allocated; two integer RPC correlations per packet are separate from the eleven UUIDs. Configurations, actor/epoch/fence/control/seal IDs and failed attempts add costs. The current transport issues a fresh Price/genesis/block-time trio; batching or cached-genesis exemptions require a separate contract.

Warmup needs 915 **qualified** contiguous minutes and 61 complete 15-minute closes. Startup can discard a forming prefix of up to another 15 minutes; those attempts still have evidence costs. Late/unknown readback cannot fill a past minute. Two successful packets/minute require 7,320 source events before fences; multiple markets add independently scoped histories and aggregate load. Model economic commands are outside this source-only event set, so these counts do not describe a complete trading runtime.

## Fence arithmetic and independent limits

For `N` successful packets, `F` acquisition/renewal events and `R` other committed events, a proposed bootstrap inventory capped at 4,096 needs `4N + F + R <= 4096`. For an ideal 54,900-second interval and hypothetical cadence `C`, `F = ceil(54900/C)`:

| Cadence | Source + fence events | Remaining before other events |
|---|---:|---:|
| 60 seconds | 4,575 | −479 |
| 120 seconds | 4,118 | −22 |
| 180 seconds | 3,965 | 131 |
| 300 seconds | 3,843 | 253 |

These are not recommended fence settings. With a merely illustrative reserve of 32 other events, the first two cases fit at most 812 and 903 successful minute packets. Alignment, expiry margin, restarts and failures can make these estimates worse. The proposed source fence is distinct from the economic lease; do not copy legacy lease durations or renewal reserves into B2.

Other limits remain independent: A1 envelopes 4 MiB, seals 8 MiB, supplied epochs 128 and dependencies 24,576; prospective marks 16 KiB, manifests 1 MiB and history 4 MiB. Lifetime original-ID and recorder/reader-origin registries cannot be truncated to these supplied-list sizes. Ten thousand prepared UUIDs already exceed a 4,096-entry complete identity export even when 2,745 provider records fit.

B1 currently binds eight actual fake actor sessions across two scopes, with a 16-binding guard and unique session name/OID per binding. Its all-actor closure has 64-node/256-edge guards. Four profile labels per scope consume four bindings; one bound session cannot silently serve another market. Only the installed eight-actor baseline is accepted. Every public call recomputes catalog evidence. Its measured 215,899-byte K frame is metadata-construction evidence, not per-packet network/storage cost or a five-second latency proof.

The transport defaults to 8 MiB retained charge and 4,000 results, requiring 1 MiB reserve before new I/O. Actual completed charges can be smaller; eight reserve slots are not an assertion of exhaustion at packet eight. It has no release API: closing drains I/O but retains results and used IDs. A count cap alone does not prove 915-minute memory capacity. Durable authenticated original getters, crash-safe same-ID reconciliation and a new native/reader wrapping measurement must precede eviction.

Relevant frozen code: `provider_recorded_transport_v3.py:64,402,419,448`; B1 SQL `jupiter_actor_catalog_v3.sql:28,98,121,269`; source contract `JUPITER-PROSPECTIVE-SOURCE-V3-CONTRACT.md:37,110,193`.

## Smallest policy options

1. **Bounded B2 accounting:** reserve terminal work under the same scope lock as ordinary allocation. Count identities, views, bytes and physical associations separately. Freeze the maximum Stop/closure/readback/seal write set before selecting reserves. Refusing safely before 915 minutes is a mechanism result, not successful warmup.
2. **New paged-seal format if needed:** commit exact scope/package, immutable through-head, previous boundary, page ordinal/count and contiguous native ranges. Validate no missing/duplicate ranges and both journal-to-original and original-to-journal coverage. Sixty-one 15-minute groups are a measurement layout, not permission for early native seals or larger A1 inputs. Stored pages must belong to an accounted transaction/event. Ordinary pagination bounds replies; it does not establish completeness or change aggregate capacity. Deterministic order is essential, and OFFSET still processes skipped rows. [PostgreSQL17 LIMIT/OFFSET](https://www.postgresql.org/docs/17/queries-limit.html).
3. **Store immutable originals once:** measure exact scoped associations referencing retained originals instead of duplicating bodies across views. Strictly decoding a capsule can recover its original raw body; omitting a redundant physical copy must preserve every original capsule byte. Equal content never merges record/action identity. Keep bounded active projections separate from historical originals.

Physical time partitioning is later work. PostgreSQL17 partitioned unique/primary keys must include all partition keys; per-partition UUID keys alone cannot enforce lifetime cross-partition uniqueness. Retain an independently enforced identity registry. Partition maintenance also changes locks/catalogs. [Partitioning limitations](https://www.postgresql.org/docs/17/ddl-partitioning.html#DDL-PARTITIONING-DECLARATIVE-LIMITATIONS).

## Retention boundary

Retain current/prior checkpoint dependencies, pending/uncertain originals and prepared identities, accepted/excluded safe captures, receipts, closure tombstones, lifetime IDs/origins, seals/overlap anchors, holdings/assessment/optimizer lineage, Stop/recovery records and unacknowledged reader/relay work. Old IDs and A→B→A origins never become reusable. Sixty-one closes, hashes or projections do not replace original evidence.

Hot eviction first needs verified durable availability. Later archival needs immutable scope/version manifests, original-ID routing, exact request/result/receipt/dependency readback, restored next-wire equivalence and atomic reader/pending-pin handoff. Deletion remains a later reviewed operation after reverse-reference checks. DELETE/VACUUM generally enables reuse rather than immediate filesystem shrinkage; VACUUM FULL rewrites with additional disk and an exclusive lock. [PostgreSQL17 vacuuming](https://www.postgresql.org/docs/17/routine-vacuuming.html#VACUUM-FOR-SPACE-RECOVERY). Existing obligations remain in `JOURNAL-RETENTION-DESIGN.md:104`.

## Ordered experiment and acceptance

**First, before B2 freezes:** produce an accounting worksheet for all sixteen event kinds: maximum committed positions, allocated IDs, rows/pins, encoded/raw bytes and terminal reserve. Reconcile one packet, 15 packets, 915 packets and two scopes; distinguish per-scope from shared limits and committed events from rollback. Freeze pass criteria before measurement. Repair B1's CI image identity, canonical opt-in and MAINTAIN coverage before its current-base acceptance.

**Then B1/B2 mechanisms:** prove actual scoped actors, allocation/replay, alias/foreign-ID refusal, complete retired origins, one unresolved packet, fence expiry/races and reserve boundaries at below/exact/over capacity. Load with genuine accepted data-free controls; preserve all table state on refusal. This does not create 915 observed source minutes.

**After B3–B8:** compare ordinary and maximum-body layouts in an owned PG fixture, including failed capture, late availability, reader restart, same-ID lost acknowledgment and closure races. Measure exact row/wire counts, heap/fsm/vm, indexes, TOAST, WAL-window growth and individual phase times/clock ages. Avoid double-counting: `pg_table_size` includes TOAST and `pg_total_relation_size` includes indexes. WAL LSN deltas can include background activity; sampled memory peaks are not hard limits. [PostgreSQL17 size/WAL functions](https://www.postgresql.org/docs/17/functions-admin.html).

**For a forward paged representation:** require identical resolved originals, eligible minutes/winners, 61 closes, full/compact next model wires, original receipts and terminal reserve. Reject omitted/reordered/duplicate pages, wrong heads/scopes, corrupted dependencies and late attempts to reopen a sealed minute. Validate unchanged mutable tables after rejection.

**Finally, after native/reader/model gates:** separately opt into a genuine-clock 915-minute trace plus two 15-minute increments. Include startup alignment, failures, package/reader rotation, quota/call counts, storage growth and target-host costs. Preserve receipt age below five seconds, source ceiling 30 seconds, future tolerance two seconds and original minute eligibility. Record recognized-COMMIT checks separately from final visibility. End at a declared bound with reserved Stop/reconciliation. Long-run retention, worst-case tails, archive recovery and cost remain deferred research; one finite trace proves neither continuous operation nor profitability.

### Evidence identity

The source contract is frozen at commit `05fa535`; B1 SQL SHA256 `84b3167c6626911fd231f2eeb337e1df4ab645a89c723017ecb169cdabf93cad`, A1 policy `305793e9dd9069be3fb215918df121696a2a22fbf240a5de89a9b2254c630403`, transport `9549a4d461138e980259ed6d68b2644c3b3010642892425dabd44a0104a0d46f`. The lifecycle proposal inspected hashes to `629bb304beddfdf84a73a5df2afe0ab56798f349ce4ae73c1efc63722443d554`. Historical v2 control-storage measurements are instrumentation precedents, not v3 bytes-per-packet or hosting estimates. No historical evidence is rewritten by this research.
