# Home sample provenance and fictional activity actions

This bounded UI slice is based on local commit
`2e54ab8b5cb003dc31d81822468a4a3604447768`, on private branch
`codex/dashboard-home-sample-provenance`. It owns exactly Home, KpiCards,
Charts, ActivityTable, one new controlled test and this contract. Header,
Sidebar, provider/auth/API/model code, mock generators, migrations, environment
values, hosted projects and external widget sources are unchanged. The separate
DB-04 descriptor remains untracked and unchanged, outside this slice.

## Behavior and preserved calculations

Home now states that prices, holdings, metrics, charts and activity are
generated or fixed examples, with no account trades or live quotes loaded.
`Live Feed` becomes `Sample ticker`; `Your Holdings` becomes `Example holdings`.
The ticker timestamp is explicitly a local clock, not quote time. The existing
local/UTC welcome clocks and animation intervals retain their original
behavior; none establishes provider quote freshness.

Each KPI title is explicitly a sample. Its percentage label now describes
`sample change over selected range`: the unchanged mock getter compares the
last selected value with the beginning of that selected range, rather than
evaluating a separate previous trading period. No numeric formula, seed,
format, trend, range or change direction is altered.

The generated crypto chart, its tooltip and loading text identify sample
prices. Holdings allocation and exchange volume identify fixed examples and
their independence from the selected sample range. The plots retain their
existing data getters, axes, colors, legends, tooltips and animation behavior.
Unused preexisting imports were removed after focused lint reported them;
there is no plotting-library or package change.

The activity table and detail dialog identify generated sample trades and
fictional transaction/wallet identifiers. The existing shared and local search,
timestamp/total sorting, eight-row paging, page reset, row selection and dialog
close remain. They manipulate only local example data, not owner account rows
or the worker. No explorer URL or wallet connection is constructed.

The old clipboard helper, copied-success state/check icon and success-reset
timer are removed. Copy and explorer buttons are explicitly disabled with a
shared visible reason and `aria-describedby`; the copy button also has an
accessible unavailable label. Both buttons have type `button` and no action or
keyboard handler. The reason accurately describes unavailable actions for the
fictional abbreviated identifiers; it does not promise that the browser blocks
manual text selection. No clipboard request, premature success, network
navigation or transaction acknowledgment is emitted.

## Controlled evidence and limits

Five focused cases execute the actual nested local TSX and mock getters under
controlled hook frames and owned synthetic effect/timer queues: **5 passed,
zero skips, 583.823833 ms** on pinned Node 24.19.0. They cover:

- Page/nested metric/chart/table provenance and the local-clock label.
- All three 7/30/90-day ranges with exact unchanged displayed KPI/trend/price
  values, and unchanged fixed allocation/volume.
- All three activity ranges and both directions of timestamp and total sorts,
  comparing actual row IDs with independently sorted local source values.
- First/last-page boundaries, previous/next behavior, combined global/local
  search with nonempty results, empty results, and search/range page resets.
- Actual row-selected dialog details and close, disabled copy/explorer reasons,
  no callbacks, and no clipboard/network/navigation/artifact side effects.

The initial test run passed four of five cases; a cross-VM array prototype
difference caused strict comparison to fail although the row ID values matched.
The fixture normalized the independently expected ID arrays into the outer
test realm without changing source behavior or removing value assertions.
Subsequent five-case results passed. The final source also corrects the KPI
comparison label and states that actions are unavailable without claiming
manual text cannot be copied. Whole-project TypeScript, focused lint with zero
errors/warnings, and diff whitespace checks pass on the final source.

These are controlled TSX/callback tests, not a React DOM/portal/keyboard/hydration
or elapsed animation-time implementation. The fake queues settle existing
timeout effects; interval callbacks are registered but not automatically run
as a live clock or ticker feed. The fixture disposes its own fake queues and
traps real clipboard, fetch, popup, download and DOM creation. It reads no app
environment, credential, live account or provider, and starts no server.
Actual browser accessibility/layout/keyboard acceptance and the integration
build remain root gates. Existing animation timer ownership and performance
were not redesigned or proved by this provenance repair.

This does not establish real dashboard prices/performance, historical strategy
evaluation, trading readiness, native-source authority, account persistence or
complete audit acceptance. It does not change paper/live trading or any hosted
data. Other page/Sidebar sample claims remain separate scoped audit work.

## Source preservation and review

The React checklist was applied: hook order remains unconditional; no new
listener, fetch, timer or state synchronization is introduced; sample controls
retain their existing callbacks; unsupported actions are disabled with visible
and accessible reasons. Existing responsive/card structure remains, with no
new finance-model or account flow.

Byte comparisons against the reviewed base confirm unchanged Header,
DashboardProvider and `src/lib/mock/data.ts` (SHA-256
`e116aea4e8a44ef1023012aadccf62fbc54f1feb880cb5f261bcac0fef077aa0`).
ActivityTable's filter/sort/page computation and sort-handler block remain
byte-identical, SHA-256
`a451d80a47bcba04075b65e6c75c482ab6142b7740f5b531b1b64d99c1cba6f3`.
The controlled behavior cases, rather than these comparisons alone, establish
the finite local preservation result.

| Owned implementation/test | SHA-256 |
| --- | --- |
| src/app/(dashboard)/page.tsx | 1f5003d1396558ab2eebe250db82f91fd15fbfe2eae5b065ea792d9a9ded1f12 |
| src/components/dashboard/KpiCards.tsx | 6478745c8a5ece0639c50588d58cb488539bba5c814a958c2b3391205f11593a |
| src/components/dashboard/Charts.tsx | 969e7a40f19279c1773b5b548260506a8d677b68db2a34352acc9a0a1d92fe53 |
| src/components/dashboard/ActivityTable.tsx | f8601b37cbcb2ec82a2a48e7c55e42eedd5f82cf9dc089709f1ff34b4a233c78 |
| tests/home-sample-provenance.test.mjs | e7412ceac2e467f71c3820e211d81058d846ae2079e46ac1c628a446f20285d8 |

Root and security peer completed the six-file source/test/contract review with
no remaining blocker within this bounded scope. Only the exact six-file local
commit is authorized here; the combined integration build and actual browser
checks remain separate root gates. No remote, root-checkout, cloud/schema, provider, shared-tool or shared-
process operation was performed. Frozen prior commits and the DB-04 descriptor
retain their recorded bytes.
