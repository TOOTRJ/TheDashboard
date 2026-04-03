# Nestegg — Retirement calculator

Nestegg is a **retirement planning and scenario modeling** page inside The Dashboard. It lives at the **`/nestegg`** route. **Draft state** (inputs, scenario tab, compare toggle) **auto-saves to `localStorage`** and restores on return; **named scenarios** can be saved **locally** or to **Supabase** when signed in (see `supabase/migrations`). This document explains structure and **math** at high and low levels.

---

## Where things live

| Area | Location |
|------|----------|
| Page (UI, layout, wiring) | `src/app/(dashboard)/nestegg/page.tsx` |
| Projection engine & insights | `src/lib/nestegg/projections.ts` |
| RMD divisors (approx.) | `src/lib/nestegg/rmd.ts` |
| Defaults, `normalizeNesteggInputs` | `src/lib/nestegg/constants.ts` |
| Local draft + saved scenarios | `src/lib/nestegg/storage.ts` |
| Supabase CRUD | `src/lib/nestegg/scenarios-supabase.ts` |
| DB migration (run in Supabase) | `supabase/migrations/20260402120000_nestegg_scenarios.sql` |
| TypeScript types | `src/lib/nestegg/types.ts` |
| Nestegg components | `src/components/nestegg/` |
| Slider (Radix) | `src/components/ui/slider.tsx` |
| Sidebar / shell title | `src/components/layout/Sidebar.tsx`, `Header.tsx` |

The UI calls `runProjection(...)` whenever inputs or scenario change. Charts read the returned **time series**; cards and hero copy read **summary fields** on the same result object.

---

## High level: what the calculator does

1. **You set assumptions** — current age, retirement age, life expectancy, savings, contributions, expected return, retirement spending, plus optional inflation, salary growth, Social Security, other income, and one-time cash flows at retirement.
2. **The engine simulates month by month** from **now (current age)** through **life expectancy**, updating a single **portfolio balance**.
3. **Before retirement**, the balance compounds and you add monthly contributions (which can grow each year with salary growth).
4. **After retirement**, the balance still compounds, but each month the model subtracts **net spending**: retirement spending minus Social Security and other monthly income, with spending and those incomes stepped up by **inflation** each retirement year.
5. **Outputs** include: balance over time (chart), balance at retirement, whether money lasts to the end of the plan, approximate age when the balance hits zero (if it does), a simple **readiness score**, and (when relevant) a rough **“save more per month”** hint.

Optional **flat marginal tax** on portfolio draws and a simplified **RMD floor** (Uniform Lifetime divisors) are available; there are **no real tax brackets**, separate account types, fees, or Monte Carlo. The core remains a **deterministic, nominal-dollar** simulation.

---

## High level: the math in plain language

### Two phases

- **Accumulation:** Portfolio earns a **compound return** every month. Each month you also **deposit** a contribution. The contribution amount can **increase once per calendar year** in the model (salary growth), matching “raises” in a simple way.
- **Decumulation (retirement):** Portfolio still earns the same monthly compound return. Each month you **withdraw the net cost of living**: spending minus recurring income (Social Security + other). Spending and those incomes **grow once per retirement year** at the inflation rate. **One-time** income and expense hit the balance **once**, on the **first month of retirement**.

### Effective return (what actually gets compounded)

The annual return you type is adjusted in two ways before it becomes a monthly rate:

1. **Risk profile** (Advanced): Conservative **−0.5%**, Moderate **0%**, Aggressive **+0.5%** to the annual return, then the result is **clamped** between **0.5%** and **15%** per year.
2. **Scenario tab** (Base / Conservative / Aggressive): Applied **before** the projection runs by changing the **annual return** and (for Conservative only) **inflation** in a copy of your inputs — see `applyScenarioToInputs` in `constants.ts`.

So: **scenario tweaks the inputs → risk profile tweaks return inside `runProjection` → monthly compounding uses the final effective annual return.**

