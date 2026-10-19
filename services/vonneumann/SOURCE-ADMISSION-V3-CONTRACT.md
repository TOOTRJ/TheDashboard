# R3-03A1 independent original-source research contract

This is an offline, opt-in pure validation stage. It does not contact Jupiter or
Solana, read credentials, acquire data, write a database, issue a native receipt,
read or calibrate a clock, acquire a lease, activate a worker or authorize a
trade. It changes no synthetic v2, existing v5, native SQL or hosted runtime.
All nine research formats retain all nine authority fields as literal `false`.
Changing any to `true` is a refusal, even after recomputing every supplied hash.

The implementation is in `vonneumann/market/source_admission_v3.py`. Its exact
field sets, formats, enum rules, dependency pins and input bounds are in
`source_admission_v3_policy.py`. There is no dispatch into an older policy. The
policy canonical digest is
`2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640`.
The initial proposal remains separately archived in
`R3-03A1-SCHEMA-POLICY-DRAFT.json`, canonical digest
`dd10a7b430eeeed3dc51480590fcff15522c5d29d59d2ed5bc85c4f6ba27d499`.
The historical `R3-03A1-SCHEMA-DRAFT.md` is explicitly marked historical. Its
older field lists and draft digest do not describe the final research policy.

The final descriptor pins these reviewed dependencies:

| Dependency | Policy SHA-256 |
|---|---|
| Original acquisition/parser | `912fd28c718311f9b6f72cf0327a7c6b5f4ec7cc4033744d3306064ed869ac89` |
| Prospective sampled-close source | `3be1de572d954859002546e5d525ddb0fbda71a5ca844368381a98395571aad1` |
| Bounded recorded transport | `a62184b94f88dbc248a6f3569e171a60e8a0a530addf8ed8aa943b10433f055e` |

The dependency names pin semantics for review. A matching SHA-256, issuer UUID,
package hash, private-principal label or TLS provenance does not authenticate a
caller, a provider response, a clock or a native database record. Actual
authenticated original acquisition, principal resolution, immutable database
getters and complete ledger/epoch registries remain R3-03A2 and later gates.

## Exact immutable envelopes and dependencies

`decode(kind, original_bytes)` accepts canonical bounded UTF-8 JSON with the
exact field set, literal format and current policy hash. Unknown or duplicate
fields, Boolean-as-integer coercion, noncanonical counters/UUIDs/digests, unsafe
or unsupported JSON, and authority escalation refuse. Decimal prices use exact
18-place integer scaling; no binary floating-point price conversion is used.
Raw provider integer fields remain JSON integers, while envelope counters are
canonical decimal strings. `ResearchEnvelope` is an immutable typed byte
container. Public validators revalidate supplied original bytes and types;
passing a dictionary, a similarly named envelope or a hash alone is insufficient.

| Format suffix, with common prefix `ga-jupiter-source-` | Meaning |
|---|---|
| `reservation-research-v3` | Seven distinct original UUIDs, RPC IDs, issuer/endpoints, scope, expected principal and package/policy bindings. |
| `capture-retention-research-v3` | Original safe capsules or incomplete diagnostics under that reservation; `eligibility=false` always. |
| `submission-research-v3` | Exact original admission command linking reservation, capture, observation and prior candidate. |
| `expected-context-research-v3` | Separately supplied expected bindings, process/UTC guards, known original inventory and epoch chain. |
| `prior-original-witness-research-v3` | Original reservation, capture, submission, candidate, readback and availability wires for one prior accepted snapshot. |
| `admission-candidate-research-v3` | Independently parsed raw trio and conservative original process-clock age snapshot; distinct from `DerivedObservation` or `SourceMark`. |
| `original-readback-research-v3` | Supplied original acceptance/sequence/receipt/package/record pins and committed-readback observation interval. |
| `availability-research-v3` | Exact original readback hash/interval and known-available UTC upper bound. |
| `inventory-seal-research-v3` | Complete supplied write interval, eligible research pins, period range and prior seal link. |

`validate_capture(reservation, capture)` independently checks each retained
capsule's scope, issuer, endpoint, original public request, record/raw references,
base64 encoding, raw byte length/hash, response metadata and original clocks.
The packet retains Price V3, mainnet genesis, then exact-slot block-time capsules
in that order. A successful capture has exactly three originals, no diagnostics
and no failure. An incomplete capture has an explicit whitelisted failure and
at most one diagnostic. `captured_original` can accompany a cleanup/deadline
failure only when that very original capsule is retained and its request,
receipt and status metadata agree. `withheld`, `partial_discarded` and
`not_received` cannot masquerade as retained originals. There is no redaction
and relabeling of replacement bytes as an original response.

