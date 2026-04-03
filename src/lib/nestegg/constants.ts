import type { NesteggInputs, NesteggScenarioId } from "./types";

export const DEFAULT_NESTEGG_INPUTS: NesteggInputs = {
  currentAge: 32,
  retirementAge: 65,
  lifeExpectancy: 90,
  currentSavings: 0,
  monthlyContribution: 0,
  annualReturnPercent: 7,
  monthlyRetirementSpending: 0,
  inflationPercent: 2.5,
  salaryGrowthPercent: 3,
  socialSecurityMonthly: 0,
  otherRetirementIncomeMonthly: 0,
  oneTimeIncome: 0,
  oneTimeExpense: 0,
  riskProfile: "moderate",
  householdMode: "single",
  spouseCurrentAge: 32,
  spouseRetirementAge: 65,
  spouseLifeExpectancy: 90,
  spouseMonthlyContribution: 0,
  spouseSocialSecurityMonthly: 0,
  enableTaxOnWithdrawals: false,
  marginalTaxRatePercent: 22,
  enableRmd: false,
  rmdStartAge: 73,
  taxDeferredSharePercent: 100,
  monteCarloVolatilityPercent: null,
  enableSurvivorModeling: false,
  survivorSpendingRatioPercent: 72,
};

export const SCENARIO_LABELS: Record<NesteggScenarioId, string> = {
  base: "Base",
  conservative: "Conservative",
  aggressive: "Aggressive",
};

/** Merge partial / JSON-loaded data with defaults (for storage round-trips). */
export function normalizeNesteggInputs(raw: unknown): NesteggInputs {
  if (!raw || typeof raw !== "object") {
    return { ...DEFAULT_NESTEGG_INPUTS };
  }
  const o = raw as Record<string, unknown>;
  return {
    ...DEFAULT_NESTEGG_INPUTS,
    currentAge: Number(o.currentAge) || DEFAULT_NESTEGG_INPUTS.currentAge,
    retirementAge: Number(o.retirementAge) || DEFAULT_NESTEGG_INPUTS.retirementAge,
    lifeExpectancy: Number(o.lifeExpectancy) || DEFAULT_NESTEGG_INPUTS.lifeExpectancy,
    currentSavings: Number(o.currentSavings) || 0,
    monthlyContribution: Number(o.monthlyContribution) || 0,
    annualReturnPercent: Number(o.annualReturnPercent) || DEFAULT_NESTEGG_INPUTS.annualReturnPercent,
    monthlyRetirementSpending:
      Number(o.monthlyRetirementSpending) || DEFAULT_NESTEGG_INPUTS.monthlyRetirementSpending,
    inflationPercent: clampNum(Number(o.inflationPercent), 0, 8, DEFAULT_NESTEGG_INPUTS.inflationPercent),
    salaryGrowthPercent: clampNum(Number(o.salaryGrowthPercent), 0, 10, DEFAULT_NESTEGG_INPUTS.salaryGrowthPercent),
    socialSecurityMonthly: Number(o.socialSecurityMonthly) || 0,
    otherRetirementIncomeMonthly: Number(o.otherRetirementIncomeMonthly) || 0,
    oneTimeIncome: Number(o.oneTimeIncome) || 0,
    oneTimeExpense: Number(o.oneTimeExpense) || 0,
    riskProfile:
      o.riskProfile === "conservative" || o.riskProfile === "aggressive" || o.riskProfile === "moderate"
        ? o.riskProfile
        : DEFAULT_NESTEGG_INPUTS.riskProfile,
    householdMode: o.householdMode === "couple" ? "couple" : "single",
    spouseCurrentAge: Number(o.spouseCurrentAge) || DEFAULT_NESTEGG_INPUTS.spouseCurrentAge,
    spouseRetirementAge: Number(o.spouseRetirementAge) || DEFAULT_NESTEGG_INPUTS.spouseRetirementAge,
    spouseLifeExpectancy: Number(o.spouseLifeExpectancy) || DEFAULT_NESTEGG_INPUTS.spouseLifeExpectancy,
    spouseMonthlyContribution: Number(o.spouseMonthlyContribution) || 0,
    spouseSocialSecurityMonthly: Number(o.spouseSocialSecurityMonthly) || 0,
    enableTaxOnWithdrawals: Boolean(o.enableTaxOnWithdrawals),
    marginalTaxRatePercent: clampNum(Number(o.marginalTaxRatePercent), 0, 50, 22),
    enableRmd: Boolean(o.enableRmd),
    rmdStartAge: clampNum(Number(o.rmdStartAge), 65, 80, 73),
    taxDeferredSharePercent: clampNum(Number(o.taxDeferredSharePercent), 0, 100, 100),
    monteCarloVolatilityPercent: (() => {
      const v = o.monteCarloVolatilityPercent;
      if (v === null || v === undefined || String(v) === "") return null;
      const n = Number(v);
      if (!Number.isFinite(n)) return null;
      return clampNum(n, 4, 45, 13);
    })(),
    enableSurvivorModeling: Boolean(o.enableSurvivorModeling),
    survivorSpendingRatioPercent: clampNum(
      Number(o.survivorSpendingRatioPercent),
      35,
      100,
      72
    ),
  };
}

