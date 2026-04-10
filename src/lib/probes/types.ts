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
  | "REPRODUCING";

export type SimulationStatus = "running" | "paused" | "stopped";

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
  death_drawdown_pct: number;
  num_assets: number;
  assets: string[];
  generation: number;
  parent_ids: string[];
}

export interface Probe {
  id: string;
  probe_name: string;
  generation: number;
  parent_id: string | null;
  state: ProbeState;
  genome: Genome;
  initial_capital: number;
  current_capital: number;
  peak_capital: number;
  total_trades: number;
  winning_trades: number;
  total_pnl: number;
  max_drawdown: number;
  sharpe_ratio: number;
  fitness_score: number;
  born_at: string;
  died_at: string | null;
  death_reason: string | null;
  mode: string;
  created_at: string;
  updated_at: string;
}

export interface Trade {
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
  sharpe_ratio: number;
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
  mode: string;
  strategy?: string;
  started_at: string;
  ended_at: string | null;
  probe_count: number;
  best_fitness: number;
}

export interface PriceTick {
  asset: string;
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
  reserve_capital: number;
  active_capital: number;
  total_capital: number;
  circuit_breaker: boolean;
  diversity: number;
  started_at: string | null;
  uptime_secs: number;
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
  total_capital: number;
  diversity: number;
  started_at: string;
  uptime_secs: number;
}

export interface StrategyInfo {
  name: string;
  label: string;
  description: string;
}
