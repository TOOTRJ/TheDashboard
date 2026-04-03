import type { NesteggInputs } from "./types";

/**
 * First simulation month index (1-based from plan start) at which the *earlier*
 * partner reaches their life expectancy. Used for survivor-phase spending/SS.
 * Returns `Infinity` if survivor modeling does not apply.
 */
export function coupleFirstDeathMonth(inputs: NesteggInputs): number {
  if (inputs.householdMode !== "couple" || !inputs.enableSurvivorModeling) {
    return Infinity;
  }
  const primaryDeath = (inputs.lifeExpectancy - inputs.currentAge) * 12;
  const spouseDeath =
    (inputs.spouseLifeExpectancy - inputs.spouseCurrentAge) * 12;
  return Math.min(
    primaryDeath > 0 ? primaryDeath : Infinity,
    spouseDeath > 0 ? spouseDeath : Infinity
  );
}

/**
 * Retirement-phase household spending and recurring income for one month.
 * When in survivor phase (after first death), spending scales by
 * `survivorSpendingRatioPercent`; SS uses a simplified survivor benefit (max of two benefits).
 */
export function retirementSpendAndIncome(
  inputs: NesteggInputs,
  monthIdx: number,
  monthsWorking: number,
  spouseWorkMonths: number
): { spend: number; income: number } {
  const {
    monthlyRetirementSpending,
    inflationPercent,
    socialSecurityMonthly,
    otherRetirementIncomeMonthly,
    spouseSocialSecurityMonthly,
    householdMode,
  } = inputs;

  const inflation = inflationPercent / 100;
  const monthsRetired = monthIdx - monthsWorking - 1;
  const yearsRetired = Math.floor(monthsRetired / 12);

  const inf = Math.pow(1 + inflation, yearsRetired);

  const firstDeath = coupleFirstDeathMonth(inputs);
  const survivorPhase =
    householdMode === "couple" &&
    inputs.enableSurvivorModeling &&
    monthIdx >= firstDeath &&
    Number.isFinite(firstDeath);

  let spend = monthlyRetirementSpending * inf;
  if (survivorPhase) {
    const ratio = clamp(
      inputs.survivorSpendingRatioPercent / 100,
      0.35,
      1
    );
    spend *= ratio;
  }

  let income: number;
  if (
    survivorPhase &&
    householdMode === "couple" &&
    monthIdx > spouseWorkMonths
  ) {
    const spouseMonthsRetired = monthIdx - spouseWorkMonths - 1;
    const spouseYearsRetired = Math.floor(spouseMonthsRetired / 12);
    const spouseInf = Math.pow(1 + inflation, spouseYearsRetired);
    income =
      otherRetirementIncomeMonthly * inf +
      Math.max(
        socialSecurityMonthly * inf,
        spouseSocialSecurityMonthly * spouseInf
      );
  } else {
    income =
      (socialSecurityMonthly + otherRetirementIncomeMonthly) * inf;
    if (householdMode === "couple" && monthIdx > spouseWorkMonths) {
      const spouseMonthsRetired = monthIdx - spouseWorkMonths - 1;
      const spouseYearsRetired = Math.floor(spouseMonthsRetired / 12);
      income +=
        spouseSocialSecurityMonthly *
        Math.pow(1 + inflation, spouseYearsRetired);
    }
  }

  return { spend, income };
}

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}
