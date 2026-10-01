import { isFrictionless, type ExecutionPolicy } from "@/lib/probes/execution";

export function ExecutionPolicyNotice({ policy }: { policy?: ExecutionPolicy }) {
  if (!policy) return <p className="text-xs text-muted-foreground">Execution accounting is unclassified for this record. Costs and account units cannot be inferred from legacy asset identifiers.</p>;
  const { config } = policy;
  return (
    <div className="rounded-lg border border-[#00fff5]/20 bg-card/80 p-3 text-xs space-y-1">
      <p className="font-medium">USD reference account · {isFrictionless(config) ? "frictionless mechanics control" : "modeled execution costs"}</p>
      <p>Fee: {config.fee_bps} bps; half-spread: {config.half_spread_bps} bps; adverse slippage: {config.slippage_bps} bps on each entry and exit. These assumptions are fixed for this run and have not been calibrated to market execution.</p>
      <p>Holdings are valued at reference prices. Asset names retain their /USDC identifiers; no USDC conversion is applied. Gas, priority fees, size impact and execution latency are not modeled.</p>
    </div>
  );
}
