import { createClient } from "@/lib/supabase/client";
import type { NesteggInputs, NesteggScenarioId, SavedNesteggScenario } from "./types";
import { normalizeNesteggInputs } from "./constants";

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

export async function fetchNesteggScenariosFromSupabase(): Promise<SavedNesteggScenario[]> {
  const supabase = createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return [];

  const { data, error } = await supabase
    .from("nestegg_scenarios")
    .select("id,user_id,name,inputs,market_scenario,updated_at")
    .order("updated_at", { ascending: false });

  if (error || !data) {
    console.warn("nestegg_scenarios fetch:", error?.message ?? "no data");
    return [];
  }

  return (data as Row[]).map(rowToSaved);
}

export async function insertNesteggScenarioToSupabase(
  name: string,
  inputs: NesteggInputs,
  marketScenario: NesteggScenarioId
): Promise<SavedNesteggScenario | null> {
  const supabase = createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;

  const payload = {
    user_id: user.id,
    name: name.trim() || "Untitled",
    inputs: normalizeNesteggInputs(inputs) as unknown as Record<string, unknown>,
    market_scenario: marketScenario,
    updated_at: new Date().toISOString(),
  };

  const { data, error } = await supabase
    .from("nestegg_scenarios")
    .insert(payload)
    .select("id,user_id,name,inputs,market_scenario,updated_at")
    .single();

  if (error || !data) {
    console.warn("nestegg_scenarios insert:", error?.message);
    return null;
  }
  return rowToSaved(data as Row);
}

export async function deleteNesteggScenarioFromSupabase(id: string): Promise<boolean> {
  const supabase = createClient();
  const { error } = await supabase.from("nestegg_scenarios").delete().eq("id", id);
  if (error) {
    console.warn("nestegg_scenarios delete:", error.message);
    return false;
  }
  return true;
}

export async function updateNesteggScenarioInSupabase(
  id: string,
  inputs: NesteggInputs,
  marketScenario: NesteggScenarioId,
  options?: { name?: string }
): Promise<SavedNesteggScenario | null> {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const normalized = normalizeNesteggInputs(inputs) as unknown as Record<string, unknown>;
  const payload: Record<string, unknown> = {
    inputs: normalized,
    market_scenario: marketScenario,
    updated_at: new Date().toISOString(),
  };
  if (options?.name !== undefined) {
    payload.name = options.name.trim() || "Untitled";
  }

  const { data, error } = await supabase
    .from("nestegg_scenarios")
    .update(payload)
    .eq("id", id)
    .eq("user_id", user.id)
    .select("id,user_id,name,inputs,market_scenario,updated_at")
    .single();

  if (error || !data) {
    console.warn("nestegg_scenarios update:", error?.message);
    return null;
  }
  return rowToSaved(data as Row);
}

export async function updateNesteggScenarioNameInSupabase(
  id: string,
  name: string
): Promise<SavedNesteggScenario | null> {
  const supabase = createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;

  const { data, error } = await supabase
    .from("nestegg_scenarios")
    .update({
      name: name.trim() || "Untitled",
      updated_at: new Date().toISOString(),
    })
    .eq("id", id)
    .select("id,user_id,name,inputs,market_scenario,updated_at")
    .single();

  if (error || !data) {
    console.warn("nestegg_scenarios update:", error?.message);
    return null;
  }
  return rowToSaved(data as Row);
}
