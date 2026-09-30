"use client";

import * as React from "react";
import { Loader2, Pause, Play, Square, Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ConnectionStatus } from "./ConnectionStatus";
import { ColonyConfigDialog } from "./ColonyConfigDialog";
import type { SimulationStatus, ColonyInfo } from "@/lib/probes/types";
import type { StartConfig } from "@/lib/probes/colony-config";
import { STRATEGY_LABELS } from "@/lib/probes/constants";

interface Props {
  status: SimulationStatus;
  connected: boolean;
  generation: number;
  tick: number;
  liveProbes: number;
  mode: string;
  strategy?: string;
  activeColonies?: ColonyInfo[];
  starting: boolean;
  startError?: string | null;
  onStart: (config: StartConfig) => Promise<boolean>;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
}

export function SimulationControls({
  status,
  connected,
  generation,
  tick,
  liveProbes,
  mode,
  strategy,
  activeColonies,
  starting,
  startError,
  onStart,
  onStop,
  onPause,
  onResume,
}: Props) {
  const [configOpen, setConfigOpen] = React.useState(false);

  return (
    <>
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[#00fff5]/20 bg-card/80 px-4 py-3 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          {!["running", "paused", "starting"].includes(status) ? (
            <Button
              size="sm"
              onClick={() => setConfigOpen(true)}
              disabled={starting}
              className="h-8 border border-[#39ff14]/30 bg-[#39ff14]/10 text-[#39ff14] hover:bg-[#39ff14]/20 text-xs"
            >
              {starting ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Settings2 className="mr-1.5 h-3.5 w-3.5" />
              )}
              {starting ? "Launching..." : "New Colony"}
            </Button>
          ) : (
            <>
              {status === "running" ? (
                <Button
                  size="sm"
                  onClick={onPause}
                  className="h-8 border border-[#ffff00]/30 bg-[#ffff00]/10 text-[#ffff00] hover:bg-[#ffff00]/20 text-xs"
                >
                  <Pause className="mr-1.5 h-3.5 w-3.5" />
                  Pause
                </Button>
              ) : status === "paused" ? (
                <Button
                  size="sm"
                  onClick={onResume}
                  className="h-8 border border-[#39ff14]/30 bg-[#39ff14]/10 text-[#39ff14] hover:bg-[#39ff14]/20 text-xs"
                >
                  <Play className="mr-1.5 h-3.5 w-3.5" />
                  Resume
                </Button>
              ) : null}
              <Button
                size="sm"
                onClick={onStop}
                disabled={status === "starting"}
                className="h-8 border border-[#ff3366]/30 bg-[#ff3366]/10 text-[#ff3366] hover:bg-[#ff3366]/20 text-xs"
              >
                <Square className="mr-1.5 h-3.5 w-3.5" />
                Stop
              </Button>
            </>
          )}
        </div>

        <div className="h-6 w-px bg-[#00fff5]/20" />

        <Badge variant="outline" className="text-[10px] uppercase">
          {status === "unknown" ? "Status unavailable" : status}
        </Badge>

        {["running", "paused", "starting"].includes(status) && (
          <Badge
            variant="outline"
            className="text-[10px] px-1.5 py-0"
            style={{
              borderColor: mode === "paper" ? "#00fff540" : "#39ff1440",
              backgroundColor: mode === "paper" ? "#00fff510" : "#39ff1410",
              color: mode === "paper" ? "#00fff5" : "#39ff14",
            }}
          >
            {mode === "paper" ? "LIVE PRICES" : "SIMULATED"}
          </Badge>
        )}

        {["running", "paused", "starting"].includes(status) && strategy && (
          <Badge variant="outline" className="ml-2 text-xs">
            {STRATEGY_LABELS[strategy] ?? strategy}
          </Badge>
        )}

        {activeColonies && activeColonies.length > 1 && (
          <Badge
            variant="outline"
            className="text-[10px] px-1.5 py-0 border-[#bf00ff]/40 bg-[#bf00ff]/10 text-[#bf00ff]"
          >
            {activeColonies.length} colonies
          </Badge>
        )}

        <div className="flex items-center gap-4 text-xs">
          <div>
            <span className="text-muted-foreground">Gen </span>
            <span className="font-mono text-[#00fff5]">{generation}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Tick </span>
            <span className="font-mono text-[#00fff5]">{tick}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Probes </span>
            <span className="font-mono text-[#39ff14]">{liveProbes}</span>
          </div>
        </div>

        <div className="flex-1" />
        <ConnectionStatus connected={connected} />
      </div>

      <ColonyConfigDialog
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        onStart={async (cfg) => {
          const launched = await onStart(cfg);
          if (launched) setConfigOpen(false);
          return launched;
        }}
        starting={starting}
        startError={startError}
      />
    </>
  );
}
