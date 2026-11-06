# B2 V12: independent Stop reserve and getter-size worksheet

Static review only, 2026-11-05. No candidate source was imported or executed,
no tests or databases/Docker/provider operations ran, no credential was read,
and no repository file changed. The October private native directory is absent
in this session; reviewed inputs are the repository's verified review-only
archive and immutable acceptance record. This is a conditional structural bound,
not an admitted maximum witness, a proposed policy edit, or native/hosted authority.

Source bindings: `services/vonneumann/research/b2-review-2026-10-21/`
`candidate-v11b.patch` SHA-256
`27ed0cfc08ad4ff2e26e2dd4d25f3a255c512f4dc2e27c01c15f85606ac7e9a9`;
`services/vonneumann/research/b2-review-2026-10-21-v12/`
`candidate-forward.patch` SHA-256
`5d12701dff4f4cddbac02765785e3c530d082aa5335851dbe4f66c55923f8f50`.
Both patch digests were independently reread and verified. V12 manifest pins
SQL `4e1e55b7c565982067195fd8d818ac6dfef5dadbfae21dbc2ba35a96dd4771c0`
and unchanged descriptor-file `0a1c8663f4f6cbf9b299cab11fcdd00a379dbe3ca3493b706ddafca9b75c0f1a`.
Additional read inputs: `B2-NATIVE-ACCEPTANCE-2026-10-21-V12.md`,
`WORKER-CAPACITY-RETENTION-RESEARCH-2026-10-17.md`, and
`services/vonneumann/B2-ONE-SHOT-ALLOCATION-CONTROL-PROPOSAL-2026-10-17-V3.md`.

## Decision

The original 76,533 logical / 144,142 staging-inclusive encoded byte reserve
can be reconstructed exactly. V12's one-byte Accounting change does outgrow
that exact **loose historical envelope**, but that alone does not prove an
admitted Stop can exhaust the reserve. With the closed installation and prior
control command grammars, the same retained reserve has independently derived
margins of 855 logical and 1,727 staging-inclusive bytes, even allowing a
19-digit resulting/retained fence revision in the worksheet. Do not raise
capacity or change an issued policy digest just to repair a conservative bound.
First make the typed shape assumptions executable and review actual staging,
authority and reachable-state proofs. No full B2 acceptance follows.

## Counting rule and exact typed-width assumptions

Compact canonical UTF-8 object bytes = two braces, `n-1` commas, and for each
field its quoted key, one colon and encoded value. An array has two brackets
and `n-1` commas. Every string field below is counted with quotes. UUID36 is
38 encoded bytes; digest64 is 66; `null` is 4; `false` is 5; `true` is 4;
a 19-digit decimal string is 21 and a 20-digit xid8 string is 22. The three-UUID
scope object is 153 bytes. The closed eight-digest Policies object is 706.
All string values used for these symbolic widths are fixed grammars, not
fabricated/truncated accepted original bytes.

For a canonical compact JSON wire of raw length L, embedding as `original_wire`
contributes `2 + L + E`, where E counts additional escapes for embedded quotes
and backslashes. In the V12 canonical UTF-8 representation there are no raw
control bytes inside a canonical original; UTF-8 is retained. Therefore
`E <= L` is a safe loose upper bound. This counts the escaping at the layer
where a wire is embedded. A retained Result's wire cap already includes its
embedded pins; embedding that Result in the reply requires a second count at
that outer layer. No HTTP/pretty JSON/additional JSON-string wrapper is included.

The reviewed Stop grammar has two body fields, `expected_control_sha256` and
`expected_mode`, null expected fence fields and null previous seal. The longest
mode is `paused` and a nonnull prior control SHA is 64 hex characters. Native
sequence 16 is the maximum resulting position and prior position is at most 15;
both have two digits. That gives **731** bytes for future Stop C (748 if a
19-digit sequence is considered, matching the V3 proposal). V12's actual first
path instead uses one-digit prior position and null control SHA: **668** bytes.

The installation Command has the same fixed envelope, one-digit initial head,
null fence fields, and body `{installation_id,scope,policies,
catalog_manifest_sha256,actor_manifest_sha256,genesis_registry_sha256}`. With
153-byte scope and 706-byte eight-digest Policies, it is **1,827** bytes. The
frozen install anchor/Command comparisons close these fields; no padding is
admitted. Use 2,048 only when reproducing the earlier envelope.

