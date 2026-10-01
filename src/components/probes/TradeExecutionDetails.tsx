import { formatReferenceNumber, parseTradeExecution } from "@/lib/probes/execution";

export function TradeExecutionDetails({ execution }: { execution: unknown }) {
  const ledger = parseTradeExecution(execution);
  if (!ledger) return <span className="text-[10px] text-muted-foreground">Cost accounting unavailable</span>;
  const { entry, exit } = ledger;
  const money = (value: number) => `$${formatReferenceNumber(value)} USD`;
  return (
    <details className="text-[10px] min-w-44">
      <summary className="cursor-pointer text-[#00fff5]">USD reference cost ledger</summary>
      <dl className="mt-2 space-y-1">
        <div><dt className="inline">Entry reference / fill: </dt><dd className="inline font-mono">{money(entry.reference_price)} / {money(entry.fill_price)}</dd></div>
        <div><dt className="inline">Base-token quantity: </dt><dd className="inline font-mono">{entry.quantity.toPrecision(8)}</dd></div>
        <div><dt className="inline">Entry notional: </dt><dd className="inline font-mono">{money(entry.notional)}</dd></div>
        <div><dt className="inline">Entry fee / cash debit: </dt><dd className="inline font-mono">{money(entry.fee)} / {money(entry.cash_debit)}</dd></div>
        <div><dt className="inline">Entry spread / slippage: </dt><dd className="inline font-mono">{money(entry.spread_cost)} / {money(entry.slippage_cost)}</dd></div>
        {exit ? <>
          <div><dt className="inline">Exit: </dt><dd className="inline">{exit.kind === "writeoff" ? "Terminal write-off" : "Modeled fill"}</dd></div>
          <div><dt className="inline">Exit reference / fill: </dt><dd className="inline font-mono">{money(exit.reference_price)} / {money(exit.fill_price)}</dd></div>
          <div><dt className="inline">Exit notional: </dt><dd className="inline font-mono">{money(exit.notional)}</dd></div>
          <div><dt className="inline">Exit fee / cash credit: </dt><dd className="inline font-mono">{money(exit.fee)} / {money(exit.cash_credit)}</dd></div>
          <div><dt className="inline">Exit spread / slippage: </dt><dd className="inline font-mono">{money(exit.spread_cost)} / {money(exit.slippage_cost)}</dd></div>
          <div><dt className="inline">Gross P&amp;L before fees: </dt><dd className="inline font-mono">{money(exit.gross_pnl)}</dd></div>
          <div><dt className="inline">Net P&amp;L / return: </dt><dd className="inline font-mono">{money(exit.net_pnl)} / {(exit.net_return * 100).toFixed(2)}%</dd></div>
        </> : <div><dt className="inline">Exit costs: </dt><dd className="inline">Not realized; position remains open.</dd></div>}
      </dl>
      <p className="mt-2 text-muted-foreground">Spread and slippage are embedded in fill prices, not extra cash debits. Gross P&amp;L already includes their effect; net P&amp;L also includes fees.</p>
    </details>
  );
}
