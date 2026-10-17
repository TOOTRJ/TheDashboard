# Bounded anonymous fixture pull coordination

Date: 2026-10-13. Local implementation from
`22bd5387ab66cb95ccb73edf59d805b4009d7d73`, before adoption or hosted acceptance.
This slice changes only CI image preparation, its exact workflow capability
boundary and controlled tests. It does not change image versions, SQL fixtures,
test selection, native/source guards, worker activation or trading permissions.

The motivating run is `38458301073` at `22bd5387`; SQL4 job `115506607790`
failed during its immutable public ECR image pull after three attempts. Its
required integration step executed for zero seconds. This evidence is a setup
failure, not a SQL result. Other job outcomes must remain separately recorded.
The prior preparation failures and full-suite timing/refusal evidence in
[CI fixture research](services/vonneumann/CI-FIXTURE-RELIABILITY-RESEARCH-2026-10-13.md)
remain historical observations; this local proof does not replace them.

## Closed coordination descriptor

The following JSON has 1423 canonical UTF-8 bytes when encoded with sorted keys,
compact separators and ASCII strings, without a trailing newline. Its SHA256 is
`1d4d8d53081810ebab26b5c2e278a131a4ac2576dd897dfcc1d410d367adaed6`.
It describes the reviewed policy, rather than a self-issued hosted receipt.

```json
{"acceptance":{"hosted_new_head_proven":false,"mock_unit_proof_only":true,"production_worker_authority":false,"registry_availability_guaranteed":false,"trade_authority":false},"base_commit":"22bd5387ab66cb95ccb73edf59d805b4009d7d73","docker_config":{"cleanup":"same-inode-empty-created-directory-via-held-parent-fd-only","directory_mode":"0700","empty_before_each_child":true,"explicit_cli_and_environment":true,"parent":"canonical-real-owned-nongroup-nonworld-writable-RUNNER_TEMP"},"format":"dashboard-ci-pull-coordination-v1","pull":{"jitter_range_seconds":[0,3],"maximum_attempts":5,"per_pin_deadline_seconds":240,"retry_delays_seconds":[10,20,40,60],"stagger_within_deadline":true,"success_after_deadline_refused":true},"repository_id":"1141090963","runner":{"environment":"github-hosted","github_actions":"true","platform":"linux/amd64"},"shard":{"canonical_values":["1","2","3","4"],"initial_offsets_seconds":[0,4,8,12],"variable":"DASHBOARD_TEST_SHARD"},"transient_classes":["rate-limited","registry-unavailable","network-timeout","transport-reset"],"trust":{"raw_registry_blob_equivalence_proven":false,"required_platform":true,"required_repo_digest":true,"required_reviewed_image_id":true,"reviewed_pins_unchanged":true},"workflow":{"added_environment_scope":"exact-image-preparation-step-only","permissions":"contents:read","required_sql_shards":[1,2,3,4],"sql_child_deadline_seconds":2400,"sql_job_minutes":50}}
```

## Preparation and identity

The helper first requires the existing Dashboard repository ID/GitHub-hosted
context and a local Unix Docker socket. It now requires the literal shard string
`1`, `2`, `3` or `4` before filesystem or process work. Missing, coerced, padded,
out-of-range or event-selected shard input cannot silently select a default.
Every shard prepares all three unchanged Linux amd64 image pins.

The workflow adds `DASHBOARD_TEST_SHARD: ${{ matrix.shard }}` only to the existing
image preparation step. The capability validator requires the exact step,
command, environment and position before integration. All four actual SQL jobs,
read-only repository permission, pinned actions, required commands, no-skip
audit, 2400-second SQL child budget and 50-minute job budget remain required.

Each pin starts its existing 240-second monotonic **pull-phase** deadline before
an offset of 0/4/8/12 seconds plus independent 0–3-second OS-random jitter.
Only the existing four transient error classes may retry. Five attempts share
that deadline; retry waits are 10/20/40/60 seconds plus 0–3-second jitter. Waits
and process time never start another 240-second window. An exhausted deadline,
sleep scheduling overshoot or success returned after the deadline is refused.
The maximum planned sleep total is 157 seconds for shard4 if all five attempts
occur with maximum jitter; actual attempts can stop earlier. Permanent/unknown
errors, malformed inspect output or identity mismatch still fail immediately.

