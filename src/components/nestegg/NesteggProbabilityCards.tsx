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

export type NesteggProbabilityTier = "all" | "primary" | "secondary";

type Props = {
  mc: MonteCarloResult | null;
  deterministic: ProjectionResult;
  lifeExpectancy: number;
  /** Recomputing batched simulation */
  isRefreshing?: boolean;
  progress?: number;
  /** Split headline vs deeper metrics without changing any calculations. */
  tier?: NesteggProbabilityTier;
  /** Hide the built-in section title when a parent (e.g. collapsible) already has one. */
  hideSectionLabel?: boolean;
};

const PRIMARY_CARD_INDEXES = [0, 3, 2] as const;
const SECONDARY_CARD_INDEXES = [1, 4, 5] as const;

export function NesteggProbabilityCards({
  mc,
  deterministic,
  lifeExpectancy,
  isRefreshing,
  progress = 0,
  tier = "all",
  hideSectionLabel = false,
}: Props) {
  const skeletonCount = tier === "primary" ? 3 : tier === "secondary" ? 3 : 6;

  if (!mc) {
    if (tier === "secondary") return null;
    return (
      <div className="space-y-2">
        {!(hideSectionLabel && tier === "primary") ? (
          <div className="flex items-center justify-between gap-2 px-1">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#39ff14]/80">
              {tier === "primary" ? "Headline results" : "Probability engine"}
            </p>
            <span className="text-[10px] text-muted-foreground tabular-nums">
              Preparing…
            </span>
          </div>
        ) : (
          <div className="flex justify-end px-1">
            <span className="text-[10px] text-muted-foreground tabular-nums">Preparing…</span>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: skeletonCount }).map((_, i) => (
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
      detail:
        "Share of paths where your portfolio stays funded through your planning horizon.",
      icon: Gauge,
      accent: "text-[#39ff14]",
    },
    {
      title: "Most likely balance at the end",
      value: medianEnd,
      sub: `Stress case ${pessimisticEnd} · upside ${optimisticEnd}`,
      detail: "Typical range of ending balances (10th–90th percentile across runs).",
      icon: Activity,
      accent: "text-[#00fff5]",
    },
    {
      title: "What you may have at retirement",
      value: medianRetire,
      sub: "Typical result across simulations",
      detail: "Median balance when you retire and stop contributing.",
      icon: PiggyBank,
      accent: "text-[#bf00ff]",
    },
    {
      title: "Risk of running out of money",
      value: `${runOutPct}%`,
      sub: "Before end of your horizon",
      detail: "Paths where assets reach zero before the plan ends.",
      icon: TrendingDown,
      accent: runOutPct > 35 ? "text-[#ff3366]" : "text-[#ffff00]",
    },
    {
      title: "How long your money may last",
      value: `~${Math.round(mc.portfolioMayLastUntilMedianAge)}`,
      sub: mayLast,
      detail: "Typical last age with assets still in the portfolio (across paths).",
      icon: Timer,
      accent: "text-[#00fff5]",
    },
    {
      title: "Stress path & cash flow",
      value:
        mc.worstCaseDepletionAge !== null
          ? `~${Math.ceil(mc.worstCaseDepletionAge)} in weaker paths`
          : "No early depletion in most paths",
      sub: `Year 1: ${gap} (before portfolio draws)`,
      detail:
        "Rough picture of weaker outcomes and first-year income vs spending before draws.",
      icon: AlertTriangle,
      accent: "text-[#ff99ff]",
    },
  ];

  const indexes =
    tier === "primary"
      ? PRIMARY_CARD_INDEXES
      : tier === "secondary"
        ? SECONDARY_CARD_INDEXES
        : ([0, 1, 2, 3, 4, 5] as const);
  const visibleCards = indexes.map((i) => cards[i]!);

  return (
    <div className="space-y-2">
      {tier !== "secondary" && !(hideSectionLabel && tier === "primary") ? (
        <div className="flex items-center justify-between gap-2 px-1">
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#39ff14]/80">
            {tier === "primary" ? "Headline results" : "Probability engine"}
          </p>
          {isRefreshing ? (
            <span className="text-[10px] text-muted-foreground tabular-nums">Updating…</span>
          ) : null}
        </div>
      ) : null}
      {tier !== "secondary" && hideSectionLabel && tier === "primary" && isRefreshing ? (
        <div className="flex justify-end px-1">
          <span className="text-[10px] text-muted-foreground tabular-nums">Updating…</span>
        </div>
      ) : null}
      {tier !== "secondary" && isRefreshing ? (
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
          isRefreshing && tier !== "secondary" && "opacity-75"
        )}
      >
      {visibleCards.map((c) => {
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