function clampNum(v: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(v)) return fallback;
  return Math.min(max, Math.max(min, v));
}

/** Adjust inputs for market scenario (return / stress). Base uses raw inputs. */
/** Deep equality for comparing stored vs current inputs (order-independent). */
export function nesteggInputsEqual(a: NesteggInputs, b: NesteggInputs): boolean {
  return (
    a.currentAge === b.currentAge &&
    a.retirementAge === b.retirementAge &&
    a.lifeExpectancy === b.lifeExpectancy &&
    a.currentSavings === b.currentSavings &&
    a.monthlyContribution === b.monthlyContribution &&
    a.annualReturnPercent === b.annualReturnPercent &&
    a.monthlyRetirementSpending === b.monthlyRetirementSpending &&
    a.inflationPercent === b.inflationPercent &&
    a.salaryGrowthPercent === b.salaryGrowthPercent &&
    a.socialSecurityMonthly === b.socialSecurityMonthly &&
    a.otherRetirementIncomeMonthly === b.otherRetirementIncomeMonthly &&
    a.oneTimeIncome === b.oneTimeIncome &&
    a.oneTimeExpense === b.oneTimeExpense &&
    a.riskProfile === b.riskProfile &&
    a.householdMode === b.householdMode &&
    a.spouseCurrentAge === b.spouseCurrentAge &&
    a.spouseRetirementAge === b.spouseRetirementAge &&
    a.spouseLifeExpectancy === b.spouseLifeExpectancy &&
    a.spouseMonthlyContribution === b.spouseMonthlyContribution &&
    a.spouseSocialSecurityMonthly === b.spouseSocialSecurityMonthly &&
    a.enableTaxOnWithdrawals === b.enableTaxOnWithdrawals &&
    a.marginalTaxRatePercent === b.marginalTaxRatePercent &&
    a.enableRmd === b.enableRmd &&
    a.rmdStartAge === b.rmdStartAge &&
    a.taxDeferredSharePercent === b.taxDeferredSharePercent &&
    a.monteCarloVolatilityPercent === b.monteCarloVolatilityPercent &&
    a.enableSurvivorModeling === b.enableSurvivorModeling &&
    a.survivorSpendingRatioPercent === b.survivorSpendingRatioPercent
  );
}

/** True when the workspace matches shipped app defaults (inputs + base market + no compare overlay). */
export function isNesteggWorkspaceAppDefaults(
  inputs: NesteggInputs,
  marketScenario: NesteggScenarioId,
  compareOverlay: boolean
): boolean {
  return (
    !compareOverlay &&
    marketScenario === "base" &&
    nesteggInputsEqual(inputs, DEFAULT_NESTEGG_INPUTS)
  );
}

export function applyScenarioToInputs(
  inputs: NesteggInputs,
  scenario: NesteggScenarioId
): NesteggInputs {
  if (scenario === "base") {
    return { ...inputs };
  }
  if (scenario === "conservative") {
    return {
      ...inputs,
      annualReturnPercent: Math.max(1, inputs.annualReturnPercent - 2),
      inflationPercent: Math.min(8, inputs.inflationPercent + 0.5),
    };
  }
  return {
    ...inputs,
    annualReturnPercent: Math.min(12, inputs.annualReturnPercent + 2),
  };
}
