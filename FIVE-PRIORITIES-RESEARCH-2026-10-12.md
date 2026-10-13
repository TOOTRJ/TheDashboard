# Security, historical data, execution costs, and evolutionary evaluation

Research date: **October 12, 2026, America/Denver**. Public registry/schema
captures below were made on **October 13, 2026 UTC**. This is priority 4 of the
authorized five-priority batch. It supplies implementation contracts and dated
research findings; it does not close the empirical, continuous-paper, or live
promotion gates.

Read alongside [TODO.md](TODO.md), [dependency review](DEPENDENCY-REVIEW.md),
[Jupiter tooling boundaries](JUPITER-TOOLING.md), [GA research](services/vonneumann/GA-DEEP-RESEARCH.md),
[data research](services/vonneumann/JUPITER-DATA-RESEARCH.md), and the
[existing synthetic evaluator](services/vonneumann/OFFLINE-RESEARCH.md).

## Decisions that can be made now

1. Keep **two evolvable genes, fast and slow EMA**, with fixed asset, timeframe,
   capital, exposure, risk, cost policy, and assessment horizon. Adding genes
   does not repair durable admission, source quality, or experimental bias.
   A third gene needs a separate ablation demonstrating benefit on a new,
   previously untouched chronological test set.
2. Keep Jupiter Price V3 for current USD reference marks and Swap V2 for
   amount-specific quotes. Keep Birdeye narrowly for historical candles and
   warmup. Fresh public contracts still do not establish a Jupiter general
   historical-price or OHLCV range endpoint.
3. Obtain bounded historical windows when an experiment needs them, then retain
   the exact licensed input snapshot. A permanent 24/7 historical collector is
   unnecessary for the first comparison; repeatedly downloading mutable inputs
   would make the comparison less reproducible.
4. Preserve the current versioned ROI/drawdown objective while testing its
   sensitivity separately. Do not breed on unstable Sharpe ratios, trade counts,
   win rate, or whichever metric looks best after viewing the results.
5. Compare the GA with fixed EMA, exhaustive grid, paired random search, cash,
   and passive exposure. A profitable GA result alone cannot establish that
   evolution added value.
6. Prepare the October 14 security response, but wait for actual published
   affected ranges and fixes. A stable feature release does not resolve an
   undisclosed vulnerability by implication.

These are project design recommendations. The numerical protocol choices below
are proposals to freeze before acquisition/evaluation, not statistically
calibrated guarantees or observed trading results.

## SEC-05B: current security evidence and release contract

