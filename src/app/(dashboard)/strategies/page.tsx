"use client";

import * as React from "react";
import { 
  Play, 
  Pause, 
  RotateCcw, 
  TrendingUp, 
  TrendingDown, 
  Clock,
  Target,
  Zap,
  BarChart2,
  Calendar,
  ChevronDown,
  ChevronUp,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ExternalLink,
} from "lucide-react";
import { toast } from "sonner";

import { TradingViewChart, TradingViewAnalysis } from "@/components/strategies/TradingViewChart";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  defaultStrategies,
  getDefaultBacktestResults,
  runBacktest,
  supportedSymbols,
  timeframes,
  type StrategyConfig,
  type StrategyResult,
  type TimeFrame,
} from "@/lib/mock/strategies";
import { formatDateTime } from "@/lib/formatters";

function StrategyCard({ 
  strategy, 
  isSelected, 
  onToggle,
  isRunning,
}: { 
  strategy: StrategyConfig; 
  isSelected: boolean;
  onToggle: () => void;
  isRunning: boolean;
}) {
  return (
    <div 
      className={`
        relative rounded-lg border p-4 cursor-pointer transition-all duration-300
        ${isSelected 
          ? `border-[${strategy.color}]/50 bg-[${strategy.color}]/10 shadow-[0_0_20px_${strategy.color}20]` 
          : 'border-[#00fff5]/10 bg-card/50 hover:border-[#00fff5]/30'
        }
        ${isRunning ? 'opacity-50 pointer-events-none' : ''}
      `}
      onClick={onToggle}
      style={{
        borderColor: isSelected ? `${strategy.color}50` : undefined,
        backgroundColor: isSelected ? `${strategy.color}10` : undefined,
      }}
    >
      <div className="flex items-start gap-3">
        <Checkbox 
          checked={isSelected} 
          className="mt-1 data-[state=checked]:bg-[#00fff5] data-[state=checked]:border-[#00fff5]"
        />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold" style={{ color: strategy.color }}>
              {strategy.name}
            </h3>
            <Badge variant="outline" className="text-[10px] border-muted-foreground/30">
              {strategy.defaultTimeframe}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
            {strategy.description}
          </p>
          <div className="flex flex-wrap gap-2 mt-2">
            {Object.entries(strategy.parameters).slice(0, 3).map(([key, value]) => (
              <span 
                key={key} 
                className="text-[10px] px-1.5 py-0.5 rounded bg-muted/50 text-muted-foreground"
              >
                {key}: {value}
              </span>
            ))}
          </div>
        </div>
      </div>
      
      {/* Selection indicator */}
      {isSelected && (
        <div 
          className="absolute top-0 right-0 w-0 h-0 border-t-[20px] border-r-[20px] border-t-transparent"
          style={{ borderRightColor: strategy.color }}
        />
      )}
    </div>
  );
}

