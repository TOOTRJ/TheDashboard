"use client";

import { Activity, Dna, DollarSign, TrendingUp, Zap } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { Probe, SystemStatus } from "@/lib/probes/types";

interface Props {
  probes: Probe[];
  systemStatus: SystemStatus | null;
  valuationAvailable?: boolean;
}

export function ProbesOverview({ probes, systemStatus, valuationAvailable }: Props) {
  const live = probes.filter((p) => p.state !== "DEAD");
  const bestFitness = live.length > 0
    ? Math.max(...live.map((p) => p.fitness_score))
    : 0;
  const totalCapital = systemStatus?.total_capital;
  const hasValuation = valuationAvailable !== false && systemStatus?.valuation_available !== false &&
    typeof totalCapital === "number" && Number.isFinite(totalCapital);
  const reserve = systemStatus?.reserve_capital;
  const reserveText = typeof reserve === "number" && Number.isFinite(reserve)
    ? `$${reserve.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "unavailable";
  const diversity = systemStatus?.diversity;
  const maxGen = probes.length > 0
    ? Math.max(...probes.map((p) => p.generation))
    : 0;

  // API usage metrics
  const apiCalls = systemStatus?.jup_api_calls ?? 0;
  const uptimeSecs = systemStatus?.uptime_secs ?? 0;
  const callsPerMin = uptimeSecs > 0 ? (apiCalls / uptimeSecs) * 60 : 0;
  const projected24h = Math.round(callsPerMin * 60 * 24);
  const isPaper = systemStatus?.mode === "paper";

  const cards = [
    {
      label: "Active Probes",
      value: live.length.toString(),
      sub: `${probes.length - live.length} dead`,
      icon: Activity,
      color: "#39ff14",
    },
    {
      label: "Generation",
      value: (systemStatus?.generation ?? maxGen).toString(),
      sub: `${systemStatus?.tick ?? 0} ticks`,
      icon: Dna,
      color: "#00fff5",
    },
    {
      label: "Best Fitness",
      value: Number.isFinite(bestFitness) ? bestFitness.toFixed(3) : "Unavailable",
      sub: systemStatus
        ? `Diversity: ${typeof diversity === "number" && Number.isFinite(diversity) ? diversity.toFixed(3) : "unavailable"}`
        : undefined,
      icon: TrendingUp,
      color: "#ff00ff",
    },
    {
      label: "Colony Capital",
      value: hasValuation ? `$${totalCapital.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "Unavailable",
      sub: hasValuation
        ? `Last reported total · Reserve: ${reserveText}`
        : "Current market valuation is unavailable",
      icon: DollarSign,
      color: "#ffff00",
    },
  ];

  // Add JUP API card when in paper mode or when there are API calls
  if (isPaper || apiCalls > 0) {
    cards.push({
      label: "JUP API Calls",
      value: apiCalls.toLocaleString(),
      sub: callsPerMin > 0
        ? `${callsPerMin.toFixed(1)}/min \u00b7 ~${projected24h.toLocaleString()}/24h`
        : undefined,
      icon: Zap,
      color: "#bf00ff",
    });
  }

  return (
    <div className={`grid gap-3 sm:grid-cols-2 ${cards.length > 4 ? "lg:grid-cols-5" : "lg:grid-cols-4"}`}>
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <Card
            key={card.label}
            className="border-[color:var(--accent)]/20 bg-card/80 backdrop-blur-sm"
            style={{ "--accent": card.color } as React.CSSProperties}
          >
            <CardContent className="flex items-center gap-3 p-4">
              <div
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
                style={{ backgroundColor: `${card.color}15` }}
              >
                <Icon className="h-5 w-5" style={{ color: card.color }} />
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  {card.label}
                </p>
                <p
                  className="text-lg font-bold font-mono"
                  style={{ color: card.color }}
                >
                  {card.value}
                </p>
                {card.sub && (
                  <p className="text-[10px] text-muted-foreground">
                    {card.sub}
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
