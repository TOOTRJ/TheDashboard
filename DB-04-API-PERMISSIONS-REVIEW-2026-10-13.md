# Dashboard API table permission review and exact forward delta

One authorized catalog-only request reverified `The Dashboard` /
`fxpxsciltakyypunglzr`, organization `cqfnnaunmupdyobkyqfo`, before querying
only metadata and effective privileges for `public.test_events` and
`public.market_sentiment`. No table rows, credentials, function bodies, writes,
grants, policies or migrations were read or changed. The linked project matches
the immutable target. [Query](supabase/audits/2026-10-13-api-permissions-readonly.sql)
and [original result](supabase/audits/2026-10-13-api-permissions-readonly.json).
The receipt SHA256 is
`e39f2099d5d9b0f17e847a1fc190de8842343536c7e72c7147e8ed822521c420`.

## Actual prerequisites and limits

Both ordinary tables are owned by `postgres`, retain enabled/unforced RLS,
and have zero policies. Their columns have no separate ACL entries. Effective
table privilege checks report SELECT, INSERT, UPDATE, DELETE, TRUNCATE,
REFERENCES, TRIGGER and MAINTAIN for all three API roles. Each role's transitive
membership closure contains only itself, with no membership edges. There are
no PUBLIC table grants. All three roles have public-schema USAGE and no CREATE,
and none is a superuser or LOGIN role. Only `service_role` has BYPASSRLS.

This confirms unnecessarily broad database capabilities. It does not establish
an anonymous row leak or an exposed REST TRUNCATE operation. With RLS and no
policy, normal non-bypass access is denied by the row-security layer; PostgreSQL
explicitly excludes whole-table TRUNCATE and REFERENCES from that layer.
Table grants therefore need their own review. [PostgreSQL17 row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

The observed postgres/public default ACLs also grant broad table, sequence and
function privileges to the three roles. This narrow repair must preserve those
defaults and all other objects; every fresh API baseline must explicitly apply
its final two-table grants in the same transaction as creation. PostgreSQL sums
direct, inherited and PUBLIC grants, and column grants can survive a table-only
revoke; both were inspected for these two tables. [PostgreSQL17 GRANT](https://www.postgresql.org/docs/17/sql-grant.html).

The bounded function-consumer scan returns no non-system routine with a direct
catalog dependency or literal table-name reference. It is not proof against
dynamic SQL, indirect views or external services. Local reviewed API source
requires only service SELECT/INSERT with selected inserted-row replies. The
user reports no other application connects directly to this Dashboard database.
The global API integration is separate from logged-in browser owner authority.

## Frozen proposed delta, not applied SQL

For exactly these two tables, revoke all current explicit table privileges from
`anon`, `authenticated` and `service_role`, then grant SELECT and INSERT to
`service_role`. Preserve postgres ownership/privileges, public-schema grants,
role attributes/memberships, RLS/policies, all data/defaults/constraints/indexes,
global default ACLs, and every unrelated object. The current proof finds no
column, inherited or PUBLIC table grant to repair. If any appears in the next
fresh fingerprint, stop rather than silently expanding the delta.

Postconditions must verify each table's complete effective privilege matrix:
anon/authenticated have none of the eight table privileges or four column
privileges; service has SELECT/INSERT and lacks UPDATE/DELETE/TRUNCATE/
REFERENCES/TRIGGER/MAINTAIN. Preserve exact unrelated/default ACL fingerprints.
No credential rotation, global role/default change or new browser policy follows.

## Ordered remaining implementation and acceptance

1. Draft a source-pinned forward baseline for the exact observed two-table
   shapes. Independently verify existing columns/defaults/constraints/indexes,
   owner, row-security and policies before any permission step. Fresh creation,
   matching continuation, second application and unknown-shape refusal must be
   distinct paths. Do not use CREATE IF NOT EXISTS as equivalence.
2. Review the concrete SQL, its complete catalog manifest, transaction/lock
   budget and additive rollback before execution. Preserve the user-owned
   existing migration; no existing file is a free cleanup target.
3. Run an owned PostgreSQL experiment with synthetic data/roles. Prove service
   SELECT/INSERT/RETURNING, all denied operations, original-row/default/RLS/
   unrelated-object preservation, idempotent application and atomic drift
   refusal. Native SQL and actual PostgREST API behavior need separate proofs.
4. Compose the API validator and reviewed baseline after the CI/app release
   gates. Reverify the exact hosted project and fresh fingerprints, apply only
   the reviewed forward migration, then retain before/after catalogs. No test
   write or lost-acknowledgment retry is implicit in migration validation.
5. If rollback is needed, restore only the exact recorded two-table prior ACLs
   after drift checks. Never drop tables/data, disable RLS or reset defaults.
   Real persistence, complete returned-row validation, conflict receipts,
   retention/index tuning and authentication redesign remain separate work.

The hosted read-only prerequisites are now measured. Concrete migration,
offline SQL/PostgREST proof, exact-source release and hosted application remain
open. This report does not confer a worker or live-trading capability.
