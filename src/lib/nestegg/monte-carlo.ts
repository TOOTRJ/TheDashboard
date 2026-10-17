import type { NesteggInputs, NesteggScenarioId, ProjectionPoint } from "./types";
import type { RiskProfile } from "./types";
import { applyScenarioToInputs } from "./constants";
import { planHorizonAge, runProjection } from "./projections";
import { retirementSpendAndIncome } from "./retirement-cashflow";
import { uniformLifetimeDivisor } from "./rmd";

/** Annual return volatility (%) by risk profile — used for Monte Carlo noise when custom is unset. */
export const ANNUAL_VOLATILITY_BY_RISK: Record<RiskProfile, number> = {
  conservative: 9,
  moderate: 13,
  aggressive: 17,
};

/** Effective annual volatility (%) for Monte Carlo: custom input or risk-profile default. */
export function effectiveAnnualVolatilityPercent(inputs: NesteggInputs): number {
  if (
    inputs.monteCarloVolatilityPercent !== null &&
    Number.isFinite(inputs.monteCarloVolatilityPercent)
  ) {
    return clamp(inputs.monteCarloVolatilityPercent, 4, 45);
  }
  return ANNUAL_VOLATILITY_BY_RISK[inputs.riskProfile] ?? ANNUAL_VOLATILITY_BY_RISK.moderate;
}

/** Identity metadata for the existing formulas and seed implementation; no calibration claim. */
export const NESTEGG_MC_MODEL_VERSION = "nestegg-monthly-normal-v1";
export const NESTEGG_MC_SEED_POLICY = "fnv1a-input-json-mulberry32-path-v1";

const DEFAULT_PATHS = 900;
const MAX_PATHS = 1500;

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

function monthlyRateFromAnnual(annualPercent: number): number {
  const r = annualPercent / 100;
  return Math.pow(1 + r, 1 / 12) - 1;
}

/** Deterministic mulberry32 PRNG for reproducible batches per (inputs, scenario). */
function mulberry32(seed: number): () => number {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), t | 1);
    r ^= r + Math.imul(r ^ (r >>> 7), r | 61);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function randn(rng: () => number): number {
  const u1 = rng() + 1e-12;
  const u2 = rng();
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

function hashSeed(inputs: NesteggInputs, scenario: NesteggScenarioId): number {
  const s = JSON.stringify({
    ...inputs,
    _s: scenario,
  });
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export type MonteCarloBandPoint = {
  age: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
};

export type MonteCarloResult = {
  paths: number;
  successRate: number;
  chanceRunOut: number;
  medianNestEggAtRetirement: number;
  medianEndingBalance: number;
  pessimisticEndingBalance: number;
  optimisticEndingBalance: number;
  /** Median depletion age among paths that depleted before horizon (null if none). */
  medianDepletionAgeAmongFailures: number | null;
  /** ~10th percentile depletion age among depleted paths (weaker outcomes). */
  worstCaseDepletionAge: number | null;
  /** Median of “last age with assets” across all paths (depletion age or horizon). */
  portfolioMayLastUntilMedianAge: number;
  bandSeries: MonteCarloBandPoint[];
};

export type MonteCarloOptions = {
  paths?: number;
  /** Yield between batches so the UI stays responsive (default ~100 paths). */
  chunkSize?: number;
  onProgress?: (fraction: number) => void;
};

type PathOutcome = {
  nestEggAtRetirement: number;
  endingBalance: number;
  depletionAge: number | null;
  lastsToHorizon: boolean;
  /** Balance at each snapshot index (aligned with snapshotAges). */
  balances: number[];
};

/**
 * One stochastic path: mirrors deterministic projection logic with monthly return noise.
 */
function simulatePath(
  inputs: NesteggInputs,
  rng: () => number,
  annualVolPercent: number,
  snapshotCount: number
): PathOutcome {
  const {
    currentAge,
    retirementAge,
    currentSavings,
    monthlyContribution,
    annualReturnPercent,
    salaryGrowthPercent,
    oneTimeIncome,
    oneTimeExpense,
    riskProfile,
    householdMode,
    spouseCurrentAge,
    spouseRetirementAge,
    spouseMonthlyContribution,
    enableTaxOnWithdrawals,
    marginalTaxRatePercent,
    enableRmd,
    rmdStartAge,
    taxDeferredSharePercent,
  } = inputs;

  const planEndAge = planHorizonAge(inputs);
  const riskAdj =
    riskProfile === "conservative" ? -0.5 : riskProfile === "aggressive" ? 0.5 : 0;
  const effectiveReturn = clamp(annualReturnPercent + riskAdj, 0.5, 15);

  const baseMonthly = monthlyRateFromAnnual(effectiveReturn);
  const volMonthly = annualVolPercent / 100 / Math.sqrt(12);

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
  let nestEggAtRetirement = 0;
  let oneTimeApplied = false;

  const balances: number[] = new Array(snapshotCount).fill(0);
  let snapIdx = 0;

  for (let monthIdx = 1; monthIdx <= totalMonths; monthIdx++) {
    const noise = volMonthly * randn(rng);
    const monthlyR = clamp(baseMonthly + noise, -0.08, 0.08);
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
      if (snapIdx < snapshotCount) {
        balances[snapIdx] = Math.round(balance);
        snapIdx++;
      }
    }
  }

  if (totalMonths === 0) {
    if (snapshotCount > 0) balances[0] = Math.round(balance);
    nestEggAtRetirement = Math.round(balance);
  }

  const endingBalance = balances[snapIdx - 1] ?? Math.round(balance);
  const lastsToHorizon = depletionAge === null || depletionAge >= planEndAge - 0.01;

  return {
    nestEggAtRetirement: Math.round(nestEggAtRetirement),
    endingBalance,
    depletionAge,
    lastsToHorizon,
    balances,
  };
}

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = clamp(Math.floor((p / 100) * (sorted.length - 1)), 0, sorted.length - 1);
  return sorted[idx]!;
}

