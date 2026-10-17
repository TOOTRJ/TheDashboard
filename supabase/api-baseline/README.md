# Independent two-table API baseline candidate

This is **offline candidate source**, not a migration or permission to execute
against a hosted project. `scripts/dashboard_api_baseline.py` only emits SQL;
it reads no environment file, credential or database connection. Existing
migrations, including the user's dirty migration, remain untouched.

The independent constructor declares exactly these public objects:

| Root | Columns | Default-bearing columns | Constraints | Indexes |
| --- | --- | --- | --- | --- |
| market_sentiment | 8 | id, key_factors, date, source, created_at | primary id, unique date, score range, sentiment enum | primary id, unique date, descending date |
| test_events | 4 | id, source, created_at | primary id | primary id, descending created_at |

There are eight column-default bindings and six distinct expressions. Source
and created_at stay nullable. Native CURRENT_DATE is preserved; no UTC rewrite,
NULL filling, payload/array constraint, owner column or index optimization is
introduced. Tables are postgres-owned ordinary permanent heaps with enabled,
unforced RLS and no policies. No role/schema/default-ACL modification is emitted.

## Two-phase independent expectation

1. Review constructor/catalog/emitter and the separately owned API fixture.
   `constructor_sql()` requires both tables **and every planned relation/type
   name** to be absent, then constructs only these two tables and their owned
   indexes. It grants only service SELECT/INSERT before the same transaction
   commits. It is the explicit fresh-fixture probe, not an idempotent installer.
2. The root-owned approved PG17.6 fixture independently runs that constructor
   and obtains `catalog_sql()` JSON. Review its complete structural inventory,
   actual native function/operator/default identities and supported context.
3. Freeze only the reviewed `structure` under `expected.json` with exact source
   hashes, status `reviewed-owned-constructor`, and its externally pinned whole
   file SHA256 in the library. No caller can provide a replacement expected
   file/hash. The expectation is now frozen from the reviewed ordinary-role
   constructor probe. Its source hashes and external whole-file hash are checked
   before `baseline_sql()` emits admission SQL. No hosted-derived expectation
   has been substituted.

The final expected-file keys are exactly `format`, `status`,
`constructor_sha256`, `catalog_sha256`, and `structure`. Format is
`dashboard-api-independent-native-expectation-v1`; `structure` has exactly
`tables`, whose keys are exactly the two table names. Every nested native field
is then bound by the source-reviewed external expected-file hash and exact
JSONB equality, including all array inventories. Python refuses duplicate keys,
nonfinite constants, missing/extra outer keys, source mismatches and oversized
files. An evidence receipt cannot authorize native or hosted execution.

## Modes and no-op behavior

`baseline_sql(*, apply_acl=False)` returns one BEGIN/SET LOCAL/DO/COMMIT program.
It acquires fixed-order ACCESS EXCLUSIVE locks on existing target tables,
checks both complete existing structures, supported ACL envelopes and all
planned-name collisions **before creating either missing table**, then creates
only missing reviewed objects. Exact existing structure is never repaired,
renamed, altered or replaced. Its existing-table paths execute no CREATE,
GRANT or REVOKE. Every fresh table receives final narrow table ACLs before
commit, even when postgres global/public creator defaults are broad.

`baseline_sql(apply_acl=True)` is explicitly **permissions-only**. Both tables
must exist and match. It accepts only the reviewed broad-before or narrow-final
table/effective-column privilege envelopes, then changes only the broad table
ACLs. An already-final table executes no ACL statement. The broad envelope is
all eight privileges for postgres and the three API roles, without grant
options; final preserves postgres and gives only SELECT/INSERT to service_role.
PUBLIC, column, adjunct, inherited or unfamiliar effective grants refuse.

There is no CREATE IF NOT EXISTS, DROP, ALTER-existing-structure, new policy,
generalized controller, execution CLI or success-on-exception branch. Failures
raise `P0001` with fixed message `dashboard_api_baseline_refused` and fixed safe
detail codes. No raw row/expression/database error is added to those details.
An intentional test-only failure can be inserted before the original COMMIT
to prove transaction rollback; there is no production failure-injection option.

