"use client";

import * as React from "react";
import { FileText, Loader2, Clock, Download, ArrowUpRight, ArrowDownLeft } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";

const reports = [
  {
    id: "pnl",
    title: "P&L Statement",
    description: "Detailed profit and loss breakdown by asset and time period.",
    lastGenerated: "Jan 22, 2026",
    icon: ArrowUpRight,
    color: "#39ff14",
  },
  {
    id: "portfolio",
    title: "Portfolio Snapshot",
    description: "Current holdings, allocation, and unrealized gains.",
    lastGenerated: "Jan 22, 2026",
    icon: FileText,
    color: "#00fff5",
  },
  {
    id: "tax",
    title: "Tax Report",
    description: "Cost basis and capital gains for tax filing purposes.",
    lastGenerated: "Jan 21, 2026",
    icon: Download,
    color: "#ff00ff",
  },
  {
    id: "trades",
    title: "Trade History Export",
    description: "Complete transaction history with timestamps and fees.",
    lastGenerated: "Jan 20, 2026",
    icon: ArrowDownLeft,
    color: "#bf00ff",
  },
];

const recentTrades = [
  { id: 1, asset: "BTC", type: "Buy", amount: 0.15, value: 14178, time: "2 hours ago" },
  { id: 2, asset: "ETH", type: "Sell", amount: 3.2, value: 10234, time: "5 hours ago" },
  { id: 3, asset: "SOL", type: "Buy", amount: 45, value: 8340, time: "Yesterday" },
  { id: 4, asset: "LINK", type: "Swap", amount: 120, value: 2388, time: "Yesterday" },
];

export default function ReportsPage() {
  const [loadingId, setLoadingId] = React.useState<string | null>(null);
  const [previewReport, setPreviewReport] = React.useState<(typeof reports)[number] | null>(null);

  const handleGenerate = (reportId: string) => {
    setLoadingId(reportId);
    setTimeout(() => {
      setLoadingId(null);
      toast.success("Report generated successfully!", {
        description: "Your report is ready for download.",
      });
    }, 1500);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-4">
        <div className="mb-6">
          <h2 className="text-lg font-semibold uppercase tracking-wider text-[#00fff5] neon-text-cyan">
            Available Reports
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            Generate and export trading reports for analysis or compliance
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
                <div className="flex items-center gap-2">
                  <Button 
                    variant="outline" 
                    size="sm"
                    className="border-[#00fff5]/20 hover:bg-[#00fff5]/10 hover:text-[#00fff5]"
                    onClick={() => setPreviewReport(report)}
                  >
                    Preview
                  </Button>
                  <Button 
                    size="sm"
                    onClick={() => handleGenerate(report.id)} 
                    disabled={loadingId === report.id}
                    className="bg-gradient-to-r from-[#00fff5] to-[#ff00ff] text-black hover:opacity-90"
                  >
                    {loadingId === report.id ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Generating
                      </>
                    ) : (
                      <>
                        <Download className="mr-2 h-4 w-4" />
                        Generate
                      </>
                    )}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="flex items-center gap-3 text-xs text-muted-foreground pt-0">
                <Clock className="h-3 w-3" />
                Last generated: {report.lastGenerated}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="space-y-4">
        <Card className="border-[#ff00ff]/20 bg-card/80 backdrop-blur-sm">
          <CardHeader>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-[#ff00ff]">
              Quick Summary
            </h3>
            <p className="text-xs text-muted-foreground">
              Recent trading activity overview
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
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Recent Activity</p>
              {recentTrades.map((trade) => (
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
                    <p className="text-xs font-mono text-[#00fff5]">${trade.value.toLocaleString()}</p>
                    <p className="text-[10px] text-muted-foreground">{trade.time}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="border-[#bf00ff]/20 bg-card/80 backdrop-blur-sm">
          <CardHeader>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-[#bf00ff]">
              Export Settings
            </h3>
          </CardHeader>
          <CardContent className="space-y-3 text-xs text-muted-foreground">
            <p>
              Reports are generated in CSV format compatible with most accounting software 
              and tax preparation tools.
            </p>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-[#39ff14]" />
              <span>Supports TurboTax, CoinTracker, Koinly</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-[#39ff14]" />
              <span>FIFO/LIFO cost basis methods available</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-[#39ff14]" />
              <span>Automatic fee tracking included</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <Sheet open={!!previewReport} onOpenChange={(open) => !open && setPreviewReport(null)}>
        <SheetContent side="right" className="w-full sm:max-w-lg border-l border-[#00fff5]/20 bg-card">
          <SheetHeader>
            <SheetTitle className="text-[#00fff5] uppercase tracking-wider">
              {previewReport?.title ?? "Report Preview"}
            </SheetTitle>
          </SheetHeader>
          <div className="mt-6 space-y-4">
            <p className="text-sm text-muted-foreground">
              This preview shows a summary of what will be included in the generated report.
            </p>
            
            <div className="rounded-lg border border-[#00fff5]/20 p-4">
              <h4 className="text-sm font-semibold text-[#00fff5] mb-3">Report Contents</h4>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#00fff5]" />
                  Complete transaction history with timestamps
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#00fff5]" />
                  Cost basis calculations (FIFO method)
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#00fff5]" />
                  Realized and unrealized gains/losses
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#00fff5]" />
                  Network fees and exchange commissions
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#00fff5]" />
                  Wallet address mapping
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
              className="w-full bg-gradient-to-r from-[#00fff5] to-[#ff00ff] text-black hover:opacity-90"
              onClick={() => {
                handleGenerate(previewReport?.id ?? "");
                setPreviewReport(null);
              }}
            >
              <Download className="mr-2 h-4 w-4" />
              Generate Full Report
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
