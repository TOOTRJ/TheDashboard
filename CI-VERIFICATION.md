# Secret-free Dashboard verification

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
The five-second laboratory guard must remain intact. Test preparation/capture
order and its actual critical-path timing are under review; a failed original
request must not be reinterpreted as accepted or silently rebased.

All seven required jobs at the final corrected head, exhaustive coverage,
explicit skip audit and fresh exact-project/source/author/alias release checks
remain the merge gate. The source count inventories2398 ordinary and600 SQL
occurrences retain54 original repeated IDs; discovery is not execution.

PR/manual triggers have no path/type/branch filters, and main pushes have only
the main-branch filter. The capability validator requires every advertised Node,
type, lint, advisory, build, lock/hash installation, dependency-consistency and
image/integration command; removing one or adding a bypass/filter fails its tests.

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
