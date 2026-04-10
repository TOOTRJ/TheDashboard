"use client";

import * as React from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type {
  Probe,
  GenerationStats,
  SystemStatus,
  SimulationStatus,
  ColonyRun,
  PriceTick,
} from "@/lib/probes/types";
import type { StartConfig } from "@/lib/probes/colony-config";
import { SimulationControls } from "./SimulationControls";
import { ProbesOverview } from "./ProbesOverview";
import { ProbeGrid } from "./ProbeGrid";
import { ProbeDetail } from "./ProbeDetail";
import { FitnessChart } from "./FitnessChart";
import { GenerationTimeline } from "./GenerationTimeline";
import { GenealogyTree } from "./GenealogyTree";
import { ColonySelector } from "./ColonySelector";
import { PriceFeed } from "./PriceFeed";

interface Props {
  probes: Probe[];
  generationStats: GenerationStats[];
  systemStatus: SystemStatus | null;
  connected: boolean;
  simStatus: SimulationStatus;
  mode: string;
  starting: boolean;
  colonyRuns: ColonyRun[];
  activeRunId: string | null;
  prices: Record<string, PriceTick>;
  onStart: (config: StartConfig) => void;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
  onSelectRun: (runId: string) => void;
}

export function ProbesDashboard({
  probes,
  generationStats,
  systemStatus,
  connected,
  simStatus,
  mode,
  starting,
  colonyRuns,
  activeRunId,
  prices,
  onStart,
  onStop,
  onPause,
  onResume,
  onSelectRun,
}: Props) {
  const [selectedProbe, setSelectedProbe] = React.useState<Probe | null>(null);
  const [detailOpen, setDetailOpen] = React.useState(false);

  const handleSelectProbe = (probe: Probe) => {
    setSelectedProbe(probe);
    setDetailOpen(true);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex-1">
          <SimulationControls
            status={simStatus}
            connected={connected}
            generation={systemStatus?.generation ?? 0}
            tick={systemStatus?.tick ?? 0}
            liveProbes={
              systemStatus?.live_probes ??
              probes.filter((p) => p.state !== "DEAD").length
            }
            mode={mode}
            starting={starting}
            onStart={onStart}
            onStop={onStop}
            onPause={onPause}
            onResume={onResume}
          />
        </div>
        <ColonySelector
          runs={colonyRuns}
          activeRunId={activeRunId}
          onSelectRun={onSelectRun}
        />
      </div>

      <PriceFeed prices={prices} />

      <ProbesOverview probes={probes} systemStatus={systemStatus} />

      <Tabs defaultValue="colony" className="space-y-4">
        <TabsList className="bg-card/50 border border-[#00fff5]/20">
          <TabsTrigger
            value="colony"
            className="data-[state=active]:bg-[#00fff5]/10 data-[state=active]:text-[#00fff5]"
          >
            Colony
          </TabsTrigger>
          <TabsTrigger
            value="evolution"
            className="data-[state=active]:bg-[#ff00ff]/10 data-[state=active]:text-[#ff00ff]"
          >
            Evolution
          </TabsTrigger>
          <TabsTrigger
            value="genealogy"
            className="data-[state=active]:bg-[#bf00ff]/10 data-[state=active]:text-[#bf00ff]"
          >
            Genealogy
          </TabsTrigger>
        </TabsList>

        <TabsContent value="colony">
          <ProbeGrid probes={probes} onSelectProbe={handleSelectProbe} />
        </TabsContent>

        <TabsContent value="evolution" className="space-y-4">
          <FitnessChart stats={generationStats} />
          <GenerationTimeline stats={generationStats} />
        </TabsContent>

        <TabsContent value="genealogy">
          <GenealogyTree probes={probes} onSelectProbe={handleSelectProbe} />
        </TabsContent>
      </Tabs>

      <ProbeDetail
        probe={selectedProbe}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      />
    </div>
  );
}
