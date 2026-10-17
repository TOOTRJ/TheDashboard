"use client";

import * as React from "react";
import { toast, type ExternalToast } from "sonner";
import Link from "next/link";
import { ArrowRight, Pencil, Plus, Save, Target, Trash2, Wallet, X } from "lucide-react";

import { useAuth } from "@/components/auth/AuthProvider";
import { sessionIdentity } from "@/lib/auth/session-guard";
import { createNesteggWorkspaceScope, type NesteggRequestScope } from "@/lib/nestegg/session-scope";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency } from "@/lib/formatters";
import {
  fetchPortfolioAccounts,
  insertPortfolioAccount,
  updatePortfolioAccount,
  deletePortfolioAccount,
  fetchPortfolioGoal,
  updatePortfolioGoal,
  type PortfolioAccount,
} from "@/lib/portfolio/portfolio-supabase";
import { computeRequiredMonthlySavings } from "@/lib/nestegg/future-value";

export default function PortfolioPage() {
  const { user, session, loading } = useAuth();
  const ownerId = user?.id ?? null;
  const identity = sessionIdentity(session?.access_token);
  const boundary = React.useMemo(() => ownerId && identity ? {
    key: crypto.randomUUID(), scope: createNesteggWorkspaceScope(ownerId, identity),
  } : null, [ownerId, identity]);
  if (loading) return <p role="status">Checking your Portfolio session…</p>;
  if (!boundary || !user || !session || session.user.id !== user.id) {
    return <p role="status">Sign in to manage your portfolio accounts.</p>;
  }
  return <PortfolioWorkspace key={boundary.key} workspaceScope={boundary.scope} />;
}

