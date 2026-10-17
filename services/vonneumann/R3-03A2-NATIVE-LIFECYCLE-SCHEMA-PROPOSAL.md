# R3-03A2 native original lifecycle and complete-journal proposal

Current-state note, 2026-10-13: only the separately scoped B1 actor/catalog
prototype has since received one passing local fourteen-case native run.
`B1-ACTOR-CATALOG-CONTRACT.md` records that bounded result and its earlier
setup failure. The source/epoch/packet/reader/journal/closure/seal/model
lifecycle proposed in this document remains unimplemented and unauthorized;
D5 capacity remains open. No historical proposal hash or A1 wire is relabeled.

Status: **design only; D1–D4 design approved, D5 pending**, 2026-10-13. This new document
reconciles the A2 plan with the frozen original-source and prospective-model
contracts. It changes no existing file, policy, parser, schema, database, model,
source adapter, runtime flag or credential. It runs no test or provider request.
The proposed field sets and limits are review inputs, not installed capabilities
or a final policy descriptor. No implementation may infer authorization from
this document. No commit or remote operation is part of this slice.

Proposal revision 2 adds the independently registered reader process origin and
explicit command-only tombstone links requested by security review. The earlier
fifteen-event proposal is superseded, not a previously issued native wire or
accepted policy. The closed proposed full journal now has sixteen event kinds.

## Frozen dependencies and exact separation

| Input | Reviewed original |
|---|---|
| A1 contract/implementation | `45d2b7aabbb889f4ff628c02a1864e7206192a0d` |
| A1 schema policy | `2c48b61440f7d61f9567fa295da1c9c98a4483c2c834ec7074412d261f085640` |
| Existing A2 plan and completed parser slice | `5410e914d16f0ec906a471007e5fe8a345c8f012` |
| Independent raw parser descriptor | `e7fb225868e9401e5648487e9836d9c0aff817f2ba2cdd63a20b90b75aadb24e` |
| Independent raw parser SQL | `1bcfa71e652f5c462e61bb891828d0d756e70d60a0141a1d203530e17f5e3a94` |
| Prospective model | `760f1553c9cc47fef6d7aa2a0410607c83bc7197` |
| Acquisition / source / transport policies | `912fd28c718311f9b6f72cf0327a7c6b5f4ec7cc4033744d3306064ed869ac89` / `3be1de572d954859002546e5d525ddb0fbda71a5ca844368381a98395571aad1` / `a62184b94f88dbc248a6f3569e171a60e8a0a530addf8ed8aa943b10433f055e` |

The completed parser's sixteen owned PostgreSQL cases establish only its bounded
raw-value projection. A1's forty-one pure cases establish supplied-witness
consistency. The model's offline ledger establishes model consistency. None
authenticates a real recorder, reader, database admission, provider or clock.
Every existing A1/source/model research authority flag stays literally false.
The native experiment uses separate names, records and entry points. It cannot
activate a research wire by setting a flag, changing its header, casting a raw
parser projection or accepting its hash as a principal.

SOL/USD remains Price V3 reference `usdPrice`, wrapped SOL decimals 9, pinned
mainnet genesis and integer `getBlockTime` for that exact Price slot. These are
prospective sampled prices, not OHLCV, exact market closes, executable quotes,
volume, publication-time attestations, finality or measured fills. Initial
history requires 915 complete observed minutes and 61 close-only 15-minute bars;
two EMA genes and the frozen model math remain unchanged.

## 1. One full native journal; no hidden control writes

**Recommended decision D1:** one contiguous scope journal records every committed
native write. Its closed event-kind set is:

```text
installation
epoch_registration
epoch_rollover
reader_epoch_registration
fence_acquire
fence_renew
fence_release
source_pause
source_resume
source_stop
packet_reservation
capture_retention
source_admission
availability_retention
terminal_closure
inventory_seal
```

There is no generic arbitrary event, implicit refusal event or unjournaled actor
configuration edit. An initial `installation` event pins the complete initial
catalog/actor/scope manifests. Subsequent epoch registration and enablement,
fence changes, Pause/Resume/Stop and closures consume real journal positions.
Only successfully committed actions consume positions. Validation failure rolls
the action back; a separately accepted closure or diagnostic-capture action may
later retain an honest observation. Exact replay writes nothing.

`native_sequence` is allocated by incrementing the locked transactional scope
head, never by a caller or a nontransactional sequence. A source admission's
`ingest_sequence` equals **its own native journal position**. Thus successive
admissions legitimately have gaps. Every full journal entry resolves its exact
original command and original result in both directions. The retained lifetime
ID/epoch registries are complete even when a bounded seal omits older intervals.

Frozen A1 expects a contiguous five-kind **supplied** journal and cannot consume
this sixteen-kind inventory. Do not strip controls, close gaps, relabel sequence
values or call that limited projection the native complete ledger. A later
R3-03B bridge must resolve the new native originals/seal and independently
construct the sampled-source/model inputs under a separately reviewed contract.
A1 can remain a pure cross-check of individual original facts with all flags
false. It is not the authoritative full-native-seal validator. If a five-kind
projection is ever added, it needs its own explicit position mapping and pins to
the full head; this proposal implements no such projection.

## 2. Closed scalar types and common records

All proposed wire fields below are mandatory; unknown fields refuse. `?` means
explicit JSON null is allowed in the named cases, not optional omission.
Canonical UTF-8 JSON uses the reviewed duplicate/type/Unicode/number rules;
counter values are canonical unsigned decimal strings in the signed-64-bit
range, UUIDs canonical lowercase and digests lowercase SHA-256. Raw provider
integer tokens remain integers; original raw bytes are never JSONB replacements.
Prices retain the frozen exact scale-18 grid and decimal grammar. No binary64
clock or price conversion is introduced.

The closed proposed format literals are:

| Record | Literal format |
|---|---|
| NativeCommand | `ga-jupiter-native-source-command-research-v3-v1` |
| NativeResult | `ga-jupiter-native-source-result-research-v3-v1` |
| NativeReceipt | `ga-jupiter-native-source-receipt-research-v3-v1` |
| OriginalQuery | `ga-jupiter-native-source-query-research-v3-v1` |
| QueryObservation | `ga-jupiter-native-source-query-observation-research-v3-v1` |
| CommittedOriginalReply | `ga-jupiter-native-source-committed-original-reply-research-v3-v1` |
| ReadObservation | `ga-jupiter-native-source-read-observation-research-v3-v1` |
| NativeSeal | `ga-jupiter-native-source-complete-seal-research-v3-v1` |

Private typed registry rows, JournalEntry, NativeAvailability and tombstone are
resolved under that native policy, not interchangeable public format labels.

