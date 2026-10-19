# B1 actor/catalog adoption acceptance V2 — 2026-10-17

This document records a proposed, actor/catalog-only code adoption. The
corrected owned native fixture passed 15 cases. Root and an independent peer
review found no adoption blocker within that boundary. The original-partition current-base ordinary composition also passed locally.
The rebalanced ordinary composition has now passed locally as well. Eventual
required CI/release results remain explicitly pending. No lifecycle, source admission, administrative installation,
clock, hosted worker, running process, or trading authority follows from this
receipt. Existing fake profile names do not grant future capabilities.

## Exact adoption inventory

The adoption contains the following 13 previously absent paths originating at
`05fa5354743ac209fc950370570cafad1842e2d1`. Paths are relative to
`services/vonneumann`:

1. `B1-ACTOR-CATALOG-CONTRACT.md`
2. `B1-ACTOR-CATALOG-WORKING-CANDIDATE.md`
3. `R3-03A2-B1-ACTOR-CATALOG-PLAN.md`
4. `R3-03A2-B1-ACTOR-CATALOG-POLICY-PROPOSAL-V2.json`
5. `R3-03A2-B1-ACTOR-CATALOG-POLICY-PROPOSAL.json`
6. `R3-03A2-B1-CATALOG-SCHEMA-DRAFT.md`
7. `R3-03A2-NATIVE-LIFECYCLE-SCHEMA-PROPOSAL.md`
8. `db-contract/research/actor_catalog_v3_source.py`
9. `db-contract/research/jupiter_actor_catalog_v3.sql`
10. `research/b1-actor-catalog-owned-native-2026-10-13.json`
11. `tests/postgres/actor_catalog_v3_fixture.py`
12. `tests/postgres/test_actor_catalog_v3.py`
13. `tests/test_actor_catalog_v3_source.py`

The fourteenth new path is
`tests/test_actor_catalog_v3_fixture_policy.py`, containing seven pure fixture
policy cases. The sanitized machine receipt lists the original and proposed
hashes for every path. Only the fixture and native-test paths receive forward
portability/maintenance changes; the other original eleven paths remain
byte-identical. No existing application or worker implementation is replaced.

The frozen SQL remains SHA256
`84b3167c6626911fd231f2eeb337e1df4ab645a89c723017ecb169cdabf93cad`.
The frozen current policy file remains
`468b195e5789e8df0cc9dfd26bcc76b57911f9d7268a1a7ad77e4f89eceb2351`,
with canonical policy digest
`2618f8f4239460112df4b7b21138f103f265353233d35e779e874431057a7c06`.
The original 14-case contract and public fake receipt are historical evidence,
not rewritten as results of the new 15-case module. That original receipt
remains `5cc3ae3cb5f9e358aeb1939ff5eb18f86779c4acb05b52c63b0eff0d816eaf50`.

## Forward fixture repair and retained failure

The original portability proposal replaced an ARM-only fixture gate with an
explicit dispatch: amd64 uses the current reviewed original/mirror image
verifier; ARM retains only the previously observed original index-store
identity. It does not invent ARM leaf/config or mirror acceptance. The native
class uses the runner's canonical PostgreSQL opt-in skip reason. Seven pure
cases cover admitted and refused metadata without starting a native fixture,
Docker command, subprocess, or network connection.

The proposal also adds PostgreSQL17 `MAINTAIN` to the independent privilege
matrix and a fifteenth native case. A denied `ANALYZE` may deliberately return
exit zero while warning that the table was skipped, so the test examines the
actual warning rather than treating zero exit as authorization. It then grants
MAINTAIN only to one fake actor, verifies real maintenance succeeds, and
requires the installed catalog guard to reject that unauthorized ACL drift.

The first 15-case run produced **11 passes, four errors, zero skips**. This
failure is preserved. Source inspection of PostgreSQL17 ACL handling and K's
`acl_is_null` projection attributes the four errors to NULL becoming an explicit
owner-only ACL after GRANT/REVOKE, despite equivalent effective permissions.
The failed run did not retain actual before/after ACL preimages; that specific
transition is therefore an attribution, not a preimage comparison observed in
that run. The corrected later run does prove exact equality. The repair
does not weaken K, accept the drift digest, or change the frozen SQL/policy.
Instead, fixture preparation materializes and independently verifies the exact
owner-only ACL before accepting gold. The controlled test then requires exact
ACL and original-K restoration after revocation.

