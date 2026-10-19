# B1 actor/catalog local native contract — 2026-10-13

The exact reviewed actor/catalog-only prototype passed **14 actual owned
PostgreSQL cases, zero failures/errors/skips, 36.448576082941145 suite seconds**.
Seven source-only checks passed in 0.004 seconds at the same SQL pin. The first
native attempt failed in setup with SQLSTATE `42703` and ran zero cases; it is
retained below. This result establishes the tested local fake-actor/catalog
behavior. It issues no source, journal, clock, reader, model, hosted or trading
authority and is not acceptance of ordinary CI on another platform.

The worktree is `codex/dashboard-v3-native-lifecycle-design`, based on frozen
A1 commit `45d2b7aabbb889f4ff628c02a1864e7206192a0d`. Every file in this slice is
new; no frozen A1, acquisition, source, transport, parser, model, SEC06, legacy
v2/v5 or application file was edited. No cloud/provider request, migration,
hosted activation, dependency installation, stage/commit or push is part of
this execution receipt. A commit requires the separate final slice review.

## Exact accepted source and descriptor

Paths below are relative to `services/vonneumann`.

| File | SHA256 |
| --- | --- |
| `db-contract/research/jupiter_actor_catalog_v3.sql` | `84b3167c6626911fd231f2eeb337e1df4ab645a89c723017ecb169cdabf93cad` |
| `db-contract/research/actor_catalog_v3_source.py` | `ffc56bfefdc405cad7a3d61ed8f3d7206ae79105c9e5a5a15f6a677fade355b3` |
| `tests/test_actor_catalog_v3_source.py` | `a24765bdc7016e9f124cd4e2235d848afed759d7c6351f78dbfa3f88c15081a3` |
| `tests/postgres/actor_catalog_v3_fixture.py` | `29a5097b744cddbd0350e5eaaf122628a6bae62b6d64ad77be0e7c83cd8affa4` |
| `tests/postgres/test_actor_catalog_v3.py` | `a28b16e0c0b6033381101fa8cb7b52b64181464f198c7e6c1e54e4ffe6e42923` |
| `research/b1-actor-catalog-owned-native-2026-10-13.json` | `5cc3ae3cb5f9e358aeb1939ff5eb18f86779c4acb05b52c63b0eff0d816eaf50` |

The current v3 descriptor's sorted-key compact UTF-8 JSON is **12,338 bytes**,
SHA256 `2618f8f4239460112df4b7b21138f103f265353233d35e779e874431057a7c06`.
Its pretty file is `R3-03A2-B1-ACTOR-CATALOG-POLICY-PROPOSAL.json`, SHA256
`468b195e5789e8df0cc9dfd26bcc76b57911f9d7268a1a7ad77e4f89eceb2351`.
The archived v2 pretty file remains byte-identical at `c1e25e560cb14fb2b3eb14117024c708febf4a8acfd832fa5d9d52ac022ce5de`;
its 6,978-byte canonical digest is `b6acdad734a2b25f066ac97e7238dbf33ca5674b09a67ebc4053c4f5894515e3`.
The earlier 3,444-byte proposal also retains its historical meaning. No wire
is silently relabeled as another descriptor, source package or authority.

## Actor-only boundary and independent acceptance

The only actor entrypoints are exactly four-TEXT
`vn_jupiter_actor_catalog_research_v3.verify_scoped_actor` and
`get_scoped_binding`. B1 grants only `verify_actor` and `read_scoped_binding`.
The eight fixture actor login roles span two fake owner/run/market scopes;
their recorder/reader/sealer/control profile labels do not grant those future
operations. Calls bind the actual `session_user` name and original role OID
to the installed original binding, scope and capability. A requested binding
outside that actor's scope and an unknown UUID both produce absent evidence;
they do not reveal another scope's binding contents.

Both entrypoints are `CALLED ON NULL INPUT`, with an explicit first NULL
refusal. Their canonical UUID/capability lexical checks apply to actual final
TEXT values without trimming or normalization. PostgreSQL cannot determine
whether a caller explicitly cast another value to the same final TEXT; the
equivalent explicit CAST case is accepted within that declared boundary.
Output bounds remain 8,192 bytes and public scalar bounds remain 4,096 bytes.
SQL errors expose fixed safe refusal messages, rather than private catalog
contents or credentials.