```text
Scope = { owner_id, run_id, market_epoch }
Policies = { acquisition_sha256, source_sha256, transport_sha256,
             a1_schema_sha256, raw_parser_sha256, recorder_package_sha256,
             reader_package_sha256, native_package_sha256 }
UtcObservation = { observed_at_us, wall_lower_us, wall_upper_us }
ProcessClock = { owner_id, run_id, market_epoch, acquisition_epoch,
                 monotonic_us, wall_lower_us, wall_upper_us }
ReaderClock = { owner_id, run_id, market_epoch, reader_process_epoch,
                monotonic_us, wall_lower_us, wall_upper_us }
EndpointBinding = { provider_family, endpoint_binding_id, public_origin_sha256 }
PacketIds = { reservation_id, capture_id, admission_id, observation_id,
              price_record_id, genesis_record_id, block_time_record_id,
              read_observation_id, availability_id, closure_id, reconcile_id }
HeadPin = { native_sequence, native_head_sha256, previous_seal_sha256? }
OriginalPin = { semantic_kind, original_id, original_wire, wire_sha256, wire_bytes }
RecordPin = { provider_family, record_id, raw_response_ref, capsule_sha256,
              request_sha256, response_sha256, response_bytes,
              endpoint_binding_id, received_wall_us, received_monotonic_us }
Limits = { provider_attested:false, calibrated_clock:false,
           hosted_authority:false, running_authority:false,
           live_trading_authority:false, model_native_join:false }
```

All eleven `PacketIds` are different and are allocated before collection. The
first seven retain the A1 meanings; the four new native/reader IDs never borrow
a capture, admission, record or configuration UUID. `reconcile_id` is reserved
as query correlation, not an implied write/action receipt (decision D3 below).
RPC IDs are separately allocated canonical bounded integers, not journal IDs.
The only permitted raw-reference alias is its **own** original record UUID when
the frozen capsule contract allows it. Same bytes do not permit reuse by another
record, packet, scope or epoch. The private global ID registry includes reserved,
excluded and terminal IDs and configuration/actor/fence IDs. A foreign existing
ID and an absent random ID produce the same safe public absence result.

`Limits` is a closed statement of what the experiment does not establish, not
the source of a permission grant. Actual laboratory write permission comes from
the independently installed database binding and capability check. A native
record cannot establish production clock, provider or model authority merely
because its bytes or digest match.

`OriginalPin.original_wire` is exact original canonical UTF-8 JSON text;
`wire_bytes` is its checked byte count, not a replacement for that body.
Provider bytes remain original base64 inside their capsule. Its semantic kinds
are exactly `native_command, native_result, native_receipt, a1_reservation,
a1_capture, a1_submission, provider_capsule, native_epoch_registration,
native_fence_record, native_read_observation, native_availability, native_seal,
native_tombstone`. Command/result/receipt are semantic views of the **same**
allocated action ID, not separate identity allocations or write events. The A1
submission similarly retains the admission ID under its distinct frozen view.
An allowed view association does not permit the ID to become another action.
Reader registry dependencies additionally use the closed semantic kind
`native_reader_epoch_registration`.

## 3. Server-held actor, epoch and fence bindings

Private immutable registry records have the following exact proposed fields:

```text
InstalledPackage = { installation_id, database_identity_sha256,
                     native_package_sha256, catalog_manifest_sha256,
                     policies, scope, initial_actor_manifest_sha256 }
ActorBinding = { principal_binding_id, database_identity_sha256,
                 session_user_oid, session_user_name, scope, capabilities,
                 recorder_package_sha256?, reader_package_sha256?,
                 issuer_binding_id?, endpoint_bindings, installation_id }
EpochRegistration = { registration_id, scope, acquisition_epoch, ordinal,
                      predecessor_epoch?, recorder_principal_binding_id,
                      reader_principal_binding_id, issuer_binding_id,
                      recorder_package_sha256, reader_package_sha256,
                      policies, endpoint_bindings, original_command_sha256 }
ReaderEpochRegistration = { registration_id, scope, reader_process_epoch,
                            ordinal, predecessor_reader_epoch?,
                            reader_principal_binding_id, reader_package_sha256,
                            original_command_sha256, native_sequence }
FenceRecord = { fence_id, scope, holder_principal_binding_id,
                acquisition_epoch, revision, issued_at_us, expires_at_us,
                original_command_sha256, native_sequence }
ScopeHead = { scope, native_sequence, native_head_sha256,
              active_acquisition_epoch, active_fence_id?, fence_revision,
              source_mode, last_admission_sha256?, last_ingest_sequence,
              last_availability_sha256?, previous_seal_sha256? }
IdentityAssociation = { owner_id, run_id?, market_epoch?, packet_reservation_id? }
IdentityRecord = { original_id, identity_role, association,
                   original_allocation_sha256, first_native_sequence }
```

`capabilities` is a duplicate-free subset of this closed set:
`reserve, retain_capture, admit, read_original, retain_availability,
close_original, seal, fence_manage, control, register_epoch, register_reader_epoch,
install`. Installer-only entries
cannot be provisioned by a recorder, operator-supplied UUID or application
service-role label. `identity_role` is exactly a packet-ID field name or
`owner_id, run_id, installation_id, principal_binding_id, issuer_binding_id,
endpoint_binding_id, market_epoch, acquisition_epoch, reader_process_epoch,
registration_id, fence_id, control_action_id,
seal_id`. A raw reference has its original record association, not a new role
exception. Fixed scope owner/run UUID meanings cannot alias packet allocations.
For `owner_id`, association has that owner with run/market/packet null; for
`run_id`, it has the held owner/run with market/packet null. For every other
configuration identity it has the full held owner/run/market and null packet;
packet IDs have the full scope and original reservation. Thus the same real
owner can legitimately have multiple runs and the same run multiple market
epochs without allocating its owner/run UUID again or permitting a role alias.
Other scope/role associations refuse. Endpoint bindings are exactly the two
accepted families `jupiter-price-v3` and `solana-rpc`, in canonical order; the
three records still retain Price→genesis→block-time request distinctions. No
Birdeye family can be added to this profile by importing a broader parser cap.

Recommended capability profiles for the lab are separate actors:

| Profile | Allowed capabilities |
|---|---|
| Private installer | `install, register_epoch, read_original` |
| Recorder | `reserve, retain_capture, admit, read_original, close_original, fence_manage` |
| Original reader | `read_original, retain_availability, register_reader_epoch` |
| Sealer | `read_original, seal` |
| Scoped control actor | `control, read_original, close_original` |

An actor with another profile cannot gain a capability from a command field.
The installer provisions the closed accepted actor manifest before the lab;
epoch registration can reference only those existing immutable bindings. Adding
an actor, capability, accepted package or catalog policy is outside this initial
native schema and needs a separately reviewed installation/event policy; no
unrecorded registry edit is implied. Epoch rollover requires both the held
installer-approved successor registration and the scoped control capability.

The runtime actor is the real `session_user` **name and OID**, resolved to the
private binding under the checked installation. `SET ROLE`, caller owner fields,
hashes or a name recreated with another OID cannot supply that binding. Check
transitive memberships, superuser/bypass/create privileges, relevant parameter
privileges, ACL/default ACL, object owners and the accepted catalog fingerprint.
Every entry/getter uses explicit qualified application objects and
`pg_catalog,pg_temp` search path with qualified catalog references. Benign shadow
sentinels must prove that temp objects cannot redirect checks. Do not alter
database-wide PUBLIC TEMP or shared users/configuration.

An epoch row is immutable. Active/retired state is derived from committed epoch
events; it is not rewritten on an old row. Registration must reference the
current last epoch; enabling a successor is explicit, serialized and binds the
same accepted recorder package. The complete lifetime registry refuses A→B→A,
even after A disappears from rolling history. A retired epoch remains readable
for original facts. Cross-package continuation is unsupported; it needs accepted
archive dispatch or a separately authorized new warmup. No old package label,
monotonic origin, history anchor or receipt is rewritten.