| Retained evidence | SHA256 |
| --- | --- |
| Failed snapshot manifest | `4353d0f69fdbaa752c2023bebde57ebb196072d66bfc69b3495fa889d5ccf323` |
| Failed native receipt | `b42b99bd16208c789beb7ac2cede6fd382338a796c8302c26b361e060d8bdacb` |
| Failed native log | `649600bdc4724a0120cc7cad3440be94cf13fb7c96b2d3e832f65cc4650b1c63` |
| Two-file ACL repair patch | `952f5908d935568492e59bb14bc507a6ec043056f356ca8d1d5560453e65189c` |
| Corrected frozen manifest | `c228c0f3a987ddeda98669f5eb9d7d0a9abc477d7c0243dbf98ab0d647c9360f` |

## Corrected acceptance and its limits

The corrected original run passed **15 executed cases, zero errors, failures,
or skips** in **22.850456125 suite seconds**, with **22.923115000 outer
seconds**, exit zero, and no timeout under the 180-second supervisor. Its receipt
is `949d776b0ce8328bbb553a5e107d82e1f24931e876444098231f15f9c979427a`;
the log is
`168c0023fd1a0cf0052b7894d25ff9980b465fc35b66d23f3478c3955620830e`.
Exact owned-container absence and removal of the owned empty Docker configuration
were verified; source hashes matched before and after. No hosted or provider
activity occurred. The corrected snapshot's seven pure policy cases also
passed, separately from native execution.

The controlled maintenance case proves more than effective privilege recovery:
the original stored ACL and complete K both return exactly, and an ordinary
authorized ANALYZE changes statistics without requiring replacement gold. The
loader derives function/header/table expectations from independently held
reviewed source before installation output can become a baseline. The fixture
then seals ownership and independently checks real privileges. Eight actual
fake sessions across two scopes bind original role OID plus name; dropping and
recreating a role cannot inherit its old binding. Foreign and unknown requested
bindings share absent disclosure. Only `verify_actor` and
`read_scoped_binding` are granted, and all seventeen authority-limit fields
remain literal false.

These are bounded laboratory observations, not production principal, engine,
image-binary, administrator, resource-capacity, or arbitrary-role attestation.
The trusted fixture bootstrap remains a trust assumption. Current amd64 image
policy tests do not replace actual required amd64 CI. The older contract's
unexercised exact boundary limits are not newly certified by adding one case.

## Current-base ordinary composition and balanced follow-up

The prior original-partition local composition passed: **2,083 executed cases,
2,601 reported, 2,735 discovered occurrences, 54 repeated IDs, 533 approved skip
entries, and zero unexpected skips**. Its ordinary unittest suite durations were
416.774s and 728.155s under the unchanged 1,500-second limits. Receipt SHA256 is
`2c9658e43e7a36aa0952fcad538b38acd4326d9955146fb90190046be434d12f`;
its complete 882-file source manifest is
`f983823818c9d3c9083d0e2da11165c1909061065e41dfbe9e0aa871de2378b3`.
Source bytes were unchanged across that run.

This was a private archive composition of base
`dd2332dcdc1bb0b63153fabe267c8863fa25b7fb` plus the fourteen new B1 paths.
It is not an actual Git adoption head; `actual_source_head` remains null.
Its local success did not supersede that base's actual Linux/amd64 shard2 CI
timeout at 1,500s in run 39014680277.

A single passive timing diagnostic completed all sixty model/source cases
without skips: model 20 inclusive 122.732878041s and source-admission 40
inclusive 250.224282041s, receipt
`0ef10e530c8bcae511765759310bf95adcf8dc4d34c36176ab7549d6f21b24dd`.
The first-order transfer estimate 539.507s/605.422s is local only, not a hosted
resource or completion guarantee. The proposed mapping keeps both complete
modules opposite, every occurrence and fixture segment intact, and the original
two ordinary/four SQL shards and 1,500/2,400-second deadlines unchanged.
Eleven focused sharding regressions passed with zero skips.

