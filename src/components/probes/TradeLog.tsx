"use client";

import * as React from "react";
import { formatReferenceNumber, parseTradeExecution } from "@/lib/probes/execution";
import { TradeExecutionDetails } from "./TradeExecutionDetails";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fetchProbeTrades } from "@/lib/probes/probes-supabase";
import type { Trade } from "@/lib/probes/types";

interface Props {
  probeId: string;
}

export function TradeLog({ probeId }: Props) {
  return <ProbeTradeLog key={probeId} probeId={probeId} />;
}

function ProbeTradeLog({ probeId }: Props) {
  const [trades, setTrades] = React.useState<Trade[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(false);
  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    fetchProbeTrades(probeId, abort.signal)
      .then((data) => {
        if (!abort.signal.aborted) {
          setTrades(data);
          setError(false);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!abort.signal.aborted) {
          setError(true);
          setLoading(false);
        }
      });
    return () => {
      abort.abort();
    };
  }, [probeId, attempt]);

  if (loading && trades.length === 0) {
    return (
      <p className="text-xs text-muted-foreground py-4 text-center">
        Loading trades...
      </p>
    );
  }

  if (trades.length === 0 && !error) {
    return (
      <p className="text-xs text-muted-foreground py-4 text-center">
        No trades recorded yet.
      </p>
    );
  }

  return (
    <>
    {error && (
      <div role="alert" className="mb-2 text-xs text-destructive">
        Trade history is unavailable.{trades.length > 0 && " Showing the last successful result."}
        <Button variant="outline" size="sm" className="ml-2" disabled={loading} onClick={() => setAttempt((n) => n + 1)}>Retry</Button>
      </div>
    )}
    {trades.length > 0 && (
    <div className="rounded-lg border border-[#00fff5]/10 max-h-64 overflow-auto">
      <Table>
        <TableHeader>
          <TableRow className="border-b border-[#00fff5]/10 hover:bg-transparent">
            <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Asset / accounting
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
              Net P&L / recorded P&L
            </TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">Execution accounting</TableHead>
            <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Reason
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {trades.map((trade) => {
            const execution = parseTradeExecution(trade.execution);
            const pnl = execution ? execution.exit?.net_pnl ?? null : trade.pnl;
            const unit = execution ? "$" : "";
            const exitPrice = execution ? execution.exit?.fill_price ?? null : trade.exit_price;
            const closed = execution ? execution.exit !== null : trade.exit_price != null;
            return <TableRow
              key={trade.id}
              className="border-b border-[#00fff5]/5 hover:bg-[#00fff5]/5"
            >
              <TableCell className="text-xs font-medium">{trade.pair.split("/")[0]}<span className="block text-[10px] text-muted-foreground">{execution ? "USD reference" : `${trade.pair} · unit unverified`}</span></TableCell>
              <TableCell className="text-[10px] text-muted-foreground whitespace-nowrap">
                {new Date(trade.opened_at).toLocaleTimeString([], {
                  hour: "2-digit", minute: "2-digit", second: "2-digit",
                })}
              </TableCell>
              <TableCell className="text-xs font-mono">
                {unit}{formatReferenceNumber(execution?.entry.fill_price ?? trade.entry_price)}
              </TableCell>
              <TableCell className="text-xs font-mono">
                {exitPrice != null
                  ? `${unit}${formatReferenceNumber(exitPrice)}`
                  : "—"}
              </TableCell>
              <TableCell>
                {pnl != null ? (
                  <span
                    className="text-xs font-mono font-medium"
                    style={{
                      color: pnl >= 0 ? "#39ff14" : "#ff3366",
                    }}
                  >
                    {pnl >= 0 ? "+" : ""}{unit}{formatReferenceNumber(pnl)}
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground">open</span>
                )}
              </TableCell>
              <TableCell><TradeExecutionDetails execution={trade.execution} /></TableCell>
              <TableCell>
                {closed && trade.exit_reason ? (
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
            </TableRow>;
          })}
        </TableBody>
      </Table>
    </div>
    )}
    </>
  );
}
