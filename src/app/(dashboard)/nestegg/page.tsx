"use client";

import * as React from "react";
import { toast } from "sonner";
import { PiggyBank, SlidersHorizontal } from "lucide-react";

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
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { NesteggControls } from "@/components/nestegg/NesteggControls";
import { NesteggAdvancedSettings } from "@/components/nestegg/NesteggAdvancedSettings";
import { NesteggFidelitySettings } from "@/components/nestegg/NesteggFidelitySettings";
import { NesteggScenarioSelector } from "@/components/nestegg/NesteggScenarioSelector";
import { NesteggHeroInsight } from "@/components/nestegg/NesteggHeroInsight";
import { NesteggSummaryCards } from "@/components/nestegg/NesteggSummaryCards";
import { NesteggProjectionChart } from "@/components/nestegg/NesteggProjectionChart";
import { NesteggSecondaryChart } from "@/components/nestegg/NesteggSecondaryChart";
import { NesteggSavedPlanTabsToolbar } from "@/components/nestegg/NesteggSavedPlanTabsToolbar";
import { NesteggProbabilityCards } from "@/components/nestegg/NesteggProbabilityCards";
import { NesteggComparisonTable } from "@/components/nestegg/NesteggComparisonTable";
import { NesteggQuickWhatIf } from "@/components/nestegg/NesteggQuickWhatIf";
import { NesteggInsightsPanel } from "@/components/nestegg/NesteggInsightsPanel";
import { NesteggGuideSheet } from "@/components/nestegg/NesteggGuideSheet";
import { NesteggWalkthrough } from "@/components/nestegg/NesteggWalkthrough";
import { NesteggSavedCompare } from "@/components/nestegg/NesteggSavedCompare";
import { NesteggMonteCarloSettings } from "@/components/nestegg/NesteggMonteCarloSettings";
import { NesteggExportMenu } from "@/components/nestegg/NesteggExportMenu";
import { NesteggOrientationStrip } from "@/components/nestegg/NesteggOrientationStrip";
import { NesteggExpandedMetricsSection } from "@/components/nestegg/NesteggExpandedMetricsSection";
import { NesteggPortfolioHighlightCard } from "@/components/nestegg/NesteggPortfolioHighlightCard";
import { NesteggCollapsibleBlock } from "@/components/nestegg/NesteggCollapsibleBlock";
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
  runMonteCarlo,
  runMonteCarloBatched,
  runMonteCarloScenarioComparison,
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
  /** Last saved scenario label (cloud plans only). */
  name: string;
};

