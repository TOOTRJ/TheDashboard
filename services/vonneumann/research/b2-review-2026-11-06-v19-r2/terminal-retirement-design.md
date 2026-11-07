# V20 bounded terminal retirement design

V19 already accepts an independent exact getter after the selected
original's one pinned writer loses LOGIN. It keeps full catalog equality
for write paths. The result is an operational dead end under wider
retirement. Two LOGIN removals invalidate the V19 reader fallback, and
even the first invalidates the remaining control actor's reserved Stop.
The frozen V19-R2 test isolates that gap before changing SQL.

## Smallest proposed repair

Start with the one admitted open state after Install, Acquire and Resume at
position 3. Permit one owner-authorized synthetic retirement batch for
the scope's exact installed installer and recorder. Neither is the
still-live independently installed control or reader. The batch binds
the original reserved open Stop at position 4. Keep later positions and
other transition kinds out of this new authority until reviewed.

Add one optional bounded retirement wire to the already trusted, scoped
package input row. Keep existing package/genesis/actor-manifest bytes
and the independent catalog digest in their existing fields. The new
wire is canonical UTF-8 with a closed schema and a 4 KiB maximum.
It contains its format, exact scope, original native package and catalog
digests, exact reserved Stop UUID and original Command digest, and exactly
two ordered writer binding tuples. A tuple pins the installed binding ID,
real PostgreSQL role name and OID, and the canonical installed binding
digest. Writer selection is independently derived from the held installer
profile and genesis recorder binding. There is no caller-supplied list or
wildcard. A nullable field keeps the eight tables and existing grants.
Update held constructor, loader, fixture pins and catalog evidence for
the changed table. V20 needs its own independently accepted catalog and
source seal before the first Install in a fresh laboratory. V19's sealed
package and original digest stay immutable. The subsequent V20 retirement
must preserve the exact V20 package/genesis/actor-manifest bytes and V20
expected digest established at installation. Charge the one bounded
trusted anchor update separately from actor operations and Stop.

The trusted lab owner selects the known fixture scope and approved
original Stop while the catalog is still intact. In a single transaction
it locks the package row exclusively before the writer binding rows and
scope head, verifies position 3, exact head and package plus an absent
marker, and performs only the two exact LOGIN removals and one exact
marker write. This ordering serializes with the broker's package SHARE
lock and prevents a trusted handoff from racing past an in-flight actor
transaction. A lock failure aborts the batch. The worker cannot add or
modify the marker or change roles. The initial lab can model this as an
explicit owned admin fixture transaction. No callable administrative
endpoint is needed in the worker package.

## Authorization modes and ordering

1. **Marker absent.** Preserve all accepted V19 behavior, including the
   one selected writer getter recovery. Raw NOLOGIN drift without a
   marker still cannot authorize Stop or multiwriter readback.
2. **Marker present, exact terminal command.** Require the actual
   installed live control binding and only the exact original reserved
   Stop Command whose digest is in the marker. Check scope, ID, kind,
   exact current locked head, prior original Resume, fence association
   and unchanged reserve. No live recorder or installer capability is
   needed. Verify both pinned retired roles currently have NOLOGIN.
   Transiently restore only their two login bits in the full catalog and
   compare the original independent digest. Revalidate the same marker,
   actual live control, exact terminal operation and complete catalog
   comparison at recognized COMMIT under the retained package row lock.
   An out-of-band LOGIN restoration still refuses while the marker exists.
3. **Marker present, independent getter.** Authenticate the live exact
   installed reader in the usual stable snapshot. Only a found finalized
   same-scope, same-kind, exact-digest original by one of the two retired
   writers, or the exact committed Stop in the marker, may use the same
   two-bit full-catalog comparison. Unknown, wrong digest, wrong kind,
   foreign, nonreader and writer-provisional cases remain strict. Verify
   the entire relevant prefix and return the original bytes and receipt.
4. **Marker present, every other mutation or submit replay.** Refuse.
   Do this even if someone restores both login bits and the live
   catalog matches its original digest. Recovery uses the separate
   committed getter. Never rebase or submit a replacement Stop.

The current _reply reauthenticates historical dependencies used by submit
and COMMIT. A repair that changes only public getter or top-level Stop
auth still fails in this internal path. Thread a private checked
terminal context to _reply for the authorized Stop's exact previous
original only. Bind the context to the same scope, exact approved Stop
digest and real live control actor. Its source is the broker-locked
transaction and _auth, never wire data. All normal submit paths continue
to call strict _reply. Keep the public signatures and existing role/ACL
allowlists. Independently verify that held C/R/T and catalog bytes cannot
be substituted by this context.

Only those two role login bits are projected in memory. Name, OID,
capabilities, valid_until, role flags, memberships, ACL, catalog shape,
package and session facts retain exact checks. There is no rehashing of
a new expected digest or a general retirement bitmask. Missing,
malformed, partially applied or mismatched marker states refuse.

## Limits and acceptance order

- Reproduce the counterexample first with V19 SQL and a single focused
  exact-ID run. It validates that the prepared original Stop stages
  successfully under intact K, rolls it back, observes definitive
  refusals under one and two LOGIN changes, and checks immutable
  committed snapshots after synthetic restoration.
- Review the marker constructor, writer list derivation, exact Stop
  admission, internal checked-context call graph and trusted-owner
  procedure before any forward SQL. The owner is the existing trusted
  synthetic fixture anchor owner. A real deployment requires a
  dedicated independent owner and explicit administrative lifecycle.
- A new private candidate should prove the trusted batch commits
  atomically; direct marker or role mutation by actual actors refuses;
  exact committed originals remain readable by the real reader;
  the real control can use the original Stop once; independent
  readback returns the unchanged original receipt; and held/fresh
  writer access, non-Stop operations and submit replay remain denied.
- Preserve strict refusal for changed Stop ID/hash/head, wrong roles,
  both bits without marker, one bit with marker, a third revoked role,
  name/OID, role attribute including valid_until, binding, package,
  ACL and other structural drift. Check exact no-write snapshots.
  Exercise a controlled retirement lock barrier and guard refusal
  for unexpected post-staging drift in separate owned fixture cases.
- Current _catalog includes actor role OIDs from every scope in the
  schema. A retirement in one fixture scope can therefore fail closed
  in another. Limit this slice to one owned scope and treat the other
  scope as a strict negative. A product that must preserve another
  active scope needs a separately reviewed catalog isolation design.
- Package row locks serialize only the trusted retirement path.
  PostgreSQL superuser DDL performed outside that path remains outside
  this trust boundary. Neither V19 nor this draft establishes native
  protection from arbitrary privileged role/catalog mutation.
- The bound is for this exact original at position 4. More positions,
  multiple retirement batches, late expiry/DDL races, hosted owner,
  migrations and source adoption require separate evidence.
