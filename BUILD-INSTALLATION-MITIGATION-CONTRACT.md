# Dashboard isolated installation connection-limit contract

This is a bounded build-helper mitigation on the reviewed app base
`f4ea1ef46cc9ab23588bf4008e17e55149f0fcd3`, recorded on 2026-10-13. It does
not establish a successful installation, a production build, browser readiness,
provider availability, or a cause for either earlier failure.

## Exact change and preserved boundaries

`buildEnvironment()` now supplies the fixed child-process value
`NPM_CONFIG_MAXSOCKETS=4`. Its existing inheritance allowlist is unchanged;
an inherited value such as `999` cannot replace the fixed value. The existing
browser fixture receives the same value through its existing call to
`buildEnvironment()`. No shared npm setting, credential, cache, shell startup
file, global installation, or another process's environment is changed.

The npm v11 [configuration documentation](https://docs.npmjs.com/cli/v11/using-npm/config/#maxsockets)
describes `maxsockets` as a per-origin maximum, with a default of 15. Lowering
the helper's limit to 4 is a connection-burst mitigation hypothesis. The unit
proof establishes the environment delivered to the child; it does not observe
the npm client's live socket count, establish the exact npm version of a failed
attempt, or attribute its reset to excessive concurrency.

The exact lock, install arguments, lifecycle, cleanup checks and deadlines are
preserved. Both helpers still use one locked `npm ci --include=dev
--ignore-scripts --no-audit --no-fund` installation with its existing 300,000 ms
deadline, followed only after successful installation by the existing Next
production build with its 600,000 ms deadline. No retry loop, deadline extension,
package change, alternate registry, or successful fallback is introduced.

The helper still creates a fresh owner-marked allowlisted copy, excludes private
environment/SSL/cloud/agent files and existing dependency/build caches, supplies
fake application configuration, and confines npm user/global configuration and
cache paths to that owned copy. The browser fixture still uses only its exact
synthetic loopback backend. The browser fixture helper's process cleanup still
acts on its registered owned children and verifies quiescence before removing
an owned copy. That claim does not apply to `check-build.mjs`, whose unchanged
`spawnSync` execution and cleanup have different semantics. Neither helper is
replaced or bypassed.

## Historical failure evidence

1. The first unchanged-helper attempt reached the existing 300-second locked
   installation deadline. The owned copy
   `/private/var/folders/y2/1vj8vbdx6x72s2g5_r3vlxb00000gn/T/dashboard-ci-build-a2kPKD`
   was removed by normal cleanup and was subsequently observed absent.
   No Next build or server-ready result was
   produced. Its private npm cache/debug files were removed with the copy;
   the available evidence does not identify the installation's cause.
2. The second authorized unchanged-helper attempt failed with npm
   `read ECONNRESET`, `errno -54`, and `ENOTEMPTY` cleanup warnings. The helper
   exited 1 and completed normal owned cleanup; it produced no Ready result
   and started no application server. The bounded private output log is
   `/private/tmp/dashboard-app-f4ea1ef-browser-attempt2-20261013.log`
   (metadata rechecked: a regular mode-0600 file, 2,492 bytes). The failure codes
   and cleanup warnings do not identify which
   network endpoint, transfer, filesystem operation or dependency caused the
   failure, and do not prove the warnings caused the reset.

`/private/tmp/dashboard-app-f4ea1ef-frontend-20261013.log` is an app-test log,
not the failed installation log. Earlier source test/type successes and an older
browser receipt are not relabeled as a successful build of this app source.

## Bounded public reachability observations

The unchanged package lock has SHA-256
`a6c5c1d1cd80203a5a9b191ca3828c551783f10d09e7e2d7d8af32c74919a86b`,
lockfile version 3 and 533 resolved packages, whose resolved URLs are
credential-free `https://registry.npmjs.org` URLs. No lock or package bytes were
changed or downloaded during the diagnostic probes.

At `2026-10-13T20:42:42Z`, credential-free, config-disabled curl HEAD probes
with 5-second connection and 10-second total bounds observed:

| Public resource | HTTP result | DNS / connection / TLS / first byte / total seconds |
| --- | --- | --- |
| npm registry ping | 200 | 0.017047 / 0.142332 / 0.396407 / 0.626228 / 0.626281 |
| exact locked Next 16.3.8 tarball | 200 | 0.014861 / 0.044100 / 0.110216 / 0.164613 / 0.164733 |
| exact locked TypeScript 5.9.3 tarball | 200 | 0.008048 / 0.048016 / 0.129981 / 0.180154 / 0.180210 |

At `2026-10-13T20:43:38.014Z`, a sanitized pinned Node 24.19.0 HTTPS HEAD
probe with a 10-second deadline observed:

| Public resource | HTTP result | DNS / connection / TLS / total milliseconds |
| --- | --- | --- |
| npm registry ping | 200 | 20.999084 / 148.941792 / 407.846209 / 679.905167 |
| exact locked Next 16.3.8 tarball | 200 | 5.848583 / 137.531208 / 406.778792 / 549.478500 |

These are observations at those times, not historical availability proof. HEAD
does not establish complete package-body transfer, a 533-package installation,
extraction/filesystem success, or absence of later connection resets. No response
cookies or headers are retained as credentials, and no application credential or
provider endpoint was used.

## Source binding and focused acceptance

The following hashes bind the final working implementation and tests. They do
not grant installation, deployment, database, worker, or trading authority.

| File | SHA-256 |
| --- | --- |
| `scripts/check-build.mjs` | `249ac44a4063dab2db65a83dcb087d420dc9cb9f08a325d3344841d481994582` |
| `scripts/tests/check-build.test.mjs` | `c9e047cd67fdbf4b310eed1cf5c7d4441e678794136454a859df6165b62a4692` |
| `scripts/tests/browser-fixture.test.mjs` | `f072e94c88345ad973bcef28ca9f39c12beebeaf5b0e54bb35372d2aebef0a2c` |
| unchanged `scripts/browser-fixture.mjs` | `44a81c063f8bd9b6bde6be945f6fbc206f6e4a3f88307d9a90792c17b9c44bc8` |

The two existing helper modules passed 29 cases (6 build-helper and 23 browser
fixture cases), zero failures/cancellations/skips, in 22,198.712 ms under pinned
Node 24.19.0. The command used an `env -i` child with the pinned Node binary,
bounded executable PATH, `TMPDIR=/private/tmp` and `LANG=C`, and ran only
`scripts/tests/check-build.test.mjs` and
`scripts/tests/browser-fixture.test.mjs`. Scoped permission covered the tests'
own synthetic loopback servers and exact owned process-group inspection.

The changed assertions check hostile inherited values, propagation into the
browser environment, and the mocked actual build-execution boundary. Existing
tests exercise only synthetic loopback data and registered owned child cleanup;
they perform no npm installation, Next build or provider operation. Their mock
executor prints the existing build-stage labels without executing those stages.
The one owned test session exited 0 after cleanup; no owned test process remains.

No new build attempt or remote operation has been performed for this change.
Root's local review of the exact four-file slice is complete, including the
corrected historical copy path and the browser-only process-group claim. A peer
read-only review was requested; no additional peer test result is claimed. The
root authorized an exact local four-file commit. Any future installation attempt
requires separate review and keeps the unchanged deadlines, exact lock and owned
cleanup. A successful future attempt would be new dated evidence, without
retroactively diagnosing either historical failure.
