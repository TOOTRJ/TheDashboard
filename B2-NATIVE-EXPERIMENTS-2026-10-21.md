# B2 native experiments — October 21, 2026

**V11b passes the bounded local laboratory: 19 of 19 actual cases, with zero errors, failures or skips.** Full B2 acceptance, runtime/test-path adoption and hosted operation remain open. The failed V8 fourteen-method and V9b nineteen-method attempts retain their own results and source identities. The [machine record](B2-NATIVE-EXPERIMENTS-2026-10-21.json) binds the original receipts, logs, controllers, manifests and six candidate source hashes without copying private raw artifacts into the repository.

## Latest executed result — V11b

The one bounded V11b experiment discovers and executes all 19 methods in 82.504645708 seconds; outer elapsed is 82.686071834 seconds. It exits 0 without timeout, with zero failures, errors, skips, expected failures or unexpected successes. The external guard remains 240 seconds. All 896 source hashes remain unchanged. Normal exact-owned container and child-group cleanup succeeds, with no fallback removal; the empty owned Docker configuration is removed.

This is a network-none local ARM64 PostgreSQL 17.6 laboratory using the existing CPython 3.12.14 environment. Its private source composition is based on `a6aadce78c467d4ef364591c7d06e83013262d91`, not an adopted B2 Git head. The original receipt SHA256 is `fc533b9a7554c0b65f76b208a9140f5717a85de5bf13d730dd1f18bd4a550d7b`; source-candidate manifest `f238558b99bbf59e199fd9e8a1c8d0b5b29584aa7b5bea4e3b6d4c7d09f3efc9`; snapshot manifest `c7ff229f33ecfbbd351f3aa0226a5f7aecfdabfd5db2a40c43fee915f8744f7c`; controller `334820b4d801aa76e63b4a6cf5357f07d8388e1c555d10600a29627b750de49f`. The machine record supplies the log and exact six-file source pins. The exact six files are durably retained in a [review-only patch and manifest](services/vonneumann/research/b2-review-2026-10-21/README.md); worker and test-discovery paths do not load that bundle.

The nineteen passing cases cover the original installation/getter/reserved-Stop path, provisional absence and committed readback, rollback, exact replay, same-writer refusal and malformed/foreign inputs, plus five broker gates. Those gates cover direct-actor denial, no anchor UPDATE right for the sealed owner, preserved rows/released locks on rollback, blocking anchor updates through transaction end, and post-lock reauthorization after trusted-input change. The four-pin Stop DML case passes; it is not the distinct-seven-pin maximum.

