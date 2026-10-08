# Limited native credential issuer rehearsal

DB-03A2D3B2C3B1, 2026-10-07. This closes the offline limited-issuer proof within
C3B. Subsequent actual managed rollback acceptance and corrected installer
REPLICATION/Auth dependency facts are recorded in [SUPABASE-CUTOVER.md](../../SUPABASE-CUTOVER.md). The worker remains unhosted; actual selected-host IPv6/TLS/native acceptance
and production secret injection remain open. No production credential is issued
or revoked. Templates are outside migrations and startup; only the explicitly
opted-in, owned, network-isolated PostgreSQL fixture executes them.

## Missing proof and research

C1/C2 used a disposable superuser to create test logins. The new issuer actually
authenticates as non-superuser `postgres`, with the [captured Dashboard attributes](../../supabase/audits/2026-10-05-vonneumann-owner-capabilities.json).
The synthetic administrator only bootstraps, seeds Auth, injects faults and
observes independently. Supabase's managed role hooks still require separate
acceptance; its `postgres` is not an unrestricted superuser.
[Supabase role limits](https://supabase.com/docs/guides/database/postgres/roles-superuser).

PostgreSQL 17 gives a non-superuser creator an automatic ADMIN-only membership
in each new role. ADMIN supplies neither SET nor inheritance, but the trusted
DBA can grant those to itself. This protects against accidents, not compromised
administration. Capability administration uses the installed economic/relay
roles' ADMIN grants; registry access explicitly uses the reviewed private-owner
SET membership. [Role attributes](https://www.postgresql.org/docs/17/role-attributes.html),
[GRANT](https://www.postgresql.org/docs/17/sql-grant.html).

## Atomic issuance

The manifest pins three templates and the managed-profile-corrected native-auth package
`0a01e7828d9a7619efd54ac9a9331e598c650429c61717183464c09f4387c5ee`.
No privileged public RPC, stored provisioner, production runner, environment
credential loader or DSN is introduced.

One bounded transaction verifies actual limited issuer identity, reviewed
private-owner/catalog/capability state and absence of unexpected API/private
table/column access. It refuses existing principal names or issuance IDs. Two
independent UUID principals/issuance IDs and 256-bit ASCII synthetic passwords
are generated in memory; strict input/lifetime validation precedes SQL.

Creator self-grants are locally neutralized. Both principals begin NOLOGIN,
non-admin and noninheriting, with two connection slots and exactly one SET-only
capability each. One database clock supplies both immutable owner/run/OID/name
bindings and finite activation/write/recovery/password deadlines. Existing
two-hour write and twenty-four-hour recovery ceilings are unchanged.

Private object resolution/insertion explicitly switches to the private owner,
then returns to `postgres` for role administration. No extra schema access or
managed Auth grants are added. Exact role/membership/deadline postconditions
precede LOGIN and COMMIT. Other sessions see neither principal nor binding
before commit; an Auth FK failure or injected late error rolls back both roles,
memberships and bindings. Caller creator/password settings restore afterward;
API roles, managed objects, defaults and unrelated rows/grants are preserved.

The fixture computes SCRAM verifiers before SQL; real TLS/SCRAM/channel-bound
logins prove their format. Plaintext passwords are absent from statements and
object representations. Passwords/verifiers remain sensitive: memory/stdin and
private owned tmpfs only, with known synthetic values redacted from returned SQL
diagnostics. This is not a production secret/logging runner. PostgreSQL warns
that plaintext password statements may appear in client/server logs.
[ALTER ROLE](https://www.postgresql.org/docs/17/sql-alterrole.html).

Lock, statement and transaction limits are 500 ms, 6 seconds and 10 seconds,
plus a finite owned client lifetime. These are local engineering bounds, not
measured hosted limits. [Timeout and creator settings](https://www.postgresql.org/docs/17/runtime-config-client.html).

## Revocation, rotation and uncertain replies

Revocation needs only retained scope, exact OIDs/names and issuance IDs, never
an old password or usable write lifetime. It locks both bindings in stable
order, checks owner/run/capabilities, sets one-way revocation and disables LOGIN
in one transaction. Repeating completed revocation retains its first timestamps
and all evidence.

Admitted transactions hold SHARE locks. A lock timeout is failed revocation,
with neither pair member partially revoked. No session termination or reversal
of acknowledged economics is performed. After success, already-open unadmitted
connections are denied by the SQL binding guard independently of NOLOGIN.

A pre-DDL name/OID check alone was insufficient. A concurrent DBA may drop and
recreate the name during the gap. The template revalidates after ALTER ROLE has
acquired the role's tuple lock. The real gap race rolls back binding/NOLOGIN
effects and preserves the independently created replacement. A second real
test proves DROP cannot replace that role between final validation and COMMIT.
Identity/attribute drift fails closed and requires separate incident review.

Rotation uses a fresh immutable pair for the same owner/run, which can read the
original command without repeating economics. Old revocation retains history.
The lost-reply test closes only its owned client after COMMIT and proves that
resubmission is refused while the exact pair remains. Future operator code must
reconcile original issuance IDs and retained secrets, not automatically issue
another pair. That production workflow remains unimplemented.

## Acceptance and next gates

Seven ordinary checks and 38 real isolated issuer/native-auth cases cover
source/input/secret bounds, creator settings, atomic publication/collisions,
FK/late rollback, preserved managed/unrelated state, issuer/API refusal, actual
login/RPC scope and expiry, recovery, held-transaction and role-replacement
races, one-way revocation, rotation and lost replies. Existing installer,
canonical-v5 and native-auth suites supply dependency regression. Final counts
and release evidence belong in CONFIGURATION-PREFLIGHT.md and the PR.

This is behavior on pinned local PostgreSQL 17.6, not a managed-platform or
hosted connection proof. Rollback is a reviewed code revert, with no hosted
object/credential cleanup.

Remaining order: actual selected-host IPv6/project-CA/hostname and native canary
acceptance, gated private injection/SSL-maintenance review; B2 durable legacy
drain/reconciliation/archive evidence and invalidation; full composition,
catalog/history/overlap and additive post-ACK rollback; D3C/A3 selected writer
and browser/two-user cutover. Provider/lease/relay timing/quotas, preview isolation,
image/capacity/shutdown acceptance still precede the bounded paper pilot.

**Deep substantial research remains:** managed role hooks/current grants;
issuer secret transport/SCRAM parameters/log handling; uncertain issuer/revoker
readback; role/registry/held-transaction lock tails; expiry/rotation operations;
CA/native-library maintenance; aggregate connection/relay capacity and real
provider timing. No wallet funding/signing/swaps/live trading.