function buildMonteCarloResult(
  paths: number,
  inputs: NesteggInputs,
  planEndAge: number,
  detSeries: ProjectionPoint[],
  nestEggs: number[],
  endings: number[],
  depletionAges: number[],
  lastAssetAges: number[],
  successCount: number,
  perSnap: number[][]
): MonteCarloResult {
  const successRate = successCount / paths;
  nestEggs.sort((a, b) => a - b);
  endings.sort((a, b) => a - b);
  depletionAges.sort((a, b) => a - b);

  const medianNestEggAtRetirement = percentile(nestEggs, 50);
  const medianEndingBalance = percentile(endings, 50);
  const pessimisticEndingBalance = percentile(endings, 10);
  const optimisticEndingBalance = percentile(endings, 90);

  let medianDepletionAmongFailures: number | null = null;
  let worstCaseDepletionAge: number | null = null;
  if (depletionAges.length > 0) {
    medianDepletionAmongFailures = percentile(depletionAges, 50);
    worstCaseDepletionAge = percentile(depletionAges, 10);
  }

  lastAssetAges.sort((a, b) => a - b);
  const portfolioMayLastUntilMedianAge = percentile(lastAssetAges, 50);

  const actualSnaps = detSeries.length;
  const bandSeries: MonteCarloBandPoint[] = [];
  for (let i = 0; i < actualSnaps; i++) {
    const arr = [...perSnap[i]!].sort((a, b) => a - b);
    const age = detSeries[i]?.age ?? inputs.currentAge;
    bandSeries.push({
      age: Math.round(age * 10) / 10,
      p10: percentile(arr, 10),
      p25: percentile(arr, 25),
      p50: percentile(arr, 50),
      p75: percentile(arr, 75),
      p90: percentile(arr, 90),
    });
  }

  return {
    paths,
    successRate,
    chanceRunOut: 1 - successRate,
    medianNestEggAtRetirement,
    medianEndingBalance,
    pessimisticEndingBalance,
    optimisticEndingBalance,
    medianDepletionAgeAmongFailures: medianDepletionAmongFailures,
    worstCaseDepletionAge,
    portfolioMayLastUntilMedianAge,
    bandSeries,
  };
}

function accumulatePathResults(
  out: PathOutcome,
  planEndAge: number,
  nestEggs: number[],
  endings: number[],
  depletionAges: number[],
  lastAssetAges: number[],
  successCount: { n: number },
  perSnap: number[][]
): void {
  nestEggs.push(out.nestEggAtRetirement);
  endings.push(out.endingBalance);

  if (out.lastsToHorizon) {
    successCount.n++;
    lastAssetAges.push(planEndAge);
  } else if (out.depletionAge !== null) {
    depletionAges.push(out.depletionAge);
    lastAssetAges.push(out.depletionAge);
  }

  for (let i = 0; i < perSnap.length; i++) {
    perSnap[i]!.push(out.balances[i] ?? 0);
  }
}

export function runMonteCarlo(
  inputs: NesteggInputs,
  scenario: NesteggScenarioId,
  options?: MonteCarloOptions
): MonteCarloResult {
  const paths = clamp(
    options?.paths ?? DEFAULT_PATHS,
    100,
    MAX_PATHS
  );

  const planEndAge = planHorizonAge(inputs);
  const detSeries = runProjection(inputs).series;
  const actualSnaps = detSeries.length;

  const annualVol = effectiveAnnualVolatilityPercent(inputs);

  const seedBase = hashSeed(inputs, scenario);

  const nestEggs: number[] = [];
  const endings: number[] = [];
  const depletionAges: number[] = [];
  const lastAssetAges: number[] = [];
  const successCount = { n: 0 };

  const perSnap: number[][] = Array.from({ length: actualSnaps }, () => []);

  for (let p = 0; p < paths; p++) {
    const rng = mulberry32(seedBase + p * 2654435761);
    const out = simulatePath(inputs, rng, annualVol, actualSnaps);
    accumulatePathResults(
      out,
      planEndAge,
      nestEggs,
      endings,
      depletionAges,
      lastAssetAges,
      successCount,
      perSnap
    );
  }

  return buildMonteCarloResult(
    paths,
    inputs,
    planEndAge,
    detSeries,
    nestEggs,
    endings,
    depletionAges,
    lastAssetAges,
    successCount.n,
    perSnap
  );
}

