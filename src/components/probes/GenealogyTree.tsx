"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { STATE_COLORS, STATE_LABELS } from "@/lib/probes/constants";
import { probeParentIds } from "@/lib/probes/lifecycle";
import type { Probe } from "@/lib/probes/types";

interface Props {
  probes: Probe[];
  onSelectProbe: (probe: Probe) => void;
}

export function GenealogyTree({ probes, onSelectProbe }: Props) {
  const byId = new Map(probes.map((probe) => [probe.id, probe]));
  const ordered = [...probes].sort((a, b) => a.generation - b.generation || a.born_at.localeCompare(b.born_at) || a.id.localeCompare(b.id));
  return (
    <Card className="border-[#bf00ff]/20 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-[#bf00ff]">Probe Genealogy</h3>
        <p className="text-xs text-muted-foreground">
          Candidates grouped by birth generation. Source links include cloning, crossover and numerical optimizer contributors.
        </p>
      </CardHeader>
      <CardContent className="max-h-[400px] overflow-y-auto">
        {ordered.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No saved candidates for this colony.</p>
        ) : ordered.map((probe) => {
          const parents = probeParentIds(probe);
          return (
            <div key={probe.id} className="border-b border-muted/20 py-2 text-xs">
              <button onClick={() => onSelectProbe(probe)} className="flex items-center gap-2 rounded px-2 py-1 hover:bg-[#00fff5]/10">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: STATE_COLORS[probe.state] }} aria-hidden="true" />
                <span className="sr-only">{STATE_LABELS[probe.state]}</span>
                <span className="font-medium">{probe.probe_name}</span>
                <Badge variant="outline" className="px-1 py-0 text-[9px]">G{probe.generation}</Badge>
                <span className="font-mono text-muted-foreground">F:{probe.fitness_score.toFixed(2)}</span>
              </button>
              <div className="ml-6 flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
                <span>{parents.length ? "Sources:" : "No recorded sources"}</span>
                {parents.map((id) => {
                  const parent = byId.get(id);
                  return parent ? (
                    <button key={id} onClick={() => onSelectProbe(parent)} className="rounded border border-[#00fff5]/20 px-1.5 py-0.5 hover:text-[#00fff5]">
                      {parent.probe_name}
                    </button>
                  ) : <span key={id} title={id} className="rounded border border-muted/20 px-1.5 py-0.5">{id.slice(0, 8)} · outside loaded history</span>;
                })}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
