# PR110 release acceptance — October 21, 2026

The three-ordinary-group CI repair is released. [PR110](https://github.com/TOOTRJ/TheDashboard/pull/110) passes all eight required jobs in [run39187444654](https://github.com/TOOTRJ/TheDashboard/actions/runs/39187444654), then merges as `02f90563c5ececd4f89a3dd92796601b9abdce7b`. The merge time is October 21 in Denver / `2026-10-22T01:16:35Z`. The [machine receipt](RELEASE-PR110-ACCEPTANCE-2026-10-21.json) retains the exact observed identities, jobs and checks.

PR head `b42f8f80450e896baf4b9cd0cd5f13bb06a6c153`, actual Actions checkout `7b6d45ba3883b6ecde5aaac9f86b8fc8908e21f3`, and the actual merge have identical Git tree `9dfb3786ab3488124cacb9f7eef2f39b89f2b592`. The release verifies `TOOTRJ/TheDashboard`, immutable repository ID `1141090963`, using the dedicated `biggrizzly11` account. Later documentation does not claim that its own source head ran these jobs.

| Required job | Actual duration | Conclusion |
|---|---:|---|
| Frontend tests, types, lint and isolated build | 1m 21s | Success |
| Ordinary worker and helpers (shard 1/3; SQL opt-in skips reported) | 19m 06s | Success |
| Required owned PostgreSQL and PostgREST (shard 4/4) | 26m 26s | Success |
| Required owned PostgreSQL and PostgREST (shard 3/4) | 26m 12s | Success |
| Required owned PostgreSQL and PostgREST (shard 1/4) | 36m 18s | Success |
| Ordinary worker and helpers (shard 3/3; SQL opt-in skips reported) | 15m 55s | Success |
| Ordinary worker and helpers (shard 2/3; SQL opt-in skips reported) | 10m 13s | Success |
| Required owned PostgreSQL and PostgREST (shard 2/4) | 37m 37s | Success |

The reviewed matrix has one frontend, three ordinary and four PostgreSQL/PostgREST jobs. Only the complete prospective-model/source-admission modules move to ordinary group 3; other assignments, all cases and 54 repeated IDs, fixture segments, skip rules, SQL images/groups and 1,500/2,400-second child deadlines remain. The original local 2,085-executed-case proof and the earlier failed/blocked attempts retain their own scope; these job conclusions are not fabricated hosted case counts. [Earlier repair evidence](RELEASE-CI-ACCEPTANCE-2026-10-18.md).

## Separate post-merge confirmation

Root later checks the actual main-source [run39704739120](https://github.com/TOOTRJ/TheDashboard/actions/runs/39704739120): it is completed SUCCESS, with all eight job conclusions successful on `02f90563c5ececd4f89a3dd92796601b9abdce7b`. This supplements the original PR run without replacing its receipt, durations or tested-tree evidence. Neither run accepts a later documentation commit.

## Exact Dashboard production

Vercel project `the-dashboard` / `prj_wFUe9k9USVreOQcmQKNWRAVsx5fH`, team `orderoftheredjester` / `team_8iNNxiNjrOseD4gdSCHkQEzF`, is verified through the signed-in project/team settings. Production [`dpl_4DiPn3ojEE4pfLftypmeL4dXRTHk`](https://vercel.com/orderoftheredjester/the-dashboard/4DiPn3ojEE4pfLftypmeL4dXRTHk) is READY in 22 seconds from the actual merge. Its current canonical alias is [the-dashboard-chi.vercel.app](https://the-dashboard-chi.vercel.app).

The read-only smoke receipt at `2026-10-22T01:19:09.857Z` passes all four checks: login 200; anonymous root 307 to `/login`; anonymous test API 401; authenticated zero-row test API 200 with no returned rows. Writes are zero. These checks do not establish a complete authenticated browser workflow, native worker operation or continuous paper trading.

## Remaining work and preserved failures

The following V6/V7 notes record the release-time checkpoint. The separate [B2 experiment record](B2-NATIVE-EXPERIMENTS-2026-10-21.md) is authoritative for subsequent V8/V9b failures and V11b's 19-case bounded laboratory pass. That private source is not adopted into runtime/test paths or accepted as full B2/hosted operation, and none of these later experiments is part of PR110's CI or production acceptance.

B2 stays private and unadopted. V6 discovers 14 tests but runs zero: class setup refuses at the independent constructor comparison with `b2_independent_constructor_mismatch`. Exit is 1 without timeout; original source hashes remain unchanged, and the exact owned child group/container are absent after cleanup. The original V6 receipt is pinned in the machine record. A subsequent root-reviewed V7 diagnostic also runs zero cases and identifies the missing deferred `committed_original_guard` constraint trigger in the reference fixture; a forward correction is being prepared with the comparisons retained. This diagnosis is not native acceptance. V4's `pg_catalog.boolean` setup failure and V5's prelaunch SQL/loader mismatch remain separate preserved failures.

Next is the smallest reviewed B2 diagnostic/correction and a separately reviewed bounded experiment. Maximum admitted-wire/escaping charges, deferred accounting, original replay/refusal, commit/getter isolation and the remaining source/reader/model path still require their own evidence. Full seven-pin Stop, the remaining transitions and hosted/sustained acceptance are not implied by this release. [Current order](TODO.md).

No Supabase or Railway target was freshly verified or changed for PR110 release. At that release-time checkpoint the Railway metadata failure was unclassified; neither token expiry nor a current worker-state check was inferred. The later classified diagnostic, completed token replacement, successful identity/service/configuration checks and outage/security assessment belong to the [current checkpoint](B2-NATIVE-EXPERIMENTS-2026-10-21.md#separate-railway-access-checkpoint) and [incident record](RAILWAY-INCIDENT-ASSESSMENT-2026-10-21.md), not fresh Railway verification for this release. Hosted activation remains blocked pending that assessment and platform recovery. No migration, credential, provider, billing, wallet or shared-project change accompanies the release. Keep the worker closed pending its acceptance gates and retain the approved $20/month pilot design ceiling.

Rollback is a reviewed source revert of the five coordinated CI files with matching partition/policy tests and subsequent required verification. This CI-only release needs no database or worker rollback. The earlier PR108/PR109 acceptances remain unchanged. Live funding, signing, swaps and activation remain outside the release authority.
