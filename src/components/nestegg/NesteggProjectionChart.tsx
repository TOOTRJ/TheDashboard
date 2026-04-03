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
import type { MonteCarloBandPoint } from "@/lib/nestegg/monte-carlo";
import type { ProjectionPoint } from "@/lib/nestegg/types";
import { cn } from "@/lib/utils";
import { LineChart as LineChartIcon } from "lucide-react";

const NEON = {
  cyan: "#00fff5",
  pink: "#ff00ff",
  green: "#39ff14",
  yellow: "#ffff00",
  muted: "#7a7a8c",
};

type CompareRow = {
  age: number;
  base: number;
  conservative: number;
  aggressive: number;
};

type Props = {
  singleSeries: ProjectionPoint[];
  compareMode: boolean;
  compareData: CompareRow[];
  retirementAge: number;
  depletionAge: number | null;
  lifeExpectancy: number;
  /** When set and not in compare mode, show median path + percentile rails. */
  monteCarloBands?: MonteCarloBandPoint[] | null;
  /** Optional horizontal goal line on the chart. */
  goalAmount?: number | null;
  className?: string;
};

function ChartTooltip({
  active,
  payload,
  compareMode,
  bandMode,
}: {
  active?: boolean;
  payload?: Array<{ payload: Record<string, number> }>;
  compareMode: boolean;
  bandMode: boolean;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div
      className="rounded-lg border border-[#00fff5]/25 px-3 py-2 text-xs shadow-lg"
      style={{
        backgroundColor: "rgba(15, 15, 26, 0.95)",
      }}
    >
      <p className="font-mono text-[#00fff5] mb-1">Age {row.age}</p>
      {compareMode ? (
        <ul className="space-y-0.5 font-mono text-[11px]">
          <li className="text-[#00fff5]">Base: {formatCurrency(row.base)}</li>
          <li className="text-[#ffff00]">
            Conservative: {formatCurrency(row.conservative)}
          </li>
          <li className="text-[#ff00ff]">
            Aggressive: {formatCurrency(row.aggressive)}
          </li>
        </ul>
      ) : bandMode ? (
        <ul className="space-y-0.5 font-mono text-[11px] text-muted-foreground">
          <li className="text-[#39ff14]">Median: {formatCurrency(row.p50)}</li>
          <li>90th pct: {formatCurrency(row.p90)}</li>
          <li>10th pct: {formatCurrency(row.p10)}</li>
        </ul>
      ) : (
        <p className="font-mono text-foreground">
          {formatCurrency(row.balance as number)}
        </p>
      )}
    </div>
  );
}

