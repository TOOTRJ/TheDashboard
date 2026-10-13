"use client";

import * as React from "react";
import { FileText, Download, ArrowUpRight, ArrowDownLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";

const reports = [
  {
    id: "pnl",
    title: "P&L Statement",
    description: "Example layout for profit and loss by asset and period.",
    icon: ArrowUpRight,
    color: "#39ff14",
  },
  {
    id: "portfolio",
    title: "Portfolio Snapshot",
    description: "Example layout for holdings and allocation.",
    icon: FileText,
    color: "#00fff5",
  },
  {
    id: "tax",
    title: "Tax Report",
    description: "Report concept only; tax calculations are not available.",
    icon: Download,
    color: "#ff00ff",
  },
  {
    id: "trades",
    title: "Trade History Export",
    description: "Example layout for trade activity.",
    icon: ArrowDownLeft,
    color: "#bf00ff",
  },
];

const sampleTrades = [
  { id: 1, asset: "BTC", type: "Buy", amount: 0.15, value: 14178 },
  { id: 2, asset: "ETH", type: "Sell", amount: 3.2, value: 10234 },
  { id: 3, asset: "SOL", type: "Buy", amount: 45, value: 8340 },
  { id: 4, asset: "LINK", type: "Swap", amount: 120, value: 2388 },
];

export default function ReportsPage() {
  const [previewReport, setPreviewReport] = React.useState<(typeof reports)[number] | null>(null);

  return (
    <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
      <div className="lg:col-span-2 rounded-lg border border-[#00fff5]/20 bg-[#00fff5]/5 p-4">
        <Badge variant="outline">Sample report preview</Badge>
        <p className="mt-2 text-sm text-muted-foreground">
          All figures and trades on this page are examples. They do not reflect your account or bot activity.
        </p>
      </div>
      <div className="space-y-4">
        <div className="mb-6">
          <h2 className="text-lg font-semibold uppercase tracking-wider text-[#00fff5] neon-text-cyan">
            Report Previews
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            Explore example layouts. Report generation and downloads are not available yet.
          </p>
        </div>
        
        {reports.map((report) => {
          const Icon = report.icon;
          return (
            <Card 
              key={report.id}
              className="border-[#00fff5]/10 bg-card/80 backdrop-blur-sm hover:border-[#00fff5]/30 transition-all card-hover-glow"
            >
              <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <div 
                    className="flex h-10 w-10 items-center justify-center rounded-lg"
                    style={{ backgroundColor: `${report.color}15` }}
                  >
                    <Icon className="h-5 w-5" style={{ color: report.color }} />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold" style={{ color: report.color }}>
                      {report.title}
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">{report.description}</p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button 
                    type="button"
                    variant="outline" 
                    size="sm"
                    className="border-[#00fff5]/20 hover:bg-[#00fff5]/10 hover:text-[#00fff5]"
                    onClick={() => setPreviewReport(report)}
                  >
                    Sample Preview
                  </Button>
                  <Button 
                    size="sm"
                    type="button"
                    disabled
                    aria-describedby={`report-unavailable-${report.id}`}
                    className="bg-gradient-to-r from-[#00fff5] to-[#ff00ff] text-black hover:opacity-90"
                  >
                    <Download className="mr-2 h-4 w-4" />
                    Generate unavailable
                  </Button>
                </div>
              </CardHeader>
              <CardContent id={`report-unavailable-${report.id}`} className="text-xs text-muted-foreground pt-0">
                Account report generation is not available yet. No report has been created here.
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="space-y-4">
        <Card className="border-[#ff00ff]/20 bg-card/80 backdrop-blur-sm">
          <CardHeader>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-[#ff00ff]">
              Sample Summary
            </h3>
            <p className="text-xs text-muted-foreground">
              Illustrative figures only; no account history has been loaded.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg border border-[#00fff5]/20 bg-[#00fff5]/5 p-3 text-center">
                <p className="text-xl font-bold font-mono text-[#00fff5]">127</p>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-1">
                  Total Trades
                </p>
              </div>
              <div className="rounded-lg border border-[#39ff14]/20 bg-[#39ff14]/5 p-3 text-center">
                <p className="text-xl font-bold font-mono text-[#39ff14]">+$18.5k</p>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-1">
                  Total P&L
                </p>
              </div>
            </div>
            
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Sample Activity</p>
              {sampleTrades.map((trade) => (
                <div 
                  key={trade.id}
                  className="flex items-center justify-between rounded-lg border border-[#00fff5]/10 bg-[#00fff5]/5 p-2"
                >
                  <div className="flex items-center gap-2">
                    <Badge 
                      variant="outline"
                      className={
                        trade.type === "Buy" 
                          ? "border-[#39ff14]/30 bg-[#39ff14]/10 text-[#39ff14]"
                          : trade.type === "Sell"
                            ? "border-[#ff3366]/30 bg-[#ff3366]/10 text-[#ff3366]"
                            : "border-[#00fff5]/30 bg-[#00fff5]/10 text-[#00fff5]"
                      }
                    >
                      {trade.type}
                    </Badge>
                    <span className="text-sm font-medium">{trade.asset}</span>
                    <span className="text-xs text-muted-foreground">{trade.amount}</span>
                  </div>
                  <div className="text-right">
                    <p className="text-xs font-mono text-[#00fff5]">${trade.value.toLocaleString("en-US")}</p>
                    <p className="text-[10px] text-muted-foreground">Example trade {trade.id}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="border-[#bf00ff]/20 bg-card/80 backdrop-blur-sm">
          <CardHeader>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-[#bf00ff]">
              Export Availability
            </h3>
          </CardHeader>
          <CardContent className="space-y-3 text-xs text-muted-foreground">
            <p>
              Downloads and tax reports are not available yet. These previews are not account statements or tax documents.
            </p>
          </CardContent>
        </Card>
      </div>

      <Sheet open={!!previewReport} onOpenChange={(open) => !open && setPreviewReport(null)}>
        <SheetContent side="right" className="w-full sm:max-w-lg border-l border-[#00fff5]/20 bg-card">
          <SheetHeader>
            <SheetTitle className="text-[#00fff5] uppercase tracking-wider">
              Sample {previewReport?.title ?? "Report"} Preview
            </SheetTitle>
            <SheetDescription>
              Illustrative layout only. No account data, tax calculation or downloadable report is included.
            </SheetDescription>
          </SheetHeader>
          <div className="mt-6 space-y-4">
            <p className="text-sm text-muted-foreground">
              These fixed example figures show a possible report layout. They do not describe your trading results.
            </p>
            
            <div className="rounded-lg border border-[#00fff5]/20 p-4">
              <h4 className="text-sm font-semibold text-[#00fff5] mb-3">Example Contents</h4>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#00fff5]" />
                  Sample activity and period summary
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#00fff5]" />
                  Example asset amounts
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#00fff5]" />
                  Illustrative profit and loss figures
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#00fff5]" />
                  No fee reconciliation or tax calculations
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#00fff5]" />
                  No verified wallet history
                </li>
              </ul>
            </div>
            
            <div className="rounded-lg border border-[#ff00ff]/20 bg-[#ff00ff]/5 p-4">
              <h4 className="text-sm font-semibold text-[#ff00ff] mb-2">Sample Data</h4>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-xs text-muted-foreground">Period</p>
                  <p className="font-mono">Jan 1 - Jan 22, 2026</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Total Trades</p>
                  <p className="font-mono">127</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Total Volume</p>
                  <p className="font-mono text-[#00fff5]">$245,892</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Net P&L</p>
                  <p className="font-mono text-[#39ff14]">+$18,523</p>
                </div>
              </div>
            </div>
            
            <Button 
              type="button"
              disabled
              aria-describedby="preview-report-unavailable"
              className="w-full bg-gradient-to-r from-[#00fff5] to-[#ff00ff] text-black hover:opacity-90"
            >
              <Download className="mr-2 h-4 w-4" />
              Generate unavailable
            </Button>
            <p id="preview-report-unavailable" className="text-xs text-muted-foreground">
              Account report generation is not available yet. This preview cannot be downloaded.
            </p>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