Reader origins have their own immutable registry and committed
`reader_epoch_registration` events. The authenticated accepted reader can
register only its own new same-package `reader_process_epoch`, with its actual
binding and the held prior reader-origin reference. Native ordinal/position are
server assigned. This registration uses the current head and null fence fields;
it does not create source freshness, enable recorder acquisition or revise an
availability. All previous reader origins stay in the full lifetime registry;
reader A→B→A, a recorder epoch reused as reader epoch, wrong principal/package
or another scope's origin refuse. The complete epoch-view digest includes both
the recorder acquisition and independent reader-origin registries.

Retired reader observations remain exact historical facts. A new reader process
has its own monotonic origin, even if the same acquisition epoch is still active.
No reader counter is compared or subtracted against a recorder counter or a
different reader origin. The original recorder `ProcessClock` stays unchanged;
the observation bridge uses separately validated UTC intervals between them.
Authenticating the registered native actor still does not prove that a supplied
process clock really came from its reviewed runtime; that remains A3's gate.

The fence is a laboratory serialization hold, not the engine's economic lease.
Its holder/revision/current epoch and actual expiry are checked under locks,
after expensive work and at recognized commit processing. Renewal is a new
explicit original control, never a clock refresh on an existing packet.

## 4. Exact proposed commands and event bodies

The outer mutating command is:

```text
NativeCommand = { format, native_policy_sha256, scope, action_id, action_kind,
                  expected_head, expected_fence_id?, expected_fence_revision?,
                  body }
```

`format` is proposed `ga-jupiter-native-source-command-research-v3-v1`; a new
native policy digest will be frozen only after root review. `action_kind` is one
event kind above. `body` must match exactly its corresponding set below. There
is no caller native clock, ingest position, chosen receipt or authority flag.
Exact original replay lookup precedes the fresh-write checks. Original replay
still requires current authorized scoped read capability. Fresh expected-head
and fence requirements are explicit per class, rather than making expired
originals impossible to retain or reconcile:

- Admission, epoch/fence changes, Pause/Resume and seal require the current
  complete expected head; fresh collection/admission also requires the current
  unexpired recorder fence and open mode.
- Stop requires the current expected head and independently authorized control
  actor, but no live recorder fence or source data. Installation uses the fixed
  empty genesis head.
- Capture, availability and closure bind an **original scoped ancestor head**
  plus the exact current target/allocation/dependency facts under the held
  current head. They do not require that their previously observed head remain
  current after a concurrent Stop. Their authorized archival/closure capability
  requires no source freshness or live recorder fence, grants no new collection,
  and cannot change original receipts. A supplied unknown/foreign ancestor hash
  refuses. This avoids rebasing an uncertain command merely to close it.

For capture/availability/closure the expected fence fields are null. For Stop
they are null; for installation, epoch registration, epoch rollover, Pause and
reader epoch registration and seal they are null. Admission, reservation, Resume and fence renewal/release
name their exact held fence/revision. A fence acquisition names null expected fence
only when the private head independently has no active hold. Epoch registration
is installer-authorized at the current expected head, with null fence fields;
it does not enable collection. A reservation requires the current head/fence,
open mode and no unresolved predecessor before any provider I/O.

Capture/availability/closure/seal require their narrow authenticated capability,
not a live recorder fence. Pause/Stop require scoped control capability without
source freshness or a live recorder hold; Resume additionally needs the current
unexpired recorder hold and current enabled epoch. Epoch rollover uses its held
installer-approved successor plus control capability, with no pending original;
it invalidates the old hold and pauses collection. `fence_manage` can acquire,
renew or release **only the authenticated recorder's own** enabled-epoch hold;
the supplied holder ID must equal that actual binding. It grants no source
Pause/Resume/Stop or epoch/package provisioning. No expired hold is renewed;
fresh reacquisition gets another preallocated fence ID/revision under the scope
head and cannot hide an unresolved packet or restore an economic lease.

| Event | Exact body fields | Important fixed rule |
|---|---|---|
| installation | `installation_id, scope, policies, catalog_manifest_sha256, actor_manifest_sha256, genesis_registry_sha256` | Private installer only; complete initial state pinned. |
| epoch_registration | `registration_id, predecessor_epoch, acquisition_epoch, recorder_principal_binding_id, reader_principal_binding_id, issuer_binding_id, policies, endpoint_bindings` | Successor never previously allocated; no activation by registration alone. |
| epoch_rollover | `registration_sha256, predecessor_epoch, successor_epoch, expected_last_admission_sha256, expected_last_availability_sha256` | Same accepted recorder/reader packages; no unresolved original; successor enabled and prior fence invalidated; new fence acquired separately. |
| reader_epoch_registration | `registration_id, reader_process_epoch, predecessor_reader_epoch, reader_principal_binding_id, reader_package_sha256` | Authenticated reader registers only its own new same-package origin; full retained registry, no clock or source-epoch rewrite. |
| fence_acquire | `fence_id, acquisition_epoch, holder_principal_binding_id, requested_duration_us` | Duration bounded by reviewed policy, generated UTC/revision held server-side. |
| fence_renew | `fence_id, expected_revision, requested_duration_us` | Same holder/current epoch; no resurrection after expiry. |
| fence_release | `fence_id, expected_revision` | Retains original fence and increments revision; no ID reuse. |
| source_pause | `expected_control_sha256, expected_mode` | No market request or fabricated economic close. |
| source_resume | `expected_control_sha256, expected_mode` | Only paused→open, independently current epoch/fence and no unresolved original. |
| source_stop | `expected_control_sha256, expected_mode` | Terminal source mode; invalidates fresh-writing fence. |
| packet_reservation | `packet_ids, genesis_rpc_id, block_time_rpc_id, original_a1_reservation_wire, policies, issuer_binding_id, acquisition_epoch` | Seven A1 IDs and every embedded policy/link exactly match native preallocation. |
| capture_retention | `reservation_sha256, original_a1_capture_wire` | Its `action_id` is the preallocated capture ID; safe original bodies/diagnostics only; eligibility remains false. |
| source_admission | `reservation_sha256, capture_sha256, original_a1_submission_wire, process_clock, expected_prior_admission_sha256, expected_prior_ingest_sequence` | Raw trio independently parsed; no supplied Candidate/ExpectedContext/prior inventory. |
| availability_retention | `reservation_sha256, admission_sha256, original_read_observation_wire` | Its `action_id` is preallocated availability ID; immutable original observation links. |
| terminal_closure | `reservation_original_pin, target_kind, target_original_pin, expected_capture_sha256, closure_reason` | Preallocated closure ID; atomic locked reconciliation plus permanent tombstone if target not committed. |
| inventory_seal | `seal_id, start_second, end_second, expected_previous_seal_sha256, expected_through_head` | Caller supplies no eligible list or complete journal; native locked state is resolved. |

