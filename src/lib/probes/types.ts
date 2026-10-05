import type { ExecutionPolicy, TradeExecution, ProbeAccounting } from "./execution";
import type { SignalPolicy } from "./signal-profile";

export type ProbeState =
  | "BORN"
  | "FUNDED"
  | "OBSERVING"
  | "TRADING"
  | "REPRODUCING"
  | "DYING"
  | "DEAD";

export type TradeExitReason =
  | "TAKE_PROFIT"
  | "STOP_LOSS"
  | "SIGNAL_EXIT"
  | "PROBE_DYING"
  | "REPRODUCING"
  | "EVOLUTION"
  | "TERMINAL_LOSS";

// "unknown" is a UI state while no authoritative worker status is available.
export type SimulationStatus = "running" | "paused" | "risk_halted" | "stopped" | "starting" | "failed" | "unknown";

export interface RiskControl {
  policy: "initial-account-loss-v1";
  threshold_fraction: number;
  baseline_equity: number | null;
  observed_equity: number | null;
  observed_loss_fraction: number | null;
  observed_at: string | null;
  trip_id: string | null;
  tripped_at: string | null;
  trip_equity: number | null;
  trip_loss_fraction: number | null;
  last_recovered_at: string | null;
  recovery_count: number;
}

export interface LifecyclePolicy {
  version: "acknowledged-terminal-sealed-generations-v1";
  terminal_event: "probe_dead";
  generation_completion: "sealed_births_all_terminal_acknowledged";
  generation_semantics: "birth_epoch_not_ancestry_depth";
  generation_diversity: "rms_pairwise_global_normalized_numeric_v1";
  generation_diversity_assets: "excluded";
  reproduced_count: "distinct_sources_with_acknowledged_offspring_before_completion";
  closed_trade_retention: number;
  dead_probe_retention: number;
  generation_history_retention: number;
}

export interface SearchSpec {
  version: "search-spec-v1";
  seed: string;
  algorithm: string;
  epoch: number;
  stream_policy: "sha256-namespaced-search-v1";
  optimizer_state_checkpointed: false;
}

export interface EvaluationPolicy {
  version: "common-market-window-v1";
  horizon_unit: "market_minutes";
  warmup: "all_candidates_ready";
  interruptions: "abort_without_tell";
}

export interface EvaluationCohort {
  phase: "warming" | "evaluating" | "completed" | "aborted";
  iteration_id: string;
  member_count: number;
  completed_count: number;
  started_at: number | null;
  ends_at: number | null;
  abort_reason: string | null;
}

export interface Genome {
  rsi_period: number;
  rsi_oversold: number;
  rsi_overbought: number;
  ema_fast: number;
  ema_slow: number;
  volume_threshold: number;
  position_size_pct: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  max_open_positions: number;
  timeframe_minutes: number;
  benchmark_target_pct: number;
  reproduce_target_dollars: number;
  death_drawdown_pct: number;
  num_assets: number;
  assets: string[];
  generation: number;
  parent_ids: string[];
}

export interface ProbeMetrics {
  execution_sampling?: "pre_decision";
  terminal_execution_costs_in_returns?: boolean;
  accounting?: ProbeAccounting | null;
  policy_version?: string;
  fitness_version?: string;
  status?: string;
  sharpe_ratio?: number | null;
  return_count?: number;
  missing_periods?: number;
  last_sample_endpoint?: number | null;
  last_sample_observed_at?: number | null;
  window_start_endpoint?: number | null;
  current_drawdown?: number;
}

export interface Probe {
  id: string;
  probe_name: string;
  generation: number;
  parent_id: string | null;
  parent_ids?: string[];
  state: ProbeState;
  genome: Genome;
  initial_capital: number;
  current_capital: number;
  peak_capital: number;
  total_trades: number;
  winning_trades: number;
  total_pnl: number;
  max_drawdown: number;
  sharpe_ratio: number | null;
  metrics?: ProbeMetrics | null;
  fitness_score: number;
  born_at: string;
  died_at: string | null;
  death_reason: string | null;
  mode: string;
  created_at: string;
  updated_at: string;
}

