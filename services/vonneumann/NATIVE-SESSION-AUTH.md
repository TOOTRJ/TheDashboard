# Native SQL authentication and owner/run authorization

DB-03A2D3B2C1, reviewed 2026-10-06. This is an **offline direct-connection
candidate**, not deployed DDL, a credential provisioner, or an active transport.
The production worker remains unhosted. The unchanged canonical v5 component
from B2B is its hash-pinned dependency.

## Recommended path and current research

Use separate PostgreSQL logins for the first supervised long-running paper
worker's economic and relay connections. Supabase recommends direct connections
for persistent processes and session pooling when IPv4 is needed. Its role
guidance recommends a separate user per service. This supports the choice;
whether the selected host has working IPv6 and acceptable direct-connection
latency still needs measurement. [Connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres),
[roles](https://supabase.com/docs/guides/database/postgres/roles).

This is an engineering recommendation, not a claim that native SQL is always
better than HTTP. The existing inert HTTP adapter and PostgREST experiments
remain useful evidence. Separate modern Supabase secret keys do not select
separate economic/relay roles. Custom JWT issuance needs a reviewed issuer and
accepted signing key; Supabase-managed signing private keys cannot be extracted.
Avoid changing the project's Auth signing arrangement merely to unblock this
worker. [Signing-key documentation](https://supabase.com/docs/guides/auth/signing-keys).

PostgreSQL's `session_user` retains the original login across `SET ROLE` and
`SECURITY DEFINER`; `current_user` changes. PostgreSQL 17's `system_user` records
the authentication method and identity and is NULL for trust authentication.
The candidate checks both the original login and its actual SCRAM identity,
without trusting caller JWT claims or session settings.
[Session identity semantics](https://www.postgresql.org/docs/17/functions-info.html).

Use a private, explicitly selected project CA and hostname verification for
the client. `sslmode=require` alone does not supply full server identity
verification; `verify-full` checks the certificate chain and hostname. Verify
the actual hosted SSL-enforcement policy before provisioning a credential.
Do not append a CA to the macOS user's shared certificate files.
[TLS verification](https://www.postgresql.org/docs/17/libpq-ssl.html),
[Supabase SSL policy](https://supabase.com/docs/guides/platform/ssl-enforcement).

## What the candidate enforces

`db-contract/session-auth/build.py` composes the verified v5 package with
`access.sql` in one transaction. It accepts no DSN or credentials. Committed
SQL and a manifest reproduce exactly; the reviewed base digest must match.
No application, startup path or migration reads this candidate.

Each native principal has one immutable issuance record with its role OID and
name, economic or relay capability, Auth owner UUID, reserved run UUID, activation,
write expiry and recovery expiry. Reserving a run before creation does not create
an economic run. OID plus name prevents a dropped/recreated login from borrowing
an old record. Existing Auth REFERENCES plus installer-to-private-owner table
handoff avoids new managed Auth grants.

The two capability roles remain NOLOGIN. No credential is installed by the SQL.
The future native login must be non-admin, noninheriting, have a bounded connection
limit and exactly one direct, non-admin, noninheriting, SET-only capability
membership. Attribute/membership drift, absent or mismatched binding, forged owner
or run, not-yet-active issuance, revocation and invalid/infinite password deadlines
fail closed. Native roles cannot inspect or change binding/core/projection tables,
call private helpers, impersonate another login, or acquire the other capability.

All eight economic/relay RPCs check identity/scope at entry and before **every**
successful return, including idempotent replies. Expiry after journal/projection
effects raises an error that rolls back the whole statement transaction. The
existing v5 economics, fencing, revision and source validators remain in place.
Browser reads still use the existing narrow Auth bridge; native worker arguments
are not browser authentication.

The first candidate caps write authority at two hours from issuance and recovery
authority at twenty-four hours. These are conservative engineering ceilings, not
the measured production cadence or a promise that a run lasts that long. Password
`VALID UNTIL` must be finite, cover write expiry and not exceed recovery expiry.
After write expiry, only economic `get_command` may read the original command
until recovery expiry. NULL remains absent evidence, not proof of rollback.
Revocation blocks this recovery access too; a newly issued principal bound to the
same owner/run can reconcile the original command without repeating economics.

Issuance fields cannot be updated or deleted through ordinary table DML. Only a
one-way, nonfuture revocation update is allowed. Rotation means a new principal
and issuance record, followed by old-record revocation, rather than rewriting
old scope/lifetimes. Password changes/expiry alone do not remove an already-open
session's authority; the SQL binding check supplies the runtime deadline.
[Password deadline semantics](https://www.postgresql.org/docs/17/sql-alterrole.html).

## Transaction and TLS limits

The binding row is held `FOR SHARE` through the admitted transaction. Revocation
serializes after work that already acquired that lock, then denies subsequent
admission. It does not preempt an in-flight transaction or retroactively undo a
committed command. Snapshot isolation cannot keep old revocation authority: a
changed locked row causes rejection/serialization failure in the acceptance test.

The checks describe statement admission and final successful return, not an
exact wall-clock deadline at WAL commit. A client holding an explicit transaction
can delay commit and revocation. C2 must own transaction lifetime, server/client
timeouts, cancellation and commit uncertainty, and must not return a known receipt
before independent committed readback where required. No automatic retry with a
fresh command ID is allowed.

TLS statistics are redacted after a role switch/inside these functions. Do not
grant broad `pg_read_all_stats` authority or install an extension merely to read
them. The SQL guard verifies real SCRAM and TCP identity; **client verification
and server SSL policy are separate mandatory gates**. The owned fixture enforces
`hostssl`, verifies the synthetic CA/hostname, and requires SCRAM channel binding.
It does not prove the hosted project has that policy.

Only direct TLS/SCRAM sessions are admitted by this candidate's supported profile.
Session pooling is an IPv4 alternative that needs its own proof of server-side
authentication identity, connection state, timeouts and certificates. Transaction
pooling is not selected. Copy a pooler's exact host/index from verified project
connection metadata rather than inventing it from the region.
[Connection profiles](https://supabase.com/docs/guides/database/connecting-to-postgres).

## Executable evidence and rollback

`tests/postgres/session_auth_fixture.py` uses the cached PostgreSQL image in an
owned, resource-bounded, network-none container. Loopback TCP exists only inside
that container. No exposed port, host mount, application credential or production
connection is used. Synthetic certificates/passwords travel through stdin and
live in owned tmpfs files with private modes. Tests authenticate as real independent
SCRAM logins; trusted fixture administration is used only for issuance, observation
and fault injection. The installer remains the actual limited postgres login.

Five offline composition checks cover reproduction, pinned dependency drift,
eight-entrypoint/return guard coverage and rejection of unreviewed source.
Twenty actual database cases cover authentication/TLS failures, owner/run spoofing,
capability/private/API/trust denial, membership/attribute drift, not-before/expiry,
original-ID recovery, revocation on open sessions and lock serialization, rotation,
OID reuse, immutable scope, stale snapshots, late create/batch rollback, actual
provider-bound bootstrap/relay acceptance/ACK/owner projections, preserved Auth/API/
defaults/unrelated objects, late install rollback and namespace collision.
The canonical 31-case suite is also retained as a dependency regression.

For this inert code release, rollback is a reviewed code revert; there are no
hosted database objects or credentials to remove. Later production application
requires forward migration/catalog/history/lock/postcondition and additive
rollback plans, including retained acknowledged commands and evidence. Do not
delete economic history or restore a second writer as a rollback shortcut.

## Next implementation and substantial research

1. **B2C2 is complete offline:** the [bounded native SQL transport](NATIVE-SQL-TRANSPORT.md)
   hash-locks Psycopg 3.3.6, owns connections/transactions/explicit COMMIT/cleanup
   and exact JSON, and proves the actual controller/relay plus lost-reply/cancel/
   timeout recovery through real TLS/SCRAM. It remains inert and uses no runtime
   psql subprocess. **B2C3 is next:** read-only hosted profile/CA/SSL/auth/network
   facts and a scoped credential validation/storage/expiry/rollback plan before
   provisioning or service selection.
2. **Research deeply:** direct IPv6 versus session pool identity/TLS behavior,
   Supavisor queue/connect/statement/idle bounds, connection capacity, SCRAM/channel
   binding compatibility, secret storage/rotation/expiry and revocation-lock latency.
   Establish a production credential inventory and capture hosted read-only role,
   SSL and certificate facts before selecting a deployment profile.
3. **Finish B2:** durable owner/run/original-ID/provenance-bound legacy writer drain,
   reconciliation/archive evidence and invalidation; full classifier/retirement/
   v5 composition, migration history/overlap and post-acknowledgment rollback.
4. **D3C/A3:** one authoritative selected service, complete browser control/history/
   archive/replay and two-user acceptance; then verified hosted cutover. Actual
   provider/lease/relay latency and quotas, safe interruption, preview isolation
   and worker hosting still precede the supervised paper launch.

Funding, signing, swaps and live trading remain outside this work.

B2C3A now captures [actual hosted metadata and a TLS-only operator preflight](HOSTED-NATIVE-PREFLIGHT.md).
The management path's SCRAM/TLS observation is not worker authentication proof.
The synthetic login issuer uses disposable superuser authority; actual limited
postgres issuance/grants/registry/revocation still require C3B acceptance.