For installation/epoch/fence/control actions `action_id` is their independently
allocated original operation UUID. For reservation/capture/admission/availability/
closure it equals the respective preallocated packet ID. Seal action ID equals
`seal_id`. `expected_head` is a complete `HeadPin`, interpreted under the explicit
current-versus-original-ancestor rules above, not an optional current-state
claim. The scope head stores its actual original values, not the desired ones.
Nullable prior digests are permitted only at genesis; `expected_mode` is exactly
`open, paused, stopped`, constrained by the operation's legal transition.

Recommended finite fence durations are **not set here**: minimum, maximum,
renewal margin and hold lifetime require root freeze and genuine-clock tests.
Their absence closes implementation rather than supplying a guessed default.

## 5. Original commands, results and exact replay

Private original operation/result records are proposed as:

```text
OriginalOperation = { action_id, action_kind, scope, original_command_wire,
                      original_command_sha256, original_result_wire,
                      original_result_sha256, original_receipt_wire,
                      original_receipt_sha256, native_sequence }
NativeReceipt = { format, native_policy_sha256, scope, action_id, action_kind,
                  original_command_sha256, result_sha256, native_sequence,
                  previous_native_head_sha256, admission_observation?,
                  final_function_observation, commit_processing_observation?,
                  native_package_sha256, catalog_manifest_sha256, limits }
NativeResult = { format, native_policy_sha256, scope, action_id, action_kind,
                 native_sequence, original_command_sha256, dependencies,
                 result_body, limits }
JournalEntry = { native_sequence, action_id, action_kind,
                 original_command_sha256, original_result_sha256,
                 original_receipt_sha256, previous_native_head_sha256 }
```

The exact `result_body` union is closed by `action_kind`:

```text
installation = { installation_id, catalog_manifest_sha256,
                 actor_manifest_sha256, genesis_registry_sha256 }
epoch_registration = { registration_sha256, acquisition_epoch, ordinal }
epoch_rollover = { predecessor_epoch, successor_epoch,
                   registration_sha256, resulting_source_mode }
reader_epoch_registration = { registration_sha256, reader_process_epoch,
                              predecessor_reader_epoch?, ordinal }
fence_acquire = { original_fence_record }
fence_renew = { original_fence_record, previous_fence_sha256 }
fence_release = { fence_id, previous_fence_sha256, resulting_fence_revision }
source_pause = { previous_mode, resulting_mode, previous_control_sha256?,
                 resulting_fence_revision }
source_resume = { previous_mode, resulting_mode, previous_control_sha256?,
                  resulting_fence_revision }
source_stop = { previous_mode, resulting_mode, previous_control_sha256?,
                resulting_fence_revision }
packet_reservation = { packet_ids, original_a1_reservation_sha256,
                       allocation_manifest_sha256, policies }
capture_retention = { original_a1_capture_sha256, collection_completed,
                      eligibility:false, failure_code?, raw_manifest_sha256 }
source_admission = { admission_id, observation_id, reservation_sha256,
                     capture_sha256, original_submission_sha256,
                     previous_admission_sha256?, prior_ingest_sequence,
                     process_clock, normalized, admission_observation,
                     final_function_observation, ingest_sequence }
availability_retention = { original_read_observation_sha256,
                           original_native_availability }
terminal_closure = { original_tombstone_sha256, outcome:terminal_nonadmission }
inventory_seal = { original_native_seal_sha256 }
```

`original_fence_record`, `original_native_availability`, `original_native_seal`
and `normalized` use exactly the named sets here; `normalized` has the frozen
A1 `Normalized` field/type/meaning set, independently generated from native
originals without an A1 Candidate wrapper. All source admission clocks are
original integer observations. Only admission has nonnull receipt
`admission_observation`; other kinds require null. Completed capture requires
`failure_code=null`/exactly three safe capsules/no diagnostic; incomplete capture
requires its frozen whitelisted failure and original diagnostic/capsule rules.
Source modes and closure outcomes are literal strings, not Boolean aliases.
`result_body` never carries a mutable success flag or arbitrary extra payload.

Every `original_command_sha256` and
`TerminalTombstone.original_closure_command_sha256` hashes exactly the original
COMMAND bytes. They never mean Result, Receipt or OriginalOperation digest.
The tombstone can therefore be hashed by its closure Result without a cycle.
Epoch/fence/reader registry dependencies follow the same command-only rule.

`dependencies` is a sorted, duplicate-free bounded list of `OriginalPin`; actual
full bytes are resolved from immutable storage and hashing never substitutes
for their association. There is no self-hash: `result_sha256` hashes Result;
Receipt hashes Result but Result does not hash Receipt. Journal/head hash the
completed original Result/Receipt pair. The candidate's earlier final function
guard is not rehashed to claim it occurred during later commit processing.

The deferred guard must store its separate observation before computing the
final original receipt/journal head, within the same transaction. An earlier
provisional return is explicitly `pending_commit` and cannot carry the final
receipt/hash. Only a separate committed getter can return the final originals.
The exact receipt assembly/head ordering and one-operation-per-transaction
mechanism remain acceptance gates; this document does not assert their existence.

Fresh mutation locks in one reviewed order: actor/package binding, scope head,
original packet/operation, then globally ordered UUID/dependency identities.
All late writers and closures follow that order and recheck tombstones/bindings
under the locks. Unique constraints are not a substitute for reviewing opposing
cross-packet UUID lock orders. No actor can read its own uncommitted admission
as a committed fact. One new write action per transaction; no two deferred
admissions chained within the same transaction.

For a retained original, compare **exact original command bytes**, kind, scope,
allocation, original capsule/raw/body associations and every dependency before
any fresh-age/head/epoch check. Exact matching replay preserves original clocks,
native position, result and receipt; it appends nothing. Changed bytes or a
same-ID hash/kind/package association refuse. An unauthorized/foreign scope
cannot turn replay into an existence oracle. Historical facts remain readable
after expiry, Stop or epoch rollover; their historical status grants no current
fence, source freshness or continuation permission.

## 6. Uncertain, found, absent and terminal closure

**Recommended decision D3:** reconciliation is a scoped **read-only observation**,
not a persisted mutation claiming terminal absence. Its closed query/response:

```text
OriginalQuery = { format, native_policy_sha256, scope, reconcile_id,
                  target_kind, target_id, expected_original_command_sha256 }
QueryObservation = { format, native_policy_sha256, scope, reconcile_id,
                     target_kind, target_id, resolution, observed_head,
                     original_operation_pin?, terminal_closure_pin?, limits }
CommittedOriginalReply = { format, native_policy_sha256, scope, target_kind,
                           target_id, original_command_wire,
                           original_result_wire, original_receipt_wire,
                           dependencies, observed_head, limits }
```

`target_kind` is exactly `packet_reservation, capture_retention, source_admission,
availability_retention, terminal_closure`. `resolution` is exactly
`original_committed, terminal_closed, observed_absent_unknown`. A locked getter
without a committed tombstone still returns `observed_absent_unknown`. Query
responses are observations of different heads, not immutable admitted results;
the preallocated correlation ID does not manufacture a write receipt. Their
originals/observed head remain distinguishable. If root instead requires durable
reconciliation observations, that needs another explicit event kind, original
action allocation and capacity budget; it cannot silently add an unjournaled
write or turn a cached unknown response into current knowledge.

