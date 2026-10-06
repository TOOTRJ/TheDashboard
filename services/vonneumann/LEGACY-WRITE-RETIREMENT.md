# Legacy write retirement and classification rehearsal

DB-03A2D3B1, 2026-10-05. The 25 real PostgreSQL acceptance cases pass. This
completes the isolated legacy-retirement slice; **D3B remains open** for the
v5 production DDL, full object manifest, credential/installation acceptance and
evidence-backed legacy archive policy. D3C and DB-03A3 still gate application.

`db-contract/003_legacy_retirement.sql` and `legacy_catalog.sql` are deliberately
outside `supabase/migrations`. Application startup imports neither. The reviewed
[manifest](db-contract/legacy_retirement_manifest.json) pins their SHA-256 hashes,
exact object/grant scope, finite limits and open gates. It explicitly declares
`production_application_available=false`. There is no cloud application runner.
Do not remove the rehearsal marker to manufacture a production migration, or
run this retirement while the existing direct-writing service remains selected.

## Measured production evidence

Fresh exact GitHub identity and Supabase project/link/pooler identity were
verified. The sequential read-only legacy inventory matches the committed
2026-10-05 snapshot in every field: 8 stopped colonies, 497 probes across 24
runs, 807 trades including 17 unclosed records, and 9,837 samples. The fourteen
migration versions, grants, policies and absent durability schema are unchanged.
Counts do not establish a worker drain, reconciled holdings or two-user isolation.

The additional [capability query](../../supabase/audits/vonneumann-owner-capabilities.sql)
and [approved metadata](../../supabase/audits/2026-10-05-vonneumann-owner-capabilities.json)
run under `postgres` in a repeatable-read/read-only transaction, with one-second
lock and 15-second statement limits. Hosted `postgres` has CREATEROLE and
BYPASSRLS but is **not a superuser**. It can use `auth`/`auth.uid()` and reference
`auth.users.id`, but has no grant option on any of those dependencies. The
proposed private owner does not exist. The four API roles have no CREATEROLE,
CREATEDB, replication or ADMIN memberships in this snapshot. No credentials,
function bodies or user IDs were returned.

This exposes a real installation gap: the local fixture's superuser bootstrap
grants auth dependencies that ordinary hosted `postgres` cannot grant onward.
The v5 migration must prove its installation path under the actual role. Review
existing PUBLIC dependency grants, creating/validating constraints under the
authorized installer before transferring ownership, and an owner-derived claims
helper if necessary. These are options requiring acceptance, not applied fixes.
Do not broaden managed auth permissions, borrow `supabase_admin` credentials or
treat its catalog capabilities as usable session authority.

Vercel's dedicated profile could not return authenticated target metadata during
this increment, and its auth file was absent when checked. A login to the exact
Dashboard profile was requested. Shared/default profiles are not a fallback.
On 2026-10-06, user-completed dedicated login restored access. Fresh provider
metadata, non-interactive resolved project inspection and team identity match
`the-dashboard`/`prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`/team
`team_8iNNxiNjrOseD4gdSCHkQEzF`, slug `orderoftheredjester`; GitHub and Supabase
targets also match. Release still requires exact-source READY preview, the
reviewed merge, exact-merge READY production and read-only application smokes.
Final immutable evidence is recorded in the PR; no migration is part of release.

## Exact retirement scope

| Object or capability | Rehearsed change |
|---|---|
| Five `public.vn_*` tables | Revoke INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER and PG17 MAINTAIN from PUBLIC, anon, authenticated, service_role and authenticator. |
| Every column in those tables | Explicitly revoke INSERT, UPDATE and REFERENCES from the same roles; retain existing SELECT. |
| Rows, columns/defaults, constraints/indexes, triggers/functions and RLS policies | Preserve all definitions and rows. No backfill, liquidation, status rewrite or delete. |
| Existing browser/service read grants | Preserve them. Anonymous owner-filtered reads still see no rows; privileged service-role SELECT remains privileged. |
| Shared roles, memberships, `postgres`/`supabase_admin` defaults and unrelated objects | Preserve them. Reject residual inherited/settable authority instead of changing shared role structure. |
| Rehearsal private owner | Grant SELECT on precisely the five legacy tables, using existing fixture auth dependencies. Validate NOLOGIN/NOBYPASSRLS/nonprivileged/noninherited role and no API membership in either direction. |
| New `vn_legacy` schema and `classify_run(uuid)` | Only authenticated receives USAGE/EXECUTE. Function derives `auth.uid()` and explicitly filters every legacy query by owner/run. No mutations. |

