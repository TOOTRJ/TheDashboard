# B1 closed catalog schema and source acceptance draft

Current-state note, 2026-10-13: the requirements below preserve the reviewed
design before native execution. The corresponding actor-only implementation
has one exact passing local fourteen-case run, after a reported zero-case
setup failure and separately reviewed variable-only repair. The dated
`B1-ACTOR-CATALOG-CONTRACT.md` records source pins, both original outcomes,
actual transfer sizes and unresolved CI/B2–B9 gates. This draft is not itself
an execution receipt or permission for broader native operations.

Historical draft status: **design only, pending root/peer agreement**, 2026-10-13. This refines
the actor-only plan. No SQL, role, container, test, database/provider request or
commit has been executed. Actor-only SQL/source-loader working drafts are now
being prepared under root's conditional authorization; they are not installed
or accepted. All seventeen B1 limits stay false; B2–B9 remain
closed. Nothing here authenticates recorder/reader packages, source receipts,
epochs, availability, original identities, complete journals or trading.

## Installation and privilege order

The trusted owned-fixture bootstrap precreates eight fake actor login roles,
`vn_jupiter_b1_installer`, and `vn_jupiter_b1_sealed_owner`. Installer and sealed
owner have no SUPERUSER/CREATEROLE/CREATEDB/REPLICATION/BYPASSRLS. Sealed owner is
NOLOGIN and has no membership edge. The bootstrap owns the anchor schema and
its two tables. Its privileged identity is an explicit trusted fixture root,
never an actor or restricted installer.

The restricted installer initially owns the preprovisioned B1 schema and may
create only the reviewed B1 objects there. After independent source/definition
acceptance, the bootstrap transfers B1 schema, tables, implicit types, indices
and all eight functions to sealed owner. It removes installer membership,
schema CREATE/USAGE, table and function grants. The installer has no ability to
replace/drop/alter the accepted guard after sealing. A prototype must test
these actual denials rather than infer them from a role name.

Actor grants are exactly B1 schema USAGE and EXECUTE on the two four-TEXT
entrypoints. Actors have no table/helper/anchor grant. Sealed owner receives
anchor schema USAGE and SELECT on exactly `installer_reference` and
`expected_functions`; it receives no anchor CREATE/ownership/membership or
write. This narrow protected read is the only foreign-schema exception. It is
needed by the security-definer entrypoints; it is not a general foreign-schema
capability. PUBLIC/helper EXECUTE and owned schema/table/type PUBLIC privileges
are removed explicitly. Existing PUBLIC TEMP is preserved. The bootstrap's
trusted authority is not claimed safe against its own compromise.

After sealing and independent definition acceptance, the bootstrap derives and
holds P/M/R/K and populates the nine excluded value cells. Computing current K
does not itself authorize storing it as gold. A source-derived expected schema,
function specification, owner/ACL boundary and runtime acceptance must pass
first. The external driver records this ordered acceptance independently of
the native guard.

## Exact logical root inventory

These are the complete expected roots. No overload, view, sequence, procedure,
aggregate, domain, enum, policy, rule, trigger, extension-owned app object,
operator, conversion, collation, text-search object or statistics object is
allowed in either namespace. Presence of an additional root refuses; a
1024-object bound is an overflow refusal, never an object sampling limit.

| Namespace | Kind | Exact logical name | Accepted owner |
| --- | --- | --- | --- |
| `vn_jupiter_actor_catalog_research_v3` | schema | same name | sealed owner |
| same B1 namespace | table | `actor_bindings` | sealed owner |
| same B1 namespace | table | `accepted_pins` | sealed owner |
| same B1 namespace | function | `_c14n(jsonb)` | sealed owner |
| same B1 namespace | function | `_binding_core()` | sealed owner |
| same B1 namespace | function | `_role_closure()` | sealed owner |
| same B1 namespace | function | `_installation_preimage()` | sealed owner |
| same B1 namespace | function | `_catalog_preimage()` | sealed owner |
| same B1 namespace | function | `_checked_actor(text,text,text,text)` | sealed owner |
| same B1 namespace | function | `verify_scoped_actor(text,text,text,text)` | sealed owner |
| same B1 namespace | function | `get_scoped_binding(text,text,text,text)` | sealed owner |
| `vn_jupiter_b1_fixture_anchor` | schema | same name | trusted bootstrap |
| same anchor namespace | table | `installer_reference` | trusted bootstrap |
| same anchor namespace | table | `expected_functions` | trusted bootstrap |

