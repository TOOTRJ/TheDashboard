"use client";

import * as React from "react";
import { toast } from "sonner";
import { PiggyBank, RotateCcw } from "lucide-react";

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
import { NesteggControls } from "@/components/nestegg/NesteggControls";
import { NesteggAdvancedSettings } from "@/components/nestegg/NesteggAdvancedSettings";
import { NesteggFidelitySettings } from "@/components/nestegg/NesteggFidelitySettings";
import { NesteggScenarioSelector } from "@/components/nestegg/NesteggScenarioSelector";
import { NesteggHeroInsight } from "@/components/nestegg/NesteggHeroInsight";
import { NesteggSummaryCards } from "@/components/nestegg/NesteggSummaryCards";
import { NesteggProjectionChart } from "@/components/nestegg/NesteggProjectionChart";
import { NesteggSecondaryChart } from "@/components/nestegg/NesteggSecondaryChart";
import { NesteggScenariosManager } from "@/components/nestegg/NesteggScenariosManager";
import {
  DEFAULT_NESTEGG_INPUTS,
  applyScenarioToInputs,
  isNesteggWorkspaceAppDefaults,
  nesteggInputsEqual,
  normalizeNesteggInputs,
} from "@/lib/nestegg/constants";
import {
  runProjection,
  mergeComparisonSeries,
  buildRetirementCashflowYears,
  planHorizonAge,
} from "@/lib/nestegg/projections";
import { fetchNesteggScenariosFromSupabase } from "@/lib/nestegg/scenarios-supabase";
import type { NesteggInputs, NesteggScenarioId, SavedNesteggScenario } from "@/lib/nestegg/types";
import {
  defaultDraftState,
  loadNesteggDraft,
  saveNesteggDraft,
} from "@/lib/nestegg/storage";

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
  return next;
}

type ActiveSaved = { id: string; name: string };

type LoadedBaseline = {
  inputs: NesteggInputs;
  marketScenario: NesteggScenarioId;
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
    });
    setActiveSavedScenario({ id: row.id, name: row.name });
  }, []);

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
      scenario !== loadedBaseline.marketScenario);

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

  const onPatch = React.useCallback((patch: Partial<NesteggInputs>) => {
    setInputs((prev) => mergeInputs(prev, patch));
  }, []);

  const resetToAppDefaults = React.useCallback(() => {
    const d = defaultDraftState();
    setInputs(d.inputs);
    setScenario(d.marketScenario);
    setCompareOverlay(d.compareOverlay);
    setActiveSavedScenario(null);
    setLoadedBaseline(null);
  }, []);

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
        resetToAppDefaults();
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

  return (
    <div className="space-y-6 pb-10">
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
                  title={activeSavedScenario.name}
                >
                  {activeSavedScenario.name}
                </Badge>
              ) : null}
              {dirtyFromSaved ? (
                <span className="text-[10px] text-amber-400/90 uppercase tracking-wider">
                  Unsaved edits
                </span>
              ) : null}
            </div>
            <p className="text-xs text-muted-foreground max-w-xl">
              Retirement analytics and scenario modeling — adjust assumptions and see how your
              trajectory responds in real time.
              {user
                ? " Saved plans sync to your account; new visits load your most recently saved plan."
                : " Sign in to save named scenarios; this device still remembers your in-progress edits."}
            </p>
            {user && cloudScenarios.length > 0 ? (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Label
                  htmlFor="saved-plan-select"
                  className="text-[10px] uppercase tracking-wider text-muted-foreground shrink-0"
                >
                  Saved plan
                </Label>
                <Select value={savedPlanSelectValue} onValueChange={onSavedPlanSelect}>
                  <SelectTrigger
                    id="saved-plan-select"
                    className="h-8 w-full min-w-[200px] max-w-sm border-[#ff00ff]/25 bg-[#ff00ff]/5 text-xs focus:border-[#ff00ff]/45 sm:w-[280px]"
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
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            className="border-[#00fff5]/20 hover:bg-[#00fff5]/10 hover:text-[#00fff5] hover:border-[#00fff5]/40"
            onClick={() => {
              resetToAppDefaults();
              toast.success("Reset to demo defaults");
            }}
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            Reset defaults
          </Button>
          <NesteggScenariosManager
            inputs={inputs}
            marketScenario={scenario}
            onLoadScenario={onLoadScenario}
            cloudScenarios={cloudScenarios}
            onRefreshCloud={refreshCloudScenarios}
            cloudRefreshing={cloudRefreshing}
            activeSavedScenarioId={activeSavedScenario?.id ?? null}
            onCloudSaved={onCloudSaved}
            onCloudScenarioDeleted={handleCloudScenarioDeleted}
          />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-12 lg:items-start">
        <div className="space-y-4 lg:col-span-4">
          <NesteggScenarioSelector value={scenario} onChange={setScenario} />
          <NesteggControls inputs={inputs} onChange={onPatch} />
          <NesteggAdvancedSettings inputs={inputs} onChange={onPatch} />
          <NesteggFidelitySettings inputs={inputs} onChange={onPatch} />
          <div className="flex items-center justify-between rounded-lg border border-[#00fff5]/15 bg-card/50 px-3 py-3">
            <div className="space-y-0.5">
              <Label htmlFor="compare-overlay" className="text-xs font-semibold text-foreground">
                Compare all scenarios on chart
              </Label>
              <p className="text-[10px] text-muted-foreground">
                Overlay Base, Conservative, and Aggressive projections
              </p>
            </div>
            <Switch
              id="compare-overlay"
              checked={compareOverlay}
              onCheckedChange={setCompareOverlay}
              className="data-[state=checked]:bg-[#00fff5]"
            />
          </div>
        </div>

        <div className="space-y-4 lg:col-span-8">
          <NesteggHeroInsight message={result.heroMessage} tone={result.heroTone} />
          <NesteggSummaryCards result={result} lifeExpectancy={horizonAge} />
          <div className="grid gap-4 xl:grid-cols-3">
            <div className="xl:col-span-2">
              <NesteggProjectionChart
                singleSeries={result.series}
                compareMode={compareOverlay}
                compareData={compareData}
                retirementAge={inputs.retirementAge}
                depletionAge={result.depletionAge}
                lifeExpectancy={horizonAge}
              />
            </div>
            <div className="xl:col-span-1 min-h-[280px]">
              <NesteggSecondaryChart data={cashflowData} />
            </div>
          </div>
          <p className="text-[10px] text-muted-foreground leading-relaxed px-1">
            For educational planning purposes only. Not financial advice. Past performance does not
            guarantee future results; returns, inflation, taxes, and health costs are uncertain.
          </p>
        </div>
      </div>
    </div>
  );
}