The official October 8 notice still announces an October 14 out-of-band update
for two critical and one high upstream vulnerabilities, with details to be
published with the update. The public notice was successfully retrieved at
`2026-10-13T01:55:20Z`; it does not supply affected ranges or patched versions.
Consequently SEC-05B cannot truthfully be marked fixed on this date.
[Official notice](https://nextjs.org/blog/upcoming-nextjs-security-update-october-2026).

The npm public registry identifies **Next and eslint-config-next 16.4.0** as
latest stable. Next 16.4.0 declares Node `>=20.9.0` and React/React DOM peers
including `^19.0.0`, so the Dashboard's Node 24 and React 19.2.8 meet these
declared direct requirements. This is metadata compatibility, not a successful
application upgrade. Keep framework and its ESLint configuration aligned.
[Next metadata](https://registry.npmjs.org/next/16.4.0),
[configuration metadata](https://registry.npmjs.org/eslint-config-next/16.4.0),
[official release](https://github.com/vercel/next.js/releases/tag/v16.4.0).

Next 16.x is Active LTS and 15.x is Maintenance LTS; 14.x is unsupported.
Adopting npm's suggested Next 14 tooling downgrade would not be a suitable
framework maintenance strategy. Canary builds are unsuitable as the default
production repair. A compatible stable 16.x security release is the preferred
path once its actual advisory is available.
[Support policy](https://nextjs.org/support-policy).

The existing sanitized `scripts/check-advisories.mjs` was rerun with the bundled
Node, empty task-specific npm configuration, public registry, and a temporary
cache. It completed successfully and reported:

| Scope | Fresh result | Meaning |
| --- | --- | --- |
| Full graph | Five affected package entries; exact accepted `GHSA-vfj7-8cjw-p6xm` | One underlying development-only braces advisory propagated through five graph entries |
| Production graph | Zero findings | No known production advisory in this registry scan at this date |

Braces remains 3.0.3, and its reviewed advisory still lists no patched version.
The exception expires **2026-10-26T00:00:00Z** and is bounded to exact dev-only
paths/versions. This does not mean the vulnerability is removed or future
advisories are covered. The existing policy rejects new findings, changed
paths/versions, production findings, invalid scans, and expiry.
[Braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).

**Implementation order when the security release exists:**

1. Capture publication/revision times, advisory IDs, affected/patched ranges,
   supported release branches, and the exact public package metadata. Examine
   bundled framework dependencies as well as direct React packages.
2. Map each actual affected feature to this App Router/proxy/Auth/API/build
   configuration. An unused feature narrows reachability; a login redirect does
   not prove a framework exploit is mitigated.
3. Upgrade exact compatible stable Next/config versions in an isolated install.
   Inspect the complete lock diff and platform-native entries; do not use
   `--force` or peer-dependency suppression to mask incompatibility. Reassess the
   braces path instead of extending its exception automatically.
4. Require clean production scan, valid full-graph policy, Node tests,
   TypeScript, lint, isolated build, and real Auth/proxy/API regression coverage.
   Verify accepted source and exact Dashboard targets before PR merge, then
   verify its exact production deployment and canonical alias.
5. Retain the previous verified deployment/source and define rollback for a
   functional regression. An old deployment is not an adequate permanent
   fallback if the new advisory shows that version is vulnerable.

No dependency, runtime, lock, account, scheduled automation, or cloud setting was
changed by this research. A new check after October 14 is required; this file
does not claim knowledge of a future publication.

## Jupiter and Birdeye: current capability findings

The complete Jupiter and Birdeye documentation indexes were fetched before the
selected endpoint pages. Current versioned Jupiter schema hashes match the
previous reviewed Price V3, Swap V2, and Tokens V2 contracts. The older unversioned
Swap schema remains unsuitable as a V2 contract.
[Jupiter index](https://developers.jup.ag/docs/llms.txt),
[Birdeye index](https://data.birdeye.so/docs/llms.txt).

| Capability | Recommended use | What it does not establish |
| --- | --- | --- |
| Jupiter `/price/v3` | Fresh reference marks with requested/returned mint reconciliation and `blockId` checks | Historical candles, an amount-specific fill, or monotonic references across every request |
| Jupiter `/tokens/v2/search`, category/tag/recent | Prospective metadata, liquidity/audit/verification screening | The historical investable universe or historical risk state |
| Jupiter `/swap/v2/order`, without `taker` | Amount-specific quote-only research through the existing adapter | Past hypothetical fills, landing, or net realized wallet balances |
| Birdeye `/defi/v3/ohlcv` | Bounded historical price candles and completed warmup | Original publication/receipt time or the bot's counterfactual execution |
| Birdeye liquidity history | Optional liquidity-regime/capacity research | Full AMM reserves, routed executable depth, or a validated slippage formula |

Price V3 documents up to 50 mint IDs, omits unreliable/untraded mints, and uses
`blockId` for recency. Missing keys must remain unavailable rather than zero or
silently stale marks. Tokens audit fields and current verification are useful
screens but cannot guarantee safety. Historical order/DCA records are account
activity, not a general market-history dataset.
[Price](https://developers.jup.ag/docs/price),
[Tokens](https://developers.jup.ag/docs/tokens),
[Price schema](https://developers.jup.ag/docs/openapi-spec/price/v3/price.yaml).

**An earlier documentation ambiguity is resolved:** the current Birdeye OHLCV
usage note and parameter agree that `outlier=true` includes outliers and
`outlier=false` filters them. The older project's note that these descriptions
conflicted is historical. Pin this flag explicitly; retain both raw and filtered
small samples in any later authorized semantics check instead of assuming
filtering improves strategy realism. OHLCV allows 5,000 records, omits empty
buckets unless padding is enabled, and retains 1-second history for two weeks
and 15-/30-second history for three months.
[Current OHLCV contract](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-v3-ohlcv).

The current accessibility table includes OHLCV V3 on Standard. Published Standard
capacity is 30,000 CU/month and 1 request/second. Public plan access does not
prove this account's remaining credits, token coverage, retention, or
redistribution rights. The user has already confirmed Jupiter retention;
Birdeye's separate retention/entitlement remains to be established.
[Accessibility](https://data.birdeye.so/docs/guides/data-accessibility-by-packages),
[Pricing](https://data.birdeye.so/docs/guides/payment/pricing).

Birdeye's September 29 release adds pair liquidity history; token liquidity
history also returns open-value snapshots, up to 100 records. This could help
separate thin-liquidity periods from liquid periods in later execution research.
The token page's prose lists only `1m/4h/1D`, while its query enum lists additional
resolutions; response examples use `prev` while query direction uses `back`.
Resolve actual wire semantics, coverage, costs, entitlement and timestamps before
adding an adapter. Avoid treating TVL or aggregate exit liquidity as a universal
price-impact coefficient.
[Release](https://data.birdeye.so/docs/changelog/20260929-release-liquidity-history-pair-and-token-money-flow),
[Token liquidity history](https://data.birdeye.so/docs/data-api/price-ohlcv/get-defi-v3-liquidity-history-token).

### DATA-01E: quota and cost acceptance

Jupiter's current documentation gives Developer **600 requests per 60-second
sliding window**, shared per organization, and a separate execute bucket. The
reset timestamp frees the oldest request's slot, not the whole window. Firewall
limits can be additional. The previous observed first-response remaining=9 and
later remaining=98 are actual project evidence, but neither prove that published
window. Keep the finite worker's explicit reserve/refusal policy until resolved.
[Current quota contract](https://developers.jup.ag/docs/portal/rate-limits).

A plan upgrade changes included credits and quotas, not data freshness/latency.
Published costs are one credit for Price V3 and Swap V2 order/build, ten for
Tokens search and fifty for tag. Avoid frequent discovery when the pilot already
pins its mint. Twelve Price requests/minute at a five-second cadence are 518,400
requests in a 30-day month before quotes, diagnostics and failures: an arithmetic
planning estimate, not billed usage or continuous-service acceptance.
[Plan and credit contract](https://developers.jup.ag/docs/portal/plans).

The next approved finite read measurement should bind endpoint/bucket, original
request ID, status, receipt clocks, sanitized quota headers and credit attribution.
Separate cold/warm connections, source age, clock/RPC lookup and whole adapter
latency; report p50/p95/max and refusal counts. Identify the cause of a regressing
block reference from retained rejected/current evidence rather than asserting
cache routing or a reorganization. Stop on missing/stale quota evidence, source
refusal, 429 or the fixed budget; do not retry or burst to exhaustion. Accept only
a tested aggregate cadence with reserve for protective/control work and a
monthly cost bound. No provider-key call or portal inspection occurred here.

## DATA-01C / RES-03: historical corpus and availability contract

Freeze a **corpus plan before downloading**: mint IDs/decimals, USD units,
interval, exact UTC boundaries, provider endpoint/version/parameters, publication
assumptions, allowed gaps, outlier/padding policy, request/CU ceilings, permission
evidence and rejection behavior. Begin with SOL; name a second liquid robustness
mint explicitly before acquisition. Two successful surviving assets cannot
establish a historical launch-token or failed-token strategy.

A proposed first ingestion rehearsal is two mints over a fixed 30-day period,
one-minute bars aggregated to the strategy's fixed 15-minute timeframe, plus
915 minutes of warmup per mint. This is **88,230 expected minute buckets** under
complete coverage, at most 18 pages at the documented 5,000-record cap if paging
semantics match, and at most 1,800 CU at the current maximum OHLCV tier. Freeze a
20-request/2,000-CU ceiling; abort incomplete coverage instead of topping up
unboundedly. This is request arithmetic, not proof that the account can acquire
it or the data are complete. It tests ingestion, not economic significance.

After ingestion passes, a candidate broader corpus uses the contiguous calendar
windows `[2026-01-04,2026-04-04)`, `[2026-04-04,2026-07-03)`, and
`[2026-07-03,2026-10-01)` in UTC. Each is 90 days, split chronologically into
60 training, 15 validation and 15 untouched test days. Dates are proposed calendar
boundaries, not windows chosen from observed favorable price moves. Two mints,
three windows and separate warmup require up to 783,090 one-minute buckets and
162 maximum-size pages before overlap checks/revisions. Freeze a fresh separate
180-request/18,000-CU ceiling only after checking account headroom and terms;
do not silently extend the first acquisition budget. This finite corpus still
does not measure long-run strategy reliability or justify live trading.

Archive original response bytes once, sanitized request parameters/status,
retrieval time, source schema/hash, exact mint/units/scaling, page boundaries,
deduplication/revision decisions and normalized file hashes. The manifest must
bind the raw-to-normalized transformation and distinguish:

- Historical provider-reconstructed bars retrieved today.
- Observations actually received during a prospective paper run.
- Modeled historical availability/latency and hypothetical fills.

A bar timestamp cannot be repurposed as an observed live receipt timestamp.
An immutable hash protects our snapshot; it does not authenticate the provider
or prove original publication history. Require complete warmup and scored-window
coverage, completed UTC buckets, finite valid OHLC/volume, exact mint/units and
strict chronological ordering. Do not pad missing data into apparent liquidity.
Keep rejected pages/gap explanations in evidence, and never repair a scored gap
from a later download without creating a new dataset identity.

**Concrete implementation gap:** the current runner consumes strict synthetic
one-minute ReplayFeed frames and rejects provider replay. A historical adapter
needs its own versioned contract; do not relabel downloaded bars synthetic or
invent old Jupiter responses to bypass this restriction. Candidate comparison
can use declared next-bar/reference fills, but must say those are modeled
historical fills. Preserve the original engine's later eligible observation rule,
fresh scoring accounts and completed-only warmup.

Acceptance requires an independently checked normalized dataset, bounded
publication/gap/revision fixtures, input/source hashes, exact shared indicators,
suffix-change causality, preserved raw evidence and a fresh deterministic replay.
Representative performance remains open until licensed inputs and truthful
availability/execution assumptions pass.

## FILL-01B / RES-02: a cost ledger that avoids optimistic fills

The current `usd-reference-percentage-cost-v1` model is useful for mechanics and
declared sensitivity; its zero default is frictionless. It is not a Solana
settlement model. Keep that policy readable and create a new version when adding
amount-specific quotes, fixed lamport costs, token-atomic quantities, rejection,
or route-dependent timing. Costs stay outside genes.

For each hypothetical action, retain reference mark/source, decision time,
execution availability rule, mint decimals and exact atomic amount, accepted
quote/router/mode/expiry, and a charge table with **amount, denomination, payer,
provenance, included-in-quote flag, charged-on-outcome rule, and refundable flag**.
Keep USD valuation and USDC settlement distinct. Use Decimal/integer conversion;
never approximate general atomic amounts with floating-point multiplication.

Jupiter order quotes already include its platform fee; top-level `feeBps` can
include extra gasless recoup and differ from `platformFee.feeBps`. Future execute
wallet amounts are `totalInputAmount/totalOutputAmount`; route amounts are
different. Use these distinctions to prevent double-deducting the same fee.
Do not assume a permanent flat fee from one token-pair table or treat a quote as
realized wallet accounting.
[Managed order/execution accounting](https://developers.jup.ag/docs/swap/order-and-execute).

The order schema exposes fee payers and estimated signature, priority and rent
charges. `prioritizationFeeLamports` includes tips. Adding another generic Jito
tip to that field can double-charge. Quote-only requests omit a taker; actual
wallet sponsorship, rent and transaction-build eligibility remain unknown. Mark
unavailable fields unknown rather than zero. A slippage tolerance/minimum output
is a constraint, not observed realized adverse slippage.
[Order schema](https://developers.jup.ag/docs/api-reference/swap/order).

Solana documents a 5,000-lamport base fee per signature and the traditional
priority calculation using requested CU limit and CU price, not consumed CU;
its V1 message format uses an absolute fee. Charge accepted failed transactions
according to their actual outcome, while distinguishing expired/unprocessed and
uncertain submissions. Rent is a cash requirement with possible later refund,
not automatically a permanent percentage trading fee.
[Fee contract](https://solana.com/docs/core/fees),
[Confirmation/expiration](https://solana.com/developers/cookbook/transactions/confirmation).

Proposed evaluation layers:

| Layer | Inputs | Permitted interpretation |
| --- | --- | --- |
| Frictionless | Explicit zero costs | Mechanics control only |
| Declared sensitivity | Fixed fee/spread/adverse-price/fixed-cost/latency/rejection scenarios | Robustness to assumptions, not calibrated net performance |
| Quote-observed paper | Prospective amount-specific quotes, source/receipt/route/fees, declared post-quote delay and failure assumptions | Quote-feasibility and paper accounting; still no actual fills |
| Future settlement-calibrated | Separately authorized signed transactions and reconciled wallet/network outcomes | Measured live execution at tested sizes/conditions only |

Prespecify sensitivity scenarios rather than choosing the profitable one. Test
normal/stressed costs, small/larger sizes, next-eligible/two-observation delay,
missing route, quote expiry, gap exits, explicit rejection, terminal liquidation
and uncertain outcomes. A shared exogenous scenario schedule must be keyed to
asset/time/size/side, so algorithms see the same opportunity conditions rather
than consuming different random failures because they made different numbers
of calls. Retain every refusal; no rejected action receives a fictional fill.

Hand calculations and an independent Decimal oracle must reconcile token/cash
debits/credits, payer-specific fees, embedded spread/impact, failed-action costs,
inventory valuation, rent/refunds and final liquidation. Tests must fail if an
included fee/tip is charged twice, an omitted cost becomes zero, a future quote
is used too early, USD is silently equated with USDC, or rejection creates a trade.
Fit empirical parameters only on calibration/training data; test sensitivity
outside that fit. Candles and aggregate liquidity alone cannot recover past
counterfactual routing, MEV, inclusion, or size-dependent fills.

### Faster Solana connection: measure total execution quality first

Managed Jupiter `/order` plus `/execute` remains the first future live candidate
because it supplies routing and managed landing without a custom RPC submission
pipeline. Beta `/build?mode=fast` removes route splitting and uses global rather
than route-account-specific fee estimation; lower quote latency can come with
worse output or fee estimation. For this 15-minute EMA strategy, choose on net
outcome and operational reliability after measuring the actual bottleneck.
[Fast-mode tradeoffs](https://developers.jup.ag/docs/swap/advanced/reduce-latency).

Fresh Helius Sender documentation now lists **0.001 SOL** minimum tip for Sender
Max and **0.000005 SOL** for SWQOS-only, plus a priority fee. Credit-free does not
mean cost-free. Jito documents a 1,000-lamport bundle minimum, an auction that may
need more, and its sendTransaction path skips preflight. These are capability
and cost inputs, not evidence that either improves this bot's tested fill quality.
[Helius Sender](https://www.helius.dev/docs/sending-transactions/sender),
[Jito sending](https://docs.jito.wtf/lowlatencytxnsend/).

Benchmark source age → decision → quote → durable admission → submission →
landing → confirmed/reconciled wallet outcome, with failure/expiry rates and
total fees. Distinguish HTTP response, provider processing, chain inclusion and
confirmation. Record host region, cold/warm connections and tails; no provider's
headline latency establishes “top-tier” trading. Yellowstone/gRPC/shred streams
should follow a demonstrated data-latency need, not precede working durability.
No signing, submission or new infrastructure installation is authorized by this
research file.

## BASE-02/03 / RES-01: prespecified paired comparison

The existing evaluator is a good mechanics foundation: twenty EMA pairs, fixed
9/21 EMA, cash, passive 25% and 100%, exact training selection, fresh chronological
holdout accounts and a reference GA/random comparison. It uses standalone
accounts, not the production colony's shared reserve/funding/replacement system.
Do not describe its reference GA as the production solver or its synthetic
artifact as a historical performance result.

Freeze one protocol identity before results are computed. Bind dataset/source/
runtime hashes, asset/units/timeframe, warmup/splits, capital/exposure/risk,
training objective/ties, search domain/policy, seeds/budgets, costs, failure
schedule, primary/secondary metrics and stopping/rejection rules. Keep the
twenty-point `{3,5,8,12} × {15,20,30,45,60}` grid as an explicit small domain.
The production integer-domain adapter must be constrained to that same domain
for a fair solver comparison, or use a separately labeled larger-domain study.

**Proposed initial experiment protocol:**

1. Use 30 predetermined seeds, `0..29`, and fixed logical budgets `4,8,12,20`.
   These engineering choices expose initialization/search variability; 30 seeds
   do not create 30 independent market histories or establish statistical power.
2. Pair GA and random on each seed/window/asset/cost scenario with the same
   initial four candidates. Give private deterministic streams to offspring,
   initialization and execution scenarios. Preserve serialized RNG continuation.
3. Count every logical request, duplicate, elite reuse, unique evaluation,
   cache hit, failure, wall/CPU time and evaluator call. Under the primary
   logical-budget comparison duplicates consume budget. A secondary unique-
   evaluation comparison must have a separately frozen duplicate policy and
   work ceiling; do not reward one algorithm with free forced exploration.
4. Treat exhaustive grid as an oracle/coverage benchmark, not an equal-cost
   search. The existing cached fixture evaluates 24 training accounts and
   exposes only requested scores to search; it cannot demonstrate runtime
   savings from avoiding those evaluations. Add an uncached, separately charged
   evaluator when testing actual computational cost.
5. Select each search winner only from training net fitness
   `ROI - 2 * historical maximum drawdown`, with the existing deterministic tie.
   Validation can support a documented research decision; changing policy after
   seeing validation consumes that validation set. Freeze once before the final
   test. No test reranking, seed selection, favorable-window selection, or
   objective/threshold tuning from the test.
6. Carry only causal indicator history into fresh test accounts. Apply the same
   accepted source/cost rules to selected candidates and controls. Passive 25%
   is an exposure comparator; passive 100% is a separate market reference,
   because it has different exposure and no EMA protective exits.
7. Report all seeds/failures and per-window paired differences. Primary search
   outcome: held-out net-fitness difference GA minus paired random; secondary:
   net ROI, worst drawdown, turnover, exposure, rejection, unique-trial count and
   training regret. Also show differences from fixed EMA, cash and passive
   controls. An inactive strategy is valid cash-like evidence, not an automatic
   success or a reason to add a trade-count reward.

The random-search paper supports using random search as a serious benchmark,
but its neural-network experiments do not prove superiority on this two-gene
trading task. Test the actual declared domain and budget.
[Bergstra and Bengio, 2012](https://www.jmlr.org/papers/v13/bergstra12a.html).

Repeated model, seed, cost and asset choices increase selection bias. The
Deflated Sharpe Ratio paper accounts for multiple testing and non-normality;
it requires return-series and effective-trial assumptions. Do not insert its
formula into the current ROI/drawdown fitness or calculate confident DSR from
short, dependent windows and unknown trial counts.
[Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

The PBO paper provides a diagnostic for the selection process using a complete
candidate-performance matrix and combinatorially symmetric partitions. It does
not remove the need for causal indicators, independent fill validation, a final
untouched chronological test, or sufficient observations. Keep full histories,
review dependence/purge rules and window adequacy before applying it. Seeds and
overlapping windows must not be counted as independent market samples. Until a
reviewed uncertainty method exists, report distributions/differences honestly
without IID p-values or universal significance thresholds.
[Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

**Acceptance criteria:** independently reconcile full ledgers; reproduce every
result with frozen inputs/runtime/source; prove a changed test suffix cannot
affect training or winner selection; reject coordinated semantic tampering even
when hashes are recomputed; preserve all requests/failures and no overshoot;
demonstrate matched budgets/domain/source/costs; report underperformance and
unprofitable outcomes. Mechanical acceptance can pass when the strategy fails
economic evaluation. Live promotion thresholds and acceptable risk need their
own frozen decision contract before a future live release.

## Public code worth learning from, without replacing the worker

| Project / primary documentation | Useful design input | Adoption boundary |
| --- | --- | --- |
| [DEAP checkpointing](https://deap.readthedocs.io/en/master/tutorials/advanced/checkpoint.html) | Preserve population, generation, report state and RNG continuation; standard algorithms require checkpoint integration | Its pickle tutorial is unsuitable for untrusted durable state; it does not provide atomic SQL admission |
| [Optuna RandomSampler](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.RandomSampler.html) | Explicit seeds and trial recording for later comparator adapters | Parallel reseeding and built-in treatment of failed trials must not silently change this protocol |
| [Freqtrade backtesting](https://www.freqtrade.io/en/stable/backtesting/) | Explicit assumptions and lower-timeframe detail; useful look-ahead/ledger review patterns | Its documented candle fills/no-slippage assumptions and centralized-exchange limits are not Solana execution |
| [Passivbot optimizing](https://github.com/enarjord/passivbot/blob/master/docs/optimizing.md) | Match the complete fixed evaluation contract before reusing checkpoint fitness | A different strategy/market/risk model; review a pinned version/license before any code extraction |

No library install is needed to finish the current twenty-candidate comparison.
Adopt a reviewed adapter only for a concrete missing capability, with pinned
source/license, fixed seed/duplicate/failure rules and result equivalence tests.
Do not migrate a working two-gene evaluator to a larger optimizer merely because
a repository offers GPU or many-objective features.

## Ordered implementation and deeper-research work

| Order / lane | Deliverable | Completion evidence / outstanding dependency |
| --- | --- | --- |
| Immediate, security in parallel | SEC-05B response packet and fresh scan at actual publication | Actual advisory IDs/ranges/patched source plus Dashboard Auth/proxy/API/build/deployment verification; unavailable future details stay open |
| Immediate, research contracts in parallel | Freeze corpus acquisition/normalization and cost/protocol identities | Explicit licensed input scope, request/CU cap, gap/publication/units policy, fee provenance, paired seeds/budgets and holdout-use ledger |
| Before historical ranking | Historical adapter and bounded corpus rehearsal | No synthetic relabeling; raw/normalized hashes, truthful availability, independently checked causal windows and replay |
| Before calibrated paper claims | Bounded prospective quote/source/quota measurement and cost oracle | Actual compatible source/header fields, measured tails/refusals, fee/payer/no-double-charge acceptance; account-specific permissions/costs remain separate |
| After data/cost contract freezes | Paired fixed/grid/random/GA/cash/passive evaluator and production-solver adapter | All trials, equal domains/budgets, independent ledgers, source bindings, immutable results and untouched-test policy |
| Downstream bot critical path | Full v2 independent semantic SQL → native atomic admission → restore → retention → UI → multi-window/fault/load join | Current batch's durability receipts; this research cannot substitute for source/lease/Stop/idempotency and hosted closed-mode gates |
| Before expanding genes or live promotion | Substantial statistical/microstructure research | Dependence/effective trials, objective sensitivity, insufficient activity/sample length, survivorship/failed tokens, size-dependent impact, historical revisions, provider consistency, MEV/fees/rent/uncertain outcomes and risk thresholds |

This research completes a dated decision/protocol deliverable. DATA-01C/E,
FILL-01B, BASE-02/03 and RES-01/02/03 remain open for their measured acceptance.
No market history was downloaded, no provider key was used, no project/account
was modified, and no signing or transaction operation occurred.

## Public document fingerprints

These hashes bind the exact retrieved public bytes, not permanent provider
guarantees. Dynamic documents can change, so recheck before implementation.
Registry/schema captures are from `2026-10-13T01:55:20Z` through
`2026-10-13T01:55:22Z`; indexes were retrieved later in the same research pass.

| Public artifact | SHA-256 |
| --- | --- |
| October 8 Next security notice | `e87a101318e72945eb0672928ef175365eca57b28ebba301ed71bee4f31319cc` |
| Next/config dist-tags, identical bytes at capture | `e584598fe146931d40bf03489a1c710baa09965986e70ccc6251b5f6ccd4f71a` |
| Next 16.4.0 metadata | `e4e3a816fe9f00647039f01579f9a928c5a6c4783bb7f09b9b72d1c957238c11` |
| eslint-config-next 16.4.0 metadata | `209895f711b86ccc2b56c562a5c982190086225ef80bb7ae5fa7949bb64752c4` |
| Price V3 YAML | `bc798556d98db9f5f5586cbd4deadd3c0839e167c2fffe93f8df9308acc7e029` |
| Swap V2 YAML | `76daa0a94d51cb8ca2488b2cfae22f3ba7dab05444615c7169ce7893cb0ddd67` |
| Tokens V2 YAML | `a1ba94ded9c4cc2a4afe1d20c675bf09e50e4e388f2dffd1042f1ef348837535` |
| Birdeye complete documentation index | `fbe3b5f80d57b3089c4708b15eea74df98d439c4cb97fd45e236b7e95daa6887` |
