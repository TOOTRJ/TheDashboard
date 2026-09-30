/**
 * Gene Registry — TypeScript mirror of the Python gene_registry.py.
 * Single source of truth for gene definitions in the dashboard.
 *
 * Adding a new gene: add one entry to GENE_DEFINITIONS below.
 * It auto-appears in the config dialog, genome radar, and probe detail.
 */

export type GeneType = "float" | "int";
export type GeneGroup = "signal" | "risk" | "lifecycle";

export interface GeneDefinition {
  name: string;
  label: string;
  group: GeneGroup;
  min: number;
  max: number;
  default: number;
  type: GeneType;
  description: string;
}

/**
 * All gene definitions in registration order.
 * Must match the Python GENE_REGISTRY exactly.
 */
export const GENE_DEFINITIONS: GeneDefinition[] = [
  // Signal genes
  {
    name: "rsi_period",
    label: "RSI Period",
    group: "signal",
    min: 5, max: 30, default: 14,
    type: "int",
    description: "Number of candles used to compute the Relative Strength Index.",
  },
  {
    name: "rsi_oversold",
    label: "RSI Oversold",
    group: "signal",
    min: 20, max: 45, default: 32,
    type: "float",
    description: "RSI threshold below which an asset is considered oversold (buy signal).",
  },
  {
    name: "rsi_overbought",
    label: "RSI Overbought",
    group: "signal",
    min: 55, max: 85, default: 70,
    type: "float",
    description: "RSI threshold above which an asset is considered overbought (sell signal).",
  },
  {
    name: "ema_fast",
    label: "EMA Fast",
    group: "signal",
    min: 3, max: 20, default: 9,
    type: "int",
    description: "Period of the fast Exponential Moving Average. Must be less than EMA Slow.",
  },
  {
    name: "ema_slow",
    label: "EMA Slow",
    group: "signal",
    min: 10, max: 60, default: 21,
    type: "int",
    description: "Period of the slow Exponential Moving Average.",
  },
  {
    name: "volume_threshold",
    label: "Volume Threshold",
    group: "signal",
    min: 1.0, max: 3.0, default: 1.4,
    type: "float",
    description: "Multiplier of average volume required to confirm entry signal.",
  },
  // Risk genes
  {
    name: "position_size_pct",
    label: "Position Size %",
    group: "risk",
    min: 0.05, max: 0.90, default: 0.75,
    type: "float",
    description: "Fraction of capital allocated per trade.",
  },
  {
    name: "stop_loss_pct",
    label: "Stop Loss %",
    group: "risk",
    min: 0.01, max: 0.10, default: 0.03,
    type: "float",
    description: "Maximum loss percentage before a position is automatically closed.",
  },
  {
    name: "take_profit_pct",
    label: "Take Profit %",
    group: "risk",
    min: 0.03, max: 0.20, default: 0.07,
    type: "float",
    description: "Target profit percentage to automatically close a winning position.",
  },
  {
    name: "max_open_positions",
    label: "Max Positions",
    group: "risk",
    min: 1, max: 4, default: 1,
    type: "int",
    description: "Maximum number of simultaneous open positions.",
  },
  // Lifecycle genes
  {
    name: "timeframe_minutes",
    label: "Timeframe (min)",
    group: "lifecycle",
    min: 5, max: 60, default: 15,
    type: "int",
    description: "Candle timeframe in minutes for signal computation.",
  },
  {
    name: "benchmark_target_pct",
    label: "Reproduce At %",
    group: "lifecycle",
    min: 0.03, max: 0.15, default: 0.08,
    type: "float",
    description: "Minimum ROI required for a probe to be eligible for reproduction.",
  },
  {
    name: "reproduce_target_dollars",
    label: "Reproduce At $",
    group: "lifecycle",
    min: 2.0, max: 50.0, default: 10.0,
    type: "float",
    description: "Dollar profit target for reproduction eligibility (OR'd with ROI %).",
  },
  {
    name: "death_drawdown_pct",
    label: "Death Drawdown %",
    group: "lifecycle",
    min: 0.10, max: 0.35, default: 0.20,
    type: "float",
    description: "Maximum drawdown percentage before a probe dies.",
  },
  {
    name: "num_assets",
    label: "# Assets",
    group: "lifecycle",
    min: 1, max: 3, default: 2,
    type: "int",
    description: "Number of trading pairs the probe monitors simultaneously.",
  },
];

// Derived lookups (backward-compatible exports)
export const GENE_BOUNDS: Record<string, [number, number]> = Object.fromEntries(
  GENE_DEFINITIONS.map((g) => [g.name, [g.min, g.max]]),
) as Record<string, [number, number]>;

export const GENE_LABELS: Record<string, string> = Object.fromEntries(
  GENE_DEFINITIONS.map((g) => [g.name, g.label]),
);

export const GENE_GROUPS: GeneGroup[] = ["signal", "risk", "lifecycle"];

export const GENE_GROUP_LABELS: Record<GeneGroup, string> = {
  signal: "Signal Genes",
  risk: "Risk Genes",
  lifecycle: "Lifecycle Genes",
};

export function genesByGroup(group: GeneGroup): GeneDefinition[] {
  return GENE_DEFINITIONS.filter((g) => g.group === group);
}

export const ALL_ASSETS = [
  "SOL/USDC",
  "JUP/USDC",
  "BONK/USDC",
  "WIF/USDC",
  "JTO/USDC",
  "PYTH/USDC",
  "ORCA/USDC",
  "RAY/USDC",
];
