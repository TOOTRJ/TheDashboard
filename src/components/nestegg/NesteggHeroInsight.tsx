"use client";

import { cn } from "@/lib/utils";
import { Sparkles, AlertTriangle, Info } from "lucide-react";

type Props = {
  message: string;
  tone: "positive" | "caution" | "warning";
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

export function NesteggHeroInsight({ message, tone }: Props) {
  const s = toneStyles[tone];
  const Icon = s.icon;

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border px-5 py-4 backdrop-blur-sm",
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
          <p className={cn("text-[10px] font-bold uppercase tracking-widest", s.text)}>
            Key insight
          </p>
          <p className="mt-1 text-sm leading-relaxed text-foreground sm:text-base">
            {message}
          </p>
        </div>
      </div>
    </div>
  );
}
