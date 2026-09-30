"use client";

import * as React from "react";
import { FlaskConical, Zap, Settings2, Dna, Shield, Timer, Lock, Unlock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  GENE_DEFINITIONS,
  GENE_GROUPS,
  GENE_GROUP_LABELS,
  ALL_ASSETS,
  genesByGroup,
} from "@/lib/probes/gene-registry";
import type { GeneDefinition, GeneGroup } from "@/lib/probes/gene-registry";
import {
  PRESETS,
  buildDefaultStartConfig,
  type StartConfig,
  type ColonyConfig,
  type GeneOverride,
  validateStartConfig,
} from "@/lib/probes/colony-config";
import type { StrategyInfo } from "@/lib/probes/types";
import {
  STRATEGY_LABELS,
  STRATEGY_DESCRIPTIONS,
  VN_ENDPOINTS,
} from "@/lib/probes/constants";
import { START_LIMITS } from "@/lib/probes/transport";

interface Props {
  open: boolean;
  onClose: () => void;
  onStart: (config: StartConfig) => Promise<boolean>;
  starting: boolean;
  startError?: string | null;
}

const GROUP_ICONS: Record<GeneGroup, React.ElementType> = {
  signal: Dna,
  risk: Shield,
  lifecycle: Timer,
};

// ── Gene display helpers ────────────────────────────────────────────────

function isPctGene(name: string): boolean {
  return name.endsWith("_pct");
}

function geneScale(name: string): number {
  return isPctGene(name) ? 100 : 1;
}

function geneStep(gene: GeneDefinition): number {
  if (isPctGene(gene.name)) return 0.01;
  if (gene.type === "float") return 0.1;
  return 1;
}

function formatGeneValue(gene: GeneDefinition, value: number): string {
  if (isPctGene(gene.name)) return `${(value * 100).toFixed(0)}%`;
  if (gene.name === "volume_threshold") return `${value.toFixed(1)}x`;
  if (gene.name === "reproduce_target_dollars") return `$${value.toFixed(0)}`;
  if (gene.type === "int") return `${Math.round(value)}`;
  return value.toFixed(1);
}

// ── Component ───────────────────────────────────────────────────────────

