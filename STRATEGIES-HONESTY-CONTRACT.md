# Strategies concepts and unavailable historical evaluation

Status: isolated local candidate, 2026-10-13. Base is
`edbf4d55fb49b71e4c395c066d1a236c8a275084`; branch is
`codex/dashboard-strategy-preview`. Root owns integration, actual browser
acceptance and release. This slice changes the Strategies page and only its
route title/description in the shared Header, with one controlled test file.

The earlier page displayed seeded generated trades and metrics on initial
render, then reported another fabricated historical backtest as completed after
a timer. Its controls did not run an independently verified historical
evaluation. Keeping that table would continue to present generated numbers as
measured results, so the page now has no results, profits, trade table, risk
scores, progress or completion notification.

The historical evaluator is visibly unavailable. Its disabled button has an
adjacent reason and no action, keyboard handler, timer or artifact callback.
Five predefined strategy concepts and parameter values remain read-only,
explicitly labelled examples which do not run a backtest or configure the bot.
No historical dataset or evaluation is claimed. The mock library remains
byte-identical; the page imports only its existing static concept and selector
metadata, rather than invoking its generated-result functions.

The existing external TradingView widgets remain. The eight supported symbol
choices and six chart timeframe mappings alter the external chart properties
only. The existing separate one-hour analysis is explicitly labelled with that
interval, so changing the chart timeframe does not imply a local evaluation or
change the analysis interval. The actual widget source is unchanged. No claim
is made that the selected pair is available, data is live/fresh, an external
script loaded, or a widget signal is a strategy score. An ordinary external
TradingView link retains `noopener noreferrer`.

The page and route Header agree on “Strategy Concepts” and the unavailable
evaluator. This does not implement an evaluation engine, retention/data policy,
financial formula, API, model, provider integration or cloud change. Other
shared Header controls and notifications remain outside this slice.

## Controlled verification and remaining gates

The credential-empty pinned Node 24.19.0 run of
`node --test tests/strategy-preview.test.mjs` passed six cases in
418.187375 ms, zero skips. The harness executes the actual transpiled TSX and
local concept function with controlled hooks/components. It checks absent
generated-result UI, visible unavailable action/reason, every supported symbol
and interval mapping, invalid selector values, all example parameter text, and
the actual route Header copy. Forbidden mock operations, timers, artifact
creation, network and completion notifications throw in the controlled harness.
External widgets and React DOM are deliberately not executed by those tests.

TypeScript passes with incremental output disabled. Scoped ESLint has zero
errors and the preexisting shared Header unused `Wifi` warning; this slice does
not remove that unrelated import. Node's existing typeless TypeScript module
warning does not change the package configuration. `git diff --check` passes.
A fresh source-bound fake-configuration production build passed all 18 routes
with Next 16.3.8 on pinned Node 24.19.0, from 153 tracked frontend inputs /
1,334,654 bytes. The existing helper used its own locked dependency installation,
literal fake application values and owned empty npm configuration files; its
successful finalizer removed the exact marked copy. No server was started.
The build is bound to this branch's base plus the reviewed Strategies source,
not to a later root integration of other parallel slices. Root's actual browser
check remains pending. Controlled component callbacks are not evidence of native keyboard,
portal, layout, external widget availability or real provider behavior. No cloud
target, application credential or production data is used by these tests.

Current implementation and unchanged dependency pins:

| File | SHA-256 |
|---|---|
| `src/app/(dashboard)/strategies/page.tsx` | `df53f9a862d7d22a211fa7e48fc84c3da29c4297d965a4cf6782cb30a088f404` |
| `src/components/layout/Header.tsx` | `eb907364a131c4fb4d44ae44d966e1b51b6e053c3330c53e14a96eb77f04da48` |
| `tests/strategy-preview.test.mjs` | `79efabfad721e47ce001330bc6fe98ba5ea6e61d9f4d0f9ccb1f80017cfd4fd5` |
| unchanged `src/lib/mock/strategies.ts` | `dc2e1cdbc0761b7dae73342a08646c5c1e511609e09fe996bea211c8858cc67d` |
| unchanged `src/components/strategies/TradingViewChart.tsx` | `791d809b59280af2e11e7c5bce7c05cd655267836063f846dd6c3277f0a474ad` |

These are local source pins, not provider or deployment attestations. The
contract's own bytes are reviewed separately to avoid a self-hash cycle.
