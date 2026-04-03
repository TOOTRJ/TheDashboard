"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Props = {
  title: string;
  description?: string;
  defaultOpen?: boolean;
  /** Controlled open state (use with `onOpenChange`). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
  className?: string;
  /** Stronger header styling for primary editing sections. */
  headerVariant?: "default" | "planInputs";
  /** When `planInputs` + `named`, title is a plan label (mixed case); otherwise “Your plan inputs” styling. */
  planInputsTitleMode?: "default" | "named";
};

export const NesteggCollapsibleBlock = React.forwardRef<HTMLDivElement, Props>(
  function NesteggCollapsibleBlock(
    {
      title,
      description,
      defaultOpen = false,
      open: controlledOpen,
      onOpenChange,
      children,
      className,
      headerVariant = "default",
      planInputsTitleMode = "default",
    },
    ref
  ) {
    const [uncontrolledOpen, setUncontrolledOpen] = React.useState(defaultOpen);
    const isControlled = controlledOpen !== undefined;
    const open = isControlled ? controlledOpen : uncontrolledOpen;

    const setOpen = React.useCallback(
      (next: boolean) => {
        if (!isControlled) {
          setUncontrolledOpen(next);
        }
        onOpenChange?.(next);
      },
      [isControlled, onOpenChange]
    );

    const isPlanInputs = headerVariant === "planInputs";
    const namedPlanTitle = isPlanInputs && planInputsTitleMode === "named";

    const planInputsNameClass = namedPlanTitle
      ? "normal-case tracking-tight bg-gradient-to-r from-[#ff99ff] via-[#ff00ff] to-[#00fff5] bg-clip-text text-transparent drop-shadow-[0_0_12px_rgba(255,0,255,0.35)] max-w-[85vw] sm:max-w-lg truncate"
      : "uppercase tracking-wider bg-gradient-to-r from-[#ff99ff] via-[#ff00ff] to-[#00fff5] bg-clip-text text-transparent drop-shadow-[0_0_12px_rgba(255,0,255,0.35)] max-w-[85vw] sm:max-w-md truncate";

    return (
    <div
      ref={ref}
      className={cn(
        "rounded-xl border bg-card/40 backdrop-blur-sm overflow-hidden",
        isPlanInputs
          ? "border-[#ff00ff]/25 shadow-[0_0_28px_-10px_rgba(255,0,255,0.35)] ring-1 ring-[#ff00ff]/15"
          : "border-[#00fff5]/12",
        className
      )}
    >
      <Button
        type="button"
        variant="ghost"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className={cn(
          "flex h-auto w-full items-center justify-between gap-3 rounded-none px-4 py-3.5 text-left",
          isPlanInputs
            ? "hover:bg-[#ff00ff]/8 bg-gradient-to-r from-[#ff00ff]/10 via-transparent to-[#00fff5]/5"
            : "hover:bg-[#00fff5]/5"
        )}
      >
        <div className="min-w-0 flex-1">
          <p
            className={cn(
              "text-sm font-semibold",
              isPlanInputs
                ? "flex min-w-0 flex-wrap items-baseline gap-x-1 gap-y-0.5"
                : "uppercase tracking-wider text-[#00fff5]"
            )}
            title={isPlanInputs ? `Plan Inputs: ${title}` : title}
          >
            {isPlanInputs ? (
              <>
                <span className="shrink-0 text-muted-foreground/90 font-medium normal-case tracking-normal">
                  Plan Inputs:
                </span>
                <span className={cn("min-w-0", planInputsNameClass)}>{title}</span>
              </>
            ) : (
              title
            )}
          </p>
          {description ? (
            <p
              className={cn(
                "text-[11px] mt-0.5 leading-snug",
                isPlanInputs ? "text-muted-foreground/95" : "text-muted-foreground"
              )}
            >
              {description}
            </p>
          ) : null}
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
            open && "rotate-180"
          )}
          aria-hidden
        />
      </Button>
      {open ? <div className="border-t border-[#00fff5]/10 px-4 pb-4 pt-3 space-y-3">{children}</div> : null}
    </div>
    );
  }
);

NesteggCollapsibleBlock.displayName = "NesteggCollapsibleBlock";
