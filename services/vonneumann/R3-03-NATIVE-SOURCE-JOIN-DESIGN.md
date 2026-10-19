# R3-03 independent source admission and history sealing — review design

Status: design only, 2026-10-13. No SQL, database, credentials, provider requests,
role grants, migration, worker wiring or activation is implemented here. This
plan follows the reviewed pure source, parser and inert transport slices. It is
a proposed new research boundary, without synthetic v2 wrappers or production
capabilities. The full engine/native join follows source-native admission; it
must not be used to skip independent original-source validation.

## Frozen dependencies and identity

The source profile is `jupiter-price-v3-prospective-minute-sampled-close-v1`:
915 complete observed minutes, 61 completed 15-minute close-only bars, exact
15-anchor provenance per bar, two EMA genes, and a five-second completion margin
that remains unmeasured for activation. No OHLCV, retrospective mark, missing
candle, interpolated anchor or executable quote is produced.

| Dependency | Reviewed digest |
| --- | --- |
| Acquisition parser policy | `912fd28c718311f9b6f72cf0327a7c6b5f4ec7cc4033744d3306064ed869ac89` |
| Prospective source policy | `3be1de572d954859002546e5d525ddb0fbda71a5ca844368381a98395571aad1` |
| Recorded transport security policy | `a62184b94f88dbc248a6f3569e171a60e8a0a530addf8ed8aa943b10433f055e` |
| Public certifi 2026.7.22 CA bytes | `9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f` |

Reviewed implementation commits are `a78e7348603cc58498c9b6c03a19149de5755b3a`
(initial source), `282c08722f886cde8bb89aa6932032ecc4e20d25`
(explicit nullable-change parser and source dependency), and
`0785ab48c605d3b9468154773eb5ceb7a49d0c61` (inert original transport).
The accepted native package must separately pin actual module/helper/runtime
bytes and exact native schema/catalog. Hash equality identifies bytes; it does
not prove the caller acquired those bytes from Jupiter or the trusted recorder.

Keep owner/run/market identity durable. A process restart obtains an explicitly
registered acquisition epoch and accepted principal binding, retaining each
original record's own epoch. Do not replace old epoch labels or subtract a new
process's monotonic origin from an old record. The same-package history path
retains UTC provenance, original UUIDs and the global native ingest sequence.
The current source seal requires one recorder package. Cross-package history
continuity, old-reader dispatch and archived policy compatibility remain separate
unimplemented gates; a new package hash cannot silently reinterpret old records.

## Authentication is a separate input

Use a restricted authenticated recorder database principal bound server-side to
owner/run/market, enabled acquisition epoch, permitted endpoint-binding IDs,
transport/parser/source policies and accepted recorder/native packages. Derive
that binding from the verified database session/capability and frozen catalog,
not JSON owner IDs, caller headers, application service-role assertions, capsule
hashes or a Python `IssuerBinding` constructor. Do not grant a recorder economic
write capability or let an engine fabricate source rows through a broad API role.

The proposed separation is a recorder that submits original packets, a guarded
native validator that independently parses those originals, and a scoped reader
that exposes committed original evidence and sealed inventories to the engine.
Whether those are separate OS services must be resolved during runtime design;
the source and economic database capabilities remain distinct. A limited login
authenticates the accepted recorder principal, not Jupiter. Genuine TLS under
the accepted private runtime is the transport trust assumption. Provider signed
attestation, on-chain executable price, publication time and finality are not
obtained by these interfaces.

Every initial DTO/SQL receipt uses an explicit `ga-jupiter-...-research-v3` format,
an independent package/policy version, strict unknown-field rejection and false
authority fields. Never toggle an existing research flag or strip a format to
turn it into a production receipt. A future authenticated operator/release
capability is a separately reviewed artifact and installation boundary.

## Proposed source-native interface

These operation names and additional envelopes are proposed, not callable APIs.
Freeze their exact schemas with root review before implementation. They preserve
the already frozen `PreparedPacket`, `RecordReference`, `SealReference`,
`SourceMark`, `SampledHistory` and `SampledCloseSeries` contracts.

1. `reserve_original_packet` records an exact original packet reservation before
   provider I/O. Bind the four transport UUIDs/RPC IDs plus a distinct original
   native admission-operation UUID, scope, current acquisition epoch, principal,
   endpoint mappings and packages. The authenticated reservation must survive
   restart. The recorder cannot replace an unresolved reservation with fresh IDs.
2. `admit_original_packet` accepts the exact reservation and the three original
   capsules, with independently authenticated recorder/clock provenance and
   prior accepted source head. It independently validates canonical capsule/raw
   bytes, public request, status, JSON, mint/decimals/price grid, mainnet genesis,
   exact block/RPC IDs, original record/raw-reference IDs, epochs and policy
   versions. Recompute the observation from all three bodies; never trust a
   submitted normalized price, mark hash or proposed native ingest sequence.
3. `get_original_packet`, `get_original_raw` and `get_original_admission` expose
   immutable committed original bytes/receipts to the scoped authorized reader.
   Getters compare exact original UUID, scope and hashes and reject conflicting
   bodies. The reader independently decodes/recomputes the packet and observes
   the committed original readback under a genuine bounded clock.
