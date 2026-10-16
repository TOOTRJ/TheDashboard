# Secret-free Dashboard verification

## October16 exact-content mirror repair — superseding failed scheduling experiment

Actual run38979594404 at e004800 shows two-way scheduling does not fix the
quota: SQL1/3 fail image preparation. Before the planned superseding push,
frontend passes1m47s and ordinary2 passes; ordinary1 and SQL2/4 are still running.
The incomplete run is not seven-job acceptance. Existing automatic concurrency
cancellation will retain its unfinished/canceled states; none count as passes.

The replacement restores original four-way SQL scheduling and adds only a
rate-limit-triggered switch to the two official Docker Hub repositories whose
raw manifest/config bytes match the original pins. Five total pull attempts,
the shared240-second pull phase, subsequent30-second inspect/tag/inspect
limits, all source/lease guards, test inventory and job/child limits remain.
Actual selected-source RepoDigests are verified; no ECR digest is invented.
[Metadata, publisher proof and remaining availability limits](CI-IMAGE-MIRRORS-2026-10-16.md).

Root's complete focused policy/native-wheel/pull/pure-archive/sharding checks
pass106 cases, zero skips,0.784s after scheduling restoration. Actual workflow
validation passes. These mock/pure cases are not actual registry or SQL
acceptance; the corrected head must finish every required job. Earlier
two-way policy observations below retain their historical experiment scope.

## October16 bounded concurrency repair — new-head acceptance pending

The reviewed first mitigation changes only PostgreSQL matrix max-parallel4→2
and its exact policy/mutation tests. All four shard values, fail-fastfalse,
image verifier/pins, pull attempts/bounds, tests, skips, permissions and job/
child timeouts remain. GitHub's [matrix concurrency semantics](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations#defining-the-maximum-number-of-concurrent-jobs)
limit simultaneous jobs without removing queued combinations. Two SQL waves
may increase elapsed workflow time. This is not proof of the registry cause
or future availability. The archive prototype is unused; transport redesign
is deferred. Every actual new-head job remains mandatory before merging.

The candidate's full policy/helper module passes24 cases in0.858s; root's
composed policy plus pure archive check passes58 in4.430s. Actual workflow
validation passes. Original missing-yaml setup failure is retained; a new
private CPython3.12.14/PyYAML6.0.3 policy-only environment uses the complete
tracked hash block, public PyPI and no shared configuration change. Root's
attempt to additionally import an unchanged wheel module fails for absent
packaging; the subsequent58-case run excludes that unnecessary module and
does not claim it tested. Hosted CI installs the full existing locked graph.

The already tested build helper also fixes task-owned npm maxsockets at4,
overriding inherited values without changing locks, registry, retries or
deadlines. Its existing regressions are adopted fromd16c8ee; final new-lock
frontend/build checks are recorded inDEPENDENCY-REVIEW.md. No registry login,
publisher, artifact upload, shared Docker state or account setting is added.

## Historical verification checkpoints

Prepared 2026-10-12 for QA-01A. The repository now has three independent GitHub
Actions verification gates in [.github/workflows/verification.yml](.github/workflows/verification.yml).
They run on pull requests, main pushes and explicit dispatch, with only
`contents:read`, no application secrets, no cloud environment, no deploy step and
no artifact upload. Checkout does not persist its read-only repository credential.
Fork pull requests use the ordinary `pull_request` context; this workflow never
uses `pull_request_target` or `workflow_run` to execute fork code. Feature pushes
do not duplicate PR jobs. Concurrency cancels a superseded run for the same PR/ref.

QA-01A's automated gate has actual GitHub-hosted Linux amd64 acceptance at PR102
head `cbdc5d010f1f2e37ca50ca7d4528e8f85149e153`; the receipt below records all
seven successful jobs. This does not establish hosted Supabase/native v2
admission, real browser/session behavior, continuous paper operation or live
readiness. No production credential or Vercel/Supabase/Railway login is required
by the workflow.

