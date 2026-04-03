"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency } from "@/lib/formatters";
import type { MonteCarloResult } from "@/lib/nestegg/monte-carlo";
import type { ProjectionResult } from "@/lib/nestegg/types";
import {
  Activity,
  AlertTriangle,
  Gauge,
  PiggyBank,
  Timer,
  TrendingDown,
} from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  mc: MonteCarloResult | null;
  deterministic: ProjectionResult;
  lifeExpectancy: number;
  /** Recomputing batched simulation */
  isRefreshing?: boolean;
  progress?: number;
};

export function NesteggProbabilityCards({
  mc,
  deterministic,
  lifeExpectancy,
  isRefreshing,
  progress = 0,
}: Props) {
  if (!mc) {
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2 px-1">
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#39ff14]/80">
            Probability engine
          </p>
          <span className="text-[10px] text-muted-foreground tabular-nums">
            Preparing…
          </span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card
              key={i}
              className="border-[#00fff5]/15 bg-card/80 backdrop-blur-sm overflow-hidden"
            >
              <CardHeader className="pb-2">
                <Skeleton className="h-9 w-9 rounded-lg bg-[#00fff5]/10" />
                <Skeleton className="mt-2 h-4 w-3/4 bg-muted/40" />
                <Skeleton className="mt-2 h-7 w-1/2 bg-muted/30" />
              </CardHeader>
              <CardContent className="pt-0">
                <Skeleton className="h-10 w-full bg-muted/20" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const successPct = Math.round(mc.successRate * 100);
  const runOutPct = Math.round(mc.chanceRunOut * 100);
  const medianRetire = formatCurrency(mc.medianNestEggAtRetirement);
  const medianEnd = formatCurrency(mc.medianEndingBalance);
  const pessimisticEnd = formatCurrency(mc.pessimisticEndingBalance);
  const optimisticEnd = formatCurrency(mc.optimisticEndingBalance);

  const gap =
    deterministic.monthlyGapOrSurplus >= 0
      ? `${formatCurrency(deterministic.monthlyGapOrSurplus)} surplus`
      : `${formatCurrency(Math.abs(deterministic.monthlyGapOrSurplus))} gap`;

  const mayLast =
    mc.worstCaseDepletionAge !== null
      ? `Weaker paths may deplete around age ${Math.ceil(mc.worstCaseDepletionAge)}`
      : `Most paths reach your horizon (${lifeExpectancy})`;

  const cards = [
    {
      title: "Chance of success",
      value: `${successPct}%`,
      sub: `${mc.paths.toLocaleString()} simulated paths`,
      detail: "Portfolio stays funded through your planning horizon.",
      icon: Gauge,
      accent: "text-[#39ff14]",
    },
    {
      title: "Median outcome (end)",
      value: medianEnd,
      sub: `Pessimistic ${pessimisticEnd} · Optimistic ${optimisticEnd}`,
      detail: "10th–90th percentile ending balances across simulations.",
      icon: Activity,
      accent: "text-[#00fff5]",
    },
    {
      title: "Projected nest egg at retirement",
      value: medianRetire,
      sub: "Median across simulations",
      detail: "When you stop contributing (simulation median).",
      icon: PiggyBank,
      accent: "text-[#bf00ff]",
    },
    {
      title: "Chance of running out",
      value: `${runOutPct}%`,
      sub: "Before end of horizon",
      detail: "Paths where assets hit zero early.",
      icon: TrendingDown,
      accent: runOutPct > 35 ? "text-[#ff3366]" : "text-[#ffff00]",
    },
    {
      title: "Portfolio may last until",
      value: `~${Math.round(mc.portfolioMayLastUntilMedianAge)}`,
      sub: mayLast,
      detail: "Median last age with assets across paths (years).",
      icon: Timer,
      accent: "text-[#00fff5]",
    },
    {
      title: "Weaker outcomes & cash flow",
      value:
        mc.worstCaseDepletionAge !== null
          ? `~${Math.ceil(mc.worstCaseDepletionAge)} depletion (stress)`
          : "No early depletion in most paths",
      sub: `Monthly ${gap} (year 1, before draws)`,
      detail: "10th percentile depletion age among paths that fail; first-year income vs spending.",
      icon: AlertTriangle,
      accent: "text-[#ff99ff]",
    },
  ];

  return (
    <div className="space-y-2">
      {isRefreshing ? (
        <div
          className="h-0.5 w-full overflow-hidden rounded-full bg-[#00fff5]/10"
          role="progressbar"
          aria-valuenow={Math.round(progress * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="h-full bg-gradient-to-r from-[#00fff5]/40 to-[#ff00ff]/50 transition-[width] duration-150 ease-out"
            style={{ width: `${Math.max(4, progress * 100)}%` }}
          />
        </div>
      ) : null}
      <div
        className={cn(
          "grid gap-3 sm:grid-cols-2 xl:grid-cols-3 transition-opacity duration-200",
          isRefreshing && "opacity-75"
        )}
      >
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <Card
            key={c.title}
            className="border-[#00fff5]/15 bg-card/80 backdrop-blur-sm"
          >
            <CardHeader className="pb-2">
              <div className="flex items-start gap-2">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#00fff5]/10">
                  <Icon className={cn("h-4 w-4", c.accent)} aria-hidden />
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground leading-tight">
                    {c.title}
                  </p>
                  <p
                    className={cn(
                      "mt-1 font-mono text-base font-bold tracking-tight sm:text-lg truncate",
                      c.accent
                    )}
                  >
                    {c.value}
                  </p>
                  {c.sub ? (
                    <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug">
                      {c.sub}
                    </p>
                  ) : null}
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <p className="text-[11px] leading-snug text-muted-foreground">{c.detail}</p>
            </CardContent>
          </Card>
        );
      })}
      </div>
    </div>
  );
}
