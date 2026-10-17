# B2 one-shot allocation/control contract proposal, revision3 — 2026-10-17

**Bounded allocator research experiment only. This is not the paper-MVP Stop mechanism and reserved capacity does not guarantee native Stop liveness. Design only; not a frozen policy or execution authority.** No repository/proposal edit, SQL, Docker, test, provider/hosted request or credential access occurred. This resolves the smallest reachable allocator/control slice from worksheet94dbf6c9. B1 `05fa535`, A1/source/model `65f9236` and the sixteen-kind lifecycle proposal retain their exact original meanings. No old research flag is flipped and no old header/digest is reinterpreted. These are continued offline design choices, not a new human-approval gate.

## 1. Version and narrow scope

Propose descriptor format `ga-jupiter-b2-allocation-policy-proposal-research-v3-v1`, with a new source-bound digest after review. Proposed wire literals are:

- Command/Result/Receipt: `ga-jupiter-b2-allocation-command-research-v3-v1`, `ga-jupiter-b2-allocation-result-research-v3-v1`, `ga-jupiter-b2-allocation-receipt-research-v3-v1`.
- Query/reply/observation: `ga-jupiter-b2-original-query-research-v3-v1`, `ga-jupiter-b2-original-reply-research-v3-v1`, `ga-jupiter-b2-query-observation-research-v3-v1`.
- Genesis registry/terminal allocation: `ga-jupiter-b2-genesis-registry-research-v3-v1`, `ga-jupiter-b2-terminal-allocation-research-v3-v1`.

The complete proposed sixteen-kind vocabulary remains an immutable dependency. B2 enables exactly installation, epoch_registration, epoch_rollover, reader_epoch_registration, fence_acquire/renew/release, source_pause/resume/stop and packet_reservation. The other five kinds (capture_retention, source_admission, availability_retention, terminal_closure, inventory_seal) refuse with no writes. No provider I/O is authorized even when the allocator mode is named open. There is no accepted admission or packet completion in B2.

All common fields/types are the full proposal's closed sets: canonical UTF8 JSON, duplicate/unknown/type refusal, UUID36/digest64, signed64-bounded unsigned decimal-string counters. Command has exactly:

```text
{format,native_policy_sha256,scope,action_id,action_kind,expected_head,
 expected_fence_id,expected_fence_revision,body}
```

`Scope`, `Policies`, `HeadPin`, eleven `PacketIds` and each of the eleven enabled Command body sets are unchanged in meaning. B2 requires `HeadPin.previous_seal_sha256=null` because it cannot create seals. Each fresh action needs its exact current head. Its original replay is checked first under current scoped read authorization, not after fresh mode/head/fence checks. Result/Receipt keep the proposal's exact fields and result_body union for those kinds, under the new literal formats. All six Limits remain false; B1's seventeen false evidence flags remain untouched. No caller supplies a native sequence, final clock or success receipt.

B1 exposes only verify_actor/read_scoped_binding. A separate reviewed B2 package/catalog/capability manifest is indispensable; the old profile labels and recomputed K cannot grant these operations. Registry/DDL/ACL/source acceptance must be independent, as for B1; no self-issued actor or source manifest becomes gold.

## 2. Closed original identity mapping

Propose **one explicit forward identity_role addition**, `native_operation_id`. Retain every existing identity role, hierarchical scope association and packet role. Result/Receipt/Journal are views of the same original action, not new identities. Non-packet query correlation below is another read-only view, not an allocation-role alias.

