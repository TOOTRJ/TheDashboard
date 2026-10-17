# Nestegg calendar, units and accounting research

Research checkpoint for RES-05 and NEST-01/02/03/04, dated 2026-10-13.
This is a model specification proposal and three bounded reproductions, not
an implemented formula change or a calibrated retirement forecast. It uses
public sources and synthetic inputs; no personal financial account is read.

## Reproduced current defects

[The source-bound receipt](NESTEGG-CALENDAR-UNITS-REPRODUCTION-2026-10-13.json)
replays the actual TypeScript functions with the pinned Node runtime and
transpilation, using the existing default inputs plus explicit synthetic fields.
Its SHA-256 is
`28ac98d39c888e5dc6fbcfaba5cbfdb4f3dc2a20a17212120e7efe5cfbf42a21`.
The independent expected values are elementary elapsed-time and compound-growth
arithmetic; they do not depend on another copy of the implementation.

| Case | Current result | Independent expectation |
| --- | --- | --- |
| Primary 60, spouse 40, both end ages 90 | Primary-axis end 90; 360 projected months | max(90−60, 90−40) = 50 elapsed years, 600 months; primary-axis end 110 |
| Age 35, retirement 65, $5,000/month today, inflation 2.5% | First retirement month spends $5,000 | $5,000 × 1.025^30 = $10,487.83789540893 |
| $100,000 savings, no contributions, moderate risk, 0% annual return | First year ends at $100,500 | $100,000 when no return or cash flow applies |

`planHorizonAge` compares endpoint ages before subtracting the primary's current
age. Both deterministic and Monte Carlo paths inherit that shortened timeline.
`retirementSpendAndIncome` starts inflation at retirement rather than the
input's documented today's-dollar base. Both engines impose a positive 0.5%
minimum base/scenario return; Monte Carlo then adds noise, so its realized
monthly draws can still be negative. The separate retirement-income chart additionally
uses a summed benefit assumption instead of the engine's timing/survivor logic.
These findings do not validate the remaining formulas.

## Smallest coherent next model

Use one elapsed-month household timeline. Each person's age at elapsed month m
is their own starting age plus m/12; the household horizon is the maximum of
their remaining modeled durations. Keep elapsed time separate from the displayed
primary age. A primary axis reaching 110 in the example does not mean the primary
remains alive past the entered age 90. Explicit alive/working/retired states must
govern contributions and benefits, including when a first death precedes either
retirement. Freeze whole-month boundary and fractional-age input semantics before
implementation; do not silently round existing saved inputs.

Use today's dollars as the common monetary input base, matching the existing
spending and Social Security input descriptions. Maintain an explicit cumulative
price index from plan start and convert to nominal cash flows on the household
timeline. Choose and version annual anniversary versus smooth monthly inflation
before changing results; either must include the accumulation years and share
the same base with charts, goals, summaries and exports. Real outputs divide
nominal values by that same index. This follows BLS's distinction between nominal
amounts and purchasing power; a fixed future inflation assumption is a scenario,
not an observed future CPI series.
[BLS income and CPI](https://www.bls.gov/cpi/factsheets/income.htm),
[BLS constant dollars](https://www.bls.gov/cpi/factsheets/purchasing-power-constant-dollars.htm).

Keep working-stop dates distinct from benefit-start dates. The existing input
ties them together and cannot represent every claiming choice. SSA documents
that stopping work and claiming can occur at different ages. Its survivor
benefit depends on eligibility and claiming age; eligible benefits are not
simply added together, and switching can be possible. Treat the current
max-of-two approximation as an explicit educational assumption until the input
and state model supports the relevant rules. Do not silently present it as an
SSA entitlement calculation.
[SSA working versus claiming](https://www.ssa.gov/benefits/retirement/planner/stopwork.html),
[SSA survivor amounts](https://www.ssa.gov/survivor/amount),
[SSA survivor eligibility](https://www.ssa.gov/survivor/eligibility).

Account transfers require a ledger. A distribution from a deferred account can
fund spending, taxes or retained taxable cash; it is not automatically loss of
household wealth. IRS's current Publication 590-B describes annual RMDs from
the preceding year-end balance and different tables for certain younger-spouse
beneficiaries. The current monthly balance-based floor and one aggregate
deferred-share input do not implement that full account-specific behavior.
Preserve a clearly scoped approximation until ownership, account type, birth
year, tax basis, distribution timing and retained-cash fields are specified.
[IRS Publication 590-B, 2025 edition](https://www.irs.gov/publications/p590b).
This research does not certify all 2026 or future tax rules.

## Implementation and deeper research order

1. Freeze versioned calendar, monetary base, month boundaries and result/ledger
   fields. Reuse them across deterministic and stochastic paths; invalidate
   results and exports when the model version changes.
2. Implement NEST-01/02 together with hand-worked equal/asymmetric/reversed-age,
   immediate-retirement, birthday, first-death and inflation boundary cases.
   Make charts and summaries consume the same monthly cash-flow rows.
3. Repair impossible/clamped-return and depletion accounting under NEST-03.
   A zero-input/no-flow fixture must preserve wealth; negative returns must be
   either supported or rejected explicitly. Depletion should record unmet
   spending, not erase obligations by clamping assets to zero.
4. Add an account ledger for NEST-04 before claiming accurate taxes/RMDs.
   Test windfalls at the declared retirement boundary, distribution transfers,
   excess income, tax payments and unspent cash conservation independently.
5. Research current IRS/SSA rules and supported jurisdictions, claim-age and
   birth-year behavior, account ownership/basis, pensions and survivor treatment.
   Compare hand examples with authoritative calculators within their supported
   scope. Do not use a retirement calculator for survivor rules it excludes.
6. Research return/inflation distributions, cross-asset correlation, sequence
   risk, clipping bias and sensitivity before interpreting Monte Carlo success
   percentages or prescriptive recommendations. A shared correct ledger alone
   does not calibrate those probabilities.

The existing privacy/result-order repairs can release independently. Formula,
tax, distribution and probabilistic acceptance remain open; no saved inputs,
database schema, account data or financial transactions change in this checkpoint.
