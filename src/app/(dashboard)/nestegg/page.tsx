"use client";

import * as React from "react";
import { toast } from "sonner";
import { FlaskConical, PiggyBank, SlidersHorizontal } from "lucide-react";

import { useAuth } from "@/components/auth/AuthProvider";
import { sessionIdentity } from "@/lib/auth/session-guard";
import { createNesteggWorkspaceScope } from "@/lib/nestegg/session-scope";
import {
  captureNesteggCalculationSource, createNesteggPublicationClock, currentNesteggCalculation,
  nesteggCalculationIdentity, type NesteggCalculationEnvelope, type NesteggPublication,
} from "@/lib/nestegg/result-identity";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { NesteggHeroInsight } from "@/components/nestegg/NesteggHeroInsight";
import { NesteggSummaryCards } from "@/components/nestegg/NesteggSummaryCards";
import { NesteggProjectionChart } from "@/components/nestegg/NesteggProjectionChart";
import { NesteggSavedPlanTabsToolbar } from "@/components/nestegg/NesteggSavedPlanTabsToolbar";
import { NesteggProbabilityCards } from "@/components/nestegg/NesteggProbabilityCards";
import { NesteggComparisonTable } from "@/components/nestegg/NesteggComparisonTable";
import { NesteggQuickWhatIf } from "@/components/nestegg/NesteggQuickWhatIf";
import { NesteggInsightsPanel } from "@/components/nestegg/NesteggInsightsPanel";
import { NesteggGuideSheet } from "@/components/nestegg/NesteggGuideSheet";
import { NesteggWalkthrough } from "@/components/nestegg/NesteggWalkthrough";
import { NesteggSavedCompare } from "@/components/nestegg/NesteggSavedCompare";
import { NesteggExportMenu } from "@/components/nestegg/NesteggExportMenu";
import { NesteggExpandedMetricsSection } from "@/components/nestegg/NesteggExpandedMetricsSection";
import { NesteggPortfolioHighlightCard } from "@/components/nestegg/NesteggPortfolioHighlightCard";
import { NesteggCollapsibleBlock } from "@/components/nestegg/NesteggCollapsibleBlock";
import { NesteggQuickInputsPanel } from "@/components/nestegg/NesteggQuickInputsPanel";
import { NesteggChartTabs } from "@/components/nestegg/NesteggChartTabs";
import { NesteggAllInputsPanel } from "@/components/nestegg/NesteggAllInputsPanel";
import {
  DEFAULT_NESTEGG_INPUTS,
  SCENARIO_LABELS,
  applyScenarioToInputs,
  isNesteggWorkspaceAppDefaults,
  nesteggInputsEqual,
  normalizeNesteggInputs,
} from "@/lib/nestegg/constants";
import { buildNesteggInsights } from "@/lib/nestegg/insights-engine";
import {
  runMonteCarloBatched,
  runMonteCarloScenarioComparisonBatched,
  NESTEGG_MC_MODEL_VERSION, NESTEGG_MC_SEED_POLICY, NESTEGG_MC_COMPARE_PATHS,
  type ScenarioMonteCompareRow,
  type MonteCarloResult,
} from "@/lib/nestegg/monte-carlo";
import {
  runProjection,
  mergeComparisonSeries,
  buildRetirementCashflowYears,
  planHorizonAge,
} from "@/lib/nestegg/projections";
import {
  fetchNesteggScenariosFromSupabase,
  updateNesteggScenarioInSupabase,
} from "@/lib/nestegg/scenarios-supabase";
import type { NesteggInputs, NesteggScenarioId, SavedNesteggScenario } from "@/lib/nestegg/types";
import {
  defaultDraftState,
  loadNesteggDraft,
  saveNesteggDraft,
} from "@/lib/nestegg/storage";
import { formatCurrency } from "@/lib/formatters";
import { fetchPortfolioTotal, fetchPortfolioGoal } from "@/lib/portfolio/portfolio-supabase";
import { buildGoalProjectionSeries } from "@/lib/nestegg/future-value";

function mergeInputs(prev: NesteggInputs, patch: Partial<NesteggInputs>): NesteggInputs {
  const next = { ...prev, ...patch };
  if (next.retirementAge < next.currentAge) {
    next.retirementAge = next.currentAge;
  }
  if (next.lifeExpectancy <= next.retirementAge) {
    next.lifeExpectancy = next.retirementAge + 1;
  }
  if (next.spouseRetirementAge < next.spouseCurrentAge) {
    next.spouseRetirementAge = next.spouseCurrentAge;
  }
  if (next.spouseLifeExpectancy <= next.spouseRetirementAge) {
    next.spouseLifeExpectancy = next.spouseRetirementAge + 1;
  }
  next.currentSavings = Math.max(0, next.currentSavings);
  next.monthlyContribution = Math.max(0, next.monthlyContribution);
  next.monthlyRetirementSpending = Math.max(0, next.monthlyRetirementSpending);
  next.spouseMonthlyContribution = Math.max(0, next.spouseMonthlyContribution);
  next.marginalTaxRatePercent = Math.min(50, Math.max(0, next.marginalTaxRatePercent));
  next.rmdStartAge = Math.min(80, Math.max(65, Math.round(next.rmdStartAge)));
  next.taxDeferredSharePercent = Math.min(100, Math.max(0, next.taxDeferredSharePercent));
  if (next.monteCarloVolatilityPercent !== null && next.monteCarloVolatilityPercent !== undefined) {
    next.monteCarloVolatilityPercent = Math.min(45, Math.max(4, next.monteCarloVolatilityPercent));
  }
  next.survivorSpendingRatioPercent = Math.min(
    100,
    Math.max(35, Math.round(next.survivorSpendingRatioPercent))
  );
  return next;
}

type ActiveSaved = { id: string; name: string };

type LoadedBaseline = {
  inputs: NesteggInputs;
  marketScenario: NesteggScenarioId;
  name: string;
};

const SELECT_DEFAULTS = "__defaults__";
const SELECT_CUSTOM = "__custom__";