| Kind | action_id role | Independently distinct object identities born by the event |
|---|---|---|
| installation | native_operation_id | installation_id and every genuinely new closed genesis identity; terminal Stop control_action_id is preallocated here |
| epoch_registration | native_operation_id | registration_id and unseen acquisition_epoch |
| epoch_rollover | native_operation_id | none; references the original accepted successor registration |
| reader_epoch_registration | native_operation_id | registration_id and unseen reader_process_epoch |
| fence_acquire | native_operation_id | new fence_id |
| fence_renew / fence_release | native_operation_id | none; original fence_id stays allocated |
| source_pause / source_resume | control_action_id | none beyond this new operation identity |
| source_stop | control_action_id | none at execution: must consume the installation's preallocated terminal Stop ID |
| packet_reservation | reservation_id | exactly the eleven different PacketIds; reservation_id already is its action_id |

All operation IDs differ from their installation/registration/fence/epoch IDs, all configuration and packet IDs, and other action IDs. A new registration_id differs from its origin UUID. Control action IDs cannot borrow the terminal Stop ID. The full future policy's capture/admission/availability/closure action aliases and seal_id alias are preserved but disabled. RPC integers remain separate correlations; own raw-record alias remains the sole allowed raw-reference association. Unused prepared packet/closure/query IDs remain used forever.

Closed proposed new records:

```text
IdentitySpec = {original_id,identity_role,association}
InitialAcquisitionSpec = {registration_id,acquisition_epoch,predecessor_epoch,
                          recorder_principal_binding_id,reader_principal_binding_id,
                          issuer_binding_id,recorder_package_sha256,
                          reader_package_sha256,policies,endpoint_bindings}
GenesisRegistry = {format,scope,identity_specs,initial_acquisition_spec,
                   terminal_stop_action_id}
TerminalAllocation = {format,scope,installation_id,stop_action_id,
                      allocation_command_sha256,first_native_sequence}
```

`identity_specs` is the exact independently installed genesis input list, not completed IdentityRecords or a caller-chosen extension. It contains no current Command/Result/Receipt digest, assigned position or native time. InitialAcquisitionSpec.predecessor_epoch is null. The spec has no server-assigned ordinal or original_command_sha256; its scope is the enclosing fixed GenesisRegistry.scope. The terminal spec is only the distinct preallocated terminal_stop_action_id, not a completed TerminalAllocation. Ordinary immutable package/policy/actor references are independently held inputs, not hashes of the current installation output.

To avoid a nullable active-epoch reinterpretation, recommend installation pin exactly one initial acquisition specification, then enable its completed registration under the installation event. Its immutable registration and origin IDs are distinct. Initial source mode is paused, active fence null; later registration alone never activates a successor. Reader origins may first register through their authenticated reader event with predecessor null. This explicit genesis construction is a forward detail; it cannot be inferred from the old proposal's default values.

The acyclic construction is: independently held canonical genesis **inputs G** → hash(G) in exact installation **Command C** → hash(C) and locked assigned position → completed immutable IdentityRecords/EpochRegistration/TerminalAllocation → Result → deferred Receipt → Journal/Head. The server completes each new IdentityRecord with original_allocation_sha256=hash(C) and its actual first position (preserving already legitimate existing scope associations); completes the initial EpochRegistration with its assigned ordinal and original_command_sha256=hash(C); and creates TerminalAllocation with allocation_command_sha256=hash(C) and first_native_sequence equal to that installation position. These completed fields are absent from G, not mutable cells excluded while hashing a completed object. Nothing in C or G hashes a future completed fact that points back to C. Exact typed derivation and every input/result association must be independently checked, rather than trusting a digest alone.

For complete resolved dependencies, the new B2 OriginalPin.semantic_kind union explicitly adds `native_genesis_input` and `native_terminal_allocation`; it retains `native_epoch_registration` for the completed epoch fact. This is another declared forward extension, not substitution under an old semantic kind. TerminalAllocation is immutable; whether Stop is consumed is derived from its exact original operation. Its row and ID are installed and journaled by installation, never a hidden control write.

These are the **only two new forward identity-view exceptions**; both require exact semantic kind + original_id + held scope + installed native package/policy + canonical original bytes/hash/byte count, not just a matching UUID:

| New OriginalPin.semantic_kind | Exact original_id / identity role | Mandatory association |
|---|---|---|
| native_genesis_input | This installation's installation_id / installation_id | Exact G bytes/hash named by the same original installation C.body.genesis_registry_sha256; C.body.installation_id equals the pin ID, G.scope equals C.scope and the private installed scope, and G's policy/package references match that same accepted installation. G has no separately allocated own UUID. |
| native_terminal_allocation | Its reserved stop_action_id / control_action_id | Exact completed TerminalAllocation bytes/hash; its stop_action_id equals G.terminal_stop_action_id and the pin ID, its installation_id equals that same installation C.body.installation_id, its allocation_command_sha256 equals hash(C), and first_native_sequence equals C's actual assigned installation position; scope/package and original identity allocation associations match that installation. |

Neither exception permits another configuration/control UUID, another installation's G, a foreign scope/package or an arbitrary derived object with equal bytes. The existing installation-ID and reserved Stop-ID registry records remain distinct and are not reallocated under the view kinds. Input/allocation views grant **no** Command/Result/Receipt authority, actor capability or proof of a Stop execution: only the separately committed original source_stop operation under that same reserved ID can prove Stop. A getter for source_stop with no such operation remains observed_absent_unknown even when its TerminalAllocation fact is present. Reinterpreting either view as native_command/native_result/native_receipt or another original format refuses.

## 3. Controls, fences and legal transitions

`F_recorder`: the actual recorder session's own installed holder binding, accepted package and enabled origin, current fence ID/revision, genuine unexpired hold. Used by reserve/renew and recorder fence management.

`F_scope`: the scope's installed recorder binding/current enabled epoch/current unexpired fence, resolved server-side while the **actual control session** is authenticated separately. Used by Resume. Control receives no fence_manage capability and does not impersonate the recorder. Supplied holder fields cannot substitute for either binding.

| Action | Exact fresh transition / preconditions | Effect |
|---|---|---|
| Pause | open→paused; actual control, H, expected_mode=open and exact prior-control Command SHA | Preserve outstanding reservation and existing fence facts/revision; quote-free. Fresh paused→paused or stopped Pause refuses. |
| Resume | paused→open; actual control, H, F_scope, current enabled epoch, no unresolved reservation; exact prior-control Command SHA | Mode only; no source/model/economic freshness or new hold. Fresh open→open/stopped→open refuses. |
| Stop | open or paused→stopped; actual control, H, original reserved Stop ID, exact prior-control Command SHA; no live fence/quote needed | Preserve all allocations/originals; clear active fence and advance fence revision transactionally, retaining immutable fence versions. Fresh Stop when stopped refuses; exact original replay remains zero-write. |
| Acquire | paused/open; actual recorder, H/current enabled own epoch; no active head hold and no unresolved reservation | New fence ID, server-assigned revision/actual UTC; duration must match separately frozen finite policy. |
| Renew | paused/open; actual recorder, H+F_recorder, exact held revision | New original version/operation; old expiry must still hold at the required final/commit guards. Never resurrect. |
| Release | paused/open; actual recorder, H, exact own current enabled-epoch fence/revision | **Permit expired release**: it removes authority, grants none. Clear hold and advance revision; retain original facts. Replaced/foreign/retired/noncurrent fence refuses. |
| Rollover | no unresolved reservation; actual control, H and installer-approved unseen same-package successor | Activate successor, invalidate old hold, pause; no implicit Resume or new economic lease. |

Expiry alone does not mutate the head or create a journal row. Reacquire requires an explicitly cleared hold; no replacement of an expired-but-still-held ID. If the original recorder cannot release it, permitted control/rollover/Stop paths remain separate; B2 offers no forced ownership transfer. Fence acquire/renew/release after stopped refuse. Pause retaining a fence is minimal: mode already bars collection, and Resume separately tests genuine current expiry. Prior-control links mean **original Command SHA**, with null only before the first control. This command-only meaning avoids Result/Receipt self-cycles and must be explicit in the new descriptor.

