"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Props = {
  children: React.ReactNode;
  /** When true, section starts expanded (e.g. power users). */
  defaultOpen?: boolean;
};

export function NesteggExpandedMetricsSection({ children, defaultOpen = false }: Props) {
  const [open, setOpen] = React.useState(defaultOpen);

  return (
    <div className="rounded-xl border border-[#00fff5]/12 bg-card/35 backdrop-blur-sm overflow-hidden">
      <Button
        type="button"
        variant="ghost"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex h-auto w-full items-center justify-between rounded-none px-4 py-3.5 text-left hover:bg-[#00fff5]/5"
      >
        <div className="min-w-0 pr-2">
          <p className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">
            More from the simulation
          </p>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Percentiles, longevity detail, and retirement readiness — open anytime
          </p>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
            open && "rotate-180"
          )}
          aria-hidden
        />
      </Button>
      {open ? <div className="space-y-4 border-t border-[#00fff5]/10 px-4 pb-4 pt-4">{children}</div> : null}
    </div>
  );
}