Nullability is outcome-specific: `original_committed` requires a resolved
`original_operation_pin`; `terminal_closed` requires a resolved
`terminal_closure_pin` and null original pin; `observed_absent_unknown` requires
both pins null. A retained reservation/capture can legitimately be found while
its packet is terminally non-admitted, so `original_committed` may also retain
that packet's closure pin for those two target kinds. A committed admission and
a non-admission tombstone cannot coexist. Every nonnull pin must resolve its
exact scoped relationship; a classification alone is insufficient.

`CommittedOriginalReply` contains final committed originals and their complete
bounded dependency closure. Its current observed-head metadata does not alter
their immutable bytes or supply a later receipt. The trusted reader stores the
hash and bytes of the **particular complete reply it actually validated**.
Missing bodies, changed original command/result/receipt pins or a partial page
are not a successful complete read observation. Native getters may later return
the same original facts under another current observed head; that is not a
replacement for the earlier original reader observation.

`terminal_closure.target_kind` is restricted to `packet_reservation,
capture_retention, source_admission`: closure is for a packet that **has not
committed admission**. `target_original_pin` retains the exact originally
attempted target command bytes/hash; `reservation_original_pin` retains the
entire exact preallocated reservation command, even if its transaction was
observed absent. Closure reason is a closed safe class:
`operator_abandonment, observed_expiry, invalid_capture, capacity_refusal,
transport_incomplete, unknown_outcome_abandonment`. These are observations or
operator classifications; none attests which unobserved rollback branch ran.

The closure transaction rechecks the real actor, locks the scope/original IDs,
and resolves the exact target and admission before deciding. If admission is
already committed, it refuses terminal closure and returns the safe found
original through the ordinary getter; no tombstone overwrites success. If it is
not committed, atomically retain one original closure command/result/journal
entry and a permanent packet tombstone containing:

```text
TerminalTombstone = { closure_id, scope, packet_ids,
                      reservation_original_sha256, target_kind,
                      target_original_sha256, retained_capture_sha256?,
                      closure_reason, native_sequence,
                      original_closure_command_sha256 }
```

Every future queued/replayed fresh writer checks that tombstone after obtaining
the same locks. IDs remain allocated forever; absent admission cannot later
succeed after the closure releases locks. Existing safe captures/reservations
stay immutable and inspectable. Missing capture at a failed admission is null,
not invented retained data. A closure's lost reply is itself uncertain; resolve
the **same closure ID/bytes**, never issue another closure or packet ID merely
because its getter was initially absent. No same-byte resend or reacquisition
policy is enabled by this design.

Closure is permitted only after the owner has stopped its original collection
and cleanup; that actual process condition is an A3 gate, not something SQL can
infer from a UUID. If the exact capture command was attempted but never
committed, its original safe bytes remain retained as the closure's target
dependency, explicitly an **attempted** original, not an accepted Capture.
Already committed capture bytes remain their original accepted operation.
There is no new capture write after terminal closure, no relabeling of attempted
capture as committed, and no disposal of original evidence merely because its
admission was refused. The independent target-pin parser must enforce the
closed safe command grammar before retention; arbitrary malformed/secret-bearing
command bytes cannot be stored by bypassing it through closure.

| Observed state | Permitted next work | Forbidden inference |
|---|---|---|
| Reservation reply lost; getter absent | Same-ID query or locked original closure | Not permission to collect/reallocate. |
| Reservation committed, no capture | Exact capture action or closure | Reservation alone is not source evidence. |
| Safe capture committed, admission unknown | Resolve original admission or close it under locks | No replacement sample/submission. |
| Admission committed, availability unknown | Resolve/create the one genuine original reader observation and retain its exact availability action | No backdated minute or refreshed source receipt. |
| Original availability committed | Historical getter/replay; new packet only under independent current binding/fence | Availability hash is not current-action freshness. |
| Terminal closure committed | Historical getter/replay; later separately authorized packet with fresh IDs | Closed packet IDs cannot ever acquire admission. |

The recorder remains serial across unresolved originals. A fresh reservation
cannot hide an unknown predecessor. A committed late availability may resolve
the original prior chain while leaving a missing minute permanently ineligible;
new correctly observed minutes can begin a new contiguous warmup interval.

## 7. Trusted original reader and availability

**Recommended decision D2:** retain late original read observations as historical
facts, distinguishing retention from minute/current freshness. This matches
A1's separate baseline/readback validation and seal eligibility. There is no
age exception for a current protective/decision action. Reader availability
is the time its complete committed-original reply was received and validated,
not the SQL transaction's admission time, a getter's execution or cache lookup.

Proposed original reader wire:

```text
ReadObservation = { format, native_policy_sha256, scope, read_observation_id,
                    reservation_sha256, admission_sha256,
                    original_committed_reply_sha256, original_receipt_sha256,
                    original_submission_sha256, original_capture_sha256,
                    reader_principal_binding_id, reader_package_sha256,
                    acquisition_epoch, reader_process_epoch, request_started_wall_us,
                    request_started_monotonic_us, received_wall_us,
                    received_monotonic_us, validated_clock, record_pins }
NativeAvailability = { availability_id, scope, read_observation_sha256,
                       admission_sha256, original_receipt_sha256,
                       available_at_upper_us, actual_retention_observation,
                       native_sequence, limits }
```

`validated_clock` is the exact original **ReaderClock** after verifying the entire
committed reply; its epoch equals the independently resolved reader origin and
its UTC upper is `available_at_upper_us`. Its UTC lower is at least the original
candidate final-function upper, original acceptance and its own reply-received
wall time. Its monotonic counter is at least its own reply-received counter;
request/receipt/validation differences use only this reader origin. Neither a
shared recorder acquisition epoch nor a later reader epoch permits subtraction
against original recorder counters. Actual later SQL retention time is
separately retained and never replaces the original observation interval.
ReadObservation's `acquisition_epoch` identifies the original packet; it is not
the reader's monotonic origin and can identify an archived earlier packet.

The real session reader binding must match the installation/epoch registry and
accepted reader package. That authenticates the narrow lab actor, **not the
truth of a supplied clock or actual network delivery**. A3 must implement the
trusted process/manifest/TLS/clock/readback protocol and durable original
observation storage before real-availability activation. A2 fixtures can supply
explicit lab observations and prove their scoped association/causal storage,
while reporting that acquisition/delivery/calibration remains unproved.
Cryptographic hashes, DB role possession or pinned TLS alone do not fill that
gap. No server helper issues an availability time merely because it can see a row.

Preallocate observation/availability IDs. Once a complete original observation
has been captured, persist its exact bytes safely before the availability write;
all retries/getters retain that same original interval. A lost acknowledgment
does not create a later observation ID or restamp the earlier one. If no complete
validated observation ever existed, a later genuine first read can be retained
under the original prepared ID, honestly late and possibly ineligible. If the
reader cannot prove whether an earlier captured original existed, outcome stays
unknown; it may not assert a new first observation. The crash/durable handoff
protocol is A3, not a policy supplied by a receipt hash.

Late observation or retention after a seal never revises that sealed inventory.
Freshness at original admission is preserved separately; old history is not
claimed fresh now. The last accepted prior requires its original durable
readback/availability chain before a new prior-linked admission. Its read
interval is not a lower bound for the next distinct native admission guard.

## 8. Source/native UTC, controls and immutable seals

