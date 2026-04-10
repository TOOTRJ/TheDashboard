"use client";

import * as React from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { fetchProbeTrades } from "@/lib/probes/probes-supabase";
import type { Trade } from "@/lib/probes/types";

interface Props {
  probeId: string;
}

export function TradeLog({ probeId }: Props) {
  const [trades, setTrades] = React.useState<Trade[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchProbeTrades(probeId)
      .then((data) => {
        if (!cancelled) {
          setTrades(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error("TradeLog fetch error:", err);
        if (!cancelled) {
          setTrades([]);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [probeId]);

  if (loading) {
    return (
      <p className="text-xs text-muted-foreground py-4 text-center">
        Loading trades...
      </p>
    );
  }

  if (trades.length === 0) {
    return (
      <p className="text-xs text-muted-foreground py-4 text-center">
        No trades recorded yet.
      </p>
    );
  }

  return (
    <div className="rounded-lg border border-[#00fff5]/10 overflow-hidden max-h-64 overflow-y-auto">
      <Table>
        <TableHeader>
          <TableRow className="border-b border-[#00fff5]/10 hover:bg-transparent">
            <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Pair
            </TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Opened
            </TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Entry
            </TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Exit
            </TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
              P&L
            </TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Reason
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {trades.map((trade) => (
            <TableRow
              key={trade.id}
              className="border-b border-[#00fff5]/5 hover:bg-[#00fff5]/5"
            >
              <TableCell className="text-xs font-medium">{trade.pair}</TableCell>
              <TableCell className="text-[10px] text-muted-foreground whitespace-nowrap">
                {new Date(trade.opened_at).toLocaleTimeString([], {
                  hour: "2-digit", minute: "2-digit", second: "2-digit",
                })}
              </TableCell>
              <TableCell className="text-xs font-mono">
                ${trade.entry_price.toFixed(2)}
              </TableCell>
              <TableCell className="text-xs font-mono">
                {trade.exit_price != null
                  ? `$${trade.exit_price.toFixed(2)}`
                  : "—"}
              </TableCell>
              <TableCell>
                {trade.pnl != null ? (
                  <span
                    className="text-xs font-mono font-medium"
                    style={{
                      color: trade.pnl >= 0 ? "#39ff14" : "#ff3366",
                    }}
                  >
                    {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground">open</span>
                )}
              </TableCell>
              <TableCell>
                {trade.exit_reason ? (
                  <Badge
                    variant="outline"
                    className="text-[9px] px-1 py-0"
                    style={{
                      borderColor:
                        trade.exit_reason === "TAKE_PROFIT"
                          ? "#39ff1450"
                          : trade.exit_reason === "STOP_LOSS"
                            ? "#ff336650"
                            : "#00fff550",
                      color:
                        trade.exit_reason === "TAKE_PROFIT"
                          ? "#39ff14"
                          : trade.exit_reason === "STOP_LOSS"
                            ? "#ff3366"
                            : "#00fff5",
                    }}
                  >
                    {trade.exit_reason}
                  </Badge>
                ) : null}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
