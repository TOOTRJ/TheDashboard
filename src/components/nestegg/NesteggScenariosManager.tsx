"use client";

import * as React from "react";
import { Bookmark, Copy, Loader2, Pencil, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { NesteggInputs, NesteggScenarioId, SavedNesteggScenario } from "@/lib/nestegg/types";
import {
  deleteNesteggScenarioFromSupabase,
  insertNesteggScenarioToSupabase,
  updateNesteggScenarioNameInSupabase,
} from "@/lib/nestegg/scenarios-supabase";

type Props = {
  inputs: NesteggInputs;
  marketScenario: NesteggScenarioId;
  onLoadScenario: (row: SavedNesteggScenario) => void;
  cloudScenarios: SavedNesteggScenario[];
  onRefreshCloud: () => Promise<void>;
  cloudRefreshing?: boolean;
  activeSavedScenarioId: string | null;
  onCloudSaved: (row: SavedNesteggScenario) => void;
  /** Refetch list and reconcile workspace if the active saved row was removed. */
  onCloudScenarioDeleted: (deletedId: string) => Promise<void>;
};

export function NesteggScenariosManager({
  inputs,
  marketScenario,
  onLoadScenario,
  cloudScenarios,
  onRefreshCloud,
  cloudRefreshing = false,
  activeSavedScenarioId,
  onCloudSaved,
  onCloudScenarioDeleted,
}: Props) {
  const { user, loading: authLoading } = useAuth();
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editName, setEditName] = React.useState("");

  React.useEffect(() => {
    if (open) {
      void onRefreshCloud();
    }
  }, [open, onRefreshCloud]);

  const handleSave = async () => {
    if (!user) {
      toast.error("Sign in to save scenarios");
      return;
    }
    const row = await insertNesteggScenarioToSupabase(name, inputs, marketScenario);
    if (!row) {
      toast.error("Could not save", {
        description:
          "Ensure the nestegg_scenarios table exists in Supabase (see supabase/migrations).",
      });
      return;
    }
    setName("");
    setOpen(false);
    onCloudSaved(row);
    await onRefreshCloud();
    toast.success("Scenario saved", { description: row.name });
  };

  const handleDeleteCloud = async (id: string) => {
    const ok = await deleteNesteggScenarioFromSupabase(id);
    if (ok) {
      await onCloudScenarioDeleted(id);
      toast.message("Scenario removed");
    } else {
      toast.error("Delete failed");
    }
  };

  const handleDuplicate = async (row: SavedNesteggScenario) => {
    if (!user) return;
    const label = `${row.name} (copy)`.slice(0, 120);
    const created = await insertNesteggScenarioToSupabase(
      label,
      row.inputs,
      row.marketScenario
    );
    if (!created) {
      toast.error("Could not duplicate");
      return;
    }
    onCloudSaved(created);
    await onRefreshCloud();
    toast.success("Duplicated", { description: created.name });
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

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className="border-[#ff00ff]/25 hover:bg-[#ff00ff]/10 hover:text-[#ff00ff] hover:border-[#ff00ff]/40"
        >
          <Bookmark className="mr-2 h-4 w-4" />
          Saved scenarios
        </Button>
      </DialogTrigger>
      <DialogContent className="border-[#00fff5]/20 bg-card/95 backdrop-blur-xl max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-[#00fff5] uppercase tracking-wider text-sm">
            Save &amp; load scenarios
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-2">
          <Label htmlFor="scenario-name" className="text-xs uppercase tracking-wider text-muted-foreground">
            Label
          </Label>
          <Input
            id="scenario-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Baseline 65 / SS at 67"
            className="border-[#00fff5]/20 bg-[#00fff5]/5"
          />
        </div>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-start">
          <Button
            type="button"
            className="border-[#ff00ff]/30 bg-[#ff00ff]/10 hover:bg-[#ff00ff]/20 text-foreground"
            onClick={() => void handleSave()}
            disabled={authLoading || !user}
          >
            <Save className="mr-2 h-4 w-4" />
            Save scenario
          </Button>
        </DialogFooter>
        {!user && !authLoading ? (
          <p className="text-[10px] text-muted-foreground">
            You must be signed in to save and load named scenarios.
          </p>
        ) : null}

        <div className="space-y-2 pt-2 border-t border-[#00fff5]/10">
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            Your saved plans
            {cloudRefreshing ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          </p>
          {!user ? (
            <p className="text-xs text-muted-foreground">Sign in to see saved plans.</p>
          ) : cloudScenarios.length === 0 ? (
            <p className="text-xs text-muted-foreground">No saved scenarios yet.</p>
          ) : (
            <ul className="space-y-2">
              {cloudScenarios.map((s) => (
                <li
                  key={s.id}
                  className={`flex items-center gap-2 rounded-md border px-2 py-2 text-sm ${
                    s.id === activeSavedScenarioId
                      ? "border-[#ff00ff]/50 bg-[#ff00ff]/10 ring-1 ring-[#ff00ff]/30"
                      : "border-[#ff00ff]/15"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    {editingId === s.id ? (
                      <div className="flex flex-col gap-1">
                        <Input
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          className="h-8 text-xs border-[#00fff5]/30"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === "Enter") void handleRenameSave(s.id);
                            if (e.key === "Escape") setEditingId(null);
                          }}
                        />
                        <div className="flex gap-1">
                          <Button
                            type="button"
                            size="sm"
                            className="h-7 text-[10px]"
                            onClick={() => void handleRenameSave(s.id)}
                          >
                            Save
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="h-7 text-[10px]"
                            onClick={() => setEditingId(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="w-full text-left hover:text-[#ff00ff]"
                        onClick={() => {
                          onLoadScenario(s);
                          setOpen(false);
                          toast.success("Loaded", { description: s.name });
                        }}
                      >
                        <span className="block truncate font-medium">{s.name}</span>
                        <span className="block text-[10px] text-muted-foreground font-normal">
                          Updated{" "}
                          {new Date(s.updatedAt).toLocaleString(undefined, {
                            dateStyle: "medium",
                            timeStyle: "short",
                          })}
                        </span>
                      </button>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-0.5">
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 text-muted-foreground hover:text-[#00fff5]"
                      aria-label={`Rename ${s.name}`}
                      onClick={() => {
                        setEditingId(s.id);
                        setEditName(s.name);
                      }}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 text-muted-foreground hover:text-[#ff99ff]"
                      aria-label={`Duplicate ${s.name}`}
                      onClick={() => void handleDuplicate(s)}
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 text-muted-foreground hover:text-[#ff3366]"
                      aria-label={`Delete ${s.name}`}
                      onClick={() => void handleDeleteCloud(s.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
