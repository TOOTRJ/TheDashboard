/**
 * Colony configuration types and presets.
 * Mirrors Python colony_config.py.
 */

import { GENE_DEFINITIONS, ALL_ASSETS } from "./gene-registry";
import { START_LIMITS } from "./transport";

export interface GeneOverride {
  min?: number;
  max?: number;
  default?: number;
  fixed?: number;
}

export interface ColonyConfig {
  gene_overrides: Record<string, GeneOverride>;
  enabled_genes: string[] | null;
  available_assets: string[] | null;
  max_lifespan_ticks: number | null;
  reproduction_interval: number;
}

export interface ColonyPreset {
  name: string;
  label: string;
  description: string;
  config: ColonyConfig;
  /** Overrides applied to StartConfig (mutation_rate, etc.) */
  startOverrides?: Partial<Pick<StartConfig, "mutation_rate" | "max_probes" | "gen0_count" | "seed_capital" | "tick_interval_ms">>;
}

export function buildDefaultConfig(): ColonyConfig {
  return {
    gene_overrides: {},
    enabled_genes: null,
    available_assets: null,
    max_lifespan_ticks: null,
    reproduction_interval: 100,
  };
}

/** Full start config sent to the API */
export interface StartConfig {
  mode: "simulation" | "paper";
  strategy: string;
  preset?: string;
  colony_config: ColonyConfig;
  gen0_count: number;
  max_capital: number;
  seed_capital: number;
  tick_interval_ms: number;
  mutation_rate: number;
  max_probes: number;
}

export function buildDefaultStartConfig(): StartConfig {
  return {
    mode: "simulation",
    strategy: "genetic_algorithm",
    colony_config: buildDefaultConfig(),
    gen0_count: 10,
    max_capital: 10_000,
    seed_capital: 100,
    tick_interval_ms: 1000,
    mutation_rate: 0.20,
    max_probes: 50,
  };
}

export interface ConfigIssue { field: string; message: string }

