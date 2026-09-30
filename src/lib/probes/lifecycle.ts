import type { Probe, ProbeState } from "./types";

/** Preserve complete terminal metrics and ancestry from worker events. */
export function mapProbeEvent(data: Record<string, unknown>, timestamp?: string): Partial<Probe> {
  const result: Partial<Probe> = {};
  const strings = { probe_id: "id", probe_name: "probe_name", born_at: "born_at", mode: "mode" } as const;
  for (const [source, target] of Object.entries(strings)) {
    if (typeof data[source] === "string") Object.assign(result, { [target]: data[source] });
  }
  const states: ProbeState[] = ["BORN", "FUNDED", "OBSERVING", "TRADING", "REPRODUCING", "DYING", "DEAD"];
  if (states.includes(data.state as ProbeState)) result.state = data.state as ProbeState;
  const numbers = ["generation", "initial_capital", "current_capital", "peak_capital", "total_trades", "winning_trades", "total_pnl", "fitness_score"] as const;
  for (const name of numbers) if (typeof data[name] === "number" && Number.isFinite(data[name])) result[name] = data[name];
  if (typeof data.max_drawdown_pct === "number" && Number.isFinite(data.max_drawdown_pct)) result.max_drawdown = data.max_drawdown_pct / 100;
  if (data.sharpe_ratio !== undefined) result.sharpe_ratio = typeof data.sharpe_ratio === "number" && Number.isFinite(data.sharpe_ratio) ? data.sharpe_ratio : null;
  if (data.metrics !== undefined) result.metrics = data.metrics && typeof data.metrics === "object" && !Array.isArray(data.metrics) ? data.metrics as Probe["metrics"] : null;
  if (data.genome && typeof data.genome === "object" && !Array.isArray(data.genome)) result.genome = data.genome as Probe["genome"];
  for (const name of ["died_at", "death_reason"] as const) if (data[name] === null || typeof data[name] === "string") result[name] = data[name];
  const rawParents = probeParentIds({ id: result.id, parent_ids: data.parent_ids, genome: result.genome, parent_id: data.parent_id } as Probe);
  if (data.parent_ids !== undefined || data.parent_id !== undefined || result.genome?.parent_ids !== undefined) {
    result.parent_ids = [...new Set(rawParents as string[])];
    result.parent_id = result.parent_ids[0] ?? null;
  }
  if (timestamp && Number.isFinite(Date.parse(timestamp))) result.updated_at = timestamp;
  return result;
}

export function probeParentIds(probe: Probe): string[] {
  for (const source of [probe.parent_ids, probe.genome?.parent_ids, [probe.parent_id]]) {
    if (!Array.isArray(source)) continue;
    const ids = [...new Set(source.filter((id): id is string => typeof id === "string" && id.length > 0 && id !== probe.id))];
    if (ids.length > 0) return ids;
  }
  return [];
}

/** An intent is not a terminal acknowledgement; a terminal probe stays terminal. */
export function applyProbeEvent(probe: Probe, type: string, data: Record<string, unknown>, timestamp?: string): Probe {
  if (data.probe_id !== probe.id) return probe;
  if (probe.state === "DEAD" && type !== "probe_dead") return probe;
  const update = mapProbeEvent(data, timestamp);
  if (type !== "probe_dead") {
    delete update.died_at;
    delete update.death_reason;
    if (update.state === "DEAD") delete update.state;
  }
  if (type === "probe_reproducing") update.state = "REPRODUCING";
  if (type === "probe_dying") update.state = "DYING";
  if (type === "probe_dead") {
    update.state = "DEAD";
    update.died_at = typeof data.died_at === "string" ? data.died_at : timestamp ?? probe.died_at;
    update.death_reason = typeof data.death_reason === "string" ? data.death_reason : typeof data.reason === "string" ? data.reason : probe.death_reason;
  }
  if (update.genome) update.genome = { ...probe.genome, ...update.genome };
  if (update.metrics) update.metrics = { ...probe.metrics, ...update.metrics };
  return { ...probe, ...update };
}

/** A new card needs a complete birth snapshot; sparse updates cannot invent one. */
export function probeFromBirth(data: Record<string, unknown>, timestamp?: string): Probe | null {
  const mapped = mapProbeEvent(data, timestamp);
  const requiredNumbers = ["generation", "initial_capital", "current_capital", "peak_capital",
    "total_trades", "winning_trades", "total_pnl", "max_drawdown", "fitness_score"] as const;
  if (!mapped.id || !mapped.probe_name || !mapped.state || mapped.state === "DEAD" ||
      !mapped.born_at || !Number.isFinite(Date.parse(mapped.born_at)) || !mapped.mode ||
      !mapped.genome || requiredNumbers.some(name => typeof mapped[name] !== "number")) return null;
  return {
    ...mapped,
    parent_ids: mapped.parent_ids ?? [], parent_id: mapped.parent_id ?? null,
    sharpe_ratio: mapped.sharpe_ratio ?? null,
    died_at: null, death_reason: null,
    created_at: mapped.born_at, updated_at: mapped.updated_at ?? mapped.born_at,
  } as Probe;
}
