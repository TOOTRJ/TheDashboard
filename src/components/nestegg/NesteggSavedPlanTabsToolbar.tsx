"use client";

import * as React from "react";
import { Bookmark, Copy, Loader2, Pencil, Save, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { NesteggInputs, NesteggScenarioId, SavedNesteggScenario } from "@/lib/nestegg/types";
import {
  deleteNesteggScenarioFromSupabase,
  insertNesteggScenarioToSupabase,
  updateNesteggScenarioNameInSupabase,
} from "@/lib/nestegg/scenarios-supabase";
import { cn } from "@/lib/utils";

type Props = {
  inputs: NesteggInputs;
  marketScenario: NesteggScenarioId;
  cloudScenarios: SavedNesteggScenario[];
  activeSavedScenarioId: string | null;
  onLoadScenario: (row: SavedNesteggScenario) => void;
  onRefreshCloud: () => Promise<void>;
  cloudRefreshing?: boolean;
  onCloudSaved: (row: SavedNesteggScenario) => void;
  onCloudScenarioDeleted: (deletedId: string) => Promise<void>;
  /** When a cloud plan tab is selected: overwrite that row with current workspace + label. */
  canSaveActivePlan?: boolean;
  dirtyActivePlan?: boolean;
  savingActivePlan?: boolean;
  onSaveActivePlan?: () => void;
  /** Shown next to update button (e.g. draft label). */
  activePlanLabelPreview?: string;
};

export function NesteggSavedPlanTabsToolbar({
  inputs,
  marketScenario,
  cloudScenarios,
  activeSavedScenarioId,
  onLoadScenario,
  onRefreshCloud,
  cloudRefreshing = false,
  onCloudSaved,
  onCloudScenarioDeleted,
  canSaveActivePlan = false,
  dirtyActivePlan = false,
  savingActivePlan = false,
  onSaveActivePlan,
  activePlanLabelPreview = "",
}: Props) {
  const { user, loading: authLoading } = useAuth();
  const [newPlanName, setNewPlanName] = React.useState("");
  const [saveNewOpen, setSaveNewOpen] = React.useState(false);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editName, setEditName] = React.useState("");

  const activeRow = React.useMemo(
    () => cloudScenarios.find((s) => s.id === activeSavedScenarioId) ?? null,
    [cloudScenarios, activeSavedScenarioId]
  );

  React.useEffect(() => {
    setEditingId(null);
    setSaveNewOpen(false);
    setNewPlanName("");
  }, [activeSavedScenarioId]);

  React.useEffect(() => {
    if (saveNewOpen) {
      window.setTimeout(() => document.getElementById("nestegg-new-plan-name")?.focus(), 0);
    }
  }, [saveNewOpen]);

  const handleSaveNew = async () => {
    if (!user) {
      toast.error("Sign in to save scenarios");
      return;
    }
    const row = await insertNesteggScenarioToSupabase(newPlanName, inputs, marketScenario);
    if (!row) {
      toast.error("Could not save", {
        description:
          "Ensure the nestegg_scenarios table exists in Supabase (see supabase/migrations).",
      });
      return;
    }
    setNewPlanName("");
    setSaveNewOpen(false);
    onCloudSaved(row);
    await onRefreshCloud();
    toast.success("New plan saved", { description: row.name });
  };

  const handleDelete = async (id: string) => {
    const ok = await deleteNesteggScenarioFromSupabase(id);
    if (ok) {
      await onCloudScenarioDeleted(id);
      toast.message("Scenario removed");
    } else {
      toast.error("Delete failed");
    }
  };

  const handleRenameSave = async (id: string) => {
    const next = await updateNesteggScenarioNameInSupabase(id, editName);
    if (!next) {
      toast.error("Rename failed");
      return;
    }
    setEditingId(null);
    await onRefreshCloud();
    if (activeSavedScenarioId === id) {
      onLoadScenario(next);
    }
    toast.success("Renamed", { description: next.name });
  };

  if (!user && !authLoading) {
    return (
      <p className="text-[11px] text-muted-foreground">
        Sign in to save plans and use folder tabs.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
        <Bookmark className="h-3.5 w-3.5 text-[#ff00ff]/80" aria-hidden />
        Saved plans
        {cloudRefreshing ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> : null}
      </div>

      {cloudScenarios.length > 0 ? (
        <div className="overflow-x-auto pb-px -mx-1 px-1">
          <div
            className="flex min-h-[40px] flex-wrap items-end gap-1 border-b border-[#00fff5]/20"
            role="tablist"
            aria-label="Saved plans"
          >
            {cloudScenarios.map((s) => {
              const selected = activeSavedScenarioId === s.id;
              return (
                <button
                  key={s.id}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  onClick={() => {
                    onLoadScenario(s);
                    toast.success("Loaded", { description: s.name });
                  }}
                  className={cn(
                    "relative shrink-0 rounded-t-lg border border-b-0 px-3 py-2 text-left text-xs font-medium transition-colors max-w-[min(100vw-2rem,220px)]",
                    selected
                      ? "z-[1] border-[#ff00ff]/45 bg-[#ff00ff]/12 text-[#ff99ff] shadow-[0_-4px_16px_-4px_rgba(255,0,255,0.25)]"
                      : "border-transparent bg-card/30 text-muted-foreground hover:bg-card/50 hover:text-foreground"
                  )}
                >
                  <span className="block truncate" title={s.name}>
                    {s.name}
                  </span>
                  <span className="mt-0.5 block truncate text-[10px] font-normal text-muted-foreground">
                    {new Date(s.updatedAt).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        <p className="text-[11px] text-muted-foreground">No saved plans yet — save one below.</p>
      )}

      {editingId ? (
        <div className="flex flex-col gap-2 rounded-lg border border-[#00fff5]/20 bg-[#00fff5]/5 p-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1">
            <Label htmlFor="rename-plan-inline" className="text-[10px] uppercase tracking-wider">
              Rename plan
            </Label>
            <Input
              id="rename-plan-inline"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="h-9 border-[#00fff5]/30 bg-background/60 text-sm"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && editingId) void handleRenameSave(editingId);
                if (e.key === "Escape") setEditingId(null);
              }}
            />
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              className="h-9"
              onClick={() => editingId && void handleRenameSave(editingId)}
            >
              Apply name
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setEditingId(null)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      <div className="rounded-lg border border-[#ff00ff]/25 bg-gradient-to-r from-[#ff00ff]/10 to-[#00fff5]/5 p-3 space-y-3">
        {canSaveActivePlan && onSaveActivePlan ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
            <div className="min-w-0 space-y-0.5 flex-1">
              <p className="text-[10px] font-bold uppercase tracking-widest text-[#ff99ff]/90">
                Update selected plan
              </p>
              <p className="text-[11px] text-muted-foreground leading-snug">
                Saves your current inputs and scenario label to the open tab
                {activePlanLabelPreview ? (
                  <>
                    :{" "}
                    <span
                      className="font-medium text-foreground/90 truncate inline-block max-w-[min(100%,240px)] align-bottom"
                      title={activePlanLabelPreview}
                    >
                      {activePlanLabelPreview}
                    </span>
                  </>
                ) : null}
                .
              </p>
            </div>
            <div className="flex flex-col gap-1.5 sm:items-end shrink-0 w-full sm:w-auto sm:min-w-[min(100%,320px)]">
              <span
                className={
                  dirtyActivePlan
                    ? "text-[10px] font-medium uppercase tracking-wider text-amber-400/95 sm:text-right"
                    : "text-[10px] uppercase tracking-wider text-muted-foreground sm:text-right"
                }
              >
                {dirtyActivePlan ? "Unsaved changes" : "In sync with cloud"}
              </span>
              <div className="flex flex-wrap items-center justify-end gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={!dirtyActivePlan || savingActivePlan}
                  onClick={() => void onSaveActivePlan()}
                  className="border-[#ff00ff]/40 bg-[#ff00ff]/15 hover:bg-[#ff00ff]/25 text-foreground"
                >
                  {savingActivePlan ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
                  ) : (
                    <Upload className="mr-2 h-4 w-4" aria-hidden />
                  )}
                  Save changes to this tab
                </Button>
                {!saveNewOpen ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={authLoading || !user}
                    className="border-[#00fff5]/35 bg-[#00fff5]/8 hover:bg-[#00fff5]/15 text-foreground"
                    onClick={() => setSaveNewOpen(true)}
                  >
                    <Copy className="mr-2 h-4 w-4" aria-hidden />
                    Duplicate
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="border-[#00fff5]/35 bg-transparent hover:bg-[#00fff5]/10"
                    onClick={() => {
                      setSaveNewOpen(false);
                      setNewPlanName("");
                    }}
                  >
                    Cancel new plan
                  </Button>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
            <div className="space-y-0.5 min-w-0 flex-1">
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                Save your plan
              </p>
              <p className="text-[11px] text-muted-foreground leading-snug">
                Select a saved tab above to update it, or use{" "}
                <span className="font-medium text-foreground/85">Duplicate</span> to create a named
                copy without changing an existing tab.
              </p>
            </div>
            {!saveNewOpen ? (
              <div className="flex shrink-0 justify-end sm:pt-5">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={authLoading || !user}
                  className="border-[#00fff5]/35 bg-[#00fff5]/8 hover:bg-[#00fff5]/15 text-foreground"
                  onClick={() => setSaveNewOpen(true)}
                >
                  <Copy className="mr-2 h-4 w-4" aria-hidden />
                  Duplicate
                </Button>
              </div>
            ) : (
              <div className="flex shrink-0 justify-end sm:pt-5">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="border-[#00fff5]/35 bg-transparent hover:bg-[#00fff5]/10"
                  onClick={() => {
                    setSaveNewOpen(false);
                    setNewPlanName("");
                  }}
                >
                  Cancel new plan
                </Button>
              </div>
            )}
          </div>
        )}

        {!saveNewOpen && activeRow ? (
          <div className="flex flex-wrap items-center justify-end gap-0.5 border-t border-[#00fff5]/15 pt-3">
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-9 w-9 text-muted-foreground hover:text-[#00fff5]"
              aria-label={`Rename ${activeRow.name}`}
              onClick={() => {
                setEditingId(activeRow.id);
                setEditName(activeRow.name);
              }}
            >
              <Pencil className="h-4 w-4" aria-hidden />
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-9 w-9 text-muted-foreground hover:text-[#ff3366]"
              aria-label={`Delete ${activeRow.name}`}
              onClick={() => void handleDelete(activeRow.id)}
            >
              <Trash2 className="h-4 w-4" aria-hidden />
            </Button>
          </div>
        ) : null}

        {saveNewOpen ? (
          <div className="space-y-2 border-t border-[#00fff5]/15 pt-3">
            <div className="space-y-1.5">
              <Label htmlFor="nestegg-new-plan-name" className="text-[10px] uppercase tracking-wider text-muted-foreground">
                New plan name
              </Label>
              <p className="text-[11px] text-muted-foreground leading-snug">
                {canSaveActivePlan ? (
                  <>
                    Adds a new tab; the open tab is unchanged until you use{" "}
                    <span className="font-medium text-foreground/85">Save changes to this tab</span>.
                  </>
                ) : (
                  "Creates a new saved plan from your current inputs in a new tab."
                )}
              </p>
              <Input
                id="nestegg-new-plan-name"
                value={newPlanName}
                onChange={(e) => setNewPlanName(e.target.value)}
                placeholder="e.g. Baseline 65 / SS at 67"
                className="border-[#00fff5]/25 bg-[#00fff5]/8"
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleSaveNew();
                  if (e.key === "Escape") {
                    setSaveNewOpen(false);
                    setNewPlanName("");
                  }
                }}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                disabled={authLoading || !user}
                className="border-[#00fff5]/40 bg-[#00fff5]/15 hover:bg-[#00fff5]/25 text-foreground"
                onClick={() => void handleSaveNew()}
              >
                <Save className="mr-2 h-4 w-4" aria-hidden />
                Create saved plan
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSaveNewOpen(false);
                  setNewPlanName("");
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
