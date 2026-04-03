# Nestegg — Retirement calculator

Nestegg is a **retirement planning and scenario modeling** page inside The Dashboard at **`/nestegg`**. It combines a **deterministic** month-by-month projection with **Monte Carlo** paths for probability-style outputs. **Draft state** (inputs, market preset, compare overlay) **auto-saves to `localStorage`**; **named scenarios** persist to **Supabase** when the user is signed in (see `supabase/migrations/20260402120000_nestegg_scenarios.sql`).

---

## Where things live

| Area | Location |
|------|----------|
| Page (UI, layout, wiring) | `src/app/(dashboard)/nestegg/page.tsx` |
| Deterministic projection & hero heuristics | `src/lib/nestegg/projections.ts` |
| Retirement spend/income (incl. survivor phase) | `src/lib/nestegg/retirement-cashflow.ts` |
| Monte Carlo simulation | `src/lib/nestegg/monte-carlo.ts` (`runMonteCarlo`, `runMonteCarloBatched`) |
| Rule-based insight bullets | `src/lib/nestegg/insights-engine.ts` |
| CSV / print report | `src/lib/nestegg/export-report.ts` |
| Saved vs workspace input diff | `src/lib/nestegg/plan-diff.ts` |
| RMD divisors (approx.) | `src/lib/nestegg/rmd.ts` |
| Defaults, `normalizeNesteggInputs`, market presets | `src/lib/nestegg/constants.ts` |
| Local draft only | `src/lib/nestegg/storage.ts` (`nestegg-draft-v1`) |
| Supabase: list, insert, update name, delete | `src/lib/nestegg/scenarios-supabase.ts` |
| DB migration | `supabase/migrations/20260402120000_nestegg_scenarios.sql` |
| TypeScript types | `src/lib/nestegg/types.ts` |
| UI components | `src/components/nestegg/` |
| Formatting helpers | `src/lib/formatters.ts` (e.g. `formatCurrency`) |
| Charts | **Recharts** (`NesteggProjectionChart`, `NesteggSecondaryChart`) |
| Sidebar / shell | `src/components/layout/Sidebar.tsx`, `Header.tsx` |

The page calls **`runProjection(scenarioInputs)`** for deterministic summaries, hero, readiness, and the default single-line chart. **Compare all scenarios on chart** runs three deterministic projections and **`mergeComparisonSeries`**. **`runMonteCarloBatched`** (chunked, `requestAnimationFrame` between chunks) drives the main probability run on the client; **`runMonteCarlo`** remains for sync use (e.g. smaller batches in comparisons). Probability cards, percentile bands (when not in compare-all mode), preset comparison table, saved-plan compare, and **`buildNesteggInsights`** use Monte Carlo outputs where noted below.

---

## High level: what the calculator does

1. **Assumptions** — ages, life expectancy, savings, contributions, return, retirement spending, inflation, salary growth, Social Security, other income, one-time flows, optional tax gross-up on draws, optional RMD floor, household mode, optional **custom MC volatility**, optional **survivor transition** (couple).
2. **Deterministic core** — month-by-month balance from current age through **`planHorizonAge`** with a **fixed** effective return path (see below).
3. **Monte Carlo** — many paths with the same cash-flow logic as deterministic, plus **random monthly return noise**; annual volatility from **risk profile** or **custom %** (`monteCarloVolatilityPercent`). Main run is **batched** so the UI stays responsive.
4. **Market presets (Base / Conservative / Aggressive)** — `applyScenarioToInputs` adjusts return (and conservative inflation) **before** any run; the **scenario tab** is saved with cloud scenarios.
5. **UI** — hero + probability cards + summary cards, main chart (deterministic line, **or** three-line overlay, **or** median + 10th/90th rails), cash-flow chart, preset comparison table, **saved plan** compare + **input diff** sheet, **Monte Carlo volatility** panel, quick what-if, **Export** (CSV + print/PDF), insights, **How it works** sheet, optional first-run tour.

---

## Deterministic engine (`projections.ts`)

