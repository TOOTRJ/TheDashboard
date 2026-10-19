# Fresh Jupiter prospective GA research model — R3-02B

This is a new independent in-process research engine for the reviewed
`jupiter-price-v3-prospective-minute-sampled-close-v1` source. It makes no
request, reads no environment or clock, creates no UUID, connects to no
database, restores no lease and has no runtime entry point. Every wire's
provider, calibration, profitability, native, restoration, lease, hosted,
running and live-trading authority stays false. A later independently installed
native/operator capability is a separate boundary; these flags never flip to
activate the same research wire.

The model has its own configuration, inputs, state, candidate, ledger and
lifecycle. It does not import, inherit, bootstrap, wrap or relabel the old v2/v5
models or states. The source uses the separately reviewed acquisition/parser
and prospective-source contracts, including the explicit nullable optional
metadata policy. No old capsule/mark/state becomes current by replacing a hash
or header. The accepted dependency descriptor is imported and pinned into the
new configuration and source witnesses.

## Formats and complete required configuration

| Boundary | New format |
| --- | --- |
| Configuration | `ga-jupiter-prospective-config-research-v3` |
| Owned model | `ga-jupiter-prospective-model-research-v3` |
| Complete transition | `ga-jupiter-prospective-transition-research-v3` |
| Assessment | `ga-jupiter-prospective-assessment-research-v3` |
| Paper fill assumptions | `ga-jupiter-prospective-paper-fill-policy-research-v3` |
| Lifecycle policy | `ga-jupiter-prospective-integer-us-lifecycle-research-v3` |

`V3Config` requires explicit owner/run/market UUIDs, an independently supplied
`SourceBinding`, and a required `PaperFillPolicy`. The binding pins the current
acquisition epoch, recorder principal binding and recorder package digest.
Its constructor performs lexical checks; it does not authenticate a role,
source, original receipt or server head. The original configuration's genesis
binding remains immutable. An explicit rollover records a successor binding
separately in the owned source state.

Default economic/search values are initial cash1000USD reference units,
seed cash100 per member, search seed0 and account loss2000bps. Those values do
not imply a wallet, USDC conversion or account funding. Only eight fully funded
members, one fixed SOL/USD asset and two EMA periods are supported. Fast3…12
and slow15…60 retain the original configured two-gene operator geometry.
Other genome fields are fixed compatibility primitives, without extra signal
rules or evolvable controls. Unknown fields, unsupported versions, numeric
aliases, noncanonical exact amounts and configuration drift refuse.

The required cost policy has fee, half-spread and slippage as explicit canonical
strings plus a bounded evidence label, evidence UUID and digest. There is no
implicit default zero-cost policy. An explicitly supplied all-zero scenario
is still uncalibrated. The pinned Decimal execution arithmetic retains USD
reference valuation, cash36/price18/quantity18 grids, adverse-price and fee
rounding, retained residual cash, and exact entry/exit plans. Its provenance
is an operator-supplied scenario, with authentication/calibration false.
It is not an executable quote, measured liquidity, actual on-chain costs,
profitability evidence or permission to activate trading.

## Fresh engine and preserved mathematics

The new engine constructs its own private state and staged branches. It uses
fresh reviewed `GeneticAlgorithmStrategy`, `Genome`, `ExactMarkColonyConfig`,
`EvaluationCohort`, `SearchRandomStreams` and explicit strategy/evaluation forks.
The economic plans, fitness function, crossing predicate, lineage primitives,
optimizer evidence encoder and integer mutation operator are reused directly.
EMA/economic/lifecycle algorithms are deliberately ported into the new module;
no runtime helper from a synthetic model creates or wraps its state.

The original gen0/strategy/mutation stream derivation and RNG state are retained.
Completed ordered eight-member common cohorts use the existing tournament
selection and uniform crossover, with actual per-child triangular integer
period mutation and clamp. The provisional ROI minus twice observed historical
drawdown ranking remains a heuristic; trade count and Sharpe do not provide
breeding rewards. Completed no-trade or losing windows remain valid simulation
evidence if risk and funding bounds permit the next cohort. Interrupted windows
have no completed score and are never told to the optimizer.

