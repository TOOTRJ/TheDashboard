"use client";

import { Card, CardContent } from "@/components/ui/card";
import { formatCurrency } from "@/lib/formatters";
import { Wallet, TrendingUp } from "lucide-react";

type Props = {
  currentPortfolio: number;
  projectedAtRetirement: number;
  retirementAge: number;
};

export function NesteggPortfolioHighlightCard({
  currentPortfolio,
  projectedAtRetirement,
  retirementAge,
}: Props) {
  return (
    <Card className="border-[#00fff5]/20 bg-card/85 backdrop-blur-sm shadow-[0_0_24px_-8px_rgba(0,255,245,0.1)]">
      <CardContent className="p-4 sm:p-5">
        <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-4">
          Portfolio
        </p>
        <div className="grid gap-4 sm:grid-cols-2 sm:gap-6">
          <div className="flex gap-3 min-w-0">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#00fff5]/12 ring-1 ring-[#00fff5]/20">
              <Wallet className="h-5 w-5 text-[#00fff5]" aria-hidden />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Current portfolio
              </p>
              <p className="mt-1 font-mono text-xl sm:text-2xl font-bold tracking-tight text-[#00fff5] truncate">
                {formatCurrency(currentPortfolio)}
              </p>
              <p className="text-[11px] text-muted-foreground mt-1 leading-snug">
                What you have invested today (same as plan inputs).
              </p>
            </div>
          </div>
          <div className="flex gap-3 min-w-0 sm:border-l sm:border-[#00fff5]/10 sm:pl-6">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#bf00ff]/12 ring-1 ring-[#bf00ff]/20">
              <TrendingUp className="h-5 w-5 text-[#bf00ff]" aria-hidden />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Projected at retirement (baseline path)
              </p>
              <p className="mt-1 font-mono text-xl sm:text-2xl font-bold tracking-tight text-[#bf00ff] truncate">
                {formatCurrency(projectedAtRetirement)}
              </p>
              <p className="text-[11px] text-muted-foreground mt-1 leading-snug">
                Single-path estimate when you retire at age {retirementAge}.
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
