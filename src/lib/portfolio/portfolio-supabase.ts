import { createClient } from "@/lib/supabase/client";

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

export async function fetchPortfolioAccounts(): Promise<PortfolioAccount[]> {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return [];

  const { data, error } = await supabase
    .from("portfolio_accounts")
    .select("id,user_id,name,balance,updated_at")
    .order("name", { ascending: true });

  if (error || !data) {
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

export async function fetchPortfolioTotal(): Promise<number> {
  const accounts = await fetchPortfolioAccounts();
  return accounts.reduce((sum, a) => sum + a.balance, 0);
}

export type PortfolioGoal = {
  goal: number;
  goalYear: number | null;
};

export async function fetchPortfolioGoal(): Promise<PortfolioGoal> {
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { goal: 0, goalYear: null };

  const { data, error } = await supabase
    .from("profiles")
    .select("portfolio_goal,portfolio_goal_year")
    .eq("id", user.id)
    .single();

  if (error || !data) {
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
