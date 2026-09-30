"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { BookOpen, Dna } from "lucide-react";
import { useAuth } from "@/components/auth/AuthProvider";
import { ProbesDashboard } from "@/components/probes/ProbesDashboard";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchProbes, fetchGenerationStats, fetchColonyRuns } from "@/lib/probes/probes-supabase";
import { useProbesWebSocket } from "@/lib/probes/websocket";
import { VN_ENDPOINTS } from "@/lib/probes/constants";
import {
  belongsToSelectedColony, colonyPath, createSelectionScope,
  requestWorker, WorkerRequestError,
  formatColonyFailure,
} from "@/lib/probes/transport";
import { validateStartConfig, type StartConfig } from "@/lib/probes/colony-config";
import type {
  Probe, GenerationStats, SimulationStatus, SystemStatus,
  ColonyRun, ColonyInfo, PriceTick, WsMessage,
} from "@/lib/probes/types";

export default function ProbesPage() {
  const { user, session, loading } = useAuth();
  if (loading) return <Skeleton className="h-64 w-full bg-[#00fff5]/10" />;
  if (!user || !session) {
    return (
      <div className="space-y-6">
        <PageHeader simStatus="stopped" mode="simulation" startedAt={null} />
        <p className="rounded-lg border border-[#00fff5]/20 bg-card/80 p-12 text-center text-sm text-muted-foreground">
          Sign in to access the Von Neumann probe colony.
        </p>
      </div>
    );
  }
  // An account change unmounts all private state, pending work and subscriptions.
  return <AuthenticatedProbesPage key={user.id} userId={user.id} accessToken={session.access_token} />;
}

