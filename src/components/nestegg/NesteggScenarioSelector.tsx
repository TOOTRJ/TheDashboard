"use client";

import { cn } from "@/lib/utils";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { NesteggScenarioId } from "@/lib/nestegg/types";
import { SCENARIO_LABELS } from "@/lib/nestegg/constants";

type Props = {
  value: NesteggScenarioId;
  onChange: (v: NesteggScenarioId) => void;
  className?: string;
};

export function NesteggScenarioSelector({ value, onChange, className }: Props) {
  return (
    <Tabs
      value={value}
      onValueChange={(v) => onChange(v as NesteggScenarioId)}
      className={cn("w-full", className)}
    >
      <TabsList className="grid w-full grid-cols-3 bg-card/50 border border-[#00fff5]/20 h-auto p-1 gap-1">
        {(["base", "conservative", "aggressive"] as const).map((id) => (
          <TabsTrigger
            key={id}
            value={id}
            className="text-xs uppercase tracking-wider data-[state=active]:bg-[#00fff5]/10 data-[state=active]:text-[#00fff5] py-2"
          >
            {SCENARIO_LABELS[id]}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
