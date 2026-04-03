"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { formatCurrency } from "@/lib/formatters";
import { BarChart2 } from "lucide-react";

const NEON = {
  cyan: "#00fff5",
  pink: "#ff00ff",
  muted: "#7a7a8c",
};

type Row = { year: string; expenses: number; income: number };

type Props = {
  data: Row[];
};

export function NesteggSecondaryChart({ data }: Props) {
  return (
    <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm h-full flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#ff00ff]/10">
            <BarChart2 className="h-4 w-4 text-[#ff00ff]" aria-hidden />
          </div>
          <div>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-[#ff00ff]">
              Retirement cash flow
            </h3>
            <p className="text-[11px] text-muted-foreground">
              Annual income vs expenses in early retirement (inflation-adjusted path)
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="h-[280px] sm:h-[320px] flex-1 min-h-[240px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255, 0, 255, 0.08)"
              vertical={false}
            />
            <XAxis
              dataKey="year"
              tickLine={false}
              axisLine={false}
              tick={{ fill: NEON.muted, fontSize: 9 }}
              interval={0}
              angle={-35}
              textAnchor="end"
              height={48}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={{ fill: NEON.muted, fontSize: 10 }}
              tickFormatter={(v) =>
                v >= 1000 ? `$${(v / 1000).toFixed(0)}k` : `$${v}`
              }
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                return (
                  <div
                    className="rounded-lg border border-[#ff00ff]/25 px-3 py-2 text-xs font-mono shadow-lg"
                    style={{
                      backgroundColor: "rgba(15, 15, 26, 0.95)",
                    }}
                  >
                    {payload.map((entry) => (
                      <p key={String(entry.dataKey)} className="text-foreground">
                        <span className="text-muted-foreground">
                          {entry.dataKey === "expenses" ? "Expenses" : "Income"}:{" "}
                        </span>
                        {formatCurrency(Number(entry.value ?? 0))}
                      </p>
                    ))}
                  </div>
                );
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: 11 }}
              formatter={(value) => (
                <span className="text-muted-foreground capitalize">{value}</span>
              )}
            />
            <Bar
              dataKey="income"
              name="income"
              fill={NEON.cyan}
              radius={[4, 4, 0, 0]}
              style={{ filter: `drop-shadow(0 0 6px ${NEON.cyan})` }}
            />
            <Bar
              dataKey="expenses"
              name="expenses"
              fill={NEON.pink}
              radius={[4, 4, 0, 0]}
              style={{ filter: `drop-shadow(0 0 6px ${NEON.pink})` }}
            />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
