"use client";

import * as React from "react";
import { ArrowDownRight, ArrowUpRight, Layers, Target, TrendingUp, Wallet } from "lucide-react";
import { Line, LineChart, ResponsiveContainer } from "recharts";

import { useDashboardFilters } from "@/components/layout/DashboardProvider";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getKpiSnapshots } from "@/lib/mock";

const iconMap: Record<string, React.ElementType> = {
  wallet: Wallet,
  "trending-up": TrendingUp,
  target: Target,
  layers: Layers,
};

function AnimatedNumber({ value, prefix = "", suffix = "" }: { value: string; prefix?: string; suffix?: string }) {
  const [displayValue, setDisplayValue] = React.useState(value);
  const [isAnimating, setIsAnimating] = React.useState(false);
  
  React.useEffect(() => {
    setIsAnimating(true);
    const timer = setTimeout(() => {
      setDisplayValue(value);
      setIsAnimating(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [value]);
  
  return (
    <span className={`transition-all duration-300 ${isAnimating ? 'opacity-50 blur-[1px]' : 'opacity-100 blur-0'}`}>
      {prefix}{displayValue}{suffix}
    </span>
  );
}

export function KpiCards() {
  const { dateRange } = useDashboardFilters();
  const [isLoading, setIsLoading] = React.useState(true);
  const [isVisible, setIsVisible] = React.useState(false);

  React.useEffect(() => {
    setIsLoading(true);
    setIsVisible(false);
    const timer = setTimeout(() => {
      setIsLoading(false);
      setTimeout(() => setIsVisible(true), 50);
    }, 650);
    return () => clearTimeout(timer);
  }, [dateRange]);

  const kpis = getKpiSnapshots(dateRange);

  return (
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {kpis.map((kpi, index) => {
        const ChangeIcon = kpi.change >= 0 ? ArrowUpRight : ArrowDownRight;
        const isPositive = kpi.change >= 0;
        const Icon = iconMap[kpi.icon] || Wallet;
        
        const accentColor = index % 2 === 0 ? "#00fff5" : "#ff00ff";
        const glowClass = index % 2 === 0 ? "neon-glow-cyan" : "neon-glow-pink";

        return (
          <Card 
            key={kpi.title} 
            className={`
              card-hover-glow card-3d gradient-border-animated
              border-transparent bg-card/80 backdrop-blur-sm overflow-hidden relative
              transition-all duration-500 ease-out
              ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}
            `}
            style={{ 
              transitionDelay: `${index * 100}ms`,
            }}
          >
            {/* Animated gradient accent bar */}
            <div 
              className="absolute top-0 left-0 right-0 h-0.5 animated-gradient"
            />
            
            {/* Shimmer effect on hover */}
            <div className="absolute inset-0 opacity-0 hover:opacity-100 transition-opacity duration-500 pointer-events-none">
              <div className="absolute inset-0 shimmer" />
            </div>
            
            <CardHeader className="space-y-2 pb-2 relative">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div 
                    className={`flex h-9 w-9 items-center justify-center rounded-lg transition-all duration-300 hover:scale-110 ${glowClass}`}
                    style={{ backgroundColor: `${accentColor}15` }}
                  >
                    <Icon 
                      className="h-4 w-4 transition-transform duration-300 card-icon" 
                      style={{ color: accentColor }} 
                    />
                  </div>
                  <span className="text-xs uppercase tracking-wider text-muted-foreground font-medium">
                    {kpi.title}
                  </span>
                </div>
                <div 
                  className={`
                    inline-flex items-center gap-0.5 text-xs font-medium px-2 py-1 rounded-full
                    transition-all duration-300
                    ${isPositive 
                      ? "text-[#39ff14] bg-[#39ff14]/10 neon-text-green" 
                      : "text-[#ff3366] bg-[#ff3366]/10 neon-text-red"
                    }
                  `}
                >
                  <ChangeIcon className="h-3 w-3 animate-bounce" style={{ animationDuration: '2s' }} />
                  {Math.abs(kpi.change).toFixed(1)}%
                </div>
              </div>
              {isLoading ? (
                <div className="h-9 w-28 shimmer rounded-md" />
              ) : (
                <div 
                  className="text-3xl font-bold font-mono tracking-tight transition-all duration-300"
                  style={{ color: accentColor }}
                >
                  <AnimatedNumber value={kpi.formattedValue} />
                </div>
              )}
            </CardHeader>
            
            <CardContent className="pt-0 relative">
              {isLoading ? (
                <div className="h-14 w-full shimmer rounded-md" />
              ) : (
                <div className="h-14 w-full relative">
                  {/* Glow effect under chart */}
                  <div 
                    className="absolute bottom-0 left-1/2 -translate-x-1/2 w-3/4 h-4 blur-xl opacity-30"
                    style={{ backgroundColor: accentColor }}
                  />
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={kpi.trend}>
                      <defs>
                        <linearGradient id={`gradient-${index}`} x1="0" y1="0" x2="1" y2="0">
                          <stop offset="0%" stopColor={accentColor} stopOpacity={0.2} />
                          <stop offset="50%" stopColor={accentColor} stopOpacity={1} />
                          <stop offset="100%" stopColor={accentColor} stopOpacity={0.2} />
                        </linearGradient>
                        <filter id={`glow-${index}`}>
                          <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
                          <feMerge>
                            <feMergeNode in="coloredBlur"/>
                            <feMergeNode in="SourceGraphic"/>
                          </feMerge>
                        </filter>
                      </defs>
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke={`url(#gradient-${index})`}
                        strokeWidth={2.5}
                        dot={false}
                        filter={`url(#glow-${index})`}
                        className="chart-line-draw"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
              <p className="mt-3 text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                <span className="inline-block w-1 h-1 rounded-full bg-current animate-pulse" />
                vs. previous period
              </p>
            </CardContent>
          </Card>
        );
      })}
    </section>
  );
}