Prior Pause/Resume uses a closed two-field control body and the same head
shape. Its longest kind is `source_resume`; allow the longest legal mode text,
nonnull control digest, the full UUID fence and 19-digit fence revision and
head sequence. Even this conservative grammar gives **801** bytes. The
previous-head Command is a different dependency that can be a packet original;
keep its full 16,384-byte cap. Do not replace its bound with 801.

| Seven distinct direct Stop pins | Historical raw cap | Refined raw upper |
| --- | ---: | ---: |
| Native genesis input | 8,192 | 8,192 |
| Installation Command | 2,048 | 1,827 |
| Active epoch registration | 2,048 | 2,048 |
| Terminal allocation | 1,024 | 1,024 |
| Previous head Command | 16,384 | 16,384 |
| Prior control Command | 1,024 | 801 |
| Old active fence record | 1,024 | 1,024 |

Each pin includes `semantic_kind`, `original_id`, `wire_sha256`, decimal
`wire_bytes`, and the escaped `original_wire`. The Result pays all seven such
copies plus its own envelope/body/limits. A dependency-association row adds the
scope/action identity, kind/id/digest/byte count and one-digit ordinal; it does
not add another body wire. Its two logical key arrays each have 149 bytes plus
the kind text length. The original's three keys count 224 bytes, and the other
journal/scope keys are counted independently. The six limits flags remain false.

## Independent reserve arithmetic

This worksheet adds the selected canonical row/metadata/key components directly.
It does not call `_cost`, use a `_cost` result as an oracle or fit observed
catalog data. The final and pending operation metadata each include the complete
116-byte final-function observation. The completed Receipt includes it again,
plus the separate 116-byte COMMIT-processing observation. The pending insert
has null receipt SHA, receipt byte count `"0"` and `finalized:false`; finalization
writes the completed original. Scope/head/accounting and dependency row metadata
are separate components. Existing genesis/fence/etc. pins do not allocate new
identity or domain rows during Stop.

| Component | Refined upper bytes |
| --- | ---: |
| Stop Command | 731 |
| Stop Result with seven escaped pins | 64,993 |
| Receipt | 1,365 |
| Journal | 478 |
| ScopeHead, conservative 19-digit fence revision | 542 |
| Accounting, wider false and all fixed cap widths | 217 |
| Final original metadata | 853 |
| Journal metadata | 343 |
| Scope metadata | 288 |
| Seven dependency-association metadata rows | 2,939 |
| Declared final logical key arrays | 2,929 |
| **Total final logical encoded charge** | **75,678** |
| Additional pending INSERT: C + R + 789-byte pending metadata + 224 key bytes | **66,737** |
| **Total staging-inclusive encoded charge** | **142,415** |

Cross-check: with 2,048 install and 1,024 prior-control caps instead, seven
escaped pins add 889 Result bytes (888 body bytes and one wire-byte digit),
and one association metadata digit adds another byte. Thus this conservative
19-digit, false-Boolean loose envelope is 76,568 logical and 144,194 combined.
Replacing the 19-digit Result/head fence revisions with two digits removes
17 bytes each from the final total and 17 from the pending Result. Replacing
Accounting false with true removes another byte. That reconstructs exactly
**76,533 final + 67,609 pending = 144,142** before V12. Keeping V12 false and
the same loose assumptions gives **76,534 + 67,609 = 144,143**, as expected.
No nested component's byte-count field crosses a decimal-width boundary here.

The candidate's `_cost` currently uses a two-digit `ScopeHead.fence_revision`
upper value. Before enabling new kinds, prove every fresh operation increments
fence revision by at most one, from zero at installation, or replace the upper
representation under reviewed source/policy. Also re-audit active-fence head
storage: the V12 `_cost` head envelope uses `active_fence_id:null` for the two
implemented kinds, whereas an ordinary future fence operation retains a UUID
(34 encoded bytes wider). The Stop head itself clears it. That is a concrete
ordinary-future-envelope blocker, independent of the Stop reserve's headroom.
Similarly keep last-source/admission/availability/seal fields null and ingest
sequence zero throughout B2, or derive a new bound for the next phase.

The seven-pin discrete vector remains one position, nine retained rows, seven
new dependency associations, zero new identities/domain facts, ten logical
writes/twenty keys, and eleven row/23 key touches including the pending original.
`_budget` must preserve each dimension under the same scope lock, with the
existing-accounting state, ordinary increment and a dominating Stop vector.
Verify the deferred guard sees the same staged original/facts, immutable past
stage accounting and exact original. No change to owner/right/rollback/refusal
rules follows from this worksheet. None of these units measures PostgreSQL heap,
index, TOAST, WAL, lock time, resident memory or physical DML size.