Raw trio requests and bodies are resolved from durable captures, independently
reparsed by the reviewed parser, and checked against actual reservation/issuer/
endpoint identities. Caller candidates/normalized prices, ExpectedContext,
known-ID subsets, prior wires, native times and epoch lists cannot replace
server-held facts. Process-clock inputs are separately bound to the accepted
recorder protocol; their lexical correctness does not establish calibration.
Source age cannot be reduced below the raw/receipt/clock baseline or accepted
prior carry. Same epoch uses genuine monotonic elapsed; cross epoch uses
conservative UTC interval differences, never cross-process monotonic subtraction.

Record real native integer UTC after parsing/locks, again after final writes,
and at separately recognized commit processing. Require receipt ages strictly
below 5,000,000 microseconds, source ceiling at most 30,000,000 and future
tolerance at most 2,000,000. Admission observation, final function and prior
corresponding lower/upper/observed values must not regress; current admission
observed is at least prior original accepted time. Block and estimated source
second do not regress; a repeated block requires exactly the same price and
source second. Apply that order across every admitted original in native ingest
order, including unavailable/excluded records. No ordinary accepted timestamp
is floored, rounded up, rewritten or delayed by the old integral-v2 action rule.

Accepted-at is original native admission observation, **not COMMIT visibility**.
Final-function and commit-processing observations are separate. Genuine clock
regression refuses. Recognized standalone COMMIT/session/catalog restrictions
require new native tests. Even a successful deferred guard proves freshness at
that processing point only; later PostgreSQL/WAL/deferred/durability work can
occur. Timeout is unknown, not proof of rollback or a hard source-to-durable
deadline. There is no production calibration or five-second SLA claim here.

Source modes are `open, paused, stopped`. Pause/Stop need no quote; Stop can be
serialized by a scoped control actor after the recorder's hold expires, revokes
fresh-writing permission and preserves unknown originals for reconciliation.
Historical getters, safe retention, closure and seals remain narrowly possible;
none resumes the worker. Resume only accepts paused→open under independently
current bindings. Stopped cannot Resume. Source controls do not claim to execute
the model's economic Pause/Resume/Stop/recovery or liquidate holdings. The model
keeps its frozen controls: Stop aborts partial scores and preserves positions;
epoch rollover aborts the partial cohort, preserves accounts/history and pauses.
The later full-native/model join must make corresponding control admission
atomic and complete, with no omitted model/control event. Recovery is outside
this source-only event set and cannot be invented without that join.

Proposed complete native seal:

```text
NativeSeal = { format, native_policy_sha256, scope, seal_id,
               start_second, end_second, previous_seal_sha256?,
               through_native_sequence, through_native_head_sha256,
               recorder_package_sha256, policies,
               complete_inventory_sha256, complete_identity_view_sha256,
               complete_epoch_view_sha256, eligible_originals_sha256,
               minute_winners, dependency_manifest_sha256,
               actual_seal_observation, limits }
MinuteWinner = { minute_start_second, admission_sha256,
                 original_submission_sha256, reservation_sha256,
                 capture_sha256, original_receipt_sha256,
                 read_observation_sha256, availability_sha256,
                 ingest_sequence, accepted_at_us, available_at_upper_us,
                 price_decimal, record_pins }
```

The native seal traverses actual contiguous journal entries through its locked
head, including installation/epochs/fences/Pause/Resume/Stop, reservations,
captures, admissions, unknown/pending exclusions, late availability, closures
and previous seals. Both journal→original and original-write→journal coverage
are checked, with full immutable dependency closure and namespace identities.
No invented failure row stands in for a rolled-back operation. Pending packet
allocations remain explicit exclusions. Completeness comes from private native
state, not client pages, a digest or a supplied inventory list.

Its own write is **outside** its own through-head/hash and consumes the next
native position; a next seal includes that original boundary. Initial range is
915 complete minutes aligned to 15-minute boundaries. Increment advances one
15-minute bar and verifies the exact prior 15-minute overlap in the 30-minute
seal range; later full history retains 900 old minute anchors byte-for-byte.
Each minute needs at least one accepted original within `[start,end)`, with its
genuine original committed-read observation upper no later than minute end.
Qualification independently checks the frozen original source/receipt/causal
bounds; select latest actual accepted-at then unique ingest position. Seal no
earlier than interval end plus the unchanged five-second margin. That margin
is unmeasured operational capacity, not source freshness or latency permission.
Missing, late, uncertain or unlinked anchors refuse; no padding/interpolation.
Sample offsets remain explicit and are not exact market-close claims.

Locks prevent a later insertion from entering the frozen through-head. Later
availability/capture/closure has a greater native position, cannot backdate
actual observation, and cannot reopen a sealed minute. A failed seal rolls back
only its attempted write; previously committed originals remain intact. Future
bounded getters bind every page to the same original head/digest. Pages prove
neither omitted-row completeness nor an enlarged accepted seal capacity.

## 9. Finite capacity and native acceptance order

Retain the reviewed 1 MiB packet reserve, 4 MiB envelope, 8 MiB seal, 4,096-row
per-seal/known inventory, 128 supplied epoch and 24,576 dependency engineering
bounds as **closed limits pending native sizing**. They do not cap lifetime
registry completeness or prove CPU/RSS/latency. Eleven IDs and native envelopes
add overhead and require a new measured reserve test before a producer claims
the earlier seven-ID bound still covers them. Every lifetime original remains
durable until an explicitly reviewed retention/release policy exists.

One successful packet per minute consumes 3,660 source writes over 915 minutes,
leaving only 436 of 4,096 positions for initial installation, epochs/fences,
controls, failed captures/closures and other writes. D1 includes these real
costs. Faster collection, renewal cadence and refusals may exceed this capacity;
measure the complete engineering trace before choosing cadence or implementing
single-seal storage. Do not silently widen limits, truncate controls, prune IDs
or reinterpret paging as a larger seal. A forward capacity policy, if needed,
is a separate root-reviewed change.

### Explicit renewal, original-ID and storage arithmetic

Let `N=915`, ideal interval length `T=54,900 seconds`, and hypothetical renewal
cadence `C`. Ideal fence events are one acquisition plus
`max(0,ceil(T/C)-1)` renewals. This counts a renewal strictly before the ideal
ending boundary; alignment, pre-start holds, scheduler/expiry margin, restarts
and an actual longer trace can require more. It neither chooses a hold duration
nor proves that cadence/hold is safe. The reviewed hold lifetime must exceed
the renewal interval by its separately measured required margin.

| Hypothetical cadence C | Ideal renewals | Acquisition + renewals | Source + fence writes | Remaining of 4,096 before every other event |
|---|---:|---:|---:|---:|
| 60 s | 914 | 915 | 4,575 | **over by 479** |
| 120 s | 457 | 458 | 4,118 | **over by 22** |
| 180 s | 304 | 305 | 3,965 | 131 |
| 300 s | 182 | 183 | 3,843 | 253 |
| 600 s | 91 | 92 | 3,752 | 344 |
| 900 s | 60 | 61 | 3,721 | 375 |

