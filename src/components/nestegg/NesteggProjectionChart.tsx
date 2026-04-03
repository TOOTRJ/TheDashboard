"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { formatCurrency } from "@/lib/formatters";
import type { ProjectionPoint } from "@/lib/nestegg/types";
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
};

function ChartTooltip({
  active,
  payload,
  compareMode,
}: {
  active?: boolean;
  payload?: Array<{ payload: Record<string, number> }>;
  compareMode: boolean;
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
}: Props) {
  const data = compareMode
    ? compareData
    : singleSeries.map((p) => ({ age: p.age, balance: p.balance }));

  const depletionX =
    depletionAge !== null && depletionAge <= lifeExpectancy
      ? Math.round(depletionAge * 10) / 10
      : null;

  return (
    <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm h-full">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#00fff5]/10">
            <LineChartIcon className="h-4 w-4 text-[#00fff5]" aria-hidden />
          </div>
          <div>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">
              Net worth over time
            </h3>
            <p className="text-[11px] text-muted-foreground">
              Accumulation, retirement start, and drawdown through your horizon
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="h-[320px] sm:h-[380px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
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
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
