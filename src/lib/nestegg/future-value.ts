export type FVInputs = {
  currentBalance: number;
  goalAmount: number;
  monthsToGoal: number;
  /** Effective annual return; contributions arrive at each month end. */
  annualReturnPercent: number;
  /** Annual increase applied on contribution anniversaries. */
  annualEscalationPercent: number;
};

export const MONTHLY_SAVINGS_SEARCH_LIMIT = 200_000;
export const MAX_GOAL_MONTHS = 100 * 12;

export type SavingsRequirement = {
  status: "calculated" | "above-limit" | "invalid-input" | "past-deadline";
  monthly: number | null;
};
export type GoalProjectionPoint = {
  year: number;
  goalPath: number | null;
  currentPath: number;
  goalLine: number;
};
export type GoalStatus = "on-track" | "ahead" | "behind" | "past-deadline" | "no-goal" | "above-limit" | "invalid-input";
export type TimelineSensitivityRow = { year: number; requiredMonthly: number | null };
export type ReturnSensitivityRow = { returnPercent: number; requiredMonthly: number | null };
export type GoalProjectionResult = {
  requiredMonthly: number | null;
  series: GoalProjectionPoint[];
  currentPathEndBalance: number;
  totalContributed: number | null;
  totalGrowth: number | null;
  status: GoalStatus;
  progressPercent: number;
  extraSavingsNeeded: number | null;
  yearsAtCurrentPace: number | null;
  inflationAdjustedGoal: number;
  timelineSensitivity: TimelineSensitivityRow[];
  returnSensitivity: ReturnSensitivityRow[];
};

function validInputs(opts: FVInputs): boolean {
  return [opts.currentBalance, opts.goalAmount, opts.monthsToGoal, opts.annualReturnPercent, opts.annualEscalationPercent].every(Number.isFinite) &&
    opts.currentBalance >= 0 && opts.goalAmount >= 0 &&
    Number.isInteger(opts.monthsToGoal) && opts.monthsToGoal >= 0 && opts.monthsToGoal <= MAX_GOAL_MONTHS &&
    opts.annualReturnPercent > -100 && opts.annualReturnPercent <= 100 &&
    opts.annualEscalationPercent >= -100 && opts.annualEscalationPercent <= 100;
}

function monthlyRateFromAnnual(annualPercent: number): number {
  return Math.pow(1 + annualPercent / 100, 1 / 12) - 1;
}

function simulateAccumulation(startBalance: number, baseMonthly: number, months: number, monthlyRate: number, annualEscalation: number) {
  let balance = startBalance;
  const yearSnapshots: number[] = [];
  for (let m = 1; m <= months; m++) {
    const contribution = baseMonthly * Math.pow(1 + annualEscalation, Math.floor((m - 1) / 12));
    balance = balance * (1 + monthlyRate) + contribution;
    if (m % 12 === 0 || m === months) yearSnapshots.push(Math.round(balance));
  }
  return { finalBalance: balance, yearSnapshots };
}

/** A finite search limit is not evidence that a goal is mathematically impossible. */
export function solveSavingsRequirement(opts: FVInputs): SavingsRequirement {
  if (!validInputs(opts)) return { status: "invalid-input", monthly: null };
  if (opts.goalAmount === 0) return { status: "calculated", monthly: 0 };
  if (opts.monthsToGoal === 0) return { status: "past-deadline", monthly: null };
  const rate = monthlyRateFromAnnual(opts.annualReturnPercent);
  const escalation = opts.annualEscalationPercent / 100;
  const end = (monthly: number) => simulateAccumulation(opts.currentBalance, monthly, opts.monthsToGoal, rate, escalation).finalBalance;
  const growthOnly = end(0);
  if (!Number.isFinite(growthOnly)) return { status: "invalid-input", monthly: null };
  if (growthOnly >= opts.goalAmount) return { status: "calculated", monthly: 0 };
  const maximum = end(MONTHLY_SAVINGS_SEARCH_LIMIT);
  if (!Number.isFinite(maximum)) return { status: "invalid-input", monthly: null };
  if (maximum < opts.goalAmount) return { status: "above-limit", monthly: null };
  let low = 0, high = MONTHLY_SAVINGS_SEARCH_LIMIT;
  for (let i = 0; i < 64 && high - low > 1e-8; i++) {
    const mid = (low + high) / 2;
    if (end(mid) >= opts.goalAmount) high = mid;
    else low = mid;
  }
  // Verify the lower $5 step, then round up if it misses. Nearest rounding can undershoot.
  const lowerStep = Math.floor(high / 5) * 5;
  return { status: "calculated", monthly: end(lowerStep) >= opts.goalAmount ? lowerStep : lowerStep + 5 };
}

/** Legacy numeric adapter: -1 means unavailable, never zero required savings. */
export function computeRequiredMonthlySavings(opts: FVInputs): number {
  return solveSavingsRequirement(opts).monthly ?? -1;
}

