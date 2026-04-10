"use client";

import * as React from "react";
import { toast } from "sonner";
import { Dna } from "lucide-react";

import { useAuth } from "@/components/auth/AuthProvider";
import { ProbesDashboard } from "@/components/probes/ProbesDashboard";
import { Skeleton } from "@/components/ui/skeleton";
import {
  fetchProbes,
  fetchGenerationStats,
  fetchLatestRunId,
  fetchColonyRuns,
} from "@/lib/probes/probes-supabase";
import { useProbesWebSocket } from "@/lib/probes/websocket";
import { VN_API_URL, VN_API_KEY } from "@/lib/probes/constants";
import type { StartConfig } from "@/lib/probes/colony-config";
import type {
  Probe,
  GenerationStats,
  SimulationStatus,
  SystemStatus,
  ColonyRun,
  PriceTick,
  WsMessage,
} from "@/lib/probes/types";

export default function ProbesPage() {
  const { user, loading: authLoading } = useAuth();

  const [probes, setProbes] = React.useState<Probe[]>([]);
  const [genStats, setGenStats] = React.useState<GenerationStats[]>([]);
  const [colonyRuns, setColonyRuns] = React.useState<ColonyRun[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [simStatus, setSimStatus] = React.useState<SimulationStatus>("stopped");
  const [simMode, setSimMode] = React.useState<string>("simulation");
  const [runId, setRunId] = React.useState<string | null>(null);
  const [systemStatus, setSystemStatus] = React.useState<SystemStatus | null>(null);
  const [starting, setStarting] = React.useState(false);
  const [prices, setPrices] = React.useState<Record<string, PriceTick>>({});
  // Track previous prices for computing change %
  const prevPrices = React.useRef<Record<string, number>>({});

  // WS callback — fires for every message, no drops from batching
  const handleWsMessage = React.useCallback((msg: WsMessage) => {
    switch (msg.type) {
      case "probe_born":
      case "probe_update": {
        const d = msg.data as Record<string, unknown>;
        const probeId = d.probe_id as string;
        setProbes((prev) => {
          const idx = prev.findIndex((p) => p.id === probeId);
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = { ...updated[idx], ...mapWsToProbe(d) };
            return updated;
          }
          if (msg.type === "probe_born") {
            return [...prev, mapWsToProbe(d) as Probe];
          }
          return prev;
        });
        break;
      }
      case "probe_dying":
      case "probe_reproducing": {
        const d = msg.data as Record<string, unknown>;
        const probeId = d.probe_id as string;
        setProbes((prev) =>
          prev.map((p) =>
            p.id === probeId
              ? { ...p, state: "DEAD" as const, death_reason: (d.reason as string) || msg.type }
              : p,
          ),
        );
        break;
      }
      case "simulation_status": {
        const d = msg.data as unknown as SystemStatus & { run_id?: string };
        setSystemStatus(d);
        setSimStatus(d.status);
        setSimMode(d.mode || "simulation");
        if (d.run_id) setRunId(d.run_id);
        break;
      }
      case "generation_complete": {
        const d = msg.data as unknown as GenerationStats;
        setGenStats((prev) => {
          const exists = prev.some((s) => s.generation === d.generation);
          return exists ? prev : [...prev, d];
        });
        break;
      }
      case "price_update": {
        const d = msg.data as {
          prices: Record<string, { price: number; volume: number }>;
          tick: number;
        };
        if (d.prices) {
          setPrices((prev) => {
            const next: Record<string, PriceTick> = { ...prev };
            for (const [asset, info] of Object.entries(d.prices)) {
              const prevPrice = prevPrices.current[asset] || info.price;
              const change =
                prevPrice > 0
                  ? ((info.price - prevPrice) / prevPrice) * 100
                  : 0;
              next[asset] = { asset, price: info.price, change };
              prevPrices.current[asset] = info.price;
            }
            return next;
          });
        }
        break;
      }
    }
  }, []);

  const { connected } = useProbesWebSocket(handleWsMessage);

  // ── Helpers ────────────────────────────────────────────────────────────

  const apiCall = async (path: string, method = "POST", body?: unknown) => {
    const res = await fetch(`${VN_API_URL}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        "x-api-key": VN_API_KEY,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(err.detail || "Request failed");
    }
    return res.json();
  };

  const refreshFromSupabase = React.useCallback(
    async (rid?: string | null) => {
      if (!user) return;
      const activeRunId = rid ?? runId;
      const [probeRows, statsRows] = await Promise.all([
        fetchProbes(activeRunId ?? undefined),
        fetchGenerationStats(activeRunId ?? undefined),
      ]);
      setProbes(probeRows);
      setGenStats(statsRows);
    },
    [user, runId],
  );

  const refreshColonyRuns = React.useCallback(async () => {
    if (!user) return;
    const runs = await fetchColonyRuns();
    setColonyRuns(runs);
  }, [user]);

  // ── Check service status on mount ─────────────────────────────────────

  const checkServiceStatus = React.useCallback(async () => {
    try {
      const data = await apiCall("/api/v1/status", "GET");
      const status = data.status as SimulationStatus;
      if (status === "running" || status === "paused") {
        setSimStatus(status);
        setSimMode((data.mode as string) || "simulation");
        setSystemStatus(data as unknown as SystemStatus);
        if (data.run_id) {
          setRunId(data.run_id as string);
          return data.run_id as string;
        }
      } else {
        setSimStatus("stopped");
      }
    } catch {
      setSimStatus("stopped");
    }
    return null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Initial load ──────────────────────────────────────────────────────

  React.useEffect(() => {
    if (authLoading || !user) return;
    let cancelled = false;
    (async () => {
      const [activeRunId] = await Promise.all([
        checkServiceStatus(),
        refreshColonyRuns(),
      ]);
      const effectiveRunId = activeRunId || (await fetchLatestRunId());
      if (effectiveRunId && !cancelled) setRunId(effectiveRunId);
      await refreshFromSupabase(effectiveRunId);
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [user, authLoading, checkServiceStatus, refreshFromSupabase, refreshColonyRuns]);

  // ── Periodic Supabase refresh while sim is active ─────────────────────

  React.useEffect(() => {
    if (!user || simStatus === "stopped" || !runId) return;
    const interval = setInterval(() => refreshFromSupabase(runId), 5_000);
    return () => clearInterval(interval);
  }, [user, simStatus, runId, refreshFromSupabase]);

  // ── Simulation controls ───────────────────────────────────────────────

  const handleStart = async (startConfig: StartConfig) => {
    if (!user) return;
    setStarting(true);
    try {
      setProbes([]);
      setGenStats([]);
      setPrices({});
      prevPrices.current = {};

      const result = await apiCall("/api/v1/simulation/start", "POST", {
        user_id: user.id,
        mode: startConfig.mode,
        preset: startConfig.preset,
        colony_config: startConfig.colony_config,
        gen0_count: startConfig.gen0_count,
        max_capital: startConfig.max_capital,
        seed_capital: startConfig.seed_capital,
        tick_interval_ms: startConfig.tick_interval_ms,
        mutation_rate: startConfig.mutation_rate,
        max_probes: startConfig.max_probes,
      });

      const newRunId = result.run_id as string;
      setRunId(newRunId);
      setSimStatus("running");
      setSimMode(startConfig.mode);
      await refreshColonyRuns();

      const desc = startConfig.mode === "paper"
        ? "Paper trading with live Jupiter prices..."
        : "Spawning probes with simulated prices...";
      toast.success("Colony launched", { description: desc });
    } catch (e) {
      toast.error("Failed to start simulation", {
        description: e instanceof Error ? e.message : "Connection error",
      });
    } finally {
      setStarting(false);
    }
  };

  const handleStop = async () => {
    try {
      await apiCall("/api/v1/simulation/stop");
      setSimStatus("stopped");
      await Promise.all([refreshFromSupabase(runId), refreshColonyRuns()]);
      toast.success("Simulation stopped");
    } catch {
      toast.error("Failed to stop simulation");
    }
  };

  const handlePause = async () => {
    try {
      await apiCall("/api/v1/simulation/pause");
      setSimStatus("paused");
    } catch {
      toast.error("Failed to pause simulation");
    }
  };

  const handleResume = async () => {
    try {
      await apiCall("/api/v1/simulation/resume");
      setSimStatus("running");
    } catch {
      toast.error("Failed to resume simulation");
    }
  };

  const handleSelectRun = async (selectedRunId: string) => {
    setRunId(selectedRunId);
    setPrices({});
    prevPrices.current = {};
    await refreshFromSupabase(selectedRunId);
  };

  // ── Render ────────────────────────────────────────────────────────────

  if (authLoading || loading) {
    return (
      <div className="space-y-6">
        <PageHeader simStatus="stopped" mode="simulation" startedAt={null} />
        <div className="space-y-3">
          <Skeleton className="h-14 w-full bg-[#00fff5]/10" />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-20 bg-[#00fff5]/10" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="space-y-6">
        <PageHeader simStatus="stopped" mode="simulation" startedAt={null} />
        <div className="rounded-lg border border-[#00fff5]/20 bg-card/80 p-12 text-center backdrop-blur-sm">
          <p className="text-sm text-muted-foreground">
            Sign in to access the Von Neumann probe colony.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        simStatus={simStatus}
        mode={simMode}
        startedAt={systemStatus?.started_at ?? null}
      />
      <ProbesDashboard
        probes={probes}
        generationStats={genStats}
        systemStatus={systemStatus}
        connected={connected}
        simStatus={simStatus}
        mode={simMode}
        starting={starting}
        colonyRuns={colonyRuns}
        activeRunId={runId}
        prices={prices}
        onStart={handleStart}
        onStop={handleStop}
        onPause={handlePause}
        onResume={handleResume}
        onSelectRun={handleSelectRun}
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
    if (!startedAt || simStatus === "stopped") {
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

  const isActive = simStatus !== "stopped";

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