An offline append-only ledger holds original candidate/source witnesses,
historical allocated economic UUIDs and immutable deltas outside the active
state. Acceptance reexecutes the original new-model preparation, requires full
wire equality, and independently replays exact cash/position/retire/birth deltas.
The scoped ledger also retains every accepted acquisition epoch beyond the
rolling history, registering genesis/successors only after complete acceptance.
Preparation never writes that epoch set, rejected candidates cannot publish an
epoch, and A→B→A reuse refuses. Exact original wire replay remains idempotent
and grants no new epoch or current-head authority.
It is an in-process fixture oracle, not a database receipt, authenticated
identity service, durable restoration or complete native source ledger.
Original wire replay returns its historical owned snapshot, which cannot pass
the current-prior check for continuation after the ledger advances.

## Typed source, immutable provenance and bounds

Bootstrap requires a typed `SampledHistory`, typed `SampledCloseSeries` and a
separate expected history digest. It rederives the complete close series from
the retained strict history and compares the exact supplied series bytes. It
requires 915 contiguous observed minutes/61 completed close-only bars, the
same owner/run/market and recorder package, and the current completed cutoff.
The pure fixtures simulate those records; they do not prove 15h15m of actual
acquisition. No OHLC, volume, retrospective fills, padding or historical market
close is fabricated for an old Bar object.

Protection validates the original typed `SourceMark` against an independently
supplied mark digest and current `ClockBound`; it additionally matches current
scope/epoch/principal/package. It preserves the full original mark and original
receipt identity. Decision requires the exact accepted protective mark and
rechecks its current bound without replacing its body, quote or timestamps.
New history advances one contiguous closed bar with exact retained overlap and
previous history hash; its package must independently equal both the retained
history package and current binding package. A self-consistent rehashed global
history-package change with valid range/overlap and typed rederived close series
still refuses. Ordinary backlog/gaps refuse. Controls do not obtain
market data merely to create a checkpoint. Risk recovery acknowledges the
original trip and requires valid current protective/history evidence.

Full original DTOs and raw/native-record dependencies remain externally required
in the source journal and immutable candidate witnesses. Active state retains
bounded source references, current mark and rolling EMA values. Assessment
cursors refer to the original mark/native receipt/history/series rather than
copying every original pin into eight repeated members. Those references do
not authenticate origin or independently establish derivation. Future native
admission must resolve and pin all original records, normalized packets and
immutable history seals under its accepted scoped server head; a missing body
or reference-only partial validator never acquires authority.

The unchanged stateless numeric codec uses strict tagged integers and binary64
views, refusing bool/int aliases, nonfinite values, structural overflow and
wires beyond262144bytes. Active member/holding capacity8, allocated delta
capacity17 and operation capacity33 stay bounded. Initial prototype assessment
duplication exceeded those existing limits and was reduced to bounded original
references; no limit or old codec was widened. A future compact/component/native
v3 namespace remains a separate R3-03 implementation gate.

## Integer clocks, evaluation and explicit restart

All source, control, pending-signal and causal clocks are integer microseconds.
Current action UTC lower must follow original committed-readback availability
and latest original receipt. All three original wall/monotonic receipt ages,
source age and future bounds remain independently checked by the new source
seam. Its current-clock values are supplied research inputs, not a clock read or
proof of genuine current time. Native admission must reobserve its own clock
after processing/locks and preserve the separately reviewed COMMIT limits.

Only indicator/calendar/cohort math uses the actual event's floor seconds, with
bounded exact integer seconds. There is no artificial next-second wait, future
ceiling label or binary64 receipt conversion. A decision preserves the sealed
protective math timestamp while checking its own later current action bound.
Different causal protective observations can share one floor second; original
mark/ingest identity and true-us ordering prevent duplicate decisions or twice
advancing a completed period. A common cohort must also reach its actual
integer-us one-hour interval before completion; a floor rounding edge cannot
shorten that observed interval.

Operation/evaluation events, assessment finalization and risk
observed/tripped/recovered reports retain their actual supplied `event_us`.
Assessment window microseconds are the original logical protective-action
start and that start plus one hour; they remain null before the cohort starts.
Early-terminal metric capture keeps its original `captured_event_us` while
later finalization records its separate `finalized_event_us`. The old
coarse/math aliases remain for the unchanged optimizer and display views.
These logical window bounds are not a server COMMIT timestamp or final native
freshness proof.

The exact-hour boundary fixture first makes the unchanged coarse cohort
`due` predicate true while the original protected-action interval is100ms
short. That decision appends its valid close but publishes no assessments,
replacement, births or optimizer tell. A separate newly captured literal mark
200ms later, still in the same math second, then satisfies the complete logical
hour and publishes one ordered eight-member score/selection batch. Each
protective/decision pair retains its own original mark and receipt; there is no
replacement of a pending observation, wall-clock sleep or native-clock claim.

