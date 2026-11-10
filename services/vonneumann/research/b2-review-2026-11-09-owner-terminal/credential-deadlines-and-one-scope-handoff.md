# B2 independent deadlines and one-scope recorder handoff

Private implementation design. Starting point is the exact direct-SCRAM
archive. Its focused native receipt passed on PG 17.6 and used one role
deadline for login and runtime. It proved refusal at the recognized literal
COMMIT guard. Use the retained inheritance results on the changed SQL when
they are independently accepted. Treat owner-separated terminal retirement as
a separate dependency before composing a handoff.

| Held input | SHA-256 |
| --- | --- |
| SCRAM archive manifest | `58347ac5e0d30828a05fe51428bd8e914264e6c6f696921e1a5316097d6116bb` |
| SCRAM held SQL | `f3b069e005afdc672fa8b15dfd75360e876cd0e5fc0d98180fa2ac1f940b0942` |
| SCRAM archive native receipt file | `a2278c40e548c4b33e20347cca8d401a89b7638117dd87fc773c2b3e5efa1929` |
| I2a retirement-and-handoff design | `4f0182346f19fc7fab00024d4952fc0a0bd7427ce62a62c8d0fa2dd141cc7c43` |

## First change: independent deadlines

Add an explicit SCRAM-deadline package format and capability manifest format.
Keep the accepted trust and SCRAM-v1 profiles and method bodies for regressions.
Use the existing immutable canonical `actor_bindings.binding_wire` plus its
exact manifest entry. Add the following keys only for the new format:

| Key | Exact meaning |
| --- | --- |
| `issuance_id` | New canonical UUID, distinct per actor, scope and generation. The shared issuer binding remains separate. |
| `credential_generation` | Canonical string `"1"` initially. Only the successor recorder gets `"2"` in the subsequent slice. |
| `issued_at_us`, `not_before_us` | Canonical bounded decimal UTC epoch microseconds from the authoritative issuance transaction. |
| `write_until_us` | Exclusive cutoff for installer, recorder and control. JSON null on the independent reader. |
| `read_until_us` | Exclusive cutoff for the independent reader. JSON null on the writers. |
| `login_until_us` | Finite exact bound equal to that role's catalog `rolvaliduntil`; checked on held sessions as well. |

Require one non-null application cutoff, exact by capability, and
`issued <= not_before < cutoff <= login_until`, with a held laboratory
maximum of five minutes for this fixture profile. Pick stricter separated
times in the actual expiry tests. Sample database time once for issuer input,
using the source's exact numeric epoch-microsecond conversion. Compare
`rolvaliduntil` by the same conversion and require its exact finite value.
Parse only canonical positive bounded integers after type/shape checks. Bind
the new bytes to the pinned name/OID, database, scope, package, issuer and exact
creator edge. In the new manifest verifier require one exact typed entry per
initial actor, unique binding and issuance IDs, and equality to every initial
binding row. Preserve the 2,048-byte per-binding and aggregate package limits
and measure the new admitted bytes. The first candidate adds no table or role
DDL beyond the existing finite issuance, whose `VALID UNTIL` is already exact.
It requires no TTL extension or writer permission changes.

1. Add one private authorization-use parameter to `_auth`, set only by
   held callers. The public getter uses `getter`; submit's precheck, exact
   submit replay, internal prior-original assembly and recognized COMMIT use
   `writer`. The independent reader can invoke only the public getter under
   its read window. Existing writer getters in the new profile still require
   the writer's live window. Historical writer evidence is checked as
   immutable identity, scoped binding and catalog lineage. The historical
   writer's clock need not remain live. Continue authenticating the actual
   control session for Resume and check the dependent recorder's write
   window after the existing broker takes both bindings.
