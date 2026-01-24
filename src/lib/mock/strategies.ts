export type StrategyType = 
  | "RSI Divergence"
  | "MACD Crossover"
  | "Bollinger Breakout"
  | "Moving Average Cross"
  | "Volume Spike";

export type TimeFrame = "1m" | "5m" | "15m" | "1h" | "4h" | "1d";

export type BacktestStatus = "pending" | "running" | "completed" | "failed";

export type Trade = {
  id: string;
  entryTime: string;
  exitTime: string;
  entryPrice: number;
  exitPrice: number;
  side: "long" | "short";
  pnl: number;
  pnlPercent: number;
};

export type StrategyResult = {
  id: string;
  name: StrategyType;
  symbol: string;
  timeframe: TimeFrame;
  startDate: string;
  endDate: string;
  status: BacktestStatus;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  winRate: number;
  totalPnl: number;
  totalPnlPercent: number;
  maxDrawdown: number;
  sharpeRatio: number;
  profitFactor: number;
  avgWin: number;
  avgLoss: number;
  largestWin: number;
  largestLoss: number;
  trades: Trade[];
  runTime: number; // in seconds
};

export type StrategyConfig = {
  id: string;
  name: StrategyType;
  description: string;
  parameters: Record<string, number | string>;
  defaultTimeframe: TimeFrame;
  color: string;
};

// Default strategy configurations
export const defaultStrategies: StrategyConfig[] = [
  {
    id: "rsi-divergence",
    name: "RSI Divergence",
    description: "Identifies bullish and bearish divergences between price and RSI indicator to predict reversals.",
    parameters: {
      rsiPeriod: 14,
      overbought: 70,
      oversold: 30,
      divergenceLookback: 10,
    },
    defaultTimeframe: "4h",
    color: "#00fff5",
  },
  {
    id: "macd-crossover",
    name: "MACD Crossover",
    description: "Generates signals when MACD line crosses the signal line, indicating momentum shifts.",
    parameters: {
      fastPeriod: 12,
      slowPeriod: 26,
      signalPeriod: 9,
    },
    defaultTimeframe: "1h",
    color: "#ff00ff",
  },
  {
    id: "bollinger-breakout",
    name: "Bollinger Breakout",
    description: "Trades breakouts when price moves outside Bollinger Bands with volume confirmation.",
    parameters: {
      period: 20,
      standardDeviations: 2,
      volumeMultiplier: 1.5,
    },
    defaultTimeframe: "1h",
    color: "#39ff14",
  },
  {
    id: "ma-cross",
    name: "Moving Average Cross",
    description: "Classic strategy using fast and slow moving average crossovers for trend following.",
    parameters: {
      fastMA: 9,
      slowMA: 21,
      maType: "EMA",
    },
    defaultTimeframe: "4h",
    color: "#ffff00",
  },
  {
    id: "volume-spike",
    name: "Volume Spike",
    description: "Detects unusual volume spikes and trades in the direction of the price movement.",
    parameters: {
      volumeThreshold: 2.5,
      priceConfirmation: 0.5,
      lookbackPeriod: 20,
    },
    defaultTimeframe: "15m",
    color: "#bf00ff",
  },
];

// Seeded random for consistent results
function seededRandom(seed: number) {
  let value = seed;
  return () => {
    value = (value * 16807) % 2147483647;
    return (value - 1) / 2147483646;
  };
}

// Generate mock trades for a strategy
function generateMockTrades(
  startDate: Date,
  endDate: Date,
  seed: number
): Trade[] {
  const random = seededRandom(seed);
  const trades: Trade[] = [];
  const daysDiff = Math.ceil((endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24));
  const numTrades = Math.max(10, Math.min(150, Math.floor(daysDiff * 0.8 + random() * daysDiff * 0.4)));
  
  let currentDate = new Date(startDate);
  const avgTradeLength = daysDiff / numTrades;
  
  for (let i = 0; i < numTrades; i++) {
    const entryTime = new Date(currentDate);
    const tradeDuration = avgTradeLength * 0.5 + random() * avgTradeLength;
    const exitTime = new Date(currentDate.getTime() + tradeDuration * 24 * 60 * 60 * 1000);
    
    if (exitTime > endDate) break;
    
    const side = random() > 0.45 ? "long" : "short";
    const entryPrice = 90000 + random() * 10000;
    const priceChange = (random() - 0.45) * 0.08; // Slight positive bias
    const exitPrice = side === "long" 
      ? entryPrice * (1 + priceChange)
      : entryPrice * (1 - priceChange);
    
    const pnl = side === "long"
      ? exitPrice - entryPrice
      : entryPrice - exitPrice;
    const pnlPercent = (pnl / entryPrice) * 100;
    
    trades.push({
      id: `trade-${i + 1}`,
      entryTime: entryTime.toISOString(),
      exitTime: exitTime.toISOString(),
      entryPrice: Math.round(entryPrice * 100) / 100,
      exitPrice: Math.round(exitPrice * 100) / 100,
      side,
      pnl: Math.round(pnl * 100) / 100,
      pnlPercent: Math.round(pnlPercent * 100) / 100,
    });
    
    currentDate = new Date(exitTime.getTime() + random() * avgTradeLength * 12 * 60 * 60 * 1000);
  }
  
  return trades;
}

