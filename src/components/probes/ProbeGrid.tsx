"use client";

import * as React from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ProbeCard } from "./ProbeCard";
import type { Probe } from "@/lib/probes/types";

interface Props {
  probes: Probe[];
  onSelectProbe: (probe: Probe) => void;
}

type SortKey = "fitness" | "capital" | "generation" | "trades";

function sortProbes(probes: Probe[], key: SortKey): Probe[] {
  const sorted = [...probes];
  switch (key) {
    case "fitness":
      return sorted.sort((a, b) => b.fitness_score - a.fitness_score);
    case "capital":
      return sorted.sort((a, b) => b.current_capital - a.current_capital);
    case "generation":
      return sorted.sort((a, b) => b.generation - a.generation || b.fitness_score - a.fitness_score);
    case "trades":
      return sorted.sort((a, b) => b.total_trades - a.total_trades);
    default:
      return sorted;
  }
}

export function ProbeGrid({ probes, onSelectProbe }: Props) {
  const [sortKey, setSortKey] = React.useState<SortKey>("fitness");
  const [showDead, setShowDead] = React.useState(false);

  const filtered = showDead
    ? probes
    : probes.filter((p) => p.state !== "DEAD");
  const sorted = sortProbes(filtered, sortKey);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Select
          value={sortKey}
          onValueChange={(v) => setSortKey(v as SortKey)}
        >
          <SelectTrigger className="w-36 h-8 border-[#00fff5]/20 bg-[#00fff5]/5 text-xs">
            <SelectValue placeholder="Sort by" />
          </SelectTrigger>
          <SelectContent className="border-[#00fff5]/20 bg-card">
            <SelectItem value="fitness">Fitness</SelectItem>
            <SelectItem value="capital">Capital</SelectItem>
            <SelectItem value="generation">Generation</SelectItem>
            <SelectItem value="trades">Trades</SelectItem>
          </SelectContent>
        </Select>
        <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={showDead}
            onChange={(e) => setShowDead(e.target.checked)}
            className="rounded border-[#00fff5]/30"
          />
          Show dead
        </label>
        <span className="text-[10px] text-muted-foreground ml-auto">
          {sorted.length} probes
        </span>
      </div>

      {sorted.length === 0 ? (
        <div className="rounded-lg border border-dashed border-[#00fff5]/20 p-12 text-center">
          <p className="text-sm text-muted-foreground">
            No probes yet. Start a simulation to spawn the colony.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {sorted.map((probe) => (
            <ProbeCard
              key={probe.id}
              probe={probe}
              onClick={() => onSelectProbe(probe)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