Table privileges and column privileges are additive. A column revocation cannot
cancel a table grant; PostgreSQL's table revocation also removes corresponding
column privileges. The explicit column pass and independent postcondition check
make the expected denial reviewable.
[PostgreSQL GRANT](https://www.postgresql.org/docs/17/sql-grant.html),
[REVOKE](https://www.postgresql.org/docs/17/sql-revoke.html).

INHERIT, SET and ADMIN are separate membership options. The catalog oracle walks
API-role ancestors to depth 16, rejects truncated scans, and examines every
reachable role conservatively. Residual table/column write or maintenance
privileges, privileged role paths and ADMIN membership abort the transaction.
[PostgreSQL role membership](https://www.postgresql.org/docs/17/role-membership.html).
No membership is revoked to force the test to pass.

## Review, lock and atomic failure behavior

The runner obtains its expected catalog in an independent session before the
mutation session. A session-local review table then holds exactly one bounded
JSON object. The retirement locks all five legacy tables in a fixed order with
ACCESS EXCLUSIVE, a 500 ms lock limit and an eight-second statement limit. The
snapshot is checked again after acquiring the locks.

The oracle includes table ownership/RLS, 93 column definitions, constraints,
indexes, policies, enabled triggers, exact table/column grantors/grantees/grant
options, API role attributes/memberships, relevant defaults and function
definitions/settings/ACLs. Function MD5 values are change indicators, not security
signatures or provider-authenticity proof. Unexpected relevant security-definer
functions, dependent views, external incoming FKs or related sequences require
separate review. Source-string function discovery remains a heuristic: dynamic
SQL, indirect wrappers and external credentials require the later full audit.

After REVOKE, effective privileges are recomputed for every reachable role,
including column REFERENCES and MAINTAIN. Remaining authority raises an error
and rolls back every preceding revocation. RESTRICT avoids silently cascading
delegated grants; another grantor or grant-option delegation is rejected.

A pre-existing writer holding a table lock causes a bounded failure with no
partial retirement. Once that writer finishes, a fresh reviewed attempt can
succeed. A transaction/session opened before successful retirement cannot later
write using its old role privileges. This does not prove external processes have
exited, fence administrators or stop a privileged owner from granting access
again. Production still needs measured drain evidence and operational monitoring.

The caller-settable rehearsal marker is an accidental-application guard, **not
authentication or authorization**. The expected JSON is test review input, not
a signed release approval. A production assembler must pin a human-reviewed
artifact/target and implement its own installation and independently committed
postconditions; it must not capture-and-approve an unknown catalog automatically.

## Honest legacy classification

`classify_run(run)` returns version 1, provenance `legacy`, derived owner/run,
saved colony status/mode when available, counts of probes/trades/samples/
generations, missing object-shaped metrics/execution records, scalar-parent
records, unavailable ancestry arrays and unresolved owner/run-bound links.
NULL run is supported for genuinely unbound legacy rows without inventing an ID.
An inaccessible/missing run returns the same unavailable error.

A colony-backed run is `legacy_unfenced`; a probe/trade/sample-only or unbound
group is `legacy_unmanaged`. Neither is automatically restored or converted into
v5 money, policy, fitness or ancestry. Empty `parent_ids` does not assert no
parents. Existing scalar parents remain untouched. An object-shaped record such
as `{}` only satisfies a shape-presence count; `metrics_verified`,
`execution_verified` and `ancestry_verified` remain false. Currency and sampling
policies remain `legacy_unknown`, separate from v5 USD-reference/sample policies.

Every legacy archive response is ineligible until a separately reviewed durable
evidence workflow exists. Baseline blockers are `writer_drain_unproven`,
`reconciliation_unproven` and `no_authoritative_checkpoint`; unbound runs,
unresolved relationships and unclosed records add their own blockers. Seventeen
production unclosed records are evidence requiring investigation, **not proof of
seventeen current on-chain positions**. `live_holdings_verified` remains false.

The future legacy archive workflow must bind a reviewed writer inventory/drain
receipt, owner/run/provenance, post-drain retained-row evidence and reconciliation
results (including explicitly retained/unmanaged exposure). It needs immutable
original request IDs, audit history, invalidation on subsequent evidence change,
two-owner denial and non-destructive operator behavior. No saved stopped status,
empty open-row count, lease absence or caller boolean substitutes for that proof.

## Acceptance and remaining research

The fixture reconstructs the captured 93 columns, 19 constraints, 25 indexes,
18 RLS policies, two invoker triggers, six broad default ACL entries and three
noninherited/settable authenticator memberships from committed metadata. It does
not replay the edited historical migration. Rows and identities are fabricated;
real application env files, keys and provider requests are never used. API roles
have LOGIN for real independent connections. Administrative bootstrapping still
differs from hosted Supabase and is explicitly not production installation proof.

Twenty-five cases cover all eight initial privileges, table/column/PUBLIC denial,
BYPASSRLS without write grants, direct DML/TRUNCATE/REFERENCES/TRIGGER/REINDEX/locks,
authenticator SET ROLE, nested maintenance and inheritance-only aliases, ADMIN/
CREATEROLE, private-owner leakage, drift, delegated grants, indirect dependencies,
late rollback and old-worker overlap. Two synthetic owners and anon validate
owner reads/classification. Rows/definitions/policies/defaults/memberships and an
unrelated sentinel are compared. A new unrelated table retains its original
broad default grants. Presentation removal preserves history and keeps writes
denied. Actual v5 creation/bootstrap and atomic eight-probe projections coexist
with retired legacy tables without a second legacy economic writer.

**Deep substantial research and acceptance remain necessary:**

1. **Least-privilege credentials and installer capabilities.** Modern secret
   keys still resolve to `service_role`; separate opaque keys do not create
   separate SQL roles. Compare a dedicated direct-DB worker role against a
   separately authorized short-lived custom-role gateway, and split economic
   command and identity-only relay capabilities. A custom-role JWT example uses
   signing authority; do not give that project-wide authority to the worker by
   assumption. Validate hosted gateway support, owner binding, revocation,
   timeouts and exact installer grant paths before choosing.
   [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys),
   [roles](https://supabase.com/docs/guides/database/postgres/roles),
   [custom-role example](https://supabase.com/docs/guides/storage/schema/custom-roles).
2. **Complete v5 object/dependency closure.** Extract reviewed canonical exact
   validators, then install v5-only public entrypoints and explicit auth/owner/
   projection/read/relay contracts. Do not copy the multi-version 001 laboratory
   fixture or expose its v1–v4 entrypoints. Hash and review every deployable object,
   overload, bound, grant and rollback action; test with hosted-like installer
   capabilities before DB-03A3.
3. **Legacy evidence and comparison.** Establish drain/reconciliation/archive
   attestation semantics; research historical execution, ancestry and sampling
   availability without invented backfills or retrospective v5 policy labels.
4. **Operational limits.** Measure actual lock/DDL/gateway/source/lease/relay
   tails, compact checkpoints, query/storage costs, retention and concurrent
   administrative grant drift. A local 500 ms lock limit is a test bound, not a
   measured production outage budget.

Before any v5 economic command is acknowledged, a failed migration transaction
can roll back its own changes atomically. After acknowledgment, code rollback
must drain and preserve authoritative journals/projections/relay/checkpoints and
keep legacy writes denied. Do not re-enable an unfenced old release over v5 runs.
Production application and full rollback drills remain D3B2/D3C/DB-03A3 work.