## Catalog, clocks and administrative boundary

`catalog_sql()` returns one read-only JSON SELECT with exact envelope keys:
`format`, `complete`, `counts`, `structure`, `permissions`, `collisions`,
`identities`, `context`, `limits`. It reads no application rows. It inventories
all scoped main/index/TOAST relations and attributes, full index flags/vectors/
operator classes, row and array types, defaults and constraints, referenced core
functions/operators, adjunct counts, and direct incoming/outgoing dependencies
of the two roots and owned adjuncts. No arbitrary dependency graph is traversed.
Actual object OIDs are retained separately in `identities`; structural endpoints
normalize only reviewed local owned objects. Core OIDs remain literal and
actual native metadata must match the independently derived expectation.
Core function, operator and operator-class ownership is bound by numeric
`owner_oid` (the PG17 bootstrap owner OID10), not its display name: the owned
fixture uses a separately named bootstrap administrator and a non-superuser
postgres installer. Renaming that fixture bootstrap identity must not relabel
native ownership. Application table, index and row/array-type owners remain
explicitly bound to the postgres role name. This distinction neither changes
roles nor accepts a different native owner OID.

Native default/CHECK trees normalize only `:location` fields. Exact known
deparser spellings permit publication of those source-declared expression
trees, **not admission**: complete native tree and referenced identity equality
still decide admission. Unknown expression trees are suppressed as null and
must mismatch/refuse; raw unknown expression text is never a refusal detail.
Overflow/incomplete inventory refuses. TOAST relations include their own
attributes and pg_index state; an empty/abbreviated older observation is not
used as a complete TOAST expectation. Shared ACL dependencies are separated
from structural dependencies; effective table/column grants are checked under
the separate ACL envelope. Existing scoped native identities must survive.

The candidate supports PG170006, UTF8, effective current_user postgres and the
three reviewed NOLOGIN/INHERIT API-role attributes with no outgoing memberships;
only service has BYPASSRLS. It records session_user without guessing hosted
Management API connection identity. The complete hosted installer/schema-owner/
context admission profile remains separately gated; this is not a hosted
authentication or full role-control model.

READ COMMITTED catalog reads occur in separate volatile DO/SPI statements.
Local lock_timeout1s and statement_timeout10s are checked in the transaction.
They are not a total operation wall deadline; the caller must own the separately
reviewed wall/cleanup budget (the owned suite passes with 15s per SQL call;
the hosted caller budget remains separate). Relation
locks protect relevant table structure; they **do not exclude GRANT/REVOKE or
role/schema/default administration**. The candidate requires externally
serialized/quiescent administration, checks before/after context and refuses
observed drift. It does not claim absolute admin exclusion or final-visible
freshness. Missing-name DDL races must fail the transaction; no cooperative
advisory lock is represented as a namespace lock.

## Required proof before acceptance or deployment

The independent fixture lane must prove fresh/matching/repeat/mixed states;
wrong-kind/name/array/default/type/constraint/index/adjunct/dependency refusal;
full rollback after a late failure; unchanged original rows/IDs/owners/defaults/
unrelated objects; exact table/effective-column privilege matrices; legitimate
defaults and explicit nullable values; range/enum/date/unique behavior; and real
PostgREST selected replies plus independent committed SQL readback. Synthetic
authenticator/JWT tests establish the owned PostgREST role boundary, not the
hosted gateway or global API key. All 19 focused local cases now pass, zero
skips; the dated [acceptance receipt](../../DB-04-API-BASELINE-ACCEPTANCE-2026-10-17.md)
records provenance, repairs and remaining release/hosted gates.

After offline proof: review exact hosted target/context, obtain fresh complete
catalog/ACL evidence, reconcile every mismatch, freeze a forward migration and
rollback plan, then execute within existing Dashboard-only authorization. Rollback never drops accepted
tables/data, disables RLS or resets defaults. An uncertain write/commit response
requires original-operation/catalog reconciliation, not an automatic retry.
