"use client";

import * as React from "react";
import { Bookmark, Copy, Loader2, Pencil, Save, Upload, X } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth/AuthProvider";
import type { createNesteggWorkspaceScope } from "@/lib/nestegg/session-scope";
import { createNesteggPublicationClock, type NesteggPublication } from "@/lib/nestegg/result-identity";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  workspaceScope: ReturnType<typeof createNesteggWorkspaceScope>;
  captureWorkspaceIntent: () => NesteggPublication;
  inputs: NesteggInputs;
  marketScenario: NesteggScenarioId;
  cloudScenarios: SavedNesteggScenario[];
  activeSavedScenarioId: string | null;
  onLoadScenario: (row: SavedNesteggScenario) => void;
  onRefreshCloud: () => Promise<void>;
  cloudRefreshing?: boolean;
  onCloudSaved: (row: SavedNesteggScenario, publication: NesteggPublication) => void;
  onCloudRenamed: (row: SavedNesteggScenario, publication: NesteggPublication) => void;
  onCloudScenarioDeleted: (deletedId: string, publication: NesteggPublication) => Promise<void>;
  /** When a cloud plan tab is selected: overwrite that row with current workspace + label. */
  canSaveActivePlan?: boolean;
  dirtyActivePlan?: boolean;
  savingActivePlan?: boolean;
  onSaveActivePlan?: () => void;
  /** Shown next to update button (e.g. draft label). */
  activePlanLabelPreview?: string;
};