function ResultsTable({ 
  results, 
  onViewDetails 
}: { 
  results: StrategyResult[];
  onViewDetails: (result: StrategyResult) => void;
}) {
  const [sortKey, setSortKey] = React.useState<keyof StrategyResult>("totalPnlPercent");
  const [sortDir, setSortDir] = React.useState<"asc" | "desc">("desc");
  
  const sorted = [...results].sort((a, b) => {
    const aVal = a[sortKey];
    const bVal = b[sortKey];
    if (typeof aVal === "number" && typeof bVal === "number") {
      return sortDir === "desc" ? bVal - aVal : aVal - bVal;
    }
    return 0;
  });
  
  const handleSort = (key: keyof StrategyResult) => {
    if (key === sortKey) {
      setSortDir(prev => prev === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };
  
  const SortIcon = ({ field }: { field: keyof StrategyResult }) => {
    if (field !== sortKey) return null;
    return sortDir === "desc" ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />;
  };
  
  return (
    <div className="rounded-lg border border-[#00fff5]/10 overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="border-b border-[#00fff5]/10 hover:bg-transparent">
            <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Strategy</TableHead>
            <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
              <Button variant="ghost" size="sm" className="px-0 h-auto" onClick={() => handleSort("totalTrades")}>
                Trades <SortIcon field="totalTrades" />
              </Button>
            </TableHead>
            <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
              <Button variant="ghost" size="sm" className="px-0 h-auto" onClick={() => handleSort("winRate")}>
                Win Rate <SortIcon field="winRate" />
              </Button>
            </TableHead>
            <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
              <Button variant="ghost" size="sm" className="px-0 h-auto" onClick={() => handleSort("totalPnlPercent")}>
                P&L % <SortIcon field="totalPnlPercent" />
              </Button>
            </TableHead>
            <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
              <Button variant="ghost" size="sm" className="px-0 h-auto" onClick={() => handleSort("profitFactor")}>
                Profit Factor <SortIcon field="profitFactor" />
              </Button>
            </TableHead>
            <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
              <Button variant="ghost" size="sm" className="px-0 h-auto" onClick={() => handleSort("maxDrawdown")}>
                Max DD <SortIcon field="maxDrawdown" />
              </Button>
            </TableHead>
            <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
              <Button variant="ghost" size="sm" className="px-0 h-auto" onClick={() => handleSort("sharpeRatio")}>
                Sharpe <SortIcon field="sharpeRatio" />
              </Button>
            </TableHead>
            <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((result) => {
            const config = defaultStrategies.find(s => s.name === result.name);
            const color = config?.color || "#00fff5";
            
            return (
              <TableRow 
                key={result.id}
                className="border-b border-[#00fff5]/5 hover:bg-[#00fff5]/5 cursor-pointer transition-colors"
                onClick={() => onViewDetails(result)}
              >
                <TableCell>
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                    <span className="font-medium">{result.name}</span>
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">
                    {result.symbol} • {result.timeframe}
                  </div>
                </TableCell>
                <TableCell className="font-mono">{result.totalTrades}</TableCell>
                <TableCell>
                  <span className={result.winRate >= 50 ? "text-[#39ff14]" : "text-[#ff3366]"}>
                    {result.winRate}%
                  </span>
                </TableCell>
                <TableCell>
                  <span className={`font-mono font-bold ${result.totalPnlPercent >= 0 ? "text-[#39ff14]" : "text-[#ff3366]"}`}>
                    {result.totalPnlPercent >= 0 ? "+" : ""}{result.totalPnlPercent}%
                  </span>
                </TableCell>
                <TableCell className="font-mono">
                  <span className={result.profitFactor >= 1.5 ? "text-[#39ff14]" : result.profitFactor >= 1 ? "text-[#ffff00]" : "text-[#ff3366]"}>
                    {result.profitFactor === Infinity ? "∞" : result.profitFactor.toFixed(2)}
                  </span>
                </TableCell>
                <TableCell className="font-mono text-[#ff3366]">
                  -{result.maxDrawdown}%
                </TableCell>
                <TableCell className="font-mono">
                  <span className={result.sharpeRatio >= 2 ? "text-[#39ff14]" : result.sharpeRatio >= 1 ? "text-[#ffff00]" : "text-muted-foreground"}>
                    {result.sharpeRatio.toFixed(2)}
                  </span>
                </TableCell>
                <TableCell>
                  {result.status === "completed" && (
                    <Badge className="bg-[#39ff14]/10 text-[#39ff14] border-[#39ff14]/30">
                      <CheckCircle2 className="h-3 w-3 mr-1" />
                      Complete
                    </Badge>
                  )}
                  {result.status === "running" && (
                    <Badge className="bg-[#00fff5]/10 text-[#00fff5] border-[#00fff5]/30 animate-pulse">
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      Running
                    </Badge>
                  )}
                  {result.status === "failed" && (
                    <Badge className="bg-[#ff3366]/10 text-[#ff3366] border-[#ff3366]/30">
                      <XCircle className="h-3 w-3 mr-1" />
                      Failed
                    </Badge>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

function StrategyDetailDialog({ 
  result, 
  isOpen, 
  onClose 
}: { 
  result: StrategyResult | null;
  isOpen: boolean;
  onClose: () => void;
}) {
  if (!result) return null;
  
  const config = defaultStrategies.find(s => s.name === result.name);
  const color = config?.color || "#00fff5";
  
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl border-[#00fff5]/20 bg-card/95 backdrop-blur-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <div className="h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
            <span style={{ color }}>{result.name}</span>
            <span className="text-muted-foreground font-normal text-sm">
              {result.symbol} • {result.timeframe}
            </span>
          </DialogTitle>
        </DialogHeader>
        
        <Tabs defaultValue="overview" className="mt-4">
          <TabsList className="bg-muted/50">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="trades">Trades ({result.totalTrades})</TabsTrigger>
            <TabsTrigger value="metrics">Metrics</TabsTrigger>
          </TabsList>
          
          <TabsContent value="overview" className="mt-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="rounded-lg border border-[#00fff5]/20 bg-[#00fff5]/5 p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Total P&L</p>
                <p className={`text-2xl font-bold font-mono ${result.totalPnlPercent >= 0 ? "text-[#39ff14]" : "text-[#ff3366]"}`}>
                  {result.totalPnlPercent >= 0 ? "+" : ""}{result.totalPnlPercent}%
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  ${result.totalPnl.toLocaleString()}
                </p>
              </div>
              <div className="rounded-lg border border-[#39ff14]/20 bg-[#39ff14]/5 p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Win Rate</p>
                <p className="text-2xl font-bold font-mono text-[#39ff14]">{result.winRate}%</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {result.winningTrades}W / {result.losingTrades}L
                </p>
              </div>
              <div className="rounded-lg border border-[#ff3366]/20 bg-[#ff3366]/5 p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Max Drawdown</p>
                <p className="text-2xl font-bold font-mono text-[#ff3366]">-{result.maxDrawdown}%</p>
              </div>
              <div className="rounded-lg border border-[#bf00ff]/20 bg-[#bf00ff]/5 p-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider">Sharpe Ratio</p>
                <p className="text-2xl font-bold font-mono text-[#bf00ff]">{result.sharpeRatio.toFixed(2)}</p>
              </div>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
              <div className="text-center p-3 rounded-lg bg-muted/30">
                <p className="text-xs text-muted-foreground">Profit Factor</p>
                <p className="text-lg font-mono font-bold">{result.profitFactor === Infinity ? "∞" : result.profitFactor.toFixed(2)}</p>
              </div>
              <div className="text-center p-3 rounded-lg bg-muted/30">
                <p className="text-xs text-muted-foreground">Avg Win</p>
                <p className="text-lg font-mono font-bold text-[#39ff14]">+${result.avgWin}</p>
              </div>
              <div className="text-center p-3 rounded-lg bg-muted/30">
                <p className="text-xs text-muted-foreground">Avg Loss</p>
                <p className="text-lg font-mono font-bold text-[#ff3366]">-${result.avgLoss}</p>
              </div>
              <div className="text-center p-3 rounded-lg bg-muted/30">
                <p className="text-xs text-muted-foreground">Run Time</p>
                <p className="text-lg font-mono font-bold">{result.runTime.toFixed(1)}s</p>
              </div>
            </div>
          </TabsContent>
          
          <TabsContent value="trades" className="mt-4">
            <div className="max-h-[400px] overflow-auto rounded-lg border border-[#00fff5]/10">
              <Table>
                <TableHeader>
                  <TableRow className="border-b border-[#00fff5]/10">
                    <TableHead className="text-xs">Entry</TableHead>
                    <TableHead className="text-xs">Exit</TableHead>
                    <TableHead className="text-xs">Side</TableHead>
                    <TableHead className="text-xs">Entry Price</TableHead>
                    <TableHead className="text-xs">Exit Price</TableHead>
                    <TableHead className="text-xs">P&L</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.trades.slice(0, 50).map((trade) => (
                    <TableRow key={trade.id} className="border-b border-[#00fff5]/5">
                      <TableCell className="text-xs font-mono text-muted-foreground">
                        {new Date(trade.entryTime).toLocaleDateString()}
                      </TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">
                        {new Date(trade.exitTime).toLocaleDateString()}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={trade.side === "long" ? "text-[#39ff14] border-[#39ff14]/30" : "text-[#ff3366] border-[#ff3366]/30"}>
                          {trade.side === "long" ? <TrendingUp className="h-3 w-3 mr-1" /> : <TrendingDown className="h-3 w-3 mr-1" />}
                          {trade.side}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-sm">${trade.entryPrice.toLocaleString()}</TableCell>
                      <TableCell className="font-mono text-sm">${trade.exitPrice.toLocaleString()}</TableCell>
                      <TableCell className={`font-mono font-bold ${trade.pnl >= 0 ? "text-[#39ff14]" : "text-[#ff3366]"}`}>
                        {trade.pnl >= 0 ? "+" : ""}{trade.pnlPercent}%
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </TabsContent>
          
          <TabsContent value="metrics" className="mt-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-3">
                <h4 className="text-sm font-semibold text-[#00fff5]">Performance</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Total Trades</span>
                    <span className="font-mono">{result.totalTrades}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Winning Trades</span>
                    <span className="font-mono text-[#39ff14]">{result.winningTrades}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Losing Trades</span>
                    <span className="font-mono text-[#ff3366]">{result.losingTrades}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Win Rate</span>
                    <span className="font-mono">{result.winRate}%</span>
                  </div>
                </div>
              </div>
              <div className="space-y-3">
                <h4 className="text-sm font-semibold text-[#ff00ff]">Risk Metrics</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Max Drawdown</span>
                    <span className="font-mono text-[#ff3366]">-{result.maxDrawdown}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Sharpe Ratio</span>
                    <span className="font-mono">{result.sharpeRatio.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Profit Factor</span>
                    <span className="font-mono">{result.profitFactor === Infinity ? "∞" : result.profitFactor.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Largest Win</span>
                    <span className="font-mono text-[#39ff14]">+${result.largestWin}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Largest Loss</span>
                    <span className="font-mono text-[#ff3366]">-${result.largestLoss}</span>
                  </div>
                </div>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

export default function StrategiesPage() {
  // State
  const [selectedStrategies, setSelectedStrategies] = React.useState<string[]>(
    defaultStrategies.map(s => s.id)
  );
  const [symbol, setSymbol] = React.useState("BTCUSD");
  const [timeframe, setTimeframe] = React.useState<TimeFrame>("1h");
  const [startDate, setStartDate] = React.useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 90);
    return date.toISOString().slice(0, 16);
  });
  const [endDate, setEndDate] = React.useState(() => {
    return new Date().toISOString().slice(0, 16);
  });
  const [isRunning, setIsRunning] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [results, setResults] = React.useState<StrategyResult[]>(() => getDefaultBacktestResults());
  const [selectedResult, setSelectedResult] = React.useState<StrategyResult | null>(null);
  
  const toggleStrategy = (id: string) => {
    setSelectedStrategies(prev => 
      prev.includes(id) 
        ? prev.filter(s => s !== id)
        : [...prev, id]
    );
  };
  
  const runBacktests = async () => {
    if (selectedStrategies.length === 0) {
      toast.error("Select at least one strategy");
      return;
    }
    
    setIsRunning(true);
    setProgress(0);
    
    const newResults: StrategyResult[] = [];
    const strategies = defaultStrategies.filter(s => selectedStrategies.includes(s.id));
    
    for (let i = 0; i < strategies.length; i++) {
      const strategy = strategies[i];
      
      toast.info(`Running ${strategy.name}...`, { duration: 2000 });
      
      try {
        const result = await runBacktest(
          strategy,
          symbol,
          timeframe,
          new Date(startDate),
          new Date(endDate),
          (p) => setProgress(((i / strategies.length) + (p / 100 / strategies.length)) * 100)
        );
        
        newResults.push(result);
        
        if (result.totalPnlPercent > 0) {
          toast.success(`${strategy.name}: +${result.totalPnlPercent}% P&L`);
        } else {
          toast.warning(`${strategy.name}: ${result.totalPnlPercent}% P&L`);
        }
      } catch (error) {
        toast.error(`${strategy.name} failed`);
      }
    }
    
    setResults(newResults);
    setIsRunning(false);
    setProgress(100);
    
    toast.success("Backtest complete!", {
      description: `Tested ${strategies.length} strategies`,
    });
  };
  
  const resetResults = () => {
    setResults(getDefaultBacktestResults());
    toast.info("Results reset to defaults");
  };
  
  // Convert symbol for TradingView
  const tvSymbol = `BINANCE:${symbol.replace("USD", "USDT")}`;
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">
            <span className="glitch neon-text-cyan" data-text="Strategy Backtester">
              Strategy Backtester
            </span>
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Test trading strategies with historical data powered by TradingView
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a 
            href="https://www.tradingview.com/chart/" 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-xs text-muted-foreground hover:text-[#00fff5] flex items-center gap-1 transition-colors"
          >
            <ExternalLink className="h-3 w-3" />
            Open in TradingView
          </a>
        </div>
      </div>
      
      <div className="grid gap-6 lg:grid-cols-[1fr_350px]">
        {/* Main Content */}
        <div className="space-y-6">
          {/* TradingView Chart */}
          <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#00fff5] to-transparent" />
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">
                  Live Chart
                </h2>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px] border-[#39ff14]/30 text-[#39ff14]">
                    <div className="h-1.5 w-1.5 rounded-full bg-[#39ff14] mr-1 animate-pulse" />
                    Live
                  </Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <TradingViewChart 
                symbol={tvSymbol}
                interval={timeframe === "1m" ? "1" : timeframe === "5m" ? "5" : timeframe === "15m" ? "15" : timeframe === "1h" ? "60" : timeframe === "4h" ? "240" : "D"}
                height={450}
                theme="dark"
              />
            </CardContent>
          </Card>
          
          {/* Results Table */}
          <Card className="border-[#ff00ff]/20 bg-card/80 backdrop-blur-sm">
            <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#ff00ff] to-transparent" />
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold uppercase tracking-wider text-[#ff00ff]">
                    Backtest Results
                  </h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    Click a row to view detailed metrics
                  </p>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <BarChart2 className="h-4 w-4" />
                  {results.length} strategies tested
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {results.length > 0 ? (
                <ResultsTable 
                  results={results} 
                  onViewDetails={setSelectedResult}
                />
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <AlertCircle className="h-12 w-12 text-muted-foreground/50 mb-4" />
                  <p className="text-muted-foreground">No results yet</p>
                  <p className="text-xs text-muted-foreground/50 mt-1">
                    Select strategies and run a backtest
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
        
        {/* Sidebar - Configuration */}
        <div className="space-y-4">
          {/* Backtest Settings */}
          <Card className="border-[#bf00ff]/20 bg-card/80 backdrop-blur-sm">
            <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#bf00ff] to-transparent" />
            <CardHeader>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#bf00ff]">
                Backtest Settings
              </h2>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Symbol */}
              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                  Symbol
                </Label>
                <Select value={symbol} onValueChange={setSymbol} disabled={isRunning}>
                  <SelectTrigger className="border-[#bf00ff]/20 bg-[#bf00ff]/5">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {supportedSymbols.map(s => (
                      <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              {/* Timeframe */}
              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                  Timeframe
                </Label>
                <Select value={timeframe} onValueChange={(v) => setTimeframe(v as TimeFrame)} disabled={isRunning}>
                  <SelectTrigger className="border-[#bf00ff]/20 bg-[#bf00ff]/5">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {timeframes.map(t => (
                      <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              {/* Date Range */}
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                    Start Date
                  </Label>
                  <Input 
                    type="datetime-local" 
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    disabled={isRunning}
                    className="border-[#bf00ff]/20 bg-[#bf00ff]/5 text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                    End Date
                  </Label>
                  <Input 
                    type="datetime-local"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    disabled={isRunning}
                    className="border-[#bf00ff]/20 bg-[#bf00ff]/5 text-xs"
                  />
                </div>
              </div>
              
              {/* Progress */}
              {isRunning && (
                <div className="space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Progress</span>
                    <span className="text-[#00fff5]">{Math.round(progress)}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-muted/30 overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-[#00fff5] to-[#ff00ff] transition-all duration-300"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              )}
              
              {/* Action Buttons */}
              <div className="flex gap-2">
                <Button 
                  className="flex-1 bg-gradient-to-r from-[#00fff5] to-[#ff00ff] text-black hover:opacity-90"
                  onClick={runBacktests}
                  disabled={isRunning || selectedStrategies.length === 0}
                >
                  {isRunning ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Running...
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4 mr-2" />
                      Run Backtest
                    </>
                  )}
                </Button>
                <Button 
                  variant="outline"
                  size="icon"
                  onClick={resetResults}
                  disabled={isRunning}
                  className="border-[#bf00ff]/20 hover:bg-[#bf00ff]/10"
                >
                  <RotateCcw className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
          
          {/* Strategy Selection */}
          <Card className="border-[#39ff14]/20 bg-card/80 backdrop-blur-sm">
            <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#39ff14] to-transparent" />
            <CardHeader>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wider text-[#39ff14]">
                  Strategies
                </h2>
                <Badge variant="outline" className="text-[10px] border-muted-foreground/30">
                  {selectedStrategies.length}/{defaultStrategies.length} selected
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 max-h-[500px] overflow-auto">
              {defaultStrategies.map((strategy) => (
                <StrategyCard
                  key={strategy.id}
                  strategy={strategy}
                  isSelected={selectedStrategies.includes(strategy.id)}
                  onToggle={() => toggleStrategy(strategy.id)}
                  isRunning={isRunning}
                />
              ))}
            </CardContent>
          </Card>
          
          {/* Technical Analysis */}
          <Card className="border-[#ffff00]/20 bg-card/80 backdrop-blur-sm">
            <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#ffff00] to-transparent" />
            <CardHeader>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#ffff00]">
                Technical Analysis
              </h2>
            </CardHeader>
            <CardContent className="p-0">
              <TradingViewAnalysis symbol={tvSymbol} interval="1h" />
            </CardContent>
          </Card>
        </div>
      </div>
      
      {/* Detail Dialog */}
      <StrategyDetailDialog 
        result={selectedResult}
        isOpen={!!selectedResult}
        onClose={() => setSelectedResult(null)}
      />
    </div>
  );
}
