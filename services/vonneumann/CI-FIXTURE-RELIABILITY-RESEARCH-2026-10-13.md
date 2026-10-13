# Dashboard CI fixture transport and execution reliability plan

Research date: 2026-10-13. The research itself performed no image pulls, container
execution, package publication, credential/account changes or remote mutations.
Its inspected failed PR104 baseline is
`c58177afe7d22ab17b6ee21da91ec2b9e7d5a73d`; implementation and acceptance of the
subsequent repairs are recorded separately in CI-VERIFICATION.md.

## Recommendation and evidence limits

Treat fixture acquisition and SQL execution duration as separate failure domains.
The current seven-job run has completed with two SQL failures; retain those
failures and do not merge on the basis of partial or older acceptance. The
immediate work is a measured whole-module scheduling adjustment and a separately
reviewed native restoration test critical path. Bounded pull diagnostics and
retry coordination follow that repair; a content-verified fixture transport is
a later prototype.
Compare a single producer with same-run artifacts against a digest-preserving,
repository-linked GHCR mirror. Choose after measuring archive bytes, load time,
storage cost and provenance round trips; neither is a drop-in cache switch.

Historical evidence was supplied by the parent's exact-repository read-only log
inspection, rather than independently fetched by this research agent:

| Recorded run | Observed failure | What it establishes |
| --- | --- | --- |
| Main source `92d3d43`, [run38330331163/job115078724210](https://github.com/TOOTRJ/TheDashboard/actions/runs/38330331163/job/115078724210) | SQL2 image preparation fails in 46 seconds: the pinned public ECR PostgreSQL pull is rate-limited after three attempts with 5/10-second backoffs. | Required SQL did not execute in this job. This is infrastructure preparation failure, not SQL rejection or acceptance. |
| Documentation PR103 source `8f3a1c2`, [run38330293182/job115078281006](https://github.com/TOOTRJ/TheDashboard/actions/runs/38330293182/job/115078281006) | SQL2 job takes 41m6; its 40-minute child reaches `TimeoutExpired(2399.99997319)` during the complete source-transition trace. Earlier source-policy/59-seed methods pass, but no final unittest report exists. | There is a separate execution-duration tail. Partial progress is not complete acceptance; a cache does not solve this CPU/SQL tail. |
| Previously accepted PR102, same baseline code | SQL2 previously completes around 27 minutes. | One successful timing is not a reliable upper bound or a diagnosed cause of the later slowdown. |
| PR104 source `c58177a`, [run38357623351](https://github.com/TOOTRJ/TheDashboard/actions/runs/38357623351) | Frontend passes 2m1; ordinary groups pass 11m28/10m41; SQL1 passes 36m42 and SQL3 passes 28m37. SQL2 fails 40m57 with its required child reaching `TimeoutExpired(2399.999975517)` during the complete source-transition trace, without a final suite result. SQL4 fails 15m39 with 205 cases/869.304s/zero skips and the original decision rejected by `portable_native_final_source_or_lease_expired`. Image preparation passes all four shards. | Two current execution blockers remain. Successful preparation does not explain either. SQL2 partial progress and SQL4's earlier local pass do not close exact-head acceptance. |

In the current SQL2 log supplied by the parent, the native clock, retention and
read-projection cases completed; the first four source-transition methods also
completed before the 93-row complete trace exceeded the parent deadline. A
minimal next scheduling change is to move **the entire defining
`tests.postgres.test_source_transition` module from SQL2 to SQL4**. Static review
finds 15 methods in that class. Preserve its actual SQL, 93-row assertions,
before/after snapshots, discovery order and existing fixture segments. Imported
`EconomicTransitionSqlTests` aliases remain assigned by their own defining
module; preserve their repeated occurrences rather than deduplicating them.
SQL4's observed 15m39 offers the most plausible destination among these measured
shards, but the source module's total duration is not independently bounded. The
new head still needs all four complete required SQL results under the same
2400-second child and 50-minute job budgets; this is a balancing hypothesis, not
a performance guarantee.

The restoration failure is independent of that redistribution. The error text
combines source and lease checks, so its exact branch cannot be inferred from
that string alone. A diagnostic after rollback must label its separately
observed database time, current lease/source/head and original-ID lookup; it is
not an observation at the failed guard instant. Remove redundant restoration
comparisons from the five-second source admission path only if both protective
and decision transitions retain complete restored-state, 13-component,
full-wire and compact-wire equivalence against independently captured actually
current snapshots and requested-only ID oracles. Submit each original request
once, preserve its raw receipt/frame/ID, and leave source/lease guards unchanged.
Delayed equivalence is a saved-snapshot correctness proof; it grants no current
admission authority and no cold-restoration latency claim. A late original
submission must remain a failing positive case, never a rebase, retry or skipped
case.

Current source inspected: `scripts/check-ci-images.py`
SHA256 `e828035d681f33ff3cd8b22a315e8254c925a9bc160b2306e35315de1827fd5f`;
`scripts/check-worker.py`
`3aa1b25bdabd160a6848a4af1443ad3dfbf14a84eb6409c3e40d55e8f6b0644d`;
`.github/workflows/verification.yml`
`9907efaceae57f00e1fadcdb6a6d445f089547cfa394f114e45ef6bfec54a687`.

## What current preparation does

Four required PostgreSQL jobs run on fresh Ubuntu 24.04 runners. Each pulls all
three reviewed Linux amd64 fixture manifests: PostgreSQL17.6, PostgREST14.5 and
Python3.12.14. Each independently verifies platform, approved RepoDigest and
immutable image identity, then supplies the existing fixture tags only on that
disposable daemon. Pulls have a 240-second per-pin budget, three attempts and
fixed 5/10-second delays for allowlisted transient errors. Permanent or unknown
failure stops preparation. The helper does not independently retain and validate
the raw manifest/config/each compressed layer; its normal pull path relies on
Docker's content-addressed ingestion plus the explicit inspect checks.

Workflow concurrency cancels an older run of the same PR/ref; it is not a
repository-wide image-pull lock across different PRs and main. GitHub's standard
hosted jobs receive new VMs, so a Docker daemon cache in one shard is not shared
with another. Runner capacity differs with repository visibility; record actual
runner metadata rather than assuming a particular CPU count. [Hosted runner
reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

AWS documents unauthenticated ECR Public pulls at 1/s and authenticated pulls at
10/s. This supports designing for backpressure, but does not prove that this
job's 429 arose from shared NAT, bandwidth, a particular quota bucket or another
repository. Authentication needs AWS IAM permissions and its tokens last 12
hours; adding it would introduce a new credential/account dependency.
[Public quotas](https://docs.aws.amazon.com/AmazonECR/latest/public/public-service-quotas.html),
[pull/authentication requirements](https://docs.aws.amazon.com/AmazonECR/latest/public/docker-pull-ecr-image.html).

## Options and tradeoffs

| Option | Useful behavior | Required proof / remaining limit |
| --- | --- | --- |
| Bounded retry and stagger, anonymous pinned pulls | Smallest change; reduce synchronized retries with bounded jitter and use the remaining existing deadline intelligently. Keep permanent/unknown failures immediate. | Does not remove upstream dependency. Measure retries and completion; do not blindly loop for all 240 seconds on every error or extend budgets. |
| One same-run fixture producer, four consumers | Fetch upstream once per run, then distribute the identical approved bytes. SQL execution remains parallel on independent daemons. | Needs a new bounded archive/provenance validator, mandatory failure propagation, same-run identity, artifact cost/size proof and load round-trip verification. A failed producer still blocks all SQL. |
| Trusted-main repository cache plus same-run fan-out | Reduce repeated upstream downloads across PRs; a miss can use the same bounded producer path. | Treat all restored bytes as untrusted. Exact keys, approved content verification, trusted writes and eviction handling are mandatory. It is a transport optimization, not a new trust root. |
| Repository-linked GHCR mirror of the three exact platform manifests | Remove public ECR pulls from ordinary PR shards while retaining registry-native digest verification. Public container packages support anonymous consumption. | A separately reviewed publisher must prove byte-preserving copy, exact package ownership/repository association, redistribution/notice handling and consumer provenance. No silent mutable tag or rebuilt equivalent image. |
| ECR authentication/private pull-through cache | AWS supports public ECR upstream caching into a private registry. | New AWS account/IAM/registry/billing dependencies and possibly secrets. Not the preferred next repo-only change; no shared login, account provisioning or billing change is authorized by this plan. |

For GHCR, a trusted publisher can use its repository-scoped `GITHUB_TOKEN` with
only the required package permission; PR/fork consumers must not obtain publisher
credentials. Public package pulls can remain anonymous. Current GitHub policy
says Container registry storage/bandwidth is free, while Actions artifact storage
has separate billing implications; recheck policy and exact account entitlements
before choosing a transport. [Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry),
[Packages billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages).

GitHub caches are unsigned and readable to applicable PRs. Use restore-only
operations for PR consumers, trusted-main writes, no broad restore prefixes, and
a key binding platform, all pin digests, bundle format and validator version.
Cache eviction and the default 10GB repository allowance mean a hit cannot be an
availability guarantee. Store no credentials, daemon directories or workspace
snapshots. [Cache security and limits](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).

## Required archive and provenance contract

Docker save/load supports moving images and tags; the docs do not promise that
the upstream RepoDigest survives every daemon/export format. The current checker
requires that RepoDigest. Do not drop this check because a loaded tag exists or
manually manufacture a provenance marker. Prototype the actual pinned engine/API
round trip first; `--platform` save/load requires API1.48 or later.
[Save](https://docs.docker.com/reference/cli/docker/image/save/),
[load](https://docs.docker.com/reference/cli/docker/image/load/).

The preferred archive prototype preserves original registry manifest/config and
compressed blob bytes in an OCI-compatible content layout. A reviewed validator
must prove the original platform-manifest SHA, config SHA/platform, ordered layer
digest/size inventory, and uncompressed diffIDs/loaded RootFS correspondence.
Also bind format, source repositories, validator/helper SHA, archive/file hashes,
producer workflow/ref/commit/run/attempt, and exact allowed tags. Bound bytes,
entry count, decompression, parsing and time; reject duplicates, path traversal,
foreign references, wrong architecture, extras and unsupported media types before
load or execution. Never extract arbitrary archive paths into the checkout.
[OCI manifest](https://github.com/opencontainers/image-spec/blob/main/manifest.md),
[configuration](https://github.com/opencontainers/image-spec/blob/main/config.md),
[layout](https://github.com/opencontainers/image-spec/blob/main/image-layout.md).

A digest-preserving copy tool is a candidate for a future pinned runner tool,
not an installation performed here. Skopeo explicitly offers `--preserve-digests`
with refusal on an unpreservable digest; platform manifest versus multi-platform
index remains a separate choice. Supply explicit isolated trust/auth files and
verify resulting bytes, not just tool success. Avoid compression/media-type
conversion or rebuilding images. [Official copy contract](https://github.com/podman-container-tools/skopeo/blob/main/docs/skopeo-copy.1.md).

GitHub artifacts can fan out same-run data, but the download action's digest
mismatch is documented as a warning. The consumer's validator must hard-fail its
own digest/content mismatch. Select exactly the intended artifact, not all
artifacts or an unpinned latest run. Attestations can additionally bind the exact
repository and signer workflow; they prove producer provenance, not upstream
Supabase build authenticity or safety. [Artifact transfer/validation](https://docs.github.com/en/actions/tutorials/store-and-share-data),
[attestation verification](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/increase-security-rating).

Producer failure must produce failing required SQL checks. A bare `needs: prep`
causes dependent jobs to skip, and GitHub documents skipped jobs as successful
for required-check purposes. Design explicit failure propagation: required shard
jobs run their setup-result check even when preparation fails and fail without
claiming execution; a complete acceptance gate checks producer plus all four
actual SQL results, coverage and audited skips. Cancellation cannot become
success. [Needs behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs),
[skipped-check behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions).

## Bounded implementation and rollback sequence

1. Retain PR104's actual seven outcomes and both current failures. Review the
   intact source-module redistribution and independent restoration critical-path
   repair, then require seven complete outcomes at their exact new head. Keep
   earlier failed preparation, deadline and freshness evidence separate from any
   later acceptance; do not widen guards or execution deadlines.
2. In a later isolated PR, add private-safe phase/module timings and anonymous
   jitter/stagger tests. Preserve immutable pins, 240-second per-pin pull limit,
   2400-second SQL child limit, 50-minute job limit, occurrence order/multiplicity,
   fixture segmentation and current skip audit. Use an explicit empty owned
   `DOCKER_CONFIG` for every child; do not rely on a default runner profile.
3. Build pure hostile-archive tests before any consumer loader: corrupt/missing
   blob, substituted config, altered diffID, wrong platform, stale helper, foreign
   producer, archive path/symlink/duplicate/bomb, missing artifact and cancellation.
4. Measure one authorized disposable hosted round trip without app data/secrets:
   approved original bytes → archive/mirror → consumer load → complete manifest,
   config/RootFS verification → existing fixture smoke. Missing cache/setup fails.
5. Choose producer/artifact or mirror only after byte/time/cost measurements.
   Pin new action/tool SHAs and update the verification capability tests, exact
   source inventories and mandatory dependency-failure tests. Do not enable cache
   writes or package publication from untrusted PR code.
6. Run all seven existing verification outcomes plus any mandatory preparation
   result at the exact new head. No optionalization of required SQL, ignored
   setup failure, global prune, shared daemon, account-wide configuration or
   automatic substitution of an alternate version/platform.
7. Roll back by selecting the prior reviewed transport and exact digests via a
   reviewed commit. Disable only this repository's new producer/cache/mirror
   consumption. Preserve evidence; do not delete broad caches/packages, modify
   other projects or weaken the SQL gate. Integrity, platform or producer mismatch
   fails closed. A cache miss may use one explicitly approved fallback to the same
   original digest within the same finite preparation budget; it cannot restart
   the deadline or turn a failed mandatory producer into successful SQL checks.

Actions artifacts and Packages share storage allowances; cache storage is
separate. Standard public runner minutes do not establish free archive storage.
Measure retained byte-hours before artifact fan-out, use short reviewed retention
and do not increase account limits or billing. The Railway $20/month ceiling is
not permission for GitHub billing changes. [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Ordered TODO candidates and deeper measurements

- **CI-IMAGE-01:** classify preparation separately from SQL execution, add bounded
  jitter/remaining-budget policy and explicit owned configuration tests. Record
  each pin's attempts, fixed error category, elapsed time and cancellation cleanup.
- **CI-RESOURCE-01:** retain parent deadline failure and add per-module setup/test/
  teardown timings and actual runner/engine/resource metadata. Compare the same
  source/pins over independent hosted runs; diagnose CPU, memory, storage, Docker
  overhead and provider availability separately. Do not infer the slowdown cause.
- **CI-IMAGE-02:** measure and prove a complete immutable archive transport on a
  disposable runner, with authenticity-negative tests and no accepted SQL skips.
- **CI-IMAGE-03:** compare trusted cache/artifact and public repository-linked
  mirror availability, transfer/load p95/p99, byte-hours, cold-miss behavior,
  digest preservation, licenses and credential/attestation policy. Decide before
  publication or any new permissions/account cost.
- **CI-SHARD-02 (immediate):** review the entire
  `tests.postgres.test_source_transition` defining module move from SQL2 to SQL4
  against the now-recorded current SQL2 timeout and SQL4 timing. Keep all
  occurrences, repeated IDs, original fixture segments and deadlines unchanged.
  The existing portable-transition move to SQL3 did not bound baseline SQL2;
  the next distribution also requires actual complete new-head acceptance.
- **CI-ACCEPT-02:** exact new-head full coverage plus corrupted-cache,
  producer-failure, cancelled/missing-artifact and no-run gate regressions.

Deeper research must quantify actual upstream errors and quota scope without
logging credentials; per-image compressed/uncompressed bytes and cache hit
rates; manifest preservation across classic/containerd stores and pinned APIs;
artifact/cache service failure and poisoning boundaries; trusted signer/ref
verification; repeated hosted resource tails and balanced module scheduling.
Neither extra retries nor a cached image establishes SQL performance, continuous
worker readiness, source freshness, production activation or profitability.

## Next.js security check on October 13

Read-only primary-source check at 2026-10-13 14:50 UTC; installed Next.js and
`eslint-config-next` remain pinned to 16.3.8. The full October8 official notice
still schedules an out-of-band October14 update for two Critical and one High
upstream dependency vulnerabilities and says impact, affected versions and
upgrade instructions will accompany the update. It provides no patch-version
selection or affected range yet. [Official advance notice](https://nextjs.org/blog/upcoming-nextjs-security-update-october-2026).

The npm registry's current `next` dist-tags expose stable `latest:16.4.0` and
`canary:16.5.0-canary.9`; this is version availability, not proof that the planned
security fixes are included. The maintainer advisory page retrieved in this
check shows September/August publications; no October14 advisory or upgrade
range was found on the checked pages. That bounded observation does not prove
the absence of every possible upstream advisory. The separate
`eslint-config-next` dist-tag page could not be retrieved by the web tool, so no
fresh metadata claim is made for it. [Official npm metadata](https://registry.npmjs.org/-/package/next/dist-tags),
[maintainer advisories](https://github.com/vercel/next.js/security/advisories).

Next.js16.x remains Active LTS and15.x Maintenance LTS; the project need not
downgrade or adopt a canary to stay on a supported major. Keep SEC05B open until
the actual security release supplies affected/fixed versions, then review the
smallest supported compatible patched upgrade together with matched tooling,
lockfile, route/auth/cache behavior and exact-head deployment checks. Do not
claim 16.3.8 safe from the forthcoming vulnerabilities or 16.4.0 patched from the
announcement alone. No dependencies were changed. [Support policy](https://nextjs.org/support-policy).

## Measured catalog compilation hypothesis — 2026-10-13

A bounded read-only A/B in a newly owned network-none PostgreSQL17.6 fixture
examines the exact catalog function body, rather than an EXPLAIN of its opaque
wrapper. The original native SQL SHA256 is
76e23d44a296c838238e5545c9ea498eb86d2ac5caee9798236aee1f8a5bf5c4;
the extracted pure-query body SHA256 is
ca1c520fa5eb4b69bd7d03a834c8fd2dfd6d163871c566ce64dac4097ad96bb6.
Both read-only transactions use the fixture installer and pg_catalog,pg_temp,
and roll back. No commit/advance function or source admission is executed by
the measurement. Package setup and exact owned cleanup are separate fixture work.

Default jit=on has estimated query cost1121.99 against jit_above_cost100000,
with no JIT section, planning1.470ms and execution4.935ms. Transaction-local
jit=off also has no JIT section, planning1.349ms and execution4.658ms. Both
produce the same catalog digest. One pair is not a latency distribution; it
does not support compilation as the cause of the hosted restoration expiry or
justify changing server settings. The fixture/native profile remains unchanged.
Nested semantic costs and hosted CPU/client scheduling remain unmeasured here.
[PostgreSQL JIT decision rules](https://www.postgresql.org/docs/17/jit-decision.html).