function estimateYearsAtCurrentPace(opts: FVInputs, currentMonthly: number): number | null {
  if (opts.currentBalance >= opts.goalAmount) return 0;
  const rate = monthlyRateFromAnnual(opts.annualReturnPercent);
  const escalation = opts.annualEscalationPercent / 100;
  let balance = opts.currentBalance;
  for (let m = 1; m <= 80 * 12; m++) {
    balance = balance * (1 + rate) + currentMonthly * Math.pow(1 + escalation, Math.floor((m - 1) / 12));
    if (balance >= opts.goalAmount) return Math.ceil((m / 12) * 10) / 10;
  }
  return null;
}

/** Deterministic illustration only; no probability or retirement entitlement is inferred. */
export function buildGoalProjectionSeries(opts: FVInputs & { currentMonthly: number; inflationPercent?: number }): GoalProjectionResult {
  const { currentBalance, goalAmount, monthsToGoal, annualReturnPercent, annualEscalationPercent, currentMonthly, inflationPercent = 2.5 } = opts;
  const now = new Date().getFullYear();
  const requirement = solveSavingsRequirement(opts);
  let valid = requirement.status !== "invalid-input" && Number.isFinite(currentMonthly) && currentMonthly >= 0 && Number.isFinite(inflationPercent) && inflationPercent > -100 && inflationPercent <= 100;
  const rate = monthlyRateFromAnnual(annualReturnPercent), escalation = annualEscalationPercent / 100;
  const currentRun = valid ? simulateAccumulation(currentBalance, currentMonthly, monthsToGoal, rate, escalation) : null;
  if (currentRun && !Number.isFinite(currentRun.finalBalance)) valid = false;
  const realGoal = valid ? goalAmount / Math.pow(1 + inflationPercent / 100, monthsToGoal / 12) : NaN;
  if (!Number.isFinite(realGoal)) valid = false;
  const progressPercent = valid && goalAmount > 0 ? Math.min(100, Math.round(currentBalance / goalAmount * 100)) : 0;
  if (!valid || !currentRun || monthsToGoal === 0 || goalAmount === 0) {
    return {
      requiredMonthly: valid && goalAmount === 0 ? 0 : null,
      series: [], currentPathEndBalance: Number.isFinite(currentBalance) ? Math.max(0, currentBalance) : 0,
      totalContributed: null, totalGrowth: null,
      status: !valid ? "invalid-input" : goalAmount === 0 ? "no-goal" : "past-deadline",
      progressPercent, extraSavingsNeeded: null, yearsAtCurrentPace: null,
      inflationAdjustedGoal: Number.isFinite(goalAmount) ? Math.max(0, goalAmount) : 0,
      timelineSensitivity: [], returnSensitivity: [],
    };
  }
  const requiredMonthly = requirement.monthly;
  const goalRun = requiredMonthly === null ? null : simulateAccumulation(currentBalance, requiredMonthly, monthsToGoal, rate, escalation);
  const series: GoalProjectionPoint[] = [{ year: now, goalPath: goalRun ? Math.round(currentBalance) : null, currentPath: Math.round(currentBalance), goalLine: goalAmount }];
  for (let i = 0; i < currentRun.yearSnapshots.length; i++) {
    series.push({ year: now + Math.min((i + 1) * 12, monthsToGoal) / 12, goalPath: goalRun?.yearSnapshots[i] ?? null, currentPath: currentRun.yearSnapshots[i]!, goalLine: goalAmount });
  }
  let contributed = 0;
  if (requiredMonthly !== null) for (let m = 0; m < monthsToGoal; m++) contributed += requiredMonthly * Math.pow(1 + escalation, Math.floor(m / 12));
  const totalContributed = goalRun ? Math.round(contributed) : null;
  const totalGrowth = goalRun ? Math.round(goalRun.finalBalance - currentBalance - contributed) : null;
  const status: GoalStatus = requiredMonthly === null ? "above-limit" : requiredMonthly === 0 ? "ahead" : currentRun.finalBalance >= goalAmount ? "on-track" : "behind";
  const targetYear = now + monthsToGoal / 12;
  const timelineSensitivity = [-5, -3, 0, 3, 5, 10].flatMap(offset => {
    const months = monthsToGoal + offset * 12;
    return months <= 0 ? [] : [{ year: targetYear + offset, requiredMonthly: solveSavingsRequirement({ ...opts, monthsToGoal: months }).monthly }];
  });
  const returnSensitivity = [4, 5, 6, 7, 8, 9, 10].map(returnPercent => ({ returnPercent, requiredMonthly: solveSavingsRequirement({ ...opts, annualReturnPercent: returnPercent }).monthly }));
  return {
    requiredMonthly, series, currentPathEndBalance: Math.round(currentRun.finalBalance), totalContributed, totalGrowth, status, progressPercent,
    extraSavingsNeeded: requiredMonthly === null ? null : Math.max(0, requiredMonthly - currentMonthly),
    yearsAtCurrentPace: estimateYearsAtCurrentPace(opts, currentMonthly),
    inflationAdjustedGoal: Math.round(realGoal),
    timelineSensitivity, returnSensitivity,
  };
}
