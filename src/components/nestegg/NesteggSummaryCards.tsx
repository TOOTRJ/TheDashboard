"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { formatCurrency } from "@/lib/formatters";
import type { ProjectionResult, ReadinessLevel } from "@/lib/nestegg/types";
import { Landmark, Hourglass, Scale, Target } from "lucide-react";

import { cn } from "@/lib/utils";

const readinessCopy: Record<
  ReadinessLevel,
  { hint: string; color: string }
> = {
  Excellent: {
    hint: "Your plan looks resilient across the modeled horizon.",
    color: "text-[#39ff14]",
  },
  Strong: {
    hint: "You are in a solid position with room to refine details.",
    color: "text-[#00fff5]",
  },
  "Needs Attention": {
    hint: "Small adjustments to savings or timing may help a lot.",
    color: "text-[#ffff00]",
  },
  "High Risk": {
    hint: "Consider revisiting spending, income, or retirement age.",
    color: "text-[#ff3366]",
  },
};

export type NesteggSummaryTier = "all" | "primary" | "secondary";

type Props = {
  result: ProjectionResult;
  lifeExpectancy: number;
  /** Core vs supporting deterministic snapshot cards (same numbers). */
  tier?: NesteggSummaryTier;
};

export function NesteggSummaryCards({ result, lifeExpectancy, tier = "all" }: Props) {
  const {
    nestEggAtRetirement,
    depletionAge,
    lastsThroughLifeExpectancy,
    monthlyGapOrSurplus,
    readiness,
    readinessScore,
  } = result;

  const longevityLabel = lastsThroughLifeExpectancy
    ? `Through age ${lifeExpectancy}`
    : depletionAge !== null
      ? `May deplete by ~${Math.ceil(depletionAge)}`
      : "—";

  const longevityDetail = lastsThroughLifeExpectancy
    ? "Portfolio stays above zero in this simulation."
    : "Modeled balance reaches zero before your horizon.";

  const gapLabel =
    monthlyGapOrSurplus >= 0
      ? `${formatCurrency(monthlyGapOrSurplus)} / mo surplus`
      : `${formatCurrency(Math.abs(monthlyGapOrSurplus))} / mo shortfall`;

  const gapDetail =
    "First year of retirement: income minus spending, before portfolio withdrawals.";

  const rc = readinessCopy[readiness];

  const cards: Array<{
    title: string;
    value: string;
    sub?: string;
    detail: string;
    icon: typeof Landmark;
    accent: string;
  }> = [
    {
      title: "What you’ll have at retirement",
      value: formatCurrency(nestEggAtRetirement),
      detail: "Single-path estimate when you stop contributing and begin drawdown.",
      icon: Landmark,
      accent: "text-[#00fff5]",
    },
    {
      title: "How long your money may last",
      value: longevityLabel,
      detail: longevityDetail,
      icon: Hourglass,
      accent: "text-[#bf00ff]",
    },
    {
      title: "Retirement cash flow (year one)",
      value: gapLabel,
      detail: gapDetail,
      icon: Scale,
      accent: monthlyGapOrSurplus >= 0 ? "text-[#39ff14]" : "text-[#ff3366]",
    },
    {
      title: "Plan readiness",
      value: readiness,
      sub: `${readinessScore} / 100`,
      detail: rc.hint,
      icon: Target,
      accent: rc.color,
    },
  ];

  const indexes =
    tier === "primary"
      ? ([0, 1] as const)
      : tier === "secondary"
        ? ([2, 3] as const)
        : ([0, 1, 2, 3] as const);
  const visibleCards = indexes.map((i) => cards[i]!);

  return (
    <div
      className={cn(
        "grid gap-3 sm:grid-cols-2",
        tier === "all" ? "xl:grid-cols-4" : "xl:grid-cols-2"
      )}
    >
      {visibleCards.map((c) => {
        const Icon = c.icon;
        return (
          <Card
            key={c.title}
            className={cn(
              "border-[#00fff5]/20 bg-card/80 backdrop-blur-sm",
              tier === "secondary" && "border-[#00fff5]/10 bg-card/60"
            )}
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
                      "mt-1 font-mono text-lg font-bold tracking-tight truncate",
                      c.accent
                    )}
                  >
                    {c.value}
                  </p>
                  {c.sub ? (
                    <p className="text-xs text-muted-foreground mt-0.5">{c.sub}</p>
                  ) : null}
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <p className="text-[11px] leading-snug text-muted-foreground">
                {c.detail}
              </p>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
