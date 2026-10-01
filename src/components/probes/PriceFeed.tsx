"use client";

import * as React from "react";
import { formatReferenceNumber, type ExecutionPolicy } from "@/lib/probes/execution";
import { TrendingUp, TrendingDown, Radio } from "lucide-react";
import type { PriceTick } from "@/lib/probes/types";

interface Props {
  prices: Record<string, PriceTick>;
  mode?: string;
  policy?: ExecutionPolicy;
}

export function PriceFeed({ prices, mode, policy }: Props) {
  const entries = Object.values(prices);

  if (entries.length === 0) return null;

  return (
    <div className="rounded-lg border border-[#00fff5]/15 bg-card/60 backdrop-blur-sm overflow-hidden">
      <div className="flex items-center gap-2 border-b border-[#00fff5]/10 px-3 py-1.5">
        <Radio className="h-3 w-3 text-[#39ff14]" />
        <span className="text-[10px] uppercase tracking-wider text-[#39ff14] font-bold">
          {mode === "simulation" ? "Last reported synthetic prices" : "Last reported reference prices"}{policy ? " · USD" : " · unit unverified"}
        </span>
        <div className="flex-1 h-px bg-gradient-to-r from-[#39ff14]/20 to-transparent" />
      </div>
      <div className="flex overflow-x-auto gap-1 px-2 py-2 scrollbar-hide">
        {entries
          .sort((a, b) => b.price - a.price)
          .map((tick) => {
            const symbol = tick.asset.split("/")[0];
            const change = typeof tick.change === "number" && Number.isFinite(tick.change) ? tick.change : 0;
            const sourceTime = typeof tick.timestamp === "number" ? new Date(tick.timestamp * 1000) : null;
            const sourceLabel = sourceTime && Number.isFinite(sourceTime.getTime()) ? `Source/model time: ${sourceTime.toISOString()}` : "Source time unavailable";
            const isUp = change >= 0;
            return (
              <div
                key={tick.asset}
                title={sourceLabel}
                className="flex items-center gap-2 rounded-md border border-[#00fff5]/10 bg-[#00fff5]/5 px-3 py-1.5 shrink-0 min-w-fit"
              >
                <span className="text-xs font-bold text-foreground">
                  {symbol}
                </span>
                <span className="text-xs font-mono text-[#00fff5]">
                  {policy ? "$" : ""}{formatReferenceNumber(tick.price)}
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
