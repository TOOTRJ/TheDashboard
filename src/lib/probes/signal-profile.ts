/** Versioned signal semantics are separate from which genome values evolve. */
export type StrategyProfile = "rsi_ema_volume_v1" | "ema_baseline_v1";

export type SignalPolicy = {
  version: "ema-crossover-v1";
  profile: "ema_baseline_v1";
  rsi_enabled: false;
  volume_enabled: false;
  warmup_completed_bars: 61;
  entry: "previous_fast_lte_slow_then_fast_gt_slow";
  exit: "previous_fast_gte_slow_then_fast_lt_slow";
  execution: "later_eligible_quote";
} | {
  version: "rsi-ema-volume-v1";
  profile: "rsi_ema_volume_v1";
  rsi_enabled: true;
  volume_enabled: true;
  warmup_completed_bars: null;
  entry: "rsi_oversold_ema_above_and_volume";
  exit: "rsi_overbought_or_ema_below";
  execution: "later_eligible_quote";
};

/** Unknown/missing policies must not be inferred from a preset or gene list. */
export function parseSignalPolicy(value: unknown): SignalPolicy | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const item = value as Record<string, unknown>;
  if (item.execution !== "later_eligible_quote") return undefined;
  if (item.version === "ema-crossover-v1" && item.profile === "ema_baseline_v1" &&
      item.rsi_enabled === false && item.volume_enabled === false && item.warmup_completed_bars === 61 &&
      item.entry === "previous_fast_lte_slow_then_fast_gt_slow" &&
      item.exit === "previous_fast_gte_slow_then_fast_lt_slow") {
    return { version: item.version, profile: item.profile, rsi_enabled: false, volume_enabled: false,
      warmup_completed_bars: 61, entry: item.entry, exit: item.exit, execution: item.execution };
  }
  if (item.version === "rsi-ema-volume-v1" && item.profile === "rsi_ema_volume_v1" &&
      item.rsi_enabled === true && item.volume_enabled === true && item.warmup_completed_bars === null &&
      item.entry === "rsi_oversold_ema_above_and_volume" && item.exit === "rsi_overbought_or_ema_below") {
    return { version: item.version, profile: item.profile, rsi_enabled: true, volume_enabled: true,
      warmup_completed_bars: null, entry: item.entry, exit: item.exit, execution: item.execution };
  }
  return undefined;
}

/** Only an absent runtime field may fall back to the immutable initial policy. */
export function savedSignalPolicy(config: unknown): SignalPolicy | undefined {
  if (!config || typeof config !== "object" || Array.isArray(config)) return undefined;
  const record = config as Record<string, unknown>;
  const runtime = record.runtime;
  if (runtime && typeof runtime === "object" && !Array.isArray(runtime) && Object.hasOwn(runtime, "signal_policy")) {
    return parseSignalPolicy((runtime as Record<string, unknown>).signal_policy);
  }
  return parseSignalPolicy(record.signal_policy);
}

export function signalPolicyDescription(value: unknown): string {
  const policy = parseSignalPolicy(value);
  if (!policy) return "Signal profile unavailable for this run. Historical genes alone do not identify its signal rules.";
  if (policy.profile === "ema_baseline_v1") return "Two-gene EMA baseline: bullish crossing enters, bearish crossing exits. RSI and volume filters are off. All candidates require 61 completed timeframe bars before evaluation; fills wait for a later eligible quote. Protective exits remain active.";
  return "RSI, EMA trend and volume profile: RSI oversold, EMA fast above slow and volume confirm entry; RSI overbought or EMA fast below slow exits. Fills wait for a later eligible quote; protective exits remain active.";
}
