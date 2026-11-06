import { parseExecutionPolicy } from "./execution";
import { savedSignalPolicy } from "./signal-profile";
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

/** Complete bounded trade scan. Separate pages are not a database snapshot:
 * detected count/identity drift refuses; same-count edits need a versioned reader.
 */
export async function fetchProbeTrades(probeId: string, signal?: AbortSignal): Promise<Trade[]> {
  if (!historyString(probeId)) throw new ProbeDataError("trade history without a selected probe");
  const abort = new AbortController();
  const cancel = () => abort.abort();
  signal?.addEventListener("abort", cancel, { once: true });
  if (signal?.aborted) cancel();
  const timer = setTimeout(cancel, HISTORY_TIMEOUT_MS);
  try {
    const db = supabase();
    const rows: Trade[] = [];
    const ids = new Set<string>();
    let expectedCount: number | undefined;
    for (let page = 0; page < HISTORY_MAX_PAGES; page++) {
      if (abort.signal.aborted) throw new ProbeDataError("trade history");
      const { data, error, count } = await db.from("vn_trades")
        .select("*", { count: "exact" }).eq("probe_id", probeId)
        .order("opened_at", { ascending: false }).order("id", { ascending: true })
        .range(rows.length, rows.length + HISTORY_PAGE_SIZE - 1).abortSignal(abort.signal);
      if (abort.signal.aborted || error || !Array.isArray(data)
        || typeof count !== "number" || !Number.isSafeInteger(count) || count < 0
        || count > HISTORY_MAX_ROWS || data.length > HISTORY_PAGE_SIZE
        || (expectedCount !== undefined && count !== expectedCount)
        || rows.length + data.length > count) throw new ProbeDataError("trade history");
      expectedCount = count;
      for (const value of data as unknown[]) {
        if (!value || typeof value !== "object" || Array.isArray(value)) throw new ProbeDataError("trade history");
        const row = value as Record<string, unknown>;
        if (!historyString(row.id) || row.probe_id !== probeId || ids.has(row.id)
          || !historyDate(row.opened_at)) throw new ProbeDataError("trade history");
        ids.add(row.id);
        rows.push(row as unknown as Trade);
      }
      if (rows.length === expectedCount) return rows;
      if (data.length === 0) throw new ProbeDataError("trade history");
    }
    throw new ProbeDataError("trade history");
  } catch (error) {
    if (error instanceof ProbeDataError) throw error;
    throw new ProbeDataError("trade history");
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
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

// A complete bounded scan is required before publishing any history. These are
// read limits, not database/provider settings. Counts apply after owner filtering.
const HISTORY_PAGE_SIZE = 200;
const HISTORY_MAX_ROWS = 50_000;
const HISTORY_MAX_PAGES = 500;
const HISTORY_TIMEOUT_MS = 8_000;

type HistoryRow = { id: string; user_id: string };
type SavedColony = HistoryRow & {
  strategy: string; mode: string; status?: string; config?: unknown;
  started_at: string; stopped_at: string | null;
};
type SavedProbe = HistoryRow & {
  run_id: string | null; mode: string; fitness_score: number; created_at: string;
};

function historyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}
function historyDate(value: unknown): value is string {
  return historyString(value) && Number.isFinite(Date.parse(value));
}

async function readHistoryPages<T extends HistoryRow>(
  db: ReturnType<typeof supabase>, table: "vn_colonies" | "vn_probes", fields: string,
  ownerId: string, signal: AbortSignal, operation: string,
): Promise<T[]> {
  const rows: T[] = [];
  let expectedCount: number | undefined;
  let previousId: string | undefined;
  for (let page = 0; page < HISTORY_MAX_PAGES; page++) {
    if (signal.aborted) throw new ProbeDataError(operation);
    const { data, error, count } = await db.from(table)
      .select(fields, { count: "exact" }).eq("user_id", ownerId)
      .order("id", { ascending: true })
      .range(rows.length, rows.length + HISTORY_PAGE_SIZE - 1).abortSignal(signal);
    if (signal.aborted || error || !Array.isArray(data)
      || typeof count !== "number" || !Number.isSafeInteger(count) || count < 0
      || count > HISTORY_MAX_ROWS || data.length > HISTORY_PAGE_SIZE
      || (expectedCount !== undefined && count !== expectedCount)
      || rows.length + data.length > count) throw new ProbeDataError(operation);
    expectedCount = count;
    for (const value of data as unknown[]) {
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new ProbeDataError(operation);
      const row = value as Record<string, unknown>;
      // Exact ID order detects overlapping/repeated pages; never count them twice
      // or silently deduplicate a changing/partial result into a successful scan.
      if (!row || !historyString(row.id) || row.user_id !== ownerId
        || (previousId !== undefined && row.id <= previousId)) throw new ProbeDataError(operation);
      previousId = row.id;
      rows.push(row as unknown as T);
    }
    if (rows.length === expectedCount) return rows;
    if (data.length === 0) throw new ProbeDataError(operation);
    // A server row cap may be smaller than the requested page. Advance by the
    // actual rows and continue until the exact count, not until a short page.
  }
  throw new ProbeDataError(operation);
}

/** Merge owner-visible colony and probe-only runs, newest first.
 * Separate page requests are not a repeatable-read database snapshot. Detected
 * count/order drift fails the scan; same-count concurrent edits need the future
 * versioned server projections. No historical colony authority is manufactured.
 */
export async function fetchColonyRuns(ownerId: string, signal?: AbortSignal): Promise<ColonyRun[]> {
  if (!historyString(ownerId)) throw new ProbeDataError("colony history without an authenticated owner");
  const abort = new AbortController();
  const cancel = () => abort.abort();
  signal?.addEventListener("abort", cancel, { once: true });
  if (signal?.aborted) cancel();
  const timer = setTimeout(cancel, HISTORY_TIMEOUT_MS);
  try {
    const db = supabase();
    const colonies = await readHistoryPages<SavedColony>(db, "vn_colonies",
      "id, user_id, strategy, mode, status, config, started_at, stopped_at", ownerId, abort.signal, "colony history");
    const probes = await readHistoryPages<SavedProbe>(db, "vn_probes",
      "id, user_id, run_id, mode, fitness_score, created_at", ownerId, abort.signal, "colony summary statistics");
    if (abort.signal.aborted) throw new ProbeDataError("colony history");
    return mergeColonyRuns(colonies, probes);
  } catch (error) {
    if (error instanceof ProbeDataError) throw error;
    throw new ProbeDataError("colony history");
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}

function mergeColonyRuns(colonies: SavedColony[], probes: SavedProbe[]): ColonyRun[] {
  const probeAgg = new Map<string, { count: number; best: number; first: string; mode: string }>();
  for (const p of probes) {
    if ((p.run_id !== null && !historyString(p.run_id)) || !historyDate(p.created_at)
      || !historyString(p.mode) || typeof p.fitness_score !== "number" || !Number.isFinite(p.fitness_score)) {
      throw new ProbeDataError("colony summary statistics");
    }
    // Rows without a run are not assigned a fabricated identity.
    if (p.run_id === null) continue;
    const existing = probeAgg.get(p.run_id);
    if (existing) {
      existing.count += 1;
      existing.best = Math.max(existing.best, p.fitness_score);
      if (Date.parse(p.created_at) < Date.parse(existing.first)) existing.first = p.created_at;
      if (existing.mode !== p.mode) existing.mode = "unknown";
    } else {
      probeAgg.set(p.run_id, { count: 1, best: p.fitness_score, first: p.created_at, mode: p.mode });
    }
  }

  const runs: ColonyRun[] = colonies.map((c) => {
    if (!historyDate(c.started_at) || (c.stopped_at !== null && !historyDate(c.stopped_at))
      || !historyString(c.mode) || !historyString(c.strategy)) throw new ProbeDataError("colony history");
    const agg = probeAgg.get(c.id);
    probeAgg.delete(c.id);
    const saved = c.config && typeof c.config === "object" && "runtime" in c.config ? c.config.runtime : null;
    const record = saved && typeof saved === "object" && !Array.isArray(saved) ? saved as Record<string, unknown> : {};
    const evaluationPolicy = parseEvaluationPolicy(record.evaluation_policy);
    const runtime: ColonyRun["runtime"] = {
      signal_policy: savedSignalPolicy(c.config),
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
      history_source: "colony",
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
  for (const [runId, agg] of probeAgg) {
    runs.push({
      run_id: runId, history_source: "probe_only", mode: agg.mode,
      started_at: agg.first, ended_at: null, probe_count: agg.count, best_fitness: agg.best,
    });
  }
  return runs.sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at)
    || (a.run_id < b.run_id ? -1 : a.run_id > b.run_id ? 1 : 0));
}