The initial workflow-file push was rejected for permission. The user updated the
existing dedicated Dashboard token; exact account/repository verification and the
codex branch push now succeed. No shared login, credential rotation or
organization-wide policy change was performed by this task. GitHub documents the
separate [workflow write capability](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens#repository-permissions-for-workflows).
The CI PR's frontend, both ordinary worker groups and all four required PostgreSQL
results passed before merge. Workflow results were read
through the existing authorized Dashboard browser; additional token permissions
for unrelated checks are not required for this setup step.

## Actual exact-source acceptance — 2026-10-12 Denver / 2026-10-13 UTC

[PR102](https://github.com/TOOTRJ/TheDashboard/pull/102) is merged after
[run38326660837](https://github.com/TOOTRJ/TheDashboard/actions/runs/38326660837)
passes at the exact source above in 36m49s. The completed job reports confirm:

| Required job | Duration | Actual result |
| --- | --- | --- |
| Frontend | 1m41s | Node checks, types, lint, advisory policy and fresh fake-configuration build pass |
| Ordinary group 1 | 13m19s | 756 executed; 911 reported; 163 SQL opt-in skip records |
| Ordinary group 2 | 11m53s | 977 executed; 1,221 reported; 251 SQL opt-in skip records |
| PostgreSQL group 1 | 35m56s | 91 executed; 94 reported; 3 allowed timing measurements skipped |
| PostgreSQL group 2 | 26m31s | 128 executed; 132 reported; 4 allowed timing measurements skipped |
| PostgreSQL group 3 | 23m0s | 123 executed; 126 reported; 3 allowed timing measurements skipped |
| PostgreSQL group 4 | 12m29s | 181 executed/reported; zero skips; all 15 additional inner native-driver cases pass in 24.574s |

Every group reports acceptance and zero unexpected skips. Ordinary discovery
retains all 2,266 occurrences, including 54 original repeated IDs, split 994/1,272.
It reports 2,132 cases and executes 1,733; its 414 opt-in skip records include 399
method records and 15 class-setup records. A skipped class setup represents
multiple discovered methods, so discovery, reported cases and skip-record totals
are distinct. These ordinary skips do not establish SQL acceptance.

Required SQL discovery retains all 533 outer occurrences, including 54 original
repeated IDs, split 94/132/126/181. It executes 523 outer cases and reports 10
allowlisted timing-method skips; no SQL opt-in/setup skip is accepted. The 10
records correspond to six approved optional measurement definitions, with
original imported aliases preserved. The 15 nested native-driver cases are
additional to the 181-case outer group 4 wrapper scope.

Both ordinary groups bind discovery fingerprint
`bd8dd654e4c05d56bc19d0af07323dcf084c8139ea0acbdaac560d51e1ba17a7`;
all four SQL groups bind
`f37180b1a163178743746acf3db94d16e434cae9a9ba062d27bbe71c6a07dc05`.
All six share selection helper fingerprint
`6872899a4daad220bc89ce6a615cbad595eb73afb475ab804cfa8bd5f5c5efae`.
Complete coverage, original multiplicity/fixture segments and the 1500/2400-second
child limits remain enforced. Sharding improves scheduling; no test is omitted
or deduplicated to meet a deadline.

Merge `58808efaf2c025ea865f7429723599081edae491` has the same Git tree
`67cd62325d11ceb29381abbc71cfb60a0bffe106` as the accepted PR head. Exact Vercel
production `dpl_3TNp9KSP3cBu7DX26GzehqSKe8XJ` is READY, owned by the pinned
Dashboard team/project/repository and serving `the-dashboard-chi.vercel.app`.
Read-only `/login` 200, anonymous `/` 307→login, anonymous test API 401 and
authenticated zero-row test API 200 checks all pass. The API key stays in memory.
Supabase target metadata and the unchanged ordinary closed Railway service were
reverified; no migration, runtime setting, provider/key or wallet change occurs.

Later Markdown-only closure records this immutable receipt. Its own workflow
run is separate; this receipt does not claim that another source head completed
the same jobs. Application, test, helper, workflow and dependency sources must
remain byte-identical for that documentation-only scope.

## PR104 release review — failed head retained as evidence

The five-priority batch head `897ec2ad369d82ccef80b05a4bbd475f630a1a3b`
starts all seven required jobs in
[run38349686661](https://github.com/TOOTRJ/TheDashboard/actions/runs/38349686661).
Its frontend passes in2m21s. This is **not complete CI acceptance**: ordinary
shard1 and PostgreSQL shard4 fail, and the head must not be merged on the
strength of its successful frontend or local focused proofs.

The rendered ordinary shard1 log reports962 tests in673.884s,2 errors and163
audited opt-in skip records. The two new child-import tests used the local
`/private/tmp/dashboard-locked-worker/bin/python` executable, which is absent on
the Linux runner. The scoped repair `82759034349d9fc1d0de87a74e4f4a8ba83ff12d`
uses the active `sys.executable` in both tests. Their sanitized environment,
working directory, import guards, assertions and20/10-second limits remain
unchanged; both affected cases pass locally, zero skips,31.031s. The local
repair requires a new exact-source hosted run and does not replace the failed
head's evidence.

The rendered PostgreSQL shard4 log reports205 tests in885.928s, zero skips and
one error in the native current-head restoration/retired-identity case. Its
source-bearing command refuses with `portable_native_final_source_or_lease_expired`.
The five-second laboratory guard remains intact. Review identifies the test's
preparation/capture order and critical-path timing; a failed original
request must not be reinterpreted as accepted or silently rebased. The reviewed
repair loads the prior restoration/oracle before fresh capture, captures the
actual current protective head and scoped original snapshot, submits the same
decision once, then verifies saved-snapshot full/compact equivalence off the
admission path. A three-case revision passes24.439s, zero skips; the final
affected-case representation/reporting repair passes17.695s, zero skips. Its
native receipt records protective/decision guard intervals1.646198s/2.895655s
after the unchanged original fractional receipt. These local source-specific
proofs do not establish cold restoration and full decision within five seconds,
new-v3 integer-clock acceptance, hosted performance or final CI acceptance.

The completed original run also reports SQLshard2 failure in40m54s total. Its
parent child limit expires at2399.9999737519997s during the new portable semantic
module. The partial log records `test_latest_bootstrap_receipt_is_checked_even_when_an_earlier_document_is_fresh`
as FAIL but reaches no final unittest traceback/report. Source review identifies
a timing-sensitive four-second future claim; that explanation remains an
inference rather than a recovered exception. The repaired native-first supplied-history
negative keeps the sealed producer baseline unchanged and submits one explicit
adversarial canonical request whose later receipt is claimed60 seconds ahead.
It passes1/1 actual PostgreSQL case, zero skips,3.103s, with the expected native
future refusal and complete table equality. It is not producer-valid continuation
acceptance; server clock, model, guard and30-second SQL test limit stay unchanged. Partial
progress/coverage must not be treated as completed execution.

Observed SQLshard1 passes32m36s and shard3 passes18m40s at this failed head.
The reviewed41c214d scheduling repair moves the whole new
`tests.postgres.test_portable_transition` module to shard3. Ten existing
selection/coverage/environment tests pass0.006s. Every discovered occurrence,
original order/fixture segment,54 repeated IDs, skip rule and1500/2400-second
child deadline remains enforced; the final selection source fingerprint changes.
The corrected source still requires all seven actual hosted jobs.

### Completed follow-up head c58177a — 2026-10-13

The complete [run38357623351](https://github.com/TOOTRJ/TheDashboard/actions/runs/38357623351)
at `c58177afe7d22ab17b6ee21da91ec2b9e7d5a73d` fails in42m29s. Fresh rendered
job results show frontend2m1s, ordinary1/2 in11m28s/10m41s, SQL1 in36m42s and
SQL3 in28m37s all successful. SQL4 fails in15m39s and SQL2 in40m57s. These
successful job outcomes do not close the seven-job release gate.

SQL4 still refuses the once-only original decision in the current-head/retired-ID
restoration case with `portable_native_final_source_or_lease_expired`. The native
condition combines source and lease deadlines; the failed log does not identify
which expired at the actual guard instant. The prior local pass is therefore
insufficient. Review must preserve the original request, genuine observed
clocks and accepted-head/oracle snapshot, and must not widen either deadline,
renew/rebase evidence or turn an expired request into a passing continuation.

SQL2's required integration step reaches40m0s. The sanitized child's parent
expires after2399.999975517s in
`test_complete_provider_control_risk_and_held_stop_traces` from the defining
`tests.postgres.test_source_transition` module. The preceding four methods in
that module and the new native clock/latest-history/retention cases are rendered
as successful. There is no final unittest report for this interrupted group;
do not count its partial progress as complete execution. Immutable image
preparation succeeded in this run, so registry pull failure is a separate
historical problem, not this timeout's cause.

The test merge's tree is identical to the reviewed PR head tree; the workflow
uses the normal pull-request test merge checkout. PR104 remains open and
production remains the last verified PR103 release. Source-specific timing,
exhaustive selection and the complete next hosted run remain required.

All seven required jobs at the final corrected head, exhaustive coverage,
explicit skip audit and fresh exact-project/source/author/alias release checks
remain the merge gate. The c581 source inventories2398 ordinary and600 SQL
occurrences, retaining54 original repeated IDs; discovery is not execution.
Its earlier module move produces SQL counts94/158/143/205 and ordinary
counts1045/1353.

The subsequent original-pair test repair moves both duplicate reconstruction
comparisons after the once-only pair while retaining actual current-at-capture
snapshots/oracles and complete state/13-component/full+compact equality. A new
genuine six-second expired-original regression requires one native refusal,
original-ID absence and complete rollback with a live lease. A separate pure
output-error check preserves the same SQL exception without a database call.
All four native cases pass33.380s, zero skips; ordinary restoration16 cases
pass52.863s, zero skips. Native/model/decoder bytes and source5/lease60/future2
bounds remain unchanged. [Detailed sequence and limits](services/vonneumann/PORTABLE-RESTORATION-CONTRACT.md#captured-head-pair-equivalence-and-refusal-diagnosis--2026-10-13-utc).

The whole defining source-transition module now moves SQL2→SQL4. All600 prior
ordered occurrences and54 repeated IDs are preserved; only its30 occurrences
move. Ten existing coverage/fixture/environment tests pass0.007s, with unchanged
1500/2400-second limits. The added refusal case then yields2399 ordinary
occurrences1045/1354 and601 SQL occurrences94/128/143/236. Final selection SHA256
is `be75136c0592a7a2da26707a3d7e4c1e7e740dda639776f6759d23ed64357af1`;
ordinary discovery SHA256
`e1f774da9b5d8e47d5d4941aeb2f53e3867b4a3f08dccd7b89c8037a8c857262`,
SQL discovery SHA256
`7ea5fd730d7d91975c5b62f9fbf81ec02b8fd37a6ad324b3b25a3b153f06718c`.
These inventories and focused passes still require complete exact-source hosted
acceptance; a balancing hypothesis is not an upper latency bound.

### Completed follow-up head 360d4a2 — 2026-10-13

[Run38420675259](https://github.com/TOOTRJ/TheDashboard/actions/runs/38420675259)
at `360d4a2ea490eabf53bfa2709495f89b725a368e` completes in35m5s. Frontend
passes2m43s; both ordinary groups pass15m47s/13m14s. SQL groups1–3 pass
29m58s/29m59s/35m1s. SQL4 fails26m5s: its report contains236 cases in
1499.558s, one error and two allowlisted optional timing skips. The moved
complete source-transition trace passes. The original current-head restoration
decision still refuses with `portable_native_final_source_or_lease_expired`.
PR104 remains unmerged; six successful jobs do not establish release acceptance.

The post-rollback observation retains the original decision ID/wire digest and
reports no original committed row. Its later clock sees the original receipt
aged5.246318s and a still-valid lease. The protective committed receipt records
a guard2.281214s after that same first receipt. This supports investigating
source-path cost but does not recover the actual failed guard instant or prove
its branch. The genuine expired-original refusal and rollback regression passes.
No new ID, clock adjustment, retry, guard widening or test omission is accepted.

A separate owned local one-case phase observation passes14.694s with unchanged
source/native/model bytes. Its protective/decision native guard intervals are
0.888197s/1.986572s after the original receipt. Local preparation/capture,
transport, current-head reads and both original commits are measured separately;
these observations are not hosted bounds or substitutes for the failed run.

The subsequent test-only repair keeps explicit COMMIT and full authenticated
native readback in one ACTOR connection, then independently verifies the current
head/catalog through a fresh operator connection before the same original
decision. All native checks and separate final reads remain. Five native cases
pass36.091s, zero skips, including an actual error after COMMIT that reconciles
the original committed protection without retry or decision. Fixed process
phase timings are available on success/refusal without claiming the failed
native clock. No server/JIT/native/model/decoder or guard change occurs.

Final discovery contains2400 ordinary occurrences1045/1355 and602 SQL occurrences
94/128/143/237, retaining54 original repeated IDs. Selection SHA256 is unchanged;
ordinary discovery SHA256
`d8b26be79ff95f08d5077565f67284b2ac5c0ff485c16a63b4872cc3f49eec77`;
SQL discovery SHA256
`970cba0134f6186013506ae042595e32e1d541427f019208fce63c6a7d44a536`.
Discovery does not execute tests. Complete next-head CI remains required.

### Completed follow-up head 4edff598 — 2026-10-13

[Run38429396878](https://github.com/TOOTRJ/TheDashboard/actions/runs/38429396878)
at `4edff5983ec6817fe7156c659cd716e8340f5eac` completes39m36s. Frontend
passes2m11s, ordinary groups pass15m34s/15m8s, and SQL1–3 pass36m30s/39m33s/
28m51s. SQL4 fails25m9s, reporting237 cases in1442.718s with one error and two
allowed optional timing skips. Its complete source-transition trace and the
new actual post-COMMIT failure/reconciliation case pass. The original restoration
decision still refuses at `portable_native_final_source_or_lease_expired`.
PR104 remains unmerged; no job rerun, deadline change or omission closes this.

The fixed process-phase observations identify repeated checkpoint capture and
transport preparation as a substantial cost: protective capture0.456948445s,
protective transport0.317276690s, decision capture0.432810786s and decision
transport0.440093513s (1.647129434s together). Original protective submission
and native readback takes1.208044806s; its separate fresh operator read takes
0.160430889s; decision native submission takes1.518929106s. These process
durations are not the failed native guard's clock. The accepted protective guard
is2.789782s after the first original receipt; a later diagnostic observes that
receipt aged5.514220s and a live lease. The combined failed predicate's exact
instant remains unobserved. Preserve the original-ID reconciliation and refusal.

The next investigation may cache the completed full validation only for exact
immutable objects created by the private checkpoint factory. Arbitrary decoded,
restored, forged or changed objects must retain full validation; detached views,
canonical full/compact wires, first-factory validation and independent native
source/lease checks remain required. This would change Python implementation
hashes and requires new evidence, without relabeling prior source-bound receipts.

### Factory-owned resolution follow-up — adopted locally 2026-10-13

Reviewed cache commit `d55bff6` is adopted as `468574193c33c9d5f4c2ddee44ed00faca0a7d53`
with exactly five files; its separate TLS parent is excluded. Both first-factory
full audits, complete arbitrary `resolve_manifest` functions, transport/candidate
comparisons and all wire/capacity policies stay intact. Exact immutable factory
object/type/byte identities permit a detached JSON view from already validated
evidence; unowned, restored, changed or copied objects keep full auditing. Weak
ownership does not confer source, receipt, lease or native authority.

The author passes14 dedicated cases/18.244s, including70 independently captured
pre-change full/compact/manifest/component wire records, and16 existing offline
restoration cases/38.370s; both report zero skips. Root independently runs all five
actual native restoration cases against4edff598 plus this cache:5/5 pass32.342s,
zero skips. The actual positive guards are0.904890s/1.827126s after the same
original receipt; its integral-action delay is0.183815s. This differing delay and
local scheduling prevent a calibrated old/new speedup or hosted bound claim.
Actual post-COMMIT reconciliation, genuine expiry rollback, original absence,
foreign/historical refusal and data-free controls remain accepted locally.

New ordinary discovery is2414 occurrences1045/1369, SHA256
`d5a508ad6d4801fa51b57ca160ec4da1bb6415f9b5666e361c0a92d542121bad`.
SQL discovery remains602 occurrences94/128/143/237, SHA256
`970cba0134f6186013506ae042595e32e1d541427f019208fce63c6a7d44a536`.
Selection SHA256,54 original repeated IDs and all limits stay unchanged.
This is discovery, not complete execution. Require all seven actual checks on
the next pushed head before merge. [Ownership contract](services/vonneumann/OWNED-CHECKPOINT-RESOLUTION-CONTRACT.md).

PR/manual triggers have no path/type/branch filters, and main pushes have only
the main-branch filter. The capability validator requires every advertised Node,
type, lint, advisory, build, lock/hash installation, dependency-consistency and
image/integration command; removing one or adding a bypass/filter fails its tests.

### Completed cache head 35d6aac and source-lineage repair — 2026-10-13

[Run38438232967](https://github.com/TOOTRJ/TheDashboard/actions/runs/38438232967)
at `35d6aaca46cb1f628bf4f910433fdfc9355a242e` completes37m58s. Frontend passes
2m43s and ordinary1 passes17m39s (962 reported cases/1024.988s,163 audited SQL
opt-in skip records). Ordinary2 fails14m17s (1318 cases/822.455s, one stale
source-hash assertion and320 audited opt-in skip records). SQL1 passes36m47s
(94 cases/2139.987s, three allowed timing skips); SQL2 fails37m58s (128 cases/
2212.972s, one stale source-hash assertion and two allowed timing skips); SQL3
passes33m32s (143 cases/1947.677s, three allowed timing skips); SQL4 passes16m15s
(237 cases/903.634s, two allowed timing skips). The full run remains failed;
five successful jobs are not release acceptance. All jobs finish before another
push, preserving their evidence rather than cancelling the unfinished groups.

SQL4 now accepts the original restoration pair with protective/decision guards
1.361904s/2.612940s after the same original receipt and integral-action delay
0.473995s. Capture/transport phases total0.481070084s; pair plus delayed complete
full/compact equivalence takes2.973974s. Actual post-COMMIT reconciliation finds
the original committed protection without retry or a decision; its native/readback
phase is0.642235079s. Genuine expiry rollback and the complete moved source trace
also pass. These are source-specific hosted fixture observations with unchanged
guards, not a calibrated speedup, tail bound or production/runtime acceptance.

The ordinary provenance test and native retention test both compared current
checkpoint implementation files with historical pre-cache hashes. The correction
preserves every historical measurement and source-contract byte. Root adopts the
reviewed ordinary lineage repair as `3c643d77f7a5847e089bf8170c2daeecd913ef3b`;
all six affected configuration/provenance tests pass5.484s, zero skips. Its exact
new lineage artifact binds the historical receipts, two changed checkpoint files,
current regression and unchanged model/golden wires. The retention test checks
the exact historical source-contract and lineage hashes, replaces only the two
reviewed implementation hashes, and still checks all ten current model sources.
Every native/control/Stop/storage assertion and source/lease/SQL limit remains.

The unchanged owned retention trace then passes one actual PostgreSQL case in
38.017s, zero skips:33 commands,60 original-ID/13-pin readbacks, all allocated
identities retained and final Stop while flat. The new
[source-bound receipt](services/vonneumann/research/portable-retention-cache-lineage-acceptance.json)
records1,736,704 total relation bytes and671,205 selected text-wire bytes across
the13 owned tables. It does not overwrite or recalibrate older storage receipts;
WAL/backups/cloud/load/pruning/crash durability remain unmeasured. No hosted
database, provider or application credential enters the owned fixture.

After the ordinary repair, discovery remains2414 ordinary occurrences1045/1369
and602 SQL occurrences94/128/143/237, retaining54 repeated IDs. Ordinary discovery
SHA256 is `c75bec99799fb8ff73e2d0154c5fc8e231406893f8a931ba5f55c7bea3897eee`;
SQL remains unchanged until the subsequent retention test-only edit. Final
post-repair discovery retains the same counts/54 repeated IDs and selection;
ordinary SHA256 is `46ea26933326d3027efa9074beb7dba7d5327225a438bf87982ed15815573427`,
SQL SHA256 is `8c4e2f7f1be78163b436bfd1d61d366ddd9375b01a6429a251e439b855f52b46`.
Discovery executes no cases. All seven actual next-head jobs remain required.

## Independent gates

| Job | Runtime / limit | Work and truthful scope |
| --- | --- | --- |
| Frontend | Node 24.19.0; Ubuntu 24.04; 20 minutes | Clean lock install with lifecycle scripts disabled; all current `tests/*.test.mjs`, `tests/probes/*.test.mjs` and helper Node files; TypeScript, lint, advisory policy and a second fresh fake-configuration production build. Existing lint warnings are reported; errors fail. |
| Ordinary worker, two required groups | CPython 3.12.14 x64; Ubuntu 24.04; 30 minutes each | Fresh virtual environment per runner, hash-required binary-only dev/runtime wheels, `pip check`, complete worker discovery plus repository/helper Python tests partitioned into two exhaustive deterministic groups. SQL opt-in skips and optional measurement skips are explicitly categorized and printed; no SQL acceptance is claimed. Unexpected skips, empty/all-skipped results and errors fail. |
| Required PostgreSQL, four required groups | Same Python; Ubuntu 24.04; 50 minutes each | Reviewed immutable amd64 PostgreSQL 17.6/PostgREST 14.5/Python 3.12.14 fixtures and a verified native-driver wheel bundle, followed by full actual PostgreSQL discovery with explicit opt-in before exhaustive deterministic selection. Missing Docker/image/setup, foreign daemon, zero execution or any opt-in skip fails. Six allowlisted non-gating timing-method definitions may be skipped; every reported skip retains its test ID and exact reason. |

The chosen patch versions match the current reviewed source/software contract.
They are deliberate pins, not a claim to be the newest security patches. A later
runtime or action update requires source/lock/advisory and compatibility review;
do not silently switch to `latest`. The frontend advisory gate belongs to the
separate security slice: zero production findings and only its exact expiring
development exception are permitted. It must not be replaced with global audit
suppression or a blanket `continue-on-error`.

The owned child deadlines are 1500 seconds for each ordinary group and 2400 seconds
for each required PostgreSQL group, leaving 300/600 seconds within the 30/50 minute
job ceilings for setup and cleanup. Actual hosted run38320983287 at source1f6a1f7
passes frontend in 2m0s but exceeds the monolithic ordinary 1500-second deadline
without a final test summary. The earlier local duration was not a reliable bound
for the Ubuntu runner. Two required groups preserve the complete suite and its
original test occurrence multiplicity, including imported aliases; heavy original
provider-GA traces are separate from portable-GA/active-GA/partitioned traces.
Remaining and new modules use a fixed deterministic partition. Full discovery,
module ownership, ordered occurrence coverage and fingerprints are checked before
execution; discovery errors, missing/duplicate occurrences, overlap, unknown shard
selection and empty groups fail. Each original defining-module fixture segment
retains setup/teardown boundaries. Matrix fail-fast is disabled so a failed group
does not cancel the other group's evidence. No heavy replay window or assertion is
removed. The same run's full SQL child also exceeds its2400-second deadline without a
final summary. Required SQL now uses four exhaustive defining-module groups,
retaining all aliases, fixture segments and the same strict skip policy. The
known assessment/causal setup segments consume roughly633s/515s respectively;
causal aliases alone total about1030s before the remaining modules. Independent
assessment, causal, optimizer and portable-mutation anchors distribute that
work across four groups. Partial observed costs justify scheduling, not a claim
that the bounds pass. Every required group must finish successfully.
The wrapper requires CPython 3.12.14 explicitly and gives a virtual-environment
setup error for an unsupported default interpreter.

## Build and environment isolation

[scripts/check-build.mjs](scripts/check-build.mjs) reads the local Git index's
frontend/build filename list with hooks/fsmonitor disabled, then copies only
those current working-tree files into a new owned temporary directory. Stage new
frontend source before running this check; an untracked file is intentionally
excluded. It does not copy `.git`, `.env*`, `ssl`, existing `node_modules`/`.next`,
agent/cloud configuration, worker source or unrelated drafts. Private/generated
reviewed paths, symlinks in any input ancestor and nonregular files are rejected.
The marker-protected directory is removed by its owner even if install/build fails.
Fixture tests can supply an explicit reviewed path list without constructing Git.

The build does its own locked install with
`npm ci --include=dev --ignore-scripts --no-audit --no-fund` and invokes Next directly
in that directory. The explicit dev inclusion retains Tailwind/PostCSS and other
build tools even though the isolated child uses `NODE_ENV=production`; omitting it
reproduced a missing build dependency in the first actual clean build.
Its child receives only minimal runtime/locale paths, fixed fake Supabase public
and server keys, and the reserved `https://dashboard-ci.invalid` URL. These fake
values grant no authority and cannot point at Dashboard services. Shared npm
user/global configuration and caches are excluded through separate empty config
files and an owned cache. The workflow's initial install also uses distinct empty
configs and a runner-temporary cache. No build bundle is uploaded. This is a
clean build check; it does not perform authenticated application requests or
prove provider/browser integration.

[scripts/check-worker.py](scripts/check-worker.py) reexecutes only its own Python
process with allowlisted paths/locale, disabled dotenv/bytecode, fixed thread
bounds and the repository worker import path. It drops application credentials,
proxy/token settings, arbitrary Python import/startup settings, inherited opt-in
and measurement flags. The internal child flag cannot bypass this environment
check. The required SQL child admits only an explicit local Unix Docker socket and the independently validated native fixture bundle path.
No existing Supabase database is selected.
Locale is fixed to C with Python UTF-8 mode enabled and locale coercion disabled.
On macOS, the child also fixes the benign per-UID text-encoding key added during
Python imports and checks its exact value; arbitrary extra environment keys are
still rejected. The reproduced pre-discovery failure came from that implicit
macOS key, not an application credential or a broad allowance needed by tests.

## Fixture identity and owned integration

[Reviewed registry metadata](scripts/check-ci-images-evidence.json) was captured
from public ECR on 2026-10-12 with response-digest verification. It distinguishes
the multi-platform index, platform manifest and image config; the earlier
`965e…` observed identity is the PostgreSQL index, not an amd64 config digest.

| Image | Linux amd64 manifest | Config digest |
| --- | --- | --- |
| `public.ecr.aws/supabase/postgres:17.6.1.095` | `sha256:4c087262afbfbb47da86e2863a52d7e424eb21ab589f732d77eeaab51be8e521` | `sha256:972aabc75779f6e535f87e1669f36edbab02cdf8bf3f47d13579963c119adefb` |
| `public.ecr.aws/supabase/postgrest:v14.5` | `sha256:bb289d00570b569525e1e22fb77c49cd17c17ca3f41da9ee2b4351a35027551b` | `sha256:af0a6dad76305650c215449d905a124ae5ad3bcd0f04c01845a0cea17d4e0960` |
| Official `python:3.12.14-slim-bookworm` | `sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a` | `sha256:febd0be41adb897a0ab8f1f1c693d8912669ea60c4940e076e9946b60e210ef0` |

[scripts/check-ci-images.py](scripts/check-ci-images.py) pulls those exact leaf
references, checks Linux/amd64, repository `RepoDigests` and the reviewed immutable
manifest/config identity, then supplies the exact existing harness tags only in
the new disposable GitHub-hosted Dashboard runner. Its explicit preparation action
checks the documented [runner and repository variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) and refuses local/self-hosted and wrong-repository contexts; it never retags a shared
local daemon. Registry failures fail setup rather than selecting a different image.

The existing [owned harness](services/vonneumann/tests/postgres/README.md) creates
UUID-labeled bounded containers and verifies ownership before cleanup. Ordinary
PostgreSQL has no network/host mounts/ports and uses socket-only SQL. The
PostgREST fixture uses its documented private bridge and exclusive loopback HTTP
port with fake identities; this is not a general egress firewall. Tests cover real
role/transaction/lock/HTTP behavior; they do not authenticate hosted Supabase or
establish native version 2 admission, restoration, profitability or live readiness.
No broad Docker stop/prune is used. Cancellation may prevent normal test cleanup;
the disposable hosted runner bounds the lifetime of any remaining fixture.

## Reviewed action pins and local verification

The release pages and pinned action manifests were reviewed on 2026-10-12. All
three run on the action's Node 24 runtime:

- [checkout 7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1): `3d3c42e5aac5ba805825da76410c181273ba90b1`; [pinned inputs/runtime](https://raw.githubusercontent.com/actions/checkout/3d3c42e5aac5ba805825da76410c181273ba90b1/action.yml).
- [setup-node 7.1.0](https://github.com/actions/setup-node/releases/tag/v7.1.0): `949feb2413d6458794dcd2491c4babbbce0c15c1`; [pinned cache/runtime inputs](https://raw.githubusercontent.com/actions/setup-node/949feb2413d6458794dcd2491c4babbbce0c15c1/action.yml).
- [setup-python 6.3.0](https://github.com/actions/setup-python/releases/tag/v6.3.0): `ece7cb06caefa5fff74198d8649806c4678c61a1`; [pinned Python/runtime inputs](https://raw.githubusercontent.com/actions/setup-python/ece7cb06caefa5fff74198d8649806c4678c61a1/action.yml).

Local checks use the existing project Node/Python runtimes. The helper regressions
exercise real snapshot exclusions and symlink rejection, fake child configuration,
failure/owned cleanup, skip accounting and mandatory-SQL denial, registry/platform
identity, and workflow privilege/trigger/bypass changes. The receipt above
separately establishes actual hosted execution of every required group. The workflow capability
check is part of ordinary helper test discovery.

The complete sanitized local run reported 2,088 cases in 1,287.086 seconds. All
1,630 executed worker cases passed; it separately reported 414 SQL opt-in skip
records (399 methods and 15 class setup skips). Its only error was an older
repository export fixture missing the already required controller canary. The
positive fixture and a missing-canary refusal regression repair that test; the
production exporter is unchanged. After the associated portability repair, all
66 repository/helper cases pass again with zero skips. This is the full worker
result plus a complete rerun of the changed helper scope, not a second clean
monolithic run or actual Linux/PostgreSQL acceptance.

Worker research/dataset fixtures now create their owned temporary directories
under the resolved platform temporary root, making the same artifact and dataset
assertions executable on Linux. The test-only change does not relax production
operator `/private/tmp` destination or symlink/ownership guards.

Older operator tests assumed macOS import and staging paths. Their bounded
[test-only loader](scripts/tests/operator_fixture.py) admits six reviewed public
source paths, checks and substitutes only the exact pinned ROOT assignment in
memory, and scopes nested imports and pure artifact reads to the fixture checkout.
It denies real subprocess/urllib activity and repository-private file reads and
restores its patches. The relocated-checkout case copies only an explicit public
source/artifact list. Railway export fixtures inject only their owned temporary
staging comparison; default invalid-destination refusal remains unpatched. No
production operator source, target, credential handling or staging constant is
changed. These fixtures test the current admitted helpers, not a general Python
sandbox or real cloud behavior.

```sh
node --test scripts/tests/check-build.test.mjs
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s scripts/tests -p test_ci_verification.py -v
node scripts/check-build.mjs --prepare-only
```

`--prepare-only` resolves/copies/removes the reviewed snapshot without installing
dependencies or executing a build. Full build installation and fixture pulls are
explicit CI work; they were not performed by the helper unit-test review. All
production deployments, migration/rollback evidence, reader compatibility and
operational budgets remain separately verified release gates.

The earlier scheduling repair passed seven focused sharding and20 workflow regressions,
plus seven portable research/dataset fixture checks. A discovery-only smoke finds
2241 occurrences/54 repeated baseline IDs, split994/1247; this is selection evidence
without test execution or class setup. These intermediate discovery counts are
historical; the final actual run and its larger helper discovery appear above.

## Required native fixture preparation

The full SQL discovery includes the real native driver wrapper and its15 inner
TLS/SCRAM/controller/fault cases. Its previously missing cached Python image and
Linux wheels are now explicit prerequisites. [check-ci-native-wheels.py](scripts/check-ci-native-wheels.py)
downloads only on the exact disposable Dashboard GitHub-hosted Linux amd64
CPython3.12.14 runner. It uses public PyPI, the current hash-required binary lock,
no cache, a sanitized process environment and disabled shared pip configuration.
Explicit CPython/ABI/platform constraints target Bookworm glibc2.36 and compatible
earlier manylinux tags, rather than Ubuntu2.39 or unconstrained Linux/musl binaries.
[Debian target](https://packages.debian.org/bookworm/libc6),
[pip target options](https://pip.pypa.io/en/stable/cli/pip_download/),
[pip configuration isolation](https://pip.pypa.io/en/stable/topics/configuration/).

Pure validation requires all51 locked packages exactly once, matching filename/
internal package/version/Python requirements and platform tags, archive hashes,
owned0700/0600 nonsymlink directories/files and a150MiB whole-bundle limit. A sibling
manifest outside the wheel-only directory binds current lock/helper/target and
exact file inventory. The SQL parent validates the explicit path before copying
it; the sanitized child validates it again. No application environment enters the
container. The existing native fixture remains unchanged: offline hash-required
installation, only synthetic TLS/password data through stdin, owned private tmpfs,
no host ports/mounts or external network namespace. This proves its actual tested
scope when run, not hosted Supabase/native-v2 admission.

For an independently prepared local amd64 bundle, create an owned temporary parent
and its0700 `dashboard-native-wheels` child, containing only the current locked
Bookworm-compatible0600 wheels. `python scripts/check-ci-native-wheels.py
--record-existing /absolute/owned/temp/dashboard-native-wheels` performs only
validation and absent sibling-manifest creation; it downloads/installs nothing,
uses no Docker/network and refuses overwrite. Set `DASHBOARD_NATIVE_SQL_WHEELS` to
that explicit canonical child path before the full `check-worker.py postgres
--allow-isolated-postgres` command. Reviewed cached compatible images/local daemon
opt-in remain separate prerequisites; hosted preparation cannot retag a local
daemon. Loose old bundles fail with a setup message.

Before the image-retry change, combined sanitized helper discovery passed83/83 cases, zero skips, including
16 native bundle regressions. Source-bound discovery-only finds2262 ordinary
occurrences split994/1268 and533 SQL occurrences split94/132/126/181; both preserve
54 baseline repeated IDs. Discovery-only executes no tests/class setups. Actual
hosted pulls/downloads and every group's completion were still required at that
intermediate source. The final receipt above supersedes that pending state.

Run38326083781/sourcea20bcee passes frontend and the actual15 inner native driver
cases (19.462s), but one SQL group fails an opaque image pull; whole-group and
workflow acceptance are not claimed. Public pin/operation/fixed-class diagnostics
and up to three recognized-transient same-reference pull attempts now preserve
the original total240s-per-pin budget. Permanent/unknown or identity failures
still fail, and captured Docker output/credentials never enter logs. No image
fallback is added. After this change all87 combined helper cases pass with zero
skips. All seven actual jobs at the revised head subsequently completed
successfully, as recorded in the exact-source receipt above.

### Completed head c04be4f and pre-acquisition fixture pacing — 2026-10-13

[Run38444382423](https://github.com/TOOTRJ/TheDashboard/actions/runs/38444382423)
at `c04be4fb536c593541603a7e7c6c1140771b139d` completes33m57s. Frontend passes
2m40s, ordinary1/2 pass15m2s/14m8s, and SQL1–3 pass33m53s/24m27s/32m52s.
Both historical/current source-lineage corrections now pass. SQL4 fails25m37s:
237 cases/1472.116s, one original restoration decision error, two allowed timing
skips and zero unexpected skips. The complete source trace, post-COMMIT original
reconciliation and genuine expiry rollback pass. No unfinished job is cancelled
before the next push; the failed run is retained and PR104 remains unmerged.

The first genuine receipt is3,545 microseconds into its second, yielding a
0.996455-second wait for the legacy integral action. Its accepted protective
native guard is2.769208s after that same receipt; the later rollback diagnostic
sees receipt age5.315392s and a live lease. The failed predicate combines source
and lease; its actual guard instant is unobserved. This supports investigating
preparation cost, not a definitive failed-branch or native clock attribution.

The positive test now paces once before its designated first receipt. A real
fixture clock schedules a wait to fraction0.95; the following actual clock
sample becomes the original receipt. It is never rounded down, refreshed,
retried or re-paced after overshoot. The remaining actual ceiling/action wait,
all original wire/ID/current-head/oracle checks, full native source/lease guards
and off-path full/compact equivalence remain. Only the first positive acquisition
uses pacing; retired-ID, post-COMMIT and genuine expiry negatives remain unpaced.
No production/model/native/decoder or server setting changes.

All five actual native cases pass34.233s, zero skips, using pinned CPython3.12.14
and the owned network-none cached PostgreSQL17.6 fixture with exact cleanup.
The first receipt fraction is952,363us, action delay0.047637s and original
protective/decision guard offsets0.787651s/1.741515s. Pair plus delayed equivalence
takes2.182149s. The pre-acquisition host phase0.392364625s is outside that receipt
and cannot be presented as a faster receipt-critical-path operation.
[Exact source-bound local receipt](services/vonneumann/research/portable-restoration-paced-laboratory-2026-10-13.json).
These are paced original-v2 laboratory observations, not an unpaced cold restore,
new-v3 runtime, hosted tail bound or continuous acceptance.

Discovery-only retains2414 ordinary occurrences1045/1369 and602 SQL occurrences
94/128/143/237, with54 baseline repeated IDs and unchanged selection/limits.
Ordinary SHA256 `9f07a0d170c4953b39c8cbe61c06eaeb584609ca2f20466a8f48a94c3f5d3afe`;
SQL SHA256 `2d782fbae39f0b3166507c11830e5c7fed1ea2bb3f57655da12ea7af22771aeb`;
selection SHA256 `be75136c0592a7a2da26707a3d7e4c1e7e740dda639776f6759d23ed64357af1`.
Discovery executes no tests. All seven actual new-head jobs still gate merge.

The earlier35d6aac run's workflow total is38m2s; its longest SQL2 job is37m58s.
Earlier references to37m58s as total are corrected here without changing that
source's individual job reports or relabeling historical measurement artifacts.

### Parallel app/browser verification and local inspection uncertainty

Reviewed Portfolio and Reports/Settings slices are adopted asedbf4d55/846c00bf.
Their controlled/compiler/lint/fake build receipts remain bound to their precise
source. Root's rendered combined fake browser proves finite keyboard/mobile/
preview/theme and owner/acknowledgment/late-reply cases, with exact owned cleanup.
[BROWSER-ACCEPTANCE-2026-10-13.json](BROWSER-ACCEPTANCE-2026-10-13.json) states
that synthetic protocol evidence is not real Supabase/RLS/runtime acceptance.

A315-case complete frontend run passes32,317.481584ms before the two new fake
Portfolio protocol tests. The new protocol cases pass2/2 in221.898ms. A scoped
whole-fixture run then exposes phase ambiguity in an existing test's first-ps
failure injection. Its repair targets only the registered negative PGID's actual
TERM phase, forwarding real TERM/KILL and every final inspection unchanged.
All23 fixture cases pass22,069.801417ms, zero skips. The production helper's
1000ms inspection timeout/final positive cleanup requirements remain unchanged.

The subsequent complete frontend attempt exits1 in a different existing
ignore-TERM descendant case: final exact-group inspection is unavailable. The
full report's count/inspection errno were not retained, so no cause or aggregate
current-source pass is claimed. One separately approved exact-PGID diagnostic
passes10,888.176541ms with actual post-KILL EPERM followed by positive metadata,
then genuine empty-group disappearance. It does not explain or supersede the
failed whole-suite attempt. A metadata-only refusal diagnostic is now separately
reviewed; unknown inspection failures must remain failures, not empty-group
claims. Full next-source CI and relevant actual checks remain required.

### Complete local frontend verification after refusal diagnostics

Source `0609db36b168a803283d57e3302a54c8ebbecaaa` retains bounded,
metadata-only diagnostics for unavailable inspection of an owned process group.
The cleanup predicates, signal order, exact selectors, 1000 ms inspection bound
and requirement for positive final absence are unchanged. No failure is retried
or converted into an empty group. The diagnostic tests include hostile error
objects and fabricated metadata so error serialization cannot expose credentials.

The exhaustive frontend suite passes **332/332, zero skips**, in
22,623.090834 ms using the pinned Node runtime and the explicitly approved
owned-OS-inspection context. The mode-0600 log is retained locally at
`/private/tmp/dashboard-frontend-0609db3-20261013.log`. This is a new-source local
pass; the previous whole-suite failure remains unattributed historical evidence.
Every next-head hosted job and exact release verification still gate merge.

### Pushed head 22bd538 — registry preparation failure

[Run 38458301073](https://github.com/TOOTRJ/TheDashboard/actions/runs/38458301073)
is bound to pushed head `22bd5387ab66cb95ccb73edf59d805b4009d7d73`.
Frontend passes in 2m37s. SQL4 job
[115506607790](https://github.com/TOOTRJ/TheDashboard/actions/runs/38458301073/job/115506607790)
fails in 48 seconds during image preparation: the pinned ECR PostgreSQL manifest
is rate-limited on all three attempts, including the existing 5/10-second
backoffs. Native-wheel preparation and required integration do not run; zero
SQL cases execute in that job. This is preparation failure, not a restoration
rejection or an accepted SQL result. The remaining jobs are allowed to finish;
no cancellation, job rerun, optional SQL gate or older-result substitution.

The exact Dashboard preview `dpl_584BwNfUphmYcqh6HbqErJKv42ic` is READY,
with source 22bd538, branch `codex/dashboard-five-priorities`, repository
`TOOTRJ/TheDashboard` and author `biggrizzly11` visible in the verified project.
Preview readiness does not override incomplete CI or establish production.

The smallest reviewed follow-up coordinates anonymous pulls and transient
backoff within the existing 240-second per-pin deadline, with an owned empty
Docker config and unchanged repository-digest/config/platform verification.
Implementation and exact-source acceptance remain pending. A larger shared
artifact transport stays deferred: Docker save/load does not promise upstream
RepoDigest retention, and GitHub's automatic artifact digest mismatch is a
warning, so neither is sufficient for strict immutable-image admission.
[Docker save](https://docs.docker.com/reference/cli/docker/image/save/),
[Docker load](https://docs.docker.com/reference/cli/docker/image/load/),
[GitHub artifact validation](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow#validating-artifacts).

The reviewed coordination repair is adopted as
`41d4ed00e40956736e1564ebd1e048c629894f6f`. Root executes both complete affected
unit modules: 53 pass, zero skips, in 0.714s, with the workflow capability checker
also passing. These tests mock Docker pulls and sleeps; they do not establish
registry recovery. The original source-specific 53/0.690s candidate proof remains
separate. [Reviewed policy and boundaries](CI-PULL-COORDINATION-CONTRACT.md).

Discovery-only now retains 2,425 ordinary occurrences (1,045/1,380), 602 SQL
occurrences (94/128/143/237), and all 54 baseline repetitions. Eleven new pull/
capability cases add coverage without deleting or deduplicating earlier cases.
Ordinary discovery SHA-256
`1d6bf0c97ab6d1ac1563c38d6be7a950a0dcf8bdbb60c5cca7a6e37e95fe7ace`;
SQL discovery remains
`2d782fbae39f0b3166507c11830e5c7fed1ea2bb3f57655da12ea7af22771aeb`;
selection remains
`be75136c0592a7a2da26707a3d7e4c1e7e740dda639776f6759d23ed64357af1`.
Discovery executes no tests. The current run's ordinary groups pass in
18m58s and 11m6s; three SQL groups remain running at this observation. Wait for
those results before another push so unfinished evidence is not cancelled.

The 22bd538 run then finishes **36m17s** with six passing jobs: frontend 2m37s,
ordinary groups 18m58s/11m6s, and SQL1/2/3 36m12s/29m33s/23m57s. SQL4's 48-second
registry preparation failure is the sole failure. Its restoration cases never
execute, so this run supplies no hosted acceptance of the new positive pacing.
Every job is settled before the next repaired-head push. Complete new-head
seven-job acceptance remains required; no failed job is rerun or omitted.

### Pushed81474c1 — five-attempt quota refusal, all jobs settled

[Run38464960221](https://github.com/TOOTRJ/TheDashboard/actions/runs/38464960221)
is bound to`81474c1f9b65ac0defe0da4a1c061aa88c417561` and finishes35m2s,
FAIL. Actual job summaries report frontend1m56s, ordinary1/2 14m59s/13m59s,
SQL1/2/3 26m43s/25m14s/34m58s, all PASS.
[SQL4 job115529138328](https://github.com/TOOTRJ/TheDashboard/actions/runs/38464960221/job/115529138328)
fails3m6s in image preparation. Its wheel environment step passes18s.
The five original PostgreSQL manifest pulls are rate-limited after the real
13.7868775s stagger; attempts begin13.787/24.026/46.325/87.984/149.780s and
finish13.970/24.120/46.420/88.094/149.879s. Backoffs are
10.054704/22.204467/41.563597/61.685535s. Zero SQL cases execute.

This measures correct bounded retry/refusal under persistent anonymous quota,
not SQL restoration failure or successful recovery. No failed job is rerun,
cancelled, skipped or replaced by historical results. PR104 stays open. The
exact Dashboard preview`dpl_EwKi7hgmUme1x6XbQnKSva2zebzT` is READY40s with
source81474c1, expected branch/repository/biggrizzly11 author, in the verified
project/team. Preview does not establish production or override failed CI.

The next isolated B prototype retains original platform-manifest/config bytes
and verifies every ordered uncompressed layer DiffID. It explicitly does not
claim original compressed registry blobs or restored RepoDigests. Pure
synthetic consistency is separate from actual Docker-format/export/load proof
and an authenticated same-run artifact producer. All seven test jobs remain
mandatory; producer/missing/cancelled/corrupt failures must fail the aggregate.
Current direct verifier/workflow/pins and2400-second SQL deadlines are unchanged.
Actual archive size, byte-hours, transfer/load tails and source-format provenance
must be measured before adoption; no mirror/publisher/shared-credential change.
