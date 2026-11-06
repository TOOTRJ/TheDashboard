import type {
  NesteggInputs,
  ProjectionPoint,
  ProjectionResult,
  ReadinessLevel,
} from "./types";
import { retirementSpendAndIncome } from "./retirement-cashflow";
import { uniformLifetimeDivisor } from "./rmd";

/** Baseline growth shared by deterministic and stochastic retirement paths. */
export function retirementMonthlyBaseReturn(
  { annualReturnPercent, riskProfile }: Pick<NesteggInputs, "annualReturnPercent" | "riskProfile">
): number {
  // Explicit zero is a flat baseline; stochastic volatility is separate.
  if (annualReturnPercent === 0) return 0;
  const riskAdj =
    riskProfile === "conservative" ? -0.5 : riskProfile === "aggressive" ? 0.5 : 0;
  const annual = clamp(annualReturnPercent + riskAdj, 0.5, 15);
  return Math.pow(1 + annual / 100, 1 / 12) - 1;
}

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

/** Last age (years) included in the simulation — max of partners in couple mode. */
export function planHorizonAge(inputs: NesteggInputs): number {
  if (inputs.householdMode === "couple") {
    return Math.max(inputs.lifeExpectancy, inputs.spouseLifeExpectancy);
  }
  return inputs.lifeExpectancy;
}

export type RunProjectionOptions = {
  /** When true, skips nested binary search for “extra monthly” (avoids infinite recursion). */
  skipSuggestedExtra?: boolean;
};

/**
 * Month-by-month projection; one chart point per integer age (end of that age year).
 * Supports couple contributions/SS, optional tax gross-up on portfolio draws, and RMD floor.
 */
export function runProjection(
  inputs: NesteggInputs,
  options?: RunProjectionOptions
): ProjectionResult {
  const {
    currentAge,
    retirementAge,
    currentSavings,
    monthlyContribution,
    monthlyRetirementSpending,
    salaryGrowthPercent,
    socialSecurityMonthly,
    otherRetirementIncomeMonthly,
    oneTimeIncome,
    oneTimeExpense,
    householdMode,
    spouseCurrentAge,
    spouseRetirementAge,
    spouseMonthlyContribution,
    spouseSocialSecurityMonthly,
    enableTaxOnWithdrawals,
    marginalTaxRatePercent,
    enableRmd,
    rmdStartAge,
    taxDeferredSharePercent,
  } = inputs;

  const planEndAge = planHorizonAge(inputs);

  const monthlyR = retirementMonthlyBaseReturn(inputs);
  const salaryGrowth = salaryGrowthPercent / 100;

  const totalMonths = Math.max(0, (planEndAge - currentAge) * 12);
  const monthsWorking = Math.max(0, (retirementAge - currentAge) * 12);
  const spouseWorkMonths =
    householdMode === "couple"
      ? Math.max(0, Math.round((spouseRetirementAge - spouseCurrentAge) * 12))
      : 0;

  const taxRate = clamp(marginalTaxRatePercent / 100, 0, 0.5);
  const deferredShare = clamp(taxDeferredSharePercent / 100, 0, 1);

  let balance = Math.max(0, currentSavings);
  let depletionAge: number | null = null;
  const series: ProjectionPoint[] = [];
  let nestEggAtRetirement = 0;
  let oneTimeApplied = false;

  for (let monthIdx = 1; monthIdx <= totalMonths; monthIdx++) {
    balance *= 1 + monthlyR;

    const yearIndex = Math.floor((monthIdx - 1) / 12);
    const primaryAge = currentAge + monthIdx / 12;

    if (monthIdx <= monthsWorking) {
      balance += monthlyContribution * Math.pow(1 + salaryGrowth, yearIndex);
    }
    if (householdMode === "couple" && monthIdx <= spouseWorkMonths) {
      balance += spouseMonthlyContribution * Math.pow(1 + salaryGrowth, yearIndex);
    }

    if (monthIdx > monthsWorking) {
      if (!oneTimeApplied) {
        balance += oneTimeIncome - oneTimeExpense;
        oneTimeApplied = true;
        if (monthsWorking === 0) {
          nestEggAtRetirement = balance;
        }
      }

      const { spend, income } = retirementSpendAndIncome(
        inputs,
        monthIdx,
        monthsWorking,
        spouseWorkMonths
      );

      const netFromPortfolio = spend - income;

      let rmdMonthly = 0;
      if (enableRmd && primaryAge >= rmdStartAge && deferredShare > 0) {
        const div = uniformLifetimeDivisor(Math.floor(primaryAge));
        if (div !== null) {
          const annualRmd = (balance * deferredShare) / div;
          rmdMonthly = annualRmd / 12;
        }
      }

      if (netFromPortfolio <= 0) {
        balance -= netFromPortfolio;
        if (rmdMonthly > 0) {
          balance -= rmdMonthly;
        }
      } else {
        let draw =
          enableTaxOnWithdrawals && taxRate > 0 && taxRate < 1
            ? netFromPortfolio / (1 - taxRate)
            : netFromPortfolio;
        draw = Math.max(draw, rmdMonthly);
        balance -= draw;
      }
    }

    if (balance < 0) {
      balance = 0;
      if (depletionAge === null) {
        depletionAge = currentAge + monthIdx / 12;
      }
    }

    if (monthIdx === monthsWorking && monthsWorking > 0) {
      nestEggAtRetirement = balance;
    }

    if (monthIdx % 12 === 0 || monthIdx === totalMonths) {
      const age = currentAge + monthIdx / 12;
      const phase: ProjectionPoint["phase"] =
        monthIdx > monthsWorking ? "retirement" : "accumulation";
      series.push({
        age: Math.round(age * 10) / 10,
        balance: Math.round(balance),
        phase,
      });
    }
  }

  if (totalMonths === 0) {
    series.push({
      age: currentAge,
      balance: Math.round(balance),
      phase: "accumulation",
    });
  }

  // An exact $0 balance is funded; a negative pre-floor balance marks a
  // shortfall, including in the final modeled month.
  const lastsThroughLifeExpectancy = depletionAge === null;

  let monthlyGapOrSurplus =
    socialSecurityMonthly +
    otherRetirementIncomeMonthly -
    monthlyRetirementSpending;
  if (householdMode === "couple") {
    monthlyGapOrSurplus += spouseSocialSecurityMonthly;
  }

  const { readiness, readinessScore, heroMessage, heroTone, suggestedExtraMonthly } =
    buildInsights({
      inputs,
      nestEggAtRetirement,
      depletionAge,
      lastsThroughLifeExpectancy,
      monthlyGapOrSurplus,
      planEndAge,
      computeSuggestedExtra: !options?.skipSuggestedExtra,
    });

  return {
    series,
    nestEggAtRetirement,
    depletionAge,
    lastsThroughLifeExpectancy,
    monthlyGapOrSurplus,
    readiness,
    readinessScore,
    heroMessage,
    heroTone,
    suggestedExtraMonthly,
  };
}

