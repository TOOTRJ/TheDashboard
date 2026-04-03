"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { NesteggInsight } from "@/lib/nestegg/insights-engine";
import { Lightbulb } from "lucide-react";

type Props = {
  insights: NesteggInsight[];
};

export function NesteggInsightsPanel({ insights }: Props) {
  if (insights.length === 0) return null;

  return (
    <Card className="border-[#ff00ff]/20 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#ff00ff]/10">
            <Lightbulb className="h-4 w-4 text-[#ff99ff]" aria-hidden />
          </div>
          <div>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-[#ff99ff]">
              Insights
            </h3>
            <p className="text-[11px] text-muted-foreground">
              Plain-English takeaways from your numbers — not predictions
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <ul className="space-y-2 text-sm text-muted-foreground leading-relaxed">
          {insights.map((ins) => (
            <li key={ins.id} className="flex gap-2">
              <span className="text-[#ff99ff] shrink-0" aria-hidden>
                ·
              </span>
              <span>{ins.text}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
