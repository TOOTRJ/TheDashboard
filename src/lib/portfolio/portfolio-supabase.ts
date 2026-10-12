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
  balance: number;
  updated_at: string;
};

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
  if (error || !data || (data as Row[]).some(row => row.user_id !== ownerId)) {
    if (scope) throw new Error("Portfolio accounts are unavailable");
    console.warn("portfolio_accounts fetch:", error?.message ?? "no data");
    return [];
  }

  return (data as Row[]).map(rowToAccount);
}

export async function insertPortfolioAccount(
  name: string,
  balance: number
): Promise<PortfolioAccount | null> {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const { data, error } = await supabase
    .from("portfolio_accounts")
    .insert({
      user_id: user.id,
      name: name.trim() || "Untitled",
      balance,
      updated_at: new Date().toISOString(),
    })
    .select("id,user_id,name,balance,updated_at")
    .single();

  if (error || !data) {
    console.warn("portfolio_accounts insert:", error?.message);
    return null;
  }

  return rowToAccount(data as Row);
}

export async function updatePortfolioAccount(
  id: string,
  fields: { name?: string; balance?: number }
): Promise<PortfolioAccount | null> {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const payload: Record<string, unknown> = {
    updated_at: new Date().toISOString(),
  };
  if (fields.name !== undefined) payload.name = fields.name.trim() || "Untitled";
  if (fields.balance !== undefined) payload.balance = fields.balance;

  const { data, error } = await supabase
    .from("portfolio_accounts")
    .update(payload)
    .eq("id", id)
    .eq("user_id", user.id)
    .select("id,user_id,name,balance,updated_at")
    .single();

  if (error || !data) {
    console.warn("portfolio_accounts update:", error?.message);
    return null;
  }

  return rowToAccount(data as Row);
}

export async function deletePortfolioAccount(id: string): Promise<boolean> {
  const supabase = createClient();
  const { error } = await supabase
    .from("portfolio_accounts")
    .delete()
    .eq("id", id);

  if (error) {
    console.warn("portfolio_accounts delete:", error.message);
    return false;
  }
  return true;
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
  if (error || !data) {
    if (scope && error) throw new Error("Portfolio goal is unavailable");
    console.warn("portfolio goal fetch:", error?.message ?? "no data");
    return { goal: 0, goalYear: null };
  }

  return {
    goal: Number(data.portfolio_goal) || 0,
    goalYear: data.portfolio_goal_year != null ? Number(data.portfolio_goal_year) : null,
  };
}

export async function updatePortfolioGoal(
  goal: number,
  goalYear: number | null
): Promise<boolean> {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return false;

  const { error } = await supabase
    .from("profiles")
    .update({
      portfolio_goal: Math.max(0, goal),
      portfolio_goal_year: goalYear,
    })
    .eq("id", user.id);

  if (error) {
    console.warn("portfolio goal update:", error.message);
    return false;
  }
  return true;
}
