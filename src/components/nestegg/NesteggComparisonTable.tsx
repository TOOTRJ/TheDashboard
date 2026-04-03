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
  /** Hide the card title row when wrapped in a parent section (e.g. collapsible). */
  hideHeader?: boolean;
};

const NEON = {
  base: "#00fff5",
  cons: "#ffff00",
  agg: "#ff00ff",
};

export function NesteggComparisonTable({ rows, loading, hideHeader = false }: Props) {
  return (
    <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm">
      {!hideHeader ? (
        <CardHeader className="pb-2">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#00fff5]/10">
              <Columns3 className="h-4 w-4 text-[#00fff5]" aria-hidden />
            </div>
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">
                Compare market presets
              </h3>
              <p className="text-[11px] text-muted-foreground">
                Same plan, three stress levels — see how success odds and balances shift
              </p>
            </div>
          </div>
        </CardHeader>
      ) : null}
      <CardContent className={hideHeader ? "overflow-x-auto pt-1" : "overflow-x-auto pt-0"}>
        <Table>
          <TableHeader>
            <TableRow className="border-[#00fff5]/10 hover:bg-transparent">
              <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Preset
              </TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Chance of success
              </TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                At retirement (median)
              </TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Balance at end (median)
              </TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Typical depletion age
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
