# Provider-bound GA checkpoint and evaluation research

Research date: 2026-10-08. This report accompanies PAPER-COMPACT-02B2. It
separates implemented offline evidence from the database, restoration and
continuous-operation gates. No live wallet operation, hosted database mutation,
worker activation, account configuration or dependency installation is part of
this research.

## Decisions

1. Keep the two evolvable EMA genes for the first working paper profile. Keep
   population eight, one SOL/USD reference asset, fixed capital/risk controls,
   completed common windows and a later eligible execution quote. Adding genes
   now increases the search and validation burden without fixing persistence.
2. Retain the complete GA/cohort/RNG evidence until an explicit decoder proves
   byte-for-byte next-command equivalence. A seed is insufficient for continuing
   a partly consumed random stream. Do not remove serialized fixed gene fields
   merely because they are not currently evolvable.
3. Use typed immutable components with scoped hashes and a bounded active
   manifest. Preserve complete history separately, once per original command.
   Component reuse is a proposed storage optimization, not evidence that a
   server retained a component or committed a command.
4. Keep Jupiter Price V3 for current USD reference marks and Swap V2 for future
   amount-specific execution evidence. Keep the historical candle adapter until
   a replacement satisfies the actual EMA/history/provenance requirements.
5. Preserve the current objective while measuring sensitivity. Cash is a valid
   benchmark; insufficient activity/evidence needs an explicit assessment label,
   not an automatic reward for making trades. Profitability is still unproved.

## What this slice implements

`research/provider_ga_model.py` and `research/provider_source.py` are separately
versioned copies of the reviewed offline lifecycle and source rules. They do
not change v3/v4/v5 admission or route production into a new model. The owned
state retains eight current accounts/members, all open holdings, risk, pending
decisions, indicator state, complete optimizer/cohort evidence and bounded
provider history. Bootstrap validates 61 completed 15-minute bars before seeding
EMA at the current startup clock; warmup cannot execute historical trades.

Protective preparation validates the original provider frame before accepting
its sequence. Decision preparation uses that same accepted frame and validates
the next completed candle bundle. Source epoch, strict block order, source-time
estimate, age floor, receipt clocks, freshness, completion margin and gap/revision
refusal remain explicit. Control Stop requires no new market request. Staged
provider inputs live in a detached per-call ledger facade; preparation cannot
silently replace the ledger's current source or advance its optimizer.

Finalized assessment records now pin the provider policy, epoch, original frame
and document identities at the common start/end and at metric capture. Early
terminal economics/source freeze before retirement and remain distinct from the
later common deadline. Interrupted cohorts retain observed economics but
withhold ROI/fitness eligibility. Provider manifests identify worker-parsed
records; their hashes do not authenticate Jupiter/Birdeye or let SQL reconstruct
the original response. Raw document archive availability remains a separate
requirement.

`research/provider_checkpoint.py` uses eleven flat typed slots: configuration,
optimizer, cohort and eight genomes. Each block binds owner, run, kind, entity,
generation, format and hash policy. A complete resolver refuses missing, extra,
duplicate, foreign, stale and substituted blocks and audits optimizer/cohort/
phenotype mirrors. The resolved capture must equal the original owned active
state. The resolver returns primitive evidence; it constructs no RNG, strategy,
state, lease or execution capability. Economics, historical identity uniqueness,
assessment completeness and lineage still require independent locked SQL
admission, rather than trusting this worker-side test oracle.

## Numeric transport and budgets

All JSON integers use a canonical decimal `$integer` tag; actual finite binary64
values use a canonical `$float64` hex tag. Booleans remain booleans. Untagged
numbers, duplicate keys, reserved-tag collisions, noncanonical decimal/hex,
nonfinite floats, oversized integers, cyclic/unsupported values and excessive
depth/nodes/string/whole-byte budgets fail closed. This preserves signed bigint
counters and unsigned 64-bit block references through an actual Node JSON
parse/stringify round trip. PostgreSQL-native receipt hashes are not substituted
for the explicit UTF-8 component hash.

Ordinary revisions end at 2^63−2, with 2^63−1 reserved for Stop. Ordinary monotonic
counters/source sequence reject before wrap; no reset or epoch reuse extends a
run. Generation/name allocation remains signed 32-bit and model timestamps
remain bounded by 2^40; source clock/time limits remain independently tighter.
These are declared research bounds, not arbitrary-precision runtime promises.