/**
 * Same as `runMonteCarlo`, but processes paths in chunks and yields between chunks
 * (`requestAnimationFrame`) so the main thread stays responsive.
 */
export async function runMonteCarloBatched(
  inputs: NesteggInputs,
  scenario: NesteggScenarioId,
  options?: MonteCarloOptions
): Promise<MonteCarloResult> {
  const paths = clamp(
    options?.paths ?? DEFAULT_PATHS,
    100,
    MAX_PATHS
  );
  const chunkSize = Math.max(1, options?.chunkSize ?? 120);

  const planEndAge = planHorizonAge(inputs);
  const detSeries = runProjection(inputs).series;
  const actualSnaps = detSeries.length;
  const annualVol = effectiveAnnualVolatilityPercent(inputs);
  const seedBase = hashSeed(inputs, scenario);

  const nestEggs: number[] = [];
  const endings: number[] = [];
  const depletionAges: number[] = [];
  const lastAssetAges: number[] = [];
  const successCount = { n: 0 };
  const perSnap: number[][] = Array.from({ length: actualSnaps }, () => []);

  let p = 0;
  while (p < paths) {
    const end = Math.min(p + chunkSize, paths);
    for (; p < end; p++) {
      const rng = mulberry32(seedBase + p * 2654435761);
      const out = simulatePath(inputs, rng, annualVol, actualSnaps);
      accumulatePathResults(
        out,
        planEndAge,
        nestEggs,
        endings,
        depletionAges,
        lastAssetAges,
        successCount,
        perSnap
      );
    }
    options?.onProgress?.(end / paths);
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => resolve());
    });
  }

  return buildMonteCarloResult(
    paths,
    inputs,
    planEndAge,
    detSeries,
    nestEggs,
    endings,
    depletionAges,
    lastAssetAges,
    successCount.n,
    perSnap
  );
}

export type ScenarioMonteCompareRow = {
  scenarioId: NesteggScenarioId;
  label: string;
  successRate: number;
  medianNestEggAtRetirement: number;
  medianEndingBalance: number;
  medianDepletionAge: number | null;
};

export const NESTEGG_MC_COMPARE_PATHS = 350;
const COMPARE_PATHS = NESTEGG_MC_COMPARE_PATHS;

export function runMonteCarloScenarioComparison(
  inputs: NesteggInputs,
  labels: Record<NesteggScenarioId, string>
): ScenarioMonteCompareRow[] {
  const ids: NesteggScenarioId[] = ["base", "conservative", "aggressive"];
  return ids.map((scenarioId) => {
    const adjusted = applyScenarioToInputs(inputs, scenarioId);
    const mc = runMonteCarlo(adjusted, scenarioId, { paths: COMPARE_PATHS });
    return {
      scenarioId,
      label: labels[scenarioId] ?? scenarioId,
      successRate: mc.successRate,
      medianNestEggAtRetirement: mc.medianNestEggAtRetirement,
      medianEndingBalance: mc.medianEndingBalance,
      medianDepletionAge: mc.medianDepletionAgeAmongFailures,
    };
  });
}

/**
 * Async/batched version of `runMonteCarloScenarioComparison`.
 * Yields between scenarios so the UI stays responsive.
 */
export async function runMonteCarloScenarioComparisonBatched(
  inputs: NesteggInputs,
  labels: Record<NesteggScenarioId, string>,
  options?: { pathsPerScenario?: number }
): Promise<ScenarioMonteCompareRow[]> {
  const ids: NesteggScenarioId[] = ["base", "conservative", "aggressive"];
  const pathsEach = clamp(options?.pathsPerScenario ?? COMPARE_PATHS, 100, MAX_PATHS);
  const rows: ScenarioMonteCompareRow[] = [];

  for (const scenarioId of ids) {
    const adjusted = applyScenarioToInputs(inputs, scenarioId);
    const mc = await runMonteCarloBatched(adjusted, scenarioId, {
      paths: pathsEach,
      chunkSize: Math.ceil(pathsEach / 3),
    });
    rows.push({
      scenarioId,
      label: labels[scenarioId] ?? scenarioId,
      successRate: mc.successRate,
      medianNestEggAtRetirement: mc.medianNestEggAtRetirement,
      medianEndingBalance: mc.medianEndingBalance,
      medianDepletionAge: mc.medianDepletionAgeAmongFailures,
    });
  }

  return rows;
}
