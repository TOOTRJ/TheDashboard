# V20-O ownership and terminal retirement composition

The new private source combines the exact V19-O owner and grantor seal with
the exact V20 retirement guard and owned fixture issuance procedure. The
dedicated NOLOGIN anchor owner owns its schema, both tables and fixed broker.
The sealed native NOLOGIN owner receives only anchor USAGE, SELECT and broker
EXECUTE from that owner. The broker retains its exact fixed row locks and
has no DML, role-management statement or dynamic SQL. Actors and owners have
no membership edges. The fixture still verifies owner/type/grantor identity,
table and column access and scoped catalog before establishing its held K.

Only the actual trusted fixture bootstrap superuser executes the fixed
retirement arrangement. It verifies session_user, exact held package and
catalog, scope, head, writer names and OIDs under locks. It then issues the
two exact LOGIN removals and writes one marker in the same transaction.
The NOLOGIN anchor owner has intrinsic table ownership, but no reachable
login or membership. It has no CREATEROLE. There is no worker route for
arbitrary marker changes or role management. The disposable superuser
remains the explicit administrative trust boundary.

The catalog pins the dedicated anchor owner's role attributes and membership
edges. The retirement exception still projects only the two exact writer
login bits, never either owner. Its sole write is the reserved exact Stop
for the current marker. The V20 held/fresh paths and V19-O closed ACL
expectations remain intact as source.

## Root-only review and run

1. Verify [the manifest](candidate-manifest-v20-o.json) SHA-256
   `9c60394ec9f52d51e6d0bebc8f45cecb10d8a755b32a709e1e3509a92a4466ea`.
   Reconstruct from either exact parent with the manifest's corresponding
   forward patch, then verify all six postimages. Both reconstructions
   already passed static verification. All 41 methods match parent bodies.
2. Choose and pin one exact Git base before composition. The PR113 repeated
   reference base produces 936 files with six source postimages. The local
   accepted PR115 merge `f317ffc4519d5a70002279458992e54465a9821f`, tree
   `3eb3469b0d4eb4e4d7993d202fc54909bff9da89`, has 936 ordinary tracked
   blobs and no candidate destinations, for 942 files after composition.
   Validate every tracked blob and prospective source hash in the private
   export. A newer tree needs its own reviewed inventory.
3. After independent source and controller review, use the exact two IDs
   in the manifest under the existing CPython 3.12.14, local Unix Docker
   socket, immutable cached PostgreSQL ARM64 image, network-none sandbox,
   explicit environment allowlist and unchanged 240-second outer limit.
   Require two actual cases with zero errors, failures or skips, exact
   unchanged snapshot and normal owned cleanup. Retain all raw outcomes.
4. The first case verifies both owners and refuses owner LOGIN/membership
   drift. The second runs the authorized marker and terminal Stop on that
   same composed seal, including live reader recovery and late unrelated
   drift refusal. Any broader regression suite gets its own exact case
   list and receipt. No native execution occurred during composition.
