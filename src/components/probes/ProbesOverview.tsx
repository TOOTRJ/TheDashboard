"use client";

import { Activity, Dna, DollarSign, TrendingUp, Zap } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { Probe, SystemStatus } from "@/lib/probes/types";

interface Props {
  probes: Probe[];
  systemStatus: SystemStatus | null;
}

export function ProbesOverview({ probes, systemStatus }: Props) {
  const live = probes.filter((p) => p.state !== "DEAD");
  const bestFitness = live.length > 0
    ? Math.max(...live.map((p) => p.fitness_score))
    : 0;
  const totalCapital = live.reduce((s, p) => s + p.current_capital, 0);
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
      value: bestFitness.toFixed(3),
      sub: systemStatus
        ? `Diversity: ${systemStatus.diversity.toFixed(3)}`
        : undefined,
      icon: TrendingUp,
      color: "#ff00ff",
    },
    {
      label: "Colony Capital",
      value: `$${totalCapital.toLocaleString("en-US", { maximumFractionDigits: 0 })}`,
      sub: systemStatus
        ? `Reserve: $${systemStatus.reserve_capital.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
        : undefined,
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
