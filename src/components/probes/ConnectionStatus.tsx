"use client";

export function ConnectionStatus({ connected }: { connected: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={`h-2 w-2 rounded-full ${
          connected ? "bg-[#39ff14] shadow-[0_0_6px_#39ff14]" : "bg-[#ff3366]"
        }`}
      />
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {connected ? "Live" : "Offline"}
      </span>
    </div>
  );
}
