# Paper Dashboard QA acceptance — 2026-10-17

The private three-file repair passes 30 focused component tests, TypeScript, targeted lint with one existing warning, and four finite checks in a freshly compiled synthetic browser fixture. The parent observed the browser checks through CUA. This is preparation for adoption onto the accepted application source; final pull request CI, production release and hosted worker acceptance are separate gates.

The source comes from tracked archive `dd2332dcdc1bb0b63153fabe267c8863fa25b7fb`, with 868 regular files and no Git checkout, credentials, environment files or SSL folder. Only [PaperDashboard.tsx](src/components/probes/PaperDashboard.tsx), its [existing test module](tests/probes/paper-dashboard.test.mjs), and [eslint.config.mjs](eslint.config.mjs) changed. All other 865 files match the archive, and all 868 final hashes still match after the browser run and cleanup. The accompanying JSON binds the archive, exact before/after source hashes, frozen diff and private original receipts.

## What the repair covers

Rendered busy state and the retained control intent now come from React state. Refs remain the synchronous duplicate-submission and original-target guards used by event handlers and asynchronous callbacks. Credential verification is tagged with an immutable owner/token/API identity. Layout cleanup retires the prior identity, and rendering immediately masks status and controls that belong to it, including when a token changes but the injected API object stays the same.

A retired control or archive reply cannot publish private status, errors or replacement intent. Its finalizer can release only its own exact flight and visible busy state. The original run, Start, Stop and archive request identities remain retained for reconciliation or retry. Account replacement still remounts the private dashboard.

Independent review also found an adjacent preexisting manual-history race. History now has a layout-owned immutable context for selected run, follow intent, refresh, API, credentials and legacy reader. Each individual request captures the browse generation as well. A response begun before a manual selection cannot restore the old snapshot, and an old timer cannot begin more reads from its retired selection closure. Reselecting the same run retires the pending reply without permanently stopping later polling.

## Focused and compiled evidence

The actual TSX is transpiled and exercised by the deterministic VM hook harness: **30 passed, zero failures, zero skips**, in 0.847 seconds outer elapsed time. Twenty existing cases remain; ten additional cases cover credential replacement, layout-before-passive cleanup, original IDs, matching-flight busy release, cross-handler locking and the three distinct browse races. The harness rejects render-time ref access, freezes memoized credential objects, separates layout and passive effects, and prevents unmounted setters writing into a replacement owner's hook cells. It is not an actual React renderer or browser.

Separate TypeScript checking passed in 2.502 seconds. Targeted lint passed with **zero errors and one existing `react-hooks/set-state-in-effect` warning** in the unconfigured-endpoint effect. Only this component's `refs` and `immutability` warning overrides were removed. Other warning scopes remain unchanged.

The browser fixture used a fresh locked installation, with 462 packages added in the reported six seconds, private HOME/cache and empty npm configuration files. Install timeout remained 300 seconds and scripts/audit/funding were disabled. The original lockfile was unchanged. Actual packages were Next and eslint-config-next 16.4.2 and React/React DOM 19.2.8. The production fixture compiled in 3.3 seconds and its TypeScript stage finished in 2.8 seconds. It copied 155 explicitly reviewed frontend inputs using unchanged build-helper exports.

Only the owned browser copy replaced application configuration with synthetic loopback URLs, an ownership header and a restrictive connection policy. Its unique localhost hostname used port 62740; the synthetic backend used 127.0.0.1:62739. This compiled fixture does not establish acceptance of the original deployment headers or production credentials.

## Parent-observed browser checks

The parent used its existing CUA browser session and a new background tab, number 42. These are the supplied finite UI/DOM observations; no exported automation trace or screenshot filepath was supplied.

1. A held worker status response, followed by signing in as the same synthetic Alice again, showed an unverified worker, unavailable verified target and disabled Start/Stop. The trace showed reads and no Start. Releasing status restored the fresh verified target.
2. Under `pending-start`, Start trace 173 retained original `a300…`. Same-Alice token replacement verified pending status while Settle stayed disabled. Releasing the retired Start acknowledgment enabled Settle without manual Refresh and retained the original intent. Settle trace 194 reused that same Start ID and reached running, with no second Start.
3. An old held history page for `a200…` did not override deliberate selection of `a100…`, already complete at revision 3. Releasing the aborted old response preserved the new selection.
4. An Alice Start response held at trace 317 was released after signing in as Bob. Bob's configured `b200…` and history `b100…` remained, with 16 Bob private rows, zero Alice private rows, no retained Alice original intent and zero pending barriers.

These four flows are not a claim that all 30 deterministic cases ran in a browser. No real worker, provider, hosted database persistence or trading operation was exercised.

## Cleanup, limits and adoption

The subagent initially had no available browser surface; its IAB attempt created no tab. The parent completed the proof in its existing session and closed only tab 42. Existing CI and Vercel tabs were preserved. An initial sandbox denial of exact process inspection occurred before any cleanup signal; scoped authorized inspection then verified the exact runner command and ownership marker.

Only verified runner 48878 received SIGTERM. The owned runner's cleanup exited zero; runner 48878 and Next process group 48945 are absent, both loopback ports refuse connections, and the exact generated copy is absent. Frozen source hashes are unchanged. No ROOT source, shared dependency, credential, cloud target or unrelated process changed.

The parent and an independent peer reviewed the final source with no blocker. Adoption still requires the appropriate complete frontend checks, original-configuration build, final source CI and release verification. Other QA warnings and worker/runtime joins remain open. Rollback is a reviewed code-only revert of the three paths with normal validation; these disconnected UI changes need no hosted database rollback.

## Current-base integration follow-up

The earlier private 868-file proof and its original receipts remain unchanged.
One additional complete frontend verification uses exact Git archive
`cad3f413ca858998fa953939cc41caa85f91ee7e` plus only the three reviewed QA
postimages. It contains 887 regular files, with manifest SHA256
`d2b5315e6174329340599c5728c78d7d3aa6febf5982af22b0536fa889b64217`.
This private composition is not an invented actual QA Git head. Only current
roadmap/evidence prose is added when adopting these same source bytes.

All 389 Node cases pass with zero failures, skips or cancellations (22.372s).
Full TypeScript passes (5.207s), whole-project lint has zero errors and 40
retained warnings (7.788s), and the advisory gate passes (5.288s). Production
findings are zero; five full-tree entries remain under the existing exact
braces development exception, expiring October26. No exception is widened.

The fresh build uses the original application configuration and unchanged
build-helper exports with 155 archive-derived inputs (1,346,969 bytes).
Its separate locked installation passes in 5.532s and actual Next build in
7.231s, within 13.976s supervised outer duration. Next/config16.4.2,
React/DOM19.2.8, TypeScript5.9.3 and ESLint9.39.5 are the actual locked versions.
All 887 source hashes remain unchanged. Both exact build child processes and
the exact generated build copy are absent; the owned temporary directory is
empty after removing only its own Node compile cache. No test or build repeats.

The original full receipt SHA256 is
`595ee77bf4920eb8e4b6b25ab33b1ebf82822e9ca2e87bc517a60c74d22ece83`.
The [sanitized composed receipt](services/vonneumann/research/qa01c-composed-frontend-2026-10-17.json)
retains exact source pins, results and cleanup bounds. Local acceptance does
not replace actual final-head CI or release verification. PR107 and PR108's
new runs are blocked before any jobs start by GitHub's payment/spending
annotation. No merge or production release is accepted on that basis.
