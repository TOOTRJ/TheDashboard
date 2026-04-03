"use client";

import { Download, FileText, MoreHorizontal } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  buildNesteggScenarioCsv,
  downloadNesteggCsv,
  openNesteggPrintReport,
} from "@/lib/nestegg/export-report";
import type { MonteCarloResult } from "@/lib/nestegg/monte-carlo";
import type { NesteggInputs, NesteggScenarioId } from "@/lib/nestegg/types";
import type { ProjectionResult } from "@/lib/nestegg/types";

type Props = {
  inputs: NesteggInputs;
  marketScenario: NesteggScenarioId;
  deterministic: ProjectionResult;
  monteCarlo: MonteCarloResult | null;
};

export function NesteggExportMenu({
  inputs,
  marketScenario,
  deterministic,
  monteCarlo,
}: Props) {
  const stamp = new Date().toISOString().slice(0, 10);

  const csv = () => {
    const content = buildNesteggScenarioCsv(
      inputs,
      marketScenario,
      deterministic,
      monteCarlo
    );
    downloadNesteggCsv(`nestegg-${stamp}.csv`, content);
    toast.success("Download started");
  };

  const printPdf = () => {
    openNesteggPrintReport({
      title: `Nestegg — ${stamp}`,
      inputs,
      marketScenario,
      deterministic,
      mc: monteCarlo,
    });
    toast.message("Print dialog opened — choose Save as PDF if you like");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-9 border-[#bf00ff]/25 bg-[#bf00ff]/5 text-xs hover:bg-[#bf00ff]/15 hover:text-[#ff99ff]"
        >
          <MoreHorizontal className="mr-2 h-4 w-4" />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="border-[#bf00ff]/20 bg-card/95 backdrop-blur-xl min-w-[200px]"
      >
        <DropdownMenuItem
          className="text-xs gap-2 cursor-pointer"
          onSelect={(e) => {
            e.preventDefault();
            csv();
          }}
        >
          <Download className="h-3.5 w-3.5 text-[#00fff5]" />
          Download CSV
        </DropdownMenuItem>
        <DropdownMenuItem
          className="text-xs gap-2 cursor-pointer"
          onSelect={(e) => {
            e.preventDefault();
            printPdf();
          }}
        >
          <FileText className="h-3.5 w-3.5 text-[#ff99ff]" />
          Print / Save as PDF
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
