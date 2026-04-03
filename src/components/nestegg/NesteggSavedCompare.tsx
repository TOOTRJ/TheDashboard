"use client";

import * as React from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCurrency } from "@/lib/formatters";
import { applyScenarioToInputs, normalizeNesteggInputs } from "@/lib/nestegg/constants";
import { runMonteCarloBatched } from "@/lib/nestegg/monte-carlo";
import type { MonteCarloResult } from "@/lib/nestegg/monte-carlo";
import { buildPlanDiff } from "@/lib/nestegg/plan-diff";
import type { NesteggInputs, NesteggScenarioId, SavedNesteggScenario } from "@/lib/nestegg/types";
import { GitCompare, ListTree } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  cloudScenarios: SavedNesteggScenario[];
  workspaceInputs: NesteggInputs;
  workspaceMarketScenario: NesteggScenarioId;
  activeSavedId: string | null;
  /** Main MC from page (avoid duplicate simulation). */
  workspaceMonteCarlo: MonteCarloResult | null;
  /** Hide the card title row when wrapped in a parent section (e.g. collapsible). */
  hideHeader?: boolean;
};

const NONE = "__none__";

export function NesteggSavedCompare({
  cloudScenarios,
  workspaceInputs,
  workspaceMarketScenario,
  activeSavedId,
  workspaceMonteCarlo,
  hideHeader = false,
}: Props) {
  const [compareId, setCompareId] = React.useState<string>(NONE);
  const [compareMc, setCompareMc] = React.useState<MonteCarloResult | null>(null);
  const [compareLoading, setCompareLoading] = React.useState(false);

  const options = cloudScenarios.filter((s) => s.id !== activeSavedId);

  const selectedRow = cloudScenarios.find((s) => s.id === compareId);

  React.useEffect(() => {
    if (compareId === NONE) {
      setCompareMc(null);
      setCompareLoading(false);
      return;
    }
    const row = cloudScenarios.find((s) => s.id === compareId);
    if (!row) {
      setCompareMc(null);
      setCompareLoading(false);
      return;
    }
    let cancelled = false;
    setCompareLoading(true);
    const normalized = normalizeNesteggInputs(row.inputs);
    const adj = applyScenarioToInputs(normalized, row.marketScenario);
    void runMonteCarloBatched(adj, row.marketScenario, {
      paths: 420,
      chunkSize: 140,
    }).then((r) => {
      if (!cancelled) {
        setCompareMc(r);
        setCompareLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [compareId, cloudScenarios]);

  const diffRows =
    compareId !== NONE && selectedRow
      ? buildPlanDiff(
          workspaceInputs,
          workspaceMarketScenario,
          normalizeNesteggInputs(selectedRow.inputs),
          selectedRow.marketScenario
        )
      : [];

  if (options.length === 0) return null;

  const inputDiffSheet =
    compareId !== NONE && selectedRow ? (
      <Sheet>
        <SheetTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 border-[#bf00ff]/30 text-[11px] text-[#ff99ff] hover:bg-[#bf00ff]/10"
          >
            <ListTree className="mr-1.5 h-3.5 w-3.5" />
            Input diff
          </Button>
        </SheetTrigger>
        <SheetContent
          side="right"
          className="w-full overflow-y-auto border-[#bf00ff]/20 bg-card/95 backdrop-blur-xl sm:max-w-lg"
        >
          <SheetHeader>
            <SheetTitle className="text-[#bf00ff] uppercase tracking-wider text-sm">
              Plan inputs vs {selectedRow.name}
            </SheetTitle>
          </SheetHeader>
          <div className="mt-4 px-1">
            <Table>
              <TableHeader>
                <TableRow className="border-[#bf00ff]/10 hover:bg-transparent">
                  <TableHead className="text-[10px] uppercase text-muted-foreground">
                    Field
                  </TableHead>
                  <TableHead className="text-[10px] uppercase text-[#00fff5]">
                    Workspace
                  </TableHead>
                  <TableHead className="text-[10px] uppercase text-[#ff99ff]">
                    Saved
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {diffRows.map((row) => (
                  <TableRow
                    key={row.id}
                    className={cn(
                      "border-[#bf00ff]/10",
                      row.changed && "bg-[#ffff00]/5"
                    )}
                  >
                    <TableCell className="text-xs text-muted-foreground align-top">
                      {row.label}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-xs font-mono align-top",
                        row.changed && "text-[#00fff5]"
                      )}
                    >
                      {row.a}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-xs font-mono align-top",
                        row.changed && "text-[#ff99ff]"
                      )}
                    >
                      {row.b}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-4 text-[10px] text-muted-foreground leading-relaxed">
              Changed rows are highlighted. Market preset and numeric assumptions can both move your
              Monte Carlo snapshot.
            </p>
          </div>
        </SheetContent>
      </Sheet>
    ) : null;

  return (
    <Card className="border-[#bf00ff]/20 bg-card/80 backdrop-blur-sm overflow-hidden">
      {!hideHeader ? (
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#bf00ff]/10">
                <GitCompare className="h-4 w-4 text-[#bf00ff]" aria-hidden />
              </div>
              <div className="min-w-0">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-[#bf00ff]">
                  Compare to a saved plan
                </h3>
                <p className="text-[11px] text-muted-foreground">
                  Side-by-side probability — does not change your workspace
                </p>
              </div>
            </div>
            {inputDiffSheet}
          </div>
        </CardHeader>
      ) : null}
      <CardContent className={hideHeader ? "space-y-3 pt-1" : "space-y-3 pt-0"}>
        {hideHeader && inputDiffSheet ? (
          <div className="flex justify-end">{inputDiffSheet}</div>
        ) : null}
        <div className="space-y-1">
          <Label htmlFor="compare-saved" className="text-[10px] uppercase tracking-wider">
            Saved plan
          </Label>
          <Select value={compareId} onValueChange={setCompareId}>
            <SelectTrigger
              id="compare-saved"
              className="h-9 border-[#bf00ff]/25 bg-[#bf00ff]/5 text-xs"
            >
              <SelectValue placeholder="Choose a plan" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE} className="text-xs">
                None
              </SelectItem>
              {options.map((s) => (
                <SelectItem key={s.id} value={s.id} className="text-xs">
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {compareId !== NONE ? (
          <div className="grid gap-3 sm:grid-cols-2 rounded-lg border border-[#bf00ff]/15 bg-background/40 p-3 text-xs">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                This workspace
              </p>
              {workspaceMonteCarlo ? (
                <>
                  <p className="font-mono text-[#00fff5]">
                    Success {Math.round(workspaceMonteCarlo.successRate * 100)}%
                  </p>
                  <p className="text-muted-foreground mt-1">
                    Nest egg (median){" "}
                    {formatCurrency(workspaceMonteCarlo.medianNestEggAtRetirement)}
                  </p>
                </>
              ) : (
                <p className="text-muted-foreground animate-pulse">Updating simulation…</p>
              )}
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                Saved plan
              </p>
              {compareLoading ? (
                <p className="text-muted-foreground animate-pulse">Running comparison…</p>
              ) : compareMc ? (
                <>
                  <p className="font-mono text-[#ff99ff]">
                    Success {Math.round(compareMc.successRate * 100)}%
                  </p>
                  <p className="text-muted-foreground mt-1">
                    Nest egg (median) {formatCurrency(compareMc.medianNestEggAtRetirement)}
                  </p>
                </>
              ) : null}
            </div>
          </div>
        ) : (
          <p className="text-[11px] text-muted-foreground">
            Select a saved plan to compare success rate and median nest egg at retirement.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
