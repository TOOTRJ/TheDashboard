# R3-03A1 exact offline schema proposal — awaiting interface review

Historical proposal retained on 2026-10-13. The text and draft JSON below describe
the initial proposal, before implementation review added reservation pins,
`captured_original` diagnostics and `seal_boundary` writes. They do not describe
the final schema. The unchanged draft JSON's canonical digest remains
`dd10a7b430eeeed3dc51480590fcff15522c5d29d59d2ed5bc85c4f6ba27d499`.
See [SOURCE-ADMISSION-V3-CONTRACT.md](SOURCE-ADMISSION-V3-CONTRACT.md) and the
new `source_admission_v3_policy.py` descriptor for the final research contract.

New files only; no implementation, SQL or authority yet. All envelopes use exact
field sets, canonical bounded UTF-8 JSON, string counters/decimal amounts,
canonical UUIDs/digests and strict unknown/duplicate-field refusal. All have
`policy_sha256` and this exact `authority` object:

```text
provider_attested=false, authenticated_principal=false, calibrated_clock=false,
native_admission=false, committed_readback=false, lease_authority=false,
hosted_authority=false, running_authority=false, live_trading_authority=false
```

The new schema policy descriptor will hash these field sets and current
acquisition/source/transport dependency hashes. Its immutable final hash follows
review; no existing policy/wire receives a new label. Proposed DTO constructors
check syntax only. Supplied context/clock/readback facts do not become authentic
because a parser returns a value or computes a matching digest.

The machine-readable draft is `R3-03A1-SCHEMA-POLICY-DRAFT.json` with 23 exact
field sets and nine new formats. Its draft-policy canonical-byte SHA-256 is
`dd10a7b430eeeed3dc51480590fcff15522c5d29d59d2ed5bc85c4f6ba27d499`.
The file has an ordinary trailing newline outside those canonical descriptor
bytes. Its format explicitly says `draft1`; a final approved policy will receive
an explicit final version/digest rather than silently reinterpret this draft.

## Shared exact nested field sets

```text
Scope = {owner_id, run_id, market_epoch}
Issuer = {owner_id, run_id, market_epoch, acquisition_epoch, issuer_binding_id,
          parser_policy_sha256, endpoint_bindings}
EndpointEntry = {provider_family, endpoint_binding_id}
ProcessClock = {owner_id, run_id, market_epoch, acquisition_epoch,
                wall_lower_us, wall_upper_us, monotonic_us}
UtcGuard = {wall_lower_us, wall_upper_us, observed_at_us}
Policies = {acquisition_sha256, source_sha256, transport_sha256,
            recorder_package_sha256, native_package_sha256}
EpochEntry = {acquisition_epoch, predecessor_epoch, ordinal,
              issuer_principal_binding_id, recorder_package_sha256, status}
KnownRecord = {record_id, capsule_sha256, raw_response_ref, response_sha256}
KnownOperation = {operation_id, operation_kind, original_wire_sha256}
RecordPin = {record_id, capsule_sha256, raw_response_ref, response_sha256,
             request_sha256, response_bytes, provider_family, endpoint_binding_id,
             received_wall_us, received_monotonic_us}
```

Process clocks retain the original recorder epoch; native UTC guards have no
invented process-monotonic field. Guard uncertainty is at most two seconds and
its supplied observed timestamp lies within its interval. Their provenance is
a future native/runtime boundary. Epoch entries form a bounded ordered unique
chain with one current active epoch, retired predecessors and no A→B→A reuse.
The list is a supplied offline witness; completeness/authentication comes from
the future native registry. Immutable historical entries remain readable.

## Reservation

`ga-jupiter-source-reservation-research-v3` fields:

```text
format, policy_sha256, scope, reservation_id, admission_id, capture_id,
observation_id, price_record_id, genesis_record_id, block_time_record_id,
genesis_rpc_id, block_time_rpc_id, issuer, issuer_principal_binding_id,
policies, authority
```