V11b changes only two SQL expression sites from executed V9b: extract `(c->'body')` before subtracting `ARRAY['scope','policies']`, in result preparation and original-result verification. The fixture's held SQL digest and provenance follow that source change. All nineteen test cases, the broker, refusal catches, loader and policy remain unchanged. PostgreSQL's operator-precedence rules explain why these parentheses are required. [PostgreSQL 17 operator precedence](https://www.postgresql.org/docs/17/sql-syntax-lexical.html#SQL-PRECEDENCE).

## Remaining first-slice acceptance

Before adoption, independently reconcile encoded UTF-8/escaping, the complete scalar response plus LF, the installation/Stop three-pin and six-pin getter closures, and the full counter vector. The expected installation-plus-Stop vector is 35 retained rows including six bootstrap rows, 31 logical writes and 62 declared keys; derived staging-inclusive touches are 33 rows and 68 keys. These are targets for an independent check, not newly observed acceptance. Do not copy `_cost` as its own oracle or confuse logical credits with physical PostgreSQL tuple/index/WAL costs.

Two controlled native races remain: simultaneous identical originals waiting on one scope must reconcile the winner's committed original without a new ID, and a getter's held parent-SELECT snapshot racing COMMIT must return a coherent absent/head-0 or complete/head-1 observation, never mixed evidence. Then review current-base composition, applicable ordinary/CI results and first-slice source adoption. The fixture still uses trusted `postgres` for the broker; a dedicated NOLOGIN production anchor owner and managed privilege proof remain open.

The distinct-seven-pin state, all sixteen positions and seventy-pin maximum depend on the remaining nine allocator/control kinds; fabricated rows do not establish their native acceptance. Review future maximum accounting's Boolean width (`false` is one byte wider than `true`) and the first slice's null-head assumptions before extending kinds. No complete source/reader/model join, calibrated clock, hosted authority, continuous operation or trading authority follows from this pass. Elapsed time is not a controlled capacity benchmark.

## Actual V8 result

The single owned experiment runs on local ARM64 PostgreSQL 17.6, in a network-none container from the pinned cached image, with the existing CPython 3.12.14 environment and a 240-second external guard. Its source is a private composition based on `a6aadce78c467d4ef364591c7d06e83013262d91`, not an accepted B2 Git head. It discovers and executes 14 methods in 20.792970 seconds; outer elapsed is 20.932361 seconds. Exit is 1, without timeout. There are five error records, nine assertion-failure records and zero skips. Failure records include subtests, so those counts are not disjoint method totals.

Four methods pass: consistent wrong-database binding refusal; refusal of every unimplemented kind; malformed package digest refusal; and the constructor's NULL-capability rejection. These bounded negatives do not prove successful installation, original receipts/replay, committed getters, Stop or accounting.

All nine assertion-failure records contain SQLSTATE 42501, permission denied for `package_inputs`, at the `SELECT ... FOR SHARE` in submit. The sealed native owner can read the private anchors but lacks the UPDATE privilege also required for row locking. PostgreSQL documents that a row-locking SELECT requires UPDATE privilege in addition to SELECT. [PostgreSQL17 SELECT and locking privileges](https://www.postgresql.org/docs/17/sql-select.html).

The five error records instead report an EOF-style writer failure after its helper discards the underlying stderr. They are consistent with the same refusal, but this does not prove that all five have that cause. Preserve them as unresolved original errors; do not replace them with inferred SQLSTATEs.

Normal exact-owned cleanup verifies the container and child process group absent, with no fallback removal. All 896 source hashes remain unchanged; the owned empty Docker configuration is removed. The trial makes no provider or hosted request and activates no runtime. This is not a controlled performance benchmark.

## Preserved earlier attempts

- V4 fails setup because `pg_catalog.boolean` does not exist, SQLSTATE 42704.
- V5 is not executed: source review identifies that SQL uses `bool` while the held loader still expects `boolean`.
- V6 discovers 14 methods but executes zero; independent-constructor comparison raises `b2_independent_constructor_mismatch`. Its failed receipt, source identity and successful owned cleanup remain preserved.
- V7 also executes zero. Its diagnostic identifies projection 3, `original_operations`, with eight actual constraints versus seven reference constraints: the reference fixture omitted the held source's deferred `committed_original_guard` constraint trigger. V8 adds that same source-declared reference guard with all comparisons retained; it reaches the later permission failure above.

Each version keeps its original source and raw evidence privately. No earlier failure is relabeled as a passing retry, and the previous PR110 release-time V6/V7 checkpoint remains dated history. [Independent PR110 acceptance](RELEASE-PR110-ACCEPTANCE-2026-10-21.md).

## V9b failure and preserved unused diagnostics

The V9b broker candidate executes nineteen methods in 42.806939500 seconds but records eight errors and three failures, with zero skips. Its original receipt is `e3d7831d2fd1d91ff0327687a30809a2d70786335353deb558a25cc1c5c5f7d1`; raw log `7f725b914ea0390d2ffa76ebd4872ca38884b1eae30476a3d0c116e01c1ec7d5`. Three broker-denial/reauthorization gates pass, and valid genesis validation advances beyond the earlier row-lock refusal. The generic `b2_invalid_command` catch masks two JSON-body subtraction precedence defects, corrected only at the two expression sites in V11b. The failed V9b source/result is not relabeled as passed.

V10 and V11 are intermediate unused diagnostic preparations. They remain preserved and unexecuted; no result or native acceptance is assigned to them. V11b is the separately pinned executed correction above.

## Historical V9 broker design boundary

The V9 design introduces a static, narrowly scoped SECURITY DEFINER broker that locks fixed anchor rows using the existing trusted fixture anchor owner `postgres`. It grants no anchor UPDATE to the sealed native owner and is not an arbitrary query or lock interface. Its seventeen-function/nineteen-method boundary is retained in V11b. A dedicated NOLOGIN production anchor owner and its managed privilege/revocation proof remain a later gate.

Definer ownership, fixed trusted search path, exact function body/signature and narrowly granted execution must be reviewed together; PostgreSQL's definer-function guidance describes why ordinary default privileges and untrusted names require care. [PostgreSQL17 SECURITY DEFINER hardening](https://www.postgresql.org/docs/17/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY).

Any next experiment requires its own reviewed source and owned bounded launch. Preserve the fourteen-method failed V8, nineteen-method failed V9b and nineteen-case V11b pass as distinct evidence. The remaining gates above still apply despite the passing finite path. No hosted migration is part of this experiment; live trading remains outside the current authorization. [Ordered next work](TODO.md).

## Separate Railway access checkpoint

The earlier read-only identity request returned HTTP 200 with the GraphQL category `project_token_not_found`, classified only through a fixed in-memory allowlist. No raw response or token was printed. This remains historical evidence; expiry, revocation or a connection to the subsequent incident is not established.

The user completes the replacement in ignored mode-0600 `ssl/railway-project-token.txt`. Root now verifies `The Dashboard Worker` / `38facb49-4de9-4d66-85aa-2861e0306dcf`, workspace `Red Jester's Projects` / `f3fcd4b2-e424-4c6b-ac33-91196ccc96e1`, production environment `9bbe52c6-2305-467a-bf39-8d5e1a98e4e4`, and `dashboard-paper-worker` / `8e78ad4b-1d8f-43e7-898a-3882ac5053d7`. Service metadata reports deployment `cf05895d-adc5-427f-873e-82ad6606e5a1` / SUCCESS, one replica, no sleep, restart NEVER, zero overlap, 30-second draining, 60-second health timeout, outbound IPv6 and 0.25 CPU / 500 MB. These are configuration observations, not fresh running-image, TLS, authentication or in-container mode acceptance.

The root-owned name-only inventory at `2026-10-22T01:52:37.472788Z` finds 19 variables: 11 Railway system names and the eight expected explicit names (`PYTHON_DOTENV_DISABLED`, `VN_DOTENV_DISABLED`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `VN_DATABASE_CA_PEM`, `VN_ALLOWED_ORIGINS`, `VN_ENVIRONMENT`, `VN_SERVICE_MODE`). Safe comparisons confirm closed configuration and both dotenv-disable flags; no management token, database/native credential or provider-secret variable name is present. No values are copied here. Current names do not establish what was stored historically or prove exposure absent.

Railway's official status still lists a major outage; its latest observed update at October 22, 01:22 UTC says builds remain unavailable, preventing required redeployments. [Official status](https://status.railway.com/). Its October 21 disclosure describes possible access to customer environment variables, including some decrypted contents, and recommends credential rotation and unusual-usage review as a precaution while affected accounts are investigated. That notice does not confirm this Dashboard account was affected. [Official security disclosure](https://blog.railway.com/p/security-disclosure-wednesday-october-21st).

The hosted gate therefore remains closed. Complete the historical Dashboard-service credential inventory and downstream dependency map, review relevant service/provider usage, and prepare any required scoped rotation with coordinated consumer updates and old-credential retirement. Identify shared consumers before acting; another project's work, shared account settings and unrelated credentials remain outside scope. Platform restoration and subsequent exact-target configuration/TLS/Auth checks precede any hosted activation. The current name-only inventory is complete; historical exposure assessment and the rotation/dependency plan are not. No credential rotation, redeployment or other Railway mutation accompanies this documentation. Local B2 work can continue. [Current incident assessment and action order](RAILWAY-INCIDENT-ASSESSMENT-2026-10-21.md). This follow-up does not rewrite PR110's release-time evidence.
