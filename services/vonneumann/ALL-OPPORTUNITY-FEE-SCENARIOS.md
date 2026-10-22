# All-opportunity fee scenario research

The two pure source/test files are adopted locally after source review and a parent-owned 14-case offline pass. They are not joined to the runner, provider ingestion or production execution. Final-source CI and empirical integration remain separate gates.

## Scope and source boundary

Reviewed 2026-10-21 from source baseline `764d00a1d0fb149269ff752be99d8965a70272df`.
The pure report and its fourteen tests are present locally. No runner, production
strategy, genes, provider collection, native database or hosted service is changed.
Source-bound CI and the remaining empirical contracts precede integration.

## Existing evaluation controls remain in place

BASE-03B is already implemented. `research/runner.py:350–372` compares reference
GA and random search over the same twenty-point grid and logical request budget,
binds training evidence before holdout selection, and carries only selected
training winners and prespecified controls into holdout. The reference GA shares
initialization, charges duplicate requests and separates the exhaustive training
cache's cost; `OFFLINE-RESEARCH.md:76–122` describes these policies. Rebuilding
them would duplicate working code.

`research/protocol.py:33–43,97–148` freezes the baseline, up to eight unique seeds,
sorted budgets, source/runtime and dataset identities. It reports algorithm
variation on a single dataset descriptively, without treating seeds as
independent markets. Cash, fixed EMA 9/21, buy-and-hold 25% and buy-and-hold 100%
are already controls. The production solver's lifecycle is outside this reference
experiment (`OFFLINE-RESEARCH.md:97–108`). Its 460 legal integer pairs are not the
same search domain as the reference twenty points.

The existing follow-up memo identifies missing all-opportunity cost denominators
at `EMPIRICAL-EVALUATION-FOLLOWUP-2026-10-16.md:31–41`. The pure fee-provenance
validator covers individual ledgers but is not an opportunity-population report.
The percentage-cost fill model explicitly excludes fixed/network fees, delay,
capacity and rejection (`core/execution.py:1–6`). The candidate addresses only
the population-reporting gap; it does not silently alter that model.

## New bounded component

The component comprises two new source files:

- `vonneumann/research/opportunity_costs.py`: pure frozen scenario records and a
  population fee report, using the unchanged `fee_provenance.py` contract.
- `tests/test_opportunity_costs.py`: fourteen independent, hand-calculated cases.

There is no CLI, file loader, artifact publication, runner import, API client,
signer, settlement inference, new dependency or automatic data acquisition.
Internal exact-money helpers are reused from the pinned fee module rather than
duplicating their canonical amount and currency rules. These are research-internal
interfaces; that dependency must be reviewed if either module later changes.

The caller declares one to 128 eligible opportunities, each with a fixed status:
missing quote, assembly refusal, not submitted, or attempted. An attempted row
contains one to eight distinct attempt records. The whole population admits at
most 512 attempts and 2 MiB of canonical ASCII input. Each row and attempt needs
an evidence SHA-256; these references bind declared inputs without authenticating
the evidence or proving that every eligible opportunity was supplied. IDs and
evidence formats are closed and bounded. Capacity errors refuse; they do not
truncate the population.

Attempt outcomes reuse the existing five values: success, processed failure,
explicit unprocessed expiry, explicit rejection before submission, or uncertain.
An attempt record is a declared execution decision record, not necessarily an
on-chain submission. A new attempt after success or uncertainty is refused.
Uncertainty needs a separate original-transaction reconciliation protocol; this
report cannot resolve it or legitimize retrying under a new ID.

An unattempted opportunity with no explicit fee ledger remains unresolved. A
caller may instead supply an explicit rejected-before-submission ledger, including
an empty ledger declaring zero charged costs. That is a scenario assumption,
not a conclusion inferred from the absence of a quote. Missing accounting,
unknown outcome, payer, amount or refund never becomes an inferred zero.

Every opportunity remains in the result and in the opportunity denominator.
Processed failed attempts remain in the fee numerator even when a later attempt
succeeds. Wholly unsuccessful opportunities also remain in that numerator.
Complete population totals and ratios are null if any opportunity's accounting
is unresolved. Known subtotals are deliberately labelled as totals from fully
resolved ledgers only; they are not population totals or necessarily every known
component inside an unresolved ledger.

Costs preserve SOL lamports, USDC atomic units and USD-reference decimals as
separate denominations. Integer arithmetic preserves the existing canonical
currency bounds. There is no exchange-rate conversion. Included-in-quote costs
are disclosed separately and never subtracted again; sponsored additional costs
are separate from account-paid costs; explicit refunds reduce the matching
charge. A potentially charged source/kind cannot be counted twice anywhere in
the population. An aggregate priority-and-tip source cannot also supply a
separate tip. An explicitly excluded charge does not consume that source identity
and may be disclosed once on a later success. Source IDs must denote unique
economic charge evidence consistently across the population; the module cannot
detect a malicious alias under a different ID.

Ratios retain an exact numerator amount and integer denominator, without rounding
fractional lamports. `cost_per_opportunity` divides all-population additional
account debits by all declared opportunities. `cost_per_completed_flow` uses the
same all-population numerator and divides by opportunities ending in success.
It is a cost-per-completed-flow population measure, not the mean fee among
successful transactions. With no successes the completed-flow ratio is null.
With no debited currencies the complete debit mapping is empty, declaring no
costs under the supplied ledger assumptions; it is not an observed zero-cost
guarantee. Other currency/disposition groups remain visible separately.

