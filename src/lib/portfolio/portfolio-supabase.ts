import { createClient } from "@/lib/supabase/client";
import { getNesteggDataClient } from "@/lib/nestegg/scoped-client";
import type { NesteggRequestScope } from "@/lib/nestegg/session-scope";

export type PortfolioAccount = {
  id: string;
  name: string;
  balance: number;
  updatedAt: string;
};

type Row = {
  id: string;
  user_id: string;
  name: string;
  balance: number | string;
  updated_at: string;
};

function numericValue(value: unknown): number | null {
  if (typeof value !== "number" && (typeof value !== "string"
    || !/^[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/.test(value.trim()))) return null;
  const result = Number(value);
  return Number.isFinite(result) ? result : null;
}

function goalValue(value: { portfolio_goal: unknown; portfolio_goal_year: unknown }): PortfolioGoal | null {
  const amount = numericValue(value.portfolio_goal);
  const year = value.portfolio_goal_year === null ? null : numericValue(value.portfolio_goal_year);
  if (amount === null || amount < 0 || value.portfolio_goal_year !== null && (year === null || !Number.isSafeInteger(year))) return null;
  return { goal: amount, goalYear: year };
}

function validAccount(r: Row, ownerId: string, id?: string): boolean {
  const balance = r && numericValue(r.balance);
  return !!r && typeof r.id === "string" && r.id.length > 0 && (id === undefined || r.id === id)
    && r.user_id === ownerId && typeof r.name === "string"
    && typeof r.updated_at === "string" && r.updated_at.length > 0
    && balance !== null && balance >= 0;
}

function rowToAccount(r: Row): PortfolioAccount {
  return {
    id: r.id,
    name: r.name,
    balance: Number(r.balance),
    updatedAt: r.updated_at,
  };
}

async function portfolioReadClient(scope?: NesteggRequestScope) {
  if (scope) {
    const client = await getNesteggDataClient(scope);
    return client ? { client, ownerId: scope.ownerId } : null;
  }
  const client = createClient();
  const { data: { user } } = await client.auth.getUser();
  return user ? { client, ownerId: user.id } : null;
}

export async function fetchPortfolioAccounts(scope?: NesteggRequestScope): Promise<PortfolioAccount[]> {
  if (scope && !scope.isCurrent()) return [];
  const access = await portfolioReadClient(scope);
  if (!access) {
    if (scope?.isCurrent()) throw new Error("Current portfolio session is unavailable");
    return [];
  }
  const { client: supabase, ownerId } = access;

  const { data, error } = await supabase
    .from("portfolio_accounts")
    .select("id,user_id,name,balance,updated_at")
    .eq("user_id", ownerId)
    .order("name", { ascending: true });

  if (scope && !scope.isCurrent()) return [];
  if (error || !Array.isArray(data) || (data as Row[]).some(row => !validAccount(row, ownerId))) {
    if (scope) throw new Error("Portfolio accounts are unavailable");
    console.warn("portfolio_accounts fetch:", error?.message ?? "no data");
    return [];
  }

  return (data as Row[]).map(rowToAccount);
}

export async function insertPortfolioAccount(
  name: string,
  balance: number,
  scope: NesteggRequestScope
): Promise<PortfolioAccount | null> {
  if (!Number.isFinite(balance) || balance < 0) return null;
  const supabase = await getNesteggDataClient(scope);
  if (!supabase || !scope.isCurrent()) return null;

  const { data, error } = await supabase
    .from("portfolio_accounts")
    .insert({
      user_id: scope.ownerId,
      name: name.trim() || "Untitled",
      balance,
      updated_at: new Date().toISOString(),
    })
    .select("id,user_id,name,balance,updated_at")
    .single();

  if (!scope.isCurrent() || error || !data || !validAccount(data as Row, scope.ownerId)) {
    return null;
  }

  return rowToAccount(data as Row);
}

export async function updatePortfolioAccount(
  id: string,
  fields: { name?: string; balance?: number },
  scope: NesteggRequestScope
): Promise<PortfolioAccount | null> {
  if (fields.balance !== undefined && (!Number.isFinite(fields.balance) || fields.balance < 0)) return null;
  const supabase = await getNesteggDataClient(scope);
  if (!supabase || !scope.isCurrent()) return null;

  const payload: Record<string, unknown> = {
    updated_at: new Date().toISOString(),
  };
  if (fields.name !== undefined) payload.name = fields.name.trim() || "Untitled";
  if (fields.balance !== undefined) payload.balance = fields.balance;

  const { data, error } = await supabase
    .from("portfolio_accounts")
    .update(payload)
    .eq("id", id)
    .eq("user_id", scope.ownerId)
    .select("id,user_id,name,balance,updated_at")
    .single();

  if (!scope.isCurrent() || error || !data || !validAccount(data as Row, scope.ownerId, id)) {
    return null;
  }

  return rowToAccount(data as Row);
}

export async function deletePortfolioAccount(id: string, scope: NesteggRequestScope): Promise<boolean> {
  const supabase = await getNesteggDataClient(scope);
  if (!supabase || !scope.isCurrent()) return false;
  const { data, error } = await supabase
    .from("portfolio_accounts")
    .delete()
    .eq("id", id).eq("user_id", scope.ownerId)
    .select("id,user_id").single();
  return scope.isCurrent() && !error && !!data && data.id === id && data.user_id === scope.ownerId;
}

export async function fetchPortfolioTotal(scope?: NesteggRequestScope): Promise<number> {
  const accounts = await fetchPortfolioAccounts(scope);
  return accounts.reduce((sum, a) => sum + a.balance, 0);
}

export type PortfolioGoal = {
  goal: number;
  goalYear: number | null;
};

export async function fetchPortfolioGoal(scope?: NesteggRequestScope): Promise<PortfolioGoal> {
  if (scope && !scope.isCurrent()) return { goal: 0, goalYear: null };
  const access = await portfolioReadClient(scope);
  if (!access) {
    if (scope?.isCurrent()) throw new Error("Current portfolio session is unavailable");
    return { goal: 0, goalYear: null };
  }
  const { client: supabase, ownerId } = access;

  const { data, error } = await supabase
    .from("profiles")
    .select("portfolio_goal,portfolio_goal_year")
    .eq("id", ownerId)
    .maybeSingle();

  if (scope && !scope.isCurrent()) return { goal: 0, goalYear: null };
  if (error || data === null) {
    if (scope && error) throw new Error("Portfolio goal is unavailable");
    if (!scope) console.warn("portfolio goal fetch:", error?.message ?? "no data");
    return { goal: 0, goalYear: null };
  }

  if (typeof data !== "object" || Array.isArray(data)) throw new Error("Portfolio goal is unavailable");
  const goal = goalValue(data);
  if (!goal) throw new Error("Portfolio goal is unavailable");
  return goal;
}

export async function updatePortfolioGoal(
  goal: number,
  goalYear: number | null,
  scope: NesteggRequestScope
): Promise<boolean> {
  if (!Number.isFinite(goal) || goal < 0 || (goalYear !== null && !Number.isSafeInteger(goalYear))) return false;
  const supabase = await getNesteggDataClient(scope);
  if (!supabase || !scope.isCurrent()) return false;

  const { data, error } = await supabase
    .from("profiles")
    .update({
      portfolio_goal: goal,
      portfolio_goal_year: goalYear,
    })
    .eq("id", scope.ownerId)
    .select("id,portfolio_goal,portfolio_goal_year").single();
  if (!scope.isCurrent() || error || !data || data.id !== scope.ownerId) return false;
  const saved = goalValue(data);
  return !!saved && saved.goal === goal && saved.goalYear === goalYear;
}