Seven original UUIDs (reservation/admission/capture/observation/three records)
are distinct and explicitly supplied before I/O. Raw references may equal their
own original record ID, as in the existing capsule default, but cannot alias
another packet record/operation/observation. No UUID, sequence or clock allocator
is part of the pure validator.

## Separate append-only capture retention outcome

`ga-jupiter-source-capture-retention-research-v3` fields:

```text
format, policy_sha256, scope, reservation_sha256, capture_id, observation_id,
capsule_wires, diagnostics, collection_completed, failure_code,
eligibility, authority
```

`capsule_wires` preserves zero to three original canonical capsule strings in
Price/genesis/block-time order. `eligibility` must always be false. Capture
retention does not claim source-valid admission even when transport completed.
Each incomplete diagnostic has this exact field set:

```text
record_id, provider_family, endpoint_binding_id, request_sha256,
request_started_wall_us, request_started_monotonic_us,
received_wall_us, received_monotonic_us, http_status,
body_state, incomplete, failure_code
```

Receipt/status values may be null only when unknown. `incomplete=true`;
`body_state` is `not_received`, `partial_discarded`, or `withheld`. There is no
unsafe body, private URL/header/message, fabricated raw hash or replacement
identity. Captured safe capsules may coexist with an incomplete diagnostic for
cleanup/deadline failure under the same attempted original. Fixed failure codes
are whitelisted. Original capture persistence is a separately authenticated
append-only action. A failing source-admission transaction does not magically
persist its rejected capture or diagnostic; that requires its own successful
original-ID capture action/reconciliation.

## Submission and independent expected context

`ga-jupiter-source-submission-research-v3` fields:

```text
format, policy_sha256, scope, admission_id, observation_id,
reservation_sha256, capture_sha256, previous_admission_sha256, authority
```

It submits references to the original reservation/capture, not a normalized
price or a desired new native sequence. The independent expected context is
`ga-jupiter-source-expected-context-research-v3`:

```text
format, policy_sha256, scope, current_issuer, current_principal_binding_id,
policies, epoch_registry, expected_reservation_sha256, expected_capture_sha256,
expected_previous_admission_sha256, prior_ingest_sequence,
known_records, known_operations, original_resolution, original_admission_wire,
process_clock, admission_guard, final_guard, authority
```

`original_resolution` is `fresh_reservation`, `original_committed`, or `unknown`.
An unknown result refuses new admission. A missing getter does not establish
safe terminal absence. The future native reservation/fencing/serialization must
authenticate `fresh_reservation`; the pure enum cannot supply that proof.
An existing original supplies its immutable admission wire and exact original
submission/capture/reservation hashes; conflict refuses before current freshness
checks, while exact original replay preserves its prior outcome and timestamps.

The prior admission witness must retain its original reservation, capture,
submission, process/native guards and normalized age result, each compared
against separately supplied expected hashes. Reparse its raw trio and original
clock facts. Validate its supplied conservative accepted carried-age snapshot
against the raw baseline, then carry that snapshot forward with monotonic
elapsed only within its epoch or conservative UTC elapsed across epochs.
This does not prove the complete earlier accepted ancestry; the authenticated
append-only native source ledger remains required.

The explicit wrapper `ga-jupiter-source-prior-original-witness-research-v3` has:

```text
format, policy_sha256, scope, reservation_wire, capture_wire, submission_wire,
admission_candidate_wire, original_readback_wire, availability_wire, authority
```

Every original wire resolves against its recorded immutable hash links. Its
candidate hash must equal the separately expected previous admission hash. Its
readback/availability must reference that same original. Validation does not
substitute a caller's normalized price/carry snapshot for missing raw originals.

## Admission candidate and original readback witnesses

`ga-jupiter-source-admission-candidate-research-v3` fields:

```text
format, policy_sha256, scope, admission_id, observation_id,
reservation_sha256, capture_sha256, submission_sha256,
previous_admission_sha256, expected_prior_ingest_sequence,
process_clock, admission_guard, final_guard, normalized, authority
```

Normalized exact fields:

```text
asset, mint, decimals, denomination, valuation, price_decimal, block_ref,
genesis_hash, estimated_source_second, source_time_basis,
source_age_floor_us, source_age_ceiling_us, receipt_age_ceilings_us, record_pins
```

The independent validator reparses all three original bodies using shared
bounded JSON/Decimal primitives, but does not call `d.derive_observation`, reuse
its normalized header or treat a source hash as a raw parser. It compares the
candidate to independently recomputed facts under the separately supplied
context and original prior witness. This candidate is a research result, not a
self-issued native receipt. Actual native sequence/accepted timestamp/COMMIT
must be assigned and authenticated by a future independently guarded validator.

`ga-jupiter-source-original-readback-research-v3` fields:

```text
format, policy_sha256, scope, admission_id, original_admission_sha256,
original_reservation_sha256, original_capture_sha256, original_submission_sha256,
observation_id, native_receipt_sha256, native_package_sha256,
supplied_ingest_sequence, supplied_accepted_at_us, readback_guard,
record_pins, authority
```

`supplied_*` and guard names explicitly signal fixture/caller trust inputs.
Validation cannot issue or authenticate a native receipt. Getters must resolve
all exact raw/capsule originals independently; an unavailable body refuses a
complete witness and blocks cache release/new replacement allocation.

## Availability and complete inventory seal

`ga-jupiter-source-availability-research-v3` fields:

```text
format, policy_sha256, scope, availability_id, admission_id,
original_readback_sha256, original_admission_sha256, readback_guard,
available_at_upper_us, authority
```

Its upper bound equals the original supplied readback guard's upper, follows
supplied acceptance, and is never restamped for a cached getter. It is not known
visibility until independently authenticated in the future native channel.

`ga-jupiter-source-inventory-seal-research-v3` fields:

```text
format, policy_sha256, scope, seal_id, start_second, end_second,
seal_guard, through_ingest_sequence, previous_seal_sha256,
inventory_entries, complete_inventory_sha256, eligible_records_sha256,
recorder_package_sha256, source_policy_sha256, authority
```

Inventory entry exact fields:

```text
inventory_sequence, operation_id, operation_kind, original_wire_sha256,
admission_id, observation_id, reservation_sha256, capture_sha256,
admission_sha256, availability_sha256, ingest_sequence, outcome
```

`outcome` is `reserved_pending`, `source_candidate`, `capture_only`, or
`refused_source`; capture/admission/availability references may be null only
according to that outcome and operation kind. Every supplied journal operation
has a unique operation ID, original wire hash and contiguous inventory sequence.
An admission's ingest sequence equals its own serialized inventory-operation
sequence; later availability/capture/diagnostic entries may create gaps between
source admissions. Through-ingest sequence pins this same complete native
journal position. Pending reservations are not omitted from the complete supplied
inventory and never qualify as marks.
The inventory accounts for safe captured and explicitly withheld/refused outcomes
as well as eligible marks. The pure checker proves deterministic supplied
inventory/eligibility/selection and identifies gaps; it cannot prove a caller
included every database row. The independent native registry supplies complete
through-sequence coverage. Exact eligibility requires original accepted-before-
minute-end and committed-readback upper no later than minute end, with latest
accepted-time/unique sequence selection. Native seal may be finalized only after
end+five seconds; no late readback or new insert revises a frozen minute.

## Review questions and implementation order

Recommended: keep the new admission candidate's normalized schema distinct from
the existing `DerivedObservation` header. A later explicit native adapter resolves
these original facts and the accepted source head into the already frozen source
seam; no header wrapping or self-issued `RecordReference` occurs in A1.

Recommended: treat prior accepted carried-age snapshots as separately supplied
research trust inputs constrained by rederived original raw/clock facts. Proving
their complete ancestry/authenticated source head is the A2 native ledger gate,
not a claim made by a fixture digest.

After review, implement strict decoders/revalidators and independent raw-trio,
clock/age-carry, replay/conflict, availability and supplied-inventory validators
with adversarial tests. Bound every input/list/wire and keep all authority false.
Worst-packet pre-reserve accounting is a separate offline test, not an RSS claim.