2. Reuse `_lock_inputs` and the fresh post-lock `_auth`. Sample
   `clock_timestamp()` for authorization, with inclusive not-before and
   exclusive cutoff, and return the validated private deadline context to
   held callers. Add a pure private check that compares that validated context
   to the existing `_clock` observation before provisional response and to
   the late `_commit_guard` observation immediately before final writes.
   Use `42501` and distinct fixed messages for application write cutoff,
   reader cutoff and actual credential expiry. A cutoff detected after DML
   rolls back the operation. Keep the existing earlier COMMIT reauthorization
   and original fence-clock proof. Both observations are guard points.
3. Public `get_original` stays STABLE on a single parent snapshot. Sample
   the wall clock again at the return boundary for either exact response or
   safe observed absence. This can be a scalar check using the already
   validated private context. Keep nested catalog/history reads STABLE and
   scope the lookup before examining a target. No caller clock or fallback
   profile. A writer submitting a duplicate after its write cutoff fails
   before replay. A matching committed original is recovered by the separately
   live reader. Missing, wrong-scope, wrong-kind, mismatched digest and own
   provisional cases retain their existing boundaries.
4. Owner-separated terminal recording must use actual control write and
   independent reader read windows, plus their exact login bounds, at the
   trusted marker and deferred COMMIT guards. Keeping the old role-only
   five-second check after introducing earlier application deadlines would
   admit an unusable Stop. Before composing the branches, prove a supported
   terminal Stop and exact recovery fit the configured fixture margin.

## Second change: one recorder handoff in one scope

Limit the first slice to one installed scope, exact finalized Install1,
Acquire2 and open Resume3, one live revision-1 fence, unused reserved Stop,
one preallocated successor Renew4, one new recorder and one permanent
handoff. Control, reader and installer keep their existing identities. The
installer has no post-Install mutation in this slice. Refuse a second
handoff, other scope, existing terminal marker, later head, expired fence,
unresolved command, different permit, insufficient control/reader/recorder
headroom, or any unexpected role/catalog delta. The operator reconciles and
quiesces its own in-flight originals before requesting the handoff. The
package lock independently fences admitted database transactions.

Preserve `package_inputs.package_wire`, original actor manifest, genesis,
Install and every existing C/Result/Receipt, identity and journal row. Keep
the native package digest for this newly installed handoff-capable package.
The effective catalog seal advances separately. The SQL cannot safely swap
the original package rows: `_reply` currently compares all historical
receipts to one current K and checks the Install against the original actor
manifest. Renew and its verifier currently require the genesis recorder and
the prior fence holder to be the same identity.

### Table and authority changes

Add one anchor-owned private `credential_handoff` row per scope with these
columns. Use the existing package PK for its scope FK. Retain the old binding
and insert the new recorder in the existing actor-binding registry with its
own exact name/OID and canonical binding.

```text
scope_wire         text PRIMARY KEY, FK -> package_inputs(scope_wire)
handoff_id         uuid NOT NULL UNIQUE
permit_wire        text NOT NULL, <=8192 UTF-8 bytes
stage_xid          xid8 NULL
handoff_wire       text NULL, <=8192 UTF-8 bytes
CHECK(handoff_wire IS NULL OR stage_xid IS NOT NULL)
```

A private anchor operator preloads one immutable exact permit. The permit
contains the scope, installation, package/policy, K1, exact head sequence and
hash, old binding identity/hash, prior fence ID/revision/digest/expiry, new
role name and binding/issuance UUIDs, issued/not-before/write/login times,
pinned issuer identity, exact role/ACL profile, pinned Renew4 action ID and
command digest, preallocated Stop ID and permit expiry. Command wires
remain canonical; pending or submitted Stop4 cannot be rebased after a
competing command. Keep verifier/password material outside the permit and
receipt. Bound scope and every scalar. The completed marker adds only exact
observed successor name/OID and binding digest, assigned creator tuple,
independently checked K2, database handoff time and linkage to the permit
digest. Keep both wires immutable once committed.

