import { parseExecutionPolicy } from "./execution";
import { createClient } from "@/lib/supabase/client";
import type { Probe, Trade, FitnessSnapshot, GenerationStats, ColonyRun } from "./types";
import { parseLifecyclePolicy, parseSearchSpec, parseEvaluationCohort, parseEvaluationPolicy, parseRiskControl } from "./transport";

function supabase() {
  return createClient();
}

export class ProbeDataError extends Error {
  constructor(operation: string) {
    super(`Could not load ${operation}. Retry when the database is available.`);
    this.name = "ProbeDataError";
  }
}

function requireRun(runId: string) {
  if (!runId?.trim()) throw new ProbeDataError("colony data without a selected colony");
}

/** Fetch a specific colony; a failed query is never reported as an empty colony. */
export async function fetchProbes(runId: string): Promise<Probe[]> {
  requireRun(runId);
  const { data, error } = await supabase()
    .from("vn_probes")
    .select("*")
    .order("fitness_score", { ascending: false })
    .eq("run_id", runId);
  if (error || !Array.isArray(data)) throw new ProbeDataError("probes");
  return data as Probe[];
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
  if (error || !Array.isArray(data)) throw new ProbeDataError("latest colony");
  if (data.length === 0) return null;
  return (data[0] as { run_id: string | null }).run_id;
}

export async function fetchProbe(id: string): Promise<Probe | null> {
  const { data, error } = await supabase()
    .from("vn_probes")
    .select("*")
    .eq("id", id)
    .maybeSingle();
  if (error) throw new ProbeDataError("probe details");
  return data as Probe | null;
}

export async function fetchProbeTrades(probeId: string): Promise<Trade[]> {
  const { data, error } = await supabase()
    .from("vn_trades")
    .select("*")
    .eq("probe_id", probeId)
    .order("opened_at", { ascending: false });
  if (error || !Array.isArray(data)) throw new ProbeDataError("trade history");
  return data as Trade[];
}

export async function fetchGenerationStats(runId: string): Promise<GenerationStats[]> {
  requireRun(runId);
  const { data, error } = await supabase()
    .from("vn_generation_stats")
    .select("*")
    .order("generation", { ascending: true })
    .eq("run_id", runId);
  if (error || !Array.isArray(data)) throw new ProbeDataError("generation statistics");
  return data as GenerationStats[];
}

export async function fetchFitnessSnapshots(
  probeId: string,
): Promise<FitnessSnapshot[]> {
  const { data, error } = await supabase()
    .from("vn_fitness_snapshots")
    .select("*")
    .eq("probe_id", probeId)
    .order("captured_at", { ascending: true });
  if (error || !Array.isArray(data)) throw new ProbeDataError("fitness history");
  return data as FitnessSnapshot[];
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
    .select("id, strategy, mode, status, config, started_at, stopped_at")
    .order("created_at", { ascending: false });

  if (colErr || !Array.isArray(colonies)) throw new ProbeDataError("colony history");
  if (colonies.length > 0) {
    return _enrichColonyRuns(colonies);
  }

  // Successful empty colony table: support history created before colony records existed.
  return _fetchColonyRunsFromProbes();
}

async function _enrichColonyRuns(
  colonies: Array<{ id: string; strategy: string; mode: string; status?: string; config?: unknown; started_at: string; stopped_at: string | null }>,
): Promise<ColonyRun[]> {
  const colonyIds = colonies.map((c) => c.id);

  const { data: probes, error } = await supabase()
    .from("vn_probes")
    .select("run_id, fitness_score")
    .in("run_id", colonyIds);
  if (error || !Array.isArray(probes)) throw new ProbeDataError("colony summary statistics");

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
    const saved = c.config && typeof c.config === "object" && "runtime" in c.config ? c.config.runtime : null;
    const record = saved && typeof saved === "object" && !Array.isArray(saved) ? saved as Record<string, unknown> : {};
    const evaluationPolicy = parseEvaluationPolicy(record.evaluation_policy);
    const runtime: ColonyRun["runtime"] = {
      search_spec: parseSearchSpec(record.search_spec ?? (c.config && typeof c.config === "object" && "search_spec" in c.config ? c.config.search_spec : undefined)),
      failure_code: typeof record.failure_code === "string" ? record.failure_code : null,
      state_persisted: typeof record.state_persisted === "boolean" ? record.state_persisted : undefined,
      open_positions: typeof record.open_positions === "number" && Number.isSafeInteger(record.open_positions) && record.open_positions >= 0 ? record.open_positions : undefined,
      requires_reconciliation: typeof record.requires_reconciliation === "boolean" ? record.requires_reconciliation : undefined,
      valuation_available: typeof record.valuation_available === "boolean" ? record.valuation_available : undefined,
      clock_basis: record.clock_basis === "synthetic_market" || record.clock_basis === "wall" ? record.clock_basis : undefined,
      market_time: typeof record.market_time === "string" && Number.isFinite(Date.parse(record.market_time)) ? record.market_time : undefined,
      market_elapsed_secs: typeof record.market_elapsed_secs === "number" && Number.isFinite(record.market_elapsed_secs) && record.market_elapsed_secs >= 0 ? record.market_elapsed_secs : undefined,
      circuit_breaker: typeof record.circuit_breaker === "boolean" ? record.circuit_breaker : undefined,
      lifecycle_policy: parseLifecyclePolicy(record.lifecycle_policy),
      execution_policy: parseExecutionPolicy(Object.hasOwn(record, "execution_policy") ? record.execution_policy : (c.config && typeof c.config === "object" && "execution_policy" in c.config ? c.config.execution_policy : undefined)),
      risk_control: parseRiskControl(record.risk_control),
      evaluation_policy: evaluationPolicy,
      cohort: evaluationPolicy ? parseEvaluationCohort(record.cohort) : undefined,
    };
    return {
      run_id: c.id,
      mode: c.mode,
      strategy: c.strategy,
      started_at: c.started_at,
      ended_at: c.stopped_at,
      probe_count: agg?.count ?? 0,
      best_fitness: agg?.best ?? 0,
      status: ["starting", "running", "paused", "risk_halted", "stopped", "failed"].includes(c.status ?? "") ? c.status : undefined,
      runtime,
    } as ColonyRun;
  });
}

async function _fetchColonyRunsFromProbes(): Promise<ColonyRun[]> {
  const { data, error } = await supabase()
    .from("vn_probes")
    .select("run_id, mode, fitness_score, created_at")
    .not("run_id", "is", null)
    .order("created_at", { ascending: false });

  if (error || !Array.isArray(data)) throw new ProbeDataError("legacy colony history");

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
  for (const [table, column] of [
    ["vn_fitness_snapshots", "captured_at"], ["vn_trades", "created_at"],
    ["vn_generation_stats", "started_at"], ["vn_probes", "created_at"],
  ]) {
    const { error } = await db.from(table).delete().gte(column, "2000-01-01");
    if (error) throw new Error("Could not finish deleting colony data. Some records may already have been removed.");
  }
  return true;
}
