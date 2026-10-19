# R3-03A2 B1 actor/catalog-only freeze proposal

Current-state note, 2026-10-13: this document preserves the approved proposal
and its pre-execution requirements. Subsequent reviewed actor-only SQL and
tests passed one exact local fourteen-case native run after a separately
reported setup failure and variable-only repair. See
`B1-ACTOR-CATALOG-CONTRACT.md` and the dated source-bound evidence there.
Historical descriptors keep their original meaning; B2–B9 remain closed.

Historical proposal status: **actor-only scope approved; concrete schema refinement pending review**,
2026-10-13. This is the smallest B1 experiment, separated from the lifecycle
proposal. It changes no A1/source/model/parser/native code, grants no source or
economic operation, creates no database/role/container, runs no test, contacts
no provider/cloud target and commits nothing. Existing research flags remain
false. B2–B9, trusted reader delivery, full journals, packet/fence/closure/seal
admission, warmup, model restoration, resource/hosting and trading remain closed.

The exact proposed descriptor is
`R3-03A2-B1-ACTOR-CATALOG-POLICY-PROPOSAL.json`. Its sorted-key, compact UTF-8
canonical JSON is **12,338 bytes**, SHA-256
`2618f8f4239460112df4b7b21138f103f265353233d35e779e874431057a7c06`.
The pretty-file digest is recorded externally; it is not the canonical policy
digest. The prior 3,444-byte `af249638...` proposal remains historical in section
11 of the lifecycle document. The complete v2 pretty descriptor is preserved
byte-for-byte in `R3-03A2-B1-ACTOR-CATALOG-POLICY-PROPOSAL-V2.json`, SHA256
`c1e25e560cb14fb2b3eb14117024c708febf4a8acfd832fa5d9d52ac022ce5de`;
its historical canonical 6,978-byte digest is
`b6acdad734a2b25f066ac97e7238dbf33ca5674b09a67ebc4053c4f5894515e3`.
No native wire was issued under either proposal. This forward v3 adds the
closed catalog schema, independent source acceptance, sealed ownership and
all-actors/shared-runtime normalization. It does not broaden B1 authority.
A changed descriptor requires review/new hash. Its concrete schema is in
`R3-03A2-B1-CATALOG-SCHEMA-DRAFT.md`. Root has allowed actor-only prototype
working changes after these refinements, with **no actual PostgreSQL fixture
before concrete SQL/manifest/source-verification review, no stage/commit**.
No SQL/prototype or fixture has been created by this document-only revision.

## Exact two-entry boundary

Namespace: `vn_jupiter_actor_catalog_research_v3`.

```text
verify_scoped_actor(text, text, text, text)
  = (owner_id, run_id, market_epoch, required_capability)
get_scoped_binding(text, text, text, text)
  = (owner_id, run_id, market_epoch, requested_binding_id)
```

Both are explicitly **CALLED ON NULL INPUT**, never PostgreSQL `STRICT`.
Their first checks reject any NULL argument with fixed SQLSTATE `22023` and a
fixed safe invalid-input message. A NULL cannot bypass the body and return a
misleading NULL result. Subsequent nullable predicates use an explicit
`IS DISTINCT FROM TRUE` failure test where appropriate; SQL unknown is not
success. Null cases for each argument are required actual acceptance cases.

All boundary values are actual TEXT, then exact lexical checks validate UUIDs
and the closed `verify_actor, read_scoped_binding` capabilities. UUIDs are
canonical lowercase, with no trimming, case conversion or cast-to-uuid followed
by normalization. No default arguments, variadics, wrappers or other overloads
are accepted. A caller's explicit CAST yielding identical TEXT is indistinguish-
able at this boundary; this API does not prove its previous lexical/type origin
or claim to forbid that CAST. It validates the final values and exact qualified
signature. This is distinct from the raw-provider integer-token grammar.

The descriptor's output field sets/formats are closed. Evidence resolves real
`session_user` name/OID plus the private held binding, B1 capability and catalog.
It returns no clock, process/stdio/environment, provider body or secret.
OIDs are canonical unsigned-32-bit counter strings; role names fit PostgreSQL's
63-byte bound. All seventeen `limits` fields are literal false. Its package hash
identifies the actor/catalog SQL artifact, not the client's recorder/reader
process. An actual lab identity check is not an original packet/native/model
receipt. Found lookup requires complete Evidence; absence requires null Evidence.
Known foreign-scope/actor bindings and random missing bindings return the same
absence representation. Catalog/actor drift raises one fixed safe refusal,
never a scope/role fallback or arbitrary diagnostic.

## Trusted fixture bootstrap versus restricted installer

PostgreSQL `CREATEROLE` is not namespace- or prefix-scoped. The future **trusted
owned-fixture bootstrap** creates the eight public-fake login actors, installer
and required owned schemas/ownership/initial grants. It can perform the necessary
fixture-local privileged setup; this is a separate trusted role, not an actor or
the restricted installer. No shared database, Supabase user, host account or
global CLI setting is touched. The bootstrap is limited by the owned isolated
fixture boundary, not a fictional per-prefix CREATEROLE grant.