Reuse the two NOLOGIN owners and actual limited SCRAM issuer. Give issuer
only direct EXECUTE on fixed anchor stage/finish, anchor owner direct
EXECUTE on fixed native validation/grant helper, and native owner SELECT
on exact anchor inputs and handoff marker. No worker table privileges,
issuer owner membership, broad ALTER/GRANT authority or maker role reuse.
The native owner is the exact direct grantor of schema USAGE and submit and
getter EXECUTE to the one allowed replacement. Accept no caller SQL, grant
list or unbound identifier. Resolve the role under the locked exact permit
and name/OID before quoting it as one identifier. Verify the resulting
grantor and non-grantable direct ACLs. Reuse the anchor package and binding
locks and native scope validation pattern from the owner-separated terminal
slice. The worker lock broker remains lock-only.

1. **Stage.** Use one bounded issuer transaction with explicit settings.
   Stage validates the actual issuer session and permit, then takes package
   exclusive NOWAIT, ordered old binding locks, the permit row and native
   scope head lock. Follow that order everywhere. Verify full K1, no
   replacement role/binding, exact Resume3 journal and original fence,
   unconsumed Stop reserve and no competing committed operation. Use actual
   DB time after locking and require permit, issuer, old live fence and the
   necessary actor windows to cover the fixed fixture margins. Save the
   actual xid in the permit row. A deferred constraint trigger queued when
   the previously null xid becomes set ensures COMMIT cannot skip finish.
2. **Issue and finish.** In that same transaction the limited issuer creates
   precisely the allowed fresh NOLOGIN SCRAM actor using its verified PG17
   creator profile. The narrow native-owner helper grants the three exact
   ACLs. The issuer disables the exact old recorder and enables the exact
   new recorder. Finish verifies the same actual xid/session, complete
   unchanged scope/head/fence, exact role/creator/grant shapes and clock,
   inserts the new immutable binding and stores the marker.
3. **Verify K2.** Verify the new role attributes, actual assigned role and
   membership OIDs, one creator tuple, zero outgoing memberships and exact
   ACL atoms and dependencies independently of the final digest. To compare
   against held K1, invert only the verified new role/membership, exact
   three direct ACL atoms and their exact scoped `pg_shdepend` additions,
   and restore the one old recorder's actual false login bit to true in
   the comparison object. Preserve existing array order and every other
   catalog value. Refuse extra dependency or ACL shape rather than adopting
   it. Only then hash unmodified actual K2 for the marker. After publication
   compare against raw K2, with no new generic catalog projections.
4. **COMMIT and custody.** The anchor-owned deferred trigger rereads the
   staged and finalized row in the same transaction. It requires the
   recognized standalone literal COMMIT, exact xid/issuer, retained scope
   conditions, exact K2 proof and fresh clock/margins. Early constraints,
   omission of finish, a later role/ACL change, stale head or any inconsistent
   DCL refuse. Role changes, successor binding, permit consumption and
   marker roll back together. Reconcile an unknown response in a distinct
   read transaction through the trusted fixture owner, by original permit
   and exact marker/new binding and role states. Publish the new password to
   the scoped worker only after positive reconciliation. An uncertain or
   partial state keeps ordinary admission closed pending reconciliation.
   Hosted operator readback and custody need a separate reviewed path.

### Authorization, lineage and Stop

- Read the committed marker in the same authorization snapshot. Validate
  its exact canonical permit relationship and raw K2 before treating the
  old recorder as retired and new recorder as current. Submit and COMMIT
  require active writer binding and its own clock. The independent reader
  retains its own window and recovers generation-1 originals using the
  frozen historical manifest. Unexplained LOGIN restoration, membership,
  ACL, role, package or row drift refuses. Do not reuse a terminal marker
  to cover generation drift.
