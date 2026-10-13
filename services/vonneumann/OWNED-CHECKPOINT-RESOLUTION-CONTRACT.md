# Factory-owned checkpoint resolution

This slice removes repeated full Python audits only for an unchanged checkpoint
that this process has already created and fully validated. It changes the Python
implementation of the original portable v2 eleven-slot and thirteen-slot
checkpoint factories. Their formats, wire policy, size limits, model, and complete
untrusted manifest validators retain their original meanings. A resolved view is
still a detached JSON object. The slice grants no provider, lease, receipt,
restoration, native admission, or running authority.

The local branch is `codex/dashboard-owned-checkpoint-cache`, based on
`b1ab59f4e6d5ae9a134a21235ba9a7f4343332fd`. That parent contains the separate SEC-06
TLS work. The cache change consists of exactly the two checkpoint modules, the
new dedicated test, the pre-change golden fixture, and this contract. Its commit
must exclude TLS files so it can be adopted independently of that separate work.

## Ownership and validation

Each module holds a private `WeakKeyDictionary` keyed by the exact
`ActiveCheckpoint` object created by its factory. Registration happens after all
existing candidate checks, full `resolve_manifest` validation, independent
expected-state comparison, and bounded encoding have succeeded. A failed factory
cannot register a result. No hash, owner/run/revision tuple, successful untrusted
resolution, restored object, or equal object confers registration.

The frozen ownership value retains only the original manifest bytes, expected
JSON bytes, component tuple, and each original component's bytes. It holds no
capture back-reference. A reuse requires the exact checkpoint type; the exact
same original manifest, expected, and component tuple objects; the complete
original component count; exact `TypedComponent` types; and each component's exact
original byte object. These checks run before every reuse. An equal replacement
byte object or a replaced, missing, reordered, duplicated, or changed component
tuple takes the full resolver path. Full successful resolution never refreshes or
promotes the ownership proof.

Both paths return a detached object. Reuse calls `json.loads` on the original
validated expected bytes rather than sharing a mutable graph with transport
callers. Ordinary `resolve_manifest` remains independent of this registry and
still checks every supplied component. Both original `resolve_manifest`,
`prepare_transport`, and `component_updates` function bodies were compared against
the parent source and are unchanged. Candidate-to-capture and prior-state
comparisons, complete original operations/history/evidence, wire capacity checks,
and the actual native checks remain in place.

Component tuple order has no new semantic rule: the original full resolver treats
a complete block tuple as a hash-addressed set. A reordered tuple therefore takes
the full path and may succeed if its original evidence is complete. Missing or
duplicated blocks and inconsistent or self-rehashed invalid semantic evidence
still refuse. This preserves the existing validator's acceptance contract.

This is a trusted in-process optimization. It is not a Python reflection, hostile
same-user process, shared-memory, or OS sandbox boundary. Source freshness and
current-head admission must still be independently checked where their existing
contracts require them. A weak registry follows the live capture's lifetime; it
is not a durable history store, retention policy, or physical memory benchmark.

## Pre-change wire evidence

Before modifying either checkpoint module, one network-denied process produced
`tests/fixtures/owned-checkpoint-cache-wire-baseline.json` from the unchanged
original portable v2 model: sparse and dense synthetic traces, two complete
windows each, search seed `0`, 35 commands per trace. The 70 records bind the
original complete candidate bytes, complete compact command bytes, manifest
bytes, and all thirteen ordered component byte hashes. The baseline was created
once from the stated parent and is not regenerated from the optimized code.

Baseline SHA-256:
`ba9985083f9d96cd8212e8e1642725a62bdc1f7cba2fdc61764b1e7a9ce2c2c3`.
The fixture records these original source hashes:

| Original file | SHA-256 before this slice |
| --- | --- |
| `provider_portable_checkpoint.py` | `cc897d41c55882113e02c295c355b7be8bc620a442667df5add5d33fadbd10c8` |
| `portable_partitioned_checkpoint.py` | `cb682e2acbddc321e4f282c23d69e22ab32b599162873d0e44fd87ea30407985` |
| `provider_portable_ga_model.py` | `e53486d35be4fdf642df85c33c9b9c278a82ba2016905a60e6870e59ae5df9ec` |

The model source is unchanged. Previous source-bound native, storage, browser,
and genuine-bar receipts retain their original Python source hashes. Their
acceptance must not be relabeled as testing this implementation. Any new runtime
package binding must include the changed checkpoint source bytes.

## Local verification and remaining release gate

The final dedicated `tests.test_owned_checkpoint_resolution` suite passed all
14 methods, zero skips, in 18.244 seconds using the pinned Python 3.12.14 worker
runtime, an empty child environment with dotenv disabled, and `deny_network`.
This includes the exact 70-command pre-change baseline comparison and focused
proofs for both factories: full first validation, detached views, unowned copies,
equal byte replacement, changed manifests/expected views/components,
self-rehashed semantic forgery, order/count/duplicate changes, component equality
versus object identity, nonexact types with custom equality/hash, weak-key
collection, raw full-validator coverage, and full unowned versus owned compact
transport equality. The preceding 12-method developmental subset passed in
4.389 seconds; it is not a separate final source version.