export function ColonyConfigDialog({ open, onClose, onStart, starting, startError }: Props) {
  const [config, setConfig] = React.useState<StartConfig>(buildDefaultStartConfig());
  const [preset, setPreset] = React.useState("default");
  const [showAdvanced, setShowAdvanced] = React.useState(false);
  const [validationErrors, setValidationErrors] = React.useState<string[]>([]);

  // Gene state: enabled + override per gene
  const [geneEnabled, setGeneEnabled] = React.useState<Record<string, boolean>>(
    () => Object.fromEntries(GENE_DEFINITIONS.map((g) => [g.name, true])),
  );
  const [geneOverrides, setGeneOverrides] = React.useState<Record<string, GeneOverride>>({});
  const [selectedAssets, setSelectedAssets] = React.useState<string[]>([...ALL_ASSETS]);
  const [strategies, setStrategies] = React.useState<StrategyInfo[]>(() =>
    Object.keys(STRATEGY_LABELS).map((name) => ({
      name,
      label: STRATEGY_LABELS[name],
      description: STRATEGY_DESCRIPTIONS[name] ?? "",
    })),
  );

  // Fetch available strategies on mount
  React.useEffect(() => {
    if (!VN_ENDPOINTS.apiUrl || VN_ENDPOINTS.error) return;
    const abort = new AbortController();
    fetch(`${VN_ENDPOINTS.apiUrl}/api/v1/strategies`, {
      signal: abort.signal,
      credentials: "omit",
      redirect: "error",
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((data: StrategyInfo[]) => {
        if (!abort.signal.aborted && Array.isArray(data)) setStrategies(data);
      })
      .catch(() => { /* Keep built-in strategy descriptions when the worker is offline. */ });
    return () => abort.abort();
  }, []);

  // Apply preset
  const applyPreset = (presetName: string) => {
    setPreset(presetName);
    const p = PRESETS.find((x) => x.name === presetName);
    if (!p) return;
    const c = p.config;

    const enabled: Record<string, boolean> = {};
    for (const g of GENE_DEFINITIONS) {
      if (c.enabled_genes) {
        enabled[g.name] = c.enabled_genes.includes(g.name);
      } else {
        enabled[g.name] = true;
      }
      if (c.gene_overrides[g.name]?.fixed != null) {
        enabled[g.name] = false;
      }
    }
    setGeneEnabled(enabled);
    setGeneOverrides({ ...c.gene_overrides });
    setSelectedAssets(c.available_assets ?? [...ALL_ASSETS]);

    // Apply startOverrides (mutation_rate, etc.) from preset
    const defaults = buildDefaultStartConfig();
    setConfig((prev) => ({
      ...defaults,
      ...prev,
      ...(p.startOverrides ?? {}),
      colony_config: { ...c },
      preset: presetName,
    }));
  };

  // Preset summary stats
  const presetSummary = React.useMemo(() => {
    const evolving = GENE_DEFINITIONS.filter((g) => geneEnabled[g.name] && geneOverrides[g.name]?.fixed == null).length;
    const locked = GENE_DEFINITIONS.filter((g) => geneOverrides[g.name]?.fixed != null).length;
    const repro = config.colony_config.reproduction_interval;
    return { evolving, locked, repro };
  }, [geneEnabled, geneOverrides, config.colony_config.reproduction_interval]);

  const handleStart = () => {
    const overrides: Record<string, GeneOverride> = {};
    for (const g of GENE_DEFINITIONS) {
      // An explicit empty override clears a preset gene that the user unlocked.
      overrides[g.name] = geneOverrides[g.name] ?? {};
    }

    const enabledGenes = GENE_DEFINITIONS
      .filter((g) => geneEnabled[g.name])
      .map((g) => g.name);

    const colonyConfig: ColonyConfig = {
      gene_overrides: overrides,
      enabled_genes: enabledGenes.length < GENE_DEFINITIONS.length ? enabledGenes : null,
      available_assets: selectedAssets.length < ALL_ASSETS.length ? selectedAssets : null,
      max_lifespan_ticks: config.colony_config.max_lifespan_ticks,
      reproduction_interval: config.colony_config.reproduction_interval,
    };

    const submission = { ...config, colony_config: colonyConfig, preset };
    const issues = validateStartConfig(submission);
    setValidationErrors(issues.map((issue) => issue.message));
    if (issues.length === 0) void onStart(submission);
  };

  const setGeneFixed = (geneName: string, fixed: boolean, value?: number) => {
    setGeneOverrides((prev) => {
      const ov = { ...prev };
      if (fixed) {
        const gene = GENE_DEFINITIONS.find((g) => g.name === geneName);
        ov[geneName] = { ...ov[geneName], fixed: value ?? gene?.default ?? 0 };
      } else {
        if (ov[geneName]) {
          const { fixed: _, ...rest } = ov[geneName];
          ov[geneName] = rest;
        }
      }
      return ov;
    });
    if (fixed) {
      setGeneEnabled((prev) => ({ ...prev, [geneName]: false }));
    }
  };

  const setGeneRange = (geneName: string, min: number, max: number) => {
    setGeneOverrides((prev) => ({
      ...prev,
      [geneName]: { ...prev[geneName], min, max, fixed: undefined },
    }));
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="border-[#00fff5]/20 bg-card/95 backdrop-blur-xl sm:max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-[#00fff5] uppercase tracking-wider">
            Colony Configuration
          </DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            Configure strategy, genes, and evolution parameters for a new colony.
          </DialogDescription>
        </DialogHeader>

        {/* Strategy selector */}
        <div className="mt-2">
          <span className="text-[10px] font-bold uppercase tracking-widest text-[#bf00ff]">
            Strategy
          </span>
          <Select
            value={config.strategy}
            onValueChange={(v) => setConfig((c) => ({ ...c, strategy: v }))}
          >
            <SelectTrigger className="mt-1 w-full h-8 border-[#bf00ff]/20 bg-[#bf00ff]/5 text-xs">
              <SelectValue placeholder="Select strategy" />
            </SelectTrigger>
            <SelectContent className="border-[#bf00ff]/20 bg-card">
              {strategies.map((s) => (
                <SelectItem key={s.name} value={s.name}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {strategies.find((s) => s.name === config.strategy)?.description && (
            <p className="text-[10px] text-muted-foreground mt-1">
              {strategies.find((s) => s.name === config.strategy)!.description}
            </p>
          )}
        </div>

        {/* Mode + Preset selector */}
        <div className="flex flex-wrap items-end gap-3 mt-2">
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => setConfig((c) => ({ ...c, mode: "simulation" }))}
              className={`h-8 text-xs border ${
                config.mode === "simulation"
                  ? "border-[#39ff14]/50 bg-[#39ff14]/15 text-[#39ff14]"
                  : "border-muted/30 bg-muted/5 text-muted-foreground"
              }`}
            >
              <FlaskConical className="mr-1.5 h-3.5 w-3.5" />
              Simulation
            </Button>
            <Button
              size="sm"
              onClick={() => setConfig((c) => ({ ...c, mode: "paper" }))}
              className={`h-8 text-xs border ${
                config.mode === "paper"
                  ? "border-[#00fff5]/50 bg-[#00fff5]/15 text-[#00fff5]"
                  : "border-muted/30 bg-muted/5 text-muted-foreground"
              }`}
            >
              <Zap className="mr-1.5 h-3.5 w-3.5" />
              Paper Trade
            </Button>
          </div>
          <div className="flex-1 min-w-[180px]">
            <Select value={preset} onValueChange={applyPreset}>
              <SelectTrigger className="w-full h-8 border-[#bf00ff]/20 bg-[#bf00ff]/5 text-xs">
                <SelectValue placeholder="Preset" />
              </SelectTrigger>
              <SelectContent className="border-[#bf00ff]/20 bg-card w-[320px]">
                {PRESETS.map((p) => (
                  <SelectItem key={p.name} value={p.name}>
                    <div className="flex flex-col">
                      <span>{p.label}</span>
                      <span className="text-[10px] text-muted-foreground">{p.description}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Preset summary badge */}
        <div className="flex gap-3 text-[10px] text-muted-foreground mt-1">
          <span><span className="text-[#00fff5] font-mono">{presetSummary.evolving}</span> genes evolve</span>
          <span className="text-muted-foreground/40">|</span>
          <span><span className="text-[#ffff00] font-mono">{presetSummary.locked}</span> locked</span>
          <span className="text-muted-foreground/40">|</span>
          <span>evaluation window <span className="text-[#bf00ff] font-mono">{presetSummary.repro}</span> market minutes</span>
          {config.mutation_rate !== 0.20 && (
            <>
              <span className="text-muted-foreground/40">|</span>
              <span>mutation <span className="text-[#ff6600] font-mono">{(config.mutation_rate * 100).toFixed(0)}%</span></span>
            </>
          )}
        </div>

        {/* Gene groups */}
        <TooltipProvider>
          <div className="space-y-4 mt-3">
            {GENE_GROUPS.map((group) => {
              const genes = genesByGroup(group);
              const Icon = GROUP_ICONS[group];
              const groupColor = group === "signal" ? "#00fff5" : group === "risk" ? "#ff00ff" : "#39ff14";

              return (
                <div key={group}>
                  <div className="flex items-center gap-2 mb-2">
                    <Icon className="h-3.5 w-3.5" style={{ color: groupColor }} />
                    <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: groupColor }}>
                      {GENE_GROUP_LABELS[group]}
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    {genes.map((gene) => {
                      const isFixed = geneOverrides[gene.name]?.fixed != null;
                      const isEnabled = geneEnabled[gene.name] && !isFixed;
                      const override = geneOverrides[gene.name] || {};
                      const effectiveMin = override.min ?? gene.min;
                      const effectiveMax = override.max ?? gene.max;
                      const fixedVal = override.fixed ?? gene.default;
                      const scale = geneScale(gene.name);
                      const step = geneStep(gene);

                      return (
                        <div
                          key={gene.name}
                          className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                            isFixed
                              ? "border-[#ffff00]/20 bg-[#ffff00]/5"
                              : isEnabled
                                ? "border-[#00fff5]/10 bg-[#00fff5]/5"
                                : "border-muted/10 bg-muted/5 opacity-60"
                          }`}
                        >
                          {/* Enable checkbox */}
                          <Checkbox
                            checked={isEnabled}
                            onCheckedChange={(checked) => {
                              setGeneEnabled((prev) => ({ ...prev, [gene.name]: !!checked }));
                              if (checked && isFixed) {
                                setGeneFixed(gene.name, false);
                              }
                            }}
                            className="data-[state=checked]:bg-[#00fff5] data-[state=checked]:border-[#00fff5]"
                          />

                          {/* Gene label with tooltip */}
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="text-xs font-medium w-28 shrink-0 cursor-help">
                                {gene.label}
                              </span>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-xs">
                              <p className="text-xs">{gene.description}</p>
                            </TooltipContent>
                          </Tooltip>

                          {/* Lock toggle */}
                          <div className="flex items-center gap-1 shrink-0">
                            {isFixed
                              ? <Lock className="h-3 w-3 text-[#ffff00]" />
                              : <Unlock className="h-3 w-3 text-muted-foreground/40" />
                            }
                            <Switch
                              checked={isFixed}
                              onCheckedChange={(checked) => setGeneFixed(gene.name, checked)}
                              className="scale-75 data-[state=checked]:bg-[#ffff00]"
                            />
                          </div>

                          {/* Range or fixed value */}
                          <div className="flex-1 min-w-0">
                            {isFixed ? (
                              <div className="flex items-center gap-2">
                                <Input
                                  type="number"
                                  step={step}
                                  min={gene.min}
                                  max={gene.max}
                                  value={fixedVal}
                                  onChange={(e) => setGeneFixed(gene.name, true, Number(e.target.value))}
                                  className="h-6 w-20 text-xs font-mono border-[#ffff00]/20 bg-[#ffff00]/5"
                                />
                                <span className="text-[9px] text-[#ffff00]">
                                  {formatGeneValue(gene, fixedVal)}
                                </span>
                              </div>
                            ) : (
                              <div className="flex items-center gap-2">
                                <span className="text-[9px] font-mono text-muted-foreground w-12 text-right shrink-0">
                                  {formatGeneValue(gene, effectiveMin)}
                                </span>
                                <Slider
                                  min={gene.min * scale}
                                  max={gene.max * scale}
                                  step={1}
                                  value={[effectiveMin * scale, effectiveMax * scale]}
                                  onValueChange={([lo, hi]) => setGeneRange(gene.name, lo / scale, hi / scale)}
                                  className="flex-1"
                                  disabled={!isEnabled}
                                />
                                <span className="text-[9px] font-mono text-muted-foreground w-12 shrink-0">
                                  {formatGeneValue(gene, effectiveMax)}
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                    {/* Inline hint for reproduction genes */}
                    {group === "lifecycle" && (
                      <p className="text-[9px] italic text-muted-foreground/60 ml-4 mt-0.5">
                        Self-reproduction and diversity injection wait for cohort boundaries. Profit thresholds do not interrupt the shared evaluation window.
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </TooltipProvider>

        {/* Asset selector */}
        <div className="mt-4">
          <span className="text-[10px] font-bold uppercase tracking-widest text-[#bf00ff]">
            Trading Pairs
          </span>
          <div className="flex flex-wrap gap-2 mt-2">
            {ALL_ASSETS.map((asset) => {
              const checked = selectedAssets.includes(asset);
              return (
                <label
                  key={asset}
                  className={`flex items-center gap-1.5 rounded-md border px-2 py-1 cursor-pointer text-xs ${
                    checked
                      ? "border-[#00fff5]/30 bg-[#00fff5]/10 text-[#00fff5]"
                      : "border-muted/20 bg-muted/5 text-muted-foreground"
                  }`}
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={(c) => {
                      setSelectedAssets((prev) =>
                        c ? [...prev, asset] : prev.filter((a) => a !== asset),
                      );
                    }}
                    className="scale-75"
                  />
                  {asset}
                </label>
              );
            })}
          </div>
        </div>

        {/* Advanced toggle */}
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex items-center gap-2 mt-3 text-xs text-muted-foreground hover:text-[#00fff5] transition-colors"
        >
          <Settings2 className="h-3.5 w-3.5" />
          {showAdvanced ? "Hide" : "Show"} Advanced Settings
        </button>

        {showAdvanced && (
          <div className="grid grid-cols-2 gap-3 mt-2 rounded-lg border border-[#00fff5]/10 bg-[#00fff5]/5 p-3">
            <div className="space-y-1">
              <Label className="text-[9px] uppercase tracking-wider text-muted-foreground">
                Initial Probes
              </Label>
              <Input
                type="number" min={START_LIMITS.gen0_count.min} max={START_LIMITS.gen0_count.max} step={1}
                value={config.gen0_count}
                onChange={(e) => setConfig((c) => ({ ...c, gen0_count: Number(e.target.value) }))}
                className="h-7 text-xs font-mono border-[#00fff5]/20 bg-transparent"
              />
              {config.strategy === "differential_evolution" && (
                <p className="text-[10px] text-muted-foreground">
                  Choose an even count of at least 8. Each optimizer slot uses two funded accounts
                  to compare its target and trial over the same market window.
                </p>
              )}
            </div>
            <div className="space-y-1">
              <Label className="text-[9px] uppercase tracking-wider text-muted-foreground">
                Max Capital ($)
              </Label>
              <Input
                type="number" min={START_LIMITS.max_capital.min} max={START_LIMITS.max_capital.max} step={10}
                value={config.max_capital}
                onChange={(e) => setConfig((c) => ({ ...c, max_capital: Number(e.target.value) }))}
                className="h-7 text-xs font-mono border-[#00fff5]/20 bg-transparent"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-[9px] uppercase tracking-wider text-muted-foreground">
                Capital Per Probe ($)
              </Label>
              <Input
                type="number" min={START_LIMITS.seed_capital.min} max={START_LIMITS.seed_capital.max} step={10}
                value={config.seed_capital}
                onChange={(e) => setConfig((c) => ({ ...c, seed_capital: Number(e.target.value) }))}
                className="h-7 text-xs font-mono border-[#00fff5]/20 bg-transparent"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-[9px] uppercase tracking-wider text-muted-foreground">
                Tick Interval (ms)
              </Label>
              <Input
                type="number" min={START_LIMITS.tick_interval_ms.min} max={START_LIMITS.tick_interval_ms.max} step={1}
                value={config.tick_interval_ms}
                onChange={(e) => setConfig((c) => ({ ...c, tick_interval_ms: Number(e.target.value) }))}
                className="h-7 text-xs font-mono border-[#00fff5]/20 bg-transparent"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-[9px] uppercase tracking-wider text-muted-foreground">
                Mutation Rate
              </Label>
              <Input
                type="number" min={START_LIMITS.mutation_rate.min} max={START_LIMITS.mutation_rate.max} step={0.05}
                value={config.mutation_rate}
                onChange={(e) => setConfig((c) => ({ ...c, mutation_rate: Number(e.target.value) }))}
                className="h-7 text-xs font-mono border-[#00fff5]/20 bg-transparent"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-[9px] uppercase tracking-wider text-muted-foreground">
                Evaluation window (market minutes)
              </Label>
              <Input
                type="number" min={START_LIMITS.reproduction_interval.min} max={START_LIMITS.reproduction_interval.max} step={1}
                value={config.colony_config.reproduction_interval}
                onChange={(e) => setConfig((c) => ({
                  ...c,
                  colony_config: { ...c.colony_config, reproduction_interval: Number(e.target.value) },
                }))}
                className="h-7 text-xs font-mono border-[#00fff5]/20 bg-transparent"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-[9px] uppercase tracking-wider text-muted-foreground">
                Maximum candidate age (market minutes after warmup)
              </Label>
              <Input
                type="number" min={START_LIMITS.max_lifespan_ticks.min} max={START_LIMITS.max_lifespan_ticks.max} step={1}
                value={config.colony_config.max_lifespan_ticks ?? 0}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setConfig((c) => ({
                    ...c,
                    colony_config: { ...c.colony_config, max_lifespan_ticks: v === 0 ? null : v },
                  }));
                }}
                className="h-7 text-xs font-mono border-[#00fff5]/20 bg-transparent"
              />
              <p className="text-[9px] text-muted-foreground">0 means no age limit. Age starts when every candidate is ready.</p>
            </div>
            <div className="space-y-1">
              <Label className="text-[9px] uppercase tracking-wider text-muted-foreground">
                Max Probes
              </Label>
              <Input
                type="number" min={START_LIMITS.max_probes.min} max={START_LIMITS.max_probes.max} step={1}
                value={config.max_probes}
                onChange={(e) => setConfig((c) => ({ ...c, max_probes: Number(e.target.value) }))}
                className="h-7 text-xs font-mono border-[#00fff5]/20 bg-transparent"
              />
            </div>
          </div>
        )}

        {/* Launch button */}
        {(validationErrors.length > 0 || startError) && (
          <div role="alert" className="space-y-1 text-sm text-destructive">
            {validationErrors.map((message, index) => <p key={index}>{message}</p>)}
            {startError && <p>{startError}</p>}
          </div>
        )}
        {VN_ENDPOINTS.error && <p role="alert" className="text-sm text-destructive">{VN_ENDPOINTS.error}</p>}
        <Button
          onClick={handleStart}
          disabled={starting || selectedAssets.length === 0 || !!VN_ENDPOINTS.error}
          className="w-full mt-4 h-10 bg-gradient-to-r from-[#00fff5] to-[#ff00ff] text-black font-bold hover:opacity-90"
        >
          {starting ? "Launching..." : "Launch Colony"}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
