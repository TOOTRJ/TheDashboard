import type { NesteggInputs, ProjectionResult } from "./types";
import type { MonteCarloResult } from "./monte-carlo";
import { formatCurrency } from "@/lib/formatters";
import { runProjection } from "./projections";

export type NesteggInsight = {
  id: string;
  text: string;
};

export type NesteggInsightsOptions = {
  /** Monte Carlo success rate for the conservative market preset (same base inputs). */
  conservativeMcSuccessRate?: number;
};

/**
 * Deterministic, rule-based insights from Monte Carlo + baseline projection.
 */
export function buildNesteggInsights(
  inputs: NesteggInputs,
  deterministic: ProjectionResult,
  mc: MonteCarloResult,
  opts?: NesteggInsightsOptions
): NesteggInsight[] {
  const out: NesteggInsight[] = [];
  const annualSpend = inputs.monthlyRetirementSpending * 12;
  const assetsToSpend =
    annualSpend > 0 ? inputs.currentSavings / annualSpend : Infinity;

  if (annualSpend > 0 && assetsToSpend < 3 && inputs.currentAge < inputs.retirementAge) {
    out.push({
      id: "spend-vs-assets",
      text: "Your planned retirement spending is high relative to what you have saved today — small increases in savings or a later retirement date can help a lot.",
    });
  }

  if (mc.successRate >= 0.5 && mc.successRate < 0.75) {
    out.push({
      id: "success-mid",
      text: "Your plan succeeds in a meaningful share of simulated paths, but there is still material uncertainty — stress-test spending and market assumptions.",
    });
  }

  if (mc.successRate < 0.5) {
    out.push({
      id: "success-low",
      text: "Across randomized return paths, your plan often falls short of lasting through your full horizon — consider adjusting savings, timing, or spending.",
    });
  }

  const retire3 = runProjection(
    { ...inputs, retirementAge: inputs.retirementAge + 3 },
    { skipSuggestedExtra: true }
  );
  const save250 = runProjection(
    { ...inputs, monthlyContribution: inputs.monthlyContribution + 250 },
    { skipSuggestedExtra: true }
  );

  if (
    !deterministic.lastsThroughLifeExpectancy &&
    retire3.lastsThroughLifeExpectancy &&
    save250.lastsThroughLifeExpectancy
  ) {
    out.push({
      id: "delay-or-save",
      text: "Delaying retirement by about three years or saving roughly $250 more per month (primary) both move the needle — compare them to see which fits your life better.",
    });
  } else if (!deterministic.lastsThroughLifeExpectancy && retire3.lastsThroughLifeExpectancy) {
    out.push({
      id: "delay-helps",
      text: "Delaying retirement by a few years materially improves how often the plan succeeds in simulations.",
    });
  } else if (!deterministic.lastsThroughLifeExpectancy && save250.lastsThroughLifeExpectancy) {
    out.push({
      id: "save-helps",
      text: "A modest increase in monthly savings improves your modeled odds more than small tweaks to other knobs alone.",
    });
  }

  const cons = opts?.conservativeMcSuccessRate;
  if (
    cons !== undefined &&
    mc.successRate > 0 &&
    cons + 0.12 < mc.successRate
  ) {
    out.push({
      id: "conservative-stress",
      text: "A more conservative market path lowers your success rate noticeably — your plan is sensitive to returns and inflation stress.",
    });
  }

  const ssTotal =
    inputs.socialSecurityMonthly +
    inputs.otherRetirementIncomeMonthly +
    (inputs.householdMode === "couple" ? inputs.spouseSocialSecurityMonthly : 0);
  if (ssTotal >= inputs.monthlyRetirementSpending * 0.35) {
    out.push({
      id: "ss-cushion",
      text: "Social Security and other steady income meaningfully reduce portfolio pressure in retirement.",
    });
  }

  if (deterministic.suggestedExtraMonthly && deterministic.suggestedExtraMonthly > 0) {
    out.push({
      id: "suggested-extra",
      text: `Modeling suggests about ${formatCurrency(
        deterministic.suggestedExtraMonthly
      )} more per month while working could help close the gap in weaker outcomes.`,
    });
  }

  return out.slice(0, 5);
}
