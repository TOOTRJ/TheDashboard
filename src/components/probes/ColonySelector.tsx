"use client";

import * as React from "react";
import { History, Clock, Dna, Trophy } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import type { ColonyRun } from "@/lib/probes/types";

interface Props {
  runs: ColonyRun[];
  activeRunId: string | null;
  onSelectRun: (runId: string) => void;
}

function formatDuration(startStr: string, endStr: string): string {
  const ms = new Date(endStr).getTime() - new Date(startStr).getTime();
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ${secs % 60}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function ColonySelector({ runs, activeRunId, onSelectRun }: Props) {
  const [open, setOpen] = React.useState(false);

  if (runs.length <= 1) return null;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="h-8 border-[#bf00ff]/20 bg-[#bf00ff]/5 text-[#bf00ff] hover:bg-[#bf00ff]/15 hover:border-[#bf00ff]/40 text-xs"
        >
          <History className="mr-1.5 h-3.5 w-3.5" />
          History ({runs.length})
        </Button>
      </SheetTrigger>
      <SheetContent
        side="right"
        className="w-full sm:max-w-md border-l border-[#bf00ff]/20 bg-card"
      >
        <SheetHeader>
          <SheetTitle className="text-[#bf00ff] uppercase tracking-wider text-sm">
            Colony History
          </SheetTitle>
        </SheetHeader>
        <div className="mt-4 space-y-2 max-h-[calc(100vh-120px)] overflow-y-auto">
          {runs.map((run) => {
            const isActive = run.run_id === activeRunId;
            return (
              <button
                key={run.run_id}
                onClick={() => {
                  onSelectRun(run.run_id);
                  setOpen(false);
                }}
                className={`
                  w-full rounded-lg border p-3 text-left transition-all
                  ${isActive
                    ? "border-[#00fff5]/40 bg-[#00fff5]/10"
                    : "border-[#bf00ff]/10 bg-card/50 hover:border-[#bf00ff]/30 hover:bg-[#bf00ff]/5"
                  }
                `}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Dna
                      className="h-3.5 w-3.5"
                      style={{ color: isActive ? "#00fff5" : "#bf00ff" }}
                    />
                    <span className="text-xs font-mono text-muted-foreground">
                      {run.run_id.slice(0, 8)}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Badge
                      variant="outline"
                      className="text-[9px] px-1 py-0"
                      style={{
                        borderColor:
                          run.mode === "paper" ? "#00fff540" : "#39ff1440",
                        color: run.mode === "paper" ? "#00fff5" : "#39ff14",
                      }}
                    >
                      {run.mode}
                    </Badge>
                    {isActive && (
                      <Badge
                        variant="outline"
                        className="text-[9px] px-1 py-0 border-[#00fff5]/40 text-[#00fff5] bg-[#00fff5]/10"
                      >
                        CURRENT
                      </Badge>
                    )}
                  </div>
                </div>
                <div className="text-[10px] text-muted-foreground mb-1">
                  {new Date(run.started_at).toLocaleString([], {
                    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                  })}
                  {run.ended_at && (
                    <span className="ml-2 font-mono">
                      ({formatDuration(run.started_at, run.ended_at)})
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-3 gap-2 text-[10px]">
                  <div className="flex items-center gap-1 text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    {formatTimeAgo(run.started_at)}
                  </div>
                  <div className="flex items-center gap-1 text-muted-foreground">
                    <Dna className="h-3 w-3" />
                    {run.probe_count} probes
                  </div>
                  <div className="flex items-center gap-1 text-muted-foreground">
                    <Trophy className="h-3 w-3" />
                    <span className="font-mono text-[#00fff5]">
                      {run.best_fitness.toFixed(3)}
                    </span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
}
