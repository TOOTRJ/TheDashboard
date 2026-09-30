"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { GenerationStats } from "@/lib/probes/types";

interface Props {
  stats: GenerationStats[];
}

export function GenerationTimeline({ stats }: Props) {
  if (stats.length === 0) {
    return null;
  }

  return (
    <Card className="border-[#ff00ff]/20 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-[#ff00ff]">
          Generation Timeline
        </h3>
      </CardHeader>
      <CardContent>
        <div className="flex overflow-x-auto gap-3 pb-2 scrollbar-hide">
          {stats.map((gen) => (
            <div
              key={gen.generation}
              className="flex-shrink-0 rounded-lg border border-[#ff00ff]/10 bg-[#ff00ff]/5 p-3 min-w-[140px]"
            >
              <p className="text-xs font-bold text-[#ff00ff] mb-2">
                Gen {gen.generation}
              </p>
              <div className="space-y-1 text-[10px]">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Alive / total</span>
                  <span className="font-mono">
                    {gen.alive_probes}/{gen.total_probes}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Best Fit</span>
                  <span className="font-mono text-[#00fff5]">
                    {gen.best_fitness.toFixed(3)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Avg ROI</span>
                  <span
                    className="font-mono"
                    style={{
                      color: gen.avg_roi >= 0 ? "#39ff14" : "#ff3366",
                    }}
                  >
                    {(gen.avg_roi * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Diversity</span>
                  <span className="font-mono">
                    {gen.genome_diversity.toFixed(3)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
