"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import { GENE_DEFINITIONS } from "@/lib/probes/gene-registry";
import type { Genome } from "@/lib/probes/types";

interface Props {
  genome: Genome;
}

// Dynamically derive radar genes from registry (exclude num_assets)
const RADAR_GENES = GENE_DEFINITIONS.filter((g) => g.name !== "num_assets");

export function GenomeRadar({ genome }: Props) {
  const data = RADAR_GENES.map((gene) => {
    const raw = (genome as unknown as Record<string, unknown>)[gene.name] as number;
    const normalized =
      gene.max > gene.min ? ((raw - gene.min) / (gene.max - gene.min)) * 100 : 50;
    return {
      gene: gene.label,
      value: Math.max(0, Math.min(100, normalized)),
    };
  });

  return (
    <ResponsiveContainer width="100%" height={260}>
      <RadarChart data={data} cx="50%" cy="50%" outerRadius="75%">
        <PolarGrid stroke="rgba(0, 255, 245, 0.15)" />
        <PolarAngleAxis
          dataKey="gene"
          tick={{ fill: "#7a7a8c", fontSize: 9 }}
        />
        <Radar
          dataKey="value"
          stroke="#00fff5"
          fill="#00fff5"
          fillOpacity={0.2}
          strokeWidth={2}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}