type InsightArgs = {
  inputs: NesteggInputs;
  nestEggAtRetirement: number;
  depletionAge: number | null;
  lastsThroughLifeExpectancy: boolean;
  monthlyGapOrSurplus: number;
  planEndAge: number;
  computeSuggestedExtra: boolean;
};

function buildInsights(args: InsightArgs): {
  readiness: ReadinessLevel;
  readinessScore: number;
  heroMessage: string;
  heroTone: "positive" | "caution" | "warning";
  suggestedExtraMonthly: number | null;
} {
  const {
    inputs,
    nestEggAtRetirement,
    depletionAge,
    lastsThroughLifeExpectancy,
    monthlyGapOrSurplus,
    planEndAge,
    computeSuggestedExtra,
  } = args;

  const annualSpend = inputs.monthlyRetirementSpending * 12;
  const targetMultiple = annualSpend * 25;
  const fundedRatio =
    annualSpend > 0 ? clamp(nestEggAtRetirement / targetMultiple, 0, 2) : 1;

  let score = 50;
  if (lastsThroughLifeExpectancy) {
    score += 25;
    if (monthlyGapOrSurplus >= 0) score += 10;
    if (fundedRatio >= 1) score += 15;
    else if (fundedRatio >= 0.7) score += 8;
  } else {
    score -= 30;
    if (depletionAge !== null) {
      const yearsShort = planEndAge - depletionAge;
      score -= clamp(yearsShort * 3, 0, 25);
    }
  }

  if (inputs.retirementAge < 55 && !lastsThroughLifeExpectancy) score -= 10;
  if (inputs.retirementAge >= 67 && lastsThroughLifeExpectancy) score += 5;

  score = Math.round(clamp(score, 0, 100));

  let readiness: ReadinessLevel;
  if (score >= 85 && lastsThroughLifeExpectancy) readiness = "Excellent";
  else if (score >= 65 && lastsThroughLifeExpectancy) readiness = "Strong";
  else if (score >= 40) readiness = "Needs Attention";
  else readiness = "High Risk";

  let heroMessage: string;
  let heroTone: "positive" | "caution" | "warning";

  if (lastsThroughLifeExpectancy) {
    heroTone = monthlyGapOrSurplus >= -200 ? "positive" : "caution";
    heroMessage = `You are on track to fund retirement through age ${planEndAge} at your current plan.`;
    if (inputs.retirementAge <= inputs.currentAge) {
      heroMessage = `You modeled an immediate retirement start — adjust ages if you are still accumulating.`;
      heroTone = "caution";
    }
  } else if (depletionAge !== null) {
    heroTone = "warning";
    const d = Math.ceil(depletionAge);
    heroMessage = `Your savings may fall short around age ${d}. Your planned horizon is age ${planEndAge}.`;
  } else {
    heroTone = "caution";
    heroMessage = `Review contributions and retirement spending — outcomes are sensitive to return and inflation assumptions.`;
  }

  const suggestedExtraMonthly =
    computeSuggestedExtra && !lastsThroughLifeExpectancy
      ? estimateExtraMonthlyNeeded(inputs)
      : null;

  if (
    !lastsThroughLifeExpectancy &&
    suggestedExtraMonthly !== null &&
    suggestedExtraMonthly > 0 &&
    depletionAge !== null
  ) {
    heroMessage = `Your savings may run out around age ${Math.ceil(
      depletionAge
    )}. Modeling suggests roughly ${formatUsd(
      suggestedExtraMonthly
    )} more per month (primary earner) while working could help cover modeled spending through age ${planEndAge}.`;
    heroTone = "caution";
  }

  return {
    readiness,
    readinessScore: score,
    heroMessage,
    heroTone,
    suggestedExtraMonthly,
  };
}

