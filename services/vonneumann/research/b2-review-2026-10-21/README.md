# B2 first-slice source retained for review

This directory preserves the exact six-file V11b candidate that passed the
19-case local PostgreSQL experiment. The source is stored as a review patch;
it is not installed in worker or test-discovery paths and has no automatic
execution or hosted migration step. Full B2 acceptance and runtime adoption
remain open.

[The manifest](manifest.json) pins each candidate file, the patch and the original
experiment evidence. [The patch](candidate-v11b.patch) contains the SQL, held-source
validator, fixture, nineteen tests, finite policy and candidate contract. Its
original source base is `a6aadce78c467d4ef364591c7d06e83013262d91`; PR110 later
changes the CI partition, with release merge
`02f90563c5ececd4f89a3dd92796601b9abdce7b`. A later adoption must review the actual
composed source rather than treating this archive as an installed package.

The actual experiment executes all 19 methods with zero failures, errors or skips
in 82.504646 seconds. Exact owned container/process cleanup passes, and all 896
source hashes remain unchanged. This proves the tested installation, original
replay, committed getter, rollback, four-pin reserved Stop/accounting and five
anchor-lock boundary cases within the closed synthetic laboratory.

The anchor locking function is owned by the existing trusted `postgres` fixture
owner. A separately reviewed dedicated `NOLOGIN` owner is required for production.
The source does not grant anchor mutation privileges to the native owner or
actors. Maximum admitted-wire/escaping charges, broader getter/concurrent-original
proofs, the full seven-pin Stop path, the remaining allocator/control transitions,
and source/reader/model/hosted joins retain their separate gates. The finite policy
and authority fields remain unchanged; a passing experiment grants no provider,
worker-running or live-trading authority.

[The experiment record](../../../../B2-NATIVE-EXPERIMENTS-2026-10-21.md) preserves
earlier failed attempts and the precise acceptance limits.
[TODO.md](../../../../TODO.md) gives the current dependency order. Do not apply this
patch to Supabase or treat it as an unattended service release.
