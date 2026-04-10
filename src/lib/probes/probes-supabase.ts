import { createClient } from "@/lib/supabase/client";
import type { Probe, Trade, FitnessSnapshot, GenerationStats, ColonyRun } from "./types";

function supabase() {
  return createClient();
}

/**
 * Fetch probes for a specific simulation run.
 * If no runId provided, returns the most recent run's probes.
 */
export async function fetchProbes(runId?: string): Promise<Probe[]> {
  let query = supabase()
    .from("vn_probes")
    .select("*")
    .order("fitness_score", { ascending: false });

  if (runId) {
    query = query.eq("run_id", runId);
  }

  const { data, error } = await query;
  if (error) {
    console.error("fetchProbes error:", error);
    return [];
  }
  return (data ?? []) as Probe[];
}

/**
 * Fetch the most recent run_id for this user (if any simulation has been run).
 */
export async function fetchLatestRunId(): Promise<string | null> {
  const { data, error } = await supabase()
    .from("vn_probes")
    .select("run_id")
    .order("created_at", { ascending: false })
    .limit(1);
  if (error || !data || data.length === 0) return null;
  return (data[0] as { run_id: string | null }).run_id;
}

export async function fetchProbe(id: string): Promise<Probe | null> {
  const { data, error } = await supabase()
    .from("vn_probes")
    .select("*")
    .eq("id", id)
    .single();
  if (error) return null;
  return data as Probe;
}

export async function fetchProbeTrades(probeId: string): Promise<Trade[]> {
  const { data, error } = await supabase()
    .from("vn_trades")
    .select("*")
    .eq("probe_id", probeId)
    .order("opened_at", { ascending: false });
  if (error) {
    console.error("fetchProbeTrades error:", error);
    return [];
  }
  return (data ?? []) as Trade[];
}

export async function fetchGenerationStats(runId?: string): Promise<GenerationStats[]> {
  let query = supabase()
    .from("vn_generation_stats")
    .select("*")
    .order("generation", { ascending: true });

  if (runId) {
    query = query.eq("run_id", runId);
  }

  const { data, error } = await query;
  if (error) {
    console.error("fetchGenerationStats error:", error);
    return [];
  }
  return (data ?? []) as GenerationStats[];
}

export async function fetchFitnessSnapshots(
  probeId: string,
): Promise<FitnessSnapshot[]> {
  const { data, error } = await supabase()
    .from("vn_fitness_snapshots")
    .select("*")
    .eq("probe_id", probeId)
    .order("captured_at", { ascending: true });
  if (error) {
    console.error("fetchFitnessSnapshots error:", error);
    return [];
  }
  return (data ?? []) as FitnessSnapshot[];
}

/**
 * Fetch all distinct simulation runs with summary info.
 * Tries vn_colonies table first (new schema), falls back to grouping from vn_probes.
 * Returns newest first.
 */
export async function fetchColonyRuns(): Promise<ColonyRun[]> {
  // Try the new vn_colonies table first
  const { data: colonies, error: colErr } = await supabase()
    .from("vn_colonies")
    .select("id, strategy, mode, status, started_at, stopped_at")
    .order("created_at", { ascending: false });

  if (!colErr && colonies && colonies.length > 0) {
    return _enrichColonyRuns(colonies);
  }

  // Fallback: group from vn_probes (pre-migration data)
  return _fetchColonyRunsFromProbes();
}

async function _enrichColonyRuns(
  colonies: Array<{ id: string; strategy: string; mode: string; started_at: string; stopped_at: string | null }>,
): Promise<ColonyRun[]> {
  const colonyIds = colonies.map((c) => c.id);

  const { data: probes } = await supabase()
    .from("vn_probes")
    .select("run_id, fitness_score")
    .in("run_id", colonyIds);

  const probeAgg = new Map<string, { count: number; best: number }>();
  for (const p of (probes ?? []) as Array<{ run_id: string; fitness_score: number }>) {
    const existing = probeAgg.get(p.run_id);
    if (existing) {
      existing.count += 1;
      existing.best = Math.max(existing.best, p.fitness_score ?? 0);
    } else {
      probeAgg.set(p.run_id, { count: 1, best: p.fitness_score ?? 0 });
    }
  }

  return colonies.map((c) => {
    const agg = probeAgg.get(c.id);
    return {
      run_id: c.id,
      mode: c.mode,
      strategy: c.strategy,
      started_at: c.started_at,
      ended_at: c.stopped_at,
      probe_count: agg?.count ?? 0,
      best_fitness: agg?.best ?? 0,
    } as ColonyRun;
  });
}

async function _fetchColonyRunsFromProbes(): Promise<ColonyRun[]> {
  const { data, error } = await supabase()
    .from("vn_probes")
    .select("run_id, mode, fitness_score, created_at")
    .not("run_id", "is", null)
    .order("created_at", { ascending: false });

  if (error || !data) return [];

  const runs = new Map<string, ColonyRun>();
  for (const row of data as Array<{
    run_id: string;
    mode: string;
    fitness_score: number;
    created_at: string;
  }>) {
    if (!row.run_id) continue;
    const existing = runs.get(row.run_id);
    if (existing) {
      existing.probe_count += 1;
      existing.best_fitness = Math.max(existing.best_fitness, row.fitness_score ?? 0);
    } else {
      runs.set(row.run_id, {
        run_id: row.run_id,
        mode: row.mode,
        started_at: row.created_at,
        ended_at: null,
        probe_count: 1,
        best_fitness: row.fitness_score ?? 0,
      });
    }
  }

  return Array.from(runs.values());
}

export async function deleteAllProbes(): Promise<boolean> {
  const db = supabase();
  await db.from("vn_fitness_snapshots").delete().gte("captured_at", "2000-01-01");
  await db.from("vn_trades").delete().gte("created_at", "2000-01-01");
  await db.from("vn_generation_stats").delete().gte("started_at", "2000-01-01");
  await db.from("vn_probes").delete().gte("created_at", "2000-01-01");
  return true;
}