## Getter budget and reachable witnesses

A coarse safe scalar+LF envelope uses 16 total C/R/Receipt trios (target own
trio plus up to 15 ancestors) at independent caps 16,384/131,072/4,096, plus
independent domain caps: 8,192 genesis; 1,024 terminal; three 2,048 acquisition;
three 2,048 reader; sixteen 1,024 fence; one 4,096 reservation. That is
**2,466,816 raw bytes**. Escape at most twice that length, and add at most
16,786 bytes for top-level fixed fields, 70 full pin headers/array separators,
empty embedded-wire quotes and exactly one LF. Longest pin kind and six-digit
wire-length metadata cover every permitted kind. Conservative scalar+LF bound:
**4,950,418**, below 8,388,608 by **3,438,190**. This is conditional on exact
canonical UTF-8 output and the per-wire/position/domain guards, without any
extra wrappers. It neither proves reachable maximum size nor bounds intermediate
JSONB allocations, repeated catalog work, transaction time or physical storage.

Seventy is a safe sum of independent caps, not a business-state target. Under
the current descriptor's domain transitions, installation creates three domain
facts, each later ordinary operation at most one, and Stop creates none. At
Stop position k, the closure is at most `3*(k-1) + 3+(k-2) = 4*k-2`, hence at
most 62 when k=16. A nonterminal target is at most position 15, with at most
`4*k-1 <= 59` pins. Keep the existing cap; do not pad/synthesize 70 accepted
business pins or confuse that cap with the 7 direct associations.

Smallest useful native sequence after the required transitions exist:

1. Install (paused, empty, genesis/epoch/terminal facts and reserved Stop UUID).
2. Acquire a real recorder-owned fence in paused mode with its own actor and
   approved real clock; no artificial hold/fixture SQL edits.
3. Resume using the separately authenticated control and server-resolved F_scope.
4. Renew through the recorder's F_recorder. This makes previous head Command
   distinct from both installation and prior control; the renewed fence is the
   current exact old-fence dependency for Stop.
5. Quiesce ordinary intake, observe the current head, submit the original reserved
   Stop, literal COMMIT, independently read back, exact replay with zero writes.
   The seven direct pins are the three fixed facts, installation C, renewal C,
   Resume C and renewed fence. The getter should have 12 ancestor pins + 5 domain
   facts = 17 closure pins, with exact bytes and complete closure resolution.

For an admitted position-bound witness, use twelve renewals in total after
Resume: 15 ordinary operations. Attempt one further ordinary operation at the
would-be position16; require reserve refusal and complete no-write snapshots.
The original Stop then commits at16 and gets 45 ancestor pins + 16 domain facts
=61. The prior control remains distinct. A paused seven-pin variant additionally
pauses then renews before Stop. Actual trusted clock/expiry and existing bounds
must hold; do not extend deadlines or use arbitrary sleeps to force an outcome.

The missing acquire, Resume and renew paths require explicit future semantics
in submit, commit guard and independent getter/retained facts, scoped actor
proofs, lock/current-head/fence/version and post-lock/COMMIT reauthorization,
expiry, distinct IDs and exact replay. Current V12's getters only accept the
installation/Stop semantics, and Stop assumes paused/no active fence. Its
first-slice auth checks the present actor, not an arbitrary claim that every
possible trusted bootstrap/unused binding has a closed maximal shape. Preserve
independently pinned four-binding construction; reject padding and confirm all
anchor/header/type/cap assumptions before extending claims to new actors.

Sequence the next review: (1) statically bind closed widths and reserve
inequalities, including wider ordinary head and staged metadata; (2) preserve
V12 original19+5 and review/add the three required transitions in a separate
closed forward laboratory candidate, with exact getter/commit semantics;
(3) execute the minimal legal seven-pin witness, then admitted position
below/exact/over proof and terminal lost-ACK reconciliation under the existing
owned budget; (4) add remaining kinds with their own capacity/authority proofs.
Exercise nominal byte/counter predicate boundaries using a separately labelled
symbolic arithmetic contract where actual reachable states cannot hit those
limits; never write artificial counters or padded trusted rows to advertise
an accepted maximum. Production NOLOGIN broker ownership, complete installed
catalog/managed privileges, composition/CI, durable recovery/retention and
hosted gates remain separate. Reserved capacity cannot guarantee Stop liveness
under stale head, missing actor, lock/expiry failures or an uncertain COMMIT;
only the exact original reconciliation is authorized in those cases.
