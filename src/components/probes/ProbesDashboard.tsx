"use client";

import * as React from "react";
import type { ExecutionPolicy } from "@/lib/probes/execution";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type {
  Probe,
  LifecyclePolicy,
  GenerationStats,
  SystemStatus,
  SimulationStatus,
  ColonyRun,
  ColonyInfo,
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
  lifecyclePolicy?: LifecyclePolicy;
  executionPolicy?: ExecutionPolicy;
  systemStatus: SystemStatus | null;
  valuationAvailable?: boolean;
  connected: boolean;
  simStatus: SimulationStatus;
  mode: string;
  strategy?: string;
  activeColonies: ColonyInfo[];
  starting: boolean;
  startError?: string | null;
  recoveryAvailable: boolean;
  controlPending: boolean;
  colonyRuns: ColonyRun[];
  activeRunId: string | null;
  prices: Record<string, PriceTick>;
  onStart: (config: StartConfig) => Promise<boolean>;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
  onRecover: () => void;
  onSelectRun: (runId: string) => void;
}

export function ProbesDashboard({
  probes,
  generationStats,
  lifecyclePolicy,
  executionPolicy,
  systemStatus,
  valuationAvailable,
  connected,
  simStatus,
  mode,
  strategy,
  activeColonies,
  starting,
  startError,
  recoveryAvailable,
  controlPending,
  colonyRuns,
  activeRunId,
  prices,
  onStart,
  onStop,
  onPause,
  onResume,
  onRecover,
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
            strategy={strategy}
            activeColonies={activeColonies}
            starting={starting}
            startError={startError}
            recoveryAvailable={recoveryAvailable}
            controlPending={controlPending}
            onStart={onStart}
            onStop={onStop}
            onPause={onPause}
            onResume={onResume}
            onRecover={onRecover}
          />
        </div>
        <ColonySelector
          runs={colonyRuns}
          activeRunId={activeRunId}
          activeColonies={activeColonies}
          onSelectRun={onSelectRun}
        />
      </div>

      <PriceFeed prices={prices} mode={mode} policy={executionPolicy} />

      <ProbesOverview probes={probes} systemStatus={systemStatus} valuationAvailable={valuationAvailable} />

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
          <p className="text-xs text-muted-foreground">
            {lifecyclePolicy
              ? "Generations group candidate births, not ancestry depth. A summary requires closed membership and confirmed terminal records for every candidate. Generation diversity is RMS numeric distance; live population diversity uses a different measure."
              : "The reporting policy is unavailable for this run. Historical generation statistics may use earlier definitions."}
          </p>
          <FitnessChart stats={generationStats} />
          <GenerationTimeline stats={generationStats} />
        </TabsContent>

        <TabsContent value="genealogy">
          <GenealogyTree probes={probes} onSelectProbe={handleSelectProbe} />
        </TabsContent>
      </Tabs>

      <ProbeDetail
        probe={probes.find((probe) => probe.id === selectedProbe?.id) ?? selectedProbe}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      />
    </div>
  );
}
