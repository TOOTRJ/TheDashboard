"use client";

import * as React from "react";
import { ActivityTable } from "@/components/dashboard/ActivityTable";
import { Charts } from "@/components/dashboard/Charts";
import { KpiCards } from "@/components/dashboard/KpiCards";
import { getHoldings, getMarketTicker } from "@/lib/mock";
import { TrendingUp, TrendingDown, Zap, Radio } from "lucide-react";

function SampleMarketBanner() {
  const ticker = getMarketTicker();
  const [offset, setOffset] = React.useState(0);
  
  React.useEffect(() => {
    const interval = setInterval(() => {
      setOffset(prev => prev - 1);
    }, 50);
    return () => clearInterval(interval);
  }, []);
  
  // Double the ticker for seamless loop
  const doubledTicker = [...ticker, ...ticker];
  
  return (
    <div className="overflow-hidden rounded-lg border border-[#00fff5]/20 bg-gradient-to-r from-card/90 via-card/50 to-card/90 backdrop-blur-sm relative">
      {/* Animated border glow */}
      <div className="absolute inset-0 rounded-lg opacity-50">
        <div className="absolute inset-0 rounded-lg bg-gradient-to-r from-[#00fff5]/0 via-[#00fff5]/20 to-[#00fff5]/0 animate-pulse" />
      </div>
      
      <div className="flex items-center gap-3 border-b border-[#00fff5]/10 px-4 py-2 relative">
        <div className="relative flex items-center gap-2">
          <Radio className="h-3 w-3 text-[#39ff14] animate-pulse" />
          <span className="text-xs uppercase tracking-wider text-[#39ff14] font-bold">Sample ticker</span>
        </div>
        <div className="flex-1 h-px bg-gradient-to-r from-[#00fff5]/20 via-[#00fff5]/5 to-transparent" />
        <span className="text-[10px] text-muted-foreground font-mono">
          Local clock, not quote time: {new Date().toLocaleTimeString()}
        </span>
      </div>
      
      <div className="relative overflow-hidden py-3">
        <div 
          className="flex gap-8 whitespace-nowrap transition-transform"
          style={{ transform: `translateX(${offset}px)` }}
        >
          {doubledTicker.map((item, idx) => (
            <div 
              key={`${item.symbol}-${idx}`}
              className="flex items-center gap-3 px-4 py-1.5 rounded-lg bg-[#00fff5]/5 hover:bg-[#00fff5]/10 transition-colors cursor-pointer group"
            >
              <span className="text-sm font-bold text-foreground group-hover:text-[#00fff5] transition-colors">
                {item.symbol}
              </span>
              <span className="text-sm font-mono text-[#00fff5]">
                ${item.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className={`flex items-center text-xs font-medium ${item.change >= 0 ? 'text-[#39ff14]' : 'text-[#ff3366]'}`}>
                {item.change >= 0 ? <TrendingUp className="h-3 w-3 mr-0.5" /> : <TrendingDown className="h-3 w-3 mr-0.5" />}
                {item.change >= 0 ? '+' : ''}{item.change.toFixed(2)}%
              </span>
            </div>
          ))}
        </div>
        
        {/* Fade edges */}
        <div className="absolute left-0 top-0 bottom-0 w-12 bg-gradient-to-r from-card to-transparent pointer-events-none" />
        <div className="absolute right-0 top-0 bottom-0 w-12 bg-gradient-to-l from-card to-transparent pointer-events-none" />
      </div>
    </div>
  );
}

function HoldingsTicker() {
  const holdings = getHoldings();
  const [hoveredIndex, setHoveredIndex] = React.useState<number | null>(null);
  
  return (
    <div className="overflow-hidden rounded-lg border border-[#ff00ff]/20 bg-card/50 backdrop-blur-sm relative gradient-border-animated">
      <div className="flex items-center gap-2 border-b border-[#ff00ff]/10 px-4 py-2">
        <Zap className="h-3 w-3 text-[#ff00ff] animate-pulse" />
        <span className="text-xs uppercase tracking-wider text-[#ff00ff] font-bold">Example holdings</span>
        <div className="flex-1" />
        <span className="text-xs text-muted-foreground">
          {holdings.length} assets
        </span>
      </div>
      <div className="flex overflow-x-auto py-3 px-2 gap-3 scrollbar-hide">
        {holdings.map((holding, index) => (
          <div 
            key={holding.symbol}
            className={`
              flex items-center gap-3 rounded-lg border border-[#00fff5]/10 
              bg-gradient-to-br from-[#00fff5]/5 to-transparent
              px-4 py-3 min-w-fit cursor-pointer
              transition-all duration-300 ease-out
              hover:border-[#00fff5]/30 hover:scale-105 hover:shadow-lg hover:shadow-[#00fff5]/10
              ${hoveredIndex === index ? 'scale-105 border-[#00fff5]/30' : ''}
            `}
            style={{
              animationDelay: `${index * 100}ms`,
            }}
            onMouseEnter={() => setHoveredIndex(index)}
            onMouseLeave={() => setHoveredIndex(null)}
          >
            <div 
              className={`
                flex h-10 w-10 items-center justify-center rounded-full text-xs font-bold
                transition-all duration-300
                ${hoveredIndex === index ? 'scale-110 rotate-12' : ''}
              `}
              style={{ 
                backgroundColor: `${holding.color}25`,
                color: holding.color,
                boxShadow: hoveredIndex === index ? `0 0 20px ${holding.color}40` : 'none',
              }}
            >
              {holding.symbol.slice(0, 2)}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold">{holding.symbol}</span>
                <span className={`
                  flex items-center text-xs font-medium px-1.5 py-0.5 rounded
                  ${holding.change24h >= 0 
                    ? 'text-[#39ff14] bg-[#39ff14]/10' 
                    : 'text-[#ff3366] bg-[#ff3366]/10'
                  }
                `}>
                  {holding.change24h >= 0 ? <TrendingUp className="h-3 w-3 mr-0.5" /> : <TrendingDown className="h-3 w-3 mr-0.5" />}
                  {holding.change24h >= 0 ? '+' : ''}{holding.change24h.toFixed(1)}%
                </span>
              </div>
              <div className="flex items-baseline gap-2 text-xs mt-0.5">
                <span className="text-muted-foreground">{holding.amount} {holding.symbol}</span>
                <span className="font-mono text-[#00fff5] font-medium">${holding.value.toLocaleString()}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function WelcomeHeader() {
  const [time, setTime] = React.useState(new Date());
  
  React.useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  
  const greeting = time.getHours() < 12 ? "Good Morning" : time.getHours() < 18 ? "Good Afternoon" : "Good Evening";
  
  return (
    <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-2">
      <div>
        <p className="text-sm text-muted-foreground mb-1">{greeting}, Trader</p>
        <h1 className="text-2xl sm:text-3xl font-bold">
          <span className="glitch neon-text-cyan" data-text="Welcome back">
            Welcome back
          </span>
          <span className="text-[#ff00ff]">.</span>
        </h1>
      </div>
      <div className="flex items-center gap-3">
        <div className="text-right">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Local Time</p>
          <p className="text-lg font-mono text-[#00fff5] tabular-nums">
            {time.toLocaleTimeString()}
          </p>
        </div>
        <div className="h-10 w-px bg-gradient-to-b from-transparent via-[#00fff5]/30 to-transparent" />
        <div className="text-right">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">UTC</p>
          <p className="text-lg font-mono text-muted-foreground tabular-nums">
            {time.toLocaleTimeString('en-US', { timeZone: 'UTC' })}
          </p>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <div className="space-y-6">
      <p className="rounded-lg border border-[#00fff5]/20 bg-[#00fff5]/5 p-3 text-sm text-muted-foreground">
        All prices, holdings, metrics, charts and activity below are generated or fixed examples. No account trades or live quotes are loaded.
      </p>
      <WelcomeHeader />
      <SampleMarketBanner />
      <HoldingsTicker />
      <KpiCards />
      <Charts />
      <ActivityTable />
    </div>
  );
}