Safe capture retention is deliberately separate from eligible source admission.
Source-invalid, stale or full-admission rollback outcomes do not become durable
inside a failed transaction. The future native design must persist an
authenticated append-only capture/diagnostic action separately, then record a
valid admission or terminal refusal with the appropriate transaction semantics.
These pure functions perform none of those writes. A supplied `refused_source`
journal label is a research classification, not proof of a real terminal native
refusal. A missing getter is unknown, not terminal absence.

## Independent raw validation and exact clocks

`validate_submission(reservation, capture, submission, expected_context,
prior=...)` parses the three original response bodies directly. It does not call
`derive_observation`, `assess_record_age`, `capture_mark`, or cast an existing
normalized header. Reused bounded JSON, canonical request, Decimal and scalar
primitives do not substitute for this independent raw parsing.

The supported source is SOL/USD, the pinned wrapped-SOL mint and decimals 9,
Price V3's reference `usdPrice`, its literal integer `blockId`, the pinned
mainnet genesis hash and the integer `getBlockTime` result for that exact slot.
RPC IDs, method, arguments, JSON-RPC shape and original request hashes must agree.
Wrong network/mint/slot/ID, null block time/block ID, error responses, unsafe
numbers or missing bodies refuse. Nullable `priceChange24h` is ignored while its
original raw bytes remain retained. This does not make the source OHLCV,
provider publication time, exact market close or an executable quote.

The source-time basis is explicitly
`estimated-block-production-not-provider-publication`. Original UTC and
same-process monotonic receipt clocks are integer microseconds. Each original
request duration and receipt age must be strictly below five seconds; the
existing future tolerance is two seconds and source-age ceiling is 30 seconds.
The independent baseline carries the older of applicable UTC and monotonic
age bounds. A supplied prior accepted age snapshot cannot fall below the
independently parsed raw/clock baseline.

The original `ProcessClock` remains the age-snapshot anchor. Separately supplied
admission and final UTC intervals must be bounded and nonregressing; their
conservative elapsed upper bound rechecks the same receipt/source budgets.
Native UTC is not given a synthetic monotonic origin, and the candidate does not
restamp an original receipt or reduce its stored age. These interval values are
research inputs, not calls to a real database clock or proof of calibration.
Across an original prior continuation, the new supplied admission observed UTC
cannot precede the prior original accepted value. Corresponding admission and
final lower/upper/observed values must also be nonregressing. Equal timestamps
are allowed with advancing original sequence; an integer-second rounding delay
is not introduced. Distinct-reader availability uncertainty is not compared
against these native guards. This is a research consistency check, not proof of
native transaction serialization or authenticated clock ordering.

For a same-process epoch continuation, the prior original witness is reparsed
and age is carried using genuine same-epoch monotonic differences. On a supplied
epoch change, monotonic clocks are not compared across processes; conservative
nonoverlapping UTC intervals carry age instead. Source block/time cannot regress,
and a repeated block cannot change its estimated time. Repeated blocks must also
retain exactly the same reference price, matching the
pinned sampled-source/model policy. This is its conservative refusal rule; it
does not assert that Jupiter can never change a price within a slot. The supplied
append-only epoch chain must be ordered, unique, active only at its tail, and bind both the
prior and current original principal/package. Full authenticated ancestry and
protection against an omitted older epoch remain native-registry gates. The
current seal profile accepts a single recorder package; cross-package archive
continuity and policy dispatch are separate unimplemented gates.

Original resolution occurs before current freshness. An exact supplied
`original_committed` witness returns that same candidate wire using its original
guards/snapshot; it neither allocates a sequence nor issues a fresh timestamp.
Every reservation, capture, raw capsule, policy and exact submitted command must
still match. `unknown` never creates a new candidate, new ID or new request.
The native implementation must compare original submission bytes/hash and all
links, even when normalized numbers happen to be equal.

Known records carry record ID, capsule hash, raw reference/hash and reservation
hash. A current already-retained reservation/capture/record is permitted only
with that exact original kind/byte/hash association. Cross-packet raw reuse by a
different record, record/raw/operation namespace aliases, changed same-ID hashes,
and aliases into configuration identities refuse within the supplied witness.
This inventory does not assert completeness of the actual native UUID ledger.

## Original readback, availability and complete supplied seals

`validate_readback(candidate, reservation, capture, submission, original_readback,
availability)` reparses the original raw baseline and checks every link, exact
record pin, original acceptance value and package. The supplied ingest sequence
must advance its expected prior sequence. Readback must be causally after the
original final guard and acceptance, and availability must retain that exact
readback interval and its upper bound. It cannot be refreshed by a cache hit.
An original readback can be valid research evidence yet too late for its minute.

