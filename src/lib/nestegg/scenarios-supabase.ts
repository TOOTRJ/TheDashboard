import { getNesteggDataClient as scopedClient } from "./scoped-client";
import type { NesteggInputs, NesteggScenarioId, SavedNesteggScenario } from "./types";
import { normalizeNesteggInputs } from "./constants";
import type { NesteggRequestScope } from "./session-scope";

type Row = {
  id: string;
  user_id: string;
  name: string;
  inputs: NesteggInputs;
  market_scenario: string;
  updated_at: string;
};

function rowToSaved(r: Row): SavedNesteggScenario {
  return {
    id: r.id,
    name: r.name,
    inputs: normalizeNesteggInputs(r.inputs),
    marketScenario:
      r.market_scenario === "conservative" || r.market_scenario === "aggressive"
        ? r.market_scenario
        : "base",
    updatedAt: r.updated_at,
  };
}

export async function fetchNesteggScenariosFromSupabase(scope: NesteggRequestScope): Promise<SavedNesteggScenario[]> {
  const supabase = await scopedClient(scope);
  if (!supabase) {
    if (scope.isCurrent()) throw new Error("Current Nestegg session is unavailable");
    return [];
  }
  const { data, error } = await supabase.from("nestegg_scenarios")
    .select("id,user_id,name,inputs,market_scenario,updated_at")
    .eq("user_id", scope.ownerId).order("updated_at", { ascending: false });
  if (!scope.isCurrent()) return [];
  if (error || !data || (data as Row[]).some(row => row.user_id !== scope.ownerId)) {
    throw new Error("Saved Nestegg plans are unavailable");
  }
  return (data as Row[]).map(rowToSaved);
}

export async function insertNesteggScenarioToSupabase(
  name: string, inputs: NesteggInputs, marketScenario: NesteggScenarioId,
  scope: NesteggRequestScope
): Promise<SavedNesteggScenario | null> {
  const supabase = await scopedClient(scope);
  if (!supabase) return null;
  const { data, error } = await supabase.from("nestegg_scenarios").insert({
    user_id: scope.ownerId, name: name.trim() || "Untitled",
    inputs: normalizeNesteggInputs(inputs) as unknown as Record<string, unknown>,
    market_scenario: marketScenario, updated_at: new Date().toISOString(),
  }).select("id,user_id,name,inputs,market_scenario,updated_at").single();
  if (!scope.isCurrent() || error || !data || data.user_id !== scope.ownerId) return null;
  return rowToSaved(data as Row);
}

export async function deleteNesteggScenarioFromSupabase(id: string, scope: NesteggRequestScope): Promise<boolean> {
  const supabase = await scopedClient(scope);
  if (!supabase) return false;
  const { error } = await supabase.from("nestegg_scenarios").delete()
    .eq("id", id).eq("user_id", scope.ownerId);
  return scope.isCurrent() && !error;
}

export async function updateNesteggScenarioInSupabase(
  id: string, inputs: NesteggInputs, marketScenario: NesteggScenarioId,
  options: { name?: string } | undefined, scope: NesteggRequestScope
): Promise<SavedNesteggScenario | null> {
  const supabase = await scopedClient(scope);
  if (!supabase) return null;
  const payload: Record<string, unknown> = {
    inputs: normalizeNesteggInputs(inputs) as unknown as Record<string, unknown>,
    market_scenario: marketScenario, updated_at: new Date().toISOString(),
  };
  if (options?.name !== undefined) payload.name = options.name.trim() || "Untitled";
  const { data, error } = await supabase.from("nestegg_scenarios").update(payload)
    .eq("id", id).eq("user_id", scope.ownerId)
    .select("id,user_id,name,inputs,market_scenario,updated_at").single();
  if (!scope.isCurrent() || error || !data || data.user_id !== scope.ownerId) return null;
  return rowToSaved(data as Row);
}

export async function updateNesteggScenarioNameInSupabase(
  id: string, name: string, scope: NesteggRequestScope
): Promise<SavedNesteggScenario | null> {
  const supabase = await scopedClient(scope);
  if (!supabase) return null;
  const { data, error } = await supabase.from("nestegg_scenarios")
    .update({ name: name.trim() || "Untitled", updated_at: new Date().toISOString() })
    .eq("id", id).eq("user_id", scope.ownerId)
    .select("id,user_id,name,inputs,market_scenario,updated_at").single();
  if (!scope.isCurrent() || error || !data || data.user_id !== scope.ownerId) return null;
  return rowToSaved(data as Row);
}