### What “lasts through life expectancy” means

The simulation runs through **`planHorizonAge`**: your **life expectancy**, or in **couple** mode the **maximum** of your and your partner’s life expectancies. If the balance **never goes negative** before the end of that horizon, the plan **lasts**. If it hits zero, the model records the approximate **depletion age** (continuous age: current age + months elapsed / 12). The UI treats “success” as **depletion is null** or **depletion age ≥ plan horizon**.

### Readiness score (app metric, not advice)

The score is a **heuristic** (0–100) that rewards: lasting the full horizon, non-negative **first-year** monthly cash flow (income minus spending, ignoring portfolio), and having projected **nest egg at retirement** in the ballpark of a **25× annual spending** rule of thumb. It penalizes early depletion and very early retirement when the plan fails. Labels map from the score: **Excellent**, **Strong**, **Needs Attention**, **High Risk**.

### “Extra monthly savings” hint

If the plan **does not** last to life expectancy, the code runs a **binary search** on **additional** monthly contribution (0–20,000) added **uniformly** through the working years, re-running the full projection each trial, to find a **minimum** extra amount (rounded to the nearest $25) that makes the plan last. If no amount in range works, the hint is omitted.

---

## Low level: implementation details and formulas

### Monthly rate from annual return

Let \(r\) be the **effective** annual return as a decimal (e.g. 7% → 0.07). The **equivalent monthly** compound rate is:

\[
r_{\text{month}} = (1 + r)^{1/12} - 1
\]

Implemented as `monthlyRateFromAnnual` in `projections.ts`.

### Time indices

- `planEndAge = planHorizonAge(inputs)` — `max(lifeExpectancy, spouseLifeExpectancy)` in **couple** mode, else `lifeExpectancy`.
- `totalMonths = (planEndAge - currentAge) × 12` — months simulated (if zero, a single chart point is emitted).
- `monthsWorking = max(0, (retirementAge - currentAge) × 12)` — months with **your** primary contributions.
- `spouseWorkMonths = max(0, (spouseRetirementAge - spouseCurrentAge) × 12)` in **couple** mode — months with **partner** contributions (same salary-growth curve).
- Loop: `monthIdx` runs **1 … totalMonths** (inclusive).

### Order of operations **each month**

For each `monthIdx`:

1. **Grow:** `balance *= (1 + r_month)`.
2. **Primary still working** (`monthIdx <= monthsWorking`):  
   `yearIndex = floor((monthIdx - 1) / 12)`.  
   `balance += monthlyContribution × (1 + salaryGrowth)^yearIndex`
3. **Partner still working** (**couple** and `monthIdx <= spouseWorkMonths`):  
   `balance += spouseMonthlyContribution × (1 + salaryGrowth)^yearIndex`
4. **Retired** (`monthIdx > monthsWorking`) — primary has stopped working for spending purposes:  
   - On the **first** retired month only: `balance += oneTimeIncome - oneTimeExpense`.  
   - `yearsRetired = floor((monthIdx - monthsWorking - 1) / 12)`.  
   - `spend = monthlyRetirementSpending × (1 + inflation)^yearsRetired`  
   - `income = (socialSecurityMonthly + otherRetirementIncomeMonthly) × (1 + inflation)^yearsRetired`  
   - If **couple** and `monthIdx > spouseWorkMonths`, add partner SS with its own retired-year index for inflation.  
   - Let `netFromPortfolio = spend - income`.  
   - **RMD (optional):** if enabled and `primaryAge >= rmdStartAge`, `rmdMonthly = ((balance × taxDeferredShare) / divisor(floor(primaryAge))) / 12` using `uniformLifetimeDivisor` in `rmd.ts`.  
   - **Tax (optional, flat marginal):** if `netFromPortfolio > 0` and tax enabled, `draw = netFromPortfolio / (1 - marginalRate)`; else `draw = netFromPortfolio`. Then `draw = max(draw, rmdMonthly)`.  
   - If `netFromPortfolio <= 0`: `balance -= netFromPortfolio` (surplus), then if RMD &gt; 0 subtract **RMD** as an extra outflow.  
   - If `netFromPortfolio > 0`: `balance -= draw` as above.
