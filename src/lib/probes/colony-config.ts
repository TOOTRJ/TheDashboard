/**
 * Colony configuration types and presets.
 * Mirrors Python colony_config.py.
 */

import { GENE_DEFINITIONS, ALL_ASSETS } from "./gene-registry";

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
    colony_config: buildDefaultConfig(),
    gen0_count: 10,
    max_capital: 10_000,
    seed_capital: 100,
    tick_interval_ms: 1000,
    mutation_rate: 0.20,
    max_probes: 50,
  };
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
        "benchmark_target_pct", "death_drawdown_pct",
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
      },
      enabled_genes: null,
      available_assets: null,
      max_lifespan_ticks: null,
      reproduction_interval: 50,
    },
  },
];
