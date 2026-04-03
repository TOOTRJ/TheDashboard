"use client";

import * as React from "react";
import { toast } from "sonner";
import { FlaskConical, PiggyBank, SlidersHorizontal } from "lucide-react";

import { useAuth } from "@/components/auth/AuthProvider";
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

export default function NesteggPage() {
  const { user, loading: authLoading } = useAuth();
  const [inputs, setInputs] = React.useState<NesteggInputs>(DEFAULT_NESTEGG_INPUTS);
  const [scenario, setScenario] = React.useState<NesteggScenarioId>("base");
  const [compareOverlay, setCompareOverlay] = React.useState(false);
  const [hydrated, setHydrated] = React.useState(false);
  const [cloudScenarios, setCloudScenarios] = React.useState<SavedNesteggScenario[]>([]);
  const [cloudRefreshing, setCloudRefreshing] = React.useState(false);
  const [activeSavedScenario, setActiveSavedScenario] = React.useState<ActiveSaved | null>(null);
  const [loadedBaseline, setLoadedBaseline] = React.useState<LoadedBaseline | null>(null);
  const [tourReplay, setTourReplay] = React.useState(0);
  const [savingScenario, setSavingScenario] = React.useState(false);
  const [scenarioNameDraft, setScenarioNameDraft] = React.useState("");
  const [planInputsOpen, setPlanInputsOpen] = React.useState(false);
  const planInputsSectionRef = React.useRef<HTMLDivElement>(null);

  /* ── Light MC — live, debounced (~200 paths for approximate results) ── */
  const [lightMc, setLightMc] = React.useState<MonteCarloResult | null>(null);
  const [lightMcRunning, setLightMcRunning] = React.useState(false);
  const lightMcFirstRunRef = React.useRef(true);

  /* ── Full MC — on-demand via button (~2,470 total paths) ── */
  const [fullMc, setFullMc] = React.useState<MonteCarloResult | null>(null);
  const [fullCompareRows, setFullCompareRows] = React.useState<ScenarioMonteCompareRow[]>([]);
  const [fullConservativeMc, setFullConservativeMc] = React.useState<MonteCarloResult | null>(null);
  const [fullMcProgress, setFullMcProgress] = React.useState(0);
  const [fullMcRunning, setFullMcRunning] = React.useState(false);
  const fullMcInputsKeyRef = React.useRef<string | null>(null);
  const fullAnalysisCancelRef = React.useRef<(() => void) | null>(null);

  const activeSavedRef = React.useRef<ActiveSaved | null>(null);
  React.useEffect(() => {
    activeSavedRef.current = activeSavedScenario;
  }, [activeSavedScenario]);

  const refreshCloudScenarios = React.useCallback(async () => {
    if (!user) {
      setCloudScenarios([]);
      return;
    }
    setCloudRefreshing(true);
    try {
      const rows = await fetchNesteggScenariosFromSupabase();
      setCloudScenarios(rows);
    } finally {
      setCloudRefreshing(false);
    }
  }, [user]);

  const applySavedRow = React.useCallback((row: SavedNesteggScenario) => {
    const normalized = normalizeNesteggInputs(row.inputs);
    setInputs(normalized);
    setScenario(row.marketScenario);
    setLoadedBaseline({
      inputs: normalized,
      marketScenario: row.marketScenario,
      name: row.name,
    });
    setActiveSavedScenario({ id: row.id, name: row.name });
  }, []);

  React.useEffect(() => {
    if (!activeSavedScenario) {
      setScenarioNameDraft("");
      return;
    }
    setScenarioNameDraft(activeSavedScenario.name);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- activeSavedScenario.id
  }, [activeSavedScenario?.id]);

  React.useEffect(() => {
    if (authLoading) return;
    let cancelled = false;

    (async () => {
      if (user) {
        const rows = await fetchNesteggScenariosFromSupabase();
        if (cancelled) return;
        setCloudScenarios(rows);

        if (rows.length > 0) {
          const latest = rows[0];
          const normalized = normalizeNesteggInputs(latest.inputs);
          setInputs(normalized);
          setScenario(latest.marketScenario);
          setActiveSavedScenario({ id: latest.id, name: latest.name });
          setLoadedBaseline({
            inputs: normalized,
            marketScenario: latest.marketScenario,
            name: latest.name,
          });
          const d = loadNesteggDraft();
          setCompareOverlay(d?.compareOverlay ?? false);
        } else {
          const d = loadNesteggDraft();
          if (d) {
            setInputs(d.inputs);
            setScenario(d.marketScenario);
            setCompareOverlay(d.compareOverlay);
          } else {
            setInputs({ ...DEFAULT_NESTEGG_INPUTS });
            setScenario("base");
            setCompareOverlay(false);
          }
          setActiveSavedScenario(null);
          setLoadedBaseline(null);
        }
      } else {
        const d = loadNesteggDraft();
        if (d) {
          setInputs(d.inputs);
          setScenario(d.marketScenario);
          setCompareOverlay(d.compareOverlay);
        }
        setCloudScenarios([]);
        setActiveSavedScenario(null);
        setLoadedBaseline(null);
      }
      setHydrated(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [user, authLoading]);

  React.useEffect(() => {
    if (!hydrated) return;
    const id = window.setTimeout(() => {
      saveNesteggDraft({
        inputs,
        marketScenario: scenario,
        compareOverlay,
      });
    }, 400);
    return () => window.clearTimeout(id);
  }, [inputs, scenario, compareOverlay, hydrated]);

  /* ── Derived / memoized projection data ── */

  const scenarioInputs = React.useMemo(
    () => applyScenarioToInputs(inputs, scenario),
    [inputs, scenario]
  );

  const monteCarloDepsKey = React.useMemo(
    () => JSON.stringify({ scenario, inputs }),
    [inputs, scenario]
  );

  const result = React.useMemo(
    () => runProjection(scenarioInputs),
    [scenarioInputs]
  );

  /* ── Light MC effect — runs automatically, debounced after first run ── */

  React.useEffect(() => {
    const scenarioInputsForMc = applyScenarioToInputs(inputs, scenario);
    let cancelled = false;

    const run = () => {
      setLightMcRunning(true);
      void runMonteCarloBatched(scenarioInputsForMc, scenario, {
        paths: LIGHT_MC_PATHS,
        chunkSize: LIGHT_MC_PATHS,
      }).then((mc) => {
        if (cancelled) return;
        setLightMc(mc);
        setLightMcRunning(false);
      });
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- monteCarloDepsKey
  }, [monteCarloDepsKey]);

  /* ── Full MC — triggered by user clicking "Run full analysis" ── */

  const fullMcStale = fullMc !== null && fullMcInputsKeyRef.current !== monteCarloDepsKey;

  const runFullAnalysis = React.useCallback(async () => {
    fullAnalysisCancelRef.current?.();
    let cancelled = false;
    fullAnalysisCancelRef.current = () => { cancelled = true; };

    const currentKey = monteCarloDepsKey;
    const scenarioInputsForMc = applyScenarioToInputs(inputs, scenario);

    setFullMcRunning(true);
    setFullMcProgress(0);

    try {
      const main = await runMonteCarloBatched(scenarioInputsForMc, scenario, {
        paths: FULL_MC_PATHS,
        chunkSize: 100,
        onProgress: (f) => { if (!cancelled) setFullMcProgress(f); },
      });
      if (cancelled) return;
      setFullMc(main);

      const compare = await runMonteCarloScenarioComparisonBatched(inputs, SCENARIO_LABELS);
      if (cancelled) return;
      setFullCompareRows(compare);

      const conservative = await runMonteCarloBatched(
        applyScenarioToInputs(inputs, "conservative"),
        "conservative",
        { paths: 320, chunkSize: 160 }
      );
      if (cancelled) return;
      setFullConservativeMc(conservative);

      fullMcInputsKeyRef.current = currentKey;
    } finally {
      if (!cancelled) {
        setFullMcRunning(false);
      }
    }
  }, [inputs, scenario, monteCarloDepsKey]);

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
    setInputs((prev) => mergeInputs(prev, patch));
  }, []);

  const resetToAppDefaults = React.useCallback(
    (options?: { clearSavedPlan: boolean }) => {
      const d = defaultDraftState();
      setInputs(d.inputs);
      setScenario(d.marketScenario);
      setCompareOverlay(d.compareOverlay);

      if (options?.clearSavedPlan) {
        setActiveSavedScenario(null);
        setLoadedBaseline(null);
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
    },
    [activeSavedScenario, cloudScenarios]
  );

  const onLoadScenario = React.useCallback(
    (row: SavedNesteggScenario) => {
      applySavedRow(row);
    },
    [applySavedRow]
  );

  const onCloudSaved = React.useCallback(
    (row: SavedNesteggScenario) => {
      applySavedRow(row);
    },
    [applySavedRow]
  );

  const handleCloudScenarioDeleted = React.useCallback(
    async (deletedId: string) => {
      const rows = await fetchNesteggScenariosFromSupabase();
      setCloudScenarios(rows);
      if (activeSavedRef.current?.id !== deletedId) return;
      if (rows[0]) {
        applySavedRow(rows[0]);
        toast.message("Switched to your latest saved plan", { description: rows[0].name });
        return;
      }
      const d = loadNesteggDraft();
      if (d) {
        setInputs(d.inputs);
        setScenario(d.marketScenario);
        setCompareOverlay(d.compareOverlay);
      } else {
        setInputs({ ...DEFAULT_NESTEGG_INPUTS });
        setScenario("base");
        setCompareOverlay(false);
      }
      setActiveSavedScenario(null);
      setLoadedBaseline(null);
    },
    [applySavedRow]
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
    if (!user || !activeSavedScenario || !activePlanIsOnCloud) return;
    setSavingScenario(true);
    try {
      const row = await updateNesteggScenarioInSupabase(
        activeSavedScenario.id,
        inputs,
        scenario,
        { name: scenarioNameDraft.trim() || "Untitled" }
      );
      if (!row) {
        toast.error("Could not save", {
          description: "Check your connection and try again.",
        });
        return;
      }
      const normalized = normalizeNesteggInputs(inputs);
      setLoadedBaseline({
        inputs: normalized,
        marketScenario: scenario,
        name: row.name,
      });
      setActiveSavedScenario({ id: row.id, name: row.name });
      setScenarioNameDraft(row.name);
      await refreshCloudScenarios();
      toast.success("Saved to plan", { description: row.name });
    } finally {
      setSavingScenario(false);
    }
  }, [
    user,
    activeSavedScenario,
    activePlanIsOnCloud,
    inputs,
    scenario,
    scenarioNameDraft,
    refreshCloudScenarios,
  ]);

  const focusPlanInputsSection = React.useCallback(() => {
    setPlanInputsOpen(true);
    window.setTimeout(() => {
      planInputsSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 80);
  }, []);

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
  const bestAvailableMc = fullMcStale ? lightMc : (fullMc ?? lightMc);

  return (
    <div className="space-y-6 pb-10">
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
                ? " Saved plans sync to your account; a recent visit loads your latest saved plan."
                : " Sign in to save named plans; this device still remembers your in-progress edits."}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 justify-end sm:justify-start">
          <NesteggExportMenu
            inputs={inputs}
            marketScenario={scenario}
            deterministic={result}
            monteCarlo={bestAvailableMc}
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
              onRefreshCloud={refreshCloudScenarios}
              cloudRefreshing={cloudRefreshing}
              onCloudSaved={onCloudSaved}
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
                  onChange={(e) => setScenarioNameDraft(e.target.value)}
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
              onScenarioChange={setScenario}
              compareOverlay={compareOverlay}
              onCompareOverlayChange={setCompareOverlay}
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
            <NesteggProbabilityCards
              tier="primary"
              hideSectionLabel
              mc={lightMc}
              deterministic={result}
              lifeExpectancy={horizonAge}
              isRefreshing={lightMcRunning && lightMc !== null}
              progress={0}
            />
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
                Run {FULL_MC_PATHS.toLocaleString()}+ simulation paths for precise success rates,
                three-scenario comparison, and detailed insights.
              </p>
              {fullMcStale ? (
                <p className="text-[10px] text-amber-400/90">
                  Inputs changed since last run — re-run for updated results
                </p>
              ) : null}
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
              Run a full analysis to populate this comparison.
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
              Run a full analysis to see detailed simulation metrics.
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
