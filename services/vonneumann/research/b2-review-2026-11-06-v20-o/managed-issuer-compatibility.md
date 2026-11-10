# B2 managed issuer compatibility contract

The scoped hosted observation found 40 retained legacy actors with exactly one
incoming creator membership, `ADMIN=true`, `SET=false`, `INHERIT=false`, and
zero login-enabled actors. This supports the shape of a fixture hypothesis.
It supplies neither B2 provisioning authority nor a hosted B2 receipt. The
existing v5 package and its retained original history are predecessor evidence.

## Authority and sealed facts

| Role | Authority in the proposed first slice |
| --- | --- |
| Independently verified bootstrap | Creates/seals the two B2 owners and exact object ACLs. Separate from the actor issuer and any worker login. |
| Anchor owner | NOLOGIN. Owns the package and binding registry and fixed lock-only broker. Only its reviewed operator path may provision sealed inputs or record a terminal marker. |
| Native owner | NOLOGIN. Owns native schema, tables and functions. Anchor access remains exact schema USAGE, SELECT on the two anchor tables and EXECUTE on the fixed broker. |
| Actor issuer | Actual PostgreSQL 17 non-superuser CREATEROLE session with a pinned name and OID. Creates fresh actors and administers their exact retained identities. Holds neither owner role nor an owner ADMIN edge. |
| Installer, recorder, control, reader | Four distinct actual SCRAM login identities bound to one database, owner/run/market epoch, installation, issuance and canonical capability. Direct exact entry-point grants. Give the independent reader getter-only access. No owner or peer role paths, table DML, role grant options or schema CREATE. |

