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

export type GoalStatus = "on-track" | "ahead" | "behind" | "past-deadline" | "no-goal";

export type TimelineSensitivityRow = {
  year: number;
  requiredMonthly: number;
};

export type ReturnSensitivityRow = {
  returnPercent: number;
  requiredMonthly: number;
};

export type GoalProjectionResult = {
  requiredMonthly: number;
  series: GoalProjectionPoint[];
  currentPathEndBalance: number;
  totalContributed: number;
  totalGrowth: number;
  status: GoalStatus;
  progressPercent: number;
  extraSavingsNeeded: number;
  yearsAtCurrentPace: number | null;
  inflationAdjustedGoal: number;
  timelineSensitivity: TimelineSensitivityRow[];
  returnSensitivity: ReturnSensitivityRow[];
};

function monthlyRateFromAnnual(annualPercent: number): number {
  const r = annualPercent / 100;
  return Math.pow(1 + r, 1 / 12) - 1;
}

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
 * contributions escalating annually. Returns 0 when growth alone
 * covers the goal, or -1 when the goal is not achievable even at
 * the upper bound.
 */
export function computeRequiredMonthlySavings(opts: FVInputs): number {
  const { currentBalance, goalAmount, monthsToGoal, annualReturnPercent, annualEscalationPercent } = opts;

  if (monthsToGoal <= 0 || goalAmount <= 0) return 0;

  const monthlyRate = monthlyRateFromAnnual(annualReturnPercent);
  const escalation = annualEscalationPercent / 100;

  const growthOnly = simulateAccumulation(currentBalance, 0, monthsToGoal, monthlyRate, 0);
  if (growthOnly.finalBalance >= goalAmount) return 0;

  const UPPER = 200_000;
  const maxCheck = simulateAccumulation(currentBalance, UPPER, monthsToGoal, monthlyRate, escalation);
  if (maxCheck.finalBalance < goalAmount) return -1;

  let low = 0;
  let high = UPPER;
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
 * Estimate how many years it takes to reach `goalAmount` at the
 * current monthly contribution. Returns null if it would take
 * more than 80 years or the contribution is 0.
 */
function estimateYearsAtCurrentPace(
  currentBalance: number,
  currentMonthly: number,
  goalAmount: number,
  annualReturnPercent: number,
  annualEscalationPercent: number
): number | null {
  if (currentBalance >= goalAmount) return 0;
  if (currentMonthly <= 0 && currentBalance < goalAmount) return null;

  const monthlyRate = monthlyRateFromAnnual(annualReturnPercent);
  const escalation = annualEscalationPercent / 100;
  let balance = Math.max(0, currentBalance);
  const maxMonths = 80 * 12;

  for (let m = 1; m <= maxMonths; m++) {
    const yearIndex = Math.floor((m - 1) / 12);
    balance = balance * (1 + monthlyRate) + currentMonthly * Math.pow(1 + escalation, yearIndex);
    if (balance >= goalAmount) return Math.round((m / 12) * 10) / 10;
  }

  return null;
}

/**
 * Compute required monthly for several different target years.
 */
function buildTimelineSensitivity(
  opts: FVInputs,
  targetYear: number
): TimelineSensitivityRow[] {
  const offsets = [-5, -3, 0, 3, 5, 10];
  const now = new Date().getFullYear();
  const rows: TimelineSensitivityRow[] = [];

  for (const offset of offsets) {
    const year = targetYear + offset;
    if (year <= now) continue;
    const months = (year - now) * 12;
    const req = computeRequiredMonthlySavings({ ...opts, monthsToGoal: months });
    rows.push({ year, requiredMonthly: Math.max(0, req) });
  }

  return rows;
}

/**
 * Compute required monthly at different return assumptions.
 */
function buildReturnSensitivity(opts: FVInputs): ReturnSensitivityRow[] {
  const returns = [4, 5, 6, 7, 8, 9, 10];
  return returns.map((r) => {
    const req = computeRequiredMonthlySavings({ ...opts, annualReturnPercent: r });
    return { returnPercent: r, requiredMonthly: Math.max(0, req) };
  });
}

/**
 * Build the full goal projection with all metrics.
 */
export function buildGoalProjectionSeries(
  opts: FVInputs & { currentMonthly: number; inflationPercent?: number }
): GoalProjectionResult {
  const {
    currentBalance,
    goalAmount,
    monthsToGoal,
    annualReturnPercent,
    annualEscalationPercent,
    currentMonthly,
    inflationPercent = 2.5,
  } = opts;

  const now = new Date().getFullYear();
  const targetYear = now + Math.ceil(monthsToGoal / 12);

  if (monthsToGoal <= 0) {
    return {
      requiredMonthly: 0,
      series: [],
      currentPathEndBalance: Math.round(currentBalance),
      totalContributed: 0,
      totalGrowth: 0,
      status: "past-deadline",
      progressPercent: goalAmount > 0 ? Math.min(100, Math.round((currentBalance / goalAmount) * 100)) : 0,
      extraSavingsNeeded: 0,
      yearsAtCurrentPace: null,
      inflationAdjustedGoal: goalAmount,
      timelineSensitivity: [],
      returnSensitivity: [],
    };
  }

  const requiredMonthly = computeRequiredMonthlySavings(opts);
  const monthlyRate = monthlyRateFromAnnual(annualReturnPercent);
  const escalation = annualEscalationPercent / 100;

  const effectiveRequired = requiredMonthly === -1 ? 0 : requiredMonthly;
  const goalRun = simulateAccumulation(currentBalance, effectiveRequired, monthsToGoal, monthlyRate, escalation);
  const currentRun = simulateAccumulation(currentBalance, currentMonthly, monthsToGoal, monthlyRate, escalation);

  const totalYears = goalRun.yearSnapshots.length;

  const series: GoalProjectionPoint[] = [
    {
      year: now,
      goalPath: Math.round(currentBalance),
      currentPath: Math.round(currentBalance),
      goalLine: goalAmount,
    },
  ];

  for (let i = 0; i < totalYears; i++) {
    series.push({
      year: now + i + 1,
      goalPath: goalRun.yearSnapshots[i]!,
      currentPath: currentRun.yearSnapshots[i]!,
      goalLine: goalAmount,
    });
  }

  let totalContributed = 0;
  for (let m = 0; m < monthsToGoal; m++) {
    const yearIndex = Math.floor(m / 12);
    totalContributed += effectiveRequired * Math.pow(1 + escalation, yearIndex);
  }
  totalContributed = Math.round(totalContributed);

  const totalGrowth = Math.max(0, Math.round(goalRun.finalBalance - currentBalance - totalContributed));
  const progressPercent = goalAmount > 0 ? Math.min(100, Math.round((currentBalance / goalAmount) * 100)) : 0;

  let status: GoalStatus;
  if (requiredMonthly === 0) {
    status = "ahead";
  } else if (requiredMonthly === -1) {
    status = "behind";
  } else if (currentRun.finalBalance >= goalAmount) {
    status = "on-track";
  } else {
    status = "behind";
  }

  const extraSavingsNeeded = Math.max(0, (requiredMonthly === -1 ? 0 : requiredMonthly) - currentMonthly);

  const yearsAtCurrentPace = estimateYearsAtCurrentPace(
    currentBalance, currentMonthly, goalAmount, annualReturnPercent, annualEscalationPercent
  );

  const yearsToGoal = monthsToGoal / 12;
  const inflationAdjustedGoal = Math.round(goalAmount / Math.pow(1 + inflationPercent / 100, yearsToGoal));

  const timelineSensitivity = buildTimelineSensitivity(opts, targetYear);
  const returnSensitivity = buildReturnSensitivity(opts);

  return {
    requiredMonthly: Math.max(0, requiredMonthly),
    series,
    currentPathEndBalance: Math.round(currentRun.finalBalance),
    totalContributed,
    totalGrowth,
    status,
    progressPercent,
    extraSavingsNeeded,
    yearsAtCurrentPace,
    inflationAdjustedGoal,
    timelineSensitivity,
    returnSensitivity,
  };
}