const LIGHT_MC_PATHS = 200;
const LIGHT_MC_DEBOUNCE_MS = 800;
const FULL_MC_PATHS = 1100;
const CONSERVATIVE_MC_PATHS = 320;
const MC_POLICY = { modelVersion: NESTEGG_MC_MODEL_VERSION, seedPolicy: NESTEGG_MC_SEED_POLICY };
const LIGHT_POLICY = { ...MC_POLICY, purpose: "light" as const, pathCount: LIGHT_MC_PATHS };
const FULL_POLICY = { ...MC_POLICY, purpose: "full-bundle" as const,
  pathCount: FULL_MC_PATHS + 3 * NESTEGG_MC_COMPARE_PATHS + CONSERVATIVE_MC_PATHS };
type FullAnalysis = { main: MonteCarloResult; compare: ScenarioMonteCompareRow[]; conservative: MonteCarloResult };

export default function NesteggPage() {
  const { user, session, loading } = useAuth();
  const identity = sessionIdentity(session?.access_token);
  const ownerId = user?.id ?? null;
  // Session comparison stays internal; React keys never contain a bearer token.
  const boundary = React.useMemo(() => ownerId && identity ? {
    key: crypto.randomUUID(), scope: createNesteggWorkspaceScope(ownerId, identity),
  } : null, [ownerId, identity]);
  if (loading) return <p role="status">Checking your Nestegg session…</p>;
  if (!user || !session || session.user.id !== user.id) {
    return <p role="status">Sign in to access your Nestegg workspace.</p>;
  }
  // Replacing an account or login session retires all inputs, child views and exports before paint.
  if (!boundary) return <p role="status">Sign in to access your Nestegg workspace.</p>;
  return <NesteggWorkspace key={boundary.key} ownerId={user.id} workspaceScope={boundary.scope} />;
}