Exact fresh head/revision mismatches always refuse. A prepared command is never edited to a later head after uncertain submission. Getter evidence may support a separately new permitted operation only after the earlier original outcome is actually resolved; it never authorizes same-byte resend or automatic retry.

## 4. Non-packet originals and D4 are B2 prerequisites

The old OriginalQuery target_kind contains only five packet kinds, so it is insufficient for B2 control/fence/install lost ACKs. Propose the new B2 query:

```text
Query = {format,native_policy_sha256,scope,target_kind,target_id,
         expected_original_command_sha256,correlation}
correlation = {kind,id}
```

`target_kind` is exactly the eleven enabled kinds. For packet_reservation, correlation.kind is `packet_reconcile_id`; its id is the original prepared PacketIds.reconcile_id. A found original must resolve that association. For every non-packet kind correlation.kind is `original_action_id` and id must equal target_id. This is a read-only correlation view of that original action, not a second registered identity role; queries allocate nothing. A missing original cannot prove the caller's prepared correlation was ever allocated. Foreign existing and absent IDs produce the same safe absent result.

Observation has exactly `{format,native_policy_sha256,scope,target_kind,target_id,correlation,resolution,observed_head,original_operation_pin,limits}`. Resolution is original_committed or observed_absent_unknown; original pin is nonnull only for the former. B2 never emits terminal_closed. Reply has the full proposal's exact committed Command/Result/Receipt/dependency/observed-head set with the new format; metadata does not rewrite originals. Query/reply bounds require a separately frozen B2 size/closure policy, not automatic reuse/enlargement of B1's8192-byte scalar cap.

**Required for any successful B2—not deferred wholesale to B5:** one new operation per transaction; Command→Result→deferred-finalization Receipt→Journal/Head with no self-hash; atomic complete assembly; function return explicitly provisional/pending_commit with no final receipt/hash; actual supported transaction/COMMIT protocol; exact replay; separate committed getter. A same-transaction caller must not read its own provisional writes as committed. Retain server-assigned top-level writer xid8 privately as engine transaction-origin metadata only, never as the immutable operation UUID, epoch, archived/cross-restore identity or principal. Bind the getter to the same immutable scope/kind/action UUID/exact Command and installed package/complete Result+Receipt, and reject a getter in that writer transaction; require the approved independent primary read and one consistent complete assembly. `pg_xact_status` is supplemental only, never durable retained-original authority or proof of absence/abort. Do not assemble a receipt from unrelated snapshots.

Required fence freshness checks use actual clock_timestamp observations after locks/work and recognized COMMIT processing. Stop/release require no live-fence freshness; dependent acquire/renew/reserve/Resume use their declared guard. Receipt's final-function and commit-processing observations are separate. Actual transaction-level durability/trigger/session/catalog conditions must be reviewed/tested; a function-local synchronous_commit that reverts before COMMIT proves nothing. No hard final-visible/WAL-time freshness bound is claimed. Full source receipt5s/source30s/future2s checks, process clocks and trusted reader delivery remain downstream B3/B4/B5/B7/A3 work.

## 5. Bounded reachable terminal graph

For allocation-only B2, define pending as the one committed reservation with no installed resolution path. It never becomes completed, closed or recyclable. Initial state is paused/empty.

```text
paused/empty --F_scope+Resume--> open/empty
open/empty --F_recorder+Reserve11--> open/pending
open/{empty,pending} --Pause--> paused/{empty,pending}
{open,paused}/{empty,pending} --reserved Stop--> stopped/{empty,pending}
stopped/{empty,pending} --scoped original get/replay--> same state (read-only)
```