/** Match bounded worker input before any request; never rely on number-input attributes. */
export function validateStartConfig(input: unknown): ConfigIssue[] {
  const issues: ConfigIssue[] = [];
  const add = (field: string, message: string) => issues.push({ field, message });
  const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
  if (!record(input)) return [{ field: "configuration", message: "Provide a colony configuration." }];
  const allowed = ["mode", "strategy", "preset", "colony_config", "gen0_count", "max_probes", "max_capital", "seed_capital", "tick_interval_ms", "mutation_rate"];
  if (Object.keys(input).some((key) => !allowed.includes(key))) add("configuration", "Remove unsupported configuration fields.");
  if (input.mode !== "simulation" && input.mode !== "paper") add("mode", "Choose simulation or paper trading.");
  if (!["genetic_algorithm", "differential_evolution", "particle_swarm", "cma_es"].includes(input.strategy as string)) add("strategy", "Choose an available strategy.");
  const preset = input.preset == null ? undefined : PRESETS.find((entry) => entry.name === input.preset);
  if (input.preset != null && !preset) add("preset", "Choose an available preset.");
  const numeric = (key: keyof typeof START_LIMITS, value: unknown) => {
    const limit = START_LIMITS[key];
    if (typeof value !== "number" || !Number.isFinite(value) || value < limit.min || value > limit.max || (limit.integer && !Number.isInteger(value))) {
      add(key, `${limit.label} must be ${limit.integer ? "a whole number" : "a finite number"} from ${limit.min} to ${limit.max}.`);
    }
  };
  for (const key of ["gen0_count", "max_probes", "max_capital", "seed_capital", "tick_interval_ms", "mutation_rate"] as const) numeric(key, input[key]);
  if (typeof input.gen0_count === "number" && typeof input.max_probes === "number" && input.gen0_count > input.max_probes) add("max_probes", "Maximum probes must cover the initial population.");
  if (typeof input.gen0_count === "number" && typeof input.seed_capital === "number" && typeof input.max_capital === "number" && input.gen0_count * input.seed_capital > input.max_capital) add("max_capital", "Maximum capital must fund every initial probe (initial probes × capital per probe).");
  if (input.strategy === "differential_evolution" && typeof input.gen0_count === "number" && (input.gen0_count < 8 || input.gen0_count % 2 !== 0)) add("gen0_count", "Differential evolution requires an even number of at least eight funded accounts: one target and one trial per optimizer slot.");
  const config = input.colony_config;
  if (!record(config)) { add("colony_config", "Provide colony gene and lifecycle settings."); return issues; }
  if (Object.keys(config).some((key) => !["gene_overrides", "enabled_genes", "available_assets", "max_lifespan_ticks", "reproduction_interval"].includes(key))) add("colony_config", "Remove unsupported colony settings.");
  numeric("reproduction_interval", config.reproduction_interval);
  if (config.max_lifespan_ticks !== null) numeric("max_lifespan_ticks", config.max_lifespan_ticks);
  const names = GENE_DEFINITIONS.map((gene) => gene.name);
  const checkSelection = (field: "enabled_genes" | "available_assets", choices: string[], nonempty: boolean) => {
    const values = config[field];
    if (values !== null && (!Array.isArray(values) || (nonempty && values.length === 0) || values.some((value) => typeof value !== "string" || !choices.includes(value)) || new Set(values).size !== values.length)) {
      add(field, field === "available_assets" ? "Choose at least one unique supported trading pair." : "Enabled genes must be unique registered genes.");
    }
  };
  checkSelection("enabled_genes", names, false);
  checkSelection("available_assets", ALL_ASSETS, true);
  if (!record(config.gene_overrides)) { add("gene_overrides", "Provide registered gene overrides."); return issues; }
  const overrides: Record<string, unknown> = { ...preset?.config.gene_overrides, ...config.gene_overrides };
  const ranges = new Map<string, { min: number; max: number }>();
  const assets = Array.isArray(config.available_assets) ? config.available_assets.length : ALL_ASSETS.length;
  for (const name of Object.keys(overrides)) {
    if (!names.includes(name)) add("gene_overrides", "Overrides may only use registered genes.");
  }
  for (const gene of GENE_DEFINITIONS) {
    const value = overrides[gene.name] ?? {};
    if (!record(value)) { add(gene.name, `${gene.label}: provide numeric gene overrides.`); continue; }
    if (Object.keys(value).some((key) => !["min", "max", "fixed", "default"].includes(key))) add(gene.name, `${gene.label}: remove unsupported override fields.`);
    let valid = true;
    for (const key of ["min", "max", "fixed", "default"]) {
      const number = value[key];
      if (number == null) continue;
      if (typeof number !== "number" || !Number.isFinite(number) || number < gene.min || number > gene.max || (gene.type === "int" && !Number.isInteger(number))) {
        add(gene.name, `${gene.label}: ${key} must be ${gene.type === "int" ? "a whole number" : "a finite number"} from ${gene.min} to ${gene.max}.`);
        valid = false;
      }
    }
    if (!valid) continue;
    const min = (value.min as number | undefined) ?? gene.min;
    const max = (value.max as number | undefined) ?? gene.max;
    if (min > max) add(gene.name, `${gene.label}: minimum must not exceed maximum.`);
    for (const key of ["fixed", "default"]) {
      if (typeof value[key] === "number" && (value[key] < min || value[key] > max)) add(gene.name, `${gene.label}: ${key} must fit within its configured range.`);
    }
    const effectiveMax = gene.name === "num_assets" ? Math.min(max, assets) : max;
    if (min > effectiveMax || (gene.name === "num_assets" && [value.fixed, value.default].some((item) => typeof item === "number" && item > effectiveMax))) {
      add(gene.name, "The configured asset count must fit the selected trading pairs.");
    }
    const resolvedDefault = typeof value.default === "number" ? value.default : Math.min(effectiveMax, Math.max(min, gene.default));
    const fixed = typeof value.fixed === "number";
    const disabled = Array.isArray(config.enabled_genes) && !config.enabled_genes.includes(gene.name);
    const locked = fixed ? value.fixed as number : disabled ? resolvedDefault : undefined;
    ranges.set(gene.name, { min: locked ?? min, max: locked ?? effectiveMax });
  }
  for (const [lower, upper, label] of [["ema_fast", "ema_slow", "EMA fast must remain below EMA slow"], ["stop_loss_pct", "take_profit_pct", "Stop loss must remain below take profit"]]) {
    const lo = ranges.get(lower), hi = ranges.get(upper);
    if (lo && hi && lo.min >= hi.max) add(lower, `${label}; fixed values and disabled defaults must allow a valid pair.`);
  }
  return issues;
}

