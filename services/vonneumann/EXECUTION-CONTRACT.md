# USD reference execution accounting

Policy: `usd-reference-percentage-cost-v1`. Implemented for simulation and paper
observations; no wallet, transaction submission, or on-chain settlement is involved.
This is an **uncalibrated cost scenario**, not a Solana execution simulator.

## Configuration and units

A run accepts immutable `execution` settings: `fee_bps`, `half_spread_bps`, and
`slippage_bps`. All three are required when the object is supplied, must be finite
nonnegative numbers, with fee below 10,000 bps and spread plus slippage below
10,000 bps. Omitting the object explicitly resolves to three zeros: a frictionless
mechanics control, not a realistic default estimate. A basis point is 0.01%.
These assumptions are outside the genome and cannot evolve to reduce costs.

The model holds long-only fractional positions. Prices, cash, fees, P&L and equity use a hypothetical **USD reference account**.
Internal asset identifiers such as `SOL/USDC` remain compatibility identifiers;
they do not prove USDC settlement or an assumed USD/USDC conversion. Jupiter
Price V3 supplies USD reference prices, not an executable amount-specific quote.
Old records without the new policy remain unclassified.

## Accounting

For reference price P, all-in entry budget B, fee fraction f, half-spread h and
adverse slippage s (each bps / 10,000):

```
buy fill price = P * (1 + h + s)
entry notional = B / (1 + f)
entry fee = entry notional * f
quantity = entry notional / buy fill price
cash debit = B

sell fill price = P * (1 - h - s)
exit notional = quantity * sell fill price
exit fee = exit notional * f
cash credit = exit notional * (1 - f)
net P&L = cash credit - cash debit
net return = net P&L / cash debit
reference equity = free cash + sum(quantity * fresh reference mark)
```

Spread and slippage are embedded in the execution prices. Their separate cost
records explain the adjustment and must **not** be deducted a second time.
`gross_pnl` means exit executed notional minus entry executed notional, before
explicit entry/exit fees. It is not a counterfactual reference-price profit.
Reference-mark equity excludes hypothetical future exit costs; completed
candidate windows liquidate before fitness/ranking so realized exit costs count.
Entry costs reduce equity immediately and can halt further queued entries.
The existing immutable minute return diagnostic samples before frame decisions.
Costs normally appear at the next eligible sample; final liquidation costs have
no subsequent sample after retirement. Metadata and the UI explicitly disclose
that limitation. Net P&L, ROI and fitness include final costs. Do not call this
pre-decision Sharpe diagnostic a complete net execution-return series.

`TradeRecord.amount` and database `amount` retain the all-in entry cash debit.
The execution JSON separately records quantity, invested notional, reference/fill
prices, explicit fees, embedded costs, configuration, and version. In-memory
`pnl_pct` / execution `net_return` are fractions; the existing event/database
`pnl_pct` remains percentage points. Values are persisted without display rounding.
Arithmetic uses finite binary64 values with explicit representability checks;
this version does not claim integer token-atomic or decimal settlement precision.

Hand calculation: buy quantity 2 at reference 100 with 1% total adverse price
adjustment and 0.1% fee. Fill price is 101, notional 202, fee 0.202 and debit
202.202. From initial cash 1,000, remaining cash is 797.798 and reference equity
997.798. Exit at reference 110 gives fill 108.9, notional 217.8, fee 0.2178,
credit 217.5822, final cash 1,015.3802 and net profit 15.3802.

## Timing, exits and failure behavior

Existing causal intents still require a later eligible source/receipt observation.
Stop and take-profit thresholds compare **reference price movement from entry**;
a gap executes at the next accepted observation with the same adverse costs,
not at the threshold. Signal, stop, take-profit, death, reproduction and evolution
exits share the same calculator. An explicit terminal loss writes off the holding
with zero proceeds and no invented exit fee; it is identified as a write-off.

Whole liquidation batches are preflighted without changing positions, cash,
metrics or records. Invalid/unrepresentable calculations fail before mutation.
Risk checks retain events already applied if a subsequent operation fails.
Cohort completion charges closing costs before ranking; a resulting account
halt aborts the cohort rather than submitting it to the optimizer.

The new nullable `vn_trades.execution` JSONB column preserves existing rows.
It does not make the trade, cash/probe update, event stream or optimizer state
one atomic transaction. Durable idempotency, ownership fencing and crash
reconciliation remain DB-02/DB-03/HOST-01 requirements.

## Research needed before economic comparisons

FILL-01 remains open for calibrated size/impact/capacity, latency and rejection
models; fixed/network/priority fees and tips; token decimals/extensions/transfer
fees; account rent; quote expiry and failure outcomes; synchronized USD/USDC
conversion; and a versioned durable result ledger. Slippage tolerance is a limit,
not measured realized slippage. Use multiple declared scenarios until calibration
is supported by appropriately licensed observations.

Primary sources reviewed 2026-09-30:

- [Jupiter Price](https://developers.jup.ag/docs/price): USD reference prices.
- [Swap order schema](https://developers.jup.ag/docs/api-reference/swap/order):
  amount-specific quotes, fee units and aggregate priority-fee fields.
- [Order and Execute](https://developers.jup.ag/docs/swap/order-and-execute) and
  [Build](https://developers.jup.ag/docs/swap/build): distinct fee/execution paths.
- [Slippage](https://developers.jup.ag/docs/swap/advanced/slippage): tolerance/RTSE
  semantics, not evidence for a realized-cost assumption.
- [Solana fees](https://solana.com/docs/core/fees/fee-structure) and
  [accounts](https://solana.com/docs/core/accounts): transaction-format-specific
  fees and refundable locked account storage balances.
- [Jito submission](https://docs.jito.wtf/lowlatencytxnsend/): tips and transaction
  composition; minimum tips do not establish landing probability.

The user confirmed on 2026-09-30 that Jupiter permits retention for backtesting;
that permission is accepted. [The data research decision](JUPITER-DATA-RESEARCH.md)
favors small on-demand historical snapshots now and bounded quote/receipt recording
later for execution calibration. Separate Birdeye entitlements/retention and any
future redistribution remain research items; a combined public archive is not
part of the current work. No provider records were collected for this change.