Reader/epoch/fence maintenance is ordinary accounted work, not part of the terminal path. Pending blocks new reserve, rollover and Resume. Exact historical replays write nothing. Any observer/ACK uncertainty allows only original reconciliation; observed_absent_unknown remains unknown and supplies no fresh action. No B2 closure capability, tombstone, seal, diagnostic retention, reader availability, row deletion or silent slot release exists. The source can remain stopped with unresolved evidence indefinitely. Recycling requires an explicitly installed reservation-abandonment subset of B6, then its own versioned reserve/race proof; this proposal does not implement it.

Thus the **maximum additional committed terminal path from any nonstopped reachable state is one Stop event**, and from stopped it is zero. This is a one-shot safety result, not full B6 terminal resolution/liveness. Every ordinary mutation preserves the reserved Stop capacity under the same locks. Reserve Stop's action UUID at installation; do not wait until exhaustion to allocate it. Read-only reconciliation has zero journal writes but its reply/CPU availability still needs its own bounded acceptance. Reserve one additional head/journal counter increment and one fence-revision increment for Stop within the existing signed64 range; ordinary work must refuse before it consumes either counter headroom.

The one-Stop allowance is a capacity bound, not unconditional liveness under stale-head races. Construct that one original Stop only after ordinary intake/owned producers are quiescent and the current head is observed. If a competing allowed writer wins or the outcome is uncertain, preserve the exact attempted Stop ID/bytes and close local activity to read-only reconciliation; do not claim native stopped, manufacture another Stop ID or rebase that command. If no committed Stop can be proved, the native mode remains unproved and the experiment can remain indefinitely locally closed/unresolved. A lock-held head-preparation protocol or bounded fresh-action retry policy would be a separate explicit extension, not an assumption of this one-shot slice.

## 6. Derived quantities versus unresolved measurements

For that one Stop: one new OriginalOperation, one JournalEntry, one scope-head mutation; zero new packet/epoch/fence identities, no provider bodies, no capture/tombstone/availability/seal record. The already allocated Stop ID is consumed, not allocated again. Physical staging/guard/accounting rows and MVCC/TOAST/WAL are schema/measurement decisions, not these logical counts.

The exact bounded Command grammar yields a derived maximum Stop Command of **748 UTF8 bytes** for this proposed format: UUID36/digest64, maximum19-digit head sequence, null previous_seal/fence fields,64-byte prior-control SHA, longest legal source Stop mode `paused`. The scalar-shaped maximum is a length calculation, not an issued wire or accepted byte cap; it says nothing about full Reply or transitive dependencies. Empty/genesis digest cases are shorter.

Stop also requires immutable installed package/actor/scope/terminal-allocation facts, actual current epoch/head and prior-control original associations, plus the former fence fact if referenced. The precise dependency encoding, original-closure traversal, preexisting referenced bytes versus newly duplicated bytes, Result/Receipt/deferred staging and complete getter size must be frozen before deriving a total byte reserve. Do not claim a constant total while a recursively embedded prior-control history remains unbounded. Prefer shared immutable originals plus exact direct associations and separately bounded complete resolution; no hash-only acceptance or lost association. If complete reply growth cannot fit the unchanged chosen bound, ordinary work must stop before that state or use a separately reviewed forward representation.

No accepted storage/row/dependency limit, hold duration, renewal cadence, new per-seal bound or physical budget is selected here. Existing4096 supplied/per-seal inputs remain distinct from lifetime completeness. D5 for the **whole** source lifecycle stays open; only this proposed one-shot terminal action count is closed. Native source/model/control coupling, archive/prune/cache release, genuine915-minute warmup and hosting remain closed.

## 7. Minimum exact acceptance after source freeze

Prove separate B2 actor/catalog grant installation, identity matrix and all11 packet UUIDs; initial genesis/first registration; legal mode table including expired release; recorder-vs-control F separation; one pending slot/no bypass; below/exact/over ordinary-plus-Stop reserve; current/retired origins; hold replacement/expiry races; Stop without fence; one-op/deferred receipt/getter barriers; provisional-then-ROLLBACK; same-writer getter refusal; concurrent getter before/after COMMIT; same-ID lost ACK/changed bytes; and full mutable-table no-write snapshots for every refused path. Keep actual deadlines/fence constants pending review, genuine clocks and independent exact cleanup. These are native tests to build later, not results of this document.

