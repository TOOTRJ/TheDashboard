# CI worker workload redistribution — 2026-10-17

The complete prospective model module moves to ordinary shard1 so it runs separately from the expensive source-admission inventory. The two-file change preserves every case, fixture boundary and existing deadline. The balanced full local run passes; all seven final-head CI/release checks remain pending. Earlier local success did not prevent the actual amd64 deadline failure.

## Observed failure and its limits

PR107 head `dd2332dcdc1bb0b63153fabe267c8863fa25b7fb`, GitHub Actions run `39014680277`, ordinary worker shard2 job `117344192855`, reached the unchanged 1,500-second child deadline. The job lasted 25m31s. Its last reported case was `tests.test_source_admission_v3.SourceSealTests.test_outcome_nullability_and_current_self_inventoried_seal_refuse`. This is an incomplete test run caused by the deadline; it does not establish an assertion failure in that last case or in the source-admission implementation.

For the same head/run, worker shard1 passed in 14m52s and frontend passed in 2m40s. All four required PostgreSQL shards passed: shard1 38m23s, shard2 39m33s, shard3 34m16s, shard4 26m30s. The complete run therefore has six passing jobs and the one ordinary deadline failure. It remains failed and unmerged; those native passes do not replace a complete new-head run.

Earlier local ordinary shard2 success at approximately 728 seconds remains useful historical evidence for its own machine and source composition. It did not supersede this actual Linux/amd64 CI timeout or prove that the hosted workload fits its deadline. Local and CI resource differences remain material; scheduling is a mitigation hypothesis until measured and exercised.

## Exact candidate and focused evidence

The two-file candidate adds the complete defining module `tests.test_prospective_ga_v3_model` to offline shard1 through the existing `HEAVY_MODULE_SHARDS` mapping. Its 20 model cases move together. The complete `tests.test_source_admission_v3` module, with 40 cases, stays on offline shard2. No test is divided by method name or given a separate selector.

The only changed files are `scripts/check-worker.py` and `scripts/tests/test_worker_sharding.py`. The original patch SHA256 is `aa3a123ff44f0f73f20c075909d690525bfffffa59352cf6fabf98bda2db95ed`. Final helper SHA256 is `b2cc6f472ce8deaf0f491a6a2f930ba8e83143dae07d742c236ac42f365bb9f7`; test SHA256 remains `d9ca3e0c8d09cf4ce180b6dab1d7e1f0ad95b08f46ce761f93b0154cebe4191b`. The final two-line comment names run 39014680277 as the historical reason; AST equivalence confirms no functional change from the tested candidate. The new partition regression verifies order and occurrence counts, including a repeated test ID, and compares actual module/class fixture event sequences across interrupted module segments for the original and selected suites. Existing regression coverage remains present.

One focused, credential-free CPython3.12.14 run passed all 11 sharding tests in 0.008 seconds with zero failures, errors, or skips. This proves the tested selection/fixture behavior, not workload balance. Independent source review found no selection or fixture blocker.

The candidate preserves two ordinary shards, four PostgreSQL shards, the 1,500/2,400-second deadlines, discovery inventory, assertions, existing skip policy, repeated occurrences, fixture boundaries, image identities, and workflow behavior. It introduces no runtime, database, provider, or deployment operation.

## Required acceptance chain

The separately authorized passive timing diagnostic completed all 60 cases with zero skips: complete model 20 inclusive 122.732878041s; complete source-admission 40 inclusive 250.224282041s. Its retained receipt SHA256 is `0ef10e530c8bcae511765759310bf95adcf8dc4d34c36176ab7549d6f21b24dd`. This finite local measurement does not establish hosted balance. The source-seal 16-case sum was 232.806888418s; admission 24-case sum 0.526605331s; inclusive totals also include setup and surrounding work.

The original frozen 882 local full composition measured ordinary shards 416.774s/728.155s. Moving the measured model block gives only the first-order local estimate 539.507s/605.422s; it excludes any changed resource contention and is not a Linux/amd64 guarantee. One balanced full ordinary composition now passes on that frozen 882-file B1 snapshot with exactly the final two-file candidate. It preserves every discovered occurrence, all 54 intentional repeated IDs, and existing module/class lifecycle boundaries. This one composition replaces redundant baseline/B1 reruns; it does not replace final CI.

The original receipt SHA256 is `53f9298410c6e421356f5a059a69b9fba102a479f971349d5c6e54ea547f687d`; source manifest SHA256 is `acde518483be0646ace2d5a21a789947cb74b6ae43727c3087cca120f0373c38`. Its source composition is the Git archive at `dd2332d`, fourteen new B1 paths, and exactly the two changed CI files; the other 880 source files are unchanged. This private composition is not an actual Git head. Discovery contains 2,736 occurrences / 54 repeated IDs. The run reports 2,602 tests and actually executes 2,084, with 533 audited canonical PostgreSQL opt-in skip entries (518 method-level and 15 class/module entries), zero unexpected skips, failures or errors. Another 134 discovered occurrences never start because their class/module setup is skipped; skip entries are not a count of all unexecuted occurrences.

Shard1 selects 1,092, reports 1,009 and executes 835 in 562.709 test seconds / 564.959081 outer seconds. Shard2 selects 1,644, reports 1,593 and executes 1,249 in 628.682 test seconds / 630.675162 outer seconds. Both return zero within the original deadline. Both exact owned process groups are absent, and all 882 source hashes remain unchanged. No retry, native opt-in, provider request or hosted operation occurs. B1 is present only in this local composition and remains outside PR107. These actual local durations supersede the estimate for this composition, without becoming a hosted timing guarantee.

Acceptance still requires all seven mandatory jobs to complete successfully on the exact final PR head, followed by the existing review and release gates. Timing diagnostics, a local full pass, and an earlier successful shard cannot substitute for those final-head results. No release is recorded by this receipt.

## Rollback

If redistribution is rejected, revert only the new model-module hint and its dedicated partition regression, retaining all previously existing policy tests. Re-run the focused sharding suite and verify inventory, occurrence multiplicity, fixture segmentation, shard counts, and deadlines against the chosen head. A subsequent remote CI run remains a separate action. Rollback needs no runtime, database, credential, image-pin, or environment change.