export function NesteggProjectionChart({
  singleSeries,
  compareMode,
  compareData,
  retirementAge,
  depletionAge,
  lifeExpectancy,
  monteCarloBands,
  goalAmount,
  className,
}: Props) {
  const bandMode = Boolean(!compareMode && monteCarloBands && monteCarloBands.length > 0);

  const data = compareMode
    ? compareData
    : bandMode
      ? monteCarloBands!
      : singleSeries.map((p) => ({ age: p.age, balance: p.balance }));

  const depletionX =
    depletionAge !== null && depletionAge <= lifeExpectancy
      ? Math.round(depletionAge * 10) / 10
      : null;

  return (
    <Card
      className={cn(
        "border-[#00fff5]/25 bg-card/85 backdrop-blur-sm h-full shadow-[0_0_32px_-8px_rgba(0,255,245,0.12)]",
        className
      )}
    >
      <CardHeader className="pb-2 space-y-2">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#00fff5]/12 ring-1 ring-[#00fff5]/20">
            <LineChartIcon className="h-5 w-5 text-[#00fff5]" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">
              Your wealth over time
            </h3>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {bandMode
                ? "Typical path with a stress and upside band from the simulation"
                : compareMode
                  ? "Three market presets on the same inputs — compare curves at a glance"
                  : "Growth while you save, then drawdown after you retire — through your planning horizon"}
            </p>
            <p className="text-[11px] text-muted-foreground/90 mt-2 leading-snug border-t border-[#00fff5]/10 pt-2">
              {bandMode
                ? "The green line is the median path; faded lines show softer vs tougher outcomes."
                : "Watch this line move when you change savings, retirement age, or spending. Markers show retirement and, if modeled, when the balance may reach zero."}
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="h-[320px] sm:h-[400px] min-h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data}>
            <defs>
              <linearGradient id="nesteggLine" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor={NEON.cyan} stopOpacity={0.5} />
                <stop offset="50%" stopColor={NEON.cyan} stopOpacity={1} />
                <stop offset="100%" stopColor={NEON.pink} stopOpacity={0.6} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(0, 255, 245, 0.08)"
              vertical={false}
            />
            <XAxis
              dataKey="age"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickLine={false}
              axisLine={false}
              tick={{ fill: NEON.muted, fontSize: 10 }}
              label={{
                value: "Age",
                position: "insideBottom",
                offset: -4,
                fill: NEON.muted,
                fontSize: 10,
              }}
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
                  compareMode={compareMode}
                  bandMode={bandMode}
                />
              )}
            />
            {compareMode ? (
              <>
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
                  dataKey="base"
                  name="Base"
                  stroke={NEON.cyan}
                  strokeWidth={2}
                  dot={false}
                  style={{ filter: `drop-shadow(0 0 6px ${NEON.cyan})` }}
                />
                <Line
                  type="monotone"
                  dataKey="conservative"
                  name="Conservative"
                  stroke={NEON.yellow}
                  strokeWidth={2}
                  dot={false}
                  style={{ filter: `drop-shadow(0 0 6px ${NEON.yellow})` }}
                />
                <Line
                  type="monotone"
                  dataKey="aggressive"
                  name="Aggressive"
                  stroke={NEON.pink}
                  strokeWidth={2}
                  dot={false}
                  style={{ filter: `drop-shadow(0 0 6px ${NEON.pink})` }}
                />
              </>
            ) : bandMode ? (
              <>
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
                  dataKey="p90"
                  name="90th pct"
                  stroke={NEON.cyan}
                  strokeWidth={1}
                  strokeOpacity={0.45}
                  dot={false}
                  strokeDasharray="4 4"
                />
                <Line
                  type="monotone"
                  dataKey="p50"
                  name="Median path"
                  stroke={NEON.green}
                  strokeWidth={2.5}
                  dot={false}
                  style={{ filter: `drop-shadow(0 0 8px ${NEON.green})` }}
                />
                <Line
                  type="monotone"
                  dataKey="p10"
                  name="10th pct"
                  stroke={NEON.pink}
                  strokeWidth={1}
                  strokeOpacity={0.45}
                  dot={false}
                  strokeDasharray="4 4"
                />
              </>
            ) : (
              <Line
                type="monotone"
                dataKey="balance"
                name="Portfolio"
                stroke="url(#nesteggLine)"
                strokeWidth={2.5}
                dot={false}
                style={{ filter: `drop-shadow(0 0 8px ${NEON.cyan})` }}
              />
            )}
            <ReferenceLine
              x={retirementAge}
              stroke={NEON.pink}
              strokeDasharray="4 4"
              label={{
                value: "Retire",
                fill: NEON.pink,
                fontSize: 10,
                position: "top",
              }}
            />
            {depletionX !== null ? (
              <ReferenceLine
                x={depletionX}
                stroke={NEON.green}
                strokeDasharray="4 4"
                label={{
                  value: "~Deplete",
                  fill: NEON.green,
                  fontSize: 10,
                  position: "top",
                }}
              />
            ) : null}
            {goalAmount && goalAmount > 0 ? (
              <ReferenceLine
                y={goalAmount}
                stroke={NEON.yellow}
                strokeDasharray="6 4"
                strokeOpacity={0.5}
                label={{
                  value: "Goal",
                  fill: NEON.yellow,
                  fontSize: 10,
                  position: "right",
                }}
              />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
