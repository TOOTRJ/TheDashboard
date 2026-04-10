"use client";

import * as React from "react";
import { TrendingUp, TrendingDown, Radio } from "lucide-react";
import type { PriceTick } from "@/lib/probes/types";

interface Props {
  prices: Record<string, PriceTick>;
}

export function PriceFeed({ prices }: Props) {
  const entries = Object.values(prices);

  if (entries.length === 0) return null;

  return (
    <div className="rounded-lg border border-[#00fff5]/15 bg-card/60 backdrop-blur-sm overflow-hidden">
      <div className="flex items-center gap-2 border-b border-[#00fff5]/10 px-3 py-1.5">
        <Radio className="h-3 w-3 text-[#39ff14] animate-pulse" />
        <span className="text-[10px] uppercase tracking-wider text-[#39ff14] font-bold">
          Live Prices
        </span>
        <div className="flex-1 h-px bg-gradient-to-r from-[#39ff14]/20 to-transparent" />
      </div>
      <div className="flex overflow-x-auto gap-1 px-2 py-2 scrollbar-hide">
        {entries
          .sort((a, b) => b.price - a.price)
          .map((tick) => {
            const symbol = tick.asset.split("/")[0];
            const change = tick.change ?? 0;
            const isUp = change >= 0;
            return (
              <div
                key={tick.asset}
                className="flex items-center gap-2 rounded-md border border-[#00fff5]/10 bg-[#00fff5]/5 px-3 py-1.5 shrink-0 min-w-fit"
              >
                <span className="text-xs font-bold text-foreground">
                  {symbol}
                </span>
                <span className="text-xs font-mono text-[#00fff5]">
                  $
                  {tick.price >= 1
                    ? tick.price.toLocaleString("en-US", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })
                    : tick.price.toFixed(6)}
                </span>
                {change !== 0 && (
                  <span
                    className="flex items-center text-[10px] font-medium"
                    style={{ color: isUp ? "#39ff14" : "#ff3366" }}
                  >
                    {isUp ? (
                      <TrendingUp className="h-2.5 w-2.5 mr-0.5" />
                    ) : (
                      <TrendingDown className="h-2.5 w-2.5 mr-0.5" />
                    )}
                    {isUp ? "+" : ""}
                    {change.toFixed(2)}%
                  </span>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}
