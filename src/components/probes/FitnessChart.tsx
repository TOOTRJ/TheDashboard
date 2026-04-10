"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { GenerationStats } from "@/lib/probes/types";

interface Props {
  stats: GenerationStats[];
}

export function FitnessChart({ stats }: Props) {
  if (stats.length === 0) {
    return (
      <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm">
        <CardContent className="py-12 text-center">
          <p className="text-sm text-muted-foreground">
            No generation data yet. Start a simulation to see fitness evolution.
          </p>
        </CardContent>
      </Card>
    );
  }

  const data = stats.map((s) => ({
    gen: `Gen ${s.generation}`,
    best: Number(s.best_fitness.toFixed(3)),
    avg: Number(s.avg_fitness.toFixed(3)),
    worst: Number(s.worst_fitness.toFixed(3)),
  }));

  return (
    <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">
          Fitness Over Generations
        </h3>
        <p className="text-xs text-muted-foreground">
          Best, average, and worst fitness per generation
        </p>
      </CardHeader>
      <CardContent className="h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="bestGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#00fff5" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#00fff5" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="avgGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ff00ff" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#ff00ff" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(0, 255, 245, 0.1)"
              vertical={false}
            />
            <XAxis
              dataKey="gen"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "#7a7a8c", fontSize: 10 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={{ fill: "#7a7a8c", fontSize: 10 }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(15, 15, 26, 0.95)",
                border: "1px solid rgba(0, 255, 245, 0.2)",
                borderRadius: "8px",
                fontSize: 12,
              }}
            />
            <Area
              type="monotone"
              dataKey="best"
              stroke="#00fff5"
              strokeWidth={2}
              fill="url(#bestGrad)"
              name="Best"
            />
            <Area
              type="monotone"
              dataKey="avg"
              stroke="#ff00ff"
              strokeWidth={1.5}
              fill="url(#avgGrad)"
              name="Average"
            />
            <Area
              type="monotone"
              dataKey="worst"
              stroke="#7a7a8c"
              strokeWidth={1}
              fillOpacity={0}
              strokeDasharray="4 4"
              name="Worst"
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
