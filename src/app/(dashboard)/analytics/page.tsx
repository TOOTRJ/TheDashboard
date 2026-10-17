"use client";

import { Download, BarChart2 } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useDashboardFilters } from "@/components/layout/DashboardProvider";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatShortDate } from "@/lib/formatters";
import {
  getPortfolioSeries,
  getPnlSeries,
  getWinRateSeries,
  getVolumeByExchange,
} from "@/lib/mock";

const NEON_COLORS = {
  cyan: "#00fff5",
  pink: "#ff00ff",
  purple: "#bf00ff",
  green: "#39ff14",
  yellow: "#ffff00",
};

export default function AnalyticsPage() {
  const { dateRange } = useDashboardFilters();

  const portfolioData = getPortfolioSeries(dateRange);
  const pnlData = getPnlSeries(dateRange);
  const winRateData = getWinRateSeries(dateRange);
  const volumeData = getVolumeByExchange();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold uppercase tracking-wider text-[#00fff5] neon-text-cyan">
            Sample Analytics
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            Local sample charts and fixed example metrics. No account or trading bot performance is loaded.
          </p>
        </div>
        <div className="space-y-1">
          <Button
            type="button"
            variant="outline"
            disabled
            aria-describedby="analytics-export-unavailable"
            className="border-[#00fff5]/20"
          >
            <Download className="mr-2 h-4 w-4" />
            Export CSV unavailable
          </Button>
          <p id="analytics-export-unavailable" className="max-w-xs text-xs text-muted-foreground">
            These sample charts are not connected to an account export.
          </p>
        </div>
      </div>

      <Tabs defaultValue="performance" className="space-y-4">
        <TabsList className="bg-card/50 border border-[#00fff5]/20">
          <TabsTrigger 
            value="performance"
            className="data-[state=active]:bg-[#00fff5]/10 data-[state=active]:text-[#00fff5]"
          >
            Performance
          </TabsTrigger>
          <TabsTrigger 
            value="markets"
            className="data-[state=active]:bg-[#00fff5]/10 data-[state=active]:text-[#00fff5]"
          >
            Markets
          </TabsTrigger>
          <TabsTrigger 
            value="strategy"
            className="data-[state=active]:bg-[#00fff5]/10 data-[state=active]:text-[#00fff5]"
          >
            Strategy
          </TabsTrigger>
        </TabsList>

        <TabsContent value="performance">
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2 border-[#00fff5]/20 bg-card/80 backdrop-blur-sm">
              <CardHeader>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">
                  Sample Portfolio Growth
                </h3>
                <p className="text-xs text-muted-foreground">
                  Generated portfolio series for the sample date range
                </p>
              </CardHeader>
              <CardContent className="h-[280px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={portfolioData}>
                    <defs>
                      <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={NEON_COLORS.cyan} stopOpacity={0.4}/>
                        <stop offset="95%" stopColor={NEON_COLORS.cyan} stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0, 255, 245, 0.1)" vertical={false} />
                    <XAxis 
                      dataKey="date" 
                      tickFormatter={formatShortDate} 
                      tickLine={false} 
                      axisLine={false}
                      tick={{ fill: '#7a7a8c', fontSize: 10 }}
                    />
                    <YAxis 
                      tickLine={false} 
                      axisLine={false}
                      tick={{ fill: '#7a7a8c', fontSize: 10 }}
                      tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
                    />
                    <Tooltip 
                      formatter={(value) => [`$${(value as number)?.toLocaleString("en-US") ?? '0'}`, "Portfolio"]}
                      contentStyle={{
                        backgroundColor: 'rgba(15, 15, 26, 0.95)',
                        border: '1px solid rgba(0, 255, 245, 0.2)',
                        borderRadius: '8px',
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke={NEON_COLORS.cyan}
                      strokeWidth={2}
                      fill="url(#portfolioGradient)"
                      style={{ filter: `drop-shadow(0 0 8px ${NEON_COLORS.cyan})` }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            
            <Card className="border-[#39ff14]/20 bg-card/80 backdrop-blur-sm">
              <CardHeader>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-[#39ff14]">
                  About These Samples
                </h3>
                <p className="text-xs text-muted-foreground">Local examples with no account performance analysis</p>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <div className="flex items-start gap-3 rounded-lg border border-[#39ff14]/20 bg-[#39ff14]/5 p-3">
                  <BarChart2 className="h-5 w-5 text-[#39ff14] mt-0.5" />
                  <div>
                    <p className="font-medium text-[#39ff14]">Generated Trend Examples</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Portfolio, P&L and win-rate charts use generated local samples for the selected sample range.
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3 rounded-lg border border-[#00fff5]/20 bg-[#00fff5]/5 p-3">
                  <BarChart2 className="h-5 w-5 text-[#00fff5] mt-0.5" />
                  <div>
                    <p className="font-medium text-[#00fff5]">Fixed Example Values</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Exchange volume and strategy stats are fixed examples. They do not change with the sample range.
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3 rounded-lg border border-[#ff00ff]/20 bg-[#ff00ff]/5 p-3">
                  <BarChart2 className="h-5 w-5 text-[#ff00ff] mt-0.5" />
                  <div>
                    <p className="font-medium text-[#ff00ff]">Analysis Unavailable</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      No AI analysis or historical strategy evaluation has been performed for these examples.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="markets">
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2 border-[#ff00ff]/20 bg-card/80 backdrop-blur-sm">
              <CardHeader>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-[#ff00ff]">
                  Sample P&L Trend
                </h3>
                <p className="text-xs text-muted-foreground">Generated example values, not realized account profit or loss</p>
              </CardHeader>
              <CardContent className="h-[280px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={pnlData}>
                    <defs>
                      <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={NEON_COLORS.green} stopOpacity={0.4}/>
                        <stop offset="95%" stopColor={NEON_COLORS.green} stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(57, 255, 20, 0.1)" vertical={false} />
                    <XAxis 
                      dataKey="date" 
                      tickFormatter={formatShortDate} 
                      tickLine={false} 
                      axisLine={false}
                      tick={{ fill: '#7a7a8c', fontSize: 10 }}
                    />
                    <YAxis 
                      tickLine={false} 
                      axisLine={false}
                      tick={{ fill: '#7a7a8c', fontSize: 10 }}
                      tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
                    />
                    <Tooltip 
                      formatter={(value) => [`+$${(value as number)?.toLocaleString("en-US") ?? '0'}`, "P&L"]}
                      contentStyle={{
                        backgroundColor: 'rgba(15, 15, 26, 0.95)',
                        border: '1px solid rgba(57, 255, 20, 0.2)',
                        borderRadius: '8px',
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke={NEON_COLORS.green}
                      strokeWidth={2}
                      fill="url(#pnlGradient)"
                      style={{ filter: `drop-shadow(0 0 8px ${NEON_COLORS.green})` }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            
            <Card className="border-[#bf00ff]/20 bg-card/80 backdrop-blur-sm">
              <CardHeader>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-[#bf00ff]">
                  Sample Exchange Volume
                </h3>
                <p className="text-xs text-muted-foreground">Fixed platform examples; independent of the sample date range</p>
              </CardHeader>
              <CardContent className="h-[280px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={volumeData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(191, 0, 255, 0.1)" horizontal={false} />
                    <XAxis 
                      type="number"
                      tickLine={false} 
                      axisLine={false}
                      tick={{ fill: '#7a7a8c', fontSize: 10 }}
                      tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
                    />
                    <YAxis 
                      type="category"
                      dataKey="exchange" 
                      tickLine={false} 
                      axisLine={false}
                      tick={{ fill: '#7a7a8c', fontSize: 10 }}
                      width={70}
                    />
                    <Tooltip 
                      formatter={(value) => [`$${(value as number)?.toLocaleString("en-US") ?? '0'}`, "Volume"]}
                      contentStyle={{
                        backgroundColor: 'rgba(15, 15, 26, 0.95)',
                        border: '1px solid rgba(191, 0, 255, 0.2)',
                        borderRadius: '8px',
                      }}
                    />
                    <Bar dataKey="volume" radius={[0, 4, 4, 0]}>
                      {volumeData.map((_, index) => (
                        <Cell 
                          key={`cell-${index}`} 
                          fill={NEON_COLORS.purple}
                          style={{ filter: `drop-shadow(0 0 4px ${NEON_COLORS.purple})` }}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="strategy">
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2 border-[#ffff00]/20 bg-card/80 backdrop-blur-sm">
              <CardHeader>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-[#ffff00]">
                  Sample Win Rate Trend
                </h3>
                <p className="text-xs text-muted-foreground">Generated example percentages for the sample date range</p>
              </CardHeader>
              <CardContent className="h-[280px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={winRateData}>
                    <defs>
                      <linearGradient id="winRateGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={NEON_COLORS.yellow} stopOpacity={0.4}/>
                        <stop offset="95%" stopColor={NEON_COLORS.yellow} stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 0, 0.1)" vertical={false} />
                    <XAxis 
                      dataKey="date" 
                      tickFormatter={formatShortDate} 
                      tickLine={false} 
                      axisLine={false}
                      tick={{ fill: '#7a7a8c', fontSize: 10 }}
                    />
                    <YAxis 
                      tickLine={false} 
                      axisLine={false}
                      tick={{ fill: '#7a7a8c', fontSize: 10 }}
                      tickFormatter={(value) => `${value}%`}
                      domain={[40, 80]}
                    />
                    <Tooltip 
                      formatter={(value) => [`${(value as number)?.toFixed(1) ?? '0'}%`, "Win Rate"]}
                      contentStyle={{
                        backgroundColor: 'rgba(15, 15, 26, 0.95)',
                        border: '1px solid rgba(255, 255, 0, 0.2)',
                        borderRadius: '8px',
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke={NEON_COLORS.yellow}
                      strokeWidth={2}
                      fill="url(#winRateGradient)"
                      style={{ filter: `drop-shadow(0 0 8px ${NEON_COLORS.yellow})` }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            
            <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm">
              <CardHeader>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">
                  Fixed Sample Stats
                </h3>
                <p className="text-xs text-muted-foreground">Example metrics; not calculated from these charts or your trades</p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="rounded-lg border border-[#00fff5]/20 bg-[#00fff5]/5 p-3 text-center">
                    <p className="text-2xl font-bold font-mono text-[#00fff5]">64%</p>
                    <p className="text-xs text-muted-foreground mt-1">Win Rate</p>
                  </div>
                  <div className="rounded-lg border border-[#39ff14]/20 bg-[#39ff14]/5 p-3 text-center">
                    <p className="text-2xl font-bold font-mono text-[#39ff14]">2.4x</p>
                    <p className="text-xs text-muted-foreground mt-1">Profit Factor</p>
                  </div>
                  <div className="rounded-lg border border-[#ff00ff]/20 bg-[#ff00ff]/5 p-3 text-center">
                    <p className="text-2xl font-bold font-mono text-[#ff00ff]">$842</p>
                    <p className="text-xs text-muted-foreground mt-1">Avg Win</p>
                  </div>
                  <div className="rounded-lg border border-[#ff3366]/20 bg-[#ff3366]/5 p-3 text-center">
                    <p className="text-2xl font-bold font-mono text-[#ff3366]">-$312</p>
                    <p className="text-xs text-muted-foreground mt-1">Avg Loss</p>
                  </div>
                </div>
                <div className="rounded-lg border border-[#bf00ff]/20 bg-[#bf00ff]/5 p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <BarChart2 className="h-4 w-4 text-[#bf00ff]" />
                    <span className="text-sm font-medium text-[#bf00ff]">Example Risk/Reward</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Average R:R Ratio</span>
                    <span className="font-mono text-[#bf00ff]">1:2.7</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