The 240-second bound is not a deadline for the entire pin: the existing
post-pull inspect/tag/inspect operations retain their individual 30-second
timeouts. The overall job budget is unchanged and can still expire during
preparation or SQL execution. Python process startup and scheduler delays are
not hard real-time guarantees; a late successful return is rejected, rather
than claimed timely. No new overall availability or latency guarantee is made.

Direct pulls still require the original repository/platform-manifest digest,
reviewed immutable image ID and Linux amd64 platform both before and after the
existing disposable-daemon tag operation. No archive load, equivalent rebuild,
mirror, alternate registry/tag/platform or credential fallback is introduced.
The unchanged pin table remains covered against the reviewed registry evidence.
Docker's content-addressed ingestion remains the existing trust boundary; this
helper does not independently validate every original compressed layer blob.

AWS documents unauthenticated public ECR pulls at 1/s and a 500GB/month ceiling.
Those limits motivate backpressure; they do not identify the quota bucket or
network cause of this particular failure. Staggering reduces synchronized
attempts within one run, without a cross-run/global lock or assured recovery.
[AWS public quotas](https://docs.aws.amazon.com/AmazonECR/latest/public/public-service-quotas.html).

## Private Docker configuration and truthful diagnostics

`RUNNER_TEMP` must be an absolute canonical real directory belonging to the
effective user and not writable by the group or others. Symlinks, missing paths,
files, relative paths, parent aliases and a different owner are refused.
A held no-follow parent descriptor pins its device/inode. The helper creates
one exclusive mode0700 child directory; every Docker process gets that exact
empty directory through both `--config` and `DOCKER_CONFIG`, and its parent
through `TMPDIR`. The existing PATH/locale allowance remains. HOME, inherited
Docker configuration/auth/context, proxies and application credentials are not
copied into child environments. Docker documents `--config` as the explicit
configuration directory selector.
[Docker CLI configuration](https://docs.docker.com/reference/cli/docker/).

Parent and child identity/owner/mode, path binding and directory emptiness are
checked before each subprocess and before successful return. Cleanup calls
`rmdir` only for the same created inode through its held parent descriptor.
There is no recursive deletion, deletion of replacements or shared config
mutation. Unexpected contents or replacement names refuse cleanup and retain
the evidence. A renamed original parent may still have its exact empty created
child removed through the pinned descriptor; the replacement parent is untouched.
This covers ordinary observed local replacement, not hostile same-user process
isolation or a general filesystem sandbox.

Diagnostics add attempt command elapsed time and elapsed time since this pin's
pull-phase start, including the existing post-pull phases. They retain only fixed
operation/state/error classes, public pin identity, bounded policy delays and
trusted-runtime monotonic durations. Captured Docker stderr/stdout, private
environment values and paths are not published. The overall verified-manifests
summary is emitted only after context validation and cleanup succeed.

Controlled cancellation proof is specifically `KeyboardInterrupt` during
staggering or a mocked pull. Cooperative unwinding removes only the owned empty
config. This implementation adds no SIGTERM/SIGKILL or runner-teardown handler
and makes no cleanup guarantee for uncatchable termination. GitHub cancellation
cannot become a successful required SQL result.

## Source-bound local verification

Final local source ran both complete affected unittest modules under CPython
3.12.14, empty child environment, dotenv disabled and bytecode writes disabled:
**53 cases passed, zero skips, 0.690 seconds**. Docker subprocesses and sleeps
were mocked; the existing real sanitized import child did not use Docker.
The standalone workflow capability validator and `git diff --check` also pass.
Earlier candidate observations of 51/0.932s and 53/0.697s are not this final
source receipt. No pull, container, installation, application/provider/DB call,
shared profile write, new action permission, publisher operation or remote
mutation was performed by this proof.

The tests exercise remaining-budget retry/cutoff, all four offsets and all three
unchanged pin identities, permanent/unknown refusal, sleeping/late-success
overshoot, cooperative cancellation, exact child environment, private empty
config lifecycle, invalid shard before FS/process, canonical parent refusal,
parent/name/mode replacement and unexpected-content preservation. Capability
mutations reject missing/duplicated/moved image setup and foreign shard/env.
Existing wheel/hash/runtime/skip-policy regressions remain included.

| Source | SHA256 |
| --- | --- |
| `scripts/check-ci-images.py` | `1d28e16d3db54c5ed5f709c872f0e0b6470e2c85a2a9cdda8d02b2618efc3d5f` |
| `.github/workflows/verification.yml` | `637aec26b0cf858c5844ae6ddbe8eab19450c29b3aa9566dd0a81050a2b423fb` |
| `scripts/check-ci.py` | `a5c64a1611c48fc7cee348efb3b724fb1195687f306c029224d8357d09800a29` |
| `scripts/tests/test_ci_native_wheels.py` | `b9dc50deb43ae0c3ad9a78f3424ce579d2dea692da4fb27453c92fa7e3ad702f` |
| `scripts/tests/test_ci_verification.py` | `6a474f800ff206dd5b4e6a2197a0b5d9b08ceb76e0f0dee171ec0c7526da7d41` |

Root and source peer code/contract reviews completed without a blocker, and the
exact six-file local commit is authorized. Adoption must retain the current
completed/failed run evidence, then require complete seven-check actual
acceptance at the new exact head. No silent green rerun, cancellation of the
currently running evidence, optional SQL skip or freshness widening is authorized.
Rollback is a reviewed repository commit reverting this transport policy and
its exact capability allowance; preserve outcomes and immutable pins.

## Deferred one-producer artifact design

Same-run distribution remains a separate, unimplemented trust/transport policy.
The smallest credible version needs one producer on its own disposable daemon,
three original direct-pull validations, an independently verified export and
four consumers that still execute the complete actual SQL suites. Missing,
failed, cancelled or corrupt producer/artifact must fail every required consumer
setup guard. Bare `needs` skips are insufficient. Same-run/attempt/repository/
commit/helper identity and exact artifact ID/name must be compared independently;
no latest-run lookup, all-artifact download, shared daemon/cache or publisher role.
GitHub's automatic artifact digest mismatch is warning-only, so strict local
digest/content verification is required.
[GitHub artifact transfer](https://docs.github.com/en/actions/tutorials/store-and-share-data).

Two separately versioned verifier choices are defensible: preserve original
platform manifest/config/compressed blob bytes and check all digests, sizes,
ordered decompressed diffIDs and loaded RootFS; or explicitly define a
producer-attested Docker export mapping, independently check original manifest
and pinned config bytes plus every exported uncompressed layer's ordered diffID,
and verify the loaded ID/platform/RootFS. The latter proves the selected runtime
content contract, not preservation of original compressed registry blobs or
RepoDigests. It must not masquerade as the current direct-pull verifier.
OCI configuration binds ordered uncompressed layer hashes; layer DiffIDs and
compressed manifest digests are distinct.
[OCI configuration](https://github.com/opencontainers/image-spec/blob/main/config.md).

Docker save/load documentation promises images and tags, without a guarantee of
original RepoDigest preservation; engine/store/API/archive format must be tested
and frozen before adoption. Candidate upper bounds for a first explicit design
are three images, 64 layers/image, 1MiB per JSON metadata document, 4GiB transferred
bundle, 8GiB total uncompressed layer bytes, 1MiB streaming buffers, 240-second
validation/load budgets and one-day retention. These are unmeasured refusal
limits, not proof the current images fit, affordable storage, or permission to
raise account limits. Reject archive links, duplicates, traversal, sparse/extra
members, unsupported formats and expansion bombs before load. A measured
round trip and hostile-content tests must precede any workflow replacement.
[Docker save](https://docs.docker.com/reference/cli/docker/image/save/),
[Docker load](https://docs.docker.com/reference/cli/docker/image/load/).
