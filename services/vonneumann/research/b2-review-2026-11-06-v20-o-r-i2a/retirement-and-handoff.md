# Owner-separated retirement and credential handoff

Keep the first proof to the existing one-scope, two-writer terminal case.
I2a seals both the actor grants and all memberships touching the limited issuer.
The earlier retirement case uses the fixture superuser for the two `ALTER ROLE`
statements and the marker update. The next version needs those effects in one
transaction under separated authority. A later version needs a distinct handoff
for a continuing run. [I2a evidence](README.md) · [Issuer proof plan](../b2-review-2026-11-06-v20-o/managed-issuer-compatibility.md).

## Terminal retirement

| Authority | Operation |
| --- | --- |
| Independent anchor owner | Provision a one-use permit for the exact scope, package version, head, original reserved Stop ID and digest, two writer bindings, and expiry. Own the narrow marker-writing function and the marker validation trigger. |
| Independent native owner | Own a helper that locks and verifies the exact scope head and reserved Stop, callable only by the anchor definer. Keep application journal and receipt ownership separate. |
| Limited issuer | Authenticate as the pinned issuer, consume the one-use permit through the marker function, and apply `NOLOGIN` to the two pinned actor roles in the same bounded transaction. |
| Control and independent reader | Retain the exact reserved Stop and exact committed receipt readback under their existing restricted entry points. |

The permit's two roles come from the trusted installed bindings. The issuer
passes the original permit ID and exact scope. Neither definer accepts a role
list, SQL, an arbitrary row filter or a replacement Stop. Pin function owner,
language, body, signature, search path, direct EXECUTE grants and grantors in the
held package. Allow only the exact schema USAGE and direct EXECUTE crossings
from issuer to anchor helper and anchor owner to native helper, with pinned
grantors. Resolve identifiers in trusted schemas and revoke default PUBLIC
EXECUTE in the creation transaction. The anchor and native owners stay `NOLOGIN`
and outside the issuer's `ADMIN`, `SET` and inheritance graph. The issuer remains
trusted over actor credentials. It can replace an actor password without a
visible change to the catalog fields in the seal. Prefer a dedicated limited
issuer for this package and a restricted, reviewed transaction boundary for its
operator. [PostgreSQL definer rules](https://www.postgresql.org/docs/17/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY) · [Creator role authority](https://www.postgresql.org/docs/17/role-attributes.html).

1. Lock the package exclusively, then the two ordered writer bindings and the
   exact scope head. Verify actual issuer session identity, trusted permit,
   installed actor name/OID and creator tuples, complete held catalog, current
   head and adequate remaining control and reader lifetime using database time.
   A concurrent writer holding the package lock causes a bounded refusal.
2. In the same transaction, stage only the exact terminal marker and consume
   the permit. As the issuer, change the two verified roles to `NOLOGIN`.
   Check both actual role identities and login bits, unchanged head and retained
   scope lock, and full held catalog after projecting only those two bits. The
   marker's deferred check must recognize the reviewed standalone literal
   `COMMIT` and refuse incomplete retirement. Any failure rolls back the permit,
   marker and both role changes together.
3. Resolve an uncertain reply by the original permit and exact independently
   read committed state. A matching committed marker and both exact retired
   roles lead to the same reserved Stop. An unresolved or inconsistent state
   closes the path for reconciliation. Bind a later getter to its own credential
   and the exact historical writer or Stop identity.

`SET CONSTRAINTS ... IMMEDIATE` can fire a pending check early. Exercise it
before the role changes and after both correct changes. An early check that
succeeds after both changes could be followed by role DDL that restores `LOGIN`
before commit. The commit-form guard must refuse either early path. Keep the
sanctioned operator limited to the fixed transaction and require the actor and
reader guards to fail closed on unexpected catalog drift. Keep a separate
administrative response for out-of-band changes. [PostgreSQL deferred constraint timing](https://www.postgresql.org/docs/17/sql-set-constraints.html).

The first native cases should observe a competing writer, rollback after the
first role change, early constraint forcing, and successful retirement with
exact original recovery and Stop. Include direct marker or role attempts by a
worker, changed head or grantor, and cross-scope refusal. Run the authorized path
with a genuine limited issuer and actual control and reader logins. Verify the
committed marker, role flags and economic rows through independent readback.

## Continuing-run handoff

Use a separately versioned, one-shot actor-generation transition. Creating a
replacement actor with the same limited issuer adds a creator grant incident to
that issuer. That changes I2a's held membership seal even before the new role
gets an application grant. Issuing replacement roles in the background under
the live package would therefore block current actors. [Issuer membership correction](candidate-v20-o-r-i-to-v20-o-r-i2.patch).

Prefer a serialized generation transition under the same package, binding and
scope locks. Precompute the authorized role names, issuance IDs, grant
relationships, custody and timing policy. Under the locks, prove the old head
and reconcile pending originals, create the next actors, and capture their real
assigned OIDs. Independently verify the exact predicted catalog delta and new
package digest, then atomically retire old writers and make the new binding
generation and fence authoritative. Publish new login material after independent
commit readback. A failed or unknown transaction closes ordinary admission
pending exact reconciliation. Keep the first proof to one active scope. I2a's
seal includes issuer memberships across its schema. Multi-scope use needs
issuer-wide serialization or a separately reviewed scoped seal.

Preserve the old bindings and committed receipts under their original hashes.
Carry forward the market cursor, eligible-minute history, model and RNG state,
cash and holdings, and pending Stop and original IDs. Fresh writer authority
comes from the committed new generation and fence. Verify late old writers at
literal COMMIT, same-handoff retry, grant drift, permission failure between role
changes, and a read across the handoff boundary. Prove next-command equivalence
and measure the resulting data gap before counting continuous minutes. The
terminal marker stays the fallback for the exact supported Stop. A continuing
handoff, its credential lifetime, and its hosted installer require separate
native proof and review.
