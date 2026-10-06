# Canonical fresh v5 database component

DB-03A2D3B2B, 2026-10-06. This closes the canonical fresh-command extraction
slice within B2. It is an **offline reviewed component**, outside Supabase
migrations and application startup. The complete legacy cutover, production
credentials/gateway, selected service/browser and hosted acceptance remain open.

## What is extracted

[Explicit entrypoint source](db-contract/v5/entrypoints.sql) accepts exactly
numeric v5 configurations and commands. Missing/null/string/boolean versions
and v1–v4 requests are rejected. The run table itself requires command_version=5.
Older admission branches, permissive parent-ID births and evidence-free fills
are absent. Creation/replay, exact original journal requests and hashes, fence,
lease/revision, canonical IDs, typed lineage, execution arithmetic, risk recovery,
server freshness before/after effects and one atomic acknowledged checkpoint are
preserved. Replay of the identical acknowledged command still precedes renewed
source validation; a new ID cannot stand in for uncertainty resolution.

[The offline builder](db-contract/v5/build.py) pins the reviewed 001/002/004
source hashes, extracts the transitive callable dependencies of the explicit
entrypoints and projection/read/relay functions, and rejects unknown callable
references or changed grammar/anchors. It neither accepts a connection string
nor applies SQL. The pinned $$ function scanner is specific to these sources,
not a general SQL parser or universal dynamic-SQL dependency proof.

The 72-function component retains the private v4 lifecycle model used by v5's
provider adapter, exact decimal arithmetic, optimizer graph/state validation,
cohort/lineage, protection/control and provider/history/clock validators. Four
obsolete v3 admission/evaluation validators are absent. A private inner v4 model
is not a public v4 command path. Curated v5 projections remain synchronous with
the journal insert. Archive admits only a known v5 stopped checkpoint and retains
open-exposure/reconciliation warnings; it does not liquidate or clear them.

[The generated SQL](db-contract/v5/package.sql) and [manifest](db-contract/v5/manifest.json)
are committed review artifacts. The manifest binds complete SQL/source hashes,
each function signature/body/DDL hash/callable dependencies/security-definer flag
and execute role, all 18 fresh core/projection tables with their column/constraint
DDL, domain, explicit indexes and triggers. It is the **fresh component manifest**;
it is not the full production manifest including legacy evidence and migration
history. Internal constraint indexes and catalog OIDs are not represented as
portable explicit index names. Final catalog checks reject extra functions,
wrong owners/bodies/search paths, unexpected grants, raw table/column/maintenance
access, policies and privileged/settable capability memberships before COMMIT.
The tests independently compare the actual catalog with the manifest.

## Capability and installation boundary

| Role | Explicit executable interface | Authority limitation |
| --- | --- | --- |
| vn_economic | create_run, heartbeat, commit_command, get_command, interrupt_expired | No relay acceptance/ACK, curated user identity bridge, helper execution or raw table access |
| vn_relay | read_outbox, acknowledge_event, accept_event | No creation/renewal/economic commands, caller event body or raw table access |
| authenticated | page, events, archive_run | JWT-derived owner-only curated reads/presentation archive; no economic/relay mutation |
| anon, service_role, authenticator | None | No fresh component RPC or raw table capability |
| vn_contract_owner | Internal objects/helpers | Private NOLOGIN owner; no managed Auth usage/grants; narrow bridge execution only |

Both capability roles are NOLOGIN/NOSUPERUSER/NOCREATEROLE/NOCREATEDB/NOINHERIT/
NOREPLICATION/NOBYPASSRLS. No authenticator membership, JWT issuer, password,
production key or schema exposure is configured. The owned fixture creates two
separate non-admin client logins with SET-only membership **after** installation
for real permission tests. Session identity must be nonprivileged when testing
SET ROLE denial: a superuser session that first assumes a lesser role can still
change roles using its session-user authority.