export function NesteggWorkspace({ ownerId, workspaceScope }: {
  ownerId: string; workspaceScope: ReturnType<typeof createNesteggWorkspaceScope>;
}) {
  const user = React.useMemo(() => ({ id: ownerId }), [ownerId]);
  const [inputs, setInputs] = React.useState<NesteggInputs>(DEFAULT_NESTEGG_INPUTS);
  const [scenario, setScenario] = React.useState<NesteggScenarioId>("base");
  const [compareOverlay, setCompareOverlay] = React.useState(false);
  const [hydrated, setHydrated] = React.useState(false);
  const [hydrationError, setHydrationError] = React.useState(false);
  const [hydrationAttempt, setHydrationAttempt] = React.useState(0);
  const [storageUnavailable, setStorageUnavailable] = React.useState(false);
  const [cloudScenarios, setCloudScenarios] = React.useState<SavedNesteggScenario[]>([]);
  const [cloudListGeneration, setCloudListGeneration] = React.useState(0);
  const [cloudRefreshGeneration, setCloudRefreshGeneration] = React.useState<number | null>(null);
  const [activeSavedScenario, setActiveSavedScenario] = React.useState<ActiveSaved | null>(null);
  const [loadedBaseline, setLoadedBaseline] = React.useState<LoadedBaseline | null>(null);
  const [tourReplay, setTourReplay] = React.useState(0);
  const [savingGeneration, setSavingGeneration] = React.useState<number | null>(null);
  const [scenarioNameDraft, setScenarioNameDraft] = React.useState("");
  const [planInputsOpen, setPlanInputsOpen] = React.useState(false);
  const [portfolioLinked, setPortfolioLinked] = React.useState(false);
  const [portfolioGoal, setPortfolioGoal] = React.useState(0);
  const [portfolioGoalYear, setPortfolioGoalYear] = React.useState<number | null>(null);
  const planInputsSectionRef = React.useRef<HTMLDivElement>(null);
  const [calculationWorkspaceKey] = React.useState(() => crypto.randomUUID());
  const cloudListClock = React.useRef(createNesteggPublicationClock());
  const workspaceIntentClock = React.useRef(createNesteggPublicationClock());
  const [intentGeneration, setIntentGeneration] = React.useState(0);
  const invalidateWorkspaceIntent = React.useCallback(() => {
    workspaceIntentClock.current.invalidate(); setIntentGeneration(workspaceIntentClock.current.generation());
  }, []);
  const captureWorkspaceIntent = React.useCallback((): NesteggPublication => {
    const session = workspaceScope.capture();
    const intent = workspaceIntentClock.current.next();
    setIntentGeneration(intent.generation);
    return { generation: intent.generation, isCurrent: () => session.isCurrent() && intent.isCurrent() };
  }, [workspaceScope]);
  const savingScenario = savingGeneration !== null && savingGeneration === intentGeneration;
  const cloudRefreshing = cloudRefreshGeneration !== null && cloudRefreshGeneration === cloudListGeneration;
  const inputClock = React.useRef(createNesteggPublicationClock());
  const lightClock = React.useRef(createNesteggPublicationClock());
  const fullClock = React.useRef(createNesteggPublicationClock());
  const [inputGeneration, setInputGeneration] = React.useState(0);
  const [lightGeneration, setLightGeneration] = React.useState(0);
  const [fullGeneration, setFullGeneration] = React.useState(0);
  const invalidateCalculations = React.useCallback(() => {
    inputClock.current.invalidate(); lightClock.current.invalidate(); fullClock.current.invalidate();
    setInputGeneration(inputClock.current.generation());
    setLightGeneration(lightClock.current.generation()); setFullGeneration(fullClock.current.generation());
    fullAnalysisCancelRef.current?.();
  }, []);

  /* ── Light MC — live, debounced (~200 paths for approximate results) ── */
  const [lightEnvelope, setLightEnvelope] = React.useState<NesteggCalculationEnvelope<MonteCarloResult> | null>(null);
  const [lightActivity, setLightActivity] = React.useState<{ generation: number; status: "running" | "complete" | "failed" } | null>(null);
  const lightMcFirstRunRef = React.useRef(true);

  /* ── Full MC — on-demand via button (~2,470 total paths) ── */
  const [fullEnvelope, setFullEnvelope] = React.useState<NesteggCalculationEnvelope<FullAnalysis> | null>(null);
  const [fullActivity, setFullActivity] = React.useState<{ generation: number; status: "running" | "complete" | "failed"; progress: number } | null>(null);
  const fullAnalysisCancelRef = React.useRef<(() => void) | null>(null);

  React.useLayoutEffect(() => {
    workspaceScope.activate();
    return () => { workspaceScope.dispose(); fullAnalysisCancelRef.current?.(); };
  }, [workspaceScope]);

  const refreshCloudScenarios = React.useCallback(async () => {
    const request = workspaceScope.capture();
    if (!request.isCurrent()) return;
    const listing = cloudListClock.current.next();
    setCloudListGeneration(listing.generation);
    const isCurrent = () => request.isCurrent() && listing.isCurrent();
    setCloudRefreshGeneration(listing.generation);
    try {
      const rows = await fetchNesteggScenariosFromSupabase(request);
      if (isCurrent()) setCloudScenarios(rows);
    } catch {
      if (isCurrent()) toast.error("Unable to refresh saved plans");
    } finally {
      if (isCurrent()) setCloudRefreshGeneration(null);
    }
  }, [workspaceScope]);

  const applySavedRow = React.useCallback((row: SavedNesteggScenario, publication?: NesteggPublication) => {
    if (!workspaceScope.isCurrent()) return;
    if (publication && !publication.isCurrent()) return;
    if (!publication) invalidateWorkspaceIntent();
    const normalized = normalizeNesteggInputs(row.inputs);
    invalidateCalculations();
    setInputs(normalized);
    setScenario(row.marketScenario);
    setLoadedBaseline({
      inputs: normalized,
      marketScenario: row.marketScenario,
      name: row.name,
    });
    setActiveSavedScenario({ id: row.id, name: row.name });
    setScenarioNameDraft(row.name);
  }, [workspaceScope, invalidateCalculations, invalidateWorkspaceIntent]);

  React.useEffect(() => {
    const request = workspaceScope.capture();
    if (!request.isCurrent()) return;
    const listing = cloudListClock.current.next();
    setCloudListGeneration(listing.generation);
    const intent = captureWorkspaceIntent();
    setHydrationError(false);
    void (async () => {
      try {
        const [rows, portfolioTotal, goalData] = await Promise.all([
          fetchNesteggScenariosFromSupabase(request), fetchPortfolioTotal(request), fetchPortfolioGoal(request),
        ]);
        if (!request.isCurrent() || !listing.isCurrent() || !intent.isCurrent()) return;
        invalidateCalculations();
        const saved = loadNesteggDraft(ownerId);
        setStorageUnavailable(saved.unavailable);
        const d = saved.draft;
        const hasPortfolio = portfolioTotal > 0;
        setPortfolioGoal(goalData.goal);
        setPortfolioGoalYear(goalData.goalYear);
        setCloudScenarios(rows);
        if (rows.length > 0) {
          const latest = rows[0];
          const normalized = normalizeNesteggInputs(latest.inputs);
          const withPortfolio = hasPortfolio ? { ...normalized, currentSavings: portfolioTotal } : normalized;
          setInputs(withPortfolio);
          setScenario(latest.marketScenario);
          setActiveSavedScenario({ id: latest.id, name: latest.name });
          setScenarioNameDraft(latest.name);
          setLoadedBaseline({ inputs: withPortfolio, marketScenario: latest.marketScenario, name: latest.name });
          setCompareOverlay(d?.compareOverlay ?? false);
        } else {
          const next = d ?? defaultDraftState();
          setInputs({ ...next.inputs, currentSavings: hasPortfolio ? portfolioTotal : d?.inputs.currentSavings ?? 0 });
          setScenario(next.marketScenario);
          setCompareOverlay(next.compareOverlay);
          setActiveSavedScenario(null);
          setScenarioNameDraft("");
          setLoadedBaseline(null);
        }
        setPortfolioLinked(hasPortfolio);
        setHydrated(true);
      } catch {
        if (request.isCurrent() && listing.isCurrent() && intent.isCurrent()) setHydrationError(true);
      }
    })();
  }, [ownerId, workspaceScope, hydrationAttempt, invalidateCalculations, captureWorkspaceIntent]);

  React.useEffect(() => {
    if (!hydrated) return;
    const request = workspaceScope.capture();
    const id = window.setTimeout(() => {
      if (!request.isCurrent()) return;
      setStorageUnavailable(!saveNesteggDraft(ownerId, { inputs, marketScenario: scenario, compareOverlay }));
    }, 400);
    return () => window.clearTimeout(id);
  }, [ownerId, workspaceScope, inputs, scenario, compareOverlay, hydrated]);

  /* ── Derived / memoized projection data ── */

  const scenarioInputs = React.useMemo(
    () => applyScenarioToInputs(inputs, scenario),
    [inputs, scenario]
  );

  const calculationSource = React.useMemo(
    () => captureNesteggCalculationSource(calculationWorkspaceKey, inputs, scenario, inputGeneration),
    [calculationWorkspaceKey, inputs, scenario, inputGeneration]
  );
  // Eligibility is derived during render, before effects/debounce can run. Retained values never
  // reach another input generation, including X → Y → X or identical-input overlapping runs.
  const lightMc = currentNesteggCalculation(lightEnvelope, calculationSource, LIGHT_POLICY, lightGeneration);
  const fullBundle = currentNesteggCalculation(fullEnvelope, calculationSource, FULL_POLICY, fullGeneration);
  const fullMc = fullBundle?.main ?? null;
  const fullCompareRows = fullBundle?.compare ?? [];
  const fullConservativeMc = fullBundle?.conservative ?? null;
  const lightMcRunning = lightActivity?.generation === lightGeneration && lightActivity.status === "running";
  const lightMcFailed = lightActivity?.generation === lightGeneration && lightActivity.status === "failed";
  const fullMcRunning = fullActivity?.generation === fullGeneration && fullActivity.status === "running";
  const fullMcFailed = fullActivity?.generation === fullGeneration && fullActivity.status === "failed";
  const fullMcProgress = fullMcRunning ? fullActivity?.progress ?? 0 : 0;

  const result = React.useMemo(
    () => runProjection(scenarioInputs),
    [scenarioInputs]
  );

  /* ── Light MC effect — runs automatically, debounced after first run ── */

  React.useEffect(() => {
    if (!hydrated) return;
    const request = workspaceScope.capture();
    const inputRequest = inputClock.current.capture();
    const calculation = lightClock.current.next();
    setLightGeneration(calculation.generation);
    const source = calculationSource;
    const scenarioInputsForMc = applyScenarioToInputs(source.inputs, source.scenario);
    let cancelled = false;
    const isCurrent = () => !cancelled && request.isCurrent() && inputRequest.isCurrent() && calculation.isCurrent();

    const run = () => {
      if (!isCurrent()) return;
      setLightActivity({ generation: calculation.generation, status: "running" });
      void runMonteCarloBatched(scenarioInputsForMc, source.scenario, {
        paths: LIGHT_MC_PATHS,
        chunkSize: LIGHT_MC_PATHS,
      }).then((mc) => {
        if (!isCurrent()) return;
        setLightEnvelope({ identity: nesteggCalculationIdentity(source, LIGHT_POLICY, calculation.generation), value: mc });
        setLightActivity({ generation: calculation.generation, status: "complete" });
      }).catch(() => { if (isCurrent()) setLightActivity({ generation: calculation.generation, status: "failed" }); });
    };

    if (lightMcFirstRunRef.current) {
      lightMcFirstRunRef.current = false;
      run();
      return () => { cancelled = true; };
    }

    const timer = window.setTimeout(run, LIGHT_MC_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [calculationSource, hydrated, workspaceScope]);

  /* ── Full MC — triggered by user clicking "Run full analysis" ── */

  const fullMcStale = fullEnvelope !== null && (
    fullEnvelope.identity.inputGeneration !== calculationSource.inputGeneration ||
    fullEnvelope.identity.inputKey !== calculationSource.inputKey
  );

  const runFullAnalysis = React.useCallback(async () => {
    const request = workspaceScope.capture();
    if (!hydrated || !request.isCurrent()) return;
    fullAnalysisCancelRef.current?.();
    let cancelled = false;
    let finished = false;
    fullAnalysisCancelRef.current = () => { cancelled = true; };
    const inputRequest = inputClock.current.capture();
    const calculation = fullClock.current.next();
    setFullGeneration(calculation.generation);
    const source = calculationSource;
    const isCurrent = () => !cancelled && !finished && request.isCurrent() && inputRequest.isCurrent() && calculation.isCurrent();
    const scenarioInputsForMc = applyScenarioToInputs(source.inputs, source.scenario);
    setFullActivity({ generation: calculation.generation, status: "running", progress: 0 });

    try {
      const main = await runMonteCarloBatched(scenarioInputsForMc, source.scenario, {
        paths: FULL_MC_PATHS,
        chunkSize: 100,
        onProgress: (progress) => { if (isCurrent()) setFullActivity({ generation: calculation.generation, status: "running", progress }); },
      });
      if (!isCurrent()) return;

      const compare = await runMonteCarloScenarioComparisonBatched(source.inputs, SCENARIO_LABELS, { pathsPerScenario: NESTEGG_MC_COMPARE_PATHS });
      if (!isCurrent()) return;

      const conservative = await runMonteCarloBatched(
        applyScenarioToInputs(source.inputs, "conservative"),
        "conservative",
        { paths: CONSERVATIVE_MC_PATHS, chunkSize: 160 }
      );
      if (!isCurrent()) return;
      setFullEnvelope({ identity: nesteggCalculationIdentity(source, FULL_POLICY, calculation.generation), value: { main, compare, conservative } });
      setFullActivity({ generation: calculation.generation, status: "complete", progress: 1 });
      finished = true;
    } catch {
      if (isCurrent()) {
        setFullActivity({ generation: calculation.generation, status: "failed", progress: 0 });
        toast.error("Unable to complete the analysis");
        finished = true;
      }
    }
  }, [calculationSource, hydrated, workspaceScope]);

  /* ── Insights (require full MC) ── */

  const nesteggInsights = React.useMemo(() => {
    if (!fullMc || !fullConservativeMc) return [];
    return buildNesteggInsights(inputs, result, fullMc, {
      conservativeMcSuccessRate: fullConservativeMc.successRate,
    });
  }, [inputs, result, fullMc, fullConservativeMc]);

  const heroHighlights = React.useMemo(() => {
    if (!lightMc) return [];
    const lines: string[] = [];
    lines.push(
      `Quick check (~${lightMc.paths} runs): on track about ${Math.round(
        lightMc.successRate * 100
      )}% of the time.`
    );
    if (lightMc.worstCaseDepletionAge !== null && lightMc.chanceRunOut > 0.05) {
      lines.push(
        `In tougher outcomes, money may run low around age ${Math.ceil(lightMc.worstCaseDepletionAge)}.`
      );
    }
    if (result.suggestedExtraMonthly && result.suggestedExtraMonthly > 0) {
      lines.push(
        `Saving about ${formatCurrency(result.suggestedExtraMonthly)} more per month could nudge those odds up.`
      );
    }
    return lines.slice(0, 3);
  }, [lightMc, result.suggestedExtraMonthly]);

  const compareData = React.useMemo(() => {
    const b = runProjection(applyScenarioToInputs(inputs, "base"));
    const c = runProjection(applyScenarioToInputs(inputs, "conservative"));
    const a = runProjection(applyScenarioToInputs(inputs, "aggressive"));
    return mergeComparisonSeries(b.series, c.series, a.series);
  }, [inputs]);

  const cashflowData = React.useMemo(
    () => buildRetirementCashflowYears(scenarioInputs, 15),
    [scenarioInputs]
  );

  const goalProjection = React.useMemo(() => {
    if (!portfolioGoal || portfolioGoal <= 0 || !portfolioGoalYear) return null;
    const now = new Date().getFullYear();
    const monthsToGoal = Math.max(0, (portfolioGoalYear - now) * 12);
    if (monthsToGoal <= 0) return null;
    return buildGoalProjectionSeries({
      currentBalance: inputs.currentSavings,
      goalAmount: portfolioGoal,
      monthsToGoal,
      annualReturnPercent: inputs.annualReturnPercent,
      annualEscalationPercent: inputs.salaryGrowthPercent,
      currentMonthly: inputs.monthlyContribution,
      inflationPercent: inputs.inflationPercent,
    });
  }, [inputs.currentSavings, inputs.annualReturnPercent, inputs.salaryGrowthPercent, inputs.monthlyContribution, inputs.inflationPercent, portfolioGoal, portfolioGoalYear]);

  const goalProbability = React.useMemo(() => {
    if (!lightMc || !portfolioGoal || portfolioGoal <= 0) return null;
    const retirementIdx = lightMc.bandSeries.findIndex(
      (p) => p.age >= inputs.retirementAge
    );
    if (retirementIdx < 0) return null;
    const band = lightMc.bandSeries[retirementIdx]!;
    if (band.p10 >= portfolioGoal) return 0.95;
    if (band.p25 >= portfolioGoal) return 0.8;
    if (band.p50 >= portfolioGoal) return 0.55;
    if (band.p75 >= portfolioGoal) return 0.3;
    if (band.p90 >= portfolioGoal) return 0.12;
    return 0.05;
  }, [lightMc, portfolioGoal, inputs.retirementAge]);

  const horizonAge = planHorizonAge(inputs);

  const usingAppDefaults = isNesteggWorkspaceAppDefaults(inputs, scenario, compareOverlay);

  const dirtyFromSaved =
    activeSavedScenario !== null &&
    loadedBaseline !== null &&
    (!nesteggInputsEqual(inputs, loadedBaseline.inputs) ||
      scenario !== loadedBaseline.marketScenario ||
      scenarioNameDraft.trim() !== loadedBaseline.name);

  const activePlanIsOnCloud =
    activeSavedScenario !== null &&
    cloudScenarios.some((s) => s.id === activeSavedScenario.id);

  const savedPlanSelectValue = activeSavedScenario
    ? activePlanIsOnCloud
      ? activeSavedScenario.id
      : SELECT_CUSTOM
    : usingAppDefaults
      ? SELECT_DEFAULTS
      : SELECT_CUSTOM;

  const canSaveCloudPlan =
    Boolean(user) && activeSavedScenario !== null && activePlanIsOnCloud;

  const onPatch = React.useCallback((patch: Partial<NesteggInputs>) => {
    invalidateWorkspaceIntent(); invalidateCalculations();
    setInputs((prev) => mergeInputs(prev, patch));
  }, [invalidateCalculations, invalidateWorkspaceIntent]);
  const onScenarioChange = React.useCallback((next: NesteggScenarioId) => {
    invalidateWorkspaceIntent(); invalidateCalculations(); setScenario(next);
  }, [invalidateCalculations, invalidateWorkspaceIntent]);

  const resetToAppDefaults = React.useCallback(
    (options?: { clearSavedPlan: boolean }) => {
      const d = defaultDraftState();
      invalidateWorkspaceIntent();
      invalidateCalculations();
      setInputs(d.inputs);
      setScenario(d.marketScenario);
      setCompareOverlay(d.compareOverlay);

      if (options?.clearSavedPlan) {
        setActiveSavedScenario(null);
        setLoadedBaseline(null);
        setScenarioNameDraft("");
        return;
      }

      const onCloud =
        activeSavedScenario !== null &&
        cloudScenarios.some((s) => s.id === activeSavedScenario.id);
      if (onCloud) {
        setScenarioNameDraft(activeSavedScenario.name);
        return;
      }

      setActiveSavedScenario(null);
      setLoadedBaseline(null);
      setScenarioNameDraft("");
    },
    [activeSavedScenario, cloudScenarios, invalidateCalculations, invalidateWorkspaceIntent]
  );

  const onLoadScenario = React.useCallback(
    (row: SavedNesteggScenario) => {
      applySavedRow(row);
    },
    [applySavedRow]
  );

  const onCloudSaved = React.useCallback(
    (row: SavedNesteggScenario, publication: NesteggPublication) => {
      applySavedRow(row, publication);
    },
    [applySavedRow]
  );
  const onCloudRenamed = React.useCallback((row: SavedNesteggScenario, publication: NesteggPublication) => {
    if (!publication.isCurrent() || !workspaceScope.isCurrent() || activeSavedScenario?.id !== row.id) return;
    // Renaming is metadata-only: do not replace unsaved financial inputs with the stored row.
    setActiveSavedScenario({ id: row.id, name: row.name });
    setScenarioNameDraft(row.name);
    setLoadedBaseline((baseline) => baseline ? { ...baseline, name: row.name } : null);
  }, [workspaceScope, activeSavedScenario]);

  const handleCloudScenarioDeleted = React.useCallback(
    async (deletedId: string, intent: NesteggPublication) => {
      const request = workspaceScope.capture();
      if (!request.isCurrent() || !intent.isCurrent()) return;
      const listing = cloudListClock.current.next();
    setCloudListGeneration(listing.generation);
      const isCurrent = () => request.isCurrent() && listing.isCurrent();
      let rows: SavedNesteggScenario[];
      try { rows = await fetchNesteggScenariosFromSupabase(request); }
      catch { if (isCurrent()) toast.error("Unable to refresh saved plans"); return; }
      if (!isCurrent()) return;
      setCloudScenarios(rows);
      if (!intent.isCurrent() || activeSavedScenario?.id !== deletedId) return;
      if (rows[0]) {
        applySavedRow(rows[0], intent);
        toast.message("Switched to your latest saved plan", { description: rows[0].name });
        return;
      }
      const saved = loadNesteggDraft(ownerId);
      setStorageUnavailable(saved.unavailable);
      const d = saved.draft;
      if (d) {
        invalidateCalculations();
        setInputs(d.inputs);
        setScenario(d.marketScenario);
        setCompareOverlay(d.compareOverlay);
      } else {
        invalidateCalculations();
        setInputs({ ...DEFAULT_NESTEGG_INPUTS });
        setScenario("base");
        setCompareOverlay(false);
      }
      setActiveSavedScenario(null);
      setLoadedBaseline(null);
      setScenarioNameDraft("");
    },
    [applySavedRow, ownerId, workspaceScope, invalidateCalculations, activeSavedScenario]
  );

  const onSavedPlanSelect = React.useCallback(
    (value: string) => {
      if (value === SELECT_DEFAULTS) {
        resetToAppDefaults({ clearSavedPlan: true });
        toast.success("App defaults");
        return;
      }
      if (value === SELECT_CUSTOM) return;
      const row = cloudScenarios.find((s) => s.id === value);
      if (row) {
        onLoadScenario(row);
        toast.success("Loaded plan", { description: row.name });
      }
    },
    [cloudScenarios, onLoadScenario, resetToAppDefaults]
  );

  const handleSaveActiveScenario = React.useCallback(async () => {
    const request = workspaceScope.capture();
    if (!request.isCurrent() || !activeSavedScenario || !activePlanIsOnCloud) return;
    const intent = captureWorkspaceIntent();
    const isCurrent = () => request.isCurrent() && intent.isCurrent();
    const savedInputs = { ...inputs }, savedScenario = scenario;
    const savedId = activeSavedScenario.id, savedName = scenarioNameDraft.trim() || "Untitled";
    setSavingGeneration(intent.generation);
    try {
      const row = await updateNesteggScenarioInSupabase(
        savedId, savedInputs, savedScenario, { name: savedName }, request
      );
      if (!isCurrent()) return;
      if (!row) {
        toast.error("Could not save", {
          description: "Check your connection and try again.",
        });
        return;
      }
      const normalized = normalizeNesteggInputs(savedInputs);
      setLoadedBaseline({
        inputs: normalized,
        marketScenario: savedScenario,
        name: row.name,
      });
      setActiveSavedScenario({ id: row.id, name: row.name });
      setScenarioNameDraft(row.name);
      await refreshCloudScenarios();
      if (!isCurrent()) return;
      toast.success("Saved to plan", { description: row.name });
    } catch {
      if (isCurrent()) toast.error("Could not save your plan");
    } finally {
      if (isCurrent()) setSavingGeneration(null);
    }
  }, [
    workspaceScope,
    activeSavedScenario,
    activePlanIsOnCloud,
    inputs,
    scenario,
    scenarioNameDraft,
    refreshCloudScenarios,
    captureWorkspaceIntent,
  ]);

  const focusPlanInputsSection = React.useCallback(() => {
    setPlanInputsOpen(true);
    const request = workspaceScope.capture();
    window.setTimeout(() => {
      if (!request.isCurrent()) return;
      planInputsSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 80);
  }, [workspaceScope]);

  const planInputsTitle = React.useMemo(() => {
    if (activeSavedScenario && activePlanIsOnCloud) {
      return scenarioNameDraft.trim() || activeSavedScenario.name;
    }
    return "Your plan inputs";
  }, [activeSavedScenario, activePlanIsOnCloud, scenarioNameDraft]);

  const planInputsDescription = React.useMemo(() => {
    if (activeSavedScenario && activePlanIsOnCloud) {
      return "Switch plans with the tabs below, or edit — updates apply to the chart above.";
    }
    return "Market presets, volatility, and the numbers that drive the chart above.";
  }, [activeSavedScenario, activePlanIsOnCloud]);

  /* ── Best available MC for export / saved-compare (prefer full, fall back to light) ── */
  const bestAvailableMc = fullMc ?? lightMc;
  const bestAvailableIdentity = fullMc ? fullEnvelope?.identity ?? null : lightMc ? lightEnvelope?.identity ?? null : null;

  if (!hydrated) return <div role="status">
    <p>{hydrationError ? "Unable to load your Nestegg workspace." : "Loading your Nestegg workspace…"}</p>
    {hydrationError && <button onClick={() => setHydrationAttempt(n => n + 1)}>Retry workspace load</button>}
  </div>;
  return (
    <div className="space-y-6 pb-10">
      {storageUnavailable && <p role="alert">Your browser draft could not be saved or read. Changes remain in this workspace; cloud plan saving is separate.</p>}
      <NesteggWalkthrough replayKey={tourReplay} />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-start">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-[#00fff5]/20 bg-gradient-to-br from-[#00fff5]/20 to-[#ff00ff]/15">
            <PiggyBank className="h-6 w-6 text-[#00fff5]" aria-hidden />
          </div>
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold uppercase tracking-wider text-[#00fff5] neon-text-cyan">
                Nestegg
              </h2>
              {usingAppDefaults ? (
                <Badge
                  variant="outline"
                  className="border-[#00fff5]/40 bg-[#00fff5]/10 text-[#00fff5] text-[10px] uppercase tracking-wider"
                >
                  App defaults
                </Badge>
              ) : null}
              {activeSavedScenario ? (
                <Badge
                  variant="outline"
                  className="border-[#ff00ff]/35 bg-[#ff00ff]/10 text-[#ff99ff] text-[10px] font-medium normal-case tracking-normal max-w-[min(100%,280px)] truncate"
                  title={scenarioNameDraft || activeSavedScenario.name}
                >
                  Viewing: {scenarioNameDraft || activeSavedScenario.name}
                </Badge>
              ) : null}
              {dirtyFromSaved && canSaveCloudPlan ? (
                <span className="text-[10px] text-amber-400/90 uppercase tracking-wider">
                  Unsaved edits (save in plan inputs)
                </span>
              ) : null}
            </div>
            <p className="text-xs text-muted-foreground max-w-xl leading-relaxed">
              Explore retirement outcomes, compare stress tests, and tune your plan — results update
              as you go.
              {user
                ? " Saved plans and device drafts are scoped to your account. Older unassigned device drafts are not imported."
                : " Sign in to save named plans."}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 justify-end sm:justify-start">
          <NesteggExportMenu
            inputs={inputs}
            marketScenario={scenario}
            deterministic={result}
            monteCarlo={bestAvailableMc}
            simulationIdentity={bestAvailableIdentity}
            onResetDefaults={() => {
              const wasOnCloud =
                activeSavedScenario !== null &&
                cloudScenarios.some((s) => s.id === activeSavedScenario.id);
              resetToAppDefaults();
              if (wasOnCloud) {
                toast.success("App defaults applied to this plan", {
                  description: "Save changes to this tab to update your cloud copy.",
                });
              } else {
                toast.success("Restored app defaults");
              }
            }}
          />
          <NesteggGuideSheet onReplayTour={() => setTourReplay((k) => k + 1)} />
          {user && cloudScenarios.length > 0 ? (
            <Select value={savedPlanSelectValue} onValueChange={onSavedPlanSelect}>
              <SelectTrigger
                id="saved-plan-select"
                aria-label="Select plan"
                className="h-9 min-w-[min(100vw-10rem,220px)] max-w-[min(100vw-2rem,300px)] border-[#ff00ff]/25 bg-[#ff00ff]/5 text-xs focus:border-[#ff00ff]/45"
              >
                <span className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
                  <span className="shrink-0 text-muted-foreground">Plan:</span>
                  <SelectValue
                    placeholder="Choose a saved plan"
                    className="min-w-0 flex-1 truncate text-left"
                  />
                </span>
              </SelectTrigger>
              <SelectContent className="border-[#ff00ff]/20 bg-card/95 backdrop-blur-xl">
                <SelectItem value={SELECT_DEFAULTS} className="text-xs">
                  App defaults (reset)
                </SelectItem>
                {savedPlanSelectValue === SELECT_CUSTOM ? (
                  <SelectItem value={SELECT_CUSTOM} className="text-xs" disabled>
                    {activeSavedScenario
                      ? `${activeSavedScenario.name} (refresh list if missing)`
                      : "Custom workspace (save a scenario to keep)"}
                  </SelectItem>
                ) : null}
                {cloudScenarios.map((s) => (
                  <SelectItem key={s.id} value={s.id} className="text-xs">
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
          <Button
            type="button"
            variant="outline"
            className="border-[#ff00ff]/25 hover:bg-[#ff00ff]/10 hover:text-[#ff99ff] hover:border-[#ff00ff]/40"
            onClick={focusPlanInputsSection}
          >
            <SlidersHorizontal className="mr-2 h-4 w-4" aria-hidden />
            Edit plan inputs
          </Button>
        </div>
      </div>

      <div className="space-y-5 lg:space-y-6">
        <NesteggPortfolioHighlightCard
          currentPortfolio={inputs.currentSavings}
          projectedAtRetirement={result.nestEggAtRetirement}
          retirementAge={inputs.retirementAge}
          portfolioLinked={portfolioLinked}
        />

        <div className="grid gap-4 xl:grid-cols-3 xl:items-stretch">
          <div className="xl:col-span-2 min-w-0">
            <NesteggProjectionChart
              singleSeries={result.series}
              compareMode={compareOverlay}
              compareData={compareData}
              retirementAge={inputs.retirementAge}
              depletionAge={result.depletionAge}
              lifeExpectancy={horizonAge}
              monteCarloBands={compareOverlay || !lightMc ? null : lightMc.bandSeries}
              goalAmount={portfolioGoal > 0 ? portfolioGoal : null}
            />
          </div>
          <div className="xl:col-span-1 min-w-0">
            <NesteggQuickInputsPanel
              inputs={inputs}
              onChange={onPatch}
              canSave={canSaveCloudPlan}
              dirty={dirtyFromSaved}
              saving={savingScenario}
              onSave={handleSaveActiveScenario}
            />
          </div>
        </div>

        <NesteggChartTabs
          cashflowData={cashflowData}
          compareData={compareData}
          retirementAge={inputs.retirementAge}
          depletionAge={result.depletionAge}
          lifeExpectancy={horizonAge}
          goalProjection={goalProjection}
          goalAmount={portfolioGoal}
          goalYear={portfolioGoalYear}
          currentMonthly={inputs.monthlyContribution}
          escalationPercent={inputs.salaryGrowthPercent}
          goalProbability={goalProbability}
        />

        {/* ── Plan Inputs (collapsible) ── */}
        <NesteggCollapsibleBlock
          ref={planInputsSectionRef}
          className="scroll-mt-24"
          title={planInputsTitle}
          description={planInputsDescription}
          open={planInputsOpen}
          onOpenChange={setPlanInputsOpen}
          headerVariant="planInputs"
          planInputsTitleMode={activeSavedScenario && activePlanIsOnCloud ? "named" : "default"}
        >
          <div className="rounded-lg border border-[#00fff5]/10 bg-card/30 p-3 sm:p-4 space-y-4">
            <NesteggSavedPlanTabsToolbar
              inputs={inputs}
              marketScenario={scenario}
              cloudScenarios={cloudScenarios}
              activeSavedScenarioId={activeSavedScenario?.id ?? null}
              onLoadScenario={onLoadScenario}
              workspaceScope={workspaceScope}
              captureWorkspaceIntent={captureWorkspaceIntent}
              onRefreshCloud={refreshCloudScenarios}
              cloudRefreshing={cloudRefreshing}
              onCloudSaved={onCloudSaved}
              onCloudRenamed={onCloudRenamed}
              onCloudScenarioDeleted={handleCloudScenarioDeleted}
              canSaveActivePlan={canSaveCloudPlan}
              dirtyActivePlan={dirtyFromSaved}
              savingActivePlan={savingScenario}
              onSaveActivePlan={handleSaveActiveScenario}
              activePlanLabelPreview={
                activeSavedScenario && activePlanIsOnCloud
                  ? scenarioNameDraft.trim() || activeSavedScenario.name
                  : ""
              }
            />
            {user && activeSavedScenario && activePlanIsOnCloud ? (
              <div className="space-y-2">
                <Label
                  htmlFor="scenario-label"
                  className="text-[10px] uppercase tracking-wider text-muted-foreground"
                >
                  Scenario label
                </Label>
                <Input
                  id="scenario-label"
                  value={scenarioNameDraft}
                  onChange={(e) => { invalidateWorkspaceIntent(); setScenarioNameDraft(e.target.value); }}
                  className="border-[#ff00ff]/25 bg-[#ff00ff]/5 focus-visible:border-[#ff00ff]/45 max-w-md font-medium text-[#ff99ff] placeholder:text-muted-foreground"
                  placeholder="Name this plan"
                  maxLength={120}
                  autoComplete="off"
                />
                <p className="text-[10px] text-muted-foreground leading-snug">
                  This name appears in your saved plans list and in the header above. Use{" "}
                  <span className="font-medium text-foreground/90">Save changes to this tab</span>{" "}
                  in the toolbar to store it in the cloud.
                </p>
              </div>
            ) : null}
            <NesteggAllInputsPanel
              inputs={inputs}
              onChange={onPatch}
              scenario={scenario}
              onScenarioChange={onScenarioChange}
              compareOverlay={compareOverlay}
              onCompareOverlayChange={(next) => { invalidateWorkspaceIntent(); setCompareOverlay(next); }}
            />
          </div>
        </NesteggCollapsibleBlock>

        {/* ── Live sections (powered by deterministic + light MC) ── */}

        <div className="space-y-3">
          <NesteggCollapsibleBlock
            title="Plan snapshot"
            description="Plain-language read on how your plan looks right now."
            defaultOpen={false}
          >
            <NesteggHeroInsight
              message={result.heroMessage}
              tone={result.heroTone}
              highlights={heroHighlights}
              hideEyebrow
            />
          </NesteggCollapsibleBlock>
          <NesteggCollapsibleBlock
            title="Headline results"
            description="Quick simulation odds — updates live as you edit (~200 paths, approximate)."
            defaultOpen={false}
          >
            {!lightMc ? <p role="status" className="text-xs text-muted-foreground pb-3">
              {lightMcFailed ? "Quick simulation is unavailable. Edit an input to retry, or run full analysis." : "Updating quick simulation for these inputs…"}
            </p> : null}
            {lightMcFailed && !lightMc ? null : <NesteggProbabilityCards
              tier="primary"
              hideSectionLabel
              mc={lightMc}
              deterministic={result}
              lifeExpectancy={horizonAge}
              isRefreshing={lightMcRunning && lightMc !== null}
              progress={0}
            />}
          </NesteggCollapsibleBlock>
          <NesteggCollapsibleBlock
            title="Baseline snapshot"
            description="Single-path balances alongside the headline odds above."
            defaultOpen={false}
          >
            <NesteggSummaryCards tier="primary" result={result} lifeExpectancy={horizonAge} />
          </NesteggCollapsibleBlock>
        </div>

        <NesteggCollapsibleBlock
          title="Try a different plan"
          description="One-tap ideas to test — save a variant from Saved scenarios if you like it."
          defaultOpen={false}
        >
          <NesteggQuickWhatIf inputs={inputs} onPatch={onPatch} hideHeader />
        </NesteggCollapsibleBlock>

        {/* ── Full analysis trigger ── */}

        <div className="rounded-xl border border-[#39ff14]/20 bg-gradient-to-br from-[#39ff14]/5 via-transparent to-[#00fff5]/5 p-5 space-y-3">
          <div className="flex flex-col items-center text-center gap-3 sm:flex-row sm:text-left">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#39ff14]/12 ring-1 ring-[#39ff14]/20">
              <FlaskConical className="h-5 w-5 text-[#39ff14]" aria-hidden />
            </div>
            <div className="min-w-0 flex-1 space-y-0.5">
              <p className="text-sm font-semibold uppercase tracking-wider text-[#39ff14]">
                Full analysis
              </p>
              <p className="text-[11px] text-muted-foreground leading-snug">
                Run {FULL_MC_PATHS.toLocaleString()}+ simulation paths for more detailed success estimates,
                three-scenario comparison, and detailed insights.
              </p>
              {fullMcStale ? (
                <p className="text-[10px] text-amber-400/90">
                  Inputs changed since last run — re-run for updated results
                </p>
              ) : null}
              {fullMcFailed ? <p role="alert" className="text-[10px] text-amber-400/90">
                Analysis unavailable. No partial results were published; retry the full analysis.
              </p> : null}
            </div>
            <Button
              type="button"
              onClick={runFullAnalysis}
              disabled={fullMcRunning}
              className="shrink-0 border border-[#39ff14]/30 bg-[#39ff14]/10 text-[#39ff14] hover:bg-[#39ff14]/20 hover:text-[#39ff14] h-10 px-5"
            >
              <FlaskConical className="mr-2 h-4 w-4" aria-hidden />
              {fullMcRunning ? "Running…" : fullMc ? "Re-run analysis" : "Run full analysis"}
            </Button>
          </div>
          {fullMcRunning ? (
            <div
              className="h-1 w-full overflow-hidden rounded-full bg-[#39ff14]/10"
              role="progressbar"
              aria-valuenow={Math.round(fullMcProgress * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full bg-gradient-to-r from-[#39ff14]/50 to-[#00fff5]/50 transition-[width] duration-150 ease-out"
                style={{ width: `${Math.max(4, fullMcProgress * 100)}%` }}
              />
            </div>
          ) : null}
        </div>

        {/* ── Full-analysis sections (populated after user runs full MC) ── */}

        <NesteggCollapsibleBlock
          title="Compare market presets"
          description={
            fullMc
              ? "Same plan, three stress levels — see how success odds and balances shift."
              : "Run a full analysis above to compare scenarios with Monte Carlo."
          }
          defaultOpen={false}
        >
          {fullMc ? (
            <NesteggComparisonTable
              rows={fullCompareRows}
              loading={fullMcRunning && fullCompareRows.length === 0}
              hideHeader
            />
          ) : (
            <p className="text-xs text-muted-foreground text-center py-4">
              {fullMcRunning ? "Completing full analysis…" : fullMcFailed ? "Full analysis unavailable. Retry above." : "Run a full analysis to populate this comparison."}
            </p>
          )}
        </NesteggCollapsibleBlock>

        {user && cloudScenarios.length > 0 ? (
          <NesteggCollapsibleBlock
            title="Compare to a saved plan"
            description="Side-by-side probability — does not change your workspace."
            defaultOpen={false}
          >
            <NesteggSavedCompare
              cloudScenarios={cloudScenarios}
              workspaceInputs={inputs}
              workspaceMarketScenario={scenario}
              activeSavedId={activeSavedScenario?.id ?? null}
              workspaceMonteCarlo={bestAvailableMc}
              workspaceKey={calculationWorkspaceKey}
              workspaceScope={workspaceScope}
              workspaceSimulationStatus={lightMcFailed && !fullMcRunning ? "unavailable" : "pending"}
              hideHeader
            />
          </NesteggCollapsibleBlock>
        ) : null}

        <NesteggExpandedMetricsSection>
          {fullMc ? (
            <>
              <NesteggProbabilityCards
                tier="secondary"
                mc={fullMc}
                deterministic={result}
                lifeExpectancy={horizonAge}
                isRefreshing={false}
                progress={0}
              />
              <NesteggSummaryCards tier="secondary" result={result} lifeExpectancy={horizonAge} />
            </>
          ) : (
            <p className="text-xs text-muted-foreground text-center py-4">
              {fullMcRunning ? "Completing full analysis…" : fullMcFailed ? "Full analysis unavailable. Retry above." : "Run a full analysis to see detailed simulation metrics."}
            </p>
          )}
        </NesteggExpandedMetricsSection>

        <NesteggInsightsPanel insights={nesteggInsights} />
        <p className="text-[10px] text-muted-foreground leading-relaxed px-1">
          For educational planning purposes only. Not financial advice. Past performance does not
          guarantee future results; returns, inflation, taxes, and health costs are uncertain.
        </p>
      </div>
    </div>
  );
}
