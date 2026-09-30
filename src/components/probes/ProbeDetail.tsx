"use client";

import { Clock, Skull, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { STATE_COLORS, STATE_LABELS } from "@/lib/probes/constants";
import { GENE_DEFINITIONS } from "@/lib/probes/gene-registry";
import { probeParentIds } from "@/lib/probes/lifecycle";
import type { Probe } from "@/lib/probes/types";
import { GenomeRadar } from "./GenomeRadar";
import { TradeLog } from "./TradeLog";

interface Props {
  probe: Probe | null;
  open: boolean;
  onClose: () => void;
}

export function ProbeDetail({ probe, open, onClose }: Props) {
  if (!probe) return null;
  const stateColor = STATE_COLORS[probe.state];
  const parentIds = probeParentIds(probe);
  const isDead = probe.state === "DEAD";
  const hasDeathTime = isDead && probe.died_at !== null && Number.isFinite(Date.parse(probe.died_at));
  const pendingLabel = probe.state === "DYING" ? "Awaiting terminal confirmation"
    : probe.state === "REPRODUCING" ? "Awaiting replacement confirmation"
      : isDead ? "Terminal record · death time unavailable" : "Alive";
  const equityMetrics = probe.metrics?.fitness_version === "equity-roi-historical-dd-v1";
  const sharpe = typeof probe.sharpe_ratio === "number" && Number.isFinite(probe.sharpe_ratio)
    ? probe.sharpe_ratio.toFixed(2) : "Unavailable";
  const currentDrawdown = probe.metrics?.current_drawdown;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="border-[#00fff5]/20 bg-card/95 backdrop-blur-xl sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <div>
              <DialogTitle className="text-[#00fff5]">
                {probe.probe_name}
              </DialogTitle>
              <div className="flex items-center gap-2 mt-1">
                <Badge
                  variant="outline"
                  className="text-[10px]"
                  style={{
                    borderColor: `${stateColor}50`,
                    backgroundColor: `${stateColor}15`,
                    color: stateColor,
                  }}
                >
                  {STATE_LABELS[probe.state]}
                </Badge>
                <span className="text-[10px] text-muted-foreground font-mono">
                  Gen {probe.generation}
                </span>
                {parentIds.length > 0 && (
                  <span className="text-[10px] text-muted-foreground" title={parentIds.join(", ")}>
                    Sources: {parentIds.map(id => id.slice(0, 8)).join(", ")}
                  </span>
                )}
              </div>
            </div>
          </div>
        </DialogHeader>

        {/* Lifecycle */}
        <div className="flex flex-wrap items-center gap-3 mt-4 rounded-lg border border-[#00fff5]/10 bg-[#00fff5]/[0.03] px-3 py-2 text-[11px]">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Sparkles className="h-3 w-3 text-[#39ff14]" />
            <span>Born</span>
            <span className="font-mono text-foreground">
              {new Date(probe.born_at).toLocaleString([], {
                month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
              })}
            </span>
          </div>
          {hasDeathTime ? (
            <>
              <div className="h-3 w-px bg-[#00fff5]/20" />
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <Skull className="h-3 w-3 text-[#ff3366]" />
                <span>Died</span>
                <span className="font-mono text-foreground">
                  {new Date(probe.died_at!).toLocaleString([], {
                    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
                  })}
                </span>
              </div>
              <div className="h-3 w-px bg-[#00fff5]/20" />
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <Clock className="h-3 w-3" />
                <span>Lifespan</span>
                <span className="font-mono text-foreground">
                  {(() => {
                    const ms = new Date(probe.died_at!).getTime() - new Date(probe.born_at).getTime();
                    if (!Number.isFinite(ms) || ms < 0) return "Unavailable";
                    const secs = Math.floor(ms / 1000);
                    const m = Math.floor(secs / 60);
                    const s = secs % 60;
                    return m > 0 ? `${m}m ${s}s` : `${s}s`;
                  })()}
                </span>
              </div>
              {probe.death_reason && (
                <>
                  <div className="h-3 w-px bg-[#00fff5]/20" />
                  <Badge variant="outline" className="text-[9px] px-1 py-0 border-[#ff3366]/30 text-[#ff3366]">
                    {probe.death_reason}
                  </Badge>
                </>
              )}
            </>
          ) : (
            <>
              <div className="h-3 w-px bg-[#00fff5]/20" />
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: stateColor }} aria-hidden="true" />
                <span className="font-medium" style={{ color: stateColor }}>{pendingLabel}</span>
              </div>
            </>
          )}
        </div>

        {/* Metrics grid */}
        <div className="grid grid-cols-3 gap-3 mt-4">
          {[
            { label: "Fitness", value: probe.fitness_score.toFixed(3), color: "#00fff5" },
            { label: "Capital", value: `$${probe.current_capital.toFixed(0)}`, color: "#39ff14" },
            { label: "P&L", value: `${probe.total_pnl >= 0 ? "+" : ""}$${probe.total_pnl.toFixed(2)}`, color: probe.total_pnl >= 0 ? "#39ff14" : "#ff3366" },
            { label: "Win Rate", value: probe.total_trades > 0 ? `${((probe.winning_trades / probe.total_trades) * 100).toFixed(0)}%` : "—", color: "#bf00ff" },
            { label: equityMetrics ? "Equity Sharpe (diagnostic)" : "Sharpe (run policy)", value: sharpe, color: "#ff00ff" },
            { label: equityMetrics ? "Historical max drawdown" : "Drawdown (run policy)", value: `${(probe.max_drawdown * 100).toFixed(1)}%`, color: "#ff3366" },
          ].map((m) => (
            <div
              key={m.label}
              className="rounded-lg border border-[#00fff5]/10 bg-[#00fff5]/5 p-2.5 text-center"
            >
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
                {m.label}
              </p>
              <p className="text-sm font-bold font-mono" style={{ color: m.color }}>
                {m.value}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          {equityMetrics ? (
            <>Fitness uses return on initial equity minus twice historical maximum drawdown. Sharpe uses minute equity returns without annualization; it does not affect the score.
              {typeof probe.metrics?.return_count === "number"
                ? ` Returns in the current sample: ${probe.metrics.return_count}.` : ""}
              {typeof probe.metrics?.missing_periods === "number"
                ? ` Missing minute endpoints: ${probe.metrics.missing_periods}.` : ""}
              {" Sample size alone does not establish statistical reliability."}
              {typeof currentDrawdown === "number" && Number.isFinite(currentDrawdown)
                ? ` Current drawdown: ${(currentDrawdown * 100).toFixed(1)}%.` : ""}
            </>
          ) : (
            <>This record does not identify the current equity metric policy. Its stored values may use legacy definitions; compare scores only when their calculation policies match.</>
          )}
        </p>

        {/* Genome radar */}
        <Card className="border-[#00fff5]/10 bg-card/50 mt-4">
          <CardHeader className="pb-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#00fff5]/80">
              Genome DNA
            </p>
          </CardHeader>
          <CardContent>
            <GenomeRadar genome={probe.genome} />
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-[10px]">
              {GENE_DEFINITIONS.map((gene) => {
                const val = (probe.genome as unknown as Record<string, unknown>)[gene.name];
                if (val == null) return null;
                const numVal = typeof val === "number" ? val : 0;
                const display =
                  gene.name.includes("pct") || gene.name.includes("threshold")
                    ? `${(numVal * 100).toFixed(1)}%`
                    : numVal.toFixed(1);
                return (
                  <div key={gene.name} className="flex justify-between py-0.5">
                    <span className="text-muted-foreground">{gene.label}</span>
                    <span className="font-mono text-[#00fff5]">{display}</span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Trade log */}
        <Card className="border-[#ff00ff]/10 bg-card/50 mt-4">
          <CardHeader className="pb-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#ff00ff]/80">
              Trade History ({probe.total_trades} trades)
            </p>
          </CardHeader>
          <CardContent>
            <TradeLog probeId={probe.id} />
          </CardContent>
        </Card>
      </DialogContent>
    </Dialog>
  );
}