These are arithmetic scenarios, not recommended or accepted fence settings.
The 60-second scenario already cannot fit before installation, recorder/reader
epochs, Pause/Resume/Stop, incomplete attempts, closures or the seal boundary.
It must not be made to fit by omitting renewals from the complete journal.
For an independently chosen reserve `R` for all non-source/non-fence events,
the row condition is `4N + F + R <=4096`, leaving `F <=436-R`:

| Hypothetical other-event reserve R | Maximum ideal fence events F | Meaning |
|---|---:|---|
| 16 | 420 | A 120-second cadence still cannot fit. |
| 32 | 404 | A 180-second scenario leaves only 99 additional positions beyond that reserve. |
| 128 | 308 | The 180-second scenario leaves only three positions beyond that reserve. |

No reserve in this table is a policy default or an adequate refusal budget.
A failed capture plus terminal closure costs two extra writes, and one failed
packet reservation/capture/closure can cost three; genuine admission rollback
does not create an invented admission row. Reader restarts and operator actions
also consume rows. Reserve exhaustion must close collection before allocating
an unsupported seal, preserve all original state, and require an independently
authorized resolution/capacity policy; it cannot prune an adverse outcome.

The other independent budgets also need proof:

- **IDs:** eleven prepared packet IDs give `11N=10,065` lifetime packet/query/
  reader/closure identities, even for 915 otherwise successful packets. The
  three original record IDs are `3N=2,745`; unused prepared closure IDs remain
  allocated. Fence/action/configuration/reader-origin IDs add to this count.
  Private lifetime UUID membership is not capped or truncated to the A1
  4,096 supplied-known-operation limit. Exporting a complete identity view above
  that supplied bound is a new native representation decision, not permission
  to enlarge an A1 list.
- **Dependencies:** an explicitly naive distinct-view inventory counts twelve
  native command/result/receipt views per successful packet (four writes), three
  A1 reservation/capture/submission wires, three provider capsules, and one reader
  observation plus one native availability: `20N=18,300` possible dependency
  views before controls/registry/seals. A fence event with its command/result/
  receipt and immutable fence view adds up to four. The 60-second scenario is
  already `18,300+4*915=21,960` views, leaving only 2,616 of 24,576 before all
  other closure/epoch/identity/schema dependencies. This is an explanatory
  counting scenario, not a final exact manifest; shared views must be resolved
  once by exact kind/identity/bytes without deleting their associations.
- **Raw bytes:** maximum original provider bodies per packet are
  `131,072+65,536+65,536=262,144` bytes; over 915 packets that is
  `239,861,760` bytes (228.75 MiB), excluding metadata. Base64 alone for the three
  separate bodies is `174,764+87,384+87,384=349,532` bytes per packet or
  `319,821,780` bytes across the trace, before canonical capsule/command/result/
  receipt/closure/readback encoding. These are allowed-body maxima, not measured
  production storage. TOAST/dedup/index/page/WAL allocation may differ.
- **Seal/envelope:** an 8-MiB seal cannot embed the maximum 915 raw-body corpus.
  Future native storage must resolve immutable originals independently through
  a complete bounded manifest, not pretend an all-body witness fits the old
  envelope. The final representation must independently measure complete
  journal/minute/pin/registry encoding under the exact 8-MiB and dependency caps.
  Reference-only validation is still insufficient; actual original resolution
  is required at the native boundary.
- **Packet/process cache:** `915*1MiB=959,447,040` bytes is an engineering
  per-packet-reserve sum, not an RSS or disk allocation proof. Native/reader
  command nesting and four new IDs must be measured before claiming the existing
  1-MiB reserve covers them. The 8-MiB/4,000 packet cache cannot stand in for
  durable warmup storage; original getters/verified durable handoff must permit
  safe same-ID release before that cache fills. No such A3 handoff is implemented.

These gates may require a separately reviewed **forward native capacity and
paged-seal policy**. It must name its own exact schema/hash, immutable page/head
commitments, original resolution and complete control coverage. It cannot
silently widen A1/source/model inputs or claim that ordinary getter paging
changes the existing accepted seal. B1 below sets none of these capacities.

| Ordered native slice | Positive acceptance case | Required negative/uncertain case |
|---|---|---|
| B1 actor/catalog registry | Real two-scope session actors get only their closed capabilities; scoped historical getter returns exact originals. | Caller owner/role/package/epoch spoof; recreated same-name role; transitive dangerous privilege; benign temp sentinel; foreign/absent IDs indistinguishable. |
| B2 allocation and controls | Installation plus epoch/fence operations consume exact complete native positions; seven A1 plus four native IDs allocated once. | Cross-scope/config/raw alias; swapped record with same bytes; ID/tombstone reuse; A→B→A; package rollover; unsupported source-control transition. |
| B3 separate capture retention | Complete or safe incomplete original capture atomically persists eligibility=false without an admission. | Withheld/redacted/partial bytes claimed original; mismatched reservation/raw/capsule; failure transaction claimed to persist diagnostic. |
| B4 raw admission/guards | Independently parsed exact trio, complete prior and genuine current guards produce original result under head position. | Same-block changed price/time; prior/native clock regression; lower carried age; missing prior availability; wrong slot/genesis/type; genuine expiry and rollback with no partial admission/head/receipt. |
| B5 replay and COMMIT | Same exact original returns immutable original facts before current freshness, without append; one recognized standalone transaction commits. | Changed bytes with same ID; two writes per transaction; uncommitted self-read; altered session/catalog/deferred guard; late recognized commit expiry; dropped reply stays unknown. |
| B6 closure concurrency | Delayed original writer versus closure is serialized: exactly one committed admission or permanent closure; exact lost-ack closure getter finds same result. | Nonlocking absence claimed terminal; queued writer succeeds after tombstone; closure borrows capture ID; unknown closure replaced by new ID; closure erases committed admission. |
| B7 original availability | Accepted reader binding retains one exact original observation and later retention time separately; lost ack resolves same IDs/bytes. | Role/hash asserted as true reader delivery; cache restamping; changed interval/body under same ID; failed first-read uncertainty hidden; late availability fills an old minute. |
| B8 full minute/seal mechanism | Native inventory includes interleaved controls/closures/exclusions; exact minute winner/tie; next seal includes prior seal boundary. | Omitted Stop/control/pending write; extra unjournaled original; duplicated old position; wrong head/page; missing minute; late insert reopens seal; fabricated initial warmup. |
| B9 actual long history and bridge | Genuine 915-minute trace plus actual increment, bounded complete dependencies and authenticated source/model join. | Seeded past native clocks, scaled test clock, synthetic labels, missing 900 retained anchors or hash-only model acceptance. |

B1→B2→B3→B4→B5→B6→B7→B8 is ordered; schema/parser/getter codec analysis
can run in parallel after exact field freeze. B7's real reader provenance needs
A3 and B9 needs R3-03B/native-model integration. A short owned PG experiment may
prove B1–B8 mechanisms with explicitly lab-constructed original data; it cannot
claim genuine initial history or actual provider provenance. The long trace is
at least 15h15m plus alignment/sealing, separately opt-in, never default CI.

Every native fixture must be owned/isolated, cached reviewed PostgreSQL image,
no network/host ports/mounts/application secrets, sanitized pinned runtime and
exact cleanup. Record actual package/catalog/source hashes, bytes/row/TOAST/
index/dependency counts, CPU/RSS and parsing/lock/guard/commit/read elapsed tails.
No current tests were run for this document. Railway 0.25 CPU/$20 ceiling and
provider quotas remain later measured gates, not assumed performance evidence.

