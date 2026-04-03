"use client";

const STEPS = [
  { n: "1", label: "Enter your current plan" },
  { n: "2", label: "Review your projected outcome" },
  { n: "3", label: "Compare scenarios" },
  { n: "4", label: "Test improvements" },
] as const;

export function NesteggOrientationStrip() {
  return (
    <div className="rounded-lg border border-[#00fff5]/15 bg-gradient-to-r from-[#00fff5]/[0.06] via-transparent to-[#ff00ff]/[0.04] px-3 py-3 sm:px-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
        <p className="text-[10px] font-bold uppercase tracking-widest text-[#00fff5]/90 shrink-0">
          Start here
        </p>
        <div
          className="flex flex-wrap items-center gap-x-1 gap-y-2 text-[11px] leading-snug text-muted-foreground sm:gap-x-2"
          role="list"
        >
          {STEPS.map((s, i) => (
            <span key={s.n} className="inline-flex items-center gap-2" role="listitem">
              {i > 0 ? (
                <span className="hidden text-muted-foreground/35 sm:inline" aria-hidden>
                  ·
                </span>
              ) : null}
              <span className="font-mono text-[10px] text-[#00fff5]/75">{s.n}.</span>
              <span className="text-foreground/90">{s.label}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
