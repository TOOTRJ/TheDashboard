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
import type { GoalProjectionResult, GoalProjectionPoint } from "@/lib/nestegg/future-value";
import { CheckCircle, Target, AlertTriangle, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

const NEON = {
  cyan: "#00fff5",
  green: "#39ff14",
  pink: "#ff00ff",
  yellow: "#ffff00",
  muted: "#7a7a8c",
};

type Props = {
  projection: GoalProjectionResult;
  goalAmount: number;
  targetYear: number;
  currentMonthly: number;
  escalationPercent: number;
  /** Reserved for a future goal-date model; no calibrated probability is currently displayed. */
  goalProbability?: number | null;
};

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: GoalProjectionPoint }>;
}) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  return (
    <div
      className="rounded-lg border border-[#39ff14]/25 px-3 py-2 text-xs shadow-lg"
      style={{ backgroundColor: "rgba(15, 15, 26, 0.95)" }}
    >
      <p className="font-mono text-[#00fff5] mb-1">{row.year}</p>
      <ul className="space-y-0.5 font-mono text-[11px]">
        <li className="text-[#39ff14]">Goal pace: {row.goalPath === null ? "Unavailable" : formatCurrency(row.goalPath)}</li>
        <li className="text-[#00fff5]">Current pace: {formatCurrency(row.currentPath)}</li>
        <li className="text-[#ffff00]">Goal: {formatCurrency(row.goalLine)}</li>
      </ul>
    </div>
  );
}