Same-process monotonic regressions refuse. Explicit acquisition-epoch rollover
is the only transition permitting a different monotonic epoch. It retains
holdings, identity history, market/history sequence and immutable original
receipts, aborts the partial cohort without scores, records the new binding,
and pauses ordinary running state. It creates no lease. Paused state retains
the original refusal to consume quotes: explicit Resume precedes fresh
protection, and a later valid fresh mark is required before the reviewed
restart-clone math can replace the interrupted optimizer state. Risk recovery
retains its separately checked trip/current-source rules. Stop aborts/unpublishes
partial scores and preserves held positions without a stale or fabricated liquidation.

This rollover supports the same accepted recorder package in a new acquisition
process. The positive fixture preserves held accounts/positions, original
915-minute/61-bar history and all original prior IDs, resets the new process's
monotonic clock explicitly, refuses an old-epoch mark, resumes, and accepts
strictly increasing original new-epoch ingest references. Fresh protection and
restart close holdings at the explicit new mark before creating eight clone
members. The following exact 30-minute overlap seal contains unchanged old
process anchors and independently constructed new-process anchors; one full
decision appends one close and continues evaluation without another 915-minute
warmup. This is an offline consistency proof of supplied records, not an
authenticated restart or native ingest receipt.

Recorder-package upgrades refuse at rollover. The current prospective source
seal pins one package; continuity across different packages needs an explicit
accepted archived-decoder/registry dispatch or a new warmup. No package field,
old anchor epoch, wire header or digest is rewritten to simulate that work.

## Verification status and remaining gates

Literal-source tests compare independently constructed new prospective history
and original synthetic-v2 history on the same normalized close/quote series.
Both formats remain intact. Neutral comparisons cover exact founder phenotype,
EMA values, optimizer RNG graph, selection metadata, every economic operation,
cash/holdings and actual two-cohort child periods. New microsecond/provenance
fields intentionally have their separate contract; no version fields are
stripped to turn old states into new ones.

The complete focused model class passed20/20, zero skips, in125.704s
under locked local CPython3.12.14, with networking denied and
environment/dotenv disabled. It includes exact normalized-close equivalence
over two completed cohorts, actual integer child mutation/RNG graph,
same-floor true-us observations, strict costs/configuration/source hash/body
refusals, stale/scope/monotonic clocks, economic ID reuse, missing-bar refusal,
held Stop, early-terminal freezing until the shared deadline, exact risk-trip
acknowledgment, the explicit same-package rollover continuation, independent
history-package refusal, unseen-epoch reuse refusal/rollback, true-us
reporting and the exact-hour negative/positive boundary. The affected five
cases separately passed5/5 in36.338s. An independent reviewer reran only the
epoch and package cases:2/2 passed, zero skips, in10.448s. No provider,
database, Docker or runtime-worker fixture was launched for these checks.
The model source hash for this acceptance is
`71a6daff63187686c879227afc5d1207adc010b00c14d5f84b935befc233afb5`;
the policy hash is
`d53c584a0516293473585db691bbd4b5b2c7568f4772f580e045574117b034ab`.

The previous18-case model class passed18/18, zero skips, in104.539s before
the explicit history-package, unseen-epoch and true-us reporting additions.
The19-case predecessor class passed19/19 in107.001s. The additional exact-hour
boundary case passed1/1 in17.398s before the final20-case acceptance above.

The prior focused model class passed17/17, zero skips, in81.899s.
The added same-package rollover continuation first refused a fixture that tried
to protect while paused, consistent with the preserved lifecycle; after the
fixture ordered Resume before fresh protection, that case passed1/1 in22.413s.
An initial test-only identity-oracle attribute typo also failed before this
correction; those failed/intermediate runs are not counted as acceptance.
The dependency base is the reviewed prospective source commit `a78e734` plus
the reviewed metadata/parser-policy commit `282c087` (adopted locally as
`ab050739`); no old model/acquisition/native SQL was changed by this model slice.

This proves bounded offline research-model consistency only. No native admission,
compact/restoration/schema join, runtime performance,
quota/billing/CPU adequacy, authenticated source reader, recording transport,
native original-command recovery, source/epoch/identity ledger, retained-storage
budget, hosted Start/Stop or paper pilot is claimed. The full existing source
and model remain separate from live funding, signing, swaps and trading.