5. If `balance < 0`, set `balance = 0` and, if not already set, `depletionAge = currentAge + monthIdx / 12`.

**Nest egg at retirement** is the balance **after** processing the **last working month** (`monthIdx === monthsWorking` when `monthsWorking > 0`). If `monthsWorking === 0`, it is taken **after** one-time flows on the first retired month, **before** that month’s recurring net withdrawal (see code paths in `runProjection`).

### Chart sampling

A point is appended to the **series** when `monthIdx` is a multiple of **12** (end of each simulated year) or equals `totalMonths`, so the x-axis is roughly **age at year-end**: `age = currentAge + monthIdx / 12`.

### Monthly gap / surplus (summary card)

This is **not** portfolio-based. It is:

\[
\text{socialSecurityMonthly} + \text{otherRetirementIncomeMonthly} + \text{(spouse SS if couple)} - \text{monthlyRetirementSpending}
\]

using **entered** values (first-year, nominal), for a quick “income vs budget” read.

### Scenario adjustments (`constants.ts`)

| Scenario | Effect on inputs |
|----------|------------------|
| **Base** | No change |
| **Conservative** | `annualReturnPercent = max(1, annual − 2)`; `inflationPercent = min(8, inflation + 0.5)` |
| **Aggressive** | `annualReturnPercent = min(12, annual + 2)` |

These adjusted inputs are what get passed into `runProjection` for that scenario’s run.

### Compare-all on chart

Three projections are run (Base, Conservative, Aggressive) with the **same** underlying form inputs; series are **merged by age** in `mergeComparisonSeries` so Recharts can plot three lines.

### Secondary “retirement cash flow” bars

`buildRetirementCashflowYears` builds **15** years of **annual** totals for **expenses** and **income** only, using the same inflation growth on spending and income as in the main simulation (year index `y = 0 … 14`). In **couple** mode, **partner Social Security** is included in the income series. It does **not** re-run the balance; it is a **side visualization** of the inflation path of those flows.

---

## Persistence & saved scenarios

- **Draft:** On change (debounced), `saveNesteggDraft` writes inputs, market scenario tab, and compare overlay to `localStorage` under `nestegg-draft-v1`. On load, `loadNesteggDraft` restores if present.
- **Named scenarios (local):** Stored in `nestegg-saved-scenarios-v1` as JSON; managed from **Saved scenarios** on the Nestegg page.
- **Named scenarios (cloud):** If the user is signed in and the `nestegg_scenarios` table exists with RLS, rows are saved per `user_id`. Apply the SQL in `supabase/migrations/20260402120000_nestegg_scenarios.sql` in the Supabase SQL editor or CLI.

---

## What the model does **not** do

- No **progressive tax brackets** (only a **flat marginal** gross-up on draws); no IRAs vs taxable vs Roth modeling or capital gains.
- **RMD** uses a **single** tax-deferred share of the **whole** balance and approximate divisors — not per-account rules.
- No variability of returns (single fixed return path).
- No fees explicitly modeled.
- Couple mode is a **simplified** two-earner / two-SS model (no separate filing status, no survivor logic).
- **Suggested extra savings** only increases the **primary** monthly contribution; it is a rough binary search, not financial planning software.

---

## Further improvements

- **Progressive tax brackets** (federal/state) and withholding-aware draws.
- **Per-account** buckets (401k / Roth / taxable) and proportional drawdown.
- **Monte Carlo** or historical return sequences.
- **Spouse** survivor expenses and filing-status changes.

---

## Disclaimer

Nestegg is for **educational planning** inside the app. It is **not** financial, legal, or tax advice. Real outcomes depend on markets, policy, health, and behavior that this toy model cannot capture.
