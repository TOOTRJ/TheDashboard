export type FVInputs = {
  currentBalance: number;
  goalAmount: number;
  monthsToGoal: number;
  annualReturnPercent: number;
  /** Annual % increase applied to the base monthly contribution each year. */
  annualEscalationPercent: number;
};

export type GoalProjectionPoint = {
  year: number;
  goalPath: number;
  currentPath: number;
  goalLine: number;
};

export type GoalProjectionResult = {
  requiredMonthly: number;
  series: GoalProjectionPoint[];
  currentPathEndBalance: number;
  totalContributed: number;
  totalGrowth: number;
};

function monthlyRateFromAnnual(annualPercent: number): number {
  const r = annualPercent / 100;
  return Math.pow(1 + r, 1 / 12) - 1;
}

/**
 * Simulate a month-by-month accumulation path.
 * Returns the final balance and a year-end snapshot array.
 */
function simulateAccumulation(
  startBalance: number,
  baseMonthly: number,
  months: number,
  monthlyRate: number,
  annualEscalation: number
): { finalBalance: number; yearSnapshots: number[] } {
  let balance = Math.max(0, startBalance);
  const snapshots: number[] = [];

  for (let m = 1; m <= months; m++) {
    const yearIndex = Math.floor((m - 1) / 12);
    const contribution = baseMonthly * Math.pow(1 + annualEscalation, yearIndex);
    balance = balance * (1 + monthlyRate) + contribution;

    if (m % 12 === 0 || m === months) {
      snapshots.push(Math.round(balance));
    }
  }

  return { finalBalance: balance, yearSnapshots: snapshots };
}

/**
 * Binary search for the base monthly contribution that grows
 * `currentBalance` to `goalAmount` over `monthsToGoal`, with
 * contributions escalating annually.
 */
export function computeRequiredMonthlySavings(opts: FVInputs): number {
  const { currentBalance, goalAmount, monthsToGoal, annualReturnPercent, annualEscalationPercent } = opts;

  if (monthsToGoal <= 0 || goalAmount <= 0) return 0;

  const monthlyRate = monthlyRateFromAnnual(annualReturnPercent);
  const escalation = annualEscalationPercent / 100;

  const growthOnly = simulateAccumulation(currentBalance, 0, monthsToGoal, monthlyRate, 0);
  if (growthOnly.finalBalance >= goalAmount) return 0;

  let low = 0;
  let high = 100_000;
  let best = high;

  for (let i = 0; i < 30; i++) {
    const mid = (low + high) / 2;
    const { finalBalance } = simulateAccumulation(currentBalance, mid, monthsToGoal, monthlyRate, escalation);
    if (finalBalance >= goalAmount) {
      best = mid;
      high = mid;
    } else {
      low = mid;
    }
    if (high - low < 0.5) break;
  }

  return Math.round(best / 5) * 5;
}

/**
 * Build year-by-year projection series for the goal chart.
 * Produces two paths: one at the required monthly rate, one at the current rate.
 */
export function buildGoalProjectionSeries(
  opts: FVInputs & { currentMonthly: number }
): GoalProjectionResult {
  const {
    currentBalance,
    goalAmount,
    monthsToGoal,
    annualReturnPercent,
    annualEscalationPercent,
    currentMonthly,
  } = opts;

  const requiredMonthly = computeRequiredMonthlySavings(opts);
  const monthlyRate = monthlyRateFromAnnual(annualReturnPercent);
  const escalation = annualEscalationPercent / 100;

  const goalRun = simulateAccumulation(currentBalance, requiredMonthly, monthsToGoal, monthlyRate, escalation);
  const currentRun = simulateAccumulation(currentBalance, currentMonthly, monthsToGoal, monthlyRate, escalation);

  const currentYear = new Date().getFullYear();
  const totalYears = goalRun.yearSnapshots.length;

  const series: GoalProjectionPoint[] = [
    {
      year: currentYear,
      goalPath: Math.round(currentBalance),
      currentPath: Math.round(currentBalance),
      goalLine: goalAmount,
    },
  ];

  for (let i = 0; i < totalYears; i++) {
    series.push({
      year: currentYear + i + 1,
      goalPath: goalRun.yearSnapshots[i]!,
      currentPath: currentRun.yearSnapshots[i]!,
      goalLine: goalAmount,
    });
  }

  const totalMonthsContrib = monthsToGoal;
  let totalContributed = 0;
  for (let m = 0; m < totalMonthsContrib; m++) {
    const yearIndex = Math.floor(m / 12);
    totalContributed += requiredMonthly * Math.pow(1 + escalation, yearIndex);
  }
  totalContributed = Math.round(totalContributed);

  const totalGrowth = Math.round(goalRun.finalBalance - currentBalance - totalContributed);

  return {
    requiredMonthly,
    series,
    currentPathEndBalance: Math.round(currentRun.finalBalance),
    totalContributed,
    totalGrowth: Math.max(0, totalGrowth),
  };
}
