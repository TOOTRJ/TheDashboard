"use client";

import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { formatCurrency } from "@/lib/formatters";
import type { GoalProjectionPoint } from "@/lib/nestegg/future-value";
import { Target } from "lucide-react";

const NEON = {
  cyan: "#00fff5",
  green: "#39ff14",
  pink: "#ff00ff",
  yellow: "#ffff00",
  muted: "#7a7a8c",
};

type Props = {
  series: GoalProjectionPoint[];
  goalAmount: number;
  targetYear: number;
  requiredMonthly: number;
  currentMonthly: number;
  currentPathEndBalance: number;
  escalationPercent: number;
};

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: Record<string, number> }>;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div
      className="rounded-lg border border-[#39ff14]/25 px-3 py-2 text-xs shadow-lg"
      style={{ backgroundColor: "rgba(15, 15, 26, 0.95)" }}
    >
      <p className="font-mono text-[#00fff5] mb-1">{row.year}</p>
      <ul className="space-y-0.5 font-mono text-[11px]">
        <li className="text-[#39ff14]">Goal pace: {formatCurrency(row.goalPath)}</li>
        <li className="text-[#00fff5]">Current pace: {formatCurrency(row.currentPath)}</li>
        <li className="text-[#ffff00]">Goal: {formatCurrency(row.goalLine)}</li>
      </ul>
    </div>
  );
}

export function NesteggGoalChart({
  series,
  goalAmount,
  targetYear,
  requiredMonthly,
  currentMonthly,
  currentPathEndBalance,
  escalationPercent,
}: Props) {
  const gap = goalAmount - currentPathEndBalance;
  const onTrack = currentPathEndBalance >= goalAmount;

  return (
    <Card className="border-[#39ff14]/20 bg-card/85 backdrop-blur-sm h-full shadow-[0_0_32px_-8px_rgba(57,255,20,0.12)]">
      <CardHeader className="pb-2 space-y-2">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#39ff14]/12 ring-1 ring-[#39ff14]/20">
            <Target className="h-5 w-5 text-[#39ff14]" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-[#39ff14]">
              Goal tracker
            </h3>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Reach {formatCurrency(goalAmount)} by {targetYear} — green line shows the
              pace you need, cyan shows your current trajectory
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="h-[280px] sm:h-[320px] min-h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={series}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(57, 255, 20, 0.08)"
                vertical={false}
              />
              <XAxis
                dataKey="year"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickLine={false}
                axisLine={false}
                tick={{ fill: NEON.muted, fontSize: 10 }}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tick={{ fill: NEON.muted, fontSize: 10 }}
                tickFormatter={(v) =>
                  v >= 1_000_000
                    ? `$${(v / 1_000_000).toFixed(1)}M`
                    : `$${(v / 1000).toFixed(0)}k`
                }
              />
              <Tooltip
                content={(props) => (
                  <ChartTooltip
                    active={props.active}
                    payload={props.payload as Array<{ payload: Record<string, number> }>}
                  />
                )}
              />
              <Legend
                wrapperStyle={{ fontSize: 11 }}
                formatter={(value) => (
                  <span className="text-muted-foreground uppercase tracking-wider">
                    {value}
                  </span>
                )}
              />
              <Line
                type="monotone"
                dataKey="goalPath"
                name="Goal pace"
                stroke={NEON.green}
                strokeWidth={2.5}
                dot={false}
                style={{ filter: `drop-shadow(0 0 8px ${NEON.green})` }}
              />
              <Line
                type="monotone"
                dataKey="currentPath"
                name="Current pace"
                stroke={NEON.cyan}
                strokeWidth={2}
                dot={false}
                style={{ filter: `drop-shadow(0 0 6px ${NEON.cyan})` }}
              />
              <ReferenceLine
                y={goalAmount}
                stroke={NEON.yellow}
                strokeDasharray="6 4"
                strokeOpacity={0.6}
                label={{
                  value: "Goal",
                  fill: NEON.yellow,
                  fontSize: 10,
                  position: "right",
                }}
              />
              <ReferenceLine
                x={targetYear}
                stroke={NEON.pink}
                strokeDasharray="4 4"
                strokeOpacity={0.5}
                label={{
                  value: String(targetYear),
                  fill: NEON.pink,
                  fontSize: 10,
                  position: "top",
                }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {/* Summary metrics */}
        <div className="grid gap-2 sm:grid-cols-3 text-xs rounded-lg border border-[#39ff14]/15 bg-[#39ff14]/[0.03] p-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Required monthly
            </p>
            <p className="font-mono font-semibold text-[#39ff14] mt-0.5">
              {formatCurrency(requiredMonthly)}/mo
              {escalationPercent > 0 ? (
                <span className="text-muted-foreground font-normal ml-1">
                  +{escalationPercent}%/yr
                </span>
              ) : null}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              At current rate ({formatCurrency(currentMonthly)}/mo)
            </p>
            <p className="font-mono font-semibold text-[#00fff5] mt-0.5">
              {formatCurrency(currentPathEndBalance)}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {onTrack ? "Surplus" : "Gap"}
            </p>
            <p
              className={`font-mono font-semibold mt-0.5 ${
                onTrack ? "text-[#39ff14]" : "text-[#ff3366]"
              }`}
            >
              {onTrack ? "+" : "-"}
              {formatCurrency(Math.abs(gap))}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