## Upstream consistency and source binding

Additive forward changes are unavoidable: the non-packet operation identity role, non-packet original query/correlation union and explicit new genesis/terminal dependency-view kinds. The old closed role/query unions cannot encode these needs without a new descriptor/format. The proposed genesis active-epoch and reserved Stop allocation must likewise be explicit installed manifest inputs. None requires altering issued A1/B1/source/model bytes or changing the sixteen event meanings. Returning committed success without the D4 subset would contradict the existing design and is not an acceptable partial B2 implementation.

Source context: worksheet SHA94dbf6c9162f7b06fd806a77bf878b767d6c9736c41917c735185aab5eeaf252 contains the exact ten upstream hashes; frozen lifecycle proposal SHA629bb304beddfdf84a73a5df2afe0ab56798f349ce4ae73c1efc63722443d554. Root's additional native commit/clock note is 3654 bytes, SHA06cef8cd41b37385505ea32656967f4000fff7cb2f5d4273efccad9a0eb3d7bd. All those originals are unchanged; this new proposal supersedes neither their evidence nor unresolved claims.

## Revision lineage and clock-note cross-check

The preserved earlier private draft is B2-ONE-SHOT-ALLOCATION-CONTROL-PROPOSAL-2026-10-17.md, SHA587fbdfe285c14450e81fb2043da8f5c2f4368b47b90817f432985dffdf8fd4e. It is **not a valid frozen preimage design**: its GenesisRegistry nested completed EpochRegistration.original_command_sha256 and TerminalAllocation.allocation_command_sha256 while installation Command itself hashed GenesisRegistry, forming Command→genesis→derived Command-SHA→Command. Its unspecified identity-list shape could similarly admit completed position/Command fields. This revision uses only closed IdentitySpec/InitialAcquisitionSpec/Stop-ID inputs in G and derives complete immutable facts afterward. It preserves the old draft unchanged, creates no issued wire, uses no self-hash exclusions, and changes no existing policy/header. The748-byte Stop Command length is unchanged.

The root clock note06cef8cd was independently checked against its five official PostgreSQL17 links. No concrete error was found: [transaction-management CALL/DO restrictions](https://www.postgresql.org/docs/17/plpgsql-transactions.html), [READ COMMITTED own writes/snapshots and nontransactional sequences](https://www.postgresql.org/docs/17/transaction-iso.html), [top-level xid8 and recent status/prepared/NULL limits](https://www.postgresql.org/docs/17/functions-info.html#FUNCTIONS-TXID-SNAPSHOT), [commit-time synchronous_commit selection](https://www.postgresql.org/docs/17/wal-async-commit.html), and [actual versus transaction/command wall-clock functions](https://www.postgresql.org/docs/17/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT). Preserve its conditional wording about a function-local setting **that reverts**; do not assert that every SET LOCAL executed inside an ordinary function automatically reverts at function return. Public-document checks are not native execution, durability acceptance, settings changes or a production capability.

## Revision3 lineage

The preserved revision2 file is B2-ONE-SHOT-ALLOCATION-CONTROL-PROPOSAL-2026-10-17-V2.md, SHA95725f5d24e4c4b4b1e6cb63ffcd75036979c4693c844936e2430dbcf9a48d24. This revision adds only the explicit two OriginalPin existing-ID view associations and their exact installation/Stop/spec/scope/package/hash requirements, addressing peer review of the cycle-corrected draft. It allocates no extra ID, changes no old format, selects no new resource/fence constant and provides no runtime freeze or implementation. Both earlier drafts remain unchanged.