## 10. Root decisions before final native descriptor or code

1. **D1 journal mapping — root approved:** the one complete sixteen-kind native journal
   and native-position admission ingest, with no claim that A1's five-kind
   supplied seal validates it. Alternative source/control journals would need
   exact cross-head mapping and additional completeness tests before code.
2. **D2 late availability — root approved:** immutable late historical retention while
   preserving permanent minute/current-action ineligibility. Root must freeze
   the actual trusted reader/durable observation handoff separately; lab actor
   authorization does not prove real process clock/delivery.
3. **D3 reconciliation — root approved:** read-only observed resolution plus a separate
   mutating preallocated closure/tombstone. If durable reconciliation writes are
   required, freeze their new original action/event/schema/capacity explicitly.
4. **D4 final receipt construction — root approved DESIGN:** original Command →
   Result → deferred-guard Receipt → Journal/Head; provisional `pending_commit`
   carries no final receipt/hash and only a separate committed getter supplies
   final originals. One-operation/standalone transaction, own-uncommitted-read
   restriction and actual guard/receipt/hash-order correctness remain unproved
   B5 acceptance gates. No native code or receipt exists here.
5. **D5 controls/limits:** freeze fence-duration/renewal bounds, Stop's scoped
   source-only semantics and actual 4,096-entry/packet-reserve capacity. The later
   economic/model control join cannot be implied by source Stop or epoch events.

After these decisions, produce a separate exact canonical native descriptor,
source-bound policy digest and narrow B1/B2 acceptance plan for root/security
review. Do not implement SQL or export new grants from this proposal. Do not
alter A1/source/model/parser bytes, deploy migrations, collect provider data,
activate runtime flags, sign transactions or change Dashboard cloud projects.



## 11. Historical B1 proposal; current narrow freeze separated

The initial actor/catalog-only descriptor below was a 3,444-byte canonical
proposal, SHA-256 `af2496382afd2135832616a3846cbd0d78f09e3eab03f52f1b5076038e7f6ea1`.
It issued no native wire, grant or implemented policy. Root/source/security
review required explicit manifest preimages/separate references, NULL refusal,
TEXT cast limits, membership-edge bounds and fixture bootstrap distinctions.
Its earlier prose is superseded rather than treated as current SQL behavior.

The current minimal B1 proposal and exact v2 descriptor are separately retained
in `R3-03A2-B1-ACTOR-CATALOG-PLAN.md` and
`R3-03A2-B1-ACTOR-CATALOG-POLICY-PROPOSAL.json`. Their independently recorded new
hashes require final peer/root agreement before implementation authorization.
No broader lifecycle authority follows from that actor-only proposal.

```json
{
  "bounds": {
    "catalog_objects": "1024",
    "input_total_bytes": "4096",
    "installed_bindings": "16",
    "output_bytes": "8192",
    "parameter_acl_entries": "64",
    "role_closure_entries": "64"
  },
  "capabilities": [
    "verify_actor",
    "read_scoped_binding"
  ],
  "entrypoints": {
    "get_scoped_binding": {
      "arguments": [
        "owner_id",
        "run_id",
        "market_epoch",
        "requested_binding_id"
      ],
      "return": "BindingLookup"
    },
    "verify_scoped_actor": {
      "arguments": [
        "owner_id",
        "run_id",
        "market_epoch",
        "required_capability"
      ],
      "return": "ActorCatalogEvidence"
    }
  },
  "fields": {
    "ActorCatalogEvidence": [
      "format",
      "actor_catalog_policy_sha256",
      "scope",
      "principal_binding_id",
      "session_user_oid",
      "session_user_name",
      "profile",
      "capability_checked",
      "actor_catalog_package_sha256",
      "installation_manifest_sha256",
      "accepted_catalog_sha256",
      "observed_catalog_sha256",
      "role_closure_sha256",
      "limits"
    ],
    "BindingLookup": [
      "format",
      "actor_catalog_policy_sha256",
      "scope",
      "requested_binding_id",
      "resolution",
      "evidence",
      "limits"
    ],
    "InstalledBinding": [
      "principal_binding_id",
      "session_user_oid",
      "session_user_name",
      "scope",
      "profile",
      "capabilities",
      "installation_manifest_sha256"
    ],
    "Limits": [
      "provider_attested",
      "calibrated_clock",
      "original_identity_registry",
      "epoch_registry",
      "source_freshness",
      "capture_retention",
      "native_source_admission",
      "committed_packet_readback",
      "terminal_resolution",
      "availability_authority",
      "complete_inventory",
      "history_seal",
      "model_native_join",
      "lease_authority",
      "hosted_authority",
      "running_authority",
      "live_trading_authority"
    ],
    "Scope": [
      "owner_id",
      "run_id",
      "market_epoch"
    ]
  },
  "format": "ga-jupiter-actor-catalog-policy-proposal-research-v3-b1-v1",
  "formats": {
    "ActorCatalogEvidence": "ga-jupiter-actor-catalog-evidence-research-v3-b1-v1",
    "BindingLookup": "ga-jupiter-actor-catalog-binding-lookup-research-v3-b1-v1"
  },
  "input_codec": "four-strict-text-scalars-no-json-caller-context",
  "limits": {
    "availability_authority": false,
    "calibrated_clock": false,
    "capture_retention": false,
    "committed_packet_readback": false,
    "complete_inventory": false,
    "epoch_registry": false,
    "history_seal": false,
    "hosted_authority": false,
    "lease_authority": false,
    "live_trading_authority": false,
    "model_native_join": false,
    "native_source_admission": false,
    "original_identity_registry": false,
    "provider_attested": false,
    "running_authority": false,
    "source_freshness": false,
    "terminal_resolution": false
  },
  "namespace": "vn_jupiter_actor_catalog_research_v3",
  "output_codec": "closed-json-evidence-not-original-receipt",
  "profile": "actor-and-catalog-only",
  "profiles": [
    "recorder",
    "reader",
    "sealer",
    "control"
  ],
  "rules": {
    "actor": "actual-session-user-name-and-oid-plus-private-scoped-installer-binding",
    "authority": "no-source-packet-model-runtime-authority",
    "closure": "full-transitive-membership-and-dangerous-effective-privileges-no-truncation",
    "fingerprint": "independent-installer-accepted-definition-ownership-acl-role-session-manifest",
    "foreign_lookup": "same-observed-absence-as-random-unknown-binding",
    "hash_exclusion": "fixed-accepted-digest-value-cells-excluded-no-caller-toggle-or-self-hash",
    "input": "canonical-lowercase-uuid-or-closed-capability-no-null-no-coercion",
    "output": "closed-scalars-no-clock-process-env-secret-raw-provider-data",
    "overflow": "refuse-complete-catalog-or-closure-over-bound",
    "package": "actor-catalog-sql-artifact-only-not-caller-recorder-or-reader-attestation",
    "search_path": "pg_catalog,pg_temp-explicit-qualified-system-and-application-objects",
    "unknown_or_true_limit": "refuse",
    "write_effects": "none-from-two-actor-entrypoints-no-source-registry-or-journal"
  }
}
```