The **one balanced 882-file composition passed locally**, using the same
dd233 base, fourteen new B1 paths, and exactly two modified CI paths:
`scripts/check-worker.py` SHA256
`b2cc6f472ce8deaf0f491a6a2f930ba8e83143dae07d742c236ac42f365bb9f7`
and `scripts/tests/test_worker_sharding.py` SHA256
`d9ca3e0c8d09cf4ce180b6dab1d7e1f0ad95b08f46ce761f93b0154cebe4191b`.
The source manifest remains
`acde518483be0646ace2d5a21a789947cb74b6ae43727c3087cca120f0373c38`;
all 882 source hashes and the other 880 source files were unchanged. A snapshot
manifest binds these bytes; it is not an invented Git commit.

The original balanced receipt is
`53f9298410c6e421356f5a059a69b9fba102a479f971349d5c6e54ea547f687d`.
It records **2,736 discovered occurrences, 54 repeated IDs, 2,602 reported,
2,084 executed, 533 canonical approved skip entries, and zero unexpected skips**.
Those audited entries comprise 518 method skips and 15 class/module setup skips,
all for the canonical PostgreSQL opt-in boundary; 134 discovered occurrences
were not started, so 652 discovered occurrences were nonexecuted in total.
The additional discovered/executed case versus the earlier composition is the
new sharding regression; no existing occurrence was removed.

| Ordinary shard | Selected | Reported | Executed | Unittest seconds | Outer seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,092 | 1,009 | 835 | 562.709 | 564.959081250 |
| 2 | 1,644 | 1,593 | 1,249 | 628.682 | 630.675161708 |

Both original 1,500-second children exited zero without timeout, and both owned
child groups were verified absent. This is the original accepted local run,
not a repeated or reconstructed result. It executed no native fixture, provider,
or hosted operation and does not establish amd64 CI or B1 release acceptance.

Final seven-job CI and exact Dashboard production verification belong to a
separate actual B1 adoption pull request, which has not been created. Both remain
pending. Private fixture/composition results cannot stand in for those release
observations.

## Next boundary and rollback

The smallest coherent next B2 slice needs a separately reviewed forward
descriptor, closed non-packet action identity and read-only query/correlation
mapping, and the minimum structural D4 commit/getter isolation needed for
immutable originals. Define recorder-self fence checks separately from the
scoped control actor's check of the installed recorder's current fence. Then
prove finite fence/control transitions, one eleven-ID reservation, and reserved
Stop attempt followed by read-only original reconciliation. An unresolved
reservation remains locally closed and unknown indefinitely unless the same
original committed Stop is verified. A stale-head Stop can refuse; reserved
capacity does not establish native stopped state or MVP Stop liveness. No fresh
ID or silent collection retry follows uncertainty. If recycling is required,
the explicit abandonment-closure
subset and its budget must be installed first. Full capture, admission,
availability, reader delivery, seal, and model joins remain separate gates.

The smallest rollback is a reviewed code revert of this scoped 14-path adoption,
with normal CI and release verification. Preserve the earlier accepted
foundations and historical evidence in Git history. No hosted database rollback
is required: these research fixtures install nothing in the hosted project,
and this code adoption grants no live runtime capability. Any later native or
worker activation needs its own implementation, acceptance, and rollback review.

The original private review drafts are retained unchanged as lineage; their
hashes and the wording corrections are recorded in the sanitized receipt.

## Receipt lineage and preparation scope

The reviewed original MD/JSON remain unchanged. This V2 preserves the failed
native history, source-inference qualifiers, two forward fixture/native-test
changes, unchanged frozen SQL/policy, and separate native acceptance bounds.
The optional B2 V3 proposal and root commit/clock note may accompany a later B1
adoption as design documents; neither freezes a B2 policy or grants runtime
authority.

This agent wrote only these private receipt drafts. The machine field declaring
no ROOT writes describes this receipt-preparation step alone; it does not claim
that adoption/integration made or will make no repository changes. No new tests,
Docker commands, provider calls, hosted operations, or credentials were used in
preparing the drafts. Only sanitized counts, source/evidence hashes and bounded
acceptance facts are retained; no raw logs, environment values or actor IDs are
copied.