function formatUsd(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

/** Find the smallest displayed $25 step that passes the same projection. */
function estimateExtraMonthlyNeeded(inputs: NesteggInputs): number | null {
  const step = 25;
  let low = 1;
  let high = 20_000 / step;
  let best: number | null = null;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const extra = mid * step;
    const trial = runProjection(
      {
        ...inputs,
        monthlyContribution: inputs.monthlyContribution + extra,
      },
      { skipSuggestedExtra: true }
    );
    if (trial.lastsThroughLifeExpectancy) {
      best = extra;
      high = mid - 1;
    } else {
      low = mid + 1;
    }
  }
  return best;
}

export function mergeComparisonSeries(
  base: ProjectionPoint[],
  conservative: ProjectionPoint[],
  aggressive: ProjectionPoint[]
): Array<{
  age: number;
  base: number;
  conservative: number;
  aggressive: number;
}> {
  const byAge = new Map<
    number,
    { base?: number; conservative?: number; aggressive?: number }
  >();
  for (const p of base) {
    const e = byAge.get(p.age) ?? {};
    e.base = p.balance;
    byAge.set(p.age, e);
  }
  for (const p of conservative) {
    const e = byAge.get(p.age) ?? {};
    e.conservative = p.balance;
    byAge.set(p.age, e);
  }
  for (const p of aggressive) {
    const e = byAge.get(p.age) ?? {};
    e.aggressive = p.balance;
    byAge.set(p.age, e);
  }
  return Array.from(byAge.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([age, v]) => ({
      age,
      base: v.base ?? 0,
      conservative: v.conservative ?? 0,
      aggressive: v.aggressive ?? 0,
    }));
}

/** First years of retirement: annual expenses vs income (inflation path). */
export function buildRetirementCashflowYears(
  inputs: NesteggInputs,
  years = 15
): { year: string; expenses: number; income: number }[] {
  const inflation = inputs.inflationPercent / 100;
  const out: { year: string; expenses: number; income: number }[] = [];
  const baseIncome =
    inputs.socialSecurityMonthly +
    inputs.otherRetirementIncomeMonthly +
    (inputs.householdMode === "couple" ? inputs.spouseSocialSecurityMonthly : 0);

  for (let y = 0; y < years; y++) {
    const expenses =
      inputs.monthlyRetirementSpending * 12 * Math.pow(1 + inflation, y);
    const income = baseIncome * 12 * Math.pow(1 + inflation, y);
    out.push({
      year: `Yr ${y + 1}`,
      expenses: Math.round(expenses),
      income: Math.round(income),
    });
  }
  return out;
}
