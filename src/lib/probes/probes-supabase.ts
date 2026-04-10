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
 * Returns newest first.
 */
export async function fetchColonyRuns(): Promise<ColonyRun[]> {
  const { data, error } = await supabase()
    .from("vn_probes")
    .select("run_id, mode, born_at, updated_at, fitness_score")
    .not("run_id", "is", null)
    .order("born_at", { ascending: false });

  if (error || !data) {
    console.error("fetchColonyRuns error:", error);
    return [];
  }

  // Group by run_id and compute aggregates
  const runsMap = new Map<string, ColonyRun>();
  for (const row of data as Array<{
    run_id: string;
    mode: string;
    born_at: string;
    updated_at: string;
    fitness_score: number;
  }>) {
    if (!row.run_id) continue;
    const existing = runsMap.get(row.run_id);
    if (existing) {
      existing.probe_count += 1;
      existing.best_fitness = Math.max(existing.best_fitness, row.fitness_score);
      // Track latest activity as ended_at
      if (row.updated_at > (existing.ended_at ?? "")) {
        existing.ended_at = row.updated_at;
      }
    } else {
      runsMap.set(row.run_id, {
        run_id: row.run_id,
        mode: row.mode,
        started_at: row.born_at,
        ended_at: row.updated_at,
        probe_count: 1,
        best_fitness: row.fitness_score,
      });
    }
  }

  return Array.from(runsMap.values()).sort(
    (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  );
}

export async function deleteAllProbes(): Promise<boolean> {
  const db = supabase();
  await db.from("vn_fitness_snapshots").delete().gte("captured_at", "2000-01-01");
  await db.from("vn_trades").delete().gte("created_at", "2000-01-01");
  await db.from("vn_generation_stats").delete().gte("started_at", "2000-01-01");
  await db.from("vn_probes").delete().gte("created_at", "2000-01-01");
  return true;
}