All four tables are ordinary persistent, nonpartitioned heap tables, no RLS,
replica identity DEFAULT, no rules/policies/triggers, no generated/identity
columns, no defaults, no inheritance and no storage/reloptions overrides.
Columns below are NOT NULL, in the listed ordinal order. All TEXT and TEXT[]
columns use the reviewed fixed database collation (UTF-8 fixture `C`); comparison
and ordering in guards additionally specify `COLLATE "C"`. OID is actual
`pg_catalog.oid`, bool is `pg_catalog.bool`, int4 is `pg_catalog.int4`, JSONB is
`pg_catalog.jsonb`, and TEXT/arrays are `pg_catalog.text`/`pg_catalog._text`.

| Table | Ordered columns |
| --- | --- |
| `actor_bindings` | `principal_binding_id text`, `session_user_oid oid`, `session_user_name text`, `owner_id text`, `run_id text`, `market_epoch text`, `profile text`, `capabilities text[]`, `installation_manifest_sha256 text` |
| `accepted_pins` | `singleton bool`, `actor_catalog_package_sha256 text`, `installation_manifest_sha256 text`, `catalog_manifest_sha256 text`, `role_closure_sha256 text` |
| `installer_reference` | `singleton bool`, `fixture_id text`, `database_oid oid`, `database_name text`, `server_version_num int4`, `actor_catalog_package_sha256 text`, `installation_manifest_sha256 text`, `catalog_manifest_sha256 text`, `role_closure_sha256 text` |
| `expected_functions` | `signature text`, `spec jsonb` |

Exactly six named unique/primary btree indices and ten named constraints exist:

| Table | Primary key / unique keys | Single named CHECK |
| --- | --- | --- |
| `actor_bindings` | `actor_bindings_pkey(principal_binding_id)`, `actor_bindings_session_oid_key(session_user_oid)`, `actor_bindings_session_name_key(session_user_name)` | `actor_bindings_shape` |
| `accepted_pins` | `accepted_pins_pkey(singleton)` | `accepted_pins_shape` |
| `installer_reference` | `installer_reference_pkey(singleton)` | `installer_reference_shape` |
| `expected_functions` | `expected_functions_pkey(signature)` | `expected_functions_shape` |

The four CHECK expressions are source-derived expectations, not an accepted
`pg_get_constraintdef` snapshot. They enforce canonical lexical IDs/hash text,
the four profiles, exact ordered capabilities, singleton=true, positive native
OID/version fields and the closed function-spec object shape/types respectively.
The source loader must freeze their exact expressions with the prototype. A
weaker/different expression refuses even if its current data happens to pass.

Implicit table composite types, their array types, primary/unique indices and
TOAST/index objects are permitted **only** as constructor-bound children of
these exact roots. Their original fixture OIDs and catalog association links
are retained in K. The trusted source acceptance checks their kinds, columns,
type links, index expressions/opclasses and owner against the reviewed DDL/PG17
constructor rules; it never accepts arbitrary extra children as a current
snapshot. Toast contents/statistics/files are not read. A missing, recreated or
misassociated child changes the fingerprint/refuses. No cross-database OID
stability or portability is claimed.

## Exact function source specification

Six helpers are PRIVATE SECURITY INVOKER. `_c14n(jsonb)` returns TEXT and is
IMMUTABLE; all other helpers return JSONB and are VOLATILE. Both public
entrypoints return JSONB, are VOLATILE SECURITY DEFINER and only have the four
TEXT IN arguments stated by the actor plan. All eight are PL/pgSQL normal
functions, CALLED ON NULL INPUT, non-leakproof, PARALLEL UNSAFE, COST 100,
non-set-returning, rows=0, no support function, no variadic/default/OUT/transform
arguments, `probin`/`prosqlbody` null. Exact argument names are fixed by source.
Every function has the same explicitly fixed local settings below, sorted by
setting name. Owner-only helper EXECUTE is never granted to actors or installer.

`expected_functions` has exactly eight source-derived rows. Its `spec` is
closed, with fields:

```text
signature, argument_type_names, argument_names, return_type_name, language,
kind, owner_role_name, security_definer, volatility, parallel, strict,
leakproof, returns_set, cost_text, rows_text, support_oid_text,
variadic_oid_text, default_argument_count_text, all_argument_types,
argument_modes, transform_types, binary, sql_body, local_settings,
body_sha256, source_package_sha256, execute_role_names
```

Type names are fully qualified builtin type names; nullable catalog absence is
literal JSON null, not an empty array/string. Execute role names are owner plus
the exact eight actor names only for the two public entries; helpers have owner
only. ACL grantor/grantee OIDs, grant options and actual owner/OID links also
enter K, independently of this logical source spec. Costs/rows/counters use
exact canonical strings, booleans are genuine JSON booleans. Function source
sha256 is the exact UTF-8 PL/pgSQL body between the source's fixed, unique dollar
delimiters; no whitespace stripping or rewriting is allowed.

The external loader must independently hash the original SQL package P and
extract these exact eight bodies/signatures/attributes from reviewed source,
reject duplicate/unknown declarations and retain the literal expected specs
before any installation query. It may not derive expected body hashes or
expected signatures from `pg_proc`, `pg_get_functiondef` or the just-installed
catalog. The bootstrap then compares actual `prosrc` UTF-8 sha256, complete
signature/type/language/attribute/configuration/owner/ACL facts with those
expected specs before inserting its protected expected rows and accepting K.
Every native guard repeats actual-versus-protected-spec comparison. A body,
overload, security-definer mode, strictness, local setting or grant drift
refuses; recomputing its new K or installing a changed accepted pin is not a
replacement for this independent source acceptance.

Source package P identifies reviewed bytes. The protected bootstrap reference
and immutable sealed ownership are the explicit trust roots. This is not code
attestation against a malicious trusted bootstrap, PostgreSQL binary or host.
It does not imply a caller's recorder/reader package was loaded from P.

## Closed catalog preimage, enumeration and ordering

K hashes compact sorted-key UTF-8 JSON of exactly:

```text
format, actor_catalog_policy_sha256, database_identity, invariant_runtime,
catalog_objects, default_acl_rows, database_role_settings, protected_roles,
bindings_core, expected_function_rows, role_closure
```

Format is `ga-jupiter-b1-catalog-manifest-v3`. The policy has no own digest cell.
`database_identity`, BindingCore and RoleClosure retain their closed descriptor
fields. Expected function rows sort by qualified signature byte order and
retain exact `{signature,spec}`. BindingCore excludes its stored M cell; the
other nine fixed pin-cell exclusions are unchanged. No further exclusions may
be selected by a caller. A reference/accepted table's singleton, database fields,
columns, constraints, ownership and ACL remain included; excluded values are
separately compared to the independently held reference on every call.

`catalog_objects` is the complete actual union of namespace, relation, column,
type, constraint, index, routine, trigger, policy, rule and dependency entries
for the roots and constructor-bound children. Enumerate actual owned namespaces
first and count the complete set, with no LIMIT. Reject unexpected kinds from
the other namespace-ownable PG catalogs listed below rather than omit them.
Each row is exactly `{kind,namespace,identity,oid,owner_oid,owner_name,attributes,
acl_is_null,effective_acl}`. Non-applicable owner/ACL is explicit null. Object
identities are qualified original names, with ordinal names for columns and
qualified identity arguments for routines; original object/dependency OIDs are
counter strings, not normalized away. Rows sort by
`(kind,namespace,identity,oid)` with text byte `C` order and numeric OID tie order.
Duplicate logical identities refuse. Independent ownable catalog rows also
require unique original OIDs in their kind. Column/dependency/index-detail
rows do not have independent PostgreSQL row OIDs: their `oid` is the original
parent relation/object/index OID, and identity retains ordinal or full
dependency tuple. Several such facts may legitimately share that parent OID;
no synthetic per-column or dependency OID is invented. A constraint has no
independent owner; an index-detail row's owner is null while its `pg_class`
relation row retains the actual relation owner.

The per-kind `attributes` object is closed:

| Kind | Included definition attributes |
| --- | --- |
| namespace | original namespace name |
| relation | relkind, persistence, access method name/OID, row type OID, toast OID, reloptions, tablespace OID, replica identity, RLS/forced-RLS, partition flag/bound, inheritance parents |
| column | relation OID, ordinal, name, type qualified name/OID, typmod, collation qualified name/OID, not-null, dropped, identity, generated, storage, compression, options, FDW options, default expression or null |
| type | kind, category, relation/base/array/element OIDs, dimensions, typmod, delimiter, by-value, length, alignment, storage, not-null, collation OID, default expression, input/output/receive/send/typmod/analyze/subscript function OIDs |
| constraint | relation/domain OIDs, type, key columns, foreign fields, deferrable/deferred/validated, index OID, parent OID, inherited/local/no-inherit, exact `pg_get_constraintdef(oid,false)` |
| index | relation OID, access method, key/total counts, unique/primary/exclusion/immediate/valid/ready/live/nulls-not-distinct flags, key columns, opclass/collation/options vectors, expressions/predicate or null, exact `pg_get_indexdef(oid,0,false)` |
| routine | full actual source-spec fields above, original language/argument/return type/owner/support OIDs, argument/default/config fields, exact prosrc SHA256, `pg_get_functiondef` text as additional actual fingerprint only |
| trigger | relation OID, function OID, name, type/enabled/internal, constraint/link fields, arguments bytes hex, columns/when expression/transition tables; expected complete set empty |
| policy | relation OID, command, permissive, roles, qualification/check expressions; expected complete set empty |
| rule | relation OID, type/enabled/instead, qualification/action; expected complete set empty |
| dependency | object/class/subobject and referenced object/class/subobject original OIDs plus dependency type, from `pg_depend` and current-database `pg_shdepend`, limited to source-declared roots/children and their system dependencies; shared role refs have referenced subobject `0` |

Stored ACL NULL is retained separately from its effective `acldefault` expansion;
NULL is never treated as an empty ACL. Expanded rows are closed
`{grantor_oid,grantee_oid,privilege_kind,grantable}` and sort by that full tuple.
PUBLIC is grantee OID `0`. Every actual grant option and ownership privilege is
checked. All relevant default ACL rows (owned namespaces and global defaults of
bootstrap/installer/sealed owner) retain owner OID, namespace OID/name or null,
object kind and expanded ACL; they sort by owner/namespace/kind/full ACL. Actual
defaults differ from NULL ACL semantics and both are fingerprinted.

PostgreSQL17 true-array type access follows its element type's privileges.
Array `acl_is_null` preserves the original stored array ACL state, while its
expanded effective ACL resolves the original element owner/ACL through the
included type-element association. Only the four base composite types receive
explicit PUBLIC revocation; attempting to GRANT/REVOKE the generated arrays is
unsupported. Independent native privilege APIs must verify both base and array
access for every actor/installer before K acceptance. This reflects the native
type rule rather than inventing independent array grants.

Unexpected namespace objects in `pg_operator`, `pg_opclass`, `pg_opfamily`,
`pg_collation`, `pg_conversion`, `pg_ts_config`, `pg_ts_dict`, `pg_ts_parser`,
`pg_ts_template`, `pg_statistic_ext` or extension ownership refuse. An active
event trigger affecting owned creation/DDL or uncontrolled dependency also
refuses at bootstrap/source acceptance. No global catalog body, unrelated
project contents, user role password, TOAST contents, table statistics or
process environment is disclosed. This is an owned empty fixture, not a query
recipe for a shared Supabase database.

`protected_roles` contains exact native role metadata for bootstrap, installer
and sealed owner, plus their membership edges, ordered by original OID/full
edge tuple. Actor RoleClosure is separate and still serves all eight callers.
The privileged bootstrap metadata is permitted only as the held trusted root;
it is never reachable from an actor. `database_role_settings` includes actual
current-database/all-database and relevant protected/actor/PUBLIC role setting
rows with exact sorted configuration strings. Unexpected duplicate setting
keys refuse. No catalog-definition formatting normalization strips meaningful
source bytes; fixed PG17/server-version/C-collation rules plus source expected
specs make changes explicit. Formatting portability remains outside B1.

## One union R and one shared invariant K