// Calculate strategy metrics from trades
function calculateMetrics(trades: Trade[]): Partial<StrategyResult> {
  if (trades.length === 0) {
    return {
      totalTrades: 0,
      winningTrades: 0,
      losingTrades: 0,
      winRate: 0,
      totalPnl: 0,
      totalPnlPercent: 0,
      maxDrawdown: 0,
      sharpeRatio: 0,
      profitFactor: 0,
      avgWin: 0,
      avgLoss: 0,
      largestWin: 0,
      largestLoss: 0,
    };
  }
  
  const winningTrades = trades.filter(t => t.pnl > 0);
  const losingTrades = trades.filter(t => t.pnl <= 0);
  
  const totalPnl = trades.reduce((sum, t) => sum + t.pnl, 0);
  const totalPnlPercent = trades.reduce((sum, t) => sum + t.pnlPercent, 0);
  
  const grossProfit = winningTrades.reduce((sum, t) => sum + t.pnl, 0);
  const grossLoss = Math.abs(losingTrades.reduce((sum, t) => sum + t.pnl, 0));
  
  // Calculate max drawdown
  let peak = 0;
  let maxDrawdown = 0;
  let equity = 0;
  for (const trade of trades) {
    equity += trade.pnl;
    if (equity > peak) peak = equity;
    const drawdown = ((peak - equity) / peak) * 100;
    if (drawdown > maxDrawdown) maxDrawdown = drawdown;
  }
  
  // Calculate Sharpe Ratio (simplified)
  const returns = trades.map(t => t.pnlPercent);
  const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
  const stdDev = Math.sqrt(
    returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length
  );
  const sharpeRatio = stdDev > 0 ? (avgReturn / stdDev) * Math.sqrt(365) : 0;
  
  return {
    totalTrades: trades.length,
    winningTrades: winningTrades.length,
    losingTrades: losingTrades.length,
    winRate: Math.round((winningTrades.length / trades.length) * 100 * 10) / 10,
    totalPnl: Math.round(totalPnl * 100) / 100,
    totalPnlPercent: Math.round(totalPnlPercent * 100) / 100,
    maxDrawdown: Math.round(maxDrawdown * 100) / 100,
    sharpeRatio: Math.round(sharpeRatio * 100) / 100,
    profitFactor: grossLoss > 0 ? Math.round((grossProfit / grossLoss) * 100) / 100 : grossProfit > 0 ? Infinity : 0,
    avgWin: winningTrades.length > 0 
      ? Math.round((grossProfit / winningTrades.length) * 100) / 100 
      : 0,
    avgLoss: losingTrades.length > 0 
      ? Math.round((grossLoss / losingTrades.length) * 100) / 100 
      : 0,
    largestWin: winningTrades.length > 0 
      ? Math.round(Math.max(...winningTrades.map(t => t.pnl)) * 100) / 100 
      : 0,
    largestLoss: losingTrades.length > 0 
      ? Math.round(Math.max(...losingTrades.map(t => Math.abs(t.pnl))) * 100) / 100 
      : 0,
  };
}

// Simulate running a backtest
export async function runBacktest(
  strategy: StrategyConfig,
  symbol: string,
  timeframe: TimeFrame,
  startDate: Date,
  endDate: Date,
  onProgress?: (progress: number) => void
): Promise<StrategyResult> {
  // Simulate backtest running time
  const totalSteps = 10;
  const stepDelay = 200 + Math.random() * 300;
  
  for (let i = 1; i <= totalSteps; i++) {
    await new Promise(resolve => setTimeout(resolve, stepDelay));
    onProgress?.(i * 10);
  }
  
  // Generate seed from strategy ID and dates for consistent results
  const seed = strategy.id.split('').reduce((a, c) => a + c.charCodeAt(0), 0) + 
    startDate.getTime() % 10000;
  
  const trades = generateMockTrades(startDate, endDate, seed);
  const metrics = calculateMetrics(trades);
  
  return {
    id: `result-${Date.now()}-${strategy.id}`,
    name: strategy.name,
    symbol,
    timeframe,
    startDate: startDate.toISOString(),
    endDate: endDate.toISOString(),
    status: "completed",
    trades,
    runTime: Math.round((totalSteps * stepDelay) / 1000 * 10) / 10,
    ...metrics,
  } as StrategyResult;
}

// Get pre-generated results for display
export function getDefaultBacktestResults(): StrategyResult[] {
  const endDate = new Date();
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - 90);
  
  return defaultStrategies.map((strategy, index) => {
    const seed = strategy.id.split('').reduce((a, c) => a + c.charCodeAt(0), 0) + 12345;
    const trades = generateMockTrades(startDate, endDate, seed + index * 1000);
    const metrics = calculateMetrics(trades);
    
    return {
      id: `default-${strategy.id}`,
      name: strategy.name,
      symbol: "BTCUSD",
      timeframe: strategy.defaultTimeframe,
      startDate: startDate.toISOString(),
      endDate: endDate.toISOString(),
      status: "completed" as BacktestStatus,
      trades,
      runTime: 2.5 + Math.random() * 2,
      ...metrics,
    } as StrategyResult;
  });
}

export const supportedSymbols = [
  { value: "BTCUSD", label: "BTC/USD" },
  { value: "ETHUSD", label: "ETH/USD" },
  { value: "SOLUSD", label: "SOL/USD" },
  { value: "BNBUSD", label: "BNB/USD" },
  { value: "XRPUSD", label: "XRP/USD" },
  { value: "ADAUSD", label: "ADA/USD" },
  { value: "AVAXUSD", label: "AVAX/USD" },
  { value: "LINKUSD", label: "LINK/USD" },
];

export const timeframes: { value: TimeFrame; label: string }[] = [
  { value: "1m", label: "1 Minute" },
  { value: "5m", label: "5 Minutes" },
  { value: "15m", label: "15 Minutes" },
  { value: "1h", label: "1 Hour" },
  { value: "4h", label: "4 Hours" },
  { value: "1d", label: "1 Day" },
];
