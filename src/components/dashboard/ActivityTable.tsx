"use client";

import * as React from "react";
import { 
  ArrowDownLeft, 
  ArrowRightLeft, 
  ArrowUpRight, 
  ChevronLeft, 
  ChevronRight, 
  ChevronsUpDown,
  ExternalLink,
  Copy,
  Search,
  Sparkles
} from "lucide-react";

import { useDashboardFilters } from "@/components/layout/DashboardProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/formatters";
import type { TradeItem } from "@/lib/mock";
import { getTradeFeed, searchTradeFeed } from "@/lib/mock";

type SortKey = "timestamp" | "total";
type SortDirection = "asc" | "desc";

const tradeTypeIcons = {
  Buy: ArrowDownLeft,
  Sell: ArrowUpRight,
  Swap: ArrowRightLeft,
};

const tradeTypeColors = {
  Buy: "#39ff14",
  Sell: "#ff3366",
  Swap: "#00fff5",
};

function TableSkeleton() {
  return (
    <div className="space-y-3">
      {[...Array(5)].map((_, i) => (
        <div 
          key={i} 
          className="h-12 w-full shimmer rounded-lg"
          style={{ animationDelay: `${i * 100}ms` }}
        />
      ))}
    </div>
  );
}

export function ActivityTable() {
  const { dateRange, searchQuery } = useDashboardFilters();
  const [localQuery, setLocalQuery] = React.useState("");
  const [sortKey, setSortKey] = React.useState<SortKey>("timestamp");
  const [sortDirection, setSortDirection] = React.useState<SortDirection>("desc");
  const [currentPage, setCurrentPage] = React.useState(1);
  const [selectedItem, setSelectedItem] = React.useState<TradeItem | null>(null);
  const detailsTrigger = React.useRef<HTMLButtonElement | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isVisible, setIsVisible] = React.useState(false);

  React.useEffect(() => {
    setIsLoading(true);
    setIsVisible(false);
    const timer = setTimeout(() => {
      setIsLoading(false);
      setTimeout(() => setIsVisible(true), 50);
    }, 700);
    return () => clearTimeout(timer);
  }, [dateRange, searchQuery]);

  React.useEffect(() => {
    setCurrentPage(1);
  }, [dateRange, searchQuery, localQuery]);

  const data = getTradeFeed(dateRange);
  let filtered = searchTradeFeed(data, searchQuery);
  filtered = searchTradeFeed(filtered, localQuery);

  const sorted = [...filtered].sort((a, b) => {
    const modifier = sortDirection === "asc" ? 1 : -1;
    if (sortKey === "total") {
      return (a.total - b.total) * modifier;
    }
    return (new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()) * modifier;
  });

  const pageSize = 8;
  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const paginated = sorted.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("desc");
    }
  };

  return (
    <section>
      <Card 
        className={`
          border-[#00fff5]/20 bg-card/80 backdrop-blur-sm overflow-hidden relative
          card-hover-glow transition-all duration-500 ease-out
          ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}
        `}
      >
        {/* Animated gradient border top */}
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-[#00fff5] via-[#ff00ff] to-[#00fff5] bg-[length:200%_100%] animate-[gradient-shift_4s_ease_infinite]" />
        
        {/* Corner decorations */}
        <div className="absolute top-2 left-2 w-4 h-4 border-l-2 border-t-2 border-[#00fff5]/30" />
        <div className="absolute top-2 right-2 w-4 h-4 border-r-2 border-t-2 border-[#00fff5]/30" />
        <div className="absolute bottom-2 left-2 w-4 h-4 border-l-2 border-b-2 border-[#00fff5]/30" />
        <div className="absolute bottom-2 right-2 w-4 h-4 border-r-2 border-b-2 border-[#00fff5]/30" />
        
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between relative">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5] flex items-center gap-2">
              <Sparkles className="h-4 w-4 animate-pulse" />
              Sample Activity
            </h2>
            <p className="text-xs text-muted-foreground mt-1">
              Generated trade examples with fictional identifiers; no account trades are loaded
            </p>
          </div>
          <div className="relative w-full sm:max-w-xs group">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground transition-colors group-focus-within:text-[#00fff5]" />
            <Input
              value={localQuery}
              onChange={(event) => setLocalQuery(event.target.value)}
              aria-label="Filter sample activity"
              placeholder="Filter sample asset or fictional hash..."
              className="pl-9 border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40 focus:shadow-[0_0_10px_rgba(0,255,245,0.2)] transition-all duration-300"
            />
          </div>
        </CardHeader>
        
        <CardContent>
          {isLoading ? (
            <TableSkeleton />
          ) : (
            <div className="space-y-4">
              <div className="rounded-lg border border-[#00fff5]/10 overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="border-b border-[#00fff5]/10 hover:bg-transparent">
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="flex items-center gap-2 px-0 text-xs hover:text-[#00fff5] transition-colors"
                          onClick={() => handleSort("timestamp")}
                        >
                          Time
                          <ChevronsUpDown className="h-3 w-3" />
                        </Button>
                      </TableHead>
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Type</TableHead>
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Asset</TableHead>
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Amount</TableHead>
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Price</TableHead>
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="flex items-center gap-2 px-0 text-xs hover:text-[#00fff5] transition-colors"
                          onClick={() => handleSort("total")}
                        >
                          Total
                          <ChevronsUpDown className="h-3 w-3" />
                        </Button>
                      </TableHead>
                      <TableHead className="text-xs uppercase tracking-wider text-muted-foreground">Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginated.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="py-10 text-center text-sm text-muted-foreground">
                          <div className="flex flex-col items-center gap-3">
                            <div className="h-16 w-16 rounded-full border border-[#00fff5]/20 flex items-center justify-center relative">
                              <ArrowRightLeft className="h-6 w-6 text-[#00fff5]/50" />
                              <div className="absolute inset-0 rounded-full border border-[#00fff5]/20 animate-ping" />
                            </div>
                            <p>No trades match your filters</p>
                            <p className="text-xs text-muted-foreground/50">Try adjusting your search criteria</p>
                          </div>
                        </TableCell>
                      </TableRow>
                    ) : (
                      paginated.map((item, index) => {
                        const TypeIcon = tradeTypeIcons[item.type];
                        const typeColor = tradeTypeColors[item.type];
                        
                        return (
                          <TableRow 
                            key={item.id} 
                            className={`
                              cursor-pointer border-b border-[#00fff5]/5 
                              hover:bg-gradient-to-r hover:from-[#00fff5]/10 hover:to-transparent 
                              transition-all duration-300 group
                              ${isVisible ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-4'}
                            `}
                            style={{ transitionDelay: `${index * 50}ms` }}
                            onClick={() => {
                              detailsTrigger.current = null;
                              setSelectedItem(item);
                            }}
                          >
                            <TableCell className="font-mono text-xs text-muted-foreground">
                              {formatDateTime(item.timestamp)}
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-1.5 group-hover:scale-105 transition-transform">
                                <div 
                                  className="p-1 rounded"
                                  style={{ backgroundColor: `${typeColor}20` }}
                                >
                                  <TypeIcon className="h-3.5 w-3.5" style={{ color: typeColor }} />
                                </div>
                                <span className="text-xs font-medium" style={{ color: typeColor }}>
                                  {item.type}
                                </span>
                              </div>
                            </TableCell>
                            <TableCell>
                              <button
                                type="button"
                                aria-label={`View sample ${item.type.toLowerCase()} ${item.asset} trade details`}
                                aria-haspopup="dialog"
                                className="text-left text-sm font-semibold text-foreground group-hover:text-[#00fff5] transition-colors"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  detailsTrigger.current = event.currentTarget;
                                  setSelectedItem(item);
                                }}
                              >
                                {item.asset}
                              </button>
                            </TableCell>
                            <TableCell className="font-mono text-sm">
                              {item.amount.toLocaleString("en-US", { maximumFractionDigits: 4 })}
                            </TableCell>
                            <TableCell className="font-mono text-sm text-[#00fff5]">
                              ${item.price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                            </TableCell>
                            <TableCell className="font-mono text-sm font-medium text-foreground">
                              ${item.total.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                            </TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={`transition-all duration-300 ${
                                  item.status === "Completed"
                                    ? "border-[#39ff14]/30 bg-[#39ff14]/10 text-[#39ff14] hover:bg-[#39ff14]/20"
                                    : item.status === "Pending"
                                      ? "border-[#ffff00]/30 bg-[#ffff00]/10 text-[#ffff00] hover:bg-[#ffff00]/20 animate-pulse"
                                      : "border-[#ff3366]/30 bg-[#ff3366]/10 text-[#ff3366] hover:bg-[#ff3366]/20"
                                }`}
                              >
                                {item.status}
                              </Badge>
                            </TableCell>
                          </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
              </div>

              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Page <span className="text-[#00fff5] font-mono">{currentPage}</span> of{" "}
                  <span className="font-mono">{totalPages}</span> • {sorted.length} sample trades
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                    disabled={currentPage === 1}
                    aria-label="Previous page"
                    className="h-8 w-8 border-[#00fff5]/20 hover:border-[#00fff5]/40 hover:bg-[#00fff5]/10 disabled:opacity-30 transition-all duration-300 hover:scale-105"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                    disabled={currentPage === totalPages}
                    aria-label="Next page"
                    className="h-8 w-8 border-[#00fff5]/20 hover:border-[#00fff5]/40 hover:bg-[#00fff5]/10 disabled:opacity-30 transition-all duration-300 hover:scale-105"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!selectedItem} onOpenChange={(open) => !open && setSelectedItem(null)}>
        <DialogContent
          className="border-[#00fff5]/20 bg-card/95 backdrop-blur-xl scale-in"
          onCloseAutoFocus={(event) => {
            if (detailsTrigger.current?.isConnected) {
              event.preventDefault();
              detailsTrigger.current.focus();
            }
            detailsTrigger.current = null;
          }}
        >
          {/* Animated border */}
          <div className="absolute inset-0 rounded-lg overflow-hidden pointer-events-none">
            <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#00fff5] to-transparent animate-[data-flow_2s_linear_infinite]" />
            <div className="absolute bottom-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#ff00ff] to-transparent animate-[data-flow_2s_linear_infinite]" style={{ animationDelay: '-1s' }} />
          </div>
          
          <DialogHeader>
            <DialogTitle className="text-[#00fff5] uppercase tracking-wider flex items-center gap-2">
              <Sparkles className="h-4 w-4 animate-pulse" />
              Sample Trade Details
            </DialogTitle>
            <DialogDescription>
              Generated example with fictional identifiers. No account transaction or live quote is loaded.
            </DialogDescription>
          </DialogHeader>
          {selectedItem && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                {(() => {
                  const TypeIcon = tradeTypeIcons[selectedItem.type];
                  const typeColor = tradeTypeColors[selectedItem.type];
                  return (
                    <>
                      <div 
                        className="flex h-14 w-14 items-center justify-center rounded-xl transition-transform hover:scale-110 hover:rotate-6"
                        style={{ 
                          backgroundColor: `${typeColor}20`,
                          boxShadow: `0 0 20px ${typeColor}30`,
                        }}
                      >
                        <TypeIcon className="h-7 w-7" style={{ color: typeColor }} />
                      </div>
                      <div>
                        <p className="text-xl font-bold" style={{ color: typeColor }}>
                          {selectedItem.type} {selectedItem.asset}
                        </p>
                        <p className="text-xs text-muted-foreground font-mono">
                          {formatDateTime(selectedItem.timestamp)}
                        </p>
                      </div>
                    </>
                  );
                })()}
              </div>
              
              <div className="grid gap-3 rounded-lg border border-[#00fff5]/10 bg-gradient-to-br from-[#00fff5]/5 to-transparent p-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="group">
                    <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Amount</p>
                    <p className="font-mono text-lg font-medium group-hover:text-[#00fff5] transition-colors">
                      {selectedItem.amount.toLocaleString("en-US", { maximumFractionDigits: 6 })} {selectedItem.asset}
                    </p>
                  </div>
                  <div className="group">
                    <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Price</p>
                    <p className="font-mono text-lg font-medium text-[#00fff5]">
                      ${selectedItem.price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="group">
                    <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Total Value</p>
                    <p className="font-mono text-xl font-bold text-foreground">
                      ${selectedItem.total.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Status</p>
                    <Badge
                      variant="outline"
                      className={
                        selectedItem.status === "Completed"
                          ? "border-[#39ff14]/30 bg-[#39ff14]/10 text-[#39ff14]"
                          : selectedItem.status === "Pending"
                            ? "border-[#ffff00]/30 bg-[#ffff00]/10 text-[#ffff00] animate-pulse"
                            : "border-[#ff3366]/30 bg-[#ff3366]/10 text-[#ff3366]"
                      }
                    >
                      {selectedItem.status}
                    </Badge>
                  </div>
                </div>
              </div>
              
              <div className="space-y-3">
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Fictional Transaction Hash</p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 rounded-lg bg-muted/30 px-3 py-2 font-mono text-sm text-[#00fff5] border border-[#00fff5]/10">
                      {selectedItem.txHash}
                    </code>
                    <Button 
                      type="button"
                      variant="outline" 
                      size="icon"
                      disabled
                      aria-label="Copy unavailable"
                      aria-describedby="sample-trade-links-unavailable"
                      className="h-9 w-9 border-[#00fff5]/20 hover:bg-[#00fff5]/10 hover:scale-105 transition-all duration-300"
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Fictional Wallet</p>
                  <code className="block rounded-lg bg-muted/30 px-3 py-2 font-mono text-sm text-muted-foreground border border-[#00fff5]/10">
                    {selectedItem.wallet}
                  </code>
                </div>
              </div>
              <p id="sample-trade-links-unavailable" className="text-xs text-muted-foreground">
                Copy and explorer actions are unavailable for these fictional, abbreviated identifiers.
              </p>
              
              <Button 
                type="button"
                variant="outline" 
                disabled
                aria-describedby="sample-trade-links-unavailable"
                className="w-full border-[#00fff5]/20 hover:bg-[#00fff5]/10 hover:text-[#00fff5] hover:border-[#00fff5]/40 transition-all duration-300 group btn-glow"
              >
                <ExternalLink className="mr-2 h-4 w-4 group-hover:scale-110 transition-transform" />
                Explorer unavailable
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