export function NesteggGoalChart({
  projection,
  goalAmount,
  targetYear,
  currentMonthly,
  escalationPercent,
}: Props) {
  const {
    requiredMonthly,
    series,
    currentPathEndBalance,
    totalContributed,
    totalGrowth,
    status,
    progressPercent,
    extraSavingsNeeded,
    yearsAtCurrentPace,
    inflationAdjustedGoal,
    timelineSensitivity,
    returnSensitivity,
  } = projection;

  const gap = goalAmount - currentPathEndBalance;

  const statusConfig = {
    ahead: {
      icon: CheckCircle,
      color: "text-[#39ff14]",
      bg: "bg-[#39ff14]/10",
      border: "border-[#39ff14]/20",
      label: "Ahead of schedule",
      message: "Your portfolio growth alone is projected to exceed your goal — no additional savings required.",
    },
    "on-track": {
      icon: CheckCircle,
      color: "text-[#00fff5]",
      bg: "bg-[#00fff5]/10",
      border: "border-[#00fff5]/20",
      label: "On track",
      message: "At your current savings rate, you're projected to reach your goal by the target year.",
    },
    behind: {
      icon: AlertTriangle,
      color: "text-[#ffff00]",
      bg: "bg-[#ffff00]/10",
      border: "border-[#ffff00]/20",
      label: "Needs adjustment",
      message: extraSavingsNeeded !== null && extraSavingsNeeded > 0
        ? `Save about ${formatCurrency(extraSavingsNeeded)} more per month to get on track.`
        : "Consider extending your timeline or adjusting your goal.",
    },
    "above-limit": {
      icon: AlertTriangle,
      color: "text-[#ffff00]",
      bg: "bg-[#ffff00]/10",
      border: "border-[#ffff00]/20",
      label: "Above calculation limit",
      message: "This projection needs more than $200,000/month in initial savings. Extend the timeline or lower the target to calculate a goal pace.",
    },
    "invalid-input": {
      icon: AlertTriangle,
      color: "text-[#ff3366]",
      bg: "bg-[#ff3366]/10",
      border: "border-[#ff3366]/20",
      label: "Check goal inputs",
      message: "Use finite nonnegative balances and savings, whole months within 100 years, and supported return assumptions.",
    },
    "past-deadline": {
      icon: AlertTriangle,
      color: "text-[#ff3366]",
      bg: "bg-[#ff3366]/10",
      border: "border-[#ff3366]/20",
      label: "Target year has passed",
      message: "Update your target year on the Portfolio page to see a new projection.",
    },
    "no-goal": {
      icon: Target,
      color: "text-muted-foreground",
      bg: "bg-muted/10",
      border: "border-muted/20",
      label: "No goal set",
      message: "Set a goal on your Portfolio page.",
    },
  };

  const sc = statusConfig[status];
  const StatusIcon = sc.icon;

  if (status === "invalid-input" || status === "past-deadline" || status === "no-goal") {
    return (
      <Card className="border-[#39ff14]/20 bg-card/85 h-full">
        <CardHeader className="space-y-2">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-[#39ff14]">Goal tracker</h3>
          <p className={sc.color}>{sc.label}</p>
          <p className="text-xs text-muted-foreground">{sc.message}</p>
        </CardHeader>
      </Card>
    );
  }

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
              Reach {formatCurrency(goalAmount)} by {targetYear}
              <span className="text-muted-foreground/70 ml-1">
                ({formatCurrency(inflationAdjustedGoal)} in today&apos;s dollars)
              </span>
            </p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="space-y-1">
          <div className="flex justify-between text-[10px]">
            <span className="text-muted-foreground">{progressPercent}% of goal</span>
            <span className="font-mono text-[#39ff14]">{formatCurrency(projection.series[0]?.currentPath ?? 0)} / {formatCurrency(goalAmount)}</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-[#39ff14]/10 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[#39ff14]/60 to-[#00fff5]/60 transition-[width] duration-300"
              style={{ width: `${Math.min(100, progressPercent)}%` }}
            />
          </div>
        </div>

        {/* Status badge */}
        <div className={cn("flex items-center gap-2 rounded-lg px-3 py-2 text-xs", sc.bg, sc.border, "border")}>
          <StatusIcon className={cn("h-4 w-4 shrink-0", sc.color)} />
          <div>
            <span className={cn("font-semibold", sc.color)}>{sc.label}</span>
            <span className="text-muted-foreground ml-1.5">{sc.message}</span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Chart */}
        {series.length > 1 ? (
          <div className="h-[260px] sm:h-[300px] min-h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={series}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(57, 255, 20, 0.08)" vertical={false} />
                <XAxis dataKey="year" type="number" domain={["dataMin", "dataMax"]} tickLine={false} axisLine={false} tick={{ fill: NEON.muted, fontSize: 10 }} />
                <YAxis tickLine={false} axisLine={false} tick={{ fill: NEON.muted, fontSize: 10 }} tickFormatter={(v) => v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(1)}M` : `$${(v / 1000).toFixed(0)}k`} />
                <Tooltip content={(props) => <ChartTooltip active={props.active} payload={props.payload} />} />
                <Legend wrapperStyle={{ fontSize: 11 }} formatter={(value) => <span className="text-muted-foreground uppercase tracking-wider">{value}</span>} />
                <Line type="monotone" dataKey="goalPath" name="Goal pace" stroke={NEON.green} strokeWidth={2.5} dot={false} style={{ filter: `drop-shadow(0 0 8px ${NEON.green})` }} />
                <Line type="monotone" dataKey="currentPath" name="Current pace" stroke={NEON.cyan} strokeWidth={2} dot={false} style={{ filter: `drop-shadow(0 0 6px ${NEON.cyan})` }} />
                <ReferenceLine y={goalAmount} stroke={NEON.yellow} strokeDasharray="6 4" strokeOpacity={0.6} label={{ value: "Goal", fill: NEON.yellow, fontSize: 10, position: "right" }} />
                <ReferenceLine x={targetYear} stroke={NEON.pink} strokeDasharray="4 4" strokeOpacity={0.5} label={{ value: String(targetYear), fill: NEON.pink, fontSize: 10, position: "top" }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        {/* Primary metrics */}
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 text-xs rounded-lg border border-[#39ff14]/15 bg-[#39ff14]/[0.03] p-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Required monthly</p>
            <p className="font-mono font-semibold text-[#39ff14] mt-0.5">
              {requiredMonthly === null ? "Unavailable" : requiredMonthly > 0 ? `${formatCurrency(requiredMonthly)}/mo` : "None needed"}
              {escalationPercent > 0 && requiredMonthly !== null && requiredMonthly > 0 ? <span className="text-muted-foreground font-normal ml-1">+{escalationPercent}%/yr</span> : null}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Extra savings needed</p>
            <p className={cn("font-mono font-semibold mt-0.5", extraSavingsNeeded !== null && extraSavingsNeeded > 0 ? "text-[#ffff00]" : "text-[#39ff14]")}>
              {extraSavingsNeeded === null ? "Unavailable" : extraSavingsNeeded > 0 ? `+${formatCurrency(extraSavingsNeeded)}/mo` : "None needed"}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">At current rate ({formatCurrency(currentMonthly)}/mo)</p>
            <p className="font-mono font-semibold text-[#00fff5] mt-0.5">{formatCurrency(currentPathEndBalance)}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {currentPathEndBalance >= goalAmount ? "Surplus" : "Gap"}
            </p>
            <p className={cn("font-mono font-semibold mt-0.5", currentPathEndBalance >= goalAmount ? "text-[#39ff14]" : "text-[#ff3366]")}>
              {currentPathEndBalance >= goalAmount ? "+" : "-"}{formatCurrency(Math.abs(gap))}
            </p>
          </div>
        </div>

        {/* Contributions vs Growth + Years at current pace + MC probability */}
        <div className="grid gap-2 sm:grid-cols-3 text-xs rounded-lg border border-[#00fff5]/15 bg-[#00fff5]/[0.03] p-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Contributions needed</p>
            <p className="font-mono font-semibold text-[#00fff5] mt-0.5">{totalContributed === null ? "Unavailable" : formatCurrency(totalContributed)}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Investment growth / loss</p>
            <p className="font-mono font-semibold text-[#bf00ff] mt-0.5">{totalGrowth === null ? "Unavailable" : formatCurrency(totalGrowth)}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Years at current pace
            </p>
            <p className="font-mono font-semibold mt-0.5">
              {yearsAtCurrentPace !== null ? (
                <span className={yearsAtCurrentPace <= (targetYear - new Date().getFullYear()) ? "text-[#39ff14]" : "text-[#ffff00]"}>
                  {yearsAtCurrentPace === 0 ? "Already there" : `~${yearsAtCurrentPace} yrs`}
                </span>
              ) : (
                <span className="text-muted-foreground">Not reached within 80 years</span>
              )}
            </p>
          </div>
        </div>

        {/* Sensitivity tables */}
        {timelineSensitivity.length > 0 ? (
          <div className="rounded-lg border border-[#ff00ff]/15 bg-[#ff00ff]/[0.02] p-3 space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#ff99ff]/80">
              Timeline sensitivity
            </p>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
              {timelineSensitivity.map((row) => (
                <div key={row.year} className={cn("font-mono", row.year === targetYear ? "text-[#39ff14] font-semibold" : "text-muted-foreground")}>
                  {row.year}: {row.requiredMonthly !== null && row.requiredMonthly > 0 ? `${formatCurrency(row.requiredMonthly)}/mo` : row.requiredMonthly === 0 ? "None" : "Above limit / unavailable"}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {returnSensitivity.length > 0 ? (
          <div className="rounded-lg border border-[#bf00ff]/15 bg-[#bf00ff]/[0.02] p-3 space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#bf00ff]/80">
              Return sensitivity
            </p>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
              {returnSensitivity.map((row) => (
                <div key={row.returnPercent} className={cn("font-mono", row.returnPercent === Math.round(projection.series.length > 0 ? 7 : 0) ? "text-[#39ff14] font-semibold" : "text-muted-foreground")}>
                  {row.returnPercent}%: {row.requiredMonthly !== null && row.requiredMonthly > 0 ? `${formatCurrency(row.requiredMonthly)}/mo` : row.requiredMonthly === 0 ? "None" : "Above limit / unavailable"}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
