"use client";

import { cn } from "@/lib/utils";
import { Sparkles, AlertTriangle, Info } from "lucide-react";

type Props = {
  message: string;
  tone: "positive" | "caution" | "warning";
  /** Optional Monte Carlo / probability lines (plain English, concise). */
  highlights?: string[];
  /** Hide the small “Plan snapshot” line when the parent section already has a title. */
  hideEyebrow?: boolean;
};

const toneStyles = {
  positive: {
    border: "border-[#39ff14]/30",
    bg: "from-[#39ff14]/10 to-transparent",
    text: "text-[#39ff14]",
    icon: Sparkles,
  },
  caution: {
    border: "border-[#ffff00]/25",
    bg: "from-[#ffff00]/10 to-transparent",
    text: "text-[#ffff00]",
    icon: Info,
  },
  warning: {
    border: "border-[#ff3366]/30",
    bg: "from-[#ff3366]/10 to-transparent",
    text: "text-[#ff3366]",
    icon: AlertTriangle,
  },
};

export function NesteggHeroInsight({ message, tone, highlights, hideEyebrow }: Props) {
  const s = toneStyles[tone];
  const Icon = s.icon;

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border px-5 py-5 sm:px-6 backdrop-blur-sm",
        s.border,
        "bg-gradient-to-br",
        s.bg
      )}
    >
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.03] to-transparent pointer-events-none" />
      <div className="relative flex gap-3">
        <div
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-background/40",
            s.text
          )}
        >
          <Icon className="h-5 w-5" aria-hidden />
        </div>
        <div>
          {!hideEyebrow ? (
            <p className={cn("text-[10px] font-bold uppercase tracking-widest", s.text)}>
              Plan snapshot
            </p>
          ) : null}
          <p
            className={cn(
              "text-sm leading-relaxed text-foreground sm:text-base",
              !hideEyebrow && "mt-1.5"
            )}
          >
            {message}
          </p>
          {highlights && highlights.length > 0 ? (
            <ul className="mt-3 space-y-1.5 border-t border-white/10 pt-3 text-xs text-muted-foreground sm:text-sm">
              {highlights.map((h, i) => (
                <li key={i} className="flex gap-2 leading-snug">
                  <span className="text-[#00fff5]/80" aria-hidden>
                    ·
                  </span>
                  <span>{h}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </div>
  );
}
