# App local acceptance — 2026-10-16

Fresh local Node, type, lint, production-build and scoped browser acceptance
covers clean app source `7dd5b116ac1bd0709aeb5118b9877fb3315e186b`, on
`codex/dashboard-app-release`, composed over PR104 source `e0048002c8e387a2d4ad5021c4207ba9329c3de5`.
The source and lock stayed unchanged before/after the local checks; the parent
also observed the compiled browser source clean. These two evidence files were
created afterward and are the only new worktree files. No hosted release follows
from this record. [Machine-readable record](APP-ACCEPTANCE-2026-10-16.json).

## Fresh dependency and source verification

The actual worktree installation uses Node **24.19.0**, npm **11.9.0**, Next and
`eslint-config-next` **16.4.2**, React/ReactDOM **19.2.8**, and ESLint **9.39.5**.
The lock SHA-256 remains
`8bdc3b4b786c94753676d5ce8e05e03321b271d9b773f571872004bf28a39463`.
One fresh locked `npm ci --include=dev --ignore-scripts --no-audit --no-fund
--registry=https://registry.npmjs.org` succeeds in **8.375 seconds**, installing
462 packages. Its whitelisted child uses a new owned mode-0700 task directory,
empty private npm user/global configuration, private cache/HOME/temp paths,
fixed `NPM_CONFIG_MAXSOCKETS=4`, disabled Next telemetry and no application keys.
Only the worktree's ignored dependency symlink was removed; its shared root
node_modules target was untouched. The worktree now has physical local dependencies.

The bundled Node has no adjacent npm CLI. The successful invocation explicitly
runs the existing npm CLI with that pinned Node; no global tool was changed.
The initial missing-adjacent-CLI launch performed no installation. Reading the
installed config package's package.json through Node exports was unsupported;
the verified versions come from the actual installed package files, followed by
the successful real framework build. Neither diagnostic is an application defect.

| Check | Observed result |
| --- | --- |
| Complete frontend/Node suite | **379 passed**, zero failures, cancellations or skips; 30 files; reported duration **22,547.778458 ms** |
| TypeScript | **Passed**, incremental cache disabled; **5.700 seconds** |
| ESLint | **Passed: 0 errors, 69 warnings**; **8.143 seconds** |
| Separate original-configuration isolated build | **Passed**, **15.762 seconds**; actual Next **16.4.2**, fresh fake-configuration locked install |

The retained warnings are 18 `react-hooks/set-state-in-effect`, two
`react-hooks/immutability`, 28 `react-hooks/refs`, three
`react-hooks/exhaustive-deps`, and 18 `@typescript-eslint/no-unused-vars`.
No source or lint configuration was changed to obtain these results. The install
also retains ESLint's existing deprecation notice; no upgrade was performed here.

The original-configuration build copies **155 tracked allowlisted inputs /
1,344,506 bytes**, installs 462 packages, displays **4.1 seconds** for compilation
and **3.0 seconds** for TypeScript, and builds **18 routes**. Its original
`next.config.ts` source is retained and its application values are fake. No owned
build snapshot remains after successful helper cleanup. This build is separate
from the browser fixture's configuration replacement described below.

## Scoped compiled browser observations

The following facts are actual observations reported by the parent, rather than
an invented automation trace or timestamped recording. The owned compiled fixture
uses the same **155 files / 1,344,506 source bytes**, owner
`1a1e8e88-bfac-4b1d-8fdb-e90204578326`, a unique `*.localhost` app hostname on
port **57860**, and synthetic backend `127.0.0.1:57859`. Only the owned browser
copy's configuration is replaced; the worktree's original configuration is
unchanged. Accounts and API data in this fixture are synthetic.

- Home explicitly identifies generated/fixed content and the absence of account
  trades/live quotes. Fictional Copy and Explorer actions are disabled.
- The native LINK details button opens a described dialog with **Return and
  Space**. Escape and Close each leave **zero dialogs**, return focus to the
  original button, and leave the body pointer-events observation empty. The
  restored-focus LINK button's observed `animationName` after Escape is `none`.
- Analytics explicitly says Sample, disclaims account/bot metrics, and disables
  CSV with an adjacent reason.
- Alice's mouse Sign out passes. Bob's login → Portfolio → full reload → mouse
  Sign out also passes against the synthetic backend. An earlier single
  old-app/root logout failure remains historical with **unproved cause**; these
  successful flows do not establish why it failed or a permanent corrective cause.
- At **390×844**, login and the navigation sheet reach Analytics with document
  width **390**. The immediate **Home → Analytics** observation sees **one
  dialog**. A separate **Analytics → Terminal** test explicitly waits with
  `getByRole(dialog).waitFor(hidden)` and succeeds: its later observation has
  **zero dialogs**, empty body pointer-events and document width **382 ≤ 390**.
  The immediate read is not treated as a stuck dialog, nor is an unmeasured
  latency guarantee inferred. The viewport is reset.

Tabs **39/40** are closed. Before normal SIGTERM, the parent verifies fixture
parent **75557** using its exact owner marker and command. The fixture exits **0**
and the exact owned copy `/private/tmp/dashboard-ci-build-QiNA8Q` is verified
absent. This records that fixture's cleanup; it does not imply any broad process
cleanup or ownership over another agent's processes.

## Evidence, remaining gates and preserved history

The JSON records SHA-256 bindings for all **18 changed app/API source files and
four regression files**, plus package/lock/config/build/browser-helper inputs.
The original private acceptance summary and all retained private logs were
re-read and their hashes, byte counts, owner and mode-0600 checks verified before
this record was written. Only bounded filenames, counts and hashes are included;
no credential, environment-file contents, browser cookies, screenshots or
invented trace/timestamps are published.

The October13 final receipt is unchanged, with SHA-256
`7a004c309d5be74597ff70a0c8e7a809c2912b0b8a440b2cace129392a34066b`. Its Next16.3.8/browser/frontend evidence remains dated and is not
relabeled as this new Next16.4.2 acceptance. Earlier installation/dialog failures
also remain in their historical records.

This finite local acceptance does **not** establish hosted Vercel release,
actual Supabase authentication/RLS or API persistence, provider data/freshness,
paper/native worker integration, runtime persistence, continuous operation, full
accessibility, all-route browser coverage, or live trading/signing authority.
Exact release-head CI, project/source/alias checks and the separately ordered
native/database/runtime gates remain required. No source edit, lint-baseline
expansion, hosted mutation or deployment is performed to create this record.