export interface Trade {
  execution?: TradeExecution | null;
  id: string;
  probe_id: string;
  side: "BUY" | "SELL";
  pair: string;
  entry_price: number;
  exit_price: number | null;
  amount: number;
  pnl: number | null;
  pnl_pct: number | null;
  signal_rsi: number | null;
  signal_ema_fast: number | null;
  signal_ema_slow: number | null;
  signal_volume_ratio: number | null;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  exit_reason: TradeExitReason | null;
  opened_at: string;
  closed_at: string | null;
  mode: string;
}

export interface FitnessSnapshot {
  id: string;
  probe_id: string;
  generation: number;
  tick: number;
  fitness_score: number;
  roi: number;
  sharpe_ratio: number | null;
  metrics?: ProbeMetrics | null;
  max_drawdown: number;
  win_rate: number;
  trade_count: number;
  current_capital: number;
  captured_at: string;
}

export interface GenerationStats {
  id: string;
  generation: number;
  total_probes: number;
  alive_probes: number;
  dead_probes: number;
  reproduced_count: number;
  best_fitness: number;
  avg_fitness: number;
  worst_fitness: number;
  total_capital: number;
  avg_capital: number;
  total_trades: number;
  avg_win_rate: number;
  best_roi: number;
  avg_roi: number;
  genome_diversity: number;
  started_at: string;
  ended_at: string | null;
}

export interface WsMessage {
  type: string;
  timestamp: string;
  colony_id?: string;
  data: Record<string, unknown>;
}

export interface ColonyRun {
  run_id: string;
  history_source?: "colony" | "probe_only";
  mode: string;
  strategy?: string;
  started_at: string;
  ended_at: string | null;
  probe_count: number;
  best_fitness: number;
  status?: Exclude<SimulationStatus, "unknown">;
  runtime?: Partial<Pick<SystemStatus, "failure_code" | "state_persisted" | "open_positions" | "requires_reconciliation" | "valuation_available" | "clock_basis" | "market_time" | "market_elapsed_secs" | "circuit_breaker" | "risk_control" | "evaluation_policy" | "cohort" | "search_spec" | "lifecycle_policy" | "execution_policy" | "signal_policy">>;
}

export interface PriceTick {
  asset: string;
  timestamp?: number;
  account_currency?: "USD";
  price: number;
  change?: number;
}

export interface SystemStatus {
  status: SimulationStatus;
  run_id: string;
  colony_id?: string;
  mode: string;
  strategy?: string;
  jup_api_calls: number;
  generation: number;
  tick: number;
  live_probes: number;
  dead_probes: number;
  total_probes: number;
  reserve_capital: number | null;
  active_capital: number | null;
  total_capital: number | null;
  valuation_available?: boolean;
  circuit_breaker: boolean;
  risk_control?: RiskControl;
  search_spec?: SearchSpec;
  lifecycle_policy?: LifecyclePolicy;
  execution_policy?: ExecutionPolicy;
  signal_policy?: SignalPolicy;
  evaluation_policy?: EvaluationPolicy;
  cohort?: EvaluationCohort;
  diversity: number | null;
  started_at: string | null;
  uptime_secs: number;
  clock_basis?: "synthetic_market" | "wall";
  market_time?: string | null;
  market_elapsed_secs?: number | null;
  failure_code?: string | null;
  failure_message?: string | null;
  state_persisted?: boolean;
  open_positions?: number;
  requires_reconciliation?: boolean;
}

export interface ColonyInfo {
  colony_id: string;
  strategy: string;
  mode: string;
  status: SimulationStatus;
  generation: number;
  tick: number;
  live_probes: number;
  dead_probes: number;
  total_capital: number | null;
  valuation_available?: boolean;
  diversity: number | null;
  started_at: string;
  uptime_secs: number;
  failure_code?: string | null;
  failure_message?: string | null;
  state_persisted?: boolean;
  open_positions?: number;
  requires_reconciliation?: boolean;
  circuit_breaker?: boolean;
  risk_control?: RiskControl;
  search_spec?: SearchSpec;
  lifecycle_policy?: LifecyclePolicy;
  execution_policy?: ExecutionPolicy;
  signal_policy?: SignalPolicy;
  evaluation_policy?: EvaluationPolicy;
  cohort?: EvaluationCohort;
}

export interface StrategyInfo {
  name: string;
  label: string;
  description: string;
}