`validate_seal(seal, original_operations, previous=...,
expected_previous_sha256=...)` accepts an immutable tuple of original research
envelopes. Initial sealing requires 915 complete minutes. Each next seal advances
15 minutes and retains the previous 15-minute overlap in its 30-minute interval.
The five-second post-period seal margin remains reserved and unmeasured for
activation, as in the frozen source contract.

Journal write kinds are reservation, capture, admission, availability and prior
seal. Submission and original readback are independently resolved immutable
dependencies/getters, not invented second write events with the admission UUID.
Every supplied readback also retains the original accepted guard, record pins,
package, causal final/readback bounds and its own admission journal position,
even when no availability envelope exists and it cannot qualify for selection.
Every supplied dependency has the exact scope; getters must bind an inventoried
original candidate/command. Each admission's actual supplied ingest sequence
equals that admission's own journal position. `original_wire_sha256` for an
admission pins its candidate result; `submission_sha256` separately pins the
exact command. Incomplete, capture-only and refused outcomes have strict
nullable-field combinations and every capture-bearing outcome still resolves
and validates its actual reservation/capture pair.

Positions are contiguous; operation IDs are unique across the retained previous
interval plus the new one. Both directions of coverage are checked: every
inventory write resolves its original envelope, and every supplied write
envelope appears in that retained/new inventory. A pending reservation omitted
from the supplied journal refuses. Equal bytes are not a new appended write;
an original replay keeps its old position. Exact duplicate lookup entries and
conflicting same-kind IDs refuse rather than silently overwrite.

A `seal_boundary` row resolves the original prior seal at its next write
position, with null packet links only for that write kind. The current seal is
excluded from its own inventory and hash; future native sealing assigns its
write position after a locked head. This avoids a self-referential digest. An
increment must retain the independently expected previous seal hash. Supplying
the old seal proves neither an authenticated seal action nor database coverage.

Eligible research pins retain candidate, original readback and availability
hashes, supplied acceptance, original supplied readback upper bound, sequence and
sampled reference price. At least one eligible original must be accepted inside
each minute with a consistent original supplied readback upper no later than
that minute's end. Late/unknown availability,
source/receipt age failures or gaps cannot fill the minute. Selection is latest
acceptance and then unique original sequence within this immutable supplied set;
there is no interpolation, invented candle or retroactive later insert. The
eligible digest sorts all eligible research pins by original ingest sequence.
It is deliberately not the existing `SourceMark` record-set digest. No header
cast, native seal or sampled-history authority is produced. The existing source
contract remains responsible for its distinct sampled-close history DTO; a
future authenticated bridge must join these original facts without weakening it.
An independent consistency pass orders all supplied admitted candidates by their
original ingest sequence. Acceptance, block and estimated source time cannot
regress; repeated blocks retain exact price/time; corresponding original native
UTC guards are nonregressing. It runs even when a candidate has no qualifying
availability, so direct baseline-valid candidate construction cannot bypass the
fresh-submission ordering checks. Full original ancestry remains unproved.

Completeness here means complete **supplied** journal and original dependencies.
There is no query to a database and no assertion that a caller supplied every
real pending/resolved operation or ancestor. Locked native inventory, principal
authentication, original getter completeness, receipt issuance and epoch/ID
registries remain closed until the next reviewed native stage.

## Bounds, evidence and next gates

Per-envelope canonical input is bounded to 4 MiB, a seal to 8 MiB, supplied
records/operations/inventory entries to 4096 each, epochs to 128 and original
dependencies to 24576. These are finite schema bounds, not an aggregate memory,
RSS, CPU, five-second native-action or hosting-budget proof. Validation uses
within-call immutable kind/hash indexing and exact-wire memoization only to
avoid repeated checks of the same packet. Every original still receives strict
decoding/link checks; no cross-call authority cache, receipt or clock is created.

The independent producer-bound reserve test constructs maximum raw-body and
metadata/counter/capsule encodings and retains the prepared packet, three raw
bodies, capsules, result summary and conservative diagnostic charge below the
reserved 1 MiB. This is an encoded-retention accounting check, not an RSS limit.
The transport's 8 MiB/4000 engineering cache is not proof it can retain a
915-minute warmup. Durable authenticated immutable capture/getters and explicit
same-ID reconciliation must precede safe process-cache disposal/release. Missing
or conflicting native originals stay unknown; a fresh UUID is not a repair.

Offline tests use literal clocks, public fake IDs and `deny_network`; there are
no provider requests or skipped cloud tests. Adversarial cases recompute their
own hashes and associations where needed, so rejection is tested beyond stale
hash detection. The full 915-minute supplied-witness trace is an engineering
measurement only. Its observed runtime is recorded with the final test receipt;
it is not a cadence, RSS, source-native SLA or $20 hosting proof.

