# Refusal diagnostics for exact owned process-group cleanup

Status: reviewed local slice, 2026-10-13. Isolated branch
`codex/dashboard-owned-inspection-diagnostics` is based on
`846c00bf8d83909be2b55754df36535e7eee4e26`. The helper at that base matches the
root helper's original SHA-256
`a684c3f1e487e74cca367b466708e189962569575a112bd8b82cec5f99435793`.
This slice changes that helper, adds a separate controlled test file and this
contract. Root's other uncommitted changes, the frozen Strategies branch and all
cloud/provider/database configuration remain separate.

## Preserved cleanup requirements

The helper still probes and signals only the exact registered negative PGID.
Darwin queries remain `/bin/ps -g <owned-pgid> -o pid=,pgid=,stat=` with
`COMMAND_MODE=unix2003` and `LC_ALL=C`. Linux still obtains the exact group's
members through `pgrep -g`, queries only that PID subset and resamples group
membership before accepting zombie-only quiescence. Commands retain their
1,000-ms timeout and 262,144-byte output buffer bound.

No query, signal, retry, process selection or cleanup timeout is added or
broadened. Literal status-1/empty/no-stderr results, positive signal absence and
strict exact-group zombie metadata preserve their existing meanings. Foreign,
malformed, unsupported or unavailable metadata remains refusal. A failed TERM
wait still attempts the exact registered group's KILL; its final verification
is mandatory. The copy-removal finalizer still requires successful owned
cleanup. Backend closure/drain and failed-copy retention are unchanged.

This is a diagnostics repair, not a waiver of a failed inspection, permission
to terminate another group, or proof that unknown failures mean a group is gone.

## Closed refusal observation

Only helper-created inspection refusal Errors receive a private WeakMap
association. `fixtureFailureMetadata` returns a detached primitive-field copy
only for that exact associated Error object. Arbitrary `error.inspection`,
copied causes and fabricated Error objects cannot supply that association.
Standard generic error-name/code fields remain closed enums.

The trusted optional `inspection` object has exactly these fields:

| Field | Closed values / meaning |
|---|---|
| `queryKind` | `darwin-group-ps`, `linux-group-pgrep`, `linux-member-ps` |
| `phase` | `membership-before`, `state`, `membership-after`; the actual query stage |
| `cleanupPhase` | `initial`, `term`, `kill` from a private exact-child association; direct untracked calls report `untracked` |
| `status` | Integer exit status 0…255 or null when unavailable/invalid |
| `signal` | Fixed known signal enum, `UNKNOWN`, or null |
| `errno` | Fixed known error-code enum, `UNKNOWN`, or null |
| `stdoutChars` | Returned string's UTF-16 code-unit length, 0…262,144; `OVER_LIMIT` or null |
| `stdoutBytes` | UTF-8 encoding length of that returned string, 0…262,144; `OVER_LIMIT` or null |
| `stderrPresent` | Boolean for a returned string, otherwise null |
| `elapsedMs` | Host monotonic elapsed from query dispatch to refusal construction, including intervening validation; finite 0…10,000 ms rounded to three decimals, otherwise null |

The byte length describes the returned decoded string, not a new attestation of
the original OS pipe bytes. Expected process-state output is ASCII; overlong
and malformed supplied output still refuses. Timings are diagnostic observations,
not CPU benchmarks, worker source clocks or a latency guarantee. Null/unknown
fields supply no success inference.

For ordinary Node assertion-failure formatting, the helper Error's cause
contains only an optional closed code and a frozen detached sanitized observation.
It never retains the original result, raw error, stdout, stderr, environment,
process arguments or private serializer. The WeakMap remains the reporter's
exclusive observation source even if the public cause is replaced. No logging
side effect was added.

Diagnostic collection uses data-property descriptors without invoking supplied
accessor or serialization functions. Native Error names are found through a
bounded descriptor walk. Prepared ownership metadata and group IDs likewise
admit only appropriate data/scalar fields; group processing is bounded to 4,096
slots. Thrown proxy-reflection failures become unknown metadata. This does not
isolate arbitrary JavaScript already executing in the same process or promise
that a custom Proxy's reflection trap never executes.

## Source-bound controlled evidence

Credential-empty pinned Node 24.19.0 runs on the final helper/test bytes:

- `node --test scripts/tests/owned-inspection-diagnostics.test.mjs`: **15 cases,
  zero skips, 254.414709 ms**. Actual helper functions are exercised with controlled
  query results and a controlled EventEmitter ChildProcess. Tests cover exact
  commands/1,000-ms limit/no retry, known and unknown errors, failed versus genuine
  empty results, Linux before/state/after stages, overlong/multibyte output,
  getter/proxy/serializer containment, trusted-error association, detached/frozen
  cause/report views and initial/TERM/KILL controller phases.
- Six selected existing parser/refusal/diagnostic cases from
  `scripts/tests/browser-fixture.test.mjs`: **six cases, zero skips,
  217.840792 ms**. This is the named pure-test subset, not a complete frontend or
  operating-system process test run.
- Scoped ESLint for the helper/new test passes with zero errors/warnings;
  `git diff --check` passes.

These checks launch no real process group, application server, database, worker
or provider connection. Synthetic ChildProcess cases intercept only their exact
synthetic handle and restore the local test wrappers. No root test guard,
backend protocol, package, environment file or shared dependency is edited.

Root's earlier complete frontend run failed the unchanged ignore-TERM descendant
case at the final inspection path. Its ps status/errno was not retained, so the
failure's cause remains unproved. Earlier full-suite passes and a later scoped
23-case pass do not replace it. A separately authorized observation against the
original helper tested that one case in an explicit OS-inspection context: the
real post-KILL probe returned EPERM, successful exact-group metadata established
quiescence, and a final status-1/empty result established disappearance. That
single-case pass is historical baseline evidence, not current-helper full-suite
acceptance or conclusive attribution of the unknown failure.

The private marked report at
`/private/tmp/dashboard-owned-cleanup-diagnostic-hhono7i9/FINDINGS.md`
(SHA-256 `4311d307a8f32625d2540e64c523770529b6c08595f5cbb618a8dd795afa098c`)
preserves that observation and its limitations. Root owns the next integrated
frontend run and will retain its output in an owned mode-0600 log. No new green
run may erase the prior failure. If another inspection refuses, the new closed
observation supports a separately reviewed cause-specific repair.

Final source pins:

| File | SHA-256 |
|---|---|
| `scripts/browser-fixture.mjs` | `44a81c063f8bd9b6bde6be945f6fbc206f6e4a3f88307d9a90792c17b9c44bc8` |
| `scripts/tests/owned-inspection-diagnostics.test.mjs` | `a270e3622d2670b80ef1d86ab6ef7031ecc42bd4549194444f27718000da93db` |

These local diagnostic source pins grant no cloud, native-source, model, trading
or process-isolation authority. Root and source peer completed final read-only
review and authorized the exact three-file local commit. Root's integrated
source-changed frontend acceptance remains separate; no remote operation or root
adoption is part of this local slice.