PostgreSQL 17 creates an ADMIN-only edge automatically for a new role made
by a non-superuser CREATEROLE issuer when `createrole_self_grant=''`. Existing
v5 `issue.sql:26–49` validates the actor's incoming edge as `(roleid=actor_oid,
member=postgres_oid,grantor=10,ADMIN=true,INHERIT=false,SET=false)` and a
separate outgoing edge to its v5 capability template. `grantor` is the bootstrap
authority OID, while `member` is the actual limited creator OID. The existing
installer fixture renames the OID-10 bootstrap principal and creates a new
non-superuser `postgres` login with its own OID. Pin both role OIDs and names
from the verified target catalog and assert the complete grant tuple and row
identity. The hosted aggregate alone does not supply individual OIDs, current
role attributes or complete grantor provenance. Export only boolean/count
comparisons and sealed artifact digests.

Use direct B2 RPC ACLs for this slice. Each actor has exactly one incoming
creator row and zero outgoing membership rows. A `vn_economic` or `vn_relay`
SET-only membership is a predecessor capability and is a B2 negative case.
If future B2 ACLs use a template, it needs its own NOLOGIN role, exact grantor
and one bounded outgoing `ADMIN=false,INHERIT=false,SET=true` tuple. Owner
roles and templates are different trust boundaries. An ADMIN-only owner edge
is unsafe even when SET is false. The legacy bootstrap shows how an ADMIN
holder can grant itself a second SET edge. Prove the actor issuer cannot
GRANT itself either owner, ALTER either owner or use an inherited owner path.

## Minimal forward source design

1. Use the exact composed V20-O private source as the starting point. Preserve
   the held constructor, prior scoped wire identities and original receipt
   semantics. Add a distinct managed-actor package/profile and source seal.
   Keep the existing no-membership laboratory profile for regressions. Derive
   the new edge/role expectations from trusted installation inputs and an
   independent catalog verifier. Never accept the first observed catalog as
   the expected shape, learn new edges on an RPC or reuse the old v5 digest.
2. Replace the blanket actor membership rejection in `_auth` only for the new
   profile. Check all rows touching each relevant actor and demand the one
   exact incoming tuple and no outgoing rows. Check the actor's real name/OID,
   role flags, connection limit, empty role settings, immutable issuance and
   scope/capabilities, and finite matching `rolvaliduntil`. Keep the complete
   original catalog seal over role/grant rows, ACLs, owners, definitions and
   constructor evidence. Record issuer/grantor role identity in its own narrow
   catalog section so checking their names and OIDs does not implicitly make
   every unrelated issuer membership part of this package. Reject missing,
   extra, duplicate, changed-flag, changed-grantor or re-created edges. Only
   the already reviewed historical getter/terminal LOGIN projections remain
   available, and those still require full structural equality.
3. Require `system_user = 'scram-sha-256:' || session_user` and non-null
   `inet_client_addr()` for the actual caller. Verify TLS server identity and
   mandatory channel binding in the pinned direct client. For Resume, verify
   the actual control's authenticated session, plus the locked recorder's
   identity and live authority. The recorder is a dependency, not the control
   connection's `system_user`. Leave poolers for a separate identity test.
4. Keep issuance ID, role name/OID, canonical profile and scope, issued/not-
   before/write/recovery times, and `rolvaliduntil` fixed for each binding.
   The existing shared issuer-binding ID identifies the issuer authority, not
   each actor's issuance ID. Use the B2 anchor broker's retained package and
   binding locks. Compare `clock_timestamp()` after lock acquisition and again
   on recognized COMMIT. Write/replay uses a write deadline. The independent
   getter uses its own finite deadline and immutable historical writer identity,
   without requiring that writer's old credential to remain usable. Fresh
   logins after `VALID UNTIL` and held-session operations after the application
   deadline must both fail. No caller timestamp, client clock advance, or role
   catalog time change is an expiry witness. Prove enough control and reader
   lifetime remains for reserved Stop plus receipt recovery when a writer ends.
5. Reuse the predecessor's operational pattern, not its `vn_access.bindings`
   or pair-specific SQL. Generate unique names, issuance IDs and synthetic
   SCRAM verifiers. Create bounded NOLOGIN actor roles as the limited issuer,
   independently verify exact identities/edges/ACLs, enable LOGIN and publish
   only with complete trusted bindings and the independently verified K. The
   first lab may use separated owner steps while the new package is closed
   and credentials remain unpublished. Capture the final seal with the reviewed
   LOGIN bits only after independent verification, before publishing any
   admitting package row. Partial failure must leave no admitted actors and
   exact readback determines the next owned step. Never give the
   issuer permanent owner SET or ADMIN authority to join the steps.

The existing SECURITY INVOKER operator uses a bounded single parameterized
statement, scoped identity/release and safe logging checks. `issue` is for the
closed reviewed v5 release. `issue_quiescent` allows an open v5 release only
with no active run, live old credentials or existing binding for the requested
fresh run. The v5 offline same-run rotation test issues a fresh pair, retires the
old pair and recovers one original. It is not an available active hosted rotation
procedure. B2 V20-O seals the installed actor manifest, grants and role catalog.
Adding a replacement login/binding or changing its OID/ACL/deadline changes that
seal. A real in-scope rotation requires a separate versioned authorization
handoff under package/binding locks, exact old-ID reconciliation and preserved
historical writer evidence. Do not overwrite an old binding, reuse a name or
extend `VALID UNTIL`. Until that contract exists, stop the bounded run while
control/reader remain live, reconcile the original Stop, then retire; the V20-O
marker supports only its exact position-three, two-writer terminal witness.

A B2 terminal batch can reuse v5 revocation's public-data-only receipt, bounded
lock deadline, ordered row locking and post-DDL role-name/OID validation. It
must use B2's package→binding→scope lock order and tie two exact NOLOGIN changes
to one terminal marker transaction. v5 `revoke` updates its own registry and
retains roles/originals; it cannot authorize B2 Stop. Loss of either SQL reply
requires exact identity/state readback. A role recreated under the old name or
partial or unrecognized state is a refusal, not permission for another Stop.

V20-O's fixture administrator can write the marker and change roles in one
transaction because it is superuser. Under separated authority, review one
new narrow anchor-owned definer for the exact marker transition. Only the
pinned actual issuer can call it. It has no DDL or general row-update surface.
It takes the package and ordered actor locks, then uses an independently
sealed native-owner function to verify and lock the exact scope head. Keep
the existing actor broker lock-only. Stage the one canonical marker and run
the two fixed role DDL statements as the limited issuer in the same bounded
transaction. An immutable/deferred marker check must reject COMMIT unless
both exact name/OID/creator tuples now have NOLOGIN and the pinned head,
package and independent catalog comparison still match. These extra helper
ACLs and declarations need their own held-source verification. An issuer
can still administer its own actor roles outside this supported procedure.
Unexpected unmarked DDL invalidates the package and has no Stop/readback
continuity guarantee. Administrative access controls and a hosted inverse
are separate from the PostgreSQL proof.

## One isolated native proof sequence

Use an owned PG17.6 network-none fixture with synthetic SCRAM and TLS entirely
inside container loopback. Reuse the prior real limited-issuer bootstrap
pattern (`tests/postgres/installer_fixture.py:22–43`), the certificate/pgpass
and channel-binding settings in `session_auth_fixture.py:38–109`, and the
bounded B2 `StepSession` for literal COMMIT. Its socket-trust path stays for
bootstrap or explicit negative checks. The existing v5 native helper performs
`SET ROLE vn_economic/vn_relay` on connect, so add only a bounded direct B2 actor
variant for this candidate. A genuinely authenticated limited role issues the
actors. Bootstrap superuser is reserved for fixture setup or labeled synthetic
fault injection. No provider, external network, hosted token or host mounts.

1. **Baseline incompatibility and privilege separation.** Give a literal
   V20-O actor the genuine creator edge by having the limited issuer create
   it. The existing fixture seal rejects the row. To isolate `_auth`, use
   test-only independently checked actor-edge expectations before calculating
   the scoped catalog digest, and leave the exact V20-O SQL unchanged.
   Its `_auth` rejects the otherwise exact actor. The new profile then
   accepts the exact direct-SCRAM actors for Install, Acquire, Resume and exact
   getter; record redacted database/role/grantor equality, one incoming and zero
   outgoing actor rows. Assert issuer and each actor cannot assume or administer
   either owner, reader cannot submit, and a socket-trust or sibling-scope
   actor cannot borrow the binding. Owner/grant/table snapshots are unchanged.
2. **Membership faults.** In separate disposable fault transactions, add one
   incoming inert edge with ADMIN/SET/INHERIT all false, one outgoing SET-only
   template edge, and change one expected creator flag. Also remove the expected
   edge or substitute a same-flags edge with another valid grantor if the fixture
   can establish that state. Prove the exact catalog witness is present before
   checking refusal. Admin-only duplicate and wrong grantor must fail even when
   effective SET rights are unchanged. Auth and exact getter refuse unexplained
   drift, without economic rows or replacement receipts. Roll back each fault
   and prove the original receipt bytes recover unchanged.
3. **Real credential time.** Capture authoritative issuance/deadline receipts.
   Stage a valid actor operation before the real database write deadline. Use
   a trusted barrier and sampled DB wall clock to send literal COMMIT after
   write expiry and before login/recovery expiry. Confirm refusal, identical
   committed rows, continued connection in the recovery interval, and access
   to a previously committed exact original only as the independent reader.
   Hold the old writer session beyond its `VALID UNTIL` and prove both its next
   RPC and a fresh password login fail. Record wall-clock inequalities with
   margin and a bounded timeout. Keep fence expiry beyond the observed window
   or use a non-fence operation so the credential check is the causal failure.
4. **Real limited-issuer retirement.** At the reviewed position-three head,
   pin the exact reserved Stop. A staged actor transaction blocks the scoped
   retirement with no partial marker or role mutation. After it releases, the
   same limited issuer disables precisely the two pinned actor logins using the
   owner-separated reviewed path. Force failure after one DDL and separately
   attempt COMMIT after one DDL. Both checks must restore the absent marker
   and both original login states. On success prove held/fresh writer denial, exact two original
   readbacks by the independent reader, one original Stop by control and exact
   Stop receipt readback. A competing grant, OID replacement or unrelated
   retiree refuses. State explicitly which authority performed each SQL step.

The first source-forward review can stop after the exact-edge and fault cases.
That proves the narrow compatibility correction. Credential-clock coverage,
controlled retirement, role handoff, managed bootstrap feasibility and hosted
acceptance then remain separate gates. No source, database or test was executed
when preparing this packet.