function AuthenticatedProbesPage({ userId, accessToken }: { userId: string; accessToken: string }) {
  const [scope] = React.useState(createSelectionScope);
  const [probes, setProbes] = React.useState<Probe[]>([]);
  const [genStats, setGenStats] = React.useState<GenerationStats[]>([]);
  const [colonyRuns, setColonyRuns] = React.useState<ColonyRun[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [simStatus, setSimStatus] = React.useState<SimulationStatus>("unknown");
  const [simMode, setSimMode] = React.useState("simulation");
  const [systemStatus, setSystemStatus] = React.useState<SystemStatus | null>(null);
  const [startingToken, setStartingToken] = React.useState<string | null>(null);
  const starting = startingToken === accessToken;
  const [prices, setPrices] = React.useState<Record<string, PriceTick>>({});
  const [activeColonies, setActiveColonies] = React.useState<ColonyInfo[]>([]);
  const [selectedColonyId, setSelectedColonyId] = React.useState<string | null>(null);
  const [errors, setErrors] = React.useState<Record<string, string | null>>({});
  const reportError = React.useCallback((source: string, error: string | null) => {
    setErrors((previous) => ({ ...previous, [source]: error }));
  }, []);
  const prevPrices = React.useRef<Record<string, number>>({});
  const creating = React.useRef(false);
  const controlling = React.useRef(false);

  React.useLayoutEffect(() => {
    scope.activate();
    return () => scope.dispose();
  }, [scope, accessToken]);

  const selectColony = React.useCallback((id: string) => {
    if (scope.current() === id) return;
    scope.select(id);
    setSelectedColonyId(id);
    setProbes([]);
    setGenStats([]);
    setPrices({});
    prevPrices.current = {};
    setSystemStatus(null);
    setSimStatus("unknown");
    setSimMode("simulation");
    reportError("status", null);
    reportError("data", null);
    setStartingToken(null);
    setLoading(true);
  }, [scope, reportError]);

  const handleWsMessage = React.useCallback((msg: WsMessage) => {
    // No event, including a status or death event, may modify a different colony.
    if (!belongsToSelectedColony(msg, scope.current())) return;
    switch (msg.type) {
      case "probe_born":
      case "probe_update": {
        const d = msg.data;
        setProbes((prev) => {
          const idx = prev.findIndex((p) => p.id === d.probe_id);
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = { ...updated[idx], ...mapWsToProbe(d) };
            return updated;
          }
          return msg.type === "probe_born" ? [...prev, mapWsToProbe(d) as Probe] : prev;
        });
        break;
      }
      case "probe_dying":
      case "probe_reproducing": {
        const d = msg.data;
        setProbes((prev) => prev.map((p) => p.id === d.probe_id
          ? { ...p, state: "DEAD" as const, death_reason: (d.reason as string) || msg.type }
          : p));
        break;
      }
      case "simulation_status": {
        const data = msg.data as unknown as SystemStatus;
        // A later REST status response must not undo this newer event.
        scope.begin("status");
        setSystemStatus(data);
        setSimStatus(data.status);
        setSimMode(data.mode || "simulation");
        reportError("status", null);
        break;
      }
      case "generation_complete": {
        const data = msg.data as unknown as GenerationStats;
        setGenStats((prev) => prev.some((s) => s.generation === data.generation) ? prev : [...prev, data]);
        break;
      }
      case "price_update": {
        const data = msg.data as { prices?: Record<string, { price: number }> };
        if (!data.prices) break;
        const changes: Record<string, PriceTick> = {};
        for (const [asset, info] of Object.entries(data.prices)) {
          const before = prevPrices.current[asset] ?? info.price;
          changes[asset] = { asset, price: info.price, change: before > 0 ? ((info.price - before) / before) * 100 : 0 };
          prevPrices.current[asset] = info.price;
        }
        setPrices((prev) => ({ ...prev, ...changes }));
        break;
      }
    }
  }, [scope, reportError]);

  const connection = useProbesWebSocket(accessToken, userId, handleWsMessage);

  const refreshColonyList = React.useCallback(async () => {
    const ticket = scope.begin("list");
    const [history, live] = await Promise.allSettled([
      fetchColonyRuns(),
      requestWorker<ColonyInfo[]>(VN_ENDPOINTS, accessToken, "/api/v1/colonies/"),
    ]);
    if (!scope.isCurrent(ticket)) return;
    const runs = history.status === "fulfilled" ? history.value : [];
    const colonies = live.status === "fulfilled" && Array.isArray(live.value) ? live.value : [];
    if (history.status === "fulfilled") {
      setColonyRuns(runs);
      reportError("history", null);
    } else {
      reportError("history", "Colony history is unavailable. The last successful result is retained.");
    }
    if (live.status === "fulfilled" && Array.isArray(live.value)) {
      setActiveColonies(colonies);
      reportError("live", null);
    } else {
      reportError("live", "The current colony list is unavailable. The last successful result is retained.");
    }
    if (scope.current() === null) {
      const id = colonies.at(-1)?.colony_id ?? runs[0]?.run_id;
      if (id) selectColony(id);
      else setLoading(false);
    }
  }, [accessToken, scope, selectColony, reportError]);

  React.useEffect(() => {
    void refreshColonyList();
    const timer = setInterval(() => void refreshColonyList(), 10_000);
    return () => clearInterval(timer);
  }, [refreshColonyList]);

  const refreshSelected = React.useCallback(async (signal?: AbortSignal) => {
    const id = scope.current();
    if (!id) return;
    const ticket = scope.begin("data");
    try {
      // Never query without the selected run ID: that would combine all colonies.
      const [rows, stats] = await Promise.all([fetchProbes(id), fetchGenerationStats(id)]);
      if (signal?.aborted || !scope.isCurrent(ticket)) return;
      setProbes(rows);
      setGenStats(stats);
      reportError("data", null);
    } catch {
      if (!signal?.aborted && scope.isCurrent(ticket)) reportError("data", "Colony data is unavailable. The last successful result is retained.");
    } finally {
      if (!signal?.aborted && scope.isCurrent(ticket)) setLoading(false);
    }
  }, [scope, reportError]);

  const refreshStatus = React.useCallback(async (signal?: AbortSignal) => {
    const id = scope.current();
    if (!id) return;
    const ticket = scope.begin("status");
    try {
      const data = await requestWorker<SystemStatus>(VN_ENDPOINTS, accessToken, colonyPath(id), { signal });
      if (signal?.aborted || !scope.isCurrent(ticket)) return;
      setSystemStatus(data);
      setSimStatus(data.status);
      setSimMode(data.mode || "simulation");
      reportError("status", null);
    } catch (error) {
      if (signal?.aborted || !scope.isCurrent(ticket)) return;
      reportError("status", error instanceof WorkerRequestError && error.status === 404
        ? "This colony is unavailable from the worker. Saved history may still be available."
        : "Current colony status is unavailable. The last confirmed status is retained.");
    }
  }, [accessToken, scope, reportError]);

  React.useEffect(() => {
    if (!selectedColonyId) return;
    const abort = new AbortController();
    const refresh = () => { void refreshSelected(abort.signal); void refreshStatus(abort.signal); };
    refresh();
    const timer = setInterval(refresh, 5_000);
    return () => { abort.abort(); clearInterval(timer); };
  }, [selectedColonyId, refreshSelected, refreshStatus]);

  const handleStart = async (config: StartConfig): Promise<boolean> => {
    if (creating.current) return false;
    const issues = validateStartConfig(config);
    if (issues.length > 0) {
      reportError("launch", issues.map((issue) => issue.message).join(" "));
      return false;
    }
    reportError("launch", null);
    creating.current = true;
    const ticket = scope.begin("create");
    setStartingToken(accessToken);
    try {
      const result = await requestWorker<{ colony_id: string }>(VN_ENDPOINTS, accessToken, "/api/v1/colonies/", {
        method: "POST", body: config,
      });
      if (!scope.isCurrent(ticket)) return false;
      selectColony(result.colony_id);
      setSimStatus("running");
      setSimMode(config.mode);
      void refreshColonyList();
      toast.success("Colony launched");
      return true;
    } catch (error) {
      if (scope.isCurrent(ticket)) {
        const message = error instanceof WorkerRequestError ? error.message : "Could not confirm colony startup. Refresh the colony list before retrying.";
        reportError("launch", message);
        void refreshColonyList();
      }
      return false;
    } finally {
      creating.current = false;
      if (scope.isCurrent(ticket)) setStartingToken(null);
    }
  };

  const handleControl = async (action: "stop" | "pause" | "resume") => {
    if (controlling.current) return;
    const ticket = scope.begin("control");
    if (!ticket.colonyId) return;
    controlling.current = true;
    try {
      await requestWorker(VN_ENDPOINTS, accessToken, colonyPath(ticket.colonyId, action), { method: "POST" });
      if (!scope.isCurrent(ticket)) return;
      reportError("control", null);
      // Confirm the worker's resulting state, including failed persistence/reconciliation.
      void refreshStatus();
      void refreshSelected();
      void refreshColonyList();
    } catch (error) {
      if (scope.isCurrent(ticket)) {
        reportError("control", error instanceof WorkerRequestError ? error.message : "The action could not be confirmed. Refresh colony status before retrying.");
        void refreshStatus();
      }
    } finally {
      controlling.current = false;
    }
  };

  const selectedHistory = colonyRuns.find((run) => run.run_id === selectedColonyId);
  const savedTerminal = selectedHistory?.status === "failed" || selectedHistory?.status === "stopped";
  const showSavedStatus = (!systemStatus || !!errors.status) && savedTerminal;
  const displayedStatus = showSavedStatus ? selectedHistory.status! : simStatus;
  const displayedMode = showSavedStatus ? selectedHistory.mode : simMode;
  const diagnostics = showSavedStatus || !systemStatus ? selectedHistory?.runtime : systemStatus;
  const marketTimestamp = diagnostics?.clock_basis === "synthetic_market" && typeof diagnostics.market_time === "string"
    ? Date.parse(diagnostics.market_time) : NaN;
  const syntheticMarketTime = Number.isFinite(marketTimestamp)
    ? new Date(marketTimestamp).toISOString().replace("T", " ").replace(".000Z", "Z").replace("Z", " UTC") : null;
  const errorMessages = [...new Set([VN_ENDPOINTS.error, ...Object.values(errors), connection.error].filter(Boolean))];
  return (
    <div className="space-y-6">
      <PageHeader simStatus={displayedStatus} mode={displayedMode} startedAt={systemStatus?.started_at ?? null} />
      {errorMessages.length > 0 && (
        <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm space-y-1">
          {errorMessages.map((message) => <p key={message}>{message}</p>)}
          <button type="button" className="underline" onClick={() => {
            void refreshColonyList(); void refreshSelected(); void refreshStatus();
          }}>Retry data and status</button>
        </div>
      )}
      {loading && <p role="status" className="text-sm text-muted-foreground">Loading colony data…</p>}
      {showSavedStatus && <p className="text-sm text-muted-foreground">Showing the saved terminal status. Current worker status is unavailable.</p>}
      {syntheticMarketTime && (
        <p className="text-xs text-muted-foreground">
          Last reported synthetic market time: <span className="font-mono">{syntheticMarketTime}</span>.
          {" "}Prices are generated. Playback speed changes service pacing;
          trade and probe timestamps use this modeled clock.
        </p>
      )}
      {displayedStatus === "failed" && <p role="alert" className="text-sm text-destructive">{formatColonyFailure(diagnostics?.failure_code)}</p>}
      {diagnostics?.state_persisted === false && <p role="alert" className="text-sm text-destructive">Colony state could not be saved. Displayed results may not survive a worker restart.</p>}
      {diagnostics?.valuation_available === false && <p role="alert" className="text-sm text-destructive">Current colony valuation is unavailable. Previously recorded probe balances are not a current market valuation.</p>}
      {diagnostics?.requires_reconciliation && <p role="alert" className="text-sm text-destructive">Paper positions or saved trade records require reconciliation.{(diagnostics.open_positions ?? 0) > 0 && ` ${diagnostics.open_positions} paper positions remain open.`}</p>}
      <ProbesDashboard
        key={`${userId}:${selectedColonyId ?? "none"}`}
        probes={probes}
        generationStats={genStats}
        systemStatus={systemStatus}
        valuationAvailable={diagnostics?.valuation_available}
        strategy={systemStatus?.strategy}
        activeColonies={activeColonies}
        connected={connection.connected}
        simStatus={displayedStatus}
        mode={displayedMode}
        starting={starting}
        startError={errors.launch}
        colonyRuns={colonyRuns}
        activeRunId={selectedColonyId}
        prices={prices}
        onStart={handleStart}
        onStop={() => handleControl("stop")}
        onPause={() => handleControl("pause")}
        onResume={() => handleControl("resume")}
        onSelectRun={selectColony}
      />
    </div>
  );
}

