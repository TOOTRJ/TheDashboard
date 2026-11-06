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
      <TabsList className="grid w-full grid-cols-3 bg-card/50 border border-[#00fff5]/20 h-auto p-1 gap-1 ring-1 ring-[#00fff5]/5">
        {(["base", "conservative", "aggressive"] as const).map((id) => (
          <TabsTrigger
            key={id}
            value={id}
            title={
              id === "base"
                ? "Starts with your entered assumptions before risk adjustments. A 0% return keeps a zero baseline."
                : id === "conservative"
                  ? "Lower returns when possible and stress-test with higher inflation."
                  : "Higher returns; use alongside conservative for range."
            }
            className="text-xs uppercase tracking-wider py-2.5 rounded-md transition-colors data-[state=active]:bg-[#00fff5]/15 data-[state=active]:text-[#00fff5] data-[state=active]:shadow-[0_0_16px_-4px_rgba(0,255,245,0.35)] data-[state=active]:ring-1 data-[state=active]:ring-[#00fff5]/40"
          >
            {SCENARIO_LABELS[id]}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
