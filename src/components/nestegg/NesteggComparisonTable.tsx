"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCurrency } from "@/lib/formatters";
import type { ScenarioMonteCompareRow } from "@/lib/nestegg/monte-carlo";
import { Columns3 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

type Props = {
  rows: ScenarioMonteCompareRow[];
  loading?: boolean;
};

const NEON = {
  base: "#00fff5",
  cons: "#ffff00",
  agg: "#ff00ff",
};

export function NesteggComparisonTable({ rows, loading }: Props) {
  return (
    <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#00fff5]/10">
            <Columns3 className="h-4 w-4 text-[#00fff5]" aria-hidden />
          </div>
          <div>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">
              Scenario comparison
            </h3>
            <p className="text-[11px] text-muted-foreground">
              Monte Carlo metrics for Base, Conservative, and Aggressive presets (same inputs)
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto pt-0">
        <Table>
          <TableHeader>
            <TableRow className="border-[#00fff5]/10 hover:bg-transparent">
              <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Preset
              </TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Success
              </TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Nest egg at retirement
              </TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Ending balance (median)
              </TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Median depletion age
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              [0, 1, 2].map((i) => (
                <TableRow key={i} className="border-[#00fff5]/10">
                  <TableCell colSpan={5}>
                    <Skeleton className="h-8 w-full bg-[#00fff5]/10" />
                  </TableCell>
                </TableRow>
              ))
            ) : (
            rows.map((r) => {
              const color =
                r.scenarioId === "base"
                  ? NEON.base
                  : r.scenarioId === "conservative"
                    ? NEON.cons
                    : NEON.agg;
              return (
                <TableRow key={r.scenarioId} className="border-[#00fff5]/10">
                  <TableCell
                    className="font-medium text-xs"
                    style={{ color }}
                  >
                    {r.label}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {Math.round(r.successRate * 100)}%
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {formatCurrency(r.medianNestEggAtRetirement)}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {formatCurrency(r.medianEndingBalance)}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {r.medianDepletionAge !== null
                      ? `~${Math.ceil(r.medianDepletionAge)}`
                      : "—"}
                  </TableCell>
                </TableRow>
              );
            })
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