export const PRESETS: ColonyPreset[] = [
  {
    name: "default",
    label: "Default",
    description: "All genes evolve freely within full ranges.",
    config: buildDefaultConfig(),
  },
  {
    name: "rsi_focus",
    label: "RSI Focus",
    description: "Only RSI + risk genes evolve. EMA and volume fixed.",
    config: {
      gene_overrides: {
        volume_threshold: { fixed: 1.5 },
        ema_fast: { fixed: 9.0 },
        ema_slow: { fixed: 21.0 },
      },
      enabled_genes: [
        "rsi_period", "rsi_oversold", "rsi_overbought",
        "stop_loss_pct", "take_profit_pct", "position_size_pct",
        "benchmark_target_pct", "reproduce_target_dollars", "death_drawdown_pct",
      ],
      available_assets: null,
      max_lifespan_ticks: null,
      reproduction_interval: 100,
    },
  },
  {
    name: "conservative_risk",
    label: "Conservative Risk",
    description: "Tighter risk bounds. Single position only.",
    config: {
      gene_overrides: {
        position_size_pct: { min: 0.05, max: 0.15 },
        stop_loss_pct: { min: 0.01, max: 0.05 },
        take_profit_pct: { min: 0.03, max: 0.10 },
        max_open_positions: { fixed: 1.0 },
      },
      enabled_genes: null,
      available_assets: null,
      max_lifespan_ticks: null,
      reproduction_interval: 100,
    },
  },
  {
    name: "wide_exploration",
    label: "Wide Exploration",
    description: "Lower reproduction threshold. Faster evolution cycles.",
    config: {
      gene_overrides: {
        benchmark_target_pct: { min: 0.03, max: 0.08 },
        reproduce_target_dollars: { min: 2.0, max: 8.0 },
      },
      enabled_genes: null,
      available_assets: null,
      max_lifespan_ticks: null,
      reproduction_interval: 50,
    },
  },
  {
    name: "high_risk",
    label: "High Risk",
    description: "Big positions, wide stops, aggressive reproduction.",
    config: {
      gene_overrides: {
        position_size_pct: { min: 0.70, max: 0.90 },
        stop_loss_pct: { min: 0.05, max: 0.10 },
        take_profit_pct: { min: 0.10, max: 0.20 },
        max_open_positions: { fixed: 4.0 },
        benchmark_target_pct: { min: 0.03, max: 0.06 },
        reproduce_target_dollars: { min: 2.0, max: 5.0 },
        death_drawdown_pct: { min: 0.25, max: 0.35 },
      },
      enabled_genes: null,
      available_assets: null,
      max_lifespan_ticks: null,
      reproduction_interval: 75,
    },
  },
  {
    name: "fast_evolution",
    label: "Fast Evolution",
    description: "Rapid generations. High mutation, short lifespan, frequent reproduction.",
    config: {
      gene_overrides: {
        benchmark_target_pct: { min: 0.03, max: 0.05 },
        reproduce_target_dollars: { min: 2.0, max: 5.0 },
        timeframe_minutes: { min: 5, max: 15 },
      },
      enabled_genes: null,
      available_assets: null,
      max_lifespan_ticks: 200,
      reproduction_interval: 25,
    },
    startOverrides: { mutation_rate: 0.35 },
  },
  {
    name: "slow_evolution",
    label: "Slow & Steady",
    description: "Probes mature fully. Low mutation, long lifespan, high bar to reproduce.",
    config: {
      gene_overrides: {
        benchmark_target_pct: { min: 0.08, max: 0.15 },
        reproduce_target_dollars: { min: 15.0, max: 50.0 },
        timeframe_minutes: { min: 30, max: 60 },
      },
      enabled_genes: null,
      available_assets: null,
      max_lifespan_ticks: null,
      reproduction_interval: 200,
    },
    startOverrides: { mutation_rate: 0.10 },
  },
  {
    name: "scalper",
    label: "Scalper",
    description: "Fast in/out, tight stops, small profits. High trade volume.",
    config: {
      gene_overrides: {
        position_size_pct: { min: 0.10, max: 0.25 },
        stop_loss_pct: { min: 0.01, max: 0.03 },
        take_profit_pct: { min: 0.03, max: 0.06 },
        timeframe_minutes: { fixed: 5.0 },
        max_open_positions: { min: 2, max: 4 },
      },
      enabled_genes: null,
      available_assets: null,
      max_lifespan_ticks: null,
      reproduction_interval: 50,
    },
  },
];