const SELECT_DEFAULTS = "__defaults__";
const SELECT_CUSTOM = "__custom__";

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
    // Reset label draft only when switching to another saved plan (id), not on every parent re-render.
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

  const scenarioInputs = React.useMemo(
    () => applyScenarioToInputs(inputs, scenario),
    [inputs, scenario]
  );

  const result = React.useMemo(
    () => runProjection(scenarioInputs),
    [scenarioInputs]
  );

  const [monteCarlo, setMonteCarlo] = React.useState<MonteCarloResult | null>(null);
  const [compareRows, setCompareRows] = React.useState<ScenarioMonteCompareRow[]>([]);
  const [conservativeMcForInsights, setConservativeMcForInsights] =
    React.useState<MonteCarloResult | null>(null);
  const [mcProgress, setMcProgress] = React.useState(0);
  const [mcRunning, setMcRunning] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    setMcRunning(true);
    setMcProgress(0);
    setCompareRows([]);

    void runMonteCarloBatched(scenarioInputs, scenario, {
      paths: 1100,
      chunkSize: 100,
      onProgress: (f) => {
        if (!cancelled) setMcProgress(f);
      },
    }).then((main) => {
      if (cancelled) return;
      setMonteCarlo(main);
      setCompareRows(runMonteCarloScenarioComparison(inputs, SCENARIO_LABELS));
      setConservativeMcForInsights(
        runMonteCarlo(applyScenarioToInputs(inputs, "conservative"), "conservative", {
          paths: 320,
        })
      );
      setMcRunning(false);
    });

    return () => {
      cancelled = true;
    };
  }, [scenarioInputs, scenario, inputs]);

  const nesteggInsights = React.useMemo(() => {
    if (!monteCarlo || !conservativeMcForInsights) return [];
    return buildNesteggInsights(inputs, result, monteCarlo, {
      conservativeMcSuccessRate: conservativeMcForInsights.successRate,
    });
  }, [inputs, result, monteCarlo, conservativeMcForInsights]);

  const heroHighlights = React.useMemo(() => {
    if (!monteCarlo) return [];
    const lines: string[] = [];
    lines.push(
      `Across ${monteCarlo.paths.toLocaleString()} test runs, things look on track about ${Math.round(
        monteCarlo.successRate * 100
      )}% of the time.`
    );
    if (monteCarlo.worstCaseDepletionAge !== null && monteCarlo.chanceRunOut > 0.05) {
      lines.push(
        `In tougher outcomes, money may run low around age ${Math.ceil(monteCarlo.worstCaseDepletionAge)}.`
      );
    }
    if (result.suggestedExtraMonthly && result.suggestedExtraMonthly > 0) {
      lines.push(
        `Saving about ${formatCurrency(result.suggestedExtraMonthly)} more per month could nudge those odds up.`
      );
    }
    return lines.slice(0, 3);
  }, [monteCarlo, result.suggestedExtraMonthly]);

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
            {user && cloudScenarios.length > 0 ? (
              <div className="flex flex-col gap-1.5 pt-1 sm:flex-row sm:flex-wrap sm:items-center sm:gap-2">
                <Label
                  htmlFor="saved-plan-select"
                  className="text-[10px] uppercase tracking-wider text-muted-foreground shrink-0"
                >
                  Load a saved plan
                </Label>
                <Select value={savedPlanSelectValue} onValueChange={onSavedPlanSelect}>
                  <SelectTrigger
                    id="saved-plan-select"
                    className="h-9 w-full min-w-[200px] max-w-sm border-[#ff00ff]/25 bg-[#ff00ff]/5 text-xs focus:border-[#ff00ff]/45 sm:w-[min(100%,280px)]"
                  >
                    <SelectValue placeholder="Choose a saved plan" />
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
              </div>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 justify-end sm:justify-start">
          <NesteggExportMenu
            inputs={inputs}
            marketScenario={scenario}
            deterministic={result}
            monteCarlo={monteCarlo}
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

      <NesteggOrientationStrip />

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
              monteCarloBands={compareOverlay || !monteCarlo ? null : monteCarlo.bandSeries}
            />
          </div>
          <div className="xl:col-span-1 min-h-[260px] min-w-0">
            <NesteggSecondaryChart data={cashflowData} />
          </div>
        </div>

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
              <>
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
              </>
            ) : null}
            <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
              <div className="space-y-4 lg:sticky lg:top-4 lg:self-start">
                <div className="space-y-2">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground px-0.5">
                    Market presets
                  </p>
                  <p className="text-[11px] text-muted-foreground px-0.5">
                    Same inputs, three stress levels — switch tabs to see odds and the chart update.
                  </p>
                  <NesteggScenarioSelector value={scenario} onChange={setScenario} />
                </div>
                <NesteggMonteCarloSettings inputs={inputs} onChange={onPatch} />
                <NesteggControls inputs={inputs} onChange={onPatch} />
              </div>
              <div className="space-y-4">
                <NesteggAdvancedSettings inputs={inputs} onChange={onPatch} />
                <NesteggFidelitySettings inputs={inputs} onChange={onPatch} />
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-lg border border-[#00fff5]/15 bg-card/50 px-3 py-3">
                  <div className="space-y-0.5 min-w-0">
                    <Label htmlFor="compare-overlay" className="text-xs font-semibold text-foreground">
                      Overlay three curves on the chart
                    </Label>
                    <p className="text-[10px] text-muted-foreground leading-snug">
                      Show Base, Conservative, and Aggressive projections at once
                    </p>
                  </div>
                  <Switch
                    id="compare-overlay"
                    checked={compareOverlay}
                    onCheckedChange={setCompareOverlay}
                    className="shrink-0 data-[state=checked]:bg-[#00fff5]"
                  />
                </div>
              </div>
            </div>
          </div>
        </NesteggCollapsibleBlock>

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
            description="Simulation odds — chance of success, risk of running out, and more."
            defaultOpen={false}
          >
            <NesteggProbabilityCards
              tier="primary"
              hideSectionLabel
              mc={monteCarlo}
              deterministic={result}
              lifeExpectancy={horizonAge}
              isRefreshing={mcRunning && monteCarlo !== null}
              progress={mcProgress}
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
          title="Compare market presets"
          description="Same plan, three stress levels — see how success odds and balances shift."
          defaultOpen={false}
        >
          <NesteggComparisonTable rows={compareRows} loading={mcRunning} hideHeader />
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
              workspaceMonteCarlo={monteCarlo}
              hideHeader
            />
          </NesteggCollapsibleBlock>
        ) : null}

        <NesteggCollapsibleBlock
          title="Try a different plan"
          description="One-tap ideas to test — save a variant from Saved scenarios if you like it."
          defaultOpen={false}
        >
          <NesteggQuickWhatIf inputs={inputs} onPatch={onPatch} hideHeader />
        </NesteggCollapsibleBlock>

        <NesteggExpandedMetricsSection>
          <NesteggProbabilityCards
            tier="secondary"
            mc={monteCarlo}
            deterministic={result}
            lifeExpectancy={horizonAge}
            isRefreshing={false}
            progress={mcProgress}
          />
          <NesteggSummaryCards tier="secondary" result={result} lifeExpectancy={horizonAge} />
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