- Keep the original fence record and head byte-identical at handoff.
  Its old holder is historical. Fresh fence authority is the exact
  committed handoff overlay for that head, fence ID, revision, digest and
  successor. Only the new recorder can use that overlay, and only on the
  permitted Renew4, while the old hold remains live. The ordinary deferred
  Renew guard validates this same one-time exception. Require its issue
  time at or after both the prior commit observation and handoff observation,
  and its COMMIT before both old expiry and the new writer deadline. Renew4
  produces the usual next immutable fence version with the new recorder
  binding. Subsequent supported Renew uses that recorded holder and the
  already committed generation, without another overlay. This does not
  reopen an expired hold.
- In `_reply`, choose expected receipt K by sequence relative to the
  exact immutable handoff boundary, then reconstruct the historical
  generation-specific writer and fence checks. Generation 1 still uses the
  original manifest and K1. Later receipts use K2. Keep the same original
  package digest and head ancestry, existing canonical wire formats and
  domain pins. An old reply's embedded original bytes and dependency set
  remain equal. Its separate observed-head field follows its statement
  snapshot. No extra public recovery privilege or historical write path.
- Stop stays available under the live control write window. Immediately
  after handoff, the exact original Stop4 at the unchanged head works
  without requiring the successor or live fence. If the permitted Renew4
  has conclusively committed and no Stop was previously submitted or is
  unresolved, construct the first Stop at position 5 with the same
  preallocated Stop ID and its new exact expected head. A prepared Stop4
  must remain exact if retried after a definitive rollback at the unchanged
  head. If a submitted Stop4 loses to another writer or its outcome is
  unknown, reconcile the original. Never change its bytes to turn it into
  Stop5. Do not claim the position-three terminal-retirement procedure also
  works after a completed handoff. That is a separate expansion.
- The two retained admin rows and one-time DCL consume resources despite
  leaving the native position unchanged. Deduct a separate fixed admin
  envelope from every ordinary and Stop admission cap for the handoff
  profile at initial installation. Candidate ceilings to prove against an
  independent UTF-8/key ledger before sealing are 32,768 retained bytes,
  65,536 staged bytes, two retained rows, four logical keys, four row writes
  and eight staged key touches, with zero native positions or domain pins.
  Calculate exact row metadata, escaped wire bytes and both rows' keys.
  Count permit insert, stage update, marker update and successor insert.
  Preserve the existing original scope accounting and Stop reserve. Keep
  PostgreSQL role/ACL catalog storage and physical DB costs separate.

## Native acceptance in order

1. Reconstruct the pinned SCRAM source, confirm the inherited 44 result on
   it, and keep old profiles for full regressions. Forward-test the
   deadline format with genuine verify-full/TCP/SCRAM and channel binding,
   trusted issuance, and independent actual reader. Verify strict
   negative manifest/deadline/ACL checks with a disposable owner.
2. With at least the prior accepted clock margins, stage an exact Acquire
   before the writer cutoff and while fence remains live, verify an
   independent getter sees no committed original, then literal COMMIT
   after the write cutoff but before the role `VALID UNTIL` and fence
   expiry. Expect the new precise write refusal, no committed row changes,
   another successful SCRAM login during the credential-only interval, and
   failed submit/replay/own recovery there. Verify independent original
   Install readback and Acquire absence. Separately cross the real reader
   cutoff with its held and fresh sessions before login cutoff, then cross
   actual login expiry. Both missing and present reads refuse after the
   application read cutoff. Exercise caller and dependent recorder expiry
   on Resume plus exact original Stop while its separate windows remain
   live. Use bounded DB-clock waits, real timestamps and actual failure
   receipts. Do not create expiry by editing role/catalog/time state.
3. Independently accept the owner-separated terminal proof and rerun its
   original Stop/recovery, real limited issuer, early constraints and atomic
   rollback against the deadline composition. Add exact changed constructor
   and function/ACL grantor gold for handoff.
4. On a dedicated one-scope fixture, hold a genuine recorder Renew with
   the shared package lock. Prove the issuer gets the bounded conflict and
   no role, marker, binding or application row changes. Roll back that
   operation for the successful branch. Separately let it commit first and
   show stale handoff refusal. Force incomplete DCL, late grant drift,
   failure between role mutations, and early constraint checks before and
   after finish. Confirm original K1, absence of successor artifacts and
   retained exact committed originals after each rollback.