The trusted owned-fixture bootstrap creates the fake actors, restricted
installer, sealed NOLOGIN nonprivileged owner and private reference namespace.
The installer initially creates only the B1 objects. Before installed helper
output can become a baseline, the external loader checks the externally held
reviewed SQL package P, closed eight function headers/bodies and four table
constructors. Native body/signature/configuration/owner/ACL checks compare
those independently extracted source expectations. Four comparison tables
are built from the held source constructors, with CHECK/PK/UNIQUE/column/index
semantics compared against the real installed objects. Every original
comparison parent/type/constraint/TOAST/index child is confirmed absent before
accepting K. This explicitly trusts the pinned PostgreSQL17 engine constructor;
it is not independent engine or image-binary attestation.

Final ownership is sealed. The installer loses ownership, membership, schema
create/write, private/table/helper access and guard replacement ability. The
sealed NOLOGIN owner has only the exact anchor USAGE/SELECT grants needed by
the guard; actors have only B1 schema USAGE and the two entrypoint EXECUTEs.
Base composite PUBLIC privileges are revoked. Stored NULL array ACLs remain
NULL and effective array access is derived from the element type as PostgreSQL
17 actually does; the implementation does not invent an array GRANT.

R is the complete deterministic union rooted at all eight installed actors,
with full structural membership edges and effective PUBLIC parameter grants.
M covers the closed source/package/database/binding-core installation inputs.
K covers the closed owned catalog, source-derived expectations, owners, ACLs,
definitions and invariant runtime configuration. Nine specifically enumerated
stored digest value cells are excluded to avoid self-hash cycles; their
containing objects and protection remain included. Each stored excluded pin
must equal the separately held bootstrap reference. Recomputing a changed
catalog and writing its digest cannot make the changed code a new baseline.
All eight actual actor sessions reproduce one shared K while their actual
identity/OID checks remain separate; transient caller/transaction identity is
not part of shared K. Trusted bootstrap/admin/host/engine compromise is outside
this bounded prototype's trust claim. A source digest alone is not attestation
of the real worker, provider or execution environment.

Every native evidence limit was decoded and checked with **`value is False`**,
including the absent-lookup result. The seventeen exact keys are
`provider_attested`, `calibrated_clock`, `original_identity_registry`,
`epoch_registry`, `source_freshness`, `capture_retention`,
`native_source_admission`, `committed_packet_readback`, `terminal_resolution`,
`availability_authority`, `complete_inventory`, `history_seal`,
`model_native_join`, `lease_authority`, `hosted_authority`, `running_authority`
and `live_trading_authority`. B1 does not emit a successful source admission,
lease, receipt, terminal closure, journal position, minute seal or model event.

## Actual native cases

Each row corresponds to one real test method in the frozen native module;
all fourteen passed. Several methods include multiple controlled subcases.

| Case | Actual boundary exercised |
| --- | --- |
| PUBLIC parameter privileges | PUBLIC parameter grants remain in the all-actor union and drift refuses |
| Actor and installer access | Private reads/writes, helpers, replacement and sealed-owner assumption deny |
| Eight actual sessions | Genuine fresh role connections share K, differ in actual identity, and emit literal-false limits |
| Final TEXT | Canonical values, an equivalent explicit CAST, lexical/type-boundary and invalid-capability refusal |
| Complete role bound | Complete 64-node closure accepts; 65 nodes refuse rather than truncate |
| NULL handling | Each of four NULL positions in both entries reaches the fixed body refusal; neither entry is STRICT |
| Excluded pins | Changed accepted pins and a current drift digest cannot bless a modified catalog |
| Scoped lookup | Own evidence is found; foreign and unknown requested UUIDs have the same absent disclosure |
| Source and guard | Source/body mismatch and native guard drift refuse independently of caller claims |
| Exact namespace | Extra roots, overloads and B2–B9 capabilities refuse |
| Role identity and authority | Rename, dangerous role attributes and SET-membership changes refuse |
| Function and ACL | STRICT header and helper EXECUTE-ACL drift refuse |
| Temporary shadow | Qualified guards resist temp shadows while shared PUBLIC TEMP remains unchanged |
| Original role OID | Dropping/recreating the fake role cannot reuse its original binding through the new OID |

