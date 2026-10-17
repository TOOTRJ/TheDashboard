# Frozen paired research and explicit fee provenance

Implemented as a bounded priority-4 mechanics slice on 2026-10-12. It adds no
provider client, worker activation, database migration, dependency or change to
the existing strategy/evaluator. Historical performance, calibrated Solana fills,
the production colony solver and live promotion remain separate gates.

## Freeze before evaluating

`vonneumann.research.protocol.PairedProtocol` stores immutable canonical bytes.
It binds the complete synthetic dataset specification and hashes, reviewed
CPython 3.12.14, existing evaluator/helper sources, this wrapper and artifact
codec, base strategy/risk/capital/execution configuration, exact seed/budget
order and a versioned baseline/selection/reporting contract. Copies returned by
`to_dict()` are detached. Separate protocol seed/budget lists replace the base
ResearchConfig's individual `random_seed`/`random_budget` fields.

Only the original validated synthetic ReplayFeed is admitted. Observed provider
archives still fail; no historical bar is relabeled synthetic and no old Jupiter
response is invented. The current dataset is bounded to 10,000 frames. Asset,
timeframe alignment and required warmup/scoring coverage are checked before
publishing a plan. A changed dataset, source or Python version requires a new
protocol; current verification refuses mismatches.

Bounds are 1–8 unique canonical uint64-string seeds, 1–4 unique ascending budgets
from1–20, at most 16 child experiments, at most 2,000,000 planned account-ledger
rows and 128 MiB total result bytes. The row plan conservatively charges 24 training
accounts and up to 7 distinct selected/control holdout accounts per child. The
wrapper executes children sequentially with fresh accounts. Thirty seeds from
the research proposal are not admitted implicitly; larger experiments need a
reviewed bounded protocol version and an appropriate empirical corpus.

The unchanged evaluator supplies the twenty-pair grid, fixed 9/21 EMA, cash,
passive 25% and 100%, shared initial four candidates, equal logical GA/random
requests, duplicate charges, private deterministic randomness, training-only
selection and fresh holdout accounts. The grid is a separately charged coverage
benchmark. Every child actually computes 24 training accounts and queries their
cached scores; no runtime/evaluation saving is claimed. The reference GA is
distinct from the production colony's solver, reserve and funding lifecycle.

## Complete evidence and verification

Each child retains its complete original payload: configuration, source/runtime,
dataset, candidate/control definitions, training and holdout ledgers, all ordered
fills, search requests/duplicates/parents, selection and training-evidence hash.
The child manifest uses the existing ASCII/sorted/compact/LF artifact codec;
payload bytes/SHA-256 and canonical manifest result ID are retained. The outer
result contains these complete child artifacts, protocol identity and paired
holdout fitness/ROI/drawdown/P&L/cost/trade-count differences against random,
grid-selected, cash, fixed EMA and both passive controls.

Per-budget minimum/median/maximum and positive/equal/negative counts are
descriptive. Search seeds on the same data are algorithm variability, not
independent markets. No p-value, calibrated cost, profitability, production-
solver comparison, native admission or runtime-saving claim is emitted. No
best seed, budget or holdout winner is chosen by this wrapper.

Existing `write_result` exclusive creation/fsync/path/type/size rules are reused
for plan and result directories. A paired bundle has its own `format`; use this
module's verifier, not the individual-evaluator CLI. Integrity loading alone is
not semantic validation. `verify_result` runs every original child again against
the bound context and compares the complete outer payload, including every
ledger and aggregate. Coordinated fresh child/outer hashes cannot bypass replay.
Cancellation returns no result for publication; an incomplete disk bundle is
still refused by the existing codec. Caller-created failed output directories
are not silently overwritten or deleted.

Example in the isolated worker Python 3.12.14 environment, with newly allocated
physical `/private/tmp` directories and an existing synthetic dataset:

```sh
PYTHON_DOTENV_DISABLED=1 PYTHONPATH=services/vonneumann python -B -m vonneumann.research.protocol plan \
  --dataset /private/tmp/owned-synthetic-dataset --output /private/tmp/new-paired-plan \
  --seed 0 --seed 1 --budget 4 --budget 8 --timeframe-minutes 5 \
  --train-minutes 40 --holdout-minutes 40 --fee-bps 2 --half-spread-bps 3 --slippage-bps 5

PYTHON_DOTENV_DISABLED=1 PYTHONPATH=services/vonneumann python -B -m vonneumann.research.protocol run \
  --dataset /private/tmp/owned-synthetic-dataset --plan /private/tmp/new-paired-plan \
  --output /private/tmp/new-paired-result

PYTHON_DOTENV_DISABLED=1 PYTHONPATH=services/vonneumann python -B -m vonneumann.research.protocol verify \
  --dataset /private/tmp/owned-synthetic-dataset --result /private/tmp/new-paired-result
```

These intentionally short windows/five-minute candles and hypothetical costs
are mechanics checks. They do not define the 15-minute paper pilot or a meaningful
historical investment experiment.

## Fee provenance is a separate pure contract

`fee_provenance.py` admits at most 32 immutable annotated components per outcome.
Each records a bounded component/source identity, kind, denomination, payer,
canonical amount or explicit unknown, included-in-quote/additional disposition,
declared/quoted/observed provenance, explicit charged outcomes and refundable/
known-refund state. Supported denominations are separate USD-reference decimal
units, SOL lamports and USDC atomics. All calculations use integers; ambient
Decimal precision cannot affect them, and no exchange-rate conversion is made.

Repeated component IDs or repeated source/kind components are refused. A source
with combined priority-and-tip plus a second tip is refused. Known included fees
are disclosed separately and never debited again. Account additional charges
and sponsor additional charges remain separate. A processed-failure network cost
must be declared explicitly; network fees cannot be assigned to an unprocessed
expiry or pre-submission rejection. Explicitly excluded outcomes are reported.

An active unknown amount/payer/refund or uncertain transaction makes settlement
totals unavailable (`None`), not zero; `require_resolved()` refuses. Known refund
values describe the declared/observed snapshot, not a promise of future refund.
Refunds cannot exceed the recorded charge. Individual and aggregate amounts are
bounded. Invalid types, noncanonical numbers, fractional atomic amounts, unknown
fields and unsupported outcomes fail with fixed safe errors.

This validator does not ingest a quote or authenticate provenance. Incorrect
caller labels can misdescribe real fees; renaming sources is not evidence of
independent charges. Empty/resolved annotations do not prove quote completeness
or economic feasibility. Output explicitly denies settlement/provider authority
and verified quote completeness. It does not apply these new components to the
existing percentage-cost evaluator. Connecting a quote-observed or settlement
ledger requires a separately versioned adapter and independent accounting oracle.

## Actual bounded evidence and remaining work

Four actual child experiments (seeds 0/1, budgets 4/8) run with complete ledgers
and reproduce through the new verifier. Fourteen focused tests pass, covering
pairing/budgets/control metrics, complete artifact identities, coordinated rehash
refusal, nested plan immutability, source/dataset/provider refusal, cancellation,
exclusive publication, and fee/refund/payer/currency/outcome/double-charge cases.
The existing 65 evaluator/search/CLI/artifact/configuration cases also pass in
15.156 seconds. The new focused cases take 4.307 seconds. These are isolated local
test timings; no inference about hosted capacity or empirical performance follows.
The separate retained CLI receipt is
[paired-protocol-smoke-20261012.json](research/paired-protocol-smoke-20261012.json).
Its network/import-denied fresh children and contended local timings are a
mechanics acceptance receipt, not an empirical or performance benchmark.

Jupiter retention is already user-approved; do not request it again. Existing
finite Birdeye warmup success establishes that earlier OHLCV call's access, not
complete historical window coverage, original publication history or separate
retention/redistribution rights. Before representative acquisition: establish
the applicable Birdeye terms/retention entitlement and current account headroom,
freeze mint/window/normalization/publication/gap/outlier/unit policies and a finite
request/CU ceiling, then build the historical adapter. The existing 10,000-frame
synthetic codec cannot directly represent a 30-/90-day minute corpus. Do not raise
that cap or substitute modeled receipts as an incidental extension of this tool.

Keep DATA-01C/E, FILL-01B, BASE-02/03 and RES-01/02/03 open for licensed historical
data, prospective source/quote/quota tails, calibrated fees/impact/latency/
rejection, production-solver equal-domain comparison, effective trial/dependence
research, untouched chronological test and explicit promotion thresholds. The
separate full-v2 SQL/native/restoration/retention/UI/hosted join remains required.