4. `register_original_availability` stores the authenticated reader observation
   of original committed visibility, including its clock upper bound. This is
   distinct from the native accepted-at/final-guard time. The current
   `RecordReference.available_at_upper_us` must come from that immutable causal
   observation, not receipt time, transaction start or a newly selected caller
   timestamp. An uncertain acknowledgment resolved after a minute ends cannot
   supply an earlier availability bound or retroactively fill that minute.
5. `seal_observed_interval` freezes complete inventory and eligible marks for a
   requested observed range. It produces an original seal operation/readback
   plus the independently verified inputs needed for `SealReference`.
6. `get_original_seal`/`get_source_head` return the committed immutable seal,
   complete inventory, history references and native sequence under accepted
   scope/package. A submitted expected history digest must resolve from that
   authenticated head, rather than the same untrusted history being validated.

The additional reservation, native-admission, availability and inventory
envelopes must distinguish server-derived fields from client-supplied diagnostic
inputs. Required envelope identity includes original admission UUID, original
observation UUID/hash, the three raw/capsule UUID/hash pins, original prepared
wire/hash, scope/epochs/principal, parser/transport/source and package pins.
Native outputs add global ingest sequence, actual accepted clock, final-guard
clock, original transaction/receipt identity and observed-commit status.
Availability outputs add the independent readback clock/upper bound. Seal outputs
add original seal ID, source range, complete inventory digest, through-sequence,
eligible record-set digest and original immutable readback. Define bounds/types
for every field before a validator or migration is written.

## Clocks, causal checks and idempotency

Use canonical integer microseconds and bounded exact counters throughout native
and source-admission wires. Do not convert through binary64 epoch seconds or add
the old synthetic whole-second ceiling guard. The current action policy is
`integer-us-causal-after-original-readback-and-latest-receipt-v1`; calendar/cohort
floor seconds serve only math. Independently capture/recheck genuine native
clocks after parsing and relevant locks, and again at the final guard. An
in-transaction final guard is not a visible COMMIT or known reader availability.
Accepted readback is separately observed after COMMIT.

All three original receipt/acquisition ages remain strictly below five seconds;
estimated source age remains at most 30 seconds, future tolerance at most two
seconds, and supplied clock uncertainty within the existing two-second cap.
Use actual original receipt times and authenticated native acceptance/readback
times. No cache hit, new HTTP receipt for the same old block, epoch change or
clock correction resets carried source age. Resolve the previous accepted
original observation and independently derive the next observation with its
age carry and block/source nonregression checks. Current actions must also
resolve/recheck the original mark under their actual action clock.

Global native ingest sequence is assigned by serialized server admission and
never supplied by the recorder. Its ordering and accepted-at relationship must
be deterministic under concurrent attempts, not dependent on callback arrival.
Keep original UUID/raw-reference conflict checks across the complete ledger,
including old epochs and excluded diagnostic records. Same UUID plus different
wire/hash/scope is a conflict; no overwrite, replacement or fresh timestamp.

Exact original-ID lookup comes before a new admission's freshness/epoch checks:
an existing committed original returns its original receipt without restamping
or becoming current evidence. Changed original wire always refuses. A missing
lookup after a timeout is not proof the original transaction cannot still
commit. Reconciliation must serialize against that original operation/reservation
and prove its terminal committed or safely absent/aborted state. If safely
resubmittable, use the same original bytes/IDs and genuine later admission clock;
stale originals may be retained as refused diagnostics, never refreshed. Do not
allocate a replacement observation while the original outcome remains uncertain.

## Complete immutable minute/history sealing

The seal's full native inventory includes reservations, admitted/rejected packet
outcomes, original capsules/raw references, observations, availability outcomes,
principal/epoch/package pins and sequence coverage. Its eligible mark set is a
separate deterministic projection. The pure `records_sha256` pin addresses that
eligible frozen mark set; an additional native complete-inventory digest must
prove omitted/late/rejected originals were accounted for. Do not mistake a hash
over a caller's filtered marks for a complete inventory proof.

For each minute require at least one eligible original observation accepted
within the minute whose independently authenticated original committed-readback
availability upper is no later than minute end. Within the immutable frozen
set, choose latest accepted-at then unique ingest sequence. Pin all 15 anchors
per bar; the final minute's sampled reference mark is the close, with explicit
offset below 60 seconds. Preserve actual source age separately from sample offset.
Missing/late/unavailable anchors produce a gap/refusal. No fill, interpolation,
backdating, retrospective insert, changed tie winner or revision of a sealed
period is allowed.

Bootstrap requires 915 contiguous observed minutes/61 bars. An increment keeps
915 minutes/61 bars, advances exactly one 15-minute period, pins the original
prior history digest, and matches every retained original minute/bar and the
15-minute overlap. Native inventory/seal identities and through-sequences must
be monotonic; mixed packages, regressed source head, changed consumed original
pin or ordinary backlog refuses. Original seals remain readable after a newer
head, but cannot become the current head by replay.

