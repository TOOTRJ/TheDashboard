"use client";

import * as React from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useDashboardFilters } from "@/components/layout/DashboardProvider";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { formatShortDate } from "@/lib/formatters";
import { getCryptoPriceSeries, getHoldingsDistribution, getVolumeByExchange } from "@/lib/mock";

const NEON_COLORS = {
  cyan: "#00fff5",
  pink: "#ff00ff",
  purple: "#bf00ff",
  green: "#39ff14",
  yellow: "#ffff00",
  orange: "#ff6600",
};

function ChartSkeleton() {
  return (
    <div className="h-full w-full relative overflow-hidden rounded-lg">
      <div className="absolute inset-0 shimmer" />
      <div className="absolute bottom-0 left-0 right-0 h-1/2 bg-gradient-to-t from-card to-transparent" />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="flex items-center gap-2 text-muted-foreground">
          <div className="h-4 w-4 border-2 border-[#00fff5] border-t-transparent rounded-full animate-spin" />
          <span className="text-xs uppercase tracking-wider">Loading chart...</span>
        </div>
      </div>
    </div>
  );
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string }) {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-lg border border-[#00fff5]/30 bg-card/95 backdrop-blur-xl p-3 shadow-xl shadow-[#00fff5]/10 scale-in">
        <p className="text-xs text-muted-foreground mb-2 font-mono">{label}</p>
        {payload.map((entry, index) => (
          <p key={index} className="text-sm font-mono font-medium flex items-center gap-2" style={{ color: entry.color }}>
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: entry.color, boxShadow: `0 0 8px ${entry.color}` }} />
            {entry.name}: ${entry.value.toLocaleString("en-US")}
          </p>
        ))}
      </div>
    );
  }
  return null;
}

