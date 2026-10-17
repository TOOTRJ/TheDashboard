# Analytics sample provenance and scoped Header controls

This bounded UI repair is based on reviewed combined local commit
`0e83c3ca2221e408fe07fd901cb8d74959f25ab1`, on private branch
`codex/dashboard-analytics-header-honesty`. Its implementation scope is exactly
the Analytics page, shared Header, one controlled test file and this contract.
It changes no account/profile data, provider endpoint, API, environment,
migration, model, mock generator, strategy evaluator, worker or hosted project.
The separate untracked DB-04 baseline descriptor is preserved unchanged and is
not part of this UI slice.

## Resulting behavior

Analytics previously described generated local charts as the user's trading
performance and presented fixed advice about an uptrend, position sizes and
Solana performance as AI analysis. It now identifies all of its chart/stat
content as samples. Dated portfolio, P&L and win-rate charts retain their
existing local getters and sample range behavior. Exchange volume and fixed
strategy statistics are labeled as fixed examples, not calculations from the
displayed charts, account trades or bot. Unsupported advice and performance
comparisons are removed; no replacement forecast or profitability assertion is
introduced.

The former unscoped Analytics CSV action is removed, including its Blob/object
URL/anchor helper and unused price-series read. A disabled `Export CSV
unavailable` button has an adjacent visible reason: the sample charts are not
connected to an account export. Its button type, disabled state and
`aria-describedby` link are explicit. There is no success handler, file,
download request, popup, silent zero substitution or completion claim.

Header search appears only at `/`, where ActivityTable consumes the shared
search value. The sample date selector appears only at `/` and `/analytics`.
It admits a callback value only when exactly equal to an existing canonical
`7d`, `30d` or `90d` option, without a type cast, trim or coercion. Shared state
and working local getters are preserved; hidden controls do not reset filters
or mutate an unrelated page. An adjacent scope explanation states that
allocation, exchange volume and fixed stat examples do not follow the range.
Neither control configures the worker or filters owner-scoped Nestegg/portfolio
data. Header and page both use the title `Sample Analytics`; the Strategies
Header title/description remain unchanged.

The fabricated notification count and inert notification button are removed;
plain text says notifications are unavailable. Profile, wallet settings and API
key menu entries are explicitly disabled and share a visible unavailable
reason. The actual account display, mobile navigation callback, ThemeToggle and
sign-out callback remain. Sign-out still awaits the existing auth action before
the existing `/login` navigation and refresh. No wallet connection, API-key
management, notification service or profile-save implementation is invented.

## Focused verification and its limits

Pinned Node 24.19.0 ran eight new controlled cases plus the six existing
Strategies preview cases: **14 passed, zero skips, 631.186125 ms** on the final
copy-aligned source. The prior 14-case result (668.798709 ms) preceded the
Header title alignment and is historical. The new
tests transpile and execute the actual Analytics/Header/ThemeToggle TSX and the
actual local mock data module, with controlled JSX, hooks, routing/auth/theme
callbacks and a fixed synthetic date. Unsupported timer, network, artifact,
download, popup and DOM creation calls are trapped. No app environment,
credential, live account or provider request is loaded.

The cases cover visible provenance/advice removal; unavailable export and its
click/Enter absence; unchanged three sample range getters and fixed volume/
stats; Header control scope across nine existing dashboard routes plus an
unsupported subpath; canonical date acceptance and malformed value refusal;
nonempty actual local activity search; unavailable account entries; mobile and
sign-out callback order on all nine routes; and Light/Dark/System dispatch from
the unchanged actual ThemeToggle. The existing Strategies cases also verify
its Header copy and independent external widget bindings without evaluating a
strategy or fetching widgets.

The initial combined test run passed 13 of 14 cases: the controlled fixture's
System-theme label matcher incorrectly assumed text after the child icon.
The matching-only fixture correction preserved source behavior, and the later
14-case results passed. The final test additionally includes `/docs` and
requires the local SOL search result to be nonempty. Whole-project TypeScript
passed on the final implementation; focused TSX/test lint and diff whitespace
checks pass. No package or shared tool was installed or changed.

These tests do not render React DOM or Radix portals, implement native keyboard
or disabled-control behavior, establish hydration/responsive layout, sign out
an actual account or prove a browser download. Nested live widget/market-ticker
effects are not executed by the controlled Header renderer. Actual browser QA
and the integration build remain root review gates. This slice does not close
the broader dashboard sample-data audit, real performance analytics or account
export work. No production/runtime authority or complete audit claim follows
from the tests.

## Preserved behavior and source bindings

The React review checklist was applied: no new data fetching, global listeners,
timers, hooks or state synchronization; hook order remains unconditional;
simple pathname conditions are derived during render; supported actions keep
their existing callbacks; unavailable controls have explicit visible copy and
accessible names/reasons. Charts retain their styles and local data semantics.
Existing responsive Header action wrapping allows unavailable text alongside
the genuine controls; native layout acceptance remains browser QA.

Byte comparisons against the reviewed base verify unchanged ActivityTable,
ThemeToggle, DashboardProvider and mock data files. The MarketTicker function
body remains byte-identical, SHA-256
`96c50f6c948f6f09e0de5a5913a1e0434387d6983a90a7b5677a9e2e617376d3`;
the sign-out handler remains byte-identical, SHA-256
`6aadd49a9b84e151c6f1ae58a7c93d9b7cb6452b53c16d1873e4aa67cb536836`.
These are preservation checks, not live-market or actual-auth acceptance.

| Owned implementation/test | SHA-256 |
| --- | --- |
| src/app/(dashboard)/analytics/page.tsx | 04da4aa2b12bb81ded0d6072d96d1338c6f3548c49cf4427571aa006b36522a4 |
| src/components/layout/Header.tsx | f2a0e7cebb83fdd788f3bd5da629a700aa4605d514fa518bd9669ba2d4db1d52 |
| tests/analytics-header-honesty.test.mjs | 20342eee34ad0b465a6b5b806b472738de50b47cd97ffd2c600a50c9c3492c79 |

Root and security peer completed source, final copy/hash and contract review
with no remaining blocker in this scope. Only the exact four-file local commit
is authorized here; integration build and actual browser acceptance remain
separate root gates.
No remote push, cloud/account operation, database write, finance-model change or
shared-process action was performed. Frozen integer/API/parser/A1/model/Nestegg
commits and the DB-04 descriptor retain their recorded bytes.