## Durable original storage and release lifecycle

The transport's eight-MiB/4,000-packet process cache is only an engineering cap.
It does not prove that 915 minutes of actual warmup fit, persist, restore or remain
complete. Measure maximum valid packet charge using raw-body caps (128 KiB Price,
64 KiB each RPC), exact canonical capsule/base64 expansion, safe metadata,
prepared wire and result summary. Test the worst valid padded JSON responses,
maximum bounded metadata/identities and refused diagnostics, proving the full
encoded/raw charge never exceeds the one-MiB pre-I/O reserve. Measure actual
Python RSS independently; encoded byte accounting is not a heap-size bound.

No process-cache disposal API currently exists. Add an explicitly reviewed safe
lifecycle only after durable storage/getters and reconciliation are implemented:

1. Reserve original IDs durably; collect once under the accepted recorder epoch.
2. Persist exact originals and accepted/refused outcome under the original IDs.
3. Observe and authenticate original committed readback; resolve every raw body,
   capsule, observation and receipt by its immutable scoped getter.
4. Register original availability and retain seal/history dependency pins.
5. Mark the original packet durably reconciled, then release only that exact
   process-cache entry under a matching original acknowledgment/hash. Do not
   erase its durable identity ledger or accepted raw/archive dependencies.

Lost acknowledgments, missing bodies, unknown transaction outcome, conflicting
UUIDs or missing original readback block release and new allocation. Restart
first enumerates/reconciles durable reservations/pending originals; it does not
restart an in-memory allocator or acquire duplicates for an old packet. Cache
release needs bounded accounting/tombstone semantics so later original replay
resolves immutable durable getters rather than reacquiring from providers.
Archive/retention policies must preserve every source dependency needed by the
active 915-minute window, consumed overlap, assessments, accepted commands and
restoration history. No deletion/expiration is authorized by a cache budget.

## Ordered implementation slices and parallel work

| Order | Slice | Implementable offline result and prerequisite |
| --- | --- | --- |
| 1 | R3-03A1 contract and pure validator | Freeze strict new envelopes; independent full raw-trio rederivation, prior-age carry, causal/identity/inventory checks and adversarial fixtures. All authority false. Root must approve this design first. |
| 2 | R3-03A2 guarded source-native experiment | New research SQL namespace, narrow actor bindings, native clocks/sequence/locks, immutable original getters, reservation/admission/reconciliation and seal tables/functions. Independently parse originals in native code; no caller-hash surrogate or old synthetic wrappers. Run only an owned isolated PostgreSQL fixture. |
| 3 | R3-03A3 durable recorder/release experiment | Inert adapter against the reviewed source-native experiment, bounded original pending state, restart reconciliation, durable getters, acknowledged cache release, maximum-charge/RSS tests. No provider/hosted activation. |
| 4 | R3-03B full engine/native join | Independently resolve accepted source history/marks, new model configuration/lifecycle/operations/assessments, component/archive dependencies and exact economic deltas against the accepted server head. Add compact/restoration forms without widening old codecs or relabeling v2/v5. |
| 5 | R3-03C authentication/release rehearsal | Pin complete native/runtime/catalog packages, demonstrate restricted source/economic principals and denial paths, prepare target-specific forward/rollback validation and explicit closed release admission. |
| 6 | R3-03D measured prospective paper pilot | Only after exact Dashboard target verification and the independent installation/operator gates: collect real cadence/source-age/offset/gap/late/resource/quota/cost evidence, retain warmup, and evaluate whether the five-second margin and pilot limits are attainable. |

The new model's offline math/negative tests and offline maximum-packet/resource
analysis can proceed in parallel with slice 1 once interfaces are frozen. Schema
and authenticated source admission must precede recorder native writes, seals,
engine/native authority or a hosted pilot. Epoch registry, full identity ledger,
original availability and complete inventories are shared interfaces requiring
coordination; they cannot be bypassed by parallel implementation.

Native adversarial cases must include forged caller principal/header/hash; wrong
scope/epoch/package/policy; duplicate/regressed identity/sequence; rehashed wrong
raw/mint/decimal/genesis/slot/time; future/old/carried-age and fractional-microsecond
boundaries; delayed lock/final guard/COMMIT/readback; unknown write with late
commit; original replay after expiry/restart; missing immutable raw getters;
omitted/late anchor and sealed-minute retroinsert; conflicting overlap/tie/old
seal; cache disposal before authentic durable readback; and changed catalog,
untrusted role or unauthenticated expected source head. Fixtures must distinguish
pure lexical validity, independent native parsing, authenticated session origin,
visible original readback and eventual provider/runtime acceptance.

Deeper research remains useful for calibrated clock/UTC availability bounds,
Jupiter/RPC cadence and source-block age under the upgraded plan, provider/RPC
pricing and regional latency, durable raw storage/retention cost, safe credential
delivery/rotation and worker process isolation, and explicit cross-package
history/archive compatibility. These are measurement/policy tasks. None is a
reason to describe hashes, supplied ClockBound values or local fixture receipts
as authentic provider/native authority.