export function Charts() {
  const { dateRange } = useDashboardFilters();
  const [isLoading, setIsLoading] = React.useState(true);
  const [isVisible, setIsVisible] = React.useState(false);

  React.useEffect(() => {
    setIsLoading(true);
    setIsVisible(false);
    const timer = setTimeout(() => {
      setIsLoading(false);
      setTimeout(() => setIsVisible(true), 50);
    }, 750);
    return () => clearTimeout(timer);
  }, [dateRange]);

  const priceData = getCryptoPriceSeries(dateRange);
  const holdingsData = getHoldingsDistribution();
  const volumeData = getVolumeByExchange();


  const cardBaseClass = `
    card-hover-glow bg-card/80 backdrop-blur-sm overflow-hidden relative
    transition-all duration-500 ease-out
  `;

  return (
    <section className="grid gap-4 lg:grid-cols-3">
      {/* Main Price Chart */}
      <Card 
        className={`lg:col-span-2 border-[#00fff5]/20 ${cardBaseClass} ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}
        style={{ transitionDelay: '0ms' }}
      >
        {/* Data stream effect */}
        <div className="absolute top-0 left-0 right-0 h-[1px] overflow-hidden">
          <div className="h-full w-full bg-gradient-to-r from-transparent via-[#00fff5] to-transparent animate-[data-flow_3s_linear_infinite]" />
        </div>
        
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5] flex items-center gap-2">
                <span className="relative">
                  <span className="absolute inset-0 animate-ping opacity-30">●</span>
                  <span className="relative">●</span>
                </span>
                Price Action
              </h2>
              <p className="text-xs text-muted-foreground mt-1">
                BTC, ETH & SOL price movements
              </p>
            </div>
            <div className="flex items-center gap-4 text-xs">
              {[
                { label: "BTC", color: NEON_COLORS.cyan },
                { label: "ETH", color: NEON_COLORS.pink },
                { label: "SOL", color: NEON_COLORS.green },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-1.5 group cursor-pointer">
                  <div 
                    className="h-2 w-2 rounded-full transition-all duration-300 group-hover:scale-150" 
                    style={{ 
                      backgroundColor: item.color,
                      boxShadow: `0 0 8px ${item.color}40`,
                    }} 
                  />
                  <span className="text-muted-foreground group-hover:text-foreground transition-colors">{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent className="h-[300px]">
          {isLoading ? (
            <ChartSkeleton />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={priceData}>
                <defs>
                  <linearGradient id="btcGlow" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={NEON_COLORS.cyan} stopOpacity={0.3}/>
                    <stop offset="95%" stopColor={NEON_COLORS.cyan} stopOpacity={0}/>
                  </linearGradient>
                  <filter id="neonGlow" x="-50%" y="-50%" width="200%" height="200%">
                    <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
                    <feMerge>
                      <feMergeNode in="coloredBlur"/>
                      <feMergeNode in="SourceGraphic"/>
                    </feMerge>
                  </filter>
                </defs>
                <CartesianGrid 
                  strokeDasharray="3 3" 
                  stroke="rgba(0, 255, 245, 0.08)" 
                  vertical={false}
                />
                <XAxis 
                  dataKey="date" 
                  tickFormatter={formatShortDate} 
                  tickLine={false} 
                  axisLine={false}
                  tick={{ fill: '#7a7a8c', fontSize: 10 }}
                />
                <YAxis 
                  yAxisId="btc"
                  tickLine={false} 
                  axisLine={false}
                  tick={{ fill: '#7a7a8c', fontSize: 10 }}
                  tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
                />
                <YAxis 
                  yAxisId="alt"
                  orientation="right"
                  tickLine={false} 
                  axisLine={false}
                  tick={{ fill: '#7a7a8c', fontSize: 10 }}
                  tickFormatter={(value) => `$${value}`}
                />
                <Tooltip content={<CustomTooltip />} />
                <Line
                  yAxisId="btc"
                  type="monotone"
                  dataKey="btc"
                  name="BTC"
                  stroke={NEON_COLORS.cyan}
                  strokeWidth={2.5}
                  dot={false}
                  filter="url(#neonGlow)"
                  animationDuration={2000}
                  animationEasing="ease-out"
                />
                <Line
                  yAxisId="alt"
                  type="monotone"
                  dataKey="eth"
                  name="ETH"
                  stroke={NEON_COLORS.pink}
                  strokeWidth={2}
                  dot={false}
                  filter="url(#neonGlow)"
                  animationDuration={2000}
                  animationEasing="ease-out"
                  animationBegin={300}
                />
                <Line
                  yAxisId="alt"
                  type="monotone"
                  dataKey="sol"
                  name="SOL"
                  stroke={NEON_COLORS.green}
                  strokeWidth={2}
                  dot={false}
                  filter="url(#neonGlow)"
                  animationDuration={2000}
                  animationEasing="ease-out"
                  animationBegin={600}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Holdings Pie Chart */}
      <Card 
        className={`border-[#ff00ff]/20 ${cardBaseClass} ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}
        style={{ transitionDelay: '100ms' }}
      >
        <div className="absolute top-0 left-0 right-0 h-[1px] overflow-hidden">
          <div className="h-full w-full bg-gradient-to-r from-transparent via-[#ff00ff] to-transparent animate-[data-flow_3s_linear_infinite]" style={{ animationDelay: '-1s' }} />
        </div>
        
        <CardHeader>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[#ff00ff]">
            Holdings
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            Portfolio allocation by asset
          </p>
        </CardHeader>
        <CardContent className="h-[300px]">
          {isLoading ? (
            <ChartSkeleton />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={holdingsData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={55}
                  outerRadius={80}
                  paddingAngle={4}
                  stroke="transparent"
                  animationDuration={1500}
                  animationEasing="ease-out"
                >
                  {holdingsData.map((entry, index) => (
                    <Cell 
                      key={`cell-${index}`} 
                      fill={entry.color}
                      style={{ 
                        filter: `drop-shadow(0 0 8px ${entry.color}60)`,
                        cursor: 'pointer',
                      }}
                    />
                  ))}
                </Pie>
                <Tooltip 
                  formatter={(value) => [`$${(value as number)?.toLocaleString("en-US") ?? '0'}`, "Value"]}
                  contentStyle={{
                    backgroundColor: 'rgba(15, 15, 26, 0.95)',
                    border: '1px solid rgba(255, 0, 255, 0.3)',
                    borderRadius: '8px',
                    fontSize: '12px',
                    backdropFilter: 'blur(10px)',
                  }}
                />
                <Legend 
                  verticalAlign="bottom" 
                  height={50}
                  formatter={(value) => (
                    <span className="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
                      {value}
                    </span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </CardContent>
        
        {/* Center decoration */}
        {!isLoading && (
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[60%] pointer-events-none">
            <div className="text-center">
              <p className="text-2xl font-bold font-mono text-[#ff00ff]">6</p>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Assets</p>
            </div>
          </div>
        )}
      </Card>

      {/* Volume by Exchange */}
      <Card 
        className={`lg:col-span-3 border-[#bf00ff]/20 ${cardBaseClass} ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}
        style={{ transitionDelay: '200ms' }}
      >
        <div className="absolute top-0 left-0 right-0 h-[1px] overflow-hidden">
          <div className="h-full w-full bg-gradient-to-r from-transparent via-[#bf00ff] to-transparent animate-[data-flow_3s_linear_infinite]" style={{ animationDelay: '-2s' }} />
        </div>
        
        <CardHeader>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[#bf00ff]">
            Trading Volume by Exchange
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            Your trading activity distribution across platforms
          </p>
        </CardHeader>
        <CardContent className="h-[220px]">
          {isLoading ? (
            <ChartSkeleton />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={volumeData} layout="vertical">
                <defs>
                  <linearGradient id="volumeGradient" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor={NEON_COLORS.purple} stopOpacity={0.9} />
                    <stop offset="100%" stopColor={NEON_COLORS.cyan} stopOpacity={0.7} />
                  </linearGradient>
                </defs>
                <CartesianGrid 
                  strokeDasharray="3 3" 
                  stroke="rgba(191, 0, 255, 0.08)" 
                  horizontal={false}
                />
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
                  tick={{ fill: '#7a7a8c', fontSize: 11 }}
                  width={80}
                />
                <Tooltip 
                  formatter={(value) => [`$${(value as number)?.toLocaleString("en-US") ?? '0'}`, "Volume"]}
                  contentStyle={{
                    backgroundColor: 'rgba(15, 15, 26, 0.95)',
                    border: '1px solid rgba(191, 0, 255, 0.3)',
                    borderRadius: '8px',
                    fontSize: '12px',
                    backdropFilter: 'blur(10px)',
                  }}
                  cursor={{ fill: 'rgba(191, 0, 255, 0.1)' }}
                />
                <Bar 
                  dataKey="volume" 
                  radius={[0, 6, 6, 0]}
                  fill="url(#volumeGradient)"
                  animationDuration={1500}
                  animationEasing="ease-out"
                >
                  {volumeData.map((_, index) => (
                    <Cell 
                      key={`cell-${index}`}
                      style={{ 
                        filter: `drop-shadow(0 0 4px ${NEON_COLORS.purple}40)`,
                        cursor: 'pointer',
                      }}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