The node-bound case used and cleaned only its exact 57 additional uninstalled
fake support roles within the owned database. Role recreation and scoped
`DROP OWNED` applied only to the fixture's fake role.
The 64-node positive case exercises the private `_role_closure` builder under
the test operator; the accepted public baseline remains eight actors and
refuses membership drift.
The 256-edge, 64-parameter
and 1,024-catalog-element complete-set bounds are guards, but this fourteen-case
run does **not** prove all their overflow branches, exhaustive native language
or catalog equivalence, concurrency, hostile-admin isolation or worst-case
CPU/RSS bounds.

## Original run evidence and cleanup

Both runs used reviewed CPython3.12.14, an empty child environment with fixed
PATH/PYTHONPATH and standard dotenv/bytecode disablement, explicit native opt-in,
an exclusive empty mode0700 Docker configuration and the explicit local socket
`unix:///Users/redjester/.colima/default/docker.sock`. The original daemon ID
`7e62dd69-3357-4ce0-8b18-f1e54f3226d8` / `colima` was checked before and after.
The cached `public.ecr.aws/supabase/postgres:17.6.1.095` image was Linux/arm64,
PostgreSQL17.6; its observed local image ID and RepoDigest were
`sha256:965e2dfb5a23a0d6541b6106541e777b303656ebabd4e878746b189d550c0a66`.
No registry request was made. The existing harness used `--pull=never`, network
none, no host ports/mounts, read-only root, PostgreSQL user, dropped capabilities,
no-new-privileges and 1 CPU/512 MiB. These settings are not proof of actual
worst-case memory usage or hostile-process isolation.

The first actual run at SQL `3a30d8a94f5b25436cdb426b017d53a5d858e4b3239629e09a332177b7fd4845`
discovered fourteen cases but **ran zero**, with one `setUpClass` error,
23.095487541984767 suite seconds, exit1. SQLSTATE `42703` arose when the
`_catalog_preimage` PL/pgSQL anchor variable `r` shadowed SQL alias `pg_roles r`.
No bootstrap M/R/K receipt returned; intermediate local values are not invented
or reported as partial acceptance. Root and security approved only renaming
that function's PL variable/INTO target and genuine anchor-field references
to `anchor_ref`. All SQL table aliases, predicates, definitions, grants,
manifests, bounds and every byte outside that function remained unchanged.
Held SQL hash constants were updated in the source test/fixture; the loader
and native test bytes were unchanged. Seven source checks then passed once
in 0.004 seconds. A separate explicit approval preceded the next native run.

The accepted run at the current source pins ran **14 PASS**, zero skips, in
36.448576082941145 suite seconds; its controller took 36.53464550001081 seconds.
The 600-second whole-process supervisor did not fire. Passive observation
retained each helper's original returned frame digest/size without issuing
another query, retry, clock or receipt. The MATERIALIZED query construction is
pinned by the helper/controller source; there was no separately recorded
execution-query byte trace and none is claimed after the fact.

| Original frame | Canonical preimage bytes | Original received frame bytes | SHA256 |
| --- | ---: | ---: | --- |
| M | 3,713 | 4,013 | `0fc524cbc04649731d70fd6afaad26941131538cd9908bf4426a6be408bcc555` |
| R | 2,024 | 2,352 | `e06404e636029645274adbcb2bdd5d8d39bb1678fca257df0912d9b437678cd8` |
| K | 202,971 | 215,899 | `7d3be42b7b7a34cd24d2317686d608a59face6d8fa92b5b64fc3f35b706efd61` |

One original MATERIALIZED SELECT per helper returns the preimage/native hash;
the host verifies that same original value. The whole serialized frame is
bounded at **1 MiB before server transmission and on client receipt**. K's
measured 215,899-byte frame exceeds the former 131,072-byte literal feasibility
limit; this confirms why the reviewed original-frame transfer was needed.
The literal cap and public bounds were not widened. Metadata construction and
hashing allocate before that transfer guard; no total RSS, CPU preemption,
five-second packet deadline, source cadence or hosted transfer proof follows.
The public receipt records frame digests/sizes and constructor hashes/counts;
publishing the full original K preimage is unnecessary.