The restricted installer has **no CREATEROLE, SUPERUSER, CREATEDB, REPLICATION
or BYPASSRLS**. It creates only B1 objects in the bootstrap-provisioned namespace
during installation. The bootstrap independently validates the reviewed source
specifications, then seals B1 ownership to a nonprivileged NOLOGIN owner and
removes installer membership/ownership/create/write. The sealed guard owner
alone gets exact USAGE+SELECT on two private anchor tables, without anchor
create/write/ownership/membership. That is a narrow protected-read exception,
not a general foreign-schema capability. Four profile labels per each of two fake
scopes are recorder, reader, sealer and control. Each receives only B1 verify/get
execution, no helper/table-write/package/binding provisioning capability.
Profile labels do not grant the broader lifecycle capabilities. The sixteen-
binding limit is a fail-closed bound; the baseline has exactly eight actors.
Default PUBLIC/helper execution is removed only for owned B1 objects; shared
PUBLIC TEMP is preserved. Benign temp sentinels must not redirect qualified
checks. Both entrypoints use explicit qualified app/system objects and a fixed
`pg_catalog,pg_temp` search path.

## Closed hash preimages and independent pin ordering

Let `C14N(x)` mean compact UTF-8 JSON with sorted keys and reviewed exact scalar
encoding; list ordering is explicit below. `H(x)=SHA256(C14N(x))`. These are
proposal semantics, not a claim that an implementation already reproduces them.
All source hashes are externally measured; no SQL source embeds its own digest.

1. **P:** externally hash the source-bound actor/catalog SQL package. It is a
   source artifact, without a field containing its own hash. The trusted
   bootstrap retains this separate expected package reference.
2. **R:** derive full RoleClosure from actual catalog facts. Its exact preimage is
   `{format, actor_catalog_policy_sha256, nodes, edges, parameter_privileges}`.
   R is the complete deterministic union rooted at **all** installed binding
   actor OIDs, so all eight actors compare the same R. Parameter privileges
   include reachable roles and PUBLIC; grantor metadata alone is not a root.
   Nodes sort by numeric OID; edges sort by
   `(roleid,member,grantor,admin_option,inherit_option,set_option)`; parameter
   privilege rows sort by their full five-field tuple. No R digest is embedded
   in this preimage. Definitions for all three row types are in the descriptor.
3. **M:** installation manifest preimage is exactly
   `{format, actor_catalog_policy_sha256, actor_catalog_package_sha256,
   database_identity, scopes, bindings_core}`. Package SHA is P, already known.
   Scope rows sort by `(owner_id,run_id,market_epoch)`; BindingCore rows sort by
   `principal_binding_id`. BindingCore has exactly the six descriptor fields;
   **installation_manifest_sha256 is absent from BindingCore/M**. DatabaseIdentity
   has exactly fixture ID, database OID/name and server version number. Formats
   are fixed `ga-jupiter-b1-role-closure-v3` and
   `ga-jupiter-b1-installation-manifest-v3` respectively. The fixture identity is
   bootstrap held, not caller supplied.
4. **K:** derive the source-bound complete owned catalog fingerprint from actual
   schema/table/column/type/constraint/index/trigger/function definitions,
   ownership, ACL/default ACL, BindingCore data, complete role/parameter facts
   and the **shared invariant** database/runtime configuration. The exact
   root/constructor-child inventory, per-kind attributes, ACL semantics,
   ordering, fixed GUCs and independent expected-function specs are now defined
   by the separate concrete schema draft and forward descriptor. Transient
   session_user/current_user/OID/transaction/activity identity stays outside K
   and is independently checked per call. Concrete SQL must reproduce this
   manifest and receive source review before fixture/code acceptance;
   incomplete/hash-only or arbitrary object subsets cannot pass. K contains no
   value cell from the exact exclusion list below. The containing table/column
   definitions, owners, ACLs and protections remain included.
5. **Before accepting K**, the external source loader derives the exact eight
   function bodies/signatures/configuration/attributes and table/constraint/
   index/child constructor expectations from reviewed SQL bytes. Actual native
   definitions/owners/ACLs must independently match them. No current catalog
   snapshot or `pg_get_functiondef` value becomes its own expected source.
   The bootstrap seals ownership and then stores the **independent expected
   tuple `(P,M,K,R)`** in its
   private `vn_jupiter_b1_fixture_anchor.installer_reference`. The restricted
   installer and actors cannot write/replace that reference or own its schema.
   `accepted_pins` and the full InstalledBinding rows are then populated; the
   latter's installation hash equals M. A source-bound external fixture driver
   independently records/rechecks the bootstrap references and actual schema.

The only excluded catalog **value cells** are exactly:

```text
vn_jupiter_actor_catalog_research_v3.actor_bindings.installation_manifest_sha256
vn_jupiter_actor_catalog_research_v3.accepted_pins.actor_catalog_package_sha256
vn_jupiter_actor_catalog_research_v3.accepted_pins.installation_manifest_sha256
vn_jupiter_actor_catalog_research_v3.accepted_pins.catalog_manifest_sha256
vn_jupiter_actor_catalog_research_v3.accepted_pins.role_closure_sha256
vn_jupiter_b1_fixture_anchor.installer_reference.actor_catalog_package_sha256
vn_jupiter_b1_fixture_anchor.installer_reference.installation_manifest_sha256
vn_jupiter_b1_fixture_anchor.installer_reference.catalog_manifest_sha256
vn_jupiter_b1_fixture_anchor.installer_reference.role_closure_sha256
```

No actor chooses exclusions, expected digest or snapshot. On **every** call,
recompute R/M/K, require their equality to the independently held bootstrap
references, require accepted_pins exactly `(P,M,K,R)`, and require every stored
binding installation hash M. Thus changing an excluded accepted/binding pin
refuses; it cannot become a newly accepted expected value just because it was
excluded from its own hash. Replacing that pin with a digest of current drift
also refuses against the old held reference. The reference's definition/owner/
ACL/protection is fingerprinted; its fixed self-digest values stay excluded.
The trusted bootstrap reference is the trust root, not another self-hashed row.
No security against a compromised trusted bootstrap/privileged administrator or
arbitrary same-process mutation is claimed. Caller and restricted-installer
write denial plus external source/reference checks are concrete required tests.

The bootstrap's exact read-only `expected_functions` rows are fully included
in K and repeated actual-versus-expected checks. They retain source-derived
body/signature facts; their expected values cannot originate from the just
installed catalog. The native guard itself is protected by sealed ownership;
source hashes alone are not code/runtime attestation.

No cycle exists: P precedes M; R has no digest of itself; M omits its embedded
binding hash; K omits the nine fixed value cells; separately held expected pins
are compared rather than used as new actual gold. This pattern does not prove
the wider D4 packet Result/Receipt/Journal construction.

## Full bounded role closure

Node fields are exact descriptor RoleNode fields. R roots all installed actors
and retains their complete structural closure, including PUBLIC parameter
grants. This conservative inventory is separate from effective access, which follows
actual membership and SET ROLE possibilities, not only `rolinherit` or current
role. Edges retain all six actual `roleid/member/grantor/admin/inherit/set`
properties. Grantor metadata alone does not make that grantor an accessible role;
the implementation must use the reviewed PostgreSQL membership semantics.
All reachable actor roles/edges and relevant parameter grants must be examined,
including privilege paths through NOINHERIT with SET ROLE. Dangerous effective
SUPERUSER/CREATEROLE/CREATEDB/REPLICATION/BYPASSRLS, unauthorized schema/data/helper
access, membership administration or privileged parameters refuse. Changes to
benign accepted metadata also fail the immutable fingerprint; no drift adoption.

Limits are **64 role nodes, 256 membership edges, 64 parameter ACL rows**, plus
the separate 1,024 object/16 binding limits. These are independent complete-set
bounds, not `LIMIT n` sampling. Overflow refuses. The actual role/config/ACL
normalization and complete object manifest are specified in the concrete schema
draft and must be externally source bound in
the eventual fixture and reviewed before acceptance. No secret `rolpassword`
data is returned or needed; no role credentials are read, copied or rotated.

## Smallest actual acceptance proposal

Only after root authorizes B1 SQL/prototype:

1. Own cached PostgreSQL fixture bootstrap, restricted installer and eight fake
   actors; image/runtime/source/descriptor/package/reference pins recorded.
2. Positive verify/get for each profile in both scopes with exact closed output;
   all false limits and absence versus foreign binding behavior checked.
3. Each of four NULL positions actually calls the public body and raises the
   fixed safe refusal. Catalog `proisstrict=false` and exact four-TEXT signatures,
   no default/variadic/overload, are independently checked.
4. Canonical text positives including an explicit CAST to the identical TEXT;
   whitespace/case/UUID/capability/wrong final text negatives. This proves final
   value validation, not pre-cast provenance.
5. Actual role rename/recreation/OID, inherited/SET/admin membership, dangerous
   attribute/parameter and node/edge overflow negatives; full closure fails
   without truncation. No global/shared role capability is introduced.
6. Source-bound catalog/owner/ACL/default-ACL/helper/constraint/index/trigger/
   binding and excluded-pin changes refuse, including a pin set to a newly
   computed drift digest. Restricted installer/actor cannot change bootstrap
   references. Independently verify exact preimages/no digest self-reference.
7. Benign temp-shadow sentinels never execute; private writes/provisioning/helper
   invocation deny; shared PUBLIC TEMP remains unchanged.
8. Confirm no B2–B9 table/API/grant/packet/fence/journal/closure/availability/seal/
   model effect; safe error/output disclosure; exact owned cleanup.

These are **planned** cases. There are no current B1 SQL or test results.
The future fixture uses sanitized pinned runtime, cached reviewed image,
network none/no host ports/mounts/application secrets and exact owned cleanup.
B1 cannot close D5 capacity, genuine-clock/source deadlines, provider/reader
provenance, 915-minute warmup, model joining/restoration or worker activation.
