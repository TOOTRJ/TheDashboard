"use client";

import { formatReferenceNumber, parseProbeAccounting } from "@/lib/probes/execution";
import { Badge } from "@/components/ui/badge";
import { STATE_COLORS, STATE_LABELS } from "@/lib/probes/constants";
import type { Probe } from "@/lib/probes/types";

interface Props {
  probe: Probe;
  onClick: () => void;
}

export function ProbeCard({ probe, onClick }: Props) {
  const stateColor = STATE_COLORS[probe.state];
  const accounting = parseProbeAccounting(probe.metrics?.accounting);
  const isDead = probe.state === "DEAD";

  return (
    <div
      onClick={onClick}
      className={`
        group cursor-pointer rounded-lg border p-4 transition-all duration-300
        hover:scale-[1.02] hover:shadow-lg
        ${isDead ? "opacity-50 border-[#7a7a8c]/20 bg-card/30" : "border-[#00fff5]/15 bg-card/80 backdrop-blur-sm hover:border-[#00fff5]/30"}
      `}
      style={{
        boxShadow: !isDead
          ? `0 0 0 0 ${stateColor}00`
          : undefined,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold truncate">{probe.probe_name}</p>
          <p className="text-[10px] text-muted-foreground font-mono mt-0.5">
            Gen {probe.generation}
          </p>
        </div>
        <Badge
          variant="outline"
          className="shrink-0 text-[10px] px-1.5 py-0"
          style={{
            borderColor: `${stateColor}50`,
            backgroundColor: `${stateColor}15`,
            color: stateColor,
          }}
        >
          {STATE_LABELS[probe.state]}
        </Badge>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-muted-foreground">Fitness</span>
          <p className="font-mono font-medium text-[#00fff5]">
            {probe.fitness_score.toFixed(3)}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">{accounting ? "Cash (USD)" : "Recorded cash · unit unverified"}</span>
          <p className="font-mono font-medium text-[#39ff14]">
            {accounting ? "$" : ""}{formatReferenceNumber(accounting?.cash ?? probe.current_capital)}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">Win Rate</span>
          <p className="font-mono font-medium">
            {probe.total_trades > 0
              ? `${((probe.winning_trades / probe.total_trades) * 100).toFixed(0)}%`
              : "—"}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">Trades</span>
          <p className="font-mono font-medium">{probe.total_trades}</p>
        </div>
      </div>

      <div className="mt-2 space-y-1 text-[10px] text-muted-foreground">
        <p>Recorded equity (USD): <span className="font-mono">{accounting?.valuation_available ? `$${formatReferenceNumber(accounting.equity)}` : "Unavailable"}</span></p>
        <p>Equity ROI: <span className="font-mono">{accounting?.valuation_available && accounting.roi !== null ? `${(accounting.roi * 100).toFixed(2)}%` : "Unavailable"}</span></p>
        <p>{accounting ? "Realized P&L (USD)" : "Recorded P&L · unit unverified"}: <span className="font-mono">{formatReferenceNumber(probe.total_pnl)}</span></p>
      </div>
    </div>
  );
}