export function NesteggSavedPlanTabsToolbar({
  workspaceScope,
  captureWorkspaceIntent,
  inputs,
  marketScenario,
  cloudScenarios,
  activeSavedScenarioId,
  onLoadScenario,
  onRefreshCloud,
  cloudRefreshing = false,
  onCloudSaved,
  onCloudRenamed,
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
  const [deleteTarget, setDeleteTarget] = React.useState<SavedNesteggScenario | null>(null);
  const operationClock = React.useRef(createNesteggPublicationClock());
  const editLocal = () => { operationClock.current.invalidate(); };

  const activeRow = React.useMemo(
    () => cloudScenarios.find((s) => s.id === activeSavedScenarioId) ?? null,
    [cloudScenarios, activeSavedScenarioId]
  );

  React.useEffect(() => {
    operationClock.current.invalidate();
    setEditingId(null);
    setSaveNewOpen(false);
    setNewPlanName("");
  }, [activeSavedScenarioId]);

  React.useEffect(() => {
    if (saveNewOpen) {
      const request = workspaceScope.capture();
      const timer = window.setTimeout(() => { if (request.isCurrent()) document.getElementById("nestegg-new-plan-name")?.focus(); }, 0);
      return () => window.clearTimeout(timer);
    }
  }, [saveNewOpen, workspaceScope]);

  const handleSaveNew = async () => {
    const request = workspaceScope.capture();
    if (!request.isCurrent() || user?.id !== request.ownerId) return;
    const publication = captureWorkspaceIntent(), operation = operationClock.current.next();
    const isCurrent = () => request.isCurrent() && publication.isCurrent() && operation.isCurrent();
    const savedName = newPlanName, savedInputs = { ...inputs }, savedScenario = marketScenario;
    try {
      const row = await insertNesteggScenarioToSupabase(savedName, savedInputs, savedScenario, request);
      if (!isCurrent()) return;
      if (!row) {
        toast.error("Could not save", {
          description:
            "Ensure the nestegg_scenarios table exists in Supabase (see supabase/migrations).",
        });
        return;
      }
      setNewPlanName("");
      setSaveNewOpen(false);
      // Selecting the newly saved row retires this dialog's generation. Acknowledge the
      // confirmed write while its original workspace is current, before that transition.
      toast.success("New plan saved", { description: row.name });
      onCloudSaved(row, publication);
      await onRefreshCloud();
    } catch {
      if (isCurrent()) toast.error("Unable to complete the saved-plan operation");
    }
  };

  const handleDelete = async (id: string) => {
    const request = workspaceScope.capture();
    if (!request.isCurrent()) return;
    const publication = captureWorkspaceIntent(), operation = operationClock.current.next();
    const isCurrent = () => request.isCurrent() && publication.isCurrent() && operation.isCurrent();
    try {
      const ok = await deleteNesteggScenarioFromSupabase(id, request);
      if (!isCurrent()) return;
      if (ok) {
        await onCloudScenarioDeleted(id, publication);
        if (!isCurrent()) return;
        toast.message("Scenario removed");
        setDeleteTarget(null);
      } else {
        toast.error("Delete failed");
      }
    } catch {
      if (isCurrent()) toast.error("Unable to complete the saved-plan operation");
    }
  };

  const handleRenameSave = async (id: string) => {
    const request = workspaceScope.capture();
    if (!request.isCurrent()) return;
    const publication = captureWorkspaceIntent(), operation = operationClock.current.next();
    const isCurrent = () => request.isCurrent() && publication.isCurrent() && operation.isCurrent();
    const savedName = editName;
    try {
      const next = await updateNesteggScenarioNameInSupabase(id, savedName, request);
      if (!isCurrent()) return;
      if (!next) {
        toast.error("Rename failed");
        return;
      }
      setEditingId(null);
      onCloudRenamed(next, publication);
      await onRefreshCloud();
      if (!isCurrent()) return;
      toast.success("Renamed", { description: next.name });
    } catch {
      if (isCurrent()) toast.error("Unable to complete the saved-plan operation");
    }
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
                <div
                  key={s.id}
                  className={cn(
                    "relative flex shrink-0 items-stretch rounded-t-lg border border-b-0 max-w-[min(100vw-2rem,260px)] overflow-hidden",
                    selected
                      ? "z-[1] border-[#ff00ff]/45 bg-[#ff00ff]/12 shadow-[0_-4px_16px_-4px_rgba(255,0,255,0.25)]"
                      : "border-transparent bg-card/30"
                  )}
                >
                  <button
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    onClick={() => {
                      onLoadScenario(s);
                      toast.success("Loaded", { description: s.name });
                    }}
                    className={cn(
                      "min-w-0 flex-1 px-3 py-2 text-left text-xs font-medium transition-colors",
                      selected
                        ? "text-[#ff99ff]"
                        : "text-muted-foreground hover:bg-card/50 hover:text-foreground"
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
                  <button
                    type="button"
                    aria-label={`Delete ${s.name}`}
                    className={cn(
                      "flex shrink-0 items-center justify-center px-2 border-l transition-colors",
                      selected
                        ? "border-[#ff00ff]/30 bg-black/15 hover:bg-[#ff3366]/20 hover:text-[#ff3366] text-muted-foreground"
                        : "border-[#00fff5]/10 bg-black/10 hover:bg-[#ff3366]/15 hover:text-[#ff3366] text-muted-foreground"
                    )}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      editLocal(); setDeleteTarget(s);
                    }}
                  >
                    <X className="h-3.5 w-3.5 opacity-90" aria-hidden />
                  </button>
                </div>
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
              onChange={(e) => { editLocal(); setEditName(e.target.value); }}
              className="h-9 border-[#00fff5]/30 bg-background/60 text-sm"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && editingId) void handleRenameSave(editingId);
                if (e.key === "Escape") { editLocal(); setEditingId(null); }
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
            <Button type="button" size="sm" variant="ghost" onClick={() => { editLocal(); setEditingId(null); }}>
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
                    onClick={() => { editLocal(); setSaveNewOpen(true); }}
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
                      editLocal(); setSaveNewOpen(false);
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
                  onClick={() => { editLocal(); setSaveNewOpen(true); }}
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
                    editLocal(); setSaveNewOpen(false);
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
                editLocal(); setEditingId(activeRow.id);
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
              onClick={() => { editLocal(); setDeleteTarget(activeRow); }}
            >
              <X className="h-4 w-4" aria-hidden />
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
                onChange={(e) => { editLocal(); setNewPlanName(e.target.value); }}
                placeholder="e.g. Baseline 65 / SS at 67"
                className="border-[#00fff5]/25 bg-[#00fff5]/8"
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleSaveNew();
                  if (e.key === "Escape") {
                    editLocal(); setSaveNewOpen(false);
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
                  editLocal(); setSaveNewOpen(false);
                  setNewPlanName("");
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      <Dialog open={deleteTarget !== null} onOpenChange={(open) => { if (!open) { editLocal(); setDeleteTarget(null); } }}>
        <DialogContent className="border-[#ff00ff]/25 bg-card/95 backdrop-blur-xl sm:max-w-md" showCloseButton>
          <DialogHeader>
            <DialogTitle>Delete saved plan?</DialogTitle>
            <DialogDescription>
              {deleteTarget
                ? `This removes "${deleteTarget.name}" from your account. You can't undo this.`
                : null}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={() => { editLocal(); setDeleteTarget(null); }}>
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              className="bg-[#b91c1c] hover:bg-[#991b1b]"
              onClick={() => deleteTarget && void handleDelete(deleteTarget.id)}
            >
              Delete plan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