The manifest budget is 64 KiB, each component 192 KiB, and complete component
aggregate/resolved model 256 KiB. A complete ordinary compact request must fit
192 KiB, leaving a 64 KiB margin for Stop within the 256 KiB research envelope.
The request includes original command UUID, owner/run, prior reference, following
manifest, changed blocks, complete operations/history/evidence/events. Both
tagged PostgreSQL-spaced JSON and decoded spaced JSON are charged, alongside
the separately bounded complete component set/resolved state. Sending fragments
cannot bypass these limits. The margin is a proposed byte budget; PAPER-COMPACT-03
must additionally prove reserved database rows, locks, transport deadlines and
native Stop/receipt behavior at the final transaction boundary.

## Reproducible capacity and component invalidation

The capacity artifact is `research/provider-ga-capacity.json`. Its two traces
use literal synthetic Jupiter/Birdeye responses parsed by the actual adapters,
then prepare, capture, resolve, encode and accept every candidate through the
mandatory offline ledger. Each trace covers 32 completed windows, 515 complete
candidates, 256 finalized assessments, source sequence 257 and EMA count 189.
Sparse and dense candle schedules intentionally generate different trading
activity. They skip ordinary intervening seconds; these counts are not a
real-provider request-rate or sustainability measurement.

| 32-window trace | Maximum resolved active bytes | Maximum complete compact request bytes | Maximum full candidate bytes | Closed positions |
| --- | ---: | ---: | ---: | ---: |
| Sparse | 60,895 | 145,567 | 185,736 | 221 |
| Dense | 60,927 | 159,934 | 205,244 | 512 |

Each trace reuses all typed blocks in 481 of 515 candidates, and retains 333
unique blocks totaling 1,680,162 wire bytes. The two traces share the same
component count/bytes because this constant-price, zero-cost fixture can assign
the same fitness despite different turnover; that is not evidence of comparable
real trading performance. Total compact journal bytes are 16,152,421/17,257,752,
versus 63,542,524/65,018,736 full-candidate bytes. These are logical request
totals; physical three-window storage is separately measured below.

The artifact records maximum manifest/resolved/full-candidate/compact-command
bytes, total journal bytes, changed-slot counts by phase/kind, unique immutable
component bytes and maximum component-body sizes. Quote-only protective changes
reuse all eleven blocks. A generation replacement changes ten blocks while the
configuration remains stable. Early terminal/cohort evidence can invalidate the
cohort/optimizer before the deadline; a design that assumes only one change per
hour would lose this evidence.

There is no proof yet that the optimizer is minimal. The first safe minimization
experiment should split its primitive field inventory into: current population
and aliases/order; selection cohort/frozen results; search epoch and mutation
event; private RNG state including cached Gaussian values; immutable controls;
and historical reporting fields. Remove only fields proven irrelevant to every
next prepared byte across mid-window, early-death, selection, interrupted/restart
and uncertain-commit cases. Compare stored bytes, changed-block frequency,
readback expansion and validation work as well as payload size. A smaller block
that invalidates on every quote can cost more than a larger stable block.