The existing offline `tests.test_portable_restoration` suite also passed all
16 methods, zero skips, in 38.370 seconds under the same isolated runtime. It
checks original next full/compact wire equivalence, all thirteen dependencies,
untrusted and rehashed graph refusal, decoder/import boundaries, current-head
identity lookup, retired identities, stopped holdings, and original uncertain
request reconciliation. No native or provider test, Docker operation, hosted
timing comparison, CI run, or remote mutation was performed by this cache slice.
The measured local unit-test durations are mechanics evidence, not a calibrated
speedup or hosted deadline guarantee.

The original decision was rejected by the combined source/lease guard. A later
diagnostic observed the original receipt beyond the freshness deadline and a
still-valid lease; it did not record the failed-guard instant or conclusively
identify its predicate. Repeated Python checkpoint audits are a measured
critical-path cost in that trace; this change tests the reuse mechanism and exact
wire continuity. It does not prove the remaining work fits the deadline on a
contended hosted runner. Root must run the unchanged native positive and negative
cases against the adopted cache implementation and require the relevant complete
CI checks on its exact new head. The original source and lease guards, original
request IDs/receipts, once-only admission, rollback behavior, and uncertain
original-ID reconciliation cannot be widened, refreshed, skipped, or retried to
make that proof pass.

Rollback is a reviewed reversion of the two implementation modules to the
previous full-resolution behavior. It needs no database migration or provider
change. New package/source bindings must again use the reverted bytes; retained
receipts and this historical golden fixture keep their recorded provenance.

## Root adoption and independent native check — 2026-10-13

The exact five-file local commit `d55bff696694c69dde87577565c496d1f72ea93a`
is adopted as `468574193c33c9d5f4c2ddee44ed00faca0a7d53` on the PR104 branch.
Root independently confirms the pre-change source hashes match its4edff598 base;
the separate TLS parent is excluded. The changed legacy/partitioned Python
hashes are respectively
`b79433a9e7aaf34112b5f76927a4e6eb990e5f6630627337e6b1add90cb60843` and
`5fc9a5ddac33a58f8855f4d7c356ca13a119909e6b819e4a681ae82972d55b75`.
Native SQL remains
`76e23d44a296c838238e5545c9ea498eb86d2ac5caee9798236aee1f8a5bf5c4`.

All five actual native restoration cases pass32.342s, zero skips, against this
adopted source and a newly owned network-none PostgreSQL fixture. Original
protective/decision guard offsets are0.904890s/1.827126s after the first original
receipt; the integral-action delay is0.183815s. The differing delay, source
sample and local scheduling prevent a calibrated old/new speedup claim. Actual
after-COMMIT failure reconciles the original protection without retry/decision;
genuine expiry refuses and leaves the original absent with rollback. Historical/
foreign/current-head, data-free controls and no-load-created authority checks
pass. Exact owned fixture cleanup completes. Complete hosted next-head CI remains
required before merge or any operating bound; no provider/cloud request occurs.

## Historical measurement lineage follow-up

The hosted ordinary-test run at cache head `35d` passed the golden wire case but
failed the configuration-repair provenance test because that test still compared
current checkpoint implementation files with their pre-cache source hashes.
That assertion failure is retained as CI evidence. It does not justify rewriting
the historical measurements or claiming new native or trajectory measurements.

The follow-up adds
`research/owned-checkpoint-cache-source-lineage.json`, SHA-256
`af0a494726b242fb110b591366e933ad6cfe2dfee68dc8c70934f353498f3869`.
It binds these unchanged original measurement files:

| Historical measurement | Preserved SHA-256 |
| --- | --- |
| `configuration-type-repair-measurements.json` | `0843296d6f677f089f897a5b41e9dc8de23ca1f32a0de2ea8a0925bd57adef05` |
| `portable-ga-model-type-repair-measurements.json` | `8a520851e022f2ee079226687714a6b98df5d7632c2e240b5e3fd49bc826a146` |

The record merges their original repaired-source maps, declares exactly three
subsequent source changes (the two portable checkpoint modules and the provenance
test itself), and binds every current source file to its actual bytes. All other
recorded sources must still equal their historical hashes. The pre-change golden
fixture's two checkpoint and model source hashes must equal those same historical
repaired hashes. Both historical artifacts, the historical defect artifact, and
the golden fixture retain their original bytes and hashes.

The corrected provenance test requires the exact lineage schema, ancestor hashes,
three-path change allowlist, actual current hashes, golden links, and false
authority fields. It does not contain a literal hash of the lineage artifact:
that artifact records the test's own new source hash, so such an assertion would
create a self-hash cycle. This separately reviewed contract pins the lineage
artifact instead. The original configuration adversarial assertions remain.

All six `ResearchConfigurationTypeTests` methods passed, zero skips, in 6.866
seconds with the same pinned, empty-environment, network-denied worker setup.
This verifies rehashed scalar aliases, unknown/missing configuration fields,
unchanged state/RNG/identity ledger/Stop behavior, canonical variable settings,
and the new historical-to-current source bindings. The unchanged checkpoint
implementation and 70-record golden fixture were not regenerated or remeasured.
Complete CI on the corrected release head remains required.