export function PortfolioWorkspace({ workspaceScope }: {
  workspaceScope: ReturnType<typeof createNesteggWorkspaceScope>;
}) {
  const [accounts, setAccounts] = React.useState<PortfolioAccount[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState(false);
  const [readAttempt, setReadAttempt] = React.useState(0);
  const [newName, setNewName] = React.useState("");
  const [newBalance, setNewBalance] = React.useState("");
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editName, setEditName] = React.useState("");
  const [editBalance, setEditBalance] = React.useState("");
  const [goalAmount, setGoalAmount] = React.useState("");
  const [goalYear, setGoalYear] = React.useState("");
  const [goalSaved, setGoalSaved] = React.useState({ amount: 0, year: null as number | null });
  const [pending, setPending] = React.useState<string | null>(null);
  const mutationActive = React.useRef<NesteggRequestScope | null>(null);
  const goalRevision = React.useRef(0);
  const ownedToasts = React.useRef(new Set<string>());
  const adding = pending === "add";
  const saving = pending === "edit";
  const savingGoal = pending === "goal" || pending === "undo";
  const busy = pending !== null;

  const notify = (kind: "success" | "error", message: string, options?: ExternalToast) => {
    if (!workspaceScope.isCurrent()) return;
    const ids = ownedToasts.current;
    while (ids.size >= 8) {
      const oldest = ids.values().next().value!;
      ids.delete(oldest); toast.dismiss(oldest);
    }
    const id = crypto.randomUUID(); ids.add(id);
    toast[kind](message, { ...options, id,
      onDismiss: () => ids.delete(id), onAutoClose: () => ids.delete(id),
    });
  };

  React.useLayoutEffect(() => {
    const ids = ownedToasts.current;
    workspaceScope.activate();
    mutationActive.current = null;
    setPending(null);
    return () => {
      workspaceScope.dispose();
      for (const id of ids) toast.dismiss(id);
      ids.clear();
    };
  }, [workspaceScope]);

  const total = accounts.reduce((sum, a) => sum + a.balance, 0);
  const goalDirty =
    Number(goalAmount) !== goalSaved.amount ||
    (goalYear ? Number(goalYear) : null) !== goalSaved.year;

  React.useEffect(() => {
    const request = workspaceScope.capture();
    let cancelled = false;
    const current = () => !cancelled && request.isCurrent();
    setLoading(true); setLoadError(false);
    void (async () => {
      try {
        const [rows, goal] = await Promise.all([
          fetchPortfolioAccounts(request), fetchPortfolioGoal(request),
        ]);
        if (!current()) return;
        setAccounts(rows);
        setGoalAmount(goal.goal > 0 ? String(goal.goal) : "");
        setGoalYear(goal.goalYear != null ? String(goal.goalYear) : "");
        setGoalSaved({ amount: goal.goal, year: goal.goalYear });
      } catch {
        if (current()) setLoadError(true);
      } finally {
        if (current()) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [workspaceScope, readAttempt]);

  // Serialize this workspace's mutations, including double clicks before React
  // paints pending state. A retired workspace can finish a server write, but it
  // cannot publish into a replacement login or issue a retained Undo.
  const mutate = async (kind: string, action: (request: NesteggRequestScope) => Promise<void>) => {
    const request = workspaceScope.capture();
    if (!request.isCurrent() || mutationActive.current) return;
    mutationActive.current = request; setPending(kind);
    try { await action(request); }
    catch {
      if (request.isCurrent()) notify("error", kind === "undo" ? "Could not revert goal" : "Could not save portfolio change");
    } finally {
      if (mutationActive.current === request) {
        mutationActive.current = null;
        if (request.isCurrent()) setPending(null);
      }
    }
  };

  const handleSaveGoal = () => mutate("goal", async (request) => {
    const prev = { ...goalSaved };
    const amount = goalAmount === "" ? 0 : Number(goalAmount);
    const year = goalYear === "" ? null : Number(goalYear);
    const revision = ++goalRevision.current;
    const ok = await updatePortfolioGoal(amount, year, request);
    if (!request.isCurrent()) return;
    if (!ok) { notify("error", "Could not save goal"); return; }
    setGoalSaved({ amount, year });
    notify("success", "Portfolio goal saved", {
      action: {
        label: "Undo",
        onClick: () => {
          if (!request.isCurrent() || goalRevision.current !== revision) return;
          return mutate("undo", async (undoRequest) => {
            ++goalRevision.current;
            const reverted = await updatePortfolioGoal(prev.amount, prev.year, undoRequest);
            if (!undoRequest.isCurrent()) return;
            if (!reverted) { notify("error", "Could not revert goal"); return; }
            setGoalAmount(prev.amount > 0 ? String(prev.amount) : "");
            setGoalYear(prev.year != null ? String(prev.year) : "");
            setGoalSaved(prev);
            notify("success", "Goal reverted");
          });
        },
      },
    });
  });

  const goalProgress = goalSaved.amount > 0 ? Math.min(100, Math.round((total / goalSaved.amount) * 100)) : 0;

  const requiredMonthlyPreview = React.useMemo(() => {
    if (!goalSaved.amount || goalSaved.amount <= 0 || !goalSaved.year) return null;
    const now = new Date().getFullYear();
    const months = Math.max(0, (goalSaved.year - now) * 12);
    if (months <= 0) return null;
    const req = computeRequiredMonthlySavings({
      currentBalance: total,
      goalAmount: goalSaved.amount,
      monthsToGoal: months,
      annualReturnPercent: 7,
      annualEscalationPercent: 0,
    });
    return req;
  }, [total, goalSaved.amount, goalSaved.year]);

  const handleAdd = () => mutate("add", async (request) => {
    const name = newName.trim();
    if (!name) { notify("error", "Enter an account name"); return; }
    const balance = newBalance === "" ? 0 : Number(newBalance);
    const row = await insertPortfolioAccount(name, balance, request);
    if (!request.isCurrent()) return;
    if (!row) { notify("error", "Could not add account"); return; }
    setAccounts((prev) => [...prev, row].sort((a, b) => a.name.localeCompare(b.name)));
    setNewName(""); setNewBalance("");
    notify("success", "Account added");
  });

  const startEdit = (account: PortfolioAccount) => {
    if (!workspaceScope.isCurrent() || mutationActive.current) return;
    setEditingId(account.id); setEditName(account.name); setEditBalance(String(account.balance));
  };
  const cancelEdit = () => {
    if (!workspaceScope.isCurrent() || mutationActive.current) return;
    setEditingId(null); setEditName(""); setEditBalance("");
  };
  const handleSaveEdit = () => mutate("edit", async (request) => {
    if (!editingId) return;
    const row = await updatePortfolioAccount(editingId, {
      name: editName.trim() || "Untitled", balance: editBalance === "" ? 0 : Number(editBalance),
    }, request);
    if (!request.isCurrent()) return;
    if (!row) { notify("error", "Could not save changes"); return; }
    setAccounts((prev) => prev.map((a) => a.id === row.id ? row : a).sort((a, b) => a.name.localeCompare(b.name)));
    setEditingId(null); setEditName(""); setEditBalance("");
    notify("success", "Account updated");
  });
  const handleDelete = (id: string) => mutate("delete", async (request) => {
    const ok = await deletePortfolioAccount(id, request);
    if (!request.isCurrent()) return;
    if (!ok) { notify("error", "Could not delete account"); return; }
    setAccounts((prev) => prev.filter((a) => a.id !== id));
    if (editingId === id) { setEditingId(null); setEditName(""); setEditBalance(""); }
    notify("success", "Account removed");
  });

  if (loading) {
    return (
      <div className="space-y-6 pb-10">
        <PageHeader total={0} loading />
        <Card className="border-[#00fff5]/20 bg-card/80">
          <CardContent className="p-6 space-y-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-14 w-full bg-[#00fff5]/10" />
            ))}
          </CardContent>
        </Card>
      </div>
    );
  }

  if (loadError) return (
    <div role="alert" className="space-y-3">
      <p>Portfolio data is unavailable. Your saved accounts and goal have not been verified.</p>
      <Button type="button" onClick={() => setReadAttempt((n) => n + 1)}>Retry portfolio read</Button>
    </div>
  );

  return (
    <div className="space-y-6 pb-10">
      <PageHeader total={total} />

      {/* Portfolio Goal */}
      <Card className="border-[#39ff14]/20 bg-card/80 backdrop-blur-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#39ff14]/12 ring-1 ring-[#39ff14]/20">
              <Target className="h-4 w-4 text-[#39ff14]" aria-hidden />
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-[#39ff14]/80">
                Portfolio goal
              </p>
              <p className="text-[11px] text-muted-foreground">
                Set a target amount and year — the NestEgg planner shows how much to save each month.
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex-1 space-y-1">
              <Label
                htmlFor="goal-amount"
                className="text-[10px] uppercase tracking-wider text-muted-foreground"
              >
                Target amount
              </Label>
              <Input
                id="goal-amount"
                type="number"
                min={0}
                step={1000}
                placeholder="e.g. 1000000"
                value={goalAmount}
                disabled={busy}
                onChange={(e) => { ++goalRevision.current; setGoalAmount(e.target.value); }}
                className="h-8 border-[#39ff14]/20 bg-[#39ff14]/5 focus:border-[#39ff14]/40 font-mono text-sm"
              />
            </div>
            <div className="w-full sm:w-36 space-y-1">
              <Label
                htmlFor="goal-year"
                className="text-[10px] uppercase tracking-wider text-muted-foreground"
              >
                Target year
              </Label>
              <Input
                id="goal-year"
                type="number"
                min={new Date().getFullYear() + 1}
                max={2100}
                step={1}
                placeholder={`e.g. ${new Date().getFullYear() + 20}`}
                value={goalYear}
                disabled={busy}
                onChange={(e) => { ++goalRevision.current; setGoalYear(e.target.value); }}
                className="h-8 border-[#39ff14]/20 bg-[#39ff14]/5 focus:border-[#39ff14]/40 font-mono text-sm"
              />
            </div>
            <Button
              type="button"
              onClick={handleSaveGoal}
              disabled={busy || !goalDirty}
              className="h-8 shrink-0 border border-[#39ff14]/30 bg-[#39ff14]/10 text-[#39ff14] hover:bg-[#39ff14]/20 text-xs disabled:opacity-40"
            >
              <Save className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              {savingGoal ? "Saving…" : goalDirty ? "Save goal" : "Saved"}
            </Button>
          </div>
          {goalSaved.amount > 0 && goalSaved.year ? (
            <div className="space-y-2.5 rounded-lg border border-[#39ff14]/10 bg-[#39ff14]/[0.02] p-3">
              <p className="text-[11px] text-muted-foreground">
                Grow your portfolio from{" "}
                <span className="font-mono text-[#00fff5]">{formatCurrency(total)}</span> to{" "}
                <span className="font-mono text-[#39ff14]">{formatCurrency(goalSaved.amount)}</span> by{" "}
                <span className="font-mono text-[#39ff14]">{goalSaved.year}</span>.
              </p>
              {/* Progress bar */}
              <div className="space-y-1">
                <div className="flex justify-between text-[10px]">
                  <span className="text-muted-foreground">{goalProgress}% of goal</span>
                  <span className="font-mono text-[#39ff14]">
                    {formatCurrency(total)} / {formatCurrency(goalSaved.amount)}
                  </span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-[#39ff14]/10 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-[#39ff14]/60 to-[#00fff5]/60 transition-[width] duration-300"
                    style={{ width: `${goalProgress}%` }}
                  />
                </div>
              </div>
              {/* Required monthly preview */}
              {requiredMonthlyPreview !== null ? (
                <p className="text-[11px] text-muted-foreground">
                  {requiredMonthlyPreview === 0 ? (
                    <span className="text-[#39ff14] font-medium">
                      Your portfolio growth alone is projected to exceed your goal.
                    </span>
                  ) : requiredMonthlyPreview === -1 ? (
                    <span className="text-[#ff3366] font-medium">
                      This goal may require a longer timeline or lower target.
                    </span>
                  ) : (
                    <>
                      Estimated{" "}
                      <span className="font-mono text-[#39ff14] font-medium">
                        {formatCurrency(requiredMonthlyPreview)}/mo
                      </span>{" "}
                      needed at 7% return.
                    </>
                  )}
                </p>
              ) : null}
              {/* Link to NestEgg */}
              <Link
                href="/nestegg"
                className="inline-flex items-center gap-1.5 text-[11px] text-[#39ff14]/80 hover:text-[#39ff14] underline underline-offset-2 transition-colors"
              >
                View full projection in NestEgg
                <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm">
        <CardHeader className="pb-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            Accounts
          </p>
          <p className="text-[11px] text-muted-foreground">
            Add your investment accounts below. The total feeds into the NestEgg planner
            as your current portfolio value.
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          {accounts.length === 0 && !adding ? (
            <p className="text-xs text-muted-foreground text-center py-6">
              No accounts yet — add one below.
            </p>
          ) : null}

          {accounts.map((account) =>
            editingId === account.id ? (
              <div
                key={account.id}
                className="flex flex-col gap-2 sm:flex-row sm:items-end rounded-lg border border-[#ff00ff]/25 bg-[#ff00ff]/5 p-3"
              >
                <div className="flex-1 space-y-1">
                  <Label
                    htmlFor={`edit-name-${account.id}`}
                    className="text-[10px] uppercase tracking-wider text-muted-foreground"
                  >
                    Name
                  </Label>
                  <Input
                    id={`edit-name-${account.id}`}
                    value={editName}
                    disabled={busy}
                    onChange={(e) => setEditName(e.target.value)}
                    className="h-8 border-[#ff00ff]/20 bg-[#ff00ff]/5 focus:border-[#ff00ff]/40 font-medium text-sm"
                    autoFocus
                  />
                </div>
                <div className="w-full sm:w-40 space-y-1">
                  <Label
                    htmlFor={`edit-bal-${account.id}`}
                    className="text-[10px] uppercase tracking-wider text-muted-foreground"
                  >
                    Balance
                  </Label>
                  <Input
                    id={`edit-bal-${account.id}`}
                    type="number"
                    min={0}
                    step={100}
                    value={editBalance}
                    disabled={busy}
                    onChange={(e) => setEditBalance(e.target.value)}
                    className="h-8 border-[#ff00ff]/20 bg-[#ff00ff]/5 focus:border-[#ff00ff]/40 font-mono text-sm"
                  />
                </div>
                <div className="flex gap-1.5 shrink-0">
                  <Button
                    type="button"
                    size="sm"
                    onClick={handleSaveEdit}
                    disabled={busy}
                    className="h-8 bg-[#ff00ff]/15 border border-[#ff00ff]/30 text-[#ff99ff] hover:bg-[#ff00ff]/25 text-xs"
                  >
                    {saving ? "Saving…" : "Save"}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    aria-label="Cancel account edit"
                    onClick={cancelEdit}
                    className="h-8 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ) : (
              <div
                key={account.id}
                className="flex items-center gap-3 rounded-lg border border-[#00fff5]/10 bg-card/50 px-3 py-2.5 group"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#00fff5]/10">
                  <Wallet className="h-3.5 w-3.5 text-[#00fff5]" aria-hidden />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{account.name}</p>
                </div>
                <p className="font-mono text-sm font-semibold text-[#00fff5] tabular-nums shrink-0">
                  {formatCurrency(account.balance)}
                </p>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-[#00fff5]"
                    disabled={busy}
                    aria-label={`Edit ${account.name}`}
                    onClick={() => startEdit(account)}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-[#ff3366]"
                    disabled={busy}
                    aria-label={`Delete ${account.name}`}
                    onClick={() => handleDelete(account.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            )
          )}

          {/* Add account form */}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end rounded-lg border border-dashed border-[#00fff5]/20 bg-[#00fff5]/[0.02] p-3 mt-2">
            <div className="flex-1 space-y-1">
              <Label
                htmlFor="new-account-name"
                className="text-[10px] uppercase tracking-wider text-muted-foreground"
              >
                Account name
              </Label>
              <Input
                id="new-account-name"
                placeholder="e.g. 401(k), Roth IRA, Brokerage"
                value={newName}
                disabled={busy}
                onChange={(e) => setNewName(e.target.value)}
                className="h-8 border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40 text-sm"
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleAdd();
                }}
              />
            </div>
            <div className="w-full sm:w-40 space-y-1">
              <Label
                htmlFor="new-account-balance"
                className="text-[10px] uppercase tracking-wider text-muted-foreground"
              >
                Balance
              </Label>
              <Input
                id="new-account-balance"
                type="number"
                min={0}
                step={100}
                placeholder="0"
                value={newBalance}
                disabled={busy}
                onChange={(e) => setNewBalance(e.target.value)}
                className="h-8 border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40 font-mono text-sm"
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleAdd();
                }}
              />
            </div>
            <Button
              type="button"
              onClick={handleAdd}
              disabled={busy || !newName.trim()}
              className="h-8 shrink-0 border border-[#00fff5]/30 bg-[#00fff5]/10 text-[#00fff5] hover:bg-[#00fff5]/20 text-xs"
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              {adding ? "Adding…" : "Add account"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function PageHeader({ total, loading = false }: { total: number; loading?: boolean }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-start">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-[#00fff5]/20 bg-gradient-to-br from-[#00fff5]/20 to-[#ff00ff]/15">
          <Wallet className="h-6 w-6 text-[#00fff5]" aria-hidden />
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <h2 className="text-lg font-semibold uppercase tracking-wider text-[#00fff5] neon-text-cyan">
            Portfolio
          </h2>
          <p className="text-xs text-muted-foreground max-w-xl leading-relaxed">
            Track your investment accounts here. The total balance is used as the starting
            portfolio value in the NestEgg retirement planner.
          </p>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Total
            </span>
            {loading ? (
              <Skeleton className="h-7 w-32 bg-[#00fff5]/10" />
            ) : (
              <span className="font-mono text-xl sm:text-2xl font-bold tracking-tight text-[#00fff5]">
                {formatCurrency(total)}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