Python documents explicit RNG state capture/restore and version limitations on
reproducibility. DEAP's checkpoint tutorial also saves current population,
generation, reporting state and RNG state; its standard algorithms require
custom checkpoint integration. These sources support preserving continuation
state. Their pickle example is not a suitable decoder for this application's
untrusted durable evidence. [Python random](https://docs.python.org/3.12/library/random.html),
[DEAP checkpoint tutorial](https://deap.readthedocs.io/en/master/tutorials/advanced/checkpoint.html).

## Actual PostgreSQL storage experiment

`tests/measure_provider_ga_research.py --measure` creates a disposable local
PostgreSQL 17.6 instance using the already installed image. It has no network,
ports, host data mounts or application credentials. Only the owned container is
removed. The experiment inserts the same three-window dense trace into a full
candidate journal and a tagged compact journal, with unique typed components
and complete per-revision dependency pins. Both journals have the same
owner/run/revision primary key. The component/pin tables have their own indexes
and a real dependency foreign key.

`research/provider-ga-deep-research.json` records row counts, heap bytes, table
bytes including TOAST, index bytes and total bytes for every table. The comparison
charges the component store and dependency indexes as well as the compact
journal. Logical JSON savings must not be reported as equivalent physical disk
savings. PostgreSQL can compress/offload large values with TOAST, and its total
relation function includes indexes/TOAST. [TOAST](https://www.postgresql.org/docs/17/storage-toast.html),
[database size functions](https://www.postgresql.org/docs/17/functions-admin.html).

One hundred warm server-side reads per case measure full/compact row lookup and
component join p50/p95. They do not perform full independent validation,
projections, forced detoasting of every body, TLS/handshakes, locks, receipt
recovery or COMMIT fault injection. Physical measurements also exclude WAL,
backups, old retained journals, raw provider archives and additional production
tables. This is a toy layout, not a migration or native contract. Larger retained
datasets and actual hosted measurements remain necessary before budgets,
retention periods or continuous operation are approved.

Measured three-window dense results (51 journal rows, 43 unique components,
561 dependency pins):

| Physical relation | Total bytes including indexes/TOAST |
| --- | ---: |
| Full candidate journal | 2,236,416 |
| Compact journal | 835,584 |
| Unique components | 204,800 |
| Complete dependency pins | 221,184 |
| Compact layout total | 1,261,568 |

This fixture reduces the charged physical layout by 43.59%, compared with
71.51% fewer logical journal bytes. The smaller physical reduction demonstrates
why counting only the compact request would overstate savings. Complete pins
cost more physical space than the component store at this short horizon.
Optimizer bodies reach 39,826 tagged bytes, versus 952 for cohort, 2,220 for
configuration and 755 per genome. Preserve the optimizer first and investigate
its safe decomposition later. The observed quote-only protective updates all
reuse eleven blocks; the startup decision changes two and each replacement ten.
Real outages, recovery/early death and mutation policies can change that pattern.

Local warm statement p95 is approximately 15.1 µs for full lookup, 12 µs for
compact lookup and 29.05 µs for component lookup. The queries do not force full
body validation/detoasting; these numbers must not be presented as end-to-end
SQL, API or hosted worker latency.

## Conditional journal workload and the next contract

The workload-planning artifact also samples one fresh window's quote-only
requests: nine protective requests average21,054 bytes, and three decision
requests average28,626 bytes. The samples include changing holdings/intents and
are too small to estimate a real steady-state distribution. **Conditionally**,
two such accepted commands every second would journal about49,681 bytes/tick,
4.29 GB/day or128.77 GB/30 days of logical JSON, before additional candles,
replacement/projection/source archive/WAL/receipt data and physical compression.
The current worker is closed and has not demonstrated that rate. This is
arithmetic over measured fixture means, not a throughput/storage forecast.

Consequently, a small bounded active model alone cannot establish continuous
paper readiness. Before finalizing the durable contract, investigate stable
source-bar/EMA components and dependency-safe journal retention alongside
per-command/history completeness. Candle/indicator arrays change less often
than provider frames and are still repeated in the manifest. Do not deduplicate
them by discarding freshness clocks, collapsing protective priority, or treating
a component diff as ACK. Any new partition must preserve complete resolution,
Stop capacity, source/holding evidence and later exact continuation proof.

## Fitness, inactivity and costs

The implementation still uses provisional `ROI − 2 × observed historical max
drawdown`. For positive drawdown d, an active probe with ROI r beats cash only
when `r > weight × d`; its crossover is `weight = r/d`. For example, ROI 0.1%
and drawdown 0.2% yield −0.3% at weight two, so cash's zero score wins. Changing
the sign or rewarding trade count would hide the risk tradeoff and can promote
unnecessary turnover. A zero score by itself does not establish that an inactive
probe has useful predictive evidence.

The artifact includes eight **fresh** single-window replays across two synthetic
quote paths, using fee assumptions 0, 2, 10 and 50 bps per side. The private
credential-free test ledgers reuse fixture identities to keep candidate/RNG
inputs equal; they are not hosted runs or mixed durable histories. Finalized
records include exact cash/ROI/drawdown and closed
trade counts after liquidation. A rising illustrative execution quote is
independent of alternating signal candles, so these are accounting/objective
diagnostics rather than plausible market simulations. Costs are uncalibrated;
no scenario stands in for actual Jupiter route fees, price impact, network/tip,
rent or liquidity/latency effects.

Weights 0, 0.5, 1, 2 and 4 are arithmetic diagnostics over those newly finalized
metrics. They show score/cash crossover sensitivity without writing new scores
onto prior database results. They do **not** prove the population trajectory
under a different selection objective: that requires a separately versioned
fresh multi-window replay because an early ranking change alters parents,
offspring and later trades. Execution cost policies similarly require separate
run identities and comparisons over the same frozen dataset/availability clock.

The next policy experiment should report cash and a fixed EMA baseline beside
GA, net return, maximum drawdown, exposure, turnover, closed count, coverage,
terminal/aborted status and confidence/insufficient-evidence labels. Predeclare
the weight grid, cost/size scenarios, seeds and search budget. Keep independent
account-level risk limits outside fitness. Do not optimize objectives and genes
on the final evaluation sample or force a minimum number of trades to manufacture
an advantage over cash.

The fresh fixture gives the same two closed trades to all eight members within
each fee case; coarse candle/quote schedules can make different EMA genes
behaviorally identical. It therefore offers eight ledger checks, not eight
independent demonstrations of an edge. Per-member results:

| Fee per side (bps) | ROI (%) | Max drawdown (%) | Actual fitness at weight two (%) |
| --- | ---: | ---: | ---: |
| 0 | 0.490844 | 0 | 0.490844 |
| 2 | 0.470603 | 0.010035 | 0.450533 |
| 10 | 0.389743 | 0.050135 | 0.289472 |
| 50 | −0.012147 | 0.249679 | −0.511504 |

The 50-bps scenario loses even on this favorable illustrative rising quote;
cash wins for every nonnegative tested weight. At 2/10 bps, cash crossover
weights are approximately 46.90/7.77 in this fixture. Neither observation
calibrates the actual market, and neither changes the production weight or costs.

The second quote path briefly marks the held position lower, then returns to
the same later fill quotes. No protective threshold is crossed. Its realized
ROI stays equal while observed drawdown changes, exposing the actual objective
effect. With 2-bps fees, ROI is +0.470603%, drawdown 0.252693%, and the score
is −0.034782%; cash wins at weight two even though the probe made money.
The crossover weight is approximately 1.8624. This is an explicit accounting
and scoring fixture, not grounds to choose that weight for real markets.

## Evaluation and cross-policy comparability

DSR research addresses selection bias from repeated trials and non-normal
returns. PBO research explains why a single reused holdout does not account for
all adaptive trials. They motivate recording rejected configurations, all seeds,
policy changes and aligned return series, rather than retaining only winners.
Eight probes in the same market/window share exposure and are not eight
independent experiments. A short cohort with few trades cannot supply a reliable
Sharpe/DSR/PBO claim. [Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf),
[Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

Recommended protocol: freeze an immutable point-in-time dataset and publication/
receipt schedule; use chronological train/validation periods and prespecified
walk-forward windows; reserve a final sample used once after all choices; log
the complete adaptive search; verify warmup precedes scoring and each action
uses only then-available data; compare fixed baselines under identical execution
assumptions; report robustness across seeds/regimes/costs and abstention. Leave
gaps, revisions, source failures and aborts visible. Statistical correction is
additional evidence, not a substitute for these controls or proof of future
performance. Develop DSR/PBO only once the complete return/trial data supports
their assumptions; investigate effective trial dependence and temporal leakage.

Freqtrade's lookahead analysis compares full and sliced backtests to detect
changed indicators/signals. Its documented caveats include untriggered signals,
pair-dependent behavior and limit-order false positives. Borrow the validation
idea: truncating future provider documents must not change an already prepared
decision. Do not import its altered capital/protection assumptions as our paper
ledger policy. [Freqtrade lookahead analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/).

Compare policy versions through common source/execution experiments and separate
results, not by retroactively converting fitness. Pin code/profile, exact genes,
evaluation/fitness/execution/source policies, library/runtime versions, source
archive identities and original run/command/cohort. Old records with absent
final drawdown/provider context must remain explicitly missing.

## Jupiter, history and workload

The complete official index and endpoint-specific price/portal/swap pages were
reviewed. Price V3 supplies current USD reference values, accepts up to 50 mints,
and includes block reference information. The reviewed index/price contract does
not document a ranged historical OHLCV endpoint for EMA warmup. This is an
inference from the reviewed public contracts, not a statement that Jupiter can
never offer history. Historical order/PnL endpoints are not interchangeable with
historical candle data. [Documentation index](https://developers.jup.ag/docs/llms.txt),
[Price V3](https://developers.jup.ag/docs/price).

The current plan page states that plans share data freshness/latency and differ
in rate/credits. It lists Developer at 600 requests per 60-second main bucket
and 25M included monthly credits; Price V3 and Swap V2 order/build each cost
one credit in the published table. Actual organization overrides/metering need
portal verification. The worker remains closed; no paid market calls or billing
settings were changed for this report. [Plans](https://developers.jup.ag/docs/portal/plans).

Current rate documentation makes the main quota organization-wide across keys,
with Price/Swap/Tokens sharing a sliding 60-second bucket. Execute has a separate
bucket. A reset header identifies the next freed slot, not a complete replenished
bucket, and additional firewall limits may apply. Reserve retries and other
endpoint requests; no trading sample justifies operating at the exact ceiling.
[Rate limits](https://developers.jup.ag/docs/portal/rate-limits).

Derived planning arithmetic for a 30-day month:

| Current-price topology | Requests/minute | Requests/month at continuous operation |
| --- | ---: | ---: |
| One shared 1 Hz poll for eight same-asset probes | 60 | 2,592,000 |
| Independent 1 Hz poll for each of eight probes | 480 | 20,736,000 |
| One shared 1 Hz poll across fifty supported mints | 60 | 2,592,000 |

These omit candles, block-time/RPC work, amount-specific route requests, retries,
other endpoints and actual unchanged-price scheduling. Sharing one immutable
frame per epoch/asset/decision boundary is preferable to per-probe polling; do
not refresh its receipt to make a reused frame fresh. Batching reference marks
does not batch size-specific executable swaps or certify sufficient liquidity.
Measure real request/source-age/429 distributions before choosing rates.

For future live accounting, Swap V2 distinguishes route-result token amounts
from wallet totals and total fee rate from Jupiter platform fee. The SOL-stable
platform-fee table currently shows 2 bps, but gasless/additional charges and
amount-dependent responses require actual fee fields; our USD paper ledger is
not a SOL/USDC wallet ledger. [Order and Execute](https://developers.jup.ag/docs/swap/order-and-execute).

Birdeye's official support documents list OHLCV V3/historical price and scaled
UI token considerations. Its reference URL was inaccessible through the web
reader in this session; that limitation leaves entitlements, retention rights,
request metering, completion/revision distributions and replacement coverage
open. User-confirmed Jupiter retention rights remain accepted. Do not remove
Birdeye until another source supplies the same validated point-in-time candles.
[Birdeye scaled token support](https://bds-support.birdeye.so/hc/en-us/articles/48443824197785-Birdeye-Now-Supports-Scaled-UI-Amounts-for-Solana-Token-2022).

## Public code worth using as references

| Project | Useful idea | Recommendation for this project |
| --- | --- | --- |
| [DEAP](https://github.com/deap/DEAP) | Explicit variation/selection, invalidated fitness, genealogy, checkpoint tutorial | Use as an independent operator/checkpoint design reference; it does not provide our atomic economic/provider/native contract. Its LGPL license needs review before copying/incorporating code. |
| [Freqtrade](https://www.freqtrade.io/en/stable/lookahead-analysis/) | Sliced/full backtest bias checks and failure caveats | Adapt test methodology to frozen provider streams. No need to replace the dashboard/ledger or install its runtime for this slice. |
| [Hummingbot Gateway](https://hummingbot.org/exchanges/gateway/jupiter/) | Solana router interface, separate quote/execution paths, alternate routers | Evaluate later for connector abstraction/failure fixtures. The reviewed Jupiter guide still references legacy lite API/API documentation; audit actual pinned connector code against Swap V2 before adoption. Added wallet/server/dependency operations require a separate design review. |

No repository or library can establish strategy profitability or solve our
original-command recovery, scoped credentials, independent risk admission and
point-in-time archive requirements by being installed. Replacing the current
worker now would reopen those already reviewed boundaries. For this MVP, use
reference ideas and focused fixture comparisons first.

## Remaining deeper research, ordered by dependency

1. PAPER-COMPACT-03: real limited-role SQL validation, durable uniqueness,
   complete history/lineage/economics, original-ID replay/receipt, source/lease
   freshness at final commit, dependency pins and reserved Stop capacity. Include
   held locks, late rollback, cancellation/lost reply and old/new readers.
2. PAPER-COMPACT-04: allowlisted explicit restoration and whole next-command
   equivalence. Only then attempt minimal GA/RNG/component removal.
3. PAPER-COMPACT-05: longer retained-state physical storage/TOAST/index/WAL and
   validation/lock/COMMIT/relay tails; dependency-safe archive/retention; actual
   closed hosted multi-window restart/holdings/receipt acceptance and cost.
4. DATA/RES: actual shared Jupiter quotas/credit metrics, Birdeye entitlements
   and archive rights, publication latency/gaps/revisions, immutable representative
   datasets and amount-specific cost/availability evidence.
5. BASE/RES/LIVE-01: full fresh multi-policy/multi-seed cost/weight experiments,
   baseline/cash comparisons, predeclared heldout/walk-forward acceptance and
   multiple-testing/dependence research. Do not use synthetic capacity results
   as a performance/promotion signal.
6. LIVE-02…07: separately authorized custody/signing, integer token settlement,
   original transaction uncertainty reconciliation, wallet fills/P&L, protective
   admission and measured execution infrastructure. A faster host/RPC is useful
   only after measuring the actual strategy's latency and adverse execution.

The reusable-connection study already recorded in TODO remains separate:
prove idle/session/role cleanup, unknown-COMMIT quarantine, TLS/SCRAM and
already-connected expiry/revocation before adopting a pool. This slice neither
installs a pool nor relaxes the current original-command/no-retry transport.

## Stable source/EMA partition and journal budgets — 2026-10-09

PAPER-COMPACT-03A adds `ga-provider-checkpoint-research-v2`, its own typed
component/transport formats and thirteen explicit flat slots. The previous
eleven-slot format, provider model, all genes and full optimizer/RNG evidence
remain unchanged. Two generation-zero slots hold completed source bars and
EMA state. A quote-only update reuses both; a completed candle changes both;
cohort replacement reuses them if their contents did not change. Generation
zero does not certify freshness. Current frame/receipt/sequence/source epoch,
holdings, pending decisions and frozen terminal metrics remain in the manifest.
Every original command retains its original UUID, operations, immutable history,
evidence and events, plus its prior manifest digest and changed components.

The bounded adapter validates all thirteen scope/hash/type/reference slots and
complete aggregate before expanding into the existing provider checkpoint
validator. That validator audits full source/EMA correspondence and GA/economic
mirrors; capture additionally matches the owned original state. Complete command
evidence is compared through canonical tagged numeric bytes, preserving binary64
values as well as integer identities. This preserves exact continuation evidence
without a decoder or runtime grant. It is a correctness prototype; repeated
validation/encoding and adapter allocations are not a fast native implementation.
Native/SQL must prove its own canonical numeric/hash boundary and independent
transition validation. Hashes do not authenticate a provider response or ensure
its raw archive remains available.

Forty-three focused tests pass: ten new partition tests, twenty unchanged active
format tests, six reference tests and seven canonical/forward package tests.
They cover missing/foreign/duplicate/old-format blocks, rehashed inconsistent
source/EMA, exact prior and original-ID transport, full aggregate capacity,
detachment, candle/replacement reuse and production version refusal. Stop with
eight held positions preserves those positions and cash, aborts assessments
without scoring and creates no fictional closed fills under the existing policy.
No operator may interpret stopped holdings as liquidated or restart authority.

The same synthetic sparse/dense32-window traces each complete515 candidates and
256 assessments with221/512 closed positions. Every resolved state and original
command evidence matches v1. Maximum resolved state remains60,895/60,927 bytes;
maximum v2 manifest is12,020 bytes; complete request maxima135,705/150,040 bytes
(v1:145,567/159,934). Total request wire bytes fall22.93%/21.52% to
12,448,392/13,544,539. Retaining all historical stable blocks increases unique
components from333 to591 and their wire bytes to3,064,369/3,067,441. Component
reuse does not make historical component storage free or prove server readback.
[Full capacity artifact](research/partitioned-checkpoint-capacity.json).

Actual disposable PostgreSQL17.6 toy tables compare all three layouts using the
same accepted offline candidate stream. Each compact layout includes every
checkpoint dependency pin, component table, indexes and TOAST:

| Workload | Full journal bytes | Eleven-slot layout bytes | Thirteen-slot layout bytes | v2 reduction from v1 |
| --- | ---: | ---: | ---: | ---: |
| Three dense windows /51 commands | 2,236,416 | 1,261,568 | 1,130,496 | 10.39% |
|64 sequential fresh frames /129 commands, no completed candle | 5,070,848 | 2,326,528 | 1,499,136 | 35.56% |

Both actual PostgreSQL fixtures refuse deletion of a referenced component and
retain every row after that refusal. They use digest-only toy keys, not the
proposed composite owner/run keys, and do not prove native installer/privilege
isolation, receipts or archiving. All fixtures have no network/ports/production
credentials and are removed after measurement.

One hundred warm server samples per query force JSONB text materialization.
Dense v1/v2 journal p95 is5,155.7/4,171.05 microseconds; all-dependency p95 is
228.25/263.70 microseconds. Quote-only journal p95 is7,370.3/4,353.35 microseconds;
all-dependency p95 is326.25/348.10 microseconds. The extra component lookup costs
more in these fixtures even though journal materialization costs less. These are
local warm fixed-order diagnostics; no independent model validation, contention,
TLS, COMMIT, WAL, relay or hosted tails are measured. PostgreSQL can keep large
values compressed/out-of-line and defer materialization, so simple `SELECT body`
was not sufficient for the earlier timing diagnostic.
[PostgreSQL TOAST](https://www.postgresql.org/docs/17/storage-toast.html).

Rate arithmetic remains conditional, not a production cadence. The32-window
quote-only sample means imply v2 logical journals of2.62/3.01GB per day at one
accepted fresh frame/second and two accepted commands/frame, before candle/
replacement/Stop/projection/archive/receipt/WAL/backup work. The64-frame quote
fixture instead implies1.79GB/day, illustrating state/workload sensitivity.
For the illustrative128MiB logical budget,32-window means exhaust it in
73.76/64.21 minutes at that rate. There is no configured128MiB database limit,
selected rate or demonstrated worker/provider throughput. The existing selected
pilot skips no-op decisions; the hypothetical two-command cadence is not a
measurement of its deployed journal growth. Actual bounded pilot scheduling,
held-position source age and whole native validation must be measured before
changing rate or duration. Never lower protective frequency merely to fit this
arithmetic or treat logical bytes as physical storage/billing.

The next contract journals an original compact request once, pins all dependencies,
uses durable uniqueness/lineage/receipts instead of active-state history scans,
reserves native Stop/reconciliation resources and checks final source/lease age
after all transactional work. Keep current, pending, uncertain, recovery,
unacknowledged relay and unverified archive dependencies pinned. Archive bytes
must be read back and verified before releasing hot pins; original-ID lookup
and UUID uniqueness must survive archiving. Deletion is not a storage policy by
itself: dead tuples and physical reuse/vacuum need measurement.
[Journal and retention design](JOURNAL-RETENTION-DESIGN.md),
[PostgreSQL vacuuming](https://www.postgresql.org/docs/17/routine-vacuuming.html).

**Deep substantial research remains:** larger retained native SQL/WAL/lock/COMMIT/
TOAST workloads, binary digest and pin-index layout, actual stable-block/provider
invalidation and source age, scoped archive costs/readback/rights and cleanup
races. Explicit exact restoration still precedes minimal RNG removal; full fresh
cost/objective/multi-seed/baseline/holdout research remains separately open.
No Supabase migration, hosted schema/configuration, Railway deployment, paid
market request, billing change, archive deletion or activation occurs here.

Reproduce from the project root with the isolated worker environment and dotenv
disabled, without application credentials:

```sh
PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_partitioned_checkpoint tests.test_active_checkpoint tests.test_checkpoint_reference tests.test_canonical_v5_package tests.test_forward_package -v
DASHBOARD_ISOLATED_POSTGRES_TESTS=1 PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m tests.measure_partitioned_checkpoint --measure
```

The measurement requires the already cached pinned PostgreSQL image and the
local Colima/Docker Unix daemon. It never installs or prunes shared tooling.