R is a deterministic union rooted at **all installed BindingCore actor OIDs**,
not the current caller. Traverse member→role edges to a deduplicated complete
structural closure even when INHERIT/SET is false, retaining every original
edge and its admin/inherit/set flags. This conservative superset refuses
unapproved structural/dangerous privileges; it does not equate every structural
edge with effective SQL access. Grantor metadata does not create reachability.
Relevant parameter ACL entries include all grants to the union and PUBLIC,
with full grantor/grantee/privilege/grantable fields. Baseline eight actors have
no membership edges or special parameter grants; any changed set refuses.
Complete-set node/edge/parameter bounds stay 64/256/64, no truncation.

Shared `invariant_runtime` is exactly the values of `server_version_num`,
`server_encoding`, `client_encoding`, `TimeZone`, `DateStyle`, `IntervalStyle`,
`standard_conforming_strings`, and `row_security`, plus the reviewed fixed
database encoding/collation/provider/locale/version attributes. Every function's
local SET values are exactly:

```text
DateStyle=ISO, YMD
IntervalStyle=postgres
TimeZone=UTC
client_encoding=UTF8
row_security=on
search_path=pg_catalog, pg_temp
standard_conforming_strings=on
```

The external bootstrap derives expected K under these same explicit fixed
settings; each public call's guarded function context independently checks them.
Server version/encoding/database metadata are native facts compared with the
held fixture reference. The function configurations themselves are source-pinned
and fingerprinted, rather than trusting a caller-set GUC. Setting rows/defaults
are checked as described above even if a function-local SET overrides them.

`session_user`, `current_user`, their OIDs, transaction/backend IDs, application
name, socket/port and statement/clock values are **not in K**. The public guard
checks actual session_user name/OID against its one scoped original held binding
on every call. Current user must be the sealed owner during the definer body;
it is a separate per-call identity guard. No SET ROLE, caller-supplied role name,
claimed package or per-call snapshot can change the independently held shared
K. All eight actors must produce the same observed K while retaining their
different independently verified native session identities.

## Required concrete acceptance additions

Before any fixture, root reviews the new SQL, external source loader, exact
source spec, full object manifest and expected DDL expressions. The later actual
owned fixture must prove source→installed-body/signature/config/owner/ACL parity
and reject a source mismatch **before** accepting K. A newly recomputed current
snapshot must not bless changed code. Exercise all eight actors against one K;
change only a caller identity to demonstrate independent per-call refusal.

Test explicit installer ALTER FUNCTION/schema CREATE/write/anchor write denial
after final sealing; direct actor/helper/anchor denial; source-body/strictness/
overload/config/ACL/constraint/index/type/implicit-child drift; NULL in each
position; unexpected object and complete-set overflow; PUBLIC parameter and
NOINHERIT/SET/admin edge drift; benign temp shadows; changed excluded pin or
pin replaced with a current drift digest. Actual fixture execution remains
blocked until root reviews concrete files. No result is claimed here.
CHECK/PK/UNIQUE formatting parity is established by temporary constructor
tables created only from the exact source-pinned table bodies/headers extracted
before installation. They are independent of the actual installed definitions
and use the pinned PostgreSQL17 constructor as an explicit trusted engine.
Exact owned constructor absence must be checked before accepting K; their
original hashes/counts/cleanup are recorded separately.

The fixture's internal M/R/K transfer is separately bounded at **1 MiB** per
serialized metadata frame, while public arguments/output stay 4096/8192 bytes
and the SQL literal helper stays 131072 bytes. One MATERIALIZED bootstrap
SELECT retains the original preimage and its native `_c14n` SHA; the host hashes
that same returned value, with no reinsertion or second read of mutable facts.
The server checks the full frame before transmitting it and the client checks
original received bytes. Refusal cannot become a positive acceptance. Actual
received/canonical byte sizes must be recorded when the fixture is authorized.
Producing and hashing a preimage allocates before that transmission guard;
there is no RSS, CPU preemption, five-second or hosted-transfer proof.

PostgreSQL17 primary references used to verify the native field boundaries:
[pg_proc](https://www.postgresql.org/docs/17/catalog-pg-proc.html),
[pg_auth_members](https://www.postgresql.org/docs/17/catalog-pg-auth-members.html),
[pg_parameter_acl](https://www.postgresql.org/docs/17/catalog-pg-parameter-acl.html),
[pg_default_acl](https://www.postgresql.org/docs/17/catalog-pg-default-acl.html).
The array access/grant boundary also follows the official
[PG17 ACL implementation](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/backend/catalog/aclchk.c).
They inform this planned PG17 representation; they grant no database authority.
