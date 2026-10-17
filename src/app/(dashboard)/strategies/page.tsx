"use client";

import * as React from "react";
import { AlertCircle, ExternalLink, Play } from "lucide-react";
import { TradingViewChart, TradingViewAnalysis } from "@/components/strategies/TradingViewChart";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { defaultStrategies, supportedSymbols, timeframes, type StrategyConfig, type TimeFrame } from "@/lib/mock/strategies";

const chartIntervals: Record<TimeFrame, string> = { "1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D" };

function StrategyConcept({ strategy }: { strategy: StrategyConfig }) {
  return (
    <div className="rounded-lg border border-[#00fff5]/10 bg-card/50 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold" style={{ color: strategy.color }}>{strategy.name}</h3>
        <Badge variant="outline" className="text-[10px] border-muted-foreground/30">Example: {strategy.defaultTimeframe}</Badge>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{strategy.description}</p>
      <p className="mt-2 text-[10px] uppercase tracking-wider text-muted-foreground">Example parameters</p>
      <div className="mt-1 flex flex-wrap gap-2">
        {Object.entries(strategy.parameters).map(([key, value]) => (
          <span key={key} className="rounded bg-muted/50 px-1.5 py-0.5 text-[10px] text-muted-foreground">{key}: {value}</span>
        ))}
      </div>
    </div>
  );
}

export default function StrategiesPage() {
  const [symbol, setSymbol] = React.useState("BTCUSD");
  const [timeframe, setTimeframe] = React.useState<TimeFrame>("1h");
  const tvSymbol = `BINANCE:${symbol.replace("USD", "USDT")}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#00fff5]">Strategy Concepts</h1>
          <p className="mt-1 text-sm text-muted-foreground">Explore example strategy descriptions and independent external charts.</p>
        </div>
        <a href="https://www.tradingview.com/chart/" target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-[#00fff5]">
          <ExternalLink className="h-3 w-3" /> Open in TradingView
        </a>
      </div>

      <div className="rounded-lg border border-[#ffff00]/20 bg-[#ffff00]/5 p-4">
        <Badge variant="outline">Examples only</Badge>
        <p className="mt-2 text-sm text-muted-foreground">
          These predefined descriptions and parameter values are examples. No trades, returns or risk scores have been calculated here.
          The examples do not run a backtest or configure the trading bot.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_350px]">
        <div className="space-y-6">
          <Card className="overflow-hidden border-[#00fff5]/20 bg-card/80 backdrop-blur-sm">
            <CardHeader>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">External TradingView Chart</h2>
              <p className="text-xs text-muted-foreground">This independently provided chart is not input to a strategy evaluation on this page.</p>
            </CardHeader>
            <CardContent className="p-0">
              <TradingViewChart symbol={tvSymbol} interval={chartIntervals[timeframe]} height={450} theme="dark" />
            </CardContent>
          </Card>

          <Card className="border-[#ff00ff]/20 bg-card/80 backdrop-blur-sm">
            <CardHeader>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#ff00ff]">Historical Evaluation</h2>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-start gap-2">
                <AlertCircle className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden />
                <p id="backtest-unavailable" className="text-sm text-muted-foreground">
                  Historical strategy evaluation is not available yet. No historical dataset has been evaluated and no backtest results are available.
                </p>
              </div>
              <Button type="button" disabled aria-describedby="backtest-unavailable" className="bg-gradient-to-r from-[#00fff5] to-[#ff00ff] text-black">
                <Play className="mr-2 h-4 w-4" /> Run backtest unavailable
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="border-[#bf00ff]/20 bg-card/80 backdrop-blur-sm">
            <CardHeader>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#bf00ff]">External Chart Settings</h2>
              <p className="text-xs text-muted-foreground">These controls change the external chart only.</p>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="strategy-chart-symbol" className="text-xs uppercase tracking-wider text-muted-foreground">Chart symbol</Label>
                <Select value={symbol} onValueChange={(value) => { if (supportedSymbols.some((item) => item.value === value)) setSymbol(value); }}>
                  <SelectTrigger id="strategy-chart-symbol" className="border-[#bf00ff]/20 bg-[#bf00ff]/5"><SelectValue /></SelectTrigger>
                  <SelectContent>{supportedSymbols.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="strategy-chart-timeframe" className="text-xs uppercase tracking-wider text-muted-foreground">Chart timeframe</Label>
                <Select value={timeframe} onValueChange={(value) => { if (timeframes.some((item) => item.value === value)) setTimeframe(value as TimeFrame); }}>
                  <SelectTrigger id="strategy-chart-timeframe" className="border-[#bf00ff]/20 bg-[#bf00ff]/5"><SelectValue /></SelectTrigger>
                  <SelectContent>{timeframes.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          <Card className="border-[#39ff14]/20 bg-card/80 backdrop-blur-sm">
            <CardHeader>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#39ff14]">Example Strategy Concepts</h2>
              <p className="text-xs text-muted-foreground">Reference descriptions only; these concepts have not been evaluated.</p>
            </CardHeader>
            <CardContent className="space-y-3">
              {defaultStrategies.map((strategy) => <StrategyConcept key={strategy.id} strategy={strategy} />)}
            </CardContent>
          </Card>

          <Card className="border-[#ffff00]/20 bg-card/80 backdrop-blur-sm">
            <CardHeader>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#ffff00]">External One-Hour Analysis</h2>
              <p className="text-xs text-muted-foreground">TradingView&apos;s independent one-hour summary for the selected symbol; no local strategy score is produced.</p>
            </CardHeader>
            <CardContent className="p-0"><TradingViewAnalysis symbol={tvSymbol} interval="1h" /></CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
