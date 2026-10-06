# Hosted-like private-owner installation rehearsal

DB-03A2D3B2A, reviewed 2026-10-06. This closes one dependency within D3B2:
the private-owner/Auth installation path. The SQL and composition helper are
isolated experiments, outside migrations and application startup. They do not
produce a deployable v5 package or provision any production credential.

## Why the previous bootstrap is insufficient

The [measured Dashboard metadata](../../supabase/audits/2026-10-05-vonneumann-owner-capabilities.json)
shows ordinary hosted `postgres` is NOSUPERUSER, CREATEROLE, CREATEDB, INHERIT and
BYPASSRLS. It can use the Auth schema, execute `auth.uid()` and reference
`auth.users.id`, without grant options. API roles have no role-administration
memberships or role/database creation powers. The private owner is absent.

The original laboratory grants Auth dependencies to `vn_contract_owner` from a
superuser. A new real-PostgreSQL case reproduces its failure when those grants
are absent. Supabase documents that hosted `postgres` is not a superuser;
its managed role/object behavior still needs hosted acceptance.
[Supabase roles and superuser limits](https://supabase.com/docs/guides/database/postgres/roles-superuser).

## Rehearsed installation path

The existing offline harness first creates its disposable cluster as a
superuser. The new fixture renames initdb's bootstrap role, which cannot lose
SUPERUSER, then creates a distinct **actual `postgres` login** with the measured
attributes. A separate synthetic Auth owner retains the managed objects.
The installation authenticates as that non-superuser login; it does not obtain
its permissions from a superuser session using SET ROLE. Test seeding,
adversarial injection and independent catalog observation use a clearly named
fixture administrator. They never supply installation statements with that
administrator's connection.

One transaction performs the following:

1. Require the rehearsal marker, exact installer identity/attributes, the
   measured usable-but-not-grantable Auth dependencies, four nonadministrative
   API roles and fresh private object names. Mismatches abort before mutation.
2. Create a dedicated NOLOGIN/NOSUPERUSER/NOCREATEROLE/NOCREATEDB/NOINHERIT/
   NOREPLICATION/NOBYPASSRLS owner. Preserve PostgreSQL 17's automatic creator
   ADMIN-only membership and add a separate self-granted SET-only membership.
   Neither inherits privileges. A transaction-local empty
   `createrole_self_grant` neutralizes inherited settings; the prior setting
   returns at transaction end. Membership postconditions require exactly the
   two reviewed grantor/option tuples, with no API or reverse membership.
3. Create a parameterless, STABLE, SECURITY DEFINER `vn_identity.owner_id()`
   owned by `postgres`, with a fixed `pg_catalog,pg_temp` search path and only
   `SELECT auth.uid()` as its body. The installer owns its schema; the private
   owner gets USAGE/EXECUTE without CREATE or grant options. PUBLIC/API and
   unexpected function-execution grants are rejected. No managed Auth ACL or
   function body changes.
4. Temporarily grant the installer CREATE/USAGE on the new core schema. After
   the private owner creates the exact balance domain, `postgres` creates the
   original run table and Auth FK using its existing REFERENCES privilege,
   transfers the table to the private owner, and removes those temporary schema
   grants. The remaining laboratory objects use the private owner.
5. Bind private read-identity expressions to the narrow bridge and install the
   unchanged economic/validator SQL and curated projections. An injected late
   error or Auth-FK lock timeout rolls back roles, memberships and objects.

PostgreSQL documents the distinct ADMIN/SET/INHERIT options and the automatic
creator grant. It requires SET access to a new table owner and that owner's
CREATE privilege on the schema for ownership transfer. These rules motivate
the rehearsal; the tests establish the observed behavior on the pinned image.
[Role attributes](https://www.postgresql.org/docs/17/role-attributes.html),
[GRANT](https://www.postgresql.org/docs/17/sql-grant.html),
[ALTER TABLE](https://www.postgresql.org/docs/17/sql-altertable.html),
[creator settings](https://www.postgresql.org/docs/17/runtime-config-client.html#GUC-CREATEROLE-SELF-GRANT).

The identity bridge preserves `auth.uid()` semantics, including null identity,
sub/claims precedence and malformed UUID rejection. **It does not verify JWT
signatures or turn caller-set SQL claims into authentication.** Actual hosted
gateway authentication remains A3 work. SQL roles able to set claims must be
treated according to their own privileges. The installer is a trusted DBA
boundary; the bridge does not protect against a compromised installer.
The private owner cannot replace/drop the bridge or grant its execution onward.

## Source and acceptance boundary

[The manifest](db-contract/installer_boundary_manifest.json) pins the original
001/002 laboratory hashes and the new 004 boundary SQL. The composition helper
checks exact source sets, hashes and unique textual anchors before adapting
ownership/identity statements. This is deliberately **not** the future
production compiler: 001 retains private multi-version validators and its old
service-role entrypoint grants for laboratory compatibility. No generated
artifact is written into migrations. D3B2 must still extract canonical
dependencies and expose only the reviewed v5 production entrypoints.

All 17 focused cases pass in 10.288 seconds on the final boundary SQL. Tests
use independent real role connections, all four actual v5 solver
bootstraps with eight-probe atomic projections, two-owner/null-identity read
denial, Auth FK enforcement after transfer, fixed search-path behavior, private
owner/API denial, original-bootstrap failure, stale object rejection,
unexpected default-grant rejection, full late rollback and FK lock timeout.
Auth owners/ACLs/column grants/function body, API attributes/memberships,
installer defaults and unrelated rows/grants are compared before and after.
Tests run only in the owned local Docker cluster; no application environment,
provider/network request or hosted write is used.

The ordinary worker regression ran 1,465 tests successfully in 231.112 seconds
with 62 expected isolated-database skips. Those skips do not replace the 17
explicit real-database cases above.

The caller-set rehearsal marker reduces accidental application; it is not an
authorization boundary. The snapshot is not a complete managed-platform emulator. Hosted DDL hooks,
database ownership, gateway configuration, schema cache, current grants and
transaction-end behavior must be reverified before production application.
The 003 legacy retirement/classifier is not yet composed with this installation
path. Its identity dependency and durable evidence workflow remain in B2.

## Credential research and next implementation

Creating two modern Supabase secret keys helps independent key management but
both resolve to `service_role`. It does not separate economic commands from
relay acceptance. [Supabase API key role mapping](https://supabase.com/docs/guides/getting-started/api-keys).

| Candidate | Useful property | Required proof before selection |
|---|---|---|
| Custom PostgREST roles with short-lived verified JWTs | Can preserve the HTTP/RPC path with separate SQL grants | Trusted issuer, role/sub/run restrictions, authenticator SET grants, hosted key verification, expiry/revocation, and token-bound owner checks; no arbitrary claims from browser metadata. |
| Separate direct database logins | Native SQL grants can separate economic and relay authority | Project-pinned TLS/pooler identity, secret storage and rotation, one-attempt transaction-end/readback semantics, bounded pools/timeouts and a new transport. Current HTTP adapter does not implement this. |
| A narrow trusted token/RPC broker | Can centralize issuance and owner authorization | Its privileged credential remains a broad trust boundary; prove restricted routes, identity, replay, lifecycle, latency and availability before claiming isolation. |

PostgREST validates JWTs then switches to the claim's database role only through
its configured role membership. Current Supabase signing-key documentation says
managed private key extraction is unavailable; a generated custom JWT is not
usable merely because its payload has the right role. These facts require
issuer/gateway research before implementing custom worker credentials.
[PostgREST authentication](https://docs.postgrest.org/en/v14/references/auth.html),
[Supabase signing keys](https://supabase.com/docs/guides/auth/signing-keys).

Next, extract and rehearse the canonical v5-only package with complete object/
signature/hash/grant checks under this installer path. Then select and prove
separate economic/relay credentials, bind legacy drain/reconciliation/archive
evidence to original owner/run/provenance IDs, and rehearse additive rollback
after acknowledged commands. Deep research remains for indirect privileges,
credential expiry/issuer compromise, hosted gateway feasibility, legacy evidence
invalidation, retention/compact checkpoints and production timing/costs. D3C
service/browser selection and DB-03A3 full hosted cutover remain required.

Rollback this inert code/documentation release by reviewed revert. The offline
late-failure test is not a production rollback plan after acknowledged v5
commands. That future rollback must retain history and denied legacy writes.
No credential creation/rotation, managed grant change, migration, worker
deployment, signing, funding, swap or live trading is included here.
