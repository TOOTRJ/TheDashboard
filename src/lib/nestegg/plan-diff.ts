import type { NesteggInputs } from "./types";
import { formatCurrency } from "@/lib/formatters";
import { SCENARIO_LABELS } from "./constants";
import type { NesteggScenarioId } from "./types";

export type PlanDiffRow = {
  id: string;
  label: string;
  a: string;
  b: string;
  changed: boolean;
};

function fmt(n: number, suffix = ""): string {
  if (Number.isNaN(n)) return "—";
  return `${n.toLocaleString()}${suffix}`;
}

export function buildPlanDiff(
  workspace: NesteggInputs,
  workspaceScenario: NesteggScenarioId,
  saved: NesteggInputs,
  savedScenario: NesteggScenarioId
): PlanDiffRow[] {
  const rows: PlanDiffRow[] = [];

  const add = (
    id: string,
    label: string,
    a: string,
    b: string
  ) => {
    const changed = a !== b;
    rows.push({ id, label, a, b, changed });
  };

  add("preset", "Market preset", SCENARIO_LABELS[workspaceScenario], SCENARIO_LABELS[savedScenario]);
  add("age", "Current age → retirement", `${workspace.currentAge} → ${workspace.retirementAge}`, `${saved.currentAge} → ${saved.retirementAge}`);
  add("life", "Life expectancy", fmt(workspace.lifeExpectancy), fmt(saved.lifeExpectancy));
  add("savings", "Current savings", formatCurrency(workspace.currentSavings), formatCurrency(saved.currentSavings));
  add("contrib", "Monthly contribution", formatCurrency(workspace.monthlyContribution), formatCurrency(saved.monthlyContribution));
  add("return", "Annual return %", `${workspace.annualReturnPercent}%`, `${saved.annualReturnPercent}%`);
  add("spend", "Monthly retirement spending", formatCurrency(workspace.monthlyRetirementSpending), formatCurrency(saved.monthlyRetirementSpending));
  add("infl", "Inflation %", `${workspace.inflationPercent}%`, `${saved.inflationPercent}%`);
  add("ss", "Social Security / mo", formatCurrency(workspace.socialSecurityMonthly), formatCurrency(saved.socialSecurityMonthly));
  add("risk", "Risk profile", workspace.riskProfile, saved.riskProfile);
  add("house", "Household", workspace.householdMode, saved.householdMode);
  add("vol", "MC volatility", workspace.monteCarloVolatilityPercent == null ? "Auto" : `${workspace.monteCarloVolatilityPercent}%`, saved.monteCarloVolatilityPercent == null ? "Auto" : `${saved.monteCarloVolatilityPercent}%`);
  add("surv", "Survivor modeling", workspace.enableSurvivorModeling ? `On (${workspace.survivorSpendingRatioPercent}%)` : "Off", saved.enableSurvivorModeling ? `On (${saved.survivorSpendingRatioPercent}%)` : "Off");

  if (workspace.householdMode === "couple" && saved.householdMode === "couple") {
    add("spAge", "Partner age → ret.", `${workspace.spouseCurrentAge} → ${workspace.spouseRetirementAge}`, `${saved.spouseCurrentAge} → ${saved.spouseRetirementAge}`);
    add("spSS", "Partner SS / mo", formatCurrency(workspace.spouseSocialSecurityMonthly), formatCurrency(saved.spouseSocialSecurityMonthly));
  }

  return rows;
}