function PageHeader({
  simStatus,
  mode,
  startedAt,
}: {
  simStatus: SimulationStatus;
  mode: string;
  startedAt: string | null;
}) {
  const [elapsed, setElapsed] = React.useState("");

  React.useEffect(() => {
    if (!startedAt || !["running", "paused", "starting"].includes(simStatus)) {
      setElapsed("");
      return;
    }
    const start = new Date(startedAt).getTime();
    const tick = () => {
      const diff = Math.max(0, Math.floor((Date.now() - start) / 1000));
      const h = Math.floor(diff / 3600);
      const m = Math.floor((diff % 3600) / 60);
      const s = diff % 60;
      setElapsed(
        h > 0
          ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
          : `${m}:${String(s).padStart(2, "0")}`,
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAt, simStatus]);

  const isActive = ["running", "paused", "starting"].includes(simStatus);

  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-[#00fff5]/20 bg-gradient-to-br from-[#00fff5]/20 to-[#ff00ff]/15">
          <Dna className="h-6 w-6 text-[#00fff5]" aria-hidden />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold uppercase tracking-wider text-[#00fff5] neon-text-cyan">
              Von Neumann Probes
            </h2>
            {isActive && (
              <span
                className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border"
                style={{
                  borderColor: mode === "paper" ? "#00fff540" : "#39ff1440",
                  backgroundColor: mode === "paper" ? "#00fff510" : "#39ff1410",
                  color: mode === "paper" ? "#00fff5" : "#39ff14",
                }}
              >
                {mode === "paper" ? "Paper Trade" : "Simulation"}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground max-w-xl leading-relaxed">
            Self-replicating evolutionary trading colony. Probes evolve through
            genetic crossover and mutation — profitable ones reproduce, losing ones
            die.
          </p>
          <Link
            href="/docs#probes"
            className="mt-1 inline-flex items-center gap-1 text-[11px] text-white/30 hover:text-[#00fff5] transition-colors"
          >
            <BookOpen className="h-3 w-3" />
            View Documentation
          </Link>
        </div>
      </div>
      {isActive && startedAt && (
        <div className="text-right shrink-0">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
            Elapsed
          </p>
          <p className="text-lg font-mono text-[#00fff5] tabular-nums">{elapsed}</p>
          <p className="text-[10px] text-muted-foreground">
            {new Date(startedAt).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        </div>
      )}
    </div>
  );
}

function mapWsToProbe(d: Record<string, unknown>): Partial<Probe> {
  return {
    id: d.probe_id as string,
    probe_name: (d.probe_name as string) || "",
    state: (d.state as Probe["state"]) || "OBSERVING",
    generation: (d.generation as number) || 0,
    genome: d.genome as Probe["genome"],
    initial_capital: (d.initial_capital as number) || 0,
    current_capital: (d.current_capital as number) || 0,
    peak_capital: (d.peak_capital as number) || 0,
    total_trades: (d.total_trades as number) || 0,
    winning_trades: (d.winning_trades as number) || 0,
    total_pnl: (d.total_pnl as number) || 0,
    max_drawdown: ((d.max_drawdown_pct as number) || 0) / 100,
    sharpe_ratio: (d.sharpe_ratio as number) || 0,
    fitness_score: (d.fitness_score as number) || 0,
    born_at: (d.born_at as string) || new Date().toISOString(),
    died_at: (d.died_at as string) || null,
    death_reason: (d.death_reason as string) || null,
    mode: (d.mode as string) || "simulation",
    parent_id: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}
