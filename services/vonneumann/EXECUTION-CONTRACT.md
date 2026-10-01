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

## Exact durable-policy plans (DB-03A2B, 2026-10-01)

`core/decimal_execution.py` implements a separate policy,
`usd-reference-decimal-v2`, for the forthcoming durable engine cutover. The
current worker and offline comparison runner still use the binary64 v1 model
above. There is no silent reinterpretation of old execution records, floats,
USDC balances or live token amounts. New plans accept explicit decimal strings.

The existing float model can report a debit of `100.0` while its independently
serialized notional and fee sum to `100.00000000000000734`. An exact ledger
correctly rejects that sum against a 100 balance. Version 2 defines the complete
calculation, rather than altering a fee afterward to make the ledger fit.

| Quantity | Decimal places | Interpretation |
| --- | --- | --- |
| Cash, notional, explicit fees | 36 | Hypothetical USD reference units |
| Prices | 18 | USD reference per hypothetical base unit |
| Position quantities | 18 | Hypothetical base units, not mint atoms |
| Fee, half-spread and slippage settings | 6 | Basis points |

These fixed grids are provisional research-policy choices, not exchange or mint
precision claims. Amounts are bounded by the rehearsal's `10^36` maximum. Inputs
with excess places, exponent notation, signs, nonfinite values or non-string
types are rejected; they are not rounded implicitly. Equivalent accepted input
spellings are normalized when constructing a plan. Serialized evidence is
canonical and must recompute exactly, including its policy version.

All calculations use scaled integers, independent of ambient `decimal.Context`.
For cash integer B, reference-price integer P, fee-bps integer F, adverse-impact
integer I and D = `10000 * 10^6`:

```
buy price integer = ceil(P * (D + I) / D)
affordable notional integer = floor(B * D / (D + F))
quantity integer = floor(affordable notional / buy price integer)
entry notional integer = quantity integer * buy price integer
entry fee integer = ceil(entry notional integer * F / D)
cash debit integer = entry notional integer + entry fee integer
residual budget integer = B - cash debit integer

sell price integer = floor(P * (D - I) / D)
exit notional integer = quantity integer * sell price integer
exit fee integer = ceil(exit notional integer * F / D)
cash credit integer = exit notional integer - exit fee integer
```

An 18-place price times an 18-place quantity fits the 36-place cash grid exactly.
The affordability formula proves debit cannot exceed budget even when fees round
up. Unspent budget remains cash; it is neither an extra fee nor a write-off. For
budget 100, price 123.45, fee 30 bps, half-spread 10 bps and slippage 10 bps,
debit is `99.9999999999999999910943253` and retained budget is
`0.0000000000000000089056747`. Their sum is exactly 100.

Zero-size lots, an adverse price rounded to zero, and out-of-range results fail
before any state change. A valid positive-price exit can have zero net credit
when its minimum-unit proceeds are consumed by the rounded fee; it remains a
`fill`. Explicit terminal write-off uses a `None` reference price and a separate
`writeoff` kind with zero proceeds/fee. Signed gross/net P&L are exact decimal
strings. No rounded finite-decimal net-return value is asserted for a generally
nonterminating ratio; the future metrics layer must declare that conversion.

Immutable entry/exit plans retain the original entry budget and configuration;
strict readers recompute every derived field. `debit_cash`, `credit_cash` and
`transfer_cash` provide pure bounded account calculations. Reference mark value
also uses the exact grids and does not charge hypothetical exit fees.

`db/economic_operations.py` seals those plans into v2 open/close operations and
binds the version/configuration through `run_configuration`. The isolated SQL
contract independently verifies the evidence and matches closes to their stored
entry. This proves arithmetic consistency, not provider-price truth, liquidity,
source freshness, permission to trade or real-world execution quality. Full
engine state installation, source/code identities and migration remain DB-03A2C/D.

Research basis and remaining work:

- [Python Decimal](https://docs.python.org/3.12/library/decimal.html) documents
  context-dependent arithmetic and exact conversion of binary-float artifacts.
  The new planner avoids both with explicit integer grids and string inputs.
- [PostgreSQL numeric](https://www.postgresql.org/docs/17/datatype-numeric.html)
  distinguishes exact numeric from floating-point types and documents scale
  coercion. The rehearsal rejects invalid input scale explicitly; it does not
  rely on a silently rounding `numeric(p,s)` column.
- [Solana token balances](https://solana.com/docs/rpc/http/gettokenaccountbalance)
  distinguish integer amount strings, mint decimals and display amounts. Future
  actual settlement must use mint-specific units, transfer/extension rules,
  quote-owned amounts and synchronized currency conversion, not these grids.
- Before promoting this policy, quantify rounding impact over realistic price,
  position and fee ranges; define exact-source decoding and signal/fitness
  conversion; preserve versioned historical comparisons. Fixed/network fees,
  capacity, rejection and latency remain uncalibrated work under FILL-01.
