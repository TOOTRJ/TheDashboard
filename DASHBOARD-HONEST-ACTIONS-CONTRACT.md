# APP-02 Reports and Settings honest action contract

This slice fixes false completion and account provenance in Reports and Settings.
It changes no account, provider, wallet, subscription, database, worker, source
contract, model, authentication implementation or cloud project. No backend
feature is activated by removing a fake success message. Header/Home/Analytics,
Portfolio, strategy execution and actual report generation remain separate work.

The owned branch is `codex/dashboard-honest-actions`, based on root's exact
`c04be4fb536c593541603a7e7c6c1140771b139d`. The earlier frozen source branch
remains at `45d2b7aabbb889f4ff628c02a1864e7206192a0d` with unchanged bytes.
Only these four files belong to this slice:

- `src/app/(dashboard)/reports/page.tsx`
- `src/app/(dashboard)/settings/page.tsx`
- `tests/dashboard-honest-actions.test.mjs`
- This contract.

## Resulting behavior

Reports previously waited 1.5 seconds and announced a generated, downloadable
report without producing an artifact or making a request. Both generation paths
now expose disabled buttons with adjacent visible reasons, including the sample
preview. No fake loading state, completion handler, timer, toast, download or
network operation remains. Sample previews still open and close.

Every report figure/trade is explicitly sample data rather than account/bot
activity. Fictional last-generated dates and relative trade timestamps are
removed. The interface no longer claims tax compatibility, available FIFO/LIFO
methods, verified fee tracking, wallet mapping or complete account history.
The sample preview does not promise future actual report contents. Dollar sample
formatting has a fixed locale so SSR/browser defaults do not change its text.

Settings previously reported saved profile/preferences, disconnected wallets and
a payment redirect without performing those actions. These controls are now
unavailable with visible explanations and no success handlers. The sample
profile is read-only, with a reserved example email address; there is no inert
form whose Enter key can navigate or pretend to save. Sample wallet addresses,
balances and primary badge are expressly examples. Wallet connection and
disconnection are unavailable.

Notification controls and trading defaults are disabled sample values. They do
not configure the bot. The existing real `ThemeToggle` is preserved and remains
the supported appearance control on this device. No new preference persistence
or auth behavior is introduced.

Subscription details are labelled examples and no billing date or actual
account subscription is asserted. The example plan dialog is a local preview.
`selectedExamplePlan` changes only the selected preview, while the immutable
`exampleCurrentPlan` remains unchanged. There is no checkout, payment redirect,
upgrade toast or implied entitlement. Example plan names/prices explicitly do
not confirm availability, actual pricing or included features. The unsupported
upgrade action is disabled with a visible explanation.

Disabled-control reasons remain visible beside the controls and have matching
`aria-describedby` references; they do not rely on hovering an inaccessible
tooltip. Profile inputs retain associated labels, sample switches have explicit
accessible names, selection triggers have associated labels and the preview
sheet/dialog have descriptions. Action groups and sample wallet cards wrap or
stack on narrow screens. Actual focus, portal, hydration, layout and keyboard
acceptance require the separate real browser check below.

## Controlled verification and limits

`tests/dashboard-honest-actions.test.mjs` transpiles the actual pages and executes
their hooks, JSX and handlers in an isolated VM with controlled UI component
bindings. It asserts visible provenance/reasons and simulates click/Enter/local
selection. Timer, success toast, request, popup, artifact and storage effects
are forbidden. Tests cover all four report previews, disabled generation inside
and outside the preview, read-only profile/no form, unavailable wallet actions,
sample preference/trading controls, preserved ThemeToggle binding and three
sample tier choices without a current-plan change.

This is a controlled action/JSX regression test. It does not execute React DOM,
Radix native keyboard/portal behavior, actual ThemeToggle persistence, account
authentication, Supabase, payment or download APIs. It does not claim that a
report can be generated or that an account was changed. Root owns the actual
synthetic-browser review for desktop/mobile, preview/dialog keyboard behavior,
visible disabled reasons and preserved theme/navigation.

The reviewed runtime is Node 24.19.0 at the dedicated Codex runtime path; the
shell's Node 25 is not used. Controlled tests/compiler/lint may resolve the exact
Dashboard locked dependencies read-only. No symlink, global upgrade, shared
configuration edit or root `node_modules` write is used. The production check
uses the existing `scripts/check-build.mjs` allowlisted fresh copy with fake
Supabase configuration and fresh locked dependencies, no `.env`, `ssl`, private
CLI files or provider credentials. Its exact owned directory/marker is cleaned
after checks, and heavy builds are serialized with the other Dashboard lane.

## Final controlled and build receipt, 2026-10-13

The final isolated production check passed Next.js 16.3.8 compilation, its
TypeScript check and all 18 generated routes. The allowlisted source snapshot
contained 153 files and 1,354,633 bytes. Its separately invoked TypeScript
`--noEmit --incremental false` and three-file no-cache ESLint check also passed
with zero errors/warnings. All five controlled honesty cases passed, zero skips,
in 209.075292 ms inside that same locked snapshot. The dedicated runtime was
Node 24.19.0. The npm deprecation notice for the existing pinned ESLint 9.39.5 and
Next's missing build-cache notice are existing tool notices; no package changed.

The fresh build copy contained only reviewed frontend inputs and fake Supabase
configuration; the test file was copied in after the production build for scoped
lint/test execution. Its exact ownership-marker cleanup completed. No app
credential or ignored `.env`/`ssl` file was loaded or uploaded. Root dependencies
remained read-only throughout; the final build used its own locked copy. No root
dependency file or cloud project changed. No service was started for this build.

The exact three implementation/test hashes observed were:

| File | SHA-256 |
|---|---|
| Reports page | `ffa2ad5006ee1d9b050f94bf090c555c87ea0171aeb661eda7d6d5e4cf7c0777` |
| Settings page | `967770c0b437672a09e3b3ee7d8c9f65451e3f0d2e1dbd4f4d561fe5ee0d5a17` |
| Controlled honesty test | `48f98a163f4dd2727e50518b12f1be8655b79eabb9b2472f18aeac579284cd39` |

Independent read-only review found no fake success, source/copy or controlled
test blocker in this scope. Root's actual synthetic-browser receipt is pending;
native keyboard/portal/theme/navigation and mobile layout acceptance are not
claimed by the VM/build receipt. APP-02's broader header and real backend
outcomes remain separate acceptance gates. No commit, push or deployment is
implied by these checks.