Single fixed return path: **nominal** dollars, no explicit fees.

### Effective annual return

1. **Risk profile:** Conservative **−0.5%**, Moderate **0%**, Aggressive **+0.5%** on the typed annual return, then **clamped** to **0.5%–15%** per year.
2. **Monthly compounding:** \(r_{\text{month}} = (1 + r)^{1/12} - 1\) (`monthlyRateFromAnnual`).

### Market preset (`applyScenarioToInputs`)

| Preset | Effect |
|--------|--------|
| **Base** | No change |
| **Conservative** | `annualReturnPercent = max(1, annual − 2)`; `inflationPercent = min(8, inflation + 0.5)` |
| **Aggressive** | `annualReturnPercent = min(12, annual + 2)` |

### Survivor modeling (couple, optional)

When **`enableSurvivorModeling`** is on, after the **earlier** partner reaches their life expectancy (in simulation months), retirement spending scales by **`survivorSpendingRatioPercent`**, and Social Security uses a **simplified survivor benefit** (`max` of the two benefits, plus other income). Implemented in **`retirement-cashflow.ts`** and used by both **`runProjection`** and **`simulatePath`** (Monte Carlo).

### Horizon, chart series, readiness, cash-flow chart

Same as before: **`planHorizonAge`**, year-end series points, readiness / extra-savings hint, **`buildRetirementCashflowYears`** for the side chart. See **`runProjection`** for the full month loop.

---

## Monte Carlo (`monte-carlo.ts`)

- **Paths:** main UI run uses **~1100** paths (batched). Hard cap **1500**. Preset comparison uses **350** paths per row.
- **Volatility:** **`effectiveAnnualVolatilityPercent(inputs)`** — uses **`monteCarloVolatilityPercent`** when set (4–45%), else **`ANNUAL_VOLATILITY_BY_RISK`** by risk profile.
- **RNG:** **mulberry32**, seeded from inputs + scenario.
- **Batched execution:** **`runMonteCarloBatched`** processes paths in chunks and yields with **`requestAnimationFrame`** so React can paint progress; **`runMonteCarlo`** remains for synchronous use.
- **Success / bands:** same meaning as before (success through horizon; p10–p90 bands aligned to deterministic series ages).

---

## Persistence & saved scenarios

- **Draft:** **`nestegg-draft-v1`** — inputs, `marketScenario`, `compareOverlay`.
- **Cloud:** `nestegg_scenarios` — insert, delete, rename, duplicate; RLS per user.

---

## Export

- **`buildNesteggScenarioCsv` / `downloadNesteggCsv`** — assumptions + deterministic + optional MC summary.
- **`openNesteggPrintReport`** — opens a **new tab** with print-friendly HTML; user uses **Print → Save as PDF** in the browser.

---

## In-app help

- **`nestegg-onboarding-v1` (localStorage)** — welcome tour.
- **`NesteggGuideSheet`** — full guide; replay tour.

---

## App shell / hydration note

If you see a **hydration mismatch** in dev tools on **`<body>`** with attributes like **`data-gr-ext-installed`** or **`data-new-gr-c-s-check-loaded`**, that is usually a **browser extension** (e.g. Grammarly) mutating the DOM before React hydrates — not Nestegg or Monte Carlo. The root **`layout.tsx`** sets **`suppressHydrationWarning`** on **`<body>`** (and **`html`**) so those extension-injected attributes do not trigger spurious warnings.

---

## What the model still does **not** do

- No progressive tax brackets; no per-account buckets.
- **Monte Carlo** is a simplified volatility model, not a full institutional simulator.
- Couple / survivor logic is **educational**, not filing-status or SSA-rule complete.

---

## Possible next steps

- Optional **Web Worker** for Monte Carlo (off main thread entirely).
- Deeper tax and account-type modeling.
- Automated tests on `runProjection` / `runMonteCarlo` invariants.

---

## Disclaimer

Nestegg is for **educational planning** inside the app. It is **not** financial, legal, or tax advice.