The next ordered stage is a separately reviewed guarded native source-admission
experiment: independent original raw parsing, authenticated recorder principal,
real UTC/final guards, immutable same-ID getters/reconciliation, append-only ID
and epoch registry, complete locked journal and original committed availability.
It requires new SQL/native tests and migration review before any remote action.
Durable recorder release and full model/native joining follow. Only then can a
measured closed canary establish source cadence, late/gap fractions, CPU/RSS,
Jupiter organization quota, close-anchor age and the approved $20 pilot budget.
Hosted paper trading and all live wallet/signing/swap authority remain closed.

## Historical preparatory offline receipt, 2026-10-13

The following 37-case receipt predates the final native-time and repeated-block
ordering refinements. It tested research policy
`baa1ceeadbc2a198865c2d44982e011fb4d3841e4e21cee2fc1d8f23babaa68c`
and only the older file hashes listed below. It does not validate the final policy
or source bytes. The final decoder refuses that older policy rather than
relabeling its research envelopes. A separately scoped final receipt follows.

The final scoped command was:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 PYTHONPATH=services/vonneumann \
/private/tmp/dashboard-locked-worker/bin/python -m unittest \
tests.test_source_admission_v3 tests.test_original_packet_reserve_v3 -q
```

It passed **37 tests in 143.833 seconds, zero skips**: 22 independent admission
cases, 14 seal cases and one producer reserve case. The seal class constructs 915
original minute packets and checks initial sealing, two consecutive 15-minute
increments, original boundary/overlap positions, late-readback gaps, omitted
pending writes/dependencies, excluded malformed captures, cross-packet
record/raw/observation aliases, changed or repeated original identities,
unrelated getter records and contradictory outcome/nullability fields. The
admission cases include exact raw parsing, internally rehashed malformed bodies,
required nonnull hashes, original replay before current age, unknown outcomes,
same-/cross-epoch age carry, prior principal/package binding and one-microsecond
receipt-budget boundaries. This is the complete suite's engineering duration,
including fixture construction and multiple validations; it is not a measured
single native action or a five-second runtime guarantee.

These are the exact source-bound bytes tested:

| File | SHA-256 |
|---|---|
| `source_admission_v3.py` | `129b1e7c3066cdb92b41ca5e1bb4e1a388ce1c3c7844c157addd0aa48aeda224` |
| `source_admission_v3_policy.py` | `f370b684fbc5dbd9b42a4023fbe434582683483decbd560d5c700e8705babb31` |
| `test_source_admission_v3.py` | `c21688480658335112d94c80ef5415f5bb823abca08ab7edfc62a1866f017b05` |
| `test_original_packet_reserve_v3.py` | `a286a98671fc8d24b7f47b8040472394b137f70d5eafa7071aa36f72327c8bb7` |

All eight new files passed whitespace checks. Existing acquisition, derivation,
sampled source, recorded transport, native migrations and TODO files have no
changes in this slice. No external target was contacted or modified.

## Final ordering-refined receipt, 2026-10-13

The same scoped command passed **41 tests in 288.718 seconds, zero skips** under
the final policy `2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640`:
24 admission cases, 16 seal cases and the reserve case. The new cases prove that
later monotonic samples/higher sequence cannot conceal earlier original native
acceptance/final guards; equal original guard boundaries remain valid. A fresh
raw-price change at the same block refuses even with recomputed capture,
submission and context hashes.

Additional seal negatives use internally rehashed extra originals inside the
already covered final minute. Each individually passes the raw/readback
validator, then fails the sequence consistency pass for acceptance, block or
source-time regression, or a changed price at the same block. All candidate,
readback, availability, journal and eligible-set hashes are recomputed. The
unavailable-readback case has a valid positive with no availability envelope;
changed original acceptance or journal position still refuses. These tests do
not authenticate supplied native clocks or prove complete native ancestry.

The final source-bound hashes replace only the historical bytes listed above:

| File | Final SHA-256 |
|---|---|
| `source_admission_v3.py` | `b821b469f50b6fe3554851d348822059a33facb5a77e6133290e1c3283fb9bc6` |
| `source_admission_v3_policy.py` | `305793e9dd9069be3fb215918df121696a2a22fbf240a5de89a9b2254c630403` |
| `test_source_admission_v3.py` | `b23d0d963a44e0356b3b20c85db005b41854729787b3d24a12ce6d04b72279dd` |
| `test_original_packet_reserve_v3.py` | `a286a98671fc8d24b7f47b8040472394b137f70d5eafa7071aa36f72327c8bb7` |

The measured 288.718 seconds includes fixture construction and all positive and
adversarial history validations. It is neither a single-seal latency measurement
nor a five-second CPU/RSS guarantee. Resource, native parser/clock, inventory
capacity, authenticated original delivery and prospective warmup gates remain
open. No broad provider, cloud or native test was substituted for this pure scope.