| Evidence | Original private receipt SHA256 | Original log SHA256 | Controller SHA256 |
| --- | --- | --- | --- |
| First zero-case failure | `6fa6ce0925547846163b705df6348254737d5adf9bac388939cebe5bdcc1bda2` | `e23da6a772bfa21065f5b64353700beffc71346775ff974c88bdc0a9a534a5b1` | `0724c4b66148dd3213c79687ffaf3cc543c65aebd2871233cec01ffb2d0dfe93` |
| Current fourteen-case pass | `e38f337f34b52bc54945d110a9185a50b03518fe1d3d4a1d135556ff111e1881` | `8365a89efa2e510316347601f273f537d3d268909c7b2c7bce926cb3601cf41e` | `3f5243c8db448ca26e2f6fd8a9e4f25e2ad6f05b5fc2af5b7ad06e7930e9e401` |

Original mode0600 evidence remains respectively in
`/private/tmp/dashboard-b1-actor-native-20261013-ia_etqto` and
`/private/tmp/dashboard-b1-actor-native-20261013-5ddyb665`; the failed original
SQL was preserved separately. The exact original containers
`17d6b12b8b31416cc97944a277f30ef9d8e2d2791caef7ba5739ca2425b0a16f`
and `f3c8a99e7d5af6e9c15938585a888b1c94d5bad466d0c5d39c345c164bf220a9`
were removed through normal label/ID-owned cleanup. Successful exact-ID queries
confirmed both absent after the correct daemon rechecks. Both empty Docker
configuration directories were removed by original descriptor/name/inode
ownership checks. No other process, container, configuration or credential
was selected. The public receipt preserves original IDs and all case outcomes.

The earlier pure-test six-pass/one-mutator-subcase failure also remains in the
public evidence. Its first-occurrence string replacement had changed a table
constructor instead of the intended function header. The reviewed test-only
repair targeted exactly the intended header and asserted the unchanged
constructor; it did not repair SQL, loosen source policy or imply a native
installation. Historical checks are not relabeled as the current acceptance.

## Required release and next native gates

Two concrete **CI portability prerequisites remain unresolved** in the frozen
accepted source. The fixture presently requires observed RepoDigest `965e2d…`
from this locally cached ARM image. The current GitHub direct preparer uses the
approved Linux/amd64 leaf manifest
`sha256:4c087262afbfbb47da86e2863a52d7e424eb21ab589f732d77eeaab51be8e521`
and config `sha256:972aabc75779f6e535f87e1669f36edbab02cdf8bf3f47d13579963c119adefb`;
its store may record only that leaf RepoDigest. A forward separately reviewed
fixture-only identity contract must support the independently approved store/
platform evidence. It may not fabricate the `965e2d…` marker, infer amd64
acceptance from this local ARM result or widen source/runtime authority.

The current class skip reason, `Requires owned PostgreSQL opt-in and concrete
review`, is outside the current `scripts/check-worker.py` `OPT_IN_REASONS`.
Ordinary CI would classify that opt-out as unexpected. A separately reviewed
fixture-only revision must use an exact canonical opt-in reason or a narrowly
tested helper allowlist. This receipt preserves the accepted current source
and does not silently edit either portability boundary after testing.

After those fixture-only release prerequisites, the next native work is still
the independently versioned B2–B9 design/code/test sequence: real principal/
package/epoch bindings; original pre-I/O reservations and identity registries;
durable safe captures; native guarded original admission; unknown-outcome
reconciliation and distinct terminal closure/tombstones; trusted original
reader availability; complete control/Stop/refusal journals and seals; then
an explicitly reviewed source/model/native bridge. The pure A1 five-kind
supplied-witness format cannot masquerade as the proposed full sixteen-kind
native journal or authenticate these missing dependencies.

D5 full capacity/duration remains closed: 915 minutes of four source writes
alone use 3,660 of a 4,096-entry journal, leaving only 436 for every control,
fence, epoch, closure and seal; minute renewal alone would add about 915 rows.
The 8 MiB/4,000-result process cache is not a 915-minute durable-retention proof.
Any forward capacity, paging, renewal, archive-dispatch or source-history policy
requires separate review rather than a silent expansion of frozen bounds.
No full ordinary/hosted CI, long warmup, genuine-clock/source freshness,
worst-case resource, production worker, hosted migration, wallet or live-trade
acceptance is asserted by the fourteen passing local cases.
