"use client";

import Link from "next/link";
import { BarChart2, GitCompare, Target } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { NesteggProjectionChart } from "./NesteggProjectionChart";
import { NesteggSecondaryChart } from "./NesteggSecondaryChart";
import { NesteggGoalChart } from "./NesteggGoalChart";
import type { GoalProjectionResult } from "@/lib/nestegg/future-value";

type CompareRow = {
  age: number;
  base: number;
  conservative: number;
  aggressive: number;
};

type CashflowRow = {
  year: string;
  expenses: number;
  income: number;
};

type Props = {
  cashflowData: CashflowRow[];
  compareData: CompareRow[];
  retirementAge: number;
  depletionAge: number | null;
  lifeExpectancy: number;
  goalProjection: GoalProjectionResult | null;
  goalAmount: number;
  goalYear: number | null;
  currentMonthly: number;
  escalationPercent: number;
  goalProbability?: number | null;
};

export function NesteggChartTabs({
  cashflowData,
  compareData,
  retirementAge,
  depletionAge,
  lifeExpectancy,
  goalProjection,
  goalAmount,
  goalYear,
  currentMonthly,
  escalationPercent,
  goalProbability,
}: Props) {
  return (
    <Tabs defaultValue="cashflow" className="space-y-2">
      <TabsList className="bg-card/50 border border-[#00fff5]/20 h-auto p-1 gap-1 ring-1 ring-[#00fff5]/5 w-full grid grid-cols-3">
        <TabsTrigger
          value="cashflow"
          className="text-xs uppercase tracking-wider py-2 rounded-md data-[state=active]:bg-[#ff00ff]/12 data-[state=active]:text-[#ff99ff] data-[state=active]:shadow-[0_0_12px_-4px_rgba(255,0,255,0.3)] data-[state=active]:ring-1 data-[state=active]:ring-[#ff00ff]/30"
        >
          <BarChart2 className="mr-1.5 h-3.5 w-3.5" aria-hidden />
          Cash flow
        </TabsTrigger>
        <TabsTrigger
          value="comparison"
          className="text-xs uppercase tracking-wider py-2 rounded-md data-[state=active]:bg-[#00fff5]/12 data-[state=active]:text-[#00fff5] data-[state=active]:shadow-[0_0_12px_-4px_rgba(0,255,245,0.3)] data-[state=active]:ring-1 data-[state=active]:ring-[#00fff5]/30"
        >
          <GitCompare className="mr-1.5 h-3.5 w-3.5" aria-hidden />
          Comparison
        </TabsTrigger>
        <TabsTrigger
          value="goal"
          className="text-xs uppercase tracking-wider py-2 rounded-md data-[state=active]:bg-[#39ff14]/12 data-[state=active]:text-[#39ff14] data-[state=active]:shadow-[0_0_12px_-4px_rgba(57,255,20,0.3)] data-[state=active]:ring-1 data-[state=active]:ring-[#39ff14]/30"
        >
          <Target className="mr-1.5 h-3.5 w-3.5" aria-hidden />
          Goal
        </TabsTrigger>
      </TabsList>
      <TabsContent value="cashflow" className="mt-0 min-h-[420px]">
        <NesteggSecondaryChart data={cashflowData} />
      </TabsContent>
      <TabsContent value="comparison" className="mt-0 min-h-[420px]">
        <NesteggProjectionChart
          singleSeries={[]}
          compareMode
          compareData={compareData}
          retirementAge={retirementAge}
          depletionAge={depletionAge}
          lifeExpectancy={lifeExpectancy}
          monteCarloBands={null}
        />
      </TabsContent>
      <TabsContent value="goal" className="mt-0 min-h-[420px]">
        {goalProjection && goalYear ? (
          <NesteggGoalChart
            projection={goalProjection}
            goalAmount={goalAmount}
            targetYear={goalYear}
            currentMonthly={currentMonthly}
            escalationPercent={escalationPercent}
            goalProbability={goalProbability}
          />
        ) : (
          <div className="flex flex-col items-center justify-center py-16 text-center space-y-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#39ff14]/12 ring-1 ring-[#39ff14]/20">
              <Target className="h-5 w-5 text-[#39ff14]" aria-hidden />
            </div>
            <p className="text-sm text-muted-foreground max-w-sm">
              Set a portfolio goal and target year on your{" "}
              <Link
                href="/portfolio"
                className="text-[#39ff14]/80 hover:text-[#39ff14] underline underline-offset-2"
              >
                Portfolio page
              </Link>{" "}
              to see how much you need to save each month.
            </p>
          </div>
        )}
      </TabsContent>
    </Tabs>
  );
}
