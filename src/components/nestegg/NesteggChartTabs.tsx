"use client";

import { BarChart2, GitCompare } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { NesteggProjectionChart } from "./NesteggProjectionChart";
import { NesteggSecondaryChart } from "./NesteggSecondaryChart";

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
};

export function NesteggChartTabs({
  cashflowData,
  compareData,
  retirementAge,
  depletionAge,
  lifeExpectancy,
}: Props) {
  return (
    <Tabs defaultValue="cashflow" className="space-y-2">
      <TabsList className="bg-card/50 border border-[#00fff5]/20 h-auto p-1 gap-1 ring-1 ring-[#00fff5]/5 w-full grid grid-cols-2">
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
    </Tabs>
  );
}