5. Complete one handoff while old hold still lives. Pause an independent
   getter in one parent statement across COMMIT and show old snapshot
   consistency, then prove a fresh K2 reader gets byte-identical original
   records. Suppress issuer acknowledgement, resolve the original marker
   once, then release the successor secret. Prove held and fresh old writer
   denial, a fresh successor positive, same-ID retry does not mint another
   actor, wrong scope and exact fence/command/authority faults refuse.
6. Split terminal branches in fresh fixtures. In one, use exact Stop4
   after handoff without renewing. In another, commit successor Renew4,
   prove same old-fence boundary and next-version lineage, then build the
   first Stop5. Verify exact historical readback and independent ledger
   with seven direct Stop5 pins and 17 closure pins. Check both rows'
   admin charge and unchanged native accounting prior to successor
   execution, then each economic operation and Stop reserve. Rehearse
   deadline/expiry and interruption branches without counting unmeasured
   continuity. Run exact test IDs under the existing 240-second owned
   controller partitions. Native role-DDL/ACL deltas and PostgreSQL clock
   behavior need actual receipts before any acceptance.

## Managed Supabase and selected Railway transport gates

- The November 6 exact closed Railway deployment proved Dashboard IPv6 and
  supplied-CA hostname TLS to the direct PostgreSQL endpoint before
  StartupMessage. A prior v5 pair has real selected-host SCRAM evidence.
  The direct B2 application actors and separated issuer still require a
  scoped closed rehearsal on the exact project, database and selected
  Railway replica. Pin `db.fxpxsciltakyypunglzr.supabase.co:5432`, direct IPv6,
  `verify-full`, approved CA and minimum TLS, required SCRAM and channel
  binding, actual `session_user`/`system_user`/role OID, UTF-8/UTC, primary
  READ COMMITTED and independent client-side TLS evidence. A management SQL
  response or TLS-only probe cannot prove the worker's role/session shape.
- Verify the actual managed issuer role attributes, creator grantor and
  membership tuple, safe role DCL, and bootstrap authority to install
  separate owners without retaining owner ADMIN or SET. Rehearse complete
  scoped K construction with actual managed default ACLs, dependencies,
  parameter ACLs, extensions and event triggers. Existing management/v5
  receipts do not resolve these B2 constraints. Avoid role/default-ACL/CA
  changes or broad grants to force fixture parity.
- Reuse the prior bounded direct libpq transport pattern, with a separately
  reviewed B2 route mapping exact submit/get. The current adapter targets
  the v5 capability pair and performs SET ROLE. B2 needs direct
  actor-specific sessions, no SET ROLE, explicit separate literal COMMIT
  and proven idle completion. Validate current-query form with the actual
  selected psycopg/libpq path, application bytes and deadlines. No use of
  PostgREST, management SQL or a pooler for the native commit proof. Any
  later pooler would need distinct backend identity, SCRAM/channel
  binding, single-transaction semantics and queue/timeout acceptance.
- Verify private per-generation credential custody, redacted operator
  errors/logs, issuer/reader separation, lost-commit reconciliation and
  correct cleanup. Measure aggregate connection slots and simultaneous
  issuer/control/reader/successor handshakes, role/catalog lock and COMMIT
  tails under actual worker CPU limits, plus max data gap, stop/recovery
  margins, interruption/overlap and next-command equivalence. Rehearse the
  reviewed hosted inverse while closed. Active market cursor, eligible
  history, model/RNG, cash and holdings continuity require a separate
  adopted-run acceptance. This laboratory slice has no economic mutation
  to serve as that proof.

Prepared by static source and archived receipt review. This is a design
artifact. No candidate code, repository edit, credential use, native
execution or remote change is part of it.