**This proves SQL capability separation, not credential authentication.** Economic
and relay functions still take a trusted owner argument. A compromised future
credential with these capabilities is not run-scoped by these arguments. B2 must
choose/prove verified issuer/custom-role or pinned direct-database/broker transport,
identity/owner/run authorization, issuance/expiry/rotation and independent actor
access before activation. The existing one-key HTTP adapter cannot transparently
serve both separated capabilities; explicit routing/authentication changes are
required in that subsequent slice. Separate modern Supabase secret keys still
resolve to service_role and cannot supply this separation.

Installation connects as the actual limited NOSUPERUSER postgres login, uses the
[B2A Auth bridge and FK ownership path](INSTALLER-BOUNDARY.md), and changes no
managed Auth ACL/body, API membership, installer default or unrelated row/grant.
Existing component/role names abort rather than overwrite. Unexpected global
installer table grants abort atomically. Functions revoke default PUBLIC EXECUTE
inside the installation transaction and fix trusted search paths, including
pg_temp last. PostgreSQL documents why role membership options, PUBLIC/default
execution and SECURITY DEFINER search paths need explicit handling:
[PG17 GRANT](https://www.postgresql.org/docs/17/sql-grant.html),
[PG17 CREATE FUNCTION](https://www.postgresql.org/docs/17/sql-createfunction.html).

## Validation and rollback

Reproduce artifacts from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 services/vonneumann/db-contract/v5/build.py --check
```

Run focused cases from services/vonneumann using the isolated worker environment:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
  DASHBOARD_ISOLATED_POSTGRES_TESTS=1 python -m unittest \
  tests.test_canonical_v5_package tests.postgres.test_canonical_v5 -v
```

Five offline source/dependency/manifest checks and 31 real isolated PostgreSQL
cases cover all four solvers' v5 seed/protection/decision, provider/policy/history/
clock tampering, replay after source expiry, expiry during effects, flat-GA
controller pause/stop, lost commit/delivery replies, caller cancellation/finite
runner, actual-role denials, exact function/object/ACL inventory, owner/foreign/null
reads, durable accept-before-ACK/dedup, archive replay, fresh-name refusal,
unexpected defaults, Auth-FK lock timeout, final installation rollback and late
projection failure. Quotes/providers are fabricated locally; server/process clocks
and SQL transactions are real. This does not claim a full timed v5 replacement
window or production capacity/cadence. Unchanged pinned lifecycle helpers already
have the broader multi-version laboratory trace coverage.

Code rollback for this inert release is a reviewed revert; no production DDL
has been applied. Isolated installation is one transaction, and late failure or
lock timeout removes all new objects/roles. This is **not** the remaining additive
production rollback after acknowledged v5 commands. That must preserve original
journal/outbox/projection evidence and keep retired legacy writers disabled.

An existing synthetic-clock test required exact binary64 uptime equality and
failed by one rounding bit during the full regression. Its uptime assertions now
allow one microsecond; synthetic market clock/pause invariants remain exact.
All seven related clock cases pass; production clock/economic code is unchanged.

## Remaining B2 priorities and substantial research

1. Choose and prove separate economic/relay credentials and the actual gateway or
   database authentication path, owner/run scope, bounded transport, expiry and
   rotation. Do not interpret inert NOLOGIN role creation as a usable credential.
2. Add durable original-ID owner/run/provenance-bound legacy drain/reconciliation
   evidence, retained-position classification, honest archive eligibility and
   invalidation when evidence becomes stale. Stopped status alone is insufficient.
3. Compose the complete forward object/signature/hash/grant manifest with legacy
   classification/retirement, migration history and fresh catalog review; rehearse
   managed installer behavior, locks, old-worker overlap and additive rollback
   after acknowledged commands.
4. D3C replaces every service/UI direct writer, selects one authority and wires
   new/legacy discovery/history/archive/event replay. A3 proves the hosted gateway,
   schema cache, transaction end and complete operator flow before migration/start.

Deep substantial research remains required on indirect privilege closure and
credential issuer/gateway feasibility, legacy exposure/sample comparability,
bounded retention and compact checkpoints, organization provider quotas, lease/
relay/source latency, measured production cadence and worker restart/hosting.
Live wallet funding/signing/swaps/trading remain outside authorization.