The result explicitly marks calibration, population completeness, provider
authentication, quote completeness, settlement, historical replay, paper
integration and live-trading authority false. The population hash proves the
identity of the declared canonical input; it does not prove authenticity,
economic completeness, profitability or valid future fill probabilities.

## Independent test oracles

The primary hand ledger has three opportunities: one failed attempt costing 5
followed by success costing 7; one missing quote with an explicit zero-cost
declaration; and one wholly unsuccessful opportunity costing 3. Expected total
additional account debit is 15, with three opportunities, three attempts and one
completed flow. Expected ratios are 15/3 and 15/1. The implementation does not
calculate these expected values for the test.

The remaining cases cover no successful denominator; uncertainty with retained
known subtotals; unknown fee amount plus missing accounting; explicit unprocessed
expiry exclusions; sponsor/included/refund separation; exact 0.1 + 0.2 and
separate denominations; duplicate attempt/source refusal; priority/tip alias
refusal; an excluded quote charge later included once; no retry after success or
uncertainty; closed input/status/capacity; population currency overflow; and
repeatable reviews isolated from mutation of prior output. A test-local network
guard applies during candidate import and every test. All inputs are synthetic.
The parent-owned clean-environment run passed all fourteen cases; source review and arithmetic fixtures do not establish empirical calibration.

## Fresh primary-source research and limits

Solana validates transaction age before fee collection, while failures after fee
deduction can retain charges. A timeout is therefore insufficient evidence for
uncharged expiry. The report requires an explicit outcome and leaves uncertain
records unresolved. [Solana transaction pipeline](https://solana.com/docs/core/transactions/transaction-pipeline)

Current Solana documentation distinguishes requested-CU priority-fee calculation
for legacy/v0 from the absolute priority fee in the v1 message format. A later
calibration schema must retain transaction version and exact charge evidence;
this candidate neither computes hardcoded fees nor infers fee probabilities.
[Solana fee structure](https://solana.com/docs/core/fees/fee-structure)

Jupiter separates expected order output from execution's realized total input and
output. Quote values and included fees must remain distinct from eventual
account debits; historical closes do not reconstruct counterfactual quotes.
This candidate does not connect to Jupiter or claim quote completeness.
[Jupiter Order & Execute](https://developers.jup.ag/docs/swap/order-and-execute)

Repeated strategy selection can create false discoveries. An independent family
registry and untouched holdout policy remain prerequisites for useful evaluation;
this fee report does not calculate a PBO/DSR statistic or make eligibility claims
for the current drawdown objective. [Bailey et al., Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)

Public documentation was the only network research. No provider API/key request,
licensed-data acquisition, transaction, account mutation or cost was authorized
or performed in this candidate's preparation.

## Ordered remaining evaluation gates and parallel work

1. Complete final-source CI and review the experiment-family and split contracts before evaluator integration.
   Adoption of a fee report is not permission to integrate it into production.
2. Build the append-only experiment-family registry: prepared, failed and complete
   runs; objective/domain/cost/source/data choices; exclusions; stopping rule;
   holdout access and subsequent contamination. This is independent of the
   fee-report code and can proceed in parallel with split-manifest design.
3. Freeze the split/availability contract and provider replay clock: original
   observation time, provider availability, receipt, quote age/gaps, history,
   signal, action/fill and terminal intervals. Preserve current gap rejection and
   `market/replay_feed.py:23–31` provider-replay refusal until separately reviewed.
4. Define a production-solver adapter using the same 460-pair domain, capital,
   risk lifecycle, initialization and logical budget as random search; retain
   fixed/cash/passive controls and unique requests/cache/runtime separately.
   This needs source correctness gates but not provider keys, and can be developed
   independently from data collection. Keep the two EMA genes.
5. Prepare a prespecified longer-prefix sensitivity experiment at identical
   decision boundaries. Slow-60 has only one recursive update after its SMA seed
   at common bar 61, so the current readiness convention is not convergence
   evidence. Compare indicators, near-crossings, intents/fills, rankings and net
   economics. Do not change the current warmup policy while gathering evidence.
6. Review representative point-in-time corpus and cost-calibration acquisition
   scope, licensing, quotas and budget before collection. Research survivorship,
   regimes, missing/delayed observations, notional/liquidity sensitivity, failed
   fees, refunds and timestamped currency valuation. Raw evidence and canonical
   source identities must be sufficient to join attempts without double counting.
7. Only after family/split/cost/corpus/adapter gates, run predeclared forward
   windows with multiple frozen seeds. Keep seed variation separate from market
   variation; never rank/reselect on the final untouched holdout. Report cash
   abstention and underperformance honestly. Eligibility for serial-dependence,
   effective-trial, PBO/DSR or other corrections needs deeper research and a
   separate prespecified method.

Steps 2, 3, 4, 5 and pure scenario review can be prepared in parallel. Empirical
collection depends on acquisition approval; empirical scoring depends on the
family/split/clock, data/cost and exact-domain contracts. Live trading remains a
separate authorization and safety milestone.
